```
ID:        0044-reuse-a-ub-buffer-instead-of-detouring-through-gm-to-zero-or-stage
LABEL:     knowledge
LEVEL:     L2 (memory hierarchy & residency)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/single-core-pipeline/techniques/mem-04-ub-buffer-reuse.md:14 — "关键是生命周期分析：复用仅在前一数据已被最后一次消费且不同步访问时安全；否则必须保留独立 buffer 与事件边界"
           ops/ascendc-perf-optimize/references/single-core-pipeline/techniques/mem-04-ub-buffer-reuse.md:31 — "host tiling 需要把复用后的峰值 UB 用量而不是各逻辑 buffer 的静态和写入预算"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a paired build on a named 950 board where replacing a GM zeroing detour with in-UB
           initialisation does not reduce `aiv_time` or GM traffic beyond spread — the detour
           would then be free, and the card's premise wrong for that operator.
```

# 0044 · Reuse a UB buffer instead of detouring through GM to zero or stage

## 1 · Claim
Upstream asserts (card mem-04, evidence: four named arch35 commits, no numbers) that a temporary
consumed later on the same core should stay in UB — reusing an already-released buffer or being
initialised in place — rather than being written to GM and read back for zeroing, staging or a
format transition; that the enabling condition is lifetime analysis, reuse being safe only when
the previous data has had its last consumption and there is no concurrent access; and that the
host tiling budget must use the *peak* UB after reuse, not the static sum of logical buffers. Not
established here.

## 2 · The wrong branch this removes
A GM detour for zeroing is a natural idiom: a zero-filled region is easy to produce on the host or
with a fill kernel, and reading it back is one copy. Its cost is two GM traversals of data that
never had to exist. Similarly, giving each temporary its own UB buffer for the whole kernel is the
safe default, and it inflates the static budget, which forces smaller tiles, which multiplies
per-tile fixed cost (0017) — a chain in which the real cause is three steps from the symptom.

The wrong branch inside the repair is aliasing by type: two `LocalTensor`s of the same dtype and
length are not interchangeable. The card's stop rule states the condition as a proof obligation —
`CanAlias` is derived from lifetime, events and physical layout, not from a matching declaration.

## 3 · Ground / Source
`mem-04:6-10` diagnostic: adjacent stages writing GM and immediately reading it back, or a separate
GM area opened purely for zeroing, staging or scale/metadata preparation; several temporaries with
non-overlapping lifetimes each holding UB permanently, forcing smaller tiles or extra copies;
short-lived GM read/write pairs, useless buffer initialisation, or synchronisation exceeding the
real result write-back in the trace.

`mem-04:19-29` before/after: `FillGm(tmpGm, 0, bytes); CopyIn(tmpUb, tmpGm, bytes); Consume(tmpUb);`
becomes `LocalTensor<T> tmpUb = AcquireOrAliasUb(CanAlias(prevUb, nextStage)); Duplicate(tmpUb,
static_cast<T>(0), elems); Consume(tmpUb);`, with the comment that `CanAlias` is proved by
lifetime, events and physical layout and is not a pointer reuse. `mem-04:31` adds that overlapping
stages should become ping-pong or ring buffers with the production, consumption and release events
recorded explicitly per buffer.

Stop rules, `mem-04:39-42`: the previous consumer must have finished reading; dtype, length,
alignment, offset and initialisation semantics must be compatible and a tail may not borrow
uninitialised space; zeroing only in UB is not equivalent to preserving GM output semantics —
anything externally visible or read by a later core must still be written back; and if reuse
shrinks the tile, adds synchronisation or breaks double-buffered overlap, decide by measured peak
throughput.

Evidence, `mem-04:35`: record GM read/write bytes, MTE issue count, peak UB and `aiv_time`, with
the buffer-lifetime cases (adjacent, partially overlapping, fully parallel) verified separately —
no values given. Commits at `:46`: LightningIndexer UB reuse and temporary-buffer shrinking,
FlashAttentionScoreGrad UB zeroing replacing GM zeroing, QBSA dead-buffer cleanup with `qscale`
reuse.

## 4 · Procedure
Later phase, needs a card; device selection per 0010, board token from the driver readout.
1. Build one operator three ways from a common tree: (G) GM zeroing detour plus per-temporary UB
   buffers; (U) in-UB `Duplicate` zeroing, buffers still separate; (R) in-UB zeroing plus reuse of
   a released buffer for a later non-overlapping temporary. Record `md5sum` of each.
2. Capture `aiv_time`, `aiv_mte2_ratio`, `aiv_mte3_ratio`, GM bytes if a counter is available, and
   peak UB; five repetitions, median and spread.
3. Sweep tile size so that the peak-UB difference between (U) and (R) translates into a different
   admissible tile, and record the tile each build could reach.
4. Build a fourth variant (R') that aliases two buffers whose lifetimes *do* overlap, and run the
   same correctness comparison.

## 5 · Checker — acceptance declared before the run
Verdict variables `gain`, `gm_bytes(build)`, `ub_peak(build)`, `max_tile(build)`, `correct(build)`.
Acceptance: `gm_bytes(U) < gm_bytes(G)` by the size of the zeroed region; `ub_peak(R) < ub_peak(U)`;
`max_tile(R) >= max_tile(U)`; and `gain` positive beyond spread. A time gain with unchanged GM
bytes did not come from removing the detour.

Exit code is not the verdict. Correctness is element-wise on all outputs, including any GM region
whose semantics the card warns about — a build that stopped writing an externally visible zeroed
region would otherwise look like a pure win.

Red input: variant R', the overlapping alias. It must fail. If it passes, the schedule never
interleaved the two consumers and the reuse result carries no safety information.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured, by us or upstream. No board, shape or operator family. It does not establish how
`CanAlias` should be computed — the card states the obligation and leaves the mechanism to the
implementation. It says nothing about cross-core visibility rules, which it explicitly defers to
"the agreed write-back", nor about L1/L0 buffers, which have different residency semantics.
