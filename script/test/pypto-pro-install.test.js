// Copyright (c) 2026 CANNBot contributors
// SPDX-License-Identifier: MIT

import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { lstatSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const repository = fileURLToPath(new URL("../..", import.meta.url));
const cli = join(repository, "script/bin/cannbot.js");
const plugin = join(repository, "plugins-community/pypto-pro-op-orchestrator");
const skills = [
  "pypto-pro-kernel",
];

test("PyPTO-Pro installs its shared Skills and usable instructions for each client", (t) => {
  const root = mkdtempSync(join(tmpdir(), "pypto-pro-install-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const dependency = join(root, "cannbot-skills");
  const home = join(root, "home");
  mkdirSync(dependency);
  mkdirSync(home);
  execFileSync("git", ["init", "-q", "-b", "master", dependency]);
  for (const name of skills) {
    const directory = join(dependency, "community/ops", name);
    mkdirSync(directory, { recursive: true });
    writeFileSync(join(directory, "SKILL.md"), `---\nname: ${name}\ndescription: fixture\n---\n`);
  }
  execFileSync("git", ["-C", dependency, "add", "."]);
  execFileSync("git", ["-C", dependency, "-c", "user.name=Test", "-c", "user.email=test@example.org",
    "commit", "-qm", "Create shared Skill fixtures"]);

  for (const [tool, directory, instructions] of [
    ["opencode", ".agents/skills", "AGENTS.md"],
    ["codex", ".agents/skills", "AGENTS.md"],
    ["claude", ".claude/skills", "CLAUDE.md"],
    ["codearts", ".codeartsdoer/skills", "AGENTS.md"],
  ]) {
    const target = join(root, tool);
    const env = {
      ...process.env,
      HOME: home,
      PATH: `${dirname(process.execPath)}:${process.env.PATH}`,
      CANNBOT_SKIP_OPENCODE_PLUGIN_ADD: "1",
      GIT_CONFIG_GLOBAL: "/dev/null",
      GIT_CONFIG_SYSTEM: "/dev/null",
      GIT_CONFIG_COUNT: "1",
      GIT_CONFIG_KEY_0: `url.file://${dependency}.insteadOf`,
      GIT_CONFIG_VALUE_0: "https://gitcode.com/cann/cannbot-skills.git",
    };
    delete env.CANNBOT_SKIP_DEPENDENCY_REPOS;
    const result = spawnSync(process.execPath, [cli, "install", "pypto-pro-op-orchestrator",
      "--source", repository, "--plugin-dir", plugin, "--tool", tool, "--target", target],
    { env, encoding: "utf8", timeout: 60000 });
    assert.equal(result.status, 0, result.stdout + result.stderr);
    for (const name of skills) {
      const installed = join(target, directory, name);
      assert.ok(lstatSync(installed).isSymbolicLink(), `${tool}: ${name}`);
      assert.match(readFileSync(join(installed, "SKILL.md"), "utf8"), new RegExp(`name: ${name}`));
    }
    const text = readFileSync(join(target, instructions), "utf8");
    assert.match(text, /pypto-pro-kernel/);
    assert.match(text, /\.cannbot\/plugins\/pypto-pro-op-orchestrator\/workflows\/references\/multi-agent-workflow\.md/);
    assert.doesNotMatch(text, /\$CANNBOT_CONFIG_ROOT/);
  }
});
