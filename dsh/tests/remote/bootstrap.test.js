// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { test } from 'node:test'
import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import {
  bootstrapSshInvocation,
  parseBootstrapOutput,
  parseStateOutput,
  readRemoteScript,
  sshArgs,
  stateProbeCommand,
  failureHint,
} from '../../plugin/backend/ssh/bootstrap.js'
import { installArgs, installCommandLine, loadCatalog, normalizeCatalog, registryArgs } from '../../plugin/backend/ssh/catalog.js'

const SHARED_SERVER = {
  alias: 'npu-01',
  inSshConfig: true,
  hostName: '10.0.0.11',
  user: 'HwHiAiUser',
  port: 2222,
}

test('sshArgs relies on ssh config for configured aliases', () => {
  const { args, target } = sshArgs({ server: SHARED_SERVER })
  assert.equal(target, 'npu-01')
  assert.ok(args.includes('-o'))
  assert.ok(args.includes('BatchMode=yes'))
  assert.ok(!args.includes('-p'), 'no explicit port when the alias is in ssh config')
})

test('sshArgs builds user@host for servers outside ssh config', () => {
  const { args, target } = sshArgs({
    server: { alias: 'adhoc', inSshConfig: false, hostName: '10.9.9.9', user: 'me', port: 2200 },
  })
  assert.equal(target, 'me@10.9.9.9')
  assert.deepEqual(args.slice(-2), ['-p', '2200'])
})

test('bootstrapSshInvocation sends a single quoted remote command to OpenSSH', () => {
  const invocation = bootstrapSshInvocation({
    server: SHARED_SERVER,
    remotePort: 17633,
    dshVersion: '0.2.2-rc.1',
    pluginVersion: '1.0.0-alpha.1',
    registry: 'https://registry.npmmirror.com',
    profile: 'web',
  })
  assert.equal(invocation.command, 'ssh')
  assert.equal(invocation.target, 'npu-01')
  assert.deepEqual(invocation.args.slice(-2), [
    'npu-01',
    "bash -s -- '17633' '0.2.2-rc.1' '1.0.0-alpha.1' 'https://registry.npmmirror.com' 'web'",
  ])
})

test('bootstrapSshInvocation retains empty reuse versions before registry and profile', () => {
  const invocation = bootstrapSshInvocation({ server: SHARED_SERVER, remotePort: 17633, dshVersion: '', pluginVersion: '', registry: 'https://registry.npmmirror.com', profile: 'web' })
  assert.equal(invocation.args.at(-1), "bash -s -- '17633' '' '' 'https://registry.npmmirror.com' 'web'")
})

test('remote shell receives empty and special-character arguments literally', { skip: process.platform === 'win32' && 'requires a POSIX shell' }, () => {
  const registry = "https://registry.example/a b'c?x=$HOME&y=$(printf injected)"
  const invocation = bootstrapSshInvocation({ server: SHARED_SERVER, remotePort: 17633, dshVersion: '', pluginVersion: '', registry, profile: 'web' })
  const result = spawnSync('sh', ['-c', invocation.args.at(-1)], { input: 'printf "%s\\0" "$@"', encoding: 'utf8' })
  assert.ifError(result.error)
  assert.equal(result.status, 0, result.stderr)
  assert.deepEqual(result.stdout.split('\0').slice(0, -1), ['17633', '', '', registry, 'web'])
})

function nativeProbeFixture(t, { nested = true, working = true } = {}) {
  const root = mkdtempSync(join(tmpdir(), 'cannbot-native-'))
  t.after(() => rmSync(root, { recursive: true, force: true }))
  const npmRoot = join(root, 'custom-prefix', 'lib', 'node_modules')
  const dshDir = join(npmRoot, '@deepseek-ai', 'dsh')
  const executable = join(dshDir, 'bin', 'dsh.js')
  const wrapper = join(root, 'bin', 'dsh')
  const ptyDir = nested ? join(dshDir, 'node_modules', 'node-pty') : join(npmRoot, 'node-pty')
  for (const dir of [dirname(executable), dirname(wrapper), ptyDir]) mkdirSync(dir, { recursive: true })
  writeFileSync(join(dshDir, 'package.json'), JSON.stringify({ name: '@deepseek-ai/dsh' }))
  writeFileSync(executable, '')
  writeFileSync(wrapper, '')
  writeFileSync(join(ptyDir, 'index.js'), working ? 'exports.spawn = function () {}' : 'throw new Error("native binding missing")')
  const source = readRemoteScript().match(/<<'NODE_NATIVE_CHECK'\n([\s\S]*?)\nNODE_NATIVE_CHECK/)[1]
  return {
    check(entry = executable, globalRoot = '') {
      const result = spawnSync(process.execPath, ['-', entry, globalRoot], { input: source, encoding: 'utf8', windowsHide: true })
      assert.ifError(result.error)
      return result.status
    },
    executable, wrapper, npmRoot,
  }
}

