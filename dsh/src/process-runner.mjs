import { spawn } from 'node:child_process'

/** Wait for termination before callers release locks or remove staging files. */
export function runProcess(command, args, { signal, timeoutMs, graceMs = 1000, onData, ...options } = {}) {
  signal?.throwIfAborted()
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { ...options, detached: true })
    let stopped, escalation, timer
    const kill = force => {
      if (!child.pid) return
      try { process.kill(-child.pid, force ? 'SIGKILL' : 'SIGTERM') } catch {}
    }
    const stop = reason => {
      if (stopped) return
      stopped = reason
      kill(false)
      escalation = setTimeout(() => kill(true), graceMs)
    }
    const abort = () => stop(signal.reason ?? new Error('Operation cancelled'))
    const cleanup = () => { clearTimeout(timer); clearTimeout(escalation); signal?.removeEventListener('abort', abort) }
    if (onData) { child.stdout?.on('data', onData); child.stderr?.on('data', onData) }
    signal?.addEventListener('abort', abort, { once: true })
    if (signal?.aborted) abort()
    if (timeoutMs !== undefined) timer = setTimeout(() => stop(new Error('Initialization timed out')), timeoutMs)
    child.on('error', error => { cleanup(); reject(error) })
    child.on('close', (code, exitSignal) => {
      if (stopped) kill(true)
      cleanup()
      if (stopped) reject(stopped)
      else if (code !== 0) reject(new Error(`Command failed: ${command} (exit ${code ?? exitSignal})`))
      else resolve()
    })
  })
}
