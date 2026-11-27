# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.

# Install the current CANNBot main plugin, including remote support, on Desktop.
#
# The DSH desktop profile is application-owned: `dsh plugin --profile desktop`
# is refused by the CLI, so provisioning writes the profile directly.
#
#   .\provision.ps1            install / reinstall
#   .\provision.ps1 -Repair    re-apply the bundle list after a crash-recovery reset
#   .\provision.ps1 -Check     report status only
#   .\provision.ps1 -Uninstall remove the plugin from the profile
[CmdletBinding()]
param(
    [switch]$Repair,
    [switch]$Check,
    [switch]$Uninstall,
    [string]$PluginArchive = "",
    [string]$PluginVersion = "",
    [string]$BuildId = "",
    [string]$DshExecutable = ""
)

$ErrorActionPreference = 'Stop'

$PACKAGE_NAME = '@cannbot-plugin/cannbot-dsh'
$BUNDLE_ENTRY = '@cannbot-plugin/cannbot-dsh'


$dshHome = if ($env:DSH_HOME -and $env:DSH_HOME.Trim()) { $env:DSH_HOME.Trim() } else { Join-Path $env:USERPROFILE '.dsh' }
$profileDir = Join-Path $dshHome 'profiles\desktop'
$profilePkg = Join-Path $profileDir 'package.json'
$targetDir = Join-Path $profileDir 'node_modules\@cannbot-plugin\cannbot-dsh'

function Write-Step($message) { Write-Host "[provision] $message" }
function Write-Warn2($message) { Write-Host "[provision][warn] $message" -ForegroundColor Yellow }
function Resolve-Node {
    # Desktop 0.2.2 keeps its primary runtime beside the application. A clean
    # machine need not have a legacy ~/.dsh runtime or Node on PATH.
    if ($DshExecutable) {
        $appRoot = Split-Path -Parent $DshExecutable
        $desktopNode = Join-Path $appRoot 'resources\runtime\primary-runtime\dependencies\node\bin\node.exe'
        if (Test-Path -LiteralPath $desktopNode -PathType Leaf) { return $desktopNode }
    }
    $bundled = Join-Path $dshHome 'dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe'
    if (Test-Path -LiteralPath $bundled) { return $bundled }
    $command = Get-Command node -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    throw 'Cannot find the DSH Node.js runtime. Repair the DSH installation, then retry.'
}
function Get-Workbench([switch]$ReadOnly) {
    $node = Resolve-Node
    $helper = Join-Path $PSScriptRoot 'ensure-workbench.mjs'
    $arguments = @($helper, $profileDir)
    if ($ReadOnly) { $arguments += '--check' }
    else { $arguments += @($PluginArchive, $PluginVersion, $BuildId) }
    $lines = @(& $node @arguments)
    $code = $LASTEXITCODE
    $result = $null
    foreach ($line in $lines) {
        if ($line -like 'CANNBOT_WORKBENCH=*') { $result = $line.Substring(18) | ConvertFrom-Json }
        else { Write-Host $line }
    }
    if (-not $ReadOnly -and ($code -ne 0 -or -not $result)) { throw 'Official CANNBot workbench installation failed; profile was not changed.' }
    return $result
}
function Remove-RemotePlugin {
    # Preserve package backups and all user state. Renaming a junction never
    # traverses its store, and an existing npm package is recoverable too.
    if (Test-Path -LiteralPath $targetDir) {
        $backupTarget = $targetDir + '.before-uninstall-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff')
        Move-Item -LiteralPath $targetDir -Destination $backupTarget
    }
}
function Write-ProfileManifest {
    # Windows PowerShell 5.1's Set-Content -Encoding UTF8 adds a BOM. DSH reads
    # this file with JSON.parse, which rejects that leading U+FEFF character.
    # Use the same BOM-free encoding for install, repair, and uninstall.
    $json = ($pkg | ConvertTo-Json -Depth 100) + [Environment]::NewLine
    $tempPath = $profilePkg + '.' + [Guid]::NewGuid().ToString('N') + '.tmp'
    try {
        [IO.File]::WriteAllText($tempPath, $json, (New-Object System.Text.UTF8Encoding($false)))
        [IO.File]::Replace($tempPath, $profilePkg, [Management.Automation.Language.NullString]::Value)
    } finally { if (Test-Path -LiteralPath $tempPath) { Remove-Item -LiteralPath $tempPath -Force } }
}

Write-Step "dsh home : $dshHome"
Write-Step "profile  : $profileDir"

if (-not (Test-Path -LiteralPath $profilePkg)) {
    throw "desktop profile not found. Launch DeepSeek Harness once, quit it, then re-run this script."
}

$running = Get-Process -Name 'DeepSeek Harness' -ErrorAction SilentlyContinue
if ($running -and -not $Check) {
    Write-Host ''
    Write-Host '  DeepSeek Harness is running.' -ForegroundColor Yellow
    Write-Host '  Quit it completely (including the tray icon), then press Enter ...' -ForegroundColor Yellow
    [void](Read-Host)
    $running = Get-Process -Name 'DeepSeek Harness' -ErrorAction SilentlyContinue
    if ($running) {
        throw 'DeepSeek Harness is still running. Quit it completely and run this script again.'
    }
}

$pkg = Get-Content -LiteralPath $profilePkg -Raw -Encoding UTF8 | ConvertFrom-Json

