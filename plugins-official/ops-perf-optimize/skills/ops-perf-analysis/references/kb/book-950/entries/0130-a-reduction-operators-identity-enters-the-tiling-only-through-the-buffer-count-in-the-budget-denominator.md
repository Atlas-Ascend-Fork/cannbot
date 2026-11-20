```
ID:        0130-a-reduction-operators-identity-enters-the-tiling-only-through-the-buffer-count-in-the-budget-denominator
LABEL:     procedure
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/tiling/reduction/fallback/tiling-flow.md:3-4,342-353 —
           "所有归约算子共享同一套模板语言；不同算子仅在 UB 预算的分母（中间 buffer 数量）上有差异" ·
           "通用模板不变，修正的是 **per_row_bytes** 或 **每元素开销** 中的 buffer 项" ·
           "**Agent 推导步骤**：先确定算子数学流程 → 数清 UB 内同时存在的 buffer 份数 → 代入对应
           模板的预算公式。"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a reduction operator on a named 950 board whose best plan requires a template or a
           multi-core split that the five-template tree cannot express — the operator would then
           enter the tiling somewhere other than the denominator, which this claim denies.
```

# 0130 · A reduction operator's identity enters the tiling only through the buffer count in the budget denominator

## 1 · Claim
Upstream asserts that all reduction operators share one template language and differ only in the
UB budget's denominator — the number of intermediate buffers simultaneously live in UB. Upstream
states the derivation procedure for a new operator in three steps: determine the operator's
mathematical flow along the R axis, count the buffer copies simultaneously present in UB, and
substitute that count into the chosen template's budget formula. Upstream gives a per-operator
correction table: ReduceSum/ReduceMax need no extra intermediate and use the standard formula;
Softmax needs max, exp and sum, giving `input×2 + output×2 + fp32×2` under FullLoad and requiring
a re-read of the source data under Recompute; LayerNorm needs mean and normalize — two correlated
statistics — which upstream says should switch to Welford's online algorithm under Recompute;
RMSNorm is similar with one fewer buffer. Upstream asserts explicitly that Softmax needs no
additional branch in the decision tree. Not established here.

## 2 · The wrong branch this removes
Without this rule an agent asked for a LayerNorm tiling looks for LayerNorm knowledge, finds none
(this family ships case studies for Softmax and EuclideanNorm only), and either refuses or invents.
The rule says the missing knowledge is not missing: LayerNorm is the five templates with a
different denominator, and the only genuinely operator-specific decision is how many buffers its
math needs at once. That turns an open-ended question into a countable one.

The second wrong branch is under-counting, and Softmax's Recompute row is the instructive case.
Under Recompute the chunk is sized with `每元素开销 = 输入×3 + 输出×2 + FP32×1`, where the three
input copies are, in upstream's own annotation, the original data, the exp result, and a re-read
buffer — because Softmax's step 4 needs the sum from step 3, so the source must be visited twice.
An agent that counts the *tensors* in the formula (input, output) rather than the *live copies in
UB at one moment* will budget two and get a chunk 1.5× too large. Nothing checks this: the plan is
schema-valid and the overflow appears at run time or as a silent clamp.

The third: Welford. Upstream ties it to a specific condition — two correlated statistics plus
Recompute — not to Norm operators in general. An agent that enables it for a FullLoad LayerNorm has
paid for an online algorithm it does not need; one that skips it for a Recompute LayerNorm computes
variance from a two-pass formula over chunked data, which is a numerical-accuracy problem rather
than a performance one.

## 3 · Ground / Source
The rule, `reduction/fallback/tiling-flow.md:3-4`:

```
> 归约类算子的五模板决策树与 UB 预算推导。所有归约算子共享同一套模板语言；
> 不同算子仅在 UB 预算的分母（中间 buffer 数量）上有差异。
```

The correction table and procedure, `:342-353`, in full:

```
## 7. 算子差异：如何修正 UB 预算

通用模板不变，修正的是 **per_row_bytes** 或 **每元素开销** 中的 buffer 项：

| 算子 | 沿 R 轴中间量 | buffer 修正 |
|------|-------------|------------|
| ReduceSum/Max | 无额外中间量 | 标准公式 |
| Softmax | max, exp, sum | 输入×2 + 输出×2 + FP32×2（FullLoad）；Recompute 需重读原数据 |
| LayerNorm | mean, var, normalize | 两个关联统计量 → Recompute 时启用 Welford |
| RMSNorm | mean_sq, normalize | 类似 LayerNorm，少一个 mean 缓冲 |

**Agent 推导步骤**：先确定算子数学流程 → 数清 UB 内同时存在的 buffer 份数 → 代入对应模板的预算公式。
```

The worked instance, `reduction/fallback/example/softmax/experience.md:10-26`, establishing the
buffer count from the math:

```
output[i] = exp(input[i] - max(R)) / sum(exp(input[R] - max(R)))

| 步骤 | 操作 | 沿 R 轴类型 |
|------|------|-----------|
| ① | ReduceMax → max | 归约 |
| ② | Sub + Exp → exp_shifted | 逐元素 |
| ③ | ReduceSum → sum | 归约 |
| ④ | Div → output | 逐元素 |

**关键特征**：步骤 ②③ 需要步骤 ① 的结果（max），步骤 ④ 需要步骤 ③ 的结果（sum）。
Recompute 模式下 R 无法一次载入，需**分轮重读原数据**。
```

and its budget corrections, `softmax/experience.md:86-136`:

```
### AR-FullLoad

每行 UB 开销 = r_align × (输入×2 + 输出×2 + FP32中间量×2)
固定预留 = 1024 + 512

rows_per_ub = (ub_size - 1536) / (r_align × (4 + 4×dtype_bytes))
rows_per_core = ceil(A1 / core_num)
rows_per_ub = min(rows_per_ub, rows_per_core)

FullLoad 条件: rows_per_ub ≥ 1

对比标准 ReduceSum：分母多了 FP32 中间量和双倍 buffer（输入/输出各 2 份）。

### AR-Recompute

可用 UB = ub_size - 2112   // max_buf(32) + sum_buf(32) + binary_cache(2048)

每元素开销 = 输入×3 + 输出×2 + FP32×1
  // 3 份输入: 原数据 + exp 结果 + 重读缓冲
  // Recompute 需分轮重读原数据计算 exp

r_chunk = floor(可用UB / 每元素开销)，32B 对齐
```

Note the arithmetic in the FullLoad line: the prose denominator is
`r_align × (输入×2 + 输出×2 + FP32中间量×2)` while the formula denominator is
`r_align × (4 + 4×dtype_bytes)`. Reading the second: `4×dtype_bytes` covers four operand-precision
copies (input ×2 + output ×2) and the bare `4` covers the FP32 intermediate — but the prose says
FP32 ×2, which would be 8. The two lines disagree by one FP32 copy. At FP32
(`dtype_bytes = 4`) the formula gives 20 bytes per element against the prose's 24; at FP16 it gives
12 against 20. Registered as C-950tiling-012. It matters because this is the file an agent copies
when deriving LayerNorm.

Upstream's Norm-derivation hints, `softmax/experience.md:167-181`:

```
| 对比项 | Softmax | LayerNorm |
|--------|---------|-----------|
| 归约次数 | max + sum | mean + var（两个关联统计量） |
| 中间 buffer | exp 缓冲 | 去均值缓冲、方差缓冲 |
| Recompute 增强 | 重读原数据 | 建议启用 **Welford Online** |
| 模板选择 | 通用五模板 | 相同决策树，修正 UB 预算 |

**Agent 步骤**：
1. 列出 Norm 算子沿 R 轴的计算步骤
2. 数清 UB 内同时需要的 buffer 份数
3. 套用 [通用 UB 预算公式](../../tiling-flow.md#7-算子差异如何修正-ub-预算)
4. 若有两个关联统计量且走 Recompute，启用 Welford
```

and the enhancement gate, `tiling-flow.md:330-334`:
`| **Welford Online** | op_type 为 var/std/norm 且 Recompute 模式 | 分块流式计算 mean + var |`.

