// ----------------------------------------------------------------------------------------------------------
// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.
// ----------------------------------------------------------------------------------------------------------

import { createRequire } from 'node:module'
export const WORKFLOW_SCOPE = '@cannbot-plugin/workflow-'
export const CATALOG_PACKAGE = '@cannbot-plugin/workflow-catalog'
export const REGISTRY = 'https://registry.npmjs.org/'
export const MIRROR = 'https://registry.npmmirror.com/'
export const validId = (id: string) => typeof id === 'string' && /^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(id)
export const validVersion = (version: string) => typeof version === 'string' && /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/.test(version)
export interface PackageManifest {
  name: string; version: string; dist: { integrity: string; tarball: string }
  dependencies?: Record<string, string>; optionalDependencies?: Record<string, string>; scripts?: Record<string, string>
  cannbotWorkflow?: { schemaVersion: number; id: string }
  cannbotWorkflowCatalog?: { schemaVersion: number; workflows: unknown[] }
}
export interface NpmFetcher {
  manifest(spec: string, options: Record<string, unknown>): Promise<PackageManifest>
  extract(spec: string, destination: string, options: Record<string, unknown>): Promise<unknown>
}
export const npmFetcher = () => createRequire(import.meta.url)('pacote') as NpmFetcher
export function validateTarball(manifest: PackageManifest) {
  if (!validVersion(manifest.version) || !/^sha512-[A-Za-z0-9+/]+={0,2}$/.test(manifest.dist?.integrity ?? '')) throw new Error('Package version or integrity is invalid')
  const url = new URL(manifest.dist.tarball)
  if (url.protocol !== 'https:' || !['registry.npmjs.org', 'registry.npmmirror.com'].includes(url.hostname) || url.username || url.password || url.port) throw new Error('Unexpected package download origin')
}
