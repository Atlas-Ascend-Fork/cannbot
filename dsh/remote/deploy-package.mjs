// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

// Executed with node -e over SSH; stdin is exactly the locally built npm tgz.
import { DatabaseSync } from 'node:sqlite'
import { existsSync, readFileSync, writeFileSync, mkdirSync, readdirSync, realpathSync, lstatSync, mkdtempSync, rmSync, renameSync, symlinkSync, openSync, closeSync, statSync } from 'node:fs'
import { homedir } from 'node:os'
import { join, dirname, resolve } from 'node:path'
import { spawn, spawnSync } from 'node:child_process'
import net from 'node:net'

const PACKAGE = '@cannbot-plugin/cannbot-dsh-server'
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms))
function fail(message) { throw new Error(message) }
function json(file) { return JSON.parse(readFileSync(file, 'utf8').replace(/^\uFEFF/, '')) }
function atomic(file, data) { const temporary = file + '.tmp-' + process.pid; writeFileSync(temporary, JSON.stringify(data, null, 2) + '\n', { mode: 0o600 }); renameSync(temporary, file) }
function run(command, args, options = {}, execute = spawnSync) {
  const result = execute(command, args, { encoding: 'utf8', maxBuffer: 8 * 1024 * 1024, timeout: 12 * 60 * 1000, ...options })
  if (result.status !== 0) {
    // Package-manager output can contain authenticated registry URLs. Report
    // only its fixed error code and exit status, never raw stdout/stderr.
    const code = /(?:npm (?:error|ERR!) code)\s+(E[A-Z0-9_]+)\b/.exec(result.stderr || '')?.[1]
    const detail = `${code ? code + ', ' : ''}${Number.isInteger(result.status) ? 'exit ' + result.status : 'could not start'}`
    if (code === 'E404') fail(`CANNBot dependency was not found in the package registry (${detail}). Verify the configured registry and retry.`)
    fail(`CANNBot package installation failed (${detail}); verify npm connectivity and retry.`)
  }
  return result.stdout.trim()
}

export function installCurrentPackage(store, archive, registry = '', operations = {}) {
  const publicRegistry = 'https://registry.npmjs.org/'
  // The public mirror may have package metadata before its CDN has the tarball.
  // npm also rewrites npmjs tarball URLs using its global registry, so a scope
  // override alone is insufficient. Use the official registry for this isolated
  // install and disable that rewrite; preserve explicitly configured custom hosts.
  const useOfficialRegistry = !registry || new URL(registry).hostname === 'registry.npmmirror.com'
  const installRegistry = useOfficialRegistry ? publicRegistry : registry
  return run('npm', ['install', '--prefix', store, '--ignore-scripts', '--legacy-peer-deps', '--omit=dev', '--no-audit', '--no-fund', '--save-exact', '--prefer-offline',
    '--registry', installRegistry, `--@cannbot-plugin:registry=${installRegistry}`,
    ...(useOfficialRegistry ? ['--replace-registry-host=never'] : []), archive], {}, operations.execute)
}
function portBusy(port) { return new Promise(resolve => { const socket = net.createConnection({ host: '127.0.0.1', port }); const end = value => { socket.destroy(); resolve(value) }; socket.setTimeout(800, () => end(false)); socket.once('connect', () => end(true)); socket.once('error', () => end(false)) }) }

// Launcher options precede all Web-app options; "dsh web" is shorthand for the web profile.
function selectedProfile(args, executableAt) {
  if (executableAt < 0) return null
  const next = args[executableAt + 1]
  return next === '--profile' ? args[executableAt + 2] : next
}

