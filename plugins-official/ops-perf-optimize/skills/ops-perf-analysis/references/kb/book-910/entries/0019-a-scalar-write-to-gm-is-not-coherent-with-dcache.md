```
ID:        0019-a-scalar-write-to-gm-is-not-coherent-with-dcache
LABEL:     trap
LEVEL:     L4 (synchronisation)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-analysis/references/metrics_reference.md:413 — "| Scalar 写 GM | DCache 与 GM 不保证一致性 | 使用 `DataCacheCleanAndInvalid` |"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a scalar write to GM followed by a read from another unit, without `DataCacheCleanAndInvalid`, is shown to be reliably visible on a named DAV_2201 board across shapes and repeat counts.
```

# 0019 · A scalar write to GM is not coherent with DCache

## 1 · Claim
Upstream asserts that coherency between the scalar data cache and Global Memory is not guaranteed
when the scalar unit writes GM, and that `DataCacheCleanAndInvalid` is the remedy. Upstream
separately asserts, in an A2-scoped hardware table, that the scalar→UB→DMA path is cache-incoherent
and that batching scalar output through a DMA write is therefore not viable. Not established here.

## 2 · The wrong branch this removes
An agent implementing a sparse or data-dependent output — TopK indices, NonZero positions,
MaskedSelect results — writes them one at a time with scalar `SetValue`, notices the per-element
cost, and reaches for the obvious optimisation: accumulate into a UB staging buffer and issue one
DMA at the end. Upstream says that path does not work on this family because of the same
incoherency. The agent's test then passes anyway, because the failure is timing- and
capacity-dependent: with a small case the cache may happen to be written back, and a single run is
clean.

That is the shape that makes this a trap rather than knowledge — it is the same signature as 0029:
single run PASS, failure accumulates across launches. An agent that validates with one launch has
no way to see it, and the validation is not obviously inadequate.

## 3 · Ground / Source
`ops/ascendc-performance-analysis/references/metrics_reference.md` §7 硬件约束速查表, line 413:
```
| Scalar 写 GM | DCache 与 GM 不保证一致性 | 使用 `DataCacheCleanAndInvalid` |
```
The remedy names a specific API, which is the strongest part of the claim — an incoherency
statement with no clean-and-invalidate call would be much harder to act on.

The A2-scoped statement of the same mechanism,
`ops/ascendc-performance-best-practices/reference/sort/radix_sort.md:307`, inside a table headed
"6.1 A2 硬件特性速查":
```
| scalar → UB → DMA | cache 不一致 | batch DMA 写出不可行 |
```
Same repo, so one origin (RULES.md Art. 3), but a materially stronger scoping: that document declares
itself A2-verified (see 0047), where metrics_reference's §7 table carries no architecture at all.
This is the reverse of the usual situation in this book — here the *practice* document is better
scoped than the *reference* document.

The same A2 table, lines 305-306, gives the two adjacent scalar facts that make the batching
temptation concrete: "| `xGm_.GetValue` | 非阻塞流水线读 | 不可替换为同步计算 |" and
"| `SetValue` | 阻塞写 | 是标量输出的真实瓶颈 |" — carried by 0048. The blocking write is why an
agent wants to batch, and the incoherency is why it cannot.

## 4 · Procedure
Proposed, runnable later; not run. The claim is about an absence of a guarantee, which cannot be
proven by a passing run — so the procedure is built to make the failure appear, not to confirm the
happy path.

1. Name the die; occupancy before and after; no substitution.
2. Arm N (no barrier): a kernel where the scalar unit writes a known pattern to GM and a second
   consumer — another core, or a subsequent MTE2 read — reads it back, with no
   `DataCacheCleanAndInvalid` between. Vary the write count over 1, 16, 1024, 65536 and the number
   of launches over 1, 10, 200.
3. Arm C (with the call): identical source with `DataCacheCleanAndInvalid` inserted, md5-confirmed
   to be the only difference.
4. Verify every element, not a checksum: a checksum over a mostly-correct buffer can pass by
   coincidence and is a check that reads only what it expects. Report the count and the positions
   of mismatches.
5. Report the launch index of the first mismatch. If mismatches only appear after launch 40, that
   number is the most useful thing the run produces — it tells a consuming agent how long its own
   testing must be to see this.

## 5 · Checker — acceptance declared before the run
Verdict variable `mismatch_count_N` per (write count, launch count) cell, and `mismatch_count_C`
for the same cells.
The claim is upheld iff some cell has `mismatch_count_N > 0` while `mismatch_count_C == 0` in
every cell.
An all-zero `mismatch_count_N` across every cell does NOT establish coherency and is recorded as
"did not bite, retained" — the claim is about the absence of a *guarantee*, and no finite run can
establish a guarantee's presence. This asymmetry is declared here, before the run, so that a clean
sweep cannot later be narrated as an overturn. The OVERTURN line in the header is deliberately
demanding for the same reason: it asks for reliable visibility across shapes and repeat counts,
not for one clean run.
The positive fixture this checker must find: seed arm N with a deliberate un-flushed write in a
case known to be large enough, and confirm the verification loop reports it. If the loop reports
zero on a buffer that was never written at all, the loop is broken.
Exit code is not the verdict.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; no board touched. This entry does not establish when the incoherency manifests —
that is exactly what §4 is built to find out and cannot be inferred. It does not establish the cost
of `DataCacheCleanAndInvalid`, which matters because the remedy may be expensive enough to change
the design; no source in scope quantifies it. It does not establish the direction: whether the
problem is stale data in the cache, un-flushed writes, or both. The A2 attribution attaches to the
scalar→UB→DMA statement only; the `DataCacheCleanAndInvalid` row carries no architecture.
