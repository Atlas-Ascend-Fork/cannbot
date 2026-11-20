```
ID:        0331-a-seventeen-element-fixed-sorting-network-is-seventy-two-compare-exchanges-in-eleven-dependency-layers
LABEL:     knowledge
LEVEL:     L5 (compute & numerics)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/sort/templates/usage_guide.md:148-150 —
           "GM 以 axis 行搬入，index 行填 axis 编号。每个 compare-exchange 对整段 inner 列并行，
           value/index 必须使用同一个 swap mask。D=17 使用 72 次 compare-exchange、11 层依赖；
           不能换成动态插入排序后期待相同性能。"
SOURCE:    same file:154-161 — "- `largest` 在运行时改变 compare 方向，不需要两套网络。- NaN 比较与
           交换必须显式遵守接口语义，不能依赖普通 `>`/`<` 的偶然结果。- 尾 inner tile 仅写有效
           width；scratch 和 mask 仍按对齐 tileWidth 分配。- 最终 SIMT 写回 `[outer,D,inner]`，
           index 从 uint16 转 int64。" · "实现上可将比较对整理为 `constexpr TopKComparePair[]`，由
           固定编译期长度的 `for` 循环配合 `#pragma unroll` 展开；不要使用运行时生成的 pair 表或
           未展开的动态索引循环"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured D=17 TopK on a named 950 board where a dynamic insertion sort matches the
           fixed network's time within the run spread — the network's fixed structure would then not
           be what buys the performance, and the "不能期待相同性能" claim would be wrong.
```

# 0331 · A seventeen-element fixed sorting network is seventy-two compare-exchanges in eleven dependency layers

## 1 · Claim
Upstream asserts a special TopK path for very small non-last axes — `D = 7` or `17`, `k = D`,
fp16/bf16 — implemented as a fixed compare-exchange network vectorised along the `inner` dimension:
each axis value is a row, each compare-exchange operates on the whole `inner` segment in parallel,
and value and index rows must be swapped under one shared mask. Upstream asserts the network's size
for `D = 17`: 72 compare-exchanges in 11 dependency layers. Upstream asserts that substituting a
dynamic insertion sort should not be expected to reach the same performance. Upstream asserts four
correctness details: `largest` flips the comparison direction at run time so one network serves both
directions; NaN comparison and swapping must follow the interface semantics explicitly and must not
rely on the incidental behaviour of `>`/`<`; the tail `inner` tile writes only the valid width while
scratch and mask stay allocated at the aligned tile width; and the final SIMT write-back produces
`[outer, D, inner]` with indices converted from uint16 to int64. Upstream asserts an implementation
constraint: the comparison pairs go in a `constexpr TopKComparePair[]` walked by a compile-time-length
loop with `#pragma unroll`, and neither a runtime-generated pair table nor an unexpanded
dynamic-index loop is acceptable. Not established here.

## 2 · The wrong branch this removes
For 17 elements, an insertion sort is the obvious implementation and looks cheap. It is data
dependent — the number of swaps varies with the input — and this path's whole design is that the
work is *fixed*: 72 comparisons regardless of input, arranged in 11 layers so that comparisons
within a layer are independent and can issue together, and every comparison acting on a whole
`inner` segment at once. A data-dependent sort loses the vectorisation across `inner` (different
columns want different swap sequences) and loses the layer structure (each step depends on the
previous). Upstream states the conclusion and not the reason; the reason is why the entry carries
the layer count as well as the comparison count.

The second wrong branch is the pair table. Generating it at run time, or walking it with a dynamic
index, reintroduces exactly what the fixed network exists to remove — upstream's stated cost is
`额外的循环控制和 UB 地址计算`. `#pragma unroll` over a `constexpr` array is not a style preference
here; it is the mechanism.

The third is the shared swap mask. Value and index rows are two tensors that must permute
identically; computing the mask twice, or letting the index swap follow its own comparison, produces
correct-looking values with wrong indices — and a value-only comparison passes. This family's own
regression matrix requires fetching back through the returned indices for exactly this reason
(`0330` §5).

The fourth is NaN. `>` and `<` on NaN have an incidental answer, and a sorting network built on that
answer will produce *an* ordering, deterministically, that does not match the interface's specified
NaN placement. Upstream names it as a rule rather than describing the failure, which means the
failure is silent.

## 3 · Ground / Source
The layout and the network size, `templates/usage_guide.md:135-150`:

```
## 6. 固定 D=7/17 排序网络

### 6.1 UB 布局与并行方向

把每个 axis value 看成一行，沿 inner tileWidth 向量化：

values  [D, tileWidth] uint16 storage
indices [D, tileWidth] uint16
scratch value/index rows
compare mask + NaN mask

GM 以 axis 行搬入，index 行填 axis 编号。每个 compare-exchange 对整段 inner 列并行，value/index
必须使用同一个 swap mask。D=17 使用 72 次 compare-exchange、11 层依赖；不能换成动态插入排序后期待
相同性能。
```

