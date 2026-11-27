// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { useLayoutEffect, useMemo, useState, useSyncExternalStore, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import type { WorkspaceModes } from './workspace-modes.ts'
import './workspace-tree-bridge.css'

type Target = { anchor: HTMLElement; host: HTMLDivElement; frame: HTMLElement; wide: boolean }
const HIDDEN = 'data-cannbot-workspaces-hidden'

function findFrame(anchor: HTMLElement): HTMLElement | null {
  const sidebar = anchor.closest<HTMLElement>('[data-slot="sidebar"]')
  const root = sidebar?.firstElementChild, region = anchor.parentElement
  const column = sidebar?.parentElement, frame = column?.parentElement
  const main = column?.nextElementSibling, rightbar = main?.nextElementSibling
  // AppFrame omits data-sidebar-collapsed while expanded (both desktop rc.5
  // and remote rc.1). Find the owning frame by its public slots, not by an
  // attribute which only exists in the collapsed state.
  // Newer 0.2.2 sidebars wrap the workspace region in shared scrolling
  // containers. The public workspace seat still belongs to this sidebar;
  // its depth is not part of the slot contract.
  if (!(root instanceof HTMLElement) || !region || !root.contains(region)
    || !frame?.parentElement?.matches('[data-slot="root"]')
    || column?.firstElementChild !== sidebar || !frame.style.gridTemplateColumns
    || !main?.querySelector('[data-slot="main"]') || !rightbar?.matches('[data-rightbar-col]')
    || !rightbar.querySelector(':scope > [data-slot="rightbar"]')
    || !frame.querySelector(':scope > [data-shell-overlay]') || !frame.querySelector(':scope > [data-shell-bottom]')
    || region.querySelectorAll('[data-slot="sidebar.workspaces"]').length !== 1
    || region.querySelector('[data-slot="main"], [data-slot="sidebar.settings"]')) return null
  const collapsed = frame.getAttribute('data-sidebar-collapsed')
  return collapsed === null || collapsed === 'true' || collapsed === 'false' ? frame : null
}

/**
 * Keep the native WorkspaceBrowser mounted: its private search request counter
 * outlives its component, so replacing its slot replays old search requests.
 * The public slot anchor is the visibility boundary; native children and their
 * React ownership, local state, directory flows and menus remain untouched.
 */
export function WorkspaceTreeBridge({ modes, children }: {
  modes: Pick<WorkspaceModes, 'getSnapshot' | 'subscribe'>
  children(wide: boolean): ReactNode
}) {
  const source = useMemo(() => ({ getSnapshot: () => modes.getSnapshot().mode, subscribe: (listener: () => void) => modes.subscribe(listener) }), [modes])
  const mode = useSyncExternalStore(source.subscribe, source.getSnapshot)
  const [target, setTarget] = useState<Target | null>(null)
  useLayoutEffect(() => {
    let current: Target | null = null
    const scan = () => {
      const candidates = [...document.querySelectorAll<HTMLElement>('[data-slot="sidebar.workspaces"]')].filter(anchor => findFrame(anchor) !== null)
      const anchor = candidates.length === 1 ? candidates[0]! : null
      const frame = anchor ? findFrame(anchor) : null
      if (current && (current.anchor !== anchor || !current.host.isConnected || current.host.previousElementSibling !== anchor)) {
        current.host.remove(); current = null
      }
      if (anchor && frame && !current) {
        const host = document.createElement('div')
        host.dataset.cannbotWorkspaceTreeHost = ''
        anchor.after(host)
        current = { anchor, host, frame, wide: frame.getAttribute('data-sidebar-collapsed') !== 'true' }
      }
      const wide = current?.frame.getAttribute('data-sidebar-collapsed') !== 'true'
      if (current && current.wide !== wide) current = { ...current, wide }
      setTarget(previous => previous?.anchor === current?.anchor && previous?.host === current?.host && previous?.wide === current?.wide ? previous : current)
    }
    const observer = new MutationObserver(scan)
    observer.observe(document.documentElement, { childList: true, subtree: true, attributes: true, attributeFilter: ['data-sidebar-collapsed'] })
    scan()
    return () => { observer.disconnect(); current?.host.remove() }
  }, [])
  useLayoutEffect(() => {
    if (!target || mode !== 'cannbot') return
    const { anchor, host } = target
    // Never overwrite another owner's visibility/a11y state. Restore precisely
    // what was present when CANNBot took over this region.
    const inert = anchor.getAttribute('inert'), aria = anchor.getAttribute('aria-hidden')
    if (anchor.hasAttribute(HIDDEN)) return
    anchor.setAttribute(HIDDEN, '')
    anchor.setAttribute('inert', '')
    anchor.setAttribute('aria-hidden', 'true')
    host.setAttribute('data-cannbot-workspaces-active', '')
    return () => {
      anchor.removeAttribute(HIDDEN)
      if (anchor.getAttribute('inert') === '') inert === null ? anchor.removeAttribute('inert') : anchor.setAttribute('inert', inert)
      if (anchor.getAttribute('aria-hidden') === 'true') aria === null ? anchor.removeAttribute('aria-hidden') : anchor.setAttribute('aria-hidden', aria)
      host.removeAttribute('data-cannbot-workspaces-active')
    }
  }, [target, mode])
  return target ? createPortal(children(target.wide), target.host) : null
}
