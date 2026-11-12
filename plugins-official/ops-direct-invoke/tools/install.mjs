// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// Licensed under the CANN Open Software License Agreement Version 2.0.

import { cpSync, existsSync, lstatSync, mkdirSync, mkdtempSync, readFileSync, readdirSync,
  realpathSync, renameSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { basename, dirname, isAbsolute, join, relative, resolve, sep } from "node:path";
import { spawnSync } from "node:child_process";
import { pathToFileURL } from "node:url";
import { prepareDirectInvokeConfig, directInvokeSkillPaths } from "./direct-invoke-config.mjs";
import { selectChoice } from "./terminal-select.mjs";

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

const repositoryIdentity = (url) => url.replace(/^git@gitcode\.com:/, "https://gitcode.com/")
  .replace(/\.git$/, "").replace(/\/$/, "");

// Reuse repositories the performance plugin already prepared instead of cloning them twice.
export function linkSharedDependencies(source, target, dependencies) {
  for (const dependency of dependencies) {
    const prepared = join(source, dependency.name);
    if (!dependency?.name || !dependency?.repository || !existsSync(join(prepared, ".git"))) continue;
    const remote = spawnSync("git", ["-C", prepared, "remote", "get-url", "origin"], { encoding: "utf8" });
    if (remote.status !== 0
      || repositoryIdentity(remote.stdout.trim()) !== repositoryIdentity(dependency.repository)) continue;
    const destination = join(target, dependency.name);
    if (present(destination)) continue;
    mkdirSync(dirname(destination), { recursive: true });
    symlinkSync(process.platform === "win32" ? resolve(prepared) : relative(dirname(destination), prepared),
      destination, process.platform === "win32" ? "junction" : "dir");
  }
}

// A non-empty target is updated in place unless the user chooses a clean reinstall.
export async function resolveTargetMode(target, { input = process.stdin, output = process.stdout } = {}) {
  if (!existsSync(target) || !lstatSync(target).isDirectory() || !readdirSync(target).length) return "fresh";
  if (!input.isTTY || !output.isTTY) return "fresh";
  const choice = await selectChoice(`目标目录 ${target} 已有内容，请选择处理方式？`,
    ["更新现有工作流组件", "清空目录后重新安装（删除目录内所有内容）"], { input, output, initial: 0 });
  if (choice !== "2") return "update";
  for (const entry of readdirSync(target)) rmSync(join(target, entry), { recursive: true, force: true });
  return "clean";
}

// DSH reaches workflows only through the CANNBot DSH plugin, which lives in a user profile.
export async function confirmDshPlugin({ tool, installer, profile }, {
  input = process.stdin, output = process.stdout, env = process.env } = {}) {
  if (tool !== "dsh") return false;
  const forced = env.CANNBOT_INSTALL_DSH_PLUGIN;
  if (forced === "1") return true;
  if (forced === "0") return false;
  const paint = (line) => (output.isTTY ? `\x1b[32m${line}\x1b[0m` : line);
  const hint = [
    "选择 DSH 时，需要安装 CANNBot DSH 插件。",
    paint("该功能需要安装在当前指定目录之外，用户全局的 DSH 环境里。"),
    "安装完成后需要重启 DSH。",
  ];
  const say = (line) => output.write(`${line}\n`);
  if (!existsSync(installer)) {
    say(`提示：${hint.join("")} 可执行：dsh plugin --profile ${profile} add cannbot-dsh@latest`);
    return false;
  }
  if (!input.isTTY || !output.isTTY) {
    say(`提示：${hint.join("")} 可执行：bash ${installer} --profile ${profile}`);
    return false;
  }
  const answer = await selectChoice([...hint, "是否继续安装？"].join("\n"),
    ["继续", "取消"], { input, output, initial: 0 });
  if (answer === "1") return true;
  say(`已取消安装 CANNBot DSH 插件；需要时执行 bash ${installer} --profile ${profile}，然后重启 DSH。`);
  return false;
}

export async function initialize({ options, pluginDir, sourceRepositoryRoot, sourceDefinition,
  installerRoot, pathsFor, install }) {
  const mode = await resolveTargetMode(options.target);
  const repositoryRoot = sourceRepositoryRoot ?? dirname(dirname(pluginDir));
  const dshProfile = process.env.DSH_PROFILE || "web";
  const dshInstaller = join(repositoryRoot, "dsh", "install.sh");
  const dshWanted = await confirmDshPlugin({ tool: options.tool, installer: dshInstaller, profile: dshProfile });
  const config = await prepareDirectInvokeConfig({ ...options, refresh: mode === "update" });
  // The questionnaire has closed its screen; report coarse install progress next.
  const steps = 6 + (dshWanted ? 1 : 0);
  let step = 0;
  const green = process.stdout.isTTY ? (line) => `\x1b[32m${line}\x1b[0m` : (line) => line;
  const report = (label) => console.log(green(`(${Math.round((step++ * 100) / steps)}%) ${label}`));
  report("准备平台声明、公共 Skills 与定制覆盖");
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
  report("安装性能优化插件 ops-perf-optimize");
  const performance = await install({ ...options, pluginId: "ops-perf-optimize", pluginDir: undefined,
    overrideSkills: undefined, target: config.performance_root, registerNative: false, summary: false,
    skills: shared?.root ?? options.skills });
  report("准备性能插件资源与 OpModel 运行时");
  const { findPluginDirectory } = await import(pathToFileURL(join(installerRoot, "lib/plugin-bundle.js")).href);
  const repository = sourceRepositoryRoot ?? installerRoot;
  const perfPlugin = ["plugins-official", "plugins-community", "dist/plugins"]
    .map((parent) => findPluginDirectory(repository, parent, "ops-perf-optimize"))
    .find((path) => path !== null);
  if (!perfPlugin) throw new Error("performance plugin source is unavailable");
  const perfDefinitionPath = join(perfPlugin, "plugin-install.json");
  const perfDependencyNames = new Set((existsSync(perfDefinitionPath)
    ? (readJson(perfDefinitionPath).dependencies ?? []) : []).map((entry) => entry.name));
  const perfAssets = join(config.performance_root, ".cannbot/plugins/ops-perf-optimize");
  copy(join(perfPlugin, "AGENTS.md"), join(perfAssets, "AGENTS.md"));
  for (const path of performance.skills) {
    const entry = skill(join(config.performance_root, path));
    const destination = join(perfAssets, "skills", entry.name);
    rmSync(destination, { recursive: true, force: true });
    copy(realpathSync(entry.source), destination, performance.skillInstallMode === "symlink");
  }
  // pip maps PIP_NO_WARN_CONFLICTS to --no-warn-conflicts (a store_false option),
  // so 0 skips its post-install scan. That scan reports CANN packages leaked via
  // PYTHONPATH as broken; the wheel itself is unaffected.
  const runtime = spawnSync("bash", [join(perfPlugin, "installer/install-opmodel.sh"), options.tool, config.performance_root],
    { cwd: config.performance_root, stdio: "inherit", env: { ...process.env, PIP_NO_WARN_CONFLICTS: "0" } });
  if (runtime.error || runtime.status !== 0) {
    console.warn("cannbot: OpModel setup unavailable; plugin installation will continue");
    if (process.env.CANNBOT_OPMODEL_STRICT === "1") throw new Error("OpModel setup failed in strict mode");
  }

  // Feed a standard four-Skill plugin to the shared installer, then publish private resources.
  report("安装直调插件、依赖仓库与客户端配置");
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
    linkSharedDependencies(join(config.performance_root, ".cannbot/dependencies", performance.plugin),
      join(options.target, ".cannbot/dependencies", NAME),
      dependencies.filter((entry) => perfDependencyNames.has(entry.name)));
    const record = await install({ ...options, pluginDir: temporary, skills: undefined,
      overrideSkills: undefined, registerNative: false, summary: false });
    const linked = sourceDefinition?.skillInstallMode === "symlink";
    report("发布工作区资产与外部 Skills");
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
    report("写入安装记录与初始化配置");
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
    if (dshWanted) {
      report("安装 CANNBot DSH 插件");
      const installed = spawnSync("bash", [dshInstaller, "--profile", dshProfile],
        { cwd: repositoryRoot, stdio: "inherit" });
      if (installed.error || installed.status !== 0) {
        console.warn(`cannbot: CANNBot DSH 插件安装失败；请手动执行 bash ${dshInstaller} `
          + `--profile ${dshProfile}，然后重启 DSH`);
      } else {
        console.log("CANNBot DSH 插件已安装，重启 DSH 后生效。");
      }
    }
    console.log(green("(100%) 安装完成"));
    console.log(green(`安装目录：${options.target}`));
    console.log(green("使用方法："));
    console.log(green(`1. cd ${options.target}`));
    console.log(green("2. 启动客户端"));
    console.log(green("3. 描述算子开发需求"));
    return record;
  } finally {
    cleanup();
    process.removeListener("exit", cleanup);
  }
}
