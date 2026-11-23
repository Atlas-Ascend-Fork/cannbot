// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import type { Context } from '@deepseek-ai/cordis'
import type {} from '@deepseek-ai/dsh-client-connection'
import { workspaceOperation, type CANNBotOperationResult, type CANNBotWorkspaceOperation, type CANNBotWorkspaceTree } from './workspace-mode-types.ts'
import { creationRequest, type WorkspaceCreationRequest } from './workspace-creation.ts'
import { workspaceOperationFailure } from './workspace-mode-errors.ts'
import { initializationRequest, type InitializationRequest } from './initialization-contract.ts'

interface Connection { connected: boolean; localPort: number; url: string; token?: string }
interface Connections { getConnection(id: string): Connection | null }
const failure = () => new Error('无法读取远端 CANNBot 工作区，请重新连接以更新插件并重试。')
class RemoteOperationError extends Error {
  readonly result: ReturnType<typeof workspaceOperationFailure>
  constructor(result: ReturnType<typeof workspaceOperationFailure>) { super(result.body.message); this.result = result }
}

/** Only a manager-owned, active loopback tunnel is eligible. The launch token
 * is exchanged for DSH's own cookie in the Host; neither reaches this response.
 */
async function remoteAttempt(manager: Connections, id: string, operation: CANNBotWorkspaceOperation | WorkspaceCreationRequest | InitializationRequest | undefined, fetcher: typeof fetch): Promise<unknown> {
  try {
    const connection = manager.getConnection(id)
    if (!connection?.connected || !Number.isInteger(connection.localPort) || connection.localPort < 1 || connection.localPort > 65535) throw failure()
    const base = new URL(connection.url)
    if (base.protocol !== 'http:' || base.hostname !== '127.0.0.1' || Number(base.port) !== connection.localPort || base.username || base.password) throw failure()
    base.pathname = '/'; base.hash = ''; base.search = ''
    if (connection.token) base.searchParams.set('token', connection.token)
    const signal = AbortSignal.timeout(operation?.action === 'create-folder' ? 180000 : 15000)
    const handshake = await fetcher(base, { redirect: 'manual', signal, cache: 'no-store' })
    const cookies = handshake.headers.getSetCookie().map(value => value.split(';', 1)[0]).filter(value => /^[A-Za-z0-9_-]+=[A-Za-z0-9_.-]+$/.test(value)).join('; ')
    await handshake.body?.cancel()
    if (handshake.status !== 303 || !cookies) throw failure()
    const url = new URL('/api/cannbot-dsh/workspaces', base)
    const response = await fetcher(url, { headers: { cookie: cookies, ...(operation ? { 'content-type': 'application/json', ...(operation.action === 'create-folder' ? { 'x-cannbot-remote-workspace': '1' } : {}) } : {}) }, signal, redirect: 'error', cache: 'no-store',
      ...(operation ? { method: 'POST', body: JSON.stringify(operation) } : {}) })
    if (!response.body) throw failure()
    const reader = response.body.getReader()
    const pieces: Uint8Array[] = []
    let length = 0
    try {
      while (true) {
        const piece = await reader.read()
        if (piece.done) break
        length += piece.value.length
        if (length > 4 * 1024 * 1024) throw failure()
        pieces.push(piece.value)
      }
    } finally { await reader.cancel() }
    const raw = JSON.parse(Buffer.concat(pieces).toString('utf8'))
    if (!response.ok) {
      if (operation) throw new RemoteOperationError(workspaceOperationFailure(raw))
      throw failure()
    }
    return raw
  } catch (error) {
    if (error instanceof RemoteOperationError) throw error
    if (operation) throw new RemoteOperationError({ status: 502, body: { error: 'remote-operation-failed', message: operation.action === 'browse-directory' ? '远端目录暂时无法读取，请检查连接后重试。' : '远端操作结果暂不可用，请刷新列表确认结果后重试。' } })
    throw failure()
  }
}

async function remoteRequest(manager: Connections, id: string, operation: CANNBotWorkspaceOperation | WorkspaceCreationRequest | InitializationRequest | undefined, fetcher: typeof fetch): Promise<unknown> {
  // A ready SSH port can precede the newly deployed Host's HTTP routes. Only
  // directory reads are retried; mutations must never be replayed implicitly.
  for (let attempt = 0;; attempt++) {
    try { return await remoteAttempt(manager, id, operation, fetcher) }
    catch (error) {
      if (operation?.action !== 'browse-directory' || attempt >= 3 || !(error instanceof RemoteOperationError) || ![502, 503].includes(error.result.status)) throw error
      await new Promise(resolve => setTimeout(resolve, 400 * (attempt + 1)))
    }
  }
}

