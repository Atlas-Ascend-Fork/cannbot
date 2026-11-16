/*
 * Copyright (c) 2026 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 * ----------------------------------------------------------------------------------------------------------
 */

/*
 * flash_attention_gen 算子声明
 */
#ifndef OPS_H
#define OPS_H

#include <torch/extension.h>

namespace ascend_kernel {

at::Tensor flash_attention_gen_fp16(const at::Tensor& q, const at::Tensor& k, const at::Tensor& v, bool isCausal);
at::Tensor flash_attention_gen_bf16(const at::Tensor& q, const at::Tensor& k, const at::Tensor& v, bool isCausal);
at::Tensor flash_attention_gen_fp32(const at::Tensor& q, const at::Tensor& k, const at::Tensor& v, bool isCausal);

} // namespace ascend_kernel

#endif // OPS_H
