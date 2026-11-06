import test from 'node:test'
import assert from 'node:assert/strict'
import { installWorkflowContext, Config } from '../src/workflow-context.ts'

function setup(config, legacy = false) {
  let hook
  let legacyValue = config
  const skill = {
    name: 'ops-direct-invoke', provider: 'cannbot-dsh', content: 'OFFICIAL WORKFLOW INSTRUCTIONS',
    invocation: { userInvocable: true, modelInvocable: true },
    resourceBase: { kind: 'directory', path: '/packaged/skills/ops-direct-invoke' },
  }
  const ctx = {
    inject(keys, callback) {
      if (keys.includes('settings')) callback({ settings: legacy ? { register: () => ({ get: () => legacyValue }) } : {} })
      else callback(this)
    },
    on(_event, handler) { hook = handler },
    workingDirectory: { ensure: async () => '/workspace' },
    skills: { get: async () => skill },
  }
  // The official Loader passes parsed Config, whose volatile fields expose get().
  installWorkflowContext(ctx, Config(config))
  return { run: (sessionId, messages) => hook({ agent: { id: sessionId }, signal: new AbortController().signal }, async () => ({ kind: 'continue', messages })),
    setLegacy: value => { legacyValue = value }, ctx }
}

test('adds the selected official Skill as model context while retaining the exact user text and attachments', async () => {
  const user = { role: 'user', id: 'user-1', source: { kind: 'user' }, content: [{ type: 'text', text: '开发矩阵算子' }, { type: 'image', data: 'IMAGE' }] }
  const before = structuredClone(user)
  const app = setup({ selections: [{ sessionId: 'A', workflow: 'ops-direct-invoke' }] })
  const result = await app.run('A', [user])
  assert.deepEqual(user, before)
  assert.strictEqual(result.messages[0], user)
  assert.equal(result.messages.length, 2)
  assert.equal(result.messages[1].source.kind, 'cannbot-dsh-workflow')
  assert(result.messages[1].content[0].text.includes('OFFICIAL WORKFLOW INSTRUCTIONS'))
  assert(!JSON.stringify(user).includes('/ops-direct-invoke'))
  assert.equal((await app.run('B', [user])).messages.length, 1)
})

test('replaces previous workflow context and normal conversation removes it', async () => {
  const old = { role: 'user', id: 'old-context', source: { kind: 'cannbot-dsh-workflow', name: 'old' }, content: [] }
  const user = { role: 'user', id: 'user-2', source: { kind: 'user' }, content: [{ type: 'text', text: '需求' }] }
  const active = setup({ selections: [{ sessionId: 'A', workflow: 'ops-direct-invoke' }] })
  const result = await active.run('A', [old, user])
  assert(!result.messages.includes(old))
  assert.equal(result.messages.filter(message => message.source.kind === 'cannbot-dsh-workflow').length, 1)
  const normal = setup({ selections: [] })
  assert.deepEqual((await normal.run('A', [old, user])).messages, [user])
})

test('legacy namespace settings are read live without raising the DSH minimum', async () => {
  const app = setup({}, true)
  assert.equal((await app.run('A', [])).messages.length, 0)
  app.setLegacy({ selections: [{ sessionId: 'A', workflow: 'ops-direct-invoke' }] })
  assert.equal((await app.run('A', [])).messages.length, 1)
})

test('unavailable or user-disabled workflows cannot silently fall back to ordinary execution', async () => {
  const app = setup({ selections: [{ sessionId: 'A', workflow: 'ops-direct-invoke' }] })
  app.ctx.skills.get = async () => undefined
  await assert.rejects(app.run('A', []), /workflow is unavailable/)
})
