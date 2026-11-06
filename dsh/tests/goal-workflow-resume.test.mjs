import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtemp, mkdir, writeFile, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { goalWorkflowRuns, installGoalWorkflowResume } from '../src/goal-workflow-resume.mjs'

function history(cwd, beforeGoal = false) {
  const goal = { type: 'goal/change', data: { operation: 'create', goal: { id: 'goal' } } }
  const call = { type: 'tool/call', data: { turn: 1, callId: 'call', name: 'cannbot_workflow_run', arguments: JSON.stringify({ workflow: 'flow', yaml: join(cwd, 'flow.yaml'), prompt: 'old request' }) } }
  const result = { type: 'tool/result', data: { message: { toolCallId: 'call', content: [{ text: JSON.stringify({ runId: 'old-run', workDir: cwd }) }] } } }
  return (beforeGoal ? [call, result, goal] : [goal, call, result]).map((event, seq) => ({ ...event, seq }))
}
async function fixture(t) {
  const cwd = await mkdtemp(join(tmpdir(), 'goal-workflow-'))
  t.after(() => rm(cwd, { recursive: true, force: true }))
  await mkdir(join(cwd, '.workflow'))
  const state = status => writeFile(join(cwd, '.workflow/status.json'), JSON.stringify({ tasks: { '0': { status } } }))
  await state('running')
  const events = history(cwd, true), handlers = new Map(), starts = []
  const agent = { id: 'session', session: { inheritedEventCount: 0 } }
  const goal = { id: 'goal', revision: 2, phase: 'active' }, execution = { runs: new Map() }
  const ctx = { on: (name, fn) => handlers.set(name, fn), goals: { get: () => goal }, sessionQuery: { readSession: async () => ({ events }) }, workingDirectory: { ensure: async () => cwd } }
  installGoalWorkflowResume(ctx, execution, async (args, parent, signal) => {
    signal.throwIfAborted(); starts.push(args)
    execution.runs.set('new', { id: 'new', owner: parent.id, cwd, code: null })
    return { runId: 'new', status: 'running' }
  })
  const change = operation => handlers.get('goal/changed')({ agent, change: { operation, ref: { id: 'goal', revision: goal.revision } } })
  const step = (kind = 'enter', signal = new AbortController().signal) => handlers.get('agent/pre-step')({ agent, signal }, async () => ({ kind, messages: [{ role: 'user', content: [{ type: 'text', text: 'Continue goal' }] }] }))
  return { cwd, state, events, ctx, starts, goal, execution, change, step }
}

test('associates starts before first goal in same turn, excludes other goals and inherited history', () => {
  assert.equal(goalWorkflowRuns(history('/work', true), 'goal').length, 1)
  assert.equal(goalWorkflowRuns(history('/work'), 'other').length, 0)
  assert.equal(goalWorkflowRuns(history('/work'), 'goal', 3).length, 0)
  const rows = history('/work', true)
  rows.splice(2, 0, { seq: 2, type: 'tool/call', data: { turn: 2, name: 'create_goal' } })
  assert.equal(goalWorkflowRuns(rows, 'goal').length, 0)
  const failed = history('/work'); failed[2].data.isError = true
  assert.equal(goalWorkflowRuns(failed, 'goal').length, 0)
})

test('resume starts interrupted workflow once, without replacing saved prompt, and reports runId to PM', async t => {
  const f = await fixture(t)
  await f.step(); assert.equal(f.starts.length, 0)
  f.change('resume')
  const decision = await f.step()
  assert.equal(f.starts.length, 1)
  assert.equal(f.starts[0].workDir, f.cwd)
  assert.equal(f.starts[0].prompt, undefined)
  assert.match(JSON.stringify(decision.messages), /new.*running/)
  await f.step(); assert.equal(f.starts.length, 1)
  f.goal.revision++; f.change('resume')
  assert.match(JSON.stringify((await f.step()).messages), /reused/)
  assert.equal(f.starts.length, 1)
})

test('completed work and other goal work are not restarted', async t => {
  const f = await fixture(t)
  await f.state('pass'); f.change('resume'); await f.step()
  assert.equal(f.starts.length, 0)
  await f.state('running'); f.events[2].data.goal.id = 'other'
  f.change('resume'); await f.step(); assert.equal(f.starts.length, 0)
})

test('pause, stale revision, aborted and rejected steps cannot launch recovery', async t => {
  const f = await fixture(t)
  f.change('resume'); f.change('pause'); await f.step()
  f.change('resume'); f.goal.revision++; await f.step()
  f.change('resume'); await f.step('reject')
  const controller = new AbortController(); controller.abort()
  await assert.rejects(f.step('enter', controller.signal))
  assert.equal(f.starts.length, 0)
})

test('recovery errors are visible to PM instead of stale polling', async t => {
  const f = await fixture(t)
  await rm(join(f.cwd, '.workflow/status.json'))
  f.change('resume')
  assert.match(JSON.stringify((await f.step()).messages), /Workflow recovery failed/)
  assert.equal(f.starts.length, 0)
})

test('pause stops only associated owned runs and immediate resume waits for shutdown', async t => {
  const f = await fixture(t)
  f.change('resume'); await f.step()
  f.execution.runs.set('foreign', { id: 'foreign', owner: 'other', cwd: f.cwd, code: null })
  const stopped = []
  let finish
  f.execution.stop = async run => { stopped.push(run); await new Promise(resolve => { finish = resolve }); run.code = 2 }
  const pausing = f.change('pause')
  while (!finish) await new Promise(resolve => setImmediate(resolve))
  assert.deepEqual(stopped.map(run => run.id), ['new'])
  assert.equal(stopped[0].paused, true)
  f.execution.runs.delete('foreign')
  f.goal.revision++; f.change('resume')
  const resuming = f.step()
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(f.starts.length, 1)
  finish(); await pausing; await resuming
  assert.equal(f.starts.length, 2)
})
