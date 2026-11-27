; Copyright (c) 2026 Huawei Technologies Co., Ltd.
; This program is free software, you can redistribute it and/or modify it under the terms and conditions of
; CANN Open Software License Agreement Version 2.0 (the "License").
; Please refer to the License for details. You may not use this file except in compliance with the License.
; THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
; INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
; See LICENSE in the root of the software repository for the full text of the License.

Unicode true
ManifestDPIAware true
RequestExecutionLevel user
SetCompressor zlib
Name "CANNBot开发工作台"
Caption "CANNBot开发工作台 安装向导"
OutFile "${OUTPUT}"
InstallDir "$LOCALAPPDATA\Programs\CANNBot"
BrandingText "CANNBot开发工作台"
ShowInstDetails show
SetFont "Microsoft YaHei UI" 9
!include MUI2.nsh
!include nsDialogs.nsh
!include FileFunc.nsh
!include LogicLib.nsh
!define MUI_ICON "${ASSETS}\setup-icon.ico"
!define MUI_HEADERIMAGE
!define MUI_HEADERIMAGE_RIGHT
!define MUI_HEADERIMAGE_BITMAP "${ASSETS}\header.bmp"
!define MUI_WELCOMEFINISHPAGE_BITMAP "${ASSETS}\sidebar.bmp"
!define MUI_BGCOLOR FFFFFF
!define MUI_TEXTCOLOR 242424
!define MUI_INSTFILESPAGE_COLORS "242424 FFFFFF"
!define MUI_ABORTWARNING
!define MUI_CUSTOMFUNCTION_ABORT OnCancel

Var Dialog
Var Consent
Var ConsentValue
Var ExistingExe
Var InstalledExe
Var RunRoot
Var Running
Var Phase
Var PreviousPhase
Var WorkerHandle
Var ProgressBar
Var ProgressLabel
Var ExtractDirectory
Var DisclosureText
Var DisclosureBrowser
Var DisclosureSelect
Var DisclosurePath
Var DisclosureUrl
Var DocumentIndex
Var DirectoryInput
Var ExistingConsent
Var ExistingConsentValue

Page custom WelcomeShow WelcomeLeave
Page custom DirectoryShow DirectoryLeave
!define MUI_PAGE_HEADER_TEXT "正在安装 CANNBot开发工作台"
!define MUI_PAGE_HEADER_SUBTEXT "请保持网络连接，安装完成后将自动进入下一页。"
!define MUI_PAGE_CUSTOMFUNCTION_SHOW ProgressShow
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_TITLE "CANNBot开发工作台安装完成"
!define MUI_FINISHPAGE_TEXT "已安装 CANNBot开发工作台，可创建工作区或连接远程服务器。$\r$\n$\r$\n点击“完成”应用以下选项。"
!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_TEXT "启动 CANNBot开发工作台"
!define MUI_FINISHPAGE_RUN_FUNCTION LaunchWorkbench
!define MUI_FINISHPAGE_SHOWREADME
!define MUI_FINISHPAGE_SHOWREADME_TEXT "创建桌面快捷方式"
!define MUI_FINISHPAGE_SHOWREADME_FUNCTION CreateDesktopShortcut
!define MUI_FINISHPAGE_NOREBOOTSUPPORT
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_LANGUAGE "SimpChinese"

