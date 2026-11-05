// Copyright (c) 2026 CANNBot contributors
// SPDX-License-Identifier: MIT

import assert from "node:assert/strict";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import test from "node:test";

const cli = fileURLToPath(new URL("../bin/cannbot.js", import.meta.url));

function fixture(t, duplicate, { names = ["sample-skill", "sample-skill"], platform, existing = false } = {}) {
  const root = mkdtempSync(join(tmpdir(), "cannbot-duplicate-skills-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const plugin = join(root, "plugin");
  const target = join(root, "target");
  const a = join(plugin, "skills", "first");
  const b = join(plugin, "skills", "second");
  mkdirSync(join(plugin, ".claude-plugin"), { recursive: true });
  mkdirSync(a, { recursive: true });
  writeFileSync(join(plugin, ".claude-plugin", "plugin.json"), JSON.stringify({
    name: "fixture", version: "1.0.0", skills: ["./skills/first"],
  }));
  writeFileSync(join(a, "SKILL.md"), `---\nname: ${names[0]}\ndescription: first\n---\n`);
  if (duplicate) {
    mkdirSync(b, { recursive: true });
    writeFileSync(join(b, "SKILL.md"), `---\nname: ${names[1]}\ndescription: second\n---\n`);
  }
  const marker = join(target, ".dsh", "skills", names[0], "KEEP.txt");
  if (existing) {
    mkdirSync(join(target, ".dsh", "skills", names[0]), { recursive: true });
    writeFileSync(marker, "existing Skill content\n");
  }
  const nodeOptions = [];
  if (platform) {
    const preload = join(root, "platform.cjs");
    writeFileSync(preload, `Object.defineProperty(process, "platform", { value: ${JSON.stringify(platform)} });\n`);
    nodeOptions.push("--require", preload);
  }
  const result = spawnSync(process.execPath, [...nodeOptions, cli, "install", "fixture", "--tool", "dsh",
    "--target", target, "--plugin-dir", plugin], {
    cwd: root, encoding: "utf8", timeout: 30000,
    env: { ...process.env, CANNBOT_SKIP_DEPENDENCY_REPOS: "1", CANNBOT_SKIP_KNOWLEDGE_INDEX: "1" },
  });
  return { result, target, marker };
}

test("different Skill directories with the same name are rejected", (t) => {
  const { result, target } = fixture(t, true);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /duplicate Skill name.*sample-skill/i);
  assert.equal(existsSync(join(target, ".dsh", "skills", "sample-skill", "SKILL.md")), false);
});

test("a Skill discovered both in the manifest and directory is installed", (t) => {
  const { result, target } = fixture(t, false);
  assert.equal(result.status, 0, result.stderr);
  assert.match(readFileSync(join(target, ".dsh", "skills", "sample-skill", "SKILL.md"), "utf8"), /description: first/);
});

test("Windows case collisions are rejected before replacing existing Skills", (t) => {
  const { result, marker } = fixture(t, true, {
    names: ["Shared", "shared"], platform: "win32", existing: true,
  });
  assert.equal(readFileSync(marker, "utf8"), "existing Skill content\n");
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /duplicate Skill name.*shared/i);
});

test("a unique mixed-case Skill retains its original installed name", (t) => {
  const { result, target } = fixture(t, false, { names: ["Shared"] });
  assert.equal(result.status, 0, result.stderr);
  assert.match(readFileSync(join(target, ".dsh", "skills", "Shared", "SKILL.md"), "utf8"), /name: Shared/);
});

test("Linux keeps distinct mixed-case Skill names", { skip: process.platform !== "linux" }, (t) => {
  const { result, target } = fixture(t, true, { names: ["Shared", "shared"] });
  assert.equal(result.status, 0, result.stderr);
  assert.match(readFileSync(join(target, ".dsh", "skills", "Shared", "SKILL.md"), "utf8"), /description: first/);
  assert.match(readFileSync(join(target, ".dsh", "skills", "shared", "SKILL.md"), "utf8"), /description: second/);
});
