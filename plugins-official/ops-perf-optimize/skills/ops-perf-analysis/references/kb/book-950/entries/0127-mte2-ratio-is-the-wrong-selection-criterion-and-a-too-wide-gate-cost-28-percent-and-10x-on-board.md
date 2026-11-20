```
ID:        0127-mte2-ratio-is-the-wrong-selection-criterion-and-a-too-wide-gate-cost-28-percent-and-10x-on-board
LABEL:     trap
LEVEL:     L9 (performance)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/tiling/reduction/fallback/example/euclidean_norm/experience.md:144-159 —
           "初版 tail-A（RARA）gate 太宽——只校验 `slabCnt×2≥coreNum`、未卡内块每行大小——**误命中
           #13/#15 导致严重退化**" · "#15 ararara_0008 | 32B | 8 元素 | **229µs（慢 10×!）** |
           22.8µs" · "`mte2_ratio` 单指标会误导。真正决定赢面的是 **基线最内 burst 大小** ...
           **必须上板实测校准。**"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured case on a named 950 board where `mte2_ratio` alone predicts the correct
           template choice across a set spanning both regimes — the single-metric criterion would
           then be sufficient after all, and upstream's stated lesson would be over-drawn.
```

# 0127 · `mte2_ratio` is the wrong selection criterion, and a too-wide gate cost 28 % and 10× on board

## 1 · Claim
Upstream asserts that a single memory-pipe utilisation metric is a misleading basis for choosing
the interleaved reduction template, and supports the assertion with two disclosed misfires from its
own on-board measurement set. Upstream states that its first version of the tail-A gate checked
only `slabCnt × 2 ≥ coreNum` and did not constrain the inner block's per-row size, and that this
gate wrongly admitted cases #13 and #15, producing severe degradation: #13 at 320 B per row (80
elements) ran 92.6 µs under the wrongly-selected template against 75.2 µs after falling back — 28 %
slower; #15 at 32 B per row (8 elements) with `slabCnt = 18000` ran 229 µs against 22.8 µs — about
10× slower. Upstream states the root cause for both: the inner block's rows were too small for
contiguous loading to buy any MTE2 benefit, and the per-slab step-2 barrier plus the small
reduction overwhelmed it, with #15 additionally suffering barrier cost explosion from 18000 slabs.
Upstream states the fix — adding the `innerRowElems ≥ 512` threshold — and states that the
threshold `是 **上板抓出 #13/#15 退化后新增的**`. Upstream closes with `必须上板实测校准`. Not
established here; these are upstream's measurements, not ours.

## 2 · The wrong branch this removes
The wrong branch is choosing a template from the symptom. An interleaved case pushed through the
five templates shows MTE2 saturated at `ratio ≈ 0.995` (0125), which is a correct reading and
points at the memory pipe — so an agent selects the template that reduces scattered reads. The
criterion is right about the mechanism and wrong about the decision, because the interleaved
template's own fixed costs are also real and are not visible in the baseline's profile at all. #13
and #15 both had saturated MTE2 and both got slower. An agent using the metric as the gate makes
exactly upstream's first-version mistake, and the 10× case shows the size of the downside.

The general form is worth stating because it recurs: a metric that identifies a bottleneck does not
identify the remedy's cost. The remedy's cost lives in the *candidate* plan and can only be
predicted from the candidate's structure — here, the number of slabs and the size of each row —
which is why the fixed gate is expressed in `innerRowElems` and `slabCnt`, quantities of the plan,
not in `mte2_ratio`, a quantity of the baseline.

A third wrong branch this removes: assuming a gate that was derived from a mechanism is safe. The
mechanism argument for tail-A is sound and upstream believed it enough to ship a gate that only
checked parallelism. It took a board to find the 10×. `必须上板实测校准` is upstream's own
conclusion and it is carried here as a claim rather than as advice.

## 3 · Ground / Source
`reduction/fallback/example/euclidean_norm/experience.md:144-159`, §6 in full:

