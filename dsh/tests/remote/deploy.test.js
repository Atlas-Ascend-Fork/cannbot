// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { test } from 'node:test'
import assert from 'node:assert/strict'
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { gunzipSync } from 'node:zlib'
import { spawnSync } from 'node:child_process'
import { createArtifact } from '../../src/remote/artifact.js'
import { deployCurrentPackage } from '../../src/remote/deploy.js'
import { processIdentity, stopOwned, existingWeb, installCurrentPackage } from '../../remote/deploy-package.mjs'

function source(t) {
  const root = mkdtempSync(join(tmpdir(), 'cannbot-artifact-'))
  t.after(() => rmSync(root, { recursive: true, force: true }))
  writeFileSync(join(root, 'package.json'), JSON.stringify({ name: '@cannbot-plugin/cannbot-dsh', version: '1.0.0-alpha.1', files: ['lib', 'remote'] }))
  for (const file of ['lib/index.js', 'lib/client.js', 'remote/deploy-package.mjs']) { mkdirSync(join(root, file.split('/')[0]), { recursive: true }); writeFileSync(join(root, file), 'current source') }
  writeFileSync(join(root, '.credentials'), 'fixture-secret-excluded')
  return root
}

test('release archive is deterministic, excludes non-release state, and changes with same-version source', t => {
  const root = source(t), first = createArtifact(root)
  assert.deepEqual(createArtifact(root).bytes, first.bytes)
  const archive = join(root, 'verify.tgz')
  writeFileSync(archive, first.bytes)
  const listed = spawnSync(process.platform === 'win32' ? 'tar.exe' : 'tar', ['-tzf', archive], { encoding: 'utf8' })
  assert.equal(listed.status, 0, listed.stderr)
  assert.ok(listed.stdout.split(/\r?\n/).includes('package/lib/client.js'))
  assert.ok(gunzipSync(first.bytes).includes(Buffer.from('package/lib/client.js')))
  assert.ok(!gunzipSync(first.bytes).includes(Buffer.from('fixture-secret-excluded')))
  writeFileSync(join(root, 'lib/client.js'), 'new source, same version')
  const second = createArtifact(root)
  assert.equal(second.version, first.version)
  assert.notEqual(second.hash, first.hash)
})

test('unbuilt source and unsafe package whitelists cannot be deployed', t => {
  const root = source(t)
  writeFileSync(join(root, 'package.json'), JSON.stringify({ name: '@cannbot-plugin/cannbot-dsh', files: ['../private'] }))
  assert.throws(() => createArtifact(root), /whitelist/)
  rmSync(join(root, 'lib/client.js'))
  assert.throws(() => createArtifact(root), /尚未构建/)
})

test('deployment transfers the exact archive only over SSH stdin and requires a ready authenticated result', async () => {
  const artifact = { hash: 'a'.repeat(64), bytes: Buffer.from('source-payload-only-in-stdin'), version: '1.0.0-alpha.1' }
  const calls = [], progress = []
  const params = { artifact, server: { alias: 'fixture', inSshConfig: true }, binary: 'ssh', profile: 'web', remotePort: 17633, progress: message => progress.push(message) }
  const result = await deployCurrentPackage({ ...params, exec: async (command, args, options) => {
    calls.push({ command, args, options })
    options.onLine('CANNBOT_STEP=Preparing source build')
    options.onLine('CANNBOT_TOKEN=private-fixture-token')
    return { code: 0, stdout: 'CANNBOT_OK=1\nCANNBOT_REMOTE_PORT=17633\nCANNBOT_TOKEN=private-fixture-token\n', stderr: '' }
  } })
  assert.equal(calls.length, 1)
  assert.equal(calls[0].options.input, artifact.bytes)
  assert.ok(!calls[0].args.join(' ').includes(artifact.bytes.toString()))
  assert.deepEqual(progress, ['Preparing source build'])
  assert.equal(result.token, 'private-fixture-token')
  assert.equal(result.sourceHash, artifact.hash)
  await assert.rejects(deployCurrentPackage({ ...params, exec: async () => ({ code: 0, stdout: 'CANNBOT_OK=1\n', stderr: '' }) }), /同步失败/)
  await assert.rejects(deployCurrentPackage({ ...params, exec: async () => ({ code: 1, stdout: 'CANNBOT_ERROR=Stop the original server\n', stderr: '' }) }), /Stop the original server/)
})

test('remote installation avoids mirror tarball rewriting and honors custom registries', () => {
  for (const registry of ['', 'https://registry.npmmirror.com', 'https://registry.npmmirror.com/', 'https://packages.example.test/npm/']) {
    let invocation
    installCurrentPackage('/isolated/build', '/isolated/build/source.tgz', registry, { execute(command, args) {
      invocation = { command, args }
      return { status: 0, stdout: 'installed' }
    } })
    assert.equal(invocation.command, 'npm')
    const workflowRegistry = registry.includes('packages.example.test') ? registry : 'https://registry.npmjs.org/'
    assert.ok(invocation.args.includes(`--@cannbot-plugin:registry=${workflowRegistry}`))
    assert.equal(invocation.args[invocation.args.indexOf('--registry') + 1], workflowRegistry)
    assert.equal(invocation.args.includes('--replace-registry-host=never'), !registry.includes('packages.example.test'))
    assert.equal(invocation.args.at(-1), '/isolated/build/source.tgz')
    assert.ok(invocation.args.includes('--ignore-scripts'))
    assert.ok(invocation.args.includes('--legacy-peer-deps'))
  }
})

