// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { existsSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

// Works both from src/remote during tests and from the compiled Host bundle.
export function packageRoot(start = import.meta.url) {
  let directory = dirname(fileURLToPath(start))
  while (true) {
    const manifest = join(directory, 'package.json')
    if (existsSync(manifest)) {
      try { if (JSON.parse(readFileSync(manifest, 'utf8')).name === '@cannbot-plugin/cannbot-dsh') return directory } catch {}
    }
    const parent = dirname(directory)
    if (parent === directory) throw new Error('Cannot locate the CANNBot DSH package')
    directory = parent
  }
}

export const packageVersion = JSON.parse(readFileSync(join(packageRoot(), 'package.json'), 'utf8')).version
