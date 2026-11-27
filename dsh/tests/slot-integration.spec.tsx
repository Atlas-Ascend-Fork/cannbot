// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Context } from '@deepseek-ai/cordis'
import type { ReactElement } from 'react'
import { SlotCore } from '@deepseek-ai/dsh-client-ui-slots'
import { apply } from '../plugin/editions/client/ui.ts'
import { apply as applyServer } from '../plugin/editions/server/ui.ts'
import { SidebarMark } from '../plugin/frontend/Brand.tsx'
import type { WorkspaceModes } from '../plugin/frontend/workspace-modes.ts'

vi.mock('@deepseek-ai/dsh-client-ui-primitives', () => ({ FishLogo: () => null, Menu: () => null, StateDot: () => null }))
afterEach(() => { vi.unstubAllGlobals(); localStorage.clear() })

function fixture() {
  const core = new SlotCore()
  const register = (options: object, component: unknown = () => null) => core.register(options as never, component as never)
  register({ name: 'root', children: { sidebar: { kind: 'single', scope: 'root' }, main: { kind: 'keyed', scope: 'root' }, 'shell.overlay': { kind: 'list', scope: 'root' } } })
  register({ name: 'sidebar', children: {
    'sidebar.brand.mark': { kind: 'single', scope: 'root' }, 'sidebar.brand.name': { kind: 'single', scope: 'root' },
    'sidebar.workspaces': { kind: 'single', scope: 'root' }, 'sidebar.settings': { kind: 'single', scope: 'root' },
    'sidebar.footer.action': { kind: 'list', scope: 'root' }, 'sidebar.panellist': { kind: 'list', scope: 'root' },
    'conversation.input.dock': { kind: 'list', scope: 'root' }, 'conversation.session.header.actions': { kind: 'list', scope: 'root' },
    'conversation.input.overlay': { kind: 'list', scope: 'session' },
    'conversation.hero.brand.mark': { kind: 'single', scope: 'root' }, 'conversation.hero.agentPreset': { kind: 'single', scope: 'root' },
    'conversation.hero.workspace': { kind: 'single', scope: 'root' },
  } })
  const nativeTree = () => null, nativeTodo = () => null, nativeHeader = () => null, nativeMain = () => null, nativePicker = () => null
  register({ name: 'sidebar.workspaces', children: { 'sidebar.workspaces.session.menu.item': { kind: 'list', scope: 'root' } } }, nativeTree)
  register({ name: 'conversation.input.dock', id: 'todo' }, nativeTodo)
  register({ name: 'conversation.session.header.actions', id: 'native' }, nativeHeader)
  register({ name: 'main', key: 'conversation' }, nativeMain)
  register({ name: 'conversation.hero.workspace' }, nativePicker)
  const effects: (() => void)[] = []
  const originalStart = vi.fn(), originalArchive = vi.fn(async () => {}), originalFork = vi.fn(async () => 'C2')
  const workspace = { workspaceId: 'C', path: '/cann', title: 'CANN', pluginId: 'ops-direct-invoke', sessionIds: ['C1'], sharedWithDeepSeek: false }
  const sessions = [{ sessionId: 'C1', workspaceId: 'C', pluginId: 'ops-direct-invoke', title: 'CANN会话' }]
  const requests: object[] = []
  vi.stubGlobal('fetch', vi.fn(async (_: unknown, init?: RequestInit) => {
    if (init?.method === 'POST') { const request = JSON.parse(init.body as string); requests.push(request); const session = { sessionId: request.sessionId, workspaceId: request.workspaceId, pluginId: workspace.pluginId, title: '分支' }; sessions.push(session); workspace.sessionIds.push(session.sessionId); return new Response(JSON.stringify({ ok: true, session })) }
    return new Response(JSON.stringify({ mode: 'cannbot', workspaces: [workspace], sessions, plugins: [], servers: [] }))
  }))
  const state = { phase: 'ready', items: [workspace, { workspaceId: 'D', path: '/deepseek', title: 'DS', sessionIds: ['D1'] }], archivedSessionIds: [], byId: { D1: { retainedBy: { mainView: 1 } } } }
  let panel: string | null = null
  const ctx = {
    inject(keys: string[], callback: (ctx: object) => void) { if (keys[0] === 'layout') callback(ctx); return { dispose() {} } },
    effect(callback: () => () => void) { effects.push(callback()) },
    get: () => undefined,
    slots: { register, inject(name: string, callback: () => () => void) { if (!core.specDynamic(name)) throw new Error('undeclared test slot'); return callback() } },
    locale: { register: () => () => {} }, theme: { overrideTokens: () => () => {} },
    workspaces: { list: { getSnapshot: () => state, subscribe: () => () => {} } },
    sessions: { list: { getSnapshot: () => state, subscribe: () => () => {} }, retain: vi.fn() },
    conversation: { input: { requestDraftInitialization: vi.fn() } },
    layout: { panelInfo: { getSnapshot: () => ({ activePanelId: panel }), subscribe: () => () => {} }, selectPanel(id: string | null) { panel = id } },
    uiWorkspace: { startSession: originalStart, archiveSession: originalArchive, forkSession: originalFork, openSession: vi.fn() },
  }
  const dispose = () => { for (const stop of effects.splice(0).reverse()) stop() }
  return { core, ctx, register, dispose, originalStart, originalArchive, originalFork, requests, nativeTree, nativeTodo, nativeHeader, nativeMain, nativePicker }
}

