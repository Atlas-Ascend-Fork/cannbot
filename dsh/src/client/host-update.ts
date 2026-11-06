// ----------------------------------------------------------------------------------------------------------
// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.
// ----------------------------------------------------------------------------------------------------------

import type { Change } from './plugin-update.ts'
import { en, zh } from './locales.ts'

/** This notice belongs to the in-flight update, so removing the plugin must not remove it. */
export async function updateOnHost(name: string, version: string): Promise<{ result: Change; restore?: Change }> {
  const words = document.documentElement.lang.startsWith('en') ? en : zh
  const notice = document.createElement('div')
  notice.setAttribute('role', 'status')
  notice.setAttribute('aria-live', 'polite')
  notice.dataset.cannbotUpdate = 'progress'
  Object.assign(notice.style, { position: 'fixed', bottom: '24px', right: '24px', zIndex: '2147483647',
    maxWidth: 'min(380px, calc(100vw - 48px))', padding: '16px', borderRadius: '12px',
    background: 'var(--dsw-alias-bg-base, white)', color: 'var(--dsw-alias-label-primary, #222)',
    border: '1px solid var(--dsw-alias-border-l2, #ddd)', boxShadow: '0 8px 32px #0002', fontSize: '13px', lineHeight: '1.6' })
  const text = document.createElement('span')
  text.textContent = `${words.updateRunning} ${version} · ${words.updateBackground}`
  notice.append(text)
  document.body.append(notice)
  try {
    const response = await fetch(new URL('api/cannbot-dsh/update', document.baseURI), {
      method: 'POST', credentials: 'same-origin', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ name, version }),
      // No plugin-lifetime abort: its own uninstall is expected during the transaction.
    })
    if (!response.ok) throw new Error('Host update unavailable')
    const answer = await response.json() as { result: Change; restore?: Change }
    if (!answer?.result || typeof answer.result.application !== 'string') throw new Error('Invalid update result')
    const succeeded = (result: Change) => !result.error && ['applied', 'restart-required'].includes(result.application)
    text.textContent = succeeded(answer.result)
      ? `${answer.result.application === 'restart-required' ? words.updateRestart : words.updateDone} (${version})`
      : answer.restore ? succeeded(answer.restore) ? words.updateRestored : words.updateRepair : words.updateFailed
    return answer
  } catch (error) {
    text.textContent = words.updateConnectionLost
    throw error
  } finally {
    const close = document.createElement('button')
    close.type = 'button'; close.textContent = '×'; close.setAttribute('aria-label', words.updateDismiss)
    Object.assign(close.style, { marginLeft: '12px', border: '0', background: 'transparent', color: 'inherit', cursor: 'pointer', fontSize: '18px' })
    close.addEventListener('click', () => notice.remove(), { once: true })
    notice.append(close)
  }
}
