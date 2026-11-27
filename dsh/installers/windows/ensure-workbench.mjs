// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

// Install the official workbench in an isolated store inside the desktop profile.
// The profile's existing dependency tree is never passed to npm/pnpm install.
import { existsSync, lstatSync, mkdirSync, readFileSync, realpathSync, symlinkSync, writeFileSync, renameSync } from 'node:fs'
import { createRequire } from 'node:module'
import { dirname, join, resolve, delimiter, relative, isAbsolute, sep } from 'node:path'
import { homedir } from 'node:os'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

export const WORKBENCH = '@cannbot-plugin/cannbot-dsh'
export const SHORT = 'cannbot-dsh'
const readJson = file => JSON.parse(readFileSync(file, 'utf8').replace(/^\uFEFF/, ''))
const packageDirectory = (root, name) => join(root, 'node_modules', ...name.split('/'))

export function inspectWorkbench(profile) {
  const manifest = readJson(join(profile, 'package.json'))
  const bundles = manifest.dsh?.profile?.bundles || []
  // Preserve an existing short entry, otherwise prefer the full package.
  const names = bundles.includes(SHORT) || manifest.dependencies?.[SHORT] ? [SHORT, WORKBENCH] : [WORKBENCH, SHORT]
  for (const name of names) {
    const directory = packageDirectory(profile, name)
    if (!existsSync(join(directory, 'package.json'))) continue
    const pkg = readJson(join(directory, 'package.json'))
    if (pkg.name !== name) continue
    try {
      // pnpm exposes a junction whose peers/dependencies live beside the real
      // package in .pnpm/<version>/node_modules, not beside the top-level link.
      const actualDirectory = realpathSync(directory)
      const require = createRequire(join(actualDirectory, 'package.json'))
      const core = name === SHORT ? realpathSync(dirname(require.resolve(`${WORKBENCH}/package.json`))) : actualDirectory
      const corePkg = readJson(join(core, 'package.json'))
      if (!existsSync(join(core, 'lib', 'index.js')) || !existsSync(join(core, 'lib', 'client.js')) || !existsSync(join(core, 'cordis.patch.yml'))) continue
      const coreRequire = createRequire(join(core, 'package.json'))
      for (const dependency of Object.keys(corePkg.dependencies || {})) {
        try { coreRequire.resolve(`${dependency}/package.json`) } catch { coreRequire.resolve(dependency) }
      }
      return { bundle: name, version: pkg.version, coreVersion: corePkg.version, edition: corePkg.cannbotEdition, buildId: corePkg.cannbotBuildId, directory, reused: true }
    } catch { /* A partial package tree is not a successful installation. */ }
  }
  return null
}

export function packageManager(execPath = process.execPath) {
  // The current Desktop Node and pnpm are siblings under dependencies/.
  // Prefer that matching pnpm over unrelated developer tools on PATH.
  const desktopPnpm = resolve(dirname(execPath), '../../pnpm/bin/pnpm.cjs')
  if (existsSync(desktopPnpm)) return { cli: desktopPnpm, kind: 'pnpm' }
  const runtime = join(process.env.DSH_HOME || join(homedir(), '.dsh'), 'dsh-runtimes', 'dsh-primary-runtime', 'dependencies')
  const nodeRoots = [dirname(execPath), resolve(dirname(execPath), '..'), join(runtime, 'node')]
  for (const base of nodeRoots) {
    for (const part of ['node_modules/npm/bin/npm-cli.js', 'lib/node_modules/npm/bin/npm-cli.js']) {
      const cli = join(base, part)
      if (existsSync(cli)) return { cli, kind: 'npm' }
    }
  }
  for (const base of [join(runtime, 'pnpm'), ...nodeRoots]) {
    for (const part of ['bin/pnpm.cjs', 'node_modules/pnpm/bin/pnpm.cjs', 'lib/node_modules/pnpm/bin/pnpm.cjs']) {
      const cli = join(base, part)
      if (existsSync(cli)) return { cli, kind: 'pnpm' }
    }
  }
  // The bundled runtime also exposes pnpm.cjs next to a pnpm.cmd shim.
  for (const base of (process.env.PATH || '').split(delimiter)) {
    for (const part of ['pnpm.cjs', 'node_modules/pnpm/bin/pnpm.cjs', '../pnpm/bin/pnpm.cjs']) {
      const cli = resolve(base, part)
      if (existsSync(cli)) return { cli, kind: 'pnpm' }
    }
  }
  throw new Error('Cannot find npm/pnpm. Launch DSH once to prepare its runtime, or install Node.js with npm.')
}

