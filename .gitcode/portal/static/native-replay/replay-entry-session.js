/*!
 * CANNBot portal adaptations:
 * Copyright (c) 2026 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 *
 * Source: https://cann.cannbot.cn/dsh-native-replay-v3/replay-entry-session.js
 * Bundled components retain their respective copyrights and licenses.
 */

(() => {
  const prompt = new URLSearchParams(location.search).get("prompt") || "\u8bf7\u5f00\u53d1\u4e00\u4e2a\u652f\u6301FP32\u7684add\u7b97\u5b50\uff0c\u5e76\u9a8c\u8bc1\u7cbe\u5ea6\u3002";
  let requested = false, filled = false;
  const editor = () => document.querySelector('[data-slot="conversation.composer"] [contenteditable="true"]');
  const attempt = () => {
    if (!requested || filled) return;
    const input = editor();
    if (!input) return;
    filled = true;
    observer.disconnect();
    if (!input.textContent.trim()) {
      input.focus({preventScroll:true});
      document.execCommand('insertText', false, prompt);
    }
  };
  const lockModel = () => {
    for(const b of document.querySelectorAll('[data-slot="conversation.composer"] button[aria-haspopup="menu"]')){
      if ((b.getAttribute('aria-label')||'').includes('DeepSeek-V4-Flash') || (b.title||'').includes('DeepSeek-V4-Flash')) {
        if(!b.disabled) b.disabled=true;
        b.classList.add('cannbot-fixed-model');
      }
    }
  };
  new MutationObserver(lockModel).observe(document.documentElement,{childList:true,subtree:true,attributes:true,attributeFilter:['aria-label','disabled']});
  const style=document.createElement('style');
  style.textContent='.cannbot-fixed-model:disabled{cursor:default;opacity:1;pointer-events:none}.cannbot-fixed-model:disabled svg:last-child{visibility:hidden}';
  style.textContent += '[data-slot="conversation.session.header.corner"],button[aria-label="打开右侧边栏"],button[aria-label="收起右侧边栏"],button[aria-label="全屏"],button[aria-label="分栏"],button[aria-label="新标签页"]{display:none!important}';
  document.addEventListener('click',event=>{
    const a=event.target.closest?.('a[href]');
    if(!a || a.dataset.replayDownload) return;
    const url=new URL(a.href,document.baseURI);
    if(url.origin!==location.origin || !["../replay/npu-validation.log", "../replay/STATE.md"].some(path => url.href === new URL(path, document.baseURI).href)) return;
    event.preventDefault();event.stopImmediatePropagation();
    const link=document.createElement('a');
    link.href=url.href;link.download=url.pathname.split('/').at(-1);link.dataset.replayDownload='true';link.hidden=true;
    document.body.appendChild(link);link.click();link.remove();
  },true);
  style.textContent += 'button[data-schedule-reminder-entry],button[aria-label="更多操作"]{display:none!important}';
  document.head.append(style);
  const observer = new MutationObserver(attempt);
  window.startCANNBotReplay = () => {
    requested = true;
    observer.observe(document.documentElement,{childList:true,subtree:true});
    attempt();
  };
  if(new URLSearchParams(location.search).get("view")==="direct") window.startCANNBotReplay();
})();