export function processIdentity(pid, { executable, port, log, profile, runtime = process.execPath }, system = {}) {
  const read = system.read || readFileSync
  const stat = system.stat || statSync
  const realpath = system.realpath || realpathSync
  const uid = system.uid ?? process.getuid?.()
  if (!Number.isSafeInteger(pid) || pid < 2) return null
  try {
    const directory = '/proc/' + pid
    if (stat(directory).uid !== uid) return null
    if (realpath(directory + '/exe') !== realpath(runtime)) return null
    const args = read(directory + '/cmdline', 'utf8').split('\0').filter(Boolean)
    const entry = args.find(arg => { try { return realpath(arg) === executable } catch { return false } })
    const option = name => { const at = args.indexOf(name); return at < 0 ? undefined : args[at + 1] }
    if (!entry || option('--host') !== '127.0.0.1' || option('--port') !== String(port)) return null
    if (selectedProfile(args, args.indexOf(entry)) !== profile) return null
    if (realpath(directory + '/fd/1') !== realpath(log)) return null
    const status = read(directory + '/stat', 'utf8')
    const start = status.slice(status.lastIndexOf(')') + 2).split(' ')[19]
    return { pid, start, executable, port, log, profile, uid }
  } catch { return null }
}

export function existingWeb(home, executable, profile, operations = {}) {
  const list = operations.list || readdirSync, read = operations.read || readFileSync
  const stat = operations.stat || statSync, realpath = operations.realpath || realpathSync
  const identify = operations.identify || processIdentity
  const uid = operations.uid ?? process.getuid?.()
  const defaultHome = operations.defaultHome || join(homedir(), '.dsh')
  const found = []
  for (const name of list('/proc').filter(name => /^\d+$/.test(name))) {
    const directory = '/proc/' + name
    let args
    try {
      if (stat(directory).uid !== uid) continue
      args = read(directory + '/cmdline', 'utf8').split('\0').filter(Boolean)
      const at = args.findIndex(arg => { try { return realpath(arg) === executable } catch { return false } })
      if (selectedProfile(args, at) !== profile) continue
    } catch { continue }
    let environment
    try { environment = read(directory + '/environ', 'utf8').split('\0') }
    catch { fail('Cannot verify an existing DSH Web environment. Stop that server in its original terminal, then reconnect.') }
    const setting = environment.find(entry => entry.startsWith('DSH_HOME='))?.slice(9)
    if (resolve(setting || defaultHome) !== home) continue
    const at = args.indexOf('--port'), port = Number(at >= 0 ? args[at + 1] : NaN)
    const identity = identify(Number(name), { executable, profile, port, log: join(home, 'web-' + port + '.log') })
    if (!identity) fail('An existing DSH Web uses this data directory but its ownership cannot be verified. Stop it in its original terminal, then reconnect.')
    found.push(identity)
  }
  if (found.length > 1) fail('Multiple DSH Web processes use this data directory. Stop them before reconnecting.')
  return found[0] || null
}

function installedServer(target, version, buildId) {
  try {
    const pkg = json(join(target, 'package.json'))
    return pkg.name === PACKAGE && pkg.cannbotEdition === 'server' && pkg.version === version && pkg.cannbotBuildId === buildId &&
      ['lib/client.js', 'lib/index.js', 'cordis.patch.yml'].every(file => existsSync(join(target, file)))
  } catch { return false }
}

function cachedArchive(path) {
  try { return readFileSync(path) } catch (error) { if (error.code === 'ENOENT') return null; throw error }
}

export function preinstalledArchive(home, userHome, version, buildId) {
  const manual = join(home, 'profiles/cannbot-server/.cannbot-install.json')
  let receipt
  try { receipt = json(manual) } catch { return null }
  if (receipt.schemaVersion !== 1 || receipt.edition !== 'server' || receipt.buildId !== buildId || receipt.version !== version) return null
  return cachedArchive(join(userHome, '.local/share/cannbot/releases', buildId, 'server.tgz'))
}

