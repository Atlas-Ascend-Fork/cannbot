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
import { createPackageArtifact } from '../../tools/package-archive.mjs'
import { deployCurrentPackage, pairedServer } from '../../plugin/backend/ssh/deploy.js'
import { processIdentity, availablePort, existingWeb, readyServer, preinstalledArchive, installCurrentPackage } from '../../remote/deploy-package.mjs'

function source(t) {
  const root = mkdtempSync(join(tmpdir(), 'cannbot-artifact-'))
  t.after(() => rmSync(root, { recursive: true, force: true }))
  writeFileSync(join(root, 'package.json'), JSON.stringify({ name: '@cannbot-plugin/cannbot-dsh', version: '1.0.0-alpha.1', files: ['lib', 'remote'] }))
  for (const file of ['lib/index.js', 'lib/client.js', 'remote/deploy-package.mjs']) { mkdirSync(join(root, file.split('/')[0]), { recursive: true }); writeFileSync(join(root, file), 'current source') }
  writeFileSync(join(root, '.credentials'), 'fixture-secret-excluded')
  return root
}

test('release archive is deterministic, excludes non-release state, and changes with same-version source', t => {
  const root = source(t), first = createPackageArtifact(root)
  assert.deepEqual(createPackageArtifact(root).bytes, first.bytes)
  const archive = join(root, 'verify.tgz')
  writeFileSync(archive, first.bytes)
  const listed = spawnSync(process.platform === 'win32' ? 'tar.exe' : 'tar', ['-tzf', archive], { encoding: 'utf8' })
  assert.equal(listed.status, 0, listed.stderr)
  assert.ok(listed.stdout.split(/\r?\n/).includes('package/lib/client.js'))
  assert.ok(gunzipSync(first.bytes).includes(Buffer.from('package/lib/client.js')))
  assert.ok(!gunzipSync(first.bytes).includes(Buffer.from('fixture-secret-excluded')))
  writeFileSync(join(root, 'lib/client.js'), 'new source, same version')
  const second = createPackageArtifact(root)
  assert.equal(second.version, first.version)
  assert.notEqual(second.hash, first.hash)
})

test('unsafe package whitelists are rejected', t => {
  const root = source(t)
  writeFileSync(join(root, 'package.json'), JSON.stringify({ name: '@cannbot-plugin/cannbot-dsh', files: ['../private'] }))
  assert.throws(() => createPackageArtifact(root), /whitelist/)
})

test('pairing uses the matching server edition, buildId and version', t => {
  const root = source(t), pkgPath = join(root, 'package.json')
  const client = { ...JSON.parse(readFileSync(pkgPath)), cannbotEdition: 'client', cannbotBuildId: 'build-1' }
  writeFileSync(pkgPath, JSON.stringify(client))
  const bytes = Buffer.from('server only')
  const file = join(root, 'remote/server.json'), metadata = { name: '@cannbot-plugin/cannbot-dsh-server', version: client.version, buildId: 'build-1' }
  writeFileSync(file, JSON.stringify(metadata)); writeFileSync(join(root, 'remote/server.tgz'), bytes)
  assert.deepEqual(pairedServer(root), { bytes, version: client.version, buildId: 'build-1' })
  for (const override of [{ buildId: 'build-2' }, { name: client.name }, { version: '2.0.0' }]) {
    writeFileSync(file, JSON.stringify({ ...metadata, ...override })); assert.throws(() => pairedServer(root))
  }
})

test('deployment uploads only on cache miss and accepts only a matching authenticated server', async () => {
  const artifact = { bytes: Buffer.from('only-in-stdin'), version: '1.0.0', buildId: 'build-1' }
  const params = { artifact, server: { alias: 'fixture', inSshConfig: true }, binary: 'ssh', remotePort: 17633 }
  const ready = 'CANNBOT_OK=1\nCANNBOT_REMOTE_PORT=17633\nCANNBOT_TOKEN=fixture\nCANNBOT_PLUGIN_VERSION=1.0.0\nCANNBOT_BUILD_ID=build-1\n'
  for (const cached of [true, false]) {
    const calls = []
    const result = await deployCurrentPackage({ ...params, exec: async (command, args, options) => {
      assert.ok(!args.join(' ').includes(artifact.bytes.toString()))
      calls.push(options.input)
      return { code: 0, stdout: cached || calls.length > 1 ? ready : 'CANNBOT_NEED_ARCHIVE=1\n' }
    } })
    assert.deepEqual(calls, cached ? [Buffer.alloc(0)] : [Buffer.alloc(0), artifact.bytes])
    assert.equal(result.profile, 'cannbot-server-' + artifact.buildId)
    assert.equal(result.buildId, artifact.buildId)
  }
  for (const output of [ready.replace('build-1', 'other'), ready.replace('1.0.0', '0.2.0'), ready.replace('TOKEN=fixture', 'TOKEN=')]) {
    await assert.rejects(deployCurrentPackage({ ...params, exec: async () => ({ code: 0, stdout: output }) }), /同步失败/)
  }
})

