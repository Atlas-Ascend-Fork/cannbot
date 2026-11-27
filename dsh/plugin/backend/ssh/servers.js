// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

// Server inventory: the shared team list merged with this machine's ssh config,
// plus persisted per-connection runtime state (ports, tokens).
import { readFileSync, writeFileSync, existsSync } from 'node:fs'
import { ensureParent } from './paths.js'

export const DEFAULT_LOCAL_PORT = 17633
export const DEFAULT_REMOTE_PORT = 17633

/** @returns {{version: number, servers: any[]}} */
export function emptyInventory() {
  return { version: 1, servers: [] }
}

export function normalizeServer(raw) {
  if (!raw || typeof raw !== 'object') return null
  const alias = typeof raw.alias === 'string' ? raw.alias.trim() : ''
  if (!alias) return null
  return {
    alias,
    label: typeof raw.label === 'string' && raw.label.trim() ? raw.label.trim() : alias,
    group: typeof raw.group === 'string' ? raw.group : 'default',
    remotePort: Number.isInteger(raw.remotePort) ? raw.remotePort : null,
    dshVersion: typeof raw.dshVersion === 'string' ? raw.dshVersion : '',
    pluginVersion: typeof raw.pluginVersion === 'string' ? raw.pluginVersion : '',
    note: typeof raw.note === 'string' ? raw.note : '',
  }
}

export function normalizeInventory(json) {
  const servers = Array.isArray(json && json.servers) ? json.servers.map(normalizeServer).filter(Boolean) : []
  const deduped = new Map()
  for (const server of servers) deduped.set(server.alias.toLowerCase(), server)
  const aliases = value => [...new Set(value.filter(item => typeof item === 'string' && item.trim() && item.length <= 512 && !/[\x00-\x1f\x7f]/.test(item)).map(item => item.trim().toLowerCase()))]
  return { version: 1, servers: [...deduped.values()],
    ...(Array.isArray(json?.order) && { order: aliases(json.order) }),
    ...(Array.isArray(json?.hiddenAliases) && { hiddenAliases: aliases(json.hiddenAliases) }),
  }
}

export function loadInventory(file) {
  if (!existsSync(file)) return null
  try {
    return normalizeInventory(JSON.parse(readFileSync(file, 'utf8')))
  } catch {
    return null
  }
}

export function saveInventory(file, inventory) {
  ensureParent(file)
  const normalized = normalizeInventory(inventory)
  writeFileSync(file, `${JSON.stringify(normalized, null, 2)}\n`, 'utf8')
  return normalized
}

/**
 * Merge the shared inventory with aliases discovered in ~/.ssh/config.
 * Shared entries win on metadata; ssh-config-only aliases are added as
 * "discovered" so a user can connect to anything already in their config.
 *
 * @param {{shared?: {servers: any[]}, sshAliases?: string[], sshResolved?: any[]}} input
 */
export function mergeInventory({ shared, sshAliases = [], sshResolved = [] }) {
  const byAlias = new Map()
  const hidden = new Set((shared?.hiddenAliases || []).map(alias => alias.toLowerCase()))
  const resolvedByAlias = new Map(sshResolved.map((entry) => [entry.alias.toLowerCase(), entry]))

  for (const alias of sshAliases) {
    if (hidden.has(alias.toLowerCase())) continue
    const resolved = resolvedByAlias.get(alias.toLowerCase()) || {}
    byAlias.set(alias.toLowerCase(), {
      id: alias,
      alias,
      label: alias,
      group: 'ssh-config',
      source: 'ssh-config',
      inSshConfig: true,
      hostName: resolved.hostName || alias,
      user: resolved.user || '',
      port: resolved.port || 22,
      proxyJump: resolved.proxyJump || '',
    })
  }

  for (const server of (shared && shared.servers) || []) {
    const key = server.alias.toLowerCase()
    if (hidden.has(key)) continue
    const existing = byAlias.get(key)
    const resolved = resolvedByAlias.get(key) || {}
    byAlias.set(key, {
      ...(existing || {}),
      ...server,
      id: server.alias,
      source: 'shared',
      inSshConfig: Boolean(existing),
      hostName: resolved.hostName || server.alias,
      user: resolved.user || '',
      port: resolved.port || 22,
      proxyJump: resolved.proxyJump || '',
    })
  }

  const order = new Map((shared?.order || []).map((alias, index) => [alias.toLowerCase(), index]))
  const servers = [...byAlias.values()].sort((a, b) => {
    const position = (order.get(a.alias.toLowerCase()) ?? Infinity) - (order.get(b.alias.toLowerCase()) ?? Infinity)
    if (position && !Number.isNaN(position)) return position
    if (a.source !== b.source) return a.source === 'shared' ? -1 : 1
    return a.label.localeCompare(b.label, 'zh-Hans-CN')
  })
  return { version: 1, servers }
}

/** Pick the first free local port starting at `start`. */
export function allocateLocalPort({ used = [], start = DEFAULT_LOCAL_PORT, max = start + 200 } = {}) {
  const taken = new Set(used.map((port) => Number(port)).filter((port) => Number.isInteger(port)))
  for (let port = start; port <= max; port += 1) {
    if (!taken.has(port)) return port
  }
  return start
}

export function loadState(file) {
  if (!existsSync(file)) return { version: 1, connections: {} }
  try {
    const json = JSON.parse(readFileSync(file, 'utf8'))
    if (!json || typeof json !== 'object' || typeof json.connections !== 'object') {
      return { version: 1, connections: {} }
    }
    return { version: 1, connections: json.connections }
  } catch {
    return { version: 1, connections: {} }
  }
}

export function saveState(file, state) {
  ensureParent(file)
  writeFileSync(file, `${JSON.stringify({ version: 1, connections: state.connections || {} }, null, 2)}\n`, 'utf8')
}
