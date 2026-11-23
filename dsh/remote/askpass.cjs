// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// Licensed under CANN Open Software License Agreement Version 2.0. See LICENSE.
const http = require('node:http')
if (process.argv.length !== 3 || process.env.SSH_ASKPASS_PROMPT) process.exit(1)
const port = Number(process.env.CANNBOT_ASKPASS_PORT)
if (!Number.isInteger(port) || port < 1 || port > 65535) process.exit(1)
const request = http.request({ host: '127.0.0.1', port, path: '/', method: 'POST',
  headers: { authorization: 'Bearer ' + process.env.CANNBOT_ASKPASS_TOKEN, 'content-type': 'application/json' } }, response => {
  if (response.statusCode !== 200) { response.resume(); process.exitCode = 1; return }
  let answer = ''
  response.setEncoding('utf8').on('data', chunk => { answer += chunk }).on('end', () => { process.stdout.write(answer + '\n'); answer = '' })
})
request.setTimeout(125000, () => request.destroy())
request.on('error', () => { process.exitCode = 1 })
request.end(JSON.stringify({ prompt: process.argv[2], callId: process.env.CANNBOT_ASKPASS_CALL }))
