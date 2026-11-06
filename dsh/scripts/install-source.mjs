import { withStaging } from './staging.mjs'
import { runProcess } from '../src/process-runner.mjs'
/** Assemble current repository resources at installation time, outside the adapter source tree. */
import { cpSync, existsSync, mkdirSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { join, resolve } from 'node:path'
import { project, resolveSource } from './source.mjs'

const args = process.argv.slice(2)
if (args.includes('--help')) {
  console.log('node scripts/install-source.mjs [--source /path/to/cannbot | --repository GitURL] [--profile web]\nDefaults to the current parent repository, including uncommitted edits. A remote repository is freshly cloned with its declared submodules. DSH_HOME and CANNBOT_DSH_WORKFLOW_ROOT are honored.')
  process.exit(0)
}
const options = {}
for (let i = 0; i < args.length; i += 2) {
  if (!['--source', '--repository', '--profile'].includes(args[i]) || !args[i + 1] || args[i + 1].startsWith('--')) throw new Error(`Invalid option: ${args[i]}`)
  options[args[i].slice(2)] = args[i + 1]
}
if (options.source && options.repository) throw new Error('Choose --source or --repository')
const checkout = resolveSource()
const home = resolve(process.env.DSH_HOME ?? join(homedir(), '.dsh'))
const cache = resolve(process.env.CANNBOT_DSH_WORKFLOW_ROOT ?? join(home, 'cannbot-dsh-workflows'))
await withStaging('cannbot-source-install-', async (temporary, signal) => {
  const run = (command, args) => runProcess(command, args, { cwd: project, stdio: 'inherit', signal, env: { ...process.env, TMPDIR: temporary } })
  let source = resolve(options.source ?? join(project, '..'))
  if (options.repository) {
    source = join(temporary, 'source')
    await run('git', ['clone', '--depth', '1', '--recurse-submodules', '--shallow-submodules', '--', options.repository, source])
  }
  // Generate all resources before changing the installed plugin or active workflows.
  const pkg = JSON.parse(readFileSync(join(project, 'package.json'), 'utf8'))
  const catalogRange = pkg.dependencies?.['@cannbot-plugin/workflow-catalog'] ?? '1.0.0'
  const catalogVersion = catalogRange.replace(/^[\^~]/, '')
  if (!/^\d+\.\d+\.\d+$/.test(catalogVersion)) throw new Error(`Unsupported workflow catalog range: ${catalogRange}`)
  const output = join(temporary, 'reports')
  await run(process.execPath, [join(project, 'scripts/build-workflow-packages.mjs'), '--source', source, '--build-root', join(temporary, 'packages'), '--output', output, '--no-pack', 'true', '--catalog-version', catalogVersion])
  await run(process.execPath, [join(project, 'scripts/build.mjs')])
  await run(process.execPath, [join(project, 'scripts/package.mjs')])
  const profile = options.profile ?? 'web'
  const profileDir = join(home, 'profiles', profile)
  const archive = join(project, 'dist', `${pkg.name.replace(/^@/, '').replaceAll('/', '-')}-${pkg.version}.tgz`)
  await run('dsh', ['plugin', '--profile', profile, 'add', archive, '--force'])
  // pnpm keeps the previously linked files when the package version is unchanged, so the
  // rebuilt archive must replace the installed copy before the profile is relinked.
  rmSync(join(profileDir, 'node_modules', ...pkg.name.split('/')), { recursive: true, force: true })
  await run('dsh', ['plugin', '--profile', profile, 'install', '--force'])
  // Ship the catalog assembled from this source tree: the registry catalog lists workflows
  // this build does not contain, and the runtime reads whichever catalog is installed.
  const reports = JSON.parse(readFileSync(join(output, 'release-1.0.0-report.json'), 'utf8'))
  const catalog = reports.find(item => item.name === '@cannbot-plugin/workflow-catalog')
  if (!catalog) throw new Error('Source build did not produce a workflow catalog')
  const installedCatalog = join(profileDir, 'node_modules/@cannbot-plugin/workflow-catalog')
  rmSync(installedCatalog, { recursive: true, force: true })
  cpSync(catalog.directory, installedCatalog, { recursive: true })
  mkdirSync(cache, { recursive: true })
  await run(process.execPath, [join(checkout, 'node_modules/tsx/dist/cli.mjs'), join(project, 'scripts/activate-source.ts'), join(output, 'release-1.0.0-report.json'), join(project, 'workflow-defaults.json'), cache])
  // Earlier installs leave entries and copies behind; a source install keeps exactly the declared workflows.
  const activeFile = join(cache, 'active.json')
  if (existsSync(activeFile)) {
    const index = JSON.parse(readFileSync(activeFile, 'utf8'))
    const defaults = JSON.parse(readFileSync(join(project, 'workflow-defaults.json'), 'utf8'))
    const keep = new Set(defaults.workflows.map(item => item.id))
    const dropped = index.entries.filter(item => !keep.has(item.id))
    index.entries = index.entries.filter(item => keep.has(item.id))
    for (const id of Object.keys(index.records)) if (!keep.has(id)) delete index.records[id]
    for (const id of Object.keys(index.history ?? {})) if (!keep.has(id)) delete index.history[id]
    index.pinned = (index.pinned ?? []).filter(id => keep.has(id))
    if (dropped.length) writeFileSync(activeFile, JSON.stringify(index, null, 2))
    for (const item of dropped) rmSync(join(cache, 'packages', item.id), { recursive: true, force: true })
    for (const id of keep) {
      const directory = join(cache, 'packages', id)
      if (!existsSync(directory)) continue
      const current = index.records[id]?.directory
      for (const entry of readdirSync(directory)) if (`packages/${id}/${entry}` !== current) rmSync(join(directory, entry), { recursive: true, force: true })
    }
  }
  console.log('Source installation complete. Restart DSH to load the rebuilt plugin.')
})
