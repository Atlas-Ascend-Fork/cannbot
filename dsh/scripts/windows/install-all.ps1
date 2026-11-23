# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.

# One-click installer: install DeepSeek Harness and this checkout's CANNBot build.
#
#   .\install-all.ps1          install everything
#   .\install-all.ps1 -Check   detect only, change nothing
#   .\install-all.ps1 -Upgrade reinstall the latest DSH even if one is installed
#
# ASCII-only on purpose: PowerShell 5.1 parses BOM-less .ps1 as ANSI, so non-ASCII
# string literals break the parser.
[CmdletBinding()]
param(
    [switch]$Check,
    [switch]$Upgrade,
    [switch]$DisclosureAccepted,
    [string]$PackageRoot = '',
    [string]$ProgressPath = ''
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$provisionScript = Join-Path $repoRoot 'scripts\windows\provision.ps1'
$installerUrl = 'https://download.deepseek.com/desktop/dsh-latest-windows-x64.exe'
$dshHome = if ($env:DSH_HOME -and $env:DSH_HOME.Trim()) { $env:DSH_HOME.Trim() } else { Join-Path $env:USERPROFILE '.dsh' }
$profilePkg = Join-Path $dshHome 'profiles\desktop\package.json'
$appProcessName = 'DeepSeek Harness'

function Say([string]$text, [string]$color = 'Gray') { Write-Host $text -ForegroundColor $color }
function Step([string]$text) { Write-Host ''; Write-Host "== $text" -ForegroundColor Cyan }

# The UI observes structured state, not localized console output. A same-folder
# rename publishes a complete snapshot; readers can retry while Windows locks it.
function Report-Setup([string]$Phase, [long]$Received = 0, [long]$Total = 0, [double]$Speed = 0, [string]$Executable = '') {
    if (-not $ProgressPath) { return }
    $json = @{ phase = $Phase; received = $Received; total = $Total; speed = $Speed; executable = $Executable } | ConvertTo-Json -Compress
    $temporary = $ProgressPath + '.tmp'
    [IO.File]::WriteAllText($temporary, $json, [Text.UTF8Encoding]::new($false))
    for ($attempt = 0; $attempt -lt 6; $attempt++) {
        try { Move-Item -LiteralPath $temporary -Destination $ProgressPath -Force; break }
        catch { if ($attempt -eq 5) { throw }; Start-Sleep -Milliseconds 20 }
    }
}

function Assert-DownloadActive {
    if ($ProgressPath -and (Test-Path -LiteralPath ($ProgressPath + '.cancel'))) {
        throw [OperationCanceledException]::new('Download cancelled by user.')
    }
}

function Receive-Installer([string]$Uri, [string]$Destination) {
    $partial = $Destination + '.' + [Guid]::NewGuid().ToString('N') + '.partial'
    $response = $null; $inputStream = $null; $outputStream = $null
    try {
        Assert-DownloadActive
        Report-Setup 'download'
        $request = [Net.HttpWebRequest]::Create($Uri)
        $request.Timeout = 30000
        $request.ReadWriteTimeout = 30000
        $response = $request.GetResponse()
        $total = [long]$response.ContentLength
        $inputStream = $response.GetResponseStream()
        $outputStream = [IO.File]::Create($partial)
        $buffer = New-Object byte[] 131072
        $received = 0L
        $watch = [Diagnostics.Stopwatch]::StartNew()
        $lastReport = -1000L
        while (($count = $inputStream.Read($buffer, 0, $buffer.Length)) -gt 0) {
            Assert-DownloadActive
            $outputStream.Write($buffer, 0, $count)
            $received += $count
            if ($watch.ElapsedMilliseconds - $lastReport -ge 250) {
                Report-Setup 'download' $received $total ($received / [Math]::Max(0.1, $watch.Elapsed.TotalSeconds))
                $lastReport = $watch.ElapsedMilliseconds
            }
        }
        Assert-DownloadActive
        if ($received -eq 0 -or ($total -ge 0 -and $received -ne $total)) { throw 'Incomplete DSH download. Please retry.' }
        $outputStream.Dispose(); $outputStream = $null
        Move-Item -LiteralPath $partial -Destination $Destination -Force
        Report-Setup 'download' $received $received ($received / [Math]::Max(0.1, $watch.Elapsed.TotalSeconds))
    } finally {
        if ($outputStream) { $outputStream.Dispose() }
        if ($inputStream) { $inputStream.Dispose() }
        if ($response) { $response.Close() }
        if (Test-Path -LiteralPath $partial) { Remove-Item -LiteralPath $partial -Force }
    }
}

function Get-UninstallEntries {
    $roots = @(
        'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*'
    )
    $found = @()
    foreach ($root in $roots) {
        try {
            $found += Get-ItemProperty -Path $root -ErrorAction SilentlyContinue |
                Where-Object {
                    ($_.DisplayName -and $_.DisplayName -like '*DeepSeek*Harness*') -or
                    ($_.Publisher -and $_.Publisher -like '*DeepSeek*' -and $_.DisplayName -and $_.DisplayName -like '*Harness*')
                }
        } catch { }
    }
    return $found
}

function Find-Dsh {
    foreach ($entry in (Get-UninstallEntries)) {
        foreach ($candidate in @($entry.DisplayIcon, $entry.InstallLocation)) {
            if (-not $candidate) { continue }
            $path = $candidate.Trim('"')
            if ($path -match '\.exe$') {
                if (Test-Path -LiteralPath $path) { return (Resolve-Path -LiteralPath $path).Path }
            } elseif (Test-Path -LiteralPath $path) {
                $exe = Join-Path $path 'DeepSeek Harness.exe'
                if (Test-Path -LiteralPath $exe) { return (Resolve-Path -LiteralPath $exe).Path }
            }
        }
    }
    $fallbacks = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\DeepSeek Harness\DeepSeek Harness.exe'),
        (Join-Path $env:ProgramFiles 'DeepSeek Harness\DeepSeek Harness.exe'),
        (Join-Path ${env:ProgramFiles(x86)} 'DeepSeek Harness\DeepSeek Harness.exe')
    )
    foreach ($candidate in $fallbacks) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) { return (Resolve-Path -LiteralPath $candidate).Path }
    }
    return $null
}

