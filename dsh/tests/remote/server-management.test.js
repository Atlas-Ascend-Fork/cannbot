// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { test } from 'node:test'
import assert from 'node:assert/strict'
import { mkdtempSync, mkdirSync, readFileSync, writeFileSync, existsSync, rmSync, readdirSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { tmpdir } from 'node:os'
import { spawn } from 'node:child_process'
import { reorderServers, removeServerRecord } from '../../src/remote/server-management.js'
import { addServerRecord, ServerInputError } from '../../src/remote/add-server.js'
import { setServerLabel } from '../../src/remote/server-label.js'
import { createManager } from '../../src/remote/manager.js'
import { createRouter, ROUTE } from '../../src/remote/routes.js'

function fixture(t, deps = {}) {
  const root = mkdtempSync(join(tmpdir(), 'cannbot-servers-'))
  t.after(() => { assert.equal(dirname(resolve(root)), resolve(tmpdir())); rmSync(root, { recursive: true, force: true }) })
  const configPath = join(root, 'ssh', 'config'), serversPath = join(root, 'data', 'servers.json'), stateFile = join(root, 'state.json')
  mkdirSync(dirname(configPath)); mkdirSync(dirname(serversPath))
  const config = 'Host DevEnv950\r\n  HostName host.example\r\nInclude more.conf\r\n'
  writeFileSync(configPath, config)
  const includedPath = join(dirname(configPath), 'more.conf'), included = 'Host Imported Jump\n  HostName other.example\n'
  writeFileSync(includedPath, included)
  const inventory = { version: 1, metadata: { keep: ['all', 'fields'] }, servers: [
    { alias: 'DevEnv950', label: '旧备注', group: 'team', remotePort: 17777, custom: { keep: true } },
    { alias: 'inventory-only', label: '仅列表', note: 'keep' },
  ] }
  writeFileSync(serversPath, JSON.stringify(inventory))
  const state = JSON.stringify({ version: 1, connections: { DevEnv950: { token: 'fake-state-grant', url: 'http://127.0.0.1:17777/?token=fake-state-grant' }, other: { localPort: 17778 } } })
  writeFileSync(stateFile, state)
  const active = new Set(['DevEnv950']), stopped = [], calls = []
  const tunnel = { status: id => active.has(id) ? { localPort: 17777 } : null,
    stop(id) { stopped.push(id); return active.delete(id) },
    async ensure(input) { calls.push('tunnel'); active.add(input.id); return { started: true, url: 'http://127.0.0.1:17777/', ...input } },
  }
  const exec = async (_command, args) => {
    const line = args.join(' '); calls.push(line)
    return { code: 0, stderr: '', stdout: line.includes('CANNBOT_SSH_OK') ? 'CANNBOT_SSH_OK' : line.includes('CANNBOT_STATE_DSH') ? 'CANNBOT_STATE_DSH=0.2.2-rc.1\nCANNBOT_STATE_PLUGIN=1.0.0-alpha.1' : 'CANNBOT_OK=1\nCANNBOT_REMOTE_PORT=17633' }
  }
  const options = { sshConfig: configPath, serversFile: serversPath, stateFile, exec, tunnel, config: { syncLogin: false }, deployPackage: async () => { calls.push('deploy'); return {} }, ...deps }
  const manager = createManager(options)
  return { root, configPath, config, includedPath, included, serversPath, inventory, stateFile, state, active, stopped, calls, tunnel, exec, manager, options,
    read: () => JSON.parse(readFileSync(serversPath, 'utf8')), ids: () => manager.listServers().map(server => server.id) }
}

test('orders shared and SSH-imported rows persistently without touching config, connection state or metadata', t => {
  const f = fixture(t), beforeServers = f.read().servers
  const result = f.manager.reorderServers({ ids: ['Jump', 'devenv950'] })
  assert.deepEqual(result.ids.slice(0, 2), ['Jump', 'DevEnv950'])
  assert.deepEqual(f.ids(), result.ids)
  assert.deepEqual(createManager(f.options).listServers().map(server => server.id), result.ids)
  assert.deepEqual(f.read().servers, beforeServers); assert.deepEqual(f.read().metadata, f.inventory.metadata)
  assert.equal(readFileSync(f.configPath, 'utf8'), f.config); assert.equal(readFileSync(f.includedPath, 'utf8'), f.included)
  assert.equal(readFileSync(f.stateFile, 'utf8'), f.state); assert.deepEqual(f.calls, []); assert.deepEqual(f.stopped, [])
  // A concurrently discovered alias omitted by an older client is retained.
  writeFileSync(f.includedPath, f.included + 'Host NewlyAdded\n HostName new.example\n')
  const next = f.manager.reorderServers({ ids: result.ids })
  assert.deepEqual(next.ids, [...result.ids, 'NewlyAdded'])
})

test('rejects malformed, duplicate and stale orders without partial writes or revealing unknown IDs', t => {
  const f = fixture(t), before = readFileSync(f.serversPath)
  for (const input of [null, [], {}, { ids: 'DevEnv950' }, { ids: [1] }, { ids: [''] }, { ids: ['a\nb'] }, { ids: ['DevEnv950', 'devenv950'] }, { ids: Array(2001).fill('A') }]) {
    assert.throws(() => f.manager.reorderServers(input), error => error instanceof ServerInputError && error.status === 400)
  }
  assert.throws(() => f.manager.reorderServers({ ids: ['private-host-unknown'] }), error => error.status === 409 && /刷新列表后重新排序/.test(error.message) && !error.message.includes('private-host'))
  assert.deepEqual(readFileSync(f.serversPath), before)
  assert.deepEqual(f.calls, []); assert.deepEqual(f.stopped, [])
})

test('removing an imported alias keeps its tombstone across refreshes and adding the alias restores it last', t => {
  const f = fixture(t)
  f.manager.reorderServers({ ids: ['Imported', 'Jump'] })
  assert.deepEqual(f.manager.removeServer({ id: 'imported' }), { id: 'Imported', stopped: false })
  assert.ok(!f.ids().includes('Imported'))
  assert.ok(!createManager(f.options).listServers().some(server => server.id === 'Imported'))
  assert.deepEqual(f.read().hiddenAliases, ['imported'])
  assert.throws(() => f.manager.reorderServers({ ids: ['Imported'] }), error => error.status === 409)
  assert.throws(() => setServerLabel({ id: 'Imported', label: 'stale' }, f), error => error.status === 404)
  const before = f.ids()
  assert.equal(f.manager.addServer({ command: 'Imported' }).id, 'Imported')
  assert.deepEqual(f.ids(), [...before, 'Imported'])
  assert.deepEqual(f.read().hiddenAliases, [])
  assert.equal(readFileSync(f.configPath, 'utf8'), f.config); assert.equal(readFileSync(f.includedPath, 'utf8'), f.included)
  assert.deepEqual(f.calls, [])
})

test('removing a connected row stops only its local tunnel and retains its metadata and remote state', t => {
  const f = fixture(t), before = f.read()
  assert.deepEqual(f.manager.removeServer({ id: 'devenv950' }), { id: 'DevEnv950', stopped: true })
  assert.deepEqual(f.stopped, ['DevEnv950']); assert.deepEqual(f.calls, [])
  assert.equal(f.manager.getConnection('DevEnv950'), null)
  assert.deepEqual(f.read().servers, before.servers); assert.deepEqual(f.read().metadata, before.metadata)
  assert.equal(readFileSync(f.stateFile, 'utf8'), f.state)
  assert.equal(readFileSync(f.configPath, 'utf8'), f.config)
  assert.equal(f.manager.removeServer({ id: 'DevEnv950' }).stopped, false)
  const restored = f.manager.addServer({ command: 'DevEnv950', label: 'do not replace old metadata' })
  assert.equal(restored.label, '旧备注'); assert.equal(restored.connected, false)
  assert.deepEqual(f.read().servers, before.servers)
})

test('inventory-only aliases can be removed and explicitly restored without creating SSH config', t => {
  const f = fixture(t)
  f.manager.removeServer({ id: 'inventory-only' })
  assert.equal(f.manager.addServer({ command: 'inventory-only' }).label, '仅列表')
  assert.equal(f.ids().at(-1), 'inventory-only')
  assert.equal(readFileSync(f.configPath, 'utf8'), f.config)
})

test('failed validation, active locks and corrupt metadata never disconnect or hide rows', t => {
  const f = fixture(t), before = readFileSync(f.serversPath)
  assert.throws(() => f.manager.removeServer({ id: 'unknown' }), error => error.status === 404)
  assert.throws(() => f.manager.removeServer({ id: [] }), error => error.status === 400)
  writeFileSync(f.configPath + '.cannbot-add.lock', 'other writer')
  assert.throws(() => f.manager.removeServer({ id: 'DevEnv950' }), error => error.status === 409)
  assert.throws(() => f.manager.reorderServers({ ids: [] }), error => error.status === 409)
  assert.equal(readFileSync(f.configPath + '.cannbot-add.lock', 'utf8'), 'other writer')
  rmSync(f.configPath + '.cannbot-add.lock')
  assert.deepEqual(readFileSync(f.serversPath), before)
  writeFileSync(f.serversPath, JSON.stringify({ ...f.inventory, hiddenAliases: [5] }))
  assert.throws(() => f.manager.removeServer({ id: 'DevEnv950' }), error => error.status === 409)
  assert.deepEqual(f.stopped, []); assert.deepEqual(f.calls, [])
})

test('a failed local tunnel stop leaves inventory visible and removes unpublished temporary files', t => {
  const f = fixture(t), before = readFileSync(f.serversPath)
  f.tunnel.stop = () => { throw Error('private process detail') }
  assert.throws(() => f.manager.removeServer({ id: 'DevEnv950' }), error => error.status === 500 && !error.message.includes('private'))
  assert.deepEqual(readFileSync(f.serversPath), before); assert.ok(f.ids().includes('DevEnv950'))
  assert.deepEqual(readdirSync(dirname(f.serversPath)), ['servers.json'])
  assert.equal(existsSync(f.configPath + '.cannbot-add.lock'), false)
})

test('removal during a pending probe cancels later deployment even if the alias is added again', async t => {
  const probe = Promise.withResolvers(), f = fixture(t)
  f.options.exec = () => probe.promise
  const manager = createManager(f.options), pending = manager.connect('DevEnv950')
  const rejected = assert.rejects(pending, error => error.status === 409 && /已移除/.test(error.message))
  manager.removeServer({ id: 'DevEnv950' })
  manager.addServer({ command: 'DevEnv950' })
  await assert.rejects(manager.connect('DevEnv950'), error => error.status === 409)
  probe.resolve({ code: 0, stdout: 'CANNBOT_SSH_OK', stderr: '' })
  await rejected
  assert.deepEqual(f.calls, []); assert.equal(f.active.has('DevEnv950'), false)
  assert.equal(readFileSync(f.stateFile, 'utf8'), f.state)
})

test('a non-cancellable in-flight tunnel rejects removal before hiding and succeeds after settling', async t => {
  const ready = Promise.withResolvers(), entered = Promise.withResolvers(), f = fixture(t)
  f.tunnel.ensure = async input => { entered.resolve(); await ready.promise; f.active.add(input.id); return { started: true, url: 'http://127.0.0.1:17777/' } }
  const pending = f.manager.connect('DevEnv950')
  await entered.promise
  const before = readFileSync(f.serversPath)
  assert.throws(() => f.manager.removeServer({ id: 'DevEnv950' }), error => error.status === 409 && /建立隧道/.test(error.message))
  assert.deepEqual(readFileSync(f.serversPath), before); assert.deepEqual(f.stopped, [])
  ready.resolve(); assert.equal((await pending).ok, true)
  assert.equal(f.manager.removeServer({ id: 'DevEnv950' }).stopped, true)
  assert.equal(f.active.has('DevEnv950'), false); assert.ok(!f.ids().includes('DevEnv950'))
})

test('authenticated order/remove routes return safe summaries and method/body errors without executing SSH', async t => {
  const f = fixture(t), handler = createRouter({ manager: f.manager })
  const post = (path, body) => handler(new Request(`http://dsh.invalid${ROUTE}/servers/${path}`, { method: 'POST', body: JSON.stringify(body) }))
  const sorted = await post('order', { ids: ['Jump'] })
  assert.equal(sorted.status, 200); assert.deepEqual(await sorted.json(), { ok: true, ids: f.ids() })
  const removed = await post('remove', { id: 'DevEnv950' })
  assert.equal(removed.status, 200); assert.deepEqual(await removed.json(), { ok: true, id: 'DevEnv950', stopped: true })
  assert.equal((await post('order', { ids: ['DevEnv950'] })).status, 409)
  assert.equal((await post('remove', { id: 'missing' })).status, 404)
  assert.equal((await handler(new Request(`http://dsh.invalid${ROUTE}/servers/remove`))).status, 404)
  assert.equal((await handler(new Request(`http://dsh.invalid${ROUTE}/servers/order`, { method: 'POST', body: '{' }))).status, 400)
  assert.deepEqual(f.calls, [])
})

test('concurrent process add, label, reorder and remove transactions preserve all successful writes', { timeout: 20000 }, async t => {
  const f = fixture(t)
  const source = `import {addServerRecord} from ${JSON.stringify(new URL('../../src/remote/add-server.js', import.meta.url).href)};
    import {setServerLabel} from ${JSON.stringify(new URL('../../src/remote/server-label.js', import.meta.url).href)};
    import {reorderServers,removeServerRecord} from ${JSON.stringify(new URL('../../src/remote/server-management.js', import.meta.url).href)};
    const [configPath,serversPath,index]=process.argv.slice(1);const paths={configPath,serversPath};
    async function retry(fn){for(let n=0;n<300;n++){try{return fn()}catch(e){if(e.status!==409)throw e;await new Promise(r=>setTimeout(r,5))}}throw Error('timeout')}
    for(let n=0;n<4;n++){const row=await retry(()=>addServerRecord({command:'ssh user@parallel-'+index+'-'+n+'.example'},paths));await retry(()=>setServerLabel({id:row.alias,label:'worker '+index+' '+n},paths));await retry(()=>reorderServers({ids:[]},paths));await retry(()=>removeServerRecord({id:row.alias},paths))}`
  await Promise.all([0, 1, 2].map(index => new Promise((resolve, reject) => {
    const child = spawn(process.execPath, ['--input-type=module', '-e', source, f.configPath, f.serversPath, String(index)], { stdio: ['ignore', 'ignore', 'pipe'] })
    let stderr = ''; child.stderr.on('data', bytes => { stderr += bytes })
    child.on('error', reject); child.on('close', code => code === 0 ? resolve() : reject(Error(stderr || `exit ${code}`)))
  })))
  const saved = f.read()
  assert.equal(saved.servers.length, 14); assert.equal(saved.hiddenAliases.length, 12)
  assert.deepEqual(saved.servers.slice(0, 2), f.inventory.servers); assert.deepEqual(saved.metadata, f.inventory.metadata)
  assert.equal(new Set(saved.servers.slice(2).map(server => server.label)).size, 12)
  assert.deepEqual(new Set(f.ids()), new Set(['DevEnv950', 'inventory-only', 'Imported', 'Jump']))
})
