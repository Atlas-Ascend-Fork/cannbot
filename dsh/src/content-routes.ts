// ----------------------------------------------------------------------------------------------------------
// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.
// ----------------------------------------------------------------------------------------------------------

import type { Context } from '@deepseek-ai/cordis'
import type {} from '@deepseek-ai/dsh-client-connection'
import type {} from '@deepseek-ai/dsh-session-query'
import type {} from '@deepseek-ai/dsh-working-directory'
import type { ContentManager } from './content-manager.ts'
import { validVersion } from './npm-workflows.ts'

export function registerContentRoutes(ctx: Context, content: ContentManager) {
  let workspaceFor: ((sessionId: string) => Promise<string>) | undefined
  ctx.inject(['sessionQuery', 'workingDirectory'], scoped => {
    workspaceFor = async sessionId => {
      using observation = await scoped.sessionQuery.observeSession(sessionId as Parameters<typeof scoped.sessionQuery.observeSession>[0])
      return observation.projections?.values.workingDirectory ?? observation.header.cwd ?? scoped.workingDirectory.defaultDirectory
    }
  })
  ctx.inject(['connection'], scoped => {
    if (typeof scoped.connection.fetch?.register !== 'function') return
    scoped.connection.fetch.register({
      path: '/api/cannbot-dsh/content', methods: ['GET', 'POST'], requestBody: 'buffered',
      async fetch(request) {
        if (request.method === 'GET') return Response.json(content.getStatus(), { headers: { 'cache-control': 'no-store' } })
        try {
          const body = await request.json() as { action?: string; id?: string; sessionId?: string; version?: string }
          if (body.version !== undefined && (typeof body.version !== 'string' || !validVersion(body.version))) return Response.json({ error: 'invalid-version' }, { status: 400 })
          if (body.action === 'check') { void content.check().catch(() => {}); return Response.json({ started: true }, { status: 202 }) }
          if (body.action === 'sync') { void content.sync().catch(() => {}); return Response.json({ started: true }, { status: 202 }) }
          if (body.action === 'update' && typeof body.id === 'string') { void content.sync(body.id, body.version).catch(() => {}); return Response.json({ started: true }, { status: 202 }) }
          if (body.action === 'rollback' && typeof body.id === 'string') { await content.rollback(body.id); return Response.json({ restored: true }) }
          if (body.action !== 'prepare' || typeof body.id !== 'string' || typeof body.sessionId !== 'string' || !workspaceFor) return Response.json({ error: 'invalid-request' }, { status: 400 })
          await content.prepare(await workspaceFor(body.sessionId), body.id)
          return Response.json({ ready: true })
        } catch { return Response.json({ error: 'Content preparation failed. See content status and logs.' }, { status: 500 }) }
      },
    })
    // Baseline packages are mandatory npm dependencies and ready before apply completes.
    // Downloading newer resources is an explicit action in workflow management.
  })
}
