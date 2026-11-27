// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { test } from 'node:test'
import assert from 'node:assert/strict'
import { mkdirSync, writeFileSync, rmSync, readFileSync, existsSync } from 'node:fs'
import { join } from 'node:path'
import { createManager as createProductionManager } from '../../plugin/backend/ssh/manager.js'
import { createRouter, ROUTE } from '../../plugin/backend/ssh/routes.js'

// Network-free adapter: deployment behavior has its own transfer/lifecycle tests.
function createManager(deps) { return createProductionManager({ deployPackage: async () => ({}), ...deps }) }

test('cancelling an active probe aborts SSH and cannot bootstrap or create a tunnel', async () => {
  const fixture = setup('cancel-probe'), tunnel = fakeTunnel()
  let signal, calls = 0
  const manager = createManager({ ...fixture, tunnel, exec: async (_command, _args, options) => {
    calls++; signal = options.signal
    return new Promise(resolve => signal.addEventListener('abort', () => resolve({ code: -3, stdout: '', stderr: '' }), { once: true }))
  } })
  const task = manager.connect('npu-01', { requestId: 'current' })
  manager.cancelConnect('npu-01', 'stale'); assert.equal(signal.aborted, false)
  manager.cancelConnect('npu-01', 'current')
  await assert.rejects(task, /取消/)
  assert.equal(signal.aborted, true); assert.equal(calls, 1); assert.equal(tunnel.list().length, 0)
})

const ROOT = join(process.cwd(), '_scratch', 'manager')

test('remote cancellation targets the attempt marker and does not advance to bootstrap', async () => {
  const fixture = setup('cancel-remote'), tunnel = fakeTunnel(), calls = []
  let ready, signal
  const inspected = new Promise(resolve => { ready = resolve })
  const manager = createManager({ ...fixture, tunnel, exec: async (_command, args, options) => {
    const command = args.at(-1); calls.push(command)
    if (command.includes('echo CANNBOT_SSH_OK')) return { code: 0, stdout: 'CANNBOT_SSH_OK', stderr: '' }
    if (command.startsWith('for pass')) return { code: 0, stdout: '', stderr: '' }
    signal = options.signal; ready()
    return new Promise(resolve => signal.addEventListener('abort', () => resolve({ code: -3, stdout: '', stderr: '' }), { once: true }))
  } })
  const connection = manager.connect('npu-01', { requestId: 'test' })
  const cancelled = assert.rejects(connection, /取消/)
  await inspected; await manager.cancelConnect('npu-01', 'test'); await cancelled
  assert.equal(calls.length, 3)
  const marker = calls[1].match(/CANNBOT_CONNECT_ATTEMPT='([\da-f-]+)'/)[1]
  assert(calls[2].includes('CANNBOT_CONNECT_ATTEMPT=' + marker))
  assert(calls[2].includes('[ -O "$p" ]')); assert(calls[2].includes('kill -TERM'))
  assert.equal(tunnel.list().length, 0)
})

function setup(name) {
  const dir = join(ROOT, name)
  rmSync(dir, { recursive: true, force: true })
  mkdirSync(dir, { recursive: true })
  const sshConfig = join(dir, 'ssh_config')
  writeFileSync(sshConfig, 'Host npu-01\n  HostName 10.0.0.11\n  User HwHiAiUser\n  Port 2222\n')
  writeFileSync(join(dir, 'servers.json'), JSON.stringify({
    version: 1,
    servers: [{ alias: 'npu-01', label: '训练机 1' }, { alias: 'npu-missing', label: '没配 ssh 的机器' }],
  }))
  return {
    dir,
    sshConfig,
    serversFile: join(dir, 'servers.json'),
    stateFile: join(dir, 'state.json'),
  }
}

