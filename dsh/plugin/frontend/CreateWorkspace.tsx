// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { useEffect, useRef, useState, useSyncExternalStore } from 'react'
import type { RemoteClient } from './remote/types.ts'
import { remoteWorkspaceEndpoint } from './remote/endpoint.ts'
import { WorkspaceForm, type WorkspaceFormProps } from './WorkspaceForm.tsx'

export function CreateWorkspace(props: WorkspaceFormProps & { remote: RemoteClient }) {
  const { remote, modes, close } = props
  const servers = useSyncExternalStore(remote.subscribe, remote.getSnapshot)
  const [serverId, setServerId] = useState<string | null>(modes.getSnapshot().creationServerId || '')
  const [connection, setConnection] = useState<{ id: string; autoStart: boolean } | null>(null)
  const alive = useRef(true)
  useEffect(() => { alive.current = true; return () => { alive.current = false } }, [])
  const selectServer = (id: string, autoStart = false) => {
    setServerId(id)
    const server = remote.getSnapshot().servers.find(item => item.id === id)
    if (server && !server.connected) setConnection({ id, autoStart })
  }
  const connected = serverId !== null && (!serverId || servers.servers.some(server => server.id === serverId && server.connected))
  return <><WorkspaceForm {...props} location={{
    serverId, connected, connecting: !!connection, clearSelection: () => setServerId(null),
    endpoint: serverId ? remoteWorkspaceEndpoint(serverId) : undefined,
    onCreated: serverId ? async (workspace, recommendPermissions) => {
      close(); modes.selectServer(serverId)
      await remote.open({ serverId, workspaceId: workspace.workspaceId, recommendPermissions })
    } : undefined,
    field: ({ saving, workflowNotice, localWorkflowAllowed }) => <label className="cb-create-field">服务器<select aria-label="服务器" value={serverId ?? '__select_server__'} disabled={saving || modes.embedded} onChange={event => {
      if (event.target.value === '__add_server__') {
        remote.showConnections(id => { if (alive.current) selectServer(id, true) })
      } else if (event.target.value !== '' || !workflowNotice || localWorkflowAllowed) { selectServer(event.target.value) }
    }}>
      <option value="__select_server__" disabled>选择一个服务器</option>
      <option value="" disabled={workflowNotice && !localWorkflowAllowed}>{modes.embedded ? '此服务器' : workflowNotice && !localWorkflowAllowed ? '本机（本工作流需要连接NPU的Linux环境）' : '本机'}</option>
      {!modes.embedded && servers.servers.map(server => <option value={server.id} key={server.id} aria-label={`${server.label || server.alias}，${server.connected ? '已连接' : '未连接'}`}>{server.connected ? '🟢' : '🔴'} {server.label || server.alias}</option>)}
      {!modes.embedded && <option value="__add_server__">添加服务器</option>}
    </select></label>
  }} />{connection && <WorkspaceConnectionDialog remote={remote} id={connection.id} autoStart={connection.autoStart} complete={() => setConnection(null)} cancel={() => { setConnection(null); setServerId(null) }} />}</>
}
function WorkspaceConnectionDialog({ remote, id, autoStart, complete, cancel }: {
  remote: RemoteClient; id: string; autoStart: boolean; complete(): void; cancel(): void
}) {
  const state = useSyncExternalStore(remote.subscribe, remote.getSnapshot)
  const dialog = useRef<HTMLDialogElement>(null), log = useRef<HTMLPreElement>(null), alive = useRef(true), running = useRef(false)
  const cancelling = useRef(false)
  const [stopping, setStopping] = useState(false)
  const [phase, setPhase] = useState<'confirm' | 'connecting' | 'error'>(autoStart ? 'connecting' : 'confirm')
  const [error, setError] = useState('')
  const server = state.servers.find(item => item.id === id)
  const connect = async () => {
    if (running.current) return
    if (remote.getSnapshot().servers.find(item => item.id === id)?.connected) { complete(); return }
    running.current = true; setPhase('connecting'); setError('')
    try { await remote.connect(id); if (alive.current && !cancelling.current) complete() }
    catch (reason) { if (alive.current && !cancelling.current) { setError(reason instanceof Error ? reason.message : '连接失败，请重试。'); setPhase('error') } }
    finally { running.current = false }
  }
  const stop = async () => {
    if (cancelling.current) return
    if (phase !== 'connecting') { cancel(); return }
    cancelling.current = true; setStopping(true); setError('')
    try { await remote.cancelConnect(id); if (alive.current) cancel() }
    catch { if (alive.current) { cancelling.current = false; setStopping(false); setError('取消连接未完成，请重试。') } }
  }
  useEffect(() => {
    alive.current = true; dialog.current?.showModal()
    if (autoStart) void connect()
    return () => { alive.current = false }
  }, [])
  useEffect(() => { if (log.current) log.current.scrollTop = log.current.scrollHeight }, [state.progress])
  return <dialog ref={dialog} className={`cwb-directory cb-workspace-connection ${phase !== 'confirm' ? 'cb-connection-progress' : ''}`} aria-label={phase === 'confirm' ? '连接服务器' : '服务器连接与安装'} onCancel={event => { event.preventDefault(); event.stopPropagation(); void stop() }}>
    <header><h2>{phase === 'confirm' ? '连接服务器' : '服务器连接与安装'}</h2>{phase === 'connecting' && <button type="button" className="cwb-text-button" disabled={stopping} onClick={() => void stop()}>{stopping ? '正在取消…' : '取消'}</button>}</header>
    <p>{server?.label || server?.alias || id}</p>
    {phase === 'confirm' ? <p>服务器还未连接，是否立即连接？</p> : <pre ref={log} role="log" aria-label="连接与安装日志" aria-live="polite">{state.progress.join('\n') || '正在连接服务器…'}</pre>}
    {error && <p role="alert" className="cwb-error">{error}</p>}
    {phase === 'connecting' ? <p role="status">正在连接并准备环境，完成后自动关闭…</p> : <footer>
      <button type="button" className="cwb-text-button" onClick={cancel}>{phase === 'confirm' ? '取消' : '关闭'}</button>
      <button type="button" className="cwb-primary" disabled={state.busy} onClick={() => void connect()}>{phase === 'confirm' ? '确认' : '重试'}</button>
    </footer>}
  </dialog>
}