if ($Check) {
    $installed = $true
    foreach ($relative in @('package.json', 'lib\index.js', 'lib\client.js', 'remote\sync-credentials.mjs', 'remote\deploy-package.mjs', 'cordis.patch.yml')) {
        if (-not (Test-Path -LiteralPath (Join-Path $targetDir $relative) -PathType Leaf)) { $installed = $false }
    }
    $listed = $false
    if ($pkg.dsh -and $pkg.dsh.profile -and $pkg.dsh.profile.bundles) {
        $listed = @($pkg.dsh.profile.bundles) -contains $BUNDLE_ENTRY
    }
    Write-Step "plugin files : $(if ($installed) { 'present' } else { 'missing' })"
    Write-Step "bundle entry : $(if ($listed) { 'listed' } else { 'missing' })"
    $cannbot = @()
    if ($pkg.dsh -and $pkg.dsh.profile -and $pkg.dsh.profile.bundles) { $cannbot = @($pkg.dsh.profile.bundles) | Where-Object { $_ -like '*cannbot*' } }
    Write-Step "cannbot bundles: $($cannbot -join ', ')"
    $bytes = [IO.File]::ReadAllBytes($profilePkg)
    if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
        Write-Warn2 'profile package.json has a UTF-8 BOM; DSH cannot start. Quit DSH, then run provision.ps1 -Repair.'
        exit 1
    }
    Write-Step 'profile encoding: UTF-8 without BOM'
    $workbench = Get-Workbench -ReadOnly
    if (-not $workbench) { Write-Warn2 'Official CANNBot workbench is missing or incomplete. Run provision.ps1 to install it.'; exit 1 }
    Write-Step "official workbench: $($workbench.bundle)@$($workbench.version)"
    $workbenchListed = @($pkg.dsh.profile.bundles) -contains $workbench.bundle
    Write-Step "official bundle entry: $(if ($workbenchListed) { 'listed' } else { 'missing' })"
    if (-not $installed -or -not $listed -or -not $workbenchListed) {
        Write-Warn2 'CANNBot installation is incomplete or disabled. Quit DSH, then run provision.ps1 -Repair.'
        exit 1
    }
    return
}

$backup = $profilePkg + '.before-cannbot-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '.bak'
Copy-Item -LiteralPath $profilePkg -Destination $backup
Write-Step "profile backup: $backup"

if ($Uninstall) {
    if (Test-Path -LiteralPath $targetDir) {
        Remove-RemotePlugin
        Write-Step "removed $targetDir"
    }
    if ($pkg.dsh -and $pkg.dsh.profile -and $pkg.dsh.profile.bundles) {
        $pkg.dsh.profile.bundles = @($pkg.dsh.profile.bundles | Where-Object { $_ -ne $BUNDLE_ENTRY -and $_ -ne 'cannbot-dsh' -and $_ -ne '@cannbot-plugin/cannbot-remote' })
    }
    if ($pkg.dependencies -and $pkg.dependencies.PSObject.Properties.Name -contains $PACKAGE_NAME) {
        $pkg.dependencies.PSObject.Properties.Remove($PACKAGE_NAME)
    }
    foreach ($oldName in @('cannbot-dsh', '@cannbot-plugin/cannbot-remote')) { if ($pkg.dependencies) { $pkg.dependencies.PSObject.Properties.Remove($oldName) } }
    Write-ProfileManifest
    Write-Step 'uninstalled. restart DeepSeek Harness.'
    return
}

if (-not $PluginArchive -or -not $PluginVersion -or -not $BuildId) { throw 'Missing release archive.' }
$workbench = Get-Workbench
Write-Step "current workbench: $($workbench.bundle)@$($workbench.version)"

if (-not $pkg.dependencies) { $pkg | Add-Member -MemberType NoteProperty -Name dependencies -Value ([pscustomobject]@{}) }
if (-not $pkg.dsh) { $pkg | Add-Member -MemberType NoteProperty -Name dsh -Value ([pscustomobject]@{}) }
if (-not $pkg.dsh.profile) { $pkg.dsh | Add-Member -MemberType NoteProperty -Name profile -Value ([pscustomobject]@{}) }
if ($pkg.dsh.profile.PSObject.Properties.Name -notcontains 'bundles') { $pkg.dsh.profile | Add-Member -MemberType NoteProperty -Name bundles -Value @() }
$pkg.dsh.profile.bundles = @(@($pkg.dsh.profile.bundles | Where-Object { $_ -ne 'cannbot-dsh' -and $_ -ne '@cannbot-plugin/cannbot-dsh' -and $_ -ne '@cannbot-plugin/cannbot-remote' }) + @($BUNDLE_ENTRY))
foreach ($oldName in @('cannbot-dsh', '@cannbot-plugin/cannbot-remote')) { $pkg.dependencies.PSObject.Properties.Remove($oldName) }
$dependency = 'file:./node_modules/@cannbot-plugin/cannbot-dsh'
if ($pkg.dependencies.PSObject.Properties.Name -contains $PACKAGE_NAME) { $pkg.dependencies.$PACKAGE_NAME = $dependency }
else { $pkg.dependencies | Add-Member -MemberType NoteProperty -Name $PACKAGE_NAME -Value $dependency }
Write-ProfileManifest
Write-Step "updated $profilePkg"
Write-Host 'DONE. Restart DSH. First launch opens CANNBot. Choose a local workspace or connect a server to open its workspaces and sessions.' -ForegroundColor Green