function fakeExecFactory(outcomes) {
  const calls = []
  const defaultState = {
    code: 0,
    stdout: 'CANNBOT_STATE_DSH=0.2.2-rc.1\nCANNBOT_STATE_PLUGIN=1.0.0-alpha.1\n',
    stderr: '',
    timedOut: false,
  }
  const exec = async (command, args, options) => {
    const joined = args.map(String).join(' ')
    const kind = joined.includes('CANNBOT_SSH_OK')
      ? 'probe'
      : joined.includes('CANNBOT_STATE_DSH')
        ? 'state'
        : joined.includes('CANNBOT_CREDENTIALS_STATUS=')
          ? 'credentials'
          : 'bootstrap'
    const { input: stdin, ...executionOptions } = options || {}
    calls.push({ command, args, kind, input: stdin ? stdin.length : 0, stdin, executionOptions })
    const outcome = kind === 'state' && !outcomes.state
      ? defaultState
      : typeof outcomes[kind] === 'function'
        ? outcomes[kind](command, args, options)
        : outcomes[kind]
    // Mirror the real runner: stream stdout lines to the caller's onLine hook.
    if (options && typeof options.onLine === 'function' && outcome) {
      for (const line of String(outcome.stdout || '').split(/\r?\n/)) {
        if (line) options.onLine(line, false)
      }
    }
    return outcome
  }
  return { exec, calls }
}

function fakeTunnel(options = {}) {
  const state = new Map()
  return {
    entries: state,
    status: (id) => (state.has(id) ? state.get(id) : null),
    list: () => [...state.values()],
    ensure: async (input) => {
      options.onEnsure?.(input)
      if (options.fail) return { started: false, error: options.fail, localPort: input.localPort, remotePort: input.remotePort }
      const record = { localPort: input.localPort, remotePort: input.remotePort, startedAt: Date.now(), pid: 4242 }
      state.set(input.id, record)
      return { started: true, url: `http://127.0.0.1:${input.localPort}/`, localPort: input.localPort, remotePort: input.remotePort }
    },
    stop: (id) => state.delete(id),
    stopAll: () => state.clear(),
  }
}

const BOOTSTRAP_OK = {
  code: 0,
  stdout: [
    'CANNBOT_STEP=1/7 check node',
    'CANNBOT_STEP=5/7 install CANNBot plugin',
    'CANNBOT_REMOTE_PORT=17634',
    'CANNBOT_WEB_LOG=/home/u/.dsh/web-17634.log',
    'CANNBOT_TOKEN=tok_123',
    'CANNBOT_REUSE=0',
    'CANNBOT_OK=1',
  ].join('\n'),
  stderr: '',
  timedOut: false,
}

test('current source deployment precedes credential sync and exposes connection details only through the Host capability', async () => {
  const paths = setup('current-source-deployment'), order = []
  const { exec } = fakeExecFactory({ probe: PROBE_OK, bootstrap: BOOTSTRAP_OK })
  const manager = createManager({ ...paths, exec, config: { syncLogin: false }, tunnel: fakeTunnel({ onEnsure() { order.push('tunnel') } }),
    deployPackage: async params => { order.push('deploy'); assert.equal(params.server.id, 'npu-01'); return { token: 'deployed-token', remotePort: 17640, buildId: 'a'.repeat(64), pluginVersion: '1.0.0-alpha.1' } },
  })
  assert.equal(manager.getConnection('npu-01'), null)
  const result = await manager.connect('npu-01')
  assert.equal(result.ok, true)
  assert.deepEqual(order, ['deploy', 'tunnel'])
  assert.equal(result.remotePort, 17640)
  assert.equal(manager.getConnection('npu-01').token, 'deployed-token')
  assert.equal(JSON.parse(readFileSync(paths.stateFile, 'utf8')).connections['npu-01'].buildId, 'a'.repeat(64))
  manager.disconnect('npu-01')
  assert.equal(manager.getConnection('npu-01'), null)
})

