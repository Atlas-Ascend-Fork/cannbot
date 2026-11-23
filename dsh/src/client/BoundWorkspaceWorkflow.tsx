// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { useSyncExternalStore } from 'react'
import type { WorkspaceModes } from './workspace-modes.ts'
import { GENERAL_WORKSPACE } from '../workspace-mode-types.ts'

/** A CANNBot workspace chooses its plugin at creation, never in a blank session. */
export function BoundWorkspaceWorkflow({ modes, sessionId }: { modes: WorkspaceModes; sessionId?: string }) {
  const state = useSyncExternalStore(modes.subscribe, modes.getSnapshot)
  const workspace = sessionId
    ? state.workspaces.find(item => item.sessionIds.includes(sessionId)
      || item.workspaceId === state.sessions.find(session => session.sessionId === sessionId)?.workspaceId)
    : state.workspaces.find(item => item.workspaceId === state.selectedWorkspaceId)
  if (!workspace) return null
  if (workspace.pluginId === GENERAL_WORKSPACE) return <span className="cannbot-dsh-session-workflow">空白工作区</span>
  return <span className="cannbot-dsh-session-workflow" title={`工作区工作流：${workspace.pluginId}`}>
    <span>工作流</span><code>{workspace.pluginId}</code>
  </span>
}
