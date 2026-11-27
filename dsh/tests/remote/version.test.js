// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  compareVersions,
  decideDshVersion,
  decidePluginVersion,
  parseVersion,
  satisfiesRange,
} from '../../plugin/backend/ssh/version.js'

test('parseVersion accepts v-prefix and prerelease suffixes', () => {
  assert.deepEqual(parseVersion('0.2.2-rc.1'), { major: 0, minor: 2, patch: 2, prerelease: ['rc', '1'] })
  assert.deepEqual(parseVersion('v1.2.3'), { major: 1, minor: 2, patch: 3, prerelease: [] })
  assert.equal(parseVersion('dsh 0.2.2'), null)
  assert.equal(parseVersion(''), null)
})

test('compareVersions orders releases and prereleases', () => {
  assert.equal(compareVersions('0.2.1', '0.2.2'), -1)
  assert.equal(compareVersions('0.2.2', '0.2.2'), 0)
  assert.equal(compareVersions('0.3.0', '0.2.9'), 1)
  assert.equal(compareVersions('0.3.0-rc.1', '0.3.0'), -1, 'prerelease sorts before release')
  assert.equal(compareVersions('0.2.2-rc.2', '0.2.2-rc.10'), -1, 'numeric prerelease segments compare numerically')
  assert.equal(compareVersions('nonsense', '0.1.0'), null)
})

test('satisfiesRange matches the CANNBot plugin window', () => {
  assert.equal(satisfiesRange('0.1.1-rc.1'), true, 'inclusive lower bound')
  assert.equal(satisfiesRange('0.2.1-rc.5'), true)
  assert.equal(satisfiesRange('0.2.2-rc.1'), true)
  assert.equal(satisfiesRange('0.3.0-rc.1'), true, 'still below the exclusive upper bound')
  assert.equal(satisfiesRange('0.3.0'), false, 'exclusive upper bound')
  assert.equal(satisfiesRange('0.1.0'), false)
  assert.equal(satisfiesRange(''), false)
})

test('decideDshVersion reuses a compatible install and pins otherwise', () => {
  const reuse = decideDshVersion({ existing: '0.2.2-rc.1', pinned: '0.2.2-rc.1' })
  assert.equal(reuse.action, 'reuse')
  assert.equal(reuse.version, '', 'empty version means "do not touch the remote install"')
  assert.match(reuse.reason, /复用/)

  const upgrade = decideDshVersion({ existing: '0.0.9', pinned: '0.2.2-rc.1' })
  assert.equal(upgrade.action, 'install')
  assert.equal(upgrade.version, '0.2.2-rc.1')
  assert.match(upgrade.reason, /不在兼容范围/)

  const fresh = decideDshVersion({ existing: '', pinned: '0.2.2-rc.1' })
  assert.equal(fresh.action, 'install')
  assert.match(fresh.reason, /未安装/)

  const latest = decideDshVersion({ existing: '0.1.0', pinned: '' })
  assert.equal(latest.action, 'install-latest')
  assert.equal(latest.version, 'latest')
})

test('decideDshVersion honours a custom range', () => {
  const decision = decideDshVersion({
    existing: '0.9.9',
    pinned: '0.1.2',
    range: { min: '0.0.1', max: '0.1.0' },
  })
  assert.equal(decision.action, 'install')
  assert.equal(decision.version, '0.1.2')

  const inside = decideDshVersion({
    existing: '0.0.5',
    pinned: '0.1.2',
    range: { min: '0.0.1', max: '0.1.0' },
  })
  assert.equal(inside.action, 'reuse')
})

test('decidePluginVersion reuses an exact match and reinstalls on drift', () => {
  const reuse = decidePluginVersion({ existing: '1.0.0-alpha.1', desired: '1.0.0-alpha.1' })
  assert.equal(reuse.action, 'reuse')
  assert.equal(reuse.version, '')

  const drift = decidePluginVersion({ existing: '0.9.0', desired: '1.0.0-alpha.1' })
  assert.equal(drift.action, 'install')
  assert.equal(drift.version, '1.0.0-alpha.1')

  const fresh = decidePluginVersion({ existing: '', desired: '1.0.0-alpha.1' })
  assert.equal(fresh.action, 'install')

  const unpinnedInstalled = decidePluginVersion({ existing: '1.0.0-alpha.1', desired: '' })
  assert.equal(unpinnedInstalled.action, 'reuse')

  const unpinnedMissing = decidePluginVersion({ existing: '', desired: '' })
  assert.equal(unpinnedMissing.action, 'skip')
})
