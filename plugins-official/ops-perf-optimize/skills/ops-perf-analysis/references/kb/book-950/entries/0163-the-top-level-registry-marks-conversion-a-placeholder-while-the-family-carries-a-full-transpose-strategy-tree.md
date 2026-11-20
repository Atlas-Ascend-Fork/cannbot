```
ID:        0163-the-top-level-registry-marks-conversion-a-placeholder-while-the-family-carries-a-full-transpose-strategy-tree
LABEL:     trap
LEVEL:     L8 (toolchain & build)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/tiling/index.md:76 —
           "| Conversion | [conversion/](conversion/) | [fallback/](conversion/fallback/)（占位） | — | — |" ;
           conversion/fallback/index.md:3 — "> Conversion 族（Transpose, Concat, Split）的兜底 Tiling
           算法。Transpose 已收录参考策略；Concat/Split 待补充。" ; conversion/index.md:49-115 —
           a five-step strategy decision tree with five named principles
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a reading of `conversion/index.md` and `conversion/fallback/` showing the Transpose
           strategy tree is absent or non-actionable — the registry's `占位` label would then be
           accurate and this entry wrong.
```

# 0163 · The top-level registry marks conversion a placeholder while the family carries a full transpose strategy tree

## 1 · Claim
Upstream asserts, in the top-level tiling registry, that the conversion family's fallback is `占位` —
a placeholder. Upstream asserts, in the conversion family's own fallback index, something different
and more precise: Transpose has a recorded reference strategy and only Concat/Split are outstanding
(`Transpose 已收录参考策略；Concat/Split 待补充`). The family's `index.md` carries a five-step strategy
decision tree, a six-row applicability table mapping transpose strategies onto the reordering
operators, five numbered principles each with a measured justification, and a routing note directing
the reader back to `fallback/tiling-flow.md` for TilingData derivation. The fallback directory holds
`tiling-flow.md` and `tiling-fields.md` covering Small-Channel Transpose (`C ≤ 16`, modelled as
`[C, N] → [N, C]`) plus a reference script. Not established here; this entry records a labelling
state.

## 2 · The wrong branch this removes
This is the third instance of the same failure in one subtree (0152 elewise, 0156 broadcast), and it
is the sharpest, because here the family's own index is *correct* and only the registry is wrong. An
agent routing a Transpose case reads the registry, sees `占位`, and stops — without ever opening the
family index that would have told it the content exists. The one document that describes the state
accurately is the one the mislabel prevents reaching.

The content lost is not marginal. It includes the only decision tree in this domain that carries a
measured correction to its own predecessor: upstream states that the original transpose template's
"total bytes < 4 MB → SIMT" rule caused 3–10× degradations on conversion-class operators, gives the
mechanism (SIMT element-wise GM→GM at 6.25 % bandwidth utilisation, plus about 4 µs of `asc_vf_call`
dispatch), and replaces it. An agent that never reaches this file will reimplement the rule that was
already measured to be wrong.

The third wrong branch is one this book must avoid: treating all three `占位` labels as the same
defect. They are not. Elewise and broadcast have placeholder text *in the family's own fallback
index*; conversion does not — its fallback index states its coverage accurately and only the registry
disagrees. The repair differs accordingly, and this entry records the distinction rather than folding
it into a count.

## 3 · Ground / Source
The registry label, `tiling/index.md:76`:

```
| Conversion | [conversion/](conversion/) | [fallback/](conversion/fallback/)（占位） | — | — |
```

The family's own statement of coverage, `conversion/fallback/index.md:1-24`, in full:

```
# Conversion 数据转换类 — 兜底算法

> Conversion 族（Transpose, Concat, Split）的兜底 Tiling 算法。Transpose 已收录参考策略；Concat/Split 待补充。

## 适用算子

Transpose, Concat, Split

## Transpose 及重排类算子 — 已收录

本目录的 [tiling-flow.md](tiling-flow.md) 与 [tiling-fields.md](tiling-fields.md) 覆盖 **Small-Channel Transpose**（C ≤ 16，建模为 [C, N] → [N, C]）的 Tiling 推导与字段语义。

其余 Transpose 场景（大通道、多轴切分、021、5HD、gather、tensor_move、small_shape 等），以及同族重排算子（BatchToSpace / SpaceToBatch / DepthToSpace）的完整 tiling 策略选择，参考../index.md：

> **性能优化参考流程**：先按 `../index.md` 的策略速查表选定策略；命中 NDDMA 家族（TENSOR_MOVE / SMALL_SHAPE / CUT_ONCE / CUT_TWICE / N_LAST / BIG_DIM）或 small-channel 场景时，回到本目录的 tiling-flow.md 做 TilingData 参数推导。
>
> **BatchToSpace / SpaceToBatch / DepthToSpace 的参考范围**：这类算子本质是带 stride 的多维 DMA 重排，与 transpose 的 NDDMA 家族（CUT_ONCE/CUT_TWICE/BIG_DIM/N_LAST）同构，可原理参考其切分轴选择与多维 DataCopy 地址映射；TENSOR_MOVE 不适用（重排算子必有维度重排），VCONV/GATHER/SMALL_SHAPE/small-channel 需视具体 perm/block_shape 判定。

## Concat / Split — 待补充

- 多核切分策略（Concat 按输入段 / Split 按输出段）
- 单核切分策略（block 为单位搬移，考虑跨 stride 对齐）
- Buffer 规划
- 分支覆盖
```

So the family's index distinguishes what is covered (Transpose and the reordering operators) from
what is not (Concat/Split), gives the reading order between its two documents, and scopes the
transfer to BatchToSpace-class operators strategy by strategy. That is a coverage statement, not a
placeholder.

The strategy applicability table, `conversion/index.md:38-45`:

```
| transpose 策略 | 重排类算子能否参考 | 说明 |
|----------------|-------------------|------|
| NDDMA 家族（CUT_ONCE / CUT_TWICE / BIG_DIM / N_LAST） | ✅ 可原理参考 | 带 stride 的多维 DataCopy + perm 反查地址，与 BatchToSpace 等的"搬入即重排"同构 |
| TENSOR_MOVE | ❌ 不适用 | 要求轴规约后 dim==1（纯拷贝），重排算子必有维度重排 |
| VCONV_5HD / VCONV_021 | ⚠️ 视 perm 判定 | 仅适配 2D 末轴交换 / `perm=[0,2,1]`，重排算子的 perm 一般不匹配 |
| GATHER | ⚠️ 视 perm/硬件判定 | 需 dav-3510 + 末轴参与转置 + `TRANSPOSE_ENABLE_GATHER` |
| SMALL_SHAPE (SIMT 逐元素) | ⚠️ 仅极小数据量 | 原始模板逐元素读写带宽利用率仅 6.25%，须实现向量化读写 |
| small-channel (C≤16) | ⚠️ 需重新判定 C 语义 | transpose 的 C=被转小通道轴；重排算子的"通道"语义不同，需按实际 block_shape 重新建模为 [C, N]→[N, C] |
```

A three-state applicability column — yes, no, conditional — with the condition named in each row. This
is the most carefully scoped transfer table in the domain, and it is behind the `占位` label.

The measured correction that motivates the whole tree, `conversion/index.md:51`:

```
> ⚠️ **实战经验**:原始 transpose 模板按"总字节数 < 4MB → SIMT"的简单阈值分流,在 conversion 类算子(如 batch_to_space)中导致 SIMT 分支性能严重退化(比基线慢 3-10 倍)。根因是 SIMT 逐元素 GM→GM 搬运的带宽利用率仅 6.25%,在末轴不转置(N_LAST 适用)的场景下远不如批量 DataCopyPad。以下是经过实战验证的更新版决策树。
```

`dav-3510` appears in the GATHER row as a hardware condition — the only architecture word in this
family, naming an architecture and not a board.

Registered as C-950tiling-028, distinguished from C-950tiling-026 (elewise) and C-950tiling-027
(broadcast) by the fact that here only the registry is wrong.

