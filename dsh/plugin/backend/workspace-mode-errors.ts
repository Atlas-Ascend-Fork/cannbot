// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { sessionActivity } from '../contracts/workspace-mode-types.ts'

const errors: Record<string, readonly [number, string]> = {
  'workflow-linux-only': [400, '本工作流需要 Linux 环境。Windows 或 macOS 本机请选择空白工作区，或连接 Linux 服务器。'],
  'workflow-active': [409, '工作区仍有运行中的会话、后台任务或定时任务。请先停止或等待完成。'],
  'workflow-switching': [409, '工作流正在切换，请等待初始化完成。'],
  'session-frozen': [409, '会话所属工作流已变更，历史记录已冻结。请新建会话。'],
  'folder-exists': [409, '同名文件夹已存在，请换一个新名称。'],
  'creation-changed': [409, '创建请求或目录已变化，请重新创建工作区。'],
  'invalid-directory': [400, '父目录不可用，请选择有效的绝对路径。'],
  'invalid-plugin': [400, '请选择已安装的工作流。'],
  'EACCES': [403, '没有此目录的访问权限，请选择其他父目录。'],
  'EPERM': [403, '没有此目录的访问权限，请选择其他父目录。'],
  'ENOENT': [404, '目录不存在，请重新选择父目录。'],

  'workspace/session-active': [409, '该会话仍有运行中的任务，确认停止任务后才能归档。'],
  'workspace/name-conflict': [409, '已有同名工作区，请使用其他名称。'],
  'workspace/not-found': [404, '工作区已被移除，请刷新列表。'],
  'session/not-found': [404, '会话已不可用，请刷新列表。'],
  'session/title-invalid': [400, '会话名称无效，请输入有效名称。'],
  'session/fork-unavailable': [409, '该会话尚无可用于创建分支的完整对话。'],
  'session/migration-required': [409, '请先打开原会话完成迁移，再创建分支。'],
  'gateway/bad-request': [400, '当前状态不支持此操作，请刷新列表并检查输入。'],
  'unknown-workspace': [404, '该工作区不属于 CANNBot，或已被移除。'],
  'unknown-session': [404, '该会话不属于 CANNBot。'],
  'session-workspace-mismatch': [409, '会话与其登记的工作区不一致。'],
  'session-conflict': [409, '会话归属已改变，请刷新后重试。'],
  'operation-unavailable': [503, '当前 DSH 不支持此操作，请更新后重试。'],
  'host-not-ready': [503, 'DSH 服务尚未就绪，请稍后重试。'],
  'invalid-request': [400, '操作参数无效，请检查后重试。'],
}

/** Keep stable semantic codes and bounded display facts, never native exception text. */
export function workspaceOperationFailure(value: unknown) {
  const error = value && typeof value === 'object' ? value as { code?: unknown; error?: unknown; details?: { activity?: unknown }; activity?: unknown } : {}
  const code = typeof error.code === 'string' ? error.code : typeof error.error === 'string' ? error.error : ''
  const known = errors[code]
  if (!known) return { status: 500, body: { error: 'workspace-operation-failed', message: '操作未能完成，请刷新列表确认结果后重试。' } }
  return { status: known[0], body: { error: code, message: known[1], ...(code === 'workspace/session-active' ? { activity: sessionActivity(error.activity ?? error.details?.activity) } : {}) } }
}
