// Copyright (c) 2026 CANNBot contributors
// SPDX-License-Identifier: MIT
// See script/LICENSE for the full license text.

import assert from 'node:assert/strict';
import { cpSync, symlinkSync, existsSync, lstatSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, realpathSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { basename, dirname, isAbsolute, join, relative, resolve } from 'node:path';
import { spawnSync } from 'node:child_process';
import test from 'node:test';
import { assemblePlugins } from '../../../../script/lib/plugin-bundle.js';

const repository = resolve(import.meta.dirname, '../../../..');
const plugin = 'ops-direct-invoke';
const performance = 'ops-perf-optimize';
const sourceDirectory = 'plugins-official/ops-direct-invoke';
const bundleDirectory = 'dist/plugins/ops-direct-invoke';
const mainSkills = ['ops-direct-invoke-maintain', 'ops-direct-invoke', 'ops-direct-invoke-repo-guide', 'ops-direct-invoke-requirement'];
const mainSources = ['maintain', 'orchestrator', 'custom-skills/repo-guide/cannbench', 'custom-skills/requirement/ascend'];
const cli = join(repository, 'script/bin/cannbot.js');

function sandbox(t) {
  const root = mkdtempSync(join(tmpdir(), 'ops-direct-invoke-'));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const target = join(root, 'project');
  mkdirSync(target);
  const env = { ...process.env, HOME: join(root, 'home'), XDG_CACHE_HOME: join(root, 'cache'),
    CANNBOT_SKIP_DEPENDENCY_REPOS: '1', CANNBOT_SKIP_OPMODEL_INSTALL: '1', CANNBOT_SKIP_CODEX_PLUGIN_ADD: '1', CANNBOT_SKIP_OPENCODE_PLUGIN_ADD: '1' };
  const initConfig = join(root, 'init.json');
  writeFileSync(initConfig, JSON.stringify({ repo: 'cannbench', platform: 'ascend', chip: 'Ascend950',
    preferences: { interaction: 'confirm', autonomy: '仅已明确授权范围', review_points: [] } }));
  env.CANNBOT_DIRECT_INVOKE_CONFIG = initConfig;
  return { root, target, env, initConfig };
}

function install(box, tool, source, extra = []) {
  const args = [cli, 'install', plugin, '--tool', tool, '--target', box.target];
  if (source === 'repository') args.push('--source', repository, '--plugin-dir', sourceDirectory,
    '--skills', join(repository, 'vendor/cannbot-skills'));
  else args.push('--plugin-dir', bundleDirectory);
  const result = spawnSync(process.execPath, [...args, ...extra], { env: box.env, encoding: 'utf8' });
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.match(result.stdout, /安装目录：/, result.stdout);
  assert.match(result.stdout, /使用方法：/, result.stdout);
  return join(box.target, ['codex', 'opencode'].includes(tool) ? '.agents' : `.${tool}`, 'skills');
}

function configuration(box) {
  return JSON.parse(readFileSync(join(box.target, '.cannbot/ops-direct-invoke.json'), 'utf8'));
}

function assertAssets(root) {
  // Every classified implementation and its resources must survive packaging, even
  // when it is not selected for the main session.
  const source = join(repository, sourceDirectory);
  for (const category of ['skills', 'tools', 'orchestrations', 'docs', 'agents']) {
    for (const file of readdirSync(join(source, category), { recursive: true, withFileTypes: true })) {
      if (!file.isFile() || file.name.endsWith('.pyc')) continue;
      const relative = join(file.parentPath.slice(join(source, category).length), file.name);
      assert.deepEqual(readFileSync(join(root, category, relative)), readFileSync(join(source, category, relative)), `${category}/${relative}`);
    }
  }
}

// Resolve from the client-visible link before I/O, as editor/client path helpers do.
// Resolving the Skill symlink first would conceal parent-relative links into other Skills.
function assertSkillResources(visible, expected) {
  const pending = ['SKILL.md'], visited = new Set();
  while (pending.length) {
    const resource = pending.pop();
    if (visited.has(resource)) continue;
    visited.add(resource);
    const path = resolve(visible, resource), original = resolve(expected, resource);
    const contents = readFileSync(path, 'utf8');
    assert.equal(contents, readFileSync(original, 'utf8'), path);
    const prose = contents.replace(/^```[^\n]*\n[\s\S]*?^```\s*$/gm, '');
    for (const match of prose.matchAll(/\[[^\]]*\]\(([^)]+)\)/g)) {
      const target = match[1].replace(/^<|>$/g, '').split('#')[0];
      if (!target || /^[a-z][a-z0-9+.-]*:/i.test(target) || target.includes('$')) continue;
      const next = resolve(dirname(path), target);
      const local = relative(visible, next);
      assert.ok(!isAbsolute(local) && local !== '..' && !local.startsWith('../'), `${path}: ${target} escapes the linked Skill`);
      assert.deepEqual(readFileSync(next), readFileSync(resolve(expected, local)), `${path}: ${target}`);
      if (next.endsWith('.md')) pending.push(local);
    }
  }
}

