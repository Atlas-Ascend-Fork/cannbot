// Copyright (c) 2026 CANNBot contributors
// SPDX-License-Identifier: MIT
// See script/LICENSE for the full license text.

import assert from "node:assert/strict";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";
import { installWorkspace } from "../lib/workspace-install.js";

const repository = resolve(import.meta.dirname, "../..");
const plugin = join(repository, "plugins-community/autoresearch");
const cli = join(repository, "script/bin/cannbot.js");

test("autoresearch packs the same Git exclusions used by its source workspace", () => {
  assert.equal(readFileSync(join(plugin, "gitignore.template"), "utf8"),
    readFileSync(join(plugin, ".gitignore"), "utf8"));
});

test("autoresearch legal-document filters work with Java and Python OAT", () => {
  const config = readFileSync(join(repository, "OAT.xml"), "utf8");
  const expected = ["LICENSE", "LICENSE-APACHE", "NOTICE", "README.OpenSource"];
  const filters = [...config.matchAll(
    /<filefilter name="(?:defaultPolicyFilter|licenseFileNamePolicyFilter)"[^>]*>([\s\S]*?)<\/filefilter>/g,
  )];
  assert.equal(filters.length, 2);
  for (const [, body] of filters) {
    const paths = [...body.matchAll(/type="filepath" name="(plugins-community\/autoresearch\/[^"]+)"/g)]
      .map((match) => match[1]);
    assert.equal(paths.length, expected.length);
    // Java OAT normalizes backslashes and splits values on | before compiling.
    const patterns = paths.flatMap((path) => path.replaceAll("\\", "/").split("|"))
      .map((path) => new RegExp(`^(?:${path})$`));
    for (const filename of expected) {
      assert.ok(patterns.some((pattern) => pattern.test(`plugins-community/autoresearch/${filename}`)));
    }
    for (const filename of ["scripts/decide.py", "LICENSE-extra", "README.OpenSource.bak", "READMExOpenSource"]) {
      assert.ok(patterns.every((pattern) => !pattern.test(`plugins-community/autoresearch/${filename}`)));
    }
  }
});

