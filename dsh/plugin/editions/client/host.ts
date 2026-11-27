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
import { apply as applyWorkbench, type Config } from '../../backend/index.ts'
import { registerHostUpdater } from '../../backend/update-host.ts'
import { registerRemoteTree } from '../../backend/remote-tree.ts'
import { registerRemote } from '../../backend/ssh/register.js'
export { Config, inject } from '../../backend/index.ts'

export async function apply(ctx: Context, config: Config = {}): Promise<void> {
  registerHostUpdater(ctx)
  registerRemoteTree(ctx, registerRemote(ctx))
  await applyWorkbench(ctx, config)
}
