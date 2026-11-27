// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdir, mkdtemp, readFile, readdir, rename, rm, symlink, writeFile } from 'node:fs/promises'
import { join, relative, resolve, sep } from 'node:path'
import { WorkspaceModes } from '../plugin/backend/workspace-mode.ts'
import { workspaceModeResponse, registerWorkspaceModes } from '../plugin/backend/workspace-mode-host.ts'
import { ContentManager } from '../plugin/backend/content-manager.ts'

const ownedRoot = resolve('.acceptance-workspace-mode-tests')
async function fixture(t) {
  await mkdir(ownedRoot, { recursive: true })
  const directory = await mkdtemp(join(ownedRoot, 'case-'))
  t.after(async () => {
    const diff = relative(ownedRoot, directory)
    assert(diff && diff !== '..' && !diff.startsWith('..' + sep))
    await rm(directory, { recursive: true, force: true })
  })
  const root = join(directory, 'host-state'), project = join(directory, 'project'), other = join(directory, 'other')
  await Promise.all([mkdir(project), mkdir(other)])
  const native = new Map(), sessions = new Map(), initialized = [], registrations = []
  let nextWorkspaceId = 0
  let prepare = async (path, pluginId) => { initialized.push({ path, pluginId }); await writeFile(join(path, 'plugin.txt'), pluginId) }
  const dependencies = {
    platform: 'linux',
    available: id => ['flow-a', 'flow-b'].includes(id),
    prepare: (path, id) => modes.withPreparation(path, id, () => prepare(path, id)),
    async createWorkspace(path) {
      const existing = [...native.values()].find(item => item.path === path)
      if (existing) return { workspace: existing, created: false }
      const workspace = { workspaceId: `workspace-${++nextWorkspaceId}`, path, title: 'Project', sessionIds: [] }
      registrations.push(path); native.set(workspace.workspaceId, workspace)
      return { workspace, created: true }
    },
    async listWorkspaces() { return [...native.values()] },
    async readSession(id) { const session = sessions.get(id); if (!session) throw new Error('session missing'); return session },
    async renameWorkspace(id, title) { native.get(id).title = title },
    async removeWorkspace(id) { native.delete(id) },
    async renameSession(id, title) { sessions.get(id).title = title },
    async forkSession(id) {
      const source = sessions.get(id), child = { ...source, sessionId: 'fork-' + id }
      sessions.set(child.sessionId, child)
      for (const workspace of native.values()) if (workspace.sessionIds.includes(id)) workspace.sessionIds.push(child.sessionId)
      return { sessionId: child.sessionId }
    },
    async archiveSession(id, stopActivity) { const session = sessions.get(id); if (session.running && !stopActivity) throw Object.assign(new Error('unsafe original detail token=SECRET'), { code: 'workspace/session-active', details: { activity: [{ kind: 'turn' }, { kind: 'job', items: [{ id: 'job-one', label: 'Build', secret: 'NO' }] }] } }); session.running = false; session.archived = true; session.pinned = false },
    async unarchiveSession(id) { sessions.get(id).archived = false },
    async pinSession(id) { sessions.get(id).pinned = true },
    async unpinSession(id) { sessions.get(id).pinned = false },
  }
  const modes = new WorkspaceModes(root, dependencies)
  return { directory, root, project, other, native, sessions, initialized, registrations, dependencies, modes,
    prepare: value => { prepare = value },
    session(id, workspace, cwd = workspace.path) {
      const session = { sessionId: id, cwd, title: 'Saved session title', updatedAt: '2026-01-01T00:00:00.000Z', archived: false }
      sessions.set(id, session); native.get(workspace.workspaceId).sessionIds.push(id); return session
    },
  }
}
const request = body => new Request('http://localhost/api/cannbot-dsh/workspaces', { method: 'POST', body: JSON.stringify(body) })

test('Windows rejects local workflow creation through legacy routes but still allows blank workspaces', async t => {
  const f = await fixture(t); f.dependencies.platform = 'win32'
  const response = await workspaceModeResponse(f.modes, request({ action: 'create', path: f.project, pluginId: 'flow-a' }))
  assert.equal(response.status, 400); assert.equal((await response.json()).error, 'workflow-linux-only')
  assert.equal(f.initialized.length, 0)
  assert.equal((await f.modes.create(f.project, 'general')).pluginId, 'general')
})

test('workflow activation generations freeze history and native descendants across restart and switching back', async t => {
  const f = await fixture(t); f.dependencies.platform = 'linux'; f.dependencies.sessionActivity = async () => []
  f.dependencies.switchWorkflow = async (_path, _old, _next, commit) => commit()
  const workspace = await f.modes.create(f.project, 'flow-a')
  f.session('old', workspace); await f.modes.recordSession(workspace.workspaceId, 'old')
  await f.modes.switchWorkflow(workspace.workspaceId, 'flow-b')
  assert.equal((await f.modes.tree()).sessions[0].frozen, true)
  await assert.rejects(f.modes.workflowForSession('old'), { code: 'session-frozen' })
  f.session('native-fork', workspace).parentSession = 'old'
  await assert.rejects(f.modes.workflowForSession('native-fork'), { code: 'session-frozen' })
  await assert.rejects(f.modes.recordSession(workspace.workspaceId, 'native-fork'), { code: 'session-frozen' })
  f.session('new', workspace); await f.modes.recordSession(workspace.workspaceId, 'new')
  assert.equal(await f.modes.workflowForSession('new'), 'flow-b')
  const reboot = new WorkspaceModes(f.root, f.dependencies)
  await reboot.switchWorkflow(workspace.workspaceId, 'flow-a')
  await assert.rejects(reboot.workflowForSession('old'), { code: 'session-frozen' })
  await assert.rejects(reboot.workflowForSession('new'), { code: 'session-frozen' })
  await assert.rejects(reboot.operate({ action: 'fork-session', sessionId: 'old' }), { code: 'session-frozen' })
  await reboot.operate({ action: 'rename-session', sessionId: 'old', title: '保留的历史' })
  assert.equal((await reboot.tree()).sessions.find(row => row.sessionId === 'old').title, '保留的历史')
})

