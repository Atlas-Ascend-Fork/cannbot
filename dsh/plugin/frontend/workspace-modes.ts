// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import type { Context } from '@deepseek-ai/cordis'
import type { ISessions } from '@deepseek-ai/dsh-api-session-controller/client'
import type { SessionId } from '@deepseek-ai/dsh-session/types'
import { CANNBOT_WORKSPACES_PATH, type CANNBotWorkspace, type CANNBotSession, type CANNBotWorkspaceOperation, type CANNBotOperationResult } from '../contracts/workspace-mode-types.ts'
import { announceEmbedded } from './embedded-navigation.ts'
import { createWorkbenchState, type WorkbenchState } from './workbench-state.ts'

export type ProductMode = 'deepseek' | 'cannbot'
export const CANNBOT_HOME = 'cannbot-dsh-workbench'
export interface ModeSnapshot {
  platform?: string
  mode: ProductMode; workspaces: CANNBotWorkspace[]; sessions: CANNBotSession[]
  ready: boolean; error: string; navigationError: string; creating: boolean; selectedWorkspaceId: string
  serverId: string; list: 'projects' | 'recent'; activeSessionId: string
  restoringSession?: boolean; creationServerId?: string; permissionWorkspaceId?: string
}
type Page = { panel: string | null; session?: string }
/** The Host owns membership. This controller only owns navigation and unsubmitted drafts. */
export function createWorkspaceModes(ctx: Context, edition: 'client' | 'server' = 'client') {
  const sessions = ctx.sessions as unknown as ISessions
  const params = new URLSearchParams(typeof location === 'undefined' ? '' : location.hash.replace(/^#/, ''))
  const embedded = params.get('cannEmbed') === '1'
  const createRequested = embedded && params.get('cannCreateWorkspace') === '1'
  if (createRequested) {
    // An explicit desktop action is consumed once; a reload must not reopen
    // a creation dialog the user already completed or dismissed.
    const address = new URL(location.href), fragment = new URLSearchParams(address.hash.slice(1))
    fragment.delete('cannCreateWorkspace'); address.hash = fragment.toString()
    history.replaceState(history.state, '', address)
  }
  const allowModeSwitch = edition === 'client' && !embedded
  const key = edition === 'client' ? 'cannbot.ui.modes.v1' : 'cannbot.ui.server.v1'
  let preference: { mode?: ProductMode; workspace?: string } = {}
  if (!embedded) {
    try {
      const saved: unknown = JSON.parse(localStorage.getItem(key) || '{}')
      if (saved && typeof saved === 'object') {
        const value = saved as { mode?: unknown; workspace?: unknown }
        preference = { ...(value.mode === 'cannbot' || value.mode === 'deepseek' ? { mode: value.mode } : {}), ...(typeof value.workspace === 'string' ? { workspace: value.workspace } : {}) }
      }
    } catch { /* Preferences cannot prevent the client from starting. */ }
  }
  let state: ModeSnapshot = { mode: allowModeSwitch && preference.mode === 'deepseek' ? 'deepseek' : 'cannbot', workspaces: [], sessions: [], ready: false, error: '', navigationError: '', creating: false, selectedWorkspaceId: preference.workspace || '', serverId: '', list: 'projects', activeSessionId: '', restoringSession: embedded && !createRequested && !!(params.get('cannSession') || params.get('cannWorkspace')) }
  const listeners = new Set<() => void>(), drafts = new Map<string, Partial<WorkbenchState>>()
  const workbench = createWorkbenchState()
  workbench.set({ workflow: '' })
  const pages: Record<ProductMode, Page> = { deepseek: { panel: null }, cannbot: { panel: CANNBOT_HOME } }
  const lifetime = new AbortController()
  let timer: ReturnType<typeof setTimeout> | undefined, pulling = false, started = false, switching = false, membershipRevision = 0
  let activePull: Promise<void> | undefined
  let restoringEmbed = embedded, targetSyncDepth = 0
  const publish = (patch: Partial<ModeSnapshot>) => { if (lifetime.signal.aborted) return; state = { ...state, ...patch }; for (const listener of listeners) listener() }
  const persist = () => { if (!embedded) try { localStorage.setItem(key, JSON.stringify({ mode: state.mode, workspace: state.selectedWorkspaceId })) } catch { /* preferences are optional */ } }
  const syncEmbeddedTarget = (workspaceId?: string, sessionId?: string) => {
    if (!embedded || restoringEmbed || targetSyncDepth > 0 || !state.ready || lifetime.signal.aborted) return
    const sessionWorkspace = sessionId && (state.workspaces.find(item => item.sessionIds.includes(sessionId))
      || state.workspaces.find(item => item.workspaceId === state.sessions.find(row => row.sessionId === sessionId)?.workspaceId))
    // A removed workspace's receipt still owns its ungrouped CANN history.
    const orphan = sessionId && state.sessions.find(row => row.sessionId === sessionId && row.ungrouped)
    // Only Host-verified membership may become a deep link for the outer desktop shell.
    if (sessionId && !sessionWorkspace && !orphan) return
    const workspace = sessionWorkspace || state.workspaces.find(item => item.workspaceId === workspaceId)
    const ownerId = workspace?.workspaceId || (orphan ? orphan.workspaceId : '')
    const address = new URL(location.href), fragment = new URLSearchParams(address.hash.slice(1))
    fragment.set('cannEmbed', '1'); fragment.set('cannMode', 'cannbot')
    if (ownerId) fragment.set('cannWorkspace', ownerId); else fragment.delete('cannWorkspace')
    if (sessionId) fragment.set('cannSession', sessionId); else fragment.delete('cannSession')
    address.hash = fragment.toString()
    if (address.href !== location.href) history.replaceState(history.state, '', address)
    announceEmbedded(params, 'location', { workspaceId: ownerId || undefined, sessionId })
  }
  const endpoint = () => new URL(CANNBOT_WORKSPACES_PATH, document.baseURI)
  const request = async (body?: object) => {
    const response = await fetch(endpoint(), { method: body ? 'POST' : 'GET', credentials: 'same-origin', cache: 'no-store', signal: lifetime.signal, ...(body && { headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) }) })
    const value = await response.json()
    if (!response.ok) {
      const messages: Record<string, string> = {
        'directory-not-empty': '该目录不是空目录，请另选一个空目录。',
        'plugin-conflict': '此目录已绑定其他工作流，请另选一个空目录。',
        'invalid-directory': '请选择已有目录的绝对路径。',
        'invalid-plugin': '请选择一个已安装的工作流。',
        'directory-replaced': '该路径对应的目录已被替换，请另选一个空目录。',
        'host-not-ready': '工作区服务正在准备，请稍后重试。',
        'workspace-operation-failed': '工作区初始化未完成。请在插件页查看准备日志，再用同一目录和工作流重试。',
      }
      throw Object.assign(new Error(messages[value?.error] || (typeof value?.message === 'string' ? value.message : '工作区操作失败，请重试。')), {
        code: typeof value?.error === 'string' ? value.error : '', status: response.status,
        ...(Array.isArray(value?.activity) && { activity: value.activity }),
      })
    }
    return value
  }
  const refresh = async () => {
    if (pulling || lifetime.signal.aborted) return
    pulling = true
    const revision = membershipRevision
    activePull = (async () => {
      try {
        const value = await request()
        if (revision !== membershipRevision) return
        if (!Array.isArray(value.workspaces) || !Array.isArray(value.sessions)) throw new Error('工作区服务返回了无效数据。')
        if (value.sessions.some((row: CANNBotSession) => row.archived && row.sessionId === pages.cannbot.session)) pages.cannbot = { panel: CANNBOT_HOME }
        publish({ workspaces: value.workspaces, sessions: value.sessions, platform: value.platform, ready: true, error: '' })
      } catch (error) { if (!lifetime.signal.aborted && revision === membershipRevision) publish({ error: error instanceof Error ? error.message : '无法读取工作区，请重试。' }) }
      finally { pulling = false }
    })()
    await activePull
  }
  const refreshAfterOperation = async () => {
    ++membershipRevision
    // Existing record/create calls still publish membership before waiting.
    // Row operations additionally wait out an older poll, then read committed state.
    await activePull
    await refresh()
    if (!lifetime.signal.aborted && state.error) throw Object.assign(new Error('操作已完成，但列表刷新失败。请刷新列表查看结果。'), { committed: true })
  }
  const currentSession = () => {
    const snapshot = sessions.list.getSnapshot() as unknown as { current?: string; byId?: Record<string, { retainedBy?: { mainView?: number } }> }
    return snapshot.current || Object.entries(snapshot.byId || {}).find(([, item]) => (item.retainedBy?.mainView || 0) > 0)?.[0] || ''
  }
  const selectPanel = (panel: string | null) => ctx.layout.selectPanel(panel as Parameters<typeof ctx.layout.selectPanel>[0])
  const capture = () => {
    if (switching) return
    const panel = ctx.layout.panelInfo.getSnapshot().activePanelId || null
    const session = currentSession()
    const belongs = state.workspaces.some(row => row.sessionIds.includes(session)) || state.sessions.some(row => row.sessionId === session)
    if (panel || (session && (state.mode === 'deepseek' || belongs))) pages[state.mode] = { panel, ...(session && { session }) }
    publish({ activeSessionId: session })
    if (panel === CANNBOT_HOME) syncEmbeddedTarget(state.selectedWorkspaceId)
    else if (!panel && belongs) syncEmbeddedTarget(undefined, session)
  }
  const selectWorkspace = (id: string) => {
    const previous = workbench.getSnapshot()
    drafts.set(previous.workspaceId, { prompt: previous.prompt, files: previous.files, detail: previous.detail })
    const workspace = state.workspaces.find(item => item.workspaceId === id)
    workbench.set({ prompt: '', files: [], ...drafts.get(id), workspaceId: id, workflow: workspace?.pluginId || '', error: '' })
    publish({ selectedWorkspaceId: id, serverId: '', navigationError: '' }); persist(); syncEmbeddedTarget(id)
  }
  const openSession = (id: string) => {
    const owned = state.workspaces.some(item => item.sessionIds.includes(id)) || state.sessions.some(item => item.sessionId === id)
    if (state.mode === 'cannbot' && (!state.ready || !owned)) { publish({ error: state.ready ? '请先切换到该会话所属模式。' : '工作区正在加载，请稍后重试。' }); return }
    // Cancel an in-flight native startup restore before retaining the explicit target.
    ctx.layout.beginNavigation()
    targetSyncDepth++
    try {
      const owned = state.sessions.find(item => item.sessionId === id)
      if (state.mode === 'cannbot' && owned) selectWorkspace(owned.workspaceId)
      ctx.uiWorkspace.openSession(id as Parameters<typeof ctx.uiWorkspace.openSession>[0])
      pages[state.mode] = { panel: null, session: id }; publish({ activeSessionId: id })
    } finally { targetSyncDepth-- }
    syncEmbeddedTarget(undefined, id)
  }
  const waitForSessionCatalog = (id: string, signal: AbortSignal) => new Promise<void>((resolve, reject) => {
    let unsubscribe = () => {}
    const finish = (error?: unknown) => { unsubscribe(); signal.removeEventListener('abort', abort); error ? reject(error) : resolve() }
    const abort = () => finish(signal.reason ?? new Error('cancelled'))
    const check = () => {
      const snapshot = sessions.list.getSnapshot()
      if (snapshot.phase !== 'ready') return
      finish(snapshot.byId[id as SessionId] ? undefined : new Error('session unavailable'))
    }
    unsubscribe = sessions.list.subscribe(check)
    signal.addEventListener('abort', abort, { once: true })
    if (signal.aborted) abort(); else check()
  })
  const openEmbeddedSession = async (id: string): Promise<boolean> => {
    const changedPage = new AbortController(), timeout = AbortSignal.timeout(20000)
    const initialPanel = ctx.layout.panelInfo.getSnapshot().activePanelId
    const stopPage = ctx.layout.panelInfo.subscribe(() => {
      if (ctx.layout.panelInfo.getSnapshot().activePanelId !== initialPanel) changedPage.abort()
    })
    let navigation: AbortSignal | undefined
    let reference: ReturnType<ISessions['retain']> | undefined
    try {
      // The membership HTTP response can precede DSH's own Session baseline.
      // retain() rejects undiscovered IDs, so wait for the public catalog first.
      await waitForSessionCatalog(id, AbortSignal.any([lifetime.signal, changedPage.signal, timeout]))
      stopPage()
      navigation = ctx.layout.beginNavigation()
      const signal = AbortSignal.any([lifetime.signal, navigation, timeout])
      reference = sessions.retain(id as SessionId, { source: 'controllerOperation', signal })
      await reference.ready
      signal.throwIfAborted()
      openSession(id)
      return true
    } catch {
      if (!lifetime.signal.aborted && !changedPage.signal.aborted && (!navigation?.aborted || timeout.aborted)) {
        const error = timeout.aborted ? '远端会话加载超时，请返回本地后重新打开。' : '无法读取远端会话，请返回本地后重新打开。'
        publish({ navigationError: error }); selectPanel(CANNBOT_HOME)
      }
      return false
    } finally { stopPage(); reference?.release() }
  }
  const setMode = (mode: ProductMode) => {
    if (!allowModeSwitch || mode === state.mode) return
    capture(); switching = true
    publish({ mode, creating: false }); persist()
    const page = pages[mode]
    const rememberedOwned = page.session && !state.sessions.some(row => row.sessionId === page.session && row.archived) && (state.workspaces.some(row => row.sessionIds.includes(page.session!)) || state.sessions.some(row => row.sessionId === page.session))
    try {
      if (page.panel) selectPanel(page.panel)
      else if (page.session && (mode === 'deepseek' || (state.ready && rememberedOwned))) ctx.uiWorkspace.openSession(page.session as Parameters<typeof ctx.uiWorkspace.openSession>[0])
      else if (mode === 'cannbot') selectPanel(CANNBOT_HOME)
      else { selectPanel(null); ctx.uiWorkspace.startSession() }
    } finally { switching = false; capture() }
  }
  const api = {
    embedded, workbench, getSnapshot: () => state,
    subscribe(listener: () => void) { listeners.add(listener); return () => { listeners.delete(listener) } },
    refresh, refreshAfterOperation, selectWorkspace, setMode, openSession,
    async operate(operation: CANNBotWorkspaceOperation): Promise<CANNBotOperationResult> {
      const result = await request(operation) as CANNBotOperationResult
      await refreshAfterOperation()
      return result
    },
    reportError(error: string) { publish({ error }) },
    setList(list: ModeSnapshot['list']) { publish({ list }) },
    selectServer(serverId: string) { publish({ serverId, creating: false }) },
    setCreating(creating: boolean, creationServerId = '') {
      if (creating && embedded) {
        const address = new URL(location.href), fragment = new URLSearchParams(address.hash.slice(1))
        announceEmbedded(params, 'create')
        fragment.set('cannNewFolder', crypto.randomUUID()); address.hash = fragment.toString()
        history.replaceState(history.state, '', address)
        return
      }
      publish({ creating, creationServerId })
    },
    newSession(workspaceId?: string) {
      if (state.mode === 'cannbot') { ctx.layout.beginNavigation(); if (workspaceId) selectWorkspace(workspaceId); pages.cannbot = { panel: CANNBOT_HOME }; selectPanel(CANNBOT_HOME); syncEmbeddedTarget(state.selectedWorkspaceId) }
      else ctx.uiWorkspace.startSession(workspaceId as Parameters<typeof ctx.uiWorkspace.startSession>[0])
    },
    enterCreatedWorkspace(workspace: CANNBotWorkspace) {
      ++membershipRevision
      publish({ workspaces: [...state.workspaces.filter(item => item.workspaceId !== workspace.workspaceId), workspace], ready: true, creating: false,
        permissionWorkspaceId: workspace.pluginId === 'general' ? undefined : workspace.workspaceId })
      api.newSession(workspace.workspaceId)
      void refreshAfterOperation().catch(error => publish({ error: error.message }))
    },
    finishPermissionRequest() {
      publish({ permissionWorkspaceId: undefined })
      if (embedded) {
        const address = new URL(location.href), fragment = new URLSearchParams(address.hash.slice(1))
        fragment.delete('cannRecommendPermissions'); address.hash = fragment.toString(); history.replaceState(history.state, '', address)
      }
    },
    returnLocal() { publish({ mode: 'cannbot', serverId: '' }); selectPanel(CANNBOT_HOME); persist() },
    async create(path: string, pluginId: string) {
      const result = await request({ action: 'create', path, pluginId })
      ++membershipRevision
      publish({ workspaces: [...state.workspaces.filter(item => item.workspaceId !== result.workspace.workspaceId), result.workspace] })
      await refresh(); selectWorkspace(result.workspace.workspaceId); publish({ creating: false }); selectPanel(CANNBOT_HOME)
      return result.workspace as CANNBotWorkspace
    },
    async recordSession(workspaceId: string, sessionId: string, options: { reveal?: boolean } = {}) {
      const result = await request({ action: 'session', workspaceId, sessionId })
      // A periodic GET started before this committed write must not erase the
      // new membership before native navigation checks the session's owner.
      ++membershipRevision
      publish({ sessions: [...state.sessions.filter(item => item.sessionId !== sessionId), result.session], workspaces: state.workspaces.map(item => item.workspaceId === workspaceId ? { ...item, sessionIds: [...new Set([...item.sessionIds, sessionId])] } : item) })
      if (options.reveal !== false) syncEmbeddedTarget(workspaceId, sessionId)
      await refresh()
      if (options.reveal !== false) { pages.cannbot = { panel: null, session: sessionId }; publish({ activeSessionId: sessionId }) }
    },
    start() {
      if (started) return () => {}
      started = true
      const tick = async () => { await refresh(); if (!lifetime.signal.aborted) timer = setTimeout(() => { void tick() }, 4000) }
      const unlisten = sessions.list.subscribe(capture), unpanel = ctx.layout.panelInfo.subscribe(capture)
      capture()
      void (async () => {
        await tick()
        if (lifetime.signal.aborted) return
        if (embedded) {
          announceEmbedded(params, 'ready')
          const workspace = params.get('cannWorkspace'), session = params.get('cannSession')
          const verifiedSession = !createRequested && session && state.sessions.some(item => item.sessionId === session) ? session : undefined
          try {
            if (session && !verifiedSession && !createRequested) { publish({ navigationError: '无法读取远端会话，请返回本地后重新打开。' }); selectPanel(CANNBOT_HOME); return }
            if (createRequested) { selectPanel(CANNBOT_HOME); publish({ creating: true }) }
            else if (verifiedSession) {
              if (workspace && state.workspaces.some(item => item.workspaceId === workspace)) selectWorkspace(workspace)
              if (!await openEmbeddedSession(verifiedSession)) return
            }
            else {
              // The creation receipt can arrive before this new web client's first
              // membership snapshot. Resolve the explicit target before navigation.
              if (workspace && !state.workspaces.some(item => item.workspaceId === workspace)) await refreshAfterOperation()
              if (workspace && !state.workspaces.some(item => item.workspaceId === workspace)) { publish({ navigationError: '新工作区正在加载，请重新打开该工作区。' }); selectPanel(CANNBOT_HOME); return }
              if (workspace && params.get('cannRecommendPermissions') === '1' && state.workspaces.find(item => item.workspaceId === workspace)?.pluginId !== 'general') publish({ permissionWorkspaceId: workspace })
              api.newSession(workspace || undefined)
            }
          } finally { restoringEmbed = false; publish({ restoringSession: false }) }
          // Publish one settled deep link, never the temporary workspace-only selection.
          syncEmbeddedTarget(state.selectedWorkspaceId, verifiedSession)
        } else if (state.mode === 'cannbot') { if (state.selectedWorkspaceId) selectWorkspace(state.selectedWorkspaceId); selectPanel(CANNBOT_HOME) }
      })()
      return () => { unlisten(); unpanel(); api.dispose() }
    },
    dispose() { if (lifetime.signal.aborted) return; lifetime.abort(); clearTimeout(timer); workbench.dispose(); listeners.clear() },
  }
  return api
}
export type WorkspaceModes = ReturnType<typeof createWorkspaceModes>
