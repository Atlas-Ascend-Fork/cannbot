// ----------------------------------------------------------------------------------------------------------
// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.
// ----------------------------------------------------------------------------------------------------------

/** Browser companion using the existing DSH theme, settings and UI slots. */
import type { Context } from '@deepseek-ai/cordis'
import type {} from '@deepseek-ai/dsh-client-locale/client'
import type {} from '@deepseek-ai/dsh-client-ui-renderer/client'
import type {} from '@deepseek-ai/dsh-client-ui-sidebar/client'
import type {} from '@deepseek-ai/dsh-client-ui-conversation/client'
import type {} from '@deepseek-ai/dsh-client-ui-theme/client'
import { en, zh, NAMESPACE, PACKAGE, type LocaleKey } from './locales.ts'
import { SidebarMark, SidebarName, Hero } from './Brand.tsx'
import { WorkflowCompat } from './WorkflowCompat.tsx'
import { SessionWorkflow } from './SessionWorkflow.tsx'
import { TaskDock } from './TaskList.tsx'
import { cannTheme } from './theme.ts'
import interfaceCss from './interface.css?inline'
import './controls.css'
import { createElement } from 'react'
import { InterfaceToggle } from './InterfaceToggle.tsx'
import { createPresentationController } from './presentation.ts'
import { injectSlot } from './slot-compat.ts'
import { createWorkflowSelection, connectWorkflowSelection, type WorkflowSelection } from './workflow-selection.ts'
import { registerPluginUpdates } from './register-updates.ts'
import { createContentStore, type ContentStore } from './content-store.ts'
import { registerWorkbench } from './register-workbench.ts'

declare module '@deepseek-ai/dsh-client-ui-slots' {
  interface LocaleNamespaceMap { cannbotDsh: LocaleKey }
}
export const inject = ['slots', 'theme', 'locale', 'sessions', 'conversation']

/** Register presentation with an explicit disposer so the original entries remain live underneath. */
function mountInterface(ctx: Context, selection: WorkflowSelection, content: ContentStore): () => void {
  const style = document.createElement('style')
  style.dataset.cannbotDsh = 'interface'
  style.textContent = interfaceCss
  document.head.append(style)
  const releases = [
    ctx.theme.overrideTokens(PACKAGE, cannTheme),
    injectSlot(ctx, 'sidebar.brand.mark', () => ctx.slots.register({ name: 'sidebar.brand.mark', priority: -100 }, SidebarMark)),
    injectSlot(ctx, 'sidebar.brand.name', () => ctx.slots.register({ name: 'sidebar.brand.name', priority: -100 }, SidebarName)),
    injectSlot(ctx, 'conversation.hero.brand.mark', () => ctx.slots.register({ name: 'conversation.hero.brand.mark', priority: -100 }, Hero)),
    injectSlot(ctx, 'conversation.hero.agentPreset', () => ctx.slots.register({ name: 'conversation.hero.agentPreset', priority: -100, locale: NAMESPACE }, props => createElement(WorkflowCompat, { ...props, ctx, selection, content }))),
    registerWorkbench(ctx, selection, content),
  ]
  return () => { for (const release of releases.reverse()) release(); style.remove() }
}

export function apply(ctx: Context): void {
  const content = createContentStore()
  ctx.effect(() => content.start())
  registerPluginUpdates(ctx, content)
  const selection = createWorkflowSelection((sessionId, reason) => {
    const blocks = ctx.conversation.blocks
    const id = sessionId as Parameters<typeof blocks.set>[0]
    const store = blocks.storeFor(id)
    // Do not replace a block owned by another DSH plugin.
    if (store.getSnapshot() !== undefined) return () => {}
    const block = { reason }
    blocks.set(id, block)
    return () => { if (store.getSnapshot() === block) blocks.set(id, undefined) }
  }, content.prepare)
  connectWorkflowSelection(ctx, selection)
  ctx.effect(() => () => selection.dispose())
  ctx.effect(() => ctx.locale.register(NAMESPACE, { zh, en, ja: en, es: en, fr: en, de: en, ru: en, pt: en }))
  ctx.effect(() => injectSlot(ctx, 'conversation.input.dock', () => ctx.slots.register({
    name: 'conversation.input.dock', id: 'todo', priority: -100, order: 0, locale: NAMESPACE,
  }, TaskDock)))
  ctx.effect(() => injectSlot(ctx, 'conversation.session.header.actions', () => ctx.slots.register({
    name: 'conversation.session.header.actions', id: 'cannbot-session-workflow', order: -100, locale: NAMESPACE,
  }, props => createElement(SessionWorkflow, { ...props, selection }))))
  ctx.effect(() => {
    const controller = createPresentationController(() => mountInterface(ctx, selection, content))
    const releaseToggle = injectSlot(ctx, 'sidebar.footer.action', () => ctx.slots.register({
      name: 'sidebar.footer.action', id: 'cannbot-dsh-interface', order: -100,
    }, props => createElement(InterfaceToggle, { ...props, controller })))
    return () => { releaseToggle(); controller.dispose() }
  })
}
