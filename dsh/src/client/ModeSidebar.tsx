// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { useEffect, useLayoutEffect, useRef, useMemo, useState, useSyncExternalStore, type DragEvent, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import type { Context } from '@deepseek-ai/cordis'
import type { ISessions } from '@deepseek-ai/dsh-api-session-controller/client'
import type { SessionId } from '@deepseek-ai/dsh-session/types'
import type { WorkspaceId } from '@deepseek-ai/dsh-api-workspace-controller/client'
import { FishLogo, IconCheckOutlineRegular, IconEditOutlineRegular, IconFolderCloseRegular, IconFolderOpenRegular, IconFollowsystemOutlineRegular, IconLinkOutlineRegular, IconNewChatOutlineRegular, IconPinFillRegular, IconPlusOutlineRegular, IconProjectAddOutlineRegular, IconRefreshOutlineRegular, IconTrashOutlineRegular, IconTriangleRightFillRegular, MenuItemButton, relativeTime, StateDot, Tooltip } from '@deepseek-ai/dsh-client-ui-primitives'
import type { ContentStore } from './content-store.ts'
import type { WorkspaceModes } from './workspace-modes.ts'
import type { RemoteClient, RemoteServer, RemoteSnapshot, RemoteTree } from './remote/types.ts'
import { CreateWorkspace } from './CreateWorkspace.tsx'
export const SERVERS_PANEL = 'cannbot-servers' as import('@deepseek-ai/dsh-client-ui-layout/client').MainPanelId
import { WorkbenchIcon } from './WorkbenchIcon.tsx'
import { Mark } from './Brand.tsx'
import { ArchivedViewMenu, ConfirmAction, MoreMenu, RenameDialog, SessionActions, WorkspaceActions, type ArchivedFilter, type SidebarOperation, type SidebarReadback, type SidebarSession, type SidebarWorkspace } from './SidebarActions.tsx'
import { createSidebarNotices, SidebarNotice, type SidebarNotices } from './SidebarNotice.tsx'
import { GENERAL_WORKSPACE } from '../workspace-mode-types.ts'
import './modes.css'

function useStore<T>(source: { getSnapshot(): T; subscribe(listener: () => void): () => void }) {
  const bound = useMemo(() => ({ getSnapshot: () => source.getSnapshot(), subscribe: (listener: () => void) => source.subscribe(listener) }), [source])
  return useSyncExternalStore(bound.subscribe, bound.getSnapshot)
}

