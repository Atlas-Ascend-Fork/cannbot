// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

// Orchestration: inventory -> ssh probe -> remote bootstrap -> tunnel -> URL.
import { join } from 'node:path'
import { EventEmitter } from 'node:events'
import { run, shQuote } from './exec.js'
import { randomUUID } from 'node:crypto'
import { serversFile as defaultServersFile, stateFile as defaultStateFile, sshConfigPath } from './paths.js'
import { resolveSshBinary } from './ssh-binary.js'
import { listAliases } from './ssh-config.js'
import {
  allocateLocalPort,
  DEFAULT_LOCAL_PORT,
  DEFAULT_REMOTE_PORT,
  loadInventory,
  loadState,
  mergeInventory,
  saveState,
} from './servers.js'
import { loadCatalog } from './catalog.js'
import { bootstrapSshInvocation, failureHint, parseBootstrapOutput, parseStateOutput, readRemoteScript, sshArgs, stateSshInvocation } from './bootstrap.js'
import { decideDshVersion, decidePluginVersion } from './version.js'
import { TunnelSupervisor } from './tunnel.js'
import { syncCredentials } from './credentials-sync.js'
import { deployCurrentPackage } from './deploy.js'
import { packageVersion } from './package-root.js'
import { addServerRecord, ServerInputError } from './add-server.js'
import { setServerLabel } from './server-label.js'
import { reorderServers, removeServerRecord } from './server-management.js'
import { createPasswordAuth } from './password-auth.js'

const BOOTSTRAP_TIMEOUT_MS = 15 * 60 * 1000
const PROBE_TIMEOUT_MS = 20 * 1000

export const DEFAULT_CONFIG = {
  localPortStart: DEFAULT_LOCAL_PORT,
  remotePort: DEFAULT_REMOTE_PORT,
  dshVersion: '0.2.2-rc.1',
  pluginVersion: packageVersion,
  registry: 'https://registry.npmmirror.com',
  profile: 'web',
  catalogFile: '',
  sshBinary: '',
  syncLogin: true,
}

/**
 * @param {{config?: Partial<typeof DEFAULT_CONFIG>, exec?: typeof run,
 *          tunnel?: TunnelSupervisor, serversFile?: string, stateFile?: string,
 *          sshConfig?: string, logger?: (msg: string) => void}} [deps]
 */
