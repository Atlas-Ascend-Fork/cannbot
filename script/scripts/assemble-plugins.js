#!/usr/bin/env node
// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// SPDX-License-Identifier: MIT
// See script/LICENSE for the full license text.

import { rmSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { assemblePlugins, assertSafeAssemblyOutput } from "../lib/plugin-bundle.js";

const repositoryRoot = fileURLToPath(new URL("../../", import.meta.url));
const outputRoot = resolve(process.argv[2] ?? new URL("../dist", import.meta.url).pathname);
assertSafeAssemblyOutput(repositoryRoot, outputRoot);
rmSync(outputRoot, { recursive: true, force: true });
const assembled = assemblePlugins(repositoryRoot, outputRoot);
for (const plugin of assembled) {
  console.error(`assembled ${plugin.parent}/${plugin.pluginId}: ${plugin.skills} Skills`);
}
