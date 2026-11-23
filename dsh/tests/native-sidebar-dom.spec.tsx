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
import { afterEach, expect, it, vi } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import * as cordis from '@deepseek-ai/cordis'
import * as slotCore from '@deepseek-ai/dsh-client-ui-slots'
import * as React from 'react'
import * as ReactDOM from 'react-dom'
import * as ReactDOMClient from 'react-dom/client'
import * as jsxRuntime from 'react/jsx-runtime'
import { readFileSync } from 'node:fs'
import type { ReactNode } from 'react'
import { SidebarRoot } from '@dsh-test-source/packages/client/ui-sidebar/src/client/SidebarRoot.tsx'
import { AppFrame } from '@dsh-test-source/packages/client/ui-layout/src/client/AppFrame.tsx'
import { ModeBrandMark } from '../src/client/ModeSidebar.tsx'
import { mountEmbeddedShell } from '../src/client/embedded-shell.ts'
import { WorkspaceTreeBridge } from '../src/client/WorkspaceTreeBridge.tsx'
import { NativeWorkbench, NativeWorkbenchEmpty } from '../src/client/NativeWorkbench.tsx'
import { CANNBOT_HOME } from '../src/client/workspace-modes.ts'
import type { WorkspaceModes } from '../src/client/workspace-modes.ts'

