// Copyright (c) 2026 CANNBot contributors
// SPDX-License-Identifier: MIT

import assert from "node:assert/strict";
import { cpSync, existsSync, lstatSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, realpathSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import { PassThrough } from "node:stream";
import test from "node:test";
import { assemblePlugins } from "../../../../script/lib/plugin-bundle.js";
import { prepareDirectInvokeConfig, questionnaireSummary } from "../../tools/direct-invoke-config.mjs";
import { confirmDshPlugin, dshWorkflowMessage, dshWorkflowWarning, linkSharedDependencies, resolveTargetMode } from "../../tools/install.mjs";
import { BACK, QuestionnaireScreen, selectChoice, textQuestion } from "../../tools/terminal-select.mjs";

const repository = resolve(import.meta.dirname, "../../../..");
const cli = join(repository, "script/bin/cannbot.js");
const selected = ["ops-direct-invoke", "ops-direct-invoke-maintain", "ops-direct-invoke-repo-guide", "ops-direct-invoke-requirement"];
const answers = { repo: "common", platform: "ascend", chip: "Ascend950", language: "unspecified",
  preferences: { interaction: "confirm", autonomy: "仅已明确授权范围", review_points: [] } };

function write(path, value) {
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, typeof value === "string" ? value : `${JSON.stringify(value, null, 2)}\n`);
}

function menuTerminal(t, raw = false, term = "xterm") {
  const previousTerm = process.env.TERM;
  process.env.TERM = term;
  t.after(() => {
    if (previousTerm === undefined) delete process.env.TERM;
    else process.env.TERM = previousTerm;
  });
  const input = new PassThrough();
  const output = new PassThrough();
  input.isRaw = raw;
  input.setRawMode = (value) => { input.isRaw = value; };
  output.columns = 40;
  let text = "";
  output.on("data", (chunk) => { text += chunk; });
  t.after(() => { input.destroy(); output.destroy(); });
  return { input, output, text: () => text };
}

test("menu supports arrow navigation, wrapping, numeric jumps and resize", async (t) => {
  const terminal = menuTerminal(t);
  const labels = ["静默运行，你替我做决定", "重要节点和我确认（推荐）", "我监督所有细节"];
  for (const [keys, expected] of [["\x1b[B\r", "2"], ["\x1b[A\r", "3"], ["3\x1b[B\r", "1"], ["9x2\r", "2"]]) {
    const selection = selectChoice("(4/4) 您的交互偏好是？", labels, terminal);
    assert.equal(terminal.input.isRaw, true);
    terminal.output.columns = 30;
    terminal.output.emit("resize");
    terminal.input.write(keys);
    assert.equal(await selection, expected);
    assert.equal(terminal.input.isRaw, false);
    assert.equal(terminal.input.listenerCount("keypress"), 0);
    const finalDisplay = terminal.text().split("\x1b[0J").at(-1);
    assert.ok(finalDisplay.includes(`您的交互偏好是：\x1b[1;32m${labels[Number(expected) - 1]}`));
    assert.doesNotMatch(finalDisplay, /❯|数字跳转|您的交互偏好是？/);
  }
  assert.match(terminal.text(), /输入无效/);
  assert.match(terminal.text(), /❯ 2\./);
  assert.ok(terminal.text().includes("\x1b[1;32m❯"));
  const defaultChoice = selectChoice("交互偏好", labels, { ...terminal, initial: 1 });
  terminal.input.write("\r");
  assert.equal(await defaultChoice, "2");
});

test("menu cancellation and EOF restore terminal state and remove handlers", async (t) => {
  for (const key of ["\x03", "\x04", null]) {
    const terminal = menuTerminal(t, true);
    const choice = selectChoice("选择平台", ["Ascend", "Kirin"], terminal);
    const cancelled = assert.rejects(choice, /初始化已取消/);
    if (key === null) terminal.input.end();
    else terminal.input.write(key);
    await cancelled;
    assert.equal(terminal.input.isRaw, true);
    assert.equal(terminal.input.listenerCount("keypress"), 0);
    assert.equal(terminal.input.listenerCount("end"), 0);
  }
});

