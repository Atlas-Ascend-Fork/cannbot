// Copyright (c) 2026 CANNBot contributors
// SPDX-License-Identifier: MIT
// See script/LICENSE for the full license text.

import assert from "node:assert/strict";
import { existsSync, lstatSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, readlinkSync, realpathSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { isAbsolute, dirname, join, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";
import { assemblePlugins, pluginSourceDefinition } from "../lib/plugin-bundle.js";

const packageRoot = resolve(import.meta.dirname, "..");
const repositoryRoot = resolve(packageRoot, "..");
const cli = join(packageRoot, "bin", "cannbot.js");
const installerPackage = JSON.parse(readFileSync(join(packageRoot, "package.json"), "utf8"));
const sourcePackage = `${installerPackage.name}@${installerPackage.version}`;
const tools = ["opencode", "codex", "claude", "trae", "dsh"];
const sources = ["repository", "package"];
process.env.CANNBOT_SKIP_DEPENDENCY_REPOS = "1";
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

test("model-train-precision-diagnose resolves its community Skill sources", () => {
  const definition = pluginSourceDefinition(repositoryRoot, "model-train-precision-diagnose");
  assert.equal(
    definition.pluginRoot,
    join(repositoryRoot, "plugins-community", "model-train-precision-diagnose"),
  );
  assert.deepEqual(definition.skills, [
    "model/model-train-precision-numerical-mismatch",
    "model/model-train-precision-nonfinite",
    "model/model-train-precision-determinism",
    "model/model-train-log-visualization",
  ]);
});

function configRoot(target, tool) {
  return join(target, tool === "opencode" ? ".opencode" : `.${tool}`);
}

function skillRoot(target, tool) {
  return tool === "codex" || tool === "opencode"
    ? join(target, ".agents", "skills")
    : join(configRoot(target, tool), "skills");
}

function assertSkillInstallation(installedSkill, source, plugin, skill, pluginRoot = "plugins") {
  const shouldLink = source === "repository";
  assert.equal(lstatSync(installedSkill).isSymbolicLink(), shouldLink);
  if (!shouldLink) return;
  assert.equal(isAbsolute(readlinkSync(installedSkill)), false);
  const definition = pluginSourceDefinition(repositoryRoot, plugin);
  assert.ok(definition, `missing source definition for ${plugin}`);
  const relativeSkill = definition.skills.find((candidate) => candidate.split("/").at(-1) === skill);
  assert.ok(relativeSkill, `missing source mapping for ${plugin}/${skill}`);
  assert.equal(
    realpathSync(installedSkill),
    realpathSync(join(repositoryRoot, definition.skillsRepository, relativeSkill)),
  );
}

function installPlugin(plugin, tool, source = "repository") {
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
      HOME: join(sandbox, "home"),
      XDG_CACHE_HOME: join(sandbox, "cache"),
      CANNBOT_SKIP_CODEX_PLUGIN_ADD: "1",
      CANNBOT_SKIP_OPENCODE_PLUGIN_ADD: "1",
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

for (const tool of tools) {
  test(`ascendc-port-orchestrator source install exposes the renamed migration Skill for ${tool}`, () => {
    const { target } = installPlugin("ascendc-port-orchestrator", tool);
    const installed = join(skillRoot(target, tool), "ascendc-cross-gen-migration");
    assert.equal(realpathSync(installed), realpathSync(join(
      repositoryRoot, "vendor", "cannbot-skills", "ops", "ascendc-cross-gen-migration",
    )));
    assert.match(readFileSync(join(installed, "SKILL.md"), "utf8"), /^name: ascendc-cross-gen-migration$/m);
    assert.equal(existsSync(join(skillRoot(target, tool), "ascendc-cross-gen-port-light")), false);
  });
}

test("ascendc-port-orchestrator bundles the renamed migration Skill and its route assets", () => {
  const sandbox = createSandbox("cannbot-migration-bundle-");
  assemblePlugins(repositoryRoot, sandbox, ["ascendc-port-orchestrator"]);
  const plugin = join(sandbox, "plugins", "ascendc-port-orchestrator");
  const manifest = JSON.parse(readFileSync(join(plugin, ".claude-plugin", "plugin.json"), "utf8"));
  assert.ok(manifest.skills.includes("./skills/ascendc-cross-gen-migration"));
  assert.equal(manifest.skills.includes("./skills/ascendc-cross-gen-port-light"), false);
  const skill = join(plugin, "skills", "ascendc-cross-gen-migration");
  assert.match(readFileSync(join(skill, "SKILL.md"), "utf8"), /^name: ascendc-cross-gen-migration$/m);
  assert.ok(existsSync(join(skill, "routes", "2201-to-3510", "stages", "stage_0_env.md")));
});

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
    assert.equal(instructions.match(new RegExp(`<!-- cannbot:${plugin}:start -->`, "g"))?.length, 1);
  }
}

test("repository maps every official plugin to the Skill submodule", () => {
  for (const plugin of ["ops-direct-invoke", "model-infer-optimize"]) {
    const root = join(repositoryRoot, "plugins-official", plugin);
    assert.equal(existsSync(join(root, ".claude-plugin", "plugin.json")), true);
    assert.equal(existsSync(join(root, ".codex-plugin", "plugin.json")), true);
    assert.equal(existsSync(join(root, "plugin-sources.json")), true);
    if (plugin !== "ops-direct-invoke") {
      assert.equal(existsSync(join(root, "skills")), false);
    }
    const sourceDefinition = JSON.parse(readFileSync(join(root, "plugin-sources.json"), "utf8"));
    assert.equal(sourceDefinition.skillInstallMode, "symlink");
    const quickstartPath = join(root, "quickstart.md");
    if (existsSync(quickstartPath)) {
      const quickstart = readFileSync(quickstartPath, "utf8");
      assert.doesNotMatch(quickstart, /cann\.cannbot\.cn/);
      assert.doesNotMatch(quickstart, /默认安装到当前目录并使用 OpenCode/);
      assert.match(quickstart, /git clone --recurse-submodules/);
    }
    const codexManifest = JSON.parse(readFileSync(join(root, ".codex-plugin", "plugin.json"), "utf8"));
    assert.equal(codexManifest.homepage, "https://gitcode.com/cann/cannbot");
    assert.equal(codexManifest.repository, "https://gitcode.com/cann/cannbot");
    const trackedFiles = spawnSync("git", ["ls-files", "-s", `plugins-official/${plugin}`], {
      cwd: repositoryRoot,
      encoding: "utf8",
    });
    assert.equal(trackedFiles.status, 0, trackedFiles.stderr);
    assert.equal(trackedFiles.stdout.split("\n").some((line) => line.startsWith("120000 ")), false);
  }
  // ops-direct-invoke ships self-contained workflow skills in plugins-official/<id>/skills/;
  // the other two plugins resolve all skills from the submodule only.
  assert.equal(existsSync(join(repositoryRoot, "plugins-official", "ops-direct-invoke", "skills")), true);
  assert.equal(existsSync(join(repositoryRoot, "plugins-official", "model-infer-optimize", "skills")), false);
  assert.equal(existsSync(join(repositoryRoot, "vendor", "cannbot-skills", ".git")), true);
  for (const removed of ["catalog", "ops", "infra", "model", "plugins"]) {
    assert.equal(existsSync(join(repositoryRoot, removed)), false, `${removed} should not exist at repository root`);
  }
});

test("Claude marketplace matches the bundled official plugin manifests", () => {
  const marketplace = JSON.parse(readFileSync(join(repositoryRoot, ".claude-plugin", "marketplace.json"), "utf8"));
  const entries = new Map(marketplace.plugins.map((plugin) => [plugin.name, plugin]));
  const submodule = readFileSync(join(repositoryRoot, ".gitmodules"), "utf8");
  const skillSourceUrl = submodule.match(/url = (https:\/\/[^\s]+cannbot-skills[^\s]*)/)?.[1];
  // Marketplace entries pin the main repository's Gitlink, independently of
  // the mutable shared checkout used by source installs.
  const revision = spawnSync("git", ["ls-tree", "HEAD", "vendor/cannbot-skills"], {
    cwd: repositoryRoot,
    encoding: "utf8",
  });
  assert.equal(revision.status, 0, revision.stderr);
  const skillCommit = revision.stdout.match(/commit ([0-9a-f]+)\t/)?.[1];
  assert.ok(skillSourceUrl, "missing Skill submodule URL");
  assert.match(skillCommit, /^[0-9a-f]{40}$/);
  const expectedPlugins = ["catlass-op-generator", "hccl-op-generator", "model-infer-optimize", "ops-direct-invoke", "ops-perf-optimize", "triton-op-generator"];
  // Only bundled plugins have manifests; source-only workflow entries are not packaged.
  // A community plugin is bundled under its directory name, which need not match its
  // manifest name, so only official-directory entries belong to this official list;
  // community entries are validated by the dedicated loop below.
  const officialPlugins = marketplace.plugins.filter((plugin) =>
    typeof plugin.source === "string" && plugin.source.startsWith("./plugins-official/")
    && existsSync(join(packageRoot, "dist", "plugins", plugin.name)));
  for (const plugin of marketplace.plugins.filter((entry) => typeof entry.source === "string")) {
    assert.ok(existsSync(resolve(repositoryRoot, plugin.source)), plugin.source);
  }
  assert.deepEqual(officialPlugins.map((plugin) => plugin.name).sort(), expectedPlugins);
  assert.equal(entries.has("model-train-precision-diagnose"), false);
  // A community plugin is indexed by its manifest name, so its directory name may differ;
  // the manifest at the declared source path is what has to agree with the entry.
  for (const plugin of marketplace.plugins.filter(
    (entry) => typeof entry.source === "string" && entry.source.startsWith("./plugins-community/"),
  )) {
    const manifest = JSON.parse(readFileSync(
      join(repositoryRoot, plugin.source, ".claude-plugin", "plugin.json"),
      "utf8",
    ));
    assert.equal(manifest.name, plugin.name);
    assert.equal(plugin.version, manifest.version);
  }
  assert.equal(marketplace.owner.url, "https://gitcode.com/cann/cannbot");
  for (const plugin of officialPlugins) {
    assert.equal(plugin.source, `./plugins-official/${plugin.name}`);
    const manifest = JSON.parse(readFileSync(
      join(repositoryRoot, "plugins-official", plugin.name, ".claude-plugin", "plugin.json"),
      "utf8",
    ));
    assert.equal(plugin.version, manifest.version);
    assert.equal(plugin.description, manifest.description);
    assert.deepEqual(plugin.dependencies, manifest.dependencies);
    assert.equal(manifest.homepage, "https://gitcode.com/cann/cannbot");
    assert.equal(manifest.repository, "https://gitcode.com/cann/cannbot");
    assert.equal(manifest.skills, undefined);

    const sourceDefinition = JSON.parse(readFileSync(
      join(repositoryRoot, "plugins-official", plugin.name, "plugin-sources.json"),
      "utf8",
    ));
    const marketplaceSkills = (manifest.dependencies ?? []).flatMap((dependency) => {
      const entry = entries.get(dependency);
      assert.equal(entry.category, "skills");
      assert.equal(entry.strict, false);
      assert.equal(entry.source.source, "git-subdir");
      assert.equal(entry.source.url, skillSourceUrl);
      assert.equal(entry.source.sha, skillCommit);
      return entry.skills.map((skill) => `${entry.source.path}/${skill.replace(/^\.\//, "")}`);
    });
    if (manifest.dependencies) {
      assert.deepEqual(marketplaceSkills.sort(), sourceDefinition.skills.sort());
    } else {
      assert.equal(sourceDefinition.skillsRepository, '.');
      for (const skill of sourceDefinition.skills) {
        assert.ok(existsSync(join(repositoryRoot, skill, 'SKILL.md')), skill);
      }
    }

    const bundledManifest = JSON.parse(readFileSync(
      join(packageRoot, "dist", "plugins", plugin.name, ".claude-plugin", "plugin.json"),
      "utf8",
    ));
    assert.equal(bundledManifest.dependencies, undefined);
    // The bundled manifest lists the union of submodule skills (plugin-sources.json)
    // and any self-contained skills shipped inside the plugin (plugins-official/<id>/skills/).
    const bundledSkills = bundledManifest.skills.map((skill) => skill.replace(/^\.\/skills\//, "")).sort();
    const submoduleSkills = sourceDefinition.skills.map((skill) => skill.split("/").at(-1)).sort();
    const selfContainedSkills = [];
    const selfContainedRoot = join(repositoryRoot, "plugins-official", plugin.name, "skills");
    if (existsSync(selfContainedRoot)) {
      for (const entry of readdirSync(selfContainedRoot)) {
        if (existsSync(join(selfContainedRoot, entry, "SKILL.md"))) selfContainedSkills.push(entry);
      }
    }
    assert.deepEqual(bundledSkills, [...submoduleSkills, ...selfContainedSkills].sort());
  }
});

test("package bundle includes plugin licenses", () => {
  assert.equal(
    readFileSync(join(packageRoot, "dist", "plugins", "LICENSE"), "utf8"),
    readFileSync(join(repositoryRoot, "plugins-official", "LICENSE"), "utf8"),
  );
  for (const plugin of ["model-infer-optimize", "ops-direct-invoke", "ops-perf-optimize", "triton-op-generator"]) {
    assert.equal(
      readFileSync(join(packageRoot, "dist", "plugins", plugin, "LICENSE"), "utf8"),
      readFileSync(join(repositoryRoot, "plugins-official", "LICENSE"), "utf8"),
    );
    const source = JSON.parse(readFileSync(
      join(repositoryRoot, "plugins-official", plugin, "plugin-sources.json"), "utf8"));
    assert.equal(
      readFileSync(join(packageRoot, "dist", "plugins", plugin, "SKILLS_LICENSE"), "utf8"),
      readFileSync(join(repositoryRoot, source.skillsRepository, "LICENSE"), "utf8"),
    );
  }
  assert.equal(
    readFileSync(join(packageRoot, "dist", "plugins", "model-train-precision-diagnose", "LICENSE"), "utf8"),
    readFileSync(join(repositoryRoot, "plugins-community", "model-train-precision-diagnose", "LICENSE"), "utf8"),
  );
  assert.equal(
    readFileSync(join(packageRoot, "dist", "plugins", "model-train-precision-diagnose", "SKILLS_LICENSE"), "utf8"),
    readFileSync(join(repositoryRoot, "vendor", "cannbot-skills", "LICENSE"), "utf8"),
  );
});

for (const source of sources) {
  for (const tool of tools) {
    test(`${source} installs ops-direct-invoke for ${tool}`, () => {
      const { sandbox, target } = installPlugin("ops-direct-invoke", tool, source);
      const root = configRoot(target, tool);
      const agent = tool === "codex" ? "ops-direct-invoke-architect.toml" : "ops-direct-invoke-architect.md";
      const workflowScript = join(skillRoot(target, tool), "ops-direct-invoke", "scripts", "assemble_workflow.py");
      const installedSharedSkill = join(skillRoot(target, tool), "ascendc-env-check");
      assert.equal(existsSync(join(installedSharedSkill, "SKILL.md")), true);
      assertSkillInstallation(installedSharedSkill, source, "ops-direct-invoke", "ascendc-env-check");
      assert.equal(existsSync(join(skillRoot(target, tool), "workflow-orchestrator", "SKILL.md")), true);
      assert.equal(existsSync(join(skillRoot(target, tool), "ops-direct-invoke", "SKILL.md")), true);
      assert.equal(existsSync(join(root, "agents", agent)), true);
      assert.equal(existsSync(workflowScript), true);
      assert.equal(existsSync(join(target, ".cannbot", "permissions", "PM.js")), false);
      assert.equal(existsSync(join(target, ".cannbot", "settings.json")), false);
      const record = readPluginRecord(target, tool, "ops-direct-invoke");
      const configured = JSON.parse(readFileSync(join(repositoryRoot, "plugins-official", "ops-direct-invoke", "plugin-sources.json"), "utf8"));
      const localSkills = readdirSync(join(repositoryRoot, "plugins-official", "ops-direct-invoke", "skills"))
        .filter((name) => existsSync(join(repositoryRoot, "plugins-official", "ops-direct-invoke", "skills", name, "SKILL.md")));
      assert.equal(record.skills.length, configured.skills.length + localSkills.length);
      for (const name of ["cannbot-dsl-env-check", "cannbot-dsl-op-design", "cannbot-dsl-unit-planner", "cannbot-dsl-test-generator", "cannbot-dsl-best-practice", "cannbot-dsl-code-reviewer", "ops-design-paradigms"]) {
        const installedSkill = join(skillRoot(target, tool), name);
        assert.equal(existsSync(join(installedSkill, "SKILL.md")), true, name);
        assertSkillInstallation(installedSkill, source, "ops-direct-invoke", name);
      }
      assert.equal(record.agents.length, 3);
      assert.equal(record.sourcePackage, sourcePackage);
      assert.equal(record.source.kind, source);
      assert.equal(record.skillInstallMode, source === "repository" ? "symlink" : "copy");
      assertUnifiedInstall(target, tool, "ops-direct-invoke");
      if (tool === "codex") {
        assert.equal(existsSync(join(sandbox, "home", "plugins", "ops-direct-invoke", ".codex-plugin", "plugin.json")), true);
      }
    });
  }
}

for (const source of sources) {
  for (const tool of tools) {
    test(`${source} installs model-infer-optimize for ${tool}`, () => {
      const { target } = installPlugin("model-infer-optimize", tool, source);
      const root = configRoot(target, tool);
      const agent = tool === "codex" ? "model-infer-analyzer.toml" : "model-infer-analyzer.md";
      const workflow = join(target, ".cannbot", "plugins", "model-infer-optimize", "workflows");
      assert.equal(existsSync(join(skillRoot(target, tool), "model-infer-migrator", "SKILL.md")), true);
      assert.equal(existsSync(join(root, "agents", agent)), true);
      assert.equal(existsSync(join(workflow, "optimize-workflow.md")), true);
      const record = readPluginRecord(target, tool, "model-infer-optimize");
      assert.equal(record.skills.length, 14);
      assert.equal(record.agents.length, 9);
      assert.equal(record.sourcePackage, sourcePackage);
      assert.equal(record.source.kind, source);
      assert.equal(record.skillInstallMode, source === "repository" ? "symlink" : "copy");
      assertSkillInstallation(
        join(skillRoot(target, tool), "model-infer-migrator"),
        source,
        "model-infer-optimize",
        "model-infer-migrator",
      );
      assertUnifiedInstall(target, tool, "model-infer-optimize");
      if (tool === "claude") {
        assert.equal(existsSync(join(root, "settings.json")), true);
        assert.equal(existsSync(join(target, ".cannbot", "plugins", "model-infer-optimize", "hooks", "pre_tool_use.py")), true);
      }
    });
  }
}

const trainPrecisionSkills = [
  "model-train-precision-numerical-mismatch",
  "model-train-precision-nonfinite",
  "model-train-precision-determinism",
  "model-train-log-visualization",
];
const trainPrecisionAgents = [
  "model-train-precision-scope-reducer-agent",
  "model-train-precision-numerical-mismatch-agent",
  "model-train-precision-nonfinite-agent",
  "model-train-precision-determinism-agent",
  "model-train-precision-reviewer-agent",
];
const trainPrecisionReferences = [
  "cluster-execution-and-artifact-plane.md",
  "dump-integrity-and-compare-gate.md",
  "evidence-and-risk-policy.md",
  "intake-routing.md",
  "optional-hardware-and-silent-error-checks.md",
  "preflight-checklist.md",
  "record-templates.md",
  "reviewer-contract.md",
  "scope-reduction.md",
  "subagent-prompt-templates.md",
  "tool-semantics-and-version-probe.md",
];

for (const source of sources) {
  for (const tool of tools) {
    test(`${source} installs model-train-precision-diagnose for ${tool}`, () => {
      const plugin = "model-train-precision-diagnose";
      const { target } = installPlugin(plugin, tool, source);
      const root = configRoot(target, tool);
      const agentExtension = tool === "codex" ? ".toml" : ".md";
      const workflowRoot = join(target, ".cannbot", "plugins", plugin, "workflows");
      const installedReferencePrefix = `.cannbot/plugins/${plugin}/workflows/references/`;

      for (const skill of trainPrecisionSkills) {
        const installedSkill = join(skillRoot(target, tool), skill);
        assert.equal(existsSync(join(installedSkill, "SKILL.md")), true);
        assertSkillInstallation(installedSkill, source, plugin, skill);
      }
      for (const agent of trainPrecisionAgents) {
        const installedAgent = join(root, "agents", `${agent}${agentExtension}`);
        assert.equal(existsSync(installedAgent), true);
        const content = readFileSync(installedAgent, "utf8");
        assert.equal(content.includes(installedReferencePrefix), true);
        assert.doesNotMatch(content, /\.\.\/(?:\.cannbot|references|workflows)\//);
      }

      assert.equal(existsSync(join(workflowRoot, "precision-diagnose-workflow.md")), true);
      for (const reference of trainPrecisionReferences) {
        assert.equal(existsSync(join(workflowRoot, "references", reference)), true);
      }

      const instructionsPath = join(target, tool === "claude" ? "CLAUDE.md" : "AGENTS.md");
      const instructions = readFileSync(instructionsPath, "utf8");
      assert.equal(instructions.includes(installedReferencePrefix), true);
      assert.doesNotMatch(instructions, /\.\.\/(?:\.cannbot|references|workflows)\//);

      const record = readPluginRecord(target, tool, plugin);
      assert.equal(record.skills.length, 4);
      assert.equal(record.agents.length, 5);
      assert.equal(record.source.kind, source);
      assert.equal(record.skillInstallMode, source === "repository" ? "symlink" : "copy");
      assertUnifiedInstall(target, tool, plugin);
    });
  }
}

for (const source of sources) {
  test(`${source} installs ops-perf-optimize workflow tools`, () => {
    const { target, result: installResult } = installPlugin("ops-perf-optimize", "opencode", source);
    const pluginRoot = join(target, ".cannbot", "plugins", "ops-perf-optimize");
    const workflowRoot = join(skillRoot(target, "opencode"), "ops-perf-optimize-workflow");
    const workflowScripts = join(workflowRoot, "scripts");
    for (const script of ["workflow_state.py", "prepare_case_sets.py", "validate_source_isolation.py"]) {
      assert.equal(existsSync(join(workflowScripts, script)), true, script);
    }
    assert.equal(existsSync(join(workflowRoot, "workflows", "task-prompts.md")), true);
    assert.equal(existsSync(join(workflowRoot, "workflows", "prompts", "baseline.md")), true);
    assert.equal(existsSync(join(pluginRoot, "workflows")), false);
    assert.equal(existsSync(join(pluginRoot, "scripts")), false);
    assert.equal(existsSync(join(pluginRoot, "quickstart.md")), true);
    assert.match(installResult.stdout, /方式一：自动化调优/);
    assert.match(installResult.stdout, /方式二：交互式调优/);
    const agentFile = join(target, ".opencode", "agents", "perf-optimize.md");
    assert.equal(existsSync(agentFile), true);
    assert.match(readFileSync(agentFile, "utf8"), /^name: perf-optimize$/m);
    assert.deepEqual(readPluginRecord(target, "opencode", "ops-perf-optimize").agents,
      [".opencode/agents/perf-optimize.md"]);
  });
}

for (const plugin of ["model-infer-optimize"]) {
  test(`${plugin} source init delegates to the unified installer`, () => {
    const { target } = installWithSourceInit(plugin, "opencode");
    const record = readPluginRecord(target, "opencode", plugin);
    assert.equal(record.skillInstallMode, "symlink");
    assert.equal(lstatSync(join(target, record.skills[0])).isSymbolicLink(), true);
    assert.equal(existsSync(join(configRoot(target, "opencode"), "cannbot-plugin.json")), true);
    assertUnifiedInstall(target, "opencode", plugin);
  });
}

test("model-train-precision-diagnose source init delegates to the unified installer", () => {
  const plugin = "model-train-precision-diagnose";
  const { target } = installWithSourceInit(plugin, "opencode");
  const record = readPluginRecord(target, "opencode", plugin);
  assert.equal(record.skillInstallMode, "symlink");
  assert.equal(record.skills.length, 4);
  assert.equal(record.agents.length, 5);
  assert.equal(
    existsSync(join(target, ".cannbot", "plugins", plugin, "workflows", "references", "tool-semantics-and-version-probe.md")),
    true,
  );
  assertUnifiedInstall(target, "opencode", plugin);
});

test("ops-direct-invoke source init uses the unified installer", () => {
  const { target } = installWithSourceInit("ops-direct-invoke", "opencode");
  const root = configRoot(target, "opencode");
  assertUnifiedInstall(target, "opencode", "ops-direct-invoke");
  assert.equal(existsSync(join(target, ".cannbot", "permissions", "PM.js")), false);
  assert.equal(existsSync(join(skillRoot(target, "opencode"), "ops-direct-invoke", "SKILL.md")), true);
  assert.equal(existsSync(join(root, "agents", "ops-direct-invoke-verifier.md")), true);
});

test("source init defaults to the source repository root and reads the manifest name", () => {
  const sandbox = createSandbox("cannbot-init-default-");
  const fixtureRepository = join(sandbox, "repository");
  const pluginDir = join(fixtureRepository, "plugins-official", "fixture-plugin");
  const fixtureCli = join(fixtureRepository, "script", "bin", "cannbot.js");
  const capture = join(sandbox, "args.json");
  mkdirSync(join(pluginDir, ".claude-plugin"), { recursive: true });
  writeFileSync(join(pluginDir, ".claude-plugin", "plugin.json"), JSON.stringify({ name: "fixture-entry" }));
  mkdirSync(join(fixtureRepository, "script", "bin"), { recursive: true });
  writeFileSync(fixtureCli, [
    "const fs = require('node:fs');",
    "fs.writeFileSync(process.env.CANNBOT_CAPTURE, JSON.stringify(process.argv.slice(2)));",
    "",
  ].join("\n"));

  const result = spawnSync("bash", [join(packageRoot, "bin", "source-plugin-init.sh"), pluginDir], {
    cwd: pluginDir,
    encoding: "utf8",
    env: { ...process.env, CANNBOT_CAPTURE: capture },
  });
  assert.equal(result.status, 0, result.stderr || result.stdout);
  const args = JSON.parse(readFileSync(capture, "utf8"));
  assert.deepEqual(args, [
    "install",
    "fixture-entry",
    "--tool",
    "opencode",
    "--target",
    fixtureRepository,
    "--source",
    fixtureRepository,
    "--plugin-dir",
    pluginDir,
  ]);

  const skills = "a25ecb1cda6234d9a95493bf8c913f81b86b55a0";
  const withSkills = spawnSync("bash", [
    join(packageRoot, "bin", "source-plugin-init.sh"), pluginDir, "codex", join(sandbox, "target"), "--skills", skills,
  ], {
    cwd: pluginDir,
    encoding: "utf8",
    env: { ...process.env, CANNBOT_CAPTURE: capture },
  });
  assert.equal(withSkills.status, 0, withSkills.stderr || withSkills.stdout);
  assert.deepEqual(JSON.parse(readFileSync(capture, "utf8")), [
    "install",
    "fixture-entry",
    "--tool",
    "codex",
    "--target",
    join(sandbox, "target"),
    "--source",
    fixtureRepository,
    "--plugin-dir",
    pluginDir,
    "--skills",
    skills,
  ]);
});

test("source install links a selected local shared Skill repository and records its revision", () => {
  const sandbox = createSandbox("cannbot-local-skills-");
  const target = join(sandbox, "project");
  const skills = join(sandbox, "cannbot-skills");
  mkdirSync(target);
  const definition = pluginSourceDefinition(repositoryRoot, "model-infer-optimize");
  for (const skill of definition.skills) {
    mkdirSync(join(skills, skill), { recursive: true });
    writeFileSync(join(skills, skill, "SKILL.md"), [
      "---",
      `name: ${skill.split("/").at(-1)}`,
      "description: fixture",
      "---",
      "",
    ].join("\n"));
  }
  writeFileSync(join(skills, "LICENSE"), "fixture shared license\n");
  for (const args of [["init"], ["add", "."], ["-c", "user.name=test", "-c", "user.email=test@example.com", "commit", "-m", "fixture"]]) {
    const result = spawnSync("git", args, { cwd: skills, encoding: "utf8" });
    assert.equal(result.status, 0, result.stderr || result.stdout);
  }

  const result = spawnSync(process.execPath, [
    cli, "install", "model-infer-optimize", "--tool", "codex", "--target", target,
    "--source", repositoryRoot, "--skills", skills,
  ], {
    cwd: target,
    encoding: "utf8",
    env: {
      ...process.env,
      HOME: join(sandbox, "home"),
      XDG_CACHE_HOME: join(sandbox, "cache"),
      CANNBOT_SKIP_CODEX_PLUGIN_ADD: "1",
      CANNBOT_SKIP_DEPENDENCY_REPOS: "1",
    },
  });
  assert.equal(result.status, 0, result.stderr || result.stdout);
  const record = readPluginRecord(target, "codex", "model-infer-optimize");
  assert.equal(record.source.revisions["cannbot-skills"].selection, "local-path");
  assert.equal(record.source.revisions["cannbot-skills"].path, skills);
  assert.equal(record.source.revisions["cannbot-skills"].commit, spawnSync(
    "git", ["-C", skills, "rev-parse", "HEAD"], { encoding: "utf8" },
  ).stdout.trim());
  assert.equal(realpathSync(join(skillRoot(target, "codex"), "model-infer-fusion")),
    realpathSync(join(skills, "model", "model-infer-fusion")));
  assert.equal(readFileSync(join(target, ".cannbot", "plugins", "model-infer-optimize", "SKILLS_LICENSE"), "utf8"),
    "fixture shared license\n");
});

test("source install preserves an existing real Skill directory", () => {
  const sandbox = createSandbox("cannbot-skill-collision-");
  const target = join(sandbox, "project");
  const destination = join(target, ".agents", "skills", "model-infer-fusion");
  const sentinel = join(destination, "user-content.txt");
  mkdirSync(destination, { recursive: true });
  writeFileSync(sentinel, "keep\n");

  const result = spawnSync(process.execPath, [
    cli,
    "install",
    "model-infer-optimize",
    "--tool",
    "opencode",
    "--target",
    target,
    "--source",
    repositoryRoot,
    "--skills",
    join(repositoryRoot, "vendor", "cannbot-skills"),
  ], {
    cwd: target,
    encoding: "utf8",
    env: {
      ...process.env,
      HOME: join(sandbox, "home"),
      CANNBOT_SKIP_OPENCODE_PLUGIN_ADD: "1",
      CANNBOT_SKIP_DEPENDENCY_REPOS: "1",
    },
  });
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /Skill destination already exists and is not a symlink/);
  assert.equal(readFileSync(sentinel, "utf8"), "keep\n");
  assert.equal(lstatSync(destination).isDirectory(), true);
});

test("reinstall preserves user instructions and keeps one managed block", () => {
  const { sandbox, target } = installPlugin("model-infer-optimize", "dsh", "package");
  const instructionsPath = join(target, "AGENTS.md");
  writeFileSync(instructionsPath, `user instructions\n\n${readFileSync(instructionsPath, "utf8")}`);
  const result = spawnSync(process.execPath, [
    cli,
    "install",
    "model-infer-optimize",
    "--tool",
    "dsh",
    "--target",
    target,
  ], {
    cwd: target,
    encoding: "utf8",
    env: {
      ...process.env,
      HOME: join(sandbox, "home"),
      XDG_CACHE_HOME: join(sandbox, "cache"),
      CANNBOT_SKIP_DEPENDENCY_REPOS: "1",
    },
  });
  assert.equal(result.status, 0, result.stderr || result.stdout);
  const instructions = readFileSync(instructionsPath, "utf8");
  assert.match(instructions, /^user instructions/m);
  assert.equal(instructions.match(/<!-- cannbot:model-infer-optimize:start -->/g)?.length, 1);
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
  assert.equal(existsSync(join(skillRoot(first.target, "dsh"), "ascendc-env-check", "SKILL.md")), true);
  assert.equal(existsSync(join(skillRoot(first.target, "dsh"), "model-infer-migrator", "SKILL.md")), true);
});

test("Claude hook installation is idempotent", () => {
  const first = installPlugin("model-infer-optimize", "claude", "package");
  const settingsPath = join(first.target, ".claude", "settings.json");
  const before = readFileSync(settingsPath, "utf8");
  const result = spawnSync(process.execPath, [
    cli,
    "install",
    "model-infer-optimize",
    "--tool",
    "claude",
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
  assert.equal(readFileSync(settingsPath, "utf8"), before);
});

test("declarative dependencies use the same project-level install flow", () => {
  const sandbox = createSandbox("cannbot-dependency-");
  const dependencyRepository = join(sandbox, "dependency-repository");
  mkdirSync(dependencyRepository);
  const initialized = spawnSync("git", ["init", "--quiet", dependencyRepository], { encoding: "utf8" });
  assert.equal(initialized.status, 0, initialized.stderr || initialized.stdout);

  const plugin = "dependency-fixture";
  const bundleRoot = join(sandbox, "bundle");
  const pluginRoot = join(bundleRoot, "plugins-official", plugin);
  const skillsRepository = join(bundleRoot, "skills-repository");
  const fixtureSkill = join(skillsRepository, "fixture-skill");
  mkdirSync(join(pluginRoot, ".claude-plugin"), { recursive: true });
  mkdirSync(join(fixtureSkill, "scripts"), { recursive: true });
  mkdirSync(join(skillsRepository, ".git"));
  writeFileSync(join(pluginRoot, ".claude-plugin", "plugin.json"), JSON.stringify({
    name: plugin,
    version: "1.0.0",
    description: "Dependency fixture",
  }));
  writeFileSync(join(pluginRoot, "plugin-sources.json"), JSON.stringify({
    skillsRepository: "skills-repository",
    skillInstallMode: "symlink",
    skills: ["fixture-skill"],
  }));
  writeFileSync(join(fixtureSkill, "SKILL.md"), [
    "---",
    "name: fixture-skill",
    "description: Test fixture",
    "---",
    "",
  ].join("\n"));
  writeFileSync(join(fixtureSkill, "scripts", "clean_markdown.py"), [
    "import argparse",
    "from pathlib import Path",
    "parser = argparse.ArgumentParser()",
    "parser.add_argument('--dir', required=True)",
    "parser.add_argument('--no-backup', action='store_true')",
    "parser.add_argument('--quiet', action='store_true')",
    "args = parser.parse_args()",
    "Path(args.dir, '.cleaned-by-skill').write_text('cleaned\\n')",
    "",
  ].join("\n"));
  writeFileSync(join(pluginRoot, "plugin-install.json"), JSON.stringify({
    dependencies: [{
      name: "fixture-dependency",
      repository: dependencyRepository,
      expose: "fixture-dependency",
      cleanMarkdownWithSkill: "fixture-skill",
    }],
  }));

  const target = join(sandbox, "project");
  mkdirSync(target);
  const result = spawnSync(process.execPath, [
    cli,
    "install",
    plugin,
    "--tool",
    "dsh",
    "--target",
    target,
    "--source",
    bundleRoot,
  ], {
    cwd: target,
    encoding: "utf8",
    env: {
      ...process.env,
      HOME: join(sandbox, "home"),
      XDG_CACHE_HOME: join(sandbox, "cache"),
      CANNBOT_SKIP_DEPENDENCY_REPOS: "0",
    },
  });
  assert.equal(result.status, 0, result.stderr || result.stdout);
  const checkout = join(target, ".cannbot", "dependencies", plugin, "fixture-dependency");
  assert.equal(existsSync(join(checkout, ".git")), true);
  assert.equal(readFileSync(join(checkout, ".cleaned-by-skill"), "utf8"), "cleaned\n");
  assert.equal(lstatSync(join(target, "fixture-dependency")).isSymbolicLink(), true);
  assert.equal(isAbsolute(readlinkSync(join(target, "fixture-dependency"))), false);
  const record = readPluginRecord(target, "dsh", plugin);
  assert.deepEqual(record.dependencies, [join(".cannbot", "dependencies", plugin, "fixture-dependency")]);
});

// Dependency repository assets: a plugin without a local skills/ directory declares
// an "assets" dependency; the installer clones the dependency repository, reads the
// plugin-assets.json manifest inside it (inline keys in plugin-install.json override),
// and links the declared Skills / hooks / AGENTS.md into the target project.
function createDependencyRepository(sandbox, name, files) {
  const repository = join(sandbox, name);
  for (const [relativePath, content] of Object.entries(files)) {
    const path = join(repository, relativePath);
    mkdirSync(dirname(path), { recursive: true });
    writeFileSync(path, content);
  }
  for (const args of [
    ["init", "--quiet"],
    ["add", "-A"],
    ["-c", "user.name=test", "-c", "user.email=test@example.com", "commit", "--quiet", "-m", "fixture"],
  ]) {
    const result = spawnSync("git", args, { cwd: repository, encoding: "utf8" });
    assert.equal(result.status, 0, result.stderr || result.stdout);
  }
  return repository;
}

function createAssetsPluginBundle(sandbox, dependencies) {
  const bundleRoot = join(sandbox, "bundle");
  const pluginRoot = join(bundleRoot, "plugins-official", "asset-fixture");
  mkdirSync(join(pluginRoot, ".claude-plugin"), { recursive: true });
  writeFileSync(join(pluginRoot, ".claude-plugin", "plugin.json"), JSON.stringify({
    name: "asset-fixture",
    version: "1.0.0",
    description: "Dependency assets fixture",
  }));
  writeFileSync(join(pluginRoot, "plugin-install.json"), JSON.stringify({ dependencies }));
  return bundleRoot;
}

function installAssetsFixture(bundleRoot, target, sandbox, tool) {
  mkdirSync(target, { recursive: true });
  const result = spawnSync(process.execPath, [
    cli, "install", "asset-fixture", "--tool", tool, "--target", target, "--source", bundleRoot,
  ], {
    cwd: target,
    encoding: "utf8",
    env: {
      ...process.env,
      HOME: join(sandbox, "home"),
      XDG_CACHE_HOME: join(sandbox, "cache"),
      CANNBOT_SKIP_CODEX_PLUGIN_ADD: "1",
      CANNBOT_SKIP_OPENCODE_PLUGIN_ADD: "1",
      CANNBOT_SKIP_DEPENDENCY_REPOS: "0",
    },
  });
  return result;
}

const manifestSkillFiles = {
  "ops/demo-skill/SKILL.md": ["---", "name: demo-skill", "description: Fixture", "---", ""].join("\n"),
  "plugins-official/demo-plugin/plugin-assets.json": JSON.stringify({
    plugin: "demo-plugin",
    skills: { dir: "ops", names: ["demo-skill"] },
    hooks: { dir: "plugins-official/demo-plugin/hooks" },
    agentsMd: "plugins-official/demo-plugin/AGENTS.md",
  }),
  "plugins-official/demo-plugin/hooks/hooks.json": JSON.stringify({
    hooks: {
      SessionStart: [{
        matcher: "",
        hooks: [{ type: "command", command: "node ${CLAUDE_PLUGIN_ROOT}/hooks/session-start.js" }],
      }],
    },
  }),
  "plugins-official/demo-plugin/AGENTS.md": "# Demo Plugin\n\nRun `bash skills/demo-skill/scripts/check.sh`.\n",
};

test("dependency assets install Skills, hooks and instructions from the dependency repository", () => {
  const sandbox = createSandbox("cannbot-dep-assets-");
  const dependency = createDependencyRepository(sandbox, "skills-repository", manifestSkillFiles);
  const bundleRoot = createAssetsPluginBundle(sandbox, [{
    name: "skills-repository",
    repository: dependency,
    assets: { plugin: "plugins-official/demo-plugin" },
  }]);
  const target = join(sandbox, "project");

  const result = installAssetsFixture(bundleRoot, target, sandbox, "opencode");
  assert.equal(result.status, 0, result.stderr || result.stdout);

  const checkout = join(target, ".cannbot", "dependencies", "asset-fixture", "skills-repository");
  const installedSkill = join(target, ".agents", "skills", "demo-skill");
  assert.equal(lstatSync(installedSkill).isSymbolicLink(), true);
  assert.equal(isAbsolute(readlinkSync(installedSkill)), false);
  assert.equal(realpathSync(installedSkill), realpathSync(join(checkout, "ops", "demo-skill")));
  assert.equal(
    existsSync(join(target, ".cannbot", "plugins", "asset-fixture", "hooks", "hooks.json")),
    true,
  );
  const instructions = readFileSync(join(target, "AGENTS.md"), "utf8");
  assert.match(instructions, /# Demo Plugin/);
  assert.equal(instructions.match(/<!-- cannbot:asset-fixture:start -->/g)?.length, 1);
  // The Skill path in the dependency instructions is rewritten to the installed location.
  assert.ok(instructions.includes(join(target, ".agents", "skills", "demo-skill") + "/"));

  const record = readPluginRecord(target, "opencode", "asset-fixture");
  assert.deepEqual(record.dependencies, [join(".cannbot", "dependencies", "asset-fixture", "skills-repository")]);
  assert.deepEqual(record.dependencyAssets, [{
    dependency: "skills-repository",
    skills: ["demo-skill"],
    hooks: true,
    agentsMd: true,
  }]);

  // Reinstalling is idempotent: the same links, one managed instructions block.
  const again = installAssetsFixture(bundleRoot, target, sandbox, "opencode");
  assert.equal(again.status, 0, again.stderr || again.stdout);
  assert.equal(lstatSync(installedSkill).isSymbolicLink(), true);
  assert.equal(
    readFileSync(join(target, "AGENTS.md"), "utf8").match(/<!-- cannbot:asset-fixture:start -->/g)?.length,
    1,
  );
});

test("Codex native plugin receives dependency Skills", () => {
  const sandbox = createSandbox("cannbot-dep-assets-codex-");
  const dependency = createDependencyRepository(sandbox, "skills-repository", manifestSkillFiles);
  const bundleRoot = createAssetsPluginBundle(sandbox, [{
    name: "skills-repository",
    repository: dependency,
    assets: { plugin: "plugins-official/demo-plugin" },
  }]);
  const target = join(sandbox, "project");

  const result = installAssetsFixture(bundleRoot, target, sandbox, "codex");
  assert.equal(result.status, 0, result.stderr || result.stdout);
  const checkoutSkill = join(target, ".cannbot", "dependencies", "asset-fixture", "skills-repository", "ops", "demo-skill");
  const projectSkill = join(target, ".agents", "skills", "demo-skill");
  const nativeSkill = join(sandbox, "home", "plugins", "asset-fixture", "skills", "demo-skill");
  assert.equal(realpathSync(projectSkill), realpathSync(checkoutSkill));
  assert.equal(existsSync(join(nativeSkill, "SKILL.md")), true);
  assert.equal(readFileSync(join(nativeSkill, "SKILL.md"), "utf8"),
    readFileSync(join(checkoutSkill, "SKILL.md"), "utf8"));
});

test("dependency hooks register in Claude settings with the assembled plugin root", () => {
  const sandbox = createSandbox("cannbot-dep-assets-claude-");
  const dependency = createDependencyRepository(sandbox, "skills-repository", manifestSkillFiles);
  const bundleRoot = createAssetsPluginBundle(sandbox, [{
    name: "skills-repository",
    repository: dependency,
    assets: { plugin: "plugins-official/demo-plugin" },
  }]);
  const target = join(sandbox, "project");

  const result = installAssetsFixture(bundleRoot, target, sandbox, "claude");
  assert.equal(result.status, 0, result.stderr || result.stdout);
  const settings = JSON.parse(readFileSync(join(target, ".claude", "settings.json"), "utf8"));
  const command = settings.hooks.SessionStart[0].hooks[0].command;
  assert.ok(command.includes(join(target, ".cannbot", "plugins", "asset-fixture")));
  assert.equal(command.includes("${CLAUDE_PLUGIN_ROOT}"), false);
  assert.equal(
    existsSync(join(target, ".claude", "skills", "demo-skill", "SKILL.md")),
    true,
  );
});

test("inline assets override the manifest and a missing manifest is skipped", () => {
  const sandbox = createSandbox("cannbot-dep-assets-inline-");
  const inlineRepository = createDependencyRepository(sandbox, "inline-repository", {
    "ops/inline-skill/SKILL.md": ["---", "name: inline-skill", "description: Fixture", "---", ""].join("\n"),
    "plugins-official/no-manifest/.gitkeep": "",
  });
  const bareRepository = createDependencyRepository(sandbox, "bare-repository", {
    "plugins-official/no-manifest/.gitkeep": "",
  });
  const bundleRoot = createAssetsPluginBundle(sandbox, [
    {
      name: "inline-repository",
      repository: inlineRepository,
      assets: {
        plugin: "plugins-official/no-manifest",
        skills: { dir: "ops", names: ["inline-skill"] },
      },
    },
    {
      name: "bare-repository",
      repository: bareRepository,
      assets: { plugin: "plugins-official/no-manifest" },
    },
  ]);
  const target = join(sandbox, "project");

  const result = installAssetsFixture(bundleRoot, target, sandbox, "opencode");
  assert.equal(result.status, 0, result.stderr || result.stdout);
  assert.match(result.stdout, /bare-repository.*skipped/);

  const inlineSkill = join(target, ".agents", "skills", "inline-skill");
  assert.equal(lstatSync(inlineSkill).isSymbolicLink(), true);
  assert.equal(
    realpathSync(inlineSkill),
    realpathSync(join(target, ".cannbot", "dependencies", "asset-fixture", "inline-repository", "ops", "inline-skill")),
  );
  const record = readPluginRecord(target, "opencode", "asset-fixture");
  assert.deepEqual(record.dependencyAssets, [{
    dependency: "inline-repository",
    skills: ["inline-skill"],
    hooks: false,
    agentsMd: false,
  }]);
});

// The community channel is exercised against fixtures built inside the sandbox rather
// than tracked fixture directories, following the dependency test above: nothing here is
// subject to CodeCheck, OAT, or the package `files` field.
function writeSkill(root, name, { policy = null, script = null } = {}) {
  mkdirSync(root, { recursive: true });
  const frontmatter = ["---", `name: ${name}`, `description: Fixture skill ${name}`];
  if (policy !== null) frontmatter.push(`disable-model-invocation: ${policy}`);
  frontmatter.push("---", "");
  writeFileSync(join(root, "SKILL.md"), frontmatter.join("\n"));
  if (script) {
    mkdirSync(join(root, "scripts"), { recursive: true });
    writeFileSync(join(root, "scripts", script), "#!/bin/bash\nexit 0\n");
  }
}

function createCommunityBundle(sandbox, bundleName, plugins, sharedSkills = []) {
  const bundleRoot = join(sandbox, bundleName);
  const skillsRepository = join(bundleRoot, "skills-repository");
  mkdirSync(join(skillsRepository, ".git"), { recursive: true });
  writeFileSync(join(skillsRepository, "LICENSE"), "fixture skills license\n");
  mkdirSync(join(bundleRoot, "plugins-community"), { recursive: true });
  // assemblePlugins stamps the repository licence onto official plugins, so it must exist
  // even in a bundle that only carries community ones.
  mkdirSync(join(bundleRoot, "plugins-official"), { recursive: true });
  writeFileSync(join(bundleRoot, "plugins-official", "LICENSE"), "fixture plugin license\n");
  for (const skill of sharedSkills) writeSkill(join(skillsRepository, skill), skill);

  const created = [];
  for (const plugin of plugins) {
    const pluginRoot = join(bundleRoot, "plugins-community", plugin.directoryName);
    mkdirSync(join(pluginRoot, ".claude-plugin"), { recursive: true });
    mkdirSync(join(pluginRoot, "agents"), { recursive: true });
    writeFileSync(join(pluginRoot, ".claude-plugin", "plugin.json"), JSON.stringify({
      name: plugin.name,
      version: "0.2.0",
      description: `Community fixture ${plugin.name}`,
      agents: ["./agents/fixture-agent.md"],
    }));
    writeFileSync(join(pluginRoot, "plugin-sources.json"), JSON.stringify({
      skillsRepository: "skills-repository",
      skillInstallMode: "symlink",
      skills: plugin.skills ?? [],
      preserveSkillInvocationPolicy: plugin.preserveSkillInvocationPolicy ?? true,
    }));

    const localSkills = plugin.localSkills ?? [];
    for (const [index, name] of localSkills.entries()) {
      // The first local Skill declares a policy and the second omits the key, so one
      // fixture covers both states of the invocation-policy switch.
      writeSkill(join(pluginRoot, "skills", name), name, {
        policy: index === 0 ? "true" : null,
        script: index === 0 ? "check.sh" : null,
      });
    }

    const referenced = localSkills[0] ?? (plugin.skills ?? [])[0];
    writeFileSync(join(pluginRoot, "agents", "fixture-agent.md"), [
      "---",
      "name: fixture-agent",
      "description: Fixture agent",
      "---",
      "",
      "Run the gate:",
      "",
      "```bash",
      `bash skills/${referenced}/scripts/check.sh --target a2`,
      "```",
      "",
      "Place new material in the skills/ directory of the plugin.",
      "",
    ].join("\n"));
    created.push({ ...plugin, pluginRoot, localSkills });
  }
  return { bundleRoot, skillsRepository, plugins: created };
}

function installFromBundle(bundleRoot, pluginName, tool, sandbox, target) {
  const projectTarget = target ?? join(sandbox, `project-${tool}-${pluginName}`);
  mkdirSync(projectTarget, { recursive: true });
  const result = spawnSync(process.execPath, [
    cli, "install", pluginName, "--tool", tool, "--target", projectTarget, "--source", bundleRoot,
  ], {
    cwd: projectTarget,
    encoding: "utf8",
    env: {
      ...process.env,
      HOME: join(sandbox, "home"),
      XDG_CACHE_HOME: join(sandbox, "cache"),
      CANNBOT_SKIP_CODEX_PLUGIN_ADD: "1",
      CANNBOT_SKIP_OPENCODE_PLUGIN_ADD: "1",
    },
  });
  return { target: projectTarget, result };
}

const communityFixturePlugin = {
  name: "fixture-community",
  directoryName: "collaborative-fixture-long-directory-name",
  localSkills: ["fixture-policy-skill", "fixture-plain-skill"],
};

test("a community plugin installs under a directory name that differs from its manifest name", () => {
  const sandbox = createSandbox("cannbot-community-");
  const bundle = createCommunityBundle(sandbox, "bundle", [communityFixturePlugin]);
  assert.notEqual(communityFixturePlugin.directoryName, communityFixturePlugin.name);

  for (const tool of tools) {
    const { target, result } = installFromBundle(bundle.bundleRoot, communityFixturePlugin.name, tool, sandbox);
    assert.equal(result.status, 0, `${tool}: ${result.stderr || result.stdout}`);
    for (const skill of communityFixturePlugin.localSkills) {
      assert.equal(existsSync(join(skillRoot(target, tool), skill)), true, `${tool}: ${skill} missing`);
    }
    assert.equal(readPluginRecord(target, tool, communityFixturePlugin.name).plugin, communityFixturePlugin.name);
  }
});

test("installing a community plugin twice is idempotent", () => {
  const sandbox = createSandbox("cannbot-community-repeat-");
  const bundle = createCommunityBundle(sandbox, "bundle", [communityFixturePlugin]);
  const first = installFromBundle(bundle.bundleRoot, communityFixturePlugin.name, "claude", sandbox);
  assert.equal(first.result.status, 0, first.result.stderr || first.result.stdout);
  const registryPath = join(configRoot(first.target, "claude"), "cannbot-plugin.json");
  const before = readFileSync(registryPath, "utf8");

  const again = installFromBundle(
    bundle.bundleRoot, communityFixturePlugin.name, "claude", sandbox, first.target,
  );
  assert.equal(again.result.status, 0, again.result.stderr || again.result.stdout);
  assert.equal(readFileSync(registryPath, "utf8"), before);
});

test("agent bodies resolve Skill script paths after installation, and prose is left alone", () => {
  const sandbox = createSandbox("cannbot-agent-paths-");
  const bundle = createCommunityBundle(sandbox, "bundle", [communityFixturePlugin]);
  const referenced = communityFixturePlugin.localSkills[0];

  for (const tool of tools) {
    const { target, result } = installFromBundle(bundle.bundleRoot, communityFixturePlugin.name, tool, sandbox);
    assert.equal(result.status, 0, `${tool}: ${result.stderr || result.stdout}`);
    const agentPath = join(
      configRoot(target, tool), "agents", tool === "codex" ? "fixture-agent.toml" : "fixture-agent.md",
    );
    const body = readFileSync(agentPath, "utf8");
    const installedScript = join(skillRoot(target, tool), referenced, "scripts", "check.sh");

    assert.equal(existsSync(installedScript), true, `${tool}: installed script is missing`);
    assert.equal(
      body.includes(tool === "codex" ? JSON.stringify(installedScript).slice(1, -1) : installedScript),
      true,
      `${tool}: the executable path was not rewritten to the installed location`,
    );
    assert.doesNotMatch(body, new RegExp(`bash skills/${referenced}/`));
    // This sentence names the plugin's own skills/ directory, not a Skill, and stands.
    assert.match(body, /Place new material in the skills\/ directory of the plugin\./);
  }
});

test("a plugin may keep the invocation policy its Skills were authored with", () => {
  const sandbox = createSandbox("cannbot-invocation-policy-");
  const preserved = createCommunityBundle(sandbox, "bundle-preserve", [{
    ...communityFixturePlugin, preserveSkillInvocationPolicy: true,
  }]);
  const rewritten = createCommunityBundle(sandbox, "bundle-rewrite", [{
    ...communityFixturePlugin,
    name: "fixture-community-rewrite",
    directoryName: "community-rewrite-directory",
    preserveSkillInvocationPolicy: false,
  }]);

  const readBuiltSkill = (bundle, plugin, skill) => {
    const outputRoot = join(bundle.bundleRoot, "dist");
    assemblePlugins(bundle.bundleRoot, outputRoot);
    return readFileSync(
      join(outputRoot, "plugins", plugin.directoryName, "skills", skill, "SKILL.md"),
      "utf8",
    );
  };

  const [policySkill, plainSkill] = communityFixturePlugin.localSkills;
  assert.match(
    readBuiltSkill(preserved, preserved.plugins[0], policySkill),
    /^disable-model-invocation: true$/m,
  );
  assert.match(
    readBuiltSkill(rewritten, rewritten.plugins[0], policySkill),
    /^disable-model-invocation: false$/m,
  );
  // The Skill that never declared the key has no key in either mode.
  for (const [bundle, plugin] of [[preserved, preserved.plugins[0]], [rewritten, rewritten.plugins[0]]]) {
    assert.doesNotMatch(readBuiltSkill(bundle, plugin, plainSkill), /disable-model-invocation/);
  }
});

test("symlinks inside a community plugin resolve within that plugin", () => {
  const marketplace = JSON.parse(readFileSync(join(repositoryRoot, ".claude-plugin", "marketplace.json"), "utf8"));
  // plugins/ forbids tracked symlinks outright (see the 120000 assertion above). A
  // community plugin may carry them, so the replacement assertion is containment.
  for (const plugin of marketplace.plugins.filter(
    (candidate) => typeof candidate.source === "string" && candidate.source.startsWith("./plugins-community/"),
  )) {
    const pluginDir = realpathSync(join(repositoryRoot, plugin.source));
    const tracked = spawnSync("git", ["ls-files", "-s", plugin.source.replace(/^\.\//, "")], {
      cwd: repositoryRoot,
      encoding: "utf8",
    });
    assert.equal(tracked.status, 0, tracked.stderr);
    for (const line of tracked.stdout.split("\n")) {
      if (!line.startsWith("120000 ")) continue;
      const path = join(repositoryRoot, line.split("\t").at(-1));
      const resolved = realpathSync(path);
      assert.equal(resolved.startsWith(pluginDir), true, `${path} resolves outside its plugin: ${resolved}`);
    }
  }
});
