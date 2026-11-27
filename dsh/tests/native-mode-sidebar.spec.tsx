// ----------------------------------------------------------------------------------------------------------
// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.
// ----------------------------------------------------------------------------------------------------------

import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ReactNode } from 'react'
import type { Context } from '@deepseek-ai/cordis'
import { ModeBrandMark, ModeWorkspaceTree, ModeWorkspaceCreation } from '../plugin/frontend/ModeSidebar.tsx'
import { createWorkspaceModes } from '../plugin/frontend/workspace-modes.ts'
import { Workbench } from '../plugin/frontend/Workbench.tsx'
import type { ContentStore } from '../plugin/frontend/content-store.ts'
import type { RemoteClient, RemoteSnapshot } from '../plugin/frontend/remote/types.ts'
import type { WorkflowSelection } from '../plugin/frontend/workflow-selection.ts'
import { WORKFLOWS } from '../plugin/contracts/workflows.ts'

vi.mock('@deepseek-ai/dsh-client-ui-primitives', async () => ({
  // Exercise upstream public menus, dialogs, tooltips and Toast unchanged;
  // icons stay lightweight so assertions focus on action and ownership behavior.
  ...(await import('@dsh-test-source/packages/client/ui-primitives/src/DisclosureRow.tsx')),
  ...(await import('@dsh-test-source/packages/client/ui-primitives/src/BrandWordmark.tsx')),
  ...(await import('@dsh-test-source/packages/client/ui-primitives/src/Tooltip.tsx')),
  FishLogo: () => <svg data-testid="deepseek-logo" />, IconFolderCloseRegular: () => <svg data-testid="folder-icon" />, IconNewChatOutlineRegular: () => <svg />,
  IconFollowsystemOutlineRegular: () => <svg data-testid="computer-icon" />,
  IconFolderOpenRegular: () => <svg data-testid="open-folder-icon" />, IconTriangleRightFillRegular: (props: { className?: string }) => <svg data-testid="triangle-icon" {...props} />,
  IconArchiveOffOutlineRegular: () => <svg />, IconArchiveCheckOutlineRegular: () => <svg />, IconQueueOutlineRegular: () => <svg />, IconSlidersTwoOutlineRegular: () => <svg />, IconWarningOutlineRegular: () => <svg />,
  StateDot: ({ state }: { state: string }) => <svg data-state={state} />,

  IconEditOutlineRegular: () => <svg />, IconEllipsisOutlineRegular: () => <svg />, IconPinFillRegular: () => <svg />, IconPinOutlineRegular: () => <svg />,
  IconArchiveOutlineRegular: () => <svg />, IconUnarchiveOutlineRegular: () => <svg />, IconBranchOutlineRegular: () => <svg />, IconCopyOutlineRegular: () => <svg />, IconTrashOutlineRegular: () => <svg />,

  IconLinkOutlineRegular: () => <svg />, IconCheckOutlineRegular: () => <svg />, IconRefreshOutlineRegular: () => <svg />,
  IconChevronDownOutlineRegular: () => <svg />, IconPlusOutlineRegular: () => <svg />, IconProjectAddOutlineRegular: () => <svg />, IconSendOutlineRegular: () => <svg />,
  ...(await import('@dsh-test-source/packages/client/ui-primitives/src/Menu.tsx')),
  ...(await import('@dsh-test-source/packages/client/ui-primitives/src/Modal.tsx')),
  ...(await import('@dsh-test-source/packages/client/ui-primitives/src/Button.tsx')),
  ...(await import('@dsh-test-source/packages/client/ui-primitives/src/Toast.tsx')),
  ...(await import('@dsh-test-source/packages/client/ui-primitives/src/relative-time.ts')),
}))
globalThis.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} } as unknown as typeof ResizeObserver
Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value() { this.setAttribute('open', '') } })
function store<T>(value: T) { const listeners = new Set<() => void>(); return { getSnapshot: () => value, subscribe(listener: () => void) { listeners.add(listener); return () => { listeners.delete(listener) } }, set(next: T) { value = next; for (const listener of listeners) listener() } } }
const owned = { workspaceId: 'C', title: '算子项目', path: '/cann', pluginId: 'ops-direct-invoke', sessionIds: ['C1'], sharedWithDeepSeek: false }
const wire = { mode: 'cannbot', workspaces: [owned], sessions: [{ sessionId: 'C1', workspaceId: 'C', pluginId: owned.pluginId, title: 'CANN会话' }] }
function fixture() {
  const workspaceList = store({ items: [{ workspaceId: 'D', title: '历史项目', path: '/dsh', sessionIds: ['D1'] }, { workspaceId: 'EMPTY', title: '历史空目录', path: '/old-empty', sessionIds: [] }, owned], archivedSessionIds: ['ARCHIVED'], phase: 'ready', state: 'idle' })
  const sessionList = store({ ids: ['D1', 'C1'], byId: { D1: { id: 'D1', title: '历史会话', updatedAt: 2, retainedBy: { mainView: 1 } }, C1: { id: 'C1', title: 'CANN会话', retainedBy: {}, updatedAt: 1 }, SUB: { id: 'SUB', title: '隐藏子会话', origin: 'subagent', retainedBy: {}, updatedAt: 3 }, ARCHIVED: { id: 'ARCHIVED', title: '已归档', retainedBy: {}, updatedAt: 4 } } })
  const panelInfo = store({ activePanelId: null as string | null })
  const ctx = {
    workspaces: { list: workspaceList }, sessions: { list: sessionList },
    layout: { panelInfo, selectPanel: vi.fn((activePanelId: string | null) => panelInfo.set({ activePanelId })), beginNavigation: vi.fn(() => new AbortController().signal), toggleSidebar: vi.fn() },
    uiWorkspace: { startSession: vi.fn(), openSession: vi.fn(() => panelInfo.set({ activePanelId: null })), pickDirectory: vi.fn(async () => '/workspace/empty'), listDirectory: vi.fn(async () => ({ path: '/empty', crumbs: [], entries: [], truncated: false })), createDirectory: vi.fn(async () => '/empty/new') },
    slots: { entriesOfSlot: () => [{ options: { id: 'plugins', label: '插件' } }, { options: { id: 'cannbot-dsh-workbench', label: 'CANNBot工作台' } }], subscribe: () => () => {} },
    get: () => undefined,
  } as unknown as Context
  const remoteState = store({ servers: [{ id: 'S', label: 'DevEnv950', alias: 'DevEnv950', connected: false }], busy: false, error: '', progress: [], syncLogin: true, revision: 0, target: null, status: 'idle', notice: '' } as RemoteSnapshot)
  const remote = { ...remoteState, start: () => () => {}, connect: vi.fn(async () => {}), disconnect: vi.fn(async () => {}), open: vi.fn(async target => { const previous = remoteState.getSnapshot(); remoteState.set({ ...previous, target, selectedServerId: target.serverId, servers: previous.servers.map(server => server.id === target.serverId ? { ...server, connected: true } : server) }) }), getTree: vi.fn(async () => ({ workspaces: [{ ...owned, workspaceId: 'REMOTE', title: '远端项目', sessionIds: ['R1'] }], sessions: [{ id: 'R1', workspaceId: 'REMOTE', title: '远端会话' }] })), showConnections: vi.fn(), returnLocal: vi.fn(), dispose: vi.fn() } as RemoteClient
  const contentState = { workflows: WORKFLOWS.map(item => ({ id: item.id, title: item.id })), status: undefined }
  const content = { getSnapshot: () => contentState, subscribe: () => () => {} } as ContentStore
  const fetch = vi.fn(async (_: unknown, init?: RequestInit) => new Response(JSON.stringify(init?.method === 'POST' ? { workspace: owned } : wire)))
  vi.stubGlobal('fetch', fetch)
  const modes = createWorkspaceModes(ctx)
  vi.mocked(remote.returnLocal).mockImplementation(() => { modes.returnLocal() })
  return { ctx, remote, remoteState, content, modes, fetch, workspaceList, sessionList, panelInfo }
}
beforeEach(() => { localStorage.clear(); history.replaceState(null, '', '/') })
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals() })

