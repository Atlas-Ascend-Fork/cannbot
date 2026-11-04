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
const pluginId = "shmem-ops-generator";
const plugin = join(repository, "plugins-community", pluginId);
const cli = join(repository, "script/bin/cannbot.js");
const definition = JSON.parse(readFileSync(join(plugin, "plugin-sources.json"), "utf8"));
const skillsRepository = join(repository, definition.skillsRepository);
const skillSources = definition.skills.map((path) => join(skillsRepository, path));
const skillNames = skillSources.map((path) => basename(path)).sort();
const bash = process.env.CANNBOT_TEST_BASH || "bash";

function sandbox(t) {
  const root = mkdtempSync(join(tmpdir(), "cannbot-shmem-"));
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

test("SHMEM source tree declares the migrated Skill package without local copies", () => {
  assert.equal(existsSync(join(plugin, "skills")), false);
  assert.equal(skillNames.length, 10);
  assert.equal(definition.skillsRepository, "vendor/cannbot-skills");
  assert.equal(definition.preserveSkillInvocationPolicy, true);
  const marketplace = JSON.parse(readFileSync(join(repository, ".claude-plugin/marketplace.json"), "utf8"));
  const pack = marketplace.plugins.find((entry) => entry.name === "shmem-ops-skills");
  assert.equal(pack.source.source, "git-subdir");
  assert.equal(pack.source.url, "https://gitcode.com/cann/cannbot-skills.git");
  assert.equal(pack.source.path, "community/ops");
  assert.equal(pack.source.sha, spawnSync("git", ["-C", skillsRepository, "rev-parse", "HEAD"], { encoding: "utf8" }).stdout.trim());
  assert.deepEqual(pack.skills.map((path) => `${pack.source.path}/${path.replace(/^\.\//, "")}`).sort(), definition.skills.slice().sort());
});

for (const source of ["repository", "package"]) {
  for (const tool of ["opencode", "codex", "claude", "trae", "dsh"]) {
    test(`SHMEM ${source} installs and reinstalls for ${tool} with usable instructions`, (t) => {
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
        assert.deepEqual(readdirSync(skillRoot).sort(), skillNames);
        const active = readFileSync(instructions, "utf8");
        assert.ok(active.startsWith("KEEP_EXISTING_PROJECT_RULES\n"));
        assert.equal(active.split(`<!-- cannbot:${pluginId}:start -->`).length - 1, 1);
        assert.doesNotMatch(active, /\]\(skills\/README\.md\)/);
        const registry = JSON.parse(readFileSync(join(config, "cannbot-plugin.json"), "utf8"));
        assert.equal(registry.plugins.filter((entry) => entry.plugin === pluginId).length, 1);
        assert.equal(registry.plugins[0].skills.length, 10);
        assert.equal(registry.plugins[0].agents.length, 1);
        assert.deepEqual(registry.plugins[0].dependencies, []);
        for (const name of skillNames) {
          assert.ok(existsSync(join(skillRoot, name, "SKILL.md")));
          const origin = skillSources.find((path) => basename(path) === name);
          assertSkillBytes(origin, join(skillRoot, name));
          if (source === "repository") assert.equal(realpathSync(join(skillRoot, name)), realpathSync(origin));
        }
        const guide = join(skillRoot, "shmem-ops-dev", "references", "GUIDE.md");
        assert.ok(existsSync(guide));
        if (tool === "codex") {
          assert.ok(existsSync(join(root, "isolated home", "plugins", pluginId, "skills", "shmem-ops-dev", "SKILL.md")));
        }
      }
    });
  }
}

test("SHMEM bundle delivers plugin guides with usable document links", (t) => {
  const root = sandbox(t);
  assemblePlugins(repository, root, [pluginId]);
  const bundled = join(root, "plugins", pluginId);
  for (const [directory, name] of [["", "README.md"], ["docs", "README.md"], ["docs", "skill-format-guide.md"]]) {
    const document = readFileSync(join(bundled, directory, name), "utf8");
    assert.equal(document, readFileSync(join(plugin, directory, name), "utf8"));
    for (const match of document.matchAll(/\[[^\]]*\]\(([^)]+)\)/g)) {
      if (!match[1].includes("://")) assert.ok(existsSync(join(bundled, directory, match[1])), match[1]);
      const shared = match[1].match(/^https:\/\/gitcode\.com\/cann\/cannbot-skills\/blob\/[0-9a-f]{40}\/(.+)$/);
      if (shared) assert.ok(existsSync(join(skillsRepository, shared[1])), shared[1]);
    }
  }
  for (const source of skillSources) assertSkillBytes(source, join(bundled, "skills", basename(source)));
});

