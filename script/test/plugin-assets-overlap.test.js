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

function fixture(t, location, useAlias = false, assetAlias = null, assetPlacement = "inside") {
  const root = mkdtempSync(join(tmpdir(), "cannbot-plugin-overlap-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const target = join(root, "project");
  const destination = join(target, ".cannbot", "plugins", "fixture");
  const plugin = location === "same" ? destination : location === "nested" ? join(destination, "source") : join(root, "plugin");
  mkdirSync(join(plugin, ".claude-plugin"), { recursive: true });
  mkdirSync(join(plugin, "skills", "demo"), { recursive: true });
  const assetBase = assetPlacement === "outside" ? join(root, "external") : destination;
  const workflows = assetAlias === "workflows" ? join(assetBase, "saved-workflows") : join(plugin, "workflows");
  mkdirSync(workflows, { recursive: true });
  writeFileSync(join(plugin, ".claude-plugin", "plugin.json"), JSON.stringify({ name: "fixture", version: "1.0.0" }));
  writeFileSync(join(plugin, "skills", "demo", "SKILL.md"), "---\nname: demo\ndescription: fixture\n---\n");
  writeFileSync(join(workflows, "sentinel.txt"), "keep source\n");
  const existing = join(destination, "KEEP.txt");
  if (assetAlias) {
    mkdirSync(destination, { recursive: true });
    writeFileSync(existing, "keep existing assets\n");
    const source = assetPlacement === "ancestor" ? root
      : assetAlias === "workflows" ? workflows : join(assetBase, `saved-${assetAlias}`);
    mkdirSync(source, { recursive: true });
    writeFileSync(join(source, "source.txt"), "keep linked source\n");
    symlinkSync(source, join(plugin, assetAlias), process.platform === "win32" ? "junction" : "dir");
  }
  let source = plugin;
  if (useAlias) {
    source = join(root, "alias");
    symlinkSync(plugin, source, process.platform === "win32" ? "junction" : "dir");
  }
  const result = spawnSync(process.execPath, [cli, "install", "fixture", "--tool", "dsh", "--target", target,
    "--plugin-dir", source], {
    cwd: root, encoding: "utf8", timeout: 30000,
    env: { ...process.env, CANNBOT_SKIP_DEPENDENCY_REPOS: "1", CANNBOT_SKIP_KNOWLEDGE_INDEX: "1" },
  });
  return { result, target, plugin, destination, existing };
}

for (const [location, alias] of [["same", false], ["nested", false], ["same", true]]) {
  test(`plugin source at ${location}${alias ? " through an alias" : ""} is preserved`, (t) => {
    const f = fixture(t, location, alias);
    assert.equal(existsSync(join(f.plugin, "workflows", "sentinel.txt")), true, "source was deleted");
    assert.notEqual(f.result.status, 0);
    assert.match(f.result.stderr, /plugin source.*inside.*assets/i);
    assert.equal(readFileSync(join(f.plugin, "workflows", "sentinel.txt"), "utf8"), "keep source\n");
    assert.equal(existsSync(join(f.target, ".dsh", "skills", "demo")), false);
  });
}

test("a separate plugin source installs its workflow assets", (t) => {
  const f = fixture(t, "separate");
  assert.equal(f.result.status, 0, f.result.stderr);
  assert.equal(readFileSync(join(f.destination, "workflows", "sentinel.txt"), "utf8"), "keep source\n");
});

for (const name of ["scripts", "workflows", "hooks"]) {
  test(`a linked ${name} source inside the asset output is preserved`, (t) => {
    const f = fixture(t, "separate", false, name);
    assert.equal(readFileSync(f.existing, "utf8"), "keep existing assets\n");
    assert.equal(readFileSync(join(f.plugin, name, "source.txt"), "utf8"), "keep linked source\n");
    assert.notEqual(f.result.status, 0);
    assert.match(f.result.stderr, /asset source.*overlap.*destination/i);
  });
}

test("an asset source containing its destination is rejected before cleanup", (t) => {
  const f = fixture(t, "separate", false, "scripts", "ancestor");
  assert.equal(readFileSync(f.existing, "utf8"), "keep existing assets\n");
  assert.notEqual(f.result.status, 0);
  assert.match(f.result.stderr, /asset source.*overlap.*destination/i);
});

test("a separate linked asset source is still copied", (t) => {
  const f = fixture(t, "separate", false, "scripts", "outside");
  assert.equal(f.result.status, 0, f.result.stderr);
  assert.equal(readFileSync(join(f.plugin, "scripts", "source.txt"), "utf8"), "keep linked source\n");
  assert.equal(readFileSync(join(f.destination, "scripts", "source.txt"), "utf8"), "keep linked source\n");
});
