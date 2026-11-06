// ----------------------------------------------------------------------------------------------------------
// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.
// ----------------------------------------------------------------------------------------------------------

/** All official CANNBot plugins, mounted through DSH's public Skill provider API. */
import type { Context } from '@deepseek-ai/cordis'
import type { SkillCandidate } from '@deepseek-ai/dsh-skill'
import { FileSystemSkillProvider } from '@deepseek-ai/dsh-skill-filesystem'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { resolve } from 'node:path'
import { installWorkflowContext, type Config } from './workflow-context.ts'
import { registerHostUpdater } from './update-host.ts'
import { ContentManager } from './content-manager.ts'
import { registerContentRoutes } from './content-routes.ts'
import { installNativeWorkflowTools } from './native-workflow-tools.mjs'
import type { ContentPlugin as Plugin, ContentSkill as BundledSkill, ContentCatalog as Catalog } from './content-types.ts'
export { Config } from './workflow-context.ts'

export const inject = ['skills']

export async function apply(ctx: Context, config: Config = {}): Promise<void> {
  registerHostUpdater(ctx)
  const content = new ContentManager(fileURLToPath(new URL('../workflow-defaults.json', import.meta.url)))
  const require = createRequire(import.meta.url)
  const catalogFile = require.resolve('@cannbot-plugin/workflow-catalog/package.json')
  const dependencies = createRequire(catalogFile)
  await content.installDependencies(catalogFile, name => dependencies.resolve(`${name}/package.json`))
  registerContentRoutes(ctx, content)
  installWorkflowContext(ctx, config, content)
  installNativeWorkflowTools(ctx, content)
  ctx.skills.registerProvider(control => {
    let observed = content.getSource().revision
    const release = content.subscribe(() => {
      const current = content.getSource().revision
      if (current !== observed) { observed = current; control.invalidate() }
    })
    control.signal.addEventListener('abort', release, { once: true })
    let assets = '', revision = '', catalog: Catalog, byPath: Map<string, BundledSkill>, providers: { plugin: Plugin; provider: FileSystemSkillProvider }[] = []
    const refresh = () => {
      const current = content.getSource()
      if (current.revision === revision) return
      assets = current.assets; catalog = current.catalog; revision = current.revision
      byPath = new Map(catalog.exposedSkills.map(skill => [resolve(assets, skill.path), skill]))
      providers = catalog.plugins.map(plugin => ({ plugin, provider: new FileSystemSkillProvider(ctx, control, {
      providerName: 'cannbot-dsh', includeDefaultRoots: false,
      bundledSkillDir: resolve(assets, plugin.resourceDirectory ?? plugin.id, 'skills'), watch: false,
      }) }))
    }
    const owners = new WeakMap<SkillCandidate, { provider: FileSystemSkillProvider; bundled: BundledSkill; plugin?: Plugin; assets: string }>()
    return {
      name: 'cannbot-dsh',
      async list(options) {
        refresh()
        const candidates: SkillCandidate[] = []
        let complete = true
        for (const { provider } of providers) {
          const observation = await provider.list(options)
          const items = Array.isArray(observation) ? observation : observation.candidates
          if (!Array.isArray(observation) && !observation.complete) complete = false
          for (const candidate of items) {
            const bundled = candidate.path === undefined ? undefined : byPath.get(resolve(candidate.path))
            if (bundled === undefined) continue
            // A project init may install a second copy of the entry. Keep the selected
            // Keep the bundled entry from this validated snapshot so its alias map stays intact.
            const exposed = { ...candidate, name: bundled.name, ...bundled.entry ? { rank: -100 } : {} }
            owners.set(exposed, { provider, bundled, plugin: catalog.plugins.find(item => item.id === bundled.pluginId), assets })
            candidates.push(exposed)
          }
        }
        return { candidates, complete }
      },
      async get(candidate, options) {
        const owner = owners.get(candidate)
        if (owner === undefined) return undefined
        const { provider, bundled, plugin, assets } = owner
        const definition = await provider.get(candidate, options)
        if (definition === undefined) return undefined
        const preface = bundled?.entry && plugin ? [
          `# CANNBot DSH — ${plugin.title}`,
          `官方工作流包资源目录：${resolve(assets, plugin.resourceDirectory ?? plugin.id)}`,
          '读取该目录中的 Skills、agents、脚本与模板时使用绝对路径；项目依赖由上游官方安装器初始化。',
          ...Object.entries(plugin.aliases).map(([original, exposed]) => `本工作流调用 Skill ${original} 时，使用 DSH 中的名称 ${exposed}；资源目录中的原始文件名保持不变。`),
          '', '---', '',
        ].join('\n') : ''
        return { ...definition, name: candidate.name, content: preface + definition.content }
      },
    }
  })
}
