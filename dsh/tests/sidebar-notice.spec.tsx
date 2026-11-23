// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createSidebarNotices, SidebarNotice } from '../src/client/SidebarNotice.tsx'

const observed = vi.hoisted(() => ({ holdMs: undefined as number | undefined, onDone: () => {} }))
// The public component owns layout and fade timing. These tests isolate our
// action identity and display contract; native portal/timing runs separately.
vi.mock('@deepseek-ai/dsh-client-ui-primitives', () => ({
  IconWarningOutlineRegular: () => <svg />,
  Toast: ({ text, holdMs, actions, onDone }: { text: string; holdMs?: number; actions: { label: string; prefix?: string; onClick(): void }[]; onDone(): void }) => {
    observed.holdMs = holdMs; observed.onDone = onDone
    return <div role="alert">{text}{actions.map(action => <span key={action.label}>{action.prefix}<button onClick={action.onClick}>{action.label}</button></span>)}</div>
  },
}))
afterEach(() => { cleanup(); vi.useRealTimers() })
function deferred() {
  let resolve!: () => void, reject!: (reason: unknown) => void
  const promise = new Promise<void>((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}

describe('native sidebar notices', () => {
  it('provides the native archive hold and updates filter actions without replacing notice identity', () => {
    const notices = createSidebarNotices()
    const view = render(<div style={{ transform: 'translateX(1px)' }}><SidebarNotice notices={notices} /></div>)
    act(() => notices.archived({ sessionId: 'remote-C1', undo: vi.fn(async () => {}), showArchived: vi.fn() }))
    const toast = screen.getByRole('alert')
    expect(toast.textContent).toBe('会话已归档，可撤销或筛选已归档会话')
    expect(observed.holdMs).toBe(6000)
    view.rerender(<div><SidebarNotice notices={notices} archivedVisible /></div>)
    expect(screen.queryByRole('button', { name: '筛选已归档会话' })).toBeNull()
    expect(screen.getByRole('alert')).toBe(toast)
    act(() => observed.onDone())
    expect(screen.queryByRole('alert')).toBeNull()
    notices.dispose()
  })

  it('dismisses before undo and invokes the original session callback once', async () => {
    const notices = createSidebarNotices(), pending = deferred()
    const undo = vi.fn(() => {
      expect(notices.getSnapshot()).toBeNull()
      return pending.promise
    })
    render(<SidebarNotice notices={notices} />)
    act(() => notices.archived({ sessionId: 'original-server/session', stopped: true, undo }))
    expect(screen.getByRole('alert').textContent).toBe('已停止并归档，可撤销')
    const oldAction = notices.getSnapshot()!.actions![0]
    fireEvent.click(screen.getByRole('button', { name: '撤销' }))
    oldAction.onClick()
    expect(undo).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole('alert')).toBeNull()
    await act(async () => { pending.resolve(); await pending.promise })
    expect(screen.queryByRole('alert')).toBeNull()
    notices.dispose()
  })

  it('only changes the archive filter when its separate action is chosen', () => {
    const notices = createSidebarNotices(), undo = vi.fn(async () => {}), showArchived = vi.fn()
    render(<SidebarNotice notices={notices} />)
    act(() => notices.archived({ sessionId: 'C1', undo, showArchived }))
    fireEvent.click(screen.getByRole('button', { name: '筛选已归档会话' }))
    expect(showArchived).toHaveBeenCalledTimes(1)
    expect(undo).not.toHaveBeenCalled()
    expect(notices.getSnapshot()).toBeNull()
    notices.dispose()
  })

  it('restarts identical notices and ignores an old dismissal or action', () => {
    const notices = createSidebarNotices(), oldUndo = vi.fn(async () => {})
    render(<SidebarNotice notices={notices} />)
    act(() => notices.archived({ sessionId: 'C1', undo: oldUndo }))
    const old = notices.getSnapshot()!
    const oldToast = screen.getByRole('alert'), oldDone = observed.onDone
    act(() => notices.archived({ sessionId: 'C2', undo: vi.fn(async () => {}) }))
    act(() => { oldDone(); notices.dismiss(old.seq); old.actions![0].onClick() })
    expect(oldUndo).not.toHaveBeenCalled()
    expect(screen.getByRole('alert')).not.toBe(oldToast)
    act(() => observed.onDone())
    expect(screen.queryByRole('alert')).toBeNull()
    act(() => notices.dispose())
  })

  it.each([false, true])('reports undo failure safely without retrying (committed=%s)', async committed => {
    const notices = createSidebarNotices()
    const undo = vi.fn(async () => { throw Object.assign(new Error('token=secret-should-never-render'), { committed }) })
    render(<SidebarNotice notices={notices} />)
    act(() => notices.archived({ sessionId: 'C1', undo }))
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: '撤销' })) })
    expect(screen.getByRole('alert').textContent).toBe(committed ? '操作已完成，但列表刷新失败。请刷新列表确认。' : '取消归档未完成，请刷新列表确认后重试。')
    expect(document.body.textContent).not.toContain('secret')
    expect(screen.queryByRole('button')).toBeNull()
    expect(undo).toHaveBeenCalledTimes(1)
    notices.dispose()
  })

  it.each(['newer', 'clear', 'dispose'] as const)('ignores pending undo failure after %s', async operation => {
    const notices = createSidebarNotices(), pending = deferred()
    const view = render(<SidebarNotice notices={notices} />)
    act(() => notices.archived({ sessionId: 'C1', undo: () => pending.promise }))
    fireEvent.click(screen.getByRole('button', { name: '撤销' }))
    act(() => {
      if (operation === 'newer') notices.copied(true)
      else notices[operation]()
    })
    await act(async () => { pending.reject(new Error('late private error')); await pending.promise.catch(() => {}) })
    expect(screen.queryByRole('alert')?.textContent ?? null).toBe(operation === 'newer' ? 'Session ID 已复制' : null)
    view.unmount(); notices.dispose()
  })

  it('uses native copy success/failure feedback and its default hold', () => {
    const notices = createSidebarNotices()
    render(<SidebarNotice notices={notices} />)
    act(() => notices.copied(true))
    expect(screen.getByRole('alert').textContent).toBe('Session ID 已复制')
    expect(observed.holdMs).toBeUndefined()
    act(() => notices.copied(false))
    expect(screen.getByRole('alert').textContent).toBe('复制失败，请重试')
    act(() => observed.onDone())
    expect(screen.queryByRole('alert')).toBeNull()
    notices.dispose()
  })

  it('explains why an archived row cannot open without changing its state', () => {
    const notices = createSidebarNotices()
    render(<SidebarNotice notices={notices} />)
    act(() => notices.archivedNotOpenable())
    expect(screen.getByRole('alert').textContent).toBe('已归档对话暂时无法查看，请取消归档后查看')
    expect(screen.queryByRole('button')).toBeNull()
    act(() => notices.dispose())
  })
})
