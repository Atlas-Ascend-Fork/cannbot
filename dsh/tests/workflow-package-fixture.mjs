// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { mkdtempSync, mkdirSync, readFileSync } from 'node:fs'
import { resolve, join } from 'node:path'
import { createRequire } from 'node:module'
import { ContentManager } from '../plugin/backend/content-manager.ts'
const pacote = createRequire(import.meta.url)('pacote')
export async function createVerifiedWorkflowCache() {
  mkdirSync('.acceptance-workflow-tests', { recursive: true })
  const root = mkdtempSync(resolve('.acceptance-workflow-tests/real-')), cache = join(root, 'cache'), workspace = join(root, 'workspace')
  mkdirSync(workspace)
  if (process.env.CANNBOT_TEST_HOST_PACKAGE) {
    const dependencies = createRequire(join(resolve(process.env.CANNBOT_TEST_HOST_PACKAGE), 'package.json'))
    const catalogFile = dependencies.resolve('@cannbot-plugin/workflow-catalog/package.json')
    const packages = createRequire(catalogFile)
    const manager = new ContentManager(resolve('workflow-defaults.json'), cache, {
      async manifest() { throw new Error('Published Host fixture must remain offline') },
      async extract() { throw new Error('Published Host fixture must remain offline') },
    })
    await manager.installDependencies(catalogFile, name => packages.resolve(name + '/package.json'))
    return { root, cache, workspace, manager }
  }
  const reports = JSON.parse(readFileSync(new URL('../dist/workflow-releases/release-1.0.0-report.json', import.meta.url), 'utf8'))
  const manifest = report => ({ ...JSON.parse(readFileSync(join(report.directory, 'package.json'), 'utf8')), dist: { integrity: report.integrity, tarball: `https://registry.npmjs.org/${report.name}/-/${report.version}.tgz` } })
  const fetcher = {
    async manifest(spec) { const report = reports.find(item => spec === `${item.name}@latest` || spec === `${item.name}@${item.version}`); if (!report) throw new Error('Unknown fixture package'); return manifest(report) },
    async extract(spec, destination, options) { const report = reports.find(item => manifest(item).dist.tarball === spec); if (!report) throw new Error('Unknown fixture tarball'); return pacote.extract(report.tarball, destination, options) },
  }
  const manager = new ContentManager(resolve('workflow-defaults.json'), cache, fetcher)
  await manager.sync()
  return { root, cache, workspace, manager }
}
