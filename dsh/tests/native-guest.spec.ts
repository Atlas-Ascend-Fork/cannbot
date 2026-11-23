// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createNativeGuest } from '../src/client/remote/native-guest.mjs'

const target = 'http://127.0.0.1:17633/?token=TEST_ONLY_TUNNEL_SECRET#cannEmbed=1&cannMode=cannbot&cannWorkspace=W1&cannSession=S1'
const guests: ReturnType<typeof createNativeGuest>[] = []
const flush = async () => { for (let index = 0; index < 6; index++) await Promise.resolve() }

afterEach(async () => {
  await Promise.all(guests.splice(0).map(guest => guest.dispose()))
  document.body.replaceChildren()
  vi.restoreAllMocks()
  vi.useRealTimers()
})

async function fixture(options: { acquire?: () => Promise<{ lease: string; partition: string }>; aborted?: boolean } = {}) {
  const host = document.createElement('div')
  document.body.append(host)
  const element = document.createElement('webview')
  let currentUrl = 'about:blank'
  const getURL = vi.fn(() => currentUrl)
  const loadURL = vi.fn(async (url: string) => {
    if (options.aborted) throw Object.assign(new Error('TEST_ONLY_TUNNEL_SECRET'), { code: 'ERR_ABORTED' })
    currentUrl = url
  })
  const reload = vi.fn()
  Object.assign(element, { getURL, loadURL, reload })
  const originalCreate = document.createElement.bind(document)
  vi.spyOn(document, 'createElement').mockImplementation(((name: string, ...args: unknown[]) => name === 'webview'
    ? element : originalCreate(name, ...args as [])) as typeof document.createElement)
  const unsubscribe = vi.fn(), onLocation = vi.fn(), onState = vi.fn(), onCreateWorkspace = vi.fn()
  let onOpen: ((url: string) => void) | undefined
  const bridge = {
    acquire: vi.fn(options.acquire ?? (async () => ({ lease: 'test-lease', partition: 'persist:test-partition' }))),
    release: vi.fn(async (_lease: string) => {}),
    onOpenRequested: vi.fn((_lease: string, listener: (url: string) => void) => { onOpen = listener; return unsubscribe }),
  }
  const guest = createNativeGuest({ host, url: target, workspaceKey: 'test-workspace', bridge, onLocation, onState, onCreateWorkspace })
  guests.push(guest)
  await flush()
  return { host, element, guest, bridge, unsubscribe, onLocation, onState, onCreateWorkspace, getURL, loadURL, reload,
    setUrl: (url: string) => { currentUrl = url },
    fire: (name: string, properties: Record<string, unknown> = {}) => element.dispatchEvent(Object.assign(new Event(name), properties)),
    open: (url: string) => onOpen?.(url),
  }
}

