// ----------------------------------------------------------------------------------------------------------
// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.
// ----------------------------------------------------------------------------------------------------------

/** Activate a fully assembled source installation through the normal cache validator. */
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { ContentManager } from '../src/content-manager.ts'

const [reportFile, defaults, cache] = process.argv.slice(2)
const reports = JSON.parse(readFileSync(reportFile, 'utf8')) as { name: string; directory: string }[]
const resolvePackage = (name: string) => {
  const report = reports.find(item => item.name === name)
  if (!report) throw new Error(`Missing assembled package: ${name}`)
  return join(report.directory, 'package.json')
}
const manager = new ContentManager(defaults, cache, {
  async manifest() { throw new Error('Source activation must not fetch npm packages') },
  async extract() { throw new Error('Source activation must not fetch npm packages') },
})
await manager.installDependencies(resolvePackage('@cannbot-plugin/workflow-catalog'), resolvePackage, true)
console.log(`Activated ${manager.getSource().catalog.plugins.length} workflows from current source.`)