test('a failed source deployment never reads credentials or opens a tunnel', async () => {
  const paths = setup('source-deployment-failure')
  const { exec } = fakeExecFactory({ probe: PROBE_OK, bootstrap: BOOTSTRAP_OK })
  const manager = createManager({ ...paths, exec, tunnel: fakeTunnel({ onEnsure() { assert.fail('no tunnel after failed source update') } }),
    readLocalRecord() { assert.fail('no credential transfer after failed source update') },
    deployPackage: async () => { throw Error('Stop the original server, then reconnect.') },
  })
  const result = await manager.connect('npu-01')
  assert.equal(result.ok, false)
  assert.match(result.error, /Stop the original server/)
})

const PROBE_OK = { code: 0, stdout: 'CANNBOT_SSH_OK\n', stderr: '', timedOut: false }
test('inventory and workspace capability remain unavailable during deployment over a previous tunnel', async () => {
  const paths = setup('deploy-readiness'), tunnel = fakeTunnel()
  const { exec } = fakeExecFactory({ probe: PROBE_OK, bootstrap: BOOTSTRAP_OK })
  let entered, release
  const deploying = new Promise(resolve => { entered = resolve })
  const gate = new Promise(resolve => { release = resolve })
  const manager = createManager({ ...paths, exec, tunnel, config: { syncLogin: false }, deployPackage: async () => { entered(); await gate; return { token: 'fresh' } } })
  await tunnel.ensure({ id: 'npu-01', localPort: 17633, remotePort: 17634 })
  const connection = manager.connect('npu-01')
  await deploying
  assert.equal(manager.listServers().find(server => server.id === 'npu-01').connected, false)
  assert.equal(manager.getConnection('npu-01'), null)
  release(); assert.equal((await connection).ok, true)
  assert.equal(manager.listServers().find(server => server.id === 'npu-01').connected, true)
  assert.equal(manager.getConnection('npu-01').token, 'fresh')
})
const FAKE_GRANT_TOKEN = 'unit-test-platform-grant-not-a-real-secret'
const FAKE_EXTRA_SECRET = 'unit-test-unrelated-record-field'
const FAKE_GRANT = {
  kind: 'grant',
  payload: { version: 1, issuer: 'https://platform.deepseek.com', token: FAKE_GRANT_TOKEN },
  unrelated: FAKE_EXTRA_SECRET,
}

function assertNoAccountSecrets(value) {
  const text = typeof value === 'string' ? value : JSON.stringify(value)
  assert.equal(text.includes(FAKE_GRANT_TOKEN), false, 'account grant must not escape SSH stdin')
  assert.equal(text.includes(FAKE_EXTRA_SECRET), false, 'unrelated credential fields must never be forwarded')
}

test('consented login sync runs after bootstrap and before the tunnel, with the grant only in SSH stdin', async () => {
  const paths = setup('login-sync-order')
  const timeline = []
  const events = []
  const logs = []
  const { exec: fakeExec, calls } = fakeExecFactory({
    probe: PROBE_OK,
    bootstrap: BOOTSTRAP_OK,
    credentials: {
      code: 0,
      stdout: `untrusted diagnostic ${FAKE_GRANT_TOKEN}\nCANNBOT_CREDENTIALS_STATUS=synced\n`,
      stderr: FAKE_EXTRA_SECRET,
      timedOut: false,
    },
  })
  const manager = createManager({
    ...paths,
    exec: async (...args) => {
      const outcome = await fakeExec(...args)
      timeline.push(calls.at(-1).kind)
      return outcome
    },
    tunnel: fakeTunnel({ onEnsure: () => timeline.push('tunnel') }),
    logger: (message) => logs.push(message),
    readLocalRecord: async (key) => {
      assert.equal(key, 'deepseek-account-platform/default')
      timeline.push('read-local')
      return FAKE_GRANT
    },
  })
  manager.onProgress((event) => events.push(event))
  const router = createRouter({ manager })
  const response = await router(new Request(`http://dsh.invalid${ROUTE}/connect`, {
    method: 'POST', body: JSON.stringify({ id: 'npu-01', syncLogin: true }),
  }))
  const result = await response.json()
  assert.equal(result.ok, true)
  assert.equal(result.loginSync.status, 'synced')
  assert.deepEqual(timeline, ['probe', 'state', 'bootstrap', 'read-local', 'credentials', 'tunnel'])
  const syncCall = calls.find((call) => call.kind === 'credentials')
  assert.equal(syncCall.args.at(-2), 'npu-01', 'credentials use a separate SSH call to the selected server')
  assert.deepEqual(JSON.parse(syncCall.stdin), { kind: 'grant', payload: FAKE_GRANT.payload })
  assert.equal(syncCall.executionOptions.onLine, undefined, 'raw credential stdout must not stream into UI progress')
  for (const call of calls) {
    const { stdin, ...metadata } = call
    assertNoAccountSecrets(metadata)
    if (call.kind !== 'credentials') assertNoAccountSecrets(stdin || '')
  }
  assert.ok(events.some((event) => event.phase === 'login-sync'))
  for (const output of [result, events, logs, manager.listServers(), readFileSync(paths.stateFile, 'utf8')]) assertNoAccountSecrets(output)
  for (const path of ['/state', '/servers']) {
    const body = await (await router(new Request(`http://dsh.invalid${ROUTE}${path}`))).json()
    assert.equal(body.servers.find((server) => server.id === 'npu-01').loginSync.status, 'synced')
    assertNoAccountSecrets(body)
  }
})

