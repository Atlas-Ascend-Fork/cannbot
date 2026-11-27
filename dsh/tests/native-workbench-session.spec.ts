// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Context } from '@deepseek-ai/cordis'
import { createNativeWorkbenchSession } from '../plugin/frontend/native-workbench-session.ts'
import { CANNBOT_HOME, type WorkspaceModes } from '../plugin/frontend/workspace-modes.ts'
import type { SelectionSnapshot, WorkflowSelection } from '../plugin/frontend/workflow-selection.ts'

function store<T>(value: T) {
  const listeners = new Set<() => void>()
  return { getSnapshot: () => value, subscribe(listener: () => void) { listeners.add(listener); return () => listeners.delete(listener) }, set(next: T) { value = next; [...listeners].forEach(listener => listener()) } }
}
const controllers: ReturnType<typeof createNativeWorkbenchSession>[] = []
afterEach(() => { controllers.splice(0).forEach(controller => controller.dispose()); vi.restoreAllMocks() })
function fixture() {
  const order: string[] = [], references: any[] = []
  let next = 0
  const catalog = store({ phase: 'ready', ids: ['D1'], byId: { D1: { blank: true, cwd: '/A' } } as Record<string, { blank: boolean; cwd: string }> })
  const panel = store({ activePanelId: CANNBOT_HOME as string | null })
  const mode = store({ mode: 'cannbot' as 'cannbot' | 'deepseek', ready: true, restoringSession: false, navigationError: '', selectedWorkspaceId: '', serverId: '', workspaces: [
    { workspaceId: 'A', path: '/A', pluginId: 'plugin-a', sessionIds: [] as string[] }, { workspaceId: 'B', path: '/B', pluginId: 'plugin-b', sessionIds: [] as string[] },
  ], sessions: [] as { sessionId: string; workspaceId: string }[] })
  const nativeWorkspaces = store({ archivedSessionIds: [] as string[] })
  const saved = store<SelectionSnapshot>({ ready: true, pending: false, error: false, values: {} })
  const choose = vi.fn(async (id: string, pluginId: string) => { order.push('choose:' + id); saved.set({ ...saved.getSnapshot(), values: { ...saved.getSnapshot().values, [id]: pluginId } }) })
  const selection = { ...saved, choose } as unknown as WorkflowSelection
  const recordSession = vi.fn(async (workspaceId: string, id: string, options?: { reveal?: boolean }) => {
    order.push('record:' + id)
    expect(options).toEqual({ reveal: false })
    mode.set({ ...mode.getSnapshot(), workspaces: mode.getSnapshot().workspaces.map(workspace => workspace.workspaceId === workspaceId ? { ...workspace, sessionIds: [...new Set([...workspace.sessionIds, id])] } : workspace), sessions: [...mode.getSnapshot().sessions, { sessionId: id, workspaceId }] })
  })
  const modes = { ...mode, selectWorkspace: vi.fn((id: string) => mode.set({ ...mode.getSnapshot(), selectedWorkspaceId: id })), recordSession,
    openSession: vi.fn((_id: string) => panel.set({ activePanelId: null })) } as unknown as WorkspaceModes
  const create = vi.fn(async ({ workspaceId, sessionId }: { workspaceId: string; sessionId?: string }) => {
    const id = sessionId || 'N' + ++next; order.push('create:' + id)
    catalog.set({ ...catalog.getSnapshot(), ids: [...new Set([...catalog.getSnapshot().ids, id])], byId: { ...catalog.getSnapshot().byId, [id]: { blank: true, cwd: '/' + workspaceId } } })
    return id
  })
  const retain = vi.fn((id: string, options: { signal: AbortSignal }) => {
    order.push('retain:' + id)
    const binding = { ctx: {}, draft: '', attachments: [] as string[], model: 'default', permission: 'ask' }
    const reference = { sessionId: id, binding, ready: Promise.resolve(binding), release: vi.fn() }
    options.signal.addEventListener('abort', () => reference.release(), { once: true })
    references.push(reference); return reference
  })
  const ctx = { sessions: { list: catalog, create, retain }, workspaces: { list: nativeWorkspaces }, layout: { panelInfo: panel }, conversation: { input: { submit: vi.fn(), requestDraftInitialization: vi.fn() } } } as unknown as Context
  const manager = createNativeWorkbenchSession(ctx, selection, modes); controllers.push(manager)
  return { manager, catalog, mode, modes, panel, saved, choose, create, retain, recordSession, references, order, ctx, nativeWorkspaces }
}