describe('native guest scope bridge', () => {
  it('reports completed loads and top-level hash navigation as only the current CANN workspace/session', async () => {
    const f = await fixture()
    f.setUrl(target)
    f.fire('did-navigate-in-page', { isMainFrame: true })
    expect(f.onLocation).not.toHaveBeenCalled()
    f.fire('dom-ready')
    expect(f.loadURL).toHaveBeenCalledWith(target)
    f.fire('did-finish-load')
    expect(f.onLocation).toHaveBeenLastCalledWith({ workspaceId: 'W1', sessionId: 'S1' })
    f.setUrl('http://127.0.0.1:17633/?token=ANOTHER_TEST_SECRET#cannEmbed=1&cannMode=cannbot&cannWorkspace=W2&cannSession=S2&unrelated=PRIVATE')
    f.fire('did-navigate-in-page', { isMainFrame: true })
    expect(f.onLocation).toHaveBeenLastCalledWith({ workspaceId: 'W2', sessionId: 'S2' })
    expect(f.onLocation).toHaveBeenCalledTimes(2)
    expect(JSON.stringify(f.onLocation.mock.calls)).not.toMatch(/SECRET|PRIVATE|https?:|token|lease|partition/)
  })

  it('reports a workspace without a stale session when the guest returns to its workspace page', async () => {
    const f = await fixture()
    f.fire('dom-ready'); f.fire('did-finish-load')
    f.setUrl('http://127.0.0.1:17633/#cannEmbed=1&cannMode=cannbot&cannWorkspace=W2')
    f.fire('did-navigate-in-page', { isMainFrame: true })
    expect(f.onLocation).toHaveBeenLastCalledWith({ workspaceId: 'W2' })
  })

  it('ignores subframes, other origins or paths, malformed URLs, and pages without explicit embedded CANN mode', async () => {
    const f = await fixture()
    f.fire('dom-ready')
    f.fire('did-navigate-in-page', { isMainFrame: false })
    f.fire('did-navigate-in-page')
    expect(f.onLocation).not.toHaveBeenCalled()
    const scope = '#cannEmbed=1&cannMode=cannbot&cannWorkspace=W2&cannSession=S2'
    for (const url of [
      'http://example.test/' + scope,
      'http://127.0.0.1:17634/' + scope,
      'http://127.0.0.1:17633/other' + scope,
      'http://user:PRIVATE@127.0.0.1:17633/' + scope,
      'http://127.0.0.1:17633/#cannMode=cannbot&cannWorkspace=W2&cannSession=S2',
      'http://127.0.0.1:17633/#cannEmbed=0&cannMode=cannbot&cannWorkspace=W2&cannSession=S2',
      'http://127.0.0.1:17633/#cannEmbed=1&cannMode=deepseek&cannWorkspace=W2&cannSession=S2',
      'http://127.0.0.1:17633/', 'about:blank', 'not a URL',
    ]) {
      f.setUrl(url)
      f.fire('did-navigate-in-page', { isMainFrame: true })
      f.fire('did-finish-load')
    }
    expect(f.onLocation).not.toHaveBeenCalled()
  })

  it('rejects session-only scopes and malformed IDs while permitting an empty CANN scope', async () => {
    const f = await fixture()
    f.fire('dom-ready')
    for (const query of [
      'cannSession=S2', 'cannWorkspace=bad%0Aworkspace&cannSession=S2',
      'cannWorkspace=W2&cannSession=bad%20session', 'cannWorkspace=' + 'W'.repeat(513),
    ]) {
      f.setUrl('http://127.0.0.1:17633/#cannEmbed=1&cannMode=cannbot&' + query)
      f.fire('did-navigate-in-page', { isMainFrame: true })
    }
    expect(f.onLocation).not.toHaveBeenCalled()
    f.setUrl('http://127.0.0.1:17633/#cannEmbed=1&cannMode=cannbot')
    f.fire('did-navigate-in-page', { isMainFrame: true })
    expect(f.onLocation).toHaveBeenCalledExactlyOnceWith({ workspaceId: undefined, sessionId: undefined })
  })

  it('ignores aborted navigation without exposing its exception or turning it into a failed load', async () => {
    const f = await fixture({ aborted: true })
    f.fire('dom-ready')
    await flush()
    f.fire('did-fail-load', { isMainFrame: true, errorCode: -3, validatedURL: target })
    expect(f.onLocation).not.toHaveBeenCalled()
    expect(f.onState.mock.calls.every(([state]) => state.status !== 'error')).toBe(true)
    expect(JSON.stringify(f.onState.mock.calls)).not.toContain('SECRET')
  })

  it('handles getURL exceptions without returning exception contents to callbacks', async () => {
    const f = await fixture()
    f.fire('dom-ready')
    f.getURL.mockImplementation(() => { throw new Error('TEST_ONLY_TUNNEL_SECRET') })
    f.fire('did-navigate-in-page', { isMainFrame: true }); f.fire('did-finish-load')
    expect(f.onLocation).not.toHaveBeenCalled()
    expect(JSON.stringify(f.onState.mock.calls)).not.toContain('SECRET')
  })

  it('completes a main-frame hash navigation without waiting for did-finish-load or falsely timing out', async () => {
    vi.useFakeTimers()
    const f = await fixture()
    f.fire('dom-ready'); f.fire('did-finish-load')
    f.onState.mockClear(); f.onLocation.mockClear()
    f.fire('did-start-loading')
    f.setUrl('http://127.0.0.1:17633/#cannEmbed=1&cannMode=cannbot&cannWorkspace=W1&cannSession=NEW')
    f.fire('did-navigate-in-page', { isMainFrame: false })
    expect(f.onState).toHaveBeenLastCalledWith({ status: 'loading', error: '', notice: '' })
    f.fire('did-navigate-in-page', { isMainFrame: true })
    expect(f.onState).toHaveBeenLastCalledWith({ status: 'ready', error: '' })
    expect(f.onLocation).toHaveBeenCalledExactlyOnceWith({ workspaceId: 'W1', sessionId: 'NEW' })
    const completedCalls = f.onState.mock.calls.length
    await vi.advanceTimersByTimeAsync(31_000)
    expect(f.onState).toHaveBeenCalledTimes(completedCalls)
    expect(f.onState.mock.calls.some(([state]) => state.status === 'error')).toBe(false)
  })

  it('completes a stopped non-blank load and cancels the watchdog when finish-load is absent', async () => {
    vi.useFakeTimers()
    const f = await fixture()
    f.fire('dom-ready'); f.fire('did-start-loading'); f.fire('did-stop-loading')
    expect(f.onState).toHaveBeenLastCalledWith({ status: 'ready', error: '' })
    expect(f.onLocation).toHaveBeenCalledExactlyOnceWith({ workspaceId: 'W1', sessionId: 'S1' })
    const completedCalls = f.onState.mock.calls.length
    await vi.advanceTimersByTimeAsync(31_000)
    expect(f.onState).toHaveBeenCalledTimes(completedCalls)
  })

  it('keeps a blank-page stop pending so an actual unfinished load still times out', async () => {
    vi.useFakeTimers()
    const f = await fixture()
    f.fire('dom-ready'); f.setUrl('about:blank'); f.fire('did-stop-loading')
    expect(f.onState).toHaveBeenLastCalledWith({ status: 'loading', error: '', notice: '' })
    expect(f.onLocation).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(30_001)
    expect(f.onState.mock.lastCall?.[0].status).toBe('error')
  })

  it.each(['did-fail-load', 'render-process-gone'])('preserves %s errors on stop-loading until a new load begins', async eventName => {
    vi.useFakeTimers()
    const f = await fixture()
    f.fire('dom-ready'); f.fire(eventName, { isMainFrame: true, errorCode: -105, errorDescription: 'TEST_ONLY_TUNNEL_SECRET' })
    const failedCalls = f.onState.mock.calls.length
    expect(f.onState.mock.lastCall?.[0].status).toBe('error')
    f.fire('did-stop-loading')
    await vi.advanceTimersByTimeAsync(31_000)
    expect(f.onState).toHaveBeenCalledTimes(failedCalls)
    expect(f.onLocation).not.toHaveBeenCalled()
    expect(JSON.stringify(f.onState.mock.calls)).not.toContain('SECRET')
    expect(f.guest.reload()).toBe(true)
    f.fire('did-stop-loading')
    expect(f.onState).toHaveBeenLastCalledWith({ status: 'ready', error: '' })
    expect(f.onLocation).toHaveBeenCalledExactlyOnceWith({ workspaceId: 'W1', sessionId: 'S1' })
  })

  it('releases its lease exactly once and ignores all detached guest callbacks after disposal', async () => {
    const f = await fixture()
    f.fire('dom-ready'); f.fire('did-finish-load')
    f.onLocation.mockClear(); f.onState.mockClear()
    const first = f.guest.dispose(), second = f.guest.dispose()
    expect(first).toBe(second)
    await first
    f.fire('did-navigate-in-page', { isMainFrame: true }); f.fire('did-finish-load'); f.fire('render-process-gone')
    f.open(target)
    expect(f.guest.reload()).toBe(false)
    expect(f.host.children).toHaveLength(0)
    expect(f.bridge.release).toHaveBeenCalledExactlyOnceWith('test-lease')
    expect(f.unsubscribe).toHaveBeenCalledOnce()
    expect(f.onLocation).not.toHaveBeenCalled(); expect(f.onState).not.toHaveBeenCalled()
  })

  it('releases a late reservation once without constructing a guest after disposal', async () => {
    let resolve!: (reservation: { lease: string; partition: string }) => void
    const f = await fixture({ acquire: () => new Promise(done => { resolve = done }) })
    const disposing = f.guest.dispose()
    resolve({ lease: 'late-lease', partition: 'persist:late' })
    await disposing; await f.guest.dispose()
    expect(f.bridge.release).toHaveBeenCalledExactlyOnceWith('late-lease')
    expect(f.host.children).toHaveLength(0)
    expect(f.bridge.onOpenRequested).not.toHaveBeenCalled()
    expect(f.onLocation).not.toHaveBeenCalled()
  })
})


it('forwards one explicit in-page creation request to the desktop without reopening on reload', async () => {
  const f = await fixture(); f.fire('dom-ready'); f.fire('did-finish-load')
  const url = target + '&cannNewFolder=12345678-1234-1234-1234-123456789abc'
  f.setUrl(url); f.fire('did-finish-load'); expect(f.onCreateWorkspace).not.toHaveBeenCalled()
  f.fire('did-navigate-in-page', { isMainFrame: false }); expect(f.onCreateWorkspace).not.toHaveBeenCalled()
  f.fire('did-navigate-in-page', { isMainFrame: true }); f.fire('did-navigate-in-page', { isMainFrame: true })
  expect(f.onCreateWorkspace).toHaveBeenCalledOnce()
  f.setUrl('https://outside.invalid/#cannEmbed=1&cannMode=cannbot&cannNewFolder=22345678-1234-1234-1234-123456789abc')
  f.fire('did-navigate-in-page', { isMainFrame: true }); expect(f.onCreateWorkspace).toHaveBeenCalledOnce()
})