for (const source of ['repository', 'package']) {
  for (const tool of ['codex', 'opencode', 'claude', 'trae', 'dsh']) {
    test(`harness installs complete ${source} assets for ${tool} and exposes only main Skills`, (t) => {
      const box = sandbox(t);
      const skills = install(box, tool, source);
      const config = configuration(box);
      const registry = JSON.parse(readFileSync(join(box.target, `.${tool}`, 'cannbot-plugin.json'), 'utf8'));
      assert.deepEqual(registry.plugins.map((item) => item.plugin), [plugin]);
      assert.equal(registry.plugins[0].instructions, null);
      assert.deepEqual(registry.plugins[0].agents, []);
      assert.deepEqual(readdirSync(skills).sort(), [...mainSkills].sort());
      for (const [index, name] of mainSkills.entries()) {
        assert.ok(existsSync(join(skills, name, 'SKILL.md')), name);
        assert.equal(realpathSync(join(skills, name)), realpathSync(join(config.asset_root, 'skills', mainSources[index])));
        if (source === 'repository') assert.equal(realpathSync(join(skills, name)), join(repository, sourceDirectory, 'skills', mainSources[index]));
      }
      assertAssets(config.asset_root);
      for (const [index, name] of mainSkills.entries()) {
        assertSkillResources(join(skills, name), join(repository, sourceDirectory, 'skills', mainSources[index]));
      }
      const templates = join(config.asset_root, 'skills/custom-skills/doc-templates');
      assert.equal(existsSync(join(templates, 'common')), false);
      for (const file of readdirSync(templates, { recursive: true, withFileTypes: true })) {
        if (file.name !== 'SKILL.md') continue;
        const leaf = dirname(join(file.parentPath, file.name));
        const visible = join(box.root, 'template-views', relative(templates, leaf), '.agents/skills/ops-direct-invoke-doc-templates');
        mkdirSync(dirname(visible), { recursive: true });
        symlinkSync(leaf, visible, 'dir');
        assertSkillResources(visible, join(repository, sourceDirectory, 'skills/custom-skills/doc-templates', relative(templates, leaf)));
      }
      const envSkill = join(config.asset_root, 'skills/custom-skills/env-check/ascend/ascendc');
      assert.ok(readFileSync(resolve(envSkill, 'references/environment-policy.md'), 'utf8').length);
      for (const path of ['README.md', 'QUICKSTART.md', 'tests/test_all.py']) assert.ok(existsSync(join(config.asset_root, path)), path);
      assert.ok(existsSync(join(config.external_skills_root, 'workflow-orchestrator/scripts/orchestrator.py')));
      const guide = workflowGuide(config.asset_root, box.root);
      assert.ok(guide.length);
      for (const template of guide) assert.ok(template.use_when.length);
      assert.equal(existsSync(join(box.target, 'AGENTS.md')), false);
      assert.equal(existsSync(join(box.target, 'CLAUDE.md')), false);
      const perf = JSON.parse(readFileSync(config.performance_registry, 'utf8')).plugins.find((item) => item.plugin === performance);
      assert.ok(perf);
      const perfWorkflow = perf.skills.find((path) => basename(path) === 'ops-perf-optimize-workflow');
      assert.ok(perfWorkflow);
      const perfRoot = join(config.performance_root, perfWorkflow);
      const help = spawnSync('python3', ['-B', join(perfRoot, 'scripts/workflow_state.py'), '--help'], { encoding: 'utf8' });
      assert.equal(help.status, 0, help.stdout + help.stderr);
      assert.ok(existsSync(join(perfRoot, 'workflows/task-prompts.md')));
      install(box, tool, source);
      assert.deepEqual(configuration(box), config);
      assert.equal(existsSync(join(skills, 'ops-perf-optimize-workflow')), false);
    });
  }
}

