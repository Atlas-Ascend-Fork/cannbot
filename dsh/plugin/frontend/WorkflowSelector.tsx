// ----------------------------------------------------------------------------------------------------------
// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.
// ----------------------------------------------------------------------------------------------------------

import { useState, useSyncExternalStore, type ComponentType, type ReactNode } from 'react'
import * as primitives from '@deepseek-ai/dsh-client-ui-primitives'
import type { PropsLocale, PropsRuntime } from '@deepseek-ai/dsh-client-ui-slots'
import type {} from '@deepseek-ai/dsh-client-ui-conversation/client'
import { workflowCopy } from './workflow-copy.ts'
import { WorkflowIcon, ChevronIcon } from './WorkflowIcon.tsx'
import type { WorkflowSelection } from './workflow-selection.ts'
import { fallbackContent, type ContentStore, type DynamicWorkflow } from './content-store.ts'

export type WorkflowProps = PropsRuntime<'conversation.hero.agentPreset'> & PropsLocale<'cannbotDsh'> & { selection: WorkflowSelection; content?: ContentStore }

/** Select a workflow without submitting, replacing text, or discarding reference chips. */
export function WorkflowSelector({ sessionId, inputActions, useInput, t, selection, content = fallbackContent as ContentStore }: WorkflowProps) {
  const { workflows } = useSyncExternalStore(content.subscribe, content.getSnapshot)
  const copy = (workflow: DynamicWorkflow) => workflowCopy(workflow, t)
  const input = useInput(state => state)
  const saved = useSyncExternalStore(selection.subscribe, selection.getSnapshot)
  const [open, setOpen] = useState(false)
  const selected = workflows.find(workflow => sessionId && saved.values[sessionId] === workflow.id)
  const available = !!sessionId && saved.ready && !saved.pending && inputActions !== undefined && input !== undefined && input.phase === 'plain'
  const pick = (id: string) => {
    setOpen(false)
    if (sessionId && available) void selection.choose(sessionId, id, t('saving'))
  }
  const anchor = (
      <button type="button" className="cannbot-dsh-workflow-trigger" aria-label={t('workflow')} aria-haspopup="menu" aria-expanded={open}
        disabled={!available} title={inputActions === undefined ? t('chooseWorkspace') : t('commandHint')}
        onClick={() => setOpen(value => !value)}>
        <WorkflowIcon />
        <span className="cannbot-dsh-workflow-label" lang={selected ? 'en' : undefined}>{selected ? copy(selected).name : t('workflow')}</span><ChevronIcon size={12} />
      </button>
  )
  const label = (workflow: DynamicWorkflow) => <span className="cannbot-dsh-workflow-option">
        <span lang="en">{copy(workflow).name}</span>
        {copy(workflow).description && <>{' '}<small>{copy(workflow).description}</small></>}
      </span>
  const { Menu, MenuItemButton } = primitives
  const LegacyMenu = Menu as unknown as ComponentType<{ open: boolean; anchor: ReactNode; portal: boolean; className: string; onClose(): void; selectedId?: string; onSelect(id: string): void; items: { id: string; label: ReactNode; icon: ReactNode }[] }>
  return <span className="cannbot-dsh-workflow">
    {typeof MenuItemButton === 'function' ? <Menu open={open} onClose={() => setOpen(false)} portal className="cannbot-dsh-workflow-anchor" anchor={anchor}>
      <MenuItemButton icon={<WorkflowIcon />} onSelect={() => pick('')}>{t('ordinary')}</MenuItemButton>
      {workflows.map(workflow => <MenuItemButton key={workflow.id} icon={<WorkflowIcon />} onSelect={() => pick(workflow.id)}>{label(workflow)}</MenuItemButton>)}
    </Menu> : <LegacyMenu open={open} onClose={() => setOpen(false)} portal className="cannbot-dsh-workflow-anchor" anchor={anchor}
      selectedId={selected?.id} items={[{ id: '', label: t('ordinary'), icon: <WorkflowIcon /> }, ...workflows.map(workflow => ({ id: workflow.id, label: label(workflow), icon: <WorkflowIcon /> }))]}
      onSelect={pick} />}
    {saved.error && <span role="alert" className="cannbot-dsh-error">
      <button type="button" onClick={() => selection.retry()} title={t('insertFailed')}>
        {t(saved.errorKind === 'settings' ? 'settingsRetry' : 'workflowRetry')}
      </button>
    </span>}
  </span>
}
