// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { useEffect, useMemo, useState, type ReactNode } from 'react'
import type { Context } from '@deepseek-ai/cordis'
import type { ISessions } from '@deepseek-ai/dsh-api-session-controller/client'
import type { SessionId } from '@deepseek-ai/dsh-session/types'
import type { WorkspaceId } from '@deepseek-ai/dsh-api-workspace-controller/client'
import type { WorkspaceModes } from './workspace-modes.ts'
import { WorkbenchIcon } from './WorkbenchIcon.tsx'
import { ArchivedViewMenu, type ArchivedFilter, type SidebarOperation, type SidebarReadback } from './SidebarActions.tsx'
import { createSidebarNotices, SidebarNotice, type SidebarNotices } from './SidebarNotice.tsx'
import { NewWorkspaceAction, WorkspaceRows, toggleSet, useStore, type TreeSession } from './WorkspaceRows.tsx'
import './modes.css'

export interface ServerListContext {
  archivedFilter: ArchivedFilter
  notices: SidebarNotices
  showArchived(): void
}
export interface WorkspaceTreeProps {
  ctx: Context
  modes: WorkspaceModes
  wide?: boolean
}
export function WorkspaceTree({ ctx, modes, wide = true, managementHeader, renderServers, onReturnLocal }: WorkspaceTreeProps & {
  managementHeader?: ReactNode
  renderServers?(view: ServerListContext): ReactNode
  onReturnLocal?(): void
}) {
  const state = useStore(modes)
  const management = !!managementHeader
  const panel = useStore(ctx.layout.panelInfo)
  const workspaceState = useStore(ctx.workspaces.list)
  const sessionState = useStore((ctx.sessions as unknown as ISessions).list)
  const [closed, setClosed] = useState<Set<string>>(new Set())
  const [archivedFilter, setArchivedFilter] = useState<ArchivedFilter>('default')
  const notices = useMemo(createSidebarNotices, [])
  useEffect(() => () => notices.dispose(), [notices])
  useEffect(() => { if (state.mode !== 'cannbot') notices.clear() }, [notices, state.mode])
  useEffect(() => { if (modes.embedded && wide) ctx.layout.toggleSidebar() }, [ctx, modes, wide])
  const [localReadRevision, setLocalReadRevision] = useState(0)
  useEffect(() => { if (state.ready && !state.error) setLocalReadRevision(value => value + 1) }, [state.workspaces, state.sessions, state.ready, state.error])
  const liveWorkspaces = new Map(workspaceState.items.map(item => [item.workspaceId as string, item]))
  const workspaces = state.ready ? state.workspaces.filter(item => workspaceState.phase !== 'ready' || liveWorkspaces.has(item.workspaceId)).map(item => ({ ...item, title: liveWorkspaces.get(item.workspaceId)?.title || item.title })) : []
  const archived = new Set<string>(workspaceState.archivedSessionIds)
  const pins: readonly string[] = workspaceState.pinnedSessionIds || []
  const summaries = sessionState.byId as Record<string, (typeof sessionState.byId)[keyof typeof sessionState.byId]>
  const sessions: TreeSession[] = !state.ready ? [] : state.sessions.filter(item => summaries[item.sessionId]?.origin !== 'subagent').map(item => ({ ...item, id: item.sessionId, title: summaries[item.sessionId]?.title || item.title || '新会话', updatedAt: summaries[item.sessionId]?.updatedAt || item.updatedAt, blank: summaries[item.sessionId]?.blank ?? item.blank, running: summaries[item.sessionId]?.running ?? item.running, archived: workspaceState.phase === 'ready' ? archived.has(item.sessionId) : item.archived, pinned: pins.includes(item.sessionId), pinOrder: pins.indexOf(item.sessionId) }))
  const currentBlankId = Object.values(summaries).find(summary => summary.retainedBy?.mainView)?.id as string | undefined
  const local = (action: () => void) => { if (state.serverId) onReturnLocal?.(); action() }
  const open = (session: TreeSession) => { if (session.archived) notices.archivedNotOpenable(); else local(() => modes.openSession(session.id)) }
  const create = (id: string) => local(() => modes.newSession(id))
  const add = () => modes.setCreating(true)
  const runLocal: SidebarOperation = async operation => {
    const announceArchive = () => { if (operation.action === 'archive-session' && modes.getSnapshot().mode === 'cannbot') notices.archived({ sessionId: operation.sessionId, stopped: operation.stopActivity, undo: () => runLocal({ action: 'unarchive-session', sessionId: operation.sessionId }), showArchived: () => setArchivedFilter('only') }) }
    switch (operation.action) {
      case 'rename-workspace': await ctx.workspaces.rename(operation.workspaceId as WorkspaceId, operation.title); break
      case 'remove-workspace': {
        const before = modes.getSnapshot(), beforePanel = ctx.layout.panelInfo.getSnapshot().activePanelId
        await ctx.workspaces.delete(operation.workspaceId as WorkspaceId)
        const after = modes.getSnapshot()
        if (before.mode === 'cannbot' && after.mode === 'cannbot' && !before.serverId && !after.serverId && before.selectedWorkspaceId === operation.workspaceId && after.selectedWorkspaceId === operation.workspaceId && before.activeSessionId === after.activeSessionId && ctx.layout.panelInfo.getSnapshot().activePanelId === beforePanel) {
          modes.selectWorkspace(''); modes.newSession()
        }
        break
      }
      case 'rename-session': {
        const result = await (ctx.sessions as unknown as ISessions).using(operation.sessionId as SessionId, { source: 'workspaceOperation' }, reference => reference.binding.session.rename(operation.title))
        if (!result.ok) throw new Error('重命名未完成，请重试。')
        break
      }
      case 'pin-session': await ctx.uiWorkspace.pinSession(operation.sessionId as SessionId); break
      case 'unpin-session': await ctx.uiWorkspace.unpinSession(operation.sessionId as SessionId); break
      case 'archive-session': {
        // The remote panel keeps a local native main reference. Only explicit
        // local-row operations may reach this Host route while that panel is open.
        if (modes.getSnapshot().serverId) { await modes.operate(operation); announceArchive(); return }
        await ctx.uiWorkspace.archiveSession(operation.sessionId as SessionId, operation.stopActivity ? { stopActivity: true } : undefined); break
      }
      case 'unarchive-session': await ctx.uiWorkspace.unarchiveSession(operation.sessionId as SessionId); break
      case 'fork-session': {
        // The Host preserves CANNBot ownership even for a removed workspace's session.
        const before = modes.getSnapshot(), beforePanel = ctx.layout.panelInfo.getSnapshot().activePanelId
        const result = await modes.operate(operation), after = modes.getSnapshot()
        if (result.sessionId && before.mode === after.mode && before.serverId === after.serverId && before.activeSessionId === after.activeSessionId && before.selectedWorkspaceId === after.selectedWorkspaceId && ctx.layout.panelInfo.getSnapshot().activePanelId === beforePanel) local(() => modes.openSession(result.sessionId!))
        return
      }
    }
    await modes.refreshAfterOperation()
    announceArchive()
  }
  const localReadback: SidebarReadback = { revision: localReadRevision, refresh: async () => { await modes.refreshAfterOperation(); const error = modes.getSnapshot().error; if (error) throw new Error(error) } }
  const localRows = <WorkspaceRows platform={state.platform} workspaces={workspaces} allWorkspaces={workspaceState.items} sessions={sessions} currentBlankId={currentBlankId} activeSessionId={!state.serverId && panel.activePanelId === null ? state.activeSessionId : undefined} activeWorkspaceId={!state.serverId ? state.selectedWorkspaceId : undefined} closed={closed} toggle={id => setClosed(previous => toggleSet(previous, id))} open={open} create={create} run={runLocal} readback={localReadback} archivedFilter={archivedFilter} copyFeedback={ok => { if (modes.getSnapshot().mode === 'cannbot') notices.copied(ok) }} />
  // DeepSeek uses its original workspace browser; only CANNBot mounts this tree.
  if (modes.embedded || state.mode !== 'cannbot') return null
  if (!wide) return <button className="cb-icon-button" aria-label="展开工作区列表" onClick={() => ctx.layout.toggleSidebar()}><WorkbenchIcon name="folder" /></button>
  return <section className={`cb-workspaces${management ? ' cb-server-page' : ''}`} aria-label={management ? '服务器管理' : 'CANNBot工作区'}>
    <div className="cb-workspaces-heading"><h2>{management ? '服务器' : '工作区'}</h2><span className="cb-heading-actions">{management ? managementHeader : <><ArchivedViewMenu value={archivedFilter} change={setArchivedFilter} /><NewWorkspaceAction workspace label="添加工作区" onClick={add} /></>}</span></div>
    {state.error && <p role="alert" className="cb-sidebar-error">{state.error} <button type="button" onClick={() => void modes.refresh()}>重试</button></p>}
    <div className="cb-workspace-list">
      {!management && <>{!state.ready && <p role="status" className="cb-empty">正在加载工作区…</p>}{localRows}</>}
      {renderServers?.({ archivedFilter, notices, showArchived: () => setArchivedFilter('only') })}
    </div>
    <SidebarNotice notices={notices} archivedVisible={archivedFilter !== 'default'} />
  </section>
}
