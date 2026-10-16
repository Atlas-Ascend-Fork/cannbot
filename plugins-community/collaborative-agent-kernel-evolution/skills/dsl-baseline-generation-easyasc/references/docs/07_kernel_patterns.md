# Kernel Patterns

The `agent/example/kernels/` directory is not just a sample folder. It is the repository's pattern library for legal DSL usage and stable implementation shapes.

## 1. How to use the kernel catalog

Use existing kernels to answer questions like:

- what is the shortest legal matmul baseline
- how should a cube -> vec handoff look
- how should tail writeback be handled
- how are fp8 casts currently modeled
- what does a multi-stage pipeline look like in this DSL

Do not copy a kernel body mechanically into a new kernel. Start from the target formula and borrow only the patterns that are justified by that formula.

## 2. Shortest correctness baselines

Study these first:

- `agent/example/kernels/a5/matmul_float_mmad.py`
  - shortest pure cube matmul path
- `agent/example/kernels/a5/matmul_e5m2_shortcut.py`
  - float8 input matmul with float output
- `agent/example/kernels/a5/matmul_kmkn_fp32_out.py`
  - native `KM @ KN -> MN` layout

## 3. Cube -> vec postprocess patterns

These are useful when the matmul result needs vector work before final writeback.

- `agent/example/kernels/a5/basic_cube_vec_mix.py`
  - `abs(matmul) + 1`
- `agent/example/kernels/a5/matmul_rowwise_norm.py`
  - rowwise reduction plus broadcast divide
- `agent/example/kernels/a5/matmul_rowwise_norm_large_nk.py`
  - two-pass normalization for larger shapes

Use these when the output transform is naturally vec-side and does not need to be fused back into cube immediately.

## 4. Vec -> cube preprocess patterns

These fit formulas where an operand must be transformed before matmul:

- `agent/example/kernels/a5/vec_cube_abs_sqrt_matmul.py`
- `agent/example/kernels/a5/vec_cube_abs_sqrt_matmul_nz.py`
- `agent/example/kernels/a5/recompute_wu_cube_vec.py`

Common ideas:

- compute in UB
- cast or repack if needed
- publish to L1 with `ub_to_l1_nd2nz` or `ub_to_l1_nz`
- consume from cube-side matmul

## 5. Multi-stage mixed pipeline patterns

These show how to combine more than one handoff:

- `agent/example/kernels/a5/vec_cube_vec_scale2_abs_add1_matmul.py`
  - vec preprocess -> cube -> vec postprocess
- `agent/example/kernels/a5/cube_vec_atomic_add_two_outputs.py`
  - mixed pipeline with dual outputs and atomics

These are the right files to study when a new formula cannot be expressed as one pure stage.

## 6. Streaming and lookahead pattern

The most advanced retained example is:

- `agent/example/kernels/a5/test_mla_entire.py`
- `agent/example/kernels/a5/mha_ifa_fp8_scale_256.py`

What it demonstrates:

- one-tile lookahead scheduling
- delayed consumer lifetime
- streamed `row_max` and `row_sum`
- vec and cube cooperation without round-tripping intermediate state to GM
- tail-safe fp8 decode attention with external `scale_q`, `scale_k`, and `scale_v`

Read this file only after you are comfortable with the smaller mixed kernels.

## 7. Pure vec and micro patterns

Useful files:

- `agent/example/kernels/a5/vec_unaligned_gm_to_ub_pad.py`
- `agent/example/kernels/a5/micro_cast_fp8_pack4_dual.py`

These kernels answer questions such as:

- how to write a pure vec kernel
- how to work with scalar extraction via `single()`
- how to handle unaligned widths
- how fp8 pack4 writeback works in micro code

## 8. Pattern selection guide

If your target kernel is:

- shortest pure matmul: start from `matmul_float_mmad.py`
- cube matmul plus vec epilogue: start from `basic_cube_vec_mix.py`
- vec preprocessing before matmul: start from `vec_cube_abs_sqrt_matmul.py`
- two mixed stages: start from `vec_cube_vec_scale2_abs_add1_matmul.py`
- advanced streamed attention-like path: study `test_mla_entire.py`
- fp8 decode-style streamed attention with tail handling: study `mha_ifa_fp8_scale_256.py`

## 9. a2-specific patterns

The kernels above are a5-flavored mixed pipelines. The a2 (b3) device family adds a mandatory GM workspace between cube and vec, so its patterns form a distinct family with different sync, buffering, and tail rules. Read these when the target device is a2.

- `agent/example/kernels/a2/qk_matmul_batched.py`
  - simplest a2 cube-only baseline with batched `BH` flattening
- `agent/example/kernels/a2/to_hif8_torch.py`
  - pure-vec hif8 emulation baseline
- `agent/example/kernels/a2/sort_rows.py`
  - pure-vec row-wise sort built from `sort32` + `mergesort4` + `mergesort_2seq` + `gather` de-interleave
- `agent/example/kernels/a2/flash_attn_score.py`
  - a2 `cube -> vec` with the explicit GM bridge
- `agent/example/kernels/a2/flash_attn_score_iter.py`
  - the same pipeline extended to running state across tiles
- `agent/example/kernels/a2/flash_attn_full.py`
  - a2 `cube -> vec -> cube -> vec` normalized online softmax reference
- `agent/example/kernels/a2/flash_attn_full_pj_hif8.py`, `flash_attn_full_pj_hif8_commonub.py`
  - scaled-hif8 probability path variants; the `_commonub` version moves vec scratch onto shared `DBuff` lineage for better `MTE2 -> V` `ubin` queueing
- `agent/example/kernels/a2/flash_attn_full_pj_hif8_causal.py`, `flash_attn_full_pj_half_block32_causal.py`
  - causal variants, including blockwise `32x32` diagonal-tile masking
- `agent/example/kernels/a2/attn_backward_dense_stage1_tail_dbuf.py`, `attn_backward_dense_stage12_tail.py`
  - staged attention-backward references with tail-safe buffering
- `agent/example/kernels/a2/attn_backward_dense_total_tail.py`, `_causal.py`, `_causal_hif8.py`
  - fully fused tail-safe dense backward kernels, plus the causal and hif8 variants

For the exact a2 pipeline topologies and device-side constraints (GM-bridge rules, a2 vec reduction, mask semantics, online-softmax tail handling), see the focused references under `agent/references/patterns/a2-*.md` and `agent/references/constraints/a2-*.md`.

## 10. Supporting notes

Two repository files are specifically meant to complement the kernel catalog:

- `agent/references/examples/kernel-catalog.md`
- `agent/references/examples/kernel-practice.md`

Use them alongside the source files when deriving new kernels.
