/**
 * Copyright (c) 2026 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#include <torch/library.h>
#include <torch/csrc/autograd/custom_function.h>
#include "pytorch_npu_helper.hpp"
#include <torch/extension.h>

at::Tensor rms_matmul_scale_custom_impl_npu(const at::Tensor& x, const at::Tensor& weight, double norm_eps) {
    // x: [B, S, N, D] → viewed as [M, K] where M=B*S, K=N*D
    // weight: [K, O]
    // output: [M, O] in float16
    int64_t B = x.size(0);
    int64_t S = x.size(1);
    int64_t M = B * S;
    int64_t K = x.size(2) * x.size(3);
    int64_t O = weight.size(1);

    at::Tensor result = at::empty({M, O}, x.options());

    // Workspace: matmul accumulation (M*O floats) + inv_rms per row (M floats)
    int64_t workspace_elems = M * O + M;
    at::Tensor workspace = at::empty({workspace_elems}, x.options().dtype(at::kFloat));

    EXEC_NPU_CMD(aclnnRmsMatmulScaleCustom, x, weight, result, workspace);
    return result;
}

TORCH_LIBRARY_IMPL(myops, PrivateUse1, m) {
    m.impl("rms_matmul_scale_custom", &rms_matmul_scale_custom_impl_npu);
}

PYBIND11_MODULE(TORCH_EXTENSION_NAME, m) {
    m.def("rms_matmul_scale_custom", &rms_matmul_scale_custom_impl_npu, "RMSNorm + MatMul + Scale Fused Custom");
}
