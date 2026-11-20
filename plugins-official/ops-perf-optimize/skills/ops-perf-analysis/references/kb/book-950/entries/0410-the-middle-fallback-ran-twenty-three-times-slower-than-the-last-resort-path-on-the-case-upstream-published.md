```
ID:        0410-the-middle-fallback-ran-twenty-three-times-slower-than-the-last-resort-path-on-the-case-upstream-published
LABEL:     trap
LEVEL:     L9 (performance)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured by us
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/gather/templates/
           gather_elements_v2_scalar.md:91 — "已观测反例：某 PER_ELEMENT BF16/int32、`Gx=Gi=7`、
           大 inner 的 case，SIMT 为 16.99 us，Scalar 为 388.69 us；将全部 7 个 x 平面的 inner tile
           搬入 UB 后为 7.10 us。这个结果只证明路径选择规则，不应把 `7` 或对应 shape 写成通用门槛。"
SOURCE:    same file :27 — "Scalar 只消除了 index/y 的逐元素 GM 访问，最昂贵的 x 随机 GM 读取仍然存在，
           而且落在 SCALAR 管线。Transpose UB 不够只能说明 Scalar"可用"，不能说明它"更快"。"
SOURCE:    same shelf, templates/gather_elements_small_gd_tiled.md:87 — the same triple, restated:
           "原 SIMT 16.99 us，Scalar 388.69 us，small-GD tiled full-load 7.10 us"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a `PER_ELEMENT` gather on a named 950 board, at a shape where the transpose template's UB
           test fails, in which the Scalar template is faster than the SIMT template by more than the
           variance floor. Scalar would then be a defensible fallback for some regime, and this entry's
           rule — that a UB refusal never selects Scalar — would need its regime stated rather than
           being unconditional.
```

# 0410 · The middle fallback ran twenty-three times slower than the last-resort path on the case upstream published

## 1 · Claim
Upstream asserts that the Scalar gather template is a *candidate* between the transpose path and the
SIMT path rather than a default, and asserts the reason: Scalar converts the index read and the output
write into batched DMA but leaves the expensive part — the random per-element read of `x` — as a scalar
`GetValue` on the SCALAR pipeline, so a transpose path running out of UB shows Scalar is *available*
and not that it is *faster*. Upstream asserts one observed counter-example, stated twice in two files
of the same directory: on a `PER_ELEMENT` BF16/int32 case with seven gather-axis planes and a large
inner dimension, SIMT measured 16.99 µs, Scalar measured 388.69 µs, and loading all seven `x` planes'
inner tile into UB measured 7.10 µs. Upstream asserts that this result establishes the routing rule and
not a threshold, and specifically that neither `7` nor that shape may be written into a gate. Not
established here.

## 2 · The wrong branch this removes
The wrong branch is a default that looks like a decision. A transpose path fails its UB test; the next
thing in the document is Scalar; Scalar is chosen. Nothing in that sequence is a comparison, and the
sequence is what a competent agent does, because a fallback list read top-down *is* a decision
procedure unless someone says it is not. Upstream says it is not, in the sharpest form this
repository offers: `Transpose UB 不够只能说明 Scalar"可用"，不能说明它"更快"`.

The number is what makes the caution unignorable. **388.69 / 16.99 = 22.9**. The middle path is
twenty-three times slower than the path listed after it as a last resort. That is not a tuning
difference; it is a path that should never have been reachable by a UB refusal, and a plan that took it
would look reasonable in review — it uses DMA where it can, it uses less UB, it has a document.

The mechanism is worth carrying separately from the number, because the number is one case. Scalar's
saving is on `index` and `y`, both of which are *contiguous* and therefore cheap to begin with;
`x` is the random access and Scalar leaves it in place while moving it onto the SCALAR pipeline. So
Scalar optimises the two accesses that were already efficient and pessimises the one that was not.
SIMT, by contrast, keeps all three per-element but issues them from 2048 threads whose latencies
overlap. Framed that way the 23× is not surprising: one path hides latency with parallelism, the other
serialises the worst access into a scalar loop.

The third arm of the triple removes a different wrong branch. **16.99 / 7.10 = 2.39**: the best of the
three is neither the documented fallback nor the last resort but the experimental mode with no
`.template` file (`0409`) — loading whole `x` planes contiguously so the random read disappears
entirely rather than being hidden. So the ranking on this one case is
`small-GD (7.10) < SIMT (16.99) << Scalar (388.69)`, and the two paths a reader is most likely to reach
by following the documents are second and third.