test('disabling login sync in config or per connection never reads credentials or executes sync SSH', async () => {
  for (const [name, config, options] of [
    ['config', { syncLogin: false }, { syncLogin: true }],
    ['connection', {}, { syncLogin: false }],
    ['default', {}, {}],
  ]) {
    const paths = setup('login-disabled-' + name)
    const { exec, calls } = fakeExecFactory({ probe: PROBE_OK, bootstrap: BOOTSTRAP_OK })
    let reads = 0
    const events = []
    const manager = createManager({
      ...paths, config, exec, tunnel: fakeTunnel(),
      readLocalRecord() { reads++; throw new Error(FAKE_GRANT_TOKEN) },
    })
    const result = await manager.connect('npu-01', { ...options, progress: (event) => events.push(event) })
    assert.equal(result.ok, true)
    assert.equal(result.loginSync.status, 'skipped')
    assert.equal(reads, 0)
    assert.deepEqual(calls.map((call) => call.kind), ['probe', 'state', 'bootstrap'])
    assert.equal(events.some((event) => event.phase === 'login-sync'), false)
    assertNoAccountSecrets([result, events, readFileSync(paths.stateFile, 'utf8')])
  }
})

test('missing Host credential support reports unsupported and connects without sync SSH', async () => {
  const paths = setup('login-unsupported')
  const { exec, calls } = fakeExecFactory({ probe: PROBE_OK, bootstrap: BOOTSTRAP_OK })
  const manager = createManager({ ...paths, exec, tunnel: fakeTunnel() })
  const result = await manager.connect('npu-01', { syncLogin: true })
  assert.equal(result.ok, true)
  assert.equal(result.loginSync.status, 'unsupported')
  assert.deepEqual(calls.map((call) => call.kind), ['probe', 'state', 'bootstrap'])
})

test('bootstrap failure prevents even reading the local account grant', async () => {
  const paths = setup('login-before-bootstrap-failed')
  const { exec, calls } = fakeExecFactory({
    probe: PROBE_OK,
    bootstrap: { code: 1, stdout: 'CANNBOT_ERROR=bootstrap failed\n', stderr: '', timedOut: false },
  })
  let reads = 0
  const tunnel = fakeTunnel()
  const manager = createManager({
    ...paths, exec, tunnel,
    readLocalRecord() { reads++; return FAKE_GRANT },
  })
  const result = await manager.connect('npu-01')
  assert.equal(result.ok, false)
  assert.equal(reads, 0)
  assert.equal(calls.some((call) => call.kind === 'credentials'), false)
  assert.equal(tunnel.entries.size, 0)
})

