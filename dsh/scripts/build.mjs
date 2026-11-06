import { spawnSync } from 'node:child_process'
import { resolve } from 'node:path'
import { project, resolveSource } from './source.mjs'
const checkout = resolveSource()
const result = spawnSync(process.execPath, [resolve(checkout, 'node_modules/tsdown/dist/run.mjs'), '--config-loader', 'native', '--config', 'tsdown.config.ts'], {
  cwd: project, stdio: 'inherit', env: { ...process.env, DSH_CLIENT_BUILD_PROFILE: 'local' },
})
process.exit(result.status ?? 1)
