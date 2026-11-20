```
ID:        0123-each-reduction-template-carries-its-own-ub-budget-with-named-fixed-reserves
LABEL:     knowledge
LEVEL:     L2 (memory hierarchy & residency)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/tiling/reduction/fallback/tiling-flow.md:207-308 —
           "固定预留 = 1024 + 512   // 通用预留 + 二分累加临时区" ·
           "可用 UB = ub_size - max_buf - sum_buf - binary_cache; max_buf = 32, sum_buf = 32,
           binary_cache = 2048" · "r_max = (ub_size - tmp_buf - 64) / (2 × dtype_bytes)" ·
           "r_bin_size = 128" · "per_tile = R × (输入×2 + FP32中间量×2 + FP32输出) + 固定 8B"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured reduction on a named 950 board where a tile sized exactly at the budget's
           limit overflows UB, or where a tile at twice the limit runs correctly — either shows
           the reserves are wrong, and every template's tile size is wrong with them.
```

# 0123 · Each reduction template carries its own UB budget with named fixed reserves

## 1 · Claim
Upstream asserts a distinct UB budget formula for each of the five templates, each stated against a
standard single-pass reduction (one input copy, one output copy, one Reduce-API temporary region),
with named fixed reserves subtracted before the per-element cost divides the remainder. AR-SmallR:
`per_tile = r_align × (input×2 + output×2 + fp32-intermediate×2)`,
`max_a1_tiles = ub_size / (a0_tile_unit × (per_tile + 4))` with `a0_tile_unit = 64`. AR-FullLoad:
`rows_per_ub = (ub_size − 固定预留) / per_row_bytes` with `固定预留 = 1024 + 512` (general reserve
plus binary-accumulation scratch), and a simplified form `r_max = (ub_size − tmp_buf − 64) /
(2 × dtype_bytes)`. AR-Recompute: `可用 UB = ub_size − max_buf − sum_buf − binary_cache` with
`max_buf = 32`, `sum_buf = 32`, `binary_cache = 2048`, and per-element cost `input×3 + output×2 +
fp32×1`. ARA-FullLoad: `per_tile = R × (input×2 + fp32-intermediate×2 + fp32-output) + 8 B` fixed.
ARA-Recompute: `r_bin_size = 128`, `cache_layers = log2(bin_loop_count)`, and
`per_tile = r_bin_size × (input×2 + fp32) + fp32 × (11 + cache_layers)`. Not established here.

## 2 · The wrong branch this removes
Without the per-template budgets an agent sizes tiles from the obvious quantity — the data — and
gets a tile that does not fit, because every one of these formulas charges more than the data.
Three specific over-charges are invisible unless stated. First, input and output are counted twice
(`输入×2 + 输出×2`), which is double-buffering folded into the budget rather than expressed as a
flag; an agent that budgets one copy each will be over by 2×. Second, intermediates are FP32
regardless of the operand dtype, so an FP16 reduction pays 4 bytes per intermediate element, not 2.
Third, the fixed reserves are small (1536, 2112, 8, 4096-floor) but they are subtracted *before*
the division, so at small tile counts they change the answer, and a budget written without them
produces tiles that fit on paper and overflow at the edge case.

The `cache_layers = log2(bin_loop_count)` term in ARA-Recompute removes a fourth: the budget's
denominator depends on the number of chunks, which depends on the chunk size, which is what the
budget is computing. An agent that does not notice the circularity will solve it in the wrong
order and get a self-consistent but wrong `a0_tile_len`.

## 3 · Ground / Source
`reduction/fallback/tiling-flow.md:207-308`, §4 in full — the five budgets, verbatim.

