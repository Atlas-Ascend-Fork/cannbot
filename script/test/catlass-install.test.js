// Copyright (c) 2026 CANNBot contributors
// SPDX-License-Identifier: MIT
// See script/LICENSE for the full license text.

import assert from "node:assert/strict";
import { cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, unlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { spawnSync } from "node:child_process";
import test from "node:test";
import { assemblePlugins } from "../lib/plugin-bundle.js";

const packageRoot = resolve(import.meta.dirname, "..");
const repositoryRoot = resolve(packageRoot, "..");
const pluginId = "catlass-op-generator";
const pluginPath = join("plugins-official", pluginId);
const names = ["interface", "reference", "design", "develop", "test", "knowledge"].map((part) => `catlass-cpp-${part}`);
const knowledgeFiles = ["knowledge/ops/catlass/index.md", "knowledge/ops/catlass/apis/block_mmad.md"];
const sandboxes = new Set();
test.afterEach(() => {
  for (const path of sandboxes) rmSync(path, { recursive: true, force: true });
  sandboxes.clear();
});

function git(path, ...args) {
  const result = spawnSync("git", ["-C", path, ...args], { encoding: "utf8", env: { ...process.env, GIT_ALLOW_PROTOCOL: "file" } });
  assert.equal(result.status, 0, result.stderr || result.stdout);
  return result.stdout.trim();
}

function commit(path) {
  git(path, "add", ".");
  git(path, "-c", "user.name=installer-test", "-c", "user.email=installer@example.invalid", "commit", "-m", "fixture");
}

function fixture({ packaged = false, edit } = {}) {
  const root = mkdtempSync(join(tmpdir(), "cannbot-catlass-"));
  sandboxes.add(root);
  const source = join(root, "source");
  const target = join(root, "project");
  const plugin = join(source, pluginPath);
  mkdirSync(target, { recursive: true });
  mkdirSync(join(source, "script", "bin"), { recursive: true });
  cpSync(join(repositoryRoot, pluginPath), plugin, { recursive: true });
  cpSync(join(packageRoot, "bin", "cannbot.js"), join(source, "script", "bin", "cannbot.js"));
  cpSync(join(packageRoot, "lib"), join(source, "script", "lib"), { recursive: true });
  cpSync(join(packageRoot, "package.json"), join(source, "script", "package.json"));
  cpSync(join(repositoryRoot, "LICENSE"), join(source, "LICENSE"));
  cpSync(join(repositoryRoot, "plugins-official", "LICENSE"), join(source, "plugins-official", "LICENSE"));
  const definition = JSON.parse(readFileSync(join(plugin, "plugin-install.json"), "utf8"));
  const repos = {};
  const skillDependency = { name: "cannbot-skills" };
  for (const dependency of [skillDependency, ...definition.dependencies]) {
    const repo = join(root, dependency.name);
    mkdirSync(repo);
    git(repo, "init", "--initial-branch=master");
    writeFileSync(join(repo, ".gitattributes"), "* -text\n");
    writeFileSync(join(repo, "LICENSE"), "fixture license\n");
    if (dependency.name === "cannbot-skills") {
      for (const name of names) {
        mkdirSync(join(repo, "ops", name), { recursive: true });
        writeFileSync(join(repo, "ops", name, "SKILL.md"), `---\nname: ${name}\ndescription: fixture\ndisable-model-invocation: true\n---\n# Preserved body\n`);
      }
    }
    for (const relative of dependency.name === "cannbot-knowledge" ? knowledgeFiles : []) {
      const file = join(repo, relative);
      mkdirSync(dirname(file), { recursive: true });
      writeFileSync(file, "# Preserved knowledge fixture\n");
    }
    commit(repo);
    dependency.repository = pathToFileURL(repo).href;
    repos[dependency.name] = repo;
  }
  edit?.({ definition, repos, root, target });
  writeFileSync(join(plugin, "plugin-install.json"), JSON.stringify(definition));
  git(source, "init", "--initial-branch=master");
  git(source, "-c", "protocol.file.allow=always", "submodule", "add", "-b", "master", pathToFileURL(repos["cannbot-skills"]).href, "vendor/cannbot-skills");
  commit(source);
  if (packaged) assemblePlugins(source, join(source, "script", "dist"), [pluginId]);
  return { root, source, target, plugin, repos, packaged };
}

function install(f, tool = "claude", overrides = {}) {
  const args = [join(f.source, "script", "bin", "cannbot.js"), "install", pluginId, "--tool", tool, "--target", f.target];
  if (!f.packaged) args.push("--source", f.source);
  return spawnSync(process.execPath, args, {
    cwd: f.target,
    encoding: "utf8",
    env: { ...process.env, HOME: join(f.root, "home"), XDG_CACHE_HOME: join(f.root, "cache"),
      GIT_ALLOW_PROTOCOL: "file", CANNBOT_SKIP_DEPENDENCY_REPOS: "0", CANNBOT_SKIP_CODEX_PLUGIN_ADD: "1", CANNBOT_SKIP_OPENCODE_PLUGIN_ADD: "1", ...overrides },
  });
}

function checkout(f, name) {
  return join(f.target, ".cannbot", "dependencies", pluginId, name);
}

function assertFailure(f, pattern) {
  const result = install(f);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, pattern);
  assert.doesNotMatch(result.stdout, /Installed catlass-op-generator/);
  assert.equal(existsSync(join(f.target, "CLAUDE.md")), false);
}

