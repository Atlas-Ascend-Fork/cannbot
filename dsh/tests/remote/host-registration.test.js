// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

// Exercise production registration with DSH's Fetch-route API shape. The Node
// HTTP test bridge is deliberately not involved in this contract test.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { createRouter, registerRoutes, ROUTE } from '../../src/remote/routes.js'

function captureRoutes(manager) {
  const registered = []
  const ctx = { connection: { fetch: { register(route) { registered.push(route) } } } }
  registerRoutes(ctx, createRouter({ manager }))
  return registered
}

test('password route rejects stale challenges and never echoes submitted secrets', async () => {
  let received
  const routes = captureRoutes({ submitPassword(...args) { received = args; return args[2] === 'current' } })
  const route = routes.find(item => item.path.endsWith('/password'))
  for (const challengeId of ['stale', 'current']) {
    const response = await route.fetch(new Request(`http://local${ROUTE}/password`, { method: 'POST', body: JSON.stringify({ id: 'dev', requestId: 'attempt', challengeId, password: 'fixture-secret' }) }))
    assert.equal(response.status, challengeId === 'current' ? 200 : 409)
    assert.equal((await response.text()).includes('fixture-secret'), false)
    assert.deepEqual(received, ['dev', 'attempt', challengeId, 'fixture-secret'])
  }
})

test('cancellation fences a delayed stream so it cannot start a new connection', async () => {
  let connects = 0
  const routes = captureRoutes({ connect() { connects++; throw new Error('must not connect') } })
  const requestId = '12345678-1234-1234-1234-123456789abc'
  const cancelled = await routes.find(route => route.path.endsWith('/cancel-connect')).fetch(new Request(`http://local${ROUTE}/cancel-connect`, {
    method: 'POST', body: JSON.stringify({ id: 'npu-01', requestId }),
  }))
  assert.equal(cancelled.status, 200)
  const late = await routes.find(route => route.path.endsWith('/connect-stream')).fetch(new Request(`http://local${ROUTE}/connect-stream?id=npu-01&requestId=${requestId}`))
  assert.equal(late.status, 409); assert.equal(connects, 0)
})

test('host registers exact authenticated Fetch routes with supported methods and buffered bodies', () => {
  const routes = captureRoutes({})
  assert.equal(ROUTE, '/api/cannbot-remote')
  assert.deepEqual(routes.map(({ path, methods }) => [path, methods]), [
    [`${ROUTE}/health`, ['GET']], [`${ROUTE}/state`, ['GET']], [`${ROUTE}/servers`, ['GET', 'POST']], [`${ROUTE}/servers/label`, ['POST']], [`${ROUTE}/servers/order`, ['POST']], [`${ROUTE}/servers/remove`, ['POST']],
    [`${ROUTE}/catalog`, ['GET']], [`${ROUTE}/diagnose`, ['GET']], [`${ROUTE}/disconnect`, ['POST']],
    [`${ROUTE}/connect`, ['POST']], [`${ROUTE}/connect-stream`, ['GET']], [`${ROUTE}/cancel-connect`, ['POST']], [`${ROUTE}/password`, ['POST']], [`${ROUTE}/log`, ['GET']],
  ])
  for (const route of routes) {
    assert.equal(route.requestBody, 'buffered')
    assert.equal(typeof route.fetch, 'function')
    assert.equal(Object.hasOwn(route, 'handler'), false, 'Fetch registration must not use the Node HTTP handler property')
  }
})

test('registered Fetch handlers return JSON state and read a POST body without Node response objects', async () => {
  const calls = []
  const manager = {
    config: { remotePort: 17633, profile: 'web' },
    listServers: () => [{ id: 'npu-01', label: '训练机' }],
    catalog: () => ({ entries: [] }),
    connect: async (id) => { calls.push(id); return { ok: true, url: 'http://localhost:17633/' } },
  }
  const routes = captureRoutes(manager)
  const state = await routes.find((route) => route.path.endsWith('/state')).fetch(new Request(`http://dsh.invalid${ROUTE}/state`))
  assert.ok(state instanceof Response)
  assert.equal(state.status, 200)
  assert.equal((await state.json()).servers[0].label, '训练机')

  const response = await routes.find((route) => route.path.endsWith('/connect')).fetch(new Request(`http://dsh.invalid${ROUTE}/connect`, {
    method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ id: 'npu-01' }),
  }))
  assert.deepEqual(calls, ['npu-01'])
  assert.equal((await response.json()).ok, true)
})

