// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// Licensed under CANN Open Software License Agreement Version 2.0. See LICENSE.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { existsSync } from 'node:fs'
import { resolve } from 'node:path'
import { createPasswordAuth } from '../../src/remote/password-auth.js'
import { run } from '../../src/remote/exec.js'

test('native askpass reuses credentials per identity, retries and disposes without writing the password', { timeout: 30000 }, async () => {
  const events = [], secret = 'test-only-密碼 $ & " 123'
  let auth
  auth = await createPasswordAuth({ onPrompt(event) { events.push(event); assert(auth.submit(event.challengeId, secret)) } })
  const first = auth.invocation(['-o', 'BatchMode=yes', '-o', 'NumberOfPasswordPrompts=0'])
  const helper = prompt => run(first.env.SSH_ASKPASS, [prompt], { env: first.env, cwd: first.cwd })
  try {
    assert(!JSON.stringify(first).includes(secret))
    assert(first.args.includes('BatchMode=no'))
    const one = await helper("alice@localhost's password: ")
    assert.equal(one.code, 0, one.stderr); assert.equal(one.stdout.trimEnd(), secret)
    assert.equal(events.length, 1)
    // A repeat in one SSH process means the first answer was rejected.
    assert.equal((await helper("alice@localhost's password: ")).code, 0)
    assert.equal(events.length, 2); assert.equal(events[1].retry, true)
    const next = auth.invocation([])
    assert.equal((await run(next.env.SSH_ASKPASS, ["alice@localhost's password: "], { env: next.env, cwd: next.cwd })).stdout.trimEnd(), secret)
    assert.equal(events.length, 2)
    assert.equal((await run(next.env.SSH_ASKPASS, ["bob@localhost's password: "], { env: next.env, cwd: next.cwd })).code, 0)
    assert.equal(events.length, 3, 'different identity must prompt separately')
    for (const prompt of ['Are you sure you want to continue connecting (yes/no)?', 'Enter passphrase for key:', 'Password:', 'Verification code:']) {
      assert.notEqual((await helper(prompt)).code, 0)
    }
    assert.equal(events.length, 3)
    assert(!auth.submit(events[0].challengeId, 'stale'))
    const forbidden = await fetch(`http://127.0.0.1:${first.env.CANNBOT_ASKPASS_PORT}/`, { method: 'POST', body: '{}' })
    assert.equal(forbidden.status, 403)
  } finally { await auth.dispose() }
  assert.equal(existsSync(resolve(first.cwd || '.', first.env.SSH_ASKPASS)), false)
  assert.notEqual((await helper("alice@localhost's password: ")).code, 0)
})

test('cancelling a pending prompt releases the askpass child and does not accept a late answer', { timeout: 30000 }, async () => {
  const controller = new AbortController()
  let prompted, challenge
  const ready = new Promise(resolve => { prompted = resolve })
  const auth = await createPasswordAuth({ signal: controller.signal, onPrompt(event) { challenge = event; prompted() } })
  try {
    const input = auth.invocation([])
    const child = run(input.env.SSH_ASKPASS, ["user@localhost's password: "], { env: input.env, cwd: input.cwd })
    await Promise.race([ready, child.then(() => { throw new Error('askpass exited before prompting') })]); controller.abort()
    assert.notEqual((await child).code, 0)
    assert.equal(auth.submit(challenge.challengeId, 'too-late'), false)
  } finally { await auth.dispose() }
})

test('password prompt times out without hanging the connection', async () => {
  const auth = await createPasswordAuth({ timeoutMs: 25, onPrompt() {} })
  try {
    const input = auth.invocation([])
    assert.notEqual((await run(input.env.SSH_ASKPASS, ["user@localhost's password: "], { env: input.env, cwd: input.cwd })).code, 0)
  } finally { await auth.dispose() }
})