function sandbox(t) {
  const root = mkdtempSync(join(tmpdir(), "cannbot-autoresearch-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  return root;
}
function write(path, value) {
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, value);
}
function run(root, tool, source = "repository", target = join(root, "project with spaces")) {
  const args = [cli, "install", "autoresearch", "--tool", tool, "--target", target];
  if (source === "repository") args.push("--source", repository);
  return spawnSync(process.execPath, args, {
    cwd: root, encoding: "utf8", timeout: 30000,
    env: { ...process.env, HOME: join(root, "home"), CANNBOT_SKIP_DEPENDENCY_REPOS: "1",
      CANNBOT_SKIP_OPENCODE_PLUGIN_ADD: "1", XDG_CACHE_HOME: join(root, "cache") },
  });
}

for (const source of ["repository", "package"]) {
  for (const tool of ["claude", "opencode"]) {
    test(`autoresearch ${source} ${tool} preserves its workspace and user customization`, (t) => {
      const root = sandbox(t);
      const target = join(root, "project with spaces");
      const instructions = join(target, tool === "claude" ? "CLAUDE.md" : "AGENTS.md");
      write(instructions, "# User instructions\nKeep my instructions.\n");
      const preserved = ["config.yaml", "package.json", ".gitignore", "README.md"];
      for (const path of preserved) write(join(target, path), `user ${path}\n`);
      write(join(target, "ar_tasks/task1/state.json"), '{"phase":"EDIT"}\n');
      write(join(target, ".opencode/command/personal.md"), "personal command\n");
      const customHook = { matcher: "Read", hooks: [{ type: "command", command: "echo personal" }] };
      write(join(target, ".claude/settings.json"), JSON.stringify({ permissions: { deny: ["Bash(rm *)"] },
        env: { PERSONAL: "keep" }, hooks: { PreToolUse: [customHook] } }));
      const first = run(root, tool, source);
      assert.equal(first.status, 0, first.stderr || first.stdout);
      for (const path of ["scripts/decide.py", "scripts/engine/create_plan.py", "src/op_autoresearch/__init__.py",
        ".claude/hooks/cc_hook.py", ".claude/commands/autoresearch.md", ".claude/agents/ar-diagnosis.md",
        ".opencode/door.py", ".opencode/run_loop.py", ".opencode/plugin/autoresearch.js",
        ".opencode/command/autoresearch.md", ".opencode/agent/ar-diagnosis.md", "pyproject.toml",
        "LICENSE", "LICENSE-APACHE", "NOTICE", "SOURCE_REVISION", "README.OpenSource"]) {
        assert.deepEqual(readFileSync(join(target, path)), readFileSync(join(plugin, path)), path);
      }
      for (const path of ["workspace", "ar_tasks", ".session_tasks", ".task_dir_pointers"]) {
        assert.equal(existsSync(join(target, path)), true, path);
      }
      const second = run(root, tool, source);
      assert.equal(second.status, 0, second.stderr || second.stdout);
      for (const path of preserved) assert.equal(readFileSync(join(target, path), "utf8"), `user ${path}\n`);
      assert.equal(readFileSync(join(target, "ar_tasks/task1/state.json"), "utf8"), '{"phase":"EDIT"}\n');
      assert.equal(readFileSync(join(target, ".opencode/command/personal.md"), "utf8"), "personal command\n");
      const text = readFileSync(instructions, "utf8");
      assert.match(text, /Keep my instructions/);
      assert.equal(text.split("<!-- cannbot:autoresearch:start -->").length, 2);
      const settings = JSON.parse(readFileSync(join(target, ".claude/settings.json")));
      assert.deepEqual(settings.permissions, { deny: ["Bash(rm *)"] });
      assert.deepEqual(settings.env, { PERSONAL: "keep" });
      assert.deepEqual(settings.hooks.PreToolUse[0], customHook);
      for (const entries of Object.values(settings.hooks)) {
        assert.equal(new Set(entries.map((entry) => JSON.stringify(entry))).size, entries.length);
      }
      assert.equal(settings.hooks.Stop.length, 1);
      const record = JSON.parse(readFileSync(join(target, `.${tool}/cannbot-plugin.json`)))
        .plugins.find((entry) => entry.plugin === "autoresearch");
      assert.deepEqual(record.skills, []);
      assert.ok(record.workspace.includes("scripts/decide.py"));
    });
  }
}

test("autoresearch package is discoverable without a skills directory", (t) => {
  const root = sandbox(t);
  const packaged = join(repository, "script/dist/plugins/autoresearch");
  assert.equal(existsSync(join(packaged, "plugin-install.json")), true, "run build:plugins first");
  assert.equal(existsSync(join(packaged, "skills")), false);
  const result = run(root, "claude", "package");
  assert.equal(result.status, 0, result.stderr || result.stdout);
});

for (const tool of ["codex", "trae", "cursor", "copilot", "codearts", "dsh"]) {
  test(`autoresearch refuses unsupported ${tool} before creating a workspace`, (t) => {
    const root = sandbox(t);
    const result = run(root, tool);
    assert.notEqual(result.status, 0);
    assert.match(result.stderr, /supports only: claude, opencode|--tool must be one of:/);
    assert.equal(existsSync(join(root, "project with spaces")), false);
  });
}

function fixture(t) {
  const root = sandbox(t);
  const source = join(root, "source");
  const target = join(root, "target");
  write(join(source, "first.txt"), "new\n");
  write(join(source, "nested/last.txt"), "last\n");
  const workspace = { tools: ["claude", "opencode"], files: ["first.txt", "nested"], preserve: [], directories: [] };
  const save = () => write(join(source, "plugin-install.json"), JSON.stringify({ workspace }));
  save();
  write(join(target, "first.txt"), "old\n");
  return { root, source, target, workspace, save };
}
for (const side of ["source", "destination"]) {
  test(`workspace rejects ${side} symlink before replacing earlier files`, (t) => {
    const f = fixture(t);
    const external = join(f.root, "external");
    mkdirSync(external);
    write(join(external, "last.txt"), "outside\n");
    if (side === "source") rmSync(join(f.source, "nested"), { recursive: true });
    symlinkSync(external, join(side === "source" ? f.source : f.target, "nested"), "dir");
    assert.throws(() => installWorkspace(f.source, f.target, "claude"), /symlink/);
    assert.equal(readFileSync(join(f.target, "first.txt"), "utf8"), "old\n");
    assert.equal(existsSync(join(f.target, "first.txt.cannbot-backup")), false);
    assert.equal(readFileSync(join(external, "last.txt"), "utf8"), "outside\n");
  });
}
test("workspace rejects source/target overlap in either direction", (t) => {
  const f = fixture(t);
  for (const target of [f.source, join(f.source, "child"), f.root]) {
    assert.throws(() => installWorkspace(f.source, target, "claude"), /overlap/);
  }
  assert.equal(existsSync(join(f.source, "child")), false);
});
test("workspace validates all declared paths before modifying files", (t) => {
  const f = fixture(t);
  f.workspace.files.push("../outside.txt");
  f.save();
  assert.throws(() => installWorkspace(f.source, f.target, "claude"), /escapes root/);
  assert.equal(readFileSync(join(f.target, "first.txt"), "utf8"), "old\n");
});
test("workspace rejects malformed settings before copying any runtime", (t) => {
  const f = fixture(t);
  f.workspace.claudeSettings = ".claude/settings.json";
  f.save();
  write(join(f.source, ".claude/settings.json"), '{"hooks":{}}');
  write(join(f.target, ".claude/settings.json"), "invalid json");
  assert.throws(() => installWorkspace(f.source, f.target, "claude"), SyntaxError);
  assert.equal(readFileSync(join(f.target, "first.txt"), "utf8"), "old\n");
});
test("workspace backs up changed managed files once and retains unlisted files", (t) => {
  const f = fixture(t);
  write(join(f.target, "nested/personal.txt"), "keep\n");
  installWorkspace(f.source, f.target, "claude");
  installWorkspace(f.source, f.target, "claude");
  assert.equal(readFileSync(join(f.target, "first.txt.cannbot-backup"), "utf8"), "old\n");
  assert.equal(readFileSync(join(f.target, "first.txt"), "utf8"), "new\n");
  assert.equal(readFileSync(join(f.target, "nested/personal.txt"), "utf8"), "keep\n");
  assert.deepEqual(readdirSync(f.target).filter((path) => path.includes("backup")), ["first.txt.cannbot-backup"]);
});

test("installed AutoResearch command and both adapters run without hardware", (t) => {
  const python = spawnSync("python3", ["-c", "import yaml"], { encoding: "utf8" });
  if (python.status !== 0) {
    t.skip("Python 3 and PyYAML are required for runtime smoke checks");
    return;
  }
  const root = sandbox(t);
  const target = join(root, "project with spaces");
  const installed = run(root, "claude");
  assert.equal(installed.status, 0, installed.stderr || installed.stdout);
  const options = { cwd: target, encoding: "utf8", timeout: 30000,
    env: { ...process.env, PYTHONPATH: join(target, "src"), AR_SESSION_ID: "installation-smoke" } };
  const command = spawnSync("python3", ["scripts/engine/parse_args.py", "--resume"], options);
  assert.equal(command.status, 0, command.stderr);
  assert.equal(JSON.parse(command.stdout).mode, "resume");
  const hook = spawnSync("python3", [".claude/hooks/cc_hook.py", "pre_tool"], {
    ...options, input: JSON.stringify({ tool_name: "Read", tool_input: { file_path: "README.md" } }),
  });
  assert.equal(hook.status, 0, hook.stderr);
  const payload = Buffer.from(JSON.stringify({ kind: "pre_tool", tool: "Read", session_id: "installation-smoke" })).toString("base64");
  const door = spawnSync("python3", [".opencode/door.py", "event", payload], options);
  assert.equal(door.status, 0, door.stderr);
  assert.doesNotMatch(door.stderr, /internal error/);
  assert.equal(JSON.parse(door.stdout).block, false);
});

test("workspace rejects a declared source below a symlink ancestor", (t) => {
  const f = fixture(t);
  const external = join(f.root, "external");
  write(join(external, "last.txt"), "outside\n");
  symlinkSync(external, join(f.source, "alias"), "dir");
  f.workspace.files.push("alias/last.txt");
  f.save();
  assert.throws(() => installWorkspace(f.source, f.target, "claude"), /symlink/);
  assert.equal(readFileSync(join(f.target, "first.txt"), "utf8"), "old\n");
  assert.equal(existsSync(join(f.target, "alias")), false);
});

for (const location of ["file", "ancestor"]) {
  test(`workspace rejects Claude settings source symlink at ${location}`, (t) => {
    const f = fixture(t);
    const external = join(f.root, "external");
    write(join(external, "settings.json"), '{"hooks":{}}');
    mkdirSync(join(f.source, ".claude"), { recursive: true });
    if (location === "file") {
      symlinkSync(join(external, "settings.json"), join(f.source, ".claude/settings.json"));
    } else {
      rmSync(join(f.source, ".claude"), { recursive: true });
      symlinkSync(external, join(f.source, ".claude"), "dir");
    }
    f.workspace.claudeSettings = ".claude/settings.json";
    f.save();
    assert.throws(() => installWorkspace(f.source, f.target, "claude"), /symlink/);
    assert.equal(readFileSync(join(f.target, "first.txt"), "utf8"), "old\n");
    assert.equal(existsSync(join(f.target, ".claude/settings.json")), false);
  });
}

for (const tool of ["claude", "opencode"]) {
  for (const kind of ["instructions", "registry"]) {
    test(`autoresearch rejects ${tool} ${kind} destination symlink before runtime copies`, (t) => {
      const root = sandbox(t);
      const target = join(root, "project with spaces");
      const external = join(root, "external.txt");
      const content = kind === "registry" ? '{"plugins":[]}' : "external instructions\n";
      write(external, content);
      const path = kind === "registry" ? `.${tool}/cannbot-plugin.json`
        : tool === "claude" ? "CLAUDE.md" : "AGENTS.md";
      mkdirSync(dirname(join(target, path)), { recursive: true });
      symlinkSync(external, join(target, path));
      const result = run(root, tool);
      assert.notEqual(result.status, 0, "unsafe destination was accepted");
      assert.match(result.stderr, /symlink/);
      assert.equal(existsSync(join(target, "scripts")), false, "runtime was copied before rejection");
      assert.equal(readFileSync(external, "utf8"), content);
      assert.equal(existsSync(join(target, "config.yaml")), false);
    });
  }
}