test('workflow switch gates new execution, refuses active jobs, and restores previous activation after initializer failure', async t => {
  const f = await fixture(t); f.dependencies.platform = 'linux'
  const workspace = await f.modes.create(f.project, 'flow-a')
  f.session('old', workspace); await f.modes.recordSession(workspace.workspaceId, 'old')
  let calls = 0
  f.dependencies.sessionActivity = async () => [{ kind: 'job' }]
  f.dependencies.switchWorkflow = async () => { calls++; throw new Error('questionnaire failed') }
  await assert.rejects(f.modes.switchWorkflow(workspace.workspaceId, 'flow-b'), { code: 'workflow-active' })
  assert.equal(calls, 0); assert.equal(await f.modes.workflowForSession('old'), 'flow-a')
  f.dependencies.sessionActivity = async () => { await assert.rejects(f.modes.workflowForSession('old'), { code: 'workflow-switching' }); return [] }
  await assert.rejects(f.modes.switchWorkflow(workspace.workspaceId, 'flow-b'), /questionnaire failed/)
  assert.equal(await f.modes.workflowForSession('old'), 'flow-a')
  assert.equal((await f.modes.tree()).sessions[0].frozen, false)
  f.dependencies.platform = 'win32'
  await assert.rejects(f.modes.switchWorkflow(workspace.workspaceId, 'flow-b'), { code: 'workflow-linux-only' })
})

test('terminal preparation defers native workspace registration until Host startup', async t => {
  const f = await fixture(t)
  await f.modes.prepareBeforeLaunch(f.project, 'flow-a')
  assert.equal(f.registrations.length, 0)
  f.dependencies.prepare = async () => {}
  await new WorkspaceModes(f.root, f.dependencies).registerPreparedWorkspaces()
  assert.equal(f.registrations.length, 1)
  assert.equal((await f.modes.tree()).workspaces[0].pluginId, 'flow-a')
})

test('general workspaces persist membership without installing or injecting a workflow', async t => {
  const f = await fixture(t)
  f.dependencies.available = () => false
  const workspace = await f.modes.create(f.project, 'general')
  assert.equal(workspace.pluginId, 'general')
  assert.deepEqual(f.initialized, [])
  assert.deepEqual(await readdir(f.project), [])
  f.session('general-session', workspace)
  await f.modes.recordSession(workspace.workspaceId, 'general-session')
  const reboot = new WorkspaceModes(f.root, f.dependencies)
  assert.equal((await reboot.tree()).sessions[0].sessionId, 'general-session')
  assert.equal(await reboot.workflowForSession('general-session'), undefined)
  await assert.rejects(reboot.workflowForSession('general-session', 'flow-a'), { code: 'plugin-conflict' })
  await assert.rejects(reboot.withPreparation(f.project, 'flow-a', async () => {}), { code: 'plugin-conflict' })
})

test('historical objects default to DeepSeek; only explicit CANNBot sessions appear after restart', async t => {
  const f = await fixture(t)
  f.native.set('historical', { workspaceId: 'historical', path: f.other, title: 'Old project', sessionIds: ['old-session'] })
  assert.deepEqual(await f.modes.tree(), { mode: 'cannbot', platform: process.platform, workspaces: [], sessions: [] })
  const workspace = await f.modes.create(f.project, 'flow-a')
  assert.equal(workspace.sharedWithDeepSeek, false)
  assert.equal(await readFile(join(f.project, 'plugin.txt'), 'utf8'), 'flow-a')
  f.session('cann-session', workspace); f.session('deepseek-session', workspace)
  assert.deepEqual((await f.modes.tree()).workspaces[0].sessionIds, [])
  await f.modes.recordSession(workspace.workspaceId, 'cann-session')
  const reboot = new WorkspaceModes(f.root, f.dependencies), tree = await reboot.tree()
  assert.deepEqual(tree.workspaces[0].sessionIds, ['cann-session'])
  assert.equal(tree.sessions[0].title, 'Saved session title')
  assert.equal(tree.sessions[0].pluginId, 'flow-a')
  assert.equal(await reboot.workflowForSession('deepseek-session'), undefined)
  assert.equal(await reboot.workflowForSession('cann-session'), 'flow-a')
})

test('existing empty DeepSeek workspace is reused and retains its original mode visibility', async t => {
  const f = await fixture(t)
  f.native.set('old-empty', { workspaceId: 'old-empty', path: f.project, title: 'Empty DSH project', sessionIds: [] })
  const workspace = await f.modes.create(f.project, 'flow-a')
  assert.equal(workspace.workspaceId, 'old-empty')
  assert.equal(workspace.sharedWithDeepSeek, true)
  assert.equal(f.registrations.length, 0)
})

