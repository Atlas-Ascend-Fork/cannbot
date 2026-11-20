```
ID:        0134-the-scan-template-is-picked-by-index-tracking-first-then-by-n-width-and-r-against-ub
LABEL:     knowledge
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/tiling/scan/fallback/tiling-flow.md:39-61,114-125 —
           "┌─ 带索引？(Cummin / Cummax，需输出 argmin/argmax)" · "└─ 无索引 (Cumsum / Cumprod /
           LogCumsumExp) ├─ N 宽（alignN > VREG/4=16 元素 fp32） → 【oneway Sklansky】 └─ N 窄
           （alignN ≤ VREG/4，且折叠 foldCount>1） → 【twoway 折叠】" ; the 8-row 模板速查 table
           with "流式（streaming） ... 仅作参考实现，**勿用于性能路径**"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured scan on a named 950 board where the streaming template — which upstream
           forbids on the performance path — matches or beats the template its decision tree
           selects for the same shape; that would make the routing tree's central exclusion wrong.
```

# 0134 · The scan template is picked by index tracking first, then by N width and R against UB

## 1 · Claim
Upstream asserts a decision tree for scan whose first question is whether the operator must emit an
index: Cummin and Cummax need argmin/argmax and route to the index-capable templates, while Cumsum,
Cumprod and LogCumsumExp route to the Sklansky family. On the indexed side, `N > 1` selects a
tile-resident scan holding the running `(val, idx)` pair in registers with an `[R][lane]` UB layout
and zero DMA inside the loop, and `N == 1` selects one of three modes by a further three-way
decision (0136). On the un-indexed side, a wide N — `alignN > VREG/4`, which upstream annotates as
16 elements at fp32 — selects one-way Sklansky combining whole rows along contiguous R, while a
narrow N with `foldCount > 1` selects two-way folding, packing a long R into idle vector lanes and
running a two-level Sklansky. Either branch then takes an R-versus-UB test: R fully resident gives
template keys 1001/1002, R exceeding UB adds a serial `ub chunk` layer with binary carry memoisation
giving 1011/1012, and insufficient parallelism with a very long R escalates to cross-core R
borrowing (1101/1102/1111/1112). Upstream asserts the streaming template — running state updated
serially along R — is a reference implementation only and must not be used on a performance path.
Not established here.

## 2 · The wrong branch this removes
The streaming template is the one an agent writes by default, because a prefix scan *is* a serial
running update and the streaming form is the direct transcription of the definition. Upstream marks
it `仅作参考实现，勿用于性能路径` and quantifies what happens when it is used: for `M = N = 1` it
produces a single work-item, one core, per-element micro-DMA, and about 230 µs on a million points
(`:345`). Nothing about that plan looks wrong — it is correct, it is simple, and its profile shows a
busy memory pipe.

The index-first ordering removes a second wrong branch. Sklansky is the better-known algorithm and
an agent that reaches for it on a Cummax must then bolt index tracking onto a log-depth tree, where
tie-breaking across levels is not expressible without extra passes. Upstream routes index-carrying
operators away from Sklansky entirely and to templates whose running state is a `(val, idx)` pair,
which makes the tie rule (0138) a single comparison mode rather than a merge policy.

The `N > 1` / `N == 1` split removes a third: whether the scan axis is contiguous in GM. At
`N == 1` a whole row is one descriptor and the interesting question becomes how many rows to move
at once; at `N > 1` the scan axis is strided and the lane dimension has to come from N or from
folded M. Those are different tiling problems, and upstream keeps them apart at the top of the tree.

## 3 · Ground / Source
`scan/fallback/tiling-flow.md:39-61`, the tree in full:

