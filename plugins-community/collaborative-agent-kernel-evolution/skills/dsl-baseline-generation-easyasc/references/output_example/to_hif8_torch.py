# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------
from typing import Tuple

import torch

from easyasc.a2 import *

TILE = 512
HIF8_MAX = 2.0 ** 15 * 1.25
HIF8_MIN_NORMAL = 2.0 ** -23
HIF8_MIN_CLAMP = 2.0 ** -22
FLOAT32_FINITE_MAX = float(torch.finfo(torch.float32).max)
FLOAT32_FINITE_MIN = -FLOAT32_FINITE_MAX
EXP_MASK = 0x7F800000
EXPABS_BIAS = -0x00800000


@kernel()
def to_hif8_torch_kernel(x: GMTensor, y: GMTensor, total: Var):
    xub = Tensor(DT.float, [1, TILE], Position.UB)
    workub = Tensor(DT.float, [1, TILE], Position.UB)
    absub = Tensor(DT.float, [1, TILE], Position.UB)
    expub = Tensor(DT.float, [1, TILE], Position.UB)
    expabsub = Tensor(DT.float, [1, TILE], Position.UB)
    scaleub = Tensor(DT.float, [1, TILE], Position.UB)
    bias1 = Tensor(DT.float, [1, TILE], Position.UB)
    bias2 = Tensor(DT.float, [1, TILE], Position.UB)
    bias3 = Tensor(DT.float, [1, TILE], Position.UB)
    outub = Tensor(DT.float, [1, TILE], Position.UB)
    roundint = Tensor(DT.int, [1, TILE], Position.UB)

    expmask = Tensor(DT.uint32, [1, TILE], Position.UB)
    finiteflag = Tensor(DT.uint8, [1, TILE], Position.UB)
    keepflag = Tensor(DT.uint8, [1, TILE], Position.UB)
    overflowflag = Tensor(DT.uint8, [1, TILE], Position.UB)
    le15flag = Tensor(DT.uint8, [1, TILE], Position.UB)
    le7flag = Tensor(DT.uint8, [1, TILE], Position.UB)
    le3flag = Tensor(DT.uint8, [1, TILE], Position.UB)
    nonnegflag = Tensor(DT.uint8, [1, TILE], Position.UB)

    halfub = Tensor(DT.float, [1, TILE], Position.UB)
    poslarge_buf = Tensor(DT.float, [1, TILE], Position.UB)
    zero_buf = Tensor(DT.float, [1, TILE], Position.UB)
    one_buf = Tensor(DT.float, [1, TILE], Position.UB)
    neghalf_buf = Tensor(DT.float, [1, TILE], Position.UB)
    neglarge_buf = Tensor(DT.float, [1, TILE], Position.UB)

    n_tiles = CeilDiv(total, TILE)
    tile_per_core = CeilDiv(n_tiles, GetVecNum())
    tile_start = Var(tile_per_core * GetVecIdx())
    tile_end = Min(tile_start + tile_per_core, n_tiles)

    dup(expmask, EXP_MASK)
    dup(halfub, 0.5)
    dup(poslarge_buf, FLOAT32_FINITE_MAX)
    dup(zero_buf, 0.0)
    dup(one_buf, 1.0)
    dup(neghalf_buf, -0.5)
    dup(neglarge_buf, FLOAT32_FINITE_MIN)

    with auto_sync():
        for t in range(tile_start, tile_end):
            n1 = Var(t * TILE)
            n_valid = Min(total - n1, TILE)

            xub <<= x[n1:n1 + n_valid]

            absub <<= xub.abs()
            compare_scalar(finiteflag, absub, FLOAT32_FINITE_MAX, CompareMode.LE)
            select(workub, finiteflag, xub, zero_buf, SelectMode.TENSOR_SCALAR)
            absub <<= workub.abs()

            x_u16 = workub.reinterpret(DT.uint16)
            exp_u16 = expub.reinterpret(DT.uint16)
            expmask_u16 = expmask.reinterpret(DT.uint16)
            vand(exp_u16, x_u16, expmask_u16)

            expabs_u16 = expabsub.reinterpret(DT.uint16)
            vnot(expabs_u16, exp_u16)
            vand(expabs_u16, expabs_u16, expmask_u16)
            expabs_i32 = expabsub.reinterpret(DT.int)
            adds(expabs_i32, expabs_i32, EXPABS_BIAS)
            vmax(expabsub, expabsub, expub)

            compare_scalar(keepflag, expub, HIF8_MIN_NORMAL, CompareMode.GE)
            compare_scalar(le15flag, expabsub, 32768.0, CompareMode.LE)
            compare_scalar(le7flag, expabsub, 128.0, CompareMode.LE)
            compare_scalar(le3flag, expabsub, 8.0, CompareMode.LE)

            vmaxs(scaleub, expub, HIF8_MIN_CLAMP)
            select(bias1, le15flag, halfub, one_buf, SelectMode.TENSOR_SCALAR)
            select(bias2, le7flag, halfub, one_buf, SelectMode.TENSOR_SCALAR)
            select(bias3, le3flag, halfub, one_buf, SelectMode.TENSOR_SCALAR)
            scaleub <<= scaleub * bias1
            scaleub <<= scaleub * bias2
            scaleub <<= scaleub * bias3

            outub <<= workub / scaleub
            compare_scalar(nonnegflag, outub, 0.0, CompareMode.GE)
            select(bias1, nonnegflag, halfub, neghalf_buf, SelectMode.TENSOR_SCALAR)
            outub <<= outub + bias1
            cast(roundint, outub, round_mode=RoundMode.TRUNC)
            cast(outub, roundint)
            outub <<= outub * scaleub
            select(outub, keepflag, outub, zero_buf, SelectMode.TENSOR_SCALAR)

            compare_scalar(overflowflag, absub, HIF8_MAX, CompareMode.GE)
            compare_scalar(nonnegflag, workub, 0.0, CompareMode.GE)
            select(bias2, nonnegflag, poslarge_buf, neglarge_buf, SelectMode.TENSOR_SCALAR)
            select(outub, overflowflag, bias2, outub, SelectMode.TENSOR_TENSOR)
            select(outub, finiteflag, outub, xub, SelectMode.TENSOR_TENSOR)

            y[n1:n1 + n_valid] <<= outub

    return y