test('preserved remote credentials and sync failures do not block connection or leak diagnostics', async () => {
  const outcomes = [
    ['remote-preserved', { code: 0, stdout: 'CANNBOT_CREDENTIALS_STATUS=remote-preserved\n', stderr: '' }],
    ['failed', { code: 0, stdout: `CANNBOT_CREDENTIALS_STATUS=failed\n${FAKE_GRANT_TOKEN}`, stderr: FAKE_EXTRA_SECRET }],
    ['failed-exit', { code: 1, stdout: FAKE_GRANT_TOKEN, stderr: FAKE_EXTRA_SECRET }],
    ['failed-throw', () => { throw new Error(FAKE_GRANT_TOKEN) }],
  ]
  for (const [name, outcome] of outcomes) {
    const paths = setup('login-' + name)
    const { exec, calls } = fakeExecFactory({ probe: PROBE_OK, bootstrap: BOOTSTRAP_OK, credentials: outcome })
    const events = []
    const logs = []
    const manager = createManager({
      ...paths, exec, tunnel: fakeTunnel(),
      readLocalRecord: () => FAKE_GRANT,
      logger: (message) => logs.push(message),
    })
    const result = await manager.connect('npu-01', { syncLogin: true, progress: (event) => events.push(event) })
    assert.equal(result.ok, true, name)
    assert.equal(result.loginSync.status, name.startsWith('failed') ? 'failed' : name)
    assert.equal(calls.filter((call) => call.kind === 'credentials').length, 1)
    assert.equal(manager.listServers().find((server) => server.id === 'npu-01').connected, true)
    assertNoAccountSecrets([result, events, logs, readFileSync(paths.stateFile, 'utf8')])
  }
})

test('connect runs probe -> bootstrap -> tunnel and returns a tokenised URL', async () => {
  const paths = setup('happy')
  const { exec, calls } = fakeExecFactory({
    probe: { code: 0, stdout: 'CANNBOT_SSH_OK\n', stderr: '', timedOut: false },
    bootstrap: BOOTSTRAP_OK,
  })
  const tunnel = fakeTunnel()
  const manager = createManager({
    exec,
    tunnel,
    serversFile: paths.serversFile,
    stateFile: paths.stateFile,
    sshConfig: paths.sshConfig,
  })

  const events = []
  const result = await manager.connect('npu-01', { progress: (event) => events.push(event) })

  assert.equal(result.ok, true)
  assert.equal(result.token, 'tok_123')
  assert.equal(result.remotePort, 17634)
  assert.match(result.url, /^http:\/\/127\.0\.0\.1:\d+\/\?token=tok_123$/)
  assert.equal(calls.length, 3, 'probe + state inspection + bootstrap')
  assert.equal(calls[1].kind, 'state')
  assert.ok(calls[2].input > 500, 'bootstrap script is streamed on stdin')
  const phases = events.map((event) => event.phase)
  assert.deepEqual(phases.slice(0, 2), ['probe', 'probe'])
  assert.ok(phases.includes('inspect'), 'remote version inspection is reported')
  assert.ok(events.some((event) => event.message && event.message.includes('直接复用')), 'reuses a compatible remote dsh')
  assert.equal(phases[phases.length - 1], 'ready')
  assert.ok(phases.indexOf('tunnel') > phases.indexOf('bootstrap'), 'tunnel starts after bootstrap')
  assert.ok(
    events.some((event) => event.message && event.message.includes('install CANNBot plugin')),
    `progress messages: ${JSON.stringify(events.map((event) => event.message))}`,
  )

  const state = JSON.parse(readFileSync(paths.stateFile, 'utf8'))
  assert.equal(state.connections['npu-01'].remotePort, 17634)
  assert.equal(state.connections['npu-01'].token, 'tok_123')
  assert.equal(manager.listServers().find((server) => server.id === 'npu-01').connected, true)
})

