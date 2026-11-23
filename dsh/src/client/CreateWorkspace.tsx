// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { GENERAL_WORKSPACE, CANNBOT_WORKSPACES_PATH } from '../workspace-mode-types.ts'
import type { CANNBotWorkspace } from '../workspace-mode-types.ts'
import type { WorkspaceCreationRequest } from '../workspace-creation.ts'
import type { WorkspaceModes } from './workspace-modes.ts'
import type { RemoteClient } from './remote/types.ts'
import { WorkbenchIcon } from './WorkbenchIcon.tsx'
import { WORKFLOWS } from '../workflows.ts'
import { zh } from './locales.ts'
import { InitializationDialog } from './InitializationDialog.tsx'
import type { InitializationOperation } from '../initialization-contract.ts'

type Listing = { path: string; crumbs: { name: string; path: string }[]; entries: { name: string; path: string }[]; truncated: boolean; partial?: boolean }
export function CreateWorkspace({ modes, remote, workflows, close }: {
  modes: WorkspaceModes; remote: RemoteClient; workflows: readonly { id: string; description?: string }[]; close(): void
}) {
  const servers = useSyncExternalStore(remote.subscribe, remote.getSnapshot)
  const host = useSyncExternalStore(modes.subscribe, modes.getSnapshot)
  const localWorkflowAllowed = host.platform === 'linux'
  const dialog = useRef<HTMLDialogElement>(null), reading = useRef<AbortController | null>(null), alive = useRef(true)
  const parentPicker = useRef<HTMLDivElement>(null), typing = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const [serverId, setServerId] = useState<string | null>(modes.getSnapshot().creationServerId || '')
  const [name, setName] = useState(''), [parent, setParent] = useState(''), [pluginId, setPluginId] = useState('')
  const [listing, setListing] = useState<Listing>(), [browseOpen, setBrowseOpen] = useState(false)
  const [loading, setLoading] = useState(true), [saving, setSaving] = useState(false), [error, setError] = useState('')
  const [connection, setConnection] = useState<{ id: string; autoStart: boolean } | null>(null)
  const [initialization, setInitialization] = useState<InitializationOperation>()
  const workflowNotice = !!pluginId && pluginId !== GENERAL_WORKSPACE
  const submission = useRef({ key: '', requestId: '' })
  const selectedServer = servers.servers.find(server => server.id === serverId)
  const connected = serverId !== null && (!serverId || selectedServer?.connected === true)
  const remoteLocation = !!serverId || modes.embedded
  const send = async (body: WorkspaceCreationRequest, signal?: AbortSignal) => {
    const url = new URL(serverId ? 'api/cannbot-remote/tree?id=' + encodeURIComponent(serverId) : CANNBOT_WORKSPACES_PATH, document.baseURI)
    const response = await fetch(url, { method: 'POST', credentials: 'same-origin', cache: 'no-store', signal,
      headers: { 'content-type': 'application/json', ...(modes.embedded ? { 'x-cannbot-remote-workspace': '1' } : {}) }, body: JSON.stringify(body) })
    const value = await response.json()
    if (!response.ok) throw new Error(value.message || '操作未完成，请检查目录或服务器连接后重试。')
    return value
  }
  const browse = async (path = '', complete = false) => {
    clearTimeout(typing.current)
    reading.current?.abort()
    const controller = new AbortController(); reading.current = controller
    setLoading(true); setError(''); setListing(undefined)
    try {
      const value = await send({ action: 'browse-directory', path, ...(complete && { complete }) }, controller.signal) as Listing
      if (!controller.signal.aborted && alive.current) { setListing(value); if (!value.partial) setParent(value.path); return value }
    } catch (reason) { if (!controller.signal.aborted && alive.current) setError(reason instanceof Error ? reason.message : '无法读取目录。') }
    finally { if (!controller.signal.aborted && alive.current) setLoading(false) }
  }
  useEffect(() => { alive.current = true; dialog.current?.showModal(); return () => { alive.current = false; reading.current?.abort(); clearTimeout(typing.current) } }, [])
  useEffect(() => {
    reading.current?.abort(); clearTimeout(typing.current); setBrowseOpen(false); setListing(undefined); setParent(connected && remoteLocation ? '/' : ''); setError(''); setLoading(false)
    if (connected) void browse()
    return () => reading.current?.abort()
  }, [serverId, connected])
  const confirmParent = () => {
    clearTimeout(typing.current); setBrowseOpen(false)
    if (connected && listing?.path !== parent) void browse(parent)
  }
  useEffect(() => {
    if (!browseOpen) return
    const outside = (event: PointerEvent) => { if (!parentPicker.current?.contains(event.target as Node)) confirmParent() }
    document.addEventListener('pointerdown', outside)
    return () => document.removeEventListener('pointerdown', outside)
  }, [browseOpen, parent, listing, connected])
  const selectServer = (id: string, autoStart = false) => {
    setServerId(id); setError('')
    const server = remote.getSnapshot().servers.find(item => item.id === id)
    if (server && !server.connected) setConnection({ id, autoStart })
  }
  const chooseType = (value: string) => {
    if (value !== GENERAL_WORKSPACE && !remoteLocation && !localWorkflowAllowed) setServerId(null)
    setError(''); setPluginId(value)
  }
  const invalidName = !name.trim() || /[<>:"/\\|?*\x00-\x1f]/.test(name) || /[. ]$/.test(name) || /^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/i.test(name)
  const create = async () => {
    if (saving || loading || !connected || invalidName || !pluginId || !listing || listing.path !== parent) return
    if (workflowNotice && !remoteLocation && !localWorkflowAllowed) return
    setSaving(true); setError('')
    const key = JSON.stringify([serverId, parent, name.trim(), pluginId])
    if (submission.current.key !== key) submission.current = { key, requestId: crypto.randomUUID() }
    try {
      if (workflowNotice) {
        setInitialization({ action: 'create-folder', parent, name: name.trim(), pluginId, requestId: submission.current.requestId })
        return
      }
      const result = await send({ action: 'create-folder', parent, name: name.trim(), pluginId, requestId: submission.current.requestId }) as { workspace: CANNBotWorkspace }
      // Closing a native dialog must never re-run a committed initialization.
      if (!alive.current) return
      if (serverId) {
        close(); modes.selectServer(serverId)
        await remote.open({ serverId, workspaceId: result.workspace.workspaceId, recommendPermissions: false })
      } else {
        modes.enterCreatedWorkspace(result.workspace); close()
      }
    } catch (reason) { if (alive.current) setError(reason instanceof Error ? reason.message : '创建未完成，请重试。') }
    finally { if (alive.current && !workflowNotice) setSaving(false) }
  }
  return <dialog ref={dialog} className="cwb-directory cb-create-workspace" aria-label="创建工作区" onCancel={event => { event.preventDefault(); if (!saving && !connection) close() }}>
    <h2>创建工作区</h2>
    <label className="cb-create-field">工作流<select autoFocus aria-label="工作流" value={pluginId} required disabled={saving} onChange={event => chooseType(event.target.value)}><option value="" disabled>选择一个工作流</option><option value={GENERAL_WORKSPACE}>空白工作区：不安装工作流</option>{workflows.map(workflow => <option key={workflow.id} value={workflow.id}>{workflow.id}：{workflow.description?.trim() || zh[WORKFLOWS.find(item => item.id === workflow.id)?.description ?? 'flashDescription']}</option>)}</select></label>
    <label className="cb-create-field">服务器<select aria-label="服务器" value={serverId ?? '__select_server__'} disabled={saving || modes.embedded} onChange={event => {
      if (event.target.value === '__add_server__') {
        remote.showConnections(id => { if (alive.current) selectServer(id, true) })
      } else if (event.target.value !== '' || !workflowNotice || localWorkflowAllowed) { selectServer(event.target.value) }
    }}>
      <option value="__select_server__" disabled>选择一个服务器</option>
      <option value="" disabled={workflowNotice && !localWorkflowAllowed}>{modes.embedded ? '此服务器' : workflowNotice && !localWorkflowAllowed ? '本机（本工作流需要连接NPU的Linux环境）' : '本机'}</option>
      {!modes.embedded && servers.servers.map(server => <option value={server.id} key={server.id} aria-label={`${server.label || server.alias}，${server.connected ? '已连接' : '未连接'}`}>{server.connected ? '🟢' : '🔴'} {server.label || server.alias}</option>)}
      {!modes.embedded && <option value="__add_server__">添加服务器</option>}
    </select></label>
    {workflowNotice && !connected && <p role="alert" className="cwb-error">本工作流需要在连接了NPU环境的Linux服务器上创建</p>}
    <div ref={parentPicker} className="cb-parent-picker">
      <label className="cb-create-field">父目录<input aria-label="父目录" aria-expanded={browseOpen} aria-controls="cb-parent-directories" autoComplete="off" value={parent} disabled={saving || !connected}
        onClick={() => setBrowseOpen(true)} onChange={event => {
          const value = event.target.value; reading.current?.abort(); clearTimeout(typing.current)
          setParent(value); setBrowseOpen(true); setError(''); setLoading(true)
          typing.current = setTimeout(() => { void browse(value, true) }, 250)
        }} onKeyDown={event => {
          if (event.key === 'Enter') { event.preventDefault(); setBrowseOpen(true); void browse(parent, true) }
          if (event.key === 'Escape' && browseOpen) { event.preventDefault(); event.stopPropagation(); confirmParent() }
          if (event.key === 'Tab' && !event.shiftKey && browseOpen && parent !== listing?.path) {
            event.preventDefault(); void browse(parent, true).then(value => { if (value?.partial && value.entries.length) void browse(value.entries[0].path) })
          }
        }} /></label>
      {browseOpen && <div id="cb-parent-directories" className="cb-parent-browser" style={{ maxHeight: Math.max(120, window.innerHeight - (parentPicker.current?.getBoundingClientRect().bottom ?? 0) - 16) }}>
        {loading && <p role="status">正在读取目录…</p>}
        {!loading && listing && <><nav aria-label="目录层级">{listing.crumbs.map(crumb => <button type="button" className="cwb-text-button" key={crumb.path} disabled={saving} onClick={() => void browse(crumb.path)}>{crumb.name}</button>)}</nav><ul className="cwb-directory-list">{listing.entries.map(entry => <li key={entry.path}><button type="button" disabled={saving} onClick={() => void browse(entry.path)}><WorkbenchIcon name="folder" size={16} />{entry.name}</button></li>)}</ul>{!listing.entries.length && <p>{listing.partial ? '没有匹配的文件夹。' : '此目录下没有子文件夹。'}</p>}{listing.truncated && <p>仅显示部分目录，可输入完整路径。</p>}</>}
        <footer><button type="button" className="cwb-text-button" disabled={loading || saving || !listing || parent !== listing.path} onClick={confirmParent}>确认</button></footer>
      </div>}
    </div>
    {loading && !browseOpen && <p role="status">正在读取目录…</p>}
    <label className="cb-create-field">工作区名<input aria-label="工作区名" placeholder="新工作区名称" value={name} disabled={saving} onChange={event => setName(event.target.value)} /></label>
    {error && <p role="alert" className="cwb-error">{error}</p>}
    {initialization && <InitializationDialog operation={initialization} serverId={serverId || ''} close={() => { setInitialization(undefined); setSaving(false) }} complete={value => {
      const result = value as { workspace: CANNBotWorkspace }
      setInitialization(undefined); setSaving(false)
      if (serverId) { close(); modes.selectServer(serverId); void remote.open({ serverId, workspaceId: result.workspace.workspaceId, recommendPermissions: true }) }
      else { modes.enterCreatedWorkspace(result.workspace); close() }
    }} />}
    {connection && <WorkspaceConnectionDialog remote={remote} id={connection.id} autoStart={connection.autoStart} complete={() => setConnection(null)} cancel={() => { setConnection(null); setServerId(null) }} />}
    <footer><button type="button" className="cwb-text-button" disabled={saving} onClick={close}>取消</button><button type="button" className="cwb-primary" disabled={saving || loading || !connected || invalidName || !pluginId || !listing || parent !== listing.path} onClick={() => void create()}>{saving ? '正在创建…' : '创建工作区'}</button></footer>
  </dialog>
}

function WorkspaceConnectionDialog({ remote, id, autoStart, complete, cancel }: {
  remote: RemoteClient; id: string; autoStart: boolean; complete(): void; cancel(): void
}) {
  const state = useSyncExternalStore(remote.subscribe, remote.getSnapshot)
  const dialog = useRef<HTMLDialogElement>(null), log = useRef<HTMLPreElement>(null), alive = useRef(true), running = useRef(false)
  const cancelling = useRef(false)
  const [stopping, setStopping] = useState(false)
  const [phase, setPhase] = useState<'confirm' | 'connecting' | 'error'>(autoStart ? 'connecting' : 'confirm')
  const [error, setError] = useState('')
  const server = state.servers.find(item => item.id === id)
  const connect = async () => {
    if (running.current) return
    if (remote.getSnapshot().servers.find(item => item.id === id)?.connected) { complete(); return }
    running.current = true; setPhase('connecting'); setError('')
    try { await remote.connect(id); if (alive.current && !cancelling.current) complete() }
    catch (reason) { if (alive.current && !cancelling.current) { setError(reason instanceof Error ? reason.message : '连接失败，请重试。'); setPhase('error') } }
    finally { running.current = false }
  }
  const stop = async () => {
    if (cancelling.current) return
    if (phase !== 'connecting') { cancel(); return }
    cancelling.current = true; setStopping(true); setError('')
    try { await remote.cancelConnect(id); if (alive.current) cancel() }
    catch { if (alive.current) { cancelling.current = false; setStopping(false); setError('取消连接未完成，请重试。') } }
  }
  useEffect(() => {
    alive.current = true; dialog.current?.showModal()
    if (autoStart) void connect()
    return () => { alive.current = false }
  }, [])
  useEffect(() => { if (log.current) log.current.scrollTop = log.current.scrollHeight }, [state.progress])
  return <dialog ref={dialog} className={`cwb-directory cb-workspace-connection ${phase !== 'confirm' ? 'cb-connection-progress' : ''}`} aria-label={phase === 'confirm' ? '连接服务器' : '服务器连接与安装'} onCancel={event => { event.preventDefault(); event.stopPropagation(); void stop() }}>
    <header><h2>{phase === 'confirm' ? '连接服务器' : '服务器连接与安装'}</h2>{phase === 'connecting' && <button type="button" className="cwb-text-button" disabled={stopping} onClick={() => void stop()}>{stopping ? '正在取消…' : '取消'}</button>}</header>
    <p>{server?.label || server?.alias || id}</p>
    {phase === 'confirm' ? <p>服务器还未连接，是否立即连接？</p> : <pre ref={log} role="log" aria-label="连接与安装日志" aria-live="polite">{state.progress.join('\n') || '正在连接服务器…'}</pre>}
    {error && <p role="alert" className="cwb-error">{error}</p>}
    {phase === 'connecting' ? <p role="status">正在连接并准备环境，完成后自动关闭…</p> : <footer>
      <button type="button" className="cwb-text-button" onClick={cancel}>{phase === 'confirm' ? '取消' : '关闭'}</button>
      <button type="button" className="cwb-primary" disabled={state.busy} onClick={() => void connect()}>{phase === 'confirm' ? '确认' : '重试'}</button>
    </footer>}
  </dialog>
}
