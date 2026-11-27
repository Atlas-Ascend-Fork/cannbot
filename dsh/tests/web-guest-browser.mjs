// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

// Run with CANNBOT_TEST_BROWSER pointing to a local Chromium executable.
import assert from 'node:assert/strict'
import { createServer } from 'node:http'
import { createHash } from 'node:crypto'
import { spawn } from 'node:child_process'
import { once } from 'node:events'
import { mkdtemp, readFile, realpath, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { openWebGuest } from '../plugin/backend/ssh/web-guest.js'

const listen = async handler => {
  const server = createServer(handler)
  server.listen(0, '127.0.0.1'); await once(server, 'listening')
  return server
}
const cookieReceipts = []
async function remoteHost(key) {
  const server = await listen((req, res) => {
    if (req.url === '/?token=' + key) {
      cookieReceipts.push([key + '-login', req.headers.cookie || ''])
      res.writeHead(303, { location: './', 'set-cookie': 'session=' + key + '; Path=/; HttpOnly; SameSite=Strict' }); res.end(); return
    }
    cookieReceipts.push([key, req.headers.cookie || ''])
    if (req.headers.cookie !== 'session=' + key) { res.writeHead(401).end(); return }
    if (req.url === '/check') { res.end(key); return }
    res.writeHead(200, { 'content-type': 'text/html' }).end(
      '<button id="run">Run</button><script>' +
      'run.onclick = async () => {const value=await (await fetch("/check")).text();' +
      'const ws=new WebSocket("ws://"+location.host+"/socket");ws.onopen=()=>ws.send(value);' +
      'ws.onmessage=e=>{parent.postMessage(e.data,"*");ws.close()}};' +
      'addEventListener("message", e=>{if(e.source===parent && e.data==="run")run.click()});parent.postMessage("loaded","*")</script>')
  })
  server.on('upgrade', (req, socket) => {
    cookieReceipts.push([key + '-ws', req.headers.cookie || ''])
    if (req.headers.cookie !== 'session=' + key || req.headers.origin !== 'http://127.0.0.1:' + server.address().port) return socket.destroy()
    const accept = createHash('sha1').update(req.headers['sec-websocket-key'] + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').digest('base64')
    socket.write('HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: ' + accept + '\r\n\r\n')
    socket.once('data', frame => {
      const length = frame[1] & 127, payload = Buffer.from(frame.subarray(6, 6 + length))
      for (let at = 0; at < payload.length; at++) payload[at] ^= frame[2 + at % 4]
      if (payload.toString() !== key) { socket.destroy(); return }
      socket.write(Buffer.concat([Buffer.from([129, length]), payload]))
    })
    socket.on('error', () => {})
  })
  return server
}

async function run() {
  const browser = process.env.CANNBOT_TEST_BROWSER
  assert.ok(browser, 'Set CANNBOT_TEST_BROWSER to a Chromium executable.')
  const temp = await realpath(tmpdir()), profile = await mkdtemp(join(temp, 'cannbot-web-guest-'))
  const servers = [], views = []
  let child, finish, responseTimer
  try {
    const done = new Promise(resolve => { finish = resolve })
    const parent = await listen((req, res) => {
      if (req.url === '/done') { res.end(); finish(); return }
      res.writeHead(200, { 'content-type': 'text/html', 'set-cookie': 'local=must-not-leave; HttpOnly; SameSite=Strict; Path=/' })
      res.end('<body><script>const urls=' + JSON.stringify(views.map(v => v.url)) +
        ';let i=0,frame;function start(){frame=document.createElement("iframe");frame.sandbox="allow-scripts allow-same-origin allow-forms";frame.src=urls[i];document.body.append(frame)}' +
        'onmessage=e=>{if(e.source!==frame.contentWindow || e.origin!==new URL(urls[i]).origin)return;' +
        'if(e.data==="loaded"){frame.contentWindow.postMessage("run",e.origin);return}' +
        'if(e.data!=="host"+i)return;frame.remove();if(++i<urls.length)start();else fetch("/done")};start()</script>')
    })
    servers.push(parent)
    const parentOrigin = 'http://127.0.0.1:' + parent.address().port
    for (const key of ['host0', 'host1']) {
      const remote = await remoteHost(key); servers.push(remote)
      const manager = { getConnection: () => ({ connected: true, token: key, localPort: remote.address().port }) }
      views.push(await openWebGuest(manager, key, parentOrigin))
    }
    child = spawn(browser, ['--headless', '--disable-gpu', '--disable-background-networking', '--no-first-run', '--remote-debugging-port=0', '--user-data-dir=' + profile, parentOrigin], { windowsHide: true, stdio: 'ignore' })
    await Promise.race([done, new Promise((_, reject) => { responseTimer = setTimeout(() => reject(new Error('Guest handshake timed out. ' + JSON.stringify(cookieReceipts))), 25000) })])
    for (const key of ['host0', 'host1']) {
      assert.deepEqual(cookieReceipts.filter(([name]) => name === key + '-login'), [[key + '-login', '']])
      assert.deepEqual(cookieReceipts.filter(([name]) => name === key + '-ws'), [[key + '-ws', 'session=' + key]])
      assert.ok(cookieReceipts.some(([name]) => name === key))
      assert.ok(cookieReceipts.filter(([name]) => name === key).every(([, value]) => value === 'session=' + key))
    }
    console.log('Two embedded views authenticated, submitted HTTP requests, and exchanged WebSocket messages with isolated cookies.')
  } finally {
    clearTimeout(responseTimer)
    if (child && child.exitCode === null) {
      const exited = once(child, 'exit')
      try {
        const [port, path] = (await readFile(join(profile, 'DevToolsActivePort'), 'utf8')).trim().split(/\r?\n/)
        const control = new WebSocket('ws://127.0.0.1:' + port + path)
        await once(control, 'open'); control.send(JSON.stringify({ id: 1, method: 'Browser.close' }))
      } catch { child.kill() }
      await exited
    }
    for (const view of views) view.close()
    for (const server of servers) { server.closeAllConnections(); server.close() }
    if (dirname(await realpath(profile)) === temp) await rm(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 })
  }
}
await run()
