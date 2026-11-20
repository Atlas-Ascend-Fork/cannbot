# CARD 002 · Cube granularity is a dtype lookup, with only `k0` varying (16 / 8 / 32)

- **Quote** (`ops/ascendc-perf-optimize/references/tiling/convolution/fallback/tiling-fields.md:7-17`):
  ```
  ## 1. Cube 计算粒度 (m0, k0, n0)

  由 dtype 查表确定 Cube 指令的基本计算块：

  | dtype | m0 | k0 | n0 |
  |-------|----|----|-----|
  | FP16 / BF16 | 16 | 16 | 16 |
  | FP32 | 16 | 8 | 16 |
  | INT8 / HF8 / FP8 | 16 | 32 | 16 |

  > 源码：`CUBE_MKN_TAB` in `conv_api_tiling_util.h`
  ```
  Matched by `convolution/fallback/script/conv_tiling.py:51-55` (`M0 = 16`, `N0 = 16`,
  `B16_K0 = 16`, `B8_K0 = 32`) and by the multi-core rule at `tiling-fields.md:28` —
  `所有维度值均为 aicoreNum 的因子，乘积 ≤ aicoreNum`.
- **Guessed book**: 950. No chip named anywhere in the convolution family.
- **Guessed level**: L5 (compute & numerics).
- **Evidence class**: bare. A hardware granularity table with a named source header that is not in
  this tree.
- **Why a card and not an entry**: this is an architectural constant table, not a tiling decision —
  `m0` and `n0` are invariant at 16 and only `k0` tracks element width (`16 × k0 × 16` is a constant
  512 bytes of K per Cube step at every listed dtype, re-derived here). It belongs with the
  arch-constants block (950: 0201–0299), not with tiling, and is carded rather than entered so the
  domain boundary is not crossed. The matmul family's `CUBE_BLOCK = 16` (`matmul/fallback/tiling-flow.md:31`)
  is the same quantity stated without the dtype dimension.
- **OVERTURN sketch**: a runtime query or a Cube instruction trace on a named 950 board reporting a
  granularity other than `(16, k0, 16)` for a listed dtype.
- **Cross-refs**: entries 0166, 0167, 0168; `harvest/standing/950-tiling.md` S1, S4, S6.
