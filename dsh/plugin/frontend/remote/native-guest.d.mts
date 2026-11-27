// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

export interface BrowserBridge {
  acquire(key: string): Promise<{ lease: string; partition: string }>
  release(lease: string): Promise<unknown>
  onOpenRequested?(lease: string, listener: (url: string) => void): () => void
}
export interface GuestState { status?: 'loading' | 'ready' | 'error'; error?: string; notice?: string }
export function remoteUrl(value: string): string
export function desktopBrowser(): BrowserBridge
export function createNativeGuest(options: {
  bridge: BrowserBridge; host: HTMLElement; url: string; workspaceKey: string;
  onState?(state: GuestState): void
  onCreateWorkspace?(): void
  onLocation?(scope: { workspaceId?: string; sessionId?: string }): void
}): { reload(): boolean; dispose(): Promise<void> }
