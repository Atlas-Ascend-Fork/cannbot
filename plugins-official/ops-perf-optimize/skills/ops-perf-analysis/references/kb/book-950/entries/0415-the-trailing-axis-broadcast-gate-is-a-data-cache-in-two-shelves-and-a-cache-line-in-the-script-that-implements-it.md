```
ID:        0415-the-trailing-axis-broadcast-gate-is-a-data-cache-in-two-shelves-and-a-cache-line-in-the-script-that-implements-it
LABEL:     trap
LEVEL:     L3 (data movement & layout)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/broadcast/broadcast_design.md:132 —
           "│  ├─ 尾轴非广播 且 存在非尾轴广播 且 尾轴字节 ≥ dcache/2(~4096B) → ③ UB-BRC (BigNLast)" ;
           ub_broadcast_design.md:17 — "- 或 BigNLast：非尾轴广播且尾轴字节 ≥ `nddma dcache/2`（源码注释 ~4096B）；" ;
           code/broadcast_add_tiling.cpp:63 — "dcache 阈值用平台查询，源码注释约 4096B。"
SOURCE:    ops/ascendc-tiling-design/references/broadcast/patterns.md:76 —
           "| 2 | NLast 场景，尾轴 >= dcache/2 | UB BRC → [dynamic-ub-broadcast.md] |"
           (same repo — contrast, not corroboration)
SOURCE:    ops/ascendc-perf-optimize/references/tiling/broadcast/fallback/script/
           broadcast_tiling.py:31,354 — "CACHE_LINE = 128          # bytes, OneDim alignment" ·
           "                return output_dims[last_axis] >= CACHE_LINE // 2"
           (same repo — contrast, not corroboration)
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a runtime query on a named 950 board returning an NDDMA data-cache size whose half equals
           64 bytes — the script's `CACHE_LINE // 2` would then be the same threshold as the
           documents' `dcache/2`, the two would not disagree, and this entry's claim of a
           substitution would be wrong.
```

# 0415 · The trailing-axis broadcast gate is a data cache in two shelves and a cache line in the script that implements it

## 1 · Claim
Upstream asserts, in three of its skills, one routing gate for broadcast: when the trailing axis is
not itself broadcast but some non-trailing axis is, a sufficiently large trailing axis selects the
UB-side Broadcast expansion rather than NDDMA, because NDDMA would re-read that axis and thrash a
cache. Upstream expresses the threshold three ways. The design shelf writes `尾轴 >= dcache/2` with no
value and no units. The implementation shelf writes `尾轴字节 ≥ dcache/2`, in **bytes**, glossing the
value as `~4096B` and attributing that gloss to a **source comment** rather than to a measurement or a
platform query; its own reference tiling code takes the threshold as a caller-supplied parameter and
repeats the same attribution. The analysis shelf's reference script implements the gate as
`output_dims[last_axis] >= CACHE_LINE // 2`, where `CACHE_LINE = 128` is declared, in that file, as
`bytes, OneDim alignment` — so the script compares an **element count** against half of a *cache line*.
Upstream nowhere reconciles the two constants, and no file in any of the three states a value for
`dcache`. Not established here.

## 2 · The wrong branch this removes
An agent reproducing this gate has three sources and they do not agree about what quantity is being
compared, let alone against what. Taking the script — the only executable artifact — it will emit a
gate that fires at a trailing axis of 64 elements. Taking the documents' gloss it will emit one that
fires at 4096 bytes, which at FP32 is 1024 elements. That is a factor of sixteen in the elements at
which a broadcast switches implementation, and the two also disagree on units: the script's left-hand
side is `output_dims[last_axis]`, a count, while every document says `尾轴字节`. A gate written from
the script fires sixteen to sixty-four times too early depending on dtype, and every broadcast whose
trailing axis lands between the two thresholds is routed to the wrong implementation — silently, since
both implementations are correct.