vi.mock('@deepseek-ai/dsh-client-ui-primitives', async () => ({
  ...(await import('@dsh-test-source/packages/client/ui-primitives/src/BrandWordmark.tsx')),
  FishLogo: () => <svg data-testid="native-brand" />, isDarwinDesktop: () => false,
  IconAppsAddOutlineRegular: () => null, IconNewChatOutlineMedium: () => null,
  IconNewChatOutlineRegular: () => null, IconPanelLeftOutlineRegular: () => null,
  Tooltip: ({ children }: { children: ReactNode }) => children, ShortcutKeys: () => null, Menu: () => null,
}))
// Pin persistence is unrelated to placement; SidebarRoot only imports this published constant.
vi.mock('@dsh-test-source/packages/client/ui-sidebar/src/client/panel-pins.ts', () => ({ FIXED_PANEL_ID: 'plugins' }))
afterEach(() => { cleanup(); vi.unstubAllGlobals() })
const moduleURL = import.meta.url
function createSlotsContext(currentSession?: string) {
  // Execute the installed SDK dependency through its real module-loader contract.
  // It includes the upstream selector shim, avoiding unrelated test-only network installs.
  const dependencies: Record<string, unknown> = { react: React, 'react-dom': ReactDOM, 'react-dom/client': ReactDOMClient, 'react/jsx-runtime': jsxRuntime, '@deepseek-ai/cordis': cordis, '@deepseek-ai/dsh-client-ui-slots': slotCore }
  let renderer: { apply(ctx: Context): void } | undefined
  new Function('window', readFileSync(new URL('../node_modules/@deepseek-ai/dsh-client-ui-renderer/lib/client.js', moduleURL), 'utf8'))({ __ModuleLoader__: { load(entry: { factory(require: (id: string) => unknown): typeof renderer }) { renderer = entry.factory(id => { if (!(id in dependencies)) throw new Error('Missing renderer dependency: ' + id); return dependencies[id] }) } } })
  const ctx = new Context(); renderer!.apply(ctx)
  const absent = { key: undefined, hooks: {}, keyedHooks: {}, props: {} }
  const current = currentSession ? { ...absent, key: currentSession } : absent
  const selection = { getSnapshot: () => current, subscribe: () => () => {} }
  const emptySelection = { getSnapshot: () => absent, subscribe: () => () => {} }
  ctx.slots.installScope('session', { current: selection, bindingSource: target => target === undefined ? emptySelection : selection,
    renderArea: (binding, props) => binding.key === undefined ? props.empty?.() : props.children })
  return ctx
}
it('places the brand switch first in official source panel navigation', async () => {
  const ctx = createSlotsContext()
  const listeners = new Set<() => void>()
  let snapshot = { mode: 'deepseek' }
  const modes = { embedded: false, getSnapshot: () => snapshot, subscribe: (listener: () => void) => { listeners.add(listener); return () => listeners.delete(listener) }, setMode: vi.fn((mode: string) => { snapshot = { mode }; listeners.forEach(listener => listener()) }) } as unknown as WorkspaceModes
  const startSession = vi.fn(), noop = () => {}
  const register = ctx.slots.register.bind(ctx.slots) as (options: object, component: (props: any) => ReactNode) => () => void
  register({ name: 'root', children: { sidebar: { kind: 'single', scope: 'root' } } }, ({ renderSlot }) => renderSlot('sidebar', { collapsed: false, width: 280 }))
  register({ name: 'sidebar', children: {
    'sidebar.brand.mark': { kind: 'single', scope: 'root' }, 'sidebar.brand.name': { kind: 'single', scope: 'root' },
    'sidebar.toggle.badge': { kind: 'single', scope: 'root' }, 'sidebar.panellist': { kind: 'list', scope: 'root' },
    'sidebar.panellist.actions': { kind: 'list', scope: 'root' }, 'sidebar.workspaces': { kind: 'single', scope: 'root' },
    'sidebar.settings': { kind: 'single', scope: 'root' }, 'sidebar.footer.action': { kind: 'list', scope: 'root' },
  } }, props => <SidebarRoot {...props} startSession={startSession} toggleSidebar={noop} selectPanel={noop} setPinned={noop} trackEntryClick={noop} usePanels={(select: any) => select([{ id: 'plugins', label: '插件' }, { id: 'schedules', label: '自动化任务' }])} useEntryPins={(select: any) => select([])} useEntryActions={(select: any) => select(false)} useShortcuts={(select: any) => select([])} usePanelInfo={(select: any) => select({ activePanelId: null })} t={((key: string) => key === 'session.new.label' || key === 'session.new' ? '新会话' : 'DeepSeek Harness') as never} />)
  register({ name: 'sidebar.panellist', id: 'plugins', label: '插件' }, () => <svg />)
  register({ name: 'sidebar.panellist', id: 'schedules', label: '自动化任务' }, () => <svg />)
  const stop = register({ name: 'sidebar.brand.mark', priority: -100 }, props => <ModeBrandMark {...props} modes={modes} />)
  const view = render(ctx.slots.renderSlot('root', {}))
  await act(async () => {})
  const switchMode = screen.getByRole('button', { name: 'CANNBot', exact: true })
  expect(switchMode.closest('[aria-hidden="true"]')).toBeNull(); expect(switchMode.parentElement?.closest('button')).toBeNull()
  const sidebar = view.container.querySelector('[data-slot="sidebar"]')!
  const host = sidebar.querySelector('[data-cannbot-mode-switch-host]')!
  expect(host.parentElement?.tagName).toBe('NAV')
  expect(host.parentElement?.firstElementChild).toBe(host)
  expect(host.nextElementSibling?.textContent).toContain('插件')
  expect(host.textContent).toBe('CANNBot')
  fireEvent.click(switchMode)
  expect(modes.setMode).toHaveBeenCalledWith('cannbot'); expect(startSession).not.toHaveBeenCalled()
  const returnToDeepSeek = screen.getByTitle('返回原生工作台')
  expect(returnToDeepSeek.getAttribute('aria-label')).toBe('返回原生工作台')
  expect(returnToDeepSeek.textContent).toBe('返回原生工作台')
  expect(returnToDeepSeek.querySelector('svg')).not.toBeNull()
  expect(returnToDeepSeek.querySelector('[data-testid="native-brand"]')).toBeNull()
  fireEvent.click(returnToDeepSeek)
  expect(modes.setMode).toHaveBeenLastCalledWith('deepseek'); expect(startSession).not.toHaveBeenCalled()
  fireEvent.click(sidebar.querySelector('[data-slot="sidebar.brand.mark"]')!.closest('button')!)
  expect(startSession).toHaveBeenCalledOnce()
  expect(screen.queryByRole('tablist')).toBeNull()
  await act(async () => { stop() })
  expect(sidebar.querySelector('[data-cannbot-mode-switch-host]')).toBeNull()
  expect(sidebar.querySelector('[data-slot-error]')).toBeNull()
  view.unmount(); await ctx.fiber.dispose()
})

