```
ID:        0153-elewise-refuses-a-core-below-4kb-aligns-blocks-to-512-elements-and-promotes-fp16-add-to-fp32
LABEL:     knowledge
LEVEL:     L1 (core & pipe assignment)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/tiling/elewise/fallback/tiling-flow.md:27-38,17-20 and
           elewise/fallback/tiling-fields.md:26-41 — "coreNum = min((dim0 * minDtypeBits +
           MIN_TILING_BITS - 1) / MIN_TILING_BITS, availableCoreNum)" · "blockFormer =
           AlignUp(CeilDiv(dim0, coreNum), 512)" · "| `MIN_TILING_BITS` | 32768 (4KB) | 每核最小数据量 |"
           · "运算为Add/Sub + dtype∈{FP16,BF16} + 输入量级未知? → 升精度分支"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured elementwise sweep on a named 950 board where opening cores below the 4 KB
           per-core floor still reduces wall time — the floor would then be costing parallelism
           rather than avoiding waste.
```

# 0153 · Elewise refuses a core below 4 KB, aligns blocks to 512 elements, and promotes fp16 Add to fp32

## 1 · Claim
Upstream asserts three rules for elementwise tiling. First, a minimum work quantum per core:
`coreNum = min((dim0 × minDtypeBits + MIN_TILING_BITS − 1) / MIN_TILING_BITS, availableCoreNum)`
with `MIN_TILING_BITS = 32768` bits = 4 KB, stated as `每核≥4KB，否则不值得开核` — a core is not
opened for less than 4 KB of data. Second, an element alignment on the multi-core split:
`blockFormer = AlignUp(CeilDiv(dim0, coreNum), 512)` with `ELEM_ALIGN_FACTOR = 512`, and a separate
256-byte alignment on the UB tile stated as ensuring vector instruction efficiency. Third, a
precision branch: when the operation is Add or Sub, the dtype is FP16 or BF16, and the input
magnitude is unknown, the computation is promoted — cast to FP32, computed, cast back — at the cost
of `K` extra FP32 intermediate buffers of `ubFormer × 4` bytes each, where `K` is set by API aliasing
constraints. Upstream also asserts a cross-core offset rule,
`blockFormer × blockIdx × sizeof(dtype)`. Not established here.

## 2 · The wrong branch this removes
The 4 KB floor inverts the instinct. An agent told to use the machine will split `dim0` by the
available core count, and for small tensors that gives every core a few hundred bytes — at which
point the per-core launch and synchronisation cost exceeds the work. Upstream's formula makes
`coreNum` a function of the data volume first and the machine second, so a small tensor deliberately
leaves cores idle. An agent that "fixes" the idle cores makes the operator slower, and the profile
will show high occupancy, which reads as success.

Note the formula's unit: `dim0 × minDtypeBits` is bits, and `MIN_TILING_BITS` is bits, so the floor
is 4 KB of *data*, not 4 K elements — at int8 that is 4096 elements per core, at fp32 1024. An agent
that reads 32768 as an element count is wrong by `minDtypeBits`.

The 512-element alignment removes a second wrong branch: computing `blockFormer` by exact division
gives per-core extents that start at arbitrary byte offsets, so every core's first and last transfer
is unaligned. `AlignUp` to 512 elements trades a slightly uneven tail for aligned starts everywhere.
The trade is only visible if you know the alignment is deliberate — `CeilDiv` alone looks more
correct.

The promotion branch removes the most expensive one. FP16 Add with unknown input magnitude loses
precision catastrophically when the operands are far apart in scale, and the failure is a numeric
one that no tiling check sees. Upstream's condition is narrow and worth keeping narrow: Add/Sub
only, FP16/BF16 only, and only when the magnitude is unknown — an agent that promotes everything
pays `K × ubFormer × 4` bytes of UB on every case, which shrinks `ubFormer` and multiplies the loop
count.

## 3 · Ground / Source
The multi-core split, `elewise/fallback/tiling-flow.md:25-38`:

```
## 2. 多核切分

coreNum = min(
  (dim0 * minDtypeBits + MIN_TILING_BITS - 1) / MIN_TILING_BITS,
  availableCoreNum
)

blockFormer = AlignUp(CeilDiv(dim0, coreNum), 512)
blockNum = CeilDiv(dim0, blockFormer)
blockTail = dim0 - (blockNum - 1) * blockFormer

确保每核至少4KB数据，元素数对齐到512。
```

The constants and rules, `elewise/fallback/tiling-fields.md:26-41`:

```
## 2. 约束常量

| 常量 | 值 | 说明 |
|------|----|------|
| `MIN_TILING_BITS` | 32768 (4KB) | 每核最小数据量 |
| `ELEM_ALIGN_FACTOR` | 512 | 多核切分元素对齐因子 |
| `ALIGN_256` | 256 | UB对齐字节数 |

## 3. 经验规则

| 规则 | 说明 |
|------|------|
| 最小粒度 | 每核≥4KB，否则不值得开核 |
| 多核对齐 | 元素数对齐到512 |
| UB对齐 | 按256B对齐确保Vector指令效率 |
| 跨核偏移 | `blockFormer * blockIdx * sizeof(dtype)` |
```

`经验规则` — empirical rules — is upstream's own header, and under 0104's provenance rule all three
constants trace to literals with no chip-configuration chain. They are software 经验值 and
searchable; upstream labels them as such without using that vocabulary.

The precision branch, `tiling-flow.md:17-20`:

