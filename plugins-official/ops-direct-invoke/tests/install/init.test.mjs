// Copyright (c) 2026 CANNBot contributors
// SPDX-License-Identifier: MIT

import assert from "node:assert/strict";
import { cpSync, existsSync, lstatSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, realpathSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";
import { assemblePlugins } from "../../../../script/lib/plugin-bundle.js";
import { prepareDirectInvokeConfig } from "../../tools/direct-invoke-config.mjs";

const repository = resolve(import.meta.dirname, "../../../..");
const cli = join(repository, "script/bin/cannbot.js");
const selected = ["ops-direct-invoke", "ops-direct-invoke-maintain", "ops-direct-invoke-repo-guide", "ops-direct-invoke-requirement"];
const answers = { repo: "common", platform: "ascend", chip: "Ascend950",
  preferences: { interaction: "confirm", autonomy: "仅已明确授权范围", review_points: [] } };

function write(path, value) {
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, typeof value === "string" ? value : `${JSON.stringify(value, null, 2)}\n`);
}

function fixture(t) {
  const box = mkdtempSync(join(tmpdir(), "direct-init-"));
  t.after(() => rmSync(box, { recursive: true, force: true }));
  const source = join(box, "source");
  mkdirSync(join(source, ".git"), { recursive: true });
  write(join(source, "LICENSE"), "main license");
  write(join(source, "plugins-official/LICENSE"), "plugin license");
  const plugin = join(source, "plugins-official/ops-direct-invoke");
  const entries = { maintain: "maintain", orchestrator: "orchestrator",
    "custom-skills/requirement/ascend": "requirement", "custom-skills/requirement/kirin": "requirement",
    "custom-skills/repo-guide/common": "repo-guide", "custom-skills/repo-guide/cannbench": "repo-guide" };
  for (const [path, name] of Object.entries(entries)) {
    write(join(plugin, "skills", path, "SKILL.md"), `---\nname: ${name === "orchestrator" ? "ops-direct-invoke" : `ops-direct-invoke-${name}`}\ndescription: ${path}\ndisable-model-invocation: true\n---\n${path}\n`);
  }
  write(join(plugin, "skills/custom-skills/requirement/references/shared.md"), "shared requirement reference");
  for (const platform of ["ascend", "kirin"]) {
    symlinkSync("../references", join(plugin, "skills/custom-skills/requirement", platform, "references"));
  }
  for (const platform of ["ascend", "kirin"]) {
    write(join(plugin, "skills/custom-skills/env-check", platform, "platform.json"), { languages: ["ascendc"] });
  }
  for (const path of ["tools/runtime.py", "docs/contract.md", "orchestrations/tasks/task.yaml", "agents/developer.md", "skills/custom-skills/common/shared.md"]) {
    write(join(plugin, path), path);
  }
  write(join(source, "shared/short/SKILL.md"), "---\nname: public-dependency\ndescription: dependency\ndisable-model-invocation: true\n---\n");
  write(join(source, "shared/short/scripts/run.py"), "print('dependency')\n");
  write(join(plugin, ".claude-plugin/plugin.json"), { name: "ops-direct-invoke", version: "1.0.0", description: "fixture", skills: ["./skills/maintain", "./skills/orchestrator"] });
  write(join(plugin, "plugin-sources.json"), { skillsRepository: ".", skills: ["shared/short"], skillInstallMode: "symlink", preserveSkillInvocationPolicy: true, extraAssets: ["skills/custom-skills"] });
  write(join(plugin, "plugin-install.json"), { initializer: "tools/install.mjs", initializeBefore: ["ops-perf-optimize"] });
  for (const name of ["install.mjs", "direct-invoke-config.mjs"]) cpSync(join(repository, "plugins-official/ops-direct-invoke/tools", name), join(plugin, "tools", name));
  const perf = join(source, "plugins-official/ops-perf-optimize");
  write(join(perf, ".claude-plugin/plugin.json"), { name: "ops-perf-optimize", version: "1.0.0", description: "perf" });
  write(join(perf, "plugin-sources.json"), { skillsRepository: ".", skills: [], skillInstallMode: "symlink" });
  write(join(perf, "skills/ops-perf-optimize-workflow/SKILL.md"), "---\nname: ops-perf-optimize-workflow\ndescription: perf\n---\n");
  write(join(perf, "scripts/run.py"), "print('perf')\n");
  write(join(perf, "AGENTS.md"), "performance instructions\n");
  write(join(perf, "installer/install-opmodel.sh"), '#!/usr/bin/env bash\nset -eu\nprintf "%s\\n" "$1" >> "$2/opmodel-calls.txt"\nexit "${CANNBOT_FIXTURE_OPMODEL_EXIT:-0}"\n');
  const target = join(box, "project");
  const input = join(box, "answers.json");
  write(input, answers);
  const env = { ...process.env, HOME: join(box, "home"), CANNBOT_SKIP_DEPENDENCY_REPOS: "1",
    CANNBOT_SKIP_CODEX_PLUGIN_ADD: "1", CANNBOT_SKIP_OPENCODE_PLUGIN_ADD: "1", CANNBOT_SKIP_KNOWLEDGE_INDEX: "1" };
  const install = (root = source, tool = "codex", config = input) => spawnSync(process.execPath,
    [cli, "install", "ops-direct-invoke", "--source", root, "--target", target, "--tool", tool], { encoding: "utf8", env: { ...env, CANNBOT_DIRECT_INVOKE_CONFIG: config ?? "" } });
  return { box, source, plugin, target, input, env, install };
}

