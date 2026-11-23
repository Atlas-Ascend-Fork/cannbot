// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { lstat, readFile, realpath, rm, writeFile } from 'node:fs/promises'
import { dirname, isAbsolute, join, relative, resolve, sep } from 'node:path'
import type { WorkflowDescriptor } from './content-types.ts'

/** Retire executable registrations only; repositories and project source stay put. */
export async function workflowRetirement(workspace: string, descriptor?: WorkflowDescriptor) {
  const paths = new Set<string>(), markers = new Set<string>(), names = new Set<string>()
  let registry: { schemaVersion: number; plugins: Record<string, unknown>[] } | undefined
  if (descriptor) {
    markers.add(descriptor.id)
    for (const skill of descriptor.skills) { paths.add(`.dsh/skills/${skill.name}`); names.add(skill.name) }
    paths.add(`.cannbot/plugins/${descriptor.id}`)
    try { registry = JSON.parse(await readFile(join(workspace, '.dsh/cannbot-plugin.json'), 'utf8')) }
    catch (error) { if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error }
    if (registry) {
      if (registry.schemaVersion !== 2 || !Array.isArray(registry.plugins)) throw new Error('工作流安装记录无效，未修改工作区。')
      for (const row of registry.plugins.filter(row => row.plugin === descriptor.id)) {
        for (const path of [...(Array.isArray(row.skills) ? row.skills : []), ...(Array.isArray(row.agents) ? row.agents : [])]) {
          if (typeof path !== 'string' || !/^\.dsh\/(?:skills\/[\w.-]+|agents\/[\w.-]+\.md)$/.test(path.replaceAll('\\', '/'))) throw new Error('工作流安装记录包含无效的受管路径。')
          paths.add(path.replaceAll('\\', '/'))
        }
        if (Array.isArray(row.dependencyAssets)) for (const asset of row.dependencyAssets) {
          if (typeof asset.dependency === 'string' && /^[\w.-]+$/.test(asset.dependency)) markers.add(asset.dependency)
          for (const name of asset.skills ?? []) { if (typeof name !== 'string' || !/^[\w.-]+$/.test(name)) throw new Error('工作流依赖记录无效。'); paths.add('.dsh/skills/' + name); names.add(name) }
        }
      }
    }
  }
  // Refuse linked parent directories before any removal outside the transaction.
  for (const path of paths) {
    const target = resolve(workspace, path), diff = relative(workspace, target)
    if (!diff || isAbsolute(diff) || diff === '..' || diff.startsWith('..' + sep)) throw new Error('受管路径超出工作区。')
    let parent = dirname(target)
    while (parent !== workspace) {
      try { const actual = await realpath(parent), rel = relative(workspace, actual); if (isAbsolute(rel) || rel === '..' || rel.startsWith('..' + sep)) throw new Error('受管路径的父目录指向工作区外。'); break }
      catch (error) { if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error; parent = dirname(parent) }
    }
  }
  return { paths: [...paths], async retire() {
    if (!descriptor) return
    for (const path of paths) await rm(join(workspace, path), { recursive: true, force: true })
    for (const file of ['AGENTS.md', 'CLAUDE.md']) {
      const path = join(workspace, file)
      let text: string
      try { if ((await lstat(path)).isSymbolicLink()) throw new Error('指令文件为符号链接，未修改。'); text = await readFile(path, 'utf8') } catch (error) { if ((error as NodeJS.ErrnoException).code === 'ENOENT') continue; throw error }
      for (const marker of markers) {
        const name = marker.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
        text = text.replace(new RegExp(`<!-- cannbot:${name}:start -->[\\s\\S]*?<!-- cannbot:${name}:end -->`, 'g'), '')
      }
      await writeFile(path, text)
    }
    if (registry) { registry.plugins = registry.plugins.filter(row => row.plugin !== descriptor.id); await writeFile(join(workspace, '.dsh/cannbot-plugin.json'), JSON.stringify(registry, null, 2) + '\n') }
    const settings = join(workspace, '.cannbot/settings.json')
    try {
      if ((await lstat(settings)).isSymbolicLink()) throw new Error('工作流配置为符号链接，未修改。')
      const data = JSON.parse(await readFile(settings, 'utf8'))
      for (const name of names) if (data.plugins && typeof data.plugins === 'object') delete data.plugins[name]
      await writeFile(settings, JSON.stringify(data, null, 2) + '\n')
    } catch (error) { if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error }
  } }
}