test('nonempty and unknown-plugin requests are rejected without initializer or state ownership changes', async t => {
  const f = await fixture(t)
  await writeFile(join(f.project, 'keep.txt'), 'user data')
  await assert.rejects(f.modes.create(f.project, 'flow-a'), error => error.code === 'directory-not-empty')
  await assert.rejects(f.modes.create(f.other, 'not-installed'), error => error.code === 'invalid-plugin')
  assert.equal(f.initialized.length, 0)
  assert.deepEqual(await readdir(f.other), [])
  assert.equal(await readFile(join(f.project, 'keep.txt'), 'utf8'), 'user data')
  assert.deepEqual((await f.modes.tree()).workspaces, [])
})

test('failed initialization can retry only its reserved plugin, including across process-style restarts', async t => {
  const f = await fixture(t)
  f.prepare(async path => { await writeFile(join(path, 'partial.txt'), 'safe recovery input'); throw new Error('initializer interrupted') })
  await assert.rejects(f.modes.create(f.project, 'flow-a'), /interrupted/)
  assert.equal(f.native.size, 0)
  await assert.rejects(new WorkspaceModes(f.root, f.dependencies).create(f.project, 'flow-b'), error => error.code === 'plugin-conflict')
  f.prepare(async path => { assert.equal(await readFile(join(path, 'partial.txt'), 'utf8'), 'safe recovery input'); await writeFile(join(path, 'plugin.txt'), 'flow-a') })
  const completed = await f.modes.create(f.project, 'flow-a')
  assert.equal(completed.pluginId, 'flow-a')
  assert.equal(f.native.size, 1)
})

test('registration failure retries without duplicate workspaces or changing the reserved plugin', async t => {
  const f = await fixture(t), create = f.dependencies.createWorkspace
  let calls = 0
  f.dependencies.createWorkspace = async path => { if (++calls === 1) throw new Error('registry temporarily offline'); return create(path) }
  await assert.rejects(f.modes.create(f.project, 'flow-a'), /temporarily offline/)
  assert.equal(f.native.size, 0)
  const ready = await f.modes.create(f.project, 'flow-a')
  assert.equal(ready.pluginId, 'flow-a')
  assert.equal((await f.modes.create(f.project, 'flow-a')).workspaceId, ready.workspaceId)
  assert.equal(f.registrations.length, 1)
})

test('realpath aliases and concurrent manager instances cannot bind a second plugin', async t => {
  const f = await fixture(t), alias = join(f.directory, 'project-link')
  await symlink(f.project, alias, process.platform === 'win32' ? 'junction' : 'dir')
  const second = new WorkspaceModes(f.root, { ...f.dependencies, prepare: async (path, id) => { f.initialized.push({ path, pluginId: id }); await writeFile(join(path, 'plugin.txt'), id) } })
  const results = await Promise.allSettled([f.modes.create(f.project, 'flow-a'), second.create(alias, 'flow-b')])
  assert.equal(results.filter(item => item.status === 'fulfilled').length, 1)
  assert.equal(results.find(item => item.status === 'rejected').reason.code, 'plugin-conflict')
  assert.equal(f.initialized.length, 1)
  const plugin = (await f.modes.tree()).workspaces[0].pluginId
  assert.equal((await f.modes.create(alias, plugin)).workspaceId, (await f.modes.tree()).workspaces[0].workspaceId)
})

test('parallel creation in distinct directories does not lose global state updates', async t => {
  const f = await fixture(t)
  await Promise.all([f.modes.create(f.project, 'flow-a'), f.modes.create(f.other, 'flow-b')])
  const tree = await new WorkspaceModes(f.root, f.dependencies).tree()
  assert.deepEqual(new Set(tree.workspaces.map(item => item.pluginId)), new Set(['flow-a', 'flow-b']))
})

test('legacy content initialization is unchanged for unbound directories and guarded for bound ones', async t => {
  const f = await fixture(t)
  await writeFile(join(f.other, 'existing-code.txt'), 'code')
  let legacyRuns = 0
  await f.modes.withPreparation(f.other, 'flow-a', async () => { legacyRuns++ })
  assert.equal(legacyRuns, 1)
  // Existing DeepSeek sessions may use a home directory containing Host state.
  await f.modes.withPreparation(f.directory, 'flow-a', async () => { legacyRuns++ })
  assert.deepEqual((await f.modes.tree()).workspaces, [])
  await f.modes.create(f.project, 'flow-a')
  await assert.rejects(f.modes.withPreparation(f.project, 'flow-b', async () => { legacyRuns++ }), error => error.code === 'plugin-conflict')
  assert.equal(legacyRuns, 2)
})

test('real ContentManager blocks a second plugin before fetching or running its initializer', async t => {
  const f = await fixture(t), defaults = join(f.directory, 'defaults.json')
  await f.modes.create(f.project, 'flow-a')
  await writeFile(defaults, JSON.stringify({ workflows: ['flow-a', 'flow-b'].map(id => ({ id, title: id, package: '@cannbot-plugin/workflow-' + id, default: true })) }))
  const offline = { async manifest() { assert.fail('must not download a conflicting plugin') }, async extract() { assert.fail('must not extract a conflicting plugin') } }
  const content = new ContentManager(defaults, join(f.directory, 'content-cache'), offline)
  content.setPreparationGuard((cwd, id, run) => f.modes.withPreparation(cwd, id, run))
  await assert.rejects(content.prepare(f.project, 'flow-b'), error => error.code === 'plugin-conflict')
  assert.equal(await readFile(join(f.project, 'plugin.txt'), 'utf8'), 'flow-a')
})

