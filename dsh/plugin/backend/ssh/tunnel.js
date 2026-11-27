// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

// SSH local-forward supervisor: one long-lived `ssh -N -L` per connection.
import { spawn } from 'node:child_process'
import { connect } from 'node:net'

/** Resolve true when `port` on `host` accepts a TCP connection within `timeoutMs`. */
export function isPortListening(port, host = '127.0.0.1', timeoutMs = 800) {
  return new Promise((resolve) => {
    const socket = connect({ host, port })
    let done = false
    const finish = (value) => {
      if (done) return
      done = true
      socket.destroy()
      resolve(value)
    }
    socket.setTimeout(timeoutMs)
    socket.once('connect', () => finish(true))
    socket.once('timeout', () => finish(false))
    socket.once('error', () => finish(false))
  })
}

/** Poll until the port is listening (or give up). */
export async function waitForPort(port, { host = '127.0.0.1', timeoutMs = 20_000, intervalMs = 300, signal, alive = () => true } = {}) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    if (signal?.aborted || !alive()) return false
    if (await isPortListening(port, host)) return true
    await new Promise((resolve) => setTimeout(resolve, intervalMs))
  }
  return false
}

/** Tunnel-specific ssh options. Duplicates with the caller's base are harmless. */
export const TUNNEL_SSH_OPTIONS = [
  '-N',
  '-o', 'ExitOnForwardFailure=yes',
  '-o', 'ServerAliveInterval=30',
  '-o', 'ServerAliveCountMax=3',
]

export class TunnelSupervisor {
  constructor({ binary = 'ssh', logger = () => {} } = {}) {
    this.binary = binary
    this.logger = logger
    /** @type {Map<string, {child: any, localPort: number, remotePort: number, startedAt: number, stderr: string}>} */
    this.entries = new Map()
    this.exitHookInstalled = false
  }

  has(id) {
    return this.entries.has(id)
  }

  status(id) {
    const entry = this.entries.get(id)
    if (!entry) return null
    return {
      running: true,
      pid: entry.child ? entry.child.pid : null,
      localPort: entry.localPort,
      remotePort: entry.remotePort,
      startedAt: entry.startedAt,
    }
  }

  list() {
    return [...this.entries.entries()].map(([id, entry]) => ({
      id,
      pid: entry.child ? entry.child.pid : null,
      localPort: entry.localPort,
      remotePort: entry.remotePort,
      startedAt: entry.startedAt,
    }))
  }

  /**
   * Start or reuse a tunnel.
   * @param {{id: string, target: string, sshArgs?: string[], localPort: number, remotePort: number}} input
   * @returns {Promise<{started: boolean, url?: string, error?: string, localPort: number, remotePort: number}>}
   */
  async ensure({ id, target, sshArgs = [], localPort, remotePort, signal, env, cwd, timeoutMs }) {
    signal?.throwIfAborted()
    const previous = this.entries.get(id)
    if (previous && previous.localPort === localPort && previous.remotePort === remotePort && (await isPortListening(localPort))) {
      signal?.throwIfAborted()
      return { started: false, url: `http://127.0.0.1:${localPort}/`, localPort, remotePort }
    }
    if (this.has(id)) this.stop(id)
    signal?.throwIfAborted()

    const args = [
      ...sshArgs,
      ...TUNNEL_SSH_OPTIONS,
      '-L', `${localPort}:127.0.0.1:${remotePort}`,
      target,
    ]

    const entry = { child: null, localPort, remotePort, startedAt: Date.now(), stderr: '' }
    let child
    try {
      child = spawn(this.binary, args, {
        windowsHide: true,
        ...(env && { env }),
        ...(cwd && { cwd }),
        stdio: ['ignore', 'pipe', 'pipe'],
      })
    } catch (error) {
      return { started: false, error: `无法启动 ssh: ${error.message}`, localPort, remotePort }
    }

    child.stderr.on('data', (chunk) => {
      entry.stderr += chunk.toString('utf8')
      if (entry.stderr.length > 8192) entry.stderr = entry.stderr.slice(-8192)
    })
    child.on('exit', (code) => {
      this.logger(`tunnel ${id} exited (${code})${entry.stderr ? `: ${entry.stderr.trim().split(/\r?\n/).slice(-1)[0]}` : ''}`)
      if (this.entries.get(id) === entry) this.entries.delete(id)
    })
    child.on('error', (error) => {
      this.logger(`tunnel ${id} failed to spawn: ${error.message}`)
      if (this.entries.get(id) === entry) this.entries.delete(id)
    })

    entry.child = child
    this.entries.set(id, entry)
    this.installExitHook()

    const abort = () => this.stop(id)
    signal?.addEventListener('abort', abort, { once: true })
    if (signal?.aborted) abort()
    let up
    try { up = await waitForPort(localPort, { signal, timeoutMs, alive: () => this.entries.get(id) === entry }) }
    finally { signal?.removeEventListener('abort', abort) }
    signal?.throwIfAborted()
    if (!up) {
      const hint = entry.stderr.trim() || `隧道端口 ${localPort} 未就绪`
      this.stop(id)
      return { started: false, error: hint, localPort, remotePort }
    }
    return { started: true, url: `http://127.0.0.1:${localPort}/`, localPort, remotePort }
  }

  stop(id) {
    const entry = this.entries.get(id)
    if (!entry) return false
    this.entries.delete(id)
    try { entry.child.kill() } catch { /* already gone */ }
    return true
  }

  stopAll() {
    for (const id of [...this.entries.keys()]) this.stop(id)
  }

  installExitHook() {
    if (this.exitHookInstalled) return
    this.exitHookInstalled = true
    process.once('exit', () => this.stopAll())
    process.once('SIGINT', () => { this.stopAll(); process.exit(130) })
    process.once('SIGTERM', () => { this.stopAll(); process.exit(143) })
  }
}
