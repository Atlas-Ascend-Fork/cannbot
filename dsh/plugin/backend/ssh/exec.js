// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

// Small promise wrapper around child_process.spawn with timeout + streaming lines.
import { spawn } from 'node:child_process'

/**
 * @param {string} command
 * @param {string[]} args
 * @param {{input?: string | Buffer, timeoutMs?: number, env?: NodeJS.ProcessEnv, cwd?: string,
 *          signal?: AbortSignal, onLine?: (line: string, fromStderr: boolean) => void | 'stop'}} [options]
 * @returns {Promise<{code: number, stdout: string, stderr: string, timedOut: boolean}>}
 */
export function run(command, args, options = {}) {
  const { input, timeoutMs = 120_000, env = process.env, cwd, onLine, signal } = options
  if (signal?.aborted) return Promise.resolve({ code: -3, stdout: '', stderr: 'Connection cancelled', timedOut: false })
  return new Promise((resolve) => {
    let settled = false
    let timer = null
    let child
    try {
      child = spawn(command, args, {
        cwd,
        env,
        windowsHide: true,
        stdio: ['pipe', 'pipe', 'pipe'],
      })
    } catch (error) {
      resolve({ code: -1, stdout: '', stderr: String(error && error.message ? error.message : error), timedOut: false })
      return
    }

    let stdout = ''
    let stderr = ''
    let stoppedByCaller = false
    let inputFailed = false

    const inputError = () => {
      // A peer can close stdin while a large payload is still queued. This is
      // an asynchronous stream error (usually EPIPE), not an exception from
      // end(). Keep the listener even after settlement to prevent an unhandled
      // error from terminating the DSH Host. Never include input or error text.
      if (settled || inputFailed || stoppedByCaller) return
      inputFailed = true
      stderr += `${stderr && !stderr.endsWith('\n') ? '\n' : ''}stdin write failed\n`
    }
    child.stdin.on('error', inputError)

    const finish = (code, timedOut) => {
      if (settled) return
      settled = true
      if (timer) clearTimeout(timer)
      signal?.removeEventListener('abort', abort)
      // Retain a real non-zero child exit code. A zero exit after a failed
      // payload write is not a successful transfer; explicit onLine stop is.
      const finalCode = stoppedByCaller ? 0 : (code === 0 && inputFailed ? -1 : code)
      resolve({ code: finalCode, stdout, stderr, timedOut: Boolean(timedOut) })
    }

    const abort = () => {
      stoppedByCaller = false
      try { child.kill() } catch { /* already exited */ }
      finish(-3, false)
    }
    signal?.addEventListener('abort', abort, { once: true })
    if (signal?.aborted) { abort(); return }

    const pump = (chunk, fromStderr) => {
      if (!onLine) return
      const text = chunk.toString('utf8')
      for (const line of text.split(/\r?\n/)) {
        if (!line) continue
        // A caller may return 'stop' once it has seen its terminal marker: the
        // remote daemon can legitimately keep the SSH channel open, and waiting
        // for the channel to close would hang the one-click flow.
        if (onLine(line, fromStderr) === 'stop') {
          stoppedByCaller = true
          try { child.kill() } catch { /* already gone */ }
          return
        }
      }
    }

    child.stdout.on('data', (chunk) => {
      stdout += chunk.toString('utf8')
      pump(chunk, false)
    })
    child.stderr.on('data', (chunk) => {
      stderr += chunk.toString('utf8')
      pump(chunk, true)
    })
    child.on('error', (error) => {
      stderr += String(error && error.message ? error.message : error)
      finish(-1, false)
    })
    child.on('close', (code) => finish(code === null ? -1 : code, false))

    if (timeoutMs > 0) {
      timer = setTimeout(() => {
        try { child.kill() } catch { /* ignore */ }
        finish(-2, true)
      }, timeoutMs)
      if (typeof timer.unref === 'function') timer.unref()
    }

    try {
      if (input) child.stdin.end(input)
      else child.stdin.end()
    } catch { inputError() }
  })
}

/** Quote a value for a POSIX shell (used when assembling remote command strings). */
export function shQuote(value) {
  return `'${String(value).replace(/'/g, `'\\''`)}'`
}