Function .onInit
  SetShellVarContext current
  StrCpy $ConsentValue ${BST_UNCHECKED}
  StrCpy $ExistingConsentValue ${BST_UNCHECKED}
  StrCpy $DocumentIndex 0
  InitPluginsDir
  ${GetParameters} $0
  ClearErrors
  ${GetOptions} $0 "/EXTRACTONLY=" $ExtractDirectory
  ${IfNot} ${Errors}
    ; A fresh destination is required: extraction never overwrites user files.
    ${GetRoot} $ExtractDirectory $1
    ${If} $1 == ""
      SetErrorLevel 2
      Quit
    ${EndIf}
    IfFileExists "$ExtractDirectory" 0 +3
      SetErrorLevel 2
      Quit
    SetOutPath "$ExtractDirectory\package"
    File /r "${PAYLOAD}\*"
    SetErrorLevel 0
    Quit
  ${EndIf}
  IfSilent 0 +3
    SetErrorLevel 2
    Quit
  System::Call 'kernel32::CreateMutexW(p 0, i 0, w "Local\CANNBot.Workbench.Setup") p .r1 ?e'
  Pop $0
  ${If} $0 == 183
    MessageBox MB_ICONINFORMATION "另一个 CANNBot 安装向导正在运行，请先完成该次安装。"
    SetErrorLevel 1
    Quit
  ${EndIf}
  SetOutPath "$PLUGINSDIR\package"
  File /r "${PAYLOAD}\*"
  ; Detection is read-only and never launches the host or creates a profile.
  nsExec::ExecToStack '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$PLUGINSDIR\package\installers\windows\install-all.ps1" -InspectPath "$PLUGINSDIR\detected.ini"'
  Pop $0
  Pop $1
  ${If} $0 != 0
    MessageBox MB_ICONSTOP "无法检测现有安装，请重新打开安装包。$\r$\n$1"
    SetErrorLevel 1
    Quit
  ${EndIf}
  ReadINIStr $ExistingExe "$PLUGINSDIR\detected.ini" "setup" "executable"
  Banner::show /NOUNLOAD "正在获取版本和安装协议…"
  nsExec::ExecToStack /TIMEOUT=240000 '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$PLUGINSDIR\package\installers\windows\release.ps1" -Action prepare -DshExecutable "$ExistingExe"'
  Pop $0
  Pop $1
  Banner::destroy
  ${If} $0 != 0
    MessageBox MB_ICONSTOP "无法读取安装版本或协议。$\r$\n$1"
    SetErrorLevel 1
    Quit
  ${EndIf}
  ${If} $ExistingExe != ""
    ${GetParent} $ExistingExe $INSTDIR
  ${EndIf}
FunctionEnd

Function OpenDisclosureBrowser
  Pop $0
  ${If} $DisclosureUrl == ""
    Return
  ${EndIf}
  ClearErrors
  ExecShell "open" "$DisclosureUrl"
  ${If} ${Errors}
    MessageBox MB_ICONEXCLAMATION "无法打开默认浏览器，请复制以下地址查看原文：$\r$\n$DisclosureUrl"
  ${EndIf}
FunctionEnd


Function LoadDisclosureText
  ; Read the complete UTF-16 file into a native edit control. Do not truncate
  ; full license texts to NSIS's per-string length limit.
  System::Call 'kernel32::CreateFileW(w "$DisclosurePath", i 0x80000000, i 1, p 0, i 3, i 0, p 0) p .r0'
  ${If} $0 == -1
    MessageBox MB_ICONSTOP "安装告知文件不可用，请重新下载安装包。"
    Quit
  ${EndIf}
  System::Call 'kernel32::GetFileSize(p r0, p 0) i .r1'
  ${If} $1 < 2
  ${OrIf} $1 > 2097152
    System::Call 'kernel32::CloseHandle(p r0)'
    MessageBox MB_ICONSTOP "安装告知文件无效，请重新下载安装包。"
    Quit
  ${EndIf}
  IntOp $2 $1 + 2
  System::Alloc $2
  Pop $2
  ${If} $2 == 0
    System::Call 'kernel32::CloseHandle(p r0)'
    MessageBox MB_ICONSTOP "内存不足，无法读取安装告知。"
    Quit
  ${EndIf}
  System::Call 'kernel32::ReadFile(p r0, p r2, i r1, *i .r4, p 0) i .r3'
  System::Call 'kernel32::CloseHandle(p r0)'
  ${If} $3 == 0
  ${OrIf} $4 != $1
    System::Free $2
    MessageBox MB_ICONSTOP "无法读取完整安装告知，请重新下载安装包。"
    Quit
  ${EndIf}
  IntOp $3 $2 + 2
  SendMessage $DisclosureText ${EM_SETLIMITTEXT} 0x7ffffffe 0
  SendMessage $DisclosureText ${WM_SETTEXT} 0 $3
  System::Free $2
