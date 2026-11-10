// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// Licensed under the CANN Open Software License Agreement Version 2.0.

import { cpSync, existsSync, lstatSync, mkdirSync, mkdtempSync, readFileSync, readdirSync,
  realpathSync, renameSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { basename, dirname, isAbsolute, join, relative, resolve, sep } from "node:path";
import { spawnSync } from "node:child_process";
import { pathToFileURL } from "node:url";
import { prepareDirectInvokeConfig, directInvokeSkillPaths } from "./direct-invoke-config.mjs";

const NAME = "ops-direct-invoke";
const readJson = (path) => JSON.parse(readFileSync(path, "utf8"));
const present = (path) => { try { lstatSync(path); return true; } catch (error) {
  if (error.code === "ENOENT") return false;
  throw error;
} };
const inside = (root, path) => {
  const value = relative(root, path);
  return !isAbsolute(value) && value !== ".." && !value.startsWith(`..${sep}`);
};

function writeJson(path, value) {
  mkdirSync(dirname(path), { recursive: true });
  const temporary = `${path}.${process.pid}.tmp`;
  writeFileSync(temporary, `${JSON.stringify(value, null, 2)}\n`);
  renameSync(temporary, path);
}

function skill(source) {
  const name = readFileSync(join(source, "SKILL.md"), "utf8").match(/^name:\s*([^\r\n]+)$/m)?.[1]?.trim();
  if (!name || !/^[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*$/.test(name)) {
    throw new Error(`invalid Skill name: ${source}`);
  }
  return { name, source };
}

function copy(source, destination, link = false) {
  mkdirSync(dirname(destination), { recursive: true });
  if (link && lstatSync(source).isDirectory()) {
    symlinkSync(process.platform === "win32" ? resolve(source) : relative(dirname(destination), source),
      destination, process.platform === "win32" ? "junction" : "dir");
  } else {
    cpSync(source, destination, { recursive: true, dereference: true,
      filter: (path) => basename(path) !== "__pycache__" && !path.endsWith(".pyc") });
  }
}

function managedSkills(target, paths, selected) {
  const records = paths.registries.filter(existsSync).flatMap((path) => readJson(path).plugins ?? []);
  const owned = new Set(records.filter((record) => record.plugin === NAME)
    .flatMap((record) => record.skills ?? []).map((path) => resolve(target, path)));
  const others = new Set(records.filter((record) => record.plugin !== NAME)
    .flatMap((record) => record.skills ?? []).map((path) => resolve(target, path)));
  const destinations = new Set(selected.map((entry) => join(paths.skillsDir, entry.name)));
  for (const path of destinations) {
    if (present(path) && (!owned.has(path) || others.has(path))) {
      throw new Error(`selected Skill destination is not exclusively managed by ${NAME}: ${path}`);
    }
  }
  return [...owned].filter((path) => dirname(path) === paths.skillsDir
    && !destinations.has(path) && !others.has(path));
}

function noAssetOverlap(destination, sources, replaceLeaf = false) {
  // Replacing a Skill link removes the link itself, not its current target.
  let existing = replaceLeaf ? dirname(destination) : destination;
  while (!existsSync(existing)) existing = dirname(existing);
  const output = resolve(realpathSync(existing), relative(existing, destination));
  for (const source of sources) {
    const input = realpathSync(source);
    if (inside(input, output) || inside(output, input)) {
      throw new Error(`plugin asset source overlaps its destination: ${source}`);
    }
  }
}

export async function initialize({ options, pluginDir, sourceRepositoryRoot, sourceDefinition,
  installerRoot, pathsFor, install }) {
  const config = await prepareDirectInvokeConfig(options);
  const paths = pathsFor(options.target, options.tool);
  const selected = directInvokeSkillPaths(config).map((path) => ({ ...skill(join(pluginDir, path)), assetPath: path }));
  const declaration = join(pluginDir, "skills/custom-skills/env-check", config.platform, "platform.json");
  const { languages } = readJson(declaration);
  if (!Array.isArray(languages) || !languages.length || languages.some((name) => typeof name !== "string" || !name)) {
    throw new Error(`invalid platform language declaration: ${declaration}`);
  }
  if (options.overrideSkills) {
    for (const entry of readdirSync(options.overrideSkills, { withFileTypes: true })) {
      if (!entry.isDirectory()) continue;
      const candidate = selected.find((item) => item.name === entry.name);
      if (!candidate || !/^ops-direct-invoke-(requirement|repo-guide)$/.test(entry.name)) {
        throw new Error(`Skill cannot be overridden: ${entry.name}`);
      }
      const override = skill(join(options.overrideSkills, entry.name));
      if (override.name !== entry.name) throw new Error(`override name mismatch: ${entry.name}`);
      candidate.source = realpathSync(override.source);
      config.skill_overrides ??= {};
      config.skill_overrides[entry.name] = join(paths.skillsDir, entry.name);
    }
  }
  const stale = managedSkills(options.target, paths, selected);
  const { prepareSharedSkills, resolveSkillSource, sourceRevisions } = await import(
    pathToFileURL(join(installerRoot, "lib/skills-source.js")).href);
  const shared = prepareSharedSkills(sourceRepositoryRoot, sourceDefinition, options.skills);
  const external = sourceDefinition
    ? sourceDefinition.skills.map((path) => skill(resolveSkillSource(sourceRepositoryRoot, sourceDefinition, path, shared?.root)))
    : readdirSync(join(pluginDir, "skills"), { withFileTypes: true })
      .filter((entry) => entry.isDirectory() && !["maintain", "orchestrator"].includes(entry.name)
        && existsSync(join(pluginDir, "skills", entry.name, "SKILL.md")))
      .map((entry) => skill(join(pluginDir, "skills", entry.name)));
  if (new Set(external.map((entry) => entry.name)).size !== external.length) {
    throw new Error("duplicate external Skill name");
  }
  const resources = ["skills", "tools", "orchestrations", "docs", "agents", "tests",
    "README.md", "QUICKSTART.md", "plugin-install.json"]
    .map((name) => ({ name, source: join(pluginDir, name) })).filter((item) => existsSync(item.source));
  const selectedSources = selected.map((entry) => entry.source);
  noAssetOverlap(config.asset_root, [...resources.map((entry) => entry.source),
    ...external.map((entry) => entry.source), ...selectedSources]);
  for (const destination of [...selected.map((entry) => join(paths.skillsDir, entry.name)), ...stale]) {
    noAssetOverlap(destination, selectedSources, true);
  }

  // The performance plugin keeps its own installation and runtime; only its target is private.
  const performance = await install({ ...options, pluginId: "ops-perf-optimize", pluginDir: undefined,
    overrideSkills: undefined, target: config.performance_root, registerNative: false,
    skills: shared?.root ?? options.skills });
  const { findPluginDirectory } = await import(pathToFileURL(join(installerRoot, "lib/plugin-bundle.js")).href);
  const repository = sourceRepositoryRoot ?? installerRoot;
  const perfPlugin = ["plugins-official", "plugins-community", "dist/plugins"]
    .map((parent) => findPluginDirectory(repository, parent, "ops-perf-optimize"))
    .find((path) => path !== null);
  if (!perfPlugin) throw new Error("performance plugin source is unavailable");
  const perfAssets = join(config.performance_root, ".cannbot/plugins/ops-perf-optimize");
  copy(join(perfPlugin, "AGENTS.md"), join(perfAssets, "AGENTS.md"));
  for (const path of performance.skills) {
    const entry = skill(join(config.performance_root, path));
    const destination = join(perfAssets, "skills", entry.name);
    rmSync(destination, { recursive: true, force: true });
    copy(realpathSync(entry.source), destination, performance.skillInstallMode === "symlink");
  }
  const runtime = spawnSync("bash", [join(perfPlugin, "installer/install-opmodel.sh"), options.tool, config.performance_root],
    { cwd: config.performance_root, stdio: "inherit" });
  if (runtime.error || runtime.status !== 0) {
    console.warn("cannbot: OpModel setup unavailable; plugin installation will continue");
    if (process.env.CANNBOT_OPMODEL_STRICT === "1") throw new Error("OpModel setup failed in strict mode");
  }

  // Feed a standard four-Skill plugin to the shared installer, then publish private resources.
  const temporary = mkdtempSync(join(tmpdir(), "ops-direct-invoke-install-"));
  const cleanup = () => rmSync(temporary, { recursive: true, force: true });
  process.once("exit", cleanup);
  try {
    const manifest = readJson(join(pluginDir, ".claude-plugin/plugin.json"));
    writeJson(join(temporary, ".claude-plugin/plugin.json"), { ...manifest, agents: [],
      skills: selected.map((entry) => `./skills/${entry.name}`) });
    const definition = readJson(join(pluginDir, "plugin-install.json"));
    delete definition.initializer;
    delete definition.initializeBefore;
    const dependencies = definition.dependencies ?? [];
    writeJson(join(temporary, "plugin-install.json"), { ...definition,
      dependencies: dependencies.map(({ cleanMarkdownWithSkill, ...entry }) => entry) });
    for (const entry of selected) copy(entry.source, join(temporary, "skills", entry.name));
    for (const name of ["LICENSE", "SKILLS_LICENSE"]) {
      const source = join(pluginDir, name);
      const fallback = name === "LICENSE" ? join(dirname(pluginDir), "LICENSE")
        : sourceDefinition ? join(shared?.root ?? resolve(sourceRepositoryRoot, sourceDefinition.skillsRepository), "LICENSE") : null;
      if (existsSync(source)) copy(source, join(temporary, name));
      else if (fallback && existsSync(fallback)) copy(fallback, join(temporary, name));
    }
    const record = await install({ ...options, pluginDir: temporary, skills: undefined,
      overrideSkills: undefined, registerNative: false });
    const linked = sourceDefinition?.skillInstallMode === "symlink";
    for (const entry of resources) {
      const destination = join(config.asset_root, entry.name);
      rmSync(destination, { recursive: true, force: true });
      if (entry.name === "skills" && !sourceDefinition) {
        for (const name of ["maintain", "orchestrator", "custom-skills", "README.md"]) {
          if (existsSync(join(entry.source, name))) copy(join(entry.source, name), join(destination, name));
        }
      } else copy(entry.source, destination, linked);
    }
    mkdirSync(config.external_skills_root, { recursive: true });
    for (const entry of external) copy(entry.source, join(config.external_skills_root, entry.name), linked);
    for (const entry of selected) {
      const destination = join(paths.skillsDir, entry.name);
      const source = linked || config.skill_overrides?.[entry.name]
        ? entry.source : join(config.asset_root, entry.assetPath);
      rmSync(destination, { recursive: true, force: true });
      copy(source, destination, true);
    }
    for (const path of stale) rmSync(path, { recursive: true, force: true });
    for (const dependency of dependencies) {
      const cleaner = external.find((entry) => entry.name === dependency.cleanMarkdownWithSkill);
      const checkout = join(options.target, ".cannbot/dependencies", NAME, dependency.name);
      if (!cleaner || !existsSync(join(checkout, ".git"))) continue;
      const script = join(cleaner.source, "scripts/clean_markdown.py");
      if (!existsSync(script)) continue;
      const result = spawnSync("python3", [script, "--dir", checkout, "--no-backup", "--quiet"],
        { cwd: options.target, stdio: "inherit" });
      if (result.error || result.status !== 0) console.warn(`cannbot: markdown cleanup failed for ${dependency.name}`);
    }
    record.skillInstallMode = "symlink";
    record.assets = relative(options.target, config.asset_root);
    if (sourceDefinition) record.source = { kind: "repository", revisions: sourceRevisions(sourceRepositoryRoot, shared) };
    const registryPath = join(paths.configDir, "cannbot-plugin.json");
    const registry = readJson(registryPath);
    registry.plugins = registry.plugins.map((item) => item.plugin === NAME ? record : item);
    writeJson(registryPath, registry);
    config.performance_registry = join(pathsFor(config.performance_root, options.tool).configDir, "cannbot-plugin.json");
    writeJson(join(options.target, ".cannbot/ops-direct-invoke.json"), config);
    return record;
  } finally {
    cleanup();
    process.removeListener("exit", cleanup);
  }
}
