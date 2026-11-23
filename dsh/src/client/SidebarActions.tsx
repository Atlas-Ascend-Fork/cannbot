// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { useEffect, useRef, useState, type ReactNode } from 'react'
import {
  Button, IconArchiveOutlineRegular, IconArchiveOffOutlineRegular, IconArchiveCheckOutlineRegular, IconBranchOutlineRegular, IconCopyOutlineRegular,
  IconEditOutlineRegular, IconEllipsisOutlineRegular, IconPinFillRegular, IconPinOutlineRegular,
  IconQueueOutlineRegular, IconSlidersTwoOutlineRegular, IconTrashOutlineRegular, IconUnarchiveOutlineRegular, Menu, MenuItemButton, Modal, Tooltip,
} from '@deepseek-ai/dsh-client-ui-primitives'
import type { CANNBotWorkspaceOperation } from '../workspace-mode-types.ts'
import { InitializationDialog } from './InitializationDialog.tsx'
import { WORKFLOWS } from '../workflows.ts'
import { zh } from './locales.ts'

export type SidebarOperation = (operation: CANNBotWorkspaceOperation) => Promise<void>
export interface SidebarReadback { revision: number; refresh(): Promise<void> }
export interface SidebarSession { id: string; title: string; workspaceId: string; updatedAt?: number | string; pinned?: boolean; archived?: boolean; pinOrder?: number; blank?: boolean; running?: boolean; frozen?: boolean }
export interface SidebarWorkspace { workspaceId: string; title: string; path: string; pluginId?: string }
export type ArchivedFilter = 'default' | 'show' | 'only'

export function ArchivedViewMenu({ value, change }: { value: ArchivedFilter; change(value: ArchivedFilter): void }) {
  const [open, setOpen] = useState(false)
  return <Menu open={open} onClose={() => setOpen(false)} align="end" dense portal selectedId={value} items={[
    { type: 'label', id: 'filter-by', text: '筛选会话' },
    { id: 'default', label: '隐藏已归档', icon: <IconArchiveOffOutlineRegular /> },
    { id: 'show', label: '全部对话（显示已归档）', icon: <IconQueueOutlineRegular /> },
    { id: 'only', label: '仅显示已归档', icon: <IconArchiveCheckOutlineRegular /> },
  ]} onSelect={id => { if (id === 'default' || id === 'show' || id === 'only') change(id); setOpen(false) }} anchor={<Tooltip label="视图选项" side="bottom" delayMs={500}><button type="button" className="cb-toolbar-button" aria-label="视图选项" onClick={() => setOpen(value => !value)}><IconSlidersTwoOutlineRegular size={16} /></button></Tooltip>} />
}

/** The native browser owns its child slots; use the same public menu controls here. */
export function MoreMenu({ label, disabled, children, className = '' }: { label: string; disabled?: boolean; children(close: () => void): ReactNode; className?: string }) {
  const [open, setOpen] = useState(false)
  return <Menu open={open} onClose={() => setOpen(false)} portal closeOnPointerLeave align="start" anchor={<button className={`cb-project-action ${className}`} type="button" aria-label={label} aria-haspopup="menu" aria-expanded={open} disabled={disabled} onClick={event => { event.stopPropagation(); setOpen(value => !value) }}><IconEllipsisOutlineRegular size={16} /></button>}>
    {children(() => setOpen(false))}
  </Menu>
}

function message(reason: unknown, fallback: string) { return reason instanceof Error && reason.message ? reason.message : fallback }

function useActionError(readback?: SidebarReadback, recovered?: () => void) {
  const [error, setError] = useState<{ message: string; committed: boolean; revision: number } | null>(null)
  const current = useRef(readback); current.current = readback
  useEffect(() => {
    if (error?.committed && readback && readback.revision > error.revision) { setError(null); recovered?.() }
  }, [error, readback?.revision, recovered])
  return {
    error,
    clear: () => setError(null),
    report: (reason: unknown, fallback: string) => setError({ message: message(reason, fallback), committed: !!reason && typeof reason === 'object' && 'committed' in reason && reason.committed === true, revision: current.current?.revision ?? 0 }),
  }
}

/** Retry only the read after a committed write; never run the mutation again. */
function RefreshListButton({ readback }: { readback: SidebarReadback }) {
  const [busy, setBusy] = useState(false), [failed, setFailed] = useState(false)
  const pending = useRef(false)
  const refresh = async () => {
    if (pending.current) return
    pending.current = true; setBusy(true); setFailed(false)
    try { await readback.refresh() }
    catch { setFailed(true) }
    finally { pending.current = false; setBusy(false) }
  }
  return <><Button variant="outline" disabled={busy} onClick={() => void refresh()}>{busy ? '正在刷新…' : '刷新列表'}</Button>{failed && <span role="alert"> 刷新未完成，请重试刷新列表。</span>}</>
}

