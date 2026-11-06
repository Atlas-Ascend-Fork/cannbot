import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdirSync, mkdtempSync, readFileSync, readdirSync, writeFileSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { ContentManager } from '../src/content-manager.ts'

const shipped = ['ops-direct-invoke', 'ops-direct-invoke-flash', 'ops-registry-invoke']
const retired = ['hccl-op-generator', 'triton-op-generator']

function packageFor(root, id) {
  const directory = join(root, 'packages', id, '1.0.0-dependency-TEST')
  const skills = join(directory, 'resources', 'skills', id)
  mkdirSync(skills, { recursive: true })
  writeFileSync(join(directory, 'package.json'), JSON.stringify({ name: `@cannbot-plugin/workflow-${id}`, version: '1.0.0', cannbotWorkflow: { schemaVersion: 1, id } }))
  writeFileSync(join(directory, 'workflow.json'), JSON.stringify({ schemaVersion: 1, id, title: id, version: '1.0.0', initialization: { kind: 'skill-native' }, skills: [{ name: id, path: `skills/${id}/SKILL.md`, hash: '0'.repeat(64), entry: true }] }))
  writeFileSync(join(skills, 'SKILL.md'), `---\nname: ${id}\ndescription: fixture\n---\n`)
  return { directory: `packages/${id}/1.0.0-dependency-TEST`, id }
}

function cacheWith(ids) {
  const root = mkdtempSync(resolve('.acceptance-workflow-tests/prune-'))
  const entries = [], records = {}
  for (const id of ids) {
    const { directory } = packageFor(root, id)
    entries.push({ id, title: id, package: `@cannbot-plugin/workflow-${id}`, default: true })
    records[id] = { id, package: `@cannbot-plugin/workflow-${id}`, version: '1.0.0', integrity: `dependency:${id}`, directory, installedAt: new Date(0).toISOString(), dependency: true }
  }
  writeFileSync(join(root, 'active.json'), JSON.stringify({ schemaVersion: 1, catalogVersion: '1.0.2', entries, records, history: {}, pinned: [retired[0]] }))
  return root
}

test('entries and copies retired by a later release are dropped from an existing cache', async () => {
  mkdirSync('.acceptance-workflow-tests', { recursive: true })
  const root = cacheWith([...shipped, ...retired])
  const catalog = join(root, 'catalog.json')
  writeFileSync(catalog, JSON.stringify({
    name: '@cannbot-plugin/workflow-catalog',
    version: '1.0.3',
    cannbotWorkflowCatalog: { schemaVersion: 1, workflows: shipped.map(id => ({ id, title: id, package: `@cannbot-plugin/workflow-${id}`, default: true })) },
    dependencies: Object.fromEntries(shipped.map(id => [`@cannbot-plugin/workflow-${id}`, '>=1.0.0'])),
  }))
  const manager = new ContentManager(resolve('workflow-defaults.json'), root, {
    async manifest() { throw new Error('Unexpected network access') },
    async extract() { throw new Error('Unexpected network access') },
  })
  await manager.installDependencies(catalog, name => join(root, 'packages', name.split('/workflow-')[1], '1.0.0-dependency-TEST', 'package.json'))
  const status = manager.getStatus()
  assert.deepEqual(status.workflows.map(row => row.id), shipped)
  assert.deepEqual(status.plugins.map(plugin => plugin.id), shipped)
  const index = JSON.parse(readFileSync(join(root, 'active.json'), 'utf8'))
  assert.deepEqual(Object.keys(index.records), shipped)
  assert.deepEqual(readdirSync(join(root, 'packages')).sort(), [...shipped].sort())
})
