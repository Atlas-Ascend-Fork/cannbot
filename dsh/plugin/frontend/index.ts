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
import { applyWorkbench } from './mount-workbench.ts'
import { ModeBrandMark, ModeWorkspaceTree, ModeWorkspaceCreation, SERVERS_PANEL } from './ModeSidebar.tsx'
import { createRemoteClient } from './remote/index.tsx'
import { registerPluginUpdates } from './register-updates.ts'
import { injectSlot } from './slot-compat.ts'

export { inject } from './mount-workbench.ts'

export function apply(ctx: Context): void {
  applyWorkbench(ctx, {
    configure: registerPluginUpdates,
    create(scoped, modes, content) {
      const remote = createRemoteClient(scoped, {
        onReturnLocal: () => modes.returnLocal(),
        onSelectServer: id => modes.selectServer(id),
        onCreateWorkspace: id => modes.setCreating(true, id),
      })
      const props = { ctx: scoped, modes, content, remote }
      return {
        brand: size => createElement(ModeBrandMark, { modes, size, onServers: () => scoped.layout.selectPanel(SERVERS_PANEL) }),
        tree: wide => createElement(ModeWorkspaceTree, { ...props, wide }),
        creation: () => createElement(ModeWorkspaceCreation, props),
        open: (serverId, workspaceId) => remote.open({ serverId, workspaceId }),
        start() {
          const panel = injectSlot(scoped, 'main', () => scoped.slots.register({ name: 'main', key: SERVERS_PANEL }, () => createElement(ModeWorkspaceTree, { ...props, management: true })))
          const stop = remote.start()
          return () => { stop(); panel() }
        },
        dispose: () => remote.dispose(),
      }
    },
  })
}
