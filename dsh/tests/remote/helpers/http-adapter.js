// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

// Test-only bridge from a Node HTTP server to Fetch routes. DSH's production
// connection.fetch service calls the Fetch handler directly (including IPC on
// desktop); this bridge lets tests exercise browser HTTP/SSE transport behavior.
import { Readable } from 'node:stream'
import { pipeline } from 'node:stream/promises'

export function createNodeHandler(handler, { logger = () => {} } = {}) {
  return async function nodeHandler(req, res) {
    const abort = new AbortController()
    const disconnected = () => abort.abort(new Error('client disconnected'))
    const closed = () => { if (!res.writableFinished) disconnected() }
    req.once('aborted', disconnected)
    res.once('close', closed)

    try {
      const method = req.method || 'GET'
      const request = new Request(new URL(req.url || '/', 'http://dsh.invalid'), {
        method,
        headers: req.headers,
        signal: abort.signal,
        ...(method === 'GET' || method === 'HEAD' ? {} : { body: Readable.toWeb(req), duplex: 'half' }),
      })
      const response = await handler(request)
      if (!(response instanceof Response)) throw new TypeError('route must return a Response')

      // A disconnect can occur while the route is awaiting SSH or another task.
      if (abort.signal.aborted || res.destroyed) {
        await response.body?.cancel()
        return
      }

      res.statusCode = response.status
      for (const [name, value] of response.headers) {
        if (name !== 'set-cookie') res.setHeader(name, value)
      }
      const cookies = response.headers.getSetCookie()
      if (cookies.length) res.setHeader('set-cookie', cookies)

      if (!response.body || method === 'HEAD') {
        await response.body?.cancel()
        res.end()
        return
      }
      // Send SSE headers immediately; pipeline preserves backpressure and
      // cancels the Web stream if the client closes the Node response.
      res.flushHeaders()
      await pipeline(Readable.fromWeb(response.body), res, { signal: abort.signal })
    } catch (error) {
      if (abort.signal.aborted || res.destroyed) return
      logger(`HTTP adapter failure: ${error && error.message}`)
      if (res.headersSent) {
        res.destroy(error)
      } else {
        res.statusCode = 500
        res.setHeader('content-type', 'application/json; charset=utf-8')
        res.end(JSON.stringify({ ok: false, error: 'plugin HTTP request failed' }))
      }
    } finally {
      req.removeListener('aborted', disconnected)
      res.removeListener('close', closed)
    }
  }
}
