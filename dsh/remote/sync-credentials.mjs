// Standalone code sent as a static `node -e` program. Secrets arrive on stdin.
import { createRequire } from 'node:module'
import { lstat, mkdir, readFile, realpath } from 'node:fs/promises'
import { homedir } from 'node:os'
import { dirname, isAbsolute, join, resolve } from 'node:path'
import { pathToFileURL } from 'node:url'
import { execFile } from 'node:child_process'
import { promisify } from 'node:util'

const RECORD_KEY = 'deepseek-account-platform/default'
const MAX_INPUT_BYTES = 64 * 1024
const ISSUER = 'https://platform.deepseek.com'
const execFileAsync = promisify(execFile)

function validGrant(record) {
  if (!record || typeof record !== 'object' || Array.isArray(record)
    || Object.keys(record).sort().join(',') !== 'kind,payload' || record.kind !== 'grant') return false
  const payload = record.payload
  return Boolean(payload && typeof payload === 'object' && !Array.isArray(payload)
    && Object.keys(payload).sort().join(',') === 'issuer,token,version'
    && payload.version === 1 && payload.issuer === ISSUER
    && typeof payload.token === 'string' && /^[\x21-\x7e]+$/.test(payload.token)
    && !payload.token.startsWith('dsh_mock_'))
}

async function readInput(input) {
  let size = 0
  const chunks = []
  for await (const chunk of input) {
    const bytes = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk)
    size += bytes.length
    if (size > MAX_INPUT_BYTES) throw new Error('invalid input')
    chunks.push(bytes)
  }
  return JSON.parse(Buffer.concat(chunks).toString('utf8'))
}

/** Resolve the installed DSH's own libraries, including custom npm prefixes. */
export async function loadDshDependencies(dshExecutable) {
  if (typeof dshExecutable !== 'string' || !isAbsolute(dshExecutable)) return null
  const executable = await realpath(dshExecutable)
  const require = createRequire(executable)
  const load = name => import(pathToFileURL(require.resolve(name)).href)
  const [credentials, atomic, yaml] = await Promise.all([
    load('@deepseek-ai/dsh-credentials-local'),
    load('@deepseek-ai/dsh-atomic-write'),
    load('yaml'),
  ])
  if (credentials.DOCUMENT_VERSION !== 1
    || typeof credentials.parseCredentialsDocument !== 'function'
    || typeof atomic.withFileLock !== 'function' || typeof atomic.writeFileAtomic !== 'function'
    || typeof yaml.parseDocument !== 'function') return null
  return { ...atomic, parseCredentialsDocument: credentials.parseCredentialsDocument, parseDocument: yaml.parseDocument }
}

/** Admit only the default, live-watched store in the effective profile. */
export function supportsDefaultStore(text, parseDocument) {
  const document = parseDocument(text, { prettyErrors: false, uniqueKeys: true })
  if (document.errors.length) return false
  const rows = document.toJS()
  if (!Array.isArray(rows)) return false
  const stores = []
  const accounts = []
  let uncertain = false
  const visit = (entries, ancestorUncertain = false) => {
    for (const row of entries) {
      if (!row || typeof row !== 'object' || row.disabled === true) continue
      const dynamic = ancestorUncertain || (row.disabled !== undefined && row.disabled !== false)
      if (row.name === 'cordis:include') { uncertain = true; continue }
      if (row.name === 'cordis:group' || row.group === true) {
        if (!Array.isArray(row.config)) uncertain = true
        else visit(row.config, dynamic)
        continue
      }
      if (row.id === 'credentials' || row.name === '@deepseek-ai/dsh-credentials-local') {
        if (dynamic || row.name !== '@deepseek-ai/dsh-credentials-local') uncertain = true
        stores.push(row)
      }
      if (row.id === 'deepseek-account' || row.name === '@deepseek-ai/dsh-deepseek-account-platform') {
        if (dynamic || row.name !== '@deepseek-ai/dsh-deepseek-account-platform') uncertain = true
        accounts.push(row)
      }
    }
  }
  visit(rows)
  if (uncertain || stores.length !== 1 || accounts.length !== 1) return false
  const store = stores[0].config ?? {}
  const account = accounts[0].config ?? {}
  if (!store || typeof store !== 'object' || Array.isArray(store)
    || !account || typeof account !== 'object' || Array.isArray(account)) return false
  return store.path === undefined && store.dshHome === undefined
    && (store.watch === undefined || store.watch === true)
    && (account.platformOrigin === undefined || account.platformOrigin === ISSUER)
    && (account.inferenceOrigin === undefined || account.inferenceOrigin === 'https://api.deepseek.com')
}