FunctionEnd

Function WelcomeShow
  !insertmacro MUI_HEADER_TEXT "欢迎安装 CANNBot" "基于开源的 harness 软件，接入 CANNBot 插件，$\r$\n一站式完成算子开发"
  nsDialogs::Create 1018
  Pop $Dialog
  ; The page keeps the standard gray background. Only document contents are white.
  ${NSD_CreateDropList} 0 0 100% 90u ""
  Pop $DisclosureSelect
  ReadINIStr $R0 "$PLUGINSDIR\package\installation-documents\index.ini" "documents" "count"
  StrCpy $R1 0
  ${DoWhile} $R1 < $R0
    ReadINIStr $R2 "$PLUGINSDIR\package\installation-documents\index.ini" "$R1" "title"
    ${NSD_CB_AddString} $DisclosureSelect $R2
    IntOp $R1 $R1 + 1
  ${Loop}
  ${NSD_CB_SetSelectionIndex} $DisclosureSelect $DocumentIndex
  ${NSD_OnChange} $DisclosureSelect DisclosureChanged
  nsDialogs::CreateControl EDIT ${WS_CHILD}|${WS_VISIBLE}|${WS_TABSTOP}|${WS_VSCROLL}|${ES_MULTILINE}|${ES_READONLY}|${ES_AUTOVSCROLL} ${WS_EX_CLIENTEDGE} 0 22u 100% 86u ""
  Pop $DisclosureText
  SetCtlColors $DisclosureText 242424 FFFFFF
  ${NSD_CreateLink} 210u 112u 90u 12u "查看在线原文"
  Pop $DisclosureBrowser
  ${NSD_OnClick} $DisclosureBrowser OpenDisclosureBrowser
  ${NSD_CreateCheckbox} 0 128u 100% 12u "我同意用户协议，并已阅读隐私政策和开源软件声明"
  Pop $Consent
  ${NSD_SetState} $Consent $ConsentValue
  ${NSD_OnClick} $Consent ConsentChanged
  Call SelectDisclosure
  Call UpdateConsent
  nsDialogs::Show
FunctionEnd

Function DisclosureChanged
  Pop $0
  Call SelectDisclosure
FunctionEnd

Function SelectDisclosure
  ${NSD_CB_GetSelectionIndex} $DisclosureSelect $DocumentIndex
  ReadINIStr $0 "$PLUGINSDIR\package\installation-documents\index.ini" "$DocumentIndex" "file"
  StrCpy $DisclosurePath "$PLUGINSDIR\package\installation-documents\$0"
  ReadINIStr $DisclosureUrl "$PLUGINSDIR\package\installation-documents\index.ini" "$DocumentIndex" "url"
  ${If} $DisclosureUrl == ""
    ShowWindow $DisclosureBrowser ${SW_HIDE}
  ${Else}
    ShowWindow $DisclosureBrowser ${SW_SHOW}
  ${EndIf}
  Call LoadDisclosureText
  SendMessage $DisclosureText ${EM_SETSEL} 0 0
  SendMessage $DisclosureText ${EM_SCROLLCARET} 0 0
FunctionEnd

Function ConsentChanged
  Pop $0
  Call UpdateConsent
FunctionEnd

Function UpdateConsent
  ${NSD_GetState} $Consent $ConsentValue
  GetDlgItem $0 $HWNDPARENT 1
  EnableWindow $0 $ConsentValue
FunctionEnd

Function WelcomeLeave
  ${If} $ConsentValue != ${BST_CHECKED}
    Abort
  ${EndIf}
FunctionEnd

