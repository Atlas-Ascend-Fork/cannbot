// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { packageRoot } from '../package-root.js'
import { sshArgs, parseBootstrapOutput } from './bootstrap.js'
import { run, shQuote } from './exec.js'

export function pairedServer(root = packageRoot()) {
  const client = JSON.parse(readFileSync(join(root, 'package.json'), 'utf8'))
  const server = JSON.parse(readFileSync(join(root, 'remote/server.json'), 'utf8'))
  if (client.cannbotEdition !== 'client' || server.name !== '@cannbot-plugin/cannbot-dsh-server' || !client.cannbotBuildId || server.buildId !== client.cannbotBuildId || server.version !== client.version) {
    throw new Error('客户端和配套服务器版的发布标识不一致。')
  }
  const bytes = readFileSync(join(root, 'remote/server.tgz'))
  return { bytes, version: server.version, buildId: server.buildId }
}

export async function deployCurrentPackage({ server, binary, registry = '', remotePort, ascendEnv = '', exec = run, artifact = pairedServer(), progress = () => {} }) {
  const profile = 'cannbot-server-' + artifact.buildId
  const script = readFileSync(join(packageRoot(), 'remote/deploy-package.mjs'), 'utf8')
  const invocation = sshArgs({ server, binary })
  const environment = ascendEnv ? 'if [ -f ' + shQuote(ascendEnv) + ' ]; then . ' + shQuote(ascendEnv) + ' >/dev/null 2>&1; fi; ' : ''
  const args = ['cannbot-deploy', artifact.buildId, artifact.version, String(remotePort || ''), registry].map(shQuote).join(' ')
  const command = 'export PATH="$HOME/.local/bin:$PATH"; ' + environment + 'node --input-type=module -e ' + shQuote(script) + ' -- ' + args
  const invoke = input => exec(invocation.command, [...invocation.args, invocation.target, command], {
    input, timeoutMs: 15 * 60 * 1000,
    onLine(line) { if (line.startsWith('CANNBOT_STEP=')) progress(line.slice(13)) },
  })
  let result = await invoke(Buffer.alloc(0))
  if (result.code === 0 && /^CANNBOT_NEED_ARCHIVE=1$/m.test(result.stdout || '')) result = await invoke(artifact.bytes)
  const parsed = parseBootstrapOutput(result.stdout || '')
  if (result.code !== 0 || !parsed.ok || !parsed.token || !parsed.remotePort || parsed.pluginVersion !== artifact.version || !String(result.stdout).split(/\r?\n/).includes('CANNBOT_BUILD_ID=' + artifact.buildId)) {
    throw new Error(parsed.error || 'CANNBot 服务器版同步失败，请检查远端服务与安装日志后重试。')
  }
  return { ...parsed, profile, buildId: artifact.buildId }
}
