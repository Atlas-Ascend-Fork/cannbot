// ----------------------------------------------------------------------------------------------------------
// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.
// ----------------------------------------------------------------------------------------------------------

import { useMemo, useRef, useState, useSyncExternalStore, type FormEvent } from 'react'
import type { Context } from '@deepseek-ai/cordis'
import type { ISessions } from '@deepseek-ai/dsh-api-session-controller/client'
import type { MainPanelId } from '@deepseek-ai/dsh-client-ui-layout/client'
import type {} from '@deepseek-ai/dsh-client-ui-workspace/client'
import type {} from '@deepseek-ai/dsh-client-ui-plugin-manager/client'
import type { WorkflowSelection } from './workflow-selection.ts'
import type { ContentStore, DynamicWorkflow } from './content-store.ts'
import { preparationLabels, type WorkbenchStore } from './workbench-state.ts'
import { cardOrder, categories, guideFor, type Category } from './workbench-data.ts'
import { inheritedWorkspaceId } from './workbench-workspace.ts'
import { WorkbenchIcon } from './WorkbenchIcon.tsx'
import { WorkspaceDirectory } from './WorkspaceDirectory.tsx'
import { workflowCopy } from './workflow-copy.ts'
import { zh, PACKAGE } from './locales.ts'
import { launchWorkbench } from './workbench-launch.ts'
import { newerVersion } from './plugin-update.ts'

export const HOME_PANEL = 'cannbot-dsh-workbench' as MainPanelId
export const LIBRARY_PANEL = 'cannbot-dsh-workflows' as MainPanelId
const copy = (workflow: DynamicWorkflow) => workflowCopy(workflow, key => zh[key])
export interface WorkbenchProps { ctx: Context; content: ContentStore; selection: WorkflowSelection; store: WorkbenchStore; library?: boolean }

