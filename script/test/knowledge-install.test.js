// Copyright (c) 2026 CANNBot contributors
// SPDX-License-Identifier: MIT

import assert from "node:assert/strict";
import { cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";

const cli = resolve(import.meta.dirname, "../bin/cannbot.js");
const sandboxes = new Set();
test.afterEach(() => {
  for (const sandbox of sandboxes) rmSync(sandbox, { recursive: true, force: true });
  sandboxes.clear();
});

// A local repository implements the public consumer/discover contract. No
// network, Python packages or real knowledge resources are needed by these tests.
function fixture() {
  const sandbox = mkdtempSync(join(tmpdir(), "cannbot-knowledge-"));
  sandboxes.add(sandbox);
  const repository = join(sandbox, "knowledge repository");
  const files = {
    "install.sh": `#!/usr/bin/env bash
set -eu
"\${CANNBOT_PYTHON:-python3}" - "$@" <<'PY'
import json, os, shlex, sys
from pathlib import Path
root = Path(__file__).resolve().parent if __file__ != '-' else Path.cwd()
tool, target, mode, *options = sys.argv[1:]
assert mode == 'consumer'
assert set(options) <= {'--skip-repository-update', '--skip-resources'}
(root / 'installer-args.json').write_text(json.dumps(sys.argv[1:]))
if os.environ.get('FIXTURE_INSTALL_FAIL') or tool == 'dsh':
    sys.exit('consumer installation refused')
target = Path(target)
for name in ['knowledge-query', 'ascendc-api-knowledge-query']:
    source = root / '.agents/skills' / name
    canonical = target / '.agents/skills' / name
    canonical.parent.mkdir(parents=True, exist_ok=True)
    if not canonical.is_symlink():
        canonical.symlink_to(source, target_is_directory=True)
    if tool in ['claude', 'trae']:
        adapter = target / ('.' + tool) / 'skills' / name
        adapter.parent.mkdir(parents=True, exist_ok=True)
        if not adapter.is_symlink():
            adapter.symlink_to(canonical, target_is_directory=True)
(target / '.cannbot/knowledge.env').write_text('CANNBOT_KNOWLEDGE_ROOT=' + shlex.quote(str(root)) + '\\n')
index = root / 'artifacts/indexes/knowledge.sqlite3'
index.parent.mkdir(parents=True, exist_ok=True)
index.write_text('prepared by consumer')
PY
`,
    ".agents/skills/knowledge-query/SKILL.md": "---\nname: knowledge-query\ndescription: Query fixture\n---\n",
    ".agents/skills/ascendc-api-knowledge-query/SKILL.md": "---\nname: ascendc-api-knowledge-query\ndescription: API fixture\n---\n",
    ".agents/skills/knowledge-query/scripts/knowledge_query.py": `import argparse, json, os, shlex, sys
from pathlib import Path
parser = argparse.ArgumentParser()
parser.add_argument('command', choices=['discover'])
parser.add_argument('--json', action='store_true')
args = parser.parse_args()
config = shlex.split(Path('.cannbot/knowledge.env').read_text())[0].split('=', 1)[1]
root = Path(os.environ.get('CANNBOT_KNOWLEDGE_ROOT', config))
assert (root / 'governance/contract.txt').is_file(), 'expected repository root'
assert (root / 'artifacts/indexes/knowledge.sqlite3').is_file(), 'index is missing'
if os.environ.get('FIXTURE_DISCOVER_FAIL'):
    sys.exit('knowledge index is stale')
if os.environ.get('FIXTURE_DISCOVER_INVALID'):
    print('{}')
else:
    reported_root = '/' if os.environ.get('FIXTURE_DISCOVER_WRONG_ROOT') else str(root)
    print(json.dumps({'schema_version': 'knowledge-discovery.v1', 'root': reported_root, 'cards': 2}))
`,
    "governance/contract.txt": "same checkout contract\n",
    // A legacy marker must never bypass consumer installation or discovery.
    "knowledge/search/okf.index.json": "{}\n",
  };
  const write = (path, content) => {
    mkdirSync(dirname(path), { recursive: true });
    writeFileSync(path, content);
  };
  for (const [path, content] of Object.entries(files)) write(join(repository, path), content);
  for (const args of [
    ["init", "--quiet"], ["add", "-A"],
    ["-c", "user.name=test", "-c", "user.email=test@example.com", "commit", "--quiet", "-m", "fixture"],
  ]) {
    const result = spawnSync("git", args, { cwd: repository, encoding: "utf8" });
    assert.equal(result.status, 0, result.stderr);
  }
  const source = join(sandbox, "bundle");
  const plugin = join(source, "plugins-official", "knowledge-fixture");
  write(join(plugin, ".claude-plugin/plugin.json"), JSON.stringify({
    name: "knowledge-fixture", version: "1.0.0", description: "Knowledge install fixture",
  }));
  write(join(plugin, "skills/demo/SKILL.md"), "---\nname: demo\ndescription: Demo\n---\n");
  write(join(plugin, "plugin-install.json"), JSON.stringify({
    dependencies: [{ name: "cannbot-knowledge", repository }],
  }));
  const target = join(sandbox, "项目 with spaces");
  mkdirSync(target);
  const checkout = join(target, ".cannbot/dependencies/knowledge-fixture/cannbot-knowledge");
  const install = (tool, env = {}) => spawnSync(process.execPath, [
    cli, "install", "knowledge-fixture", "--tool", tool, "--target", target, "--source", source,
  ], {
    cwd: sandbox,
    encoding: "utf8",
    env: {
      ...process.env,
      HOME: join(sandbox, "home"), XDG_CACHE_HOME: join(sandbox, "cache"),
      CANNBOT_SKIP_CODEX_PLUGIN_ADD: "1", CANNBOT_SKIP_OPENCODE_PLUGIN_ADD: "1",
      CANNBOT_SKIP_DEPENDENCY_REPOS: "0", CANNBOT_SKIP_KNOWLEDGE_INDEX: "0",
      CANNBOT_SKIP_KNOWLEDGE_RESOURCES: "0", CANNBOT_PYTHON: "python3",
      CANNBOT_KNOWLEDGE_ROOT: undefined,
      ...env,
    },
  });
  const record = (tool) => JSON.parse(readFileSync(join(target, `.${tool}/cannbot-plugin.json`), "utf8"))
    .plugins.find((entry) => entry.plugin === "knowledge-fixture");
  return { sandbox, repository, source, plugin, target, checkout, install, record };
}

for (const tool of ["opencode", "codex", "claude", "trae"]) {
  test(`${tool} installs a usable knowledge consumer from the full checkout`, () => {
    const f = fixture();
    const result = f.install(tool);
    assert.equal(result.status, 0, result.stderr || result.stdout);
    assert.equal(f.record(tool).knowledgeIndex, "ready");
    assert.deepEqual(JSON.parse(readFileSync(join(f.checkout, "installer-args.json"), "utf8")),
      [tool, f.target, "consumer", "--skip-repository-update"]);
    for (const name of ["knowledge-query", "ascendc-api-knowledge-query"]) {
      assert.equal(realpathSync(join(f.target, ".agents/skills", name)),
        realpathSync(join(f.checkout, ".agents/skills", name)));
      if (tool === "claude" || tool === "trae") {
        assert.equal(realpathSync(join(f.target, `.${tool}/skills`, name)),
          realpathSync(join(f.checkout, ".agents/skills", name)));
      }
    }
    assert.ok(existsSync(join(f.target, ".cannbot/knowledge.env")));
    assert.match(result.stdout, /discover verified/);
    const again = f.install(tool);
    assert.equal(again.status, 0, again.stderr || again.stdout);
    assert.equal(f.record(tool).knowledgeIndex, "ready");
  });
}

for (const [name, env, message] of [
  ["installer failure", { FIXTURE_INSTALL_FAIL: "1" }, /installer exit/],
  ["unusable index", { FIXTURE_DISCOVER_FAIL: "1" }, /knowledge index is stale/],
  ["invalid discovery", { FIXTURE_DISCOVER_INVALID: "1" }, /did not confirm/],
  ["different knowledge root", { FIXTURE_DISCOVER_WRONG_ROOT: "1" }, /did not confirm/],
]) {
  test(`${name} stays pending and reports a repair command`, () => {
    const f = fixture();
    const result = f.install("codex", env);
    assert.equal(result.status, 0, result.stderr || result.stdout);
    assert.equal(f.record("codex").knowledgeIndex, "pending");
    assert.match(result.stderr, message);
    assert.match(result.stderr, /repair: bash .*install.sh/);
    assert.doesNotMatch(result.stderr, /first query will retry/);
    assert.doesNotMatch(result.stdout, /knowledge index: ready/);
  });
}

test("an explicit offline install delegates resource skipping to the consumer", () => {
  const f = fixture();
  const result = f.install("codex", { CANNBOT_SKIP_KNOWLEDGE_RESOURCES: "1" });
  assert.equal(result.status, 0, result.stderr);
  assert.equal(f.record("codex").knowledgeIndex, "ready");
  assert.ok(JSON.parse(readFileSync(join(f.checkout, "installer-args.json"), "utf8")).includes("--skip-resources"));
});

test("explicit knowledge or repository skipping does not run the consumer", () => {
  for (const env of [{ CANNBOT_SKIP_KNOWLEDGE_INDEX: "1" }, { CANNBOT_SKIP_DEPENDENCY_REPOS: "1" }]) {
    const f = fixture();
    const result = f.install("codex", env);
    assert.equal(result.status, 0, result.stderr);
    assert.equal(f.record("codex").knowledgeIndex, "pending");
    assert.equal(existsSync(join(f.checkout, "installer-args.json")), false);
  }
});

test("an unsupported consumer client does not prevent plugin installation", () => {
  const f = fixture();
  const result = f.install("dsh");
  assert.equal(result.status, 0, result.stderr);
  assert.equal(f.record("dsh").knowledgeIndex, "pending");
  assert.match(result.stderr, /consumer installation refused/);
});

test("a generic public initializer still installs the knowledge consumer", () => {
  const f = fixture();
  const realPlugin = resolve(import.meta.dirname, "../../plugins-official/ops-perf-optimize");
  cpSync(join(realPlugin, "init.sh"), join(f.plugin, "init.sh"));
  cpSync(join(realPlugin, "installer"), join(f.plugin, "installer"), { recursive: true });
  const target = join(f.sandbox, "public init target");
  mkdirSync(target);
  const result = spawnSync("bash", [join(f.plugin, "init.sh"), "project", "codex", target], {
    cwd: f.plugin,
    encoding: "utf8",
    env: {
      ...process.env,
      HOME: join(f.sandbox, "home"), XDG_CACHE_HOME: join(f.sandbox, "cache"),
      CANNBOT_INIT_CONTEXT: JSON.stringify({ plugin: "knowledge-fixture", tool: "codex", target }),
      CANNBOT_TOOL: "codex", CANNBOT_TARGET_DIR: target,
      CANNBOT_SKIP_KNOWLEDGE_RESOURCES: "1", CANNBOT_PYTHON: "python3",
      CANNBOT_SKIP_OPMODEL_INSTALL: "1",
    },
  });
  assert.equal(result.status, 0, result.stderr || result.stdout);
  const checkout = join(target, ".cannbot/dependencies/knowledge-fixture/cannbot-knowledge");
  assert.ok(existsSync(join(target, ".cannbot/knowledge.env")));
  for (const name of ["knowledge-query", "ascendc-api-knowledge-query"]) {
    assert.equal(realpathSync(join(target, ".agents/skills", name)),
      realpathSync(join(checkout, ".agents/skills", name)));
  }
  assert.match(result.stdout, /knowledge index: ready/);
});
