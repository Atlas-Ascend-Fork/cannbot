import test from 'node:test'
import assert from 'node:assert/strict'
import { cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { execFileSync } from 'node:child_process'
import { ContentManager } from '../../../../dsh/src/workflow-package-manager.ts'

const repository = fileURLToPath(new URL('../../../../', import.meta.url))

test('classified resources package the declared entry and isolated prerequisite, and require initialization answers', async t => {
  const root = mkdtempSync(join(tmpdir(), 'dsh-classified-package-'))
  t.after(() => rmSync(root, { recursive: true, force: true }))
  const source = join(root, 'source')
  const write = (path, value) => {
    const target = join(source, path)
    mkdirSync(dirname(target), { recursive: true })
    writeFileSync(target, typeof value === 'string' ? value : JSON.stringify(value))
  }
  const skill = (path, name) => write(path + '/SKILL.md', `---\nname: ${name}\ndescription: fixture\n---\n${name}\n`)
  write('vendor/cannbot-skills/LICENSE', 'shared license')
  write('plugins-official/LICENSE', 'plugin license')
  for (const id of ['ops-direct-invoke-flash', 'ops-registry-invoke', 'ops-perf-optimize']) {
    write(`plugins-official/${id}/.claude-plugin/plugin.json`, { name: id, version: '1.0.0', description: id })
    skill(`plugins-official/${id}/skills/${id === 'ops-perf-optimize' ? 'ops-perf-optimize-workflow' : id}`, id === 'ops-perf-optimize' ? 'ops-perf-optimize-workflow' : id)
  }
  write('plugins-official/ops-registry-invoke/skills/ops-registry-invoke/skills.json', { skills: { native: [], external: [] } })
  write('plugins-official/ops-perf-optimize/AGENTS.md', 'original performance identity')
  write('plugins-official/ops-perf-optimize/installer/install-opmodel.sh', 'exit 0\n')
  const direct = 'plugins-official/ops-direct-invoke'
  write(`${direct}/.claude-plugin/plugin.json`, { name: 'ops-direct-invoke', version: '1.0.0', description: 'fixture', skills: ['./skills/maintain', './skills/orchestrator'] })
  write(`${direct}/plugin-install.json`, { entrySkill: 'ops-direct-invoke', initializer: 'tools/install.mjs', nativeWorkflow: 'tools/dsh-native.mjs' })
  write(`${direct}/plugin-sources.json`, { skillsRepository: '.', skills: ['harness/short-name'], extraAssets: ['skills/custom-skills'] })
  skill('harness/short-name', 'workflow-orchestrator')
  write('harness/short-name/scripts/orchestrator.py', '# shared scheduler\n')
  for (const name of ['maintain', 'orchestrator']) skill(`${direct}/skills/${name}`, name === 'orchestrator' ? 'ops-direct-invoke' : `ops-direct-invoke-${name}`)
  for (const platform of ['ascend', 'kirin']) skill(`${direct}/skills/custom-skills/requirement/${platform}`, 'ops-direct-invoke-requirement')
  for (const repo of ['cannbench', 'common']) skill(`${direct}/skills/custom-skills/repo-guide/${repo}`, 'ops-direct-invoke-repo-guide')
  write(`${direct}/skills/custom-skills/env-check/ascend/platform.json`, { languages: ['ascendc', 'dsl'] })
  write(`${direct}/tools/runtime.py`, '# preserved tool\n')
  for (const name of ['install.mjs', 'direct-invoke-config.mjs', 'dsh-native.mjs']) cpSync(join(repository, direct, 'tools', name), join(source, direct, 'tools', name))
  write(`${direct}/orchestrations/workflows/basic.yaml`, 'workflow: fixture\n')
  cpSync(join(repository, 'script/lib'), join(source, 'script/lib'), { recursive: true })
  mkdirSync(join(source, 'script/bin'), { recursive: true })
  cpSync(join(repository, 'script/bin/cannbot.js'), join(source, 'script/bin/cannbot.js'))
  cpSync(join(repository, 'script/LICENSE'), join(source, 'script/LICENSE'))
  const git = (...args) => execFileSync('git', args, { cwd: source, stdio: 'pipe' })
  git('init', '--quiet'); git('add', '.')
  git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', '-c', 'commit.gpgsign=false', 'commit', '--quiet', '-m', 'fixture')
  const output = join(root, 'reports'), buildRoot = join(root, 'packages')
  execFileSync(process.execPath, [join(repository, 'dsh/scripts/build-workflow-packages.mjs'), '--source', source,
    '--build-root', buildRoot, '--output', output, '--no-pack', 'true', '--id', 'ops-direct-invoke'], { stdio: 'pipe' })
  const packaged = join(buildRoot, 'packages/ops-direct-invoke/1.0.0')
  const descriptor = JSON.parse(readFileSync(join(packaged, 'workflow.json')))
  assert.deepEqual(descriptor.skills.filter(item => item.entry).map(item => item.name), ['ops-direct-invoke'])
  assert.deepEqual(descriptor.skills.map(item => item.name).sort(), ['ops-direct-invoke', 'ops-direct-invoke-maintain'])
  for (const path of ['resources/skills/short-name/scripts/orchestrator.py',
    'resources/skills/custom-skills/requirement/kirin/SKILL.md', 'resources/tools/runtime.py',
    'upstream/dist/plugins/ops-perf-optimize/skills/ops-perf-optimize-workflow/SKILL.md']) assert.ok(existsSync(join(packaged, path)), path)
  assert.equal(existsSync(join(packaged, 'resources/skills/ops-direct-invoke/SKILL.md')), false)
  const entry = { id: 'ops-direct-invoke', title: 'fixture', package: '@cannbot-plugin/workflow-ops-direct-invoke', default: true }
  const defaults = join(root, 'defaults.json'), catalog = join(root, 'catalog.json')
  writeFileSync(defaults, JSON.stringify({ workflows: [entry] }))
  writeFileSync(catalog, JSON.stringify({ name: '@cannbot-plugin/workflow-catalog', version: '1.0.0',
    dependencies: { [entry.package]: '*' }, cannbotWorkflowCatalog: { schemaVersion: 1, workflows: [entry] } }))
  const manager = new ContentManager(defaults, join(root, 'cache'), {
    async manifest() { assert.fail('test must stay offline') }, async extract() { assert.fail('test must stay offline') },
  })
  await manager.installDependencies(catalog, () => join(packaged, 'package.json'))
  assert.equal(manager.getSource().catalog.exposedSkills.find(item => item.entry).name, 'ops-direct-invoke')
  const workspace = join(root, 'workspace')
  mkdirSync(workspace)
  await assert.rejects(manager.prepare(workspace, entry.id), /needs initialization answers/)
  assert.equal(existsSync(join(workspace, '.cannbot/ops-direct-invoke.json')), false)
  mkdirSync(join(workspace, '.cannbot'), { recursive: true })
  writeFileSync(join(workspace, '.cannbot/ops-direct-invoke.json'), JSON.stringify({
    repo: 'common', platform: 'ascend', chip: 'test', preferences: { interaction: 'confirm', autonomy: 'test only', review_points: [] },
  }))
  await manager.prepare(workspace, entry.id)
  assert.deepEqual(readdirSync(join(workspace, '.dsh/skills')).sort(), ['ops-direct-invoke', 'ops-direct-invoke-maintain', 'ops-direct-invoke-repo-guide', 'ops-direct-invoke-requirement'])
  assert.ok(existsSync(join(workspace, '.cannbot/dependencies/ops-direct-invoke/performance/.dsh/skills/ops-perf-optimize-workflow/SKILL.md')))
})
