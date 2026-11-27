// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdir, mkdtemp, readFile, readdir, rm, writeFile } from 'node:fs/promises'
import { join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { assembleFeed } from '../tools/release.mjs'
import { prepare, frozenRelease, getPackage, releaseSource } from '../installers/common/release.mjs'

test('the shipped installer reads the master agreements and downloads the two pinned npm editions', async t => {
  const raw = 'https://api.gitcode.com/api/v5/repos/cann/cannbot/raw/dsh/'
  const source = await releaseSource(new URL('../installers/common/release-source.json', import.meta.url))
  assert.equal(source.manifestUrl, raw + 'release/manifest.json?ref=master')
  const stage = await mkdtemp(resolve('.acceptance-master-release-'))
  t.after(() => rm(stage, { recursive: true, force: true }))
  const fromCheckout = url => {
    assert.ok(url.startsWith(raw), url)
    assert.equal(new URL(url).search, '?ref=master')
    return readFile(new URL('../' + url.slice(raw.length).split('?')[0], import.meta.url))
  }
  const manifest = await prepare(source, stage, fromCheckout)
  assert.deepEqual(manifest.legal.documents.map(({ title }) => title), ['用户协议', '隐私政策', '开源软件声明'])
  for (const { id, url, viewUrl } of manifest.legal.documents) {
    assert.equal(url, raw + 'legal/' + id + '.txt?ref=master')
    assert.equal(viewUrl, 'https://gitcode.com/cann/cannbot/blob/master/dsh/legal/' + id + '.txt')
    assert.deepEqual(await readFile(join(stage, id + '.txt')), await fromCheckout(url))
  }
  for (const edition of ['client', 'server']) {
    const short = edition === 'server' ? 'cannbot-dsh-server' : 'cannbot-dsh'
    const tarball = 'https://registry.npmjs.org/@cannbot-plugin/' + short + '/-/' + short + '-' + manifest.version + '.tgz'
    const file = await getPackage(manifest, edition, stage, async url => {
      assert.equal(url, tarball)
      return Buffer.from(edition)
    })
    assert.equal(await readFile(file, 'utf8'), edition)
  }
})

test('public feed uses each published tarball and the common build ID without rebuilding packages', async t => {
  const root = new URL('../', import.meta.url)
  const config = JSON.parse(await readFile(new URL('tools/release-config.json', root), 'utf8'))
  const { version } = JSON.parse(await readFile(new URL('package.json', root), 'utf8'))
  const output = await mkdtemp(resolve('.acceptance-npm-feed-'))
  t.after(() => rm(output, { recursive: true, force: true }))
  let serverBuild = 'published-build'
  const download = async url => {
    const [, scope, short, requestedVersion] = new URL(url).pathname.split('/')
    assert.equal(requestedVersion, version)
    const server = short === 'cannbot-dsh-server'
    return Buffer.from(JSON.stringify({
      name: scope + '/' + short, version, cannbotEdition: server ? 'server' : 'client',
      cannbotBuildId: server ? serverBuild : 'published-build', dist: { tarball: 'https://registry.npmjs.org/' + short + '.tgz' },
    }))
  }
  const options = { root: fileURLToPath(root), output, config, download, build: () => assert.fail('unexpected build') }
  const dir = await assembleFeed(options)
  assert.deepEqual(await readdir(dir), ['manifest.json'])
  const manifest = JSON.parse(await readFile(join(dir, 'manifest.json'), 'utf8'))
  assert.equal(manifest.buildId, serverBuild)
  assert.equal(manifest.packages.server.url, 'https://registry.npmjs.org/cannbot-dsh-server.tgz')
  serverBuild = 'different-build'
  await assert.rejects(assembleFeed(options), /different build IDs/)
})

test('publish and install from one manifest URL and keep the agreements shown in the installer', async t => {
  const root = await mkdtemp(resolve('.acceptance-release-'))
  t.after(() => rm(root, { recursive: true, force: true }))
  const source = { manifestUrl: 'https://release.test/manifest.json' }
  const config = { assetBaseUrl: 'https://release.test/', hosts: { 'linux-x64': { version: '0.2.1-rc.3' } } }
  await mkdir(join(root, 'legal'))
  await mkdir(join(root, 'tools'))
  const documents = ['user-agreement', 'privacy-policy', 'open-source-notices'].map(id => ({ id, title: id, path: id + '.txt' }))
  for (const d of documents) await writeFile(join(root, 'legal', d.path), 'fixture ' + d.id)
  await writeFile(join(root, 'tools/legal-manifest.json'), JSON.stringify({ version: '1', documents }))
  await writeFile(join(root, 'package.json'), JSON.stringify({ version: '1.2.3', engines: { dsh: '>=0.1.1-rc.1 <0.3.0' } }))
  const editions = Object.fromEntries(['client','server'].map(role => [role, {
    name: '@cannbot-plugin/cannbot-dsh' + (role === 'server' ? '-server' : ''), bytes: Buffer.from(role),
  }]))
  const dir = await assembleFeed({ root, output: join(root, 'feed'), config, build: async () => {}, archives: async () => ({ ...editions, buildId: 'build-test' }) })
  assert.deepEqual((await readdir(dir)).sort(), ['legal','manifest.json','releases'])
  const stage = join(root, 'installation')
  const fetchLocal = url => readFile(join(dir, new URL(url).pathname.slice(1)))
  const release = await prepare(source, stage, fetchLocal)
  assert.equal(release.version, '1.2.3')
  assert.deepEqual(Object.keys(release.packages.server).sort(), ['name','url'])
  assert.equal(await readFile(join(stage, 'privacy-policy.txt'), 'utf8'), 'fixture privacy-policy')
  assert.equal(await readFile(await getPackage(release, 'server', stage, fetchLocal), 'utf8'), 'server')
  await writeFile(join(dir, 'manifest.json'), '{}')
  assert.equal((await frozenRelease(stage)).buildId, 'build-test')
})