export async function readRemoteTree(manager: Connections, id: string, fetcher: typeof fetch = fetch): Promise<CANNBotWorkspaceTree> {
  try {
    const raw = await remoteRequest(manager, id, undefined, fetcher) as Record<string, unknown>
    if (!raw || raw.mode !== 'cannbot' || !Array.isArray(raw.workspaces) || !Array.isArray(raw.sessions)) throw failure()
    const text = (value: unknown): value is string => typeof value === 'string' && value.length > 0 && value.length <= 16384
    const workspaces: CANNBotWorkspaceTree['workspaces'] = raw.workspaces.filter((item: Record<string, unknown>) => item && text(item.workspaceId) && text(item.path) && text(item.pluginId)).map((item: Record<string, unknown>) => ({
      workspaceId: String(item.workspaceId), path: String(item.path), title: text(item.title) ? item.title : String(item.path), pluginId: String(item.pluginId),
      sessionIds: [], sharedWithDeepSeek: false,
    }))
    const owners = new Map(workspaces.map(item => [item.workspaceId, item]))
    const sessions: CANNBotWorkspaceTree['sessions'] = raw.sessions.filter((item: Record<string, unknown>) => item && text(item.sessionId) && text(item.workspaceId) && text(item.pluginId)
      && (owners.has(item.workspaceId) ? item.pluginId === owners.get(item.workspaceId)?.pluginId || item.frozen === true : item.ungrouped === true)).map((item: Record<string, unknown>) => ({
      sessionId: String(item.sessionId), workspaceId: String(item.workspaceId), pluginId: String(item.pluginId), title: text(item.title) ? item.title : '新会话',
      ...(text(item.updatedAt) ? { updatedAt: item.updatedAt } : {}),
      archived: item.archived === true, pinned: item.pinned === true, frozen: item.frozen === true, ...(!owners.has(String(item.workspaceId)) ? { ungrouped: true } : {}),
      ...(typeof item.blank === 'boolean' ? { blank: item.blank } : {}), ...(typeof item.running === 'boolean' ? { running: item.running } : {}),
      ...(item.pinned === true && typeof item.pinOrder === 'number' && Number.isSafeInteger(item.pinOrder) && item.pinOrder >= 0 ? { pinOrder: item.pinOrder } : {}),
    }))
    for (const session of sessions) owners.get(session.workspaceId)?.sessionIds.push(session.sessionId)
    return { mode: 'cannbot', platform: typeof raw.platform === 'string' ? raw.platform : undefined, workspaces, sessions }
  } catch { throw failure() }
}

/** A mutation is attempted once. Timeout/failure cannot establish whether the
 * remote Host committed it, so callers must refresh instead of blind retry.
 */
export async function operateRemoteTree(manager: Connections, id: string, value: unknown, fetcher: typeof fetch = fetch): Promise<CANNBotOperationResult> {
  const operation = workspaceOperation(value)
  if (!operation) throw new RemoteOperationError(workspaceOperationFailure({ code: 'invalid-request' }))
  const raw = await remoteRequest(manager, id, operation, fetcher) as { ok?: unknown; sessionId?: unknown }
  if (raw?.ok !== true) throw new RemoteOperationError(workspaceOperationFailure(null))
  if (operation.action === 'fork-session') {
    if (typeof raw.sessionId !== 'string' || !raw.sessionId || raw.sessionId.length > 2000 || /[\s\x00-\x1f\x7f]/.test(raw.sessionId)) throw new RemoteOperationError(workspaceOperationFailure(null))
    return { ok: true, sessionId: raw.sessionId }
  }
  return { ok: true }
}

export function registerRemoteTree(ctx: Context, manager: Connections) {
  ctx.inject(['connection'], scoped => {
    scoped.connection.fetch.register({ path: '/api/cannbot-remote/tree', methods: ['GET', 'POST'], requestBody: 'buffered', async fetch(request) {
      const id = new URL(request.url).searchParams.get('id')
      if (!id || id.length > 2000) return Response.json({ error: '请选择已连接的服务器。' }, { status: 400 })
      try {
        if (request.method === 'POST') {
          let body: unknown
          try { const text = await request.text(); if (text.length > 16384) throw new Error(); body = JSON.parse(text) }
          catch { throw new RemoteOperationError(workspaceOperationFailure({ code: 'invalid-request' })) }
          const creation = creationRequest(body)
          const initialization = initializationRequest(body)
          return Response.json(initialization || creation ? await remoteRequest(manager, id, initialization || creation, fetch) : await operateRemoteTree(manager, id, body), { headers: { 'cache-control': 'no-store' } })
        }
        if (request.method !== 'GET') return Response.json({ error: 'method-not-allowed' }, { status: 405 })
        return Response.json(await readRemoteTree(manager, id), { headers: { 'cache-control': 'no-store' } })
      }
      catch (error) {
        if (error instanceof RemoteOperationError) return Response.json(error.result.body, { status: error.result.status, headers: { 'cache-control': 'no-store' } })
        return Response.json({ error: failure().message }, { status: 502, headers: { 'cache-control': 'no-store' } })
      }
    } })
  })
}
