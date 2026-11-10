import test from 'node:test'
import assert from 'node:assert/strict'
import { copyFile, mkdtemp, mkdir, readFile, realpath, symlink, writeFile, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { execFileSync } from 'node:child_process'
import { NativeWorkflow, prepareWorkflow } from '../../../../dsh/src/native-workflow.mjs'

const scripts = fileURLToPath(new URL('../../../../harness/workflow-orchestrator/scripts/', import.meta.url))
const runner = join(scripts, 'orchestrator.py')
async function fixture(t) {
  const cwd = await mkdtemp(join(tmpdir(), 'native-workflow-'))
  t.after(() => rm(cwd, { recursive: true, force: true }))
  const resources = join(cwd, 'resources')
  await mkdir(join(resources, 'agents'), { recursive: true })
  for (const role of ['general-executor', 'general-verifier']) await writeFile(join(resources, 'agents', role + '.md'), `Role: ${role}`)
  const yaml = join(resources, 'workflow.yaml')
  const node = (id, depends_on = []) => ({ id, task_type: 'normal', title: id,
    goal: ['complete'], approach: ['complete'], acceptance: ['pass'], out_of_scope: ['none'],
    depends_on, executor: 'general-executor', verifier: 'general-verifier', max_retries: 1, on_exhaust: 'exit' })
  await writeFile(yaml, JSON.stringify({ workflow: 'native-test', max_parallel: 2,
    nodes: [node('a'), node('b'), node('c', ['a', 'b'])] }))
  return { runner, yaml, cwd, resources, prompt: 'test native workflow' }
}

const workspaceTools = fileURLToPath(new URL('../../tools/', import.meta.url))

async function attachAdapter(spec) {
  await mkdir(join(spec.resources, 'tools'), { recursive: true })
  await copyFile(join(workspaceTools, 'dsh-native.mjs'), join(spec.resources, 'tools/dsh-native.mjs'))
  await writeFile(join(spec.resources, 'plugin-install.json'), JSON.stringify({ nativeWorkflow: 'tools/dsh-native.mjs' }))
}

async function isolatedFixture(t, performance = false) {
  const spec = await fixture(t)
  // Use the real freezer and phase preparer, with small local Skill/installer fixtures.
  execFileSync('python3', ['-B', '-c', String.raw`
import json, pathlib, shutil, sys
root, tools, harness = map(pathlib.Path, sys.argv[1:])
sys.path.insert(0, str(tools))
from workspace import prepare
source = root / 'source'
def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
def skill(path, name):
    write(path / 'SKILL.md', f'---\nname: {name}\ndescription: fixture\n---\n{name}\n')
for group, suffix in {'requirement': 'ascend', 'repo-guide': 'common', 'engineering': 'common',
                      'env-check': 'ascend/ascendc', 'doc-templates': 'ascend/ascendc'}.items():
    skill(source / 'skills/custom-skills' / group / suffix, 'ops-direct-invoke-' + group)
write(source / 'skills/custom-skills/env-check/ascend/platform.json', json.dumps({'languages': ['ascendc']}))
write(source / 'skills/custom-skills/engineering/common/support.json', json.dumps({'platforms': ['ascend'], 'languages': ['ascendc']}))
for role in ['general-executor', 'general-verifier', 'ops-direct-invoke-architect']:
    write(source / 'agents' / (role + '.md'), 'FROZEN ROLE: ' + role)
for name in ['docs', 'orchestrations']:
    (source / name).mkdir()
shutil.copytree(tools, source / 'tools', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
external = root / 'external'
shutil.copytree(harness, external / 'workflow-orchestrator', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
perf = root / 'performance'
skill(perf / '.dsh/skills/ops-perf-optimize-workflow', 'ops-perf-optimize-workflow')
write(perf / '.cannbot/plugins/ops-perf-optimize/AGENTS.md', 'FROZEN PERF IDENTITY')
registry = perf / '.dsh/cannbot-plugin.json'
write(registry, json.dumps({'plugins': [{'plugin': 'ops-perf-optimize', 'skills': ['.dsh/skills/ops-perf-optimize-workflow']}]}))
config = root / 'init.json'
write(config, json.dumps({'schema_version': 1, 'asset_root': str(source), 'external_skills_root': str(external),
    'performance_root': str(perf), 'performance_registry': str(registry), 'repo': 'common',
    'platform': 'ascend', 'chip': 'test', 'preferences': {}, 'tool': 'dsh'}))
prepare(config, root, 'ascendc', 'fixture', 'common', root / 'code')
`, spec.cwd, workspaceTools, join(scripts, '..')], { encoding: 'utf8' })
  const definition = JSON.parse(await readFile(spec.yaml, 'utf8'))
  definition.nodes = [definition.nodes[0]]
  if (performance) definition.nodes[0].executor = 'perf-optimize'
  await writeFile(spec.yaml, JSON.stringify(definition))
  await writeFile(`${spec.yaml}.contexts.yaml`, JSON.stringify({
    a: { execute: { skills: [performance ? 'ops-perf-optimize-workflow' : 'ops-direct-invoke-repo-guide'] }, verify: { skills: ['ops-direct-invoke-doc-templates'] } },
  }))
  await attachAdapter(spec)
  Object.assign(spec, await prepareWorkflow(spec.resources, { ...spec, workflow: 'ops-direct-invoke' }))
  assert.ok(spec.runner.startsWith(join(spec.cwd, '.context/external-skills/workflow-orchestrator')))
  return spec
}

test('frozen direct-invoke phases cross the Python bridge with separate cwd, identity and selected Skills', { timeout: 20000 }, async t => {
  const spec = await isolatedFixture(t), parent = { id: 'isolated-parent' }, calls = []
  const execution = new NativeWorkflow({ subagents: { async startActivation(options) {
    const [, id, phase] = /^CANNBot (\w+) · (\w+)$/.exec(options.label)
    const cwd = join(spec.cwd, 'agents', id, phase === 'verify' ? 'verifier' : phase)
    assert.equal(options.request.cwd, cwd)
    assert.equal('env' in options.request, false)
    const prompt = options.request.prompt[0].text
    assert.match(prompt, new RegExp(`FROZEN ROLE: general-${phase === 'verify' ? 'verifier' : 'executor'}`))
    assert.match(prompt, /Selected Skills:/)
    assert.match(prompt, new RegExp(`ops-direct-invoke-${phase === 'verify' ? 'doc-templates' : 'repo-guide'}`))
    assert.doesNotMatch(prompt, /Workflow resources:|ops-direct-invoke-engineering/)
    assert.ok(prompt.includes(`export WORK_DIR=${spec.cwd}`))
    assert.ok(prompt.includes(`export CODE_DIR=${join(spec.cwd, 'code')}`))
    const identity = await realpath(join(cwd, 'AGENTS.md'))
    assert.equal(identity, join(spec.cwd, '.context/plugin/agents', `general-${phase === 'verify' ? 'verifier' : 'executor'}.md`))
    calls.push(cwd)
    if (phase === 'verify') execFileSync('python3', [join(scripts, 'verdict_pass.py'), '--work-dir', spec.cwd, '--task-id', id])
    return { childId: phase, result: Promise.resolve({ stopReason: 'completed', output: 'done' }), async dispose() {} }
  } } })
  t.after(() => execution.dispose())
  const handle = await execution.start(parent, spec)
  const result = await execution.status(parent, handle.runId, 15000)
  assert.equal(result.exitCode, 0, result.log)
  assert.equal(calls.length, 2)
  assert.equal(new Set(calls).size, 2)
  assert.equal(result.state.tasks.a.status, 'pass')
})

test('frozen resources are verified before native child activation', { timeout: 10000 }, async t => {
  const spec = await isolatedFixture(t)
  await writeFile(join(spec.cwd, '.context/plugin/agents/general-executor.md'), 'changed identity')
  const execution = new NativeWorkflow({ subagents: { async startActivation() { assert.fail('must not dispatch changed resources') } } })
  t.after(() => execution.dispose())
  await assert.rejects(prepareWorkflow(spec.resources, { ...spec, workflow: 'ops-direct-invoke' }), /frozen resources changed/)
  const request = { taskId: 'a', phase: 'execute', role: 'general-executor', prompt: 'test', workDir: spec.cwd }
  await assert.rejects(execution.executeNode({}, request, spec.resources, new AbortController().signal, spec.prepareNode), /frozen resources changed/)
})

test('delegated performance keeps the original perf-optimize identity', { timeout: 10000 }, async t => {
  const spec = await isolatedFixture(t, true), parent = { id: 'performance-parent' }, calls = []
  const execution = new NativeWorkflow({ subagents: { async startActivation(options) {
    const [, id, phase] = /^CANNBot (\w+) · (\w+)$/.exec(options.label)
    const identity = await realpath(join(options.request.cwd, 'AGENTS.md'))
    if (phase === 'execute') {
      assert.equal(identity, join(spec.cwd, '.context/performance/.cannbot/plugins/ops-perf-optimize/AGENTS.md'))
      assert.match(options.request.prompt[0].text, /FROZEN PERF IDENTITY/)
    } else {
      assert.equal(identity, join(spec.cwd, '.context/plugin/agents/general-verifier.md'))
      execFileSync('python3', [join(scripts, 'verdict_pass.py'), '--work-dir', spec.cwd, '--task-id', id])
    }
    calls.push(phase)
    return { childId: phase, result: Promise.resolve({ stopReason: 'completed' }), async dispose() {} }
  } } })
  t.after(() => execution.dispose())
  const handle = await execution.start(parent, spec)
  const result = await execution.status(parent, handle.runId, 5000)
  assert.equal(result.exitCode, 0, result.log)
  assert.deepEqual(calls, ['execute', 'verify'])
})

test('phase adapter derives identity and Skills from the frozen graph and rejects workspace escape', async t => {
  const spec = await isolatedFixture(t)
  const request = { taskId: 'a', phase: 'execute', role: 'general-executor', prompt: 'test', workDir: spec.cwd }
  const signal = new AbortController().signal
  const prepared = await spec.prepareNode({ ...request, cwd: tmpdir(), identity: '/untrusted/identity',
    skills: { 'not-selected': spec.resources } }, signal)
  assert.equal(prepared.cwd, join(spec.cwd, 'agents/a/execute'))
  assert.match(prepared.prompt, /FROZEN ROLE: general-executor/)
  assert.match(prepared.prompt, /ops-direct-invoke-repo-guide/)
  assert.doesNotMatch(prepared.prompt, /untrusted|not-selected/)
  await assert.rejects(spec.prepareNode({ ...request, workDir: tmpdir() }, signal), /another workflow/)
  await rm(join(spec.cwd, 'agents/a/execute'), { recursive: true })
  await symlink(tmpdir(), join(spec.cwd, 'agents/a/execute'))
  await assert.rejects(spec.prepareNode(request, signal), /private directory|symlink|inside this workflow/)
})

test('an unrelated workflow context does not enable direct-invoke phase preparation', { timeout: 10000 }, async t => {
  const spec = await fixture(t)
  await writeFile(join(spec.cwd, 'context.json'), JSON.stringify({ plugin: 'other-workflow', plugin_root: '/unused' }))
  const execution = new NativeWorkflow({ subagents: { async startActivation(options) {
    assert.equal(options.request.cwd, spec.cwd)
    assert.match(options.request.prompt[0].text, /Workflow resources:/)
    const [, id, phase] = /^CANNBot (\w+) · (\w+)$/.exec(options.label)
    if (phase === 'verify') execFileSync('python3', [join(scripts, 'verdict_pass.py'), '--work-dir', spec.cwd, '--task-id', id])
    return { childId: id, result: Promise.resolve({ stopReason: 'completed' }), async dispose() {} }
  } } })
  t.after(() => execution.dispose())
  const parent = { id: 'other-plugin' }, handle = await execution.start(parent, spec)
  const result = await execution.status(parent, handle.runId, 5000)
  assert.equal(result.exitCode, 0, result.log)
})


test('direct workflow launch requires prepared context and rejects an unfrozen scheduler', async t => {
  const missing = await fixture(t)
  await attachAdapter(missing)
  await assert.rejects(prepareWorkflow(missing.resources, { ...missing, workflow: 'ops-direct-invoke' }), /Prepare context.json/)
  const spec = await isolatedFixture(t)
  await assert.rejects(prepareWorkflow(spec.resources, { ...spec, workflow: 'other-plugin' }), /another plugin/)
  const contextPath = join(spec.cwd, 'context.json')
  const context = JSON.parse(await readFile(contextPath, 'utf8'))
  context.skills['workflow-orchestrator'] = join(scripts, '..')
  await writeFile(contextPath, JSON.stringify(context))
  await assert.rejects(prepareWorkflow(spec.resources, { ...spec, workflow: 'ops-direct-invoke' }), /frozen workflow/)
})
