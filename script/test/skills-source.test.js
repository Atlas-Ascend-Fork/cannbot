// Copyright (c) 2026 CANNBot contributors
// SPDX-License-Identifier: MIT

import assert from "node:assert/strict";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";
import { gitCommit, prepareSharedSkills } from "../lib/skills-source.js";

const repository = resolve(import.meta.dirname, "../..");
const env = { ...process.env, GIT_ALLOW_PROTOCOL: "file", GIT_AUTHOR_NAME: "test", GIT_AUTHOR_EMAIL: "test@example.com",
  GIT_COMMITTER_NAME: "test", GIT_COMMITTER_EMAIL: "test@example.com", CANNBOT_SKIP_CODEX_PLUGIN_ADD: "1",
  CANNBOT_SKIP_OPENCODE_PLUGIN_ADD: "1", CANNBOT_SKIP_DEPENDENCY_REPOS: "1" };

function git(root, ...args) {
  const result = spawnSync("git", ["-C", root, ...args], { encoding: "utf8", env });
  assert.equal(result.status, 0, result.stdout + result.stderr);
  return result.stdout.trim();
}

function fixture(t, mixed = false) {
  const box = mkdtempSync(join(tmpdir(), "cannbot-skills-source-"));
  t.after(() => rmSync(box, { recursive: true, force: true }));
  const remote = join(box, "skills-remote");
  const source = join(box, "source");
  const checkout = join(box, "checkout");
  mkdirSync(join(remote, "ops", "fixture"), { recursive: true });
  writeFileSync(join(remote, "ops", "fixture", "SKILL.md"), "---\nname: fixture\ndescription: fixture\n---\nfirst\n");
  writeFileSync(join(remote, "LICENSE"), "shared license\n");
  git(remote, "init", "-b", "master");
  git(remote, "add", "."); git(remote, "commit", "-m", "first");
  const pinned = gitCommit(remote);
  mkdirSync(source); git(source, "init", "-b", "master");
  git(source, "submodule", "add", "-b", "master", `file://${remote}`, "vendor/cannbot-skills");
  const plugin = join(source, "plugins-official", "fixture-plugin");
  mkdirSync(join(plugin, ".claude-plugin"), { recursive: true });
  writeFileSync(join(plugin, ".claude-plugin", "plugin.json"), JSON.stringify({ name: "fixture-plugin", version: "1.0.0", description: "fixture" }));
  writeFileSync(join(source, "LICENSE"), "main license\n");
  const definition = { skillsRepository: mixed ? "." : "vendor/cannbot-skills", skillInstallMode: "symlink",
    skills: mixed ? ["harness/fixture-harness", "vendor/cannbot-skills/ops/fixture"] : ["ops/fixture"] };
  if (mixed) {
    mkdirSync(join(source, "harness", "fixture-harness"), { recursive: true });
    writeFileSync(join(source, "harness", "fixture-harness", "SKILL.md"), "---\nname: fixture-harness\ndescription: fixture\n---\n");
  }
  writeFileSync(join(plugin, "plugin-sources.json"), JSON.stringify(definition));
  git(source, "add", "."); git(source, "commit", "-m", "pinned dependency");
  writeFileSync(join(remote, "ops", "fixture", "SKILL.md"), "---\nname: fixture\ndescription: fixture\n---\nlatest\n");
  git(remote, "add", "."); git(remote, "commit", "-m", "latest");
  git(box, "clone", "--no-recurse-submodules", source, checkout);
  return { box, remote, checkout, definition, pinned, latest: gitCommit(remote) };
}

function install(f, skills) {
  return spawnSync(process.execPath, [join(repository, "script/bin/cannbot.js"), "install", "fixture-plugin",
    "--source", f.checkout, "--tool", "codex", "--target", join(f.box, "target"),
    ...(skills === undefined ? [] : ["--skills", skills])], { encoding: "utf8",
    env: { ...env, HOME: join(f.box, "home"), XDG_CACHE_HOME: join(f.box, "cache") } });
}

