// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

// Remote plugin catalog: the single extension point reserved for the future
// CANNBot plugin market.
//
// Today it is a static list of npm packages installed into the remote DSH
// profile. A market only has to replace `loadCatalog()` with something that
// fetches a private index (DSH already supports "custom plugin indexes"), while
// the install path below stays unchanged.
import { readFileSync, existsSync } from 'node:fs'
import { packageVersion } from '../package-root.js'

export const DEFAULT_CATALOG = {
  version: 1,
  entries: [
    {
      id: 'cannbot-dsh',
      package: '@cannbot-plugin/cannbot-dsh-server',
      version: packageVersion,
      profile: 'cannbot-server',
      required: true,
      label: 'CANNBot DSH (operator workbench)',
    },
  ],
}

export function normalizeEntry(raw) {
  if (!raw || typeof raw !== 'object') return null
  const pkg = typeof raw.package === 'string' ? raw.package.trim() : ''
  if (!pkg) return null
  return {
    id: typeof raw.id === 'string' && raw.id.trim() ? raw.id.trim() : pkg,
    package: pkg,
    version: typeof raw.version === 'string' ? raw.version.trim() : '',
    profile: typeof raw.profile === 'string' && raw.profile.trim() ? raw.profile.trim() : 'web',
    required: raw.required !== false,
    label: typeof raw.label === 'string' ? raw.label : pkg,
  }
}

export function normalizeCatalog(json) {
  const entries = Array.isArray(json && json.entries) ? json.entries.map(normalizeEntry).filter(Boolean) : []
  return { version: 1, entries }
}

/**
 * Load the catalog. A future market can point CANNBOT_REMOTE_CATALOG at a JSON
 * file (or swap this function for an HTTP fetch of a private index).
 */
export function loadCatalog(file) {
  if (file && existsSync(file)) {
    try {
      const parsed = normalizeCatalog(JSON.parse(readFileSync(file, 'utf8')))
      if (parsed.entries.length) return parsed
    } catch { /* fall through to default */ }
  }
  return normalizeCatalog(DEFAULT_CATALOG)
}

/** `dsh` argv that installs one entry into a profile (forwards to pnpm). */
export function installArgs(entry) {
  const spec = entry.version ? `${entry.package}@${entry.version}` : entry.package
  return ['plugin', '--profile', entry.profile, 'add', spec]
}

/** Registry flag appended when a mirror is configured. */
export function registryArgs(registry) {
  return registry ? ['--registry', registry] : []
}

/** Human readable, shell-safe-ish command line for logs. */
export function installCommandLine(entry, registry) {
  return ['dsh', ...installArgs(entry), ...registryArgs(registry)].join(' ')
}
