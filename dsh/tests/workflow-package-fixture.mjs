import { mkdtempSync, mkdirSync, readFileSync } from 'node:fs'
import { resolve, join } from 'node:path'
import { createRequire } from 'node:module'
import { ContentManager } from '../src/content-manager.ts'
const pacote = createRequire(import.meta.url)('pacote')
export async function createVerifiedWorkflowCache() {
  const reports = JSON.parse(readFileSync(new URL('../dist/workflow-releases/release-1.0.0-report.json', import.meta.url), 'utf8'))
  mkdirSync('.acceptance-workflow-tests', { recursive: true })
  const root = mkdtempSync(resolve('.acceptance-workflow-tests/real-')), cache = join(root, 'cache'), workspace = join(root, 'workspace')
  mkdirSync(workspace)
  const manifest = report => ({ ...JSON.parse(readFileSync(join(report.directory, 'package.json'), 'utf8')), dist: { integrity: report.integrity, tarball: `https://registry.npmjs.org/${report.name}/-/${report.version}.tgz` } })
  const fetcher = {
    async manifest(spec) { const report = reports.find(item => spec === `${item.name}@latest` || spec === `${item.name}@${item.version}`); if (!report) throw new Error('Unknown fixture package'); return manifest(report) },
    async extract(spec, destination, options) { const report = reports.find(item => manifest(item).dist.tarball === spec); if (!report) throw new Error('Unknown fixture tarball'); return pacote.extract(report.tarball, destination, options) },
  }
  const manager = new ContentManager(resolve('workflow-defaults.json'), cache, fetcher)
  await manager.sync()
  return { root, cache, workspace, manager }
}
