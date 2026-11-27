// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { useEffect, useMemo, useRef, useSyncExternalStore } from 'react'
import type { Context } from '@deepseek-ai/cordis'
import type { ISessions } from '@deepseek-ai/dsh-api-session-controller/client'
import type { PropsRuntime } from '@deepseek-ai/dsh-client-ui-slots'
import type { WorkspaceModes } from './workspace-modes.ts'
import type { WorkflowSelection } from './workflow-selection.ts'
import { guideFor } from './workbench-data.ts'

/** Change only the native editor's placeholder text, never its value or styles.
 * Public composer markers avoid relying on renderer internals or CSS hashes. */
export function adaptNativePlaceholder(root: Element, example: string): () => void {
  const original = new Map<Element, { text?: string | null; attributes?: Record<string, string | null> }>()
  const restore = () => {
    for (const [node, saved] of original) {
      if ('text' in saved && node.textContent === example) node.textContent = saved.text ?? ''
      for (const [name, value] of Object.entries(saved.attributes || {})) {
        if (node.getAttribute(name) !== example) continue
        if (value === null) node.removeAttribute(name); else node.setAttribute(name, value)
      }
    }
    original.clear()
  }
  const update = () => {
    const editor = root.querySelector('[role="textbox"][data-placeholder]')
    if (!editor || editor.getAttribute('contenteditable') !== 'true' || editor.getAttribute('aria-disabled') === 'true') { restore(); return }
    const saved = original.get(editor) ?? { attributes: {} }
    for (const name of ['data-placeholder', 'aria-label']) {
      const current = editor.getAttribute(name)
      if (current !== example) { saved.attributes![name] = current; editor.setAttribute(name, example) }
    }
    original.set(editor, saved)
    for (const node of root.querySelectorAll('[data-composer-placeholder]')) {
      if (node.textContent === example) continue
      original.set(node, { text: node.textContent }); node.textContent = example
    }
  }
  const observer = new MutationObserver(update)
  observer.observe(root, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ['data-placeholder', 'aria-label', 'aria-disabled', 'contenteditable'] })
  update()
  return () => { observer.disconnect(); restore() }
}

type InputScope = Pick<PropsRuntime<'conversation.input.overlay'>, 'sessionId' | 'useInput' | 'useSession' | 'useProjection'>
export function NativeWorkflowPlaceholder({ ctx, modes, selection, sessionId, useInput, useSession, useProjection }: InputScope & {
  ctx: Context; modes: WorkspaceModes; selection: WorkflowSelection
}) {
  const marker = useRef<HTMLSpanElement>(null)
  const mode = useSyncExternalStore(modes.subscribe, modes.getSnapshot)
  const saved = useSyncExternalStore(selection.subscribe, selection.getSnapshot)
  const sessions = ctx.sessions as unknown as ISessions
  const sources = useMemo(() => ({ subscribe: (listener: () => void) => sessions.list.subscribe(listener), getSnapshot: () => sessions.list.getSnapshot() }), [sessions])
  const catalog = useSyncExternalStore(sources.subscribe, sources.getSnapshot)
  const input = useInput(snapshot => snapshot)
  const session = useSession(snapshot => snapshot)
  // The installed SDK omits plan-mode's declaration file; this is its public
  // projection shape, also consumed by DSH's own InputBar.
  const readPlan = useProjection as unknown as (key: 'plan', select: (plan: { pending: boolean; active: boolean } | undefined) => boolean) => boolean
  const planActive = readPlan('plan', plan => !!plan && (plan.pending ? !plan.active : plan.active))
  const blockSource = useMemo(() => ctx.conversation.blocks.storeFor(sessionId), [ctx, sessionId])
  const block = useSyncExternalStore(blockSource.subscribe, blockSource.getSnapshot)
  const workspace = mode.workspaces.find(item => item.sessionIds.includes(sessionId)
    || item.workspaceId === mode.sessions.find(item => item.sessionId === sessionId)?.workspaceId)
  const allowed = mode.mode === 'cannbot' && mode.ready && !!workspace && catalog.byId[sessionId]?.blank === true
    && saved.ready && !saved.pending && !saved.error && saved.values[sessionId] === workspace.pluginId
    && input?.phase === 'plain' && !planActive && !block && !session?.running && !session?.promptError && !session?.removed
  const example = workspace ? guideFor(workspace.pluginId).example : ''
  useEffect(() => {
    const root = marker.current?.closest('[data-slot="conversation.composer.bar"]')
    if (!allowed || !root || !example) return
    return adaptNativePlaceholder(root, example)
  }, [allowed, example, sessionId])
  return <span ref={marker} hidden aria-hidden="true" />
}
