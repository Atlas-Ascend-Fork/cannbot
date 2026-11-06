import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
export const project = fileURLToPath(new URL('../', import.meta.url))
export function resolveSource(explicit) {
  const local = resolve(project, '.dsh-source.json')
  const saved = existsSync(local) ? JSON.parse(readFileSync(local, 'utf8')).path : undefined
  const source = resolve(explicit || process.env.DSH_SOURCE || saved || resolve(project, '../deepseek-harness'))
  const manifest = JSON.parse(readFileSync(resolve(source, 'package.json'), 'utf8'))
  if (manifest.name !== '@deepseek-ai/dsh-root' || manifest.version !== '0.2.1-rc.3') throw new Error('Use the official DSH 0.2.1-rc.3 source checkout.')
  return source
}