test('manual Linux installation reuses only its matching preinstalled build', t => {
  const root = source(t), home = join(root, '.dsh')
  const profile = join(home, 'profiles', 'cannbot-server'), releases = join(root, '.local/share/cannbot/releases/b1')
  mkdirSync(profile, { recursive: true }); mkdirSync(releases, { recursive: true })
  const bytes = Buffer.from('preinstalled')
  const receipt = { schemaVersion: 1, edition: 'server', version: '1.0.0', buildId: 'b1' }
  writeFileSync(join(releases, 'server.tgz'), bytes)
  const check = () => preinstalledArchive(home, root, '1.0.0', 'b1')
  for (const patch of [{ edition: 'client' }, { buildId: 'b2' }, { version: '1.0.1' }]) {
    writeFileSync(join(profile, '.cannbot-install.json'), JSON.stringify({ ...receipt, ...patch })); assert.equal(check(), null)
  }
  writeFileSync(join(profile, '.cannbot-install.json'), JSON.stringify(receipt)); assert.deepEqual(check(), bytes)
})

test('a listening DSH Web counts as ready only when the paired server plugin answers', async () => {
  for (const [edition, version, buildId, ready] of [['server', '1.0.0', 'b1', true], ['client', '1.0.0', 'b1', false], ['server', '1.0.1', 'b1', false], ['server', '1.0.0', 'b2', false]]) {
    const fetcher = async (url, options) => {
      if (url.endsWith('/?token=login')) return new Response(null, { status: 303, headers: { 'set-cookie': 'auth=fixture; HttpOnly' } })
      assert.equal(url, 'http://127.0.0.1:17634/api/cannbot-dsh/server'); assert.equal(options.headers.cookie, 'auth=fixture')
      return Response.json({ edition, version, buildId })
    }
    assert.equal(await readyServer(17634, 'login', '1.0.0', 'b1', fetcher), ready)
  }
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
    { args: [expected.executable, '--profile', 'another', '--host', '127.0.0.1', '--port', '17633'] },
  ]) assert.equal(processIdentity(42, expected, identitySystem(changes)), null)
})

test('new builds select a free port without stopping other profiles or users', async () => {
  assert.equal(await availablePort(18888, async () => false), 18888)
  assert.equal(await availablePort(17633, async p => p < 17635), 17635)
  await assert.rejects(availablePort(17633, async () => true), /No loopback port/)
})

test('discovery follows an existing owned port and refuses a second instance in the same data directory', () => {
  const home = resolve('/fixture-home/.dsh')
  const operations = {
    uid: 1000, defaultHome: home, list: () => ['42'], stat: () => ({ uid: 1000 }),
    realpath: path => path,
    read: path => path.endsWith('/environ') ? '' : [expected.executable, 'web', '--host', '127.0.0.1', '--port', '17650'].join('\0'),
    identify: (pid, value) => ({ ...value, pid, start: '777' }),
  }
  assert.equal(existingWeb(home, expected.executable, 'cannbot-server-other', operations), null)
  assert.equal(existingWeb(home, expected.executable, 'web', operations).port, 17650)
  assert.throws(() => existingWeb(home, expected.executable, 'web', { ...operations, identify: () => null }), /ownership cannot be verified/)
  assert.throws(() => existingWeb(home, expected.executable, 'web', { ...operations, list: () => ['42', '43'] }), /Multiple DSH/)
  assert.equal(existingWeb(resolve('/other-home/.dsh'), expected.executable, 'web', operations), null)
})
