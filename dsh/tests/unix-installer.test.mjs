// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import test from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { installUnix } from '../installers/common/install-unix.mjs'
import { packages } from '../installers/common/release.mjs'

const source = { manifestUrl: 'https://release.test/manifest.json' }
async function fixture(t, platform, edition) {
  const home = await mkdtemp(join(tmpdir(), 'cannbot-platform-'))
  t.after(() => rm(home, { recursive: true, force: true }))
  const files = new Map(), calls = []
  function asset(name, text) {
    const data = Buffer.from(text), url = 'https://release.test/' + name
    files.set(url, data)
    return { url }
  }
  const ids = ['user-agreement', 'privacy-policy', 'open-source-notices']
  const manifest = { schemaVersion: 1, channel: 'stable', version: '1.2.3', buildId: 'build-123',
    expiresAt: new Date(Date.now() + 3600000).toISOString(), minInstallerVersion: '1.0.0', dshRange: '>=0.1.1-rc.1 <0.3.0',
    hosts: { [platform + '-x64']: {version: '0.2.1-rc.3'} }, legal: { version: '2026.11', documents: ids.map(id => ({ id, title: id, ...asset(id, 'terms of ' + id) })) },
    packages: Object.fromEntries(Object.entries(packages).map(([key, name]) => [key, { name, ...asset(key, key + '-fixture-bytes') }])) }
  const bytes = Buffer.from(JSON.stringify(manifest))
  files.set(source.manifestUrl, bytes)
  const dshHome = join(home, '.dsh'), profile = edition === 'server' ? 'cannbot-server' : 'web'
  const profileDir = join(dshHome, 'profiles', profile)
  const options = { home, dshHome, temp: join(home, 'tmp'), source, platform, archName: 'x64',
    download: async url => { assert.ok(files.has(url)); return files.get(url) },
    consent: async (release, stage) => { assert.equal(release.version, manifest.version); assert.equal(readFileSync(join(stage, 'privacy-policy.txt'), 'utf8'), 'terms of privacy-policy') },
    execute(command, args) {
      calls.push([command, args])
      if (command === '/bin/sh') return { status: 0, stdout: '/tools/' + args.at(-1) }
      if (args[0] === '--version') return { status: 0, stdout: 'dsh 0.2.1-rc.3' }
      assert.equal(command, '/tools/dsh')
      assert.deepEqual(args.slice(0, 4), ['plugin','--profile',profile,'add'])
      assert.equal(readFileSync(args[4].slice(5), 'utf8'), edition + '-fixture-bytes')
      const file = join(profileDir, 'package.json'), pkg = existsSync(file) ? JSON.parse(readFileSync(file)) : {dsh:{profile:{bundles:[]}}}
      pkg.dsh.profile.bundles.push(packages[edition])
      writeFileSync(file, JSON.stringify(pkg))
      const installed = join(profileDir, 'node_modules', packages[edition], 'package.json')
      mkdirSync(dirname(installed), {recursive:true})
      writeFileSync(installed, JSON.stringify({name:packages[edition], version:manifest.version, cannbotEdition:edition, cannbotBuildId:manifest.buildId}))
      return { status: 0 }
    } }
  return { options, manifest, profileDir, calls }
}

for (const [platform, edition] of [['linux','client'],['linux','server'],['darwin','client']]) {
  test(platform + ' ' + edition + ' activates the selected build and records the accepted legal version', async t => {
    const { options, manifest, profileDir } = await fixture(t, platform, edition)
    await installUnix({edition}, options)
    const receipt = JSON.parse(readFileSync(join(profileDir, '.cannbot-install.json')))
    assert.equal(receipt.buildId, manifest.buildId)
    assert.equal(receipt.edition, edition)
    assert.equal(receipt.legalVersion, manifest.legal.version)
    const launch = edition === 'client' ? 'cannbot' : 'cannbot-cannbot-server'
    assert.match(readFileSync(join(options.home, '.local/share/cannbot/bin', launch), 'utf8'), new RegExp("--profile '" + (edition === 'server' ? 'cannbot-server' : 'web') + "' --host 127\\.0\\.0\\.1"))
    if (edition === 'server') assert.deepEqual(JSON.parse(readFileSync(join(profileDir, 'package.json'))).dsh.profile.bundles, ['@deepseek-ai/dsh-base','@deepseek-ai/dsh-web-app',packages.server])
  })
}
test('declined consent and unsupported server editions leave profiles untouched', async t => {
  const {options, profileDir, calls} = await fixture(t, 'darwin', 'client')
  await assert.rejects(installUnix({edition:'server'}, options), /requires Linux/)
  options.consent = async () => { throw new Error('declined') }
  await assert.rejects(installUnix({edition:'client'}, options), /declined/)
  assert.equal(existsSync(profileDir), false)
  assert.equal(calls.length, 0)
})
