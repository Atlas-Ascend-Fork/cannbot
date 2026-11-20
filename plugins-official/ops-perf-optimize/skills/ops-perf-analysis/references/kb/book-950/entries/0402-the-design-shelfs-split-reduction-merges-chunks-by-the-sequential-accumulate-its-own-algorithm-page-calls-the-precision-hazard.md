```
ID:        0402-the-design-shelfs-split-reduction-merges-chunks-by-the-sequential-accumulate-its-own-algorithm-page-calls-the-precision-hazard
LABEL:     trap
LEVEL:     L5 (compute & numerics)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-tiling-design/references/reduction/ar-colsplit.md:125-127 —
           "1. **跨 chunk 合并**: / - ReduceMax: 使用 `if` 或者 `三目运算` 取最大值 /
           - ReduceSum: 使用 `+=` API 累加" ; :99,116 — "float globalMax = -INFINITY;" ·
           "globalMax = chunkMax;"
SOURCE:    ops/ascendc-tiling-design/references/reduction/alg-dichotomy.md:5 —
           "**问题**: 顺序累加 `sum = a1 + a2 + a3 + ...` 时，当 sum 已经很大而后续元素很小，
           小数会因浮点精度被"吃掉"。" ; :40 — "| 精度 | 大数吃小数 | 相近量级先加，精度更好 |"
           (same file tree — this is the shelf contradicting itself, not a second origin)
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a 2-D FP32 ReduceSum on a named 950 board, at an R large enough to force the split arm and
           with an input whose magnitudes span several decades, in which the scalar `+=` cross-chunk
           merge and the binary fold produce max absolute errors against a float64 reference that
           differ by less than the run-to-run variance floor. The precision distinction the shelf's
           own algorithm page asserts would then not be observable at the cross-chunk level, and this
           entry's reason for caring about the merge mechanism would be wrong.
```

# 0402 · The design shelf's split reduction merges chunks by the sequential accumulate its own algorithm page calls the precision hazard

## 1 · Claim
Upstream asserts, in the design shelf's AR split-load branch, that chunks are combined by a scalar
running variable held outside UB: a `float globalMax` initialised to `-INFINITY` and updated by a C
`if` per chunk for max, and `+=` per chunk for sum. Upstream asserts separately, two files away in the
same shelf, that sequential accumulation is precisely the pattern that loses small addends to a large
running total (`大数吃小数`), and that the fix is a binary fold so that operands of similar magnitude
meet first. Upstream lists that binary fold as an **orthogonal dimension** to be selected when a sum
is precision-sensitive, and does not wire it into the split arm's stated merge. The analysis shelf's
counterpart arm makes the binary fold the merge itself, with a named 2048-byte cache and a
`fold_base`/`fold_remain` decomposition; the implementation shelf makes it a named piece of shared
kernel machinery (`UpdateCache` / `GetCacheID` / `FindNearestPower2`) common to both Recompute
templates and describes it as `O(log N) 层而非 O(N) 串行`. Not established here.

## 2 · The wrong branch this removes
An agent asked to tile a large-R ReduceSum reads the design shelf's split branch, finds a complete
worked implementation with buffer sizes, a chunk loop and an explicit merge rule, and ships it. The
merge rule it ships is `sum += chunkSum`, executed once per chunk in program order. At `R = 10^6` with
`r_chunk` around 10^4 that is a hundred sequential float32 additions of partial sums that are
themselves each ~10^4 elements — the exact shape the shelf's own `alg-dichotomy.md` opens by warning
about. The result is not wrong enough to fail a smoke test and not right enough to pass a tight
tolerance; it fails late, in someone else's precision gate, and the tiling document that produced it
looks blameless because the numbers it computed were correct.

What makes this a trap rather than a gap is that the shelf *has* the fix and files it somewhere the
agent has no reason to look. `patterns.md:53` lists 二分累加 under 正交维度 — a table the reader is told
to consult "确定分支后，根据算子特征和数据规模选择" — with the applicability condition `大向量 sum
精度敏感`. So the correction is available, conditional, and phrased as an optional refinement for a
class of operators the agent must self-identify into. The split arm's own text never mentions it. An
agent following the tree top-down reaches the merge rule before it reaches the orthogonal table, and
first-match trees are not re-entered.

