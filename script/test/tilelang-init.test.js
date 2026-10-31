// Copyright (c) 2026 CANNBot contributors
// SPDX-License-Identifier: MIT
// See script/LICENSE for the full license text.

import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { cpSync, existsSync, lstatSync, mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { basename, dirname, join, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";

const repositoryRoot = resolve(import.meta.dirname, "../..");
const pluginId = "tilelang-op-orchestrator";
const original = JSON.parse(readFileSync(join(import.meta.dirname, "fixtures", "tilelang-original-files.json"), "utf8"));
const runtimeNames = [".agents", ".cannbot", ".opencode", ".codex", ".claude", ".trae", ".dsh", "CLAUDE.md"];
const sourcePlugin = join(repositoryRoot, "plugins-official", pluginId);
const tools = ["opencode", "codex", "claude", "trae", "dsh"];

function sandbox(t) {
  const root = mkdtempSync(join(tmpdir(), "tilelang-install-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const env = { ...process.env, HOME: join(root, "home"), XDG_CACHE_HOME: join(root, "cache") };
  return { root, env };
}

function assertOriginalFiles(plugin) {
  for (const [file, expected] of Object.entries(original.files)) {
    const actual = createHash("sha256").update(readFileSync(join(plugin, file))).digest("hex");
    assert.equal(actual, original.reviewedFixes?.[file]?.sha256 ?? expected, file);
  }
  assert.equal(existsSync(join(plugin, "skills", pluginId)), false);
  assert.equal(existsSync(join(plugin, "platforms")), false);
  assert.equal(existsSync(join(plugin, "scripts", "route_tilelang.py")), false);
}

function assertInstalled(target, tool, plugin) {
  const config = join(target, `.${tool}`);
  const registry = JSON.parse(readFileSync(join(config, "cannbot-plugin.json"), "utf8"));
  const record = registry.plugins.find((entry) => entry.plugin === pluginId);
  assert.equal(record.skills.length, 13);
  assert.equal(record.agents.length, 6);
  for (const skill of record.skills) {
    assert.ok(lstatSync(resolve(target, skill)).isSymbolicLink(), skill);
    assert.ok(existsSync(join(target, skill, "SKILL.md")), skill);
  }
  for (const agent of record.agents) {
    const installed = resolve(target, agent);
    assert.ok(existsSync(installed), agent);
    if (tool === "codex") {
      const canonical = resolve(dirname(realpathSync(installed)), "..", `${basename(agent, ".toml")}.md`);
      assert.ok(existsSync(canonical), canonical);
    } else {
      assert.equal(realpathSync(installed), realpathSync(join(plugin, "agents", basename(agent))));
    }
  }
  assert.ok(existsSync(join(target, tool === "claude" ? "CLAUDE.md" : "AGENTS.md")));
  assert.equal(record.skills.some((path) => basename(path) === pluginId), false);
  assertApiReferences(target, plugin, record);
}

function assertApiReferences(target, plugin, record) {
  const workflow = readFileSync(join(plugin, "workflows", "Ascend910", "workflow.md"), "utf8");
  const section = workflow.split("### API 参考\n")[1].split("\n### 开发规范")[0];
  assert.ok(section.includes("tilelang-api-best-practices"));
  assert.match(section, /Skill 的真实目录/);
  assert.equal(section.includes("../../../../ops/"), false);
  const resources = [...section.matchAll(/`(Ascend910\/references\/[^`]+\.md)`/g)].map((match) => match[1]);
  assert.deepEqual(resources, [
    "Ascend910/references/api-kernel-memory.md",
    "Ascend910/references/api-compute.md",
    "Ascend910/references/api-schedule-sync.md",
  ]);
  const installed = record.skills.find((path) => basename(path) === "tilelang-api-best-practices");
  assert.ok(installed, "API Skill is missing from the installation registry");
  const skillRoot = realpathSync(resolve(target, installed));
  for (const resource of resources) {
    assert.ok(existsSync(join(skillRoot, resource)), `installed API resource is missing: ${resource}`);
    assert.ok(readFileSync(join(skillRoot, resource), "utf8").trim());
  }
}

function assertHook(target, plugin, env) {
  const settings = JSON.parse(readFileSync(join(target, ".claude", "settings.json"), "utf8"));
  assert.equal(settings.hooks.SessionStart.length, 1);
  const result = spawnSync("bash", ["-c", settings.hooks.SessionStart[0].hooks[0].command], {
    cwd: target, env, encoding: "utf8",
  });
  assert.equal(result.status, 0, result.stderr);
  const output = JSON.parse(result.stdout).hookSpecificOutput;
  assert.equal(output.hookEventName, "SessionStart");
  assert.ok(output.additionalContext.includes(join(plugin, "workflows", "Ascend910", "workflow.md")));
  assert.ok(output.additionalContext.includes(join(plugin, "workflows", "Ascend950", "workflow.md")));
}

test("TileLang migration preserves original workflow files without a duplicate routing script", () => {
  assertOriginalFiles(sourcePlugin);
});

for (const tool of tools) {
  test(`TileLang default ${tool} installation preserves original files across repeated installs`, (t) => {
    const { root, env } = sandbox(t);
    const repository = join(root, "repository with spaces");
    const plugin = join(repository, "plugins-official", pluginId);
    cpSync(sourcePlugin, plugin, { recursive: true, filter: (path) => !runtimeNames.includes(basename(path)) });
    for (const path of ["script/bin", "script/lib", "script/package.json"]) {
      cpSync(join(repositoryRoot, path), join(repository, path), { recursive: true });
    }
    const args = tool === "opencode" ? [] : ["project", tool];
    args.push("--skills", join(repositoryRoot, "vendor", "cannbot-skills"));
    for (const cwd of [repository, root]) {
      const result = spawnSync("bash", [join(plugin, "init.sh"), ...args], { cwd, env, encoding: "utf8" });
      assert.equal(result.status, 0, result.stderr || result.stdout);
      assertOriginalFiles(plugin);
      assertInstalled(plugin, tool, plugin);
      for (const parent of [repository, root]) {
        for (const name of [...runtimeNames, "AGENTS.md"]) assert.equal(existsSync(join(parent, name)), false, name);
      }
      if (tool === "claude") assertHook(plugin, plugin, env);
    }
  });
}

for (const source of ["repository", "package"]) {
  for (const tool of tools) {
    test(`TileLang ${source} CLI installation retains the original workflow and role layout for ${tool}`, (t) => {
      const { root, env } = sandbox(t);
      const target = join(root, "project with spaces");
      const args = [join(repositoryRoot, "script", "bin", "cannbot.js"), "install", pluginId, "--tool", tool, "--target", target];
      if (source === "repository") args.push("--source", repositoryRoot, "--skills", join(repositoryRoot, "vendor", "cannbot-skills"));
      const plugin = source === "repository" ? sourcePlugin : join(repositoryRoot, "script", "dist", "plugins", pluginId);
      const result = spawnSync(process.execPath, args, { env, encoding: "utf8" });
      assert.equal(result.status, 0, result.stderr || result.stdout);
      assertOriginalFiles(plugin);
      assertInstalled(target, tool, plugin);
      if (tool === "claude") assertHook(target, plugin, env);
    });
  }
}

test("TileLang help and invalid shared source do not modify its original entry", (t) => {
  const { root, env } = sandbox(t);
  const entry = readFileSync(join(sourcePlugin, "AGENTS.md"), "utf8");
  const help = spawnSync("bash", [join(sourcePlugin, "init.sh"), "--help"], { cwd: root, env, encoding: "utf8" });
  assert.equal(help.status, 0, help.stderr);
  assert.match(help.stdout, /default: this TileLang plugin directory/);
  const invalid = spawnSync("bash", [join(sourcePlugin, "init.sh"), "project", "codex", join(root, "target"), "--skills", join(root, "missing")], {
    env, encoding: "utf8",
  });
  assert.notEqual(invalid.status, 0);
  assert.equal(readFileSync(join(sourcePlugin, "AGENTS.md"), "utf8"), entry);
});
