// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { useEffect, useRef, useState } from 'react'
import { Terminal } from '@xterm/xterm'
import '@xterm/xterm/css/xterm.css'
import type { InitializationOperation, InitializationSnapshot } from '../initialization-contract.ts'
import { CANNBOT_WORKSPACES_PATH } from '../workspace-mode-types.ts'

export function InitializationDialog({ operation, serverId = '', complete, close }: {
  operation: InitializationOperation; serverId?: string; complete(result: unknown): void; close(): void
}) {
  const dialog = useRef<HTMLDialogElement>(null), element = useRef<HTMLDivElement>(null)
  const [snapshot, setSnapshot] = useState<InitializationSnapshot>(), [error, setError] = useState(''), [cancelling, setCancelling] = useState(false)
  const job = useRef(''), initial = useRef(operation), startId = useRef(crypto.randomUUID()), term = useRef<Terminal>(), sendCancel = useRef<() => Promise<void>>()
  const retry = useRef<() => void>()
  useEffect(() => {
    dialog.current?.showModal()
    const terminal = new Terminal({ cols: 86, rows: 20, fontSize: 13, fontFamily: 'Consolas, monospace', scrollback: 1500, disableStdin: true, cursorBlink: true, theme: { background: '#181818', foreground: '#e5e5e5' } })
    term.current = terminal; terminal.open(element.current!)
    let disposed = false, timer: ReturnType<typeof setTimeout>, offset = 0, sequence = 0, accepting = false, inputQueue = Promise.resolve(), done = false
    const url = new URL(serverId ? 'api/cannbot-remote/tree?id=' + encodeURIComponent(serverId) : CANNBOT_WORKSPACES_PATH, document.baseURI)
    const request = async (body: object) => {
      const response = await fetch(url, { method: 'POST', credentials: 'same-origin', cache: 'no-store', signal: AbortSignal.timeout(15000), headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) })
      const value = await response.json()
      if (!response.ok) throw new Error(value.message || '初始化连接暂不可用，请重试读取进度。')
      return value as InitializationSnapshot
    }
    const update = (value: InitializationSnapshot) => {
      if (disposed) return
      job.current = value.jobId; setSnapshot(value); sequence = Math.max(sequence, value.inputSequence)
      if (value.offset > offset) { terminal.reset(); terminal.writeln('[较早的输出已省略]') }
      if (value.nextOffset > offset) terminal.write(value.output.slice(Math.max(0, offset - value.offset)))
      offset = Math.max(offset, value.nextOffset); accepting = value.interactive && value.phase === 'running'; terminal.options.disableStdin = !accepting
      if (value.phase === 'ready') { done = true; complete(value.result) }
      if (value.phase === 'error') { done = true; setError(value.message || '初始化失败，请关闭后重试。') }
    }
    const poll = async () => {
      try {
        const value = await request(job.current ? { action: 'initialization-status', jobId: job.current, offset } : { action: 'start-initialization', requestId: startId.current, operation: initial.current })
        if (disposed) return
        setError(''); update(value)
      } catch (reason) { if (!disposed) setError(String((reason as Error).message)) }
      if (!disposed && !done) timer = setTimeout(poll, 400)
    }
    retry.current = () => { clearTimeout(timer); void poll() }
    sendCancel.current = async () => {
      if (!job.current) return
      setCancelling(true); accepting = false; terminal.options.disableStdin = true
      try { update(await request({ action: 'cancel-initialization', jobId: job.current, offset })) }
      catch (reason) { setCancelling(false); if (!disposed) setError(String((reason as Error).message)) }
    }
    const input = terminal.onData(data => {
      if (!accepting) return
      inputQueue = inputQueue.then(async () => {
        const next = sequence + 1
        // Retry the same sequence once; the Host deduplicates delivered input.
        const body = { action: 'initialization-input', jobId: job.current, sequence: next, data }
        try { await request(body) } catch { await request(body) }
        sequence = Math.max(sequence, next)
      }).catch(reason => { if (!disposed) { accepting = false; terminal.options.disableStdin = true; setError('终端输入未确认，请检查连接后重新输入：' + String(reason.message)) } })
    })
    void poll()
    return () => { disposed = true; clearTimeout(timer); input.dispose(); terminal.dispose(); term.current = undefined }
  }, [])
  const finished = snapshot?.phase === 'error'
  return <dialog ref={dialog} className="cwb-directory cb-initialization" aria-label="工作流初始化" onCancel={event => { event.preventDefault(); if (finished) close(); else void sendCancel.current?.() }}>
    <header><h2>工作流初始化</h2><button type="button" className="cwb-text-button" disabled={!finished && (!snapshot || cancelling)} onClick={() => finished ? close() : void sendCancel.current?.()}>{finished ? '关闭' : cancelling ? '正在取消…' : '取消初始化'}</button></header>
    <p>{snapshot?.interactive ? '请点击终端，按提示回答问卷；支持方向键、空格和回车。' : '正在准备工作区，完成后才能开始对话。'}</p>
    <div ref={element} className="cb-initialization-terminal" aria-label="初始化交互终端" />
    {error && <p role="alert" className="cwb-error">{error}{!finished && <button type="button" className="cwb-text-button" onClick={() => retry.current?.()}>重新读取进度</button>}</p>}
  </dialog>
}