test('unreadable CANNBot sessions retain their mode membership and cannot reappear as DeepSeek history', async t => {
  const f = await fixture(t), workspace = await f.modes.create(f.project, 'flow-a')
  f.session('bound', workspace); await f.modes.recordSession(workspace.workspaceId, 'bound')
  f.sessions.delete('bound')
  const tree = await f.modes.tree()
  assert.deepEqual(tree.workspaces[0].sessionIds, ['bound'])
  assert.deepEqual(tree.sessions, [])
})

test('session registration verifies actual cwd and workflow/cwd cannot later switch', async t => {
  const f = await fixture(t), workspace = await f.modes.create(f.project, 'flow-a')
  f.sessions.set('same-path-unregistered', { sessionId: 'same-path-unregistered', cwd: f.project })
  await assert.rejects(f.modes.recordSession(workspace.workspaceId, 'same-path-unregistered'), error => error.code === 'session-workspace-mismatch')
  f.session('foreign', workspace, f.other)
  await assert.rejects(f.modes.recordSession(workspace.workspaceId, 'foreign'), error => error.code === 'session-workspace-mismatch')
  f.session('allowed', workspace)
  await f.modes.recordSession(workspace.workspaceId, 'allowed')
  await f.modes.recordSession(workspace.workspaceId, 'allowed')
  assert.deepEqual((await f.modes.tree()).workspaces[0].sessionIds, ['allowed'])
  await assert.rejects(f.modes.workflowForSession('allowed', 'flow-b'), error => error.code === 'plugin-conflict')
  await assert.rejects(f.modes.assertSessionWorkflow('allowed', f.other, 'flow-a'), error => error.code === 'session-workspace-mismatch')
  await assert.rejects(f.modes.assertSessionWorkflow('allowed', f.project, 'flow-b'), error => error.code === 'plugin-conflict')
  await f.modes.assertSessionWorkflow('allowed', f.project, 'flow-a')
})

test('replacing a bound physical directory does not silently reuse its reservation', async t => {
  const f = await fixture(t)
  await f.modes.create(f.project, 'flow-a')
  await rename(f.project, join(f.directory, 'original-project')); await mkdir(f.project)
  await assert.rejects(f.modes.create(f.project, 'flow-a'), error => error.code === 'directory-replaced')
  await assert.rejects(f.modes.withPreparation(f.project, 'flow-a', async () => {}), error => error.code === 'directory-replaced')
  assert.deepEqual(await readdir(f.project), [])
})

test('invalid persisted state fails closed instead of treating bound directories as new', async t => {
  const f = await fixture(t)
  await mkdir(f.root, { recursive: true }); await writeFile(join(f.root, 'state.json'), '{invalid')
  await assert.rejects(f.modes.create(f.project, 'flow-a'), error => error.code === 'invalid-mode-state')
  await assert.rejects(f.modes.withPreparation(f.other, 'flow-a', async () => assert.fail('must not initialize')), error => error.code === 'invalid-mode-state')
})

test('HTTP contract returns CANNBot-only tree and actionable non-success validation errors', async t => {
  const f = await fixture(t)
  let response = await workspaceModeResponse(f.modes, request({ action: 'create', path: f.project, pluginId: 'flow-a' }))
  assert.equal(response.status, 200)
  const { workspace } = await response.json()
  f.session('new-session', workspace)
  response = await workspaceModeResponse(f.modes, request({ action: 'session', workspaceId: workspace.workspaceId, sessionId: 'new-session' }))
  assert.equal((await response.json()).session.pluginId, 'flow-a')
  response = await workspaceModeResponse(f.modes, request({ action: 'create', path: f.project, pluginId: 'flow-b' }))
  assert.equal(response.status, 409)
  const conflict = await response.json()
  assert.equal(conflict.error, 'plugin-conflict')
  assert.match(conflict.message, /bound to another CANNBot workflow/)
  assert.equal((await workspaceModeResponse(f.modes, request({ action: 'create', path: f.other, pluginId: ['flow-a', 'flow-b'] }))).status, 400)
  response = await workspaceModeResponse(f.modes, new Request('http://localhost/api/cannbot-dsh/workspaces'))
  assert.equal(response.headers.get('cache-control'), 'no-store')
  assert.deepEqual((await response.json()).sessions.map(item => item.sessionId), ['new-session'])
})

