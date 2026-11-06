// ----------------------------------------------------------------------------------------------------------
// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.
// ----------------------------------------------------------------------------------------------------------

import { createElement, Fragment } from 'react'
import type { Context } from '@deepseek-ai/cordis'
import type {} from '@deepseek-ai/dsh-client-ui-plugin-manager/client'
import type { PropsLocale } from '@deepseek-ai/dsh-client-ui-slots'
import { createPluginUpdater, UPDATE_PACKAGES } from './plugin-update.ts'
import { PluginUpdateCard } from './PluginUpdateCard.tsx'
import { NAMESPACE } from './locales.ts'
import { injectSlot } from './slot-compat.ts'
import { updateOnHost } from './host-update.ts'
import { ContentCard } from './ContentCard.tsx'
import type { ContentStore } from './content-store.ts'

/** Optional integration: old DSH versions without a Plugins page keep loading. */
export function registerPluginUpdates(ctx: Context, content?: ContentStore) {
  ctx.inject(['remote', 'remote.pluginManager'], scoped => {
    const manager = scoped.remote.pluginManager
    for (const name of UPDATE_PACKAGES) {
      const updater = createPluginUpdater({
        list: async () => unwrap(await manager.listBundles()),
        install: async spec => unwrap(await manager.installBundle(spec, { saveExact: true })),
        update: updateOnHost,
      }, name)
      scoped.effect(() => () => updater.dispose())
      scoped.effect(() => injectSlot(scoped, 'plugins.bundle.config', () => scoped.slots.register({
        name: 'plugins.bundle.config', key: name, locale: NAMESPACE,
      }, props => createElement(Fragment, null,
        createElement(PluginUpdateCard, { ...(props as PropsLocale<'cannbotDsh'>), updater }),
        content && createElement(ContentCard, { ...(props as PropsLocale<'cannbotDsh'>), content })))))
    }
  })
}
function unwrap<T>(result: { ok: true; value: T } | { ok: false; error: unknown }): T {
  if (!result.ok) throw result.error
  return result.value
}
