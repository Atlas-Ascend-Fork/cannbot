// Copyright (c) 2026 CANNBot contributors
// SPDX-License-Identifier: MIT
// See script/LICENSE for the full license text.

import assert from "node:assert/strict";
import { chmodSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";

const packageRoot = resolve(import.meta.dirname, "..");
const entry = join(packageRoot, "bin", "source-plugin-init.sh");
const minimumMajor = Number(JSON.parse(readFileSync(join(packageRoot, "package.json"))).engines.node.match(/^>=(\d+)$/)[1]);
const bash = spawnSync("bash", ["-c", "command -v bash"], { encoding: "utf8" }).stdout.trim();

function fixture(t, version, versionExit = 0) {
  const root = mkdtempSync(join(tmpdir(), "cannbot-node-preflight-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const bin = join(root, "bin");
  const repository = join(root, "repository");
  const plugin = join(repository, "plugins-official", "fixture");
  const capture = join(root, "installed.json");
  mkdirSync(bin);
  symlinkSync(bash, join(bin, "bash"));
  const dirname = spawnSync(bash, ["-c", "command -v dirname"], { encoding: "utf8" }).stdout.trim();
  symlinkSync(dirname, join(bin, "dirname"));
  mkdirSync(join(plugin, ".claude-plugin"), { recursive: true });
  writeFileSync(join(plugin, ".claude-plugin", "plugin.json"), JSON.stringify({ name: "fixture" }));
  mkdirSync(join(repository, "script", "bin"), { recursive: true });
  writeFileSync(join(repository, "script", "bin", "cannbot.js"),
    "require('node:fs').writeFileSync(process.env.CANNBOT_CAPTURE, JSON.stringify(process.argv.slice(2)));\n");
  if (version !== null) {
    const node = join(bin, "node");
    writeFileSync(node, [
      "#!/usr/bin/env bash",
      'if [[ "${1:-}" == "--version" ]]; then',
      '  printf "%s\\n" "$CANNBOT_TEST_NODE_VERSION"',
      '  exit "$CANNBOT_TEST_NODE_VERSION_EXIT"',
      "fi",
      'exec "$CANNBOT_TEST_NODE" "$@"',
      "",
    ].join("\n"));
    chmodSync(node, 0o755);
  }
  const result = spawnSync(bash, [entry, plugin, "project", "codex", join(root, "target")], {
    encoding: "utf8",
    env: {
      ...process.env,
      PATH: bin,
      CANNBOT_CAPTURE: capture,
      CANNBOT_TEST_NODE: process.execPath,
      CANNBOT_TEST_NODE_VERSION: version ?? "",
      CANNBOT_TEST_NODE_VERSION_EXIT: String(versionExit),
    },
  });
  return { root, capture, result };
}

for (const [name, version, code] of [
  ["missing Node.js", null, 0],
  ["Node.js below the package requirement", `v${minimumMajor - 1}.9.0`, 0],
  ["Node.js that cannot run", "failed to load libnode", 127],
  ["unrecognized Node.js version", "unknown", 0],
]) {
  test(`source init stops before installation for ${name}`, (t) => {
    const { root, capture, result } = fixture(t, version, code);
    assert.equal(result.status, 1, result.stderr);
    assert.match(result.stderr, /Node\.js/);
    assert.ok(result.stderr.includes(`>=${minimumMajor}`));
    assert.match(result.stderr, /node --version/);
    assert.equal(existsSync(capture), false);
    assert.equal(existsSync(join(root, "target")), false);
  });
}

for (const major of [minimumMajor, minimumMajor + 2]) {
  test(`source init runs the installer with supported Node.js ${major}`, (t) => {
    const { capture, result } = fixture(t, `v${major}.0.0`);
    assert.equal(result.status, 0, result.stderr);
    const args = JSON.parse(readFileSync(capture));
    assert.deepEqual(args.slice(0, 4), ["install", "fixture", "--tool", "codex"]);
  });
}
