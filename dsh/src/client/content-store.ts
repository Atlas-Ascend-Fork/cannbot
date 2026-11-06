// ----------------------------------------------------------------------------------------------------------
// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.
// ----------------------------------------------------------------------------------------------------------

import { WORKFLOWS } from '../workflows.ts'
import { CONTENT_PATH, type ContentStatus } from '../content-types.ts'
export interface DynamicWorkflow { id: string; title: string }
const initial: { workflows: DynamicWorkflow[]; status: ContentStatus | undefined } = { workflows: WORKFLOWS.map(({ id }) => ({ id, title: id })), status: undefined }
export function createContentStore() {
  let state = initial, closed = false, timer: ReturnType<typeof setTimeout> | undefined
  const listeners = new Set<() => void>()
  const publish = (status: ContentStatus) => { if (!closed) { state = { status, workflows: status.plugins }; for (const listener of listeners) listener() } }
  const endpoint = () => new URL(CONTENT_PATH, document.baseURI)
  let requestSequence = 0
  const pull = async () => {
    const sequence = ++requestSequence
    try {
      const response = await fetch(endpoint(), { credentials: 'same-origin', cache: 'no-store', signal: AbortSignal.timeout(15000) })
      if (response.ok) {
        const status = await response.json() as ContentStatus
        if (sequence === requestSequence && Array.isArray(status.plugins) && status.plugins.every(item => /^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(item.id) && typeof item.title === 'string')) publish(status)
      }
    } catch { /* Keep the last catalog across a short disconnect. */ }
  }
  const post = async (body: object) => {
    ++requestSequence // Invalidate pre-operation snapshots before the POST begins.
    const response = await fetch(endpoint(), { method: 'POST', credentials: 'same-origin', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) })
    if (!response.ok) { await pull(); throw new Error(state.status?.message || '工作流准备失败，请检查插件日志。') }
    await pull()
  }
  return {
    getSnapshot: () => state,
    subscribe(listener: () => void) { listeners.add(listener); return () => { listeners.delete(listener) } },
    start() {
      const tick = async () => { await pull(); if (!closed) timer = setTimeout(() => { void tick() }, 3000) }
      void tick()
      return () => { closed = true; clearTimeout(timer); listeners.clear() }
    },
    sync: () => post({ action: 'sync' }),
    check: () => post({ action: 'check' }),
    update: (id: string, version: string) => post({ action: 'update', id, version }),
    rollback: (id: string) => post({ action: 'rollback', id }),
    prepare: (sessionId: string, id: string) => post({ action: 'prepare', sessionId, id }),
  }
}
export type ContentStore = ReturnType<typeof createContentStore>
export const fallbackContent = { getSnapshot: () => initial, subscribe: (_: () => void) => () => {} }