function legacyInstructions(box, tool) {
  const block = `<!-- cannbot:${plugin}:start -->\nLegacy PM instructions\n<!-- cannbot:${plugin}:end -->`;
  const other = '<!-- cannbot:other:start -->\nOther plugin\n<!-- cannbot:other:end -->';
  const prefix = `用户自己的 PM 说明\r\n${other}\n\n`;
  const suffix = '\n用户尾部内容  \n\n';
  const expectedAgents = prefix + suffix;
  const expectedClaude = '';
  writeFileSync(join(box.target, 'AGENTS.md'), prefix + block + suffix + block);
  writeFileSync(join(box.target, 'CLAUDE.md'), block + expectedClaude);
  const client = tool === 'codex' ? '.codex' : tool === 'claude' ? '.claude' : `.${tool}`;
  const registryPath = join(box.target, client, 'cannbot-plugin.json');
  const registry = JSON.parse(readFileSync(registryPath, 'utf8'));
  registry.plugins[0].instructions = tool === 'claude' ? 'CLAUDE.md' : 'AGENTS.md';
  writeFileSync(registryPath, JSON.stringify(registry));
  return { registryPath, expected: expectedAgents, expectedClaude };
}

for (const source of ['repository', 'package']) {
  for (const tool of ['codex', 'opencode', 'claude', 'trae', 'dsh']) {
    test(`upgrade ${source} for ${tool} retires only managed PM blocks in both instruction files`, (t) => {
      const box = sandbox(t);
      install(box, tool, source);
      const { registryPath, expected, expectedClaude } = legacyInstructions(box, tool);
      for (let attempt = 0; attempt < 2; attempt++) {
        install(box, tool, source);
        assert.equal(readFileSync(join(box.target, 'AGENTS.md'), 'utf8'), expected);
        assert.equal(readFileSync(join(box.target, 'CLAUDE.md'), 'utf8'), expectedClaude);
        const registry = JSON.parse(readFileSync(registryPath, 'utf8'));
        assert.equal(registry.plugins[0].instructions, null);
      }
    });
  }
}

test('upgrade preserves unmarked or incomplete user instructions', (t) => {
  const box = sandbox(t);
  const instructions = '<!-- cannbot:ops-direct-invoke:start -->\nUser-maintained PM instructions\n';
  writeFileSync(join(box.target, 'AGENTS.md'), instructions);
  install(box, 'codex', 'repository');
  assert.ok(readFileSync(join(box.target, 'AGENTS.md'), 'utf8').startsWith(instructions));
  assert.equal(readFileSync(join(box.target, 'AGENTS.md'), 'utf8'), instructions);
  assert.equal(existsSync(join(box.target, 'CLAUDE.md')), false);
});

test('harness knowledge overrides preserve the source and cannot replace scheduling', (t) => {
  const box = sandbox(t);
  const overrides = join(box.root, 'overrides');
  mkdirSync(join(overrides, 'ops-direct-invoke-repo-guide'), { recursive: true });
  writeFileSync(join(overrides, 'ops-direct-invoke-repo-guide/SKILL.md'), '---\nname: ops-direct-invoke-repo-guide\ndescription: test override\n---\nSUBREPO_SENTINEL\n');
  const source = join(repository, sourceDirectory, 'skills/custom-skills/repo-guide/cannbench/SKILL.md');
  const original = readFileSync(source, 'utf8');
  const skills = install(box, 'codex', 'repository', ['--override-skills', overrides]);
  assert.match(readFileSync(join(skills, 'ops-direct-invoke-repo-guide/SKILL.md'), 'utf8'), /SUBREPO_SENTINEL/);
  assert.equal(readFileSync(source, 'utf8'), original);
  mkdirSync(join(overrides, 'workflow-orchestrator'));
  writeFileSync(join(overrides, 'workflow-orchestrator/SKILL.md'), '---\nname: workflow-orchestrator\n---\n');
  const result = spawnSync(process.execPath, [cli, 'install', plugin, '--source', repository, '--plugin-dir', sourceDirectory,
    '--tool', 'codex', '--target', box.target, '--override-skills', overrides,
    '--skills', join(repository, 'vendor/cannbot-skills')], { env: box.env, encoding: 'utf8' });
  assert.equal(result.status, 1);
  assert.match(result.stderr, /cannot be overridden/);
});

