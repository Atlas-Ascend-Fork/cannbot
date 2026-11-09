// Copyright (c) 2026 CANNBot contributors
// SPDX-License-Identifier: MIT
// See script/LICENSE for the full license text.

import {
  copyFileSync, existsSync, lstatSync, mkdirSync, readdirSync, readFileSync,
  realpathSync, renameSync, writeFileSync,
} from "node:fs";
import { dirname, isAbsolute, join, relative, resolve, sep } from "node:path";

export function hasWorkspace(pluginDir) {
  const path = join(pluginDir, "plugin-install.json");
  return existsSync(path) && JSON.parse(readFileSync(path, "utf8")).workspace !== undefined;
}

function inside(root, path) {
  const rel = relative(root, path);
  return rel === "" || (!isAbsolute(rel) && rel !== ".." && !rel.startsWith(`..${sep}`));
}

function checkedPath(root, path) {
  if (typeof path !== "string" || !path || isAbsolute(path)) throw new Error(`invalid workspace path: ${path}`);
  const result = resolve(root, path);
  if (result === resolve(root) || !inside(root, result)) throw new Error(`workspace path escapes root: ${path}`);
  return result;
}

function existing(path) {
  try { return lstatSync(path); } catch (error) {
    if (error.code === "ENOENT") return null;
    throw error;
  }
}

// Never follow a destination link, even one pointing inside the workspace.
function checkDestination(target, destination, directory = false) {
  let current = destination;
  while (inside(target, current)) {
    const stat = existing(current);
    if (stat?.isSymbolicLink()) throw new Error(`workspace destination is a symlink: ${current}`);
    if (stat && (current !== destination || directory) && !stat.isDirectory()) {
      throw new Error(`workspace directory is not a directory: ${current}`);
    }
    if (current === target) break;
    current = dirname(current);
  }
  const stat = existing(destination);
  if (stat && !directory && !stat.isFile()) throw new Error(`workspace file is not a regular file: ${destination}`);
}

export function preflightWorkspaceFiles(target, paths) {
  target = resolve(target);
  for (const path of paths) checkDestination(target, checkedPath(target, path));
}

function backup(path) {
  let destination = `${path}.cannbot-backup`;
  let index = 1;
  while (existing(destination)) destination = `${path}.cannbot-backup.${index++}`;
  renameSync(path, destination);
}

export function installWorkspace(pluginDir, target, tool) {
  const definition = JSON.parse(readFileSync(join(pluginDir, "plugin-install.json"), "utf8")).workspace;
  if (!definition || !Array.isArray(definition.tools) || !definition.tools.includes(tool)) {
    throw new Error(`workspace supports only: ${(definition?.tools ?? []).join(", ")}`);
  }
  for (const key of ["files", "preserve", "directories"]) {
    if (!Array.isArray(definition[key])) throw new Error(`workspace.${key} must be an array`);
  }
  target = resolve(target);
  pluginDir = realpathSync(pluginDir);
  let ancestor = target;
  while (!existing(ancestor)) ancestor = dirname(ancestor);
  const canonicalTarget = resolve(realpathSync(ancestor), relative(ancestor, target));
  if (inside(pluginDir, canonicalTarget) || inside(canonicalTarget, pluginDir)) {
    throw new Error("workspace source and target must not overlap");
  }
  const files = [];
  const collect = (source, destination, preserve) => {
    const stat = lstatSync(source);
    if (stat.isSymbolicLink()) throw new Error(`workspace source is a symlink: ${source}`);
    if (stat.isDirectory()) {
      checkDestination(target, destination, true);
      for (const entry of readdirSync(source)) {
        if (entry === "__pycache__" || entry.endsWith(".pyc") || entry.endsWith(".egg-info")) continue;
        collect(join(source, entry), join(destination, entry), preserve);
      }
    } else if (stat.isFile()) {
      checkDestination(target, destination);
      files.push({ source, destination, preserve });
    } else throw new Error(`unsupported workspace source: ${source}`);
  };
  for (const [key, preserve] of [["files", false], ["preserve", true]]) {
    for (const entry of definition[key]) {
      const sourcePath = typeof entry === "string" ? entry : entry?.source;
      const targetPath = typeof entry === "string" ? entry : entry?.target;
      const source = checkedPath(pluginDir, sourcePath);
      checkDestination(pluginDir, source, lstatSync(source).isDirectory());
      collect(source, checkedPath(target, targetPath), preserve);
    }
  }
  const directories = definition.directories.map((path) => checkedPath(target, path));
  for (const directory of directories) checkDestination(target, directory, true);

  // Only merge hook registrations. Never install a plugin's blanket permission grants.
  let settings;
  let settingsPath;
  if (definition.claudeSettings) {
    const source = checkedPath(pluginDir, definition.claudeSettings);
    checkDestination(pluginDir, source);
    settingsPath = checkedPath(target, definition.claudeSettings);
    checkDestination(target, settingsPath);
    settings = existsSync(settingsPath) ? JSON.parse(readFileSync(settingsPath, "utf8")) : {};
    if (!settings || typeof settings !== "object" || Array.isArray(settings)) throw new Error("Claude settings must be an object");
    const hooks = JSON.parse(readFileSync(source, "utf8")).hooks ?? {};
    settings.hooks ??= {};
    if (!settings.hooks || typeof settings.hooks !== "object" || Array.isArray(settings.hooks)) throw new Error("Claude hooks must be an object");
    for (const [event, entries] of Object.entries(hooks)) {
      const current = settings.hooks[event] ?? [];
      if (!Array.isArray(current) || !Array.isArray(entries)) throw new Error(`invalid Claude hook event: ${event}`);
      const known = new Set(current.map((entry) => JSON.stringify(entry)));
      for (const entry of entries) {
        const serialized = JSON.stringify(entry);
        if (!known.has(serialized)) current.push(entry);
        known.add(serialized);
      }
      settings.hooks[event] = current;
    }
  }
  // Preflight the complete copy and settings before changing the project.
  for (const { source, destination, preserve } of files) {
    if (existsSync(destination)) {
      if (preserve || readFileSync(source).equals(readFileSync(destination))) continue;
      backup(destination);
    }
    mkdirSync(dirname(destination), { recursive: true });
    copyFileSync(source, destination);
  }
  for (const directory of directories) mkdirSync(directory, { recursive: true });
  if (settingsPath) {
    mkdirSync(dirname(settingsPath), { recursive: true });
    writeFileSync(settingsPath, `${JSON.stringify(settings, null, 2)}\n`);
  }
  return files.map(({ destination }) => relative(target, destination));
}
