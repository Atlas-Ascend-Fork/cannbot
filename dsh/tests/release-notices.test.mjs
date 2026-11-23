// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync, readdirSync } from 'node:fs'
import { createRequire } from 'node:module'
import { createHash } from 'node:crypto'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { gunzipSync } from 'node:zlib'
import { createArtifact } from '../src/remote/artifact.js'
import { resolveSource } from '../scripts/source.mjs'

const root = fileURLToPath(new URL('../', import.meta.url))
const read = file => readFileSync(file, 'utf8').replaceAll('\r\n', '\n').trimEnd()
const require = createRequire(import.meta.url)

test('notices preserve complete licenses for code actually included in the release', () => {
  const notices = read(join(root, 'THIRD_PARTY_NOTICES.md'))
  const yaml = dirname(require.resolve('yaml/package.json'))
  const tsdown = require.resolve('tsdown/package.json', { paths: [resolveSource()] })
  const rolldown = dirname(createRequire(tsdown).resolve('rolldown/package.json'))
  for (const [component, directory] of [['yaml', yaml], ['Rolldown', rolldown], ['@xterm/xterm', dirname(require.resolve('@xterm/xterm/package.json'))]]) {
    const version = JSON.parse(read(join(directory, 'package.json'))).version
    assert.ok(notices.includes(`${component} ${version}`), `Audit ${component} ${version} before publishing`)
    assert.ok(notices.includes(read(join(directory, 'LICENSE'))), `${component}: complete upstream license`)
  }
  assert.ok(notices.includes(read(join(rolldown, 'THIRD-PARTY-LICENSE'))), 'retain inherited compiler notices')
  assert.ok(notices.includes(read(join(resolveSource(), 'LICENSE'))), 'generated DSH client glue retains upstream license')
  assert.ok(notices.includes(read(join(root, 'packages/install/LICENSE'))), 'pre-existing file-lock component retains its own license')
  const oxc = notices.split('## @oxc-project/runtime 0.156.0 — MIT')[1]?.match(/```text\n([\s\S]*?)\n```/)?.[1]
  assert.ok(oxc, 'Oxc runtime notice is required')
  // Exact full LICENSE from the versioned npm package, normalized to LF.
  assert.equal(createHash('sha256').update(oxc).digest('hex'), '5b0650b078309ba2772569bb419e40e6883874af64d21bd9c27b44cc1a8e46ff')
})

test('built module inventory contains no unaudited inline third-party source', () => {
  const host = readdirSync(join(root, 'lib')).filter(name => name.endsWith('.js') && !name.startsWith('client')).map(name => read(join(root, 'lib', name))).join('\n')
  const markers = [...host.matchAll(/^\/\/ (.+\.(?:js|mjs|ts|tsx))$/gm)].map(match => match[1])
  assert.ok(markers.some(value => value.includes('node_modules/yaml/')))
  assert.ok(markers.includes('\\0rolldown/runtime.js'))
  assert.ok(markers.includes('packages/install/lib/file-lock.mjs'))
  const oxcRuntime = '\\0@oxc-project+runtime@0.156.0/helpers/esm/usingCtx.js'
  assert.ok(markers.includes(oxcRuntime))
  for (const marker of markers) {
    assert.ok(marker.startsWith('src/') || marker === 'packages/install/lib/file-lock.mjs' || marker === '\\0rolldown/runtime.js' || marker === oxcRuntime || /node_modules\/yaml\/dist\//.test(marker), `Audit bundled module: ${marker}`)
  }
  const client = read(join(root, 'lib/client.js'))
  const map = JSON.parse(read(join(root, 'lib/client.js.map')))
  assert.ok(map.sources.length > 0)
  for (const source of map.sources) assert.ok(source.startsWith('../src/') && !source.includes('node_modules') || /node_modules\/@xterm\/xterm\//.test(source), `Audit client input: ${source}`)
  assert.ok(client.includes('window.__ModuleLoader__.load('), 'audited generated host wrapper')
  assert.ok(client.includes('require("react")'), 'React stays host-provided')
  assert.ok(client.includes('require("@deepseek-ai/dsh-client-ui-primitives")'), 'native UI stays host-provided')
})

test('main release archive distributes the unchanged root license and full notices', () => {
  const archive = gunzipSync(createArtifact(root).bytes), entries = new Map()
  for (let offset = 0; offset + 512 <= archive.length && archive[offset];) {
    const header = archive.subarray(offset, offset + 512)
    const field = (start, size) => header.subarray(start, start + size).toString().replace(/\0.*$/s, '')
    const name = [field(345, 155), field(0, 100)].filter(Boolean).join('/')
    const size = Number.parseInt(field(124, 12).trim(), 8)
    entries.set(name, archive.subarray(offset + 512, offset + 512 + size))
    offset += 512 + Math.ceil(size / 512) * 512
  }
  assert.deepEqual(entries.get('package/LICENSE'), readFileSync(join(root, '../LICENSE')))
  assert.deepEqual(entries.get('package/THIRD_PARTY_NOTICES.md'), readFileSync(join(root, 'THIRD_PARTY_NOTICES.md')))
  assert.ok(![...entries.keys()].some(name => name.includes('node_modules/') || name.endsWith('.exe')))
})
