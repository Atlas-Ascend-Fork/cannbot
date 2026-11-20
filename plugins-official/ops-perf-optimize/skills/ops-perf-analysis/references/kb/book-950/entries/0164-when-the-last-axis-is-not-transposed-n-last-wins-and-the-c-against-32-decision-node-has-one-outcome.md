```
ID:        0164-when-the-last-axis-is-not-transposed-n-last-wins-and-the-c-against-32-decision-node-has-one-outcome
LABEL:     trap
LEVEL:     L3 (data movement & layout)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/tiling/conversion/index.md:95-102,119,127,129 —
           "Step 4: 末轴长度 C 是否 ≥ 32？ ├─ C ≥ 32: → N_LAST ★ 推荐 └─ C < 32: → N_LAST ★ 推荐
           (配合维度合并)" · "N_LAST 的批量 DataCopyPad 搬运效率始终优于 SIMT 的逐元素 GM→GM 搬运" ·
           "原始模板的 `MOVEALIGN_LAST_MIN_ELE=32` 阈值将 C<32 的 case 分到 BIG_DIM，但 BIG_DIM 的
           NDDMA 多维 stride 搬运在 conversion 算子中比 N_LAST 更慢" · "未做维度合并的 N_LAST ...
           比基线慢 2-5 倍"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured conversion case on a named 950 board with `C < 32` where BIG_DIM beats N_LAST
           with dimension merging — the `MOVEALIGN_LAST_MIN_ELE = 32` threshold the tree overrides
           would then be right, and the override wrong.
```

# 0164 · When the last axis is not transposed, N_LAST wins, and the `C ≥ 32` decision node has one outcome

## 1 · Claim
Upstream asserts that when the last axis does not participate in the transpose
(`perm[permSize-1] == permSize-1`) and at least two output dimension groups are mergeable, the plan is
N_LAST regardless of the trailing axis length: the tree asks `末轴长度 C 是否 ≥ 32？` and both arms
answer `N_LAST ★ 推荐`, the second qualified as `配合维度合并`. Upstream states why the node exists
despite having one outcome — the original template's `MOVEALIGN_LAST_MIN_ELE = 32` threshold routed
`C < 32` cases to BIG_DIM, and BIG_DIM's multi-dimensional NDDMA strided movement is slower than
N_LAST on conversion-class operators whose `perm` carries a large-stride batch dimension, while
N_LAST with dimension merging turns `CopyOut` into a contiguous write that does not depend on `C`.
Upstream asserts as a general principle that N_LAST's batched `DataCopyPad` always beats SIMT's
element-wise GM→GM movement whenever the last axis is untransposed, and asserts that dimension
merging is a necessary enhancement rather than an optimisation — without it, N_LAST on a
high-dimensional `perm` such as a 6-D `batch_to_space` degrades `CopyOut` into repeated small strided
transfers, measured 2–5× slower than baseline. Not established here.

## 2 · The wrong branch this removes
The decision node is the trap and the teaching at once. Read as a decision, it decides nothing: both
arms produce N_LAST, so an agent implementing the tree literally will write a branch whose two sides
are identical, and an agent tidying the tree will delete the node — losing the information that the
node carries. What it actually encodes is a *correction*: the reader is expected to arrive already
knowing the `MOVEALIGN_LAST_MIN_ELE = 32` rule from the original template, and the node exists to say
"that threshold applied here would be wrong". Delete the node and the next reader reinstates the
threshold.

That is a general shape worth naming: a decision node whose arms agree is not always a defect, but it
is always ambiguous, because nothing distinguishes "we corrected a rule here" from "we forgot to
finish this". Upstream's version is the good case — the reason is in the prose two sections down — and
it is still one refactor away from being lost, because the reason lives in a numbered principle and
the node lives in a code block.

The dimension-merging claim removes a harder wrong branch. `N_LAST` is a strategy name, and an agent
that selects it has selected only half of what it needs: without merging, upstream measures the same
strategy 2–5× *slower* than baseline on a 6-D `perm`. So "route to N_LAST" and "route to N_LAST with
merging" are different plans with opposite outcomes, and the tree's arms name the first while the
principles require the second.

## 3 · Ground / Source
The node, `conversion/index.md:88-102`:

```
  └─ perm[permSize-1] == permSize-1 (末轴不转置) ★ 最常见
      │
      Step 3: N_LAST 维度合并可行性检查
      │  检查 inv_perm 连续性: output 中有多少相邻维度可合并？
      │
      ├─ 可合并维度组数 ≥ 2 (有连续块可利用)
      │   │
      │   Step 4: 末轴长度 C 是否 ≥ 32？
      │   ├─ C ≥ 32: → N_LAST ★ 推荐
      │   │   (末轴连续 burst 长, CopyIn/CopyOut 高效)
      │   │
      │   └─ C < 32: → N_LAST ★ 推荐 (配合维度合并)
      │       (原始模板阈值 MOVEALIGN_LAST_MIN_ELE=32 会将 C<32 分到 BIG_DIM,
      │        但 BIG_DIM 的 NDDMA 大 stride 搬运在 conversion 算子中更慢。
      │        N_LAST + 维度合并后, CopyOut 变连续写出, 不依赖 C 长度)
```

The fall-through when nothing is mergeable, `:104-114`:

```
      └─ 可合并维度组数 = 0 (perm 完全打散, 无连续维度)
          │
          Step 5: 数据量是否极小？
          ├─ 总字节 < ~10KB 且 C ≥ 16 (向量化可打满带宽):
          │   → SMALL_SHAPE ★ 仅此场景推荐 SIMT
          │   (数据量极小时 UB 流水固定开销 > 搬运时间,
          │    SIMT 的 GM→GM 直通 + 向量化读写可覆盖 asc_vf_call 派发开销)
          │
          └─ 否则: → N_LAST 或 CUT_ONCE
              (即使无连续维度可合并, N_LAST 的批量 DataCopyPad
               仍比 SIMT 逐元素搬运更高效)
```

Note that the final arm is also under-determined: `N_LAST 或 CUT_ONCE` with no rule to choose between
them. So the untransposed-last-axis subtree has one node whose arms agree and one leaf that names two
strategies without a discriminator. Registered together as C-950tiling-032.

The four principles that carry the reasons, `:119-129`:

```
1. **N_LAST 优先于 SIMT**:当末轴不转置时(`perm[permSize-1] == permSize-1`),N_LAST 的批量 DataCopyPad 搬运效率始终优于 SIMT 的逐元素 GM→GM 搬运。原始模板的"总字节数 < 4MB → SIMT"阈值在实践中过于激进——4MB 的数据用批量搬运只需几 us,但 SIMT 的 asc_vf_call 派发开销(~4us)+ 逐元素读写带宽利用率(6.25%)使其慢 3-10 倍。

2. **SIMT 仅在极小数据量 + 无连续维度时使用**:SIMT 的 GM→GM 直通只在以下条件同时满足时才有优势:
   - 数据量极小(< ~10KB),UB 流水固定开销 > 实际搬运时间
   - C ≥ 16,向量化读写可打满 GM 带宽(带宽利用率 ≥ 50%)
   - perm 无连续维度可合并,N_LAST 退化为 strided 搬运
   - **必须实现向量化读写**(每线程处理 C 个连续元素),否则带宽利用率仅 6.25%

3. **C < 32 不应触发 BIG_DIM**:原始模板的 `MOVEALIGN_LAST_MIN_ELE=32` 阈值将 C<32 的 case 分到 BIG_DIM,但 BIG_DIM 的 NDDMA 多维 stride 搬运在 conversion 算子中(perm 含大 stride 的 bs 维度)比 N_LAST 更慢。N_LAST + 维度合并后,CopyOut 变为连续写出,不依赖 C 长度。

4. **维度合并是 N_LAST 的必要增强**:未做维度合并的 N_LAST 在高维 perm(如 6D batch_to_space)中 CopyOut 退化为多次 strided 小搬运,比基线慢 2-5 倍。维度合并后 N_LAST 的 CopyOut 变为连续写出,性能等价于直接 4D 搬运。
```

Four numbers appear here, all without a case identity, a board, a tool or a repetition count:
`~4us` dispatch, `6.25%` bandwidth utilisation, `3-10 倍` SIMT penalty, `2-5 倍` unmerged-N_LAST
penalty. The 6.25 % figure is exact enough to be structural rather than measured — it is 2/32, which
is what a 2-byte element occupying one lane of a 32-byte access unit would achieve — and upstream
presents it as a property of element-wise GM→GM movement without stating the element width it assumes.
Recorded as a reading, not a fact.

Principle 2's four conditions are worth separating: three are shape/size predicates and the fourth
(`必须实现向量化读写`) is an implementation obligation on the kernel, not a tiling condition. A tiling
plan that selects SMALL_SHAPE without the kernel implementing vectorised access gets the 6.25 % case
it was trying to avoid. Upstream states this as a bolded requirement inside a selection principle,
where a tiling-side reader may not act on it.