test("SHMEM standalone installer reports partial failure and preserves conflicting instructions", (t) => {
  const root = sandbox(t);
  const conflict = join(root, ".opencode", "AGENTS.md");
  mkdirSync(join(root, ".opencode"), { recursive: true });
  writeFileSync(conflict, "KEEP_REAL_FILE\n");
  const result = spawnSync(bash, [join(plugin, "init.sh"), "project", "opencode", root], { encoding: "utf8" });
  assert.equal(result.status, 1, result.stderr || result.stdout);
  assert.equal(readFileSync(conflict, "utf8"), "KEEP_REAL_FILE\n");
  const manifest = JSON.parse(readFileSync(join(root, ".opencode", "cannbot-manifest.json"), "utf8"));
  assert.equal(manifest.status, "partial");
  assert.equal(manifest.context_status, "skipped");
  assert.doesNotMatch(result.stdout, /安装完成/);
});

test("SHMEM standalone installer reports a complete installation only after all entries succeed", (t) => {
  const root = sandbox(t);
  const result = spawnSync(bash, [join(plugin, "init.sh"), "project", "claude", root], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr || result.stdout);
  const config = join(root, ".claude");
  const manifest = JSON.parse(readFileSync(join(config, "cannbot-manifest.json"), "utf8"));
  assert.equal(manifest.status, "complete");
  assert.equal(manifest.context_status, "installed");
  assert.deepEqual(manifest.installed_skills.slice().sort(), skillNames);
  assert.ok(existsSync(join(config, "CLAUDE.md")));
});

test("SHMEM standalone installer validates all Skills before touching the target", (t) => {
  const root = sandbox(t);
  const damaged = join(root, "damaged plugin");
  cpSync(plugin, damaged, { recursive: true });
  for (const source of skillSources) cpSync(source, join(damaged, "skills", basename(source)), { recursive: true });
  rmSync(join(damaged, "skills", "shmem-ops-performance-optim", "SKILL.md"));
  const target = join(root, "untouched project");
  const result = spawnSync(bash, [join(damaged, "init.sh"), "project", "opencode", target], { encoding: "utf8" });
  assert.equal(result.status, 1, result.stderr || result.stdout);
  assert.equal(existsSync(target), false);
});

test("SHMEM standalone installer resolves an explicit Skill checkout without bundled Skills", (t) => {
  const root = sandbox(t);
  const copied = join(root, "standalone plugin");
  cpSync(plugin, copied, { recursive: true });
  const target = join(root, "project");
  const result = spawnSync(bash, [join(copied, "init.sh"), "project", "claude", target,
    "--skills-repo", skillsRepository], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr || result.stdout);
  for (const source of skillSources) assertSkillBytes(source, join(target, ".claude/skills", basename(source)));
});

test("SHMEM standalone installer fails before writes if no Skill dependency is available", (t) => {
  const root = sandbox(t);
  const copied = join(root, "standalone plugin");
  cpSync(plugin, copied, { recursive: true });
  const target = join(root, "untouched project");
  const result = spawnSync(bash, [join(copied, "init.sh"), "project", "opencode", target], { encoding: "utf8" });
  assert.equal(result.status, 1, result.stderr || result.stdout);
  assert.match(result.stderr, /community\/ops/);
  assert.match(result.stderr, /--skills-repo/);
  assert.equal(existsSync(target), false);
});

test("SHMEM bundled standalone installer works without a Skill submodule", (t) => {
  const root = sandbox(t);
  assemblePlugins(repository, root, [pluginId]);
  const bundled = join(root, "plugins", pluginId);
  const target = join(root, "project");
  const result = spawnSync(bash, [join(bundled, "init.sh"), "project", "claude", target], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr || result.stdout);
  for (const source of skillSources) assertSkillBytes(source, join(target, ".claude/skills", basename(source)));
});

test("SHMEM standalone installer rejects unsupported tools and unknown flags", (t) => {
  const root = sandbox(t);
  for (const argument of ["codex", "dsh", "--unsupported"]) {
    const result = spawnSync(bash, [join(plugin, "init.sh"), "project", argument], { cwd: root, encoding: "utf8" });
    assert.equal(result.status, 2, result.stderr || result.stdout);
    assert.deepEqual(readdirSync(root), []);
  }
});
