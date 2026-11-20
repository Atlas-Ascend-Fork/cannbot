```
ID:        0330-the-dav-3510-topk-is-nine-templates-in-one-fixed-dispatch-order-and-the-order-is-a-performance-contract
LABEL:     knowledge
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/sort/templates/usage_guide.md:20 —
           "当前性能不能概括为"使用 RadixSort"。实现按 shape、dtype、k、UB 和核数在以下模板间选择"
SOURCE:    same file:97-101 — "common 内保持 `non-last mode 8 -> last-axis small MergeSort ->
           single-block radix -> fp32 inter-core merge -> fp32 intra-core merge -> single-core radix
           -> optimized multi-core radix -> general multi-core radix -> SortAndTopK`。这些模板共享
           TilingData，但 mode 专属字段不同；host 判断、modeType、tilingKey 和模板实例必须一一对应。"
           ; :267 — "这些模板的次序属于性能契约。任何顺序调整都要对被抢占模板的所有边界 case 做 A/B。"
           ; :259-265 — the six per-template conditions quoted in §3
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured DAV_3510 TopK on a named 950 board where a later template in the order beats
           an earlier one on a case the earlier one claims — the order would then not be a
           performance contract but an arbitrary sequence, and the routing would need re-deriving
           per case rather than being preserved.
```

# 0330 · The DAV_3510 TopK is nine templates in one fixed dispatch order, and the order is a performance contract

## 1 · Claim
Upstream asserts that the DAV_3510 TopK's performance cannot be summarised as "use RadixSort", and
that the implementation selects among templates by normalised shape, dtype, `k`, UB capacity and
core count jointly. Upstream asserts a specific dispatch order for the common (non-special) route,
nine positions long: non-last mode 8 → last-axis small MergeSort → single-block radix → fp32
inter-core merge → fp32 intra-core merge → single-core radix → optimized multi-core radix →
general multi-core radix → SortAndTopK. Upstream asserts that these templates share one TilingData
while their mode-specific fields differ, and that the host decision, `modeType`, `tilingKey` and
template instance must correspond one to one. Upstream asserts that the order is a **performance
contract**: any reordering requires A/B testing every boundary case of the template that gets
pre-empted. Upstream asserts three special routes (tiling keys 900001/900002/900003) that dispatch
*before* the common keys. Not established here.

Upstream states the operator contract the whole thing serves: contiguous ND input, ordered output,
int64 indices, `1 ≤ k ≤ min(D, 2048)`, seven dtypes (int8/uint8/int32/int64/fp16/fp32/bf16), and
both `largest` and `smallest`.

## 2 · The wrong branch this removes
The available simplification is to implement one good radix select and route everything to it.
Upstream's first sentence exists to block exactly that, and its anti-pattern table names the
consequence — `用一个 RadixSort 覆盖全部 TopK | 小轴、非尾轴、int64 和大 k case 明显回归`.

The second simplification is routing by dtype. It is the most natural feature to branch on, and
upstream names it as an anti-pattern too: `只按 dtype 选模板 | 同 dtype 不同 D/inner/k 落入错误路径`.
The correct feature set is the normalised shape *plus* UB *plus* core count, which means the routing
decision is not expressible without querying the platform (`950:0141`).

The third and least obvious: treating the nine-position order as an implementation detail and
reordering it during a refactor. The order is a pre-emption chain — each position claims the cases
it can serve and passes the rest down — so moving a template up silently takes cases from everything
below it. Upstream's rule is the audit that makes a reorder safe, and it is expensive by design:
A/B every boundary case of the pre-empted template. An agent that reorders "harmlessly" will find
the regression in a hidden set, not in its own tests, which is the same shape as `0326`.

The fourth is subtler and concerns the shared TilingData. Nine templates sharing one struct with
mode-specific fields means an incorrect `modeType` produces a *plausible* kernel reading garbage
from fields the other mode owns — not a crash, not a type error. Upstream's one-to-one correspondence
rule (`host 判断、modeType、tilingKey 和模板实例必须一一对应`) is the only thing standing between an
implementer and that failure, and nothing enforces it.

## 3 · Ground / Source
The refusal to summarise, `templates/usage_guide.md:20-30`:

