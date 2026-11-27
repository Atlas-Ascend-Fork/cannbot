// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import test from 'node:test'
import assert from 'node:assert/strict'
import { Context } from '@deepseek-ai/cordis'
import SessionStore from '@deepseek-ai/dsh-session'
import ToolRuntime from '@deepseek-ai/dsh-tools'
import SystemPrompt from '@deepseek-ai/dsh-system-prompt'
import SessionProjectionRegistry from '@deepseek-ai/dsh-session-projection'
import * as ToolTodo from '@deepseek-ai/dsh-tool-todo'
import { WorkflowTodos } from '../plugin/backend/workflow-todos.mjs'

test('DSH native todos projection renders workflow events and keeps its turn lifecycle', async () => {
  const ctx = new Context()
  let tracker
  const fibers = []
  try {
    fibers.push(ctx.plugin(SessionStore))
    fibers.push(ctx.plugin(SystemPrompt, { personaPrefix: '' }))
    fibers.push(ctx.plugin(ToolRuntime))
    fibers.push(ctx.plugin(SessionProjectionRegistry))
    fibers.push(ctx.plugin(ToolTodo, { allowParallelInProgress: true }))
    await Promise.all(fibers)
    tracker = new WorkflowTodos(ctx)
    const session = ctx.sessions.create(), parent = { id: session.id, session }
    session.append('todo/write', { todos: [{ content: 'Existing plan', status: 'pending' }] })
    const run = { workflow: 'ops-direct-invoke', cwd: '/project' }
    tracker.update(parent, run, { tasks: { impl: { status: 'verifying' }, review: { status: 'awaiting_approval' } } })
    const todos = ctx.sessionProjections.snapshot(session).values.todos
    assert.equal(todos.length, 3)
    assert.equal(todos[0].content, 'Existing plan')
    assert(todos.slice(1).every(todo => todo.status === 'in_progress'))
    session.append('todo/write', { todos: [{ content: 'New plan', status: 'completed' }] })
    await new Promise(resolve => setImmediate(resolve))
    assert.equal(ctx.sessionProjections.snapshot(session).values.todos.length, 3)
    tracker.update(parent, run, { tasks: { impl: { status: 'pass' }, review: { status: 'pass' } } }, true)
    session.append('turn/start', { turn: 1 })
    await new Promise(resolve => setImmediate(resolve))
    assert.equal(ctx.sessionProjections.snapshot(session).values.todos.length, 2)
    assert(ctx.sessionProjections.snapshot(session).values.todos.every(todo => todo.status === 'completed'))
  } finally { tracker?.dispose(); await Promise.all(fibers.reverse().map(fiber => fiber.dispose())) }
})
