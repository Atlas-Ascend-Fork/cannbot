// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ReactNode } from 'react'
import type { Context } from '@deepseek-ai/cordis'
import { ModeBrandMark, ModeWorkspaceTree, ModeWorkspaceCreation } from '../src/client/ModeSidebar.tsx'
import { BoundWorkspaceWorkflow } from '../src/client/BoundWorkspaceWorkflow.tsx'
import { createWorkspaceModes } from '../src/client/workspace-modes.ts'
import { Workbench } from '../src/client/Workbench.tsx'
import type { ContentStore } from '../src/client/content-store.ts'
import type { RemoteClient, RemoteSnapshot } from '../src/client/remote/types.ts'
import type { WorkflowSelection } from '../src/client/workflow-selection.ts'
import { WORKFLOWS } from '../src/workflows.ts'

vi.mock('@xterm/xterm', () => ({ Terminal: class { options = {}; open() {} onData() { return { dispose() {} } } write() {} writeln() {} reset() {} dispose() {} } }))

vi.mock('@deepseek-ai/dsh-client-ui-primitives', () => ({
  // Isolate the documented public contracts. The validation suite also runs
  // these interactions against the actual upstream components and native shell.
  DisclosureRow: ({ title, open, expandable, onToggle, headerAccessory, children, className, rowClassName, icon }: { title: string; open: boolean; expandable: boolean; onToggle(): void; headerAccessory: ReactNode; children: ReactNode; className: string; rowClassName: string; icon: ReactNode }) => <div className={className}><div data-disclosure-header><div className={rowClassName} data-disclosure-row role={expandable ? 'button' : undefined} tabIndex={expandable ? 0 : undefined} aria-expanded={expandable ? open : undefined} onClick={expandable ? onToggle : undefined} onKeyDown={event => { if (expandable && (event.key === 'Enter' || event.key === ' ')) { event.preventDefault(); onToggle() } }}>{icon}{title}</div>{headerAccessory}</div>{open && children}</div>,
  BrandWordmark: () => <svg data-testid="full-deepseek-brand" />,
  FishLogo: () => <svg data-testid="deepseek-logo" />, IconFolderCloseRegular: () => <svg data-testid="folder-icon" />, IconNewChatOutlineRegular: () => <svg />,
  IconFollowsystemOutlineRegular: () => <svg data-testid="computer-icon" />,
  IconFolderOpenRegular: () => <svg data-testid="open-folder-icon" />, IconTriangleRightFillRegular: (props: { className?: string }) => <svg data-testid="triangle-icon" {...props} />,
  IconArchiveOffOutlineRegular: () => <svg />, IconArchiveCheckOutlineRegular: () => <svg />, IconQueueOutlineRegular: () => <svg />, IconSlidersTwoOutlineRegular: () => <svg />, IconWarningOutlineRegular: () => <svg />,
  StateDot: ({ state }: { state: string }) => <svg data-state={state} />,

  IconEditOutlineRegular: () => <svg />, IconEllipsisOutlineRegular: () => <svg />, IconPinFillRegular: () => <svg />, IconPinOutlineRegular: () => <svg />,
  IconArchiveOutlineRegular: () => <svg />, IconUnarchiveOutlineRegular: () => <svg />, IconBranchOutlineRegular: () => <svg />, IconCopyOutlineRegular: () => <svg />, IconTrashOutlineRegular: () => <svg />,

  IconLinkOutlineRegular: () => <svg />, IconCheckOutlineRegular: () => <svg />, IconRefreshOutlineRegular: () => <svg />,
  IconChevronDownOutlineRegular: () => <svg />, IconPlusOutlineRegular: () => <svg />, IconProjectAddOutlineRegular: () => <svg />, IconSendOutlineRegular: () => <svg />,
  Tooltip: ({ children }: { children: ReactNode }) => <>{children}</>,
  MenuItemButton: ({ children, onSelect, disabled }: { children: ReactNode; onSelect(): void; disabled?: boolean }) => <button role="menuitem" disabled={disabled} onClick={onSelect}>{children}</button>,
  Button: ({ children, variant: _variant, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: string }) => <button {...props}>{children}</button>,
  Modal: ({ open, title, description, children, footer, onClose }: { open: boolean; title: string; description?: string; children?: ReactNode; footer?: ReactNode; onClose(): void }) => open ? <div role="dialog" aria-label={title}><h2>{title}</h2><p>{description}</p>{children}{footer}<button aria-label="关闭" onClick={onClose}>×</button></div> : null,
  relativeTime: () => ({ unit: 'minutes', n: 5 }),
  Toast: ({ text, actions }: { text: string; actions?: { label: string; onClick(): void }[] }) => <div role="status">{text}{actions?.map(action => <button key={action.label} onClick={action.onClick}>{action.label}</button>)}</div>,
  Menu: ({ anchor, open, children, items = [], onSelect }: { anchor: ReactNode; open: boolean; children: ReactNode; items?: { id: string; type?: string; text?: string; label?: ReactNode }[]; onSelect?(id: string): void }) => <>{anchor}{open && <div role="menu">{items.map(item => item.type ? <span key={item.id}>{item.text}</span> : <button key={item.id} role="menuitem" onClick={() => onSelect?.(item.id)}>{item.label}</button>)}{children}</div>}</>,
}))
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
    uiWorkspace: { startSession: vi.fn(), openSession: vi.fn(() => panelInfo.set({ activePanelId: null })), pickDirectory: vi.fn(async () => 'D:\\workspace\\empty'), listDirectory: vi.fn(async () => ({ path: '/empty', crumbs: [], entries: [], truncated: false })), createDirectory: vi.fn(async () => '/empty/new') },
    slots: { entriesOfSlot: () => [{ options: { id: 'plugins', label: '插件' } }, { options: { id: 'cannbot-dsh-workbench', label: 'CANNBot工作台' } }], subscribe: () => () => {} },
    get: () => undefined,
  } as unknown as Context
  const remoteState = store({ servers: [{ id: 'S', label: 'DevEnv950', alias: 'DevEnv950', connected: false }], busy: false, error: '', progress: [], syncLogin: true, revision: 0, target: null, status: 'idle', notice: '' } as RemoteSnapshot)
  const remote = { ...remoteState, start: () => () => {}, connect: vi.fn(async id => { const previous = remoteState.getSnapshot(); remoteState.set({ ...previous, servers: previous.servers.map(server => server.id === id ? { ...server, connected: true } : server) }) }), disconnect: vi.fn(async () => {}), open: vi.fn(async target => { const previous = remoteState.getSnapshot(); remoteState.set({ ...previous, target, selectedServerId: target.serverId, servers: previous.servers.map(server => server.id === target.serverId ? { ...server, connected: true } : server) }) }), getTree: vi.fn(async () => ({ workspaces: [{ ...owned, workspaceId: 'REMOTE', title: '远端项目', sessionIds: ['R1'] }], sessions: [{ id: 'R1', workspaceId: 'REMOTE', title: '远端会话' }] })), showConnections: vi.fn(), returnLocal: vi.fn(), dispose: vi.fn() } as RemoteClient
  const contentState = { workflows: WORKFLOWS.map(item => ({ id: item.id, title: item.id })), status: undefined }
  const content = { getSnapshot: () => contentState, subscribe: () => () => {} } as ContentStore
  const fetch = vi.fn(async (_: unknown, init?: RequestInit) => new Response(JSON.stringify(init?.method === 'POST' ? (JSON.parse(String(init.body)).action === 'browse-directory' ? { path: '/', crumbs: [{ name: '/', path: '/' }], entries: [], truncated: false } : { workspace: owned }) : wire)))
  vi.stubGlobal('fetch', fetch)
  const modes = createWorkspaceModes(ctx)
  vi.mocked(remote.returnLocal).mockImplementation(() => { modes.returnLocal() })
  return { ctx, remote, remoteState, content, modes, fetch, workspaceList, sessionList, panelInfo }
}
beforeEach(() => { localStorage.clear(); history.replaceState(null, '', '/') })
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals() })

