// Copyright (c) 2026 CANNBot contributors
// SPDX-License-Identifier: MIT
// See script/LICENSE for the full license text.

import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import test from "node:test";

const cli = fileURLToPath(new URL("../bin/cannbot.js", import.meta.url));

function prepare(t) {
  const sandbox = mkdtempSync(join(tmpdir(), "cannbot-markers-"));
  t.after(() => rmSync(sandbox, { recursive: true, force: true }));
  const target = join(sandbox, "project");
  mkdirSync(target);
  writeFileSync(join(target, "CLAUDE.md"), "User instructions must remain.\n");

  const install = (name, body) => {
    const pluginDirectory = join(sandbox, name);
    mkdirSync(join(pluginDirectory, ".claude-plugin"), { recursive: true });
    writeFileSync(join(pluginDirectory, ".claude-plugin", "plugin.json"), JSON.stringify({
      name, version: "1.0.0", description: "Local instruction fixture", skills: [], agents: [],
    }));
    writeFileSync(join(pluginDirectory, "AGENTS.md"), body);
    const env = { ...process.env, CANNBOT_SKIP_DEPENDENCY_REPOS: "1" };
    delete env.CANNBOT_SOURCE_ROOT;
    delete env.CANNBOT_SKILLS_PATH;
    const result = spawnSync(process.execPath, [
      cli, "install", name, "--tool", "claude", "--target", target, "--plugin-dir", pluginDirectory,
    ], { encoding: "utf8", env });
    assert.equal(result.status, 0, result.stderr || result.stdout);
  };
  return { install, read: () => readFileSync(join(target, "CLAUDE.md"), "utf8") };
}

for (const [dotted, neighboring] of [["review.v1", "reviewXv1"], ["review.v1.beta", "reviewXv1Ybeta"]]) {
  test(`reinstall ${dotted} preserves ${neighboring} and user instructions`, (t) => {
    const { install, read } = prepare(t);
    install(dotted, "Old owned instructions.");
    install(neighboring, "Neighbor instructions must remain.");

    install(dotted, "Updated owned instructions.");

    const instructions = read();
    assert.ok(instructions.includes("Neighbor instructions must remain."));
    assert.ok(instructions.includes("User instructions must remain."));
    assert.ok(instructions.includes("Updated owned instructions."));
    assert.ok(!instructions.includes("Old owned instructions."));
    assert.equal(instructions.split(`<!-- cannbot:${dotted}:start -->`).length - 1, 1);
  });
}

test("first dotted installation preserves an already installed neighboring plugin", (t) => {
  const { install, read } = prepare(t);
  install("reviewXv1", "Existing neighbor instructions.");

  install("review.v1", "New dotted plugin instructions.");

  const instructions = read();
  assert.ok(instructions.includes("Existing neighbor instructions."));
  assert.ok(instructions.includes("New dotted plugin instructions."));
});

test("plain plugin reinstallation only replaces its own instructions", (t) => {
  const { install, read } = prepare(t);
  install("review-one", "Old plain instructions.");
  install("review-two", "Independent plain instructions.");

  install("review-one", "Updated plain instructions.");

  const instructions = read();
  assert.ok(instructions.includes("Independent plain instructions."));
  assert.ok(instructions.includes("Updated plain instructions."));
  assert.ok(!instructions.includes("Old plain instructions."));
});

test("repeated dotted installation stays idempotent without a neighboring plugin", (t) => {
  const { install, read } = prepare(t);
  install("review.v1", "Stable instructions.");

  install("review.v1", "Stable instructions.");

  const instructions = read();
  assert.equal(instructions.split("Stable instructions.").length - 1, 1);
  assert.ok(instructions.includes("User instructions must remain."));
});
