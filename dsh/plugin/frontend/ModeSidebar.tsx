// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { useEffect, useLayoutEffect, useRef, useState, type DragEvent } from 'react'
import { createPortal } from 'react-dom'
import type { Context } from '@deepseek-ai/cordis'
import { FishLogo, IconCheckOutlineRegular, IconEditOutlineRegular, IconFollowsystemOutlineRegular, IconLinkOutlineRegular, IconPlusOutlineRegular, IconRefreshOutlineRegular, IconTrashOutlineRegular, MenuItemButton, Tooltip } from '@deepseek-ai/dsh-client-ui-primitives'
import type { ContentStore } from './content-store.ts'
import type { WorkspaceModes } from './workspace-modes.ts'
import type { RemoteClient, RemoteServer, RemoteSnapshot, RemoteTree } from './remote/types.ts'
import { CreateWorkspace } from './CreateWorkspace.tsx'
import { WorkbenchIcon } from './WorkbenchIcon.tsx'
import { Mark } from './Brand.tsx'
import { ConfirmAction, MoreMenu, RenameDialog, type ArchivedFilter, type SidebarOperation } from './SidebarActions.tsx'
import { type SidebarNotices } from './SidebarNotice.tsx'
import { remoteWorkspaceEndpoint } from './remote/endpoint.ts'
import { WorkspaceTree, type ServerListContext, type WorkspaceTreeProps } from './WorkspaceTree.tsx'
import { NewWorkspaceAction, ProjectRow, WorkspaceRows, toggleSet, useStore, type ServerRowDrag } from './WorkspaceRows.tsx'
export { NewWorkspaceAction, ProjectRow, SessionRow } from './WorkspaceRows.tsx'
export const SERVERS_PANEL = 'cannbot-servers' as import('@deepseek-ai/dsh-client-ui-layout/client').MainPanelId

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
  if (!management) return server.connected ? <>{connectionError && <p role="alert" className="cb-sidebar-error">{connectionError}</p>}{error && <p role="alert" className="cb-sidebar-error">{label}：{error} <button type="button" onClick={() => { startupDeadline.current = 0; setError(''); setRetry(value => value + 1) }}>重试</button></p>}{loading && !tree && <p role="status" className="cb-empty">正在加载 {label} 的工作区…</p>}<WorkspaceRows endpoint={remoteWorkspaceEndpoint(server.id)} remoteLabel={label} workspaces={tree?.workspaces || []} sessions={tree?.sessions || []} activeSessionId={target?.sessionId} currentBlankId={snapshot.target?.serverId === server.id ? snapshot.target.sessionId : undefined} activeWorkspaceId={target?.workspaceId} closed={closed} toggle={id => setClosed(previous => toggleSet(previous, id))} open={session => { if (session.archived) notices.archivedNotOpenable(); else open(session.workspaceId, session.id) }} create={id => open(id)} run={run} disabled={disabled} archivedFilter={archivedFilter} copyFeedback={ok => { if (modes.getSnapshot().mode === 'cannbot') notices.copied(ok) }} readback={{ revision: readRevision, refresh: refreshList }} /></> : null
  return <><ProjectRow title={label} expanded={false} expandable={false} toggle={toggle} selected={!!target} drag={sorting.row(server.id, !disabled && !renaming && !removing)} icon={<IconFollowsystemOutlineRegular size={16} />} accessory={<div className="cb-server-actions"><span className="cb-server-status" role="status">{status}</span><Tooltip label={`${status} · ${action}`} side="bottom" delayMs={500} portal>
    <button className="cb-connection-action" type="button" aria-label={action} disabled={disabled} onClick={() => server.connected ? disconnect() : connect()}>
      <span aria-hidden="true" className={connecting || disconnecting ? 'cb-connection-pending' : undefined}>{connecting || disconnecting ? <IconRefreshOutlineRegular size={16} /> : server.connected ? <IconCheckOutlineRegular size={16} /> : <IconLinkOutlineRegular size={16} />}</span>
    </button>
  </Tooltip><span className="cb-row-actions"><MoreMenu label={`${label}的服务器操作`} disabled={disabled}>{close => <><MenuItemButton icon={<IconEditOutlineRegular size={16} />} onSelect={() => { close(); setRenaming(true) }}>编辑备注</MenuItemButton><MenuItemButton danger icon={<IconTrashOutlineRegular size={16} />} onSelect={() => { close(); setRemoving(true) }}>删除服务器</MenuItemButton></>}</MoreMenu><NewWorkspaceAction workspace label={`在 ${label} 上添加工作区`} onClick={() => modes.setCreating(true, server.id)} disabled={!server.connected || disabled} /></span></div>}>
  </ProjectRow>{connectionError && <p role="alert" className="cb-sidebar-error">{connectionError} <button type="button" onClick={() => server.connected ? disconnect() : connect()}>重试</button></p>}{renaming && <RenameDialog title="编辑服务器备注" field="服务器备注" description={`SSH 服务器：${server.alias}。清空备注后显示 SSH 名称，不会修改连接配置。`} initial={server.label} allowEmpty actionLabel="保存" maxLength={120} save={value => remote.renameServer(server.id, value)} close={() => setRenaming(false)} />}
    {removing && <ConfirmAction title="删除服务器" description={`将把“${label}”从本机服务器列表中移除，并断开本机 SSH 隧道。远端文件、会话和运行中的任务会保留，SSH 配置不会修改。`} action="删除服务器" pending="正在删除服务器…" confirm={remove} close={() => setRemoving(false)} />}</>
}