## 4 · Procedure
The claim is about a document set; the decisive test needs no device and has not been run.

Arm 1 — coverage check, read-only, no device, no execution. Attempt to produce a complete strategy
selection plus TilingData derivation for four Transpose cases using only `conversion/index.md` and
`conversion/fallback/`: a `C ≤ 16` small-channel case, an `N_LAST` case with mergeable dimensions, a
last-axis-transposed case, and a `perm`-fully-scattered small case. Record for each whether the
selection completes and whether the TilingData derivation completes, and where blocked, the first
missing rule. Prediction on record: strategy selection completes for all four; TilingData derivation
completes only for the small-channel case, since `fallback/tiling-flow.md` covers `C ≤ 16` and the
other strategies' parameter derivations are not in this directory.

Arm 2 — routing cost, on a named 950 board (950PR or 950DT); never run in this phase.
Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and discard the
case if the die moved. Variance floor first: one build, 30 in-process runs and 5 fresh-process runs.

Take one `batch_to_space`-shaped case with a non-transposed last axis and mergeable output dimensions.
Build two kernels with one compiler pin: the plan the family's decision tree gives (`N_LAST` with
dimension merging), and the plan the original template's rule gives (`total bytes < 4 MB → SIMT`).
md5 both; host echo of the selected strategy and its parameters; output compared elementwise against a
CPU reference; `aiv_time` and achieved GB/s under `msprof --aic-metrics=PipeUtilization`, ≥10
iterations, first 5 dropped. Upstream predicts the SIMT plan is 3–10× slower and that its bandwidth
utilisation is about 6.25 %; both are checked.

Refuses to assume: that a free die stays free; that a die may be substituted; that the 4 MB rule is
what any current template actually implements — upstream describes it as the *original* template's
rule, and this book has not inspected that template; that the 3–10× range reproduces (arm 2 measures
it); that `dav-3510` availability implies `TRANSPOSE_ENABLE_GATHER` is set.

## 5 · Checker — acceptance declared before the run
Verdict variable `strategy_selectable`, 0 to 4, and `tiling_derivable`, 0 to 4, from arm 1. Declared
before the run: the `占位` label is wrong iff `strategy_selectable ≥ 3`. The OVERTURN fires iff
`strategy_selectable ≤ 1`. A low `tiling_derivable` alongside a high `strategy_selectable` is the
expected outcome and is reported as its own finding — the family can *choose* a strategy it cannot
fully *parameterise* from these files, which is a different gap from the one the label describes.

Verdict `simt_penalty` = SIMT median `aiv_time` / `N_LAST` median from arm 2, compared against 3–10×,
and `simt_bw` = the SIMT arm's achieved bandwidth as a fraction of the `N_LAST` arm's, compared
against 6.25 %.

The exit code is not the verdict: a transpose with a wrong address map produces wrong output and
exits 0. The elementwise comparison runs on both arms and the checker fails red if it did not. Arm 1's
guard: the coverage table must have eight rows (four cases × two questions) and the checker fails on a
short table, since silently skipping a case that could not be attempted would inflate both counts.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The 3–10×, 6.25 % and ~4 µs
figures are upstream's, none carrying a case identity, a board or a repetition count. Arm 1 needs no
device and has not been run either.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured, and no coverage check was performed. The entry does not establish that the
content behind the label is correct — 0164 records a decision node whose two arms give the same
answer, so "present" and "right" remain separate questions. It does not establish that the family's
own index is complete: it says Concat and Split are outstanding, and this entry does not dispute that.
It does not establish the 3–10 × SIMT penalty, the 6.25 % bandwidth figure or the ~4 µs dispatch cost.
It does not establish that `fallback/tiling-flow.md`'s coverage extends beyond `C ≤ 16`. It does not
resolve the other two `占位` instances, which have a different shape (0152, 0156). `dav-3510` names an
architecture, not a board, and appears only as a GATHER precondition, so BOARD is
`family-claimed(unverified)` and no board is named anywhere in this family. §4 arm 2 names 950PR/950DT
because that is where our run would happen. Nothing here is established for any 910-family board.
