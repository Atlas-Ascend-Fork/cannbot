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
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ReactNode } from 'react'
import { WorkflowSelector, type WorkflowProps } from '../src/client/WorkflowSelector.tsx'
import { zh } from '../src/client/locales.ts'
import { apply } from '../src/client/index.ts'
import type { Context } from '@deepseek-ai/cordis'
import { WORKFLOWS } from '../src/workflows.ts'
import { createPresentationController } from '../src/client/presentation.ts'
import { InterfaceToggle } from '../src/client/InterfaceToggle.tsx'
import { createWorkflowSelection, connectWorkflowSelection } from '../src/client/workflow-selection.ts'
import { WorkflowCompat } from '../src/client/WorkflowCompat.tsx'
import { SessionWorkflow, type SessionWorkflowProps } from '../src/client/SessionWorkflow.tsx'

const compatibility = vi.hoisted(() => ({ legacy: false }))

vi.mock('@deepseek-ai/dsh-client-ui-primitives', () => ({
  Button: ({ children, variant: _variant, size: _size, ...props }: { children: ReactNode; variant: string; size: string }) => <button {...props}>{children}</button>,
  IconChevronDownOutlineRegular: () => null,
  get IconAgentPresetOutlineRegular() { return compatibility.legacy ? undefined : () => <svg aria-hidden="true" /> },
  IconAgentPresetOutline16: () => <svg aria-hidden="true" data-testid="legacy-preset-icon" />,
  Menu: ({ anchor, open, children, items, onSelect }: { anchor: ReactNode; open: boolean; children: ReactNode; items?: { id: string; label: ReactNode }[]; onSelect?(id: string): void }) => <>{anchor}{open && <div role="menu">{items ? items.map(item => <button key={item.id} role="menuitem" onClick={() => onSelect?.(item.id)}>{item.label}</button>) : children}</div>}</>,
  get MenuItemButton() { return compatibility.legacy ? undefined : ({ onSelect, children }: { onSelect: () => void; children: ReactNode }) => <button role="menuitem" onClick={onSelect}>{children}</button> },
  Tooltip: ({ children }: { children: ReactNode }) => children,
  Switch: ({ label, checked, onChange, disabled }: { label: string; checked: boolean; onChange: (value: boolean) => void; disabled: boolean }) =>
    <button role="switch" aria-label={label} aria-checked={checked} disabled={disabled} onClick={() => onChange(!checked)} />,
}))
afterEach(() => { cleanup(); compatibility.legacy = false })
const t = (key: keyof typeof zh) => zh[key]
async function workflow(draft = '保留已有需求', phase = 'plain', initial = {}) {
  const selection = createWorkflowSelection()
  let values: Record<string, string> = initial
  const update = vi.fn(async (_ns, patch) => { values = Object.fromEntries(patch.selections.map((item: { sessionId: string; workflow: string }) => [item.sessionId, item.workflow])); return { ns: 'cannbot-dsh', value: patch } })
  selection.attach({ describe: async () => ({ namespaces: [{ ns: 'cannbot-dsh', value: { selections: Object.entries(values).map(([sessionId, workflow]) => ({ sessionId, workflow })) } }] }), update })
  const insertText = vi.fn(), setDraft = vi.fn(), submit = vi.fn()
  const props = { t, sessionId: 'session-1', selection, useInput: (select: (input: object) => object) => select({ draft, draftRev: 7, phase }), inputActions: { insertText, setDraft, submit } } as unknown as WorkflowProps
  render(<WorkflowSelector {...props} />)
  await waitFor(() => expect(selection.getSnapshot().ready).toBe(true))
  return { selection, update, insertText, setDraft, submit }
}

