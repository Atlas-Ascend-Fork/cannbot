// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ReactNode } from 'react'
import type { Context } from '@deepseek-ai/cordis'
import { NativeWorkbench, NativeWorkbenchEmpty, NativeWorkspacePicker, WorkflowPermissionDialog } from '../src/client/NativeWorkbench.tsx'
import { NativeWorkflowPlaceholder, adaptNativePlaceholder } from '../src/client/NativeWorkflowPlaceholder.tsx'
import { CANNBOT_HOME, type WorkspaceModes } from '../src/client/workspace-modes.ts'
import type { WorkflowSelection } from '../src/client/workflow-selection.ts'
import type { NativeWorkbenchSessionSnapshot } from '../src/client/native-workbench-session.ts'

vi.mock('@deepseek-ai/dsh-client-ui-primitives', () => ({
  IconFolderCloseRegular: () => <svg />, IconProjectAddOutlineRegular: () => <svg />,
  Menu: ({ open, items, onSelect }: { open: boolean; items: { id: string; type?: string; label?: ReactNode; disabled?: boolean }[]; onSelect(id: string): void }) => open ? <div role="menu">{items.filter(item => !item.type).map(item => <button key={item.id} role="menuitem" disabled={item.disabled} onClick={() => onSelect(item.id)}>{item.label}</button>)}</div> : null,
}))
afterEach(cleanup)
function store<T>(initial: T) { let value = initial; const listeners = new Set<() => void>(); return { getSnapshot: () => value, subscribe(listener: () => void) { listeners.add(listener); return () => listeners.delete(listener) }, set(next: T) { value = next; listeners.forEach(listener => listener()) } } }
const workspace = { workspaceId: 'C', title: '算子项目', path: '/cann', pluginId: 'ops-direct-invoke', sessionIds: ['C1'] }
function fixture(selectedWorkspaceId = 'C') {
  const mode = store({ mode: 'cannbot', ready: true, selectedWorkspaceId, workspaces: [workspace], sessions: [], serverId: '', navigationError: '', restoringSession: false, permissionWorkspaceId: undefined as string | undefined })
  const panel = store({ activePanelId: CANNBOT_HOME as string | null })
  const modes = { ...mode, newSession: vi.fn(), setCreating: vi.fn(), finishPermissionRequest: vi.fn(() => mode.set({ ...mode.getSnapshot(), permissionWorkspaceId: undefined })), openSession: vi.fn(() => panel.set({ activePanelId: null })) } as unknown as WorkspaceModes
  const prepared = store<NativeWorkbenchSessionSnapshot>({ workspaceId: '', busy: false, error: '' })
  const preparation = { ...prepared, selectWorkspace: vi.fn(async () => {}), retry: vi.fn(async () => {}), dispose: vi.fn() }
  const ctx = { layout: { panelInfo: panel } } as unknown as Context
  const renderSlot = vi.fn(() => <div>原生未选择工作区输入</div>)
  const SessionProvider = vi.fn((props: { session?: unknown; empty?: () => ReactNode; children: ReactNode }) => props.session === undefined ? props.empty?.() : props.children)
  return { mode, panel, modes, prepared, preparation, ctx, renderSlot, SessionProvider }
}
describe('native CANNBot home', () => {
  it('never grants workflow permissions without consent and supports retry after failure', async () => {
    Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value() { this.setAttribute('open', '') } })
    const grant = vi.fn(async () => {}), complete = vi.fn()
    const view = render(<WorkflowPermissionDialog grant={grant} complete={complete} />)
    expect(grant).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: '暂不授予' }))
    expect(grant).not.toHaveBeenCalled(); expect(complete).toHaveBeenCalledOnce()
    view.unmount(); complete.mockClear()
    grant.mockRejectedValueOnce(new Error('offline'))
    render(<WorkflowPermissionDialog grant={grant} complete={complete} />)
    fireEvent.click(screen.getByRole('button', { name: '授予完全权限' }))
    await screen.findByRole('alert'); expect(complete).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: '授予完全权限' }))
    await waitFor(() => expect(complete).toHaveBeenCalledOnce())
  })
  it('uses an explicitly absent SessionProvider before a workspace is selected', () => {
    const f = fixture(''); render(<NativeWorkbench {...f} />)
    expect(f.SessionProvider.mock.calls[0][0]).toHaveProperty('session', undefined)
    expect(screen.getByText('原生未选择工作区输入')).toBeTruthy()
    expect(f.preparation.selectWorkspace).not.toHaveBeenCalled()
    expect(f.modes.openSession).not.toHaveBeenCalled()
    expect(screen.queryByRole('textbox')).toBeNull()
  })
  it('renders the actual public conversation factory for the absent workspace surface', () => {
    const renderFactorySlot = vi.fn(() => <div>官方空会话</div>)
    render(<NativeWorkbenchEmpty renderFactorySlot={renderFactorySlot} />)
    expect(renderFactorySlot).toHaveBeenCalledWith('conversation.content', { variant: 'embedded', phase: 'hero', hero: true })
  })
  it('opens only the successfully prepared blank through native navigation without submitting a draft', async () => {
    const f = fixture(); let finish!: () => void
    f.preparation.selectWorkspace.mockImplementation(async () => { await new Promise<void>(resolve => { finish = resolve }); f.prepared.set({ workspaceId: 'C', sessionId: 'C1', busy: false, error: '' }) })
    render(<NativeWorkbench {...f} />)
    expect(f.modes.openSession).not.toHaveBeenCalled()
    expect(screen.getByRole('status').textContent).toContain('正在准备工作区')
    expect(f.SessionProvider).not.toHaveBeenCalled()
    await act(async () => { finish() })
    expect(f.modes.openSession).toHaveBeenCalledExactlyOnceWith('C1')
    expect(screen.queryByText('原生未选择工作区输入')).toBeNull()
  })
  it('does not expose an inert composer during a cold remote target restoration', () => {
    const f = fixture('')
    f.mode.set({ ...f.mode.getSnapshot(), restoringSession: true })
    render(<NativeWorkbench {...f} />)
    expect(screen.getByRole('status').textContent).toContain('正在准备工作区')
    expect(f.SessionProvider).not.toHaveBeenCalled()
    expect(f.preparation.selectWorkspace).not.toHaveBeenCalled()
  })
  it('keeps preparation visible until the permission suggestion is resolved, then opens the ready session', async () => {
    Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value() { this.setAttribute('open', '') } })
    const f = fixture(); let finish!: () => void
    f.mode.set({ ...f.mode.getSnapshot(), permissionWorkspaceId: 'C' })
    const command = vi.fn(async () => ({ ok: true, value: { matched: true } }))
    f.preparation.selectWorkspace.mockImplementation(async () => {
      await new Promise<void>(resolve => { finish = resolve })
      f.prepared.set({ workspaceId: 'C', sessionId: 'C1', session: { binding: { session: { command } } } as never, busy: false, error: '' })
    })
    render(<NativeWorkbench {...f} />)
    expect(screen.getByRole('status').textContent).toContain('正在准备工作区')
    await act(async () => { finish() })
    expect(screen.getByRole('dialog', { name: '工作流权限' })).toBeTruthy()
    expect(screen.getByRole('status').textContent).toContain('工作区已准备就绪')
    expect(f.SessionProvider).not.toHaveBeenCalled(); expect(f.modes.openSession).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: '暂不授予' }))
    expect(command).not.toHaveBeenCalled()
    expect(f.modes.openSession).toHaveBeenCalledExactlyOnceWith('C1')
    expect(screen.queryByRole('status')).toBeNull()
  })
  it.each(['mode', 'workspace', 'panel', 'remote'])('does not redirect after the user changes %s during preparation', async changed => {
    const f = fixture(); let finish!: () => void
    f.preparation.selectWorkspace.mockImplementation(async () => { await new Promise<void>(resolve => { finish = resolve }); f.prepared.set({ workspaceId: 'C', sessionId: 'C1', busy: false, error: '' }) })
    render(<NativeWorkbench {...f} />)
    await act(async () => {
      if (changed === 'panel') f.panel.set({ activePanelId: 'plugins' })
      else f.mode.set({ ...f.mode.getSnapshot(), ...(changed === 'mode' ? { mode: 'deepseek' } : changed === 'remote' ? { serverId: 'remote' } : { selectedWorkspaceId: '' }) })
    })
    await act(async () => { finish() })
    expect(f.modes.openSession).not.toHaveBeenCalled()
  })
  it.each(['restore', 'restore-error', 'remote'])('does not prepare a new local blank for %s', flag => {
    const f = fixture()
    f.mode.set({ ...f.mode.getSnapshot(), restoringSession: flag === 'restore', navigationError: flag === 'restore-error' ? '恢复失败' : '', serverId: flag === 'remote' ? 'S' : '' })
    render(<NativeWorkbench {...f} />)
    expect(f.preparation.selectWorkspace).not.toHaveBeenCalled()
  })
  it('uses only CANN workspace membership and never calls the native reusable-blank picker callback', () => {
    const f = fixture(), onPick = vi.fn(), onClose = vi.fn()
    render(<NativeWorkspacePicker modes={f.modes} open onPick={onPick} onClose={onClose} />)
    fireEvent.click(screen.getByRole('menuitem', { name: '算子项目' }))
    expect(f.modes.newSession).toHaveBeenCalledExactlyOnceWith('C')
    expect(onPick).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('menuitem', { name: '创建工作区' }))
    expect(f.modes.setCreating).toHaveBeenCalledExactlyOnceWith(true)
    expect(onClose).toHaveBeenCalledTimes(2)
  })
})