it('renders an explicitly absent CANN home through the SDK renderer while a DSH session is current', async () => {
  const ctx = createSlotsContext('OLD_DSH_SESSION'), noop = () => () => {}
  const register = ctx.slots.register.bind(ctx.slots) as (options: object, component: (props: any) => ReactNode) => () => void
  const state = { mode: 'cannbot', ready: true, selectedWorkspaceId: '', serverId: '', workspaces: [], sessions: [], navigationError: '' }
  const modes = { getSnapshot: () => state, subscribe: noop } as unknown as WorkspaceModes
  const prepared = { workspaceId: '', busy: false, error: '' }, panel = { activePanelId: CANNBOT_HOME }
  const preparation = { getSnapshot: () => prepared, subscribe: noop, selectWorkspace: vi.fn(), retry: vi.fn(), dispose: vi.fn() }
  const scoped = { layout: { panelInfo: { getSnapshot: () => panel, subscribe: noop } } } as unknown as Context
  register({ name: 'root', children: { main: { kind: 'keyed', scope: 'root' } } }, ({ renderSlot }) => renderSlot('main', {}, { entryKey: CANNBOT_HOME }))
  register({ name: 'main', key: CANNBOT_HOME, children: { 'cannbot.workbench.content': { kind: 'single', scope: 'session-maybe' } } }, props => <NativeWorkbench {...props} ctx={scoped} modes={modes} preparation={preparation as never} />)
  register({ name: 'cannbot.workbench.content' }, NativeWorkbenchEmpty)
  ctx.slots.registerFactory({ name: 'conversation.content', scope: 'session-maybe' }, props => <div data-testid="native-factory-binding">{props.sessionId || 'ABSENT'}</div>)
  const view = render(ctx.slots.renderSlot('root', {})); await act(async () => {})
  expect(screen.getByTestId('native-factory-binding').textContent).toBe('ABSENT')
  expect(view.container.querySelector('[data-slot-error]')).toBeNull()
  expect(preparation.selectWorkspace).not.toHaveBeenCalled()
  view.unmount(); await ctx.fiber.dispose()
})

