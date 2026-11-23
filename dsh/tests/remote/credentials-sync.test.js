// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { test } from 'node:test'
import assert from 'node:assert/strict'
import { existsSync } from 'node:fs'
import { chmod, lstat, mkdir, mkdtemp, readFile, rm, symlink, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { Readable } from 'node:stream'
import { ACCOUNT_RECORD_KEY, MAX_CREDENTIAL_BYTES, syncCredentials } from '../../src/remote/credentials-sync.js'
import { loadDshDependencies, mergeAccountGrant, runRemoteSync, supportsDefaultStore } from '../../remote/sync-credentials.mjs'

const fakeToken = 'TEST_ONLY_PRIVATE_GRANT_6f11d519'
const record = (token = fakeToken) => ({ kind: 'grant', payload: { version: 1, token, issuer: 'https://platform.deepseek.com' } })
const server = { alias: 'test-server', inSshConfig: true }
const summaryHasNoSecret = value => assert.equal(JSON.stringify(value).includes(fakeToken), false)

test('missing local account skips SSH and reads only the approved record', async () => {
  let calls = 0
  const result = await syncCredentials({ server, readLocalRecord: async key => {
    assert.equal(key, ACCOUNT_RECORD_KEY)
    return undefined
  }, exec: async () => { calls++ } })
  assert.equal(result.status, 'local-missing')
  assert.equal(calls, 0)
})

test('account grant travels only over stdin, never argv, environment, progress, or return value', async () => {
  let calls = 0
  const result = await syncCredentials({ server, binary: 'custom-ssh', profile: 'custom-profile',
    readLocalRecord: async () => ({ ...record(), ignoredPrivateField: 'unrelated-secret' }),
    exec: async (command, args, options) => {
      calls++
      assert.equal(command, 'custom-ssh')
      assert.equal(JSON.stringify(args).includes(fakeToken), false)
      assert.equal(options.env, undefined)
      assert.equal(options.onLine, undefined)
      assert.match(args.at(-1), /node --input-type=module -e /)
      assert.match(args.at(-1), /'custom-profile'$/)
      assert.deepEqual(JSON.parse(options.input), record())
      assert.equal(options.input.includes('unrelated-secret'), false)
      return { code: 0, stdout: 'CANNBOT_CREDENTIALS_STATUS=synced\n', stderr: '', timedOut: false }
    } })
  assert.equal(calls, 1)
  assert.equal(result.status, 'synced')
  assert.deepEqual(Object.keys(result).sort(), ['message', 'status'])
  summaryHasNoSecret(result)
})

test('unsupported providers, versions, issuers and oversized tokens never leave the Host', async () => {
  const variants = [
    { kind: 'api-key', key: fakeToken },
    { kind: 'grant', payload: { ...record().payload, version: 2 } },
    { kind: 'grant', payload: { ...record().payload, issuer: 'https://other.example' } },
    record('dsh_mock_test'), record('contains\nnewline'), record('X'.repeat(MAX_CREDENTIAL_BYTES)),
  ]
  for (const invalid of variants) {
    const result = await syncCredentials({ server, readLocalRecord: async () => invalid,
      exec: async () => assert.fail('unsupported credentials must not be sent') })
    assert.equal(result.status, 'unsupported')
    summaryHasNoSecret(result)
  }
  assert.equal((await syncCredentials({ server })).status, 'unsupported')
})

test('fixed summaries contain no SSH, storage or credential exception details', async () => {
  for (const remote of [
    { code: 1, stdout: fakeToken, stderr: fakeToken },
    { code: 0, stdout: fakeToken, stderr: fakeToken },
    { code: 0, timedOut: true, stdout: 'CANNBOT_CREDENTIALS_STATUS=synced' },
    { code: 0, stdout: 'CANNBOT_CREDENTIALS_STATUS=synced\nCANNBOT_CREDENTIALS_STATUS=unchanged\n' },
  ]) {
    const result = await syncCredentials({ server, readLocalRecord: async () => record(), exec: async () => remote })
    assert.equal(result.status, 'failed')
    summaryHasNoSecret(result)
  }
  const result = await syncCredentials({ server, readLocalRecord: async () => { throw new Error(fakeToken) } })
  assert.equal(result.status, 'failed')
  summaryHasNoSecret(result)
})

test('remote boundary rejects invalid and oversized stdin before loading modules or touching files', async () => {
  for (const input of ['not JSON ' + fakeToken, ' '.repeat(MAX_CREDENTIAL_BYTES + 1), JSON.stringify({ ...record(), extra: fakeToken })]) {
    let output = ''
    const status = await runRemoteSync({ input: Readable.from([input]), output: { write: value => { output += value } },
      loadDependencies: async () => assert.fail('input validation must precede module loading') })
    assert.equal(status, 'unsupported')
    assert.equal(output, 'CANNBOT_CREDENTIALS_STATUS=unsupported\n')
    summaryHasNoSecret(output)
  }
})

test('remote boundary hides dependency and profile errors', async () => {
  let output = ''
  const status = await runRemoteSync({ input: Readable.from([JSON.stringify(record())]),
    output: { write: value => { output += value } }, loadDependencies: async () => { throw new Error(fakeToken) } })
  assert.equal(status, 'unsupported')
  assert.equal(output, 'CANNBOT_CREDENTIALS_STATUS=unsupported\n')
})

// These integration cases use unmodified official DSH dependencies. CI can point
// this variable at a test installation; it never points at a real credential file.
const officialEntry = process.env.CANNBOT_TEST_DSH_EXECUTABLE
  || fileURLToPath(new URL('../../_scratch/credentials-official/dsh-entry.mjs', import.meta.url))
const officialAvailable = existsSync(officialEntry)
const officialOptions = { skip: officialAvailable ? false : 'set CANNBOT_TEST_DSH_EXECUTABLE to test with official DSH modules' }
async function fixture(t) {
  const root = await mkdtemp(join(tmpdir(), 'cannbot-credentials-test-'))
  t.after(async () => { await rm(root, { recursive: true, force: true }) })
  const dshHome = join(root, 'isolated-dsh-home')
  const filename = join(dshHome, '.credentials.yaml')
  const dependencies = await loadDshDependencies(officialEntry)
  assert.ok(dependencies)
  return { root, dshHome, filename, dependencies,
    merge: value => mergeAccountGrant({ record: value, dshHome, dependencies }),
    async seed(text) { await mkdir(dshHome, { recursive: true, mode: 0o700 }); await writeFile(filename, text, { mode: 0o600 }) },
    async read() { return dependencies.parseCredentialsDocument(await readFile(filename, 'utf8'), filename) },
  }
}

test('official parser and writer create a private version-1 store with only the approved grant', officialOptions, async t => {
  const f = await fixture(t)
  assert.equal(await f.merge(record()), 'synced')
  const parsed = await f.read()
  assert.deepEqual([...parsed.records.keys()], [ACCOUNT_RECORD_KEY])
  assert.deepEqual(parsed.records.get(ACCOUNT_RECORD_KEY), record())
  assert.equal(parsed.refs.size, 0)
  if (process.platform !== 'win32') {
    assert.equal((await lstat(f.filename)).mode & 0o777, 0o600)
    assert.equal((await lstat(f.dshHome)).mode & 0o777, 0o700)
  }
})

test('official merge preserves API keys, other OAuth grants, devices, and YAML comments', officialOptions, async t => {
  const f = await fixture(t)
  await f.seed('# keep this comment\nversion: 1\nrefs:\n  OPENAI_API_KEY: unrelated-test-key\nrecords:\n  deepseek-account-platform/device:\n    kind: grant\n    payload: {id: test-device-id}\n  llm-pi-ai/other:\n    kind: grant\n    payload: {refresh: unrelated-test-refresh}\n')
  const before = await f.read()
  assert.equal(await f.merge(record()), 'synced')
  const after = await f.read()
  assert.deepEqual(after.refs, before.refs)
  for (const [key, value] of before.records) assert.deepEqual(after.records.get(key), value)
  assert.match(await readFile(f.filename, 'utf8'), /^# keep this comment/m)
  assert.equal(after.records.size, 3)
})

test('same login is unchanged and any existing different login is preserved byte-for-byte', officialOptions, async t => {
  const f = await fixture(t)
  assert.equal(await f.merge(record()), 'synced')
  const before = await readFile(f.filename, 'utf8')
  assert.equal(await f.merge(record()), 'unchanged')
  assert.equal(await f.merge(record('ANOTHER_TEST_ACCOUNT')), 'remote-preserved')
  assert.equal(await readFile(f.filename, 'utf8'), before)
})

test('official writer lock prevents concurrent different logins from overwriting each other', officialOptions, async t => {
  const f = await fixture(t)
  const results = await Promise.all([f.merge(record()), f.merge(record('SECOND_TEST_ACCOUNT'))])
  assert.deepEqual(results.sort(), ['remote-preserved', 'synced'])
  const token = (await f.read()).records.get(ACCOUNT_RECORD_KEY).payload.token
  assert.ok([fakeToken, 'SECOND_TEST_ACCOUNT'].includes(token))
})

test('malformed or future stores stay untouched and errors never echo their contents', officialOptions, async t => {
  const f = await fixture(t)
  for (const original of ['version: 2\nrecords: {}\n', `version: 1\nrecords: [${fakeToken}\n`]) {
    await f.seed(original)
    assert.equal(await f.merge(record()), 'unsupported')
    assert.equal(await readFile(f.filename, 'utf8'), original)
  }
})

test('symlink target is refused and its destination remains unchanged', officialOptions, async t => {
  const f = await fixture(t)
  await mkdir(f.dshHome, { recursive: true })
  const target = join(f.root, 'other-file')
  await writeFile(target, 'do not modify', { mode: 0o600 })
  try { await symlink(target, f.filename) } catch (error) {
    if (process.platform === 'win32' && error.code === 'EPERM') { t.skip('Windows symlink privilege unavailable'); return }
    throw error
  }
  let output = ''
  const status = await runRemoteSync({ dshHome: f.dshHome, input: Readable.from([JSON.stringify(record())]),
    output: { write: value => { output += value } }, loadDependencies: async () => f.dependencies, checkProfile: async () => true })
  assert.equal(status, 'failed')
  assert.equal(output, 'CANNBOT_CREDENTIALS_STATUS=failed\n')
  assert.equal(await readFile(target, 'utf8'), 'do not modify')
  assert.equal((await lstat(f.filename)).isSymbolicLink(), true)
})

test('world-readable existing store is refused on POSIX', { ...officialOptions, skip: !officialAvailable || process.platform === 'win32' }, async t => {
  const f = await fixture(t)
  await f.seed('version: 1\nrecords: {}\n')
  await chmod(f.filename, 0o644)
  await assert.rejects(() => f.merge(record()))
  assert.equal(await readFile(f.filename, 'utf8'), 'version: 1\nrecords: {}\n')
})

test('effective profile check accepts default store and rejects custom storage, disabled watch, or issuer', officialOptions, async () => {
  const dependencies = await loadDshDependencies(officialEntry)
  const dump = (store = '', account = '') => '- id: credentials\n  name: "@deepseek-ai/dsh-credentials-local"\n'
    + store + '- id: deepseek-account\n  name: "@deepseek-ai/dsh-deepseek-account-platform"\n' + account
  assert.equal(supportsDefaultStore(dump(), dependencies.parseDocument), true)
  for (const config of ['  config: {path: /other/store}\n', '  config: {dshHome: /other}\n', '  config: {watch: false}\n', '  disabled: true\n']) {
    assert.equal(supportsDefaultStore(dump(config), dependencies.parseDocument), false)
  }
  assert.equal(supportsDefaultStore(dump('', '  config: {platformOrigin: "https://other.example"}\n'), dependencies.parseDocument), false)
  assert.equal(supportsDefaultStore(dump() + '- name: cordis:include\n  config: {path: other.yml}\n', dependencies.parseDocument), false)
  assert.equal(supportsDefaultStore(dump() + '- id: duplicate\n  name: "@deepseek-ai/dsh-credentials-local"\n', dependencies.parseDocument), false)
})
