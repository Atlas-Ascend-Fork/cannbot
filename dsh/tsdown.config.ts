// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { pathToFileURL } from 'node:url'
import { editionManifest, editions } from './tools/editions.mjs'
import { resolveSource } from './tools/source.mjs'

const preset = resolve(resolveSource(), 'packages/client/tsdown.client.ts')
const { clientBundle } = await import(pathToFileURL(preset).href)
const root = import.meta.dirname
const source = JSON.parse(readFileSync(resolve(root, 'package.json'), 'utf8'))

// The DSH preset reads the package name for the browser module registration
// and the production dependency list for Host externals.
export default (environment: Record<string, unknown>) => Object.keys(editions).flatMap(edition => {
  const directory = resolve(root, '.build-cache/compiler', edition)
  mkdirSync(directory, { recursive: true })
  writeFileSync(resolve(directory, 'package.json'), JSON.stringify(editionManifest(source, edition)))
  const configs = clientBundle(directory, [], {})(environment)
  return configs.map((config: any) => ({
    ...config,
    entry: config.name?.endsWith('/client')
      ? { client: 'plugin/editions/' + edition + '/ui.ts' }
      : { index: 'plugin/editions/' + edition + '/host.ts', 'initialize-workspace': 'plugin/backend/initialize-workspace.ts' },
    outDir: edition === 'server' ? 'lib/server' : 'lib',
    clean: false,
    define: { ...config.define, 'process.env.CANNBOT_EDITION': JSON.stringify(edition) },
  }))
})