The second wrong branch is the opposite: treating the two merges as interchangeable because both are
"combine the chunk results". They differ in three ways that all matter and none of which is a
precision question. The scalar merge reads a value out of UB into a general-purpose register every
chunk (`chunkResultLocal.GetValue(0)`), which is a vector-to-scalar dependency — the exact stall this
book records elsewhere as a scalar-bound cause (`0017`, `0026`). The fold merge keeps partials in UB
and pays 2048 bytes for the privilege (`0123`). And the fold's serial depth is `log2` of the chunk
count rather than the chunk count, which the implementation shelf states outright is the point
(`guide.md:83`, `显著降低长 R 的归约串行延迟`). An agent that reads "different merge" as "same result,
different style" will not think to measure any of those three.

Third, and this is the boundary this entry must not overstate: the two arms are documented for
**different operator classes**, and that may be the whole explanation. The design shelf's ColSplit
declares its output `标量（1 个值）` (`ar-colsplit.md:28`) and its worked example is `ReduceMax` — one
statistic, one pass over GM. The analysis and implementation shelves' Recompute is written for
Softmax and declares three passes (`R 切 chunk，3 阶段重读 GM + 二分累加树`, `guide.md:95`). So it is
possible that ColSplit's scalar merge is adequate for the single-statistic case it documents and the
fold exists only because Softmax's sum-of-exponentials is harder. Upstream never says this. §4 is
built so that the answer is a measurement rather than a reading.

## 3 · Ground / Source
The design shelf's split arm, `ascendc-tiling-design/references/reduction/ar-colsplit.md`. Its
identity, `:18-28`:

```
| 特征 | 说明 |
|------|------|
| **模板类型** | AR 模板（A 轴 + R 轴） |
| **Shape 抽象** | (A1, R) |
| **载入模式** | 分载（整行放不下，分 chunk 处理） |
| **适用条件** | A0=1, R > [全载阈值](#3.1全载阈值) |
| **切分方向** | 列方向（沿 R 分 chunk） |
| **数据连续性** | 每行 R 个元素连续 |
| **Reduce 结果** | 标量（1 个值） |
```

Its merge, `:97-121`, verbatim (the running state is a C scalar, not a tensor):

```cpp
// 初始化全局最大值为 -∞
float globalMax = -INFINITY;

for (uint32_t chunkIdx = 0; chunkIdx < numChunks; chunkIdx++) {
    uint32_t chunkStart = chunkIdx * chunkCols;
    uint32_t chunkSize = (chunkIdx == numChunks - 1) ? lastChunkSize : chunkCols;

    // Load chunk. use `DataCopyPad` in case last chunk is not 32 bytes aligned.
    DataCopyExtParams copyParams{1, static_cast<uint32_t>(chunkSize * sizeof(float)), 0, 0, 0};
    DataCopyPadExtParams<float> padParams{false, 0, 0, 0};
    DataCopyPad(xLocal, xGm[chunkStart], copyParams, padParams);

    // ReduceMax for this chunk
    ReduceMax<float>(chunkResultLocal, xLocal, tmpLocal, chunkSize, false);
    float chunkMax = chunkResultLocal.GetValue(0);

    // Update `globalMax`. DO NOT use `std::` function.
    if (chunkMax > globalMax) {
        globalMax = chunkMax;
    }
}
```

and the rule generalising it to sum, `:123-127`:

```
### 4.3 关键注意点

1. **跨 chunk 合并**:
   - ReduceMax: 使用 `if` 或者 `三目运算` 取最大值
   - ReduceSum: 使用 `+=` API 累加
```

Its own troubleshooting table treats precision loss as an implementation bug rather than a property of
the merge, `:139`:

```
| 精度下降 | chunk 合并逻辑错误 | 确保正确合并（Max取最大值，Sum累加） |
```

Against that, the same shelf's `alg-dichotomy.md:1-8`:

