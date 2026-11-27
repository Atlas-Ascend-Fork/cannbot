// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import test from 'node:test'
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { mkdtemp, mkdir, readFile, rm, writeFile } from 'node:fs/promises'
import { join, resolve } from 'node:path'
import { tmpdir } from 'node:os'
import { pathToFileURL } from 'node:url'
import { createPackageArtifact } from '../tools/package-archive.mjs'
import { activateClient, installedClient } from '../plugin/backend/update-host.ts'

const sdk = createRequire(process.env.CANNBOT_TEST_DSH_SDK ? resolve(process.env.CANNBOT_TEST_DSH_SDK, 'package.json') : import.meta.url)
let bootPath, managerPath
try { bootPath = sdk.resolve('@deepseek-ai/dsh-app-boot'); managerPath = sdk.resolve('@deepseek-ai/dsh-plugin-manager') } catch { /* unbuilt SDK checkout */ }
const name = '@cannbot-plugin/cannbot-dsh'

test('real DSH pluginManager installs local archives, persists the exact build and restores the last working bundle on rejection', {
  skip: !bootPath || !managerPath ? 'requires the compiled DSH SDK (CANNBOT_TEST_DSH_SDK)' : false, timeout: 120000,
}, async t => {
  const { boot, initProfile, readProfilePatches, loadProfileDirectory } = await import(pathToFileURL(bootPath))
  const { default: PluginManager } = await import(pathToFileURL(managerPath))
  const home = await mkdtemp(join(tmpdir(), 'cannbot-profile-update-'))
  let ctx
  t.after(async () => { await ctx?.fiber.dispose(); await rm(home, { recursive: true, force: true }) })
  const dir = join(home, 'profiles', 'update-fixture'), installAnchor = join(home, 'package.json')
  await writeFile(installAnchor, JSON.stringify({ name: 'fixture', version: '0.2.1', dependencies: {} }))
  const core = join(home, 'node_modules', 'fixture-core')
  await mkdir(core, { recursive: true })
  await writeFile(join(core, 'package.json'), JSON.stringify({ name: 'fixture-core', version: '1.0.0', dsh: { bundle: { patch: './cordis.patch.yml' } } }))
  await writeFile(join(core, 'cordis.patch.yml'), JSON.stringify([{ insert: [{ id: 'manager', name: 'cordis:manager' }] }]))
  initProfile(dir, ['fixture-core'])
  await writeFile(join(dir, 'cordis.yml'), '[]\n')
  const managerEnv = { npm_config_offline: 'true', npm_config_store_dir: join(home, 'pnpm-store'), CI: 'true' }
  const profile = { name: 'update-fixture', home, dir, cwd: home, installAnchor, patchPath: join(dir, 'cordis.patch.yml'), startedBundles: ['fixture-core'], overlays: [],
    packageManager: process.env.CANNBOT_TEST_PNPM ? { command: process.execPath, args: [process.env.CANNBOT_TEST_PNPM], env: managerEnv } : { command: 'pnpm', args: [], env: managerEnv } }
  ctx = await boot('fixture', join(dir, 'cordis.yml'), readProfilePatches('fixture', profile), context => {
    context.provide('appReady', { onReady(listener) { listener(); return () => {} } })
    context.provide('profileContext', profile)
    context.loader.builtins.manager = PluginManager
  })
  const operations = []
  const install = spec => {
    operations.push(spec)
    return ctx.pluginManager.installBundle(spec, { saveExact: true, enabled: true, registry: 'https://registry.npmjs.org/' })
  }
  async function archive(version, buildId, broken = false) {
    const source = join(home, buildId)
    await mkdir(source)
    await writeFile(join(source, 'package.json'), JSON.stringify({ name, version, cannbotEdition: 'client', cannbotBuildId: buildId,
      files: ['cordis.patch.yml'], dsh: { bundle: { patch: broken ? './missing.yml' : './cordis.patch.yml' } } }))
    await writeFile(join(source, 'cordis.patch.yml'), '[]\n')
    return createPackageArtifact(source)
  }
  const previous = await archive('1.0.0', 'one'), next = await archive('1.0.1', 'two'), bad = await archive('1.0.2', 'bad', true)
  const oldArchive = join(home, 'one.tgz')
  await writeFile(oldArchive, previous.bytes)
  const initial = await install('file:' + oldArchive)
  assert.ok(['restart-required', 'applied'].includes(initial.application), JSON.stringify(initial))
  const receiptPath = join(dir, '.cannbot-install.json')
  const acceptedAt = '2026-11-01T00:00:00.000Z'
  await writeFile(receiptPath, JSON.stringify({ schemaVersion: 1, edition: 'client', version: '1.0.0', buildId: 'one',
    legalVersion: '1', acceptedAt }))
  async function upgrade(artifact, version, buildId, activate = install) {
    const release = { manifest: { version, buildId, dshRange: '>=0.2.0 <0.3.0',
      packages: { client: { url: 'https://test.invalid/client.tgz' } }, legal: { version: '1', documents: [] } } }
    return activateClient(profile, release, await installedClient(profile), activate, async () => artifact.bytes)
  }
  const success = await upgrade(next, '1.0.1', 'two')
  assert.ok(['restart-required', 'applied'].includes(success.application), JSON.stringify(success))
  const accepted = await readFile(receiptPath, 'utf8')
  assert.equal(JSON.parse(accepted).acceptedAt, acceptedAt)
  assert.equal(JSON.parse(accepted).buildId, 'two')
  assert.equal((await installedClient(profile)).buildId, 'two')
  const rejected = await upgrade(bad, '1.0.2', 'bad')
  assert.equal(rejected.application, 'failed')
  assert.notEqual(rejected.error?.code, 'stop-profile')
  assert.equal(await readFile(receiptPath, 'utf8'), accepted)
  const actual = await installedClient(profile)
  assert.equal(actual.version, '1.0.1'); assert.equal(actual.buildId, 'two')
  // Inject a lost activation response after the real package manager has
  // committed to disk, then let it execute the updater's compensating install.
  const third = await archive('1.0.3', 'three')
  let lost = false
  const ambiguous = await upgrade(third, '1.0.3', 'three', async spec => {
    const change = await install(spec)
    if (lost) return change
    assert.ok(['applied', 'restart-required'].includes(change.application), JSON.stringify(change))
    lost = true
    throw new Error('Simulated lost response')
  })
  assert.ok(lost)
  assert.equal(ambiguous.application, 'failed')
  assert.equal((await installedClient(profile)).buildId, 'two')
  assert.equal(await readFile(receiptPath, 'utf8'), accepted)
  const restarted = loadProfileDirectory('fixture', dir, installAnchor)
  assert.deepEqual(restarted.layers.map(layer => layer.packageName), ['fixture-core', name])
  assert.deepEqual(restarted.skippedBundles, [])
  assert.match(operations.at(-1), /restore-.*\.tgz$/)
})
