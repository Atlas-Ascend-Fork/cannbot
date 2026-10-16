# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

# ============================================================================================
# CANONICAL reference for the **NN-Normalization** pattern in cake.
#
# This file replaces the older `layer_norm.py` example (deleted — used 1-D
# `Tensor(DT.float, [N], Position.UB)` which the current easyasc rejects with
# `shape length must be 2`).
#
# When to study this file
#   - Any norm-along-last-dim op (RMSNorm, LayerNorm, GroupNorm, AddRMSNorm,
#     QK-norm, AddLayerNorm, …) — the structure transfers directly.
#   - Any op that needs a per-row reduce-then-broadcast-then-scale flow.
#
# Patterns demonstrated (each maps to a file under `references/constraints/`)
#   1. `cadd` is a **group reduction** (64 fp32 lanes per repeat → 1 scalar).
#      We use TILE_H=64 so one repeat per row covers the chunk exactly.
#      See `references/constraints/vec-reduction-a2.md`.
#   2. Row-scalar → wide-tensor broadcast via `brcb([M,1]→[M,8])` then
#      `mul(wide_dst, wide_src, narrow [M,8])`.
#      See `references/constraints/vec-reduction-a2.md` §3.
#   3. `auto_sync()` does NOT order control-lane Var reads against vec-lane
#      writes — we stay entirely in the vec lane (dup+rec for runtime 1/H,
#      no `Var(0.0) <<= ub_tensor` extraction).
#      See `references/constraints/autosync.md`.
#   4. Tail handling: source slice carries `valid_h`, dst tile is full TILE_H,
#      MTE2's `gm_to_ub_pad` auto-zeros the padding cols.
#      See `references/constraints/tail-safety.md`.
#   5. `1.0 / H` where H is an int Var: `var_div(1.0, int_var)` rejects mixed
#      dtypes. Official A2 workaround — materialise the reciprocal on the vec
#      unit: `dup(fp_tile, H)` then `rec(inv_tile, fp_tile)`. Then
#      `mul(sum_s, sum_s, inv_h_t)` does the runtime divide. See also the
#      "Runtime 1/N from int Var" entry in `references/easyasc_dsl_primer.md`.
#
# Verified end-to-end on 910B2 — see `output/AddRMSNorm/REVIEW.md` for the eval
# result (12/12 cases passed, geomean speedup 0.88x baseline).
# ============================================================================================
#
# easyasc DSL for the fused residual-add + RMSNorm operator (LLaMA / Mistral / Qwen2 style).
#
#     y = weight * (x + residual) * rsqrt(mean((x + residual) ** 2, dim=-1, keepdim=True) + eps)
#
# Layout
#   - inputs   : x, residual  shape [M, H]   (M = B*S, flattened by the caller)
#                weight       shape [H]
#   - output   : y            shape [M, H]
#   - vars     : M (rows), H (cols / hidden_size)
#
# Tiling strategy (norm-along-last-dim, vectorized via [64, 64] tiles)
#   The fundamental constraint on this version of easyasc is that the per-row
#   reduction primitive `cadd` is a *group* reduction (64 lanes per repeat → 1
#   scalar per repeat), and broadcast / per-row scalar→row multiplication is
#   only well-supported via the `brcb([M,1] → [M,8])` + `mul(wide, wide, narrow)`
#   pattern documented in `agent/references/constraints/vec-reduction-a2.md`.
#   That pattern requires processing TILE_M = 64 rows per tile (because brcb
#   with `dst_blk_stride=1, dst_rep_stride=8` produces a `[64, 8]` dest from a
#   `[64, 1]` source).
#
#   So we tile both M and H:
#     - TILE_M = 64 rows per tile (matches the brcb scalar-broadcast convention).
#     - TILE_H = 64 cols per inner H tile (matches one cadd repeat).
#     - For H = 4096 there are H/TILE_H = 64 inner H tiles per row-tile.
#     - For M = 2048 there are CeilDiv(M, TILE_M) = 32 row-tiles, distributed across cores.
#
#   Per-row reduction (mean of squares) is two-pass:
#     pass 1: outer H-chunk loop accumulates sum of squares into `sum_s[64, 1]`.
#     pass 2: inv_rms[64, 1] = rsqrt(sum_s / H + eps), then `brcb` to `[64, 8]` and
#             a second outer H-chunk loop reloads (x + residual), multiplies by
#             inv_rms broadcast, multiplies by weight, and stores y.
#   This is the standard a2 LayerNorm/RMSNorm shape.
#
# Precision
#   - All on-chip buffers and the simulator self-check use float32 (DT.float).
#   - The bf16 ↔ fp32 cast happens at the C++ pybind layer (handled later by the dsl-bridge stage).
#   - Reductions and rsqrt stay in fp32 end-to-end — bf16 reductions over H = 4096 are a known
#     accuracy footgun, and the layer_norm.py reference example also stays in fp32.
#
# UB budget per core
#   x_tile, res_tile, row_tile, sq_tile, weight_tile, w_chunk_buf : 6 × [64, 64] × 4 B = 6 × 16 KB = 96 KB
#   sum_s, inv_rms_s                                              : 2 × [64,  1] × 4 B  ≈ 0.5 KB
#   inv_rms_brcb                                                  : 1 × [64,  8] × 4 B  =  2 KB
#   weight_full                                                   :   [1, H] × 4 B     = 16 KB (loaded once)
#   ⇒ total well below the 192 KB UB budget.
#
# Comparison vs the closest example (layer_norm.py in skill references)
#   - LayerNorm subtracts the row mean before squaring; RMSNorm just squares the row.
#     So we drop the centered/mean buffer and the first-pass row-mean cadd.
#   - We add the residual into the row before the reduction (`add(row_tile, x_tile, res_tile)`).
#   - There is no bias; only `weight` (gamma).
#   - eps is a compile-time Python float constant inlined into the kernel body.
#   - The reference layer_norm.py was written for an older easyasc (1-D Tensor shapes,
#     full-reduce cadd that produced a [1] output). The current upstream simulator
#     requires 2-D Tensor shapes and `cadd` is a group reduction, so we use the
#     [TILE_M, TILE_H] tiled pattern from `flash_attn_score.py` / `flash_attn_full.py`.
# ----------------------------------------------------------------------------------------------------------
from easyasc.a2 import *
from easyasc.utils.datatype import Datatype
import torch