for (const packaged of [false, true]) {
  for (const tool of ["codex", "opencode", "claude", "trae", "dsh", "codearts"]) {
    test(`${packaged ? "package" : "source"} initializes selected Skills and isolated performance for ${tool}`, (t) => {
      const f = fixture(t);
      let root = f.source;
      if (packaged) {
        root = join(f.box, "package");
        assemblePlugins(f.source, join(root, "dist"), ["ops-direct-invoke", "ops-perf-optimize"]);
      }
      const result = f.install(root, tool);
      assert.equal(result.status, 0, result.stdout + result.stderr);
      const config = JSON.parse(readFileSync(join(f.target, ".cannbot/ops-direct-invoke.json")));
      assert.equal(config.repo, "common");
      assert.equal(config.language, undefined);
      const configDir = tool === "codearts" ? ".codeartsdoer" : `.${tool}`;
      const skillsDir = tool === "codex" || tool === "opencode" ? ".agents/skills" : `${configDir}/skills`;
      assert.deepEqual(readdirSync(join(f.target, skillsDir)).sort(), selected);
      const requirement = join(f.target, skillsDir, "ops-direct-invoke-requirement");
      assert.equal(realpathSync(requirement), realpathSync(join(config.asset_root, "skills/custom-skills/requirement/ascend")));
      assert.equal(readFileSync(resolve(requirement, "references/shared.md"), "utf8"), "shared requirement reference");
      assert.equal(existsSync(join(f.env.HOME, "plugins/ops-perf-optimize")), false);
      assert.equal(existsSync(join(f.env.HOME, "plugins/ops-direct-invoke")), false);
      assert.equal(existsSync(join(f.target, "AGENTS.md")), false);
      const record = JSON.parse(readFileSync(join(f.target, configDir, "cannbot-plugin.json")));
      assert.deepEqual(record.plugins.map((entry) => entry.plugin), ["ops-direct-invoke"]);
      const perf = JSON.parse(readFileSync(config.performance_registry)).plugins[0];
      assert.equal(perf.plugin, "ops-perf-optimize");
      assert.ok(existsSync(join(config.performance_root, perf.skills[0], "SKILL.md")));
      assert.equal(readFileSync(join(config.performance_root, "opmodel-calls.txt"), "utf8"), `${tool}\n`);
      for (const path of ["tools/runtime.py", "docs/contract.md", "orchestrations/tasks/task.yaml", "agents/developer.md",
        "skills/custom-skills/requirement/kirin/SKILL.md", "skills/custom-skills/common/shared.md",
        "external-skills/public-dependency/scripts/run.py"]) assert.ok(existsSync(join(config.asset_root, path)), path);
      assert.match(readFileSync(join(config.external_skills_root, "public-dependency/SKILL.md"), "utf8"), /disable-model-invocation: true/);
      assert.ok(result.stdout.indexOf("Installed ops-perf-optimize@") < result.stdout.indexOf("Installed ops-direct-invoke@"));
      write(join(f.target, "USER.md"), "keep user file");
      write(join(f.target, ".cannbot/runs/existing/context.json"), "frozen run");
      const repeated = f.install(root, tool, null);
      assert.equal(repeated.status, 0, repeated.stdout + repeated.stderr);
      assert.equal(readFileSync(join(f.target, ".cannbot/runs/existing/context.json"), "utf8"), "frozen run");
      assert.equal(readFileSync(join(f.target, "USER.md"), "utf8"), "keep user file");
      write(join(f.plugin, "skills/custom-skills/requirement/references/shared.md"), "updated source reference");
      assert.equal(readFileSync(resolve(requirement, "references/shared.md"), "utf8"),
        packaged ? "shared requirement reference" : "updated source reference");
    });
  }
}

