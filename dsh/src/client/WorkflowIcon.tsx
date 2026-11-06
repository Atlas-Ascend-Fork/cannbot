// ----------------------------------------------------------------------------------------------------------
// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.
// ----------------------------------------------------------------------------------------------------------

import * as primitives from '@deepseek-ai/dsh-client-ui-primitives'
import type { ComponentType } from 'react'

/** The exact icon component used by DSH's original Standard mode selector. */
export function WorkflowIcon({ size = 16 }: { size?: number }) {
  const icons = primitives as unknown as Record<string, ComponentType<{ size?: number }>>
  const Icon = icons.IconAgentPresetOutlineRegular ?? icons.IconAgentPresetOutline16 ?? icons.IconRefreshOutline16
  return Icon ? <Icon size={size} /> : null
}

export function ChevronIcon({ size = 12 }: { size?: number }) {
  const icons = primitives as unknown as Record<string, ComponentType<{ size?: number }>>
  const Icon = icons.IconChevronDownOutlineRegular ?? icons.IconChevronDownOutline14
  return Icon ? <Icon size={size} /> : <svg width={size} height={size} viewBox="0 0 12 12" fill="none" aria-hidden="true"><path d="m3 4.5 3 3 3-3" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" /></svg>
}