# RMSNorm epsilon — compile-time constant inlined into the DSL body.
# Matches output/AddRMSNorm/AddRMSNorm_functional.py default.
EPS = 1e-6

# Tile shape — see docstring above. Both dims are 64 because that's the natural
# size for one cadd repeat (= 64 fp32 lanes = 256 bytes) AND for the brcb
# scalar-broadcast pattern (`[M, 1]` → `[M, 8]` with `dst_rep_stride=8`).
# TILE sizing for reduction-style norm ops — different rules than elementwise:
#   TILE_M is bounded by the brcb pattern (one cadd repeat produces 64 scalars,
#       and `brcb([M,1]→[M,8])` requires exactly TILE_M=64 because
#       dst_rep_stride=8 fans 8 datablocks per source). Don't change without
#       rewriting the broadcast section.
#   TILE_H is bounded by cadd's per-repeat group size (= 64 fp32 lanes /
#       32 bytes of datablock). Going larger means multi-stage reduction
#       (see rms_norm_bf16.py for the cadd → 128 → 64 → 1 staging recipe
#       that goes up to TILE_H=8192).
# For H ≤ 64: TILE_H=64 is exactly right (1 cadd repeat covers the row).
# For larger H or higher UB utilization, switch to the
# multi-stage-reduce pattern in rms_norm_bf16.py (which uses TILE_H=8192 and
# reaches 60-80% UB utilization vs this file's ~60% at TILE_H=64).
TILE_M = 64
TILE_H = 64


