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

ROWS = 40
COLS = 4096
INTER_COLS = 2 * COLS


@kernel()
def sort_rows_kernel(
    x: GMTensor, idx_init_gm: GMTensor, gather_offset_gm: GMTensor,
    sorted_value: GMTensor, sorted_idx: GMTensor,
    rows: Var,
):
    val_ub = Tensor(DT.float, [1, COLS], Position.UB)
    idx_ub = Tensor(DT.int, [1, COLS], Position.UB)
    buf_a = Tensor(DT.float, [1, INTER_COLS], Position.UB)
    buf_b = Tensor(DT.float, [1, INTER_COLS], Position.UB)
    gather_offset_ub = Tensor(DT.int, [1, COLS], Position.UB)
    deinter_val = Tensor(DT.float, [1, COLS], Position.UB)
    deinter_idx = Tensor(DT.float, [1, COLS], Position.UB)

    rows_per_core = CeilDiv(rows, GetVecNum())
    row_start = Var(rows_per_core * GetVecIdx())
    row_end = Min(row_start + rows_per_core, rows)

    idx_ub <<= idx_init_gm[:, :]
    gather_offset_ub <<= gather_offset_gm[:, :]

    for t in range(row_start, row_end):
        with auto_sync():
            val_ub <<= x[t:t + 1, :]
            val_ub <<= val_ub * -1.0

            idx_u32 = reinterpret(idx_ub, DT.uint32)
            gather_off_u32 = reinterpret(gather_offset_ub, DT.uint32)
            sort32(buf_a, val_ub, idx_u32, repeat=COLS // 32)
            mergesort4(buf_b, buf_a, 32, COLS // 128)
            mergesort4(buf_a, buf_b, 128, COLS // 512)
            mergesort4(buf_b, buf_a, 512, COLS // 2048)
            mergesort_2seq(buf_a, buf_b, buf_b[:, INTER_COLS // 2:], COLS // 2, COLS // 2)

            gather(deinter_val, buf_a, gather_off_u32, 0)
            gather(deinter_idx, buf_a, gather_off_u32, 4)

            deinter_val <<= deinter_val * -1.0

            sorted_value[t:t + 1, :] <<= deinter_val
            idx_bits_i32 = reinterpret(deinter_idx, DT.int)
            sorted_idx[t:t + 1, :] <<= idx_bits_i32

    return sorted_value, sorted_idx


def check_case(seed: int) -> None:
    torch.manual_seed(seed)
    x = torch.randn(ROWS, COLS, dtype=torch.float32)

    ref_value, ref_idx = torch.sort(x, dim=-1)

    sorted_value = torch.zeros_like(x)
    sorted_idx = torch.zeros(ROWS, COLS, dtype=torch.int32)
    idx_init = torch.arange(COLS, dtype=torch.int32).view(1, COLS)
    gather_offset = (torch.arange(COLS, dtype=torch.int32) * 8).view(1, COLS)

    sorted_value_out, sorted_idx_out = OpExec(
        sort_rows_kernel, simulator=True, out_dir="./tmp/sort_rows",
    )(x, idx_init, gather_offset, sorted_value, sorted_idx, ROWS)

    value_match = torch.allclose(sorted_value_out, ref_value, rtol=0.0, atol=0.0)
    idx_match = torch.equal(sorted_idx_out.to(torch.int64), ref_idx.to(torch.int64))

    gathered_by_idx = torch.gather(x, 1, sorted_idx_out.to(torch.int64))
    roundtrip_match = torch.allclose(gathered_by_idx, sorted_value_out, rtol=0.0, atol=0.0)

    print(
        "seed={} value_match={} idx_match={} roundtrip_match={}".format(
            seed, value_match, idx_match, roundtrip_match,
        )
    )
    if not (value_match and roundtrip_match):
        diff = (sorted_value_out - ref_value).abs().max().item()
        raise AssertionError(
            "sort_rows_kernel value mismatch: max_abs_diff={}".format(diff)
        )


def main():
    check_case(seed=0)
    check_case(seed=1)

if __name__ == "__main__":
    main()
