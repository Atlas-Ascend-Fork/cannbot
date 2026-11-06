import { readFile, realpath } from 'node:fs/promises'
import { join } from 'node:path'
import { within } from './native-workflow.mjs'

/** Recover successful starts belonging to this goal, excluding fork-inherited work. */
export function goalWorkflowRuns(events, goalId, inherited = 0) {
  const calls = new Map(), runs = new Map()
  let currentGoal, turn, hadGoal = false
  for (const event of events) {
    if (event.seq < inherited) continue
    if (event.type === 'tool/call') turn = event.data.turn
    if (event.type === 'goal/change') {
      // PM may create its first goal after starting the workflow in the same turn.
      if (!hadGoal && event.data.operation === 'create') {
        for (const call of calls.values()) if (call.turn === turn) call.goal = event.data.goal?.id
      }
      currentGoal = event.data.goal?.id
      hadGoal = true
    }
    if (event.type === 'tool/call' && event.data.name === 'cannbot_workflow_run') {
      try { calls.set(event.data.callId, { args: JSON.parse(event.data.arguments), goal: currentGoal, turn }) } catch {}
    }
    if (event.type !== 'tool/result' || event.data.isError) continue
    const message = event.data.message, call = calls.get(message?.toolCallId)
    if (!call) continue
    for (const block of message.content ?? []) {
      try {
        const result = JSON.parse(block.text)
        if (result.runId && typeof result.workDir === 'string') {
          runs.set(result.workDir, { call, workDir: result.workDir })
        }
      } catch {}
    }
  }
  return [...runs.values()].filter(run => run.call.goal === goalId).map(({ call, workDir }) => ({ workflow: call.args.workflow, yaml: call.args.yaml, workDir }))
}

export function installGoalWorkflowResume(ctx, execution, start) {
  const pending = new Map()
  const stopping = new Map()
  ctx.on('goal/changed', ({ agent, change }) => {
    if (change.operation === 'resume') pending.set(agent, change.ref)
    else pending.delete(agent)
    if (change.operation === 'pause') {
      const previous = stopping.get(agent)
      const job = (async () => {
        await previous
        const history = await ctx.sessionQuery.readSession(agent.id)
        const directories = new Set(goalWorkflowRuns(history.events, change.ref.id, agent.session.inheritedEventCount).map(run => run.workDir))
        await Promise.all([...execution.runs.values()]
          .filter(run => run.owner === agent.id && run.code === null && (run.goalId === change.ref.id || directories.has(run.cwd)))
          .map(run => { run.paused = true; return execution.stop(run) }))
      })()
      stopping.set(agent, job)
      // Event dispatch is synchronous; retain the promise so resume waits for shutdown.
      void job.catch(error => ctx.logger?.warn(`Cannot pause workflow: ${error}`))
      return job
    }
  })
  ctx.on('agent/disposed', ({ agent }) => { pending.delete(agent); stopping.delete(agent) })
  ctx.on('dispose', () => { pending.clear(); stopping.clear() })
  ctx.on('agent/pre-step', async ({ agent, signal }, next) => {
    const decision = await next()
    const ref = pending.get(agent)
    if (decision.kind !== 'enter' || !ref) return decision
    const valid = () => {
      const goal = ctx.goals.get(agent)
      return pending.get(agent) === ref && goal?.id === ref.id && goal.revision === ref.revision && goal.phase === 'active'
    }
    if (!valid()) return decision
    const notices = []
    try {
      await stopping.get(agent)
      signal.throwIfAborted()
      if (!valid()) return decision
      const history = await ctx.sessionQuery.readSession(agent.id)
      const runs = goalWorkflowRuns(history.events, ref.id, agent.session.inheritedEventCount)
      const workspace = await realpath(await ctx.workingDirectory.ensure(agent, signal))
      for (const args of runs) {
        signal.throwIfAborted()
        if (!valid()) break
        const cwd = await realpath(args.workDir)
        if (!within(workspace, cwd)) throw new Error('Workflow directory escapes the session workspace')
        const live = [...execution.runs.values()].find(run => run.cwd === cwd && run.code === null)
        if (live) {
          if (live.owner !== agent.id) throw new Error('Workflow directory is running in another session')
          notices.push({ workflow: args.workflow, runId: live.id, status: 'running', reused: true })
          continue
        }
        const path = await realpath(join(cwd, '.workflow/status.json'))
        if (!within(workspace, path)) throw new Error('Workflow state escapes the session workspace')
        const state = JSON.parse(await readFile(path, 'utf8'))
        const tasks = Object.values(state.tasks ?? {})
        if (!tasks.length || tasks.every(task => ['pass', 'skipped'].includes(task.status))) continue
        signal.throwIfAborted()
        if (!valid()) break
        // No prompt: Python resumes the existing state and saved user request.
        const result = await start(args, agent, signal)
        const run = execution.runs.get(result.runId)
        if (run) run.goalId = ref.id
        // A pause may arrive while package preparation/start is awaiting IO.
        if (!valid()) {
          if (run && run.code === null) { run.paused = true; await execution.stop(run) }
          break
        }
        notices.push({ workflow: args.workflow, ...result })
      }
    } catch (error) {
      if (signal.aborted) throw error
      notices.push({ error: String(error), instruction: 'Workflow recovery failed. Diagnose this error; do not assume a stale running state means the scheduler is alive.' })
    }
    if (pending.get(agent) === ref) pending.delete(agent)
    if (!notices.length) return decision
    // Deliver the new run IDs in this very step, before PM decides what to do next.
    return { ...decision, messages: decision.messages.map((message, index) => index === 0 ? {
      ...message, content: [...message.content, { type: 'text', text:
        `CANNBot workflow recovery after goal resume: ${JSON.stringify(notices)}\nUse cannbot_workflow_status with the reported runId to track scheduling; do not replace it with shell sleep/poll loops.` }],
    } : message) }
  })
}