test('failed remote installs expose the package-manager code without authenticated URLs or secrets', () => {
  for (const stderr of [
    'npm error code E404\nnpm error 404 https://user:fixture-secret@registry.example.test/package?token=fixture-token',
    'npm ERR! code E404\nprivate fixture-token',
  ]) {
    assert.throws(() => installCurrentPackage('/build', '/build/source.tgz', '', { execute: () => ({ status: 1, stdout: 'fixture-secret', stderr }) }), error => {
      assert.match(error.message, /not found.*E404, exit 1/)
      assert.doesNotMatch(error.message, /fixture|https:|user:/)
      return true
    })
  }
  assert.throws(() => installCurrentPackage('/build', '/build/source.tgz', '', { execute: () => ({ status: null, error: new Error('fixture-secret'), stdout: '', stderr: '' }) }), /could not start/)
})

const expected = { executable: '/opt/dsh/bin/dsh.mjs', runtime: '/usr/bin/node', port: 17633, log: '/home/u/.dsh/web-17633.log', profile: 'web' }
function identitySystem(changes = {}) {
  const args = changes.args || ['/usr/bin/node', expected.executable, 'web', '--host', '127.0.0.1', '--port', '17633']
  return {
    uid: 1000,
    stat() { return { uid: changes.uid ?? 1000 } },
    realpath(file) { if (file.endsWith('/fd/1')) return changes.log || expected.log; if (file.endsWith('/exe')) return changes.runtime || expected.runtime; if ([expected.executable, expected.log, expected.runtime].includes(file)) return file; throw Error('not a file') },
    read(file) { if (file.endsWith('/cmdline')) return args.join('\0'); if (file.endsWith('/stat')) return '42 (node) ' + Array(19).fill('0').concat('777').join(' '); throw Error('missing') },
  }
}

test('legacy service adoption requires the exact user, DSH command, profile, loopback port and logfile', () => {
  assert.equal(processIdentity(42, expected, identitySystem()).start, '777')
  for (const changes of [
    { uid: 2000 }, { log: '/other/application.log' }, { runtime: '/usr/bin/another-process' },
    { args: ['/opt/other/dsh.mjs', 'web', '--host', '127.0.0.1', '--port', '17633'] },
    { args: [expected.executable, 'web', '--host', '0.0.0.0', '--port', '17633'] },
    { args: [expected.executable, 'web', '--host', '127.0.0.1', '--port', '17634'] },
    { args: [expected.executable, 'web', '--host', '127.0.0.1', '--port', '17633', '--profile', 'another'] },
  ]) assert.equal(processIdentity(42, expected, identitySystem(changes)), null)
})

test('service shutdown only terminates a validated main PID and refuses ambiguous or changed ownership', async () => {
  const owner = { ...expected, pid: 42, start: '777' }, killed = []
  const operations = { readOwner: () => owner, identify: () => owner, candidates: () => [], kill: (pid, signal) => killed.push([pid, signal]), busy: async () => false, wait: async () => {} }
  await stopOwned('unused', expected, operations)
  assert.deepEqual(killed, [[42, 'SIGTERM']])
  await assert.rejects(stopOwned('unused', expected, { ...operations, readOwner: () => null, candidates: () => [owner, { ...owner, pid: 43 }] }), /safely identify/)
  let reads = 0
  await assert.rejects(stopOwned('unused', expected, { ...operations, identify: () => ++reads === 1 ? owner : { ...owner, start: '999' } }), /changed before shutdown/)
  assert.equal(killed.length, 1)
})

test('an uncooperative verified service is never escalated to a force kill', async () => {
  const owner = { ...expected, pid: 42, start: '777' }, signals = []
  await assert.rejects(stopOwned('unused', expected, { readOwner: () => owner, identify: () => owner, kill: (_pid, signal) => signals.push(signal), busy: async () => true, wait: async () => {} }), /did not exit/)
  assert.deepEqual(signals, ['SIGTERM'])
})

test('discovery follows an existing owned port and refuses a second instance in the same data directory', () => {
  const home = resolve('/fixture-home/.dsh')
  const operations = {
    uid: 1000, defaultHome: home, list: () => ['42'], stat: () => ({ uid: 1000 }),
    realpath: path => path,
    read: path => path.endsWith('/environ') ? '' : [expected.executable, 'web', '--host', '127.0.0.1', '--port', '17650'].join('\0'),
    identify: (pid, value) => ({ ...value, pid, start: '777' }),
  }
  assert.equal(existingWeb(home, expected.executable, 'web', operations).port, 17650)
  assert.throws(() => existingWeb(home, expected.executable, 'web', { ...operations, identify: () => null }), /ownership cannot be verified/)
  assert.throws(() => existingWeb(home, expected.executable, 'web', { ...operations, list: () => ['42', '43'] }), /Multiple DSH/)
  assert.equal(existingWeb(resolve('/other-home/.dsh'), expected.executable, 'web', operations), null)
})