The fourth wrong branch is the one upstream pre-empts twice, and it is the reason this entry does not
state a threshold: `不应把 7 或对应 shape 写成通用门槛`. The case has `Gx = Gi = 7`. It would be very
easy, and completely wrong, to leave here with "route to small-GD when the gather axis has ≤ 8 planes".
That is a case-derived constant, which this book already forbids at `0046`, and upstream forbids it in
this family four separate times (`0412`).

## 3 · Ground / Source
The counter-example, `reference/gather/templates/gather_elements_v2_scalar.md:82-91`, in full:

```
## 9. A/B 决策与已知反例

执行以下检查，不要根据单一理论流量直接启用 Scalar：

1. 用 profiling 确认 Scalar 的 SCALAR/SCALARLDST 是否因 x `GetValue` 成为主导。
2. 在同一 case 上至少比较原 SIMT 与 Scalar；目标是完整算子时间，不是仅比较 index/y 搬运段。
3. 对候选路由运行完整用例集，按总体评分选择，避免只优化一个 case 后引入其他 shape 回退。
4. 不写 case ID、固定输出 MiB 阈值或单一 shape 特判。

已观测反例：某 PER_ELEMENT BF16/int32、`Gx=Gi=7`、大 inner 的 case，SIMT 为 16.99 us，Scalar 为 388.69 us；将全部 7 个 x 平面的 inner tile 搬入 UB 后为 7.10 us。这个结果只证明路径选择规则，不应把 `7` 或对应 shape 写成通用门槛。
```

Item 2 is the methodological half and deserves reading beside the number: `目标是完整算子时间，不是仅
比较 index/y 搬运段`. A Scalar-versus-SIMT comparison scoped to the transfer segments would show Scalar
winning, because that is the segment Scalar improves. The 23× only appears at whole-operator scope.
That is a measurement-scope failure of exactly the shape this project records — a measurement whose
scope does not cover the sentence's scope — and upstream states the fix before anyone makes the error.

The mechanism, `:16-27`, as a table plus its conclusion:

```
## 3. 与 SIMT 的区别（关键）

| 维度 | SIMT 路径 | Scalar 路径 |
|------|----------|------------|
| index 读取 | VEC 流水线逐元素 GM 读 | **DMA 批量搬运到 UB**（连续读，η≈1.0） |
| x 读取 | VEC 流水线逐元素 GM 随机读 | GM `GetValue` 标量随机读（SCALAR 管线） |
| y 写入 | VEC 流水线逐元素 GM 写 | **DMA 批量写回**（连续写，η≈1.0） |
| UB 使用 | 无 | index tile + y tile（不含 x，UB 需求小） |
| 固定开销 | 无 UB/DMA 启动 | 无 workspace/转置，但有 DMA 和标量循环开销 |
| 适用场景 | 大规模散点读（2048 线程并行掩盖延迟） | Transpose UB 不够时的中间路径 |

> **关键**：Scalar 只消除了 index/y 的逐元素 GM 访问，最昂贵的 x 随机 GM 读取仍然存在，而且落在 SCALAR 管线。Transpose UB 不够只能说明 Scalar"可用"，不能说明它"更快"。必须在同一构建、warmup、repeat 口径下与 SIMT A/B；若 gather 轴小且 x 平面可按 inner tile 连续装入 UB，还要加入 [small-GD tiled full-load](gather_elements_small_gd_tiled.md) 候选。
```

`必须在同一构建、warmup、repeat 口径下` — same build, same warm-up, same repeat count — is upstream
specifying the comparison discipline, and it is the discipline this book's own `§4` sections require
for the same reason.

The Scalar inner loop that produces the cost, `:29-42`:

```
Device (每核):
  对每个 preDim × postDimBlock:
    CopyInIdx: DataCopyPad(连续读 index tile from GM → UB)
    Compute:
      for each idxPos in tile:
        xGatherPos = idxLocal.GetValue(idxPos)    // 标量读 index (from UB)
        xGatherPos = (xGatherPos + xGatherDim) % xGatherDim  // 负索引补偿
        xValue = xGm[xBaseOffset + xGatherPos * xPostDim + idxPostPos].GetValue(0)  // GM 标量读 x
        yLocal.SetValue(idxPos, xValue)           // 标量写 UB
    CopyOutY: DataCopyPad(UB → GM)
```