test('Host adapter closes baseline subscriptions, reads real session title, and installs the content guard', async t => {
  const f = await fixture(t)
  let guard, route, closed = 0, observations = 0
  const ctx = {
    inject(keys, callback) { callback(this) },
    effect() {},
    workspaceController: {
      create: ({ path }) => f.dependencies.createWorkspace(path),
      async *follow() { try { yield { type: 'baseline', value: { items: [...f.native.values()], archivedSessionIds: ['bound'], pinnedSessionIds: ['bound-second', 'deepseek-only', 'bound'] } } } finally { closed++ } },
    },
    sessionQuery: {
      async observeSession(id) { return { header: { id, cwd: f.sessions.get(id)?.cwd, createdAt: 1000 }, [Symbol.dispose]() { observations++ } } },
      async readTitleSnapshot() { return { title: { title: 'Persisted title', updatedAt: 2000 } } },
    },
    connection: { fetch: { register(value) { route = value } } },
  }
  const content = { root: f.root, getSource: () => ({ catalog: { plugins: [{ id: 'flow-a' }] } }), setPreparationGuard(value) { guard = value }, prepare: (path, id) => guard(path, id, async () => {}) }
  const modes = registerWorkspaceModes(ctx, content)
  const workspace = await modes.create(f.project, 'general')
  f.session('bound', workspace)
  await modes.recordSession(workspace.workspaceId, 'bound')
  f.session('bound-second', workspace)
  await modes.recordSession(workspace.workspaceId, 'bound-second')
  f.session('unpinned', workspace)
  await modes.recordSession(workspace.workspaceId, 'unpinned')
  const tree = await modes.tree()
  assert.equal(tree.sessions[0].title, 'Persisted title')
  assert.equal(tree.sessions[0].archived, true)
  assert.equal(tree.sessions[0].pinned, true)
  assert.equal(tree.sessions[0].pinOrder, 2)
  assert.equal(tree.sessions[1].pinOrder, 0)
  assert.equal(tree.sessions[2].pinned, false)
  assert.equal(Object.hasOwn(tree.sessions[2], 'pinOrder'), false)
  assert.deepEqual(tree.sessions.filter(item => item.pinned).sort((a, b) => a.pinOrder - b.pinOrder).map(item => item.sessionId), ['bound-second', 'bound'])
  assert.equal(tree.sessions[0].updatedAt, '1970-01-01T00:00:01.000Z')
  assert.equal(Object.hasOwn(tree.sessions[0], 'blank'), false)
  assert.equal(Object.hasOwn(tree.sessions[0], 'running'), false)
  assert(closed >= 2); assert(observations >= 2)
  assert.equal(route.path, '/api/cannbot-dsh/workspaces')
  await assert.rejects(guard(f.project, 'flow-b', async () => assert.fail('second plugin must be blocked')), error => error.code === 'plugin-conflict')
})

test('tree batches native summaries once, follows native activity/blank/running facts, and degrades without inventing live state', async t => {
  const f = await fixture(t)
  let listCalls = 0, unavailable = false
  const ctx = {
    inject(_keys, callback) { callback(this) }, effect() {},
    workspaceController: {
      create: ({ path }) => f.dependencies.createWorkspace(path),
      async *follow() { yield { type: 'baseline', value: { items: [...f.native.values()], archivedSessionIds: [], pinnedSessionIds: [] } } },
    },
    sessionController: {
      async list(request, signal) {
        listCalls++; assert.deepEqual(request, {}); assert(signal instanceof AbortSignal)
        if (unavailable) throw new Error('native projection temporarily unavailable')
        return { items: [
          { sessionId: 'started', updatedAt: 5000, blank: false, running: true },
          { sessionId: 'draft', updatedAt: 3000, blank: true, running: false },
          { sessionId: 'deepseek-only', updatedAt: 9000, blank: false, running: true },
        ] }
      },
    },
    sessionQuery: {
      async observeSession(id) { return { header: { id, cwd: f.sessions.get(id)?.cwd, createdAt: 1000 },
        ...(id === 'fallback' ? { projections: { values: { sessionListMetadata: { blank: true, lastPromptAt: 2000 } } } } : {}), [Symbol.dispose]() {} } },
      async readTitleSnapshot() { return { title: { title: 'Renamed recently', updatedAt: 99000 } } },
    }, connection: { fetch: { register() {} } },
  }
  const content = { root: f.root, getSource: () => ({ catalog: { plugins: [{ id: 'flow-a' }] } }), setPreparationGuard() {}, async prepare() {} }
  const modes = registerWorkspaceModes(ctx, content), workspace = await modes.create(f.project, 'general')
  for (const id of ['started', 'draft', 'fallback']) { f.session(id, workspace); await modes.recordSession(workspace.workspaceId, id) }
  assert.equal(listCalls, 0)
  let tree = await modes.tree()
  assert.equal(listCalls, 1); assert.equal(tree.sessions.length, 3)
  assert.deepEqual(tree.sessions.map(({ sessionId, updatedAt, blank, running }) => ({ sessionId, updatedAt, blank, running })), [
    { sessionId: 'started', updatedAt: '1970-01-01T00:00:05.000Z', blank: false, running: true },
    { sessionId: 'draft', updatedAt: '1970-01-01T00:00:03.000Z', blank: true, running: false },
    { sessionId: 'fallback', updatedAt: '1970-01-01T00:00:02.000Z', blank: true, running: undefined },
  ])
  assert.equal(Object.hasOwn(tree.sessions[2], 'running'), false)
  unavailable = true; tree = await modes.tree()
  assert.equal(listCalls, 2); assert.equal(tree.sessions.length, 3)
  assert.equal(tree.sessions[0].updatedAt, '1970-01-01T00:00:01.000Z')
  assert.equal(Object.hasOwn(tree.sessions[0], 'blank'), false)
  assert.equal(Object.hasOwn(tree.sessions[0], 'running'), false)
  assert.equal(tree.sessions[2].blank, true)
})