```
# 二分累加（Dichotomy Addition / Half-Interval）

**适用场景**: Sum 归约专用，解决顺序累加中大数吃小数的精度问题

**问题**: 顺序累加 `sum = a1 + a2 + a3 + ...` 时，当 sum 已经很大而后续元素很小，小数会因浮点精度被"吃掉"。

**原理**: 用二叉树结构折叠求和，使相近量级的数先相加。
```

with the algorithm, `:11-33`, whose terminal step names the hardware instruction and its element
ceiling:

```cpp
float DichotomyReduceSum(LocalTensor<float>& src, int count) {
    // Step 1: 找到最大的 2^k ≤ count
    int powerTwo = FindNextPower2LessEqual(count);

    // Step 2: 尾部折叠
    int tail = count - powerTwo;
    if (tail > 0) {
        Add(src, src, src[powerTwo], tail);
        // 变体（Half-Interval）：用 mask 保护尾部
        // Add(src, src, src[powerTwo], GenMask(tail));
    }

    // Step 3: 二分折叠
    while (powerTwo > 64) {
        powerTwo /= 2;
        Add(src, src, src[powerTwo], powerTwo);
    }

    // Step 4: WholeReduceSum 硬件指令（≤64 元素）
    WholeReduceSum(result, src, powerTwo);
    return result;
}
```

and the trade-off table, `:38-43`, which places the sequential form exactly where ColSplit is:

```
| 方面 | 顺序累加 ReduceSum | 二分累加 |
|------|-------------------|---------|
| 精度 | 大数吃小数 | 相近量级先加，精度更好 |
| 适用操作 | 仅 Sum | 仅 Sum（Max/Min 不受影响） |
| UB 开销 | 无额外 | 原地操作，无额外 buffer |
| 典型场景 | R ≤ VL，量级均匀 | R >> VL，量级差异大 |
```

The last row is the sharpest: sequential accumulation's stated typical scenario is `R ≤ VL` — a
reduction axis no longer than one vector length — and ColSplit is by construction the arm for
`R > 全载阈值`, which is many thousands of vector lengths. The document that recommends the sequential
merge and the document that scopes the sequential merge to short R are two files in one directory.

Where the shelf files the fix, `patterns.md:47-54`:

```
**正交维度**（确定分支后，根据算子特征和数据规模选择）：

| 维度 | 选项 | 适用条件 | 详细文档 |
|------|------|---------|---------|
| 算法选择 | Welford Online | 分载 + 需要流式计算两个相关统计量 | [algorithms.md](...) |
| 多核策略 | Group Reduce | R 太大单核处理不完 + A 太小不足以并行 | [algorithms.md](...) |
| 精度策略 | 二分累加 | 大向量 sum 精度敏感 | [algorithms.md](...) |
| 索引跟踪 | With-Index | 归约+返回极值位置 | [with-index.md](with-index.md) |
```

and `algorithms.md:16`, the selection table row: `| Sum 精度敏感 | 二分累加 | 相近量级先加，解决大数吃
小数 | reduce_sum, reduce_var | [alg-dichotomy.md](alg-dichotomy.md) |`.

The other two shelves' answer, quoted as contrast (one repo, one origin — RULES.md Art. 3, so neither
corroborates). The analysis shelf makes the fold the merge, `ascendc-perf-optimize/references/tiling/
reduction/fallback/tiling-flow.md:253-270`:

```
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
```

(the budget half of that block is already carried at `0123`; it is re-quoted here only because
`块间合并: 二分累加` is the line this entry turns on). The implementation shelf names it as shipped
machinery, `ascendc-performance-best-practices/reference/reduce/guide.md:77-78,83,233`:

```
| `UpdateCache` | **跨 chunk/bin 二分累加树**核心：按 `cacheID` 层级归并局部 sum，recompute 类模板共用 |
| `GetCacheID` / `FindNearestPower2` | 二分树层级计算，确定配对关系与根节点位置 |
```
```
> `UpdateCache` 和 `NlastReduceSum` 是 recompute 系模板（AR-Recompute / ARA-Recompute）的关键，
> 把"逐 chunk 串行累加 sum"变为"二分树对数层合并"，显著降低长 R 的归约串行延迟。
```
```
| **二分累加树（UpdateCache）** | AR/ARA-Recompute | 跨 chunk/bin 的局部 sum 按 `GetCacheID` 层级二分合并，O(log N) 层而非 O(N) 串行 |
```

