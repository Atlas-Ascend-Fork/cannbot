// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { spawnSync } from 'node:child_process'
import { access, chmod, copyFile, cp, mkdir, mkdtemp, readFile, realpath, rename, rm, writeFile } from 'node:fs/promises'
import { join, dirname, delimiter } from 'node:path'
import { pathToFileURL } from 'node:url'
import { homedir } from 'node:os'
import { parseArgs } from 'node:util'
import { createInterface } from 'node:readline/promises'
import { frozenRelease, getPackage, packages, prepare, recordInstallation, requireCompatible, releaseSource } from './release.mjs'

async function review(manifest, stage, macDialog) {
  if (macDialog) {
    const args = manifest.legal.documents.flatMap(doc => [doc.title, join(stage, doc.id + '.txt')])
    const script = new URL('../macos/consent.applescript', import.meta.url)
    const { fileURLToPath } = await import('node:url')
    const result = spawnSync('/usr/bin/osascript', [fileURLToPath(script), ...args], { stdio: 'inherit' })
    if (result.status !== 0) throw new Error('Installation cancelled before changing the DSH profile.')
  } else {
    if (!process.stdin.isTTY) throw new Error('Open an interactive terminal to review the release agreements.')
    const terminal = createInterface({ input: process.stdin, output: process.stdout })
    try {
      for (const [index, doc] of manifest.legal.documents.entries()) console.log((index + 1) + '. ' + doc.title + '  ' + doc.url)
      for (;;) {
        const answer = (await terminal.question('输入序号阅读文件。输入 AGREE 表示同意用户协议，并已阅读隐私政策和开源软件声明，或输入 Q 退出：')).trim()
        if (answer === 'AGREE') break
        if (answer.toLowerCase() === 'q') throw new Error('Installation cancelled.')
        const doc = manifest.legal.documents[Number(answer) - 1]
        if (doc) console.log(await readFile(join(stage, doc.id + '.txt'), 'utf8'))
      }
    } finally { terminal.close() }
  }
}

