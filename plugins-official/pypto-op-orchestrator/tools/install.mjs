// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// SPDX-License-Identifier: CANN-2.0

import { spawnSync } from "node:child_process";
import { rmdirSync } from "node:fs";
import { join } from "node:path";

export async function initialize({ options, install }) {
  if (options.tool === "opencode" && options.registerNative !== false
      && process.env.CANNBOT_SKIP_OPENCODE_PLUGIN_ADD !== "1") {
    const result = spawnSync("opencode", ["--version"], { encoding: "utf8" });
    if (result.error) throw new Error(`opencode failed: ${result.error.message}`);
    if (result.status !== 0) throw new Error(`opencode --version exited with status ${result.status}`);
    const version = result.stdout.trim().match(/^(?:opencode\s+)?v?([1-9]\d*)\.\d+\.\d+(?:-[\w.-]+)?(?:\+[\w.-]+)?$/i);
    if (!version) throw new Error("cannot determine OpenCode version; check opencode --version");
    if (version[1] !== "1") {
      throw new Error(`pypto-op-orchestrator requires OpenCode 1.x; OpenCode ${version[1]}.x is not supported.`);
    }
  }
  const record = await install(options);
  // The shared installer creates this directory for any plugin-install.json.
  // This plugin declares no dependencies; remove only empty directories.
  const dependencies = join(options.target, ".cannbot", "dependencies");
  for (const path of [join(dependencies, options.pluginId), dependencies]) {
    try {
      rmdirSync(path);
    } catch (error) {
      if (error.code !== "ENOENT" && error.code !== "ENOTEMPTY") throw error;
    }
  }
  return record;
}
