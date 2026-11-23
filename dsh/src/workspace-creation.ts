// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { mkdir, readdir, realpath, stat, readFile, writeFile } from 'node:fs/promises'
import { basename, dirname, isAbsolute, join, parse } from 'node:path'
import { withContentLock } from './content-lock.ts'
import { WorkspaceModeError, type WorkspaceModes } from './workspace-mode.ts'
import { GENERAL_WORKSPACE } from './workspace-mode-types.ts'

export type WorkspaceCreationRequest =
  | { action: 'browse-directory'; path: string; complete?: boolean }
  | { action: 'create-folder'; parent: string; name: string; pluginId: string; requestId: string }

export function creationRequest(value: unknown): WorkspaceCreationRequest | undefined {
  if (!value || typeof value !== 'object') return
  const data = value as Record<string, unknown>
  const path = (value: unknown): value is string => typeof value === 'string' && value.length <= 32768 && !/[\x00-\x1f]/.test(value)
  if (data.action === 'browse-directory' && path(data.path)) return { action: data.action, path: data.path, ...(data.complete === true && { complete: true }) }
  if (data.action === 'create-folder' && path(data.parent) && typeof data.name === 'string' && data.name.length > 0 && data.name.length <= 255
    && !/[<>:"/\\|?*\x00-\x1f]/.test(data.name) && data.name.trim() === data.name && !/[. ]$/.test(data.name)
    && !/^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/i.test(data.name)
    && typeof data.pluginId === 'string' && /^[\w-]{1,100}$/.test(data.pluginId)
    && typeof data.requestId === 'string' && /^[\da-f-]{36}$/i.test(data.requestId)) {
    return { action: data.action, parent: data.parent, name: data.name, pluginId: data.pluginId, requestId: data.requestId }
  }
}

export async function workspaceCreation(modes: WorkspaceModes, request: WorkspaceCreationRequest, remote: boolean) {
  if (request.action === 'browse-directory') {
    const selected = request.path || parse(process.cwd()).root
    if (!isAbsolute(selected)) throw new WorkspaceModeError('invalid-directory', '请选择父目录的绝对路径。', 400)
    let partial = false, path: string
    try { path = await realpath(selected); if (!(await stat(path)).isDirectory()) throw Object.assign(new Error('Not a directory'), { code: 'ENOTDIR' }) }
    catch (error) {
      if (!request.complete || !['ENOENT', 'ENOTDIR'].includes((error as NodeJS.ErrnoException).code || '')) throw error
      path = await realpath(dirname(selected)); partial = true
    }
    const entries = await readdir(path, { withFileTypes: true })
    const crumbs: { name: string; path: string; hidden: boolean }[] = []
    for (let current = path;; current = dirname(current)) {
      crumbs.unshift({ name: basename(current) || current, path: current, hidden: false })
      if (dirname(current) === current) break
    }
    const directories = entries.filter(entry => entry.isDirectory() && (!partial || entry.name.toLocaleLowerCase().startsWith(basename(selected).toLocaleLowerCase()))).sort((a, b) => a.name.localeCompare(b.name))
    return { path, crumbs, entries: directories.slice(0, 1000).map(entry => ({ name: entry.name, path: join(path, entry.name), hidden: entry.name.startsWith('.') })), truncated: directories.length > 1000, ...(partial && { partial }) }
  }
  if (request.pluginId !== GENERAL_WORKSPACE && process.platform !== 'linux') throw new WorkspaceModeError('workflow-linux-only', '本工作流需要 Linux 环境。Windows 本机请选择空白工作区，或连接 Linux 服务器。', 400)
  if (!isAbsolute(request.parent)) throw new WorkspaceModeError('invalid-directory', '请选择父目录的绝对路径。', 400)
  const parent = await realpath(request.parent), path = join(parent, request.name)
  const root = join(modes.root, 'creation-requests')
  // Keep one receipt across connection timeouts. Retrying the same submission
  // may resume initialization, but can never adopt a pre-existing directory.
  return withContentLock(join(root, request.requestId + '.lock'), async () => {
    const receipt = join(root, request.requestId + '.json')
    let saved: { path: string; pluginId: string; identity: string } | undefined
    try { saved = JSON.parse(await readFile(receipt, 'utf8')) }
    catch (error) { if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error }
    if (saved) {
      const info = await stat(path)
      if (saved.path !== path || saved.pluginId !== request.pluginId || saved.identity !== `${info.dev}:${info.ino}` || await realpath(path) !== path) throw new WorkspaceModeError('creation-changed', '创建请求或目录已变化，请重新创建工作区。')
    } else {
      try { await mkdir(path) }
      catch (error) {
        if ((error as NodeJS.ErrnoException).code === 'EEXIST') throw new WorkspaceModeError('folder-exists', '同名文件夹已存在，请换一个新名称。')
        throw error
      }
      const info = await stat(path)
      await mkdir(root, { recursive: true })
      await writeFile(receipt, JSON.stringify({ path, pluginId: request.pluginId, identity: `${info.dev}:${info.ino}` }), { flag: 'wx', mode: 0o600 })
    }
    return { workspace: await modes.create(path, request.pluginId) }
  })
}