export async function readyServer(port, token, version, buildId, fetcher = fetch) {
  const origin = 'http://127.0.0.1:' + port
  try {
    const signal = AbortSignal.timeout(2000)
    const handshake = await fetcher(origin + '/?token=' + encodeURIComponent(token), { redirect: 'manual', signal })
    const cookies = handshake.headers.getSetCookie().map(cookie => cookie.split(';', 1)[0]).join('; ')
    await handshake.body?.cancel()
    if (handshake.status !== 303 || !cookies) return false
    const response = await fetcher(origin + '/api/cannbot-dsh/server', { headers: { cookie: cookies }, redirect: 'error', signal })
    if (!response.ok) { await response.body?.cancel(); return false }
    const actual = await response.json()
    return actual.edition === 'server' && actual.buildId === buildId && actual.version === version
  } catch { return false }
}

export async function availablePort(preferred, busy = portBusy) {
  if (!Number.isSafeInteger(preferred) || preferred < 1024 || preferred > 65535) fail('Invalid Web port')
  if (!await busy(preferred)) return preferred
  for (let port = 17633; port <= 17700; port++) if (port !== preferred && !await busy(port)) return port
  fail('No loopback port is available for the CANNBot server')
}

function ensureProfile(home, profile, buildId, target) {
  const profiles = join(home, 'profiles'), dir = join(profiles, profile)
  const link = packageDir => join(packageDir, 'node_modules', ...PACKAGE.split('/'))
  mkdirSync(profiles, { recursive: true, mode: 0o700 })
  if (existsSync(dir)) {
    const manifest = json(join(dir, 'package.json'))
    if (lstatSync(dir).isSymbolicLink() || manifest.cannbotManagedBuild !== buildId ||
        !manifest.dsh?.profile?.bundles?.includes(PACKAGE) || realpathSync(link(dir)) !== realpathSync(target)) {
      fail('The managed CANNBot profile has changed. Restore its original configuration before reconnecting.')
    }
    return
  }
  const staging = mkdtempSync(join(profiles, '.cannbot-staging-'))
  try {
    mkdirSync(dirname(link(staging)), { recursive: true })
    symlinkSync(target, link(staging), 'dir')
    atomic(join(staging, 'package.json'), {
      name: 'dsh-profile-' + profile, private: true, cannbotManagedBuild: buildId, dependencies: { [PACKAGE]: 'file:' + target },
      dsh: { profile: { bundles: ['@deepseek-ai/dsh-base', '@deepseek-ai/dsh-web-app', PACKAGE] } },
    })
    renameSync(staging, dir)
  } finally { rmSync(staging, { recursive: true, force: true }) }
}

