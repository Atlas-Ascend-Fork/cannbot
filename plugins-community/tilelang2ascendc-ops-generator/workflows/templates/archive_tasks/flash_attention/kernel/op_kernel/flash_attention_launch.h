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

/* flash_attention_launch — launch_* 启动包装声明（gcc 侧包含） */
#ifndef FLASH_ATTENTION_LAUNCH_H
#define FLASH_ATTENTION_LAUNCH_H

#include <cstdint>

#ifndef GM_ADDR
#define GM_ADDR void*
#endif

// 兼容 utils/torch_kernel_helper.h 的 EXEC_KERNEL_CMD
#ifndef ACLRT_LAUNCH_KERNEL
#define ACLRT_LAUNCH_KERNEL(kernel_name) launch_##kernel_name
#endif

extern "C" {

void launch_flash_attention_gen_bf16(uint32_t numBlocks, void* stream, GM_ADDR q, GM_ADDR k, GM_ADDR v, GM_ADDR output,
                                     GM_ADDR workspace_s, GM_ADDR workspace_p, GM_ADDR workspace_o, GM_ADDR tiling);

void launch_flash_attention_gen_fp16(uint32_t numBlocks, void* stream, GM_ADDR q, GM_ADDR k, GM_ADDR v, GM_ADDR output,
                                     GM_ADDR workspace_s, GM_ADDR workspace_p, GM_ADDR workspace_o, GM_ADDR tiling);

void launch_flash_attention_gen_fp32(uint32_t numBlocks, void* stream, GM_ADDR q, GM_ADDR k, GM_ADDR v, GM_ADDR output,
                                     GM_ADDR workspace_s, GM_ADDR workspace_p, GM_ADDR workspace_o, GM_ADDR tiling);
}

#endif // FLASH_ATTENTION_LAUNCH_H
