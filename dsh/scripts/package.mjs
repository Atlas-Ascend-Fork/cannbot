import { readFile, mkdir, rename, unlink, writeFile } from 'node:fs/promises'
import { randomUUID } from 'node:crypto'
import { join, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { createArtifact, createPackageArtifact } from '../src/remote/artifact.js'
import { acquireFileLock } from '../packages/install/lib/file-lock.mjs'
import { buildCurrent } from './build-current.mjs'

async function atomicWrite(file, content) {
  const temporary = file + '.' + randomUUID() + '.tmp'
  try { await writeFile(temporary, content, { mode: 0o600, flush: true }); await rename(temporary, file) }
  finally { await unlink(temporary).catch(error => { if (error.code !== 'ENOENT') throw error }) }
}
export function updateChecksums(text, name, hash) {
  const entries = new Map()
  for (const line of text.split(/\r?\n/).filter(Boolean)) {
    const match = /^([a-f0-9]{64}) {2}([^/\\]+\.tgz)$/.exec(line)
    if (!match) throw new Error('Existing SHA256SUMS contains an invalid entry; repair it before packaging')
    entries.set(match[2], match[1])
  }
  entries.set(name, hash)
  return [...entries].sort(([left], [right]) => left < right ? -1 : left > right ? 1 : 0).map(([file, digest]) => `${digest}  ${file}\n`).join('')
}
export async function packageCurrent({ root = fileURLToPath(new URL('../', import.meta.url)), short = false, build = buildCurrent, log = console.log } = {}) {
  root = resolve(root)
  if (!short) await build({ root })
  const packageRoot = short ? join(root, 'packages/short') : root
  const manifest = JSON.parse(await readFile(join(packageRoot, 'package.json'), 'utf8'))
  if (!/^(?:@[a-z0-9][a-z0-9._-]*\/)?[a-z0-9][a-z0-9._-]*$/.test(manifest.name ?? '') || !/^\d+\.\d+\.\d+(?:-[a-zA-Z0-9.-]+)?(?:\+[a-zA-Z0-9.-]+)?$/.test(manifest.version ?? '')) throw new Error('Invalid release package name or version')
  const file = `${manifest.name.replace(/^@/, '').replaceAll('/', '-')}-${manifest.version}.tgz`
  const artifact = short ? createPackageArtifact(packageRoot, { licensePath: join(root, '../LICENSE') }) : createArtifact(root)
  const dist = join(root, 'dist')
  await mkdir(dist, { recursive: true })
  const release = await acquireFileLock(join(dist, '.package.lock'), 20 * 60_000)
  try {
    const sums = join(dist, 'SHA256SUMS')
    const previous = await readFile(sums, 'utf8').catch(error => { if (error.code === 'ENOENT') return ''; throw error })
    const next = updateChecksums(previous, file, artifact.hash)
    await atomicWrite(join(dist, file), artifact.bytes)
    await atomicWrite(sums, next)
  } finally { release() }
  log(`Packed ${file} (${artifact.hash})`)
  return { file: join(dist, file), hash: artifact.hash }
}

if (process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === import.meta.url) {
  try {
    if (process.argv.slice(2).some(arg => arg !== '--short')) throw new Error('Usage: node scripts/package.mjs [--short]')
    await packageCurrent({ short: process.argv.includes('--short') })
  } catch (error) { console.error(error.message); process.exitCode = 1 }
}
