// ----------------------------------------------------------------------------------------------------------
// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.
// ----------------------------------------------------------------------------------------------------------

import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createPluginUpdater, newerVersion } from '../plugin/frontend/plugin-update.ts'
import { PluginUpdateCard } from '../plugin/frontend/PluginUpdateCard.tsx'
import { zh } from '../plugin/frontend/locales.ts'

afterEach(() => { cleanup(); vi.unstubAllGlobals() })
const t = (key: keyof typeof zh) => zh[key]
const available = { status: 'available', current: '1.0.0', buildId: 'release-1', version: '1.0.1', targetBuildId: 'release-2' }

describe('client plugin update entry', () => {
  it('checks on display and submits only the explicitly selected build', async () => {
    const fetcher = vi.fn(async (_url: URL, init: RequestInit) => Response.json(init.method === 'POST' ? { status: 'restart' } : available))
    vi.stubGlobal('fetch', fetcher)
    const updater = createPluginUpdater()
    render(<PluginUpdateCard updater={updater} t={t} />)
    const action = await screen.findByRole('button', { name: zh.updateTo + ' 1.0.1' })
    expect(fetcher).toHaveBeenCalledTimes(1)
    fireEvent.click(action); fireEvent.click(action)
    await screen.findByText(zh.updateRestart)
    expect(fetcher).toHaveBeenCalledTimes(2)
    const [url, init] = fetcher.mock.calls[1]
    expect(url.origin).toBe(location.origin)
    expect(JSON.parse(String(init.body))).toEqual({ version: '1.0.1', buildId: 'release-2' })
    updater.dispose()
  })
  it.each(['latest', 'unconfigured', 'agreement-required', 'incompatible'])('does not install when the release service reports %s', async status => {
    vi.stubGlobal('fetch', vi.fn(async () => Response.json({ status, current: '1.0.0' })))
    const updater = createPluginUpdater(); await updater.check(); await updater.update()
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(updater.getSnapshot()).toMatchObject({ phase: status, current: '1.0.0' })
    updater.dispose()
  })
  it('leaves the installed version visible after a failed network recheck', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(Response.json(available)).mockRejectedValueOnce(new Error()))
    const updater = createPluginUpdater(); await updater.check(); await updater.check(); await updater.update()
    expect(updater.getSnapshot()).toMatchObject({ phase: 'error', current: '1.0.0', release: undefined })
    updater.dispose()
  })
})

it('ignores hyphens in build metadata but promotes prereleases', () => {
  expect(newerVersion('1.0.0', '1.0.0+build-1')).toBe(false)
  expect(newerVersion('1.0.0', '1.0.0-rc.1+build-1')).toBe(true)
})
