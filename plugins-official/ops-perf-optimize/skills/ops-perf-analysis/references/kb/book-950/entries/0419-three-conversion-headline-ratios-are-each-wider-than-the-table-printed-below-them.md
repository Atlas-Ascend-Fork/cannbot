```
ID:        0419-three-conversion-headline-ratios-are-each-wider-than-the-table-printed-below-them
LABEL:     trap
LEVEL:     L9 (performance)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured by us
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/conversion/transpose_small_shape.md:192 —
           "实测可导致 SIMT 分支比基线 DataCopyPad 慢 3-10 倍。" ; :288-293 — the table whose
           worst geomean is "0.17x（严重退化）"
SOURCE:    same shelf, conversion/transpose_n_last.md:267 — "N_LAST 未合并时比基线慢 2-5 倍，根因就是
           CopyOut 的 strided 写。" ; :262-263 — "| 基线 DataCopyPad | 4D 连续写出 | 19.4 | 24.6 |" ·
           "| N_LAST（未合并） | 6 维 strided 写 | 58.9 | 124.1 |"
SOURCE:    same shelf, conversion/transpose_small_shape.md:196 — "每线程读/写 1 个元素（float16=2B），
           带宽利用率仅 `2/32 = 6.25%`。" ; :199-202 — the per-dtype table giving int8 3.1%,
           float16/bfloat16 6.25%, float32/int32 12.5%
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a `batch_to_space`-class transpose on a named 950 board at which the unmerged N_LAST path is
           10× slower than a `DataCopyPad` baseline, or at which a `float32` SIMT element-wise path
           achieves 6.25% of bandwidth. Either would show a headline figure is supported by cases
           outside the published tables, and this entry's claim that the summaries over-reach their
           own evidence would be wrong for that figure.
```

# 0419 · Three conversion headline ratios are each wider than the table printed below them

## 1 · Claim
Upstream asserts three summary figures in its conversion family, and prints, in the same two files, the
tables from which each is drawn. The summaries are wider than the tables in three different directions.
Upstream asserts a SIMT element-wise path is `慢 3-10 倍` than a `DataCopyPad` baseline; its table's
worst measured geomean is `0.17x`, a factor of 5.9, and nothing in it reaches 10. Upstream asserts an
unmerged N_LAST path is `慢 2-5 倍`; its table's two measured pairs give 3.04× and 5.04×, so the upper
end is right and the lower end corresponds to no measured case. Upstream asserts a bandwidth
utilisation of `6.25%`, derived explicitly as `2/32` for a 2-byte element, and its own per-dtype table
gives 3.1% for int8 and 12.5% for float32 — so the single figure is one row of three, restated
without its dtype in three other places. Not established here.

## 2 · The wrong branch this removes
A ratio in a warning box is what gets carried into the next document, and all three of these have
already travelled: `6.25%` is restated without its dtype at `guide.md:35`, `guide.md:61` and
`transpose_small_shape.md:297`, and this book's own `0164` carries it flat from the analysis shelf. An
agent budgeting a `float32` transpose against 6.25% has under-estimated the element-wise path's
bandwidth by exactly 2×, and will reject a path that was viable. An agent quoting `10×` for the SIMT
penalty is quoting a number no measurement in the family produced.

The second wrong branch is over-correcting into distrust. The tables are good — better than most in
this repository. They name the operator, the `perm`, the rank and the board; the per-dtype derivation
is arithmetic anyone can check (`1/32`, `2/32`, `4/32`); and the N_LAST table's own upper bound is
exactly right. The defect is not fabrication, it is **rounding outward in the direction that makes the
warning louder**, and the repair is mechanical: when a summary and a table disagree, the table is the
measurement and the summary is the author's gloss. That rule is what this entry actually carries.

## 3 · Ground / Source
**Instance 1 — the SIMT penalty.** The summary, `conversion/transpose_small_shape.md:192`:

