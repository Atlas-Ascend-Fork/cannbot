// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import test from 'node:test'
import assert from 'node:assert/strict'
import { freezeSessionInputs } from '../plugin/frontend/frozen-sessions.ts'

test('native composer blocks frozen sessions without replacing other extensions or ordinary sessions', () => {
  let sessions = [{ sessionId: 'old', frozen: true }, { sessionId: 'other', frozen: true }, { sessionId: 'normal' }], notify
  const other = { reason: 'Other extension' }, values = new Map([['other', other]])
  const stop = freezeSessionInputs({ getSnapshot: () => ({ sessions }), subscribe: listener => { notify = listener; return () => { notify = undefined } } }, {
    storeFor: id => ({ getSnapshot: () => values.get(id) }), set: (id, value) => value ? values.set(id, value) : values.delete(id),
  })
  assert.match(values.get('old').reason, /冻结/)
  assert.equal(values.get('other'), other)
  assert.equal(values.has('normal'), false)
  sessions = sessions.filter(item => item.sessionId !== 'old'); notify()
  assert.equal(values.has('old'), false)
  stop(); assert.equal(values.get('other'), other); assert.equal(notify, undefined)
})