def round_away_from_zero(x: torch.Tensor) -> torch.Tensor:
    return torch.sign(x) * torch.floor(torch.abs(x) + 0.5)


def _kernel_exp_scales(x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
    x_bits = x.contiguous().view(torch.int32)
    exp_bits = x_bits & 0x7F800000
    exp = exp_bits.view(torch.float32)

    inv_exp_bits = (~exp_bits) & 0x7F800000
    expabs_bits = inv_exp_bits - 0x00800000
    exp_abs = expabs_bits.view(torch.float32)
    exp_abs = torch.maximum(exp_abs, exp)
    return exp, exp_abs


def to_hif8_torch(x: torch.Tensor) -> torch.Tensor:
    x = x.to(dtype=torch.float32)
    out = x.clone()

    finite_mask = torch.isfinite(x)
    if not finite_mask.any():
        return out

    finite_x = x[finite_mask].contiguous()
    exp, exp_abs = _kernel_exp_scales(finite_x)

    le15 = exp_abs <= 32768.0
    le7 = exp_abs <= 128.0
    le3 = exp_abs <= 8.0
    keep_mask = exp >= HIF8_MIN_NORMAL

    scale = torch.maximum(exp, torch.full_like(exp, HIF8_MIN_CLAMP))
    scale = scale * torch.where(le15, torch.full_like(scale, 0.5), torch.ones_like(scale))
    scale = scale * torch.where(le7, torch.full_like(scale, 0.5), torch.ones_like(scale))
    scale = scale * torch.where(le3, torch.full_like(scale, 0.5), torch.ones_like(scale))

    quantized = round_away_from_zero(finite_x / scale) * scale
    quantized = torch.where(keep_mask, quantized, torch.zeros_like(quantized))

    overflow_mask = torch.abs(finite_x) >= HIF8_MAX
    sat_values = torch.sign(finite_x) * torch.full_like(finite_x, FLOAT32_FINITE_MAX)
    quantized = torch.where(overflow_mask, sat_values, quantized)

    out[finite_mask] = quantized
    return out


def build_demo_input(total: int, seed: int, scale: float) -> torch.Tensor:
    gen = torch.Generator(device="cpu")
    gen.manual_seed(seed)
    x = torch.randn(total, generator=gen, dtype=torch.float32) * scale
    finite_edge = torch.tensor(
        [
            0.0,
            -0.0,
            2.0 ** -24,
            2.0 ** -23,
            2.0 ** -22,
            7.5,
            8.5,
            127.5,
            128.5,
            HIF8_MAX - 1.0,
            HIF8_MAX,
        ],
        dtype=torch.float32,
    )
    nonfinite_edge = torch.tensor([FLOAT32_FINITE_MAX, FLOAT32_FINITE_MIN], dtype=torch.float32) * 2.0
    nan_edge = torch.tensor([float("nan")], dtype=torch.float32)
    edge = torch.cat([finite_edge, nonfinite_edge, nan_edge], dim=0)
    return torch.cat([x, edge], dim=0)


def check_case(total: int, seed: int, scale: float) -> None:
    x = build_demo_input(total=total, seed=seed, scale=scale)
    y_ref = to_hif8_torch(x)
    y = torch.zeros_like(x)

    y_out = OpExec(to_hif8_torch_kernel, simulator=True, out_dir="./tmp/to_hif8_torch")(
        x, y, x.numel())

    same = (y_out == y_ref) | (torch.isnan(y_out) & torch.isnan(y_ref))
    if not bool(same.all().item()):
        mismatch_idx = torch.nonzero(~same, as_tuple=False).flatten()
        first = int(mismatch_idx[0].item())
        raise AssertionError(
            "to_hif8_torch_kernel mismatch: idx={} input={} ref={} out={} mismatches={}".format(
                first,
                float(x[first]),
                float(y_ref[first]),
                float(y_out[first]),
                int(mismatch_idx.numel()),
            )
        )

    print(
        "case total={} actual_numel={} scale={} max_diff={}".format(
            total,
            x.numel(),
            scale,
            float(torch.nan_to_num(torch.abs(y_out - y_ref), nan=0.0).max().item()),
        )
    )


def main():
    check_case(total=512 * 8, seed=0, scale=1000.0)
    check_case(total=512 * 8 + 37, seed=1, scale=1000.0)

if __name__ == "__main__":
    main()
