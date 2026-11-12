// Copyright (c) 2026 CANNBot contributors
// SPDX-License-Identifier: MIT

import { existsSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { BACK, QuestionnaireScreen, selectChoice, textQuestion } from "./terminal-select.mjs";

const choices = (values) => (value) => values.includes(value);
const nonempty = (value) => typeof value === "string" && value.trim().length > 0;
// Model names verified against CANN 9.3.0 data/platform_config/*.ini.
// Menus list at most three models per series; the rest are covered by "等".
const chipSeries = {
  ascend: [
    ["ascend950", "Ascend950 系列（950PR/950DT）"],
    ["ascend910", "Ascend910 系列（910_9391/910B/910A 等）"],
  ],
  kirin: [["kirin9030", "Kirin9030 系列"], ["kirinx90", "KirinX90 系列"]],
};
const interactionScopes = {
  autonomous: "在当前任务和已有修改权限内自主选择方案、实现及验证方式，不主动请求确认；无法确定的必要输入如实记录为阻塞。",
  confirm: "常规实现与验证自主推进；仅在需求分析等必要确认点，以及需求、交付标准或权限发生实质变化时询问。",
  supervised: "在已有明确约定内执行；所有不确定项及时通过问卷询问用户，不自行作出尚未确认的取舍。",
};
const fields = [
  { key: "platform", prompt: "您在哪种硬件平台上进行开发？", labels: ["昇腾(Ascend)系列", "麒麟(Kirin)系列"],
    options: ["ascend", "kirin"], valid: choices(["ascend", "kirin"]) },
  { key: "chip", prompt: "您开发的芯片型号或系列是？", valid: nonempty },
  { key: "repo", prompt: "您希望使用哪种工程框架？", labels: ["通用框架", "cannbench评测框架"],
    options: ["common", "cannbench"], valid: choices(["common", "cannbench"]) },
  { key: "language", prompt: "您使用哪种开发语言？",
    labels: ["AscendC", "CANNBot-DSL", "暂不确定"],
    options: ["ascendc", "dsl", "unspecified"], valid: choices(["ascendc", "dsl", "unspecified"]) },
  { key: "interaction", prompt: "您的交互偏好是？", initial: 1,
    labels: ["静默运行，你替我做决定", "重要节点和我确认（推荐）", "我监督所有细节"],
    options: ["autonomous", "confirm", "supervised"], valid: choices(Object.keys(interactionScopes)) },
];

function answers(config) {
  return { repo: config.repo, platform: config.platform, chip: config.chip, language: config.language,
    interaction: config.preferences?.interaction };
}

// Rebuild the questionnaire's question/answer lines for install pages and the final summary.
export function questionnaireSummary(config) {
  const field = (key) => fields.find((candidate) => candidate.key === key);
  const label = (key, value) => {
    const candidate = field(key);
    const index = candidate?.options?.indexOf(value) ?? -1;
    return index >= 0 ? candidate.labels[index] : value;
  };
  const question = (key, value) => `${field(key).prompt.replace(/[？?]$/, "：")}${value}`;
  const chip = (() => {
    if (!config.chip) return null;
    if (config.chip === "unknown") return "暂不确定";
    const series = (chipSeries[config.platform] ?? []).find(([value]) => value === config.chip);
    return series ? series[1] : config.chip;
  })();
  const interaction = config.preferences?.interaction;
  return [
    config.platform && question("platform", label("platform", config.platform)),
    chip && question("chip", chip),
    config.repo && question("repo", label("repo", config.repo)),
    config.language && question("language", label("language", config.language)),
    interaction && question("interaction", label("interaction", interaction)),
  ].filter(Boolean);
}

function supportsLanguage(platform, language) {
  if (language === "unspecified") return true;
  if (!["ascend", "kirin"].includes(platform)) return false;
  const declaration = new URL(`../skills/custom-skills/env-check/${platform}/platform.json`, import.meta.url);
  return JSON.parse(readFileSync(declaration, "utf8")).languages.includes(language);
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
  if (explicit.chip === "") explicit.chip = "unknown";
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
    && !(field.key === "repo" && value === "cannbench" && values.platform !== "ascend")
    && (field.key !== "language" || supportsLanguage(values.platform, value));
  const conflict = "cannbench 仅支持 Ascend；Kirin 平台请选择 common 仓库规则";
  const isTTY = io.isTTY ?? (process.stdin.isTTY && process.stdout.isTTY);
  // A reinstall on an existing target asks every applicable question again.
  const refresh = options.refresh === true && isTTY;
  const asked = new Set();
  const backStack = [];
  const prefill = new Map();
  if (!isTTY && values.chip === undefined) {
    values.chip = "unknown";
    origins.chip = "default";
  }
  if (!isTTY && values.language === undefined) {
    values.language = "unspecified";
    origins.language = "default";
  }
  const pendingQuestions = () => {
    const pending = [];
    for (const candidate of fields) {
      if (refresh ? asked.has(candidate.key) : valid(candidate, values[candidate.key])) continue;
      let field = candidate;
      // Do not filter dependent menus until the platform has been chosen.
      if (["ascend", "kirin"].includes(values.platform)) {
        if (field.key === "chip") field = {
          ...field,
          options: [...chipSeries[values.platform].map(([value]) => value), "other", "unknown"],
          labels: [...chipSeries[values.platform].map(([, label]) => label), "其他（自行输入）", "暂不确定"],
        };
        if (field.key === "language") {
          // "暂不确定" is a fallback, not an alternative: a platform with a single
          // supported language adopts it without asking.
          const supported = field.options.filter((value) => value !== "unspecified" && valid(field, value));
          if (supported.length === 1 && (isTTY || explicit[field.key] === undefined)) {
            values[field.key] = supported[0];
            origins[field.key] = "inferred";
            continue;
          }
        }
        const available = field.options?.map((value, index) => ({ value, label: field.labels[index] }))
          .filter(({ value }) => valid(field, value));
        if (available) field = { ...field, options: available.map(({ value }) => value), labels: available.map(({ label }) => label) };
        if (field.options?.length === 1 && (isTTY || explicit[field.key] === undefined)) {
          values[field.key] = field.options[0];
          origins[field.key] = "inferred";
          continue;
        }
      }
      if (refresh && field.options) {
        const saved = field.options.indexOf(values[field.key]);
        const fallback = field.key === "chip" ? field.options.indexOf("other") : (field.initial ?? 0);
        field = { ...field, initial: saved >= 0 ? saved : fallback };
      }
      const remembered = prefill.get(field.key);
      if (remembered !== undefined && field.options) {
        const index = field.options.indexOf(remembered);
        const fallback = field.key === "chip" ? field.options.indexOf("other") : (field.initial ?? 0);
        field = { ...field, initial: index >= 0 ? index : fallback };
      }
      pending.push(field);
    }
    return pending;
  };
  let pending = pendingQuestions();
  if (pending.length && !isTTY) {
    if (values.repo === "cannbench" && values.platform === "kirin") throw new Error(conflict);
    if (values.language && !supportsLanguage(values.platform, values.language)) {
      throw new Error(`${values.platform} 不支持开发语言 ${values.language}，请按平台支持范围选择，或使用 unspecified 暂不指定。`);
    }
    throw new Error(`ops-direct-invoke needs initialization answers (${pending.map((field) => field.key).join(", ")}); use an interactive terminal or CANNBOT_DIRECT_INVOKE_CONFIG=<JSON file> (init.sh: --init-config)`);
  }
  const prelude = options.prelude && typeof options.prelude.label === "string" ? options.prelude : null;
  const screen = pending.length && !io.question ? new QuestionnaireScreen(io.output ?? process.stdout) : null;
  if (screen && prelude) {
    screen.answer(prelude.prompt, screen.display ? `\x1b[1;32m${prelude.label}\x1b[0m` : prelude.label);
  }
  const total = pending.length;
  const progress = (fraction) => { io.progress?.(fraction); };
  let answered = 0;
  try {
    // Percent of the questions that actually remain, so inferred fields do not
    // make the counter jump. Color the parentheses only on an interactive screen.
    const share = () => (answered + pending.length ? answered / (answered + pending.length) : 1);
    const prefix = (percent) => screen?.display
      ? `\x1b[32m(${percent}%)\x1b[0m` : `(${percent}%)`;
    const labeled = (prompt) => total ? `${prefix(Math.round(share() * 100))} ${prompt}` : prompt;
    const defaultAsk = (prompt, field) => field.options
      ? selectChoice(prompt, field.labels, { initial: field.initial ?? 0, screen, allowBack: field.allowBack,
        input: io.input, output: io.output })
      : textQuestion(prompt, { screen, initial: field.defaultText, input: io.input, output: io.output });
    const ask = (prompt, field) => (io.question ?? defaultAsk)(labeled(prompt), field);
    if (total) progress(0);
    while (pending.length) {
      const field = pending[0];
      while (true) {
        const response = await ask(field.prompt, { ...field, allowBack: backStack.length > 0 });
        if (response === BACK) {
          const previous = backStack.pop();
          if (!previous) continue;
          asked.delete(previous.key);
          delete values[previous.key];
          delete origins[previous.key];
          prefill.set(previous.key, previous.value);
          answered = Math.max(0, answered - 1);
          screen?.popAnswer();
          pending = pendingQuestions();
          progress(share());
          break;
        }
        const text = response.trim();
        let value = field.options
          ? (/^[1-9]$/.test(text) ? field.options[Number(text) - 1] : undefined)
          : text || "unknown";
        if (field.key === "chip" && value === "other") {
          // Keep a previously typed model as an editable default.
          const remembered = values.chip ?? prefill.get(field.key);
          const custom = remembered && field.options && !field.options.includes(remembered);
          let prompt = "请输入具体芯片型号？";
          let defaultText = custom ? remembered : "";
          while (true) {
            value = (await ask(prompt, { defaultText })).trim();
            defaultText = "";
            if (nonempty(value)) break;
            prompt = "芯片型号不能为空，请输入具体芯片型号？";
          }
        }
        if (!valid(field, value)) {
          (io.log ?? console.log)(`输入无效，请输入一个数字（${field.options.map((_, option) => option + 1).join(" 或 ")}）。`);
          continue;
        }
        values[field.key] = value;
        origins[field.key] = "questionnaire";
        const label = field.labels?.[field.options.indexOf(value)] ?? value;
        screen?.answer(field.prompt, screen.display ? `\x1b[1;32m${label}\x1b[0m` : label);
        backStack.push({ key: field.key, value, label });
        prefill.delete(field.key);
        break;
      }
      asked.add(field.key);
      answered += 1;
      pending = pendingQuestions();
      progress(share());
    }
  } finally {
    screen?.close();
  }
  // Keep existing explicit review gates, but do not ask users to configure them during init.
  const reviewPoints = supplied.preferences?.review_points ?? previous.preferences?.review_points ?? [];
  if (!Array.isArray(reviewPoints) || !reviewPoints.every(nonempty)) throw new Error("invalid initialization value: review_points");
  origins.autonomy = "interaction";
  const assetRoot = resolve(options.target, ".cannbot/plugins/ops-direct-invoke");
  return {
    schema_version: 1,
    repo: values.repo,
    platform: values.platform,
    chip: values.chip,
    language: values.language,
    preferences: { interaction: values.interaction, autonomy: interactionScopes[values.interaction], review_points: reviewPoints },
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