```
输入: (M, R, N), dtype, op_type, ub_size, core_num

┌─ 带索引？(Cummin / Cummax，需输出 argmin/argmax)
│    ├─ N > 1（dim 非最后一维）
│    │    → 【tile 常驻扫描】整段 R 一次搬进 UB 按 [R][lane] 布局，
│    │      running-(val,idx) 常驻寄存器，循环体内零 DMA。lane 维用 N（N 够宽）
│    │      或借 M 轴折叠（N 窄）。**不要退化成逐 r 搬入搬出，实测慢 8~50 倍**
│    │      并且 **x/val/out 必须各开两份做 ping-pong**：块间 carry 串行、
│    │      计算无法重叠，但「搬入下一块 / 算当前块 / 搬出上一块」可以。
│    │      不做的话四条流水占比之和只有 101%（全串行），实测慢 12~31%。UB 预算见 §5.2
│    │      若 lane 数用不满（如 M=1 且 N 只切得出十几个元素宽的 tile）→ 转 §4.1
│    └─ N == 1（dim=-1，扫描轴在 GM 上连续）→ 见 §3.2
│      并行度判定见 §3.1；若 M×N 极小 + R 超长 → 转 §4 跨核借 R
│
└─ 无索引 (Cumsum / Cumprod / LogCumsumExp)
     ├─ N 宽（alignN > VREG/4=16 元素 fp32）
     │    → 【oneway Sklansky】沿连续 R 行整行向量 combine；R 全载 UB → key 类 1001
     │      R 超 UB → 叠加 ub chunk（key 类 1011）
     └─ N 窄（alignN ≤ VREG/4，且折叠 foldCount>1）
          → 【twoway 折叠】长 R 折叠进向量道，段内→段间两级 Sklansky；R 全载 → 1002；超 UB → 1012
     两分支再过 §3.1 并行度判定：M 小 + R 超长 → 跨核借 R（1101/1102/1111/1112）
```

The template summary, `:116-125`:

```
| 模板 | 带索引 | N | R vs UB | M×N 并行度 | 关键策略 |
|------|:---:|---|---------|-----------|---------|
| **tile 常驻 + ping-pong** | ✅ | **>1** | 切 rChunk，块间 UB carry | 够满核 | `[R][lane]` 布局，running 常驻寄存器，三条流水重叠 |
| **lane 并行顺序扫描** | ✅ | **==1** | 整行入 UB | 够满核 | gather 虚拟转置，指令条数与 log2(R) 脱钩 |
| 行内 Kogge-Stone | ✅ | ==1 | 整行入 UB | 够满核 | log2(R) 级；R 小到一两个 chunk 时比 lane 并行划算 |
| 流式（streaming） | ✅ | 任意 | 逐 r 切片（不必全载） | 够满核 | 常驻 running-(val,idx)，仅作参考实现，**勿用于性能路径** |
| oneway Sklansky | ❌ | 宽 | 全载 | 够满核 | ceil(log2 R) 层整行 combine |
| twoway 折叠 | ❌ | 窄 | 全载 | 够满核 | 长 R 折叠进向量道，两级扫描 |
| +ub chunk | 视内层 | — | 超 UB | 够满核 | chunk 串行 + 二进制进位 memo |
| **core partition（借 R）** | **视内层** | — | 超长 | **不足** | 跨核切 R + 保序进位 |
```

The parallelism test that gates the escalation, `:63-72`:

```
流式/oneway 先按切 M（行）或借 N 估 work-item 数 items：
  items ≥ core_num              → 直接切行，够满核
  items < core_num（不足）      → 先缩小分块补偿（减小 nTileLen/mBlk 提高 items，对齐 VL）
  仍 items ≪ core_num 且 R 超长 → 转 §4 跨核借 R（core partition）

Cumsum 生产 tiling 的等价判据（以促进 fp32 尺寸）：`M > core_num/2` 时切 M 即够（不借 R）；否则借 N 再借 R。
```

The twoway gate's full condition set, `:296`:
`窄 N 门控: alignN ≤ VREG/4；foldCount>1；fp16/bf16 foldCount≤4；foldLen≥256（向上取 2 的幂）`.

Three unconditioned measurements appear inside the tree itself: `实测慢 8~50 倍` for degrading the
tile-resident path into per-`r` moves, `实测慢 12~31%` for omitting ping-pong (0136), and
`四条流水占比之和只有 101%` as the symptom of full serialisation. None carries a board, shape,
dtype, core count or repetition count, and the first is a range spanning a factor of six.

