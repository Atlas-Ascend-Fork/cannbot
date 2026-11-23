// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { createElement, useEffect, useRef, useState, useSyncExternalStore } from 'react'
import type { Context } from '@deepseek-ai/cordis'
import type { MainPanelId } from '@deepseek-ai/dsh-client-ui-layout/client'
import { injectSlot } from '../slot-compat.ts'
import { createNativeGuest, desktopBrowser, remoteUrl } from './native-guest.mjs'
import type { RemoteClient, RemoteServer, RemoteSnapshot, RemoteTarget, RemoteTree } from './types.ts'
import './remote.css'

export type { RemoteClient, RemoteServer, RemoteSnapshot, RemoteTarget, RemoteTree } from './types.ts'
const PANEL = 'cannbot-remote-workbench' as MainPanelId
const HOME = 'cannbot-dsh-workbench' as MainPanelId
const endpoint = (path: string) => new URL('api/cannbot-remote/' + path, document.baseURI)
const safeMessage = (value: unknown) => String(value ?? '').replace(/https?:\/\/[^\s"'<>]+/gi, '[远端地址]').replace(/(token[=:]\s*)[^\s&]+/gi, '$1[已隐藏]')

export function createRemoteClient(ctx: Context, options: { onReturnLocal?(): void; onSelectServer?(id: string): void; onCreateWorkspace?(id: string): void } = {}): RemoteClient {
  let state: RemoteSnapshot = { servers: [], busy: false, error: '', progress: [], syncLogin: false, revision: 0, target: null, status: 'idle', notice: '' }
  const loginConsent = new Set<string>()
  const listeners = new Set<() => void>()
  const urls = new Map<string, string>()
  const connecting = new Map<string, Promise<void>>()
  const attempts = new Map<string, { controller: AbortController; requestId: string; cancelling: boolean }>()
  const disconnecting = new Map<string, Promise<void>>()
  const removing = new Map<string, Promise<void>>()
  const lifetime = new AbortController()
  let disposed = false, started = false, pullSequence = 0, openSequence = 0
  let serverAdded: ((id: string) => void) | undefined
  let timer: ReturnType<typeof setTimeout> | undefined
  let guest: ReturnType<typeof createNativeGuest> | null = null
  let requestedTarget: RemoteTarget | null = null
  const releases: (() => void)[] = []
  const publish = (next: Partial<RemoteSnapshot>) => {
    if (disposed) return
    state = { ...state, ...next }
    for (const listener of listeners) listener()
  }
  const inOrder = (servers: RemoteServer[], ids: readonly string[]) => {
    const rank = new Map(ids.map((id, index) => [id, index]))
    return [...servers].sort((left, right) => (rank.get(left.id) ?? ids.length) - (rank.get(right.id) ?? ids.length))
  }
  async function json(path: string, init?: RequestInit) {
    const response = await fetch(endpoint(path), { credentials: 'same-origin', cache: 'no-store', ...init,
      // Leave time for the Host's 15-second tunnel deadline to report its result.
      signal: AbortSignal.any([lifetime.signal, AbortSignal.timeout(20000)]) })
    const result = await response.json()
    if (!response.ok || result.ok === false) {
      const error = new Error(safeMessage(result.message || result.error || '远程连接请求失败，请重试。'))
      Object.assign(error, { code: typeof result.error === 'string' ? result.error : '', status: response.status,
        ...(Array.isArray(result.activity) && { activity: result.activity }) })
      throw error
    }
    return result
  }
  async function pull() {
    const sequence = ++pullSequence
    try {
      const result = await json('servers')
      if (disposed || sequence !== pullSequence || !Array.isArray(result.servers)) return
      const servers = result.servers.filter((item: RemoteServer) => item && typeof item.id === 'string' && typeof item.alias === 'string').map((item: RemoteServer & { url?: string }) => {
        if (item.connected && item.url) { try { urls.set(item.id, remoteUrl(item.url)) } catch { urls.delete(item.id) } }
        else urls.delete(item.id)
        return { id: item.id, alias: item.alias, label: item.label || item.alias, connected: !!item.connected,
          localPort: item.localPort, remotePort: item.remotePort, loginSync: item.loginSync }
      })
      publish({ servers: state.orderingServers ? inOrder(servers, state.servers.map(server => server.id)) : servers })
    } catch (error) { if (!disposed && sequence === pullSequence) publish({ error: safeMessage(error instanceof Error ? error.message : '无法读取服务器列表，请重试。') }) }
  }
  function stopGuest() { const old = guest; guest = null; if (old) void old.dispose() }
  function back() {
    ++openSequence
    stopGuest()
    ctx.layout.selectPanel(HOME)
    options.onReturnLocal?.()
  }
  async function disconnectServer(id: string, remove = false) {
    // The Host's existing disconnect closes only a ready local tunnel. A stream
    // cancellation does not cancel its bootstrap, so let an already-started
    // connect settle before issuing the single disconnect; it cannot recreate
    // the tunnel after this call succeeds.
    await connecting.get(id)?.catch(() => {})
    if (disposed) return
    await json(remove ? 'servers/remove' : 'disconnect', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ id }) })
    if (disposed) return
    ++pullSequence
    urls.delete(id)
    const ownsTarget = state.target?.serverId === id, ownsRequest = requestedTarget?.serverId === id
    const ownsSelection = state.selectedServerId === id
    const visible = ctx.layout.panelInfo.getSnapshot().activePanelId === PANEL
      && (ownsTarget || (!state.target && ownsRequest && ownsSelection))
    if (ownsTarget) stopGuest()
    if (ownsRequest) requestedTarget = null
    publish({ servers: remove ? state.servers.filter(server => server.id !== id) : state.servers.map(server => server.id === id ? { ...server, connected: false } : server),
      ...(ownsSelection ? { selectedServerId: undefined } : {}),
      ...(ownsTarget || ownsRequest ? { target: ownsTarget ? null : state.target, revision: state.revision + 1, status: 'idle', error: '', notice: '', progress: [] } : {}),
    })
    // A remembered remote target may survive Return Local or a DeepSeek switch.
    // Only leave the actually displayed guest; another server/page keeps focus.
    if (visible) { ctx.layout.selectPanel(HOME); options.onReturnLocal?.() }
  }
  async function streamConnect(id: string, attempt: { controller: AbortController; requestId: string; cancelling: boolean }) {
    desktopBrowser()
    publish({ busy: true, error: '', progress: [] })
    const address = endpoint('connect-stream')
    address.searchParams.set('id', id)
    address.searchParams.set('syncLogin', loginConsent.has(id) ? '1' : '0')
    address.searchParams.set('requestId', attempt.requestId)
    let reader: ReadableStreamDefaultReader<Uint8Array> | undefined
    let done = false
    try {
      const response = await fetch(address, { credentials: 'same-origin', cache: 'no-store', signal: AbortSignal.any([lifetime.signal, attempt.controller.signal]) })
      if (!response.ok || !response.body) throw new Error('无法建立远程连接，请重试。')
      reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      while (!disposed) {
        const chunk = await reader.read()
        if (chunk.done) break
        buffer += decoder.decode(chunk.value, { stream: true }).replace(/\r/g, '')
        let boundary: number
        while ((boundary = buffer.indexOf('\n\n')) >= 0) {
          const block = buffer.slice(0, boundary); buffer = buffer.slice(boundary + 2)
          const data = block.split('\n').filter(line => line.startsWith('data:')).map(line => line.slice(5).trimStart()).join('\n')
          if (!data) continue
          const event = JSON.parse(data)
          if (event.phase === 'password' && typeof event.challengeId === 'string' && typeof event.prompt === 'string') {
            publish({ passwordRequests: [...(state.passwordRequests || []).filter(item => item.serverId !== id),
              { serverId: id, challengeId: event.challengeId, prompt: event.prompt, retry: !!event.retry }] })
          }
          if (event.phase === 'error' || event.ok === false) throw new Error(safeMessage(event.message || event.error || '连接失败，请重试。'))
          if (event.message) publish({ progress: [...state.progress.slice(-79), safeMessage(event.message)] })
          if (event.phase === 'done') {
            if (!event.ok || typeof event.url !== 'string') throw new Error('远端未返回可用工作台，请重新连接。')
            urls.set(id, remoteUrl(event.url)); done = true
          }
        }
      }
      if (!done && !disposed) throw new Error('连接在完成前中断，请重新连接。')
      if (!attempt.cancelling) await pull()
    } catch (error) {
      const message = safeMessage(error instanceof Error ? error.message : '远程连接失败，请重试。')
      if (!attempt.cancelling) publish({ error: message })
      throw new Error(message)
    } finally { if (reader) { try { await reader.cancel() } catch { /* Channel may already be closed. */ } }
      publish({ busy: false, passwordRequests: (state.passwordRequests || []).filter(item => item.serverId !== id) }) }
  }
  function attach(host: HTMLElement) {
    const target = state.target, revision = state.revision
    if (!target || disposed) return () => {}
    stopGuest()
    const initial = urls.get(target.serverId)
    if (!initial) { publish({ status: 'error', error: '请重新连接服务器后打开工作台。' }); return () => {} }
    const address = new URL(initial)
    const fragment = new URLSearchParams({ cannEmbed: '1', cannMode: 'cannbot' })
    if (target.createWorkspace) fragment.set('cannCreateWorkspace', '1')
    else {
      if (target.workspaceId) fragment.set('cannWorkspace', target.workspaceId)
      if (target.recommendPermissions) fragment.set('cannRecommendPermissions', '1')
      if (target.sessionId) fragment.set('cannSession', target.sessionId)
    }
    address.hash = fragment.toString()
    try {
      let current: ReturnType<typeof createNativeGuest> | undefined
      current = createNativeGuest({ bridge: desktopBrowser(), host, url: address.href, workspaceKey: 'cannbot-remote:' + target.serverId,
        onState: next => { if (current && guest === current && state.revision === revision) publish(next) },
        onCreateWorkspace: () => { if (current && guest === current && state.revision === revision) options.onCreateWorkspace?.(target.serverId) },
        onLocation: scope => {
          if (!current || guest !== current || state.revision !== revision) return
          const next = { serverId: target.serverId, ...scope }
          requestedTarget = next
          if (state.target?.workspaceId !== next.workspaceId || state.target?.sessionId !== next.sessionId || state.target?.createWorkspace) publish({ target: next })
        },
      })
      guest = current
      const mounted = current
      return () => { if (guest === mounted) guest = null; void mounted.dispose() }
    } catch { publish({ status: 'error', error: '当前桌面环境无法打开内嵌工作台，请重新连接。' }); return () => {} }
  }
  function reload() {
    if (!state.target && requestedTarget) { void client.open(requestedTarget).catch(() => {}); return }
    if (state.status !== 'error' && guest?.reload()) return
    stopGuest()
    publish({ revision: state.revision + 1, error: '', status: 'loading', notice: '' })
  }
  const client: RemoteClient = {
    getSnapshot: () => state,
    subscribe(listener) { listeners.add(listener); return () => { listeners.delete(listener) } },
    start() {
      if (started || disposed) return () => {}
      started = true
      releases.push(injectSlot(ctx, 'main', () => ctx.slots.register({ name: 'main', key: PANEL }, () => createElement(RemotePage, { client, attach, reload }))))
      releases.push(injectSlot(ctx, 'shell.overlay', () => ctx.slots.register({ name: 'shell.overlay', id: 'cannbot-ssh-password' }, () => createElement(PasswordPrompt, { client,
        submit: async (serverId: string, challengeId: string, password: string) => {
          const attempt = attempts.get(serverId)
          if (!attempt || attempt.cancelling) throw new Error('连接已取消，请重新连接。')
          await json('password', { method: 'POST', headers: { 'content-type': 'application/json' },
            body: JSON.stringify({ id: serverId, requestId: attempt.requestId, challengeId, password }) })
          publish({ passwordRequests: (state.passwordRequests || []).filter(item => item.challengeId !== challengeId) })
        },
      }))))
      releases.push(injectSlot(ctx, 'shell.overlay', () => ctx.slots.register({ name: 'shell.overlay', id: 'cannbot-add-server' }, () => createElement(AddServer, { client,
        close: () => { serverAdded = undefined; publish({ addingServer: false }) }, setSync: (value: boolean) => publish({ syncLogin: value }),
        save: async (entry: ServerEntry, label: string) => {
          desktopBrowser()
          const result = await json('servers', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ ...entry, ...(label && { label }) }) })
          if (typeof result.server?.id !== 'string' || !result.server.id) throw new Error('服务器已保存，但未返回可用标识，请重新打开新增服务器。')
          if (state.syncLogin) loginConsent.add(result.server.id); else loginConsent.delete(result.server.id)
          await pull()
          const onAdded = serverAdded; serverAdded = undefined
          publish({ addingServer: false })
          if (onAdded) {
            onAdded(result.server.id)
            void client.connect(result.server.id).catch(() => {})
            return
          }
          options.onSelectServer?.(result.server.id)
          // open owns progress/errors in the remote main page after this modal closes.
          void client.open({ serverId: result.server.id }).catch(() => {})
        },
      }))))
      releases.push(ctx.layout.panelInfo.subscribe(() => {
        if (ctx.layout.panelInfo.getSnapshot().activePanelId !== PANEL) { ++openSequence; stopGuest() }
        else if (state.status === 'idle' && !state.target && !requestedTarget) {
          // A disconnect can finish while DeepSeek is visible. Leave that page
          // alone; only resolve the now-empty remembered remote panel when the
          // user later returns to it.
          ctx.layout.selectPanel(HOME)
          options.onReturnLocal?.()
        }
      }))
      const tick = async () => { await pull(); if (!disposed) timer = setTimeout(() => { void tick() }, 5000) }
      void tick()
      return () => client.dispose()
    },
    connect(id) {
      if (removing.has(id)) return Promise.reject(new Error('服务器正在删除，请完成后再操作。'))
      if (disconnecting.has(id)) return Promise.reject(new Error('服务器正在断开，请完成后再连接。'))
      const running = connecting.get(id)
      if (running) return running
      const attempt = { controller: new AbortController(), requestId: crypto.randomUUID(), cancelling: false }
      attempts.set(id, attempt)
      const task = streamConnect(id, attempt).finally(() => { connecting.delete(id) })
      connecting.set(id, task)
      return task
    },
    async cancelConnect(id) {
      const attempt = attempts.get(id)
      if (!attempt) return
      attempt.cancelling = true
      try {
        await json('cancel-connect', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ id, requestId: attempt.requestId }) })
        attempt.controller.abort()
        await connecting.get(id)?.catch(() => {})
        ++pullSequence; urls.delete(id)
        publish({ busy: false, error: '', progress: [], servers: state.servers.map(server => server.id === id ? { ...server, connected: false } : server) })
      } catch (error) { attempt.cancelling = false; throw error }
    },
    disconnect(id) {
      if (removing.has(id)) return removing.get(id)!
      const pending = disconnecting.get(id)
      if (pending) return pending
      if (disposed) return Promise.reject(new Error('远程连接组件已关闭。'))
      // Cancel only an open of this server, leaving another server's navigation
      // intact. Invalidate every older inventory poll at both action boundaries.
      if (requestedTarget?.serverId === id || state.target?.serverId === id) ++openSequence
      ++pullSequence
      const task = disconnectServer(id).catch(error => {
        // An existing guest remains usable after a failed disconnect. If this
        // action superseded an unfinished open, expose its normal retry route.
        if (!disposed && !state.target && requestedTarget?.serverId === id && ctx.layout.panelInfo.getSnapshot().activePanelId === PANEL) publish({ status: 'error', error: '断开连接未完成，请重试打开工作台。' })
        throw error
      }).finally(() => {
        disconnecting.delete(id)
        publish({ disconnectingServerIds: [...disconnecting.keys()] })
      })
      disconnecting.set(id, task)
      publish({ disconnectingServerIds: [...disconnecting.keys()] })
      return task
    },
    removeServer(id) {
      const pending = removing.get(id)
      if (pending) return pending
      if (disposed) return Promise.reject(new Error('远程连接组件已关闭。'))
      if (state.orderingServers) return Promise.reject(new Error('服务器顺序正在保存，请稍后重试。'))
      if (requestedTarget?.serverId === id || state.target?.serverId === id) ++openSequence
      ++pullSequence
      const task = (async () => {
        await disconnecting.get(id)
        await disconnectServer(id, true)
      })().catch(error => {
        if (!disposed && !state.target && requestedTarget?.serverId === id && ctx.layout.panelInfo.getSnapshot().activePanelId === PANEL) publish({ status: 'error', error: '删除服务器未完成，请重试打开工作台。' })
        throw error
      }).finally(() => {
        removing.delete(id)
        publish({ removingServerIds: [...removing.keys()] })
      })
      removing.set(id, task)
      publish({ removingServerIds: [...removing.keys()] })
      return task
    },
    async reorderServers(ids) {
      if (disposed) throw new Error('远程连接组件已关闭。')
      if (state.orderingServers || removing.size) throw new Error('服务器列表正在更新，请稍后重试。')
      if (new Set(ids).size !== ids.length || ids.some(id => !state.servers.some(server => server.id === id))) throw new Error('服务器列表已变化，请刷新后重新排序。')
      const previous = state.servers.map(server => server.id)
      if (ids.length === previous.length && ids.every((id, index) => id === previous[index])) return
      ++pullSequence
      publish({ orderingServers: true, servers: inOrder(state.servers, ids) })
      try {
        const result = await json('servers/order', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ ids }) })
        // Reconcile by IDs so a concurrent poll's live status or new server is retained.
        ++pullSequence
        const saved = Array.isArray(result.ids) && result.ids.every((id: unknown) => typeof id === 'string') ? result.ids : ids
        publish({ servers: inOrder(state.servers, saved) })
      } catch (error) {
        ++pullSequence
        publish({ servers: inOrder(state.servers, previous) })
        throw error
      } finally { publish({ orderingServers: false }) }
    },
    async getTree(id) {
      const result = await json('tree?id=' + encodeURIComponent(id))
      if (result.mode !== 'cannbot' || !Array.isArray(result.workspaces) || !Array.isArray(result.sessions)) throw new Error('远端 CANNBot 版本不支持工作区列表，请重新连接以更新插件。')
      return { workspaces: result.workspaces, sessions: result.sessions.map((item: { id?: string; sessionId?: string; title?: string; workspaceId: string; updatedAt?: string; pinned?: boolean; pinOrder?: number; archived?: boolean; ungrouped?: boolean; frozen?: boolean; blank?: boolean; running?: boolean }) => ({
        id: item.sessionId || item.id || '', workspaceId: item.workspaceId, title: item.title || '新会话', updatedAt: item.updatedAt,
        frozen: item.frozen === true, pinned: item.pinned === true, archived: item.archived === true, ungrouped: item.ungrouped === true,
        ...(typeof item.blank === 'boolean' ? { blank: item.blank } : {}), ...(typeof item.running === 'boolean' ? { running: item.running } : {}),
        ...(Number.isSafeInteger(item.pinOrder) && item.pinOrder! >= 0 && { pinOrder: item.pinOrder }),
      })) }
    },
    async operate(id, operation) {
      const target = state.target
      const result = await json('tree?id=' + encodeURIComponent(id), { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(operation) })
      // Updating a row may invalidate the guest's selected page, including its
      // remembered page while DeepSeek is visible. Never steal a newer target.
      const invalidatesTarget = target?.serverId === id && (
        (operation.action === 'remove-workspace' && target.workspaceId === operation.workspaceId)
        || (operation.action === 'archive-session' && target.sessionId === operation.sessionId))
      if (invalidatesTarget && state.target === target) {
        const next: RemoteTarget = { serverId: id, ...(operation.action === 'archive-session' && target.workspaceId ? { workspaceId: target.workspaceId } : {}) }
        requestedTarget = next
        stopGuest()
        publish({ target: next, revision: state.revision + 1, status: 'loading', error: '', notice: '' })
      }
      try {
        let tree: RemoteTree
        try { tree = await client.getTree(id) }
        catch {
          lifetime.signal.throwIfAborted()
          // Retry only the read after a transient tunnel failure, never the write.
          tree = await client.getTree(id)
        }
        return { tree, ...(typeof result.sessionId === 'string' ? { sessionId: result.sessionId } : {}) }
      }
      catch {
        // A committed fork/archive must not be repeated because a read failed.
        throw Object.assign(new Error('操作已完成，但列表刷新失败。请刷新列表查看结果。'), { committed: true })
      }
    },
    async renameServer(id, label) {
      if (removing.has(id)) throw new Error('服务器正在删除，请完成后再操作。')
      const result = await json('servers/label', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ id, label }) })
      if (result.server?.id !== id || typeof result.server?.label !== 'string') throw new Error('备注已保存，请刷新服务器列表确认。')
      // Prevent an older inventory poll from restoring the label after save.
      ++pullSequence
      publish({ servers: state.servers.map(server => server.id === id ? { ...server, label: result.server.label } : server) })
    },
    async open(target) {
      if (removing.has(target.serverId)) throw new Error('服务器正在删除，请完成后再打开。')
      if (disconnecting.has(target.serverId)) throw new Error('服务器正在断开，请完成后再打开。')
      const sequence = ++openSequence
      desktopBrowser()
      requestedTarget = { ...target }
      stopGuest()
      publish({ selectedServerId: target.serverId, target: null, revision: state.revision + 1, status: 'loading', error: '', notice: '' })
      ctx.layout.selectPanel(PANEL)
      try {
        if (!state.servers.find(item => item.id === target.serverId)?.connected) await client.connect(target.serverId)
        if (disposed || sequence !== openSequence) return
        if (!urls.has(target.serverId)) await pull()
        if (disposed || sequence !== openSequence) return
        if (!urls.has(target.serverId)) throw new Error('远端工作台地址不可用，请重新连接。')
      } catch (error) {
        if (!disposed && sequence === openSequence) publish({ status: 'error', error: safeMessage(error instanceof Error ? error.message : '远程连接失败，请重试。') })
        throw error
      }
      publish({ selectedServerId: target.serverId, target: { ...target }, revision: state.revision + 1, status: 'loading', error: '', notice: '' })
      ctx.layout.selectPanel(PANEL)
    },
    returnLocal: back,
    showConnections(onAdded) { serverAdded = onAdded; publish({ addingServer: true }) },
    dispose() {
      if (disposed) return
      // Closing the UI must also release a Host waiting for password input.
      for (const [id, attempt] of attempts) if (connecting.has(id)) {
        void fetch(endpoint('cancel-connect'), { method: 'POST', credentials: 'same-origin', headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ id, requestId: attempt.requestId }), signal: AbortSignal.timeout(20000) }).catch(() => {})
      }
      disposed = true; serverAdded = undefined; ++openSequence; lifetime.abort(); clearTimeout(timer); stopGuest()
      const panel = ctx.layout.panelInfo.getSnapshot().activePanelId
      if (panel === PANEL) ctx.layout.selectPanel(HOME)
      for (const release of releases.reverse()) release()
      urls.clear(); listeners.clear()
    },
  }
  return client
}

