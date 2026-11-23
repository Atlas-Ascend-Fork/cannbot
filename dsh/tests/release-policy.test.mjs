// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import test from 'node:test'
import assert from 'node:assert/strict'
import { readReleasePolicy, validateReleasePolicy } from '../scripts/release-policy.mjs'

test('development policy exposes unconfigured legal links but cannot become a public package', async () => {
  const policy = await readReleasePolicy(new URL('../release-policy.json', import.meta.url))
  assert.equal(policy.channel, 'development')
  assert.throws(() => validateReleasePolicy({ ...policy, userAgreementUrl: '', privacyPolicyUrl: '' }, true), /requires/)
  assert.throws(() => validateReleasePolicy({ ...policy, channel: 'public', userAgreementUrl: '' }), /requires/)
  const configured = { ...policy, userAgreementUrl: 'https://cannbot.test/legal/terms', privacyPolicyUrl: 'https://cannbot.test/legal/privacy' }
  assert.equal(validateReleasePolicy(configured, true).channel, 'public')
  for (const link of ['http://cannbot.test/terms', 'https://user:secret@cannbot.test/terms', 'https://example.com/terms', 'https://localhost/terms']) {
    assert.throws(() => validateReleasePolicy({ ...configured, userAgreementUrl: link }, true), /Invalid/)
  }
})
