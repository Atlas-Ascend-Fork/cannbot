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
import type {} from '@deepseek-ai/dsh-plugin-manager'
import { newerVersion, UPDATE_PACKAGES, type Change } from './client/plugin-update.ts'

export const UPDATE_PATH = '/api/cannbot-dsh/update'
export interface UpdateResult { result: Change; restore?: Change }
interface Bundle { name: string; version?: string; installed: boolean; removable?: boolean; enabled: boolean }
export interface UpdateManager {
  listBundles(): Promise<Bundle[]>
  removeBundle(name: string): Promise<Change>
  installBundle(spec: string, options: { saveExact: true; enabled: boolean; registry: string }): Promise<Change>
  updateBundle?(name: string, version: string, options: { registry: string }): Promise<UpdateResult>
}
const registry = 'https://registry.npmjs.org/'
const ok = (change: Change) => ['applied', 'restart-required'].includes(change.application) && !change.error
const failure = (code = 'operation-error'): Change => ({ application: 'failed', error: { code } })
const settled = async (action: () => Promise<Change>): Promise<Change> => { try { return await action() } catch { return failure() } }
async function publishedTarget(name: string, version: string): Promise<boolean> {
  const response = await fetch(`${registry}${encodeURIComponent(name)}/${version}`, { signal: AbortSignal.timeout(30000), cache: 'no-store' })
  if (!response.ok) return false
  const manifest = await response.json() as { name?: string; version?: string; dsh?: { bundle?: unknown }; dist?: { integrity?: string; tarball?: string } }
  if (manifest.name !== name || manifest.version !== version || !manifest.dsh?.bundle || !manifest.dist?.integrity || !manifest.dist.tarball) return false
  const tarball = new URL(manifest.dist.tarball)
  return tarball.protocol === 'https:' && tarball.hostname === 'registry.npmjs.org'
}

/** One Host-owned transaction. Unloading this plugin withdraws its route, not this in-flight task. */
export function createHostUpdater(manager: UpdateManager, lookup = publishedTarget) {
  let running = false
  return async (name: string, version: string): Promise<UpdateResult> => {
    if (!UPDATE_PACKAGES.includes(name as typeof UPDATE_PACKAGES[number]) || !/^\d+\.\d+\.\d+$/.test(version)) return { result: failure('invalid-spec') }
    if (running) return { result: failure('update-in-progress') }
    running = true
    try {
      const bundle = (await manager.listBundles()).find(item => item.name === name && item.installed)
      if (!bundle?.version || !newerVersion(version, bundle.version)) return { result: failure('invalid-spec') }
      // Prefer the official transaction wherever it exists.
      if (typeof manager.updateBundle === 'function') return await manager.updateBundle(name, version, { registry })
      if (bundle.removable !== true) return { result: failure('not-removable') }
      // Validate the exact public target before touching the running installation.
      if (!await lookup(name, version)) return { result: failure('invalid-spec') }
      const install = (value: string) => settled(() => manager.installBundle(`${name}@${value}`, { saveExact: true, enabled: bundle.enabled, registry }))
      // Non-HMR profiles can install in place and report that a restart is needed.
      const direct = await install(version)
      if (ok(direct) || direct.error?.code !== 'already-installed') return { result: direct }
      const removed = await settled(() => manager.removeBundle(name))
      if (!ok(removed)) return { result: removed }
      const result = await install(version)
      if (ok(result)) return { result }
      // Failed activation can leave the new dependency present. Remove it before restoring.
      let installed = true
      try { installed = (await manager.listBundles()).some(item => item.name === name && item.installed) } catch { /* still attempt cleanup and recovery */ }
      if (installed) {
        const cleanup = await settled(() => manager.removeBundle(name))
        if (!ok(cleanup) && cleanup.error?.code !== 'not-removable') return { result, restore: cleanup }
      }
      return { result, restore: await install(bundle.version) }
    } catch { return { result: failure() } }
    finally { running = false }
  }
}

export function registerHostUpdater(ctx: Context) {
  ctx.inject(['connection', 'pluginManager'], scoped => {
    if (typeof scoped.connection.fetch?.register !== 'function') return
    const update = createHostUpdater(scoped.pluginManager)
    scoped.connection.fetch.register({
      path: UPDATE_PATH, methods: ['POST'], requestBody: 'buffered',
      async fetch(request) {
        try {
          const body: unknown = await request.json()
          if (!body || typeof body !== 'object' || !('name' in body) || !('version' in body)
            || typeof body.name !== 'string' || typeof body.version !== 'string') return Response.json({ error: 'invalid-request' }, { status: 400 })
          // Deliberately no disposal/Request abort signal: self-removal or a closed browser must not cancel restoration.
          return Response.json(await update(body.name, body.version), { headers: { 'cache-control': 'no-store' } })
        } catch { return Response.json({ error: 'update-failed' }, { status: 500 }) }
      },
    })
  })
}
