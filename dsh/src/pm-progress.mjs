const PREFIX = '[PM 当前操作] '
const isWorkflow = item => item.content.startsWith('[工作流] ')
const isProgress = item => item.content.startsWith(PREFIX)

/** Keep native PM plans across turns; show factual activity until PM supplies a plan. */
export class PmProgress {
  constructor(ctx) {
    this.ctx = ctx
    this.entries = new Map()
    this.closed = false
    this.releases = [
      ctx.on('session/created', session => { void this.restore(session) }),
      ctx.on('session/event', (session, event) => this.event(session, event)),
    ]
    for (const session of ctx.sessions?.list() ?? []) void this.restore(session)
  }

  event(session, event, replay = false) {
    if (this.closed) return
    if (!['user/message', 'tool/call', 'tool/result', 'todo/write', 'turn/start', 'turn/end'].includes(event.type)) return
    let entry = this.entries.get(session.id)
    if (event.type === 'user/message' && event.data.source?.kind === 'cannbot-dsh-workflow') {
      if (!entry) {
        entry = { session, plan: [], activity: '准备工作流', status: 'in_progress', queued: false }
        this.entries.set(session.id, entry)
      }
    }
    if (!entry) return
    if (event.type === 'tool/call' && event.data.name !== 'todo_write') {
      try {
        const args = JSON.parse(event.data.arguments)
        // Descriptions are model-authored labels; do not expose command text or file contents.
        if (typeof args.description === 'string' && args.description.trim()) {
          entry.activity = args.description.trim().slice(0,240)
          entry.status = 'in_progress'
          entry.callId = event.data.callId
        }
      } catch {}
    }
    if (event.type === 'tool/result' && event.data.message?.toolCallId === entry.callId && event.data.isError) {
      entry.status = 'pending'
      entry.activity = `操作失败，待处理：${entry.activity}`
    }
    if (event.type === 'todo/write') {
      const rows = event.data.todos ?? []
      // Our own activity row is never mistaken for a PM-authored plan.
      const plan = rows.filter(item => !isWorkflow(item) && !isProgress(item))
      if (!rows.some(isProgress) && (plan.length || !rows.length)) entry.plan = plan
    }
    if (event.type === 'turn/end') entry.status = 'pending'
    if (event.type === 'turn/start') entry.status = 'in_progress'
    if (!replay) this.queue(entry)
  }

  queue(entry) {
    if (entry.queued || this.closed) return
    entry.queued = true
    queueMicrotask(() => {
      entry.queued = false
      if (this.closed || this.entries.get(entry.session.id) !== entry) return
      const current = this.ctx.sessionProjections.stateOf(entry.session, 'todos')
      if (current === undefined) return
      const workflow = (current ?? []).filter(isWorkflow)
      const rows = [...entry.plan, ...workflow]
      if (!rows.length) rows.push({ content: PREFIX + entry.activity, status: entry.status })
      if (JSON.stringify(current) !== JSON.stringify(rows)) entry.session.append('todo/write', { todos: rows })
    })
  }

  async restore(session) {
    try {
      const history = await this.ctx.sessionQuery.readSession(session.id)
      if (this.closed || this.entries.has(session.id)) return
      for (const event of history.events) {
        if (event.seq >= (session.inheritedEventCount ?? 0)) this.event(session, event, true)
      }
      const entry = this.entries.get(session.id)
      if (entry) this.queue(entry)
    } catch (error) { this.ctx.logger?.warn(`Cannot restore PM progress: ${error}`) }
  }

  dispose() { this.closed = true; for (const release of this.releases) release?.(); this.entries.clear() }
}