Note the implementation shelf's justification is **latency**, not precision, while the design shelf's
justification for the same structure is **precision**, not latency. Two shelves recommend the same
mechanism for two unrelated reasons, and neither mentions the other's. Registered as `C-950td-003`.

The 3-D counterpart shows the same split of habit. The design shelf's `ara-rowsplit.md:186-190`
merges element-wise in UB (`Max<float>` / `Add<float>` over a `globalResultBuf`), which is not a
scalar round-trip — so within one shelf the 2-D split arm reads a scalar back per chunk and the 3-D
split arm does not, a difference the shelf never comments on. Registered as `C-950td-004`.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase. This entry's
claim is about a *difference between two merges*, so the procedure must vary the merge and nothing
else — the failure species this book records (`a two-point comparison of two different builds carries
no attribution at all`) is the one to design against.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and discard the
case if the die moved. Variance floor first: one build, 30 in-process runs and 5 fresh-process runs,
IQR over median, reported beside every number.

**One kernel, one build, a compile-time merge switch.** Write a single AR split-load ReduceSum whose
chunk loop is identical in every respect except the cross-chunk combine, selected by a template
parameter: `MERGE_SCALAR` implements `ar-colsplit.md:127` (`GetValue(0)` per chunk into a C float,
`+=`), `MERGE_FOLD` implements `alg-dichotomy.md:11-33` over the chunk partials kept in UB, sized to
the analysis shelf's `binary_cache = 2048`. Both instantiations come from one source file and one
compiler pin; record both md5s and confirm they differ (if they do not, the switch did not take and
the run is void). Host echo per arm: the merge mode, `R`, `chunkCols`, `numChunks`, and the runtime
UB capacity actually queried (`0141`).

**Precision arm — the one this entry exists for.** Inputs are generated to make the hazard observable
rather than to be representative: for each of `R ∈ {2^14, 2^16, 2^18, 2^20}`, three input
distributions — (a) uniform `[1, 2)`, the benign control; (b) one element of magnitude `2^20` and the
rest uniform `[2^-10, 2^-9)`, the classic large-eats-small case; (c) log-uniform over `[2^-20, 2^20]`.
Each is generated in float64, rounded to float32 once, and that float32 array is the kernel input, so
both arms see bit-identical data. The reference is the float64 sum of the *same float32 values*
(Kahan-compensated), so the comparison isolates the kernel's accumulation order and not the input
rounding. Record max absolute error and max relative error per arm per case.

**Latency arm.** Same shapes, `aiv_time` under `msprof --aic-metrics=PipeUtilization`, ≥10 iterations,
first 5 dropped, plus the scalar-pipe share so the `GetValue` round-trip is visible if it costs. The
implementation shelf predicts the fold wins on long R by serial depth; the design shelf's fold table
claims the fold has `无额外 buffer`, which contradicts the analysis shelf's 2048-byte cache — record
the actual UB high-water mark of both arms so that sub-claim is answered too.

**Max arm, which must not bite.** Repeat the precision arm for `ReduceMax` with `MERGE_SCALAR` and an
element-wise `Max` fold. `alg-dichotomy.md:41` states `Max/Min 不受影响`, so both arms must agree
bit-exactly. Retained precisely because it is expected to show nothing: if the max arm shows a
difference, the instrument is measuring something other than accumulation order and the sum arm's
numbers are void.

Refuses to assume: that a free die stays free; that a die may be substituted; that the two arms saw
the same bytes (a checksum of the input buffer is echoed from the device by both arms and compared);
that `ub_size` is a literal; that the compile-time switch took effect (two md5s and two echoed modes
required); that a float32 reference is adequate (it is not, and using one would hide the entire
effect).

