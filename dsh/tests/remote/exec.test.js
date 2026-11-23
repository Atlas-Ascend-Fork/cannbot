// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { test } from 'node:test'
import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { run } from '../../src/remote/exec.js'

const privateMarker = 'PRIVATE_STDIN_TEST_ONLY_321cb8'
const largeInput = Buffer.alloc(8 * 1024 * 1024, privateMarker)

test('abort stops a running child promptly and a pre-aborted call never spawns', async () => {
  const controller = new AbortController()
  const task = run(process.execPath, ['-e', 'console.log("ready");setInterval(()=>{},1000)'], {
    signal: controller.signal, timeoutMs: 10000, onLine() { controller.abort() },
  })
  const result = await task
  assert.equal(result.code, -3); assert.equal(result.timedOut, false)
  const skipped = await run('must-never-exist', [], { signal: controller.signal })
  assert.equal(skipped.code, -3)
})

test('an early stdin close with a large private payload does not crash the host or leak the payload', async () => {
  const events = []
  const result = await run(process.execPath, ['-e', `
    require('node:fs').closeSync(0);
    process.stderr.write('remote rejected input\\n');
    setTimeout(() => process.exit(23), 50);
  `], { input: largeInput, timeoutMs: 5000, onLine: line => events.push(line) })
  assert.equal(result.code, 23, 'preserve the remote failure exit code')
  assert.equal(result.timedOut, false)
  assert.match(result.stderr, /stdin write failed/)
  assert.match(result.stderr, /remote rejected input/)
  assert.equal(JSON.stringify({ result, events }).includes(privateMarker), false)
})

test('a zero child exit after an incomplete stdin transfer is still a failure', async () => {
  const result = await run(process.execPath, ['-e', `
    require('node:fs').closeSync(0);
    setTimeout(() => process.exit(0), 50);
  `], { input: largeInput, timeoutMs: 5000 })
  assert.equal(result.code, -1)
  assert.equal(result.timedOut, false)
  assert.match(result.stderr, /stdin write failed/)
  assert.equal(JSON.stringify(result).includes(privateMarker), false)
})

test('successful stdin delivery preserves all bytes without logging the input', async () => {
  const input = Buffer.from(`${privateMarker}\r\n中文\0literal $(not-a-command) ' "\\`, 'utf8')
  const expected = createHash('sha256').update(input).digest('hex')
  const result = await run(process.execPath, ['-e', `
    const hash = require('node:crypto').createHash('sha256');
    process.stdin.on('data', chunk => hash.update(chunk));
    process.stdin.on('end', () => process.stdout.write(hash.digest('hex')));
  `], { input, timeoutMs: 5000 })
  assert.equal(result.code, 0)
  assert.equal(result.stdout, expected)
  assert.equal(result.stderr, '')
  assert.equal(result.timedOut, false)
})

test('ordinary SSH-like failures retain their exit code and diagnostics', async () => {
  const result = await run(process.execPath, ['-e', `
    process.stderr.write('Permission denied');
    process.exit(255);
  `], { timeoutMs: 5000 })
  assert.equal(result.code, 255)
  assert.match(result.stderr, /Permission denied/)
  assert.equal(result.timedOut, false)
})

test('a peer that neither consumes stdin nor exits is still bounded by the timeout', async () => {
  const result = await run(process.execPath, ['-e', 'setInterval(() => {}, 1000)'], {
    input: largeInput, timeoutMs: 150,
  })
  assert.equal(result.code, -2)
  assert.equal(result.timedOut, true)
  assert.equal(JSON.stringify(result).includes(privateMarker), false)
})

test('the existing terminal-marker onLine stop keeps its successful result', async () => {
  const result = await run(process.execPath, ['-e', `
    process.stdout.write('CANNBOT_OK=1\\n');
    setInterval(() => {}, 1000);
  `], {
    input: largeInput, timeoutMs: 5000,
    onLine: line => line === 'CANNBOT_OK=1' ? 'stop' : undefined,
  })
  assert.equal(result.code, 0)
  assert.equal(result.timedOut, false)
  assert.match(result.stdout, /CANNBOT_OK=1/)
  assert.equal(JSON.stringify(result).includes(privateMarker), false)
})
