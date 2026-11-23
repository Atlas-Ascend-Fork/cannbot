// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { test } from 'node:test'
import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { copyFileSync, cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, unlinkSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createArtifact } from '../../src/remote/artifact.js'

const provision = fileURLToPath(new URL('../../scripts/windows/provision.ps1', import.meta.url))
const packageName = '@cannbot-plugin/cannbot-dsh'
const workbenchName = '@cannbot-plugin/cannbot-dsh'
const windowsOnly = { skip: process.platform !== 'win32' && 'requires Windows PowerShell 5.1' }
const original = {
  name: 'desktop-test-profile',
  private: true,
  dependencies: { 'existing-bundle': '1.2.3', [workbenchName]: '1.0.0-alpha.1' },
  dsh: { profile: { bundles: ['existing-bundle', workbenchName], settings: { label: '中文配置', enabled: true } } },
  custom: { preserved: [1, 2, 3] },
}

function fixture(t, manifest = original) {
  const home = mkdtempSync(join(tmpdir(), 'cannbot-provision-'))
  t.after(() => rmSync(home, { recursive: true, force: true }))
  const profile = join(home, 'profiles', 'desktop', 'package.json')
  const target = join(dirname(profile), 'node_modules', '@cannbot-plugin', 'cannbot-dsh')
  mkdirSync(dirname(profile), { recursive: true })
  writeFileSync(profile, JSON.stringify(manifest), 'utf8')
  const source = join(home, 'source')
  mkdirSync(source)
  const manifestSource = { name: packageName, version: '1.0.0-alpha.1', files: ['lib', 'remote', 'cordis.patch.yml'] }
  writeFileSync(join(source, 'package.json'), JSON.stringify(manifestSource))
  for (const file of ['lib/index.js','lib/client.js','remote/sync-credentials.mjs','remote/deploy-package.mjs','cordis.patch.yml']) { mkdirSync(dirname(join(source,file)), { recursive:true }); writeFileSync(join(source,file),'// built fixture') }
  const artifact = createArtifact(source)
  const store = join(dirname(profile), '.cannbot-workbench', artifact.hash)
  mkdirSync(store, {recursive:true})
  writeFileSync(join(store, 'package.json'), '{}')
  writeFileSync(join(store, 'complete.json'), JSON.stringify({hash:artifact.hash}))
  const packageTarget = join(store, 'node_modules', ...packageName.split('/'))
  cpSync(source, packageTarget, {recursive:true})
  return { home, profile, target, source }

}

function runProvision(fixture, mode = '', expectedStatus = 0) {
  // Keep the real desktop process out of these isolated-profile tests. The
  // production script otherwise prompts whenever any DSH desktop is running.
  // Pass paths via environment variables so spaces/non-ASCII never need shell escaping.
  const command = [
    '$ErrorActionPreference = "Stop"',
    'if ($PSVersionTable.PSEdition -ne "Desktop" -or $PSVersionTable.PSVersion.Major -ne 5) { throw "Windows PowerShell 5.1 required" }',
    'function Get-Process { param($Name, $ErrorAction) return $null }',
    'if ($env:CANNBOT_TEST_CLEAN_PATH -and (Get-Command node -ErrorAction SilentlyContinue)) { throw "Test PATH must not contain Node" }',
    '& $env:CANNBOT_TEST_PROVISION -PackageRoot $env:CANNBOT_TEST_PACKAGE -DshExecutable $env:CANNBOT_TEST_DSH ' + mode,
  ].join('; ')
  const env = { ...process.env, DSH_HOME: fixture.home, CANNBOT_TEST_PROVISION: provision, CANNBOT_TEST_PACKAGE: fixture.source, CANNBOT_TEST_DSH: fixture.executable || '' }
  if (fixture.cleanPath) {
    for (const key of Object.keys(env)) if (key.toLowerCase() === 'path') delete env[key]
    env.PATH = join(process.env.SystemRoot, 'System32'); env.CANNBOT_TEST_CLEAN_PATH = '1'
  }
  const result = spawnSync(join(process.env.SystemRoot, 'System32/WindowsPowerShell/v1.0/powershell.exe'), [
    '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
    '-EncodedCommand', Buffer.from(command, 'utf16le').toString('base64'),
  ], {
    env,
    encoding: 'utf8',
    windowsHide: true,
    timeout: 30_000,
  })
  assert.ifError(result.error)
  assert.equal(result.status, expectedStatus, result.stdout + result.stderr)
  return result.stdout + result.stderr
}