test('harness source init initializes performance first and installs each plugin once', (t) => {
  const box = sandbox(t);
  const result = spawnSync('bash', [join(repository, sourceDirectory, 'init.sh'), 'project', 'codex', box.target,
    '--skills', join(repository, 'vendor/cannbot-skills')],
    { env: box.env, encoding: 'utf8' });
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.equal(result.stdout.match(/安装目录：/g)?.length, 1, result.stdout);
  assert.equal(result.stdout.match(/使用方法：/g)?.length, 1, result.stdout);
  const config = configuration(box);
  assert.ok(existsSync(join(config.performance_root, '.agents/skills/ops-perf-optimize-workflow/SKILL.md')));
  assert.ok(existsSync(join(config.performance_root, '.codex/agents/perf-optimize.toml')));
  assert.ok(existsSync(join(config.asset_root, 'orchestrations/tasks/ascendc/知识搜集.yaml')));
});

function prepare(box, skills, input = 'template') {
  const work = join(box.target, '.cannbot/AddExample/workflow1');
  const config = configuration(box);
  const root = config.asset_root;
  const guide = workflowGuide(root, box.root);
  const selected = guide.find((template) => template.file === 'ascendc/basic.yaml');
  assert.ok(selected);
  const template = join(root, 'orchestrations/workflows', selected.file);
  const complete = join(box.root, 'assembled.yaml');
  if (input === 'yaml') {
    const result = spawnSync('python3', [join(root, 'tools/assemble_workflow.py'),
      '--template', template, '--output', complete], { encoding: 'utf8' });
    assert.equal(result.status, 0, result.stderr);
  }
  const definition = input === 'template'
    ? ['--template', selected.file]
    : ['--yaml', complete];
  return { work, template, complete, run: [join(root, 'tools/run_workflow.py'), '--provider', 'codex',
    ...definition, '--work-dir', work, '--harness-skill', join(config.external_skills_root, 'workflow-orchestrator'), '--foreground', '--dry-run'] };
}

function simulate(box, prepared, replies = {}, first = true) {
  mkdirSync(join(prepared.work, '.workflow'), { recursive: true });
  writeFileSync(join(prepared.work, '.workflow/dry_replies.json'), JSON.stringify(replies));
  const args = [...prepared.run];
  if (first) args.push('--prompt', 'test operator');
  else if (args.includes('--template')) {
    args.splice(args.indexOf('--template'), 2, '--yaml', join(prepared.work, `${basename(prepared.work)}.yaml`));
  }
  return spawnSync('python3', args, { env: box.env, encoding: 'utf8', timeout: 30000 });
}

function state(prepared) {
  return JSON.parse(readFileSync(join(prepared.work, '.workflow/status.json'), 'utf8'));
}

for (const source of ['repository', 'package']) for (const input of ['template', 'yaml']) {
  test(`public harness executes discovered workflow from ${source} via --${input}`, (t) => {
    const box = sandbox(t);
    const skills = install(box, 'codex', source);
    const prepared = prepare(box, skills, input);
    const original = readFileSync(prepared.template, 'utf8');
    const result = simulate(box, prepared, { '3': ['executed', '$VERDICT:fail', 'executed', '$VERDICT:pass'] });
    assert.equal(result.status, 0, result.stdout + result.stderr);
    assert.equal(readFileSync(prepared.template, 'utf8'), original);
    const current = state(prepared);
    const definition = input === 'template' ? join(prepared.work, `${basename(prepared.work)}.yaml`) : prepared.complete;
    const expected = yamlValue(definition).nodes.map((node) => node.id);
    assert.deepEqual(Object.keys(current.tasks).sort(), expected.sort());
    assert.equal(current.tasks['3'].retries, 1);
    for (const [tid, node] of Object.entries(current.tasks)) assert.equal(node.status, 'pass', tid);

  });
}

test('task verifier exhaustion blocks dependents; restart does not invent recovery', (t) => {
  const box = sandbox(t);
  const skills = install(box, 'codex', 'repository');
  const prepared = prepare(box, skills);
  const failed = simulate(box, prepared, { '0.0': Array(4).fill(['executed', '$VERDICT:fail']).flat() });
  assert.equal(failed.status, 1, failed.stdout + failed.stderr);
  assert.equal(state(prepared).tasks['0.0'].status, 'fail');
  for (const tid of ['1', '2', '3', '4', '5']) assert.equal(state(prepared).tasks[tid].status, 'pending');
  const restarted = simulate(box, prepared, {}, false);
  assert.equal(restarted.status, 1, restarted.stdout + restarted.stderr);
  assert.equal(state(prepared).tasks['2'].status, 'pending');
});

