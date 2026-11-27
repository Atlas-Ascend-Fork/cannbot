// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { randomUUID } from 'node:crypto'
import { copyFile, mkdir, mkdtemp, readFile, rename, rm, writeFile } from 'node:fs/promises'
import { dirname, isAbsolute, join, relative, resolve } from 'node:path'
import { pathToFileURL } from 'node:url'
import { getBytes, httpsUrl, installerVersion, requiredDocuments, requireCompatible } from '../installers/common/release.mjs'
import { buildCurrent } from './build-current.mjs'
import { editions } from './editions.mjs'
import { buildEditionArchives } from './package-editions.mjs'
import { project } from './source.mjs'

const readJson = async path => JSON.parse(await readFile(path, 'utf8'))

function directoryUrl(value) {
  const url = httpsUrl(value)
  if (!url.pathname.endsWith('/')) throw new Error('Release directory paths must end with /')
  return url
}

function fileUrl(path, directory) {
  const file = new URL(path, directory)
  file.search = directory.search
  return file.href
}

async function copyFeedFile(staging, target, path) {
  const destination = join(target, path)
  const pending = destination + '.' + randomUUID() + '.tmp'
  await mkdir(dirname(destination), { recursive: true })
  try {
    await copyFile(join(staging, path), pending)
    await rename(pending, destination)
  } finally { await rm(pending, { force: true }) }
}

async function publishedEditions(registry, version, download) {
  const packages = {}
  let buildId
  for (const [edition, name] of Object.entries(editions)) {
    const endpoint = new URL(name + '/' + encodeURIComponent(version), registry)
    const pkg = JSON.parse(await download(endpoint.href, 1024 * 1024))
    if (pkg.name !== name || pkg.version !== version || pkg.cannbotEdition !== edition || !pkg.cannbotBuildId) {
      throw new Error('Missing published ' + edition + ' build metadata for ' + name + '@' + version)
    }
    if (buildId && pkg.cannbotBuildId !== buildId) throw new Error('Published client and server have different build IDs')
    buildId = pkg.cannbotBuildId
    packages[edition] = { name, url: httpsUrl(pkg.dist.tarball).href }
  }
  return { buildId, packages }
}

/** Assemble the public npm feed or a self-hosted release directory. */
export async function assembleFeed({ root, output, config, build = buildCurrent, archives = buildEditionArchives, download = getBytes }) {
  const base = directoryUrl(config.assetBaseUrl)
  const documentBase = config.documentBaseUrl && directoryUrl(config.documentBaseUrl)
  const documentPages = config.documentPageBaseUrl && directoryUrl(config.documentPageBaseUrl)
  const legal = await readJson(join(root, 'tools/legal-manifest.json'))
  if (!legal.version?.trim()) throw new Error('Set the agreement version in tools/legal-manifest.json')
  const source = await readJson(join(root, 'package.json'))
  const dshRange = source.engines.dsh
  if (!config.hosts || !Object.keys(config.hosts).length) throw new Error('Supply the DSH download information for each supported platform')
  for (const [arch, host] of Object.entries(config.hosts)) {
    if (!/^(win32|linux|darwin)-(arm64|x64)$/.test(arch)) throw new Error('Unknown platform: ' + arch)
    requireCompatible(dshRange, host.version)
    if (arch.startsWith('win32-') && httpsUrl(host.url).hostname !== 'download.deepseek.com') throw new Error('Use the official Windows DSH download address')
  }

  const files = new Map()
  function asset(path, bytes) {
    files.set(path, bytes)
    return fileUrl(path, base)
  }
  // Legal text and plugins can be released independently.
  const documents = []
  const legalDirectory = join(root, 'legal')
  if (!/^[a-zA-Z0-9][a-zA-Z0-9._-]*$/.test(legal.version)) throw new Error('Use a version number or date for the agreement directory')
  for (const { id, title, path } of legal.documents) {
    if (!/^[a-z][a-z0-9-]{0,63}$/.test(id)) throw new Error('Invalid legal document id')
    const sourcePath = resolve(legalDirectory, path)
    const inside = relative(legalDirectory, sourcePath)
    if ((inside.startsWith('..') || isAbsolute(inside)) && !['LICENSE','THIRD_PARTY_NOTICES.md'].some(name => sourcePath === join(root, name))) throw new Error('Unexpected legal file path')
    const bytes = await readFile(sourcePath)
    if (!bytes.toString('utf8').trim()) throw new Error('Empty legal document: ' + id)
    const filename = inside.split('\\').join('/')
    const url = documentBase
      ? fileUrl(filename, documentBase)
      : asset('legal/' + legal.version + '/' + id + '.txt', bytes)
    const document = { id, title, url }
    if (documentPages) document.viewUrl = fileUrl(filename, documentPages)
    documents.push(document)
  }
  for (const id of requiredDocuments) {
    if (!documents.some(doc => doc.id === id)) throw new Error('Missing required installation document: ' + id)
  }

  let release
  if (config.packageRegistry) {
    release = await publishedEditions(directoryUrl(config.packageRegistry), source.version, download)
  } else {
    await build({ root })
    const pair = await archives(root)
    const packages = {}
    for (const edition of Object.keys(editions)) {
      const pkg = pair[edition]
      packages[edition] = { name: pkg.name, url: asset('releases/' + pair.buildId + '/' + edition + '.tgz', pkg.bytes) }
    }
    release = { buildId: pair.buildId, packages }
  }
  const manifest = { schemaVersion: 1, channel: 'stable', version: source.version, buildId: release.buildId,
    minInstallerVersion: config.minInstallerVersion ?? installerVersion, dshRange, hosts: config.hosts,
    packages: release.packages, legal: { version: legal.version, documents } }
  await mkdir(output, { recursive: true })
  const directory = await mkdtemp(join(output, 'release-'))
  try {
    for (const [path, data] of files) {
      await mkdir(dirname(join(directory, path)), { recursive: true })
      await writeFile(join(directory, path), data)
    }
    await writeFile(join(directory, 'manifest.json'), JSON.stringify(manifest, null, 2) + '\n')
    return directory
  } catch (error) {
    await rm(directory, { recursive: true, force: true })
    throw error
  }
}

if (process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === import.meta.url) {
  try {
    const [configFile, ...extra] = process.argv.slice(2)
    if (extra.length) throw new Error('Usage: node tools/release.mjs [release-config.json]')
    const root = resolve(project)
    const config = await readJson(configFile || join(root, 'tools/release-config.json'))
    const directory = await assembleFeed({ root, output: join(root, 'dist/feed'), config })
    if (configFile) {
      console.log(directory)
    } else {
      const target = join(root, 'release')
      await copyFeedFile(directory, target, 'manifest.json')
      console.log(target)
    }
  } catch (error) { console.error(error.message); process.exitCode = 1 }
}
