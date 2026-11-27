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
import { mkdtempSync, mkdirSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { tmpdir } from 'node:os'
import { fileURLToPath } from 'node:url'

const installer = fileURLToPath(new URL('../../installers/windows/install-all.ps1', import.meta.url))
const provision = fileURLToPath(new URL('../../installers/windows/provision.ps1', import.meta.url))
const windowsOnly = { skip: process.platform !== 'win32' && 'requires Windows PowerShell 5.1' }

function check(t, { bom = false, complete = true, profileExists = true } = {}) {
  const home = mkdtempSync(join(tmpdir(), 'cannbot-install-check-'))
  t.after(() => rmSync(home, { recursive: true, force: true }))
  const profile = join(home, 'profiles', 'desktop', 'package.json')
  mkdirSync(dirname(profile), { recursive: true })
  const packageName = '@cannbot-plugin/cannbot-dsh'
  const bytes = Buffer.from((bom ? '\uFEFF' : '') + JSON.stringify({ dependencies: { [packageName]: '1.0.0-alpha.1' }, dsh: { profile: { bundles: [packageName] } } }))
  if (profileExists) writeFileSync(profile, bytes)
  if (complete) {
    const target = join(dirname(profile), 'node_modules', ...packageName.split('/'))
    mkdirSync(target, { recursive: true })
    writeFileSync(join(target, 'package.json'), JSON.stringify({ name: packageName, version: '1.0.0-alpha.1' }))
    for (const file of ['lib/index.js', 'lib/client.js', 'remote/sync-credentials.mjs', 'remote/deploy-package.mjs', 'cordis.patch.yml']) {
      mkdirSync(dirname(join(target, file)), { recursive: true }); writeFileSync(join(target, file), '')
    }
  }
  const before = readdirSync(dirname(profile)).sort()
  const script = String.raw`
$ErrorActionPreference = 'Stop'
$tokens = $null; $errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($env:CANNBOT_CHECK_INSTALLER, [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw 'PowerShell 5.1 parse failure' }
foreach ($statement in $ast.EndBlock.Statements) {
    if ($statement -is [System.Management.Automation.Language.FunctionDefinitionAst]) { Invoke-Expression $statement.Extent.Text }
}
# Isolate hardware/registry discovery. The main program and child provision
# check are real; no installer, process closure, build or SSH may be invoked.
function Find-Dsh { return 'D:\Fixture\DeepSeek Harness.exe' }
function Get-UninstallEntries { return @() }
function Get-InstalledVersion { return '' }
function Stop-DshIfRunning { throw 'Check must never close DSH' }
function Download-Installer { throw 'Check must never download' }
function Install-Dsh { throw 'Check must never install DSH' }
function Ensure-Profile { throw 'Check must never create a profile' }
$Check = $true; $Upgrade = $false
$profilePkg = $env:CANNBOT_CHECK_PROFILE
$provisionScript = $env:CANNBOT_CHECK_PROVISION
$installerUrl = 'https://example.invalid/never-requested'
$source = [IO.File]::ReadAllText($env:CANNBOT_CHECK_INSTALLER)
$main = $source.Substring($source.IndexOf('# ---------------------------------------------------------------- main'))
Invoke-Expression $main
`
  const result = spawnSync('powershell.exe', ['-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-EncodedCommand', Buffer.from(script, 'utf16le').toString('base64')], {
    env: { ...process.env, DSH_HOME: home, CANNBOT_CHECK_INSTALLER: installer, CANNBOT_CHECK_PROVISION: provision, CANNBOT_CHECK_PROFILE: profile }, encoding: 'utf8', windowsHide: true, timeout: 30_000,
  })
  assert.ifError(result.error)
  assert.deepEqual(readdirSync(dirname(profile)).sort(), before, 'read-only check creates no backup or profile files')
  if (profileExists) assert.deepEqual(readFileSync(profile), bytes)
  return result
}

test('one-click Check invokes real provisioning checks and reports a complete profile', windowsOnly, t => {
  const result = check(t)
  assert.equal(result.status, 0, result.stdout + result.stderr)
  assert.match(result.stdout, /CHECK PASSED/)
  assert.match(result.stdout, /UTF-8 without BOM/)
})

test('one-click Check propagates BOM and missing-package failures without claiming success', windowsOnly, t => {
  for (const scenario of [{ bom: true }, { complete: false }, { profileExists: false }]) {
    const result = check(t, scenario)
    assert.equal(result.status, 1, result.stdout + result.stderr)
    assert.doesNotMatch(result.stdout, /CHECK PASSED|DONE -/)
    if (scenario.bom) assert.match(result.stdout, /UTF-8 BOM/)
  }
})