```
## 6. gate 误判教训（#13 / #15，仅上板才能发现）

初版 tail-A（RARA）gate 太宽——只校验 `slabCnt×2≥coreNum`、未卡内块每行大小——**误命中 #13/#15 导致严重退化**：

| case | 内块/行 | innerRowElems | 误命中 RARA | 回退后 | 根因 |
|------|--------:|-------------:|-----------:|------:|------|
| #13 ararara_0006 | 320B | 80 元素 | 92.6µs（慢 **28%**） | 75.2µs | 内块每行太小，连续载入无 MTE2 收益，反被每 slab 的 step2 屏障+小规约拖垮 |
| #15 ararara_0008 | 32B | 8 元素 | **229µs（慢 10×!）** | 22.8µs | 同上，且 slabCnt=18000 → 屏障开销爆炸 |

**修复**：tail-A gate 增加 `innerRowElems ≥ 512`（2KB/行）阈值 → #13/#15 干净回退，#11/#12 保留（`euclidean_norm_tiling_host.h` 的 opt2 版本尚未加此阈值，合并 demo 已补）。

**另一类回退（#17）**：8 轴 tail-R 但内块最内 R=16 → burst 64B（中等），且内块需分块（chunkA0=14<A0=32）。fast 的分块屏障+逐平面规约吃掉 MTE2 增益，实测 **-9%** → `chunkA0==A0`（及 `R1×dtypeSize≤16B`）不满足，回退 normal。

**核心判据（务必牢记）**：

> `mte2_ratio` 单指标会误导。真正决定赢面的是 **基线最内 burst 大小**（tail-R：内块最内 R 长度；≤~16B 病态才大赢）或 **内块每行大小**（tail-A：innerRowElems ≥ 512 才值得）。中等 burst（64B）或小内块（≤320B）反被模板固定开销反超。**必须上板实测校准阈值。**
```

Restated in the flow document, `reduction/fallback/tiling-flow.md:531-542`, with the same three
counter-cases in a compact table:

```
**反例（必须回退五模板）**：

| case | 症状 | 现象 | gate 动作 |
|------|------|------|----------|
| #17 arararar_0001 | 内块最内 R=16 → burst **64B**（中等），内块需分块 chunkA0=14<32 | fast 分块屏障+逐平面规约吃掉增益，实测 **-9%** | `R1×dtypeSize≤16` / `chunkA0==A0` 不满足 → 回退 normal |
| #13 ararara_0006 | innerRowElems=80（**320B**/行） | 误命中 RARA 慢 **28%**（92.6 vs 75.2µs） | `innerRowElems ≥ 512` 不满足 → 回退 group |
| #15 ararara_0008 | innerRowElems=8（**32B**/行），slabCnt=18000 | 误命中 RARA 慢 **10×**（229 vs 22.8µs），大量 slab 的 step2 屏障+小规约开销拖垮 | 同上 → 回退 normal |

**教训**：
1. 中等 burst（64B）或小内块（≤320B）时，模板的固定开销（分块屏障、逐平面规约、每 slab 的 step2 屏障+小规约）反被基线反超。
2. `innerRowElems ≥ 512` 阈值是 **上板抓出 #13/#15 退化后新增的**（初版 RARA gate 太宽，只判 slabCnt，误命中）。
3. 交错模板是"精准打击"型优化：20 case 里仅 #11/#12 /#18 真正获益，其余 17 个必须干净回退，零退化。**任一门控不满足即 `return false` 落回五模板/group，回退安全。**
```

