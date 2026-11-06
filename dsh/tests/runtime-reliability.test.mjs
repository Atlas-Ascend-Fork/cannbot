import test from 'node:test'
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { once } from 'node:events'
import { mkdtempSync, rmSync, writeFileSync, existsSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { acquireFileLock } from '../packages/install/lib/file-lock.mjs'
import { runProcess } from '../src/process-runner.mjs'

test('exclusive locks serialize contenders and release after owner crashes', async () => {
  const directory = mkdtempSync(join(tmpdir(), 'cannbot-lock-test-')), path = join(directory, 'lock')
  const module = new URL('../packages/install/lib/file-lock.mjs', import.meta.url).href
  const child = spawn(process.execPath, ['--input-type=module', '-e', `import {acquireFileLock} from ${JSON.stringify(module)};await acquireFileLock(process.argv[1]);process.send('locked');setInterval(()=>{},1000)`, path], { stdio: ['ignore', 'pipe', 'pipe', 'ipc'] })
  try {
    await once(child, 'message')
    await assert.rejects(acquireFileLock(path), /still running/)
    const exited = once(child, 'exit'); child.kill('SIGKILL'); await exited
    let active = 0, peak = 0
    await Promise.all(Array.from({ length: 4 }, async () => {
      const release = await acquireFileLock(path, 5000)
      try { peak = Math.max(peak, ++active); await new Promise(resolve => setTimeout(resolve, 30)); active-- }
      finally { release() }
    }))
    assert.equal(peak, 1)
    // Legacy truncated JSON locks cannot block the new kernel-managed lock.
    writeFileSync(path, '{')
    const release = await acquireFileLock(path); release(); release()
  } finally { child.kill('SIGKILL'); rmSync(directory, { recursive: true, force: true }) }
})

test('timeout kills a child that ignores SIGTERM', async () => {
  const start = Date.now()
  let ready = false
  await assert.rejects(runProcess(process.execPath, ['-e', "process.on('SIGTERM',()=>{});console.log('ready');setInterval(()=>{},1000)"], {
    timeoutMs: 500, graceMs: 100, stdio: ['ignore', 'pipe', 'pipe'], onData: () => { ready = true },
  }), /timed out/)
  assert.equal(ready, true)
  assert.ok(Date.now() - start < 5000)
})

test('signal interruption cleans staging after terminating child', async () => {
  const module = new URL('../scripts/staging.mjs', import.meta.url).href
  const runner = new URL('../src/process-runner.mjs', import.meta.url).href
  const child = spawn(process.execPath, ['--input-type=module', '-e', `import {withStaging} from ${JSON.stringify(module)};import {runProcess} from ${JSON.stringify(runner)};await withStaging('cannbot-signal-test-',async(dir,signal)=>{process.send(dir);await runProcess(process.execPath,['-e','setInterval(()=>{},1000)'],{signal,stdio:'ignore'})}).catch(()=>{});`], { stdio: ['ignore', 'pipe', 'pipe', 'ipc'] })
  const [directory] = await once(child, 'message')
  const exited = once(child, 'exit'); child.kill('SIGTERM'); await exited
  assert.equal(existsSync(directory), false)
})
