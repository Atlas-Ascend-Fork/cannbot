/*!
 * CANNBot DSH client code:
 * Copyright (c) 2026 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 *
 * Third-party notices: see dsh/THIRD_PARTY_NOTICES.md.
 * Source: https://cann.cannbot.cn/dsh-native-replay-v3/bundles/cannbot-client.js
 * Bundled components retain their respective copyrights and licenses.
 */

window.__ModuleLoader__.load({
	id: "@cannbot-plugin/cannbot-dsh",
	factory: (require) => {
		var module = { exports: {} };
		var exports = module.exports;
		Object.defineProperty(exports, Symbol.toStringTag, { value: "Module" });
		let react_jsx_runtime = require("react/jsx-runtime");
		let react = require("react");
		let _deepseek_ai_dsh_client_ui_primitives = require("@deepseek-ai/dsh-client-ui-primitives");
		let react_dom = require("react-dom");
		// src/client/locales.ts
		const NAMESPACE = "cannbotDsh";
		const PACKAGE = "@cannbot-plugin/cannbot-dsh";
		const zh = {
			tasksTitle: "任务列表",
			tasksDone: "已完成",
			tasksRecent: "仅显示最近完成",
			tasksAll: "查看全部任务",
			currentWorkflow: "工作流",
			contentCatalog: "工作流目录",
			contentCheck: "检查工作流更新",
			contentVersion: "当前版本",
			contentLatest: "最新版本",
			contentPinned: "已固定回退版本",
			contentInstall: "安装",
			contentUpdate: "更新",
			contentRollback: "回退到",
			contentUpToDate: "已是最新",
			contentUnchecked: "已安装，可使用",
			contentNotInstalled: "未安装",
			contentUnavailable: "暂不可用",
			contentTitle: "工作流管理",
			contentSync: "更新全部工作流",
			contentBusy: "正在准备…",
			contentDownloading: "正在从 npm 获取独立工作流包…",
			contentInitializing: "正在执行官方安装器，准备工作区依赖…",
			contentReady: "工作流已准备完成，可独立更新。选择工作流时自动准备当前工作区。",
			contentFailed: "准备未完成。已有工作流版本保留；请查看日志后重试。",
			contentFallback: "正在准备首次安装的工作流包。",
			contentWorkflows: "个已安装工作流",
			contentLogs: "查看准备日志",
			updateBackground: "后台正在更新，请勿重复安装。",
			updateRestored: "更新失败，已恢复旧版。",
			updateRepair: "更新和恢复未完成，请在插件页重新安装原版本。",
			updateConnectionLost: "连接中断，后台更新可能仍在进行。请重新打开插件页确认版本，勿重复安装。",
			updateDismiss: "关闭更新提示",
			updateTitle: "版本更新",
			updateCurrent: "当前版本",
			updateCheck: "检查更新",
			updateChecking: "正在检查…",
			updateTo: "更新到",
			updateRunning: "正在更新…",
			updateAvailable: "发现新版本，点击上方按钮更新。",
			updateLatest: "当前已是最新版本。",
			updateDone: "更新已完成。",
			updateRestart: "新版已安装，重启 DSH 后生效。",
			updateManual: "当前 DSH 要求先卸载旧版。请先下载新版包，再在插件页卸载旧版并添加下载的安装包。",
			updateIncompatible: "当前 DSH 不支持此版本，请先升级 DSH。",
			updateFailed: "暂时无法完成，请稍后重试。",
			updateDownload: "下载新版安装包",
			workflow: "选择工作流",
			ordinary: "普通对话",
			saving: "正在应用工作流…",
			operator: "ops-direct-invoke",
			commandHint: "发送时自动应用所选工作流，只需填写需求。",
			flash: "ops-direct-invoke-flash",
			registry: "ops-registry-invoke",
			operatorDescription: "开发 Ascend C 算子，通过直调方式接入使用。",
			flashDescription: "快速生成并验证 Ascend C 算子。",
			registryDescription: "开发 Ascend C 注册算子，通过 ACLNN / GEIR 接入框架。",
			chooseWorkspace: "请先选择工作目录。",
			insertFailed: "工作流准备或设置未完成，请到插件详情查看准备日志后重试。",
			settingsRetry: "设置连接失败，重试",
			workflowRetry: "工作流未就绪，重试"
		};
		const en = {
			tasksTitle: "Tasks",
			tasksDone: "Completed",
			tasksRecent: "Show recent completions",
			tasksAll: "Show all tasks",
			currentWorkflow: "Workflow",
			contentCatalog: "Workflow catalog",
			contentCheck: "Check workflow updates",
			contentVersion: "Installed",
			contentLatest: "Latest",
			contentPinned: "Rolled-back version pinned",
			contentInstall: "Install",
			contentUpdate: "Update",
			contentRollback: "Roll back to",
			contentUpToDate: "Up to date",
			contentUnchecked: "Installed and ready",
			contentNotInstalled: "Not installed",
			contentUnavailable: "Unavailable",
			contentTitle: "Workflow manager",
			contentSync: "Update all workflows",
			contentBusy: "Preparing…",
			contentDownloading: "Fetching independent workflow packages from npm…",
			contentInitializing: "Running the official installer to prepare workspace dependencies…",
			contentReady: "Workflows are ready and can be updated independently. Selecting one prepares this workspace automatically.",
			contentFailed: "Preparation did not finish. Existing workflow versions are retained; check the log and retry.",
			contentFallback: "Preparing the first workflow package installation.",
			contentWorkflows: "installed workflows",
			contentLogs: "View preparation log",
			updateBackground: "Updating in the background. Do not install again.",
			updateRestored: "Update failed; the previous version was restored.",
			updateRepair: "Update and recovery did not finish. Reinstall the previous version from Plugins.",
			updateConnectionLost: "Connection lost. The Host may still be updating. Reopen Plugins to check the version before retrying.",
			updateDismiss: "Dismiss update notice",
			updateTitle: "Updates",
			updateCurrent: "Installed version",
			updateCheck: "Check for updates",
			updateChecking: "Checking…",
			updateTo: "Update to",
			updateRunning: "Updating…",
			updateAvailable: "A new version is available. Use the button above to update.",
			updateLatest: "You are up to date.",
			updateDone: "Update completed.",
			updateRestart: "The update is installed. Restart DSH to apply it.",
			updateManual: "This DSH version requires removing the old plugin first. Download the update, then uninstall the old plugin and add the downloaded package.",
			updateIncompatible: "This release requires updating DSH first.",
			updateFailed: "Unable to complete this operation. Please retry.",
			updateDownload: "Download update",
			workflow: "Choose workflow",
			ordinary: "Ordinary conversation",
			saving: "Applying workflow…",
			operator: "ops-direct-invoke",
			commandHint: "The selected workflow is applied in the background when you send.",
			flash: "ops-direct-invoke-flash",
			registry: "ops-registry-invoke",
			operatorDescription: "Develop Ascend C operators and integrate them through direct invocation.",
			flashDescription: "Quickly generate and validate Ascend C operators.",
			registryDescription: "Develop registered Ascend C operators for framework integration through ACLNN / GEIR.",
			chooseWorkspace: "Choose a working directory first.",
			insertFailed: "Workflow preparation or saving failed. Check preparation logs in the plugin details and retry.",
			settingsRetry: "Reconnect settings",
			workflowRetry: "Retry workflow"
		};
		// src/client/logo.svg
		var logo_default = "data:image/svg+xml;base64,PHN2ZyB2aWV3Qm94PSIwIDAgMTI4IDEyOCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIiB4bWxuczp4bGluaz0iaHR0cDovL3d3dy53My5vcmcvMTk5OS94bGluayIgd2lkdGg9IjEyOC4wMDAwMDAiIGhlaWdodD0iMTI4LjAwMDAwMCIgZmlsbD0ibm9uZSIgY3VzdG9tRnJhbWU9IiMwMDAwMDAiPgoJPGRlZnM+CgkJPGNsaXBQYXRoIGlkPSJjbGlwUGF0aF8xMiI+CgkJCTxyZWN0IHdpZHRoPSIxMjguMDAwMDAwIiBoZWlnaHQ9IjEyNy45OTk5NTQiIHg9IjAuMDAwMDAwIiB5PSIwLjAwMDAwMCIgZmlsbD0icmdiKDI1NSwyNTUsMjU1KSIgLz4KCQk8L2NsaXBQYXRoPgoJCTxsaW5lYXJHcmFkaWVudCBpZD0icGFpbnRfbGluZWFyXzIyIiB4MT0iMjkuMzMzMzM0IiB4Mj0iMjkuMzMzMzM0IiB5MT0iMCIgeTI9IjczLjkzOTE5MzciIGdyYWRpZW50VW5pdHM9InVzZXJTcGFjZU9uVXNlIj4KCQkJPHN0b3Agc3RvcC1jb2xvcj0icmdiKDI1NSwyNTUsMjU1KSIgb2Zmc2V0PSIwIiBzdG9wLW9wYWNpdHk9IjAuMzAwMDAwMDEyIiAvPgoJCQk8c3RvcCBzdG9wLWNvbG9yPSJyZ2IoMjU1LDI1NSwyNTUpIiBvZmZzZXQ9IjEiIHN0b3Atb3BhY2l0eT0iMCIgLz4KCQk8L2xpbmVhckdyYWRpZW50PgoJCTxsaW5lYXJHcmFkaWVudCBpZD0icGFpbnRfbGluZWFyXzIzIiB4MT0iMzguOTMyOTQ1MyIgeDI9IjM4LjkzMjk0NTMiIHkxPSIyMS4zMzM0OTYxIiB5Mj0iOTUuMjcyNjg5OCIgZ3JhZGllbnRVbml0cz0idXNlclNwYWNlT25Vc2UiPgoJCQk8c3RvcCBzdG9wLWNvbG9yPSJyZ2IoMjU1LDI1NSwyNTUpIiBvZmZzZXQ9IjAiIHN0b3Atb3BhY2l0eT0iMSIgLz4KCQkJPHN0b3Agc3RvcC1jb2xvcj0icmdiKDI1NSwyNTUsMjU1KSIgb2Zmc2V0PSIxIiBzdG9wLW9wYWNpdHk9IjAiIC8+CgkJPC9saW5lYXJHcmFkaWVudD4KCQk8bGluZWFyR3JhZGllbnQgaWQ9InBhaW50X2xpbmVhcl8yNCIgeDE9IjQ5LjU5OTM0NjIiIHgyPSI0OS41OTkzNDYyIiB5MT0iNTQuMzk5OTAyMyIgeTI9IjcxLjAzNjIyNDQiIGdyYWRpZW50VW5pdHM9InVzZXJTcGFjZU9uVXNlIj4KCQkJPHN0b3Agc3RvcC1jb2xvcj0icmdiKDI1NSwyNTUsMjU1KSIgb2Zmc2V0PSIwIiBzdG9wLW9wYWNpdHk9IjEiIC8+CgkJCTxzdG9wIHN0b3AtY29sb3I9InJnYigyNTUsMjU1LDI1NSkiIG9mZnNldD0iMSIgc3RvcC1vcGFjaXR5PSIwIiAvPgoJCTwvbGluZWFyR3JhZGllbnQ+CgkJPGxpbmVhckdyYWRpZW50IGlkPSJwYWludF9saW5lYXJfMjUiIHgxPSI3OC40MDAxMzEyIiB4Mj0iNzguNDAwMTMxMiIgeTE9IjU0LjM5OTkwMjMiIHkyPSI3MS4wMzYyMTY3IiBncmFkaWVudFVuaXRzPSJ1c2VyU3BhY2VPblVzZSI+CgkJCTxzdG9wIHN0b3AtY29sb3I9InJnYigyNTUsMjU1LDI1NSkiIG9mZnNldD0iMCIgc3RvcC1vcGFjaXR5PSIwLjMwMDAwMDAxMiIgLz4KCQkJPHN0b3Agc3RvcC1jb2xvcj0icmdiKDI1NSwyNTUsMjU1KSIgb2Zmc2V0PSIxIiBzdG9wLW9wYWNpdHk9IjAiIC8+CgkJPC9saW5lYXJHcmFkaWVudD4KCTwvZGVmcz4KCTxnIGlkPSJjYW5uYm90LeWNlWxvZ28iPgoJCTxnIGlkPSLlrrnlmaggOTEzMzQwNDAiIGN1c3RvbUZyYW1lPSJ1cmwoI2NsaXBQYXRoXzEyKSI+CgkJCTxyZWN0IGlkPSLlrrnlmaggOTEzMzQwNDAiIHdpZHRoPSIxMjguMDAwMDAwIiBoZWlnaHQ9IjEyNy45OTk5NTQiIHg9IjAuMDAwMDAwIiB5PSIwLjAwMDAwMCIgLz4KCQkJPGcgaWQ9Iue7hOWQiCA5MTMzNDA4NyI+CgkJCQk8cGF0aCBpZD0i55+i6YePIDYxMTgiIGQ9Ik01NC42NTYgMC4wMTEwMDk3QzU0LjY1NTggMC4wMTEwMTEzIDUxLjc2NjggMy42NzQ1N2UtMDUgNTEuNzY2OCAzLjY3NDU3ZS0wNUM1MS43NjY4IDMuNjc0NTdlLTA1IDUxLjc2NjggMy42NzYzNmUtMDUgNTEuNzY2NyAzLjY4MDEzZS0wNUM1MS42ODk5IDcuMTIxNjFlLTA1IDIyLjk4NDcgMC4wMTU4MDExIDIyLjgzNjkgMC4wMTEwMDk3QzE3LjE5MDkgLTAuMTcwMjExIDEyLjM2NjcgMS44OTg3MyA4LjA5NzU3IDUuMjU4MDlDMi4wOTk4IDkuOTcyMTggMC4xMjUyMTUgMTYuNTk1MSAwLjA1MDE3MTIgMjMuODI2Qy0wLjA1MDkyOTQgMzQuMjIyNSAwLjAyMDQ3NTggNDMuMDk2OCAwLjA5MTg3MTYgNTMuNDkzM0MwLjA5NjA0MDcgNTQuMDcwOCAwLjA5OTY4ODYgNTQuNjQ4NiAwLjEwMzg1OCA1NS4yMjYxQzAuMTA2NDYzIDU1Ljc0MTkgMC4xMDgwMjcgNTYuMjU4NSAwLjEwOTA2OSA1Ni43NzU4QzAuMTE1ODQ0IDU5Ljk5MjMgMC4xMjI2MTggNjMuMjMxOCAwLjU3MzQwMiA2Ni4zOTIzQzIuMjE3MDcgNzcuODM1OCAxMS4xNTA0IDg1LjMyMjYgMjIuNzgzOCA4NS4zMjI2QzIzLjAwNTYgODUuMzIyNiAzNi44MDk0IDg1LjMzMTYgMzcuMzU1MyA4NS4zMzMzQzM5LjI5NzUgODUuMzMzMyA0MC42MjEyIDg0LjY1MDggNDEuNDUzNSA4Mi44NDgzQzQyLjk3OTkgNzkuNDg4OSA0NC42NTU0IDc2LjIwNCA0Ni4yMTM2IDcyLjg1NTNDNDguMTc3NyA2OC42MjE0IDQ2Ljg2NSA2Ni42Njk2IDQyLjEyNjMgNjYuNjY5NkwyNS45NTMzIDY2LjY2OTZDMjUuNjU4NCA2Ni42Njk2IDI1LjM2MjMgNjYuNjcxNCAyNS4wNjYzIDY2LjY3M0wyNS4wNjU4IDY2LjY3M0MyNC4wNzc3IDY2LjY3ODcgMjMuMDg2IDY2LjY4NDQgMjIuMTAwNSA2Ni42MjY5QzIwLjI5NjkgNjYuNTMxMSAxOS4xNDQxIDY1LjMzNjUgMTkuMTQ0MSA2My41NjYyTDE5LjE0NDEgMjEuNjE4MkMxOS4xNDQxIDIwLjE5OTcgMTkuODU5MSAxOS4yNCAyMS4xODI4IDE4Ljg4NzlDMjIuMzI0NiAxOC41ODkzIDIzLjUzMDUgMTguNDI5NCAyNC43MTU2IDE4LjQyOTRDMzYuMzI3NiAxOC4zOTc0IDMwLjg2NjEgMTguNDA4MSA0Mi40NzggMTguNDI5NEM0NC43ODM1IDE4LjQyOTQgNDcuMDg5MSAxOC41NDY2IDQ5LjM5NDEgMTguNTU3M0M1MS4wMjczIDE4LjU1NzMgNTIuMjg2NCAxNy45MTc1IDUzLjAwMTkgMTYuMzYwNUM1NC43NDE0IDEyLjU2MzcgNTYuNTY2NSA4LjgyMDI4IDU4LjI0MTkgNS4wMDIxNEM1OS41MDE1IDIuMTIyNjUgNTcuODU3OCAtMC4wMjEwMTY0IDU0LjY1NiAwLjAyMTY4NTFMNTQuNjU2IDAuMDExMDA5N1oiIGZpbGw9InJnYigxOTksMCwxMSkiIGZpbGwtcnVsZT0iZXZlbm9kZCIgdHJhbnNmb3JtPSJtYXRyaXgoLTEsMCwwLC0xLDExOC40LDEwNi42NjcpIiAvPgoJCQkJPHBhdGggaWQ9IuefoumHjyA2MTE4IiBkPSJNNTEuNzY2OCAzLjY3NDU3ZS0wNUw1NC42NTU4IDAuMDExMDA5Mkw1NC42NTYgMC4wMTEwMDk3TDU0LjY1NTkgMC4wMTkzMTg5TDU0LjY1NTkgMC4wMjE2ODVMNTQuNjU2IDAuMDIxNjg0NEw1NC42NTYgMC4wMjE2ODUxQzU0LjY4OTcgMC4wMjEyMzUxIDU0LjcyMzMgMC4wMjEwMjc5IDU0Ljc1NjcgMC4wMjEwNjE5QzU0Ljc4NTMgMC4wMjEwOTEgNTQuODEzOCAwLjAyMTI5NzQgNTQuODQyMiAwLjAyMTY3OThMNTQuODQyNiAwLjAyMTY4NTFDNTcuMjAxOCAwLjA1MzYyNzUgNTguNjY2NyAxLjMwMzYxIDU4LjY2NjcgMy4xNTY0OUM1OC42NjY3IDMuNzIxNDcgNTguNTMwNSA0LjM0MjUgNTguMjQxOSA1LjAwMjE0QzU2LjU2NjUgOC44MjAyOCA1NC43NDE0IDEyLjU2MzcgNTMuMDAxOSAxNi4zNjA1QzUyLjI4NjQgMTcuOTE3NSA1MS4wMjczIDE4LjU1NzMgNDkuMzk0MSAxOC41NTczQzQ3LjA4OTEgMTguNTQ2NiA0NC43ODM1IDE4LjQyOTQgNDIuNDc4IDE4LjQyOTRDMzYuNjcyIDE4LjQxODggMzUuMTM0NCAxOC40MTA3IDMzLjU5NjggMTguNDA5NEMzMi4zMDAzIDE4LjQwODMgMzEuMDAzOCAxOC40MTE5IDI3LjE0ODYgMTguNDIyN0MyNi40MzE2IDE4LjQyNDcgMjUuNjI2MSAxOC40MjY5IDI0LjcxNTYgMTguNDI5NEMyMy41MzA1IDE4LjQyOTQgMjIuMzI0NiAxOC41ODkzIDIxLjE4MjggMTguODg3OUMxOS44NTkxIDE5LjI0IDE5LjE0NDEgMjAuMTk5NyAxOS4xNDQxIDIxLjYxODJMMTkuMTQ0MSA2My41NjYyQzE5LjE0NDEgNjUuMzM2NSAyMC4yOTY5IDY2LjUzMTEgMjIuMTAwNSA2Ni42MjY5QzIzLjA4NiA2Ni42ODQ0IDI0LjA3NzcgNjYuNjc4NyAyNS4wNjU4IDY2LjY3M0wyNS4wNjYzIDY2LjY3M0MyNS4zNjIzIDY2LjY3MTQgMjUuNjU4NCA2Ni42Njk2IDI1Ljk1MzMgNjYuNjY5Nkw0Mi4xMjYzIDY2LjY2OTZDNDUuNDU0MyA2Ni42Njk2IDQ3LjA5MjYgNjcuNjMyMyA0Ny4wOTI2IDY5LjY3MjJDNDcuMDkyNiA3MC41MzY4IDQ2Ljc5ODMgNzEuNTk0OSA0Ni4yMTM2IDcyLjg1NTNDNDQuNjU1NCA3Ni4yMDQgNDIuOTc5OSA3OS40ODg5IDQxLjQ1MzUgODIuODQ4M0M0MC42MjEyIDg0LjY1MDggMzkuMjk3NSA4NS4zMzMzIDM3LjM1NTMgODUuMzMzM0MzNi44MDk0IDg1LjMzMTYgMjMuMDA1NiA4NS4zMjI2IDIyLjc4MzggODUuMzIyNkMxMS4xNTA0IDg1LjMyMjYgMi4yMTcwNyA3Ny44MzU4IDAuNTczNDAyIDY2LjM5MjNDMC4xMjI2MTggNjMuMjMxOCAwLjExNTg0NCA1OS45OTIzIDAuMTA5MDY5IDU2Ljc3NThDMC4xMDgwMjcgNTYuMjU4NSAwLjEwNjQ2MyA1NS43NDE5IDAuMTAzODU4IDU1LjIyNjFDMC4wOTk2ODg2IDU0LjY0ODYgMC4wOTYwNDA3IDU0LjA3MDggMC4wOTE4NzE2IDUzLjQ5MzNDMC4wODc5ODE4IDUyLjkyNjkgMC4wODQwOTIxIDUyLjM2NSAwLjA4MDIzMDIgNTEuODA3MUMwLjAzODQ4NzEgNDUuNzc3MSAwIDQwLjIxNzQgMCAzNC41MDY0QzAgMzEuMDQ3OCAwLjAxNDExNTUgMjcuNTMzNyAwLjA1MDE3MTIgMjMuODI2QzAuMTI1MjE1IDE2LjU5NTEgMi4wOTk4IDkuOTcyMTggOC4wOTc1NyA1LjI1ODA5QzEyLjM2NjcgMS44OTg3MyAxNy4xOTA5IC0wLjE3MDIxMSAyMi44MzY5IDAuMDExMDA5N0MyMi45NzkzIDAuMDE1NjI0MSA0OS42MDgyIDAuMDAxMjA1MzEgNTEuNjQzOSAwLjAwMDEwMzAzOEw1MS43NjY3IDMuNjgwMTNlLTA1TDUxLjc2NjggMy42NzQ1N2UtMDVaTTUxLjc2NzcgMi4wMDAwNEw1MS43Njc2IDIuMDAwMDRMNTEuNzYzNSAyLjAwMDA0TDM3LjMwMjYgMi4wMDczNEwyMi44MDUxIDIuMDExMDJMMjIuNzcyNyAyLjAwOTk4UTIxLjM5ODQgMS45NjU4NyAyMC4wNDc1IDIuMTIzNDFMMjAuMDQ3NCAyLjEyMzQyTDIwLjA0NzMgMi4xMjM0NFExNC40OTE5IDIuNzcxNCA5LjMzNDM2IDYuODI5ODNRNy4yOTA2NCA4LjQzNjE0IDUuODI4MzkgMTAuNDYyMUw1LjgyODM2IDEwLjQ2MjJRNC41NDYyNiAxMi4yMzg1IDMuNzExMTggMTQuMzM3NlEyLjEwNjkgMTguMzcgMi4wNTAwNiAyMy44NDY3UTIuMDA4ODYgMjguMDg0IDIuMDA4ODYgMzMuODczM1EyLjAwODg2IDQxLjQ5MDEgMi4wODAxOCA1MS43OTMzQzIuMDg1MzMgNTIuNTM3NSAyLjA4OTIxIDUzLjA5OTYgMi4wOTE4MiA1My40Nzk2TDIuMDk3ODEgNTQuMzQ0OUwyLjEwMzgxIDU1LjIxMjNMMi4xMDkwNiA1Ni43NjkxTDIuMTA5MDcgNTYuNzcyN0MyLjExMzU0IDU4Ljg5NzYgMi4xMzQ5OSA2MC40ODQxIDIuMTczNDEgNjEuNTMyM0MyLjIzNjM0IDYzLjI0OTMgMi4zNjI5OSA2NC43NzUyIDIuNTUzMzYgNjYuMTA5OUMyLjkyNTIxIDY4LjY5ODcgMy42OTQxOSA3MS4wNzA4IDQuODYwMyA3My4yMjYyUTUuOTA0MjMgNzUuMTU1NiA3LjMxOTU3IDc2Ljc1NjhMNy4zMTk2NSA3Ni43NTY5TDcuMzIwODggNzYuNzU4M0M3LjkwODA1IDc3LjQyMjQgOC41NDMxNSA3OC4wNDQyIDkuMjI2MTggNzguNjIzNVE5LjkyMzA4IDc5LjIxNDcgMTAuNjcwMyA3OS43MzMzTDEwLjY3MDUgNzkuNzMzNEwxMC42NzA4IDc5LjczMzZMMTAuNjcyNiA3OS43MzQ5UTEyLjc4NTkgODEuMjAxMiAxNS4zMDE0IDgyLjA4NzdDMTcuNjM3NyA4Mi45MTEgMjAuMTMxOCA4My4zMjI2IDIyLjc4MzggODMuMzIyNkwzMC4wNzc4IDgzLjMyNzRMMzcuMzU2OSA4My4zMzMzUTM4LjMwOTUgODMuMzMzMyAzOC44MTE4IDgzLjAzOThDMzkuMTMxNiA4Mi44NTMgMzkuNDA2OSA4Mi41MDk3IDM5LjYzNzcgODIuMDA5OUM0MC4yMDY0IDgwLjc1ODEgNDEuMDkwNSA3OC44OTU4IDQyLjI4OTggNzYuNDIyOUM0My4yMzk1IDc0LjQ2NDggNDMuOTQzIDcyLjk5NDMgNDQuNDAwMyA3Mi4wMTE2QzQ0Ljc5NzUgNzEuMTU1MiA0NS4wMjQyIDcwLjQ1MTUgNDUuMDgwMiA2OS45MDA0QzQ1LjA4OTMgNjkuODEwMyA0NS4wOTM5IDY5LjcyODcgNDUuMDkzOSA2OS42NTU3QzQ1LjA5MzkgNjkuNDgyOCA0NS4wNjgzIDY5LjM1NzggNDUuMDE3IDY5LjI4MDZDNDQuOTM2NSA2OS4xNTkyIDQ0LjczNjIgNjkuMDQ1OSA0NC40MTYzIDY4Ljk0MDlDNDMuODY1NSA2OC43NiA0My4xMDIxIDY4LjY2OTYgNDIuMTI2MyA2OC42Njk2TDI1Ljk1MzMgNjguNjY5NkwyNS4wOTEgNjguNjcyOUwyNS4wNzcgNjguNjcyOUwyNS4wNjU4IDY4LjY3M0MyMy43MTEyIDY4LjY4MDggMjIuNjgzOSA2OC42NjQzIDIxLjk4NCA2OC42MjM1QzIxLjAzMjEgNjguNTcyOSAyMC4xOTcyIDY4LjMyOTcgMTkuNDc5MiA2Ny44OTM5UTE4Ljk1MSA2Ny41NzMzIDE4LjUwNzMgNjcuMTEzOEMxOC4xODg2IDY2Ljc4MzcgMTcuOTI1OCA2Ni40MjQgMTcuNzE4OCA2Ni4wMzQ2QzE3LjMzNTcgNjUuMzEzNiAxNy4xNDQxIDY0LjQ5MDggMTcuMTQ0MSA2My41NjYyTDE3LjE0NDEgMjEuNjE4MlExNy4xNDQxIDIwLjI2MzMgMTcuNzA5NiAxOS4yMTI4TDE3LjcwOTcgMTkuMjEyNkMxNy44MTM2IDE5LjAxOTcgMTcuOTMxNyAxOC44MzQ1IDE4LjA2NDIgMTguNjU3QzE4LjI0NiAxOC40MTMzIDE4LjQ0ODMgMTguMTkyNiAxOC42NzA4IDE3Ljk5NDhMMTguNjcxMSAxNy45OTQ2UTE5LjQ4NzMgMTcuMjY5MyAyMC42Njg4IDE2Ljk1NTFDMjEuNzQxMyAxNi42NzQ2IDIyLjgxOTYgMTYuNTA2MyAyMy45MDM2IDE2LjQ1MDRDMjQuMTczOSAxNi40MzY0IDI0LjQ0NDYgMTYuNDI5NCAyNC43MTU2IDE2LjQyOTRMMzMuNTkyMyAxNi40MDk0TDQyLjQ4MjUgMTYuNDI5NEM0My4zMDI1IDE2LjQyOTQgNDQuNTI2NiAxNi40NTExIDQ2LjE1NDcgMTYuNDk0NUM0Ny42MDM1IDE2LjUzMyA0OC42ODY0IDE2LjU1NCA0OS40MDMzIDE2LjU1NzNDNDkuODgwNSAxNi41NTczIDUwLjI1NzcgMTYuNDc2NSA1MC41MzUgMTYuMzE0OFE1MC45MjY3IDE2LjA4NjYgNTEuMTg0NiAxNS41MjU0QzUxLjYyMDggMTQuNTczNCA1Mi4yODIyIDEzLjE1MjIgNTMuMTY4OCAxMS4yNjE5UTU1LjM3MjUgNi41NjM5NSA1Ni40MTA1IDQuMTk4NDhRNTYuNjc1OSAzLjU5MTg0IDU2LjY3NTkgMy4xNjQyQzU2LjY3NTkgMi45NTEyMSA1Ni42MjY1IDIuNzcxNTMgNTYuNTI3NyAyLjYyNTE1QzU2LjUyMTkgMi42MTY1MSA1Ni41MTU5IDIuNjA3OTkgNTYuNTA5OCAyLjU5OTU5UTU2LjA3MTggMi4wMDI5OCA1NC42ODI2IDIuMDIxNTFMNTIuNjU2IDIuMDQ4NTRMNTIuNjU2IDIuMDAzNDNMNTEuNzY3NyAyLjAwMDA0WiIgZmlsbD0idXJsKCNwYWludF9saW5lYXJfMjIpIiBmaWxsLW9wYWNpdHk9IjAiIGZpbGwtcnVsZT0iZXZlbm9kZCIgdHJhbnNmb3JtPSJtYXRyaXgoLTEsMCwwLC0xLDExOC40LDEwNi42NjcpIiAvPgoJCQkJPHBhdGggaWQ9IuefoumHjyA2MTE5IiBkPSJNNjQuMjU1NiAyMS4zNDQ1QzY0LjI1NTQgMjEuMzQ0NSA2MS4zNjY1IDIxLjMzMzUgNjEuMzY2NSAyMS4zMzM1QzYxLjM2NjUgMjEuMzMzNSA2MS4zNjY0IDIxLjMzMzUgNjEuMzY2MyAyMS4zMzM1QzYxLjI4OTUgMjEuMzMzNiAzMi41ODQzIDIxLjM0OTMgMzIuNDM2NSAyMS4zNDQ1QzI2Ljc5MDUgMjEuMTYzMyAyMS45NjYzIDIzLjIzMjIgMTcuNjk3MiAyNi41OTE2QzExLjY5OTQgMzEuMzA1NyA5LjcyNDgyIDM3LjkyODYgOS42NDk3OCA0NS4xNTk1QzkuNTQ4NjggNTUuNTU2IDkuNjIwMDggNjQuNDMwMyA5LjY5MTQ4IDc0LjgyNjhDOS42OTU2NSA3NS40MDQzIDkuNjk5MyA3NS45ODIxIDkuNzAzNDcgNzYuNTU5NkM5LjcwNjA3IDc3LjA3NTQgOS43MDc2NCA3Ny41OTIgOS43MDg2OCA3OC4xMDkzQzkuNzE1NDUgODEuMzI1OCA5LjcyMjIzIDg0LjU2NTMgMTAuMTczIDg3LjcyNThDMTEuODE2NyA5OS4xNjkzIDIwLjc1IDEwNi42NTYgMzIuMzgzNCAxMDYuNjU2QzMyLjYwNTIgMTA2LjY1NiA0Ni40MDkgMTA2LjY2NSA0Ni45NTQ5IDEwNi42NjdDNDguODk3MiAxMDYuNjY3IDUwLjIyMDggMTA1Ljk4NCA1MS4wNTMxIDEwNC4xODJDNTIuNTc5NSAxMDAuODIyIDU0LjI1NSA5Ny41Mzc1IDU1LjgxMzIgOTQuMTg4OEM1Ny43NzczIDg5Ljk1NDkgNTYuNDY0NiA4OC4wMDMxIDUxLjcyNTkgODguMDAzMUwzNS41NTI5IDg4LjAwMzFDMzUuMjU4IDg4LjAwMzEgMzQuOTYyIDg4LjAwNDkgMzQuNjY2IDg4LjAwNjVMMzQuNjY1NCA4OC4wMDY1QzMzLjY3NzQgODguMDEyMiAzMi42ODU2IDg4LjAxNzkgMzEuNzAwMiA4Ny45NjA0QzI5Ljg5NjUgODcuODY0NiAyOC43NDM3IDg2LjY3IDI4Ljc0MzcgODQuODk5N0wyOC43NDM3IDQyLjk1MTdDMjguNzQzNyA0MS41MzMyIDI5LjQ1ODcgNDAuNTczNSAzMC43ODI0IDQwLjIyMTRDMzEuOTI0MiAzOS45MjI4IDMzLjEzMDEgMzkuNzYyOSAzNC4zMTUyIDM5Ljc2MjlDNDUuOTI3MiAzOS43MzA5IDQwLjQ2NTcgMzkuNzQxNiA1Mi4wNzc2IDM5Ljc2MjlDNTQuMzgzMiAzOS43NjI5IDU2LjY4ODcgMzkuODgwMSA1OC45OTM3IDM5Ljg5MDhDNjAuNjI2OSAzOS44OTA4IDYxLjg4NiAzOS4yNTEgNjIuNjAxNSAzNy42OTRDNjQuMzQxIDMzLjg5NzIgNjYuMTY2MSAzMC4xNTM4IDY3Ljg0MTUgMjYuMzM1NkM2OS4xMDExIDIzLjQ1NjIgNjcuNDU3NSAyMS4zMTI1IDY0LjI1NTYgMjEuMzU1Mkw2NC4yNTU2IDIxLjM0NDVaIiBmaWxsPSJyZ2IoMzUsMjMsMjIpIiBmaWxsLXJ1bGU9ImV2ZW5vZGQiIC8+CgkJCQk8cGF0aCBpZD0i55+i6YePIDYxMTkiIGQ9Ik02MS4zNjY1IDIxLjMzMzVMNjQuMjU1NCAyMS4zNDQ1TDY0LjI1NTYgMjEuMzQ0NUw2NC4yNTU2IDIxLjM1MjhMNjQuMjU1NSAyMS4zNTUyTDY0LjI1NTYgMjEuMzU1Mkw2NC4yNTU2IDIxLjM1NTJDNjQuMjg5MyAyMS4zNTQ3IDY0LjMyMjkgMjEuMzU0NSA2NC4zNTYzIDIxLjM1NDZDNjQuMzg0OSAyMS4zNTQ2IDY0LjQxMzQgMjEuMzU0OCA2NC40NDE4IDIxLjM1NTJMNjQuNDQyMiAyMS4zNTUyQzY2LjgwMTUgMjEuMzg3MSA2OC4yNjYzIDIyLjYzNzEgNjguMjY2MyAyNC40OUM2OC4yNjYzIDI1LjA1NSA2OC4xMzAxIDI1LjY3NiA2Ny44NDE1IDI2LjMzNTZDNjYuMTY2MSAzMC4xNTM4IDY0LjM0MSAzMy44OTcyIDYyLjYwMTUgMzcuNjk0QzYxLjg4NiAzOS4yNTEgNjAuNjI2OSAzOS44OTA4IDU4Ljk5MzcgMzkuODkwOEM1Ni42ODg3IDM5Ljg4MDEgNTQuMzgzMiAzOS43NjI5IDUyLjA3NzYgMzkuNzYyOUM0Ni4yNzE2IDM5Ljc1MjIgNDQuNzM0IDM5Ljc0NDIgNDMuMTk2NCAzOS43NDI5QzQxLjg5OTkgMzkuNzQxOCA0MC42MDM1IDM5Ljc0NTQgMzYuNzQ4MiAzOS43NTYyQzM2LjAzMTIgMzkuNzU4MiAzNS4yMjU3IDM5Ljc2MDQgMzQuMzE1MiAzOS43NjI5QzMzLjEzMDEgMzkuNzYyOSAzMS45MjQyIDM5LjkyMjggMzAuNzgyNCA0MC4yMjE0QzI5LjQ1ODcgNDAuNTczNSAyOC43NDM3IDQxLjUzMzIgMjguNzQzNyA0Mi45NTE3TDI4Ljc0MzcgODQuODk5N0MyOC43NDM3IDg2LjY3IDI5Ljg5NjUgODcuODY0NiAzMS43MDAyIDg3Ljk2MDRDMzIuNjg1NiA4OC4wMTc5IDMzLjY3NzQgODguMDEyMiAzNC42NjU0IDg4LjAwNjVMMzQuNjY2IDg4LjAwNjVDMzQuOTYyIDg4LjAwNDkgMzUuMjU4IDg4LjAwMzEgMzUuNTUyOSA4OC4wMDMxTDUxLjcyNTkgODguMDAzMUM1NS4wNTQgODguMDAzMSA1Ni42OTIyIDg4Ljk2NTggNTYuNjkyMiA5MS4wMDU3QzU2LjY5MjIgOTEuODcwMyA1Ni4zOTc5IDkyLjkyODQgNTUuODEzMiA5NC4xODg4QzU0LjI1NSA5Ny41Mzc1IDUyLjU3OTUgMTAwLjgyMiA1MS4wNTMxIDEwNC4xODJDNTAuMjIwOCAxMDUuOTg0IDQ4Ljg5NzIgMTA2LjY2NyA0Ni45NTQ5IDEwNi42NjdDNDYuNDA5IDEwNi42NjUgMzIuNjA1MiAxMDYuNjU2IDMyLjM4MzQgMTA2LjY1NkMyMC43NSAxMDYuNjU2IDExLjgxNjcgOTkuMTY5MyAxMC4xNzMgODcuNzI1OEM5LjcyMjIzIDg0LjU2NTMgOS43MTU0NSA4MS4zMjU4IDkuNzA4NjggNzguMTA5M0M5LjcwNzY0IDc3LjU5MiA5LjcwNjA3IDc3LjA3NTQgOS43MDM0NyA3Ni41NTk2QzkuNjk5MyA3NS45ODIxIDkuNjk1NjUgNzUuNDA0MyA5LjY5MTQ4IDc0LjgyNjhDOS42ODc1OSA3NC4yNjA0IDkuNjgzNyA3My42OTg1IDkuNjc5ODQgNzMuMTQwNkM5LjYzODEgNjcuMTEwNiA5LjU5OTYxIDYxLjU1MDkgOS41OTk2MSA1NS44Mzk5QzkuNTk5NjEgNTIuMzgxMyA5LjYxMzcyIDQ4Ljg2NzIgOS42NDk3OCA0NS4xNTk1QzkuNzI0ODIgMzcuOTI4NiAxMS42OTk0IDMxLjMwNTcgMTcuNjk3MiAyNi41OTE2QzIxLjk2NjMgMjMuMjMyMiAyNi43OTA1IDIxLjE2MzMgMzIuNDM2NSAyMS4zNDQ1QzMyLjU3ODkgMjEuMzQ5MSA1OS4yMDc4IDIxLjMzNDcgNjEuMjQzNSAyMS4zMzM2TDYxLjM2NjMgMjEuMzMzNUw2MS4zNjY1IDIxLjMzMzVaTTYxLjM2NzMgMjMuMzMzNUw2MS4zNjcyIDIzLjMzMzVMNjEuMzYzMSAyMy4zMzM1TDQ2LjkwMjIgMjMuMzQwOEwzMi40MDQ3IDIzLjM0NDVMMzIuMzcyNCAyMy4zNDM1UTMwLjk5NzggMjMuMjk5NCAyOS42NDY5IDIzLjQ1NjlRMjQuMDkxNSAyNC4xMDQ5IDE4LjkzNCAyOC4xNjMzUTE2Ljg5MDMgMjkuNzY5NiAxNS40MjggMzEuNzk1NkwxNS40MjggMzEuNzk1NkwxNS40Mjc5IDMxLjc5NTdRMTQuMTQ1OSAzMy41NzIxIDEzLjMxMDggMzUuNjcxMVExMS43MDY1IDM5LjcwMzUgMTEuNjQ5NyA0NS4xODAyUTExLjYwODUgNDkuNDE3NSAxMS42MDg1IDU1LjIwNjhRMTEuNjA4NSA2Mi44MjM2IDExLjY3OTggNzMuMTI2OEMxMS42ODUgNzMuODczMyAxMS42ODg4IDc0LjQzNTQgMTEuNjkxNCA3NC44MTMxTDExLjY5NzQgNzUuNjc4NEwxMS43MDM0IDc2LjU0NThMMTEuNzA4NyA3OC4xMDI2TDExLjcwODcgNzguMTA2MlExMS43MTU0IDgxLjI5MzUgMTEuNzczIDgyLjg2NThRMTEuODY3NCA4NS40NDEzIDEyLjE1MyA4Ny40NDM0QzEyLjUyNDggOTAuMDMyMiAxMy4yOTM4IDkyLjQwNDMgMTQuNDU5OSA5NC41NTk2UTE1LjUwMzggOTYuNDg5MSAxNi45MTkyIDk4LjA5MDNMMTYuOTE5MyA5OC4wOTA0TDE2LjkyMDUgOTguMDkxOEMxNy41MDc3IDk4Ljc1NTkgMTguMTQyOCA5OS4zNzc3IDE4LjgyNTggOTkuOTU3UTE5LjUyMjcgMTAwLjU0OCAyMC4yNjk5IDEwMS4wNjdMMjAuMjcwMSAxMDEuMDY3TDIwLjI3MDQgMTAxLjA2N0wyMC4yNzIyIDEwMS4wNjhRMjIuMzg1NSAxMDIuNTM1IDI0LjkwMTEgMTAzLjQyMUMyNy4yMzczIDEwNC4yNDQgMjkuNzMxNCAxMDQuNjU2IDMyLjM4MzQgMTA0LjY1NkwzOS42Nzc0IDEwNC42NjFMNDYuOTU2NSAxMDQuNjY3UTQ3LjkwOTEgMTA0LjY2NyA0OC40MTE0IDEwNC4zNzNDNDguNzMxMyAxMDQuMTg2IDQ5LjAwNjYgMTAzLjg0MyA0OS4yMzczIDEwMy4zNDNDNDkuODA2IDEwMi4wOTIgNTAuNjkwMSAxMDAuMjI5IDUxLjg4OTQgOTcuNzU2NEM1Mi44MzkxIDk1Ljc5ODMgNTMuNTQyNiA5NC4zMjc4IDUzLjk5OTkgOTMuMzQ1MUM1NC4zOTcxIDkyLjQ4ODcgNTQuNjIzOCA5MS43ODUgNTQuNjc5OCA5MS4yMzM5QzU0LjY4ODkgOTEuMTQzOCA1NC42OTM1IDkxLjA2MjIgNTQuNjkzNSA5MC45ODkyQzU0LjY5MzUgOTAuODE2MyA1NC42Njc5IDkwLjY5MTMgNTQuNjE2NiA5MC42MTQxQzU0LjUzNjEgOTAuNDkyNyA1NC4zMzU4IDkwLjM3OTQgNTQuMDE2IDkwLjI3NDRDNTMuNDY1MSA5MC4wOTM1IDUyLjcwMTcgOTAuMDAzMSA1MS43MjU5IDkwLjAwMzFMMzUuNTUyOSA5MC4wMDMxTDM0LjY5MDYgOTAuMDA2NEwzNC42NzY3IDkwLjAwNjRMMzQuNjY1NCA5MC4wMDY1QzMzLjMxMDggOTAuMDE0MyAzMi4yODM1IDg5Ljk5NzggMzEuNTgzNiA4OS45NTdDMzAuNjMxNyA4OS45MDY0IDI5Ljc5NjggODkuNjYzMiAyOS4wNzg4IDg5LjIyNzRDMjguNzI2NyA4OS4wMTM3IDI4LjQwMjcgODguNzUzNiAyOC4xMDY5IDg4LjQ0NzNDMjcuNzg4MiA4OC4xMTcyIDI3LjUyNTQgODcuNzU3NSAyNy4zMTg1IDg3LjM2ODFDMjYuOTM1MyA4Ni42NDcxIDI2Ljc0MzcgODUuODI0MyAyNi43NDM3IDg0Ljg5OTdMMjYuNzQzNyA0Mi45NTE3UTI2Ljc0MzcgNDEuNTk2OCAyNy4zMDkyIDQwLjU0NjNMMjcuMzA5MyA0MC41NDYxQzI3LjQxMzIgNDAuMzUzMiAyNy41MzEzIDQwLjE2OCAyNy42NjM4IDM5Ljk5MDVDMjcuODQ1NyAzOS43NDY4IDI4LjA0NzkgMzkuNTI2MSAyOC4yNzA1IDM5LjMyODNRMjkuMDg2NyAzOC42MDI5IDMwLjI2ODQgMzguMjg4NkMzMS4zNDA5IDM4LjAwODEgMzIuNDE5MiAzNy44Mzk4IDMzLjUwMzIgMzcuNzgzOUMzMy43NzM1IDM3Ljc2OTkgMzQuMDQ0MiAzNy43NjI5IDM0LjMxNTIgMzcuNzYyOUw0My4xOTE5IDM3Ljc0MjlMNTIuMDgyMiAzNy43NjI5QzUyLjkwMjEgMzcuNzYyOSA1NC4xMjYyIDM3Ljc4NDYgNTUuNzU0NCAzNy44Mjc5QzU3LjIwMzEgMzcuODY2NSA1OC4yODYgMzcuODg3NSA1OS4wMDI5IDM3Ljg5MDhDNTkuNDgwMSAzNy44OTA4IDU5Ljg1NzMgMzcuODEgNjAuMTM0NiAzNy42NDgzUTYwLjUyNjMgMzcuNDIwMSA2MC43ODQyIDM2Ljg1ODlDNjEuMjIwNCAzNS45MDY5IDYxLjg4MTggMzQuNDg1NyA2Mi43Njg1IDMyLjU5NTRRNjQuOTcyMSAyNy44OTc0IDY2LjAxMDEgMjUuNTMyUTY2LjI3NTUgMjQuOTI1MyA2Ni4yNzU1IDI0LjQ5NzdDNjYuMjc1NSAyNC4yODQ3IDY2LjIyNjEgMjQuMTA1IDY2LjEyNzMgMjMuOTU4NkM2Ni4xMjE1IDIzLjk1IDY2LjExNTUgMjMuOTQxNSA2Ni4xMDk0IDIzLjkzMzFRNjUuNjcxNCAyMy4zMzY1IDY0LjI4MjMgMjMuMzU1TDYyLjI1NTYgMjMuMzgyTDYyLjI1NTYgMjMuMzM2OUw2MS4zNjczIDIzLjMzMzVaIiBmaWxsPSJ1cmwoI3BhaW50X2xpbmVhcl8yMykiIGZpbGwtb3BhY2l0eT0iMCIgZmlsbC1ydWxlPSJldmVub2RkIiAvPgoJCQkJPHBhdGggaWQ9IuefoumHjyA2MTA5IiBkPSJNMzkuNTkwMSA3My41OTk5TDUxLjg0MDIgNzMuNTk5OUM1NC4zNjk0IDczLjU5OTkgNTYuNjYxMyA3Mi4xMTA0IDU3LjY4ODYgNjkuNzk5Mkw2Mi41MzI4IDU4Ljg5OTVDNjMuNDczMyA1Ni43ODM0IDYxLjkyNDQgNTQuMzk5OSA1OS42MDg2IDU0LjM5OTlMNDcuMzU4NSA1NC4zOTk5QzQ0LjgyOTMgNTQuMzk5OSA0Mi41MzczIDU1Ljg4OTQgNDEuNTEwMSA1OC4yMDA2TDM2LjY2NTkgNjkuMTAwM0MzNS43MjU0IDcxLjIxNjQgMzcuMjc0MyA3My41OTk5IDM5LjU5MDEgNzMuNTk5OVoiIGZpbGw9InJnYigzNSwyMywyMikiIGZpbGwtcnVsZT0iZXZlbm9kZCIgLz4KCQkJCTxwYXRoIGlkPSLnn6Lph48gNjEwOSIgZD0iTTM2LjM4NjQgNzAuNDAxQzM2LjM4NjQgNjkuOTcxMiAzNi40NzQ4IDY5LjUzMDIgMzYuNjY1OSA2OS4xMDAzTDQxLjUxMDEgNTguMjAwNkM0Mi41MzczIDU1Ljg4OTQgNDQuODI5MyA1NC4zOTk5IDQ3LjM1ODUgNTQuMzk5OUw1OS42MDg2IDU0LjM5OTlDNjEuNDUzOCA1NC4zOTk5IDYyLjgxMjIgNTUuOTEzMyA2Mi44MTIyIDU3LjU5ODhDNjIuODEyMiA1OC4wMjg2IDYyLjcyMzkgNTguNDY5NiA2Mi41MzI4IDU4Ljg5OTVMNTcuNjg4NiA2OS43OTkyQzU2LjY2MTMgNzIuMTEwNCA1NC4zNjk0IDczLjU5OTkgNTEuODQwMiA3My41OTk5TDM5LjU5MDEgNzMuNTk5OUMzNy43NDQ4IDczLjU5OTkgMzYuMzg2NCA3Mi4wODY1IDM2LjM4NjQgNzAuNDAxWk01MS44NDAyIDcxLjU5OTlRNTIuNDkyMiA3MS41OTk5IDUzLjA5MTYgNzEuNDIyMkM1My40OTEyIDcxLjMwMzggNTMuODczMyA3MS4xMjYxIDU0LjIzNzggNzAuODg5M0M1NC42MDIzIDcwLjY1MjQgNTQuOTE5OCA3MC4zNzU0IDU1LjE5MDMgNzAuMDU4M0M1NS40NjA4IDY5Ljc0MTMgNTUuNjg0NCA2OS4zODQxIDU1Ljg2MDkgNjguOTg2OUw2MC43MDUyIDU4LjA4NzNRNjAuODE4MiA1Ny44MzMxIDYwLjgxODIgNTcuNTg3OUM2MC44MTgyIDU3LjU2IDYwLjgxNzEgNTcuNTMyMSA2MC44MTQ5IDU3LjUwNDRDNjAuNzk5OCA1Ny4zMTQyIDYwLjczMzEgNTcuMTI4IDYwLjYxNDggNTYuOTQ2QzYwLjQ5NjUgNTYuNzY0IDYwLjM1MzUgNTYuNjI3NCA2MC4xODU4IDU2LjUzNjRDNjAuMDE4MSA1Ni40NDU0IDU5LjgyNTcgNTYuMzk5OSA1OS42MDg2IDU2LjM5OTlMNDcuMzU4NSA1Ni4zOTk5QzQ2LjkyMzggNTYuMzk5OSA0Ni41MDY3IDU2LjQ1OTEgNDYuMTA3MSA1Ni41Nzc2TDQ2LjEwNyA1Ni41Nzc2UTQ1LjUwNzYgNTYuNzU1MiA0NC45NjA5IDU3LjExMDVDNDQuNTk2NCA1Ny4zNDc0IDQ0LjI3ODkgNTcuNjI0NCA0NC4wMDg0IDU3Ljk0MTRDNDMuNzM3OSA1OC4yNTg1IDQzLjUxNDMgNTguNjE1NyA0My4zMzc4IDU5LjAxMjlMMzguNDkzNSA2OS45MTI1UTM4LjM4MDUgNzAuMTY2NyAzOC4zODA1IDcwLjQxMTlRMzguMzgwNSA3MC40NTM4IDM4LjM4MzggNzAuNDk1NFEzOC40MDY0IDcwLjc4MDcgMzguNTgzOSA3MS4wNTM4QzM4LjcwMjIgNzEuMjM1OCAzOC44NDUyIDcxLjM3MjQgMzkuMDEyOSA3MS40NjM0TDM5LjAxMjkgNzEuNDYzNFEzOS4yNjQ0IDcxLjU5OTkgMzkuNTkwMSA3MS41OTk5TDUxLjg0MDIgNzEuNTk5OVoiIGZpbGw9InVybCgjcGFpbnRfbGluZWFyXzI0KSIgZmlsbC1vcGFjaXR5PSIwIiBmaWxsLXJ1bGU9ImV2ZW5vZGQiIC8+CgkJCQk8cGF0aCBpZD0i55+i6YePIDYxMTUiIGQ9Ik02OC4zOTA4IDczLjU5OTlMODAuNjQwOSA3My41OTk5QzgzLjE3MDIgNzMuNTk5OSA4NS40NjIxIDcyLjExMDQgODYuNDg5MyA2OS43OTkyTDkxLjMzMzYgNTguODk5NUM5Mi4yNzQxIDU2Ljc4MzQgOTAuNzI1MSA1NC4zOTk5IDg4LjQwOTQgNTQuMzk5OUw3Ni4xNTkzIDU0LjM5OTlDNzMuNjMwMSA1NC4zOTk5IDcxLjMzODEgNTUuODg5NCA3MC4zMTA5IDU4LjIwMDZMNjUuNDY2NiA2OS4xMDAzQzY0LjUyNjEgNzEuMjE2NCA2Ni4wNzUxIDczLjU5OTkgNjguMzkwOCA3My41OTk5WiIgZmlsbD0icmdiKDE5OSwwLDExKSIgZmlsbC1ydWxlPSJldmVub2RkIiAvPgoJCQkJPHBhdGggaWQ9IuefoumHjyA2MTE1IiBkPSJNODAuNjQwOSA3My41OTk5TDY4LjM5MDggNzMuNTk5OUM2Ni41NDU2IDczLjU5OTkgNjUuMTg3MiA3Mi4wODY1IDY1LjE4NzIgNzAuNDAxQzY1LjE4NzIgNjkuOTcxMiA2NS4yNzU2IDY5LjUzMDIgNjUuNDY2NiA2OS4xMDAzTDcwLjMxMDkgNTguMjAwNkM3MS4zMzgxIDU1Ljg4OTQgNzMuNjMwMSA1NC4zOTk5IDc2LjE1OTMgNTQuMzk5OUw4OC40MDk0IDU0LjM5OTlDOTAuMjU0NiA1NC4zOTk5IDkxLjYxMyA1NS45MTMzIDkxLjYxMyA1Ny41OTg4QzkxLjYxMyA1OC4wMjg2IDkxLjUyNDcgNTguNDY5NiA5MS4zMzM2IDU4Ljg5OTVMODYuNDg5MyA2OS43OTkyQzg1LjQ2MjEgNzIuMTEwNCA4My4xNzAyIDczLjU5OTkgODAuNjQwOSA3My41OTk5Wk04MC42NDA5IDcxLjU5OTlDODEuMDc1NyA3MS41OTk5IDgxLjQ5MjggNzEuNTQwNyA4MS44OTI0IDcxLjQyMjJDODIuMjkyIDcxLjMwMzggODIuNjc0MSA3MS4xMjYxIDgzLjAzODYgNzAuODg5M0M4My40MDMxIDcwLjY1MjQgODMuNzIwNiA3MC4zNzU0IDgzLjk5MTEgNzAuMDU4M0M4NC4yNjE2IDY5Ljc0MTMgODQuNDg1MiA2OS4zODQxIDg0LjY2MTcgNjguOTg2OUw4OS41MDYgNTguMDg3M0M4OS41ODEzIDU3LjkxNzggODkuNjE5IDU3Ljc1MTQgODkuNjE5IDU3LjU4NzlDODkuNjE5IDU3LjU2IDg5LjYxNzkgNTcuNTMyMSA4OS42MTU3IDU3LjUwNDRDODkuNjAwNiA1Ny4zMTQyIDg5LjUzMzkgNTcuMTI4IDg5LjQxNTYgNTYuOTQ2Qzg5LjI5NzMgNTYuNzY0IDg5LjE1NDMgNTYuNjI3NCA4OC45ODY2IDU2LjUzNjRMODguOTg2NSA1Ni41MzY0UTg4LjczNSA1Ni4zOTk5IDg4LjQwOTQgNTYuMzk5OUw3Ni4xNTkzIDU2LjM5OTlRNzUuNTA3MyA1Ni4zOTk5IDc0LjkwNzkgNTYuNTc3NlE3NC4zMDg0IDU2Ljc1NTIgNzMuNzYxNyA1Ny4xMTA1UTczLjIxNDkgNTcuNDY1OSA3Mi44MDkyIDU3Ljk0MTVDNzIuNTM4NiA1OC4yNTg1IDcyLjMxNTEgNTguNjE1NyA3Mi4xMzg1IDU5LjAxMjlMNjcuMjk0MyA2OS45MTI1QzY3LjIxOSA3MC4wODIgNjcuMTgxMyA3MC4yNDg0IDY3LjE4MTMgNzAuNDExOUM2Ny4xODEzIDcwLjQzOTggNjcuMTgyNCA3MC40Njc3IDY3LjE4NDYgNzAuNDk1NFE2Ny4yMDcyIDcwLjc4MDcgNjcuMzg0NiA3MS4wNTM4QzY3LjUwMjkgNzEuMjM1OCA2Ny42NDU5IDcxLjM3MjMgNjcuODEzNiA3MS40NjM0QzY3Ljk4MTMgNzEuNTU0NCA2OC4xNzM3IDcxLjU5OTkgNjguMzkwOCA3MS41OTk5TDgwLjY0MDkgNzEuNTk5OVoiIGZpbGw9InVybCgjcGFpbnRfbGluZWFyXzI1KSIgZmlsbC1vcGFjaXR5PSIwIiBmaWxsLXJ1bGU9ImV2ZW5vZGQiIC8+CgkJCTwvZz4KCQk8L2c+Cgk8L2c+Cjwvc3ZnPgo=";
		// src/client/Brand.tsx
		/** CANNBot brand mark: the packaged logo, scaled by the slot's requested size. */
		function Mark({ size }) {
			return /* @__PURE__ */ (0, react_jsx_runtime.jsx)("img", {
				src: logo_default,
				width: size,
				height: size,
				alt: "",
				"aria-hidden": "true",
				draggable: false,
				"data-cannbot-dsh-logo": ""
			});
		}
		function SidebarName() {
			return /* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
				className: "cannbot-dsh-name",
				children: "CANNBot"
			});
		}
		function Hero({ size }) {
			return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("span", {
				"data-cannbot-dsh-hero": "",
				children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)(Mark, { size }), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", { children: "现在，交给CANNBot" })]
			});
		}
		// src/workspace-mode-types.ts
		/** Shared wire contract. Unregistered workspaces and sessions belong to DeepSeek. */
		const CANNBOT_WORKSPACES_PATH = "api/cannbot-dsh/workspaces";
		/** Workspace ownership marker, never a workflow package or Skill. */
		const GENERAL_WORKSPACE = "general";
		// src/client/BoundWorkspaceWorkflow.tsx
		/** A CANNBot workspace chooses its plugin at creation, never in a blank session. */
		function BoundWorkspaceWorkflow({ modes, sessionId }) {
			const state = (0, react.useSyncExternalStore)(modes.subscribe, modes.getSnapshot);
			const workspace = sessionId ? state.workspaces.find((item) => item.sessionIds.includes(sessionId) || item.workspaceId === state.sessions.find((session) => session.sessionId === sessionId)?.workspaceId) : state.workspaces.find((item) => item.workspaceId === state.selectedWorkspaceId);
			if (!workspace) return null;
			if (workspace.pluginId === "general") return /* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
				className: "cannbot-dsh-session-workflow",
				children: "空白工作区"
			});
			return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("span", {
				className: "cannbot-dsh-session-workflow",
				title: `工作区工作流：${workspace.pluginId}`,
				children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", { children: "工作流" }), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("code", { children: workspace.pluginId })]
			});
		}
		// src/client/SessionWorkflow.tsx
		/** Read the committed selection for this header's Session, including after reload. */
		function SessionWorkflow({ sessionId, selection, t }) {
			const workflow = (0, react.useSyncExternalStore)(selection.subscribe, selection.getSnapshot).values[sessionId];
			if (!workflow) return null;
			return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("span", {
				className: "cannbot-dsh-session-workflow",
				title: `${t("currentWorkflow")}: ${workflow}`,
				children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", { children: t("currentWorkflow") }), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("code", { children: workflow })]
			});
		}
		// src/client/TaskList.tsx
		/** One view of the native todos projection, including a compact completion history. */
		function TaskList({ todos, t }) {
			const [expanded, setExpanded] = (0, react.useState)(false);
			const [showAll, setShowAll] = (0, react.useState)(false);
			if (!todos.length) return null;
			const done = todos.filter((task) => task.status === "completed");
			const open = todos.filter((task) => task.status !== "completed");
			const visible = [...(showAll ? done : done.slice(-2)).reverse(), ...open];
			return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("section", {
				className: "cannbot-task-list",
				"aria-label": t("tasksTitle"),
				children: [/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("button", {
					className: "cannbot-task-list-toggle",
					type: "button",
					"aria-expanded": expanded,
					onClick: () => setExpanded((value) => !value),
					children: [
						/* @__PURE__ */ (0, react_jsx_runtime.jsx)("strong", { children: t("tasksTitle") }),
						/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("span", {
							role: "status",
							children: [
								t("tasksDone"),
								" ",
								done.length,
								" / ",
								todos.length
							]
						}),
						/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
							className: "cannbot-task-list-chevron",
							"aria-hidden": true,
							children: expanded ? "⌄" : "⌃"
						})
					]
				}), expanded && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)(react_jsx_runtime.Fragment, { children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("ul", { children: visible.map((task) => /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("li", {
					"data-status": task.status,
					children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
						className: "cannbot-task-list-icon",
						"aria-hidden": true,
						children: task.status === "in_progress" ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.StateDot, { state: "ongoing" }) : task.status === "completed" ? "✓" : "○"
					}), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", { children: task.content })]
				}, task.content)) }), done.length > 2 && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
					type: "button",
					onClick: () => setShowAll((value) => !value),
					children: t(showAll ? "tasksRecent" : "tasksAll")
				})] })]
			});
		}
		function TaskDock({ useProjection, t }) {
			const todos = useProjection("todos");
			return /* @__PURE__ */ (0, react_jsx_runtime.jsx)(TaskList, {
				todos: todos ?? [],
				t
			});
		}
		// src/client/theme.ts
		/** Accent only: DSH owns surfaces, typography, radii and light/dark themes. */
		const cannTheme = Object.fromEntries([
			"--dsw-alias-brand-primary",
			"--dsw-alias-button-primary-hover",
			"--dsw-alias-button-info-fill",
			"--dsw-alias-button-info-hover",
			"--dsw-alias-state-business-primary",
			"--dsw-alias-link",
			"--dsw-focus-ring-color"
		].map((name) => [name, {
			light: "#C7000B",
			dark: "#C7000B"
		}]));
		// \0dsh-inline-css:/home/t00607008/cannbot/dsh/src/client/interface.css.mjs
		var interface_css_default = "span:has(>[data-slot=\"conversation.hero.brand.mark\"]>[data-cannbot-dsh-hero]){width:auto;min-width:0;height:auto}span:has(>[data-slot=\"conversation.hero.brand.mark\"]>[data-cannbot-dsh-hero])+span{display:none}[data-cannbot-dsh-hero]{color:var(--dsw-alias-label-primary);justify-content:center;align-items:center;gap:10px;font-size:26px;font-weight:500;line-height:32px;display:inline-flex}[data-cannbot-dsh-hero] svg{flex-shrink:0}.cannbot-dsh-name{letter-spacing:-.3px;font-weight:650}";
		// \0dsh-global-css:/home/t00607008/cannbot/dsh/src/client/controls.css.mjs
		const css$5 = ".cannbot-dsh-workflow{flex-direction:column;align-items:flex-start;gap:4px;min-width:120px;max-width:280px;display:inline-flex;position:relative}.cannbot-dsh-workflow-anchor{flex:none;min-width:120px;max-width:100%}.cannbot-dsh-workflow-trigger{border-radius:var(--dsw-radius-sm);min-width:0;max-width:100%;min-height:28px;color:var(--dsw-alias-label-primary);white-space:nowrap;cursor:pointer;background:0 0;border:0;align-items:center;gap:4px;padding:0 8px;font-family:inherit;font-size:13px;font-weight:500;line-height:20px;display:inline-flex}.cannbot-dsh-workflow-trigger svg{flex:none}.cannbot-dsh-workflow-trigger svg:last-child{color:var(--dsw-alias-label-caption)}.cannbot-dsh-workflow-trigger[aria-expanded=true]{background:var(--dsw-alias-interactive-bg-hover)}.cannbot-dsh-workflow-trigger:disabled{cursor:default;color:var(--dsw-alias-label-quaternary)}.cannbot-dsh-workflow-trigger:focus-visible{outline:2px solid var(--dsw-focus-ring-color);outline-offset:2px}.cannbot-dsh-workflow-label{text-overflow:ellipsis;white-space:nowrap;min-width:0;overflow:hidden}@media (hover:hover){.cannbot-dsh-workflow-trigger:not(:disabled):hover{background:var(--dsw-alias-interactive-bg-hover)}}.cannbot-dsh-workflow-option{white-space:normal;flex-direction:column;gap:4px;max-width:320px;padding:5px 0;display:flex}.cannbot-dsh-workflow-option small{color:var(--dsw-alias-label-secondary);font-size:12px;line-height:1.5}.cannbot-dsh-error{color:var(--dsw-alias-label-secondary);max-width:100%;font-size:12px;line-height:18px}.cannbot-dsh-error button{color:inherit;font:inherit;text-align:start;cursor:pointer;text-underline-offset:3px;background:0 0;border:0;padding:0 8px;text-decoration:underline}.cannbot-dsh-toggle{box-sizing:border-box;justify-content:space-between;align-items:center;gap:8px;width:100%;padding:8px;display:flex}.cannbot-dsh-toggle-name{min-width:0;color:var(--dsw-alias-label-primary);align-items:center;gap:8px;font-size:12px;line-height:20px;display:inline-flex}.cannbot-dsh-toggle-name svg{flex-shrink:0}.cannbot-dsh-toggle-compact{flex-direction:column;gap:6px}.cannbot-dsh-switch{background:var(--dsw-alias-interactive-bg-hover,#d7dadd);cursor:pointer;border:0;border-radius:99px;flex-shrink:0;width:36px;height:20px;padding:2px}.cannbot-dsh-switch[aria-checked=true]{background:#cf1740}.cannbot-dsh-switch>span{background:#fff;border-radius:50%;width:16px;height:16px;display:block;transform:translate(0)}.cannbot-dsh-switch[aria-checked=true]>span{transform:translate(16px)}.cannbot-dsh-switch:focus-visible{outline:2px solid var(--dsw-focus-ring-color,#cf1740);outline-offset:2px}.cannbot-dsh-update{border:1px solid var(--dsw-alias-border-l2,#e5e7eb);border-radius:var(--dsw-radius-md,12px);color:var(--dsw-alias-label-primary);padding:16px}.cannbot-dsh-update-heading{flex-wrap:wrap;align-items:baseline;gap:12px;margin-bottom:14px;display:flex}.cannbot-dsh-update h4{margin:0;font-size:14px;font-weight:600}.cannbot-dsh-update-heading>span,.cannbot-dsh-update p{color:var(--dsw-alias-label-secondary);font-size:12px;line-height:1.6}.cannbot-dsh-update-actions{flex-wrap:wrap;align-items:center;gap:12px;display:flex}.cannbot-dsh-update-button{box-sizing:border-box;background:var(--dsw-alias-brand-primary,#cf1740);color:#fff;min-height:32px;font:inherit;cursor:pointer;border:0;border-radius:8px;align-items:center;padding:5px 14px;font-size:13px;text-decoration:none;display:inline-flex}.cannbot-dsh-update-button:disabled{opacity:.6;cursor:default}.cannbot-dsh-update-button:focus-visible,.cannbot-dsh-update-recheck:focus-visible{outline:2px solid var(--dsw-focus-ring-color,#cf1740);outline-offset:3px}.cannbot-dsh-update-recheck{font:inherit;color:var(--dsw-alias-brand-primary,#cf1740);cursor:pointer;background:0 0;border:0;padding:4px;font-size:12px}.cannbot-dsh-update p{margin:10px 0 0}.cannbot-dsh-content{margin-top:16px}.cannbot-dsh-content details{margin-top:12px;font-size:12px}.cannbot-dsh-content summary{cursor:pointer}.cannbot-dsh-content pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:220px;font-size:11px;line-height:1.5;overflow:auto}.cannbot-dsh-workflow-package{border-bottom:1px solid var(--dsw-alias-border-l2,#eee);justify-content:space-between;align-items:center;gap:12px;padding:14px 0;display:flex}.cannbot-dsh-workflow-package>div:first-child{min-width:0}.cannbot-dsh-workflow-package strong{font-size:13px;font-weight:500}.cannbot-dsh-workflow-package small{color:var(--dsw-alias-label-secondary);overflow-wrap:anywhere;font-size:11px;line-height:1.6;display:block}.cannbot-dsh-workflow-package-actions{flex-wrap:wrap;flex-shrink:0;justify-content:flex-end;gap:8px;display:flex}@media (width<=480px){.cannbot-dsh-workflow-package{flex-direction:column;align-items:flex-start}}.cannbot-dsh-session-workflow{border-radius:var(--dsw-radius-sm,6px);background:var(--dsw-alias-interactive-bg-hover);min-width:0;max-width:min(320px,40vw);color:var(--dsw-alias-label-secondary);align-items:center;gap:6px;padding:3px 8px;font-size:12px;line-height:20px;display:inline-flex}.cannbot-dsh-session-workflow>span{flex-shrink:0}.cannbot-dsh-session-workflow code{text-overflow:ellipsis;white-space:nowrap;font-size:inherit;color:var(--dsw-alias-label-primary);overflow:hidden}.cannbot-task-list{width:calc(100% - 48px);max-width:var(--dsh-composer-card-max-width,760px);box-sizing:border-box;border-radius:var(--dsw-radius-lg,12px);background:var(--dsw-specific-menu);color:var(--dsw-alias-label-primary);margin:0 auto;padding:8px 12px;font-size:13px}.cannbot-task-list .cannbot-task-list-toggle{text-align:left;flex-wrap:wrap;align-items:center;gap:12px;width:100%;padding:0;display:flex}.cannbot-task-list-toggle span{color:var(--dsw-alias-label-secondary)}.cannbot-task-list-chevron{margin-left:auto}.cannbot-task-list button{color:inherit;font:inherit;cursor:pointer;background:0 0;border:0;margin-left:auto}.cannbot-task-list ul{max-height:220px;margin:8px 0 0;padding:0;list-style:none;overflow-y:auto}.cannbot-task-list li{overflow-wrap:anywhere;gap:8px;padding:3px 0;display:flex}.cannbot-task-list li[data-status=completed]{color:var(--dsw-alias-label-secondary)}.cannbot-task-list-icon{flex:none;justify-content:center;align-items:center;width:14px;display:inline-flex}";
		const tagId$5 = "@cannbot-plugin/cannbot-dsh/controls.css";
		if (typeof document !== "undefined" && document.querySelector("style[data-plugin-css=" + JSON.stringify(tagId$5) + "]") === null) {
			const tag = document.createElement("style");
			tag.dataset.plugin = "@cannbot-plugin/cannbot-dsh";
			tag.dataset.pluginCss = tagId$5;
			tag.textContent = css$5;
			document.head.appendChild(tag);
		}
		// src/client/slot-compat.ts
		/** Older DSH declares the injected parent modules before this plugin and uses direct register(). */
		function injectSlot(ctx, name, register) {
			return typeof ctx.slots.inject === "function" ? ctx.slots.inject(name, register) : register();
		}
		// src/client/workflow-selection.ts
		const NS = "cannbot-dsh";
		const valuesOf = (view) => Object.fromEntries((view?.value.selections ?? []).map((item) => [item.sessionId, item.workflow]));
		function createWorkflowSelection(blockSubmission = () => () => {}, prepare = async () => {}) {
			let snapshot = {
				ready: false,
				pending: false,
				error: false,
				values: {}
			};
			let transport;
			let generation = 0;
			let pendingRelease;
			let timer;
			let lastChoice;
			const listeners = /* @__PURE__ */ new Set();
			const publish = (next) => {
				snapshot = next;
				for (const listener of listeners) listener();
			};
			const read = async (current, own, attempt = 0) => {
				try {
					const view = await current.describe();
					if (own !== generation) return;
					const section = view.namespaces.find((item) => item.ns === NS);
					if (!section) throw new Error("Workflow settings are not active yet");
					publish({
						ready: true,
						pending: false,
						error: false,
						values: valuesOf(section)
					});
				} catch {
					if (own !== generation) return;
					if (attempt >= 9) publish({
						...snapshot,
						ready: false,
						pending: false,
						error: true,
						errorKind: "settings"
					});
					timer = setTimeout(() => {
						read(current, own, Math.min(attempt + 1, 9));
					}, attempt < 9 ? Math.min(250 * (attempt + 1), 1500) : 5e3);
				}
			};
			const api = {
				subscribe(listener) {
					listeners.add(listener);
					return () => {
						listeners.delete(listener);
					};
				},
				getSnapshot: () => snapshot,
				attach(next) {
					clearTimeout(timer);
					pendingRelease?.();
					pendingRelease = void 0;
					transport = next;
					const own = ++generation;
					publish({
						...snapshot,
						ready: false,
						pending: false,
						error: false,
						errorKind: void 0
					});
					read(next, own);
					return () => {
						if (own === generation) {
							generation++;
							clearTimeout(timer);
							transport = void 0;
							publish({
								...snapshot,
								ready: false
							});
						}
					};
				},
				async choose(sessionId, workflow, reason = "CANNBot DSH…") {
					if (!transport || !snapshot.ready || snapshot.pending) return;
					if (workflow !== "" && !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(workflow)) throw new Error("Unknown workflow");
					const current = transport, own = generation;
					lastChoice = {
						sessionId,
						workflow,
						reason
					};
					const unblock = blockSubmission(sessionId, reason);
					let released = false;
					const release = () => {
						if (!released) {
							released = true;
							unblock();
						}
					};
					pendingRelease = release;
					publish({
						...snapshot,
						pending: true,
						error: false,
						errorKind: void 0,
						errorMessage: void 0
					});
					let stage = "prepare";
					try {
						if (workflow) await prepare(sessionId, workflow);
						stage = "save";
						const view = (await current.describe()).namespaces.find((item) => item.ns === NS);
						if (!view) throw new Error("Workflow settings unavailable");
						const values = {
							...valuesOf(view),
							[sessionId]: workflow
						};
						const selections = Object.entries(values).filter(([, id]) => id !== "").map(([sessionId, workflow]) => ({
							sessionId,
							workflow
						}));
						const result = await current.update(NS, { selections }, view.revision);
						if (own === generation) publish({
							ready: true,
							pending: false,
							error: false,
							values: valuesOf(result)
						});
					} catch (error) {
						if (own === generation) publish({
							...snapshot,
							pending: false,
							error: true,
							errorKind: stage,
							errorMessage: error instanceof Error ? error.message : void 0
						});
					} finally {
						release();
						if (pendingRelease === release) pendingRelease = void 0;
					}
				},
				retry() {
					if (snapshot.errorKind === "settings" && transport) {
						clearTimeout(timer);
						publish({
							...snapshot,
							error: false,
							errorKind: void 0
						});
						read(transport, generation);
					} else if (lastChoice) api.choose(lastChoice.sessionId, lastChoice.workflow, lastChoice.reason);
				},
				dispose() {
					generation++;
					clearTimeout(timer);
					transport = void 0;
					pendingRelease?.();
					pendingRelease = void 0;
					listeners.clear();
				}
			};
			return api;
		}
		/** Both transports are official DSH settings APIs; no private editor access. */
		function connectWorkflowSelection(ctx, selection) {
			ctx.inject(["remote", "remote.settings"], (scoped) => {
				const settings = scoped.remote.settings;
				scoped.effect(() => selection.attach({
					describe: async () => unwrap$1(await settings.describe()),
					update: async (ns, patch, revision) => unwrap$1(await settings.update(ns, { selections: patch.selections.map(({ sessionId, workflow }) => ({
						sessionId,
						workflow
					})) }, revision))
				}));
			});
			ctx.inject(["connection"], (scoped) => {
				const api = scoped.connection.api;
				if (!api?.settings) return;
				scoped.effect(() => selection.attach({
					describe: async () => unwrap$1(await api.settings.describe({})),
					update: async (ns, patch, expectedRevision) => unwrap$1(await api.settings.update({
						ns,
						patch,
						expectedRevision
					}))
				}));
			});
		}
		function unwrap$1(response) {
			const result = response.result ?? response;
			if (!result.ok) throw new Error(result.error?.message ?? "Workflow settings failed");
			return result.value;
		}
		// src/client/plugin-update.ts
		const UPDATE_PACKAGES = ["cannbot-dsh", "@cannbot-plugin/cannbot-dsh"];
		/** Only stable npm releases of our two installation entries may be selected. */
		function newerVersion(candidate, current) {
			const next = /^(\d+)\.(\d+)\.(\d+)$/.exec(candidate);
			const old = /^(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$/.exec(current);
			if (!next || !old) return false;
			for (let index = 1; index < 4; index++) {
				const difference = Number(next[index]) - Number(old[index]);
				if (difference) return difference > 0;
			}
			return /^\d+\.\d+\.\d+-/.test(current);
		}
		async function latestRelease(name, signal) {
			if (!UPDATE_PACKAGES.includes(name)) throw new Error("Unsupported update target");
			const answers = await Promise.allSettled(["https://registry.npmjs.org/", "https://registry.npmmirror.com/"].map(async (registry) => {
				const response = await fetch(`${registry}${encodeURIComponent(name)}/latest`, {
					signal: AbortSignal.any([signal, AbortSignal.timeout(15e3)]),
					cache: "no-store"
				});
				if (!response.ok) throw new Error("Registry unavailable");
				const manifest = await response.json();
				if (manifest.name !== name || !manifest.version || !/^\d+\.\d+\.\d+$/.test(manifest.version) || !manifest.dsh?.bundle || !manifest.dist?.tarball) throw new Error("Invalid release");
				const url = new URL(manifest.dist.tarball);
				if (url.protocol !== "https:" || !["registry.npmjs.org", "registry.npmmirror.com"].includes(url.hostname)) throw new Error("Invalid download origin");
				return {
					name,
					version: manifest.version,
					tarball: url.href
				};
			}));
			signal.throwIfAborted();
			const latest = answers.flatMap((answer) => answer.status === "fulfilled" ? [answer.value] : []).reduce((best, release) => !best || newerVersion(release.version, best.version) ? release : best, void 0);
			if (!latest) throw new Error("No release available");
			return latest;
		}
		function createPluginUpdater(bridge, requestedName, lookup = latestRelease) {
			let state = { phase: "idle" };
			let disposed = false;
			let checking;
			const listeners = /* @__PURE__ */ new Set();
			const publish = (next) => {
				if (disposed) return;
				state = next;
				for (const listener of listeners) listener();
			};
			const failed = (result) => !["applied", "restart-required"].includes(result.application) || !!result.error;
			return {
				getSnapshot: () => state,
				subscribe(listener) {
					listeners.add(listener);
					return () => {
						listeners.delete(listener);
					};
				},
				async check() {
					if (disposed || state.phase === "checking" || state.phase === "updating") return;
					checking?.abort();
					const abort = new AbortController();
					checking = abort;
					publish({
						...state,
						phase: "checking"
					});
					try {
						const bundles = (await bridge.list()).filter((bundle) => bundle.installed && UPDATE_PACKAGES.includes(bundle.name));
						const bundle = bundles.find((bundle) => bundle.name === requestedName) ?? bundles[0];
						if (!bundle?.version) throw new Error("Installed entry unavailable");
						publish({
							...state,
							current: bundle.version,
							packageName: bundle.name
						});
						const release = await lookup(bundle.name, abort.signal);
						if (checking !== abort || disposed) return;
						publish({
							phase: newerVersion(release.version, bundle.version) ? "available" : "latest",
							current: bundle.version,
							release,
							packageName: bundle.name
						});
					} catch {
						if (!abort.signal.aborted) publish({
							...state,
							phase: "error"
						});
					}
				},
				async update() {
					if (disposed || state.phase !== "available" || !state.release || !state.packageName) return;
					const target = state.release, name = state.packageName;
					publish({
						...state,
						phase: "updating"
					});
					try {
						const result = (bridge.update ? await bridge.update(name, target.version) : { result: await bridge.install(`${name}@${target.version}`) }).result;
						if (failed(result)) {
							const code = result.error?.code;
							publish({
								...state,
								phase: code === "already-installed" || code === "stop-profile" ? "manual" : code === "incompatible-version" ? "incompatible" : "error"
							});
						} else publish({
							...state,
							phase: result.application === "restart-required" ? "restart" : "done",
							current: target.version
						});
					} catch {
						publish({
							...state,
							phase: "error"
						});
					}
				},
				dispose() {
					disposed = true;
					checking?.abort();
					listeners.clear();
				}
			};
		}
		// src/client/PluginUpdateCard.tsx
		function PluginUpdateCard({ updater, t }) {
			const state = (0, react.useSyncExternalStore)(updater.subscribe, updater.getSnapshot);
			(0, react.useEffect)(() => {
				updater.check();
			}, [updater]);
			const busy = state.phase === "checking" || state.phase === "updating";
			const canUpdate = state.phase === "available";
			const message = state.phase === "latest" ? t("updateLatest") : state.phase === "available" ? t("updateAvailable") : state.phase === "updating" ? t("updateRunning") : state.phase === "done" ? t("updateDone") : state.phase === "restart" ? t("updateRestart") : state.phase === "manual" ? t("updateManual") : state.phase === "incompatible" ? t("updateIncompatible") : state.phase === "error" ? t("updateFailed") : "";
			return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("section", {
				className: "cannbot-dsh-update",
				"aria-label": t("updateTitle"),
				children: [
					/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
						className: "cannbot-dsh-update-heading",
						children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("h4", { children: t("updateTitle") }), state.current && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("span", { children: [
							t("updateCurrent"),
							" ",
							state.current
						] })]
					}),
					/* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
						className: "cannbot-dsh-update-actions",
						children: state.phase === "manual" && state.release ? /* @__PURE__ */ (0, react_jsx_runtime.jsxs)(react_jsx_runtime.Fragment, { children: [/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("a", {
							className: "cannbot-dsh-update-button",
							href: state.release.tarball,
							download: true,
							rel: "noreferrer",
							children: [
								t("updateDownload"),
								" ",
								state.release.version
							]
						}), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
							type: "button",
							className: "cannbot-dsh-update-recheck",
							onClick: () => {
								updater.check();
							},
							children: t("updateCheck")
						})] }) : /* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
							type: "button",
							className: "cannbot-dsh-update-button",
							disabled: busy,
							onClick: () => {
								canUpdate ? updater.update() : updater.check();
							},
							children: state.phase === "checking" ? t("updateChecking") : state.phase === "updating" ? t("updateRunning") : canUpdate ? `${t("updateTo")} ${state.release?.version}` : t("updateCheck")
						})
					}),
					message && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", {
						role: state.phase === "error" ? "alert" : "status",
						"aria-live": "polite",
						children: message
					})
				]
			});
		}
		// src/client/host-update.ts
		/** This notice belongs to the in-flight update, so removing the plugin must not remove it. */
		async function updateOnHost(name, version) {
			const words = document.documentElement.lang.startsWith("en") ? en : zh;
			const notice = document.createElement("div");
			notice.setAttribute("role", "status");
			notice.setAttribute("aria-live", "polite");
			notice.dataset.cannbotUpdate = "progress";
			Object.assign(notice.style, {
				position: "fixed",
				bottom: "24px",
				right: "24px",
				zIndex: "2147483647",
				maxWidth: "min(380px, calc(100vw - 48px))",
				padding: "16px",
				borderRadius: "12px",
				background: "var(--dsw-alias-bg-base, white)",
				color: "var(--dsw-alias-label-primary, #222)",
				border: "1px solid var(--dsw-alias-border-l2, #ddd)",
				boxShadow: "0 8px 32px #0002",
				fontSize: "13px",
				lineHeight: "1.6"
			});
			const text = document.createElement("span");
			text.textContent = `${words.updateRunning} ${version} · ${words.updateBackground}`;
			notice.append(text);
			document.body.append(notice);
			try {
				const response = await fetch(new URL("api/cannbot-dsh/update", document.baseURI), {
					method: "POST",
					credentials: "same-origin",
					headers: { "content-type": "application/json" },
					body: JSON.stringify({
						name,
						version
					})
				});
				if (!response.ok) throw new Error("Host update unavailable");
				const answer = await response.json();
				if (!answer?.result || typeof answer.result.application !== "string") throw new Error("Invalid update result");
				const succeeded = (result) => !result.error && ["applied", "restart-required"].includes(result.application);
				text.textContent = succeeded(answer.result) ? `${answer.result.application === "restart-required" ? words.updateRestart : words.updateDone} (${version})` : answer.restore ? succeeded(answer.restore) ? words.updateRestored : words.updateRepair : words.updateFailed;
				return answer;
			} catch (error) {
				text.textContent = words.updateConnectionLost;
				throw error;
			} finally {
				const close = document.createElement("button");
				close.type = "button";
				close.textContent = "×";
				close.setAttribute("aria-label", words.updateDismiss);
				Object.assign(close.style, {
					marginLeft: "12px",
					border: "0",
					background: "transparent",
					color: "inherit",
					cursor: "pointer",
					fontSize: "18px"
				});
				close.addEventListener("click", () => notice.remove(), { once: true });
				notice.append(close);
			}
		}
		// src/workflows.ts
		const WORKFLOWS = [
			{
				id: "ops-direct-invoke-flash",
				label: "flash",
				description: "flashDescription"
			},
			{
				id: "ops-direct-invoke",
				label: "operator",
				description: "operatorDescription"
			},
			{
				id: "ops-registry-invoke",
				label: "registry",
				description: "registryDescription"
			}
		];
		// src/client/workflow-copy.ts
		/** Keep presentation consistent even when an older workflow package has a Chinese title. */
		function workflowCopy(workflow, t) {
			const known = WORKFLOWS.find((item) => item.id === workflow.id);
			return {
				name: workflow.id,
				description: known ? t(known.description) : workflow.description ?? (workflow.title === workflow.id ? "" : workflow.title)
			};
		}
		// src/client/ContentCard.tsx
		function ContentCard({ content, t }) {
			const { status } = (0, react.useSyncExternalStore)(content.subscribe, content.getSnapshot);
			const [failed, setFailed] = (0, react.useState)(false);
			const busy = status?.busy || status?.phase === "syncing" || status?.phase === "initializing";
			const act = (action) => {
				setFailed(false);
				action().catch(() => setFailed(true));
			};
			return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("section", {
				className: "cannbot-dsh-update cannbot-dsh-content",
				"aria-label": t("contentTitle"),
				children: [
					/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
						className: "cannbot-dsh-update-heading",
						children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("h4", { children: t("contentTitle") }), status?.catalogVersion && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("span", { children: [
							t("contentCatalog"),
							" ",
							status.catalogVersion
						] })]
					}),
					/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
						className: "cannbot-dsh-update-actions",
						children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
							type: "button",
							className: "cannbot-dsh-update-button",
							disabled: busy,
							onClick: () => act(content.sync),
							children: busy ? t("contentBusy") : t("contentSync")
						}), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
							type: "button",
							className: "cannbot-dsh-update-recheck",
							disabled: busy,
							onClick: () => act(content.check),
							children: t("contentCheck")
						})]
					}),
					/* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", {
						role: failed || status?.phase === "error" ? "alert" : "status",
						"aria-live": "polite",
						children: failed || status?.phase === "error" ? t("contentFailed") : status?.phase === "initializing" ? t("contentInitializing") : status?.phase === "syncing" ? t("contentDownloading") : status?.fallback ? t("contentFallback") : t("contentReady")
					}),
					status && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("p", { children: [
						status.plugins.length,
						" ",
						t("contentWorkflows")
					] }),
					/* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
						className: "cannbot-dsh-workflow-packages",
						children: status?.workflows?.map((row) => {
							const available = row.latest && (!row.version || newerVersion(row.latest, row.version));
							const copy = workflowCopy(row, t);
							return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
								className: "cannbot-dsh-workflow-package",
								children: [/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", { children: [
									/* @__PURE__ */ (0, react_jsx_runtime.jsx)("strong", {
										lang: "en",
										children: copy.name
									}),
									/* @__PURE__ */ (0, react_jsx_runtime.jsx)("small", { children: copy.description }),
									/* @__PURE__ */ (0, react_jsx_runtime.jsx)("small", {
										lang: "en",
										children: row.package
									}),
									/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("small", { children: [
										row.version ? `${t("contentVersion")} ${row.version}` : t("contentNotInstalled"),
										available && ` · ${t("contentLatest")} ${row.latest}`,
										row.pinned && ` · ${t("contentPinned")}`
									] }),
									row.error && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("small", {
										role: "alert",
										children: row.error
									})
								] }), /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
									className: "cannbot-dsh-workflow-package-actions",
									children: [available ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
										type: "button",
										className: "cannbot-dsh-update-recheck",
										disabled: busy,
										"aria-label": `${row.installed ? t("contentUpdate") : t("contentInstall")} ${copy.name}`,
										onClick: () => act(() => content.update(row.id, row.latest)),
										children: row.installed ? t("contentUpdate") : t("contentInstall")
									}) : /* @__PURE__ */ (0, react_jsx_runtime.jsx)("small", { children: row.installed ? row.latest ? t("contentUpToDate") : t("contentUnchecked") : t("contentUnavailable") }), row.previous && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("button", {
										type: "button",
										className: "cannbot-dsh-update-recheck",
										disabled: busy,
										"aria-label": `${t("contentRollback")} ${copy.name}`,
										onClick: () => act(() => content.rollback(row.id)),
										children: [
											t("contentRollback"),
											" ",
											row.previous
										]
									})]
								})]
							}, row.id);
						})
					}),
					(status?.log || status?.message) && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("details", { children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("summary", { children: t("contentLogs") }), /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("pre", { children: [
						status.message,
						"\n",
						status.log
					] })] })
				]
			});
		}
		// src/client/register-updates.ts
		/** Optional integration: old DSH versions without a Plugins page keep loading. */
		function registerPluginUpdates(ctx, content) {
			ctx.inject(["remote", "remote.pluginManager"], (scoped) => {
				const manager = scoped.remote.pluginManager;
				for (const name of UPDATE_PACKAGES) {
					const updater = createPluginUpdater({
						list: async () => unwrap(await manager.listBundles()),
						install: async (spec) => unwrap(await manager.installBundle(spec, { saveExact: true })),
						update: updateOnHost
					}, name);
					scoped.effect(() => () => updater.dispose());
					scoped.effect(() => injectSlot(scoped, "plugins.bundle.config", () => scoped.slots.register({
						name: "plugins.bundle.config",
						key: name,
						locale: NAMESPACE
					}, (props) => (0, react.createElement)(react.Fragment, null, (0, react.createElement)(PluginUpdateCard, {
						...props,
						updater
					}), content && (0, react.createElement)(ContentCard, {
						...props,
						content
					})))));
				}
			});
		}
		function unwrap(result) {
			if (!result.ok) throw result.error;
			return result.value;
		}
		// src/content-types.ts
		const CONTENT_PATH = "api/cannbot-dsh/content";
		// src/client/content-store.ts
		const initial = {
			workflows: WORKFLOWS.map(({ id }) => ({
				id,
				title: id
			})),
			status: void 0
		};
		function createContentStore() {
			let state = initial, closed = false, timer;
			const listeners = /* @__PURE__ */ new Set();
			const publish = (status) => {
				if (!closed) {
					state = {
						status,
						workflows: status.plugins
					};
					for (const listener of listeners) listener();
				}
			};
			const endpoint = () => new URL(CONTENT_PATH, document.baseURI);
			let requestSequence = 0;
			const pull = async () => {
				const sequence = ++requestSequence;
				try {
					const response = await fetch(endpoint(), {
						credentials: "same-origin",
						cache: "no-store",
						signal: AbortSignal.timeout(15e3)
					});
					if (response.ok) {
						const status = await response.json();
						if (sequence === requestSequence && Array.isArray(status.plugins) && status.plugins.every((item) => /^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(item.id) && typeof item.title === "string")) publish(status);
					}
				} catch {}
			};
			const post = async (body) => {
				++requestSequence;
				if (!(await fetch(endpoint(), {
					method: "POST",
					credentials: "same-origin",
					headers: { "content-type": "application/json" },
					body: JSON.stringify(body)
				})).ok) {
					await pull();
					throw new Error(state.status?.message || "工作流准备失败，请检查插件日志。");
				}
				await pull();
			};
			return {
				getSnapshot: () => state,
				subscribe(listener) {
					listeners.add(listener);
					return () => {
						listeners.delete(listener);
					};
				},
				start() {
					const tick = async () => {
						await pull();
						if (!closed) timer = setTimeout(() => {
							tick();
						}, 3e3);
					};
					tick();
					return () => {
						closed = true;
						clearTimeout(timer);
						listeners.clear();
					};
				},
				sync: () => post({ action: "sync" }),
				check: () => post({ action: "check" }),
				update: (id, version) => post({
					action: "update",
					id,
					version
				}),
				rollback: (id) => post({
					action: "rollback",
					id
				}),
				prepare: (sessionId, id) => post({
					action: "prepare",
					sessionId,
					id
				})
			};
		}
		// src/client/workbench-state.ts
		const preparationLabels = {
			idle: "",
			workspace: "正在准备工作区…",
			dependencies: "正在准备工作流依赖…",
			upload: "正在上传文件…",
			conversation: "正在进入对话…"
		};
		function createWorkbenchState() {
			let state = {
				prompt: "",
				workflow: "ops-direct-invoke-flash",
				workspaceId: "",
				files: [],
				detail: "ops-direct-invoke-flash",
				busy: false,
				error: "",
				stage: "idle"
			};
			const listeners = /* @__PURE__ */ new Set();
			const lifetime = new AbortController();
			return {
				signal: lifetime.signal,
				getSnapshot: () => state,
				subscribe(listener) {
					listeners.add(listener);
					return () => {
						listeners.delete(listener);
					};
				},
				set(patch) {
					if (lifetime.signal.aborted) return;
					state = {
						...state,
						...patch
					};
					for (const listener of listeners) listener();
				},
				dispose() {
					lifetime.abort();
					listeners.clear();
				}
			};
		}
		// src/client/workbench-data.ts
		/** Presentation copy only. Execution and initialization remain owned by the workflow packages. */
		const categories = ["全部", "Ascend C"];
		const guides = {
			"ops-direct-invoke-flash": {
				category: "Ascend C",
				icon: "flash",
				scenes: ["快速实现与验证算子原型", "从明确的功能需求开始开发"],
				inputs: ["必需：算子功能及输入输出规格", "可选：参考代码、测试数据及目标硬件"],
				outputs: ["Ascend C 算子代码", "在可用环境中执行的编译与精度验证结果"],
				example: "帮我快速生成并验证一个 Ascend C 的 MatMul 算子，输入使用 float16，请先确认形状约束。"
			},
			"ops-direct-invoke": {
				category: "Ascend C",
				icon: "code",
				scenes: ["开发新的 Ascend C 算子", "通过直调方式集成算子"],
				inputs: ["必需：算子功能、输入输出及数据类型", "可选：参考实现、目标硬件及性能要求"],
				outputs: ["算子实现与直调示例", "按实际环境生成的验证结果及运行说明"],
				example: "请开发一个 Ascend C 的 Add 算子，输入为两个 float16 张量，并通过直调方式验证结果。"
			},
			"ops-registry-invoke": {
				category: "Ascend C",
				icon: "document",
				scenes: ["开发需要注册到框架的算子", "通过 ACLNN / GEIR 接入算子"],
				inputs: ["必需：算子定义、输入输出及接入方式", "可选：现有工程、参考实现及目标环境"],
				outputs: ["注册算子相关代码及接入示例", "按实际环境完成的验证与使用说明"],
				example: "开发一个 Ascend C 的自定义算子，并通过 ACLNN 接入。请先检查当前工程及输入输出定义。"
			}
		};
		const guideFor = (id) => guides[id] ?? {
			category: "Ascend C",
			icon: "nodes",
			scenes: ["使用此工作流完成开发需求"],
			inputs: ["请描述目标，并提供相关工程或代码"],
			outputs: ["以工作流实际执行结果为准"],
			example: "请根据当前工程和我的需求开展工作，开始前先检查必要的输入。"
		};
		const cardOrder = Object.keys(guides);
		// src/client/workbench-workspace.ts
		/** Read only the public Session catalog and its main-view retention facts. */
		function inheritedWorkspaceId(workspaces, sessions) {
			const current = sessions.current ?? Object.entries(sessions.byId ?? {}).find(([, session]) => (session.retainedBy?.mainView ?? 0) > 0)?.[0];
			return current ? workspaces.find((workspace) => workspace.sessionIds?.includes(current))?.workspaceId : void 0;
		}
		// src/client/WorkbenchIcon.tsx
		function WorkbenchIcon({ name = "grid", size = 20 }) {
			const paths = {
				globe: "M12 2a10 10 0 1 0 0 20a10 10 0 1 0 0-20 M2 12h20 M12 2c-6 5-6 15 0 20 M12 2c6 5 6 15 0 20",
				back: "M20 12H4 M10 6l-6 6 6 6",
				grid: "M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z",
				code: "m8 6-6 6 6 6 M16 6l6 6-6 6 M14 3l-4 18",
				flash: "m13 2-9 12h7l-1 8 10-13h-7z",
				document: "M5 3h14v18H5z M8 8h8 M8 12h8 M8 16h5",
				layers: "m12 2 10 6-10 6L2 8z M2 12l10 6 10-6 M2 16l10 6 10-6",
				nodes: "M10 2h4v4h-4z M2 18h6v4H2z M16 18h6v4h-6z M12 6v6 M5 18v-6h14v6",
				arrows: "M3 7h17l-4-4 M20 7l-4 4 M21 17H4l4-4 M4 17l4 4",
				chart: "M3 13h4v8H3z M10 8h4v13h-4z M17 3h4v18h-4z",
				gear: "M9 3h6l1 3 3 1 2 5-2 5-3 1-1 3H9l-1-3-3-1-2-5 2-5 3-1z M9 12a3 3 0 1 0 6 0a3 3 0 1 0-6 0",
				folder: "M2 6h8l2 3h10v12H2z M2 6V3h7l3 3h10v3",
				search: "M16 16l6 6 M18 10a8 8 0 1 0-16 0a8 8 0 1 0 16 0",
				clip: "m8 13 7-7a3 3 0 0 1 4 4L9 20a5 5 0 0 1-7-7L13 2 M6 15l9-9"
			};
			return /* @__PURE__ */ (0, react_jsx_runtime.jsx)("svg", {
				width: size,
				height: size,
				viewBox: "0 0 24 24",
				fill: "none",
				stroke: "currentColor",
				strokeWidth: "1.6",
				strokeLinecap: "round",
				strokeLinejoin: "round",
				"aria-hidden": "true",
				children: /* @__PURE__ */ (0, react_jsx_runtime.jsx)("path", { d: paths[name] ?? paths.grid })
			});
		}
		// src/client/WorkspaceDirectory.tsx
		function pluginLabel(plugin) {
			const workflow = WORKFLOWS.find((item) => item.id === plugin.id);
			const description = plugin.description?.trim() || workflow && zh[workflow.description] || "按此工作流配置工作区。";
			return `${plugin.id}：${description}`;
		}
		/** Browse Host directories through the capability shared by Web and desktop pickers. */
		function WorkspaceDirectory({ ctx, initialPath, onSelect, onClose, plugins, create }) {
			const dialog = (0, react.useRef)(null);
			const lifetime = (0, react.useRef)(null);
			const request = (0, react.useRef)(null);
			const [listing, setListing] = (0, react.useState)();
			const [path, setPath] = (0, react.useState)(initialPath ?? "");
			const [loading, setLoading] = (0, react.useState)(true);
			const [saving, setSaving] = (0, react.useState)(false);
			const [error, setError] = (0, react.useState)("");
			const [pluginId, setPluginId] = (0, react.useState)("");
			const [folderName, setFolderName] = (0, react.useState)("");
			const [nativeOnly, setNativeOnly] = (0, react.useState)(false);
			const browse = async (target) => {
				request.current?.abort();
				const controller = new AbortController();
				request.current = controller;
				setLoading(true);
				setError("");
				setListing(void 0);
				try {
					let next = await ctx.uiWorkspace.listDirectory(target || void 0, controller.signal);
					const root = next.crumbs[0]?.path;
					if (!target && root && root !== next.path && !controller.signal.aborted) next = await ctx.uiWorkspace.listDirectory(root, controller.signal);
					if (!controller.signal.aborted) {
						setListing(next);
						setPath(next.path);
					}
				} catch (reason) {
					if (!controller.signal.aborted) {
						if (reason?.rpcError?.code === "directory-picker/unavailable" || reason instanceof Error && reason.message.includes("directory-picker/unavailable")) {
							setNativeOnly(true);
							setError("");
						} else setError(reason instanceof Error ? reason.message : "无法读取目录，请重试。");
					}
				} finally {
					if (!controller.signal.aborted) setLoading(false);
				}
			};
			(0, react.useEffect)(() => {
				lifetime.current = new AbortController();
				dialog.current?.showModal();
				browse(initialPath);
				return () => {
					lifetime.current?.abort();
					request.current?.abort();
				};
			}, []);
			const choose = async () => {
				const selectedPath = nativeOnly ? path.trim() : listing?.path;
				if (!selectedPath || loading || saving || create && !pluginId) return;
				setSaving(true);
				setError("");
				try {
					const existing = !create && ctx.workspaces.list.getSnapshot().items.find((item) => item.path === selectedPath);
					const selected = create ? await create(selectedPath, pluginId) : existing || await ctx.workspaces.create({ path: selectedPath });
					if (!lifetime.current?.signal.aborted) {
						onSelect(selected.workspaceId);
						onClose();
					}
				} catch (reason) {
					if (!lifetime.current?.signal.aborted) setError(reason instanceof Error ? reason.message : "无法选择工作区，请重试。");
				} finally {
					if (!lifetime.current?.signal.aborted) setSaving(false);
				}
			};
			const pickNative = async () => {
				if (saving) return;
				setSaving(true);
				setError("");
				try {
					const selected = await ctx.uiWorkspace.pickDirectory();
					if (selected && !lifetime.current?.signal.aborted) {
						setPath(selected);
						setNativeOnly(true);
					}
				} catch {
					if (!lifetime.current?.signal.aborted) setError("无法打开系统目录选择器，可在上方填写目录的绝对路径。");
				} finally {
					if (!lifetime.current?.signal.aborted) setSaving(false);
				}
			};
			const createFolder = async () => {
				if (!listing || saving || !folderName.trim()) return;
				setSaving(true);
				setError("");
				try {
					const created = await ctx.uiWorkspace.createDirectory(listing.path, folderName.trim());
					setFolderName("");
					await browse(created);
				} catch (reason) {
					if (!lifetime.current?.signal.aborted) setError(reason instanceof Error ? reason.message : "无法新建目录，请重试。");
				} finally {
					if (!lifetime.current?.signal.aborted) setSaving(false);
				}
			};
			return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("dialog", {
				ref: dialog,
				className: "cwb-directory",
				"aria-label": "选择工作区目录",
				onCancel: (event) => {
					event.preventDefault();
					if (!saving) onClose();
				},
				children: [
					/* @__PURE__ */ (0, react_jsx_runtime.jsx)("h2", { children: create ? "创建 CANNBot 工作区" : "选择工作区" }),
					/* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", { children: create ? "选择一个空目录。空白工作区不预装工作流，供手动配置昇腾项目；也可以选择一种工作流进行初始化。" : "选择 DSH 所在机器上的项目目录。" }),
					create && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("label", {
						className: "cwb-plugin-choice",
						children: ["工作区工作流", /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("select", {
							"aria-label": "工作区工作流",
							value: pluginId,
							required: true,
							disabled: saving,
							onChange: (event) => setPluginId(event.target.value),
							children: [
								/* @__PURE__ */ (0, react_jsx_runtime.jsx)("option", {
									value: "",
									disabled: true,
									children: "选择一个工作流"
								}),
								/* @__PURE__ */ (0, react_jsx_runtime.jsx)("option", {
									value: "general",
									children: "空白工作区：不安装工作流"
								}),
								plugins?.map((plugin) => /* @__PURE__ */ (0, react_jsx_runtime.jsx)("option", {
									value: plugin.id,
									children: pluginLabel(plugin)
								}, plugin.id))
							]
						})]
					}),
					/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("form", {
						onSubmit: (event) => {
							event.preventDefault();
							if (!saving && !nativeOnly) browse(path);
						},
						children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("input", {
							"aria-label": "目录路径",
							value: path,
							disabled: saving,
							onChange: (event) => setPath(event.target.value)
						}), nativeOnly ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
							className: "cwb-text-button",
							disabled: saving,
							type: "button",
							onClick: () => void pickNative(),
							children: "选择文件夹"
						}) : /* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
							className: "cwb-text-button",
							disabled: saving,
							type: "submit",
							children: "打开目录"
						})]
					}),
					nativeOnly && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("p", { children: ["使用系统文件夹选择器，或填写目录的绝对路径。", create && "创建时会检查目录为空。"] }),
					/* @__PURE__ */ (0, react_jsx_runtime.jsx)("nav", {
						"aria-label": "目录层级",
						children: listing?.crumbs.map((crumb) => /* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
							type: "button",
							className: "cwb-text-button",
							disabled: saving,
							onClick: () => void browse(crumb.path),
							children: crumb.name || crumb.path
						}, crumb.path))
					}),
					create && !nativeOnly && typeof ctx.uiWorkspace.createDirectory === "function" && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("form", {
						onSubmit: (event) => {
							event.preventDefault();
							createFolder();
						},
						children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("input", {
							"aria-label": "新文件夹名称",
							placeholder: "在当前目录下新建文件夹",
							value: folderName,
							onChange: (event) => setFolderName(event.target.value),
							disabled: saving || loading
						}), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
							type: "submit",
							className: "cwb-text-button",
							disabled: saving || loading || !folderName.trim(),
							children: "新建文件夹"
						})]
					}),
					loading ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", {
						role: "status",
						children: "正在读取目录…"
					}) : listing && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)(react_jsx_runtime.Fragment, { children: [
						/* @__PURE__ */ (0, react_jsx_runtime.jsx)("ul", {
							className: "cwb-directory-list",
							children: listing.entries.map((entry) => /* @__PURE__ */ (0, react_jsx_runtime.jsx)("li", { children: /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("button", {
								type: "button",
								disabled: saving,
								onClick: () => void browse(entry.path),
								children: [
									/* @__PURE__ */ (0, react_jsx_runtime.jsx)(WorkbenchIcon, {
										name: "folder",
										size: 16
									}),
									" ",
									entry.name
								]
							}) }, entry.path))
						}),
						!listing.entries.length && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", { children: create ? "此目录下没有子目录；创建时还会检查文件，确认目录为空。" : "此目录下没有子目录，可以直接选择当前目录。" }),
						listing.truncated && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", { children: "目录较多，仅显示部分结果；可输入完整路径打开。" })
					] }),
					error && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
						role: "alert",
						className: "cwb-error",
						children: error
					}),
					/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("footer", { children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
						type: "button",
						className: "cwb-text-button",
						disabled: saving,
						onClick: onClose,
						children: "取消"
					}), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
						type: "button",
						className: "cwb-primary",
						disabled: loading || saving || (nativeOnly ? !path.trim() : !listing || path !== listing.path) || !!create && !pluginId,
						onClick: () => void choose(),
						children: saving ? create ? pluginId === "general" ? "正在创建…" : "正在初始化…" : "正在选择…" : create ? !pluginId || pluginId === "general" ? "创建工作区" : "创建并初始化" : "选择此目录"
					})] })
				]
			});
		}
		// src/client/workbench-launch.ts
		/** Transfer to the resident DSH composer; its own submit policy remains authoritative. */
		async function launchWorkbench(ctx, selection, request, signal, onStage = () => {}) {
			if (!selection.getSnapshot().ready || selection.getSnapshot().pending) throw new Error("工作流设置尚未就绪，请稍后重试。");
			signal.throwIfAborted();
			const startingPanel = ctx.layout.panelInfo.getSnapshot().activePanelId;
			const sessions = ctx.sessions;
			onStage("workspace");
			const id = await sessions.create({ workspaceId: request.workspaceId });
			await request.recordSession?.(request.workspaceId, id);
			signal.throwIfAborted();
			const reference = sessions.retain(id, {
				source: "controllerOperation",
				signal
			});
			const conversation = ctx.conversation;
			let attachments = [];
			let transferred = false;
			try {
				const binding = await reference.ready;
				signal.throwIfAborted();
				if (request.workflow) onStage("dependencies");
				await selection.choose(id, request.workflow);
				signal.throwIfAborted();
				const saved = selection.getSnapshot();
				if (!saved.ready || saved.pending || saved.error || (saved.values[id] ?? "") !== request.workflow) throw new Error(saved.errorMessage || "工作流准备未完成，请在插件设置中查看日志后重试。");
				if (conversation.blocks.storeFor(id).getSnapshot()) throw new Error("当前对话暂时不能发送，请稍后重试。");
				const input = conversation.input.for(binding.ctx);
				if (conversation.input.requestDraftInitialization(binding, {
					prompt: request.prompt,
					whenDraftExists: "keep"
				}) !== "applied") throw new Error("新对话已存在草稿，已保留内容，请重试。");
				if (request.files.length) {
					onStage("upload");
					if (typeof conversation.createDrafts !== "function") throw new Error("此 DSH 版本请进入对话后添加文件。");
					attachments = conversation.createDrafts(id, request.files);
					await waitForUploads(conversation, attachments.filter((item) => item.kind === "file").map((item) => item.id), signal);
					if (!input.addAttachments(attachments.map((item) => item.id))) throw new Error("文件暂时无法加入对话，请重试。");
				}
				signal.throwIfAborted();
				if (ctx.layout.panelInfo.getSnapshot().activePanelId !== startingPanel) throw new Error("你已离开工作台，需求已保留；返回后可重新开始。");
				onStage("conversation");
				ctx.uiWorkspace.openSession(id);
				transferred = true;
				input.submit("queue", "click");
			} finally {
				if (!transferred) for (const attachment of attachments) conversation.releaseDraftAttachment(attachment.id);
				reference.release();
			}
		}
		function waitForUploads(conversation, ids, signal) {
			return new Promise((resolve, reject) => {
				let unsubscribe = () => {}, timer;
				const finish = (error) => {
					unsubscribe();
					clearTimeout(timer);
					signal.removeEventListener("abort", abort);
					error ? reject(error) : resolve();
				};
				const abort = () => finish(signal.reason ?? /* @__PURE__ */ new Error("操作已取消。"));
				const check = () => {
					const uploads = conversation.fileUploads.getSnapshot();
					const failed = ids.map((id) => uploads[id]).find((upload) => upload?.status === "error");
					if (failed?.status === "error") finish(/* @__PURE__ */ new Error(`文件上传失败：${failed.message}`));
					else if (ids.every((id) => uploads[id]?.status === "ready")) finish();
				};
				unsubscribe = conversation.fileUploads.subscribe(check);
				timer = setTimeout(() => finish(/* @__PURE__ */ new Error("文件上传超时，请检查连接后重试。")), 12e4);
				signal.addEventListener("abort", abort, { once: true });
				if (signal.aborted) abort();
				else check();
			});
		}
		// src/client/Workbench.tsx
		const HOME_PANEL = "cannbot-dsh-workbench";
		const LIBRARY_PANEL = "cannbot-dsh-workflows";
		const copy = (workflow) => workflowCopy(workflow, (key) => zh[key]);
		const noMode = {
			subscribe: (_) => () => {},
			getSnapshot: () => void 0
		};
		function Workbench({ ctx, content, selection, store, library = false, modes }) {
			const state = (0, react.useSyncExternalStore)(store.subscribe, store.getSnapshot);
			const mode = (0, react.useSyncExternalStore)(modes?.subscribe ?? noMode.subscribe, modes?.getSnapshot ?? noMode.getSnapshot);
			const { workflows } = (0, react.useSyncExternalStore)(content.subscribe, content.getSnapshot);
			const workspaceSource = ctx.workspaces.list;
			const workspaceBinding = (0, react.useMemo)(() => ({
				subscribe: (listener) => workspaceSource.subscribe(listener),
				getSnapshot: () => workspaceSource.getSnapshot()
			}), [workspaceSource]);
			const workspaceState = (0, react.useSyncExternalStore)(workspaceBinding.subscribe, workspaceBinding.getSnapshot);
			const sessionSource = ctx.sessions.list;
			const sessionBinding = (0, react.useMemo)(() => ({
				subscribe: (listener) => sessionSource.subscribe(listener),
				getSnapshot: () => sessionSource.getSnapshot()
			}), [sessionSource]);
			const sessionState = (0, react.useSyncExternalStore)(sessionBinding.subscribe, sessionBinding.getSnapshot);
			const saved = (0, react.useSyncExternalStore)(selection.subscribe, selection.getSnapshot);
			const [category, setCategory] = (0, react.useState)("全部");
			const [query, setQuery] = (0, react.useState)("");
			const [pickingWorkspace, setPickingWorkspace] = (0, react.useState)(false);
			const [workspaceMenuOpen, setWorkspaceMenuOpen] = (0, react.useState)(false);
			const input = (0, react.useRef)(null);
			const files = (0, react.useRef)(null);
			const ordered = [...workflows].sort((a, b) => (cardOrder.indexOf(a.id) < 0 ? 999 : cardOrder.indexOf(a.id)) - (cardOrder.indexOf(b.id) < 0 ? 999 : cardOrder.indexOf(b.id)));
			const fixedWorkspace = mode?.workspaces.find((item) => item.workspaceId === mode.selectedWorkspaceId);
			const visible = ordered.filter((workflow) => (!modes || !fixedWorkspace || workflow.id === fixedWorkspace.pluginId) && (category === "全部" || guideFor(workflow.id).category === category) && `${workflow.id} ${copy(workflow).description}`.toLowerCase().includes(query.toLowerCase().trim()));
			const inheritedId = modes ? "" : inheritedWorkspaceId(workspaceState.items, sessionState);
			const workspace = modes ? fixedWorkspace : workspaceState.items.find((item) => item.workspaceId === (state.workspaceId || inheritedId));
			const inherited = !state.workspaceId && !!workspace && workspace.workspaceId === inheritedId;
			const boundWorkflow = fixedWorkspace?.pluginId === "general" ? "" : fixedWorkspace?.pluginId ?? (modes ? "" : state.workflow);
			const selected = workflows.find((item) => item.id === boundWorkflow);
			const workspaceChoices = modes ? mode?.workspaces ?? [] : workspaceState.items;
			const workspaceReady = modes ? !!mode?.ready : workspaceState.phase === "ready";
			const detail = workflows.find((item) => item.id === state.detail) ?? workflows[0];
			const navigate = (panel) => ctx.layout.selectPanel(panel);
			const settings = () => ctx.get("pluginNavigation")?.openBundle(PACKAGE);
			const fail = (error) => store.set({ error: error instanceof Error ? error.message : "暂时无法完成，请重试。" });
			const start = async (event) => {
				event?.preventDefault();
				if (store.getSnapshot().busy) return;
				if (!workspace) {
					store.set({ error: "请先选择或添加工作区。" });
					return;
				}
				if (!state.prompt.trim() && state.files.length === 0) {
					input.current?.focus();
					return;
				}
				store.set({
					busy: true,
					error: "",
					stage: "workspace"
				});
				try {
					await launchWorkbench(ctx, selection, {
						workspaceId: workspace.workspaceId,
						workflow: fixedWorkspace?.pluginId === "general" ? "" : fixedWorkspace?.pluginId ?? state.workflow,
						prompt: state.prompt,
						files: state.files,
						...modes && { recordSession: modes.recordSession }
					}, store.signal, (stage) => store.set({ stage }));
					store.set({
						prompt: "",
						files: []
					});
				} catch (error) {
					fail(error);
				} finally {
					store.set({
						busy: false,
						stage: "idle"
					});
				}
			};
			const useWorkflow = (id, example) => {
				if (modes && id !== fixedWorkspace?.pluginId) {
					modes.setCreating(true);
					return;
				}
				store.set({
					workflow: id,
					...example && !state.prompt.trim() ? { prompt: example } : {},
					error: ""
				});
				navigate(HOME_PANEL);
			};
			const workspacePicker = /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.Menu, {
				open: workspaceMenuOpen,
				onClose: () => setWorkspaceMenuOpen(false),
				portal: true,
				listClassName: "cwb-workspace-menu",
				anchor: /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("button", {
					type: "button",
					className: "cwb-workspace-chip",
					"aria-label": "当前工作区",
					"aria-haspopup": "menu",
					"aria-expanded": workspaceMenuOpen,
					title: workspace?.path,
					disabled: state.busy || !workspaceReady,
					onClick: () => setWorkspaceMenuOpen((value) => !value),
					children: [
						/* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.IconFolderCloseRegular, { size: 16 }),
						/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", { children: workspace ? workspace.title === "default-workspace" ? "默认工作区" : workspace.title : "选择工作区" }),
						/* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.IconChevronDownOutlineRegular, { size: 12 })
					]
				}),
				selectedId: workspace?.workspaceId,
				items: [
					...workspaceChoices.map((item) => ({
						id: item.workspaceId,
						icon: /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.IconFolderCloseRegular, { size: 16 }),
						label: /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("span", {
							className: "cwb-workspace-menu-label",
							children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", { children: item.title === "default-workspace" ? "默认工作区" : item.title }), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("small", { children: item.path })]
						})
					})),
					{
						type: "separator",
						id: "workspace-create-separator"
					},
					{
						id: "workspace-create",
						icon: /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.IconProjectAddOutlineRegular, { size: 16 }),
						label: modes ? "创建工作区" : "选择其他目录…"
					}
				],
				onSelect: (id) => {
					setWorkspaceMenuOpen(false);
					if (state.busy) return;
					if (id === "workspace-create") {
						if (modes) modes.setCreating(true);
						else setPickingWorkspace(true);
						return;
					}
					if (!workspaceChoices.some((item) => item.workspaceId === id)) return;
					if (modes) modes.selectWorkspace(id);
					else store.set({
						workspaceId: id,
						error: ""
					});
				}
			});
			return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("main", {
				className: `cannbot-workbench ${library ? "cwb-library-page" : "cwb-home"}`,
				"aria-label": library ? "CANNBot 工作流" : "CANNBot工作台",
				children: [
					library && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("header", {
						className: "cwb-header",
						children: [workspacePicker, /* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
							className: "cwb-text-button",
							onClick: settings,
							children: "插件设置"
						})]
					}),
					pickingWorkspace && /* @__PURE__ */ (0, react_jsx_runtime.jsx)(WorkspaceDirectory, {
						ctx,
						initialPath: workspace?.path,
						onSelect: (workspaceId) => {
							if (!store.signal.aborted) store.set({
								workspaceId,
								error: ""
							});
						},
						onClose: () => setPickingWorkspace(false)
					}),
					/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
						className: "cwb-content",
						children: [
							library ? /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
								className: "cwb-heading",
								children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("h1", { children: "找到适合你的工作流" }), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", { children: "了解适用场景，准备好输入，再开始。" })]
							}) : /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
								className: "cwb-hero",
								children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)(Mark, { size: 34 }), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("h1", { children: "现在，交给CANNBot" })]
							}),
							!library && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)(react_jsx_runtime.Fragment, { children: [
								/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
									className: "cwb-composer-context",
									children: [
										workspacePicker,
										boundWorkflow && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
											className: "cwb-bound-workflow",
											title: "工作流在创建工作区时绑定",
											children: boundWorkflow
										}),
										inherited && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
											className: "cwb-inherited",
											children: "沿用当前对话"
										})
									]
								}),
								/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("form", {
									className: "cwb-composer",
									onSubmit: (event) => void start(event),
									onDragOver: (event) => event.preventDefault(),
									onDrop: (event) => {
										event.preventDefault();
										if (!state.busy) store.set({ files: [...state.files, ...Array.from(event.dataTransfer.files)] });
									},
									children: [
										/* @__PURE__ */ (0, react_jsx_runtime.jsx)("textarea", {
											ref: input,
											"aria-label": "开发需求",
											placeholder: selected ? guideFor(selected.id).example : "描述算子需求，或添加需要优化的代码。",
											value: state.prompt,
											disabled: state.busy,
											onChange: (event) => store.set({ prompt: event.target.value })
										}),
										state.files.length > 0 && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("ul", {
											className: "cwb-files",
											children: state.files.map((file, index) => /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("li", { children: [
												/* @__PURE__ */ (0, react_jsx_runtime.jsx)(WorkbenchIcon, {
													name: "document",
													size: 14
												}),
												/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", { children: file.name }),
												/* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
													type: "button",
													disabled: state.busy,
													"aria-label": `移除 ${file.name}`,
													onClick: () => store.set({ files: state.files.filter((_, i) => i !== index) }),
													children: "×"
												})
											] }, `${file.name}-${index}`))
										}),
										/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
											className: "cwb-composer-actions",
											children: [/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
												className: "cwb-composer-tools",
												children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("input", {
													type: "file",
													multiple: true,
													hidden: true,
													ref: files,
													onChange: (event) => {
														store.set({ files: [...state.files, ...Array.from(event.target.files ?? [])] });
														event.target.value = "";
													}
												}), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
													type: "button",
													className: "cwb-attach",
													"aria-label": "添加文件",
													title: "添加文件",
													disabled: state.busy,
													onClick: () => files.current?.click(),
													children: /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.IconPlusOutlineRegular, { size: 20 })
												})]
											}), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
												className: "cwb-send",
												type: "submit",
												"aria-label": state.busy ? "处理中…" : "开始",
												title: state.busy ? "处理中…" : "开始",
												disabled: state.busy || !saved.ready || saved.pending || !workspace || !state.prompt.trim() && !state.files.length,
												children: /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.IconSendOutlineRegular, { size: 18 })
											})]
										})
									]
								}),
								(state.busy || !saved.ready || !workspace) && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", {
									className: "cwb-hint",
									role: "status",
									"aria-live": "polite",
									children: state.busy ? preparationLabels[state.stage] : !saved.ready ? "正在连接工作流设置…" : "请先选择或添加工作区。"
								}),
								saved.errorKind === "settings" && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
									className: "cwb-text-button",
									onClick: () => selection.retry(),
									children: "重试连接工作流设置"
								})
							] }),
							state.error && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
								className: "cwb-error",
								role: "alert",
								children: [/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
									className: "cwb-error-heading",
									children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", { children: "暂时无法开始，需求和文件已保留。" }), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
										type: "button",
										className: "cwb-text-button",
										disabled: state.busy || !saved.ready || saved.pending,
										onClick: () => void start(),
										children: "重试"
									})]
								}), /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("details", { children: [
									/* @__PURE__ */ (0, react_jsx_runtime.jsx)("summary", { children: "查看原因" }),
									/* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", { children: state.error }),
									/* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
										className: "cwb-text-button",
										onClick: settings,
										children: "打开插件设置"
									})
								] })]
							}),
							mode?.navigationError && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", {
								role: "alert",
								className: "cwb-error",
								children: mode.navigationError
							}),
							workspaceState.state === "error" && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", {
								role: "alert",
								className: "cwb-error",
								children: "工作区加载失败，请检查 DSH 连接。"
							}),
							!library && boundWorkflow && !selected && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", {
								role: "alert",
								className: "cwb-error",
								children: "工作区绑定的工作流尚未就绪，请检查插件设置。"
							}),
							library && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("section", {
								className: "cwb-catalog",
								"aria-label": "工作流目录",
								children: [
									/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
										className: "cwb-catalog-heading",
										children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("h2", { children: "全部工作流" }), /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("label", {
											className: "cwb-search",
											children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)(WorkbenchIcon, {
												name: "search",
												size: 17
											}), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("input", {
												"aria-label": "搜索工作流",
												placeholder: "搜索工作流",
												value: query,
												onChange: (event) => setQuery(event.target.value)
											})]
										})]
									}),
									!fixedWorkspace && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
										className: "cwb-categories",
										role: "group",
										"aria-label": "工作流分类",
										children: categories.map((item) => /* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
											"aria-pressed": category === item,
											onClick: () => setCategory(item),
											children: item
										}, item))
									}),
									/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
										className: "cwb-library",
										children: [/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("nav", {
											"aria-label": "选择工作流详情",
											className: "cwb-library-list",
											children: [visible.map((workflow) => /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("button", {
												"aria-current": detail?.id === workflow.id ? "true" : void 0,
												onClick: () => store.set({ detail: workflow.id }),
												children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)(WorkbenchIcon, { name: guideFor(workflow.id).icon }), /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("span", { children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("strong", { children: workflow.id }), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("small", { children: copy(workflow).description })] })]
											}, workflow.id)), !visible.length && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", {
												className: "cwb-empty",
												children: "没有匹配的工作流"
											})]
										}), detail ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)(WorkflowDetail, {
											workflow: detail,
											content,
											onUse: () => useWorkflow(detail.id),
											onExample: () => useWorkflow(detail.id, guideFor(detail.id).example),
											onSettings: settings
										}, detail.id) : /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", {
											className: "cwb-empty",
											children: "工作流目录尚未准备完成，请到插件设置查看准备状态。"
										})]
									})
								]
							})
						]
					})
				]
			});
		}
		function WorkflowDetail({ workflow, content, onUse, onExample, onSettings }) {
			const { status } = (0, react.useSyncExternalStore)(content.subscribe, content.getSnapshot);
			const [error, setError] = (0, react.useState)(""), [pending, setPending] = (0, react.useState)(false);
			const guide = guideFor(workflow.id), row = status?.workflows?.find((item) => item.id === workflow.id);
			const busy = pending || status?.busy || status?.phase === "syncing" || status?.phase === "initializing";
			const act = async (action) => {
				setError("");
				setPending(true);
				try {
					await action();
				} catch {
					setError("操作未完成，请在插件设置中查看日志后重试。");
				} finally {
					setPending(false);
				}
			};
			return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("article", {
				className: "cwb-detail",
				children: [
					/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
						className: "cwb-detail-title",
						children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
							className: "cwb-card-icon",
							children: /* @__PURE__ */ (0, react_jsx_runtime.jsx)(WorkbenchIcon, {
								name: guide.icon,
								size: 25
							})
						}), /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("span", { children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("small", { children: guide.category }), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("h2", { children: workflow.id })] })]
					}),
					/* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", {
						className: "cwb-detail-summary",
						children: copy(workflow).description
					}),
					/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("button", {
						className: "cwb-primary",
						onClick: onUse,
						children: ["使用此工作流 ", /* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
							"aria-hidden": "true",
							children: "→"
						})]
					}),
					/* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
						className: "cwb-guide-sections",
						children: [
							["适合做什么", guide.scenes],
							["需要提供什么", guide.inputs],
							["可以获得什么", guide.outputs]
						].map(([title, entries]) => /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("section", { children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("h3", { children: title }), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("ul", { children: entries.map((line) => /* @__PURE__ */ (0, react_jsx_runtime.jsx)("li", { children: line }, line)) })] }, title))
					}),
					/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("section", {
						className: "cwb-example",
						children: [
							/* @__PURE__ */ (0, react_jsx_runtime.jsx)("h3", { children: "试试这样描述需求" }),
							/* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", { children: guide.example }),
							/* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
								className: "cwb-text-button",
								onClick: onExample,
								children: "使用此示例 ↗"
							}),
							/* @__PURE__ */ (0, react_jsx_runtime.jsx)("small", { children: "已有需求会保留，不会被示例覆盖。" })
						]
					}),
					/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("details", {
						className: "cwb-version",
						children: [
							/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("summary", { children: ["版本与更新 ", row?.version ? ` · ${row.version}` : ""] }),
							/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("p", { children: [row?.installed ? `已安装 ${row.version ?? ""}` : "安装状态尚未确认，请检查插件设置。", row?.latest && ` · 最新版本 ${row.latest}`] }),
							/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
								className: "cwb-version-actions",
								children: [
									/* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
										className: "cwb-text-button",
										disabled: busy,
										onClick: () => void act(content.check),
										children: "检查更新"
									}),
									row?.latest && (!row.version || newerVersion(row.latest, row.version)) && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
										className: "cwb-text-button",
										disabled: busy,
										onClick: () => void act(() => content.update(row.id, row.latest)),
										children: row.installed ? "更新工作流" : "安装工作流"
									}),
									row?.previous && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("button", {
										className: "cwb-text-button",
										disabled: busy,
										onClick: () => void act(() => content.rollback(row.id)),
										children: ["回退到 ", row.previous]
									}),
									/* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
										className: "cwb-text-button",
										onClick: onSettings,
										children: "准备日志与管理"
									})
								]
							}),
							/* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", { children: "初始化和验证以当前工作区的实际环境为准。" }),
							error && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", {
								role: "alert",
								children: error
							})
						]
					})
				]
			}, workflow.id);
		}
		// src/client/workspace-modes.ts
		const CANNBOT_HOME = "cannbot-dsh-workbench";
		/** The Host owns membership. This controller only owns navigation and unsubmitted drafts. */
		function createWorkspaceModes(ctx) {
			const sessions = ctx.sessions;
			const params = new URLSearchParams(typeof location === "undefined" ? "" : location.hash.replace(/^#/, ""));
			const embedded = params.get("cannEmbed") === "1";
			const createRequested = embedded && params.get("cannCreateWorkspace") === "1";
			if (createRequested) {
				const address = new URL(location.href), fragment = new URLSearchParams(address.hash.slice(1));
				fragment.delete("cannCreateWorkspace");
				address.hash = fragment.toString();
				history.replaceState(history.state, "", address);
			}
			const key = "cannbot.ui.modes.v1";
			let preference = {};
			if (!embedded) try {
				const saved = JSON.parse(localStorage.getItem(key) || "{}");
				if (saved && typeof saved === "object") {
					const value = saved;
					preference = {
						...value.mode === "cannbot" || value.mode === "deepseek" ? { mode: value.mode } : {},
						...typeof value.workspace === "string" ? { workspace: value.workspace } : {}
					};
				}
			} catch {}
			let state = {
				mode: !embedded && preference.mode === "deepseek" ? "deepseek" : "cannbot",
				workspaces: [],
				sessions: [],
				ready: false,
				error: "",
				navigationError: "",
				creating: false,
				selectedWorkspaceId: preference.workspace || "",
				serverId: "",
				list: "projects",
				activeSessionId: "",
				restoringSession: embedded && !createRequested && !!(params.get("cannSession") || params.get("cannWorkspace"))
			};
			const listeners = /* @__PURE__ */ new Set(), drafts = /* @__PURE__ */ new Map();
			const workbench = createWorkbenchState();
			workbench.set({ workflow: "" });
			const pages = {
				deepseek: { panel: null },
				cannbot: { panel: CANNBOT_HOME }
			};
			const lifetime = new AbortController();
			let timer, pulling = false, started = false, switching = false, membershipRevision = 0;
			let activePull;
			let restoringEmbed = embedded, targetSyncDepth = 0;
			const publish = (patch) => {
				if (lifetime.signal.aborted) return;
				state = {
					...state,
					...patch
				};
				for (const listener of listeners) listener();
			};
			const persist = () => {
				if (!embedded) try {
					localStorage.setItem(key, JSON.stringify({
						mode: state.mode,
						workspace: state.selectedWorkspaceId
					}));
				} catch {}
			};
			const syncEmbeddedTarget = (workspaceId, sessionId) => {
				if (!embedded || restoringEmbed || targetSyncDepth > 0 || !state.ready || lifetime.signal.aborted) return;
				const sessionWorkspace = sessionId && (state.workspaces.find((item) => item.sessionIds.includes(sessionId)) || state.workspaces.find((item) => item.workspaceId === state.sessions.find((row) => row.sessionId === sessionId)?.workspaceId));
				const orphan = sessionId && state.sessions.find((row) => row.sessionId === sessionId && row.ungrouped);
				if (sessionId && !sessionWorkspace && !orphan) return;
				const ownerId = (sessionWorkspace || state.workspaces.find((item) => item.workspaceId === workspaceId))?.workspaceId || (orphan ? orphan.workspaceId : "");
				const address = new URL(location.href), fragment = new URLSearchParams(address.hash.slice(1));
				fragment.set("cannEmbed", "1");
				fragment.set("cannMode", "cannbot");
				if (ownerId) fragment.set("cannWorkspace", ownerId);
				else fragment.delete("cannWorkspace");
				if (sessionId) fragment.set("cannSession", sessionId);
				else fragment.delete("cannSession");
				address.hash = fragment.toString();
				if (address.href !== location.href) history.replaceState(history.state, "", address);
			};
			const endpoint = () => new URL(CANNBOT_WORKSPACES_PATH, document.baseURI);
			const request = async (body) => {
				const response = await fetch(endpoint(), {
					method: body ? "POST" : "GET",
					credentials: "same-origin",
					cache: "no-store",
					signal: lifetime.signal,
					...body && {
						headers: { "content-type": "application/json" },
						body: JSON.stringify(body)
					}
				});
				const value = await response.json();
				if (!response.ok) throw Object.assign(new Error({
					"directory-not-empty": "该目录不是空目录，请另选一个空目录。",
					"plugin-conflict": "此目录已绑定其他工作流，请另选一个空目录。",
					"invalid-directory": "请选择已有目录的绝对路径。",
					"invalid-plugin": "请选择一个已安装的工作流。",
					"directory-replaced": "该路径对应的目录已被替换，请另选一个空目录。",
					"host-not-ready": "工作区服务正在准备，请稍后重试。",
					"workspace-operation-failed": "工作区初始化未完成。请在插件页查看准备日志，再用同一目录和工作流重试。"
				}[value?.error] || (typeof value?.message === "string" ? value.message : "工作区操作失败，请重试。")), {
					code: typeof value?.error === "string" ? value.error : "",
					status: response.status,
					...Array.isArray(value?.activity) && { activity: value.activity }
				});
				return value;
			};
			const refresh = async () => {
				if (pulling || lifetime.signal.aborted) return;
				pulling = true;
				const revision = membershipRevision;
				activePull = (async () => {
					try {
						const value = await request();
						if (revision !== membershipRevision) return;
						if (!Array.isArray(value.workspaces) || !Array.isArray(value.sessions)) throw new Error("工作区服务返回了无效数据。");
						if (value.sessions.some((row) => row.archived && row.sessionId === pages.cannbot.session)) pages.cannbot = { panel: CANNBOT_HOME };
						publish({
							workspaces: value.workspaces,
							sessions: value.sessions,
							ready: true,
							error: ""
						});
					} catch (error) {
						if (!lifetime.signal.aborted && revision === membershipRevision) publish({ error: error instanceof Error ? error.message : "无法读取工作区，请重试。" });
					} finally {
						pulling = false;
					}
				})();
				await activePull;
			};
			const refreshAfterOperation = async () => {
				++membershipRevision;
				await activePull;
				await refresh();
				if (!lifetime.signal.aborted && state.error) throw Object.assign(/* @__PURE__ */ new Error("操作已完成，但列表刷新失败。请刷新列表查看结果。"), { committed: true });
			};
			const currentSession = () => {
				const snapshot = sessions.list.getSnapshot();
				return snapshot.current || Object.entries(snapshot.byId || {}).find(([, item]) => (item.retainedBy?.mainView || 0) > 0)?.[0] || "";
			};
			const selectPanel = (panel) => ctx.layout.selectPanel(panel);
			const capture = () => {
				if (switching) return;
				const panel = ctx.layout.panelInfo.getSnapshot().activePanelId || null;
				const session = currentSession();
				const belongs = state.workspaces.some((row) => row.sessionIds.includes(session)) || state.sessions.some((row) => row.sessionId === session);
				if (panel || session && (state.mode === "deepseek" || belongs)) pages[state.mode] = {
					panel,
					...session && { session }
				};
				publish({ activeSessionId: session });
				if (panel === "cannbot-dsh-workbench") syncEmbeddedTarget(state.selectedWorkspaceId);
				else if (!panel && belongs) syncEmbeddedTarget(void 0, session);
			};
			const selectWorkspace = (id) => {
				const previous = workbench.getSnapshot();
				drafts.set(previous.workspaceId, {
					prompt: previous.prompt,
					files: previous.files,
					detail: previous.detail
				});
				const workspace = state.workspaces.find((item) => item.workspaceId === id);
				workbench.set({
					prompt: "",
					files: [],
					...drafts.get(id),
					workspaceId: id,
					workflow: workspace?.pluginId || "",
					error: ""
				});
				publish({
					selectedWorkspaceId: id,
					serverId: "",
					navigationError: ""
				});
				persist();
				syncEmbeddedTarget(id);
			};
			const openSession = (id) => {
				const owned = state.workspaces.some((item) => item.sessionIds.includes(id)) || state.sessions.some((item) => item.sessionId === id);
				if (state.mode === "cannbot" && (!state.ready || !owned)) {
					publish({ error: state.ready ? "请先切换到该会话所属模式。" : "工作区正在加载，请稍后重试。" });
					return;
				}
				ctx.layout.beginNavigation();
				targetSyncDepth++;
				try {
					const owned = state.sessions.find((item) => item.sessionId === id);
					if (state.mode === "cannbot" && owned) selectWorkspace(owned.workspaceId);
					ctx.uiWorkspace.openSession(id);
					pages[state.mode] = {
						panel: null,
						session: id
					};
					publish({ activeSessionId: id });
				} finally {
					targetSyncDepth--;
				}
				syncEmbeddedTarget(void 0, id);
			};
			const waitForSessionCatalog = (id, signal) => new Promise((resolve, reject) => {
				let unsubscribe = () => {};
				const finish = (error) => {
					unsubscribe();
					signal.removeEventListener("abort", abort);
					error ? reject(error) : resolve();
				};
				const abort = () => finish(signal.reason ?? /* @__PURE__ */ new Error("cancelled"));
				const check = () => {
					const snapshot = sessions.list.getSnapshot();
					if (snapshot.phase !== "ready") return;
					finish(snapshot.byId[id] ? void 0 : /* @__PURE__ */ new Error("session unavailable"));
				};
				unsubscribe = sessions.list.subscribe(check);
				signal.addEventListener("abort", abort, { once: true });
				if (signal.aborted) abort();
				else check();
			});
			const openEmbeddedSession = async (id) => {
				const changedPage = new AbortController(), timeout = AbortSignal.timeout(2e4);
				const initialPanel = ctx.layout.panelInfo.getSnapshot().activePanelId;
				const stopPage = ctx.layout.panelInfo.subscribe(() => {
					if (ctx.layout.panelInfo.getSnapshot().activePanelId !== initialPanel) changedPage.abort();
				});
				let navigation;
				let reference;
				try {
					await waitForSessionCatalog(id, AbortSignal.any([
						lifetime.signal,
						changedPage.signal,
						timeout
					]));
					stopPage();
					navigation = ctx.layout.beginNavigation();
					const signal = AbortSignal.any([
						lifetime.signal,
						navigation,
						timeout
					]);
					reference = sessions.retain(id, {
						source: "controllerOperation",
						signal
					});
					await reference.ready;
					signal.throwIfAborted();
					openSession(id);
					return true;
				} catch {
					if (!lifetime.signal.aborted && !changedPage.signal.aborted && (!navigation?.aborted || timeout.aborted)) {
						const error = timeout.aborted ? "远端会话加载超时，请返回本地后重新打开。" : "无法读取远端会话，请返回本地后重新打开。";
						publish({ navigationError: error });
						selectPanel(CANNBOT_HOME);
					}
					return false;
				} finally {
					stopPage();
					reference?.release();
				}
			};
			const setMode = (mode) => {
				if (mode === state.mode) return;
				capture();
				switching = true;
				publish({
					mode,
					creating: false
				});
				persist();
				const page = pages[mode];
				const rememberedOwned = page.session && !state.sessions.some((row) => row.sessionId === page.session && row.archived) && (state.workspaces.some((row) => row.sessionIds.includes(page.session)) || state.sessions.some((row) => row.sessionId === page.session));
				try {
					if (page.panel) selectPanel(page.panel);
					else if (page.session && (mode === "deepseek" || state.ready && rememberedOwned)) ctx.uiWorkspace.openSession(page.session);
					else if (mode === "cannbot") selectPanel(CANNBOT_HOME);
					else {
						selectPanel(null);
						ctx.uiWorkspace.startSession();
					}
				} finally {
					switching = false;
					capture();
				}
			};
			const api = {
				embedded,
				workbench,
				getSnapshot: () => state,
				subscribe(listener) {
					listeners.add(listener);
					return () => {
						listeners.delete(listener);
					};
				},
				refresh,
				refreshAfterOperation,
				selectWorkspace,
				setMode,
				openSession,
				async operate(operation) {
					const result = await request(operation);
					await refreshAfterOperation();
					return result;
				},
				reportError(error) {
					publish({ error });
				},
				setList(list) {
					publish({ list });
				},
				selectServer(serverId) {
					publish({
						serverId,
						creating: false
					});
				},
				setCreating(creating, creationServerId = "") {
					if (creating && embedded) {
						const address = new URL(location.href), fragment = new URLSearchParams(address.hash.slice(1));
						fragment.set("cannNewFolder", crypto.randomUUID());
						address.hash = fragment.toString();
						history.replaceState(history.state, "", address);
						return;
					}
					publish({
						creating,
						creationServerId
					});
				},
				newSession(workspaceId) {
					if (state.mode === "cannbot") {
						ctx.layout.beginNavigation();
						if (workspaceId) selectWorkspace(workspaceId);
						pages.cannbot = { panel: CANNBOT_HOME };
						selectPanel(CANNBOT_HOME);
						syncEmbeddedTarget(state.selectedWorkspaceId);
					} else ctx.uiWorkspace.startSession(workspaceId);
				},
				enterCreatedWorkspace(workspace) {
					++membershipRevision;
					publish({
						workspaces: [...state.workspaces.filter((item) => item.workspaceId !== workspace.workspaceId), workspace],
						ready: true,
						creating: false,
						permissionWorkspaceId: workspace.pluginId === "general" ? void 0 : workspace.workspaceId
					});
					api.newSession(workspace.workspaceId);
					refreshAfterOperation().catch((error) => publish({ error: error.message }));
				},
				finishPermissionRequest() {
					publish({ permissionWorkspaceId: void 0 });
					if (embedded) {
						const address = new URL(location.href), fragment = new URLSearchParams(address.hash.slice(1));
						fragment.delete("cannRecommendPermissions");
						address.hash = fragment.toString();
						history.replaceState(history.state, "", address);
					}
				},
				returnLocal() {
					publish({
						mode: "cannbot",
						serverId: ""
					});
					selectPanel(CANNBOT_HOME);
					persist();
				},
				async create(path, pluginId) {
					const result = await request({
						action: "create",
						path,
						pluginId
					});
					++membershipRevision;
					publish({ workspaces: [...state.workspaces.filter((item) => item.workspaceId !== result.workspace.workspaceId), result.workspace] });
					await refresh();
					selectWorkspace(result.workspace.workspaceId);
					publish({ creating: false });
					selectPanel(CANNBOT_HOME);
					return result.workspace;
				},
				async recordSession(workspaceId, sessionId, options = {}) {
					const result = await request({
						action: "session",
						workspaceId,
						sessionId
					});
					++membershipRevision;
					publish({
						sessions: [...state.sessions.filter((item) => item.sessionId !== sessionId), result.session],
						workspaces: state.workspaces.map((item) => item.workspaceId === workspaceId ? {
							...item,
							sessionIds: [.../* @__PURE__ */ new Set([...item.sessionIds, sessionId])]
						} : item)
					});
					if (options.reveal !== false) syncEmbeddedTarget(workspaceId, sessionId);
					await refresh();
					if (options.reveal !== false) {
						pages.cannbot = {
							panel: null,
							session: sessionId
						};
						publish({ activeSessionId: sessionId });
					}
				},
				start() {
					if (started) return () => {};
					started = true;
					const tick = async () => {
						await refresh();
						if (!lifetime.signal.aborted) timer = setTimeout(() => {
							tick();
						}, 4e3);
					};
					const unlisten = sessions.list.subscribe(capture), unpanel = ctx.layout.panelInfo.subscribe(capture);
					capture();
					(async () => {
						await tick();
						if (lifetime.signal.aborted) return;
						if (embedded) {
							const workspace = params.get("cannWorkspace"), session = params.get("cannSession");
							const verifiedSession = !createRequested && session && state.sessions.some((item) => item.sessionId === session) ? session : void 0;
							try {
								if (session && !verifiedSession && !createRequested) {
									publish({ navigationError: "无法读取远端会话，请返回本地后重新打开。" });
									selectPanel(CANNBOT_HOME);
									return;
								}
								if (createRequested) {
									selectPanel(CANNBOT_HOME);
									publish({ creating: true });
								} else if (verifiedSession) {
									if (workspace && state.workspaces.some((item) => item.workspaceId === workspace)) selectWorkspace(workspace);
									if (!await openEmbeddedSession(verifiedSession)) return;
								} else {
									if (workspace && !state.workspaces.some((item) => item.workspaceId === workspace)) await refreshAfterOperation();
									if (workspace && !state.workspaces.some((item) => item.workspaceId === workspace)) {
										publish({ navigationError: "新工作区正在加载，请重新打开该工作区。" });
										selectPanel(CANNBOT_HOME);
										return;
									}
									if (workspace && params.get("cannRecommendPermissions") === "1" && state.workspaces.find((item) => item.workspaceId === workspace)?.pluginId !== "general") publish({ permissionWorkspaceId: workspace });
									api.newSession(workspace || void 0);
								}
							} finally {
								restoringEmbed = false;
								publish({ restoringSession: false });
							}
							syncEmbeddedTarget(state.selectedWorkspaceId, verifiedSession);
						} else if (state.mode === "cannbot") {
							if (state.selectedWorkspaceId) selectWorkspace(state.selectedWorkspaceId);
							selectPanel(CANNBOT_HOME);
						}
					})();
					return () => {
						unlisten();
						unpanel();
						api.dispose();
					};
				},
				dispose() {
					if (lifetime.signal.aborted) return;
					lifetime.abort();
					clearTimeout(timer);
					workbench.dispose();
					listeners.clear();
				}
			};
			return api;
		}
		// \0dsh-global-css:/home/t00607008/cannbot/dsh/src/client/native-workbench.css.mjs
		const css$4 = ".cannbot-native-home{background:var(--dsw-alias-bg-base);flex-direction:column;min-width:0;height:100%;min-height:0;display:flex;position:relative}.cannbot-native-notice{text-align:center;font:inherit;color:var(--dsw-alias-label-secondary);margin:0;position:absolute;bottom:16px;left:16px;right:16px}.cannbot-native-notice button{font:inherit;color:inherit;cursor:pointer;background:0 0;border:0;margin-left:8px}.cannbot-workspace-preparing{text-align:center;color:var(--dsw-alias-label-primary);margin:auto;padding:32px}.cannbot-workspace-preparing strong{font-size:16px;font-weight:500;display:block}.cannbot-workspace-preparing p{color:var(--dsw-alias-label-secondary);margin:12px 0 0;font-size:13px}.cannbot-preparing-spinner{box-sizing:border-box;border:2px solid var(--dsw-alias-border-l2);border-top-color:var(--dsw-alias-state-business-primary);border-radius:50%;width:24px;height:24px;margin:0 auto 20px;animation:1s linear infinite cannbot-preparing-spin;display:block}@keyframes cannbot-preparing-spin{to{transform:rotate(360deg)}}@media (prefers-reduced-motion:reduce){.cannbot-preparing-spinner{animation:none}}";
		const tagId$4 = "@cannbot-plugin/cannbot-dsh/native-workbench.css";
		if (typeof document !== "undefined" && document.querySelector("style[data-plugin-css=" + JSON.stringify(tagId$4) + "]") === null) {
			const tag = document.createElement("style");
			tag.dataset.plugin = "@cannbot-plugin/cannbot-dsh";
			tag.dataset.pluginCss = tagId$4;
			tag.textContent = css$4;
			document.head.appendChild(tag);
		}
		// src/client/NativeWorkbench.tsx
		/** An absent native composer is only the workspace-selection/loading surface.
		* A prepared blank opens the real resident DSH Conversation, including its header,
		* model, permission, attachment, draft and adaptive-width implementations. */
		function NativeWorkbench({ ctx, modes, preparation, SessionProvider, renderSlot }) {
			const state = (0, react.useSyncExternalStore)(modes.subscribe, modes.getSnapshot);
			const prepared = (0, react.useSyncExternalStore)(preparation.subscribe, preparation.getSnapshot);
			const panelSource = (0, react.useMemo)(() => ({
				subscribe: (listener) => ctx.layout.panelInfo.subscribe(listener),
				getSnapshot: () => ctx.layout.panelInfo.getSnapshot()
			}), [ctx]);
			const panel = (0, react.useSyncExternalStore)(panelSource.subscribe, panelSource.getSnapshot);
			const active = state.mode === "cannbot" && !state.serverId && panel.activePanelId === "cannbot-dsh-workbench";
			(0, react.useEffect)(() => {
				if (!active || !state.ready || !state.selectedWorkspaceId || state.restoringSession || state.navigationError) return;
				let current = true;
				preparation.selectWorkspace(state.selectedWorkspaceId).then(() => {
					const next = preparation.getSnapshot(), latest = modes.getSnapshot();
					if (current && next.sessionId && !next.busy && !next.error && latest.mode === "cannbot" && !latest.serverId && latest.selectedWorkspaceId === next.workspaceId && ctx.layout.panelInfo.getSnapshot().activePanelId === "cannbot-dsh-workbench") {
						if (latest.permissionWorkspaceId !== next.workspaceId) modes.openSession(next.sessionId);
					}
				});
				return () => {
					current = false;
				};
			}, [
				active,
				state.ready,
				state.selectedWorkspaceId,
				state.restoringSession,
				state.navigationError,
				preparation,
				modes,
				ctx
			]);
			if (!active) return null;
			const empty = () => renderSlot("cannbot.workbench.content", {});
			const selecting = !state.selectedWorkspaceId && state.ready && !state.restoringSession && !state.navigationError;
			const permissionReady = !!prepared.session && !!prepared.sessionId && !prepared.busy && !prepared.error && state.permissionWorkspaceId === prepared.workspaceId && state.selectedWorkspaceId === prepared.workspaceId;
			return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("main", {
				className: "cannbot-native-home",
				"aria-label": "CANNBot工作台",
				children: [
					selecting ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)(SessionProvider, {
						session: void 0,
						empty,
						children: empty()
					}) : !prepared.error && !state.navigationError && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("section", {
						className: "cannbot-workspace-preparing",
						role: "status",
						"aria-live": "polite",
						"aria-busy": !permissionReady,
						children: [
							!permissionReady && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
								className: "cannbot-preparing-spinner",
								"aria-hidden": "true"
							}),
							/* @__PURE__ */ (0, react_jsx_runtime.jsx)("strong", { children: permissionReady ? "工作区已准备就绪" : "正在准备工作区…" }),
							/* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", { children: permissionReady ? "完成权限选择后即可开始对话。" : "正在加载会话与工作流配置，完成后即可开始对话。" })
						]
					}),
					permissionReady && /* @__PURE__ */ (0, react_jsx_runtime.jsx)(WorkflowPermissionDialog, {
						grant: async () => {
							const result = await prepared.session.binding.session.command("/permission danger-full-access");
							if (!result.ok || !result.value.matched) throw new Error("权限设置未完成，请重试。");
						},
						complete: () => {
							modes.finishPermissionRequest();
							modes.openSession(prepared.sessionId);
						}
					}),
					(prepared.error || state.navigationError) && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("p", {
						className: "cannbot-native-notice",
						role: "alert",
						children: [prepared.error || state.navigationError, prepared.error && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
							type: "button",
							onClick: () => void preparation.retry().then(() => {
								const next = preparation.getSnapshot();
								if (next.sessionId && !next.error && modes.getSnapshot().mode === "cannbot" && !modes.getSnapshot().serverId && modes.getSnapshot().permissionWorkspaceId !== next.workspaceId && modes.getSnapshot().selectedWorkspaceId === next.workspaceId && ctx.layout.panelInfo.getSnapshot().activePanelId === "cannbot-dsh-workbench") modes.openSession(next.sessionId);
							}),
							children: "重试"
						})]
					})
				]
			});
		}
		function WorkflowPermissionDialog({ grant, complete }) {
			const dialog = (0, react.useRef)(null), alive = (0, react.useRef)(true), running = (0, react.useRef)(false);
			const [saving, setSaving] = (0, react.useState)(false), [error, setError] = (0, react.useState)("");
			(0, react.useEffect)(() => {
				alive.current = true;
				dialog.current?.showModal();
				return () => {
					alive.current = false;
				};
			}, []);
			const accept = async () => {
				if (running.current) return;
				running.current = true;
				setSaving(true);
				setError("");
				try {
					await grant();
					if (alive.current) complete();
				} catch {
					if (alive.current) setError("权限设置未完成，请重试，或保留当前权限继续。");
				} finally {
					running.current = false;
					if (alive.current) setSaving(false);
				}
			};
			return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("dialog", {
				ref: dialog,
				className: "cwb-directory cb-workflow-permission",
				"aria-label": "工作流权限",
				onCancel: (event) => {
					event.preventDefault();
					if (!saving) complete();
				},
				children: [
					/* @__PURE__ */ (0, react_jsx_runtime.jsx)("h2", { children: "工作流权限" }),
					/* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", { children: "对于工作流开发，建议授予完全权限，是否授予？" }),
					error && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", {
						role: "alert",
						className: "cwb-error",
						children: error
					}),
					/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("footer", { children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
						type: "button",
						className: "cwb-text-button",
						disabled: saving,
						onClick: complete,
						children: "暂不授予"
					}), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
						type: "button",
						className: "cwb-primary",
						disabled: saving,
						onClick: () => void accept(),
						children: saving ? "正在设置…" : "授予完全权限"
					})] })
				]
			});
		}
		/** The public embedded occurrence owns its own hero centering, with no private
		* main-root CSS dependency. It is inert until a CANNBot workspace is selected. */
		function NativeWorkbenchEmpty({ renderFactorySlot }) {
			return renderFactorySlot("conversation.content", {
				variant: "embedded",
				phase: "hero",
				hero: true
			});
		}
		/** Keep the native chip and menu placement; only constrain CANNBot membership and
		* route selection through the safe blank-session preparation path. */
		function NativeWorkspacePicker({ modes, open, anchorRef, selectedId, onClose }) {
			const state = (0, react.useSyncExternalStore)(modes.subscribe, modes.getSnapshot);
			return /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.Menu, {
				open,
				anchor: null,
				portal: true,
				minWidthFromAnchor: true,
				autoFocus: true,
				getAnchorRect: () => anchorRef?.current?.getBoundingClientRect() ?? null,
				selectedId: selectedId || state.selectedWorkspaceId,
				onClose,
				items: [
					...state.workspaces.map((workspace) => ({
						id: workspace.workspaceId,
						label: workspace.title === "default-workspace" ? "默认工作区" : workspace.title,
						icon: /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.IconFolderCloseRegular, { size: 16 }),
						disabled: !state.ready
					})),
					...state.workspaces.length ? [{
						type: "separator",
						id: "cann-workspace-divider"
					}] : [],
					{
						id: "cann-workspace-create",
						label: "创建工作区",
						icon: /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.IconProjectAddOutlineRegular, { size: 16 }),
						disabled: !state.ready
					}
				],
				onSelect: (id) => {
					onClose();
					if (id === "cann-workspace-create") modes.setCreating(true);
					else if (state.workspaces.some((workspace) => workspace.workspaceId === id)) modes.newSession(id);
				}
			});
		}
		// src/client/native-workbench-session.ts
		/** Retain each workspace's native draft; no composer submission is performed here. */
		function createNativeWorkbenchSession(ctx, selection, modes) {
			const sessions = ctx.sessions;
			const lifetime = new AbortController(), listeners = /* @__PURE__ */ new Set();
			const cache = /* @__PURE__ */ new Map(), pending = /* @__PURE__ */ new Map();
			let state = {
				workspaceId: "",
				busy: false,
				error: ""
			};
			let sequence = 0, workflowQueue = Promise.resolve();
			const publish = (next) => {
				if (!lifetime.signal.aborted) {
					state = next;
					for (const listener of listeners) listener();
				}
			};
			const currentWorkspace = (id) => modes.getSnapshot().workspaces.find((item) => item.workspaceId === id);
			const active = () => modes.getSnapshot().mode === "cannbot" && !modes.getSnapshot().serverId && ctx.layout.panelInfo.getSnapshot().activePanelId === "cannbot-dsh-workbench";
			const release = (id) => {
				const entry = cache.get(id);
				if (entry) {
					cache.delete(id);
					entry.reference.release();
				}
			};
			const transferSubmitted = () => {
				const catalog = sessions.list.getSnapshot();
				for (const entry of cache.values()) if (catalog.byId[entry.reference.sessionId]?.blank === true) entry.wasBlank = true;
				const entry = cache.get(state.workspaceId);
				if (!entry || !state.session || entry.sent || !entry.wasBlank || !active() || catalog.byId[entry.reference.sessionId]?.blank !== false) return;
				entry.sent = true;
				modes.openSession(entry.reference.sessionId);
				release(state.workspaceId);
				publish({
					workspaceId: state.workspaceId,
					busy: false,
					error: ""
				});
			};
			const stopSessions = sessions.list.subscribe(transferSubmitted);
			const stopModes = modes.subscribe(() => {
				if (!modes.getSnapshot().ready) return;
				for (const id of cache.keys()) if (!currentWorkspace(id)) {
					release(id);
					if (state.workspaceId === id) {
						++sequence;
						publish({
							workspaceId: id,
							busy: false,
							error: "工作区已移除，请重新选择。"
						});
					}
				}
			});
			async function prepare(workspaceId) {
				const existing = pending.get(workspaceId);
				if (existing) return existing;
				const task = (async () => {
					const workspace = currentWorkspace(workspaceId);
					if (!workspace || !modes.getSnapshot().ready) throw new Error("请先选择 CANNBot 工作区。");
					const signal = AbortSignal.any([lifetime.signal, AbortSignal.timeout(12e4)]);
					await waitFor(sessions.list, () => sessions.list.getSnapshot().phase === "ready", AbortSignal.any([signal, AbortSignal.timeout(2e4)]));
					const catalog = sessions.list.getSnapshot();
					const owned = /* @__PURE__ */ new Set([...workspace.sessionIds, ...modes.getSnapshot().sessions.filter((item) => item.workspaceId === workspaceId).map((item) => item.sessionId)]);
					const archived = new Set(ctx.workspaces.list.getSnapshot().archivedSessionIds);
					const reusable = Object.entries(catalog.byId).find(([id, summary]) => owned.has(id) && summary.blank === true && !archived.has(id))?.[0];
					const id = await settle(sessions.create({
						workspaceId,
						...reusable && { sessionId: reusable }
					}), signal);
					signal.throwIfAborted();
					await settle(modes.recordSession(workspaceId, id, { reveal: false }), signal);
					signal.throwIfAborted();
					const reference = sessions.retain(id, {
						source: "controllerOperation",
						signal: lifetime.signal
					});
					try {
						await settle(reference.ready, signal);
						const bind = workflowQueue.then(async () => {
							await waitFor(selection, () => {
								const saved = selection.getSnapshot();
								return saved.ready && !saved.pending;
							}, signal);
							signal.throwIfAborted();
							const workflow = workspace.pluginId === "general" ? "" : workspace.pluginId;
							await settle(selection.choose(id, workflow), signal);
							const saved = selection.getSnapshot();
							if (!saved.ready || saved.pending || saved.error || (saved.values[id] || "") !== workflow) throw new Error("工作流准备未完成，请重试。");
						});
						workflowQueue = bind.catch(() => {});
						await bind;
						signal.throwIfAborted();
						if (currentWorkspace(workspaceId)?.pluginId !== workspace.pluginId) throw new Error("工作区已变化，请重新选择。");
						const entry = {
							reference,
							pluginId: workspace.pluginId,
							wasBlank: sessions.list.getSnapshot().byId[id]?.blank === true,
							sent: false
						};
						cache.set(workspaceId, entry);
						return entry;
					} catch (error) {
						reference.release();
						throw error;
					}
				})();
				pending.set(workspaceId, task);
				try {
					return await task;
				} finally {
					if (pending.get(workspaceId) === task) pending.delete(workspaceId);
				}
			}
			const api = {
				getSnapshot: () => state,
				subscribe(listener) {
					listeners.add(listener);
					return () => {
						listeners.delete(listener);
					};
				},
				async selectWorkspace(workspaceId) {
					if (lifetime.signal.aborted || !active()) return;
					const own = ++sequence, workspace = currentWorkspace(workspaceId);
					const mode = modes.getSnapshot();
					if (mode.restoringSession || mode.navigationError) {
						publish({
							workspaceId,
							busy: !!mode.restoringSession,
							error: mode.navigationError
						});
						return;
					}
					if (!workspaceId) {
						publish({
							workspaceId: "",
							busy: false,
							error: ""
						});
						return;
					}
					if (!workspace || !modes.getSnapshot().ready) {
						publish({
							workspaceId,
							busy: false,
							error: "请先选择 CANNBot 工作区。"
						});
						return;
					}
					if (modes.getSnapshot().selectedWorkspaceId !== workspaceId) modes.selectWorkspace(workspaceId);
					let entry = cache.get(workspaceId);
					if (entry && (entry.sent || entry.pluginId !== workspace.pluginId || !sessions.list.getSnapshot().byId[entry.reference.sessionId] || sessions.list.getSnapshot().byId[entry.reference.sessionId]?.blank === false || ctx.workspaces.list.getSnapshot().archivedSessionIds.includes(entry.reference.sessionId))) {
						release(workspaceId);
						entry = void 0;
					}
					if (entry) {
						publish({
							workspaceId,
							session: entry.reference,
							sessionId: entry.reference.sessionId,
							busy: false,
							error: ""
						});
						return;
					}
					publish({
						workspaceId,
						busy: true,
						error: ""
					});
					try {
						entry = await prepare(workspaceId);
						if (own !== sequence || lifetime.signal.aborted) return;
						publish({
							workspaceId,
							session: entry.reference,
							sessionId: entry.reference.sessionId,
							busy: false,
							error: ""
						});
						transferSubmitted();
					} catch {
						if (own === sequence && !lifetime.signal.aborted) publish({
							workspaceId,
							busy: false,
							error: "工作区对话准备失败，请重试。"
						});
					}
				},
				retry() {
					return api.selectWorkspace(state.workspaceId);
				},
				dispose() {
					if (lifetime.signal.aborted) return;
					++sequence;
					lifetime.abort();
					stopSessions();
					stopModes();
					for (const id of cache.keys()) release(id);
					listeners.clear();
				}
			};
			return api;
		}
		function settle(task, signal) {
			return new Promise((resolve, reject) => {
				const abort = () => reject(signal.reason ?? /* @__PURE__ */ new Error("cancelled"));
				signal.addEventListener("abort", abort, { once: true });
				task.then((value) => {
					signal.removeEventListener("abort", abort);
					signal.aborted ? abort() : resolve(value);
				}, (error) => {
					signal.removeEventListener("abort", abort);
					reject(error);
				});
				if (signal.aborted) abort();
			});
		}
		function waitFor(source, ready, signal) {
			return new Promise((resolve, reject) => {
				let unsubscribe = () => {};
				const finish = (error) => {
					unsubscribe();
					signal.removeEventListener("abort", abort);
					error ? reject(error) : resolve();
				};
				const abort = () => finish(signal.reason ?? /* @__PURE__ */ new Error("cancelled"));
				const check = () => {
					if (ready()) finish();
				};
				unsubscribe = source.subscribe(check);
				signal.addEventListener("abort", abort, { once: true });
				if (signal.aborted) abort();
				else check();
			});
		}
		// \0dsh-global-css:/home/t00607008/cannbot/dsh/src/client/workbench.css.mjs
		const css$3 = ".cannbot-workbench{--cwb-ink:var(--dsw-alias-label-primary,#17181d);--cwb-muted:var(--dsw-alias-label-secondary,#677185);--cwb-surface:var(--dsw-alias-bg-layer-1,#fff);--cwb-border:var(--dsw-alias-border-l2,#e2e5eb);--cwb-soft:var(--dsw-alias-bg-layer-3,#f6f8fa);--cwb-accent:var(--dsw-alias-state-business-primary,#c7000b);--cwb-selected:var(--dsw-alias-bg-layer-3,#f6f8fa);color:var(--cwb-ink);background:var(--dsw-alias-bg-base,var(--cwb-surface));height:100%;font-family:inherit;font-size:14px;overflow:auto}.cannbot-workbench *,.cannbot-workbench :before,.cannbot-workbench :after{box-sizing:border-box}.cannbot-workbench button,.cannbot-workbench input,.cannbot-workbench select,.cannbot-workbench textarea{font:inherit}.cannbot-workbench button{cursor:pointer}.cannbot-workbench button:disabled{opacity:.5;cursor:default}.cannbot-workbench :is(button,input,select,textarea):focus-visible{outline:2px solid var(--cwb-accent);outline-offset:3px}.cwb-header{border-bottom:1px solid var(--cwb-border);flex-wrap:wrap;justify-content:space-between;align-items:center;gap:12px;min-height:62px;padding:12px 30px;display:flex}.cwb-workspace{flex-wrap:wrap;align-items:center;gap:12px;min-width:0;display:flex}.cwb-workspace-info{min-width:0}.cwb-workspace-choice{flex-wrap:wrap;align-items:center;gap:8px;display:flex}.cwb-inherited{color:var(--cwb-muted);background:var(--cwb-soft);border-radius:5px;padding:3px 7px;font-size:11px}.cwb-workspace-path{text-overflow:ellipsis;white-space:nowrap;max-width:min(52vw,560px);color:var(--cwb-muted);padding-left:6px;font-size:12px;line-height:1.5;display:block;overflow:hidden}.cwb-workspace select{background:var(--cwb-surface);max-width:300px;color:var(--cwb-ink);border:0;padding:6px}.cwb-content{max-width:1260px;margin:0 auto;padding:26px 32px 22px}.cwb-heading{margin-bottom:20px}.cwb-heading h1{letter-spacing:-.5px;margin:0 0 8px;font-size:28px;font-weight:650;line-height:1.3}.cwb-heading p{color:var(--cwb-muted);margin:0;font-size:15px;line-height:1.6}.cwb-text-button{color:var(--cwb-muted);text-align:start;background:0 0;border:0;align-items:center;gap:7px;padding:5px 2px;display:inline-flex}.cwb-text-button:hover:not(:disabled){color:var(--cwb-accent)}.cwb-home{justify-content:center;align-items:center;padding:24px;display:flex}.cwb-home .cwb-content{width:100%;max-width:var(--dsh-composer-card-max-width,720px);margin:auto;padding:0 0 32px}.cwb-hero{color:var(--cwb-ink);flex-wrap:wrap;justify-content:center;align-items:center;gap:12px 10px;margin-bottom:12px;font-size:26px;font-weight:500;line-height:32px;display:flex}.cwb-hero>img{flex:none}.cwb-hero h1{font:inherit;margin:0}.cwb-composer{--dsw-elevation-stroke-color:var(--cwb-border);border-radius:var(--dsw-radius-panel,16px);background:var(--dsw-specific-input-major,var(--cwb-surface));width:100%;box-shadow:var(--dsw-elevation-soft,0 0 0 1px var(--cwb-border), 0 2px 8px #00000008);border:0;flex-direction:column;gap:8px;padding-top:8px;display:flex}.cwb-composer-context{align-items:center;gap:2px;min-width:0;margin:4px 0 8px;padding:0 16px 0 12px;display:flex}.cwb-workspace-chip{border-radius:var(--dsw-radius-sm,4px);max-width:min(100%,360px);min-height:28px;color:var(--cwb-ink);background:0 0;border:0;align-items:center;gap:4px;padding:0 8px;line-height:20px;display:inline-flex;font-size:13px!important;font-weight:500!important}.cwb-workspace-chip:hover:not(:disabled),.cwb-attach:hover:not(:disabled){background:var(--dsw-alias-interactive-bg-hover,var(--cwb-soft))}.cwb-workspace-chip>svg{flex:none}.cwb-workspace-chip>span{text-overflow:ellipsis;white-space:nowrap;overflow:hidden}.cwb-bound-workflow{text-overflow:ellipsis;white-space:nowrap;min-width:0;color:var(--cwb-muted);padding:0 8px;font-size:12px;line-height:20px;overflow:hidden}.cwb-workspace-menu-label{flex-direction:column;min-width:0;max-width:min(420px,70vw);display:flex}.cwb-workspace-menu-label>span,.cwb-workspace-menu-label>small{text-overflow:ellipsis;white-space:nowrap;overflow:hidden}.cwb-workspace-menu-label>small{color:var(--dsw-alias-label-secondary,#677185);font-size:11px}.cwb-composer textarea{resize:vertical;width:100%;min-height:52px;max-height:340px;color:var(--cwb-ink);line-height:calc(24px + var(--dsh-content-font-delta,0px));font-size:var(--dsh-content-font-size,14px);background:0 0;border:0;outline:0;padding:0 20px;display:block}.cwb-composer textarea:focus-visible{outline:0}.cwb-composer textarea::placeholder{color:var(--cwb-muted)}.cwb-composer-actions,.cwb-composer-tools{flex-wrap:wrap;align-items:center;gap:16px;min-width:0;display:flex}.cwb-composer-actions{justify-content:space-between;padding:0 12px 10px}.cwb-attach{border-radius:var(--dsw-radius-sm,4px);width:28px;height:28px;color:var(--cwb-muted);background:0 0;border:0;place-items:center;padding:0;display:inline-grid}.cwb-send{background:var(--dsw-alias-button-info-fill,var(--cwb-accent));color:#fff;border:0;border-radius:999px;flex:none;place-items:center;width:34px;height:34px;padding:0;display:grid}.cwb-send:hover:not(:disabled){background:var(--dsw-alias-button-info-hover,var(--cwb-accent))}.cannbot-workbench .cwb-send:disabled{opacity:.4}.cwb-primary{color:#fff;white-space:nowrap;background:#c7000b;border:1px solid #c7000b;border-radius:9px;justify-content:center;align-items:center;gap:22px;min-height:42px;padding:10px 22px;font-weight:550;display:inline-flex}.cwb-primary:hover:not(:disabled){background:#c7000b}.cwb-selection{color:var(--cwb-accent);background:var(--cwb-selected);border-radius:7px;align-items:center;gap:8px;min-width:0;max-width:100%;padding:6px 9px;font-size:12px;display:inline-flex}.cwb-selection>span{overflow-wrap:anywhere}.cwb-selection button,.cwb-files button{color:inherit;background:0 0;border:0;padding:0 4px;font-size:18px}.cwb-files{flex-wrap:wrap;gap:8px;margin:0;padding:0 20px;list-style:none;display:flex}.cwb-files li{border:1px solid var(--cwb-border);border-radius:6px;align-items:center;gap:6px;max-width:250px;padding:3px 6px;display:inline-flex}.cwb-files li span{text-overflow:ellipsis;white-space:nowrap;overflow:hidden}.cwb-hint{color:var(--cwb-muted);margin:10px 0 0;font-size:12px;line-height:1.6}.cwb-error{border-left:3px solid var(--cwb-accent);background:var(--cwb-selected);color:var(--cwb-ink);padding:12px 14px;line-height:1.6}.cwb-error-heading{justify-content:space-between;align-items:center;gap:12px;display:flex}.cwb-error .cwb-text-button{color:var(--cwb-accent)}.cwb-error summary{cursor:pointer;color:var(--cwb-muted);font-size:12px}.cwb-error details p{white-space:pre-wrap;overflow-wrap:anywhere;margin:8px 0}.cwb-catalog-heading{flex-wrap:wrap;justify-content:space-between;align-items:center;gap:12px;margin:26px 0 6px;display:flex}.cwb-catalog-heading h2{margin:0;font-size:20px;font-weight:600}.cwb-search{border:1px solid var(--cwb-border);color:var(--cwb-muted);border-radius:8px;align-items:center;gap:9px;padding:8px 11px;display:flex}.cwb-search input{width:170px;color:var(--cwb-ink);background:0 0;border:0;outline:0;font-size:13px}.cwb-categories{border-bottom:1px solid var(--cwb-border);gap:22px;margin-bottom:18px;display:flex;overflow-x:auto}.cwb-categories button{color:var(--cwb-muted);white-space:nowrap;background:0 0;border:0;border-bottom:2px solid #0000;padding:12px 3px}.cwb-categories button[aria-pressed=true]{border-bottom-color:var(--cwb-accent);color:var(--cwb-accent);font-weight:550}.cwb-grid{grid-template-columns:repeat(3,minmax(0,1fr));align-items:start;gap:10px;display:grid}.cwb-card{text-align:start;border:1px solid var(--cwb-border);width:100%;min-height:96px;color:var(--cwb-ink);background:var(--cwb-surface);border-radius:9px;grid-template-columns:28px minmax(0,1fr) 18px;align-items:start;gap:10px;padding:14px;transition:border-color .15s,background .15s;display:grid}.cwb-card:hover:not(:disabled){border-color:var(--cwb-accent)}.cwb-card[aria-pressed=true]{border-color:var(--cwb-accent);background:var(--cwb-selected)}.cwb-card-icon{background:var(--cwb-selected);width:40px;height:40px;color:var(--cwb-accent);border-radius:9px;flex:none;justify-content:center;align-items:center;display:inline-flex}.cwb-card .cwb-card-icon{border-radius:6px;width:28px;height:28px}.cwb-card .cwb-card-icon svg{width:19px;height:19px}.cwb-card-copy{flex-direction:column;gap:5px;min-width:0;padding-top:3px;display:flex}.cwb-card-copy strong{overflow-wrap:anywhere;font-size:14px;font-weight:600;line-height:1.4}.cwb-card-copy>span{color:var(--cwb-muted);font-size:12px;line-height:1.55}.cwb-card-corner{width:18px;height:18px;color:var(--cwb-muted);background:0 0;border:0;justify-content:center;align-items:center;margin-top:3px;display:inline-flex}.cwb-card-corner svg{flex:none;display:block}.cwb-empty{color:var(--cwb-muted);padding:20px 0;line-height:1.7}.cwb-library{border:1px solid var(--cwb-border);border-radius:12px;grid-template-columns:minmax(220px,.85fr) minmax(0,2fr);display:grid;overflow:hidden}.cwb-library-list{background:var(--cwb-soft);border-right:1px solid var(--cwb-border);padding:10px}.cwb-library-list button{text-align:start;width:100%;color:var(--cwb-ink);background:0 0;border:1px solid #0000;border-radius:8px;gap:12px;padding:14px 12px;display:flex}.cwb-library-list button[aria-current=true]{border-color:var(--cwb-border);background:var(--cwb-surface)}.cwb-library-list button[aria-current=true]>svg{color:var(--cwb-accent)}.cwb-library-list button>svg{flex:none;margin-top:2px}.cwb-library-list button span{min-width:0}.cwb-library-list strong{overflow-wrap:anywhere;font-size:13px;font-weight:550;line-height:1.5;display:block}.cwb-library-list small{color:var(--cwb-muted);margin-top:5px;font-size:12px;line-height:1.6;display:block}.cwb-detail{min-width:0;padding:28px 30px}.cwb-detail-title{align-items:center;gap:14px;display:flex}.cwb-detail-title small{color:var(--cwb-muted);font-size:12px}.cwb-detail-title h2{overflow-wrap:anywhere;margin:5px 0 0;font-size:21px;line-height:1.4}.cwb-detail-summary{color:var(--cwb-muted);margin:17px 0 20px;line-height:1.7}.cwb-guide-sections{grid-template-columns:1fr;gap:18px;margin-top:28px;display:grid}.cwb-detail h3{margin:0 0 9px;font-size:14px;font-weight:600}.cwb-guide-sections ul{color:var(--cwb-muted);margin:0;padding-left:18px;font-size:13px;line-height:1.9}.cwb-example{border:1px solid var(--cwb-border);background:var(--cwb-soft);border-radius:9px;margin-top:24px;padding:18px}.cwb-example p{color:var(--cwb-muted);margin:8px 0;font-size:13px;line-height:1.8}.cwb-example .cwb-text-button{color:var(--cwb-accent)}.cwb-example small{color:var(--cwb-muted);margin-top:6px;font-size:11px;display:block}.cwb-version{border-top:1px solid var(--cwb-border);color:var(--cwb-muted);margin-top:24px;padding-top:18px;font-size:12px;line-height:1.8}.cwb-version summary{cursor:pointer}.cwb-version-actions{flex-wrap:wrap;gap:15px;display:flex}.cannbot-workbench{container:cwb/inline-size}@container cwb (width<=900px){.cwb-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@container cwb (width<=590px){.cwb-grid{grid-template-columns:1fr}}@media (width<=1120px){.cwb-content{padding:24px}.cwb-library{grid-template-columns:minmax(190px,.9fr) minmax(0,1.6fr)}.cwb-detail{padding:22px}}@media (width<=700px){.cwb-header{padding:12px 16px}.cwb-content{padding:22px 16px}.cwb-home{padding:16px}.cwb-heading h1{font-size:25px}.cwb-grid,.cwb-library{grid-template-columns:1fr}.cwb-library-list{border-right:0;border-bottom:1px solid var(--cwb-border);max-height:220px;overflow:auto}.cwb-workspace select{max-width:190px}.cwb-composer-tools{gap:8px}.cwb-primary{padding:9px 17px}.cwb-search,.cwb-search input{width:100%}}@media (prefers-reduced-motion:reduce){.cwb-card{transition:none}}.cwb-directory{border:1px solid var(--cwb-border);width:min(600px,100vw - 40px);max-height:80vh;color:var(--cwb-ink);background:var(--cwb-surface);border-radius:12px;padding:24px;overflow:auto}.cwb-directory::backdrop{background:#00000059}.cwb-directory h2{margin:0 0 12px;font-size:20px}.cwb-directory p{color:var(--cwb-muted);font-size:13px}.cwb-directory form{gap:8px;display:flex}.cwb-directory input{border:1px solid var(--cwb-border);background:var(--cwb-surface);min-width:0;color:inherit;border-radius:6px;flex:1;padding:8px}.cwb-directory nav{flex-wrap:wrap;gap:8px;margin:12px 0;display:flex}.cwb-directory-list{max-height:35vh;padding:0;list-style:none;overflow:auto}.cwb-directory-list button{text-align:start;width:100%;color:inherit;cursor:pointer;background:0 0;border:0;border-radius:6px;padding:10px}.cwb-directory-list button:hover{background:var(--cwb-soft)}.cwb-directory footer{justify-content:flex-end;gap:16px;margin-top:20px;display:flex}.cwb-directory{--cwb-ink:var(--dsw-alias-label-primary,CanvasText);--cwb-muted:var(--dsw-alias-label-secondary,#677185);--cwb-surface:var(--dsw-alias-bg-layer-1,Canvas);--cwb-border:var(--dsw-alias-border-l2,#d7d7d7);--cwb-soft:var(--dsw-alias-bg-layer-3,#f6f8fa);--cwb-accent:var(--dsw-alias-brand-primary,#c7000b);--cwb-selected:var(--dsw-alias-bg-layer-3,#f6f8fa);font-family:inherit;font-size:14px}.cwb-directory :is(button,input,select){font:inherit}.cwb-directory button{cursor:pointer}.cwb-directory button:disabled{opacity:.5;cursor:default}.cwb-directory :is(button,input,select):focus-visible{outline:2px solid var(--cwb-accent);outline-offset:2px}";
		const tagId$3 = "@cannbot-plugin/cannbot-dsh/workbench.css";
		if (typeof document !== "undefined" && document.querySelector("style[data-plugin-css=" + JSON.stringify(tagId$3) + "]") === null) {
			const tag = document.createElement("style");
			tag.dataset.plugin = "@cannbot-plugin/cannbot-dsh";
			tag.dataset.pluginCss = tagId$3;
			tag.textContent = css$3;
			document.head.appendChild(tag);
		}
		// src/client/register-workbench.ts
		/** Optional public-slot integration: older DSH keeps its existing branded conversation. */
		function registerWorkbench(ctx, selection, content, modes) {
			const fiber = ctx.inject([
				"layout",
				"uiWorkspace",
				"workspaces"
			], (scoped) => {
				if (typeof scoped.uiWorkspace.openSession !== "function" || typeof scoped.sessions.retain !== "function" || typeof scoped.conversation.input.requestDraftInitialization !== "function") return;
				scoped.effect(() => {
					const store = modes?.workbench ?? createWorkbenchState();
					const releases = [];
					const preparation = modes ? createNativeWorkbenchSession(scoped, selection, modes) : void 0;
					if (preparation) releases.push(() => preparation.dispose());
					for (const [id, library] of [[HOME_PANEL, false], [LIBRARY_PANEL, true]]) if (!library && modes && preparation) {
						releases.push(injectSlot(scoped, "main", () => scoped.slots.register({
							name: "main",
							key: id,
							children: { "cannbot.workbench.content": {
								kind: "single",
								scope: "session-maybe"
							} }
						}, (props) => (0, react.createElement)(NativeWorkbench, {
							...props,
							ctx: scoped,
							modes,
							preparation
						}))));
						releases.push(injectSlot(scoped, "cannbot.workbench.content", () => scoped.slots.register({ name: "cannbot.workbench.content" }, NativeWorkbenchEmpty)));
					} else releases.push(injectSlot(scoped, "main", () => scoped.slots.register({
						name: "main",
						key: id
					}, () => (0, react.createElement)(Workbench, {
						ctx: scoped,
						selection,
						content,
						store,
						library,
						modes
					}))));
					return () => {
						if (!modes) store.dispose();
						if (["cannbot-dsh-workbench", "cannbot-dsh-workflows"].includes(scoped.layout.panelInfo.getSnapshot().activePanelId)) scoped.layout.selectPanel(null);
						for (const release of releases.reverse()) release();
					};
				});
			});
			return () => {
				if (typeof fiber?.dispose === "function") fiber.dispose();
			};
		}
		// src/client/CreateWorkspace.tsx
		function CreateWorkspace({ modes, remote, workflows, close }) {
			const servers = (0, react.useSyncExternalStore)(remote.subscribe, remote.getSnapshot);
			const dialog = (0, react.useRef)(null), reading = (0, react.useRef)(null), alive = (0, react.useRef)(true);
			const parentPicker = (0, react.useRef)(null), typing = (0, react.useRef)(void 0);
			const [serverId, setServerId] = (0, react.useState)(modes.getSnapshot().creationServerId || "");
			const [name, setName] = (0, react.useState)(""), [parent, setParent] = (0, react.useState)(""), [pluginId, setPluginId] = (0, react.useState)("");
			const [listing, setListing] = (0, react.useState)(), [browseOpen, setBrowseOpen] = (0, react.useState)(false);
			const [loading, setLoading] = (0, react.useState)(true), [saving, setSaving] = (0, react.useState)(false), [error, setError] = (0, react.useState)("");
			const [connection, setConnection] = (0, react.useState)(null);
			const workflowNotice = !!pluginId && pluginId !== "general";
			const submission = (0, react.useRef)({
				key: "",
				requestId: ""
			});
			const selectedServer = servers.servers.find((server) => server.id === serverId);
			const connected = serverId !== null && (!serverId || selectedServer?.connected === true);
			const remoteLocation = !!serverId || modes.embedded;
			const send = async (body, signal) => {
				const url = new URL(serverId ? "api/cannbot-remote/tree?id=" + encodeURIComponent(serverId) : CANNBOT_WORKSPACES_PATH, document.baseURI);
				const response = await fetch(url, {
					method: "POST",
					credentials: "same-origin",
					cache: "no-store",
					signal,
					headers: {
						"content-type": "application/json",
						...modes.embedded ? { "x-cannbot-remote-workspace": "1" } : {}
					},
					body: JSON.stringify(body)
				});
				const value = await response.json();
				if (!response.ok) throw new Error(value.message || "操作未完成，请检查目录或服务器连接后重试。");
				return value;
			};
			const browse = async (path = "", complete = false) => {
				clearTimeout(typing.current);
				reading.current?.abort();
				const controller = new AbortController();
				reading.current = controller;
				setLoading(true);
				setError("");
				setListing(void 0);
				try {
					const value = await send({
						action: "browse-directory",
						path,
						...complete && { complete }
					}, controller.signal);
					if (!controller.signal.aborted && alive.current) {
						setListing(value);
						if (!value.partial) setParent(value.path);
						return value;
					}
				} catch (reason) {
					if (!controller.signal.aborted && alive.current) setError(reason instanceof Error ? reason.message : "无法读取目录。");
				} finally {
					if (!controller.signal.aborted && alive.current) setLoading(false);
				}
			};
			(0, react.useEffect)(() => {
				alive.current = true;
				dialog.current?.showModal();
				return () => {
					alive.current = false;
					reading.current?.abort();
					clearTimeout(typing.current);
				};
			}, []);
			(0, react.useEffect)(() => {
				reading.current?.abort();
				clearTimeout(typing.current);
				setBrowseOpen(false);
				setListing(void 0);
				setParent(connected && remoteLocation ? "/" : "");
				setError("");
				setLoading(false);
				if (connected) browse();
				return () => reading.current?.abort();
			}, [serverId, connected]);
			const confirmParent = () => {
				clearTimeout(typing.current);
				setBrowseOpen(false);
				if (connected && listing?.path !== parent) browse(parent);
			};
			(0, react.useEffect)(() => {
				if (!browseOpen) return;
				const outside = (event) => {
					if (!parentPicker.current?.contains(event.target)) confirmParent();
				};
				document.addEventListener("pointerdown", outside);
				return () => document.removeEventListener("pointerdown", outside);
			}, [
				browseOpen,
				parent,
				listing,
				connected
			]);
			const selectServer = (id, autoStart = false) => {
				setServerId(id);
				setError("");
				const server = remote.getSnapshot().servers.find((item) => item.id === id);
				if (server && !server.connected) setConnection({
					id,
					autoStart
				});
			};
			const chooseType = (value) => {
				if (value !== "general" && !remoteLocation) setServerId(null);
				setError("");
				setPluginId(value);
			};
			const invalidName = !name.trim() || /[<>:"/\\|?*\x00-\x1f]/.test(name) || /[. ]$/.test(name) || /^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/i.test(name);
			const create = async () => {
				if (saving || loading || !connected || invalidName || !pluginId || !listing || listing.path !== parent) return;
				if (workflowNotice && !remoteLocation) return;
				setSaving(true);
				setError("");
				const key = JSON.stringify([
					serverId,
					parent,
					name.trim(),
					pluginId
				]);
				if (submission.current.key !== key) submission.current = {
					key,
					requestId: crypto.randomUUID()
				};
				try {
					const result = await send({
						action: "create-folder",
						parent,
						name: name.trim(),
						pluginId,
						requestId: submission.current.requestId
					});
					if (!alive.current) return;
					if (serverId) {
						close();
						modes.selectServer(serverId);
						await remote.open({
							serverId,
							workspaceId: result.workspace.workspaceId,
							...workflowNotice && { recommendPermissions: true }
						});
					} else {
						modes.enterCreatedWorkspace(result.workspace);
						close();
					}
				} catch (reason) {
					if (alive.current) setError(reason instanceof Error ? reason.message : "创建未完成，请重试。");
				} finally {
					if (alive.current) setSaving(false);
				}
			};
			return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("dialog", {
				ref: dialog,
				className: "cwb-directory cb-create-workspace",
				"aria-label": "创建工作区",
				onCancel: (event) => {
					event.preventDefault();
					if (!saving && !connection) close();
				},
				children: [
					/* @__PURE__ */ (0, react_jsx_runtime.jsx)("h2", { children: "创建工作区" }),
					/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("label", {
						className: "cb-create-field",
						children: ["工作流", /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("select", {
							autoFocus: true,
							"aria-label": "工作流",
							value: pluginId,
							required: true,
							disabled: saving,
							onChange: (event) => chooseType(event.target.value),
							children: [
								/* @__PURE__ */ (0, react_jsx_runtime.jsx)("option", {
									value: "",
									disabled: true,
									children: "选择一个工作流"
								}),
								/* @__PURE__ */ (0, react_jsx_runtime.jsx)("option", {
									value: GENERAL_WORKSPACE,
									children: "空白工作区：不安装工作流"
								}),
								workflows.map((workflow) => /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("option", {
									value: workflow.id,
									children: [
										workflow.id,
										"：",
										workflow.description?.trim() || zh[WORKFLOWS.find((item) => item.id === workflow.id)?.description ?? "flashDescription"]
									]
								}, workflow.id))
							]
						})]
					}),
					/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("label", {
						className: "cb-create-field",
						children: ["服务器", /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("select", {
							"aria-label": "服务器",
							value: serverId ?? "__select_server__",
							disabled: saving || modes.embedded,
							onChange: (event) => {
								if (event.target.value === "__add_server__") remote.showConnections((id) => {
									if (alive.current) selectServer(id, true);
								});
								else if (event.target.value !== "" || !workflowNotice) selectServer(event.target.value);
							},
							children: [
								/* @__PURE__ */ (0, react_jsx_runtime.jsx)("option", {
									value: "__select_server__",
									disabled: true,
									children: "选择一个服务器"
								}),
								/* @__PURE__ */ (0, react_jsx_runtime.jsx)("option", {
									value: "",
									disabled: workflowNotice && !modes.embedded,
									children: modes.embedded ? "此服务器" : workflowNotice ? "本机（本工作流需要连接NPU的Linux环境）" : "本机"
								}),
								!modes.embedded && servers.servers.map((server) => /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("option", {
									value: server.id,
									"aria-label": `${server.label || server.alias}，${server.connected ? "已连接" : "未连接"}`,
									children: [
										server.connected ? "🟢" : "🔴",
										" ",
										server.label || server.alias
									]
								}, server.id)),
								!modes.embedded && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("option", {
									value: "__add_server__",
									children: "添加服务器"
								})
							]
						})]
					}),
					workflowNotice && !connected && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", {
						role: "alert",
						className: "cwb-error",
						children: "本工作流需要在连接了NPU环境的Linux服务器上创建"
					}),
					/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
						ref: parentPicker,
						className: "cb-parent-picker",
						children: [/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("label", {
							className: "cb-create-field",
							children: ["父目录", /* @__PURE__ */ (0, react_jsx_runtime.jsx)("input", {
								"aria-label": "父目录",
								"aria-expanded": browseOpen,
								"aria-controls": "cb-parent-directories",
								autoComplete: "off",
								value: parent,
								disabled: saving || !connected,
								onClick: () => setBrowseOpen(true),
								onChange: (event) => {
									const value = event.target.value;
									reading.current?.abort();
									clearTimeout(typing.current);
									setParent(value);
									setBrowseOpen(true);
									setError("");
									setLoading(true);
									typing.current = setTimeout(() => {
										browse(value, true);
									}, 250);
								},
								onKeyDown: (event) => {
									if (event.key === "Enter") {
										event.preventDefault();
										setBrowseOpen(true);
										browse(parent, true);
									}
									if (event.key === "Escape" && browseOpen) {
										event.preventDefault();
										event.stopPropagation();
										confirmParent();
									}
									if (event.key === "Tab" && !event.shiftKey && browseOpen && parent !== listing?.path) {
										event.preventDefault();
										browse(parent, true).then((value) => {
											if (value?.partial && value.entries.length) browse(value.entries[0].path);
										});
									}
								}
							})]
						}), browseOpen && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
							id: "cb-parent-directories",
							className: "cb-parent-browser",
							style: { maxHeight: Math.max(120, window.innerHeight - (parentPicker.current?.getBoundingClientRect().bottom ?? 0) - 16) },
							children: [
								loading && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", {
									role: "status",
									children: "正在读取目录…"
								}),
								!loading && listing && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)(react_jsx_runtime.Fragment, { children: [
									/* @__PURE__ */ (0, react_jsx_runtime.jsx)("nav", {
										"aria-label": "目录层级",
										children: listing.crumbs.map((crumb) => /* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
											type: "button",
											className: "cwb-text-button",
											disabled: saving,
											onClick: () => void browse(crumb.path),
											children: crumb.name
										}, crumb.path))
									}),
									/* @__PURE__ */ (0, react_jsx_runtime.jsx)("ul", {
										className: "cwb-directory-list",
										children: listing.entries.map((entry) => /* @__PURE__ */ (0, react_jsx_runtime.jsx)("li", { children: /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("button", {
											type: "button",
											disabled: saving,
											onClick: () => void browse(entry.path),
											children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)(WorkbenchIcon, {
												name: "folder",
												size: 16
											}), entry.name]
										}) }, entry.path))
									}),
									!listing.entries.length && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", { children: listing.partial ? "没有匹配的文件夹。" : "此目录下没有子文件夹。" }),
									listing.truncated && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", { children: "仅显示部分目录，可输入完整路径。" })
								] }),
								/* @__PURE__ */ (0, react_jsx_runtime.jsx)("footer", { children: /* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
									type: "button",
									className: "cwb-text-button",
									disabled: loading || saving || !listing || parent !== listing.path,
									onClick: confirmParent,
									children: "确认"
								}) })
							]
						})]
					}),
					loading && !browseOpen && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", {
						role: "status",
						children: "正在读取目录…"
					}),
					/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("label", {
						className: "cb-create-field",
						children: ["工作区名", /* @__PURE__ */ (0, react_jsx_runtime.jsx)("input", {
							"aria-label": "工作区名",
							placeholder: "新工作区名称",
							value: name,
							disabled: saving,
							onChange: (event) => setName(event.target.value)
						})]
					}),
					error && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", {
						role: "alert",
						className: "cwb-error",
						children: error
					}),
					connection && /* @__PURE__ */ (0, react_jsx_runtime.jsx)(WorkspaceConnectionDialog, {
						remote,
						id: connection.id,
						autoStart: connection.autoStart,
						complete: () => setConnection(null),
						cancel: () => {
							setConnection(null);
							setServerId(null);
						}
					}),
					/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("footer", { children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
						type: "button",
						className: "cwb-text-button",
						disabled: saving,
						onClick: close,
						children: "取消"
					}), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
						type: "button",
						className: "cwb-primary",
						disabled: saving || loading || !connected || invalidName || !pluginId || !listing || parent !== listing.path,
						onClick: () => void create(),
						children: saving ? "正在创建…" : "创建工作区"
					})] })
				]
			});
		}
		function WorkspaceConnectionDialog({ remote, id, autoStart, complete, cancel }) {
			const state = (0, react.useSyncExternalStore)(remote.subscribe, remote.getSnapshot);
			const dialog = (0, react.useRef)(null), log = (0, react.useRef)(null), alive = (0, react.useRef)(true), running = (0, react.useRef)(false);
			const cancelling = (0, react.useRef)(false);
			const [stopping, setStopping] = (0, react.useState)(false);
			const [phase, setPhase] = (0, react.useState)(autoStart ? "connecting" : "confirm");
			const [error, setError] = (0, react.useState)("");
			const server = state.servers.find((item) => item.id === id);
			const connect = async () => {
				if (running.current) return;
				if (remote.getSnapshot().servers.find((item) => item.id === id)?.connected) {
					complete();
					return;
				}
				running.current = true;
				setPhase("connecting");
				setError("");
				try {
					await remote.connect(id);
					if (alive.current && !cancelling.current) complete();
				} catch (reason) {
					if (alive.current && !cancelling.current) {
						setError(reason instanceof Error ? reason.message : "连接失败，请重试。");
						setPhase("error");
					}
				} finally {
					running.current = false;
				}
			};
			const stop = async () => {
				if (cancelling.current) return;
				if (phase !== "connecting") {
					cancel();
					return;
				}
				cancelling.current = true;
				setStopping(true);
				setError("");
				try {
					await remote.cancelConnect(id);
					if (alive.current) cancel();
				} catch {
					if (alive.current) {
						cancelling.current = false;
						setStopping(false);
						setError("取消连接未完成，请重试。");
					}
				}
			};
			(0, react.useEffect)(() => {
				alive.current = true;
				dialog.current?.showModal();
				if (autoStart) connect();
				return () => {
					alive.current = false;
				};
			}, []);
			(0, react.useEffect)(() => {
				if (log.current) log.current.scrollTop = log.current.scrollHeight;
			}, [state.progress]);
			return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("dialog", {
				ref: dialog,
				className: `cwb-directory cb-workspace-connection ${phase !== "confirm" ? "cb-connection-progress" : ""}`,
				"aria-label": phase === "confirm" ? "连接服务器" : "服务器连接与安装",
				onCancel: (event) => {
					event.preventDefault();
					event.stopPropagation();
					stop();
				},
				children: [
					/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("header", { children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("h2", { children: phase === "confirm" ? "连接服务器" : "服务器连接与安装" }), phase === "connecting" && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
						type: "button",
						className: "cwb-text-button",
						disabled: stopping,
						onClick: () => void stop(),
						children: stopping ? "正在取消…" : "取消"
					})] }),
					/* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", { children: server?.label || server?.alias || id }),
					phase === "confirm" ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", { children: "服务器还未连接，是否立即连接？" }) : /* @__PURE__ */ (0, react_jsx_runtime.jsx)("pre", {
						ref: log,
						role: "log",
						"aria-label": "连接与安装日志",
						"aria-live": "polite",
						children: state.progress.join("\n") || "正在连接服务器…"
					}),
					error && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", {
						role: "alert",
						className: "cwb-error",
						children: error
					}),
					phase === "connecting" ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", {
						role: "status",
						children: "正在连接并准备环境，完成后自动关闭…"
					}) : /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("footer", { children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
						type: "button",
						className: "cwb-text-button",
						onClick: cancel,
						children: phase === "confirm" ? "取消" : "关闭"
					}), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
						type: "button",
						className: "cwb-primary",
						disabled: state.busy,
						onClick: () => void connect(),
						children: phase === "confirm" ? "确认" : "重试"
					})] })
				]
			});
		}
		// src/client/SidebarActions.tsx
		function ArchivedViewMenu({ value, change }) {
			const [open, setOpen] = (0, react.useState)(false);
			return /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.Menu, {
				open,
				onClose: () => setOpen(false),
				align: "end",
				dense: true,
				portal: true,
				selectedId: value,
				items: [
					{
						type: "label",
						id: "filter-by",
						text: "筛选会话"
					},
					{
						id: "default",
						label: "隐藏已归档",
						icon: /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.IconArchiveOffOutlineRegular, {})
					},
					{
						id: "show",
						label: "全部对话（显示已归档）",
						icon: /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.IconQueueOutlineRegular, {})
					},
					{
						id: "only",
						label: "仅显示已归档",
						icon: /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.IconArchiveCheckOutlineRegular, {})
					}
				],
				onSelect: (id) => {
					if (id === "default" || id === "show" || id === "only") change(id);
					setOpen(false);
				},
				anchor: /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.Tooltip, {
					label: "视图选项",
					side: "bottom",
					delayMs: 500,
					children: /* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
						type: "button",
						className: "cb-toolbar-button",
						"aria-label": "视图选项",
						onClick: () => setOpen((value) => !value),
						children: /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.IconSlidersTwoOutlineRegular, { size: 16 })
					})
				})
			});
		}
		/** The native browser owns its child slots; use the same public menu controls here. */
		function MoreMenu({ label, disabled, children, className = "" }) {
			const [open, setOpen] = (0, react.useState)(false);
			return /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.Menu, {
				open,
				onClose: () => setOpen(false),
				portal: true,
				closeOnPointerLeave: true,
				align: "start",
				anchor: /* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
					className: `cb-project-action ${className}`,
					type: "button",
					"aria-label": label,
					"aria-haspopup": "menu",
					"aria-expanded": open,
					disabled,
					onClick: (event) => {
						event.stopPropagation();
						setOpen((value) => !value);
					},
					children: /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.IconEllipsisOutlineRegular, { size: 16 })
				}),
				children: children(() => setOpen(false))
			});
		}
		function message(reason, fallback) {
			return reason instanceof Error && reason.message ? reason.message : fallback;
		}
		function useActionError(readback, recovered) {
			const [error, setError] = (0, react.useState)(null);
			const current = (0, react.useRef)(readback);
			current.current = readback;
			(0, react.useEffect)(() => {
				if (error?.committed && readback && readback.revision > error.revision) {
					setError(null);
					recovered?.();
				}
			}, [
				error,
				readback?.revision,
				recovered
			]);
			return {
				error,
				clear: () => setError(null),
				report: (reason, fallback) => setError({
					message: message(reason, fallback),
					committed: !!reason && typeof reason === "object" && "committed" in reason && reason.committed === true,
					revision: current.current?.revision ?? 0
				})
			};
		}
		/** Retry only the read after a committed write; never run the mutation again. */
		function RefreshListButton({ readback }) {
			const [busy, setBusy] = (0, react.useState)(false), [failed, setFailed] = (0, react.useState)(false);
			const pending = (0, react.useRef)(false);
			const refresh = async () => {
				if (pending.current) return;
				pending.current = true;
				setBusy(true);
				setFailed(false);
				try {
					await readback.refresh();
				} catch {
					setFailed(true);
				} finally {
					pending.current = false;
					setBusy(false);
				}
			};
			return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)(react_jsx_runtime.Fragment, { children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.Button, {
				variant: "outline",
				disabled: busy,
				onClick: () => void refresh(),
				children: busy ? "正在刷新…" : "刷新列表"
			}), failed && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
				role: "alert",
				children: " 刷新未完成，请重试刷新列表。"
			})] });
		}
		function RenameDialog({ title, field, initial, save, close, allowEmpty = false, allowUnchanged = false, description, maxLength = 2e3, readback, actionLabel = "重命名", validate }) {
			const [value, setValue] = (0, react.useState)(initial), [busy, setBusy] = (0, react.useState)(false);
			const { error, clear, report } = useActionError(readback, close);
			const saving = (0, react.useRef)(false), composing = (0, react.useRef)(false);
			const validation = validate?.(value.trim());
			const blocked = busy || !!error?.committed || !allowEmpty && !value.trim() || !allowUnchanged && value.trim() === initial.trim() || !!validation;
			const confirm = async () => {
				if (blocked || saving.current) return;
				saving.current = true;
				setBusy(true);
				clear();
				try {
					await save(value.trim());
					close();
				} catch (reason) {
					report(reason, "保存未完成，请重试。");
				} finally {
					saving.current = false;
					setBusy(false);
				}
			};
			return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)(_deepseek_ai_dsh_client_ui_primitives.Modal, {
				open: true,
				title,
				closeLabel: "关闭",
				description,
				onClose: () => {
					if (!saving.current) close();
				},
				footer: /* @__PURE__ */ (0, react_jsx_runtime.jsxs)(react_jsx_runtime.Fragment, { children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.Button, {
					variant: "outline",
					disabled: busy,
					onClick: close,
					children: error?.committed ? "关闭" : "取消"
				}), error?.committed ? readback && /* @__PURE__ */ (0, react_jsx_runtime.jsx)(RefreshListButton, { readback }) : /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.Button, {
					variant: "outline",
					disabled: blocked,
					onClick: () => void confirm(),
					children: actionLabel
				})] }),
				children: [
					/* @__PURE__ */ (0, react_jsx_runtime.jsx)("input", {
						className: "cb-rename-input",
						"data-modal-autofocus": true,
						"aria-label": field,
						value,
						maxLength,
						disabled: busy || !!error?.committed,
						onFocus: (event) => event.target.select(),
						onChange: (event) => {
							setValue(event.target.value);
							clear();
						},
						onCompositionStart: () => {
							composing.current = true;
						},
						onCompositionEnd: () => {
							composing.current = false;
						},
						onKeyDown: (event) => {
							if (event.key === "Enter" && !composing.current) {
								event.preventDefault();
								confirm();
							}
						}
					}),
					validation && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", {
						className: "cb-sidebar-error",
						role: "alert",
						children: validation
					}),
					error && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", {
						className: "cb-sidebar-error",
						role: "alert",
						children: error.message
					})
				]
			});
		}
		function ConfirmAction({ title, description, action, pending, confirm, close, children, readback }) {
			const [busy, setBusy] = (0, react.useState)(false), saving = (0, react.useRef)(false);
			const { error, clear, report } = useActionError(readback, close);
			const perform = async () => {
				if (saving.current || error?.committed) return;
				saving.current = true;
				setBusy(true);
				clear();
				try {
					await confirm();
					close();
				} catch (reason) {
					report(reason, "操作未完成，请重试。");
				} finally {
					saving.current = false;
					setBusy(false);
				}
			};
			return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)(_deepseek_ai_dsh_client_ui_primitives.Modal, {
				open: true,
				title,
				closeLabel: "关闭",
				description,
				onClose: () => {
					if (!saving.current) close();
				},
				footer: /* @__PURE__ */ (0, react_jsx_runtime.jsxs)(react_jsx_runtime.Fragment, { children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.Button, {
					variant: "outline",
					disabled: busy,
					onClick: close,
					children: error?.committed ? "关闭" : "取消"
				}), error?.committed ? readback && /* @__PURE__ */ (0, react_jsx_runtime.jsx)(RefreshListButton, { readback }) : /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.Button, {
					variant: "outline",
					className: "cb-danger-action",
					disabled: busy,
					onClick: () => void perform(),
					children: action
				})] }),
				children: [
					children,
					busy && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", {
						role: "status",
						children: pending
					}),
					error && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", {
						className: "cb-sidebar-error",
						role: "alert",
						children: error.message
					})
				]
			});
		}
		function WorkspaceActions({ workspace, allWorkspaces, run, disabled, readback }) {
			const [dialog, setDialog] = (0, react.useState)(null);
			return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)(react_jsx_runtime.Fragment, { children: [
				/* @__PURE__ */ (0, react_jsx_runtime.jsx)(MoreMenu, {
					label: `${workspace.title}的工作区操作`,
					disabled,
					children: (close) => /* @__PURE__ */ (0, react_jsx_runtime.jsxs)(react_jsx_runtime.Fragment, { children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.MenuItemButton, {
						icon: /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.IconEditOutlineRegular, { size: 16 }),
						onSelect: () => {
							close();
							setDialog("rename");
						},
						children: "重命名"
					}), /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.MenuItemButton, {
						danger: true,
						icon: /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.IconTrashOutlineRegular, { size: 16 }),
						onSelect: () => {
							close();
							setDialog("remove");
						},
						children: "删除工作区"
					})] })
				}),
				workspace && dialog === "rename" && /* @__PURE__ */ (0, react_jsx_runtime.jsx)(RenameDialog, {
					title: "重命名工作区",
					field: "工作区名称",
					initial: workspace.title,
					readback,
					validate: (title) => title && allWorkspaces.some((item) => item.workspaceId !== workspace.workspaceId && item.title === title) ? `已存在名为“${title}”的工作区。` : void 0,
					close: () => setDialog(null),
					save: (title) => run({
						action: "rename-workspace",
						workspaceId: workspace.workspaceId,
						title
					})
				}),
				workspace && dialog === "remove" && /* @__PURE__ */ (0, react_jsx_runtime.jsx)(ConfirmAction, {
					title: "删除工作区",
					description: `将把“${workspace.title}”从工作区列表中移除。文件夹与会话记录会保留，其会话不再显示在 CANNBot 列表中。`,
					action: "删除工作区",
					pending: "正在移除工作区…",
					readback,
					close: () => setDialog(null),
					confirm: () => run({
						action: "remove-workspace",
						workspaceId: workspace.workspaceId
					})
				})
			] });
		}
		function activeRefusal(reason) {
			if (!reason || typeof reason !== "object") return;
			const value = reason;
			if ((value.code || value.rpcError?.code) !== "workspace/session-active") return;
			const activity = value.activity || value.details?.activity || value.rpcError?.details?.activity;
			return Array.isArray(activity) ? activity.filter((entry) => !!entry && typeof entry === "object" && typeof entry.kind === "string") : [];
		}
		function activityLine(entry) {
			if (entry.kind === "turn") return "进行中的回合";
			const labels = {
				subagent: "运行中的子智能体",
				job: "后台任务",
				schedule: "定时提醒"
			};
			const items = Array.isArray(entry.items) ? entry.items : [];
			return `${items.length} 项${labels[entry.kind] || `其他工作（${entry.kind}）`}${items.length ? `：${items.map((item) => item.label || item.id).join("、")}` : ""}`;
		}
		function SessionActions({ session, run, disabled, canFork = true, readback, renameRequest = 0, copyFeedback }) {
			const [renaming, setRenaming] = (0, react.useState)(false), [activity, setActivity] = (0, react.useState)(null);
			const [busy, setBusy] = (0, react.useState)(false), pending = (0, react.useRef)(false);
			const { error, clear, report } = useActionError(readback);
			(0, react.useEffect)(() => {
				if (renameRequest > 0 && !session.blank) setRenaming(true);
			}, [renameRequest, session.blank]);
			const act = async (operation, archive = false) => {
				if (pending.current || error?.committed) return;
				pending.current = true;
				setBusy(true);
				clear();
				try {
					await operation();
				} catch (reason) {
					const active = archive ? activeRefusal(reason) : void 0;
					if (active) setActivity(active);
					else report(reason, "操作未完成，请重试。");
				} finally {
					pending.current = false;
					setBusy(false);
				}
			};
			const blocked = disabled || busy || !!error?.committed;
			const archive = () => act(() => run({
				action: session.archived ? "unarchive-session" : "archive-session",
				sessionId: session.id
			}), !session.archived);
			const pin = () => act(() => run({
				action: session.pinned ? "unpin-session" : "pin-session",
				sessionId: session.id
			}));
			const archiveLabel = session.archived ? "取消归档" : "归档会话", pinLabel = session.pinned ? "取消置顶" : "置顶会话";
			const archiveIcon = session.archived ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.IconUnarchiveOutlineRegular, { size: 14 }) : /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.IconArchiveOutlineRegular, { size: 14 });
			const pinIcon = session.pinned ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.IconPinFillRegular, { size: 14 }) : /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.IconPinOutlineRegular, { size: 14 });
			if (session.blank) return null;
			return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)(react_jsx_runtime.Fragment, { children: [
				/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("span", {
					className: "cb-row-actions",
					"data-session-actions": true,
					onClick: (event) => event.stopPropagation(),
					children: [
						/* @__PURE__ */ (0, react_jsx_runtime.jsx)(MoreMenu, {
							label: session.title + "的会话操作",
							disabled: blocked,
							children: (close) => /* @__PURE__ */ (0, react_jsx_runtime.jsxs)(react_jsx_runtime.Fragment, { children: [
								!session.archived && /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.MenuItemButton, {
									icon: session.pinned ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.IconPinFillRegular, { size: 16 }) : /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.IconPinOutlineRegular, { size: 16 }),
									onSelect: () => {
										close();
										pin();
									},
									children: pinLabel
								}),
								/* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.MenuItemButton, {
									icon: /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.IconEditOutlineRegular, { size: 16 }),
									onSelect: () => {
										close();
										setRenaming(true);
									},
									children: "重命名"
								}),
								canFork && !session.archived && /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.MenuItemButton, {
									icon: /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.IconBranchOutlineRegular, { size: 16 }),
									onSelect: () => {
										close();
										act(() => run({
											action: "fork-session",
											sessionId: session.id,
											allowMigration: false
										}));
									},
									children: "分叉会话"
								}),
								/* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.MenuItemButton, {
									icon: archiveIcon,
									onSelect: () => {
										close();
										archive();
									},
									children: archiveLabel
								}),
								/* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.MenuItemButton, {
									icon: /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.IconCopyOutlineRegular, { size: 16 }),
									onSelect: () => {
										close();
										act(async () => {
											try {
												await navigator.clipboard.writeText(session.id);
												copyFeedback?.(true);
											} catch (reason) {
												copyFeedback?.(false);
												if (!copyFeedback) throw reason;
											}
										});
									},
									children: "复制 Session ID"
								})
							] })
						}),
						/* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.Tooltip, {
							label: archiveLabel,
							side: "bottom",
							align: "end",
							delayMs: 500,
							portal: true,
							children: /* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
								type: "button",
								className: "cb-project-action",
								"aria-label": archiveLabel,
								disabled: blocked,
								"data-session-action": "archive",
								onClick: () => void archive(),
								children: archiveIcon
							})
						}),
						!session.archived && /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.Tooltip, {
							label: pinLabel,
							side: "bottom",
							align: "end",
							delayMs: 500,
							portal: true,
							children: /* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
								type: "button",
								className: "cb-project-action",
								"aria-label": pinLabel,
								disabled: blocked,
								"data-session-action": "pin",
								onClick: () => void pin(),
								children: pinIcon
							})
						})
					]
				}),
				error && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("p", {
					className: "cb-sidebar-error",
					role: "alert",
					children: [error.message, error.committed && readback && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)(react_jsx_runtime.Fragment, { children: [" ", /* @__PURE__ */ (0, react_jsx_runtime.jsx)(RefreshListButton, { readback })] })]
				}),
				renaming && /* @__PURE__ */ (0, react_jsx_runtime.jsx)(RenameDialog, {
					title: "重命名会话",
					field: "会话名称",
					initial: session.title,
					allowUnchanged: true,
					readback,
					save: (title) => run({
						action: "rename-session",
						sessionId: session.id,
						title
					}),
					close: () => setRenaming(false)
				}),
				activity && /* @__PURE__ */ (0, react_jsx_runtime.jsx)(ConfirmAction, {
					title: "停止并归档此会话？",
					description: "“" + session.title + "”仍有正在进行的工作。归档会先停止这些工作；之后可在侧栏筛选“全部对话（显示已归档）”中恢复会话，被停止的工作不会自动继续。",
					action: "停止并归档",
					pending: "正在停止并归档…",
					readback,
					close: () => setActivity(null),
					confirm: () => run({
						action: "archive-session",
						sessionId: session.id,
						stopActivity: true
					}),
					children: /* @__PURE__ */ (0, react_jsx_runtime.jsx)("ul", {
						className: "cb-archive-activity",
						"aria-label": "将被停止的工作",
						children: activity.map((entry, index) => /* @__PURE__ */ (0, react_jsx_runtime.jsx)("li", { children: activityLine(entry) }, entry.kind + "-" + index))
					})
				})
			] });
		}
		// src/client/SidebarNotice.tsx
		/** One sidebar's notice identity also bounds asynchronous action feedback. */
		function createSidebarNotices() {
			let current = null;
			let sequence = 0;
			let disposed = false;
			const listeners = /* @__PURE__ */ new Set();
			const publish = (notice) => {
				current = notice;
				for (const listener of listeners) listener();
			};
			const show = (notice) => {
				if (!disposed) publish({
					...notice,
					seq: ++sequence
				});
			};
			const clear = () => {
				sequence++;
				if (current) publish(null);
			};
			const action = (seq, callback, undo = false) => () => {
				if (disposed || current?.seq !== seq) return;
				publish(null);
				const reportFailure = (reason) => {
					if (disposed || sequence !== seq) return;
					const committed = !!reason && typeof reason === "object" && "committed" in reason && reason.committed === true;
					show({
						text: committed ? "操作已完成，但列表刷新失败。请刷新列表确认。" : undo ? "取消归档未完成，请刷新列表确认后重试。" : "筛选未完成，请重试。",
						tone: "warning"
					});
				};
				try {
					Promise.resolve(callback()).catch(reportFailure);
				} catch (reason) {
					reportFailure(reason);
				}
			};
			return {
				getSnapshot: () => current,
				subscribe(listener) {
					if (!disposed) listeners.add(listener);
					return () => {
						listeners.delete(listener);
					};
				},
				archived({ stopped, undo, showArchived }) {
					if (disposed) return;
					const seq = sequence + 1;
					show({
						text: stopped ? "已停止并归档，可" : "会话已归档，可",
						tone: "success",
						holdMs: 6e3,
						actions: [{
							label: "撤销",
							onClick: action(seq, undo, true)
						}],
						...showArchived ? { filterAction: {
							prefix: "或",
							label: "筛选已归档会话",
							onClick: action(seq, showArchived)
						} } : {}
					});
				},
				copied(ok) {
					show({
						text: ok ? "Session ID 已复制" : "复制失败，请重试",
						tone: ok ? "success" : "warning"
					});
				},
				archivedNotOpenable() {
					show({
						text: "已归档对话暂时无法查看，请取消归档后查看",
						tone: "warning"
					});
				},
				clear,
				dismiss(seq) {
					if (current?.seq === seq) clear();
				},
				dispose() {
					disposed = true;
					clear();
					listeners.clear();
				}
			};
		}
		/** Reuse the exact native portal, typography, icon, actions and fade timing. */
		function SidebarNotice({ notices, archivedVisible = false }) {
			const notice = (0, react.useSyncExternalStore)(notices.subscribe, notices.getSnapshot, notices.getSnapshot);
			if (!notice) return null;
			return /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.Toast, {
				text: notice.text,
				holdMs: notice.holdMs,
				...notice.tone === "success" ? { tone: "success" } : { icon: /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.IconWarningOutlineRegular, {}) },
				actions: [...notice.actions ?? [], ...!archivedVisible && notice.filterAction ? [notice.filterAction] : []],
				onDone: () => notices.dismiss(notice.seq)
			}, notice.seq);
		}
		// \0dsh-global-css:/home/t00607008/cannbot/dsh/src/client/modes.css.mjs
		const css$2 = "[data-slot=sidebar] [data-cannbot-mode-switch-host]{-webkit-app-region:no-drag;flex-direction:column;flex-shrink:0;min-width:0;display:flex}.cb-mode-switch{box-sizing:border-box;min-height:36px;color:var(--dsw-alias-label-primary);font:inherit;text-align:left;cursor:pointer;border-radius:var(--dsw-radius-md,8px);background:0 0;border:0;align-items:center;gap:8px;margin:0 2px;padding:7px 8px;font-size:14px;line-height:22px;display:flex}.cb-mode-switch-icon{flex:none;justify-content:center;align-items:center;display:inline-flex}.cb-mode-switch-name{text-overflow:ellipsis;white-space:nowrap;min-width:0;overflow:hidden}[data-sidebar-collapsed=true] .cb-mode-switch{justify-content:center;width:36px;height:36px;margin:0;padding:0}[data-sidebar-collapsed=true] .cb-mode-switch-name{display:none}[data-sidebar-collapsed=true] .cb-mode-switch-icon>*{width:18px;height:18px}.cb-workspaces{box-sizing:border-box;height:100%;min-height:0;padding-right:var(--dsh-sidebar-inline-padding,12px);color:var(--dsw-alias-label-primary);flex-direction:column;font-family:inherit;display:flex}[data-cannbot-embedded-frame]>[data-cannbot-embedded-column=sidebar],[data-cannbot-embedded-frame]>[data-side=sidebar],[data-cannbot-embedded-frame]>[data-shell-leading]{display:none}[data-cannbot-embedded-frame]>[data-cannbot-embedded-column=main]{grid-area:1/1/auto/3}[data-cannbot-embedded-frame]>[data-cannbot-embedded-column=rightbar]{grid-area:1/3/auto/4}.cb-icon-button,.cb-add-server,.cb-session,.cb-sidebar-error>button{font:inherit;color:inherit;cursor:pointer;border-radius:var(--dsw-radius-md,8px);background:0 0;border:0}.cb-icon-button:hover,.cb-add-server:hover,.cb-mode-switch:hover{background:var(--dsw-alias-interactive-bg-hover)}.cb-workspaces button:focus-visible,.cb-mode-switch:focus-visible,.cb-project-row:focus-visible{outline:2px solid var(--dsw-focus-ring-color);outline-offset:-2px}.cb-icon-button{flex-shrink:0;justify-content:center;align-items:center;padding:6px;display:inline-flex}.cb-workspace-list{min-height:0;overflow-y:auto}.cb-project-row{box-sizing:border-box;height:34px;padding:0 8px;min-width:0;color:var(--dsw-alias-label-primary);border-radius:var(--dsw-radius-md);user-select:none;align-items:center;gap:6px;padding-inline-start:calc(8px + var(--cb-workspace-indent,0px));display:flex}.cb-project-row[aria-expanded]{cursor:pointer}.cb-project-row:hover,.cb-project-row:has([aria-haspopup=menu][aria-expanded=true]){background:var(--dsw-alias-interactive-bg-hover)}.cb-project-title{text-overflow:ellipsis;white-space:nowrap;min-width:0;color:inherit;font-size:14px;line-height:20px;overflow:hidden}.cb-project-text{flex-direction:column;flex:1;gap:2px;min-width:0;display:flex;overflow:hidden}.cb-project-accessory{flex:none;align-items:center;display:inline-flex}.cb-leading{width:16px;height:20px;color:var(--dsw-alias-label-tertiary);flex:none;justify-content:center;align-items:center;display:inline-flex}.cb-project-selected>.cb-project-row>.cb-folder{color:var(--dsw-alias-state-business-primary)}.cb-project-row>.cb-chevron{color:var(--dsw-alias-label-caption);display:none}.cb-project-row:hover>.cb-chevron{display:inline-flex}.cb-project-row:has(>.cb-chevron):hover>.cb-folder{display:none}.cb-chevron>svg{transition:transform .15s var(--ds-ease-in-out)}.cb-chevron-open{transform:rotate(90deg)}.cb-project-children{min-width:0}.cb-project-nested>.cb-project-children{--cb-workspace-indent:12px}.cb-project-row+.cb-project-children,.cb-project-children>*+*{margin-top:2px}.cb-project+.cb-project{margin-top:4px}.cb-project-action,.cb-connection-action{border-radius:var(--dsw-radius-xs);width:16px;height:16px;color:var(--dsw-alias-label-tertiary);cursor:pointer;background:0 0;border:0;flex:none;justify-content:center;align-items:center;padding:0;display:inline-flex}.cb-project-action:hover:not(:disabled),.cb-connection-action:hover:not(:disabled){color:var(--dsw-alias-label-primary)}.cb-workspaces .cb-server-actions .cb-connection-action{opacity:0;pointer-events:none}.cb-project-row:hover .cb-connection-action,.cb-project-row:focus-within .cb-connection-action,.cb-project-row:has([aria-haspopup=menu][aria-expanded=true]) .cb-connection-action{opacity:1;pointer-events:auto}.cb-connection-action>span{display:inline-flex}.cb-connection-pending{animation:1s linear infinite cb-connection-spin}@keyframes cb-connection-spin{to{transform:rotate(360deg)}}@media (prefers-reduced-motion:reduce){.cb-connection-pending{animation:none}.cb-chevron>svg{transition:none}}.cb-server-actions{flex-shrink:0;align-items:center;gap:15px;display:flex}.cb-workspaces button:disabled{cursor:default;opacity:.55}.cb-session-row{min-height:32px;border-radius:var(--dsw-radius-md);min-width:0;color:var(--dsw-alias-label-primary);user-select:none;flex-wrap:wrap;align-items:center;gap:0;padding:0 8px;padding-inline-start:calc(8px + var(--cb-workspace-indent,0px));display:flex}.cb-session{text-align:left;flex:1;align-items:center;min-width:0;height:32px;padding:0;display:flex}.cb-session-title{white-space:nowrap;text-overflow:ellipsis;flex:1;min-width:0;margin:0 6px 0 4px;font-size:14px;line-height:20px;overflow:hidden}.cb-session-row:hover,.cb-session-row:has([aria-current=page]),.cb-session-row:has([aria-haspopup=menu][aria-expanded=true]){background:var(--dsw-alias-interactive-bg-hover)}.cb-session-time{color:var(--dsw-alias-label-tertiary);flex:none;font-size:10px;line-height:16px}.cb-session-pin{width:16px;height:20px;color:var(--dsw-alias-label-caption);flex:none;justify-content:center;align-items:center;margin-left:6px;display:inline-flex}.cb-row-actions{flex:none;align-items:center;gap:15px;display:none}.cb-project-row .cb-row-actions{height:20px}.cb-project-row:hover .cb-row-actions,.cb-project-row:focus-within .cb-row-actions,.cb-project-row:has([aria-haspopup=menu][aria-expanded=true]) .cb-row-actions,.cb-session-row:hover>.cb-row-actions,.cb-session-row:focus-within>.cb-row-actions,.cb-session-row:has([aria-haspopup=menu][aria-expanded=true])>.cb-row-actions{display:inline-flex}.cb-server-actions>.cb-row-actions{visibility:hidden;pointer-events:none;display:inline-flex}.cb-project-row:hover .cb-server-actions>.cb-row-actions,.cb-project-row:focus-within .cb-server-actions>.cb-row-actions,.cb-project-row:has([aria-haspopup=menu][aria-expanded=true]) .cb-server-actions>.cb-row-actions{visibility:visible;pointer-events:auto}.cb-session-row:hover>.cb-session-time,.cb-session-row:hover>.cb-session-pin,.cb-session-row:focus-within>.cb-session-time,.cb-session-row:focus-within>.cb-session-pin,.cb-session-row:has([aria-haspopup=menu][aria-expanded=true])>.cb-session-time,.cb-session-row:has([aria-haspopup=menu][aria-expanded=true])>.cb-session-pin{display:none}.cb-session-archived .cb-session-title{color:var(--dsw-alias-label-caption)}.cb-session-row>.cb-sidebar-error{flex-basis:100%}.cb-empty,.cb-sidebar-error{color:var(--dsw-alias-label-secondary);margin:8px;font-size:12px;line-height:1.6}.cb-sidebar-error{color:var(--dsw-alias-state-danger-primary,#c7000b)}.cwb-plugin-choice{flex-direction:column;gap:8px;margin:16px 0;display:flex}.cwb-plugin-choice select{color:inherit;background:var(--dsw-alias-bg-layer-1);border:1px solid var(--dsw-alias-border-l2);border-radius:var(--dsw-radius-md,8px);padding:8px}.cb-rename-input{box-sizing:border-box;border:.5px solid var(--dsw-alias-border-l4);border-radius:var(--dsw-radius-lg);width:100%;height:44px;font:inherit;color:var(--dsw-alias-label-primary);background:0 0;outline:none;padding:7px 14px;font-size:14px;font-weight:400;line-height:22px}.cb-rename-input:disabled{color:var(--dsw-alias-label-dimmed)}.cb-danger-action:not(:disabled){color:var(--dsw-alias-state-error-primary)}.cb-archive-activity{color:var(--dsw-alias-label-primary);margin:0 0 8px;padding-left:18px;font-size:13px;line-height:20px}.cb-archive-activity li{overflow-wrap:anywhere}.cb-workspaces-heading{box-sizing:border-box;height:36px;color:var(--dsw-alias-label-tertiary);flex:none;align-items:center;gap:4px;margin:2px 0 4px;padding-left:4px;display:flex}.cb-workspaces-heading h2{min-width:0;margin:0;font-size:14px;font-weight:400;line-height:20px}.cb-heading-actions{align-items:center;gap:4px;margin-left:auto;display:flex}.cb-toolbar-button,.cb-add-server{border-radius:var(--dsw-radius-sm);width:28px;height:28px;font:inherit;color:var(--dsw-alias-label-secondary);cursor:pointer;background:0 0;border:0;flex:none;justify-content:center;align-items:center;padding:0;font-size:14px;display:inline-flex}.cb-toolbar-button:hover{background:var(--dsw-alias-interactive-bg-hover)}.cb-server-drop-before,.cb-server-drop-after{position:relative}.cb-server-drop-before:before,.cb-server-drop-after:after{content:\"\";z-index:1;pointer-events:none;background:linear-gradient(55deg,transparent calc(50% - 1px),var(--dsw-alias-state-business-primary) calc(50% - 1px),var(--dsw-alias-state-business-primary) calc(50% + 1px),transparent calc(50% + 1px)) 0 0/5px 7px no-repeat,linear-gradient(125deg,transparent calc(50% - 1px),var(--dsw-alias-state-business-primary) calc(50% - 1px),var(--dsw-alias-state-business-primary) calc(50% + 1px),transparent calc(50% + 1px)) 0 5px/5px 7px no-repeat,linear-gradient(var(--dsw-alias-state-business-primary) 0 0) 4px 5px/calc(100% - 4px) 2px no-repeat;height:12px;position:absolute;left:0;right:0}.cb-server-drop-before:before{top:-8px}.cb-server-drop-after:after{bottom:-8px}[data-cannbot-servers-host]{-webkit-app-region:no-drag;flex-direction:column;flex-shrink:0;display:flex}.cb-remote-folder{width:16px;height:16px;display:inline-flex;position:relative}.cb-globe-badge{background:var(--dsw-alias-bg-base);color:var(--dsw-alias-state-business-primary,#c7000b);border-radius:50%;display:flex;position:absolute;bottom:-3px;right:-4px}.cb-server-page{width:100%;max-width:880px;height:100%;margin:0 auto;padding:32px 40px}.cb-server-page .cb-workspaces-heading{height:40px;margin-bottom:20px}.cb-server-page .cb-workspaces-heading h2{color:var(--dsw-alias-label-primary);font-size:20px;font-weight:600}.cb-server-page .cb-project-row{height:44px}.cb-server-status{color:var(--dsw-alias-label-tertiary);font-size:12px}.cb-create-workspace{box-sizing:border-box;width:min(520px,100vw - 48px)}.cb-create-field{flex-direction:column;gap:8px;margin:16px 0 8px;display:flex}.cb-create-field input,.cb-create-field select{box-sizing:border-box;width:100%;font:inherit;border:1px solid var(--dsw-alias-border-l2);border-radius:var(--dsw-radius-md);color:inherit;background:0 0;padding:10px 12px}.cb-parent-browser{margin-top:12px}.cb-parent-browser .cwb-directory-list{min-height:0;max-height:180px}.cb-create-field select option{background:var(--dsw-alias-bg-layer-1,Canvas);color:var(--dsw-alias-label-primary,CanvasText)}.cb-create-field select option:disabled{color:var(--dsw-alias-label-dimmed,GrayText)}.cb-workspace-connection{box-sizing:border-box;width:min(680px,100vw - 48px)}.cb-workspace-connection pre{box-sizing:border-box;white-space:pre-wrap;overflow-wrap:anywhere;border-radius:var(--dsw-radius-md);background:var(--dsw-alias-bg-base);min-height:160px;max-height:320px;color:var(--dsw-alias-label-primary);padding:16px;font:12px/1.6 ui-monospace,Consolas,monospace;overflow:auto}.cb-workspace-connection>p{color:var(--dsw-alias-label-secondary);font-size:13px}.cb-workspace-connection>header{justify-content:space-between;align-items:center;gap:16px;display:flex}.cb-workspace-connection>header h2{margin:0}.cb-connection-progress[open]{flex-direction:column;height:min(480px,100vh - 48px);max-height:calc(100vh - 48px);display:flex}.cb-connection-progress pre{flex:1;min-height:0;max-height:none;margin:8px 0;overflow:auto}.cb-connection-progress>p,.cb-connection-progress>footer{flex:none}.cb-connection-progress .cwb-error{max-height:44px;overflow:auto}.cb-create-workspace{overflow:visible}.cb-parent-picker{position:relative}.cb-parent-browser{z-index:5;box-sizing:border-box;border:1px solid var(--dsw-alias-border-l2);border-radius:var(--dsw-radius-md);background:var(--dsw-alias-bg-layer-1);margin:4px 0 0;padding:12px;position:absolute;top:100%;left:0;right:0;box-shadow:0 8px 24px #0002}.cb-parent-browser nav{flex-wrap:wrap;gap:4px;display:flex}.cb-parent-browser footer{border-top:1px solid var(--dsw-alias-border-l2);justify-content:flex-end;margin-top:8px;padding-top:8px;display:flex}.cb-parent-browser p{font-size:13px}.cb-parent-browser .cwb-directory-list{max-height:min(180px,25vh);overflow:auto}.cb-parent-browser{flex-direction:column;display:flex}.cb-parent-browser .cwb-directory-list{flex:1;min-height:0}.cb-parent-browser>nav,.cb-parent-browser>footer,.cb-parent-browser>p{flex-shrink:0}";
		const tagId$2 = "@cannbot-plugin/cannbot-dsh/modes.css";
		if (typeof document !== "undefined" && document.querySelector("style[data-plugin-css=" + JSON.stringify(tagId$2) + "]") === null) {
			const tag = document.createElement("style");
			tag.dataset.plugin = "@cannbot-plugin/cannbot-dsh";
			tag.dataset.pluginCss = tagId$2;
			tag.textContent = css$2;
			document.head.appendChild(tag);
		}
		// src/client/ModeSidebar.tsx
		const SERVERS_PANEL = "cannbot-servers";
		function useStore(source) {
			const bound = (0, react.useMemo)(() => ({
				getSnapshot: () => source.getSnapshot(),
				subscribe: (listener) => source.subscribe(listener)
			}), [source]);
			return (0, react.useSyncExternalStore)(bound.subscribe, bound.getSnapshot);
		}
		/** CANNBot owns its brand; a neutral return entry restores the native workbench. */
		function ModeBrandMark({ modes, size = 24, onServers }) {
			const state = useStore(modes);
			const marker = (0, react.useRef)(null);
			const [host, setHost] = (0, react.useState)(null);
			const [serverHost, setServerHost] = (0, react.useState)(null);
			(0, react.useLayoutEffect)(() => {
				if (modes.embedded) return;
				const seat = (marker.current?.closest("[data-slot=\"sidebar.brand.mark\"]"))?.closest("[data-slot=\"sidebar\"]");
				if (!seat) return;
				const target = document.createElement("div");
				target.dataset.cannbotModeSwitchHost = "";
				const serverTarget = document.createElement("div");
				serverTarget.dataset.cannbotServersHost = "";
				const place = () => {
					const navigation = seat.querySelector("[data-slot=\"sidebar.panellist\"]")?.closest("nav");
					if (navigation && seat.contains(navigation)) {
						if (navigation.firstElementChild !== target) navigation.prepend(target);
						if (navigation.lastElementChild !== serverTarget) navigation.append(serverTarget);
						setServerHost((current) => current === serverTarget ? current : serverTarget);
						setHost((current) => current === target ? current : target);
					} else {
						target.remove();
						serverTarget.remove();
						setHost(null);
						setServerHost(null);
					}
				};
				const observer = new MutationObserver(place);
				observer.observe(seat, {
					childList: true,
					subtree: true
				});
				place();
				return () => {
					observer.disconnect();
					target.remove();
					serverTarget.remove();
				};
			}, [modes]);
			const cann = state.mode === "cannbot", brand = cann ? "返回原生工作台" : "CANNBot";
			return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)(react_jsx_runtime.Fragment, { children: [
				/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
					ref: marker,
					children: cann ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)(Mark, { size }) : /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.FishLogo, { size })
				}),
				host && (0, react_dom.createPortal)(/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("button", {
					className: "cb-mode-switch",
					type: "button",
					"aria-label": brand,
					title: cann ? brand : `切换到 ${brand}`,
					onClick: (event) => {
						event.stopPropagation();
						modes.setMode(cann ? "deepseek" : "cannbot");
					},
					children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
						className: "cb-mode-switch-icon",
						"aria-hidden": "true",
						children: cann ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)(WorkbenchIcon, {
							name: "back",
							size: 16
						}) : /* @__PURE__ */ (0, react_jsx_runtime.jsx)(Mark, { size: 16 })
					}), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
						className: "cb-mode-switch-name",
						children: brand
					})]
				}), host),
				cann && serverHost && onServers && (0, react_dom.createPortal)(/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("button", {
					type: "button",
					className: "cb-mode-switch",
					"aria-label": "服务器",
					onClick: (event) => {
						event.stopPropagation();
						onServers();
					},
					children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
						className: "cb-mode-switch-icon",
						children: /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.IconFollowsystemOutlineRegular, { size: 16 })
					}), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
						className: "cb-mode-switch-name",
						children: "服务器"
					})]
				}), serverHost)
			] });
		}
		const timestamp = (value) => typeof value === "number" ? value : value ? Date.parse(value) || 0 : 0;
		function ProjectRow({ title, expanded, toggle, accessory, selected, icon, expandable = true, nested = false, drag, children }) {
			const open = expandable && expanded;
			const fromAction = (0, react.useRef)(false);
			return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
				className: `cb-project${selected ? " cb-project-selected" : ""}${nested ? " cb-project-nested" : ""}${drag?.marker ? ` cb-server-drop-${drag.marker}` : ""}`,
				"data-cannbot-server-id": drag?.id,
				onDragOver: drag?.over,
				onDrop: drag?.drop,
				onDragLeave: drag?.leave,
				children: [/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
					className: "cb-project-row",
					"data-disclosure-header": true,
					"data-disclosure-row": true,
					role: expandable ? "button" : void 0,
					tabIndex: expandable ? 0 : void 0,
					"aria-label": title,
					"aria-expanded": expandable ? open : void 0,
					draggable: drag?.enabled,
					onPointerDownCapture: (event) => {
						fromAction.current = !!event.target.closest(".cb-project-accessory, button, a, input, [role=\"menu\"]");
						drag?.pointerDown();
					},
					onDragStart: drag ? (event) => {
						if (fromAction.current || !!event.target.closest(".cb-project-accessory, button, a, input, [role=\"menu\"]")) {
							event.preventDefault();
							event.stopPropagation();
							return;
						}
						drag.start(event);
					} : void 0,
					onDragEnd: drag?.end,
					onClickCapture: (event) => {
						if (drag?.consumeClick()) {
							event.preventDefault();
							event.stopPropagation();
						}
					},
					onClick: () => {
						if (expandable) toggle();
					},
					onKeyDown: (event) => {
						if (event.target === event.currentTarget && expandable && (event.key === "Enter" || event.key === " ")) {
							event.preventDefault();
							toggle();
						}
					},
					children: [
						/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
							className: "cb-leading cb-folder",
							children: icon || (open ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.IconFolderOpenRegular, { size: 16 }) : /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.IconFolderCloseRegular, { size: 16 }))
						}),
						expandable && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
							className: "cb-leading cb-chevron",
							children: /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.IconTriangleRightFillRegular, {
								size: 16,
								className: open ? "cb-chevron-open" : void 0
							})
						}),
						/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
							className: "cb-project-text",
							children: /* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
								className: "cb-project-title",
								children: title
							})
						}),
						/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
							className: "cb-project-accessory",
							onClick: (event) => event.stopPropagation(),
							children: accessory
						})
					]
				}), open && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
					className: "cb-project-children",
					children
				})]
			});
		}
		function NewWorkspaceAction({ label, onClick, disabled, workspace = false }) {
			return /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.Tooltip, {
				label,
				side: "bottom",
				align: "end",
				delayMs: 500,
				portal: true,
				children: /* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
					className: "cb-project-action",
					type: "button",
					"aria-label": label,
					onClick,
					disabled,
					children: workspace ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.IconProjectAddOutlineRegular, { size: 16 }) : /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.IconNewChatOutlineRegular, { size: 16 })
				})
			});
		}
		function WorkspaceRows({ workspaces, sessions, activeSessionId, currentBlankId, activeWorkspaceId, closed, toggle, open, create, run, disabled, readback, archivedFilter, allWorkspaces = workspaces, copyFeedback, remoteLabel }) {
			const workspaceIds = new Set(workspaces.map((workspace) => workspace.workspaceId));
			const group = (workspace) => {
				const id = workspace.workspaceId;
				const rows = sessions.filter((session) => session.workspaceId === id).filter((session) => (!session.blank || session.id === currentBlankId) && (archivedFilter === "show" || !!session.archived === (archivedFilter === "only")));
				if (archivedFilter === "only" && !rows.length) return null;
				const title = `${workspace.pluginId && workspace.pluginId !== "general" ? `${workspace.pluginId}: ` : ""}${workspace.title === "default-workspace" ? "默认工作区" : workspace.title}`;
				return /* @__PURE__ */ (0, react_jsx_runtime.jsx)(ProjectRow, {
					title,
					icon: remoteLabel ? /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("span", {
						className: "cb-remote-folder",
						role: "img",
						"aria-label": `远程工作区 · ${remoteLabel}`,
						title: remoteLabel,
						children: [closed.has(id) ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.IconFolderCloseRegular, { size: 16 }) : /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.IconFolderOpenRegular, { size: 16 }), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
							className: "cb-globe-badge",
							children: /* @__PURE__ */ (0, react_jsx_runtime.jsx)(WorkbenchIcon, {
								name: "globe",
								size: 10
							})
						})]
					}) : void 0,
					expanded: !closed.has(id),
					toggle: () => toggle(id),
					selected: !!workspace && activeWorkspaceId === id,
					accessory: workspace && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("span", {
						className: "cb-row-actions",
						children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)(WorkspaceActions, {
							workspace,
							allWorkspaces,
							run,
							disabled,
							readback
						}), /* @__PURE__ */ (0, react_jsx_runtime.jsx)(NewWorkspaceAction, {
							label: `在 ${workspace.title} 中新建会话`,
							onClick: () => create(id),
							disabled
						})]
					}),
					children: /* @__PURE__ */ (0, react_jsx_runtime.jsx)(SessionRows, {
						sessions: rows,
						activeSessionId,
						open,
						run,
						disabled,
						readback,
						copyFeedback
					})
				}, id);
			};
			return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)(react_jsx_runtime.Fragment, { children: [workspaces.map((workspace) => group(workspace)), workspaces.length > 0 && archivedFilter === "only" && !sessions.some((session) => workspaceIds.has(session.workspaceId) && session.archived) && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", {
				className: "cb-empty",
				children: "暂无已归档会话"
			})] });
		}
		function SessionRows({ sessions, activeSessionId, open, run, disabled, readback, copyFeedback }) {
			return /* @__PURE__ */ (0, react_jsx_runtime.jsx)(react_jsx_runtime.Fragment, { children: [...sessions].sort((a, b) => Number(!!b.blank) - Number(!!a.blank) || Number(!!b.pinned) - Number(!!a.pinned) || (a.pinned && b.pinned ? (a.pinOrder ?? 0) - (b.pinOrder ?? 0) : 0) || timestamp(b.updatedAt) - timestamp(a.updatedAt)).map((session) => /* @__PURE__ */ (0, react_jsx_runtime.jsx)(SessionRow, {
				session,
				active: activeSessionId === session.id,
				open: () => open(session),
				run,
				disabled,
				readback,
				copyFeedback
			}, session.id)) });
		}
		function toggleSet(previous, id) {
			const next = new Set(previous);
			next.has(id) ? next.delete(id) : next.add(id);
			return next;
		}
		/** Accept native desktop drops, with a one-shot drag-end fallback for a completed move. */
		function useServerReorder(remote, enabled) {
			const current = (0, react.useRef)(null), committing = (0, react.useRef)(false), alive = (0, react.useRef)(true), suppressUntil = (0, react.useRef)(0);
			const [drag, setDrag] = (0, react.useState)(null), [pending, setPending] = (0, react.useState)(false), [error, setError] = (0, react.useState)("");
			const clear = () => {
				if (current.current) suppressUntil.current = Date.now() + 500;
				current.current = null;
				setDrag(null);
			};
			(0, react.useEffect)(() => {
				alive.current = true;
				return () => {
					alive.current = false;
					current.current = null;
				};
			}, []);
			const blocked = () => {
				const state = remote.getSnapshot();
				return !enabled || committing.current || state.busy || state.orderingServers || !!state.removingServerIds?.length || !!state.disconnectingServerIds?.length;
			};
			const setOver = (over) => {
				const source = current.current;
				if (!source || source.over?.id === over?.id && source.over?.half === over?.half) return;
				current.current = {
					...source,
					over
				};
				setDrag(current.current);
			};
			const target = (node, clientY) => {
				const source = current.current;
				const group = node instanceof Element ? node.closest("[data-cannbot-server-id]") : null;
				const id = group?.dataset.cannbotServerId;
				if (!source || blocked() || !group || group.parentElement !== source.list || !id || id === source.id || !source.ids.includes(id) || !group.querySelector(":scope > .cb-project-row")?.draggable) return;
				const bounds = group.getBoundingClientRect();
				return {
					id,
					half: clientY < bounds.top + bounds.height / 2 ? "before" : "after"
				};
			};
			const commit = () => {
				const source = current.current;
				clear();
				if (!source?.over || blocked()) return;
				const ids = remote.getSnapshot().servers.map((server) => server.id);
				if (ids.length !== source.ids.length || ids.some((value, index) => source.ids[index] !== value)) {
					setError("服务器列表已变化，请重新拖动排序。");
					return;
				}
				const next = ids.filter((value) => value !== source.id), index = next.indexOf(source.over.id);
				if (index < 0) return;
				next.splice(index + (source.over.half === "after" ? 1 : 0), 0, source.id);
				if (next.every((value, index) => value === ids[index])) return;
				committing.current = true;
				setPending(true);
				remote.reorderServers(next).catch(() => {
					if (alive.current) setError("服务器排序未保存，请重新拖动重试。");
				}).finally(() => {
					committing.current = false;
					if (alive.current) setPending(false);
				});
			};
			const dragging = drag !== null;
			(0, react.useEffect)(() => {
				if (!enabled) clear();
				if (!enabled || !dragging) return;
				const accept = (event) => {
					if (!current.current) return;
					event.preventDefault();
					const over = target(event.target, event.clientY);
					setOver(over);
					if (event.dataTransfer) event.dataTransfer.dropEffect = over ? "move" : "none";
				};
				const cancel = (event) => {
					if (event.key === "Escape" && current.current) {
						event.preventDefault();
						clear();
					}
				};
				const blur = () => clear();
				document.addEventListener("dragover", accept, true);
				document.addEventListener("drop", accept, true);
				document.addEventListener("keydown", cancel, true);
				window.addEventListener("blur", blur);
				return () => {
					document.removeEventListener("dragover", accept, true);
					document.removeEventListener("drop", accept, true);
					document.removeEventListener("keydown", cancel, true);
					window.removeEventListener("blur", blur);
				};
			}, [
				enabled,
				dragging,
				remote
			]);
			const row = (id, available) => ({
				id,
				enabled: available && !blocked(),
				marker: drag?.over?.id === id ? drag.over.half : void 0,
				pointerDown() {
					if (!current.current) suppressUntil.current = 0;
				},
				consumeClick() {
					if (Date.now() >= suppressUntil.current) return false;
					suppressUntil.current = 0;
					return true;
				},
				start(event) {
					event.stopPropagation();
					if (!available || blocked()) {
						event.preventDefault();
						return;
					}
					const ids = remote.getSnapshot().servers.map((server) => server.id);
					const list = event.currentTarget.closest(".cb-workspace-list");
					if (!ids.includes(id) || !list) {
						event.preventDefault();
						return;
					}
					event.dataTransfer.effectAllowed = "move";
					event.dataTransfer.setData("text/plain", id);
					current.current = {
						id,
						ids,
						list
					};
					setDrag(current.current);
					setError("");
					suppressUntil.current = Infinity;
				},
				over(event) {
					if (!current.current || !available || blocked() || !event.currentTarget.contains(event.target)) return;
					event.preventDefault();
					event.stopPropagation();
					const over = target(event.target, event.clientY);
					event.dataTransfer.dropEffect = over ? "move" : "none";
					setOver(over);
				},
				leave(event) {
					if (!current.current || event.currentTarget.contains(event.relatedTarget)) return;
					if (!event.relatedTarget && event.currentTarget.contains(document.elementFromPoint?.(event.clientX, event.clientY) || null)) return;
					if (current.current.over?.id === id) setOver(void 0);
				},
				drop(event) {
					if (!current.current) return;
					event.preventDefault();
					event.stopPropagation();
					if (!available || blocked() || !event.currentTarget.contains(event.target)) {
						clear();
						return;
					}
					setOver(target(event.target, event.clientY));
					commit();
				},
				end(event) {
					if (event.dataTransfer.dropEffect === "move") commit();
					else clear();
				}
			});
			return {
				row,
				pending,
				error
			};
		}
		function ServerProject({ server, expanded, toggle, remote, modes, snapshot, cache, active, archivedFilter, notices, showArchived, sorting, management = false }) {
			const [tree, setTree] = (0, react.useState)(() => cache.get(server.id) || null);
			const [loading, setLoading] = (0, react.useState)(false), [opening, setOpening] = (0, react.useState)(false), [error, setError] = (0, react.useState)(""), [retry, setRetry] = (0, react.useState)(0);
			const [connectionError, setConnectionError] = (0, react.useState)("");
			const [renaming, setRenaming] = (0, react.useState)(false), [removing, setRemoving] = (0, react.useState)(false), [operating, setOperating] = (0, react.useState)(false);
			const [readRevision, setReadRevision] = (0, react.useState)(0);
			const [closed, setClosed] = (0, react.useState)(/* @__PURE__ */ new Set());
			const alive = (0, react.useRef)(true), revision = (0, react.useRef)(0), mutation = (0, react.useRef)(false);
			const readSequence = (0, react.useRef)(0), reading = (0, react.useRef)(false), startupDeadline = (0, react.useRef)(0);
			const connectingThisServer = snapshot.busy && snapshot.selectedServerId === server.id;
			const acceptTree = (next) => {
				cache.set(server.id, next);
				setTree(next);
				setError("");
				setReadRevision((value) => value + 1);
			};
			(0, react.useEffect)(() => {
				alive.current = true;
				return () => {
					alive.current = false;
				};
			}, []);
			(0, react.useEffect)(() => {
				if (server.connected) return;
				++revision.current;
				++readSequence.current;
				reading.current = false;
				startupDeadline.current = 0;
				cache.delete(server.id);
				setTree(null);
				setLoading(false);
				setError("");
				setConnectionError("");
			}, [
				server.connected,
				server.id,
				cache
			]);
			(0, react.useEffect)(() => {
				if (!expanded || !server.connected) return;
				if (connectingThisServer) {
					setLoading(true);
					return;
				}
				if (!cache.has(server.id) && !startupDeadline.current) startupDeadline.current = Date.now() + 3e4;
				const warming = () => !cache.has(server.id) && Date.now() < startupDeadline.current;
				let active = true, timer;
				const refresh = async () => {
					if (reading.current || mutation.current) {
						timer = setTimeout(() => {
							refresh();
						}, 1e3);
						return;
					}
					const requestRevision = revision.current;
					const request = ++readSequence.current;
					reading.current = true;
					setLoading(true);
					const current = () => active && request === readSequence.current && requestRevision === revision.current && !mutation.current;
					try {
						const next = await remote.getTree(server.id);
						if (current()) acceptTree(next);
					} catch {
						if (current()) setError(warming() ? "" : "无法读取服务器工作区，请检查连接后重试。");
					} finally {
						if (request === readSequence.current) reading.current = false;
						if (active) {
							if (current()) setLoading(warming());
							timer = setTimeout(() => {
								refresh();
							}, warming() ? 2e3 : 5e3);
						}
					}
				};
				refresh();
				return () => {
					active = false;
					clearTimeout(timer);
					++readSequence.current;
					reading.current = false;
				};
			}, [
				remote,
				server.id,
				server.connected,
				expanded,
				retry,
				cache,
				connectingThisServer
			]);
			const refreshList = async () => {
				if (mutation.current) throw new Error("操作尚未完成，请稍后刷新列表。");
				const requestRevision = ++revision.current;
				const request = ++readSequence.current;
				reading.current = true;
				setLoading(true);
				try {
					const next = await remote.getTree(server.id);
					if (!alive.current || request !== readSequence.current || requestRevision !== revision.current || mutation.current) throw new Error("列表读取已被更新的操作替代，请重试刷新。");
					acceptTree(next);
				} catch (reason) {
					if (alive.current && request === readSequence.current && requestRevision === revision.current) setError("无法读取服务器工作区，请检查连接后重试。");
					throw reason;
				} finally {
					if (request === readSequence.current) {
						reading.current = false;
						if (alive.current) setLoading(false);
					}
				}
			};
			const open = (workspaceId, sessionId, createWorkspace) => {
				if (opening || mutation.current || remote.getSnapshot().busy) return;
				setOpening(true);
				setConnectionError("");
				modes.selectServer(server.id);
				remote.open({
					serverId: server.id,
					workspaceId,
					sessionId,
					...createWorkspace ? { createWorkspace: true } : {}
				}).catch(() => {
					if (alive.current) setConnectionError("无法打开远端工作台，请检查连接后重试。");
				}).finally(() => {
					if (alive.current) setOpening(false);
				});
			};
			const connect = () => {
				if (snapshot.busy || opening) return;
				setOpening(true);
				setConnectionError("");
				remote.connect(server.id).catch((reason) => {
					if (alive.current) setConnectionError(reason instanceof Error ? reason.message : "连接失败，请重试。");
				}).finally(() => {
					if (alive.current) setOpening(false);
				});
			};
			const disconnect = () => {
				if (opening || mutation.current || remote.getSnapshot().busy || remote.getSnapshot().disconnectingServerIds?.includes(server.id)) return;
				mutation.current = true;
				++revision.current;
				setOperating(true);
				setConnectionError("");
				remote.disconnect(server.id).catch(() => {
					if (alive.current) setConnectionError("无法断开服务器连接，请重试。");
				}).finally(() => {
					mutation.current = false;
					if (alive.current) setOperating(false);
				});
			};
			const disconnecting = snapshot.disconnectingServerIds?.includes(server.id) === true;
			const connecting = opening || connectingThisServer;
			const target = active && snapshot.target?.serverId === server.id ? snapshot.target : null;
			const label = server.label || server.alias;
			const status = disconnecting ? "断开中" : connecting ? "连接中" : server.connected ? "已连接" : "未连接";
			const action = disconnecting ? `正在断开 ${label}` : connecting ? `正在连接 ${label}` : server.connected ? `断开 ${label}` : `连接 ${label}`;
			const run = async (operation) => {
				if (mutation.current) throw new Error("上一项操作尚未完成，请稍后重试。");
				mutation.current = true;
				revision.current++;
				setOperating(true);
				const operationRevision = revision.current;
				const navigation = remote.getSnapshot().target, mode = modes.getSnapshot();
				try {
					const result = await remote.operate(server.id, operation);
					if (!alive.current || operationRevision !== revision.current || !remote.getSnapshot().servers.some((item) => item.id === server.id && item.connected)) return;
					revision.current++;
					if (alive.current) acceptTree(result.tree);
					if (operation.action === "archive-session" && modes.getSnapshot().mode === "cannbot") notices.archived({
						sessionId: operation.sessionId,
						stopped: operation.stopActivity,
						undo: () => run({
							action: "unarchive-session",
							sessionId: operation.sessionId
						}),
						showArchived
					});
					if (result.sessionId && operation.action === "fork-session" && remote.getSnapshot().target === navigation && modes.getSnapshot().mode === mode.mode && modes.getSnapshot().serverId === mode.serverId) {
						const child = result.tree.sessions.find((session) => session.id === result.sessionId);
						modes.selectServer(server.id);
						await remote.open({
							serverId: server.id,
							workspaceId: child?.workspaceId,
							sessionId: result.sessionId
						});
					}
				} finally {
					mutation.current = false;
					revision.current++;
					if (alive.current) setOperating(false);
				}
			};
			const disabled = snapshot.busy || opening || operating || disconnecting || snapshot.removingServerIds?.includes(server.id) || snapshot.orderingServers || sorting.pending;
			const remove = async () => {
				const state = remote.getSnapshot();
				if (opening || mutation.current || state.busy || state.orderingServers || state.removingServerIds?.includes(server.id) || state.disconnectingServerIds?.includes(server.id)) throw new Error("服务器操作尚未完成，请稍后重试。");
				mutation.current = true;
				++revision.current;
				++readSequence.current;
				reading.current = false;
				setOperating(true);
				try {
					await remote.removeServer(server.id);
					cache.delete(server.id);
				} finally {
					mutation.current = false;
					if (alive.current) setOperating(false);
				}
			};
			if (!management) return server.connected ? /* @__PURE__ */ (0, react_jsx_runtime.jsxs)(react_jsx_runtime.Fragment, { children: [
				connectionError && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", {
					role: "alert",
					className: "cb-sidebar-error",
					children: connectionError
				}),
				error && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("p", {
					role: "alert",
					className: "cb-sidebar-error",
					children: [
						label,
						"：",
						error,
						" ",
						/* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
							type: "button",
							onClick: () => {
								startupDeadline.current = 0;
								setError("");
								setRetry((value) => value + 1);
							},
							children: "重试"
						})
					]
				}),
				loading && !tree && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("p", {
					role: "status",
					className: "cb-empty",
					children: [
						"正在加载 ",
						label,
						" 的工作区…"
					]
				}),
				/* @__PURE__ */ (0, react_jsx_runtime.jsx)(WorkspaceRows, {
					remoteLabel: label,
					workspaces: tree?.workspaces || [],
					sessions: tree?.sessions || [],
					activeSessionId: target?.sessionId,
					currentBlankId: snapshot.target?.serverId === server.id ? snapshot.target.sessionId : void 0,
					activeWorkspaceId: target?.workspaceId,
					closed,
					toggle: (id) => setClosed((previous) => toggleSet(previous, id)),
					open: (session) => {
						if (session.archived) notices.archivedNotOpenable();
						else open(session.workspaceId, session.id);
					},
					create: (id) => open(id),
					run,
					disabled,
					archivedFilter,
					copyFeedback: (ok) => {
						if (modes.getSnapshot().mode === "cannbot") notices.copied(ok);
					},
					readback: {
						revision: readRevision,
						refresh: refreshList
					}
				})
			] }) : null;
			return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)(react_jsx_runtime.Fragment, { children: [
				/* @__PURE__ */ (0, react_jsx_runtime.jsx)(ProjectRow, {
					title: label,
					expanded: false,
					expandable: false,
					toggle,
					selected: !!target,
					drag: sorting.row(server.id, !disabled && !renaming && !removing),
					icon: /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.IconFollowsystemOutlineRegular, { size: 16 }),
					accessory: /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
						className: "cb-server-actions",
						children: [
							/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
								className: "cb-server-status",
								role: "status",
								children: status
							}),
							/* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.Tooltip, {
								label: `${status} · ${action}`,
								side: "bottom",
								delayMs: 500,
								portal: true,
								children: /* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
									className: "cb-connection-action",
									type: "button",
									"aria-label": action,
									disabled,
									onClick: () => server.connected ? disconnect() : connect(),
									children: /* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
										"aria-hidden": "true",
										className: connecting || disconnecting ? "cb-connection-pending" : void 0,
										children: connecting || disconnecting ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.IconRefreshOutlineRegular, { size: 16 }) : server.connected ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.IconCheckOutlineRegular, { size: 16 }) : /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.IconLinkOutlineRegular, { size: 16 })
									})
								})
							}),
							/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("span", {
								className: "cb-row-actions",
								children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)(MoreMenu, {
									label: `${label}的服务器操作`,
									disabled,
									children: (close) => /* @__PURE__ */ (0, react_jsx_runtime.jsxs)(react_jsx_runtime.Fragment, { children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.MenuItemButton, {
										icon: /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.IconEditOutlineRegular, { size: 16 }),
										onSelect: () => {
											close();
											setRenaming(true);
										},
										children: "编辑备注"
									}), /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.MenuItemButton, {
										danger: true,
										icon: /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.IconTrashOutlineRegular, { size: 16 }),
										onSelect: () => {
											close();
											setRemoving(true);
										},
										children: "删除服务器"
									})] })
								}), /* @__PURE__ */ (0, react_jsx_runtime.jsx)(NewWorkspaceAction, {
									workspace: true,
									label: `在 ${label} 上添加工作区`,
									onClick: () => modes.setCreating(true, server.id),
									disabled: !server.connected || disabled
								})]
							})
						]
					})
				}),
				connectionError && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("p", {
					role: "alert",
					className: "cb-sidebar-error",
					children: [
						connectionError,
						" ",
						/* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
							type: "button",
							onClick: () => server.connected ? disconnect() : connect(),
							children: "重试"
						})
					]
				}),
				renaming && /* @__PURE__ */ (0, react_jsx_runtime.jsx)(RenameDialog, {
					title: "编辑服务器备注",
					field: "服务器备注",
					description: `SSH 服务器：${server.alias}。清空备注后显示 SSH 名称，不会修改连接配置。`,
					initial: server.label,
					allowEmpty: true,
					actionLabel: "保存",
					maxLength: 120,
					save: (value) => remote.renameServer(server.id, value),
					close: () => setRenaming(false)
				}),
				removing && /* @__PURE__ */ (0, react_jsx_runtime.jsx)(ConfirmAction, {
					title: "删除服务器",
					description: `将把“${label}”从本机服务器列表中移除，并断开本机 SSH 隧道。远端文件、会话和运行中的任务会保留，SSH 配置不会修改。`,
					action: "删除服务器",
					pending: "正在删除服务器…",
					confirm: remove,
					close: () => setRemoving(false)
				})
			] });
		}
		function ModeWorkspaceTree({ ctx, modes, remote, wide = true, management = false }) {
			const state = useStore(modes), remoteState = useStore(remote);
			const sorting = useServerReorder(remote, state.mode === "cannbot" && management && wide && !modes.embedded);
			const panel = useStore(ctx.layout.panelInfo);
			const workspaceState = useStore(ctx.workspaces.list);
			const sessionState = useStore(ctx.sessions.list);
			const cache = (0, react.useRef)(/* @__PURE__ */ new Map());
			const [closed, setClosed] = (0, react.useState)(/* @__PURE__ */ new Set());
			const [archivedFilter, setArchivedFilter] = (0, react.useState)("default");
			const notices = (0, react.useMemo)(createSidebarNotices, []);
			(0, react.useEffect)(() => () => notices.dispose(), [notices]);
			(0, react.useEffect)(() => {
				if (state.mode !== "cannbot") notices.clear();
			}, [notices, state.mode]);
			(0, react.useEffect)(() => {
				if (modes.embedded && wide) ctx.layout.toggleSidebar();
			}, [
				ctx,
				modes,
				wide
			]);
			const [localReadRevision, setLocalReadRevision] = (0, react.useState)(0);
			(0, react.useEffect)(() => {
				if (state.ready && !state.error) setLocalReadRevision((value) => value + 1);
			}, [
				state.workspaces,
				state.sessions,
				state.ready,
				state.error
			]);
			const liveWorkspaces = new Map(workspaceState.items.map((item) => [item.workspaceId, item]));
			const workspaces = state.ready ? state.workspaces.filter((item) => workspaceState.phase !== "ready" || liveWorkspaces.has(item.workspaceId)).map((item) => ({
				...item,
				title: liveWorkspaces.get(item.workspaceId)?.title || item.title
			})) : [];
			const archived = new Set(workspaceState.archivedSessionIds);
			const pins = workspaceState.pinnedSessionIds || [];
			const summaries = sessionState.byId;
			const sessions = !state.ready ? [] : state.sessions.filter((item) => summaries[item.sessionId]?.origin !== "subagent").map((item) => ({
				...item,
				id: item.sessionId,
				title: summaries[item.sessionId]?.title || item.title || "新会话",
				updatedAt: summaries[item.sessionId]?.updatedAt || item.updatedAt,
				blank: summaries[item.sessionId]?.blank ?? item.blank,
				running: summaries[item.sessionId]?.running ?? item.running,
				archived: workspaceState.phase === "ready" ? archived.has(item.sessionId) : item.archived,
				pinned: pins.includes(item.sessionId),
				pinOrder: pins.indexOf(item.sessionId)
			}));
			const currentBlankId = Object.values(summaries).find((summary) => summary.retainedBy?.mainView)?.id;
			const local = (action) => {
				if (state.serverId) remote.returnLocal();
				action();
			};
			const open = (session) => {
				if (session.archived) notices.archivedNotOpenable();
				else local(() => modes.openSession(session.id));
			};
			const create = (id) => local(() => modes.newSession(id));
			const add = () => modes.setCreating(true);
			const runLocal = async (operation) => {
				const announceArchive = () => {
					if (operation.action === "archive-session" && modes.getSnapshot().mode === "cannbot") notices.archived({
						sessionId: operation.sessionId,
						stopped: operation.stopActivity,
						undo: () => runLocal({
							action: "unarchive-session",
							sessionId: operation.sessionId
						}),
						showArchived: () => setArchivedFilter("only")
					});
				};
				switch (operation.action) {
					case "rename-workspace":
						await ctx.workspaces.rename(operation.workspaceId, operation.title);
						break;
					case "remove-workspace": {
						const before = modes.getSnapshot(), beforePanel = ctx.layout.panelInfo.getSnapshot().activePanelId;
						await ctx.workspaces.delete(operation.workspaceId);
						const after = modes.getSnapshot();
						if (before.mode === "cannbot" && after.mode === "cannbot" && !before.serverId && !after.serverId && before.selectedWorkspaceId === operation.workspaceId && after.selectedWorkspaceId === operation.workspaceId && before.activeSessionId === after.activeSessionId && ctx.layout.panelInfo.getSnapshot().activePanelId === beforePanel) {
							modes.selectWorkspace("");
							modes.newSession();
						}
						break;
					}
					case "rename-session":
						if (!(await ctx.sessions.using(operation.sessionId, { source: "workspaceOperation" }, (reference) => reference.binding.session.rename(operation.title))).ok) throw new Error("重命名未完成，请重试。");
						break;
					case "pin-session":
						await ctx.uiWorkspace.pinSession(operation.sessionId);
						break;
					case "unpin-session":
						await ctx.uiWorkspace.unpinSession(operation.sessionId);
						break;
					case "archive-session":
						if (modes.getSnapshot().serverId) {
							await modes.operate(operation);
							announceArchive();
							return;
						}
						await ctx.uiWorkspace.archiveSession(operation.sessionId, operation.stopActivity ? { stopActivity: true } : void 0);
						break;
					case "unarchive-session":
						await ctx.uiWorkspace.unarchiveSession(operation.sessionId);
						break;
					case "fork-session": {
						const before = modes.getSnapshot(), beforePanel = ctx.layout.panelInfo.getSnapshot().activePanelId;
						const result = await modes.operate(operation), after = modes.getSnapshot();
						if (result.sessionId && before.mode === after.mode && before.serverId === after.serverId && before.activeSessionId === after.activeSessionId && before.selectedWorkspaceId === after.selectedWorkspaceId && ctx.layout.panelInfo.getSnapshot().activePanelId === beforePanel) local(() => modes.openSession(result.sessionId));
						return;
					}
				}
				await modes.refreshAfterOperation();
				announceArchive();
			};
			const localReadback = {
				revision: localReadRevision,
				refresh: async () => {
					await modes.refreshAfterOperation();
					const error = modes.getSnapshot().error;
					if (error) throw new Error(error);
				}
			};
			const localRows = /* @__PURE__ */ (0, react_jsx_runtime.jsx)(WorkspaceRows, {
				workspaces,
				allWorkspaces: workspaceState.items,
				sessions,
				currentBlankId,
				activeSessionId: !state.serverId && panel.activePanelId === null ? state.activeSessionId : void 0,
				activeWorkspaceId: !state.serverId ? state.selectedWorkspaceId : void 0,
				closed,
				toggle: (id) => setClosed((previous) => toggleSet(previous, id)),
				open,
				create,
				run: runLocal,
				readback: localReadback,
				archivedFilter,
				copyFeedback: (ok) => {
					if (modes.getSnapshot().mode === "cannbot") notices.copied(ok);
				}
			});
			if (modes.embedded || state.mode !== "cannbot") return null;
			if (!wide) return /* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
				className: "cb-icon-button",
				"aria-label": "展开工作区列表",
				onClick: () => ctx.layout.toggleSidebar(),
				children: /* @__PURE__ */ (0, react_jsx_runtime.jsx)(WorkbenchIcon, { name: "folder" })
			});
			return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("section", {
				className: `cb-workspaces${management ? " cb-server-page" : ""}`,
				"aria-label": management ? "服务器管理" : "CANNBot工作区",
				children: [
					/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
						className: "cb-workspaces-heading",
						children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("h2", { children: management ? "服务器" : "工作区" }), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
							className: "cb-heading-actions",
							children: management ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.Tooltip, {
								label: "新增服务器",
								side: "bottom",
								align: "end",
								delayMs: 500,
								portal: true,
								children: /* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
									type: "button",
									className: "cb-add-server",
									"aria-label": "新增服务器",
									onClick: () => remote.showConnections(),
									children: /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.IconPlusOutlineRegular, { size: 16 })
								})
							}) : /* @__PURE__ */ (0, react_jsx_runtime.jsxs)(react_jsx_runtime.Fragment, { children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)(ArchivedViewMenu, {
								value: archivedFilter,
								change: setArchivedFilter
							}), /* @__PURE__ */ (0, react_jsx_runtime.jsx)(NewWorkspaceAction, {
								workspace: true,
								label: "添加工作区",
								onClick: add
							})] })
						})]
					}),
					management && remoteState.error && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", {
						role: "alert",
						className: "cb-sidebar-error",
						children: remoteState.error
					}),
					management && remoteState.busy && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", {
						role: "status",
						className: "cb-empty",
						children: remoteState.progress.at(-1) || "正在连接服务器…"
					}),
					state.error && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("p", {
						role: "alert",
						className: "cb-sidebar-error",
						children: [
							state.error,
							" ",
							/* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
								type: "button",
								onClick: () => void modes.refresh(),
								children: "重试"
							})
						]
					}),
					sorting.pending && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", {
						role: "status",
						className: "cb-empty",
						children: "正在保存服务器顺序…"
					}),
					sorting.error && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", {
						role: "alert",
						className: "cb-sidebar-error",
						children: sorting.error
					}),
					/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
						className: "cb-workspace-list",
						children: [
							!management && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)(react_jsx_runtime.Fragment, { children: [!state.ready && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", {
								role: "status",
								className: "cb-empty",
								children: "正在加载工作区…"
							}), localRows] }),
							remoteState.servers.map((server) => /* @__PURE__ */ (0, react_jsx_runtime.jsx)(ServerProject, {
								management,
								server,
								expanded: !management,
								toggle: () => {},
								remote,
								modes,
								snapshot: remoteState,
								cache: cache.current,
								active: state.serverId === server.id,
								archivedFilter,
								notices,
								showArchived: () => setArchivedFilter("only"),
								sorting
							}, server.id)),
							management && !remoteState.servers.length && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", {
								className: "cb-empty",
								children: "尚未添加服务器。"
							})
						]
					}),
					/* @__PURE__ */ (0, react_jsx_runtime.jsx)(SidebarNotice, {
						notices,
						archivedVisible: archivedFilter !== "default"
					})
				]
			});
		}
		function SessionRow({ session, active, open, run, disabled, readback, copyFeedback }) {
			const [renameRequest, setRenameRequest] = (0, react.useState)(0), [now, setNow] = (0, react.useState)(Date.now);
			(0, react.useEffect)(() => {
				const timer = setInterval(() => setNow(Date.now()), 3e4);
				return () => clearInterval(timer);
			}, []);
			const at = timestamp(session.updatedAt), time = (0, _deepseek_ai_dsh_client_ui_primitives.relativeTime)(at, now);
			const units = {
				minutes: "分钟",
				hours: "小时",
				days: "天",
				months: "个月",
				years: "年"
			};
			const label = session.blank ? "新会话" : session.title;
			return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
				className: `cb-session-row${session.archived ? " cb-session-archived" : ""}`,
				"data-session-id": session.id,
				children: [
					/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("button", {
						type: "button",
						className: "cb-session",
						"aria-current": active ? "page" : void 0,
						onClick: open,
						title: label,
						disabled,
						"aria-description": session.archived ? "已归档对话暂时无法查看，请取消归档后查看" : void 0,
						children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
							className: "cb-leading",
							children: !session.blank && !session.archived && session.running && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
								"aria-label": "进行中",
								children: /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.StateDot, { state: "ongoing" })
							})
						}), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
							className: "cb-session-title",
							onDoubleClick: session.blank ? void 0 : (event) => {
								event.stopPropagation();
								setRenameRequest((value) => value + 1);
							},
							children: label
						})]
					}),
					!session.blank && at > 0 && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
						className: "cb-session-time",
						children: time.unit === "now" ? "刚刚" : `${time.n}${units[time.unit]}`
					}),
					session.pinned && !session.archived && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
						className: "cb-session-pin",
						role: "img",
						"aria-label": "已置顶",
						title: "已置顶",
						children: /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.IconPinFillRegular, { size: 14 })
					}),
					/* @__PURE__ */ (0, react_jsx_runtime.jsx)(SessionActions, {
						session,
						run,
						disabled,
						readback,
						renameRequest,
						copyFeedback
					})
				]
			});
		}
		/** Keep initialization available in embedded remote pages, whose sidebar is hidden. */
		function ModeWorkspaceCreation({ modes, content, remote }) {
			const state = useStore(modes), catalog = useStore(content);
			return state.creating ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)(CreateWorkspace, {
				modes,
				remote,
				workflows: catalog.workflows,
				close: () => modes.setCreating(false)
			}) : null;
		}
		// src/client/remote/native-guest.mjs
		function remoteUrl(value) {
			let url;
			try {
				url = new URL(value);
			} catch {
				throw new Error("远程工作台地址无效，请重新连接。");
			}
			if (!/^https?:$/.test(url.protocol) || ![
				"localhost",
				"127.0.0.1",
				"[::1]"
			].includes(url.hostname) || url.username || url.password) throw new Error("远程工作台必须使用本机 SSH 隧道地址，请重新连接。");
			return url.href;
		}
		function desktopBrowser() {
			const desktop = window.dshDesktop;
			if (desktop?.protocolVersion !== 1 || typeof desktop.browser?.acquire !== "function" || typeof desktop.browser?.release !== "function") throw new Error("当前环境不支持 DSH 原生内嵌浏览器，请使用桌面版 DSH。");
			return desktop.browser;
		}
		function createNativeGuest(options) {
			const bridge = options.bridge;
			const host = options.host;
			const target = remoteUrl(options.url);
			const origin = new URL(target).origin;
			const pathname = new URL(target).pathname;
			const lifetime = new AbortController();
			let disposed = false;
			let element = null;
			let lease = null;
			let ready = false;
			let initialNavigation = false;
			let loadFailed = false;
			let unsubscribeOpen = null;
			let timeout = null;
			let disposal = null;
			const releases = /* @__PURE__ */ new Map();
			function report(value) {
				if (!disposed) options.onState?.(value);
			}
			let lastCreation = null;
			function observeLocation(inPage = false) {
				if (disposed || !ready || !initialNavigation || !element) return;
				try {
					const address = new URL(element.getURL());
					if (address.origin !== origin || address.pathname !== pathname || address.username || address.password) return;
					const params = new URLSearchParams(address.hash.slice(1));
					if (params.get("cannEmbed") !== "1" || params.get("cannMode") !== "cannbot") return;
					const creation = params.get("cannNewFolder");
					if (inPage && creation && /^[a-f0-9-]{36}$/i.test(creation) && creation !== lastCreation) {
						lastCreation = creation;
						options.onCreateWorkspace?.();
					}
					const workspaceId = params.get("cannWorkspace") || void 0;
					const sessionId = params.get("cannSession") || void 0;
					if ([workspaceId, sessionId].some((value) => value && (value.length > 512 || /[\u0000-\u0020]/.test(value)))) return;
					if (sessionId && !workspaceId) return;
					options.onLocation?.({
						workspaceId,
						sessionId
					});
				} catch {}
			}
			function clearTimer() {
				if (timeout !== null) {
					clearTimeout(timeout);
					timeout = null;
				}
			}
			function failed() {
				loadFailed = true;
				clearTimer();
				report({
					status: "error",
					error: "远端页面加载失败，请检查连接后重试。"
				});
			}
			function loading() {
				loadFailed = false;
				clearTimer();
				report({
					status: "loading",
					error: "",
					notice: ""
				});
				timeout = setTimeout(failed, 3e4);
			}
			function release(id) {
				if (!id) return Promise.resolve();
				if (!releases.has(id)) releases.set(id, Promise.resolve().then(function() {
					return bridge.release(id);
				}).catch(function() {}));
				return releases.get(id);
			}
			function removeGuest() {
				clearTimer();
				lifetime.abort();
				if (unsubscribeOpen) {
					try {
						unsubscribeOpen();
					} catch {}
					unsubscribeOpen = null;
				}
				if (element) {
					element.remove();
					element = null;
				}
				ready = false;
				return release(lease);
			}
			function navigate(url) {
				if (disposed || !ready || !element) return;
				loading();
				try {
					Promise.resolve(element.loadURL(url)).catch(function(error) {
						if (!disposed && error?.code !== "ERR_ABORTED") failed();
					});
				} catch {
					failed();
				}
			}
			loading();
			const initializing = Promise.resolve().then(function() {
				return bridge.acquire(options.workspaceKey);
			}).then(async function(reservation) {
				if (reservation && typeof reservation.lease === "string" && reservation.lease) lease = reservation.lease;
				if (!reservation || typeof reservation.lease !== "string" || !reservation.lease || typeof reservation.partition !== "string" || !reservation.partition) throw new Error("invalid reservation");
				if (disposed) {
					await release(reservation.lease);
					return;
				}
				element = (host.ownerDocument || document).createElement("webview");
				element.dataset.sidebarBrowserFrame = "webview";
				element.setAttribute("aria-label", "远端 DSH 工作台");
				element.setAttribute("name", lease);
				element.setAttribute("partition", reservation.partition);
				element.setAttribute("allowpopups", "");
				element.setAttribute("src", "about:blank#" + lease);
				Object.assign(element.style, {
					width: "100%",
					height: "100%",
					display: "flex",
					border: "0"
				});
				const listen = function(name, listener) {
					element.addEventListener(name, listener, { signal: lifetime.signal });
				};
				listen("dom-ready", function() {
					if (disposed) return;
					ready = true;
					if (!initialNavigation) {
						initialNavigation = true;
						navigate(target);
					}
				});
				listen("did-start-loading", function() {
					if (initialNavigation) loading();
				});
				listen("did-finish-load", function() {
					if (!initialNavigation || disposed) return;
					try {
						if (element.getURL().startsWith("about:")) return;
					} catch {
						return;
					}
					clearTimer();
					report({
						status: "ready",
						error: ""
					});
					observeLocation();
				});
				listen("did-navigate-in-page", function(event) {
					if (!event.isMainFrame || !initialNavigation || disposed || !ready) return;
					observeLocation(true);
					clearTimer();
					report({
						status: "ready",
						error: ""
					});
				});
				listen("did-stop-loading", function() {
					if (!initialNavigation || disposed || !ready || loadFailed) return;
					try {
						if (element.getURL().startsWith("about:")) return;
					} catch {
						return;
					}
					clearTimer();
					report({
						status: "ready",
						error: ""
					});
					observeLocation();
				});
				listen("did-fail-load", function(event) {
					if (event.isMainFrame && event.errorCode !== -3) failed();
				});
				listen("render-process-gone", failed);
				if (typeof bridge.onOpenRequested === "function") unsubscribeOpen = bridge.onOpenRequested(lease, function(value) {
					if (disposed) return;
					let url;
					try {
						url = new URL(value);
					} catch {
						return;
					}
					if (url.origin === origin && !url.username && !url.password) navigate(url.href);
					else report({ notice: "此链接指向其他站点，当前工作区保留在远端服务器页面。" });
				});
				host.append(element);
			}).catch(function() {
				if (!disposed) failed();
				return removeGuest();
			});
			return {
				reload: function() {
					if (disposed || !ready || !element) return false;
					loading();
					try {
						element.reload();
						return true;
					} catch {
						failed();
						return false;
					}
				},
				dispose: function() {
					if (disposal) return disposal;
					disposed = true;
					const pendingRelease = removeGuest();
					disposal = Promise.all([pendingRelease, initializing]).then(function() {
						return Promise.all(releases.values());
					}).then(function() {});
					return disposal;
				}
			};
		}
		// \0dsh-global-css:/home/t00607008/cannbot/dsh/src/client/remote/remote.css.mjs
		const css$1 = ".cann-remote-page{min-width:0;height:100%;min-height:0;color:var(--dsw-alias-label-primary);background:var(--dsw-alias-bg-base);flex-direction:column;flex:1;display:flex;position:relative}.cann-remote-guest{flex:1;min-height:0;overflow:hidden}.cann-remote-page>[role=log]{white-space:pre-wrap;flex-shrink:1;min-height:0;max-height:45vh;margin:12px 16px;font-size:12px;overflow:auto}.cann-remote-loading{pointer-events:none;color:var(--dsw-alias-label-secondary);place-items:center;font-size:13px;display:grid;position:absolute;inset:0}.cann-remote-notice{color:var(--dsw-alias-label-secondary);padding:8px 16px;font-size:12px}.cann-remote-page button,.cann-add-server button{font:inherit;border:1px solid var(--dsw-alias-border-l2);border-radius:var(--dsw-radius-md,6px);color:inherit;cursor:pointer;background:0 0;padding:6px 12px}.cann-remote-error{color:var(--dsw-alias-state-error-primary,#c7000b);padding:10px 16px}.cann-add-server{box-sizing:border-box;border:1px solid var(--dsw-alias-border-l2);border-radius:var(--dsw-radius-lg,12px);background:var(--dsw-alias-bg-layer-1,var(--dsw-alias-bg-base));width:min(440px,100vw - 32px);max-height:calc(100vh - 48px);color:var(--dsw-alias-label-primary);font:inherit;box-shadow:var(--dsw-shadow-modal,0 12px 48px #0002);margin:auto;padding:20px;overflow:auto}.cann-add-server::backdrop{background:var(--dsw-alias-bg-mask-1,#0006)}.cann-add-server header{justify-content:space-between;align-items:center;gap:12px;display:flex}.cann-add-server h2{margin:0;font-size:16px;font-weight:500}.cann-add-server p{color:var(--dsw-alias-label-secondary);margin:8px 0 16px;font-size:12px;line-height:1.6}.cann-add-server .cann-add-close{width:24px;height:24px;color:var(--dsw-alias-label-secondary);border:0;padding:0;font-size:22px}.cann-add-field{color:var(--dsw-alias-label-secondary);flex-direction:column;gap:7px;margin:14px 0;font-size:12px;display:flex}.cann-add-field input{box-sizing:border-box;border:1px solid var(--dsw-alias-border-l2);border-radius:var(--dsw-radius-md,6px);background:var(--dsw-alias-bg-base);width:100%;color:var(--dsw-alias-label-primary);font:inherit;padding:8px 10px;font-size:13px}.cann-add-sync{align-items:center;gap:7px;margin:16px 0;font-size:12px;display:flex}.cann-add-sync input{accent-color:var(--dsw-alias-brand-primary)}.cann-add-server footer{justify-content:flex-end;gap:8px;margin-top:20px;display:flex}.cann-add-server .cann-add-submit{background:var(--dsw-alias-brand-primary);color:var(--dsw-alias-label-primary-inverted,#fff);border-color:#0000}.cann-add-server .cann-add-error{color:var(--dsw-alias-state-error-primary,#c7000b);overflow-wrap:anywhere}.cann-add-server button:disabled{cursor:default;opacity:.5}.cann-add-server .cann-password-identity{overflow-wrap:anywhere;white-space:pre-wrap}.cann-add-server button:focus-visible,.cann-add-field input:focus-visible{outline:2px solid var(--dsw-focus-ring-color);outline-offset:2px}";
		const tagId$1 = "@cannbot-plugin/cannbot-dsh/remote.css";
		if (typeof document !== "undefined" && document.querySelector("style[data-plugin-css=" + JSON.stringify(tagId$1) + "]") === null) {
			const tag = document.createElement("style");
			tag.dataset.plugin = "@cannbot-plugin/cannbot-dsh";
			tag.dataset.pluginCss = tagId$1;
			tag.textContent = css$1;
			document.head.appendChild(tag);
		}
		// src/client/remote/index.tsx
		const PANEL = "cannbot-remote-workbench";
		const HOME = "cannbot-dsh-workbench";
		const endpoint = (path) => new URL("api/cannbot-remote/" + path, document.baseURI);
		const safeMessage = (value) => String(value ?? "").replace(/https?:\/\/[^\s"'<>]+/gi, "[远端地址]").replace(/(token[=:]\s*)[^\s&]+/gi, "$1[已隐藏]");
		function createRemoteClient(ctx, options = {}) {
			let state = {
				servers: [],
				busy: false,
				error: "",
				progress: [],
				syncLogin: true,
				revision: 0,
				target: null,
				status: "idle",
				notice: ""
			};
			const listeners = /* @__PURE__ */ new Set();
			const urls = /* @__PURE__ */ new Map();
			const connecting = /* @__PURE__ */ new Map();
			const attempts = /* @__PURE__ */ new Map();
			const disconnecting = /* @__PURE__ */ new Map();
			const removing = /* @__PURE__ */ new Map();
			const lifetime = new AbortController();
			let disposed = false, started = false, pullSequence = 0, openSequence = 0;
			let serverAdded;
			let timer;
			let guest = null;
			let requestedTarget = null;
			const releases = [];
			const publish = (next) => {
				if (disposed) return;
				state = {
					...state,
					...next
				};
				for (const listener of listeners) listener();
			};
			const inOrder = (servers, ids) => {
				const rank = new Map(ids.map((id, index) => [id, index]));
				return [...servers].sort((left, right) => (rank.get(left.id) ?? ids.length) - (rank.get(right.id) ?? ids.length));
			};
			async function json(path, init) {
				const response = await fetch(endpoint(path), {
					credentials: "same-origin",
					cache: "no-store",
					...init,
					signal: AbortSignal.any([lifetime.signal, AbortSignal.timeout(2e4)])
				});
				const result = await response.json();
				if (!response.ok || result.ok === false) {
					const error = new Error(safeMessage(result.message || result.error || "远程连接请求失败，请重试。"));
					Object.assign(error, {
						code: typeof result.error === "string" ? result.error : "",
						status: response.status,
						...Array.isArray(result.activity) && { activity: result.activity }
					});
					throw error;
				}
				return result;
			}
			async function pull() {
				const sequence = ++pullSequence;
				try {
					const result = await json("servers");
					if (disposed || sequence !== pullSequence || !Array.isArray(result.servers)) return;
					const servers = result.servers.filter((item) => item && typeof item.id === "string" && typeof item.alias === "string").map((item) => {
						if (item.connected && item.url) try {
							urls.set(item.id, remoteUrl(item.url));
						} catch {
							urls.delete(item.id);
						}
						else urls.delete(item.id);
						return {
							id: item.id,
							alias: item.alias,
							label: item.label || item.alias,
							connected: !!item.connected,
							localPort: item.localPort,
							remotePort: item.remotePort,
							loginSync: item.loginSync
						};
					});
					publish({ servers: state.orderingServers ? inOrder(servers, state.servers.map((server) => server.id)) : servers });
				} catch (error) {
					if (!disposed && sequence === pullSequence) publish({ error: safeMessage(error instanceof Error ? error.message : "无法读取服务器列表，请重试。") });
				}
			}
			function stopGuest() {
				const old = guest;
				guest = null;
				if (old) old.dispose();
			}
			function back() {
				++openSequence;
				stopGuest();
				ctx.layout.selectPanel(HOME);
				options.onReturnLocal?.();
			}
			async function disconnectServer(id, remove = false) {
				await connecting.get(id)?.catch(() => {});
				if (disposed) return;
				await json(remove ? "servers/remove" : "disconnect", {
					method: "POST",
					headers: { "content-type": "application/json" },
					body: JSON.stringify({ id })
				});
				if (disposed) return;
				++pullSequence;
				urls.delete(id);
				const ownsTarget = state.target?.serverId === id, ownsRequest = requestedTarget?.serverId === id;
				const ownsSelection = state.selectedServerId === id;
				const visible = ctx.layout.panelInfo.getSnapshot().activePanelId === PANEL && (ownsTarget || !state.target && ownsRequest && ownsSelection);
				if (ownsTarget) stopGuest();
				if (ownsRequest) requestedTarget = null;
				publish({
					servers: remove ? state.servers.filter((server) => server.id !== id) : state.servers.map((server) => server.id === id ? {
						...server,
						connected: false
					} : server),
					...ownsSelection ? { selectedServerId: void 0 } : {},
					...ownsTarget || ownsRequest ? {
						target: ownsTarget ? null : state.target,
						revision: state.revision + 1,
						status: "idle",
						error: "",
						notice: "",
						progress: []
					} : {}
				});
				if (visible) {
					ctx.layout.selectPanel(HOME);
					options.onReturnLocal?.();
				}
			}
			async function streamConnect(id, attempt) {
				desktopBrowser();
				publish({
					busy: true,
					error: "",
					progress: []
				});
				const address = endpoint("connect-stream");
				address.searchParams.set("id", id);
				address.searchParams.set("syncLogin", state.syncLogin ? "1" : "0");
				address.searchParams.set("requestId", attempt.requestId);
				let reader;
				let done = false;
				try {
					const response = await fetch(address, {
						credentials: "same-origin",
						cache: "no-store",
						signal: AbortSignal.any([lifetime.signal, attempt.controller.signal])
					});
					if (!response.ok || !response.body) throw new Error("无法建立远程连接，请重试。");
					reader = response.body.getReader();
					const decoder = new TextDecoder();
					let buffer = "";
					while (!disposed) {
						const chunk = await reader.read();
						if (chunk.done) break;
						buffer += decoder.decode(chunk.value, { stream: true }).replace(/\r/g, "");
						let boundary;
						while ((boundary = buffer.indexOf("\n\n")) >= 0) {
							const block = buffer.slice(0, boundary);
							buffer = buffer.slice(boundary + 2);
							const data = block.split("\n").filter((line) => line.startsWith("data:")).map((line) => line.slice(5).trimStart()).join("\n");
							if (!data) continue;
							const event = JSON.parse(data);
							if (event.phase === "password" && typeof event.challengeId === "string" && typeof event.prompt === "string") publish({ passwordRequests: [...(state.passwordRequests || []).filter((item) => item.serverId !== id), {
								serverId: id,
								challengeId: event.challengeId,
								prompt: event.prompt,
								retry: !!event.retry
							}] });
							if (event.phase === "error" || event.ok === false) throw new Error(safeMessage(event.message || event.error || "连接失败，请重试。"));
							if (event.message) publish({ progress: [...state.progress.slice(-79), safeMessage(event.message)] });
							if (event.phase === "done") {
								if (!event.ok || typeof event.url !== "string") throw new Error("远端未返回可用工作台，请重新连接。");
								urls.set(id, remoteUrl(event.url));
								done = true;
							}
						}
					}
					if (!done && !disposed) throw new Error("连接在完成前中断，请重新连接。");
					if (!attempt.cancelling) await pull();
				} catch (error) {
					const message = safeMessage(error instanceof Error ? error.message : "远程连接失败，请重试。");
					if (!attempt.cancelling) publish({ error: message });
					throw new Error(message);
				} finally {
					if (reader) try {
						await reader.cancel();
					} catch {}
					publish({
						busy: false,
						passwordRequests: (state.passwordRequests || []).filter((item) => item.serverId !== id)
					});
				}
			}
			function attach(host) {
				const target = state.target, revision = state.revision;
				if (!target || disposed) return () => {};
				stopGuest();
				const initial = urls.get(target.serverId);
				if (!initial) {
					publish({
						status: "error",
						error: "请重新连接服务器后打开工作台。"
					});
					return () => {};
				}
				const address = new URL(initial);
				const fragment = new URLSearchParams({
					cannEmbed: "1",
					cannMode: "cannbot"
				});
				if (target.createWorkspace) fragment.set("cannCreateWorkspace", "1");
				else {
					if (target.workspaceId) fragment.set("cannWorkspace", target.workspaceId);
					if (target.recommendPermissions) fragment.set("cannRecommendPermissions", "1");
					if (target.sessionId) fragment.set("cannSession", target.sessionId);
				}
				address.hash = fragment.toString();
				try {
					let current;
					current = createNativeGuest({
						bridge: desktopBrowser(),
						host,
						url: address.href,
						workspaceKey: "cannbot-remote:" + target.serverId,
						onState: (next) => {
							if (current && guest === current && state.revision === revision) publish(next);
						},
						onCreateWorkspace: () => {
							if (current && guest === current && state.revision === revision) options.onCreateWorkspace?.(target.serverId);
						},
						onLocation: (scope) => {
							if (!current || guest !== current || state.revision !== revision) return;
							const next = {
								serverId: target.serverId,
								...scope
							};
							requestedTarget = next;
							if (state.target?.workspaceId !== next.workspaceId || state.target?.sessionId !== next.sessionId || state.target?.createWorkspace) publish({ target: next });
						}
					});
					guest = current;
					const mounted = current;
					return () => {
						if (guest === mounted) guest = null;
						mounted.dispose();
					};
				} catch {
					publish({
						status: "error",
						error: "当前桌面环境无法打开内嵌工作台，请重新连接。"
					});
					return () => {};
				}
			}
			function reload() {
				if (!state.target && requestedTarget) {
					client.open(requestedTarget).catch(() => {});
					return;
				}
				if (state.status !== "error" && guest?.reload()) return;
				stopGuest();
				publish({
					revision: state.revision + 1,
					error: "",
					status: "loading",
					notice: ""
				});
			}
			const client = {
				getSnapshot: () => state,
				subscribe(listener) {
					listeners.add(listener);
					return () => {
						listeners.delete(listener);
					};
				},
				start() {
					if (started || disposed) return () => {};
					started = true;
					releases.push(injectSlot(ctx, "main", () => ctx.slots.register({
						name: "main",
						key: PANEL
					}, () => (0, react.createElement)(RemotePage, {
						client,
						attach,
						reload
					}))));
					releases.push(injectSlot(ctx, "shell.overlay", () => ctx.slots.register({
						name: "shell.overlay",
						id: "cannbot-ssh-password"
					}, () => (0, react.createElement)(PasswordPrompt, {
						client,
						submit: async (serverId, challengeId, password) => {
							const attempt = attempts.get(serverId);
							if (!attempt || attempt.cancelling) throw new Error("连接已取消，请重新连接。");
							await json("password", {
								method: "POST",
								headers: { "content-type": "application/json" },
								body: JSON.stringify({
									id: serverId,
									requestId: attempt.requestId,
									challengeId,
									password
								})
							});
							publish({ passwordRequests: (state.passwordRequests || []).filter((item) => item.challengeId !== challengeId) });
						}
					}))));
					releases.push(injectSlot(ctx, "shell.overlay", () => ctx.slots.register({
						name: "shell.overlay",
						id: "cannbot-add-server"
					}, () => (0, react.createElement)(AddServer, {
						client,
						close: () => {
							serverAdded = void 0;
							publish({ addingServer: false });
						},
						setSync: (value) => publish({ syncLogin: value }),
						save: async (command, label) => {
							desktopBrowser();
							const result = await json("servers", {
								method: "POST",
								headers: { "content-type": "application/json" },
								body: JSON.stringify({
									command,
									...label && { label }
								})
							});
							if (typeof result.server?.id !== "string" || !result.server.id) throw new Error("服务器已保存，但未返回可用标识，请重新打开新增服务器。");
							await pull();
							const onAdded = serverAdded;
							serverAdded = void 0;
							publish({ addingServer: false });
							if (onAdded) {
								onAdded(result.server.id);
								client.connect(result.server.id).catch(() => {});
								return;
							}
							options.onSelectServer?.(result.server.id);
							client.open({ serverId: result.server.id }).catch(() => {});
						}
					}))));
					releases.push(ctx.layout.panelInfo.subscribe(() => {
						if (ctx.layout.panelInfo.getSnapshot().activePanelId !== PANEL) {
							++openSequence;
							stopGuest();
						} else if (state.status === "idle" && !state.target && !requestedTarget) {
							ctx.layout.selectPanel(HOME);
							options.onReturnLocal?.();
						}
					}));
					const tick = async () => {
						await pull();
						if (!disposed) timer = setTimeout(() => {
							tick();
						}, 5e3);
					};
					tick();
					return () => client.dispose();
				},
				connect(id) {
					if (removing.has(id)) return Promise.reject(/* @__PURE__ */ new Error("服务器正在删除，请完成后再操作。"));
					if (disconnecting.has(id)) return Promise.reject(/* @__PURE__ */ new Error("服务器正在断开，请完成后再连接。"));
					const running = connecting.get(id);
					if (running) return running;
					const attempt = {
						controller: new AbortController(),
						requestId: crypto.randomUUID(),
						cancelling: false
					};
					attempts.set(id, attempt);
					const task = streamConnect(id, attempt).finally(() => {
						connecting.delete(id);
					});
					connecting.set(id, task);
					return task;
				},
				async cancelConnect(id) {
					const attempt = attempts.get(id);
					if (!attempt) return;
					attempt.cancelling = true;
					try {
						await json("cancel-connect", {
							method: "POST",
							headers: { "content-type": "application/json" },
							body: JSON.stringify({
								id,
								requestId: attempt.requestId
							})
						});
						attempt.controller.abort();
						await connecting.get(id)?.catch(() => {});
						++pullSequence;
						urls.delete(id);
						publish({
							busy: false,
							error: "",
							progress: [],
							servers: state.servers.map((server) => server.id === id ? {
								...server,
								connected: false
							} : server)
						});
					} catch (error) {
						attempt.cancelling = false;
						throw error;
					}
				},
				disconnect(id) {
					if (removing.has(id)) return removing.get(id);
					const pending = disconnecting.get(id);
					if (pending) return pending;
					if (disposed) return Promise.reject(/* @__PURE__ */ new Error("远程连接组件已关闭。"));
					if (requestedTarget?.serverId === id || state.target?.serverId === id) ++openSequence;
					++pullSequence;
					const task = disconnectServer(id).catch((error) => {
						if (!disposed && !state.target && requestedTarget?.serverId === id && ctx.layout.panelInfo.getSnapshot().activePanelId === PANEL) publish({
							status: "error",
							error: "断开连接未完成，请重试打开工作台。"
						});
						throw error;
					}).finally(() => {
						disconnecting.delete(id);
						publish({ disconnectingServerIds: [...disconnecting.keys()] });
					});
					disconnecting.set(id, task);
					publish({ disconnectingServerIds: [...disconnecting.keys()] });
					return task;
				},
				removeServer(id) {
					const pending = removing.get(id);
					if (pending) return pending;
					if (disposed) return Promise.reject(/* @__PURE__ */ new Error("远程连接组件已关闭。"));
					if (state.orderingServers) return Promise.reject(/* @__PURE__ */ new Error("服务器顺序正在保存，请稍后重试。"));
					if (requestedTarget?.serverId === id || state.target?.serverId === id) ++openSequence;
					++pullSequence;
					const task = (async () => {
						await disconnecting.get(id);
						await disconnectServer(id, true);
					})().catch((error) => {
						if (!disposed && !state.target && requestedTarget?.serverId === id && ctx.layout.panelInfo.getSnapshot().activePanelId === PANEL) publish({
							status: "error",
							error: "删除服务器未完成，请重试打开工作台。"
						});
						throw error;
					}).finally(() => {
						removing.delete(id);
						publish({ removingServerIds: [...removing.keys()] });
					});
					removing.set(id, task);
					publish({ removingServerIds: [...removing.keys()] });
					return task;
				},
				async reorderServers(ids) {
					if (disposed) throw new Error("远程连接组件已关闭。");
					if (state.orderingServers || removing.size) throw new Error("服务器列表正在更新，请稍后重试。");
					if (new Set(ids).size !== ids.length || ids.some((id) => !state.servers.some((server) => server.id === id))) throw new Error("服务器列表已变化，请刷新后重新排序。");
					const previous = state.servers.map((server) => server.id);
					if (ids.length === previous.length && ids.every((id, index) => id === previous[index])) return;
					++pullSequence;
					publish({
						orderingServers: true,
						servers: inOrder(state.servers, ids)
					});
					try {
						const result = await json("servers/order", {
							method: "POST",
							headers: { "content-type": "application/json" },
							body: JSON.stringify({ ids })
						});
						++pullSequence;
						const saved = Array.isArray(result.ids) && result.ids.every((id) => typeof id === "string") ? result.ids : ids;
						publish({ servers: inOrder(state.servers, saved) });
					} catch (error) {
						++pullSequence;
						publish({ servers: inOrder(state.servers, previous) });
						throw error;
					} finally {
						publish({ orderingServers: false });
					}
				},
				async getTree(id) {
					const result = await json("tree?id=" + encodeURIComponent(id));
					if (result.mode !== "cannbot" || !Array.isArray(result.workspaces) || !Array.isArray(result.sessions)) throw new Error("远端 CANNBot 版本不支持工作区列表，请重新连接以更新插件。");
					return {
						workspaces: result.workspaces,
						sessions: result.sessions.map((item) => ({
							id: item.sessionId || item.id || "",
							workspaceId: item.workspaceId,
							title: item.title || "新会话",
							updatedAt: item.updatedAt,
							pinned: item.pinned === true,
							archived: item.archived === true,
							ungrouped: item.ungrouped === true,
							...typeof item.blank === "boolean" ? { blank: item.blank } : {},
							...typeof item.running === "boolean" ? { running: item.running } : {},
							...Number.isSafeInteger(item.pinOrder) && item.pinOrder >= 0 && { pinOrder: item.pinOrder }
						}))
					};
				},
				async operate(id, operation) {
					const target = state.target;
					const result = await json("tree?id=" + encodeURIComponent(id), {
						method: "POST",
						headers: { "content-type": "application/json" },
						body: JSON.stringify(operation)
					});
					if (target?.serverId === id && (operation.action === "remove-workspace" && target.workspaceId === operation.workspaceId || operation.action === "archive-session" && target.sessionId === operation.sessionId) && state.target === target) {
						const next = {
							serverId: id,
							...operation.action === "archive-session" && target.workspaceId ? { workspaceId: target.workspaceId } : {}
						};
						requestedTarget = next;
						stopGuest();
						publish({
							target: next,
							revision: state.revision + 1,
							status: "loading",
							error: "",
							notice: ""
						});
					}
					try {
						let tree;
						try {
							tree = await client.getTree(id);
						} catch {
							lifetime.signal.throwIfAborted();
							tree = await client.getTree(id);
						}
						return {
							tree,
							...typeof result.sessionId === "string" ? { sessionId: result.sessionId } : {}
						};
					} catch {
						throw Object.assign(/* @__PURE__ */ new Error("操作已完成，但列表刷新失败。请刷新列表查看结果。"), { committed: true });
					}
				},
				async renameServer(id, label) {
					if (removing.has(id)) throw new Error("服务器正在删除，请完成后再操作。");
					const result = await json("servers/label", {
						method: "POST",
						headers: { "content-type": "application/json" },
						body: JSON.stringify({
							id,
							label
						})
					});
					if (result.server?.id !== id || typeof result.server?.label !== "string") throw new Error("备注已保存，请刷新服务器列表确认。");
					++pullSequence;
					publish({ servers: state.servers.map((server) => server.id === id ? {
						...server,
						label: result.server.label
					} : server) });
				},
				async open(target) {
					if (removing.has(target.serverId)) throw new Error("服务器正在删除，请完成后再打开。");
					if (disconnecting.has(target.serverId)) throw new Error("服务器正在断开，请完成后再打开。");
					const sequence = ++openSequence;
					desktopBrowser();
					requestedTarget = { ...target };
					stopGuest();
					publish({
						selectedServerId: target.serverId,
						target: null,
						revision: state.revision + 1,
						status: "loading",
						error: "",
						notice: ""
					});
					ctx.layout.selectPanel(PANEL);
					try {
						if (!state.servers.find((item) => item.id === target.serverId)?.connected) await client.connect(target.serverId);
						if (disposed || sequence !== openSequence) return;
						if (!urls.has(target.serverId)) await pull();
						if (disposed || sequence !== openSequence) return;
						if (!urls.has(target.serverId)) throw new Error("远端工作台地址不可用，请重新连接。");
					} catch (error) {
						if (!disposed && sequence === openSequence) publish({
							status: "error",
							error: safeMessage(error instanceof Error ? error.message : "远程连接失败，请重试。")
						});
						throw error;
					}
					publish({
						selectedServerId: target.serverId,
						target: { ...target },
						revision: state.revision + 1,
						status: "loading",
						error: "",
						notice: ""
					});
					ctx.layout.selectPanel(PANEL);
				},
				returnLocal: back,
				showConnections(onAdded) {
					serverAdded = onAdded;
					publish({ addingServer: true });
				},
				dispose() {
					if (disposed) return;
					for (const [id, attempt] of attempts) if (connecting.has(id)) fetch(endpoint("cancel-connect"), {
						method: "POST",
						credentials: "same-origin",
						headers: { "content-type": "application/json" },
						body: JSON.stringify({
							id,
							requestId: attempt.requestId
						}),
						signal: AbortSignal.timeout(2e4)
					}).catch(() => {});
					disposed = true;
					serverAdded = void 0;
					++openSequence;
					lifetime.abort();
					clearTimeout(timer);
					stopGuest();
					if (ctx.layout.panelInfo.getSnapshot().activePanelId === PANEL) ctx.layout.selectPanel(HOME);
					for (const release of releases.reverse()) release();
					urls.clear();
					listeners.clear();
				}
			};
			return client;
		}
		function PasswordPrompt({ client, submit }) {
			const state = (0, react.useSyncExternalStore)(client.subscribe, client.getSnapshot), challenge = state.passwordRequests?.[0];
			const dialog = (0, react.useRef)(null), input = (0, react.useRef)(null);
			const [password, setPassword] = (0, react.useState)(""), [error, setError] = (0, react.useState)(""), [busy, setBusy] = (0, react.useState)(false);
			(0, react.useEffect)(() => {
				setPassword("");
				setError("");
				setBusy(false);
				if (challenge) {
					dialog.current?.showModal();
					input.current?.focus();
				}
			}, [challenge?.challengeId]);
			if (!challenge) return null;
			const cancel = async () => {
				setPassword("");
				setBusy(true);
				try {
					await client.cancelConnect(challenge.serverId);
				} catch {
					setError("取消连接未完成，请重试。");
					setBusy(false);
				}
			};
			const save = async () => {
				if (!password || busy) return;
				setBusy(true);
				setError("");
				const answer = password;
				setPassword("");
				try {
					await submit(challenge.serverId, challenge.challengeId, answer);
				} catch {
					setError("密码提交未完成，请重新输入或取消连接。");
					setBusy(false);
				}
			};
			return /* @__PURE__ */ (0, react_jsx_runtime.jsx)("dialog", {
				ref: dialog,
				className: "cann-add-server",
				"aria-labelledby": "cann-password-title",
				onCancel: (event) => {
					event.preventDefault();
					if (!busy) cancel();
				},
				children: /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("form", {
					onSubmit: (event) => {
						event.preventDefault();
						save();
					},
					children: [
						/* @__PURE__ */ (0, react_jsx_runtime.jsx)("header", { children: /* @__PURE__ */ (0, react_jsx_runtime.jsx)("h2", {
							id: "cann-password-title",
							children: "SSH 密码登录"
						}) }),
						/* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", { children: state.servers.find((server) => server.id === challenge.serverId)?.label || challenge.serverId }),
						/* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", {
							className: "cann-password-identity",
							children: challenge.prompt
						}),
						challenge.retry && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", {
							role: "alert",
							className: "cann-add-error",
							children: "认证未通过，请重新输入密码。"
						}),
						/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("label", {
							className: "cann-add-field",
							children: ["密码", /* @__PURE__ */ (0, react_jsx_runtime.jsx)("input", {
								ref: input,
								type: "password",
								value: password,
								onChange: (event) => setPassword(event.target.value),
								autoComplete: "off",
								maxLength: 1e3,
								disabled: busy,
								required: true
							})]
						}),
						/* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", { children: "密码仅用于本次连接，不会保存。" }),
						error && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", {
							role: "alert",
							className: "cann-add-error",
							children: error
						}),
						/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("footer", { children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
							type: "button",
							onClick: () => {
								cancel();
							},
							disabled: busy,
							children: "取消连接"
						}), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
							type: "submit",
							className: "cann-add-submit",
							disabled: busy || !password,
							children: busy ? "正在处理…" : "连接"
						})] })
					]
				})
			});
		}
		function RemotePage({ client, attach, reload }) {
			const state = (0, react.useSyncExternalStore)(client.subscribe, client.getSnapshot);
			const host = (0, react.useRef)(null);
			(0, react.useEffect)(() => {
				if (host.current) return attach(host.current);
			}, [attach, state.revision]);
			return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("main", {
				className: "cann-remote-page",
				"aria-label": "远端 CANNBot 工作台",
				"aria-busy": state.status === "loading",
				children: [
					state.error && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
						role: "alert",
						className: "cann-remote-error",
						children: [
							state.error,
							" ",
							/* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
								onClick: reload,
								children: "重试"
							})
						]
					}),
					state.notice && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
						role: "status",
						className: "cann-remote-notice",
						children: state.notice
					}),
					!state.target && state.progress.length > 0 && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("pre", {
						role: "log",
						children: state.progress.join("\n")
					}),
					/* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
						ref: host,
						className: "cann-remote-guest"
					}),
					state.target && state.status === "loading" && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
						role: "status",
						className: "cann-remote-loading",
						children: "正在加载远端工作台…"
					})
				]
			});
		}
		function AddServer({ client, close, setSync, save }) {
			const state = (0, react.useSyncExternalStore)(client.subscribe, client.getSnapshot);
			const dialog = (0, react.useRef)(null), input = (0, react.useRef)(null);
			const [command, setCommand] = (0, react.useState)(""), [label, setLabel] = (0, react.useState)(""), [error, setError] = (0, react.useState)(""), [saving, setSaving] = (0, react.useState)(false);
			(0, react.useEffect)(() => {
				if (!state.addingServer) return;
				setCommand("");
				setLabel("");
				setError("");
				dialog.current?.showModal();
				input.current?.focus();
			}, [state.addingServer]);
			const submit = async () => {
				if (!command.trim() || saving || state.busy) return;
				setSaving(true);
				setError("");
				try {
					await save(command.trim(), label.trim());
				} catch (reason) {
					setError(safeMessage(reason instanceof Error ? reason.message : "无法保存服务器，请重试。"));
				} finally {
					setSaving(false);
				}
			};
			if (!state.addingServer) return null;
			return /* @__PURE__ */ (0, react_jsx_runtime.jsx)("dialog", {
				ref: dialog,
				className: "cann-add-server",
				"aria-labelledby": "cann-add-server-title",
				onCancel: (event) => {
					event.preventDefault();
					if (!saving) close();
				},
				children: /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("form", {
					onSubmit: (event) => {
						event.preventDefault();
						submit();
					},
					children: [
						/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("header", { children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("h2", {
							id: "cann-add-server-title",
							children: "新增 SSH 服务器"
						}), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
							className: "cann-add-close",
							type: "button",
							"aria-label": "关闭新增服务器",
							disabled: saving,
							onClick: close,
							children: "×"
						})] }),
						/* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", { children: "输入 SSH 命令或已有的 SSH 配置别名。" }),
						/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("label", {
							className: "cann-add-field",
							children: ["SSH 命令或别名", /* @__PURE__ */ (0, react_jsx_runtime.jsx)("input", {
								ref: input,
								value: command,
								onChange: (event) => setCommand(event.target.value),
								placeholder: "ssh user@192.168.1.10 -p 22",
								list: "cann-ssh-aliases",
								autoComplete: "off",
								spellCheck: false,
								maxLength: 4096,
								disabled: saving,
								required: true
							})]
						}),
						/* @__PURE__ */ (0, react_jsx_runtime.jsx)("datalist", {
							id: "cann-ssh-aliases",
							children: state.servers.map((server) => /* @__PURE__ */ (0, react_jsx_runtime.jsx)("option", {
								value: server.alias,
								children: server.label
							}, server.id))
						}),
						/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("label", {
							className: "cann-add-field",
							children: ["显示名称（可选）", /* @__PURE__ */ (0, react_jsx_runtime.jsx)("input", {
								value: label,
								onChange: (event) => setLabel(event.target.value),
								placeholder: "例如：开发服务器",
								maxLength: 80,
								disabled: saving
							})]
						}),
						/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("label", {
							className: "cann-add-sync",
							children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("input", {
								type: "checkbox",
								checked: state.syncLogin,
								disabled: saving || state.busy,
								onChange: (event) => setSync(event.target.checked)
							}), "同步本机 DeepSeek 登录"]
						}),
						error && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", {
							role: "alert",
							className: "cann-add-error",
							children: error
						}),
						state.busy && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", {
							role: "status",
							children: "另一台服务器正在连接，请稍后保存。"
						}),
						/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("footer", { children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
							type: "button",
							onClick: close,
							disabled: saving,
							children: "取消"
						}), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
							className: "cann-add-submit",
							type: "submit",
							disabled: saving || state.busy || !command.trim(),
							children: saving ? "正在保存…" : "保存并连接"
						})] })
					]
				})
			});
		}
		// src/client/embedded-shell.ts
		/** Reclaim the embedded Web shell's sidebar track without changing native layout state. */
		function mountEmbeddedShell(document) {
			const owned = /* @__PURE__ */ new Map();
			const scan = () => {
				const live = /* @__PURE__ */ new Set();
				for (const root of document.querySelectorAll("[data-slot=\"root\"]")) {
					const frame = root.firstElementChild;
					if (!(frame instanceof HTMLElement) || frame.parentElement !== root) continue;
					const overlay = frame.querySelector(":scope > [data-shell-overlay]");
					const bottom = frame.querySelector(":scope > [data-shell-bottom]");
					const sidebar = frame.querySelector(":scope > div:has(> [data-slot=\"sidebar\"])");
					const main = sidebar?.nextElementSibling;
					const mainContent = main?.firstElementChild;
					const mainAnchor = mainContent?.matches("[data-slot=\"main\"]") ? mainContent : mainContent?.tagName === "DIV" && mainContent.childElementCount === 1 && mainContent.firstElementChild?.matches("[data-slot=\"main\"]") ? mainContent.firstElementChild : null;
					const rightbar = frame.querySelector(":scope > [data-rightbar-col]");
					if (!overlay || !bottom || !sidebar || !(main instanceof HTMLElement) || main.childElementCount !== 1 || !mainAnchor || !rightbar || !rightbar.querySelector(":scope > [data-slot=\"rightbar\"]") || sidebar.nextElementSibling !== main || main.nextElementSibling !== rightbar || !frame.style.gridTemplateColumns) continue;
					live.add(frame);
					if (owned.has(frame) || frame.hasAttribute("data-cannbot-embedded-frame")) continue;
					const marks = [
						[
							frame,
							"data-cannbot-embedded-frame",
							""
						],
						[
							sidebar,
							"data-cannbot-embedded-column",
							"sidebar"
						],
						[
							main,
							"data-cannbot-embedded-column",
							"main"
						],
						[
							rightbar,
							"data-cannbot-embedded-column",
							"rightbar"
						]
					];
					if (marks.some(([node, name]) => node.hasAttribute(name))) continue;
					for (const [node, name, value] of marks) node.setAttribute(name, value);
					owned.set(frame, () => {
						for (const [node, name, value] of marks) if (node.getAttribute(name) === value) node.removeAttribute(name);
					});
				}
				for (const [frame, release] of owned) if (!live.has(frame)) {
					release();
					owned.delete(frame);
				}
			};
			const observer = new MutationObserver(scan);
			observer.observe(document.documentElement, {
				childList: true,
				subtree: true
			});
			scan();
			return () => {
				observer.disconnect();
				for (const release of owned.values()) release();
				owned.clear();
			};
		}
		// \0dsh-global-css:/home/t00607008/cannbot/dsh/src/client/workspace-tree-bridge.css.mjs
		const css = "[data-slot=sidebar\\.workspaces][data-cannbot-workspaces-hidden]{display:none!important}[data-cannbot-workspace-tree-host]{flex-direction:column;flex:1;height:100%;min-height:0;display:flex}[data-cannbot-workspace-tree-host]:not([data-cannbot-workspaces-active]){display:none}";
		const tagId = "@cannbot-plugin/cannbot-dsh/workspace-tree-bridge.css";
		if (typeof document !== "undefined" && document.querySelector("style[data-plugin-css=" + JSON.stringify(tagId) + "]") === null) {
			const tag = document.createElement("style");
			tag.dataset.plugin = "@cannbot-plugin/cannbot-dsh";
			tag.dataset.pluginCss = tagId;
			tag.textContent = css;
			document.head.appendChild(tag);
		}
		// src/client/WorkspaceTreeBridge.tsx
		const HIDDEN = "data-cannbot-workspaces-hidden";
		function findFrame(anchor) {
			const sidebar = anchor.closest("[data-slot=\"sidebar\"]");
			const root = sidebar?.firstElementChild, region = anchor.parentElement;
			const column = sidebar?.parentElement, frame = column?.parentElement;
			const main = column?.nextElementSibling, rightbar = main?.nextElementSibling;
			if (!(root instanceof HTMLElement) || !region || !root.contains(region) || !frame?.parentElement?.matches("[data-slot=\"root\"]") || column?.firstElementChild !== sidebar || !frame.style.gridTemplateColumns || !main?.querySelector("[data-slot=\"main\"]") || !rightbar?.matches("[data-rightbar-col]") || !rightbar.querySelector(":scope > [data-slot=\"rightbar\"]") || !frame.querySelector(":scope > [data-shell-overlay]") || !frame.querySelector(":scope > [data-shell-bottom]") || region.querySelectorAll("[data-slot=\"sidebar.workspaces\"]").length !== 1 || region.querySelector("[data-slot=\"main\"], [data-slot=\"sidebar.settings\"]")) return null;
			const collapsed = frame.getAttribute("data-sidebar-collapsed");
			return collapsed === null || collapsed === "true" || collapsed === "false" ? frame : null;
		}
		/**
		* Keep the native WorkspaceBrowser mounted: its private search request counter
		* outlives its component, so replacing its slot replays old search requests.
		* The public slot anchor is the visibility boundary; native children and their
		* React ownership, local state, directory flows and menus remain untouched.
		*/
		function WorkspaceTreeBridge({ modes, children }) {
			const source = (0, react.useMemo)(() => ({
				getSnapshot: () => modes.getSnapshot().mode,
				subscribe: (listener) => modes.subscribe(listener)
			}), [modes]);
			const mode = (0, react.useSyncExternalStore)(source.subscribe, source.getSnapshot);
			const [target, setTarget] = (0, react.useState)(null);
			(0, react.useLayoutEffect)(() => {
				let current = null;
				const scan = () => {
					const candidates = [...document.querySelectorAll("[data-slot=\"sidebar.workspaces\"]")].filter((anchor) => findFrame(anchor) !== null);
					const anchor = candidates.length === 1 ? candidates[0] : null;
					const frame = anchor ? findFrame(anchor) : null;
					if (current && (current.anchor !== anchor || !current.host.isConnected || current.host.previousElementSibling !== anchor)) {
						current.host.remove();
						current = null;
					}
					if (anchor && frame && !current) {
						const host = document.createElement("div");
						host.dataset.cannbotWorkspaceTreeHost = "";
						anchor.after(host);
						current = {
							anchor,
							host,
							frame,
							wide: frame.getAttribute("data-sidebar-collapsed") !== "true"
						};
					}
					const wide = current?.frame.getAttribute("data-sidebar-collapsed") !== "true";
					if (current && current.wide !== wide) current = {
						...current,
						wide
					};
					setTarget((previous) => previous?.anchor === current?.anchor && previous?.host === current?.host && previous?.wide === current?.wide ? previous : current);
				};
				const observer = new MutationObserver(scan);
				observer.observe(document.documentElement, {
					childList: true,
					subtree: true,
					attributes: true,
					attributeFilter: ["data-sidebar-collapsed"]
				});
				scan();
				return () => {
					observer.disconnect();
					current?.host.remove();
				};
			}, []);
			(0, react.useLayoutEffect)(() => {
				if (!target || mode !== "cannbot") return;
				const { anchor, host } = target;
				const inert = anchor.getAttribute("inert"), aria = anchor.getAttribute("aria-hidden");
				if (anchor.hasAttribute(HIDDEN)) return;
				anchor.setAttribute(HIDDEN, "");
				anchor.setAttribute("inert", "");
				anchor.setAttribute("aria-hidden", "true");
				host.setAttribute("data-cannbot-workspaces-active", "");
				return () => {
					anchor.removeAttribute(HIDDEN);
					if (anchor.getAttribute("inert") === "") inert === null ? anchor.removeAttribute("inert") : anchor.setAttribute("inert", inert);
					if (anchor.getAttribute("aria-hidden") === "true") aria === null ? anchor.removeAttribute("aria-hidden") : anchor.setAttribute("aria-hidden", aria);
					host.removeAttribute("data-cannbot-workspaces-active");
				};
			}, [target, mode]);
			return target ? (0, react_dom.createPortal)(children(target.wide), target.host) : null;
		}
		// src/client/NativeWorkflowPlaceholder.tsx
		/** Change only the native editor's placeholder text, never its value or styles.
		* Public composer markers avoid relying on renderer internals or CSS hashes. */
		function adaptNativePlaceholder(root, example) {
			const original = /* @__PURE__ */ new Map();
			const restore = () => {
				for (const [node, saved] of original) {
					if ("text" in saved && node.textContent === example) node.textContent = saved.text ?? "";
					for (const [name, value] of Object.entries(saved.attributes || {})) {
						if (node.getAttribute(name) !== example) continue;
						if (value === null) node.removeAttribute(name);
						else node.setAttribute(name, value);
					}
				}
				original.clear();
			};
			const update = () => {
				const editor = root.querySelector("[role=\"textbox\"][data-placeholder]");
				if (!editor || editor.getAttribute("contenteditable") !== "true" || editor.getAttribute("aria-disabled") === "true") {
					restore();
					return;
				}
				const saved = original.get(editor) ?? { attributes: {} };
				for (const name of ["data-placeholder", "aria-label"]) {
					const current = editor.getAttribute(name);
					if (current !== example) {
						saved.attributes[name] = current;
						editor.setAttribute(name, example);
					}
				}
				original.set(editor, saved);
				for (const node of root.querySelectorAll("[data-composer-placeholder]")) {
					if (node.textContent === example) continue;
					original.set(node, { text: node.textContent });
					node.textContent = example;
				}
			};
			const observer = new MutationObserver(update);
			observer.observe(root, {
				childList: true,
				subtree: true,
				characterData: true,
				attributes: true,
				attributeFilter: [
					"data-placeholder",
					"aria-label",
					"aria-disabled",
					"contenteditable"
				]
			});
			update();
			return () => {
				observer.disconnect();
				restore();
			};
		}
		function NativeWorkflowPlaceholder({ ctx, modes, selection, sessionId, useInput, useSession, useProjection }) {
			const marker = (0, react.useRef)(null);
			const mode = (0, react.useSyncExternalStore)(modes.subscribe, modes.getSnapshot);
			const saved = (0, react.useSyncExternalStore)(selection.subscribe, selection.getSnapshot);
			const sessions = ctx.sessions;
			const sources = (0, react.useMemo)(() => ({
				subscribe: (listener) => sessions.list.subscribe(listener),
				getSnapshot: () => sessions.list.getSnapshot()
			}), [sessions]);
			const catalog = (0, react.useSyncExternalStore)(sources.subscribe, sources.getSnapshot);
			const input = useInput((snapshot) => snapshot);
			const session = useSession((snapshot) => snapshot);
			const planActive = useProjection("plan", (plan) => !!plan && (plan.pending ? !plan.active : plan.active));
			const blockSource = (0, react.useMemo)(() => ctx.conversation.blocks.storeFor(sessionId), [ctx, sessionId]);
			const block = (0, react.useSyncExternalStore)(blockSource.subscribe, blockSource.getSnapshot);
			const workspace = mode.workspaces.find((item) => item.sessionIds.includes(sessionId) || item.workspaceId === mode.sessions.find((item) => item.sessionId === sessionId)?.workspaceId);
			const allowed = mode.mode === "cannbot" && mode.ready && !!workspace && catalog.byId[sessionId]?.blank === true && saved.ready && !saved.pending && !saved.error && saved.values[sessionId] === workspace.pluginId && input?.phase === "plain" && !planActive && !block && !session?.running && !session?.promptError && !session?.removed;
			const example = workspace ? guideFor(workspace.pluginId).example : "";
			(0, react.useEffect)(() => {
				const root = marker.current?.closest("[data-slot=\"conversation.composer.bar\"]");
				if (!allowed || !root || !example) return;
				return adaptNativePlaceholder(root, example);
			}, [
				allowed,
				example,
				sessionId
			]);
			return /* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
				ref: marker,
				hidden: true,
				"aria-hidden": "true"
			});
		}
		// src/client/index.ts
		const inject = [
			"slots",
			"theme",
			"locale",
			"sessions",
			"conversation"
		];
		/** Register presentation with an explicit disposer so the original entries remain live underneath. */
		function mountInterface(ctx, selection, content, modes, remote) {
			const style = document.createElement("style");
			style.dataset.cannbotDsh = "interface";
			style.textContent = interface_css_default;
			document.head.append(style);
			const releases = [
				ctx.theme.overrideTokens(PACKAGE, cannTheme),
				injectSlot(ctx, "sidebar.brand.name", () => ctx.slots.register({
					name: "sidebar.brand.name",
					priority: -100
				}, SidebarName)),
				injectSlot(ctx, "conversation.hero.brand.mark", () => ctx.slots.register({
					name: "conversation.hero.brand.mark",
					priority: -100
				}, Hero)),
				injectSlot(ctx, "conversation.hero.agentPreset", () => ctx.slots.register({
					name: "conversation.hero.agentPreset",
					priority: -100
				}, (props) => (0, react.createElement)(BoundWorkspaceWorkflow, {
					modes,
					..."sessionId" in props && typeof props.sessionId === "string" && { sessionId: props.sessionId }
				}))),
				injectSlot(ctx, "conversation.hero.workspace", () => ctx.slots.register({
					name: "conversation.hero.workspace",
					priority: -100
				}, (props) => (0, react.createElement)(NativeWorkspacePicker, {
					...props,
					modes
				}))),
				injectSlot(ctx, "conversation.input.overlay", () => ctx.slots.register({
					name: "conversation.input.overlay",
					id: "cannbot-workflow-placeholder"
				}, (props) => (0, react.createElement)(NativeWorkflowPlaceholder, {
					...props,
					ctx,
					modes,
					selection
				}))),
				injectSlot(ctx, "shell.overlay", () => ctx.slots.register({
					name: "shell.overlay",
					id: "cannbot-workspace-create"
				}, () => (0, react.createElement)(ModeWorkspaceCreation, {
					ctx,
					modes,
					content,
					remote
				}))),
				injectSlot(ctx, "conversation.input.dock", () => ctx.slots.register({
					name: "conversation.input.dock",
					id: "todo",
					priority: -100,
					order: 0,
					locale: NAMESPACE
				}, TaskDock)),
				injectSlot(ctx, "conversation.session.header.actions", () => ctx.slots.register({
					name: "conversation.session.header.actions",
					id: "cannbot-session-workflow",
					order: -100,
					locale: NAMESPACE
				}, (props) => (0, react.createElement)(SessionWorkflow, {
					...props,
					selection
				})))
			];
			return () => {
				for (const release of releases.reverse()) release();
				style.remove();
			};
		}
		function apply(ctx) {
			const content = createContentStore();
			ctx.effect(() => content.start());
			registerPluginUpdates(ctx, content);
			const selection = createWorkflowSelection((sessionId, reason) => {
				const blocks = ctx.conversation.blocks;
				const id = sessionId;
				const store = blocks.storeFor(id);
				if (store.getSnapshot() !== void 0) return () => {};
				const block = { reason };
				blocks.set(id, block);
				return () => {
					if (store.getSnapshot() === block) blocks.set(id, void 0);
				};
			}, content.prepare);
			connectWorkflowSelection(ctx, selection);
			ctx.effect(() => () => selection.dispose());
			ctx.effect(() => ctx.locale.register(NAMESPACE, {
				zh,
				en
			}));
			ctx.inject([
				"layout",
				"uiWorkspace",
				"workspaces"
			], (scoped) => scoped.effect(() => {
				const modes = createWorkspaceModes(scoped);
				const remote = createRemoteClient(scoped, {
					onReturnLocal: () => modes.returnLocal(),
					onSelectServer: (id) => modes.selectServer(id),
					onCreateWorkspace: (id) => modes.setCreating(true, id)
				});
				const releases = [registerWorkbench(scoped, selection, content, modes)];
				releases.push(injectSlot(scoped, "main", () => scoped.slots.register({
					name: "main",
					key: SERVERS_PANEL
				}, () => (0, react.createElement)(ModeWorkspaceTree, {
					ctx: scoped,
					modes,
					content,
					remote,
					management: true
				}))));
				if (modes.embedded) releases.push(mountEmbeddedShell(document));
				releases.push(injectSlot(scoped, "sidebar.brand.mark", () => scoped.slots.register({
					name: "sidebar.brand.mark",
					priority: -100
				}, (props) => (0, react.createElement)(ModeBrandMark, {
					...props,
					modes,
					onServers: () => scoped.layout.selectPanel(SERVERS_PANEL)
				}))));
				releases.push(injectSlot(scoped, "shell.overlay", () => scoped.slots.register({
					name: "shell.overlay",
					id: "cannbot-workspace-tree-bridge"
				}, () => (0, react.createElement)(WorkspaceTreeBridge, {
					modes,
					children: (wide) => (0, react.createElement)(ModeWorkspaceTree, {
						ctx: scoped,
						modes,
						content,
						remote,
						wide
					})
				}))));
				const navigation = scoped.uiWorkspace, originalStart = navigation.startSession;
				const start = (workspaceId, options) => {
					const state = modes.getSnapshot();
					if (state.mode === "deepseek") originalStart.call(navigation, workspaceId, options);
					else if (state.serverId) remote.open({
						serverId: state.serverId,
						...workspaceId && { workspaceId }
					}).catch(() => modes.reportError("无法打开远端工作台，请检查连接后重试。"));
					else modes.newSession(workspaceId);
				};
				navigation.startSession = start;
				releases.push(() => {
					if (navigation.startSession === start) navigation.startSession = originalStart;
				});
				const originalFork = navigation.forkSession;
				if (typeof originalFork === "function") {
					const fork = async (id, onCreated, options) => {
						if (modes.getSnapshot().mode === "deepseek") return originalFork.call(navigation, id, onCreated, options);
						if (modes.getSnapshot().serverId) throw new Error("请使用远端会话行的操作菜单。");
						if (!modes.getSnapshot().ready) throw new Error("工作区正在加载，请稍后重试。");
						const snapshot = modes.getSnapshot();
						const workspace = snapshot.workspaces.find((item) => item.sessionIds.includes(id) || item.workspaceId === snapshot.sessions.find((session) => session.sessionId === id)?.workspaceId);
						if (!workspace && snapshot.sessions.some((session) => session.sessionId === id)) {
							const result = await modes.operate({
								action: "fork-session",
								sessionId: id,
								...options?.allowMigration === void 0 ? {} : { allowMigration: options.allowMigration }
							});
							if (!result.sessionId) throw new Error("DSH 未返回可用的分支会话。");
							const child = result.sessionId;
							onCreated?.(child);
							return child;
						}
						if (modes.getSnapshot().mode === "cannbot" !== !!workspace) throw new Error("请先切换到该会话所属模式。");
						if (!workspace) return originalFork.call(navigation, id, onCreated, options);
						const child = await originalFork.call(navigation, id, void 0, options);
						await modes.recordSession(workspace.workspaceId, child);
						onCreated?.(child);
						return child;
					};
					navigation.forkSession = fork;
					releases.push(() => {
						if (navigation.forkSession === fork) navigation.forkSession = originalFork;
					});
				}
				const originalArchive = navigation.archiveSession;
				if (typeof originalArchive === "function") {
					const archive = async (id, options) => {
						if (modes.getSnapshot().mode === "deepseek") return originalArchive.call(navigation, id, options);
						if (modes.getSnapshot().serverId) throw new Error("请使用远端会话行的操作菜单。");
						if (!modes.getSnapshot().ready) throw new Error("工作区正在加载，请稍后重试。");
						const snapshot = modes.getSnapshot();
						const owned = snapshot.workspaces.some((item) => item.sessionIds.includes(id)) || snapshot.sessions.some((item) => item.sessionId === id);
						if (modes.getSnapshot().mode === "cannbot" !== owned) throw new Error("请先切换到该会话所属模式。");
						return originalArchive.call(navigation, id, options);
					};
					navigation.archiveSession = archive;
					releases.push(() => {
						if (navigation.archiveSession === archive) navigation.archiveSession = originalArchive;
					});
				}
				let presentation;
				const updatePresentation = () => {
					if (modes.getSnapshot().mode === "cannbot") presentation ??= mountInterface(scoped, selection, content, modes, remote);
					else {
						presentation?.();
						presentation = void 0;
					}
				};
				releases.push(modes.subscribe(updatePresentation));
				updatePresentation();
				releases.push(() => presentation?.(), remote.start(), modes.start());
				return () => {
					for (const release of releases.reverse()) release();
					remote.dispose();
					modes.dispose();
				};
			}));
		}
		exports.apply = apply;
		exports.inject = inject;
		return module.exports;
	}
});
;
//# sourceMappingURL=??@cannbot-plugin/cannbot-dsh/client.js.map&rev=98997a55f373
