// ----------------------------------------------------------------------------------------------------------
// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.
// ----------------------------------------------------------------------------------------------------------

/** Per-activation UI preference: enabling the plugin always starts with its interface on. */
export interface PresentationController {
  getSnapshot(): boolean
  subscribe(listener: () => void): () => void
  setEnabled(enabled: boolean): void
  dispose(): void
}
export function createPresentationController(mount: () => () => void): PresentationController {
  let enabled = true
  let stopped = false
  let unmount: (() => void) | undefined = mount()
  const listeners = new Set<() => void>()
  return {
    getSnapshot: () => enabled,
    subscribe(listener) { listeners.add(listener); return () => { listeners.delete(listener) } },
    setEnabled(next) {
      if (stopped || next === enabled) return
      if (next) unmount = mount()
      else { unmount?.(); unmount = undefined }
      enabled = next
      for (const listener of listeners) listener()
    },
    dispose() { if (stopped) return; stopped = true; unmount?.(); unmount = undefined; listeners.clear() },
  }
}