function PasswordPrompt({ client, submit }: { client: RemoteClient; submit(serverId: string, challengeId: string, password: string): Promise<void> }) {
  const state = useSyncExternalStore(client.subscribe, client.getSnapshot), challenge = state.passwordRequests?.[0]
  const dialog = useRef<HTMLDialogElement>(null), input = useRef<HTMLInputElement>(null)
  const [password, setPassword] = useState(''), [error, setError] = useState(''), [busy, setBusy] = useState(false)
  useEffect(() => {
    setPassword(''); setError(''); setBusy(false)
    if (challenge) { dialog.current?.showModal(); input.current?.focus() }
  }, [challenge?.challengeId])
  if (!challenge) return null
  const cancel = async () => {
    setPassword(''); setBusy(true)
    try { await client.cancelConnect(challenge.serverId) }
    catch { setError('取消连接未完成，请重试。'); setBusy(false) }
  }
  const save = async () => {
    if (!password || busy) return
    setBusy(true); setError('')
    const answer = password; setPassword('')
    try { await submit(challenge.serverId, challenge.challengeId, answer) }
    catch { setError('密码提交未完成，请重新输入或取消连接。'); setBusy(false) }
  }
  return <dialog ref={dialog} className="cann-add-server" aria-labelledby="cann-password-title" onCancel={event => { event.preventDefault(); if (!busy) void cancel() }}>
    <form onSubmit={event => { event.preventDefault(); void save() }}>
      <header><h2 id="cann-password-title">SSH 密码登录</h2></header>
      <p>{state.servers.find(server => server.id === challenge.serverId)?.label || challenge.serverId}</p>
      <p className="cann-password-identity">{challenge.prompt}</p>
      {challenge.retry && <p role="alert" className="cann-add-error">认证未通过，请重新输入密码。</p>}
      <label className="cann-add-field">密码<input ref={input} type="password" value={password} onChange={event => setPassword(event.target.value)} autoComplete="off" maxLength={1000} disabled={busy} required /></label>
      <p>密码仅用于本次连接，不会保存。</p>
      {error && <p role="alert" className="cann-add-error">{error}</p>}
      <footer><button type="button" onClick={() => { void cancel() }} disabled={busy}>取消连接</button><button type="submit" className="cann-add-submit" disabled={busy || !password}>{busy ? '正在处理…' : '连接'}</button></footer>
    </form>
  </dialog>
}

