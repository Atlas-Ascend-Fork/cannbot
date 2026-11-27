// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { test } from 'node:test'
import assert from 'node:assert/strict'
import { mkdtempSync, mkdirSync, readFileSync, writeFileSync, existsSync, rmSync, statSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { tmpdir } from 'node:os'
import { addServerRecord, parseServerCommand, ServerInputError } from '../../plugin/backend/ssh/add-server.js'
import { createManager } from '../../plugin/backend/ssh/manager.js'
import { createRouter, registerRoutes, ROUTE } from '../../plugin/backend/ssh/routes.js'
import { listAliases } from '../../plugin/backend/ssh/ssh-config.js'

function fixture(t, content = 'Host DevEnv950\r\n  HostName 10.0.0.20\r\n  User existing\r\n  Port 22\r\n') {
  const root = mkdtempSync(join(tmpdir(), 'cannbot-add-server-'))
  t.after(() => { assert.equal(dirname(resolve(root)), resolve(tmpdir())); rmSync(root, { recursive: true, force: true }) })
  const configPath = join(root, 'ssh', 'config'), serversPath = join(root, 'data', 'servers.json')
  mkdirSync(dirname(configPath)); mkdirSync(dirname(serversPath)); writeFileSync(configPath, content)
  const stored = { version: 1, custom: { keep: true }, servers: [{ alias: 'DevEnv950', label: '已有服务器', group: 'team', note: 'retain note', pluginVersion: 'old-version', unknown: 'keep' }] }
  writeFileSync(serversPath, JSON.stringify(stored))
  return { root, configPath, serversPath, stored, before: Buffer.from(content), add: request => addServerRecord(request, { configPath, serversPath }) }
}

test('parses one SSH destination and only inert connection flags, including quoted Windows keys', () => {
  assert.deepEqual(parseServerCommand('DevEnv950'), { existingAlias: 'DevEnv950' })
  assert.deepEqual(parseServerCommand('ssh user@EXAMPLE.COM -p 2222'), { hostName: 'example.com', user: 'user', port: 2222 })
  assert.deepEqual(parseServerCommand('ssh.exe -l user -p2222 example.com'), { hostName: 'example.com', user: 'user', port: 2222 })
  assert.deepEqual(parseServerCommand('ssh -i "C:\\Users\\测试 用户\\.ssh\\id_ed25519" root@[2001:db8::1]'), { hostName: '2001:db8::1', user: 'root', identityFile: 'C:/Users/测试 用户/.ssh/id_ed25519' })
  assert.deepEqual(parseServerCommand("ssh -i '~/.ssh/my key' user@host"), { hostName: 'host', user: 'user', identityFile: '~/.ssh/my key' })
})

test('structured SSH form supports a known jump alias and rejects injection without changing existing config', t => {
  const f = fixture(t)
  const result = f.add({ connection: { hostName: '10.0.1.2', user: 'developer', port: '2222', proxyJump: 'DevEnv950' }, label: '开发机' })
  assert.equal(result.label, '开发机'); assert.match(readFileSync(f.configPath, 'utf8'), /ProxyJump DevEnv950/)
  const before = readFileSync(f.configPath)
  for (const connection of [{ hostName: 'x\nHost evil', user: 'root' }, { hostName: 'host', user: 'root', proxyJump: 'unknown' }, { hostName: {}, user: 'root' }, { hostName: 'host', port: '-oProxyCommand=bad' }]) assert.throws(() => f.add({ connection }))
  assert.deepEqual(readFileSync(f.configPath), before)
})

for (const command of [
  '', 'ssh', 'alias -p 22', 'ssh host whoami', 'ssh host;whoami', 'ssh host && whoami', 'ssh host | sh',
  'ssh $(whoami)', 'ssh `whoami`', 'ssh host\nHost injected', 'ssh host\rHost injected', 'ssh host\0',
  'ssh -oProxyCommand=whoami host', 'ssh -F other-config host', 'ssh -J user@jump host', 'ssh -L123:host:22 host',
  'ssh -p 0 host', 'ssh -p65536 host', 'ssh -pabc host', 'ssh -p22 -p23 host', 'ssh -l x y@host',
  'ssh "bad user"@host', 'ssh x@@host', 'ssh -i "x\nUser injected" host', 'ssh -i relative/key host',
  'ssh -i ~/.ssh/%h host', 'ssh host #comment', 'ssh "unfinished',
]) test(`rejects unsafe or ambiguous input ${JSON.stringify(command)}`, () => {
  assert.throws(() => parseServerCommand(command), error => error instanceof ServerInputError && error.status === 400)
})

test('appends a new Host without changing existing bytes, inventory metadata, or another connection', t => {
  const f = fixture(t)
  const added = f.add({ command: 'ssh user@new.example -p 2222 -i "C:\\keys\\my key"', label: '新服务器' })
  assert.match(added.alias, /^cannbot-[a-f0-9]{16}$/)
  assert.equal(added.label, '新服务器')
  const after = readFileSync(f.configPath)
  assert.deepEqual(after.subarray(0, f.before.length), f.before)
  assert.match(after.toString(), new RegExp(`Host ${added.alias}\\r\\n  HostName new.example\\r\\n  User user\\r\\n  Port 2222`))
  assert.ok(after.toString().includes('IdentityFile "C:/keys/my key"'))
  const inventory = JSON.parse(readFileSync(f.serversPath, 'utf8'))
  assert.deepEqual(inventory.custom, f.stored.custom)
  assert.deepEqual(inventory.servers[0], f.stored.servers[0])
  assert.equal(inventory.servers.length, 2)
  assert.ok(listAliases(f.configPath).aliases.includes(added.alias))
  assert.equal(existsSync(f.configPath + '.cannbot-add.lock'), false)
})

test('adds an included alias without editing config or include and keeps duplicates idempotent', t => {
  const f = fixture(t, 'Include hosts/*.conf\nHost DevEnv950 alternate-dev\n  HostName 10.0.0.20\n')
  mkdirSync(join(dirname(f.configPath), 'hosts'))
  const included = join(dirname(f.configPath), 'hosts', 'extra.conf'), text = 'Host Included\n  HostName 10.0.0.21\n  ProxyCommand trusted-existing-command\n'
  writeFileSync(included, text)
  const added = f.add({ command: 'ssh included', label: '包含的主机' })
  assert.deepEqual(added, { alias: 'Included', label: '包含的主机' })
  const inventory = readFileSync(f.serversPath)
  assert.deepEqual(f.add({ command: 'Included', label: '不要覆盖' }), added)
  assert.deepEqual(readFileSync(f.serversPath), inventory)
  assert.deepEqual(readFileSync(f.configPath), f.before)
  assert.equal(readFileSync(included, 'utf8'), text)
  assert.deepEqual(f.add({ command: 'alternate-dev' }), { alias: 'alternate-dev', label: 'alternate-dev' })
})

test('identical new commands reuse their complete managed Host block and inventory entry', t => {
  const f = fixture(t), first = f.add({ command: 'ssh user@new.example -p 22' })
  const config = readFileSync(f.configPath), inventory = readFileSync(f.serversPath)
  assert.deepEqual(f.add({ command: 'ssh user@new.example -p 22', label: 'do not rename on add' }), first)
  assert.deepEqual(readFileSync(f.configPath), config)
  assert.deepEqual(readFileSync(f.serversPath), inventory)
})

test('new host labels use the destination rather than the internal alias and bracket IPv6 addresses', t => {
  const f = fixture(t)
  assert.equal(f.add({ command: 'ssh user@new.example -p 22' }).label, 'user@new.example')
  assert.equal(f.add({ command: 'ssh user@new.example -p 2222' }).label, 'user@new.example:2222')
  assert.equal(f.add({ command: 'ssh root@[2001:db8::1] -p 2222' }).label, 'root@[2001:db8::1]:2222')
  assert.equal(f.add({ command: 'ssh [2001:db8::2]' }).label, '[2001:db8::2]')
  assert.equal(f.add({ command: 'DevEnv950' }).label, '已有服务器')
})

test('never reuses or overwrites a managed alias whose connection was edited by the user', t => {
  const f = fixture(t), first = f.add({ command: 'ssh user@new.example' })
  const edited = readFileSync(f.configPath, 'utf8').replace('HostName new.example', 'HostName changed.example')
  writeFileSync(f.configPath, edited)
  const second = f.add({ command: 'ssh user@new.example' })
  assert.notEqual(first.alias, second.alias)
  assert.equal(readFileSync(f.configPath, 'utf8').slice(0, edited.length), edited)
  assert.equal(listAliases(f.configPath).resolved.find(row => row.alias === second.alias).hostName, 'new.example')
})

test('does not override an existing alias with destination arguments', t => {
  const f = fixture(t)
  for (const command of ['ssh other@DevEnv950', 'ssh DevEnv950 -p 2222', 'ssh DevEnv950 -i ~/.ssh/key']) {
    assert.throws(() => f.add({ command }), error => error.status === 409)
  }
  assert.deepEqual(readFileSync(f.configPath), f.before)
  assert.deepEqual(JSON.parse(readFileSync(f.serversPath, 'utf8')), f.stored)
})

for (const rule of ['User another', 'HostName unexpected.example', 'Port 2022', 'IdentityFile ~/.ssh/other']) {
  test(`refuses earlier matching wildcard ${rule} instead of overriding it`, t => {
    const f = fixture(t, `Host *\n  ${rule}\nHost DevEnv950\n  HostName 10.0.0.20\n`)
    assert.throws(() => f.add({ command: 'ssh user@new.example -p22 -i ~/.ssh/key' }), error => error.status === 409)
    assert.deepEqual(readFileSync(f.configPath), f.before)
    assert.deepEqual(JSON.parse(readFileSync(f.serversPath, 'utf8')), f.stored)
  })
}

test('inherits unrelated defaults, respects negated patterns, and rejects matching included overrides', t => {
  const f = fixture(t, 'Host * !cannbot-*\n  User other\nHost *\n  ServerAliveInterval 30\nInclude extra.conf\n')
  const included = join(dirname(f.configPath), 'extra.conf')
  writeFileSync(included, 'Host unrelated-*\n  User another\n')
  f.add({ command: 'ssh user@new.example -p22' })
  writeFileSync(included, 'Host cannbot-*\n  User another\n')
  const before = readFileSync(f.configPath)
  assert.throws(() => f.add({ command: 'ssh user@other.example' }), error => error.status === 409)
  assert.deepEqual(readFileSync(f.configPath), before)
})

test('conditional config can be referenced by known alias but is never extended by guessing Match rules', t => {
  const f = fixture(t, 'Host DevEnv950\n  HostName 10.0.0.20\nMatch exec "trusted-existing-rule"\n  User someuser\n')
  assert.equal(f.add({ command: 'DevEnv950' }).alias, 'DevEnv950')
  assert.throws(() => f.add({ command: 'ssh user@new.example' }), error => error.status === 409)
  assert.deepEqual(readFileSync(f.configPath), f.before)
})

test('corrupt inventory, active locks and invalid labels do not erase data or append config', t => {
  const f = fixture(t)
  assert.throws(() => f.add({ command: 'missing-alias' }), error => error.status === 400)
  assert.throws(() => f.add({ command: 'ssh user@host', label: 'two\nlines' }), error => error.status === 400)
  writeFileSync(f.serversPath, '{broken')
  assert.throws(() => f.add({ command: 'ssh user@host' }), error => error.status === 409)
  assert.equal(readFileSync(f.serversPath, 'utf8'), '{broken')
  writeFileSync(f.configPath + '.cannbot-add.lock', 'another writer')
  assert.throws(() => f.add({ command: 'ssh user@host' }), error => error.status === 409)
  assert.equal(readFileSync(f.configPath + '.cannbot-add.lock', 'utf8'), 'another writer')
  assert.deepEqual(readFileSync(f.configPath), f.before)
})

test('new files have private permissions on POSIX and saving never reads an identity file', t => {
  const f = fixture(t)
  const configPath = join(f.root, 'fresh-ssh', 'config'), serversPath = join(f.root, 'fresh-data', 'servers.json')
  const added = addServerRecord({ command: 'ssh -i ~/.ssh/key-that-does-not-exist user@host' }, { configPath, serversPath })
  assert.equal(added.label, 'user@host')
  if (process.platform !== 'win32') {
    assert.equal(statSync(configPath).mode & 0o777, 0o600)
    assert.equal(statSync(serversPath).mode & 0o777, 0o600)
  }
})

test('production manager and authenticated POST add without running SSH or changing connection state', async t => {
  const f = fixture(t), statePath = join(f.root, 'state.json'), state = '{"version":1,"connections":{"DevEnv950":{"localPort":17633,"token":"fake-private-token"}}}'
  writeFileSync(statePath, state)
  const manager = createManager({ serversFile: f.serversPath, stateFile: statePath, sshConfig: f.configPath,
    exec() { throw Error('saving must not execute SSH') }, tunnel: { status: () => null } })
  const registered = []
  registerRoutes({ connection: { fetch: { register(route) { registered.push(route) } } } }, createRouter({ manager }))
  const route = registered.find(row => row.path === `${ROUTE}/servers`)
  assert.deepEqual(route.methods, ['GET', 'POST'])
  const response = await route.fetch(new Request('http://dsh.invalid' + route.path, { method: 'POST', body: JSON.stringify({ command: 'ssh user@new.example -p2222', label: '新服务器' }) }))
  const result = await response.json()
  assert.equal(response.status, 200)
  assert.equal(result.ok, true)
  assert.deepEqual(Object.keys(result.server).sort(), ['alias', 'connected', 'id', 'label'])
  assert.equal(result.server.connected, false)
  assert.ok(manager.listServers().some(row => row.id === result.server.id && row.user === 'user' && row.port === 2222))
  assert.equal(readFileSync(statePath, 'utf8'), state)
  assert.ok(!JSON.stringify(result).includes('fake-private-token'))
  const bad = await route.fetch(new Request('http://dsh.invalid' + route.path, { method: 'POST', body: JSON.stringify({ command: 'ssh host; private-secret' }) }))
  assert.equal(bad.status, 400)
  assert.ok(!(await bad.text()).includes('private-secret'))
  const malformed = await route.fetch(new Request('http://dsh.invalid' + route.path, { method: 'POST', body: '{' }))
  assert.equal(malformed.status, 400)
  const huge = await route.fetch(new Request('http://dsh.invalid' + route.path, { method: 'POST', body: ' '.repeat(8193) }))
  assert.equal(huge.status, 400)
  assert.throws(() => addServerRecord({ connection: { hostName: 'server.example', user: 'alice', port: 0 } }, f), /请输入/)
})