function Get-InstalledVersion($uninstallEntry) {
    if ($uninstallEntry -and $uninstallEntry.DisplayVersion) { return $uninstallEntry.DisplayVersion }
    return ''
}

function Stop-DshIfRunning {
    param([string]$ExecutablePath, [int]$GracePeriodSeconds = 3, [int]$ChildExitSeconds = 15)

    # A renderer has the same executable name as Electron's main process.
    # Killing these by name can make the live main process report a crash.
    # First request normal closure. DSH normally hides its window to the tray,
    # so remember the real main process before its window handle disappears.
    # Stop only that verified process; the Host handles IPC disconnect itself.
    if (-not $ExecutablePath) {
        if (Get-Process -Name $appProcessName -ErrorAction SilentlyContinue) {
            Say '  Cannot identify the running DSH installation. Quit DSH completely and retry.' Yellow
            return $false
        }
        return $true
    }
    $expectedPath = [IO.Path]::GetFullPath($ExecutablePath)
    function Get-TargetDshProcesses {
        foreach ($candidate in @(Get-Process -Name $appProcessName -ErrorAction SilentlyContinue)) {
            if ($candidate.HasExited) { continue }
            $path = $candidate.Path
            if (-not $path) {
                if ($candidate.HasExited) { continue }
                throw 'Cannot verify the path of a running DSH process.'
            }
            if ([IO.Path]::GetFullPath($path).Equals($expectedPath, [StringComparison]::OrdinalIgnoreCase)) {
                $candidate
            }
        }
    }

    try {
        $procs = @(Get-TargetDshProcesses)
        if (-not $procs.Count) { return $true }
        $mainProcesses = @()
        foreach ($p in $procs) {
            if ($p.MainWindowHandle -ne [IntPtr]::Zero) {
                $mainProcesses += [pscustomobject]@{ Id = $p.Id; StartTime = $p.StartTime }
            }
        }
        Say '  DeepSeek Harness is running. Requesting a normal shutdown ...' Yellow
        foreach ($p in $procs) {
            if ($p.MainWindowHandle -ne [IntPtr]::Zero) {
                try { [void]$p.CloseMainWindow() } catch { }
            }
        }
        $deadline = (Get-Date).AddSeconds($GracePeriodSeconds)
        do {
            if (-not @(Get-TargetDshProcesses).Count) { return $true }
            if ((Get-Date) -ge $deadline) { break }
            Start-Sleep -Milliseconds 250
        } while ($true)

        if (-not $mainProcesses.Count) {
            Say '  No main-window process was identified; refusing to stop background processes.' Yellow
            return $false
        }
        foreach ($main in $mainProcesses) {
            $current = Get-Process -Id $main.Id -ErrorAction SilentlyContinue
            if (-not $current -or $current.HasExited) { continue }
            # A PID may have been reused while the application was closing.
            if (-not $current.Path -or
                -not [IO.Path]::GetFullPath($current.Path).Equals($expectedPath, [StringComparison]::OrdinalIgnoreCase) -or
                $current.StartTime -ne $main.StartTime) {
                Say '  The recorded main process changed identity; refusing to stop it.' Yellow
                return $false
            }
            Say "  Closing verified DSH main process $($main.Id); waiting for its background processes ..." Yellow
            Stop-Process -Id $main.Id -Force -ErrorAction Stop
        }
        $deadline = (Get-Date).AddSeconds($ChildExitSeconds)
        do {
            if (-not @(Get-TargetDshProcesses).Count) { return $true }
            if ((Get-Date) -ge $deadline) { break }
            Start-Sleep -Milliseconds 250
        } while ($true)
    } catch {
        Say "  Cannot verify DSH has exited: $($_.Exception.Message)" Yellow
    }
    Say '  DSH background processes are still running. Quit DSH completely and retry; background processes were not force-killed.' Yellow
    return $false
}