```
以下公式以 **标准单次归约**（1 份输入 + 1 份输出 + Reduce API 临时区）为基准。
多遍流水算子（Softmax、Norm）需在分母中追加中间 buffer，见第 7 节。

### 4.1 AR-SmallR

条件: R ≤ r_small_threshold

r_small_threshold = r_tile_unit × 2
  r_tile_unit = 8 (FP32) / 16 (FP16)

每 tile 的 UB 开销（转置后）:
  per_tile = r_align × (输入×2 + 输出×2 + 中间FP32×2)

a0_tile_unit = 64  // FP32 向量宽度
max_a1_tiles = ub_size / (a0_tile_unit × (per_tile + 4))
a1_tile_count = min(max_a1_tiles, ceil(A1 / a0_tile_unit))
a1_tile_len = a1_tile_count × a0_tile_unit

多核: 按 a1_outer = ceil(A1 / a1_tile_len) 均分到 core_num

### 4.2 AR-FullLoad

条件: rows_per_ub ≥ 1

r_align = ceil(R, 32B/dtype) × (32B/dtype)

rows_per_ub = (ub_size - 固定预留) / per_row_bytes
  固定预留 = 1024 + 512   // 通用预留 + 二分累加临时区
  per_row_bytes = r_align × (FP32中间量 + 输入×2 + 输出×2)

rows_per_core = ceil(A1 / core_num)
rows_per_ub = min(rows_per_ub, rows_per_core)

标准归约的简化版（无多遍中间量）:

r_max = (ub_size - tmp_buf - 64) / (2 × dtype_bytes)
FullLoad 条件: R ≤ r_max

### 4.3 AR-Recompute

条件: R > AR-FullLoad 阈值

可用 UB = ub_size - max_buf - sum_buf - binary_cache
  max_buf = 32, sum_buf = 32, binary_cache = 2048

每元素开销 = 输入×3 + 输出×2 + FP32×1   // 标准归约; Softmax 等需追加
r_chunk = floor(可用UB / 每元素开销)，按 32B 对齐

r_loop_count = ceil(R / r_chunk)
尾块 r_chunk_tail = R - r_chunk × floor(R / r_chunk)

块间合并: 二分累加
  fold_base = 小于 r_loop_count 的最大 2 的幂
  fold_remain = floor(R/r_chunk) - fold_base

### 4.4 ARA-FullLoad

a0_tile_unit = 64 (FP32) / 128 (FP16)

每 tile UB 开销:
  per_tile = R × (输入×2 + FP32中间量×2 + FP32输出) + 固定 8B

max_a0_inner = ub_size / per_tile / a0_tile_unit
a0_factor_max = ceil(A0 / a0_tile_unit)
total_tiles_max = A1 × a0_factor_max

a0_inner = min(
  ceil(total_tiles_max / core_num),  // 多核均衡
  max_a0_inner,                       // UB 容量
  a0_factor_max                       // A0 维度
)
a0_tile_len = a0_inner × a0_tile_unit

R ≤ 8: 直接逐行累加，无需二分参数
R > 8: 启用 BinaryAdd（将 R 行两两分组做树形归约）

### 4.5 ARA-Recompute

r_bin_size = 128   // R 方向默认分块粒度

bin_loop_count = ceil(R / r_bin_size)
bin_tail = R - (bin_loop_count - 1) × r_bin_size

cache_layers = log2(bin_loop_count)  // 跨 bin 二分累加的 cache 层数

per_tile = r_bin_size × (输入×2 + FP32) + FP32 × (11 + cache_layers)
max_a0_inner = ub_size / a0_tile_unit / per_tile
// 后续 a0_inner / a0_tile_len / 多核分配同 ARA-FullLoad
```

The alignment rules the budgets depend on, `:371-378`:

```
| 场景 | 对齐粒度 | 说明 |
|------|---------|------|
| R 方向 | 32B / dtype_bytes 个元素 | DataCopyPad 要求 |
| A0 切分 | 64(FP32) / 128(FP16) | 向量寄存器宽度 |
| UB Buffer | 32B | 最小搬运单位 |
| tmp_buf_size | ≥ 4096B | Reduce API 下限 |
```

and the effective-versus-aligned-length discipline, `:382-389`, which is a real trap in these
formulas — `R` is used for `DataCopyPad` transfer length and Reduce-API element counts, while
`r_align` is used for UB row offsets and buffer sizing. Swapping them produces a buffer that is too
small or a reduction over padding.

Two symbols in these formulas are named but never given values in the family: `tmp_buf` in the
AR-FullLoad simplified form (it is *computed* by §8's formula, 0129, so this is a forward
reference rather than an absence), and `固定预留`'s split into `1024 + 512` with no statement of
what the general 1024 is reserved for. The literal `11` in ARA-Recompute's fp32 term is
unexplained. Under the provenance rule (0104) all of these are hardcoded literals — software
经验值, searchable — while `ub_size` and the 32 B/64/128 alignment quantities trace to chip
specification and are hardware constraints.

