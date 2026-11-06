// ----------------------------------------------------------------------------------------------------------
// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software; you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.
// ----------------------------------------------------------------------------------------------------------

import assert from "node:assert/strict";
import { cpSync, existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, realpathSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { basename, join, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";
import { assemblePlugins } from "../../../script/lib/plugin-bundle.js";

const repository = resolve(import.meta.dirname, "../../..");
const pluginId = "ops-qa-suite";
const plugin = join(repository, "plugins-community", pluginId);
const cli = join(repository, "script/bin/cannbot.js");
const definition = JSON.parse(readFileSync(join(plugin, "plugin-sources.json"), "utf8"));
const skillsRepository = join(repository, definition.skillsRepository);
const externalSkillSources = definition.skills.map((path) => join(skillsRepository, path));
const externalSkillNames = externalSkillSources.map((path) => basename(path)).sort();
const overlaySkillsRoot = join(plugin, ".opencode", "skills");
const localSkillNames = readdirSync(overlaySkillsRoot, { withFileTypes: true })
  .filter((entry) => entry.isDirectory() && existsSync(join(overlaySkillsRoot, entry.name, "SKILL.md")))
  .map((entry) => entry.name).sort();
const allSkillNames = [...localSkillNames, ...externalSkillNames].sort();
const overlayDirs = ["commands", "scripts", "templates", "config"];
const bash = process.env.CANNBOT_TEST_BASH || "bash";

function sandbox(t) {
  const root = mkdtempSync(join(tmpdir(), "cannbot-ops-qa-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  return root;
}

function assertSkillBytes(source, destination) {
  assert.deepEqual(readdirSync(destination).sort(), readdirSync(source).sort());
  for (const entry of readdirSync(source, { withFileTypes: true })) {
    if (entry.isDirectory()) assertSkillBytes(join(source, entry.name), join(destination, entry.name));
    else assert.deepEqual(readFileSync(join(destination, entry.name)), readFileSync(join(source, entry.name)));
  }
}

test("ops-qa-suite source tree declares the overlay layout without local skill copies", () => {
  assert.equal(existsSync(join(plugin, "skills")), false);
  assert.equal(localSkillNames.length, 11);
  assert.equal(externalSkillNames.length, 3);
  assert.equal(definition.skillsRepository, "vendor/cannbot-skills");
  assert.equal(definition.preserveSkillInvocationPolicy, true);
  for (const source of externalSkillSources) assert.ok(existsSync(join(source, "SKILL.md")), source);
  for (const dir of overlayDirs) assert.ok(existsSync(join(plugin, ".opencode", dir)), dir);
  const marketplace = JSON.parse(readFileSync(join(repository, ".claude-plugin/marketplace.json"), "utf8"));
  const entry = marketplace.plugins.find((candidate) => candidate.name === pluginId);
  const manifest = JSON.parse(readFileSync(join(plugin, ".claude-plugin", "plugin.json"), "utf8"));
  assert.equal(entry.source, `./plugins-community/${pluginId}`);
  assert.equal(manifest.name, entry.name);
  assert.equal(manifest.version, entry.version);
  assert.deepEqual(manifest.dependencies ?? [], entry.dependencies ?? []);
});

for (const source of ["repository", "package"]) {
  for (const tool of ["opencode", "codex", "claude", "trae", "dsh"]) {
    test(`ops-qa-suite ${source} installs and reinstalls for ${tool} with usable instructions`, (t) => {
      const root = sandbox(t);
      const target = join(root, "project with spaces");
      mkdirSync(target);
      const instructions = join(target, tool === "claude" ? "CLAUDE.md" : "AGENTS.md");
      writeFileSync(instructions, "KEEP_EXISTING_PROJECT_RULES\n");
      const args = [cli, "install", pluginId, "--tool", tool, "--target", target];
      if (source === "repository") args.push("--source", repository, "--skills", skillsRepository);
      const env = { ...process.env, HOME: join(root, "isolated home"),
        CANNBOT_SKIP_CODEX_PLUGIN_ADD: "1", CANNBOT_SKIP_OPENCODE_PLUGIN_ADD: "1" };
      for (let attempt = 0; attempt < 2; attempt += 1) {
        const result = spawnSync(process.execPath, args, { env, encoding: "utf8" });
        assert.equal(result.status, 0, result.stderr || result.stdout);
        const config = join(target, `.${tool}`);
        const skillRoot = join(target, ["opencode", "codex"].includes(tool) ? ".agents" : `.${tool}`, "skills");
        assert.deepEqual(readdirSync(skillRoot).sort(), externalSkillNames);
        const active = readFileSync(instructions, "utf8");
        assert.ok(active.startsWith("KEEP_EXISTING_PROJECT_RULES\n"));
        assert.equal(active.split(`<!-- cannbot:${pluginId}:start -->`).length - 1, 1);
        const registry = JSON.parse(readFileSync(join(config, "cannbot-plugin.json"), "utf8"));
        assert.equal(registry.plugins.filter((entry) => entry.plugin === pluginId).length, 1);
        assert.equal(registry.plugins[0].skills.length, 3);
        assert.equal(registry.plugins[0].agents.length, 1);
        for (const name of externalSkillNames) {
          assert.ok(existsSync(join(skillRoot, name, "SKILL.md")));
          const origin = externalSkillSources.find((path) => basename(path) === name);
          assertSkillBytes(origin, join(skillRoot, name));
          if (source === "repository") assert.equal(realpathSync(join(skillRoot, name)), realpathSync(origin));
        }
        if (tool === "codex") {
          assert.ok(existsSync(join(root, "isolated home", "plugins", pluginId, "skills", "gitcode-toolkit", "SKILL.md")));
        }
      }
    });
  }
}

test("ops-qa-suite bundle carries the overlay tree and shared Skills", (t) => {
  const root = sandbox(t);
  assemblePlugins(repository, root, [pluginId]);
  const bundled = join(root, "plugins", pluginId);
  assert.ok(existsSync(join(bundled, ".opencode", "skills", "scan-repo-docs", "SKILL.md")));
  assert.ok(existsSync(join(bundled, ".opencode", "scripts", "repo_detector.py")));
  assert.ok(existsSync(join(bundled, ".opencode", "commands", "scan-cmake.md")));
  assert.deepEqual(readdirSync(join(bundled, "skills")).sort(), externalSkillNames);
  const bundledManifest = JSON.parse(readFileSync(join(bundled, ".claude-plugin", "plugin.json"), "utf8"));
  assert.deepEqual(bundledManifest.skills.sort(), externalSkillNames.map((name) => `./skills/${name}`).sort());
  for (const source of externalSkillSources) assertSkillBytes(source, join(bundled, "skills", basename(source)));
  for (const name of localSkillNames) {
    assertSkillBytes(join(overlaySkillsRoot, name), join(bundled, ".opencode", "skills", name));
  }
});

test("ops-qa-suite standalone installer overlays .opencode with every Skill for opencode", (t) => {
  const root = sandbox(t);
  const target = join(root, "project");
  mkdirSync(target);
  const result = spawnSync(bash, [join(plugin, "init.sh"), "project", "opencode", target], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr || result.stdout);
  const overlay = join(target, ".opencode");
  assert.deepEqual(readdirSync(join(overlay, "skills")).sort(), allSkillNames);
  for (const name of localSkillNames) {
    assertSkillBytes(join(overlaySkillsRoot, name), join(overlay, "skills", name));
    assert.equal(realpathSync(join(overlay, "skills", name)), realpathSync(join(overlaySkillsRoot, name)));
  }
  for (const source of externalSkillSources) {
    assertSkillBytes(source, join(overlay, "skills", basename(source)));
    assert.equal(realpathSync(join(overlay, "skills", basename(source))), realpathSync(source));
  }
  for (const dir of overlayDirs) {
    assert.ok(existsSync(join(overlay, dir)));
    assert.equal(realpathSync(join(overlay, dir)), realpathSync(join(plugin, ".opencode", dir)));
  }
  assert.ok(existsSync(join(overlay, "scripts", "repo_detector.py")));
  const manifest = JSON.parse(readFileSync(join(overlay, "cannbot-manifest.json"), "utf8"));
  assert.equal(manifest.status, "complete");
  assert.equal(manifest.context_status, "installed");
  assert.equal(manifest.installed_skills.length, allSkillNames.length);
  assert.deepEqual(manifest.installed_skills.slice().sort(), allSkillNames);
  assert.ok(existsSync(join(overlay, "AGENTS.md")));
});

test("ops-qa-suite standalone installer keeps Skill and overlay targets separate for claude", (t) => {
  const root = sandbox(t);
  const target = join(root, "project");
  mkdirSync(target);
  const result = spawnSync(bash, [join(plugin, "init.sh"), "project", "claude", target], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr || result.stdout);
  assert.deepEqual(readdirSync(join(target, ".claude", "skills")).sort(), allSkillNames);
  assert.ok(existsSync(join(target, ".opencode", "scripts", "repo_detector.py")));
  assert.ok(existsSync(join(target, ".opencode", "commands")));
  assert.ok(existsSync(join(target, ".claude", "CLAUDE.md")));
  const manifest = JSON.parse(readFileSync(join(target, ".claude", "cannbot-manifest.json"), "utf8"));
  assert.equal(manifest.status, "complete");
  assert.equal(manifest.tool, "claude");
});

test("ops-qa-suite standalone installer reports partial failure and preserves conflicting overlays", (t) => {
  const root = sandbox(t);
  const target = join(root, "project");
  mkdirSync(join(target, ".opencode"), { recursive: true });
  writeFileSync(join(target, ".opencode", "scripts"), "KEEP_REAL_ENTRY\n");
  const result = spawnSync(bash, [join(plugin, "init.sh"), "project", "opencode", target], { encoding: "utf8" });
  assert.equal(result.status, 1, result.stderr || result.stdout);
  assert.equal(readFileSync(join(target, ".opencode", "scripts"), "utf8"), "KEEP_REAL_ENTRY\n");
  const manifest = JSON.parse(readFileSync(join(target, ".opencode", "cannbot-manifest.json"), "utf8"));
  assert.equal(manifest.status, "partial");
  assert.doesNotMatch(result.stdout, /安装完成/);
});

test("ops-qa-suite standalone installer validates every Skill before touching the target", (t) => {
  const root = sandbox(t);
  const damaged = join(root, "damaged plugin");
  cpSync(plugin, damaged, { recursive: true });
  rmSync(join(damaged, ".opencode", "skills", "scan-repo-docs", "SKILL.md"));
  const target = join(root, "untouched project");
  const result = spawnSync(bash, [join(damaged, "init.sh"), "project", "opencode", target], { encoding: "utf8" });
  assert.equal(result.status, 1, result.stderr || result.stdout);
  assert.equal(existsSync(target), false);
});

test("ops-qa-suite standalone installer resolves an explicit Skill repository without bundled Skills", (t) => {
  const root = sandbox(t);
  const copied = join(root, "standalone plugin");
  cpSync(plugin, copied, { recursive: true });
  const target = join(root, "project");
  const result = spawnSync(bash, [join(copied, "init.sh"), "project", "opencode", target,
    "--skills-repo", skillsRepository], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr || result.stdout);
  for (const source of externalSkillSources) {
    assertSkillBytes(source, join(target, ".opencode", "skills", basename(source)));
  }
});

test("ops-qa-suite standalone installer fails before writes if no shared Skill is available", (t) => {
  const root = sandbox(t);
  const copied = join(root, "standalone plugin");
  cpSync(plugin, copied, { recursive: true });
  const target = join(root, "untouched project");
  const result = spawnSync(bash, [join(copied, "init.sh"), "project", "opencode", target], { encoding: "utf8" });
  assert.equal(result.status, 1, result.stderr || result.stdout);
  assert.match(result.stderr, /共享 Skill/);
  assert.match(result.stderr, /--skills-repo/);
  assert.equal(existsSync(target), false);
});

test("ops-qa-suite bundled standalone installer works without a Skill submodule", (t) => {
  const root = sandbox(t);
  assemblePlugins(repository, root, [pluginId]);
  const bundled = join(root, "plugins", pluginId);
  const target = join(root, "project");
  const result = spawnSync(bash, [join(bundled, "init.sh"), "project", "opencode", target], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr || result.stdout);
  assert.deepEqual(readdirSync(join(target, ".opencode", "skills")).sort(), allSkillNames);
  for (const source of externalSkillSources) {
    assertSkillBytes(source, join(target, ".opencode", "skills", basename(source)));
  }
});

test("ops-qa-suite standalone installer rejects global installs and unsupported tools", (t) => {
  const root = sandbox(t);
  for (const argument of ["global", "codex", "dsh", "--unsupported"]) {
    const result = spawnSync(bash, [join(plugin, "init.sh"), "project", argument], { cwd: root, encoding: "utf8" });
    assert.equal(result.status, 2, result.stderr || result.stdout);
    assert.deepEqual(readdirSync(root), []);
  }
  const globalInstall = spawnSync(bash, [join(plugin, "init.sh"), "global", "opencode"], { cwd: root, encoding: "utf8" });
  assert.equal(globalInstall.status, 2, globalInstall.stderr || globalInstall.stdout);
  assert.match(globalInstall.stderr, /project 级安装/);
});
