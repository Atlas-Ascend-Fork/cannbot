// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { createHash } from 'node:crypto'
import { existsSync, lstatSync, readFileSync, readdirSync } from 'node:fs'
import { join, resolve, sep } from 'node:path'
import { gzipSync } from 'node:zlib'
import { packageRoot } from './package-root.js'

// Reproducible npm-style archive. Only declared release files are copied;
// credentials, node_modules, local profiles and build checkouts are excluded.
export function createArtifact(root = packageRoot()) {
  const manifest = JSON.parse(readFileSync(join(root, 'package.json'), 'utf8'))
  if (manifest.name !== '@cannbot-plugin/cannbot-dsh') throw new Error('Not a CANNBot DSH main package')
  for (const required of ['lib/index.js', 'lib/client.js', 'remote/deploy-package.mjs']) {
    if (!existsSync(join(root, required))) throw new Error('当前 CANNBot 主插件尚未构建，请先运行本仓构建命令。')
  }
  return createPackageArtifact(root)
}

/** The same deterministic npm archive writer for the main package and short alias. */
export function createPackageArtifact(root, { licensePath = join(root, '..', 'LICENSE') } = {}) {
  const manifest = JSON.parse(readFileSync(join(root, 'package.json'), 'utf8'))
  const entries = new Map()
  function add(relative, actual = join(root, relative)) {
    if (!relative || relative.startsWith('/') || relative.split(/[\\/]/).some(part => part === '..' || part === 'node_modules')) throw new Error('Unsafe release path')
    const info = lstatSync(actual)
    if (info.isSymbolicLink()) throw new Error('Release inputs must not contain symbolic links')
    if (info.isDirectory()) { for (const child of readdirSync(actual).sort()) add(relative + '/' + child, join(actual, child)); return }
    if (!info.isFile()) throw new Error('Unsupported release input')
    entries.set(relative.replaceAll('\\', '/'), readFileSync(actual))
  }
  add('package.json')
  for (const entry of manifest.files || []) {
    const candidate = resolve(root, entry)
    if (!candidate.startsWith(resolve(root) + sep) || /[*?]/.test(entry)) throw new Error('Unsupported release whitelist')
    const source = entry === 'LICENSE' && !existsSync(candidate) ? licensePath : candidate
    add(entry, source)
  }
  const chunks = []
  let total = 0
  for (const [relative, bytes] of [...entries].sort(([left], [right]) => left.localeCompare(right))) {
    total += bytes.length
    if (total > 128 * 1024 * 1024) throw new Error('CANNBot release exceeds 128 MiB')
    const header = Buffer.alloc(512)
    let name = 'package/' + relative, prefix = ''
    if (Buffer.byteLength(name) > 100) { const at = name.lastIndexOf('/'); prefix = name.slice(0, at); name = name.slice(at + 1) }
    if (Buffer.byteLength(name) > 100 || Buffer.byteLength(prefix) > 155) throw new Error('Release filename too long')
    header.write(name, 0, 100); header.write(prefix, 345, 155)
    const octal = (value, offset, size) => header.write(value.toString(8).padStart(size - 1, '0') + '\0', offset, size)
    octal(0o644, 100, 8); octal(0, 108, 8); octal(0, 116, 8); octal(bytes.length, 124, 12); octal(0, 136, 12)
    header.fill(32, 148, 156); header.write('0', 156); header.write('ustar\0', 257); header.write('00', 263)
    octal(header.reduce((sum, byte) => sum + byte, 0), 148, 7); header[155] = 32
    chunks.push(header, bytes, Buffer.alloc((512 - bytes.length % 512) % 512))
  }
  chunks.push(Buffer.alloc(1024))
  const bytes = gzipSync(Buffer.concat(chunks), { level: 9 })
  return { bytes, hash: createHash('sha256').update(bytes).digest('hex'), version: manifest.version }
}
