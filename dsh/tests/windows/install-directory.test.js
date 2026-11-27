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
import { fileURLToPath } from 'node:url'

test('selected path is passed literally to interactive host installer, and invalid paths fail before launch', { skip: process.platform !== 'win32' }, () => {
  const script = String.raw`
$ErrorActionPreference='Stop'
$tokens=$null; $errors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile($env:TEST_INSTALLER,[ref]$tokens,[ref]$errors)
if($errors.Count){throw 'PowerShell parse failure'}
foreach($statement in $ast.EndBlock.Statements){if($statement -is [Management.Automation.Language.FunctionDefinitionAst]){Invoke-Expression $statement.Extent.Text}}
$ProgressPath=''
$InstallDirectory="D:\apps\CANNBot & user's folder"
$script:captured=$null
function Start-Process { param($FilePath,$ArgumentList,[switch]$PassThru,[switch]$Wait); $script:captured=@{FilePath=$FilePath;ArgumentList=$ArgumentList}; return @{ExitCode=0} }
function Start-Sleep { }
function Find-Dsh { return 'D:\apps\host.exe' }
if((Install-Dsh 'D:\downloads\official.exe') -ne 'D:\apps\host.exe'){throw 'Wrong executable'}
if($captured.ArgumentList -cne ('/D='+$InstallDirectory)){throw 'Path not passed literally'}
if($captured.ArgumentList -match '(?i)/S\b'){throw 'Must not silently accept official terms'}
foreach($bad in @('C:\','relative','C:\one\..\two','C:\bad"path',('C:\bad' + [char]10 + 'path'))) {
  $failed=$false; try {Assert-InstallDirectory $bad} catch {$failed=$true}
  if(-not $failed){throw ('Accepted invalid folder: '+$bad)}
}
$InstallDirectory=''
$null=Install-Dsh 'D:\downloads\official.exe'
if($captured.ArgumentList){throw 'Default path must stay unset for legacy CLI callers'}
'PASS'
`
  const result = spawnSync('powershell.exe', ['-NoProfile', '-NonInteractive', '-EncodedCommand', Buffer.from(script, 'utf16le').toString('base64')], { encoding: 'utf8', windowsHide: true, env: { ...process.env, TEST_INSTALLER: fileURLToPath(new URL('../../installers/windows/install-all.ps1', import.meta.url)) } })
  assert.equal(result.status, 0, result.stdout + result.stderr)
})