for (const packaged of [false, true]) {
  for (const tool of ["codex", "opencode", "claude", "trae", "dsh"]) {
    test(`CATLASS ${packaged ? "package" : "source"} installs knowledge and six unchanged shared Skills for ${tool}`, () => {
      const f = fixture({ packaged });
      const result = install(f, tool);
      assert.equal(result.status, 0, result.stderr || result.stdout);
      assert.match(result.stdout, /skills: 6/);
      const skillDir = join(f.target, tool === "opencode" || tool === "codex" ? ".agents" : `.${tool}`, "skills");
      for (const name of names) {
        const original = join(f.repos["cannbot-skills"], "ops", name, "SKILL.md");
        const installed = join(skillDir, name, "SKILL.md");
        assert.deepEqual(readFileSync(installed), readFileSync(original));
        if (!packaged) assert.equal(realpathSync(join(skillDir, name)), realpathSync(join(f.source, "vendor/cannbot-skills", "ops", name)));
        if (tool === "codex") assert.deepEqual(readFileSync(join(f.root, "home", "plugins", pluginId, "skills", name, "SKILL.md")), readFileSync(original));
      }
      for (const relative of knowledgeFiles) {
        assert.deepEqual(readFileSync(join(checkout(f, "cannbot-knowledge"), relative)), readFileSync(join(f.repos["cannbot-knowledge"], relative)));
      }
      assert.equal(git(join(f.source, "vendor/cannbot-skills"), "status", "--porcelain"), "");
      assert.equal(existsSync(checkout(f, "cannbot-skills")), false);
      const config = tool === "trae" ? ".trae" : `.${tool}`;
      const record = JSON.parse(readFileSync(join(f.target, config, "cannbot-plugin.json"))).plugins[0];
      assert.equal(record.skills.length, 6);
      assert.equal(git(checkout(f, "cannbot-knowledge"), "status", "--porcelain"), "");
    });
  }
}

test("CATLASS fails when shared Skills cannot be fetched", () => {
  const f = fixture();
  git(join(f.source, "vendor/cannbot-skills"), "remote", "set-url", "origin", pathToFileURL(join(f.root, "unavailable")).href);
  assertFailure(f, /git fetch.*failed/);
});

test("CATLASS rejects a missing Skill before writing instructions", () => {
  const f = fixture({ edit: ({ repos }) => {
    unlinkSync(join(repos["cannbot-skills"], "ops", names[4], "SKILL.md"));
    commit(repos["cannbot-skills"]);
  } });
  assertFailure(f, /skill is missing SKILL.md/);
});

test("CATLASS repeat install fast-forwards clean dependencies and does not duplicate instructions", () => {
  const f = fixture();
  assert.equal(install(f).status, 0);
  writeFileSync(join(f.repos["cannbot-knowledge"], "new-version.txt"), "new version");
  commit(f.repos["cannbot-knowledge"]);
  const result = install(f);
  assert.equal(result.status, 0, result.stderr);
  assert.equal(git(checkout(f, "cannbot-knowledge"), "rev-parse", "HEAD"), git(f.repos["cannbot-knowledge"], "rev-parse", "HEAD"));
  assert.equal(readFileSync(join(f.target, "CLAUDE.md"), "utf8").match(/<!-- cannbot:catlass-op-generator:start -->/g).length, 1);
});
