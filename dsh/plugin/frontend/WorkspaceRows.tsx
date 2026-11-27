// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { useEffect, useRef, useMemo, useState, useSyncExternalStore, type DragEvent, type ReactNode } from 'react'
import { IconFolderCloseRegular, IconFolderOpenRegular, IconNewChatOutlineRegular, IconPinFillRegular, IconProjectAddOutlineRegular, IconTriangleRightFillRegular, relativeTime, StateDot, Tooltip } from '@deepseek-ai/dsh-client-ui-primitives'
import { WorkbenchIcon } from './WorkbenchIcon.tsx'
import { SessionActions, WorkspaceActions, type ArchivedFilter, type SidebarOperation, type SidebarReadback, type SidebarSession, type SidebarWorkspace } from './SidebarActions.tsx'
import { GENERAL_WORKSPACE } from '../contracts/workspace-mode-types.ts'

export function useStore<T>(source: { getSnapshot(): T; subscribe(listener: () => void): () => void }) {
  const bound = useMemo(() => ({ getSnapshot: () => source.getSnapshot(), subscribe: (listener: () => void) => source.subscribe(listener) }), [source])
  return useSyncExternalStore(bound.subscribe, bound.getSnapshot)
}

export type TreeSession = SidebarSession
type TreeWorkspace = SidebarWorkspace
const timestamp = (value: number | string | undefined) => typeof value === 'number' ? value : value ? Date.parse(value) || 0 : 0

// The native workspace row is private. Match its row contract with public icons
// and menus; DisclosureRow is a flow row whose open state always shows an up chevron.
export function ProjectRow({ title, expanded, toggle, accessory, selected, icon, expandable = true, nested = false, drag, children }: { title: string; expanded: boolean; toggle(): void; accessory?: ReactNode; selected?: boolean; icon?: ReactNode; expandable?: boolean; nested?: boolean; drag?: ServerRowDrag; children?: ReactNode }) {
  const open = expandable && expanded
  const fromAction = useRef(false)
  return <div className={`cb-project${selected ? ' cb-project-selected' : ''}${nested ? ' cb-project-nested' : ''}${drag?.marker ? ` cb-server-drop-${drag.marker}` : ''}`} data-cannbot-server-id={drag?.id} onDragOver={drag?.over} onDrop={drag?.drop} onDragLeave={drag?.leave}>
    <div className="cb-project-row" data-disclosure-header data-disclosure-row role={expandable ? 'button' : undefined} tabIndex={expandable ? 0 : undefined} aria-label={title} aria-expanded={expandable ? open : undefined}
      draggable={drag?.enabled}
      onPointerDownCapture={event => { fromAction.current = !!(event.target as Element).closest('.cb-project-accessory, button, a, input, [role="menu"]'); drag?.pointerDown() }}
      onDragStart={drag ? event => {
        if (fromAction.current || !!(event.target as Element).closest('.cb-project-accessory, button, a, input, [role="menu"]')) { event.preventDefault(); event.stopPropagation(); return }
        drag.start(event)
      } : undefined}
      onDragEnd={drag?.end}
      onClickCapture={event => { if (drag?.consumeClick()) { event.preventDefault(); event.stopPropagation() } }}
      onClick={() => { if (expandable) toggle() }} onKeyDown={event => { if (event.target === event.currentTarget && expandable && (event.key === 'Enter' || event.key === ' ')) { event.preventDefault(); toggle() } }}>
      <span className="cb-leading cb-folder">{icon || (open ? <IconFolderOpenRegular size={16} /> : <IconFolderCloseRegular size={16} />)}</span>
      {expandable && <span className="cb-leading cb-chevron"><IconTriangleRightFillRegular size={16} className={open ? 'cb-chevron-open' : undefined} /></span>}
      <span className="cb-project-text"><span className="cb-project-title">{title}</span></span>
      <span className="cb-project-accessory" onClick={event => event.stopPropagation()}>{accessory}</span>
    </div>
    {open && <div className="cb-project-children">{children}</div>}
  </div>
}
export function NewWorkspaceAction({ label, onClick, disabled, workspace = false }: { label: string; onClick(): void; disabled?: boolean; workspace?: boolean }) {
  return <Tooltip label={label} side="bottom" align="end" delayMs={500} portal><button className="cb-project-action" type="button" aria-label={label} onClick={onClick} disabled={disabled}>{workspace ? <IconProjectAddOutlineRegular size={16} /> : <IconNewChatOutlineRegular size={16} />}</button></Tooltip>
}
export function WorkspaceRows({ workspaces, sessions, activeSessionId, currentBlankId, activeWorkspaceId, closed, toggle, open, create, run, disabled, readback, archivedFilter, allWorkspaces = workspaces, copyFeedback, remoteLabel, endpoint, platform }: {
  workspaces: TreeWorkspace[]; sessions: TreeSession[]; activeSessionId?: string; currentBlankId?: string; activeWorkspaceId?: string;
  closed: Set<string>; toggle(id: string): void; open(session: TreeSession): void; create(id: string): void; run: SidebarOperation; disabled?: boolean; readback?: SidebarReadback;
  remoteLabel?: string; endpoint?: string; platform?: string; archivedFilter: ArchivedFilter; allWorkspaces?: readonly Pick<TreeWorkspace, 'workspaceId' | 'title'>[]; copyFeedback?(ok: boolean): void;
}) {
  const workspaceIds = new Set(workspaces.map(workspace => workspace.workspaceId))
  const group = (workspace: TreeWorkspace) => {
    const id = workspace.workspaceId
    const rows = sessions.filter(session => session.workspaceId === id).filter(session => (!session.blank || session.id === currentBlankId) && (archivedFilter === 'show' || !!session.archived === (archivedFilter === 'only')))
    if (archivedFilter === 'only' && !rows.length) return null
    const title = `${workspace.pluginId && workspace.pluginId !== GENERAL_WORKSPACE ? `${workspace.pluginId}: ` : ''}${workspace.title === 'default-workspace' ? '默认工作区' : workspace.title}`
    return <ProjectRow key={id} title={title} icon={remoteLabel ? <span className="cb-remote-folder" role="img" aria-label={`远程工作区 · ${remoteLabel}`} title={remoteLabel}>{closed.has(id) ? <IconFolderCloseRegular size={16} /> : <IconFolderOpenRegular size={16} />}<span className="cb-globe-badge"><WorkbenchIcon name="globe" size={10} /></span></span> : undefined} expanded={!closed.has(id)} toggle={() => toggle(id)} selected={!!workspace && activeWorkspaceId === id} accessory={workspace && <span className="cb-row-actions">
      <WorkspaceActions endpoint={endpoint} platform={platform} workspace={workspace} allWorkspaces={allWorkspaces} run={run} disabled={disabled} readback={readback} />
      <NewWorkspaceAction label={`在 ${workspace.title} 中新建会话`} onClick={() => create(id)} disabled={disabled} />
    </span>}>
      <SessionRows sessions={rows} activeSessionId={activeSessionId} open={open} run={run} disabled={disabled} readback={readback} copyFeedback={copyFeedback} />
    </ProjectRow>
  }
  return <>{workspaces.map(workspace => group(workspace))}{workspaces.length > 0 && archivedFilter === 'only' && !sessions.some(session => workspaceIds.has(session.workspaceId) && session.archived) && <p className="cb-empty">暂无已归档会话</p>}</>
}
function SessionRows({ sessions, activeSessionId, open, run, disabled, readback, copyFeedback }: { sessions: TreeSession[]; activeSessionId?: string; open(session: TreeSession): void; run: SidebarOperation; disabled?: boolean; readback?: SidebarReadback; copyFeedback?(ok: boolean): void }) {
  return <>{[...sessions].sort((a, b) => Number(!!b.blank) - Number(!!a.blank) || Number(!!b.pinned) - Number(!!a.pinned) || (a.pinned && b.pinned ? (a.pinOrder ?? 0) - (b.pinOrder ?? 0) : 0) || timestamp(b.updatedAt) - timestamp(a.updatedAt)).map(session => <SessionRow key={session.id} session={session} active={activeSessionId === session.id} open={() => open(session)} run={run} disabled={disabled} readback={readback} copyFeedback={copyFeedback} />)}</>
}
export function toggleSet(previous: Set<string>, id: string) { const next = new Set(previous); next.has(id) ? next.delete(id) : next.add(id); return next }

