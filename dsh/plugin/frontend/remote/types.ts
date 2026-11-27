// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import type { CANNBotWorkspaceOperation } from '../../contracts/workspace-mode-types.ts'

export interface RemoteServer {
  id: string
  label: string
  alias: string
  connected: boolean
  localPort?: number
  remotePort?: number
  loginSync?: { status: string; message: string }
}
export interface RemoteWorkspace {
  workspaceId: string
  path: string
  title: string
  pluginId: string
  sessionIds?: string[]
}
export interface RemoteSession {
  frozen?: boolean
  id: string
  title: string
  workspaceId: string
  updatedAt?: number | string
  blank?: boolean
  running?: boolean
  pinned?: boolean
  pinOrder?: number
  archived?: boolean
  ungrouped?: boolean
}
export interface RemoteTree { workspaces: RemoteWorkspace[]; sessions: RemoteSession[] }
export interface RemoteOperationResult { tree: RemoteTree; sessionId?: string }
export interface RemoteTarget { serverId: string; workspaceId?: string; sessionId?: string; createWorkspace?: boolean; recommendPermissions?: boolean }
export interface RemoteSnapshot {
  servers: RemoteServer[]
  selectedServerId?: string
  busy: boolean
  error: string
  progress: string[]
  syncLogin: boolean
  revision: number
  target: RemoteTarget | null
  status: 'idle' | 'loading' | 'ready' | 'error'
  notice: string
  addingServer?: boolean
  disconnectingServerIds?: readonly string[]
  removingServerIds?: readonly string[]
  orderingServers?: boolean
  passwordRequests?: readonly { serverId: string; challengeId: string; prompt: string; retry: boolean }[]
}
export interface RemoteClient {
  getSnapshot(): RemoteSnapshot
  subscribe(listener: () => void): () => void
  start(): () => void
  connect(serverId: string): Promise<void>
  cancelConnect(serverId: string): Promise<void>
  /** Close this desktop's SSH tunnel; never stop the remote DSH or its tasks. */
  disconnect(serverId: string): Promise<void>
  removeServer(serverId: string): Promise<void>
  reorderServers(ids: string[]): Promise<void>
  getTree(serverId: string): Promise<RemoteTree>
  operate(serverId: string, operation: CANNBotWorkspaceOperation): Promise<RemoteOperationResult>
  renameServer(serverId: string, label: string): Promise<void>
  open(target: RemoteTarget): Promise<void>
  returnLocal(): void
  showConnections(onAdded?: (id: string) => void): void
  dispose(): void
}
