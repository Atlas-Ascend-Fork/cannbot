// ----------------------------------------------------------------------------------------------------------
// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.
// ----------------------------------------------------------------------------------------------------------

export const PRODUCT = 'CANNBot'
export const NAMESPACE = 'cannbotDsh'
export const PACKAGE = '@cannbot-plugin/cannbot-dsh'
export const COMMAND = '/ops-direct-invoke'

export const zh = {
  tasksTitle: '任务列表', tasksDone: '已完成', tasksRecent: '仅显示最近完成', tasksAll: '查看全部任务',
  currentWorkflow: '工作流',
  contentCatalog: '工作流目录', contentCheck: '检查工作流更新', contentVersion: '当前版本', contentLatest: '最新版本', contentPinned: '已固定回退版本',
  contentInstall: '安装', contentUpdate: '更新', contentRollback: '回退到', contentUpToDate: '已是最新', contentUnchecked: '已安装，可使用', contentNotInstalled: '未安装', contentUnavailable: '暂不可用',
  contentTitle: '工作流管理', contentSync: '更新全部工作流', contentBusy: '正在准备…', contentDownloading: '正在从 npm 获取独立工作流包…',
  contentInitializing: '正在执行官方安装器，准备工作区依赖…', contentReady: '工作流已准备完成，可独立更新。选择工作流时自动准备当前工作区。',
  contentFailed: '准备未完成。已有工作流版本保留；请查看日志后重试。', contentFallback: '正在准备首次安装的工作流包。', contentWorkflows: '个已安装工作流', contentLogs: '查看准备日志',
  updateBackground: '后台正在更新，请勿重复安装。', updateRestored: '更新失败，已恢复旧版。',
  updateRepair: '更新和恢复未完成，请在插件页重新安装原版本。', updateConnectionLost: '连接中断，后台更新可能仍在进行。请重新打开插件页确认版本，勿重复安装。', updateDismiss: '关闭更新提示',
  updateTitle: '版本更新', updateCurrent: '当前版本', updateCheck: '检查更新', updateChecking: '正在检查…',
  updateTo: '更新到', updateRunning: '正在更新…', updateAvailable: '发现新版本，点击上方按钮更新。',
  updateLatest: '当前已是最新版本。', updateDone: '更新已完成。', updateRestart: '新版已安装，重启 DSH 后生效。',
  updateManual: '当前 DSH 要求先卸载旧版。请先下载新版包，再在插件页卸载旧版并添加下载的安装包。',
  updateIncompatible: '当前 DSH 不支持此版本，请先升级 DSH。', updateFailed: '暂时无法完成，请稍后重试。', updateDownload: '下载新版安装包',
  workflow: '选择工作流', ordinary: '普通对话', saving: '正在应用工作流…', operator: 'ops-direct-invoke', commandHint: '发送时自动应用所选工作流，只需填写需求。',
  flash: 'ops-direct-invoke-flash', registry: 'ops-registry-invoke',
  operatorDescription: '开发 Ascend C 算子，通过直调方式接入使用。',
  flashDescription: '快速生成并验证 Ascend C 算子。',
  registryDescription: '开发 Ascend C 注册算子，通过 ACLNN / GEIR 接入框架。',
  chooseWorkspace: '请先选择工作目录。', insertFailed: '工作流准备或设置未完成，请到插件详情查看准备日志后重试。', settingsRetry: '设置连接失败，重试', workflowRetry: '工作流未就绪，重试',
}
export const en: typeof zh = {
  tasksTitle: 'Tasks', tasksDone: 'Completed', tasksRecent: 'Show recent completions', tasksAll: 'Show all tasks',
  currentWorkflow: 'Workflow',
  contentCatalog: 'Workflow catalog', contentCheck: 'Check workflow updates', contentVersion: 'Installed', contentLatest: 'Latest', contentPinned: 'Rolled-back version pinned',
  contentInstall: 'Install', contentUpdate: 'Update', contentRollback: 'Roll back to', contentUpToDate: 'Up to date', contentUnchecked: 'Installed and ready', contentNotInstalled: 'Not installed', contentUnavailable: 'Unavailable',
  contentTitle: 'Workflow manager', contentSync: 'Update all workflows', contentBusy: 'Preparing…', contentDownloading: 'Fetching independent workflow packages from npm…',
  contentInitializing: 'Running the official installer to prepare workspace dependencies…', contentReady: 'Workflows are ready and can be updated independently. Selecting one prepares this workspace automatically.',
  contentFailed: 'Preparation did not finish. Existing workflow versions are retained; check the log and retry.', contentFallback: 'Preparing the first workflow package installation.', contentWorkflows: 'installed workflows', contentLogs: 'View preparation log',
  updateBackground: 'Updating in the background. Do not install again.', updateRestored: 'Update failed; the previous version was restored.',
  updateRepair: 'Update and recovery did not finish. Reinstall the previous version from Plugins.', updateConnectionLost: 'Connection lost. The Host may still be updating. Reopen Plugins to check the version before retrying.', updateDismiss: 'Dismiss update notice',
  updateTitle: 'Updates', updateCurrent: 'Installed version', updateCheck: 'Check for updates', updateChecking: 'Checking…',
  updateTo: 'Update to', updateRunning: 'Updating…', updateAvailable: 'A new version is available. Use the button above to update.',
  updateLatest: 'You are up to date.', updateDone: 'Update completed.', updateRestart: 'The update is installed. Restart DSH to apply it.',
  updateManual: 'This DSH version requires removing the old plugin first. Download the update, then uninstall the old plugin and add the downloaded package.',
  updateIncompatible: 'This release requires updating DSH first.', updateFailed: 'Unable to complete this operation. Please retry.', updateDownload: 'Download update',
  workflow: 'Choose workflow', ordinary: 'Ordinary conversation', saving: 'Applying workflow…', operator: 'ops-direct-invoke', commandHint: 'The selected workflow is applied in the background when you send.',
  flash: 'ops-direct-invoke-flash', registry: 'ops-registry-invoke',
  operatorDescription: 'Develop Ascend C operators and integrate them through direct invocation.',
  flashDescription: 'Quickly generate and validate Ascend C operators.',
  registryDescription: 'Develop registered Ascend C operators for framework integration through ACLNN / GEIR.',
  chooseWorkspace: 'Choose a working directory first.', insertFailed: 'Workflow preparation or saving failed. Check preparation logs in the plugin details and retry.', settingsRetry: 'Reconnect settings', workflowRetry: 'Retry workflow',
}
export type LocaleKey = keyof typeof zh
