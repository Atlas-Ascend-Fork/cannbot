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
import { dirname, join, resolve } from 'node:path'
import { gunzipSync } from 'node:zlib'
import { packageCurrent } from '../tools/package.mjs'
import { inside } from '../tools/build-bootstrap.mjs'


const owner = resolve('.acceptance-package-current-tests')
const put = async (root, path, text) => { const file = join(root, path); await mkdir(dirname(file), { recursive: true }); await writeFile(file, text) }
async function fixture(t) {
  await mkdir(owner, { recursive: true })
  const base = await mkdtemp(join(owner, 'case-')), root = join(base, 'dsh')
  t.after(async () => { assert(inside(owner, base)); await rm(base, { recursive: true, force: true }) })
  await put(root, 'LICENSE', 'repository license')
  await put(root, 'package.json', JSON.stringify({ name: '@cannbot-plugin/cannbot-dsh', version: '1.0.0-alpha.1', files: ['lib', 'remote', 'LICENSE', 'README.md'] }))
  await put(root, 'remote/deploy-package.mjs', '// deployment source')
  await put(root, 'README.md', 'main package')
  await put(root, 'packages/short/package.json', JSON.stringify({ name: 'cannbot-dsh', version: '1.0.0-alpha.1', files: ['README.md', 'LICENSE'], dependencies: { '@cannbot-plugin/cannbot-dsh': '1.0.0-alpha.1' } }))
  await put(root, 'packages/short/README.md', 'short package')
  let builds = 0
  const build = async ({ root: received }) => { assert.equal(received, root); builds++; await put(root, 'lib/index.js', 'export {}'); await put(root, 'lib/client.js', 'factory'); await put(root, 'lib/server/index.js', 'server host'); await put(root, 'lib/server/client.js', 'server UI'); await put(root, 'lib/.cannbot-build.json', '{"hash":"fixture"}') }
  return { root, build, builds: () => builds, options: { root, build, log() {} } }
}
function entries(archive) {
  const bytes = gunzipSync(archive), result = new Map(); let offset = 0
  while (offset + 512 <= bytes.length && bytes[offset]) {
    const header = bytes.subarray(offset, offset + 512)
    const string = (at, count) => header.subarray(at, at + count).toString().replace(/\0.*$/s, '')
    const name = [string(345, 155), string(0, 100)].filter(Boolean).join('/'), size = Number.parseInt(string(124, 12).trim(), 8)
    result.set(name, bytes.subarray(offset + 512, offset + 512 + size).toString())
    offset += 512 + Math.ceil(size / 512) * 512
  }
  return result
}

test('main packaging builds current source and writes the identical deployable archive', async t => {
  const f = await fixture(t), result = await packageCurrent(f.options)
  assert.equal(f.builds(), 1)
  const packed = await readFile(result.file)
  assert.equal(result.buildId.length, 64)
  const files = entries(packed)
  assert(files.has('package/lib/index.js')); assert(files.has('package/remote/server.tgz')); assert(!files.has('package/lib/server/index.js'))
  assert.equal(files.get('package/LICENSE'), 'repository license')
  assert(![...files.keys()].some(name => /node_modules|DSH_SOURCE|build-cache/.test(name)))
})

test('short packaging requires no DSH checkout, build tools or main lib and includes parent license', async t => {
  const f = await fixture(t)
  const result = await packageCurrent({ ...f.options, short: true, build: async () => assert.fail('short package must not build') })
  const files = entries(await readFile(result.file))
  assert.equal(files.get('package/LICENSE'), 'repository license')
  assert.equal(JSON.parse(files.get('package/package.json')).name, 'cannbot-dsh')
  assert.equal(f.builds(), 0)
})

test('concurrent edition and short builds produce all four packages deterministically', async t => {
  const f = await fixture(t)
  await put(f.root, 'THIRD_PARTY_NOTICES.md', 'shared notices')
  await put(f.root, 'icon.svg', '<svg/>')
  await put(f.root, 'packages/short-server/package.json', await readFile(new URL('../packages/short-server/package.json', import.meta.url)))
  await put(f.root, 'packages/short-server/cordis.patch.yml', await readFile(new URL('../packages/short-server/cordis.patch.yml', import.meta.url)))
  await put(f.root, 'packages/short-server/README.md', 'server entry')
  const [main, , serverEntry] = await Promise.all([
    packageCurrent(f.options), packageCurrent({ ...f.options, short: true }), packageCurrent({ ...f.options, short: 'server' }),
  ])
  const files = entries(await readFile(serverEntry.file))
  const manifest = JSON.parse(files.get('package/package.json'))
  assert.equal(manifest.dependencies['@cannbot-plugin/cannbot-dsh-server'], manifest.version)
  assert.match(files.get('package/cordis.patch.yml'), /name: '@cannbot-plugin\/cannbot-dsh-server'/)
  assert.equal(files.get('package/LICENSE'), 'repository license')
  assert.equal(files.get('package/THIRD_PARTY_NOTICES.md'), 'shared notices')
  assert.equal(files.get('package/icon.svg'), '<svg/>')
  assert.equal((await readdir(join(f.root, 'dist'))).filter(file => file.endsWith('.tgz')).length, 4)
  assert.equal((await packageCurrent(f.options)).buildId, main.buildId)
})

test('compiler failure cannot publish a main artifact or claim successful packaging', async t => {
  const f = await fixture(t)
  await assert.rejects(packageCurrent({ ...f.options, build: async () => { throw new Error('compile failed') } }), /compile failed/)
  await assert.rejects(readdir(join(f.root, 'dist')), error => error.code === 'ENOENT')
})
