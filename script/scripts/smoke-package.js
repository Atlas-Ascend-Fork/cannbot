#!/usr/bin/env node
// Copyright (c) 2026 CANNBot contributors
// SPDX-License-Identifier: MIT
// See script/LICENSE for the full license text.


import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const packageRoot = fileURLToPath(new URL("../", import.meta.url));
const packageJson = JSON.parse(readFileSync(join(packageRoot, "package.json"), "utf8"));
const archiveName = `${packageJson.name.replace(/^@/, "").replace("/", "-")}-${packageJson.version}.tgz`;
const sandbox = mkdtempSync(join(tmpdir(), "cannbot-package-smoke-"));

function run(command, args, cwd, env = process.env) {
  const result = spawnSync(command, args, { cwd, env, encoding: "utf8" });
  if (result.error || result.status !== 0) {
    const detail = result.error?.message || result.stderr || result.stdout;
    throw new Error(`${command} ${args.join(" ")} failed: ${detail}`);
  }
  return result;
}

try {
  const consumer = join(sandbox, "consumer");
  const target = join(sandbox, "target");
  mkdirSync(consumer, { recursive: true });
  mkdirSync(target, { recursive: true });
  writeFileSync(join(consumer, "package.json"), '{"name":"cannbot-package-smoke","private":true}\n');

  run("npm", ["pack", "--pack-destination", sandbox], packageRoot);
  const archive = join(sandbox, archiveName);
  if (!existsSync(archive)) throw new Error(`npm archive was not created: ${archive}`);
  run("npm", ["install", "--ignore-scripts", "--no-audit", "--no-fund", archive], consumer);

  const executable = join(consumer, "node_modules", ".bin", process.platform === "win32" ? "cannbot.cmd" : "cannbot");
  run(executable, ["install", "model-infer-optimize", "--tool", "dsh", "--target", target], consumer, {
    ...process.env,
    HOME: join(sandbox, "home"),
    XDG_CACHE_HOME: join(sandbox, "cache"),
    CANNBOT_SKIP_DEPENDENCY_REPOS: "1",
  });

  for (const path of [
    join(target, ".dsh", "skills", "model-infer-fusion", "SKILL.md"),
    join(target, ".cannbot", "plugins", "model-infer-optimize", "LICENSE"),
    join(target, ".cannbot", "plugins", "model-infer-optimize", "SKILLS_LICENSE"),
  ]) {
    if (!existsSync(path)) throw new Error(`packaged install is missing: ${path}`);
  }
  run(executable, ["install", "ops-direct-invoke", "--tool", "claude", "--target", target], consumer, {
    ...process.env,
    HOME: join(sandbox, "home"),
    XDG_CACHE_HOME: join(sandbox, "cache"),
    CANNBOT_SKIP_DEPENDENCY_REPOS: "1",
  });
  for (const path of [
    join(target, ".claude", "skills", "repo-requirement", "SKILL.md"),
    join(target, ".claude", "skills", "repo-requirement", "references", "requirement-checklist.md"),
    join(target, ".claude", "skills", "ops-direct-invoke", "templates", "黑盒测试设计.md"),
    join(target, ".claude", "skills", "ops-direct-invoke", "scripts", "generate_workflow_guide.py"),
    join(target, ".claude", "skills", "ops-direct-invoke", "workflows", "ascendc/basic.yaml"),
    join(target, ".claude", "skills", "ops-direct-invoke", "tasks", "ascendc", "白盒测试设计.yaml"),
    join(target, ".claude", "skills", "ops-direct-invoke", "tasks", "ascendc", "算子开发.yaml"),
    join(target, ".claude", "skills", "workflow-orchestrator", "scripts", "orchestrator.py"),
    join(target, ".cannbot", "plugins", "ops-direct-invoke", "agents", "ops-direct-invoke-verifier.md"),
    join(target, ".claude", "skills", "repo-env-check", "SKILL.md"),
    join(target, "CLAUDE.md"),
  ]) {
    if (!existsSync(path)) throw new Error(`packaged harness install is missing: ${path}`);
  }
  const workflowRun = join(sandbox, "workflow-run");
  const entryRoot = join(target, ".claude", "skills", "ops-direct-invoke");
  const guide = join(workflowRun, "workflow-guide.csv");
  run("python3", [join(entryRoot, "scripts", "generate_workflow_guide.py"), "--output", guide], consumer);
  if (!readFileSync(guide, "utf8").includes("ascendc/basic.yaml")) throw new Error("basic workflow missing from guide");
  run("python3", [join(entryRoot, "scripts", "run_workflow.py"),
    "--template", "ascendc/basic.yaml", "--work-dir", workflowRun, "--provider", "claude",
    "--prompt", "package workflow smoke test", "--foreground", "--dry-run"], consumer);
  console.log(`Verified ${archiveName} through the installed cannbot npm bin.`);
} finally {
  rmSync(sandbox, { recursive: true, force: true });
}
