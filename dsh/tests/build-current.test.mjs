import test from 'node:test'
import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { crc32, deflateRawSync } from 'node:zlib'
import { access, cp, mkdir, mkdtemp, readFile, readdir, rm, symlink, writeFile } from 'node:fs/promises'
import { dirname, join, resolve } from 'node:path'
import { buildCurrent, buildInputHash, BUILD_RECEIPT, currentBuildStatus } from '../scripts/build-current.mjs'
import { buildCache, DSH_BUILD_TAG, DSH_BUILD_VERSION, DSH_SOURCE_URL, ensureMinimalToolchain, inside, minimalToolManifest, resolveBuildSource } from '../scripts/build-bootstrap.mjs'
import { extractSourceZip } from '../scripts/build-archive.mjs'

const testRoot = resolve('.acceptance-build-current-tests')
const put = async (root, path, content) => { const file = join(root, path); await mkdir(dirname(file), { recursive: true }); await writeFile(file, content); return file }
const exists = async path => { try { await access(path); return true } catch { return false } }
const quiet = () => {}
async function fixture(t) {
  await mkdir(testRoot, { recursive: true })
  const root = await mkdtemp(join(testRoot, 'case-'))
  t.after(async () => { assert(inside(testRoot, root)); await rm(root, { recursive: true, force: true }) })
  await put(root, 'package.json', JSON.stringify({ name: 'plugin', version: '1.0.0', type: 'module', devDependencies: { yaml: '^2.4.2', '@xterm/xterm': '6.0.0' } }))
  for (const path of ['src/index.ts', 'src/client/index.ts', 'src/client/theme.css', 'remote/bootstrap.sh', 'scripts/build.mjs', 'packages/install/lib/file-lock.mjs', 'tsdown.config.ts', 'tsconfig.json', 'locale/zh-CN.json']) await put(root, path, '// initial')
  let builds = 0, tools = 0
  const run = async () => { builds++; await put(root, 'lib/index.js', `export const version = ${builds}`); await put(root, 'lib/client.js', `window.__ModuleLoader__.load({version:${builds}})`); await put(root, 'lib/chunk.js', 'chunk') }
  return { root, run, builds: () => builds, tools: () => tools, options: { root, run, log: quiet, ensureTools: async () => { tools++; return 'fixed-source' } } }
}

test('builds unstamped source once and reuses only matching source and output hashes', async t => {
  const f = await fixture(t)
  assert.equal((await buildCurrent(f.options)).rebuilt, true)
  const original = await readFile(join(f.root, BUILD_RECEIPT), 'utf8')
  assert.equal((await buildCurrent(f.options)).rebuilt, false)
  assert.equal(f.builds(), 1); assert.equal(f.tools(), 1)
  assert.equal(await readFile(join(f.root, BUILD_RECEIPT), 'utf8'), original)
  assert(!original.includes(f.root)); assert(!original.includes('builtAt'))
})

test('source, CSS, remote scripts, build configuration and imported install helper all invalidate receipt', async t => {
  const f = await fixture(t)
  await buildCurrent(f.options)
  for (const path of ['src/index.ts', 'src/client/theme.css', 'remote/bootstrap.sh', 'scripts/build.mjs', 'tsdown.config.ts', 'packages/install/lib/file-lock.mjs', 'package.json']) {
    const before = await buildInputHash(f.root)
    await put(f.root, path, await readFile(join(f.root, path), 'utf8') + ' ')
    assert.notEqual(await buildInputHash(f.root), before, path)
    assert.equal((await buildCurrent(f.options)).rebuilt, true, path)
  }
})

test('a damaged or missing compiled chunk rebuilds even with unchanged source', async t => {
  const f = await fixture(t)
  await buildCurrent(f.options)
  await put(f.root, 'lib/chunk.js', 'corrupt')
  assert.equal((await buildCurrent(f.options)).rebuilt, true)
  await rm(join(f.root, 'lib/client.js'))
  assert.equal((await buildCurrent(f.options)).rebuilt, true)
  assert.equal(f.builds(), 3)
})

test('a prebuilt release copied to another directory reuses its deterministic receipt offline', async t => {
  const f = await fixture(t), copy = await fixture(t)
  await buildCurrent(f.options)
  await cp(join(f.root, 'lib'), join(copy.root, 'lib'), { recursive: true })
  const result = await buildCurrent({ ...copy.options, ensureTools: async () => assert.fail('prebuilt release must not bootstrap') })
  assert.equal(result.rebuilt, false); assert.equal(copy.builds(), 0)
})

test('--check is read-only and missing or malformed receipts do not bless old lib', async t => {
  const f = await fixture(t)
  await f.run()
  assert.equal((await buildCurrent({ ...f.options, check: true })).current, false)
  assert.equal(await exists(join(f.root, '.build-cache')), false)
  assert.equal(f.tools(), 0)
  await put(f.root, BUILD_RECEIPT, '{broken')
  assert.equal((await buildCurrent(f.options)).rebuilt, true)
})

