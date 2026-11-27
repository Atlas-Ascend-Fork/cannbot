// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { randomUUID } from 'node:crypto'
import { existsSync } from 'node:fs'
import { mkdir, readFile, rename, rm, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'
import { execFileSync } from 'node:child_process'
import { buildCache, downloadBuildInput } from './build-bootstrap.mjs'

// The renderer belongs to the build machine. Only the resulting artwork ships.
const archiveName = 'resvg-wasm-2.6.2.tgz'

export async function prepareInstallerLogo(root, temporary) {
  const archive = join(await buildCache(root), archiveName)
  if (!existsSync(archive)) {
    const bytes = await downloadBuildInput('https://registry.npmjs.org/@resvg/resvg-wasm/-/' + archiveName)
    const pending = archive + '.' + randomUUID()
    try {
      await writeFile(pending, bytes)
      await rename(pending, archive)
    } finally { await rm(pending, { force: true }) }
  }
  const staging = join(temporary, 'artwork')
  await mkdir(staging)
  execFileSync(process.platform === 'win32' ? 'tar.exe' : 'tar',
    ['-xzf', archive, '-C', staging, 'package/index.mjs', 'package/index_bg.wasm'], { windowsHide: true })
  const moduleDir = join(staging, 'package')
  const { initWasm, Resvg } = await import(pathToFileURL(join(moduleDir, 'index.mjs')).href)
  await initWasm(await readFile(join(moduleDir, 'index_bg.wasm')))
  const svg = await readFile(join(root, 'icon.svg'))
  return size => {
    const image = new Resvg(svg, { fitTo: { mode: 'width', value: size } })
    try {
      const rendered = image.render()
      try { return Buffer.from(rendered.asPng()) } finally { rendered.free() }
    } finally { image.free() }
  }
}

// ICONDIR + a single ICONDIRENTRY for the shell's 128px, 32-bit transparent PNG.
export function windowsLogoIcon(png) {
  const header = Buffer.alloc(22)
  header.writeUInt16LE(1, 2)
  header.writeUInt16LE(1, 4)
  header[6] = 128
  header[7] = 128
  header.writeUInt16LE(1, 10)
  header.writeUInt16LE(32, 12)
  header.writeUInt32LE(png.length, 14)
  header.writeUInt32LE(header.length, 18)
  return Buffer.concat([header, png])
}
