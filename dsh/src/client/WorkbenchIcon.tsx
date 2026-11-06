// ----------------------------------------------------------------------------------------------------------
// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.
// ----------------------------------------------------------------------------------------------------------

export function WorkbenchIcon({ name = 'grid', size = 20 }: { name?: string; size?: number }) {
  const paths: Record<string, string> = {
    grid: 'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z',
    code: 'm8 6-6 6 6 6 M16 6l6 6-6 6 M14 3l-4 18',
    flash: 'm13 2-9 12h7l-1 8 10-13h-7z',
    document: 'M5 3h14v18H5z M8 8h8 M8 12h8 M8 16h5',
    layers: 'm12 2 10 6-10 6L2 8z M2 12l10 6 10-6 M2 16l10 6 10-6',
    nodes: 'M10 2h4v4h-4z M2 18h6v4H2z M16 18h6v4h-6z M12 6v6 M5 18v-6h14v6',
    arrows: 'M3 7h17l-4-4 M20 7l-4 4 M21 17H4l4-4 M4 17l4 4',
    chart: 'M3 13h4v8H3z M10 8h4v13h-4z M17 3h4v18h-4z',
    gear: 'M9 3h6l1 3 3 1 2 5-2 5-3 1-1 3H9l-1-3-3-1-2-5 2-5 3-1z M9 12a3 3 0 1 0 6 0a3 3 0 1 0-6 0',
    folder: 'M2 6h8l2 3h10v12H2z M2 6V3h7l3 3h10v3',
    search: 'M16 16l6 6 M18 10a8 8 0 1 0-16 0a8 8 0 1 0 16 0',
    clip: 'm8 13 7-7a3 3 0 0 1 4 4L9 20a5 5 0 0 1-7-7L13 2 M6 15l9-9',
  }
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name] ?? paths.grid} /></svg>
}
