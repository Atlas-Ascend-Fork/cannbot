```
ID:        0161-scatter-is-latency-bound-not-bandwidth-bound-and-three-measured-laws-on-ascend950pr-set-every-threshold
LABEL:     knowledge
LEVEL:     L9 (performance)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     950PR
SOURCE:    ops/ascendc-perf-optimize/references/tiling/scatter/fallback/tiling-flow.md:308-312,351-355 —
           "| **散射吞吐 ∝ 总线程数** | 每 block 8 / 32 / 128 / 512 线程 → 0.5 / 1.7 / 3.3 / 10~27
           G updates/s | 访存**延迟**受限，不是带宽受限（顺序流式 pass 能跑 ~600 GB/s）" ·
           "| **32 位原子 ≈ 3× 64 位原子** | 11~18 G/s vs 4.7~5.0 G/s |" · "random 2805us /
           rowwise 583us（**4.81×**）/ constant 562us" · "建议标注为 **MEM BOUND（latency，非 bandwidth）**"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured scatter on a named 950 board where reducing bytes moved improves wall time more
           than raising total thread count does — the family would then be bandwidth-limited after
           all, and every threshold derived from the latency reading would need re-deriving.
```

# 0161 · Scatter is latency-bound, not bandwidth-bound, and three measured laws on Ascend950PR set every threshold

## 1 · Claim
Upstream asserts three measured regularities for scatter on Ascend950PR and states that they are the
source of the family's thresholds. First, scatter throughput scales with total thread count — 8, 32,
128 and 512 threads per block giving 0.5, 1.7, 3.3 and 10–27 G updates/s — and upstream reads this as
memory *latency* limitation rather than bandwidth limitation, noting that the sequential streaming
passes reach about 600 GB/s while the scatter side runs at a few G updates/s. Second, 32-bit atomics
run at roughly 3× 64-bit atomics, 11–18 G/s against 4.7–5.0 G/s, which is why splitting into two
32-bit passes is preferred over one 64-bit key and also halves sequential traffic from 24 B to 12 B
per element. Third, random scatter write amplification is an order-of-magnitude effect: the same
kernel with the same instruction count and the same read pattern, varying only the index
distribution, measures random 2805 µs against rowwise 583 µs (4.81×) and constant 562 µs, because
32 lanes in a warp with contiguous `c` and differing `ix` land on 32 distinct cachelines using two
bytes of each. Upstream asserts this cannot be fixed by changing path, since ② and ③ write through the
same address expression. Upstream asserts a labelling consequence: marking this family `MEM BOUND` on
a bandwidth reading misleads, and the correct label is `MEM BOUND（latency，非 bandwidth）` with total
thread count given as the actual constraint. Not established here — these are upstream's
measurements, not ours.

## 2 · The wrong branch this removes
This is the entry that changes what an agent optimises. A profile showing a saturated memory pipe
routes every standard playbook toward reducing bytes moved: fuse, cache, reuse, shrink the tile.
Upstream's measurements say the memory pipe is not saturated in the bandwidth sense at all — the
streaming passes prove the bandwidth is there — and that the scatter passes are waiting on latency.
The correct lever is total thread count, which is the opposite of what "reduce traffic" suggests, and
upstream states the mislabel's cost directly: `否则会被引向"减少搬运量"这类无效方向`.

The write-amplification law removes a second wrong branch, and it is the harder one to accept: the
4.81× between random and rowwise indices is a property of the *input data*, not of the plan. An agent
that sees a slow case and searches for a better path is searching a space that cannot contain the
answer — upstream says so explicitly, `换路径救不了`, because ② and ③ write through the same
`y[ix*inner+c]` expression. The honest response is to report the index distribution as the cause,
which no tiling change addresses.

The atomic-width law removes a third: reaching for a single 64-bit key because it is simpler than two
32-bit passes. The 3× throughput ratio plus the halved sequential traffic is why path ③ exists as two
passes rather than one.

## 3 · Ground / Source
`scatter/fallback/tiling-flow.md:301-312`, §5.1 in full:

