// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

const channel = 'cannbot.embedded-workbench'
export interface EmbeddedTarget { workspaceId?: string; sessionId?: string }

export function announceEmbedded(params: URLSearchParams, event: 'ready' | 'location' | 'create', target?: EmbeddedTarget) {
  const destination = params.get('cannParentOrigin')
  if (!destination || window.parent === window || !/^http:\/\/(?:127\.0\.0\.1|localhost|\[::1\])(?::\d+)?$/.test(destination)) return
  window.parent.postMessage({ channel, event, ...target }, destination)
}

export function readEmbeddedEvent(value: unknown) {
  if (!value || typeof value !== 'object') return
  const message = value as Record<string, unknown>
  if (message.channel !== channel || !['ready', 'location', 'create'].includes(String(message.event))) return
  const { workspaceId, sessionId } = message
  const id = (value: unknown): value is string => typeof value === 'string' && value.length > 0 && value.length <= 512 && !/[\x00-\x20]/.test(value)
  if ((workspaceId !== undefined && !id(workspaceId)) || (sessionId !== undefined && (!id(sessionId) || !workspaceId))) return
  return { event: message.event, target: { ...(id(workspaceId) && { workspaceId }), ...(id(sessionId) && { sessionId }) } }
}
