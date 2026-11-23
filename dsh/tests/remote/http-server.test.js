// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

// HTTP/SSE transport tests run the Fetch router behind a test-only Node bridge.
// DSH itself dispatches Fetch requests through connection.fetch, including IPC
// on desktop; these tests do not claim to validate that host registration.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { createServer } from 'node:http'
import { mkdirSync, writeFileSync, rmSync } from 'node:fs'
import { join } from 'node:path'
import { createManager as createProductionManager } from '../../src/remote/manager.js'
import { createRouter, ROUTE } from '../../src/remote/routes.js'
import { createNodeHandler } from './helpers/http-adapter.js'

// Network-free adapter: deployment behavior has its own transfer/lifecycle tests.
function createManager(deps) { return createProductionManager({ deployPackage: async () => ({}), ...deps }) }

const ROOT = join(process.cwd(), '_scratch', 'http')

function fixtures(name) {
  const dir = join(ROOT, name)
  rmSync(dir, { recursive: true, force: true })
  mkdirSync(dir, { recursive: true })
  writeFileSync(join(dir, 'ssh_config'), 'Host npu-01\n  HostName 10.0.0.11\n  User HwHiAiUser\n')
  writeFileSync(join(dir, 'servers.json'), JSON.stringify({ version: 1, servers: [{ alias: 'npu-01', label: '训练机 1' }] }))
  return {
    serversFile: join(dir, 'servers.json'),
    stateFile: join(dir, 'state.json'),
    sshConfig: join(dir, 'ssh_config'),
  }
}

function fakeExec() {
  return async (command, args, options) => {
    const joined = args.map(String).join(' ')
    const isProbe = joined.includes('CANNBOT_SSH_OK')
    const isState = joined.includes('CANNBOT_STATE_DSH')
    const outcome = isProbe
      ? { code: 0, stdout: 'CANNBOT_SSH_OK\n', stderr: '', timedOut: false }
      : isState
        ? {
          code: 0,
          stdout: 'CANNBOT_STATE_DSH=0.1.0-rc.1\nCANNBOT_STATE_PLUGIN=none\n',
          stderr: '',
          timedOut: false,
        }
        : {
          code: 0,
          stdout: [
            'CANNBOT_STEP=1/7 check node',
            'CANNBOT_STEP=7/7 start dsh web on 127.0.0.1:17633',
            'CANNBOT_REMOTE_PORT=17633',
            'CANNBOT_WEB_LOG=/home/u/.dsh/web-17633.log',
            'CANNBOT_TOKEN=http_tok',
            'CANNBOT_DSH_VERSION=0.2.2-rc.1',
            'CANNBOT_PLUGIN_VERSION=1.0.0-alpha.1',
            'CANNBOT_OK=1',
          ].join('\n'),
          stderr: '',
          timedOut: false,
        }
    if (options && typeof options.onLine === 'function') {
      for (const line of String(outcome.stdout).split('\n')) if (line) options.onLine(line, false)
    }
    return outcome
  }
}

function fakeTunnel() {
  const entries = new Map()
  return {
    entries,
    status: (id) => (entries.has(id) ? entries.get(id) : null),
    list: () => [...entries.values()],
    ensure: async (input) => {
      entries.set(input.id, { localPort: input.localPort, remotePort: input.remotePort, pid: 1, startedAt: Date.now() })
      return { started: true, url: `http://127.0.0.1:${input.localPort}/`, localPort: input.localPort, remotePort: input.remotePort }
    },
    stop: (id) => entries.delete(id),
    stopAll: () => entries.clear(),
  }
}

async function startServer(handler) {
  const server = createServer(createNodeHandler(handler))
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve))
  return server
}

function buildManager(name) {
  const paths = fixtures(name)
  return createManager({
    exec: fakeExec(),
    tunnel: fakeTunnel(),
    serversFile: paths.serversFile,
    stateFile: paths.stateFile,
    sshConfig: paths.sshConfig,
  })
}

