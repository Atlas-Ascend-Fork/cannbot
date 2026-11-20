```
ID:        0028-a-kept-store-to-load-round-trip-without-localmembar-returns-maxabserr-inf
LABEL:     trap
LEVEL:     L4 (synchronisation)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/single-core-pipeline/techniques/vec-05-eliminate-ub-staging.md:70 — "**确需经 UB 中转**（如跨趟缓存、寄存器放不下）才保留往返，且 `store→broadcast-load` 之间**必须**加 `LocalMemBar<VEC_STORE,VEC_LOAD>`，否则实测 `maxAbsErr=inf`"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a build on a named 950 board with the store→broadcast-load round trip retained and the
           `LocalMemBar` removed whose output is bit-exact against the barriered build across a
           shape set that includes narrow tails — the hazard would then not be reachable, at
           least at that toolkit pin, and the "必须" would be over-stated.
```

# 0028 · A kept store-to-load round trip without LocalMemBar returns maxAbsErr = inf

## 1 · Claim
Upstream asserts that when a UB round trip is genuinely necessary — cross-pass caching, or values
that will not fit in registers — the round trip may be kept, but a
`LocalMemBar<VEC_STORE, VEC_LOAD>` between the vector store and the broadcast load is mandatory,
and that omitting it was measured to produce `maxAbsErr = inf`. Not established here: the readout
is upstream's, reported without a case identity, shape, board or build.

## 2 · The wrong branch this removes
This is the failure mode of a *correct* optimisation applied one step too far. An agent removing
UB staging (0027) will encounter round trips it cannot remove, and — having just learned that the
barriers around them are pipeline drains worth deleting — will delete the barrier while keeping
the round trip. The result is not slow, and it is not obviously wrong: the load may read the
correct value most of the time, and the failure appears as an infinity in a precision report,
which reads like a numerical instability in the algorithm rather than a missing memory barrier.
An agent debugging it will look at the mathematics.

The companion trap is the inverse and is why this entry is separate from 0027: keeping the
barrier while removing the round trip is pointless but harmless, whereas keeping the round trip
while removing the barrier is silent corruption. The two changes must move together and in only
one direction.

## 3 · Ground / Source
`vec-05:66-70`, the card's stop rules, third bullet in full:

> - 改法 B：`Reduce` 结果在 lane0，必须 `Duplicate(dst,dst,mask)` 广播后才能逐元素用。
>   **确需经 UB 中转**（如跨趟缓存、寄存器放不下）才保留往返，且 `store→broadcast-load` 之间
>   **必须**加 `LocalMemBar<VEC_STORE,VEC_LOAD>`，否则实测 `maxAbsErr=inf`。本仓 CANN
>   （cann-9.0.0-beta.2）`LocalMemBar`/`MemType` 在 `AscendC::Reg` 命名空间。

The before-form the barrier belongs to is at `vec-05:26-30` (store with
`StoreDist::DIST_FIRST_ELEMENT_B32`, barrier, load with `LoadDist::DIST_BRC_B32`). The card's
whole point is that the after-form makes the barrier unnecessary by removing the round trip; this
stop rule governs the case where that is impossible.

Note what kind of statement `maxAbsErr=inf` is: 实测 marks it as observed, but the card's own
性能数据 section says 待实测, so the observation is a correctness failure someone hit, not a
recorded experiment — no board, no shape, no dtype, no build. It is carried here because a
reported infinity is a strong signal and because the repair is cheap and specific.

The barrier's own semantics — which pipeline it drains and what it orders — are documented in a
neighbouring skill of the same repo (`ascendc-regbase-best-practice`), whose statements about
`PipeBarrier<PIPE_V>` on this architecture conflict with this library's (entry 0259). Whether
`LocalMemBar` is subject to the same disagreement is not stated anywhere and is left open here.

## 4 · Procedure
Later phase, needs a card. This is a correctness experiment; timing is secondary and reported
only so that the cost of the barrier is known.
1. Device selection per 0010: explicit visible-devices, occupancy either side, board token from
   the driver readout.
2. Build one row-reduction kernel that genuinely requires the round trip (force it by sizing the
   cross-pass cache beyond the register budget) two ways: (M) with
   `LocalMemBar<VEC_STORE, VEC_LOAD>` between store and broadcast-load; (N) without. Change
   nothing else; record `md5sum` of both objects and confirm the disassembly differs by the
   barrier only.
3. Run both over a shape set of at least twelve shapes, including narrow tails, row lengths that
   are not multiples of a VL, and at least one shape with a single row.
4. Compare outputs element-by-element against a CPU reference; record `maxAbsErr` per shape for
   each build, plus `aiv_time` median and spread.

## 5 · Checker — acceptance declared before the run
Verdict variable `hazard_reachable` = `∃ shape : maxAbsErr(N, shape) > tolerance`, with tolerance
being the dtype's relative threshold from 0021, declared before the run. The upstream claim is
supported iff `hazard_reachable` is true and `maxAbsErr(M, shape)` is within tolerance for every
shape. Secondary verdict `barrier_cost` = the `aiv_time` difference between M and N, reported
whether or not the hazard fires.

The exit code is not the verdict, and a NaN or an infinity must not crash the comparison — the
comparator handles non-finite values explicitly and reports them as themselves, because the
claimed symptom *is* a non-finite value and a harness that aborts on one would destroy the datum.

Red input: build M. It must come out clean across the whole shape set. If M also produces
infinities, the fault is elsewhere — in the kernel, the reference, or the comparator — and the
run is reported `control_arm_dirty` rather than as confirmation. A checker pinned only to "N must
be dirty" would happily accept a broken harness that dirties everything.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured by us; upstream's `maxAbsErr=inf` has no case identity, so it does not establish
under which shapes, dtypes, or toolkit the hazard fires — only that someone saw it. It does not
establish that the barrier is sufficient, only that it was necessary in that instance. It says
nothing about other store→load pairings inside a VF (register→UB→MTE3, or UB→UB), about the
`PIPE_V` barrier family (0259), or about whether auto-sync affects `LocalMemBar` at all. No board
token is established, and the namespace note is specific to one toolkit pin.
