import { acquireFileLock } from './file-lock.mjs'
import { spawn } from 'node:child_process'
import { existsSync, readFileSync, realpathSync } from 'node:fs'
import { mkdir, writeFile, readFile, readdir, unlink, rename } from 'node:fs/promises'
import { homedir } from 'node:os'
import { dirname, join, resolve, delimiter, relative, isAbsolute } from 'node:path'
import { createRequire } from 'node:module'
import net from 'node:net'
import { randomUUID } from 'node:crypto'
import semver from 'semver'
import { parse, stringify } from 'yaml'
import { DSH_VERSION, PNPM_VERSION, PLUGIN, CORE, CATALOG, REGISTRY, registryUrl, resolvePlan, manifest } from './plan.mjs'

const MARK = 'cannbot-dsh-install-v1'
const readJson = file => JSON.parse(readFileSync(file, 'utf8'))
const alive = pid => { try { process.kill(pid, 0); return true } catch (e) { return e.code !== 'ESRCH' } }
const defaultRoot = () => join(process.env.XDG_DATA_HOME || join(homedir(), '.local/share'), 'cannbot-dsh')
export function options(args) {
  const result = { root: defaultRoot(), registry: REGISTRY, port: undefined, start: true, open: true, startOnly: false }
  for (let i = 0; i < args.length; i++) {
    const arg = args[i]
    if (arg === '--no-start') result.start = false
    else if (arg === '--no-open') result.open = false
    else if (arg === '--start-only') result.startOnly = true
    else if (['--dir', '--registry', '--port'].includes(arg)) {
      const value = args[++i]
      if (!value || value.startsWith('--')) throw Error(`${arg} 缺少参数`)
      if (arg === '--dir') result.root = resolve(value)
      if (arg === '--registry') result.registry = registryUrl(value)
      if (arg === '--port') { if (!/^\d+$/.test(value) || +value < 1 || +value > 65535) throw Error('端口应在 1–65535 之间'); result.port = +value }
    } else throw Error(`未知参数：${arg}`)
  }
  result.root = resolve(result.root)
  return result
}
export async function claimRoot(root) {
  await mkdir(root, { recursive: true })
  const marker = join(root, 'installer.json')
  if (existsSync(marker)) { if (readJson(marker).owner !== MARK) throw Error('此目录由其他程序管理，请选择新的 --dir'); return }
  if ((await readdir(root)).length) throw Error('安装目录非空且不属于本安装器，请选择新的 --dir')
  await writeFile(marker, JSON.stringify({ owner: MARK, created: new Date().toISOString() }), { mode: 0o600, flag: 'wx' })
}
const lock = root => acquireFileLock(join(root, 'install.lock'))
export function npmCli() {
  const candidates = [process.env.npm_execpath, join(dirname(process.execPath), 'node_modules/npm/bin/npm-cli.js'), join(dirname(process.execPath), '../lib/node_modules/npm/bin/npm-cli.js')]
  for (const directory of (process.env.PATH || '').split(delimiter)) for (const file of ['npm']) {
    try { candidates.push(realpathSync(join(directory, file))) } catch {}
  }
  for (let candidate of candidates.filter(Boolean)) {
    if (candidate.endsWith('npx-cli.js')) candidate = join(dirname(candidate), 'npm-cli.js')
    if (existsSync(candidate) && (candidate.endsWith('npm-cli.js') || candidate.endsWith('/bin/npm'))) return candidate
  }
  throw Error('找不到 npm CLI，请使用包含 npm/npx 的 Node.js 安装')
}
export function reusableRuntimeLock(runtime) {
  try {
    const pkg = readJson(join(runtime, 'package.json')), lock = readJson(join(runtime, 'package-lock.json'))
    return pkg.dependencies?.['@deepseek-ai/dsh'] === DSH_VERSION && pkg.dependencies?.pnpm === PNPM_VERSION
      && lock.packages?.['node_modules/@deepseek-ai/dsh']?.version === DSH_VERSION && lock.packages?.['node_modules/pnpm']?.version === PNPM_VERSION
  } catch { return false }
}
function run(file, args, { env = process.env, cwd = process.cwd(), onSpawn, allowInterrupt = false } = {}) {
  return new Promise((accept, reject) => {
    const child = spawn(process.execPath, [file, ...args], { env, cwd, stdio: 'inherit' })
    const signal = name => { try { child.kill(name) } catch {} }
    const interrupt = () => signal('SIGINT'), terminate = () => signal('SIGTERM')
    process.on('SIGINT', interrupt); process.on('SIGTERM', terminate)
    const clear = () => { process.off('SIGINT', interrupt); process.off('SIGTERM', terminate) }
    child.on('error', error => { clear(); reject(error) })
    child.on('spawn', () => { try { if (onSpawn) onSpawn(child.pid) } catch (error) { signal('SIGTERM'); clear(); reject(error) } })
    child.on('exit', (code, sig) => { clear(); code === 0 || allowInterrupt && (['SIGINT', 'SIGTERM'].includes(sig) || [130, 143, 3221225786].includes(code)) ? accept() : reject(Error(`子命令未完成（退出码 ${code ?? sig}），请查看上方日志后重试`)) })
  })
}
export function verify(home, plan) {
  const profile = join(home, 'profiles/web'), pluginFile = join(profile, 'node_modules', PLUGIN, 'package.json')
  const plugin = readJson(pluginFile), requireCore = createRequire(pluginFile)
  const coreFile = requireCore.resolve(`${CORE}/package.json`), core = readJson(coreFile)
  const catalogFile = createRequire(coreFile).resolve(`${CATALOG}/package.json`), catalog = readJson(catalogFile), resources = createRequire(catalogFile)
  if (plugin.version !== plan.plugin || core.version !== plan.core || catalog.version !== plan.catalog) throw Error('安装版本与查询到的 latest 不一致，未报告成功')
  for (const expected of plan.workflows) {
    const file = resources.resolve(`${expected.package}/package.json`), installed = readJson(file), descriptor = readJson(join(dirname(file), 'workflow.json'))
    if (installed.version !== expected.version || descriptor.id !== expected.id || descriptor.version !== expected.version || !descriptor.skills?.length) throw Error(`工作流未正确安装：${expected.id}`)
    for (const skill of descriptor.skills) {
      const resource = resolve(dirname(file), 'resources', skill.path), inside = relative(resolve(dirname(file), 'resources'), resource)
      if (inside.startsWith('..') || isAbsolute(inside) || !existsSync(resource)) throw Error(`工作流资源不完整：${expected.id}`)
    }
  }
  if (!readJson(join(profile, 'package.json')).dsh?.profile?.bundles?.includes(PLUGIN)) throw Error('插件已下载但未加入 Web 启用列表，请重试安装')
  return { plugin: plan.plugin, catalog: plan.catalog, workflowCount: plan.workflows.length }
}
export async function freePort(port) {
  const listen = number => new Promise((accept, reject) => {
    const server = net.createServer(); server.once('error', reject)
    server.listen(number, '127.0.0.1', () => { const chosen = server.address().port; server.close(error => error ? reject(error) : accept(chosen)) })
  })
  try { return await listen(port ?? 3080) } catch (error) {
    if (port !== undefined || error.code !== 'EADDRINUSE') throw Error(`无法使用端口 ${port ?? 3080}：${error.message}`)
    return listen(0)
  }
}
export async function main(args = process.argv.slice(2)) {
  if (args.includes('--help') || args.includes('-h')) {
    console.log('CANNBot DSH 一键安装器\n用法：npx @cannbot-plugin/cannbot-dsh-install@latest [选项]\n\n默认：安装官方 DSH Web、最新插件及默认工作流，完成后启动浏览器界面。\n--no-start  仅安装并验证\n--no-open   启动但不打开浏览器（服务器推荐）\n--start-only 复用已安装环境，不查询或安装新版本\n--port N    指定本机监听端口\n--dir PATH  指定独立安装目录\n--registry URL 指定 HTTPS npm 源（镜像的 latest 可能滞后）\n\n需要 Node.js >=24.9.0；Web 保持终端运行，Ctrl+C 停止服务。支持 Linux／WSL，请在 Linux 环境中执行。')
    return
  }
  if (args.includes('--version')) { console.log('1.0.0'); return }
  if (process.platform !== 'linux') throw Error('本版安装器仅支持 Linux／WSL，请在 Linux 环境中执行')
  if (!semver.satisfies(process.versions.node, '>=24.9.0')) throw Error('请先安装 Node.js 24.9.0 或更新版本（包含 npm/npx）')
  const opt = options(args), root = opt.root, runtime = join(root, 'runtime'), home = join(root, 'home'), record = join(root, 'installed.json'), serverFile = join(root, 'server.json')
  await claimRoot(root)
  const release = await lock(root)
  const dsh = join(runtime, 'node_modules/@deepseek-ai/dsh/lib/bin.js')
  const runtimeReady = join(runtime, 'ready.json')
  const identity = { dsh: DSH_VERSION, pnpm: PNPM_VERSION, nodeMajor: semver.major(process.versions.node), platform: process.platform, arch: process.arch }
  const env = { ...process.env, DSH_HOME: home, CANNBOT_DSH_WORKFLOW_ROOT: join(home, 'cannbot-dsh-workflows'), PATH: join(runtime, 'node_modules/.bin') + delimiter + (process.env.PATH || '') }
  let plan
  try {
    if (existsSync(serverFile) && alive(readJson(serverFile).pid)) throw Error('此环境的 Web 服务已运行，请在原终端按 Ctrl+C 停止后重试')
    if (opt.startOnly) {
      if (!existsSync(record)) throw Error('尚未完成安装，请先不带 --start-only 运行')
      plan = readJson(record).plan; verify(home, plan)
      if (!existsSync(dsh)) throw Error('DSH 文件缺失，请重新运行安装命令')
      try { if (JSON.stringify(readJson(runtimeReady)) !== JSON.stringify(identity)) throw Error() } catch { throw Error('运行时安装尚未完整完成，请先不带 --start-only 重新执行安装') }
    } else {
      console.log('[1/5] 查询 CANNBot DSH 和默认工作流的 latest 版本…')
      plan = await resolvePlan(name => manifest(name, opt.registry))
      console.log(`主插件 ${plan.plugin}；目录 ${plan.catalog}；${plan.workflows.length} 个默认工作流。`)
      console.log(`[2/5] 准备官方 DSH ${DSH_VERSION} 和 pnpm ${PNPM_VERSION}…`)
      await mkdir(runtime, { recursive: true })
      const runtimeManifest = join(runtime, 'package.json')
      if (!existsSync(runtimeManifest)) await writeFile(runtimeManifest, JSON.stringify({ name: 'cannbot-dsh-private-runtime', private: true }), { flag: 'wx' })
      const pnpmFile = join(runtime, 'node_modules/pnpm/package.json')
      let ready = false
      try { ready = existsSync(dsh) && readJson(join(runtime, 'node_modules/@deepseek-ai/dsh/package.json')).version === DSH_VERSION && readJson(pnpmFile).version === PNPM_VERSION && JSON.stringify(readJson(runtimeReady)) === JSON.stringify(identity) } catch {}
      if (!ready) {
        // An interrupted npm operation can leave manifests present while other
        // dependencies are missing. Only a completed transaction is reusable.
        await writeFile(runtimeReady, JSON.stringify({ ready: false }), { mode: 0o600 })
        const locked = reusableRuntimeLock(runtime)
        await run(npmCli(), [locked ? 'ci' : 'install', '--prefix', runtime, '--global=false', '--omit=dev', '--prefer-offline', '--no-audit', '--no-fund', '--fetch-retries=2', '--fetch-timeout=120000', `--registry=${opt.registry}`, ...(locked ? [] : ['--save-exact', `@deepseek-ai/dsh@${DSH_VERSION}`, `pnpm@${PNPM_VERSION}`])], { env })
        const temporary = join(runtime, `ready-${randomUUID()}.json`)
        await writeFile(temporary, JSON.stringify(identity), { mode: 0o600 }); await rename(temporary, runtimeReady)
      }
      console.log('[3/5] 通过 DSH 官方命令安装主插件和全部默认工作流…')
      // Initialize only this installation's own web profile; never touch Desktop.
      await run(dsh, ['plugin', '--profile', 'web', 'install', `--registry=${opt.registry}`], { env })
      const workspaceFile = join(home, 'profiles/web/pnpm-workspace.yaml')
      const workspace = parse(await readFile(workspaceFile, 'utf8')) ?? {}
      workspace.overrides = { ...workspace.overrides, [CATALOG]: plan.catalog, ...Object.fromEntries(plan.workflows.map(w => [w.package, w.version])) }
      await writeFile(workspaceFile, stringify(workspace))
      await run(dsh, ['plugin', '--profile', 'web', 'add', `${PLUGIN}@${plan.plugin}`, '--save-exact', `--registry=${opt.registry}`], { env })
      // A prior interrupted pnpm operation may have left the package present but
      // outside the active bundle list. Repair using official commands only.
      if (!readJson(join(home, 'profiles/web/package.json')).dsh?.profile?.bundles?.includes(PLUGIN)) {
        await run(dsh, ['plugin', '--profile', 'web', 'remove', PLUGIN], { env })
        await run(dsh, ['plugin', '--profile', 'web', 'add', `${PLUGIN}@${plan.plugin}`, '--save-exact', `--registry=${opt.registry}`], { env })
      }
      console.log('[4/5] 核对主插件版本、启用状态和每个工作流资源文件…')
      const verified = verify(home, plan)
      const tmp = join(root, `installed-${randomUUID()}.json`)
      await writeFile(tmp, JSON.stringify({ owner: MARK, plan, verified, installedAt: new Date().toISOString() }, null, 2), { mode: 0o600 })
      await rename(tmp, record)
      console.log(`安装完成：CANNBot DSH ${plan.plugin}，${verified.workflowCount} 个工作流已到齐。`)
    }
  } finally { await release() }
  if (!opt.start) { console.log('已完成安装验证。下次使用同一命令加 --start-only 启动。'); return }
  const releaseStart = await lock(root)
  let serverPid
  try {
    if (existsSync(serverFile) && alive(readJson(serverFile).pid)) throw Error('此环境的 Web 服务已运行')
    const port = await freePort(opt.port)
    console.log(`[5/5] 启动 DSH Web（127.0.0.1:${port}）。首次使用请在界面中配置账号或 API Key。\n请保留终端；Ctrl+C 停止服务。使用 DSH 打印或自动打开的完整认证链接。`)
    await run(dsh, ['web', '--host', '127.0.0.1', '--port', String(port), ...(opt.open ? [] : ['--no-open'])], { env, allowInterrupt: true, onSpawn(pid) { serverPid = pid; /* Owned PID only; no authentication tokens are persisted. */ requireWrite(serverFile, { pid }); void releaseStart() } })
  } finally { await releaseStart(); try { if (readJson(serverFile).pid === serverPid) await unlink(serverFile) } catch {} }
}
function requireWrite(file, value) {
  // This small synchronous write must finish before another installer can inspect it.
  createRequire(import.meta.url)('node:fs').writeFileSync(file, JSON.stringify(value), { mode: 0o600 })
}