## 5 · Checker — acceptance declared before the run
Verdict `err_ratio(R, dist)` = max absolute error of `MERGE_SCALAR` divided by max absolute error of
`MERGE_FOLD`, against the float64 reference. Declared before the run: this entry is **supported** iff
`err_ratio > 1 + floor` for at least one `(R, dist)` with `dist ∈ {b, c}` — the sequential merge loses
more than the fold somewhere in the regime the shelf's own dichotomy page describes. The OVERTURN
fires iff `err_ratio ≤ 1 + floor` for **every** `(R, dist)`: the two merges would then be
indistinguishable in accuracy, the shelf's `大数吃小数` warning would not reach the cross-chunk level,
and this entry is corrected in place to a latency-only claim.

Verdict `fold_speedup(R)` = median `aiv_time`(`MERGE_SCALAR`) / median `aiv_time`(`MERGE_FOLD`), with
the floor. Reported, not a pass condition — the implementation shelf's `O(log N) 而非 O(N)` claim
predicts `> 1` and rising with `R`, and a flat or inverted curve is a finding about that claim rather
than about this entry.

Verdict `ub_delta` = UB high-water mark(`MERGE_FOLD`) − UB high-water mark(`MERGE_SCALAR`), in bytes.
Declared before the run: the analysis shelf predicts ≈ 2048; the design shelf's table predicts 0. Both
predictions are recorded now so the readout adjudicates them rather than being read to fit whichever
is remembered.

The exit code is not the verdict, and a reduction returns a plausible float whatever it does wrong.
Four guards. First, both arms are compared elementwise against the reference on every case and the
checker fails red if any comparison did not execute. Second — **the input that makes this checker go
red** — distribution (a), uniform `[1, 2)` with all magnitudes within one octave, must show
`err_ratio ≈ 1` within the floor: there is no large-eats-small effect to find there, and an instrument
that reports the fold winning even on (a) is measuring a build difference, not accumulation order, so
every point is void. Third, the ReduceMax arm must come out bit-identical between the two merges; if
it does not, same conclusion. Both of those are planted positives the instrument must *fail* to find
an effect in, and their purpose is to make "the fold always wins" an unreachable outcome unless it is
true. Fourth, no error figure is reported without the input checksum, the two md5s and the echoed
merge modes; an arm missing any of them is reported untestable, never as agreement.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The `R ≤ VL` observation in §3
is arithmetic on two upstream statements (`alg-dichotomy.md:43`'s typical-scenario row and
`ar-colsplit.md:25`'s entry condition), performed here on paper; no reduction was run and no error was
observed. Upstream supplies no measurement on either merge: neither shelf gives a number, a case, a
board or a tolerance for the precision claim, and the implementation shelf's latency claim
(`显著降低`) is a direction without a magnitude.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The entry does not establish that the scalar merge loses precision
on any board — it establishes that the design shelf prescribes it in the split arm and, two files
away, describes that same pattern as the problem the binary fold exists to solve. It does not
establish that the binary fold is more accurate, faster, or worth 2048 bytes; §5 declares the outcomes
under which each of those readings is wrong. It does not establish that the difference matters for
`ReduceMax`, and `alg-dichotomy.md:41` says it should not — the max arm is a control, not a claim. It
does not resolve the operator-class confound named in §2: ColSplit is documented for a single-statistic
reduction and Recompute for a three-pass Softmax, so a measured difference between them as *shipped*
would not be attributable to the merge, which is exactly why §4 varies only the merge inside one
kernel. It does not establish `ub_size`, `chunkCols`, the 2048-byte cache, the 64-element
`WholeReduceSum` ceiling, or `VL` for any board — the first is recorded as disputed at `0131`, the
last at `0219` from a different source and not re-derived here. It says nothing about the 3-D split
arm's element-wise merge beyond recording that it differs (`C-950td-004`), and nothing about the
interleaved or BlockSplitR paths, whose cross-core merge is a different mechanism (`0124`). No board
token appears anywhere in the design shelf's reduction family, so BOARD is `family-claimed(unverified)`
and §4 names 950PR/950DT only as where our run would happen. Nothing here is established for any
910-family board.