function readManifest(fixture) {
  const bytes = readFileSync(fixture.profile)
  assert.notDeepEqual([...bytes.subarray(0, 3)], [0xef, 0xbb, 0xbf], 'manifest must not contain a UTF-8 BOM')
  // Match DSH's direct JSON.parse, with no BOM stripping.
  return JSON.parse(bytes.toString('utf8'))
}

function assertInstalled(fixture) {
  const manifest = readManifest(fixture)
  assert.deepEqual(manifest, {
    ...original,
    dependencies: { ...original.dependencies, [packageName]: 'file:./node_modules/@cannbot-plugin/cannbot-dsh' },
    dsh: { profile: { ...original.dsh.profile, bundles: original.dsh.profile.bundles } },
  })
  assert.equal(JSON.parse(readFileSync(join(fixture.target, 'package.json'), 'utf8')).name, packageName)
}

test('PowerShell 5.1 install and reinstall produce parseable BOM-free profiles and preserve configuration', windowsOnly, (t) => {
  const state = fixture(t)
  runProvision(state)
  assertInstalled(state)
  runProvision(state)
  assertInstalled(state)
})

test('clean Windows reuses the Desktop runtime without Node on PATH or a legacy user runtime', windowsOnly, t => {
  const state = fixture(t)
  state.executable = join(state.home, '安装 目录', 'DeepSeek Harness.exe')
  const node = join(dirname(state.executable), 'resources/runtime/primary-runtime/dependencies/node/bin/node.exe')
  mkdirSync(dirname(node), { recursive: true })
  copyFileSync(process.execPath, node)
  state.cleanPath = true
  assert.equal(existsSync(join(state.home, 'dsh-runtimes')), false)
  runProvision(state)
  assertInstalled(state)
  runProvision(state, '-Check')
})

test('PowerShell 5.1 repair removes an existing BOM and restores the plugin bundle', windowsOnly, (t) => {
  const state = fixture(t)
  writeFileSync(state.profile, '\uFEFF' + JSON.stringify(original), 'utf8')
  assert.throws(() => JSON.parse(readFileSync(state.profile, 'utf8')), SyntaxError)
  runProvision(state, '-Repair')
  assertInstalled(state)
})

test('PowerShell 5.1 check rejects a BOM without changing the profile or installing files', windowsOnly, (t) => {
  const state = fixture(t)
  const bytes = Buffer.from('\uFEFF' + JSON.stringify(original), 'utf8')
  writeFileSync(state.profile, bytes)
  const output = runProvision(state, '-Check', 1)
  assert.match(output, /UTF-8 BOM/)
  assert.deepEqual(readFileSync(state.profile), bytes)
  assert.equal(existsSync(state.target), false)

  writeFileSync(state.profile, JSON.stringify(original), 'utf8')
  const cleanBytes = readFileSync(state.profile)
  runProvision(state, '-Check', 1)
  assert.deepEqual(readFileSync(state.profile), cleanBytes)
  assert.equal(existsSync(state.target), false)

  runProvision(state)
  const installedBytes = readFileSync(state.profile)
  const existingFiles = readdirSync(dirname(state.profile)).sort()
  runProvision(state, '-Check')
  assert.deepEqual(readFileSync(state.profile), installedBytes)
  assert.deepEqual(readdirSync(dirname(state.profile)).sort(), existingFiles, 'Check must not create backups or files')
})

