// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { createServer, request } from 'node:http'
import { randomBytes, randomUUID } from 'node:crypto'

const secret = () => randomBytes(32).toString('base64url')
const requestFields = ['accept', 'accept-language', 'accept-encoding', 'content-type', 'content-length', 'if-modified-since', 'if-none-match', 'range', 'if-range', 'x-cannbot-remote-workspace']
const responseFields = ['content-type', 'content-length', 'content-encoding', 'content-disposition', 'content-range', 'accept-ranges', 'etag', 'last-modified', 'content-security-policy', 'x-frame-options']
const wsFields = ['sec-websocket-key', 'sec-websocket-version', 'sec-websocket-protocol', 'sec-websocket-extensions']
const pick = (headers, names) => Object.fromEntries(names.filter(name => headers[name] !== undefined).map(name => [name, headers[name]]))
const local = host => ['localhost', '127.0.0.1', '[::1]'].includes(host)

/** One origin and one short-lived browser ticket per embedded view. Upstream
 * credentials stay in this process. No browser-supplied URL is a proxy target. */
export async function openWebGuest(manager, id, parentOrigin) {
  const parent = new URL(parentOrigin)
  if (!local(parent.hostname) || parent.protocol !== 'http:' || parent.origin !== parentOrigin) throw new Error('请使用本机 HTTP 回环地址打开 DSH Web。')
  const connection = manager.getConnection(id)
  if (!connection?.connected || !connection.token || !Number.isInteger(connection.localPort) || connection.localPort < 1 || connection.localPort > 65535) throw new Error('请先连接服务器。')
  const upstream = new URL('http://127.0.0.1:' + connection.localPort)
  const login = new URL(upstream); login.searchParams.set('token', connection.token)
  const response = await fetch(login, { redirect: 'manual', signal: AbortSignal.timeout(15000) })
  const cookies = response.headers.getSetCookie().map(row => row.split(';', 1)[0]).filter(row => /^[A-Za-z0-9_-]+=[A-Za-z0-9_.-]+$/.test(row))
  await response.body?.cancel()
  if (response.status !== 303 || !cookies.length) throw new Error('远端工作台认证未完成，请重新连接。')

  const view = randomUUID(), host = 'cannbot-' + view + '.localhost'
  const session = secret(), cookieName = '__Host-cannbot-session'
  let ticket = secret(), origin, closed = false, deadline = Date.now() + 45000
  const sockets = new Set()
  const valid = () => {
    try {
      const current = manager.getConnection(id)
      return current?.connected && current.localPort === connection.localPort && current.token === connection.token
    } catch { return false }
  }
  function authenticated(req) {
    if (req.headers.host !== new URL(origin).host || !valid()) return false
    if (!req.url?.startsWith('/') || req.url.startsWith('//') || req.url.includes('\\')) return false
    if (req.headers.origin && req.headers.origin !== origin) return false
    if (req.headers['sec-fetch-site'] && !['none','same-origin'].includes(req.headers['sec-fetch-site'])) return false
    return (req.headers.cookie || '').split(';').some(value => value.trim() === cookieName + '=' + session)
  }
  function forward(req, extra = {}) {
    return request({ hostname: '127.0.0.1', port: connection.localPort, method: req.method, path: req.url, headers: {
      ...pick(req.headers, requestFields), ...extra, host: upstream.host, cookie: cookies.join('; '), ...(req.headers.origin && { origin: upstream.origin }),
    } })
  }
  const server = createServer((req, res) => {
    const fail = (code = 403) => { if (!res.headersSent) res.writeHead(code, { 'cache-control': 'no-store' }); res.end() }
    if (!origin || req.headers.host !== new URL(origin).host || !valid()) return fail()
    if (ticket && req.method === 'GET' && req.url === '/?ticket=' + ticket && Date.now() <= deadline) {
      ticket = null; deadline = Date.now() + 120000
      res.writeHead(303, { location: './', 'cache-control': 'no-store', 'referrer-policy': 'no-referrer',
        'set-cookie': cookieName + '=' + session + '; Path=/; HttpOnly; Secure; SameSite=None; Partitioned' }); res.end(); return
    }
    // The initial iframe redirect is cross-site. Only its root navigation can
    // use the isolated partition cookie without a same-origin fetch initiator.
    const initial = req.method === 'GET' && req.url === '/' && req.headers['sec-fetch-dest'] === 'iframe'
      && !req.headers.origin && (req.headers.cookie || '').split(';').some(value => value.trim() === cookieName + '=' + session)
    if (req.headers['service-worker'] === 'script' || (!initial && !authenticated(req))) return fail()
    deadline = Date.now() + 120000
    const pending = forward(req)
    pending.on('error', () => fail(502))
    res.on('close', () => pending.destroy())
    pending.on('response', incoming => {
      const headers = pick(incoming.headers, responseFields)
      if (incoming.headers.location) {
        let redirect
        try { redirect = new URL(incoming.headers.location, upstream) } catch { incoming.destroy(); fail(502); return }
        if (redirect.origin !== upstream.origin) { incoming.destroy(); fail(502); return }
        headers.location = redirect.pathname + redirect.search + redirect.hash
      }
      const policy = "frame-ancestors " + parent.origin + "; object-src 'none'"
      headers['content-security-policy'] = [headers['content-security-policy'], policy].filter(Boolean).join(', ')
      headers['referrer-policy'] = 'no-referrer'; headers['cache-control'] = 'no-store'
      res.writeHead(incoming.statusCode, headers); incoming.on('error', () => res.destroy()); incoming.pipe(res)
    })
    req.pipe(pending)
  })
  server.on('connection', socket => { sockets.add(socket); socket.on('close', () => sockets.delete(socket)) })
  server.on('upgrade', (req, browser, head) => {
    if (req.headers.origin !== origin || req.headers.upgrade?.toLowerCase() !== 'websocket' || !authenticated(req)) return browser.destroy()
    const pending = forward(req, { ...pick(req.headers, wsFields), connection: 'Upgrade', upgrade: 'websocket' })
    pending.on('error', () => browser.destroy()); pending.on('response', reply => { reply.destroy(); browser.destroy() })
    browser.on('error', () => pending.destroy()); browser.on('close', () => pending.destroy())
    pending.on('upgrade', (reply, remote, unread) => {
      if (browser.destroyed) { remote.destroy(); return }
      const headers = pick(reply.headers, ['sec-websocket-accept','sec-websocket-protocol','sec-websocket-extensions'])
      browser.write(['HTTP/1.1 101 Switching Protocols', 'Connection: Upgrade','Upgrade: websocket', ...Object.entries(headers).map(([k,v]) => k + ': ' + v), '', ''].join('\r\n'))
      if (head.length) remote.write(head); if (unread.length) browser.write(unread)
      remote.on('error', () => browser.destroy()); remote.on('close', () => browser.destroy())
      browser.on('close', () => remote.destroy()); browser.on('data', () => { deadline = Date.now() + 120000 })
      browser.pipe(remote).pipe(browser)
    })
    pending.end()
  })
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve) })
  origin = 'http://' + host + ':' + server.address().port
  function close() {
    if (closed) return
    closed = true; clearInterval(timer); server.close()
    for (const socket of sockets) socket.destroy()
  }
  const timer = setInterval(() => { if (!valid() || Date.now() > deadline) close() }, 10000)
  timer.unref(); server.unref()
  return { view, url: origin + '/?ticket=' + ticket, close, get closed() { return closed } }
}

export function registerWebGuests(ctx, manager) {
  const guests = new Map()
  let disposed = false, opening = 0
  ctx.effect(() => () => { disposed = true; for (const guest of guests.values()) guest.close(); guests.clear() })
  ctx.connection.fetch.register({ path: '/api/cannbot-remote/web-guest', methods: ['POST'], requestBody: 'buffered', async fetch(request) {
    try {
      const body = await request.json()
      for (const [key, guest] of guests) if (guest.closed) guests.delete(key)
      if (body.close) { guests.get(body.close)?.close(); guests.delete(body.close); return Response.json({ ok: true }) }
      if (typeof body.id !== 'string' || !body.id || guests.size + opening >= 12) return Response.json({ ok: false }, { status: 409 })
      opening++
      try {
        const guest = await openWebGuest(manager, body.id, body.parentOrigin)
        if (disposed) { guest.close(); throw new Error() }
        guests.set(guest.view, guest)
        return Response.json({ view: guest.view, url: guest.url }, { headers: { 'cache-control': 'no-store' } })
      } finally { opening-- }
    } catch { return Response.json({ ok: false, message: '无法打开本机内嵌工作台，请检查连接。' }, { status: 502 }) }
  } })
}
