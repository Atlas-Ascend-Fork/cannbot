/**
 * Copyright (c) 2026 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#include "register/tilingdata_base.h"

namespace optiling {
BEGIN_TILING_DATA_DEF(FlashAttentionCustomTilingData)
  TILING_DATA_FIELD_DEF(int32_t, S1);
  TILING_DATA_FIELD_DEF(int32_t, S2);
  TILING_DATA_FIELD_DEF(int32_t, D);
  TILING_DATA_FIELD_DEF(int32_t, BH);
  TILING_DATA_FIELD_DEF(float, scale);
END_TILING_DATA_DEF;

REGISTER_TILING_DATA_CLASS(FlashAttentionCustom, FlashAttentionCustomTilingData)
}
