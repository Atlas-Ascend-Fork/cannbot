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
import { Hero, SidebarName, SidebarMark } from './Brand.tsx'
import { BoundWorkspaceWorkflow } from './BoundWorkspaceWorkflow.tsx'
import { SessionWorkflow } from './SessionWorkflow.tsx'
import { freezeSessionInputs } from './frozen-sessions.ts'
import { TaskDock } from './TaskList.tsx'
import { cannTheme } from './theme.ts'
import interfaceCss from './interface.css?inline'
import './controls.css'
import { createElement, type ReactNode } from 'react'
import { injectSlot } from './slot-compat.ts'
import { createWorkflowSelection, connectWorkflowSelection, type WorkflowSelection } from './workflow-selection.ts'
import { createContentStore, type ContentStore } from './content-store.ts'
import { registerPluginSettings } from './plugin-settings.ts'
import { registerWorkbench } from './register-workbench.ts'
import { createWorkspaceModes, type WorkspaceModes } from './workspace-modes.ts'
import { WorkspaceTree } from './WorkspaceTree.tsx'
import { WorkspaceForm } from './WorkspaceForm.tsx'
import { useStore } from './WorkspaceRows.tsx'
import { mountEmbeddedShell } from './embedded-shell.ts'
import { WorkspaceTreeBridge } from './WorkspaceTreeBridge.tsx'
import { NativeWorkspacePicker } from './NativeWorkbench.tsx'
import { NativeWorkflowPlaceholder } from './NativeWorkflowPlaceholder.tsx'

declare module '@deepseek-ai/dsh-client-ui-slots' {
  interface LocaleNamespaceMap { cannbotDsh: LocaleKey }
}
export const inject = ['slots', 'theme', 'locale', 'sessions', 'conversation']

interface ClientWorkbench {
  brand(size: number): ReactNode
  tree(wide: boolean): ReactNode
  creation(): ReactNode
  start(): () => void
  open(serverId: string, workspaceId?: string): Promise<void>
  dispose(): void
}
export interface ClientFeatures {
  configure(ctx: Context, content: ContentStore): void
  create(ctx: Context, modes: WorkspaceModes, content: ContentStore): ClientWorkbench
}
function LocalWorkspaceCreation({ modes, content }: { modes: WorkspaceModes; content: ContentStore }) {
  const state = useStore(modes), catalog = useStore(content)
  return state.creating ? createElement(WorkspaceForm, { modes, workflows: catalog.workflows, close: () => modes.setCreating(false) }) : null
}

/** Register presentation with an explicit disposer so the original entries remain live underneath. */
function mountInterface(ctx: Context, selection: WorkflowSelection, content: ContentStore, modes: WorkspaceModes, client?: ClientWorkbench): () => void {
  const style = document.createElement('style')
  style.dataset.cannbotDsh = 'interface'
  style.textContent = interfaceCss
  document.head.append(style)
  const releases = [
    ctx.theme.overrideTokens(PACKAGE, cannTheme),
    injectSlot(ctx, 'sidebar.brand.name', () => ctx.slots.register({ name: 'sidebar.brand.name', priority: -100 }, SidebarName)),
    injectSlot(ctx, 'conversation.hero.brand.mark', () => ctx.slots.register({ name: 'conversation.hero.brand.mark', priority: -100 }, Hero)),
    injectSlot(ctx, 'conversation.hero.agentPreset', () => ctx.slots.register({ name: 'conversation.hero.agentPreset', priority: -100 }, props => createElement(BoundWorkspaceWorkflow, { modes, ...('sessionId' in props && typeof props.sessionId === 'string' && { sessionId: props.sessionId }) }))),
    injectSlot(ctx, 'conversation.hero.workspace', () => ctx.slots.register({ name: 'conversation.hero.workspace', priority: -100 }, props => createElement(NativeWorkspacePicker, { ...props, modes }))),
    injectSlot(ctx, 'conversation.input.overlay', () => ctx.slots.register({ name: 'conversation.input.overlay', id: 'cannbot-workflow-placeholder' }, props => createElement(NativeWorkflowPlaceholder, { ...props, ctx, modes, selection }))),
    injectSlot(ctx, 'shell.overlay', () => ctx.slots.register({ name: 'shell.overlay', id: 'cannbot-workspace-create' }, () => client ? client.creation() : createElement(LocalWorkspaceCreation, { modes, content }))),
    injectSlot(ctx, 'conversation.input.dock', () => ctx.slots.register({ name: 'conversation.input.dock', id: 'todo', priority: -100, order: 0, locale: NAMESPACE }, TaskDock)),
    injectSlot(ctx, 'conversation.session.header.actions', () => ctx.slots.register({ name: 'conversation.session.header.actions', id: 'cannbot-session-workflow', order: -100, locale: NAMESPACE }, props => createElement(SessionWorkflow, { ...props, selection }))),
  ]
  return () => { for (const release of releases.reverse()) release(); style.remove() }
}

