# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.

param([string]$Installer, [string]$PackageRoot, [string]$RunRoot)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms, System.Drawing, System.Web.Extensions
$application = Join-Path $RunRoot ('CANNBot-Setup-' + [Guid]::NewGuid().ToString('N') + '.exe')
$compiler = New-Object CodeDom.Compiler.CompilerParameters
$compiler.CompilerOptions = '/target:winexe /win32icon:"' + (Join-Path $PSScriptRoot 'setup-icon.ico') + '"'
$compiler.GenerateExecutable = $true
$compiler.GenerateInMemory = $false
$compiler.OutputAssembly = $application
$compiler.ReferencedAssemblies.AddRange(@('System.dll', 'System.Core.dll', 'System.Windows.Forms.dll', 'System.Drawing.dll', 'System.Web.Extensions.dll'))
# Compile to disk without loading the generated executable into PowerShell.
$provider = New-Object Microsoft.CSharp.CSharpCodeProvider
try {
    $compiled = $provider.CompileAssemblyFromSource($compiler, @([IO.File]::ReadAllText((Join-Path $PSScriptRoot 'setup-window.cs'))))
    if ($compiled.Errors.HasErrors) { throw (($compiled.Errors | ForEach-Object { $_.ToString() }) -join [Environment]::NewLine) }
} finally { $provider.Dispose() }
$info = New-Object Diagnostics.ProcessStartInfo
$info.FileName = $application
$info.UseShellExecute = $false
$info.EnvironmentVariables['CANNBOT_GUI_INSTALLER'] = $Installer
$info.EnvironmentVariables['CANNBOT_GUI_PACKAGE'] = $PackageRoot
$info.EnvironmentVariables['CANNBOT_GUI_RUNROOT'] = $RunRoot
$process = [Diagnostics.Process]::Start($info)
$process.WaitForExit()
$result = $process.ExitCode
$process.Dispose()
exit $result
