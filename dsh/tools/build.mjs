// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { spawnSync } from 'node:child_process'
import { resolve } from 'node:path'
import { project, resolveSource } from './source.mjs'
const checkout = resolveSource()
const result = spawnSync(process.execPath, [resolve(checkout, 'node_modules/tsdown/dist/run.mjs'), '--config-loader', 'native', '--config', 'tsdown.config.ts'], {
  cwd: project, stdio: 'inherit', env: { ...process.env, DSH_CLIENT_BUILD_PROFILE: 'local' },
})
process.exit(result.status ?? 1)
