// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { test } from 'node:test'
import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const installer = fileURLToPath(new URL('../../installers/windows/install-all.ps1', import.meta.url))
const executable = 'D:\\Test DSH\\DeepSeek Harness.exe'
const windowsOnly = { skip: process.platform !== 'win32' && 'requires Windows PowerShell 5.1' }

function shutdown(processes, options = {}) {
  const source = String.raw`
$ErrorActionPreference = 'Stop'
$scenario = $env:CANNBOT_CLOSE_SCENARIO | ConvertFrom-Json
$script:now = [DateTime]::Parse('2026-11-12T12:00:00')
$script:elapsed = 0
$script:closedIds = @()
$script:forcedIds = @()
$script:firstStopAt = $null
$script:messages = @()
$appProcessName = 'DeepSeek Harness'
$script:testProcesses = @()
foreach ($entry in $scenario.processes) {
    $process = [pscustomobject]@{
        Id = $entry.id
        Path = $entry.path
        HasExited = $false
        MainWindowHandle = [IntPtr]$entry.handle
        ExitAfter = $entry.exitAfter
        ExitAfterStop = $entry.exitAfterStop
        ReplaceAt = $entry.replaceAt
        StartTime = [DateTime]::Parse('2026-11-12T11:00:00')
    }
    $process | Add-Member -MemberType ScriptMethod -Name CloseMainWindow -Value {
        $script:closedIds += $this.Id
        # DSH's real close handler hides the window to the tray.
        $this.MainWindowHandle = [IntPtr]::Zero
        return $true
    }
    $script:testProcesses += $process
}
function Get-Process {
    param($Name, $Id, $ErrorAction)
    foreach ($process in $script:testProcesses) {
        if ($null -ne $Id -and $process.Id -ne $Id) { continue }
        if ($script:forcedIds -contains $process.Id) { continue }
        if ($null -ne $process.ExitAfterStop -and $null -ne $script:firstStopAt -and $script:elapsed -ge ($script:firstStopAt + $process.ExitAfterStop)) { continue }
        if ($null -ne $process.ReplaceAt -and $script:elapsed -ge $process.ReplaceAt) { $process.StartTime = [DateTime]::Parse('2026-11-12T11:59:59') }
        if ($null -eq $process.ExitAfter -or $script:elapsed -lt $process.ExitAfter) { $process }
    }
}
function Stop-Process {
    param($Id, [switch]$Force, $ErrorAction)
    $script:forcedIds += $Id
    if ($null -eq $script:firstStopAt) { $script:firstStopAt = $script:elapsed }
}
function Start-Process { throw 'Tests must never launch an installer.' }
function Get-Date { return $script:now }
function Start-Sleep {
    param([int]$Milliseconds, [int]$Seconds)
    $delta = $Milliseconds + $Seconds * 1000
    $script:elapsed += $delta
    $script:now = $script:now.AddMilliseconds($delta)
}
function Say { param($text, $color) $script:messages += $text }

# Extract only the production function through PowerShell's parser. Never run
# the installer's main program, registry detection, downloads, or provisioning.
$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($env:CANNBOT_CLOSE_INSTALLER, [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw 'Installer does not parse under Windows PowerShell 5.1.' }
$function = $ast.Find({ param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Stop-DshIfRunning' }, $true)
if (-not $function) { throw 'Shutdown function not found.' }
Invoke-Expression $function.Extent.Text
$success = Stop-DshIfRunning -ExecutablePath $scenario.executable -GracePeriodSeconds $scenario.gracePeriod -ChildExitSeconds 15
[pscustomobject]@{
    success = $success
    closedIds = @($script:closedIds)
    forcedIds = @($script:forcedIds)
    elapsed = $script:elapsed
    messages = @($script:messages)
} | ConvertTo-Json -Depth 5 -Compress
`
  const result = spawnSync('powershell.exe', ['-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-EncodedCommand', Buffer.from(source, 'utf16le').toString('base64')], {
    env: {
      ...process.env,
      CANNBOT_CLOSE_INSTALLER: installer,
      CANNBOT_CLOSE_SCENARIO: JSON.stringify({ executable, processes, gracePeriod: 3, ...options }),
    },
    encoding: 'utf8', windowsHide: true, timeout: 15_000,
  })
  assert.ifError(result.error)
  assert.equal(result.status, 0, result.stdout + result.stderr)
  const outcome = JSON.parse(result.stdout.trim())
  for (const id of outcome.forcedIds) {
    const process = processes.find((candidate) => candidate.id === id)
    assert.ok(process?.handle, 'shutdown must never force-kill a background renderer/Host process')
    assert.equal(process.path.toLowerCase(), executable.toLowerCase(), 'only the selected installation may be stopped')
  }
  return outcome
}