```
> ⚠️ **实战经验**：SIMT 逐元素读写是 SMALL_SHAPE 策略的性能关键。原始模板的 `outputGM[idx] = inputGM[xIdx]` 每线程处理 1 个元素，在以下两个维度存在严重带宽浪费，实测可导致 SIMT 分支比基线 DataCopyPad 慢 3-10 倍。
```

The table, `:286-295`:

```
以 batch_to_space 算子（perm=[2,3,0,4,1,5]，6D）为例，在 ascend950 上的实测：

| 优化阶段 | SIMT scalar_time | SIMT vec_time | SIMT geomean vs 基线 |
|---------|-----------------|--------------|---------------------|
| 原始(逐元素) | ~10us* | 2.4-29.3us | 0.17x（严重退化） |
| +TilingData GM 直访 | ~4us | 同上 | 0.27x |
| +host 预算 magic/shift | 0.02-3.6us | 同上 | 0.32x |
| +向量化读写(C tile) | 同上 | 预期降低 C 倍 | 待验证 |

> *scalar_time ~10us 原始值来自 kernel 入口逐字节拷贝 TilingData（972 字节），修正后降至 ~4us；再经 host 预算 magic/shift 降至 0.02-3.6us。但 vec_time（VF 内 GM 读写）始终是大头，只有向量化读写才能解决。
```

Inverted here: `1 / 0.17 = 5.88`, `1 / 0.27 = 3.70`, `1 / 0.32 = 3.13`. The measured range is
**3.1×–5.9×**, and the summary's `3-10 倍` gets the lower end right and overshoots the upper end by
1.7×. The fourth row is the recommended fix and is marked `待验证` — unverified — so the family's
prescribed repair has no measurement at all, which the summary does not mention.

**Instance 2 — the N_LAST regression.** The table, `conversion/transpose_n_last.md:258-265`:

```
以 batch_to_space 算子（perm=[2,3,0,4,1,5]，6D）为例，在 ascend950 上：

| 实现 | CopyOut 方式 | case2 aiv(us) | case12 aiv(us) |
|------|------------|--------------|---------------|
| 基线 DataCopyPad | 4D 连续写出 | 19.4 | 24.6 |
| N_LAST（未合并） | 6 维 strided 写 | 58.9 | 124.1 |
| N_LAST（合并后预期） | 3 维连续写 | ~19 | ~25 |
| TQueBind 4D | 4D 连续写出 | 13.1 | 15.4 |
```

and the summary immediately below, `:267`:

```
> N_LAST 未合并时比基线慢 2-5 倍，根因就是 CopyOut 的 strided 写。合并后预期与基线持平，因为 CopyOut 变为连续写出。TQueBind 更快是因为它在 4D 空间操作，天然利用了输出连续性，且 TilingData 更小（128B vs 972B）。
```

Re-derived: `58.9 / 19.4 = 3.04`; `124.1 / 24.6 = 5.04`. Measured range **3.0×–5.0×** against a
summary of `2-5 倍`. Here the direction of the over-reach is reversed — the upper bound is right and
the *lower* bound is too low — which is what makes this a systematic rounding-outward pattern rather
than a single slip. Row three is `合并后预期`, a projection, and row four is `0420`'s subject.

**Instance 3 — the bandwidth figure.** The derivation, `conversion/transpose_small_shape.md:196`:

```
GM burst 要求 32B 对齐。每线程读/写 1 个元素（float16=2B），带宽利用率仅 `2/32 = 6.25%`。2048 个线程各读 2B = 4KB 总量，但每次 GM 访问只有 2B 有效数据。
```

and the table three lines later, `:198-202`:

```
| dtype | 单元素字节 | 每线程带宽利用率 |
|-------|----------|---------------|
| int8 | 1B | 3.1% |
| float16/bfloat16 | 2B | 6.25% |
| float32/int32 | 4B | 12.5% |
```

