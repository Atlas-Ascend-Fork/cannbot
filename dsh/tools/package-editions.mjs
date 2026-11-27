// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { createHash } from 'node:crypto'
import { cp, mkdir, readFile, writeFile } from 'node:fs/promises'
import { join, resolve, sep } from 'node:path'
import { createPackageArtifact } from './package-archive.mjs'
import { editionManifest, editions } from './editions.mjs'
import { withStaging } from './staging.mjs'

const json = value => JSON.stringify(value, null, 2) + '\n'

/** Produce the standalone server and the identical archive shipped inside its client. */
export async function buildEditionArchives(root) {
  const source = JSON.parse(await readFile(join(root, 'package.json'), 'utf8'))
  return withStaging('cannbot-editions-', async temporary => {
    const prepared = {}
    for (const edition of Object.keys(editions)) {
      const directory = join(temporary, edition)
      await mkdir(directory)
      const manifest = editionManifest(source, edition)
      await writeFile(join(directory, 'package.json'), json(manifest))
      for (const file of manifest.files) {
        if (!resolve(root, file).startsWith(resolve(root) + sep) || file.split(/[\\/]/).some(part => ['..', '.', ''].includes(part))) throw new Error('Invalid edition file: ' + file)
        const path = edition === 'server' && file === 'lib' ? join(root, 'lib/server') : join(root, file)
        if (file === 'README.md') {
          const source = await readFile(path, 'utf8')
          const readerGuide = source.split('## 源码目录')[0].replace(/ · \[算子开发示例\]\(USAGE.md\)/, '')
          await writeFile(join(directory, file), readerGuide.trimEnd() + '\n')
        } else if (file === 'cordis.patch.yml' && edition === 'server') {
          const patch = await readFile(path, 'utf8')
          await writeFile(join(directory, file), patch.replace("'" + editions.client + "'", "'" + editions.server + "'"))
        } else {
          await cp(path, join(directory, file), {
            recursive: true, verbatimSymlinks: true,
            filter: entry => entry !== join(root, 'lib/.cannbot-build.json') && (entry !== join(root, 'lib/server') || edition === 'server'),
          })
        }
      }
      // Both registration faces must exist, including in a manually staged build.
      for (const output of ['index.js', 'client.js']) await readFile(join(directory, 'lib', output))
      prepared[edition] = createPackageArtifact(directory).hash
    }
    // Includes code, static assets, role metadata and notices of both editions.
    const buildId = createHash('sha256').update(prepared.client + prepared.server).digest('hex')
    const packages = {}
    for (const edition of ['server','client']) {
      const directory = join(temporary, edition)
      const manifest = editionManifest(source, edition, buildId)
      await writeFile(join(directory, 'package.json'), json(manifest))
      if (edition === 'client') {
        const server = packages.server
        await writeFile(join(directory, 'remote/server.tgz'), server.bytes)
        await writeFile(join(directory, 'remote/server.json'), json({ name: editions.server, version: server.version, buildId }))
      }
      packages[edition] = { ...createPackageArtifact(directory), name: manifest.name }
    }
    return { buildId, ...packages }
  })
}