export function RenameDialog({ title, field, initial, save, close, allowEmpty = false, allowUnchanged = false, description, maxLength = 2000, readback, actionLabel = '重命名', validate }: {
  title: string; field: string; initial: string; save(value: string): Promise<void>; close(): void; allowEmpty?: boolean; description?: string; maxLength?: number;
  readback?: SidebarReadback; allowUnchanged?: boolean; actionLabel?: string; validate?(value: string): string | undefined;
}) {
  const [value, setValue] = useState(initial), [busy, setBusy] = useState(false)
  const { error, clear, report } = useActionError(readback, close)
  const saving = useRef(false), composing = useRef(false)
  const validation = validate?.(value.trim())
  const blocked = busy || !!error?.committed || (!allowEmpty && !value.trim()) || (!allowUnchanged && value.trim() === initial.trim()) || !!validation
  const confirm = async () => {
    if (blocked || saving.current) return
    saving.current = true; setBusy(true); clear()
    try { await save(value.trim()); close() }
    catch (reason) { report(reason, '保存未完成，请重试。') }
    finally { saving.current = false; setBusy(false) }
  }
  return <Modal open title={title} closeLabel="关闭" description={description} onClose={() => { if (!saving.current) close() }} footer={<><Button variant="outline" disabled={busy} onClick={close}>{error?.committed ? '关闭' : '取消'}</Button>{error?.committed ? readback && <RefreshListButton readback={readback} /> : <Button variant="outline" disabled={blocked} onClick={() => void confirm()}>{actionLabel}</Button>}</>}>
    <input className="cb-rename-input" data-modal-autofocus aria-label={field} value={value} maxLength={maxLength} disabled={busy || !!error?.committed} onFocus={event => event.target.select()} onChange={event => { setValue(event.target.value); clear() }} onCompositionStart={() => { composing.current = true }} onCompositionEnd={() => { composing.current = false }} onKeyDown={event => { if (event.key === 'Enter' && !composing.current) { event.preventDefault(); void confirm() } }} />
    {validation && <p className="cb-sidebar-error" role="alert">{validation}</p>}{error && <p className="cb-sidebar-error" role="alert">{error.message}</p>}
  </Modal>
}

export function ConfirmAction({ title, description, action, pending, confirm, close, children, readback }: { title: string; description: string; action: string; pending: string; confirm(): Promise<void>; close(): void; children?: ReactNode; readback?: SidebarReadback }) {
  const [busy, setBusy] = useState(false), saving = useRef(false)
  const { error, clear, report } = useActionError(readback, close)
  const perform = async () => {
    if (saving.current || error?.committed) return
    saving.current = true; setBusy(true); clear()
    try { await confirm(); close() }
    catch (reason) { report(reason, '操作未完成，请重试。') }
    finally { saving.current = false; setBusy(false) }
  }
  return <Modal open title={title} closeLabel="关闭" description={description} onClose={() => { if (!saving.current) close() }} footer={<><Button variant="outline" disabled={busy} onClick={close}>{error?.committed ? '关闭' : '取消'}</Button>{error?.committed ? readback && <RefreshListButton readback={readback} /> : <Button variant="outline" className="cb-danger-action" disabled={busy} onClick={() => void perform()}>{action}</Button>}</>}>
    {children}{busy && <p role="status">{pending}</p>}{error && <p className="cb-sidebar-error" role="alert">{error.message}</p>}
  </Modal>
}