```
## 5. 实测阈值的来源（改阈值前先读这节）

### 5.1 硬性规律

> 本节数字与最佳实践货架的 [scatter_design.md §5](../../../../../ascendc-performance-best-practices/reference/scatter/scatter_design.md) **同源**，改动请同步两处。

| 规律 | 实测数据 | 对 Tiling 的含义 |
|---|---|---|
| **散射吞吐 ∝ 总线程数** | 每 block 8 / 32 / 128 / 512 线程 → 0.5 / 1.7 / 3.3 / 10~27 G updates/s | 访存**延迟**受限，不是带宽受限（顺序流式 pass 能跑 ~600 GB/s）。优先堆总线程数 |
| **32 位原子 ≈ 3× 64 位原子** | 11~18 G/s vs 4.7~5.0 G/s | 宁可拆两趟 32 位（③），别用一趟 64 位键；顺序流量还从 24B/元素降到 12B/元素 |
| **随机散射写放大是数量级的** | 同 kernel、同指令数、同读模式，只换 index 分布：random 2805us / rowwise 583us（**4.81×**）/ constant 562us | 写地址 `y[ix*inner+c]`，一个 warp 内 32 线程 `c` 连续、`ix` 各异 → 落 32 条不同 cacheline 每条只用 2 字节。**换路径救不了**（②③写同一个地址式子） |
```

The `同源，改动请同步两处` note is a dual-maintenance obligation with no enforcement mechanism — the
same numbers live in a sibling skill and nothing checks that they stay equal. Recorded in
`harvest/standing/950-tiling.md`.

The bound-labelling consequence, `:351-355`, in full:

```
## 6. bound 类型怎么标（本族与通用口径的偏差）

按带宽口径标 `MEM BOUND` 会误导后续策略：**散射是访存延迟受限**，顺序流量能跑到 ~600 GB/s，
而散射侧只有几 G updates/s，远未打满带宽。建议标注为 **MEM BOUND（latency，非 bandwidth）**
并同时给出"总线程数"这一实际制约量，否则会被引向"减少搬运量"这类无效方向。
```

The `starved` threshold derived from law 1, `:314-317`:

```
### 5.2 `starved` 门槛 = `coreNum × 1024`

元素级并行**买的是并行宽度、付的是原子/仲裁开销**。已经铺满核的 shape 切过去只是多付一趟仲裁，
所以门槛就取"纤维路径能否喂满 `coreNum × 每 block 最大线程数`"。
```

Path ⑤'s fiber threshold and its measured counter-case, `:319-325`:

```
### 5.3 ⑤ 的纤维数门槛 1024 **不能往下调**

放宽到 256 后，某 `int64 none` 用例（**511 纤维、`sIdx=2048`**）从③的 133.67us 劣化到⑤的 **295.94us**：

- 511 条纤维只能铺 `511 × 32 = 16352` 线程；③按元素级铺满核（约 105 万个更新）
- 每 warp 要跑 `2048/32 = 64` chunk × 15 步 bitonic = **960 步排序**
- 省掉的 fill-zero（8.51us）+ workspace 往返远不足以补偿
```

Re-derived: `511 × 32 = 16352` ✓; `2048 / 32 = 64` chunks and `64 × 15 = 960` steps ✓;
`295.94 / 133.67 = 2.21×` degradation. The arithmetic checks out, and the case identity is unusually
complete — dtype, reduce mode, fiber count, `sIdx`, both timings, and the fill-zero cost it would have
saved.

A declined change with a stated reason, `:327-330`:

```
### 5.4 ⑤ 放宽到 8 字节值：安全但无收益证据

改动本身安全（排序全基于 uint32 键，值类型只出现在最后一句赋值），但实测零收益（噪声内），
且 §5.3 那条 int64 用例的数据反而指向 warp 对 int64 不利。**要启用先补"int64 + 大纤维数"的实测。**
```

The decision table that summarises the fiber threshold, `:341-347`:

```
| numFibers | jBits+idxBits | 结论 |
|---|---|---|
| 2048 | 21 ✓ | 走 ⑤ |
| 511 | 24 ✓ | 卡纤维数门槛 → ③（**已验证这样更快**） |
| 1 | 32 ✗ | 单纤维且键装不下 31 位 → ③ |
```

And the sequential-pass measurement that anchors the "not bandwidth-bound" reading, `:250`:

```
`y = data` 的整块 clone 与半精度 cast 是**规则顺序流量，必须走 SIMD 的 MTE**（用 SIMT 标量循环实测慢一个数量级：某用例 **1565us → 89us**）。
```

`1565 / 89 = 17.6×` — a measured order of magnitude for using the vector DMA path instead of a scalar
loop on the regular passes, with a case that is not otherwise identified.

Every figure in this section is stated with a unit and most with a case, and none carries a
repetition count, a variance figure or a date. The 4.81× is the best-identified: same kernel, same
instruction count, same read pattern, one variable. The `10~27 G updates/s` range at 512 threads
spans 2.7× and is given as a single table cell.

## 4 · Procedure
Proposed, runnable later on Ascend950PR — the board upstream names, so a re-measurement is
comparable; a 950DT run is a separate claim. Never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and discard the
case if the die moved. Variance floor first, and it matters more here than anywhere else in this
domain because the source's ranges are wide: one build, 30 in-process runs and 5 fresh-process runs,
interquartile range over median, reported beside every ratio below.

