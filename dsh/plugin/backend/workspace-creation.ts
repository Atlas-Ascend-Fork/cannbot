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

import type { WorkspaceCreationRequest } from '../contracts/workspace-creation-contract.ts'
export { creationRequest, type WorkspaceCreationRequest } from '../contracts/workspace-creation-contract.ts'

export async function workspaceCreation(modes: WorkspaceModes, request: WorkspaceCreationRequest) {
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
  modes.checkWorkflowPlatform(request.pluginId)
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
