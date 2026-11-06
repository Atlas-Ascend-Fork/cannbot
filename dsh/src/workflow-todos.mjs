import { readFile, realpath } from 'node:fs/promises'
import { isAbsolute, join, relative } from 'node:path'
import { parse } from 'yaml'

const PREFIX = '[工作流] '
const active = new Set(['running', 'executed', 'verifying', 'awaiting_approval'])
const labels = { pending: '待执行', running: '执行中', executed: '待验证', verifying: '验证中', awaiting_approval: '待审批', pass: '已完成', fail: '失败', skipped: '已跳过' }

// Read literal launch arguments only; never evaluate shell syntax or scan unrelated workspaces.
export function externalWorkflowLaunch(event) {
  if (event.type !== 'tool/call' || event.data.name !== 'bash') return
  try {
    const { command } = JSON.parse(event.data.arguments)
    if (!/(?:run_workflow|orchestrator)\.py(?:\s|["'])/.test(command)) return
    const argument = name => {
      const match = command.match(new RegExp(`--${name}\\s+(?:"([^"$\\\\]+)"|'([^']+)'|([^\\s;|&<>"'$\\\\]+))`))
      const value = match?.[1] ?? match?.[2] ?? match?.[3]
      return value && isAbsolute(value) ? value : undefined
    }
    const cwd = argument('work-dir'), yaml = argument('yaml')
    if (cwd && yaml) return { cwd, yaml, external: true }
  } catch {}
}

/** The native TodoItem has three states. Preserve richer scheduler states in its text. */
export async function readTaskNames(yaml) {
  const names = new Map()
  try {
    const config = parse(await readFile(yaml, 'utf8'))
    for (const node of config?.nodes ?? []) {
      if (node?.id != null && typeof node.title === 'string' && node.title.trim()) names.set(String(node.id), node.title.trim())
    }
  } catch { /* Missing display metadata must not prevent workflow execution. */ }
  return names
}

export async function readCompletionOrder(cwd) {
  const order = []
  try {
    for (const line of (await readFile(join(cwd, '.workflow/log.jsonl'), 'utf8')).split('\n')) {
      try {
        const event = JSON.parse(line)
        if (event.task_id != null && (['pass', 'skipped'].includes(event.to) || event.verdict === 'pass')) {
          const id = String(event.task_id), index = order.indexOf(id)
          if (index >= 0) order.splice(index, 1)
          order.push(id)
        }
      } catch {}
    }
  } catch {}
  return order
}

export function workflowTodos(workflow, state, finished = false, taskNames = new Map(), completionOrder = []) {
  const entries = Object.entries(state?.tasks ?? {})
  const completed = entries.filter(([, task]) => ['pass', 'skipped'].includes(task?.status))
    .sort(([a], [b]) => completionOrder.indexOf(a) - completionOrder.indexOf(b))
  return [...entries.filter(([, task]) => !['pass', 'skipped'].includes(task?.status)), ...completed].flatMap(([id, task]) => {
    if (!task || typeof task !== 'object') return []
    const interrupted = finished && active.has(task.status)
    const detail = interrupted ? (finished === 'paused' ? '已暂停' : '已中断') : labels[task.status] ?? '未知状态'
    const retry = Number.isSafeInteger(task.retries) && task.retries > 0 ? `，重试 ${task.retries}` : ''
    return [{ content: `${PREFIX}${workflow || '当前工作流'} / ${taskNames.get(id) ?? id} · ${detail}${retry}`,
      status: ['pass', 'skipped'].includes(task.status) ? 'completed' : !finished && active.has(task.status) ? 'in_progress' : 'pending' }]
  })
}

/** Publish through DSH's existing durable todo projection, preserving non-workflow todos. */
export class WorkflowTodos {
  constructor(ctx) {
    this.ctx = ctx
    this.sessions = new Map()
    this.closed = false
    this.restoring = new Set()
    this.externalSessions = new Map()
    this.externalRuns = new Map()
    this.observer = setInterval(() => { for (const session of this.externalSessions.values()) void this.restore(session, true) }, 1000)
    this.observer.unref?.()
    this.releaseCreated = ctx.on?.('session/created', session => { void this.restore(session) })
    for (const session of ctx.sessions?.list() ?? []) void this.restore(session)
    this.release = ctx.on?.('session/event', (session, event) => {
      if (externalWorkflowLaunch(event)) { this.externalSessions.set(session.id, session); void this.restore(session) }
      const entry = this.sessions.get(session.id)
      if (!entry || !['todo/write', 'turn/start'].includes(event.type)) return
      // Workflow completion history remains available across chat turns.
      // Defer until DSH has folded this event; never append inside its fold.
      if (entry.queued) return
      entry.queued = true
      queueMicrotask(() => { entry.queued = false; this.sync(entry) })
    })
  }

  // Recover only successful starts owned by this session, never other workspace runs.
  async restore(session, refresh = false) {
    if (this.closed || !this.ctx.sessionQuery || !session.header?.cwd || this.restoring.has(session.id)) return
    this.restoring.add(session.id)
    try {
      const history = refresh ? { events: [] } : await this.ctx.sessionQuery.readSession(session.id)
      const calls = new Map(), runs = refresh ? new Map(this.externalRuns.get(session.id) ?? []) : new Map()
      for (const event of history.events) {
        if (event.seq < (session.inheritedEventCount ?? 0)) continue
        const external = externalWorkflowLaunch(event)
        if (external) { runs.set(external.cwd, external); this.externalSessions.set(session.id, session) }
        if (event.type === 'tool/call' && event.data.name === 'cannbot_workflow_run') {
          try { calls.set(event.data.callId, JSON.parse(event.data.arguments)) } catch {}
        }
        if (event.type !== 'tool/result' || event.data.isError) continue
        const message = event.data.message, args = calls.get(message?.toolCallId)
        if (!args) continue
        for (const block of message.content ?? []) {
          try {
            const result = JSON.parse(block.text)
            if (result.runId && typeof result.workDir === 'string') {
              for (const [cwd, old] of runs) if (old.workflow === args.workflow) runs.delete(cwd)
              runs.set(result.workDir, { cwd: result.workDir, workflow: args.workflow })
            }
          } catch {}
        }
      }
      const latest = [...runs.values()].at(-1)
      if (latest?.external) {
        runs.clear(); runs.set(latest.cwd, latest)
        this.externalRuns.set(session.id, new Map(runs))
      } else {
        for (const [cwd, run] of runs) if (run.external) runs.delete(cwd)
        this.externalRuns.delete(session.id); this.externalSessions.delete(session.id)
      }
      const workspace = await realpath(session.header.cwd)
      for (const run of runs.values()) {
        try {
          const path = await realpath(join(run.cwd, '.workflow/status.json'))
          const diff = relative(workspace, path)
          if (diff === '..' || diff.startsWith('../') || isAbsolute(diff)) continue
          const state = JSON.parse(await readFile(path, 'utf8'))
          if (run.external) {
            // The persisted state must match the exact YAML launched in this conversation.
            const yaml = await realpath(run.yaml)
            if (!withinWorkspace(workspace, yaml) || await realpath(state.workflow) !== yaml) continue
            const config = parse(await readFile(yaml, 'utf8'))
            run.workflow = config.workflow || '外部工作流'
          }
          run.taskNames = await readTaskNames(state.workflow)
          run.completionOrder = await readCompletionOrder(run.cwd)
          // A live start/poll wins over a slower history read.
          const existing = this.sessions.get(session.id)?.runs.get(run.cwd)
          if (this.closed || (existing && !existing.external)) continue
          if (run.external) {
            const entry = this.sessions.get(session.id)
            for (const [cwd, old] of entry?.runs ?? []) {
              if (cwd !== run.cwd && old.workflow === run.workflow && (old.external || old.finished)) entry.runs.delete(cwd)
            }
          }
          this.update({ id: session.id, session }, run, state, !run.external)
        } catch {}
      }
    } catch (error) {
      this.ctx.logger?.warn(`Cannot restore workflow todos for ${session.id}: ${error.message}`)
    } finally { this.restoring.delete(session.id) }
  }

  update(parent, run, state, finished = false) {
    if (this.closed || !parent.session || !this.ctx.sessionProjections?.stateOf) return
    let entry = this.sessions.get(parent.id)
    if (!entry) { entry = { session: parent.session, runs: new Map(), queued: false }; this.sessions.set(parent.id, entry) }
    for (const [cwd, old] of entry.runs) {
      if (cwd !== run.cwd && old.workflow === run.workflow && old.finished) entry.runs.delete(cwd)
    }
    // Resuming a directory replaces that run's old rows instead of duplicating them.
    const previous = entry.runs.get(run.cwd)
    const completed = Object.keys(state?.tasks ?? {}).filter(id => ['pass', 'skipped'].includes(state.tasks[id]?.status))
    const completionOrder = (previous?.completionOrder ?? run.completionOrder ?? []).filter(id => completed.includes(id))
    for (const id of completed) if (!completionOrder.includes(id)) completionOrder.push(id)
    entry.runs.set(run.cwd, { workflow: run.workflow, cwd: run.cwd, external: run.external, taskNames: run.taskNames, completionOrder, state, finished })
    this.sync(entry)
  }

  sync(entry) {
    if (this.closed || this.sessions.get(entry.session.id) !== entry) return
    try {
      const current = this.ctx.sessionProjections.stateOf(entry.session, 'todos')
      if (current === undefined) return // The native todo provider is disabled.
      const existing = current ?? []
      const names = [...entry.runs.values()].map(run => run.workflow)
      const rows = [...entry.runs.values()].flatMap(run => workflowTodos(
        names.filter(name => name === run.workflow).length > 1 ? `${run.workflow} (${run.cwd})` : run.workflow,
        run.state, run.finished, run.taskNames, run.completionOrder,
      ))
      const todos = [...existing.filter(item => !item.content.startsWith(PREFIX)), ...rows]
      if (JSON.stringify(todos) !== JSON.stringify(existing)) entry.session.append('todo/write', { todos })
    } catch { /* A display failure must not interrupt scheduling; the next update retries. */ }
  }

  dispose() { this.closed = true; clearInterval(this.observer); this.externalSessions.clear(); this.externalRuns.clear(); this.release?.(); this.releaseCreated?.(); this.sessions.clear() }
}

function withinWorkspace(root, path) {
  const diff = relative(root, path)
  return diff !== '..' && !diff.startsWith('../') && !isAbsolute(diff)
}
