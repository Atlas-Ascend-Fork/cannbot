// ----------------------------------------------------------------------------------------------------------
// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.
// ----------------------------------------------------------------------------------------------------------

import { useEffect, useRef, useState } from 'react'
import { WorkbenchIcon } from './WorkbenchIcon.tsx'
import { WORKFLOWS } from '../contracts/workflows.ts'
import { GENERAL_WORKSPACE } from '../contracts/workspace-mode-types.ts'
import { zh } from './locales.ts'
import type { Context } from '@deepseek-ai/cordis'
import type {} from '@deepseek-ai/dsh-client-ui-workspace/client'

type Listing = Awaited<ReturnType<Context['uiWorkspace']['listDirectory']>>
type WorkspacePlugin = { id: string; title: string; description?: string }

function pluginLabel(plugin: WorkspacePlugin) {
  const workflow = WORKFLOWS.find(item => item.id === plugin.id)
  const description = plugin.description?.trim() || (workflow && zh[workflow.description]) || '按此工作流配置工作区。'
  return `${plugin.id}：${description}`
}

/** Browse Host directories through the capability shared by Web and desktop pickers. */
export function WorkspaceDirectory({ ctx, initialPath, onSelect, onClose, plugins, create }: {
  ctx: Context; initialPath?: string; onSelect(id: string): void; onClose(): void
  plugins?: readonly WorkspacePlugin[]; create?(path: string, pluginId: string): Promise<{ workspaceId: string }>
}) {
  const dialog = useRef<HTMLDialogElement>(null)
  const lifetime = useRef<AbortController | null>(null)
  const request = useRef<AbortController | null>(null)
  const [listing, setListing] = useState<Listing>()
  const [path, setPath] = useState(initialPath ?? '')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [pluginId, setPluginId] = useState('')
  const [folderName, setFolderName] = useState('')
  const [nativeOnly, setNativeOnly] = useState(false)
  const browse = async (target?: string) => {
    request.current?.abort()
    const controller = new AbortController()
    request.current = controller
    setLoading(true); setError(''); setListing(undefined)
    try {
      let next = await ctx.uiWorkspace.listDirectory(target || undefined, controller.signal)
      // Use the Host's root crumb: '/' on Linux, a qualified drive/UNC root on
      // Windows. Never infer the remote filesystem from the client's platform.
      const root = next.crumbs[0]?.path
      if (!target && root && root !== next.path && !controller.signal.aborted) {
        next = await ctx.uiWorkspace.listDirectory(root, controller.signal)
      }
      if (!controller.signal.aborted) { setListing(next); setPath(next.path) }
    } catch (reason) {
      if (!controller.signal.aborted) {
        const unavailable = (reason as { rpcError?: { code?: string } } | null)?.rpcError?.code === 'directory-picker/unavailable'
          || (reason instanceof Error && reason.message.includes('directory-picker/unavailable'))
        if (unavailable) { setNativeOnly(true); setError('') }
        else setError(reason instanceof Error ? reason.message : '无法读取目录，请重试。')
      }
    } finally { if (!controller.signal.aborted) setLoading(false) }
  }
  useEffect(() => {
    lifetime.current = new AbortController()
    dialog.current?.showModal()
    void browse(initialPath)
    return () => { lifetime.current?.abort(); request.current?.abort() }
  }, [])
  const choose = async () => {
    const selectedPath = nativeOnly ? path.trim() : listing?.path
    if (!selectedPath || loading || saving || (create && !pluginId)) return
    setSaving(true); setError('')
    try {
      const existing = !create && ctx.workspaces.list.getSnapshot().items.find(item => item.path === selectedPath)
      const selected = create ? await create(selectedPath, pluginId) : existing || await ctx.workspaces.create({ path: selectedPath })
      if (!lifetime.current?.signal.aborted) { onSelect(selected.workspaceId); onClose() }
    } catch (reason) {
      if (!lifetime.current?.signal.aborted) setError(reason instanceof Error ? reason.message : '无法选择工作区，请重试。')
    } finally { if (!lifetime.current?.signal.aborted) setSaving(false) }
  }
  const pickNative = async () => {
    if (saving) return
    setSaving(true); setError('')
    try { const selected = await ctx.uiWorkspace.pickDirectory(); if (selected && !lifetime.current?.signal.aborted) { setPath(selected); setNativeOnly(true) } }
    catch { if (!lifetime.current?.signal.aborted) setError('无法打开系统目录选择器，可在上方填写目录的绝对路径。') }
    finally { if (!lifetime.current?.signal.aborted) setSaving(false) }
  }
  const createFolder = async () => {
    if (!listing || saving || !folderName.trim()) return
    setSaving(true); setError('')
    try { const created = await ctx.uiWorkspace.createDirectory(listing.path, folderName.trim()); setFolderName(''); await browse(created) }
    catch (reason) { if (!lifetime.current?.signal.aborted) setError(reason instanceof Error ? reason.message : '无法新建目录，请重试。') }
    finally { if (!lifetime.current?.signal.aborted) setSaving(false) }
  }
  return <dialog ref={dialog} className="cwb-directory" aria-label="选择工作区目录" onCancel={event => { event.preventDefault(); if (!saving) onClose() }}>
    <h2>{create ? '创建 CANNBot 工作区' : '选择工作区'}</h2>
    <p>{create ? '选择一个空目录。空白工作区不预装工作流，供手动配置昇腾项目；也可以选择一种工作流进行初始化。' : '选择 DSH 所在机器上的项目目录。'}</p>
    {create && <label className="cwb-plugin-choice">工作区工作流<select aria-label="工作区工作流" value={pluginId} required disabled={saving} onChange={event => setPluginId(event.target.value)}><option value="" disabled>选择一个工作流</option><option value={GENERAL_WORKSPACE}>空白工作区：不安装工作流</option>{plugins?.map(plugin => <option key={plugin.id} value={plugin.id}>{pluginLabel(plugin)}</option>)}</select></label>}
    <form onSubmit={event => { event.preventDefault(); if (!saving && !nativeOnly) void browse(path) }}>
      <input aria-label="目录路径" value={path} disabled={saving} onChange={event => setPath(event.target.value)} />
      {nativeOnly ? <button className="cwb-text-button" disabled={saving} type="button" onClick={() => void pickNative()}>选择文件夹</button> : <button className="cwb-text-button" disabled={saving} type="submit">打开目录</button>}
    </form>
    {nativeOnly && <p>使用系统文件夹选择器，或填写目录的绝对路径。{create && '创建时会检查目录为空。'}</p>}
    <nav aria-label="目录层级">{listing?.crumbs.map(crumb => <button type="button" className="cwb-text-button" key={crumb.path} disabled={saving} onClick={() => void browse(crumb.path)}>{crumb.name || crumb.path}</button>)}</nav>
    {create && !nativeOnly && typeof ctx.uiWorkspace.createDirectory === 'function' && <form onSubmit={event => { event.preventDefault(); void createFolder() }}><input aria-label="新文件夹名称" placeholder="在当前目录下新建文件夹" value={folderName} onChange={event => setFolderName(event.target.value)} disabled={saving || loading} /><button type="submit" className="cwb-text-button" disabled={saving || loading || !folderName.trim()}>新建文件夹</button></form>}
    {loading ? <p role="status">正在读取目录…</p> : listing && <>
      <ul className="cwb-directory-list">{listing.entries.map(entry => <li key={entry.path}><button type="button" disabled={saving} onClick={() => void browse(entry.path)}><WorkbenchIcon name="folder" size={16} /> {entry.name}</button></li>)}</ul>
      {!listing.entries.length && <p>{create ? '此目录下没有子目录；创建时还会检查文件，确认目录为空。' : '此目录下没有子目录，可以直接选择当前目录。'}</p>}
      {listing.truncated && <p>目录较多，仅显示部分结果；可输入完整路径打开。</p>}
    </>}
    {error && <div role="alert" className="cwb-error">{error}</div>}
    <footer><button type="button" className="cwb-text-button" disabled={saving} onClick={onClose}>取消</button><button type="button" className="cwb-primary" disabled={loading || saving || (nativeOnly ? !path.trim() : !listing || path !== listing.path) || (!!create && !pluginId)} onClick={() => void choose()}>{saving ? (create ? (pluginId === GENERAL_WORKSPACE ? '正在创建…' : '正在初始化…') : '正在选择…') : (create ? (!pluginId || pluginId === GENERAL_WORKSPACE ? '创建工作区' : '创建并初始化') : '选择此目录')}</button></footer>
  </dialog>
}
