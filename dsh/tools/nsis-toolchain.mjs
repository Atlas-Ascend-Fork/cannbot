// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { mkdir, readFile, writeFile, access } from 'node:fs/promises'
import { join } from 'node:path'
import { execFileSync } from 'node:child_process'
import { createHash } from 'node:crypto'

export const nsisVersion = '3.0.4.1'
const digest = '9877df902530f96357d13a7a31ae2b9df67f48b11ffc9a1700a7c961574ec5fa'
export async function nsisToolchain(root) {
  const cache = join(root, '.build-cache', 'nsis-download')
  const archive = join(cache, `nsis-${nsisVersion}.7z`)
  await mkdir(cache, { recursive: true })
  try { await access(archive) } catch {
    const url = `https://github.com/electron-userland/electron-builder-binaries/releases/download/nsis-${nsisVersion}/nsis-${nsisVersion}.7z`
    console.log(`Downloading NSIS ${nsisVersion} build tools`)
    const response = await fetch(url, { signal: AbortSignal.timeout(60000) })
    if (!response.ok) throw new Error(`NSIS download failed: ${response.status}`)
    const bytes = Buffer.from(await response.arrayBuffer())
    if (createHash('sha256').update(bytes).digest('hex') !== digest) throw new Error('NSIS toolchain checksum mismatch')
    await writeFile(archive, bytes)
  }
  if (createHash('sha256').update(await readFile(archive)).digest('hex') !== digest) throw new Error('NSIS toolchain checksum mismatch')
  const directory = join(root, '.build-cache', `nsis-${nsisVersion}`)
  await mkdir(directory, { recursive: true })
  execFileSync('tar.exe', ['-xf', archive, '-C', directory], { windowsHide: true })
  return join(directory, 'Bin', 'makensis.exe')
}
