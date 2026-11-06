// ----------------------------------------------------------------------------------------------------------
// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.
// ----------------------------------------------------------------------------------------------------------

import { runProcess } from './process-runner.mjs'
import { createHash, randomUUID } from 'node:crypto'
import { existsSync, readFileSync, realpathSync, statSync } from 'node:fs'
import { cp, mkdir, mkdtemp, readFile, realpath, rename, rm, writeFile } from 'node:fs/promises'
import { homedir } from 'node:os'
import { dirname, isAbsolute, join, relative, resolve, sep } from 'node:path'
import { withContentLock } from './content-lock.ts'
import { initializeTransaction } from './initializer-transaction.ts'
import { newerVersion } from './client/plugin-update.ts'
import { CATALOG_PACKAGE, WORKFLOW_SCOPE, REGISTRY, MIRROR, npmFetcher, validateTarball, validId, validVersion, type NpmFetcher, type PackageManifest } from './npm-workflows.ts'
import type { ContentCatalog, ContentPlugin, ContentSkill, ContentStatus, WorkflowDescriptor, WorkflowEntry, WorkflowRow } from './content-types.ts'

interface Installed { id: string; package: string; version: string; integrity: string; directory: string; installedAt: string; dependency?: boolean }
interface Index { schemaVersion: 1; catalogVersion?: string; entries: WorkflowEntry[]; records: Record<string, Installed>; history: Record<string, Installed[]>; pinned: string[] }
function inside(root: string, path: string) {
  const value = resolve(root, path), diff = relative(resolve(root), value)
  if (diff === '..' || diff.startsWith(`..${sep}`) || isAbsolute(diff)) throw new Error('Workflow resource escapes its package')
  return value
}
function checkedEntry(value: unknown): WorkflowEntry {
  const item = value as WorkflowEntry
  if (!item || typeof item.id !== 'string' || !validId(item.id) || item.package !== WORKFLOW_SCOPE + item.id || typeof item.title !== 'string' || item.title.length > 200 || typeof item.default !== 'boolean') throw new Error('Invalid workflow catalog entry')
  return item
}

