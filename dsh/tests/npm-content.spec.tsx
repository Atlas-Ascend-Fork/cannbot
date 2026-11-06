// ----------------------------------------------------------------------------------------------------------
// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.
// ----------------------------------------------------------------------------------------------------------

// @vitest-environment node
import { expect, it } from 'vitest'
import { cpSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, writeFileSync } from 'node:fs'
import { resolve, join } from 'node:path'
import { createHash } from 'node:crypto'
import { ContentManager, withContentLock } from '../src/content-manager.ts'
import { CATALOG_PACKAGE, WORKFLOW_SCOPE, REGISTRY, MIRROR, type NpmFetcher, type PackageManifest } from '../src/npm-workflows.ts'
function fixture() {
  mkdirSync('.acceptance-workflow-tests', { recursive: true })
  const root = mkdtempSync(resolve('.acceptance-workflow-tests/npm-')), workspace = join(root, 'workspace')
  mkdirSync(workspace)
  const entries = ['flow-a', 'flow-b'].map(id => ({ id, title: id, package: WORKFLOW_SCOPE + id, default: true }))
  const defaults = join(root, 'defaults.json'); writeFileSync(defaults, JSON.stringify({ workflows: entries }))
  const latest = new Map<string, string>(), packages = new Map<string, { manifest: PackageManifest; directory: string }>()
  const extracted: string[] = []
  let bad = '', offline = false, catalogVersion = '1.0.0'
  function add(id: string, version: string) {
    const directory = join(root, 'fixtures', id, version), resource = join(directory, 'resources/skills', id)
    mkdirSync(resource, { recursive: true })
    writeFileSync(join(resource, 'SKILL.md'), `---\nname: ${id}\ndescription: ${id}\n---\n${version}\n`)
    const manifest: PackageManifest = { name: WORKFLOW_SCOPE + id, version, dist: { integrity: 'sha512-' + Buffer.from(id + version).toString('base64'), tarball: `https://registry.npmjs.org/${WORKFLOW_SCOPE + id}/-/${id}-${version}.tgz` }, cannbotWorkflow: { schemaVersion: 1, id } }
    writeFileSync(join(directory, 'package.json'), JSON.stringify({ ...manifest, type: 'module' }))
    writeFileSync(join(directory, 'workflow.json'), JSON.stringify({ schemaVersion: 1, id, title: id, version,
      initialization: { kind: 'cannbot-cli', entry: 'init.mjs' }, source: { repository: 'https://gitcode.com/cann/cannbot.git', commit: 'a'.repeat(40), skillsCommit: 'b'.repeat(40) },
      skills: [{ name: id, path: `skills/${id}/SKILL.md`, entry: true, hash: createHash('sha256').update(id + version).digest('hex') }] }))
    writeFileSync(join(directory, 'init.mjs'), `import fs from 'node:fs';import p from 'node:path';const a=process.argv.slice(2);if(a[0]!=='install'||a[a.indexOf('--tool')+1]!=='dsh'||a.includes('--source'))process.exit(2);const f=p.join(a[a.indexOf('--target')+1],'init-count');fs.writeFileSync(f,String(Number(fs.existsSync(f)?fs.readFileSync(f,'utf8'):0)+1));`)
    packages.set(`${WORKFLOW_SCOPE + id}@${version}`, { manifest, directory }); latest.set(id, version)
  }
  for (const entry of entries) add(entry.id, '1.0.0')
  const fetcher: NpmFetcher = {
    async manifest(spec) {
      if (offline) throw new Error('Network unavailable')
      if (spec === `${CATALOG_PACKAGE}@latest`) return { name: CATALOG_PACKAGE, version: catalogVersion, dist: { integrity: '', tarball: '' }, cannbotWorkflowCatalog: { schemaVersion: 1, workflows: entries } }
      const entry = entries.find(item => spec.startsWith(item.package + '@'))!
      const version = spec.endsWith('@latest') ? latest.get(entry.id) : spec.slice(entry.package.length + 1)
      return structuredClone(packages.get(`${entry.package}@${version}`)!.manifest)
    },
    async extract(spec, destination, options) {
      if (spec === bad) throw new Error('EINTEGRITY: corrupt tarball')
      const value = [...packages.values()].find(item => item.manifest.dist.tarball === spec)!
      expect(options.ignoreScripts).toBe(true); expect(options.integrity).toBe(value.manifest.dist.integrity)
      cpSync(value.directory, destination, { recursive: true }); extracted.push(value.manifest.name + '@' + value.manifest.version)
    },
  }
  const cache = join(root, 'cache'), manager = new ContentManager(defaults, cache, fetcher)
  const catalogFile = join(root, 'dependency-catalog.json')
  writeFileSync(catalogFile, JSON.stringify({ name: CATALOG_PACKAGE, version: '1.0.1', dependencies: Object.fromEntries(entries.map(entry => [entry.package, '*'])), cannbotWorkflowCatalog: { schemaVersion: 1, workflows: entries } }))
  const resolveDependency = (name: string) => join(packages.get(`${name}@1.0.0`)!.directory, 'package.json')
  return { root, cache, workspace, defaults, manager, fetcher, add, extracted, catalogFile, resolveDependency,
    fail: (id: string, version: string) => { bad = packages.get(`${WORKFLOW_SCOPE + id}@${version}`)!.manifest.dist.tarball },
    offline: () => { offline = true },
    newWorkflow: (id: string) => { entries.push({ id, title: id, package: WORKFLOW_SCOPE + id, default: true }); add(id, '1.0.0'); catalogVersion = '1.0.1' },
    foreign: () => { entries[0].package = '@untrusted/other' },
  }
}
it('updates one workflow independently without changing another workflow or the main plugin', async () => {
  const f = fixture(); await f.manager.sync(); f.add('flow-a', '1.1.0'); f.add('flow-b', '1.2.0')
  await f.manager.sync('flow-a', '1.1.0')
  expect(f.manager.getStatus().workflows?.map(item => [item.id, item.version])).toEqual([['flow-a', '1.1.0'], ['flow-b', '1.0.0']])
  expect(f.extracted).toHaveLength(3)
})
it('activates every npm-installed dependency offline without a background download', async () => {
  const f = fixture(); f.offline()
  await f.manager.installDependencies(f.catalogFile, f.resolveDependency)
  expect(f.manager.getStatus()).toMatchObject({ phase: 'ready', busy: false, catalogVersion: '1.0.1' })
  expect(f.manager.getStatus().workflows?.every(row => row.installed && row.version === '1.0.0')).toBe(true)
  expect(f.extracted).toHaveLength(0)
  await f.manager.prepare(f.workspace, 'flow-a')
  expect(readFileSync(join(f.workspace, 'init-count'), 'utf8')).toBe('1')
})
it('preserves independently updated and rolled-back versions when npm dependencies are reactivated', async () => {
  const f = fixture(); await f.manager.installDependencies(f.catalogFile, f.resolveDependency)
  await f.manager.sync() // A directory identity is not a registry SRI, but same-version checks succeed.
  f.add('flow-a', '1.1.0'); await f.manager.sync('flow-a')
  await f.manager.installDependencies(f.catalogFile, f.resolveDependency)
  expect(f.manager.getStatus().workflows?.[0].version).toBe('1.1.0')
  await f.manager.rollback('flow-a'); await f.manager.installDependencies(f.catalogFile, f.resolveDependency)
  expect(f.manager.getStatus().workflows?.[0]).toMatchObject({ version: '1.0.0', pinned: true })
})
it('fails activation when an npm-installed baseline is missing or invalid', async () => {
  const f = fixture()
  await expect(f.manager.installDependencies(f.catalogFile, () => { throw Error('missing dependency') })).rejects.toThrow('missing dependency')
  expect(f.manager.getStatus()).toMatchObject({ phase: 'error', busy: false })
})
it('refreshes changed source content at the same version and preserves unchanged initialization', async () => {
  const f = fixture(); f.offline()
  await f.manager.installDependencies(f.catalogFile, f.resolveDependency, true)
  await f.manager.prepare(f.workspace, 'flow-a')
  const before = f.manager.getSource().revision
  await f.manager.installDependencies(f.catalogFile, f.resolveDependency, true)
  expect(f.manager.getSource().revision).toBe(before)
  const directory = resolve(f.resolveDependency(WORKFLOW_SCOPE + 'flow-a'), '..')
  const descriptor = JSON.parse(readFileSync(join(directory, 'workflow.json'), 'utf8'))
  descriptor.contentHash = 'changed-source-content'
  writeFileSync(join(directory, 'workflow.json'), JSON.stringify(descriptor))
  writeFileSync(join(directory, 'resources/skills/flow-a/SKILL.md'), 'updated source')
  await f.manager.installDependencies(f.catalogFile, f.resolveDependency, true)
  expect(f.manager.getSource().revision).not.toBe(before)
  const skill = f.manager.getSource().catalog.exposedSkills.find(item => item.name === 'flow-a')!
  expect(readFileSync(join(f.cache, skill.path), 'utf8')).toBe('updated source')
  await f.manager.prepare(f.workspace, 'flow-a')
  expect(readFileSync(join(f.workspace, 'init-count'), 'utf8')).toBe('2')
})
it('keeps all active workflows when a source installation is incomplete', async () => {
  const f = fixture(); await f.manager.installDependencies(f.catalogFile, f.resolveDependency)
  const before = readFileSync(join(f.cache, 'active.json'), 'utf8')
  await expect(f.manager.installDependencies(f.catalogFile, name => {
    if (name.endsWith('flow-b')) throw Error('missing source resource')
    return f.resolveDependency(name)
  }, true)).rejects.toThrow('missing source resource')
  expect(readFileSync(join(f.cache, 'active.json'), 'utf8')).toBe(before)
})
it('retains the active version on a corrupt download', async () => {
  const f = fixture(); await f.manager.sync(); const before = readFileSync(join(f.cache, 'active.json'), 'utf8')
  f.add('flow-a', '1.1.0'); f.fail('flow-a', '1.1.0')
  await expect(f.manager.sync('flow-a')).rejects.toThrow('EINTEGRITY')
  expect(readFileSync(join(f.cache, 'active.json'), 'utf8')).toBe(before)
  expect(f.manager.getStatus().workflows?.[0].version).toBe('1.0.0')
  expect(readdirSync(join(f.cache, 'packages/flow-a'))).toHaveLength(1)
})
it('rolls back one workflow, pins automatic updates, and initializes once per package version', async () => {
  const f = fixture(); await f.manager.sync()
  await Promise.all([f.manager.prepare(f.workspace, 'flow-a'), f.manager.prepare(f.workspace, 'flow-a')])
  expect(readFileSync(join(f.workspace, 'init-count'), 'utf8')).toBe('1')
  f.add('flow-a', '1.1.0'); await f.manager.sync('flow-a'); await f.manager.prepare(f.workspace, 'flow-a')
  expect(readFileSync(join(f.workspace, 'init-count'), 'utf8')).toBe('2')
  await f.manager.rollback('flow-a'); await f.manager.sync()
  expect(f.manager.getStatus().workflows?.[0]).toMatchObject({ version: '1.0.0', pinned: true, latest: '1.1.0' })
  await f.manager.prepare(f.workspace, 'flow-a'); expect(readFileSync(join(f.workspace, 'init-count'), 'utf8')).toBe('3')
  await f.manager.sync('flow-a'); expect(f.manager.getStatus().workflows?.[0].pinned).toBe(false)
})
it('discovers a new catalog workflow without releasing the main plugin', async () => {
  const f = fixture(); await f.manager.sync(); f.newWorkflow('new-workflow'); await f.manager.sync()
  expect(f.manager.getStatus().catalogVersion).toBe('1.0.1')
  expect(f.manager.getSource().catalog.plugins.map(item => item.id)).toContain('new-workflow')
})
it('uses cached workflows offline and notices another profile updating the cache', async () => {
  const f = fixture(); await f.manager.sync()
  const second = new ContentManager(f.defaults, f.cache, f.fetcher), original = second.getSource().revision
  f.add('flow-a', '1.1.0'); await f.manager.sync('flow-a'); expect(second.getSource().revision).not.toBe(original)
  f.offline(); await second.prepare(f.workspace, 'flow-a'); expect(readFileSync(join(f.workspace, 'init-count'), 'utf8')).toBe('1')
})
it('queues different concurrent update requests rather than dropping one', async () => {
  const f = fixture(); await f.manager.sync(); f.add('flow-a', '1.1.0'); f.add('flow-b', '1.1.0')
  await Promise.all([f.manager.sync('flow-a'), f.manager.sync('flow-b')])
  expect(f.manager.getStatus().workflows?.map(item => item.version)).toEqual(['1.1.0', '1.1.0'])
})
it('rejects foreign publishers before extracting or executing a package', async () => {
  const f = fixture(); f.foreign(); await expect(f.manager.sync()).rejects.toThrow('Invalid workflow catalog entry'); expect(f.extracted).toHaveLength(0)
})
it('uses a registry mirror when the primary connection is unavailable', async () => {
  const f = fixture(), manifest = f.fetcher.manifest.bind(f.fetcher), extract = f.fetcher.extract.bind(f.fetcher)
  f.fetcher.manifest = async (spec, options) => {
    if (options.registry === REGISTRY) throw new Error('Network timeout')
    const value = await manifest(spec, options)
    if (value.dist.tarball) value.dist.tarball = value.dist.tarball.replace(REGISTRY, MIRROR)
    return value
  }
  f.fetcher.extract = (spec, destination, options) => extract(spec.replace(MIRROR, REGISTRY), destination, options)
  await f.manager.sync()
  expect(f.manager.getStatus().workflows?.every(item => item.installed)).toBe(true)
})
it('rejects a mirror whose exact-version tarball integrity differs', async () => {
  const f = fixture(); await f.manager.sync(); f.add('flow-a', '1.1.0')
  const manifest = f.fetcher.manifest.bind(f.fetcher), extract = f.fetcher.extract.bind(f.fetcher)
  f.fetcher.manifest = async (spec, options) => {
    const value = await manifest(spec, options)
    if (options.registry === MIRROR) value.dist.integrity = 'sha512-V1JPTkc='
    return value
  }
  f.fetcher.extract = (spec, destination, options) => spec.includes('1.1.0') ? Promise.reject(new Error('Network timeout')) : extract(spec, destination, options)
  await expect(f.manager.sync('flow-a')).rejects.toThrow('integrity')
  expect(f.manager.getStatus().workflows?.[0].version).toBe('1.0.0')
  expect(readdirSync(join(f.cache, 'packages/flow-a'))).toHaveLength(1)
})
it('serializes workspace operations regardless of lock acquisition order', async () => {
  mkdirSync('.acceptance-workflow-tests', { recursive: true })
  const root = mkdtempSync(resolve('.acceptance-workflow-tests/lock-')), events: number[] = []
  await Promise.all([1, 2].map(value => withContentLock(join(root, 'workspace.lock'), async () => { events.push(value); await new Promise(done => setTimeout(done, 20)); events.push(value) })))
  expect(events[0]).toBe(events[1]); expect(events[2]).toBe(events[3]); expect(events[0]).not.toBe(events[2])
})

