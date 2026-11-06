// ----------------------------------------------------------------------------------------------------------
// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.
// ----------------------------------------------------------------------------------------------------------

import { useState, useSyncExternalStore } from 'react'
import type { PropsLocale } from '@deepseek-ai/dsh-client-ui-slots'
import type { ContentStore } from './content-store.ts'
import { newerVersion } from './plugin-update.ts'
import { workflowCopy } from './workflow-copy.ts'
export function ContentCard({ content, t }: { content: ContentStore } & PropsLocale<'cannbotDsh'>) {
  const { status } = useSyncExternalStore(content.subscribe, content.getSnapshot)
  const [failed, setFailed] = useState(false)
  const busy = status?.busy || status?.phase === 'syncing' || status?.phase === 'initializing'
  const act = (action: () => Promise<void>) => { setFailed(false); void action().catch(() => setFailed(true)) }
  return <section className="cannbot-dsh-update cannbot-dsh-content" aria-label={t('contentTitle')}>
    <div className="cannbot-dsh-update-heading"><h4>{t('contentTitle')}</h4>
      {status?.catalogVersion && <span>{t('contentCatalog')} {status.catalogVersion}</span>}</div>
    <div className="cannbot-dsh-update-actions">
      <button type="button" className="cannbot-dsh-update-button" disabled={busy} onClick={() => act(content.sync)}>{busy ? t('contentBusy') : t('contentSync')}</button>
      <button type="button" className="cannbot-dsh-update-recheck" disabled={busy} onClick={() => act(content.check)}>{t('contentCheck')}</button>
    </div>
    <p role={failed || status?.phase === 'error' ? 'alert' : 'status'} aria-live="polite">
      {failed || status?.phase === 'error' ? t('contentFailed') : status?.phase === 'initializing' ? t('contentInitializing') : status?.phase === 'syncing' ? t('contentDownloading') : status?.fallback ? t('contentFallback') : t('contentReady')}
    </p>
    {status && <p>{status.plugins.length} {t('contentWorkflows')}</p>}
    <div className="cannbot-dsh-workflow-packages">
      {status?.workflows?.map(row => {
        const available = row.latest && (!row.version || newerVersion(row.latest, row.version))
        const copy = workflowCopy(row, t)
        return <div className="cannbot-dsh-workflow-package" key={row.id}>
          <div><strong lang="en">{copy.name}</strong><small>{copy.description}</small><small lang="en">{row.package}</small>
            <small>{row.version ? `${t('contentVersion')} ${row.version}` : t('contentNotInstalled')}
              {available && ` · ${t('contentLatest')} ${row.latest}`}{row.pinned && ` · ${t('contentPinned')}`}</small>
            {row.error && <small role="alert">{row.error}</small>}</div>
          <div className="cannbot-dsh-workflow-package-actions">
            {available ? <button type="button" className="cannbot-dsh-update-recheck" disabled={busy}
              aria-label={`${row.installed ? t('contentUpdate') : t('contentInstall')} ${copy.name}`}
              onClick={() => act(() => content.update(row.id, row.latest!))}>{row.installed ? t('contentUpdate') : t('contentInstall')}</button>
              : <small>{row.installed ? row.latest ? t('contentUpToDate') : t('contentUnchecked') : t('contentUnavailable')}</small>}
            {row.previous && <button type="button" className="cannbot-dsh-update-recheck" disabled={busy}
              aria-label={`${t('contentRollback')} ${copy.name}`} onClick={() => act(() => content.rollback(row.id))}>{t('contentRollback')} {row.previous}</button>}
          </div>
        </div>
      })}
    </div>
    {(status?.log || status?.message) && <details><summary>{t('contentLogs')}</summary><pre>{status.message}{'\n'}{status.log}</pre></details>}
  </section>
}
