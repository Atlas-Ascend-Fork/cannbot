// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

// Paths and environment resolution for the CANNBot Remote host plugin.
import { homedir } from 'node:os'
import { join, dirname } from 'node:path'
import { mkdirSync } from 'node:fs'

export function dshHome() {
  return process.env.DSH_HOME && process.env.DSH_HOME.trim()
    ? process.env.DSH_HOME.trim()
    : join(homedir(), '.dsh')
}

export function remoteHome() {
  return join(dshHome(), 'cannbot-remote')
}

export function serversFile() {
  return join(remoteHome(), 'servers.json')
}

export function stateFile() {
  return join(remoteHome(), 'state.json')
}

export function logsDir() {
  return join(remoteHome(), 'logs')
}

export function sshConfigPath() {
  return process.env.CANNBOT_REMOTE_SSH_CONFIG && process.env.CANNBOT_REMOTE_SSH_CONFIG.trim()
    ? process.env.CANNBOT_REMOTE_SSH_CONFIG.trim()
    : join(homedir(), '.ssh', 'config')
}

export function sshBinary() {
  const override = process.env.CANNBOT_REMOTE_SSH && process.env.CANNBOT_REMOTE_SSH.trim()
  return override || 'ssh'
}

export { resolveSshBinary } from './ssh-binary.js'

export function ensureDir(path) {
  mkdirSync(path, { recursive: true })
  return path
}

export function ensureParent(path) {
  return ensureDir(dirname(path))
}