test('workspace rename/delete delegates native records and preserves files and ungrouped CANNBot history', async t => {
  const f = await fixture(t), workspace = await f.modes.create(f.project, 'flow-a')
  f.session('owned', workspace); await f.modes.recordSession(workspace.workspaceId, 'owned')
  const initialState = await readFile(join(f.root, 'state.json'), 'utf8')
  let response = await workspaceModeResponse(f.modes, request({ action: 'rename-workspace', workspaceId: workspace.workspaceId, title: ' Renamed ' }))
  assert.equal(response.status, 200)
  assert.equal((await f.modes.tree()).workspaces[0].title, 'Renamed')
  response = await workspaceModeResponse(f.modes, request({ action: 'remove-workspace', workspaceId: workspace.workspaceId }))
  assert.equal(response.status, 200)
  assert.equal(await readFile(join(f.project, 'plugin.txt'), 'utf8'), 'flow-a')
  assert.equal(await readFile(join(f.root, 'state.json'), 'utf8'), initialState)
  const tree = await new WorkspaceModes(f.root, f.dependencies).tree()
  assert.deepEqual(tree.workspaces, [])
  assert.deepEqual(tree.sessions, [])
  assert.equal(await f.modes.workflowForSession('owned'), 'flow-a')
  // Native removal also remains possible after the directory itself moved away.
  const second = await f.modes.create(f.other, 'flow-b')
  await rename(f.other, f.other + '-moved')
  assert.equal((await workspaceModeResponse(f.modes, request({ action: 'remove-workspace', workspaceId: second.workspaceId }))).status, 200)
})

test('CANNBot operations reject unregistered shared-cwd sessions and foreign workspaces before mutation', async t => {
  const f = await fixture(t), workspace = await f.modes.create(f.project, 'flow-a')
  f.session('deepseek', workspace)
  for (const action of ['rename-session', 'fork-session', 'pin-session', 'unpin-session', 'archive-session', 'unarchive-session']) {
    const response = await workspaceModeResponse(f.modes, request({ action, sessionId: 'deepseek', title: 'Denied', stopActivity: true }))
    assert.equal(response.status, 404)
    assert.equal((await response.json()).error, 'unknown-session')
  }
  f.native.set('deepseek-workspace', { workspaceId: 'deepseek-workspace', path: f.other, title: 'DS', sessionIds: [] })
  for (const action of ['rename-workspace', 'remove-workspace']) assert.equal((await workspaceModeResponse(f.modes, request({ action, workspaceId: 'deepseek-workspace', title: 'Denied' }))).status, 404)
  assert.equal(f.sessions.get('deepseek').title, 'Saved session title')
  assert.equal(f.native.get('deepseek-workspace').title, 'DS')
})

test('session rename, pin, archive, restore work for explicit CANNBot members including ungrouped records', async t => {
  const f = await fixture(t), workspace = await f.modes.create(f.project, 'flow-a')
  f.session('owned', workspace); await f.modes.recordSession(workspace.workspaceId, 'owned')
  for (const action of ['rename-session', 'pin-session']) assert.equal((await workspaceModeResponse(f.modes, request({ action, sessionId: 'owned', title: 'Pinned session' }))).status, 200)
  let tree = await f.modes.tree()
  assert.equal(tree.sessions[0].title, 'Pinned session'); assert.equal(tree.sessions[0].pinned, true)
  await f.modes.operate({ action: 'remove-workspace', workspaceId: workspace.workspaceId })
  for (const action of ['unpin-session', 'archive-session']) assert.equal((await workspaceModeResponse(f.modes, request({ action, sessionId: 'owned' }))).status, 200)
  tree = await f.modes.tree()
  assert.deepEqual(tree.sessions, [])
  assert.equal(f.sessions.get('owned').pinned, false); assert.equal(f.sessions.get('owned').archived, true)
  assert.equal((await workspaceModeResponse(f.modes, request({ action: 'unarchive-session', sessionId: 'owned' }))).status, 200)
  assert.deepEqual((await f.modes.tree()).sessions, []); assert.equal(f.sessions.get('owned').archived, false)
})

test('active archive returns safe activity without stopping work until explicit confirmation', async t => {
  const f = await fixture(t), workspace = await f.modes.create(f.project, 'flow-a')
  const session = f.session('running', workspace); await f.modes.recordSession(workspace.workspaceId, 'running'); session.running = true
  let response = await workspaceModeResponse(f.modes, request({ action: 'archive-session', sessionId: 'running' }))
  assert.equal(response.status, 409)
  const error = await response.json()
  assert.equal(error.error, 'workspace/session-active')
  assert.deepEqual(error.activity, [{ kind: 'turn' }, { kind: 'job', items: [{ id: 'job-one', label: 'Build' }] }])
  assert(!JSON.stringify(error).includes('SECRET')); assert(!JSON.stringify(error).includes('secret'))
  assert.equal(session.running, true); assert.equal(session.archived, false)
  response = await workspaceModeResponse(f.modes, request({ action: 'archive-session', sessionId: 'running', stopActivity: true }))
  assert.equal(response.status, 200); assert.equal(session.running, false); assert.equal(session.archived, true)
})