test('connect fails fast when the ssh probe fails and records the reason', async () => {
  const paths = setup('probe-fail')
  const { exec } = fakeExecFactory({
    probe: { code: 255, stdout: '', stderr: 'Permission denied (publickey).\n', timedOut: false },
    bootstrap: BOOTSTRAP_OK,
  })
  const manager = createManager({
    exec,
    tunnel: fakeTunnel(),
    serversFile: paths.serversFile,
    stateFile: paths.stateFile,
    sshConfig: paths.sshConfig,
  })

  const result = await manager.connect('npu-01')
  assert.equal(result.ok, false)
  assert.match(result.error, /SSH 连接失败/)
  assert.match(result.error, /Permission denied/)

  const servers = manager.listServers()
  const npu01 = servers.find((server) => server.id === 'npu-01')
  assert.equal(npu01.connected, false)
  assert.match(npu01.lastError, /Permission denied/)
  assert.equal(existsSync(paths.stateFile), true)
})

test('connect surfaces bootstrap failures with the remote error marker', async () => {
  const paths = setup('bootstrap-fail')
  const { exec } = fakeExecFactory({
    probe: { code: 0, stdout: 'CANNBOT_SSH_OK\n', stderr: '', timedOut: false },
    bootstrap: {
      code: 1,
      stdout: 'CANNBOT_STEP=5/7 install CANNBot plugin\nCANNBOT_ERROR=plugin install failed (network)\n',
      stderr: '',
      timedOut: false,
    },
  })
  const manager = createManager({
    exec,
    tunnel: fakeTunnel(),
    serversFile: paths.serversFile,
    stateFile: paths.stateFile,
    sshConfig: paths.sshConfig,
  })
  const result = await manager.connect('npu-01')
  assert.equal(result.ok, false)
  assert.match(result.error, /plugin install failed/)
})

test('connect reports tunnel failures and keeps the remote port', async () => {
  const paths = setup('tunnel-fail')
  const { exec } = fakeExecFactory({
    probe: { code: 0, stdout: 'CANNBOT_SSH_OK\n', stderr: '', timedOut: false },
    bootstrap: BOOTSTRAP_OK,
  })
  const manager = createManager({
    exec,
    tunnel: fakeTunnel({ fail: 'bind: Address already in use' }),
    serversFile: paths.serversFile,
    stateFile: paths.stateFile,
    sshConfig: paths.sshConfig,
  })
  const result = await manager.connect('npu-01')
  assert.equal(result.ok, false)
  assert.match(result.error, /Address already in use/)
})

test('disconnect stops the tunnel and keeps the port assignment', async () => {
  const paths = setup('disconnect')
  const { exec } = fakeExecFactory({
    probe: { code: 0, stdout: 'CANNBOT_SSH_OK\n', stderr: '', timedOut: false },
    bootstrap: BOOTSTRAP_OK,
  })
  const tunnel = fakeTunnel()
  const manager = createManager({
    exec,
    tunnel,
    serversFile: paths.serversFile,
    stateFile: paths.stateFile,
    sshConfig: paths.sshConfig,
  })
  await manager.connect('npu-01')
  const before = manager.listServers().find((server) => server.id === 'npu-01')
  manager.disconnect('npu-01')
  const after = manager.listServers().find((server) => server.id === 'npu-01')
  assert.equal(before.connected, true)
  assert.equal(after.connected, false)
  assert.equal(after.localPort, before.localPort)
})

test('inventory merges shared list with ssh config and flags unconfigured hosts', async () => {
  const paths = setup('inventory')
  const manager = createManager({
    exec: async () => ({ code: 0, stdout: '', stderr: '', timedOut: false }),
    tunnel: fakeTunnel(),
    serversFile: paths.serversFile,
    stateFile: paths.stateFile,
    sshConfig: paths.sshConfig,
  })
  const servers = manager.listServers()
  const npu01 = servers.find((server) => server.id === 'npu-01')
  const missing = servers.find((server) => server.id === 'npu-missing')
  assert.equal(npu01.inSshConfig, true)
  assert.equal(npu01.user, 'HwHiAiUser')
  assert.equal(npu01.port, 2222)
  assert.equal(missing.inSshConfig, false)

  const unknown = await manager.connect('nope')
  assert.equal(unknown.ok, false)
  assert.match(unknown.error, /未知服务器/)
})

