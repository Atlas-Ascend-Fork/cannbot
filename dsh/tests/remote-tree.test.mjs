// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import test from 'node:test'
import assert from 'node:assert/strict'
import { operateRemoteTree, readRemoteTree, registerRemoteTree } from '../plugin/backend/remote-tree.ts'

const record = { connected: true, localPort: 17633, url: 'http://127.0.0.1:17633/?token=test-secret', token: 'test-secret' }
const manager = { getConnection: id => id === 'server' ? record : null }

test('directory reads recover while a newly connected remote Host is becoming ready', async t => {
  let route, handshakes = 0
  registerRemoteTree({ inject(_keys, callback) { callback({ connection: { fetch: { register(value) { route = value } } } }) } }, manager)
  t.mock.method(globalThis, 'fetch', async url => {
    if (new URL(url).pathname === '/') {
      if (++handshakes === 1) throw new Error('starting')
      return new Response(null, { status: 303, headers: { 'set-cookie': 'dsh=COOKIE' } })
    }
    return Response.json({ path: '/', entries: [], crumbs: [], truncated: false })
  })
  const response = await route.fetch(new Request('http://local/api/cannbot-remote/tree?id=server', { method: 'POST', body: JSON.stringify({ action: 'browse-directory', path: '' }) }))
  assert.equal(response.status, 200); assert.equal((await response.json()).path, '/'); assert.equal(handshakes, 2)
})
test('remote tree exchanges the launch token only with the owned tunnel and returns only CANNBot records', async () => {
  const calls = []
  const fetcher = async (url, options) => {
    calls.push({ url: String(url), options })
    if (calls.length === 1) return new Response(null, { status: 303, headers: { 'set-cookie': 'dsh-session-cookie=v1.FAKE.SIGNED; HttpOnly; SameSite=Strict', location: './' } })
    return Response.json({ mode: 'cannbot', token: 'never-return', workspaces: [{ workspaceId: 'w', path: '/tmp/project', title: '项目', pluginId: 'plugin-a', secret: 'no' }], sessions: [
      { sessionId: 's', workspaceId: 'w', pluginId: 'plugin-a', title: '会话', pinned: true, pinOrder: 2, blank: false, running: true, updatedAt: '2026-11-13T03:00:00.000Z' },
      { sessionId: 'other', workspaceId: 'unknown', pluginId: 'plugin-a' },
      { sessionId: 'wrong-plugin', workspaceId: 'w', pluginId: 'plugin-b' },
      { sessionId: 'archived', workspaceId: 'w', pluginId: 'plugin-a', archived: true },
      { sessionId: 'ungrouped', workspaceId: 'deleted', pluginId: 'plugin-a', ungrouped: true, pinned: true, pinOrder: 0, blank: true, running: false },
    ] })
  }
  const tree = await readRemoteTree(manager, 'server', fetcher)
  assert.equal(calls[0].url, record.url)
  assert.equal(calls[0].options.redirect, 'manual')
  assert.equal(calls[1].url, 'http://127.0.0.1:17633/api/cannbot-dsh/workspaces')
  assert.equal(calls[1].options.headers.cookie, 'dsh-session-cookie=v1.FAKE.SIGNED')
  assert.equal(calls[1].options.redirect, 'error')
  assert.deepEqual(tree.sessions.map(item => item.sessionId), ['s', 'archived', 'ungrouped'])
  assert.deepEqual(tree.workspaces[0].sessionIds, ['s', 'archived'])
  assert.equal(tree.sessions[0].pinned, true); assert.equal(tree.sessions[0].archived, false)
  assert.equal(tree.sessions[1].archived, true); assert.equal(tree.sessions[2].ungrouped, true)
  assert.equal(tree.sessions[0].pinOrder, 2); assert.equal(tree.sessions[2].pinOrder, 0)
  assert.equal(tree.sessions[0].blank, false); assert.equal(tree.sessions[0].running, true)
  assert.equal(tree.sessions[0].updatedAt, '2026-11-13T03:00:00.000Z')
  assert.equal(tree.sessions[2].blank, true); assert.equal(tree.sessions[2].running, false)
  assert.equal(Object.hasOwn(tree.sessions[1], 'blank'), false); assert.equal(Object.hasOwn(tree.sessions[1], 'running'), false)
  assert.deepEqual(tree.sessions.filter(item => item.pinned).sort((a, b) => a.pinOrder - b.pinOrder).map(item => item.sessionId), ['ungrouped', 's'])
  assert(!JSON.stringify(tree).includes('secret'))
  assert(!JSON.stringify(tree).includes('cookie'))
})