describe('real DSH SlotCore lifecycle', () => {
  it('registers only local workspaces and the fixed CANNBot brand in a server profile', async () => {
    localStorage.setItem('cannbot.ui.modes.v1', JSON.stringify({ mode: 'deepseek' }))
    const f = fixture()
    try {
      applyServer(f.ctx as unknown as Context)
      const brand = f.core.entriesOfSlot('sidebar.brand.mark')[0]!
      expect((brand.component as (props: object) => ReactElement)({ size: 24 }).type).toBe(SidebarMark)
      expect(f.core.entriesOfSlot('shell.overlay').map(entry => entry.options.id)).not.toContain('cannbot-add-server')
      expect(f.core.entriesOfSlot('main').map(entry => entry.options.key)).not.toContain('cannbot-servers')
      await vi.waitFor(() => expect(f.ctx.layout.panelInfo.getSnapshot().activePanelId).toBe('cannbot-dsh-workbench'))
      expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).includes('api/cannbot-remote/'))).toBe(false)
    } finally { f.dispose() }
    expect(f.core.entriesOfSlot('sidebar.brand.mark')).toHaveLength(0)
    expect(f.ctx.uiWorkspace.startSession).toBe(f.originalStart)
  })
  it('preserves the exact native DeepSeek sidebar, picker, main, dock and header registrations', async () => {
    localStorage.setItem('cannbot.ui.modes.v1', JSON.stringify({ mode: 'deepseek' }))
    const f = fixture()
    expect(() => f.register({ name: 'sidebar', priority: -200, children: { 'sidebar.brand.mark': { kind: 'single', scope: 'root' } } })).toThrow('already declared')
    expect(() => apply(f.ctx as unknown as Context)).not.toThrow()
    expect(f.core.entriesOfSlot('sidebar')).toHaveLength(1)
    expect(f.core.entriesOfSlot('sidebar.workspaces')).toHaveLength(1)
    expect(f.core.entriesOfSlot('sidebar.workspaces')[0]?.component).toBe(f.nativeTree)
    expect(f.core.entriesOfSlot('conversation.hero.workspace')[0]?.component).toBe(f.nativePicker)
    expect(f.core.entriesOfSlot('main').find(entry => entry.options.key === 'conversation')?.component).toBe(f.nativeMain)
    expect(f.core.entriesOfSlot('conversation.input.dock')[0]?.component).toBe(f.nativeTodo)
    expect(f.core.entriesOfSlot('conversation.session.header.actions')[0]?.component).toBe(f.nativeHeader)
    expect(f.core.entriesOfSlot('main').some(entry => entry.options.key === 'cannbot-deepseek-home')).toBe(false)
    expect(f.core.entriesOfSlot('sidebar.footer.action')).toHaveLength(0)
    expect(f.core.entriesOfSlot('sidebar.panellist')).toHaveLength(0)
    const entry = f.core.entriesOfSlot('sidebar.brand.mark')[0]!
    const element = (entry.component as (props: object) => ReactElement<{ modes: WorkspaceModes }>)({ size: 24 })
    await vi.waitFor(() => expect(element.props.modes.getSnapshot().ready).toBe(true))
    const nativeEntry = f.core.entriesOfSlot('sidebar.workspaces')[0]
    element.props.modes.setMode('cannbot')
    expect(f.core.entriesOfSlot('conversation.hero.workspace')[0]?.component).not.toBe(f.nativePicker)
    expect(f.core.entriesOfSlot('sidebar.workspaces')[0]).toBe(nativeEntry)
    expect(f.core.entriesOfSlot('shell.overlay').some(entry => entry.options.id === 'cannbot-workspace-tree-bridge')).toBe(true)
    expect(f.core.entriesOfSlot('conversation.input.dock')[0]?.component).not.toBe(f.nativeTodo)
    expect(f.core.entriesOfSlot('sidebar.brand.name')).toHaveLength(1)
    expect(f.core.entriesOfSlot('conversation.hero.agentPreset')).toHaveLength(1)
    element.props.modes.setMode('deepseek')
    expect(f.core.entriesOfSlot('sidebar.workspaces')[0]?.component).toBe(f.nativeTree)
    expect(f.core.entriesOfSlot('conversation.hero.workspace')[0]?.component).toBe(f.nativePicker)
    expect(f.core.entriesOfSlot('main').find(entry => entry.options.key === 'conversation')?.component).toBe(f.nativeMain)
    expect(f.core.entriesOfSlot('conversation.input.dock')[0]?.component).toBe(f.nativeTodo)
    expect(f.core.entriesOfSlot('conversation.session.header.actions')).toHaveLength(1)
    expect(f.core.entriesOfSlot('conversation.session.header.actions')[0]?.component).toBe(f.nativeHeader)
    expect(f.core.entriesOfSlot('conversation.hero.agentPreset')).toHaveLength(0)
    for (let attempt = 0; attempt < 3; attempt++) {
      element.props.modes.setMode('cannbot')
      expect(f.core.entriesOfSlot('sidebar.workspaces')[0]).toBe(nativeEntry)
      element.props.modes.setMode('deepseek')
      expect(f.core.entriesOfSlot('sidebar.workspaces')[0]).toBe(nativeEntry)
    }
    expect(f.core.specDynamic('sidebar.workspaces.session.menu.item')).toBeDefined()
    f.dispose()
    expect(f.core.entriesOfSlot('sidebar.workspaces')).toHaveLength(1)
    expect(f.core.entriesOfSlot('sidebar.workspaces')[0]?.options.priority ?? 0).toBe(0)
    expect(f.core.entriesOfSlot('sidebar.brand.mark')).toHaveLength(0)
    expect(f.core.entriesOfSlot('sidebar.brand.name')).toHaveLength(0)
    expect(f.core.specDynamic('sidebar.settings')).toBeDefined()
    expect(f.ctx.uiWorkspace.startSession).toBe(f.originalStart)
  })
  it('keeps native DeepSeek operations unchanged and guards CANN operations against foreign mainViews', async () => {
    localStorage.setItem('cannbot.ui.modes.v1', JSON.stringify({ mode: 'deepseek' }))
    const f = fixture(); apply(f.ctx as unknown as Context)
    const entry = f.core.entriesOfSlot('sidebar.brand.mark')[0]!
    const modes = (entry.component as (props: object) => ReactElement<{ modes: WorkspaceModes }>)({ size: 24 }).props.modes
    await vi.waitFor(() => expect(modes.getSnapshot().ready).toBe(true))
    await f.ctx.uiWorkspace.archiveSession('C1' as never)
    await f.ctx.uiWorkspace.forkSession('C1' as never)
    expect(f.originalArchive).toHaveBeenCalledOnce(); expect(f.originalFork).toHaveBeenCalledOnce()
    expect(f.requests).toHaveLength(0)
    f.originalArchive.mockClear(); f.originalFork.mockClear()
    modes.setMode('cannbot')
    await expect(f.ctx.uiWorkspace.archiveSession('D1' as never)).rejects.toThrow('所属模式')
    await expect(f.ctx.uiWorkspace.forkSession('D1' as never)).rejects.toThrow('所属模式')
    expect(f.originalArchive).not.toHaveBeenCalled(); expect(f.originalFork).not.toHaveBeenCalled()
    await f.ctx.uiWorkspace.archiveSession('C1' as never)
    await expect(f.ctx.uiWorkspace.forkSession('C1' as never)).resolves.toBe('C2')
    expect(f.requests).toContainEqual({ action: 'session', workspaceId: 'C', sessionId: 'C2' })
    f.dispose(); expect(f.ctx.uiWorkspace.archiveSession).toBe(f.originalArchive); expect(f.ctx.uiWorkspace.forkSession).toBe(f.originalFork)
  })
  it('forwards the unchanged native DeepSeek new-session target and receiver before membership loads', () => {
    localStorage.setItem('cannbot.ui.modes.v1', JSON.stringify({ mode: 'deepseek' }))
    const f = fixture(); apply(f.ctx as unknown as Context)
    const options = { prompt: 'native draft', whenDraftExists: 'keep' }
    f.ctx.uiWorkspace.startSession('D' as never, options as never)
    expect(f.originalStart).toHaveBeenCalledWith('D', options)
    expect(f.originalStart.mock.contexts[0]).toBe(f.ctx.uiWorkspace)
    expect(f.ctx.sessions.retain).not.toHaveBeenCalled()
    f.dispose()
  })
  it('does not let desktop shortcuts mutate a retained local CANN session while viewing a remote server', async () => {
    const f = fixture(); apply(f.ctx as unknown as Context)
    const entry = f.core.entriesOfSlot('sidebar.brand.mark')[0]!
    const modes = (entry.component as (props: object) => ReactElement<{ modes: WorkspaceModes }>)({ size: 24 }).props.modes
    await vi.waitFor(() => expect(modes.getSnapshot().ready).toBe(true))
    modes.setMode('cannbot'); modes.selectServer('remote-server')
    await expect(f.ctx.uiWorkspace.archiveSession('C1' as never)).rejects.toThrow('远端会话行')
    await expect(f.ctx.uiWorkspace.forkSession('C1' as never)).rejects.toThrow('远端会话行')
    expect(f.originalArchive).not.toHaveBeenCalled(); expect(f.originalFork).not.toHaveBeenCalled()
    expect(f.requests).toHaveLength(0)
    modes.setMode('deepseek')
    await f.ctx.uiWorkspace.archiveSession('C1' as never)
    await f.ctx.uiWorkspace.forkSession('C1' as never)
    expect(f.originalArchive).toHaveBeenCalledOnce(); expect(f.originalFork).toHaveBeenCalledOnce()
    f.dispose()
  })
  it('keeps a CANN branch owned after its native workspace was removed', async () => {
    const f = fixture(); apply(f.ctx as unknown as Context)
    const entry = f.core.entriesOfSlot('sidebar.brand.mark')[0]!
    const modes = (entry.component as (props: object) => ReactElement<{ modes: WorkspaceModes }>)({ size: 24 }).props.modes
    await vi.waitFor(() => expect(modes.getSnapshot().ready).toBe(true))
    modes.setMode('cannbot')
    const source = { sessionId: 'C1', workspaceId: 'removed', pluginId: 'ops-direct-invoke', ungrouped: true }
    const owned = [source]
    const fetcher = vi.fn(async (_: unknown, init?: RequestInit) => {
      if (init?.method === 'POST') { owned.push({ ...source, sessionId: 'C2' }); return new Response(JSON.stringify({ ok: true, sessionId: 'C2' })) }
      return new Response(JSON.stringify({ mode: 'cannbot', workspaces: [], sessions: owned }))
    })
    vi.stubGlobal('fetch', fetcher); await modes.refresh()
    const created = vi.fn()
    await expect((f.ctx as unknown as Context).uiWorkspace.forkSession('C1' as never, created, { allowMigration: false })).resolves.toBe('C2')
    expect(f.originalFork).not.toHaveBeenCalled()
    expect(created).toHaveBeenCalledWith('C2')
    expect(modes.getSnapshot().sessions.some(session => session.sessionId === 'C2')).toBe(true)
    expect(fetcher.mock.calls.some(([, init]) => init?.body === JSON.stringify({ action: 'fork-session', sessionId: 'C1', allowMigration: false }))).toBe(true)
    f.dispose()
  })
})
