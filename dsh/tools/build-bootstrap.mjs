// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { createHash, randomUUID } from 'node:crypto'
import { spawn } from 'node:child_process'
import { existsSync } from 'node:fs'
import { access, lstat, mkdir, mkdtemp, readFile, realpath, rename, rm, symlink, unlink, writeFile } from 'node:fs/promises'
import { dirname, isAbsolute, join, relative, resolve, sep } from 'node:path'
import { extractSourceZip } from './build-archive.mjs'

export const DSH_BUILD_VERSION = '0.2.1-rc.3'
export const DSH_BUILD_TAG = 'dsh-v' + DSH_BUILD_VERSION
export const DSH_SOURCE_URL = `https://codeload.github.com/deepseek-ai/deepseek-harness/zip/refs/tags/${DSH_BUILD_TAG}`
const exists = async path => { try { await access(path); return true } catch { return false } }
const json = async path => JSON.parse(await readFile(path, 'utf8'))
export const inside = (root, path) => { const part = relative(root, path); return part && part !== '..' && !part.startsWith('..' + sep) && !isAbsolute(part) }

export async function buildCache(root) {
  const owner = await realpath(root), cache = join(owner, '.build-cache')
  await mkdir(cache, { recursive: true })
  if (!inside(owner, await realpath(cache))) throw new Error('Build cache must remain inside this source checkout')
  return cache
}
export async function removeOwnedDirectory(root, path) {
  const owner = await realpath(root), target = resolve(path)
  if (!inside(owner, target)) throw new Error('Refusing to remove a path outside the build cache')
  let info
  try { info = await lstat(target) } catch (error) { if (error.code === 'ENOENT') return; throw error }
  if (info.isSymbolicLink()) { await unlink(target); return }
  if (!inside(owner, await realpath(target))) throw new Error('Refusing to follow a directory outside the build cache')
  await rm(target, { recursive: true, force: true, maxRetries: 3, retryDelay: 100 })
}
export function runBuildCommand(command, args, options = {}) {
  return new Promise((resolvePromise, reject) => {
    const child = spawn(command, args, { cwd: options.cwd, env: options.env ?? process.env, stdio: 'inherit', windowsHide: true })
    child.once('error', reject)
    child.once('close', (code, signal) => code === 0 ? resolvePromise() : reject(new Error(`Build command failed (${code ?? signal}): ${command}`)))
  })
}
export async function downloadBuildInput(url, maxBytes = 128 * 1024 * 1024) {
  const response = await fetch(url, { signal: AbortSignal.timeout(120_000) })
  if (!response.ok) throw new Error(`Build dependency download failed: HTTP ${response.status}`)
  const chunks = []; let size = 0
  for await (const chunk of response.body) {
    size += chunk.length
    if (size > maxBytes) throw new Error('Build dependency download exceeded its size limit')
    chunks.push(chunk)
  }
  return Buffer.concat(chunks)
}
export async function validateBuildSource(source) {
  const manifest = await json(join(source, 'package.json'))
  if (manifest.name !== '@deepseek-ai/dsh-root' || manifest.version !== DSH_BUILD_VERSION) throw new Error(`Build requires the official DSH ${DSH_BUILD_VERSION} source checkout`)
  await access(join(source, 'packages/client/tsdown.client.ts'))
  return manifest
}
export async function resolveBuildSource(root, { env = process.env, download = downloadBuildInput, log = console.log } = {}) {
  if (env.DSH_SOURCE) {
    const source = resolve(env.DSH_SOURCE); await validateBuildSource(source); return source
  }
  let saved
  try { saved = (await json(join(root, '.dsh-source.json'))).path } catch (error) { if (error.code !== 'ENOENT') throw error }
  if (saved && await exists(join(saved, 'package.json'))) { const source = resolve(saved); await validateBuildSource(source); return source }
  const sibling = resolve(root, '../deepseek-harness')
  if (await exists(join(sibling, 'package.json'))) { await validateBuildSource(sibling); return sibling }
  const cache = await buildCache(root), source = join(cache, DSH_BUILD_TAG)
  if (await exists(join(source, 'package.json'))) { await validateBuildSource(source); return source }
  log(`[build] Downloading the official ${DSH_BUILD_TAG} build preset…`)
  const staging = await mkdtemp(join(cache, 'source-'))
  try {
    await extractSourceZip(await download(DSH_SOURCE_URL), staging)
    await validateBuildSource(staging)
    await rename(staging, source)
    return source
  } finally { await removeOwnedDirectory(cache, staging) }
}

