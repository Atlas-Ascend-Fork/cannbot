// ----------------------------------------------------------------------------------------------------------
// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.
// ----------------------------------------------------------------------------------------------------------

import type { HeroBrandMarkOwnerProps } from '@deepseek-ai/dsh-client-ui-conversation/client'
import type { SidebarBrandMarkOwnerProps } from '@deepseek-ai/dsh-client-ui-sidebar/client'
import logo from './logo.svg'

/** CANNBot brand mark: the packaged logo, scaled by the slot's requested size. */
export function Mark({ size }: { size: number }) {
  return <img src={logo} width={size} height={size} alt="" aria-hidden="true" draggable={false} data-cannbot-dsh-logo="" />
}
export function SidebarMark({ size }: SidebarBrandMarkOwnerProps) { return <Mark size={size} /> }
export function SidebarName() { return <span className="cannbot-dsh-name">CANNBot</span> }
export function Hero({ size }: HeroBrandMarkOwnerProps) {
  return <span data-cannbot-dsh-hero=""><Mark size={size} /><span>CANNBot</span></span>
}
