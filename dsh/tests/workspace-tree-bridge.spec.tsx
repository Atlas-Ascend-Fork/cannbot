// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { useEffect, useState, type ReactNode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { WorkspaceTreeBridge } from '../src/client/WorkspaceTreeBridge.tsx'
import type { WorkspaceModes } from '../src/client/workspace-modes.ts'

afterEach(cleanup)
function PublicFrame({ children, bridge, collapsed }: { children: ReactNode; bridge: ReactNode; collapsed?: string }) {
  return <div data-slot="root"><div data-sidebar-collapsed={collapsed} style={{ gridTemplateColumns: '280px minmax(0,1fr) 0px' }}>
    <div><div data-slot="sidebar"><div>{children}</div></div></div><div><div data-slot="main" /></div><div data-rightbar-col><div data-slot="rightbar" /></div>
    <div data-shell-bottom /><div data-shell-overlay>{bridge}</div>
  </div></div>
}
function modesStore() {
  let snapshot = { mode: 'deepseek' as 'deepseek' | 'cannbot' }
  const listeners = new Set<() => void>()
  const modes = { getSnapshot: () => snapshot, subscribe(listener: () => void) { listeners.add(listener); return () => listeners.delete(listener) } }
  return { modes: modes as Pick<WorkspaceModes, 'getSnapshot' | 'subscribe'>, set(mode: typeof snapshot.mode) { snapshot = { mode }; listeners.forEach(listener => listener()) } }
}

