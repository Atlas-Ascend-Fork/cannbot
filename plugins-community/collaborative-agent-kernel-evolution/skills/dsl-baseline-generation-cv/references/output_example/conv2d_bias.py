# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

import tile.language as tl
import torch


@ascend_kernel
def conv2d_bias_kernel(fmap, weight, bias, output,
                       batch, Cin, H, W, Cout, kH, kW, sH, sW, pH, pW):
    # ----------------------------------------------------------------------
    # 1. Convolution Parameters
    # ----------------------------------------------------------------------
    # General Conv2d uses tl.conv2d_dot() which maps to Catlass BlockConv.
    # BlockConv internally handles:
    #   - im2col via Load3Dv2 (L1 → L0A)
    #   - Matrix multiply via Mmad (L0A × L0B → L0C)
    #   - Bias addition via BT buffer
    #   - Output via Fixpipe (L0C → GM)
    # No Vector scope needed for conv + bias only (ConvBias pattern).

    DTYPE_OUT = tl.half

    conv_params = tl.make_conv_params(
        H=H, W=W, kH=kH, kW=kW,
        strideH=sH, strideW=sW,
        padH=pH, padW=pW,
        Cin=Cin, Cout=Cout,
        bias_ptr=bias
    )

    Ho = (H + 2 * pH - kH) // sH + 1
    Wo = (W + 2 * pW - kW) // sW + 1

    # ----------------------------------------------------------------------
    # 2. Layouts (hardware-specific formats)
    # ----------------------------------------------------------------------
    # Feature map: NC1HWC0 format (C0=16 for fp16)
    #   shape: [batch, D=1, Cin1, H*W, C0]
    # Weight: FracZ format (KDC1KHKWN1N0C0)
    #   shape: [Kd*Cin1*kH*kW, Cout1, N0=16, C0=16]
    # Output: NC1HWC0 format
    #   shape: [batch, D=1, Cout1, Ho*Wo, C0]
    C0 = 16
    Cin1 = tl.cdiv(Cin, C0)
    Cout1 = tl.cdiv(Cout, C0)
    layout_fmap = tl.make_ndc1hwc0_layout(batch, 1, Cin1, H * W, C0)
    layout_weight = tl.make_fracz_layout(Cin1 * kH * kW, Cout1, C0)
    layout_out = tl.make_ndc1hwc0_layout(batch, 1, Cout1, Ho * Wo, C0)

    # ----------------------------------------------------------------------
    # 任务核间划分说明
    # ----------------------------------------------------------------------
    # BlockConv + ConvBias handles task partitioning internally via
    # Conv3dIdentityBlockSwizzle. The block scheduler divides the output
    # tensor along (batch, Cout1, Ho*Wo) dimensions and assigns tiles
    # to AICore units. Each core processes one or more output tiles.
    # No manual scheduling loop needed — BlockConv manages everything.

    aicore_id = tl.program_id()
    aicore_num = tl.num_programs()

    # ----------------------------------------------------------------------
    # 3. Cube-only Conv2d + Bias (ConvBias pattern)
    # ----------------------------------------------------------------------
    # tl.conv2d_dot() encapsulates the full convolution pipeline:
    #   GM→L1 (fmap + weight + bias)
    #   L1→L0A (im2col via Load3Dv2)
    #   L1→L0B (weight load)
    #   L0A×L0B→L0C (Mmad)
    #   L0C + bias → GM (Fixpipe)
    with tl.scope('cube'):
        conv_shape = tl.make_conv_shape(batch, Ho, Wo, Cout)
        tl.conv2d_dot(
            fmap, layout_fmap,
            weight, layout_weight,
            output, layout_out,
            conv_shape, conv_params
        )


# --- Host 调用 ---
def host_main(fmap: torch.Tensor, weight: torch.Tensor,
              bias: torch.Tensor, output: torch.Tensor):
    batch, Cin, H, W = fmap.shape
    Cout, _, kH, kW = weight.shape
    sH, sW = 1, 1
    pH, pW = 1, 1

    core_num = tl.get_core_num()

    conv2d_bias_kernel[core_num](
        fmap, weight, bias, output,
        batch, Cin, H, W, Cout, kH, kW, sH, sW, pH, pW
    )