`1/32 = 3.125%`, `2/32 = 6.25%`, `4/32 = 12.5%` — all three check, and the derivation is stated, which
makes this the best-founded number in the family. Its restatements drop the qualifier:
`guide.md:35` (`原始模板逐元素读写带宽利用率仅 6.25%`), `guide.md:61`, and
`transpose_small_shape.md:297` (`否则带宽利用率仅 6.25%，不如基线的批量 DataCopyPad`). Three
restatements, zero dtypes. This book's `0164` §1 carries the figure in the same flat form from the
analysis shelf, so the narrowing has already propagated one hop further than upstream; that is a scope
correction owed to `0164` and is recorded in `harvest/standing/950-td.md` as `Q-950td-08` rather than
edited into that entry (write partition).

Registered together as `C-950td-024`: in one family, three summary figures each state a range wider
than, or a scope narrower than, the table printed beside them.

What none of the three tables carries, and this matters for how far any of them travels: **no
profiling tool is named anywhere in the twelve-file family**, no repetition count is given, no
variance is given, and `case2` / `case12` are never defined — no shapes, no dtype. The board *is*
named (`ascend950`), which is more than most of this repository manages, though the family's own
architecture marker elsewhere is `dav-3510` / `arch35` and the two are never reconciled (`0421`).
`ascend950` is not a board token this project recognises (CONVENTIONS lists `950PR` and `950DT`), so
BOARD stays `family-claimed(unverified)`.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase. Upstream's
tables are upstream's; what is reproducible is whether the summaries' extra range exists outside them.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and discard the case
if the die moved. Variance floor first: one build, 30 in-process runs, 5 fresh-process runs, IQR over
median, beside every figure — upstream reports none, and a 3.04-versus-2.0 distinction needs one.

**Arm 1 — the bandwidth figure across dtypes, which needs the least and settles the most.** Build the
SIMT element-wise transpose at `int8`, `float16` and `float32`, same shape, and record achieved GM
bandwidth against the device's peak. Upstream's table predicts 3.1 % / 6.25 % / 12.5 %. If the measured
ratios track element width, the per-dtype table is right and the flat `6.25%` restatements are the
defect; if they do not, the whole model (`sizeof(T) / 32`) is wrong and both forms are.

**Arm 2 — the SIMT penalty range.** Reconstruct the four optimisation stages of `:288-293` — original
element-wise, TilingData direct access, host-precomputed magic/shift, and the vectorised C-tile the
table leaves `待验证` — and measure each against a `DataCopyPad` baseline on a spread of shapes wider
than one operator: `perm` patterns of rank 4, 5 and 6, two dtypes, three sizes straddling the
`4000000`-byte SMALL_SHAPE threshold. Report the geomean per stage and the **maximum** penalty observed.
The question is whether any shape reaches 10×.

**Arm 3 — the N_LAST regression range.** Same shape spread, building the baseline `DataCopyPad` path
and the unmerged N_LAST path. Report the minimum and maximum ratio. The question is whether any shape
is as low as 2×.

**Arm 4 — the unverified fix.** The vectorised C-tile row is the family's prescribed repair and is
marked `待验证`. Build it and measure. Upstream projects `降低 C 倍`; the post-vectorisation utilisation
table (`:269-273`) projects 25 % at `C=4`, 50 % at `C=8`, 100 % at `C=16`. Sweep `C ∈ {1, 4, 8, 16, 32}`
and report measured utilisation against those projections. `C=1` must show no change — upstream says so
(`C=1 时退化为逐元素（无收益但无害）`) — and is the control.