test("ordered plugin initialization reuses the selected shared checkout", (t) => {
  const f = fixture(t);
  const parent = join(f.checkout, "plugins-official/fixture-plugin");
  const before = join(f.checkout, "plugins-official/before-plugin");
  mkdirSync(join(before, ".claude-plugin"), { recursive: true });
  writeFileSync(join(before, ".claude-plugin/plugin.json"), JSON.stringify({ name: "before-plugin", version: "1.0.0", description: "Initialization fixture" }));
  writeFileSync(join(before, "plugin-sources.json"), JSON.stringify(f.definition));
  writeFileSync(join(parent, "plugin-install.json"), JSON.stringify({ initializeBefore: ["before-plugin"] }));
  const result = install(f);
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.ok(result.stdout.indexOf("Installed before-plugin@") < result.stdout.indexOf("Installed fixture-plugin@"));
  const records = JSON.parse(readFileSync(join(f.box, "target/.codex/cannbot-plugin.json"))).plugins;
  assert.deepEqual(records.map((record) => record.plugin), ["before-plugin", "fixture-plugin"]);
  for (const record of records) assert.equal(record.source.revisions["cannbot-skills"].commit, f.latest);

  writeFileSync(join(before, "plugin-install.json"), JSON.stringify({ initializeBefore: ["fixture-plugin"] }));
  const cycle = install(f, f.remote);
  assert.notEqual(cycle.status, 0);
  assert.match(cycle.stderr, /initialization cycle: fixture-plugin -> before-plugin -> fixture-plugin/);
});

test("invalid or unavailable initializers stop before installing the requested plugin", (t) => {
  const f = fixture(t);
  const config = join(f.checkout, "plugins-official/fixture-plugin/plugin-install.json");
  for (const initializeBefore of ["not-an-array", ["../escape"], ["missing-plugin"]]) {
    writeFileSync(config, JSON.stringify({ initializeBefore }));
    const result = install(f, f.remote);
    assert.notEqual(result.status, 0);
    assert.equal(existsSync(join(f.box, "target/.cannbot/plugins/fixture-plugin")), false);
    assert.equal(existsSync(join(f.box, "target/.agents/skills/fixture")), false);
  }
});

test("fresh initialization and repeated installs fetch master and record the actual SHA", (t) => {
  const f = fixture(t);
  assert.equal(existsSync(join(f.checkout, "vendor/cannbot-skills/.git")), false);
  const result = install(f);
  assert.equal(result.status, 0, result.stdout + result.stderr);
  const record = JSON.parse(readFileSync(join(f.box, "target/.codex/cannbot-plugin.json"))).plugins[0];
  assert.equal(record.source.revisions["cannbot-skills"].commit, f.latest);
  assert.equal(record.source.revisions["cannbot-skills"].selection, "latest-branch");
  assert.equal(record.source.revisions["cannbot-skills"].requested, "master");
  assert.equal(record.source.revisions.cannbot, gitCommit(f.checkout));
  writeFileSync(join(f.remote, "new.txt"), "new\n");
  git(f.remote, "add", "."); git(f.remote, "commit", "-m", "next master");
  const again = install(f);
  assert.equal(again.status, 0, again.stdout + again.stderr);
  assert.equal(gitCommit(join(f.checkout, "vendor/cannbot-skills")), gitCommit(f.remote));
});

test("default installs follow the source branch and refresh its latest remote commit", (t) => {
  const f = fixture(t);
  const branch = "release/test";
  git(f.checkout, "checkout", "-b", branch);
  git(f.checkout, "tag", branch);
  git(f.remote, "checkout", "-b", branch, f.pinned);
  let result = install(f);
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.equal(gitCommit(join(f.checkout, "vendor/cannbot-skills")), f.pinned);
  writeFileSync(join(f.remote, "release.txt"), "new branch commit\n");
  git(f.remote, "add", "."); git(f.remote, "commit", "-m", "update release");
  result = install(f);
  assert.equal(result.status, 0, result.stdout + result.stderr);
  const record = JSON.parse(readFileSync(join(f.box, "target/.codex/cannbot-plugin.json"))).plugins[0];
  assert.equal(record.source.revisions["cannbot-skills"].selection, "latest-branch");
  assert.equal(record.source.revisions["cannbot-skills"].requested, branch);
  assert.equal(record.source.revisions["cannbot-skills"].commit, gitCommit(f.remote));
  assert.equal(git(f.checkout, "branch", "--show-current"), branch);
});

