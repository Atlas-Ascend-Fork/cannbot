// ----------------------------------------------------------------------------------------------------------
// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.
// ----------------------------------------------------------------------------------------------------------

export type PreparationStage = 'idle' | 'workspace' | 'dependencies' | 'upload' | 'conversation'
export const preparationLabels: Record<PreparationStage, string> = { idle: '', workspace: '正在准备工作区…', dependencies: '正在准备工作流依赖…', upload: '正在上传文件…', conversation: '正在进入对话…' }
export interface WorkbenchState { prompt: string; workflow: string; workspaceId: string; files: File[]; detail: string; busy: boolean; error: string; stage: PreparationStage }
export function createWorkbenchState() {
  let state: WorkbenchState = { prompt: '', workflow: 'ops-direct-invoke-flash', workspaceId: '', files: [], detail: 'ops-direct-invoke-flash', busy: false, error: '', stage: 'idle' }
  const listeners = new Set<() => void>()
  const lifetime = new AbortController()
  return {
    signal: lifetime.signal,
    getSnapshot: () => state,
    subscribe(listener: () => void) { listeners.add(listener); return () => { listeners.delete(listener) } },
    set(patch: Partial<WorkbenchState>) { if (lifetime.signal.aborted) return; state = { ...state, ...patch }; for (const listener of listeners) listener() },
    dispose() { lifetime.abort(); listeners.clear() },
  }
}
export type WorkbenchStore = ReturnType<typeof createWorkbenchState>
