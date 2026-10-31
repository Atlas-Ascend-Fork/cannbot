// Copyright (c) 2026 CANNBot contributors
// SPDX-License-Identifier: MIT
// See script/LICENSE for the full license text.

import assert from "node:assert/strict";
import { chmodSync, existsSync, lstatSync, mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, statSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";

const repository = resolve(import.meta.dirname, "../..");
const cli = join(repository, "script/bin/cannbot.js");
const pluginId = "tilelang-op-orchestrator";
const plugin = join(repository, "plugins-official", pluginId);
const skills = join(repository, "vendor/cannbot-skills");
const start = `<!-- cannbot:${pluginId}:start -->`;
const end = `<!-- cannbot:${pluginId}:end -->`;
const custom = "# Project rules\r\nPROJECT_RULE_MUST_REMAIN_ACTIVE\r\nPreserve project-specific instructions.";

function sandbox(t, tool = "opencode") {
  const root = mkdtempSync(join(tmpdir(), "tilelang-coexist-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const target = join(root, "project with spaces");
  mkdirSync(target);
  const entry = join(target, tool === "claude" ? "CLAUDE.md" : "AGENTS.md");
  const env = {
    ...process.env, HOME: join(root, "home"), XDG_CACHE_HOME: join(root, "cache"),
    CANNBOT_SKIP_CODEX_PLUGIN_ADD: "1", CANNBOT_SKIP_OPENCODE_PLUGIN_ADD: "1",
  };
  return { root, target, entry, env, tool };
}

function installTileLang(state, mode = "init") {
  const args = mode === "init"
    ? [join(plugin, "init.sh"), "project", state.tool, state.target, "--skills", skills]
    : [cli, "install", pluginId, "--tool", state.tool, "--target", state.target,
      ...(mode === "repository" ? ["--source", repository, "--skills", skills] : [])];
  return spawnSync(mode === "init" ? "bash" : process.execPath, args, { env: state.env, encoding: "utf8" });
}

function installOtherPlugin(state) {
  const source = join(state.root, "other plugin");
  mkdirSync(join(source, ".claude-plugin"), { recursive: true });
  writeFileSync(join(source, ".claude-plugin/plugin.json"), JSON.stringify({
    name: "other-workflow", version: "1.0.0", description: "Coexistence test fixture", skills: [], agents: [],
  }));
  writeFileSync(join(source, "AGENTS.md"), "# Other workflow\nOTHER_PLUGIN_RULE_MUST_REMAIN_ACTIVE\n");
  const result = spawnSync(process.execPath, [cli, "install", "other-workflow", "--tool", state.tool,
    "--source", repository, "--plugin-dir", source, "--target", state.target], { env: state.env, encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr || result.stdout);
}

for (const mode of ["init", "repository", "package"]) {
  for (const tool of ["opencode", "codex", "claude", "trae", "dsh"]) {
    test(`TileLang ${mode} ${tool} preserves project rules and another installed plugin across reinstalls`, (t) => {
      const state = sandbox(t, tool);
      writeFileSync(state.entry, custom);
      installOtherPlugin(state);
      const before = readFileSync(state.entry, "utf8");
      const registryPath = join(state.target, `.${tool}`, "cannbot-plugin.json");
      const otherRecord = JSON.parse(readFileSync(registryPath, "utf8")).plugins[0];
      chmodSync(state.entry, 0o600);
      for (let attempt = 0; attempt < 2; attempt += 1) {
        const result = installTileLang(state, mode);
        assert.equal(result.status, 0, result.stderr || result.stdout);
        const active = readFileSync(state.entry, "utf8");
        assert.ok(active.startsWith(before), "pre-existing active instructions were replaced");
        assert.equal(active.split(start).length - 1, 1);
        assert.equal(active.split(end).length - 1, 1);
        assert.equal(active.split("# TileLang 算子开发入口").length - 1, 1);
        assert.equal(active.split("<!-- cannbot:other-workflow:start -->").length - 1, 1);
        assert.equal(statSync(state.entry).mode & 0o777, 0o600);
        const records = JSON.parse(readFileSync(registryPath, "utf8")).plugins;
        assert.equal(records.filter((record) => record.plugin === pluginId).length, 1);
        assert.deepEqual(records.find((record) => record.plugin === "other-workflow"), otherRecord);
      }
      installOtherPlugin(state);
      const result = installTileLang(state, mode);
      assert.equal(result.status, 0, result.stderr || result.stdout);
      const active = readFileSync(state.entry, "utf8");
      assert.ok(active.startsWith(custom));
      assert.ok(active.includes("OTHER_PLUGIN_RULE_MUST_REMAIN_ACTIVE"));
      assert.equal(active.split(start).length - 1, 1);
      assert.equal(active.split("# TileLang 算子开发入口").length - 1, 1);
    });
  }
}

test("TileLang leaves a foreign instruction symlink and its source intact on conflict", (t) => {
  const state = sandbox(t);
  const foreign = join(state.root, "foreign AGENTS.md");
  writeFileSync(foreign, custom);
  symlinkSync(foreign, state.entry);
  const result = installTileLang(state);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /instruction.*symlink|symbolic link/i);
  assert.equal(realpathSync(state.entry), foreign);
  assert.equal(readFileSync(foreign, "utf8"), custom);
  assert.equal(existsSync(join(state.target, ".opencode/cannbot-plugin.json")), false);
});

test("TileLang refreshes only its managed region while preserving a project's prefix and suffix", (t) => {
  const state = sandbox(t);
  const suffix = "\r\nPROJECT_RULE_AFTER_TILELANG\r\n";
  writeFileSync(state.entry, `${custom}\n\n${start}\nSTALE_TILELANG_RULES\n${end}\n${suffix}`);
  const result = installTileLang(state);
  assert.equal(result.status, 0, result.stderr || result.stdout);
  const active = readFileSync(state.entry, "utf8");
  assert.ok(active.startsWith(`${custom}\n\n${start}\n`));
  assert.ok(active.endsWith(suffix));
  assert.ok(!active.includes("STALE_TILELANG_RULES"));
  assert.equal(active.split("# TileLang 算子开发入口").length - 1, 1);
});

test("TileLang adopts an unchanged legacy entry without duplicating the router", (t) => {
  const state = sandbox(t);
  const first = installTileLang(state);
  assert.equal(first.status, 0, first.stderr || first.stdout);
  const active = readFileSync(state.entry, "utf8");
  writeFileSync(state.entry, active.slice(active.indexOf(start) + start.length + 1, active.indexOf(end)));
  const second = installTileLang(state);
  assert.equal(second.status, 0, second.stderr || second.stdout);
  const updated = readFileSync(state.entry, "utf8");
  assert.equal(updated.split(start).length - 1, 1);
  assert.equal(updated.split("# TileLang 算子开发入口").length - 1, 1);
});

test("TileLang refuses to replace a modified legacy entry without managed markers", (t) => {
  const state = sandbox(t);
  const legacy = `${readFileSync(join(plugin, "AGENTS.md"), "utf8")}\n${custom}`;
  writeFileSync(state.entry, legacy);
  const result = installTileLang(state);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /modified legacy.*managed block/i);
  assert.equal(readFileSync(state.entry, "utf8"), legacy);
});

test("TileLang replaces its own legacy entry symlink while preserving the canonical source", (t) => {
  const state = sandbox(t);
  const source = join(plugin, "AGENTS.md");
  const original = readFileSync(source, "utf8");
  symlinkSync(source, state.entry);
  const result = installTileLang(state);
  assert.equal(result.status, 0, result.stderr || result.stdout);
  assert.equal(lstatSync(state.entry).isSymbolicLink(), false);
  assert.equal(readFileSync(source, "utf8"), original);
  assert.equal(readFileSync(state.entry, "utf8").split(start).length - 1, 1);
});

for (const malformed of [`${custom}\n${start}\nunfinished`, `${end}\n${start}`, `${start}\n${end}\n${start}\n${end}`, `${custom}${start}\n${end}`]) {
  test("TileLang rejects ambiguous managed markers without replacing active project rules", (t) => {
    const state = sandbox(t);
    writeFileSync(state.entry, malformed);
    const result = installTileLang(state);
    assert.notEqual(result.status, 0);
    assert.match(result.stderr, /managed.*block|marker/i);
    assert.equal(readFileSync(state.entry, "utf8"), malformed);
    assert.equal(existsSync(join(state.target, ".opencode/cannbot-plugin.json")), false);
  });
}

for (const tool of ["opencode", "claude"]) {
  test(`TileLang global ${tool} retains existing instructions without an interactive overwrite prompt`, (t) => {
    const state = sandbox(t, tool);
    const config = tool === "opencode" ? join(state.env.HOME, ".config/opencode") : join(state.env.HOME, ".claude");
    const entry = join(config, tool === "claude" ? "CLAUDE.md" : "AGENTS.md");
    mkdirSync(config, { recursive: true });
    writeFileSync(entry, custom);
    for (let attempt = 0; attempt < 2; attempt += 1) {
      const result = spawnSync("bash", [join(plugin, "init.sh"), "global", tool, "--skills", skills], {
        env: state.env, encoding: "utf8",
      });
      assert.equal(result.status, 0, result.stderr || result.stdout);
      const active = readFileSync(entry, "utf8");
      assert.ok(active.startsWith(custom));
      assert.equal(active.split(start).length - 1, 1);
      assert.equal(active.split("# TileLang 算子开发入口").length - 1, 1);
    }
  });
}