function Download-Installer {
    Report-Setup 'download'
    $target = Join-Path $env:TEMP 'dsh-setup-latest.exe'
    if (Test-Path -LiteralPath $target) {
        $size = (Get-Item -LiteralPath $target).Length
        if ($size -gt 100MB) { Say "  reusing downloaded installer: $target ($([math]::Round($size / 1MB)) MB)" DarkGray; return $target }
        Remove-Item -LiteralPath $target -Force -ErrorAction SilentlyContinue
    }
    Say '  downloading DeepSeek Harness (about 280 MB, this can take a few minutes) ...' Gray
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Receive-Installer $installerUrl $target
    if (-not (Test-Path -LiteralPath $target)) { throw 'download failed' }
    Say "  saved: $target ($([math]::Round((Get-Item -LiteralPath $target).Length / 1MB)) MB)" DarkGray
    return $target
}

function Install-Dsh([string]$installerPath) {
    Assert-DownloadActive
    Report-Setup 'install'
    Say '  Please complete the official installer. Review and confirm any agreements yourself.' Gray
    $proc = Start-Process -FilePath $installerPath -PassThru -Wait
    Say "  installer exit code: $($proc.ExitCode)" DarkGray
    if ($proc.ExitCode -notin @(0, 3010)) { throw "Official installer was cancelled or failed (exit $($proc.ExitCode))." }
    Start-Sleep -Seconds 3
    $exe = Find-Dsh
    if ($exe) { return $exe }

    return (Find-Dsh)
}

function Ensure-Profile([string]$exe) {
    if (Test-Path -LiteralPath $profilePkg) { return $true }
    Say '  creating the DSH profile in the background ...' Gray
    # Match Desktop's createPluginProfile / initProfile metadata. Desktop owns
    # runtime preparation on its first real launch; no Electron window is needed
    # to install an external bundle. Never replace existing user configuration.
    $directory = Split-Path -Parent $profilePkg
    [void][IO.Directory]::CreateDirectory($directory)
    $manifest = [ordered]@{
        name = 'dsh-profile-desktop'; private = $true; dependencies = @{}
        dsh = @{ profile = @{ bundles = @('@deepseek-ai/dsh-base', '@deepseek-ai/dsh-web-app') } }
    } | ConvertTo-Json -Depth 8
    $files = [ordered]@{
        'cordis.patch.yml' = "[]`n"
        'pnpm-workspace.yaml' = "packages:`n  - .`n`nnodeLinker: hoisted`nautoInstallPeers: false`n"
        'package.json' = $manifest + "`n"
    }
    foreach ($name in $files.Keys) {
        $path = Join-Path $directory $name
        if (Test-Path -LiteralPath $path) { continue }
        $temporary = Join-Path $directory ('.cannbot-profile-' + [Guid]::NewGuid().ToString('N') + '.tmp')
        try {
            [IO.File]::WriteAllText($temporary, $files[$name], [Text.UTF8Encoding]::new($false))
            try { [IO.File]::Move($temporary, $path) }
            catch { if (-not (Test-Path -LiteralPath $path)) { throw } }
        } finally { if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force } }
    }
    return (Test-Path -LiteralPath $profilePkg)
}

function Invoke-CannbotCheck {
    param([string]$ProfilePackage, [string]$ProvisionScript, [string]$DshExecutable)
    if (-not (Test-Path -LiteralPath $ProfilePackage)) {
        Say '  Desktop profile is missing. Run the installer to prepare it.' Yellow
        return 1
    }
    if (-not (Test-Path -LiteralPath $ProvisionScript)) { throw "missing $ProvisionScript" }
    $arguments = @('-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', $ProvisionScript, '-Check')
    if ($DshExecutable) { $arguments += @('-DshExecutable', $DshExecutable) }
    & powershell @arguments | ForEach-Object { Write-Host $_ }
    return [int]$LASTEXITCODE
}

