// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

/** Link the already-installed, pinned official checkout for local development only. */
import { existsSync, mkdirSync, readdirSync, readFileSync, realpathSync, symlinkSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { project, resolveSource } from './source.mjs'
const checkout = resolveSource(process.argv[2])
const buildOnly = process.argv.includes('--build-only')
writeFileSync(join(project, '.dsh-source.json'), JSON.stringify({ path: checkout }, null, 2) + '\n')
const modules = join(project, 'node_modules')
mkdirSync(modules, { recursive: true })
function link(name, target) {
  const path = join(modules, name)
  if (existsSync(path)) return
  mkdirSync(dirname(path), { recursive: true })
  symlinkSync(realpathSync(target), path, process.platform === 'win32' ? 'junction' : 'dir')
}
for (const entry of readdirSync(join(checkout, 'node_modules'), { withFileTypes: true })) {
  if (entry.name.startsWith('.')) continue
  const path = join(checkout, 'node_modules', entry.name)
  if (entry.name.startsWith('@')) {
    for (const child of readdirSync(path)) link(`${entry.name}/${child}`, join(path, child))
  } else link(entry.name, path)
}
const workspaces = []
for (const group of ['vendor', 'packages', 'apps']) {
  for (const entry of readdirSync(join(checkout, group), { withFileTypes: true })) {
    if (!entry.isDirectory()) continue
    const path = join(checkout, group, entry.name)
    if (existsSync(join(path, 'package.json'))) workspaces.push(path)
    else for (const child of readdirSync(path, { withFileTypes: true })) {
      if (child.isDirectory() && existsSync(join(path, child.name, 'package.json'))) workspaces.push(join(path, child.name))
    }
  }
}
for (const path of workspaces) {
  const manifest = JSON.parse(readFileSync(join(path, 'package.json'), 'utf8'))
  if (manifest.name) link(manifest.name, path)
}
for (const name of buildOnly ? ['react', 'react-dom'] : ['react', 'react-dom', '@testing-library/react', '@types/react', '@types/react-dom']) {
  link(name, join(checkout, 'packages/client/ui-plugin-manager/node_modules', name))
}
console.log('Linked the official checkout for plugin development; no runtime files were changed.')
