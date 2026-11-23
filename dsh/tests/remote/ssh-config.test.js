// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { test } from 'node:test'
import assert from 'node:assert/strict'
import { mkdirSync, writeFileSync, rmSync } from 'node:fs'
import { join } from 'node:path'
import {
  concreteAliases,
  parseSshConfig,
  parseSshG,
  readConfigTree,
  resolveFromBlocks,
  listAliases,
} from '../../src/remote/ssh-config.js'

const SCRATCH = join(process.cwd(), '_scratch', 'tests')

function withTempDir(name, fn) {
  const dir = join(SCRATCH, name)
  rmSync(dir, { recursive: true, force: true })
  mkdirSync(dir, { recursive: true })
  return fn(dir)
}

const SAMPLE = `
# global defaults
Host *
  ServerAliveInterval 30

Host npu-01
  HostName 10.0.0.11
  User HwHiAiUser
  Port 2222
  IdentityFile ~/.ssh/id_ed25519

Host npu-02 npu-02-alias
  HostName 10.0.0.12
  User root
  ProxyJump bastion

Host bastion
  HostName bastion.example.com
  User jump
`

test('parseSshConfig keeps blocks in order and lowercases keys', () => {
  const blocks = parseSshConfig(SAMPLE)
  assert.equal(blocks.length, 4)
  assert.deepEqual(blocks[1].aliases, ['npu-01'])
  assert.equal(blocks[1].options.hostname, '10.0.0.11')
  assert.equal(blocks[1].options.port, '2222')
})

test('parseSshConfig keeps directives that precede the first Host block', () => {
  const blocks = parseSshConfig('Include ~/.ssh/conf.d/*.conf\nServerAliveInterval 30\nHost a\n  HostName 1.2.3.4\n')
  assert.equal(blocks.length, 2)
  assert.deepEqual(blocks[0].aliases, [])
  assert.equal(blocks[0].options.include, '~/.ssh/conf.d/*.conf')
  assert.equal(blocks[1].aliases[0], 'a')
})

test('concreteAliases drops wildcards and de-duplicates', () => {
  const blocks = parseSshConfig(SAMPLE)
  assert.deepEqual(concreteAliases(blocks), ['npu-01', 'npu-02', 'npu-02-alias', 'bastion'])
})

test('resolveFromBlocks uses first-match-wins semantics', () => {
  const blocks = parseSshConfig(SAMPLE)
  const resolved = resolveFromBlocks(blocks)
  const npu01 = resolved.find((entry) => entry.alias === 'npu-01')
  assert.equal(npu01.hostName, '10.0.0.11')
  assert.equal(npu01.user, 'HwHiAiUser')
  assert.equal(npu01.port, 2222)

  const npu02 = resolved.find((entry) => entry.alias === 'npu-02-alias')
  assert.equal(npu02.port, 22, 'no Port means 22')
  assert.equal(npu02.proxyJump, 'bastion')

  const bastion = resolved.find((entry) => entry.alias === 'bastion')
  assert.equal(bastion.user, 'jump')
  assert.equal(bastion.hostName, 'bastion.example.com')
})

test('readConfigTree follows one level of Include stubs', () => {
  withTempDir('include', (dir) => {
    writeFileSync(join(dir, 'config.d'), '')
    mkdirSync(join(dir, 'conf.d'), { recursive: true })
    writeFileSync(join(dir, 'conf.d', 'a.conf'), 'Host included-a\n  HostName 1.1.1.1\n')
    writeFileSync(join(dir, 'conf.d', 'b.conf'), 'Host included-b\n  HostName 2.2.2.2\n')
    writeFileSync(join(dir, 'config'), 'Include conf.d/*.conf\nHost local\n  HostName 3.3.3.3\n')

    const files = readConfigTree(join(dir, 'config'))
    assert.ok(files.length >= 3)
    const aliases = listAliases(join(dir, 'config')).aliases
    assert.ok(aliases.includes('included-a'))
    assert.ok(aliases.includes('included-b'))
    assert.ok(aliases.includes('local'))
  })
})

test('parseSshG reads effective values from ssh -G output', () => {
  const output = [
    'host npu-01',
    'hostname 10.0.0.11',
    'user HwHiAiUser',
    'port 2222',
    'identityfile ~/.ssh/id_ed25519',
    'identityfile ~/.ssh/id_rsa',
    'proxyjump none',
  ].join('\n')
  const parsed = parseSshG(output)
  assert.equal(parsed.hostName, '10.0.0.11')
  assert.equal(parsed.user, 'HwHiAiUser')
  assert.equal(parsed.port, 2222)
  assert.equal(parsed.identityFile.length, 2)
  assert.equal(parsed.proxyJump, '')
})

test('missing ssh config is not an error', () => {
  const result = listAliases(join(SCRATCH, 'does-not-exist', 'config'))
  assert.deepEqual(result.aliases, [])
})
