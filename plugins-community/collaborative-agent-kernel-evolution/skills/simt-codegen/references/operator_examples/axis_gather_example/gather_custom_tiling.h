/* ----------------------------------------------------------------------------------------------------------
 * Copyright (c) 2026 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 * ---------------------------------------------------------------------------------------------------------- */

#ifndef GATHER_CUSTOM_TILING_H
#define GATHER_CUSTOM_TILING_H
#include <cstdint>

// Tiling contract for axis-gather (np.take / index_select / GatherV2).
//
// Every field here is read by the kernel and MUST be set in TilingFunc
// (SKILL.md rule 6) — an unset field arrives on-device as 0, which would give
// dim3(0) / div-by-zero / wrong dtype branch (error 507035).
//
// Unlike gather_20_20's tiling (outputShape[8]/inputStrides[8]/xShape[8]), this
// operator's addressing collapses to an outer/axis/inner triple. For a 1-D index
// tensor the gathered coordinate is derived from the OUTPUT position, not from a
// per-element index read, so no N-D coord array is needed. See SIMT_GAP_REPORT.md G5.
struct GatherCustomTilingData {
    uint32_t totalElements;    // numel(y) == outerSize * indexLen * innerSize
    uint32_t threadsPerBlock;  // threads per block (256) — arg to dim3() in asc_vf_call
    uint32_t dtypeCode;        // 0=float32,1=float16,2=bfloat16,3=int32
    uint32_t indexDtypeCode;   // 0=int32, 1=int64
    uint32_t outerSize;        // prod(x.shape[:axis])
    uint32_t axisSize;         // x.shape[axis]  (bound for the OOB index guard)
    uint32_t innerSize;        // prod(x.shape[axis+1:])
    uint32_t indexLen;         // numel(indices) — the gathered extent of the output
};

// GET_TILING_DATA is NOT provided by the CANN SDK — it is emitted by msopgen
// scaffolding into generated project sources (see msopgen/interface/op_file_aicore.py:156).
// SKILL.md and pass_details_model_b.md use it in kernel code without noting this
// dependency, so a standalone kernel TU fails with "use of undeclared identifier 'td'".
// Guarded fallback keeps the skill's prescribed entry structure compiling standalone;
// inside a real msopgen project the generated definition wins. See SIMT_GAP_REPORT.md G6.
#ifndef GET_TILING_DATA
#define GET_TILING_DATA(name, tiling_ptr) \
    const __gm__ GatherCustomTilingData& name = \
        *reinterpret_cast<__gm__ const GatherCustomTilingData*>(tiling_ptr)
#endif

#endif // GATHER_CUSTOM_TILING_H
