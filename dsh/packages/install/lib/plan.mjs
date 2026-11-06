import semver from 'semver'
import https from 'node:https'
import { gunzipSync, brotliDecompressSync, inflateSync } from 'node:zlib'
export const DSH_VERSION = '0.2.1-rc.3'
export const PNPM_VERSION = '11.28.5'
export const PLUGIN = 'cannbot-dsh'
export const CORE = '@cannbot-plugin/cannbot-dsh'
export const CATALOG = '@cannbot-plugin/workflow-catalog'
export const REGISTRY = 'https://registry.npmjs.org/'
export function registryUrl(value) {
  const url = new URL(value)
  if (url.protocol !== 'https:' || url.username || url.password || url.search || url.hash) throw Error('安装源必须是无凭据的 HTTPS registry 地址')
  return url.href.replace(/\/?$/, '/')
}
// npm metadata is small. Use the standard HTTPS client with normal certificate
// validation; IPv4 avoids failed IPv6 routes on common server networks.
function readManifest(url, redirects = 0) {
  return new Promise((accept, reject) => {
    const parsed = new URL(url)
    if (parsed.protocol !== 'https:' || parsed.username || parsed.password || redirects > 3) { reject(Error('无效的 registry 重定向')); return }
    let timer
    const request = https.get(parsed, { family: ['registry.npmjs.org', 'registry.npmmirror.com'].includes(parsed.hostname) ? 4 : undefined, headers: { accept: 'application/json', 'accept-encoding': 'identity', 'cache-control': 'no-cache' } }, response => {
      if ([301, 302, 303, 307, 308].includes(response.statusCode) && response.headers.location) {
        clearTimeout(timer); response.resume(); accept(readManifest(new URL(response.headers.location, parsed), redirects + 1)); return
      }
      if (response.statusCode !== 200) { clearTimeout(timer); response.resume(); reject(Error(`registry HTTP ${response.statusCode}`)); return }
      const chunks = []; let bytes = 0
      response.on('error', error => { clearTimeout(timer); reject(error) })
      response.on('data', chunk => { bytes += chunk.length; if (bytes > 4 * 1024 * 1024) request.destroy(Error('registry 元数据超出大小限制')); else chunks.push(chunk) })
      response.on('end', () => {
        clearTimeout(timer)
        try {
          let data = Buffer.concat(chunks)
          const decode = { gzip: gunzipSync, br: brotliDecompressSync, deflate: inflateSync }[response.headers['content-encoding']]
          if (decode) data = decode(data, { maxOutputLength: 4 * 1024 * 1024 })
          accept(JSON.parse(data.toString('utf8')))
        } catch (error) { reject(error) }
      })
    })
    timer = setTimeout(() => request.destroy(Error('registry 查询超时')), 20000)
    request.on('error', error => { clearTimeout(timer); reject(error) })
  })
}
export async function manifest(name, registry = REGISTRY) {
  let last
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const value = await readManifest(new URL(`${encodeURIComponent(name).replace(/^%40/, '@')}/latest`, registry))
      if (value.name !== name || !semver.valid(value.version)) throw Error(`${name}: 无效的 npm 版本信息`)
      return value
    } catch (error) { last = error }
  }
  throw Error(`无法查询 ${name} 的 latest：${last.message}`)
}
export async function resolvePlan(lookup = manifest, nodeVersion = process.versions.node) {
  const plugin = await lookup(PLUGIN), core = await lookup(CORE), catalog = await lookup(CATALOG)
  if (plugin.dependencies?.[CORE] !== core.version) throw Error('短包和主插件 latest 尚未同步，请稍后重试')
  if (!semver.satisfies(DSH_VERSION, core.engines?.dsh ?? '', { includePrerelease: true })) throw Error('最新插件需要更新的 DSH，请更新此安装器后重试')
  if ([plugin, core, catalog].some(value => !semver.satisfies(nodeVersion, value.engines?.node ?? '*'))) throw Error('最新插件需要更新的 Node.js，请升级 Node.js 后重试')
  if (!semver.satisfies(catalog.version, core.dependencies?.[CATALOG] ?? '')) throw Error('latest 目录包与主插件不兼容')
  const entries = catalog.cannbotWorkflowCatalog?.workflows
  if (catalog.cannbotWorkflowCatalog?.schemaVersion !== 1 || !Array.isArray(entries) || !entries.length || new Set(entries.map(x => x.id)).size !== entries.length) throw Error('目录包格式不受支持')
  const workflows = []
  for (const entry of entries) {
    if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(entry.id) || entry.package !== `@cannbot-plugin/workflow-${entry.id}` || typeof entry.default !== 'boolean') throw Error('工作流目录包含无效条目')
    if (!entry.default) continue
    const value = await lookup(entry.package)
    if (!semver.satisfies(nodeVersion, value.engines?.node ?? '*')) throw Error(`工作流需要更新的 Node.js：${entry.id}`)
    if (value.cannbotWorkflow?.schemaVersion !== 1 || value.cannbotWorkflow.id !== entry.id || !semver.satisfies(value.version, catalog.dependencies?.[entry.package] ?? '')) throw Error(`工作流包不兼容：${entry.id}`)
    workflows.push({ id: entry.id, package: entry.package, version: value.version })
  }
  if (!workflows.length) throw Error('目录中没有默认工作流')
  return { plugin: plugin.version, core: core.version, catalog: catalog.version, dsh: DSH_VERSION, pnpm: PNPM_VERSION, workflows }
}