test('failed rebuild restores old generated files but exits unsuccessfully and invalidates receipt', async t => {
  const f = await fixture(t)
  await buildCurrent(f.options)
  const previous = await readFile(join(f.root, 'lib/index.js'), 'utf8')
  await assert.rejects(buildCurrent({ ...f.options, force: true, run: async () => { await put(f.root, 'lib/index.js', 'partial'); throw new Error('compiler error') } }), /compiler error/)
  assert.equal(await readFile(join(f.root, 'lib/index.js'), 'utf8'), previous)
  assert.equal(await exists(join(f.root, BUILD_RECEIPT)), false)
  assert.equal((await currentBuildStatus(f.root)).current, false)
  assert.equal((await buildCurrent(f.options)).rebuilt, true)
})

test('incomplete output and edits during a build cannot receive a successful receipt', async t => {
  const f = await fixture(t)
  await assert.rejects(buildCurrent({ ...f.options, run: () => put(f.root, 'lib/index.js', 'only host') }), /both Host and Client/)
  assert.equal(await exists(join(f.root, BUILD_RECEIPT)), false)
  await assert.rejects(buildCurrent({ ...f.options, run: async () => { await f.run(); await put(f.root, 'src/index.ts', '// edited during build') } }), /changed during/)
  assert.equal(await exists(join(f.root, BUILD_RECEIPT)), false)
})

test('simultaneous installers serialize the compiler and recheck after acquiring the lock', async t => {
  const f = await fixture(t)
  const results = await Promise.all([buildCurrent(f.options), buildCurrent(f.options)])
  assert.equal(results.filter(value => value.rebuilt).length, 1)
  assert.equal(f.builds(), 1)
})

test('lib and cache junctions outside their owner are refused without changing targets', async t => {
  const f = await fixture(t), outside = await fixture(t), type = process.platform === 'win32' ? 'junction' : 'dir'
  await put(outside.root, 'index.js', 'keep')
  await symlink(outside.root, join(f.root, 'lib'), type)
  await assert.rejects(buildCurrent(f.options), /symbolic links|unmanaged lib/)
  assert.equal(await readFile(join(outside.root, 'index.js'), 'utf8'), 'keep')
  const cached = await fixture(t)
  await symlink(outside.root, join(cached.root, '.build-cache'), type)
  await assert.rejects(buildCache(cached.root), /inside this source checkout/)
})

function zip(entries) {
  const data = [], directory = []; let offset = 0
  for (const { name, body = '', mode = 0o100644, corrupt = false, method = 8 } of entries) {
    const file = Buffer.from(name), bytes = Buffer.from(body), encoded = method === 0 ? bytes : deflateRawSync(bytes), crc = crc32(bytes) ^ (corrupt ? 1 : 0)
    const local = Buffer.alloc(30)
    local.writeUInt32LE(0x04034b50); local.writeUInt16LE(method, 8); local.writeUInt32LE(crc >>> 0, 14); local.writeUInt32LE(encoded.length, 18); local.writeUInt32LE(bytes.length, 22); local.writeUInt16LE(file.length, 26)
    data.push(local, file, encoded)
    const central = Buffer.alloc(46)
    central.writeUInt32LE(0x02014b50); central.writeUInt16LE(method, 10); central.writeUInt32LE(crc >>> 0, 16); central.writeUInt32LE(encoded.length, 20); central.writeUInt32LE(bytes.length, 24); central.writeUInt16LE(file.length, 28); central.writeUInt32LE((mode << 16) >>> 0, 38); central.writeUInt32LE(offset, 42)
    directory.push(central, file); offset += local.length + file.length + encoded.length
  }
  const central = Buffer.concat(directory), end = Buffer.alloc(22)
  end.writeUInt32LE(0x06054b50); end.writeUInt16LE(entries.length, 8); end.writeUInt16LE(entries.length, 10); end.writeUInt32LE(central.length, 12); end.writeUInt32LE(offset, 16)
  return Buffer.concat([...data, central, end])
}
function sourceFiles(version = DSH_BUILD_VERSION) {
  return [
    { name: 'source/package.json', body: JSON.stringify({ name: '@deepseek-ai/dsh-root', version, packageManager: 'pnpm@11.28.5', devDependencies: { tsdown: '^0.22.2', lightningcss: '^1.33.0', typescript: '^6.0.3', zod: '^4.4.3' } }) },
    { name: 'source/packages/client/tsdown.client.ts', body: '// official preset fixture' },
    { name: 'source/packages/client/ui-plugin-manager/package.json', body: JSON.stringify({ name: '@deepseek-ai/dsh-client-ui-plugin-manager', devDependencies: { react: '^18.2.0', 'react-dom': '^18.2.0', clsx: '^2.1.1' } }) },
  ]
}

test('ZIP extraction handles regular UTF-8 files and skips POSIX fixture symlinks on Windows', async t => {
  const f = await fixture(t), destination = join(f.root, 'archive')
  await extractSourceZip(zip([...sourceFiles(), { name: 'source/目录/说明.txt', body: '源码', method: 0 }, { name: 'source/fixture-link', mode: 0o120777, body: '../outside' }]), destination)
  assert.equal(await readFile(join(destination, '目录/说明.txt'), 'utf8'), '源码')
  assert.equal(await exists(join(destination, 'fixture-link')), false)
  assert.equal(JSON.parse(await readFile(join(destination, 'package.json'), 'utf8')).version, DSH_BUILD_VERSION)
})

