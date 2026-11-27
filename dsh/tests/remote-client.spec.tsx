// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Context } from '@deepseek-ai/cordis'
import { createRemoteClient } from '../plugin/frontend/remote/index.tsx'

const native = vi.hoisted(() => ({ create: vi.fn(), dispose: vi.fn(), reload: vi.fn() }))
vi.mock('../plugin/frontend/remote/native-guest.mjs', async original => ({
  ...await original<object>(),
  createNativeGuest: native.create,
}))
const clients: ReturnType<typeof createRemoteClient>[] = []
Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value() { this.setAttribute('open', '') } })
afterEach(() => { cleanup(); clients.splice(0).forEach(client => client.dispose()); vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks(); native.create.mockReset(); native.dispose.mockReset(); native.reload.mockReset() })
function fixture(connected = true) {
  const slots = new Map<string, () => React.ReactNode>(), listeners = new Set<() => void>()
  let activePanelId: string | null = null
  const selectPanel = vi.fn((panel: string | null) => { activePanelId = panel; for (const listener of listeners) listener() })
  const ctx = {
    slots: { register: vi.fn((spec, render) => { const key = spec.key || spec.id; slots.set(key, render); return () => slots.delete(key) }) },
    layout: { selectPanel, panelInfo: { getSnapshot: () => ({ activePanelId }), subscribe: (listener: () => void) => { listeners.add(listener); return () => listeners.delete(listener) } } },
  } as unknown as Context
  Object.defineProperty(window, 'dshDesktop', { configurable: true, value: { protocolVersion: 1, browser: { acquire: vi.fn(), release: vi.fn() } } })
  const server = { id: 'dev', alias: 'DevEnv950', label: 'DevEnv950', connected, url: 'http://127.0.0.1:17633/?token=private' }
  const fetcher = vi.fn(async (address: URL, _init?: RequestInit) => {
    if (address.pathname.endsWith('/servers')) return new Response(JSON.stringify({ servers: [server] }))
    if (address.pathname.endsWith('/tree')) return new Response(JSON.stringify({ mode: 'cannbot', workspaces: [], sessions: [{ sessionId: 'C1', workspaceId: 'W1', title: '远程对话' }] }))
    throw new Error('unexpected route')
  })
  vi.stubGlobal('fetch', fetcher)
  native.create.mockImplementation(() => ({ dispose: native.dispose, reload: native.reload }))
  const onReturnLocal = vi.fn(), onSelectServer = vi.fn(), onCreateWorkspace = vi.fn(), client = createRemoteClient(ctx, { onReturnLocal, onSelectServer, onCreateWorkspace }); clients.push(client); client.start()
  return { client, slots, selectPanel, fetcher, server, onReturnLocal, onSelectServer, onCreateWorkspace }
}