```
Step 2 — dtype×运算判定 (决定Compute路径):
  运算为Add/Sub + dtype∈{FP16,BF16} + 输入量级未知?
    → 升精度分支: Cast→FP32计算→Cast, 需额外FP32中间Buffer
    → 否则: 原dtype直接计算
```

its budget consequence, `:48-49` and `:80-86`:

```
升精度分支:
  bufferDivisor = bufferNum * elemBytes + K * sizeof(float)
```
```
| 项 | 原dtype直算 | 升精度分支 |
|---|------------|-----------|
| 输入/输出Buffer | half/bf16 | half/bf16 (不变) |
| FP32中间Buffer | — | K份 ubFormer*sizeof(float) |
| UB总占用 | bufferNum*ubFormer*elemBytes | 左边 + K*ubFormer*4 |
```

and the two fields it sets, `tiling-fields.md:23-24`:

```
| `use_fp32_cast` | bool | 是否启用FP32升精度 | dtype + op_type判定 |
| `K_extra_buffers` | int | 升精度额外FP32 buffer份数 | API别名约束 |
```

`K` is never given a value, and `API别名约束` — API aliasing constraints — is named as its source
without saying which API or which constraint. `输入量级未知` (input magnitude unknown) is a host-side
predicate over runtime data, and upstream does not say how the host decides it; for a static tiling
pass the honest reading is that it is a caller-supplied flag, and upstream does not say that either.
Both recorded in `harvest/standing/950-tiling.md`.

The script implements the multi-core rule faithfully,
`elewise/fallback/script/elewise_tiling.py:149-161`, including a floor the markdown omits:

```python
    core_num = (dim0 * min_dtype_bits + MIN_TILING_BITS - 1) // MIN_TILING_BITS
    core_num = min(core_num, available_cores)
    core_num = max(core_num, 1)
```

`max(core_num, 1)` guarantees at least one core, so any downstream check asserting `coreNum ≥ 1`
cannot fail — the same floored-predicate species this book records elsewhere.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and discard the
case if the die moved. Variance floor first: one build, 30 in-process runs and 5 fresh-process runs.

Arm 1 — the 4 KB floor. Fix `Abs` at fp16 and sweep `dim0` so the derived `coreNum` moves from 1 to
the queried core count: `dim0 ∈ {1024, 2048, 4096, 8192, 32768, 131072, 1048576}`. At each `dim0`
build two kernels with one compiler pin: the plan the formula gives, and a plan that opens the full
core count regardless. md5 each; host echo of `coreNum`, `blockFormer`, `blockNum`, `ubFormer`;
output against an fp64 reference within tolerance; `aiv_time` under
`msprof --aic-metrics=PipeUtilization`, ≥10 iterations, first 5 dropped, per case. Repeat at int8 and
fp32, where the floor lands at different element counts.

Arm 2 — the 512-element alignment. At one `dim0` in the multi-core regime, build with
`blockFormer` aligned to 512, to 256, to 64 and unaligned (exact `CeilDiv`), and record `aiv_time`
plus MTE2 bytes. If alignment is doing what upstream says, the unaligned arm moves more bytes.

Arm 3 — the promotion branch. Build fp16 `Add` with and without promotion on two inputs: one with
operands within a factor of 2 (where fp16 should be adequate), one with operands 2^12 apart (where it
should not). Compare both arms elementwise against an fp64 reference and record the maximum absolute
and relative error, plus `aiv_time` and the resulting `ubFormer` for each. This measures both halves
— what promotion buys numerically and what it costs in tile size — on the same case.

Refuses to assume: that a free die stays free; that a die may be substituted; that `ubSize` or the
core count are the script's literals (queried, 0141); that a `coreNum` that builds was used (host echo
required); that the 4 KB floor is right — arm 1 exists to find the crossover; that `K = 1` (it is
swept over {1, 2, 3} and the value that matches the observed UB occupancy is recorded).

## 5 · Checker — acceptance declared before the run
Verdict variable `floor_justified(dim0)`: true iff the formula's plan is at least as fast as the
full-core plan, by more than the variance floor, at every `dim0` where the formula opens fewer cores.
Declared acceptance: the 4 KB floor is supported iff `floor_justified` holds at every such `dim0`.
The OVERTURN fires iff the full-core plan wins by more than the variance floor at any of them.
Verdict `align_gain` from arm 2 is the MTE2 byte ratio between the unaligned and 512-aligned arms.
Verdict `promote_needed`: true iff the non-promoted arm's relative error on the wide-magnitude input
exceeds the operator's declared tolerance while the promoted arm's does not.

The exit code is not the verdict: an elementwise kernel with a wrong `ubFormer` may write past its
tile and still exit 0 (0151). The elementwise output comparison runs on every arm and the checker
fails red if it did not. Second guard: the host echo of `coreNum` and `blockFormer` must match the
requested plan at every point, because a full-core arm the host silently clamped back to the formula's
core count would make `floor_justified` true from an experiment that never opened extra cores.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured. The entry does not establish the 4 KB floor, the 512-element alignment or the
256-byte UB alignment — upstream calls all three `经验规则` and gives no derivation or measurement for
any. It does not establish `K`, does not identify the API aliasing constraint that sets it, and does
not establish how `输入量级未知` is decided on the host. It does not establish that promotion is
necessary for any input distribution. It inherits 0151's caveat: the `ubFormer` these rules feed is
computed by a formula this book records as dimensionally unclosed in the markdown, so any plan derived
from the markdown alone is suspect independently of the rules here. No chip is named anywhere in the
elewise family, so BOARD is `family-claimed(unverified)` and the chip is unstated; §4 names
950PR/950DT because that is where our run would happen. Nothing here is established for any 910-family
board.
