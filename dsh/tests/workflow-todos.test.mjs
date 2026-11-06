import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtemp, mkdir, writeFile, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { WorkflowTodos, workflowTodos, readTaskNames, externalWorkflowLaunch } from '../src/workflow-todos.mjs'

function fixture() {
  const listeners = new Set()
  const ctx = {
    on(event, callback) { if (event === 'session/event') listeners.add(callback); return () => listeners.delete(callback) },
    sessionProjections: { stateOf(session) { return session.todos } },
  }
  const tracker = new WorkflowTodos(ctx)
  function parent(id) {
    const session = { id, todos: null, events: [], append(type, data = {}) {
      this.events.push({ type, data })
      if (type === 'todo/write') this.todos = data.todos
      if (type === 'turn/start') this.todos = null
      for (const listener of listeners) listener(this, { type, data })
    } }
    return { id, session }
  }
  return { ctx, tracker, parent }
}
const state = status => ({ tasks: { design: { status, retries: 1 } } })
const run = { workflow: 'ops-direct-invoke', cwd: '/workspace/one' }
const flush = () => new Promise(resolve => setImmediate(resolve))

test('maps real workflow progress to native statuses without marking failures completed', () => {
  for (const status of ['running', 'executed', 'verifying', 'awaiting_approval']) {
    assert.equal(workflowTodos('flow', state(status))[0].status, 'in_progress')
  }
  assert.match(workflowTodos('flow', state('awaiting_approval'))[0].content, /待审批.*重试 1/)
  assert.equal(workflowTodos('flow', state('pass'))[0].status, 'completed')
  assert.equal(workflowTodos('flow', state('skipped'))[0].status, 'completed')
  assert.equal(workflowTodos('flow', state('fail'))[0].status, 'pending')
  assert.match(workflowTodos('flow', state('fail'))[0].content, /失败/)
  assert.match(workflowTodos('flow', state('running'), true)[0].content, /已中断/)
  assert.equal(workflowTodos('flow', state('running'), true)[0].status, 'pending')
})

test('merges workflow tasks into native todos, preserves agent tasks and avoids duplicate events', async () => {
  const f = fixture(), parent = f.parent('A')
  const own = { content: '用户已有计划', status: 'in_progress' }
  parent.session.append('todo/write', { todos: [own] })
  f.tracker.update(parent, run, state('running'))
  assert.deepEqual(parent.session.todos[0], own)
  assert.equal(parent.session.todos.length, 2)
  assert.equal(parent.session.todos[1].status, 'in_progress')
  const count = parent.session.events.length
  f.tracker.update(parent, run, state('running'))
  await flush()
  assert.equal(parent.session.events.length, count)
  f.tracker.update(parent, run, state('pass'), true)
  assert.equal(parent.session.todos.length, 2)
  assert.equal(parent.session.todos[1].status, 'completed')
  f.tracker.dispose()
})

test('restores workflow rows after an agent writes its own list and respects turn boundaries', async () => {
  const f = fixture(), parent = f.parent('A')
  f.tracker.update(parent, run, state('verifying'))
  parent.session.append('todo/write', { todos: [{ content: 'Agent 新计划', status: 'pending' }] })
  await flush()
  assert.equal(parent.session.todos.length, 2)
  assert.equal(parent.session.todos[0].content, 'Agent 新计划')
  parent.session.append('turn/start')
  await flush()
  assert.equal(parent.session.todos.length, 1)
  assert.match(parent.session.todos[0].content, /验证中/)
  f.tracker.update(parent, run, state('pass'), true)
  parent.session.append('turn/end')
  await flush()
  assert.equal(parent.session.todos[0].status, 'completed')
  parent.session.append('turn/start')
  await flush()
  assert.equal(parent.session.todos[0].status, 'completed')
  f.tracker.dispose()
})

test('isolates sessions and distinguishes parallel runs without duplicating resumed rows', async () => {
  const f = fixture(), a = f.parent('A'), b = f.parent('B')
  f.tracker.update(a, run, state('running'))
  f.tracker.update(b, run, state('pending'))
  assert.equal(b.session.todos[0].status, 'pending')
  f.tracker.update(a, { ...run, cwd: '/workspace/two' }, state('verifying'))
  assert.equal(a.session.todos.length, 2)
  assert.notEqual(a.session.todos[0].content, a.session.todos[1].content)
  f.tracker.update(a, run, state('pass'), true)
  assert.equal(a.session.todos.length, 2)
  f.tracker.update(a, run, state('running'))
  assert.equal(a.session.todos.length, 2)
  f.tracker.dispose()
  const count = a.session.events.length
  await flush()
  assert.equal(a.session.events.length, count)
})


