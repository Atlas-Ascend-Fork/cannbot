# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------
import builtins

import torch

from easyasc.a5 import *


VEC_WIDTH = 64

SHAPE_BINDINGS = {
    0: [0, 1],  # x[M, H]
    1: [0, 1],  # y[M, H]
}


@vf()
def chunk_row_cumsum_vf(src: Tensor, dst: Tensor, rows: Var, row_stride: Var, cols64: Var):
    prev_reg = Reg(DT.float)
    curr_reg = Reg(DT.float)

    for c in range(cols64):
        col_off = Var(c * VEC_WIDTH)
        prev_reg <<= src[col_off]
        dst[col_off] <<= prev_reg

    for r in range(1, rows):
        row_base = Var(r * row_stride)
        for c in range(cols64):
            curr_off = Var(row_base + c * VEC_WIDTH)
            prev_off = Var(curr_off - row_stride)
            curr_reg <<= src[curr_off]
            prev_reg <<= dst[prev_off]
            curr_reg <<= curr_reg + prev_reg
            dst[curr_off] <<= curr_reg


@kernel()
def chunk_row_cumsum_kernel(x: GMTensor, y: GMTensor, M: Var, H: Var, chunk_size: Var):
    xbuf = Tensor(DT.float, [chunk_size, H], Position.UB)
    ybuf = Tensor(DT.float, [chunk_size, H], Position.UB)
    xbuf_pad64 = Tensor(DT.float, [chunk_size, VEC_WIDTH], Position.UB)
    ybuf_pad64 = Tensor(DT.float, [chunk_size, VEC_WIDTH], Position.UB)

    cols64 = Var(H // VEC_WIDTH)
    total_chunks = CeilDiv(M, chunk_size)
    chunks_per_core = CeilDiv(total_chunks, GetVecNum())
    chunk_begin = Var(chunks_per_core * GetVecIdx())
    chunk_end = Min(chunk_begin + chunks_per_core, total_chunks)

    if H < VEC_WIDTH:
        with auto_sync():
            for chunk_idx in range(chunk_begin, chunk_end):
                row0 = Var(chunk_idx * chunk_size)
                valid_rows = Min(chunk_size, M - row0)
                pad_stride = Var((VEC_WIDTH - H) // DT.float.C0)
                gm_to_ub_pad(
                    xbuf_pad64,
                    x[row0:row0 + valid_rows, 0:H],
                    valid_rows,
                    H,
                    0,
                    pad_stride,
                )
                chunk_row_cumsum_vf(xbuf_pad64, ybuf_pad64, valid_rows, VEC_WIDTH, 1)
                ub_to_gm_pad(
                    y[row0:row0 + valid_rows, 0:H],
                    ybuf_pad64[0:valid_rows, 0:VEC_WIDTH],
                    valid_rows,
                    H,
                    pad_stride,
                    0,
                )
    else:
        with auto_sync():
            for chunk_idx in range(chunk_begin, chunk_end):
                row0 = Var(chunk_idx * chunk_size)
                valid_rows = Min(chunk_size, M - row0)
                xbuf <<= x[row0:row0 + valid_rows, 0:H]
                chunk_row_cumsum_vf(xbuf, ybuf, valid_rows, H, cols64)
                y[row0:row0 + valid_rows, 0:H] <<= ybuf[0:valid_rows, 0:H]

    return y


def _check_contract(m: int, h: int, chunk_size: int) -> None:
    if h <= 0:
        raise ValueError(f"H must be positive, got H={h}")
    if h >= VEC_WIDTH and h % VEC_WIDTH != 0:
        raise ValueError(
            f"H must be divisible by {VEC_WIDTH} when H >= {VEC_WIDTH} for chunk_row_cumsum_kernel, got H={h}"
        )
    if chunk_size <= 0:
        raise ValueError(f"chunk_size must be positive, got chunk_size={chunk_size}")
    elem_size = torch.tensor([], dtype=torch.float32).element_size()
    ub_bytes = chunk_size * (h + VEC_WIDTH) * elem_size * 2
    if ub_bytes > 256 * 1024:
        raise ValueError(
            "chunk_size * (H + 64) is too large for chunk_row_cumsum_kernel: "
            f"need {ub_bytes} bytes across wide and padded src/dst UB buffers"
        )
    if m <= 0:
        raise ValueError(f"M must be positive, got M={m}")


def _torch_chunk_cumsum(x: torch.Tensor, chunk_size: int) -> torch.Tensor:
    out = torch.empty_like(x)
    for row0 in builtins.range(0, x.shape[0], chunk_size):
        row1 = builtins.min(row0 + chunk_size, x.shape[0])
        out[row0:row1] = torch.cumsum(x[row0:row1], dim=0)
    return out


def main():
    torch.manual_seed(0)

    for m, h, chunk_size in [(16, 128, 8), (19, 128, 8), (19, 33, 8)]:
        _check_contract(m, h, chunk_size)

        x = torch.randn((m, h), dtype=torch.float32)
        y = torch.zeros_like(x)
        y_ref = _torch_chunk_cumsum(x, chunk_size)

        y_kernel = OpExec(chunk_row_cumsum_kernel, simulator=True)(
            x, y, m, h, chunk_size, shape_bindings=SHAPE_BINDINGS
        )

        torch.testing.assert_close(y_kernel, y_ref, rtol=1e-5, atol=1e-5)
        print(f"shape=(M={m}, H={h}, chunk_size={chunk_size})")
        print(f"max_abs_diff={torch.abs(y_kernel - y_ref).max().item():.6e}")

if __name__ == "__main__":
    main()
