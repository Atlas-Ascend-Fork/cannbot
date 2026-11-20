```
ID:        0454-the-kv-block-index-may-not-enter-the-task-index-unless-a-cross-core-combine-stage-is-added-with-it
LABEL:     boundary
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-tiling-design/references/flashattention/overview.md:150-155 —
           "**禁止**: / - 在默认 task 级模式下把 `s2` 放入 taskIdx —— 跨 task 间共享 online softmax
           状态无法保证;且默认场景 `totalTasks ≥ usedCoreNum`,跨核 fence 成本 >> 顺序 s2 累积成本 /
           - 启用 split-KV reduce 但**不补**partial reduce + cross-core combine —— 多核间无法同步
           在线 softmax 状态 → 多核死锁或精度崩塌 / - 在同一算子内混用两种切分方案 /
           **违反后果**:输出乱值 / 多核死锁 / 精度崩塌"
SOURCE:    same file:42 — "| 任务维度 | s2(KV 分块)**禁入**任务分发维度 | 多数所有维度均可任务分发 |"
           ; same shelf, design.md:136 — "| **Split-KV reduce(FlashDecoding 技术)** | 同一 KV 序列
           沿 s2 维拆给多核并行,完成各自局部 softmax + PV 后做跨核 combine | 各核计算 partial 状态后,
           通过 cross-core combine 阶段归并出最终 `max` / `sum` / `O`,等价满足 |
           `totalTasks << usedCoreNum`,典型 Sq=1 纯 decode + 极大 Sk(> 2K)的"核数富余"场景 |"
           ; design.md:138 — "**Split-KV reduce 是 FA 算子的一种实现技术,不是子族**"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a decode-shaped case (`Sq = 1`, `Sk > 2K`) on a named 950 board at which the default
           task-level decomposition, leaving cores idle, is not slower than a correctly built
           split-KV-reduce implementation beyond the variance floor — the "核数富余" motivation
           would then have no subject at that shape and the second strategy would buy nothing.
           Equally: a split-KV build without the combine stage that produces correct output would
           falsify the claim that the partial states cannot be reconciled without it.
```

# 0454 · The KV-block index may not enter the task index unless a cross-core combine stage is added with it

## 1 · Claim
Upstream asserts that `s2`, the KV-block index, is the one dimension of a FlashAttention-class
operator forbidden from the task-dispatch dimensions — stated as a family-distinguishing property
(`s2(KV 分块)**禁入**任务分发维度`) and again as invariant I4. Upstream asserts two, and only two,
legal decompositions: the default, in which `s2` iterates inside a task and the online-softmax state
accumulates sequentially; and split-KV reduce, in which `s2` is split across cores and each core's
partial `max`, `sum` and `O` are merged by a dedicated cross-core combine stage. Upstream asserts
three prohibitions with named consequences — putting `s2` in `taskIdx` under the default strategy,
enabling split-KV reduce without adding the partial-reduce segments and the combine stage
(consequence: multi-core deadlock or precision collapse), and mixing the two strategies in one
operator. Upstream asserts that split-KV reduce is a parallel-implementation technique rather than a
subfamily, orthogonal to GQA/MHA/MLA/sparse/quantised, and that a design document must therefore
declare both dimensions independently. Not established here.

## 2 · The wrong branch this removes
Without this entry an agent building the task decomposition treats `s2` like every other axis. This is
the correct instinct for almost every operator family in the corpus — the reduction, broadcast,
gather and elementwise families all dispatch on any available axis — and upstream marks it as the FA
family's defining difference in its "boundary with other families" table. `s2` looks especially
attractive because in decode shapes it is the *only* large dimension: `Sq = 1`, `B` is the batch, and
with a long KV cache `Sk` is where the parallelism is.

The normal checks do not catch the mistake in the direction that matters. Splitting `s2` across cores
without a combine stage does not produce a diagnosable error; it produces cores that each hold a
correct partial `max` and `sum` for their own slice and no mechanism to reconcile them, which upstream
says surfaces as deadlock *or* precision collapse depending on how the missing synchronisation was
approximated. Neither symptom names `s2`.

The second wrong branch is the over-correction, and it is the reason this entry is a `boundary` rather
than a `trap`: reading "s2 must never be dispatched" as absolute leaves the decode case — `Sq = 1`,
very long `Sk`, `totalTasks << usedCoreNum` — running on a fraction of the cores with no remedy.
Upstream's answer is not "never split `s2`" but "splitting `s2` costs you a combine stage, three
workspace segments, a different softmax variant and a task structure incompatible with the default
one". The prohibition is on splitting it *for free*.

The third wrong branch is a classification error with real consequences: treating split-KV reduce as a
subfamily. Subfamily selection is exclusive (`subfamilies.md:326`, `禁止混用子族`) and drives service
class naming, workspace tables and tiling decisions. If FlashDecoding is filed as a subfamily, then
"quantised MLA with FlashDecoding" becomes unrepresentable, and upstream states three times that the
two are independent axes.

