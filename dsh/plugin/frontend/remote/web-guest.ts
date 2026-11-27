// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { readEmbeddedEvent } from '../embedded-navigation.ts'
import type { GuestState } from './native-guest.mjs'

export function requireLocalWeb() {
  if (!['localhost', '127.0.0.1', '[::1]'].includes(location.hostname) || location.protocol !== 'http:') throw new Error('请通过本机回环地址打开 DSH Web，或使用桌面客户端连接服务器。')
}

export function createWebGuest(options: {
  host: HTMLElement
  serverId: string
  fragment: URLSearchParams
  onState(state: GuestState): void
  onLocation(target: { workspaceId?: string; sessionId?: string }): void
  onCreateWorkspace(): void
}) {
  requireLocalWeb()
  let disposed = false, view: string | undefined, origin: string | undefined
  let frame: HTMLIFrameElement | undefined, timer: ReturnType<typeof setTimeout> | undefined
  const endpoint = new URL('api/cannbot-remote/web-guest', document.baseURI)
  const post = (data: object) => fetch(endpoint, { method: 'POST', credentials: 'same-origin', cache: 'no-store', headers: { 'content-type': 'application/json' }, body: JSON.stringify(data), signal: AbortSignal.timeout(20000) })
  const close = async () => { const id = view; view = undefined; if (id) await post({ close: id }).catch(() => {}) }
  const fail = () => { if (!disposed) options.onState({ status: 'error', error: '无法加载远端工作台，请使用支持分区 Cookie 的本机浏览器并重试。' }) }
  const receive = (event: MessageEvent) => {
    if (disposed || !frame || event.source !== frame.contentWindow || event.origin !== origin) return
    const message = readEmbeddedEvent(event.data)
    if (!message) return
    clearTimeout(timer)
    options.onState({ status: 'ready', error: '' })
    if (message.event === 'location') options.onLocation(message.target)
    if (message.event === 'create') options.onCreateWorkspace()
  }
  window.addEventListener('message', receive)
  const opening = (async () => {
    try {
      const reply = await post({ id: options.serverId, parentOrigin: location.origin })
      if (!reply.ok) throw new Error()
      const result = await reply.json()
      if (typeof result.view !== 'string' || !/^[0-9a-f-]{36}$/.test(result.view)) throw new Error()
      view = result.view
      if (disposed) { await close(); return }
      const url = new URL(result.url)
      if (url.protocol !== 'http:' || url.hostname !== 'cannbot-' + view + '.localhost' || !url.port || url.username || url.password || url.pathname !== '/' || !url.searchParams.get('ticket')) throw new Error()
      origin = url.origin
      const fragment = new URLSearchParams(options.fragment)
      fragment.set('cannParentOrigin', location.origin); url.hash = fragment.toString()
      frame = document.createElement('iframe'); frame.title = '远端 CANNBot 工作台'
      frame.sandbox.add('allow-scripts', 'allow-same-origin', 'allow-forms', 'allow-downloads')
      frame.referrerPolicy = 'no-referrer'
      Object.assign(frame.style, { width: '100%', height: '100%', border: '0', display: 'block' })
      frame.src = url.href; options.host.append(frame)
      timer = setTimeout(fail, 45000)
    } catch { await close(); fail() }
  })()
  return {
    reload: () => false,
    async dispose() {
      disposed = true; clearTimeout(timer); window.removeEventListener('message', receive); frame?.remove()
      await opening; await close()
    },
  }
}
