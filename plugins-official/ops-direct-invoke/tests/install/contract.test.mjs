// Copyright (c) 2026 CANNBot contributors
// SPDX-License-Identifier: MIT

import assert from "node:assert/strict";
import { existsSync, lstatSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, readlinkSync, realpathSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { isAbsolute, delimiter, dirname, join, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";
import { pathToFileURL } from "node:url";
import { assemblePlugins, pluginSourceDefinition } from "../../../../script/lib/plugin-bundle.js";
import { isInside } from "../../../../script/lib/skills-source.js";

const repositoryRoot = resolve(import.meta.dirname, "../../../..");
const packageRoot = join(repositoryRoot, "script");
const cli = join(packageRoot, "bin", "cannbot.js");
const installerPackage = JSON.parse(readFileSync(join(packageRoot, "package.json"), "utf8"));
const sourcePackage = `${installerPackage.name}@${installerPackage.version}`;
const tools = ["opencode", "codex", "claude", "trae", "dsh", "codearts"];
const sources = ["repository", "package"];
process.env.CANNBOT_SKIP_DEPENDENCY_REPOS = "1";
process.env.CANNBOT_SKIP_OPMODEL_INSTALL = "1";
const temporarySandboxes = new Set();

test.afterEach(() => {
  for (const sandbox of temporarySandboxes) {
    rmSync(sandbox, { recursive: true, force: true });
  }
  temporarySandboxes.clear();
});

function createSandbox(prefix) {
  const sandbox = mkdtempSync(join(tmpdir(), prefix));
  temporarySandboxes.add(sandbox);
  return sandbox;
}

function configRoot(target, tool) {
  return join(target, tool === "codearts" ? ".codeartsdoer" : `.${tool}`);
}

function skillRoot(target, tool) {
  return tool === "codex" || tool === "opencode"
    ? join(target, ".agents", "skills")
    : join(configRoot(target, tool), "skills");
}

function directInitConfig(plugin, sandbox) {
  if (plugin !== "ops-direct-invoke") return "";
  const path = join(sandbox, "init.json");
  writeFileSync(path, JSON.stringify({ repo: "cannbench", platform: "ascend", chip: "Ascend950",
    preferences: { interaction: "confirm", autonomy: "仅已明确授权范围", review_points: [] } }));
  return path;
}

function installPlugin(plugin, tool, source = "repository", env = {}) {
  const sandbox = createSandbox(`cannbot-${source}-${plugin}-${tool}-`);
  const target = join(sandbox, "project");
  mkdirSync(target);
  const args = [
    cli,
    "install",
    plugin,
    "--tool",
    tool,
    "--target",
    target,
  ];
  if (source === "repository") {
    args.push("--source", repositoryRoot, "--skills", join(repositoryRoot, "vendor", "cannbot-skills"));
  }
  const result = spawnSync(process.execPath, args, {
    cwd: target,
    encoding: "utf8",
    env: {
      ...process.env,
      CANNBOT_DIRECT_INVOKE_CONFIG: directInitConfig(plugin, sandbox),
      HOME: join(sandbox, "home"),
      XDG_CACHE_HOME: join(sandbox, "cache"),
      CANNBOT_SKIP_CODEX_PLUGIN_ADD: "1",
      CANNBOT_SKIP_OPENCODE_PLUGIN_ADD: "1",
      ...env,
    },
  });
  assert.equal(result.status, 0, result.stderr || result.stdout);
  return { sandbox, target, result };
}

function installWithSourceInit(plugin, tool) {
  const sandbox = createSandbox(`cannbot-init-${plugin}-${tool}-`);
  const target = join(sandbox, "project");
  mkdirSync(target);
  const sourceDefinition = pluginSourceDefinition(repositoryRoot, plugin);
  const pluginRoot = sourceDefinition?.pluginRoot ?? join(repositoryRoot, "plugins-official", plugin);
  const init = join(pluginRoot, "init.sh");
  const sourceArgs = sourceDefinition?.skills.length ? ["--skills", join(repositoryRoot, "vendor", "cannbot-skills")] : [];
  const result = spawnSync("bash", [init, "project", tool, target, ...sourceArgs], {
    cwd: pluginRoot,
    encoding: "utf8",
    env: {
      ...process.env,
      CANNBOT_DIRECT_INVOKE_CONFIG: directInitConfig(plugin, sandbox),
      HOME: join(sandbox, "home"),
      XDG_CACHE_HOME: join(sandbox, "cache"),
      CANNBOT_SKIP_CODEX_PLUGIN_ADD: "1",
      CANNBOT_SKIP_OPENCODE_PLUGIN_ADD: "1",
      CANNBOT_SKIP_DEPENDENCY_REPOS: "1",
    },
  });
  assert.equal(result.status, 0, result.stderr || result.stdout);
  return { sandbox, target, result };
}

function readPluginRecord(target, tool, plugin) {
  const registry = JSON.parse(readFileSync(join(configRoot(target, tool), "cannbot-plugin.json"), "utf8"));
  assert.equal(registry.schemaVersion, 2);
  assert.equal(Array.isArray(registry.plugins), true);
  const record = registry.plugins.find((candidate) => candidate.plugin === plugin);
  assert.ok(record, `missing install record for ${plugin}`);
  return record;
}

function assertUnifiedInstall(target, tool, plugin) {
  const root = configRoot(target, tool);
  assert.equal(existsSync(join(root, "cannbot-manifest.json")), false);
  const instructionsPath = join(target, tool === "claude" ? "CLAUDE.md" : "AGENTS.md");
  if (existsSync(instructionsPath)) {
    const instructions = readFileSync(instructionsPath, "utf8");
    const expected = plugin === "ops-direct-invoke" ? undefined : 1;
    assert.equal(instructions.match(new RegExp(`<!-- cannbot:${plugin}:start -->`, "g"))?.length, expected);
    if (plugin === "ops-direct-invoke") assert.doesNotMatch(instructions, /<!-- cannbot:ops-perf-optimize:start -->/);
  }
}

for (const source of sources) {
  for (const tool of tools) {
    test(`${source} installs ops-direct-invoke for ${tool}`, () => {
      const { sandbox, target } = installPlugin("ops-direct-invoke", tool, source);
      const root = configRoot(target, tool);
      const config = JSON.parse(readFileSync(join(target, ".cannbot/ops-direct-invoke.json"), "utf8"));
      const names = ["ops-direct-invoke", "ops-direct-invoke-maintain", "ops-direct-invoke-requirement", "ops-direct-invoke-repo-guide"];
      assert.deepEqual(readdirSync(skillRoot(target, tool)).sort(), names.sort());
      for (const name of names) {
        assert.ok(existsSync(join(skillRoot(target, tool), name, "SKILL.md")));
        assert.ok(realpathSync(join(skillRoot(target, tool), name)).startsWith(realpathSync(config.asset_root) + "/") || source === "repository");
      }
      for (const name of ["ascendc-env-check", "workflow-orchestrator", "cannbot-dsl-best-practice", "ops-design-paradigms"]) {
        assert.ok(existsSync(join(config.external_skills_root, name, "SKILL.md")), name);
      }
      assert.ok(existsSync(join(config.asset_root, "tools/assemble_workflow.py")));
      assert.ok(existsSync(join(config.asset_root, "skills/custom-skills/requirement/kirin/SKILL.md")));
      const performance = readPluginRecord(config.performance_root, tool, "ops-perf-optimize");
      assert.ok(performance.skills.some((path) => path.endsWith("/ops-perf-optimize-workflow")));
      for (const path of performance.skills) assert.ok(existsSync(join(config.performance_root, path, "SKILL.md")), path);
      const performanceAssets = join(config.performance_root, ".cannbot/plugins/ops-perf-optimize");
      assert.ok(existsSync(join(performanceAssets, "AGENTS.md")));
      assert.ok(existsSync(join(performanceAssets, "skills/ops-perf-optimize-workflow/SKILL.md")));
      if (tool === "claude") {
        const hook = spawnSync("bash", [join(performanceAssets, "hooks/session-start-ops-perf-optimize")], {
          encoding: "utf8", env: { ...process.env, CLAUDE_PLUGIN_ROOT: performanceAssets },
        });
        assert.equal(hook.status, 0, hook.stderr);
        assert.match(JSON.parse(hook.stdout).hookSpecificOutput.additionalContext, /ops-perf-optimize-workflow\/SKILL.md/);
      }
      const record = readPluginRecord(target, tool, "ops-direct-invoke");
      assert.equal(record.skills.length, 4);
      assert.deepEqual(record.agents, []);
      assert.equal(record.sourcePackage, sourcePackage);
      assert.equal(record.source.kind, source);
      assert.equal(record.skillInstallMode, "symlink");
      assertUnifiedInstall(target, tool, "ops-direct-invoke");
      assert.equal(existsSync(join(sandbox, "home/plugins/ops-direct-invoke")), false);
      assert.equal(existsSync(join(sandbox, "home/plugins/ops-perf-optimize")), false);
    });
  }
}

test("ops-direct-invoke source init uses the unified installer", () => {
  const { target } = installWithSourceInit("ops-direct-invoke", "opencode");
  const root = configRoot(target, "opencode");
  assertUnifiedInstall(target, "opencode", "ops-direct-invoke");
  assert.equal(existsSync(join(target, ".cannbot", "permissions", "PM.js")), false);
  assert.equal(existsSync(join(skillRoot(target, "opencode"), "ops-direct-invoke", "SKILL.md")), true);
  assert.equal(existsSync(join(target, ".cannbot/plugins/ops-direct-invoke/agents/ops-direct-invoke-verifier.md")), true);
});

test("multiple plugins keep independent instructions and install records", () => {
  const first = installPlugin("ops-direct-invoke", "dsh", "package");
  const result = spawnSync(process.execPath, [
    cli,
    "install",
    "model-infer-optimize",
    "--tool",
    "dsh",
    "--target",
    first.target,
  ], {
    cwd: first.target,
    encoding: "utf8",
    env: {
      ...process.env,
      HOME: join(first.sandbox, "home"),
      XDG_CACHE_HOME: join(first.sandbox, "cache"),
      CANNBOT_SKIP_DEPENDENCY_REPOS: "1",
    },
  });
  assert.equal(result.status, 0, result.stderr || result.stdout);

  const instructions = readFileSync(join(first.target, "AGENTS.md"), "utf8");
  assert.doesNotMatch(instructions, /<!-- cannbot:ops-direct-invoke:start -->/);
  assert.equal(instructions.match(/<!-- cannbot:model-infer-optimize:start -->/g)?.length, 1);
  assert.match(instructions, /^# NPU 模型推理优化入口$/m);

  const registry = JSON.parse(readFileSync(join(first.target, ".dsh", "cannbot-plugin.json"), "utf8"));
  assert.equal(registry.schemaVersion, 2);
  assert.deepEqual(registry.plugins.map((plugin) => plugin.plugin), ["model-infer-optimize", "ops-direct-invoke"]);
  assert.equal(registry.plugins.find((plugin) => plugin.plugin === "ops-direct-invoke").instructions, null);
  assert.equal(existsSync(join(skillRoot(first.target, "dsh"), "ops-direct-invoke-requirement", "SKILL.md")), true);
  assert.equal(existsSync(join(skillRoot(first.target, "dsh"), "model-infer-migrator", "SKILL.md")), true);
});
