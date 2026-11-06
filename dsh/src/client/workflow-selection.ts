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
import type {} from '@deepseek-ai/dsh-api-remotes/client'
import { WORKFLOWS } from '../workflows.ts'

const NS = 'cannbot-dsh'
type Values = Record<string, string>
interface Choice { sessionId: string; workflow: string }
interface View { ns: string; value: { selections?: Choice[] }; revision?: number }
const valuesOf = (view?: View): Values => Object.fromEntries((view?.value.selections ?? []).map(item => [item.sessionId, item.workflow]))
export interface WorkflowTransport {
  describe(): Promise<{ namespaces: View[] }>
  update(ns: string, patch: { selections: Choice[] }, revision?: number): Promise<View>
}
export interface SelectionSnapshot { ready: boolean; pending: boolean; error: boolean; errorKind?: 'settings' | 'prepare' | 'save'; errorMessage?: string; values: Values }
export interface WorkflowSelection {
  subscribe(listener: () => void): () => void
  getSnapshot(): SelectionSnapshot
  attach(transport: WorkflowTransport): () => void
  choose(sessionId: string, workflow: string, reason?: string): Promise<void>
  retry(): void
  dispose(): void
}
export function createWorkflowSelection(blockSubmission: (sessionId: string, reason: string) => () => void = () => () => {}, prepare: (sessionId: string, id: string) => Promise<void> = async () => {}): WorkflowSelection {
  let snapshot: SelectionSnapshot = { ready: false, pending: false, error: false, values: {} }
  let transport: WorkflowTransport | undefined
  let generation = 0
  let pendingRelease: (() => void) | undefined
  let timer: ReturnType<typeof setTimeout> | undefined
  let lastChoice: { sessionId: string; workflow: string; reason: string } | undefined
  const listeners = new Set<() => void>()
  const publish = (next: SelectionSnapshot) => { snapshot = next; for (const listener of listeners) listener() }
  const read = async (current: WorkflowTransport, own: number, attempt = 0) => {
    try {
      const view = await current.describe()
      if (own !== generation) return
      const section = view.namespaces.find(item => item.ns === NS)
      if (!section) throw new Error('Workflow settings are not active yet')
      publish({ ready: true, pending: false, error: false, values: valuesOf(section) })
    } catch {
      if (own !== generation) return
      // Profile settings describe only active fibers. A browser can connect while
      // async plugin activation or a profile reload is still completing.
      if (attempt >= 9) publish({ ...snapshot, ready: false, pending: false, error: true, errorKind: 'settings' })
      timer = setTimeout(() => { void read(current, own, Math.min(attempt + 1, 9)) }, attempt < 9 ? Math.min(250 * (attempt + 1), 1500) : 5000)
    }
  }
  const api: WorkflowSelection = {
    subscribe(listener) { listeners.add(listener); return () => { listeners.delete(listener) } },
    getSnapshot: () => snapshot,
    attach(next) {
      clearTimeout(timer)
      pendingRelease?.(); pendingRelease = undefined
      transport = next
      const own = ++generation
      publish({ ...snapshot, ready: false, pending: false, error: false, errorKind: undefined })
      void read(next, own)
      return () => { if (own === generation) { generation++; clearTimeout(timer); transport = undefined; publish({ ...snapshot, ready: false }) } }
    },
    async choose(sessionId, workflow, reason = 'CANNBot DSH…') {
      if (!transport || !snapshot.ready || snapshot.pending) return
      if (workflow !== '' && !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(workflow)) throw new Error('Unknown workflow')
      const current = transport, own = generation
      lastChoice = { sessionId, workflow, reason }
      const unblock = blockSubmission(sessionId, reason)
      let released = false
      const release = () => { if (!released) { released = true; unblock() } }
      pendingRelease = release
      publish({ ...snapshot, pending: true, error: false, errorKind: undefined, errorMessage: undefined })
      let stage: 'prepare' | 'save' = 'prepare'
      try {
        if (workflow) await prepare(sessionId, workflow)
        stage = 'save'
        // Fresh revision prevents simultaneous windows from overwriting selections.
        const view = (await current.describe()).namespaces.find(item => item.ns === NS)
        if (!view) throw new Error('Workflow settings unavailable')
        const values = { ...valuesOf(view), [sessionId]: workflow }
        const selections = Object.entries(values).filter(([, id]) => id !== '').map(([sessionId, workflow]) => ({ sessionId, workflow }))
        const result = await current.update(NS, { selections }, view.revision)
        if (own === generation) publish({ ready: true, pending: false, error: false, values: valuesOf(result) })
      } catch (error) {
        if (own === generation) publish({ ...snapshot, pending: false, error: true, errorKind: stage, errorMessage: error instanceof Error ? error.message : undefined })
      } finally {
        release()
        if (pendingRelease === release) pendingRelease = undefined
      }
    },
    retry() {
      if (snapshot.errorKind === 'settings' && transport) {
        clearTimeout(timer)
        publish({ ...snapshot, error: false, errorKind: undefined })
        void read(transport, generation)
      } else if (lastChoice) void api.choose(lastChoice.sessionId, lastChoice.workflow, lastChoice.reason)
    },
    dispose() { generation++; clearTimeout(timer); transport = undefined; pendingRelease?.(); pendingRelease = undefined; listeners.clear() },
  }
  return api
}

/** Both transports are official DSH settings APIs; no private editor access. */
export function connectWorkflowSelection(ctx: Context, selection: WorkflowSelection) {
  ctx.inject(['remote', 'remote.settings'], scoped => {
    const settings = scoped.remote.settings
    scoped.effect(() => selection.attach({
      describe: async () => unwrap(await settings.describe()),
      update: async (ns, patch, revision) => unwrap(await settings.update(ns, patch, revision)),
    }))
  })
  ctx.inject(['connection'], scoped => {
    const api = (scoped as unknown as { connection: { api?: { settings: { describe(payload: object): Promise<unknown>; update(payload: object): Promise<unknown> } } } }).connection.api
    if (!api?.settings) return
    scoped.effect(() => selection.attach({
      describe: async () => unwrap(await api.settings.describe({})),
      update: async (ns, patch, expectedRevision) => unwrap(await api.settings.update({ ns, patch, expectedRevision })),
    }))
  })
}
function unwrap<T>(response: unknown): T {
  const raw = response as { result?: unknown }
  const result = (raw.result ?? response) as { ok: boolean; value: T; error?: { message: string } }
  if (!result.ok) throw new Error(result.error?.message ?? 'Workflow settings failed')
  return result.value
}