export function applyWorkbench(ctx: Context, features?: ClientFeatures): void {
  const content = createContentStore()
  ctx.effect(() => content.start())
  if (features) features.configure(ctx, content)
  else registerPluginSettings(ctx, ['@cannbot-plugin/cannbot-dsh-server'], content)
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
  ctx.effect(() => ctx.locale.register(NAMESPACE, { zh, en }))
  ctx.inject(['layout', 'uiWorkspace', 'workspaces'], scoped => scoped.effect(() => {
    const modes = createWorkspaceModes(scoped, features ? 'client' : 'server')
    const client = !modes.embedded ? features?.create(scoped, modes, content) : undefined
    const releases: (() => void)[] = [registerWorkbench(scoped, selection, content, modes)]
    releases.push(freezeSessionInputs(modes, {
      storeFor: id => scoped.conversation.blocks.storeFor(id as Parameters<typeof scoped.conversation.blocks.set>[0]),
      set: (id, value) => scoped.conversation.blocks.set(id as Parameters<typeof scoped.conversation.blocks.set>[0], value),
    }))
    if (modes.embedded) releases.push(mountEmbeddedShell(document))
    // Existing owners keep their child declarations. SlotCore permits one declarer
    // per child; shadowing a seat must never re-declare the native sidebar's seats.
    releases.push(injectSlot(scoped, 'sidebar.brand.mark', () => scoped.slots.register({ name: 'sidebar.brand.mark', priority: -100 }, props => client ? client.brand(props.size) : createElement(SidebarMark, props))))
    // Do not replace sidebar.workspaces: its native component must keep its
    // instance (and consumed search requests) across mode transitions.
    releases.push(injectSlot(scoped, 'shell.overlay', () => scoped.slots.register({ name: 'shell.overlay', id: 'cannbot-workspace-tree-bridge' }, () => createElement(WorkspaceTreeBridge, {
      modes, children: wide => client ? client.tree(wide) : createElement(WorkspaceTree, { ctx: scoped, modes, wide }),
    }))))
    // The official shortcut/native-menu closures call this public service method.
    // Decorate only during this plugin lifetime and preserve a later owner's replacement.
    const navigation = scoped.uiWorkspace, originalStart = navigation.startSession
    const start: typeof originalStart = (workspaceId, options) => {
      const state = modes.getSnapshot()
      if (state.mode === 'deepseek') originalStart.call(navigation, workspaceId, options)
      else if (client && state.serverId) void client.open(state.serverId, workspaceId).catch(() => modes.reportError('无法打开远端工作台，请检查连接后重试。'))
      else modes.newSession(workspaceId)
    }
    navigation.startSession = start
    releases.push(() => { if (navigation.startSession === start) navigation.startSession = originalStart })
    const originalFork = navigation.forkSession
    if (typeof originalFork === 'function') {
      const fork: typeof originalFork = async (id, onCreated, options) => {
        if (modes.getSnapshot().mode === 'deepseek') return originalFork.call(navigation, id, onCreated, options)
        // Desktop shortcuts resolve the retained local main view even while an
        // embedded remote panel is visible. Never apply that target to local data.
        if (modes.getSnapshot().serverId) throw new Error('请使用远端会话行的操作菜单。')
        if (!modes.getSnapshot().ready) throw new Error('工作区正在加载，请稍后重试。')
        const snapshot = modes.getSnapshot()
        if (snapshot.sessions.find(session => session.sessionId === id)?.frozen) throw new Error('此会话已冻结，请新建会话。')
        const workspace = snapshot.workspaces.find(item => item.sessionIds.includes(id) || item.workspaceId === snapshot.sessions.find(session => session.sessionId === id)?.workspaceId)
        if (!workspace && snapshot.sessions.some(session => session.sessionId === id)) {
          const result = await modes.operate({ action: 'fork-session', sessionId: id, ...options?.allowMigration === undefined ? {} : { allowMigration: options.allowMigration } })
          if (!result.sessionId) throw new Error('DSH 未返回可用的分支会话。')
          const child = result.sessionId as Awaited<ReturnType<typeof originalFork>>
          onCreated?.(child)
          return child
        }
        if ((modes.getSnapshot().mode === 'cannbot') !== !!workspace) throw new Error('请先切换到该会话所属模式。')
        if (!workspace) return originalFork.call(navigation, id, onCreated, options)
        const child = await originalFork.call(navigation, id, undefined, options)
        await modes.recordSession(workspace.workspaceId, child)
        onCreated?.(child)
        return child
      }
      navigation.forkSession = fork
      releases.push(() => { if (navigation.forkSession === fork) navigation.forkSession = originalFork })
    }
    const originalArchive = navigation.archiveSession
    if (typeof originalArchive === 'function') {
      const archive: typeof originalArchive = async (id, options) => {
        if (modes.getSnapshot().mode === 'deepseek') return originalArchive.call(navigation, id, options)
        if (modes.getSnapshot().serverId) throw new Error('请使用远端会话行的操作菜单。')
        if (!modes.getSnapshot().ready) throw new Error('工作区正在加载，请稍后重试。')
        const snapshot = modes.getSnapshot()
        const owned = snapshot.workspaces.some(item => item.sessionIds.includes(id)) || snapshot.sessions.some(item => item.sessionId === id)
        if ((modes.getSnapshot().mode === 'cannbot') !== owned) throw new Error('请先切换到该会话所属模式。')
        return originalArchive.call(navigation, id, options)
      }
      navigation.archiveSession = archive
      releases.push(() => { if (navigation.archiveSession === archive) navigation.archiveSession = originalArchive })
    }
    let presentation: (() => void) | undefined
    const updatePresentation = () => {
      if (modes.getSnapshot().mode === 'cannbot') presentation ??= mountInterface(scoped, selection, content, modes, client)
      else { presentation?.(); presentation = undefined }
    }
    releases.push(modes.subscribe(updatePresentation)); updatePresentation()
    if (client) releases.push(client.start())
    releases.push(() => presentation?.(), modes.start())
    return () => { for (const release of releases.reverse()) release(); client?.dispose(); modes.dispose() }
  }))
}
