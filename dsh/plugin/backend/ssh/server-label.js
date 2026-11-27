// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

// Remarks are inventory metadata. Never change an SSH alias or its connection.
import { randomUUID } from 'node:crypto'
import { dirname } from 'node:path'
import { closeSync, existsSync, mkdirSync, openSync, readFileSync, renameSync, statSync, unlinkSync, writeFileSync } from 'node:fs'
import { ServerInputError } from './add-server.js'
import { listAliases } from './ssh-config.js'

function readInventory(file) {
  if (!existsSync(file)) return { value: { version: 1, servers: [] }, bytes: null }
  try {
    const bytes = readFileSync(file), text = bytes.toString('utf8')
    if (text.length > 2 * 1024 * 1024) throw Error()
    const value = JSON.parse(text.replace(/^\uFEFF/, ''))
    if (!value || typeof value !== 'object' || Array.isArray(value) || !Array.isArray(value.servers)
      || value.servers.some(server => !server || typeof server.alias !== 'string' || !server.alias.trim())) throw Error()
    return { value, bytes }
  } catch { throw new ServerInputError('服务器列表文件无法读取；为保留已有记录，本次未修改备注。', 409) }
}

export function setServerLabel(request, { configPath, serversPath }) {
  if (!request || typeof request !== 'object' || Array.isArray(request)
    || typeof request.id !== 'string' || !request.id.trim() || request.id.length > 512 || /[\x00-\x1f\x7f]/.test(request.id)) {
    throw new ServerInputError('服务器标识无效。')
  }
  if (typeof request.label !== 'string' || request.label.length > 120 || /[\x00-\x1f\x7f]/.test(request.label)) {
    throw new ServerInputError('服务器备注应为不超过 120 个字符的单行文字。')
  }
  const id = request.id.trim(), label = request.label.trim()
  // Share the add-server lock: read the latest complete inventory only after
  // acquiring it, so adding and renaming cannot overwrite each other's work.
  const lock = configPath + '.cannbot-add.lock'
  let descriptor, temp
  try {
    mkdirSync(dirname(configPath), { recursive: true, mode: 0o700 })
    try { descriptor = openSync(lock, 'wx', 0o600) }
    catch (error) {
      if (error.code === 'EEXIST') throw new ServerInputError('另一个服务器保存操作尚未完成，请稍后重试。', 409)
      throw error
    }
    const { value: inventory, bytes: before } = readInventory(serversPath)
    if (inventory.hiddenAliases?.some?.(alias => typeof alias === 'string' && alias.trim().toLowerCase() === id.toLowerCase())) throw new ServerInputError('没有找到该服务器，请刷新列表后重试。', 404)
    const known = inventory.servers.filter(server => server.alias.trim().toLowerCase() === id.toLowerCase())
    const alias = known.at(-1)?.alias.trim() || listAliases(configPath).aliases.find(alias => alias.toLowerCase() === id.toLowerCase())
    if (!alias) throw new ServerInputError('没有找到该服务器，请刷新列表后重试。', 404)
    const result = { alias, label: label || alias }
    if (!known.length && !label) return result
    const next = { ...inventory, servers: inventory.servers.map(server => {
      if (server.alias.trim().toLowerCase() !== alias.toLowerCase()) return server
      const updated = { ...server }
      if (label) updated.label = label
      else delete updated.label
      return updated
    }) }
    if (!known.length) next.servers.push({ alias, label })
    if (JSON.stringify(next) === JSON.stringify(inventory)) return result
    mkdirSync(dirname(serversPath), { recursive: true, mode: 0o700 })
    temp = `${serversPath}.label-${randomUUID()}.tmp`
    writeFileSync(temp, JSON.stringify(next, null, 2) + '\n', {
      flag: 'wx', mode: existsSync(serversPath) ? statSync(serversPath).mode & 0o777 : 0o600,
    })
    // Our two write APIs honor the same lock. Also refuse a file changed by an
    // external editor while preparing this update, rather than erasing it.
    const current = existsSync(serversPath) ? readFileSync(serversPath) : null
    if (before === null ? current !== null : current === null || !before.equals(current)) {
      throw new ServerInputError('服务器列表已被其他操作更新，请刷新后重试。', 409)
    }
    renameSync(temp, serversPath); temp = undefined
    return result
  } catch (error) {
    if (error instanceof ServerInputError) throw error
    throw new ServerInputError('无法保存服务器备注，请检查文件权限后重试。', 500)
  } finally {
    if (temp) { try { unlinkSync(temp) } catch { /* unpublished temporary file */ } }
    if (descriptor !== undefined) { closeSync(descriptor); try { unlinkSync(lock) } catch { /* only our acquired lock */ } }
  }
}