export function ModeWorkspaceTree({ remote, management = false, ...props }: WorkspaceTreeProps & { remote: RemoteClient; content: ContentStore; management?: boolean }) {
  const add = management && <Tooltip label="新增服务器" side="bottom" align="end" delayMs={500} portal><button type="button" className="cb-add-server" aria-label="新增服务器" onClick={() => remote.showConnections()}><IconPlusOutlineRegular size={16} /></button></Tooltip>
  return <WorkspaceTree {...props} managementHeader={add} onReturnLocal={() => remote.returnLocal()} renderServers={view => <ServerList {...view} modes={props.modes} remote={remote} management={management} />} />
}

function ServerList({ remote, modes, management, archivedFilter, notices, showArchived }: ServerListContext & { modes: WorkspaceModes; remote: RemoteClient; management: boolean }) {
  const state = useStore(modes), remoteState = useStore(remote)
  const cache = useRef(new Map<string, RemoteTree>())
  const sorting = useServerReorder(remote, management)
  return <>
    {management && remoteState.error && <p role="alert" className="cb-sidebar-error">{remoteState.error}</p>}
    {management && remoteState.busy && <p role="status" className="cb-empty">{remoteState.progress.at(-1) || '正在连接服务器…'}</p>}
    {sorting.pending && <p role="status" className="cb-empty">正在保存服务器顺序…</p>}{sorting.error && <p role="alert" className="cb-sidebar-error">{sorting.error}</p>}
    {remoteState.servers.map(server => <ServerProject management={management} key={server.id} server={server} expanded={!management} toggle={() => {}} remote={remote} modes={modes} snapshot={remoteState} cache={cache.current} active={state.serverId === server.id} archivedFilter={archivedFilter} notices={notices} showArchived={showArchived} sorting={sorting} />)}
    {management && !remoteState.servers.length && <p className="cb-empty">尚未添加服务器。</p>}
  </>
}
/** Keep initialization available in embedded remote pages, whose sidebar is hidden. */
export function ModeWorkspaceCreation({ modes, content, remote }: { ctx: Context; modes: WorkspaceModes; content: ContentStore; remote: RemoteClient }) {
  const state = useStore(modes), catalog = useStore(content)
  return state.creating ? <CreateWorkspace modes={modes} remote={remote} workflows={catalog.workflows} close={() => modes.setCreating(false)} /> : null
}