describe('mode sidebar', () => {
  it('cancels an active setup and ignores its late completion', async () => {
    const f = fixture(); await f.modes.refresh(); f.modes.setCreating(true)
    let finish!: () => void
    vi.mocked(f.remote.connect).mockImplementation(() => new Promise(resolve => { finish = resolve }))
    f.remote.cancelConnect = vi.fn(async () => {})
    render(<ModeWorkspaceCreation {...f} />)
    fireEvent.change(screen.getByRole('combobox', { name: '服务器' }), { target: { value: 'S' } })
    fireEvent.click(screen.getByRole('button', { name: '确认' }))
    fireEvent.click(within(screen.getByRole('dialog', { name: '服务器连接与安装' })).getByRole('button', { name: '取消' }))
    await waitFor(() => expect(screen.queryByRole('dialog', { name: '服务器连接与安装' })).toBeNull())
    expect(f.remote.cancelConnect).toHaveBeenCalledExactlyOnceWith('S')
    await act(async () => finish())
    expect(screen.getByRole('combobox', { name: '服务器' })).toHaveProperty('value', '__select_server__')
    expect(f.remote.open).not.toHaveBeenCalled(); f.modes.dispose()
  })
  it('browses in one path field, completes typed paths with Tab and confirms outside', async () => {
    const f = fixture(); await f.modes.refresh(); f.modes.setCreating(true)
    f.fetch.mockImplementation(async (_url, init) => {
      const request = init?.body ? JSON.parse(String(init.body)) : {}
      return Response.json(request.action === 'browse-directory' ? { path: request.path === '/t' ? '/' : request.path || '/',
        partial: request.path === '/t', crumbs: [{ name: '/', path: '/' }], entries: request.path === '/tmp' ? [] : [{ name: 'tmp', path: '/tmp' }], truncated: false } : wire)
    })
    render(<ModeWorkspaceCreation {...f} />)
    const path = screen.getByRole('textbox', { name: '父目录' })
    await waitFor(() => expect(path).toHaveProperty('value', '/'))
    expect(screen.queryByRole('button', { name: '打开', exact: true })).toBeNull()
    expect(screen.queryByRole('button', { name: '浏览', exact: true })).toBeNull()
    fireEvent.click(path); fireEvent.click(screen.getByRole('button', { name: 'tmp' }))
    await waitFor(() => expect(path).toHaveProperty('value', '/tmp'))
    fireEvent.click(screen.getByRole('button', { name: '确认', exact: true }))
    expect(path.getAttribute('aria-expanded')).toBe('false')
    fireEvent.change(path, { target: { value: '/t' } })
    await screen.findByRole('button', { name: 'tmp' })
    fireEvent.keyDown(path, { key: 'Tab' })
    await waitFor(() => expect(path).toHaveProperty('value', '/tmp'))
    fireEvent.pointerDown(screen.getByRole('textbox', { name: '工作区名' }))
    expect(path.getAttribute('aria-expanded')).toBe('false'); f.modes.dispose()
  })
  it('hides environment notice once connected and opens the created remote workspace with permission recommendation', async () => {
    const f = fixture(); await f.modes.refresh(); f.modes.setCreating(true)
    await f.remote.connect('S')
    f.fetch.mockImplementation(async (_url, init) => { const body = init?.body && JSON.parse(String(init.body)); return Response.json(body?.action === 'start-initialization' ? { jobId: 'job', phase: 'ready', output: '', offset: 0, nextOffset: 0, inputSequence: 0, interactive: false, result: { workspace: owned } } : { path: '/', crumbs: [], entries: [], truncated: false }) })
    render(<ModeWorkspaceCreation {...f} />)
    fireEvent.change(screen.getByRole('combobox', { name: '工作流' }), { target: { value: 'ops-direct-invoke' } })
    fireEvent.change(screen.getByRole('combobox', { name: '服务器' }), { target: { value: 'S' } })
    await waitFor(() => expect(screen.getByRole('textbox', { name: '父目录' })).toHaveProperty('value', '/'))
    expect(screen.queryByText('本工作流需要在连接了NPU环境的Linux服务器上创建')).toBeNull()
    fireEvent.change(screen.getByRole('textbox', { name: '工作区名' }), { target: { value: 'new-project' } })
    await waitFor(() => expect(screen.getByRole('button', { name: '创建工作区' })).toHaveProperty('disabled', false))
    fireEvent.click(screen.getByRole('button', { name: '创建工作区' }))
    await waitFor(() => expect(f.remote.open).toHaveBeenCalledWith({ serverId: 'S', workspaceId: owned.workspaceId, recommendPermissions: true }))
    f.modes.dispose()
  })
  it('confirms a disconnected selection, streams setup logs and returns to the draft on success', async () => {
    const f = fixture(); await f.modes.refresh(); f.modes.setCreating(true)
    let finish!: () => void
    vi.mocked(f.remote.connect).mockImplementation(() => new Promise(resolve => { finish = resolve }))
    render(<ModeWorkspaceCreation {...f} />)
    fireEvent.change(screen.getByRole('textbox', { name: '工作区名' }), { target: { value: 'draft' } })
    expect(screen.getByRole('option', { name: 'DevEnv950，未连接' }).textContent).toBe('🔴 DevEnv950')
    fireEvent.change(screen.getByRole('combobox', { name: '服务器' }), { target: { value: 'S' } })
    expect(screen.getByText('服务器还未连接，是否立即连接？')).toBeTruthy()
    expect(f.remote.connect).not.toHaveBeenCalled()
    expect(screen.queryByRole('button', { name: '连接服务器' })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: '确认' }))
    expect(f.remote.connect).toHaveBeenCalledOnce()
    expect(screen.getByRole('dialog', { name: '服务器连接与安装' })).toBeTruthy()
    act(() => f.remoteState.set({ ...f.remoteState.getSnapshot(), busy: true, progress: ['安装 DSH', '安装 CANNBot'] }))
    expect(screen.getByRole('log').textContent).toContain('安装 CANNBot')
    await act(async () => { f.remoteState.set({ ...f.remoteState.getSnapshot(), busy: false, servers: [{ id: 'S', alias: 'DevEnv950', label: 'DevEnv950', connected: true }] }); finish() })
    await waitFor(() => expect(screen.queryByRole('dialog', { name: '服务器连接与安装' })).toBeNull())
    expect(screen.getByRole('option', { name: 'DevEnv950，已连接' }).textContent).toBe('🟢 DevEnv950')
    expect(screen.getByRole('textbox', { name: '工作区名' })).toHaveProperty('value', 'draft')
    await waitFor(() => expect(screen.getByRole('textbox', { name: '父目录' })).toHaveProperty('value', '/'))
    expect(f.remote.open).not.toHaveBeenCalled(); f.modes.dispose()
  })
  it('cancels without connecting and keeps failed setup visible for retry', async () => {
    const f = fixture(); await f.modes.refresh(); f.modes.setCreating(true)
    render(<ModeWorkspaceCreation {...f} />)
    const choose = () => fireEvent.change(screen.getByRole('combobox', { name: '服务器' }), { target: { value: 'S' } })
    choose(); fireEvent.click(within(screen.getByRole('dialog', { name: '连接服务器' })).getByRole('button', { name: '取消' }))
    expect(f.remote.connect).not.toHaveBeenCalled()
    expect(screen.getByRole('combobox', { name: '服务器' })).toHaveProperty('value', '__select_server__')
    vi.mocked(f.remote.connect).mockRejectedValueOnce(new Error('测试连接失败'))
    choose(); fireEvent.click(screen.getByRole('button', { name: '确认' }))
    await screen.findByText('测试连接失败')
    expect(screen.getByRole('dialog', { name: '服务器连接与安装' })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '重试' }))
    await waitFor(() => expect(screen.queryByRole('dialog', { name: '服务器连接与安装' })).toBeNull())
    expect(f.remote.connect).toHaveBeenCalledTimes(2); f.modes.dispose()
  })

  it('adds a server from the location field without discarding the workspace draft', async () => {
    const f = fixture(); await f.modes.refresh(); f.modes.setCreating(true)
    render(<ModeWorkspaceCreation {...f} />)
    await screen.findByDisplayValue('/')
    fireEvent.change(screen.getByRole('textbox', { name: '工作区名' }), { target: { value: 'my-project' } })
    const location = screen.getByRole('combobox', { name: '服务器' })
    fireEvent.change(location, { target: { value: '__add_server__' } })
    expect(f.remote.showConnections).toHaveBeenCalledOnce()
    expect(location).toHaveProperty('value', '')
    const resume = vi.mocked(f.remote.showConnections).mock.calls[0][0]!
    act(() => {
      f.remoteState.set({ ...f.remoteState.getSnapshot(), servers: [...f.remoteState.getSnapshot().servers, { id: 'NEW', alias: 'worker', label: 'Worker', connected: true }] })
      resume('NEW')
    })
    await waitFor(() => expect(location).toHaveProperty('value', 'NEW'))
    expect(screen.getByRole('textbox', { name: '工作区名' })).toHaveProperty('value', 'my-project')
    expect(screen.getByRole('combobox', { name: '工作流' })).toHaveProperty('value', '')
    expect(f.remote.open).not.toHaveBeenCalled()
    f.modes.dispose()
  })

  it('requires a name and explicit type and creates a new local blank folder at the root', async () => {
    const f = fixture(); await f.modes.refresh(); f.modes.setMode('cannbot'); f.modes.setCreating(true)
    render(<ModeWorkspaceCreation {...f} />)
    await waitFor(() => expect(screen.getByRole('textbox', { name: '父目录' })).toHaveProperty('value', '/'))
    expect(screen.getByRole('combobox', { name: '工作流' })).toHaveProperty('value', '')
    expect(screen.getByRole('button', { name: '创建工作区' })).toHaveProperty('disabled', true)
    fireEvent.change(screen.getByRole('combobox', { name: '工作流' }), { target: { value: 'general' } })
    expect(screen.getByRole('button', { name: '创建工作区' })).toHaveProperty('disabled', true)
    fireEvent.change(screen.getByRole('textbox', { name: '工作区名' }), { target: { value: 'new-project' } })
    fireEvent.click(screen.getByRole('button', { name: '创建工作区' }))
    await waitFor(() => expect(f.fetch.mock.calls.map(([, init]) => init?.body && JSON.parse(String(init.body))).some(value => value?.action === 'create-folder' && value.parent === '/' && value.name === 'new-project' && value.pluginId === 'general' && value.requestId)).toBe(true))
    expect(f.ctx.uiWorkspace.createDirectory).not.toHaveBeenCalled(); f.modes.dispose()
  })
  it('clears local selection for workflows and omits blank workspace prefixes', async () => {
    const f = fixture(); await f.modes.refresh(); f.modes.setMode('cannbot'); f.modes.setCreating(true)
    const view = render(<ModeWorkspaceCreation {...f} />)
    fireEvent.change(screen.getByRole('combobox', { name: '工作流' }), { target: { value: 'ops-direct-invoke' } })
    expect(screen.getByRole('alert').textContent).toBe('本工作流需要在连接了NPU环境的Linux服务器上创建')
    expect(screen.getByRole('combobox', { name: '服务器' }).closest('label')?.nextElementSibling).toBe(screen.getByRole('alert'))
    expect(screen.getByRole('combobox', { name: '工作流' })).toHaveProperty('value', 'ops-direct-invoke')
    expect(screen.getByRole('combobox', { name: '服务器' })).toHaveProperty('value', '__select_server__')
    view.unmount()
    f.fetch.mockResolvedValue(Response.json({ ...wire, workspaces: [{ ...owned, pluginId: 'general' }] }))
    await f.modes.refresh(); render(<ModeWorkspaceTree {...f} />)
    expect(screen.getByRole('button', { name: '算子项目', exact: true })).toBeTruthy()
    expect(screen.queryByText(/general:|空白工作区:/)).toBeNull(); f.modes.dispose()
  })
  it('hides workspace-less sessions on both local and connected remote lists', async () => {
    const f = fixture()
    f.fetch.mockResolvedValue(new Response(JSON.stringify({ ...wire, workspaces: [], sessions: wire.sessions })))
    await f.modes.refresh(); f.modes.setMode('cannbot')
    f.remoteState.set({ ...f.remoteState.getSnapshot(), servers: [{ id: 'S', alias: 'DevEnv950', label: 'DevEnv950', connected: true }] })
    vi.mocked(f.remote.getTree).mockResolvedValue({ workspaces: [], sessions: [{ id: 'orphan', workspaceId: 'missing', title: '远端孤立会话' }] })
    const view = render(<ModeWorkspaceTree {...f} />)
    await waitFor(() => expect(f.remote.getTree).toHaveBeenCalled())
    await waitFor(() => expect(screen.queryByText('正在加载 DevEnv950 的工作区…')).toBeNull())
    expect(screen.queryByText('未分组')).toBeNull()
    expect(screen.queryByRole('button', { name: 'CANN会话' })).toBeNull()
    expect(screen.queryByRole('button', { name: '远端孤立会话' })).toBeNull()
    expect(view.container.querySelectorAll('.cb-session')).toHaveLength(0)
    f.modes.dispose()
  })
  it('binds the read-only hero label to its workspace instead of a retained previous session', async () => {
    const f = fixture()
    const nextWorkspace = { ...owned, workspaceId: 'NEXT', title: '注册算子项目', path: '/next', pluginId: 'ops-registry-invoke', sessionIds: [] }
    vi.mocked(f.fetch).mockImplementation(async () => new Response(JSON.stringify({ ...wire, workspaces: [owned, nextWorkspace] })))
    await f.modes.refresh(); f.modes.setMode('cannbot')
    f.modes.openSession('C1'); f.modes.selectWorkspace('NEXT')
    expect(f.modes.getSnapshot()).toMatchObject({ activeSessionId: 'C1', selectedWorkspaceId: 'NEXT' })
    const view = render(<BoundWorkspaceWorkflow modes={f.modes} />)
    expect(screen.getByTitle('工作区工作流：ops-registry-invoke')).toBeTruthy()
    expect(screen.queryByText('ops-direct-invoke')).toBeNull()
    expect(screen.queryByRole('button')).toBeNull(); expect(screen.queryByRole('combobox')).toBeNull()
    view.rerender(<BoundWorkspaceWorkflow modes={f.modes} sessionId="C1" />)
    expect(screen.getByTitle('工作区工作流：ops-direct-invoke')).toBeTruthy()
    expect(screen.queryByText('ops-registry-invoke')).toBeNull()
    view.rerender(<BoundWorkspaceWorkflow modes={f.modes} sessionId="unknown-session" />)
    expect(view.container.childElementCount).toBe(0)
    f.modes.dispose()
  })
  it('uses a neutral return entry in native navigation without starting a session', async () => {
    localStorage.setItem('cannbot.ui.modes.v1', JSON.stringify({ mode: 'deepseek' }))
    const f = fixture(); await f.modes.refresh(); const brandStart = vi.fn(), onServers = vi.fn()
    const view = render(<div data-slot="sidebar"><div><div><button type="button" aria-label="品牌入口" onClick={brandStart}><span aria-hidden="true"><span data-slot="sidebar.brand.mark"><ModeBrandMark modes={f.modes} onServers={onServers} /></span><span data-slot="sidebar.brand.name">DeepSeek Harness</span></span></button></div><button aria-label="新会话" onClick={() => f.modes.newSession()}>新会话</button><nav aria-label="面板"><button><span data-slot="sidebar.panellist" />插件</button><button>自动化任务</button><button>更多</button></nav><span data-slot="sidebar.settings"><button>设置</button></span></div></div>)
    const switchMode = screen.getByRole('button', { name: 'CANNBot', exact: true }), create = screen.getByRole('button', { name: '新会话' }), nativePlugin = screen.getByRole('button', { name: '插件' })
    expect(switchMode.closest('nav')?.firstElementChild).toBe(switchMode.parentElement)
    expect(switchMode.parentElement?.nextElementSibling).toBe(nativePlugin)
    expect(switchMode.parentElement?.closest('button')).toBeNull(); expect(switchMode.closest('[aria-hidden="true"]')).toBeNull()
    expect(switchMode.title).toBe('切换到 CANNBot')
    expect(switchMode.textContent).toBe('CANNBot')
    expect(switchMode.querySelector('[data-cannbot-dsh-logo]')).toBeTruthy()
    expect(screen.getByRole('button', { name: '品牌入口' }).querySelector('[data-cannbot-dsh-logo]')).toBeNull()
    fireEvent.click(switchMode)
    expect(screen.getByRole('button', { name: '返回原生工作台', exact: true }).querySelector('svg')).toBeTruthy()
    expect(screen.getByRole('button', { name: '返回原生工作台', exact: true }).textContent).toBe('返回原生工作台')
    expect(screen.getByRole('button', { name: '返回原生工作台', exact: true }).title).toBe('返回原生工作台')
    expect(screen.queryByTestId('deepseek-logo')).toBeNull()
    expect(screen.getByRole('button', { name: '品牌入口' }).querySelector('[data-cannbot-dsh-logo]')).toBeTruthy()
    const servers = screen.getByRole('button', { name: '服务器', exact: true }); expect(servers.parentElement?.previousElementSibling?.textContent).toBe('更多')
    fireEvent.click(servers); expect(onServers).toHaveBeenCalledOnce(); expect(brandStart).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: '插件' })).toBe(nativePlugin)
    expect(screen.queryByRole('tablist')).toBeNull()
    fireEvent.click(create)
    expect(brandStart).not.toHaveBeenCalled()
    expect(f.ctx.layout.selectPanel).toHaveBeenLastCalledWith('cannbot-dsh-workbench')
    expect(screen.queryByRole('switch')).toBeNull(); expect(screen.queryByRole('button', { name: 'CANNBot工作台' })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: '返回原生工作台', exact: true }))
    expect(f.modes.getSnapshot().mode).toBe('deepseek'); expect(brandStart).not.toHaveBeenCalled(); expect(screen.queryByRole('button', { name: '服务器', exact: true })).toBeNull()
    expect(screen.getByRole('button', { name: '品牌入口' }).querySelector('[data-testid="deepseek-logo"]')).not.toBeNull()
    view.unmount(); expect(document.querySelector('[data-cannbot-mode-switch-host]')).toBeNull()
    f.modes.dispose()
  })
  it('waits for native panel navigation and restores one switch after its replacement', async () => {
    localStorage.setItem('cannbot.ui.modes.v1', JSON.stringify({ mode: 'deepseek' }))
    const f = fixture()
    const shell = (navigation: boolean, version = 0) => <div data-slot="sidebar"><span data-slot="sidebar.brand.mark"><ModeBrandMark modes={f.modes} /></span>{navigation && <nav key={version}><button><span data-slot="sidebar.panellist" />插件</button></nav>}</div>
    const view = render(shell(false))
    expect(screen.queryByRole('button', { name: 'CANNBot', exact: true })).toBeNull()
    view.rerender(shell(true))
    await screen.findByRole('button', { name: 'CANNBot', exact: true })
    view.rerender(shell(true, 1))
    await waitFor(() => expect(screen.getAllByRole('button', { name: 'CANNBot', exact: true })).toHaveLength(1))
    expect(view.container.querySelector('nav')?.firstElementChild?.hasAttribute('data-cannbot-mode-switch-host')).toBe(true)
    view.unmount(); f.modes.dispose()
  })
  it('renders no replacement workspace UI in DeepSeek mode, including the collapsed sidebar', async () => {
    localStorage.setItem('cannbot.ui.modes.v1', JSON.stringify({ mode: 'deepseek' }))
    const f = fixture()
    const view = render(<ModeWorkspaceTree {...f} />)
    expect(view.container.childElementCount).toBe(0)
    await act(() => f.modes.refresh())
    expect(view.container.childElementCount).toBe(0)
    view.rerender(<ModeWorkspaceTree {...f} wide={false} />)
    expect(view.container.childElementCount).toBe(0)
    expect(f.ctx.layout.toggleSidebar).not.toHaveBeenCalled()
    expect(f.remote.open).not.toHaveBeenCalled(); expect(f.remote.getTree).not.toHaveBeenCalled()
    f.modes.dispose()
  })
  it('waits for explicit CANN membership and excludes ordinary, archived and unowned subagent records', async () => {
    const f = fixture(); f.modes.setMode('cannbot')
    vi.mocked(f.fetch).mockResolvedValue(new Response(JSON.stringify({ ...wire, sessions: [
      ...wire.sessions, { sessionId: 'ARCHIVED', workspaceId: 'C', pluginId: owned.pluginId, title: '已归档', archived: true },
    ] })))
    render(<ModeWorkspaceTree {...f} />)
    expect(screen.queryByText('历史会话')).toBeNull(); expect(screen.queryByText('CANN会话')).toBeNull()
    expect(screen.getByText('正在加载工作区…')).toBeTruthy()
    await act(() => f.modes.refresh())
    expect(screen.getByText('CANN会话')).toBeTruthy(); expect(screen.getByText('ops-direct-invoke: 算子项目')).toBeTruthy()
    expect(screen.queryByText('ops-direct-invoke')).toBeNull()
    for (const title of ['历史会话', '历史项目', '历史空目录', '隐藏子会话', '已归档']) expect(screen.queryByText(title)).toBeNull()
    f.modes.dispose()
  })
  it('shows CANN projects without an added search field and removes its tree when switching to DeepSeek', async () => {
    const f = fixture(); await f.modes.refresh(); f.modes.setMode('cannbot')
    const view = render(<ModeWorkspaceTree {...f} />)
    expect(screen.getByText('CANN会话')).toBeTruthy()
    expect(screen.queryByRole('textbox')).toBeNull(); expect(screen.queryByRole('searchbox')).toBeNull()
    expect(screen.queryByRole('tablist')).toBeNull()
    act(() => f.modes.setMode('deepseek'))
    expect(view.container.childElementCount).toBe(0)
    f.modes.dispose()
  })
  it('clears the previous session highlight when returning to the CANNBot home panel', async () => {
    const f = fixture(); await f.modes.refresh(); f.modes.setMode('cannbot'); f.modes.openSession('C1')
    render(<ModeWorkspaceTree {...f} />)
    expect(screen.getByRole('button', { name: 'CANN会话', exact: true }).getAttribute('aria-current')).toBe('page')
    act(() => f.modes.newSession('C'))
    expect(screen.getByRole('button', { name: 'CANN会话', exact: true }).getAttribute('aria-current')).toBeNull()
    expect(screen.getByRole('button', { name: 'ops-direct-invoke: 算子项目', exact: true }).closest('.cb-project-selected')).toBeTruthy()
    f.modes.dispose()
  })
  it('manages connections separately and renders flat remote workspaces with a globe badge', async () => {
    const f = fixture(); await f.modes.refresh(); f.modes.setMode('cannbot')
    const view = render(<><ModeWorkspaceTree {...f} /><ModeWorkspaceTree {...f} management /></>)
    const server = screen.getByText('DevEnv950').closest('[data-disclosure-row]')!
    expect(server.querySelector('[data-testid="computer-icon"]')).toBeTruthy()
    fireEvent.click(server); fireEvent.keyDown(server, { key: 'Enter' })
    expect(server.getAttribute('aria-expanded')).toBeNull(); expect(f.remote.connect).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: '连接 DevEnv950' }))
    await screen.findByText('远端会话')
    expect(f.remote.connect).toHaveBeenCalledExactlyOnceWith('S'); expect(f.remote.open).not.toHaveBeenCalled()
    const workspace = screen.getByRole('button', { name: 'ops-direct-invoke: 远端项目' })
    expect(workspace.parentElement?.parentElement?.className).toBe('cb-workspace-list')
    expect(workspace.querySelector('[aria-label="远程工作区 · DevEnv950"] .cb-globe-badge')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '远端会话' }))
    await waitFor(() => expect(f.remote.open).toHaveBeenCalledWith({ serverId: 'S', workspaceId: 'REMOTE', sessionId: 'R1' }))
    fireEvent.click(screen.getByRole('button', { name: 'CANN会话' })); expect(f.remote.returnLocal).toHaveBeenCalledOnce()
    expect(f.remoteState.getSnapshot().servers[0].connected).toBe(true)
    expect(view.container.querySelectorAll('.cb-project-nested')).toHaveLength(0); f.modes.dispose()
  })
  it('never reruns connection/bootstrap from a failed tree polling cycle', async () => {
    vi.useFakeTimers()
    const f = fixture(); await f.modes.refresh(); f.modes.setMode('cannbot')
    vi.mocked(f.remote.getTree).mockRejectedValue(Error('offline'))
    f.remoteState.set({ ...f.remoteState.getSnapshot(), servers: f.remoteState.getSnapshot().servers.map(server => ({ ...server, connected: true })) }); render(<ModeWorkspaceTree {...f} />)
    await act(async () => {})
    await act(() => vi.advanceTimersByTimeAsync(16000))
    expect(screen.getByRole('status').textContent).toBe('正在加载 DevEnv950 的工作区…'); expect(screen.queryByRole('alert')).toBeNull()
    await act(() => vi.advanceTimersByTimeAsync(15000))
    expect(screen.getByRole('alert').textContent).toContain('无法读取服务器工作区')
    expect(screen.queryByRole('status')).toBeNull()
    expect(f.remote.connect).not.toHaveBeenCalled(); expect(f.remote.open).not.toHaveBeenCalled()
    const reads = vi.mocked(f.remote.getTree).mock.calls.length
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: '重试' })); await Promise.resolve(); await Promise.resolve() })
    expect(f.remote.open).not.toHaveBeenCalled(); expect(f.remote.connect).not.toHaveBeenCalled(); expect(f.remote.getTree).toHaveBeenCalledTimes(reads + 1)
    expect(screen.queryByRole('alert')).toBeNull(); expect(screen.getByRole('status').textContent).toBe('正在加载 DevEnv950 的工作区…'); f.modes.dispose()
  })
  it('opens server configuration and starts creation with the chosen server', async () => {
    const f = fixture(); await f.modes.refresh(); f.modes.setMode('cannbot')
    f.remoteState.set({ ...f.remoteState.getSnapshot(), servers: [{ id: 'S', label: 'DevEnv950', alias: 'DevEnv950', connected: true }] })
    render(<ModeWorkspaceTree {...f} management />)
    fireEvent.click(screen.getByRole('button', { name: '新增服务器' })); expect(f.remote.showConnections).toHaveBeenCalledOnce()
    fireEvent.click(screen.getByRole('button', { name: '在 DevEnv950 上添加工作区' }))
    expect(f.modes.getSnapshot()).toMatchObject({ creating: true, creationServerId: 'S' })
    expect(f.remote.open).not.toHaveBeenCalled(); expect(f.remote.getTree).not.toHaveBeenCalled(); f.modes.dispose()
  })
  it('keeps the initial workspace load pending across transient errors and accepts the next read', async () => {
    vi.useFakeTimers()
    const f = fixture(); await f.modes.refresh(); f.modes.setMode('cannbot')
    vi.mocked(f.remote.getTree).mockRejectedValueOnce(Error('web profile starting'))
    f.remoteState.set({ ...f.remoteState.getSnapshot(), servers: f.remoteState.getSnapshot().servers.map(server => ({ ...server, connected: true })) }); render(<ModeWorkspaceTree {...f} />)
    await act(async () => {})
    expect(screen.getByRole('status').textContent).toBe('正在加载 DevEnv950 的工作区…')
    expect(screen.queryByRole('alert')).toBeNull()
    await act(() => vi.advanceTimersByTimeAsync(1999))
    expect(screen.getByRole('status')).toBeTruthy(); expect(f.remote.getTree).toHaveBeenCalledOnce()
    await act(() => vi.advanceTimersByTimeAsync(1))
    expect(screen.getByText('远端会话')).toBeTruthy(); expect(screen.queryByRole('status')).toBeNull(); expect(screen.queryByRole('alert')).toBeNull()
    expect(f.remote.open).not.toHaveBeenCalled(); expect(f.remote.connect).not.toHaveBeenCalled(); f.modes.dispose()
  })
  it('disconnects once from the connected icon and discards a late workspace read before reconnecting', async () => {
    const f = fixture(); await f.modes.refresh(); f.modes.setMode('cannbot')
    let finishRead!: (tree: Awaited<ReturnType<RemoteClient['getTree']>>) => void
    vi.mocked(f.remote.getTree).mockImplementationOnce(() => new Promise(resolve => { finishRead = resolve }))
    let finishDisconnect!: () => void
    vi.mocked(f.remote.disconnect).mockImplementation(async id => {
      f.remoteState.set({ ...f.remoteState.getSnapshot(), disconnectingServerIds: [id] })
      await new Promise<void>(resolve => { finishDisconnect = resolve })
      f.remoteState.set({ ...f.remoteState.getSnapshot(), target: null, disconnectingServerIds: [], servers: f.remoteState.getSnapshot().servers.map(server => ({ ...server, connected: false })) })
      f.modes.returnLocal()
    })
    render(<><ModeWorkspaceTree {...f} /><ModeWorkspaceTree {...f} management /></>)
    fireEvent.click(screen.getByRole('button', { name: '连接 DevEnv950' }))
    const button = await screen.findByRole('button', { name: '断开 DevEnv950' })
    fireEvent.click(button); fireEvent.click(button)
    expect(f.remote.disconnect).toHaveBeenCalledExactlyOnceWith('S')
    expect(screen.getByRole('button', { name: '正在断开 DevEnv950' })).toHaveProperty('disabled', true)
    await act(async () => { finishDisconnect() })
    expect(screen.getByRole('button', { name: '连接 DevEnv950' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'DevEnv950', exact: true })).toBeNull()
    await act(async () => { finishRead({ workspaces: [], sessions: [{ id: 'STALE', title: '断开后的迟到会话', workspaceId: '' }] }) })
    fireEvent.click(screen.getByRole('button', { name: '连接 DevEnv950' }))
    await screen.findByText('远端会话')
    expect(screen.queryByText('断开后的迟到会话')).toBeNull(); expect(screen.queryByRole('alert')).toBeNull(); f.modes.dispose()
  })
  it('keeps a disconnect failure visible through successful tree polling and retries disconnect only', async () => {
    vi.useFakeTimers()
    const f = fixture(); await f.modes.refresh(); f.modes.setMode('cannbot')
    vi.mocked(f.remote.disconnect).mockRejectedValueOnce(Error('temporary failure'))
    render(<><ModeWorkspaceTree {...f} /><ModeWorkspaceTree {...f} management /></>)
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: '连接 DevEnv950' })) })
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: '断开 DevEnv950' })) })
    expect(screen.getByRole('alert').textContent).toContain('无法断开服务器连接')
    await act(() => vi.advanceTimersByTimeAsync(5000))
    expect(screen.getByText('远端会话')).toBeTruthy(); expect(screen.getByRole('alert').textContent).toContain('无法断开服务器连接')
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: '重试' })) })
    expect(f.remote.disconnect).toHaveBeenCalledTimes(2); expect(f.remote.connect).toHaveBeenCalledOnce(); f.modes.dispose()
  })
  it('keeps independent expanded server trees and never opens a jump alias on render or expansion', async () => {
    const f = fixture(); await f.modes.refresh(); f.modes.setMode('cannbot')
    f.remoteState.set({ ...f.remoteState.getSnapshot(), servers: [
      { id: 'S', alias: 'DevEnv950', label: 'DevEnv950', connected: true },
      { id: 'T', alias: 'DevEnv960', label: 'DevEnv960', connected: true },
      { id: 'J', alias: 'jump', label: '跳板机', connected: false },
    ] })
    vi.mocked(f.remote.getTree).mockImplementation(async id => ({ workspaces: [{ workspaceId: id + 'W', path: '/' + id, title: id + '项目', pluginId: 'ops' }], sessions: [{ id: id + '1', workspaceId: id + 'W', title: id + '会话' }] }))
    render(<ModeWorkspaceTree {...f} />)
    await screen.findByText('S会话'); await screen.findByText('T会话')
    expect(f.remote.open).not.toHaveBeenCalled(); expect(f.remote.connect).not.toHaveBeenCalled(); expect(f.remote.getTree).not.toHaveBeenCalledWith('J')
    fireEvent.click(screen.getByText('T会话'))
    await waitFor(() => expect(f.remote.open).toHaveBeenCalledWith({ serverId: 'T', workspaceId: 'TW', sessionId: 'T1' }))
    expect(screen.getByRole('button', { name: 'T会话' }).getAttribute('aria-current')).toBe('page'); expect(screen.getByText('S会话').getAttribute('aria-current')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'ops: S项目', expanded: true }))
    expect(screen.queryByText('S会话')).toBeNull(); expect(screen.getByText('T会话')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'ops: S项目', expanded: false }))
    expect(screen.getByText('S会话')).toBeTruthy()
    expect(screen.queryByText('历史会话')).toBeNull(); f.modes.dispose()
  })
  it('allows read-only expansion but blocks other remote navigation while a connection is running', async () => {
    const f = fixture(); await f.modes.refresh(); f.modes.setMode('cannbot')
    f.remoteState.set({ ...f.remoteState.getSnapshot(), servers: [
      ...f.remoteState.getSnapshot().servers,
      { id: 'T', alias: 'DevEnv960', label: 'DevEnv960', connected: true },
      { id: 'J', alias: 'jump', label: '跳板机', connected: false },
    ] })
    let complete!: () => void
    vi.mocked(f.remote.connect).mockImplementation(async id => {
      f.remoteState.set({ ...f.remoteState.getSnapshot(), busy: true, selectedServerId: id })
      await new Promise<void>(resolve => { complete = resolve })
      f.remoteState.set({ ...f.remoteState.getSnapshot(), busy: false })
    })
    render(<><ModeWorkspaceTree {...f} /><ModeWorkspaceTree {...f} management /></>)
    fireEvent.click(screen.getByRole('button', { name: '连接 DevEnv950' }))
    await screen.findByText('远端会话')
    const connecting = screen.getByRole('button', { name: '正在连接 DevEnv950' })
    expect(connecting.hasAttribute('title')).toBe(false); expect(connecting.textContent).toBe('')
    expect(connecting).toHaveProperty('disabled', true)
    expect(screen.getByRole('button', { name: '连接 跳板机' }).matches(':disabled')).toBe(true)
    expect(screen.getByRole('button', { name: '断开 DevEnv960' }).matches(':disabled')).toBe(true)
    expect(screen.getByRole('button', { name: '远端会话' })).toHaveProperty('disabled', true)
    fireEvent.click(screen.getByRole('button', { name: '连接 跳板机' }))
    fireEvent.click(screen.getByRole('button', { name: '断开 DevEnv960' }))
    fireEvent.click(screen.getByRole('button', { name: '远端会话' }))
    expect(f.remote.connect).toHaveBeenCalledOnce(); expect(f.remote.open).not.toHaveBeenCalled()
    await act(async () => { complete(); await Promise.resolve() })
    expect(screen.getByRole('button', { name: '断开 DevEnv960' }).matches(':disabled')).toBe(false)
    f.modes.dispose()
  })
  it('creates on the selected remote server and retains the same submission ID on retry', async () => {
    const f = fixture(); await f.modes.refresh(); f.modes.setMode('cannbot'); f.modes.setCreating(true, 'S')
    f.remoteState.set({ ...f.remoteState.getSnapshot(), servers: [{ id: 'S', label: 'DevEnv950', alias: 'DevEnv950', connected: true }] })
    f.fetch.mockImplementation(async (_, init) => { const body = init?.body && JSON.parse(String(init.body)); return body?.action === 'start-initialization' ? Response.json({ jobId: 'job', phase: 'error', output: '', offset: 0, nextOffset: 0, inputSequence: 0, interactive: false, message: '初始化未完成，请重试。' }) : Response.json({ path: '/', crumbs: [], entries: [], truncated: false }) })
    render(<ModeWorkspaceCreation {...f} />)
    await waitFor(() => expect(screen.getByRole('textbox', { name: '父目录' })).toHaveProperty('value', '/'))
    expect(screen.getByRole('combobox', { name: '服务器' })).toHaveProperty('value', 'S')
    expect(screen.getByRole('option', { name: 'ops-direct-invoke-flash：快速生成并验证 Ascend C 算子。' })).toBeTruthy()
    fireEvent.change(screen.getByRole('textbox', { name: '工作区名' }), { target: { value: 'new-flow' } })
    fireEvent.change(screen.getByRole('combobox', { name: '工作流' }), { target: { value: 'ops-direct-invoke' } })
    fireEvent.click(screen.getByRole('button', { name: '创建工作区' })); await screen.findByText('初始化未完成，请重试。')
    fireEvent.click(within(screen.getByRole('dialog', { name: '工作流初始化' })).getByRole('button', { name: '关闭' }))
    fireEvent.click(screen.getByRole('button', { name: '创建工作区' })); await screen.findByText('初始化未完成，请重试。')
    fireEvent.click(within(screen.getByRole('dialog', { name: '工作流初始化' })).getByRole('button', { name: '关闭' }))
    const writes = f.fetch.mock.calls.filter(([, init]) => init?.body && JSON.parse(String(init.body)).action === 'start-initialization')
    expect(writes).toHaveLength(2); expect(String(writes[0][0])).toContain('api/cannbot-remote/tree?id=S'); expect(JSON.parse(String(writes[0][1]?.body)).operation).toEqual(JSON.parse(String(writes[1][1]?.body)).operation)
    expect(f.remote.open).not.toHaveBeenCalled(); f.modes.dispose()
  })
  it('uses the registered workspace plugin and removes the old header workspace selector', async () => {
    const f = fixture(); await f.modes.refresh(); f.modes.setMode('cannbot'); f.modes.selectWorkspace('C')
    const saved = { ready: true, pending: false, values: {}, errorKind: undefined }
    const selection = { getSnapshot: () => saved, subscribe: () => () => {} } as unknown as WorkflowSelection
    render(<Workbench {...f} store={f.modes.workbench} selection={selection} />)
    expect(screen.queryByRole('combobox', { name: '当前工作区' })).toBeNull()
    expect(screen.queryByRole('button', { name: '取消工作流选择' })).toBeNull()
    expect(screen.queryByText('ops-registry-invoke')).toBeNull()
    expect(f.modes.workbench.getSnapshot().workflow).toBe('ops-direct-invoke'); f.modes.dispose()
  })
  it('clears a local blank selection when choosing a workflow and preserves workflows across remote choices', async () => {
    const f = fixture(); await f.modes.refresh(); f.modes.setCreating(true)
    f.remoteState.set({ ...f.remoteState.getSnapshot(), servers: [{ id: 'S', label: 'DevEnv950', alias: 'DevEnv950', connected: true }] })
    render(<ModeWorkspaceCreation {...f} />)
    const flow = screen.getByRole('combobox', { name: '工作流' }), server = screen.getByRole('combobox', { name: '服务器' })
    fireEvent.change(flow, { target: { value: 'general' } })
    fireEvent.change(server, { target: { value: '' } })
    for (const workflow of WORKFLOWS) {
      fireEvent.change(flow, { target: { value: workflow.id } })
      expect(server).toHaveProperty('value', '__select_server__')
      expect(screen.getByRole('option', { name: '本机（本工作流需要连接NPU的Linux环境）' })).toHaveProperty('disabled', true)
      expect(screen.getByRole('textbox', { name: '父目录' })).toHaveProperty('disabled', true)
      expect(screen.getByRole('button', { name: '创建工作区' })).toHaveProperty('disabled', true)
    }
    fireEvent.change(server, { target: { value: 'S' } })
    expect(flow).toHaveProperty('value', WORKFLOWS.at(-1)!.id)
    await waitFor(() => expect(screen.getByRole('textbox', { name: '父目录' })).toHaveProperty('value', '/'))
    fireEvent.change(server, { target: { value: '' } })
    expect(server).toHaveProperty('value', 'S')
    fireEvent.change(flow, { target: { value: 'general' } })
    expect(screen.getByRole('option', { name: '本机', exact: true })).toHaveProperty('disabled', false)
    fireEvent.change(server, { target: { value: '' } })
    expect(server).toHaveProperty('value', '')
    expect(screen.queryByRole('alert')).toBeNull()
    f.modes.dispose()
  })
  it('collapses the embedded sidebar without rendering another mode list', async () => {
    history.replaceState(null, '', '/#cannEmbed=1')
    const f = fixture(); await f.modes.refresh()
    render(<ModeWorkspaceTree {...f} wide />)
    expect(f.ctx.layout.toggleSidebar).toHaveBeenCalledOnce()
    expect(screen.queryByRole('tablist')).toBeNull(); f.modes.dispose()
  })
  it('shows an embedded history-open failure in the visible workbench while preserving the requested deep link', async () => {
    history.replaceState(null, '', '/#cannEmbed=1&cannWorkspace=C&cannSession=C1')
    const f = fixture()
    Object.assign(f.ctx.sessions.list.getSnapshot(), { phase: 'ready' })
    Object.assign(f.ctx.sessions, { retain: () => ({ ready: Promise.reject(Error('private detail')), release() {} }) })
    const saved = { ready: true, pending: false, values: {}, errorKind: undefined }
    const selection = { getSnapshot: () => saved, subscribe: () => () => {} } as unknown as WorkflowSelection
    const stop = f.modes.start()
    render(<Workbench {...f} store={f.modes.workbench} selection={selection} />)
    expect(await screen.findByText('无法读取远端会话，请返回本地后重新打开。')).toHaveProperty('role', 'alert')
    expect(f.ctx.layout.selectPanel).toHaveBeenLastCalledWith('cannbot-dsh-workbench')
    expect(new URLSearchParams(location.hash.slice(1)).get('cannSession')).toBe('C1')
    expect(screen.queryByText('private detail')).toBeNull(); stop()
  })
})


