// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { chmod, copyFile, mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { releaseSource } from '../installers/common/release.mjs'
import { prepareInstallerLogo } from './installer-logo.mjs'

const root = fileURLToPath(new URL('../', import.meta.url))
const platform = process.argv[2]
if (!['linux', 'macos'].includes(platform)) throw new Error('Usage: node tools/package-unix.mjs linux|macos')
const source = join(root, 'installers/common/release-source.json')
await releaseSource(source)
const dist = join(root, 'dist')
await mkdir(dist, { recursive: true })
const lines = [(await readFile(join(root, 'installers/linux/bootstrap.sh'), 'utf8')).trimEnd()]
for (const part of ['common/release.mjs', 'common/install-unix.mjs', 'common/runtime.sh', 'common/release-source.json', 'macos/consent.applescript', 'LICENSE', 'THIRD_PARTY_NOTICES.md']) {
  const path = part === 'common/release-source.json' ? source : join(root, part.includes('/') ? 'installers' : '', part)
  const content = (await readFile(path, 'utf8')).replaceAll('\r\n', '\n').trimEnd()
  const marker = 'END_CANNBOT_SETUP_FILE'
  if (content.split('\n').includes(marker)) throw new Error('Unexpected here document delimiter in ' + part)
  lines.push('cat >"$CANNBOT_SETUP_TEMP/' + part + '" <<\'' + marker + "'", content, marker)
}
lines.push('/bin/sh "$CANNBOT_SETUP_TEMP/common/runtime.sh" "$@"', '')
const script = lines.join('\n')
if (platform === 'linux') {
  const file = join(dist, 'CANNBot-Setup.sh')
  await writeFile(file, script, { mode: 0o755 })
  await chmod(file, 0o755)
  console.log('Created ' + file)
} else {
  if (process.platform !== 'darwin') throw new Error('Build the macOS package on macOS using pkgbuild and productbuild.')
  const tmp = await mkdtemp(join(tmpdir(), 'cannbot-pkg-'))
  try {
    const scripts = join(tmp, 'scripts')
    const contents = join(tmp, 'payload', 'Applications', 'CANNBot.app', 'Contents')
    await mkdir(scripts)
    await mkdir(join(contents, 'MacOS'), { recursive: true })
    await copyFile(join(root, 'installers/macos/Info.plist'), join(contents, 'Info.plist'))
    const resources = join(contents, 'Resources')
    const icons = join(tmp, 'CANNBot.iconset')
    await Promise.all([mkdir(resources), mkdir(icons)])
    const renderLogo = await prepareInstallerLogo(root, tmp)
    for (const size of [16, 32, 128, 256, 512]) {
      for (const scale of [1, 2]) {
        const name = 'icon_' + size + 'x' + size + (scale === 2 ? '@2x' : '') + '.png'
        await writeFile(join(icons, name), renderLogo(size * scale))
      }
    }
    execFileSync('/usr/bin/iconutil', ['-c', 'icns', icons, '-o', join(resources, 'CANNBot.icns')])
    await writeFile(join(contents, 'MacOS', 'CANNBot'), '#!/bin/sh\nexec "$HOME/.local/share/cannbot/bin/cannbot" "$@"\n', { mode: 0o755 })
    await writeFile(join(scripts, 'install.sh'), script)
    await copyFile(join(root, 'installers/macos/preinstall'), join(scripts, 'preinstall'))
    await chmod(join(scripts, 'preinstall'), 0o755)
    execFileSync('/usr/bin/pkgbuild', ['--root', join(tmp, 'payload'), '--install-location', '/', '--scripts', scripts, '--identifier', 'org.cannbot.workbench.client', '--version', '1.0.0', join(tmp, 'client.pkg')], { stdio: 'inherit' })
    const dest = join(dist, 'CANNBot-Setup.pkg')
    execFileSync('/usr/bin/productbuild', ['--distribution', join(root, 'installers/macos/Distribution.xml'), '--package-path', tmp, '--resources', join(root, 'installers/macos'), dest], { stdio: 'inherit' })
    console.log('Created ' + dest)
  } finally { await rm(tmp, { recursive: true, force: true }) }
}
