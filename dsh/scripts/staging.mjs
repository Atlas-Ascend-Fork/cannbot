import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

export async function withStaging(prefix, action) {
  const directory = mkdtempSync(join(tmpdir(), prefix))
  const abort = new AbortController()
  const interrupt = () => { process.exitCode = 130; abort.abort(new Error('Interrupted')) }
  const terminate = () => { process.exitCode = 143; abort.abort(new Error('Terminated')) }
  process.on('SIGINT', interrupt)
  process.on('SIGTERM', terminate)
  try { return await action(directory, abort.signal) }
  finally {
    rmSync(directory, { recursive: true, force: true })
    process.removeListener('SIGINT', interrupt)
    process.removeListener('SIGTERM', terminate)
  }
}
