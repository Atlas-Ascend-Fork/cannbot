// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

// Version policy for "reuse the remote dsh if it is compatible, otherwise install".
//
// We deliberately keep this tiny and dependency-free: the remote side reports
// `dsh --version`, and we only need range membership, not full semver specs.
// Parse rules: optional leading `v`, `major.minor.patch`, optional `-prerelease`.
// A prerelease sorts BEFORE its release (so 0.3.0-rc.1 < 0.3.0).

export function parseVersion(text) {
  if (typeof text !== 'string') return null
  const match = /^\s*v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?/.exec(text.trim())
  if (!match) return null
  return {
    major: Number(match[1]),
    minor: Number(match[2]),
    patch: Number(match[3]),
    prerelease: match[4] ? match[4].split('.') : [],
  }
}

function comparePrerelease(a, b) {
  if (a.length === 0 && b.length === 0) return 0
  if (a.length === 0) return 1 // release > prerelease
  if (b.length === 0) return -1
  const length = Math.max(a.length, b.length)
  for (let index = 0; index < length; index += 1) {
    const left = a[index]
    const right = b[index]
    if (left === undefined) return -1
    if (right === undefined) return 1
    const leftNumber = /^\d+$/.test(left)
    const rightNumber = /^\d+$/.test(right)
    if (leftNumber && rightNumber) {
      const delta = Number(left) - Number(right)
      if (delta !== 0) return delta < 0 ? -1 : 1
      continue
    }
    if (leftNumber !== rightNumber) return leftNumber ? -1 : 1
    if (left !== right) return left < right ? -1 : 1
  }
  return 0
}

/** -1 | 0 | 1, or null when either side is unparsable. */
export function compareVersions(a, b) {
  const left = typeof a === 'string' ? parseVersion(a) : a
  const right = typeof b === 'string' ? parseVersion(b) : b
  if (!left || !right) return null
  for (const key of ['major', 'minor', 'patch']) {
    if (left[key] !== right[key]) return left[key] < right[key] ? -1 : 1
  }
  return comparePrerelease(left.prerelease, right.prerelease)
}

export const DEFAULT_DSH_RANGE = { min: '0.1.1-rc.1', max: '0.3.0' }

/** min <= version < max */
export function satisfiesRange(version, range = DEFAULT_DSH_RANGE) {
  if (!version) return false
  const lower = compareVersions(version, range.min)
  const upper = compareVersions(version, range.max)
  if (lower === null || upper === null) return false
  return lower >= 0 && upper < 0
}

/**
 * Decide what to do with the remote dsh installation.
 *
 * @param {{existing?: string, pinned?: string, range?: {min: string, max: string}}} input
 * @returns {{version: string, action: 'reuse'|'install'|'install-latest', reason: string}}
 *   `version: ''` means "do not touch the installed dsh".
 */
export function decideDshVersion({ existing = '', pinned = '', range = DEFAULT_DSH_RANGE } = {}) {
  const current = (existing || '').trim()
  const target = (pinned || '').trim()

  if (current && satisfiesRange(current, range)) {
    return { version: '', action: 'reuse', reason: `远端 dsh ${current} 在兼容范围 ${range.min} ~ <${range.max} 内，直接复用` }
  }
  if (target) {
    const reason = current
      ? `远端 dsh ${current} 不在兼容范围 ${range.min} ~ <${range.max} 内，安装 ${target}`
      : `远端未安装 dsh，安装 ${target}`
    return { version: target, action: 'install', reason }
  }
  return {
    version: 'latest',
    action: 'install-latest',
    reason: current ? `远端 dsh ${current} 不在兼容范围，安装最新版` : '远端未安装 dsh，安装最新版',
  }
}

/**
 * Decide whether the CANNBot plugin needs installing.
 *
 * @param {{existing?: string, desired?: string}} input
 * @returns {{version: string, action: 'reuse'|'install'|'skip', reason: string}}
 */
export function decidePluginVersion({ existing = '', desired = '' } = {}) {
  const current = (existing || '').trim()
  const target = (desired || '').trim()
  if (current && (!target || current === target)) {
    return { version: '', action: 'reuse', reason: `已检测到预装的 CANNBot 服务器版 ${current}，即将核对构建标识` }
  }
  if (target) {
    return {
      version: target,
      action: 'install',
      reason: current ? `已预装服务器版 ${current}，将检查配套版本 ${target}` : `正在检查配套的 CANNBot 服务器版 ${target}`,
    }
  }
  return { version: '', action: 'skip', reason: '未配置插件版本，保持现状' }
}
