// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { test } from 'node:test'
import assert from 'node:assert/strict'
import { mkdtempSync, mkdirSync, readFileSync, writeFileSync, existsSync, rmSync, readdirSync, statSync } from 'node:fs'
import { join, dirname, resolve } from 'node:path'
import { tmpdir } from 'node:os'
import { spawn } from 'node:child_process'
import { setServerLabel } from '../../src/remote/server-label.js'
import { addServerRecord, ServerInputError } from '../../src/remote/add-server.js'
import { createManager } from '../../src/remote/manager.js'
import { createRouter, registerRoutes, ROUTE } from '../../src/remote/routes.js'

function fixture(t) {
  const root = mkdtempSync(join(tmpdir(), 'cannbot-label-'))
  t.after(() => { assert.equal(dirname(resolve(root)), resolve(tmpdir())); rmSync(root, { recursive: true, force: true }) })
  const configPath = join(root, 'ssh', 'config'), serversPath = join(root, 'data', 'servers.json')
  mkdirSync(dirname(configPath)); mkdirSync(dirname(serversPath))
  const config = 'Host DevEnv950\r\n  HostName existing.example\r\n  User olduser\r\nInclude extra.conf\r\n'
  writeFileSync(configPath, config)
  writeFileSync(join(dirname(configPath), 'extra.conf'), 'Host Included alternate\n  HostName included.example\n')
  const inventory = { version: 1, custom: { retained: true }, servers: [
    { alias: 'DevEnv950', label: '旧备注', group: 'team', remotePort: 17633, note: '独立说明', arbitrary: { nested: ['keep'] } },
    { alias: 'inventory-only', label: '未配置服务器', unknown: 'keep' },
  ] }
  writeFileSync(serversPath, JSON.stringify(inventory))
  return { root, configPath, serversPath, config, inventory, set: request => setServerLabel(request, { configPath, serversPath }) }
}

test('changes only the display label, preserving metadata, SSH config and alias identity', t => {
  const f = fixture(t)
  assert.deepEqual(f.set({ id: 'DevEnv950', label: '  训练服务器  ' }), { alias: 'DevEnv950', label: '训练服务器' })
  const expected = structuredClone(f.inventory); expected.servers[0].label = '训练服务器'
  assert.deepEqual(JSON.parse(readFileSync(f.serversPath, 'utf8')), expected)
  assert.equal(readFileSync(f.configPath, 'utf8'), f.config)
  assert.equal(existsSync(f.configPath + '.cannbot-add.lock'), false)
  assert.deepEqual(readdirSync(dirname(f.serversPath)), ['servers.json'])
})

test('clearing a remark removes only label and falls back to the canonical existing alias', t => {
  const f = fixture(t)
  assert.deepEqual(f.set({ id: 'devenv950', label: '   ' }), { alias: 'DevEnv950', label: 'DevEnv950' })
  const expected = structuredClone(f.inventory); delete expected.servers[0].label
  assert.deepEqual(JSON.parse(readFileSync(f.serversPath, 'utf8')), expected)
  const before = readFileSync(f.serversPath)
  f.set({ id: 'DevEnv950', label: '' })
  assert.deepEqual(readFileSync(f.serversPath), before)
  assert.equal(f.set({ id: 'inventory-only', label: '离线备注' }).label, '离线备注')
})

test('persists a config-only included alias without editing its SSH files', t => {
  const f = fixture(t), includedPath = join(dirname(f.configPath), 'extra.conf'), included = readFileSync(includedPath)
  assert.deepEqual(f.set({ id: 'included', label: '发现的服务器' }), { alias: 'Included', label: '发现的服务器' })
  const value = JSON.parse(readFileSync(f.serversPath, 'utf8'))
  assert.deepEqual(value.servers.slice(0, 2), f.inventory.servers)
  assert.deepEqual(value.servers[2], { alias: 'Included', label: '发现的服务器' })
  assert.deepEqual(value.custom, f.inventory.custom)
  assert.deepEqual(readFileSync(includedPath), included)
  assert.equal(readFileSync(f.configPath, 'utf8'), f.config)
})

test('empty remark for a config-only alias is a no-op and new inventory is created privately when needed', t => {
  const f = fixture(t)
  rmSync(f.serversPath)
  assert.deepEqual(f.set({ id: 'Included', label: '' }), { alias: 'Included', label: 'Included' })
  assert.equal(existsSync(f.serversPath), false)
  f.set({ id: 'Included', label: '备注' })
  assert.deepEqual(JSON.parse(readFileSync(f.serversPath, 'utf8')), { version: 1, servers: [{ alias: 'Included', label: '备注' }] })
  if (process.platform !== 'win32') assert.equal(statSync(f.serversPath).mode & 0o777, 0o600)
})

test('keeps duplicate legacy records and their metadata while updating their shared remark consistently', t => {
  const f = fixture(t)
  f.inventory.servers.push({ alias: 'devenv950', label: 'later label', extra: 'keep last' })
  writeFileSync(f.serversPath, '\uFEFF' + JSON.stringify(f.inventory))
  assert.deepEqual(f.set({ id: 'DevEnv950', label: '统一备注' }), { alias: 'devenv950', label: '统一备注' })
  const next = JSON.parse(readFileSync(f.serversPath, 'utf8'))
  assert.equal(next.servers.length, 3)
  assert.equal(next.servers[0].label, '统一备注')
  assert.equal(next.servers[2].label, '统一备注')
  assert.equal(next.servers[2].extra, 'keep last')
})

