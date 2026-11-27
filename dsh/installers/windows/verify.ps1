# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.

# Locate a usable node, run every test file in-process (the sandbox here cannot
# spawn children with piped stdio, so `node --test <dir>` would fail with EPERM),
# and summarise the result. Exits non-zero when any file fails.
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $repoRoot

function Resolve-Node {
    $candidates = @()
    $cmd = Get-Command node -ErrorAction SilentlyContinue
    if ($cmd) { $candidates += $cmd.Source }
    $bundled = Join-Path $env:USERPROFILE '.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe'
    if (Test-Path -LiteralPath $bundled) { $candidates += $bundled }
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) { return $candidate }
    }
    throw 'node not found: install Node.js >= 24.9 or keep the DSH runtime in place'
}

$node = Resolve-Node
Write-Host "[verify] node: $node"
Write-Host "[verify] $(& $node --version)"

$testFiles = Get-ChildItem -Path (Join-Path $repoRoot 'tests\remote'), (Join-Path $repoRoot 'tests\windows') -Filter '*.test.js' | Sort-Object FullName
if (-not $testFiles) { throw 'no test files found' }

$failed = 0
$totalPass = 0
foreach ($file in $testFiles) {
    $output = & $node $file.FullName 2>&1
    $exit = $LASTEXITCODE
    $passLine = ($output | Select-String -Pattern 'pass (\d+)$' | Select-Object -First 1)
    $failLine = ($output | Select-String -Pattern 'fail (\d+)$' | Select-Object -First 1)
    $passed = if ($passLine) { [int]$passLine.Matches[0].Groups[1].Value } else { 0 }
    $failedCount = if ($failLine) { [int]$failLine.Matches[0].Groups[1].Value } else { 0 }
    $totalPass += $passed
    $status = if ($exit -eq 0 -and $failedCount -eq 0) { 'PASS' } else { 'FAIL' }
    if ($status -eq 'FAIL') {
        $failed++
        Write-Host ("[verify] {0} {1} (pass {2}, fail {3})" -f $status, $file.Name, $passed, $failedCount) -ForegroundColor Red
        $output | Select-String -Pattern '\u2716|AssertionError|Error:' | Select-Object -First 8 | ForEach-Object { Write-Host "         $($_.Line.Trim())" }
    } else {
        Write-Host ("[verify] {0} {1} (pass {2})" -f $status, $file.Name, $passed) -ForegroundColor Green
    }
}

# Static guards for the client half: it must never contain ESM/JSX syntax.
$client = Join-Path $repoRoot 'lib\client.js'
$clientText = Get-Content -LiteralPath $client -Raw
$violations = @()
if ($clientText -match '(?m)^\s*(import|export)\s') { $violations += 'contains import/export' }
if ($clientText -match '(?<![\w.])<[A-Z][A-Za-z0-9]*[\s/>{]') { $violations += 'contains JSX element syntax' }
if ($clientText -notmatch '__ModuleLoader__\.load') { $violations += 'missing __ModuleLoader__.load wrapper' }
if ($violations.Count) {
    $failed++
    Write-Host "[verify] FAIL client bundle guard: $($violations -join '; ')" -ForegroundColor Red
} else {
    Write-Host '[verify] PASS client bundle guard' -ForegroundColor Green
}

Write-Host "[verify] total assertions passed: $totalPass"
if ($failed -gt 0) {
    Write-Host "[verify] $failed check(s) failed" -ForegroundColor Red
    exit 1
}
Write-Host '[verify] all checks passed' -ForegroundColor Green
