// ----------------------------------------------------------------------------------------------------------
// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.
// ----------------------------------------------------------------------------------------------------------

import { createElement } from 'react'
import type { Context } from '@deepseek-ai/cordis'
import type { ISessions } from '@deepseek-ai/dsh-api-session-controller/client'
import type {} from '@deepseek-ai/dsh-client-ui-layout/client'
import type {} from '@deepseek-ai/dsh-client-ui-workspace/client'
import type { WorkflowSelection } from './workflow-selection.ts'
import type { ContentStore } from './content-store.ts'
import { Workbench, HOME_PANEL, LIBRARY_PANEL } from './Workbench.tsx'
import { WorkbenchIcon } from './WorkbenchIcon.tsx'
import { createWorkbenchState } from './workbench-state.ts'
import { injectSlot } from './slot-compat.ts'
import './workbench.css'

/** Optional public-slot integration: older DSH keeps its existing branded conversation. */
export function registerWorkbench(ctx: Context, selection: WorkflowSelection, content: ContentStore): () => void {
  const fiber = ctx.inject(['layout', 'uiWorkspace', 'workspaces'], scoped => {
    if (typeof scoped.uiWorkspace.openSession !== 'function' || typeof (scoped.sessions as unknown as ISessions).retain !== 'function'
      || typeof scoped.conversation.input.requestDraftInitialization !== 'function') return
    scoped.effect(() => {
      const store = createWorkbenchState()
      const releases: (() => void)[] = []
      for (const [id, library] of [[HOME_PANEL, false], [LIBRARY_PANEL, true]] as const) {
        releases.push(injectSlot(scoped, 'main', () => scoped.slots.register({ name: 'main', key: id }, () => createElement(Workbench, { ctx: scoped, selection, content, store, library }))))
        if (!library) releases.push(injectSlot(scoped, 'sidebar.panellist', () => scoped.slots.register({ name: 'sidebar.panellist', id, order: -100, label: 'CANNBot工作台' }, ({ size }) => createElement(WorkbenchIcon, { name: 'grid', size }))))
      }
      return () => {
        store.dispose()
        if ([HOME_PANEL, LIBRARY_PANEL].includes(scoped.layout.panelInfo.getSnapshot().activePanelId!)) scoped.layout.selectPanel(null)
        for (const release of releases.reverse()) release()
      }
    })
  })
  return () => { if (typeof fiber?.dispose === 'function') void fiber.dispose() }
}