The second wrong branch is treating `~4096B` as the answer. It is not a measured value and the
documents do not claim it is: `源码注释 ~4096B` says a comment in some source said so, and
`dcache 阈值用平台查询` says the real value comes from a runtime query the family does not perform.
Its referent is also ambiguous in upstream's own text — `尾轴字节 ≥ dcache/2(~4096B)` can be read as
"dcache/2 is about 4096 B" (making dcache ≈ 8192 B) or as "dcache is about 4096 B" — and the three
sites are not consistent enough to settle it. So the honest state is: **the gate's threshold is a
runtime query nobody makes, glossed by a comment nobody cites, and implemented as a different constant
entirely.** The operational consequence is `0207`'s rule: query it, and if you cannot, do not ship a
literal in its place.

## 3 · Ground / Source
The implementation shelf's decision tree, `reference/broadcast/broadcast_design.md:132`:

```
      │  ├─ 尾轴非广播 且 存在非尾轴广播 且 尾轴字节 ≥ dcache/2(~4096B) → ③ UB-BRC (BigNLast)
```

and its branch table, `:30`, which states the same condition as one of three alternatives admitting the
UB path:

```
| ③ | [**UB 内 Broadcast 指令**](ub_broadcast_design.md) | UB 内 | `Broadcast<T,R>(dst,src,dstShape,srcShape,&tiling)` | Vector | **前提广播轴在 tile 内(brcInTile)**；且：尾轴对齐且 dtype∈{INT8,UINT8,FP16,BF16,INT16,UINT16}，或非尾轴广播且尾轴≥dcache/2（~4096B），或广播中间计算结果 |
```

Note that `:30` drops the `字节` qualifier that `:132` carries, so within one file the quantity is
"trailing axis" once and "trailing axis in bytes" once. The template's own document,
`ub_broadcast_design.md:17`, restores it and adds the provenance:

```
- 或 BigNLast：非尾轴广播且尾轴字节 ≥ `nddma dcache/2`（源码注释 ~4096B）；
```

`nddma dcache` — the cache is named as the NDDMA engine's, not the vector core's D-cache, which is a
fourth distinct object and the only place in these three skills where that distinction is drawn. And
the family's reference tiling code, `code/broadcast_add_tiling.cpp:63`:

```
// 「是否所有广播轴都在切分轴之上」，不能只看第一个广播轴。dcache 阈值用平台查询，源码注释约 4096B。
```

`用平台查询` — obtained by platform query — is the correct instruction and this book's standing rule
(`0207`, `0141`). The code then does not perform one: the threshold arrives as a function parameter
`nddmaDcache` supplied by the caller, and the gate reads
`if (f.nonLastBrc && !f.lastAxisBrc && lastDim * dtBytes >= nddmaDcache / 2) return BRC_UB;` — bytes on
the left, as the documents say. So the implementation shelf is internally consistent on units and
honest about the constant's absence.

The design shelf's version, `ascendc-tiling-design/references/broadcast/patterns.md:74-80`, in its
four-row priority chain:

```
| 优先级 | 条件 | 选择 |
|--------|------|------|
| 1 | 用户强制指定 NDDMA 或 UB BRC | 遵从 |
| 2 | NLast 场景，尾轴 >= dcache/2 | UB BRC → [dynamic-ub-broadcast.md] |
| 3 | dtype 为 INT8/FP16/BF16 且尾轴 32B 对齐 | UB BRC → [dynamic-ub-broadcast.md] |
| 4 | 其他 | NDDMA → [nddma-broadcast.md] |
```

with the rationale at `:80`:

```
**NLast** = 尾轴不需要广播（stride≠0），但非尾轴需要广播（stride=0）。尾轴数据量大时 NDDMA 反复读会刷 dcache，不如 UB 内 Broadcast API。
```

No units, no value, no query instruction. `dcache` appears nowhere else in the design shelf's broadcast
family. The analysis shelf carries the same chain (`tiling-flow.md:24`, carried at `0154`), also
without a value.

The script, `ascendc-perf-optimize/references/tiling/broadcast/fallback/script/broadcast_tiling.py`.
Its constant, `:31`:

```python
CACHE_LINE = 128          # bytes, OneDim alignment
```

and the gate, `:340-354`:

```python
def _check_nlast_ub_broadcast(
    output_dims: List[int],
    input_strides: List[List[int]],
) -> bool:
    """Check if non-last axis broadcast should route to dynamic_ub."""
    shape_len = len(output_dims)
    last_axis = shape_len - 1
    for inp_strides in input_strides:
        if inp_strides[last_axis] == 0:
            return False
    for ax in range(shape_len - 1):
        for inp_strides in input_strides:
            if inp_strides[ax] == 0 and output_dims[ax] > 1:
                return output_dims[last_axis] >= CACHE_LINE // 2
    return False
```

`grep -n dcache` over that whole subtree returns exactly one line — the markdown's `尾轴≥dcache/2` at
`tiling-flow.md:24` — and nothing in the script. So the substitution is not a rename: the word does
not appear in the executable artifact at all, and the constant that stands in its place is declared for
a different purpose (`OneDim alignment`) two hundred lines earlier.

Three divergences, and they are worth separating because they have different fixes:

1. **Constant.** `dcache/2` (unqueried, glossed ~4096 B) versus `CACHE_LINE // 2` = 64. If the gloss is
   right, these differ by 64×; the fix is to query.
2. **Units.** Every document says bytes; the script's left-hand side is `output_dims[last_axis]`, an
   element count. At FP32 that is a further 4× on top; the fix is a `* dtypeSize`.
3. **Object.** A data cache and a cache line are different things, and the implementation shelf
   further specifies *which* data cache (`nddma dcache`). The fix is to name the object before
   choosing its size.

Registered as `C-950td-019`. This book already carries a nearby figure that makes the confusion legible
and does not resolve it: `0148` records the analysis shelf's gather family stating `DCache` inline as
**128 KB**, in parentheses inside a template's condition — a third value, in a third family, for a
name that may or may not denote the same object. Recorded in `harvest/standing/950-td.md` as
`Q-950td-05`.

`0155` records that this script preserves the chip-generation branch while dropping every constraint
that branch carries. This entry adds that where the script does implement a constraint, it implements a
different one; the two findings together are why `0104`'s provenance rule matters more here than any
particular number.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and discard the case
if the die moved. Variance floor first: one build, 30 in-process runs, 5 fresh-process runs.

**Arm 1 — find the object, before measuring anything.** Search the installed toolkit (read-only) for a
platform-query API returning an NDDMA data-cache size, and for any declared constant of that name;
`GetCoreMemSize`'s enumeration is the obvious place, and `0141` records that upstream's own TopK path
queries capacities this way. Report the queried value, or report that no such query exists — which is
itself the answer to whether `用平台查询` is executable as written. This arm needs no device beyond the
query.

**Arm 2 — locate the real crossover.** Construct a `BigNLast` broadcast: trailing axis not broadcast,
one non-trailing axis broadcast, FP32. Sweep the trailing axis over
`{16, 32, 64, 128, 256, 512, 1024, 2048, 4096}` elements — a range that straddles the script's 64 and
the documents' 1024 (4096 B ÷ 4). At every point build both implementations from the family's own
files: NDDMA (`nddma_design.md`) and UB Broadcast (`ub_broadcast_design.md`). One compiler pin, two
md5s, host echo of the trailing axis in **both** elements and bytes, the branch taken, and the queried
cache size from arm 1. Elementwise comparison against a CPU reference on both arms. Record `aiv_time`
and MTE2 byte count, ≥10 iterations, first 5 dropped.

**Arm 3 — repeat at two more dtypes.** FP16 and INT8, same element sweep. If the crossover is a fixed
*byte* count it moves in elements across the three dtypes by 4× and 2×; if it is a fixed *element*
count it does not move. That single observation settles divergence 2 without needing to settle
divergence 1.

**Arm 4 — the cache-thrash mechanism.** The stated reason is that NDDMA re-reads the trailing axis and
flushes a cache (`patterns.md:80`). Above the crossover, record whether NDDMA's MTE2 byte count exceeds
the case's logical input size, and by how much — re-reading should show as inflation. If NDDMA moves
exactly the logical bytes at every point, the mechanism is not re-reading and the gate's rationale is
wrong even if its threshold is right.

