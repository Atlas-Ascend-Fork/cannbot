// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { test } from 'node:test'
import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, readdirSync, rmSync } from 'node:fs'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { fileURLToPath } from 'node:url'

const installer = fileURLToPath(new URL('../../scripts/windows/install-all.ps1', import.meta.url))
const windows = { skip: process.platform !== 'win32' }
function prepare(t, files = {}) {
  const root = mkdtempSync(join(tmpdir(), 'cannbot-profile-'))
  t.after(() => rmSync(root, { recursive: true, force: true }))
  const profile = join(root, "中文 user's profile", 'profiles', 'desktop')
  mkdirSync(profile, { recursive: true })
  for (const [name, value] of Object.entries(files)) writeFileSync(join(profile, name), value)
  const script = String.raw`
$ErrorActionPreference = 'Stop'
$tokens = $null; $errors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile($env:TEST_INSTALLER, [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw 'PowerShell 5.1 parse failure' }
foreach ($statement in $ast.EndBlock.Statements) {
    if ($statement -is [Management.Automation.Language.FunctionDefinitionAst]) { Invoke-Expression $statement.Extent.Text }
}
function Start-Process { throw 'Profile initialization must not launch a window' }
function Stop-DshIfRunning { throw 'Profile initialization must not stop an app' }
function Read-Host { throw 'Profile initialization must not prompt for login' }
$profilePkg = Join-Path $env:TEST_PROFILE 'package.json'
if (-not (Ensure-Profile 'Z:\NoDesktopInstalled\DeepSeek Harness.exe')) { throw 'Profile not created' }
if (-not (Ensure-Profile 'Z:\NoDesktopInstalled\DeepSeek Harness.exe')) { throw 'Repeat initialization failed' }
`
  const result = spawnSync('powershell.exe', ['-NoProfile', '-NonInteractive', '-EncodedCommand', Buffer.from(script, 'utf16le').toString('base64')], {
    windowsHide: true, encoding: 'utf8', timeout: 15000, env: { ...process.env, TEST_INSTALLER: installer, TEST_PROFILE: profile },
  })
  assert.ifError(result.error)
  assert.equal(result.status, 0, result.stdout + result.stderr)
  assert.equal(readdirSync(profile).some(name => name.endsWith('.tmp')), false)
  for (const [name, value] of Object.entries(files)) assert.equal(readFileSync(join(profile, name), 'utf8'), value)
  return profile
}

test('first install creates native Desktop metadata without launching or asking for login', windows, t => {
  const profile = prepare(t)
  const manifest = readFileSync(join(profile, 'package.json'), 'utf8')
  assert.notEqual(manifest.charCodeAt(0), 0xfeff)
  assert.deepEqual(JSON.parse(manifest), { name: 'dsh-profile-desktop', private: true, dependencies: {}, dsh: { profile: { bundles: ['@deepseek-ai/dsh-base', '@deepseek-ai/dsh-web-app'] } } })
  assert.equal(readFileSync(join(profile, 'cordis.patch.yml'), 'utf8'), '[]\n')
  assert.equal(readFileSync(join(profile, 'pnpm-workspace.yaml'), 'utf8'), 'packages:\n  - .\n\nnodeLinker: hoisted\nautoInstallPeers: false\n')
})

test('initialization preserves partial and existing user configuration byte for byte', windows, t => {
  prepare(t, { 'cordis.patch.yml': '# user settings\n[]\n', 'pnpm-workspace.yaml': 'nodeLinker: hoisted\n# custom\n' })
  const profile = prepare(t, { 'package.json': '{"custom":true}', 'cordis.patch.yml': '# retained\n[]\n' })
  assert.deepEqual(readdirSync(profile).sort(), ['cordis.patch.yml', 'package.json'])
})
