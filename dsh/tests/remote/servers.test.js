// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  allocateLocalPort,
  loadInventory,
  mergeInventory,
  normalizeInventory,
  saveInventory,
} from '../../plugin/backend/ssh/servers.js'
import { join } from 'node:path'
import { mkdirSync, rmSync } from 'node:fs'

const SCRATCH = join(process.cwd(), '_scratch', 'tests', 'inventory')

test('normalizeInventory drops entries without alias and de-duplicates', () => {
  const normalized = normalizeInventory({
    servers: [
      { alias: 'npu-01', label: 'NPU 01' },
      { label: 'no alias' },
      { alias: 'npu-01', label: 'duplicate' },
      { alias: 'npu-02' },
    ],
  })
  assert.equal(normalized.servers.length, 2)
  assert.equal(normalized.servers[0].label, 'duplicate', 'last write wins')
  assert.equal(normalized.servers[1].label, 'npu-02')
  assert.equal(normalized.servers[1].group, 'default')
})

test('mergeInventory marks shared entries and flags ssh-config presence', () => {
  const merged = mergeInventory({
    shared: { version: 1, servers: [{ alias: 'npu-01', label: '训练机 1' }, { alias: 'npu-09', label: '未配置' }] },
    sshAliases: ['npu-01', 'personal-box'],
    sshResolved: [
      { alias: 'npu-01', hostName: '10.0.0.11', user: 'HwHiAiUser', port: 2222, proxyJump: '' },
      { alias: 'personal-box', hostName: 'p.example.com', user: 'me', port: 22, proxyJump: 'bastion' },
    ],
  })
  const byAlias = new Map(merged.servers.map((server) => [server.alias, server]))

  const npu01 = byAlias.get('npu-01')
  assert.equal(npu01.source, 'shared')
  assert.equal(npu01.label, '训练机 1')
  assert.equal(npu01.inSshConfig, true)
  assert.equal(npu01.user, 'HwHiAiUser')
  assert.equal(npu01.port, 2222)

  const npu09 = byAlias.get('npu-09')
  assert.equal(npu09.inSshConfig, false)

  const personal = byAlias.get('personal-box')
  assert.equal(personal.source, 'ssh-config')
  assert.equal(personal.proxyJump, 'bastion')

  assert.equal(merged.servers[0].source, 'shared', 'shared entries sort first')
})

test('allocateLocalPort skips ports already assigned to other servers', () => {
  assert.equal(allocateLocalPort({ used: [] }), 17633)
  assert.equal(allocateLocalPort({ used: [17633] }), 17634)
  assert.equal(allocateLocalPort({ used: [17633, 17634, 17636] }), 17635)
  assert.equal(allocateLocalPort({ used: [], start: 18000 }), 18000)
})

test('saveInventory/loadInventory round-trips', () => {
  rmSync(SCRATCH, { recursive: true, force: true })
  mkdirSync(SCRATCH, { recursive: true })
  const file = join(SCRATCH, 'servers.json')
  saveInventory(file, { servers: [{ alias: 'npu-01', label: 'NPU 01', remotePort: 17633 }] })
  const loaded = loadInventory(file)
  assert.equal(loaded.servers.length, 1)
  assert.equal(loaded.servers[0].remotePort, 17633)
  assert.equal(loadInventory(join(SCRATCH, 'missing.json')), null)
})