Function DirectoryShow
  !insertmacro MUI_HEADER_TEXT "安装位置" "确认安装方式及程序位置。"
  nsDialogs::Create 1018
  Pop $Dialog
  ${If} $ExistingExe != ""
    ${NSD_CreateLabel} 0 0 100% 36u "检测到您已安装 DeepSeek Harness。$\r$\nCANNBot开发工作台将以插件的形式扩展现有 DeepSeek Harness 软件。"
    Pop $0
    ${NSD_CreateLabel} 0 48u 100% 12u "DeepSeek Harness 安装位置"
    Pop $0
    ${NSD_CreateText} 0 64u 100% 14u "$INSTDIR"
    Pop $DirectoryInput
    SendMessage $DirectoryInput ${EM_SETREADONLY} 1 0
    ${NSD_CreateCheckbox} 0 105u 100% 26u "我同意在现有 DeepSeek Harness 中安装 CANNBot开发工作台插件"
    Pop $ExistingConsent
    ${NSD_SetState} $ExistingConsent $ExistingConsentValue
    ${NSD_OnClick} $ExistingConsent ExistingConsentChanged
  ${Else}
    ${NSD_CreateLabel} 0 0 100% 42u "CANNBot开发工作台当前以 DeepSeek Harness 插件形式提供。$\r$\n下面将先下载安装 DeepSeek Harness，再接入 CANNBot 插件。$\r$\n请选择 DeepSeek Harness 的安装文件夹。"
    Pop $0
    ${NSD_CreateLabel} 0 55u 100% 12u "目标文件夹"
    Pop $0
    ${NSD_CreateDirRequest} 0 71u 225u 14u "$INSTDIR"
    Pop $DirectoryInput
    ${NSD_OnChange} $DirectoryInput DirectoryChanged
    ${NSD_CreateBrowseButton} 235u 70u 65u 16u "浏览…"
    Pop $0
    ${NSD_OnClick} $0 BrowseDirectory
  ${EndIf}
  GetDlgItem $0 $HWNDPARENT 1
  SendMessage $0 ${WM_SETTEXT} 0 "STR:安装(&I)"
  Call UpdateDirectory
  nsDialogs::Show
FunctionEnd

Function ExistingConsentChanged
  Pop $0
  ${NSD_GetState} $ExistingConsent $ExistingConsentValue
  Call UpdateDirectory
FunctionEnd

Function DirectoryChanged
  Pop $0
  ${NSD_GetText} $DirectoryInput $INSTDIR
  Call UpdateDirectory
FunctionEnd

Function BrowseDirectory
  Pop $0
  ${NSD_GetText} $DirectoryInput $0
  nsDialogs::SelectFolderDialog "选择 DeepSeek Harness 安装文件夹" "$0"
  Pop $0
  ${If} $0 != error
    ${NSD_SetText} $DirectoryInput $0
    StrCpy $INSTDIR $0
    Call UpdateDirectory
  ${EndIf}
FunctionEnd

Function UpdateDirectory
  GetDlgItem $0 $HWNDPARENT 1
  ${If} $ExistingExe != ""
    EnableWindow $0 $ExistingConsentValue
  ${ElseIf} $INSTDIR == ""
    EnableWindow $0 0
  ${Else}
    EnableWindow $0 1
  ${EndIf}
FunctionEnd

Function DirectoryLeave
  ${If} $ExistingExe != ""
  ${AndIf} $ExistingConsentValue != ${BST_CHECKED}
    Abort
  ${EndIf}
  ${If} $ExistingExe == ""
    ${GetRoot} $INSTDIR $0
    ${If} $0 == ""
    ${OrIf} $INSTDIR == "$0\"
    ${OrIf} $INSTDIR == "$0"
      MessageBox MB_ICONEXCLAMATION "请选择本机磁盘上的程序文件夹，不要选择磁盘根目录。"
      Abort
    ${EndIf}
  ${EndIf}
FunctionEnd