One `GetValue` on GM per output element, plus a scalar modulo per element for negative-index
compensation, inside a scalar loop. This book records at `0017` that a per-tile fixed cost multiplied
across enough tiles becomes a scalar bound; here the multiplier is the output element count.

The same triple, restated in the sibling file with the third path named,
`templates/gather_elements_small_gd_tiled.md:87`:

```
已有观测：一个 BF16/int32、`Gx=Gi=7`、大 inner 的 PER_ELEMENT case，原 SIMT 16.99 us，Scalar 388.69 us，small-GD tiled full-load 7.10 us。该数据证明"消除 x 随机 GM 读"可能产生显著收益，不构成 `G==7` 的通用阈值。
```

Two files, one case, identical figures, and both close with the same prohibition against generalising
the shape. Two files in one repo are one origin (RULES.md Art. 3), so this is one measurement stated twice,
not two.

What the case does **not** carry: no board, no core count, no tool, no repetition count, no variance,
no `inner` value (`大 inner` only), no dtype for the output (`BF16/int32` names data and index types),
and no absolute shape. So the two ratios this entry computes — `22.9×` and `2.39×` — are ratios of
three unrepeated single figures on an unnamed part. They are strong enough to overturn a default and
too weak to found a threshold, which is precisely what upstream says about them.

The design consequence upstream draws, `:79` (the not-applicable table):

```
| dim != last + small-GD tile 可装入 UB | [small-GD tiled full-load](gather_elements_small_gd_tiled.md)，优先消除 x 随机 GM 读 |
```

`优先消除 x 随机 GM 读` — eliminate the random read first — is the transferable rule, and it is
stated as a priority over the two paths that merely relocate it.

Registered as `C-950td-015`: the family's document order (transpose → Scalar → SIMT) is the reverse of
its own measured order on the only case it publishes for these paths.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase. Upstream's
three figures are upstream's; the reproducible content is the *ranking* and the *mechanism*, and the
procedure targets both.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and discard the case
if the die moved. Variance floor first: one build, 30 in-process runs and 5 fresh-process runs, IQR over
median, beside every figure — a 23× claim does not need a tight floor, but the 2.39× one does.

**Arm 1 — reconstruct the case and rank the three paths.** Upstream gives BF16 data, int32 index,
`Gx = Gi = 7`, `dim != last`, `大 inner`. Sweep `innerSize ∈ {512, 2048, 8192, 32768}` and
`outerSize ∈ {1, 64}` to cover what `大 inner` might mean, holding `gatherDim = 7`. At each point build
SIMT (`dav310/gather_simt.template`), Scalar (`dav310/gather_elements_v2_scalar.template`) and the
small-GD pattern per `gather_elements_small_gd_tiled.md:60-73`. One compiler pin, three md5s, host echo
of the path, `Gx`, `Gi`, `innerSize`, `outerSize` and the queried UB. Elementwise comparison against a
CPU reference on all three. `aiv_time` under `msprof --aic-metrics=PipeUtilization`, ≥10 iterations,
first 5 dropped, whole-operator scope — the segment-only scope upstream warns against is explicitly not
measured, and the report says so.