Arm 1 — the latency-versus-bandwidth reading, which is the entry's central claim. On one `starved`
case, run two interventions independently: (a) raise total thread count across the launchable values
while holding bytes moved constant; (b) halve bytes moved while holding total thread count constant
(narrow the value dtype from 4 B to 2 B on an otherwise identical shape). Record `aiv_time`, achieved
GB/s and G updates/s for every point under `msprof --aic-metrics=PipeUtilization`. The latency reading
predicts (a) helps and (b) does not; the bandwidth reading predicts the reverse. This is the arm that
can go either way, and the direction is the finding.

Arm 2 — the index-distribution law. Build one kernel and run it on three index sets on identical data:
uniformly random, rowwise, and constant. Compare against upstream's 2805 / 583 / 562 µs. Then repeat
under paths ② and ③ to test `换路径救不了` directly — upstream asserts it from the shared address
expression, which is an argument, not a measurement.

Arm 3 — the atomic-width law. Time a 32-bit `atomic_max` pass and a 64-bit one on matched element
counts, recording G/s for each, and separately record the sequential bytes per element for path ③
against a hypothetical single-64-bit-key path, checking the stated 24 B → 12 B.

Arm 4 — the ⑤ threshold counter-case, reproduced exactly: `int64`, `reduce=none`, 511 fibers,
`sIdx = 2048`, built under both ③ and ⑤ with the threshold relaxed. Upstream's numbers are 133.67 µs
and 295.94 µs; both are re-measured with the variance floor attached.

Refuses to assume: that a free die stays free; that a die may be substituted; that `coreNum` is a
literal (queried, 0141 — `starved = numFibers < coreNum × 1024` depends on it); that a single run is a
measurement; that the profile's GB/s figure covers the scatter passes and the streaming passes
comparably — if it aggregates them, arm 1 reports `void` for the bandwidth half rather than inferring
it; that upstream's ranges are reproducible on a different CANN version, which is recorded with every
result.

## 5 · Checker — acceptance declared before the run
Verdict variables `thread_elasticity` = the slope of G updates/s against total thread count from arm
1(a), and `byte_elasticity` = the fractional time change per fractional byte change from arm 1(b),
both with the variance floor. Declared before the run: the latency reading is supported iff
`thread_elasticity` is positive and materially above the floor while `byte_elasticity` is within the
floor. The OVERTURN fires iff `byte_elasticity` exceeds `thread_elasticity` — the family is then
bandwidth-limited and every threshold derived from the latency reading needs re-deriving.

Verdict `dist_ratio` = random median / rowwise median from arm 2, compared against 4.81×, and
`path_invariance`: true iff `dist_ratio` is the same within the floor under ② and ③, which is what
`换路径救不了` predicts. Verdict `atomic_ratio` from arm 3 against the stated ≈3×. Verdict
`five_penalty` from arm 4 against the stated 2.21×.

The exit code is not the verdict. Three guards. First, every timed arm's output is compared
elementwise against a CPU reference on duplicated-index input (0158) — a thread-count or path change
alters atomic interleaving, and a wrong result timed as a win is the failure this whole family's
acceptance metric is built to catch. Second, arm 1's two interventions must be shown to be
independent: the byte-halving arm must echo an unchanged total thread count and the thread arm an
unchanged byte count, and the checker goes red if either moved, because a two-variable comparison
carries no attribution. Third, the variance floor must exist before any ratio is reported; upstream's
own `10~27 G updates/s` cell shows what a ratio without one looks like.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. Every number in §3 —
0.5/1.7/3.3/10–27 G updates/s, ~600 GB/s, 11–18 vs 4.7–5.0 G/s, 2805/583/562 µs, 4.81×,
133.67/295.94 µs, 8.51 µs, 1565→89 µs — is upstream's readout on Ascend950PR; this book has
reproduced none of them.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured by us. `BOARD: 950PR` records the board upstream's evidence names; the stratum,
not the board field, says who measured. The entry does not establish any of the three laws. None of
upstream's figures carries a repetition count, a variance figure, a date or a CANN version, and one
of them (`10~27 G updates/s`) is a range spanning 2.7× presented as a single data point — so their
precision is not their reliability. The latency-versus-bandwidth reading is an *inference* upstream
draws from two measurements taken on different passes (scatter throughput and streaming bandwidth);
this entry records the inference as an inference, and §4 arm 1 is what would establish it directly.
The `换路径救不了` claim is likewise argued from a shared address expression rather than measured
across paths. The 4.81× is a property of index distributions, not of any tiling decision, and no plan
in this family changes it. Nothing here is established for 950DT or for any 910-family board.