`VREG` is used in two unit systems in this file. At `:57` and `:296` it appears as
`VREG/4 = 16 元素 fp32`, implying `VREG = 64` in *elements*; at `:145`,
`guardC = 256 / cBytes // 哨兵区 = 1 vreg` implies one vector register is 256 *bytes*. Both readings
are consistent with a 256 B register holding 64 fp32 elements, but the symbol is never given units,
so `VREG/4` could be read as 64 bytes by a reader who met `:145` first. Recorded in 0137.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s
spacing; bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and
discard the case if the die moved. Measure a variance floor first, by building one configuration
once and running it 30 times in-process and 5 times across processes.

Arm 1 — the streaming exclusion, which is the falsifiable core. For four shapes spanning the tree's
leaves (`M=4096,R=1024,N=1` Cummin; `M=64,R=1024,N=512` Cummin; `M=4096,R=4096,N=1` Cumsum;
`M=1,R=1000003,N=1` Cumsum), build the template the tree selects and the streaming template, one
compiler pin, md5 per binary, host echo of `mode` / template key and of `(M,R,N)`. Every arm's
output is compared elementwise against a CPU reference: for min/max, bit-identity is required; for
Cumsum, a tolerance is declared in advance because Sklansky and streaming accumulate in different
orders. Record `aiv_time` under `msprof --aic-metrics=PipeUtilization`, ≥10 iterations, first 5
dropped, per case.

Arm 2 — the N-width boundary. Fix an un-indexed operator and sweep `N` across the `alignN = VREG/4`
boundary — `N ∈ {4, 8, 12, 16, 20, 32, 64}` at fp32 — building both oneway and twoway at every N
where both are legal, recording which the host selects and which is faster.

Arm 3 — the parallelism escalation. Fix `R = 1000003`, `N = 1`, sweep `M ∈ {1, 4, 16, 32, 64, 128}`
across `core_num/2`, and record which branch the host takes and the time of each available branch.

Refuses to assume: that a free die stays free; that a die may be substituted; that `core_num` is 64
or 72 (queried, and both `items ≥ core_num` and `M > core_num/2` move with it); that `ub_size` is
any literal; that `VREG/4 = 16` (arm 2 sweeps across the boundary rather than testing at it); that
a template that builds is the template that ran (echo required); that Cumsum's two orders agree
bit-for-bit — they do not, and the tolerance is declared before the run rather than after seeing
the diff.

## 5 · Checker — acceptance declared before the run
Verdict variable `tree_picks_best(shape)`: true iff the template the tree selects has the lowest
median `aiv_time` among the legal templates for that shape, by more than the variance floor.
Declared acceptance: the tree is a selector iff `tree_picks_best` holds on all four arm-1 shapes.
The OVERTURN fires iff the streaming template matches or beats the selected template on any shape —
upstream's `勿用于性能路径` would then be wrong for that leaf. Arm 2's verdict `nwidth_cross` is the
N at which oneway and twoway swap places, checked against the predicted 16 elements at fp32; arm 3's
`escalation_point` is the M at which cross-core R borrowing starts winning, checked against
`core_num/2`.

The exit code is not the verdict. Three guards. First, template identity: the host echo of `mode` or
template key must differ between the two arms at every point; if the tree overrode a forced choice,
the two arms are one experiment and no comparison is valid — the checker goes red. Second, the
variance floor must exist before any ratio is reported; a `8~50 倍` claim in the source with no
repetition count is exactly the shape of number this guard exists to avoid reproducing. Third, the
elementwise comparison runs on every arm including the fast ones, because a wrong scan is far more
likely than a slow one when the lane layout changes, and a checker that reads only timings would
score a broken kernel as a win.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The `8~50 倍`,
`12~31%`, `101%` and `230µs` figures are upstream's, all unconditioned.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured. The entry does not establish that the tree selects the best template for any
shape, does not establish the `VREG/4` boundary or the `foldCount`/`foldLen` gates, and does not
establish that streaming is always wrong on a performance path — upstream asserts it and gives one
unconditioned range. It does not cover the `N == 1` three-way decision (0136) or the mode-selection
pseudocode's constants. It does not establish `ub_size` or `core_num`. The template keys
(1001/1002/1011/1012/1101/1102/1111/1112) are recorded as upstream's naming and their internal
structure is not decoded here. No chip is named anywhere in the scan family, so BOARD is
`family-claimed(unverified)` and every measured number in the family is unscoped; §4 names
950PR/950DT because that is where our run would happen. Nothing here is established for any
910-family board.