describe('native workspace tree preservation', () => {
  it('keeps remote server actions available inside the 0.2.2 shared scroll containers', async () => {
    const state = modesStore(), connect = vi.fn()
    function Shell({ collapsed = false }: { collapsed?: boolean }) {
      return <PublicFrame collapsed={collapsed ? 'true' : undefined} bridge={<WorkspaceTreeBridge modes={state.modes}>{wide => <section aria-label="服务器">{wide && <><button onClick={connect}>连接 DevEnv950</button><button>新增服务器</button></>}</section>}</WorkspaceTreeBridge>}>
        <div><div data-sidebar-scrollport={collapsed ? undefined : ''}><nav aria-label="全局面板" /><div><div data-slot="sidebar.workspaces"><button>原生添加工作区</button></div></div></div><span aria-hidden="true" /></div>
      </PublicFrame>
    }
    const view = render(<Shell />)
    await act(async () => {})
    const native = screen.getByRole('button', { name: '原生添加工作区' })
    act(() => state.set('cannbot'))
    expect(screen.queryByRole('button', { name: '原生添加工作区' })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: '连接 DevEnv950' }))
    expect(connect).toHaveBeenCalledOnce()
    expect(screen.getByRole('button', { name: '新增服务器' })).toBeTruthy()
    view.rerender(<Shell collapsed />)
    await act(async () => {})
    expect(screen.queryByRole('button', { name: '连接 DevEnv950' })).toBeNull()
    view.rerender(<Shell />)
    await act(async () => {})
    expect(screen.getByRole('button', { name: '连接 DevEnv950' })).toBeTruthy()
    act(() => state.set('deepseek'))
    expect(screen.getByRole('button', { name: '原生添加工作区' })).toBe(native)
    expect(native.closest('[aria-hidden="true"]')).toBeNull()
  })

  it('keeps the exact native instance and consumed search request through repeated mode changes', async () => {
    const state = modesStore(), mounted = vi.fn(), unmounted = vi.fn()
    function NativeTree() {
      const [search, setSearch] = useState(false), [query, setQuery] = useState('')
      useEffect(() => { mounted(); setSearch(true); return unmounted }, [])
      return <div>{search ? <><input aria-label="原生搜索" value={query} onChange={event => setQuery(event.target.value)} /><button onClick={() => { setQuery(''); setSearch(false) }}>清除搜索</button></> : <><h2>工作区</h2><button>视图选项</button><button>添加工作区</button></>}</div>
    }
    function Shell({ bridge = true, collapsed = false }: { bridge?: boolean; collapsed?: boolean }) {
      return <PublicFrame collapsed={collapsed ? 'true' : undefined} bridge={bridge && <WorkspaceTreeBridge modes={state.modes}>{wide => <div>CANNBot {wide ? '列表' : '收起'}</div>}</WorkspaceTreeBridge>}><div><div data-slot="sidebar.workspaces" style={{ display: 'contents' }}><NativeTree /></div></div></PublicFrame>
    }
    const view = render(<Shell />)
    await act(async () => {})
    fireEvent.click(screen.getByRole('button', { name: '清除搜索' }))
    const anchor = view.container.querySelector<HTMLElement>('[data-slot="sidebar.workspaces"]')!, native = anchor.firstElementChild
    for (let attempt = 0; attempt < 4; attempt++) {
      act(() => state.set('cannbot'))
      expect(anchor.hasAttribute('inert')).toBe(true)
      expect(screen.queryByRole('button', { name: '添加工作区' })).toBeNull()
      expect(view.container.querySelector('[data-cannbot-workspaces-active]')?.textContent).toBe('CANNBot 列表')
      act(() => state.set('deepseek'))
      expect(screen.getByRole('button', { name: '视图选项' })).toBeTruthy()
      expect(screen.queryByRole('textbox', { name: '原生搜索' })).toBeNull()
      expect(anchor.firstElementChild).toBe(native)
    }
    expect(mounted).toHaveBeenCalledOnce(); expect(unmounted).not.toHaveBeenCalled()
    expect(anchor.getAttribute('style')).toBe('display: contents;')
    act(() => state.set('cannbot'))
    view.rerender(<Shell collapsed />)
    await act(async () => {})
    expect(view.container.querySelector('[data-cannbot-workspaces-active]')?.textContent).toBe('CANNBot 收起')
    expect(anchor.firstElementChild).toBe(native)
    view.rerender(<Shell bridge={false} />)
    expect(anchor.hasAttribute('inert')).toBe(false)
    expect(anchor.hasAttribute('aria-hidden')).toBe(false)
    expect(anchor.hasAttribute('data-cannbot-workspaces-hidden')).toBe(false)
    expect(view.container.querySelector('[data-cannbot-workspace-tree-host]')).toBeNull()
    expect(mounted).toHaveBeenCalledOnce(); expect(unmounted).not.toHaveBeenCalled()
  })

  it('retains an expanded native search and its entered query without reading its state', async () => {
    const state = modesStore()
    function NativeTree() { const [query, setQuery] = useState(''); return <input aria-label="原生搜索" value={query} onChange={event => setQuery(event.target.value)} /> }
    render(<PublicFrame bridge={<WorkspaceTreeBridge modes={state.modes}>{() => <span>CANNBot</span>}</WorkspaceTreeBridge>}><div><div data-slot="sidebar.workspaces"><NativeTree /></div></div></PublicFrame>)
    await act(async () => {})
    const input = screen.getByRole('textbox', { name: '原生搜索' }) as HTMLInputElement
    fireEvent.change(input, { target: { value: '已输入查询' } })
    act(() => state.set('cannbot')); act(() => state.set('deepseek'))
    expect(screen.getByRole('textbox', { name: '原生搜索' })).toBe(input)
    expect(input.value).toBe('已输入查询')
  })

  it('restores preexisting accessibility attributes and follows a replaced public seat', async () => {
    const state = modesStore(); state.set('cannbot')
    function Shell({ id }: { id: number }) { return <PublicFrame bridge={<WorkspaceTreeBridge modes={state.modes}>{() => <span>CANNBot</span>}</WorkspaceTreeBridge>}><div key={id}><div data-slot="sidebar.workspaces" ref={node => { node?.setAttribute('inert', '') }} aria-hidden="false"><button>Native</button></div></div></PublicFrame> }
    const view = render(<Shell id={1} />); await act(async () => {})
    const old = view.container.querySelector('[data-slot="sidebar.workspaces"]')!
    expect(old.getAttribute('aria-hidden')).toBe('true')
    view.rerender(<Shell id={2} />); await act(async () => {})
    expect(old.hasAttribute('data-cannbot-workspaces-hidden')).toBe(false)
    expect(old.getAttribute('aria-hidden')).toBe('false'); expect(old.hasAttribute('inert')).toBe(true)
    expect(view.container.querySelectorAll('[data-cannbot-workspace-tree-host]')).toHaveLength(1)
    act(() => state.set('deepseek'))
    const next = view.container.querySelector('[data-slot="sidebar.workspaces"]')!
    expect(next.getAttribute('aria-hidden')).toBe('false'); expect(next.hasAttribute('inert')).toBe(true)
  })

  it.each(['ambiguous', 'unknown geometry'])('does not hide native content with %s public seams', async kind => {
    const state = modesStore(); state.set('cannbot')
    const anchor = <div data-slot="sidebar.workspaces"><button>Native</button></div>
    const view = render(<PublicFrame collapsed={kind === 'ambiguous' ? undefined : 'unknown'} bridge={<WorkspaceTreeBridge modes={state.modes}>{() => <span>CANNBot</span>}</WorkspaceTreeBridge>}><div>{anchor}{kind === 'ambiguous' && <div data-slot="sidebar.workspaces" />}</div></PublicFrame>)
    await act(async () => {})
    expect(view.container.querySelector('[data-cannbot-workspaces-hidden]')).toBeNull()
    expect(view.container.querySelector('[data-cannbot-workspace-tree-host]')).toBeNull()
    expect(screen.getByRole('button', { name: 'Native' })).toBeTruthy()
  })
})