`~10KB` and `C ≥ 16` in Step 5 are a conjunction, so a 5 KB case with `C = 8` falls to the
`否则` arm — `N_LAST 或 CUT_ONCE` — and is again undiscriminated.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and discard the
case if the die moved. Variance floor first: one build, 30 in-process runs and 5 fresh-process runs.

Arm 1 — the overridden threshold, which is the entry's falsifiable core. Take a `batch_to_space`-shaped
case with an untransposed last axis, mergeable output dimensions and a `perm` containing a large-stride
batch dimension. Sweep `C ∈ {4, 8, 16, 24, 31, 32, 48, 128}` across the `MOVEALIGN_LAST_MIN_ELE = 32`
boundary. At each `C` build both BIG_DIM and N_LAST-with-merging, one compiler pin, md5 each, host
echo of the selected strategy and its parameters. Compare output elementwise against a CPU reference on
both arms — a transpose with a wrong address map is the likely failure. Record `aiv_time`, achieved
GB/s and `CopyOut` descriptor count under `msprof --aic-metrics=PipeUtilization`, ≥10 iterations,
first 5 dropped.

Arm 2 — dimension merging as a necessity. On a 6-D `batch_to_space`, build N_LAST with merging and
N_LAST without, and record both times plus the `CopyOut` descriptor counts. Upstream predicts the
unmerged arm is 2–5× slower than baseline; a third arm running the baseline gives that comparison
directly rather than by inference.

Arm 3 — the undiscriminated leaf. On a case reaching `N_LAST 或 CUT_ONCE` (no mergeable dimensions,
not tiny), build both and record which wins, across four such shapes. The deliverable is the missing
discriminator, reported as a new observation rather than as a check against upstream.

Arm 4 — SIMT's two regimes. On a sub-10 KB case with `C ≥ 16`, build SMALL_SHAPE with vectorised
access and with element-wise access, and record achieved bandwidth for each against the 6.25 % and
≥50 % figures principle 2 states.

Refuses to assume: that a free die stays free; that a die may be substituted; that
`MOVEALIGN_LAST_MIN_ELE = 32` is what any current template implements — upstream describes it as the
original template's constant and this book has not inspected that template; that the 6.25 % figure is
dtype-independent (arm 4 records the element width used); that a selected strategy was the one that
ran (host echo required).

## 5 · Checker — acceptance declared before the run
Verdict variable `bigdim_beats_nlast(C)`: true iff BIG_DIM's median `aiv_time` is below N_LAST's by
more than the variance floor at that `C`. Declared before the run: the override is justified iff
`bigdim_beats_nlast` is false at every `C < 32`. The OVERTURN fires iff it is true at any `C < 32` —
the original threshold would then be right for that regime.

Verdict `merge_necessity` = unmerged N_LAST median / baseline median from arm 2, compared against
2–5×. Verdict `leaf_winner` per shape from arm 3, reported as a table with no expected value. Verdict
`simt_bw_vectorised` and `simt_bw_elementwise` from arm 4, compared against ≥50 % and 6.25 %.

The exit code is not the verdict: a transpose producing a correctly-shaped but wrongly-permuted output
exits 0. The elementwise comparison runs on every arm — and specifically compares against a
permutation-aware reference, not a checksum, since a permuted output has the same element multiset as
a correct one and would pass any order-insensitive check. That is the guard that keeps this checker
from being blind: an order-insensitive comparison would score every wrong permutation as correct, and
permutation is the entire operation. Second guard: strategy identity via host echo at every point.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The 3–10×, 2–5×, 6.25 %,
≥50 %, ~4 µs and ~10 KB figures are upstream's, none carrying a case identity, board, tool or
repetition count.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured. The entry does not establish that BIG_DIM is slower than N_LAST below `C = 32`,
that dimension merging is necessary, or that SIMT reaches only 6.25 % without vectorised access. It
does not establish the `MOVEALIGN_LAST_MIN_ELE = 32` constant, which upstream attributes to a template
outside this tree. It does not supply a discriminator for the `N_LAST 或 CUT_ONCE` leaf or for the
sub-10 KB fall-through (C-950tiling-032) — §4 arm 3 would produce one and has not been run. It does
not establish that the 6.25 % figure is a bandwidth-utilisation measurement rather than a structural
ratio; §3 records both readings. It does not cover the transposed-last-axis subtree (0165) or the
small-channel TilingData derivation in `fallback/`. No board is named anywhere in this family; the one
architecture word is `dav-3510` as a GATHER precondition, so BOARD is `family-claimed(unverified)`;
§4 names 950PR/950DT because that is where our run would happen. Nothing here is established for any
910-family board.
