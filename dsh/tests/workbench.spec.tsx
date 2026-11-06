// ----------------------------------------------------------------------------------------------------------
// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.
// ----------------------------------------------------------------------------------------------------------

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Context } from '@deepseek-ai/cordis'
import type { ContentStore } from '../src/client/content-store.ts'
import type { WorkflowSelection } from '../src/client/workflow-selection.ts'
import { Workbench, HOME_PANEL } from '../src/client/Workbench.tsx'
import { createWorkbenchState } from '../src/client/workbench-state.ts'
import { launchWorkbench } from '../src/client/workbench-launch.ts'
import { WORKFLOWS } from '../src/workflows.ts'
import { inheritedWorkspaceId } from '../src/client/workbench-workspace.ts'

afterEach(cleanup)
Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value() { this.setAttribute('open', '') } })
function fixture() {
  const update = vi.fn(), submit = vi.fn(), release = vi.fn(), openSession = vi.fn()
  const selectionSnapshot = { ready: true, pending: false, error: false, values: {} as Record<string, string> }
  const selection = { getSnapshot: () => selectionSnapshot, subscribe: () => () => {}, choose: vi.fn(async (id: string, workflow: string) => { selectionSnapshot.values[id] = workflow }), retry: vi.fn() } as unknown as WorkflowSelection
  const catalog = { workflows: WORKFLOWS.map(item => ({ id: item.id, title: item.id })), status: { plugins: [], workflows: [], phase: 'ready' } }
  const content = { getSnapshot: () => catalog, subscribe: () => () => {}, check: vi.fn(async () => {}), update, rollback: vi.fn() } as unknown as ContentStore
  const store = createWorkbenchState()
  const workspaceSnapshot = { phase: 'ready', state: 'idle', items: [{ workspaceId: 'W', title: '开发工作区', path: '/project', sessionIds: ['CURRENT'] }] }
  const sessionSnapshot = { byId: { CURRENT: { id: 'CURRENT', retainedBy: { mainView: 1 } } } }
  const input = { submit, addAttachments: vi.fn(() => true) }
  const binding = { ctx: {} }
  const ctx = {
    workspaces: { list: { value: workspaceSnapshot, subscribe() { if (!this.value) throw new Error('lost receiver'); return () => {} }, getSnapshot() { return this.value } }, create: vi.fn() },
    uiWorkspace: { pickDirectory: vi.fn(async () => { throw Error('native capability unavailable') }), listDirectory: vi.fn(async (path = '/project') => ({ path, home: '/home/user', crumbs: [{ name: '/', path: '/', hidden: false }], entries: [{ name: 'other', path: '/other', hidden: false }], truncated: false })), openSession },
    layout: { selectPanel: vi.fn(), panelInfo: { getSnapshot: () => ({ activePanelId: HOME_PANEL }) } },
    sessions: { list: { subscribe: () => () => {}, getSnapshot: () => sessionSnapshot }, create: vi.fn(async () => 'S'), retain: vi.fn(() => ({ ready: Promise.resolve(binding), release })) },
    conversation: { blocks: { storeFor: () => ({ getSnapshot: () => undefined }) }, input: { for: () => input, requestDraftInitialization: vi.fn(() => 'applied') }, createDrafts: vi.fn(), releaseDraftAttachment: vi.fn() },
    get: () => ({ openBundle: vi.fn() }),
  } as unknown as Context
  return { ctx, store, content, selection, selectionSnapshot, input, submit, release, openSession }
}
describe('CANNBot workbench', () => {
  it('browses and selects a workspace without invoking the native picker or starting a task', async () => {
    const f = fixture(), file = new File(['code'], 'input.cpp')
    f.store.set({ prompt: '保留需求', files: [file] })
    vi.mocked(f.ctx.workspaces.create).mockImplementation(async ({ path }) => {
      const item = { workspaceId: 'NEW', title: 'other', path, sessionIds: [] }
      f.ctx.workspaces.list.getSnapshot().items.push(item)
      return item
    })
    render(<Workbench {...f} />)
    fireEvent.click(screen.getByRole('button', { name: '选择工作区' }))
    await screen.findByRole('button', { name: /other/ })
    fireEvent.click(screen.getByRole('button', { name: /other/ }))
    await waitFor(() => expect((screen.getByRole('textbox', { name: '目录路径' }) as HTMLInputElement).value).toBe('/other'))
    fireEvent.click(screen.getByRole('button', { name: '选择此目录' }))
    await waitFor(() => expect(f.store.getSnapshot().workspaceId).toBe('NEW'))
    expect(f.ctx.workspaces.create).toHaveBeenCalledWith({ path: '/other' })
    expect(f.ctx.uiWorkspace.pickDirectory).not.toHaveBeenCalled()
    expect(f.submit).not.toHaveBeenCalled()
    expect(f.store.getSnapshot()).toMatchObject({ prompt: '保留需求', files: [file], busy: false })
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(screen.getByText('/other')).toBeTruthy()
  })
  it('reuses an existing workspace and keeps selection unchanged on cancel', async () => {
    const f = fixture(); render(<Workbench {...f} />)
    fireEvent.click(screen.getByRole('button', { name: '选择工作区' }))
    await screen.findByRole('button', { name: /other/ })
    fireEvent.click(screen.getByRole('button', { name: '取消' }))
    expect(f.store.getSnapshot().workspaceId).toBe('')
    fireEvent.click(screen.getByRole('button', { name: '选择工作区' }))
    await screen.findByRole('button', { name: /other/ })
    fireEvent.click(screen.getByRole('button', { name: '选择此目录' }))
    await waitFor(() => expect(f.store.getSnapshot().workspaceId).toBe('W'))
    expect(f.ctx.workspaces.create).not.toHaveBeenCalled()
    expect(f.submit).not.toHaveBeenCalled()
  })
  it('keeps directory errors in the chooser and retries browsing without submitting', async () => {
    const f = fixture(); vi.mocked(f.ctx.uiWorkspace.listDirectory).mockRejectedValueOnce(Error('Permission denied'))
    render(<Workbench {...f} />)
    fireEvent.click(screen.getByRole('button', { name: '选择工作区' }))
    await screen.findByText('Permission denied')
    expect(screen.queryByText('暂时无法开始，需求和文件已保留。')).toBeNull()
    expect((screen.getByRole('button', { name: '选择此目录' }) as HTMLButtonElement).disabled).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: '打开目录' }))
    await screen.findByRole('button', { name: /other/ })
    expect(screen.queryByText('Permission denied')).toBeNull()
    expect(f.submit).not.toHaveBeenCalled()
    expect(f.store.getSnapshot().error).toBe('')
  })
  it('filters, selects and clears a workflow without changing or sending the requirement', () => {
    const f = fixture(); f.store.set({ prompt: '保留原来的需求' })
    render(<Workbench {...f} />)
    expect(screen.getByRole('group', { name: '工作流分类' }).querySelectorAll('button')).toHaveLength(2)
    expect(screen.getByRole('button', { name: /ops-direct-invoke-flash.*快速生成/ }).getAttribute('aria-pressed')).toBe('true')
    fireEvent.click(screen.getByRole('button', { name: /ops-registry-invoke.*开发/ }))
    expect(f.store.getSnapshot()).toMatchObject({ workflow: 'ops-registry-invoke', prompt: '保留原来的需求' })
    expect(f.submit).not.toHaveBeenCalled()
    expect(document.activeElement).toBe(screen.getByRole('textbox', { name: '开发需求' }))
    expect(screen.queryByText('可补充输入形状、数据类型和目标硬件。')).toBeNull()
    fireEvent.change(screen.getByRole('textbox', { name: '搜索工作流' }), { target: { value: 'registry' } })
    expect(screen.getByRole('button', { name: /ops-registry-invoke.*开发/ })).toBeTruthy()
    expect(screen.queryByRole('button', { name: /ops-direct-invoke.*开发/ })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: '取消工作流选择' }))
    expect(f.store.getSnapshot().workflow).toBe('')
  })
  it('shows useful details and keeps the existing prompt when using an example', () => {
    const f = fixture(); f.store.set({ prompt: '用户自己的需求' })
    render(<Workbench {...f} library />)
    expect(screen.getByRole('heading', { name: '需要提供什么' })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '使用此示例 ↗' }))
    expect(f.store.getSnapshot()).toMatchObject({ prompt: '用户自己的需求', workflow: 'ops-direct-invoke-flash' })
    expect(f.ctx.layout.selectPanel).toHaveBeenCalledWith(HOME_PANEL)
    expect(f.submit).not.toHaveBeenCalled()
  })
  it('fills the example only when the prompt is empty', () => {
    const f = fixture(); render(<Workbench {...f} library />)
    fireEvent.click(screen.getByRole('button', { name: '使用此示例 ↗' }))
    expect(f.store.getSnapshot().prompt).toContain('float16')
  })
  it('keeps text and selected files when workflow preparation fails', async () => {
    const f = fixture(), file = new File(['code'], 'add.cpp')
    f.store.set({ prompt: '需求不丢失', workflow: 'ops-direct-invoke', files: [file] })
    f.selection.choose = vi.fn(async () => { f.selectionSnapshot.error = true })
    render(<Workbench {...f} />)
    fireEvent.click(screen.getByRole('button', { name: '开始' }))
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('工作流准备未完成'))
    expect(f.store.getSnapshot()).toMatchObject({ prompt: '需求不丢失', files: [file], busy: false })
    expect(f.submit).not.toHaveBeenCalled(); expect(f.openSession).not.toHaveBeenCalled(); expect(f.release).toHaveBeenCalledOnce()
  })
  it('transfers the plain requirement to the official input only after workflow preparation', async () => {
    const f = fixture()
    await launchWorkbench(f.ctx, f.selection, { workspaceId: 'W', workflow: 'ops-direct-invoke', prompt: '开发 Add', files: [] }, f.store.signal)
    expect(f.ctx.conversation.input.requestDraftInitialization).toHaveBeenCalledWith({ ctx: {} }, { prompt: '开发 Add', whenDraftExists: 'keep' })
    expect(f.selection.choose).toHaveBeenCalledWith('S', 'ops-direct-invoke')
    expect(f.openSession).toHaveBeenCalledWith('S'); expect(f.submit).toHaveBeenCalledWith('queue', 'click'); expect(f.release).toHaveBeenCalledOnce()
  })
  it('refuses to overwrite a retained draft and never submits after disposal', async () => {
    const f = fixture()
    vi.mocked(f.ctx.conversation.input.requestDraftInitialization).mockReturnValue('preserved')
    await expect(launchWorkbench(f.ctx, f.selection, { workspaceId: 'W', workflow: '', prompt: '新需求', files: [] }, f.store.signal)).rejects.toThrow('已存在草稿')
    expect(f.submit).not.toHaveBeenCalled(); expect(f.release).toHaveBeenCalledOnce()
    f.store.dispose()
    await expect(launchWorkbench(f.ctx, f.selection, { workspaceId: 'W', workflow: '', prompt: '新需求', files: [] }, f.store.signal)).rejects.toThrow()
    expect(f.ctx.sessions.create).toHaveBeenCalledTimes(1)
  })
  it('waits for file upload before giving attachments to the original composer', async () => {
    const f = fixture(), file = new File(['code'], 'add.cpp')
    const uploads = { getSnapshot: () => ({ A: { status: 'ready' } }), subscribe: () => () => {} }
    Object.assign(f.ctx.conversation, { createDrafts: vi.fn(() => [{ id: 'A', kind: 'file', file }]), fileUploads: uploads })
    await launchWorkbench(f.ctx, f.selection, { workspaceId: 'W', workflow: '', prompt: '代码', files: [file] }, f.store.signal)
    expect(f.input.addAttachments).toHaveBeenCalledWith(['A']); expect(f.submit).toHaveBeenCalledOnce()
    expect((f.ctx.conversation as unknown as { releaseDraftAttachment: () => void }).releaseDraftAttachment).not.toHaveBeenCalled()
  })
  it.each([false, true])('sends images without upload records (mixed: %s)', async mixed => {
    const f = fixture(), image = new File(['image'], 'input.png', { type: 'image/png' }), file = new File(['code'], 'a.cpp')
    const attachments = [{ id: 'IMAGE', kind: 'image', file: image }, ...(mixed ? [{ id: 'FILE', kind: 'file', file }] : [])]
    let status = 'uploading', notify = () => {}
    Object.assign(f.ctx.conversation, {
      createDrafts: vi.fn(() => attachments),
      fileUploads: { getSnapshot: () => mixed ? { FILE: { status } } : {}, subscribe: (listener: () => void) => { notify = listener; return () => {} } },
    })
    const request = launchWorkbench(f.ctx, f.selection, { workspaceId: 'W', workflow: '', prompt: '需求', files: mixed ? [image, file] : [image] }, f.store.signal)
    await waitFor(() => expect(f.ctx.conversation.createDrafts).toHaveBeenCalled())
    if (mixed) { expect(f.submit).not.toHaveBeenCalled(); status = 'ready'; notify() }
    await request
    expect(f.ctx.conversation.createDrafts).toHaveBeenCalledWith('S', mixed ? [image, file] : [image])
    expect(f.input.addAttachments).toHaveBeenCalledWith(mixed ? ['IMAGE', 'FILE'] : ['IMAGE'])
    expect(f.submit).toHaveBeenCalledOnce()
  })
  it('inherits only the workspace containing the main conversation, never the first unrelated workspace', () => {
    const workspaces = [{ workspaceId: 'BOT', sessionIds: ['BOT_SESSION'] }, { workspaceId: 'PROJECT', sessionIds: ['ACTIVE'] }]
    expect(inheritedWorkspaceId(workspaces, { byId: { BOT_SESSION: { retainedBy: { mainView: 0 } }, ACTIVE: { retainedBy: { mainView: 1 } } } })).toBe('PROJECT')
    expect(inheritedWorkspaceId(workspaces, { byId: {} })).toBeUndefined()
    expect(inheritedWorkspaceId(workspaces, { current: 'ACTIVE' })).toBe('PROJECT')
  })
  it('shows the real inherited path, removes the management button and preserves a manual workspace choice', () => {
    const f = fixture(); render(<Workbench {...f} />)
    expect(screen.getByText('/project')).toBeTruthy()
    expect(screen.getByText('沿用当前对话')).toBeTruthy()
    expect(screen.queryByRole('button', { name: '管理工作流' })).toBeNull()
    fireEvent.change(screen.getByRole('combobox', { name: '当前工作区' }), { target: { value: 'W' } })
    expect(f.store.getSnapshot().workspaceId).toBe('W')
    expect(screen.queryByText('沿用当前对话')).toBeNull()
  })
  it('emits only actual preparation stages and skips uploads when there are no files', async () => {
    const f = fixture(), stages: string[] = []
    await launchWorkbench(f.ctx, f.selection, { workspaceId: 'W', workflow: 'ops-direct-invoke', prompt: '需求', files: [] }, f.store.signal, stage => stages.push(stage))
    expect(stages).toEqual(['workspace', 'dependencies', 'conversation'])
  })
  it('offers a safe retry after preparation fails and keeps the requirement until transfer succeeds', async () => {
    const f = fixture(); f.store.set({ prompt: '继续保留需求', workflow: 'ops-direct-invoke' })
    let attempt = 0
    f.selection.choose = vi.fn(async (id, workflow) => { attempt++; f.selectionSnapshot.error = attempt === 1; if (attempt > 1) f.selectionSnapshot.values[id] = workflow })
    render(<Workbench {...f} />)
    fireEvent.click(screen.getByRole('button', { name: '开始' }))
    await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy())
    expect(f.store.getSnapshot().prompt).toBe('继续保留需求')
    expect(screen.getByText('查看原因')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '重试', exact: true }))
    await waitFor(() => expect(f.submit).toHaveBeenCalledOnce())
    expect(f.store.getSnapshot()).toMatchObject({ prompt: '', busy: false })
  })
})
