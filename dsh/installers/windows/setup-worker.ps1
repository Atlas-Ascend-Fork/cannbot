# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.

[CmdletBinding()]
param([Parameter(Mandatory)][string]$RunRoot, [Parameter(Mandatory)][string]$InstallDirectory)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$progressPath = Join-Path $RunRoot 'progress.json'
$resultPath = Join-Path $RunRoot 'result.ini'
$code = 1
$executable = ''
$message = ''
$transcribing = $false
try {
    [IO.File]::WriteAllText((Join-Path $RunRoot 'worker.ini'), "[setup]`r`npid=$PID`r`n", [Text.Encoding]::Unicode)
    Start-Transcript -LiteralPath (Join-Path $RunRoot 'installation.log') -Force | Out-Null
    $transcribing = $true
    & (Join-Path $PSScriptRoot 'install-all.ps1') -DisclosureAccepted -InstallDirectory $InstallDirectory -ProgressPath $progressPath
    $state = Get-Content -LiteralPath $progressPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($state.phase -ne 'complete' -or -not (Test-Path -LiteralPath $state.executable -PathType Leaf)) { throw 'Installation verification failed.' }
    $executable = $state.executable
    $code = 0
} catch {
    $message = ($_.Exception.Message -replace '[\r\n]', ' ')
    Write-Host $_ -ForegroundColor Red
} finally {
    if ($transcribing) { Stop-Transcript | Out-Null }
    [IO.File]::WriteAllText($resultPath + '.tmp', "[setup]`r`ncode=$code`r`nexecutable=$executable`r`nerror=$message`r`n", [Text.Encoding]::Unicode)
    Move-Item -LiteralPath ($resultPath + '.tmp') -Destination $resultPath -Force
}
exit $code
