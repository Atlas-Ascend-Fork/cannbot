// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
export const project = fileURLToPath(new URL('../', import.meta.url))
export function resolveSource(explicit) {
  const local = resolve(project, '.dsh-source.json')
  const saved = existsSync(local) ? JSON.parse(readFileSync(local, 'utf8')).path : undefined
  const source = resolve(explicit || process.env.DSH_SOURCE || saved || resolve(project, '../deepseek-harness'))
  const manifest = JSON.parse(readFileSync(resolve(source, 'package.json'), 'utf8'))
  if (manifest.name !== '@deepseek-ai/dsh-root' || manifest.version !== '0.2.1-rc.3') throw new Error('Use the official DSH 0.2.1-rc.3 source checkout.')
  return source
}
