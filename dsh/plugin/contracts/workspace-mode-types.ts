// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

/** Shared wire contract. Unregistered workspaces and sessions belong to DeepSeek. */
export const CANNBOT_WORKSPACES_PATH = 'api/cannbot-dsh/workspaces'
/** Workspace ownership marker, never a workflow package or Skill. */
// Keep the persisted ID for existing blank workspaces; public name: blank Ascend workspace.
export const GENERAL_WORKSPACE = 'general'
export interface CANNBotWorkspace {
  workspaceId: string
  path: string
  title: string
  pluginId: string
  sessionIds: string[]
  /** The directory was already registered before its explicit CANNBot setup. */
  sharedWithDeepSeek: boolean
}
export interface CANNBotSession {
  frozen?: boolean
  sessionId: string
  workspaceId: string
  pluginId: string
  title?: string
  updatedAt?: string
  /** Native list facts; absent when an older Host cannot provide them. */
  blank?: boolean
  running?: boolean
  archived?: boolean
  pinned?: boolean
  /** Zero-based position in the native pinnedSessionIds sequence. */
  pinOrder?: number
  /** Its CANNBot owner receipt remains, but the native workspace was removed. */
  ungrouped?: boolean
}
export interface CANNBotWorkspaceTree {
  platform?: string
  mode: 'cannbot'
  workspaces: CANNBotWorkspace[]
  sessions: CANNBotSession[]
}
export type CANNBotWorkspaceRequest =
  | { action: 'create'; path: string; pluginId: string }
  | { action: 'session' | 'record-session'; workspaceId: string; sessionId: string }
  | CANNBotWorkspaceOperation
export type CANNBotWorkspaceOperation =
  | { action: 'switch-workflow'; workspaceId: string; pluginId: string }
  | { action: 'rename-workspace'; workspaceId: string; title: string }
  | { action: 'remove-workspace'; workspaceId: string }
  | { action: 'rename-session'; sessionId: string; title: string }
  | { action: 'fork-session'; sessionId: string; allowMigration?: boolean }
  | { action: 'pin-session' | 'unpin-session' | 'unarchive-session'; sessionId: string }
  | { action: 'archive-session'; sessionId: string; stopActivity?: boolean }
export interface CANNBotOperationResult { ok: true; sessionId?: string }
export interface CANNBotSessionActivity { kind: string; items?: { id: string; label?: string }[] }
export function sessionActivity(value: unknown): CANNBotSessionActivity[] {
  if (!Array.isArray(value)) return []
  const clean = (value: unknown) => typeof value === 'string' ? value.slice(0, 512).replace(/[\x00-\x1f\x7f]/g, '').replace(/https?:\/\/[^\s]+/gi, '[地址]').replace(/(token\s*[=:]\s*)[^\s&]+/gi, '$1[已隐藏]') : ''
  return value.slice(0, 100).flatMap(entry => {
    if (!entry || typeof entry !== 'object' || typeof entry.kind !== 'string') return []
    const kind = clean(entry.kind)
    if (!kind) return []
    const items = Array.isArray(entry.items) ? entry.items.slice(0, 100).flatMap((item: Record<string, unknown>) => {
      if (!item || typeof item.id !== 'string' || !clean(item.id)) return []
      return [{ id: clean(item.id), ...(typeof item.label === 'string' ? { label: clean(item.label) } : {}) }]
    }) : undefined
    return [{ kind, ...(items ? { items } : {}) }]
  })
}

/** Project only the fixed operation contract; never forward arbitrary URL/body fields. */
export function workspaceOperation(value: unknown): CANNBotWorkspaceOperation | undefined {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return
  const data = value as Record<string, unknown>
  const id = (value: unknown): value is string => typeof value === 'string' && value.length > 0 && value.length <= 2000 && !/[\s\x00-\x1f\x7f]/.test(value)
  const title = (value: unknown): value is string => typeof value === 'string' && value.trim().length > 0 && value.length <= 2000 && !/[\x00-\x1f\x7f]/.test(value)
  if (data.action === 'rename-workspace' && id(data.workspaceId) && title(data.title)) return { action: data.action, workspaceId: data.workspaceId, title: data.title.trim() }
  if (data.action === 'remove-workspace' && id(data.workspaceId)) return { action: data.action, workspaceId: data.workspaceId }
  if (data.action === 'switch-workflow' && id(data.workspaceId) && typeof data.pluginId === 'string' && /^[\w-]{1,100}$/.test(data.pluginId)) return { action: data.action, workspaceId: data.workspaceId, pluginId: data.pluginId }
  if (!id(data.sessionId)) return
  if (data.action === 'rename-session' && title(data.title)) return { action: data.action, sessionId: data.sessionId, title: data.title.trim() }
  if (data.action === 'fork-session' && (data.allowMigration === undefined || typeof data.allowMigration === 'boolean')) return { action: data.action, sessionId: data.sessionId, ...(typeof data.allowMigration === 'boolean' ? { allowMigration: data.allowMigration } : {}) }
  if (data.action === 'pin-session' || data.action === 'unpin-session' || data.action === 'unarchive-session') return { action: data.action, sessionId: data.sessionId }
  if (data.action === 'archive-session' && (data.stopActivity === undefined || typeof data.stopActivity === 'boolean')) return { action: data.action, sessionId: data.sessionId, ...(data.stopActivity === true ? { stopActivity: true } : {}) }
}
export interface CANNBotWorkspaceCreated { workspace: CANNBotWorkspace }
export interface CANNBotSessionRecorded { ok: true; session: CANNBotSession }