test('bootstrap asks the runner to stop the ssh stream on terminal markers', async () => {
  const paths = setup('stop-marker')
  const returns = []
  const exec = async (command, args, options) => {
    const joined = args.map(String).join(' ')
    if (joined.includes('CANNBOT_SSH_OK')) return { code: 0, stdout: 'CANNBOT_SSH_OK\n', stderr: '', timedOut: false }
    if (joined.includes('CANNBOT_STATE_DSH')) {
      return { code: 0, stdout: 'CANNBOT_STATE_DSH=none\nCANNBOT_STATE_PLUGIN=none\n', stderr: '', timedOut: false }
    }
    const lines = [
      'CANNBOT_STEP=1/7 detect node',
      'CANNBOT_REMOTE_PORT=17633',
      'CANNBOT_TOKEN=tok_stop',
      'CANNBOT_OK=1',
      'LINE_AFTER_TERMINAL_MARKER',
    ]
    for (const line of lines) returns.push({ line, value: options.onLine(line, false) })
    return { code: 0, stdout: lines.join('\n'), stderr: '', timedOut: false }
  }
  const manager = createManager({
    exec,
    tunnel: fakeTunnel(),
    serversFile: paths.serversFile,
    stateFile: paths.stateFile,
    sshConfig: paths.sshConfig,
  })
  const result = await manager.connect('npu-01')
  assert.equal(result.ok, true)
  assert.equal(returns.find((entry) => entry.line === 'CANNBOT_OK=1').value, 'stop', 'OK marker stops the stream')
  assert.equal(returns.find((entry) => entry.line === 'LINE_AFTER_TERMINAL_MARKER').value, undefined, 'later lines are not classified')
})

test('bootstrap asks the runner to stop on a remote error marker too', async () => {
  const paths = setup('stop-on-error')
  let errorReturn
  const exec = async (command, args, options) => {
    const joined = args.map(String).join(' ')
    if (joined.includes('CANNBOT_SSH_OK')) return { code: 0, stdout: 'CANNBOT_SSH_OK\n', stderr: '', timedOut: false }
    if (joined.includes('CANNBOT_STATE_DSH')) {
      return { code: 0, stdout: 'CANNBOT_STATE_DSH=none\nCANNBOT_STATE_PLUGIN=none\n', stderr: '', timedOut: false }
    }
    errorReturn = options.onLine('CANNBOT_ERROR=plugin install failed', false)
    return { code: 0, stdout: 'CANNBOT_ERROR=plugin install failed\n', stderr: '', timedOut: false }
  }
  const manager = createManager({
    exec,
    tunnel: fakeTunnel(),
    serversFile: paths.serversFile,
    stateFile: paths.stateFile,
    sshConfig: paths.sshConfig,
  })
  const result = await manager.connect('npu-01')
  assert.equal(result.ok, false)
  assert.equal(errorReturn, 'stop')
})

test('router serves state and rejects unknown ids', async () => {
  const paths = setup('router')
  const manager = createManager({
    exec: async () => ({ code: 0, stdout: '', stderr: '', timedOut: false }),
    tunnel: fakeTunnel(),
    serversFile: paths.serversFile,
    stateFile: paths.stateFile,
    sshConfig: paths.sshConfig,
  })
  const handler = createRouter({ manager })

  const okResponse = await handler(new Request(`http://dsh.invalid${ROUTE}/state`))
  assert.equal(okResponse.status, 200)
  const body = await okResponse.json()
  assert.equal(body.ok, true)
  assert.ok(Array.isArray(body.servers))
  assert.equal(body.catalog.entries.length, 1)

  const missingResponse = await handler(new Request(`http://dsh.invalid${ROUTE}/connect`, {
    method: 'POST',
    body: JSON.stringify({ id: 'ghost' }),
  }))
  const missingBody = await missingResponse.json()
  assert.equal(missingBody.ok, false)

  const notFound = await handler(new Request(`http://dsh.invalid${ROUTE}/unknown`))
  assert.equal(notFound.status, 404)
})
