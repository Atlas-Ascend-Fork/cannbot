// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { test } from 'node:test'
import assert from 'node:assert/strict'
import { createServer } from 'node:http'
import { spawn } from 'node:child_process'
import { mkdtempSync, readFileSync, writeFileSync, existsSync, readdirSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const installer = fileURLToPath(new URL('../../installers/windows/install-all.ps1', import.meta.url))
const windows = { skip: process.platform !== 'win32' }
async function exercise(t, { unknown = false, cancel = false, broken = false } = {}) {
  const root = mkdtempSync(join(tmpdir(), 'cannbot-download-test-'))
  t.after(() => { assert.equal(dirname(resolve(root)), resolve(tmpdir())); rmSync(root, { recursive: true, force: true }) })
  const target = join(root, '安装包.exe'), state = join(root, 'progress.json')
  const payload = Buffer.alloc(1024 * 1024, 42)
  const states = []
  const server = createServer((request, response) => {
    if (!unknown) response.setHeader('Content-Length', payload.length)
    let offset = 0
    const interval = setInterval(() => {
      if (broken && offset >= payload.length / 2) { response.destroy(); return }
      response.write(payload.subarray(offset, offset + 65536)); offset += 65536
      if (offset >= payload.length) response.end()
    }, 60)
    response.on('close', () => clearInterval(interval))
  })
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
  t.after(() => { server.closeAllConnections(); server.close() })
  const script = String.raw`
$ErrorActionPreference='Stop'
$tokens=$null;$errors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile($env:TEST_INSTALLER,[ref]$tokens,[ref]$errors)
if($errors.Count){throw 'PowerShell parse failure'}
foreach($statement in $ast.EndBlock.Statements){if($statement -is [Management.Automation.Language.FunctionDefinitionAst]){Invoke-Expression $statement.Extent.Text}}
$ProgressPath=$env:TEST_PROGRESS
Receive-Installer $env:TEST_URL $env:TEST_TARGET
`
  const child = spawn('powershell.exe', ['-NoProfile', '-NonInteractive', '-EncodedCommand', Buffer.from(script, 'utf16le').toString('base64')], {
    windowsHide: true, env: { ...process.env, TEST_INSTALLER: installer, TEST_PROGRESS: state, TEST_TARGET: target, TEST_URL: `http://127.0.0.1:${server.address().port}/installer` },
  })
  let output = ''
  child.stdout.on('data', data => { output += data }); child.stderr.on('data', data => { output += data })
  const poll = setInterval(() => {
    try {
      const value = JSON.parse(readFileSync(state, 'utf8')); states.push(value)
      if (cancel && value.received > 0) writeFileSync(state + '.cancel', 'cancel')
    } catch {}
  }, 20)
  const deadline = setTimeout(() => child.kill(), 15000)
  let code
  try { code = await new Promise((resolve, reject) => { child.on('error', reject); child.on('exit', resolve) }) }
  finally { clearInterval(poll); clearTimeout(deadline) }
  const final = JSON.parse(readFileSync(state, 'utf8'))
  assert.ok(states.some(value => value.received > 0 && value.received < payload.length), 'live byte progress before completion')
  assert.ok(states.some(value => value.speed > 0), 'measured download speed')
  assert.equal(readdirSync(root).some(file => file.endsWith('.partial')), false, 'partial files cleaned')
  if (cancel || broken) {
    assert.notEqual(code, 0, output)
    assert.equal(existsSync(target), false, 'failed download never becomes an installer')
  } else {
    assert.equal(code, 0, output)
    assert.deepEqual(readFileSync(target), payload)
    assert.equal(final.received, payload.length)
    assert.equal(final.total, payload.length)
    if (unknown) assert.ok(states.some(value => value.total < 0), 'unknown length does not invent a percentage')
  }
}
test('download exposes live measured bytes and speed, then publishes the complete file', windows, t => exercise(t))
test('chunked download reports bytes without a fabricated percentage', windows, t => exercise(t, { unknown: true }))
test('cancelled download returns failure and removes partial files', windows, t => exercise(t, { cancel: true }))
test('truncated download never publishes a reusable installer', windows, t => exercise(t, { broken: true }))