it('removes abandoned primary extraction after mirror fallback succeeds', async () => {
  const f = fixture(), manifest = f.fetcher.manifest.bind(f.fetcher), extract = f.fetcher.extract.bind(f.fetcher)
  f.fetcher.manifest = async (spec, options) => {
    const result = await manifest(spec, options)
    if (options.registry === MIRROR && result.dist.tarball) result.dist.tarball = result.dist.tarball.replace(REGISTRY, MIRROR)
    return result
  }
  f.fetcher.extract = async (spec, destination, options) => {
    if (spec.startsWith(REGISTRY)) { writeFileSync(join(destination, 'partial'), 'interrupted'); throw new Error('Network timeout') }
    await extract(spec.replace(MIRROR, REGISTRY), destination, options)
  }
  await f.manager.sync()
  for (const id of ['flow-a', 'flow-b']) expect(readdirSync(join(f.cache, 'packages', id))).toHaveLength(1)
})
it('preserves a published package if an error occurs after saving the index', async () => {
  const f = fixture(); await f.manager.sync(); f.add('flow-a', '1.1.0')
  const manager = f.manager as unknown as { save(next: { records: Record<string, { version: string }> }): Promise<void> }
  const save = manager.save.bind(manager)
  manager.save = async next => { await save(next); if (next.records['flow-a']?.version === '1.1.0') throw new Error('after publication') }
  await expect(f.manager.sync('flow-a')).rejects.toThrow('after publication')
  const active = JSON.parse(readFileSync(join(f.cache, 'active.json'), 'utf8'))
  expect(readFileSync(join(f.cache, active.records['flow-a'].directory, 'workflow.json'), 'utf8')).toContain('1.1.0')
})
