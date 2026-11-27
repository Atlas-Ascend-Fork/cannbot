// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

// Remote bootstrap: run an idempotent POSIX script over SSH and parse its markers.
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { pathToFileURL } from 'node:url'
import { join } from 'node:path'
import { packageRoot } from '../package-root.js'
import { shQuote } from './exec.js'

export const REMOTE_SCRIPT_URL = pathToFileURL(join(packageRoot(), 'remote', 'bootstrap-remote.sh'))

export function readRemoteScript() {
  // Normalise transport artifacts before streaming to `bash -s`: a BOM or CRLF
  // (e.g. when a script is piped through PowerShell) makes bash fail on `$'\r'`.
  const text = readFileSync(fileURLToPath(REMOTE_SCRIPT_URL), 'utf8')
  return text.replace(/^\uFEFF/, '').replace(/\r\n/g, '\n')
}

/** Build the `ssh` argv used for a remote command. */
export function sshArgs({ server, binary = 'ssh', options = [] } = {}) {
  const args = ['-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', '-o', 'NumberOfPasswordPrompts=0']
  if (options.length) args.push(...options)

  const inConfig = server && server.inSshConfig
  if (!inConfig && server && server.hostName) {
    if (server.port && Number(server.port) !== 22) args.push('-p', String(server.port))
    const target = server.user ? `${server.user}@${server.hostName}` : server.hostName
    return { args, target, command: binary }
  }
  return { args, target: (server && server.alias) || '', command: binary }
}

/** ssh argv that streams the bootstrap script into `bash -s`. */
export function bootstrapSshInvocation({ server, binary = 'ssh', remotePort, dshVersion, pluginVersion, registry, profile = 'web', prepareOnly = false }) {
  const { args, target, command } = sshArgs({ server, binary })
  const scriptArgs = [
    String(remotePort || ''),
    String(dshVersion || ''),
    String(pluginVersion || ''),
    String(registry || ''),
    String(profile || 'web'),
  ]
  if (prepareOnly) scriptArgs.push('0', 'prepare-only')
  // OpenSSH joins remote argv into a shell command; separate empty argv entries
  // disappear. Quote every value to preserve reuse sentinels and literal data.
  const quote = (value) => "'" + value.replace(/'/g, "'\\''") + "'"
  const remoteCommand = 'bash -s -- ' + scriptArgs.map(quote).join(' ')
  return { command, args: [...args, target, remoteCommand], target }
}

export const MARKERS = {
  step: /^CANNBOT_STEP=(.+)$/m,
  ok: /^CANNBOT_OK=1$/m,
  token: /^CANNBOT_TOKEN=(.*)$/m,
  remotePort: /^CANNBOT_REMOTE_PORT=(\d+)$/m,
  webLog: /^CANNBOT_WEB_LOG=(.*)$/m,
  reuse: /^CANNBOT_REUSE=(\d)$/m,
  error: /^CANNBOT_ERROR=(.*)$/m,
  dshVersion: /^CANNBOT_DSH_VERSION=(.*)$/m,
  pluginVersion: /^CANNBOT_PLUGIN_VERSION=(.*)$/m,
  ascendEnv: /^CANNBOT_ASCEND_ENV=(.*)$/m,
}

/** Remote inspection: which dsh and plugin are already installed? */
export const STATE_MARKERS = {
  dsh: /^CANNBOT_STATE_DSH=(.*)$/m,
  plugin: /^CANNBOT_STATE_PLUGIN=(.*)$/m,
}

export function stateProbeCommand(profile = 'web') {
  // The bootstrap installs node/dsh under ~/.local, which is NOT on PATH for a
  // non-interactive ssh command, so the probe must extend PATH itself.
  const versionScript = "const fs=require('node:fs'),p=require('node:path');const base=p.join(process.env.DSH_HOME||p.join(process.env.HOME,'.dsh'),'profiles',process.argv[1],'node_modules');for(const name of ['@cannbot-plugin/cannbot-dsh-server']){try{console.log(JSON.parse(fs.readFileSync(p.join(base,name,'package.json'),'utf8')).version);process.exit(0)}catch{}}console.log('none')"
  return [
    'export PATH="$HOME/.local/bin:$PATH"',
    `printf 'CANNBOT_STATE_DSH=%s\\n' "$(dsh --version 2>/dev/null || echo none)"`,
    `printf 'CANNBOT_STATE_PLUGIN=%s\\n' "$(node -e ${shQuote(versionScript)} ${shQuote(profile)} 2>/dev/null || echo none)"`,
  ].join('; ')
}

export function stateSshInvocation({ server, binary = 'ssh', profile = 'web' }) {
  const { args, target, command } = sshArgs({ server, binary })
  return { command, args: [...args, target, stateProbeCommand(profile)], target }
}

export function parseStateOutput(text) {
  const source = String(text || '')
  const dsh = STATE_MARKERS.dsh.exec(source)
  const plugin = STATE_MARKERS.plugin.exec(source)
  const clean = (value) => {
    const trimmed = (value || '').trim()
    return trimmed === 'none' || trimmed === 'unknown' ? '' : trimmed
  }
  return { dshVersion: clean(dsh && dsh[1]), pluginVersion: clean(plugin && plugin[1]) }
}

/**
 * Parse bootstrap stdout/stderr into a structured result.
 * @param {string} text
 */
export function parseBootstrapOutput(text) {
  const source = String(text || '')
  const steps = source
    .split(/\r?\n/)
    .map((line) => MARKERS.step.exec(line))
    .filter(Boolean)
    .map((match) => match[1].trim())
  const tokenMatch = MARKERS.token.exec(source)
  const portMatch = MARKERS.remotePort.exec(source)
  const logMatch = MARKERS.webLog.exec(source)
  const reuseMatch = MARKERS.reuse.exec(source)
  const errorMatch = MARKERS.error.exec(source)
  const dshVersionMatch = MARKERS.dshVersion.exec(source)
  const pluginVersionMatch = MARKERS.pluginVersion.exec(source)
  const ascendEnvMatch = MARKERS.ascendEnv.exec(source)
  return {
    ok: MARKERS.ok.test(source),
    token: tokenMatch ? tokenMatch[1].trim() : '',
    remotePort: portMatch ? Number(portMatch[1]) : null,
    webLog: logMatch ? logMatch[1].trim() : '',
    reused: reuseMatch ? reuseMatch[1] === '1' : false,
    error: errorMatch ? errorMatch[1].trim() : '',
    dshVersion: dshVersionMatch ? dshVersionMatch[1].trim() : '',
    pluginVersion: pluginVersionMatch ? pluginVersionMatch[1].trim() : '',
    ascendEnv: ascendEnvMatch ? ascendEnvMatch[1].trim() : '',
    steps,
  }
}

/** Extract the human-readable failure hint from bootstrap output. */
export function failureHint(result, exitCode) {
  if (result && result.error) return result.error
  if (exitCode === -1) return 'ssh 无法启动（检查 OpenSSH Client 是否安装）'
  if (exitCode === -2) return '远端引导超时'
  return `远端引导失败（exit ${exitCode}）`
}