test("dumb terminals fall back to numeric input without ANSI menus", async (t) => {
  const terminal = menuTerminal(t, false, "dumb");
  const choice = selectChoice("选择平台？", ["Ascend", "Kirin"], terminal);
  terminal.input.write("2\n");
  assert.equal(await choice, "2");
  assert.match(terminal.text(), /请输入数字/);
  assert.equal(terminal.text().includes("\x1b"), false);
  assert.equal(terminal.input.isRaw, false);
});

test("questionnaire collapses answers while editing without banner or progress bar", async (t) => {
  const terminal = menuTerminal(t);
  const screen = new QuestionnaireScreen(terminal.output);
  t.after(() => screen.close());
  const selected = selectChoice("平台？", ["Ascend", "Kirin"], { ...terminal, screen });
  terminal.input.write("\r");
  assert.equal(await selected, "1");
  screen.answer("平台？", "Ascend");
  const typed = textQuestion("芯片型号？", { ...terminal, screen });
  terminal.input.write("Ascend950PX\x7fR\r");
  assert.equal(await typed, "Ascend950PR");
  screen.answer("芯片型号？", "Ascend950PR");
  const finalDisplay = terminal.text().split("\x1b[0J").at(-1);
  const plainDisplay = finalDisplay.replace(/\x1b\[[0-9;?]*[A-Za-z]/g, "");
  assert.equal(plainDisplay.split("平台：Ascend").length, 2);
  assert.match(plainDisplay, /芯片型号：Ascend950PR/);
  assert.doesNotMatch(plainDisplay, /[█░━─]|%|OPS-DIRECT-INVOKE/);
  assert.doesNotMatch(finalDisplay, /❯|数字跳转/);
  assert.equal(terminal.input.isRaw, false);
});

test("reinstall refresh asks every question with saved answers preselected", async (t) => {
  const f = fixture(t);
  write(join(f.target, ".cannbot/ops-direct-invoke.json"), {
    ...answers, platform: "ascend", chip: "ascend950", language: "ascendc",
    preferences: { interaction: "confirm", autonomy: "test", review_points: [] },
  });
  const asked = [];
  const replies = ["1", "1", "1", "2", "3"];
  const config = await prepareDirectInvokeConfig({ target: f.target, tool: "dsh", refresh: true }, {
    isTTY: true, question: async (_prompt, field) => {
      asked.push({ key: field.key, initial: field.initial });
      return replies.shift();
    },
  });
  assert.deepEqual(asked.map(({ key }) => key), ["platform", "chip", "repo", "language", "interaction"]);
  assert.deepEqual(asked.map(({ initial }) => initial), [0, 0, 0, 0, 1]);
  assert.equal(config.platform, "ascend");
  assert.equal(config.chip, "ascend950");
  assert.equal(config.repo, "common");
  assert.equal(config.language, "dsl");
  assert.equal(config.preferences.interaction, "supervised");
});

test("refresh preselects a custom chip and prefills its model", async (t) => {
  const f = fixture(t);
  write(join(f.target, ".cannbot/ops-direct-invoke.json"), { ...answers, chip: "Ascend910B" });
  const fields = [];
  const replies = ["1", "3", "Ascend910B2", "1", "1", "2"];
  const config = await prepareDirectInvokeConfig({ target: f.target, tool: "dsh", refresh: true }, {
    isTTY: true, question: async (_prompt, field) => {
      fields.push(field);
      return replies.shift();
    },
  });
  const chip = fields.find((field) => field.key === "chip");
  assert.equal(chip.initial, chip.options.indexOf("other"));
  assert.ok(fields.some((field) => field.defaultText === "Ascend910B"), JSON.stringify(fields));
  assert.equal(config.chip, "Ascend910B2");
});

test("text prompt prefill is editable", async (t) => {
  const terminal = menuTerminal(t);
  const screen = new QuestionnaireScreen(terminal.output);
  t.after(() => screen.close());
  const kept = textQuestion("芯片型号？", { ...terminal, screen, initial: "Ascend910B" });
  terminal.input.write("\r");
  assert.equal(await kept, "Ascend910B");
  const edited = textQuestion("芯片型号？", { ...terminal, screen, initial: "Ascend910B" });
  terminal.input.write("\x7f\r");
  assert.equal(await edited, "Ascend910");
});

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
    write(join(plugin, "skills/custom-skills/env-check", platform, "platform.json"), { languages: platform === "ascend" ? ["ascendc", "dsl"] : ["ascendc"] });
  }
  for (const path of ["tools/runtime.py", "docs/contract.md", "orchestrations/tasks/task.yaml", "agents/developer.md", "skills/custom-skills/common/shared.md"]) {
    write(join(plugin, path), path);
  }
  write(join(source, "shared/short/SKILL.md"), "---\nname: public-dependency\ndescription: dependency\ndisable-model-invocation: true\n---\n");
  write(join(source, "shared/short/scripts/run.py"), "print('dependency')\n");
  write(join(plugin, ".claude-plugin/plugin.json"), { name: "ops-direct-invoke", version: "1.0.0", description: "fixture", skills: ["./skills/maintain", "./skills/orchestrator"] });
  write(join(plugin, "plugin-sources.json"), { skillsRepository: ".", skills: ["shared/short"], skillInstallMode: "symlink", preserveSkillInvocationPolicy: true, extraAssets: ["skills/custom-skills"] });
  write(join(plugin, "plugin-install.json"), { initializer: "tools/install.mjs", initializeBefore: ["ops-perf-optimize"] });
  for (const name of ["install.mjs", "direct-invoke-config.mjs", "terminal-select.mjs"]) cpSync(join(repository, "plugins-official/ops-direct-invoke/tools", name), join(plugin, "tools", name));
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
      assert.equal(config.language, "unspecified");
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
      assert.match(result.stdout, /安装目录：/);
      assert.match(result.stdout, /使用方法：/);
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

