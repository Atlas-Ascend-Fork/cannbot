#!/usr/bin/env node
// Copyright (c) 2026 CANNBot contributors
// SPDX-License-Identifier: MIT
// See script/LICENSE for the full license text.

import assert from "node:assert/strict";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { spawnSync } from "node:child_process";

const packageRoot = resolve(import.meta.dirname, "..");
const metadata = JSON.parse(readFileSync(join(packageRoot, "package.json"), "utf8"));
const sandbox = mkdtempSync(join(tmpdir(), "cannbot-tilelang-package-"));

function run(command, args, cwd, env = process.env) {
  const result = spawnSync(command, args, { cwd, env, encoding: "utf8" });
  assert.equal(result.status, 0, result.error?.message || result.stderr || result.stdout);
  return result;
}

try {
  const consumer = join(sandbox, "consumer");
  const target = join(sandbox, "tilelang project");
  mkdirSync(consumer);
  mkdirSync(target);
  writeFileSync(join(consumer, "package.json"), '{"name":"tilelang-package-smoke","private":true}\n');
  run("npm", ["pack", "--pack-destination", sandbox], packageRoot);
  const archive = join(sandbox, `${metadata.name.replace(/^@/, "").replace("/", "-")}-${metadata.version}.tgz`);
  run("npm", ["install", "--ignore-scripts", "--no-audit", "--no-fund", archive], consumer);
  const executable = join(consumer, "node_modules", ".bin", "cannbot");
  run(executable, ["install", "tilelang-op-orchestrator", "--tool", "claude", "--target", target], consumer, {
    ...process.env,
    HOME: join(sandbox, "home"),
    XDG_CACHE_HOME: join(sandbox, "cache"),
  });
  const installedPackage = join(consumer, "node_modules", ...metadata.name.split("/"));
  const packagedPlugin = join(installedPackage, "dist", "plugins", "tilelang-op-orchestrator");
  for (const platform of ["Ascend910", "Ascend950"]) {
    assert.ok(existsSync(join(packagedPlugin, "workflows", platform, "workflow.md")));
    assert.ok(existsSync(join(target, ".claude", "skills", "tilelang-op-design", platform, "instructions.md")));
  }
  assert.equal(existsSync(join(packagedPlugin, "skills", "tilelang-op-orchestrator")), false);
  const registry = JSON.parse(readFileSync(join(target, ".claude", "cannbot-plugin.json"), "utf8"));
  assert.equal(registry.plugins[0].skills.length, 13);
  assert.equal(registry.plugins[0].agents.length, 6);
  const agent = readFileSync(join(target, ".claude", "agents", "tilelang-op-analyst.md"), "utf8");
  assert.equal(agent, readFileSync(join(packagedPlugin, "agents", "tilelang-op-analyst.md"), "utf8"));
  const settings = JSON.parse(readFileSync(join(target, ".claude", "settings.json"), "utf8"));
  const hook = run("bash", ["-c", settings.hooks.SessionStart[0].hooks[0].command], target);
  const context = JSON.parse(hook.stdout).hookSpecificOutput.additionalContext;
  assert.ok(context.includes(join(packagedPlugin, "workflows", "Ascend950", "workflow.md")));
  const sourceEntry = readFileSync(join(packagedPlugin, "AGENTS.md"), "utf8");
  run("bash", [join(packagedPlugin, "init.sh"), "project", "claude"], consumer);
  assert.ok(existsSync(join(packagedPlugin, ".claude", "cannbot-plugin.json")));
  assert.ok(existsSync(join(packagedPlugin, ".claude", "skills", "tilelang-op-design")));
  assert.equal(readFileSync(join(packagedPlugin, "AGENTS.md"), "utf8"), sourceEntry);
  for (const parent of [consumer, installedPackage]) {
    assert.equal(existsSync(join(parent, ".claude")), false);
    assert.equal(existsSync(join(parent, ".cannbot")), false);
  }
  console.log("Verified TileLang installation and SessionStart hook from the npm tarball.");
} finally {
  rmSync(sandbox, { recursive: true, force: true });
}