/** Only compiler/preset dependencies; no DSH runtime workspace installation. */
export async function minimalToolManifest(source, root) {
  const manifest = await validateBuildSource(source)
  const ui = await json(join(source, 'packages/client/ui-plugin-manager/package.json'))
  const plugin = await json(join(root, 'package.json'))
  const dependencies = {}
  for (const name of ['tsdown', 'lightningcss', 'typescript', 'zod']) dependencies[name] = manifest.devDependencies?.[name] ?? manifest.dependencies?.[name]
  for (const name of ['react', 'react-dom', 'clsx']) dependencies[name] = ui.devDependencies?.[name] ?? ui.dependencies?.[name]
  dependencies.yaml = manifest.devDependencies?.yaml ?? plugin.devDependencies?.yaml
  dependencies['@xterm/xterm'] = plugin.devDependencies['@xterm/xterm']
  for (const [name, version] of Object.entries(dependencies)) {
    if (typeof version !== 'string' || !/^[~^]?\d+\.\d+\.\d+(?:-[\w.-]+)?$/.test(version)) throw new Error(`Missing pinned build tool declaration: ${name}`)
  }
  const match = /^pnpm@(\d+\.\d+\.\d+)(?:\+sha\d+\..+)?$/.exec(manifest.packageManager ?? '')
  if (!match) throw new Error('The official source does not declare its pnpm version')
  return { name: 'cannbot-local-build-tools', private: true, type: 'module', packageManager: `pnpm@${match[1]}`, dependencies }
}
function dependenciesPresent(directory, names) {
  // Some compilers hide package.json behind exports. Check their direct local
  // manifests; ancestor resolution must not mistake a missing cache for a ready one.
  return names.every(name => existsSync(join(directory, 'node_modules', name, 'package.json')))
}
async function linkDirectory(target, path) {
  const canonical = await realpath(target)
  let info
  try { info = await lstat(path) } catch (error) { if (error.code !== 'ENOENT') throw error }
  if (info) {
    if (await exists(path)) return // Never replace a developer's working dependency tree.
    if (!info.isSymbolicLink()) throw new Error('An existing build dependency path is unavailable')
    await unlink(path)
  }
  await mkdir(dirname(path), { recursive: true })
  await symlink(canonical, path, process.platform === 'win32' ? 'junction' : 'dir')
}
async function linkTools(source, tools, names) {
  for (const location of [join(source, 'node_modules'), join(source, 'packages/client/ui-plugin-manager/node_modules')]) {
    if (!await exists(location)) await linkDirectory(join(tools, 'node_modules'), location)
    else for (const name of names) await linkDirectory(join(tools, 'node_modules', name), join(location, name))
  }
}
async function ensurePnpm(cache, version, { download, run, log }) {
  const directory = join(cache, `pnpm-${version}`), cli = join(directory, 'bin/pnpm.cjs')
  if (await exists(cli)) return cli
  log(`[build] Preparing local pnpm ${version}…`)
  const metadata = JSON.parse((await download(`https://registry.npmjs.org/pnpm/${version}`, 1024 * 1024)).toString('utf8'))
  if (metadata.name !== 'pnpm' || metadata.version !== version || !/^sha512-[A-Za-z0-9+/]+=*$/.test(metadata.dist?.integrity ?? '') || metadata.dist.tarball !== `https://registry.npmjs.org/pnpm/-/pnpm-${version}.tgz`) throw new Error('Invalid pnpm package metadata')
  const bytes = await download(metadata.dist.tarball)
  if ('sha512-' + createHash('sha512').update(bytes).digest('base64') !== metadata.dist.integrity) throw new Error('pnpm download integrity verification failed')
  const staging = await mkdtemp(join(cache, 'pnpm-')), archive = join(cache, `pnpm-${randomUUID()}.tgz`)
  try {
    await writeFile(archive, bytes, { mode: 0o600 })
    await run(process.platform === 'win32' ? 'tar.exe' : 'tar', ['-xzf', archive, '--strip-components=1', '-C', staging])
    const manifest = await json(join(staging, 'package.json'))
    if (manifest.name !== 'pnpm' || manifest.version !== version || !await exists(join(staging, 'bin/pnpm.cjs'))) throw new Error('Invalid extracted pnpm package')
    await rename(staging, directory)
  } finally { await unlink(archive).catch(error => { if (error.code !== 'ENOENT') throw error }); await removeOwnedDirectory(cache, staging) }
  return cli
}
export async function ensureMinimalToolchain(root, { env = process.env, download = downloadBuildInput, run = runBuildCommand, log = console.log } = {}) {
  const source = await resolveBuildSource(root, { env, download, log })
  const manifest = await minimalToolManifest(source, root), names = Object.keys(manifest.dependencies)
  const ui = join(source, 'packages/client/ui-plugin-manager')
  if (!dependenciesPresent(source, names) || !dependenciesPresent(ui, ['react', 'react-dom'])) {
    const cache = await buildCache(root)
    const key = createHash('sha256').update(JSON.stringify({ manifest, platform: process.platform, arch: process.arch })).digest('hex').slice(0, 16)
    const tools = join(cache, 'tools-' + key)
    await mkdir(tools, { recursive: true })
    await writeFile(join(tools, 'package.json'), JSON.stringify(manifest, null, 2) + '\n')
    // Stop pnpm from discovering/installing the parent repository's workspaces.
    await writeFile(join(tools, 'pnpm-workspace.yaml'), 'packages: []\n')
    if (!dependenciesPresent(tools, names)) {
      const pnpm = await ensurePnpm(cache, manifest.packageManager.slice(5), { download, run, log })
      log('[build] Installing the isolated client compiler tools…')
      await run(process.execPath, [pnpm, 'install', '--ignore-scripts', '--no-frozen-lockfile', '--store-dir', join(cache, 'pnpm-store'), '--registry', 'https://registry.npmjs.org/', '--config.auto-install-peers=false'], {
        cwd: tools, env: { ...env, CI: 'true', PNPM_HOME: join(cache, 'pnpm-home') },
      })
      if (!dependenciesPresent(tools, names)) throw new Error('Build tool installation completed without the required packages')
    }
    await linkTools(source, tools, names)
  }
  await run(process.execPath, [join(root, 'tools/prepare-dev.mjs'), source, '--build-only'], { cwd: root, env: { ...env, DSH_SOURCE: source } })
  return source
}