export function Workbench({ ctx, content, selection, store, library = false }: WorkbenchProps) {
  const state = useSyncExternalStore(store.subscribe, store.getSnapshot)
  const { workflows } = useSyncExternalStore(content.subscribe, content.getSnapshot)
  const workspaceSource = ctx.workspaces.list
  const workspaceBinding = useMemo(() => ({ subscribe: (listener: () => void) => workspaceSource.subscribe(listener), getSnapshot: () => workspaceSource.getSnapshot() }), [workspaceSource])
  const workspaceState = useSyncExternalStore(workspaceBinding.subscribe, workspaceBinding.getSnapshot)
  const sessionSource = (ctx.sessions as unknown as ISessions).list
  const sessionBinding = useMemo(() => ({ subscribe: (listener: () => void) => sessionSource.subscribe(listener), getSnapshot: () => sessionSource.getSnapshot() }), [sessionSource])
  const sessionState = useSyncExternalStore(sessionBinding.subscribe, sessionBinding.getSnapshot)
  const saved = useSyncExternalStore(selection.subscribe, selection.getSnapshot)
  const [category, setCategory] = useState<Category>('全部')
  const [query, setQuery] = useState('')
  const [pickingWorkspace, setPickingWorkspace] = useState(false)
  const input = useRef<HTMLTextAreaElement>(null)
  const files = useRef<HTMLInputElement>(null)
  const ordered = [...workflows].sort((a, b) => (cardOrder.indexOf(a.id) < 0 ? 999 : cardOrder.indexOf(a.id)) - (cardOrder.indexOf(b.id) < 0 ? 999 : cardOrder.indexOf(b.id)))
  const visible = ordered.filter(workflow => (category === '全部' || guideFor(workflow.id).category === category) && `${workflow.id} ${copy(workflow).description}`.toLowerCase().includes(query.toLowerCase().trim()))
  const inheritedId = inheritedWorkspaceId(workspaceState.items, sessionState)
  const workspace = workspaceState.items.find(item => item.workspaceId === (state.workspaceId || inheritedId))
  const inherited = !state.workspaceId && !!workspace && workspace.workspaceId === inheritedId
  const selected = workflows.find(item => item.id === state.workflow)
  const detail = workflows.find(item => item.id === state.detail) ?? workflows[0]
  const navigate = (panel: MainPanelId) => ctx.layout.selectPanel(panel)
  const settings = () => ctx.get('pluginNavigation')?.openBundle(PACKAGE)
  const fail = (error: unknown) => store.set({ error: error instanceof Error ? error.message : '暂时无法完成，请重试。' })
  const start = async (event?: FormEvent) => {
    event?.preventDefault()
    if (store.getSnapshot().busy) return
    if (!workspace) { store.set({ error: '请先选择或添加工作区。' }); return }
    if (!state.prompt.trim() && state.files.length === 0) { input.current?.focus(); return }
    store.set({ busy: true, error: '', stage: 'workspace' })
    try {
      await launchWorkbench(ctx, selection, { workspaceId: workspace.workspaceId, workflow: state.workflow, prompt: state.prompt, files: state.files }, store.signal, stage => store.set({ stage }))
      store.set({ prompt: '', files: [] })
    } catch (error) { fail(error) } finally { store.set({ busy: false, stage: 'idle' }) }
  }
  const useWorkflow = (id: string, example?: string) => {
    store.set({ workflow: id, ...(example && !state.prompt.trim() ? { prompt: example } : {}), error: '' })
    navigate(HOME_PANEL)
  }
  return <main className="cannbot-workbench" aria-label={library ? 'CANNBot 工作流' : 'CANNBot工作台'}>
    <header className="cwb-header">
      <div className="cwb-workspace"><WorkbenchIcon name="folder" /><div className="cwb-workspace-info"><div className="cwb-workspace-choice">
        <select aria-label="当前工作区" value={workspace?.workspaceId ?? ''} disabled={state.busy || workspaceState.phase !== 'ready'} onChange={event => store.set({ workspaceId: event.target.value, error: '' })}>
          {!workspace && <option value="">选择工作区</option>}
          {workspaceState.items.map(item => <option key={item.workspaceId} value={item.workspaceId}>{item.title === 'default-workspace' ? '默认工作区' : item.title}</option>)}
        </select>{inherited && <span className="cwb-inherited">沿用当前对话</span>}</div>{workspace && <span className="cwb-workspace-path" title={workspace.path}>{workspace.path}</span>}</div><button className="cwb-text-button" disabled={state.busy} onClick={() => setPickingWorkspace(true)}>选择工作区</button>
      </div>
      {library && <button className="cwb-text-button" onClick={settings}>插件设置</button>}
    </header>
    {pickingWorkspace && <WorkspaceDirectory ctx={ctx} initialPath={workspace?.path} onSelect={workspaceId => { if (!store.signal.aborted) store.set({ workspaceId, error: '' }) }} onClose={() => setPickingWorkspace(false)} />}
    <div className="cwb-content">
      <div className="cwb-heading"><h1>{library ? '找到适合你的工作流' : '开始你的 Ascend 开发'}</h1>{library && <p>了解适用场景，准备好输入，再开始。</p>}</div>
      {!library && <>
        <form className="cwb-composer" onSubmit={event => void start(event)} onDragOver={event => event.preventDefault()} onDrop={event => { event.preventDefault(); if (!state.busy) store.set({ files: [...state.files, ...Array.from(event.dataTransfer.files)] }) }}>
          <textarea ref={input} aria-label="开发需求" placeholder={selected ? `例如：${guideFor(selected.id).example}` : '描述算子需求，或添加需要优化的代码。'} value={state.prompt} disabled={state.busy} onChange={event => store.set({ prompt: event.target.value })} />
          {state.files.length > 0 && <ul className="cwb-files">{state.files.map((file, index) => <li key={`${file.name}-${index}`}><WorkbenchIcon name="document" size={14} /><span>{file.name}</span><button type="button" disabled={state.busy} aria-label={`移除 ${file.name}`} onClick={() => store.set({ files: state.files.filter((_, i) => i !== index) })}>×</button></li>)}</ul>}
          <div className="cwb-composer-actions"><div className="cwb-composer-tools">
            <input type="file" multiple hidden ref={files} onChange={event => { store.set({ files: [...state.files, ...Array.from(event.target.files ?? [])] }); event.target.value = '' }} />
            <button type="button" className="cwb-text-button" disabled={state.busy} onClick={() => files.current?.click()}><WorkbenchIcon name="clip" size={18} />添加文件</button>
            {state.workflow && <span className="cwb-selection"><WorkbenchIcon name={guideFor(state.workflow).icon} size={16} /><span>{state.workflow}</span><button type="button" disabled={state.busy} aria-label="取消工作流选择" onClick={() => store.set({ workflow: '' })}>×</button></span>}
          </div><button className="cwb-primary" type="submit" disabled={state.busy || !saved.ready || saved.pending || (!state.prompt.trim() && !state.files.length)}>{state.busy ? '处理中…' : '开始'}<span aria-hidden="true">→</span></button></div>
        </form>
        {(state.busy || !saved.ready || !workspace) && <p className="cwb-hint" role="status" aria-live="polite">{state.busy ? preparationLabels[state.stage] : !saved.ready ? '正在连接工作流设置…' : '请先选择或添加工作区。'}</p>}
        {saved.errorKind === 'settings' && <button className="cwb-text-button" onClick={() => selection.retry()}>重试连接工作流设置</button>}
      </>}
      {state.error && <div className="cwb-error" role="alert"><div className="cwb-error-heading"><span>暂时无法开始，需求和文件已保留。</span><button type="button" className="cwb-text-button" disabled={state.busy || !saved.ready || saved.pending} onClick={() => void start()}>重试</button></div><details><summary>查看原因</summary><p>{state.error}</p><button className="cwb-text-button" onClick={settings}>打开插件设置</button></details></div>}
      {workspaceState.state === 'error' && <p role="alert" className="cwb-error">工作区加载失败，请检查 DSH 连接。</p>}
      {!library && state.workflow && !selected && <p role="alert" className="cwb-error">所选工作流已不在当前目录中，请重新选择。</p>}
      <section className="cwb-catalog" aria-label="工作流目录">
        <div className="cwb-catalog-heading"><h2>{library ? '全部工作流' : '工作流'}</h2><label className="cwb-search"><WorkbenchIcon name="search" size={17} /><input aria-label="搜索工作流" placeholder="搜索工作流" value={query} onChange={event => setQuery(event.target.value)} /></label></div>
        <div className="cwb-categories" role="group" aria-label="工作流分类">{categories.map(item => <button key={item} aria-pressed={category === item} onClick={() => setCategory(item)}>{item}</button>)}</div>
        {library ? <div className="cwb-library"><nav aria-label="选择工作流详情" className="cwb-library-list">{visible.map(workflow => <button key={workflow.id} aria-current={detail?.id === workflow.id ? 'true' : undefined} onClick={() => store.set({ detail: workflow.id })}><WorkbenchIcon name={guideFor(workflow.id).icon} /><span><strong>{workflow.id}</strong><small>{copy(workflow).description}</small></span></button>)}{!visible.length && <p className="cwb-empty">没有匹配的工作流</p>}</nav>
          {detail ? <WorkflowDetail key={detail.id} workflow={detail} content={content} onUse={() => useWorkflow(detail.id)} onExample={() => useWorkflow(detail.id, guideFor(detail.id).example)} onSettings={settings} /> : <p className="cwb-empty">工作流目录尚未准备完成，请到插件设置查看准备状态。</p>}
        </div> : <div className="cwb-grid">{visible.map(workflow => <button type="button" key={workflow.id} className="cwb-card" aria-pressed={state.workflow === workflow.id} disabled={state.busy} onClick={() => { const next = state.workflow === workflow.id ? '' : workflow.id; store.set({ workflow: next, error: '' }); if (next) input.current?.focus() }}>
          <span className="cwb-card-icon"><WorkbenchIcon name={guideFor(workflow.id).icon} size={23} /></span><span className="cwb-card-copy"><strong>{workflow.id}</strong><span>{copy(workflow).description}</span></span><span className="cwb-card-corner" aria-hidden="true"><svg width="18" height="18" viewBox="0 0 20 20" fill="none"><circle cx="10" cy="10" r="8" fill={state.workflow === workflow.id ? '#da203e' : 'none'} stroke={state.workflow === workflow.id ? '#da203e' : 'currentColor'} strokeWidth="1.2" />{state.workflow === workflow.id && <path d="m6 10 2.6 2.6L14 7.2" stroke="white" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />}</svg></span>
        </button>)}{!visible.length && <p className="cwb-empty">没有匹配的工作流，请换一个关键词或分类。</p>}</div>}
      </section>
    </div>
  </main>
}

