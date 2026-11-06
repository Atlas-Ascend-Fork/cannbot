// ----------------------------------------------------------------------------------------------------------
// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.
// ----------------------------------------------------------------------------------------------------------

export interface ContentPlugin { id: string; title: string; aliases: Record<string, string>; resourceDirectory?: string; version?: string; packageName?: string }
export interface ContentSkill { name: string; originalName: string; pluginId: string; path: string; entry: boolean }
export interface ContentCatalog { revision?: string; commit?: string; skillsCommit?: string; plugins: ContentPlugin[]; exposedSkills: ContentSkill[] }
export interface WorkflowEntry { id: string; title: string; package: string; default: boolean }
export interface WorkflowRow extends WorkflowEntry {
  version?: string; latest?: string; previous?: string; installed: boolean; pinned: boolean; error?: string
}
export interface WorkflowDescriptor {
  schemaVersion: 1; id: string; title: string; version: string
  initialization: { kind: 'cannbot-cli'; entry: string } | { kind: 'skill-native' }
  skills: { name: string; path: string; hash: string; entry: boolean }[]
  source: { repository: string; commit: string; skillsCommit: string }
}
export interface ContentStatus {
  phase: 'idle' | 'syncing' | 'ready' | 'error' | 'initializing'
  plugins: { id: string; title: string }[]
  commit?: string; skillsCommit?: string; updatedAt?: string
  fallback: boolean; message: string; log: string
  workflows?: WorkflowRow[]; busy?: boolean; catalogVersion?: string
}
export const CONTENT_PATH = 'api/cannbot-dsh/content'