/** CANNBot owns its brand; a neutral return entry restores the native workbench. */
export function ModeBrandMark({ modes, size = 24, onServers }: { modes: WorkspaceModes; size?: number; onServers?(): void }) {
  const state = useStore(modes)
  const marker = useRef<HTMLSpanElement>(null)
  const [host, setHost] = useState<HTMLDivElement | null>(null)
  const [serverHost, setServerHost] = useState<HTMLDivElement | null>(null)
  useLayoutEffect(() => {
    if (modes.embedded) return
    const anchor = marker.current?.closest('[data-slot="sidebar.brand.mark"]')
    const seat = anchor?.closest('[data-slot="sidebar"]')
    if (!seat) return
    const target = document.createElement('div')
    target.dataset.cannbotModeSwitchHost = ''
    const serverTarget = document.createElement('div'); serverTarget.dataset.cannbotServersHost = ''
    const place = () => {
      // The settings seat is separate and single-owner. The public panel-icon
      // anchor identifies the existing Plugins / Automations / More navigation.
      const navigation = seat.querySelector('[data-slot="sidebar.panellist"]')?.closest('nav')
      if (navigation && seat.contains(navigation)) {
        if (navigation.firstElementChild !== target) navigation.prepend(target)
        if (navigation.lastElementChild !== serverTarget) navigation.append(serverTarget)
        setServerHost(current => current === serverTarget ? current : serverTarget)
        setHost(current => current === target ? current : target)
      } else { target.remove(); serverTarget.remove(); setHost(null); setServerHost(null) }
    }
    const observer = new MutationObserver(place)
    observer.observe(seat, { childList: true, subtree: true })
    place()
    return () => { observer.disconnect(); target.remove(); serverTarget.remove() }
  }, [modes])
  const cann = state.mode === 'cannbot', brand = cann ? '返回原生工作台' : 'CANNBot'
  // React portal events still bubble through the original brand button's component tree.
  return <><span ref={marker}>{cann ? <Mark size={size} /> : <FishLogo size={size} />}</span>{host && createPortal(<button className="cb-mode-switch" type="button" aria-label={brand} title={cann ? brand : `切换到 ${brand}`} onClick={event => { event.stopPropagation(); modes.setMode(cann ? 'deepseek' : 'cannbot') }}><span className="cb-mode-switch-icon" aria-hidden="true">{cann ? <WorkbenchIcon name="back" size={16} /> : <Mark size={16} />}</span><span className="cb-mode-switch-name">{brand}</span></button>, host)}{cann && serverHost && onServers && createPortal(<button type="button" className="cb-mode-switch" aria-label="服务器" onClick={event => { event.stopPropagation(); onServers() }}><span className="cb-mode-switch-icon"><IconFollowsystemOutlineRegular size={16} /></span><span className="cb-mode-switch-name">服务器</span></button>, serverHost)}</>
}
type TreeSession = SidebarSession
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
function WorkspaceRows({ workspaces, sessions, activeSessionId, currentBlankId, activeWorkspaceId, closed, toggle, open, create, run, disabled, readback, archivedFilter, allWorkspaces = workspaces, copyFeedback, remoteLabel, serverId, platform }: {
  workspaces: TreeWorkspace[]; sessions: TreeSession[]; activeSessionId?: string; currentBlankId?: string; activeWorkspaceId?: string;
  closed: Set<string>; toggle(id: string): void; open(session: TreeSession): void; create(id: string): void; run: SidebarOperation; disabled?: boolean; readback?: SidebarReadback;
  remoteLabel?: string; serverId?: string; platform?: string; archivedFilter: ArchivedFilter; allWorkspaces?: readonly Pick<TreeWorkspace, 'workspaceId' | 'title'>[]; copyFeedback?(ok: boolean): void;
}) {
  const workspaceIds = new Set(workspaces.map(workspace => workspace.workspaceId))
  const group = (workspace: TreeWorkspace) => {
    const id = workspace.workspaceId
    const rows = sessions.filter(session => session.workspaceId === id).filter(session => (!session.blank || session.id === currentBlankId) && (archivedFilter === 'show' || !!session.archived === (archivedFilter === 'only')))
    if (archivedFilter === 'only' && !rows.length) return null
    const title = `${workspace.pluginId && workspace.pluginId !== GENERAL_WORKSPACE ? `${workspace.pluginId}: ` : ''}${workspace.title === 'default-workspace' ? '默认工作区' : workspace.title}`
    return <ProjectRow key={id} title={title} icon={remoteLabel ? <span className="cb-remote-folder" role="img" aria-label={`远程工作区 · ${remoteLabel}`} title={remoteLabel}>{closed.has(id) ? <IconFolderCloseRegular size={16} /> : <IconFolderOpenRegular size={16} />}<span className="cb-globe-badge"><WorkbenchIcon name="globe" size={10} /></span></span> : undefined} expanded={!closed.has(id)} toggle={() => toggle(id)} selected={!!workspace && activeWorkspaceId === id} accessory={workspace && <span className="cb-row-actions">
      <WorkspaceActions serverId={serverId} platform={platform} workspace={workspace} allWorkspaces={allWorkspaces} run={run} disabled={disabled} readback={readback} />
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
function toggleSet(previous: Set<string>, id: string) { const next = new Set(previous); next.has(id) ? next.delete(id) : next.add(id); return next }

interface ServerRowDrag {
  id: string; enabled: boolean; marker: 'before' | 'after' | undefined
  start(event: DragEvent<HTMLDivElement>): void; over(event: DragEvent<HTMLDivElement>): void
  drop(event: DragEvent<HTMLDivElement>): void; leave(event: DragEvent<HTMLDivElement>): void
  end(event: DragEvent<HTMLDivElement>): void; pointerDown(): void; consumeClick(): boolean
}
type ServerDrag = { id: string; ids: string[]; list: Element; over?: { id: string; half: 'before' | 'after' } }

/** Accept native desktop drops, with a one-shot drag-end fallback for a completed move. */
function useServerReorder(remote: RemoteClient, enabled: boolean) {
  const current = useRef<ServerDrag | null>(null), committing = useRef(false), alive = useRef(true), suppressUntil = useRef(0)
  const [drag, setDrag] = useState<ServerDrag | null>(null), [pending, setPending] = useState(false), [error, setError] = useState('')
  const clear = () => { if (current.current) suppressUntil.current = Date.now() + 500; current.current = null; setDrag(null) }
  useEffect(() => { alive.current = true; return () => { alive.current = false; current.current = null } }, [])
  const blocked = () => {
    const state = remote.getSnapshot()
    return !enabled || committing.current || state.busy || state.orderingServers || !!state.removingServerIds?.length || !!state.disconnectingServerIds?.length
  }
  const setOver = (over: ServerDrag['over']) => {
    const source = current.current
    if (!source || (source.over?.id === over?.id && source.over?.half === over?.half)) return
    current.current = { ...source, over }; setDrag(current.current)
  }
  const target = (node: EventTarget | null, clientY: number): ServerDrag['over'] => {
    const source = current.current
    const group = node instanceof Element ? node.closest<HTMLElement>('[data-cannbot-server-id]') : null
    const id = group?.dataset.cannbotServerId
    if (!source || blocked() || !group || group.parentElement !== source.list || !id || id === source.id || !source.ids.includes(id) || !group.querySelector<HTMLElement>(':scope > .cb-project-row')?.draggable) return
    const bounds = group.getBoundingClientRect()
    return { id, half: clientY < bounds.top + bounds.height / 2 ? 'before' : 'after' }
  }
  const commit = () => {
    const source = current.current
    // Both the React drop and desktop drag-end path consume the same lease.
    clear()
    if (!source?.over || blocked()) return
    const ids = remote.getSnapshot().servers.map(server => server.id)
    if (ids.length !== source.ids.length || ids.some((value, index) => source.ids[index] !== value)) { setError('服务器列表已变化，请重新拖动排序。'); return }
    const next = ids.filter(value => value !== source.id), index = next.indexOf(source.over.id)
    if (index < 0) return
    next.splice(index + (source.over.half === 'after' ? 1 : 0), 0, source.id)
    if (next.every((value, index) => value === ids[index])) return
    committing.current = true; setPending(true)
    void remote.reorderServers(next).catch(() => { if (alive.current) setError('服务器排序未保存，请重新拖动重试。') }).finally(() => { committing.current = false; if (alive.current) setPending(false) })
  }
  const dragging = drag !== null
  useEffect(() => {
    if (!enabled) clear()
    if (!enabled || !dragging) return
    const accept = (event: globalThis.DragEvent) => {
      if (!current.current) return
      event.preventDefault()
      const over = target(event.target, event.clientY)
      setOver(over)
      if (event.dataTransfer) event.dataTransfer.dropEffect = over ? 'move' : 'none'
    }
    const cancel = (event: KeyboardEvent) => { if (event.key === 'Escape' && current.current) { event.preventDefault(); clear() } }
    const blur = () => clear()
    // Capture also accepts native drops that never reach a React row handler.
    // These listeners exist only for a drag begun on our own server header.
    document.addEventListener('dragover', accept, true)
    document.addEventListener('drop', accept, true)
    document.addEventListener('keydown', cancel, true)
    window.addEventListener('blur', blur)
    return () => {
      document.removeEventListener('dragover', accept, true)
      document.removeEventListener('drop', accept, true)
      document.removeEventListener('keydown', cancel, true)
      window.removeEventListener('blur', blur)
    }
  }, [enabled, dragging, remote])
  const row = (id: string, available: boolean): ServerRowDrag => ({
    id, enabled: available && !blocked(), marker: drag?.over?.id === id ? drag.over.half : undefined,
    pointerDown() { if (!current.current) suppressUntil.current = 0 },
    consumeClick() { if (Date.now() >= suppressUntil.current) return false; suppressUntil.current = 0; return true },
    start(event) {
      event.stopPropagation()
      if (!available || blocked()) { event.preventDefault(); return }
      const ids = remote.getSnapshot().servers.map(server => server.id)
      const list = event.currentTarget.closest('.cb-workspace-list')
      if (!ids.includes(id) || !list) { event.preventDefault(); return }
      event.dataTransfer.effectAllowed = 'move'; event.dataTransfer.setData('text/plain', id)
      current.current = { id, ids, list }; setDrag(current.current); setError(''); suppressUntil.current = Infinity
    },
    over(event) {
      if (!current.current || !available || blocked() || !event.currentTarget.contains(event.target as Node)) return
      event.preventDefault(); event.stopPropagation()
      const over = target(event.target, event.clientY)
      event.dataTransfer.dropEffect = over ? 'move' : 'none'; setOver(over)
    },
    leave(event) {
      if (!current.current || event.currentTarget.contains(event.relatedTarget as Node | null)) return
      // Electron can omit relatedTarget when traversing children of one group.
      // Hit-test the pointer before treating that event as leaving the group.
      if (!event.relatedTarget && event.currentTarget.contains(document.elementFromPoint?.(event.clientX, event.clientY) || null)) return
      if (current.current.over?.id === id) setOver(undefined)
    },
    drop(event) {
      if (!current.current) return
      event.preventDefault(); event.stopPropagation()
      if (!available || blocked() || !event.currentTarget.contains(event.target as Node)) { clear(); return }
      setOver(target(event.target, event.clientY)); commit()
    },
    end(event) { if (event.dataTransfer.dropEffect === 'move') commit(); else clear() },
  })
  return { row, pending, error }
}

function ServerProject({ server, expanded, toggle, remote, modes, snapshot, cache, active, archivedFilter, notices, showArchived, sorting, management = false }: { management?: boolean; server: RemoteServer; expanded: boolean; toggle(): void; remote: RemoteClient; modes: WorkspaceModes; snapshot: RemoteSnapshot; cache: Map<string, RemoteTree>; active: boolean; archivedFilter: ArchivedFilter; notices: SidebarNotices; showArchived(): void; sorting: ReturnType<typeof useServerReorder> }) {
  const [tree, setTree] = useState<RemoteTree | null>(() => cache.get(server.id) || null)
  const [loading, setLoading] = useState(false), [opening, setOpening] = useState(false), [error, setError] = useState(''), [retry, setRetry] = useState(0)
  const [connectionError, setConnectionError] = useState('')
  const [renaming, setRenaming] = useState(false), [removing, setRemoving] = useState(false), [operating, setOperating] = useState(false)
  const [readRevision, setReadRevision] = useState(0)
  const [closed, setClosed] = useState<Set<string>>(new Set())
  const alive = useRef(true), revision = useRef(0), mutation = useRef(false)
  const readSequence = useRef(0), reading = useRef(false), startupDeadline = useRef(0)
  const connectingThisServer = snapshot.busy && snapshot.selectedServerId === server.id
  const acceptTree = (next: RemoteTree) => { cache.set(server.id, next); setTree(next); setError(''); setReadRevision(value => value + 1) }
  useEffect(() => { alive.current = true; return () => { alive.current = false } }, [])
  useEffect(() => {
    if (server.connected) return
    ++revision.current; ++readSequence.current; reading.current = false; startupDeadline.current = 0
    cache.delete(server.id); setTree(null); setLoading(false); setError(''); setConnectionError('')
  }, [server.connected, server.id, cache])
  useEffect(() => {
    // Expanding an SSH alias is read-only. Only the explicit connection/open action
    // below can deploy or connect, even when several server rows are expanded.
    if (!expanded || !server.connected) return
    if (connectingThisServer) { setLoading(true); return }
    // The tunnel may become visible before the new web profile accepts tree reads.
    // Keep a bounded startup loading state and retry reads only, never bootstrap.
    if (!cache.has(server.id) && !startupDeadline.current) startupDeadline.current = Date.now() + 30000
    const warming = () => !cache.has(server.id) && Date.now() < startupDeadline.current
    let active = true, timer: ReturnType<typeof setTimeout> | undefined
    const refresh = async () => {
      if (reading.current || mutation.current) { timer = setTimeout(() => { void refresh() }, 1000); return }
      const requestRevision = revision.current
      const request = ++readSequence.current
      reading.current = true; setLoading(true)
      const current = () => active && request === readSequence.current && requestRevision === revision.current && !mutation.current
      try { const next = await remote.getTree(server.id); if (current()) acceptTree(next) }
      catch { if (current()) setError(warming() ? '' : '无法读取服务器工作区，请检查连接后重试。') }
      finally {
        if (request === readSequence.current) reading.current = false
        if (active) {
          if (current()) setLoading(warming())
          timer = setTimeout(() => { void refresh() }, warming() ? 2000 : 5000)
        }
      }
    }
    void refresh()
    return () => { active = false; clearTimeout(timer); ++readSequence.current; reading.current = false }
  }, [remote, server.id, server.connected, expanded, retry, cache, connectingThisServer])
  const refreshList = async () => {
    if (mutation.current) throw new Error('操作尚未完成，请稍后刷新列表。')
    const requestRevision = ++revision.current
    const request = ++readSequence.current
    reading.current = true; setLoading(true)
    try {
      const next = await remote.getTree(server.id)
      if (!alive.current || request !== readSequence.current || requestRevision !== revision.current || mutation.current) throw new Error('列表读取已被更新的操作替代，请重试刷新。')
      acceptTree(next)
    } catch (reason) {
      if (alive.current && request === readSequence.current && requestRevision === revision.current) setError('无法读取服务器工作区，请检查连接后重试。')
      throw reason
    } finally { if (request === readSequence.current) { reading.current = false; if (alive.current) setLoading(false) } }
  }
  const open = (workspaceId?: string, sessionId?: string, createWorkspace?: boolean) => {
    if (opening || mutation.current || remote.getSnapshot().busy) return
    setOpening(true); setConnectionError(''); modes.selectServer(server.id)
    void remote.open({ serverId: server.id, workspaceId, sessionId, ...(createWorkspace ? { createWorkspace: true } : {}) }).catch(() => { if (alive.current) setConnectionError('无法打开远端工作台，请检查连接后重试。') }).finally(() => { if (alive.current) setOpening(false) })
  }
  const connect = () => {
    if (snapshot.busy || opening) return
    setOpening(true); setConnectionError('')
    void remote.connect(server.id).catch(reason => { if (alive.current) setConnectionError(reason instanceof Error ? reason.message : '连接失败，请重试。') }).finally(() => { if (alive.current) setOpening(false) })
  }
  const disconnect = () => {
    if (opening || mutation.current || remote.getSnapshot().busy || remote.getSnapshot().disconnectingServerIds?.includes(server.id)) return
    mutation.current = true; ++revision.current; setOperating(true); setConnectionError('')
    void remote.disconnect(server.id).catch(() => { if (alive.current) setConnectionError('无法断开服务器连接，请重试。') }).finally(() => { mutation.current = false; if (alive.current) setOperating(false) })
  }
  const disconnecting = snapshot.disconnectingServerIds?.includes(server.id) === true
  const connecting = opening || connectingThisServer
  const target = active && snapshot.target?.serverId === server.id ? snapshot.target : null
  const label = server.label || server.alias
  const status = disconnecting ? '断开中' : connecting ? '连接中' : server.connected ? '已连接' : '未连接'
  const action = disconnecting ? `正在断开 ${label}` : connecting ? `正在连接 ${label}` : server.connected ? `断开 ${label}` : `连接 ${label}`
  const run: SidebarOperation = async operation => {
    if (mutation.current) throw new Error('上一项操作尚未完成，请稍后重试。')
    mutation.current = true; revision.current++; setOperating(true)
    const operationRevision = revision.current
    const navigation = remote.getSnapshot().target, mode = modes.getSnapshot()
    try {
      const result = await remote.operate(server.id, operation)
      // A disconnected generation may finish a committed write later. Do not
      // restore its cached tree, show a stale notice, or reopen a fork remotely.
      if (!alive.current || operationRevision !== revision.current || !remote.getSnapshot().servers.some(item => item.id === server.id && item.connected)) return
      revision.current++
      if (alive.current) acceptTree(result.tree)
      if (operation.action === 'archive-session' && modes.getSnapshot().mode === 'cannbot') notices.archived({ sessionId: operation.sessionId, stopped: operation.stopActivity, undo: () => run({ action: 'unarchive-session', sessionId: operation.sessionId }), showArchived })
      if (result.sessionId && operation.action === 'fork-session' && remote.getSnapshot().target === navigation && modes.getSnapshot().mode === mode.mode && modes.getSnapshot().serverId === mode.serverId) {
        const child = result.tree.sessions.find(session => session.id === result.sessionId)
        modes.selectServer(server.id)
        await remote.open({ serverId: server.id, workspaceId: child?.workspaceId, sessionId: result.sessionId })
      }
    } finally { mutation.current = false; revision.current++; if (alive.current) setOperating(false) }
  }
  const disabled = snapshot.busy || opening || operating || disconnecting || snapshot.removingServerIds?.includes(server.id) || snapshot.orderingServers || sorting.pending
  const remove = async () => {
    const state = remote.getSnapshot()
    if (opening || mutation.current || state.busy || state.orderingServers || state.removingServerIds?.includes(server.id) || state.disconnectingServerIds?.includes(server.id)) throw new Error('服务器操作尚未完成，请稍后重试。')
    mutation.current = true; ++revision.current; ++readSequence.current; reading.current = false; setOperating(true)
    try { await remote.removeServer(server.id); cache.delete(server.id) }
    finally { mutation.current = false; if (alive.current) setOperating(false) }
  }
  if (!management) return server.connected ? <>{connectionError && <p role="alert" className="cb-sidebar-error">{connectionError}</p>}{error && <p role="alert" className="cb-sidebar-error">{label}：{error} <button type="button" onClick={() => { startupDeadline.current = 0; setError(''); setRetry(value => value + 1) }}>重试</button></p>}{loading && !tree && <p role="status" className="cb-empty">正在加载 {label} 的工作区…</p>}<WorkspaceRows serverId={server.id} remoteLabel={label} workspaces={tree?.workspaces || []} sessions={tree?.sessions || []} activeSessionId={target?.sessionId} currentBlankId={snapshot.target?.serverId === server.id ? snapshot.target.sessionId : undefined} activeWorkspaceId={target?.workspaceId} closed={closed} toggle={id => setClosed(previous => toggleSet(previous, id))} open={session => { if (session.archived) notices.archivedNotOpenable(); else open(session.workspaceId, session.id) }} create={id => open(id)} run={run} disabled={disabled} archivedFilter={archivedFilter} copyFeedback={ok => { if (modes.getSnapshot().mode === 'cannbot') notices.copied(ok) }} readback={{ revision: readRevision, refresh: refreshList }} /></> : null
  return <><ProjectRow title={label} expanded={false} expandable={false} toggle={toggle} selected={!!target} drag={sorting.row(server.id, !disabled && !renaming && !removing)} icon={<IconFollowsystemOutlineRegular size={16} />} accessory={<div className="cb-server-actions"><span className="cb-server-status" role="status">{status}</span><Tooltip label={`${status} · ${action}`} side="bottom" delayMs={500} portal>
    <button className="cb-connection-action" type="button" aria-label={action} disabled={disabled} onClick={() => server.connected ? disconnect() : connect()}>
      <span aria-hidden="true" className={connecting || disconnecting ? 'cb-connection-pending' : undefined}>{connecting || disconnecting ? <IconRefreshOutlineRegular size={16} /> : server.connected ? <IconCheckOutlineRegular size={16} /> : <IconLinkOutlineRegular size={16} />}</span>
    </button>
  </Tooltip><span className="cb-row-actions"><MoreMenu label={`${label}的服务器操作`} disabled={disabled}>{close => <><MenuItemButton icon={<IconEditOutlineRegular size={16} />} onSelect={() => { close(); setRenaming(true) }}>编辑备注</MenuItemButton><MenuItemButton danger icon={<IconTrashOutlineRegular size={16} />} onSelect={() => { close(); setRemoving(true) }}>删除服务器</MenuItemButton></>}</MoreMenu><NewWorkspaceAction workspace label={`在 ${label} 上添加工作区`} onClick={() => modes.setCreating(true, server.id)} disabled={!server.connected || disabled} /></span></div>}>
  </ProjectRow>{connectionError && <p role="alert" className="cb-sidebar-error">{connectionError} <button type="button" onClick={() => server.connected ? disconnect() : connect()}>重试</button></p>}{renaming && <RenameDialog title="编辑服务器备注" field="服务器备注" description={`SSH 服务器：${server.alias}。清空备注后显示 SSH 名称，不会修改连接配置。`} initial={server.label} allowEmpty actionLabel="保存" maxLength={120} save={value => remote.renameServer(server.id, value)} close={() => setRenaming(false)} />}
    {removing && <ConfirmAction title="删除服务器" description={`将把“${label}”从本机服务器列表中移除，并断开本机 SSH 隧道。远端文件、会话和运行中的任务会保留，SSH 配置不会修改。`} action="删除服务器" pending="正在删除服务器…" confirm={remove} close={() => setRemoving(false)} />}</>
}

export function ModeWorkspaceTree({ ctx, modes, remote, wide = true, management = false }: { management?: boolean; ctx: Context; modes: WorkspaceModes; content: ContentStore; remote: RemoteClient; wide?: boolean }) {
  const state = useStore(modes), remoteState = useStore(remote)
  const sorting = useServerReorder(remote, state.mode === 'cannbot' && management && wide && !modes.embedded)
  const panel = useStore(ctx.layout.panelInfo)
  const workspaceState = useStore(ctx.workspaces.list)
  const sessionState = useStore((ctx.sessions as unknown as ISessions).list)
  const cache = useRef(new Map<string, RemoteTree>())
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
  const local = (action: () => void) => { if (state.serverId) remote.returnLocal(); action() }
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
    <div className="cb-workspaces-heading"><h2>{management ? '服务器' : '工作区'}</h2><span className="cb-heading-actions">{management ? <Tooltip label="新增服务器" side="bottom" align="end" delayMs={500} portal><button type="button" className="cb-add-server" aria-label="新增服务器" onClick={() => remote.showConnections()}><IconPlusOutlineRegular size={16} /></button></Tooltip> : <><ArchivedViewMenu value={archivedFilter} change={setArchivedFilter} /><NewWorkspaceAction workspace label="添加工作区" onClick={add} /></>}</span></div>
    {management && remoteState.error && <p role="alert" className="cb-sidebar-error">{remoteState.error}</p>}
    {management && remoteState.busy && <p role="status" className="cb-empty">{remoteState.progress.at(-1) || '正在连接服务器…'}</p>}
    {state.error && <p role="alert" className="cb-sidebar-error">{state.error} <button type="button" onClick={() => void modes.refresh()}>重试</button></p>}
    {sorting.pending && <p role="status" className="cb-empty">正在保存服务器顺序…</p>}{sorting.error && <p role="alert" className="cb-sidebar-error">{sorting.error}</p>}
    <div className="cb-workspace-list">
      {!management && <>{!state.ready && <p role="status" className="cb-empty">正在加载工作区…</p>}{localRows}</>}
      {remoteState.servers.map(server => <ServerProject management={management} key={server.id} server={server} expanded={!management} toggle={() => {}} remote={remote} modes={modes} snapshot={remoteState} cache={cache.current} active={state.serverId === server.id} archivedFilter={archivedFilter} notices={notices} showArchived={() => setArchivedFilter('only')} sorting={sorting} />)}
      {management && !remoteState.servers.length && <p className="cb-empty">尚未添加服务器。</p>}
    </div>
    <SidebarNotice notices={notices} archivedVisible={archivedFilter !== 'default'} />
  </section>
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

/** Keep initialization available in embedded remote pages, whose sidebar is hidden. */
export function ModeWorkspaceCreation({ modes, content, remote }: { ctx: Context; modes: WorkspaceModes; content: ContentStore; remote: RemoteClient }) {
  const state = useStore(modes), catalog = useStore(content)
  return state.creating ? <CreateWorkspace modes={modes} remote={remote} workflows={catalog.workflows} close={() => modes.setCreating(false)} /> : null
}
