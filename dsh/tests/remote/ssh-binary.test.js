// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { test } from 'node:test'
import assert from 'node:assert/strict'
import { mkdirSync, writeFileSync, rmSync } from 'node:fs'
import { join } from 'node:path'
import { parseVsCodeSshPath, resolveSshBinary, vsCodeSettingsPath } from '../../plugin/backend/ssh/ssh-binary.js'

const SCRATCH = join(process.cwd(), '_scratch', 'ssh-binary')

function writeSettings(text) {
  rmSync(SCRATCH, { recursive: true, force: true })
  mkdirSync(SCRATCH, { recursive: true })
  const file = join(SCRATCH, 'settings.json')
  writeFileSync(file, text, 'utf8')
  return file
}

test('parseVsCodeSshPath reads a plain JSON value', () => {
  assert.equal(parseVsCodeSshPath('{"remote.SSH.path": "C:\\\\Program Files\\\\Git\\\\usr\\\\bin\\\\ssh.exe"}'), 'C:\\Program Files\\Git\\usr\\bin\\ssh.exe')
})

test('parseVsCodeSshPath tolerates JSONC comments and other settings', () => {
  const jsonc = `{
    // remote settings
    "remote.SSH.path": "D:\\\\Tools\\\\ssh.exe",
    "editor.fontSize": 14,
    /* block comment */
    "files.autoSave": "onFocusChange"
  }`
  assert.equal(parseVsCodeSshPath(jsonc), 'D:\\Tools\\ssh.exe')
})

test('parseVsCodeSshPath returns empty when the setting is absent', () => {
  assert.equal(parseVsCodeSshPath('{"editor.fontSize": 14}'), '')
  assert.equal(parseVsCodeSshPath(''), '')
  assert.equal(parseVsCodeSshPath(null), '')
})

test('resolveSshBinary prefers CANNBOT_REMOTE_SSH', () => {
  const previousOverride = process.env.CANNBOT_REMOTE_SSH
  const previousSettings = process.env.CANNBOT_REMOTE_VSCODE_SETTINGS
  try {
    process.env.CANNBOT_REMOTE_SSH = 'C:\\custom\\ssh.exe'
    process.env.CANNBOT_REMOTE_VSCODE_SETTINGS = writeSettings('{"remote.SSH.path":"C:\\\\ignored\\\\ssh.exe"}')
    assert.equal(resolveSshBinary(), 'C:\\custom\\ssh.exe')
  } finally {
    process.env.CANNBOT_REMOTE_SSH = previousOverride
    process.env.CANNBOT_REMOTE_VSCODE_SETTINGS = previousSettings
  }
})

test('resolveSshBinary honours VS Code remote.SSH.path only when it exists', () => {
  const previousOverride = process.env.CANNBOT_REMOTE_SSH
  const previousSettings = process.env.CANNBOT_REMOTE_VSCODE_SETTINGS
  try {
    delete process.env.CANNBOT_REMOTE_SSH

    const existing = writeSettings('{"remote.SSH.path":"' + process.execPath.replace(/\\/g, '\\\\') + '"}')
    process.env.CANNBOT_REMOTE_VSCODE_SETTINGS = existing
    assert.equal(resolveSshBinary(), process.execPath)

    // A stale path (the classic "Git was moved/uninstalled" case) must fall back to ssh.
    process.env.CANNBOT_REMOTE_VSCODE_SETTINGS = writeSettings('{"remote.SSH.path":"D:\\\\gone\\\\ssh.exe"}')
    assert.equal(resolveSshBinary(), 'ssh')
  } finally {
    process.env.CANNBOT_REMOTE_SSH = previousOverride
    process.env.CANNBOT_REMOTE_VSCODE_SETTINGS = previousSettings
  }
})

test('vsCodeSettingsPath can be redirected for tests and reports', () => {
  const previous = process.env.CANNBOT_REMOTE_VSCODE_SETTINGS
  try {
    process.env.CANNBOT_REMOTE_VSCODE_SETTINGS = 'X:\\custom\\settings.json'
    assert.equal(vsCodeSettingsPath(), 'X:\\custom\\settings.json')
  } finally {
    process.env.CANNBOT_REMOTE_VSCODE_SETTINGS = previous
  }
})