test('operator verification waits for tests and blocks downstream delivery on failure', (t) => {
  const box = sandbox(t);
  const skills = install(box, 'codex', 'repository');
  const prepared = prepare(box, skills);
  const nodes = yamlValue(prepared.template).nodes.map((node) => ({
    ...yamlValue(resolve(dirname(prepared.template), node.yaml)), ...node }));
  const developer = nodes.find((node) => node.title === '算子开发');
  const tests = nodes.find((node) => node.title === '测试工程开发');
  assert.ok(developer.depends_on.includes(tests.id));
  assert.equal(nodes.some((node) => node.title === '代码检视'), false);
  const failed = simulate(box, prepared, { [developer.id]: Array(4).fill(['executed', '$VERDICT:fail']).flat() });
  assert.equal(failed.status, 1, failed.stdout + failed.stderr);
  assert.equal(state(prepared).tasks[tests.id].status, 'pass');
  assert.equal(state(prepared).tasks[developer.id].status, 'fail');
  for (const title of ['白盒测试设计', '代码修复', '文档准备']) {
    const node = nodes.find((item) => item.title === title);
    assert.equal(state(prepared).tasks[node.id].status, 'pending', title);
  }
});

test('a new workflow under the same task preserves the previous failed run', (t) => {
  const box = sandbox(t);
  const skills = install(box, 'codex', 'repository');
  const first = prepare(box, skills, 'yaml');
  const second = { ...first, work: join(box.target, '.cannbot/AddExample/workflow2'), run: [...first.run] };
  for (const [index, current] of [first, second].entries()) {
    mkdirSync(current.work, { recursive: true });
    const definition = join(current.work, `workflow${index + 1}.yaml`);
    cpSync(current.complete, definition);
    current.run[current.run.indexOf('--yaml') + 1] = definition;
    current.run[current.run.indexOf('--work-dir') + 1] = current.work;
  }
  const failed = simulate(box, first, { '0.0': Array(4).fill(['executed', '$VERDICT:fail']).flat() });
  assert.equal(failed.status, 1, failed.stdout + failed.stderr);
  const previousState = readFileSync(join(first.work, '.workflow/status.json'), 'utf8');
  const previousYaml = readFileSync(join(first.work, 'workflow1.yaml'), 'utf8');
  const completed = simulate(box, second);
  assert.equal(completed.status, 0, completed.stdout + completed.stderr);
  for (const node of Object.values(state(second).tasks)) assert.equal(node.status, 'pass');
  assert.equal(state(first).tasks['0.0'].status, 'fail');
  assert.equal(readFileSync(join(first.work, '.workflow/status.json'), 'utf8'), previousState);
  assert.equal(readFileSync(join(first.work, 'workflow1.yaml'), 'utf8'), previousYaml);
});

const entryScripts = join(repository, sourceDirectory, 'tools');

function yamlValue(file) {
  const result = spawnSync('python3', ['-c', 'import json,logging,sys,yaml; logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout); logging.info(json.dumps(yaml.safe_load(open(sys.argv[1]))))', file],
    { encoding: 'utf8' });
  assert.equal(result.status, 0, result.stderr);
  return JSON.parse(result.stdout);
}

function csvValue(file) {
  const result = spawnSync('python3', ['-c', 'import csv,json,logging,sys; logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout); logging.info(json.dumps(list(csv.DictReader(open(sys.argv[1], encoding="utf-8", newline="")))))', file],
    { encoding: 'utf8' });
  assert.equal(result.status, 0, result.stderr);
  return JSON.parse(result.stdout);
}

function workflowGuide(root, directory) {
  const output = join(directory, 'workflow-guide.csv');
  const result = spawnSync('python3', [join(root, 'tools/generate_workflow_guide.py'), '--output', output],
    { cwd: directory, encoding: 'utf8' });
  assert.equal(result.status, 0, result.stdout + result.stderr);
  return csvValue(output);
}

function taskFixture(box, name) {
  const task = yamlValue(join(entryScripts, '../orchestrations/tasks/ascendc/知识搜集.yaml'));
  for (const field of ['goal', 'approach', 'procedure', 'acceptance', 'out_of_scope']) {
    for (const [key, value] of Object.entries(task.variables ?? {})) {
      task[field] = task[field].map((item) => item.replaceAll(`{{var:${key}}}`, value));
    }
  }
  delete task.variables;
  task.title = name;
  const file = join(box.root, `${name}.yaml`);
  writeFileSync(file, JSON.stringify(task));
  return { file, task };
}