The correctness rules, `:152-157`:

```
### 6.2 正确性细节

- `largest` 在运行时改变 compare 方向，不需要两套网络。
- NaN 比较与交换必须显式遵守接口语义，不能依赖普通 `>`/`<` 的偶然结果。
- 尾 inner tile 仅写有效 width；scratch 和 mask 仍按对齐 tileWidth 分配。
- 最终 SIMT 写回 `[outer,D,inner]`，index 从 uint16 转 int64。
```

The implementation constraint, `:159-161`:

```
实现上可将比较对整理为 `constexpr TopKComparePair[]`，由固定编译期长度的 `for` 循环配合
`#pragma unroll` 展开；不要使用运行时生成的 pair 表或未展开的动态索引循环，否则可能引入额外的
循环控制和 UB 地址计算。
```

### The shipped table, read and checked

The pair table is present in this tree, so §4 Arms 1 and 2 were performed here as a source read plus
a host-side computation. This is **not** a measurement of any machine — it is a re-derivation of
upstream's own text, of the same kind as the arithmetic checks in `0301` and `0307` — and it is
reported as such.

`reference/sort/templates/dav3510/op_kernel/arch35/top_k_kernel.cpp.template:174-201` holds two
`constexpr TopKComparePair network[]` literals, selected by `if constexpr (AXIS_LEN == 7)`, and its
own comment above the second reads:

```
// 72 compare-exchanges in 11 layers. Pairs in each source line are
// independent, reducing both instruction count and dependency depth.
```

Counted from the literal: the `AXIS_LEN == 17` table contains **72 pairs on 11 source lines** —
upstream's prose figures are exactly the shipped ones. Greedy layering (open a new layer when an
index repeats) also yields **11**, so the source-line grouping *is* the dependency structure for
this network, as the comment claims.

Checked by the zero-one principle — a comparator network sorts all inputs iff it sorts all binary
inputs — exhaustively over all 2¹⁷ = 131 072 binary vectors: the 17-element network **sorts
correctly**.

`D = 7`, which upstream never quantifies, is **16 pairs on 4 source lines**, and it too sorts
correctly under the exhaustive zero-one check over 2⁷ inputs (16 is the known minimum comparator
count for 7 inputs). But its four source lines are **not** independent — line 1 is
`{0,6}, {2,3}, {4,5}, {0,2}`, and index 0 appears twice in it — and greedy layering gives **6**
layers, not 4. So the comment's "pairs in each source line are independent" holds for the 17-element
table and does not hold for the 7-element one. That is a small, real discrepancy between a code
comment and the code beneath it, in the direction that would mislead a reader counting layers from
the formatting. Recorded in `harvest/standing/950-bp.md`; it does not affect correctness, which the
zero-one check settles independently of layout.

Note the storage: values and indices are both `uint16` in UB, and indices become int64 only at
write-back. So the whole network runs on 16-bit lanes — which is consistent with the path's fp16/bf16
restriction and is what makes 17 rows of `tileWidth` affordable in UB, but upstream does not connect
those and this entry does not either beyond recording both.

The gate: this is a **special** route, dispatched before the common keys (`0330`), and upstream's own
warning about special routes applies — `两者只在已 A/B 的条件下抢占 common/fallback，不要为追求某个
case 泛化到相邻 dtype 或输出比例` (`:118-119`).

Nothing here is measured. There is no timing for this path, for the insertion-sort alternative, or
for the unrolled-versus-dynamic pair table.

## 4 · Procedure
Proposed, runnable later on a named 950 board. Never run in this phase.

Arm 1 — the network itself, counted rather than believed. `[no-card]`, and **DONE** (§3): read the
shipped `TopKComparePair[]` out of `op_kernel/arch35/top_k_kernel.cpp.template`, count its entries,
and compute the dependency depth by layering (two comparisons are in the same layer iff they share
no index). Result: 72 pairs / 11 layers at `D = 17`; 16 pairs / 6 layers at `D = 7`.

Arm 2 — correctness of the network as an ordering. `[no-card]`, and **DONE** (§3). Exhaustive on the
structure, not the data: a comparator network sorts all inputs iff it sorts all binary inputs (the
zero-one principle), so 2¹⁷ vectors settle `D = 17` completely and 2⁷ settle `D = 7`. Both pass. A
network that failed this would be wrong for every dtype, and no amount of device work would show it
as clearly. Note what this does *not* cover: the network is correct as an abstract comparator
sequence; whether the kernel's `Select`-based swap implements a comparator faithfully — including
under NaN — is Arm 4's question and is untouched by this.

Arm 3 — the performance claim. Build the fixed network and a dynamic insertion sort over the same
UB layout, at `D = 17`, sweeping `inner` across the tile width and across a tail. Record kernel
time and, separately, the *variance across inputs*: the fixed network's time should be independent
of the data, the insertion sort's should not, and that difference is more diagnostic than the means.

Arm 4 — the two disclosed hazards, each as its own build. (a) index rows swapped under a
separately-computed mask instead of the shared one; the value comparison must pass and the
index fetch-back must fail. (b) NaN handled by bare `>`/`<`; compared against the interface's
specified NaN placement on an input containing NaNs in every position.

Arm 5 — the unrolling constraint. The same network with `#pragma unroll` and with a
dynamic-index loop over the same table, timed. Upstream asserts extra loop control and UB address
arithmetic; the scalar pipe share is the readout that would show it.