export async function installUnix(values, { home = homedir(), dshHome = process.env.DSH_HOME || join(home, '.dsh'),
  temp = process.env.CANNBOT_SETUP_TEMP, platform = process.platform, archName = process.arch,
  source, download, consent = review, execute = spawnSync } = {}) {
  const edition = values.edition
  const profile = values.profile || (edition === 'server' ? 'cannbot-server' : 'web')
  if (!Object.hasOwn(packages, edition) || (edition === 'server' && platform !== 'linux')) throw new Error('Server edition requires Linux.')
  if (!/^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}$/.test(profile)) throw new Error('Invalid DSH profile name.')
  if (edition === 'server' && ['web', 'desktop', 'acp', 'headless', 'sdk'].includes(profile)) throw new Error('Choose a dedicated server profile.')
  if (!temp) throw new Error('Start the platform installer.')
  const prefix = join(home, '.local', 'share', 'cannbot')
  const profileDir = join(dshHome, 'profiles', profile)
  const stage = join(temp, 'release')
  source ||= await releaseSource(new URL('./release-source.json', import.meta.url))
  const manifest = await prepare(source, stage, download)
  const arch = platform + '-' + archName
  const host = manifest.hosts?.[arch]
  if (!host) throw new Error('Missing supported DSH version for ' + arch)
  requireCompatible(manifest.dshRange, host.version)
  console.log('CANNBot ' + manifest.version + ' (' + edition + ') · ' + profile)
  await consent(manifest, stage, values['mac-dialog'])
  await frozenRelease(stage)
  const packagePath = await getPackage(manifest, edition, stage, download)
  let runtimeBin = dirname(process.execPath)
  const runtime = process.env.CANNBOT_RUNTIME_TO_KEEP
  if (runtime) {
    if (!/^node-v24\.22\.3-(linux|darwin)-(x64|arm64)$/.test(runtime) || await realpath(runtimeBin) !== await realpath(join(temp, runtime, 'bin'))) throw new Error('Invalid staged Node.js runtime.')
    const runtimes = join(prefix, 'runtime'), destination = join(runtimes, runtime)
    await mkdir(runtimes, { recursive: true, mode: 0o700 })
    const staging = await mkdtemp(join(runtimes, '.prepare-'))
    try {
      await cp(join(temp, runtime), join(staging, runtime), { recursive: true, verbatimSymlinks: true })
      try { await rename(join(staging, runtime), destination) }
      catch (error) { if (!['EEXIST','ENOTEMPTY'].includes(error.code)) throw error }
    } finally { await rm(staging, { recursive: true, force: true }) }
    runtimeBin = join(destination, 'bin')
  }
  const env = { ...process.env, DSH_HOME: dshHome, PATH: [join(prefix, 'bin'), runtimeBin, process.env.PATH].join(delimiter) }
  function run(command, args, output = false) {
    const result = execute(command, args, { env, stdio: output ? ['ignore', 'pipe', 'pipe'] : 'inherit', encoding: 'utf8' })
    if (result.error) throw result.error
    if (result.status !== 0) throw new Error(command + ' failed: ' + (result.stderr || result.status))
    return result.stdout?.trim()
  }
  function existing(command) {
    const result = execute('/bin/sh', ['-c', 'command -v "$1"', 'sh', command], { env, encoding: 'utf8' })
    return result.status === 0 ? result.stdout.trim() : ''
  }
  async function present(path) { try { await access(path); return true } catch { return false } }
  async function atomic(path, bytes, mode = 0o600) {
    const pending = path + '.' + process.pid + '.tmp'
    await writeFile(pending, bytes, { mode })
    await rename(pending, path)
  }
  const registry = '--registry=https://registry.npmjs.org/'
  let dsh = existing('dsh')
  if (!dsh) {
    run('npm', ['install', '--global', '--prefix', prefix, registry, '--no-audit', '--no-fund', '@deepseek-ai/dsh@' + host.version])
    dsh = join(prefix, 'bin', 'dsh')
  }
  const output = run(dsh, ['--version'], true)
  const actual = /\b(\d+\.\d+\.\d+(?:-[0-9a-z.-]+)?)/i.exec(output)?.[1]
  requireCompatible(manifest.dshRange, actual)
  if (!existing('pnpm')) run('npm', ['install', '--global', '--prefix', prefix, registry, '--no-audit', '--no-fund', 'pnpm@11.28.5'])
  await mkdir(profileDir, { recursive: true, mode: 0o700 })
  const lock = join(profileDir, '.cannbot-setup.lock')
  const { open, unlink } = await import('node:fs/promises')
  const handle = await open(lock, 'wx').catch(error => {
    if (error.code === 'EEXIST') throw new Error('Another installer is using ' + profile + '. After an interrupted installation, check that it exited before removing ' + lock)
    throw error
  })
  try {
    await handle.writeFile(String(process.pid))
    const packageFile = join(profileDir, 'package.json')
    if (!await present(packageFile) && profile !== 'web') {
      const preset = { name: 'cannbot-' + edition + '-profile', private: true,
        dsh: { profile: { bundles: ['@deepseek-ai/dsh-base', '@deepseek-ai/dsh-web-app'] } } }
      await atomic(packageFile, JSON.stringify(preset, null, 2))
    }
    const archive = join(prefix, 'releases', manifest.buildId, edition + '.tgz')
    await mkdir(dirname(archive), { recursive: true, mode: 0o700 })
    const pending = archive + '.' + process.pid + '.tmp'
    await copyFile(packagePath, pending)
    await rename(pending, archive)
    if (await present(packageFile)) {
      const current = JSON.parse(await readFile(packageFile, 'utf8'))
      const other = packages[edition === 'client' ? 'server' : 'client']
      if (current.dsh?.profile?.bundles?.includes(other)) throw new Error('This DSH profile already uses the other CANNBot edition. Choose a separate profile.')
    }
    run(dsh, ['plugin', '--profile', profile, 'add', 'file:' + archive, '--save-exact', registry])
    const enabled = JSON.parse(await readFile(packageFile, 'utf8'))
    const installed = JSON.parse(await readFile(join(profileDir, 'node_modules', packages[edition], 'package.json'), 'utf8'))
    if (!enabled.dsh?.profile?.bundles?.includes(packages[edition]) || installed.version !== manifest.version || installed.name !== packages[edition] ||
        installed.cannbotEdition !== edition || installed.cannbotBuildId !== manifest.buildId) throw new Error('Could not confirm CANNBot in the selected profile.')
    if (enabled.dsh.profile.bundles.includes('cannbot-dsh')) run(dsh, ['plugin', '--profile', profile, 'remove', 'cannbot-dsh'])
    await recordInstallation(manifest, edition, profileDir)
    const shellQuote = text => "'" + text.replaceAll("'", "'\\''") + "'"
    const bin = join(prefix, 'bin')
    await mkdir(bin, { recursive: true })
    const launch = join(bin, edition === 'client' && profile === 'web' ? 'cannbot' : 'cannbot-' + profile)
    await atomic(launch, '#!/bin/sh\nexport PATH=' + shellQuote(bin + ':' + runtimeBin) + ':"$PATH"\nexport DSH_HOME=' + shellQuote(dshHome) + '\nexec ' + shellQuote(dsh) + ' --profile ' + shellQuote(profile) + ' --host 127.0.0.1 "$@"\n', 0o755)
    await chmod(launch, 0o755)
    console.log('安装完成。启动命令：' + shellQuote(launch))
  } finally { await handle.close(); await unlink(lock) }
}

if (process.argv[1] && pathToFileURL(process.argv[1]).href === import.meta.url) {
  const { values } = parseArgs({ options: {
    edition: { type: 'string', default: 'client' }, profile: { type: 'string' },
    'mac-dialog': { type: 'boolean' }, help: { type: 'boolean', short: 'h' },
  } })
  if (values.help) { console.log('CANNBot-Setup.sh [--edition client|server] [--profile NAME]'); }
  if (!values.help) await installUnix(values).catch(error => { console.error(error.message); process.exitCode = 1 })
}
