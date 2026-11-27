// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

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
