// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import type { Context } from '@deepseek-ai/cordis'
import type {} from '@deepseek-ai/dsh-client-connection'
import { join } from 'node:path'
import type { ContentManager } from './content-manager.ts'
import { WorkspaceModeError, WorkspaceModes, type HostSession, type HostSessionSummary, type HostWorkspace, type WorkspaceModeDependencies } from './workspace-mode.ts'
import { CANNBOT_WORKSPACES_PATH, workspaceOperation } from '../contracts/workspace-mode-types.ts'
import { creationRequest, workspaceCreation } from './workspace-creation.ts'
import { workspaceOperationFailure } from './workspace-mode-errors.ts'
import { initializationRequest } from '../contracts/initialization-contract.ts'
import { InitializationJobs, type TerminalSpawner } from './initialization-jobs.ts'
import type {} from '@deepseek-ai/dsh-workspace'
import type { SessionId } from '@deepseek-ai/dsh-session'

const jobManagers = new WeakMap<WorkspaceModes, InitializationJobs>()
function jobsFor(modes: WorkspaceModes) {
  let jobs = jobManagers.get(modes)
  if (!jobs) { jobs = new InitializationJobs(operation => operation.action === 'create-folder' ? workspaceCreation(modes, operation) : modes.operate(operation)); jobManagers.set(modes, jobs) }
  return jobs
}

interface WorkspaceBaseline { items: readonly HostWorkspace[]; archivedSessionIds: readonly string[]; pinnedSessionIds?: readonly string[] }
interface HostServices {
  workspaceController: {
    create(request: { path: string }): Promise<{ workspace: HostWorkspace; created: boolean }>
    follow(signal: AbortSignal): AsyncIterable<{ type: string; value?: WorkspaceBaseline }>
    rename(request: { workspaceId: string; title: string }): Promise<unknown>
    delete(request: { workspaceId: string }): Promise<unknown>
    archiveSession(request: { sessionId: string; stopActivity?: boolean }): Promise<unknown>
    unarchiveSession(request: { sessionId: string }): Promise<unknown>
    pinSession(request: { sessionId: string }): Promise<unknown>
    unpinSession(request: { sessionId: string }): Promise<unknown>
  }
  sessionController: {
    list?(request: Record<string, never>, signal: AbortSignal): Promise<{ items: readonly HostSessionSummary[] }>
    rename(request: { sessionId: string; title: string }): Promise<unknown>
    fork(request: { sessionId: string; allowMigration?: boolean }): Promise<{ sessionId: string }>
  }
  sessionQuery: {
    observeSession(sessionId: string): Promise<{
      header: { id: string; cwd?: string; createdAt?: number; parentSession?: string }
      projections?: { values: { workingDirectory?: string | null; sessionListMetadata?: { blank?: boolean; lastPromptAt?: number | null } } }
      [Symbol.dispose](): void
    }>
    readTitleSnapshot?(sessionId: string): Promise<{ title?: { title: string; updatedAt?: number } }>
  }
}

/** Pure HTTP handler, also used by local/remote Host route tests. */
export async function workspaceModeResponse(modes: WorkspaceModes, request: Request): Promise<Response> {
  const headers = { 'cache-control': 'no-store' }
  try {
    if (request.method === 'GET') return Response.json(await modes.tree(), { headers })
    if (request.method !== 'POST') return Response.json({ error: 'method-not-allowed' }, { status: 405, headers })
    let body: unknown
    try { body = await request.json() } catch { throw new WorkspaceModeError('invalid-request', 'Expected a JSON request.', 400) }
    if (!body || typeof body !== 'object' || Array.isArray(body)) throw new WorkspaceModeError('invalid-request', 'Invalid workspace request.', 400)
    const data = body as Record<string, unknown>
    const initialization = initializationRequest(data)
    if (initialization) return Response.json(await jobsFor(modes).handle(initialization), { headers })
    const creation = creationRequest(data)
    if (creation) return Response.json(await workspaceCreation(modes, creation), { headers })
    if (data.action === 'create' && typeof data.path === 'string' && typeof data.pluginId === 'string') {
      return Response.json({ workspace: await modes.create(data.path, data.pluginId) }, { headers })
    }
    if ((data.action === 'session' || data.action === 'record-session') && typeof data.workspaceId === 'string' && typeof data.sessionId === 'string') {
      return Response.json({ ok: true, session: await modes.recordSession(data.workspaceId, data.sessionId) }, { headers })
    }
    const operation = workspaceOperation(data)
    if (operation) return Response.json(await modes.operate(operation), { headers })
    throw new WorkspaceModeError('invalid-request', 'Choose a directory and one workflow, or provide a workspace and session.', 400)
  } catch (error) {
    if (error instanceof WorkspaceModeError) return Response.json({ error: error.code, message: error.message }, { status: error.status, headers })
    const failure = workspaceOperationFailure(error)
    return Response.json(failure.body, { status: failure.status, headers })
  }
}

