// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import type { Context } from '@deepseek-ai/cordis'
import type { ISessions, SessionReference } from '@deepseek-ai/dsh-api-session-controller/client'
import type { WorkspaceId } from '@deepseek-ai/dsh-api-workspace-controller/client'
import type { SessionId } from '@deepseek-ai/dsh-session/types'
import { CANNBOT_HOME, type WorkspaceModes } from './workspace-modes.ts'
import type { WorkflowSelection } from './workflow-selection.ts'
import { GENERAL_WORKSPACE } from '../contracts/workspace-mode-types.ts'

export interface NativeWorkbenchSessionSnapshot {
  workspaceId: string
  session?: SessionReference
  sessionId?: string
  busy: boolean
  error: string
}
type Entry = { reference: SessionReference; pluginId: string; wasBlank: boolean; sent: boolean }
type Modes = Pick<WorkspaceModes, 'getSnapshot' | 'subscribe' | 'selectWorkspace' | 'recordSession' | 'openSession'>

/** Retain each workspace's native draft; no composer submission is performed here. */
export function createNativeWorkbenchSession(ctx: Context, selection: WorkflowSelection, modes: Modes) {
  const sessions = ctx.sessions as unknown as ISessions
  const lifetime = new AbortController(), listeners = new Set<() => void>()
  const cache = new Map<string, Entry>(), pending = new Map<string, Promise<Entry>>()
  let state: NativeWorkbenchSessionSnapshot = { workspaceId: '', busy: false, error: '' }
  let sequence = 0, workflowQueue: Promise<unknown> = Promise.resolve()
  const publish = (next: NativeWorkbenchSessionSnapshot) => { if (!lifetime.signal.aborted) { state = next; for (const listener of listeners) listener() } }
  const currentWorkspace = (id: string) => modes.getSnapshot().workspaces.find(item => item.workspaceId === id)
  const active = () => modes.getSnapshot().mode === 'cannbot' && !modes.getSnapshot().serverId && ctx.layout.panelInfo.getSnapshot().activePanelId === CANNBOT_HOME
  const release = (id: string) => { const entry = cache.get(id); if (entry) { cache.delete(id); entry.reference.release() } }
  const transferSubmitted = () => {
    const catalog = sessions.list.getSnapshot()
    for (const entry of cache.values()) if (catalog.byId[entry.reference.sessionId]?.blank === true) entry.wasBlank = true
    const entry = cache.get(state.workspaceId)
    if (!entry || !state.session || entry.sent || !entry.wasBlank || !active() || catalog.byId[entry.reference.sessionId]?.blank !== false) return
    // Navigation acquires mainView synchronously before this cache lets go.
    entry.sent = true
    modes.openSession(entry.reference.sessionId)
    release(state.workspaceId)
    publish({ workspaceId: state.workspaceId, busy: false, error: '' })
  }
  const stopSessions = sessions.list.subscribe(transferSubmitted)
  const stopModes = modes.subscribe(() => {
    if (!modes.getSnapshot().ready) return
    for (const id of cache.keys()) if (!currentWorkspace(id)) {
      release(id)
      if (state.workspaceId === id) { ++sequence; publish({ workspaceId: id, busy: false, error: '工作区已移除，请重新选择。' }) }
    }
  })

  async function prepare(workspaceId: string): Promise<Entry> {
    const existing = pending.get(workspaceId)
    if (existing) return existing
    const task = (async () => {
      const workspace = currentWorkspace(workspaceId)
      if (!workspace || !modes.getSnapshot().ready) throw new Error('请先选择 CANNBot 工作区。')
      const signal = AbortSignal.any([lifetime.signal, AbortSignal.timeout(120000)])
      await waitFor(sessions.list, () => sessions.list.getSnapshot().phase === 'ready', AbortSignal.any([signal, AbortSignal.timeout(20000)]))
      const catalog = sessions.list.getSnapshot()
      const owned = new Set([...workspace.sessionIds, ...modes.getSnapshot().sessions.filter(item => item.workspaceId === workspaceId).map(item => item.sessionId)])
      const archived = new Set(ctx.workspaces.list.getSnapshot().archivedSessionIds)
      const reusable = Object.entries(catalog.byId).find(([id, summary]) => owned.has(id) && summary.blank === true && !archived.has(id as SessionId))?.[0]
      const id = await settle(sessions.create({ workspaceId: workspaceId as WorkspaceId, ...(reusable && { sessionId: reusable as SessionId }) }), signal)
      signal.throwIfAborted()
      await settle(modes.recordSession(workspaceId, id, { reveal: false }), signal)
      signal.throwIfAborted()
      // Preparation's deadline only bounds waiting. A successful native draft
      // keeps its reference for the controller lifetime, across mode switches.
      const reference = sessions.retain(id, { source: 'controllerOperation', signal: lifetime.signal })
      try {
        await settle(reference.ready, signal)
        // WorkflowSelection intentionally has a single in-flight transaction.
        // Serialize preparations without losing either workspace's native draft.
        const bind = workflowQueue.then(async () => {
          await waitFor(selection, () => { const saved = selection.getSnapshot(); return saved.ready && !saved.pending }, signal)
          signal.throwIfAborted()
          const workflow = workspace.pluginId === GENERAL_WORKSPACE ? '' : workspace.pluginId
          await settle(selection.choose(id, workflow), signal)
          const saved = selection.getSnapshot()
          if (!saved.ready || saved.pending || saved.error || (saved.values[id] || '') !== workflow) throw new Error('工作流准备未完成，请重试。')
        })
        workflowQueue = bind.catch(() => {})
        await bind
        signal.throwIfAborted()
        if (currentWorkspace(workspaceId)?.pluginId !== workspace.pluginId) throw new Error('工作区已变化，请重新选择。')
        const entry = { reference, pluginId: workspace.pluginId, wasBlank: sessions.list.getSnapshot().byId[id]?.blank === true, sent: false }
        cache.set(workspaceId, entry)
        return entry
      } catch (error) { reference.release(); throw error }
    })()
    pending.set(workspaceId, task)
    try { return await task } finally { if (pending.get(workspaceId) === task) pending.delete(workspaceId) }
  }

  const api = {
    getSnapshot: () => state,
    subscribe(listener: () => void) { listeners.add(listener); return () => { listeners.delete(listener) } },
    async selectWorkspace(workspaceId: string) {
      if (lifetime.signal.aborted || !active()) return
      const own = ++sequence, workspace = currentWorkspace(workspaceId)
      const mode = modes.getSnapshot()
      if (mode.restoringSession || mode.navigationError) { publish({ workspaceId, busy: !!mode.restoringSession, error: mode.navigationError }); return }
      if (!workspaceId) { publish({ workspaceId: '', busy: false, error: '' }); return }
      if (!workspace || !modes.getSnapshot().ready) { publish({ workspaceId, busy: false, error: '请先选择 CANNBot 工作区。' }); return }
      if (modes.getSnapshot().selectedWorkspaceId !== workspaceId) modes.selectWorkspace(workspaceId)
      let entry = cache.get(workspaceId)
      if (entry && (entry.sent || entry.pluginId !== workspace.pluginId || !sessions.list.getSnapshot().byId[entry.reference.sessionId]
        || sessions.list.getSnapshot().byId[entry.reference.sessionId]?.blank === false || ctx.workspaces.list.getSnapshot().archivedSessionIds.includes(entry.reference.sessionId))) { release(workspaceId); entry = undefined }
      if (entry) { publish({ workspaceId, session: entry.reference, sessionId: entry.reference.sessionId, busy: false, error: '' }); return }
      publish({ workspaceId, busy: true, error: '' })
      try {
        entry = await prepare(workspaceId)
        if (own !== sequence || lifetime.signal.aborted) return
        publish({ workspaceId, session: entry.reference, sessionId: entry.reference.sessionId, busy: false, error: '' })
        transferSubmitted()
      } catch {
        if (own === sequence && !lifetime.signal.aborted) publish({ workspaceId, busy: false, error: '工作区对话准备失败，请重试。' })
      }
    },
    retry() { return api.selectWorkspace(state.workspaceId) },
    dispose() {
      if (lifetime.signal.aborted) return
      ++sequence; lifetime.abort(); stopSessions(); stopModes()
      for (const id of cache.keys()) release(id)
      listeners.clear()
    },
  }
  return api
}

function settle<T>(task: Promise<T>, signal: AbortSignal): Promise<T> {
  return new Promise((resolve, reject) => {
    const abort = () => reject(signal.reason ?? new Error('cancelled'))
    signal.addEventListener('abort', abort, { once: true })
    task.then(value => { signal.removeEventListener('abort', abort); signal.aborted ? abort() : resolve(value) }, error => { signal.removeEventListener('abort', abort); reject(error) })
    if (signal.aborted) abort()
  })
}
function waitFor(source: { subscribe(listener: () => void): () => void }, ready: () => boolean, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    let unsubscribe = () => {}
    const finish = (error?: unknown) => { unsubscribe(); signal.removeEventListener('abort', abort); error ? reject(error) : resolve() }
    const abort = () => finish(signal.reason ?? new Error('cancelled'))
    const check = () => { if (ready()) finish() }
    unsubscribe = source.subscribe(check); signal.addEventListener('abort', abort, { once: true })
    if (signal.aborted) abort(); else check()
  })
}
