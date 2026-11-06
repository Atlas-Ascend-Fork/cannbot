// Copyright (c) 2026 CANNBot contributors
// SPDX-License-Identifier: MIT
// See script/LICENSE for the full license text.

import assert from "node:assert/strict";
import { cpSync, existsSync, lstatSync, mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";

const repository = resolve(import.meta.dirname, "../..");
const plugin = join(repository, "plugins-official", "torch-compile");
const cli = join(repository, "script", "bin", "cannbot.js");
const shared = join(repository, "vendor", "cannbot-skills");
const skillNames = [
  "torch-custom-ops-guide",
  "torch-npugraph-ex-compile-error-diagnosis",
  "torch-npugraph-ex-dfx-triage",
  "torch-npugraph-ex-knowledge",
  "torch-npugraph-ex-performance-diagnosis",
  "torch-npugraph-ex-runtime-error-diagnosis",
  "torch-npugraph-ex-template",
];

function sandbox(t) {
  const root = mkdtempSync(join(tmpdir(), "cannbot-torch-compile-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  return root;
}

function runHook(root, env = {}) {
  const result = spawnSync("bash", [join(root, "hooks", "session-start-torch")], {
    encoding: "utf8",
    env: { ...process.env, ...env, CLAUDE_PLUGIN_ROOT: root },
  });
  assert.equal(result.status, 0, result.stderr);
  return JSON.parse(result.stdout).hookSpecificOutput.additionalContext;
}

for (const source of ["repository", "package"]) {
  for (const tool of ["opencode", "codex", "claude", "trae", "dsh", "codearts"]) {
    test(`torch-compile ${source} installation for ${tool} retains all seven shared Skills and its Agent`, (t) => {
      const root = sandbox(t);
      const target = join(root, "project with spaces");
      mkdirSync(target);
      const instructions = join(target, tool === "claude" ? "CLAUDE.md" : "AGENTS.md");
      writeFileSync(instructions, "# Existing project instructions\n");
      const args = [cli, "install", "torch-compile", "--tool", tool, "--target", target];
      if (source === "repository") args.push("--source", repository, "--skills", shared);
      const options = {
        cwd: root,
        encoding: "utf8",
        env: {
          ...process.env,
          HOME: join(root, "home"),
          XDG_CACHE_HOME: join(root, "cache"),
          CANNBOT_SKIP_DEPENDENCY_REPOS: "1",
          CANNBOT_SKIP_CODEX_PLUGIN_ADD: "1",
          CANNBOT_SKIP_OPENCODE_PLUGIN_ADD: "1",
        },
      };
      const first = spawnSync(process.execPath, args, options);
      assert.equal(first.status, 0, first.stderr || first.stdout);
      const config = join(target, tool === "codearts" ? ".codeartsdoer" : `.${tool}`);
      const registryPath = join(config, "cannbot-plugin.json");
      const record = JSON.parse(readFileSync(registryPath)).plugins.find((item) => item.plugin === "torch-compile");
      assert.equal(record.skills.length, 7);
      assert.equal(record.agents.length, 1);
      assert.equal(record.skillInstallMode, source === "repository" ? "symlink" : "copy");
      assert.deepEqual(record.skills.map((path) => path.split("/").at(-1)).sort(), skillNames);
      for (const path of record.skills) {
        const installed = join(target, path);
        const name = path.split("/").at(-1);
        assert.equal(lstatSync(installed).isSymbolicLink(), source === "repository");
        const original = join(shared, "graph", name);
        assert.equal(readFileSync(join(installed, "SKILL.md"), "utf8"), readFileSync(join(original, "SKILL.md"), "utf8"));
        if (source === "repository") assert.equal(realpathSync(installed), realpathSync(original));
      }
      assert.match(readFileSync(instructions, "utf8"), /Existing project instructions/);
      assert.match(readFileSync(instructions, "utf8"), /Torch Compile 图模式编排 Agent/);
      const agent = readFileSync(join(target, record.agents[0]), "utf8");
      assert.match(agent, /torch-npugraph-ex/);
      assert.match(agent, /torch-custom-ops-guide/);
      assert.doesNotMatch(agent, /__CANNBOT_AGENT_SOURCE__/);
      if (tool === "codex") assert.match(record.agents[0], /\.codex\/agents\/torch-npugraph-ex\.toml$/);
      if (tool === "claude") {
        const settings = JSON.parse(readFileSync(join(config, "settings.json")));
        assert.match(settings.hooks.SessionStart[0].hooks[0].command, /session-start-torch/);
        const assets = join(target, record.assets);
        assert.equal(existsSync(join(assets, "AGENTS.md")), false);
        const context = runHook(assets);
        assert.ok(context.includes(join(target, ".claude", "skills")));
        assert.ok(context.includes(join(assets, "agents")));
        const hook = spawnSync("bash", ["-c", settings.hooks.SessionStart[0].hooks[0].command], {
          cwd: target,
          encoding: "utf8",
          env: { ...options.env, CLAUDE_PLUGIN_ROOT: "", CLAUDE_PROJECT_DIR: target },
        });
        assert.equal(hook.status, 0, hook.stderr);
        const installedContext = JSON.parse(hook.stdout).hookSpecificOutput.additionalContext;
        assert.ok(installedContext.includes(join(target, ".claude", "skills")));
      }
      const second = spawnSync(process.execPath, args, options);
      assert.equal(second.status, 0, second.stderr || second.stdout);
      assert.equal(JSON.parse(readFileSync(registryPath)).plugins.filter((item) => item.plugin === "torch-compile").length, 1);
      assert.equal((readFileSync(instructions, "utf8").match(/# Existing project instructions/g) ?? []).length, 1);
    });
  }
}

test("torch-compile source init resolves shared Skills from another working directory", (t) => {
  const root = sandbox(t);
  const target = join(root, "project");
  const result = spawnSync("bash", [join(plugin, "init.sh"), "project", "opencode", target, "--skills", shared], {
    cwd: root,
    encoding: "utf8",
    env: { ...process.env, HOME: join(root, "home"), CANNBOT_SKIP_OPENCODE_PLUGIN_ADD: "1" },
  });
  assert.equal(result.status, 0, result.stderr || result.stdout);
  assert.equal(realpathSync(join(target, ".agents", "skills", "torch-npugraph-ex-knowledge")), realpathSync(join(shared, "graph", "torch-npugraph-ex-knowledge")));
});

test("torch-compile source Hook resolves vendored graph Skills and exports their actual paths", (t) => {
  const envFile = join(sandbox(t), "claude-env.sh");
  const context = runHook(plugin, { CLAUDE_ENV_FILE: envFile });
  assert.ok(context.includes(join(shared, "graph")));
  assert.match(context, /Torch Compile 图模式编排 Agent/);
  assert.match(readFileSync(envFile, "utf8"), /export GRAPH_SKILLS_DIR=/);
});

test("torch-compile package Hook resolves its bundled Skills", () => {
  const packaged = join(repository, "script", "dist", "plugins", "torch-compile");
  const context = runHook(packaged);
  assert.ok(context.includes(join(packaged, "skills")));
});

test("torch-compile native marketplace Hook resolves the adjacent shared Skill pack", (t) => {
  const cache = join(sandbox(t), "cache", "cannbot");
  const native = join(cache, "torch-compile", "1.0.4");
  cpSync(plugin, native, { recursive: true });
  const pack = join(cache, "torch-npugraph-ex-skills", "1.0.0");
  mkdirSync(join(pack, "torch-npugraph-ex-knowledge"), { recursive: true });
  writeFileSync(join(pack, "torch-npugraph-ex-knowledge", "SKILL.md"), "# Skill pack fixture\n");
  const context = runHook(native);
  assert.ok(context.includes(pack));
});

test("torch-compile marketplace uses cannbot for orchestration and cannbot-skills for shared Skills", () => {
  const marketplace = JSON.parse(readFileSync(join(repository, ".claude-plugin", "marketplace.json")));
  const entry = marketplace.plugins.find((item) => item.name === "torch-compile");
  assert.equal(entry.source, "./plugins-official/torch-compile");
  assert.deepEqual(entry.dependencies, ["torch-npugraph-ex-skills"]);
  const pack = marketplace.plugins.find((item) => item.name === "torch-npugraph-ex-skills");
  assert.equal(pack.source.url, "https://gitcode.com/cann/cannbot-skills.git");
  assert.equal(pack.source.path, "graph");
  assert.deepEqual(pack.skills.map((path) => path.slice(2)).sort(), skillNames);
});
