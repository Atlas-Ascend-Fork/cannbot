// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { test } from 'node:test'
import assert from 'node:assert/strict'
import { mkdtempSync, readFileSync, writeFileSync, readdirSync, existsSync, rmSync } from 'node:fs'
import { join, dirname, resolve } from 'node:path'
import { tmpdir } from 'node:os'
import { spawnSync } from 'node:child_process'

test('standalone CMD extracts without a checkout and rejects a damaged payload', { skip: process.platform !== 'win32' }, () => {
  const root = mkdtempSync(join(tmpdir(), 'cannbot-setup-test-'))
  try {
    const file = join(root, "安装 包 & user's.cmd")
    const source = readFileSync(new URL('../CANNBot-Setup.cmd', import.meta.url), 'utf8')
    writeFileSync(file, source)
    const run = () => spawnSync('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', '& $env:CANNBOT_TEST_INSTALLER --extract-only; exit $LASTEXITCODE'], {
      cwd: root, encoding: 'utf8', windowsHide: true,
      env: { ...process.env, LOCALAPPDATA: root, CANNBOT_TEST_INSTALLER: file, DSH_SOURCE: '' },
    })
    const result = run()
    assert.equal(result.status, 0, result.stdout + result.stderr)
    const runs = join(root, 'CANNBot', 'Installer')
    const packageRoot = join(runs, readdirSync(runs)[0], 'package')
    for (const part of ['lib/index.js', 'lib/client.js', 'lib/initialize-workspace.js', 'release-policy.json', 'scripts/windows/provision.ps1', 'src/remote/artifact.js', 'remote/deploy-package.mjs']) assert.ok(existsSync(join(packageRoot, part)), part)
    for (const part of ['node_modules', '.git', '.dsh-source.json', 'scripts/build-current.mjs']) assert.equal(existsSync(join(packageRoot, part)), false, part)
    for (const part of ['lib/index.js', 'lib/client.js', 'README.md', 'THIRD_PARTY_NOTICES.md', 'scripts/windows/install-all.ps1', 'scripts/windows/provision.ps1', 'scripts/windows/ensure-workbench.mjs', 'scripts/windows/setup-window.cs', 'scripts/windows/setup-window.ps1']) {
      const normalized = bytes => bytes.toString('utf8').replaceAll('\r\n', '\n')
      assert.equal(normalized(readFileSync(join(packageRoot, part))), normalized(readFileSync(new URL('../' + part, import.meta.url))), `Regenerate the installer: ${part}`)
    }
    assert.deepEqual(readFileSync(join(packageRoot, 'LICENSE')), readFileSync(new URL('../../LICENSE', import.meta.url)))
    assert.deepEqual(JSON.parse(readFileSync(join(packageRoot, 'release-policy.json'))), JSON.parse(readFileSync(new URL('../release-policy.json', import.meta.url))))
    assert.deepEqual(readFileSync(join(packageRoot, 'scripts/windows/setup-logo.png')), readFileSync(new URL('../scripts/windows/setup-logo.png', import.meta.url)))
    assert.deepEqual(readFileSync(join(packageRoot, 'scripts/windows/setup-icon.ico')), readFileSync(new URL('../scripts/windows/setup-icon.ico', import.meta.url)))
    // Compile the packaged GUI with Windows PowerShell 5.1, without launching
    // installation. Exercise the real compile statements, including the icon.
    const compile = String.raw`
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$tokens = $null; $errors = $null
$TestScriptRoot = Join-Path $env:CANNBOT_TEST_PACKAGE 'scripts/windows'
$RunRoot = $env:CANNBOT_TEST_ROOT
$ast = [Management.Automation.Language.Parser]::ParseFile((Join-Path $TestScriptRoot 'setup-window.ps1'), [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw 'Invalid GUI launcher' }
foreach ($statement in $ast.EndBlock.Statements) {
    if ($statement.Extent.Text.StartsWith('$info =')) { break }
    Invoke-Expression ($statement.Extent.Text.Replace('$PSScriptRoot', '$TestScriptRoot'))
}
if (-not (Test-Path -LiteralPath $application)) { throw 'GUI executable missing' }
[void][Reflection.AssemblyName]::GetAssemblyName($application)
`
    const compiled = spawnSync('powershell.exe', ['-NoProfile', '-NonInteractive', '-EncodedCommand', Buffer.from(compile, 'utf16le').toString('base64')], {
      windowsHide: true, encoding: 'utf8', timeout: 30000,
      env: { ...process.env, CANNBOT_TEST_PACKAGE: packageRoot, CANNBOT_TEST_ROOT: root },
    })
    assert.equal(compiled.status, 0, compiled.stdout + compiled.stderr)
    const marker = '::CANNBOT_PAYLOAD\r\n', at = source.indexOf(marker) + marker.length
    writeFileSync(file, source.slice(0, at) + (source[at] === 'A' ? 'B' : 'A') + source.slice(at + 1))
    const damaged = run()
    assert.notEqual(damaged.status, 0)
    assert.match(damaged.stdout, /checksum mismatch/)
    assert.equal(readdirSync(runs).length, 1)
  } finally {
    assert.equal(dirname(resolve(root)), resolve(tmpdir()))
    rmSync(root, { recursive: true, force: true })
  }
})
