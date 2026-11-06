// ----------------------------------------------------------------------------------------------------------
// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.
// ----------------------------------------------------------------------------------------------------------

import { afterEach, expect, it, vi } from 'vitest'
import { createHostUpdater, registerHostUpdater, type UpdateManager } from '../src/update-host.ts'
import { updateOnHost } from '../src/client/host-update.ts'

afterEach(() => { vi.unstubAllGlobals(); document.body.innerHTML = '' })
function manager() {
  let installed = true
  const api: UpdateManager = {
    listBundles: vi.fn(async () => installed ? [{ name: 'cannbot-dsh', version: '1.0.0-alpha.1', installed: true, removable: true, enabled: true }] : []),
    removeBundle: vi.fn(async () => { installed = false; return { application: 'applied' } }),
    installBundle: vi.fn(async () => { installed = true; return { application: 'applied' } }).mockResolvedValueOnce({ application: 'failed', error: { code: 'already-installed' } }),
  }
  return api
}
it('uses only official APIs to remove and install the exact target', async () => {
  const api = manager()
  const answer = await createHostUpdater(api, async () => true)('cannbot-dsh', '1.0.0')
  expect(answer.result.application).toBe('applied')
  expect(api.removeBundle).toHaveBeenCalledExactlyOnceWith('cannbot-dsh')
  expect(api.installBundle).toHaveBeenLastCalledWith('cannbot-dsh@1.0.0', { saveExact: true, enabled: true, registry: 'https://registry.npmjs.org/' })
})
it('restores the previous exact version after a failed install', async () => {
  const api = manager()
  vi.mocked(api.installBundle).mockRejectedValueOnce(new Error('network'))
  const answer = await createHostUpdater(api, async () => true)('cannbot-dsh', '1.0.0')
  expect(answer.result.application).toBe('failed')
  expect(answer.restore?.application).toBe('applied')
  expect(api.installBundle).toHaveBeenLastCalledWith('cannbot-dsh@1.0.0-alpha.1', expect.objectContaining({ enabled: true }))
})
it('does not uninstall when the target is unavailable or foreign', async () => {
  const api = manager(), update = createHostUpdater(api, async () => true)
  await update('unrelated', '1.0.0'); await update('cannbot-dsh', '1.0.0-alpha.1')
  await createHostUpdater(api, async () => false)('cannbot-dsh', '1.0.0')
  expect(api.removeBundle).not.toHaveBeenCalled()
})
it('does not install after an official removal refusal', async () => {
  const api = manager()
  vi.mocked(api.removeBundle).mockResolvedValue({ application: 'failed', error: { code: 'stop-profile' } })
  const answer = await createHostUpdater(api, async () => true)('cannbot-dsh', '1.0.0')
  expect(answer.result.error?.code).toBe('stop-profile')
  expect(api.installBundle).toHaveBeenCalledTimes(1)
})
it('prefers the native official update transaction', async () => {
  const api = { ...manager(), updateBundle: vi.fn(async () => ({ result: { application: 'applied' } })) }
  await createHostUpdater(api, async () => true)('cannbot-dsh', '1.0.0')
  expect(api.updateBundle).toHaveBeenCalledOnce()
  expect(api.removeBundle).not.toHaveBeenCalled()
})
it('updates in place when the Host requests only a restart', async () => {
  const api = manager()
  vi.mocked(api.installBundle).mockReset().mockResolvedValue({ application: 'restart-required' })
  const answer = await createHostUpdater(api, async () => true)('cannbot-dsh', '1.0.0')
  expect(answer.result.application).toBe('restart-required')
  expect(api.removeBundle).not.toHaveBeenCalled()
})
it('reports failed recovery instead of claiming the update succeeded', async () => {
  const api = manager()
  vi.mocked(api.installBundle).mockResolvedValueOnce({ application: 'failed' }).mockResolvedValueOnce({ application: 'failed' })
  const answer = await createHostUpdater(api, async () => true)('cannbot-dsh', '1.0.0')
  expect(answer.result.application).toBe('failed')
  expect(answer.restore?.application).toBe('failed')
})
it('rejects concurrent requests while an update is running', async () => {
  const api = manager()
  let release!: () => void
  const gate = new Promise<void>(resolve => { release = resolve })
  const update = createHostUpdater(api, async () => { await gate; return true }), first = update('cannbot-dsh', '1.0.0')
  expect((await update('cannbot-dsh', '1.0.0')).result.error?.code).toBe('update-in-progress')
  release(); await first
  expect(api.removeBundle).toHaveBeenCalledOnce()
})
it('keeps the server transaction alive after its plugin route is withdrawn', async () => {
  const api = manager()
  let route: { fetch(request: Request): Promise<Response> } | undefined
  const scoped = { pluginManager: api, connection: { fetch: { register: (value: typeof route) => { route = value } } } }
  registerHostUpdater({ inject: (_: unknown, use: (ctx: unknown) => void) => use(scoped) } as never)
  api.updateBundle = async () => { route = undefined; return { result: { application: 'applied' } } }
  const response = await route!.fetch(new Request('http://localhost/api/cannbot-dsh/update', { method: 'POST', body: JSON.stringify({ name: 'cannbot-dsh', version: '1.0.0' }) }))
  expect((await response.json()).result.application).toBe('applied')
  expect(route).toBeUndefined()
})
it('keeps a visible result after the React plugin has unloaded', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => ({ result: { application: 'applied' } }) })))
  await updateOnHost('cannbot-dsh', '1.0.0')
  expect(document.querySelector('[data-cannbot-update]')?.textContent).toContain('1.0.0')
  expect(fetch).toHaveBeenCalledWith(expect.any(URL), expect.objectContaining({ method: 'POST', credentials: 'same-origin' }))
})
