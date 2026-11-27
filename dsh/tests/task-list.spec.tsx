// ----------------------------------------------------------------------------------------------------------
// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.
// ----------------------------------------------------------------------------------------------------------

import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, expect, it } from 'vitest'
import { TaskList } from '../plugin/frontend/TaskList.tsx'
import { zh } from '../plugin/frontend/locales.ts'

afterEach(cleanup)
const t = ((key: keyof typeof zh) => zh[key]) as Parameters<typeof TaskList>[0]['t']
it('always displays zero completed tasks', () => {
  render(<TaskList t={t} todos={[{ content: '设计', status: 'in_progress' }]} />)
  expect(screen.getByRole('status').textContent).toBe('已完成 0 / 1')
  expect(screen.queryByRole('list')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: /任务列表/ }))
  expect(screen.getByText('设计')).toBeTruthy()
  expect(screen.getByRole('listitem').querySelector('svg[data-state="ongoing"]')).toBeTruthy()
  expect(screen.getByRole('button', { name: /任务列表/ }).getAttribute('aria-expanded')).toBe('true')
  fireEvent.click(screen.getByRole('button', { name: /任务列表/ }))
  expect(screen.queryByRole('list')).toBeNull()
})
it('counts all completions while showing the latest two and expands the full list', () => {
  const completed = ['设计', '测试工程', '白盒测试', '代码检视'].map(content => ({ content, status: 'completed' as const }))
  const current = { content: '实现', status: 'in_progress' as const }
  const { rerender } = render(<TaskList t={t} todos={[current, ...completed]} />)
  const panel = within(screen.getByRole('region', { name: '任务列表' }))
  const visibleTasks = () => within(panel.getByRole('list')).getAllByRole('listitem').map(row => row.textContent)

  expect(panel.getByRole('status').textContent).toBe('已完成 4 / 5')
  expect(panel.queryByRole('list')).toBeNull()
  fireEvent.click(panel.getByRole('button', { name: /任务列表/, expanded: false }))
  const recent = ['✓代码检视', '✓白盒测试', '实现']
  expect(visibleTasks()).toEqual(recent)

  fireEvent.click(panel.getByRole('button', { name: '查看全部任务' }))
  expect(visibleTasks()).toEqual(['✓代码检视', '✓白盒测试', '✓测试工程', '✓设计', '实现'])
  fireEvent.click(panel.getByRole('button', { name: '仅显示最近完成' }))
  expect(visibleTasks()).toEqual(recent)

  rerender(<TaskList t={t} todos={[...completed, { ...current, status: 'completed' }]} />)
  expect(panel.getByRole('status').textContent).toBe('已完成 5 / 5')
  expect(visibleTasks()).toEqual(['✓实现', '✓代码检视'])
})
it('renders no panel for an empty native todo list', () => {
  const { container } = render(<TaskList t={t} todos={[]} />)
  expect(container.firstChild).toBeNull()
})
