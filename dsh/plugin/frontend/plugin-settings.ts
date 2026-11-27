// ----------------------------------------------------------------------------------------------------------
// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.
// ----------------------------------------------------------------------------------------------------------

import { createElement, Fragment, type ReactNode } from 'react'
import type { Context } from '@deepseek-ai/cordis'
import type {} from '@deepseek-ai/dsh-client-ui-plugin-manager/client'
import type { PropsLocale } from '@deepseek-ai/dsh-client-ui-slots'
import { NAMESPACE } from './locales.ts'
import { injectSlot } from './slot-compat.ts'
import { ContentCard } from './ContentCard.tsx'
import type { ContentStore } from './content-store.ts'

export function registerPluginSettings(ctx: Context, names: readonly string[], content: ContentStore, extra?: (props: PropsLocale<'cannbotDsh'>) => ReactNode) {
  ctx.inject(['remote', 'remote.pluginManager'], scoped => {
    for (const name of names) {
      scoped.effect(() => injectSlot(scoped, 'plugins.bundle.config', () => scoped.slots.register({
        name: 'plugins.bundle.config', key: name, locale: NAMESPACE,
      }, props => createElement(Fragment, null, extra?.(props), createElement(ContentCard, { ...props, content })))))
    }
  })
}