test('inactive, non-loopback, mismatched and credential-bearing endpoints never receive a network call', async () => {
  for (const item of [null, { ...record, connected: false }, { ...record, url: 'http://example.com:17633/?token=x' }, { ...record, url: 'http://127.0.0.1:17634/' }, { ...record, url: 'http://user:pass@127.0.0.1:17633/' }]) {
    await assert.rejects(readRemoteTree({ getConnection: () => item }, 'server', () => assert.fail('unsafe endpoint fetched')), /无法读取远端/)
  }
})

test('pin order accepts only safe nonnegative native positions on pinned sessions', async () => {
  let calls = 0
  const invalid = [-1, 1.5, '2', Number.MAX_SAFE_INTEGER + 1, null]
  const tree = await readRemoteTree(manager, 'server', async () => ++calls === 1
    ? new Response(null, { status: 303, headers: { 'set-cookie': 'dsh=COOKIE' } })
    : Response.json({ mode: 'cannbot', workspaces: [{ workspaceId: 'w', path: '/tmp/project', pluginId: 'p' }], sessions: [
      ...invalid.map((pinOrder, index) => ({ sessionId: 'bad-' + index, workspaceId: 'w', pluginId: 'p', pinned: true, pinOrder })),
      { sessionId: 'not-pinned', workspaceId: 'w', pluginId: 'p', pinned: false, pinOrder: 0 },
      { sessionId: 'invalid-status', workspaceId: 'w', pluginId: 'p', blank: 'true', running: 1 },
      { sessionId: 'valid', workspaceId: 'w', pluginId: 'p', pinned: true, pinOrder: 0 },
    ] }))
  for (const session of tree.sessions.filter(item => item.sessionId !== 'valid')) assert.equal(Object.hasOwn(session, 'pinOrder'), false)
  assert.equal(tree.sessions.find(item => item.sessionId === 'valid').pinOrder, 0)
  const invalidStatus = tree.sessions.find(item => item.sessionId === 'invalid-status')
  assert.equal(Object.hasOwn(invalidStatus, 'blank'), false); assert.equal(Object.hasOwn(invalidStatus, 'running'), false)
})

test('remote errors and redirects never expose authentication material or exception addresses', async () => {
  await assert.rejects(readRemoteTree(manager, 'server', async () => { throw Error(record.url) }), error => !error.message.includes('test-secret'))
  await assert.rejects(readRemoteTree(manager, 'server', async () => new Response(null, { status: 302, headers: { location: 'https://other.example/', 'set-cookie': 'x=y' } })), /无法读取远端/)
  let count = 0
  await assert.rejects(readRemoteTree(manager, 'server', async () => ++count === 1
    ? new Response(null, { status: 303, headers: { 'set-cookie': 'x=y' } })
    : Response.json({ mode: 'dsh', workspaces: [], sessions: [] })), /无法读取远端/)
})

test('tree route rejects a missing server ID without probing a server', async () => {
  let route
  registerRemoteTree({ inject(_keys, callback) { callback({ connection: { fetch: { register(value) { route = value } } } }) } }, manager)
  assert.equal(route.path, '/api/cannbot-remote/tree')
  assert.deepEqual(route.methods, ['GET', 'POST'])
  const response = await route.fetch(new Request('http://local/api/cannbot-remote/tree'))
  assert.equal(response.status, 400)
})

test('remote mutations use only the owned tunnel, fixed endpoint, fixed payload and projected success', async () => {
  const calls = []
  const fetcher = async (url, options) => {
    calls.push({ url: String(url), options })
    if (calls.length === 1) return new Response(null, { status: 303, headers: { 'set-cookie': 'dsh=COOKIE' } })
    return Response.json({ ok: true, token: 'PRIVATE', sessionId: 'unrequested', secret: 'NO' })
  }
  const result = await operateRemoteTree(manager, 'server', { action: 'rename-workspace', workspaceId: 'w', title: 'Title', url: 'https://evil.example', token: 'NO', headers: { cookie: 'NO' } }, fetcher)
  assert.deepEqual(result, { ok: true })
  assert.equal(calls.length, 2)
  assert.equal(calls[1].url, 'http://127.0.0.1:17633/api/cannbot-dsh/workspaces')
  assert.equal(calls[1].options.method, 'POST'); assert.equal(calls[1].options.redirect, 'error')
  assert.deepEqual(JSON.parse(calls[1].options.body), { action: 'rename-workspace', workspaceId: 'w', title: 'Title' })
  assert.deepEqual(calls[1].options.headers, { cookie: 'dsh=COOKIE', 'content-type': 'application/json' })
})

test('mutations reject unknown actions and inactive endpoints before any network access', async () => {
  const noFetch = () => assert.fail('must not fetch')
  for (const body of [{ action: 'create', path: '/tmp', pluginId: 'x' }, { action: 'delete-file', path: '/' }, { action: 'archive-session', sessionId: 's', stopActivity: 'true' }, { action: 'rename-session', sessionId: 's', title: '\n' }]) {
    await assert.rejects(operateRemoteTree(manager, 'server', body, noFetch), error => error.result.status === 400)
  }
  for (const connection of [null, { ...record, connected: false }, { ...record, url: 'https://example.org/' }, { ...record, url: 'http://127.0.0.1:1/' }]) await assert.rejects(operateRemoteTree({ getConnection: () => connection }, 'server', { action: 'pin-session', sessionId: 's' }, noFetch))
})

