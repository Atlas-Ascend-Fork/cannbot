// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { AsyncLocalStorage } from 'node:async_hooks'
import { createHash, randomUUID } from 'node:crypto'
import { mkdir, readFile, readdir, realpath, rename, stat, unlink, writeFile } from 'node:fs/promises'
import { isAbsolute, join, relative, resolve, sep } from 'node:path'
import { withContentLock } from './content-lock.ts'
import { GENERAL_WORKSPACE } from './workspace-mode-types.ts'
import { initializationIO } from './initialization-jobs.ts'
import type { CANNBotOperationResult, CANNBotSession, CANNBotWorkspace, CANNBotWorkspaceOperation, CANNBotWorkspaceTree } from './workspace-mode-types.ts'

export class WorkspaceModeError extends Error {
  readonly code: string
  readonly status: number
  constructor(code: string, message: string, status = 409) {
    super(message); this.name = 'WorkspaceModeError'; this.code = code; this.status = status
  }
}
export interface HostWorkspace { workspaceId: string; path: string; title: string; sessionIds: readonly string[] }
export interface HostSession { sessionId: string; cwd: string; parentSession?: string; title?: string; updatedAt?: string; archived?: boolean; pinned?: boolean; pinOrder?: number; blank?: boolean; running?: boolean }
export interface HostSessionSummary { sessionId: string; updatedAt?: number; blank?: boolean; running?: boolean }
export interface WorkspaceModeDependencies {
  platform?: string
  available(pluginId: string): boolean
  prepare(path: string, pluginId: string): Promise<void>
  switchWorkflow?(path: string, previous: string, next: string, commit: () => Promise<void>, committed: (token?: string) => Promise<boolean>, commitToken: string): Promise<void>
  sessionActivity?(sessionId: string): Promise<readonly unknown[]>
  createWorkspace(path: string): Promise<{ workspace: HostWorkspace; created: boolean }>
  listWorkspaces(): Promise<readonly HostWorkspace[]>
  readSession(sessionId: string): Promise<HostSession>
  listSessionSummaries?(): Promise<readonly HostSessionSummary[] | undefined>
  renameWorkspace?(workspaceId: string, title: string): Promise<unknown>
  removeWorkspace?(workspaceId: string): Promise<unknown>
  renameSession?(sessionId: string, title: string): Promise<unknown>
  forkSession?(sessionId: string, allowMigration?: boolean): Promise<{ sessionId: string }>
  archiveSession?(sessionId: string, stopActivity: boolean): Promise<unknown>
  unarchiveSession?(sessionId: string): Promise<unknown>
  pinSession?(sessionId: string): Promise<unknown>
  unpinSession?(sessionId: string): Promise<unknown>
}
interface Binding {
  path: string; identity: string; pluginId: string; status: 'preparing' | 'ready'
  workspaceId?: string; sharedWithDeepSeek?: boolean
  generation?: number; switchingTo?: string; switchToken?: string
  awaitingHostRegistration?: boolean
}
interface SessionBinding { sessionId: string; workspaceId: string; pluginId: string; generation?: number }
interface State { schemaVersion: 1; workspaces: Binding[]; sessions: SessionBinding[] }
const emptyState = (): State => ({ schemaVersion: 1, workspaces: [], sessions: [] })
const pathKey = (path: string) => process.platform === 'win32' ? path.toLowerCase() : path
const validString = (value: unknown): value is string => typeof value === 'string' && value.length > 0 && value.length <= 32768 && !value.includes('\0')
const samePath = (left: string, right: string) => pathKey(left) === pathKey(right)

/** Explicit view membership and directory ownership, shared by every plugin entry point.
 * Locks and receipts live in Host state, never in the selected empty directory.
 * A failed preparation retains its reservation so only the same plugin may retry.
 */
