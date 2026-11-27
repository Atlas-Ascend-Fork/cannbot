// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { readFile, mkdir, rename, unlink, writeFile } from 'node:fs/promises'
import { randomUUID } from 'node:crypto'
import { join, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { createPackageArtifact } from './package-archive.mjs'
import { acquireFileLock } from '../packages/install/lib/file-lock.mjs'
import { buildEditionArchives } from './package-editions.mjs'
import { buildCurrent } from './build-current.mjs'

async function atomicWrite(file, content) {
  const temporary = file + '.' + randomUUID() + '.tmp'
  try { await writeFile(temporary, content, { mode: 0o600, flush: true }); await rename(temporary, file) }
  finally { await unlink(temporary).catch(error => { if (error.code !== 'ENOENT') throw error }) }
}
export async function packageCurrent({ root = fileURLToPath(new URL('../', import.meta.url)), short = false, build = buildCurrent, log = console.log } = {}) {
  root = resolve(root)
  if (!short) await build({ root })
  const packageRoot = short ? join(root, 'packages', short === 'server' ? 'short-server' : 'short') : root
  const manifest = JSON.parse(await readFile(join(packageRoot, 'package.json'), 'utf8'))
  if (!/^(?:@[a-z0-9][a-z0-9._-]*\/)?[a-z0-9][a-z0-9._-]*$/.test(manifest.name ?? '') || !/^\d+\.\d+\.\d+(?:-[a-zA-Z0-9.-]+)?(?:\+[a-zA-Z0-9.-]+)?$/.test(manifest.version ?? '')) throw new Error('Invalid release package name or version')
  const file = `${manifest.name.replace(/^@/, '').replaceAll('/', '-')}-${manifest.version}.tgz`
  const pair = short ? undefined : await buildEditionArchives(root)
  const sharedFiles = Object.fromEntries(['LICENSE', 'THIRD_PARTY_NOTICES.md', 'icon.svg'].map(name => [name, join(root, name)]))
  const artifact = short ? createPackageArtifact(packageRoot, { sharedFiles }) : pair.client
  const dist = join(root, 'dist')
  await mkdir(dist, { recursive: true })
  const release = await acquireFileLock(join(dist, '.package.lock'), 20 * 60_000)
  try {
    if (pair) {
      const serverFile = pair.server.name.slice(1).replace('/', '-') + '-' + manifest.version + '.tgz'
      await atomicWrite(join(dist, serverFile), pair.server.bytes)
    }
    await atomicWrite(join(dist, file), artifact.bytes)
  } finally { release() }
  log(`Packed ${file}`)
  return { file: join(dist, file), hash: artifact.hash, buildId: pair?.buildId }
}

if (process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === import.meta.url) {
  try {
    const [mode, ...extra] = process.argv.slice(2)
    if (extra.length || (mode && !['--short', '--short-server'].includes(mode))) throw new Error('Usage: node tools/package.mjs [--short | --short-server]')
    await packageCurrent({ short: mode === '--short-server' ? 'server' : mode === '--short' })
  } catch (error) { console.error(error.message); process.exitCode = 1 }
}
