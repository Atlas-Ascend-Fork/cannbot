// Copyright (c) 2026 CANNBot contributors
// SPDX-License-Identifier: MIT
// See script/LICENSE for the full license text.

import assert from "node:assert/strict";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";

const cli = resolve(import.meta.dirname, "../bin/cannbot.js");
const pluginName = "marketplace-fixture";

function prepare(t, marketplaceText) {
  const sandbox = mkdtempSync(join(tmpdir(), "cannbot-marketplace-"));
  t.after(() => rmSync(sandbox, { recursive: true, force: true }));
  const target = join(sandbox, "project");
  const userDirectory = join(sandbox, "home");
  const pluginDirectory = join(sandbox, "plugin");
  const skill = "fixture-skill";
  mkdirSync(join(pluginDirectory, ".claude-plugin"), { recursive: true });
  mkdirSync(join(pluginDirectory, "skills", skill), { recursive: true });
  writeFileSync(join(pluginDirectory, ".claude-plugin", "plugin.json"), JSON.stringify({
    name: pluginName, version: "1.0.0", description: "Local installer fixture",
    skills: ["skills/fixture-skill"], agents: [],
  }));
  writeFileSync(join(pluginDirectory, "skills", skill, "SKILL.md"),
    "---\nname: fixture-skill\ndescription: Local installer fixture.\n---\nNew content.\n");
  const nativeMarker = join(userDirectory, "plugins", pluginName, "old.txt");
  const projectMarker = join(target, ".agents", "skills", skill, "old.txt");
  for (const marker of [nativeMarker, projectMarker]) {
    mkdirSync(dirname(marker), { recursive: true });
    writeFileSync(marker, "Existing installation must survive a rejected preflight.\n");
  }
  const marketplacePath = join(userDirectory, ".agents", "plugins", "marketplace.json");
  if (marketplaceText !== undefined) {
    mkdirSync(dirname(marketplacePath), { recursive: true });
    writeFileSync(marketplacePath, marketplaceText);
  }
  const install = (tool = "codex", selectedPluginDirectory = pluginDirectory) => spawnSync(process.execPath, [
    cli, "install", pluginName, "--tool", tool, "--target", target, "--plugin-dir", selectedPluginDirectory,
  ], {
    cwd: target, encoding: "utf8",
    env: {
      ...process.env, HOME: userDirectory, XDG_CACHE_HOME: join(sandbox, "cache"),
      CANNBOT_SKIP_CODEX_PLUGIN_ADD: "1", CANNBOT_SKIP_DEPENDENCY_REPOS: "1",
    },
  });
  return { install, target, nativeMarker, projectMarker, marketplacePath, userDirectory };
}

const invalidCatalogues = [
  ["invalid-json", "{"],
  ["wrong-root-type", "[]"],
  ["missing-name", JSON.stringify({ plugins: [] })],
  ["wrong-plugins-type", JSON.stringify({ name: "personal", plugins: {} })],
];
for (const [name, text] of invalidCatalogues) {
  test(`rejected ${name} preserves native and project assets`, (t) => {
    const fixture = prepare(t, text);
    const nativeBefore = readFileSync(fixture.nativeMarker);
    const projectBefore = readFileSync(fixture.projectMarker);

    const result = fixture.install();

    assert.notEqual(result.status, 0, result.stdout + result.stderr);
    assert.equal(readFileSync(fixture.marketplacePath, "utf8"), text);
    assert.equal(existsSync(fixture.nativeMarker), true, result.stdout + result.stderr);
    assert.equal(existsSync(fixture.projectMarker), true, result.stdout + result.stderr);
    assert.deepEqual(readFileSync(fixture.nativeMarker), nativeBefore);
    assert.deepEqual(readFileSync(fixture.projectMarker), projectBefore);
  });
}

test("valid catalogue still replaces assets and preserves unrelated entries", (t) => {
  const unrelated = { name: "unrelated", source: { source: "local", path: "./plugins/unrelated" } };
  const fixture = prepare(t, JSON.stringify({ name: "personal", plugins: [unrelated] }));

  const result = fixture.install();

  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.equal(existsSync(fixture.nativeMarker), false);
  assert.equal(existsSync(fixture.projectMarker), false);
  const catalogue = JSON.parse(readFileSync(fixture.marketplacePath, "utf8"));
  assert.deepEqual(catalogue.plugins.find((entry) => entry.name === "unrelated"), unrelated);
  assert.equal(catalogue.plugins.some((entry) => entry.name === pluginName), true);
  const installedSkill = join(fixture.userDirectory, "plugins", pluginName, "skills", "fixture-skill", "SKILL.md");
  assert.equal(existsSync(installedSkill), true);
});


test("missing catalogue is initialized for a successful Codex install", (t) => {
  const fixture = prepare(t);

  const result = fixture.install();

  assert.equal(result.status, 0, result.stdout + result.stderr);
  const catalogue = JSON.parse(readFileSync(fixture.marketplacePath, "utf8"));
  assert.equal(catalogue.name, "personal");
  assert.equal(catalogue.plugins.some((entry) => entry.name === pluginName), true);
});

test("Claude install does not validate an unrelated Codex catalogue", (t) => {
  const fixture = prepare(t, "{");

  const result = fixture.install("claude");

  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.equal(readFileSync(fixture.marketplacePath, "utf8"), "{");
  const skillPath = join(fixture.target, ".claude", "skills", "fixture-skill", "SKILL.md");
  assert.equal(existsSync(skillPath), true);
});


test("valid catalogue with a missing plugin preserves all existing assets", (t) => {
  const text = JSON.stringify({ name: "personal", plugins: [] });
  const fixture = prepare(t, text);
  const nativeBefore = readFileSync(fixture.nativeMarker);
  const projectBefore = readFileSync(fixture.projectMarker);

  const result = fixture.install("codex", join(fixture.target, "missing-plugin"));

  assert.notEqual(result.status, 0, result.stdout + result.stderr);
  assert.equal(readFileSync(fixture.marketplacePath, "utf8"), text);
  assert.deepEqual(readFileSync(fixture.nativeMarker), nativeBefore);
  assert.deepEqual(readFileSync(fixture.projectMarker), projectBefore);
});
