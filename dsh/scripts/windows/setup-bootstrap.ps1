# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.

$ErrorActionPreference = 'Stop'
$runRoot = $null
try {
    $text = [IO.File]::ReadAllText($env:CANNBOT_SETUP_FILE)
    $parts = $text -split '(?m)^::CANNBOT_PAYLOAD\r?\n', 2
    if ($parts.Count -ne 2) { throw 'Installer payload is missing. Download the complete CMD file and retry.' }
    $bytes = [Convert]::FromBase64String($parts[1])
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $hash = [BitConverter]::ToString($sha.ComputeHash($bytes)).Replace('-', '').ToLowerInvariant() } finally { $sha.Dispose() }
    if ($hash -ne '__PAYLOAD_SHA256__') { throw 'Installer checksum mismatch. Download the file again.' }
    $runRoot = Join-Path $env:LOCALAPPDATA ('CANNBot\Installer\' + [Guid]::NewGuid().ToString('N'))
    [void](New-Item -ItemType Directory -Path $runRoot)
    $archive = Join-Path $runRoot 'payload.zip'
    [IO.File]::WriteAllBytes($archive, $bytes)
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [IO.Compression.ZipFile]::ExtractToDirectory($archive, $runRoot)
    $packageRoot = Join-Path $runRoot 'package'
    $installer = Join-Path $packageRoot 'scripts\windows\install-all.ps1'
    foreach ($relative in @('lib\index.js', 'lib\client.js', 'LICENSE', 'THIRD_PARTY_NOTICES.md', 'scripts\windows\install-all.ps1', 'scripts\windows\provision.ps1')) {
        if (-not (Test-Path -LiteralPath (Join-Path $packageRoot $relative) -PathType Leaf)) { throw "Incomplete installer: $relative" }
    }
    Write-Host "Installer files: $runRoot"
    if ($env:CANNBOT_SETUP_MODE -eq '--extract-only') { exit 0 }
    if (-not $env:CANNBOT_SETUP_MODE) {
        $window = Join-Path $packageRoot 'scripts\windows\setup-window.ps1'
        & $window -Installer $installer -PackageRoot $packageRoot -RunRoot $runRoot
        exit $LASTEXITCODE
    }
    Start-Transcript -Path (Join-Path $runRoot 'installation.log') | Out-Null
    try {
        & powershell -NoProfile -ExecutionPolicy Bypass -File $installer -PackageRoot $packageRoot
        if ($LASTEXITCODE -ne 0) { throw "Installation failed (exit $LASTEXITCODE)." }
    } finally { Stop-Transcript | Out-Null }
    exit 0
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    if ($runRoot) { Write-Host "Installer files and log: $runRoot" }
    if (-not $env:CANNBOT_SETUP_MODE) {
        Add-Type -AssemblyName System.Windows.Forms
        [void][Windows.Forms.MessageBox]::Show($_.Exception.Message, 'CANNBot Setup', 'OK', 'Error')
    }
    exit 1
}
