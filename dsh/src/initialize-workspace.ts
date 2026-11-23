// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { join, resolve } from 'node:path'
import { mkdir } from 'node:fs/promises'
import { ContentManager } from './content-manager.ts'
import { WorkspaceModes } from './workspace-mode.ts'

/** CLI initialization keeps the user's real terminal, before DSH Web is started. */
export async function initializeBeforeLaunch(directory: string, workflow: string) {
  if (process.platform !== 'linux') throw new Error('工作流终端初始化需要 Linux 环境。')
  if (!process.stdin.isTTY || !process.stdout.isTTY) throw new Error('请在交互终端中执行初始化，以便回答工作流问卷。')
  const require = createRequire(import.meta.url)
  const content = new ContentManager(fileURLToPath(new URL('../workflow-defaults.json', import.meta.url)))
  const catalog = require.resolve('@cannbot-plugin/workflow-catalog/package.json'), dependencies = createRequire(catalog)
  await content.installDependencies(catalog, name => dependencies.resolve(name + '/package.json'))
  const path = resolve(directory)
  await mkdir(path, { recursive: true })
  const unavailable = async (): Promise<never> => { throw new Error('Host is not running') }
  const modes = new WorkspaceModes(join(content.root, 'workspace-modes'), {
    available: id => content.getSource().catalog.plugins.some(item => item.id === id),
    prepare: (cwd, id) => content.prepare(cwd, id), createWorkspace: unavailable, listWorkspaces: unavailable, readSession: unavailable,
  })
  content.setPreparationGuard((cwd, id, run) => modes.withPreparation(cwd, id, run))
  await modes.prepareBeforeLaunch(path, workflow)
  console.log('工作流初始化完成，即将启动工作台。')
}
