/** Build one or all independent, resource-only workflow packages from a verified source snapshot. */
import { cpSync, existsSync, mkdirSync, mkdtempSync, rmSync, readFileSync, readdirSync, unlinkSync, writeFileSync } from 'node:fs'
import { createHash } from 'node:crypto'
import { createRequire } from 'node:module'
import { basename, dirname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { tmpdir } from 'node:os'
import { spawnSync } from 'node:child_process'
const root = fileURLToPath(new URL('..', import.meta.url))
const options = Object.fromEntries(process.argv.slice(2).reduce((items, arg, i, all) => arg.startsWith('--') ? [...items, [arg.slice(2), all[i + 1]]] : items, []))
const version = options.version ?? '1.0.0', catalogVersion = options['catalog-version'] ?? '1.0.0'
if (!/^\d+\.\d+\.\d+$/.test(version) || !/^\d+\.\d+\.\d+$/.test(catalogVersion)) throw new Error('Use a stable x.y.z version')
const source = resolve(options.source ?? join(root, '..'))
// Always assemble current source; resource copies never live in the adapter repository.
const temporary = mkdtempSync(join(tmpdir(), 'cannbot-workflows-'))
process.on('exit', () => rmSync(temporary, { recursive: true, force: true }))
const assets = join(temporary, 'official')
const built = spawnSync(process.execPath, [join(root, 'scripts/materialize-workflows.mjs'), source, assets], { stdio: 'inherit' })
if (built.status !== 0) process.exit(built.status ?? 1)
const catalog = JSON.parse(readFileSync(join(assets, 'catalog.json'), 'utf8'))
const defaults = JSON.parse(readFileSync(join(root, 'workflow-defaults.json'), 'utf8'))
// workflow-defaults.json is the source of truth for which workflows this build ships:
// workflows absent from it are neither packaged nor listed in the catalog.
const shipped = new Set(defaults.workflows.map(item => item.id))
for (const id of shipped) if (!catalog.plugins.some(item => item.id === id)) throw new Error(`Default workflow is not available in source: ${id}`)
catalog.plugins = catalog.plugins.filter(item => shipped.has(item.id))
const require = createRequire(import.meta.url)
const { parse } = (()=>{try{return require('yaml')}catch{return createRequire(require.resolve('@deepseek-ai/dsh-skill-filesystem/package.json'))('yaml')}})()
const dist = resolve(options.output ?? join(root, 'dist/workflow-releases'))
mkdirSync(dist, { recursive: true })
writeFileSync(join(dist, 'source-catalog.json'), JSON.stringify(catalog, null, 2) + '\n')
const workspace = resolve(options['build-root'] ?? join(root, 'dist/workflow-packages'))
const npmCli = [process.env.npm_execpath, resolve(process.execPath,'../node_modules/npm/bin/npm-cli.js'), '/usr/share/nodejs/npm/bin/npm-cli.js', '/usr/lib/node_modules/npm/bin/npm-cli.js'].find(value=>value&&existsSync(value));
if(!npmCli)throw new Error('Use a Node.js installation with npm to build workflow packages')
const hashTree = path => {
  const hash = createHash('sha256')
  function walk(value) {
    for (const item of readdirSync(value, { withFileTypes: true }).sort((a, b) => a.name < b.name ? -1 : a.name > b.name ? 1 : 0)) {
      const file = join(value, item.name)
      if (item.isDirectory()) walk(file)
      else { hash.update(relative(path, file).split('\\').join('/')); hash.update('\0'); hash.update(readFileSync(file)); hash.update('\0') }
    }
  }
  walk(path); return hash.digest('hex')
}
const reports = []
function pack(directory, manifest) {
  if (options['no-pack'] === 'true') { reports.push({ name: manifest.name, version: manifest.version, directory }); return }
  const tarball = join(dist, `${manifest.name.replace(/^@/, '').replaceAll('/', '-')}-${manifest.version}.tgz`)
  const result = spawnSync(process.execPath, [npmCli, 'pack', '--ignore-scripts', '--json', '--pack-destination', dist, '--loglevel=error', '--logs-max=0'], { cwd: directory, encoding: 'utf8', maxBuffer: 4e6 })
  if (result.status !== 0) throw new Error(result.stderr || result.stdout)
  const bytes = readFileSync(tarball)
  const report = { name: manifest.name, version: manifest.version, directory, tarball, bytes: bytes.length, sha256: createHash('sha256').update(bytes).digest('hex'), integrity: 'sha512-' + createHash('sha512').update(bytes).digest('base64') }
  reports.push(report); console.log(JSON.stringify(report))
}
for (const plugin of catalog.plugins) {
  if (options['catalog-only'] === 'true') continue
  if (options.id && options.id !== plugin.id) continue
  if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(plugin.id)) throw new Error('Invalid workflow id')
  const name = `@cannbot-plugin/workflow-${plugin.id}`
  const directory = join(workspace, 'packages', plugin.id, version)
  if (existsSync(directory)) throw new Error(`Build directory exists; preserve the previous artifact: ${directory}`)
  mkdirSync(directory, { recursive: true })
  const resources = join(directory, 'resources')
  cpSync(join(assets, plugin.id), resources, { recursive: true })
  const skills = readdirSync(join(resources, 'skills'), { withFileTypes: true }).filter(item => item.isDirectory() && existsSync(join(resources, 'skills', item.name, 'SKILL.md'))).map(item => {
    const content = readFileSync(join(resources, 'skills', item.name, 'SKILL.md'), 'utf8')
    const frontmatter = /^\uFEFF?---\r?\n([\s\S]*?)\r?\n---/.exec(content)
    if (!frontmatter) throw new Error(`Missing Skill metadata: ${item.name}`)
    const info = parse(frontmatter[1])
    return { name: info.name, path: `skills/${item.name}/SKILL.md`, hash: hashTree(join(resources, 'skills', item.name)), entry: info.name === plugin.id }
  })
  const upstreamManifest = join(resources, '.claude-plugin/plugin.json')
  const initialization = existsSync(upstreamManifest) ? { kind: 'cannbot-cli', entry: 'upstream/bin/cannbot.js' } : { kind: 'skill-native' }
  if (existsSync(upstreamManifest)) {
    const manifest = JSON.parse(readFileSync(upstreamManifest, 'utf8'))
    manifest.skills = skills.map(item => './' + dirname(item.path).split('\\').join('/'))
    delete manifest.dependencies
    writeFileSync(upstreamManifest, JSON.stringify(manifest, null, 2) + '\n')
    // Like the upstream npm assembler, sealed packages use packaged resources,
    // not source-only Git/submodule definitions. The installer itself is unchanged.
    const sourceDefinition = join(resources, 'plugin-sources.json')
    if (existsSync(sourceDefinition)) unlinkSync(sourceDefinition)
    mkdirSync(join(directory, 'upstream/bin'), { recursive: true })
    cpSync(join(source, 'script/bin/cannbot.js'), join(directory, 'upstream/bin/cannbot.js'))
    cpSync(join(source, 'script/lib'), join(directory, 'upstream/lib'), { recursive: true })
    writeFileSync(join(directory, 'upstream/package.json'), JSON.stringify({ name, version, type: 'module', license: 'MIT' }, null, 2) + '\n')
    cpSync(join(source, 'script/LICENSE'), join(directory, 'upstream/LICENSE'))
  }
  const contentHash = hashTree(directory)
  const descriptor = { contentHash, schemaVersion: 1, id: plugin.id, title: plugin.title, version, initialization, skills, source: { repository: catalog.repository, commit: catalog.commit, skillsCommit: catalog.skillsCommit } }
  const manifest = { name, version, description: `CANNBot ${plugin.title}: independently versioned workflow resources for CANNBot DSH`, type: 'module', license: 'SEE LICENSE IN resources/LICENSE', files: ['resources', 'workflow.json', 'README.md', ...initialization.kind === 'cannbot-cli' ? ['upstream'] : []], engines: { node: '>=24.9.0' }, publishConfig: { access: 'public', registry: 'https://registry.npmjs.org/' }, cannbotWorkflow: { schemaVersion: 1, id: plugin.id }, repository: { type: 'git', url: catalog.repository, directory: `plugins-official/${plugin.id}` } }
  writeFileSync(join(directory, 'package.json'), JSON.stringify(manifest, null, 2) + '\n')
  writeFileSync(join(directory, 'workflow.json'), JSON.stringify(descriptor, null, 2) + '\n')
  writeFileSync(join(directory, 'README.md'), `# ${plugin.title}\n\nIndependent workflow package: \`${name}@${version}\`.\n\nInstall and update it from CANNBot DSH workflow management. The source CANNBot installer is preserved and invoked with its DSH target; npm lifecycle scripts are not used.\n\nSource: ${catalog.repository}\nCANNBot: ${catalog.commit}\nSkills: ${catalog.skillsCommit}\n`)
  pack(directory, manifest)
}
if (options.id && !reports.length) throw new Error('Workflow was not found')
if (!options.id || options.catalog === 'true') {
  const directory = join(workspace, 'catalog', catalogVersion)
  if (existsSync(directory)) throw new Error(`Catalog build directory exists: ${directory}`)
  mkdirSync(directory, { recursive: true })
  const workflows = catalog.plugins.map(plugin => ({ id: plugin.id, title: plugin.title, package: `@cannbot-plugin/workflow-${plugin.id}`, default: defaults.workflows.find(item => item.id === plugin.id)?.default ?? true }))
  const manifest = { name: '@cannbot-plugin/workflow-catalog', version: catalogVersion, description: 'Discover and install independently versioned CANNBot DSH workflows', license: 'MIT', files: ['catalog.json', 'README.md', 'LICENSE'], dependencies: Object.fromEntries(workflows.filter(item => item.default).map(item => [item.package, '>=1.0.0'])), publishConfig: { access: 'public', registry: 'https://registry.npmjs.org/' }, cannbotWorkflowCatalog: { schemaVersion: 1, workflows } }
  writeFileSync(join(directory, 'package.json'), JSON.stringify(manifest, null, 2) + '\n')
  writeFileSync(join(directory, 'catalog.json'), JSON.stringify(manifest.cannbotWorkflowCatalog, null, 2) + '\n')
  writeFileSync(join(directory, 'README.md'), '# CANNBot workflow catalog\n\nOnly republish this small catalog when workflows are added or discovery metadata changes. Updating an existing workflow requires publishing only that workflow package.\n')
  writeFileSync(join(directory, 'LICENSE'), readFileSync(join(source, 'script/LICENSE')))
  pack(directory, manifest)
}
writeFileSync(join(dist, options.id ? `${options.id}-${version}-report.json` : `release-${version}-report.json`), JSON.stringify(reports, null, 2) + '\n')