/** Register once immediately after constructing ContentManager. The guard remains
 * authoritative even when a legacy content or agent entry point invokes prepare.
 */
export function registerWorkspaceModes(ctx: Context, content: ContentManager): WorkspaceModes {
  let adapter: Pick<WorkspaceModeDependencies, 'createWorkspace' | 'listWorkspaces' | 'readSession' | 'renameWorkspace' | 'removeWorkspace' | 'archiveSession' | 'unarchiveSession' | 'pinSession' | 'unpinSession'> | undefined
  let sessionController: HostServices['sessionController'] | undefined
  const requireAdapter = () => {
    if (!adapter) throw new WorkspaceModeError('host-not-ready', 'Host workspace services are not ready.', 503)
    return adapter
  }
  const modes = new WorkspaceModes(join(content.root, 'workspace-modes'), {
    available: id => content.getSource().catalog.plugins.some(plugin => plugin.id === id),
    prepare: (path, id) => { requireAdapter(); return content.prepare(path, id) },
    switchWorkflow: (path, previous, next, commit, committed, token) => content.switchWorkflow(path, previous, next, commit, committed, token),
    sessionActivity: sessionId => { requireAdapter(); return ctx.waterfall('workspace/session-activity', { sessionId: sessionId as SessionId }, () => Promise.resolve([])) },
    createWorkspace: path => requireAdapter().createWorkspace(path),
    listWorkspaces: () => requireAdapter().listWorkspaces(),
    readSession: id => requireAdapter().readSession(id),
    async listSessionSummaries() {
      // One native cold-safe list per tree request, not one full catalog read
      // for every row. Older Hosts or a temporarily unavailable projection
      // keep the verified membership tree and omit unknown live facts.
      if (typeof sessionController?.list !== 'function') return undefined
      try { return (await sessionController.list({}, AbortSignal.timeout(10000))).items }
      catch { return undefined }
    },
    renameWorkspace: (id, title) => requireAdapter().renameWorkspace!(id, title),
    removeWorkspace: id => requireAdapter().removeWorkspace!(id),
    archiveSession: (id, stop) => requireAdapter().archiveSession!(id, stop),
    unarchiveSession: id => requireAdapter().unarchiveSession!(id),
    pinSession: id => requireAdapter().pinSession!(id),
    unpinSession: id => requireAdapter().unpinSession!(id),
    renameSession: (id, title) => {
      if (!sessionController?.rename) throw new WorkspaceModeError('operation-unavailable', '当前 DSH 不支持会话重命名。', 503)
      return sessionController.rename({ sessionId: id, title })
    },
    forkSession: (id, allowMigration) => {
      if (!sessionController?.fork) throw new WorkspaceModeError('operation-unavailable', '当前 DSH 不支持会话分支。', 503)
      return sessionController.fork({ sessionId: id, ...(allowMigration === undefined ? {} : { allowMigration }) })
    },
  })
  content.setPreparationGuard((cwd, id, run) => modes.withPreparation(cwd, id, run))
  ctx.inject(['workspaceController', 'sessionQuery'], scoped => {
    const services = scoped as unknown as HostServices
    let archived = new Set<string>(), pinned: readonly string[] = []
    const current = {
      createWorkspace: (path: string) => services.workspaceController.create({ path }),
      renameWorkspace: (workspaceId: string, title: string) => services.workspaceController.rename({ workspaceId, title }),
      removeWorkspace: (workspaceId: string) => services.workspaceController.delete({ workspaceId }),
      archiveSession: (sessionId: string, stopActivity: boolean) => services.workspaceController.archiveSession({ sessionId, ...(stopActivity ? { stopActivity: true } : {}) }),
      unarchiveSession: (sessionId: string) => services.workspaceController.unarchiveSession({ sessionId }),
      pinSession: (sessionId: string) => services.workspaceController.pinSession({ sessionId }),
      unpinSession: (sessionId: string) => services.workspaceController.unpinSession({ sessionId }),
      async listWorkspaces() {
        const abort = new AbortController()
        try {
          for await (const frame of services.workspaceController.follow(abort.signal)) {
            if (frame.type !== 'baseline' || !frame.value) throw new WorkspaceModeError('host-not-ready', 'Host did not provide a workspace baseline.', 503)
            archived = new Set(frame.value.archivedSessionIds)
            pinned = frame.value.pinnedSessionIds ?? []
            return frame.value.items
          }
          throw new WorkspaceModeError('host-not-ready', 'Host workspace stream closed before its baseline.', 503)
        } finally { abort.abort() }
      },
      async readSession(sessionId: string): Promise<HostSession> {
        using observation = await services.sessionQuery.observeSession(sessionId)
        const cwd = observation.projections?.values.workingDirectory ?? observation.header.cwd
        if (!cwd || observation.header.id !== sessionId) throw new WorkspaceModeError('invalid-session', 'Session has no registered working directory.', 400)
        const title = await services.sessionQuery.readTitleSnapshot?.(sessionId)
        // Native recency is the last user prompt (or creation), never the
        // title edit time. This is also the fallback when list() is absent.
        const metadata = observation.projections?.values.sessionListMetadata
        const promptedAt = metadata?.lastPromptAt
        const timestamp = typeof promptedAt === 'number' && Number.isFinite(promptedAt)
          ? Math.max(observation.header.createdAt ?? 0, promptedAt) : observation.header.createdAt
        const pinOrder = pinned.indexOf(sessionId)
        return { sessionId, cwd, parentSession: observation.header.parentSession, title: title?.title?.title, archived: archived.has(sessionId), pinned: pinOrder >= 0,
          ...(typeof metadata?.blank === 'boolean' ? { blank: metadata.blank } : {}),
          ...(pinOrder >= 0 ? { pinOrder } : {}),
          ...(typeof timestamp === 'number' && Number.isFinite(timestamp) && Math.abs(timestamp) <= 8640000000000000 ? { updatedAt: new Date(timestamp).toISOString() } : {}) }
      },
    }
    adapter = current
    void modes.registerPreparedWorkspaces().catch(error => console.error('[CANNBot] Prepared workspace registration:', (error as Error).message))
    scoped.effect(() => () => { if (adapter === current) adapter = undefined })
  })
  ctx.inject(['sessionController'], scoped => {
    const current = (scoped as unknown as HostServices).sessionController
    sessionController = current
    scoped.effect(() => () => { if (sessionController === current) sessionController = undefined })
  })
  ctx.inject(['subprocess'], scoped => {
    const runtime = (scoped as unknown as { subprocess: { spawnTerminal: TerminalSpawner } }).subprocess
    if (typeof runtime?.spawnTerminal === 'function') content.setTerminalSpawner(spec => runtime.spawnTerminal(spec))
    scoped.effect(() => () => { content.setTerminalSpawner(); jobsFor(modes).dispose() })
  })
  ctx.inject(['connection'], scoped => {
    if (typeof scoped.connection.fetch?.register !== 'function') return
    scoped.connection.fetch.register({ path: '/' + CANNBOT_WORKSPACES_PATH, methods: ['GET', 'POST'], requestBody: 'buffered', fetch: request => workspaceModeResponse(modes, request) })
  })
  return modes
}
