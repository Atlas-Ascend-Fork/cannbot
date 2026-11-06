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
import type { Context } from '@deepseek-ai/cordis'
import type {} from '@deepseek-ai/dsh-client-ui-workspace/client'

type Listing = Awaited<ReturnType<Context['uiWorkspace']['listDirectory']>>

/** Browse Host directories through the capability shared by Web and desktop pickers. */
export function WorkspaceDirectory({ ctx, initialPath, onSelect, onClose }: {
  ctx: Context; initialPath?: string; onSelect(id: string): void; onClose(): void
}) {
  const dialog = useRef<HTMLDialogElement>(null)
  const lifetime = useRef<AbortController | null>(null)
  const request = useRef<AbortController | null>(null)
  const [listing, setListing] = useState<Listing>()
  const [path, setPath] = useState(initialPath ?? '')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const browse = async (target?: string) => {
    request.current?.abort()
    const controller = new AbortController()
    request.current = controller
    setLoading(true); setError(''); setListing(undefined)
    try {
      const next = await ctx.uiWorkspace.listDirectory(target || undefined, controller.signal)
      if (!controller.signal.aborted) { setListing(next); setPath(next.path) }
    } catch (reason) {
      if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : '无法读取目录，请重试。')
    } finally { if (!controller.signal.aborted) setLoading(false) }
  }
  useEffect(() => {
    lifetime.current = new AbortController()
    dialog.current?.showModal()
    void browse(initialPath)
    return () => { lifetime.current?.abort(); request.current?.abort() }
  }, [])
  const choose = async () => {
    if (!listing || loading || saving) return
    setSaving(true); setError('')
    try {
      const existing = ctx.workspaces.list.getSnapshot().items.find(item => item.path === listing.path)
      const selected = existing ?? await ctx.workspaces.create({ path: listing.path })
      if (!lifetime.current?.signal.aborted) { onSelect(selected.workspaceId); onClose() }
    } catch (reason) {
      if (!lifetime.current?.signal.aborted) setError(reason instanceof Error ? reason.message : '无法选择工作区，请重试。')
    } finally { if (!lifetime.current?.signal.aborted) setSaving(false) }
  }
  return <dialog ref={dialog} className="cwb-directory" aria-label="选择工作区目录" onCancel={event => { event.preventDefault(); if (!saving) onClose() }}>
    <h2>选择工作区</h2>
    <p>选择 DSH 所在机器上的项目目录。</p>
    <form onSubmit={event => { event.preventDefault(); if (!saving) void browse(path) }}>
      <input aria-label="目录路径" value={path} disabled={saving} onChange={event => setPath(event.target.value)} />
      <button className="cwb-text-button" disabled={saving} type="submit">打开目录</button>
    </form>
    <nav aria-label="目录层级">{listing?.crumbs.map(crumb => <button type="button" className="cwb-text-button" key={crumb.path} disabled={saving} onClick={() => void browse(crumb.path)}>{crumb.name || crumb.path}</button>)}</nav>
    {loading ? <p role="status">正在读取目录…</p> : listing && <>
      <ul className="cwb-directory-list">{listing.entries.map(entry => <li key={entry.path}><button type="button" disabled={saving} onClick={() => void browse(entry.path)}><WorkbenchIcon name="folder" size={16} /> {entry.name}</button></li>)}</ul>
      {!listing.entries.length && <p>此目录下没有子目录，可以直接选择当前目录。</p>}
      {listing.truncated && <p>目录较多，仅显示部分结果；可输入完整路径打开。</p>}
    </>}
    {error && <div role="alert" className="cwb-error">{error}</div>}
    <footer><button type="button" className="cwb-text-button" disabled={saving} onClick={onClose}>取消</button><button type="button" className="cwb-primary" disabled={loading || saving || !listing || path !== listing.path} onClick={() => void choose()}>{saving ? '正在选择…' : '选择此目录'}</button></footer>
  </dialog>
}
