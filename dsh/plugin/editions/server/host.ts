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
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { packageRoot } from '../../backend/package-root.js'
import { apply as applyWorkbench, type Config } from '../../backend/index.ts'
export { Config, inject } from '../../backend/index.ts'

export async function apply(ctx: Context, config: Config = {}): Promise<void> {
  if (process.platform !== 'linux') throw new Error('CANNBot Server requires Linux.')
  await applyWorkbench(ctx, config)
  const { version, cannbotBuildId: buildId } = JSON.parse(readFileSync(join(packageRoot(), 'package.json'), 'utf8'))
  ctx.inject(['connection'], scoped => {
    scoped.connection.fetch?.register?.({ path: '/api/cannbot-dsh/server', methods: ['GET'], requestBody: 'buffered',
      fetch: async () => Response.json({ edition: 'server', version, buildId }, { headers: { 'cache-control': 'no-store' } }),
    })
  })
}
