// ----------------------------------------------------------------------------------------------------------
// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.
// ----------------------------------------------------------------------------------------------------------

import type { Context } from '@deepseek-ai/cordis'
import type {} from '@deepseek-ai/dsh-agent'
import type {} from '@deepseek-ai/dsh-working-directory'
import type {} from '@deepseek-ai/dsh-settings'
import { createUserMessage } from '@deepseek-ai/dsh-llm'
import { isUserInvocable, renderSkillContent } from '@deepseek-ai/dsh-skill'
import z from '@deepseek-ai/schemastery'
import { WORKFLOWS } from './workflows.ts'
import type { ContentManager } from './content-manager.ts'

export const WORKFLOW_SETTINGS = 'cannbot-dsh'
export interface WorkflowChoice { sessionId: string; workflow: string }
export interface Config { selections?: WorkflowChoice[] | { get(): WorkflowChoice[] } }
const choiceSchema = () => z.array(z.object({ sessionId: z.string(), workflow: z.string() })).default([])
const selections = choiceSchema()
// Settings used namespaces before profile-entry Config became the public write face.
export const Config = z.object({ selections: typeof selections.volatile === 'function' ? selections.volatile() : selections })
const LegacyConfig = z.object({ selections: choiceSchema() })
export function selectedWorkflows(config: Config): WorkflowChoice[] {
  const value = config.selections
  return Array.isArray(value) ? value : value?.get() ?? []
}

export function installWorkflowContext(ctx: Context, config: Config, content?: ContentManager) {
  let read = () => config
  ctx.inject(['settings'], scoped => {
    const settings = scoped.settings as unknown as { register?: (name: string, schema: unknown, options: unknown) => { get(): Config } }
    if (typeof settings.register === 'function') {
      // Arrays have the same JSON representation in the oldest and current SDK.
      const base = { selections: selectedWorkflows(config).map(({ sessionId, workflow }) => ({ sessionId, workflow })) }
      const handle = settings.register(WORKFLOW_SETTINGS, LegacyConfig, { base })
      read = () => handle.get()
    }
  })
  ctx.inject(['agents', 'workingDirectory'], scoped => {
    scoped.on('agent/pre-step', async ({ agent, signal }, next) => {
      const decision = await next()
      if (decision.kind === 'reject') return decision
      const messages = decision.messages.filter(message => message.source?.kind !== 'cannbot-dsh-workflow')
      const id = selectedWorkflows(read()).find(item => item.sessionId === agent.id)?.workflow
      if (!id) return { ...decision, messages }
      const cwd = await scoped.workingDirectory.ensure(agent, signal)
      if (!content && !WORKFLOWS.some(item => item.id === id)) throw new Error('Workflow is unavailable')
      let skill: Awaited<ReturnType<Context['skills']['get']>>
      for (let attempt = 0; attempt < 3; attempt++) {
        if (content) await content.prepare(cwd, id)
        const snapshot = content?.getSource()
        const revision = snapshot?.revision
        const entry = snapshot?.catalog.exposedSkills.find(item => item.pluginId === id && item.entry)
        const candidate = await scoped.skills.get(entry?.name ?? id, { cwd, scope: agent, signal })
        if (revision === content?.getSource().revision) { skill = candidate; break }
      }
      if (!skill || !isUserInvocable(skill)) throw new Error(`CANNBot DSH workflow is unavailable: ${id}`)
      // The normal user message remains untouched. The official pre-step seam
      // supplies the same Skill body as DSH's slash invocation, to the model only.
      const source = { kind: 'cannbot-dsh-workflow' as const, name: id, form: 'instructions' as const }
      return { ...decision, messages: [...messages, createUserMessage({
        source, content: [{ type: 'text', text: renderSkillContent(skill) + '\n\n'
          + 'DSH 会话任务跟踪：在执行多步骤工作前，用 todo_write 建立具体的 PM 任务计划；需求确认、环境准备、工作流组装等启动前工作也要列入。'
          + '开始、完成或受阻时及时更新计划，不要只在聊天中报告进展。命令返回或文件生成不等于任务验收通过。'
          + '插件自动同步 [工作流] 节点状态；todo_write 只维护你自己的 PM 计划，勿复制或修改插件节点。'
          + '在此插件内启动或续跑编排器使用 cannbot_workflow_run，查询使用 cannbot_workflow_status，节点由 DSH agent loop 执行；不要经 shell 改用其他 provider。'
          + '若已有外部编排器在运行，不要重复启动；先核实并报告其状态。' }],
      })] }
    })
  })
}

declare module '@deepseek-ai/dsh-llm' {
  interface MessageSourceMap {
    'cannbot-dsh-workflow': { kind: 'cannbot-dsh-workflow'; name: string; form: 'instructions' }
  }
}
