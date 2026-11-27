// ----------------------------------------------------------------------------------------------------------
// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.
// ----------------------------------------------------------------------------------------------------------

import { useMemo, useSyncExternalStore } from 'react'
import type { Context } from '@deepseek-ai/cordis'
import type {} from '@deepseek-ai/dsh-client-ui-conversation/client'
import { WorkflowSelector, type WorkflowProps } from './WorkflowSelector.tsx'

/** Older DSH declares the hero seat at root scope. Resolve its current session
 * through the public services rather than reaching into the editor or DOM. */
export function WorkflowCompat({ ctx, ...props }: WorkflowProps & { ctx: Context }) {
  return typeof props.useInput === 'function'
    ? <WorkflowSelector {...props} />
    : <LegacyWorkflow ctx={ctx} {...props} />
}

function LegacyWorkflow({ ctx, ...props }: WorkflowProps & { ctx: Context }) {
  type Input = ReturnType<Context['conversation']['input']['for']>
  const legacy = ctx as unknown as { sessions: { list: { subscribe(listener: () => void): () => void; getSnapshot(): { current?: string } }; scope(id: string): Context | undefined } }
  const sessions = useSyncExternalStore(legacy.sessions.list.subscribe, legacy.sessions.list.getSnapshot)
  const input = useMemo(() => {
    const scope = sessions.current && legacy.sessions.scope(sessions.current)
    return scope ? ctx.conversation.input.for(scope) as Input : undefined
  }, [ctx, sessions.current])
  const state = useSyncExternalStore(input?.state.subscribe ?? noSubscribe, input?.state.getSnapshot ?? noSnapshot)
  return <WorkflowSelector {...props} sessionId={sessions.current as WorkflowProps['sessionId']} useInput={select => state ? select(state) : undefined as never} inputActions={input ? {} as WorkflowProps['inputActions'] : undefined} />
}
const noSubscribe = () => () => {}
const noSnapshot = () => undefined