test('rejects unknown ids and invalid labels without mutating existing data', t => {
  const f = fixture(t), before = readFileSync(f.serversPath)
  for (const request of [null, [], {}, { id: '', label: 'x' }, { id: 1, label: 'x' }, { id: 'DevEnv950' },
    { id: 'DevEnv950', label: 7 }, { id: 'DevEnv950', label: 'x'.repeat(121) }, { id: 'DevEnv950', label: 'a\nb' },
    { id: 'DevEnv950\0', label: 'x' }]) {
    assert.throws(() => f.set(request), error => error instanceof ServerInputError && error.status === 400)
  }
  assert.throws(() => f.set({ id: 'unknown', label: 'x' }), error => error.status === 404)
  assert.deepEqual(readFileSync(f.serversPath), before)
  assert.equal(readFileSync(f.configPath, 'utf8'), f.config)
  f.set({ id: 'DevEnv950', label: 'x'.repeat(120) })
})

test('corrupt inventory and another writer lock cause a conflict without losing records', t => {
  const f = fixture(t)
  writeFileSync(f.serversPath, '{broken')
  assert.throws(() => f.set({ id: 'DevEnv950', label: 'x' }), error => error.status === 409)
  assert.equal(readFileSync(f.serversPath, 'utf8'), '{broken')
  writeFileSync(f.serversPath, JSON.stringify(f.inventory))
  writeFileSync(f.configPath + '.cannbot-add.lock', 'other writer')
  assert.throws(() => f.set({ id: 'DevEnv950', label: 'x' }), error => error.status === 409)
  assert.throws(() => addServerRecord({ command: 'ssh user@new.example' }, f), error => error.status === 409)
  assert.equal(readFileSync(f.configPath + '.cannbot-add.lock', 'utf8'), 'other writer')
  assert.deepEqual(JSON.parse(readFileSync(f.serversPath, 'utf8')), f.inventory)
})

test('concurrent separate-process adds and remarks preserve all successful writes', { timeout: 20000 }, async t => {
  const f = fixture(t)
  const source = `import {addServerRecord} from ${JSON.stringify(new URL('../../src/remote/add-server.js', import.meta.url).href)};
    import {setServerLabel} from ${JSON.stringify(new URL('../../src/remote/server-label.js', import.meta.url).href)};
    const [configPath,serversPath,index]=process.argv.slice(1); const paths={configPath,serversPath};
    async function retry(run){for(let i=0;i<300;i++){try{return run()}catch(error){if(error.status!==409)throw error;await new Promise(r=>setTimeout(r,5))}}throw Error('lock timeout')}
    for(let n=0;n<5;n++){const entry=await retry(()=>addServerRecord({command:'ssh user@server-'+index+'-'+n+'.example'},paths));await retry(()=>setServerLabel({id:entry.alias,label:'worker '+index+' '+n},paths))}`
  await Promise.all([0, 1, 2].map(index => new Promise((resolve, reject) => {
    const child = spawn(process.execPath, ['--input-type=module', '-e', source, f.configPath, f.serversPath, String(index)], { stdio: ['ignore', 'ignore', 'pipe'] })
    let stderr = ''; child.stderr.on('data', bytes => { stderr += bytes })
    child.on('error', reject); child.on('close', code => code === 0 ? resolve() : reject(Error(stderr || `exit ${code}`)))
  })))
  const saved = JSON.parse(readFileSync(f.serversPath, 'utf8'))
  assert.equal(saved.servers.length, 17)
  assert.deepEqual(saved.servers.slice(0, 2), f.inventory.servers)
  assert.deepEqual(saved.custom, f.inventory.custom)
  assert.equal(new Set(saved.servers.slice(2).map(server => server.label)).size, 15)
  assert.ok(saved.servers.slice(2).every(server => /^worker [0-2] [0-4]$/.test(server.label)))
})

test('authenticated label API updates the list without SSH, connection-state writes or token responses', async t => {
  const f = fixture(t), statePath = join(f.root, 'state.json'), state = '{"version":1,"connections":{"DevEnv950":{"token":"fake-private-token"}}}'
  writeFileSync(statePath, state)
  const manager = createManager({ serversFile: f.serversPath, stateFile: statePath, sshConfig: f.configPath,
    exec() { throw Error('remark must not run SSH') }, tunnel: { status: id => id === 'DevEnv950' ? { connected: true } : null } })
  const routes = []
  registerRoutes({ connection: { fetch: { register: route => routes.push(route) } } }, createRouter({ manager }))
  const route = routes.find(route => route.path === `${ROUTE}/servers/label`)
  assert.deepEqual(route.methods, ['POST'])
  const post = body => route.fetch(new Request(`http://dsh.invalid${route.path}`, { method: 'POST', body: JSON.stringify(body) }))
  const response = await post({ id: 'DevEnv950', label: '生产训练机' })
  assert.equal(response.status, 200)
  assert.deepEqual(await response.json(), { ok: true, server: { id: 'DevEnv950', alias: 'DevEnv950', label: '生产训练机', connected: true } })
  assert.equal(manager.listServers().find(row => row.id === 'DevEnv950').label, '生产训练机')
  assert.equal((await post({ id: 'missing', label: 'x' })).status, 404)
  assert.equal((await post({ id: 'DevEnv950', label: [] })).status, 400)
  assert.equal((await route.fetch(new Request(`http://dsh.invalid${route.path}`, { method: 'POST', body: '{' }))).status, 400)
  assert.equal((await route.fetch(new Request(`http://dsh.invalid${route.path}`))).status, 404)
  assert.equal(readFileSync(statePath, 'utf8'), state)
  assert.equal(readFileSync(f.configPath, 'utf8'), f.config)
})
