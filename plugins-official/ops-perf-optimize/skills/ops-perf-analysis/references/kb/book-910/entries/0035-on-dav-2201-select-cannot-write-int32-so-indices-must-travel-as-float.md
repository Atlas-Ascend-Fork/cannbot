```
ID:        0035-on-dav-2201-select-cannot-write-int32-so-indices-must-travel-as-float
LABEL:     trap
LEVEL:     L5 (compute & numerics)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-tiling-design/references/reduction/with-index.md:110 — "| **Select dst 类型** | DAV_2201 仅支持 half/float，**不支持 int32** | 索引必须用 float 存储，输出前 Cast 为 int32 |"; ibid:29 — "| **Select 8K 预留** | DAV_2201 上模式 1/2 需预留 8K UB，框架通常自动管理 |"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a `Select` with an int32 destination compiles and produces correct results on a named DAV_2201 board.
```

# 0035 · On DAV_2201, Select cannot write int32, so indices must travel as float

## 1 · Claim
Upstream asserts that on DAV_2201 the `Select` API supports only `half` and `float` destination
types and does not support int32, so index values must be held as float through the selection and
cast to int32 only at output. Upstream separately asserts that on DAV_2201, Select modes 1 and 2
require an 8 KB UB reservation, usually managed by the framework. Not established here.

## 2 · The wrong branch this removes
Any argmax-shaped operator — ArgMax, ArgMin, TopK with indices, a reduction carrying positions —
wants to select between candidate indices, and indices are integers. The obvious implementation
selects on an int32 tensor. On DAV_2201 that is unavailable, and the workaround is not a
rewrite but a representation change: carry the index as float, cast at the end.

The workaround has a numerical consequence upstream does not state and this entry must:
float32 represents integers exactly only up to 2²⁴. An index above 16 777 216 — a tensor with more
than 16 M elements along the reduced axis, which is not exotic — is not exactly representable, and
the cast back to int32 returns a neighbouring value. The failure is silent, correct for every small
test, and wrong only at scale. The related precision boundary is documented upstream for a
different API (0046 records half's exact-integer limit of 2048 and float32's of 2²⁴ from the A2
sort guide), so the number is available; the connection to Select-based indexing is drawn here.

The 8 KB reservation is a second, quieter branch: a tiling that budgets UB to the byte (0003) and
then uses Select modes 1 or 2 is 8 KB over, with no line in its own arithmetic to point at.

## 3 · Ground / Source
`ops/ascendc-tiling-design/references/reduction/with-index.md`, the API constraint table §"API 约束
（DAV_2201）" at line 106, with line 110 verbatim:
```
| **Select dst 类型** | DAV_2201 仅支持 half/float，**不支持 int32** | 索引必须用 float 存储，输出前 Cast 为 int32 |
```
Restated in the same file's summary table at line 24: "| **索引类型** | DAV_2201 上 Select 不支持
int32 dst，索引必须用 float 存储，最后 Cast 为 int32 |".

The reservation, line 29: "| **Select 8K 预留** | DAV_2201 上模式 1/2 需预留 8K UB，框架通常自动
管理 |" — note 通常 ("usually"), so the framework's management is not guaranteed and a hand-rolled
path may need to budget it explicitly.

Same constraint reaching the buffer-planning layer,
`ops/ascendc-tiling-design/references/reduction/multi-output-buffer.md:74`: "注意: DAV_2201 上
Select 不支持 int32 dst → 下标存为 float，最后 Cast 为 int32".

This is one of the few places in the sources surveyed for this book where a DAV_2201 constraint is
stated *by name and per-architecture* rather than as an unscoped rule — the file is part of
`ascendc-tiling-design`, which the structural survey identifies as one of the dual-architecture
skills that keeps its two families in separate table columns.

The 2²⁴ exact-integer limit for float32 is from
`ops/ascendc-performance-best-practices/reference/sort/radix_sort.md:243` ("float32 ReduceSum
精确到 2^24（16M）"), quoted here as the source of the number in §2 — an A2-scoped document, so
family-consistent, but making a claim about a different API. The inference that it bounds
Select-carried indices is this entry's, not upstream's.

## 4 · Procedure
Proposed, runnable later; not run.

1. Compile arm, no device needed beyond a cross-compile: attempt `Select` with an int32 destination
   targeting `__NPU_ARCH__` 2201 and record whether it compiles. A compile failure establishes the
   claim at the level it is about, and needs no card. If it compiles, the device arm decides.
2. Device arm, on a named die (occupancy before and after, no substitution): if step 1 compiles,
   run it against a host reference and check correctness.
3. Precision arm, which tests this entry's own inference rather than upstream's claim: run the
   float-carried index path with index values spanning 2²³ to 2²⁵ and compare the cast-back int32
   against the true index. Predicted: exact below 2²⁴, drifting above.
4. Reservation arm: measure peak UB occupancy with and without a Select in modes 1 and 2, via the
   largest tile that still launches (the method of 0022 §4), and check for an 8 KB step.

## 5 · Checker — acceptance declared before the run
`select_int32`: PASS (claim upheld) iff the int32 destination fails to compile, OR compiles and
produces mismatches. A clean compile-and-correct result overturns.
`index_exact_to`: the largest index that survives the float round-trip exactly. PASS for the
inference in §2 iff it is 2²⁴. This verdict is reported separately and is labelled as testing this
book's inference, not upstream's assertion — so that a failure here corrects §2 without touching
§1, and a success is not credited to upstream.
`ub_step`: PASS iff the peak-occupancy difference is within 1 KB of 8192.
The positive fixture for arm 3: include an index of exactly 2²⁴ + 1, which the inference says must
fail. If the round-trip is exact there too, the 2²⁴ boundary is wrong and the arm has found
something rather than confirmed nothing.
Exit code is not the verdict, except in arm 1 where a compiler exit code IS the observation — and
that exception is stated here rather than assumed.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; no board touched. The source names DAV_2201 as an architecture, not a board, so
BOARD is `family-claimed(unverified)` and no individual part is established. This entry does not
establish which Select modes exist or what modes 1 and 2 are — upstream references them without
defining them here. The 2²⁴ index limit in §2 is an inference joining two upstream facts about
different APIs and is explicitly not established; §4 arm 3 is what would settle it. It does not
establish whether the int32 restriction extends to `Select`'s source types or only its destination.
It says nothing about DAV_3510, where upstream implies the restriction does not apply.
