import { withStaging } from './staging.mjs'
import { runProcess } from '../src/process-runner.mjs'
import { mkdirSync, readFileSync, writeFileSync, cpSync } from 'node:fs'
import { createHash } from 'node:crypto'
import { resolve, join } from 'node:path'
import { project, resolveSource } from './source.mjs'
const source = resolveSource()
const packageRoot = process.argv.includes('--short') ? join(project, 'packages/short') : project
mkdirSync(join(project, 'dist'), { recursive: true })
const manifest = JSON.parse(readFileSync(join(packageRoot, 'package.json'), 'utf8'))
const file = `${manifest.name.replace(/^@/, '').replaceAll('/', '-')}-${manifest.version}.tgz`
// Stage only the declared release inputs so npm need not traverse isolated
// acceptance runtimes or upstream checkouts beside the project.
await withStaging('cannbot-pack-', async (stage, signal) => {
  for (const path of ['package.json', ...manifest.files]) cpSync(path === 'LICENSE' ? join(project, '../LICENSE') : join(packageRoot, path), join(stage, path), { recursive: true })
  await runProcess(process.execPath, [resolve(source, 'node_modules/pnpm/bin/pnpm.mjs'), 'pack', '--out', join(project, 'dist', file)], {
    cwd: stage, stdio: 'inherit', signal,
  })
})
const sha = createHash('sha256').update(readFileSync(join(project, 'dist', file))).digest('hex')
writeFileSync(join(project, 'dist/SHA256SUMS'), `${sha}  ${file}\n`)
