# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

# ============================================================================
# CANONICAL reference for a **full reduction to a scalar** (loss-style) op.
#
# Origin: translated from the old CAKE2-easydsl-v2 `tile.language` kernel
#   skills/dsl-baseline-generation/references/output_example/mse_loss.py
# (two-phase per-core partial reduce + workspace combine).
#
# Semantics (exactly torch.mean((predictions - targets) ** 2)):
#   The KERNEL produces Σ(pred-target)^2 over all elements in out[0,0]; the
#   caller divides by numel to obtain the mean (see __main__ / the wrapper).
#
# Verification status:
#   simulator : PASS — 3 shapes incl. non-aligned 37x1023 (diff <= 2e-5)
#   device    : PASS on 910B2 — 2 shapes incl. 37x1023 (diff <= 2.6e-5)
#
# Tiling pattern:
#   single-core full reduction (a scalar output has nothing to parallelize):
#   sweep the flattened array in TILE_H(=64)-wide strips, square the diff,
#   accumulate elementwise into a [1,64] tile, `cadd` to one scalar.
#
# Key DSL design notes (load-bearing — these were each a debugging session):
#   * The mean's DIVIDE is done on the HOST, not in the kernel. Dividing inside
#     by a `dup(int_TOTAL)` fp32 tile returns `inf` on device (the int->fp32
#     cast of the large element count is unreliable for the [1,8] divisor),
#     while the Σ reduction is bit-exact on device. Host-divide keeps it exact.
#   * Single-WRITER store guarded by `If(GetVecIdx()==0)`. `atomic_add` is not
#     modelled by the simulator (reads the GM output uninitialized -> NaN), and
#     letting ALL cores write the same GM cell segfaults the device (rc=139).
#   * `dup(core_s, 0.0)` BEFORE the cadd: cadd writes only col 0 of the [1,8]
#     scalar tile, but the 32B GM store reads all 8 lanes — uninit -> NaN.
#   * H18: pre-zero p_row/t_row each strip so a partial (sub-32B) DataCopyPad
#     does not leave STALE bytes in the last C0 block on device (sim zero-pads).
#   * `bar_all()` fences: auto_sync() has no V->MTE2 edge, and a `dup` written in
#     one auto_sync region is NOT visible to a consumer in a later region
#     without a bar_all between them (this silently produced 0/NaN).
# ============================================================================
from easyasc.a2 import *
import torch


TILE_H = 64


@kernel()
def mse_loss_custom(
    pred: GMTensor,       # flattened [TOTAL]
    target: GMTensor,     # flattened [TOTAL]
    out: GMTensor,        # [1, 8] — element 0 receives Σ (pred-target)^2
    TOTAL: Var,
):
    """Sum of squared error Σ(pred-target)^2 over ALL elements, in out[0,0].
    The caller divides by numel to get mean((pred-target)^2) — see the wrapper /
    `_ref_and_div` below. The division is deliberately done OUTSIDE the kernel:
    on device, dividing inside the kernel by a `dup(int_TOTAL)` fp32 tile yields
    `inf` (the int->fp32 cast of the large element count is not reliable for a
    [1,8] divisor tile), whereas the Σ reduction itself is bit-exact on device
    (verified: raw sum matched the torch reference to the last digit). Pushing
    the trivial scalar divide to the host keeps the heavy, device-verified work
    in the kernel and the result exact in both simulator and on hardware.

    Reduction shape: a single vec core (guarded by `GetVecIdx()==0` for the
    store) sweeps the flattened array in TILE_H-wide strips, squares the diff,
    and accumulates elementwise into a [1, TILE_H] tile; a final `cadd` folds
    the 64 lanes to one scalar. (A scalar reduction has no per-row output to
    parallelize, and `atomic_add` is unmodelled by the simulator / all-core
    writes to one GM cell segfault the device — hence the single-core design.)
    """
    p_row = Tensor(DT.float, [1, TILE_H], Position.UB)
    t_row = Tensor(DT.float, [1, TILE_H], Position.UB)
    d_row = Tensor(DT.float, [1, TILE_H], Position.UB)
    acc_row = Tensor(DT.float, [1, TILE_H], Position.UB)   # 64 elementwise accumulators
    core_s = Tensor(DT.float, [1, 8], Position.UB)        # 32B-aligned scalar tile

    # Every core runs the full reduction redundantly (cheap, no shared state),
    # but ONLY core 0 stores the result. Why this shape:
    #   * the simulator does not model `atomic_add` (reads the GM output as
    #     uninitialized → NaN), so an atomic cross-core sum cannot be verified;
    #   * having ALL cores write the same GM cell segfaults the device
    #     (concurrent overlapping GM writes are a hardware hazard, rc=139).
    # A single-writer guard (`GetVecIdx()==0`) gives one clean, correct write in
    # both simulator and on device.
    core_idx = Var(GetVecIdx())

    with auto_sync():
        dup(core_s, 0.0)       # init all 8 lanes: cadd touches col 0 only but
                               # the 32B GM store reads all 8 (uninit → NaN).
    bar_all()

    with auto_sync():
        dup(acc_row, 0.0)
    bar_all()   # make the zero-init visible to the first add() below

    n_strips = CeilDiv(TOTAL, TILE_H)
    for si in range(0, n_strips):
        roff = Var(si * TILE_H)
        rcount = Min(TILE_H, TOTAL - roff)   # last strip may be partial (>=1)
        # H18 fix: pre-zero so the partial last-strip DataCopyPad does not leave
        # STALE bytes in the final C0 block on device (sim zero-pads). (0-0)^2=0
        # so the zeroed pad lanes do not perturb the sum of squares.
        with auto_sync():
            dup(p_row, 0.0)
            dup(t_row, 0.0)
        bar_all()
        with auto_sync():
            p_row[0:1, 0:rcount] <<= pred[roff:roff + rcount]
            t_row[0:1, 0:rcount] <<= target[roff:roff + rcount]
            sub(d_row, p_row, t_row)
            mul(d_row, d_row, d_row)
            add(acc_row, acc_row, d_row)   # elementwise accumulate (64 lanes)
        bar_all()

    bar_all()   # make the loop's final acc_row visible to the cadd below
    with auto_sync():
        cadd(core_s[0:1, 0:1], acc_row)   # Σ d^2 over ALL elements (host divides)
    bar_all()

    with If(core_idx == 0):
        with auto_sync():
            out[0:1, 0:8] <<= core_s[0:1, 0:8]   # out[0,0]=Σ(pred-target)^2, [1:8]=0
        bar_all()

    return out


def _ref(pred, target):
    return torch.mean((pred - target) ** 2)


def main():
    torch.manual_seed(0)
    for shape in [(64, 256), (16, 512), (37, 1023)]:
        TOTAL = shape[0] * shape[1]
        pred = torch.rand(*shape, dtype=torch.float32)
        target = torch.rand(*shape, dtype=torch.float32)
        out = torch.zeros(1, 8, dtype=torch.float32)
        ok = OpExec(mse_loss_custom, simulator=True)(
            pred.reshape(-1), target.reshape(-1), out, TOTAL)
        # kernel returns the SUM of squared error; divide by numel for the mean.
        mse_k = ok[0, 0].item() / TOTAL
        mse_r = _ref(pred, target).item()
        diff = float(torch.tensor(mse_k - mse_r).abs())
        print(f"[shape={shape} TOTAL={TOTAL}] mse_k={mse_k:.6f} mse_r={mse_r:.6f} diff={diff:.3e}")
        assert diff < 1e-3, f"FAIL {shape}"

if __name__ == "__main__":
    main()
