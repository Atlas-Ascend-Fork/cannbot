// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { createArtifact } from './artifact.js'
import { packageRoot } from './package-root.js'
import { sshArgs, parseBootstrapOutput } from './bootstrap.js'
import { run, shQuote } from './exec.js'

export async function deployCurrentPackage({ server, binary, profile = 'web', registry = '', remotePort, ascendEnv = '', exec = run, artifact = createArtifact(), progress = () => {} }) {
  const script = readFileSync(join(packageRoot(), 'remote/deploy-package.mjs'), 'utf8')
  const invocation = sshArgs({ server, binary })
  const environment = ascendEnv ? 'if [ -f ' + shQuote(ascendEnv) + ' ]; then . ' + shQuote(ascendEnv) + ' >/dev/null 2>&1; fi; ' : ''
  const command = 'export PATH="$HOME/.local/bin:$PATH"; ' + environment + 'node --input-type=module -e ' + shQuote(script) + ' ' + [artifact.hash, profile, String(remotePort || ''), registry].map(shQuote).join(' ')
  const result = await exec(invocation.command, [...invocation.args, invocation.target, command], {
    input: artifact.bytes, timeoutMs: 15 * 60 * 1000,
    onLine(line) { if (line.startsWith('CANNBOT_STEP=')) progress(line.slice(13)) },
  })
  const parsed = parseBootstrapOutput(result.stdout || '')
  if (result.code !== 0 || !parsed.ok || !parsed.token) throw new Error(parsed.error || '当前 CANNBot 主插件同步失败，请检查远端服务与安装日志后重试。')
  return { ...parsed, sourceHash: artifact.hash }
}
