// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { test } from 'node:test'
import assert from 'node:assert/strict'
import { mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, writeFileSync, existsSync, symlinkSync } from 'node:fs'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { ensureWorkbench as installWorkbench, inspectWorkbench, packageManager, WORKBENCH, SHORT, VERSION } from '../../scripts/windows/ensure-workbench.mjs'

const ARTIFACT = { hash: 'a'.repeat(64), bytes: Buffer.from('current-source-archive') }
const ensureWorkbench = (profile, options = {}) => installWorkbench(profile, { artifact: ARTIFACT, ...options })

function fixture(t, manifest = {}) {
  const root = mkdtempSync(join(tmpdir(), 'cannbot-official-test-'))
  t.after(() => rmSync(root, { recursive: true, force: true }))
  writeFileSync(join(root, 'package.json'), JSON.stringify(manifest))
  return root
}
function official(root, name = WORKBENCH, dependencies) {
  const dir = join(root, 'node_modules', ...name.split('/'))
  mkdirSync(join(dir, 'lib'), { recursive: true })
  writeFileSync(join(dir, 'package.json'), JSON.stringify({ name, version: VERSION, dependencies }))
  for (const file of ['lib/index.js', 'lib/client.js', 'cordis.patch.yml']) writeFileSync(join(dir, file), '')
  return dir
}

test('selects pnpm bundled beside the Desktop Node without depending on PATH', t => {
  const root = fixture(t)
  const runtime = join(root, '安装 目录', 'resources/runtime/primary-runtime/dependencies')
  const cli = join(runtime, 'pnpm/bin/pnpm.cjs')
  mkdirSync(join(runtime, 'pnpm/bin'), { recursive: true })
  writeFileSync(cli, '// fixture')
  assert.deepEqual(packageManager(join(runtime, 'node/bin/node.exe')), { cli, kind: 'pnpm' })
})

test('installs into an isolated store and links the official package without changing profile JSON', (t) => {
  const root = fixture(t, { custom: 'preserve', dependencies: { example: '1' } })
  const before = readFileSync(join(root, 'package.json'))
  let installations = 0
  const installed = ensureWorkbench(root, { install(store) { installations++; official(store) } })
  assert.equal(installed.bundle, WORKBENCH)
  assert.equal(installed.reused, false)
  assert.equal(realpathSync(installed.directory), realpathSync(join(root, '.cannbot-workbench', ARTIFACT.hash, 'node_modules', ...WORKBENCH.split('/'))))
  assert.deepEqual(readFileSync(join(root, 'package.json')), before)
  assert.equal(ensureWorkbench(root, { install() { throw new Error('must reuse') } }).reused, true)
  assert.equal(installations, 1)
})

test('source deployment replaces an old short installation with the current main package', (t) => {
  const root=fixture(t,{dependencies:{[SHORT]:VERSION},dsh:{profile:{bundles:[SHORT]}}})
  const old=official(root);official(root,SHORT,{[WORKBENCH]:VERSION})
  writeFileSync(join(old,'lib/client.js'),'old source')
  const installed=ensureWorkbench(root,{install(store){ const current=official(store);writeFileSync(join(current,'lib/client.js'),'new source') }})
  assert.equal(installed.bundle,WORKBENCH)
  assert.equal(readFileSync(join(installed.directory,'lib/client.js'),'utf8'),'new source')
  assert.equal(inspectWorkbench(root).bundle,SHORT,'profile registration changes are owned by provisioning')
})

test('a same-version source hash change installs a new store and keeps the previous source recoverable', (t) => {
  const root=fixture(t)
  const first=ensureWorkbench(root,{install: store=>official(store)})
  const previous=realpathSync(first.directory)
  const second=ensureWorkbench(root,{artifact:{...ARTIFACT,hash:'b'.repeat(64)},install:store=>official(store)})
  assert.notEqual(realpathSync(second.directory),previous)
  assert.ok(existsSync(join(previous,'lib/client.js')))
})

test('validates pnpm junctions using the real package directory for dependency resolution', (t) => {
  const root = fixture(t)
  const installed = ensureWorkbench(root, { install(store) {
    const versionRoot = join(store, 'node_modules', '.pnpm', 'cannbot-dsh@1')
    const core = official(versionRoot, WORKBENCH, { 'private-catalog': '1' })
    const dependency = join(versionRoot, 'node_modules', 'private-catalog')
    mkdirSync(dependency, { recursive: true })
    writeFileSync(join(dependency, 'package.json'), JSON.stringify({ name: 'private-catalog', version: '1' }))
    const link = join(store, 'node_modules', ...WORKBENCH.split('/'))
    mkdirSync(join(store, 'node_modules', '@cannbot-plugin'), { recursive: true })
    symlinkSync(core, link, process.platform === 'win32' ? 'junction' : 'dir')
  } })
  assert.equal(installed.bundle, WORKBENCH)
  assert.equal(inspectWorkbench(root).reused, true)
})

test('failed download leaves the existing profile and bundle links untouched', (t) => {
  const root = fixture(t, { name: 'desktop', custom: 'unchanged' })
  const before = readFileSync(join(root, 'package.json'))
  assert.throws(() => ensureWorkbench(root, { install() { throw new Error('network failed') } }), /network failed/)
  assert.deepEqual(readFileSync(join(root, 'package.json')), before)
  assert.equal(existsSync(join(root, 'node_modules', ...WORKBENCH.split('/'))), false)
})
