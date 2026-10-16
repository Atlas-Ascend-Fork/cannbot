/**
 * Copyright (c) 2026 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#include "kernel_operator.h"
#include "lib/matmul_intf.h"
#include "tensorutils.h"
#include "kernel_cube.h"
#include "kernel_vec.h"


extern "C" __global__ __aicore__ void kernel(GM_ADDR q, GM_ADDR k, GM_ADDR v, GM_ADDR out, GM_ADDR workspace, GM_ADDR tiling) {
    KERNEL_TASK_TYPE_DEFAULT(KERNEL_TYPE_MIX_AIC_1_2);
    GET_TILING_DATA(tiling_data, tiling);
    PipeBarrier<PIPE_ALL>();
    int S1 = tiling_data.S1;
    int S2 = tiling_data.S2;
    int D = tiling_data.D;
    int BH = tiling_data.BH;
    float scale = tiling_data.scale;
    if ASCEND_IS_AIC{
        kernel_cube(q, k, v, out, workspace, S1, S2, D, BH, scale);
    }
    if ASCEND_IS_AIV{
        kernel_vec(q, k, v, out, workspace, S1, S2, D, BH, scale);
    }

}