test('installer shutdown returns immediately when the target is not running', windowsOnly, () => {
  const result = shutdown([])
  assert.equal(result.success, true)
  assert.deepEqual(result.closedIds, [])
  assert.deepEqual(result.forcedIds, [])
  assert.equal(result.elapsed, 0)
})

test('installer closes only main windows and waits for renderer shutdown', windowsOnly, () => {
  const result = shutdown([
    { id: 101, path: executable, handle: 123, exitAfter: 500 },
    { id: 102, path: executable, handle: 0, exitAfter: 750 },
  ])
  assert.equal(result.success, true)
  assert.deepEqual(result.closedIds, [101])
  assert.deepEqual(result.forcedIds, [])
  assert.equal(result.elapsed, 750)
})

test('installer allows a configurable graceful wait without forcing a normal exit', windowsOnly, () => {
  const result = shutdown([
    { id: 101, path: executable, handle: 123, exitAfter: 4000 },
    { id: 102, path: executable, handle: 0, exitAfter: 4500 },
  ], { gracePeriod: 5 })
  assert.equal(result.success, true)
  assert.deepEqual(result.closedIds, [101])
  assert.deepEqual(result.forcedIds, [])
  assert.equal(result.elapsed, 4500)
})

test('installer stops only the recorded main process then waits for child cleanup', windowsOnly, () => {
  const result = shutdown([
    { id: 101, path: executable, handle: 123 },
    { id: 102, path: executable, handle: 0, exitAfterStop: 750 },
    { id: 103, path: executable, handle: 0, exitAfterStop: 1250 },
  ])
  assert.equal(result.success, true)
  assert.deepEqual(result.closedIds, [101])
  assert.deepEqual(result.forcedIds, [101])
  assert.equal(result.elapsed, 4250)
})

test('installer blocks deployment if children remain after main-process shutdown', windowsOnly, () => {
  const result = shutdown([
    { id: 101, path: executable, handle: 123 },
    { id: 102, path: executable, handle: 0 },
  ])
  assert.equal(result.success, false)
  assert.deepEqual(result.closedIds, [101])
  assert.deepEqual(result.forcedIds, [101])
  assert.equal(result.elapsed, 18_000)
  assert.match(result.messages.join('\n'), /background processes were not force-killed/)
})

test('installer leaves same-name processes from another installation untouched', windowsOnly, () => {
  const result = shutdown([
    { id: 101, path: executable.toLowerCase(), handle: 123, exitAfter: 500 },
    { id: 999, path: 'E:\\Another DSH\\DeepSeek Harness.exe', handle: 999 },
  ])
  assert.equal(result.success, true)
  assert.deepEqual(result.closedIds, [101])
  assert.deepEqual(result.forcedIds, [])
  assert.equal(result.elapsed, 500)
})

test('installer refuses to close a process whose executable path cannot be verified', windowsOnly, () => {
  const result = shutdown([{ id: 101, path: null, handle: 123 }])
  assert.equal(result.success, false)
  assert.deepEqual(result.closedIds, [])
  assert.deepEqual(result.forcedIds, [])
  assert.equal(result.elapsed, 0)
  assert.match(result.messages.join('\n'), /Cannot verify/)
})

test('installer does not kill a tray-only DSH process with no main window', windowsOnly, () => {
  const result = shutdown([{ id: 101, path: executable, handle: 0 }])
  assert.equal(result.success, false)
  assert.deepEqual(result.closedIds, [])
  assert.deepEqual(result.forcedIds, [])
  assert.equal(result.elapsed, 3000)
})

test('installer refuses to stop a reused main PID whose start time changed', windowsOnly, () => {
  const result = shutdown([{ id: 101, path: executable, handle: 123, replaceAt: 2500 }])
  assert.equal(result.success, false)
  assert.deepEqual(result.closedIds, [101])
  assert.deepEqual(result.forcedIds, [])
  assert.equal(result.elapsed, 3000)
  assert.match(result.messages.join('\n'), /changed identity/)
})
