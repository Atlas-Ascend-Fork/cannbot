// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { mkdtemp, readFile, mkdir, copyFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join, dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { execFileSync } from 'node:child_process'
import { releaseSource } from '../installers/common/release.mjs'
import { nsisToolchain } from './nsis-toolchain.mjs'
import { prepareInstallerLogo, windowsLogoIcon } from './installer-logo.mjs'

const root = fileURLToPath(new URL('../', import.meta.url))
if (process.platform !== 'win32') throw new Error('Build the Windows installer on Windows.')
const sourceFile = join(root, 'installers/common/release-source.json')
await releaseSource(sourceFile)
const compiler = await nsisToolchain(root)
const temporary = await mkdtemp(join(tmpdir(), 'cannbot-setup-'))
try {
  await mkdir(join(temporary, 'package'))
  for (const relative of ['LICENSE', 'THIRD_PARTY_NOTICES.md']) await copyFile(join(root, relative), join(temporary, 'package', relative))
  for (const relative of ['installers/windows/install-all.ps1', 'installers/windows/provision.ps1', 'installers/windows/ensure-workbench.mjs', 'installers/windows/setup-worker.ps1', 'installers/windows/release.ps1', 'installers/common/release.mjs']) {
    const target = join(temporary, 'package', relative)
    await mkdir(dirname(target), { recursive: true })
    await copyFile(join(root, relative), target)
  }
  await copyFile(sourceFile, join(temporary, 'package/installers/common/release-source.json'))
  const renderLogo = await prepareInstallerLogo(root, temporary)
  const png = renderLogo(128)
  const logoPath = join(temporary, 'setup-logo.png')
  const iconPath = join(temporary, 'setup-icon.ico')
  await writeFile(logoPath, png)
  await writeFile(iconPath, windowsLogoIcon(png))
  await copyFile(iconPath, join(temporary, 'package/installers/windows/setup-icon.ico'))
  execFileSync('powershell.exe', ['-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', join(root, 'installers/windows/build-installer-assets.ps1'), '-Source', logoPath, '-Destination', temporary], { windowsHide: true })
  const destination = join(root, 'dist', 'CANNBot-Setup.exe')
  await mkdir(dirname(destination), { recursive: true })
  execFileSync(compiler, ['/V2', `/DOUTPUT=${destination}`, `/DPAYLOAD=${join(temporary, 'package')}`, `/DASSETS=${temporary}`, join(root, 'installers/windows/setup.nsi')], { windowsHide: true, stdio: 'inherit' })
  const bytes = await readFile(destination)
  console.log(`Created ${destination} (${bytes.length} bytes)`)
} finally {
  if (dirname(resolve(temporary)) !== resolve(tmpdir()) || !temporary.startsWith(join(tmpdir(), 'cannbot-setup-'))) throw new Error('Unexpected temporary directory')
  await rm(temporary, { recursive: true, force: true })
}