export function createManager(deps = {}) {
  const config = { ...DEFAULT_CONFIG, ...(deps.config || {}) }
  const exec = deps.exec || run
  const logger = deps.logger || (() => {})
  const sshBin = (config.sshBinary && String(config.sshBinary).trim()) || resolveSshBinary()
  const tunnel = deps.tunnel || new TunnelSupervisor({ binary: sshBin, logger })
  const serversPath = deps.serversFile || defaultServersFile()
  const statePath = deps.stateFile || defaultStateFile()
  const configPath = deps.sshConfig || sshConfigPath()
  const bus = new EventEmitter()
  const activeConnections = new Map()
  const cancelledOperations = new Map()

  function snapshotState() {
    return loadState(statePath)
  }

  function inventory() {
    let discovered = { aliases: [], resolved: [], files: [] }
    try {
      discovered = listAliases(configPath)
    } catch (error) {
      logger(`ssh config scan failed: ${error.message}`)
    }
    const shared = loadInventory(serversPath)
    return mergeInventory({ shared, sshAliases: discovered.aliases, sshResolved: discovered.resolved })
  }

  function findServer(id) {
    const list = inventory().servers
    return list.find((server) => server.id === id || server.alias === id) || null
  }

  function serverStatus(server) {
    const state = snapshotState()
    const record = state.connections[server.id] || null
    const tunnelStatus = tunnel.status(server.id)
    return {
      id: server.id,
      alias: server.alias,
      label: server.label,
      group: server.group,
      source: server.source,
      inSshConfig: Boolean(server.inSshConfig),
      hostName: server.hostName,
      user: server.user,
      port: server.port,
      proxyJump: server.proxyJump || '',
      // A previous tunnel may survive while deployment restarts the remote Host.
      // Do not let inventory polling start workspace reads with stale credentials.
      connected: Boolean(tunnelStatus) && !activeConnections.has(server.id.toLowerCase()),
      tunnel: tunnelStatus,
      remotePort: record ? record.remotePort : null,
      localPort: record ? record.localPort : null,
      url: record ? record.url || '' : '',
      dshVersion: record ? record.dshVersion || '' : '',
      pluginVersion: record ? record.pluginVersion || '' : '',
      reusedDsh: record ? Boolean(record.reusedDsh) : false,
      reusedPlugin: record ? Boolean(record.reusedPlugin) : false,
      ascendEnv: record ? record.ascendEnv || '' : '',
      lastConnectedAt: record ? record.lastConnectedAt : null,
      lastError: record ? record.lastError || '' : '',
      loginSync: record ? record.loginSync || null : null,
    }
  }

  async function probe(server, signal, auth) {
    const invocation = sshArgs({ server, binary: sshBin })
    const input = auth?.invocation([...invocation.args, invocation.target, 'echo CANNBOT_SSH_OK'])
    const result = await exec(invocation.command, input?.args || [...invocation.args, invocation.target, 'echo CANNBOT_SSH_OK'], {
      timeoutMs: auth ? 390000 : PROBE_TIMEOUT_MS,
      signal, ...(input && { env: input.env, cwd: input.cwd }),
    })
    const output = `${result.stdout}\n${result.stderr}`
    if (result.code !== 0 || !output.includes('CANNBOT_SSH_OK')) {
      const reason = result.stderr.trim().split(/\r?\n/).slice(-1)[0] || `exit ${result.code}`
      return { ok: false, error: `SSH 连接失败：${reason}` }
    }
    return { ok: true }
  }

  /**
   * Connect: probe, bootstrap (idempotent), start tunnel, return the URL.
   * @param {string} id
   * @param {{progress?: (event: any) => void, syncLogin?: boolean}} [options]
   */
  function connect(id, options = {}) {
    const key = String(id).toLowerCase()
    if (cancelledOperations.has(key)) return Promise.reject(new ServerInputError('上一次连接仍在取消，请完成后再重试。', 409))
    if (activeConnections.has(key)) return Promise.reject(new ServerInputError('该服务器正在连接中，请稍后重试。', 409))
    const operation = { cancelled: false, tunnelling: false, controller: new AbortController(), requestId: options.requestId, marker: randomUUID(), remoteWorkStarted: false }
    activeConnections.set(key, operation)
    return connectServer(id, options, operation).finally(async () => {
      // Keep the cached credential alive until cancellation's remote cleanup ends.
      await operation.cleanup?.catch(() => {})
      await operation.auth?.dispose()
      if (activeConnections.get(key) === operation) activeConnections.delete(key)
    })
  }

  async function connectServer(id, options, operation) {
    const progress = options.progress || (() => {})
    const emit = (event) => {
      if (operation.cancelled) return
      const payload = { id, at: Date.now(), ...event }
      progress(payload)
      bus.emit('progress', payload)
    }

    const server = findServer(id)
    if (!server) return { ok: false, error: `未知服务器：${id}` }
    const active = () => !operation.cancelled && findServer(id) !== null
    const assertActive = () => { if (!active()) throw new ServerInputError(operation.removed ? '服务器已移除，本次连接已取消。' : '本次服务器连接已取消。', 409) }
    const signal = operation.controller.signal
    if (options.passwordPrompt) {
      operation.auth = await (deps.createPasswordAuth || createPasswordAuth)({ signal,
        onPrompt: challenge => emit({ phase: 'password', ...challenge }) })
      assertActive()
    }
    const auth = operation.auth
    const execute = (command, args, options) => {
      assertActive(); operation.remoteWorkStarted = true
      // Mark only this connection's short-lived SSH commands and their children.
      // The detached DSH service explicitly drops this marker before starting.
      const marked = [...args.slice(0, -1), 'env CANNBOT_CONNECT_ATTEMPT=' + shQuote(operation.marker) + ' sh -c ' + shQuote(args.at(-1))]
      const input = auth?.invocation(marked)
      return exec(command, input?.args || marked, { ...options, ...(input && { env: input.env, cwd: input.cwd, timeoutMs: Math.max(options?.timeoutMs || 0, 390000) }), signal })
    }

    const state = snapshotState()
    const previous = state.connections[id] || {}
    const usedPorts = Object.entries(state.connections)
      .filter(([key]) => key !== id)
      .map(([, record]) => record.localPort)
    const localPort = previous.localPort || allocateLocalPort({ used: usedPorts, start: config.localPortStart })

    emit({ phase: 'probe', level: 'info', message: `检查 SSH 连接（${server.alias}）` })
    const probed = await probe(server, signal, auth)
    assertActive()
    if (!probed.ok) {
      recordFailure(id, { ...previous, localPort }, probed.error)
      emit({ phase: 'error', level: 'error', message: probed.error })
      return { ok: false, error: probed.error }
    }
    emit({ phase: 'probe', level: 'ok', message: 'SSH 连接正常' })

    emit({ phase: 'inspect', level: 'info', message: '检查远端 dsh 与 CANNBot 插件版本' })
    const stateInvocation = stateSshInvocation({ server, binary: sshBin, profile: config.profile })
    const stateResult = await execute(stateInvocation.command, stateInvocation.args, { timeoutMs: PROBE_TIMEOUT_MS })
    assertActive()
    const remote = parseStateOutput(`${stateResult.stdout}\n${stateResult.stderr}`)
    const dshDecision = decideDshVersion({ existing: remote.dshVersion, pinned: config.dshVersion })
    const pluginDecision = decidePluginVersion({ existing: remote.pluginVersion, desired: config.pluginVersion })
    emit({ phase: 'inspect', level: 'ok', message: dshDecision.reason })
    emit({ phase: 'inspect', level: pluginDecision.action === 'reuse' ? 'ok' : 'info', message: pluginDecision.reason })

    emit({ phase: 'bootstrap', level: 'info', message: '准备远端工作台 环境（首次可能需要数分钟）' })
    const invocation = bootstrapSshInvocation({
      server,
      binary: sshBin,
      remotePort: config.remotePort,
      dshVersion: dshDecision.version,
      pluginVersion: pluginDecision.version,
      registry: config.registry,
      profile: config.profile,
      prepareOnly: true,
    })
    const boot = await execute(invocation.command, invocation.args, {
      input: readRemoteScript(),
      timeoutMs: BOOTSTRAP_TIMEOUT_MS,
      onLine: (line) => {
        if (line.startsWith('CANNBOT_STEP=')) {
          emit({ phase: 'bootstrap', level: 'info', message: line.replace('CANNBOT_STEP=', '') })
          return
        }
        if (line.startsWith('[cannbot]')) {
          emit({ phase: 'bootstrap', level: 'debug', message: line.slice(9).trim() })
          return
        }
        // Terminal markers: stop the ssh stream instead of waiting for the
        // channel to close (the remote daemon may hold it open).
        if (line.trim() === 'CANNBOT_OK=1' || line.startsWith('CANNBOT_ERROR=')) return 'stop'
      },
    })
    assertActive()
    let parsed = parseBootstrapOutput(`${boot.stdout}\n${boot.stderr}`)
    if (!parsed.ok || boot.code !== 0) {
      const hint = failureHint(parsed, boot.code)
      recordFailure(id, { ...previous, localPort }, hint)
      emit({ phase: 'error', level: 'error', message: hint })
      return { ok: false, error: hint }
    }
    emit({ phase: 'bootstrap', level: 'ok', message: '远端环境就绪' })

    emit({ phase: 'deploy', level: 'info', message: '同步当前 CANNBot 主插件与远端界面' })
    try {
      const deployed = await (deps.deployPackage || deployCurrentPackage)({
        server, binary: sshBin, profile: config.profile, registry: config.registry,
        remotePort: config.remotePort, ascendEnv: parsed.ascendEnv, exec: execute,
        progress: message => emit({ phase: 'deploy', level: 'info', message }),
      })
      assertActive()
      parsed = { ...parsed, ...deployed, dshVersion: deployed.dshVersion || parsed.dshVersion, ascendEnv: deployed.ascendEnv || parsed.ascendEnv }
    } catch (error) {
      assertActive()
      const hint = error.message || '当前 CANNBot 主插件同步失败。'
      recordFailure(id, { ...previous, localPort }, hint)
      emit({ phase: 'error', level: 'error', message: hint })
      return { ok: false, error: hint }
    }

    // The account grant stays in the host and SSH stdin. Only a fixed status
    // summary may enter browser responses or the persisted connection state.
    let loginSync = { status: 'skipped', message: '本次未同步本机 模型账号授权。' }
    if (config.syncLogin !== false && options.syncLogin === true) {
      emit({ phase: 'login-sync', level: 'info', message: '同步本机 模型账号授权到所选服务器' })
      try {
        loginSync = await syncCredentials({ server, binary: sshBin, exec: execute, readLocalRecord: deps.readLocalRecord, profile: config.profile })
      } catch {
        loginSync = { status: 'failed', message: '登录同步未完成，可在远端登录后继续使用。' }
      }
      assertActive()
      emit({ phase: 'login-sync', level: ['failed', 'unsupported'].includes(loginSync.status) ? 'warning' : 'info', message: loginSync.message })
    }

    const remotePort = parsed.remotePort || config.remotePort
    emit({ phase: 'tunnel', level: 'info', message: `建立隧道 127.0.0.1:${localPort} -> ${remotePort}` })
    const base = sshArgs({ server, binary: sshBin })
    let tunnelResult
    operation.tunnelling = true
    try {
      const input = auth?.invocation(base.args)
      tunnelResult = await tunnel.ensure({ id, target: base.target, sshArgs: input?.args || base.args, localPort, remotePort, signal,
        ...(input && { env: input.env, cwd: input.cwd, timeoutMs: 390000 }) })
    } finally { operation.tunnelling = false }
    if (!active()) { tunnel.stop(id); assertActive() }
    if (!tunnelResult.started && tunnelResult.error) {
      recordFailure(id, { ...previous, localPort, remotePort }, tunnelResult.error)
      emit({ phase: 'error', level: 'error', message: tunnelResult.error })
      return { ok: false, error: tunnelResult.error }
    }
    emit({ phase: 'tunnel', level: 'ok', message: '隧道就绪' })

    const url = `${tunnelResult.url}${parsed.token ? `?token=${encodeURIComponent(parsed.token)}` : ''}`
    const record = {
      localPort,
      remotePort,
      token: parsed.token || '',
      url,
      webLog: parsed.webLog || '',
      dshVersion: parsed.dshVersion || remote.dshVersion || '',
      pluginVersion: parsed.pluginVersion || remote.pluginVersion || '',
      reusedDsh: dshDecision.action === 'reuse',
      reusedPlugin: Boolean(parsed.reused),
      ascendEnv: parsed.ascendEnv || '',
      lastConnectedAt: new Date().toISOString(),
      lastError: '',
      loginSync,
      sourceHash: parsed.sourceHash || '',
    }
    const latestState = snapshotState()
    latestState.connections[id] = record
    saveState(statePath, latestState)
    emit({ phase: 'ready', level: 'ok', message: '已连接', url })
    return {
      ok: true,
      url,
      token: parsed.token || '',
      localPort,
      remotePort,
      reused: parsed.reused,
      dshVersion: record.dshVersion,
      pluginVersion: record.pluginVersion,
      reusedDsh: record.reusedDsh,
      reusedPlugin: record.reusedPlugin,
      ascendEnv: record.ascendEnv,
      loginSync,
    }
  }

  function recordFailure(id, record, error) {
    const state = snapshotState()
    state.connections[id] = {
      ...(record || {}),
      lastConnectedAt: record && record.lastConnectedAt ? record.lastConnectedAt : null,
      lastError: error,
      failedAt: new Date().toISOString(),
    }
    try {
      saveState(statePath, state)
    } catch (writeError) {
      logger(`state write failed: ${writeError.message}`)
    }
  }

  function disconnect(id) {
    const stopped = tunnel.stop(id)
    const state = snapshotState()
    if (state.connections[id]) {
      state.connections[id].disconnectedAt = new Date().toISOString()
      saveState(statePath, state)
    }
    return { ok: true, stopped }
  }

  async function cancelConnect(id, requestId) {
    const key = String(id).toLowerCase()
    const operation = activeConnections.get(key) || cancelledOperations.get(key)
    if (operation && (!requestId || operation.requestId === requestId)) {
      operation.cancelled = true
      operation.auth?.cachedOnly()
      operation.controller.abort()
      tunnel.stop(id)
      if (operation.remoteWorkStarted) {
        cancelledOperations.set(key, operation)
        const server = findServer(id)
        if (server) {
          const invocation = sshArgs({ server, binary: sshBin })
          const marker = shQuote('CANNBOT_CONNECT_ATTEMPT=' + operation.marker)
          // Do not stop existing DSH services or user jobs. /proc ownership and
          // the unguessable exact environment marker identify only our attempt.
          const cleanup = `for pass in 1 2; do for p in /proc/[0-9]*; do [ -O "$p" ] || continue; if grep -zFxq -- ${marker} "$p/environ" 2>/dev/null; then kill -TERM "\${p##*/}" 2>/dev/null || :; fi; done; done`
          const args = [...invocation.args, invocation.target, cleanup]
          const input = operation.auth?.invocation(args)
          operation.cleanup = exec(invocation.command, input?.args || args, { timeoutMs: 10000, ...(input && { env: input.env, cwd: input.cwd }) })
          const result = await operation.cleanup
          if (result.code !== 0) throw new ServerInputError('取消远端安装未完成，请检查 SSH 连接后重试。', 502)
        }
        if (cancelledOperations.get(key) === operation) cancelledOperations.delete(key)
      }
    }
    return { ok: true }
  }

  async function diagnose(id) {
    const server = findServer(id)
    if (!server) return { ok: false, error: `未知服务器：${id}` }
    const script = [
      'echo "CANNBOT_DIAG_BEGIN"',
      'uname -srm',
      '. /etc/os-release 2>/dev/null && echo "$PRETTY_NAME"',
      'echo "node: $(node -v 2>/dev/null || echo missing)"',
      'echo "dsh: $(dsh --version 2>/dev/null || echo missing)"',
      'echo "python3: $(python3 -V 2>&1 || echo missing)"',
      'python3 -c "import yaml" >/dev/null 2>&1 && echo "pyyaml: ok" || echo "pyyaml: missing"',
      'echo "git: $(git --version 2>/dev/null || echo missing)"',
      'ls -d /usr/local/Ascend/ascend-toolkit 2>/dev/null && echo "ascend: toolkit-found" || echo "ascend: toolbox-missing"',
      'npu-smi info 2>/dev/null | head -5 || echo "npu-smi: unavailable"',
      'echo "home: $HOME"; df -h "$HOME" 2>/dev/null | tail -1',
      'echo "CANNBOT_DIAG_END"',
    ].join('; ')
    const invocation = sshArgs({ server, binary: sshBin })
    const result = await exec(invocation.command, [...invocation.args, invocation.target, script], {
      timeoutMs: 60_000,
    })
    return {
      ok: result.code === 0,
      exitCode: result.code,
      text: result.stdout.trim(),
      stderr: result.stderr.trim(),
    }
  }

  return {
    config,
    tunnel,
    inventory,
    serverStatus,
    listServers: () => inventory().servers.map(serverStatus),
    addServer(request) {
      const added = addServerRecord(request, { configPath, serversPath })
      const server = findServer(added.alias)
      return { id: added.alias, alias: added.alias, label: added.label, connected: Boolean(server && tunnel.status(server.id)) }
    },
    renameServer(request) {
      const updated = setServerLabel(request, { configPath, serversPath })
      return { id: updated.alias, alias: updated.alias, label: updated.label, connected: Boolean(tunnel.status(updated.alias)) }
    },
    reorderServers(request) { return reorderServers(request, { configPath, serversPath }) },
    removeServer(request) {
      let stopped = false
      const result = removeServerRecord(request, { configPath, serversPath }, id => {
        // This callback runs only after validation and preparing the atomic
        // inventory write. A failure leaves the row visible, possibly offline.
        const running = activeConnections.get(id.toLowerCase())
        // TunnelSupervisor has no cancellable ensure contract. Do not publish a
        // tombstone while that call could still create a local SSH process.
        if (running?.tunnelling) throw new ServerInputError('服务器正在建立隧道，请等待完成后再移除。', 409)
        stopped = tunnel.stop(id)
        if (running) { running.removed = true; running.cancelled = true; running.controller.abort() }
      })
      return { ...result, stopped }
    },
    // Host-only capability. Never include this object in a state/list route.
    getConnection(id) {
      if (activeConnections.has(String(id).toLowerCase())) return null
      if (!tunnel.status(id)) return null
      const record = snapshotState().connections[id]
      return record ? { id, connected: true, url: record.url, token: record.token, localPort: record.localPort, remotePort: record.remotePort } : null
    },
    connect,
    submitPassword(id, requestId, challengeId, password) {
      const operation = activeConnections.get(String(id).toLowerCase())
      return Boolean(operation && !operation.cancelled && operation.requestId === requestId && operation.auth?.submit(challengeId, password))
    },
    cancelConnect,
    disconnect,
    diagnose,
    catalog: () => loadCatalog(config.catalogFile),
    onProgress: (fn) => bus.on('progress', fn),
    offProgress: (fn) => bus.off('progress', fn),
    serversPath,
    statePath,
    sshConfigPath: configPath,
  }
}
