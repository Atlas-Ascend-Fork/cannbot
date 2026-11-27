// ----------------------------------------------------------------------------------------------------------
// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.
// ----------------------------------------------------------------------------------------------------------

import type { Context } from '@deepseek-ai/cordis'
import type {} from '@deepseek-ai/dsh-app-boot'
import type {} from '@deepseek-ai/dsh-client-connection'
import type {} from '@deepseek-ai/dsh-plugin-manager'
import { randomUUID } from 'node:crypto'
import { readFile, writeFile, mkdir, rename, rm, mkdtemp, copyFile } from 'node:fs/promises'
import { join, resolve } from 'node:path'
import { homedir } from 'node:os'
import releaseSource from '../../installers/common/release-source.json' with { type: 'json' }
// @ts-ignore Shared installer release reader is distributed as ESM.
import { compareVersions, parseManifest, requireCompatible, getBytes } from '../../installers/common/release.mjs'
import { withContentLock } from './content-lock.ts'

export const UPDATE_PATH = '/api/cannbot-dsh/update'
const clientPackage = '@cannbot-plugin/cannbot-dsh'
type Manifest = { version: string; buildId: string; dshRange: string; packages: { client: { url: string } }; legal: { version: string } }
type Receipt = { schemaVersion: number; version: string; buildId: string; edition: string; legalVersion: string; acceptedAt: string }
type Current = { version: string; buildId: string; hostVersion: string; receipt?: Receipt }
type Release = { manifest: Manifest }
type Status = 'unconfigured' | 'available' | 'latest' | 'error' | 'incompatible' | 'agreement-required' | 'manual'
interface Change { application: string; error?: { code: string } }
type Profile = { dir: string; installAnchor: string }
const json = async (file: string) => JSON.parse((await readFile(file, 'utf8')).replace(/^\uFEFF/, ''))

export async function installedClient(profile: Profile): Promise<Current> {
  const installed = await json(join(profile.dir, 'node_modules', ...clientPackage.split('/'), 'package.json'))
  const host = await json(profile.installAnchor)
  if (installed.name !== clientPackage || installed.cannbotEdition !== 'client' || !installed.cannbotBuildId) throw new Error('Client installation identity is unavailable')
  let receipt
  try { receipt = await json(join(profile.dir, '.cannbot-install.json')) } catch (error) { if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error }
  return { version: installed.version, buildId: installed.cannbotBuildId, hostVersion: host.version, receipt }
}

export function updateStatus({ version, buildId, hostVersion, receipt }: Current, manifest: Manifest): Status {
  const direction = compareVersions(manifest.version, version)
  if (direction < 0) return 'latest'
  if (direction === 0) return manifest.buildId === buildId ? 'latest' : 'error'
  if (manifest.buildId === buildId) return 'error'
  try { requireCompatible(manifest.dshRange, hostVersion) } catch { return 'incompatible' }
  if (receipt?.schemaVersion !== 1 || receipt.edition !== 'client' || receipt.version !== version || receipt.buildId !== buildId || !Number.isFinite(Date.parse(receipt.acceptedAt)) ||
      receipt.legalVersion !== manifest.legal.version) return 'agreement-required'
  return 'available'
}

async function latestRelease(): Promise<Release | undefined> {
  if (!releaseSource.manifestUrl) return
  return { manifest: parseManifest(await getBytes(releaseSource.manifestUrl, 256 * 1024)) }
}

interface Dependencies {
  current(): Promise<Current>
  release(): Promise<Release | undefined>
  activate(release: Release, current: Current): Promise<Change>
}
export function createHostUpdater(deps: Dependencies) {
  return async (target?: { version: string; buildId: string }) => {
    const installed = await deps.current()
    const base = { current: installed.version, buildId: installed.buildId }
    const release = await deps.release()
    if (!release) return { ...base, status: 'unconfigured' }
    const { manifest } = release
    const info = { ...base, version: manifest.version, targetBuildId: manifest.buildId }
    if (target && (target.version !== manifest.version || target.buildId !== manifest.buildId)) return { ...info, status: 'stale' }
    const status = updateStatus(installed, manifest)
    if (!target || status !== 'available') return { ...info, status }
    const change = await deps.activate(release, installed)
    if (change.application === 'applied' && !change.error) return { ...info, status: 'done' }
    if (change.application === 'restart-required' && !change.error) return { ...info, status: 'restart' }
    return { ...info, status: ['already-installed', 'stop-profile', 'not-removable'].includes(change.error?.code || '') ? 'manual' : 'error' }
  }
}

