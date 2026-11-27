// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

// Fetch surface for the host half. DSH's connection.fetch service serves these
// authenticated /api routes over both desktop IPC and web transport.
//
// The client half talks to these routes with plain fetch/EventSource, which
// avoids the typert codegen that a browser bundle cannot run at build time.
import { ServerInputError } from './add-server.js'

export const ROUTE = '/api/cannbot-remote'

export function registerRoutes(ctx, handler) {
  const routes = [
    ['health', 'GET'], ['state', 'GET'], ['servers', 'GET', 'POST'], ['servers/label', 'POST'], ['servers/order', 'POST'], ['servers/remove', 'POST'],
    ['catalog', 'GET'], ['diagnose', 'GET'], ['disconnect', 'POST'],
    ['connect', 'POST'], ['connect-stream', 'GET'], ['cancel-connect', 'POST'], ['password', 'POST'], ['log', 'GET'],
  ]
  for (const [path, ...methods] of routes) {
    // Registration is owned by the Cordis context, as with official CANNBot
    // content routes. connection.fetch expects Fetch Request/Response objects.
    ctx.connection.fetch.register({
      path: `${ROUTE}/${path}`,
      methods,
      requestBody: 'buffered',
      fetch: handler,
    })
  }
}

const JSON_HEADERS = { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' }

function json(body, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: JSON_HEADERS })
}

async function readJson(request) {
  try {
    const text = await request.text()
    return text ? JSON.parse(text) : {}
  } catch {
    return {}
  }
}

function sseResponse(handler) {
  const encoder = new TextEncoder()
  let closed = false
  let heartbeat
  const stream = new ReadableStream({
    start(controller) {
      const send = (event) => {
        if (closed) return
        try {
          controller.enqueue(encoder.encode(`data: ${JSON.stringify(event)}\n\n`))
        } catch {
          closed = true
          clearInterval(heartbeat)
        }
      }
      heartbeat = setInterval(() => send({ phase: 'heartbeat', at: Date.now() }), 15_000)
      const finish = () => {
        clearInterval(heartbeat)
        if (closed) return
        closed = true
        try { controller.close() } catch { /* already closed */ }
      }
      handler(send, finish).catch((error) => {
        send({ phase: 'error', level: 'error', message: String(error && error.message ? error.message : error) })
        finish()
      })
    },
    cancel() {
      closed = true
      clearInterval(heartbeat)
    },
  })
  return new Response(stream, {
    headers: {
      'content-type': 'text/event-stream; charset=utf-8',
      'cache-control': 'no-store',
      connection: 'keep-alive',
    },
  })
}

/**
 * @param {{manager: ReturnType<typeof import('./manager.js').createManager>, logger?: (m: string) => void}} deps
 */
