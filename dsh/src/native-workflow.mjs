/** Python owns scheduling and verdicts; each dispatched node runs in DSH's native child loop. */
import { spawn } from 'node:child_process'
import { pythonBootstrap } from './native-workflow-bootstrap.mjs'
import { randomUUID } from 'node:crypto'
import { pathToFileURL } from 'node:url'
import { access, mkdir, readFile, realpath, open } from 'node:fs/promises'
import { createInterface } from 'node:readline'
import { isAbsolute, join, relative, resolve } from 'node:path'
import { WorkflowTodos, readTaskNames, readCompletionOrder } from './workflow-todos.mjs'

export function within(root, path) {
  const diff = relative(root, path)
  return diff !== '..' && !diff.startsWith('../') && !diff.startsWith('..\\') && !isAbsolute(diff)
}

/** A workflow may prepare its runner and node contexts without owning the host loop. */
export async function prepareWorkflow(resources, options) {
  const definition = await readFile(join(resources, 'plugin-install.json'), 'utf8').then(JSON.parse).catch(error => {
    if (error.code === 'ENOENT') return {}
    throw error
  })
  if (definition.nativeWorkflow) {
    const root = await realpath(resources), path = definition.nativeWorkflow
    if (typeof path !== 'string' || isAbsolute(path)) throw new Error('Invalid native workflow adapter')
    const entry = await realpath(resolve(root, path))
    if (!within(root, entry)) throw new Error('Native workflow adapter escapes its package')
    const adapter = await import(pathToFileURL(entry).href)
    const prepared = await adapter.prepareRun({ ...options, resources: root })
    const runner = await realpath(prepared.runner)
    if (!within(root, runner) && !within(await realpath(options.cwd), runner)) throw new Error('Workflow runner escapes its resources')
    if (typeof prepared.prepareNode !== 'function') throw new Error('Invalid workflow node adapter')
    return { runner, prepareNode: prepared.prepareNode }
  }
  const runner = join(resources, 'skills/workflow-orchestrator/scripts/orchestrator.py')
  await access(runner)
  return { runner }
}

export class NativeWorkflow {
  constructor(ctx) { this.ctx = ctx; this.todos = new WorkflowTodos(ctx); this.runs = new Map(); this.closed = false }

  async start(parent, { runner, yaml, cwd, resources, prompt, workflow = '', goalId, prepareNode }) {
    if (this.closed) throw new Error('DSH workflow runner is stopping')
    await mkdir(cwd, { recursive: true })
    cwd = await realpath(cwd)
    // Reserve before the first further await so two calls cannot launch two schedulers.
    for (const run of this.runs.values()) {
      if (run.cwd === cwd && run.code === null) throw new Error('A workflow is already running in this directory')
    }
    const id = randomUUID(), controller = new AbortController()
    const run = { id, owner: parent.id, goalId, workflow, cwd, code: null, error: '', controller, process: null, done: null, log: '', finalState: undefined }
    this.runs.set(id, run)
    let file
    try {
      run.taskNames = await readTaskNames(yaml)
      run.completionOrder = await readCompletionOrder(cwd)
      await mkdir(join(cwd, '.workflow'), { recursive: true })
      file = await open(join(cwd, '.workflow/dsh-runner.log'), 'a')
      controller.signal.throwIfAborted()
      if (this.closed) throw new Error('DSH workflow runner is stopping')
      const argv = ['-c', pythonBootstrap, runner, '--yaml', yaml, '--work-dir', cwd]
      if (prompt) argv.push('--prompt', prompt)
      const child = spawn('python3', argv, { cwd, stdio: ['pipe', 'pipe', 'pipe'] })
      run.process = child
      const pending = new Set()
      const lines = createInterface({ input: child.stdout })
      let logging = Promise.resolve()
      const log = text => {
        run.log = (run.log + String(text)).slice(-8192)
        logging = logging.then(() => file.appendFile(text)).catch(error => { run.error = String(error) })
      }
      child.stderr.on('data', log)
      child.stdin.on('error', error => { if (!controller.signal.aborted) run.error = String(error) })
      child.on('error', error => { run.error = String(error) })
      lines.on('line', line => {
        let request
        try {
          request = JSON.parse(line)
          if (typeof request.id !== 'string' || typeof request.prompt !== 'string'
            || typeof request.taskId !== 'string' || !['execute', 'verify', 'advice'].includes(request.phase)
            || resolve(request.workDir) !== cwd) throw new Error('Invalid Python dispatch')
        } catch (error) {
          run.error = String(error); controller.abort(); child.kill(); return
        }
        // Python's max_parallel controls admission. Independent nodes stay concurrent.
        const job = this.executeNode(parent, request, resources, controller.signal, prepareNode)
          .catch(error => ({ ok: false, error: String(error) }))
          .then(result => {
            if (!child.stdin.destroyed && !controller.signal.aborted) child.stdin.write(JSON.stringify({ id: request.id, ...result }) + '\n')
          })
        pending.add(job)
        void job.finally(() => pending.delete(job))
      })
      run.done = new Promise(accept => child.on('close', async (code, signal) => {
        run.todoStopped = true
        clearTimeout(run.todoTimer)
        await run.todoPoll
        controller.abort(); lines.close()
        await Promise.allSettled([...pending])
        await logging
        await file.close().catch(error => { run.error = String(error) })
        try { run.finalState = JSON.parse(await readFile(join(cwd, '.workflow/status.json'), 'utf8')) } catch {}
        run.code = code ?? 2
        if (signal) run.error ||= `Scheduler terminated by ${signal}`
        this.todos.update(parent, run, run.finalState, run.paused ? 'paused' : true)
        accept()
      }))
      this.trackTodos(parent, run)
      return { runId: id, workDir: cwd, status: 'running' }
    } catch (error) {
      this.runs.delete(id)
      await file?.close()
      throw error
    }
  }

