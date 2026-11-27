// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

/** Reclaim the embedded Web shell's sidebar track without changing native layout state. */
export function mountEmbeddedShell(document: Document): () => void {
  const owned = new Map<HTMLElement, () => void>()
  const scan = () => {
    const live = new Set<HTMLElement>()
    for (const root of document.querySelectorAll<HTMLElement>('[data-slot="root"]')) {
      const frame = root.firstElementChild
      if (!(frame instanceof HTMLElement) || frame.parentElement !== root) continue
      const overlay = frame.querySelector(':scope > [data-shell-overlay]')
      const bottom = frame.querySelector(':scope > [data-shell-bottom]')
      const sidebar = frame.querySelector<HTMLElement>(':scope > div:has(> [data-slot="sidebar"])')
      const main = sidebar?.nextElementSibling
      const mainContent = main?.firstElementChild
      // 0.2.1 renders the main slot directly; 0.2.2 adds one MainPanel wrapper.
      const mainAnchor = mainContent?.matches('[data-slot="main"]') ? mainContent
        : mainContent?.tagName === 'DIV' && mainContent.childElementCount === 1
          && mainContent.firstElementChild?.matches('[data-slot="main"]') ? mainContent.firstElementChild : null
      const rightbar = frame.querySelector<HTMLElement>(':scope > [data-rightbar-col]')
      // These are the public AppFrame seams. Unknown or partial shells stay untouched.
      if (!overlay || !bottom || !sidebar || !(main instanceof HTMLElement) || main.childElementCount !== 1 || !mainAnchor || !rightbar
        || !rightbar.querySelector(':scope > [data-slot="rightbar"]')
        || sidebar.nextElementSibling !== main || main.nextElementSibling !== rightbar
        || !frame.style.gridTemplateColumns) continue
      live.add(frame)
      if (owned.has(frame) || frame.hasAttribute('data-cannbot-embedded-frame')) continue
      const marks: [HTMLElement, string, string][] = [
        [frame, 'data-cannbot-embedded-frame', ''],
        [sidebar, 'data-cannbot-embedded-column', 'sidebar'],
        [main, 'data-cannbot-embedded-column', 'main'],
        [rightbar, 'data-cannbot-embedded-column', 'rightbar'],
      ]
      if (marks.some(([node, name]) => node.hasAttribute(name))) continue
      for (const [node, name, value] of marks) node.setAttribute(name, value)
      owned.set(frame, () => { for (const [node, name, value] of marks) if (node.getAttribute(name) === value) node.removeAttribute(name) })
    }
    for (const [frame, release] of owned) if (!live.has(frame)) { release(); owned.delete(frame) }
  }
  const observer = new MutationObserver(scan)
  observer.observe(document.documentElement, { childList: true, subtree: true })
  scan()
  return () => { observer.disconnect(); for (const release of owned.values()) release(); owned.clear() }
}