describe('background workflow selection', () => {
  it('uses the official legacy connection API and unwraps its response envelope', async () => {
    const selection = createWorkflowSelection()
    const update = vi.fn(async request => ({ result: { ok: true, value: { ns: request.ns, value: request.patch } } }))
    const cleanups: (() => void)[] = []
    const scope = {
      connection: { api: { settings: {
        describe: async () => ({ result: { ok: true, value: { namespaces: [{ ns: 'cannbot-dsh', value: {}, revision: 3 }] } } }), update,
      } } },
      effect(callback: () => () => void) { cleanups.push(callback()) },
    }
    connectWorkflowSelection({ inject(keys: string[], callback: (scope: object) => void) { if (keys[0] === 'connection') callback(scope) } } as Context, selection)
    await waitFor(() => expect(selection.getSnapshot().ready).toBe(true))
    await selection.choose('session-1', 'ops-direct-invoke')
    expect(update).toHaveBeenCalledExactlyOnceWith({ ns: 'cannbot-dsh', patch: { selections: [{ sessionId: 'session-1', workflow: 'ops-direct-invoke' }] }, expectedRevision: 3 })
    expect(selection.getSnapshot().values['session-1']).toBe('ops-direct-invoke')
    for (const cleanup of cleanups) cleanup()
  })
  it('blocks submission until the preference commits and releases the block on unload', async () => {
    const release = vi.fn(), block = vi.fn(() => release)
    const selection = createWorkflowSelection(block)
    let finish!: (value: { ns: string; value: { selections: { sessionId: string; workflow: string }[] } }) => void
    selection.attach({
      describe: async () => ({ namespaces: [{ ns: 'cannbot-dsh', value: {} }] }),
      update: () => new Promise(resolve => { finish = resolve }),
    })
    await waitFor(() => expect(selection.getSnapshot().ready).toBe(true))
    const choosing = selection.choose('session-1', 'ops-direct-invoke', zh.saving)
    await waitFor(() => expect(finish).toBeTypeOf('function'))
    expect(block).toHaveBeenCalledWith('session-1', zh.saving)
    expect(release).not.toHaveBeenCalled()
    selection.dispose()
    expect(release).toHaveBeenCalledOnce()
    finish({ ns: 'cannbot-dsh', value: { selections: [{ sessionId: 'session-1', workflow: 'ops-direct-invoke' }] } })
    await choosing
    expect(release).toHaveBeenCalledOnce()
  })
  it('preserves the preparation error for the workbench without committing a failed selection', async () => {
    const release = vi.fn(), update = vi.fn()
    const selection = createWorkflowSelection(() => release, async () => { throw new Error('EIO: .dsh/skills/shared，已恢复旧版本') })
    const detach = selection.attach({ describe: async () => ({ namespaces: [{ ns: 'cannbot-dsh', value: {} }] }), update })
    await waitFor(() => expect(selection.getSnapshot().ready).toBe(true))
    await selection.choose('session-1', 'ops-direct-invoke')
    expect(selection.getSnapshot()).toMatchObject({ error: true, errorKind: 'prepare', errorMessage: 'EIO: .dsh/skills/shared，已恢复旧版本', values: {} })
    expect(update).not.toHaveBeenCalled()
    expect(release).toHaveBeenCalledOnce()
    detach(); selection.dispose()
  })
  it('persists selection for the session without editing or submitting the draft', async () => {
    const actions = await workflow()
    fireEvent.click(screen.getByRole('button', { name: zh.workflow }))
    fireEvent.click(screen.getByRole('menuitem', { name: new RegExp(`^${zh.operator}(?:\\s|$)`) }))
    await waitFor(() => expect(actions.update).toHaveBeenCalled())
    await waitFor(() => expect(screen.getByText(zh.operator)).toBeTruthy())
    expect(actions.update.mock.calls[0][1]).toEqual({ selections: [{ sessionId: 'session-1', workflow: 'ops-direct-invoke' }] })
    expect(actions.insertText).not.toHaveBeenCalled()
    expect(actions.setDraft).not.toHaveBeenCalled()
    expect(actions.submit).not.toHaveBeenCalled()
    expect(screen.queryByText('/ops-direct-invoke')).toBeNull()
  })
  it('offers three workflows and a normal-conversation reset, without command text', async () => {
    await workflow()
    fireEvent.click(screen.getByRole('button', { name: zh.workflow }))
    expect(screen.getAllByRole('menuitem')).toHaveLength(4)
    for (const item of WORKFLOWS) expect(screen.getByRole('menuitem', { name: new RegExp(`^${t(item.label)}(?:\\s|$)`) })).toBeTruthy()
    expect(screen.queryByText(/\/ops-/)).toBeNull()
  })
  it('clears only this session and preserves another window selection', async () => {
    const actions = await workflow('', 'plain', { 'session-1': 'ops-direct-invoke', 'session-2': 'ops-registry-invoke' })
    fireEvent.click(screen.getByRole('button', { name: zh.workflow }))
    fireEvent.click(screen.getByRole('menuitem', { name: zh.ordinary }))
    await waitFor(() => expect(actions.update).toHaveBeenCalled())
    expect(actions.update.mock.calls[0][1]).toEqual({ selections: [{ sessionId: 'session-2', workflow: 'ops-registry-invoke' }] })
  })
  it('keeps the last committed selection when saving fails', async () => {
    const actions = await workflow('', 'plain', { 'session-1': 'ops-direct-invoke' })
    actions.update.mockRejectedValueOnce(new Error('offline'))
    fireEvent.click(screen.getByRole('button', { name: zh.workflow }))
    fireEvent.click(screen.getByRole('menuitem', { name: new RegExp(zh.registry) }))
    await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy())
    expect(actions.selection.getSnapshot().values['session-1']).toBe('ops-direct-invoke')
  })
  it('supports the legacy menu and root seat without changing text or images', async () => {
    compatibility.legacy = true
    const selection = createWorkflowSelection()
    const update = vi.fn(async (_ns, patch) => ({ ns: 'cannbot-dsh', value: patch }))
    selection.attach({ describe: async () => ({ namespaces: [{ ns: 'cannbot-dsh', value: {} }] }), update })
    const state = { draft: '已有需求', phase: 'plain', draftRev: 4, images: ['image-1'] }
    const setDraft = vi.fn(), subscribe = () => () => {}, list = { current: 'session-1' }
    const ctx = { sessions: { list: { subscribe, getSnapshot: () => list }, scope: () => ({}) }, conversation: { input: { for: () => ({ state: { subscribe, getSnapshot: () => state }, setDraft }) } } }
    render(<WorkflowCompat {...{ t, ctx, selection } as unknown as WorkflowProps & { ctx: Context }} />)
    await waitFor(() => expect(selection.getSnapshot().ready).toBe(true))
    expect(screen.getByTestId('legacy-preset-icon')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: zh.workflow }))
    fireEvent.click(screen.getByRole('menuitem', { name: new RegExp(`^${zh.operator}(?:\\s|$)`) }))
    await waitFor(() => expect(update).toHaveBeenCalled())
    expect(setDraft).not.toHaveBeenCalled()
    expect(state).toMatchObject({ draft: '已有需求', images: ['image-1'] })
  })
  it('disables selection while a message is submitting', async () => {
    await workflow('需求', 'submitting')
    expect(screen.getByRole('button', { name: zh.workflow })).toHaveProperty('disabled', true)
  })
})
describe('session workflow indicator', () => {
  it('restores the saved workflow and follows the header session, including sessions without a workflow', async () => {
    const selection = createWorkflowSelection()
    const props = { sessionId: 'session-1', selection, t } as SessionWorkflowProps
    const view = render(<SessionWorkflow {...props} />)
    expect(view.container.textContent).toBe('')
    selection.attach({
      describe: async () => ({ namespaces: [{ ns: 'cannbot-dsh', value: { selections: [
        { sessionId: 'session-1', workflow: 'ops-direct-invoke' },
        { sessionId: 'session-2', workflow: 'ops-registry-invoke' },
      ] } }] }),
      update: async (_ns, value) => ({ ns: 'cannbot-dsh', value }),
    })
    await screen.findByText('ops-direct-invoke')
    view.rerender(<SessionWorkflow {...props} sessionId={'session-2' as SessionWorkflowProps['sessionId']} />)
    expect(screen.getByText('ops-registry-invoke')).toBeTruthy()
    expect(screen.queryByText('ops-direct-invoke')).toBeNull()
    view.rerender(<SessionWorkflow {...props} sessionId={'ordinary' as SessionWorkflowProps['sessionId']} />)
    expect(view.container.textContent).toBe('')
    view.rerender(<SessionWorkflow {...props} />)
    await act(() => selection.choose('session-1', 'ops-registry-invoke'))
    expect(screen.getByText('ops-registry-invoke')).toBeTruthy()
    await act(() => selection.choose('session-1', ''))
    expect(view.container.textContent).toBe('')
    selection.dispose()
  })
})
describe('plugin lifecycle', () => {
  it('enables the interface immediately and removes the footer and all overrides on unload', () => {
    const active = new Map<string, object>()
    const effects: (() => void)[] = []
    const releaseTheme = vi.fn()
    const ctx = {
      inject: () => () => {},
      locale: { register: () => () => {} },
      theme: { overrideTokens: vi.fn(() => releaseTheme) },
      effect: (callback: () => () => void) => { effects.push(callback()) },
      slots: {
        inject: (_name: string, callback: () => () => void) => callback(),
        register: (options: { name: string }) => { active.set(options.name, options); return () => { active.delete(options.name) } },
      },
    }
    for (let activation = 0; activation < 2; activation++) {
      apply(ctx as Context)
      expect(active.has('conversation.hero.agentPreset')).toBe(true)
      expect(active.has('conversation.session.header.actions')).toBe(true)
      expect(active.has('sidebar.brand.name')).toBe(true)
      expect(active.has('sidebar.footer.action')).toBe(true)
      expect(active.has('plugins.bundle.config')).toBe(false)
      expect(document.querySelectorAll('style[data-cannbot-dsh]')).toHaveLength(1)
      for (const effect of effects.splice(0).reverse()) effect()
      expect(active.size).toBe(0)
      expect(document.querySelector('style[data-cannbot-dsh]')).toBeNull()
    }
    expect(releaseTheme).toHaveBeenCalledTimes(2)
  })
  it('uses a plain CANNBot switch, defaults on and switches presentation without unloading Skills', () => {
    const unmount = vi.fn()
    const mount = vi.fn(() => unmount)
    const controller = createPresentationController(mount)
    render(<InterfaceToggle wide controller={controller} />)
    const toggle = screen.getByRole('switch', { name: 'CANNBot' })
    expect(toggle.getAttribute('aria-checked')).toBe('true')
    expect(screen.queryByText('CANNBot DSH 界面')).toBeNull()
    fireEvent.click(toggle)
    expect(toggle.getAttribute('aria-checked')).toBe('false')
    expect(unmount).toHaveBeenCalledOnce()
    fireEvent.click(toggle)
    expect(toggle.getAttribute('aria-checked')).toBe('true')
    expect(mount).toHaveBeenCalledTimes(2)
    cleanup(); controller.dispose()
    expect(unmount).toHaveBeenCalledTimes(2)
  })
})
