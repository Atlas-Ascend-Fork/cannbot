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

import { smokeDirectInvoke } from "../../plugins-official/ops-direct-invoke/tests/install/smoke.mjs";

const packageRoot = fileURLToPath(new URL("../", import.meta.url));
const packageJson = JSON.parse(readFileSync(join(packageRoot, "package.json"), "utf8"));
const archiveName = `${packageJson.name.replace(/^@/, "").replace("/", "-")}-${packageJson.version}.tgz`;
const sandbox = mkdtempSync(join(tmpdir(), "cannbot-package-smoke-"));

function run(command, args, cwd, env = process.env) {
  const result = spawnSync(command, args, { cwd, env, encoding: "utf8", maxBuffer: 32 * 1024 * 1024 });
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
  run(executable, ["install", "model-infer-optimize", "--tool", "codearts", "--target", target], consumer, {
    ...process.env,
    HOME: join(sandbox, "home"),
    XDG_CACHE_HOME: join(sandbox, "cache"),
    CANNBOT_SKIP_DEPENDENCY_REPOS: "1",
  });
  for (const path of [
    join(target, ".codeartsdoer", "skills", "model-infer-fusion", "SKILL.md"),
    join(target, ".codeartsdoer", "agents", "model-infer-analyzer.md"),
    join(target, ".codeartsdoer", "cannbot-plugin.json"),
    join(target, "AGENTS.md"),
  ]) {
    if (!existsSync(path)) throw new Error(`CodeArts packaged install is missing: ${path}`);
  }
  run(executable, ["install", "torch-compile", "--tool", "dsh", "--target", target], consumer, {
    ...process.env,
    HOME: join(sandbox, "home"),
    XDG_CACHE_HOME: join(sandbox, "cache"),
    CANNBOT_SKIP_DEPENDENCY_REPOS: "1",
  });
  const torchRegistry = JSON.parse(readFileSync(join(target, ".dsh", "cannbot-plugin.json"), "utf8"));
  const torchRecord = torchRegistry.plugins.find((plugin) => plugin.plugin === "torch-compile");
  if (torchRecord?.skills.length !== 7 || torchRecord.agents.length !== 1) {
    throw new Error("packaged torch-compile must install seven Skills and one Agent");
  }
  for (const path of [...torchRecord.skills, ...torchRecord.agents]) {
    if (!existsSync(join(target, path))) throw new Error(`packaged torch-compile is missing: ${path}`);
  }
  smokeDirectInvoke({ sandbox, target, consumer, executable, run });
  for (const tool of ["claude", "opencode"]) {
    const workspace = join(sandbox, `autoresearch-${tool}`);
    run(executable, ["install", "autoresearch", "--tool", tool, "--target", workspace], consumer);
    for (const path of [".gitignore", "pyproject.toml", "config.yaml", "quickstart.md", "AGENTS.md",
      "scripts/engine/parse_args.py", "src/op_autoresearch/__init__.py", ".claude/settings.json",
      ".opencode/plugin/autoresearch.js"]) {
      if (!existsSync(join(workspace, path))) throw new Error(`packaged autoresearch is missing: ${path}`);
    }
    const ignore = readFileSync(join(workspace, ".gitignore"), "utf8");
    if (!ignore.includes("ar_tasks/") || !ignore.includes("workspace/")) {
      throw new Error("packaged autoresearch must preserve its runtime Git exclusions");
    }
    run("python3", ["scripts/engine/parse_args.py", "--resume"], workspace, {
      ...process.env, PYTHONPATH: join(workspace, "src"),
    });
  }
  console.log(`Verified ${archiveName} through the installed cannbot npm bin.`);
} finally {
  rmSync(sandbox, { recursive: true, force: true });
}