async function rollbackArchive(profile: Profile, directory: string, stage: string, receipt: Receipt): Promise<string | undefined> {
  const declared = (await json(join(profile.dir, 'package.json'))).dependencies?.[clientPackage]
  if (!/^[a-z0-9][a-z0-9._-]{0,127}$/i.test(receipt.buildId)) return
  const archives = [
    join(directory, receipt.buildId, 'client.tgz'),
    join(profile.dir, '.cannbot-workbench', receipt.buildId, 'source.tgz'),
    join(homedir(), '.local/share/cannbot/releases', receipt.buildId, 'client.tgz'),
  ]
  if (typeof declared === 'string' && declared.startsWith('file:') && declared.endsWith('.tgz')) archives.unshift(resolve(profile.dir, declared.slice(5)))
  for (const original of archives) {
    // Keep a copy while DSH changes dependencies. Only a failed activation
    // needs the copy to survive this transaction at a distinct file: location.
    const archive = join(stage, 'previous.tgz')
    try { await copyFile(original, archive) } catch (error) { if ((error as NodeJS.ErrnoException).code === 'ENOENT') continue; throw error }
    return archive
  }
}

export async function activateClient(profile: Profile, release: Release, installed: Current, install: (spec: string) => Promise<Change>, download = getBytes): Promise<Change> {
  const { manifest } = release
  const target = manifest.packages.client
  const directory = join(profile.dir, '.cannbot-releases')
  await mkdir(directory, { recursive: true, mode: 0o700 })
  const stage = await mkdtemp(join(directory, '.new-'))
  const matches = async (expected: { version: string; buildId: string }) => {
    try {
      const actual = await installedClient(profile)
      const active = await json(join(profile.dir, 'package.json'))
      return actual.version === expected.version && actual.buildId === expected.buildId && active.dsh?.profile?.bundles?.includes(clientPackage)
    } catch { return false }
  }
  try {
    const releaseDirectory = join(directory, manifest.buildId)
    await mkdir(releaseDirectory, { recursive: true, mode: 0o700 })
    const archive = join(releaseDirectory, 'client.tgz')
    const staged = join(stage, 'client.tgz')
    await writeFile(staged, await download(target.url, 256 * 1024 * 1024), { mode: 0o600, flag: 'wx' })
    const previous = installed.receipt && await rollbackArchive(profile, directory, stage, installed.receipt)
    if (!previous) return { application: 'failed', error: { code: 'stop-profile' } }
    await rename(staged, archive)
    const receipt = { ...installed.receipt, version: manifest.version, buildId: manifest.buildId }
    const pending = join(stage, 'receipt-' + randomUUID())
    await writeFile(pending, JSON.stringify(receipt, null, 2) + '\n', { mode: 0o600, flag: 'wx' })
    const failed: Change = { application: 'failed', error: { code: 'activation-failed' } }
    let change: Change
    try {
      change = await install('file:' + archive)
      if (!change.error && ['applied', 'restart-required'].includes(change.application)) {
        if (!await matches(manifest)) throw new Error('Client activation incomplete')
        await rename(pending, join(profile.dir, '.cannbot-install.json'))
        return change
      }
    } catch { change = failed }
    if (!await matches(installed)) {
      const recovery = join(directory, 'restore-' + randomUUID() + '.tgz')
      await rename(previous, recovery)
      try { await install('file:' + recovery) } catch { /* check actual profile state */ }
      if (!await matches(installed)) return { application: 'failed', error: { code: 'stop-profile' } }
    }
    return change
  } finally { await rm(stage, { recursive: true, force: true }) }
}

export function registerHostUpdater(ctx: Context) {
  ctx.inject(['connection', 'pluginManager', 'profileContext'], scoped => {
    if (typeof scoped.connection.fetch?.register !== 'function') return
    const profile = scoped.profileContext, manager = scoped.pluginManager
    const update = createHostUpdater({
      current: () => installedClient(profile), release: latestRelease,
      activate: (release, installed) => activateClient(profile, release, installed, spec => manager.installBundle(spec, { saveExact: true, enabled: true })),
    })
    scoped.connection.fetch.register({
      path: UPDATE_PATH, methods: ['GET', 'POST'], requestBody: 'buffered',
      async fetch(request) {
        const headers = { 'cache-control': 'no-store' }
        try {
          if (request.method === 'GET') return Response.json(await update(), { headers })
          const target = await request.json() as { version?: unknown; buildId?: unknown }
          if (!target || typeof target.version !== 'string' || typeof target.buildId !== 'string') return Response.json({ status: 'error' }, { status: 400, headers })
          const expected = { version: target.version, buildId: target.buildId }
          return Response.json(await withContentLock(join(profile.dir, '.cannbot-update.lock'), () => update(expected)), { headers })
        } catch { return Response.json({ status: 'error' }, { status: 500, headers }) }
      },
    })
  })
}
