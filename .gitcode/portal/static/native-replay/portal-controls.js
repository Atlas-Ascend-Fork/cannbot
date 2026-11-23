// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

// Homepage controls for the native, offline DSH session.
(() => {
  const params = new URLSearchParams(location.search);
  globalThis.cannbotReplayLogo = params.get('logo') || '../img/cannbot-dsh-mark.svg';
  const play = params.get('play') || '开始回放';
  const again = params.get('again') || '重新播放';
  let trigger;
  let started = false;
  let sawRunning = false;
  let autoplay = params.has('restart');
  if (autoplay) {
    const clean = new URL(location.href);
    clean.searchParams.delete('restart');
    history.replaceState(history.state, '', clean);
  }

  function sync() {
    const card = document.querySelector('[data-composer-card]');
    if (!card) return;
    const hero = card.closest('.wSkVaW_composerHero');
    const host = hero || card;
    const workspace = hero?.querySelector('.wSkVaW_heroWorkspaceRow');
    if (workspace) workspace.inert = true;
    const running = !!document.querySelector('[data-chat-running]');
    if (running) sawRunning = true;
    const finished = sawRunning && !running;
    const send = card.querySelector('button[aria-label="发送消息"],button[aria-label="Send message"]');
    const editor = card.querySelector('[contenteditable]');
    // The native entry fills the fixed draft before the composer is locked.
    if (!started && (!editor?.textContent.trim() || !send || send.disabled)) return;
    for (const child of card.children) {
      if (!child.classList.contains('portal-replay-trigger')) child.inert = true;
    }
    if (!trigger) {
      trigger = document.createElement('button');
      trigger.type = 'button';
      trigger.className = 'portal-replay-trigger';
      trigger.addEventListener('click', () => {
        if (started) {
          if (!sawRunning || document.querySelector('[data-chat-running]')) return;
          const url = new URL(location.href);
          url.hash = '';
          url.searchParams.set('restart', '1');
          location.replace(url);
          return;
        }
        const submit = document.querySelector('[data-composer-card]')?.querySelector('button[aria-label="发送消息"],button[aria-label="Send message"]');
        if (!submit || submit.disabled) return;
        started = true;
        submit.click();
        sync();
      });
    }
    if (trigger.parentElement !== host) host.append(trigger);
    const locked = started && !finished;
    if (trigger.disabled !== locked) trigger.disabled = locked;
    trigger.setAttribute('aria-label', finished ? again : play);
    if (finished && !trigger.textContent) trigger.textContent = again + ' ↻';
    if (autoplay && !started) {
      autoplay = false;
      trigger.click();
    }
  }

  const observer = new MutationObserver(sync);
  observer.observe(document.documentElement, {
    childList: true, subtree: true, characterData: true, attributes: true,
    attributeFilter: ['disabled', 'contenteditable'],
  });
})();
