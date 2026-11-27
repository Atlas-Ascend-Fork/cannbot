// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import test from 'node:test'
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { once } from 'node:events'
import { mkdtempSync, rmSync, writeFileSync, existsSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { acquireFileLock } from '../packages/install/lib/file-lock.mjs'
import { runProcess } from '../plugin/backend/process-runner.mjs'

test('exclusive locks serialize contenders and release after owner crashes', async () => {
  const directory = mkdtempSync(join(tmpdir(), 'cannbot-lock-test-')), path = join(directory, 'lock')
  const module = new URL('../packages/install/lib/file-lock.mjs', import.meta.url).href
  const child = spawn(process.execPath, ['--input-type=module', '-e', `import {acquireFileLock} from ${JSON.stringify(module)};await acquireFileLock(process.argv[1]);process.send('locked');setInterval(()=>{},1000)`, path], { stdio: ['ignore', 'pipe', 'pipe', 'ipc'] })
  try {
    await once(child, 'message')
    await assert.rejects(acquireFileLock(path), /still running/)
    const exited = once(child, 'exit'); child.kill('SIGKILL'); await exited
    let active = 0, peak = 0
    await Promise.all(Array.from({ length: 4 }, async () => {
      const release = await acquireFileLock(path, 5000)
      try { peak = Math.max(peak, ++active); await new Promise(resolve => setTimeout(resolve, 30)); active-- }
      finally { release() }
    }))
    assert.equal(peak, 1)
    // Legacy truncated JSON locks cannot block the new kernel-managed lock.
    writeFileSync(path, '{')
    const release = await acquireFileLock(path); release(); release()
  } finally { child.kill('SIGKILL'); rmSync(directory, { recursive: true, force: true }) }
})

test('timeout kills a child that ignores SIGTERM', async () => {
  const start = Date.now()
  let ready = false
  await assert.rejects(runProcess(process.execPath, ['-e', "process.on('SIGTERM',()=>{});console.log('ready');setInterval(()=>{},1000)"], {
    timeoutMs: 500, graceMs: 100, stdio: ['ignore', 'pipe', 'pipe'], onData: () => { ready = true },
  }), /timed out/)
  assert.equal(ready, true)
  assert.ok(Date.now() - start < 5000)
})

test('handled interruption cleans staging after terminating child', { timeout: 10_000 }, async () => {
  const module = new URL('../tools/staging.mjs', import.meta.url).href
  const runner = new URL('../plugin/backend/process-runner.mjs', import.meta.url).href
  const child = spawn(process.execPath, ['--input-type=module', '-e', `import {withStaging} from ${JSON.stringify(module)};import {runProcess} from ${JSON.stringify(runner)};process.on('message',()=>process.emit('SIGTERM'));await withStaging('cannbot-signal-test-',async(dir,signal)=>{process.send(dir);await runProcess(process.execPath,['-e','setInterval(()=>{},1000)'],{signal,stdio:'ignore'})}).catch(()=>{});process.disconnect();`], { stdio: ['ignore', 'pipe', 'pipe', 'ipc'], windowsHide: true })
  try {
    const [directory] = await once(child, 'message')
    const exited = once(child, 'exit')
    // Node's child.kill('SIGTERM') forcibly terminates Windows processes without
    // delivering a JS signal. IPC exercises the same installed handler there.
    if (process.platform === 'win32') child.send('terminate')
    else child.kill('SIGTERM')
    await exited
    assert.equal(existsSync(directory), false)
  } finally { if (child.exitCode === null && child.signalCode === null) child.kill('SIGKILL') }
})

test('abort terminates the owned process tree before runProcess rejects', { timeout: 10_000 }, async () => {
  const controller = new AbortController()
  let descendant, output = ''
  const script = `const {spawn}=require('node:child_process');const child=spawn(process.execPath,['-e','setInterval(()=>{},1000)'],{stdio:'ignore',windowsHide:true});console.log(child.pid);setInterval(()=>{},1000)`
  try {
    await assert.rejects(runProcess(process.execPath, ['-e', script], {
      signal: controller.signal, timeoutMs: 5000, graceMs: 100,
      stdio: ['ignore', 'pipe', 'pipe'], onData: chunk => {
        output += chunk
        if (!descendant && /^\d+\r?\n/.test(output)) { descendant = Number(output.trim()); controller.abort(new Error('cancelled by test')) }
      },
    }), /cancelled by test/)
    assert(Number.isInteger(descendant))
    assert.throws(() => process.kill(descendant, 0), error => error.code === 'ESRCH')
  } finally { if (descendant) { try { process.kill(descendant, 'SIGKILL') } catch {} } }
})