@kernel()
def AddRMSNorm_custom(
    # Inputs first
    x: GMTensor,
    residual: GMTensor,
    weight: GMTensor,
    # Output
    y: GMTensor,
    # Var scalars (shape dims)
    M: Var,
    H: Var,
):
    # ------------------------------------------------------------------
    # On-chip (UB) buffers.
    # ------------------------------------------------------------------
    # Row-tile slabs ([64, 64] each = 16 KB).
    x_tile = Tensor(DT.float, [TILE_M, TILE_H], Position.UB)
    res_tile = Tensor(DT.float, [TILE_M, TILE_H], Position.UB)
    row_tile = Tensor(DT.float, [TILE_M, TILE_H], Position.UB)
    sq_tile = Tensor(DT.float, [TILE_M, TILE_H], Position.UB)
    out_tile = Tensor(DT.float, [TILE_M, TILE_H], Position.UB)
    w_chunk = Tensor(DT.float, [TILE_M, TILE_H], Position.UB)  # weight broadcast (one row repeated TILE_M times)

    # Per-row scalar reduction state ([64, 1]):
    sum_s = Tensor(DT.float, [TILE_M, 1], Position.UB)         # running Σ row^2 per row
    chunk_s = Tensor(DT.float, [TILE_M, 1], Position.UB)         # per-H-chunk Σ row^2 per row
    inv_rms_s = Tensor(DT.float, [TILE_M, 1], Position.UB)         # 1 / sqrt(mean + eps) per row

    # Broadcast buffer for inv_rms ([64, 8]); a4-style brcb output, used as the
    # narrow operand of `mul(wide_dst, wide_src, narrow)`.
    inv_rms_brcb = Tensor(DT.float, [TILE_M, 8], Position.UB)

    # Full row of `weight` ([1, H]); shared across all rows. We rebroadcast a chunk
    # of it into `w_chunk` on every H-iteration via ub_to_ub.
    weight_full = Tensor(DT.float, [1, H], Position.UB)

    # ------------------------------------------------------------------
    # Load `weight` (gamma) once — it's shared across all rows.
    # ------------------------------------------------------------------
    with auto_sync():
        weight_full <<= weight[0:H]

    # ------------------------------------------------------------------
    # Core partitioning: distribute (M / TILE_M) row-tiles across vec cores.
    # ------------------------------------------------------------------
    n_row_tiles = CeilDiv(M, TILE_M)
    tiles_per_core = CeilDiv(n_row_tiles, GetVecNum())
    t_begin = Var(tiles_per_core * GetVecIdx())
    t_end = Min(t_begin + tiles_per_core, n_row_tiles)

    # Number of H-tiles per row, computed at RUNTIME (not codegen) so the kernel
    # binary handles any H — not just the one used in build_codegen_inputs().
    # Reading `H.value` here would fold the codegen-time int into the kernel and
    # bake the H dimension; we MUST use Var arithmetic instead.
    # See skills/dsl-baseline-generation-easyasc/SKILL.md → "Common Pitfalls".
    n_h_tiles = CeilDiv(H, TILE_H)             # Var → runtime ⌈H / TILE_H⌉

    # Compute inv_H = 1 / H at runtime using a tiny UB scratch tensor.
    # Why this dance: easyasc's `var_div(1.0, H)` rejects mixed int/float dtype
    # (H is an int Var because it's a shape dim). Wrapping H in a float Var via
    # `Var(value=H, dtype=float)` doesn't emit a runtime cast — it's a pure
    # Python alias the simulator/codegen can't follow. So we materialise the
    # divide on the vector unit: dup H into a fp32 [TILE_M, 1] tile, then `rec`
    # gives us the reciprocal, which downstream `mul(sum_s, sum_s, inv_h_t)`
    # broadcasts row-wise.
    h_runtime_t = Tensor(DT.float, [TILE_M, 1], Position.UB)   # fp32 [TILE_M, 1]
    inv_h_t = Tensor(DT.float, [TILE_M, 1], Position.UB)   # fp32 [TILE_M, 1] = 1/H

    with auto_sync():
        dup(h_runtime_t, H)        # fill h_runtime_t with the int Var H, fp32-cast at write
        rec(inv_h_t, h_runtime_t)  # inv_h_t = 1 / h_runtime_t  (element-wise)

    # ------------------------------------------------------------------
    # Outer loop: per row-tile.  Each row-tile owns TILE_M = 64 rows × H cols.
    # ------------------------------------------------------------------
    for ti in range(t_begin, t_end):
        row0 = Var(ti * TILE_M)
        # Tail row-tile boundary: M not multiple of TILE_M means last tile
        # has fewer rows. GM source/dest slices MUST use valid_rows to avoid
        # OOB read/write (which triggers aicore 507015 and cascades the eval).
        # See dsl-baseline-generation-easyasc/SKILL.md "Tile Boundary 越界".
        valid_rows = Min(TILE_M, M - row0)

        # ---- Pass 1: accumulate Σ (x + residual)^2 across all H-tiles ----
        # Initialize the per-row running sum to 0.
        with auto_sync():
            dup(sum_s, 0.0)

        for hi in range(0, n_h_tiles):
            h0 = Var(hi * TILE_H)
            # H-tail handling: last tile may have fewer than TILE_H valid columns
            # (e.g. H=1023 with TILE_H=64 → last tile h0=960..1023 is 63 wide).
            # `<<=` lowers to `gm_to_ub_pad` which handles partial loads by
            # auto-zero-padding the destination buffer up to TILE_H. So we just
            # slice the SOURCE to `valid_h` and let MTE2 fill x_tile[:, valid_h:TILE_H]
            # with zeros. Reference pattern: vec_unaligned_gm_to_ub_pad.py.
            valid_h = Min(TILE_H, H - h0)
            with auto_sync():
                # Source slice carries `valid_h` columns; dst x_tile is full TILE_H.
                # MTE2 pads the columns valid_h..TILE_H to zero — exactly what we
                # need so cadd over [TILE_M, TILE_H] gives the exact Σ row^2.
                x_tile <<= x[row0:row0 + valid_rows, h0:h0 + valid_h]
                res_tile <<= residual[row0:row0 + valid_rows, h0:h0 + valid_h]

                # row = x + residual  (residual add)
                add(row_tile, x_tile, res_tile)

                # sq = row * row, then per-row group-reduce → chunk_s[64, 1]
                # cadd over [64, 64] produces 64 dst scalars (1 per row), since
                # 64 cols = exactly 1 cadd repeat per row.
                mul(sq_tile, row_tile, row_tile)
                cadd(chunk_s, sq_tile)

                # sum_s += chunk_s   (running sum of squares per row, in [M, 1] format)
                add(sum_s, sum_s, chunk_s)

        # ---- Pass 2: compute inv_rms = 1 / sqrt(mean + eps), apply, store ----
        with auto_sync():
            # mean = sum * (1/H) ; sum_s holds Σ (x+r)^2 per row, multiply by inv_h_t → mean
            # `inv_h_t` is a [TILE_M, 1] fp32 tile filled with 1/H at kernel start
            # (see h_runtime_t/inv_h_t setup near top). Tensor-tensor mul avoids the
            # int/float Var dtype mismatch that blocks the simpler `muls(..., var_div(1.0, H))`.
            mul(sum_s, sum_s, inv_h_t)       # sum_s now holds mean per row
            adds(sum_s, sum_s, EPS)          # add eps for numerical stability
            rsqrt(inv_rms_s, sum_s)          # inv_rms = 1 / sqrt(mean + eps)
            # Broadcast each row's inv_rms scalar to a C0 (8-element) block:
            # [64, 1] → [64, 8].  The narrow [64, 8] operand then broadcasts cleanly
            # against the wide [64, TILE_H] tiles in `mul(out_tile, row_tile, inv_rms_brcb)`.
            brcb(inv_rms_brcb, inv_rms_s, dst_blk_stride=1, dst_rep_stride=8)

        # Second pass over the H-tiles: re-load (x + residual), normalize, scale, store.
        # We re-add x + residual rather than caching it to avoid TILE_M * H UB cost.
        for hi in range(0, n_h_tiles):
            h0 = Var(hi * TILE_H)
            valid_h = Min(TILE_H, H - h0)
            with auto_sync():
                # Re-load and recompute (x + residual). Same Var-source-slice
                # trick as Pass 1: MTE2's gm_to_ub_pad auto-zeros padding.
                x_tile <<= x[row0:row0 + valid_rows, h0:h0 + valid_h]
                res_tile <<= residual[row0:row0 + valid_rows, h0:h0 + valid_h]
                add(row_tile, x_tile, res_tile)

                # Load this H-chunk of weight into the first row of w_chunk.
                # Going GM → UB (not UB → UB from weight_full) here so MTE2's
                # gm_to_ub_pad can auto-zero-pad the tail iteration. UB→UB copy
                # (`ub_to_ub`) does strict size checking and rejects mismatched
                # span (would error: "need=256 bytes, have=252 bytes" for H=1023
                # last tile valid_h=63). Costs an extra small GM read per H-tile
                # iteration; weight_full is now only used as a UB-residency hint
                # for the codegen — we could drop it entirely, but it's small.
                w_chunk[0:1, 0:TILE_H] <<= weight[h0:h0 + valid_h]

                # normalize: out = row * inv_rms_brcb  (wide × narrow [TILE_M, 8] broadcast)
                mul(out_tile, row_tile, inv_rms_brcb)

                # scale by weight: out *= weight (per-column, broadcast across TILE_M rows)
                mul(out_tile, out_tile, w_chunk[0:1, 0:TILE_H])

                # Store back to GM — only the valid_h columns. out_tile has
                # garbage in columns valid_h..TILE_H (the broadcast mul saw
                # zero weights there, so out_tile[:, valid_h:TILE_H] = 0,
                # but writing them past y[..., H] would be OOB).
                y[row0:row0 + valid_rows, h0:h0 + valid_h] <<= out_tile[0:valid_rows, 0:valid_h]

    # Returning the output GMTensor binds it as the kernel's "output" so OpExec(...)
    # returns the populated tensor to the caller (and codegen knows it's the output).
    return y