export function WorkspaceActions({ workspace, allWorkspaces, run, disabled, readback, serverId, platform }: { workspace: SidebarWorkspace; allWorkspaces: readonly Pick<SidebarWorkspace, 'workspaceId' | 'title'>[]; run: SidebarOperation; disabled?: boolean; readback?: SidebarReadback; serverId?: string; platform?: string }) {
  const [dialog, setDialog] = useState<'rename' | 'remove' | 'workflow' | null>(null)
  return <><MoreMenu label={`${workspace.title}的工作区操作`} disabled={disabled}>{close => <>
    <MenuItemButton icon={<IconEditOutlineRegular size={16} />} onSelect={() => { close(); setDialog('rename') }}>重命名</MenuItemButton>
    {workspace.pluginId && <MenuItemButton icon={<IconSlidersTwoOutlineRegular size={16} />} onSelect={() => { close(); setDialog('workflow') }}>切换工作流</MenuItemButton>}
    <MenuItemButton danger icon={<IconTrashOutlineRegular size={16} />} onSelect={() => { close(); setDialog('remove') }}>删除工作区</MenuItemButton>
  </>}</MoreMenu>
    {dialog === 'workflow' && <SwitchWorkflow workspace={workspace} serverId={serverId} platform={platform} close={() => setDialog(null)} readback={readback} />}
    {workspace && dialog === 'rename' && <RenameDialog title="重命名工作区" field="工作区名称" initial={workspace.title} readback={readback} validate={title => title && allWorkspaces.some(item => item.workspaceId !== workspace.workspaceId && item.title === title) ? `已存在名为“${title}”的工作区。` : undefined} close={() => setDialog(null)} save={title => run({ action: 'rename-workspace', workspaceId: workspace.workspaceId, title })} />}
    {workspace && dialog === 'remove' && <ConfirmAction title="删除工作区" description={`将把“${workspace.title}”从工作区列表中移除。文件夹与会话记录会保留，其会话不再显示在 CANNBot 列表中。`} action="删除工作区" pending="正在移除工作区…" readback={readback} close={() => setDialog(null)} confirm={() => run({ action: 'remove-workspace', workspaceId: workspace.workspaceId })} />}
  </>
}

function SwitchWorkflow({ workspace, serverId, platform, close, readback }: { workspace: SidebarWorkspace; serverId?: string; platform?: string; close(): void; readback?: SidebarReadback }) {
  const [pluginId, setPluginId] = useState(''), [running, setRunning] = useState(false), [error, setError] = useState(''), [committed, setCommitted] = useState(false)
  const refresh = async () => { try { await readback?.refresh(); close() } catch { setError('工作流已切换，列表刷新失败。请刷新列表，无需再次切换。') } }
  return <><Modal open closeLabel="关闭" title="切换工作流" description="同一工作区只能激活一个工作流。切换成功后，之前的会话永久冻结为只读；即使切回原工作流，也需新建会话。项目代码保留。" onClose={() => { if (!running) close() }} footer={<><Button variant="outline" disabled={running} onClick={close}>取消</Button><Button variant="outline" disabled={running || (!committed && (!pluginId || pluginId === workspace.pluginId))} onClick={() => committed ? void refresh() : setRunning(true)}>{committed ? '刷新列表' : '切换并冻结旧会话'}</Button></>}>
    <label className="cb-create-field">工作流<select aria-label="工作流" value={pluginId} disabled={running || committed} onChange={event => setPluginId(event.target.value)}><option value="" disabled>选择一个工作流</option><option value="general">空白工作区：不安装工作流</option>{WORKFLOWS.map(flow => <option key={flow.id} value={flow.id} disabled={!serverId && platform !== 'linux'}>{flow.id}：{zh[flow.description]}</option>)}</select></label>
    {!serverId && platform !== 'linux' && <p>工作流需要 Linux 环境，Windows 本机只支持空白工作区。</p>}
    {error && <p role="alert">{error}</p>}
  </Modal>{running && <InitializationDialog serverId={serverId} operation={{ action: 'switch-workflow', workspaceId: workspace.workspaceId, pluginId }} close={() => setRunning(false)} complete={() => { setRunning(false); setCommitted(true); void refresh() }} />}</>
}

interface Activity { kind: string; items?: { id: string; label?: string }[] }
function activeRefusal(reason: unknown): Activity[] | undefined {
  if (!reason || typeof reason !== 'object') return
  const value = reason as { code?: string; activity?: unknown; details?: { activity?: unknown }; rpcError?: { code?: string; details?: { activity?: unknown } } }
  if ((value.code || value.rpcError?.code) !== 'workspace/session-active') return
  const activity = value.activity || value.details?.activity || value.rpcError?.details?.activity
  return Array.isArray(activity) ? activity.filter((entry): entry is Activity => !!entry && typeof entry === 'object' && typeof entry.kind === 'string') : []
}
function activityLine(entry: Activity) {
  if (entry.kind === 'turn') return '进行中的回合'
  const labels: Record<string, string> = { subagent: '运行中的子智能体', job: '后台任务', schedule: '定时提醒' }
  const items = Array.isArray(entry.items) ? entry.items : []
  return `${items.length} 项${labels[entry.kind] || `其他工作（${entry.kind}）`}${items.length ? `：${items.map(item => item.label || item.id).join('、')}` : ''}`
}

