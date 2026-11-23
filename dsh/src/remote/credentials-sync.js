// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

// Credentials stay in the Host and travel only through the SSH process's stdin.
import { readFileSync } from 'node:fs'
import { pathToFileURL } from 'node:url'
import { packageRoot } from './package-root.js'
import { sshArgs } from './bootstrap.js'
import { run, shQuote } from './exec.js'

export const ACCOUNT_RECORD_KEY = 'deepseek-account-platform/default'
export const MAX_CREDENTIAL_BYTES = 64 * 1024
export const CREDENTIALS_SCRIPT_URL = new URL('remote/sync-credentials.mjs', pathToFileURL(packageRoot() + '/'))

const messages = Object.freeze({
  synced: '已同步本机 模型账号登录状态。',
  unchanged: '远端已使用相同的 模型账号登录状态。',
  'remote-preserved': '远端已有账号登录信息，已保留；未覆盖远端账号。',
  'local-missing': '本机未登录 模型账号，已跳过同步；可在远端工作台 中登录。',
  unsupported: '当前账号凭据或远端存储格式不支持自动同步；可在远端工作台 中登录。',
  failed: '模型账号同步未完成；连接可继续，可在远端工作台 中登录。',
})

function summary(status) {
  return { status, message: messages[status] }
}

/** Project only the supported account grant; never forward other record fields. */
function accountGrant(record) {
  if (!record || record.kind !== 'grant') return null
  const payload = record.payload
  if (!payload || payload.version !== 1 || payload.issuer !== 'https://platform.deepseek.com'
    || typeof payload.token !== 'string' || !/^[\x21-\x7e]+$/.test(payload.token)
    || payload.token.startsWith('dsh_mock_')) return null
  return { kind: 'grant', payload: { version: 1, token: payload.token, issuer: payload.issuer } }
}

/** No secret may be inserted into this command, its arguments, or its environment. */
export function credentialsSshInvocation({ server, binary = 'ssh', profile = 'web' }) {
  const { command, args, target } = sshArgs({ server, binary })
  const source = readFileSync(CREDENTIALS_SCRIPT_URL, 'utf8').replace(/^\uFEFF/, '').replace(/\r\n/g, '\n')
    + '\nawait runRemoteSync({ dshExecutable: process.argv[1], profile: process.argv[2] });\n'
  const remoteCommand = 'export PATH="$HOME/.local/bin:$PATH"; '
    + `node --input-type=module -e ${shQuote(source)} -- "$(command -v dsh)" ${shQuote(profile)}`
  return { command, args: [...args, target, remoteCommand] }
}

/**
 * Best-effort, non-destructive DeepSeek account sync after remote bootstrap.
 * The callback reads the Host credential service, never browser state or files.
 */
export async function syncCredentials({ server, binary = 'ssh', exec = run, readLocalRecord, profile = 'web' } = {}) {
  if (typeof readLocalRecord !== 'function') return summary('unsupported')
  try {
    const record = await readLocalRecord(ACCOUNT_RECORD_KEY)
    if (record == null) return summary('local-missing')
    const grant = accountGrant(record)
    if (!grant) return summary('unsupported')
    const input = JSON.stringify(grant)
    if (Buffer.byteLength(input, 'utf8') > MAX_CREDENTIAL_BYTES) return summary('unsupported')
    const invocation = credentialsSshInvocation({ server, binary, profile })
    const result = await exec(invocation.command, invocation.args, { input, timeoutMs: 45_000 })
    if (!result || result.code !== 0 || result.timedOut) return summary('failed')
    // Read only our closed protocol. Never expose arbitrary SSH output or errors.
    const matches = String(result.stdout || '').split(/\r?\n/)
      .map(line => /^CANNBOT_CREDENTIALS_STATUS=(synced|unchanged|remote-preserved|unsupported|failed)$/.exec(line))
      .filter(Boolean)
    if (matches.length !== 1) return summary('failed')
    return summary(matches[0][1])
  } catch {
    return summary('failed')
  }
}