export interface ServerRowDrag {
  id: string; enabled: boolean; marker: 'before' | 'after' | undefined
  start(event: DragEvent<HTMLDivElement>): void; over(event: DragEvent<HTMLDivElement>): void
  drop(event: DragEvent<HTMLDivElement>): void; leave(event: DragEvent<HTMLDivElement>): void
  end(event: DragEvent<HTMLDivElement>): void; pointerDown(): void; consumeClick(): boolean
}
export function SessionRow({ session, active, open, run, disabled, readback, copyFeedback }: { session: TreeSession; active: boolean; open(): void; run: SidebarOperation; disabled?: boolean; readback?: SidebarReadback; copyFeedback?(ok: boolean): void }) {
  const [renameRequest, setRenameRequest] = useState(0), [now, setNow] = useState(Date.now)
  useEffect(() => { const timer = setInterval(() => setNow(Date.now()), 30000); return () => clearInterval(timer) }, [])
  const at = timestamp(session.updatedAt), time = relativeTime(at, now)
  const units = { minutes: '分钟', hours: '小时', days: '天', months: '个月', years: '年' }
  const label = session.blank ? '新会话' : session.title
  return <div className={`cb-session-row${session.archived ? ' cb-session-archived' : ''}`} data-session-id={session.id}>
    <button type="button" className="cb-session" aria-current={active ? 'page' : undefined} onClick={open} title={label} disabled={disabled} aria-description={session.archived ? '已归档对话暂时无法查看，请取消归档后查看' : undefined}>
      <span className="cb-leading">{!session.blank && !session.archived && session.running && <span aria-label="进行中"><StateDot state="ongoing" /></span>}</span>
      <span className="cb-session-title" onDoubleClick={session.blank ? undefined : event => { event.stopPropagation(); setRenameRequest(value => value + 1) }}>{label}{session.frozen && <small> · 已冻结</small>}</span>
    </button>
    {!session.blank && at > 0 && <span className="cb-session-time">{time.unit === 'now' ? '刚刚' : `${time.n}${units[time.unit]}`}</span>}
    {session.pinned && !session.archived && <span className="cb-session-pin" role="img" aria-label="已置顶" title="已置顶"><IconPinFillRegular size={14} /></span>}
    <SessionActions session={session} run={run} disabled={disabled} readback={readback} renameRequest={renameRequest} copyFeedback={copyFeedback} />
  </div>
}