/** The dump is private memory only: it can contain unrelated deployment secrets. */
export async function inspectProfile({ dshExecutable, profile, dshHome, dependencies }) {
  if (typeof profile !== 'string' || !/^[A-Za-z0-9_-]+$/.test(profile) || profile === 'node_modules') return false
  const executable = await realpath(dshExecutable)
  const result = await execFileAsync(process.execPath, [executable, '--profile', profile, '--dump-config'], {
    env: { ...process.env, DSH_HOME: dshHome },
    windowsHide: true, timeout: 20_000, maxBuffer: 4 * 1024 * 1024,
  })
  return supportsDefaultStore(result.stdout, dependencies.parseDocument)
}

/** Reject symlinked paths rather than redirecting a credential write elsewhere. */
async function checkPath(filename) {
  let current = filename
  while (true) {
    try {
      const info = await lstat(current)
      if (info.isSymbolicLink()) throw new Error('unsafe path')
      if (current === filename) {
        if (!info.isFile() || (process.platform !== 'win32' && (info.mode & 0o077))) throw new Error('unsafe file')
      } else if (!info.isDirectory()) throw new Error('unsafe directory')
    } catch (error) {
      if (error.code !== 'ENOENT') throw error
    }
    const parent = dirname(current)
    if (parent === current) break
    current = parent
  }
}

/** Merge exactly one grant while holding the same lock as the official store. */
export async function mergeAccountGrant({ record, dshHome, dependencies }) {
  if (!validGrant(record)) return 'unsupported'
  const { parseCredentialsDocument, parseDocument, withFileLock, writeFileAtomic } = dependencies
  const filename = join(resolve(dshHome), '.credentials.yaml')
  await checkPath(filename)
  await mkdir(dirname(filename), { recursive: true, mode: 0o700 })
  return withFileLock(filename, async () => {
    await checkPath(filename)
    let original
    try { original = await readFile(filename, 'utf8') } catch (error) {
      if (error.code !== 'ENOENT') throw error
      original = 'version: 1\nrefs: {}\nrecords: {}\n'
    }
    let stored
    try { stored = parseCredentialsDocument(original, filename) } catch { return 'unsupported' }
    const existing = stored.records.get(RECORD_KEY)
    if (existing !== undefined) {
      return validGrant(existing) && existing.payload.token === record.payload.token ? 'unchanged' : 'remote-preserved'
    }
    const document = parseDocument(original, { prettyErrors: false, uniqueKeys: true })
    if (document.errors.length) return 'unsupported'
    document.setIn(['records', RECORD_KEY], record)
    const next = document.toString()
    try { parseCredentialsDocument(next, filename) } catch { return 'unsupported' }
    await checkPath(filename)
    await writeFileAtomic(filename, next, { mode: 0o600, dirMode: 0o700 })
    return 'synced'
  }, { waitMs: 30_000 })
}

/** CLI boundary: always emits one fixed status, never exception text or secrets. */
export async function runRemoteSync({
  dshExecutable,
  profile = 'web',
  dshHome = process.env.DSH_HOME || join(homedir(), '.dsh'),
  input = process.stdin,
  output = process.stdout,
  loadDependencies = loadDshDependencies,
  checkProfile = inspectProfile,
} = {}) {
  let status = 'failed'
  try {
    let record
    try { record = await readInput(input) } catch { status = 'unsupported' }
    if (record !== undefined) {
      if (!validGrant(record)) status = 'unsupported'
      else {
        let dependencies
        try { dependencies = await loadDependencies(dshExecutable) } catch { /* unsupported installation */ }
        let supported = false
        if (dependencies) {
          try { supported = await checkProfile({ dshExecutable, profile, dshHome, dependencies }) } catch { /* unsupported profile */ }
        }
        status = supported ? await mergeAccountGrant({ record, dshHome, dependencies }) : 'unsupported'
      }
    }
  } catch { /* The private payload and storage exceptions must never escape. */ }
  output.write(`CANNBOT_CREDENTIALS_STATUS=${status}\n`)
  return status
}