test('PowerShell 5.1 check rejects missing companion files and missing enabled bundles without modifying the profile', windowsOnly, (t) => {
  const state = fixture(t)
  runProvision(state)
  const installed = readManifest(state)
  for (const missing of [packageName, workbenchName]) {
    const manifest = structuredClone(installed)
    manifest.dsh.profile.bundles = manifest.dsh.profile.bundles.filter(name => name !== missing)
    const bytes = Buffer.from(JSON.stringify(manifest), 'utf8')
    writeFileSync(state.profile, bytes)
    const files = readdirSync(dirname(state.profile)).sort()
    runProvision(state, '-Check', 1)
    assert.deepEqual(readFileSync(state.profile), bytes)
    assert.deepEqual(readdirSync(dirname(state.profile)).sort(), files)
  }
  const restored = Buffer.from(JSON.stringify(installed), 'utf8')
  writeFileSync(state.profile, restored)
  unlinkSync(join(state.target, 'lib', 'client.js'))
  runProvision(state, '-Check', 1)
  assert.deepEqual(readFileSync(state.profile), restored)
  assert.equal(existsSync(join(state.target, 'lib', 'client.js')), false, 'Check must not repair missing files')
})

test('PowerShell 5.1 uninstall removes only this plugin and writes a BOM-free profile', windowsOnly, (t) => {
  const state = fixture(t)
  runProvision(state)
  writeFileSync(state.profile, '\uFEFF' + readFileSync(state.profile, 'utf8'), 'utf8')
  runProvision(state, '-Uninstall')
  assert.deepEqual(readManifest(state), { ...original, dependencies: { 'existing-bundle': '1.2.3' }, dsh: { profile: { ...original.dsh.profile, bundles: ['existing-bundle'] } } })
  assert.equal(existsSync(state.target), false)
})

test('PowerShell 5.1 install and repair accept empty bundles and uninstall preserves the empty array', windowsOnly, (t) => {
  const empty = { ...original, dsh: { profile: { ...original.dsh.profile, bundles: [] } } }
  const state = fixture(t, empty)
  runProvision(state)
  assert.deepEqual(readManifest(state).dsh.profile.bundles, [packageName])

  // Simulate crash recovery removing the bundle list but retaining the package.
  const recovered = readManifest(state)
  recovered.dsh.profile.bundles = []
  writeFileSync(state.profile, '\uFEFF' + JSON.stringify(recovered), 'utf8')
  runProvision(state, '-Repair')
  assert.deepEqual(readManifest(state).dsh.profile.bundles, [packageName])

  runProvision(state, '-Uninstall')
  assert.deepEqual(readManifest(state), { ...empty, dependencies: { 'existing-bundle': '1.2.3' }, dsh: { profile: { ...empty.dsh.profile, bundles: [] } } })
  assert.equal(existsSync(state.target), false)
})

test('migration removes legacy companion registration while preserving saved remote inventory and state', windowsOnly, t => {
  const legacy = structuredClone(original)
  legacy.dependencies['@cannbot-plugin/cannbot-remote'] = 'file:./node_modules/@cannbot-plugin/cannbot-remote'
  legacy.dependencies['cannbot-dsh'] = '1.0.0-alpha.1'
  legacy.dsh.profile.bundles.push('@cannbot-plugin/cannbot-remote', 'cannbot-dsh')
  const state = fixture(t, legacy)
  const data = join(state.home, 'cannbot-remote')
  mkdirSync(data)
  for (const file of ['servers.json', 'state.json']) writeFileSync(join(data, file), '{"preserved":true}')
  runProvision(state)
  const manifest = readManifest(state)
  assert.deepEqual(manifest.dsh.profile.bundles, ['existing-bundle', packageName])
  assert.equal(manifest.dependencies['@cannbot-plugin/cannbot-remote'], undefined)
  assert.equal(manifest.dependencies['cannbot-dsh'], undefined)
  for (const file of ['servers.json', 'state.json']) assert.equal(readFileSync(join(data, file), 'utf8'), '{"preserved":true}')
})
