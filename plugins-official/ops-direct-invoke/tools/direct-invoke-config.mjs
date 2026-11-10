// Copyright (c) 2026 CANNBot contributors
// SPDX-License-Identifier: MIT

import { existsSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { createInterface } from "node:readline/promises";

const choices = (values) => (value) => values.includes(value);
const nonempty = (value) => typeof value === "string" && value.trim().length > 0;
const fields = [
  { key: "platform", prompt: "硬件平台 ascend/kirin", valid: choices(["ascend", "kirin"]) },
  { key: "repo", prompt: "仓库规则 cannbench（仅 Ascend）/common [cannbench]", valid: choices(["cannbench", "common"]), fallback: "cannbench" },
  { key: "chip", prompt: "具体芯片型号（尚未确认请填 unknown）", valid: nonempty },
  { key: "interaction", prompt: "交互偏好 confirm/autonomous [confirm]", valid: choices(["confirm", "autonomous"]), fallback: "confirm" },
  { key: "autonomy", prompt: "允许自主决策的范围 [仅已明确授权范围]", valid: nonempty, fallback: "仅已明确授权范围" },
  { key: "review_points", prompt: "额外人工检视点（逗号分隔；无则留空）", valid: (value) => Array.isArray(value) && value.every(nonempty), parse: (text) => text.split(/[,，]/).map((part) => part.trim()).filter(Boolean) },
];

function answers(config) {
  return { repo: config.repo, platform: config.platform, chip: config.chip,
    interaction: config.preferences?.interaction, autonomy: config.preferences?.autonomy,
    review_points: config.preferences?.review_points };
}

export async function prepareDirectInvokeConfig(options, io = {}) {
  const configPath = join(options.target, ".cannbot", "ops-direct-invoke.json");
  const previous = existsSync(configPath) ? JSON.parse(readFileSync(configPath, "utf8")) : {};
  const configInput = options.initConfig ?? process.env.CANNBOT_DIRECT_INVOKE_CONFIG;
  const supplied = configInput ? JSON.parse(readFileSync(configInput, "utf8")) : {};
  for (const config of [previous, supplied]) {
    if (!config || typeof config !== "object" || Array.isArray(config)) throw new Error("ops-direct-invoke initialization config must be an object");
  }
  const values = answers(previous);
  const explicit = answers(supplied);
  const origins = { ...(previous.sources ?? {}) };
  for (const field of fields) {
    if (explicit[field.key] === undefined) continue;
    if (!field.valid(explicit[field.key])) throw new Error(`invalid initialization value: ${field.key}`);
    values[field.key] = explicit[field.key];
    origins[field.key] = "explicit";
  }
  // A model from another platform is not a confirmed answer for the new platform.
  if (explicit.platform && explicit.platform !== previous.platform && explicit.chip === undefined) delete values.chip;
  const valid = (field, value) => field.valid(value)
    && !(field.key === "repo" && value === "cannbench" && values.platform !== "ascend");
  const conflict = "cannbench 仅支持 Ascend；Kirin 平台请选择 common 仓库规则";
  const pending = fields.filter((field) => !valid(field, values[field.key]));
  if (pending.length && !(io.isTTY ?? (process.stdin.isTTY && process.stdout.isTTY))) {
    if (values.repo === "cannbench" && values.platform === "kirin") throw new Error(conflict);
    throw new Error(`ops-direct-invoke needs initialization answers (${pending.map((field) => field.key).join(", ")}); use an interactive terminal or CANNBOT_DIRECT_INVOKE_CONFIG=<JSON file> (init.sh: --init-config)`);
  }
  let terminal;
  try {
    const ask = io.question ?? ((prompt) => {
      terminal ??= createInterface({ input: process.stdin, output: process.stdout });
      return terminal.question(prompt);
    });
    for (const [index, field] of pending.entries()) {
      const kirinRepo = field.key === "repo" && values.platform === "kirin";
      while (true) {
        const response = await ask(`(${index + 1}/${pending.length}) ${kirinRepo ? "仓库规则 common（cannbench 仅支持 Ascend）[common]" : field.prompt}: `);
        const text = response.trim() || (kirinRepo ? "common" : field.fallback) || "";
        const value = field.parse ? field.parse(text) : text;
        if (!valid(field, value)) {
          (io.log ?? console.log)(kirinRepo && value === "cannbench" ? conflict : `无效回答：${field.key}`);
          continue;
        }
        values[field.key] = value;
        origins[field.key] = "questionnaire";
        break;
      }
    }
  } finally {
    terminal?.close();
  }
  const assetRoot = resolve(options.target, ".cannbot/plugins/ops-direct-invoke");
  return {
    schema_version: 1,
    repo: values.repo,
    platform: values.platform,
    chip: values.chip,
    preferences: { interaction: values.interaction, autonomy: values.autonomy, review_points: values.review_points },
    sources: origins,
    asset_root: assetRoot,
    external_skills_root: join(assetRoot, "external-skills"),
    performance_root: resolve(options.target, ".cannbot/dependencies/ops-direct-invoke/performance"),
    tool: options.tool,
  };
}

export function directInvokeSkillPaths(config) {
  return ["skills/maintain", "skills/orchestrator",
    `skills/custom-skills/requirement/${config.platform}`,
    `skills/custom-skills/repo-guide/${config.repo}`];
}
