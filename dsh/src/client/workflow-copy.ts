// ----------------------------------------------------------------------------------------------------------
// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.
// ----------------------------------------------------------------------------------------------------------

import { WORKFLOWS } from '../workflows.ts'
import type { LocaleKey } from './locales.ts'

/** Keep presentation consistent even when an older workflow package has a Chinese title. */
export function workflowCopy(workflow: { id: string; title: string; description?: string }, t: (key: LocaleKey) => string) {
  const known = WORKFLOWS.find(item => item.id === workflow.id)
  return { name: workflow.id, description: known ? t(known.description) : workflow.description ?? (workflow.title === workflow.id ? '' : workflow.title) }
}
