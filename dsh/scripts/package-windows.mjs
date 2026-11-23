// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { mkdtemp, readFile, writeFile, mkdir, copyFile, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join, dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { execFileSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import { createArtifact } from '../src/remote/artifact.js'
import { buildCurrent } from './build-current.mjs'
import { readReleasePolicy } from './release-policy.mjs'

const root = fileURLToPath(new URL('../', import.meta.url))
if (process.platform !== 'win32') throw new Error('Build the Windows installer on Windows.')
const policy = await readReleasePolicy(join(root, 'release-policy.json'), process.argv.includes('--public'))
await buildCurrent({ root })
const temporary = await mkdtemp(join(tmpdir(), 'cannbot-setup-'))
try {
  const artifact = createArtifact(root)
  const archive = join(temporary, 'plugin.tgz')
  await writeFile(archive, artifact.bytes)
  execFileSync('tar.exe', ['-xzf', archive, '-C', temporary], { windowsHide: true })
  await writeFile(join(temporary, 'package', 'release-policy.json'), JSON.stringify(policy, null, 2) + '\n')
  for (const relative of ['scripts/windows/install-all.ps1', 'scripts/windows/provision.ps1', 'scripts/windows/ensure-workbench.mjs', 'scripts/windows/setup-window.ps1', 'scripts/windows/setup-window.cs', 'scripts/windows/setup-logo.png', 'scripts/windows/setup-icon.ico', 'src/remote/artifact.js', 'src/remote/package-root.js']) {
    const target = join(temporary, 'package', relative)
    await mkdir(dirname(target), { recursive: true })
    await copyFile(join(root, relative), target)
  }
  const zip = join(temporary, 'payload.zip')
  execFileSync('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', 'Add-Type -AssemblyName System.IO.Compression.FileSystem; [IO.Compression.ZipFile]::CreateFromDirectory($env:CANNBOT_PACKAGE, $env:CANNBOT_ZIP, [IO.Compression.CompressionLevel]::Optimal, $true)'], {
    windowsHide: true, env: { ...process.env, CANNBOT_PACKAGE: join(temporary, 'package'), CANNBOT_ZIP: zip },
  })
  const bytes = await readFile(zip)
  const hash = createHash('sha256').update(bytes).digest('hex')
  const bootstrap = (await readFile(join(root, 'scripts/windows/setup-bootstrap.ps1'), 'utf8')).replace('__PAYLOAD_SHA256__', hash)
  // EncodedCommand keeps arbitrary download paths out of PowerShell source text.
  const loader = `$t=[IO.File]::ReadAllText($env:CANNBOT_SETUP_FILE);$b=(($t -split '(?m)^::CANNBOT_BOOTSTRAP\\r?\\n',2)[1] -split '(?m)^::CANNBOT_PAYLOAD\\r?\\n',2)[0]; & ([ScriptBlock]::Create([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($b))))`
  const encoded = Buffer.from(loader, 'utf16le').toString('base64')
  // Detach the GUI without hiding a pre-existing terminal belonging to the user.
  const guiLauncher = Buffer.from(`Start-Process -FilePath powershell.exe -WindowStyle Hidden -ArgumentList '-NoProfile -STA -ExecutionPolicy Bypass -EncodedCommand ${encoded}'`, 'utf16le').toString('base64')
  const header = ['@echo off', 'REM Copyright (c) 2026 Huawei Technologies Co., Ltd.', 'REM This program is free software, you can redistribute it and/or modify it under the terms and conditions of CANN Open Software License Agreement Version 2.0 (the "License"). Please refer to the License for details. You may not use this file except in compliance with the License. THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE. See LICENSE in the root of the software repository for the full text of the License.', 'setlocal', 'set "CANNBOT_SETUP_FILE=%~f0"', 'set "CANNBOT_SETUP_MODE=%~1"', `powershell.exe -NoProfile -ExecutionPolicy Bypass -EncodedCommand ${encoded}`, 'set "CANNBOT_SETUP_EXIT=%ERRORLEVEL%"', 'if "%~1"=="" pause', 'exit /b %CANNBOT_SETUP_EXIT%', '::CANNBOT_PAYLOAD', ''].join('\r\n')
  if (encoded.length > 7800) throw new Error('Bootstrap exceeds the Windows CMD command length limit')
  const destination = join(root, 'CANNBot-Setup.cmd')
  const guiHeader = header.replace(`powershell.exe -NoProfile -ExecutionPolicy Bypass -EncodedCommand ${encoded}`, `if not "%~1"=="" goto console\r\npowershell.exe -NoProfile -ExecutionPolicy Bypass -EncodedCommand ${guiLauncher}\r\nexit /b %ERRORLEVEL%\r\n:console\r\npowershell.exe -NoProfile -ExecutionPolicy Bypass -EncodedCommand ${encoded}`)
  const sections = guiHeader.replace('::CANNBOT_PAYLOAD\r\n', '::CANNBOT_BOOTSTRAP\r\n') + Buffer.from(bootstrap).toString('base64').match(/.{1,120}/g).join('\r\n') + '\r\n::CANNBOT_PAYLOAD\r\n'
  await writeFile(destination, sections + bytes.toString('base64').match(/.{1,120}/g).join('\r\n') + '\r\n')
  console.log(`Created ${destination} (${bytes.length} payload bytes, SHA256 ${hash})`)
} finally {
  if (dirname(resolve(temporary)) !== resolve(tmpdir()) || !temporary.startsWith(join(tmpdir(), 'cannbot-setup-'))) throw new Error('Unexpected temporary directory')
  await rm(temporary, { recursive: true, force: true })
}