test('assembler accepts external files in caller order and generates identity and serial dependencies', (t) => {
  const box = sandbox(t);
  const a = taskFixture(box, '外部 A');
  const b = taskFixture(box, '外部 B');
  for (const [name, inputs] of [['forward', [a, b]], ['reverse', [b, a, b]]]) {
    const output = join(box.root, `${name}.yaml`);
    const result = spawnSync('python3', [join(entryScripts, 'assemble_workflow.py'), '--max-retries', '1', '--output', output,
      ...inputs.map((input) => input.file)], { encoding: 'utf8' });
    assert.equal(result.status, 0, result.stderr);
    const workflow = yamlValue(output);
    const contexts = yamlValue(`${output}.contexts.yaml`);
    assert.equal(workflow.nodes.length, inputs.length);
    workflow.nodes.forEach(({ id, depends_on, ...task }, index) => {
      assert.equal(id, String(index));
      assert.deepEqual(depends_on, index === 0 ? [] : [String(index - 1)]);
      assert.equal(task.max_retries, 1);
      const { context, ...expectedTask } = JSON.parse(JSON.stringify(inputs[index].task).replaceAll('{{id}}', id));
      assert.deepEqual(task, { ...expectedTask, max_retries: 1 });
      assert.equal('context' in task, false);
      assert.deepEqual(contexts[id], context);
    });
  }
});

test('assembler supports independent branches and joins through positional dependency parameters', (t) => {
  const box = sandbox(t);
  const a = taskFixture(box, 'task');
  const output = join(box.root, 'parallel.yaml');
  const result = spawnSync('python3', [join(entryScripts, 'assemble_workflow.py'), '--max-retries', '1', '--output', output,
    '--depends-on', '2:', '--depends-on', '3:1,2', a.file, a.file, a.file], { encoding: 'utf8' });
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(yamlValue(output).nodes.map(({ id, depends_on }) => ({ id, depends_on })),
    [{ id: '0.0', depends_on: [] }, { id: '0.1', depends_on: [] }, { id: '1', depends_on: ['0.0', '0.1'] }]);
});

test('assembler rejects malformed tasks, invalid dependencies and overwriting existing output', (t) => {
  const box = sandbox(t);
  const a = taskFixture(box, 'valid');
  const output = join(box.root, 'workflow.yaml');
  for (const field of ['id', 'depends_on']) {
    const invalid = join(box.root, `${field}.yaml`);
    writeFileSync(invalid, JSON.stringify({ ...a.task, [field]: field === 'id' ? 'legacy' : [] }));
    const result = spawnSync('python3', [join(entryScripts, 'assemble_workflow.py'), '--max-retries', '1', '--output', output, invalid], { encoding: 'utf8' });
    assert.equal(result.status, 2);
    assert.equal(existsSync(output), false);
  }
  for (const dependencies of [['1:2'], ['1:1'], ['1:2', '2:1'], ['2:1', '2:']]) {
    const inputs = dependencies.length === 1 ? [a.file] : [a.file, a.file];
    const result = spawnSync('python3', [join(entryScripts, 'assemble_workflow.py'), '--max-retries', '1', '--output', output,
      ...dependencies.flatMap((value) => ['--depends-on', value]), ...inputs], { encoding: 'utf8' });
    assert.equal(result.status, 2, result.stdout + result.stderr);
    assert.equal(existsSync(output), false);
  }
  writeFileSync(output, 'existing run');
  const result = spawnSync('python3', [join(entryScripts, 'assemble_workflow.py'), '--max-retries', '1', '--output', output, a.file], { encoding: 'utf8' });
  assert.equal(result.status, 2);
  assert.equal(readFileSync(output, 'utf8'), 'existing run');
});