test('GET /state returns servers over real HTTP', async () => {
  const manager = buildManager('state')
  const server = await startServer(createRouter({ manager }))
  try {
    const response = await fetch(`http://127.0.0.1:${server.address().port}${ROUTE}/state`)
    assert.equal(response.status, 200)
    assert.match(response.headers.get('content-type'), /application\/json/)
    const body = await response.json()
    assert.equal(body.ok, true)
    assert.equal(body.servers.length, 1)
    assert.equal(body.servers[0].alias, 'npu-01')
    assert.equal(body.catalog.entries[0].package, '@cannbot-plugin/cannbot-dsh')
  } finally {
    server.close()
  }
})

test('POST /connect performs the full flow over HTTP', async () => {
  const manager = buildManager('connect')
  const server = await startServer(createRouter({ manager }))
  try {
    const response = await fetch(`http://127.0.0.1:${server.address().port}${ROUTE}/connect`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ id: 'npu-01' }),
    })
    const body = await response.json()
    assert.equal(body.ok, true)
    assert.equal(body.token, 'http_tok')
    assert.match(body.url, /\?token=http_tok$/)
  } finally {
    server.close()
  }
})

test('GET /connect-stream streams SSE progress and a done event', async () => {
  const manager = buildManager('stream')
  const server = await startServer(createRouter({ manager }))
  try {
    const response = await fetch(`http://127.0.0.1:${server.address().port}${ROUTE}/connect-stream?id=npu-01`)
    assert.equal(response.status, 200)
    assert.match(response.headers.get('content-type'), /text\/event-stream/)

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let text = ''
    const deadline = Date.now() + 10_000
    while (Date.now() < deadline) {
      const { done, value } = await reader.read()
      if (done) break
      text += decoder.decode(value, { stream: true })
      if (text.includes('"phase":"done"')) break
    }
    await reader.cancel().catch(() => {})

    const events = text
      .split('\n\n')
      .map((block) => block.replace(/^data: /, '').trim())
      .filter(Boolean)
      .map((json) => JSON.parse(json))
    assert.ok(events.length >= 4, `expected several events, got ${events.length}`)
    assert.equal(events[0].phase, 'probe')
    assert.ok(events.some((event) => event.phase === 'bootstrap'))
    const done = events.find((event) => event.phase === 'done')
    assert.ok(done, 'done event present')
    assert.equal(done.ok, true)
    assert.match(done.url, /token=http_tok/)
  } finally {
    server.close()
  }
})

test('GET /diagnose returns captured remote output', async () => {
  const manager = createManager({
    exec: async (command, args) => ({
      code: 0,
      stdout: 'CANNBOT_DIAG_BEGIN\nLinux 5.15.0 x86_64\nnode: v24.22.2\ndsh: 0.2.2-rc.1\nnpu-smi: ok\nCANNBOT_DIAG_END\n',
      stderr: '',
      timedOut: false,
    }),
    tunnel: fakeTunnel(),
    ...fixtures('diagnose'),
  })
  const server = await startServer(createRouter({ manager }))
  try {
    const response = await fetch(`http://127.0.0.1:${server.address().port}${ROUTE}/diagnose?id=npu-01`)
    const body = await response.json()
    assert.equal(body.ok, true)
    assert.match(body.text, /node: v24\.22\.2/)
    assert.match(body.text, /npu-smi: ok/)
  } finally {
    server.close()
  }
})

test('unknown routes 404 and unknown ids fail cleanly', async () => {
  const manager = buildManager('errors')
  const server = await startServer(createRouter({ manager }))
  try {
    const base = `http://127.0.0.1:${server.address().port}${ROUTE}`
    assert.equal((await fetch(`${base}/nope`)).status, 404)

    const missing = await fetch(`${base}/connect`, { method: 'POST', body: JSON.stringify({ id: 'ghost' }) })
    const missingBody = await missing.json()
    assert.equal(missingBody.ok, false)

    const noId = await fetch(`${base}/connect-stream`)
    assert.equal(noId.status, 400)
  } finally {
    server.close()
  }
})
