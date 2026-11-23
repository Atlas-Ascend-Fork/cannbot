// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

/** Use the native composer block surface; the Host separately enforces execution. */
export function freezeSessionInputs(modes: { subscribe(listener: () => void): () => void; getSnapshot(): { sessions: { sessionId: string; frozen?: boolean }[] } }, blocks: {
  storeFor(id: string): { getSnapshot(): { reason: string } | undefined }
  set(id: string, value: { reason: string } | undefined): void
}) {
  const owned = new Map<string, { reason: string }>()
  const refresh = () => {
    const frozen = new Set(modes.getSnapshot().sessions.filter(item => item.frozen).map(item => item.sessionId))
    for (const [id, value] of owned) if (!frozen.has(id)) { if (blocks.storeFor(id).getSnapshot() === value) blocks.set(id, undefined); owned.delete(id) }
    for (const id of frozen) if (!blocks.storeFor(id).getSnapshot()) {
      const value = { reason: '会话所属工作流已变更，历史记录已冻结。请在当前工作区新建会话。' }
      owned.set(id, value); blocks.set(id, value)
    }
  }
  const unsubscribe = modes.subscribe(refresh); refresh()
  return () => { unsubscribe(); for (const [id, value] of owned) if (blocks.storeFor(id).getSnapshot() === value) blocks.set(id, undefined) }
}