test("questionnaire skips the only compatible framework when correcting a saved repository", async (t) => {
  const f = fixture(t);
  write(join(f.target, ".cannbot/ops-direct-invoke.json"), { ...answers, repo: "cannbench", platform: "kirin" });
  const config = await prepareDirectInvokeConfig({ target: f.target, tool: "dsh" }, {
    isTTY: true, question: async () => assert.fail("single-choice framework must not be asked"),
  });
  assert.equal(config.repo, "common");
  assert.equal(config.platform, "kirin");
  assert.equal(config.sources.repo, "inferred");
});

test("questionnaire counts only pending answers and reuses the language preference", async (t) => {
  const f = fixture(t);
  write(join(f.target, ".cannbot/ops-direct-invoke.json"), { ...answers, chip: "" });
  const prompts = [];
  const replies = ["3", "Ascend910B"];
  const config = await prepareDirectInvokeConfig({ target: f.target, tool: "dsh" }, {
    isTTY: true, question: async (prompt) => { prompts.push(prompt); return replies.shift(); },
  });
  assert.equal(prompts.length, 2);
  prompts.forEach((prompt) => assert.match(prompt, /芯片/));
  assert.equal(config.chip, "Ascend910B");
  assert.equal(config.language, "unspecified");
});

test("changing platform clears the old chip and rejects invalid explicit choices", async (t) => {
  const f = fixture(t);
  write(join(f.target, ".cannbot/ops-direct-invoke.json"), answers);
  write(f.input, { platform: "kirin" });
  const config = await prepareDirectInvokeConfig({ target: f.target, tool: "dsh", initConfig: f.input }, { isTTY: false });
  assert.equal(config.platform, "kirin");
  assert.equal(config.chip, "unknown");
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
  test(`first ${platform} questionnaire follows dependencies, skips singleton choices and accepts an unknown chip`, async (t) => {
    const f = fixture(t);
    const replies = platform === "ascend" ? ["1", "4", "1", "3", "2"] : ["2", "4", "2"];
    const prompts = [];
    const questions = [];
    const progress = [];
    const config = await prepareDirectInvokeConfig({ target: f.target, tool: "dsh" }, {
      progress: (fraction) => progress.push(fraction),
      isTTY: true, question: async (prompt, field) => {
        if (field.key) questions.push(field.key);
        if (field.key === "repo") {
          assert.equal(platform, "ascend");
          assert.deepEqual(field.options, ["common", "cannbench"]);
        }
        if (field.key === "language") assert.deepEqual(field.options, ["ascendc", "dsl", "unspecified"]);
        prompts.push(prompt);
        return replies.shift();
      },
    });
    assert.equal(prompts.length, platform === "ascend" ? 5 : 3);
    prompts.forEach((prompt) => assert.doesNotMatch(prompt, /\(\d+\/\d+\)/));
    prompts.forEach((prompt) => assert.match(prompt, /^\(\d+%\) /));
    assert.equal(progress[0], 0);
    assert.equal(progress.at(-1), 1);
    progress.slice(1).forEach((fraction, index) => assert.ok(fraction > progress[index]));
    assert.deepEqual(questions, platform === "ascend"
      ? ["platform", "chip", "repo", "language", "interaction"] : ["platform", "chip", "interaction"]);
    assert.equal(config.platform, platform);
    assert.equal(config.repo, "common");
    assert.equal(config.chip, "unknown");
    assert.equal(config.language, platform === "ascend" ? "unspecified" : "ascendc");
    assert.equal(config.preferences.interaction, "confirm");
    assert.deepEqual(config.preferences.review_points, []);
  });
}

test("choice questions reject blank, words, multiple digits and out-of-range numbers", async (t) => {
  const f = fixture(t);
  const replies = ["", "ascend", "12", "0", "3", "1", "1", "common", "2", "3", "4", "3"];
  const prompts = [];
  const messages = [];
  const config = await prepareDirectInvokeConfig({ target: f.target, tool: "dsh" }, {
    isTTY: true, question: async (prompt) => { prompts.push(prompt); return replies.shift(); },
    log: (message) => messages.push(message),
  });
  assert.equal(messages.length, 7);
  messages.forEach((message) => assert.match(message, /请输入一个数字/));
  assert.match(messages.at(-1), /1 或 2 或 3/);
  prompts.slice(0, 6).forEach((prompt) => assert.match(prompt, /硬件平台/));
  assert.equal(config.repo, "cannbench");
  assert.equal(config.chip, "ascend950");
  assert.equal(config.preferences.interaction, "supervised");
});

for (const [platform, models] of [["ascend", ["ascend950", "ascend910"]], ["kirin", ["kirin9030", "kirinx90"]]]) {
  test(`${platform} chip menu offers only the selected platform's series`, async (t) => {
    const f = fixture(t);
    write(join(f.target, ".cannbot/ops-direct-invoke.json"), { ...answers, platform, chip: "" });
    for (const [index, chip] of models.entries()) {
      const config = await prepareDirectInvokeConfig({ target: f.target, tool: "dsh" }, {
        isTTY: true, question: async (_prompt, field) => {
          assert.deepEqual(field.options, [...models, "other", "unknown"]);
          assert.deepEqual(field.labels.slice(-2), ["其他（自行输入）", "暂不确定"]);
          return String(index + 1);
        },
      });
      assert.equal(config.chip, chip);
    }
  });
}

for (const [digit, mode, scope] of [
  ["1", "autonomous", /不主动请求确认/],
  ["2", "confirm", /仅在需求分析等必要确认点/],
  ["3", "supervised", /所有不确定项及时通过问卷/],
]) {
  test(`interaction choice ${digit} derives ${mode} scope and reuses saved choices`, async (t) => {
    const f = fixture(t);
    write(join(f.target, ".cannbot/ops-direct-invoke.json"), {
      ...answers, preferences: { review_points: ["delivery"], autonomy: "old scope" },
    });
    const config = await prepareDirectInvokeConfig({ target: f.target, tool: "dsh" }, {
      isTTY: true, question: async (prompt) => {
        assert.match(prompt, /交互偏好/);
        return digit;
      },
    });
    assert.equal(config.preferences.interaction, mode);
    assert.match(config.preferences.autonomy, scope);
    assert.deepEqual(config.preferences.review_points, ["delivery"]);
    write(join(f.target, ".cannbot/ops-direct-invoke.json"), config);
    const reused = await prepareDirectInvokeConfig({ target: f.target, tool: "dsh" }, { isTTY: false });
    assert.deepEqual(reused.preferences, config.preferences);
  });
}

test("explicit configuration can omit chip, autonomy and review points", async (t) => {
  const f = fixture(t);
  write(f.input, { platform: "ascend", repo: "common", preferences: { interaction: "supervised" } });
  const config = await prepareDirectInvokeConfig({ target: f.target, tool: "dsh", initConfig: f.input }, { isTTY: false });
  assert.equal(config.chip, "unknown");
  assert.equal(config.preferences.interaction, "supervised");
  assert.match(config.preferences.autonomy, /所有不确定项/);
  assert.deepEqual(config.preferences.review_points, []);
  assert.equal(config.language, "unspecified");
});

test("language choice is saved and reused without asking again", async (t) => {
  const f = fixture(t);
  for (const [index, language] of ["ascendc", "dsl", "unspecified"].entries()) {
    write(join(f.target, ".cannbot/ops-direct-invoke.json"), { ...answers, language: undefined });
    const config = await prepareDirectInvokeConfig({ target: f.target, tool: "dsh" }, {
      isTTY: true, question: async (prompt, field) => {
        assert.match(prompt, /开发语言/);
        assert.equal(field.key, "language");
        return String(index + 1);
      },
    });
    assert.equal(config.language, language);
    write(join(f.target, ".cannbot/ops-direct-invoke.json"), config);
    const reused = await prepareDirectInvokeConfig({ target: f.target, tool: "dsh" }, {
      isTTY: true, question: async () => assert.fail("saved language must not be asked again"),
    });
    assert.equal(reused.language, language);
  }
});

test("switching to Kirin adopts its only supported language without asking", async (t) => {
  const f = fixture(t);
  write(join(f.target, ".cannbot/ops-direct-invoke.json"), { ...answers, language: "dsl" });
  write(f.input, { platform: "kirin", chip: "kirin9030" });
  const config = await prepareDirectInvokeConfig({ target: f.target, tool: "dsh", initConfig: f.input }, {
    isTTY: true, question: async () => assert.fail("Kirin supports only AscendC"),
  });
  assert.equal(config.language, "ascendc");
  assert.equal(config.sources.language, "inferred");
});

test("noninteractive Kirin infers its only framework but rejects DSL", (t) => {
  const f = fixture(t);
  write(f.input, { ...answers, repo: undefined, platform: "kirin", language: "dsl" });
  const invalid = f.install(f.source, "dsh");
  assert.notEqual(invalid.status, 0);
  assert.match(invalid.stderr, /kirin.*不支持开发语言 dsl/);
  assert.equal(existsSync(f.target), false);
  write(f.input, { ...answers, repo: undefined, platform: "kirin", language: "ascendc" });
  const installed = f.install(f.source, "dsh");
  assert.equal(installed.status, 0, installed.stdout + installed.stderr);
  const config = JSON.parse(readFileSync(join(f.target, ".cannbot/ops-direct-invoke.json")));
  assert.equal(config.repo, "common");
  assert.equal(config.sources.repo, "inferred");
  assert.equal(config.language, "ascendc");
});

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


test("installation reports each step with an increasing completion percentage", (t) => {
  const f = fixture(t);
  const result = f.install(f.source, "dsh");
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.equal(result.stdout.includes("\x1b[2J"), false, result.stdout);
  const steps = result.stdout.split("\n").map((line) => /^\((\d+)%\) (.+)$/.exec(line)).filter(Boolean)
    .map((match) => ({ percent: Number(match[1]), label: match[2] }));
  assert.ok(steps.length >= 5, result.stdout);
  assert.equal(steps[0].percent, 0);
  const percents = steps.map(({ percent }) => percent);
  assert.deepEqual(percents, [...percents].sort((a, b) => a - b));
  assert.equal(steps.at(-1).percent, 100);
  assert.match(steps.at(-1).label, /安装完成/);
  assert.ok(steps.every(({ label }) => label.trim().length > 0), result.stdout);
});


test("dsh workflow check warns on missing or incompatible packages", (t) => {
  const box = mkdtempSync(join(tmpdir(), "dsh-workflows-"));
  t.after(() => rmSync(box, { recursive: true, force: true }));
  const install = (profile, definition, harness) => {
    const resources = join(box, "profiles", profile, "node_modules",
      "@cannbot-plugin/workflow-ops-direct-invoke", "resources");
    mkdirSync(resources, { recursive: true });
    if (definition) write(join(resources, "plugin-install.json"), definition);
    if (harness) write(join(resources, "skills/workflow-orchestrator/scripts/orchestrator.py"), harness);
  };
  assert.equal(dshWorkflowWarning({ dshHome: box, profile: "missing" }), "missing");
  install("old", {}, "def main():\n    pass\n");
  assert.equal(dshWorkflowWarning({ dshHome: box, profile: "old" }), "old");
  install("native", { nativeWorkflow: "tools/dsh-native.mjs" });
  assert.equal(dshWorkflowWarning({ dshHome: box, profile: "native" }), null);
  install("harness", {}, "def main(task_executor=None, args=None):\n    pass\n");
  assert.equal(dshWorkflowWarning({ dshHome: box, profile: "harness" }), null);
  assert.equal(dshWorkflowMessage("missing", "cmd"), "警告：未检测到 DSH 工作流模块，插件功能可能受损。请重新安装 DSH 插件与工作流模块后启动开发流程。\ncmd");
  assert.equal(dshWorkflowMessage("old", "cmd"), "警告：DSH 部分模块版本过低，插件功能可能受损。请重新安装 DSH 插件与工作流模块后启动开发流程。\ncmd");
});

test("menu backspace returns to the previous question only when allowed", async (t) => {
  const terminal = menuTerminal(t);
  const back = selectChoice("平台？", ["Ascend", "Kirin"], { ...terminal, allowBack: true });
  terminal.input.write("\x7f");
  assert.equal(await back, BACK);
  const ignored = selectChoice("平台？", ["Ascend", "Kirin"], terminal);
  terminal.input.write("\x7f\r");
  assert.equal(await ignored, "1");
});

test("questionnaire backspace re-asks the previous question", async (t) => {
  const terminal = menuTerminal(t);
  terminal.input.isTTY = true;
  terminal.output.isTTY = true;
  const f = fixture(t);
  const keys = ["\r", "\x7f", "\r", "4\r", "1\r", "1\r", "2\r"];
  const result = prepareDirectInvokeConfig({ target: f.target, tool: "dsh" },
    { input: terminal.input, output: terminal.output, isTTY: true });
  (async () => {
    for (const key of keys) {
      await new Promise((resolve) => setTimeout(resolve, 25));
      terminal.input.write(key);
    }
  })();
  const config = await result;
  assert.equal(config.platform, "ascend");
  assert.equal(config.chip, "unknown");
  assert.equal(config.repo, "common");
  assert.equal(config.language, "ascendc");
  assert.equal(config.preferences.interaction, "confirm");
  const text = terminal.text();
  const chip = text.indexOf("您开发的芯片型号或系列是？");
  assert.ok(chip >= 0, text);
  assert.ok(text.indexOf("您在哪种硬件平台上进行开发？", chip) > chip, text);
});

test("questionnaire keeps the existing-workspace choice as an answered prelude", async (t) => {
  const terminal = menuTerminal(t);
  terminal.input.isTTY = true;
  terminal.output.isTTY = true;
  const f = fixture(t);
  const keys = ["\r", "4\r", "1\r", "1\r", "2\r"];
  const result = prepareDirectInvokeConfig({ target: f.target, tool: "dsh",
    prelude: { prompt: "目标目录已有内容，请选择处理方式？", label: "更新现有工作流组件" } },
    { input: terminal.input, output: terminal.output, isTTY: true });
  (async () => {
    for (const key of keys) {
      await new Promise((resolve) => setTimeout(resolve, 25));
      terminal.input.write(key);
    }
  })();
  await result;
  assert.match(terminal.text(), /目标目录已有内容，请选择处理方式：\x1b\[1;32m更新现有工作流组件/);
});

test("questionnaire summary rebuilds answered labels", () => {
  assert.deepEqual(questionnaireSummary({
    platform: "ascend", chip: "ascend950", repo: "common", language: "ascendc",
    preferences: { interaction: "confirm" },
  }), [
    "您在哪种硬件平台上进行开发：昇腾(Ascend)系列",
    "您开发的芯片型号或系列是：Ascend950 系列（950PR/950DT）",
    "您希望使用哪种工程框架：通用框架",
    "您使用哪种开发语言：AscendC",
    "您的交互偏好是：重要节点和我确认（推荐）",
  ]);
  const custom = questionnaireSummary({
    platform: "kirin", chip: "KirinX90A", repo: "common", language: "unspecified",
    preferences: { interaction: "supervised" },
  });
  assert.ok(custom.includes("您开发的芯片型号或系列是：KirinX90A"), custom.join("\n"));
  assert.ok(custom.includes("您使用哪种开发语言：暂不确定"), custom.join("\n"));
  assert.ok(custom.includes("您的交互偏好是：我监督所有细节"), custom.join("\n"));
});

test("non-empty target asks whether to update or reinstall from scratch", async (t) => {
  const terminal = menuTerminal(t);
  terminal.input.isTTY = true;
  terminal.output.isTTY = true;
  const target = mkdtempSync(join(tmpdir(), "target-mode-"));
  t.after(() => rmSync(target, { recursive: true, force: true }));
  write(join(target, "AGENTS.md"), "keep");
  write(join(target, ".cannbot/ops-direct-invoke.json"), "{}");
  const updating = resolveTargetMode(target, terminal);
  terminal.input.write("\r");
  assert.equal(await updating, "update");
  assert.equal(readFileSync(join(target, "AGENTS.md"), "utf8"), "keep");
  const cleaning = resolveTargetMode(target, terminal);
  terminal.input.write("\x1b[B\r");
  assert.equal(await cleaning, "clean");
  assert.deepEqual(readdirSync(target), []);
  // An empty target and a non-interactive run install without asking.
  assert.equal(await resolveTargetMode(target, terminal), "fresh");
  write(join(target, ".cannbot/ops-direct-invoke.json"), "{}");
  const silent = new PassThrough();
  assert.equal(await resolveTargetMode(target, { input: silent, output: terminal.output }), "fresh");
  assert.ok(existsSync(join(target, ".cannbot/ops-direct-invoke.json")));
});


test("dsh install asks before installing the CANNBot DSH plugin", async (t) => {
  const terminal = menuTerminal(t);
  terminal.input.isTTY = true;
  terminal.output.isTTY = true;
  const box = mkdtempSync(join(tmpdir(), "dsh-confirm-"));
  t.after(() => rmSync(box, { recursive: true, force: true }));
  const installer = join(box, "install.sh");
  write(installer, "#!/usr/bin/env bash\nexit 0\n");
  const ask = (env = {}, io = terminal) => confirmDshPlugin(
    { tool: "dsh", installer, profile: "web" }, { ...io, env });
  const accepted = ask();
  terminal.input.write("\r");
  assert.equal(await accepted, true);
  const skipped = ask();
  terminal.input.write("\x1b[B\r");
  assert.equal(await skipped, false);
  assert.match(terminal.text(), /\x1b\[32m该功能需要安装在当前指定目录之外，用户全局的 DSH 环境里。\x1b\[0m/);
  assert.equal(await ask({ CANNBOT_INSTALL_DSH_PLUGIN: "1" }), true);
  assert.equal(await ask({ CANNBOT_INSTALL_DSH_PLUGIN: "0" }), false);
  assert.equal(await confirmDshPlugin({ tool: "opencode", installer, profile: "web" },
    { ...terminal, env: {} }), false);
  const silent = new PassThrough();
  const nonTty = new PassThrough();
  let text = "";
  nonTty.on("data", (chunk) => { text += chunk; });
  assert.equal(await confirmDshPlugin({ tool: "dsh", installer, profile: "web" },
    { input: silent, output: nonTty, env: {} }), false);
  assert.match(text, /bash .*install\.sh --profile web/);
  text = "";
  assert.equal(await confirmDshPlugin({ tool: "dsh", installer: join(box, "missing.sh"), profile: "web" },
    { input: silent, output: nonTty, env: {} }), false);
  assert.match(text, /dsh plugin --profile web add cannbot-dsh@latest/);
});


test("shared dependency checkouts are linked instead of cloned twice", (t) => {
  const box = mkdtempSync(join(tmpdir(), "shared-deps-"));
  t.after(() => rmSync(box, { recursive: true, force: true }));
  const source = join(box, "performance");
  const target = join(box, "project");
  const repo = (path, origin) => {
    mkdirSync(path, { recursive: true });
    spawnSync("git", ["init", "-q", path], { encoding: "utf8" });
    spawnSync("git", ["-C", path, "remote", "add", "origin", origin], { encoding: "utf8" });
  };
  repo(join(source, "asc-devkit"), "https://gitcode.com/cann/asc-devkit.git");
  repo(join(source, "cann-samples"), "https://gitcode.com/cann/other.git");
  repo(join(source, "ops-tensor"), "https://gitcode.com/cann/ops-tensor.git");
  mkdirSync(join(target, "ops-tensor"), { recursive: true });
  write(join(target, "ops-tensor", "keep.txt"), "keep");
  linkSharedDependencies(source, target, [
    { name: "asc-devkit", repository: "https://gitcode.com/cann/asc-devkit.git" },
    { name: "cann-samples", repository: "https://gitcode.com/cann/cann-samples.git" },
    { name: "ops-tensor", repository: "https://gitcode.com/cann/ops-tensor.git" },
    { name: "cann-bench", repository: "https://gitcode.com/cann/cann-bench.git" },
  ]);
  const linked = join(target, "asc-devkit");
  assert.equal(lstatSync(linked).isSymbolicLink(), true);
  assert.equal(realpathSync(linked), realpathSync(join(source, "asc-devkit")));
  // Mismatched origins, missing checkouts and existing destinations are left alone.
  assert.equal(existsSync(join(target, "cann-samples")), false);
  assert.equal(existsSync(join(target, "cann-bench")), false);
  assert.equal(lstatSync(join(target, "ops-tensor")).isSymbolicLink(), false);
  assert.equal(readFileSync(join(target, "ops-tensor", "keep.txt"), "utf8"), "keep");
});


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
    assert.doesNotMatch(result.stdout, /安装目录：/);
    watched.forEach((path, index) => assert.equal(readFileSync(path, "utf8"), original[index], path));
  });
}