test('fork registers the child before returning, including a deleted workspace owner', async t => {
  const f = await fixture(t), workspace = await f.modes.create(f.project, 'flow-a')
  f.session('source', workspace); await f.modes.recordSession(workspace.workspaceId, 'source')
  let response = await workspaceModeResponse(f.modes, request({ action: 'fork-session', sessionId: 'source' }))
  assert.equal(response.status, 200); assert.deepEqual(await response.json(), { ok: true, sessionId: 'fork-source' })
  assert.equal(await new WorkspaceModes(f.root, f.dependencies).workflowForSession('fork-source'), 'flow-a')
  assert.equal(f.sessions.get('fork-source').title, 'Saved session title (1)')
  await f.modes.operate({ action: 'remove-workspace', workspaceId: workspace.workspaceId })
  response = await workspaceModeResponse(f.modes, request({ action: 'fork-session', sessionId: 'fork-source' }))
  assert.deepEqual(await response.json(), { ok: true, sessionId: 'fork-fork-source' })
  const tree = await f.modes.tree()
  assert.deepEqual(tree.workspaces, [])
  assert.deepEqual(tree.sessions, [])
  assert.equal(await f.modes.workflowForSession('fork-fork-source'), 'flow-a')
  assert.equal(f.sessions.get('fork-fork-source').title, 'Saved session title (2)')
  f.dependencies.forkSession = async () => { f.sessions.set('bad-child', { sessionId: 'bad-child', cwd: f.other }); return { sessionId: 'bad-child' } }
  response = await workspaceModeResponse(f.modes, request({ action: 'fork-session', sessionId: 'source' }))
  assert.equal(response.status, 409); assert.equal(await f.modes.workflowForSession('bad-child'), undefined)
})

test('fork follows native full-width title suffix and leaves ownership intact if title update fails', async t => {
  const f = await fixture(t), workspace = await f.modes.create(f.project, 'flow-a')
  const source = f.session('source', workspace); source.title = '算子（3）'
  await f.modes.recordSession(workspace.workspaceId, 'source')
  const originalFork = f.dependencies.forkSession, choices = []
  f.dependencies.forkSession = (id, allowMigration) => { choices.push(allowMigration); return originalFork(id) }
  let response = await workspaceModeResponse(f.modes, request({ action: 'fork-session', sessionId: 'source', allowMigration: false }))
  assert.equal(response.status, 200); assert.equal(f.sessions.get('fork-source').title, '算子（4）')
  f.dependencies.renameSession = async () => { throw new Error('token=PRIVATE') }
  response = await workspaceModeResponse(f.modes, request({ action: 'fork-session', sessionId: 'fork-source', allowMigration: true }))
  assert.equal(response.status, 500)
  assert.equal(await f.modes.workflowForSession('fork-fork-source'), 'flow-a')
  assert(!JSON.stringify(await response.json()).includes('PRIVATE'))
  assert.deepEqual(choices, [false, true])
})

test('Host mutation adapter uses the official controller request shapes and default migration behavior', async t => {
  const f = await fixture(t), calls = []
  const ctx = {
    inject(_keys, callback) { callback(this) }, effect() {},
    workspaceController: {
      create: ({ path }) => f.dependencies.createWorkspace(path),
      async *follow() { yield { type: 'baseline', value: { items: [...f.native.values()], archivedSessionIds: [], pinnedSessionIds: [] } } },
      rename: value => { calls.push(['renameWorkspace', value]); return f.dependencies.renameWorkspace(value.workspaceId, value.title) },
      delete: value => { calls.push(['delete', value]); return f.dependencies.removeWorkspace(value.workspaceId) },
      archiveSession: value => { calls.push(['archive', value]); return f.dependencies.archiveSession(value.sessionId, value.stopActivity) },
      pinSession: value => { calls.push(['pin', value]); return f.dependencies.pinSession(value.sessionId) },
      unpinSession: value => { calls.push(['unpin', value]); return f.dependencies.unpinSession(value.sessionId) },
      unarchiveSession: value => { calls.push(['unarchive', value]); return f.dependencies.unarchiveSession(value.sessionId) },
    },
    sessionController: {
      rename: value => { calls.push(['renameSession', value]); return f.dependencies.renameSession(value.sessionId, value.title) },
      fork: value => { calls.push(['fork', value]); return f.dependencies.forkSession(value.sessionId) },
    },
    sessionQuery: {
      async observeSession(id) { return { header: { id, cwd: f.sessions.get(id)?.cwd }, [Symbol.dispose]() {} } },
      async readTitleSnapshot(id) { const title = f.sessions.get(id)?.title; return title ? { title: { title } } : {} },
    }, connection: { fetch: { register() {} } },
  }
  const content = { root: f.root, getSource: () => ({ catalog: { plugins: [{ id: 'flow-a' }] } }), setPreparationGuard() {}, async prepare() {} }
  const modes = registerWorkspaceModes(ctx, content), workspace = await modes.create(f.project, 'general')
  f.session('owned', workspace); await modes.recordSession(workspace.workspaceId, 'owned')
  for (const action of ['pin-session', 'unpin-session', 'archive-session', 'unarchive-session']) await modes.operate({ action, sessionId: 'owned' })
  await modes.operate({ action: 'archive-session', sessionId: 'owned', stopActivity: true })
  await modes.operate({ action: 'fork-session', sessionId: 'owned' })
  await modes.operate({ action: 'rename-workspace', workspaceId: workspace.workspaceId, title: 'Project renamed' })
  await modes.operate({ action: 'remove-workspace', workspaceId: workspace.workspaceId })
  assert.deepEqual(calls, [
    ['pin', { sessionId: 'owned' }], ['unpin', { sessionId: 'owned' }], ['archive', { sessionId: 'owned' }], ['unarchive', { sessionId: 'owned' }],
    ['archive', { sessionId: 'owned', stopActivity: true }], ['fork', { sessionId: 'owned' }],
    ['renameSession', { sessionId: 'fork-owned', title: 'Saved session title (1)' }],
    ['renameWorkspace', { workspaceId: workspace.workspaceId, title: 'Project renamed' }], ['delete', { workspaceId: workspace.workspaceId }],
  ])
})