for (const foreground of [true, false]) {
  test(`launcher preserves task text and exit result in ${foreground ? 'foreground' : 'tmux'}`, async (t) => {
    if (!foreground && spawnSync('tmux', ['-V']).status !== 0) return t.skip('tmux unavailable');
    const box = sandbox(t);
    // Fixture for the CLI boundary; never reads or modifies real harness internals.
    const harness = join(box.root, "fixture CLI ' quoted");
    mkdirSync(join(harness, 'scripts'), { recursive: true });
    writeFileSync(join(harness, 'scripts/orchestrator.py'),
      'import json,logging,sys\nlogging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)\nlogging.info(json.dumps(sys.argv[1:]))\nsys.exit(7)\n');
    const workflow = join(box.root, 'workflow.yaml');
    writeFileSync(workflow, 'fixture');
    const work = join(box.root, "run ' quoted");
    const prompt = "中文任务\n'quoted' \"double\" \\ $value $(printf unwanted) `printf unwanted`";
    const promptFile = join(box.root, 'original task.txt');
    writeFileSync(promptFile, prompt);
    const expected = ['--yaml', workflow, '--work-dir', work, '--provider', 'fixture provider', '--prompt', prompt, '--dry-run'];
    const result = spawnSync('python3', [join(entryScripts, 'run_workflow.py'), '--yaml', workflow,
      '--work-dir', work, '--provider', 'fixture provider', '--harness-skill', harness,
      '--prompt-file', promptFile, '--dry-run', ...(foreground ? ['--foreground'] : [])], { encoding: 'utf8' });
    if (foreground) {
      assert.equal(result.status, 7, result.stderr);
      assert.deepEqual(JSON.parse(result.stdout), expected);
    } else {
      assert.equal(result.status, 0, result.stderr);
      const session = result.stdout.match(/^session: (.+)$/m)?.[1];
      assert.ok(session, result.stdout);
      t.after(() => spawnSync('tmux', ['kill-session', '-t', session]));
      const log = join(work, 'orchestrator.log');
      let contents = '';
      for (let attempt = 0; attempt < 100; attempt++) {
        if (existsSync(log)) contents = readFileSync(log, 'utf8');
        if (contents.includes('exit status: 7')) break;
        await new Promise((resolve) => setTimeout(resolve, 50));
      }
      assert.match(contents, /exit status: 7/);
      assert.deepEqual(JSON.parse(contents.split('\n')[0]), expected);
    }
  });
}

test('ops-direct-invoke assembles and installs from a self-contained source layout', (t) => {
  const box = sandbox(t);
  const isolated = join(box.root, 'independent source');
  mkdirSync(join(isolated, '.git'), { recursive: true });
  mkdirSync(join(isolated, 'plugins-official'), { recursive: true });
  cpSync(join(repository, 'LICENSE'), join(isolated, 'LICENSE'));
  cpSync(join(repository, 'plugins-official/LICENSE'), join(isolated, 'plugins-official/LICENSE'));
  cpSync(join(repository, sourceDirectory), join(isolated, sourceDirectory), { recursive: true });
  // Explicit performance dependency is shipped alongside the generation plugin.
  cpSync(join(repository, 'plugins-official/ops-perf-optimize'),
    join(isolated, 'plugins-official/ops-perf-optimize'), { recursive: true });
  // Only the common framework and domain Skill repository are shared with the source tree.
  symlinkSync(join(repository, 'harness'), join(isolated, 'harness'), 'dir');
  symlinkSync(join(repository, 'vendor'), join(isolated, 'vendor'), 'dir');
  assert.equal(existsSync(join(isolated, 'plugins-community')), false);
  const bundles = assemblePlugins(isolated, join(box.root, 'dist'), [basename(sourceDirectory)]);
  assert.equal(bundles.length, 1);
  assertAssets(bundles[0].destination);
  const result = spawnSync(process.execPath, [cli, 'install', plugin, '--source', isolated, '--plugin-dir', sourceDirectory,
    '--tool', 'codex', '--target', box.target,
    '--skills', join(repository, 'vendor/cannbot-skills')], { env: box.env, encoding: 'utf8' });
  assert.equal(result.status, 0, result.stdout + result.stderr);
  const skills = join(box.target, '.agents/skills');
  for (const [index, name] of mainSkills.entries()) {
    assert.equal(realpathSync(join(skills, name)), join(isolated, sourceDirectory, 'skills', mainSources[index]));
  }
  const completed = simulate(box, prepare(box, skills));
  assert.equal(completed.status, 0, completed.stdout + completed.stderr);
});


