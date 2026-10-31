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
  realpathSync,
  renameSync,
  rmSync,
  symlinkSync,
  writeFileSync,
} from "node:fs";
import { homedir } from "node:os";
import { basename, dirname, isAbsolute, join, relative, resolve, sep } from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { findPluginDirectory, pluginSourceDefinition } from "../lib/plugin-bundle.js";
import { isInside, prepareSharedSkills, resolveSkillSource, sourceRevisions } from "../lib/skills-source.js";

const installerPackage = readJson(new URL("../package.json", import.meta.url));
const OPENCODE_PLUGIN_SPEC = `${installerPackage.name}@${installerPackage.version}`;
const BUNDLED_REPOSITORY = fileURLToPath(new URL("../", import.meta.url));
const PACKAGE_CACHEBUSTER = `cannbot-${installerPackage.version.replaceAll(".", "-")}`;
const INSTALL_NAME_PATTERN = /^[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*$/;
const TOOL_DIRECTORIES = Object.freeze({
  opencode: { configDirs: [".opencode"], defaultConfigDir: ".opencode", skillsDir: [".agents", "skills"] },
  codex: { configDirs: [".codex"], defaultConfigDir: ".codex", skillsDir: [".agents", "skills"] },
  claude: { configDirs: [".claude"], defaultConfigDir: ".claude" },
  trae: { configDirs: [".traecli", ".marscode", ".trae", ".trae-cn"], defaultConfigDir: ".trae" },
  dsh: { configDirs: [".dsh"], defaultConfigDir: ".dsh" },
});
const TOOL_NAMES = Object.keys(TOOL_DIRECTORIES);
const LAUNCH_COMMANDS = Object.freeze({
  opencode: "opencode",
  codex: "codex",
  claude: "claude",
  trae: "trae",
  dsh: "dsh",
});
const USAGE_GUIDES = Object.freeze({
  "ops-perf-optimize": `选择使用方式（将 /path/to/... 和目标 SoC 替换为实际配置）：

方式一：自动化调优

  请对 /path/to/operator/ 执行自动化性能调优，目标 SoC 为 Ascend950。
  性能用例：/path/to/cases.csv；功能用例复用性能用例。
  性能对标：同环境原始实现，逐 case 目标比例 1.2x；固定优化 3 轮。
  Python：/path/to/venv/bin/python；CANN：source /path/to/Ascend/cann/bin/setenv.bash。
  中间结果输出到 /path/to/output/。

方式二：交互式调优

  Step 1：性能分析与方案生成

  对 /path/to/operator/，先只采集性能并分析瓶颈、输出方案，完成后暂停，等我选择再实施。
  使用 ops-profiling 采集，结合 ascendc-perf-optimize 和 ascendc-performance-best-practices 分析。
  目标 SoC：Ascend950；用例：/path/to/cases.csv；Python：/path/to/venv/bin/python。
  CANN：source /path/to/Ascend/cann/bin/setenv.bash；输出到 /path/to/output/。

  Step 1 完成后，可自主审视方案，并与 Agent 对话修改；确认方案后再进入 Step 2。

  Step 2：按照生成的方案进行优化

  请对 /path/to/operator/ 做性能优化，采用审阅修改后确认的 <方案编号>。
  沿用已确认的环境、用例、约束和输出目录，实施方案并验证精度与性能。
  输出候选的逐 case 性能对比和精度结果，完成后暂停，等我确认再做全量验收与回集成。

  Step 3：全量验收与原工程回集成

  使用上一步保留的可信实现，完成全量精度与性能验收，并回集成到 /path/to/operator/。
  验证原工程调用方式，输出最终逐 case 性能对比、代码位置、验证报告和复现命令。`,
});

function fail(message) {
  console.error(`cannbot: ${message}`);
  process.exit(1);
}

function validateInstallName(name, label) {
  if (typeof name !== "string" || !INSTALL_NAME_PATTERN.test(name)) {
    fail(`${label} must be a path-safe identifier: ${name}`);
  }
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
  validateInstallName(pluginId, "plugin id");
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

function declaresDependencyAssets(pluginDir) {
  const definitionPath = join(pluginDir, "plugin-install.json");
  if (!existsSync(definitionPath)) return false;
  let definition;
  try {
    definition = readJson(definitionPath);
  } catch {
    return false;
  }
  const dependencies = Array.isArray(definition?.dependencies) ? definition.dependencies : [];
  // A plugin whose Skills arrive through a dependency repository's asset manifest
  // has no local skills/ directory; the assets declaration is what makes it whole.
  return dependencies.some((dependency) => dependency?.assets && typeof dependency.assets === "object");
}

function resolvePluginDir(repoPath, pluginId) {
  for (const parent of ["plugins-official", "plugins-community", join("dist", "plugins")]) {
    const candidate = findPluginDirectory(repoPath, parent, pluginId);
    if (candidate
        && existsSync(join(candidate, ".claude-plugin", "plugin.json"))
        && (existsSync(join(candidate, "skills")) || declaresDependencyAssets(candidate))) return candidate;
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
    const linkTarget = process.platform === "win32"
      ? resolve(source)
      : relative(dirname(destination), source) || ".";
    symlinkSync(linkTarget, destination, process.platform === "win32" ? "junction" : "dir");
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
  for (const name of ["workflows", "scripts", "agents", "hooks", "config.json", "quickstart.md", "LICENSE", "SKILLS_LICENSE"]) {
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
    validateInstallName(name, "Skill name");
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
    validateInstallName(name, "Skill name");
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
  validateInstallName(name, "agent name");
  return { name, description, body };
}

function installAgents(pluginDir, plugin, tool, target, assets, agentsDirOverride, skillRewrites) {
  const agentsDir = agentsDirOverride ?? toolAgentsDir(target, tool);
  mkdirSync(agentsDir, { recursive: true });
  const installed = [];

  for (const relativeAgent of plugin.agents ?? []) {
    const source = resolve(pluginDir, relativeAgent);
    const markdown = rewritePluginReferences(readFileSync(source, "utf8"), assets, skillRewrites);
    const agent = parseAgent(markdown);
    if (tool !== "codex") {
      const destination = join(agentsDir, `${agent.name}.md`);
      rmSync(destination, { recursive: true, force: true });
      writeFileSync(destination, markdown);
      installed.push(destination);
      continue;
    }

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

function installInstructionsFrom(source, pluginName, target, tool, assets, skillRewrites) {
  const markers = instructionMarkers(pluginName);
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

function installInstructions(pluginDir, plugin, target, tool, assets, skillRewrites) {
  return installInstructionsFrom(join(pluginDir, "AGENTS.md"), plugin.name, target, tool, assets, skillRewrites);
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

function installClaudeHooksFrom(hooksDir, target, tool, destinationRoot) {
  const definitionPath = join(hooksDir, "hooks.json");
  if (tool !== "claude" || !existsSync(definitionPath)) return null;

  const configDir = toolConfigDir(target, tool);
  const settingsPath = join(configDir, "settings.json");
  const existing = existsSync(settingsPath) ? readJson(settingsPath) : {};
  const definition = replaceStrings(readJson(definitionPath), destinationRoot);
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

function installClaudeHooks(pluginDir, target, tool, assets) {
  if (!assets) return null;
  return installClaudeHooksFrom(join(pluginDir, "hooks"), target, tool, assets.destinationRoot);
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

function dependencyExposePath(target, exposure, definitionPath) {
  if (typeof exposure !== "string" || isAbsolute(exposure)) {
    fail(`invalid dependency expose path in ${definitionPath}: ${exposure}`);
  }
  const destination = resolve(target, exposure);
  const outside = (root, candidate) => {
    const pathFromRoot = relative(root, candidate);
    return pathFromRoot === ".." || pathFromRoot.startsWith(`..${sep}`) || isAbsolute(pathFromRoot);
  };
  if (destination === resolve(target) || outside(target, destination)) {
    fail(`dependency expose path escapes its project target in ${definitionPath}: ${exposure}`);
  }
  // Follow existing parents, but not the final link: replacing that link is
  // intentional, even when it currently points outside the project.
  let parent = dirname(destination);
  while (!pathExists(parent)) parent = dirname(parent);
  if (outside(realpathSync(target), realpathSync(parent))) {
    fail(`dependency expose parent escapes its project target in ${definitionPath}: ${exposure}`);
  }
  return destination;
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
    if (dependency.required !== undefined && typeof dependency.required !== "boolean") {
      fail(`invalid dependency required flag in ${definitionPath}`);
    }
    if (dependency.requiredPaths !== undefined && !Array.isArray(dependency.requiredPaths)) {
      fail(`invalid dependency requiredPaths in ${definitionPath}`);
    }
    const exposedPath = dependency.expose
      ? dependencyExposePath(target, dependency.expose, definitionPath)
      : null;
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
      if (!available && !dependency.required) console.warn(`cannbot: failed to clone ${dependency.name}; continuing without it`);
    }
    if (!available) {
      if (dependency.required) fail(`required dependency ${dependency.name} is unavailable`);
      continue;
    }
    if (dependency.recursive) {
      const updated = tryRun("git", ["-C", destination, "submodule", "update", "--init", "--recursive", "--depth", "1"], target);
      if (!updated) console.warn(`cannbot: ${dependency.name} submodule update was incomplete`);
      if (!updated && dependency.required) fail(`required dependency ${dependency.name} submodule update failed`);
    }
    for (const requiredPath of dependency.requiredPaths ?? []) {
      const path = dependencyAssetPath(destination, requiredPath, "requiredPaths", definitionPath);
      if (!existsSync(path) || !lstatSync(path).isFile() || lstatSync(path).size === 0) {
        fail(`required dependency ${dependency.name} is missing required file: ${requiredPath}`);
      }
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
    if (exposedPath) exposeDependency(destination, exposedPath);
    installed.push({
      dependency,
      destination,
      definitionPath,
      path: join(".cannbot", "dependencies", plugin.name, dependency.name),
    });
  }
  return installed;
}

// ---------------------------------------------------------------------------
// Dependency repository assets (plugin-install.json "assets" declaration).
// A plugin may ship no Skills of its own and instead declare that a dependency
// repository provides them at install time: the dependency checkout carries a
// plugin-assets.json manifest (or the dependency entry inlines the same keys),
// and the installer links/copies the declared Skills, hooks and AGENTS.md into
// the target project. Inline keys in plugin-install.json override the manifest.
// ---------------------------------------------------------------------------

function dependencyAssetPath(checkout, relativePath, label, definitionPath) {
  if (typeof relativePath !== "string" || !relativePath || isAbsolute(relativePath)) {
    fail(`invalid ${label} in ${definitionPath}: ${relativePath}`);
  }
  const resolved = resolve(checkout, relativePath);
  if (!isInside(checkout, resolved)) {
    fail(`${label} escapes its repository checkout in ${definitionPath}: ${relativePath}`);
  }
  return resolved;
}

function dependencyAssetManifest(dependency, checkout, definitionPath) {
  const assets = dependency.assets;
  if (assets === undefined) return null;
  if (!assets || typeof assets !== "object" || Array.isArray(assets)
      || typeof assets.plugin !== "string" || !assets.plugin) {
    fail(`invalid assets declaration in ${definitionPath}: expected {"plugin": "<dir>"}`);
  }
  const pluginRoot = dependencyAssetPath(checkout, assets.plugin, "assets.plugin", definitionPath);
  let manifest = {};
  const manifestPath = join(pluginRoot, "plugin-assets.json");
  if (existsSync(manifestPath)) manifest = readJson(manifestPath);
  const merged = {
    skills: assets.skills ?? manifest.skills ?? null,
    hooks: assets.hooks ?? manifest.hooks ?? null,
    agentsMd: assets.agentsMd ?? manifest.agentsMd ?? null,
  };
  if (!merged.skills && !merged.hooks && !merged.agentsMd) {
    console.log(`  note: ${dependency.name} declares assets but ${manifestPath} is absent; skipped`);
    return null;
  }
  return { pluginRoot, ...merged };
}

function installDependencySkills(manifest, checkout, target, tool, record, definitionPath) {
  if (!manifest.skills) return;
  const { dir, names } = manifest.skills;
  if (typeof dir !== "string" || !Array.isArray(names)
      || !names.length || names.some((name) => typeof name !== "string" || /[\\/]/.test(name))) {
    fail(`invalid assets.skills in ${definitionPath}: expected {"dir": "<dir>", "names": ["<name>"]}`);
  }
  const skillsRoot = dependencyAssetPath(checkout, dir, "assets.skills.dir", definitionPath);
  const skillsDir = toolSkillsDir(target, tool);
  mkdirSync(skillsDir, { recursive: true });
  for (const name of names) {
    const source = join(skillsRoot, name);
    if (!existsSync(join(source, "SKILL.md"))) {
      fail(`dependency Skill is missing SKILL.md: ${source} (${definitionPath})`);
    }
    installSkill(source, join(skillsDir, name), "symlink");
    record.skills.push(name);
  }
}

function installDependencyHooks(manifest, checkout, target, tool, plugin, record, definitionPath) {
  if (!manifest.hooks) return;
  if (typeof manifest.hooks.dir !== "string") {
    fail(`invalid assets.hooks in ${definitionPath}: expected {"dir": "<dir>"}`);
  }
  const hooksSource = dependencyAssetPath(checkout, manifest.hooks.dir, "assets.hooks.dir", definitionPath);
  if (!existsSync(hooksSource)) {
    fail(`dependency hooks directory is missing: ${hooksSource} (${definitionPath})`);
  }
  // Same contract as installPluginAssets: hooks land under
  // .cannbot/plugins/<plugin>/hooks and Claude registrations are rewritten to it.
  const destinationRoot = join(target, ".cannbot", "plugins", plugin.name);
  mkdirSync(destinationRoot, { recursive: true });
  const destination = join(destinationRoot, "hooks");
  rmSync(destination, { recursive: true, force: true });
  cpSync(hooksSource, destination, { recursive: true, dereference: true });
  installClaudeHooksFrom(hooksSource, target, tool, destinationRoot);
  record.hooks = true;
}

function installDependencyInstructions(manifest, checkout, target, tool, plugin, record, definitionPath) {
  if (!manifest.agentsMd) return;
  const source = dependencyAssetPath(checkout, manifest.agentsMd, "assets.agentsMd", definitionPath);
  if (!existsSync(source)) {
    fail(`dependency AGENTS.md is missing: ${source} (${definitionPath})`);
  }
  const skillsDir = toolSkillsDir(target, tool);
  const skillRewrites = skillPathRewrites(record.skills.map((name) => ({ name })), skillsDir);
  const relativeRoot = `.cannbot/plugins/${plugin.name}`;
  installInstructionsFrom(source, plugin.name, target, tool,
    { destinationRoot: join(target, relativeRoot), relativeRoot }, skillRewrites);
  record.agentsMd = true;
}

function installDependencyAssets(provisioned, plugin, target, tool) {
  const installed = [];
  for (const { dependency, destination, definitionPath } of provisioned) {
    const manifest = dependencyAssetManifest(dependency, destination, definitionPath);
    if (!manifest) continue;
    const record = { dependency: dependency.name, skills: [], hooks: false, agentsMd: false };
    installDependencySkills(manifest, destination, target, tool, record, definitionPath);
    installDependencyHooks(manifest, destination, target, tool, plugin, record, definitionPath);
    installDependencyInstructions(manifest, destination, target, tool, plugin, record, definitionPath);
    installed.push(record);
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

function installKnowledgeConsumer(provisioned, target, tool) {
  const knowledge = provisioned.find((entry) => entry.dependency.name === "cannbot-knowledge");
  if (!knowledge) return false;
  if (process.env.CANNBOT_SKIP_KNOWLEDGE_INDEX === "1") {
    console.log("Skipping knowledge consumer setup (CANNBOT_SKIP_KNOWLEDGE_INDEX=1)");
    return false;
  }
  // The knowledge repository owns its runtime, full-checkout Skill links,
  // project config and index lifecycle. Query itself remains read-only.
  const root = knowledge.destination;
  const installer = join(root, "install.sh");
  const args = [installer, tool, target, "consumer", "--skip-repository-update"];
  if (process.env.CANNBOT_SKIP_KNOWLEDGE_RESOURCES === "1") args.push("--skip-resources");
  const unavailable = (reason) => {
    console.warn(`  knowledge consumer: unavailable (${reason}); knowledgeIndex=pending`);
    console.warn(`  repair: bash ${args.map((arg) => `'${arg.replaceAll("'", "'\\''")}'`).join(" ")}`);
    return false;
  };
  if (!existsSync(installer)) return unavailable(`missing installer: ${installer}`);
  console.log("  knowledge consumer: preparing runtime, resources and search index ...");
  const installed = spawnSync("bash", args, { cwd: root, stdio: "inherit", timeout: 1800000 });
  if (installed.status !== 0) {
    return unavailable(installed.error?.message ?? `installer exit ${installed.status}`);
  }
  try {
    for (const name of ["knowledge-query", "ascendc-api-knowledge-query"]) {
      const canonical = join(target, ".agents", "skills", name);
      if (realpathSync(canonical) !== realpathSync(join(root, ".agents", "skills", name))) {
        return unavailable(`${name} does not link to the knowledge checkout`);
      }
    }
    if (!existsSync(join(target, ".cannbot", "knowledge.env"))) {
      return unavailable("missing .cannbot/knowledge.env");
    }
    const query = join(target, ".agents", "skills", "knowledge-query", "scripts", "knowledge_query.py");
    const discovered = spawnSync(process.env.CANNBOT_PYTHON || "python3", [
      query, "discover", "--json",
    ], { cwd: target, encoding: "utf8", timeout: 120000 });
    if (discovered.status !== 0) {
      return unavailable(discovered.error?.message || discovered.stderr?.trim()
        || discovered.stdout?.trim() || `discover exit ${discovered.status}`);
    }
    const coverage = JSON.parse(discovered.stdout);
    if (coverage.schema_version !== "knowledge-discovery.v1" || !Number.isInteger(coverage.cards)
        || coverage.cards < 0 || realpathSync(coverage.root) !== realpathSync(root)) {
      return unavailable("discover did not confirm the installed knowledge root");
    }
    console.log(`  knowledge index: ready (${coverage.cards} cards; discover verified)`);
    return true;
  } catch (error) {
    return unavailable(error.message);
  }
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
  validateInstallName(plugin.name, "plugin manifest name");
  if (plugin.name !== options.pluginId) {
    fail(`plugin name mismatch: requested ${options.pluginId}, manifest declares ${plugin.name}`);
  }
  // TileLang retains its original agent files and workflow-relative paths.
  // Its installer resolves shared Skills without rewriting the workflow tree.
  if (plugin.name === "tilelang-op-orchestrator") {
    const args = [join(pluginDir, "init.sh"), "project", options.tool, options.target];
    if (options.skills !== undefined) args.push("--skills", options.skills);
    run("bash", args, process.cwd());
    return;
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
  // Resolve required repositories before replacing any live Skills or instructions.
  const provisioned = provisionDependencies(pluginDir, plugin, options.target, resolvedSkills);
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
  const dependencies = provisioned.map((provision) => provision.path);
  const dependencyAssets = installDependencyAssets(provisioned, plugin, options.target, options.tool);
  const nativeSkills = [
    ...resolvedSkills,
    ...dependencyAssets.flatMap((asset) => asset.skills.map((name) => ({
      name,
      source: join(skillsDir, name),
    }))),
  ];
  const nativePlugin = options.tool === "codex"
    ? installCodexPlugin(plugin, nativeSkills, options.target, skillInstallMode)
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
    dependencyAssets,
    nativePlugin,
    unsupported: existsSync(join(pluginDir, "hooks")) && options.tool === "dsh" ? ["hooks"] : [],
  };
  record.knowledgeIndex = installKnowledgeConsumer(provisioned, options.target, options.tool) ? "ready" : "pending";
  updateInstallRegistry(join(configDir, "cannbot-plugin.json"), record);

  console.log(`Installed ${plugin.name}@${plugin.version} for ${options.tool}`);
  console.log(`  skills: ${installedSkills.length}`);
  console.log(`  agents: ${installedAgents.length}`);
  console.log(`  target: ${options.target}`);
  for (const assetRecord of dependencyAssets) {
    console.log(`  dependency assets (${assetRecord.dependency}): skills=${assetRecord.skills.length} hooks=${assetRecord.hooks} agentsMd=${assetRecord.agentsMd}`);
  }
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
  console.log("");
  console.log("Next steps:");
  console.log(`  1. Start the client: ${LAUNCH_COMMANDS[options.tool]}`);
  const usage = USAGE_GUIDES[plugin.name];
  if (usage) {
    console.log("");
    for (const line of usage.split("\n")) {
      console.log(line ? `  ${line}` : "");
    }
  }
  if (assets && existsSync(join(assets.destinationRoot, "quickstart.md"))) {
    console.log("");
    console.log(`  Full guide: ${join(assets.destinationRoot, "quickstart.md")}`);
  }
}

try {
  install(parseArgs(process.argv.slice(2)));
} catch (error) {
  fail(error.message);
}