export async function runDeployment(args = process.argv.slice(1)) {
  const [buildId, version, requestedPort, registry] = args
  let lock
  try {
    if (process.platform !== 'linux') fail('CANNBot Server requires Linux')
    if (!/^[a-z0-9][a-z0-9._-]{0,127}$/i.test(buildId || '') || !/^\d+\.\d+\.\d+(?:-[a-z0-9.-]+)?$/i.test(version || '')) fail('Invalid deployment identity')
    if (registry && new URL(registry).protocol !== 'https:') fail('Registry must use HTTPS')
    const profile = 'cannbot-server-' + buildId
    const home = resolve(process.env.DSH_HOME || join(homedir(), '.dsh'))
    const state = join(home, 'cannbot-remote'), builds = join(state, 'builds'), store = join(builds, buildId)
    mkdirSync(builds, { recursive: true, mode: 0o700 })
    if (realpathSync(builds) !== join(realpathSync(home), 'cannbot-remote', 'builds')) fail('Unsafe deployment directory')
    // Serialize install, profile creation and port selection across clients. An
    // SSH cancellation or process exit releases this kernel-held lock.
    const lockFile = join(state, 'deployment.sqlite3')
    closeSync(openSync(lockFile, 'a', 0o600))
    lock = new DatabaseSync(lockFile)
    lock.exec('PRAGMA busy_timeout=720000; BEGIN EXCLUSIVE')
    mkdirSync(store, { recursive: true, mode: 0o700 })
    if (lstatSync(store).isSymbolicLink()) fail('Unsafe package store')
    const target = join(store, 'node_modules', ...PACKAGE.split('/'))
    const chunks = []
    let length = 0
    for await (const chunk of process.stdin) { length += chunk.length; if (length > 128 * 1024 * 1024) fail('Package archive too large'); chunks.push(chunk) }
    const complete = join(store, 'complete.json')
    if (!existsSync(complete) || json(complete).buildId !== buildId || !installedServer(target, version, buildId)) {
      const archive = join(store, 'source.tgz')
      let bytes = length ? Buffer.concat(chunks) : cachedArchive(archive)
      bytes ??= preinstalledArchive(home, homedir(), version, buildId)
      if (!bytes) { console.log('CANNBOT_NEED_ARCHIVE=1'); return }
      console.log('CANNBOT_STEP=Installing the matching CANNBot server and workflow dependencies')
      writeFileSync(archive, bytes, { mode: 0o600 })
      atomic(join(store, 'package.json'), { name: 'cannbot-server-build', private: true })
      installCurrentPackage(store, archive, registry)
      if (!installedServer(target, version, buildId)) fail('Installed package does not match the requested CANNBot server build')
      atomic(complete, { version, buildId })
    }

    ensureProfile(home, profile, buildId, target)
    const executable = realpathSync(run('sh', ['-c', 'command -v dsh']))
    const existing = existingWeb(home, executable, profile)
    const port = existing?.port ?? await availablePort(Number(requestedPort) || 17633)
    const log = join(home, 'web-' + port + '.log')
    if (!existing) {
      console.log('CANNBOT_STEP=Starting the CANNBot server profile')
      const output = openSync(log, 'w', 0o600)
      const env = { ...process.env, DSH_HOME: home }
      delete env.CANNBOT_CONNECT_ATTEMPT
      let child
      try { child = spawn(process.execPath, [executable, '--profile', profile, '--host', '127.0.0.1', '--port', String(port), '--no-open'], {
        cwd: homedir(), env, detached: true, stdio: ['ignore', output, output],
      }) } finally { closeSync(output) }
      let spawnFailure
      child.once('error', error => { spawnFailure = error })
      child.unref()
      let identity
      for (let attempt = 0; attempt < 40; attempt++) {
        if (spawnFailure) fail('Unable to start DSH Web')
        identity = processIdentity(child.pid, { executable, port, log, profile })
        if (identity) break
        await sleep(100)
      }
      if (!identity) fail('Unable to verify the started DSH Web process; check its log before retrying')
    }
    let token = '', ready = false
    for (let attempt = 0; attempt < 120; attempt++) {
      const matches = existsSync(log) ? [...readFileSync(log, 'utf8').matchAll(/token=([A-Za-z0-9._-]+)/g)] : []
      token = matches.at(-1)?.[1] || ''
      if (token && await readyServer(port, token, version, buildId)) { ready = true; break }
      await sleep(500)
    }
    if (!ready) fail('The matching CANNBot Server did not become ready; inspect the DSH startup log and reconnect')
    console.log('CANNBOT_REMOTE_PORT=' + port)
    console.log('CANNBOT_WEB_LOG=' + log)
    console.log('CANNBOT_TOKEN=' + token)
    console.log('CANNBOT_REUSE=' + (existing ? '1' : '0'))
    console.log('CANNBOT_PLUGIN_VERSION=' + version)
    console.log('CANNBOT_BUILD_ID=' + buildId)
    console.log('CANNBOT_OK=1')
  } catch (error) {
    console.log('CANNBOT_ERROR=' + (error?.message || 'Remote package deployment failed').replace(/[\r\n]/g, ' '))
    process.exitCode = 1
  } finally { lock?.close() }
}
if (process.argv[1] === 'cannbot-deploy') await runDeployment(process.argv.slice(2))
