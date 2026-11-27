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
import { createPluginUpdater, UPDATE_PACKAGES } from './plugin-update.ts'
import { PluginUpdateCard } from './PluginUpdateCard.tsx'
import { registerPluginSettings } from './plugin-settings.ts'
import type { ContentStore } from './content-store.ts'

export function registerPluginUpdates(ctx: Context, content: ContentStore) {
  const updater = createPluginUpdater()
  ctx.effect(() => () => updater.dispose())
  registerPluginSettings(ctx, UPDATE_PACKAGES, content, props => createElement(PluginUpdateCard, { ...props, updater }))
}
