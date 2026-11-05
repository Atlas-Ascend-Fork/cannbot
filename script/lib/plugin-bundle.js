// Copyright (c) 2026 CANNBot contributors
// SPDX-License-Identifier: MIT
// See script/LICENSE for the full license text.

import {
  cpSync,
  existsSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  realpathSync,
  rmSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { basename, dirname, isAbsolute, join, relative, resolve, sep } from "node:path";

// A community plugin ships its own licence, so the repository licence is not stamped
// onto it. Its parent directory is what marks it as community-owned.
// The marketplace advertises a plugin by its manifest name, which need not match the
// directory holding it — `cake` lives in `collaborative-agent-kernel-evolution`. Try the
// direct path first, then fall back to matching the manifest name.
export function findPluginDirectory(repositoryRoot, parent, pluginId) {
  const direct = join(repositoryRoot, parent, pluginId);
  if (existsSync(join(direct, ".claude-plugin", "plugin.json"))) return direct;
  const parentRoot = join(repositoryRoot, parent);
  if (!existsSync(parentRoot)) return null;
  const entries = readdirSync(parentRoot, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .sort((a, b) => a.name.localeCompare(b.name));
  for (const entry of entries) {
    const candidate = join(parentRoot, entry.name);
    const manifest = join(candidate, ".claude-plugin", "plugin.json");
    if (!existsSync(manifest)) continue;
    try {
      if (readJson(manifest).name === pluginId) return candidate;
    } catch {
      // A manifest that will not parse is reported where it is read, not here.
    }
  }
  return null;
}

function isCommunityPlugin(pluginRoot) {
  return basename(dirname(pluginRoot)) === "plugins-community";
}

function readJson(path) {
  return JSON.parse(readFileSync(path, "utf8"));
}

function assertInside(root, candidate, label) {
  const pathFromRoot = relative(root, candidate);
  if (pathFromRoot === "" || (!pathFromRoot.startsWith("..") && !isAbsolute(pathFromRoot))) return;
  throw new Error(`${label} escapes its repository root: ${candidate}`);
}

export function pluginSourceDefinition(repositoryRoot, pluginId, pluginDirectory = null) {
  const pluginRoot = pluginDirectory ?? ["plugins-official", "plugins-community"]
    .map((parent) => findPluginDirectory(repositoryRoot, parent, pluginId))
    .find((candidate) => candidate && existsSync(join(candidate, "plugin-sources.json")))
    ?? join(repositoryRoot, "plugins-official", pluginId);
  const definitionPath = join(pluginRoot, "plugin-sources.json");
  if (!existsSync(definitionPath)) return null;
  const definition = readJson(definitionPath);
  if (!definition || typeof definition.skillsRepository !== "string" || !Array.isArray(definition.skills)) {
    throw new Error(`invalid plugin source definition: ${definitionPath}`);
  }
  if (definition.skillInstallMode !== undefined && definition.skillInstallMode !== "symlink") {
    throw new Error(`invalid Skill install mode in ${definitionPath}`);
  }
  if (definition.preserveSkillInvocationPolicy !== undefined
    && typeof definition.preserveSkillInvocationPolicy !== "boolean") {
    throw new Error(`invalid preserveSkillInvocationPolicy in ${definitionPath}`);
  }
  return { pluginRoot, definitionPath, ...definition };
}

function physicalPath(path) {
  const absolute = resolve(path);
  let existing = absolute;
  while (!existsSync(existing)) existing = dirname(existing);
  return resolve(realpathSync(existing), relative(existing, absolute));
}

function containsPath(root, candidate) {
  const pathFromRoot = relative(root, candidate);
  return pathFromRoot === "" || (!isAbsolute(pathFromRoot)
    && pathFromRoot !== ".." && !pathFromRoot.startsWith(`..${sep}`));
}

export function assertSafeAssemblyOutput(repositoryRoot, outputRoot) {
  const repository = physicalPath(repositoryRoot);
  const output = physicalPath(outputRoot);
  const reject = () => { throw new Error(`unsafe assembly output directory: ${outputRoot}`); };
  if (existsSync(output) && !statSync(output).isDirectory()) reject();
  const inputs = [".git", "plugins-official", "plugins-community", "vendor",
    "script/bin", "script/lib", "script/scripts", "script/test", "script/docs"]
    .map((path) => physicalPath(join(repository, path)));
  // The library can reuse an existing output tree whose plugins/ is a symlink.
  for (const destination of [output, physicalPath(join(output, "plugins"))]) {
    if (containsPath(destination, repository)) reject();
    for (const input of inputs) {
      if (containsPath(input, destination) || containsPath(destination, input)) reject();
    }
  }
}

export function assemblePlugins(repositoryRoot, outputRoot, selectedPluginIds) {
  assertSafeAssemblyOutput(repositoryRoot, outputRoot);
  const sourcePluginRoot = join(repositoryRoot, "plugins-official");
  const pluginIds = selectedPluginIds ?? ["plugins-official", "plugins-community"].flatMap((parent) => {
    const root = join(repositoryRoot, parent);
    return existsSync(root) ? readdirSync(root, { withFileTypes: true })
      .filter((entry) => entry.isDirectory() && existsSync(join(root, entry.name, "plugin-sources.json")))
      .map((entry) => entry.name) : [];
  }).sort();
  if (new Set(pluginIds).size !== pluginIds.length) throw new Error("duplicate plugin ids");

  mkdirSync(join(outputRoot, "plugins"), { recursive: true });
  const pluginLicense = join(sourcePluginRoot, "LICENSE");
  if (!existsSync(pluginLicense)) throw new Error(`plugin license is missing: ${pluginLicense}`);
  cpSync(pluginLicense, join(outputRoot, "plugins", "LICENSE"));
  const assembled = [];

  for (const pluginId of pluginIds) {
    const source = pluginSourceDefinition(repositoryRoot, pluginId);
    if (!source) throw new Error(`plugin has no source definition: ${pluginId}`);
    const manifestPath = join(source.pluginRoot, ".claude-plugin", "plugin.json");
    const manifest = readJson(manifestPath);
    if (typeof manifest.name !== "string" || !/^[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*$/.test(manifest.name)) {
      throw new Error(`invalid plugin manifest name: ${manifestPath}`);
    }
    const destination = join(outputRoot, "plugins", pluginId);
    rmSync(destination, { recursive: true, force: true });
    mkdirSync(destination, { recursive: true });
    if (!isCommunityPlugin(source.pluginRoot)) cpSync(pluginLicense, join(destination, "LICENSE"));

    for (const entry of readdirSync(source.pluginRoot, { withFileTypes: true })) {
      if (entry.name === "skills" || entry.name === "plugin-sources.json") continue;
      cpSync(join(source.pluginRoot, entry.name), join(destination, entry.name), {
        recursive: true,
        dereference: true,
      });
    }

    const skillsRepository = resolve(repositoryRoot, source.skillsRepository);
    if (!existsSync(join(skillsRepository, ".git"))) {
      throw new Error(`Skill submodule is not initialized: ${source.skillsRepository}`);
    }
    const skillsLicense = join(skillsRepository, "LICENSE");
    if (!existsSync(skillsLicense)) throw new Error(`Skill repository license is missing: ${skillsLicense}`);
    cpSync(skillsLicense, join(destination, "SKILLS_LICENSE"));
    const names = new Set();

    const copySkill = (skillSource, skillName) => {
      if (names.has(skillName)) throw new Error(`duplicate Skill name in ${pluginId}: ${skillName}`);
      names.add(skillName);
      const skillDestination = join(destination, "skills", skillName);
      cpSync(skillSource, skillDestination, {
        recursive: true,
        dereference: true,
        filter: (path) => basename(path) !== "__pycache__" && !path.endsWith(".pyc"),
      });
      // A plugin may declare that its Skills carry their own invocation policy, in which
      // case each SKILL.md keeps the value it was authored with.
      if (source.preserveSkillInvocationPolicy === true) return;
      const skillManifest = join(skillDestination, "SKILL.md");
      const skillMd = readFileSync(skillManifest, "utf8")
        .replace(/^disable-model-invocation:\s*true\s*$/m, "disable-model-invocation: false");
      writeFileSync(skillManifest, skillMd);
    };

    // Shared skills pulled from the Skill submodule (plugin-sources.json).
    for (const relativeSkill of source.skills) {
      if (typeof relativeSkill !== "string" || !relativeSkill) {
        throw new Error(`invalid Skill path in ${source.definitionPath}`);
      }
      const skillSource = resolve(skillsRepository, relativeSkill);
      assertInside(skillsRepository, skillSource, "Skill path");
      if (!existsSync(join(skillSource, "SKILL.md"))) {
        throw new Error(`Skill is missing SKILL.md: ${relativeSkill}`);
      }
      copySkill(skillSource, basename(skillSource));
    }

    // Self-contained workflow skills shipped inside the plugin (skills/).
    const localSkillsRoot = join(source.pluginRoot, "skills");
    if (existsSync(localSkillsRoot)) {
      for (const entry of readdirSync(localSkillsRoot, { withFileTypes: true })) {
        if (!entry.isDirectory()) continue;
        const skillSource = join(localSkillsRoot, entry.name);
        if (!existsSync(join(skillSource, "SKILL.md"))) continue;
        copySkill(skillSource, entry.name);
      }
    }

    manifest.skills = [...names].map((name) => `./skills/${name}`);
    delete manifest.dependencies;
    writeFileSync(
      join(destination, ".claude-plugin", "plugin.json"),
      `${JSON.stringify(manifest, null, 2)}\n`,
    );
    assembled.push({ pluginId: manifest.name, destination, skills: names.size });
  }

  return assembled;
}