The Softmax case file's own worked examples, `:142-161`, illustrate the rule end to end and use
`ub_size = 248KB` at `:146` — the value this family's *measurement* anchors contradict (0131).
Its case A also computes `rows_per_core = ceil(32/64) = 1, used_core_num = 32`, which silently
assumes `core_num = 64`.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase. The claim
is that operator identity is confined to one number, so the procedure derives an operator upstream
never wrote up and checks whether the confinement holds.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s
spacing; bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and
discard the case if the die moved.

Derive-and-test, for LayerNorm and RMSNorm — the two operators in upstream's table with no case
file. For each: write out the R-axis flow, count live UB buffers per template, substitute into
0123's formulas, and record the predicted `rows_per_ub` / `r_chunk` / `a0_tile_len` *before*
building. Then build at the predicted tile, at the tile a Softmax-denominator would have given, and
at the tile a ReduceSum-denominator would have given — three points that differ only in the count
this entry says is the operator's whole contribution. One compiler pin, md5 each binary, host echo
of the derived fields, fp64 reference check within a tolerance declared in advance, `aiv_time`
under `msprof --aic-metrics=PipeUtilization`, ≥10 iterations, first 5 dropped, per case, against
0126 arm 0's variance floor.

Welford arm: for LayerNorm under AR-Recompute, build with and without Welford and compare both
`aiv_time` and numerical error against the fp64 reference at a shape with large R and a mean far
from zero — the regime where a two-pass variance loses precision. This measures the enhancement's
stated purpose (accuracy under chunking) as well as its cost.

Expressiveness arm — the falsifying arm. Attempt a reduction operator whose flow does not fit:
ArgMax with index tracking under ARA-Recompute, where the index must survive cross-bin binary
merging. If it can be expressed as a denominator change, the claim holds for it; if it needs a
different template or a different multi-core split, the claim fails and that is the OVERTURN.

Refuses to assume: that a free die stays free; that a die may be substituted; that `ub_size` is
248 KB (the Softmax case file's figure) or 192 KB (the EuclideanNorm anchor's) — it is queried and
printed (0131); that `core_num` is 64; that a predicted tile is the tile used (echo required); that
the FullLoad denominator is the prose one or the formula one — both are evaluated and both
predictions recorded, which is how C-950tiling-012 gets resolved by measurement rather than by
choosing an author.

## 5 · Checker — acceptance declared before the run
Verdict variable `denominator_suffices`, per operator: true iff the plan derived by counting
buffers is the fastest of the three built points AND produces a correct result, while the two
wrong-denominator points are respectively slower (over-counted) or incorrect/clamped
(under-counted). Declared acceptance: the rule holds iff `denominator_suffices` is true for both
LayerNorm and RMSNorm. The OVERTURN fires iff the expressiveness arm shows an operator that cannot
be expressed by a denominator change. A second verdict `prose_or_formula` names which of the two
disagreeing FullLoad denominators matched the working plan.

The exit code is not the verdict. The blind mode here is specific and easy to fall into: an
under-counted denominator produces a tile that is too large, which the host may clamp back to a
legal size, after which the point runs correctly and the comparison shows all three points equal —
reading as "the denominator does not matter", the exact opposite of the truth. The host echo of the
derived tile is therefore required at every point, any clamped point is excluded and reported, and
the checker goes red rather than issuing a verdict when a point is clamped. Second guard: the
numerical check must run on every point including the fast ones, since an under-counted Softmax
Recompute can produce a *wrong* result rather than a slow one.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured; no operator was derived against a clock. The entry does not establish that
the denominator rule covers every reduction operator — the expressiveness arm exists because it may
not, and ArgMax with index tracking is the suspected counter-example. It does not resolve the
FullLoad denominator disagreement (C-950tiling-012), does not establish any of the fixed reserves
(0123), and does not establish `ub_size` or `core_num` for any board — the Softmax case file uses
248 KB and 64 while the EuclideanNorm anchors use 192 KB and 72 (0131). It does not establish that
Welford improves accuracy or costs time; upstream recommends it under one condition and gives no
numbers. It says nothing about the interleaved templates, whose budget has a different shape
(0128), or about operators that are not reductions. No board is named in either source file, so
BOARD is `family-claimed(unverified)`; §4 names 950PR/950DT because that is where our run would
happen. Nothing here is established for any 910-family board.
