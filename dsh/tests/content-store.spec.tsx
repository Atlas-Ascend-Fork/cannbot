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
import { createContentStore } from '../src/client/content-store.ts'

afterEach(() => vi.unstubAllGlobals())
it('does not publish an older polling response after an operation refresh', async () => {
  let oldResponse!: (value: unknown) => void
  const old = new Promise(resolve => { oldResponse = resolve })
  const snapshot = (version: string) => ({ ok: true, json: async () => ({ plugins: [{ id: 'flow-a', title: version }], version }) })
  vi.stubGlobal('fetch', vi.fn().mockReturnValueOnce(old).mockResolvedValueOnce({ ok: true }).mockResolvedValueOnce(snapshot('new')))
  const store = createContentStore(), stop = store.start()
  try {
    await store.check()
    expect(store.getSnapshot().workflows[0].title).toBe('new')
    oldResponse(snapshot('old'))
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(store.getSnapshot().workflows[0].title).toBe('new')
  } finally { stop() }
})
