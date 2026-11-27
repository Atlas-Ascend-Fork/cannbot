// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { spawn } from 'node:child_process'

/** Wait for termination before callers release locks or remove staging files. */
export function runProcess(command, args, { signal, timeoutMs, graceMs = 1000, onData, ...options } = {}) {
  signal?.throwIfAborted()
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { ...options, detached: process.platform !== 'win32', windowsHide: true })
    let stopped, escalation, timer, terminating
    const kill = force => {
      if (!child.pid) return
      if (process.platform === 'win32') {
        if (terminating || child.exitCode !== null || child.signalCode !== null) return terminating
        // Windows has no negative-PID process-group signals. Target only the
        // process started here and its descendants; taskkill /T waits for the tree.
        terminating = new Promise(resolve => {
          const killer = spawn('taskkill.exe', ['/PID', String(child.pid), '/T', '/F'], { stdio: 'ignore', windowsHide: true })
          const direct = () => { try { child.kill('SIGKILL') } catch {} }
          killer.once('error', () => { direct(); resolve() })
          killer.once('close', code => { if (code !== 0) direct(); resolve() })
        })
        return terminating
      }
      try { process.kill(-child.pid, force ? 'SIGKILL' : 'SIGTERM') } catch {}
    }
    const stop = reason => {
      if (stopped) return
      stopped = reason
      kill(false)
      escalation = setTimeout(() => kill(true), graceMs)
    }
    const abort = () => stop(signal.reason ?? new Error('Operation cancelled'))
    const cleanup = () => { clearTimeout(timer); clearTimeout(escalation); signal?.removeEventListener('abort', abort) }
    if (onData) { child.stdout?.on('data', onData); child.stderr?.on('data', onData) }
    signal?.addEventListener('abort', abort, { once: true })
    if (signal?.aborted) abort()
    if (timeoutMs !== undefined) timer = setTimeout(() => stop(new Error('Initialization timed out')), timeoutMs)
    child.on('error', error => { cleanup(); reject(error) })
    child.on('close', async (code, exitSignal) => {
      if (stopped) { if (process.platform === 'win32') await terminating; else kill(true) }
      cleanup()
      if (stopped) reject(stopped)
      else if (code !== 0) reject(new Error(`Command failed: ${command} (exit ${code ?? exitSignal})`))
      else resolve()
    })
  })
}
