// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// SPDX-License-Identifier: MIT
// See script/LICENSE for the full license text.

import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";
import { registerSettingsHook } from "../bin/cannbot.js";

const cli = resolve(import.meta.dirname, "../bin/cannbot.js");
const matchers = [
  "Write|Edit",
  "Question",
  "AskUserQuestion",
  "OtherQuestionTool",
  "Custom|Write|Edit",
  "^(Write|Edit)$",
  "Write|Edit|MultiEdit|NotebookEdit|Question",
  "",
  "*",
];
const required = {
  claude: ["Write", "Edit", "MultiEdit", "NotebookEdit", "Question"],
  trae: ["AskUserQuestion"],
};

function installTwice(tool, matcher) {
  const sandbox = mkdtempSync(join(tmpdir(), "cannbot-hook-matchers-"));
  try {
    const bundle = join(sandbox, "bundle");
    const plugin = join(bundle, "plugins-official", "hook-fixture");
    mkdirSync(join(plugin, ".claude-plugin"), { recursive: true });
    mkdirSync(join(plugin, "skills"));
    mkdirSync(join(plugin, "hooks", tool), { recursive: true });
    writeFileSync(join(plugin, ".claude-plugin", "plugin.json"), JSON.stringify({
      name: "hook-fixture", version: "1.0.0", skills: [],
    }));
    // Installation copies this fixture; the client guard is not executed here.
    writeFileSync(join(plugin, "hooks", tool, "permission-guard.js"), "// fixture\n");
    const target = join(sandbox, "project");
    const config = join(target, `.${tool}`);
    mkdirSync(config, { recursive: true });
    const settings = join(config, tool === "claude" ? "settings.json" : "hooks.json");
    const hook = {
      type: "command", command: "node",
      args: [`${"${CLAUDE_PROJECT_DIR}"}/.${tool}/hooks/permission-guard.js`],
      timeout: 17,
    };
    const unrelated = { matcher: "Bash", hooks: [{ type: "command", command: "echo custom" }] };
    const original = {
      custom: { enabled: true },
      hooks: { Stop: [{ hooks: [{ type: "command", command: "echo stop" }] }],
        PreToolUse: matcher === undefined ? [unrelated] : [{ matcher, hooks: [hook] }, unrelated] },
    };
    writeFileSync(settings, `${JSON.stringify(original, null, 2)}\n`);
    const snapshots = [];
    for (let attempt = 0; attempt < 2; attempt += 1) {
      const result = spawnSync(process.execPath, [
        cli, "install", "hook-fixture", "--source", bundle, "--tool", tool, "--target", target,
      ], { cwd: target, encoding: "utf8" });
      assert.equal(result.status, 0, result.stderr || result.stdout);
      snapshots.push(JSON.parse(readFileSync(settings, "utf8")));
    }
    const [first, second] = snapshots;
    assert.deepEqual(second, first, "reinstallation must be idempotent");
    assert.deepEqual(first.custom, original.custom);
    assert.deepEqual(first.hooks.Stop, original.hooks.Stop);
    assert.equal(first.hooks.PreToolUse.length, 2);
    const group = first.hooks.PreToolUse.find((entry) => entry.hooks.some(
      (entryHook) => entryHook.args?.[0]?.endsWith("/hooks/permission-guard.js"),
    ));
    assert.deepEqual(first.hooks.PreToolUse.filter((entry) => entry !== group), [unrelated]);
    assert.equal(group.hooks.length, 1);
    if (matcher !== undefined) assert.deepEqual(group.hooks[0], hook);
    if (matcher === "" || matcher === "*") {
      assert.equal(group.matcher, matcher, "keep existing match-all coverage");
    } else {
      if (matcher !== undefined) {
        assert.ok(group.matcher.startsWith(matcher), "preserve the existing matcher expression");
      }
      for (const toolName of required[tool]) {
        assert.ok(group.matcher.split("|").includes(toolName), `missing ${toolName}: ${group.matcher}`);
      }
    }
  } finally {
    rmSync(sandbox, { recursive: true, force: true });
  }
}

for (const tool of Object.keys(required)) {
  for (const matcher of matchers) {
    test(`${tool} reinstallation completes matcher ${JSON.stringify(matcher)}`, () => {
      installTwice(tool, matcher);
    });
  }
  test(`${tool} installs a complete new hook without replacing unrelated groups`, () => {
    installTwice(tool);
  });
}


// Call the production function directly; CLI installation tests above remain intact.
function withNativeSettings(matcher, check) {
  const sandbox = mkdtempSync(join(tmpdir(), "cannbot-hook-matcher-unit-"));
  try {
    const settings = join(sandbox, "settings.json");
    const guard = { type: "command", command: "node", args: ["permission-guard.js"], timeout: 17 };
    const original = {
      custom: { enabled: true },
      hooks: {
        Stop: [{ hooks: [{ type: "command", command: "echo stop" }] }],
        PreToolUse: [
          { matcher, hooks: [guard] },
          { matcher: "Bash", hooks: [{ type: "command", command: "echo custom" }] },
        ],
      },
    };
    writeFileSync(settings, `${JSON.stringify(original, null, 2)}\n`);
    check(settings, original);
  } finally {
    rmSync(sandbox, { recursive: true, force: true });
  }
}

for (const matcher of ["", "*"]) {
  test(`registerSettingsHook retains match-all ${JSON.stringify(matcher)} without rewriting`, () => {
    withNativeSettings(matcher, (settings) => {
      const before = readFileSync(settings, "utf8");
      assert.equal(registerSettingsHook(settings, "replacement.js", required.claude.join("|")), false);
      assert.equal(readFileSync(settings, "utf8"), before);
    });
  });
}

test("registerSettingsHook appends only missing complete alternatives and keeps other settings", () => {
  withNativeSettings("Custom|Write|Edit|OtherQuestionTool", (settings, original) => {
    assert.equal(registerSettingsHook(settings, "replacement.js", required.claude.join("|")), true);
    const expected = structuredClone(original);
    expected.hooks.PreToolUse[0].matcher =
      "Custom|Write|Edit|OtherQuestionTool|MultiEdit|NotebookEdit|Question";
    assert.deepEqual(JSON.parse(readFileSync(settings, "utf8")), expected);
    const before = readFileSync(settings, "utf8");
    assert.equal(registerSettingsHook(settings, "replacement.js", required.claude.join("|")), false);
    assert.equal(readFileSync(settings, "utf8"), before, "second call must not append duplicates");
  });
});

test("registerSettingsHook leaves fully covered alternatives byte-for-byte unchanged", () => {
  withNativeSettings("Custom|Question|NotebookEdit|MultiEdit|Edit|Write", (settings) => {
    const before = readFileSync(settings, "utf8");
    assert.equal(registerSettingsHook(settings, "replacement.js", required.claude.join("|")), false);
    assert.equal(readFileSync(settings, "utf8"), before);
  });
});