test('remote archive returns safe confirmation data and never retries or auto-stops a running session', async () => {
  const calls = []
  await assert.rejects(operateRemoteTree(manager, 'server', { action: 'archive-session', sessionId: 's' }, async (_url, options) => {
    calls.push(options)
    return calls.length === 1 ? new Response(null, { status: 303, headers: { 'set-cookie': 'dsh=COOKIE' } })
      : Response.json({ error: 'workspace/session-active', message: record.url, details: { token: 'SECRET' }, activity: [{ kind: 'job', secret: 'NO', items: [{ id: 'j', label: 'build http://127.0.0.1/?token=SECRET', token: 'NO' }] }] }, { status: 409 })
  }), error => {
    assert.equal(error.result.status, 409)
    assert.equal(error.result.body.error, 'workspace/session-active')
    assert.equal(error.result.body.activity[0].items[0].id, 'j')
    assert(!JSON.stringify(error.result).includes('SECRET')); assert(!JSON.stringify(error.result).includes('cookie'))
    return true
  })
  assert.equal(calls.length, 2)
  assert.deepEqual(JSON.parse(calls[1].body), { action: 'archive-session', sessionId: 's' })
})

test('failed mutations do not retry after an uncertain commit or expose response details', async () => {
  let calls = 0
  await assert.rejects(operateRemoteTree(manager, 'server', { action: 'remove-workspace', workspaceId: 'w' }, async () => {
    if (++calls === 1) return new Response(null, { status: 303, headers: { 'set-cookie': 'dsh=COOKIE' } })
    throw new Error(record.url)
  }), error => error.result.status === 502 && !error.message.includes('test-secret'))
  assert.equal(calls, 2)
})

test('fork returns only verified child identity and forwards explicit migration choice', async () => {
  for (const allowMigration of [undefined, false, true]) {
    let calls = 0
    const result = await operateRemoteTree(manager, 'server', { action: 'fork-session', sessionId: 'parent', ...(allowMigration === undefined ? {} : { allowMigration }) }, async (_url, options) => {
      if (++calls === 1) return new Response(null, { status: 303, headers: { 'set-cookie': 'dsh=COOKIE' } })
      assert.deepEqual(JSON.parse(options.body), { action: 'fork-session', sessionId: 'parent', ...(allowMigration === undefined ? {} : { allowMigration }) })
      return Response.json({ ok: true, sessionId: 'child', url: record.url, token: 'NO' })
    })
    assert.deepEqual(result, { ok: true, sessionId: 'child' })
  }
})

test('mutation route refuses malformed or unsupported JSON without probing a server', async () => {
  let route
  registerRemoteTree({ inject(_keys, callback) { callback({ connection: { fetch: { register(value) { route = value } } } }) } }, { getConnection() { assert.fail('invalid request must not probe') } })
  for (const body of ['not-json', JSON.stringify({ action: 'arbitrary' }), ' '.repeat(16385)]) {
    const response = await route.fetch(new Request('http://local/api/cannbot-remote/tree?id=server', { method: 'POST', body }))
    assert.equal(response.status, 400)
    assert.equal((await response.json()).error, 'invalid-request')
  }
})

test('remote creation projects directory requests through the same authenticated tunnel', async t => {
  let route
  registerRemoteTree({ inject(_keys, callback) { callback({ connection: { fetch: { register(value) { route = value } } } }) } }, manager)
  const calls = []
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    calls.push({ url: String(url), options })
    if (calls.length % 2) return new Response(null, { status: 303, headers: { 'set-cookie': 'dsh=COOKIE' } })
    return Response.json({ workspace: { workspaceId: 'new' } })
  })
  const body = { action: 'create-folder', parent: '/', name: 'fresh', pluginId: 'general', requestId: '12345678-1234-1234-1234-123456789abc' }
  const response = await route.fetch(new Request('http://local/api/cannbot-remote/tree?id=server', { method: 'POST', body: JSON.stringify({ ...body, url: 'https://outside.invalid', token: 'DO_NOT_FORWARD' }) }))
  assert.equal(response.status, 200)
  assert.equal(calls[1].url, 'http://127.0.0.1:17633/api/cannbot-dsh/workspaces')
  assert.deepEqual(JSON.parse(calls[1].options.body), body)
  assert.equal(calls[1].options.headers['x-cannbot-remote-workspace'], '1')
  assert.equal(calls[1].options.headers.cookie, 'dsh=COOKIE')
  assert.equal(calls.length, 2)
})