export class WorkspaceModes {
  readonly root: string
  private readonly dependencies: WorkspaceModeDependencies
  private readonly held = new AsyncLocalStorage<{ key: string; pluginId: string }>()
  constructor(root: string, dependencies: WorkspaceModeDependencies) {
    this.root = resolve(root); this.dependencies = dependencies
  }
  private async read(): Promise<State> {
    let text: string
    try { text = await readFile(join(this.root, 'state.json'), 'utf8') }
    catch (error) { if ((error as NodeJS.ErrnoException).code === 'ENOENT') return emptyState(); throw error }
    try {
      const state = JSON.parse(text) as State
      if (state.schemaVersion !== 1 || !Array.isArray(state.workspaces) || !Array.isArray(state.sessions)) throw new Error()
      const paths = new Set<string>(), sessions = new Set<string>(), workspaces = new Set<string>()
      for (const item of state.workspaces) {
        if (item.generation !== undefined && (!Number.isSafeInteger(item.generation) || item.generation < 0)) throw new Error()
        if (item.switchingTo !== undefined && !validString(item.switchingTo)) throw new Error()
        if (!validString(item.path) || !isAbsolute(item.path) || !validString(item.identity) || !validString(item.pluginId)
          || !['preparing', 'ready'].includes(item.status) || paths.has(pathKey(item.path))) throw new Error()
        paths.add(pathKey(item.path))
        if (item.status === 'ready' && (!validString(item.workspaceId) || typeof item.sharedWithDeepSeek !== 'boolean')) throw new Error()
        if (item.workspaceId) { if (workspaces.has(item.workspaceId)) throw new Error(); workspaces.add(item.workspaceId) }
      }
      for (const item of state.sessions) {
        if (!validString(item.sessionId) || !validString(item.workspaceId) || !validString(item.pluginId) || sessions.has(item.sessionId)) throw new Error()
        const owner = state.workspaces.find(workspace => workspace.workspaceId === item.workspaceId)
        if (!owner || owner.status !== 'ready') throw new Error()
        if (item.generation !== undefined && (!Number.isSafeInteger(item.generation) || item.generation < 0)) throw new Error()
        sessions.add(item.sessionId)
      }
      return state
    } catch { throw new WorkspaceModeError('invalid-mode-state', 'CANNBot workspace state is invalid; restore its backup before continuing.', 503) }
  }
  private async change<T>(action: (state: State) => T): Promise<T> {
    return withContentLock(join(this.root, 'state.lock'), async () => {
      const state = await this.read(), result = action(state)
      await mkdir(this.root, { recursive: true })
      const temporary = join(this.root, `state-${randomUUID()}.tmp`)
      try {
        await writeFile(temporary, JSON.stringify(state), { encoding: 'utf8', mode: 0o600, flush: true })
        await rename(temporary, join(this.root, 'state.json'))
      } finally { await unlink(temporary).catch(error => { if (error.code !== 'ENOENT') throw error }) }
      return result
    })
  }
  private async directory(path: string) {
    if (!validString(path) || !isAbsolute(path)) throw new WorkspaceModeError('invalid-directory', 'Choose an existing absolute directory.', 400)
    let canonical: string, info: Awaited<ReturnType<typeof stat>>
    try { canonical = await realpath(path); info = await stat(canonical) }
    catch { throw new WorkspaceModeError('invalid-directory', 'The selected directory is unavailable.', 400) }
    if (!info.isDirectory()) throw new WorkspaceModeError('invalid-directory', 'The selected path is not a directory.', 400)
    return { path: canonical, key: pathKey(canonical), identity: `${info.dev}:${info.ino}` }
  }
  private check(binding: Binding | undefined, directory: { identity: string }, pluginId: string) {
    if (!binding) return
    if (binding.identity !== directory.identity) throw new WorkspaceModeError('directory-replaced', 'This path now identifies a different directory; choose a new empty directory.')
    if (binding.pluginId !== pluginId) throw new WorkspaceModeError('plugin-conflict', 'This directory is bound to another CANNBot workflow. Choose a different empty directory.')
  }
  private async locked<T>(path: string, pluginId: string, action: (directory: { path: string; key: string; identity: string }) => Promise<T>): Promise<T> {
    const directory = await this.directory(path), held = this.held.getStore()
    if (held?.key === directory.key) {
      if (held.pluginId !== pluginId) throw new WorkspaceModeError('plugin-conflict', 'A different workflow is already initializing this directory.')
      return action(directory)
    }
    const key = createHash('sha256').update(directory.key).digest('hex')
    return withContentLock(join(this.root, 'directories', key + '.lock'), async () => {
      const current = await this.directory(path)
      if (current.key !== directory.key || current.identity !== directory.identity) throw new WorkspaceModeError('directory-replaced', 'The selected directory changed while waiting; choose it again.')
      return this.held.run({ key: directory.key, pluginId }, () => action(current))
    })
  }
  /** Installed as ContentManager's preparation guard, including legacy routes and agent initialization. */
  withPreparation<T>(path: string, pluginId: string, prepare: () => Promise<T>): Promise<T> {
    return this.locked(path, pluginId, async directory => {
      const state = await this.read()
      const binding = state.workspaces.find(item => samePath(item.path, directory.path))
      if (binding?.switchingTo === pluginId && this.held.getStore()?.pluginId === pluginId) this.check({ ...binding, pluginId }, directory, pluginId)
      else { if (binding?.switchingTo) throw new WorkspaceModeError('workflow-switching', '工作流正在切换，请等待初始化完成。'); this.check(binding, directory, pluginId) }
      return prepare()
    })
  }
  async create(path: string, pluginId: string): Promise<CANNBotWorkspace> {
    if (!validString(pluginId) || (pluginId !== GENERAL_WORKSPACE && !this.dependencies.available(pluginId))) throw new WorkspaceModeError('invalid-plugin', 'Choose one installed CANNBot workflow.', 400)
    if (pluginId !== GENERAL_WORKSPACE && (this.dependencies.platform ?? process.platform) !== 'linux') throw new WorkspaceModeError('workflow-linux-only', '本工作流需要在 Linux 环境中初始化。', 400)
    const selected = await this.directory(path), diff = relative(selected.path, this.root)
    if (!diff || (!diff.startsWith('..' + sep) && diff !== '..' && !isAbsolute(diff))) throw new WorkspaceModeError('invalid-directory', 'Choose a project directory outside CANNBot state.', 400)
    return this.locked(path, pluginId, async directory => {
      let binding = (await this.read()).workspaces.find(item => samePath(item.path, directory.path))
      this.check(binding, directory, pluginId)
      if (!binding) {
        if ((await readdir(directory.path)).length) throw new WorkspaceModeError('directory-not-empty', 'CANNBot setup requires an empty directory. Choose or create another directory.')
        binding = { path: directory.path, identity: directory.identity, pluginId, status: 'preparing' }
        await this.change(state => { state.workspaces.push(binding!) })
      }
      // ContentManager's existing initialization transaction recovers an interrupted retry.
      if (pluginId !== GENERAL_WORKSPACE) await this.dependencies.prepare(directory.path, pluginId)
      initializationIO.getStore()?.signal.throwIfAborted()
      const result = await this.dependencies.createWorkspace(directory.path)
      if (!samePath((await this.directory(result.workspace.path)).path, directory.path)) throw new WorkspaceModeError('workspace-mismatch', 'Host registered a different workspace directory.', 500)
      const ready: Binding = { ...binding, awaitingHostRegistration: false, status: 'ready', workspaceId: result.workspace.workspaceId, sharedWithDeepSeek: binding.sharedWithDeepSeek ?? !result.created }
      await this.change(state => {
        const index = state.workspaces.findIndex(item => samePath(item.path, directory.path))
        if (index < 0) throw new WorkspaceModeError('invalid-mode-state', 'Workspace reservation disappeared.', 503)
        if (binding!.workspaceId && binding!.workspaceId !== ready.workspaceId) {
          // Native removal never removes the physical plugin binding. Retained sessions
          // follow the newly registered identity only when they had this explicit owner.
          for (const session of state.sessions) if (session.workspaceId === binding!.workspaceId) session.workspaceId = ready.workspaceId!
        }
        state.workspaces[index] = ready
      })
      return this.workspaceView(ready, result.workspace, (await this.read()).sessions)
    })
  }
  private workspaceView(binding: Binding, workspace: HostWorkspace, sessions: SessionBinding[]): CANNBotWorkspace {
    return { workspaceId: workspace.workspaceId, path: binding.path, title: workspace.title, pluginId: binding.pluginId,
      sharedWithDeepSeek: binding.sharedWithDeepSeek === true,
      sessionIds: sessions.filter(item => item.workspaceId === workspace.workspaceId).map(item => item.sessionId) }
  }
  async prepareBeforeLaunch(path: string, pluginId: string): Promise<void> {
    if (pluginId !== GENERAL_WORKSPACE && !this.dependencies.available(pluginId)) throw new WorkspaceModeError('invalid-plugin', '请选择已安装的工作流。', 400)
    await this.locked(path, pluginId, async directory => {
      const binding = (await this.read()).workspaces.find(item => samePath(item.path, directory.path))
      this.check(binding, directory, pluginId)
      if (binding?.status === 'ready') throw new WorkspaceModeError('workspace-exists', '已有工作区请在 CANNBot 中切换工作流。')
      if (!binding) {
        if ((await readdir(directory.path)).length) throw new WorkspaceModeError('directory-not-empty', '请选择一个空目录。')
        await this.change(state => { state.workspaces.push({ path: directory.path, identity: directory.identity, pluginId, status: 'preparing' }) })
      }
      if (pluginId !== GENERAL_WORKSPACE) await this.dependencies.prepare(directory.path, pluginId)
      await this.change(state => { state.workspaces.find(item => samePath(item.path, directory.path))!.awaitingHostRegistration = true })
    })
  }
  async registerPreparedWorkspaces(): Promise<void> {
    for (const binding of (await this.read()).workspaces) if (binding.status === 'preparing' && binding.awaitingHostRegistration) await this.create(binding.path, binding.pluginId)
  }
  async switchWorkflow(workspaceId: string, pluginId: string): Promise<void> {
    if (pluginId !== GENERAL_WORKSPACE && !this.dependencies.available(pluginId)) throw new WorkspaceModeError('invalid-plugin', '请选择已安装的工作流。', 400)
    if (pluginId !== GENERAL_WORKSPACE && (this.dependencies.platform ?? process.platform) !== 'linux') throw new WorkspaceModeError('workflow-linux-only', '本工作流需要在 Linux 环境中初始化。', 400)
    const original = (await this.read()).workspaces.find(item => item.workspaceId === workspaceId && item.status === 'ready')
    if (!original) throw new WorkspaceModeError('unknown-workspace', '工作区不存在。', 404)
    await this.locked(original.path, pluginId, async directory => {
      const binding = (await this.read()).workspaces.find(item => item.workspaceId === workspaceId)!
      this.check(binding, directory, binding.pluginId)
      if (binding.switchingTo && binding.switchingTo !== pluginId) throw new WorkspaceModeError('workflow-switching', '上次切换尚未完成，请先重试同一工作流以恢复配置。')
      if (binding.pluginId === pluginId && !binding.switchingTo) return
      if (!this.dependencies.switchWorkflow || !this.dependencies.sessionActivity) throw new WorkspaceModeError('operation-unavailable', '当前宿主不支持安全切换工作流。', 503)
      const workspace = (await this.dependencies.listWorkspaces()).find(item => item.workspaceId === workspaceId && samePath(resolve(item.path), binding.path))
      if (!workspace) throw new WorkspaceModeError('unknown-workspace', '工作区已被移除。', 404)
      // Publish the gate before examining activity: newly waking turns cannot enter.
      await this.change(state => { state.workspaces.find(item => item.workspaceId === workspaceId)!.switchingTo = pluginId })
      try {
        for (const id of workspace.sessionIds) {
          if ((await this.dependencies.sessionActivity(id)).length) throw new WorkspaceModeError('workflow-active', '工作区仍有运行中的会话、后台任务或定时任务。请先停止或等待完成，再切换工作流。')
        }
        initializationIO.getStore()?.signal.throwIfAborted()
        const commitToken = randomUUID()
        await this.dependencies.switchWorkflow(directory.path, binding.pluginId, pluginId, async () => {
          initializationIO.getStore()?.signal.throwIfAborted()
          await this.change(state => {
            const current = state.workspaces.find(item => item.workspaceId === workspaceId)!
            current.pluginId = pluginId; current.generation = (current.generation ?? 0) + 1; current.switchToken = commitToken; delete current.switchingTo
          })
        }, async token => {
          const current = (await this.read()).workspaces.find(item => item.workspaceId === workspaceId)
          return !!token && current?.switchToken === token
        }, commitToken)
      } catch (error) {
        // Failed filesystem recovery keeps the execution gate closed.
        if (!(error as { recoveryFailed?: boolean }).recoveryFailed) await this.change(state => { delete state.workspaces.find(item => item.workspaceId === workspaceId)!.switchingTo })
        throw error
      }
    })
  }
  async recordSession(workspaceId: string, sessionId: string): Promise<CANNBotSession> {
    if (!validString(workspaceId) || !validString(sessionId)) throw new WorkspaceModeError('invalid-session', 'Workspace and session are required.', 400)
    const state = await this.read(); let binding = state.workspaces.find(item => item.workspaceId === workspaceId && item.status === 'ready')
    if (!binding) throw new WorkspaceModeError('unknown-workspace', 'Create a CANNBot workspace before starting its session.', 404)
    return this.locked(binding.path, binding.pluginId, async directory => {
      binding = (await this.read()).workspaces.find(item => item.workspaceId === workspaceId && item.status === 'ready')!
      if (!binding || binding.switchingTo) throw new WorkspaceModeError('workflow-switching', '工作流正在切换，请等待初始化完成。')
      this.check(binding, directory, binding.pluginId)
      const workspace = (await this.dependencies.listWorkspaces()).find(item => item.workspaceId === workspaceId)
      if (!workspace || !samePath((await this.directory(workspace.path)).path, directory.path)) throw new WorkspaceModeError('unknown-workspace', 'This CANNBot workspace is no longer registered.', 404)
      if (!workspace.sessionIds.includes(sessionId)) throw new WorkspaceModeError('session-workspace-mismatch', 'Host has not registered this session in the selected workspace.')
      const session = await this.dependencies.readSession(sessionId)
      await this.workflowForSession(sessionId)
      if (session.sessionId !== sessionId || !samePath((await this.directory(session.cwd)).path, directory.path)) throw new WorkspaceModeError('session-workspace-mismatch', 'The session does not belong to this workspace.')
      const record: SessionBinding = { sessionId, workspaceId, pluginId: binding.pluginId, generation: binding.generation ?? 0 }
      await this.change(current => {
        const previous = current.sessions.find(item => item.sessionId === sessionId)
        if (previous && (previous.generation ?? 0) !== record.generation) throw new WorkspaceModeError('session-frozen', '此会话已冻结，请新建会话。')
        if (previous && (previous.workspaceId !== workspaceId || previous.pluginId !== record.pluginId)) throw new WorkspaceModeError('session-conflict', 'This session is already bound to another CANNBot workspace.')
        if (!previous) current.sessions.push(record)
      })
      return { ...record, title: session.title, updatedAt: session.updatedAt, archived: session.archived, pinned: session.pinned,
        ...(typeof session.blank === 'boolean' ? { blank: session.blank } : {}), ...(typeof session.running === 'boolean' ? { running: session.running } : {}),
        ...(session.pinned === true && Number.isSafeInteger(session.pinOrder) && session.pinOrder! >= 0 ? { pinOrder: session.pinOrder } : {}) }
    })
  }
  /** Mutations require persisted CANNBot membership, never just a shared cwd.
   * Native deletion leaves our directory/plugin receipts and session ownership intact.
   */
  async operate(request: CANNBotWorkspaceOperation): Promise<CANNBotOperationResult> {
    if (request.action === 'switch-workflow') { await this.switchWorkflow(request.workspaceId, request.pluginId); return { ok: true } }
    const state = await this.read()
    const unavailable = () => new WorkspaceModeError('operation-unavailable', '当前 DSH 不支持此操作，请更新后重试。', 503)
    if ('workspaceId' in request) {
      const binding = state.workspaces.find(item => item.status === 'ready' && item.workspaceId === request.workspaceId)
      if (!binding) throw new WorkspaceModeError('unknown-workspace', '该工作区不属于 CANNBot。', 404)
      const workspace = (await this.dependencies.listWorkspaces()).find(item => item.workspaceId === request.workspaceId)
      if (!workspace || !samePath(resolve(workspace.path), binding.path)) throw new WorkspaceModeError('unknown-workspace', '该工作区已被移除，请刷新列表。', 404)
      if (request.action === 'rename-workspace') {
        if (!this.dependencies.renameWorkspace) throw unavailable()
        await this.dependencies.renameWorkspace(request.workspaceId, request.title)
      } else {
        if (!this.dependencies.removeWorkspace) throw unavailable()
        await this.dependencies.removeWorkspace(request.workspaceId)
      }
      return { ok: true }
    }
    const record = state.sessions.find(item => item.sessionId === request.sessionId)
    const binding = record && state.workspaces.find(item => item.status === 'ready' && item.workspaceId === record.workspaceId)
    if (!record || !binding) throw new WorkspaceModeError('unknown-session', '该会话不属于 CANNBot。', 404)
    const session = await this.dependencies.readSession(request.sessionId)
    if (session.sessionId !== record.sessionId || !samePath(resolve(session.cwd), binding.path)) throw new WorkspaceModeError('session-workspace-mismatch', '会话与其登记的工作区不一致。')
    switch (request.action) {
      case 'rename-session':
        if (!this.dependencies.renameSession) throw unavailable()
        await this.dependencies.renameSession(request.sessionId, request.title); break
      case 'fork-session': {
        await this.workflowForSession(request.sessionId)
        if (!this.dependencies.forkSession) throw unavailable()
        const child = await this.dependencies.forkSession(request.sessionId, request.allowMigration)
        if (!validString(child?.sessionId) || child.sessionId === request.sessionId) throw new WorkspaceModeError('invalid-session', 'DSH 未返回可用的分支会话。', 502)
        // Forking an ungrouped native session keeps it ungrouped. Its CANNBot
        // receipt still inherits the explicit source owner, without recreating
        // a removed workspace or inferring ownership from directory alone.
        const observed = await this.dependencies.readSession(child.sessionId)
        if (observed.sessionId !== child.sessionId || !samePath(resolve(observed.cwd), binding.path)) throw new WorkspaceModeError('session-workspace-mismatch', '分支会话与原会话工作区不一致。')
        await this.change(current => {
          const owner = current.sessions.find(item => item.sessionId === record.sessionId)
          if (!owner || owner.workspaceId !== record.workspaceId || owner.pluginId !== record.pluginId) throw new WorkspaceModeError('session-conflict', '原会话归属已改变，请刷新后重试。')
          const previous = current.sessions.find(item => item.sessionId === child.sessionId)
          if (previous && (previous.workspaceId !== record.workspaceId || previous.pluginId !== record.pluginId)) throw new WorkspaceModeError('session-conflict', '分支会话已有其他归属。')
          if (!previous) current.sessions.push({ ...record, sessionId: child.sessionId })
        })
        // Match the native uiWorkspace.forkSession title policy, after its
        // onCreated-equivalent ownership receipt and before reporting success.
        if (session.title !== undefined) {
          if (!this.dependencies.renameSession) throw unavailable()
          const ascii = /^(.*?)\((\d+)\)$/u.exec(session.title), wide = /^(.*?)（(\d+)）$/u.exec(session.title)
          const title = ascii ? `${ascii[1]}(${BigInt(ascii[2]!) + 1n})` : wide ? `${wide[1]}（${BigInt(wide[2]!) + 1n}）` : `${session.title} (1)`
          await this.dependencies.renameSession(child.sessionId, title)
        }
        return { ok: true, sessionId: child.sessionId }
      }
      case 'archive-session':
        if (!this.dependencies.archiveSession) throw unavailable()
        await this.dependencies.archiveSession(request.sessionId, request.stopActivity === true); break
      case 'unarchive-session':
        if (!this.dependencies.unarchiveSession) throw unavailable()
        await this.dependencies.unarchiveSession(request.sessionId); break
      case 'pin-session':
        if (!this.dependencies.pinSession) throw unavailable()
        await this.dependencies.pinSession(request.sessionId); break
      case 'unpin-session':
        if (!this.dependencies.unpinSession) throw unavailable()
        await this.dependencies.unpinSession(request.sessionId); break
    }
    return { ok: true }
  }
  /** A persisted CANNBot session cannot switch its workflow through legacy settings. */
  async workflowForSession(sessionId: string, requested?: string): Promise<string | undefined> {
    const state = await this.read()
    let record = state.sessions.find(item => item.sessionId === sessionId)
    let id = sessionId
    const visited = new Set<string>()
    // Native forks/subagents keep parentSession in their immutable header.
    for (let depth = 0; !record && depth < 128; depth++) {
      if (visited.has(id)) throw new WorkspaceModeError('session-conflict', '会话继承链无效。')
      visited.add(id)
      let session: HostSession
      try { session = await this.dependencies.readSession(id) } catch { break }
      const workspace = state.workspaces.find(item => samePath(item.path, resolve(session.cwd)))
      if (workspace?.switchingTo) throw new WorkspaceModeError('workflow-switching', '工作流正在切换，请等待初始化完成。')
      if (!session.parentSession) break
      id = session.parentSession; record = state.sessions.find(item => item.sessionId === id)
      if (depth === 127) throw new WorkspaceModeError('session-conflict', '会话继承链过长。')
    }
    const owner = record && state.workspaces.find(item => item.workspaceId === record.workspaceId)
    if (owner?.switchingTo) throw new WorkspaceModeError('workflow-switching', '工作流正在切换，请等待初始化完成。')
    if (record && (!owner || (record.generation ?? 0) !== (owner.generation ?? 0) || record.pluginId !== owner.pluginId)) throw new WorkspaceModeError('session-frozen', '此会话所属的工作流已变更，历史记录已冻结。请在当前工作区新建会话。')
    if (record && requested && requested !== record.pluginId) throw new WorkspaceModeError('plugin-conflict', 'A CANNBot session must use its workspace workflow.')
    return record?.pluginId === GENERAL_WORKSPACE ? undefined : record?.pluginId ?? requested
  }
  async assertSessionWorkflow(sessionId: string, cwd: string, pluginId: string): Promise<void> {
    await this.workflowForSession(sessionId, pluginId)
    const state = await this.read(), session = state.sessions.find(item => item.sessionId === sessionId)
    if (!session) return
    const binding = state.workspaces.find(item => item.workspaceId === session.workspaceId)
    const directory = await this.directory(cwd)
    if (!binding || !samePath(binding.path, directory.path)) throw new WorkspaceModeError('session-workspace-mismatch', 'A CANNBot session must stay in its bound workspace.')
    this.check(binding, directory, pluginId)
  }
  async tree(): Promise<CANNBotWorkspaceTree> {
    const state = await this.read()
    const [native, summaries] = await Promise.all([this.dependencies.listWorkspaces(), this.dependencies.listSessionSummaries?.()])
    const byId = new Map((summaries ?? []).map(summary => [summary.sessionId, summary]))
    const workspaces: CANNBotWorkspace[] = [], sessions: CANNBotSession[] = []
    for (const binding of state.workspaces) {
      if (binding.status !== 'ready') continue
      const workspace = native.find(item => item.workspaceId === binding.workspaceId)
      if (!workspace) continue
      for (const record of state.sessions.filter(item => item.workspaceId === binding.workspaceId)) {
        try {
          const session = await this.dependencies.readSession(record.sessionId)
          if (session.sessionId !== record.sessionId || !samePath(resolve(session.cwd), binding.path)) continue
          const summary = byId.get(record.sessionId)
          const blank = summary?.blank ?? session.blank, running = summary?.running ?? session.running
          const time = summary?.updatedAt
          const updatedAt = typeof time === 'number' && Number.isFinite(time) && Math.abs(time) <= 8640000000000000 ? new Date(time).toISOString() : session.updatedAt
          sessions.push({ ...record, frozen: (record.generation ?? 0) !== (binding.generation ?? 0) || record.pluginId !== binding.pluginId, title: session.title, updatedAt, archived: session.archived === true, pinned: session.pinned === true,
            ...(typeof blank === 'boolean' ? { blank } : {}), ...(typeof running === 'boolean' ? { running } : {}),
            ...(session.pinned === true && Number.isSafeInteger(session.pinOrder) && session.pinOrder! >= 0 ? { pinOrder: session.pinOrder } : {}), ...(!workspace ? { ungrouped: true } : {}) })
        } catch (error) {
          // Deleted/unavailable sessions are omitted, while their explicit membership
          // is retained for reconnection. State corruption is handled before this loop.
          if ((error as NodeJS.ErrnoException).code === 'invalid-mode-state') throw error
        }
      }
      // Retain membership IDs even when one session is temporarily unreadable so
      // a DeepSeek view never mistakes it for an unregistered historical session.
      if (workspace) workspaces.push(this.workspaceView(binding, workspace, state.sessions))
    }
    return { mode: 'cannbot', platform: process.platform, workspaces, sessions }
  }
}
