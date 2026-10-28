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

at::Tensor quant_matmul_custom_impl_npu(const at::Tensor& a, const at::Tensor& b,
                                         const at::Tensor& scale, const at::Tensor& per_token_scale) {
    // a: [M, K] int8, b: [N, K] int8 -> output: [M, N] in float16
    // B is stored as [N, K] (ColumnMajor(K, N)), so N = b.size(0)
    int64_t M = a.size(0);
    int64_t N = b.size(0);

    at::Tensor result = at::empty({M, N}, at::TensorOptions().dtype(at::kHalf).device(a.device()));

    EXEC_NPU_CMD(aclnnQuantMatmulCustom, a, b, scale, per_token_scale, result);
    return result;
}

TORCH_LIBRARY_IMPL(myops, PrivateUse1, m) {
    m.impl("quant_matmul_custom", &quant_matmul_custom_impl_npu);
}

PYBIND11_MODULE(TORCH_EXTENSION_NAME, m) {
    m.def("quant_matmul_custom", &quant_matmul_custom_impl_npu, "Quantized Matrix Multiplication Custom (CV)");
}