describe('embedded remote navigation', () => {
  it('shows an SSH password dialog, sends the answer only in POST and clears it before retry', async () => {
    const f = fixture(false); await waitFor(() => expect(f.client.getSnapshot().servers).toHaveLength(1))
    let stream!: ReadableStreamDefaultController<Uint8Array>, submitted: Record<string, string> | undefined
    const send = (event: object) => stream.enqueue(new TextEncoder().encode('data: ' + JSON.stringify(event) + '\n\n'))
    f.fetcher.mockImplementation(async (address, init) => {
      if (address.pathname.endsWith('/connect-stream')) return new Response(new ReadableStream({ start(controller) { stream = controller } }))
      if (address.pathname.endsWith('/password')) { submitted = JSON.parse(String(init?.body)); return Response.json({ ok: true }) }
      return Response.json({ servers: [f.server] })
    })
    render(f.slots.get('cannbot-ssh-password')!())
    let connection!: Promise<void>
    act(() => { connection = f.client.connect('dev') })
    await act(async () => { send({ phase: 'password', challengeId: 'first', prompt: "user@host's password: " }) })
    const input = screen.getByLabelText('密码')
    expect(input.getAttribute('type')).toBe('password')
    fireEvent.change(input, { target: { value: 'fixture-secret' } })
    fireEvent.click(screen.getByRole('button', { name: '连接', exact: true }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(submitted).toMatchObject({ id: 'dev', challengeId: 'first', password: 'fixture-secret' })
    expect(submitted?.requestId).toHaveLength(36)
    expect(JSON.stringify(f.client.getSnapshot())).not.toContain('fixture-secret')
    expect(f.fetcher.mock.calls.every(([url]) => !url.href.includes('fixture-secret'))).toBe(true)
    await act(async () => { send({ phase: 'password', challengeId: 'retry', prompt: "user@host's password: ", retry: true }) })
    expect((screen.getByLabelText('密码') as HTMLInputElement).value).toBe('')
    expect(screen.getByRole('alert').textContent).toContain('认证未通过')
    await act(async () => { send({ phase: 'done', ok: true, url: f.server.url }); stream.close(); await connection })
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('cancels the exact in-flight attempt without surfacing an aborted stream error', async () => {
    const f = fixture(false); await waitFor(() => expect(f.client.getSnapshot().servers).toHaveLength(1))
    let requestId = '', cancelBody: unknown
    f.fetcher.mockImplementation(async (address, init) => {
      if (address.pathname.endsWith('/connect-stream')) {
        requestId = address.searchParams.get('requestId')!
        return new Promise((_resolve, reject) => init?.signal?.addEventListener('abort', () => reject(new Error('aborted')), { once: true }))
      }
      if (address.pathname.endsWith('/cancel-connect')) { cancelBody = JSON.parse(String(init?.body)); return Response.json({ ok: true }) }
      return Response.json({ servers: [f.server] })
    })
    const task = f.client.connect('dev').catch(() => {})
    await f.client.cancelConnect('dev'); await task
    expect(cancelBody).toEqual({ id: 'dev', requestId }); expect(requestId).toHaveLength(36)
    expect(f.client.getSnapshot()).toMatchObject({ busy: false, error: '', progress: [] })
    expect(f.client.getSnapshot().servers[0].connected).toBe(false)
  })
  it('removes a displayed server once, blocks reopening while pending and clears its guest target', async () => {
    const f = fixture(); await waitFor(() => expect(f.client.getSnapshot().servers).toHaveLength(1))
    await f.client.open({ serverId: 'dev', workspaceId: 'W1' }); render(f.slots.get('cannbot-remote-workbench')!())
    await waitFor(() => expect(native.create).toHaveBeenCalledOnce())
    let finish!: (response: Response) => void
    f.fetcher.mockImplementation(async (address, init) => {
      expect(address.pathname).toBe('/api/cannbot-remote/servers/remove')
      expect(JSON.parse(String(init?.body))).toEqual({ id: 'dev' })
      return new Promise(resolve => { finish = resolve })
    })
    let first!: Promise<void>
    act(() => { first = f.client.removeServer('dev') })
    expect(f.client.removeServer('dev')).toBe(first)
    expect(f.client.getSnapshot().removingServerIds).toEqual(['dev'])
    await expect(f.client.open({ serverId: 'dev' })).rejects.toThrow('正在删除')
    await expect(f.client.connect('dev')).rejects.toThrow('正在删除')
    await act(async () => { await Promise.resolve(); finish(Response.json({ ok: true, id: 'dev', stopped: true })); await first })
    expect(f.client.getSnapshot()).toMatchObject({ servers: [], target: null, removingServerIds: [], status: 'idle' })
    expect(native.dispose).toHaveBeenCalled(); expect(f.onReturnLocal).toHaveBeenCalledOnce()
    expect(f.selectPanel).toHaveBeenLastCalledWith('cannbot-dsh-workbench')
    expect(f.fetcher.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(1)
  })
  it('keeps a server on failed removal and never steals DeepSeek focus when a retry succeeds', async () => {
    const f = fixture(); await waitFor(() => expect(f.client.getSnapshot().servers).toHaveLength(1))
    await f.client.open({ serverId: 'dev' }); f.selectPanel(null)
    f.fetcher.mockImplementation(async () => Response.json({ ok: false, message: '请重试' }, { status: 409 }))
    await expect(f.client.removeServer('dev')).rejects.toThrow('请重试')
    expect(f.client.getSnapshot().servers[0].connected).toBe(true)
    expect(f.client.getSnapshot().target?.serverId).toBe('dev')
    f.fetcher.mockImplementation(async () => Response.json({ ok: true, id: 'dev' }))
    await f.client.removeServer('dev')
    expect(f.client.getSnapshot().servers).toEqual([])
    expect(f.client.getSnapshot().target).toBeNull()
    expect(f.selectPanel).toHaveBeenLastCalledWith(null); expect(f.onReturnLocal).not.toHaveBeenCalled()
  })
  it('ignores an inventory poll started before removal succeeds', async () => {
    vi.useFakeTimers(); const f = fixture(); await vi.advanceTimersByTimeAsync(0)
    let finish!: (response: Response) => void
    f.fetcher.mockImplementation(async (_address, init) => init?.method === 'POST' ? Response.json({ ok: true, id: 'dev' }) : new Promise(resolve => { finish = resolve }))
    await vi.advanceTimersByTimeAsync(5000)
    await f.client.removeServer('dev')
    finish(Response.json({ servers: [f.server] })); await Promise.resolve(); await Promise.resolve()
    expect(f.client.getSnapshot().servers).toEqual([])
  })
  it('persists an optimistic order without losing polling updates and rolls back IDs on failure', async () => {
    vi.useFakeTimers()
    const f = fixture()
    await vi.advanceTimersByTimeAsync(0)
    const second = { ...f.server, id: 'two', alias: 'two', label: 'two' }
    const third = { ...f.server, id: 'three', alias: 'three', label: 'three' }
    let inventory = [f.server, second, third]
    let finish!: (response: Response) => void
    f.fetcher.mockImplementation(async (address, init) => {
      if (init?.method === 'POST') {
        expect(address.pathname).toBe('/api/cannbot-remote/servers/order')
        return new Promise(resolve => { finish = resolve })
      }
      return Response.json({ servers: inventory })
    })
    await vi.advanceTimersByTimeAsync(5000)
    const pending = f.client.reorderServers(['three', 'dev', 'two'])
    expect(f.client.getSnapshot().servers.map(server => server.id)).toEqual(['three', 'dev', 'two'])
    inventory = [{ ...f.server, connected: false }, second, third]
    await vi.advanceTimersByTimeAsync(5000)
    expect(f.client.getSnapshot().servers.map(server => server.id)).toEqual(['three', 'dev', 'two'])
    expect(f.client.getSnapshot().servers[1].connected).toBe(false)
    finish(Response.json({ ok: true, ids: ['three', 'dev', 'two'] })); await pending
    expect(f.client.getSnapshot().orderingServers).toBe(false)
    const failed = f.client.reorderServers(['two', 'dev', 'three'])
    const rejection = expect(failed).rejects.toThrow('无法保存')
    finish(Response.json({ ok: false, message: '无法保存' }, { status: 409 })); await rejection
    expect(f.client.getSnapshot().servers.map(server => server.id)).toEqual(['three', 'dev', 'two'])
    expect(f.client.getSnapshot().servers[1].connected).toBe(false)
    expect(f.client.getSnapshot().orderingServers).toBe(false)
    expect(f.fetcher.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(2)
    expect(f.selectPanel).not.toHaveBeenCalled()
  })
  it('keeps tunnel URLs private, opens an in-app guest with explicit CANN scope, and returns without disconnecting', async () => {
    const f = fixture(); await waitFor(() => expect(f.client.getSnapshot().servers).toHaveLength(1))
    expect(JSON.stringify(f.client.getSnapshot())).not.toContain('private')
    await f.client.open({ serverId: 'dev', workspaceId: 'W1', sessionId: 'C1' })
    render(f.slots.get('cannbot-remote-workbench')!())
    await waitFor(() => expect(native.create).toHaveBeenCalledOnce())
    const request = native.create.mock.calls[0][0], url = new URL(request.url)
    expect(url.origin).toBe('http://127.0.0.1:17633')
    expect(new URLSearchParams(url.hash.slice(1)).get('cannSession')).toBe('C1')
    expect(new URLSearchParams(url.hash.slice(1)).get('cannEmbed')).toBe('1')
    expect(document.querySelector('.cann-remote-page footer')).toBeNull()
    expect(screen.queryByText('返回本地')).toBeNull()
    expect(document.querySelector('.cann-remote-guest')).not.toBeNull()
    act(() => f.client.returnLocal())
    expect(f.onReturnLocal).toHaveBeenCalledOnce(); expect(native.dispose).toHaveBeenCalled()
    expect(f.selectPanel).toHaveBeenLastCalledWith('cannbot-dsh-workbench')
    expect(f.fetcher.mock.calls.some(([address]) => address.pathname.endsWith('/disconnect'))).toBe(false)
    expect(f.client.getSnapshot().servers[0].connected).toBe(true)
  })
  it('does not steal the page after returning locally during an unfinished SSH connection', async () => {
    const f = fixture(false); await waitFor(() => expect(f.client.getSnapshot().servers).toHaveLength(1))
    let finish!: (response: Response) => void
    f.fetcher.mockImplementation(async address => {
      if (address.pathname.endsWith('/connect-stream')) return new Promise(resolve => { finish = resolve })
      return new Response(JSON.stringify({ servers: [{ ...f.server, connected: true }] }))
    })
    const opening = f.client.open({ serverId: 'dev' })
    await waitFor(() => expect(finish).toBeTypeOf('function'))
    f.client.returnLocal()
    finish(new Response('data: ' + JSON.stringify({ phase: 'done', ok: true, url: f.server.url }) + '\n\n'))
    await opening
    expect(f.selectPanel).toHaveBeenLastCalledWith('cannbot-dsh-workbench')
    expect(f.client.getSnapshot().target).toBe(null)
    expect(native.create).not.toHaveBeenCalled()
  })
  it('disconnects the displayed server through the existing tunnel-only endpoint and returns locally', async () => {
    const f = fixture(); await waitFor(() => expect(f.client.getSnapshot().servers).toHaveLength(1))
    await f.client.open({ serverId: 'dev', workspaceId: 'W1', sessionId: 'C1' })
    render(f.slots.get('cannbot-remote-workbench')!())
    await waitFor(() => expect(native.create).toHaveBeenCalledOnce())
    const staleGuest = native.create.mock.calls[0][0]
    f.fetcher.mockImplementation(async (address, init) => {
      expect(address.pathname).toBe('/api/cannbot-remote/disconnect')
      expect(init?.method).toBe('POST'); expect(JSON.parse(String(init?.body))).toEqual({ id: 'dev' })
      return Response.json({ ok: true, stopped: true })
    })
    await act(() => f.client.disconnect('dev'))
    expect(native.dispose).toHaveBeenCalled()
    expect(f.client.getSnapshot()).toMatchObject({ target: null, status: 'idle', disconnectingServerIds: [], servers: [{ id: 'dev', connected: false }] })
    expect(f.client.getSnapshot().selectedServerId).toBeUndefined()
    expect(f.selectPanel).toHaveBeenLastCalledWith('cannbot-dsh-workbench'); expect(f.onReturnLocal).toHaveBeenCalledOnce()
    act(() => staleGuest.onLocation({ workspaceId: 'STALE', sessionId: 'STALE' }))
    expect(f.client.getSnapshot().target).toBeNull()
    expect(f.fetcher.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(1)
    expect(f.fetcher.mock.calls.some(([address]) => /stop|shutdown|delete/.test(address.pathname))).toBe(false)
  })
  it('disconnecting another server or a remembered local/DeepSeek target never steals the current page', async () => {
    const f = fixture(); await waitFor(() => expect(f.client.getSnapshot().servers).toHaveLength(1))
    await f.client.open({ serverId: 'dev', workspaceId: 'W1', sessionId: 'C1' })
    render(f.slots.get('cannbot-remote-workbench')!())
    await waitFor(() => expect(native.create).toHaveBeenCalledOnce())
    f.fetcher.mockImplementation(async () => Response.json({ ok: true, stopped: true }))
    const target = f.client.getSnapshot().target, selections = f.selectPanel.mock.calls.length
    await act(() => f.client.disconnect('other'))
    expect(f.client.getSnapshot().target).toBe(target); expect(native.dispose).not.toHaveBeenCalled()
    expect(f.selectPanel).toHaveBeenCalledTimes(selections); expect(f.onReturnLocal).not.toHaveBeenCalled()
    act(() => f.selectPanel(null))
    const afterDeepSeek = f.selectPanel.mock.calls.length
    await act(() => f.client.disconnect('dev'))
    expect(f.selectPanel).toHaveBeenCalledTimes(afterDeepSeek); expect(f.onReturnLocal).not.toHaveBeenCalled()
    expect(f.client.getSnapshot().target).toBeNull()
    expect(f.client.getSnapshot().servers[0].connected).toBe(false)
    act(() => f.selectPanel('cannbot-remote-workbench'))
    expect(f.selectPanel).toHaveBeenLastCalledWith('cannbot-dsh-workbench')
    expect(f.onReturnLocal).toHaveBeenCalledOnce()
  })
  it('deduplicates disconnect clicks and preserves a guest and connection when the endpoint fails', async () => {
    const f = fixture(); await waitFor(() => expect(f.client.getSnapshot().servers).toHaveLength(1))
    await f.client.open({ serverId: 'dev' }); render(f.slots.get('cannbot-remote-workbench')!())
    await waitFor(() => expect(native.create).toHaveBeenCalledOnce())
    let finish!: (response: Response) => void
    f.fetcher.mockImplementation(async () => new Promise(resolve => { finish = resolve }))
    const first = f.client.disconnect('dev'), duplicate = f.client.disconnect('dev')
    expect(duplicate).toBe(first); expect(f.client.getSnapshot().disconnectingServerIds).toEqual(['dev'])
    const rejection = expect(first).rejects.toThrow('无法断开')
    await waitFor(() => expect(finish).toBeTypeOf('function'))
    finish(Response.json({ ok: false, error: '无法断开，请重试。' }, { status: 500 })); await rejection
    expect(f.client.getSnapshot()).toMatchObject({ target: { serverId: 'dev' }, servers: [{ connected: true }], disconnectingServerIds: [] })
    expect(native.dispose).not.toHaveBeenCalled(); expect(f.onReturnLocal).not.toHaveBeenCalled()
    expect(f.fetcher.mock.calls.filter(([address]) => address.pathname.endsWith('/disconnect'))).toHaveLength(1)
    f.fetcher.mockResolvedValue(Response.json({ ok: true, stopped: true }))
    await act(() => f.client.disconnect('dev'))
    expect(f.client.getSnapshot().servers[0].connected).toBe(false)
    expect(f.onReturnLocal).toHaveBeenCalledOnce()
  })
  it('ignores an inventory response that began before disconnect committed', async () => {
    vi.useFakeTimers()
    const f = fixture(); await vi.advanceTimersByTimeAsync(0)
    expect(f.client.getSnapshot().servers).toHaveLength(1)
    let finishPoll!: (response: Response) => void
    f.fetcher.mockImplementation(async address => address.pathname.endsWith('/servers')
      ? new Promise(resolve => { finishPoll = resolve }) : Response.json({ ok: true, stopped: true }))
    await vi.advanceTimersByTimeAsync(5000)
    expect(finishPoll).toBeTypeOf('function')
    await f.client.disconnect('dev')
    finishPoll(Response.json({ servers: [f.server] })); await vi.advanceTimersByTimeAsync(0)
    expect(f.client.getSnapshot().servers[0].connected).toBe(false)
    expect(f.client.getSnapshot().target).toBeNull()
  })
  it('waits for an existing connect then disconnects once so its late completion cannot reopen the guest', async () => {
    const f = fixture(false); await waitFor(() => expect(f.client.getSnapshot().servers).toHaveLength(1))
    let finishConnect!: (response: Response) => void
    f.fetcher.mockImplementation(async address => {
      if (address.pathname.endsWith('/connect-stream')) return new Promise(resolve => { finishConnect = resolve })
      if (address.pathname.endsWith('/disconnect')) return Response.json({ ok: true, stopped: true })
      return Response.json({ servers: [{ ...f.server, connected: true }] })
    })
    const opening = f.client.open({ serverId: 'dev', workspaceId: 'W1' })
    await waitFor(() => expect(finishConnect).toBeTypeOf('function'))
    const disconnect = f.client.disconnect('dev')
    await expect(f.client.open({ serverId: 'dev' })).rejects.toThrow('正在断开')
    await expect(f.client.connect('dev')).rejects.toThrow('正在断开')
    expect(f.fetcher.mock.calls.some(([address]) => address.pathname.endsWith('/disconnect'))).toBe(false)
    finishConnect(new Response('data: ' + JSON.stringify({ phase: 'done', ok: true, url: f.server.url }) + '\n\n'))
    await Promise.all([opening, disconnect])
    expect(f.fetcher.mock.calls.filter(([address]) => address.pathname.endsWith('/disconnect'))).toHaveLength(1)
    expect(f.client.getSnapshot()).toMatchObject({ target: null, status: 'idle', servers: [{ connected: false }], disconnectingServerIds: [] })
    expect(f.selectPanel).toHaveBeenLastCalledWith('cannbot-dsh-workbench')
    expect(native.create).not.toHaveBeenCalled()
  })
  it('does not leave a newer server when an older disconnect finishes late', async () => {
    const f = fixture(); await waitFor(() => expect(f.client.getSnapshot().servers).toHaveLength(1))
    await f.client.open({ serverId: 'dev' })
    let finishDisconnect!: (response: Response) => void
    const other = { ...f.server, id: 'other', alias: 'Other', url: 'http://127.0.0.1:17634/?token=other-private' }
    f.fetcher.mockImplementation(async address => {
      if (address.pathname.endsWith('/disconnect')) return new Promise(resolve => { finishDisconnect = resolve })
      if (address.pathname.endsWith('/connect-stream')) return new Response('data: ' + JSON.stringify({ phase: 'done', ok: true, url: other.url }) + '\n\n')
      return Response.json({ servers: [f.server, other] })
    })
    const disconnect = f.client.disconnect('dev'); await waitFor(() => expect(finishDisconnect).toBeTypeOf('function'))
    await f.client.open({ serverId: 'other', workspaceId: 'OTHER' })
    finishDisconnect(Response.json({ ok: true, stopped: true })); await disconnect
    expect(f.client.getSnapshot().target).toEqual({ serverId: 'other', workspaceId: 'OTHER' })
    expect(f.client.getSnapshot().servers.find(server => server.id === 'other')?.connected).toBe(true)
    expect(f.selectPanel).toHaveBeenLastCalledWith('cannbot-remote-workbench'); expect(f.onReturnLocal).not.toHaveBeenCalled()
  })
  it('reconnects explicitly with a fresh private URL after disconnecting', async () => {
    const f = fixture(); await waitFor(() => expect(f.client.getSnapshot().servers).toHaveLength(1))
    await f.client.open({ serverId: 'dev' })
    f.fetcher.mockResolvedValue(Response.json({ ok: true, stopped: true })); await f.client.disconnect('dev')
    const fresh = 'http://127.0.0.1:17635/?token=fresh-private'
    f.fetcher.mockImplementation(async address => address.pathname.endsWith('/connect-stream')
      ? new Response('data: ' + JSON.stringify({ phase: 'done', ok: true, url: fresh }) + '\n\n')
      : Response.json({ servers: [{ ...f.server, connected: true, url: fresh }] }))
    await f.client.open({ serverId: 'dev' }); render(f.slots.get('cannbot-remote-workbench')!())
    await waitFor(() => expect(native.create).toHaveBeenCalledOnce())
    expect(new URL(native.create.mock.calls[0][0].url).searchParams.get('token')).toBe('fresh-private')
    expect(f.fetcher.mock.calls.filter(([address]) => address.pathname.endsWith('/connect-stream'))).toHaveLength(1)
    expect(JSON.stringify(f.client.getSnapshot())).not.toContain('private')
  })
  it('deduplicates concurrent connect calls and defaults to login synchronization', async () => {
    const f = fixture(false); await waitFor(() => expect(f.client.getSnapshot().servers).toHaveLength(1))
    f.fetcher.mockImplementation(async address => address.pathname.endsWith('/connect-stream')
      ? new Response('data: ' + JSON.stringify({ phase: 'done', ok: true, url: f.server.url }) + '\n\n')
      : new Response(JSON.stringify({ servers: [{ ...f.server, connected: true }] })))
    await Promise.all([f.client.connect('dev'), f.client.connect('dev')])
    const calls = f.fetcher.mock.calls.filter(([address]) => address.pathname.endsWith('/connect-stream'))
    expect(calls).toHaveLength(1); expect(calls[0][0].searchParams.get('syncLogin')).toBe('0')
  })
  it('does not reopen an old remote page after switching to the DeepSeek main page during connection', async () => {
    const f = fixture(false); await waitFor(() => expect(f.client.getSnapshot().servers).toHaveLength(1))
    let finish!: (response: Response) => void
    f.fetcher.mockImplementation(async address => address.pathname.endsWith('/connect-stream')
      ? new Promise(resolve => { finish = resolve })
      : new Response(JSON.stringify({ servers: [{ ...f.server, connected: true }] })))
    const opening = f.client.open({ serverId: 'dev' }); await waitFor(() => expect(finish).toBeTypeOf('function'))
    f.selectPanel(null)
    finish(new Response('data: ' + JSON.stringify({ phase: 'done', ok: true, url: f.server.url }) + '\n\n'))
    await opening
    expect(f.selectPanel).toHaveBeenLastCalledWith(null)
    expect(f.client.getSnapshot().target).toBe(null)
  })
  it('maps the server membership response and rejects a version without CANN workspace ownership', async () => {
    const f = fixture(); expect((await f.client.getTree('dev')).sessions[0]).toMatchObject({ id: 'C1', workspaceId: 'W1' })
    f.fetcher.mockResolvedValue(new Response(JSON.stringify({ workspaces: [], sessions: [] })))
    await expect(f.client.getTree('dev')).rejects.toThrow('版本不支持')
  })
  it('preserves native archive/pin flags and orphaned CANN sessions from the server', async () => {
    const f = fixture(); await waitFor(() => expect(f.client.getSnapshot().servers).toHaveLength(1))
    f.fetcher.mockResolvedValue(new Response(JSON.stringify({ mode: 'cannbot', workspaces: [], sessions: [
      { sessionId: 'archived', workspaceId: 'removed', archived: true, pinned: false, ungrouped: true },
      { sessionId: 'pinned', workspaceId: 'W1', pinned: true, pinOrder: 0 },
    ] })))
    expect((await f.client.getTree('dev')).sessions).toEqual([
      expect.objectContaining({ id: 'archived', archived: true, pinned: false, ungrouped: true }),
      expect.objectContaining({ id: 'pinned', archived: false, pinned: true, pinOrder: 0 }),
    ])
  })
  it('preserves native blank/running/activity facts without guessing absent or malformed status', async () => {
    const f = fixture(); await waitFor(() => expect(f.client.getSnapshot().servers).toHaveLength(1))
    f.fetcher.mockResolvedValue(new Response(JSON.stringify({ mode: 'cannbot', workspaces: [], sessions: [
      { sessionId: 'blank', workspaceId: 'W1', blank: true, running: false, updatedAt: '2026-11-13T03:00:00.000Z' },
      { sessionId: 'busy', workspaceId: 'W1', blank: false, running: true },
      { sessionId: 'unknown', workspaceId: 'W1' },
      { sessionId: 'malformed', workspaceId: 'W1', blank: 'true', running: 1 },
    ] })))
    const { sessions } = await f.client.getTree('dev')
    expect(sessions[0]).toMatchObject({ blank: true, running: false, updatedAt: '2026-11-13T03:00:00.000Z' })
    expect(sessions[1]).toMatchObject({ blank: false, running: true })
    for (const item of sessions.slice(2)) { expect(item).not.toHaveProperty('blank'); expect(item).not.toHaveProperty('running') }
  })
  it('edits a disconnected server label without connecting or exposing its URL', async () => {
    const f = fixture(false); await waitFor(() => expect(f.client.getSnapshot().servers).toHaveLength(1))
    f.fetcher.mockImplementation(async (_address, init) => {
      const body = JSON.parse(String(init?.body))
      return new Response(JSON.stringify({ ok: true, server: { ...f.server, label: body.label || f.server.alias } }))
    })
    await f.client.renameServer('dev', '开发环境')
    expect(f.client.getSnapshot().servers[0]).toMatchObject({ label: '开发环境', alias: 'DevEnv950', connected: false })
    expect(f.fetcher.mock.calls.at(-1)?.[0].pathname).toBe('/api/cannbot-remote/servers/label')
    expect(JSON.stringify(f.client.getSnapshot())).not.toContain('private')
    await f.client.renameServer('dev', '')
    expect(f.client.getSnapshot().servers[0].label).toBe('DevEnv950')
    expect(f.selectPanel).not.toHaveBeenCalled()
  })
  it('keeps a running-session archive refusal inspectable without retrying or changing its page', async () => {
    const f = fixture(); await waitFor(() => expect(f.client.getSnapshot().servers).toHaveLength(1))
    await f.client.open({ serverId: 'dev', workspaceId: 'W1', sessionId: 'C1' })
    f.fetcher.mockResolvedValue(new Response(JSON.stringify({ error: 'workspace/session-active', message: '会话仍在运行。', activity: [{ kind: 'agent', items: [{ id: 'task-1', label: '正在执行任务' }] }] }), { status: 409 }))
    await expect(f.client.operate('dev', { action: 'archive-session', sessionId: 'C1' })).rejects.toMatchObject({ code: 'workspace/session-active', activity: [{ kind: 'agent', items: [{ id: 'task-1', label: '正在执行任务' }] }] })
    expect(f.client.getSnapshot().target?.sessionId).toBe('C1')
    expect(f.fetcher.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(1)
  })
  it('clears the remembered archived session without stealing the DeepSeek page', async () => {
    const f = fixture(); await waitFor(() => expect(f.client.getSnapshot().servers).toHaveLength(1))
    await f.client.open({ serverId: 'dev', workspaceId: 'W1', sessionId: 'C1' })
    f.selectPanel(null)
    f.fetcher.mockImplementation(async (_address, init) => new Response(JSON.stringify(init?.method === 'POST' ? { ok: true } : { mode: 'cannbot', workspaces: [], sessions: [] })))
    await f.client.operate('dev', { action: 'archive-session', sessionId: 'C1' })
    expect(f.client.getSnapshot().target).toEqual({ serverId: 'dev', workspaceId: 'W1' })
    expect(f.selectPanel).toHaveBeenLastCalledWith(null)
    expect(f.fetcher.mock.calls.some(([address]) => address.pathname.endsWith('/disconnect'))).toBe(false)
  })
  it('does not replace a newer target when a row operation finishes late', async () => {
    const f = fixture(); await waitFor(() => expect(f.client.getSnapshot().servers).toHaveLength(1))
    await f.client.open({ serverId: 'dev', workspaceId: 'W1', sessionId: 'C1' })
    let finish!: (response: Response) => void
    f.fetcher.mockImplementation(async (_address, init) => init?.method === 'POST' ? new Promise(resolve => { finish = resolve }) : new Response(JSON.stringify({ mode: 'cannbot', workspaces: [], sessions: [] })))
    const pending = f.client.operate('dev', { action: 'remove-workspace', workspaceId: 'W1' })
    await waitFor(() => expect(finish).toBeTypeOf('function'))
    await f.client.open({ serverId: 'dev', workspaceId: 'W2', sessionId: 'C2' })
    finish(new Response(JSON.stringify({ ok: true }))); await pending
    expect(f.client.getSnapshot().target).toEqual({ serverId: 'dev', workspaceId: 'W2', sessionId: 'C2' })
  })
  it('reports a committed fork separately from a failed list refresh instead of retrying the mutation', async () => {
    const f = fixture(); await waitFor(() => expect(f.client.getSnapshot().servers).toHaveLength(1))
    f.fetcher.mockImplementation(async (_address, init) => init?.method === 'POST' ? new Response(JSON.stringify({ ok: true, sessionId: 'child' })) : new Response('offline', { status: 503 }))
    await expect(f.client.operate('dev', { action: 'fork-session', sessionId: 'C1' })).rejects.toMatchObject({ committed: true })
    expect(f.fetcher.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(1)
    expect(f.fetcher.mock.calls.filter(([address, init]) => address.pathname.endsWith('/tree') && init?.method !== 'POST')).toHaveLength(2)
  })
  it('recovers a transient post-commit read failure without creating a second fork', async () => {
    const f = fixture(); await waitFor(() => expect(f.client.getSnapshot().servers).toHaveLength(1))
    let reads = 0
    f.fetcher.mockImplementation(async (_address, init) => {
      if (init?.method === 'POST') return new Response(JSON.stringify({ ok: true, sessionId: 'child' }))
      if (++reads === 1) throw new Error('transient tunnel failure')
      return new Response(JSON.stringify({ mode: 'cannbot', workspaces: [], sessions: [{ sessionId: 'child', workspaceId: 'W1' }] }))
    })
    const result = await f.client.operate('dev', { action: 'fork-session', sessionId: 'C1' })
    expect(result.sessionId).toBe('child'); expect(result.tree.sessions[0].id).toBe('child')
    expect(reads).toBe(2)
    expect(f.fetcher.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(1)
  })
  it('retries SSH after the first connection fails instead of refreshing an empty guest', async () => {
    const f = fixture(false); await waitFor(() => expect(f.client.getSnapshot().servers).toHaveLength(1))
    let attempts = 0
    f.fetcher.mockImplementation(async address => {
      if (address.pathname.endsWith('/connect-stream')) {
        attempts++
        return attempts === 1 ? new Response('unavailable', { status: 502 })
          : new Response('data: ' + JSON.stringify({ phase: 'done', ok: true, url: f.server.url }) + '\n\n')
      }
      return new Response(JSON.stringify({ servers: [{ ...f.server, connected: attempts > 1 }] }))
    })
    await expect(f.client.open({ serverId: 'dev', workspaceId: 'W1' })).rejects.toThrow('无法建立')
    render(f.slots.get('cannbot-remote-workbench')!())
    fireEvent.click(screen.getByText('重试'))
    await waitFor(() => expect(f.client.getSnapshot().target).toEqual({ serverId: 'dev', workspaceId: 'W1' }))
    expect(attempts).toBe(2); expect(native.create).toHaveBeenCalledOnce()
  })
  it('disposes the embedded guest when another DSH main page is selected', async () => {
    const f = fixture(); await waitFor(() => expect(f.client.getSnapshot().servers).toHaveLength(1))
    await f.client.open({ serverId: 'dev' }); render(f.slots.get('cannbot-remote-workbench')!())
    await waitFor(() => expect(native.create).toHaveBeenCalledOnce())
    act(() => f.selectPanel(null)); expect(native.dispose).toHaveBeenCalledOnce()
  })
  it('restores a session created inside the guest after a mode switch without remounting on every navigation', async () => {
    const f = fixture(); await waitFor(() => expect(f.client.getSnapshot().servers).toHaveLength(1))
    await f.client.open({ serverId: 'dev' })
    const view = render(f.slots.get('cannbot-remote-workbench')!())
    await waitFor(() => expect(native.create).toHaveBeenCalledOnce())
    const first = native.create.mock.calls[0][0]
    act(() => first.onLocation({ workspaceId: 'W2', sessionId: 'C2' }))
    expect(f.client.getSnapshot().target).toEqual({ serverId: 'dev', workspaceId: 'W2', sessionId: 'C2' })
    expect(native.create).toHaveBeenCalledOnce()
    act(() => f.selectPanel(null)); view.unmount()
    act(() => first.onLocation({ workspaceId: 'stale', sessionId: 'stale' }))
    act(() => f.selectPanel('cannbot-remote-workbench'))
    render(f.slots.get('cannbot-remote-workbench')!())
    await waitFor(() => expect(native.create).toHaveBeenCalledTimes(2))
    const restored = new URL(native.create.mock.calls[1][0].url)
    expect(new URLSearchParams(restored.hash.slice(1)).get('cannSession')).toBe('C2')
    expect(JSON.stringify(f.client.getSnapshot())).not.toContain('private')
  })

  it('opens a compact add-server dialog without replacing the current page or changing existing servers', async () => {
    const f = fixture(); await waitFor(() => expect(f.client.getSnapshot().servers).toHaveLength(1))
    render(f.slots.get('cannbot-add-server')!())
    act(() => f.client.showConnections())
    expect(screen.getByRole('dialog', { name: '新增 SSH 服务器' })).toBeTruthy()
    expect(document.querySelector('option[value="DevEnv950"]')).not.toBeNull()
    expect(f.slots.has('cannbot-remote-connections')).toBe(false)
    expect(f.selectPanel).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: '取消' }))
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(f.client.getSnapshot().servers[0].alias).toBe('DevEnv950')
    expect(f.fetcher.mock.calls.every(([, init]) => init?.method !== 'POST')).toBe(true)
  })

  it('saves only the entered SSH definition, then opens the returned server and preserves the old alias', async () => {
    const f = fixture(); await waitFor(() => expect(f.client.getSnapshot().servers).toHaveLength(1))
    const added = { ...f.server, id: 'new', alias: 'worker', label: '开发服务器', connected: true }
    f.fetcher.mockImplementation(async (address, init) => {
      if (init?.method === 'POST') return new Response(JSON.stringify({ ok: true, server: added }))
      return new Response(JSON.stringify({ servers: [f.server, added] }))
    })
    render(f.slots.get('cannbot-add-server')!()); act(() => f.client.showConnections())
    fireEvent.click(screen.getByRole('tab', { name: 'SSH 命令 / 已有配置' }))
    fireEvent.change(screen.getByLabelText('SSH 命令或别名'), { target: { value: '  ssh worker@10.0.0.2 -p 2222  ' } })
    fireEvent.change(screen.getByLabelText('备注（可选）'), { target: { value: '开发服务器' } })
    fireEvent.click(screen.getByRole('button', { name: '保存并连接' }))
    await waitFor(() => expect(f.client.getSnapshot().target).toEqual({ serverId: 'new' }))
    const saves = f.fetcher.mock.calls.filter(([, init]) => init?.method === 'POST')
    expect(saves).toHaveLength(1)
    expect(saves[0][0].pathname).toBe('/api/cannbot-remote/servers')
    expect(JSON.parse(saves[0][1]!.body as string)).toEqual({ command: 'ssh worker@10.0.0.2 -p 2222', label: '开发服务器' })
    expect(f.onSelectServer).toHaveBeenCalledWith('new')
    expect(f.selectPanel).toHaveBeenLastCalledWith('cannbot-remote-workbench')
    expect(f.client.getSnapshot().servers.map(server => server.alias)).toEqual(['DevEnv950', 'worker'])
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('defaults to a structured SSH form and does not opt into credential synchronization', async () => {
    const f = fixture(); await waitFor(() => expect(f.client.getSnapshot().servers).toHaveLength(1))
    const added = { ...f.server, id: 'new', alias: 'worker' }
    f.fetcher.mockImplementation(async (_address, init) => Response.json(init?.method === 'POST' ? { ok: true, server: added } : { servers: [f.server, added] }))
    render(f.slots.get('cannbot-add-server')!()); act(() => f.client.showConnections())
    expect(screen.getByRole('tab', { name: '填写连接信息' }).getAttribute('aria-selected')).toBe('true')
    expect((screen.getByLabelText('端口') as HTMLInputElement).value).toBe('22')
    expect((screen.getByRole('checkbox') as HTMLInputElement).checked).toBe(false)
    fireEvent.change(screen.getByLabelText('服务器地址'), { target: { value: '10.0.0.2' } })
    fireEvent.change(screen.getByLabelText('用户名'), { target: { value: 'worker' } })
    fireEvent.click(screen.getByRole('button', { name: '保存并连接' }))
    await waitFor(() => expect(f.client.getSnapshot().target).toEqual({ serverId: 'new' }))
    const save = f.fetcher.mock.calls.find(([, init]) => init?.method === 'POST')!
    expect(JSON.parse(save[1]!.body as string)).toEqual({ connection: { hostName: '10.0.0.2', user: 'worker', port: '22', identityFile: '', proxyJump: '' } })
    expect(f.client.getSnapshot().syncLogin).toBe(false)
  })

  it('returns an added server to workspace creation and connects without navigating away', async () => {
    const f = fixture(); await waitFor(() => expect(f.client.getSnapshot().servers).toHaveLength(1))
    const added = { ...f.server, id: 'new', alias: 'worker', connected: true }
    f.fetcher.mockImplementation(async (_address, init) => new Response(JSON.stringify(init?.method === 'POST' ? { ok: true, server: added } : { servers: [f.server, added] })))
    const resume = vi.fn(), connect = vi.spyOn(f.client, 'connect').mockResolvedValue()
    render(f.slots.get('cannbot-add-server')!()); act(() => f.client.showConnections(resume))
    fireEvent.click(screen.getByRole('tab', { name: 'SSH 命令 / 已有配置' }))
    fireEvent.change(screen.getByLabelText('SSH 命令或别名'), { target: { value: 'worker' } })
    fireEvent.click(screen.getByRole('button', { name: '保存并连接' }))
    await waitFor(() => expect(resume).toHaveBeenCalledWith('new'))
    expect(connect).toHaveBeenCalledWith('new')
    expect(f.selectPanel).not.toHaveBeenCalled(); expect(f.onSelectServer).not.toHaveBeenCalled()
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('keeps invalid input in the dialog with a visible error and never starts a connection', async () => {
    const f = fixture(); await waitFor(() => expect(f.client.getSnapshot().servers).toHaveLength(1))
    f.fetcher.mockResolvedValue(new Response(JSON.stringify({ ok: false, message: 'SSH 命令包含不支持的选项。' }), { status: 400 }))
    render(f.slots.get('cannbot-add-server')!()); act(() => f.client.showConnections())
    fireEvent.click(screen.getByRole('tab', { name: 'SSH 命令 / 已有配置' }))
    const input = screen.getByLabelText('SSH 命令或别名')
    fireEvent.change(input, { target: { value: 'ssh host remote-command' } })
    fireEvent.click(screen.getByRole('button', { name: '保存并连接' }))
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('不支持'))
    expect((input as HTMLInputElement).value).toBe('ssh host remote-command')
    expect(f.selectPanel).not.toHaveBeenCalled(); expect(f.onSelectServer).not.toHaveBeenCalled()
    fireEvent(screen.getByRole('dialog'), new Event('cancel', { cancelable: true }))
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('opens remote workspace creation explicitly and consumes the one-shot target after guest navigation', async () => {
    const f = fixture(); await waitFor(() => expect(f.client.getSnapshot().servers).toHaveLength(1))
    await f.client.open({ serverId: 'dev', createWorkspace: true })
    render(f.slots.get('cannbot-remote-workbench')!())
    await waitFor(() => expect(native.create).toHaveBeenCalledOnce())
    const request = native.create.mock.calls[0][0], fragment = new URLSearchParams(new URL(request.url).hash.slice(1))
    expect(fragment.get('cannCreateWorkspace')).toBe('1')
    expect(fragment.has('cannSession')).toBe(false)
    act(() => request.onLocation({ workspaceId: undefined, sessionId: undefined }))
    expect(f.client.getSnapshot().target?.createWorkspace).toBeUndefined()
    expect(native.create).toHaveBeenCalledOnce()
  })
})


it('opens the unified creation dialog for the current guest only', async () => {
  const f = fixture(); await waitFor(() => expect(f.client.getSnapshot().servers).toHaveLength(1))
  await f.client.open({ serverId: 'dev', workspaceId: 'W1' }); render(f.slots.get('cannbot-remote-workbench')!())
  await waitFor(() => expect(native.create).toHaveBeenCalledOnce())
  const guest = native.create.mock.calls[0][0]
  act(() => guest.onCreateWorkspace()); expect(f.onCreateWorkspace).toHaveBeenCalledExactlyOnceWith('dev')
  act(() => f.client.returnLocal()); act(() => guest.onCreateWorkspace())
  expect(f.onCreateWorkspace).toHaveBeenCalledOnce()
})
