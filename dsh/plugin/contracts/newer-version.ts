// ----------------------------------------------------------------------------------------------------------
// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.
// ----------------------------------------------------------------------------------------------------------

export function newerVersion(candidate: string, current: string): boolean {
  const next = /^(\d+)\.(\d+)\.(\d+)$/.exec(candidate)
  const old = /^(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$/.exec(current)
  if (!next || !old) return false
  for (let index = 1; index < 4; index++) {
    const difference = Number(next[index]) - Number(old[index])
    if (difference) return difference > 0
  }
  return /^\d+\.\d+\.\d+-/.test(current)
}