test('invalid mutations and native errors have bounded safe responses', async t => {
  const f = await fixture(t), workspace = await f.modes.create(f.project, 'flow-a')
  f.session('owned', workspace); await f.modes.recordSession(workspace.workspaceId, 'owned')
  for (const body of [{ action: 'rename-workspace', workspaceId: workspace.workspaceId, title: ' ' }, { action: 'rename-session', sessionId: 'owned', title: 'x\ny' }, { action: 'archive-session', sessionId: 'owned', stopActivity: 'true' }, { action: 'unknown', sessionId: 'owned' }]) assert.equal((await workspaceModeResponse(f.modes, request(body))).status, 400)
  f.dependencies.renameWorkspace = async () => { throw Object.assign(new Error('private'), { code: 'workspace/name-conflict' }) }
  let response = await workspaceModeResponse(f.modes, request({ action: 'rename-workspace', workspaceId: workspace.workspaceId, title: 'Used' }))
  assert.equal(response.status, 409); assert.equal((await response.json()).error, 'workspace/name-conflict')
  f.dependencies.renameSession = async () => { throw new Error('http://127.0.0.1/?token=PRIVATE') }
  response = await workspaceModeResponse(f.modes, request({ action: 'rename-session', sessionId: 'owned', title: 'New' }))
  assert.equal(response.status, 500); assert(!JSON.stringify(await response.json()).includes('PRIVATE'))
})

// New-folder creation cannot turn an existing directory into a CANNBot workspace.
test('new-folder endpoint requires an explicit type, rejects existing paths, and retries one receipt', async t => {
  const f = await fixture(t)
  const body = { action: 'create-folder', parent: f.directory, name: 'new-blank', pluginId: 'general', requestId: '12345678-1234-1234-1234-123456789abc' }
  const response = await workspaceModeResponse(f.modes, request(body))
  assert.equal(response.status, 200)
  const created = (await response.json()).workspace
  assert.equal(created.path, join(f.directory, 'new-blank'))
  assert.deepEqual(await readdir(created.path), [])
  assert.deepEqual(f.initialized, [])
  const retry = await workspaceModeResponse(f.modes, request(body))
  assert.equal((await retry.json()).workspace.workspaceId, created.workspaceId)
  assert.equal(f.registrations.length, 1)
  const duplicate = await workspaceModeResponse(f.modes, request({ ...body, requestId: '22345678-1234-1234-1234-123456789abc' }))
  assert.equal(duplicate.status, 409); assert.equal((await duplicate.json()).error, 'folder-exists')
  const existing = await workspaceModeResponse(f.modes, request({ ...body, name: 'project', requestId: '32345678-1234-1234-1234-123456789abc' }))
  assert.equal(existing.status, 409); assert.deepEqual(await readdir(f.project), [])
  for (const patch of [{ pluginId: '' }, { name: '../escaped' }, { name: '..' }, { name: 'CON' }, { name: 'trailing.' }, { requestId: '../unsafe' }]) {
    assert.equal((await workspaceModeResponse(f.modes, request({ ...body, ...patch }))).status, 400)
  }
})

test('only Linux hosts can create workflow directories, regardless of transport or entry point', async t => {
  const f = await fixture(t)
  const body = { action: 'create-folder', parent: f.directory, name: 'local-workflow', pluginId: 'flow-a', requestId: '12345678-1234-1234-1234-123456789abc' }
  for (const platform of ['win32', 'darwin']) {
    f.dependencies.platform = platform
    const response = await workspaceModeResponse(f.modes, request(body))
    assert.equal(response.status, 400); assert.equal((await response.json()).error, 'workflow-linux-only')
    assert.equal((await readdir(f.directory)).includes(body.name), false)
    await assert.rejects(f.modes.prepareBeforeLaunch(f.project, 'flow-a'), { code: 'workflow-linux-only' })
    await assert.rejects(f.modes.withPreparation(f.project, 'flow-a', async () => assert.fail()), { code: 'workflow-linux-only' })
  }
  f.dependencies.platform = 'linux'
  assert.equal((await workspaceModeResponse(f.modes, request(body))).status, 200)
})

test('directory browser starts at the filesystem root and only returns child folders', async t => {
  const f = await fixture(t)
  await writeFile(join(f.directory, 'not-a-folder.txt'), 'test')
  const response = await workspaceModeResponse(f.modes, request({ action: 'browse-directory', path: f.directory }))
  const listing = await response.json()
  assert.equal(response.status, 200); assert.equal(listing.path, f.directory)
  assert.deepEqual(listing.entries.map(entry => entry.name).sort(), ['other', 'project'])
  const partial = await workspaceModeResponse(f.modes, request({ action: 'browse-directory', path: join(f.directory, 'pro'), complete: true }))
  const matches = await partial.json()
  assert.equal(matches.partial, true); assert.equal(matches.path, f.directory)
  assert.deepEqual(matches.entries.map(entry => entry.name), ['project'])
  const root = await workspaceModeResponse(f.modes, request({ action: 'browse-directory', path: '' }))
  const atRoot = await root.json()
  assert.equal(atRoot.crumbs.length, 1); assert.equal(atRoot.path, atRoot.crumbs[0].path)
})
