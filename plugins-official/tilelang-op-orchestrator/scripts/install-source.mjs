#!/usr/bin/env node
// ----------------------------------------------------------------------------------------------------------
// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.
// ----------------------------------------------------------------------------------------------------------
import { existsSync, mkdirSync, readFileSync, realpathSync, writeFileSync } from "node:fs";
import { basename, dirname, join, relative, resolve } from "node:path";
import { pathToFileURL } from "node:url";

const [operation, directory, ...args] = process.argv.slice(2);
const pluginRoot = realpathSync(directory);
const manifest = JSON.parse(readFileSync(join(pluginRoot, ".claude-plugin", "plugin.json"), "utf8"));
const repository = resolve(pluginRoot, "../..");
const readJson = (path) => JSON.parse(readFileSync(path, "utf8"));
const writeJson = (path, value) => {
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, `${JSON.stringify(value, null, 2)}\n`);
};

if (operation === "resolve") {
  const requested = args[0] || undefined;
  const library = join(repository, "script", "lib", "skills-source.js");
  let state;
  if (existsSync(library) && existsSync(join(pluginRoot, "plugin-sources.json"))) {
    const definition = readJson(join(pluginRoot, "plugin-sources.json"));
    const { prepareSharedSkills, sourceRevisions } = await import(pathToFileURL(library));
    const shared = prepareSharedSkills(repository, definition, requested);
    state = { root: join(shared.root, "ops"), source: { kind: "repository", revisions: sourceRevisions(repository, shared) } };
    for (const skill of definition.skills) {
      if (!existsSync(join(shared.root, skill, "SKILL.md"))) throw new Error(`missing shared Skill: ${skill}`);
    }
  } else {
    if (requested !== undefined) throw new Error("--skills is only available for source installations");
    state = { root: join(pluginRoot, "skills"), source: { kind: "package" } };
    for (const skill of manifest.skills ?? []) {
      if (!existsSync(join(pluginRoot, skill, "SKILL.md"))) throw new Error(`missing bundled Skill: ${skill}`);
    }
  }
  console.log(JSON.stringify(state));
} else if (operation === "instructions") {
  const { installInstructions } = await import("./install-instructions.mjs");
  installInstructions(pluginRoot, args[0], args[1]);
} else if (operation === "record") {
  const [tool, target, configRoot, level] = args;
  const state = JSON.parse(process.env.CANNBOT_TILELANG_SKILL_STATE);
  const legacy = readJson(join(configRoot, "cannbot-manifest.json"));
  const skillNames = new Set((manifest.skills ?? readJson(join(pluginRoot, "plugin-sources.json")).skills).map((path) => basename(path)));
  const agentNames = new Set(manifest.agents.map((path) => basename(path, ".md")));
  const registryPath = join(configRoot, "cannbot-plugin.json");
  const registry = existsSync(registryPath) ? readJson(registryPath) : { schemaVersion: 2, plugins: [] };
  const record = {
    plugin: manifest.name,
    pluginVersion: manifest.version,
    source: state.source,
    tool,
    skillInstallMode: "symlink",
    skills: legacy.installed_skills.filter((name) => skillNames.has(name)).map((name) => relative(target, join(legacy.skills_dir, name))),
    agents: legacy.installed_agents.filter((name) => agentNames.has(basename(name, tool === "codex" ? ".toml" : ".md")))
      .map((name) => relative(target, join(legacy.agents_dir, name))),
    instructions: level === "global" ? join(configRoot, tool === "claude" ? "CLAUDE.md" : "AGENTS.md")
      : tool === "claude" ? "CLAUDE.md" : "AGENTS.md",
    assets: null,
    dependencies: [],
  };
  registry.plugins = registry.plugins.filter((entry) => entry.plugin !== manifest.name);
  registry.plugins.push(record);
  writeJson(registryPath, registry);
  if (tool === "claude") {
    const settingsPath = join(configRoot, "settings.json");
    const settings = existsSync(settingsPath) ? readJson(settingsPath) : {};
    const hooks = readJson(join(pluginRoot, "hooks", "hooks.json")).hooks;
    settings.hooks ??= {};
    const shellQuote = (value) => `'${value.replaceAll("'", "'\\''")}'`;
    for (const [event, entries] of Object.entries(hooks)) {
      const configured = entries.map((entry) => ({ ...entry, hooks: entry.hooks.map((hook) => ({
        ...hook,
        command: `env CLAUDE_PLUGIN_ROOT=${shellQuote(pluginRoot)} ${hook.command.replaceAll("${CLAUDE_PLUGIN_ROOT}", pluginRoot)}`,
      })) }));
      const existing = settings.hooks[event] ?? [];
      const keys = new Set(existing.map((entry) => JSON.stringify(entry)));
      settings.hooks[event] = [...existing, ...configured.filter((entry) => !keys.has(JSON.stringify(entry)))];
    }
    writeJson(settingsPath, settings);
  }
} else {
  throw new Error(`unknown installation operation: ${operation}`);
}
