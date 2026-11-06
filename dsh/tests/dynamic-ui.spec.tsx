// ----------------------------------------------------------------------------------------------------------
// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.
// ----------------------------------------------------------------------------------------------------------

import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { WorkflowSelector, type WorkflowProps } from '../src/client/WorkflowSelector.tsx'
import { createWorkflowSelection } from '../src/client/workflow-selection.ts'
import { zh } from '../src/client/locales.ts'
import type { ContentStore } from '../src/client/content-store.ts'
vi.mock('@deepseek-ai/dsh-client-ui-primitives', () => ({
  IconAgentPresetOutlineRegular: () => null,
  IconChevronDownOutlineRegular: () => null,
  Menu: ({ anchor, open, children }: { anchor: ReactNode; open: boolean; children: ReactNode }) => <>{anchor}{open && <div role="menu">{children}</div>}</>,
  MenuItemButton: ({ onSelect, children }: { onSelect(): void; children: ReactNode }) => <button role="menuitem" onClick={onSelect}>{children}</button>,
}))
afterEach(cleanup)
it('renders a workflow absent from the npm package and waits for initialization without editing the draft', async () => {
  let ready!: () => void
  const gate = new Promise<void>(resolve => { ready = resolve })
  const prepare = vi.fn(() => gate), release = vi.fn(), block = vi.fn(() => release)
  const selection = createWorkflowSelection(block, prepare)
  const update = vi.fn(async (_: string, patch: object) => ({ ns: 'cannbot-dsh', value: patch }))
  selection.attach({ describe: async () => ({ namespaces: [{ ns: 'cannbot-dsh', value: {} }] }), update })
  await waitFor(() => expect(selection.getSnapshot().ready).toBe(true))
  const snapshot = { workflows: [{ id: 'new-official-workflow', title: '新工作流' }], status: undefined }
  const content = { getSnapshot: () => snapshot, subscribe: () => () => {} } as unknown as ContentStore
  const draft = { draft: '用户原始需求', images: ['attachment'], phase: 'plain' }, setDraft = vi.fn()
  render(<WorkflowSelector {...{ sessionId: 'S', t: (key: keyof typeof zh) => zh[key], selection, content,
    useInput: (read: (input: object) => object) => read(draft), inputActions: { setDraft } } as unknown as WorkflowProps} />)
  fireEvent.click(screen.getByRole('button', { name: zh.workflow }))
  fireEvent.click(screen.getByRole('menuitem', { name: /新工作流/ }))
  expect(prepare).toHaveBeenCalledWith('S', 'new-official-workflow')
  expect(update).not.toHaveBeenCalled()
  expect(selection.getSnapshot().pending).toBe(true)
  ready()
  await waitFor(() => expect(update).toHaveBeenCalled())
  expect(update.mock.calls[0][1]).toEqual({ selections: [{ sessionId: 'S', workflow: 'new-official-workflow' }] })
  expect(setDraft).not.toHaveBeenCalled()
  expect(draft).toEqual({ draft: '用户原始需求', images: ['attachment'], phase: 'plain' })
  expect(release).toHaveBeenCalledOnce()
  selection.dispose()
})
it('preserves the committed selection and releases submission when initialization fails', async () => {
  const release = vi.fn(), update = vi.fn(), selection = createWorkflowSelection(() => release, async () => { throw new Error('init failed') })
  selection.attach({ describe: async () => ({ namespaces: [{ ns: 'cannbot-dsh', value: { selections: [{ sessionId: 'S', workflow: 'ops-direct-invoke' }] } }] }), update })
  await waitFor(() => expect(selection.getSnapshot().ready).toBe(true))
  await selection.choose('S', 'future-workflow')
  expect(update).not.toHaveBeenCalled()
  expect(selection.getSnapshot()).toMatchObject({ pending: false, error: true, values: { S: 'ops-direct-invoke' } })
  expect(release).toHaveBeenCalledOnce()
  selection.dispose()
})
it('retries settings discovery while the host plugin is still activating', async () => {
  vi.useFakeTimers()
  const selection = createWorkflowSelection()
  const describe = vi.fn().mockResolvedValueOnce({ namespaces: [] }).mockRejectedValueOnce(new Error('reconnecting'))
    .mockResolvedValue({ namespaces: [{ ns: 'cannbot-dsh', value: {} }] })
  try {
    selection.attach({ describe, update: vi.fn() })
    await vi.advanceTimersByTimeAsync(0)
    expect(selection.getSnapshot()).toMatchObject({ ready: false, error: false })
    await vi.advanceTimersByTimeAsync(1000)
    expect(selection.getSnapshot()).toMatchObject({ ready: true, error: false })
    expect(describe).toHaveBeenCalledTimes(3)
  } finally { selection.dispose(); vi.useRealTimers() }
})
it('supports retry after a settings timeout and cancels discovery on unload', async () => {
  vi.useFakeTimers()
  const selection = createWorkflowSelection()
  const describe = vi.fn().mockResolvedValue({ namespaces: [] })
  try {
    selection.attach({ describe, update: vi.fn() })
    await vi.advanceTimersByTimeAsync(20000)
    expect(selection.getSnapshot()).toMatchObject({ error: true, errorKind: 'settings' })
    describe.mockResolvedValue({ namespaces: [{ ns: 'cannbot-dsh', value: {} }] })
    selection.retry()
    await vi.advanceTimersByTimeAsync(0)
    expect(selection.getSnapshot()).toMatchObject({ ready: true, error: false })
    const detach = selection.attach({ describe: vi.fn().mockResolvedValue({ namespaces: [] }), update: vi.fn() })
    await vi.advanceTimersByTimeAsync(0)
    detach()
    expect(vi.getTimerCount()).toBe(0)
  } finally { selection.dispose(); vi.useRealTimers() }
})
it('automatically recovers when host activation takes longer than the initial retry window', async () => {
  vi.useFakeTimers()
  const selection = createWorkflowSelection(), describe = vi.fn().mockResolvedValue({ namespaces: [] })
  try {
    selection.attach({ describe, update: vi.fn() })
    await vi.advanceTimersByTimeAsync(20000)
    expect(selection.getSnapshot()).toMatchObject({ ready: false, errorKind: 'settings' })
    describe.mockResolvedValue({ namespaces: [{ ns: 'cannbot-dsh', value: {} }] })
    await vi.advanceTimersByTimeAsync(5000)
    expect(selection.getSnapshot()).toMatchObject({ ready: true, error: false })
  } finally { selection.dispose(); vi.useRealTimers() }
})
it('retries a failed workflow preparation without editing the user draft', async () => {
  const prepare = vi.fn().mockRejectedValueOnce(new Error('temporary failure')).mockResolvedValue(undefined)
  const selection = createWorkflowSelection(undefined, prepare)
  const update = vi.fn(async (_: string, patch: object) => ({ ns: 'cannbot-dsh', value: patch }))
  selection.attach({ describe: async () => ({ namespaces: [{ ns: 'cannbot-dsh', value: {} }] }), update })
  await waitFor(() => expect(selection.getSnapshot().ready).toBe(true))
  await selection.choose('S', 'ops-direct-invoke-flash')
  expect(selection.getSnapshot()).toMatchObject({ error: true, errorKind: 'prepare' })
  render(<WorkflowSelector {...{ sessionId: 'S', selection, t: (key: keyof typeof zh) => zh[key], useInput: () => ({ phase: 'plain', draft: 'unchanged' }), inputActions: {} } as unknown as WorkflowProps} />)
  expect(screen.getByRole('button', { name: zh.workflow })).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: zh.workflowRetry }))
  await waitFor(() => expect(selection.getSnapshot()).toMatchObject({ error: false, values: { S: 'ops-direct-invoke-flash' } }))
  expect(prepare).toHaveBeenCalledTimes(2)
  expect(update).toHaveBeenCalledOnce()
  selection.dispose()
})
