// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import test from 'node:test'
import assert from 'node:assert/strict'
import { PassThrough } from 'node:stream'
import { randomUUID } from 'node:crypto'
import { InitializationJobs, initializationIO, runInitializationTerminal } from '../src/initialization-jobs.ts'
import { initializationRequest } from '../src/initialization-contract.ts'
import { validateReleasePolicy } from '../scripts/release-policy.mjs'
import { readFileSync } from 'node:fs'

const status = jobId => ({ action: 'initialization-status', jobId, offset: 0 })
const turn = () => new Promise(done => setImmediate(done))
test('interactive jobs deduplicate starts and input, preserve output and only finish after the questionnaire', async () => {
  let finish, runs = 0; const answers = []
  const jobs = new InitializationJobs(async () => { runs++; const io = initializationIO.getStore(); io.output('Choose environment:'); io.input = async text => { answers.push(text) }; await new Promise(resolve => { finish = resolve }); return { workspace: { workspaceId: 'W' } } })
  const start = { action: 'start-initialization', requestId: randomUUID(), operation: { action: 'switch-workflow', workspaceId: 'W', pluginId: 'general' } }
  const first = await jobs.handle(start), duplicate = await jobs.handle(start)
  assert.equal(first.jobId, duplicate.jobId); assert.equal(runs, 1); assert.equal(first.phase, 'running')
  const input = { action: 'initialization-input', jobId: first.jobId, sequence: 1, data: 'yes\r' }
  await jobs.handle(input); await jobs.handle(input); assert.deepEqual(answers, ['yes\r'])
  finish(); await turn()
  assert.equal((await jobs.handle(status(first.jobId))).phase, 'ready')
  assert.deepEqual((await jobs.handle(status(first.jobId))).result, { workspace: { workspaceId: 'W' } })
  await assert.rejects(jobs.handle({ ...start, operation: { ...start.operation, pluginId: 'other' } }), /变化/)
})
test('terminal cancellation waits for owned process cleanup before job settles', async () => {
  let exit, cleaned = false
  const jobs = new InitializationJobs(async () => runInitializationTerminal(async () => ({
    output: new PassThrough(), done: new Promise(resolve => { exit = resolve }), write: async () => {},
    terminate: async () => { await turn(); cleaned = true; exit({ exitCode: null, signal: 'SIGTERM' }) },
  }), ['node', 'questionnaire'], '/tmp', initializationIO.getStore()))
  const job = await jobs.handle({ action: 'start-initialization', requestId: randomUUID(), operation: { action: 'switch-workflow', workspaceId: 'W', pluginId: 'general' } })
  await turn(); await jobs.handle({ action: 'cancel-initialization', jobId: job.jobId, offset: 0 })
  let value
  for (let n = 0; n < 10; n++) { await turn(); value = await jobs.handle(status(job.jobId)); if (value.phase !== 'running') break }
  assert.equal(value.phase, 'error'); assert.equal(cleaned, true); assert.match(value.message, /取消/)
})
test('initialization requests cannot forward arbitrary commands and public builds require both formal legal URLs', () => {
  assert.equal(initializationRequest({ action: 'start-initialization', requestId: randomUUID(), operation: { action: 'exec', command: 'anything' } }), undefined)
  assert.equal(initializationRequest({ action: 'initialization-input', jobId: randomUUID(), sequence: -1, data: 'bad' }), undefined)
  const policy = JSON.parse(readFileSync(new URL('../release-policy.json', import.meta.url)))
  assert.equal(validateReleasePolicy(policy).channel, 'development')
  assert.throws(() => validateReleasePolicy(policy, true), /userAgreementUrl/)
  assert.throws(() => validateReleasePolicy({ ...policy, userAgreementUrl: 'https://cannbot.test/terms' }, true), /privacyPolicyUrl/)
  assert.equal(validateReleasePolicy({ ...policy, userAgreementUrl: 'https://cannbot.test/terms', privacyPolicyUrl: 'https://cannbot.test/privacy' }, true).channel, 'public')
})