it('keeps native ownership with official source AppFrame and SidebarRoot topology', async () => {
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} })
  const ctx = createSlotsContext(), noop = () => {}, nativeMounted = vi.fn(), nativeUnmounted = vi.fn()
  const listeners = new Set<() => void>(), modeListeners = new Set<() => void>()
  let width = 280, mode = { mode: 'deepseek' }
  const modes = { getSnapshot: () => mode, subscribe(listener: () => void) { modeListeners.add(listener); return () => modeListeners.delete(listener) } } as unknown as WorkspaceModes
  const setMode = (value: string) => { mode = { mode: value }; modeListeners.forEach(listener => listener()) }
  const setWidth = (value: number) => { width = value; listeners.forEach(listener => listener()) }
  const subscribe = (listener: () => void) => { listeners.add(listener); return () => listeners.delete(listener) }
  const register = ctx.slots.register.bind(ctx.slots) as (options: object, component: (props: any) => ReactNode) => () => void
  register({ name: 'root', children: { sidebar: { kind: 'single', scope: 'root' }, main: { kind: 'keyed', scope: 'root' }, rightbar: { kind: 'single', scope: 'root' }, 'shell.bottom': { kind: 'list', scope: 'root' }, 'shell.overlay': { kind: 'list', scope: 'root' }, 'shell.leading': { kind: 'list', scope: 'root' } } }, function Root(props) {
    const sidebar = React.useSyncExternalStore(subscribe, () => width)
    const layoutInfo = { sidebar, viewportWidth: 1280, narrowExpanded: false, rightbar: 420, rightbarShown: true, rightbarTrack: true, rightbarFullscreen: false, rightbarInstant: false }
    return <AppFrame {...props} useFoldedLandscape={(select: any) => select(false)} useStore={(select: any) => select({ layoutInfo })} usePanelInfo={(select: any) => select({ activePanelId: null })} useSessions={(select: any) => select({ byId: {} })} actions={{ setViewportWidth: noop } as never} t={(() => 'DSH') as never} />
  })
  register({ name: 'sidebar', children: {
    'sidebar.brand.mark': { kind: 'single', scope: 'root' }, 'sidebar.brand.name': { kind: 'single', scope: 'root' },
    'sidebar.toggle.badge': { kind: 'single', scope: 'root' }, 'sidebar.panellist': { kind: 'list', scope: 'root' }, 'sidebar.panellist.actions': { kind: 'list', scope: 'root' },
    'sidebar.workspaces': { kind: 'single', scope: 'root' }, 'sidebar.settings': { kind: 'single', scope: 'root' }, 'sidebar.footer.action': { kind: 'list', scope: 'root' },
  } }, props => <SidebarRoot {...props} startSession={noop} toggleSidebar={noop} selectPanel={noop} setPinned={noop} trackEntryClick={noop} usePanels={(s: any) => s([])} useEntryPins={(s: any) => s([])} useEntryActions={(s: any) => s(false)} useShortcuts={(s: any) => s([])} usePanelInfo={(s: any) => s({ activePanelId: null })} t={((key: string) => key) as never} />)
  register({ name: 'sidebar.workspaces' }, function Native() { React.useEffect(() => { nativeMounted(); return nativeUnmounted }, []); return <button>原生添加工作区</button> })
  register({ name: 'main', key: 'conversation' }, () => <main>native main</main>)
  register({ name: 'rightbar' }, () => <aside>native rightbar</aside>)
  const stop = register({ name: 'shell.overlay', id: 'bridge' }, () => <WorkspaceTreeBridge modes={modes}>{wide => <div>CANNBot {wide ? '展开' : '收起'}</div>}</WorkspaceTreeBridge>)
  const view = render(ctx.slots.renderSlot('root', {})); await act(async () => {})
  const frame = view.container.querySelector('[data-slot="root"]')!.firstElementChild!, anchor = view.container.querySelector('[data-slot="sidebar.workspaces"]')!
  expect(frame.hasAttribute('data-sidebar-collapsed')).toBe(false)
  const native = screen.getByRole('button', { name: '原生添加工作区' })
  expect(view.container.querySelector('[data-cannbot-workspace-tree-host]')).not.toBeNull()
  for (let i = 0; i < 3; i++) {
    await act(async () => setMode('cannbot'))
    expect(anchor.hasAttribute('data-cannbot-workspaces-hidden')).toBe(true)
    expect(view.container.querySelector('[data-cannbot-workspaces-active]')?.textContent).toBe('CANNBot 展开')
    await act(async () => setWidth(0))
    expect(frame.getAttribute('data-sidebar-collapsed')).toBe('true')
    expect(view.container.querySelector('[data-cannbot-workspaces-active]')?.textContent).toBe('CANNBot 收起')
    await act(async () => setWidth(280))
    await act(async () => setMode('deepseek'))
    expect(screen.getByRole('button', { name: '原生添加工作区' })).toBe(native)
    expect(anchor.hasAttribute('data-cannbot-workspaces-hidden')).toBe(false)
    expect(frame.hasAttribute('data-sidebar-collapsed')).toBe(false)
  }
  expect(nativeMounted).toHaveBeenCalledOnce(); expect(nativeUnmounted).not.toHaveBeenCalled()
  await act(async () => { stop() }); expect(view.container.querySelector('[data-cannbot-workspace-tree-host]')).toBeNull()
  view.unmount(); await ctx.fiber.dispose()
})

