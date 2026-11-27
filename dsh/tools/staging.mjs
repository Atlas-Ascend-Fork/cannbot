// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

export async function withStaging(prefix, action) {
  const directory = mkdtempSync(join(tmpdir(), prefix))
  const abort = new AbortController()
  const interrupt = () => { process.exitCode = 130; abort.abort(new Error('Interrupted')) }
  const terminate = () => { process.exitCode = 143; abort.abort(new Error('Terminated')) }
  process.on('SIGINT', interrupt)
  process.on('SIGTERM', terminate)
  try { return await action(directory, abort.signal) }
  finally {
    rmSync(directory, { recursive: true, force: true })
    process.removeListener('SIGINT', interrupt)
    process.removeListener('SIGTERM', terminate)
  }
}
