// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// Licensed under CANN Open Software License Agreement Version 2.0. See LICENSE.
// Optional real OpenSSH test: CANNBOT_TEST_SSH2 points to a separately installed
// ssh2 module. The test server only accepts loopback and synthetic credentials.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { generateKeyPairSync } from 'node:crypto'
import { mkdtempSync, writeFileSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { createManager } from '../../src/remote/manager.js'
import { TunnelSupervisor } from '../../src/remote/tunnel.js'
import { run } from '../../src/remote/exec.js'
import { sshArgs } from '../../src/remote/bootstrap.js'

test('system OpenSSH authenticates, retries, transfers stdin and opens a tunnel using one password dialog', { skip: !process.env.CANNBOT_TEST_SSH2, timeout: 60000 }, async () => {
  const { Server, utils } = createRequire(import.meta.url)(process.env.CANNBOT_TEST_SSH2)
  const { privateKey } = generateKeyPairSync('rsa', { modulusLength: 2048, privateKeyEncoding: { type: 'pkcs1', format: 'pem' }, publicKeyEncoding: { type: 'spki', format: 'pem' } })
  const secret = 'synthetic-only-密碼 $&"123', clients = new Set(), commands = [], inputs = [], prompts = [], logs = []
  const fixture = mkdtempSync(join(tmpdir(), 'cannbot-ssh-test-'))
  const sshServer = new Server({ hostKeys: [privateKey] }, client => {
    clients.add(client); client.on('error', () => {}); client.on('close', () => clients.delete(client))
    client.on('authentication', ctx => {
      if (ctx.method === 'password' && ctx.username === 'cannbot-test' && ctx.password === secret) ctx.accept()
      else ctx.reject(['password'])
    })
    client.on('ready', () => {
      client.on('session', accept => {
        const session = accept()
        session.on('exec', (accept, _reject, info) => {
          const channel = accept(); commands.push(info.command)
          const data = []; channel.on('data', chunk => data.push(chunk))
          channel.on('end', () => {
            inputs.push(Buffer.concat(data))
            if (info.command.includes('CANNBOT_SSH_OK')) channel.write('CANNBOT_SSH_OK\n')
            else if (info.command.includes('CANNBOT_STATE_DSH')) channel.write('CANNBOT_STATE_DSH=0.2.2-rc.1\n')
            else if (info.command.includes('bash -s')) channel.write('CANNBOT_OK=1\nCANNBOT_REMOTE_PORT=17633\nCANNBOT_TOKEN=fixture\n')
            else if (info.command.includes('test-transfer')) channel.write(Buffer.concat(data))
            channel.exit(0); channel.end()
          })
        })
      })
      client.on('tcpip', accept => { const channel = accept(); channel.on('error', () => {}); channel.end() })
    })
  })
  await new Promise(resolve => sshServer.listen(0, '127.0.0.1', resolve))
  const port = sshServer.address().port, known = join(fixture, 'known_hosts'), config = join(fixture, 'config')
  writeFileSync(known, `[127.0.0.1]:${port} ssh-rsa ${utils.parseKey(privateKey).getPublicSSH().toString('base64')}\n`)
  writeFileSync(config, `Host test\n  HostName 127.0.0.1\n  Port ${port}\n  User cannbot-test\n`)
  const records = join(fixture, 'servers.json'), state = join(fixture, 'state.json')
  writeFileSync(records, JSON.stringify({ version: 1, servers: [{ alias: 'test', hostName: '127.0.0.1', user: 'cannbot-test', port }] }))
  const prefix = ['-F', config, '-o', `UserKnownHostsFile=${known}`, '-o', 'StrictHostKeyChecking=yes']
  const tunnel = new TunnelSupervisor({ logger: line => logs.push(line) })
  const originalEnsure = tunnel.ensure.bind(tunnel)
  tunnel.ensure = input => originalEnsure({ ...input, sshArgs: [...prefix, ...input.sshArgs] })
  const manager = createManager({ serversFile: records, stateFile: state, sshConfig: config, tunnel,
    config: { syncLogin: false, localPortStart: 27633 }, logger: line => logs.push(line),
    exec: (command, args, options) => run(command, [...prefix, ...args], options),
    deployPackage: async ({ server, exec }) => {
      const base = sshArgs({ server }), bytes = Buffer.from('archive-data\0\r\n中文')
      const result = await exec(base.command, [...base.args, base.target, 'test-transfer'], { input: bytes })
      assert.equal(result.code, 0); assert.equal(result.stdout, bytes.toString()); return {}
    },
  })
  try {
    const result = await manager.connect('test', { requestId: 'test-attempt', passwordPrompt: true, progress(event) {
      if (event.phase !== 'password') return
      prompts.push(event)
      assert.equal(manager.submitPassword('test', 'stale-attempt', event.challengeId, secret), false)
      assert.equal(manager.submitPassword('test', 'test-attempt', event.challengeId, prompts.length === 1 ? 'wrong-fixture-password' : secret), true)
    } })
    assert.equal(result.ok, true, JSON.stringify(result))
    assert.equal(prompts.length, 2, 'one correction; inspection, bootstrap, transfer and tunnel reuse the accepted password')
    assert.equal(prompts[1].retry, true)
    assert.equal(manager.serverStatus(manager.inventory().servers[0]).connected, true)
    assert(commands.length >= 4); assert(inputs.some(bytes => bytes.includes(Buffer.from('archive-data\0'))))
    assert.equal(readFileSync(state, 'utf8').includes(secret), false)
    assert.equal(JSON.stringify(logs).includes(secret), false)
    manager.disconnect('test'); assert.equal(tunnel.has('test'), false)
  } finally {
    tunnel.stopAll(); for (const client of clients) client.end()
    await new Promise(resolve => sshServer.close(resolve))
    rmSync(fixture, { recursive: true, force: true })
  }
})