**Arm 2 — attribute the Scalar cost rather than assuming it.** On the same points, collect the SCALAR
and SCALARLDST pipe shares for the Scalar arm (upstream's own check 1). The mechanism claim is that
`x`'s `GetValue` dominates; if the scalar pipe share is not high, the 23× has some other cause and
this entry's §2 explanation is wrong even if its ranking holds. This is the arm that separates the
measurement from the story.

**Arm 3 — is the ranking a property of the shape or of the paths?** Repeat arm 1 at `gatherDim ∈
{2, 7, 32, 256}` with `innerSize` fixed. Upstream forbids `7` as a threshold; this arm is what would
*find* the real boundary, if there is one — the `gatherDim` at which small-GD stops fitting UB and at
which Scalar stops losing. Reported as a curve, and explicitly **not** converted into a gate by this
entry.

**Arm 4 — the segment-scope trap, retained because it is expected to mislead.** On one point, also
measure the index-transfer and output-transfer segments alone for SIMT and Scalar. Upstream predicts
Scalar wins that comparison while losing the whole-operator one. Confirming the inversion makes
upstream's methodological warning a measured statement rather than a caution, and it is the cheapest
demonstration in this entry of why comparison scope must be declared.

Refuses to assume: that a free die stays free; that a die may be substituted; that `大 inner` means any
particular size (arm 1 sweeps it and reports the range over which the ranking holds); that `ub_size` is
a literal (queried and echoed, `0141`); that a build labelled with a path ran it; that BF16 accumulates
identically on all three paths (the elementwise comparison is against a float64 reference rounded once
to BF16, so a path that silently computes in another precision is visible).

## 5 · Checker — acceptance declared before the run
Verdict `rank(point)` = the ordering of the three paths by median `aiv_time` at that sweep point, with
the floor. Declared before the run: this entry is **supported** iff `Scalar` is slowest at every point
where all three arms built successfully. The OVERTURN fires iff `Scalar < SIMT` outside the floor at
any point — Scalar would then have a regime, and this entry's unconditional rule would need that regime
named.

Verdict `scalar_ratio(point)` = median `aiv_time`(Scalar) / median `aiv_time`(SIMT). Upstream's single
case gives 22.9. Declared now: a value anywhere in `[5, 100]` is consistent with upstream; a value below
2 means the counter-example does not reproduce at this shape and the report says so rather than
averaging it away.

Verdict `scalar_pipe_dominant` from arm 2: true iff the SCALAR + SCALARLDST share exceeds every other
pipe's share on the Scalar arm. This entry's *mechanism* is supported only if this is true; the
ranking can hold with it false, and in that case the report must separate the two.

Verdict `segment_inversion` from arm 4: true iff Scalar beats SIMT on transfer-segment time at a point
where it loses on whole-operator time.

The exit code is not the verdict: a gather with wrong indices exits 0, and the Scalar path's expected
outcome is slow-and-correct rather than a crash. Three guards. First, all three arms are compared
elementwise against a CPU reference at every point and the checker fails red if any comparison did not
execute; an arm that did not build is `did_not_build`, never a missing row in a ranking. Second, **the
input that makes this checker go red**: the sweep includes a point with `innerSize = 1` (last-axis-like,
tiny inner), where small-GD's whole premise — a large contiguous inner tile — does not apply and it
must **not** win. If small-GD is fastest everywhere including there, the harness is not building the
paths it says it is, and every ranking in the sweep is void. A three-way comparison whose only outcome
is "the newest path always wins" has not been shown able to reject it. Third, every point carries its
floor, its three md5s, its echoed path names and its whole-operator scope declaration; a point measured
at segment scope is reported in arm 4's table only and may never enter `rank`.

## 6 · Evidence
NOT YET RUN by us — no readout of ours exists. Nothing in this file is our measurement. The three
figures are upstream's, stated twice in two files of one directory (one origin), with data and index
dtypes, a plane count and a qualitative `大 inner`, and with **no** board, core count, tool, repetition
count, variance or absolute shape. What was performed here on paper at drafting time is division on
upstream's numbers: `388.69 / 16.99 = 22.88` and `16.99 / 7.10 = 2.393`. Division on a published number
is not a measurement of any machine.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured by us. The entry does not establish the 23× or the 2.39×, does not establish they
reproduce at any other shape, and does not establish the board they were taken on — none is named. It
does not establish that the SCALAR pipeline is the cause; that is §2's mechanism and §4 arm 2 is what
tests it, with §5 keeping the mechanism and the ranking as separate verdicts precisely because a
measurement and an inference must not travel in one sentence. It does not establish any threshold, and
deliberately supplies none: upstream forbids `7` and the shape twice, `0046` forbids case-derived
predicates generally, and §4 arm 3 reports a curve rather than a gate. It does not establish that
small-GD is usable — `0409` records it has no `.template` and fails its own promotion conditions. It
does not establish that Scalar is never right; the OVERTURN names exactly what would show a regime for
it. It does not extend to `PER_SLICE` gathers, where Scalar is not a candidate at all (`0147`), or to
`dim == last` (`0411`). It says nothing about the transpose paths, whose own disclosed counter-examples
are `0408`. No board token appears anywhere in the gather family on either shelf, so BOARD is
`family-claimed(unverified)`; §4 names 950PR/950DT only as where our run would happen. Nothing here is
established for any 910-family board.