it.each([0, 280])('reclaims the embedded sidebar with official source AppFrame DOM while preserving overlay/rightbar (width %s)', async sidebarWidth => {
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} })
  const ctx = createSlotsContext()
  const register = ctx.slots.register.bind(ctx.slots) as (options: object, component: (props: any) => ReactNode) => () => void
  const layoutInfo = { sidebar: sidebarWidth, viewportWidth: 1280, narrowExpanded: false, rightbar: 420, rightbarShown: true, rightbarTrack: true, rightbarFullscreen: false, rightbarInstant: false }
  register({ name: 'root', children: { sidebar: { kind: 'single', scope: 'root' }, main: { kind: 'keyed', scope: 'root' }, rightbar: { kind: 'single', scope: 'root' }, 'shell.bottom': { kind: 'list', scope: 'root' }, 'shell.overlay': { kind: 'list', scope: 'root' }, 'shell.leading': { kind: 'list', scope: 'root' } } }, props => <AppFrame {...props} useFoldedLandscape={(select: (value: boolean) => unknown) => select(false)} useStore={select => select({ layoutInfo } as never)} usePanelInfo={select => select({ activePanelId: null })} useSessions={select => select({ byId: {} } as never)} actions={{ setViewportWidth() {} } as never} t={(() => 'DSH') as never} />)
  register({ name: 'sidebar' }, () => <button>inner sidebar</button>)
  register({ name: 'main', key: 'conversation' }, () => <main>remote session</main>)
  register({ name: 'rightbar' }, () => <aside>remote tools</aside>)
  register({ name: 'shell.overlay', id: 'creation' }, () => <dialog open aria-label="create workspace">modal</dialog>)
  const style = document.createElement('style'); style.textContent = readFileSync(new URL('../src/client/modes.css', moduleURL), 'utf8'); document.head.append(style)
  const stop = mountEmbeddedShell(document)
  const view = render(ctx.slots.renderSlot('root', {}))
  await act(async () => {})
  const frame = view.container.querySelector<HTMLElement>('[data-cannbot-embedded-frame]')!
  expect(frame).not.toBeNull()
  const inline = frame.getAttribute('style'), side = frame.querySelector<HTMLElement>('[data-cannbot-embedded-column="sidebar"]')!, main = frame.querySelector<HTMLElement>('[data-cannbot-embedded-column="main"]')!, right = frame.querySelector<HTMLElement>('[data-rightbar-col]')!
  expect(getComputedStyle(side).display).toBe('none')
  expect(getComputedStyle(main).gridColumn).toBe('1 / 3')
  expect(getComputedStyle(right).gridColumn).toBe('3 / 4')
  expect(frame.style.gridTemplateColumns.startsWith(sidebarWidth === 0 ? '56px ' : '280px ')).toBe(true)
  expect(frame.querySelector('[data-shell-overlay]')?.contains(screen.getByRole('dialog', { name: 'create workspace' }))).toBe(true)
  expect(getComputedStyle(right).display).not.toBe('none')
  // Unknown/partial structure is never hidden, and can recover after the expected seam returns.
  const anchor = right.firstElementChild!; anchor.remove(); await act(async () => {})
  expect(frame.hasAttribute('data-cannbot-embedded-frame')).toBe(false)
  right.append(anchor); await act(async () => {})
  expect(frame.hasAttribute('data-cannbot-embedded-frame')).toBe(true)
  stop(); stop()
  expect(frame.hasAttribute('data-cannbot-embedded-frame')).toBe(false)
  expect(main.hasAttribute('data-cannbot-embedded-column')).toBe(false)
  expect(frame.getAttribute('style')).toBe(inline)
  expect(screen.getByRole('dialog', { name: 'create workspace' })).toBeTruthy()
  view.unmount(); await ctx.fiber.dispose(); style.remove()
})
