// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

// Which ssh binary should we spawn?
//
// Order: CANNBOT_REMOTE_SSH override -> VS Code's remote.SSH.path (only when the
// file actually exists, because a stale setting must not break us) -> `ssh` on
// PATH. VS Code users often point remote.SSH.path at Git's bundled OpenSSH, so
// honouring it keeps our transport identical to the editor they already use.
import { readFileSync, existsSync } from 'node:fs'
import { join } from 'node:path'
import { homedir } from 'node:os'

export function vsCodeSettingsPath() {
  if (process.env.CANNBOT_REMOTE_VSCODE_SETTINGS) {
    return process.env.CANNBOT_REMOTE_VSCODE_SETTINGS
  }
  const appData = process.env.APPDATA || join(homedir(), 'AppData', 'Roaming')
  return join(appData, 'Code', 'User', 'settings.json')
}

/** Pull `remote.SSH.path` out of a VS Code settings file (JSONC tolerant). */
export function parseVsCodeSshPath(text) {
  const match = /"remote\.SSH\.path"\s*:\s*"((?:[^"\\]|\\.)*)"/.exec(String(text || ''))
  if (!match) return ''
  try {
    return JSON.parse(`"${match[1]}"`)
  } catch {
    return ''
  }
}

export function resolveSshBinary() {
  const override = process.env.CANNBOT_REMOTE_SSH && process.env.CANNBOT_REMOTE_SSH.trim()
  if (override) return override.trim()
  try {
    const settings = readFileSync(vsCodeSettingsPath(), 'utf8')
    const candidate = parseVsCodeSshPath(settings)
    if (candidate && existsSync(candidate)) return candidate
  } catch { /* no VS Code settings: fall through */ }
  return 'ssh'
}
