// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react'
import type { Context } from '@deepseek-ai/cordis'
import type { PropsRenderFactories, PropsRenderSlots } from '@deepseek-ai/dsh-client-ui-slots'
import type { EmptyWorkspaceOwnerProps } from '@deepseek-ai/dsh-client-ui-conversation/client'
import { IconFolderCloseRegular, IconProjectAddOutlineRegular, Menu } from '@deepseek-ai/dsh-client-ui-primitives'
import type { WorkspaceModes } from './workspace-modes.ts'
import { CANNBOT_HOME } from './workspace-modes.ts'
import type { createNativeWorkbenchSession } from './native-workbench-session.ts'
import './native-workbench.css'

declare module '@deepseek-ai/dsh-client-ui-slots' {
  interface SlotMap {
    'cannbot.workbench.content': { kind: 'single'; scope: 'session-maybe' }
  }
}
type SessionPreparation = ReturnType<typeof createNativeWorkbenchSession>

/** An absent native composer is only the workspace-selection/loading surface.
 * A prepared blank opens the real resident DSH Conversation, including its header,
 * model, permission, attachment, draft and adaptive-width implementations. */
export function NativeWorkbench({ ctx, modes, preparation, SessionProvider, renderSlot }: {
  ctx: Context; modes: WorkspaceModes; preparation: SessionPreparation
} & PropsRenderSlots<'cannbot.workbench.content'>) {
  const state = useSyncExternalStore(modes.subscribe, modes.getSnapshot)
  const prepared = useSyncExternalStore(preparation.subscribe, preparation.getSnapshot)
  const panelSource = useMemo(() => ({ subscribe: (listener: () => void) => ctx.layout.panelInfo.subscribe(listener), getSnapshot: () => ctx.layout.panelInfo.getSnapshot() }), [ctx])
  const panel = useSyncExternalStore(panelSource.subscribe, panelSource.getSnapshot)
  const active = state.mode === 'cannbot' && !state.serverId && panel.activePanelId === CANNBOT_HOME
  useEffect(() => {
    if (!active || !state.ready || !state.selectedWorkspaceId || state.restoringSession || state.navigationError) return
    let current = true
    void preparation.selectWorkspace(state.selectedWorkspaceId).then(() => {
      const next = preparation.getSnapshot(), latest = modes.getSnapshot()
      if (current && next.sessionId && !next.busy && !next.error && latest.mode === 'cannbot' && !latest.serverId
        && latest.selectedWorkspaceId === next.workspaceId && ctx.layout.panelInfo.getSnapshot().activePanelId === CANNBOT_HOME) {
        if (latest.permissionWorkspaceId !== next.workspaceId) modes.openSession(next.sessionId)
      }
    })
    return () => { current = false }
  }, [active, state.ready, state.selectedWorkspaceId, state.restoringSession, state.navigationError, preparation, modes, ctx])
  if (!active) return null
  const empty = () => renderSlot('cannbot.workbench.content', {})
  const selecting = !state.selectedWorkspaceId && state.ready && !state.restoringSession && !state.navigationError
  const permissionReady = !!prepared.session && !!prepared.sessionId && !prepared.busy && !prepared.error
    && state.permissionWorkspaceId === prepared.workspaceId && state.selectedWorkspaceId === prepared.workspaceId
  return <main className="cannbot-native-home" aria-label="CANNBot工作台">
    {selecting ? <SessionProvider session={undefined} empty={empty}>{empty()}</SessionProvider>
      : !prepared.error && !state.navigationError && <section className="cannbot-workspace-preparing" role="status" aria-live="polite" aria-busy={!permissionReady}>
        {!permissionReady && <span className="cannbot-preparing-spinner" aria-hidden="true" />}
        <strong>{permissionReady ? '工作区已准备就绪' : '正在准备工作区…'}</strong>
        <p>{permissionReady ? '完成权限选择后即可开始对话。' : '正在加载会话与工作流配置，完成后即可开始对话。'}</p>
      </section>}
    {permissionReady && <WorkflowPermissionDialog grant={async () => {
        const result = await prepared.session!.binding.session.command('/permission danger-full-access')
        if (!result.ok || !result.value.matched) throw new Error('权限设置未完成，请重试。')
      }} complete={() => { modes.finishPermissionRequest(); modes.openSession(prepared.sessionId!) }} />}
    {(prepared.error || state.navigationError) && <p className="cannbot-native-notice" role="alert">{prepared.error || state.navigationError}{prepared.error && <button type="button" onClick={() => void preparation.retry().then(() => {
      const next = preparation.getSnapshot()
      if (next.sessionId && !next.error && modes.getSnapshot().mode === 'cannbot' && !modes.getSnapshot().serverId
        && modes.getSnapshot().permissionWorkspaceId !== next.workspaceId && modes.getSnapshot().selectedWorkspaceId === next.workspaceId && ctx.layout.panelInfo.getSnapshot().activePanelId === CANNBOT_HOME) modes.openSession(next.sessionId)
    })}>重试</button>}</p>}
  </main>
}