function WorkflowDetail({ workflow, content, onUse, onExample, onSettings }: { workflow: DynamicWorkflow; content: ContentStore; onUse(): void; onExample(): void; onSettings(): void }) {
  const { status } = useSyncExternalStore(content.subscribe, content.getSnapshot)
  const [error, setError] = useState(''), [pending, setPending] = useState(false)
  const guide = guideFor(workflow.id), row = status?.workflows?.find(item => item.id === workflow.id)
  const busy = pending || status?.busy || status?.phase === 'syncing' || status?.phase === 'initializing'
  const act = async (action: () => Promise<void>) => { setError(''); setPending(true); try { await action() } catch { setError('操作未完成，请在插件设置中查看日志后重试。') } finally { setPending(false) } }
  return <article className="cwb-detail" key={workflow.id}>
    <div className="cwb-detail-title"><span className="cwb-card-icon"><WorkbenchIcon name={guide.icon} size={25} /></span><span><small>{guide.category}</small><h2>{workflow.id}</h2></span></div>
    <p className="cwb-detail-summary">{copy(workflow).description}</p>
    <button className="cwb-primary" onClick={onUse}>使用此工作流 <span aria-hidden="true">→</span></button>
    <div className="cwb-guide-sections">{[['适合做什么', guide.scenes], ['需要提供什么', guide.inputs], ['可以获得什么', guide.outputs]].map(([title, entries]) => <section key={title as string}><h3>{title}</h3><ul>{(entries as string[]).map(line => <li key={line}>{line}</li>)}</ul></section>)}</div>
    <section className="cwb-example"><h3>试试这样描述需求</h3><p>{guide.example}</p><button className="cwb-text-button" onClick={onExample}>使用此示例 ↗</button><small>已有需求会保留，不会被示例覆盖。</small></section>
    <details className="cwb-version"><summary>版本与更新 {row?.version ? ` · ${row.version}` : ''}</summary><p>{row?.installed ? `已安装 ${row.version ?? ''}` : '安装状态尚未确认，请检查插件设置。'}{row?.latest && ` · 最新版本 ${row.latest}`}</p><div className="cwb-version-actions"><button className="cwb-text-button" disabled={busy} onClick={() => void act(content.check)}>检查更新</button>
      {row?.latest && (!row.version || newerVersion(row.latest, row.version)) && <button className="cwb-text-button" disabled={busy} onClick={() => void act(() => content.update(row.id, row.latest!))}>{row.installed ? '更新工作流' : '安装工作流'}</button>}
      {row?.previous && <button className="cwb-text-button" disabled={busy} onClick={() => void act(() => content.rollback(row.id))}>回退到 {row.previous}</button>}<button className="cwb-text-button" onClick={onSettings}>准备日志与管理</button></div><p>初始化和验证以当前工作区的实际环境为准。</p>{error && <p role="alert">{error}</p>}</details>
  </article>
}
