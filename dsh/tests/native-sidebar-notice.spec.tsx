// ----------------------------------------------------------------------------------------------------------
// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.
// ----------------------------------------------------------------------------------------------------------

import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createSidebarNotices, SidebarNotice } from '../src/client/SidebarNotice.tsx'

// The test-only facade exports upstream Toast source unchanged, including
// its CSS, portal, action buttons and timers. No primitive mock in this suite.
afterEach(() => { cleanup(); vi.useRealTimers() })

describe('native Toast integration', () => {
  it('portals outside the sidebar and preserves the six second hold across filter updates', () => {
    vi.useFakeTimers()
    const notices = createSidebarNotices()
    const view = render(<div style={{ transform: 'translateX(1px)' }}><SidebarNotice notices={notices} /></div>)
    act(() => notices.archived({ sessionId: 'C1', undo: async () => {}, showArchived() {} }))
    const toast = screen.getByRole('alert')
    expect(toast.parentElement).toBe(document.body)
    expect(view.container.contains(toast)).toBe(false)
    expect(toast.textContent).toBe('会话已归档，可撤销或筛选已归档会话')
    expect(toast.style.getPropertyValue('--dsh-toast-hold')).toBe('6000ms')
    act(() => vi.advanceTimersByTime(4000))
    view.rerender(<div><SidebarNotice notices={notices} archivedVisible /></div>)
    expect(screen.getByRole('alert')).toBe(toast)
    expect(screen.queryByRole('button', { name: '筛选已归档会话' })).toBeNull()
    act(() => vi.advanceTimersByTime(2999))
    expect(screen.getByRole('alert')).toBe(toast)
    act(() => vi.advanceTimersByTime(1))
    expect(screen.queryByRole('alert')).toBeNull()
    notices.dispose()
  })

  it('remounts repeated notices and leaves the new one intact when the original timer would finish', () => {
    vi.useFakeTimers()
    const notices = createSidebarNotices()
    render(<SidebarNotice notices={notices} />)
    act(() => notices.copied(true))
    const first = screen.getByRole('alert')
    expect(first.style.getPropertyValue('--dsh-toast-hold')).toBe('3000ms')
    act(() => vi.advanceTimersByTime(3500))
    act(() => notices.copied(true))
    expect(screen.getByRole('alert')).not.toBe(first)
    act(() => vi.advanceTimersByTime(3999))
    expect(screen.getByRole('alert').textContent).toBe('Session ID 已复制')
    act(() => vi.advanceTimersByTime(1))
    expect(screen.queryByRole('alert')).toBeNull()
    notices.dispose()
  })

  it('runs undo through the native action without opening a session or resuming stopped work', async () => {
    const notices = createSidebarNotices(), undo = vi.fn(async () => {})
    render(<SidebarNotice notices={notices} />)
    act(() => notices.archived({ sessionId: 'server/session', stopped: true, undo }))
    expect(screen.getByRole('alert').textContent).toBe('已停止并归档，可撤销')
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: '撤销' })) })
    expect(undo).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole('alert')).toBeNull()
    notices.dispose()
  })
})