test('native check resolves node-pty nested under the actual DSH executable', (t) => {
  const fixture = nativeProbeFixture(t)
  assert.equal(fixture.check(), 0)
})

test('native check supports custom npm prefixes and flat dependency layouts', (t) => {
  const fixture = nativeProbeFixture(t, { nested: false })
  assert.equal(fixture.check(fixture.wrapper, fixture.npmRoot), 0)
})

test('native check rejects an installed node-pty whose native binding cannot load', (t) => {
  const fixture = nativeProbeFixture(t, { working: false })
  assert.equal(fixture.check(fixture.executable, fixture.npmRoot), 1)
})

test('parseBootstrapOutput extracts every marker', () => {
  const stdout = [
    '[cannbot] installing',
    'CANNBOT_STEP=1/7 check node',
    'CANNBOT_STEP=5/7 install CANNBot plugin',
    'CANNBOT_REMOTE_PORT=17634',
    'CANNBOT_WEB_LOG=/home/u/.dsh/web-17634.log',
    'CANNBOT_TOKEN=abc123_DEF',
    'CANNBOT_REUSE=1',
    'CANNBOT_OK=1',
  ].join('\n')
  const parsed = parseBootstrapOutput(stdout)
  assert.equal(parsed.ok, true)
  assert.equal(parsed.token, 'abc123_DEF')
  assert.equal(parsed.remotePort, 17634)
  assert.equal(parsed.webLog, '/home/u/.dsh/web-17634.log')
  assert.equal(parsed.reused, true)
  assert.deepEqual(parsed.steps, ['1/7 check node', '5/7 install CANNBot plugin'])
})

test('parseBootstrapOutput reports failures and empty tokens', () => {
  const parsed = parseBootstrapOutput('CANNBOT_ERROR=plugin install failed\nCANNBOT_TOKEN=\n')
  assert.equal(parsed.ok, false)
  assert.equal(parsed.token, '')
  assert.equal(parsed.error, 'plugin install failed')
  assert.equal(failureHint(parsed, 1), 'plugin install failed')
  assert.match(failureHint({}, -2), /超时/)
  assert.match(failureHint({}, 3), /exit 3/)
})

test('sshArgs reports the ssh binary it will spawn', () => {
  const invocation = sshArgs({ server: SHARED_SERVER, binary: 'C:\\custom\\ssh.exe' })
  assert.equal(invocation.command, 'C:\\custom\\ssh.exe')
})

test('stateProbeCommand extends PATH and reads both versions', () => {
  const command = stateProbeCommand('web')
  assert.match(command, /export PATH="\$HOME\/\.local\/bin:\$PATH"/, 'non-interactive ssh has no ~/.local/bin on PATH')
  assert.match(command, /CANNBOT_STATE_DSH=/)
  assert.match(command, /@cannbot-plugin\/cannbot-dsh/)
  assert.ok(command.includes("'web'"))
})

test('parseStateOutput normalises the none sentinel', () => {
  assert.deepEqual(
    parseStateOutput('CANNBOT_STATE_DSH=0.2.2-rc.1\nCANNBOT_STATE_PLUGIN=1.0.0-alpha.1\n'),
    { dshVersion: '0.2.2-rc.1', pluginVersion: '1.0.0-alpha.1' },
  )
  assert.deepEqual(parseStateOutput('CANNBOT_STATE_DSH=none\nCANNBOT_STATE_PLUGIN=none\n'), {
    dshVersion: '',
    pluginVersion: '',
  })
  assert.deepEqual(parseStateOutput('garbage'), { dshVersion: '', pluginVersion: '' })
})

test('readRemoteScript is LF-only and streams a complete script', () => {
  const script = readRemoteScript()
  assert.ok(script.length > 1000, 'script body present')
  assert.equal(script.includes('\r'), false, 'no CR characters (bash would choke on $\\r)')
  assert.match(script, /^#!\/usr\/bin\/env bash/)
  assert.match(script, /CANNBOT_OK=1/)
  assert.match(script, /CANNBOT_ERROR=/)
})

test('catalog install args forward to dsh plugin', () => {
  const catalog = normalizeCatalog({
    entries: [{ package: 'cannbot-dsh', version: '1.0.0-alpha.1', profile: 'web' }],
  })
  const entry = catalog.entries[0]
  assert.deepEqual(installArgs(entry), ['plugin', '--profile', 'web', 'add', 'cannbot-dsh@1.0.0-alpha.1'])
  assert.deepEqual(registryArgs('https://r.example'), ['--registry', 'https://r.example'])
  assert.equal(
    installCommandLine(entry, 'https://r.example'),
    'dsh plugin --profile web add cannbot-dsh@1.0.0-alpha.1 --registry https://r.example',
  )
})

test('loadCatalog falls back to the built-in catalog', () => {
  const catalog = loadCatalog('')
  assert.equal(catalog.entries.length, 1)
  assert.equal(catalog.entries[0].package, '@cannbot-plugin/cannbot-dsh-server')
  assert.equal(catalog.entries[0].required, true)
})