describe('native CANNBot blank preparation', () => {
  it('prepares a general session with an empty workflow selection', async () => {
    const f = fixture()
    f.mode.set({ ...f.mode.getSnapshot(), workspaces: f.mode.getSnapshot().workspaces.map(row => ({ ...row, pluginId: 'general' })) })
    f.choose.mockImplementation(async id => { f.saved.set({ ready: true, pending: false, error: false, values: {} }) })
    await f.manager.selectWorkspace('A')
    expect(f.choose).toHaveBeenCalledWith('N1', '')
    expect(f.recordSession).toHaveBeenCalledWith('A', 'N1', { reveal: false })
    expect(f.manager.getSnapshot()).toMatchObject({ sessionId: 'N1', busy: false, error: '' })
  })
  it('records and binds a fresh CANN blank before exposing it, without reusing a DeepSeek blank or submitting', async () => {
    const f = fixture(); await f.manager.selectWorkspace('A')
    expect(f.create).toHaveBeenCalledWith({ workspaceId: 'A' })
    expect(f.order).toEqual(['create:N1', 'record:N1', 'retain:N1', 'choose:N1'])
    expect(f.manager.getSnapshot()).toMatchObject({ workspaceId: 'A', sessionId: 'N1', busy: false, error: '' })
    expect(f.manager.getSnapshot().session).toBe(f.references[0])
    expect(f.modes.openSession).not.toHaveBeenCalled()
    expect((f.ctx.conversation.input as any).submit).not.toHaveBeenCalled()
    expect(f.ctx.conversation.input.requestDraftInitialization).not.toHaveBeenCalled()
  })

  it('preserves draft, attachments, model and permission through workspace and mode switches', async () => {
    const f = fixture(); await f.manager.selectWorkspace('A')
    const first = f.references[0]
    Object.assign(first.binding, { draft: '未发送草稿', attachments: ['file'], model: 'chosen', permission: 'auto' })
    await f.manager.selectWorkspace('B')
    f.mode.set({ ...f.mode.getSnapshot(), mode: 'deepseek' }); await f.manager.selectWorkspace('A')
    expect(f.manager.getSnapshot().workspaceId).toBe('B')
    f.mode.set({ ...f.mode.getSnapshot(), mode: 'cannbot' }); await f.manager.selectWorkspace('A'); await f.manager.selectWorkspace('A')
    expect(f.manager.getSnapshot().session).toBe(first)
    expect(first.binding).toMatchObject({ draft: '未发送草稿', attachments: ['file'], model: 'chosen', permission: 'auto' })
    expect(first.release).not.toHaveBeenCalled(); expect(f.create).toHaveBeenCalledTimes(2); expect(f.choose).toHaveBeenCalledTimes(2)
  })

  it('only reuses registered, unarchived CANN blanks', async () => {
    const f = fixture()
    f.mode.set({ ...f.mode.getSnapshot(), workspaces: f.mode.getSnapshot().workspaces.map(row => row.workspaceId === 'A' ? { ...row, sessionIds: ['C-archived', 'C-active', 'C-blank'] } : row) })
    f.catalog.set({ ...f.catalog.getSnapshot(), byId: { ...f.catalog.getSnapshot().byId, 'C-archived': { blank: true, cwd: '/A' }, 'C-active': { blank: false, cwd: '/A' }, 'C-blank': { blank: true, cwd: '/A' } } })
    f.nativeWorkspaces.set({ archivedSessionIds: ['C-archived'] })
    await f.manager.selectWorkspace('A')
    expect(f.create).toHaveBeenCalledWith({ workspaceId: 'A', sessionId: 'C-blank' })
  })

  it('does not create while a remote historical session is restoring or failed to restore', async () => {
    const f = fixture(); f.mode.set({ ...f.mode.getSnapshot(), restoringSession: true })
    await f.manager.selectWorkspace('A')
    expect(f.manager.getSnapshot().busy).toBe(true); expect(f.create).not.toHaveBeenCalled()
    f.mode.set({ ...f.mode.getSnapshot(), restoringSession: false, navigationError: '历史会话不可用' })
    await f.manager.selectWorkspace('A')
    expect(f.manager.getSnapshot().error).toBe('历史会话不可用'); expect(f.create).not.toHaveBeenCalled()
  })

  it('never inherits a current DeepSeek session when no CANN workspace is selected', async () => {
    const f = fixture(); await f.manager.selectWorkspace(''); await f.manager.selectWorkspace('FOREIGN')
    expect(f.create).not.toHaveBeenCalled(); expect(f.retain).not.toHaveBeenCalled()
    expect(f.manager.getSnapshot().session).toBeUndefined()
  })

  it('keeps a late preparation cached without replacing a more recently selected workspace', async () => {
    const f = fixture(); let finish!: () => void
    f.choose.mockImplementationOnce(async id => { await new Promise<void>(resolve => { finish = resolve }); f.saved.set({ ...f.saved.getSnapshot(), values: { [id]: 'plugin-a' } }) })
    const first = f.manager.selectWorkspace('A'); await vi.waitFor(() => expect(finish).toBeTypeOf('function'))
    const second = f.manager.selectWorkspace('B'); finish(); await Promise.all([first, second])
    expect(f.manager.getSnapshot()).toMatchObject({ workspaceId: 'B', sessionId: 'N2' })
    await f.manager.selectWorkspace('A')
    expect(f.manager.getSnapshot().sessionId).toBe('N1'); expect(f.create).toHaveBeenCalledTimes(2)
  })

  it('shows a failed binding and retries the already recorded blank without exposing or submitting it early', async () => {
    const f = fixture(); f.choose.mockImplementationOnce(async () => { f.saved.set({ ...f.saved.getSnapshot(), error: true }) })
    await f.manager.selectWorkspace('A')
    expect(f.manager.getSnapshot()).toMatchObject({ busy: false, error: '工作区对话准备失败，请重试。' })
    expect(f.manager.getSnapshot().session).toBeUndefined(); expect(f.references[0].release).toHaveBeenCalledOnce()
    f.saved.set({ ...f.saved.getSnapshot(), error: false })
    await f.manager.retry()
    expect(f.create).toHaveBeenLastCalledWith({ workspaceId: 'A', sessionId: 'N1' })
    expect(f.manager.getSnapshot().sessionId).toBe('N1')
  })

  it('uses a preparation deadline without expiring the successfully retained draft', async () => {
    const deadlines: AbortController[] = []
    vi.spyOn(AbortSignal, 'timeout').mockImplementation(() => { const controller = new AbortController(); deadlines.push(controller); return controller.signal })
    const f = fixture(); await f.manager.selectWorkspace('A')
    deadlines.forEach(controller => controller.abort())
    expect(f.references[0].release).not.toHaveBeenCalled()
    expect(f.manager.getSnapshot().session).toBe(f.references[0])
  })

  it('hands a submitted blank to native main exactly once and never submits the draft itself', async () => {
    const f = fixture(); await f.manager.selectWorkspace('A')
    f.catalog.set({ ...f.catalog.getSnapshot(), byId: { ...f.catalog.getSnapshot().byId, N1: { blank: false, cwd: '/A' } } })
    expect(f.modes.openSession).toHaveBeenCalledExactlyOnceWith('N1')
    expect(f.panel.getSnapshot().activePanelId).toBeNull()
    expect(f.references[0].release).toHaveBeenCalledOnce()
    expect((f.ctx.conversation.input as any).submit).not.toHaveBeenCalled()
  })

  it('disposes pending acquisitions without publishing a late session', async () => {
    const f = fixture(); let finish!: () => void
    f.choose.mockImplementationOnce(async () => new Promise<void>(resolve => { finish = resolve }))
    const preparation = f.manager.selectWorkspace('A'); await vi.waitFor(() => expect(finish).toBeTypeOf('function'))
    f.manager.dispose(); finish(); await preparation
    expect(f.manager.getSnapshot().session).toBeUndefined()
    expect(f.references[0].release).toHaveBeenCalled()
    expect(f.modes.openSession).not.toHaveBeenCalled()
  })
})
