// ----------------------------------------------------------------------------------------------------------
// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.
// ----------------------------------------------------------------------------------------------------------

import { cp, lstat, mkdir, mkdtemp, readFile, realpath, rename, rm, writeFile } from 'node:fs/promises'
import { isAbsolute, join, relative, resolve, sep } from 'node:path'
import type { WorkflowDescriptor } from './content-types.ts'

interface Snapshot { path: string; present: boolean; slot: string }
interface Journal { workspace: string; directory: string; entries: Snapshot[]; committed?: boolean; commitToken?: string }
const transient = new Set(['EIO', 'EBUSY', 'EPERM', 'EACCES', 'ENOENT'])
async function retry<T>(action: () => Promise<T>): Promise<T> {
  for (let attempt = 0; ; attempt++) {
    try { return await action() } catch (error) {
      if (!transient.has((error as NodeJS.ErrnoException).code ?? '') || attempt === 6) throw error
      await new Promise(done => setTimeout(done, Math.min(100 * 2 ** attempt, 800)))
    }
  }
}
function inside(root: string, path: string) {
  const target = resolve(root, path), diff = relative(root, target)
  if (!diff || diff === '..' || diff.startsWith('..' + sep) || isAbsolute(diff)) throw new Error('Invalid initialization recovery path')
  return target
}
async function present(path: string) {
  try { await lstat(path); return true } catch (error) { if ((error as NodeJS.ErrnoException).code === 'ENOENT') return false; throw error }
}
async function checkParent(workspace: string, path: string) {
  let parent = resolve(path, '..')
  while (parent !== workspace && !await present(parent)) parent = resolve(parent, '..')
  if (parent !== workspace) inside(workspace, await realpath(parent))
}

/** Snapshot only installer-owned destinations; dependency repositories are never removed. */
export async function initializeTransaction(workspace: string, recoveryRoot: string, descriptor: WorkflowDescriptor, resources: string, initialize: () => Promise<void>, extraPaths: string[] = [], committed?: (token?: string) => Promise<boolean>, commitToken?: string, recoverOnly = false) {
  await mkdir(recoveryRoot, { recursive: true })
  const journalPath = join(recoveryRoot, 'recovery.json')
  async function restore(journal: Journal) {
    if (journal.workspace !== workspace || !relative(recoveryRoot, journal.directory).startsWith('snapshot-') || relative(recoveryRoot, journal.directory).includes(sep)) throw new Error('Invalid initialization recovery journal')
    for (const entry of journal.entries) {
      const destination = inside(workspace, entry.path), saved = inside(journal.directory, entry.slot)
      // Reject directory links in parent paths instead of touching another tree.
      const parent = resolve(destination, '..')
      await checkParent(workspace, destination)
      await retry(() => rm(destination, { recursive: true, force: true, maxRetries: 3, retryDelay: 100 }))
      if (entry.present) {
        await mkdir(parent, { recursive: true })
        await retry(() => cp(saved, destination, { recursive: true, dereference: false, verbatimSymlinks: true }))
      }
    }
  }
  const previous = await readFile(journalPath, 'utf8').catch(error => { if (error.code === 'ENOENT') return ''; throw error })
  if (previous) {
    const journal = JSON.parse(previous) as Journal
    if (journal.workspace !== workspace || !relative(recoveryRoot, journal.directory).startsWith('snapshot-') || relative(recoveryRoot, journal.directory).includes(sep)) throw Object.assign(new Error('Invalid initialization recovery journal'), { recoveryFailed: true })
    try { if (!journal.committed && !await committed?.(journal.commitToken)) await restore(journal) }
    catch (error) { throw Object.assign(error as Error, { recoveryFailed: true }) }
    await rm(journalPath)
    await rm(journal.directory, { recursive: true, force: true, maxRetries: 3, retryDelay: 100 }).catch(() => {})
  }
  if (recoverOnly) return
  const paths = new Set(descriptor.skills.map(skill => `.dsh/skills/${skill.name}`))
  for (const path of extraPaths) paths.add(path)
  paths.add(`.cannbot/plugins/${descriptor.id}`)
  for (const file of ['AGENTS.md', 'CLAUDE.md', '.dsh/cannbot-plugin.json', '.cannbot/settings.json', '.cannbot/permissions']) paths.add(file)
  const manifestPath = join(resources, '.claude-plugin/plugin.json')
  if (await present(manifestPath)) {
    const manifest = JSON.parse(await readFile(manifestPath, 'utf8'))
    for (const path of manifest.agents ?? []) {
      const text = await readFile(inside(resources, path), 'utf8')
      const name = /^name:\s*([^\r\n]+)$/m.exec(text)?.[1]?.trim()
      if (!name || !/^[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*$/.test(name)) throw new Error('Invalid initializer agent name')
      paths.add(`.dsh/agents/${name}.md`)
    }
  }
  const directory = await mkdtemp(join(recoveryRoot, 'snapshot-'))
  const journal: Journal = { workspace, directory, entries: [], ...(commitToken && { commitToken }) }
  for (const path of paths) {
    const source = inside(workspace, path)
    await checkParent(workspace, source)
    const exists = await present(source), slot = String(journal.entries.length)
    if (exists) await retry(() => cp(source, join(directory, slot), { recursive: true, dereference: false, verbatimSymlinks: true }))
    journal.entries.push({ path, present: exists, slot })
  }
  const temporary = journalPath + '.tmp'
  await writeFile(temporary, JSON.stringify(journal), { mode: 0o600 })
  await rename(temporary, journalPath)
  try {
    await initialize()
  } catch (error) {
    try { await restore(journal); await rm(journalPath) }
    catch (recovery) { throw Object.assign(new Error(`${(error as Error).message}\n自动恢复未完成，备份保留在 ${directory}：${(recovery as Error).message}`), { recoveryFailed: true }) }
    await rm(directory, { recursive: true, force: true, maxRetries: 3, retryDelay: 100 }).catch(() => {})
    throw new Error(`${(error as Error).message}\n已恢复本次初始化前的 Skills 和工作区配置。`)
  }
  // Keep a completed journal if cleanup fails; never roll back a committed binding.
  journal.committed = true
  try { await writeFile(temporary, JSON.stringify(journal), { mode: 0o600 }); await rename(temporary, journalPath); await rm(journalPath) }
  catch (error) { if (!committed) throw error; return }
  // A cleanup failure must not turn a successful installation into a failed one.
  await rm(directory, { recursive: true, force: true, maxRetries: 3, retryDelay: 100 }).catch(() => {})
}

/** Recover before reading the old workflow's registry to plan its retirement. */
export async function recoverInitialization(workspace: string, recoveryRoot: string, committed?: (token?: string) => Promise<boolean>) {
  const descriptor: WorkflowDescriptor = { schemaVersion: 1, id: 'recovery', title: '', version: '0.0.0', skills: [], initialization: { kind: 'skill-native' }, source: { repository: '', commit: '', skillsCommit: '' } }
  await initializeTransaction(workspace, recoveryRoot, descriptor, recoveryRoot, async () => {}, [], committed, undefined, true)
}
