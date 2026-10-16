#!/usr/bin/env node
// Copyright (c) 2026 CANNBot contributors
// SPDX-License-Identifier: MIT
// See script/LICENSE for the full license text.


import {
  cpSync,
  existsSync,
  lstatSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  renameSync,
  rmSync,
  symlinkSync,
  writeFileSync,
} from "node:fs";
import { homedir } from "node:os";
import { basename, dirname, join, relative, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { findPluginDirectory, pluginSourceDefinition } from "../lib/plugin-bundle.js";
import { prepareSharedSkills, resolveSkillSource, sourceRevisions } from "../lib/skills-source.js";

const installerPackage = readJson(new URL("../package.json", import.meta.url));
const OPENCODE_PLUGIN_SPEC = `${installerPackage.name}@${installerPackage.version}`;
const BUNDLED_REPOSITORY = fileURLToPath(new URL("../", import.meta.url));
const PACKAGE_CACHEBUSTER = `cannbot-${installerPackage.version.replaceAll(".", "-")}`;
const TOOL_DIRECTORIES = Object.freeze({
  opencode: { configDirs: [".opencode"], defaultConfigDir: ".opencode", skillsDir: [".agents", "skills"] },
  codex: { configDirs: [".codex"], defaultConfigDir: ".codex", skillsDir: [".agents", "skills"] },
  claude: { configDirs: [".claude"], defaultConfigDir: ".claude" },
  trae: { configDirs: [".traecli", ".marscode", ".trae", ".trae-cn"], defaultConfigDir: ".trae" },
  dsh: { configDirs: [".dsh"], defaultConfigDir: ".dsh" },
});
const TOOL_NAMES = Object.keys(TOOL_DIRECTORIES);

function fail(message) {
  console.error(`cannbot: ${message}`);
  process.exit(1);
}

function run(command, args, cwd) {
  const result = spawnSync(command, args, { cwd, stdio: "inherit" });
  if (result.error) fail(`${command} failed: ${result.error.message}`);
  if (result.status !== 0) fail(`${command} exited with status ${result.status}`);
}

function tryRun(command, args, cwd) {
  const result = spawnSync(command, args, { cwd, stdio: "inherit" });
  return !result.error && result.status === 0;
}

function parseArgs(argv) {
  const [command, pluginId, ...rest] = argv;
  if (command !== "install" || !pluginId) {
    fail(`usage: cannbot install <plugin> --tool <${TOOL_NAMES.join("|")}> [--target <dir>] [--source <repository>] [--plugin-dir <dir>] [--override-skills <dir>] [--skills <SHA|path>]`);
  }
  const options = { command, pluginId, target: process.cwd() };
  for (let index = 0; index < rest.length; index += 1) {
    const key = rest[index];
    const value = rest[index + 1];
    if (key === "--plugin-enable") {
      if (!value || !rest[index + 2] || !["on", "off"].includes(rest[index + 2])) {
        fail("--plugin-enable requires <name> <on|off>");
      }
      options.pluginEnable = value;
      options.pluginEnableState = rest[index + 2];
      index += 2;
      continue;
    }
    if (!value) fail(`missing value for ${key}`);
    if (key === "--tool") options.tool = value;
    else if (key === "--target") options.target = resolve(value);
    else if (key === "--source" || key === "--repo") options.source = resolve(value);
    else if (key === "--plugin-dir") options.pluginDir = value;
    else if (key === "--mode") options.mode = value;
    else if (key === "--override-skills") options.overrideSkills = resolve(value);
    else if (key === "--skills") {
      if (options.skills !== undefined || value.startsWith("--")) fail("--skills requires one SHA or local repository path");
      options.skills = value;
    } else fail(`unknown option: ${key}`);
    index += 1;
  }
  if (!TOOL_DIRECTORIES[options.tool]) {
    fail(`--tool must be one of: ${TOOL_NAMES.join(", ")}`);
  }
  return options;
}

function resolvePluginDir(repoPath, pluginId) {
  for (const parent of ["plugins-official", "plugins-community", join("dist", "plugins")]) {
    const candidate = findPluginDirectory(repoPath, parent, pluginId);
    if (candidate
        && existsSync(join(candidate, ".claude-plugin", "plugin.json"))
        && existsSync(join(candidate, "skills"))) return candidate;
  }
  return null;
}

function containsPlugin(repoPath, pluginId) {
  return resolvePluginDir(repoPath, pluginId) !== null;
}

function resolveBundle(override, pluginId, pluginDirectory = null) {
  if (override) {
    const source = pluginSourceDefinition(override, pluginId, pluginDirectory);
    if (source) return source.pluginRoot;
    if (pluginDirectory) return pluginDirectory;
    if (containsPlugin(override, pluginId)) return resolvePluginDir(override, pluginId);
    fail(`invalid CANNBot repository: ${override}`);
  }

  if (pluginDirectory) return pluginDirectory;
  if (containsPlugin(BUNDLED_REPOSITORY, pluginId)) return resolvePluginDir(BUNDLED_REPOSITORY, pluginId);

  fail(`plugin not included in this CANNBot release: ${pluginId}`);
}

function readJson(path) {
  return JSON.parse(readFileSync(path, "utf8"));
}

function writeJsonAtomic(path, value) {
  mkdirSync(dirname(path), { recursive: true });
  const temporary = `${path}.${process.pid}.tmp`;
  writeFileSync(temporary, `${JSON.stringify(value, null, 2)}\n`);
  renameSync(temporary, path);
}

function instructionMarkers(pluginName) {
  return {
    start: `<!-- cannbot:${pluginName}:start -->`,
    end: `<!-- cannbot:${pluginName}:end -->`,
  };
}

function installSkill(source, destination, mode) {
  if (mode === "symlink") {
    if (pathExists(destination)) {
      if (!lstatSync(destination).isSymbolicLink()) {
        fail(`Skill destination already exists and is not a symlink: ${destination}`);
      }
      rmSync(destination, { force: true });
    }
    const linkTarget = relative(dirname(destination), source) || ".";
    symlinkSync(linkTarget, destination, "dir");
    return;
  }
  rmSync(destination, { recursive: true, force: true });
  cpSync(source, destination, { recursive: true, dereference: true });
}

function installPluginAssets(pluginDir, plugin, target, sourceDefinition, skillRewrites, sharedSkills) {
  const relativeRoot = `.cannbot/plugins/${plugin.name}`;
  const destinationRoot = join(target, relativeRoot);
  rmSync(destinationRoot, { recursive: true, force: true });
  mkdirSync(destinationRoot, { recursive: true });
  const assets = { destinationRoot, relativeRoot };
  let installed = false;
  for (const name of ["workflows", "agents", "hooks", "LICENSE", "SKILLS_LICENSE"]) {
    let source = join(pluginDir, name);
    if (name === "SKILLS_LICENSE" && sharedSkills) {
      source = join(sharedSkills.root, "LICENSE");
    } else if (!existsSync(source) && sourceDefinition && name === "LICENSE") {
      source = join(dirname(pluginDir), "LICENSE");
      if (!existsSync(source)) source = resolve(pluginDir, "../..", "LICENSE");
    } else if (!existsSync(source) && sourceDefinition && name === "SKILLS_LICENSE") {
      source = join(sharedSkills?.root ?? resolve(pluginDir, "..", "..", sourceDefinition.skillsRepository), "LICENSE");
    }
    if (!existsSync(source)) continue;
    cpSync(source, join(destinationRoot, name), { recursive: true, dereference: true });
    installed = true;
  }
  if (!installed) {
    rmSync(destinationRoot, { recursive: true, force: true });
    return null;
  }
  const workflows = join(destinationRoot, "workflows");
  if (existsSync(workflows)) rewriteTreeReferences(workflows, assets, skillRewrites);
  return assets;
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

// Agent and workflow bodies address Skill scripts as `skills/<name>/...`, which resolves
// inside the plugin tree but not from a user project, where Skills are installed under the
// tool's own Skills directory. Build one rewrite per Skill that actually resolved, so that
// prose such as "put the file in skills/" is left alone.
function skillPathRewrites(resolvedSkills, skillsDir) {
  if (!skillsDir || !resolvedSkills?.length) return null;
  return resolvedSkills.map((skill) => ({
    pattern: new RegExp(`(^|[\\s"'\`(])skills/${escapeRegExp(skill.name)}/`, "gm"),
    installed: `${join(skillsDir, skill.name)}/`,
  }));
}

function rewritePluginReferences(markdown, assets, skillRewrites) {
  let rewritten = markdown;
  for (const { pattern, installed } of skillRewrites ?? []) {
    rewritten = rewritten.replace(pattern, (match, prefix) => `${prefix}${installed}`);
  }
  if (!assets) return rewritten;
  return rewritten
    .replaceAll("workflows/", `${assets.relativeRoot}/workflows/`)
    .replace(/\]\((?:\.\/)?agents\/([^\s)]+\.md(?:#[^\s)]*)?)\)/g,
      (_, agent) => `](${assets.relativeRoot}/agents/${agent})`);
}

function rewriteTreeReferences(root, assets, skillRewrites) {
  for (const entry of readdirSync(root, { withFileTypes: true })) {
    const path = join(root, entry.name);
    if (entry.isDirectory()) {
      rewriteTreeReferences(path, assets, skillRewrites);
      continue;
    }
    if (!entry.isFile() || !/\.(?:md|txt|sh|py|json|ya?ml)$/i.test(entry.name)) continue;
    const current = readFileSync(path, "utf8");
    const rewritten = rewritePluginReferences(current, assets, skillRewrites);
    if (rewritten !== current) writeFileSync(path, rewritten);
  }
}

function toolConfigDir(target, tool) {
  const layout = TOOL_DIRECTORIES[tool];
  return layout.configDirs
    .map((name) => join(target, name))
    .find((path) => existsSync(path)) ?? join(target, layout.defaultConfigDir);
}

function toolSkillsDir(target, tool) {
  const skillsDir = TOOL_DIRECTORIES[tool].skillsDir;
  if (skillsDir) return join(target, ...skillsDir);
  return join(toolConfigDir(target, tool), "skills");
}

function toolAgentsDir(target, tool) {
  return join(toolConfigDir(target, tool), "agents");
}

function resolveSkills(plugin, pluginDir) {
  const skills = new Map();
  const addSkill = (source) => {
    const skillPath = join(source, "SKILL.md");
    if (!existsSync(skillPath)) fail(`skill is missing SKILL.md: ${source}`);
    const name = readFileSync(skillPath, "utf8").match(/^name:\s*([^\r\n]+)$/m)?.[1]?.trim();
    if (!name) fail(`skill is missing a frontmatter name: ${skillPath}`);
    skills.set(name, source);
  };

  for (const relativeSkill of plugin.skills ?? []) {
    addSkill(resolve(pluginDir, relativeSkill));
  }

  const localSkills = join(pluginDir, "skills");
  if (existsSync(localSkills)) {
    for (const entry of readdirSync(localSkills, { withFileTypes: true })) {
      if (entry.isDirectory() && existsSync(join(localSkills, entry.name, "SKILL.md"))) {
        addSkill(join(localSkills, entry.name));
      }
    }
  }
  for (const entry of readdirSync(pluginDir, { withFileTypes: true })) {
    const source = join(pluginDir, entry.name);
    if (entry.isDirectory() && existsSync(join(source, "SKILL.md"))) addSkill(source);
  }

  return [...skills.entries()].map(([name, source]) => ({ name, source }));
}

function resolveSourceSkills(repositoryRoot, sourceDefinition, sharedSkillsRoot = null) {
  const skills = new Map();
  const addSkill = (source, label) => {
    const skillPath = join(source, "SKILL.md");
    if (!existsSync(skillPath)) fail(`skill is missing SKILL.md: ${source}`);
    const name = readFileSync(skillPath, "utf8").match(/^name:\s*([^\r\n]+)$/m)?.[1]?.trim();
    if (!name) fail(`skill is missing a frontmatter name: ${skillPath}`);
    if (skills.has(name)) fail(`duplicate Skill name in ${label}: ${name}`);
    skills.set(name, source);
  };

  for (const relativeSkill of sourceDefinition.skills) {
    const source = resolveSkillSource(repositoryRoot, sourceDefinition, relativeSkill, sharedSkillsRoot);
    addSkill(source, sourceDefinition.definitionPath);
  }

  // Self-contained workflow skills shipped inside plugins-official/<id>/skills/.
  const selfContainedRoot = join(sourceDefinition.pluginRoot, "skills");
  if (existsSync(selfContainedRoot)) {
    for (const entry of readdirSync(selfContainedRoot, { withFileTypes: true })) {
      if (entry.isDirectory() && existsSync(join(selfContainedRoot, entry.name, "SKILL.md"))) {
        addSkill(join(selfContainedRoot, entry.name), "self-contained skills");
      }
    }
  }

  return [...skills.entries()].map(([name, source]) => ({ name, source }));
}

function parseAgent(markdown) {
  const match = markdown.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n([\s\S]*)$/);
  const frontmatter = match?.[1] ?? "";
  const body = (match?.[2] ?? markdown).trim();
  const name = frontmatter.match(/^name:\s*(.+)$/m)?.[1]?.trim();
  const description = frontmatter.match(/^description:\s*(.+)$/m)?.[1]?.trim();
  if (!name || !description) fail("agent markdown requires name and description frontmatter");
  return { name, description, body };
}

function installAgents(pluginDir, plugin, tool, target, assets, agentsDirOverride, skillRewrites) {
  const agentsDir = agentsDirOverride ?? toolAgentsDir(target, tool);
  mkdirSync(agentsDir, { recursive: true });
  const installed = [];

  for (const relativeAgent of plugin.agents ?? []) {
    const source = resolve(pluginDir, relativeAgent);
    const markdown = rewritePluginReferences(readFileSync(source, "utf8"), assets, skillRewrites);
    if (tool !== "codex") {
      const destination = join(agentsDir, basename(source));
      rmSync(destination, { recursive: true, force: true });
      writeFileSync(destination, markdown);
      installed.push(destination);
      continue;
    }

    const agent = parseAgent(markdown);
    const destination = join(agentsDir, `${agent.name}.toml`);
    const toml = [
      `name = ${JSON.stringify(agent.name)}`,
      `description = ${JSON.stringify(agent.description)}`,
      `developer_instructions = ${JSON.stringify(agent.body)}`,
      "",
    ].join("\n");
    writeFileSync(destination, toml);
    installed.push(destination);
  }
  return installed;
}

function installInstructions(pluginDir, plugin, target, tool, assets, skillRewrites) {
  const source = join(pluginDir, "AGENTS.md");
  const markers = instructionMarkers(plugin.name);
  if (!existsSync(source)) {
    // Retired instructions can remain in either file after switching clients.
    for (const filename of ["AGENTS.md", "CLAUDE.md"]) {
      const path = join(target, filename);
      if (!existsSync(path)) continue;
      const current = readFileSync(path, "utf8");
      const block = new RegExp(`${escapeRegExp(markers.start)}[\\s\\S]*?${escapeRegExp(markers.end)}`, "g");
      const cleaned = current.replace(block, "");
      if (cleaned === current) continue;
      const temporary = `${path}.${process.pid}.tmp`;
      writeFileSync(temporary, cleaned);
      renameSync(temporary, path);
    }
    return null;
  }
  const destination = join(target, tool === "claude" ? "CLAUDE.md" : "AGENTS.md");
  const current = existsSync(destination) ? readFileSync(destination, "utf8") : "";
  const withoutOldBlock = current
    .replace(new RegExp(`${markers.start}[\\s\\S]*?${markers.end}\\s*`, "g"), "")
    .trimEnd();
  const pluginInstructions = rewritePluginReferences(readFileSync(source, "utf8"), assets, skillRewrites).trim();
  const parts = [withoutOldBlock, markers.start, pluginInstructions, markers.end, ""].filter(Boolean);
  const temporary = `${destination}.${process.pid}.tmp`;
  writeFileSync(temporary, parts.join("\n\n"));
  renameSync(temporary, destination);
  return destination;
}

function updateInstallRegistry(path, record) {
  let registry = { schemaVersion: 2, plugins: [] };
  if (existsSync(path)) {
    const existing = readJson(path);
    if (existing?.schemaVersion === 2 && Array.isArray(existing.plugins)) registry = existing;
  }
  const index = registry.plugins.findIndex((plugin) => plugin?.plugin === record.plugin);
  if (index === -1) registry.plugins.push(record);
  else registry.plugins[index] = record;
  registry.plugins.sort((left, right) => left.plugin.localeCompare(right.plugin));
  writeJsonAtomic(path, registry);
}

function replaceStrings(value, replacement) {
  if (typeof value === "string") return value.replaceAll("${CLAUDE_PLUGIN_ROOT}", replacement);
  if (Array.isArray(value)) return value.map((entry) => replaceStrings(entry, replacement));
  if (!value || typeof value !== "object") return value;
  return Object.fromEntries(Object.entries(value).map(([key, entry]) => [key, replaceStrings(entry, replacement)]));
}

function installClaudeHooks(pluginDir, target, tool, assets) {
  const definitionPath = join(pluginDir, "hooks", "hooks.json");
  if (tool !== "claude" || !assets || !existsSync(definitionPath)) return null;

  const configDir = toolConfigDir(target, tool);
  const settingsPath = join(configDir, "settings.json");
  const existing = existsSync(settingsPath) ? readJson(settingsPath) : {};
  const definition = replaceStrings(readJson(definitionPath), assets.destinationRoot);
  existing.hooks ??= {};
  for (const [event, entries] of Object.entries(definition.hooks ?? {})) {
    const current = Array.isArray(existing.hooks[event]) ? existing.hooks[event] : [];
    const known = new Set(current.map((entry) => JSON.stringify(entry)));
    for (const entry of entries) {
      const serialized = JSON.stringify(entry);
      if (!known.has(serialized)) current.push(entry);
      known.add(serialized);
    }
    existing.hooks[event] = current;
  }
  writeJsonAtomic(settingsPath, existing);
  return settingsPath;
}

function pathExists(path) {
  try {
    lstatSync(path);
    return true;
  } catch {
    return false;
  }
}

function repositoryIdentity(url) {
  return url.replace(/^git@gitcode\.com:/, "https://gitcode.com/").replace(/\.git$/, "").replace(/\/$/, "");
}

function exposeDependency(source, destination) {
  if (pathExists(destination)) {
    if (lstatSync(destination).isSymbolicLink()) {
      rmSync(destination, { force: true });
    } else {
      console.warn(`cannbot: dependency path already exists, keeping it unchanged: ${destination}`);
      return false;
    }
  }
  symlinkSync(relative(dirname(destination), source) || ".", destination, "dir");
  return true;
}

function provisionDependencies(pluginDir, plugin, target, skills) {
  const definitionPath = join(pluginDir, "plugin-install.json");
  if (!existsSync(definitionPath)) return [];
  const definition = readJson(definitionPath);
  const dependencies = Array.isArray(definition.dependencies) ? definition.dependencies : [];
  if (process.env.CANNBOT_SKIP_DEPENDENCY_REPOS === "1") {
    if (dependencies.length) console.log("Skipping dependency repositories (CANNBOT_SKIP_DEPENDENCY_REPOS=1)");
    return [];
  }

  const dependencyRoot = join(target, ".cannbot", "dependencies", plugin.name);
  mkdirSync(dependencyRoot, { recursive: true });
  const installed = [];
  for (const dependency of dependencies) {
    if (!dependency?.name || !dependency?.repository || /[\\/]/.test(dependency.name)) {
      fail(`invalid dependency in ${definitionPath}`);
    }
    const destination = join(dependencyRoot, dependency.name);
    let available = existsSync(join(destination, ".git"));
    if (available) {
      const remote = spawnSync("git", ["-C", destination, "remote", "get-url", "origin"], { encoding: "utf8" });
      if (remote.status !== 0 || repositoryIdentity(remote.stdout.trim()) !== repositoryIdentity(dependency.repository)) {
        console.warn(`cannbot: ${dependency.name} has an unexpected origin; update skipped`);
        available = false;
      } else {
        const pulled = tryRun("git", ["-C", destination, "pull", "--ff-only"], target);
        if (!pulled) console.warn(`cannbot: failed to update ${dependency.name}; using the existing checkout`);
      }
    } else if (pathExists(destination)) {
      console.warn(`cannbot: ${dependency.name} exists but is not a Git checkout; clone skipped`);
    } else {
      const args = ["clone", "--depth", "1"];
      if (dependency.ref) args.push("--branch", dependency.ref);
      if (dependency.recursive) args.push("--recurse-submodules", "--shallow-submodules");
      args.push(dependency.repository, destination);
      available = tryRun("git", args, target);
      if (!available) console.warn(`cannbot: failed to clone ${dependency.name}; continuing without it`);
    }
    if (!available) continue;
    if (dependency.recursive) {
      const updated = tryRun("git", ["-C", destination, "submodule", "update", "--init", "--recursive", "--depth", "1"], target);
      if (!updated) console.warn(`cannbot: ${dependency.name} submodule update was incomplete`);
    }
    if (dependency.cleanMarkdownWithSkill) {
      const cleanerSkill = skills.find((skill) => skill.name === dependency.cleanMarkdownWithSkill);
      const cleaner = cleanerSkill
        ? join(cleanerSkill.source, "scripts", "clean_markdown.py")
        : null;
      if (cleaner && existsSync(cleaner)) {
        const cleaned = tryRun("python3", [cleaner, "--dir", destination, "--no-backup", "--quiet"], target);
        if (!cleaned) console.warn(`cannbot: markdown cleanup failed for ${dependency.name}`);
      } else {
        console.warn(`cannbot: cleanup Skill is unavailable: ${dependency.cleanMarkdownWithSkill}`);
      }
    }
    if (dependency.expose) exposeDependency(destination, join(target, dependency.expose));
    installed.push(join(".cannbot", "dependencies", plugin.name, dependency.name));
  }
  return installed;
}

function installCodexPlugin(plugin, skills, target, skillInstallMode) {
  const userHome = resolve(process.env.HOME || homedir());
  const pluginRoot = join(userHome, "plugins", plugin.name);
  const pluginSkills = join(pluginRoot, "skills");
  rmSync(pluginRoot, { recursive: true, force: true });
  mkdirSync(pluginSkills, { recursive: true });
  for (const skill of skills) {
    installSkill(skill.source, join(pluginSkills, skill.name), skillInstallMode);
  }

  const developerName = plugin.author?.name || "CANNBot";
  const displayName = `CANNBot ${plugin.name
    .split("-")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ")}`;
  const manifest = {
    name: plugin.name,
    version: `${plugin.version}+codex.${PACKAGE_CACHEBUSTER}`,
    description: plugin.description,
    author: { name: developerName },
    homepage: plugin.homepage,
    repository: plugin.repository,
    license: plugin.license,
    keywords: [...new Set(["cannbot", ...(plugin.keywords ?? [])])],
    skills: "./skills/",
    interface: {
      displayName,
      shortDescription: plugin.description.slice(0, 120),
      longDescription: plugin.description,
      developerName,
      category: "Productivity",
      capabilities: ["Skills", "Agents"],
      defaultPrompt: [`Use ${plugin.name} for this task.`],
    },
  };
  writeJsonAtomic(join(pluginRoot, ".codex-plugin", "plugin.json"), manifest);

  const marketplacePath = join(userHome, ".agents", "plugins", "marketplace.json");
  const marketplace = existsSync(marketplacePath)
    ? readJson(marketplacePath)
    : { name: "personal", interface: { displayName: "Personal" }, plugins: [] };
  if (!marketplace || typeof marketplace !== "object" || Array.isArray(marketplace)) {
    fail(`invalid Codex marketplace: ${marketplacePath}`);
  }
  if (typeof marketplace.name !== "string" || !marketplace.name) {
    fail(`Codex marketplace is missing a name: ${marketplacePath}`);
  }
  if (!Array.isArray(marketplace.plugins)) {
    fail(`Codex marketplace plugins must be an array: ${marketplacePath}`);
  }
  marketplace.interface ??= { displayName: "Personal" };
  const entry = {
    name: plugin.name,
    source: { source: "local", path: `./plugins/${plugin.name}` },
    policy: { installation: "AVAILABLE", authentication: "ON_INSTALL" },
    category: "Productivity",
  };
  const existingIndex = marketplace.plugins.findIndex((candidate) => candidate?.name === plugin.name);
  if (existingIndex === -1) marketplace.plugins.push(entry);
  else marketplace.plugins[existingIndex] = entry;
  writeJsonAtomic(marketplacePath, marketplace);

  if (process.env.CANNBOT_SKIP_CODEX_PLUGIN_ADD !== "1") {
    run("codex", ["plugin", "add", `${plugin.name}@${marketplace.name}`, "--json"], target);
  }
  return { pluginRoot, marketplacePath, marketplaceName: marketplace.name };
}

function installOpenCodePlugin(target) {
  if (process.env.CANNBOT_SKIP_OPENCODE_PLUGIN_ADD !== "1") {
    run("opencode", ["plugin", OPENCODE_PLUGIN_SPEC], target);
  }
  return { package: OPENCODE_PLUGIN_SPEC };
}

// ---------------------------------------------------------------------------
// Workflow runtime assets (skill-driven workflow plugins).
// These mirror the plugins-official/<id>/init.sh "default workspace" behavior so the
// npm install path produces the same runtime scaffolding (permissions,
// settings.json, per-client permission-guard hooks).
// ---------------------------------------------------------------------------

function parseFrontmatterValue(text, key) {
  const match = text.match(new RegExp(`^${key}:\\s*(.+)$`, "m"));
  return match ? match[1].replace(/^["']|["']$/g, "").trim() : "";
}

function parseFrontmatterList(text, key) {
  const block = text.match(new RegExp(`^${key}:\\s*\\n([\\s\\S]*?)(?=^\\S|^---)|^${key}:\\s*\\[([^\\]]*)\\]`, "m"));
  if (!block) return [];
  const body = block[1] ?? block[2] ?? "";
  return body
    .split(/\n|,/)
    .map((line) => line.replace(/^\s*-\s*/, "").replace(/["']/g, "").trim())
    .filter(Boolean);
}

function readFrontmatter(path) {
  const text = readFileSync(path, "utf8");
  const match = text.match(/^---\r?\n([\s\S]*?)\r?\n---/);
  return { text, frontmatter: match ? match[1] : text };
}

function listPluginSkillDirs(pluginDir) {
  const skillsRoot = join(pluginDir, "skills");
  if (!existsSync(skillsRoot)) return [];
  return readdirSync(skillsRoot, { withFileTypes: true })
    .filter((entry) => entry.isDirectory() && entry.name.startsWith("plugin-"))
    .map((entry) => join(skillsRoot, entry.name))
    .filter((dir) => existsSync(join(dir, "SKILL.md")));
}

function flowStages(pluginDir) {
  const flowSkill = join(pluginDir, "skills", "ops-direct-invoke-workflow", "SKILL.md");
  if (!existsSync(flowSkill)) return null;
  const text = readFileSync(flowSkill, "utf8");
  const matches = [...text.matchAll(/^\|\s*[⛔\s]*([0-9][0-9A-Za-z.]*|CP[0-9A-Za-z.]+)\s*\|/gm)];
  return new Set(matches.map((match) => match[1]));
}

function installPermissions(pluginDir, target) {
  const template = join(pluginDir, "skills", "workflow-agent-permissions", "hooks");
  const destination = join(target, ".cannbot", "permissions");
  if (!existsSync(template)) {
    console.log("  note: workflow-agent-permissions hooks template not found; permissions not generated");
    return null;
  }
  if (existsSync(destination) && readdirSync(destination).length) {
    console.log(`  permissions/ already exists (${readdirSync(destination).length} files), keeping workspace config`);
    return destination;
  }
  mkdirSync(destination, { recursive: true });
  for (const entry of readdirSync(template, { withFileTypes: true })) {
    if (entry.isFile() && entry.name.endsWith(".js")) {
      cpSync(join(template, entry.name), join(destination, entry.name));
    }
  }
  console.log(`  permissions/ generated from workflow-agent-permissions skill (${readdirSync(destination).length} files)`);
  return destination;
}

function installRuntimeSettings(pluginDir, target, options) {
  const pluginDirs = listPluginSkillDirs(pluginDir);
  if (pluginDirs.length === 0) return null;

  const stages = flowStages(pluginDir);
  const records = new Map();
  for (const dir of pluginDirs) {
    const { frontmatter } = readFrontmatter(join(dir, "SKILL.md"));
    const name = parseFrontmatterValue(frontmatter, "name") || basename(dir);
    const hook = parseFrontmatterValue(frontmatter, "workflow-hook");
    const stagesCsv = parseFrontmatterList(frontmatter, "workflow-stages");
    const standalone = parseFrontmatterValue(frontmatter, "standalone") === "true";
    if (!hook) {
      console.warn(`  cannbot: plugin ${name}: frontmatter missing workflow-hook, not registered`);
      continue;
    }
    if (!/^(after|before):[0-9A-Za-z]+(\.[0-9A-Za-z]+)*$/.test(hook)) {
      console.warn(`  cannbot: plugin ${name}: invalid workflow-hook '${hook}', not registered`);
      continue;
    }
    const hookTarget = hook.slice(hook.indexOf(":") + 1);
    if (stages && !stages.has(hookTarget)) {
      console.warn(`  cannbot: plugin ${name}: workflow-hook target '${hookTarget}' not found in base flow table, not registered`);
      continue;
    }
    if (!stagesCsv.length) {
      console.warn(`  cannbot: plugin ${name}: frontmatter missing workflow-stages, not registered`);
      continue;
    }
    records.set(name, { hook, stages: stagesCsv, standalone, enabled: true });
  }

  const settingsPath = join(target, ".cannbot", "settings.json");
  let config = {};
  if (existsSync(settingsPath)) {
    try {
      const parsed = readJson(settingsPath);
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) config = parsed;
    } catch {
      console.warn(`  cannbot: settings.json 解析失败，将重建: ${settingsPath}`);
    }
  }

  const existingPlugins = config.plugins && !Array.isArray(config.plugins) ? config.plugins : {};
  let surveyed = Boolean(config.surveyed);
  let hasNew = false;
  const plugins = {};
  for (const [name, record] of [...records.entries()].sort(([left], [right]) => left.localeCompare(right))) {
    const old = existingPlugins[name];
    const enabled = old?.enabled ?? true;
    if (!old) hasNew = true;
    plugins[name] = { hook: record.hook, stages: record.stages, standalone: record.standalone, enabled };
  }
  if (hasNew) surveyed = false;

  if (options.pluginEnable) {
    if (!plugins[options.pluginEnable]) {
      fail(`--plugin-enable target not registered: ${options.pluginEnable}`);
    }
    plugins[options.pluginEnable].enabled = options.pluginEnableState === "on";
  }

  const mode = options.mode || config.mode || "interactive";
  const next = {
    version: 2,
    mode,
    surveyed,
    plugins,
    updated_at: new Date().toISOString().replace(/\.\d{3}Z$/, "Z"),
  };
  writeJsonAtomic(settingsPath, next);
  console.log(`  settings.json → ${settingsPath} (mode=${next.mode}, ${Object.keys(plugins).length} plugins)`);
  return settingsPath;
}

function registerSettingsHook(settingsPath, hookRef, matcher) {
  let existing = {};
  if (existsSync(settingsPath)) {
    try {
      const parsed = readJson(settingsPath);
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) existing = parsed;
    } catch {
      console.warn(`  cannbot: ${settingsPath} 解析失败，保留原文件未注册 hook`);
      return false;
    }
  }
  existing.hooks ??= {};
  const groups = Array.isArray(existing.hooks.PreToolUse) ? existing.hooks.PreToolUse : [];
  for (const group of groups) {
    const current = group?.matcher ?? "";
    for (const hook of group?.hooks ?? []) {
      const blob = `${hook.command ?? ""} ${(hook.args ?? []).join(" ")}`;
      if (blob.includes("permission-guard.js")) {
        if (current.includes(matcher.split("|").at(-1))) return false;
        group.matcher = `${current}|${matcher.split("|").at(-1)}`;
        writeJsonAtomic(settingsPath, existing);
        return true;
      }
    }
  }
  groups.push({ matcher, hooks: [{ type: "command", command: "node", args: [hookRef] }] });
  existing.hooks.PreToolUse = groups;
  writeJsonAtomic(settingsPath, existing);
  return true;
}

function installNativeHooks(pluginDir, target, tool, assets) {
  const configDir = toolConfigDir(target, tool);
  if (tool === "claude") {
    const source = join(pluginDir, "hooks", "claude", "permission-guard.js");
    if (!existsSync(source)) return null;
    mkdirSync(join(configDir, "hooks"), { recursive: true });
    cpSync(source, join(configDir, "hooks", "permission-guard.js"));
    registerSettingsHook(
      join(configDir, "settings.json"),
      "${CLAUDE_PROJECT_DIR}/.claude/hooks/permission-guard.js",
      "Write|Edit|MultiEdit|NotebookEdit|Question",
    );
      return join(configDir, "settings.json");
  }
  if (tool === "trae") {
    const source = join(pluginDir, "hooks", "trae", "permission-guard.js");
    if (!existsSync(source)) return null;
    mkdirSync(join(configDir, "hooks"), { recursive: true });
    cpSync(source, join(configDir, "hooks", "permission-guard.js"));
    registerSettingsHook(
      join(configDir, "hooks.json"),
      "${CLAUDE_PROJECT_DIR}/.trae/hooks/permission-guard.js",
      "AskUserQuestion",
    );
    return join(configDir, "hooks.json");
  }
  if (tool === "opencode") {
    const source = join(pluginDir, "hooks", "opencode", "permission-guard.js");
    if (!existsSync(source)) return null;
    mkdirSync(join(configDir, "plugin"), { recursive: true });
    cpSync(source, join(configDir, "plugin", "permission-guard.js"));
    return join(configDir, "plugin", "permission-guard.js");
  }
  console.log(`  note: ${tool} does not support project-level permission-guard hooks; role isolation is prompt-constrained`);
  return null;
}

function install(options) {
  const sourceRoot = options.source ?? process.env.CANNBOT_SOURCE_ROOT ?? process.env.CANNBOT_SKILLS_PATH;
  const sourceRepositoryRoot = sourceRoot ? resolve(sourceRoot) : null;
  const selectedDirectory = options.pluginDir
    ? resolve(sourceRepositoryRoot ?? BUNDLED_REPOSITORY, options.pluginDir)
    : null;
  const sourceDefinition = sourceRepositoryRoot
    ? pluginSourceDefinition(sourceRepositoryRoot, options.pluginId, selectedDirectory)
    : null;
  const pluginDir = resolveBundle(sourceRepositoryRoot, options.pluginId, selectedDirectory);
  const manifestPath = join(pluginDir, ".claude-plugin", "plugin.json");
  if (!existsSync(manifestPath)) {
    fail(`plugin not found: ${options.pluginId}`);
  }
  const plugin = readJson(manifestPath);
  if (plugin.name !== options.pluginId) {
    fail(`plugin name mismatch: requested ${options.pluginId}, manifest declares ${plugin.name}`);
  }
  const sharedSkills = prepareSharedSkills(sourceRepositoryRoot, sourceDefinition, options.skills);
  mkdirSync(options.target, { recursive: true });
  const skillInstallMode = sourceDefinition?.skillInstallMode ?? "copy";
  const resolvedSkills = sourceDefinition
    ? resolveSourceSkills(sourceRepositoryRoot, sourceDefinition, sharedSkills?.root)
    : resolveSkills(plugin, pluginDir);
  if (options.overrideSkills) {
    const overridable = /^(repo-|workflow-cp|workflow-doc-templates$)/;
    for (const entry of readdirSync(options.overrideSkills, { withFileTypes: true })) {
      if (!entry.isDirectory()) continue;
      const skill = resolvedSkills.find((candidate) => candidate.name === entry.name);
      if (!skill || !overridable.test(entry.name)) fail(`Skill cannot be overridden: ${entry.name}`);
      const source = join(options.overrideSkills, entry.name);
      const text = readFileSync(join(source, "SKILL.md"), "utf8");
      if (text.match(/^name:\s*([^\r\n]+)$/m)?.[1]?.trim() !== entry.name) fail(`override name mismatch: ${entry.name}`);
      skill.source = source;
    }
  }
  const skillsDir = toolSkillsDir(options.target, options.tool);
  mkdirSync(skillsDir, { recursive: true });
  const installedSkills = [];
  for (const skill of resolvedSkills) {
    const destination = join(skillsDir, skill.name);
    installSkill(skill.source, destination, skillInstallMode);
    installedSkills.push(destination);
  }

  const skillRewrites = skillPathRewrites(resolvedSkills, skillsDir);
  const assets = installPluginAssets(pluginDir, plugin, options.target, sourceDefinition, skillRewrites, sharedSkills);
  const installedAgents = installAgents(pluginDir, plugin, options.tool, options.target, assets,
    undefined, skillRewrites);
  const instructions = installInstructions(pluginDir, plugin, options.target, options.tool, assets,
    skillRewrites);
  const permissionsDir = installPermissions(pluginDir, options.target);
  const runtimeSettings = installRuntimeSettings(pluginDir, options.target, options);
  const nativeHookSettings = installNativeHooks(pluginDir, options.target, options.tool, assets);
  const hookSettings = installClaudeHooks(pluginDir, options.target, options.tool, assets) ?? nativeHookSettings;
  const dependencies = provisionDependencies(pluginDir, plugin, options.target, resolvedSkills);
  const nativePlugin = options.tool === "codex"
    ? installCodexPlugin(plugin, resolvedSkills, options.target, skillInstallMode)
    : options.tool === "opencode"
      ? installOpenCodePlugin(options.target)
      : { initializer: null, discovery: `${toolConfigDir("", options.tool)}/skills` };
  const configDir = toolConfigDir(options.target, options.tool);
  mkdirSync(configDir, { recursive: true });
  const record = {
    plugin: plugin.name,
    pluginVersion: plugin.version,
    sourcePackage: OPENCODE_PLUGIN_SPEC,
    source: sourceRoot ? {
      kind: "repository",
      revisions: sourceRevisions(sourceRepositoryRoot, sharedSkills),
    } : { kind: "package", package: OPENCODE_PLUGIN_SPEC },
    tool: options.tool,
    skillInstallMode,
    skills: installedSkills.map((path) => path.slice(options.target.length + 1)),
    agents: installedAgents.map((path) => path.slice(options.target.length + 1)),
    instructions: instructions?.slice(options.target.length + 1) ?? null,
    assets: assets?.relativeRoot ?? null,
    permissions: permissionsDir?.slice(options.target.length + 1) ?? null,
    settings: runtimeSettings?.slice(options.target.length + 1) ?? null,
    hookSettings: hookSettings?.slice(options.target.length + 1) ?? null,
    dependencies,
    nativePlugin,
    unsupported: existsSync(join(pluginDir, "hooks")) && options.tool === "dsh" ? ["hooks"] : [],
  };
  updateInstallRegistry(join(configDir, "cannbot-plugin.json"), record);

  console.log(`Installed ${plugin.name}@${plugin.version} for ${options.tool}`);
  console.log(`  skills: ${installedSkills.length}`);
  console.log(`  agents: ${installedAgents.length}`);
  console.log(`  target: ${options.target}`);
  if (record.unsupported.length) {
    console.log("  note: this client uses its native project configuration instead of Claude Code hooks");
  }
  if (options.tool === "codex") {
    console.log(`  codex plugin: ${plugin.name}@${nativePlugin.marketplaceName}`);
  } else if (options.tool === "opencode") {
    console.log(`  opencode plugin: ${nativePlugin.package}`);
  } else {
    console.log(`  ${options.tool} skills: ${nativePlugin.discovery}`);
  }
}

try {
  install(parseArgs(process.argv.slice(2)));
} catch (error) {
  fail(error.message);
}
