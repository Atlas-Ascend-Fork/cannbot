// Copyright (c) 2026 CANNBot contributors
// SPDX-License-Identifier: MIT

import assert from "node:assert/strict";
import { lstatSync, mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import test from "node:test";

const cli = fileURLToPath(new URL("../bin/cannbot.js", import.meta.url));

function git(cwd, args) {
  const result = spawnSync("git", args, { cwd, encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr);
}

function install(t, exposure) {
  const root = mkdtempSync(join(tmpdir(), "cannbot-nested-expose-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const repository = join(root, "dependency");
  const plugin = join(root, "plugin");
  const target = join(root, "target");
  mkdirSync(repository, { recursive: true });
  git(repository, ["init", "--quiet"]);
  writeFileSync(join(repository, "sentinel.txt"), "dependency content\n");
  git(repository, ["add", "sentinel.txt"]);
  git(repository, ["-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "--quiet", "-m", "fixture"]);
  mkdirSync(join(plugin, ".claude-plugin"), { recursive: true });
  mkdirSync(join(plugin, "skills", "demo"), { recursive: true });
  writeFileSync(join(plugin, ".claude-plugin", "plugin.json"), JSON.stringify({ name: "fixture", version: "1.0.0" }));
  writeFileSync(join(plugin, "skills", "demo", "SKILL.md"), "---\nname: demo\ndescription: fixture\n---\n");
  writeFileSync(join(plugin, "plugin-install.json"), JSON.stringify({ dependencies: [{ name: "local-dep", repository, expose: exposure, required: true }] }));
  const run = () => spawnSync(process.execPath, [cli, "install", "fixture", "--tool", "dsh", "--target", target, "--plugin-dir", plugin], {
    cwd: root, encoding: "utf8", timeout: 30000,
    env: { ...process.env, GIT_ALLOW_PROTOCOL: "file", CANNBOT_SKIP_DEPENDENCY_REPOS: "0", CANNBOT_SKIP_KNOWLEDGE_INDEX: "1" },
  });
  return { run, target };
}

test("dependency exposure works on a fresh target and reinstalls", (t) => {
  const { run, target } = install(t, "dependency");
  for (let attempt = 0; attempt < 2; attempt += 1) {
    const result = run();
    assert.equal(result.status, 0, result.stderr || result.stdout);
    const exposed = join(target, "dependency");
    assert.equal(lstatSync(exposed).isSymbolicLink(), true);
    assert.equal(realpathSync(exposed), realpathSync(join(target, ".cannbot", "dependencies", "fixture", "local-dep")));
    assert.equal(readFileSync(join(exposed, "sentinel.txt"), "utf8").trimEnd(), "dependency content");
  }
});