function RemotePage({ client, attach, reload }: { client: RemoteClient; attach(host: HTMLElement): () => void; reload(): void }) {
  const state = useSyncExternalStore(client.subscribe, client.getSnapshot)
  const host = useRef<HTMLDivElement>(null)
  useEffect(() => { if (host.current) return attach(host.current) }, [attach, state.revision])
  return <main className="cann-remote-page" aria-label="远端 CANNBot 工作台" aria-busy={state.status === 'loading'}>
    {state.error && <div role="alert" className="cann-remote-error">{state.error} <button onClick={reload}>重试</button></div>}
    {state.notice && <div role="status" className="cann-remote-notice">{state.notice}</div>}
    {!state.target && state.progress.length > 0 && <pre role="log">{state.progress.join('\n')}</pre>}
    <div ref={host} className="cann-remote-guest" />
    {state.target && state.status === 'loading' && <div role="status" className="cann-remote-loading">正在加载远端工作台…</div>}
  </main>
}

type ServerEntry = { command: string } | { connection: { hostName: string; user: string; port: string; identityFile: string; proxyJump: string } }
function AddServer({ client, close, setSync, save }: { client: RemoteClient; close(): void; setSync(value: boolean): void; save(entry: ServerEntry, label: string): Promise<void> }) {
  const state = useSyncExternalStore(client.subscribe, client.getSnapshot)
  const dialog = useRef<HTMLDialogElement>(null), input = useRef<HTMLInputElement>(null)
  const [command, setCommand] = useState(''), [label, setLabel] = useState(''), [error, setError] = useState(''), [saving, setSaving] = useState(false)
  const [method, setMethod] = useState<'form' | 'command'>('form')
  const [hostName, setHostName] = useState(''), [user, setUser] = useState(''), [port, setPort] = useState('22'), [identityFile, setIdentityFile] = useState(''), [proxyJump, setProxyJump] = useState('')
  const valid = method === 'form' ? !!hostName.trim() && !!user.trim() && /^\d{1,5}$/.test(port) && +port > 0 && +port <= 65535 : !!command.trim()
  useEffect(() => {
    if (!state.addingServer) return
    setMethod('form'); setHostName(''); setUser(''); setPort('22'); setIdentityFile(''); setProxyJump(''); setCommand(''); setLabel(''); setError(''); setSync(false)
    dialog.current?.showModal(); input.current?.focus()
  }, [state.addingServer])
  const submit = async () => {
    if (!valid || saving || state.busy) return
    setSaving(true); setError('')
    try { await save(method === 'command' ? { command: command.trim() } : { connection: { hostName: hostName.trim(), user: user.trim(), port, identityFile: identityFile.trim(), proxyJump } }, label.trim()) }
    catch (reason) { setError(safeMessage(reason instanceof Error ? reason.message : '无法保存服务器，请重试。')) }
    finally { setSaving(false) }
  }
  if (!state.addingServer) return null
  return <dialog ref={dialog} className="cann-add-server" aria-labelledby="cann-add-server-title" onCancel={event => { event.preventDefault(); if (!saving) close() }}>
    <form onSubmit={event => { event.preventDefault(); void submit() }}>
      <header><h2 id="cann-add-server-title">新增 SSH 服务器</h2><button className="cann-add-close" type="button" aria-label="关闭新增服务器" disabled={saving} onClick={close}>×</button></header>
      <div role="tablist" aria-label="添加服务器方式" className="cann-server-tabs"><button type="button" role="tab" aria-selected={method === 'form'} onClick={() => setMethod('form')} disabled={saving}>填写连接信息</button><button type="button" role="tab" aria-selected={method === 'command'} onClick={() => setMethod('command')} disabled={saving}>SSH 命令 / 已有配置</button></div>
      {method === 'form' ? <>
        <label className="cann-add-field">服务器地址<input ref={input} value={hostName} onChange={event => setHostName(event.target.value)} placeholder="192.168.1.10 或服务器域名" autoComplete="off" required disabled={saving} /></label>
        <label className="cann-add-field">用户名<input value={user} onChange={event => setUser(event.target.value)} autoComplete="off" required disabled={saving} /></label>
        <label className="cann-add-field">端口<input type="number" min="1" max="65535" value={port} onChange={event => setPort(event.target.value)} required disabled={saving} /></label>
        <details><summary>高级选项</summary><label className="cann-add-field">私钥路径（可选）<input value={identityFile} onChange={event => setIdentityFile(event.target.value)} placeholder="~/.ssh/id_ed25519" disabled={saving} /></label>
        <label className="cann-add-field">跳板机<select value={proxyJump} onChange={event => setProxyJump(event.target.value)} disabled={saving}><option value="">不使用跳板机</option>{state.servers.map(server => <option key={server.id} value={server.alias}>{server.label}</option>)}</select></label></details>
      </> : <>
      <label className="cann-add-field">SSH 命令或别名<input ref={input} value={command} onChange={event => setCommand(event.target.value)} placeholder="ssh user@192.168.1.10 -p 22" list="cann-ssh-aliases" autoComplete="off" spellCheck={false} maxLength={4096} disabled={saving} required /></label>
      <datalist id="cann-ssh-aliases">{state.servers.map(server => <option key={server.id} value={server.alias}>{server.label}</option>)}</datalist>
      </>}
      <label className="cann-add-field">备注（可选）<input value={label} onChange={event => setLabel(event.target.value)} placeholder="例如：开发服务器" maxLength={80} disabled={saving} /></label>
      <label className="cann-add-sync"><input type="checkbox" checked={state.syncLogin} disabled={saving || state.busy} onChange={event => setSync(event.target.checked)} />将本机模型账号授权同步至此服务器</label>
      {state.syncLogin && <p>授权凭据将保存在此服务器，服务器管理员可能访问并使用该授权。请仅向可信服务器同步；断开连接不会删除远端授权，可在远端账号设置中退出或由模型服务商撤销。</p>}
      {error && <p role="alert" className="cann-add-error">{error}</p>}
      {state.busy && <p role="status">另一台服务器正在连接，请稍后保存。</p>}
      <footer><button type="button" onClick={close} disabled={saving}>取消</button><button className="cann-add-submit" type="submit" disabled={saving || state.busy || !valid}>{saving ? '正在保存…' : '保存并连接'}</button></footer>
    </form>
  </dialog>
}