describe('native public sidebar controls', () => {

  it('renames a workspace through the native API and confirms removal without deleting files', async () => {
    const f = fixture(); await f.modes.refresh(); f.modes.setMode('cannbot')
    f.modes.selectWorkspace('C')
    const refresh = vi.spyOn(f.modes, 'refreshAfterOperation').mockResolvedValue()
    const rename = vi.fn(async (_: string, title: string) => f.workspaceList.set({ ...f.workspaceList.getSnapshot(), items: f.workspaceList.getSnapshot().items.map(item => item.workspaceId === 'C' ? { ...item, title } : item) }))
    const remove = vi.fn(async () => f.workspaceList.set({ ...f.workspaceList.getSnapshot(), items: f.workspaceList.getSnapshot().items.filter(item => item.workspaceId !== 'C') }))
    Object.assign(f.ctx.workspaces, { rename, delete: remove })
    render(<ModeWorkspaceTree {...f} />)
    fireEvent.click(screen.getByRole('button', { name: '算子项目的工作区操作' })); fireEvent.click(screen.getByRole('menuitem', { name: '重命名' }))
    fireEvent.change(screen.getByRole('textbox', { name: '工作区名称' }), { target: { value: '算子新名称' } }); fireEvent.click(screen.getByRole('button', { name: '重命名' }))
    await waitFor(() => expect(rename).toHaveBeenCalledWith('C', '算子新名称'))
    await screen.findByRole('button', { name: 'ops-direct-invoke: 算子新名称' })
    fireEvent.click(screen.getByRole('button', { name: '算子新名称的工作区操作' })); fireEvent.click(screen.getByRole('menuitem', { name: '删除工作区' }))
    expect(screen.getByText(/文件夹与会话记录会保留/)).toBeTruthy(); expect(remove).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: '取消' })); expect(remove).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: '算子新名称的工作区操作' })); fireEvent.click(screen.getByRole('menuitem', { name: '删除工作区' })); fireEvent.click(screen.getByRole('button', { name: '删除工作区' }))
    await waitFor(() => expect(remove).toHaveBeenCalledWith('C'))
    await waitFor(() => expect(screen.queryByRole('button', { name: 'CANN会话' })).toBeNull())
    expect(screen.queryByRole('button', { name: '未分组' })).toBeNull()
    expect(refresh).toHaveBeenCalledTimes(2); expect(f.modes.getSnapshot().selectedWorkspaceId).toBe(''); expect(f.panelInfo.getSnapshot().activePanelId).toBe('cannbot-dsh-workbench'); expect(f.ctx.uiWorkspace.openSession).not.toHaveBeenCalled(); f.modes.dispose()
  })

  it('requires stopping confirmation for active sessions and restores archived sessions from their workspace', async () => {
    const f = fixture(); await f.modes.refresh(); f.modes.setMode('cannbot'); vi.spyOn(f.modes, 'refreshAfterOperation').mockResolvedValue()
    const archive = vi.fn(async (_id: string, options?: { stopActivity?: boolean }) => {
      if (!options?.stopActivity) throw Object.assign(Error('running'), { name: 'WorkspaceArchiveError', rpcError: { code: 'workspace/session-active', details: { activity: [{ kind: 'turn' }, { kind: 'job', items: [{ id: 'J', label: '编译任务' }] }] } } })
      f.workspaceList.set({ ...f.workspaceList.getSnapshot(), archivedSessionIds: ['C1'] })
    })
    const restore = vi.fn(async () => f.workspaceList.set({ ...f.workspaceList.getSnapshot(), archivedSessionIds: [] }))
    Object.assign(f.ctx.uiWorkspace, { archiveSession: archive, unarchiveSession: restore })
    render(<ModeWorkspaceTree {...f} />)
    const requestArchive = () => { fireEvent.click(screen.getByRole('button', { name: 'CANN会话的会话操作' })); fireEvent.click(screen.getByRole('menuitem', { name: '归档会话' })) }
    requestArchive(); await screen.findByRole('dialog', { name: '停止并归档此会话？' }); expect(screen.getByText(/编译任务/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '取消' })); expect(archive).toHaveBeenCalledTimes(1); expect(screen.getByRole('button', { name: 'CANN会话' })).toBeTruthy()
    requestArchive(); await screen.findByRole('dialog', { name: '停止并归档此会话？' }); fireEvent.click(screen.getByRole('button', { name: '停止并归档' }))
    await waitFor(() => expect(archive).toHaveBeenLastCalledWith('C1', { stopActivity: true })); await waitFor(() => expect(screen.queryByRole('button', { name: 'CANN会话' })).toBeNull())
    fireEvent.click(screen.getByRole('button', { name: '视图选项' })); fireEvent.click(screen.getByRole('menuitem', { name: '仅显示已归档' }))
    expect(screen.getByRole('button', { name: 'CANN会话' })).toHaveProperty('disabled', false); fireEvent.click(screen.getByRole('button', { name: 'CANN会话' })); expect(screen.getByText('已归档对话暂时无法查看，请取消归档后查看')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'CANN会话的会话操作' })); expect(screen.queryByRole('menuitem', { name: '置顶会话' })).toBeNull(); fireEvent.click(screen.getByRole('menuitem', { name: '取消归档' }))
    await waitFor(() => expect(restore).toHaveBeenCalledWith('C1')); fireEvent.click(screen.getByRole('button', { name: '视图选项' })); fireEvent.click(screen.getByRole('menuitem', { name: '隐藏已归档' })); expect(screen.getByRole('button', { name: 'CANN会话' })).toHaveProperty('disabled', false)
    f.modes.dispose()
  })

  it('edits and clears an offline server remark without connecting or changing its SSH alias', async () => {
    const f = fixture(); await f.modes.refresh(); f.modes.setMode('cannbot')
    const rename = vi.fn(async (id: string, label: string) => f.remoteState.set({ ...f.remoteState.getSnapshot(), servers: f.remoteState.getSnapshot().servers.map(server => server.id === id ? { ...server, label } : server) }))
    Object.assign(f.remote, { renameServer: rename })
    render(<ModeWorkspaceTree {...f} management />)
    fireEvent.click(screen.getByRole('button', { name: 'DevEnv950的服务器操作' })); fireEvent.click(screen.getByRole('menuitem', { name: '编辑备注' }))
    const input = screen.getByRole('textbox', { name: '服务器备注' }); expect(input.getAttribute('maxlength')).toBe('120')
    fireEvent.change(input, { target: { value: '开发机' } }); fireEvent.click(screen.getByRole('button', { name: '保存' }))
    await screen.findByRole('button', { name: '开发机的服务器操作' }); expect(rename).toHaveBeenCalledWith('S', '开发机')
    fireEvent.click(screen.getByRole('button', { name: '开发机的服务器操作' })); fireEvent.click(screen.getByRole('menuitem', { name: '编辑备注' }))
    fireEvent.change(screen.getByRole('textbox', { name: '服务器备注' }), { target: { value: '' } }); fireEvent.click(screen.getByRole('button', { name: '保存' }))
    await screen.findByRole('button', { name: 'DevEnv950的服务器操作' }); expect(rename).toHaveBeenLastCalledWith('S', '')
    expect(f.remote.open).not.toHaveBeenCalled(); expect(f.remote.connect).not.toHaveBeenCalled(); expect(f.remoteState.getSnapshot().servers[0]?.alias).toBe('DevEnv950'); f.modes.dispose()
  })



