// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// SPDX-License-Identifier: MIT
// See script/LICENSE for the full license text.

import assert from "node:assert/strict";
import { cpSync, existsSync, lstatSync, mkdirSync, mkdtempSync, readdirSync, readFileSync,
  readlinkSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import test from "node:test";
import { assemblePlugins } from "../lib/plugin-bundle.js";

const packageRoot = resolve(import.meta.dirname, "..");

function write(path, contents) {
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, contents);
}

function fixture(t) {
  // All destructive baseline operations stay inside this disposable sandbox.
  const root = mkdtempSync(join(tmpdir(), "cannbot-assembly-output-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const repository = join(root, "repository");
  write(join(repository, "script/package.json"), '{"type":"module"}\n');
  for (const name of ["lib/plugin-bundle.js", "scripts/assemble-plugins.js"]) {
    const destination = join(repository, "script", name);
    mkdirSync(dirname(destination), { recursive: true });
    cpSync(join(packageRoot, name), destination);
  }
  for (const name of [".git/HEAD", "script/bin/sentinel", "script/test/sentinel",
    "script/docs/sentinel", "script/index.js", "script/README.md", "script/LICENSE"]) {
    write(join(repository, name), "preserve build input\n");
  }
  write(join(repository, "plugins-official/LICENSE"), "official license fixture\n");
  write(join(repository, "vendor/cannbot-skills/.git/HEAD"), "fixture metadata\n");
  write(join(repository, "vendor/cannbot-skills/LICENSE"), "skill license fixture\n");
  write(join(repository, "vendor/cannbot-skills/demo/SKILL.md"), "# Demo skill\n");
  for (const [parent, folder, name] of [
    ["plugins-official", "demo", "demo"],
    ["plugins-community", "community-folder", "community.demo"],
  ]) {
    const plugin = join(repository, parent, folder);
    write(join(plugin, ".claude-plugin/plugin.json"), JSON.stringify({ name }));
    write(join(plugin, "plugin-sources.json"), JSON.stringify({
      skillsRepository: "vendor/cannbot-skills", skills: ["demo"],
    }));
    write(join(plugin, "README.md"), "preserve plugin source\n");
    if (parent === "plugins-community") write(join(plugin, "LICENSE"), "community license fixture\n");
  }
  return { root, repository, cli: join(repository, "script/scripts/assemble-plugins.js") };
}

function snapshot(root) {
  if (!existsSync(root)) return { missing: true };
  const files = {};
  function walk(directory, prefix = "") {
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      const path = join(directory, entry.name);
      const name = prefix + entry.name;
      if (entry.isSymbolicLink()) files[name] = { link: readlinkSync(path) };
      else if (entry.isDirectory()) walk(path, name + "/");
      else files[name] = createHash("sha256").update(readFileSync(path)).digest("hex");
    }
  }
  walk(root);
  return files;
}

function runCli(box, output) {
  return spawnSync(process.execPath, [box.cli, output], { encoding: "utf8" });
}

function rejectsWithoutWrites(box, output, mode) {
  const before = snapshot(box.root);
  let error = "";
  let status;
  if (mode === "cli") {
    const result = runCli(box, output);
    error = result.stderr;
    status = result.status;
  } else {
    try {
      assemblePlugins(box.repository, output);
    } catch (caught) {
      error = caught.message;
    }
  }
  assert.deepEqual(snapshot(box.root), before, "build inputs or output changed before rejection");
  if (mode === "cli") assert.notEqual(status, 0, "unsafe output must fail");
  assert.match(error, /unsafe assembly output directory/i);
}

const unsafePaths = [
  ["repository root", (box) => box.repository],
  ["repository ancestor", (box) => box.root],
  ["official plugins", (box) => join(box.repository, "plugins-official")],
  ["inside an official plugin", (box) => join(box.repository, "plugins-official/demo/generated")],
  ["community plugins", (box) => join(box.repository, "plugins-community")],
  ["inside a community plugin", (box) => join(box.repository, "plugins-community/community-folder/generated")],
  ["vendor", (box) => join(box.repository, "vendor")],
  ["inside the Skill sources", (box) => join(box.repository, "vendor/cannbot-skills/demo/generated")],
  ["installer project", (box) => join(box.repository, "script")],
  ["installer library", (box) => join(box.repository, "script/lib")],
  ["installer scripts", (box) => join(box.repository, "script/scripts")],
  ["installer executable", (box) => join(box.repository, "script/bin")],
  ["installer tests", (box) => join(box.repository, "script/test")],
  ["Git metadata", (box) => join(box.repository, ".git")],
];

for (const mode of ["cli", "library"]) {
  for (const [name, outputPath] of unsafePaths) {
    test(`${mode} preserves all build inputs for output at ${name}`, (t) => {
      const box = fixture(t);
      rejectsWithoutWrites(box, outputPath(box), mode);
    });
  }
  test(`${mode} rejects an output symlink to plugin sources`, (t) => {
    const box = fixture(t);
    const alias = join(box.root, "source-alias");
    symlinkSync(join(box.repository, "plugins-official"), alias, "dir");
    rejectsWithoutWrites(box, alias, mode);
  });
  test(`${mode} resolves a symlink in a missing output parent`, (t) => {
    const box = fixture(t);
    const alias = join(box.root, "source-alias");
    symlinkSync(join(box.repository, "vendor"), alias, "dir");
    rejectsWithoutWrites(box, join(alias, "cannbot-skills/new/output"), mode);
  });
  test(`${mode} preserves a file passed as an output directory`, (t) => {
    const box = fixture(t);
    rejectsWithoutWrites(box, join(box.repository, "script/package.json"), mode);
  });
  for (const [name, outputPath] of [
    ["default dist", (box) => join(box.repository, "script/dist")],
    ["custom build directory", (box) => join(box.repository, ".build")],
    ["sibling with the repository name prefix", (box) => join(box.root, "repository-dist")],
  ]) {
    test(`${mode} assembles normally at ${name}`, (t) => {
      const box = fixture(t);
      const output = outputPath(box);
      const originalSkill = readFileSync(join(box.repository, "vendor/cannbot-skills/demo/SKILL.md"), "utf8");
      if (mode === "cli") {
        const result = runCli(box, output);
        assert.equal(result.status, 0, result.stderr);
      } else {
        const assembled = assemblePlugins(box.repository, output);
        assert.deepEqual(assembled.map((plugin) => plugin.pluginId), ["community.demo", "demo"]);
      }
      for (const directory of ["demo", "community-folder"]) {
        const skill = join(output, "plugins", directory, "skills/demo/SKILL.md");
        assert.equal(lstatSync(skill).isFile(), true);
        assert.equal(readFileSync(skill, "utf8"), originalSkill);
      }
      assert.equal(readFileSync(join(box.repository, "vendor/cannbot-skills/demo/SKILL.md"), "utf8"), originalSkill);
    });
  }
}

test("library rejects an existing plugins output symlink to Skill sources", (t) => {
  const box = fixture(t);
  const output = join(box.root, "artifacts");
  mkdirSync(output);
  symlinkSync(join(box.repository, "vendor/cannbot-skills"), join(output, "plugins"), "dir");
  rejectsWithoutWrites(box, output, "library");
});


test("declared extra assets preserve classified resources without exposing them as Skills", (t) => {
  const f = fixture(t);
  const plugin = join(f.repository, "plugins-official/demo");
  const definition = JSON.parse(readFileSync(join(plugin, "plugin-sources.json"), "utf8"));
  definition.extraAssets = ["skills/variants"];
  write(join(plugin, "plugin-sources.json"), JSON.stringify(definition));
  write(join(plugin, "skills/variants/platform/language/SKILL.md"), "private variant\n");
  const output = join(f.root, "output");
  assemblePlugins(f.repository, output, ["demo"]);
  const packaged = join(output, "plugins/demo");
  assert.equal(readFileSync(join(packaged, "skills/variants/platform/language/SKILL.md"), "utf8"), "private variant\n");
  assert.deepEqual(JSON.parse(readFileSync(join(packaged, ".claude-plugin/plugin.json"), "utf8")).skills, ["./skills/demo"]);
});

for (const mode of ["relative escape", "absolute path", "symlink escape", "existing destination"]) {
  test(`extra assets reject ${mode}`, (t) => {
    const f = fixture(t);
    const plugin = join(f.repository, "plugins-official/demo");
    const definition = JSON.parse(readFileSync(join(plugin, "plugin-sources.json"), "utf8"));
    const outside = join(f.root, "outside.md");
    write(outside, "private bytes\n");
    let path = "../../../outside.md";
    if (mode === "absolute path") path = outside;
    if (mode === "symlink escape") { path = "private.md"; symlinkSync(outside, join(plugin, path)); }
    if (mode === "existing destination") path = "README.md";
    definition.extraAssets = [path];
    write(join(plugin, "plugin-sources.json"), JSON.stringify(definition));
    assert.throws(() => assemblePlugins(f.repository, join(f.root, "output"), ["demo"]), /extra asset/);
    assert.equal(readFileSync(outside, "utf8"), "private bytes\n");
  });
}
