```
ID:        0156-the-broadcast-fallback-index-says-placeholder-over-a-four-branch-tiling-and-a-500-line-script
LABEL:     trap
LEVEL:     L8 (toolchain & build)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/tiling/broadcast/fallback/index.md:3,9-18 —
           "> 当前为占位文档，内容待补充。" · "## 待补充内容 - 多核切分策略（沿最大维度输出 shape
           均匀切分） - 单核切分策略（考虑广播维度的输入复用） - Buffer 规划（大张量 + 广播张量分别
           规划） - 分支覆盖" · "> 当前返回：「Broadcast Tiling 建模暂未收录。」" ;
           tiling/index.md:74 — "| Broadcast | [broadcast/](broadcast/) | [fallback/](broadcast/fallback/)（占位） |"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a reading of `broadcast/fallback/tiling-flow.md`, `tiling-fields.md` and the script
           showing they do not cover the four items the placeholder lists as missing — the label
           would then be accurate and this entry wrong.
```

# 0156 · The broadcast fallback index says "placeholder" over a four-branch tiling and a 500-line script

## 1 · Claim
Upstream asserts, in the broadcast fallback's index, that the document is a placeholder whose content
is yet to be supplied, lists four items as missing — multi-core splitting along the largest output
dimension, single-core splitting accounting for input reuse on broadcast axes, buffer planning with
the large tensor and the broadcast tensor planned separately, and branch coverage — and states the
routing answer to give meanwhile: `当前返回：「Broadcast Tiling 建模暂未收录。」`. The top-level
tiling registry repeats the `占位` label. In the same directory sit `tiling-flow.md` (a four-branch
decision tree with a chip-generation split, a four-step priority chain, per-branch flows, the general
UB and multi-core formulas, and a scalar-handling table), `tiling-fields.md` (a four-section field
table with a branch cross-reference and three alignment regimes) and
`script/broadcast_tiling.py` (a 590-line executable reference implementing the collapse, the branch
selector, all four branch tilings and a core-feeding shrink). Not established here; this entry records
a labelling state.

## 2 · The wrong branch this removes
Same shape as 0152 and, for this family, more costly. Broadcast is where the only genuine
dual-architecture branch in the whole tiling subtree lives (0154), where the NDDMA stride-0
replication technique is described, and where the dimensionally-sound copy of the UB capacity formula
sits — the one against which the elementwise markdown's broken copy is diagnosed (0151). An agent
that reads `占位`, emits the refusal string and stops loses all three.

The refusal is also self-defeating in a specific way: `elewise/fallback/tiling-flow.md:15` routes
non-identical shapes *to* the broadcast branch. So the elementwise family — itself labelled `占位`
(0152) — hands cases to a family whose index says it has no content. Two placeholders pointing at
each other, with complete tilings behind both.

Third, the placeholder's four bullets are not idle: they describe a *different* decomposition than the
one the directory implements. `大张量 + 广播张量分别规划` (plan the large tensor and the broadcast
tensor separately) is not how `tiling-flow.md` budgets — it uses one `maxElemNum` over
`bufferNum × maxDtypeBits` for all inputs. So an agent that treats the bullets as a specification and
the flow document as its implementation will look for a two-tensor buffer plan that is not there. The
bullets are an earlier design sketch, not a summary of what was built, and this entry says so rather
than claiming a clean match.

## 3 · Ground / Source
`broadcast/fallback/index.md`, in full — the entire file is 18 lines:

```
# Broadcast 广播类 — 兜底算法

> 当前为占位文档，内容待补充。

## 适用算子

Add, Mul, Sub 等含广播语义的二元逐元素算子

## 待补充内容

- 多核切分策略（沿最大维度输出 shape 均匀切分）
- 单核切分策略（考虑广播维度的输入复用）
- Buffer 规划（大张量 + 广播张量分别规划）
- 分支覆盖

---

> 当前返回：「Broadcast Tiling 建模暂未收录。」
```

The registry's matching label, `tiling/index.md:74`:

```
| Broadcast | [broadcast/](broadcast/) | [fallback/](broadcast/fallback/)（占位） | — | — |
```

The content in the same directory, item by item.

**多核切分策略** — `broadcast/fallback/tiling-flow.md:95-102`:

```
## 6. 通用多核切分公式

fusedProduct = ubOuter × (ubSplitAxis之前所有轴乘积)
blockFormer = ceil(fusedProduct / coreNum)
blockNum = ceil(fusedProduct / blockFormer)
blockTail = fusedProduct - (blockNum-1) * blockFormer
```

Note this is *not* the bullet's `沿最大维度输出 shape 均匀切分`: it flattens the UB split axis and
everything outside it, which is a different and more general rule.

**单核切分策略** — `:79-93`:

```
maxElemNum = (ubSize - extraSize) * 8 / (bufferNum * maxDtypeBits)
maxElemNum = floor_align(maxElemNum, 256 * 8 / minDtypeBits)

从最内轴向外累乘outputDims:
  curProduct *= dims[i]
  if curProduct > maxElemNum:
    ubSplitAxis = i; curProduct /= dims[i]; break

ubFormer = maxElemNum / curProduct
ubOuter = ceil(dims[ubSplitAxis] / ubFormer)
ubTail = dims[ubSplitAxis] - (ubOuter-1) * ubFormer
```