export function createRouter({ manager, logger = () => {} }) {
  const inflight = new Map()
  const attempts = new Map(), cancelledRequests = new Set()

  return async function handler(request) {
    const url = new URL(request.url, 'http://dsh.invalid')
    const path = url.pathname
    const method = request.method.toUpperCase()

    try {
      if (path === `${ROUTE}/health`) {
        return json({ ok: true, at: Date.now() })
      }

      if ([`${ROUTE}/servers`, `${ROUTE}/servers/label`, `${ROUTE}/servers/order`, `${ROUTE}/servers/remove`].includes(path) && method === 'POST') {
        const text = await request.text()
        if (text.length > (path.endsWith('/order') ? 65536 : 8192)) return json({ ok: false, error: '服务器输入过长，请缩短后重试。' }, 400)
        let body
        try { body = JSON.parse(text) } catch { return json({ ok: false, error: '服务器输入格式无效。' }, 400) }
        if (path.endsWith('/order')) return json({ ok: true, ...await manager.reorderServers(body) })
        if (path.endsWith('/remove')) return json({ ok: true, ...await manager.removeServer(body) })
        return json({ ok: true, server: await (path.endsWith('/label') ? manager.renameServer(body) : manager.addServer(body)) })
      }

      if ((path === `${ROUTE}/state` || path === `${ROUTE}/servers`) && method === 'GET') {
        return json({
          ok: true,
          servers: manager.listServers(),
          catalog: manager.catalog(),
          sshConfigPath: manager.sshConfigPath,
          serversPath: manager.serversPath,
          config: {
            remotePort: manager.config.remotePort,
            dshVersion: manager.config.dshVersion,
            pluginVersion: manager.config.pluginVersion,
            profile: manager.config.profile,
            syncLogin: manager.config.syncLogin !== false,
          },
        })
      }

      if (path === `${ROUTE}/catalog`) {
        return json({ ok: true, catalog: manager.catalog() })
      }

      if (path === `${ROUTE}/diagnose`) {
        const id = url.searchParams.get('id') || ''
        if (!id) return json({ ok: false, error: 'missing id' }, 400)
        return json(await manager.diagnose(id))
      }

      if (path === `${ROUTE}/disconnect` && method === 'POST') {
        const body = await readJson(request)
        const id = body.id || url.searchParams.get('id') || ''
        if (!id) return json({ ok: false, error: 'missing id' }, 400)
        return json({ ok: true, ...manager.disconnect(id) })
      }

      if (path === `${ROUTE}/password` && method === 'POST') {
        const text = await request.text()
        if (text.length > 8192) return json({ ok: false, error: '密码输入无效。' }, 400)
        let body
        try { body = JSON.parse(text) } catch { return json({ ok: false, error: '密码输入无效。' }, 400) }
        const { id, requestId, challengeId, password } = body
        if (typeof id !== 'string' || typeof requestId !== 'string' || typeof challengeId !== 'string' || typeof password !== 'string') return json({ ok: false, error: '密码输入无效。' }, 400)
        if (!manager.submitPassword(id, requestId, challengeId, password)) return json({ ok: false, error: '密码请求已失效或输入无效，请重新连接。' }, 409)
        return json({ ok: true })
      }

      if (path === `${ROUTE}/cancel-connect` && method === 'POST') {
        const { id, requestId } = await readJson(request)
        if (typeof id !== 'string' || !id || typeof requestId !== 'string' || !/^[\da-f-]{36}$/i.test(requestId)) return json({ ok: false, error: 'invalid request' }, 400)
        cancelledRequests.add(requestId)
        if (cancelledRequests.size > 100) cancelledRequests.delete(cancelledRequests.values().next().value)
        if (attempts.get(id) === requestId) {
          await manager.cancelConnect(id, requestId)
          await inflight.get(id)?.catch(() => {})
          if (attempts.get(id) === requestId) manager.disconnect(id)
        }
        return json({ ok: true })
      }

      if (path === `${ROUTE}/connect` && method === 'POST') {
        const body = await readJson(request)
        const id = body.id || ''
        if (!id) return json({ ok: false, error: 'missing id' }, 400)
        if (inflight.has(id)) return json({ ok: false, error: '该服务器正在连接中' }, 409)
        const task = manager.connect(id, { syncLogin: body.syncLogin === true })
        inflight.set(id, task)
        try {
          return json(await task)
        } finally {
          inflight.delete(id)
        }
      }

      if (path === `${ROUTE}/connect-stream`) {
        const id = url.searchParams.get('id') || ''
        const requestId = url.searchParams.get('requestId') || ''
        if (!id) return json({ ok: false, error: 'missing id' }, 400)
        if (cancelledRequests.has(requestId)) return json({ ok: false, error: '本次服务器连接已取消。' }, 409)
        return sseResponse(async (send, finish) => {
          if (inflight.has(id)) {
            send({ phase: 'error', level: 'error', message: '该服务器正在连接中' })
            finish()
            return
          }
          attempts.set(id, requestId)
          const task = manager.connect(id, { requestId, passwordPrompt: /^[\da-f-]{36}$/i.test(requestId), syncLogin: url.searchParams.get('syncLogin') === '1', progress: (event) => send(event) })
          inflight.set(id, task)
          try {
            const result = await task
            send({ phase: 'done', ...result })
          } catch (error) {
            send({ phase: 'error', level: 'error', message: String(error && error.message ? error.message : error) })
          } finally {
            inflight.delete(id)
            finish()
          }
        })
      }

      if (path === `${ROUTE}/log`) {
        return json({ ok: false, error: 'not implemented yet' }, 501)
      }

      return json({ ok: false, error: 'not found' }, 404)
    } catch (error) {
      if (error instanceof ServerInputError) return json({ ok: false, error: error.message }, error.status)
      logger(`route failure ${method} ${path}: ${error && error.message}`)
      return json({ ok: false, error: String(error && error.message ? error.message : error) }, 500)
    }
  }
}