it('uses remote pin, stop-and-archive and restore operations with the same native menus', async () => {
  const f = fixture(); await f.modes.refresh(); f.modes.setMode('cannbot')
  f.remoteState.set({ ...f.remoteState.getSnapshot(), servers: f.remoteState.getSnapshot().servers.map(server => ({ ...server, connected: true })) })
  const initial = await f.remote.getTree('S')
  let current = { ...initial, sessions: [...initial.sessions.map(item => ({ ...item, updatedAt: 1, pinned: false, archived: false })), { id: 'R2', workspaceId: 'REMOTE', title: '更新的远端会话', updatedAt: 20, pinned: false, archived: false }] }
  vi.mocked(f.remote.getTree).mockImplementation(async () => current)
  const operate = vi.fn(async (_server, operation) => {
    if (operation.action === 'archive-session' && !operation.stopActivity) throw Object.assign(Error('active'), { code: 'workspace/session-active', activity: [{ kind: 'turn' }] })
    current = { ...current, sessions: current.sessions.map(item => item.id !== operation.sessionId ? item : { ...item, pinned: operation.action === 'pin-session', archived: operation.action === 'archive-session' }) }
    return { tree: current }
  })
  Object.assign(f.remote, { operate })
  const view = render(<ModeWorkspaceTree {...f} />); await screen.findByRole('button', { name: '远端会话的会话操作' })
  const titles = () => [...view.container.querySelectorAll('.cb-session')].map(item => item.textContent).filter(title => title?.includes('远端会话'))
  expect(titles()).toEqual(['更新的远端会话', '远端会话'])
  fireEvent.click(screen.getByRole('button', { name: '远端会话的会话操作' })); fireEvent.click(screen.getByRole('menuitem', { name: '置顶会话' }))
  await waitFor(() => expect(titles()).toEqual(['远端会话', '更新的远端会话']))
  fireEvent.click(screen.getByRole('button', { name: '远端会话的会话操作' })); fireEvent.click(screen.getByRole('menuitem', { name: '归档会话' }))
  await screen.findByRole('dialog', { name: '停止并归档此会话？' }); expect(operate).toHaveBeenLastCalledWith('S', { action: 'archive-session', sessionId: 'R1' })
  fireEvent.click(screen.getByRole('button', { name: '停止并归档' })); await waitFor(() => expect(screen.queryByRole('button', { name: '远端会话的会话操作' })).toBeNull())
  expect(operate).toHaveBeenLastCalledWith('S', { action: 'archive-session', sessionId: 'R1', stopActivity: true })
  fireEvent.click(screen.getByRole('button', { name: '视图选项' })); fireEvent.click(screen.getByRole('menuitem', { name: '仅显示已归档' }))
  expect(screen.getByRole('button', { name: '远端会话' })).toHaveProperty('disabled', false); fireEvent.click(screen.getByRole('button', { name: '远端会话' })); expect(screen.getByText('已归档对话暂时无法查看，请取消归档后查看')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: '远端会话的会话操作' })); fireEvent.click(screen.getByRole('menuitem', { name: '取消归档' }))
  await waitFor(() => expect(operate).toHaveBeenLastCalledWith('S', { action: 'unarchive-session', sessionId: 'R1' }))
  fireEvent.click(screen.getByRole('button', { name: '视图选项' })); fireEvent.click(screen.getByRole('menuitem', { name: '隐藏已归档' })); expect(screen.getByRole('button', { name: '远端会话' })).toHaveProperty('disabled', false)
  expect(f.remote.open).not.toHaveBeenCalled(); f.modes.dispose()
})