describe('CANNBot native row operations', () => {
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
  it('reacts immediately to native pin ordering and session renames without mixing DeepSeek sessions', async () => {
    const f = fixture()
    f.fetch.mockImplementation(async () => new Response(JSON.stringify({ ...wire, sessions: [...wire.sessions, { ...wire.sessions[0], sessionId: 'C2', title: '第二个会话' }] })))
    f.sessionList.set({ ...f.sessionList.getSnapshot(), byId: { ...f.sessionList.getSnapshot().byId, C2: { id: 'C2', title: '第二个会话', updatedAt: 99, retainedBy: {} } } })
    await f.modes.refresh(); f.modes.setMode('cannbot'); vi.spyOn(f.modes, 'refreshAfterOperation').mockResolvedValue()
    const pin = vi.fn(async (id: string) => f.workspaceList.set({ ...f.workspaceList.getSnapshot(), pinnedSessionIds: [id] }))
    const rename = vi.fn(async (title: string) => f.sessionList.set({ ...f.sessionList.getSnapshot(), byId: { ...f.sessionList.getSnapshot().byId, C1: { ...f.sessionList.getSnapshot().byId.C1, title } } }))
    Object.assign(f.ctx.uiWorkspace, { pinSession: pin })
    Object.assign(f.ctx.sessions, { using: vi.fn(async (_id, _options, callback) => { await callback({ binding: { session: { rename } } }); return { ok: true } }) })
    const view = render(<ModeWorkspaceTree {...f} />)
    const titles = () => [...view.container.querySelectorAll('.cb-session')].map(item => item.textContent)
    expect(titles()).toEqual(['第二个会话', 'CANN会话'])
    fireEvent.click(screen.getByRole('button', { name: 'CANN会话的会话操作' })); fireEvent.click(screen.getByRole('menuitem', { name: '置顶会话' }))
    await waitFor(() => expect(titles()).toEqual(['CANN会话', '第二个会话']))
    expect(screen.getByLabelText('已置顶')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'CANN会话的会话操作' })); expect(screen.getByRole('menuitem', { name: '取消置顶' })).toBeTruthy(); fireEvent.click(screen.getByRole('menuitem', { name: '重命名' }))
    fireEvent.change(screen.getByRole('textbox', { name: '会话名称' }), { target: { value: '新的原生标题' } }); fireEvent.click(screen.getByRole('button', { name: '重命名' }))
    await screen.findByRole('button', { name: '新的原生标题的会话操作' }); expect(rename).toHaveBeenCalledWith('新的原生标题')
    expect(screen.queryByText('历史会话')).toBeNull(); f.modes.dispose()
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
  it('updates remote rows from mutation results and ignores an older in-flight tree poll', async () => {
    vi.useFakeTimers(); const f = fixture(); await f.modes.refresh(); f.modes.setMode('cannbot')
    f.remoteState.set({ ...f.remoteState.getSnapshot(), servers: f.remoteState.getSnapshot().servers.map(server => ({ ...server, connected: true })) })
    const first = await f.remote.getTree('S'); const renamed = { ...first, workspaces: first.workspaces.map(item => ({ ...item, title: '更新后的远端项目' })) }
    let finishOld!: (value: typeof first) => void
    vi.mocked(f.remote.getTree).mockResolvedValueOnce(first).mockImplementationOnce(() => new Promise(resolve => { finishOld = resolve }))
    const operate = vi.fn(async () => ({ tree: renamed })); Object.assign(f.remote, { operate })
    render(<ModeWorkspaceTree {...f} />); await act(async () => {})
    await act(() => vi.advanceTimersByTimeAsync(5000)); expect(finishOld).toBeTypeOf('function'); vi.useRealTimers()
    fireEvent.click(screen.getByRole('button', { name: '远端项目的工作区操作' })); fireEvent.click(screen.getByRole('menuitem', { name: '重命名' }))
    fireEvent.change(screen.getByRole('textbox', { name: '工作区名称' }), { target: { value: '更新后的远端项目' } }); fireEvent.click(screen.getByRole('button', { name: '重命名' }))
    await screen.findByRole('button', { name: '更新后的远端项目的工作区操作' }); expect(operate).toHaveBeenCalledWith('S', { action: 'rename-workspace', workspaceId: 'REMOTE', title: '更新后的远端项目' })
    await act(async () => { finishOld(first); await Promise.resolve() }); expect(screen.queryByRole('button', { name: '远端项目的工作区操作' })).toBeNull(); expect(screen.getByRole('button', { name: '更新后的远端项目的工作区操作' })).toBeTruthy()
    f.modes.dispose()
  })
  it('forks through the Host ownership operation and does not steal later navigation', async () => {
    const f = fixture(); await f.modes.refresh(); f.modes.setMode('cannbot')
    let complete!: (value: { ok: true; sessionId: string }) => void
    const operate = vi.spyOn(f.modes, 'operate').mockImplementation(() => new Promise(resolve => { complete = resolve }))
    render(<ModeWorkspaceTree {...f} />)
    fireEvent.click(screen.getByRole('button', { name: 'CANN会话的会话操作' })); fireEvent.click(screen.getByRole('menuitem', { name: '分叉会话' }))
    expect(operate).toHaveBeenCalledWith({ action: 'fork-session', sessionId: 'C1', allowMigration: false })
    act(() => { f.modes.setMode('deepseek') }); const opens = vi.mocked(f.ctx.uiWorkspace.openSession).mock.calls.length
    await act(async () => { complete({ ok: true, sessionId: 'CHILD' }); await Promise.resolve() })
    expect(f.ctx.uiWorkspace.openSession).toHaveBeenCalledTimes(opens); expect(f.modes.getSnapshot().mode).toBe('deepseek'); f.modes.dispose()
  })
  it('does not restore a disconnected tree from a late committed workspace operation', async () => {
    const f = fixture(); await f.modes.refresh(); f.modes.setMode('cannbot')
    const initial = await f.remote.getTree('S')
    let finish!: (value: { tree: typeof initial }) => void
    const operate = vi.fn(() => new Promise<{ tree: typeof initial }>(resolve => { finish = resolve }))
    Object.assign(f.remote, { operate })
    render(<ModeWorkspaceTree {...f} />)
    await act(() => f.remote.connect('S')); await screen.findByText('远端会话')
    fireEvent.click(screen.getByRole('button', { name: '远端项目的工作区操作' })); fireEvent.click(screen.getByRole('menuitem', { name: '重命名' }))
    fireEvent.change(screen.getByRole('textbox', { name: '工作区名称' }), { target: { value: '迟到的名称' } }); fireEvent.click(screen.getByRole('button', { name: '重命名' }))
    await waitFor(() => expect(operate).toHaveBeenCalledOnce())
    act(() => f.remoteState.set({ ...f.remoteState.getSnapshot(), servers: f.remoteState.getSnapshot().servers.map(server => ({ ...server, connected: false })) }))
    await act(async () => { finish({ tree: { ...initial, workspaces: initial.workspaces.map(workspace => ({ ...workspace, title: '迟到的名称' })) } }) })
    vi.mocked(f.remote.getTree).mockRejectedValue(Error('new profile starting'))
    await act(() => f.remote.connect('S'))
    await waitFor(() => expect(screen.getByRole('status').textContent).toBe('正在加载 DevEnv950 的工作区…'))
    expect(screen.queryByText('ops-direct-invoke: 迟到的名称')).toBeNull(); expect(screen.queryByText('远端会话')).toBeNull(); expect(operate).toHaveBeenCalledOnce(); f.modes.dispose()
  })
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


it('refreshes a committed remote action without sending it again and waits for successful readback', async () => {
  const f = fixture(); await f.modes.refresh(); f.modes.setMode('cannbot')
  f.remoteState.set({ ...f.remoteState.getSnapshot(), servers: f.remoteState.getSnapshot().servers.map(server => ({ ...server, connected: true })) })
  const first = await f.remote.getTree('S'), next = { ...first, sessions: first.sessions.map(item => ({ ...item, pinned: true })) }
  const operate = vi.fn(async () => { throw Object.assign(Error('已完成置顶，列表读取暂时失败。'), { committed: true }) }); Object.assign(f.remote, { operate })
  render(<ModeWorkspaceTree {...f} />); await screen.findByRole('button', { name: '远端会话的会话操作' })
  fireEvent.click(screen.getByRole('button', { name: '远端会话的会话操作' })); fireEvent.click(screen.getByRole('menuitem', { name: '置顶会话' }))
  await screen.findByText('已完成置顶，列表读取暂时失败。')
  expect(screen.getByRole('button', { name: '远端会话的会话操作' })).toHaveProperty('disabled', true)
  let fail!: (reason: Error) => void
  vi.mocked(f.remote.getTree).mockImplementationOnce(() => new Promise((_, reject) => { fail = reject }))
  fireEvent.click(screen.getByRole('button', { name: '刷新列表' }))
  expect(screen.getByText('已完成置顶，列表读取暂时失败。')).toBeTruthy(); expect(screen.getByRole('button', { name: '正在刷新…' })).toHaveProperty('disabled', true)
  await act(async () => { fail(Error('read failed')); await Promise.resolve() })
  expect(await screen.findByText('刷新未完成，请重试刷新列表。')).toBeTruthy(); expect(screen.getByText('已完成置顶，列表读取暂时失败。')).toBeTruthy()
  vi.mocked(f.remote.getTree).mockResolvedValueOnce(next); fireEvent.click(screen.getByRole('button', { name: '刷新列表' }))
  await waitFor(() => expect(screen.queryByText('已完成置顶，列表读取暂时失败。')).toBeNull())
  expect(screen.getByLabelText('已置顶')).toBeTruthy(); expect(operate).toHaveBeenCalledOnce(); expect(screen.getByRole('button', { name: '远端会话的会话操作' })).toHaveProperty('disabled', false); f.modes.dispose()
})

it.each([true, false])('clears only a committed error on a later successful background poll (committed=%s)', async committed => {
  const f = fixture(); await f.modes.refresh(); f.modes.setMode('cannbot')
  f.remoteState.set({ ...f.remoteState.getSnapshot(), servers: f.remoteState.getSnapshot().servers.map(server => ({ ...server, connected: true })) })
  const operate = vi.fn(async () => { throw Object.assign(Error('远端操作提示'), { committed }) }); Object.assign(f.remote, { operate })
  vi.useFakeTimers({ shouldAdvanceTime: true })
  render(<ModeWorkspaceTree {...f} />); await screen.findByRole('button', { name: '远端会话的会话操作' })
  fireEvent.click(screen.getByRole('button', { name: '远端会话的会话操作' })); fireEvent.click(screen.getByRole('menuitem', { name: '置顶会话' })); await screen.findByText('远端操作提示')
  const calls = vi.mocked(f.remote.getTree).mock.calls.length
  await act(async () => { await vi.advanceTimersByTimeAsync(5000) })
  expect(vi.mocked(f.remote.getTree).mock.calls.length).toBeGreaterThan(calls)
  expect(!!screen.queryByText('远端操作提示')).toBe(!committed); expect(operate).toHaveBeenCalledOnce(); f.modes.dispose()
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


describe('native sidebar layout and retained session boundaries', () => {
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
  it('preserves only the retained blank across panels without highlighting it or adding row actions', async () => {
    const f = fixture()
    f.fetch.mockImplementation(async () => new Response(JSON.stringify({ ...wire, sessions: [...wire.sessions, { ...wire.sessions[0], sessionId: 'C2', title: '另一个空会话' }, { ...wire.sessions[0], sessionId: 'C3', title: '新会话' }] })))
    const previous = f.sessionList.getSnapshot()
    f.sessionList.set({ ...previous, byId: { ...previous.byId, D1: { ...previous.byId.D1, retainedBy: {} }, C1: { ...previous.byId.C1, blank: true, retainedBy: { mainView: 1 } }, C2: { id: 'C2', title: '另一个空会话', blank: true, retainedBy: {} }, C3: { id: 'C3', title: '新会话', blank: false, running: true, retainedBy: {}, updatedAt: 9 } } })
    await f.modes.refresh(); f.modes.setMode('cannbot'); f.modes.openSession('C1')
    const view = render(<ModeWorkspaceTree {...f} />)
    expect(view.container.querySelector('[data-session-id="C1"] .cb-session')?.getAttribute('aria-current')).toBe('page')
    act(() => f.panelInfo.set({ activePanelId: 'plugins' }))
    const blank = view.container.querySelector('[data-session-id="C1"]')!
    expect(blank).toBeTruthy(); expect(blank.textContent).toBe('新会话')
    expect(blank.querySelector('.cb-session')?.hasAttribute('aria-current')).toBe(false)
    expect(blank.querySelector('.cb-row-actions')).toBeNull(); expect(blank.querySelector('.cb-session-time')).toBeNull()
    expect(view.container.querySelector('[data-session-id="C2"]')).toBeNull()
    expect(view.container.querySelector('[data-session-id="C3"] .cb-row-actions')).toBeTruthy()
    expect(view.container.querySelector('[data-session-id="C3"] [data-state="ongoing"]')).toBeTruthy()
    f.modes.dispose()
  })
  it('archives an explicit local row through Host ownership while the remote panel is selected', async () => {
    const f = fixture(); await f.modes.refresh(); f.modes.setMode('cannbot'); f.modes.selectServer('S')
    const nativeArchive = vi.fn(), operate = vi.spyOn(f.modes, 'operate').mockResolvedValue({ ok: true })
    Object.assign(f.ctx.uiWorkspace, { archiveSession: nativeArchive })
    const refresh = vi.spyOn(f.modes, 'refreshAfterOperation').mockResolvedValue()
    render(<ModeWorkspaceTree {...f} />)
    fireEvent.click(screen.getByRole('button', { name: 'CANN会话的会话操作' })); fireEvent.click(screen.getByRole('menuitem', { name: '归档会话' }))
    await waitFor(() => expect(operate).toHaveBeenCalledWith({ action: 'archive-session', sessionId: 'C1' }))
    expect(nativeArchive).not.toHaveBeenCalled(); expect(refresh).not.toHaveBeenCalled()
    expect(f.modes.getSnapshot().serverId).toBe('S'); expect(f.remote.returnLocal).not.toHaveBeenCalled()
    f.modes.dispose()
  })
})


describe('server ordering and removal', () => {
  const servers = [{ id: 'S', alias: 'DevEnv950', label: 'DevEnv950', connected: true }, { id: 'T', alias: 'DevEnv960', label: 'DevEnv960', connected: true }, { id: 'U', alias: 'DevEnv970', label: 'DevEnv970', connected: false }]
  async function setup() {
    const f = fixture(); await f.modes.refresh(); f.modes.setMode('cannbot')
    f.remoteState.set({ ...f.remoteState.getSnapshot(), servers })
    const reorder = vi.fn(async (_ids: string[]) => {}), remove = vi.fn(async (_id: string) => {})
    Object.assign(f.remote, { reorderServers: reorder, removeServer: remove })
    const view = render(<ModeWorkspaceTree {...f} management />)
    const group = (id: string) => view.container.querySelector<HTMLElement>('[data-cannbot-server-id="' + id + '"]')!
    const header = (id: string) => group(id).querySelector<HTMLElement>(':scope > .cb-project-row')!
    for (const [index, server] of servers.entries()) vi.spyOn(group(server.id), 'getBoundingClientRect').mockReturnValue({ top: 100 + index * 100, height: 80 } as DOMRect)
    const transfer = { effectAllowed: '', dropEffect: '', setData: vi.fn() }
    const event = (type: string, target: Element, clientY = 0) => {
      const next = new MouseEvent(type, { bubbles: true, cancelable: true, clientY })
      Object.defineProperty(next, 'dataTransfer', { value: transfer }); fireEvent(target, next); return next
    }
    const start = (id = 'S') => { fireEvent.pointerDown(header(id)); return event('dragstart', header(id)) }
    const order = () => [...view.container.querySelectorAll('[data-cannbot-server-id]')].map(item => item.getAttribute('data-cannbot-server-id'))
    return { ...f, view, group, header, transfer, event, start, order, reorder, remove }
  }

  it('commits one native drop, keeps local first and suppresses the drag-end click', async () => {
    const f = await setup(); let finish!: () => void
    f.reorder.mockImplementation(async ids => { await new Promise<void>(resolve => { finish = resolve }); f.remoteState.set({ ...f.remoteState.getSnapshot(), servers: ids.map(id => servers.find(server => server.id === id)!) }) })
    expect(f.view.container.querySelector('.cb-workspace-list')?.firstElementChild?.querySelector('.cb-project-title')?.textContent).toBe('DevEnv950')
    expect(screen.queryByRole('button', { name: '本机', exact: true })).toBeNull()
    f.start(); expect(f.transfer.effectAllowed).toBe('move'); expect(f.transfer.setData).toHaveBeenCalledWith('text/plain', 'S')
    f.event('dragover', f.group('T'), 275); expect(f.group('T').classList.contains('cb-server-drop-after')).toBe(true)
    expect(f.reorder).not.toHaveBeenCalled()
    f.event('drop', f.group('T'), 275); f.event('drop', f.group('T'), 275); f.event('dragend', f.header('S'))
    expect(f.reorder).toHaveBeenCalledExactlyOnceWith(['T', 'S', 'U'])
    expect(f.header('S').draggable).toBe(false); expect(f.header('T').draggable).toBe(false)
    expect(screen.getByRole('button', { name: 'DevEnv950的服务器操作' })).toHaveProperty('disabled', true)
    fireEvent.click(f.header('S')); expect(f.header('S').getAttribute('aria-expanded')).toBeNull()
    await act(async () => { finish() }); expect(f.order()).toEqual(['T', 'S', 'U'])
    expect(f.header('S').draggable).toBe(true); expect(f.remote.open).not.toHaveBeenCalled()
    f.modes.dispose()
  })

  it.each(['escape', 'outside', 'outside-over', 'local', 'blur', 'dragend-none'])('does not reorder a cancelled drag (%s)', async cancellation => {
    const f = await setup(); f.start(); f.event('dragover', f.group('T'), 275)
    if (cancellation === 'escape') fireEvent.keyDown(document, { key: 'Escape' })
    if (cancellation === 'outside') { f.event('dragleave', f.group('T'), 400); f.event('drop', document.body, 400) }
    if (cancellation === 'outside-over') f.event('dragover', document.body, 400)
    if (cancellation === 'local') f.event('dragover', screen.getByRole('heading', { name: '服务器' }), 50)
    if (cancellation === 'blur') fireEvent(window, new Event('blur'))
    if (cancellation === 'dragend-none') f.transfer.dropEffect = 'none'
    f.event('dragend', f.header('S')); f.event('drop', f.group('T'), 275)
    expect(f.reorder).not.toHaveBeenCalled(); expect(f.order()).toEqual(['S', 'T', 'U'])
    expect(f.view.container.querySelector('.cb-server-drop-before,.cb-server-drop-after')).toBeNull()
    fireEvent.click(f.header('S')); expect(f.header('S').getAttribute('aria-expanded')).toBeNull()
    f.modes.dispose()
  })

  it('accepts a desktop drop outside React and commits the last marker once on successful native drag end', async () => {
    const f = await setup()
    const stop = (event: Event) => event.stopPropagation()
    // Electron may deliver native events without dispatching a React row drop.
    f.group('T').addEventListener('dragover', stop); f.group('T').addEventListener('drop', stop)
    expect(f.event('dragover', f.group('T'), 275).defaultPrevented).toBe(false)
    f.start()
    expect(f.event('dragover', f.group('T'), 275).defaultPrevented).toBe(true)
    expect(f.transfer.dropEffect).toBe('move'); expect(f.group('T').classList.contains('cb-server-drop-after')).toBe(true)
    expect(f.event('drop', f.group('T'), 275).defaultPrevented).toBe(true)
    expect(f.reorder).not.toHaveBeenCalled()
    f.event('dragend', f.header('S')); f.event('dragend', f.header('S'))
    expect(f.reorder).toHaveBeenCalledExactlyOnceWith(['T', 'S', 'U'])
    expect(f.view.container.querySelector('.cb-server-drop-after')).toBeNull()
    expect(f.event('dragover', document.body, 400).defaultPrevented).toBe(false)
    await act(async () => {}); f.modes.dispose()
  })

  it('preserves a valid marker across a child dragleave with no relatedTarget, but clears it when the pointer leaves', async () => {
    const f = await setup(), descriptor = Object.getOwnPropertyDescriptor(document, 'elementFromPoint')
    const hit = vi.fn((): Element | null => f.header('T').querySelector('.cb-project-title'))
    Object.defineProperty(document, 'elementFromPoint', { configurable: true, value: hit })
    try {
      f.start(); f.event('dragover', f.group('T'), 275)
      f.event('dragleave', f.group('T'), 275)
      expect(f.group('T').classList.contains('cb-server-drop-after')).toBe(true)
      f.event('dragend', f.header('S')); expect(f.reorder).toHaveBeenCalledExactlyOnceWith(['T', 'S', 'U'])
      await act(async () => {})
      f.start(); f.event('dragover', f.group('T'), 275); hit.mockReturnValue(null)
      f.event('dragleave', f.group('T'), 400); f.event('dragend', f.header('S'))
      expect(f.reorder).toHaveBeenCalledOnce(); expect(f.view.container.querySelector('.cb-server-drop-after')).toBeNull()
    } finally {
      if (descriptor) Object.defineProperty(document, 'elementFromPoint', descriptor)
      else Reflect.deleteProperty(document, 'elementFromPoint')
      f.modes.dispose()
    }
  })

  it('cancels the native acceptance lease when switching to DeepSeek', async () => {
    const f = await setup(), source = f.header('S')
    f.start(); f.event('dragover', f.group('T'), 275)
    act(() => f.modes.setMode('deepseek'))
    expect(f.event('dragover', document.body, 400).defaultPrevented).toBe(false)
    f.event('dragend', source)
    expect(f.reorder).not.toHaveBeenCalled(); f.modes.dispose()
  })

  it('ignores actions and child workspace drags instead of reordering their server', async () => {
    const f = await setup(), menu = screen.getByRole('button', { name: 'DevEnv950的服务器操作' })
    fireEvent.pointerDown(menu)
    expect(f.event('dragstart', f.header('S')).defaultPrevented).toBe(true)
    f.event('dragover', f.group('T'), 275); f.event('drop', f.group('T'), 275)
    expect(f.group('S').querySelector('.cb-project-children')).toBeNull()
    expect(f.reorder).not.toHaveBeenCalled(); expect(f.transfer.setData).not.toHaveBeenCalled()
    f.modes.dispose()
  })

  it('does not write a no-op order or overwrite an inventory changed during the drag', async () => {
    const f = await setup(); f.start(); f.event('dragover', f.group('T'), 205); f.event('drop', f.group('T'), 205)
    expect(f.reorder).not.toHaveBeenCalled()
    f.start(); f.event('dragover', f.group('T'), 275)
    act(() => f.remoteState.set({ ...f.remoteState.getSnapshot(), servers: [...servers, { id: 'NEW', alias: 'new', label: '新增服务器', connected: false }] }))
    f.event('drop', f.group('T'), 275)
    expect(f.reorder).not.toHaveBeenCalled(); expect(screen.getByRole('alert').textContent).toBe('服务器列表已变化，请重新拖动排序。')
    f.modes.dispose()
  })

  it('reports a failed reorder without reconnecting or automatically repeating the write', async () => {
    const f = await setup(); f.reorder.mockRejectedValueOnce(Error('save failed'))
    f.start(); f.event('dragover', f.group('T'), 275); f.event('drop', f.group('T'), 275)
    await screen.findByText('服务器排序未保存，请重新拖动重试。')
    expect(f.order()).toEqual(['S', 'T', 'U']); expect(f.reorder).toHaveBeenCalledOnce()
    expect(f.remote.open).not.toHaveBeenCalled(); expect(f.remote.connect).not.toHaveBeenCalled()
    f.start(); f.event('dragover', f.group('T'), 275); f.event('drop', f.group('T'), 275)
    await waitFor(() => expect(f.reorder).toHaveBeenCalledTimes(2)); f.modes.dispose()
  })

  it.each([false, true])('confirms removing a server, preserves failure for retry, and guards double submission (connected=%s)', async connected => {
    const f = await setup(); act(() => f.remoteState.set({ ...f.remoteState.getSnapshot(), servers: servers.map(server => server.id === 'S' ? { ...server, connected } : server) }))
    const request = () => { fireEvent.click(screen.getByRole('button', { name: 'DevEnv950的服务器操作' })); fireEvent.click(screen.getByRole('menuitem', { name: '删除服务器' })) }
    request(); expect(screen.getByRole('dialog', { name: '删除服务器' }).textContent).toContain('远端文件、会话和运行中的任务会保留')
    expect(f.remove).not.toHaveBeenCalled(); fireEvent.click(screen.getByRole('button', { name: '取消' })); expect(f.remove).not.toHaveBeenCalled()
    f.remove.mockRejectedValueOnce(Error('删除服务器未完成，请重试。')); request(); fireEvent.click(screen.getByRole('button', { name: '删除服务器' }))
    await screen.findByText('删除服务器未完成，请重试。'); expect(screen.getByRole('dialog', { name: '删除服务器' })).toBeTruthy()
    let finish!: () => void
    f.remove.mockImplementation(async id => { await new Promise<void>(resolve => { finish = resolve }); f.remoteState.set({ ...f.remoteState.getSnapshot(), servers: f.remoteState.getSnapshot().servers.filter(server => server.id !== id) }) })
    const confirm = screen.getByRole('button', { name: '删除服务器' }); fireEvent.click(confirm); fireEvent.click(confirm)
    expect(f.remove).toHaveBeenCalledTimes(2); expect(f.remove).toHaveBeenLastCalledWith('S'); expect(confirm).toHaveProperty('disabled', true)
    expect(f.header('S').draggable).toBe(false); expect(screen.getByRole('button', { name: 'DevEnv950的服务器操作' })).toHaveProperty('disabled', true)
    await act(async () => { finish() }); expect(screen.queryByRole('dialog')).toBeNull(); expect(f.order()).toEqual(['T', 'U'])
    expect(f.remote.disconnect).not.toHaveBeenCalled(); expect(f.remote.returnLocal).not.toHaveBeenCalled(); f.modes.dispose()
  })

  it('blocks pending server actions and ordering without allowing local removal', async () => {
    const f = await setup()
    act(() => f.remoteState.set({ ...f.remoteState.getSnapshot(), removingServerIds: ['S'] }))
    expect(f.header('S').draggable).toBe(false); expect(screen.getByRole('button', { name: 'DevEnv950的服务器操作' })).toHaveProperty('disabled', true)
    f.start(); f.event('dragover', f.group('T'), 275); f.event('drop', f.group('T'), 275); expect(f.reorder).not.toHaveBeenCalled()
    act(() => f.remoteState.set({ ...f.remoteState.getSnapshot(), removingServerIds: [], orderingServers: true }))
    expect(f.header('T').draggable).toBe(false); expect(screen.getByRole('button', { name: 'DevEnv960的服务器操作' })).toHaveProperty('disabled', true)
    expect(screen.queryByRole('button', { name: '本机的服务器操作' })).toBeNull(); expect(f.remove).not.toHaveBeenCalled(); f.modes.dispose()
  })
})
