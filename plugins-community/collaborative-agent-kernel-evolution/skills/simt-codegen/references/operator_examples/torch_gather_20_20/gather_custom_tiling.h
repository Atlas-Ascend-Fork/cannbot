/* -------------------------------------------------------------------------
 * This file is part of the MindStudio project.
 * Copyright (c) 2025 Huawei Technologies Co.,Ltd.
 *
 * MindStudio is licensed under Mulan PSL v2.
 * You can use this software according to the terms and conditions of the Mulan PSL v2.
 * You may obtain a copy of Mulan PSL v2 at:
 *
 *          http://license.coscl.org.cn/MulanPSL2
 *
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND,
 * EITHER EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT,
 * MERCHANTABILITY OR FIT FOR A PARTICULAR PURPOSE.
 * See the Mulan PSL v2 for more details.
 * ------------------------------------------------------------------------- */


#ifndef GATHER_CUSTOM_TILING_H
#define GATHER_CUSTOM_TILING_H
#include <cstdint>

struct GatherCustomTilingData {
    uint32_t totalElements;      // Total number of output elements (== numel(index))
    uint32_t threadsPerBlock;    // Number of threads per block (256)
    uint32_t dtypeCode;          // 0=float32,1=float16,2=bfloat16,3=int8,4=int32,5=int64
    uint32_t indexDtypeCode;     // 0=int32, 1=int64
    uint32_t ndim;               // Number of dimensions (index/output rank)
    uint32_t dim;                // Gather dimension (normalized, >=0)
    // Metadata read DIRECTLY by the VF from the immutable GM tiling buffer (no mutable __gm__
    // globals → no cold-launch race, which was the round_2 flakiness root cause). Max 8D.
    uint32_t outputShape[8];     // output shape (== index shape)
    uint32_t inputStrides[8];    // row-major strides of the input tensor x
    uint32_t xShape[8];          // shape of input x (for the OOB index bounds-guard)
};

#endif // GATHER_CUSTOM_TILING_H