test('ZIP traversal, duplicate Windows names and corrupted file data are rejected', async t => {
  const f = await fixture(t)
  await assert.rejects(extractSourceZip(zip([...sourceFiles(), { name: 'source/../escape.txt', body: 'bad' }]), join(f.root, 'unsafe')), /Unsafe/)
  assert.equal(await exists(join(f.root, 'unsafe/package.json')), false)
  await assert.rejects(extractSourceZip(zip([{ name: 'source/UPPER', body: 'a' }, { name: 'source/upper', body: 'b' }]), join(f.root, 'duplicate')), /Conflicting/)
  await assert.rejects(extractSourceZip(zip([{ name: 'source/a', body: 'wrong checksum', corrupt: true }]), join(f.root, 'corrupt')), /checksum/)
})

test('fresh source bootstrap downloads only the fixed official tag and verifies manifest version', async t => {
  const f = await fixture(t), requests = []
  const source = await resolveBuildSource(f.root, { env: {}, log: quiet, download: async url => { requests.push(url); return zip(sourceFiles()) } })
  assert.equal(source, join(f.root, '.build-cache', DSH_BUILD_TAG))
  assert.deepEqual(requests, [DSH_SOURCE_URL])
  assert.equal(await resolveBuildSource(f.root, { env: {}, download: async () => assert.fail('cached source must not download') }), source)
  const manifest = await minimalToolManifest(source, f.root)
  assert.equal(manifest.packageManager, 'pnpm@11.28.5')
  assert.deepEqual(Object.keys(manifest.dependencies), ['tsdown', 'lightningcss', 'typescript', 'zod', 'react', 'react-dom', 'clsx', 'yaml', '@xterm/xterm'])
  assert(!Object.keys(manifest.dependencies).some(name => name.startsWith('@deepseek-ai/')))
})

test('explicit source with the wrong version fails without network fallback', async t => {
  const f = await fixture(t), source = join(f.root, 'wrong')
  await extractSourceZip(zip(sourceFiles('9.9.9')), source)
  await assert.rejects(resolveBuildSource(f.root, { env: { DSH_SOURCE: source }, download: async () => assert.fail('must not silently switch source') }), /official DSH/)
})

test('fresh minimal tool bootstrap verifies pnpm integrity and confines install and links to build state', async t => {
  const f = await fixture(t), calls = [], tarball = Buffer.from('fake pnpm archive for the injected extractor')
  const metadata = { name: 'pnpm', version: '11.28.5', dist: { tarball: 'https://registry.npmjs.org/pnpm/-/pnpm-11.28.5.tgz', integrity: 'sha512-' + createHash('sha512').update(tarball).digest('base64') } }
  const download = async url => {
    if (url === DSH_SOURCE_URL) return zip(sourceFiles())
    if (url === 'https://registry.npmjs.org/pnpm/11.28.5') return Buffer.from(JSON.stringify(metadata))
    if (url === metadata.dist.tarball) return tarball
    assert.fail('unexpected download: ' + url)
  }
  const run = async (command, args, options) => {
    calls.push({ command, args, options })
    if (args[0] === '-xzf') {
      const target = args.at(-1)
      assert(inside(join(f.root, '.build-cache'), target))
      await put(target, 'package.json', JSON.stringify({ name: 'pnpm', version: '11.28.5' })); await put(target, 'bin/pnpm.cjs', '// fake CLI')
    } else if (args[1] === 'install') {
      assert(inside(join(f.root, '.build-cache'), options.cwd))
      assert(args.includes('--ignore-scripts')); assert(args.includes('--store-dir'))
      const manifest = JSON.parse(await readFile(join(options.cwd, 'package.json'), 'utf8'))
      for (const name of Object.keys(manifest.dependencies)) await put(options.cwd, `node_modules/${name}/package.json`, JSON.stringify({ name, version: '1.0.0', exports: { '.': './index.js' } }))
    } else {
      assert.equal(args[0], join(f.root, 'scripts/prepare-dev.mjs'))
      assert.equal(args[2], '--build-only')
    }
  }
  const source = await ensureMinimalToolchain(f.root, { env: {}, download, run, log: quiet })
  assert(await exists(join(source, 'node_modules/tsdown/package.json')))
  assert(await exists(join(source, 'packages/client/ui-plugin-manager/node_modules/react/package.json')))
  assert.equal(calls.filter(call => call.args[1] === 'install').length, 1)
  await ensureMinimalToolchain(f.root, { env: {}, download: async () => assert.fail('complete cache must stay offline'), run, log: quiet })
  assert.equal(calls.filter(call => call.args[1] === 'install').length, 1)
})

test('a failed fresh source verification leaves no reusable invalid checkout', async t => {
  const f = await fixture(t)
  await assert.rejects(resolveBuildSource(f.root, { env: {}, log: quiet, download: async () => zip(sourceFiles('1.0.0')) }), /official DSH/)
  assert.deepEqual(await readdir(join(f.root, '.build-cache')), [])
})