Function ProgressShow
  GetDlgItem $0 $mui.InstFilesPage 1004
  GetDlgItem $ProgressLabel $mui.InstFilesPage 1006
  ; NSIS advances its own bar after every instruction. Use a separate native
  ; control in the same position so only measured installation progress moves it.
  System::Call '*(i 0, i 0, i 0, i 0) p .r1'
  System::Call 'user32::GetWindowRect(p r0, p r1)'
  System::Call 'user32::MapWindowPoints(p 0, p $mui.InstFilesPage, p r1, i 2)'
  System::Call '*$1(i .r2, i .r3, i .r4, i .r5)'
  System::Free $1
  IntOp $4 $4 - $2
  IntOp $5 $5 - $3
  ; A standard etched frame stays visible even when the fill reaches 100%.
  System::Call 'user32::CreateWindowExW(i 0, w "STATIC", w "", i 0x50000012, i r2, i r3, i r4, i r5, p $mui.InstFilesPage, p 0, p 0, p 0)'
  IntOp $2 $2 + 1
  IntOp $3 $3 + 1
  IntOp $4 $4 - 2
  IntOp $5 $5 - 2
  System::Call 'user32::CreateWindowExW(i 0, w "msctls_progress32", w "", i 0x50000001, i r2, i r3, i r4, i r5, p $mui.InstFilesPage, p 0, p 0, p 0) p .s'
  Pop $ProgressBar
  ${If} $ProgressBar == 0
    StrCpy $ProgressBar $0
  ${Else}
    ShowWindow $0 ${SW_HIDE}
  ${EndIf}
  System::Call 'uxtheme::SetWindowTheme(p $ProgressBar, w "", w "")'
  SendMessage $ProgressBar ${PBM_SETRANGE32} 0 100
  SendMessage $ProgressBar ${PBM_SETBKCOLOR} 0 0xE2E2E2
  SendMessage $ProgressBar ${PBM_SETBARCOLOR} 0 0x251B8E
  SendMessage $ProgressBar ${PBM_SETPOS} 0 0
FunctionEnd

Function UpdateProgress
  ReadINIStr $Phase "$RunRoot\progress.json.ini" "setup" "phase"
  ${If} $Phase == "detect"
      StrCpy $0 "1 / 5  正在检测运行环境"
      StrCpy $1 5
  ${ElseIf} $Phase == "download"
      ReadINIStr $2 "$RunRoot\progress.json.ini" "setup" "percent"
      ReadINIStr $3 "$RunRoot\progress.json.ini" "setup" "metrics"
      ${If} $2 >= 0
        StrCpy $0 "2 / 5  正在下载 DeepSeek Harness · $2% · $3"
        IntOp $1 $2 / 2
        IntOp $1 $1 + 5
      ${Else}
        StrCpy $0 "2 / 5  正在下载 DeepSeek Harness · $3"
        StrCpy $1 5
      ${EndIf}
  ${ElseIf} $Phase == "install"
      StrCpy $0 "3 / 5  请在 DeepSeek Harness 官方窗口中完成安装"
      StrCpy $1 60
  ${ElseIf} $Phase == "profile"
      StrCpy $0 "4 / 5  正在准备运行环境"
      StrCpy $1 75
  ${ElseIf} $Phase == "plugin"
      StrCpy $0 "5 / 5  正在安装并验证 CANNBot，请稍候"
      StrCpy $1 85
  ${ElseIf} $Phase == "complete"
      StrCpy $0 "CANNBot 安装完成"
      StrCpy $1 100
  ${Else}
      StrCpy $0 "正在准备安装…"
      StrCpy $1 0
  ${EndIf}
  SendMessage $ProgressBar ${PBM_SETPOS} $1 0
  SendMessage $ProgressLabel ${WM_SETTEXT} 0 "STR:$0"
  ${If} $Phase != $PreviousPhase
    DetailPrint "$0"
    StrCpy $PreviousPhase $Phase
  ${EndIf}
FunctionEnd

Section "CANNBot"
retry:
  ClearErrors
  CreateDirectory "$LOCALAPPDATA\CANNBot\Installer"
  IfErrors directoryFailed
  GetTempFileName $RunRoot "$LOCALAPPDATA\CANNBot\Installer"
  IfErrors directoryFailed
  StrCmp $RunRoot "" directoryFailed
  Delete $RunRoot
  CreateDirectory $RunRoot
  IfErrors directoryFailed
  StrCpy $Running 1
  StrCpy $PreviousPhase ""
  StrCpy $WorkerHandle 0
  StrCpy $4 0
  DetailPrint "安装日志：$RunRoot\installation.log"
  ClearErrors
  Exec '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "$PLUGINSDIR\package\installers\windows\setup-worker.ps1" -RunRoot "$RunRoot" -InstallDirectory "$INSTDIR"'
  IfErrors workerFailed
