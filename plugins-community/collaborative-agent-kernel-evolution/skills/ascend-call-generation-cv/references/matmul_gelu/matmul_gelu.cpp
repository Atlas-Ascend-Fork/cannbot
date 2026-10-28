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

at::Tensor matmul_gelu_custom_impl_npu(const at::Tensor& a, const at::Tensor& b) {
    // a: [M, K], b: [K, N] → output: [M, N] in float16
    // CV operator: cube does matmul into fp32 workspace, vector does GELU + cast to fp16
    int64_t M = a.size(0);
    int64_t K = a.size(1);
    int64_t N = b.size(1);

    at::Tensor result = at::empty({M, N}, a.options());

    // Workspace for fp32 matmul accumulation (M * N floats)
    int64_t workspace_elems = M * N;
    at::Tensor workspace = at::empty({workspace_elems}, a.options().dtype(at::kFloat));

    EXEC_NPU_CMD(aclnnMatmulGeluCustom, a, b, result, workspace);
    return result;
}

TORCH_LIBRARY_IMPL(myops, PrivateUse1, m) {
    m.impl("matmul_gelu_custom", &matmul_gelu_custom_impl_npu);
}

PYBIND11_MODULE(TORCH_EXTENSION_NAME, m) {
    m.def("matmul_gelu_custom", &matmul_gelu_custom_impl_npu, "MatMul + GELU Fused Custom");
}