# ---------------------------------------------------------------- main
if (-not $Check -and -not $DisclosureAccepted) {
    $policy = Get-Content -LiteralPath (Join-Path $repoRoot 'release-policy.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    Say 'CANNBot downloads DeepSeek Harness from its official website. Rights belong to DeepSeek; license: MIT.'
    Say ('Source: ' + $policy.hostSourceUrl)
    Say ('MIT: ' + $policy.hostLicenseUrl)
    Say ('Host terms: ' + $policy.hostTermsUrl)
    Say ('Host privacy: ' + $policy.hostPrivacyUrl)
    Say ('CANNBot agreement: ' + $policy.userAgreementUrl)
    Say ('CANNBot privacy: ' + $policy.privacyPolicyUrl)
    if ($policy.channel -ne 'public') { Say 'DEVELOPMENT BUILD: formal CANNBot legal documents are pending. Not for public distribution.' Yellow }
    Say 'Model inputs go to your chosen provider. Credential synchronization to servers is optional and disabled by default.'
    Say 'Packages may be obtained from npmjs.org or npmmirror.com. See THIRD_PARTY_NOTICES.md and LICENSE in this package.'
    if ((Read-Host 'After reviewing the information, type INSTALL to continue') -cne 'INSTALL') { throw 'Installation cancelled before making changes.' }
}
Say '=============================================='
Say ' CANNBot DSH - one-click installer'
Say '=============================================='

Step '1/4 detect DeepSeek Harness'
Report-Setup 'detect'
$entries = Get-UninstallEntries
$dshExe = Find-Dsh
if ($dshExe) {
    $version = Get-InstalledVersion ($entries | Select-Object -First 1)
    Say "  installed: $dshExe" Green
    if ($version) { Say "  version:   $version" DarkGray }
} else {
    Say '  not installed' Yellow
}

Step '2/4 install DeepSeek Harness'
if ($dshExe -and -not $Upgrade) {
    Say '  skipped (already installed; use -Upgrade to reinstall)' Green
} elseif ($Check) {
    Say '  WOULD download and install:' Yellow
    Say "  $installerUrl" DarkGray
} else {
    if (-not (Stop-DshIfRunning -ExecutablePath $dshExe)) { throw 'cannot close the running DeepSeek Harness; quit it and run again' }
    $installer = Download-Installer
    $dshExe = Install-Dsh $installer
    if (-not $dshExe) { throw 'DeepSeek Harness installation could not be verified' }
    Say "  installed: $dshExe" Green
}

Step '3/4 ensure the DSH profile exists'
Report-Setup 'profile'
if (Test-Path -LiteralPath $profilePkg) {
    Say '  profile present' Green
} elseif ($Check) {
    Say '  WOULD create the DSH profile in the background' Yellow
} elseif ($dshExe) {
    if (-not (Ensure-Profile $dshExe)) {
        throw 'DSH profile could not be created; check directory permissions and retry'
    }
    Say '  profile created' Green
}

Step '4/4 install the current CANNBot workbench with remote support'
Report-Setup 'plugin'
if ($Check) {
    $checkCode = Invoke-CannbotCheck -ProfilePackage $profilePkg -ProvisionScript $provisionScript -DshExecutable $dshExe
    if (-not $dshExe) {
        Say '  DSH is not installed. Run the installer without -Check.' Yellow
        if ($checkCode -eq 0) { $checkCode = 1 }
    }
    if ($checkCode -ne 0) { exit $checkCode }
    Say '  CHECK PASSED - DSH and the CANNBot profile are ready.' Green
    return
} else {
    if (-not (Test-Path -LiteralPath $provisionScript)) { throw "missing $provisionScript" }
    if (-not (Stop-DshIfRunning -ExecutablePath $dshExe)) { throw 'cannot close DeepSeek Harness; quit it and run again' }
    $provisionArguments = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $provisionScript)
    $provisionArguments += @('-DshExecutable', $dshExe)
    if ($PackageRoot) { $provisionArguments += @('-PackageRoot', $PackageRoot) }
    & powershell @provisionArguments
    if ($LASTEXITCODE -ne 0) { throw "plugin installation failed (exit $LASTEXITCODE)" }
}

Say ''
Say '=========================================================='
Report-Setup 'complete' -Executable $dshExe
Say ' DONE - start DeepSeek Harness, then:'
Say '   First launch opens the CANNBot workbench.'
Say '   Choose a local workspace, or connect a server and expand its workspaces and sessions.'
Say '=========================================================='