it('replaces a committed rename confirmation with read-only refresh and closes only after new data', async () => {
  const f = fixture(); await f.modes.refresh(); f.modes.setMode('cannbot')
  f.remoteState.set({ ...f.remoteState.getSnapshot(), servers: f.remoteState.getSnapshot().servers.map(server => ({ ...server, connected: true })) })
  const first = await f.remote.getTree('S'), next = { ...first, workspaces: first.workspaces.map(item => ({ ...item, title: '新远端名称' })) }
  const operate = vi.fn(async () => { throw Object.assign(Error('重命名已完成，请刷新列表。'), { committed: true }) }); Object.assign(f.remote, { operate })
  render(<ModeWorkspaceTree {...f} />); await screen.findByRole('button', { name: '远端项目的工作区操作' })
  fireEvent.click(screen.getByRole('button', { name: '远端项目的工作区操作' })); fireEvent.click(screen.getByRole('menuitem', { name: '重命名' }))
  fireEvent.change(screen.getByRole('textbox', { name: '工作区名称' }), { target: { value: '新远端名称' } }); fireEvent.click(screen.getByRole('button', { name: '重命名' })); await screen.findByText('重命名已完成，请刷新列表。')
  expect(screen.queryByRole('button', { name: '重命名' })).toBeNull(); expect(screen.getByRole('textbox', { name: '工作区名称' })).toHaveProperty('disabled', true)
  let finish!: (value: typeof next) => void
  vi.mocked(f.remote.getTree).mockImplementationOnce(() => new Promise(resolve => { finish = resolve })); fireEvent.click(screen.getByRole('button', { name: '刷新列表' }))
  expect(screen.getByRole('dialog', { name: '重命名工作区' })).toBeTruthy()
  await act(async () => { finish(next); await Promise.resolve() })
  await waitFor(() => expect(screen.queryByRole('dialog', { name: '重命名工作区' })).toBeNull())
  expect(screen.getByRole('button', { name: '新远端名称的工作区操作' })).toBeTruthy(); expect(operate).toHaveBeenCalledOnce(); f.modes.dispose()
})

  it('uses native action order and keeps project operations in hover clusters', async () => {
    const f = fixture(); await f.modes.refresh(); f.modes.setMode('cannbot')
    f.workspaceList.set({ ...f.workspaceList.getSnapshot(), pinnedSessionIds: ['C1'] })
    const view = render(<ModeWorkspaceTree {...f} />)
    const workspace = screen.getByRole('button', { name: 'ops-direct-invoke: 算子项目', exact: true })
    expect([...workspace.querySelectorAll('.cb-row-actions button')].map(button => button.getAttribute('aria-label'))).toEqual(['算子项目的工作区操作', '在 算子项目 中新建会话'])
    expect(workspace.querySelector('.cb-folder [data-testid="open-folder-icon"]')).toBeTruthy()
    expect(workspace.querySelector('.cb-chevron .cb-chevron-open')).toBeTruthy()
    expect(screen.getByRole('button', { name: '添加工作区' }).closest('.cb-heading-actions')).toBeTruthy()
    const row = view.container.querySelector('[data-session-id="C1"]')!
    expect([...row.querySelectorAll('.cb-row-actions button')].map(button => button.getAttribute('aria-label'))).toEqual(['CANN会话的会话操作', '归档会话', '取消置顶'])
    expect(row.querySelector('.cb-session-pin')?.previousElementSibling?.className).toBe('cb-session-time')
    expect(row.querySelector('.cb-session-title .cb-session-pin')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: '算子项目的工作区操作' }))
    expect(screen.getAllByRole('menuitem').map(item => item.textContent)).toEqual(['重命名', '切换工作流', '删除工作区'])
    expect(screen.queryByRole('separator')).toBeNull()
    f.modes.dispose()
  })
})