Refuses to assume: that a free die stays free; that a die may be substituted; that `dcache` names a
real queryable object (arm 1 is what asks); that the trailing axis quantity is bytes or elements (both
are echoed at every point); that `~4096B` refers to `dcache` rather than to `dcache/2` (the ambiguity
is recorded and the sweep spans both readings); that either implementation is correct (elementwise
comparison on every point).

## 5 · Checker — acceptance declared before the run
Verdict `crossover(dtype)` = the trailing-axis size at which UB Broadcast's median `aiv_time` first
falls below NDDMA's by more than the variance floor, reported in **both** elements and bytes.

Declared before the run: the script's gate is **supported** iff `crossover(FP32) ∈ [32, 128]` elements;
the documents' gloss is **supported** iff `crossover(FP32) × 4 ∈ [2048, 8192]` bytes. These are
disjoint by construction, so at most one can pass and both can fail. The OVERTURN fires iff arm 1
returns a queried cache size whose half is 64 bytes — the two thresholds would coincide and there would
be no substitution to report.

Verdict `unit_is_bytes` from arm 3: true iff `crossover` in bytes is constant across FP32/FP16/INT8
within the floor, false iff `crossover` in elements is constant instead. Exactly one should hold; both
holding is impossible and neither holding means the crossover depends on something else and the gate's
whole form is wrong.

Verdict `nddma_reread` from arm 4 = NDDMA's MTE2 bytes divided by the case's logical input bytes, above
the crossover.

The exit code is not the verdict: both broadcast implementations return full correct buffers on either
side of any threshold, which is exactly why a mis-set gate is invisible. Three guards. First, every
point on both arms is compared elementwise against a CPU reference and the checker fails red if any
comparison did not execute — `0416` records that one of these two implementations produces NaN when
mis-selected, so a silent wrong answer is a live possibility here and not a formality. Second, **the
input that makes this checker go red**: the sweep includes a case where the trailing axis *is* itself
broadcast, which `_check_nlast_ub_broadcast`'s first loop must reject outright (`return False`). If
that case produces a `BigNLast` routing, the harness is not evaluating the real gate and every
crossover in the sweep is void — a threshold study whose only outcome is "we found a crossover" cannot
distinguish the gate under test from any other monotone effect. Third, no point is reported without its
floor, its two md5s, and the trailing axis echoed in both units; a point missing the dual echo cannot
contribute to `unit_is_bytes`, which is the verdict that needs it.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The three formulations and the
`grep` result showing `dcache` absent from the script's subtree are file reads performed at drafting
time. The arithmetic in §2 — 4096 B ÷ 4 = 1024 elements at FP32, against the script's 64, giving 16× —
is done here on paper from upstream's own gloss, and that gloss is upstream's report of a comment in a
source file this tree does not contain.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The entry does not establish a value for `dcache`, for
`nddma dcache`, or for any cache line on any board; it establishes that three upstream artifacts state
one gate three ways and that the only executable one uses a constant declared for another purpose. It
does not establish that the script is wrong — the script may be a deliberate simplification, and §5
declares the observation that would show the two thresholds coincide. It does not establish that
`dcache` in this family denotes the same object as the `DCache` figure `0148` records in the gather
family (`Q-950td-05` records that as open), nor whether `nddma dcache` is distinct from a vector-core
D-cache. It does not resolve whether `~4096B` glosses `dcache` or `dcache/2`; the sweep spans both and
the entry states the ambiguity rather than picking. It does not establish the cache-thrash rationale
(arm 4). It does not cover the other two conditions admitting the UB path (dtype-plus-alignment, and
broadcasting an intermediate result), nor the NaN hazard attached to that path (`0416`), nor the
family's four-branch selection as a whole (`0154`). No board token appears in the design or analysis
shelves' broadcast families; the implementation shelf's `broadcast_design.md:6` scopes itself to
`DAV_3510（A5 / Ascend950，C310）`, which names an architecture and a family and includes a token —
`C310` — that appears in no upstream mapping table (`0203`, `C-950bp-011`). BOARD is therefore
`family-claimed(unverified)`. Nothing here is established for any 910-family board.
