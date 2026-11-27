// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

// OpenSSH config discovery + resolution.
//
// Design decision (see docs/design.md): we never implement SSH itself. The local
// OpenSSH client owns Host/User/Port/IdentityFile/ProxyJump/Include/Match, and we
// only (a) list candidate aliases from ~/.ssh/config and (b) ask `ssh -G` for the
// effective values when we need to display them.
import { readFileSync, existsSync, readdirSync } from 'node:fs'
import { isAbsolute, join, dirname } from 'node:path'
import { homedir } from 'node:os'

const TOKEN = /^(?<key>[A-Za-z][A-Za-z0-9]*)\s*(?:=\s*)?(?<value>.*)$/

/**
 * Pure parser for ssh_config text. Returns blocks in file order.
 * @param {string} text
 * @returns {{aliases: string[], options: Record<string, string>, source: string}[]}
 */
export function parseSshConfig(text, source = '') {
  const blocks = []
  let current = null
  // Directives before the first `Host` line are global (this is where a
  // top-level `Include` usually lives), so they get their own alias-less block.
  const ensureBlock = () => {
    if (current) return current
    current = { aliases: [], options: source ? { source } : {} }
    blocks.push(current)
    return current
  }
  for (const rawLine of String(text).split(/\r?\n/)) {
    const line = rawLine.trim()
    if (!line || line.startsWith('#')) continue
    const match = TOKEN.exec(line)
    if (!match) continue
    const key = match.groups.key.toLowerCase()
    const value = match.groups.value.trim()
    if (key === 'host') {
      current = { aliases: value.split(/\s+/).filter(Boolean), options: source ? { source } : {} }
      blocks.push(current)
      continue
    }
    const block = ensureBlock()
    if (key === 'include') {
      block.options.include = block.options.include ? `${block.options.include} ${value}` : value
      continue
    }
    if (!(key in block.options)) block.options[key] = value
  }
  return blocks
}

/** Concrete (non-wildcard) aliases in declaration order, de-duplicated. */
export function concreteAliases(blocks) {
  const seen = new Set()
  const out = []
  for (const block of blocks) {
    for (const alias of block.aliases) {
      if (alias === '*' || alias.includes('*') || alias.includes('?')) continue
      const key = alias.toLowerCase()
      if (seen.has(key)) continue
      seen.add(key)
      out.push(alias)
    }
  }
  return out
}

/** Effective per-alias options with OpenSSH "first match wins" semantics. */
export function resolveFromBlocks(blocks) {
  const result = new Map()
  for (const block of blocks) {
    for (const alias of block.aliases) {
      if (alias === '*' || alias.includes('*') || alias.includes('?')) continue
      const key = alias.toLowerCase()
      if (!result.has(key)) {
        result.set(key, { alias, options: {} })
      }
      const entry = result.get(key)
      for (const [option, value] of Object.entries(block.options)) {
        if (option === 'source') continue
        if (!(option in entry.options)) entry.options[option] = value
      }
    }
  }
  return [...result.values()].map((entry) => ({
    alias: entry.alias,
    hostName: entry.options.hostname || entry.alias,
    user: entry.options.user || '',
    port: entry.options.port ? Number(entry.options.port) : 22,
    identityFile: entry.options.identityfile || '',
    proxyJump: entry.options.proxyjump || '',
  }))
}

/** Expand a leading ~ and read one config file, following `Include` one level. */
export function readConfigTree(configPath) {
  const files = []
  const seen = new Set()
  const queue = [configPath]
  while (queue.length) {
    const file = queue.shift()
    const resolved = file.startsWith('~') ? join(homedir(), file.slice(1)) : file
    const absolute = isAbsolute(resolved) ? resolved : join(dirname(configPath), resolved)
    if (seen.has(absolute.toLowerCase())) continue
    seen.add(absolute.toLowerCase())
    if (!existsSync(absolute)) continue
    let text = ''
    try {
      text = readFileSync(absolute, 'utf8')
    } catch {
      continue
    }
    files.push({ path: absolute, text })
    for (const block of parseSshConfig(text, absolute)) {
      const included = block.options.include
      if (!included) continue
      for (const pattern of included.split(/\s+/)) {
        if (!pattern) continue
        for (const candidate of expandInclude(pattern, absolute)) queue.push(candidate)
      }
    }
  }
  return files
}

/** Minimal glob support: only `*` in the final path segment, one directory level. */
function expandInclude(pattern, baseFile) {
  const target = pattern.startsWith('~') ? join(homedir(), pattern.slice(1)) : pattern
  const absolute = isAbsolute(target) ? target : join(dirname(baseFile), target)
  if (!absolute.includes('*')) return [absolute]
  const dir = dirname(absolute)
  const base = absolute.slice(dir.length + 1)
  const regex = new RegExp(`^${base.split('*').map(escapeRegExp).join('.*')}$`, 'i')
  try {
    return readdirSync(dir)
      .filter((name) => regex.test(name))
      .map((name) => join(dir, name))
  } catch {
    return []
  }
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/**
 * Parse `ssh -G <alias>` output into the fields we display.
 * @param {string} text
 */
export function parseSshG(text) {
  const map = {}
  for (const rawLine of String(text).split(/\r?\n/)) {
    const line = rawLine.trim()
    if (!line) continue
    const match = TOKEN.exec(line)
    if (!match) continue
    const key = match.groups.key.toLowerCase()
    const value = match.groups.value.trim()
    if (key === 'identityfile') {
      if (!map.identityfile) map.identityfile = []
      map.identityfile.push(value)
      continue
    }
    if (!(key in map)) map[key] = value
  }
  return {
    hostName: map.hostname || '',
    user: map.user || '',
    port: map.port ? Number(map.port) : 22,
    identityFile: map.identityfile || [],
    proxyJump: map.proxyjump && map.proxyjump !== 'none' ? map.proxyjump : '',
  }
}

/** List aliases available on this machine (pure file read, no spawning). */
export function listAliases(configPath) {
  const files = readConfigTree(configPath)
  const blocks = []
  for (const file of files) blocks.push(...parseSshConfig(file.text, file.path))
  return { aliases: concreteAliases(blocks), resolved: resolveFromBlocks(blocks), files: files.map((f) => f.path) }
}
