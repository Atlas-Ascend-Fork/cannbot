import { installGoalWorkflowResume } from '../src/goal-workflow-resume.mjs'
import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtemp, mkdir, writeFile, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { execFileSync } from 'node:child_process'
import { NativeWorkflow } from '../src/native-workflow.mjs'
import { pythonBootstrap } from '../src/native-workflow-bootstrap.mjs'

const scripts = fileURLToPath(new URL('../../harness/workflow-orchestrator/scripts/', import.meta.url))
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

test('ordinary CLI retains its provider interface without plugin-specific parameters', () => {
  const help = execFileSync('python3', [runner, '--help'], { encoding: 'utf8' })
  assert(help.includes('--provider'))
  assert(!help.includes('--execution'))
  const pluginHelp = execFileSync('python3', ['-c', pythonBootstrap, runner, '--help'], { encoding: 'utf8' })
  assert.equal(pluginHelp, help)
})

test('plugin bootstrap rejects a CLI provider before launching an executor', () => {
  assert.throws(() => execFileSync('python3', ['-c', pythonBootstrap, runner,
    '--yaml', 'unused.yaml', '--work-dir', '/unused', '--provider', 'codex'], { stdio: 'pipe' }),
  error => error.status !== 0 && error.stderr.toString().includes('plugin supplies its execution callback'))
})

test('Python schedules concurrent nodes, retries, verdicts and dependencies through native DSH activations', { timeout: 20000 }, async t => {
  const spec = await fixture(t), parent = { id: 'session-a' }, calls = [], finished = new Set()
  let active = 0, maxActive = 0, failed = false, disposed = 0
  const execution = new NativeWorkflow({ subagents: { async startActivation(options) {
    assert.equal(options.provider, 'spawn')
    assert.equal(options.request.parent, parent)
    assert.equal(options.request.cwd, spec.cwd)
    assert(!('agentOptions' in options.request)) // Model route inherits from the parent.
    const [, id, phase] = /^CANNBot (\w+) · (\w+)$/.exec(options.label)
    calls.push([id, phase])
    if (id === 'c') assert.deepEqual([...finished].sort(), ['a', 'b'])
    active++; maxActive = Math.max(active, maxActive)
    const result = new Promise(accept => setTimeout(() => {
      active--
      if (id === 'a' && phase === 'execute' && !failed) {
        failed = true; accept({ stopReason: 'error', output: 'simulated node failure' }); return
      }
      if (phase === 'verify') {
        execFileSync('python3', [join(scripts, 'verdict_pass.py'), '--work-dir', spec.cwd, '--task-id', id])
        if (id !== 'c') finished.add(id)
      }
      accept({ stopReason: 'completed', output: 'done' })
    }, 150))
    return { childId: `${id}-${phase}`, result, async dispose() { disposed++ } }
  } } })
  t.after(() => execution.dispose())
  const handle = await execution.start(parent, spec)
  await assert.rejects(execution.start(parent, spec), /already running/)
  await assert.rejects(execution.status({ id: 'other-session' }, handle.runId), /unavailable/)
  const result = await execution.status(parent, handle.runId, 15000)
  assert.equal(result.exitCode, 0, result.log)
  assert.equal(result.status, 'completed')
  assert.equal(maxActive, 2)
  assert.equal(calls.filter(([id, phase]) => id === 'a' && phase === 'execute').length, 2)
  assert.equal(disposed, calls.length)
  assert(Object.values(result.state.tasks).every(task => task.status === 'pass'))
})

test('goal pause stops Python and native children, then goal resume completes saved work', { timeout: 20000 }, async t => {
  const spec = await fixture(t), parent = { id: 'session-a' }
  parent.session = { id: parent.id, todos: [{ content: 'Agent plan', status: 'pending' }], append(type, data) {
    assert.equal(type, 'todo/write'); this.todos = data.todos
  } }
  let started
  const waiting = new Promise(accept => { started = accept })
  let cancellation = false
  const execution = new NativeWorkflow({ sessionProjections: { stateOf: session => session.todos }, subagents: { async startActivation(options) {
    let finish
    const result = new Promise(accept => { finish = accept })
    started()
    return { childId: 'waiting', result, async dispose() {
      cancellation = true; finish({ stopReason: 'cancelled', output: '' })
    } }
  } } })
  t.after(() => execution.dispose())
  const handle = await execution.start(parent, spec)
  await waiting
  // No status-tool call: the background sync alone must drive the native list.
  for (let attempt = 0; attempt < 30 && !parent.session.todos.some(todo => todo.status === 'in_progress'); attempt++) {
    await new Promise(resolve => setTimeout(resolve, 100))
  }
  assert(parent.session.todos.some(todo => todo.status === 'in_progress'))
  assert.equal(parent.session.todos[0].content, 'Agent plan')
  const hooks = new Map()
  const goal = { id: 'goal', revision: 2, phase: 'active' }
  const events = [
    { seq: 0, type: 'goal/change', data: { operation: 'create', goal } },
    { seq: 1, type: 'tool/call', data: { turn: 1, name: 'cannbot_workflow_run', callId: 'start', arguments: JSON.stringify({ workflow: 'native-test', yaml: spec.yaml }) } },
    { seq: 2, type: 'tool/result', data: { message: { toolCallId: 'start', content: [{ text: JSON.stringify(handle) }] } } },
  ]
  let resumed
  installGoalWorkflowResume({
    on: (name, listener) => hooks.set(name, listener), goals: { get: () => goal },
    workingDirectory: { ensure: async () => spec.cwd },
    sessionQuery: { readSession: async () => ({ events }) },
  }, execution, async (args, agent) => {
    assert.equal(args.prompt, undefined)
    resumed = await execution.start(agent, { ...spec, prompt: undefined })
    return resumed
  })
  await hooks.get('goal/changed')({ agent: parent, change: { operation: 'pause', ref: { id: goal.id, revision: goal.revision } } })
  const result = await execution.status(parent, handle.runId)
  assert.equal(cancellation, true)
  assert.equal(result.status, 'paused')
  assert(parent.session.todos.some(todo => todo.content.includes('已暂停')))
  assert(!parent.session.todos.some(todo => todo.status === 'in_progress'))
  execution.ctx.subagents.startActivation = async options => {
    const [, id, phase] = /^CANNBot (\w+) · (\w+)$/.exec(options.label)
    if (phase === 'verify') execFileSync('python3', [join(scripts, 'verdict_pass.py'), '--work-dir', spec.cwd, '--task-id', id])
    return { childId: id, result: Promise.resolve({ stopReason: 'completed', output: '' }), async dispose() {} }
  }
  hooks.get('goal/changed')({ agent: parent, change: { operation: 'resume', ref: { id: goal.id, revision: goal.revision } } })
  const decision = await hooks.get('agent/pre-step')({ agent: parent, signal: new AbortController().signal }, async () => ({
    kind: 'enter', messages: [{ role: 'user', content: [{ type: 'text', text: 'Continue goal' }] }],
  }))
  assert.match(JSON.stringify(decision.messages), new RegExp(resumed.runId))
  const final = await execution.status(parent, resumed.runId, 15000)
  assert.equal(final.exitCode, 0, final.log)
  assert.equal(parent.session.todos.length, 4)
  assert(parent.session.todos.slice(1).every(todo => todo.status === 'completed'))
})
