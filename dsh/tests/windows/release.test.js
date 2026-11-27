// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import test from 'node:test'
import assert from 'node:assert/strict'
import { copyFile, mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { dirname, join } from 'node:path'
import { tmpdir } from 'node:os'
import { pathToFileURL } from 'node:url'
import { spawnSync } from 'node:child_process'

test('Windows release reader displays the selected legal text and installs exactly the revision accepted before the feed changes', {skip:process.platform !== 'win32'}, async t => {
  const root = await mkdtemp(join(tmpdir(), 'cannbot-release-'))
  t.after(() => rm(root, {recursive:true, force:true}))
  const common = join(root,'installers/common'), windows = join(root,'installers/windows'), feed = join(root,'fixture')
  await Promise.all([common,windows,feed].map(dir=>mkdir(dir,{recursive:true})))
  await copyFile(new URL('../../installers/common/release.mjs',import.meta.url),join(common,'release.mjs'))
  await copyFile(new URL('../../installers/windows/release.ps1',import.meta.url),join(windows,'release.ps1'))
  const exe = join(root,'desktop','DSH.exe'), node = join(dirname(exe),'resources/runtime/primary-runtime/dependencies/node/bin/node.exe')
  await mkdir(dirname(node),{recursive:true})
  await copyFile(process.execPath,node)
  await writeFile(join(common,'release-source.json'),JSON.stringify({manifestUrl:'https://release.test/manifest.json'}))
  const asset = async (file, text) => {
    await writeFile(join(feed,file),text)
    return {url:'https://release.test/'+file}
  }
  const ids = ['user-agreement', 'privacy-policy', 'open-source-notices']
  const manifest = {schemaVersion:1,channel:'stable',version:'1.2.3',buildId:'test',minInstallerVersion:'1.0.0',expiresAt:new Date(Date.now()+86400000).toISOString(),
    dshRange:'>=0.1.1-rc.1 <0.3.0',legal:{version:'legal-v1',documents:await Promise.all(ids.map(async id=>({id,title:id,viewUrl:'https://release.test/documents/'+id,...await asset(id,'正文 '+id)})))},
    packages:{client:{name:'@cannbot-plugin/cannbot-dsh',...await asset('client.tgz','fixed build')},server:{name:'@cannbot-plugin/cannbot-dsh-server',...await asset('server.tgz','server build')}},
    hosts:{'win32-x64':{version:'0.2.1-rc.3',url:'https://download.deepseek.com/desktop/test.exe'}}}
  const bytes = Buffer.from(JSON.stringify(manifest))
  await writeFile(join(feed,'manifest.json'),bytes)
  const preload = join(root,'local-feed.mjs')
  await writeFile(preload,`import {readFile} from 'node:fs/promises';import {join} from 'node:path';globalThis.fetch=async url=>new Response(await readFile(join(process.env.TEST_FEED,new URL(url).pathname.slice(1))))`)
  const run = (action, ...extra) => spawnSync('powershell.exe',['-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',join(windows,'release.ps1'),'-Action',action,'-DshExecutable',exe,...extra],{
    windowsHide:true,timeout:30000,encoding:'utf8',env:{...process.env,TEST_FEED:feed,NODE_OPTIONS:'--import='+pathToFileURL(preload).href}})
  function ok(result) { assert.ifError(result.error); assert.equal(result.status,0,result.stdout+result.stderr) }
  ok(run('prepare'))
  assert.equal(await readFile(join(root,'installation-documents/privacy-policy.txt'),'utf16le'),'\ufeff正文 privacy-policy')
  const picker = await readFile(join(root, 'installation-documents/index.ini'), 'utf16le')
  assert.ok(picker.includes('count=3'))
  for (const id of ids) {
    assert.ok(picker.includes('file=' + id + '.txt'))
    assert.ok(picker.includes('url=https://release.test/documents/' + id))
  }
  const revised = '更新后的隐私政策\r\n'.repeat(3000)
  await writeFile(join(feed, 'privacy-policy'), revised)
  ok(run('prepare'))
  assert.equal(await readFile(join(root, 'installation-documents/privacy-policy.txt'), 'utf16le'), '\ufeff' + revised)
  await writeFile(join(feed,'manifest.json'),'a new or invalid release')
  ok(run('download'))
  assert.equal(await readFile(join(root,'release/client.tgz'),'utf8'),'fixed build')
  ok(run('host-version','-HostVersion','0.2.1-rc.3'))
  assert.notEqual(run('host-version','-HostVersion','0.3.0').status,0)
  ok(run('receipt','-HostVersion',root))
  assert.equal(JSON.parse(await readFile(join(root,'.cannbot-install.json'))).version,'1.2.3')
  assert.equal(JSON.parse(await readFile(join(root,'.cannbot-install.json'))).legalVersion,'legal-v1')
})
