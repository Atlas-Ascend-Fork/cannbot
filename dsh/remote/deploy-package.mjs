// Executed with node -e over SSH; stdin is exactly the locally built npm tgz.
import { createHash } from 'node:crypto'
import { existsSync, readFileSync, writeFileSync, mkdirSync, readdirSync, realpathSync, lstatSync, renameSync, symlinkSync, openSync, closeSync, statSync } from 'node:fs'
import { homedir } from 'node:os'
import { join, dirname, resolve } from 'node:path'
import { spawn, spawnSync } from 'node:child_process'
import net from 'node:net'

const PACKAGE = '@cannbot-plugin/cannbot-dsh'
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
    if (!entry || !args.includes('web') || option('--host') !== '127.0.0.1' || option('--port') !== String(port)) return null
    if ((option('--profile') || 'web') !== profile) return null
    if (realpath(directory + '/fd/1') !== realpath(log)) return null
    const status = read(directory + '/stat', 'utf8')
    const start = status.slice(status.lastIndexOf(')') + 2).split(' ')[19]
    return { pid, start, executable, port, log, profile, uid }
  } catch { return null }
}

export async function stopOwned(ownerFile, expected, operations = {}) {
  const identify = operations.identify || processIdentity
  const busy = operations.busy || portBusy
  const wait = operations.wait || sleep
  const kill = operations.kill || process.kill
  const readOwner = operations.readOwner || (() => existsSync(ownerFile) ? json(ownerFile) : null)
  const candidatesFor = operations.candidates || (() => readdirSync('/proc').filter(name => /^\d+$/.test(name)).map(name => identify(Number(name), expected)).filter(Boolean))
  let owner = readOwner()
  if (owner) {
    const actual = identify(owner.pid, expected)
    if (!actual || actual.start !== owner.start) owner = null
  }
  if (!owner) {
    // Adopt an earlier CANNBot bootstrap only when UID, exact DSH entrypoint,
    // Web arguments, loopback port and stdout logfile all identify it.
    const candidates = candidatesFor()
    if (candidates.length !== 1) fail('Cannot safely identify the existing DSH Web process. Stop that server in its original terminal, then reconnect.')
    owner = candidates[0]
  }
  const current = identify(owner.pid, expected)
  if (!current || current.start !== owner.start) fail('DSH process changed before shutdown; reconnect after stopping the original server.')
  kill(owner.pid, 'SIGTERM')
  for (let attempt = 0; attempt < 80; attempt++) { if (!(await busy(expected.port))) return; await wait(250) }
  fail('DSH Web did not exit after graceful shutdown. Stop it in its original terminal, then reconnect.')
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
      if (!args.includes('web') || !args.some(arg => { try { return realpath(arg) === executable } catch { return false } })) continue
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

export async function runDeployment(args = process.argv.slice(1)) {
const [hash, profile = 'web', requestedPort, registry] = args
try {
  if (!/^[a-f0-9]{64}$/.test(hash || '') || !/^[A-Za-z0-9._-]+$/.test(profile)) fail('Invalid deployment identity')
  if (registry && new URL(registry).protocol !== 'https:') fail('Registry must use HTTPS')
  const home = resolve(process.env.DSH_HOME || join(homedir(), '.dsh'))
  const state = join(home, 'cannbot-remote'), builds = join(state, 'builds'), store = join(builds, hash)
  mkdirSync(builds, { recursive: true, mode: 0o700 })
  if (lstatSync(builds).isSymbolicLink() || !realpathSync(builds).startsWith(realpathSync(home) + '/')) fail('Unsafe deployment directory')
  mkdirSync(store, { mode: 0o700, recursive: true })
  if (lstatSync(store).isSymbolicLink()) fail('Unsafe package store')
  const input = []
  let length = 0
  for await (const chunk of process.stdin) { length += chunk.length; if (length > 128 * 1024 * 1024) fail('Package archive too large'); input.push(chunk) }
  const archiveBytes = Buffer.concat(input)
  if (createHash('sha256').update(archiveBytes).digest('hex') !== hash) fail('Package checksum did not match')
  const archive = join(store, 'source.tgz')
  writeFileSync(archive, archiveBytes, { mode: 0o600 })
  const target = join(store, 'node_modules', ...PACKAGE.split('/'))
  if (!existsSync(join(store, 'complete.json'))) {
    console.log('CANNBOT_STEP=Installing the current CANNBot build and workflow dependencies')
    atomic(join(store, 'package.json'), { name: 'cannbot-remote-build', private: true })
    installCurrentPackage(store, archive, registry)
    if (json(join(target, 'package.json')).name !== PACKAGE || !existsSync(join(target, 'lib/client.js')) || !existsSync(join(target, 'lib/index.js'))) fail('Installed CANNBot package is incomplete')
    atomic(join(store, 'complete.json'), { hash })
  }
  const dshCommand = run('sh', ['-c', 'command -v dsh'])
  const executable = realpathSync(dshCommand)
  const profileDir = join(home, 'profiles', profile), profileFile = join(profileDir, 'package.json')
  const installedFile = join(state, 'deployed-' + profile + '.json')
  const installed = existsSync(installedFile) ? json(installedFile) : null
  const remembered = existsSync(join(state, 'port')) ? Number(readFileSync(join(state, 'port'), 'utf8')) : 0
  const existing = existingWeb(home, executable, profile)
  let port = existing?.port || remembered || Number(requestedPort) || 17633
  if (!Number.isSafeInteger(port) || port < 1024 || port > 65535) fail('Invalid Web port')
  const log = join(home, 'web-' + port + '.log'), ownerFile = join(state, 'web-' + port + '.owner.json')
  const busy = await portBusy(port)
  if (existing && !busy) fail('An existing DSH Web process is still starting or stopping. Wait for it to exit or become ready, then reconnect.')
  const recordedOwner = existsSync(ownerFile) ? json(ownerFile) : null
  const currentOwner = recordedOwner && processIdentity(recordedOwner.pid, { executable, port, log, profile })
  let reused = Boolean(busy && installed?.hash === hash && installed?.port === port && currentOwner?.start === recordedOwner?.start)
  if (busy && !reused) await stopOwned(ownerFile, { executable, port, log, profile })
  if (!reused) {
    console.log('CANNBOT_STEP=Activating the current CANNBot build')
    if (!existsSync(profileFile)) run(dshCommand, ['plugin', '--profile', profile, 'install'], { env: { ...process.env, DSH_HOME: home } })
    const manifest = json(profileFile)
    const profileTarget = join(profileDir, 'node_modules', ...PACKAGE.split('/'))
    mkdirSync(dirname(profileTarget), { recursive: true })
    if (!realpathSync(dirname(profileTarget)).startsWith(realpathSync(profileDir) + '/')) fail('Package directory escaped the DSH profile')
    const temporaryLink = profileTarget + '.new-' + process.pid
    symlinkSync(target, temporaryLink, 'dir')
    let previous
    try { lstatSync(profileTarget); previous = profileTarget + '.before-source-' + Date.now(); renameSync(profileTarget, previous) } catch (error) { if (error.code !== 'ENOENT') throw error }
    try {
      renameSync(temporaryLink, profileTarget)
      writeFileSync(profileFile + '.before-source-' + Date.now() + '.bak', readFileSync(profileFile), { mode: 0o600 })
      manifest.dependencies ||= {}
      delete manifest.dependencies['cannbot-dsh']; delete manifest.dependencies['@cannbot-plugin/cannbot-remote']
      manifest.dependencies[PACKAGE] = 'file:' + target
      manifest.dsh ||= {}; manifest.dsh.profile ||= {}
      manifest.dsh.profile.bundles = [...(manifest.dsh.profile.bundles || []).filter(name => !['cannbot-dsh', PACKAGE, '@cannbot-plugin/cannbot-remote'].includes(name)), PACKAGE]
      atomic(profileFile, manifest)
    } catch (error) { if (previous && !existsSync(profileTarget)) renameSync(previous, profileTarget); throw error }
    const output = openSync(log, 'w', 0o600)
    const serviceEnv = { ...process.env, DSH_HOME: home }
    delete serviceEnv.CANNBOT_CONNECT_ATTEMPT
    const child = spawn(dshCommand, ['web', '--host', '127.0.0.1', '--port', String(port), ...(profile === 'web' ? [] : ['--profile', profile]), '--no-open'], { cwd: homedir(), env: serviceEnv, detached: true, stdio: ['ignore', output, output] })
    closeSync(output)
    let spawnFailure
    child.on('error', error => { spawnFailure = error })
    child.unref()
    let identity
    for (let attempt = 0; attempt < 40; attempt++) { if (spawnFailure) fail('Unable to start DSH Web'); identity = processIdentity(child.pid, { executable, port, log, profile }); if (identity) break; await sleep(100) }
    if (!identity) fail('Unable to verify the started DSH Web process; check its log before retrying')
    atomic(ownerFile, identity)
    atomic(installedFile, { hash, port, profile })
    writeFileSync(join(state, 'port'), String(port), { mode: 0o600 })
  }
  let token = ''
  for (let attempt = 0; attempt < 120; attempt++) {
    const matches = existsSync(log) ? [...readFileSync(log, 'utf8').matchAll(/token=([A-Za-z0-9._-]+)/g)] : []
    token = matches.at(-1)?.[1] || ''
    if (token && await portBusy(port)) break
    await sleep(500)
  }
  if (!token || !(await portBusy(port))) fail('DSH Web did not become ready; inspect its startup log and reconnect')
  console.log('CANNBOT_REMOTE_PORT=' + port)
  console.log('CANNBOT_WEB_LOG=' + log)
  console.log('CANNBOT_TOKEN=' + token)
  console.log('CANNBOT_REUSE=' + (reused ? '1' : '0'))
  console.log('CANNBOT_PLUGIN_VERSION=' + json(join(target, 'package.json')).version)
  console.log('CANNBOT_OK=1')
} catch (error) {
  console.log('CANNBOT_ERROR=' + (error?.message || 'Remote package deployment failed').replace(/[\r\n]/g, ' '))
  process.exitCode = 1
}

}
if (/^[a-f0-9]{64}$/.test(process.argv[1] || '')) await runDeployment()
