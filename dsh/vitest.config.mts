// ----------------------------------------------------------------------------------------------------------
// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.
// ----------------------------------------------------------------------------------------------------------

import { defineConfig } from 'vitest/config'
import { fileURLToPath } from 'node:url'
import { resolveSource } from './scripts/source.mjs'

const local = (path: string) => fileURLToPath(new URL(path, import.meta.url))

export default defineConfig({
  root: local('./'),
  resolve: { alias: [
    // Source resolution shares the pinned checkout used by prepare-dev/build.
    { find: '@dsh-test-source', replacement: resolveSource().replaceAll('\\', '/') },
    // Execute the real StateDot/Toast CSS in jsdom. Individual suites may mock
    // this facade, while native integration suites import public source directly.
    { find: '@deepseek-ai/dsh-client-ui-primitives', replacement: local('./tests/fixtures/ui-primitives.ts') },
    { find: '@deepseek-ai/dsh-client-ui-slots', replacement: local('./node_modules/@deepseek-ai/dsh-client-ui-slots/lib/index.js') },
    { find: '@deepseek-ai/dsh-client-store', replacement: local('./node_modules/@deepseek-ai/dsh-client-store/lib/index.js') },
    { find: '@deepseek-ai/cordis', replacement: local('./node_modules/@deepseek-ai/cordis/lib/index.js') },
  ] },
  test: {
    environment: 'jsdom', include: ['tests/**/*.spec.{ts,tsx}'], maxWorkers: 2,
    server: { deps: { inline: [/@deepseek-ai[\\/]/] } },
  },
})
