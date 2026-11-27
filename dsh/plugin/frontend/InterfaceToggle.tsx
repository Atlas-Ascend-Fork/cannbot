// ----------------------------------------------------------------------------------------------------------
// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.
// ----------------------------------------------------------------------------------------------------------

import { useSyncExternalStore } from 'react'
import type { PropsRuntime } from '@deepseek-ai/dsh-client-ui-slots'
import type { PresentationController } from './presentation.ts'
import { Mark } from './Brand.tsx'
import { PRODUCT } from './locales.ts'

export function InterfaceToggle({ wide, controller }: PropsRuntime<'sidebar.footer.action'> & { controller: PresentationController }) {
  const enabled = useSyncExternalStore(controller.subscribe, controller.getSnapshot, controller.getSnapshot)
  return <div className={`cannbot-dsh-toggle${wide ? '' : ' cannbot-dsh-toggle-compact'}`}>
    <span className="cannbot-dsh-toggle-name" title={PRODUCT}><Mark size={20} />{wide && <span>{PRODUCT}</span>}</span>
    <button type="button" role="switch" aria-label={PRODUCT} aria-checked={enabled} title={PRODUCT}
      className="cannbot-dsh-switch" onClick={() => controller.setEnabled(!enabled)}><span /></button>
  </div>
}