Refuses to assume: that a free die stays free; that a die may be substituted; that `case2` / `case12`
are recoverable (they are not defined upstream, so §4 uses its own shape spread and says so rather than
claiming to reproduce upstream's cases); that `ascend950` is this board; that the four optimisation
stages are separable (each is built and md5'd separately, and a stage that cannot be isolated is
reported as such); that a geomean over one operator generalises (arm 2's spread exists for that reason).

## 5 · Checker — acceptance declared before the run
Verdict `bw_ratio(dtype)` = measured GM bandwidth utilisation, arm 1. Declared before the run: the
per-dtype table is **supported** iff `bw_ratio` tracks `sizeof(T)/32` within the variance floor at all
three dtypes, and the flat restatements are then wrong for two dtypes out of three.

Verdict `simt_penalty_max` = the largest penalty over arm 2's spread. Declared before the run: this
entry is **supported** for instance 1 iff `simt_penalty_max < 10 − floor`. The OVERTURN fires for that
instance iff `simt_penalty_max ≥ 10`: a case outside the published table would then justify the
summary, and the entry is corrected in place to say the table was not the summary's only evidence.

Verdict `nlast_penalty_min` = the smallest ratio over arm 3's spread. Declared before the run: this
entry is **supported** for instance 2 iff `nlast_penalty_min > 2 + floor`. The mirror OVERTURN applies.

Verdict `vectorised_gain(C)` from arm 4, reported against upstream's projected 25/50/100 %.

The exit code is not the verdict — every transpose returns a full buffer, and a wrong `perm` produces a
fast wrong answer. Three guards. First, every arm is compared elementwise against a CPU reference at
every point, and a point whose comparison did not execute is `untestable`. Second, **the input that
makes this checker go red**: arm 4 includes `C = 1`, where upstream states there is no gain, and arm 1
includes a contiguous copy (identity `perm`), where the element-wise path should reach near-peak
bandwidth rather than `sizeof(T)/32`. If `C = 1` shows a gain, or if the identity copy also reads
6.25 %, the harness is not measuring what it claims and every ratio in the study is void — a
ratio-checking study whose only outcome is "the published numbers were wrong" cannot distinguish a
real over-reach from a mis-built baseline. Third, no ratio is reported without its variance floor, its
build md5, its dtype and its shape — the three defects this entry documents are all defects of
*dropped qualifiers*, and a report that drops them reproduces them.

## 6 · Evidence
NOT YET RUN by us — no readout of ours exists. Nothing in this file is our measurement. The three
tables are upstream's, on `ascend950`, for one operator and one `perm`, with no tool, no repetition
count, no variance and undefined case labels. What was performed here on paper at drafting time is
arithmetic on upstream's own published numbers: `1/0.17 = 5.88`, `1/0.27 = 3.70`, `1/0.32 = 3.13`,
`58.9/19.4 = 3.04`, `124.1/24.6 = 5.04`, `1/32 = 3.125%`, `4/32 = 12.5%`. Every one agrees with the
table it came from; the disagreements are between those tables and the sentences beside them.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured by us. The entry does not establish that any of the three summaries is *false* —
a range can be right for cases a table does not show, and §5 declares exactly what would demonstrate
that. It establishes only that each summary is unsupported by the evidence printed with it, and it
does not assert what the correct ranges are. It does not establish upstream's timings, the `ascend950`
attribution, or that `case2` and `case12` are distinct shapes rather than labels. It does not establish
the `sizeof(T)/32` bandwidth model, which is arithmetic on a stated 32-byte burst rather than a
measurement — the 32 B GM granularity is on this project's own establish-from-scratch list and is not
established here. It does not correct `0164`, which carries the flat `6.25%` from a different shelf;
that scope correction is owed and recorded as `Q-950td-08`, not applied (write partition). It does not
cover the fourth table row's projections (`合并后预期`, `预期降低 C 倍`), which are not measurements at
all and are labelled as such upstream. It says nothing about the other seven strategies in this family,
none of which carries any measured figure. `ascend950` names a family, not a board token this project
recognises, and the family's own architecture markers are inconsistent (`0421`); BOARD is therefore
`family-claimed(unverified)` and §4 names 950PR/950DT only as where our run would happen. Nothing here
is established for any 910-family board.