The bullet's `考虑广播维度的输入复用` is present in a different form: broadcast axes carry stride 0
(`tiling-fields.md:13` — `input_strides ... (broadcast轴=0)`), so the reuse is expressed as a stride
rather than as a separate budget term.

**Buffer 规划** — partially. `tiling-fields.md:19-27` gives the UB split fields including
`max_elem_num`, and `tiling-flow.md:57` gives a transfer-instruction optimisation
(`DataCopyPad dummy填充 → Copy → GatherMask (省tmpBuffer)`), but there is no separate plan for the
broadcast tensor as the bullet describes. This bullet is the one the directory does *not* answer in
the form the placeholder states.

**分支覆盖** — `:9-29`, the four-branch decision tree quoted in full in 0154 §3, plus the branch
cross-reference table at `tiling-fields.md:44-54` mapping every field to
OneDim / UB-Broadcast / NDDMA / Dynamic-UB.

And the executable reference, `broadcast/fallback/script/broadcast_tiling.py`, 590 lines, implementing
`DimensionCollapse`, the branch selector (0155 §3), `tiling_onedim`, the UB-split search, the NDDMA
`sch_mode` decision and `_maybe_shrink_onedim` — a core-feeding shrink whose docstring reads
`"""If block_num < core_num / 2, shrink max_elem_num to feed more cores."""` (`:320`), a rule that
appears nowhere in the markdown at all.

So the directory holds *more* than the placeholder's bullets ask for in three of four cases, and less
in one, and none of it is reachable from the index.

Registered as C-950tiling-027, alongside C-950tiling-026 (elewise, 0152) and C-950tiling-028
(conversion, 0163).

## 4 · Procedure
The claim is about a document set; the decisive test needs no device and has not been run.

Arm 1 — coverage check, read-only, no device, no execution. For each of the placeholder's four
bullets, attempt to produce the corresponding artifact from `broadcast/fallback/` alone: a multi-core
split for a given collapsed shape; a UB split; a buffer plan distinguishing the large tensor from the
broadcast tensor; and a branch selection with its `branches` block per 0103's schema. Record
completion and, where blocked, the first missing rule. Prediction on record: three complete (with the
multi-core and single-core rules being *more* general than the bullets describe), one blocked at the
separate-tensor buffer plan.

Arm 2 — routing cost, on a named 950 board (950PR or 950DT); never run in this phase.
Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and discard the
case if the die moved. Variance floor first: one build, 30 in-process runs and 5 fresh-process runs.

Take a non-last-axis broadcast `Add` (output `[64, 1024, 512]`, second input `[64, 1, 512]`, fp16) and
build two kernels with one compiler pin: the plan derived from `tiling-flow.md` plus the script, and a
plan an agent would write after the refusal string — materialise the broadcast operand in GM by an
explicit expand, then run a plain elementwise Add. md5 both; host echo of `branch`, `ub_split_axis`,
`ub_former`, `core_num`; output compared elementwise against a CPU reference; `aiv_time` and total
GM bytes moved under `msprof --aic-metrics=PipeUtilization`, ≥10 iterations, first 5 dropped. The
GM-bytes difference is the direct cost of not having the broadcast tiling.

Refuses to assume: that a free die stays free; that a die may be substituted; that `ubSize` or
`coreNum` are the script's literals (queried, 0141); that the expand-then-elementwise plan is slower —
arm 2 exists to put a number on it, and a null is reported as a null.

## 5 · Checker — acceptance declared before the run
Verdict variable `bullets_covered`, 0 to 4, from arm 1, with a partially-covered bullet counted as 0.5
and named. Declared before the run: the `占位` label is wrong iff `bullets_covered ≥ 3`. The OVERTURN
fires iff `bullets_covered ≤ 1`. Verdict `mislabel_cost` = expand-plan median `aiv_time` / derived-plan
median, and `mislabel_bytes` = the ratio of GM bytes moved, both reported with the variance floor.

The exit code is not the verdict. Arm 1's instrument is the four-row coverage table and the checker
fails red if the table has fewer than four rows. Arm 2's guards: the elementwise output comparison on
both arms — a broadcast plan with a wrong stride produces wrong output and exits 0 — and the host echo
of `branch`, since a derived plan the host re-selected would not be the plan under test.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. Arm 1 needs no device and has
not been run either.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured, and no coverage check was performed. The entry does not establish that the
content behind the label is correct — 0155 records constraints the script does not enforce, and 0154
records a `dcache` threshold the family never defines, so "present" and "right" remain separate
questions. It does not establish that a consuming agent stops at the refusal string. It does not
establish the cost of the mislabel. It does not claim the directory answers the placeholder's bullets
as stated: three are answered in a more general form and one — the separate buffer plan for the
broadcast tensor — is not answered at all. No board token appears anywhere in the broadcast family;
the flow document names two architectures, not boards, so BOARD is `family-claimed(unverified)`;
§4 arm 2 names 950PR/950DT because that is where our run would happen. Nothing here is established for
any 910-family board.
