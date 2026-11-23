// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { randomUUID } from 'node:crypto'
import { dirname } from 'node:path'
import { closeSync, existsSync, mkdirSync, openSync, readFileSync, renameSync, statSync, unlinkSync, writeFileSync } from 'node:fs'
import { ServerInputError } from './add-server.js'
import { listAliases } from './ssh-config.js'
import { mergeInventory, normalizeInventory } from './servers.js'

const key = alias => alias.trim().toLowerCase()
const validId = value => typeof value === 'string' && value.trim() && value.length <= 512 && !/[\x00-\x1f\x7f]/.test(value)

/** Use the same lock as add/label; preserve unknown inventory metadata and never
 * write SSH config. External file edits are detected before atomic publication. */
function updateInventory({ configPath, serversPath }, update, beforeCommit) {
  const lock = configPath + '.cannbot-add.lock'
  let descriptor, temp
  try {
    mkdirSync(dirname(configPath), { recursive: true, mode: 0o700 })
    try { descriptor = openSync(lock, 'wx', 0o600) }
    catch (error) { if (error.code === 'EEXIST') throw new ServerInputError('另一个服务器保存操作尚未完成，请稍后重试。', 409); throw error }
    const before = existsSync(serversPath) ? readFileSync(serversPath) : null
    let value
    try {
      if (before && before.length > 2 * 1024 * 1024) throw Error()
      value = before ? JSON.parse(before.toString('utf8').replace(/^\uFEFF/, '')) : { version: 1, servers: [] }
      if (!value || typeof value !== 'object' || Array.isArray(value) || !Array.isArray(value.servers)
        || value.servers.some(server => !server || !validId(server.alias))
        || ['order', 'hiddenAliases'].some(field => value[field] !== undefined && (!Array.isArray(value[field]) || value[field].some(id => !validId(id))))) throw Error()
    } catch { throw new ServerInputError('服务器列表文件无法读取；为保留已有记录，本次未修改。', 409) }
    const discovery = listAliases(configPath)
    const visible = mergeInventory({ shared: normalizeInventory(value), sshAliases: discovery.aliases, sshResolved: discovery.resolved }).servers
    const { next, result } = update(value, visible)
    if (JSON.stringify(next) !== JSON.stringify(value)) {
      mkdirSync(dirname(serversPath), { recursive: true, mode: 0o700 })
      temp = `${serversPath}.manage-${randomUUID()}.tmp`
      writeFileSync(temp, JSON.stringify(next, null, 2) + '\n', { flag: 'wx', mode: existsSync(serversPath) ? statSync(serversPath).mode & 0o777 : 0o600 })
      const current = existsSync(serversPath) ? readFileSync(serversPath) : null
      if (before === null ? current !== null : current === null || !before.equals(current)) throw new ServerInputError('服务器列表已更新，请刷新列表后重试。', 409)
    }
    // Stop the local tunnel before publishing a removal. If stopping or saving
    // fails the row stays visible; no remote process or file is touched.
    beforeCommit?.(result.id)
    if (temp) { renameSync(temp, serversPath); temp = undefined }
    return result
  } catch (error) {
    if (error instanceof ServerInputError) throw error
    throw new ServerInputError('无法保存服务器列表，请检查文件权限后重试。', 500)
  } finally {
    if (temp) { try { unlinkSync(temp) } catch { /* unpublished temporary file */ } }
    if (descriptor !== undefined) { closeSync(descriptor); try { unlinkSync(lock) } catch { /* release only our lock */ } }
  }
}

export function reorderServers(request, paths) {
  if (!request || typeof request !== 'object' || Array.isArray(request) || !Array.isArray(request.ids)
    || request.ids.length > 2000 || request.ids.some(id => !validId(id)) || new Set(request.ids.map(key)).size !== request.ids.length) {
    throw new ServerInputError('服务器顺序无效，请提供不重复的服务器标识。')
  }
  return updateInventory(paths, (inventory, visible) => {
    const byId = new Map(visible.map(server => [key(server.id), server.id]))
    if (request.ids.some(id => !byId.has(key(id)))) throw new ServerInputError('服务器列表已变化，请刷新列表后重新排序。', 409)
    const requested = new Set(request.ids.map(key))
    const ids = [...request.ids.map(id => byId.get(key(id))), ...visible.filter(server => !requested.has(key(server.id))).map(server => server.id)]
    return { next: { ...inventory, order: ids }, result: { ids } }
  })
}

export function removeServerRecord(request, paths, beforeCommit) {
  if (!request || typeof request !== 'object' || Array.isArray(request) || !validId(request.id)) throw new ServerInputError('服务器标识无效。')
  return updateInventory(paths, (inventory, visible) => {
    const hidden = inventory.hiddenAliases || []
    const server = visible.find(server => key(server.id) === key(request.id))
    const previouslyHidden = hidden.find(alias => key(alias) === key(request.id))
    if (!server && !previouslyHidden) throw new ServerInputError('没有找到该服务器，请刷新列表后重试。', 404)
    const id = server?.id || inventory.servers.find(server => key(server.alias) === key(request.id))?.alias.trim() || previouslyHidden
    const hiddenAliases = [...new Set([...hidden.map(key), key(id)])]
    return { next: { ...inventory, hiddenAliases, order: (inventory.order || []).filter(alias => key(alias) !== key(id)) }, result: { id } }
  }, beforeCommit)
}
