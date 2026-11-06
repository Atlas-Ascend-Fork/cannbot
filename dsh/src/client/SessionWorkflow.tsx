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
import type { PropsLocale, PropsRuntime } from '@deepseek-ai/dsh-client-ui-slots'
import type {} from '@deepseek-ai/dsh-client-ui-conversation/client'
import type { WorkflowSelection } from './workflow-selection.ts'

export type SessionWorkflowProps = Pick<PropsRuntime<'conversation.session.header.actions'>, 'sessionId'>
  & PropsLocale<'cannbotDsh'> & { selection: WorkflowSelection }

/** Read the committed selection for this header's Session, including after reload. */
export function SessionWorkflow({ sessionId, selection, t }: SessionWorkflowProps) {
  const saved = useSyncExternalStore(selection.subscribe, selection.getSnapshot)
  const workflow = saved.values[sessionId]
  if (!workflow) return null
  return <span className="cannbot-dsh-session-workflow" title={`${t('currentWorkflow')}: ${workflow}`}>
    <span>{t('currentWorkflow')}</span>
    <code>{workflow}</code>
  </span>
}