poll:
  Call UpdateProgress
  IfFileExists "$RunRoot\result.ini" workerDone
  ${If} $WorkerHandle == 0
    ReadINIStr $5 "$RunRoot\worker.ini" "setup" "pid"
    ${If} $5 != ""
      System::Call 'kernel32::OpenProcess(i 0x100000, i 0, i $5) p .r6'
      StrCpy $WorkerHandle $6
      ${If} $WorkerHandle == 0
        Goto workerFailed
      ${EndIf}
    ${EndIf}
    IntOp $4 $4 + 1
    ${If} $4 > 240
      Goto workerFailed
    ${EndIf}
  ${Else}
    System::Call 'kernel32::WaitForSingleObject(p $WorkerHandle, i 0) i .r6'
    ${If} $6 == 0
      IfFileExists "$RunRoot\result.ini" workerDone workerFailed
    ${EndIf}
  ${EndIf}
  Sleep 250
  Goto poll
workerDone:
  ReadINIStr $0 "$RunRoot\result.ini" "setup" "code"
  ${If} $0 != 0
    Goto workerFailed
  ${EndIf}
  ReadINIStr $InstalledExe "$RunRoot\result.ini" "setup" "executable"
  IfFileExists "$InstalledExe" 0 workerFailed
  Call CloseWorkerHandle
  StrCpy $Running 0
  Goto success
workerFailed:
  Call CloseWorkerHandle
  StrCpy $Running 0
  ReadINIStr $0 "$RunRoot\result.ini" "setup" "error"
  DetailPrint "安装未完成：$0"
  IfFileExists "$RunRoot\installation.log" 0 +2
    ExecShell "open" "notepad.exe" '"$RunRoot\installation.log"'
  MessageBox MB_RETRYCANCEL|MB_ICONEXCLAMATION "安装未完成，日志已打开。您可以重试，或取消后稍后再安装。$\r$\n$0" IDRETRY retry
  SetErrorLevel 1
  Quit
directoryFailed:
  MessageBox MB_RETRYCANCEL|MB_ICONEXCLAMATION "无法创建安装日志目录：$\r$\n$LOCALAPPDATA\CANNBot\Installer$\r$\n请检查该目录是否可写后重试。" IDRETRY retry
  SetErrorLevel 1
  Quit
success:
  SendMessage $ProgressBar ${PBM_SETPOS} 100 0
  DetailPrint "安装完成。"
SectionEnd

Function CloseWorkerHandle
  ${If} $WorkerHandle != 0
    System::Call 'kernel32::CloseHandle(p $WorkerHandle)'
    StrCpy $WorkerHandle 0
  ${EndIf}
FunctionEnd

Function OnCancel
  ${If} $Running == 1
    ${If} $Phase == "download"
      FileOpen $0 "$RunRoot\progress.json.cancel" w
      FileClose $0
      DetailPrint "正在取消下载，请稍候…"
    ${Else}
      MessageBox MB_ICONINFORMATION "当前步骤正在安装或验证，请等待完成。DeepSeek Harness 的安装可在其官方窗口中取消。"
    ${EndIf}
    Abort
  ${EndIf}
FunctionEnd

Function LaunchWorkbench
  ExecShell "open" "$InstalledExe"
FunctionEnd

Function CreateDesktopShortcut
  CreateDirectory "$LOCALAPPDATA\CANNBot"
  CopyFiles /SILENT "$PLUGINSDIR\package\installers\windows\setup-icon.ico" "$LOCALAPPDATA\CANNBot\cannbot.ico"
  ${GetParent} $InstalledExe $0
  SetOutPath $0
  CreateShortcut "$DESKTOP\CANNBot开发工作台.lnk" "$InstalledExe" "" "$LOCALAPPDATA\CANNBot\cannbot.ico" 0 SW_SHOWNORMAL "" "CANNBot开发工作台"
FunctionEnd
