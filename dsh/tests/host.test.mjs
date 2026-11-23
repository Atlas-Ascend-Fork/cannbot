import test from 'node:test'
import assert from 'node:assert/strict'
import { Context } from '@deepseek-ai/cordis'
import SkillRegistry from '@deepseek-ai/dsh-skill'
import { readFileSync, accessSync, mkdirSync, mkdtempSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { pathToFileURL } from 'node:url'
import { createVerifiedWorkflowCache } from './workflow-package-fixture.mjs'

const pluginApi = await import(process.env.CANNBOT_TEST_HOST_PACKAGE
  ? pathToFileURL(join(resolve(process.env.CANNBOT_TEST_HOST_PACKAGE), 'lib/index.js')).href
  : new URL('../lib/index.js', import.meta.url).href)
if (process.env.CANNBOT_TEST_HOST_PACKAGE) console.log('Host test provenance: isolated copies of published workflow packages; this does not validate rebuilding master workflow resources.')
// All remote paths and SSH discovery remain inside the test workspace.
const isolation = resolve('.acceptance-workflow-tests/host-environment')
process.env.DSH_HOME = isolation
process.env.CANNBOT_REMOTE_SSH = 'ssh'
process.env.CANNBOT_REMOTE_SSH_CONFIG = join(isolation, 'ssh-config')

test('a fresh activation awaits all npm-installed workflows before exposing the enabled plugin', async () => {
  mkdirSync('.acceptance-workflow-tests', { recursive: true })
  const cache = mkdtempSync(resolve('.acceptance-workflow-tests/dependency-activation-'))
  const previous = process.env.CANNBOT_DSH_WORKFLOW_ROOT
  process.env.CANNBOT_DSH_WORKFLOW_ROOT = cache
  const ctx = new Context()
  try {
    await ctx.plugin(SkillRegistry)
    const fiber = ctx.plugin(pluginApi)
    await fiber.await()
    const index = JSON.parse(readFileSync(resolve(cache, 'active.json'), 'utf8'))
    assert.equal(Object.keys(index.records).length, 3)
    assert(Object.values(index.records).every(record => record.dependency === true))
    const skills = await ctx.skills.list()
    assert(skills.length > 0)
    for (const id of Object.keys(index.records)) assert(skills.some(skill => skill.name === id))
  } finally {
    await ctx.fiber.dispose()
    if (previous === undefined) delete process.env.CANNBOT_DSH_WORKFLOW_ROOT
    else process.env.CANNBOT_DSH_WORKFLOW_ROOT = previous
  }
})

test('all three official plugins and every exposed Skill follow enable, disable and re-enable', async () => {
  const ctx = new Context()
  const fixture = await createVerifiedWorkflowCache()
  const catalog = fixture.manager.getSource().catalog
  const oldRoot = process.env.CANNBOT_DSH_WORKFLOW_ROOT
  process.env.CANNBOT_DSH_WORKFLOW_ROOT = fixture.cache
  try {
    await ctx.plugin(SkillRegistry)
    for (let activation = 0; activation < 2; activation++) {
      const fiber = ctx.plugin(pluginApi)
      await fiber.await()
      const skills = await ctx.skills.list()
      assert.equal(skills.length, catalog.exposedSkills.length)
      const names = new Set(skills.map(skill => skill.name))
      assert.equal(catalog.plugins.length, 3)
      for (const plugin of catalog.plugins) {
        assert(names.has(plugin.id), `Missing workflow entry: ${plugin.id}`)
        for (const skill of catalog.exposedSkills.filter(item => item.pluginId === plugin.id)) assert(names.has(skill.name), `Missing ${plugin.id} dependency: ${skill.name}`)
      }
      assert(skills.every(skill => skill.provider === 'cannbot-dsh'))
      for (const expected of catalog.exposedSkills) {
        const skill = await ctx.skills.get(expected.name)
        assert(skill?.content, `Skill cannot be loaded: ${expected.name}`)
        assert.equal(skill.name, expected.name)
        const current = fixture.manager.getSource().catalog.exposedSkills.find(item => item.name === expected.name)
        assert(current, `Missing independent package Skill: ${expected.name}`)
        assert.equal(resolve(skill.resourceBase.path), resolve(dirname(fixture.cache + '/' + current.path)))
        accessSync(skill.path)
      }
      const registryEntry = await ctx.skills.get('ops-registry-invoke')
      assert(registryEntry.content.includes('workflow-orchestrator'))
      await fiber.dispose()
      assert.equal((await ctx.skills.list()).length, 0)
    }
  } finally { await ctx.fiber.dispose(); if (oldRoot === undefined) delete process.env.CANNBOT_DSH_WORKFLOW_ROOT; else process.env.CANNBOT_DSH_WORKFLOW_ROOT = oldRoot }
})

test('the unchanged upstream installer initializes a workspace directly from a workflow npm package', async () => {
  const fixture = await createVerifiedWorkflowCache()
  await fixture.manager.prepare(fixture.workspace, 'ops-direct-invoke-flash')
  const installed = JSON.parse(readFileSync(resolve(fixture.workspace, '.dsh/cannbot-plugin.json'), 'utf8'))
  assert(JSON.stringify(installed).includes('ops-direct-invoke-flash'))
  assert(JSON.stringify(installed).includes('dsh'))
  accessSync(resolve(fixture.workspace, '.dsh/skills/ops-direct-invoke-flash/SKILL.md'))
})