The magnitudes of the reserves are worth reading against `ub_size`: 1536 B and 2112 B against a UB
of order 200 KB are under 1 %, so they matter only when the per-element cost is large enough that
`ub_size / cost` is a small number — which is exactly the Recompute regime these two belong to.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s
spacing; bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and
discard the case if the die moved.

Budget-tightness test, one per template, five in all. For each template pick a shape that routes to
it (per 0122), evaluate its budget formula against the UB capacity read at runtime — never a
literal, and the queried value is printed alongside the result because this family states two
different UB values for the same chip family (0131). Then build three points per template: at the
largest tile the formula admits, at that tile plus one alignment step, and at half the formula's
tile. For each: one compiler pin, md5 the binary, host echo of every derived field
(`a1_tile_len` / `rows_per_ub` / `r_chunk` / `a0_tile_len` / `r_bin_size`, `tmp_buf_size`), output
against an fp64 reference within the declared tolerance, and `aiv_time` under
`msprof --aic-metrics=PipeUtilization`, ≥10 iterations, first 5 dropped, per case.

Second arm — the reserves. For AR-FullLoad and AR-Recompute, re-derive the tile with the fixed
reserve set to zero and build at that (larger) tile. If it runs correctly, the reserve is not
needed at this shape and its size is an open number; if it fails, the reserve is doing work and the
failure mode is recorded. This arm is the negative arm and is reported whether or not it bites.

Third arm — the ARA-Recompute circularity. Solve `per_tile` with `cache_layers` computed from the
`bin_loop_count` implied by the resulting tile, iterate to a fixed point, and record how many
iterations it takes and whether the fixed point is unique for the swept shapes. This needs no
device and is arithmetic, and it is labelled as arithmetic in the report.

Refuses to assume: that a free die stays free; that a die may be substituted; that `ub_size` is any
literal; that a formula that admits a tile is a formula the host used (echo required); that a
correct result at the boundary means the boundary is right — the plus-one-step point is what tests
that; that FP16 behaves like FP32 (each template is run at both, since the fp32-intermediate terms
make the ratio dtype-dependent).

## 5 · Checker — acceptance declared before the run
Verdict variable `budget_tight(template)`: true iff the at-limit point builds and runs correctly,
AND the plus-one-step point fails (build error, launch error, or wrong result). Declared
acceptance: the budgets are correct as written iff `budget_tight` is true for all five templates.
Two distinct failure directions are reported separately and neither is smoothed: a point *inside*
the budget that fails means the formula under-charges (the OVERTURN condition, and every tile from
that template is too big); a point well outside that runs correctly means it over-charges, and the
margin is quantified as `(largest working tile) / (formula tile)`.

The exit code is not the verdict. The blind mode here is a host that clamps the requested tile back
inside its own budget: the plus-one-step point would then run correctly and `budget_tight` would be
scored false for a boundary that was never crossed. The echo of the derived tile field is therefore
compared against the request at every point, a mismatch marks the point `clamped`, and the checker
goes red rather than issuing a verdict when any point is clamped. Second guard: the queried
`ub_size` is recorded in the result and the checker fails if it differs between the prediction and
the run, since the whole comparison is against a capacity.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured; no tile was sized against a real capacity. The entry does not establish any
reserve value (1024, 512, 32, 32, 2048, 8, the literal 11), does not establish that `r_bin_size =
128` is the right granularity, and does not establish `ub_size` on any board — the budgets are
functions of a number this book cannot resolve (0131). It does not establish that the doubled
input/output terms correspond to double buffering; upstream writes `×2` without saying why, and
that reading is this book's inference, marked as such. It does not cover the interleaved templates,
whose budget is a different shape with a 16 KB fixed temp (0128), nor BlockSplitR's workspace
(0124). It does not resolve the ARA-Recompute circularity — §4's third arm is arithmetic, and it
has not been run either. No board is named in `tiling-flow.md`, so BOARD is
`family-claimed(unverified)`; §4 names 950PR/950DT because that is where our run would happen.
Nothing here is established for any 910-family board.