test("unchanged performance source init invokes its OpModel initializer exactly once", (t) => {
  const f = fixture(t);
  const perf = join(f.source, "plugins-official/ops-perf-optimize");
  cpSync(join(repository, "plugins-official/ops-perf-optimize/init.sh"), join(perf, "init.sh"));
  mkdirSync(join(f.source, "script/bin"), { recursive: true });
  symlinkSync(cli, join(f.source, "script/bin/cannbot.js"));
  cpSync(join(repository, "script/bin/source-plugin-init.sh"), join(f.source, "script/bin/source-plugin-init.sh"));
  const result = spawnSync("bash", [join(perf, "init.sh"), "project", "dsh", f.target], { env: f.env, encoding: "utf8" });
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.equal(readFileSync(join(f.target, "opmodel-calls.txt"), "utf8"), "dsh\n");
});

test("optional OpModel failure continues while strict failure stops initialization", (t) => {
  const f = fixture(t);
  const args = [cli, "install", "ops-direct-invoke", "--source", f.source, "--target", f.target,
    "--tool", "dsh"];
  for (const strict of ["1", "0"]) {
    const result = spawnSync(process.execPath, args, { encoding: "utf8",
      env: { ...f.env, CANNBOT_DIRECT_INVOKE_CONFIG: f.input, CANNBOT_FIXTURE_OPMODEL_EXIT: "7", CANNBOT_OPMODEL_STRICT: strict } });
    assert.equal(result.status === 0, strict === "0", result.stdout + result.stderr);
    assert.match(result.stderr, /OpModel setup unavailable/);
    if (strict === "1") assert.equal(existsSync(join(f.target, ".cannbot/ops-direct-invoke.json")), false);
  }
});

test("missing noninteractive answers fail before any installation", (t) => {
  const f = fixture(t);
  const result = f.install(f.source, "dsh", null);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /needs initialization answers.*platform/);
  assert.equal(existsSync(f.target), false);
});

test("noninteractive cannbench with Kirin fails before any installation", (t) => {
  const f = fixture(t);
  write(f.input, { ...answers, repo: "cannbench", platform: "kirin" });
  const result = f.install(f.source, "dsh");
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /cannbench.*Ascend.*Kirin.*common/);
  assert.equal(existsSync(f.target), false);
});

test("questionnaire corrects an incompatible saved repository without adding questions", async (t) => {
  const f = fixture(t);
  write(join(f.target, ".cannbot/ops-direct-invoke.json"), { ...answers, repo: "cannbench", platform: "kirin" });
  const replies = ["cannbench", ""];
  const prompts = [];
  const messages = [];
  const config = await prepareDirectInvokeConfig({ target: f.target, tool: "dsh" }, {
    isTTY: true, question: async (prompt) => { prompts.push(prompt); return replies.shift(); },
    log: (message) => messages.push(message),
  });
  assert.equal(config.repo, "common");
  assert.equal(config.platform, "kirin");
  assert.equal(config.sources.repo, "questionnaire");
  assert.equal(prompts.length, 2);
  prompts.forEach((prompt) => assert.match(prompt, /^\(1\/1\).*common/));
  assert.match(messages[0], /cannbench.*Ascend.*Kirin.*common/);
});