test('discovered workflow templates reproduce their tasks and phase contexts', (t) => {
  const box = sandbox(t);
  const root = join(repository, sourceDirectory);
  const guide = workflowGuide(root, box.root);
  assert.equal(new Set(guide.map((item) => item.file)).size, guide.length);
  assert.deepEqual(guide.map((item) => item.file).sort(),
    readdirSync(join(root, 'orchestrations/workflows'), { recursive: true })
      .filter((name) => name.endsWith('.yaml') && !name.endsWith('.graph-preview.yaml')).sort());
  for (const template of guide) {
    const output = join(box.root, template.file);
    const path = join(root, 'orchestrations/workflows', template.file);
    const reference = yamlValue(path);
    const result = spawnSync('python3', [join(root, 'tools/assemble_workflow.py'), '--output', output,
      '--template', path], { encoding: 'utf8' });
    assert.equal(result.status, 0, result.stdout + result.stderr);
    const expected = yamlValue(output);
    const contexts = yamlValue(`${output}.contexts.yaml`);
    assert.ok(expected.nodes.every((node) => !('context' in node)));
    // Complete workflows inline their task content: the freeze keeps the graph and drops use_when.
    if (!reference.nodes.some((node) => 'yaml' in node)) {
      const { use_when, ...frozen } = reference;
      frozen.nodes = reference.nodes.map(({ context, ...node }) => node);
      assert.equal(template.use_when, use_when);
      assert.deepEqual(expected, frozen);
      assert.deepEqual(contexts, Object.fromEntries(reference.nodes
        .filter((node) => 'context' in node).map((node) => [node.id, node.context])));
      continue;
    }
    assert.deepEqual(expected.nodes.map(({ id, depends_on, max_retries }) => ({ id, depends_on, max_retries })),
      reference.nodes.map(({ id, depends_on, max_retries }) => ({ id, depends_on, max_retries })));
    const expectedContexts = {};
    for (const [index, node] of expected.nodes.entries()) {
      const ref = reference.nodes[index];
      if (!('yaml' in ref)) {
        const { template: childTemplate, context, ...frozen } = ref;
        if (context !== undefined) expectedContexts[node.id] = context;
        assert.deepEqual(node, frozen);
        if (childTemplate) assert.ok(existsSync(resolve(dirname(output), ref.file)));
        continue;
      }
      const task = yamlValue(resolve(dirname(path), ref.yaml));
      assert.equal(task.max_retries, undefined);
      assert.deepEqual(node.goal, task.goal);
      assert.equal(node.title, task.title);
      if ('context' in task) expectedContexts[node.id] = task.context;
      assert.equal(node.yaml, undefined);
      assert.equal(node.variables, undefined);
    }
    assert.deepEqual(contexts, expectedContexts);
  }
});

test('launcher requires one workflow input and rejects unavailable or escaped template paths', (t) => {
  const box = sandbox(t);
  for (const [args, error] of [
    [[], /required/],
    [['--yaml', 'custom.yaml', '--template', 'ascendc/basic.yaml'], /not allowed/],
    [['--template', 'missing.yaml'], /No such file/],
    [['--template', '../tasks/ascendc/知识搜集.yaml'], /must stay inside/],
    [['--template', '.'], /must be a file/],
  ]) {
    const result = spawnSync('python3', [join(entryScripts, 'run_workflow.py'), ...args,
      '--work-dir', join(box.root, 'not-started'), '--provider', 'codex', '--foreground', '--dry-run'], { encoding: 'utf8' });
    assert.equal(result.status, 2, result.stdout + result.stderr);
    assert.match(result.stderr, error);
    assert.equal(existsSync(join(box.root, 'not-started')), false);
  }
});


test('assembler numbers dependency layers and keeps parallel branch order across layers', (t) => {
  const box = sandbox(t);
  const task = taskFixture(box, 'shared task');
  for (const [name, count, overrides, expectedIds] of [
    ['branches', 6, ['3:1', '4:3', '5:2', '6:4,5'], ['0', '1.0', '1.1', '2.1', '2.0', '3']],
    ['forward-refs', 3, ['1:2', '2:3', '3:'], ['2', '1', '0']],
  ]) {
    const output = join(box.root, `${name}.yaml`);
    const result = spawnSync('python3', [join(entryScripts, 'assemble_workflow.py'), '--max-retries', '1', '--output', output,
      ...overrides.flatMap((value) => ['--depends-on', value]), ...Array(count).fill(task.file)], { encoding: 'utf8' });
    assert.equal(result.status, 0, result.stdout + result.stderr);
    const workflow = yamlValue(output);
    assert.deepEqual(workflow.nodes.map((node) => node.id), expectedIds);
    assert.ok(workflow.nodes.every((node) => typeof node.id === 'string'
      && node.depends_on.every((parent) => typeof parent === 'string' && expectedIds.includes(parent))));
    assert.deepEqual(workflow.nodes.at(-1).depends_on, name === 'branches' ? ['2.1', '2.0'] : []);
  }
});


test('explicit plugin selection rejects a mismatched logical name', (t) => {
  const box = sandbox(t);
  const result = spawnSync(process.execPath, [cli, 'install', 'model-infer-optimize', '--source', repository,
    '--plugin-dir', sourceDirectory, '--tool', 'codex', '--target', box.target], { env: box.env, encoding: 'utf8' });
  assert.equal(result.status, 1);
  assert.match(result.stderr, /plugin name mismatch/);
  assert.deepEqual(readdirSync(box.target), []);
});
