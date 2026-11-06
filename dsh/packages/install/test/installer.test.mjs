import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtemp, writeFile, mkdir, readFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import net from 'node:net'
import { options, claimRoot, freePort, verify, reusableRuntimeLock } from '../lib/installer.mjs'
import { resolvePlan, CORE, CATALOG, PLUGIN, DSH_VERSION, PNPM_VERSION } from '../lib/plan.mjs'

const snapshot = () => ({
  [PLUGIN]: { name: PLUGIN, version: '1.0.0-alpha.1', dependencies: { [CORE]: '1.0.0-alpha.1' } },
  [CORE]: { name: CORE, version: '1.0.0-alpha.1', engines: { dsh: '>=0.1.1-rc.1 <0.3.0' }, dependencies: { [CATALOG]: '^1.0.4' } },
  [CATALOG]: { name: CATALOG, version: '1.0.4', dependencies: { '@cannbot-plugin/workflow-flow-a': '>=1.0.0' }, cannbotWorkflowCatalog: { schemaVersion: 1, workflows: [{ id: 'flow-a', package: '@cannbot-plugin/workflow-flow-a', default: true }] } },
  '@cannbot-plugin/workflow-flow-a': { version: '1.1.0', cannbotWorkflow: { schemaVersion: 1, id: 'flow-a' } },
})
test('resolves actual latest versions, including independently updated workflows', async () => {
  const values = snapshot(), requests = []
  const plan = await resolvePlan(async name => { requests.push(name); return values[name] })
  assert.equal(plan.plugin, '1.0.0-alpha.1'); assert.equal(plan.workflows[0].version, '1.1.0'); assert.equal(requests.length, 4)
})
test('refuses out-of-sync short packages and incompatible DSH versions', async () => {
  const values = snapshot(); values[PLUGIN].dependencies[CORE] = '1.0.0-alpha.2'
  await assert.rejects(resolvePlan(async name => values[name]), /尚未同步/)
  values[PLUGIN].dependencies[CORE] = '1.0.0-alpha.1'; values[CORE].engines.dsh = '>=0.3.0'
  await assert.rejects(resolvePlan(async name => values[name]), /更新的 DSH/)
})
test('rejects a foreign workflow publisher before installation', async () => {
  const values = snapshot(); values[CATALOG].cannbotWorkflowCatalog.workflows[0].package = '@foreign/flow-a'
  await assert.rejects(resolvePlan(async name => values[name]), /无效条目/)
})
test('refuses newer Node requirements before downloading the runtime', async () => {
  const values = snapshot(); values[CORE].engines.node = '>=26'
  await assert.rejects(resolvePlan(async name => values[name], '24.9.0'), /更新的 Node.js/)
})
test('validates options without allowing credential-bearing or insecure registries', () => {
  assert.equal(options(['--no-start', '--port', '3100']).port, 3100)
  for (const args of [['--registry', 'http://example.test'], ['--registry', 'https://user:pass@example.test'], ['--port', '0'], ['--dir'], ['--unknown']]) assert.throws(() => options(args))
})
test('reuses only installer-owned directories and preserves unrelated contents', async () => {
  const root = await mkdtemp(join(tmpdir(), 'cannbot-installer-test-'))
  await writeFile(join(root, 'keep.txt'), 'user data')
  await assert.rejects(claimRoot(root), /非空/)
  assert.equal(await readFile(join(root, 'keep.txt'), 'utf8'), 'user data')
  const owned = join(root, 'owned'); await claimRoot(owned); await claimRoot(owned)
})
test('falls back from a busy default port, but never ignores an explicitly requested busy port', async () => {
  const server = net.createServer(); await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
  try { await assert.rejects(freePort(server.address().port), /无法使用端口/); assert(Number.isInteger(await freePort())) }
  finally { await new Promise(resolve => server.close(resolve)) }
})
test('missing plugin resources cannot be reported as a successful installation', async () => {
  const root = await mkdtemp(join(tmpdir(), 'cannbot-installer-verification-'))
  const modules = join(root, 'profiles/web/node_modules')
  const values = snapshot(), plan = await resolvePlan(async name => values[name])
  const put = async (name, value) => { await mkdir(join(modules, name), { recursive: true }); await writeFile(join(modules, name, 'package.json'), JSON.stringify(value)) }
  await put(PLUGIN, { version: plan.plugin }); await put(CORE, { version: plan.core }); await put(CATALOG, { version: plan.catalog })
  await put(plan.workflows[0].package, { version: '1.1.0' })
  const workflowRoot = join(modules, plan.workflows[0].package)
  await writeFile(join(workflowRoot, 'workflow.json'), JSON.stringify({ id: 'flow-a', version: '1.1.0', skills: [{ path: 'skills/flow-a/SKILL.md' }] }))
  await assert.rejects(async () => verify(root, plan), /资源不完整/)
  await mkdir(join(workflowRoot, 'resources/skills/flow-a'), { recursive: true }); await writeFile(join(workflowRoot, 'resources/skills/flow-a/SKILL.md'), 'verified')
  await writeFile(join(root, 'profiles/web/package.json'), JSON.stringify({ dsh: { profile: { bundles: [PLUGIN] } } }))
  assert.equal(verify(root, plan).workflowCount, 1)
})
test('only a lockfile for the exact qualified runtime can be used for interrupted-install recovery', async () => {
  const runtime = await mkdtemp(join(tmpdir(), 'cannbot-runtime-lock-'))
  await writeFile(join(runtime, 'package.json'), JSON.stringify({ dependencies: { '@deepseek-ai/dsh': DSH_VERSION, pnpm: PNPM_VERSION } }))
  const lock = { packages: { 'node_modules/@deepseek-ai/dsh': { version: DSH_VERSION }, 'node_modules/pnpm': { version: PNPM_VERSION } } }
  await writeFile(join(runtime, 'package-lock.json'), JSON.stringify(lock))
  assert.equal(reusableRuntimeLock(runtime), true)
  lock.packages['node_modules/@deepseek-ai/dsh'].version = '0.1.0'
  await writeFile(join(runtime, 'package-lock.json'), JSON.stringify(lock))
  assert.equal(reusableRuntimeLock(runtime), false)
})
