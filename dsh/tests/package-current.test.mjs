import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { dirname, join, resolve } from 'node:path'
import { gunzipSync } from 'node:zlib'
import { packageCurrent, updateChecksums } from '../scripts/package.mjs'
import { inside } from '../scripts/build-bootstrap.mjs'
import { createArtifact } from '../src/remote/artifact.js'

const owner = resolve('.acceptance-package-current-tests')
const put = async (root, path, text) => { const file = join(root, path); await mkdir(dirname(file), { recursive: true }); await writeFile(file, text) }
async function fixture(t) {
  await mkdir(owner, { recursive: true })
  const base = await mkdtemp(join(owner, 'case-')), root = join(base, 'dsh')
  t.after(async () => { assert(inside(owner, base)); await rm(base, { recursive: true, force: true }) })
  await put(base, 'LICENSE', 'repository license')
  await put(root, 'package.json', JSON.stringify({ name: '@cannbot-plugin/cannbot-dsh', version: '1.0.0-alpha.1', files: ['lib', 'remote', 'LICENSE', 'README.md'] }))
  await put(root, 'remote/deploy-package.mjs', '// deployment source')
  await put(root, 'README.md', 'main package')
  await put(root, 'packages/short/package.json', JSON.stringify({ name: 'cannbot-dsh', version: '1.0.0-alpha.1', files: ['README.md', 'LICENSE'], dependencies: { '@cannbot-plugin/cannbot-dsh': '1.0.0-alpha.1' } }))
  await put(root, 'packages/short/README.md', 'short package')
  let builds = 0
  const build = async ({ root: received }) => { assert.equal(received, root); builds++; await put(root, 'lib/index.js', 'export {}'); await put(root, 'lib/client.js', 'factory'); await put(root, 'lib/.cannbot-build.json', '{"hash":"fixture"}') }
  return { root, build, builds: () => builds, options: { root, build, log() {} } }
}
function entries(archive) {
  const bytes = gunzipSync(archive), result = new Map(); let offset = 0
  while (offset + 512 <= bytes.length && bytes[offset]) {
    const header = bytes.subarray(offset, offset + 512)
    const string = (at, count) => header.subarray(at, at + count).toString().replace(/\0.*$/s, '')
    const name = [string(345, 155), string(0, 100)].filter(Boolean).join('/'), size = Number.parseInt(string(124, 12).trim(), 8)
    result.set(name, bytes.subarray(offset + 512, offset + 512 + size).toString())
    offset += 512 + Math.ceil(size / 512) * 512
  }
  return result
}

test('main packaging builds current source and writes the identical deployable archive', async t => {
  const f = await fixture(t), result = await packageCurrent(f.options)
  assert.equal(f.builds(), 1)
  const packed = await readFile(result.file)
  assert.deepEqual(packed, createArtifact(f.root).bytes)
  const files = entries(packed)
  assert(files.has('package/lib/index.js')); assert(files.has('package/lib/.cannbot-build.json'))
  assert.equal(files.get('package/LICENSE'), 'repository license')
  assert(![...files.keys()].some(name => /node_modules|DSH_SOURCE|build-cache/.test(name)))
})

test('short packaging requires no DSH checkout, build tools or main lib and includes parent license', async t => {
  const f = await fixture(t)
  const result = await packageCurrent({ ...f.options, short: true, build: async () => assert.fail('short package must not build') })
  const files = entries(await readFile(result.file))
  assert.equal(files.get('package/LICENSE'), 'repository license')
  assert.equal(JSON.parse(files.get('package/package.json')).name, 'cannbot-dsh')
  assert.equal(f.builds(), 0)
})

test('main and short packaging preserve both checksum lines and repeat deterministically', async t => {
  const f = await fixture(t)
  const main = await packageCurrent(f.options), short = await packageCurrent({ ...f.options, short: true })
  const before = await readFile(join(f.root, 'dist/SHA256SUMS'), 'utf8')
  assert.equal(before.trim().split('\n').length, 2)
  assert(before.includes(main.hash)); assert(before.includes(short.hash))
  const repeated = await packageCurrent(f.options)
  assert.equal(main.hash, repeated.hash)
  assert.equal(await readFile(join(f.root, 'dist/SHA256SUMS'), 'utf8'), before)
})

test('parallel main/short packaging serializes checksum updates without dropping either package', async t => {
  const f = await fixture(t)
  await Promise.all([packageCurrent(f.options), packageCurrent({ ...f.options, short: true })])
  assert.equal((await readFile(join(f.root, 'dist/SHA256SUMS'), 'utf8')).trim().split('\n').length, 2)
})

test('compiler failure cannot publish a main artifact or claim successful packaging', async t => {
  const f = await fixture(t)
  await assert.rejects(packageCurrent({ ...f.options, build: async () => { throw new Error('compile failed') } }), /compile failed/)
  await assert.rejects(readFile(join(f.root, 'dist/SHA256SUMS')), error => error.code === 'ENOENT')
})

test('checksum update replaces only the selected filename and rejects malformed existing lines', () => {
  const a = 'a'.repeat(64), b = 'b'.repeat(64), c = 'c'.repeat(64)
  assert.equal(updateChecksums(`${a}  main.tgz\n${b}  short.tgz\n`, 'main.tgz', c), `${c}  main.tgz\n${b}  short.tgz\n`)
  assert.throws(() => updateChecksums('not a checksum\n', 'main.tgz', a), /invalid entry/)
})
