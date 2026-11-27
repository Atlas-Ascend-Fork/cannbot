// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { test } from 'node:test'
import assert from 'node:assert/strict'
import { mkdtempSync, readFileSync, copyFileSync, existsSync, rmSync, writeFileSync } from 'node:fs'
import { join, dirname, resolve } from 'node:path'
import { tmpdir } from 'node:os'
import { spawnSync } from 'node:child_process'

test('standalone EXE extracts the current package without a checkout; refuses overwrites and silent installation', { skip: process.platform !== 'win32' }, () => {
  const root = mkdtempSync(join(tmpdir(), 'cannbot-exe-test-'))
  try {
    const file = join(root, "安装 包 & user's.exe")
    copyFileSync(new URL('../dist/CANNBot-Setup.exe', import.meta.url), file)
    const destination = join(root, '独立 解包')
    // NSIS options quote the value, not the /NAME= prefix.
    const run = args => spawnSync(file, args, { argv0: `"${file}"`, cwd: root, windowsHide: true, windowsVerbatimArguments: true, timeout: 30000, encoding: 'utf8' })
    const result = run(['/S', `/EXTRACTONLY="${destination}"`])
    assert.equal(result.status, 0, result.error?.message || result.stdout + result.stderr)
    const packageRoot = join(destination, 'package')
    for (const part of ['installers/common/release-source.json', 'installers/common/release.mjs', 'installers/windows/provision.ps1']) assert.ok(existsSync(join(packageRoot, part)), part)
    for (const part of ['node_modules', '.git', '.dsh-source.json', 'tools/build-current.mjs', 'installation-documents', 'INSTALLATION_NOTICES.html', 'INSTALLATION_NOTICES.txt']) assert.equal(existsSync(join(packageRoot, part)), false, part)
    for (const part of ['installers/common/release.mjs','installers/windows/release.ps1', 'THIRD_PARTY_NOTICES.md', 'installers/windows/install-all.ps1', 'installers/windows/provision.ps1', 'installers/windows/ensure-workbench.mjs', 'installers/windows/setup-worker.ps1']) {
      const normalized = bytes => bytes.toString('utf8').replaceAll('\r\n', '\n')
      assert.equal(normalized(readFileSync(join(packageRoot, part))), normalized(readFileSync(new URL('../' + part, import.meta.url))), `Regenerate the installer: ${part}`)
    }
    assert.deepEqual(readFileSync(join(packageRoot, 'LICENSE')), readFileSync(new URL('../../LICENSE', import.meta.url)))
    const source = JSON.parse(readFileSync(join(packageRoot, 'installers/common/release-source.json')))
    assert.equal(source.manifestUrl, 'https://api.gitcode.com/api/v5/repos/cann/cannbot/raw/dsh/release/manifest.json?ref=master')
    const icon = readFileSync(join(packageRoot, 'installers/windows/setup-icon.ico'))
    assert.equal(icon.readUInt16LE(2), 1, 'desktop shortcut uses an ICO image')
    assert.equal(icon.readUInt16LE(4), 1)
    const image = icon.subarray(icon.readUInt32LE(18))
    assert.deepEqual([...image.subarray(0, 8)], [137, 80, 78, 71, 13, 10, 26, 10])
    assert.equal(image.readUInt32BE(16), 128)
    assert.equal(image.readUInt32BE(20), 128)
    assert.equal(existsSync(join(packageRoot, 'artwork')), false, 'SVG renderer is build-only')
    const notices = readFileSync(join(packageRoot, 'THIRD_PARTY_NOTICES.md'), 'utf8')
    assert.match(notices, /Copyright Eemeli Aro/)
    assert.match(notices, /NSIS 3\.0\.4\.1/)
    assert.match(notices, /Copyright \(C\) 1999-2018 Contributors/)
    writeFileSync(join(destination, 'keep.txt'), 'user data')
    assert.equal(run(['/S', `/EXTRACTONLY="${destination}"`]).status, 2)
    assert.equal(readFileSync(join(destination, 'keep.txt'), 'utf8'), 'user data')
    assert.equal(run(['/S']).status, 2, 'normal install cannot bypass disclosure')
  } finally {
    assert.equal(dirname(resolve(root)), resolve(tmpdir()))
    rmSync(root, { recursive: true, force: true })
  }
})
