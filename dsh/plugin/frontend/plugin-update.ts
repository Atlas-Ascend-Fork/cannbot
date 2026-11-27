// ----------------------------------------------------------------------------------------------------------
// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.
// ----------------------------------------------------------------------------------------------------------

export const UPDATE_PACKAGES = ['cannbot-dsh', '@cannbot-plugin/cannbot-dsh'] as const

export { newerVersion } from '../contracts/newer-version.ts'

type Phase = 'idle' | 'checking' | 'latest' | 'available' | 'updating' | 'done' | 'restart' | 'manual' | 'agreement-required' | 'unconfigured' | 'incompatible' | 'stale' | 'error'
interface Release { version: string; buildId: string }
interface UpdateSnapshot { phase: Phase; current?: string; release?: Release }

export function createPluginUpdater() {
  let state: UpdateSnapshot = { phase: 'idle' }, disposed = false
  const lifetime = new AbortController(), listeners = new Set<() => void>()
  const publish = (patch: Partial<UpdateSnapshot>) => {
    if (disposed) return
    state = { ...state, ...patch }
    for (const listener of listeners) listener()
  }
  const endpoint = () => new URL('api/cannbot-dsh/update', document.baseURI)
  return {
    getSnapshot: () => state,
    subscribe(listener: () => void) { listeners.add(listener); return () => { listeners.delete(listener) } },
    async check() {
      if (disposed || state.phase === 'checking' || state.phase === 'updating') return
      publish({ phase: 'checking', release: undefined })
      try {
        const response = await fetch(endpoint(), { credentials: 'same-origin', cache: 'no-store', signal: AbortSignal.any([lifetime.signal, AbortSignal.timeout(45000)]) })
        if (!response.ok) throw new Error('Check failed')
        const answer = await response.json()
        if (typeof answer.current === 'string') publish({ current: answer.current })
        if (answer.status === 'available' && typeof answer.version === 'string' && answer.version && typeof answer.targetBuildId === 'string' && answer.targetBuildId) {
          publish({ phase: 'available', release: { version: answer.version, buildId: answer.targetBuildId } })
        } else {
          publish({ phase: ['latest', 'incompatible', 'agreement-required', 'unconfigured'].includes(answer.status) ? answer.status : 'error' })
        }
      } catch { publish({ phase: 'error' }) }
    },
    async update() {
      if (disposed || state.phase !== 'available' || !state.release) return
      const release = state.release
      publish({ phase: 'updating' })
      try {
        // Keep the selected build running on the Host if the update unmounts its own UI.
        const response = await fetch(endpoint(), { method: 'POST', credentials: 'same-origin', headers: { 'content-type': 'application/json' }, body: JSON.stringify(release) })
        const answer = await response.json()
        const phase: Phase = response.ok && ['restart', 'done', 'latest', 'manual', 'agreement-required', 'incompatible', 'stale', 'unconfigured'].includes(answer.status) ? answer.status : 'error'
        publish({ phase, release: undefined, ...(typeof answer.current === 'string' && { current: answer.current }), ...(phase === 'done' && { current: release.version }) })
      } catch { publish({ phase: 'error', release: undefined }) }
    },
    dispose() { disposed = true; lifetime.abort(); listeners.clear() },
  }
}
export type PluginUpdater = ReturnType<typeof createPluginUpdater>
