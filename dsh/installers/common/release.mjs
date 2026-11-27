// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { mkdir, readFile, writeFile, rename, rm } from 'node:fs/promises'
import { join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

export const installerVersion = '1.0.0'
export const packages = { client: '@cannbot-plugin/cannbot-dsh', server: '@cannbot-plugin/cannbot-dsh-server' }
export const requiredDocuments = ['user-agreement', 'privacy-policy', 'open-source-notices']
const versionPattern = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*))?$/
function parts(value) {
  if (typeof value !== 'string' || !versionPattern.test(value)) throw new Error('Invalid software version: ' + value)
  const [, major, minor, patch, pre] = versionPattern.exec(value)
  return { core: [major, minor, patch].map(Number), pre: pre?.split('.') }
}
export function compareVersions(a, b) {
  const left = parts(a), right = parts(b)
  for (let i = 0; i < 3; ++i) if (left.core[i] !== right.core[i]) return left.core[i] - right.core[i]
  if (!left.pre || !right.pre) return Number(!left.pre) - Number(!right.pre)
  for (let i = 0; i < Math.max(left.pre.length, right.pre.length); ++i) {
    const x = left.pre[i], y = right.pre[i]
    if (x === y) continue
    if (!x || !y) return x ? 1 : -1
    const nx = /^\d+$/.test(x), ny = /^\d+$/.test(y)
    if (nx && ny) return Number(x) - Number(y)
    if (nx !== ny) return nx ? -1 : 1
    return x < y ? -1 : 1
  }
  return 0
}
export function requireCompatible(range, version) {
  const bounds = /^>=(\S+)\s+<(\S+)$/.exec(range)
  if (!bounds || compareVersions(version, bounds[1]) < 0 || compareVersions(version, bounds[2]) >= 0) throw new Error('Unsupported DSH ' + version + '. Required: ' + range)
}
export function httpsUrl(value) {
  const url = new URL(value)
  if (url.protocol !== 'https:' || url.username || url.password || url.hash || /[\x00-\x20]/.test(value)) throw new Error('A secure HTTPS release address is required')
  return url
}
export async function getBytes(url, maxSize) {
  let target = httpsUrl(url)
  let response
  const signal = AbortSignal.timeout(180000)
  for (let redirect = 0; redirect <= 5; redirect++) {
    try {
      response = await fetch(target, { redirect: 'manual', signal })
    } catch (error) {
      throw new Error('无法访问 ' + target.origin + target.pathname + '，请检查网络连接后重试。', { cause: error })
    }
    if (![301, 302, 303, 307, 308].includes(response.status)) break
    const location = response.headers.get('location')
    await response.body?.cancel()
    if (!location || redirect === 5) throw new Error('Invalid release download redirect')
    target = httpsUrl(new URL(location, target).href)
  }
  if (!response.ok || !response.body || Number(response.headers.get('content-length')) > maxSize) throw new Error('Download failed (' + response.status + '): ' + url)
  const chunks = []
  let size = 0
  for await (const chunk of response.body) {
    size += chunk.length
    if (size > maxSize) throw new Error('Download exceeds size limit: ' + url)
    chunks.push(chunk)
  }
  return Buffer.concat(chunks)
}
export function parseManifest(bytes, now = Date.now()) {
  const manifest = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes))
  const { schemaVersion, channel, version, buildId, expiresAt, minInstallerVersion, dshRange, legal } = manifest
  parts(version)
  if (schemaVersion !== 1 || channel !== 'stable' || !/^[a-z0-9][a-z0-9._-]{0,127}$/i.test(buildId || '') ||
      (expiresAt != null && (!Number.isFinite(Date.parse(expiresAt)) || Date.parse(expiresAt) <= now)) || compareVersions(installerVersion, minInstallerVersion) < 0) throw new Error('Expired or unsupported release. Download the current installer.')
  const bounds = /^>=(\S+)\s+<(\S+)$/.exec(dshRange)
  if (!bounds || compareVersions(bounds[1], bounds[2]) >= 0) throw new Error('Invalid DSH compatibility range')
  for (const [edition, name] of Object.entries(packages)) {
    const item = manifest.packages?.[edition]
    if (item?.name !== name) throw new Error('Invalid ' + edition + ' release')
    httpsUrl(item.url)
  }
  if (!legal?.version || !Array.isArray(legal.documents) || legal.documents.length !== requiredDocuments.length) throw new Error('Missing required installation agreement')
  const ids = new Set()
  for (const item of legal.documents) {
    if (!/^[a-z][a-z0-9-]{0,63}$/.test(item.id) || ids.has(item.id) || !item.title || /[\x00-\x1f\[\]=]/.test(item.title)) throw new Error('Invalid installation document')
    ids.add(item.id)
    httpsUrl(item.url)
    if (item.viewUrl != null) httpsUrl(item.viewUrl)
  }
  if (requiredDocuments.some(id => !ids.has(id))) throw new Error('Missing required installation agreement')
  return manifest
}
export async function releaseSource(path) {
  const source = JSON.parse(await readFile(path, 'utf8'))
  if (!source.manifestUrl) throw new Error('The public release address has not been configured.')
  httpsUrl(source.manifestUrl)
  return source
}
export async function prepare(source, dir, download = getBytes) {
  await mkdir(dir, { recursive: true, mode: 0o700 })
  const bytes = await download(source.manifestUrl, 256 * 1024)
  const manifest = parseManifest(bytes)
  for (const doc of manifest.legal.documents) {
    await writeFile(join(dir, doc.id + '.txt'), await download(doc.url, 448 * 1024))
  }
  await writeFile(join(dir, 'manifest.json'), bytes)
  return manifest
}
export async function frozenRelease(dir) {
  return parseManifest(await readFile(join(dir, 'manifest.json')))
}
export async function getPackage(manifest, edition, dir, download = getBytes) {
  const pkg = manifest.packages[edition]
  if (!Object.hasOwn(packages, edition)) throw new Error('Invalid edition')
  const bytes = await download(pkg.url, 256 * 1024 * 1024)
  const path = join(dir, edition + '.tgz')
  await writeFile(path, bytes)
  return path
}
export async function recordInstallation(manifest, edition, profile) {
  const receipt = {
    schemaVersion: 1, edition, buildId: manifest.buildId, version: manifest.version,
    legalVersion: manifest.legal.version, acceptedAt: new Date().toISOString(),
  }
  const path = join(profile, '.cannbot-install.json'), temp = path + '.' + process.pid + '.tmp'
  try {
    await writeFile(temp, JSON.stringify(receipt, null, 2) + '\n', { mode: 0o600, flag: 'wx' })
    await rename(temp, path)
  } finally { await rm(temp, { force: true }) }
}
async function windows(action, dir, hostVersion) {
  const manifest = action === 'prepare'
    ? await prepare(await releaseSource(new URL('./release-source.json', import.meta.url)), dir)
    : await frozenRelease(dir)
  if (action === 'receipt') return recordInstallation(manifest, 'client', hostVersion)
  if (action === 'host-version') return requireCompatible(manifest.dshRange, hostVersion)
  const host = manifest.hosts?.['win32-x64']
  if (!host || httpsUrl(host.url).hostname !== 'download.deepseek.com') throw new Error('Missing official Windows setup information')
  requireCompatible(manifest.dshRange, host.version)
  if (action === 'download') return getPackage(manifest, 'client', dir)
  if (action !== 'prepare') throw new Error('Invalid release action')
  const directory = join(dir, '..', 'installation-documents')
  await mkdir(directory, { recursive: true })
  const ini = ['[documents]', 'count=' + manifest.legal.documents.length]
  for (const [i, doc] of manifest.legal.documents.entries()) {
    const content = await readFile(join(dir, doc.id + '.txt'), 'utf8')
    await writeFile(join(directory, doc.id + '.txt'), '\ufeff' + content, 'utf16le')
    ini.push('', '[' + i + ']', 'title=' + doc.title, 'file=' + doc.id + '.txt', 'url=' + (doc.viewUrl ?? doc.url))
  }
  await writeFile(join(directory, 'index.ini'), '\ufeff' + ini.join('\r\n') + '\r\n', 'utf16le')
}
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  windows(...process.argv.slice(2)).catch(error => { console.error(error.message); process.exitCode = 1 })
}
