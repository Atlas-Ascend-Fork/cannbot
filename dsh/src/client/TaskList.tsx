// ----------------------------------------------------------------------------------------------------------
// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.
// ----------------------------------------------------------------------------------------------------------

import { useState } from 'react'
import { StateDot } from '@deepseek-ai/dsh-client-ui-primitives'
import type { PropsLocale, PropsRuntime } from '@deepseek-ai/dsh-client-ui-slots'
import type { TodoItem } from '@deepseek-ai/dsh-tool-todo/client'

type Props = PropsLocale<'cannbotDsh'> & { todos: readonly TodoItem[] }

/** One view of the native todos projection, including a compact completion history. */
export function TaskList({ todos, t }: Props) {
  const [expanded, setExpanded] = useState(false)
  const [showAll, setShowAll] = useState(false)
  if (!todos.length) return null
  const done = todos.filter(task => task.status === 'completed')
  const open = todos.filter(task => task.status !== 'completed')
  const visible = [...(showAll ? done : done.slice(-2)).reverse(), ...open]
  return <section className="cannbot-task-list" aria-label={t('tasksTitle')}>
    <button className="cannbot-task-list-toggle" type="button" aria-expanded={expanded} onClick={() => setExpanded(value => !value)}>
      <strong>{t('tasksTitle')}</strong>
      <span role="status">{t('tasksDone')} {done.length} / {todos.length}</span>
      <span className="cannbot-task-list-chevron" aria-hidden>{expanded ? '⌄' : '⌃'}</span>
    </button>
    {expanded && <><ul>{visible.map(task => <li key={task.content} data-status={task.status}>
      <span className="cannbot-task-list-icon" aria-hidden>{task.status === 'in_progress'
        ? <StateDot state="ongoing" /> : task.status === 'completed' ? '✓' : '○'}</span>
      <span>{task.content}</span>
    </li>)}</ul>
      {done.length > 2 && <button type="button" onClick={() => setShowAll(value => !value)}>
        {t(showAll ? 'tasksRecent' : 'tasksAll')}
      </button>}
    </>}
  </section>
}

export function TaskDock({ useProjection, t }: PropsRuntime<'conversation.input.dock'> & PropsLocale<'cannbotDsh'>) {
  const todos = useProjection('todos')
  return <TaskList todos={todos ?? []} t={t} />
}