test("a missing remote branch falls back to master even when a same-named tag exists", (t) => {
  const f = fixture(t);
  git(f.checkout, "checkout", "-b", "release/missing");
  git(f.remote, "tag", "release/missing", f.pinned);
  const result = install(f);
  assert.equal(result.status, 0, result.stdout + result.stderr);
  const record = JSON.parse(readFileSync(join(f.box, "target/.codex/cannbot-plugin.json"))).plugins[0];
  assert.equal(record.source.revisions["cannbot-skills"].requested, "master");
  assert.equal(record.source.revisions["cannbot-skills"].commit, f.latest);
});

test("a detached source checkout defaults to master", (t) => {
  const f = fixture(t);
  git(f.checkout, "checkout", "--detach");
  const result = install(f);
  assert.equal(result.status, 0, result.stdout + result.stderr);
  const record = JSON.parse(readFileSync(join(f.box, "target/.codex/cannbot-plugin.json"))).plugins[0];
  assert.equal(record.source.revisions["cannbot-skills"].requested, "master");
  assert.equal(record.source.revisions["cannbot-skills"].commit, f.latest);
});

test("remote lookup errors fail without treating the branch as missing", (t) => {
  const f = fixture(t);
  git(f.checkout, "checkout", "-b", "release/test");
  git(f.checkout, "submodule", "update", "--init", "vendor/cannbot-skills");
  git(join(f.checkout, "vendor/cannbot-skills"), "remote", "set-url", "origin", join(f.box, "missing-remote"));
  const result = install(f);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /could not query cannbot-skills branch release\/test/);
  assert.equal(gitCommit(join(f.checkout, "vendor/cannbot-skills")), f.pinned);
  assert.equal(existsSync(join(f.box, "target")), false);
});

test("a missing full SHA is fetched, and a locally available short SHA can be selected", (t) => {
  const f = fixture(t);
  git(f.checkout, "checkout", "-b", "release/explicit-override");
  git(f.checkout, "submodule", "update", "--init", "vendor/cannbot-skills");
  writeFileSync(join(f.remote, "missing.txt"), "fetch this commit\n");
  git(f.remote, "add", "."); git(f.remote, "commit", "-m", "missing SHA");
  const requested = gitCommit(f.remote);
  const result = install(f, requested);
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.equal(gitCommit(join(f.checkout, "vendor/cannbot-skills")), requested);
  const pinned = install(f, f.pinned.slice(0, 10));
  assert.equal(pinned.status, 0, pinned.stdout + pinned.stderr);
  assert.equal(gitCommit(join(f.checkout, "vendor/cannbot-skills")), f.pinned);
});

test("dirty submodule contents prevent both default and fixed-SHA updates", (t) => {
  const f = fixture(t);
  git(f.checkout, "submodule", "update", "--init", "vendor/cannbot-skills");
  const file = join(f.checkout, "vendor/cannbot-skills/ops/fixture/SKILL.md");
  writeFileSync(file, "user changes\n");
  for (const requested of [undefined, f.latest]) {
    const result = install(f, requested);
    assert.notEqual(result.status, 0);
    assert.match(result.stderr, /uncommitted changes/);
    assert.equal(readFileSync(file, "utf8"), "user changes\n");
    assert.equal(gitCommit(join(f.checkout, "vendor/cannbot-skills")), f.pinned);
  }
});