/** npm installs the baseline; a private cache supports independent updates and rollback. */
export class ContentManager {
  readonly root: string
  private index: Index
  private catalog: ContentCatalog = { plugins: [], exposedSkills: [] }
  private latest = new Map<string, PackageManifest>()
  private errors = new Map<string, string>()
  private descriptors = new Map<string, WorkflowDescriptor>()
  private pending?: Promise<void>
  private pendingKey?: string
  private jobs = new Map<string, Promise<void>>()
  private listeners = new Set<() => void>()
  private stamp = ''
  private fetcher: NpmFetcher
  private registry = REGISTRY
  /** Workflows declared by the shipped defaults; registry catalogs may not reintroduce others. */
  private shipped: Set<string>
  private state: Pick<ContentStatus, 'phase' | 'message' | 'log'> = { phase: 'idle', message: '', log: '' }
  constructor(defaults: string, root = process.env.CANNBOT_DSH_WORKFLOW_ROOT ?? join(process.env.DSH_HOME ?? join(homedir(), '.dsh'), 'cannbot-dsh-workflows'), fetcher: NpmFetcher = npmFetcher()) {
    this.fetcher = fetcher
    this.root = resolve(root)
    const entries = JSON.parse(readFileSync(defaults, 'utf8')).workflows.map(checkedEntry)
    this.shipped = new Set(entries.map(item => item.id))
    this.index = { schemaVersion: 1, entries, records: {}, history: {}, pinned: [] }
    try { this.reload() } catch { /* Invalid cache never becomes active. */ }
  }
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener) } }
  private publish(patch: Partial<typeof this.state>) { this.state = { ...this.state, ...patch }; for (const listener of this.listeners) listener() }
  private options() { return { registry: this.registry, cache: join(this.root, 'npm-cache'), ignoreScripts: true, fullMetadata: true, preferOnline: true, fetchRetries: 0, fetchTimeout: 15000 } }
  private async manifest(spec: string) {
    let last: unknown
    for (const registry of [this.registry, this.registry === REGISTRY ? MIRROR : REGISTRY]) {
      try { const value = await this.fetcher.manifest(spec, { ...this.options(), registry }); this.registry = registry; return value }
      catch (error) { last = error }
    }
    throw last
  }
  private async extract(manifest: PackageManifest, directory: string) {
    const options = { ...this.options(), integrity: manifest.dist.integrity, fetchTimeout: 180000, fetchRetries: 1 }
    try { await this.fetcher.extract(manifest.dist.tarball, directory, options); return directory }
    catch (error) {
      await rm(directory, { recursive: true, force: true }).catch(() => {})
      if (String((error as Error).message).includes('EINTEGRITY') || (error as { code?: string }).code === 'EINTEGRITY') throw error
      const registry = new URL(manifest.dist.tarball).hostname === 'registry.npmjs.org' ? MIRROR : REGISTRY
      const alternative = await this.fetcher.manifest(`${manifest.name}@${manifest.version}`, { ...this.options(), registry })
      validateTarball(alternative)
      if (alternative.name !== manifest.name || alternative.version !== manifest.version || alternative.dist.integrity !== manifest.dist.integrity) throw new Error('Registry mirror disagrees with the selected package integrity')
      const fresh = await mkdtemp(join(dirname(directory), `${manifest.version}-mirror-`))
      try { await this.fetcher.extract(alternative.dist.tarball, fresh, options); return fresh }
      catch (error) { await rm(fresh, { recursive: true, force: true }).catch(() => {}); throw error }
    }
  }
  private descriptor(record: Installed): WorkflowDescriptor {
    const entry = this.index.entries.find(item => item.id === record.id)
    if (!entry || record.package !== entry.package || !validVersion(record.version)) throw new Error('Invalid installed workflow identity')
    const root = inside(this.root, record.directory), manifest = JSON.parse(readFileSync(join(root, 'package.json'), 'utf8')) as PackageManifest
    const data = JSON.parse(readFileSync(join(root, 'workflow.json'), 'utf8')) as WorkflowDescriptor
    if (manifest.name !== entry.package || manifest.version !== record.version || manifest.cannbotWorkflow?.schemaVersion !== 1 || manifest.cannbotWorkflow.id !== entry.id
      || data.schemaVersion !== 1 || data.id !== entry.id || data.version !== record.version || typeof data.title !== 'string' || !Array.isArray(data.skills) || !data.skills.length) throw new Error('Incompatible workflow package')
    if (Object.keys(manifest.dependencies ?? {}).length || Object.keys(manifest.optionalDependencies ?? {}).length || Object.keys(manifest.scripts ?? {}).length) throw new Error('Workflow packages must contain their own resources and no npm lifecycle scripts')
    const check = (path: string) => {
      const value = inside(root, path)
      inside(realpathSync(root), realpathSync(value))
      return value
    }
    const names = new Set<string>()
    for (const skill of data.skills) {
      if (!validId(skill.name) || names.has(skill.name) || !/^[a-f0-9]{64}$/.test(skill.hash) || !statSync(check(join('resources', skill.path))).isFile()) throw new Error('Invalid packaged Skill')
      names.add(skill.name)
    }
    if (!data.skills.some(item => item.name === entry.id && item.entry)) throw new Error('Workflow entry Skill is missing')
    if (data.initialization?.kind === 'cannbot-cli') check(data.initialization.entry)
    else if (data.initialization?.kind !== 'skill-native') throw new Error('Unsupported workflow initializer')
    return data
  }
  private compose() {
    const plugins: ContentPlugin[] = [], exposedSkills: ContentSkill[] = [], winners = new Map<string, { hash: string; name: string }>()
    this.descriptors.clear()
    for (const entry of this.index.entries) {
      const record = this.index.records[entry.id]
      if (!record) continue
      const data = this.descriptor(record), aliases: Record<string, string> = {}
      this.descriptors.set(entry.id, data)
      const resources = join(record.directory, 'resources')
      for (const skill of data.skills) {
        const previous = winners.get(skill.name)
        const name = !previous || previous.hash === skill.hash ? previous?.name ?? skill.name : `${entry.id}-${skill.name}`
        if (name !== skill.name) aliases[skill.name] = name
        if (previous?.hash === skill.hash) continue
        if (exposedSkills.some(item => item.name === name)) throw new Error('Conflicting workflow Skill aliases')
        if (!previous) winners.set(skill.name, { hash: skill.hash, name })
        exposedSkills.push({ name, originalName: skill.name, pluginId: entry.id, path: join(resources, skill.path), entry: skill.entry })
      }
      plugins.push({ id: entry.id, title: data.title, aliases, version: record.version, packageName: record.package, resourceDirectory: resources })
    }
    const revision = createHash('sha256').update(JSON.stringify(this.index.entries.map(item => [item.id, this.index.records[item.id]?.version, this.index.records[item.id]?.integrity]))).digest('hex')
    this.catalog = { revision, plugins, exposedSkills }
  }
  private reload() {
    const file = join(this.root, 'active.json'), stat = statSync(file), stamp = `${stat.mtimeMs}:${stat.size}`
    if (stamp === this.stamp) return
    const previous = this.index, parsed = JSON.parse(readFileSync(file, 'utf8')) as Index
    if (parsed.schemaVersion !== 1 || !Array.isArray(parsed.entries) || !parsed.records || !parsed.history || !Array.isArray(parsed.pinned)) throw new Error('Invalid workflow index')
    parsed.entries.forEach(checkedEntry)
    this.index = parsed
    try { this.compose(); this.stamp = stamp } catch (error) { this.index = previous; this.compose(); throw error }
  }
  private refresh() {
    const before = this.catalog.revision
    try { this.reload() } catch { /* Keep the last valid in-memory snapshot. */ }
    if (before !== this.catalog.revision) this.publish({})
  }
  getSource() { this.refresh(); return { assets: this.root, catalog: this.catalog, revision: this.catalog.revision ?? 'empty' } }
  getStatus = (): ContentStatus => {
    this.refresh()
    const workflows: WorkflowRow[] = this.index.entries.map(entry => {
      const current = this.index.records[entry.id]
      const previous = (this.index.history[entry.id] ?? []).find(item => current && newerVersion(current.version, item.version))
      return { ...entry, installed: !!current, version: current?.version, latest: this.latest.get(entry.id)?.version, previous: previous?.version, pinned: this.index.pinned.includes(entry.id), error: this.errors.get(entry.id) }
    })
    return { ...this.state, plugins: this.catalog.plugins, workflows, fallback: !this.catalog.plugins.length, busy: !!this.pending || !!this.jobs.size, catalogVersion: this.index.catalogVersion }
  }
  private async save(next: Index) {
    const previous = this.index
    this.index = next
    try { this.compose() } finally { this.index = previous; this.compose() }
    await mkdir(this.root, { recursive: true })
    const temporary = join(this.root, `active-${randomUUID()}.json`)
    try { await writeFile(temporary, JSON.stringify(next), { mode: 0o600 }); await rename(temporary, join(this.root, 'active.json')); this.stamp = '' ; this.reload() }
    catch (error) { this.index = previous; this.compose(); throw error }
    this.publish({})
  }
  private operation(key: string, action: () => Promise<void>): Promise<void> {
    if (this.pending) return this.pendingKey === key ? this.pending : this.pending.catch(() => {}).then(() => this.operation(key, action))
    this.pendingKey = key
    this.pending = withContentLock(join(this.root, 'operations.lock'), async () => { this.refresh(); await action() })
      .catch(error => { this.publish({ phase: 'error', message: String(error.message).slice(-1500) }); throw error })
      .finally(() => { this.pending = undefined; this.pendingKey = undefined; this.publish({}) })
    return this.pending
  }
  installDependencies(catalogFile: string, resolvePackage: (name: string) => string, replaceFromSource = false) {
    return this.operation('dependencies', async () => {
      const catalog = JSON.parse(await readFile(catalogFile, 'utf8')) as PackageManifest
      if (catalog.name !== CATALOG_PACKAGE || !validVersion(catalog.version) || catalog.cannbotWorkflowCatalog?.schemaVersion !== 1 || !Array.isArray(catalog.cannbotWorkflowCatalog.workflows)) throw new Error('Invalid installed workflow catalog')
      const baseline = catalog.cannbotWorkflowCatalog.workflows.map(checkedEntry).filter(item => this.shipped.has(item.id))
      if (!baseline.length || new Set(baseline.map(item => item.id)).size !== baseline.length) throw new Error('Invalid installed workflow entries')
      const newerCatalog = !replaceFromSource && this.index.catalogVersion && newerVersion(this.index.catalogVersion, catalog.version)
      // Entries left by earlier releases are dropped unless this build still ships them.
      const entries = (newerCatalog ? [...this.index.entries] : [...baseline]).filter(item => this.shipped.has(item.id))
      for (const old of this.index.entries) if (this.shipped.has(old.id) && !entries.some(item => item.id === old.id)) entries.push(old)
      const next = { ...this.index, entries, catalogVersion: newerCatalog ? this.index.catalogVersion : catalog.version, records: { ...this.index.records }, history: { ...this.index.history }, pinned: [...this.index.pinned] }
      const dropped = Object.keys(next.records).filter(id => !this.shipped.has(id))
      for (const id of dropped) delete next.records[id]
      for (const id of Object.keys(next.history)) if (!this.shipped.has(id)) delete next.history[id]
      next.pinned = next.pinned.filter(id => this.shipped.has(id))
      for (const entry of baseline.filter(item => item.default)) {
        if (!replaceFromSource && this.index.records[entry.id]) continue // Preserve independent npm updates and pinned rollbacks.
        if (!catalog.dependencies?.[entry.package]) throw new Error(`Workflow dependency missing: ${entry.package}`)
        const packageFile = resolvePackage(entry.package)
        const manifest = JSON.parse(await readFile(packageFile, 'utf8')) as PackageManifest
        if (manifest.name !== entry.package || !validVersion(manifest.version)) throw new Error('Incorrect installed workflow dependency')
        const identity = (replaceFromSource ? 'source:' : 'dependency:') + createHash('sha512').update(await readFile(join(dirname(packageFile), 'workflow.json'))).digest('base64')
        if (replaceFromSource && this.index.records[entry.id]?.integrity === identity) continue
        const parent = join(this.root, 'packages', entry.id)
        await mkdir(parent, { recursive: true })
        const directory = await mkdtemp(join(parent, `${manifest.version}-dependency-`))
        await cp(dirname(packageFile), directory, { recursive: true, dereference: true })
        // Source builds and npm dependencies have distinct content identities;
        // neither is represented as a registry tarball SRI.
        const integrity = identity
        const record: Installed = { id: entry.id, package: entry.package, version: manifest.version, integrity, directory: relative(this.root, directory).split(sep).join('/'), installedAt: new Date().toISOString(), dependency: true }
        // Validate against the incoming catalog without exposing a partial installation.
        const previous = this.index
        try { this.index = next; this.descriptor(record) } finally { this.index = previous }
        next.records[entry.id] = record
        if (replaceFromSource) next.pinned = next.pinned.filter(id => id !== entry.id)
      }
      await this.save(next)
      // Drop the copies only after the saved index stops referencing them.
      for (const id of dropped) await rm(join(this.root, 'packages', id), { recursive: true, force: true }).catch(() => {})
      this.publish({ phase: 'ready', message: 'Installed workflow dependencies are ready.' })
    })
  }
  private async checkPackages() {
    this.registry = REGISTRY
    this.publish({ phase: 'syncing', message: 'Checking npm workflow packages…', log: '' })
    const catalog = await this.manifest(`${CATALOG_PACKAGE}@latest`)
    if (catalog.name !== CATALOG_PACKAGE || !validVersion(catalog.version) || catalog.cannbotWorkflowCatalog?.schemaVersion !== 1 || !Array.isArray(catalog.cannbotWorkflowCatalog.workflows)) throw new Error('Unsupported workflow catalog')
    const entries = catalog.cannbotWorkflowCatalog.workflows.map(checkedEntry).filter(item => this.shipped.has(item.id))
    if (!entries.length || new Set(entries.map(item => item.id)).size !== entries.length) throw new Error('Invalid workflow catalog')
    // Catalog removal does not silently uninstall a user's existing workflow, unless this build no longer ships it.
    for (const old of this.index.entries) if (this.shipped.has(old.id) && this.index.records[old.id] && !entries.some(item => item.id === old.id)) entries.push(old)
    await this.save({ ...this.index, entries, catalogVersion: catalog.version })
    this.errors.clear()
    for (const entry of entries) {
      try {
        const manifest = await this.manifest(`${entry.package}@latest`)
        this.validateManifest(entry, manifest)
        this.latest.set(entry.id, manifest)
      } catch (error) { this.latest.delete(entry.id); this.errors.set(entry.id, String((error as Error).message).slice(-300)) }
    }
    this.publish({ phase: 'ready', message: 'Workflow versions checked.' })
  }
  private validateManifest(entry: WorkflowEntry, manifest: PackageManifest) {
    if (manifest.name !== entry.package || manifest.cannbotWorkflow?.id !== entry.id || manifest.cannbotWorkflow.schemaVersion !== 1) throw new Error('Unsupported workflow package format')
    validateTarball(manifest)
  }
  check() { return this.operation('check', () => this.checkPackages()) }
  sync(id?: string, version?: string): Promise<void> {
    if (version !== undefined && !validVersion(version)) return Promise.reject(new Error('Invalid workflow version'))
    return this.operation(`update:${id ?? '*'}:${version ?? 'latest'}`, async () => {
      await this.checkPackages()
      const entries = id ? this.index.entries.filter(item => item.id === id) : this.index.entries.filter(item => (item.default || this.index.records[item.id]) && !this.index.pinned.includes(item.id))
      if (id && !entries.length) throw new Error('Unknown workflow')
      const failures: string[] = []
      for (const entry of entries) {
        try {
          const manifest = version ? await this.manifest(`${entry.package}@${version}`) : this.latest.get(entry.id)
          if (!manifest) throw new Error(this.errors.get(entry.id) ?? 'Workflow package unavailable')
          this.validateManifest(entry, manifest)
          const previous = this.index.records[entry.id]
          if (previous?.version === manifest.version) {
            if (!previous.dependency && previous.integrity !== manifest.dist.integrity) throw new Error('A published workflow version changed integrity')
            continue
          }
          if (previous && !newerVersion(manifest.version, previous.version)) continue
          this.publish({ phase: 'syncing', message: `Installing ${entry.id}@${manifest.version}…`, log: '' })
          const parent = join(this.root, 'packages', entry.id)
          await mkdir(parent, { recursive: true })
          let directory = await mkdtemp(join(parent, `${manifest.version}-`))
          let committed = false
          try {
            directory = await this.extract(manifest, directory)
            const record: Installed = { id: entry.id, package: entry.package, version: manifest.version, integrity: manifest.dist.integrity, directory: relative(this.root, directory).split(sep).join('/'), installedAt: new Date().toISOString() }
            this.descriptor(record)
            const history = { ...this.index.history }
            if (previous) history[entry.id] = [previous, ...(history[entry.id] ?? []).filter(item => item.version !== previous.version)]
            await this.save({ ...this.index, records: { ...this.index.records, [entry.id]: record }, history, pinned: this.index.pinned.filter(item => item !== entry.id) })
            committed = true
          } finally {
            if (!committed) {
              // save() may fail after publishing active.json (e.g. a subscriber
              // throws). Never delete a directory already committed to disk.
              let retained = true
              try {
                const active = JSON.parse(await readFile(join(this.root, 'active.json'), 'utf8')) as Index
                retained = Object.values(active.records).some(record => inside(this.root, record.directory) === directory)
              } catch (error) { if ((error as NodeJS.ErrnoException).code === 'ENOENT') retained = false }
              if (!retained) await rm(directory, { recursive: true, force: true }).catch(() => {})
            }
          }
          this.errors.delete(entry.id)
        } catch (error) { const message = String((error as Error).message).slice(-500); this.errors.set(entry.id, message); failures.push(`${entry.id}: ${message}`) }
      }
      if (failures.length) throw new Error(failures.join('\n'))
      this.publish({ phase: 'ready', message: 'Workflow packages are ready.' })
    })
  }
  rollback(id: string) {
    return this.operation(`rollback:${id}`, async () => {
      const current = this.index.records[id], previous = (this.index.history[id] ?? []).find(item => current && newerVersion(current.version, item.version))
      if (!current || !previous) throw new Error('No earlier workflow version is available')
      this.descriptor(previous)
      await this.save({ ...this.index, records: { ...this.index.records, [id]: previous }, pinned: [...new Set([...this.index.pinned, id])] })
      this.publish({ phase: 'ready', message: `${id} restored to ${previous.version} and pinned.` })
    })
  }
  private async runInitializer(entry: string, args: string[], cwd: string) {
    let output = ''
    try {
      await runProcess(process.execPath, [entry, ...args], {
        cwd, stdio: ['ignore', 'pipe', 'pipe'], timeoutMs: 20 * 60000,
        env: { ...process.env, ...(process.versions.electron ? { ELECTRON_RUN_AS_NODE: '1' } : {}), GIT_TERMINAL_PROMPT: '0', GCM_INTERACTIVE: 'never' },
        onData: (data: Buffer) => { output = (output + data).slice(-16000); this.publish({ log: output.slice(-6000) }) },
      })
    } catch (error) { throw new Error(`${(error as Error).message}\n${output.slice(-1500)}`) }
  }

  async prepare(cwd: string, id: string): Promise<void> {
    if (!validId(id)) throw new Error('Invalid workflow')
    this.refresh()
    if (!this.index.records[id]) { if (this.pending) await this.pending.catch(() => {}); if (!this.index.records[id]) await this.sync(id) }
    const record = this.index.records[id]
    if (!record) throw new Error('Workflow package is not installed')
    const descriptor = this.descriptor(record), workspace = await realpath(cwd)
    const key = createHash('sha256').update(workspace).digest('hex'), receipt = JSON.stringify({ workspace, id, package: record.package, version: record.version, integrity: record.integrity })
    const marker = join(this.root, 'initialized', key, `${id}.json`), jobKey = `${key}:${id}:${record.version}:${record.integrity}`
    let job = this.jobs.get(jobKey)
    if (!job) {
      job = withContentLock(join(this.root, 'initialized', key, 'workspace.lock'), async () => {
        const recoveryRoot = join(this.root, 'initialized', key, 'recovery')
        const skillsPresent = descriptor.skills.every(skill => existsSync(join(workspace, '.dsh/skills', skill.name, 'SKILL.md')))
        if (await readFile(marker, 'utf8').catch(() => '') === receipt && !existsSync(join(recoveryRoot, 'recovery.json')) && (descriptor.initialization.kind !== 'cannbot-cli' || skillsPresent)) return
        this.publish({ phase: 'initializing', message: `Preparing ${id}@${record.version} for this workspace…`, log: '' })
        if (descriptor.initialization.kind === 'cannbot-cli') {
          const root = inside(this.root, record.directory)
          const entry = inside(root, descriptor.initialization.entry)
          await initializeTransaction(workspace, recoveryRoot, descriptor, join(root, 'resources'), () => this.runInitializer(entry, ['install', id, '--tool', 'dsh', '--target', workspace, '--plugin-dir', join(root, 'resources')], workspace))
        }
        await writeFile(marker, receipt, { mode: 0o600 })
        this.publish({ phase: 'ready', message: `${id} is ready for this workspace.` })
      }).catch(error => { this.publish({ phase: 'error', message: String(error.message).slice(-1500) }); throw error }).finally(() => { this.jobs.delete(jobKey); this.publish({}) })
      this.jobs.set(jobKey, job)
    }
    await job
    this.refresh()
    const current = this.index.records[id]
    if (current.version !== record.version || current.integrity !== record.integrity) await this.prepare(cwd, id)
  }
}