```
当前性能不能概括为"使用 RadixSort"。实现按 shape、dtype、k、UB 和核数在以下模板间选择：

| 路径 | 核心适用场景 | 决定性能的实现 |
| 固定小轴 | non-last，D=7/17，k=D，fp16/bf16 | 固定 compare-exchange network，沿 inner 宽向量并行 |
| transpose-fallback | outer=1 的超大 int32/fp32 非尾轴，inner 足够大且 k/D 小 | 设备侧物化为连续尾轴，复用完整尾轴 TopK |
| fallback L | int64 或其它 fallback 的连续行 | G 行批处理、D 分块、running TopK、连续 DMA |
| fallback S | 大非尾轴或高复用 int32 跨步行 | 2D Compact DMA、Gather 装配、G 行 TopK、UB 输出转置 |
| common mode 8 | D<=2048 的一般非尾轴 | UB 内重排为连续行，按 dtype 选 merge/radix |
| common merge/radix | 一般尾轴 | small merge、single-block/single-core/multi-core radix、fp32 merge |
| SortAndTopK | 超大 D 或 radix tile 不可行 | 多核全轴 radix sort，再复制前 k |
```

The dispatch order, `:97-101`:

```
common 内保持 `non-last mode 8 -> last-axis small MergeSort -> single-block radix -> fp32 inter-core
merge -> fp32 intra-core merge -> single-core radix -> optimized multi-core radix -> general
multi-core radix -> SortAndTopK`。这些模板共享 TilingData，但 mode 专属字段不同；host 判断、
modeType、tilingKey 和模板实例必须一一对应。
```

The per-template conditions, `:259-265`, which are what make the order a chain rather than a list:

```
- non-last mode 8：D<=2048 时在 UB 内把跨步行重排为连续行；浮点优先 MergeSort，其余 RadixSelect。
- small MergeSort：D<=1024 的 fp16/fp32/bf16 尾轴；bf16 以 fp32 compute。
- fp32 `0.25 <= k/D < 0.5`：完整排序归并比反复选择更合适，依次尝试 inter-core、intra-core 两个
  独立模板。
- optimized multi-core：只有 `k*ceil(D/tile)<=tile` 时，所有局部候选才能在一次最终选择中放下。
- general multi-core：保留每 tile 的 k 候选并做后续选择，不可误套 optimized 条件。
- SortAndTopK：前述 tile 失败或 D 超大时的性能或能力兜底，不等于通用 M-way fallback。
```

Note `optimized multi-core`'s condition is a real inequality with a stated reason —
`k × ⌈D/tile⌉ ≤ tile` is exactly the capacity test for holding every tile's `k` candidates in one
final selection — while `general multi-core`'s row is a warning not to apply it where it does not
hold. That pair is the clearest single example of what "the order is a contract" means: the two
templates are the same algorithm under different capacity assumptions, and getting the order or the
condition wrong swaps them silently.

The contract statement, `:267`:

```
这些模板的次序属于性能契约。任何顺序调整都要对被抢占模板的所有边界 case 做 A/B。
```

The special-before-common rule, `:86` and `:271`:
`special key 900001/900002/900003 先于 common key 分发。`

The operator contract, `:8-9`:

```
当前契约：连续 ND 输入，有序输出，indices 为 int64；支持 int8/uint8/int32/int64/fp16/fp32/bf16，
`1 <= k <= min(D, 2048)`，largest/smallest 均支持。
```

Where the truth lives, `:32-34` and `:40`: the exact routing thresholds and the host tiling are
maintained in the *other* shelf (`ascendc-perf-optimize/references/tiling/sort/`), and this document
states that it deliberately does not duplicate them. So the family's knowledge is split across two
shelves by design, and `950:0143` carries the sibling shelf's ordering rules. This entry carries the
implementation-side order, which `950:0143` does not have — that entry records "two fixed orders that
may not be permuted" from the tiling side; the nine-position common chain and the shared-TilingData
correspondence rule are new here.

Nothing in this section is measured. There is not one timing figure anywhere in the document.

## 4 · Procedure
Proposed, runnable later on a named 950 board. Never run in this phase.

Arm 1 — the routing, echoed. Build the template stack and run a case set spanning the seven dtypes,
last/non-last axes, `k ∈ {1, D/4, D/2, D, 2048}` and `D` across the `2048` and `1024` boundaries.
Echo per case: `tilingKey`, `modeType`, the template symbol actually entered, core count, dynamic
UB and workspace. Upstream's own first implementation step demands exactly this record
(`:94-96`: without per-case routing records, `很难区分"kernel 变慢"与"tiler 选错"`), and it is the
precondition for every other arm.

