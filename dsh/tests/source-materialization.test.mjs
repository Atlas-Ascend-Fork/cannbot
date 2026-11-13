import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync, symlinkSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { execFileSync } from 'node:child_process'
import { resolveSource } from '../scripts/source.mjs'

test('assembly reads current files and changed symlinks without a stored asset snapshot', () => {
  const root = mkdtempSync(join(tmpdir(), 'cannbot-materialize-test-'))
  const source = join(root, 'source')
  const write = (path, value) => {
    const file = join(source, path)
    mkdirSync(join(file, '..'), { recursive: true })
    writeFileSync(file, value)
  }
  const git = (...args) => execFileSync('git', args, { cwd: source, stdio: 'pipe' })
  try {
    write('vendor/cannbot-skills/LICENSE', 'shared license')
    write('plugins-official/LICENSE', 'plugin license')
    for (const id of ['ops-direct-invoke-flash', 'ops-direct-invoke', 'ops-registry-invoke']) {
      write(`plugins-official/${id}/.claude-plugin/plugin.json`, JSON.stringify({ name: id }))
      write(`plugins-official/${id}/skills/${id}/SKILL.md`, `---\nname: ${id}\ndescription: source test\n---\noriginal\n`)
    }
    write('plugins-official/ops-registry-invoke/skills/ops-registry-invoke/skills.json', JSON.stringify({ skills: { native: [], external: [] } }))
    write('harness/a.txt', 'old link target')
    write('harness/b.txt', 'new link target')
    write('script/LICENSE', 'installer license')
    write('script/bin/cannbot.js', '// installer fixture')
    write('script/lib/index.js', '// installer fixture')
    const link = join(source, 'plugins-official/ops-direct-invoke/reference.txt')
    symlinkSync('../../harness/a.txt', link)
    git('init', '--quiet')
    git('add', '.')
    git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', '-c', 'commit.gpgsign=false', 'commit', '--quiet', '-m', 'fixture')
    const script = fileURLToPath(new URL('../scripts/materialize-workflows.mjs', import.meta.url))
    execFileSync(process.execPath, [script, source, join(root, 'first')])
    const first = JSON.parse(readFileSync(join(root, 'first/catalog.json')))
    write('plugins-official/ops-direct-invoke/skills/ops-direct-invoke/SKILL.md', '---\nname: ops-direct-invoke\ndescription: source test\n---\nchanged without committing\n')
    rmSync(link)
    symlinkSync('../../harness/b.txt', link)
    execFileSync(process.execPath, [script, source, join(root, 'second')])
    const second = JSON.parse(readFileSync(join(root, 'second/catalog.json')))
    assert.equal(first.commit, second.commit)
    const firstPrimary = first.exposedSkills.find(item => item.originalName === 'ops-direct-invoke')
    const secondPrimary = second.exposedSkills.find(item => item.originalName === 'ops-direct-invoke')
    assert.notEqual(firstPrimary.hash, secondPrimary.hash)
    assert.equal(readFileSync(join(root, 'second/ops-direct-invoke/reference.txt'), 'utf8'), 'new link target')
    assert.match(readFileSync(join(root, 'second/ops-direct-invoke/skills/ops-direct-invoke/SKILL.md'), 'utf8'), /changed without committing/)
    assert.equal(readFileSync(join(root, 'second/ops-direct-invoke/LICENSE'), 'utf8'), 'plugin license')
    const builder = fileURLToPath(new URL('../scripts/build-workflow-packages.mjs', import.meta.url))
    const output = join(root, 'reports')
    execFileSync(process.execPath, [builder, '--source', source, '--build-root', join(root, 'packages'), '--output', output, '--no-pack', 'true'])
    const defaults = join(root, 'defaults.json')
    writeFileSync(defaults, JSON.stringify({ workflows: [] }))
    const cache = join(root, 'cache')
    execFileSync(process.execPath, [join(resolveSource(), 'node_modules/tsx/dist/cli.mjs'), fileURLToPath(new URL('../scripts/activate-source.ts', import.meta.url)), join(output, 'release-1.0.0-report.json'), defaults, cache])
    const active = JSON.parse(readFileSync(join(cache, 'active.json')))
    assert.match(active.records['ops-direct-invoke'].integrity, /^source:/)
    const installed = join(cache, active.records['ops-direct-invoke'].directory)
    assert.equal(readFileSync(join(installed, 'resources/reference.txt'), 'utf8'), 'new link target')
    assert.match(readFileSync(join(installed, 'resources/skills/ops-direct-invoke/SKILL.md'), 'utf8'), /changed without committing/)
  } finally {
    rmSync(root, { recursive: true, force: true })
  }
})

for (const id of ['ops-registry-invoke']) test(`${id} rejects dependency IDs escaping staging`, () => {
  const root = mkdtempSync(join(tmpdir(), 'cannbot-traversal-test-')), source = join(root, 'source')
  const write = (path, text) => { const file = join(source, path); mkdirSync(join(file, '..'), { recursive: true }); writeFileSync(file, text) }
  try {
    write('README.md', 'source payload')
    write('vendor/cannbot-skills/LICENSE', 'license')
    write('plugins-official/LICENSE', 'license')
    write(`plugins-official/${id}/.claude-plugin/plugin.json`, JSON.stringify({ name: id }))
    write(`plugins-official/${id}/skills/${id}/SKILL.md`, `---\nname: ${id}\ndescription: test\n---\n`)
    write(`plugins-official/${id}/skills/${id}/skills.json`, JSON.stringify({ skills: { native: [], external: ['../../../README.md'] } }))
    const git = (...args) => execFileSync('git', args, { cwd: source, stdio: 'pipe' })
    git('init', '--quiet'); git('add', '.'); git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', '-c', 'commit.gpgsign=false', 'commit', '--quiet', '-m', 'fixture')
    writeFileSync(join(root, 'README.md'), 'must remain unchanged')
    assert.throws(() => execFileSync(process.execPath, [fileURLToPath(new URL('../scripts/materialize-workflows.mjs', import.meta.url)), source, join(root, 'stage')], { stdio: 'pipe' }), /Invalid Skill ID/)
    assert.equal(readFileSync(join(root, 'README.md'), 'utf8'), 'must remain unchanged')
  } finally { rmSync(root, { recursive: true, force: true }) }
})
