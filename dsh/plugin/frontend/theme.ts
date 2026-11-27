// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import type { ThemeTokenOverrides } from '@deepseek-ai/dsh-client-ui-theme/client'

/** Accent only: DSH owns surfaces, typography, radii and light/dark themes. */
export const cannTheme: ThemeTokenOverrides = Object.fromEntries([
  '--dsw-alias-brand-primary', '--dsw-alias-button-primary-hover',
  '--dsw-alias-button-info-fill', '--dsw-alias-button-info-hover',
  '--dsw-alias-state-business-primary', '--dsw-alias-link', '--dsw-focus-ring-color',
].map(name => [name, { light: '#C7000B', dark: '#C7000B' }]))