describe('native placeholder text adaptation', () => {
  const surface = () => {
    const root = document.createElement('div')
    root.innerHTML = '<div role="textbox" contenteditable="true" data-placeholder="原生提示" aria-label="原生提示" style="font-size:16px;color:gray">已有草稿</div><div data-composer-placeholder>原生提示</div>'
    document.body.append(root); return root
  }
  it('preserves native editor content and styles, restores text, and settles its own observer writes', async () => {
    const root = surface(), editor = root.querySelector('[role="textbox"]')!, style = editor.getAttribute('style')
    let mutations = 0; const observer = new MutationObserver(records => { mutations += records.length })
    observer.observe(root, { childList: true, subtree: true, attributes: true })
    const stop = adaptNativePlaceholder(root, '开发一个 Add 算子。')
    await waitFor(() => expect(editor.getAttribute('data-placeholder')).toBe('开发一个 Add 算子。'))
    const count = mutations; await act(async () => { await new Promise(resolve => setTimeout(resolve, 0)) })
    expect(mutations).toBe(count)
    expect(editor.textContent).toBe('已有草稿'); expect(editor.getAttribute('style')).toBe(style)
    stop(); expect(editor.getAttribute('data-placeholder')).toBe('原生提示')
    expect(root.querySelector('[data-composer-placeholder]')?.textContent).toBe('原生提示')
    observer.disconnect(); root.remove()
  })
  it('preserves new native disabled/model-error copy and leaves it untouched on disposal', async () => {
    const root = surface(), editor = root.querySelector('[role="textbox"]')!, placeholder = root.querySelector('[data-composer-placeholder]')!
    const stop = adaptNativePlaceholder(root, '开发算子')
    editor.setAttribute('contenteditable', 'false'); editor.setAttribute('aria-disabled', 'true')
    editor.setAttribute('data-placeholder', '请选择模型'); editor.setAttribute('aria-label', '请选择模型'); placeholder.textContent = '请选择模型'
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 0)) })
    stop(); expect(editor.getAttribute('data-placeholder')).toBe('请选择模型'); expect(placeholder.textContent).toBe('请选择模型'); root.remove()
  })
  it('applies examples only to a ready CANN-owned plain blank and restores on Plan, block, mode or workflow failure', async () => {
    const f = fixture(), saved = store({ ready: true, pending: false, error: false, values: { C1: 'ops-direct-invoke' } }), block = store<undefined | { reason: string }>(undefined)
    const catalog = store({ byId: { C1: { blank: true } } })
    const ctx = { sessions: { list: catalog }, conversation: { blocks: { storeFor: () => block } } } as unknown as Context
    let plan = false
    const props = { ctx, modes: f.modes, selection: saved as unknown as WorkflowSelection, sessionId: 'C1', useInput: (select: (value: unknown) => unknown) => select({ phase: 'plain' }), useSession: (select: (value: unknown) => unknown) => select({ running: false }), useProjection: (_: string, select: (value: unknown) => unknown) => select({ active: plan, pending: false }) }
    const body = () => <div data-slot="conversation.composer.bar"><div role="textbox" contentEditable data-placeholder="原生提示" aria-label="原生提示" /><div data-composer-placeholder>原生提示</div><NativeWorkflowPlaceholder {...props as never} /></div>
    const view = render(body()), editor = screen.getByRole('textbox')
    await waitFor(() => expect(editor.getAttribute('data-placeholder')).not.toBe('原生提示'))
    expect(editor.getAttribute('data-placeholder')).not.toMatch(/^例如/)
    plan = true; view.rerender(body()); expect(editor.getAttribute('data-placeholder')).toBe('原生提示')
    plan = false; view.rerender(body()); await waitFor(() => expect(editor.getAttribute('data-placeholder')).not.toBe('原生提示'))
    act(() => block.set({ reason: '模型不可用' })); expect(editor.getAttribute('data-placeholder')).toBe('原生提示')
    act(() => block.set(undefined)); await waitFor(() => expect(editor.getAttribute('data-placeholder')).not.toBe('原生提示'))
    act(() => f.mode.set({ ...f.mode.getSnapshot(), mode: 'deepseek' })); expect(editor.getAttribute('data-placeholder')).toBe('原生提示')
    act(() => { f.mode.set({ ...f.mode.getSnapshot(), mode: 'cannbot' }); saved.set({ ...saved.getSnapshot(), error: true }) }); expect(editor.getAttribute('data-placeholder')).toBe('原生提示')
  })
})
