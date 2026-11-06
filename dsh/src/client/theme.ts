// ----------------------------------------------------------------------------------------------------------
// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.
// ----------------------------------------------------------------------------------------------------------

import type { ThemeTokenOverrides } from '@deepseek-ai/dsh-client-ui-theme/client'

/** Portal design-v2 palette, applied through the documented theme override layer. */
export const cannTheme: ThemeTokenOverrides = Object.fromEntries(Object.entries({
  '--dsw-alias-bg-base': ['#ffffff', '#101114'],
  '--dsw-alias-bg-layer-1': ['#ffffff', '#17191e'],
  '--dsw-alias-bg-layer-2': ['#ffffff', '#1d2026'],
  '--dsw-alias-bg-layer-3': ['#f6f8fa', '#252830'],
  '--dsw-specific-sidebar-fill': ['#f6f8fa', '#14161b'],
  '--dsw-specific-input-major': ['#ffffff', '#1d2026'],
  '--dsw-specific-sidebar-nav-item-active': ['#fdeef0', '#392029'],
  '--dsw-specific-sidebar-nav-item-active-accent': ['#fdeef0', '#392029'],
  '--dsw-alias-label-primary': ['#17181d', '#f3f4f6'],
  '--dsw-alias-label-primary-foreground': ['#ffffff', '#ffffff'],
  '--dsw-alias-label-primary-inverted': ['#ffffff', '#ffffff'],
  '--dsw-alias-label-primary-dimmed': ['#30343e', '#dde1e8'],
  '--dsw-alias-label-primary-bluish': ['#7f0f26', '#ff9aab'],
  '--dsw-alias-label-secondary': ['#59637a', '#b0b8c7'],
  '--dsw-alias-label-tertiary': ['#727d91', '#929db0'],
  '--dsw-alias-brand-primary': ['#da203e', '#ef4560'],
  '--dsw-alias-brand-text': ['#17181d', '#f3f4f6'],
  '--dsw-alias-button-primary-hover': ['#b11430', '#ff647d'],
  '--dsw-alias-button-info-fill': ['#da203e', '#da203e'],
  '--dsw-alias-button-info-hover': ['#b11430', '#b11430'],
  '--dsw-alias-state-business-primary': ['#da203e', '#ff8297'],
  '--dsw-alias-state-business-tertiary': ['#fdeef0', '#392029'],
  '--dsw-alias-link': ['#b11430', '#ff9aab'],
  '--dsw-focus-ring-color': ['#da203e', '#ff8297'],
  '--dsw-alias-border-l1': ['#f0f1f5', '#252830'],
  '--dsw-alias-border-l2': ['#e6e9ef', '#323641'],
  '--dsw-alias-border-l3': ['#dce0e8', '#414754'],
  '--dsw-alias-border-l4': ['#ced4df', '#505867'],
  '--dsw-alias-interactive-bg-hover': ['#eef0f4', '#252830'],
  '--dsw-alias-interactive-bg-active': ['#fdeef0', '#392029'],
  '--dsw-specific-bubble': ['#fff3f5', '#302027'],
  '--dsw-specific-bubble-highlight': ['#fbd6dd', '#59303d'],
  '--dsw-radius-panel': ['18px', '18px'],
  '--dsw-radius-xl': ['14px', '14px'],
  '--dsw-radius-lg': ['12px', '12px'],
  '--dsw-radius-md': ['10px', '10px'],
  '--cann-grid': ['#e6e9ef', '#323641'],
  '--cann-night': ['#0e0f12', '#0e0f12'],
  '--cann-night-label': ['#dde1e8', '#dde1e8'],
}).map(([name, values]) => [name, { light: values[0]!, dark: values[1]! }]))
