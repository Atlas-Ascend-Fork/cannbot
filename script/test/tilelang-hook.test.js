// Copyright (c) 2026 CANNBot contributors
// SPDX-License-Identifier: MIT
// See script/LICENSE for the full license text.

import assert from "node:assert/strict";
import { cpSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";

const source = resolve(import.meta.dirname, "../../plugins-official/tilelang-op-orchestrator/hooks/run-hook.cmd");

function sandbox(t) {
  const directory = mkdtempSync(join(tmpdir(), "tilelang-hook-"));
  t.after(() => rmSync(directory, { recursive: true, force: true }));
  const hooks = join(directory, "plugin with spaces", "hooks");
  const caller = join(directory, "caller");
  mkdirSync(hooks, { recursive: true });
  mkdirSync(caller);
  const wrapper = join(hooks, "run-hook.cmd");
  cpSync(source, wrapper);
  return { hooks, caller, wrapper };
}

for (const shell of ["bash", "sh"]) {
  test(`TileLang ${shell} hook dispatcher preserves arguments from another working directory`, (t) => {
    const { hooks, caller, wrapper } = sandbox(t);
    writeFileSync(join(hooks, "argument probe"), "printf '%s\\n' \"$@\"\n");
    const args = ["a value with spaces", "", "single'quote", 'double"quote', "literal;$()&", "--flag", "中文"];
    const result = spawnSync(shell, [wrapper, "argument probe", ...args], { cwd: caller, encoding: "utf8" });
    assert.ifError(result.error);
    assert.equal(result.status, 0, result.stderr);
    assert.equal(result.stdout, `${args.join("\n")}\n`);
    assert.equal(result.stderr, "");
  });

  test(`TileLang ${shell} hook dispatcher returns the child's status and streams`, (t) => {
    const { hooks, caller, wrapper } = sandbox(t);
    writeFileSync(join(hooks, "failing hook"), "printf 'out\\n'\nprintf 'err\\n' >&2\nexit 23\n");
    const result = spawnSync(shell, [wrapper, "failing hook"], { cwd: caller, encoding: "utf8" });
    assert.ifError(result.error);
    assert.equal(result.status, 23);
    assert.equal(result.stdout, "out\n");
    assert.equal(result.stderr, "err\n");
  });

  test(`TileLang ${shell} hook dispatcher diagnoses a missing script argument`, (t) => {
    const { caller, wrapper } = sandbox(t);
    const result = spawnSync(shell, [wrapper], { cwd: caller, encoding: "utf8" });
    assert.ifError(result.error);
    assert.equal(result.status, 1);
    assert.equal(result.stdout, "");
    assert.equal(result.stderr, "run-hook.cmd: missing script name\n");
  });
}
