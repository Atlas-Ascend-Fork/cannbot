// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { useEffect, useRef, useState, useSyncExternalStore, type ReactNode } from 'react'
import { GENERAL_WORKSPACE, CANNBOT_WORKSPACES_PATH } from '../contracts/workspace-mode-types.ts'
import type { CANNBotWorkspace } from '../contracts/workspace-mode-types.ts'
import type { WorkspaceCreationRequest } from '../contracts/workspace-creation-contract.ts'
import type { WorkspaceModes } from './workspace-modes.ts'
import { WorkbenchIcon } from './WorkbenchIcon.tsx'
import { WORKFLOWS } from '../contracts/workflows.ts'
import { zh } from './locales.ts'
import { InitializationDialog } from './InitializationDialog.tsx'
import type { InitializationOperation } from '../contracts/initialization-contract.ts'

type Listing = { path: string; crumbs: { name: string; path: string }[]; entries: { name: string; path: string }[]; truncated: boolean; partial?: boolean }
export interface WorkspaceFormProps {
  modes: WorkspaceModes
  workflows: readonly { id: string; description?: string }[]
  close(): void
}
interface LocationField {
  saving: boolean
  workflowNotice: boolean
  localWorkflowAllowed: boolean
}
export interface WorkspaceLocation {
  serverId: string | null
  connected: boolean
  endpoint?: string
  connecting: boolean
  clearSelection(): void
  field(props: LocationField): ReactNode
  onCreated?(workspace: CANNBotWorkspace, recommendPermissions: boolean): Promise<void>
}
export function WorkspaceForm({ modes, workflows, close, location }: WorkspaceFormProps & { location?: WorkspaceLocation }) {
  const host = useSyncExternalStore(modes.subscribe, modes.getSnapshot)
  const localWorkflowAllowed = host.platform === 'linux'
  const serverId = location ? location.serverId : ''
  const connected = location?.connected ?? true
  const dialog = useRef<HTMLDialogElement>(null), reading = useRef<AbortController | null>(null), alive = useRef(true)
  const parentPicker = useRef<HTMLDivElement>(null), typing = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const [name, setName] = useState(''), [parent, setParent] = useState(''), [pluginId, setPluginId] = useState('')
  const [listing, setListing] = useState<Listing>(), [browseOpen, setBrowseOpen] = useState(false)
  const [loading, setLoading] = useState(true), [saving, setSaving] = useState(false), [error, setError] = useState('')
  const [initialization, setInitialization] = useState<InitializationOperation>()
  const workflowNotice = !!pluginId && pluginId !== GENERAL_WORKSPACE
  const submission = useRef({ key: '', requestId: '' })
  const remoteLocation = !!serverId || modes.embedded
  const send = async (body: WorkspaceCreationRequest, signal?: AbortSignal) => {
    const url = new URL(location?.endpoint || CANNBOT_WORKSPACES_PATH, document.baseURI)
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
  const chooseType = (value: string) => {
    if (value !== GENERAL_WORKSPACE && !remoteLocation && !localWorkflowAllowed) location?.clearSelection()
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
      if (location?.onCreated) await location.onCreated(result.workspace, false)
      else { modes.enterCreatedWorkspace(result.workspace); close() }
    } catch (reason) { if (alive.current) setError(reason instanceof Error ? reason.message : '创建未完成，请重试。') }
    finally { if (alive.current && !workflowNotice) setSaving(false) }
  }
  return <dialog ref={dialog} className="cwb-directory cb-create-workspace" aria-label="创建工作区" onCancel={event => { event.preventDefault(); if (!saving && !location?.connecting) close() }}>
    <h2>创建工作区</h2>
    <label className="cb-create-field">工作流<select autoFocus aria-label="工作流" value={pluginId} required disabled={saving} onChange={event => chooseType(event.target.value)}><option value="" disabled>选择一个工作流</option><option value={GENERAL_WORKSPACE}>空白工作区：不安装工作流</option>{workflows.map(workflow => <option key={workflow.id} value={workflow.id}>{workflow.id}：{workflow.description?.trim() || zh[WORKFLOWS.find(item => item.id === workflow.id)?.description ?? 'flashDescription']}</option>)}</select></label>
    {location ? location.field({ saving, workflowNotice, localWorkflowAllowed }) : <label className="cb-create-field">服务器<input aria-label="服务器" readOnly value={modes.embedded ? '此服务器' : '本机'} /></label>}
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
    {initialization && <InitializationDialog operation={initialization} endpoint={location?.endpoint} close={() => { setInitialization(undefined); setSaving(false) }} complete={value => {
      const result = value as { workspace: CANNBotWorkspace }
      setInitialization(undefined); setSaving(false)
      if (location?.onCreated) void location.onCreated(result.workspace, true).catch(() => { if (alive.current) setError('工作区已创建，请从侧边栏重新打开。') })
      else { modes.enterCreatedWorkspace(result.workspace); close() }
    }} />}
    <footer><button type="button" className="cwb-text-button" disabled={saving} onClick={close}>取消</button><button type="button" className="cwb-primary" disabled={saving || loading || !connected || invalidName || !pluginId || !listing || parent !== listing.path} onClick={() => void create()}>{saving ? '正在创建…' : '创建工作区'}</button></footer>
  </dialog>
}
