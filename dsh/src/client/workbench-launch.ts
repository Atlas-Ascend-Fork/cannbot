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
import type { ConversationController } from '@deepseek-ai/dsh-client-ui-conversation/client'
import type { WorkspaceId } from '@deepseek-ai/dsh-api-workspace-controller/client'
import type { ISessions } from '@deepseek-ai/dsh-api-session-controller/client'
import type {} from '@deepseek-ai/dsh-client-ui-workspace/client'
import type { WorkflowSelection } from './workflow-selection.ts'
import type { PreparationStage } from './workbench-state.ts'

/** Transfer to the resident DSH composer; its own submit policy remains authoritative. */
export async function launchWorkbench(ctx: Context, selection: WorkflowSelection, request: { workspaceId: string; workflow: string; prompt: string; files: readonly File[] }, signal: AbortSignal, onStage: (stage: PreparationStage) => void = () => {}) {
  if (!selection.getSnapshot().ready || selection.getSnapshot().pending) throw new Error('工作流设置尚未就绪，请稍后重试。')
  signal.throwIfAborted()
  const startingPanel = ctx.layout.panelInfo.getSnapshot().activePanelId
  // The development workspace also includes legacy Context declarations.
  const sessions = ctx.sessions as unknown as ISessions
  onStage('workspace')
  const id = await sessions.create({ workspaceId: request.workspaceId as WorkspaceId })
  signal.throwIfAborted()
  const reference = sessions.retain(id, { source: 'controllerOperation', signal })
  const conversation = ctx.conversation as ConversationController
  let attachments: ReturnType<ConversationController['createDrafts']> = []
  let transferred = false
  try {
    const binding = await reference.ready
    signal.throwIfAborted()
    if (request.workflow) onStage('dependencies')
    await selection.choose(id, request.workflow)
    signal.throwIfAborted()
    const saved = selection.getSnapshot()
    if (!saved.ready || saved.pending || saved.error || (saved.values[id] ?? '') !== request.workflow) throw new Error(saved.errorMessage || '工作流准备未完成，请在插件设置中查看日志后重试。')
    if (conversation.blocks.storeFor(id).getSnapshot()) throw new Error('当前对话暂时不能发送，请稍后重试。')
    const input = conversation.input.for(binding.ctx)
    const initialized = conversation.input.requestDraftInitialization(binding, { prompt: request.prompt, whenDraftExists: 'keep' })
    if (initialized !== 'applied') throw new Error('新对话已存在草稿，已保留内容，请重试。')
    if (request.files.length) {
      onStage('upload')
      if (typeof conversation.createDrafts !== 'function') throw new Error('此 DSH 版本请进入对话后添加文件。')
      attachments = conversation.createDrafts(id, request.files)
      await waitForUploads(conversation, attachments.filter(item => item.kind === 'file').map(item => item.id), signal)
      if (!input.addAttachments(attachments.map(item => item.id))) throw new Error('文件暂时无法加入对话，请重试。')
    }
    signal.throwIfAborted()
    if (ctx.layout.panelInfo.getSnapshot().activePanelId !== startingPanel) throw new Error('你已离开工作台，需求已保留；返回后可重新开始。')
    // Navigation acquires its own reference before this transaction releases ours.
    onStage('conversation')
    ctx.uiWorkspace.openSession(id)
    transferred = true
    input.submit('queue', 'click')
  } finally {
    if (!transferred) for (const attachment of attachments) conversation.releaseDraftAttachment(attachment.id)
    reference.release()
  }
}

function waitForUploads(conversation: ConversationController, ids: readonly string[], signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    let unsubscribe = () => {}, timer: ReturnType<typeof setTimeout> | undefined
    const finish = (error?: unknown) => { unsubscribe(); clearTimeout(timer); signal.removeEventListener('abort', abort); error ? reject(error) : resolve() }
    const abort = () => finish(signal.reason ?? new Error('操作已取消。'))
    const check = () => {
      const uploads = conversation.fileUploads.getSnapshot()
      const failed = ids.map(id => uploads[id]).find(upload => upload?.status === 'error')
      if (failed?.status === 'error') finish(new Error(`文件上传失败：${failed.message}`))
      else if (ids.every(id => uploads[id]?.status === 'ready')) finish()
    }
    unsubscribe = conversation.fileUploads.subscribe(check)
    timer = setTimeout(() => finish(new Error('文件上传超时，请检查连接后重试。')), 120000)
    signal.addEventListener('abort', abort, { once: true })
    if (signal.aborted) abort(); else check()
  })
}
