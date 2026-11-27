// ----------------------------------------------------------------------------------------------------------
// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.
// ----------------------------------------------------------------------------------------------------------

import { expect, it, vi } from 'vitest'
import { createHostUpdater } from '../plugin/backend/update-host.ts'

const installed = {
  version: '1.0.0', buildId: 'build-1', hostVersion: '0.2.1',
  receipt: { schemaVersion: 1, edition: 'client', version: '1.0.0', buildId: 'build-1', acceptedAt: '2026-11-11T00:00:00Z', legalVersion: '1' },
}
const release = {
  manifest: { version: '1.0.1', buildId: 'build-2', dshRange: '>=0.2.0 <0.3.0', legal: { version: '1' }, packages: { client: { url: 'https://example.test/client.tgz' } } },
}

it('checks without mutation and binds confirmation to the exact current published build', async () => {
  const activate = vi.fn(async () => ({ application: 'restart-required' }))
  const update = createHostUpdater({ current: async () => installed, release: async () => release, activate })
  expect(await update()).toMatchObject({ status: 'available', current: '1.0.0', targetBuildId: 'build-2' })
  expect((await update({ buildId: 'yesterday', version: '1.0.1' })).status).toBe('stale')
  expect(activate).not.toHaveBeenCalled()
  expect((await update(release.manifest)).status).toBe('restart')
  expect(activate).toHaveBeenCalledOnce()
})

it('requires the installer for new legal text and refuses same-version replacements or downgrades', async () => {
  const activate = vi.fn(async () => ({ application: 'applied' }))
  for (const [patch, expected] of [
    [{ version: '0.9.0' }, 'latest'], [{ version: '1.0.0' }, 'error'], [{ buildId: 'build-1' }, 'error'],
    [{ legal: { version: '2' } }, 'agreement-required'],
    [{ dshRange: '>=1.0.0 <2.0.0' }, 'incompatible'],
  ] as const) {
    const manifest = { ...release.manifest, ...patch }
    const update = createHostUpdater({ current: async () => installed, release: async () => ({ ...release, manifest }), activate })
    expect((await update(manifest)).status).toBe(expected)
  }
  const unconfigured = createHostUpdater({ current: async () => installed, release: async () => undefined, activate })
  expect((await unconfigured()).status).toBe('unconfigured')
  expect(activate).not.toHaveBeenCalled()
})