test("local override preserves mixed repository sources, uses its license and records dirty content", (t) => {
  const f = fixture(t, true);
  writeFileSync(join(f.remote, "uncommitted.txt"), "working copy\n");
  const result = install(f, f.remote);
  assert.equal(result.status, 0, result.stdout + result.stderr);
  const root = join(f.box, "target/.agents/skills");
  assert.equal(realpathSync(join(root, "fixture")), realpathSync(join(f.remote, "ops/fixture")));
  assert.equal(realpathSync(join(root, "fixture-harness")), realpathSync(join(f.checkout, "harness/fixture-harness")));
  assert.equal(existsSync(join(f.checkout, "vendor/cannbot-skills/.git")), false);
  assert.equal(readFileSync(join(f.box, "target/.cannbot/plugins/fixture-plugin/SKILLS_LICENSE"), "utf8"), "shared license\n");
  const record = JSON.parse(readFileSync(join(f.box, "target/.codex/cannbot-plugin.json"))).plugins[0];
  assert.equal(record.source.revisions["cannbot-skills"].dirty, true);
});

test("invalid paths, parent-repository subdirectories and unsupported overrides fail before installing", (t) => {
  const f = fixture(t);
  for (const value of ["not-a-SHA", join(f.remote, "ops"), join(f.remote, "LICENSE")]) {
    const result = install(f, value);
    assert.notEqual(result.status, 0);
    assert.equal(existsSync(join(f.box, "target")), false);
  }
  assert.throws(() => prepareSharedSkills(null, null, f.latest), /requires a source plugin/);
  assert.throws(() => prepareSharedSkills(f.checkout, { skillsRepository: ".", skills: [] }, f.latest), /requires a source plugin/);
  const packaged = spawnSync(process.execPath, [join(repository, "script/bin/cannbot.js"), "install", "fixture-plugin",
    "--plugin-dir", join(f.checkout, "plugins-official/fixture-plugin"), "--tool", "codex",
    "--target", join(f.box, "target"), "--skills", f.remote], { encoding: "utf8", env });
  assert.notEqual(packaged.status, 0);
  assert.match(packaged.stderr, /requires a source plugin/);
  assert.equal(existsSync(join(f.box, "target")), false);
});

test("a failed master fetch does not silently install stale Skills", (t) => {
  const f = fixture(t);
  git(f.checkout, "submodule", "update", "--init", "vendor/cannbot-skills");
  git(join(f.checkout, "vendor/cannbot-skills"), "remote", "set-url", "origin", join(f.box, "missing-remote"));
  const result = install(f);
  assert.notEqual(result.status, 0);
  assert.equal(gitCommit(join(f.checkout, "vendor/cannbot-skills")), f.pinned);
  assert.equal(existsSync(join(f.box, "target")), false);
});

test("fixed-SHA and master selection update nested submodules to the selected commit", (t) => {
  const f = fixture(t);
  const nested = join(f.box, "nested-remote");
  mkdirSync(nested); git(nested, "init", "-b", "master");
  writeFileSync(join(nested, "value.txt"), "old\n");
  git(nested, "add", "."); git(nested, "commit", "-m", "old nested");
  const oldNested = gitCommit(nested);
  git(f.remote, "submodule", "add", `file://${nested}`, "tests");
  git(f.remote, "add", "."); git(f.remote, "commit", "-m", "old nested pointer");
  const oldShared = gitCommit(f.remote);
  writeFileSync(join(nested, "value.txt"), "new\n");
  git(nested, "add", "."); git(nested, "commit", "-m", "new nested");
  git(join(f.remote, "tests"), "fetch", "origin", "master");
  git(join(f.remote, "tests"), "checkout", "--detach", gitCommit(nested));
  git(f.remote, "add", "."); git(f.remote, "commit", "-m", "new nested pointer");
  let result = install(f, oldShared);
  assert.equal(result.status, 0, result.stdout + result.stderr);
  const installedNested = join(f.checkout, "vendor/cannbot-skills/tests");
  assert.equal(gitCommit(installedNested), oldNested);
  result = install(f);
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.equal(gitCommit(installedNested), gitCommit(nested));
});
