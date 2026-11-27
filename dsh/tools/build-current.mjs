// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

/** Build the current checkout before source installation; never accept an unproven old lib. */
import { createHash, randomUUID } from 'node:crypto'
import { lstat, mkdir, readFile, readdir, realpath, rename, unlink, writeFile } from 'node:fs/promises'
import { join, relative, resolve, sep } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { acquireFileLock } from '../packages/install/lib/file-lock.mjs'
import { buildCache, DSH_BUILD_VERSION, ensureMinimalToolchain, inside, removeOwnedDirectory, runBuildCommand } from './build-bootstrap.mjs'

export const BUILD_RECEIPT = 'lib/.cannbot-build.json'
const INPUT_DIRECTORIES = ['plugin', 'remote', 'locale', 'tools', 'installers/common', 'packages/install/lib']
const INPUT_FILES = ['package.json', 'tsdown.config.ts', 'tsconfig.json', 'cordis.patch.yml', 'workflow-defaults.json', 'official-plugins.json', 'icon.svg']
const missing = error => error.code === 'ENOENT'

async function filesUnder(root, path, files) {
  let info
  try { info = await lstat(path) } catch (error) { if (missing(error)) return; throw error }
  if (info.isSymbolicLink()) throw new Error(`Build inputs/outputs must not be symbolic links: ${relative(root, path)}`)
  if (info.isFile()) files.push(path)
  else if (info.isDirectory()) for (const name of (await readdir(path)).sort()) await filesUnder(root, join(path, name), files)
}
async function digest(root, files) {
  const hash = createHash('sha256')
  for (const path of files.sort()) {
    const bytes = await readFile(path), name = relative(root, path).split(sep).join('/')
    hash.update(JSON.stringify([name, bytes.length]) + '\n'); hash.update(bytes)
  }
  return hash.digest('hex')
}
export async function buildInputHash(root) {
  const files = []
  for (const path of [...INPUT_DIRECTORIES, ...INPUT_FILES]) await filesUnder(root, join(root, path), files)
  if (!files.includes(join(root, 'package.json')) || ['plugin/editions/client/host.ts', 'plugin/editions/client/ui.ts', 'plugin/editions/server/host.ts', 'plugin/editions/server/ui.ts'].some(file => !files.includes(join(root, file)))) throw new Error('The current source checkout is incomplete')
  return createHash('sha256').update(DSH_BUILD_VERSION + ':' + await digest(root, files)).digest('hex')
}
export async function buildOutputHash(root) {
  try {
    for (const required of ['lib/index.js', 'lib/client.js', 'lib/server/index.js', 'lib/server/client.js']) {
      const info = await lstat(join(root, required))
      if (!info.isFile() || info.size === 0) return undefined
    }
    const files = []; await filesUnder(root, join(root, 'lib'), files)
    return digest(root, files.filter(path => path !== join(root, BUILD_RECEIPT)))
  } catch (error) { if (missing(error)) return undefined; throw error }
}
async function receipt(root) {
  try { return JSON.parse(await readFile(join(root, BUILD_RECEIPT), 'utf8')) }
  catch (error) { if (missing(error) || error instanceof SyntaxError) return undefined; throw error }
}
export async function currentBuildStatus(root) {
  const inputHash = await buildInputHash(root), outputHash = await buildOutputHash(root), stamp = await receipt(root)
  return { current: !!outputHash && stamp?.schemaVersion === 1 && stamp.sourceVersion === DSH_BUILD_VERSION && stamp.inputHash === inputHash && stamp.outputHash === outputHash, inputHash, outputHash }
}
export async function buildCurrent({ root = fileURLToPath(new URL('../', import.meta.url)), force = false, check = false, ensureTools = ensureMinimalToolchain, run = runBuildCommand, log = console.log } = {}) {
  root = await realpath(root)
  let status = await currentBuildStatus(root)
  if (check) return status
  if (status.current && !force) { log('[build] Current source and compiled files match; reusing lib.'); return { ...status, rebuilt: false } }
  const cache = await buildCache(root), release = await acquireFileLock(join(cache, 'build.lock'), 20 * 60_000)
  try {
    status = await currentBuildStatus(root)
    if (status.current && !force) return { ...status, rebuilt: false }
    const source = await ensureTools(root)
    // prepare-dev writes only ignored machine configuration, never source inputs.
    const inputHash = await buildInputHash(root), lib = join(root, 'lib'), previous = join(cache, 'previous-lib-' + randomUUID())
    let saved = false, outputOwned = false
    try {
      const info = await lstat(lib).catch(error => { if (!missing(error)) throw error })
      if (info) {
        if (!info.isDirectory() || info.isSymbolicLink() || !inside(root, await realpath(lib)) || !inside(cache, previous)) throw new Error('Refusing to replace an unmanaged lib directory')
        await unlink(join(root, BUILD_RECEIPT)).catch(error => { if (!missing(error)) throw error })
        await rename(lib, previous); saved = true
      }
      outputOwned = true
      log('[build] Compiling the current CANNBot source…')
      await run(process.execPath, [join(root, 'tools/build.mjs')], { cwd: root, env: { ...process.env, DSH_SOURCE: source } })
      const outputHash = await buildOutputHash(root)
      if (!outputHash) throw new Error('Build did not produce both Host and Client bundles')
      if (await buildInputHash(root) !== inputHash) throw new Error('Source files changed during the build; run the installer again after saving your edits')
      const stamp = { schemaVersion: 1, sourceVersion: DSH_BUILD_VERSION, inputHash, outputHash }
      await writeFile(join(root, BUILD_RECEIPT), JSON.stringify(stamp, null, 2) + '\n', { encoding: 'utf8', mode: 0o600, flush: true })
      if (saved) await removeOwnedDirectory(cache, previous).catch(() => log('[build] Previous generated files remain in .build-cache for later cleanup.'))
      log('[build] Current source build is ready.')
      return { current: true, inputHash, outputHash, rebuilt: true }
    } catch (error) {
      // Only generated paths under this checkout are touched; directory links are
      // removed as links, and restoration never follows them into another tree.
      if (outputOwned) await removeOwnedDirectory(root, lib)
      if (saved) await rename(previous, lib)
      throw error
    }
  } finally { release() }
}

if (process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === import.meta.url) {
  try {
    const unknown = process.argv.slice(2).filter(arg => !['--force', '--check'].includes(arg))
    if (unknown.length) throw new Error('Usage: node tools/build-current.mjs [--force | --check]')
    const result = await buildCurrent({ force: process.argv.includes('--force'), check: process.argv.includes('--check') })
    if (process.argv.includes('--check')) { console.log(result.current ? '[build] Current.' : '[build] Build required.'); process.exitCode = result.current ? 0 : 1 }
  } catch (error) { console.error(`[build] ${error.message}`); process.exitCode = 1 }
}
