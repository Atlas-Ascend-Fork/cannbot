// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { AsyncLocalStorage } from 'node:async_hooks'
import { randomUUID } from 'node:crypto'
import type { Readable } from 'node:stream'
import type { InitializationRequest, InitializationSnapshot, InitializationOperation } from '../contracts/initialization-contract.ts'

export interface InitializationIO {
  signal: AbortSignal
  output(data: string): void
  input?: (data: string) => Promise<void>
}
export const initializationIO = new AsyncLocalStorage<InitializationIO>()
export interface InitializationTerminal {
  output: Readable; done: Promise<{ exitCode: number | null; signal?: string | null }>
  write(data: string): Promise<void>; terminate(): Promise<unknown>
}
export type TerminalSpawner = (spec: { argv: string[]; cwd: string; env: Record<string, string>; rows: number; cols: number; terminalType: string; graceMs: number; signal: AbortSignal }) => Promise<InitializationTerminal>

export async function runInitializationTerminal(spawn: TerminalSpawner, argv: string[], cwd: string, io: InitializationIO) {
  const terminal = await spawn({ argv, cwd, env: { TERM: 'xterm-256color', ...(process.versions.electron ? { ELECTRON_RUN_AS_NODE: '1' } : {}) }, rows: 20, cols: 86, terminalType: 'xterm-256color', graceMs: 1000, signal: io.signal })
  let terminating: Promise<unknown> | undefined
  const stop = () => { terminating ??= terminal.terminate(); void terminating.catch(() => {}) }
  const timer = setTimeout(stop, 20 * 60000)
  io.signal.addEventListener('abort', stop, { once: true })
  if (io.signal.aborted) stop()
  terminal.output.setEncoding('utf8')
  const output = (data: string) => io.output(data)
  terminal.output.on('data', output)
  io.input = data => terminal.write(data)
  try {
    const outcome = await terminal.done
    if (terminating) await terminating
    io.signal.throwIfAborted()
    if (terminating || outcome.exitCode !== 0) throw new Error(terminating ? '初始化超时。' : `初始化退出（${outcome.exitCode ?? outcome.signal}）。`)
  } finally {
    io.input = undefined; clearTimeout(timer); io.signal.removeEventListener('abort', stop)
    // The provider owns descendants as well as the shell. Wait before rollback.
    await terminal.terminate()
    terminal.output.off('data', output)
  }
}

interface Job {
  id: string; key: string; requestId: string; controller: AbortController; io: InitializationIO
  output: string; start: number; phase: InitializationSnapshot['phase']; result?: unknown; message?: string
  sequence: number; pending?: Promise<void>; touched: number
}
/** Authenticated Host routes only. IDs are unguessable, output bounded, input never persisted. */
export class InitializationJobs {
  private jobs = new Map<string, Job>()
  private run: (operation: InitializationOperation) => Promise<unknown>
  constructor(run: (operation: InitializationOperation) => Promise<unknown>) { this.run = run }
  async handle(request: InitializationRequest): Promise<InitializationSnapshot> {
    if (request.action === 'start-initialization') {
      for (const [id, item] of this.jobs) if (item.phase !== 'running' && Date.now() - item.touched > 30 * 60000) this.jobs.delete(id)
      const key = JSON.stringify(request.operation)
      const previous = [...this.jobs.values()].find(item => item.requestId === request.requestId)
      if (previous) {
        if (previous.key !== key) throw new Error('初始化请求内容已变化。')
        return this.snapshot(previous, 0)
      }
      if (this.jobs.size >= 100 || [...this.jobs.values()].filter(item => item.phase === 'running').length >= 4) throw new Error('初始化任务较多，请稍后重试。')
      const controller = new AbortController()
      const job: Job = { id: randomUUID(), key, requestId: request.requestId, controller, output: '', start: 0, phase: 'running', sequence: 0, touched: Date.now(),
        io: { signal: controller.signal, output: data => { job.output += data; if (job.output.length > 256000) { job.start += job.output.length - 256000; job.output = job.output.slice(-256000) } } } }
      this.jobs.set(job.id, job)
      void initializationIO.run(job.io, async () => {
        try { controller.signal.throwIfAborted(); job.result = await this.run(request.operation); job.phase = 'ready' }
        catch (error) { job.phase = 'error'; job.message = controller.signal.aborted && !(error as { recoveryFailed?: boolean }).recoveryFailed ? '已取消初始化，可以重试。' : String((error as Error).message).slice(-2000) }
        finally { job.touched = Date.now(); job.io.input = undefined }
      })
      return this.snapshot(job, 0)
    }
    const job = this.jobs.get(request.jobId)
    if (!job) throw new Error('初始化任务已过期或服务已重启，请关闭后重试。')
    job.touched = Date.now()
    if (request.action === 'cancel-initialization' && job.phase === 'running') job.controller.abort(new Error('初始化已取消。'))
    if (request.action === 'initialization-input') {
      if (job.pending) await job.pending
      if (request.sequence > job.sequence) {
        if (request.sequence !== job.sequence + 1 || job.phase !== 'running' || !job.io.input || job.controller.signal.aborted) throw new Error('终端尚未就绪，请稍后重试。')
        job.pending = job.io.input(request.data)
        try { await job.pending; job.sequence = request.sequence } finally { job.pending = undefined }
      }
    }
    return this.snapshot(job, 'offset' in request ? request.offset : job.start + job.output.length)
  }
  private snapshot(job: Job, offset: number): InitializationSnapshot {
    const start = Math.max(job.start, Math.min(offset, job.start + job.output.length))
    return { jobId: job.id, phase: job.phase, output: job.output.slice(start - job.start), offset: start, nextOffset: job.start + job.output.length,
      inputSequence: job.sequence, interactive: !!job.io.input, ...(job.message && { message: job.message }), ...(job.phase === 'ready' && { result: job.result }) }
  }
  dispose() { for (const job of this.jobs.values()) if (job.phase === 'running') job.controller.abort(new Error('Host stopped')) }
}
