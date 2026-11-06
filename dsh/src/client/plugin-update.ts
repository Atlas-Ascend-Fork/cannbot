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
export interface InstalledBundle { name: string; version?: string; installed: boolean }
export interface Change { application: string; error?: { code: string }; version?: string }
export interface UpdateBridge {
  list(): Promise<InstalledBundle[]>
  install(spec: string): Promise<Change>
  update?(name: string, version: string): Promise<{ result: Change; restore?: Change }>
}
export interface Release { name: string; version: string; tarball: string }
export type UpdatePhase = 'idle' | 'checking' | 'latest' | 'available' | 'updating' | 'done' | 'restart' | 'manual' | 'incompatible' | 'error'
export interface UpdateSnapshot { phase: UpdatePhase; current?: string; release?: Release; packageName?: string }

/** Only stable npm releases of our two installation entries may be selected. */
export function newerVersion(candidate: string, current: string): boolean {
  const next = /^(\d+)\.(\d+)\.(\d+)$/.exec(candidate)
  const old = /^(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$/.exec(current)
  if (!next || !old) return false
  for (let index = 1; index < 4; index++) {
    const difference = Number(next[index]) - Number(old[index])
    if (difference) return difference > 0
  }
  return /^\d+\.\d+\.\d+-/.test(current)
}

export async function latestRelease(name: string, signal: AbortSignal): Promise<Release> {
  if (!UPDATE_PACKAGES.includes(name as typeof UPDATE_PACKAGES[number])) throw new Error('Unsupported update target')
  const answers = await Promise.allSettled(['https://registry.npmjs.org/', 'https://registry.npmmirror.com/'].map(async registry => {
    const response = await fetch(`${registry}${encodeURIComponent(name)}/latest`, {
      signal: AbortSignal.any([signal, AbortSignal.timeout(15000)]), cache: 'no-store',
    })
    if (!response.ok) throw new Error('Registry unavailable')
    const manifest = await response.json() as { name?: string; version?: string; dist?: { tarball?: string }; dsh?: { bundle?: unknown } }
    if (manifest.name !== name || !manifest.version || !/^\d+\.\d+\.\d+$/.test(manifest.version) || !manifest.dsh?.bundle || !manifest.dist?.tarball) throw new Error('Invalid release')
    const url = new URL(manifest.dist.tarball)
    if (url.protocol !== 'https:' || !['registry.npmjs.org', 'registry.npmmirror.com'].includes(url.hostname)) throw new Error('Invalid download origin')
    return { name, version: manifest.version, tarball: url.href }
  }))
  signal.throwIfAborted()
  const releases = answers.flatMap(answer => answer.status === 'fulfilled' ? [answer.value] : [])
  const latest = releases.reduce<Release | undefined>((best, release) => !best || newerVersion(release.version, best.version) ? release : best, undefined)
  if (!latest) throw new Error('No release available')
  return latest
}

export function createPluginUpdater(bridge: UpdateBridge, requestedName: string, lookup = latestRelease) {
  let state: UpdateSnapshot = { phase: 'idle' }
  let disposed = false
  let checking: AbortController | undefined
  const listeners = new Set<() => void>()
  const publish = (next: UpdateSnapshot) => { if (disposed) return; state = next; for (const listener of listeners) listener() }
  const failed = (result: Change) => !['applied', 'restart-required'].includes(result.application) || !!result.error
  return {
    getSnapshot: () => state,
    subscribe(listener: () => void) { listeners.add(listener); return () => { listeners.delete(listener) } },
    async check() {
      if (disposed || state.phase === 'checking' || state.phase === 'updating') return
      checking?.abort()
      const abort = new AbortController()
      checking = abort
      publish({ ...state, phase: 'checking' })
      try {
        const bundles = (await bridge.list()).filter(bundle => bundle.installed && UPDATE_PACKAGES.includes(bundle.name as typeof UPDATE_PACKAGES[number]))
        // Update the actual direct dependency, preserving short/long installation form.
        const bundle = bundles.find(bundle => bundle.name === requestedName) ?? bundles[0]
        if (!bundle?.version) throw new Error('Installed entry unavailable')
        publish({ ...state, current: bundle.version, packageName: bundle.name })
        const release = await lookup(bundle.name, abort.signal)
        if (checking !== abort || disposed) return
        publish({ phase: newerVersion(release.version, bundle.version) ? 'available' : 'latest', current: bundle.version, release, packageName: bundle.name })
      } catch {
        if (!abort.signal.aborted) publish({ ...state, phase: 'error' })
      }
    },
    async update() {
      if (disposed || state.phase !== 'available' || !state.release || !state.packageName) return
      const target = state.release, name = state.packageName
      publish({ ...state, phase: 'updating' })
      try {
        // The Host owns the complete transaction, including self-removal and recovery.
        // Frontend disposal must never cancel an update that already started.
        const answer = bridge.update
          ? await bridge.update(name, target.version)
          : { result: await bridge.install(`${name}@${target.version}`) }
        const result = answer.result
        if (failed(result)) {
          const code = result.error?.code
          publish({ ...state, phase: code === 'already-installed' || code === 'stop-profile' ? 'manual' : code === 'incompatible-version' ? 'incompatible' : 'error' })
        } else {
          publish({ ...state, phase: result.application === 'restart-required' ? 'restart' : 'done', current: target.version })
        }
      } catch { publish({ ...state, phase: 'error' }) }
    },
    dispose() { disposed = true; checking?.abort(); listeners.clear() },
  }
}
export type PluginUpdater = ReturnType<typeof createPluginUpdater>