test("questionnaire counts only pending answers and never asks for a language", async (t) => {
  const f = fixture(t);
  write(join(f.target, ".cannbot/ops-direct-invoke.json"), { ...answers, chip: "" });
  const prompts = [];
  const config = await prepareDirectInvokeConfig({ target: f.target, tool: "dsh" }, {
    isTTY: true, question: async (prompt) => { prompts.push(prompt); return "Ascend910"; },
  });
  assert.equal(prompts.length, 1);
  assert.match(prompts[0], /^\(1\/1\).*芯片/);
  assert.equal(config.chip, "Ascend910");
  assert.equal(config.language, undefined);
});

test("changing platform requires a new chip answer and rejects invalid explicit choices", async (t) => {
  const f = fixture(t);
  write(join(f.target, ".cannbot/ops-direct-invoke.json"), answers);
  write(f.input, { platform: "kirin" });
  await assert.rejects(prepareDirectInvokeConfig({ target: f.target, tool: "dsh", initConfig: f.input }, { isTTY: false }), /chip/);
  write(f.input, { platform: "unknown" });
  await assert.rejects(prepareDirectInvokeConfig({ target: f.target, tool: "dsh", initConfig: f.input }), /invalid initialization value: platform/);
});

test("source init forwards optional configuration to the same installer", (t) => {
  const f = fixture(t);
  cpSync(join(repository, "plugins-official/ops-direct-invoke/init.sh"), join(f.plugin, "init.sh"));
  mkdirSync(join(f.source, "script/bin"), { recursive: true });
  symlinkSync(cli, join(f.source, "script/bin/cannbot.js"));
  cpSync(join(repository, "script/bin/source-plugin-init.sh"), join(f.source, "script/bin/source-plugin-init.sh"));
  const result = spawnSync("bash", [join(f.plugin, "init.sh"), "project", "dsh", f.target, "--init-config", f.input], { env: f.env, encoding: "utf8" });
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.equal(realpathSync(join(f.target, ".dsh/skills/ops-direct-invoke-requirement")), realpathSync(join(f.plugin, "skills/custom-skills/requirement/ascend")));
});

test("reinitialization removes only obsolete registrations owned by this plugin", (t) => {
  const f = fixture(t);
  assert.equal(f.install(f.source, "dsh").status, 0);
  const registry = join(f.target, ".dsh/cannbot-plugin.json");
  const records = JSON.parse(readFileSync(registry));
  const old = ".dsh/skills/old-direct-entry";
  const shared = ".dsh/skills/shared-with-another-plugin";
  for (const path of [old, shared, ".dsh/skills/user-skill"]) write(join(f.target, path, "SKILL.md"), "keep unless managed");
  records.plugins[0].skills.push(old, shared);
  records.plugins.push({ plugin: "another-plugin", skills: [shared] });
  write(registry, records);
  const result = f.install(f.source, "dsh", null);
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.equal(existsSync(join(f.target, old)), false);
  assert.ok(existsSync(join(f.target, shared, "SKILL.md")));
  assert.ok(existsSync(join(f.target, ".dsh/skills/user-skill/SKILL.md")));
});

test("an unrelated existing entry is not overwritten by initialization", (t) => {
  const f = fixture(t);
  const entry = join(f.target, ".dsh/skills/ops-direct-invoke-requirement/SKILL.md");
  write(entry, "user source");
  const result = f.install(f.source, "dsh");
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /not exclusively managed/);
  assert.equal(readFileSync(entry, "utf8"), "user source");
  assert.equal(existsSync(join(f.target, ".cannbot/dependencies/ops-direct-invoke/performance")), false);
});

test("switching clients reuses confirmed answers and the shared main Skill registrations", (t) => {
  const f = fixture(t);
  assert.equal(f.install(f.source, "opencode").status, 0);
  const result = f.install(f.source, "codex", null);
  assert.equal(result.status, 0, result.stdout + result.stderr);
  const config = JSON.parse(readFileSync(join(f.target, ".cannbot/ops-direct-invoke.json")));
  assert.equal(config.tool, "codex");
  assert.deepEqual(readdirSync(join(f.target, ".agents/skills")).sort(), selected);
});