## 3 · Ground / Source
The family-boundary statement, `references/flashattention/overview.md:42`:

```
| 任务维度 | s2(KV 分块)**禁入**任务分发维度 | 多数所有维度均可任务分发 |
```

The invariant and its prohibitions, `:140-155`:

```
### §3.4 I4 — s2 状态累积正确性不变量

跨 KV 分块的 online softmax 状态(`max` / `sum` / `O_acc`)必须被**完整、正确地累积**,这是 FA 数学正确性的硬要求。任何 s2 切分方案都必须保证这一点。

满足此不变量的两种合法切分方案:

1. **默认 task 级切分(主流场景)**:s2 loop 在 task 内部顺序执行,`s2` 索引**不进入** taskIdx 任务分发维度。该方案天然满足正确性——同一 task 内顺序累积 online softmax 状态,跨 task 之间没有 s2 状态共享需求。

2. **Split-KV reduce(适用 Sq=1 + 大 Sk + 核数富余场景,详见 [`design.md §2.5`](./design.md))**:s2 沿 KV 维拆给多核并行,每核计算自己切片的局部状态(`max_partial` / `sum_partial` / `O_partial`),完成后通过专门的 cross-core combine 阶段把所有切片归并出最终 `max` / `sum` / `O`。

**禁止**:
- 在默认 task 级模式下把 `s2` 放入 taskIdx —— 跨 task 间共享 online softmax 状态无法保证;且默认场景 `totalTasks ≥ usedCoreNum`,跨核 fence 成本 >> 顺序 s2 累积成本
- 启用 split-KV reduce 但**不补**partial reduce + cross-core combine —— 多核间无法同步在线 softmax 状态 → 多核死锁或精度崩塌
- 在同一算子内混用两种切分方案

**违反后果**:输出乱值 / 多核死锁 / 精度崩塌
```

Note the structure of the first prohibition's justification: it gives *two* reasons, and they are of
different kinds. `跨 task 间共享 online softmax 状态无法保证` is a correctness reason. `跨核 fence
成本 >> 顺序 s2 累积成本` is a performance reason, and it is conditioned on `totalTasks ≥
usedCoreNum` — the default scenario. So the prohibition is unconditional in the correctness half and
scoped in the performance half, and the scope of the performance half is exactly the condition that
fails in the decode case the second strategy exists for. The inequality itself is stated with no
measurement on either side; `>>` is upstream's only quantifier. Recorded as `Q-950fin-02`.

What enabling the second strategy actually costs, `design.md:140-146`:

```
#### Split-KV reduce 启用时的额外契约

- **新增 partial reduce workspace 段**:partial O 段 + partial logsumexp max 段 + partial logsumexp sum 段(具体段名见参考实现)
- **Softmax 变体**:每核处理自己的 s2 切片,不走 stateful 累积,改为每切片独立计算后再 cross-core combine
- **新增跨核 combine 阶段**:所有切片完成后,从 partial 段读回各切片局部结果,做加权归一化得到最终 O
- **任务结构变化**:任务模型本质不同,task 描述结构精简(只需 batch / kvHead / Sq 块标识 + 实际合并的切片数),与默认 task 级的 RunInfo 不兼容
```

— four changes, of which the last means the two strategies cannot share a task descriptor, which is
the mechanical reason the third prohibition (no mixing) exists.

The orthogonality statement, `design.md:138`: `**Split-KV reduce 是 FA 算子的一种实现技术,不是
子族**——它可以叠加在任意 FA 子族(GQA / MHA / MLA / 稀疏)之上,本质是替换并行模型(task 级 → s2
切片 + cross-core combine),不改变算子的数学形态。` Repeated at `design.md:151` (`设计文档应同时
声明:**子族** … + **并行策略** … 两个独立维度`) and at `subfamilies.md:23`. Stated three times in
two files, which is how a document says "readers get this wrong".

One further consequence the family records without comment: under split-KV reduce the Cube may drop
out entirely. `subfamilies.md:91` lists, for the FlashDecoding row, `仅 Vector 服务(无 Cube)` with
the computation chain `partial reduce + cross-block combine(无 Cube)`, and `:48` says the partial
computation and combine `可能由 Vector 直接做,不走 Cube`. So the "FA class is `__mix__` AIC+AIV"
statement at `overview.md:39` is a property of the default strategy, not of the family — a scope the
family-boundary table does not carry.

All passages are in one repository: one origin (RULES.md Art. 3).

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind on three consecutive idle samples only; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and
discard the case if the die moved. Report the variance floor beside every timing point.

