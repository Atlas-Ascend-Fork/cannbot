// ----------------------------------------------------------------------------------------------------------
// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.
// ----------------------------------------------------------------------------------------------------------

import { useEffect, useSyncExternalStore } from 'react'
import type { PropsLocale } from '@deepseek-ai/dsh-client-ui-slots'
import type { PluginUpdater } from './plugin-update.ts'

export function PluginUpdateCard({ updater, t }: { updater: PluginUpdater } & PropsLocale<'cannbotDsh'>) {
  const state = useSyncExternalStore(updater.subscribe, updater.getSnapshot)
  useEffect(() => { void updater.check() }, [updater])
  const busy = state.phase === 'checking' || state.phase === 'updating'
  const canUpdate = state.phase === 'available'
  const message = state.phase === 'latest' ? t('updateLatest')
    : state.phase === 'available' ? t('updateAvailable')
    : state.phase === 'updating' ? t('updateRunning')
    : state.phase === 'done' ? t('updateDone')
    : state.phase === 'restart' ? t('updateRestart')
    : state.phase === 'manual' ? t('updateManual')
    : state.phase === 'incompatible' ? t('updateIncompatible')
    : state.phase === 'error' ? t('updateFailed') : ''
  return <section className="cannbot-dsh-update" aria-label={t('updateTitle')}>
    <div className="cannbot-dsh-update-heading"><h4>{t('updateTitle')}</h4>
      {state.current && <span>{t('updateCurrent')} {state.current}</span>}</div>
    <div className="cannbot-dsh-update-actions">
      {state.phase === 'manual' && state.release ? <>
        <a className="cannbot-dsh-update-button" href={state.release.tarball} download rel="noreferrer">{t('updateDownload')} {state.release.version}</a>
        <button type="button" className="cannbot-dsh-update-recheck" onClick={() => { void updater.check() }}>{t('updateCheck')}</button>
      </> :
      <button type="button" className="cannbot-dsh-update-button" disabled={busy}
        onClick={() => { void (canUpdate ? updater.update() : updater.check()) }}>
        {state.phase === 'checking' ? t('updateChecking') : state.phase === 'updating' ? t('updateRunning')
          : canUpdate ? `${t('updateTo')} ${state.release?.version}` : t('updateCheck')}
      </button>
      }
    </div>
    {message && <p role={state.phase === 'error' ? 'alert' : 'status'} aria-live="polite">{message}</p>}
  </section>
}