for (const platform of ["ascend", "kirin"]) {
  test(`first ${platform} questionnaire uses the actual six pending questions and confirms defaults`, async (t) => {
    const f = fixture(t);
    const replies = [platform, "", "unknown", "", "", "需求,交付"];
    const prompts = [];
    const config = await prepareDirectInvokeConfig({ target: f.target, tool: "dsh" }, {
      isTTY: true, question: async (prompt) => { prompts.push(prompt); return replies.shift(); },
    });
    assert.equal(prompts.length, 6);
    prompts.forEach((prompt, index) => assert.ok(prompt.startsWith(`(${index + 1}/6)`)));
    assert.equal(config.repo, platform === "ascend" ? "cannbench" : "common");
    assert.deepEqual(config.preferences.review_points, ["需求", "交付"]);
  });
}

for (const packaged of [false, true]) {
  test(`${packaged ? "package" : "source"} preserves standalone performance installation and prepares delegated resources`, (t) => {
    const f = fixture(t);
    let root = f.source;
    if (packaged) {
      root = join(f.box, "package");
      assemblePlugins(f.source, join(root, "dist"), ["ops-direct-invoke", "ops-perf-optimize"]);
    }
    const nested = f.install(root, "dsh");
    assert.equal(nested.status, 0, nested.stdout + nested.stderr);
    const standalone = join(f.box, "performance");
    const result = spawnSync(process.execPath, [cli, "install", "ops-perf-optimize", "--source", root,
      "--target", standalone, "--tool", "dsh"], { encoding: "utf8", env: f.env });
    assert.equal(result.status, 0, result.stdout + result.stderr);
    // The standalone CLI retains its original behavior; the source init owns OpModel setup.
    assert.equal(existsSync(join(standalone, "opmodel-calls.txt")), false);
    const config = JSON.parse(readFileSync(join(f.target, ".cannbot/ops-direct-invoke.json")));
    for (const path of [".dsh/skills/ops-perf-optimize-workflow/SKILL.md", ".cannbot/plugins/ops-perf-optimize/scripts/run.py"]) {
      assert.equal(readFileSync(join(standalone, path), "utf8"), readFileSync(join(config.performance_root, path), "utf8"));
    }
    for (const path of ["AGENTS.md", "skills/ops-perf-optimize-workflow/SKILL.md"]) {
      const asset = `.cannbot/plugins/ops-perf-optimize/${path}`;
      assert.equal(existsSync(join(standalone, asset)), false);
      assert.equal(readFileSync(join(config.performance_root, asset), "utf8"),
        readFileSync(join(f.source, "plugins-official/ops-perf-optimize", path), "utf8"));
    }
  });
}


for (const location of ["private assets", "registered client Skills"]) {
  test(`reinitialization rejects overrides inside ${location} before changing installed content`, (t) => {
    const f = fixture(t);
    const first = f.install(f.source, "dsh");
    assert.equal(first.status, 0, first.stdout + first.stderr);
    const configPath = join(f.target, ".cannbot/ops-direct-invoke.json");
    const config = JSON.parse(readFileSync(configPath, "utf8"));
    const overrides = location === "private assets"
      ? join(config.asset_root, "custom-overrides") : join(f.target, ".dsh/skills");
    const source = join(overrides, "ops-direct-invoke-repo-guide");
    if (location === "registered client Skills") rmSync(source, { force: true });
    write(join(source, "SKILL.md"), "---\nname: ops-direct-invoke-repo-guide\ndescription: owned override\n---\nPRESERVE OVERRIDE\n");
    const watched = [configPath, join(f.target, ".dsh/cannbot-plugin.json"),
      join(config.performance_root, "opmodel-calls.txt"), join(source, "SKILL.md"),
      join(f.target, ".dsh/skills/ops-direct-invoke/SKILL.md")];
    const original = watched.map((path) => readFileSync(path, "utf8"));
    const result = spawnSync(process.execPath, [cli, "install", "ops-direct-invoke", "--source", f.source,
      "--target", f.target, "--tool", "dsh", "--override-skills", overrides], { env: f.env, encoding: "utf8" });
    assert.notEqual(result.status, 0);
    assert.match(result.stderr, /overlap/);
    assert.doesNotMatch(result.stdout, /Installed ops-perf-optimize@/);
    watched.forEach((path, index) => assert.equal(readFileSync(path, "utf8"), original[index], path));
  });
}