function installOfficial(store, archive) {
  const manager = packageManager()
  const registry = 'https://registry.npmjs.org/'
  const args = manager.kind === 'npm'
    ? ['install', '--prefix', store, '--ignore-scripts', '--legacy-peer-deps', '--omit=dev', '--no-audit', '--no-fund', '--save-exact', `--registry=${registry}`, archive]
    : ['--dir', store, 'add', '--ignore-scripts', '--config.auto-install-peers=false', '--prod', '--save-exact', `--registry=${registry}`, archive]
  const result = spawnSync(process.execPath, [manager.cli, ...args], {
    stdio: 'inherit', windowsHide: true,
    env: { ...process.env, PATH: `${dirname(process.execPath)}${delimiter}${process.env.PATH || ''}` },
  })
  if (result.error) throw result.error
  if (result.status !== 0) throw new Error(`Official CANNBot installation failed (exit ${result.status}). Existing profile was not changed.`)
}

export function ensureWorkbench(profilePath, { install = installOfficial, artifact } = {}) {
  if (!/^[a-z0-9][a-z0-9._-]{0,127}$/i.test(artifact.buildId || '')) throw new Error('Invalid CANNBot build identifier')
  const profile = realpathSync(profilePath)
  const store = join(profile, '.cannbot-workbench', artifact.buildId)
  mkdirSync(store, { recursive: true })
  if (lstatSync(store).isSymbolicLink()) throw new Error('CANNBot build store must not be a symbolic link')
  const within = path => { const part = relative(profile, realpathSync(path)); return part !== '..' && !part.startsWith('..' + sep) && !isAbsolute(part) }
  if (!within(store)) throw new Error('CANNBot build store escaped the desktop profile')
  const archive = join(store, 'source.tgz')
  if (!existsSync(join(store, 'complete.json'))) {
    writeFileSync(archive, artifact.bytes)
    writeFileSync(join(store, 'package.json'), JSON.stringify({ name: 'cannbot-workbench-runtime', private: true }), 'utf8')
    install(store, archive)
    if (!inspectWorkbench(store)) throw new Error('Current CANNBot build or its dependencies are incomplete; profile was not changed.')
    writeFileSync(join(store, 'complete.json'), JSON.stringify({ buildId: artifact.buildId }), 'utf8')
  }
  const staged = inspectWorkbench(store)
  if (!staged || (artifact.version && staged.coreVersion !== artifact.version) || (artifact.buildId && (staged.buildId !== artifact.buildId || staged.edition !== 'client'))) throw new Error('Current CANNBot build is incomplete; remove its incomplete store and retry.')
  const target = packageDirectory(profile, WORKBENCH)
  const actual = realpathSync(staged.directory)
  try { if (realpathSync(target) === actual) return { ...staged, directory: target, reused: true, buildId: artifact.buildId } } catch {}
  mkdirSync(dirname(target), { recursive: true })
  if (!within(dirname(target))) throw new Error('CANNBot package directory escaped the desktop profile')
  let backup
  try { lstatSync(target); backup = target + '.before-source-' + Date.now(); renameSync(target, backup) } catch (error) { if (error.code !== 'ENOENT') throw error }
  try { symlinkSync(actual, target, process.platform === 'win32' ? 'junction' : 'dir') }
  catch (error) { if (backup) renameSync(backup, target); throw error }
  return { ...staged, bundle: WORKBENCH, directory: target, reused: false, buildId: artifact.buildId }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const profile = process.argv[2]
    if (!profile) throw new Error('Usage: node ensure-workbench.mjs <desktop-profile> [--check]')
    let result
    if (process.argv.includes('--check')) result = inspectWorkbench(profile)
    else {
      const [archive, version, buildId] = process.argv.slice(3)
      const bytes = readFileSync(archive)
      if (!version || !buildId) throw new Error('Missing CANNBot release identity')
      result = ensureWorkbench(profile, { artifact: { bytes, version, buildId } })
    }
    // Windows PowerShell 5.1 decodes native stdout using the system code page.
    // Keep this machine-readable record ASCII even for Chinese profile paths.
    const json = JSON.stringify(result).replace(/[^\x00-\x7f]/g, char => `\\u${char.charCodeAt(0).toString(16).padStart(4, '0')}`)
    console.log(`CANNBOT_WORKBENCH=${json}`)
    if (!result) process.exitCode = 1
  } catch (error) { console.error(error.message); process.exitCode = 1 }
}
