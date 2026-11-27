// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { creationRequest } from './workspace-creation-contract.ts'
import { workspaceOperation } from './workspace-mode-types.ts'

export type InitializationOperation = { action: 'create-folder'; parent: string; name: string; pluginId: string; requestId: string }
  | { action: 'switch-workflow'; workspaceId: string; pluginId: string }
export type InitializationRequest =
  | { action: 'start-initialization'; requestId: string; operation: InitializationOperation }
  | { action: 'initialization-status' | 'cancel-initialization'; jobId: string; offset: number }
  | { action: 'initialization-input'; jobId: string; sequence: number; data: string }
export interface InitializationSnapshot {
  jobId: string; phase: 'running' | 'ready' | 'error'; output: string; offset: number; nextOffset: number
  inputSequence: number; interactive: boolean; message?: string; result?: unknown
}
const uuid = (value: unknown): value is string => typeof value === 'string' && /^[a-f\d]{8}-(?:[a-f\d]{4}-){3}[a-f\d]{12}$/i.test(value)
export function initializationRequest(value: unknown): InitializationRequest | undefined {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return
  const data = value as Record<string, unknown>
  if (data.action === 'start-initialization' && uuid(data.requestId)) {
    const operation = creationRequest(data.operation) || workspaceOperation(data.operation)
    if (operation?.action === 'create-folder' || operation?.action === 'switch-workflow') return { action: data.action, requestId: data.requestId, operation }
  }
  if (!uuid(data.jobId)) return
  if ((data.action === 'initialization-status' || data.action === 'cancel-initialization') && Number.isSafeInteger(data.offset) && Number(data.offset) >= 0) return { action: data.action, jobId: data.jobId, offset: Number(data.offset) }
  if (data.action === 'initialization-input' && Number.isSafeInteger(data.sequence) && Number(data.sequence) > 0 && typeof data.data === 'string' && data.data.length <= 4096) return { action: data.action, jobId: data.jobId, sequence: Number(data.sequence), data: data.data }
}