test('restores pre-install sessions from successful starts and retains interrupted tasks next turn', async () => {
  const workspace = await mkdtemp(join(tmpdir(), 'workflow-todos-'))
  const f = fixture(), parent = f.parent('restored')
  try {
    await mkdir(join(workspace, '.workflow'))
    await writeFile(join(workspace, 'workflow.yaml'), 'nodes:\n  - id: design\n    title: 黑盒测试设计\n')
    await writeFile(join(workspace, '.workflow/status.json'), JSON.stringify({ ...state('running'), workflow: join(workspace, 'workflow.yaml') }))
    parent.session.header = { cwd: workspace }
    f.ctx.sessionQuery = { async readSession() { return { events: [
      { seq: 0, type: 'tool/call', data: { callId: 'start', name: 'cannbot_workflow_run', arguments: JSON.stringify({ workflow: 'ops-direct-invoke' }) } },
      { seq: 1, type: 'tool/result', data: { message: { toolCallId: 'start', content: [{ text: JSON.stringify({ runId: 'old', workDir: workspace }) }] } } },
    ] } } }
    await f.tracker.restore(parent.session)
    assert.equal(parent.session.todos.length, 1)
    assert.match(parent.session.todos[0].content, /ops-direct-invoke \/ 黑盒测试设计.*已中断/)
    parent.session.append('turn/start')
    await flush()
    assert.match(parent.session.todos[0].content, /已中断/)
    f.tracker.update(parent, { ...run, cwd: workspace }, state('running'))
    await f.tracker.restore(parent.session)
    assert.match(parent.session.todos[0].content, /执行中/)
    const other = f.parent('fork')
    other.session.header = { cwd: workspace }
    other.session.inheritedEventCount = 2
    await f.tracker.restore(other.session)
    assert.equal(other.session.todos, null)
  } finally { f.tracker.dispose(); await rm(workspace, { recursive: true, force: true }) }
})


test('uses YAML titles for numeric task IDs and falls back for unnamed tasks', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'workflow-names-'))
  try {
    const yaml = join(dir, 'flow.yaml')
    await writeFile(yaml, 'nodes:\n  - id: 0\n    title: 黑盒测试设计\n  - id: "1"\n    title: 测试工程开发\n  - id: 2\n')
    const names = await readTaskNames(yaml)
    const rows = workflowTodos('flow', { tasks: { '0': { status: 'running' }, '1': { status: 'pending' }, '2': { status: 'pass' } } }, false, names)
    assert.match(rows[0].content, /黑盒测试设计/)
    assert.match(rows[1].content, /测试工程开发/)
    assert.match(rows[2].content, /flow \/ 2/)
    assert.equal((await readTaskNames(join(dir, 'missing.yaml'))).size, 0)
  } finally { await rm(dir, { recursive: true, force: true }) }
})

test('retains actual completion order when parallel tasks finish out of node order', async () => {
  const f = fixture(), parent = f.parent('parallel')
  f.tracker.update(parent, run, { tasks: { a: { status: 'running' }, b: { status: 'pass' } } })
  f.tracker.update(parent, run, { tasks: { a: { status: 'pass' }, b: { status: 'pass' } } }, true)
  const rows = parent.session.todos
  assert.match(rows[0].content, / \/ b /)
  assert.match(rows[1].content, / \/ a /)
  parent.session.append('turn/start')
  await flush()
  assert.deepEqual(parent.session.todos, rows)
  f.tracker.dispose()
})


test('tracks the latest explicit external launch and refreshes state without a status tool call', async () => {
  const workspace = await mkdtemp(join(tmpdir(), 'external-workflow-'))
  const f = fixture(), parent = f.parent('external')
  try {
    parent.session.header = { cwd: workspace }
    const events = []
    for (const name of ['old', 'new']) {
      const cwd = join(workspace, name), yaml = join(cwd, 'workflow.yaml')
      await mkdir(join(cwd, '.workflow'), { recursive: true })
      await writeFile(yaml, 'workflow: flow\nnodes:\n  - id: design\n    title: 新设计\n')
      await writeFile(join(cwd, '.workflow/status.json'), JSON.stringify({ ...state('running'), workflow: yaml }))
      events.push({ seq: events.length, type: 'tool/call', data: { name: 'bash', arguments: JSON.stringify({ command: `python3 /skills/run_workflow.py --yaml "${yaml}" --work-dir "${cwd}" --provider codex` }) } })
    }
    f.ctx.sessionQuery = { readSession: async () => ({ events }) }
    assert.equal(externalWorkflowLaunch(events[1]).cwd, join(workspace, 'new'))
    await f.tracker.restore(parent.session)
    assert.equal(parent.session.todos.length, 1)
    assert.match(parent.session.todos[0].content, /新设计.*执行中/)
    await writeFile(join(workspace, 'new/.workflow/status.json'), JSON.stringify({ ...state('pass'), workflow: join(workspace, 'new/workflow.yaml') }))
    await f.tracker.restore(parent.session, true)
    assert.equal(parent.session.todos[0].status, 'completed')
    const count = parent.session.events.length
    await f.tracker.restore(parent.session, true)
    assert.equal(parent.session.events.length, count)
    assert.equal(externalWorkflowLaunch({ type: 'tool/call', data: { name: 'bash', arguments: JSON.stringify({ command: 'python3 run_workflow.py --yaml "$YAML" --work-dir "$DIR"' }) } }), undefined)
  } finally { f.tracker.dispose(); await rm(workspace, { recursive: true, force: true }) }
})
