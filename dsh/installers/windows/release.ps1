# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.

[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidateSet('prepare','download','host-version','receipt')][string]$Action,
    [string]$DshExecutable,
    [string]$HostVersion
)
$ErrorActionPreference = 'Stop'
$packageRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$releaseDirectory = Join-Path $packageRoot 'release'
$common = Join-Path $packageRoot 'installers\common'
$config = Get-Content -LiteralPath (Join-Path $common 'release-source.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not $config.manifestUrl) { throw 'The release download address has not been configured.' }
[IO.Directory]::CreateDirectory($releaseDirectory) | Out-Null
$runtime = $null
if ($DshExecutable) {
    $candidate = Join-Path (Split-Path -Parent $DshExecutable) 'resources\runtime\primary-runtime\dependencies\node\bin\node.exe'
    if (Test-Path -LiteralPath $candidate -PathType Leaf) { $runtime = $candidate }
}
if (-not $runtime) {
    if (-not [Environment]::Is64BitOperatingSystem) { throw 'The Windows installer requires a 64-bit operating system.' }
    $runtime = Join-Path $releaseDirectory 'node.exe'
    if (-not (Test-Path -LiteralPath $runtime -PathType Leaf)) {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        $client = New-Object Net.WebClient
        try { $client.DownloadFile('https://nodejs.org/dist/v24.22.3/win-x64/node.exe', $runtime) }
        finally { $client.Dispose() }
    }
}
$arguments = @((Join-Path $common 'release.mjs'), $Action, $releaseDirectory)
if ($Action -in @('host-version','receipt')) { $arguments += $HostVersion }
& $runtime @arguments
exit $LASTEXITCODE
