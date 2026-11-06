import { DatabaseSync } from 'node:sqlite'
import { mkdir, open } from 'node:fs/promises'
import { dirname } from 'node:path'

/** Never unlink this inode. The kernel releases the SQLite transaction on exit.
 * The suffix separates legacy JSON locks from the database format. */
export async function acquireFileLock(path, timeout = 0) {
  await mkdir(dirname(path), { recursive: true })
  const file = path + '.sqlite3'
  const handle = await open(file, 'a', 0o600)
  await handle.close()
  const database = new DatabaseSync(file)
  const deadline = Date.now() + timeout
  try {
    for (;;) {
      try { database.exec('BEGIN EXCLUSIVE'); break }
      catch (error) {
        if (error.errcode !== 5) throw error // SQLITE_BUSY
        if (Date.now() >= deadline) throw new Error('Another installation or content operation is still running')
        await new Promise(resolve => setTimeout(resolve, Math.min(250, Math.max(1, deadline - Date.now()))))
      }
    }
  } catch (error) { database.close(); throw error }
  let released = false
  return () => { if (!released) { released = true; database.close() } }
}