Re-derived from upstream's own numbers: #13, `92.6 / 75.2 = 1.231`, i.e. 23 % slower on the
misfire, or 19 % faster after fallback — upstream states 28 %, which matches
`(92.6 − 75.2) / 62`? No: none of the natural framings gives 28 %. `92.6 / 72.9 = 1.270` against
the *baseline* (72.9 µs, from the 20-case table row #13) gives 27 %, which is where the 28 % most
likely comes from — the misfire is 27–28 % slower than the untouched baseline, not than the
fallback. The two documents place the comparison differently, and this book records the ambiguity
rather than choosing: the fallback number in §6's table (75.2 µs) is the `merged` column of row
#13, and the baseline (72.9 µs) is that row's `baseline`. #15: `229 / 22.8 = 10.04`, matching the
stated 10×; here the comparison is against 22.8 µs, which is row #15's `merged` value while its
`baseline` is 24.4 µs — so #15's factor is stated against the fallback and #13's against the
baseline. Registered as C-950tiling-010: the two disclosed misfires are quoted against different
denominators inside the same document.

The disclosure's own scope limit, at `:153`, is preserved because it is a live caveat and not
history: `（euclidean_norm_tiling_host.h 的 opt2 版本尚未加此阈值，合并 demo 已补）` — the fix is in
the merged demo, and at least one shipped host tiling version does not carry it. An agent consuming
that version reproduces the 10×.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s
spacing; bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and
discard the case if the die moved.

Reproduce both misfires deliberately — this is the arm that matters, and it is a poison arm by
construction. Build #13 (`innerRowElems = 80`) and #15 (`innerRowElems = 8`, `slabCnt = 18000`)
three ways each: (a) with the current gate, which must fall back; (b) with the gate forced open so
the tail-A template is used, reproducing the misfire; (c) the plain baseline from the 20-case
table. One compiler pin, md5 each binary, host echo of `raraSlabCnt`, `raraChunkR0`,
`innerRowElems` and the selected template. Check all three against an fp64 reference within a
tolerance declared in advance. Record `aiv_time`, `mte2_ratio`, achieved bandwidth and the
per-slab barrier count under `msprof --aic-metrics=PipeUtilization`, ≥10 iterations, first 5
dropped, per case, alongside the variance floor from 0126's arm 0.

The point of arm (b) is that a gate whose violation is never measured is a gate on faith. If the
forced-open arm does *not* reproduce the degradation on this board, the threshold does not transfer
and this entry is corrected in place.

Second arm — the criterion comparison, which is the entry's actual claim. Across all cases in
0126's ladders plus these two, record `mte2_ratio` of the baseline and the eventual best template.
Then ask whether any single threshold on `mte2_ratio` separates the cases where the interleaved
template wins from those where it loses. This is a classification question answered on recorded
data, not a new run.

Refuses to assume: that a free die stays free; that a die may be substituted; that `coreNum` is 72
(queried — `slabCnt × 2 ≥ coreNum` moves with it, and #15's misfire depended on the gate passing);
that `UB` is 192 KB (queried — 0131); that the degradation reproduces (arm (b) tests it); that
28 % and 10× share a denominator — both denominators are computed and reported.

## 5 · Checker — acceptance declared before the run
Verdict variable `misfire_reproduced`, per case: true iff arm (b)'s median `aiv_time` exceeds arm
(a)'s by more than the variance floor, with the ratio reported. Declared before the run: upstream's
disclosure is confirmed iff `misfire_reproduced` is true for both cases and #15's ratio exceeds 5×.
Verdict variable `mte2_separates`: true iff some threshold on baseline `mte2_ratio` classifies all
recorded cases correctly into win/lose. Declared acceptance for this entry's claim: it survives iff
`mte2_separates` is false. The OVERTURN fires iff `mte2_separates` is true — the single metric would
then be sufficient and upstream's lesson over-drawn.

The exit code is not the verdict. Two guards, both aimed at the way this particular experiment
could confirm itself falsely. First, arm (b) must be shown to have actually used the interleaved
template: a forced-open gate that the host overrode would produce arm (b) ≡ arm (a), giving
`misfire_reproduced = false` from an experiment that never misfired. The echo of the selected
template and a non-zero `raraSlabCnt` is required, and the checker goes red where absent. Second,
`mte2_separates` is computed over the *whole* recorded set including the cases where the template
wins; computing it only over the misfires would trivially succeed. The checker fails if the
classification set contains fewer than four winning cases and four losing cases.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The 92.6 / 75.2 / 229 /
22.8 µs figures, the 28 % and 10× factors and the −9 % for #17 are upstream's on-board readouts on
upstream's platform; this book has reproduced none of them.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured by us. The entry does not establish that `innerRowElems ≥ 512` is the correct
threshold — it establishes that upstream added it after two on-board regressions and states it as
calibrated. It does not resolve the denominator ambiguity in the 28 % figure (C-950tiling-010). It
does not establish that `mte2_ratio` is useless — upstream says it misleads as a *single* selection
criterion, which is a narrower claim, and this entry keeps it narrow. It does not establish that
the degradation reproduces on any board other than upstream's, nor for any operator other than
EuclideanNorm, nor at any core count other than 72. It does not establish which shipped host
tiling versions carry the fix; upstream discloses that at least one does not. `Ascend 950 / arch35
(dav-3510)` names a family, not a board, so BOARD is `family-claimed(unverified)`; §4 names
950PR/950DT because that is where our run would happen. Nothing here is established for any
910-family board.
