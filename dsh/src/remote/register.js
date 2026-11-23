// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { createManager } from './manager.js'
import { createRouter, registerRoutes } from './routes.js'

// Optional services are scoped so Linux workbench/Skills remain usable even
// where desktop credentials or the authenticated Fetch channel are absent.
export function registerRemote(ctx, config = {}) {
  let credentials
  ctx.inject(['credentials'], scoped => { credentials = scoped.credentials; scoped.effect(() => () => { credentials = undefined }) })
  const manager = createManager({ config, readLocalRecord: key => credentials?.readRecord?.(key) })
  ctx.inject(['connection'], scoped => registerRoutes(scoped, createRouter({ manager })))
  ctx.effect(() => () => manager.tunnel.stopAll())
  return manager
}
