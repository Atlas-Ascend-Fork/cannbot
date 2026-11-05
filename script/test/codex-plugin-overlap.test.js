// Copyright (c) 2026 CANNBot contributors
// SPDX-License-Identifier: MIT

import assert from "node:assert/strict";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import test from "node:test";

const cli = fileURLToPath(new URL("../bin/cannbot.js", import.meta.url));

function fixture(t, scenario) {
  const root = mkdtempSync(join(tmpdir(), "cannbot-codex-overlap-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const home = scenario === "skill-ancestor" ? join(root, "plugin", "skills", "repo-requirement", "native-home")
    : scenario === "override-ancestor" ? join(root, "overrides", "repo-requirement", "native-home") : join(root, "home");
  const native = join(home, "plugins", "fixture");
  const plugin = scenario === "plugin" ? join(native, "source") : join(root, "plugin");
  let target = scenario === "target" || scenario === "target-alias" ? join(native, "project")
    : scenario === "target-home" ? home : join(root, "project");
  const override = scenario === "override-ancestor" ? join(root, "overrides") : join(native, "overrides");
  mkdirSync(join(plugin, ".claude-plugin"), { recursive: true });
  mkdirSync(join(plugin, "skills", "repo-requirement"), { recursive: true });
  mkdirSync(target, { recursive: true });
  writeFileSync(join(plugin, ".claude-plugin", "plugin.json"), JSON.stringify({
    name: "fixture", version: "1.0.0", description: "Fixture",
  }));
  writeFileSync(join(plugin, "skills", "repo-requirement", "SKILL.md"), "---\nname: repo-requirement\ndescription: fixture\n---\n");
  const sourceSentinel = join(plugin, "source-sentinel.txt");
  const targetSentinel = join(target, "project-sentinel.txt");
  writeFileSync(sourceSentinel, "source intact\n");
  writeFileSync(targetSentinel, "project intact\n");
  const nativeSentinel = join(native, "old-plugin.txt");
  if (scenario === "skill-ancestor" || scenario === "override-ancestor") {
    mkdirSync(native, { recursive: true });
    writeFileSync(nativeSentinel, "old plugin intact\n");
  }
  if (scenario === "dangling-native") {
    mkdirSync(join(home, "plugins"), { recursive: true });
    symlinkSync(join(root, "missing-old-plugin"), native, process.platform === "win32" ? "junction" : "dir");
  }
  let overrideSentinel;
  const args = [cli, "install", "fixture", "--tool", "codex", "--target"];
  if (scenario === "target-alias") {
    const alias = join(root, "project-alias");
    symlinkSync(target, alias, process.platform === "win32" ? "junction" : "dir");
    target = alias;
  }
  args.push(target, "--plugin-dir", plugin);
  if (scenario === "override" || scenario === "override-ancestor") {
    mkdirSync(join(override, "repo-requirement"), { recursive: true });
    writeFileSync(join(override, "repo-requirement", "SKILL.md"), "---\nname: repo-requirement\ndescription: override\n---\n");
    overrideSentinel = join(override, "repo-requirement", "override-sentinel.txt");
    writeFileSync(overrideSentinel, "override intact\n");
    args.push("--override-skills", override);
  }
  const result = spawnSync(process.execPath, args, {
    cwd: root, encoding: "utf8", timeout: 30000,
    env: { ...process.env, HOME: home, CANNBOT_SKIP_CODEX_PLUGIN_ADD: "1", CANNBOT_SKIP_DEPENDENCY_REPOS: "1", CANNBOT_SKIP_KNOWLEDGE_INDEX: "1" },
  });
  return { result, sourceSentinel, targetSentinel, overrideSentinel, native, nativeSentinel };
}

for (const scenario of ["target", "target-alias", "plugin", "override"]) {
  test(`Codex installation preserves overlapping ${scenario}`, (t) => {
    const f = fixture(t, scenario);
    assert.equal(readFileSync(f.sourceSentinel, "utf8"), "source intact\n");
    assert.equal(readFileSync(f.targetSentinel, "utf8"), "project intact\n");
    if (f.overrideSentinel) assert.equal(readFileSync(f.overrideSentinel, "utf8"), "override intact\n");
    assert.notEqual(f.result.status, 0);
    assert.match(f.result.stderr, /Codex.*overlap/i);
  });
}

test("Codex installation accepts separate paths", (t) => {
  const f = fixture(t, "normal");
  assert.equal(f.result.status, 0, f.result.stderr || f.result.stdout);
  assert.ok(existsSync(join(f.native, ".codex-plugin", "plugin.json")));
  assert.equal(readFileSync(f.sourceSentinel, "utf8"), "source intact\n");
  assert.equal(readFileSync(f.targetSentinel, "utf8"), "project intact\n");
});

test("Codex installation can replace a dangling old plugin link", (t) => {
  const f = fixture(t, "dangling-native");
  assert.equal(f.result.status, 0, f.result.stderr || f.result.stdout);
  assert.ok(existsSync(join(f.native, ".codex-plugin", "plugin.json")));
});

for (const scenario of ["skill-ancestor", "override-ancestor"]) {
  test(`Codex preserves the old plugin when its output is inside ${scenario}`, (t) => {
    const f = fixture(t, scenario);
    assert.equal(readFileSync(f.nativeSentinel, "utf8"), "old plugin intact\n");
    assert.equal(readFileSync(f.sourceSentinel, "utf8"), "source intact\n");
    assert.equal(readFileSync(f.targetSentinel, "utf8"), "project intact\n");
    if (f.overrideSentinel) assert.equal(readFileSync(f.overrideSentinel, "utf8"), "override intact\n");
    assert.notEqual(f.result.status, 0);
    assert.match(f.result.stderr, /Codex.*overlap/i);
  });
}

test("Codex accepts the home directory as a project target", (t) => {
  const f = fixture(t, "target-home");
  assert.equal(f.result.status, 0, f.result.stderr || f.result.stdout);
  assert.ok(existsSync(join(f.native, ".codex-plugin", "plugin.json")));
  assert.equal(readFileSync(f.targetSentinel, "utf8"), "project intact\n");
});