Arm 2 — the order as a contract. For each adjacent pair in the nine-position chain, find the cases
the earlier position claims, and run them additionally under the later template with the earlier one
disabled. The contract holds iff the earlier template wins on every such case outside the floor. A
single loss is the OVERTURN and identifies the position where the order is wrong.

Arm 3 — the shared-TilingData hazard. Build one deliberately mismatched pair: `modeType` set for
template A while template B is instantiated. Record whether anything detects it — a
`static_assert`, a runtime check, a wrong answer, or nothing. Upstream states the correspondence as
a rule; this arm asks whether it is enforced anywhere.

Arm 4 — the `optimized multi-core` capacity condition, at its boundary. Sweep `k` and `tile` across
`k × ⌈D/tile⌉ = tile`, and check that the routing switches to `general multi-core` exactly there and
that the optimized template is not slower on either side than the general one.

Variance floor first: one build, 30 in-process runs, 5 fresh-process runs, IQR over median, beside
every comparison, and `0327`'s same-path same-magnitude sibling check applied to every table before
any row is read. Device selection: `npu-smi info -l`;
`npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing; bind only on three idle samples;
re-sample after; discard the case if the die moved. Refuses to assume: that a free die stays free;
that a die may be substituted; that the routing the host computed is the template the device ran
(Arm 1 echoes the entered symbol, not the intended one); that `k ≤ 2048` and `D ≤ 2048` are the same
bound (they are different constraints and are swept independently); that UB capacity or core count
is a literal — both are queried and echoed (`950:0141`, `950:0207`).

## 5 · Checker — acceptance declared before the run
Verdict `route_map` = Arm 1's per-case table of (case features → entered template). No pass
condition; it is the deliverable and the input to every other verdict.

Verdict `order_holds[i]` for each of the eight adjacent pairs, true iff the earlier template wins on
every case it claims, outside the floor. Declared before the run: the contract is **supported** iff
all eight hold. Any false fires the OVERTURN at that position and the entry is corrected in place to
name it.

Verdict `mismatch_detected` ∈ {static, runtime, wrong-answer, silent} from Arm 3. `silent` is the
predicted and most consequential outcome, and it is declared as a *finding*, not a failure.

Verdict `capacity_boundary_exact` = true iff Arm 4's routing switch coincides with
`k × ⌈D/tile⌉ = tile` to the case.

The exit code is not the verdict. Three guards.

First, every case is checked for correctness two ways, because TopK has a failure mode that a value
comparison misses: upstream's own regression matrix requires using the returned **indices** to fetch
back from the input and confirming the value/index pairs agree (`:299`,
`检查 values 之外，还要用输出 index 回取输入确认 pair 一致`). A template that returns the right
multiset of values with shuffled indices passes a value comparison and is wrong.

Second — the input that makes this checker go red — Arm 1 is repeated with one case whose features
are constructed to fall outside the stated contract (`k > min(D, 2048)`). The routing **must**
refuse or the run **must** fail. If an out-of-contract case is silently routed and returns
something, then `route_map` is not a map of a defined function and Arm 2's per-position claims have
no domain. That is a planted positive the instrument has to find.

Third, no `order_holds` is decided without the floor and without `0327`'s contamination check: eight
pairwise comparisons on a shared machine is eight chances to record a co-tenant as a routing
verdict.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The document carries no
timing for any template, so there is nothing to reproduce — only a structure to test. No case was
routed and no template was entered.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. Upstream supplies **no performance number anywhere** in this
document, so the nine-position order is a stated contract with no published evidence behind it, and
this entry carries the structure without any magnitude. The exact routing thresholds are explicitly
maintained in the sibling shelf and are not reproduced here; `950:0143` carries what that shelf
states, and the two must be read together. The `k × ⌈D/tile⌉ ≤ tile` condition is stated with a
reason but `tile` is never defined in this document. `mode 8`, the special keys 900001/900002/900003
and `modeType` are named without their value sets. The claim that host decision, `modeType`,
`tilingKey` and template instance correspond one to one is a rule, and §4 Arm 3 exists because
nothing here shows it is enforced. The operator contract (`1 ≤ k ≤ min(D, 2048)`, seven dtypes) is
stated as "current" and carries no toolkit pin. BOARD is `family-claimed(unverified)`: the document
names Ascend 950 / DAV_3510 as its target architecture and no board. Nothing transfers to the other
book (RULES.md Art. 1) — the A2 sort material is fenced off by its own author (`0329`).