  trackTodos(parent, run) {
    if (!parent.session || !this.ctx.sessionProjections?.stateOf) return
    const poll = () => {
      run.todoPoll = (async () => {
        try {
          const state = JSON.parse(await readFile(join(run.cwd, '.workflow/status.json'), 'utf8'))
          if (!run.todoStopped) this.todos.update(parent, run, state)
        } catch { /* Initialization may not have written status.json yet. */ }
        if (!run.todoStopped) run.todoTimer = setTimeout(poll, 1000)
      })()
    }
    poll()
  }

  async executeNode(parent, request, resources, signal, prepareNode) {
    if (typeof request.role !== 'string' || !/^[\w-]+$/.test(request.role)) throw new Error('Invalid workflow role')
    let cwd = request.workDir, prompt
    if (prepareNode) {
      const prepared = await prepareNode(request, signal)
      cwd = await realpath(prepared.cwd)
      if (!within(await realpath(request.workDir), cwd) || typeof prepared.prompt !== 'string') throw new Error('Invalid prepared workflow node')
      prompt = prepared.prompt
    } else {
      const role = await readFile(join(resources, 'agents', request.role + '.md'), 'utf8')
      prompt = `Execute one Python-scheduled workflow node using the DSH agent loop.\n`
        + `Workflow resources: ${resources}\nSkills: ${join(resources, 'skills')}\n`
        + `Role instructions (frontmatter is metadata):\n${role}\n\n`
        + `Follow the task's verdict callback instructions. Python owns dependencies, retries, approvals and status updates.\n`
        + request.prompt
    }
    signal.throwIfAborted()
    const activation = await this.ctx.subagents.startActivation({
      provider: 'spawn', delivery: 'caller', signal,
      label: `CANNBot ${request.taskId} · ${request.phase}`,
      request: { parent, cwd, prompt: [{ type: 'text', text: prompt }] },
    })
    const cancel = () => { void activation.dispose().catch(() => {}) }
    signal.addEventListener('abort', cancel, { once: true })
    if (signal.aborted) cancel()
    try {
      const result = await activation.result
      return { ok: !signal.aborted && result.stopReason === 'completed', childSessionId: activation.childId,
        stopReason: result.stopReason, output: result.output, diagnostic: result.diagnostic }
    } finally {
      signal.removeEventListener('abort', cancel)
      await activation.dispose()
    }
  }

  owned(parent, id) {
    const run = this.runs.get(id)
    if (!run || run.owner !== parent.id) throw new Error('Workflow run is unavailable in this session')
    return run
  }

  async status(parent, id, waitMs = 0) {
    const run = this.owned(parent, id)
    if (!Number.isInteger(waitMs) || waitMs < 0 || waitMs > 30000) throw new Error('waitMs must be between 0 and 30000')
    let timer
    if (run.done && run.code === null && waitMs) {
      try { await Promise.race([run.done, new Promise(accept => { timer = setTimeout(accept, waitMs) })]) }
      finally { clearTimeout(timer) }
    }
    let state = run.finalState
    if (run.code === null) {
      try { state = JSON.parse(await readFile(join(run.cwd, '.workflow/status.json'), 'utf8')) }
      catch (error) { if (error.code !== 'ENOENT') throw error }
    }
    if (state) this.todos.update(parent, run, state, run.code !== null && (run.paused ? 'paused' : true))
    return { runId: id, workDir: run.cwd, status: run.code === null ? 'running' : run.paused ? 'paused' : run.code === 0 ? 'completed' : 'failed',
      exitCode: run.code, error: run.error || undefined, state, log: run.log }
  }

  async stop(run) {
    run.controller.abort()
    run.process?.stdin.end()
    run.process?.kill('SIGTERM')
    const timer = setTimeout(() => run.process?.kill('SIGKILL'), 3000)
    try { await run.done } finally { clearTimeout(timer) }
  }

  async cancel(parent, id) {
    const run = this.owned(parent, id)
    if (run.code === null) await this.stop(run)
    return this.status(parent, id)
  }

  async dispose() {
    this.closed = true
    await Promise.all([...this.runs.values()].filter(run => run.code === null).map(run => this.stop(run)))
    this.todos.dispose()
  }
}
