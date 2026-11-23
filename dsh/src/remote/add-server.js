// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

// Accept connection data, never an executable shell command. Existing OpenSSH
// configuration is authoritative; new connections only append a separate Host.
import { createHash } from 'node:crypto'
import { isIP } from 'node:net'
import { dirname, isAbsolute } from 'node:path'
import { appendFileSync, closeSync, existsSync, mkdirSync, openSync, readFileSync, renameSync, statSync, unlinkSync, writeFileSync } from 'node:fs'
import { listAliases, parseSshConfig, readConfigTree } from './ssh-config.js'
import { mergeInventory, normalizeInventory } from './servers.js'

export class ServerInputError extends Error {
  constructor(message, status = 400) { super(message); this.name = 'ServerInputError'; this.status = status }
}
const invalid = () => new ServerInputError('请输入已有 SSH 别名，或 ssh 用户@主机；仅支持 -p、-l、-i 和 -J 参数，不支持远程命令。')
const aliasPattern = /^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$/
const userPattern = /^[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}$/

/** Small quoted-token grammar; no shell expansion, escaping or execution. */
function tokens(command) {
  if (typeof command !== 'string' || !command.trim() || command.length > 4096 || /[\x00-\x08\x0a-\x1f\x7f;&|`$<>]/.test(command)) throw invalid()
  const result = []
  let value = '', quote = '', started = false
  for (const char of command.trim()) {
    if (quote) { if (char === quote) quote = ''; else value += char; started = true; continue }
    if (char === '"' || char === "'") { quote = char; started = true; continue }
    if (/\s/.test(char)) { if (started) { result.push(value); value = ''; started = false }; continue }
    value += char; started = true
  }
  if (quote) throw invalid()
  if (started) result.push(value)
  if (result.some(value => !value)) throw invalid()
  return result
}

function hostName(value) {
  const host = value.startsWith('[') && value.endsWith(']') ? value.slice(1, -1) : value
  if (isIP(host)) return host.toLowerCase()
  if (host.length <= 253 && /^[A-Za-z0-9](?:[A-Za-z0-9_.-]*[A-Za-z0-9.]|)$/.test(host)) return host.toLowerCase()
  throw invalid()
}

/** Parse only flags which can be represented as inert OpenSSH configuration. */
export function parseServerCommand(command) {
  const args = tokens(command)
  const explicitSsh = /^(?:ssh|ssh\.exe)$/i.test(args[0])
  if (explicitSsh) args.shift()
  else {
    if (args.length !== 1 || !aliasPattern.test(args[0])) throw invalid()
    return { existingAlias: args[0] }
  }
  let destination = ''
  const values = {}
  for (let index = 0; index < args.length; index++) {
    const arg = args[index]
    if (arg.startsWith('-')) {
      const option = arg.slice(0, 2)
      if (!['-p', '-l', '-i', '-J'].includes(option) || Object.hasOwn(values, option)) throw invalid()
      const value = arg.length > 2 ? arg.slice(2) : args[++index]
      if (!value || value.startsWith('-')) throw invalid()
      values[option] = value
    } else {
      if (destination) throw invalid()
      destination = arg
    }
  }
  if (!destination) throw invalid()
  const parts = destination.split('@')
  if (parts.length > 2 || parts.some(value => !value)) throw invalid()
  const user = parts.length === 2 ? parts[0] : values['-l'] || ''
  if ((parts.length === 2 && values['-l']) || (user && !userPattern.test(user))) throw invalid()
  const host = hostName(parts.at(-1))
  const port = values['-p'] === undefined ? undefined : Number(values['-p'])
  if (port !== undefined && (!/^\d{1,5}$/.test(values['-p']) || !Number.isInteger(port) || port < 1 || port > 65535)) throw invalid()
  let identityFile = values['-i'] || ''
  if (identityFile) {
    if (identityFile.length > 2048 || /["'\x00-\x1f\x7f%#]/.test(identityFile)
      || !(isAbsolute(identityFile) || /^[A-Za-z]:[\\/]/.test(identityFile) || /^~[\\/]/.test(identityFile))) {
      throw new ServerInputError('私钥请使用绝对路径或 ~/.ssh 路径，路径中不能包含引号、控制字符或 SSH 占位符。')
    }
    identityFile = identityFile.replaceAll('\\', '/')
  }
  const proxyJump = values['-J'] || ''
  if (proxyJump && !aliasPattern.test(proxyJump)) throw new ServerInputError('跳板机请选择已有 SSH 配置别名。')
  return { hostName: host, user, ...(port !== undefined && { port }), ...(identityFile && { identityFile }), ...(proxyJump && { proxyJump }) }
}

function matches(pattern, alias) {
  const escaped = pattern.replace(/[.+^${}()|[\]\\]/g, '\\$&').replaceAll('*', '.*').replaceAll('?', '.')
  return new RegExp(`^${escaped}$`, 'i').test(alias)
}
function matchesBlock(patterns, alias) {
  if (!patterns.length) return true
  if (patterns.some(pattern => pattern.startsWith('!') && matches(pattern.slice(1), alias))) return false
  return patterns.some(pattern => !pattern.startsWith('!') && matches(pattern, alias))
}

// Appending cannot override an earlier matching OpenSSH value. Reject an
// ambiguous target instead of silently connecting to another host or user.
function checkEarlierRules(configPath, alias, connection) {
  const wanted = { hostname: connection.hostName, ...(connection.user && { user: connection.user }),
    ...(connection.port !== undefined && { port: String(connection.port) }), ...(connection.identityFile && { identityfile: connection.identityFile }), ...(connection.proxyJump && { proxyjump: connection.proxyJump }) }
  for (const file of readConfigTree(configPath)) {
    if (/^\s*Match\s/im.test(file.text)) throw new ServerInputError('SSH 配置包含条件规则。请先在 SSH 配置中创建所需别名，再添加该别名。', 409)
    for (const block of parseSshConfig(file.text)) {
      if (!matchesBlock(block.aliases, alias)) continue
      for (const [name, value] of Object.entries(wanted)) {
        if (block.options[name] !== undefined && block.options[name].replace(/^"(.*)"$/, '$1') !== value) {
          throw new ServerInputError('已有 SSH 全局或通配规则会覆盖新连接。请先在 SSH 配置中创建所需别名，再添加该别名。', 409)
        }
      }
    }
  }
}

function readInventory(file) {
  if (!existsSync(file)) return { version: 1, servers: [] }
  try {
    const content = readFileSync(file, 'utf8')
    if (content.length > 2 * 1024 * 1024) throw Error()
    const value = JSON.parse(content.replace(/^\uFEFF/, ''))
    if (!value || typeof value !== 'object' || Array.isArray(value) || !Array.isArray(value.servers)
      || value.servers.some(server => !server || typeof server.alias !== 'string' || !server.alias.trim())) throw Error()
    return value
  } catch { throw new ServerInputError('服务器列表文件无法读取；为保留已有记录，本次未添加服务器。', 409) }
}

function configLines(alias, fingerprint, connection) {
  const lines = [`# CANNBot connection ${fingerprint}`, `Host ${alias}`, `  HostName ${connection.hostName}`]
  if (connection.user) lines.push(`  User ${connection.user}`)
  if (connection.port !== undefined) lines.push(`  Port ${connection.port}`)
  if (connection.identityFile) lines.push(`  IdentityFile "${connection.identityFile}"`)
  if (connection.proxyJump) lines.push(`  ProxyJump ${connection.proxyJump}`)
  return lines
}

/** Serialize writes across profiles/processes; preserve every pre-existing byte
 * of SSH config, and replace only our inventory after a complete temp write. */
export function addServerRecord(request, { configPath, serversPath }) {
  if (!request || typeof request !== 'object' || Array.isArray(request)) throw invalid()
  let command = request.command
  if (request.connection !== undefined) {
    const c = request.connection
    if (command !== undefined || !c || typeof c !== 'object' || Array.isArray(c)) throw invalid()
    if (typeof c.hostName !== 'string' || !c.hostName || c.hostName.length > 253 || (c.user !== undefined && typeof c.user !== 'string') || (c.port !== undefined && typeof c.port !== 'string' && typeof c.port !== 'number')) throw invalid()
    const quote = value => {
      if (typeof value !== 'string' || /["'\r\n\0]/.test(value)) throw invalid()
      return '"' + value + '"'
    }
    command = 'ssh ' + quote((c.user ? c.user + '@' : '') + c.hostName)
      + (c.port !== undefined && c.port !== '' ? ' -p ' + quote(String(c.port)) : '') + (c.identityFile ? ' -i ' + quote(c.identityFile) : '') + (c.proxyJump ? ' -J ' + quote(c.proxyJump) : '')
  }
  const connection = parseServerCommand(command)
  if (request.label !== undefined && (typeof request.label !== 'string' || request.label.length > 120 || /[\x00-\x1f\x7f]/.test(request.label))) throw new ServerInputError('服务器名称应为不超过 120 个字符的单行文字。')
  const label = request.label?.trim()
  const lock = configPath + '.cannbot-add.lock'
  let descriptor, temp
  try {
    mkdirSync(dirname(configPath), { recursive: true, mode: 0o700 })
    try { descriptor = openSync(lock, 'wx', 0o600) }
    catch (error) { if (error.code === 'EEXIST') throw new ServerInputError('另一个服务器添加操作尚未完成，请稍后重试。', 409); throw error }
    const inventory = readInventory(serversPath)
    const inventoryBefore = existsSync(serversPath) ? readFileSync(serversPath) : null
    const before = existsSync(configPath) ? readFileSync(configPath) : Buffer.alloc(0)
    if (before.includes(0)) throw new ServerInputError('SSH 配置不是受支持的文本格式，本次未作更改。', 409)
    const discovered = listAliases(configPath)
    if (connection.proxyJump && !discovered.aliases.includes(connection.proxyJump)) throw new ServerInputError('没有找到所选跳板机别名。')
    const requestedAlias = connection.existingAlias || connection.hostName
    const existing = discovered.aliases.find(alias => alias.toLowerCase() === requestedAlias.toLowerCase())
      || (connection.existingAlias && inventory.servers.find(server => server.alias.trim().toLowerCase() === requestedAlias.toLowerCase())?.alias.trim())
    let alias, defaultLabel, append = ''
    if (existing) {
      if (!connection.existingAlias && (connection.user || connection.port !== undefined || connection.identityFile || connection.proxyJump)) throw new ServerInputError('已有 SSH 别名请直接填写别名；添加不同参数的连接时，请填写真实主机地址。', 409)
      alias = existing
      defaultLabel = existing
    } else {
      if (connection.existingAlias) throw new ServerInputError('没有找到该 SSH 别名，请检查 SSH 配置或输入 ssh 用户@主机。', 400)
      const fingerprint = createHash('sha256').update(JSON.stringify(connection)).digest('hex').slice(0, 16)
      const prefix = `cannbot-${fingerprint}`
      alias = prefix
      const displayHost = isIP(connection.hostName) === 6 ? `[${connection.hostName}]` : connection.hostName
      defaultLabel = `${connection.user ? connection.user + '@' : ''}${displayHost}${connection.port !== undefined && connection.port !== 22 ? ':' + connection.port : ''}`
      let suffix = 0
      // Repeated submissions reuse only an exact block previously written by us.
      while (discovered.aliases.some(item => item.toLowerCase() === alias.toLowerCase())) {
        const managed = configLines(alias, fingerprint, connection).join('\n') + '\n'
        if (before.toString('utf8').replaceAll('\r\n', '\n').includes(managed)) break
        alias = `${prefix}-${++suffix}`
      }
      checkEarlierRules(configPath, alias, connection)
      if (!discovered.aliases.some(item => item.toLowerCase() === alias.toLowerCase())) {
        const newline = before.includes(Buffer.from('\r\n')) ? '\r\n' : '\n'
        append = newline + configLines(alias, fingerprint, connection).join(newline) + newline
      }
    }
    const known = inventory.servers.find(server => server.alias.trim().toLowerCase() === alias.toLowerCase())
    const restored = Array.isArray(inventory.hiddenAliases) && inventory.hiddenAliases.some(item => typeof item === 'string' && item.trim().toLowerCase() === alias.toLowerCase())
    if (known && !append && !restored) return { alias: known.alias.trim(), label: known.label || known.alias.trim() }
    const next = { ...inventory, servers: known ? inventory.servers : [...inventory.servers, { alias, label: label || defaultLabel, group: 'default' }] }
    if (restored) {
      next.hiddenAliases = inventory.hiddenAliases.filter(item => typeof item !== 'string' || item.trim().toLowerCase() !== alias.toLowerCase())
      next.order = [...mergeInventory({ shared: normalizeInventory(inventory), sshAliases: discovered.aliases, sshResolved: discovered.resolved }).servers.map(server => server.id), alias]
    }
    mkdirSync(dirname(serversPath), { recursive: true, mode: 0o700 })
    temp = `${serversPath}.add-${process.pid}-${Date.now()}.tmp`
    writeFileSync(temp, JSON.stringify(next, null, 2) + '\n', { flag: 'wx', mode: existsSync(serversPath) ? statSync(serversPath).mode & 0o777 : 0o600 })
    const inventoryCurrent = existsSync(serversPath) ? readFileSync(serversPath) : null
    if (inventoryBefore === null ? inventoryCurrent !== null : inventoryCurrent === null || !inventoryBefore.equals(inventoryCurrent)) throw new ServerInputError('服务器列表已被其他操作更新，请刷新后重试。', 409)
    if (append) appendFileSync(configPath, append, { encoding: 'utf8', mode: 0o600 })
    renameSync(temp, serversPath); temp = undefined
    return { alias: known?.alias.trim() || alias, label: known ? known.label || known.alias.trim() : label || defaultLabel }
  } catch (error) {
    if (error instanceof ServerInputError) throw error
    throw new ServerInputError('无法保存 SSH 配置或服务器列表，请检查文件权限后重试。', 500)
  } finally {
    if (temp) { try { unlinkSync(temp) } catch { /* no partial inventory is published */ } }
    if (descriptor !== undefined) { closeSync(descriptor); try { unlinkSync(lock) } catch { /* do not delete another lock */ } }
  }
}
