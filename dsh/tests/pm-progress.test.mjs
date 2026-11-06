import test from 'node:test'
import assert from 'node:assert/strict'
import { PmProgress } from '../src/pm-progress.mjs'
import { WorkflowTodos } from '../src/workflow-todos.mjs'
const flush = () => new Promise(resolve => setImmediate(resolve))
const selected = { type: 'user/message', data: { source: { kind: 'cannbot-dsh-workflow', name: 'ops-registry-invoke' } } }
const call = description => ({ type: 'tool/call', data: { name: 'bash', callId: description, arguments: JSON.stringify({ description, command: 'private command' }) } })
function fixture(history = []) {
  const listeners = new Map()
  const ctx = { on(name, fn) { if (!listeners.has(name)) listeners.set(name, new Set()); listeners.get(name).add(fn); return () => listeners.get(name).delete(fn) },
    sessionQuery: { readSession: async () => ({ events: history.map((event, seq) => ({ ...event, seq })) }) },
    sessionProjections: { stateOf: session => session.todos } }
  const session = { id: 'S', todos: null, writes: 0, append(type, data) {
    if (type === 'todo/write') { this.todos = data.todos; this.writes++ }
    if (type === 'turn/start') this.todos = null
    for (const fn of listeners.get('session/event') ?? []) fn(this, { type, data })
  } }
  const pm = new PmProgress(ctx), workflow = new WorkflowTodos(ctx)
  return { session, pm, workflow, send: event => session.append(event.type, event.data), close() { pm.dispose(); workflow.dispose() } }
}
test('restores real PM activity without inventing task completion and updates subsequent actions', async () => {
  const f = fixture([selected, call('检查远端环境')])
  try {
    await f.pm.restore(f.session); await flush()
    assert.match(f.session.todos[0].content, /检查远端环境/)
    f.send({ type: 'tool/result', data: { message: { toolCallId: '检查远端环境' } } }); await flush()
    assert.equal(f.session.todos[0].status, 'in_progress')
    f.send(call('验证测试框架')); await flush()
    assert.match(f.session.todos[0].content, /验证测试框架/)
    assert(!JSON.stringify(f.session.todos).includes('private command'))
    f.send({ type: 'turn/end', data: {} }); await flush()
    assert.equal(f.session.todos[0].status, 'pending')
  } finally { f.close() }
})
test('PM plan replaces fallback, survives turns, and coexists with workflow rows without feedback loops', async () => {
  const f = fixture()
  try {
    f.send(selected); await flush()
    const plan = [{ content: '确认需求', status: 'completed' }, { content: '准备环境', status: 'in_progress' }]
    f.session.append('todo/write', { todos: plan }); await flush()
    assert.deepEqual(f.session.todos, plan)
    f.workflow.update({ id: f.session.id, session: f.session }, { cwd: '/project', workflow: 'flow' }, { tasks: { build: { status: 'running' } } })
    await flush(); assert.equal(f.session.todos.length, 3)
    f.session.append('turn/start', {}); await flush()
    assert.equal(f.session.todos.length, 3)
    assert.deepEqual(f.session.todos.slice(0, 2), plan)
    const writes = f.session.writes; await flush(); assert.equal(f.session.writes, writes)
    f.session.append('todo/write', { todos: [{ content: '准备环境', status: 'completed' }] }); await flush()
    assert.equal(f.session.todos.length, 2)
    assert.equal(f.session.todos[0].status, 'completed')
  } finally { f.close() }
})
test('ordinary sessions and inherited workflow context do not get synthetic activity', async () => {
  const f = fixture([selected, call('old')])
  try {
    f.session.inheritedEventCount = 2
    await f.pm.restore(f.session); f.send(call('ordinary')); await flush()
    assert.equal(f.session.todos, null)
  } finally { f.close() }
})
