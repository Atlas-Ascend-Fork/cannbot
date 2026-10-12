// Copyright (c) 2026 CANNBot contributors
// SPDX-License-Identifier: MIT
// See script/LICENSE for the full license text.

import assert from 'node:assert/strict';
import { cpSync, symlinkSync, existsSync, lstatSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, realpathSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { basename, dirname, join, resolve } from 'node:path';
import { spawnSync } from 'node:child_process';
import test from 'node:test';
import { assemblePlugins } from '../lib/plugin-bundle.js';

const repository = resolve(import.meta.dirname, '../..');
const plugin = 'ops-direct-invoke';
const sourceDirectory = 'plugins-official/ops-direct-invoke';
const bundleDirectory = 'dist/plugins/ops-direct-invoke';
const entry = 'ops-direct-invoke';
const requirement = 'repo-requirement';
const repoSkills = ['repo-knowledge', 'repo-build-guide', 'repo-op-templates', 'repo-coding-rules', 'repo-test-develop'];
const localKnowledge = [...repoSkills, requirement, 'repo-env-check'];
const cli = join(repository, 'script/bin/cannbot.js');

function sandbox(t) {
  const root = mkdtempSync(join(tmpdir(), 'ops-direct-invoke-'));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const target = join(root, 'project');
  mkdirSync(target);
  const env = { ...process.env, HOME: join(root, 'home'), XDG_CACHE_HOME: join(root, 'cache'),
    CANNBOT_SKIP_DEPENDENCY_REPOS: '1', CANNBOT_SKIP_CODEX_PLUGIN_ADD: '1', CANNBOT_SKIP_OPENCODE_PLUGIN_ADD: '1' };
  return { root, target, env };
}

function install(box, tool, source, extra = []) {
  const args = [cli, 'install', plugin, '--tool', tool, '--target', box.target];
  if (source === 'repository') args.push('--source', repository, '--plugin-dir', sourceDirectory,
    '--skills', join(repository, 'vendor/cannbot-skills'));
  else args.push('--plugin-dir', bundleDirectory);
  const result = spawnSync(process.execPath, [...args, ...extra], { env: box.env, encoding: 'utf8' });
  assert.equal(result.status, 0, result.stdout + result.stderr);
  return join(box.target, tool === 'claude' ? '.claude' : '.agents', 'skills');
}

for (const source of ['repository', 'package']) {
  for (const tool of ['codex', 'opencode', 'claude']) {
    test(`harness installs ${source} for ${tool} with workspace instructions and without a PM subagent`, (t) => {
      const box = sandbox(t);
      const skills = install(box, tool, source);
      const clientDirectory = tool === 'codex' ? '.codex' : tool === 'opencode' ? '.opencode' : '.claude';
      const installedRegistry = JSON.parse(readFileSync(join(box.target, clientDirectory, 'cannbot-plugin.json'), 'utf8'));
      assert.deepEqual(installedRegistry.plugins.map((item) => item.plugin), [plugin]);
      assert.deepEqual(readdirSync(join(box.target, '.cannbot/plugins')), [plugin]);
      for (const name of [entry, 'workflow-orchestrator', ...localKnowledge,
        'ascendc-simt-tiling-design', 'ascendc-mc2-best-practice', 'cann-env-setup']) {
        assert.ok(existsSync(join(skills, name, 'SKILL.md')), name);
        assert.equal(lstatSync(join(skills, name)).isSymbolicLink(), source === 'repository');
      }
      for (const name of ['workflow-doc-templates', 'direct-invoke-code', 'direct-invoke-runtime', 'ops-direct-invoke-workflow', 'plugin-pr-submit', 'plugin-perf-iteration', 'plugin-experience-summary', 'infra-gitcode-api']) {
        assert.equal(existsSync(join(skills, name)), false, name);
      }
      for (const path of ['tasks/ascendc', 'tasks/common', 'workflows/ascendc', 'workflows/cannbot-dsl']) {
        assert.ok(lstatSync(join(skills, entry, path)).isDirectory(), path);
      }
      for (const path of ['workflows/common', 'workflows/registry.csv']) {
        assert.equal(existsSync(join(skills, entry, path)), false, path);
      }
      const tasks = join(skills, entry, 'tasks/ascendc');
      assert.equal(readdirSync(tasks).length, 8);
      for (const name of readdirSync(tasks)) assert.doesNotMatch(name, /^\d/);
      const templates = join(skills, entry, 'templates');
      const sourceTemplates = join(repository, sourceDirectory, 'skills', entry, 'templates');
      assert.deepEqual(readdirSync(templates).sort(), readdirSync(sourceTemplates).sort());
      for (const name of ['测试执行记录.md', '验收报告.md']) {
        assert.ok(existsSync(join(templates, name)), name);
      }
      for (const template of readdirSync(templates)) {
        assert.doesNotMatch(template, /^\d/);
        assert.equal(readFileSync(join(templates, template), 'utf8'), readFileSync(join(sourceTemplates, template), 'utf8'));
      }
      const guide = workflowGuide(join(skills, entry), box.root);
      assert.ok(guide.length);
      for (const template of guide) {
        assert.ok(template.use_when.length);
        const installed = join(skills, entry, 'workflows', template.file);
        const original = join(repository, sourceDirectory, 'skills', entry, 'workflows', template.file);
        assert.equal(readFileSync(installed, 'utf8'), readFileSync(original, 'utf8'));
      }
      for (const name of ['知识搜集.yaml', '白盒测试设计.yaml', '算子开发.yaml', '文档准备.yaml']) {
        assert.ok(readFileSync(join(tasks, name), 'utf8').trim(), name);
      }
      assert.equal(existsSync(join(tasks, '1.1.需求分析.yaml')), false);
      assert.equal(existsSync(join(tasks, '代码检视.yaml')), false);
      for (const name of localKnowledge) {
        const referenceRoot = join(repository, sourceDirectory, 'skills', name, 'references');
        for (const reference of readdirSync(referenceRoot)) {
          assert.equal(readFileSync(join(skills, name, 'references', reference), 'utf8'), readFileSync(join(referenceRoot, reference), 'utf8'));
        }
      }
      assert.deepEqual(readdirSync(skills).filter((name) => name.startsWith('workflow-cp')), []);
      for (const name of ['prompts', 'templates/docs', 'templates/workflows']) {
        assert.equal(existsSync(join(skills, entry, name)), false, name);
      }
      for (const name of ['generate_workflow_guide.py', 'assemble_workflow.py', 'run_workflow.py']) assert.ok(existsSync(join(skills, entry, 'scripts', name)));
      const agents = join(box.target, tool === 'claude' ? '.claude' : tool === 'codex' ? '.codex' : '.opencode', 'agents');
      const extension = tool === 'codex' ? '.toml' : '.md';
      assert.deepEqual(readdirSync(agents).filter((name) => name.startsWith('ops-direct-invoke-')).sort(),
        ['architect', 'developer', 'verifier'].map((name) => `ops-direct-invoke-${name}${extension}`));
      const instructionsPath = join(box.target, tool === 'claude' ? 'CLAUDE.md' : 'AGENTS.md');
      const instructions = readFileSync(instructionsPath, 'utf8');
      const sourceInstructions = readFileSync(join(repository, sourceDirectory, 'AGENTS.md'), 'utf8').trim();
      assert.ok(instructions.includes(sourceInstructions));
      assert.doesNotMatch(instructions, /ops-direct-invoke-pm/);
      writeFileSync(instructionsPath, `user instructions\n\n${instructions}`);
      install(box, tool, source);
      const reinstalled = readFileSync(instructionsPath, 'utf8');
      assert.match(reinstalled, /^user instructions\n/);
      assert.equal(reinstalled.split(sourceInstructions).length, 2);
      assert.doesNotMatch(reinstalled, /ops-direct-invoke-pm/);
      if (source === 'package') {
        assert.equal(existsSync(join(skills, 'workflow-orchestrator/scripts/__pycache__')), false);
      }
      if (source === 'repository') {
        for (const name of localKnowledge) {
          assert.equal(realpathSync(join(skills, name)), join(repository, sourceDirectory, 'skills', name));
        }
      }
    });
  }
}

test('harness knowledge overrides preserve the source and cannot replace scheduling', (t) => {
  const box = sandbox(t);
  const overrides = join(box.root, 'overrides');
  mkdirSync(join(overrides, 'repo-test-develop'), { recursive: true });
  writeFileSync(join(overrides, 'repo-test-develop/SKILL.md'), '---\nname: repo-test-develop\ndescription: test override\n---\nSUBREPO_SENTINEL\n');
  const source = join(repository, sourceDirectory, 'skills/repo-test-develop/SKILL.md');
  const original = readFileSync(source, 'utf8');
  const skills = install(box, 'codex', 'repository', ['--override-skills', overrides]);
  assert.match(readFileSync(join(skills, 'repo-test-develop/SKILL.md'), 'utf8'), /SUBREPO_SENTINEL/);
  assert.equal(readFileSync(source, 'utf8'), original);
  mkdirSync(join(overrides, 'workflow-orchestrator'));
  writeFileSync(join(overrides, 'workflow-orchestrator/SKILL.md'), '---\nname: workflow-orchestrator\n---\n');
  const result = spawnSync(process.execPath, [cli, 'install', plugin, '--source', repository, '--plugin-dir', sourceDirectory,
    '--tool', 'codex', '--target', box.target, '--override-skills', overrides,
    '--skills', join(repository, 'vendor/cannbot-skills')], { env: box.env, encoding: 'utf8' });
  assert.equal(result.status, 1);
  assert.match(result.stderr, /cannot be overridden/);
});

test('harness source init delegates to the unified installer', (t) => {
  const box = sandbox(t);
  const result = spawnSync('bash', [join(repository, sourceDirectory, 'init.sh'), 'project', 'codex', box.target,
    '--skills', join(repository, 'vendor/cannbot-skills')],
    { env: box.env, encoding: 'utf8' });
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.ok(existsSync(join(box.target, '.agents/skills', entry, 'tasks/ascendc/知识搜集.yaml')));
});

function prepare(box, skills, input = 'template') {
  const work = join(box.target, '.cannbot/AddExample/workflow1');
  const root = join(skills, entry);
  const guide = workflowGuide(root, box.root);
  const selected = guide.find((template) => template.file === 'ascendc/basic.yaml');
  assert.ok(selected);
  const template = join(root, 'workflows', selected.file);
  const complete = join(box.root, 'assembled.yaml');
  if (input === 'yaml') {
    const result = spawnSync('python3', [join(root, 'scripts/assemble_workflow.py'),
      '--template', template, '--output', complete], { encoding: 'utf8' });
    assert.equal(result.status, 0, result.stderr);
  }
  const definition = input === 'template'
    ? ['--template', selected.file]
    : ['--yaml', complete];
  return { work, template, complete, run: [join(root, 'scripts/run_workflow.py'), '--provider', 'codex',
    ...definition, '--work-dir', work, '--foreground', '--dry-run'] };
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
    assert.equal(Object.keys(current.tasks).length, 7);
    assert.equal(current.tasks['3'].retries, 1);
    for (const tid of ['0.0', '0.1', '1', '2', '3', '4', '5']) {
      assert.equal(current.tasks[tid].status, 'pass', tid);
    }
    for (const tid of ['0.CP', '1.1.CP', '2.1.CP', '2.2.CP', '3.4.CP', '4.CP',
      '4.1', '4.2', '4.3', '7.0.1', '7.0.2', '7.0.3', '7.0.4', '7.1', '7.2']) {
      assert.equal(current.tasks[tid], undefined, tid);
    }
    assert.equal(existsSync(join(prepared.work, 'run-inputs.json')), false);
    assert.equal(existsSync(join(prepared.work, 'verification')), false);

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

const entryScripts = join(repository, sourceDirectory, 'skills', entry, 'scripts');

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
  const result = spawnSync('python3', [join(root, 'scripts/generate_workflow_guide.py'), '--output', output],
    { cwd: directory, encoding: 'utf8' });
  assert.equal(result.status, 0, result.stdout + result.stderr);
  return csvValue(output);
}

function taskFixture(box, name) {
  const task = yamlValue(join(entryScripts, '../tasks/ascendc/知识搜集.yaml'));
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
    assert.equal(workflow.nodes.length, inputs.length);
    workflow.nodes.forEach(({ id, depends_on, ...task }, index) => {
      assert.equal(id, String(index));
      assert.deepEqual(depends_on, index === 0 ? [] : [String(index - 1)]);
      assert.equal(task.max_retries, 1);
      assert.deepEqual(task, { ...JSON.parse(JSON.stringify(inputs[index].task).replaceAll('{{id}}', id)), max_retries: 1 });
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
  // Only the common framework and domain Skill repository are shared with the source tree.
  symlinkSync(join(repository, 'harness'), join(isolated, 'harness'), 'dir');
  symlinkSync(join(repository, 'vendor'), join(isolated, 'vendor'), 'dir');
  assert.equal(existsSync(join(isolated, 'plugins-community')), false);
  const bundles = assemblePlugins(isolated, join(box.root, 'dist'), [basename(sourceDirectory)]);
  assert.equal(bundles.length, 1);
  for (const name of localKnowledge) assert.ok(existsSync(join(bundles[0].destination, 'skills', name, 'SKILL.md')));
  const result = spawnSync(process.execPath, [cli, 'install', plugin, '--source', isolated, '--plugin-dir', sourceDirectory,
    '--tool', 'codex', '--target', box.target,
    '--skills', join(repository, 'vendor/cannbot-skills')], { env: box.env, encoding: 'utf8' });
  assert.equal(result.status, 0, result.stdout + result.stderr);
  const skills = join(box.target, '.agents/skills');
  for (const name of localKnowledge) {
    assert.equal(realpathSync(join(skills, name)), join(isolated, sourceDirectory, 'skills', name));
  }
  const completed = simulate(box, prepare(box, skills));
  assert.equal(completed.status, 0, completed.stdout + completed.stderr);
});


test('discovered workflow templates reproduce from tasks and reference installed document templates', (t) => {
  const box = sandbox(t);
  const root = join(repository, sourceDirectory, 'skills', entry);
  const guide = workflowGuide(root, box.root);
  assert.equal(new Set(guide.map((item) => item.file)).size, guide.length);
  assert.deepEqual(guide.map((item) => item.file).sort(),
    readdirSync(join(root, 'workflows'), { recursive: true })
      .filter((name) => name.endsWith('.yaml') && !name.endsWith('.graph-preview.yaml')).sort());
  for (const template of guide) {
    const output = join(box.root, template.file);
    const path = join(root, 'workflows', template.file);
    const reference = yamlValue(path);
    const result = spawnSync('python3', [join(root, 'scripts/assemble_workflow.py'), '--output', output,
      '--template', path], { encoding: 'utf8' });
    assert.equal(result.status, 0, result.stdout + result.stderr);
    const expected = yamlValue(output);
    // Complete workflows inline their task content: the freeze keeps the graph and drops use_when.
    if (!reference.nodes.some((node) => 'yaml' in node)) {
      const { use_when, ...frozen } = reference;
      assert.equal(template.use_when, use_when);
      assert.deepEqual(expected, frozen);
      continue;
    }
    assert.deepEqual(expected.nodes.map(({ id, depends_on, max_retries }) => ({ id, depends_on, max_retries })),
      reference.nodes.map(({ id, depends_on, max_retries }) => ({ id, depends_on, max_retries })));
    for (const [index, node] of expected.nodes.entries()) {
      const ref = reference.nodes[index];
      if (!('yaml' in ref)) {
        assert.deepEqual(node, ref);
        continue;
      }
      const task = yamlValue(resolve(dirname(path), ref.yaml));
      assert.equal(task.max_retries, undefined);
      assert.deepEqual(node.goal, task.goal);
      assert.equal(node.title, task.title);
      assert.equal(node.yaml, undefined);
      assert.equal(node.variables, undefined);
    }
    for (const node of expected.nodes) {
      for (const match of JSON.stringify(node).matchAll(/ops-direct-invoke\/(templates\/[^`"\\\s/，。]+\.md)/g)) {
        assert.ok(existsSync(join(root, match[1])), match[1]);
      }
    }
  }
});

test('launcher requires one workflow input and rejects unavailable or escaped template paths', (t) => {
  const box = sandbox(t);
  for (const [args, error] of [
    [[], /required/],
    [['--yaml', 'custom.yaml', '--template', 'ascendc/basic.yaml'], /not allowed/],
    [['--template', 'missing.yaml'], /No such file/],
    [['--template', '../templates/知识搜集.md'], /must stay inside/],
    [['--template', '.'], /must be a file/],
  ]) {
    const result = spawnSync('python3', [join(entryScripts, 'run_workflow.py'), ...args,
      '--work-dir', join(box.root, 'not-started'), '--provider', 'codex', '--foreground'], { encoding: 'utf8' });
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
  const result = spawnSync(process.execPath, [cli, 'install', 'ascendc-st-design', '--source', repository,
    '--plugin-dir', sourceDirectory, '--tool', 'codex', '--target', box.target], { env: box.env, encoding: 'utf8' });
  assert.equal(result.status, 1);
  assert.match(result.stderr, /plugin name mismatch/);
  assert.deepEqual(readdirSync(box.target), []);
});