test('registered POST connection requires explicit login-sync consent and defaults off', async () => {
  for (const [body, expected] of [
    [{ id: 'npu-01', syncLogin: false }, false],
    [{ id: 'npu-01' }, false],
    [{ id: 'npu-01', syncLogin: true }, true],
  ]) {
    const calls = []
    const routes = captureRoutes({ connect: async (id, options) => { calls.push({ id, options }); return { ok: true } } })
    const route = routes.find((entry) => entry.path === `${ROUTE}/connect`)
    const response = await route.fetch(new Request(`http://dsh.invalid${route.path}`, { method: 'POST', body: JSON.stringify(body) }))
    assert.equal((await response.json()).ok, true)
    assert.deepEqual(calls, [{ id: 'npu-01', options: { syncLogin: expected } }])
  }
})

test('registered SSE connection requires syncLogin=1 and defaults off', async () => {
  for (const [query, expected] of [['&syncLogin=0', false], ['', false], ['&syncLogin=1', true]]) {
    const calls = []
    const routes = captureRoutes({
      connect: async (id, options) => {
        calls.push({ id, syncLogin: options.syncLogin })
        options.progress({ phase: 'probe', message: '检查连接' })
        return { ok: true, loginSync: { status: options.syncLogin ? 'unsupported' : 'skipped' } }
      },
    })
    const route = routes.find((entry) => entry.path === `${ROUTE}/connect-stream`)
    const response = await route.fetch(new Request(`http://dsh.invalid${route.path}?id=npu-01${query}`))
    const events = (await response.text()).trim().split('\n\n').map((event) => JSON.parse(event.replace(/^data: /, '')))
    assert.deepEqual(calls, [{ id: 'npu-01', syncLogin: expected }])
    assert.equal(events.at(-1).phase, 'done')
    assert.equal(events.at(-1).ok, true)
    assert.equal(events.at(-1).loginSync.status, expected ? 'unsupported' : 'skipped')
  }
})

test('registered SSE handler streams progress before the connection completes', { timeout: 3000 }, async () => {
  const completion = Promise.withResolvers()
  const routes = captureRoutes({
    connect(_id, { progress }) {
      progress({ phase: 'probe', message: '检查 SSH 连接' })
      return completion.promise
    },
  })
  const response = await routes.find((route) => route.path.endsWith('/connect-stream')).fetch(new Request(`http://dsh.invalid${ROUTE}/connect-stream?id=npu-01`))
  const reader = response.body.getReader()
  try {
    assert.match(response.headers.get('content-type'), /text\/event-stream/)
    const first = await reader.read()
    assert.equal(first.done, false)
    assert.match(new TextDecoder().decode(first.value), /检查 SSH 连接/)
    completion.resolve({ ok: true, url: 'http://localhost:17633/' })
    const done = await reader.read()
    assert.match(new TextDecoder().decode(done.value), /"phase":"done"/)
    assert.equal((await reader.read()).done, true)
  } finally {
    completion.resolve({ ok: false })
    await reader.cancel()
  }
})

test('cancelling a registered SSE response releases its heartbeat before the task completes', async (t) => {
  const completion = Promise.withResolvers()
  const originalSetInterval = globalThis.setInterval
  const originalClearInterval = globalThis.clearInterval
  let heartbeat
  let released = false
  t.mock.method(globalThis, 'setInterval', (...args) => {
    heartbeat = originalSetInterval(...args)
    return heartbeat
  })
  t.mock.method(globalThis, 'clearInterval', (timer) => {
    if (timer === heartbeat) released = true
    return originalClearInterval(timer)
  })
  const routes = captureRoutes({ connect: () => completion.promise })
  try {
    const response = await routes.find((route) => route.path.endsWith('/connect-stream')).fetch(new Request(`http://dsh.invalid${ROUTE}/connect-stream?id=npu-01`))
    assert.ok(heartbeat)
    await response.body.cancel()
    assert.equal(released, true, 'SSE cancellation must clear the heartbeat immediately')
  } finally {
    completion.resolve({ ok: false })
    originalClearInterval(heartbeat)
  }
})
