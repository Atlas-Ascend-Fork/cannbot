// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { createServer } from 'node:http'
import { randomBytes, randomUUID } from 'node:crypto'
import { mkdtemp, writeFile, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { packageRoot } from '../package-root.js'
import { run, shQuote } from './exec.js'

// Passwords travel only over authenticated host IPC and an ephemeral loopback
// channel to OpenSSH's askpass child. No password is put in argv, env or files.
export async function createPasswordAuth({ onPrompt, signal, timeoutMs = 120000 }) {
  const directory = await mkdtemp(join(tmpdir(), 'cannbot-askpass-'))
  const token = randomBytes(32).toString('hex'), cache = new Map(), calls = new Map(), pending = new Map()
  let closed = false, cachedOnly = false
  const abort = () => { for (const item of pending.values()) item.reject(new Error('密码输入已取消。')); pending.clear() }
  signal?.addEventListener('abort', abort, { once: true })
  const server = createServer(async (request, response) => {
    response.setHeader('Cache-Control', 'no-store')
    if (closed || request.method !== 'POST' || request.url !== '/' || request.headers.authorization !== `Bearer ${token}`) { response.writeHead(403).end(); return }
    try {
      let body = ''
      for await (const chunk of request) { body += chunk; if (body.length > 8192) throw new Error('input too long') }
      const { prompt, callId } = JSON.parse(body)
      // Never answer host-key confirmations, private-key passphrases or MFA.
      if (typeof prompt !== 'string' || !/^[^\r\n]{1,512}'s password:\s*$/i.test(prompt) || !calls.has(callId)) throw new Error('unsupported challenge')
      const seen = calls.get(callId), retry = seen.has(prompt)
      seen.add(prompt)
      if (retry) cache.delete(prompt)
      if (!cache.has(prompt)) {
        if (cachedOnly || signal?.aborted) throw new Error('cancelled')
        const challengeId = randomUUID()
        const password = await new Promise((resolve, reject) => {
          const timer = setTimeout(() => pending.get(challengeId)?.reject(new Error('密码输入超时，请重新连接。')), timeoutMs)
          pending.set(challengeId, {
            resolve: value => { clearTimeout(timer); pending.delete(challengeId); resolve(value) },
            reject: error => { clearTimeout(timer); pending.delete(challengeId); reject(error) },
          })
          try { onPrompt({ challengeId, prompt, retry }) } catch { pending.get(challengeId)?.reject(new Error('无法显示密码输入框。')) }
        })
        if (closed || signal?.aborted) throw new Error('cancelled')
        cache.set(prompt, password)
      }
      response.writeHead(200, { 'Content-Type': 'text/plain; charset=utf-8' }).end(cache.get(prompt))
    } catch { response.writeHead(403).end() }
  })
  try {
    let executable, cwd
    if (process.platform === 'win32') {
      executable = join(directory, 'askpass.exe')
      const quote = value => "'" + value.replaceAll("'", "''") + "'"
      const result = await run(join(process.env.SystemRoot || 'C:\\Windows', 'System32', 'WindowsPowerShell', 'v1.0', 'powershell.exe'),
        ['-NoProfile', '-NonInteractive', '-Command', `Add-Type -Path ${quote(join(packageRoot(), 'remote', 'askpass.cs'))} -OutputAssembly ${quote(executable)} -OutputType ConsoleApplication -ErrorAction Stop; try { (New-Object -ComObject Scripting.FileSystemObject).GetFile(${quote(executable)}).ShortPath } catch {}`], { signal, timeoutMs: 30000 })
      if (result.code !== 0) throw new Error('无法准备 SSH 密码输入组件，请检查 Windows PowerShell 是否可用。')
      // Windows OpenSSH 9.5 cannot spawn an askpass path with non-ASCII text.
      // Prefer the short path; with 8.3 names disabled, resolve an ASCII name
      // against a Unicode-capable cwd supplied directly by Node/CreateProcessW.
      const short = result.stdout.trim()
      if (short && /^[\x20-\x7e]+$/.test(short)) executable = short
      else if (/[^\x20-\x7e]/.test(executable)) { executable = 'askpass.exe'; cwd = directory }
    } else {
      executable = join(directory, 'askpass')
      await writeFile(executable, '#!/bin/sh\nexec ' + shQuote(process.execPath) + ' ' + shQuote(join(packageRoot(), 'remote', 'askpass.cjs')) + ' "$@"\n', { mode: 0o700 })
    }
    signal?.throwIfAborted()
    await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve) })
    return {
      invocation(args) {
        const callId = randomUUID(); calls.set(callId, new Set())
        return { cwd, args: ['-o', 'KbdInteractiveAuthentication=no', ...args.map(arg => arg === 'BatchMode=yes' ? 'BatchMode=no' : arg === 'NumberOfPasswordPrompts=0' ? 'NumberOfPasswordPrompts=3' : arg)],
          env: { ...process.env, SSH_ASKPASS: executable.replaceAll('\\', '/'), SSH_ASKPASS_REQUIRE: 'force', DISPLAY: process.env.DISPLAY || 'cannbot:0',
            CANNBOT_ASKPASS_PORT: String(server.address().port), CANNBOT_ASKPASS_TOKEN: token, CANNBOT_ASKPASS_CALL: callId } }
      },
      submit(challengeId, password) {
        const item = pending.get(challengeId)
        if (!item || closed || signal?.aborted) return false
        if (typeof password !== 'string' || !password || Buffer.byteLength(password) > 1000 || /[\r\n\0]/.test(password)) return false
        item.resolve(password); return true
      },
      // Cancellation cleanup can reuse a known password, but never prompt again.
      cachedOnly() { cachedOnly = true; abort() },
      async dispose() {
        closed = true; abort(); cache.clear(); calls.clear(); signal?.removeEventListener('abort', abort)
        server.closeAllConnections(); await new Promise(resolve => server.close(resolve))
        await rm(directory, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 }).catch(() => {})
      },
    }
  } catch (error) {
    signal?.removeEventListener('abort', abort); server.close()
    await rm(directory, { recursive: true, force: true }).catch(() => {})
    throw error
  }
}