Variance floor first for Arms 3 and 5: one build, 30 in-process runs, 5 fresh-process runs, IQR over
median, and `0327`'s sibling check applied before any table is read. Device selection:
`npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing; bind only on three
idle samples; re-sample after; discard the case if the die moved. Refuses to assume: that the
shipped table matches upstream's stated counts (Arm 1 exists because it may not); that a correct
network on random data is a correct network (Arm 2 exists because it is not); that the tail `inner`
tile is exercised — the sweep includes a width that is not a multiple of the aligned tile width, by
construction.

## 5 · Checker — acceptance declared before the run
Verdict `pair_count` and `depth` from Arm 1. Declared before the read: upstream is **supported** iff
`pair_count == 72` and `depth == 11`. Any other pair is a finding about the shipped code, recorded
as such rather than reconciled with the prose.

Verdict `network_sound` = true iff Arm 2's zero-one test passes on all 2^17 binary inputs. Declared:
this is a *precondition*, not a result — if it fails, every later arm is void, because a wrong
network's timing is uninteresting.

Verdict `data_independence` = the ratio of time variance across inputs, fixed network against
insertion sort. Declared: the fixed network's variance should be at the floor. The OVERTURN fires
iff the insertion sort matches the fixed network's median within the floor at every swept `inner`.

Verdict `index_pairing_fails` and `nan_placement_fails` from Arm 4 — both **must** be true.

The exit code is not the verdict. Three guards.

First, Arm 4 is not an optional extra; it is where the checker is made able to go red. Both of its
builds are planted defects that the correctness apparatus must **find**. If (a) passes, the harness
is comparing values only and every green in the run is void for index correctness. If (b) passes,
the input contains no NaN where it matters and the NaN rule was never under test. A TopK checker
that reads only the returned values is the known blind species, and this family's own regression
matrix says so independently.

Second, Arm 2 runs on the host before any device work. It is exhaustive over structure and cheap,
and it is the only check in this entry that can be complete.

Third, `data_independence` is reported as a variance, not as a mean comparison. Upstream's claim is
about the *character* of the two implementations, and a mean-only comparison would miss a fixed
network that is slower on average but constant, which is a different and possibly preferable result.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No kernel was built, no
network was executed on a part, and no insertion sort was timed. Arms 3, 4 and 5 — every arm that
would need a device — are entirely unrun.

Two device-free arms **were** performed, and they are source analysis, not measurement. Arm 1: the
shipped `AXIS_LEN == 17` table holds 72 pairs on 11 source lines, and greedy layering confirms 11
dependency layers; the `AXIS_LEN == 7` table holds 16 pairs on 4 source lines with 6 dependency
layers. Arm 2: both tables sort correctly under the exhaustive zero-one check (2¹⁷ and 2⁷ binary
vectors respectively). These establish properties of upstream's *text*. They say nothing about
timing, nothing about the `Select`-based swap that realises each comparator on the device, nothing
about NaN behaviour, and nothing about any board — reading a table is not running a kernel.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The 72/11 figures **were** checked against the shipped
`TopKComparePair[]` and against the zero-one principle, and both hold — but that establishes only
that upstream's prose matches upstream's code and that the code is a valid comparator network. It
establishes nothing about the device: the network is realised by an `AscendC::Select`-based swap
under a shared mask, and whether that swap implements a comparator faithfully at any dtype, and what
it does with NaN, is untested here and is precisely where this path's disclosed hazards live. The
claim that a dynamic insertion sort cannot match the network is stated with no measurement on either
side. The `D = 7` figures (16 pairs, 6 layers) are this book's count, not upstream's — upstream never
quantifies that network — and the code comment's "pairs in each source line are independent" is true
of the 17-element table and false of the 7-element one.
The gate for this path (`non-last, D = 7/17, k = D, fp16/bf16`) is stated as a set of features and
its thresholds live in the sibling shelf (`0330` §7). Nothing establishes the interface's specified
NaN placement — upstream says to follow it and does not state it, so Arm 4(b) currently has no
reference to compare against, which is itself owed. The uint16 storage and the int64 write-back are
stated without a reason and this entry supplies none. BOARD is `family-claimed(unverified)`: the
document targets Ascend 950 / DAV_3510 and names no board. Nothing transfers to the other book
(RULES.md Art. 1).
