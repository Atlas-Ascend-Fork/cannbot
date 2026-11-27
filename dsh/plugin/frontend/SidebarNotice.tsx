// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { useSyncExternalStore } from 'react'
import { IconWarningOutlineRegular, Toast } from '@deepseek-ai/dsh-client-ui-primitives'

export interface SidebarArchiveNotice {
  sessionId: string
  stopped?: boolean
  /** Capture the originating server and session; undo must only unarchive them. */
  undo(): Promise<void>
  showArchived?(): void
}

interface NoticeAction { label: string; prefix?: string; onClick(): void }
interface Notice {
  seq: number
  text: string
  tone: 'success' | 'warning'
  holdMs?: number
  actions?: readonly NoticeAction[]
  filterAction?: NoticeAction
}

export interface SidebarNotices {
  getSnapshot(): Notice | null
  subscribe(listener: () => void): () => void
  archived(options: SidebarArchiveNotice): void
  archivedNotOpenable(): void
  copied(ok: boolean): void
  clear(): void
  dismiss(seq: number): void
  dispose(): void
}

/** One sidebar's notice identity also bounds asynchronous action feedback. */
export function createSidebarNotices(): SidebarNotices {
  let current: Notice | null = null
  let sequence = 0
  let disposed = false
  const listeners = new Set<() => void>()
  const publish = (notice: Notice | null) => {
    current = notice
    for (const listener of listeners) listener()
  }
  const show = (notice: Omit<Notice, 'seq'>) => {
    if (!disposed) publish({ ...notice, seq: ++sequence })
  }
  const clear = () => {
    sequence++
    if (current) publish(null)
  }
  // Dismiss before invoking, as the native toast does. The identity check also
  // makes stale buttons inert and prevents a double click from repeating a write.
  const action = (seq: number, callback: () => void | Promise<void>, undo = false) => () => {
    if (disposed || current?.seq !== seq) return
    publish(null)
    const reportFailure = (reason: unknown) => {
      if (disposed || sequence !== seq) return
      const committed = !!reason && typeof reason === 'object' && 'committed' in reason && reason.committed === true
      show({
        text: committed ? '操作已完成，但列表刷新失败。请刷新列表确认。'
          : undo ? '取消归档未完成，请刷新列表确认后重试。' : '筛选未完成，请重试。',
        tone: 'warning',
      })
    }
    try { void Promise.resolve(callback()).catch(reportFailure) }
    catch (reason) { reportFailure(reason) }
  }
  return {
    getSnapshot: () => current,
    subscribe(listener) {
      if (!disposed) listeners.add(listener)
      return () => { listeners.delete(listener) }
    },
    archived({ stopped, undo, showArchived }) {
      if (disposed) return
      const seq = sequence + 1
      show({
        text: stopped ? '已停止并归档，可' : '会话已归档，可',
        tone: 'success', holdMs: 6000,
        actions: [{ label: '撤销', onClick: action(seq, undo, true) }],
        ...(showArchived ? { filterAction: { prefix: '或', label: '筛选已归档会话', onClick: action(seq, showArchived) } } : {}),
      })
    },
    copied(ok) { show({ text: ok ? 'Session ID 已复制' : '复制失败，请重试', tone: ok ? 'success' : 'warning' }) },
    archivedNotOpenable() { show({ text: '已归档对话暂时无法查看，请取消归档后查看', tone: 'warning' }) },
    clear,
    dismiss(seq) { if (current?.seq === seq) clear() },
    dispose() { disposed = true; clear(); listeners.clear() },
  }
}

/** Reuse the exact native portal, typography, icon, actions and fade timing. */
export function SidebarNotice({ notices, archivedVisible = false }: { notices: SidebarNotices; archivedVisible?: boolean }) {
  const notice = useSyncExternalStore(notices.subscribe, notices.getSnapshot, notices.getSnapshot)
  if (!notice) return null
  return <Toast key={notice.seq} text={notice.text} holdMs={notice.holdMs}
    {...(notice.tone === 'success' ? { tone: 'success' as const } : { icon: <IconWarningOutlineRegular /> })}
    actions={[...notice.actions ?? [], ...!archivedVisible && notice.filterAction ? [notice.filterAction] : []]}
    onDone={() => notices.dismiss(notice.seq)} />
}