export function WorkflowPermissionDialog({ grant, complete }: { grant(): Promise<void>; complete(): void }) {
  const dialog = useRef<HTMLDialogElement>(null), alive = useRef(true), running = useRef(false)
  const [saving, setSaving] = useState(false), [error, setError] = useState('')
  useEffect(() => { alive.current = true; dialog.current?.showModal(); return () => { alive.current = false } }, [])
  const accept = async () => {
    if (running.current) return
    running.current = true; setSaving(true); setError('')
    try { await grant(); if (alive.current) complete() }
    catch { if (alive.current) setError('权限设置未完成，请重试，或保留当前权限继续。') }
    finally { running.current = false; if (alive.current) setSaving(false) }
  }
  return <dialog ref={dialog} className="cwb-directory cb-workflow-permission" aria-label="工作流权限" onCancel={event => { event.preventDefault(); if (!saving) complete() }}>
    <h2>工作流权限</h2><p>对于工作流开发，建议授予完全权限，是否授予？</p>
    {error && <p role="alert" className="cwb-error">{error}</p>}
    <footer><button type="button" className="cwb-text-button" disabled={saving} onClick={complete}>暂不授予</button><button type="button" className="cwb-primary" disabled={saving} onClick={() => void accept()}>{saving ? '正在设置…' : '授予完全权限'}</button></footer>
  </dialog>
}

/** The public embedded occurrence owns its own hero centering, with no private
 * main-root CSS dependency. It is inert until a CANNBot workspace is selected. */
export function NativeWorkbenchEmpty({ renderFactorySlot }: PropsRenderFactories) {
  return renderFactorySlot('conversation.content', { variant: 'embedded', phase: 'hero', hero: true })
}

/** Keep the native chip and menu placement; only constrain CANNBot membership and
 * route selection through the safe blank-session preparation path. */
export function NativeWorkspacePicker({ modes, open, anchorRef, selectedId, onClose }: EmptyWorkspaceOwnerProps & { modes: WorkspaceModes }) {
  const state = useSyncExternalStore(modes.subscribe, modes.getSnapshot)
  return <Menu open={open} anchor={null} portal minWidthFromAnchor autoFocus
    getAnchorRect={() => anchorRef?.current?.getBoundingClientRect() ?? null}
    selectedId={selectedId || state.selectedWorkspaceId} onClose={onClose}
    items={[
      ...state.workspaces.map(workspace => ({ id: workspace.workspaceId, label: workspace.title === 'default-workspace' ? '默认工作区' : workspace.title, icon: <IconFolderCloseRegular size={16} />, disabled: !state.ready })),
      ...(state.workspaces.length ? [{ type: 'separator' as const, id: 'cann-workspace-divider' }] : []),
      { id: 'cann-workspace-create', label: '创建工作区', icon: <IconProjectAddOutlineRegular size={16} />, disabled: !state.ready },
    ]} onSelect={id => {
      onClose()
      if (id === 'cann-workspace-create') modes.setCreating(true)
      else if (state.workspaces.some(workspace => workspace.workspaceId === id)) modes.newSession(id)
    }} />
}
