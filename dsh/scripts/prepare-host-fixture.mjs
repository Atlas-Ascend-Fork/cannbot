/** Copy published dependency packages read-only into an isolated Host-test install. */
import { cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, realpathSync, symlinkSync, writeFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

export function prepareHostFixture(installedPackage, project = fileURLToPath(new URL('../', import.meta.url))) {
  const installed = realpathSync(installedPackage)
  const require = createRequire(join(installed, 'package.json'))
  const catalogFile = realpathSync(require.resolve('@cannbot-plugin/workflow-catalog/package.json'))
  const catalog = JSON.parse(readFileSync(catalogFile, 'utf8'))
  const dependencies = createRequire(catalogFile)
  const base = join(project, '_scratch', 'acceptance-host-published')
  mkdirSync(base, { recursive: true })
  const fixture = mkdtempSync(join(base, 'fixture-')), host = join(fixture, 'host')
  mkdirSync(host)
  const manifest = JSON.parse(readFileSync(join(project, 'package.json'), 'utf8'))
  for (const path of ['package.json', ...manifest.files]) {
    const source = path === 'LICENSE' && !existsSync(join(project, path)) ? join(project, '..', 'LICENSE') : join(project, path)
    cpSync(source, join(host, path), { recursive: true, dereference: true })
  }
  const modules = join(host, 'node_modules'), packages = join(modules, '@cannbot-plugin')
  mkdirSync(packages, { recursive: true })
  cpSync(dirname(catalogFile), join(packages, 'workflow-catalog'), { recursive: true, dereference: true })
  const versions = []
  for (const entry of catalog.cannbotWorkflowCatalog.workflows.filter(item => item.default)) {
    const file = realpathSync(dependencies.resolve(entry.package + '/package.json'))
    const data = JSON.parse(readFileSync(file, 'utf8'))
    cpSync(dirname(file), join(packages, entry.package.slice('@cannbot-plugin/'.length)), { recursive: true, dereference: true })
    versions.push({ package: data.name, version: data.version })
  }
  for (const name of ['@deepseek-ai', 'pacote']) symlinkSync(realpathSync(join(project, 'node_modules', name)), join(modules, name), process.platform === 'win32' ? 'junction' : 'dir')
  writeFileSync(join(fixture, 'provenance.json'), JSON.stringify({ kind: 'published-packages', catalogVersion: catalog.version, workflows: versions }, null, 2) + '\n')
  return { host, fixture, catalogVersion: catalog.version, workflows: versions }
}

if (process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === import.meta.url) {
  try {
    if (process.argv[2] !== '--installed-package' || !process.argv[3] || process.argv.length !== 4) throw new Error('Usage: node scripts/prepare-host-fixture.mjs --installed-package <installed-main-package>')
    console.log(JSON.stringify(prepareHostFixture(process.argv[3])))
  } catch (error) { console.error(error.message); process.exitCode = 1 }
}