export function SessionActions({ session, run, disabled, canFork = true, readback, renameRequest = 0, copyFeedback }: { session: SidebarSession; run: SidebarOperation; disabled?: boolean; canFork?: boolean; readback?: SidebarReadback; renameRequest?: number; copyFeedback?(ok: boolean): void }) {
  const [renaming, setRenaming] = useState(false), [activity, setActivity] = useState<Activity[] | null>(null)
  const [busy, setBusy] = useState(false), pending = useRef(false)
  const { error, clear, report } = useActionError(readback)
  useEffect(() => { if (renameRequest > 0 && !session.blank) setRenaming(true) }, [renameRequest, session.blank])
  const act = async (operation: () => Promise<void>, archive = false) => {
    if (pending.current || error?.committed) return
    pending.current = true; setBusy(true); clear()
    try { await operation() }
    catch (reason) {
      const active = archive ? activeRefusal(reason) : undefined
      if (active) setActivity(active)
      else report(reason, '操作未完成，请重试。')
    } finally { pending.current = false; setBusy(false) }
  }
  const blocked = disabled || busy || !!error?.committed
  const archive = () => act(() => run({ action: session.archived ? 'unarchive-session' : 'archive-session', sessionId: session.id }), !session.archived)
  const pin = () => act(() => run({ action: session.pinned ? 'unpin-session' : 'pin-session', sessionId: session.id }))
  const archiveLabel = session.archived ? '取消归档' : '归档会话', pinLabel = session.pinned ? '取消置顶' : '置顶会话'
  const archiveIcon = session.archived ? <IconUnarchiveOutlineRegular size={14} /> : <IconArchiveOutlineRegular size={14} />
  const pinIcon = session.pinned ? <IconPinFillRegular size={14} /> : <IconPinOutlineRegular size={14} />
  if (session.blank) return null
  return <><span className="cb-row-actions" data-session-actions onClick={event => event.stopPropagation()}>
    <MoreMenu label={session.title + '的会话操作'} disabled={blocked}>{close => <>
      {!session.archived && <MenuItemButton icon={session.pinned ? <IconPinFillRegular size={16} /> : <IconPinOutlineRegular size={16} />} onSelect={() => { close(); void pin() }}>{pinLabel}</MenuItemButton>}
      <MenuItemButton icon={<IconEditOutlineRegular size={16} />} onSelect={() => { close(); setRenaming(true) }}>重命名</MenuItemButton>
      {canFork && !session.frozen && !session.archived && <MenuItemButton icon={<IconBranchOutlineRegular size={16} />} onSelect={() => { close(); void act(() => run({ action: 'fork-session', sessionId: session.id, allowMigration: false })) }}>分叉会话</MenuItemButton>}
      <MenuItemButton icon={archiveIcon} onSelect={() => { close(); void archive() }}>{archiveLabel}</MenuItemButton>
      <MenuItemButton icon={<IconCopyOutlineRegular size={16} />} onSelect={() => { close(); void act(async () => { try { await navigator.clipboard.writeText(session.id); copyFeedback?.(true) } catch (reason) { copyFeedback?.(false); if (!copyFeedback) throw reason } }) }}>复制 Session ID</MenuItemButton>
    </>}</MoreMenu>
    <Tooltip label={archiveLabel} side="bottom" align="end" delayMs={500} portal><button type="button" className="cb-project-action" aria-label={archiveLabel} disabled={blocked} data-session-action="archive" onClick={() => void archive()}>{archiveIcon}</button></Tooltip>
    {!session.archived && <Tooltip label={pinLabel} side="bottom" align="end" delayMs={500} portal><button type="button" className="cb-project-action" aria-label={pinLabel} disabled={blocked} data-session-action="pin" onClick={() => void pin()}>{pinIcon}</button></Tooltip>}
  </span>
    {error && <p className="cb-sidebar-error" role="alert">{error.message}{error.committed && readback && <> <RefreshListButton readback={readback} /></>}</p>}
    {renaming && <RenameDialog title="重命名会话" field="会话名称" initial={session.title} allowUnchanged readback={readback} save={title => run({ action: 'rename-session', sessionId: session.id, title })} close={() => setRenaming(false)} />}
    {activity && <ConfirmAction title="停止并归档此会话？" description={'“' + session.title + '”仍有正在进行的工作。归档会先停止这些工作；之后可在侧栏筛选“全部对话（显示已归档）”中恢复会话，被停止的工作不会自动继续。'} action="停止并归档" pending="正在停止并归档…" readback={readback} close={() => setActivity(null)} confirm={() => run({ action: 'archive-session', sessionId: session.id, stopActivity: true })}>
      <ul className="cb-archive-activity" aria-label="将被停止的工作">{activity.map((entry, index) => <li key={entry.kind + '-' + index}>{activityLine(entry)}</li>)}</ul>
    </ConfirmAction>}
  </>
}
