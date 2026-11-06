// ----------------------------------------------------------------------------------------------------------
// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.
// ----------------------------------------------------------------------------------------------------------

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createPluginUpdater, latestRelease, newerVersion, type Release, type UpdateBridge } from '../src/client/plugin-update.ts'
import { PluginUpdateCard } from '../src/client/PluginUpdateCard.tsx'
import { zh } from '../src/client/locales.ts'

afterEach(() => { cleanup(); vi.unstubAllGlobals() })
const target: Release = { name: 'cannbot-dsh', version: '1.0.0', tarball: 'https://registry.npmjs.org/cannbot-dsh/-/cannbot-dsh-1.0.0.tgz' }
const t = (key: keyof typeof zh) => zh[key]
function bridge(): UpdateBridge {
  return { list: vi.fn(async () => [{ name: 'cannbot-dsh', version: '1.0.0-alpha.1', installed: true }]), install: vi.fn(async () => ({ application: 'applied' })) }
}

describe('plugin update entry', () => {
  it('checks without installing and installs the exact latest version only on explicit click', async () => {
    const api = bridge(), updater = createPluginUpdater(api, 'cannbot-dsh', async () => target)
    render(<PluginUpdateCard updater={updater} t={t} />)
    const action = await screen.findByRole('button', { name: `${zh.updateTo} 1.0.0` })
    expect(screen.getByText(`${zh.updateCurrent} 1.0.0-alpha.1`)).toBeTruthy()
    expect(api.install).not.toHaveBeenCalled()
    fireEvent.click(action)
    await waitFor(() => expect(api.install).toHaveBeenCalledExactlyOnceWith('cannbot-dsh@1.0.0'))
    await screen.findByText(zh.updateDone)
    updater.dispose()
  })
  it('prefers the official update transaction when supplied', async () => {
    const api = { ...bridge(), update: vi.fn(async () => ({ result: { application: 'restart-required' } })) }
    const updater = createPluginUpdater(api, 'cannbot-dsh', async () => target)
    await updater.check(); await updater.update()
    expect(api.update).toHaveBeenCalledWith('cannbot-dsh', '1.0.0')
    expect(api.install).not.toHaveBeenCalled()
    expect(updater.getSnapshot().phase).toBe('restart')
  })
  it('uses the installed short entry instead of changing to its transitive core dependency', async () => {
    const api = bridge(), lookup = vi.fn(async () => target)
    const updater = createPluginUpdater(api, '@cannbot-plugin/cannbot-dsh', lookup)
    await updater.check(); await updater.update()
    expect(lookup).toHaveBeenCalledWith('cannbot-dsh', expect.any(AbortSignal))
    expect(api.install).toHaveBeenCalledWith('cannbot-dsh@1.0.0')
  })
  it('does not remove a plugin when the official HMR guard requires manual installation', async () => {
    const api = bridge()
    api.install = vi.fn(async () => ({ application: 'failed', error: { code: 'already-installed' } }))
    const updater = createPluginUpdater(api, 'cannbot-dsh', async () => target)
    render(<PluginUpdateCard updater={updater} t={t} />)
    fireEvent.click(await screen.findByRole('button', { name: `${zh.updateTo} 1.0.0` }))
    const link = await screen.findByRole('link', { name: `${zh.updateDownload} 1.0.0` })
    expect(link.getAttribute('href')).toBe(target.tarball)
    expect(screen.getByText(zh.updateManual)).toBeTruthy()
    expect(updater.getSnapshot().current).toBe('1.0.0-alpha.1')
    updater.dispose()
  })
  it('never reports cancellation or incompatibility as a completed update', async () => {
    for (const result of [{ application: 'cancelled' }, { application: 'failed', error: { code: 'incompatible-version' } }]) {
      const api = bridge(); api.install = vi.fn(async () => result)
      const updater = createPluginUpdater(api, 'cannbot-dsh', async () => target)
      await updater.check(); await updater.update()
      expect(['error', 'incompatible']).toContain(updater.getSnapshot().phase)
      expect(updater.getSnapshot().current).toBe('1.0.0-alpha.1')
    }
  })
  it('does not downgrade or reinstall an existing release', async () => {
    expect(newerVersion('1.0.10', '1.0.9')).toBe(true)
    expect(newerVersion('1.0.0', '1.0.1')).toBe(false)
    expect(newerVersion('1.0.1', '1.0.1')).toBe(false)
    const api = bridge(), updater = createPluginUpdater(api, 'cannbot-dsh', async () => ({ ...target, version: '1.0.0-alpha.1' }))
    await updater.check(); await updater.update()
    expect(updater.getSnapshot().phase).toBe('latest')
    expect(api.install).not.toHaveBeenCalled()
  })
  it('checks both public registries and picks the newest stable release with a trusted download URL', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => ({ ok: true, json: async () => ({
      name: 'cannbot-dsh', version: url.includes('npmmirror') ? '1.0.0' : '1.0.1', dsh: { bundle: {} }, dist: { tarball: target.tarball },
    }) })))
    const release = await latestRelease('cannbot-dsh', new AbortController().signal)
    expect(release.version).toBe('1.0.1')
    expect(fetch).toHaveBeenCalledTimes(2)
  })
  it('refuses an unrelated package or untrusted download link', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => ({
      name: 'cannbot-dsh', version: '1.0.0', dsh: { bundle: {} }, dist: { tarball: 'https://unrelated.example/download' },
    }) })))
    await expect(latestRelease('cannbot-dsh', new AbortController().signal)).rejects.toThrow('No release available')
    await expect(latestRelease('unrelated-package', new AbortController().signal)).rejects.toThrow('Unsupported update target')
  })
})

it('ignores hyphens in build metadata but promotes prereleases', () => {
  expect(newerVersion('1.0.0', '1.0.0+build-1')).toBe(false)
  expect(newerVersion('1.0.0', '1.0.0-rc.1+build-1')).toBe(true)
})