def build_codegen_inputs():
    """Single source of truth for shapes used by both simulator and codegen.

    Order MUST match the kernel signature: (x, residual, weight, y, M, H).

    Representative shape (LLaMA-3-8B hidden block, test case 1):
        B=1, S=2048, H=4096  →  flatten to M=B*S=2048.

    All tensors are float32 — the bf16 ↔ fp32 cast happens at the bridge layer.
    `weight` is initialized to all-ones to match Model.__init__ in the functional.
    """
    torch.manual_seed(0)
    M, H = 2048, 4096

    x = torch.randn(M, H, dtype=torch.float32)
    residual = torch.randn(M, H, dtype=torch.float32)
    weight = torch.ones(H, dtype=torch.float32)        # matches nn.Parameter(torch.ones(H))
    y = torch.zeros(M, H, dtype=torch.float32)

    return (x, residual, weight, y, M, H)


def main():
    # Multi-(M, H) self-check to prove the kernel really is Var-parametric.
    # After the H.value → CeilDiv(H, TILE_H) + var_div(1.0, H) refactor, this
    # loop must pass for ALL listed combinations — otherwise the kernel still
    # has shape baked in somewhere. TILE_M=64, TILE_H=64 hard-coded in DSL, so
    # listed M and H are picked to be multiples of 64 to avoid mask issues.
    #
    # If your op needs to support non-aligned H (like 1023), add a Min-clamped
    # tail loop and a third entry here (e.g. (77, 1023)).
    torch.manual_seed(0)
    test_shapes = [
        (2048, 4096),    # llama3_8b / llama2_7b / mixtral_8x7b / single-row variants
        (1024, 8192),    # llama3_70b — larger H, proves H is not baked
        (128, 768), # bf16_test — small odd-multiple H, proves H is not baked
        (64, 256), # small_batch (M floored to 64=TILE_M, smallest legal M)
        (64, 1023), # non_aligned — H NOT multiple of TILE_H, proves H-tail mask works
        # NOTE: Cases with M < TILE_M=64 (small_batch original M=32, single_token M=1)
        # would need M-tail masking — out of scope for the H-bug fix.
    ]
    for M_t, H_t in test_shapes:
        x = torch.randn(M_t, H_t, dtype=torch.float32)
        residual = torch.randn(M_t, H_t, dtype=torch.float32)
        weight = torch.ones(H_t, dtype=torch.float32)
        y = torch.zeros(M_t, H_t, dtype=torch.float32)

        y_kernel = OpExec(AddRMSNorm_custom, simulator=True)(
            x, residual, weight, y, M_t, H_t
        )

        # Reference: pure-fp32 PyTorch implementation of AddRMSNorm.
        x_res = x + residual
        variance = x_res.pow(2).mean(dim=-1, keepdim=True)
        inv_rms = torch.rsqrt(variance + EPS)
        y_ref = (x_res * inv_rms) * weight

        torch.testing.assert_close(y_kernel, y_ref, rtol=1e-4, atol=1e-4)
        diff = torch.abs(y_kernel - y_ref).max().item()
        print(f"H={H_t:>5}  M={M_t:>5}  max_abs_diff={diff:.6e}")

if __name__ == "__main__":
    main()