**Arm 1 — the crossover the prohibition is scoped by.** The default task-level build across
`(B, Sq, Sk)` from prefill-shaped (`Sq` large, `totalTasks ≫ usedCoreNum`) to decode-shaped
(`Sq = 1`, `Sk ∈ {2K, 8K, 32K}`, `totalTasks < usedCoreNum`). Echo `totalTasks`, `usedCoreNum` and
the achieved core occupancy at each point. This locates, on this board, the region upstream calls
`核数富余` — a region upstream defines by an inequality and never by a shape.

**Arm 2 — split-KV reduce, complete.** The same operator with the second strategy fully built:
three partial segments, the per-slice softmax variant, the combine stage. Same sweep. Both arms
compared elementwise against an FP64 reference at the declared atol.

**Arm 3 — split-KV reduce with the combine stage omitted (the poison arm).** Built exactly as arm 2
minus the combine, with a hard timeout so a deadlock is recorded as a deadlock rather than hanging the
suite. Record which of upstream's two predicted outcomes occurs — deadlock, or completion with wrong
values — and at which core count each appears. Upstream names both and never says which happens when.

**Arm 4 — `s2` in `taskIdx` under the default strategy.** The forbidden first form: `s2` promoted to a
dispatch dimension with the sequential accumulation left in place. Expected to produce wrong values
rather than a fault. Retained because the *correctness* half of upstream's justification is
unconditional while the *performance* half is not, and this arm is where the correctness half is
observed at a shape where the performance half does not apply.

Refuses to assume: that a free die stays free, or that a die may be substituted; that `totalTasks` and
`usedCoreNum` are what the host thinks they are (both are echoed from the kernel); that a deadlock and
a wrong answer are the same finding; that the decode case is reachable without checking that the
workspace was sized from the runtime `Sk` and not from `Sk_max` (`0459` — at `Sk = 32K` the difference
decides whether the case allocates at all); that a fast result is a correct one.

## 5 · Checker — acceptance declared before the run
Verdict `occupancy(shape) = usedCoreNum / aicNum`, echoed, and `deficit_region := { shapes :
occupancy < 1 }`. Verdict `splitkv_wins(shape) := median time(arm 2) < median time(arm 1) − floor`.
Declared before the run: the entry is **supported** iff `splitkv_wins` is true somewhere inside
`deficit_region` and false everywhere outside it. The OVERTURN fires iff `splitkv_wins` is false
throughout `deficit_region` including `Sk = 32K`, `Sq = 1` — the strategy would then buy nothing at
the shape it was introduced for.

Verdict `no_combine_outcome` from arm 3 ∈ {`deadlock`, `wrong_values`, `correct`}. `correct` is the
second OVERTURN condition, and it is declared reachable now so that the arm is a real test: if the
partial states happen to reconcile without a combine stage at some core count, upstream's second
prohibition is wrong at that count.

The exit code is not the verdict: arm 4 is expected to exit 0 with wrong numbers, and arm 3's deadlock
outcome exits by timeout, which a naive harness scores as infrastructure failure. Guards: (1) the
timeout is a *recorded value*, not a discard — an arm that times out is reported as `deadlock` only
when the same build completes at a lower core count, otherwise it is `untestable`; (2) **the input
that makes this checker go red**: arm 1 and arm 2 at a prefill shape with `occupancy == 1`, where the
two strategies must produce identical output and arm 1 must not be slower than arm 2 by more than the
combine stage's cost — if arm 2 wins there, the two builds differ in more than the parallel strategy
and every comparison in `deficit_region` is an artifact; (3) no point is reported without its
occupancy, its `totalTasks`, its atol, its floor and its CANN pin.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The invariant, the two legal
decompositions, the three prohibitions, the four-item contract for the second strategy, the
orthogonality statement in its three locations and the Cube-free FlashDecoding row are file reads
performed at drafting time. The observation that the first prohibition's justification has one
unconditional half and one half scoped to `totalTasks ≥ usedCoreNum`, and the observation that
`__mix__` is a property of the default strategy rather than of the family, are readings of upstream's
own lines, not observations of a build.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The entry does not establish that split-KV reduce is ever faster,
nor where the crossover is; upstream gives one inequality (`totalTasks << usedCoreNum`) and one
shape sketch (`Sq=1` + `Sk > 2K`) with no board, no core count and no measurement, and `>>` is never
quantified. It does not establish that omitting the combine stage deadlocks rather than merely
producing wrong values — upstream names both and this entry cannot choose between them. It does not
establish the three partial workspace segments as sufficient, only as what upstream names. It does not
cover how `s2` interacts with causal masking under a split, which upstream never discusses. It does
not establish that the two strategies cannot be mixed, only that upstream forbids it and gives an
incompatible task descriptor as the mechanical reason. No board token appears in any quoted passage,
so BOARD is `family-claimed(unverified)`; §4 names 950PR/950DT only as where our run would happen.
Nothing here is established for any 910-family board.
