```
ID:        0029-a-tail-length-derived-by-subtraction-can-go-negative-and-write-out-of-bounds
LABEL:     trap
LEVEL:     L3 (data movement & layout)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/common/tail_block_design.md:181 — "若在别处用 `尾长 = 上界 − (n−1)·former` 而 `former` 来自**向上取整而非 CeilDiv 保证**……尾长会**取负**，末核仍按满 tile 写 → **越界写、踩踏相邻 GM**。症状隐蔽：**单跑 PASS、msprof 多 launch 累积成大量 mismatch**"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a kernel whose tail length is computed by the unguarded subtraction is shown to clamp or fault rather than write a full tile, on a named DAV_2201 board across launch counts.
```

# 0029 · A tail length derived by subtraction can go negative and write out of bounds

## 1 · Claim
Upstream asserts that computing a tail length as `upper_bound − (n−1) × former` is safe only when
`former` comes from a `CeilDiv` that guarantees `(n−1) × former ≤ upper_bound`; that where `former`
comes from some other rounding-up, the tail length goes negative, the last core still writes a full
tile, and the write goes out of bounds into adjacent GM. Upstream asserts the symptom signature
explicitly: a single run PASSES, and mismatches accumulate across many msprof launches. Not
established here.

## 2 · The wrong branch this removes
The subtraction is the natural formula and is correct in the case upstream itself ships — the same
page's `normBlockTailLoopSize = total − factor·(loop−1)` is safe, because `loop = CeilDiv(total,
factor)` forces the product below `total`. An agent that reads that line, understands it, and
reuses the *shape* of it somewhere `former` was rounded up for a different reason (alignment, bank
avoidance, a hardware granularity) has copied a formula out of the invariant that made it true.

What makes this a trap rather than an arithmetic slip is the detection signature. The tail length
is typically unsigned, so a negative value becomes enormous, or the code branches on
`isLastLoop` and writes `defaultUbFactor` regardless. The write lands in a neighbouring
allocation. On a single launch that neighbour may be untouched or may not be read, so the test is
green. Across many launches the corrupted region is reused and mismatches accumulate — which means
the standard validation (run once, compare) is structurally unable to see it, and the profiling run
that does surface it looks like a flaky measurement.

This is the same detection shape as 0019 (scalar/DCache incoherency): single run PASS, failure
accumulates. Two independent mechanisms with one signature is worth knowing as a signature.

## 3 · Ground / Source
`ops/ascendc-performance-best-practices/reference/common/tail_block_design.md` §6 注意事项, item 8,
line 181, verbatim in full:

"8. **⚠️ 末块长度别用无保证的减法反推（防取负→越界）**。本页 `normBlockTailLoopSize = total −
factor·(loop−1)` 因 `loop = CeilDiv(total, factor)` 恒为正、安全。但若在别处用 `尾长 = 上界 −
(n−1)·former` 而 `former` 来自**向上取整而非 CeilDiv 保证**（如 `(n−1)·former > 上界`），尾长会
**取负**，末核仍按满 tile 写 → **越界写、踩踏相邻 GM**。症状隐蔽：**单跑 PASS、msprof 多 launch
累积成大量 mismatch**（逐核 `[off,len)` 覆盖仿真 `oob>0`、`missing=0`）。稳妥做法：末块长度
**要么由 `CeilDiv` 保证为正，要么每核用全局区间 `[start, end)` 对总长 clamp、`len=min(tileLen,
end−off)`、`start≥总长`直接 return**。"

Three things upstream supplies that are rarer than the warning itself, and are why this entry is
worth its number: (a) the *invariant* that separates the safe use from the unsafe one, not just
"be careful"; (b) the detection signature, single-run-PASS versus multi-launch accumulation;
(c) a coverage-simulation check — per-core `[off, len)` intervals against the total, with `oob > 0`
and `missing = 0` as the diagnostic pair. That last is a host-side check needing no device, and it
is the basis of §4.

The safe form is on the same page, lines 158-161: `normBlockLoop_ = Ops::Base::CeilDiv(
normCoreHandleDefaultValues_, defaultUbFactor_); normBlockTailLoopSize_ =
normCoreHandleDefaultValues_ - defaultUbFactor_ * (normBlockLoop_ - 1);`.

## 4 · Procedure
Proposed, runnable later; not run. The first arm is host-side and needs no card, which is the
point — this defect is catchable before it reaches a device.

1. Coverage-simulation arm, no device: for the tiling function under test, enumerate every core's
   `[start, start + len)` over a sweep of total sizes (including sizes just above and just below
   each `former` multiple) and compute two counters — `oob`, the number of bytes any core would
   write beyond the total, and `missing`, the number of bytes no core covers. The safe condition
   is `oob == 0 && missing == 0`. Treat `len` as the signed value the tiling actually computes,
   not as the unsigned value it will become, or the negative case is invisible.
2. Device arm, on a named die (occupancy before and after, no substitution): allocate the output
   buffer inside a larger GM region whose surrounding bytes are poisoned to a known pattern, run
   the kernel for launch counts 1, 10, 100, 500, and after each check both the output AND the
   poison guard bands.
3. Report the launch index at which the first guard-band byte changes. That number is what tells a
   consuming team how long their own testing must run.

## 5 · Checker — acceptance declared before the run
`oob`, `missing` from arm 1; `guard_dirty(launches)` from arm 2.
PASS (tiling is safe) iff `oob == 0 && missing == 0` across the whole size sweep AND
`guard_dirty` stays zero at 500 launches.
The positive fixture, required and run first: feed arm 1 a deliberately broken tiling where
`former` is rounded up outside `CeilDiv`, and confirm it reports `oob > 0`. **A coverage simulator
that reports clean on a tiling known to be broken is the exact failure species this book tracks —
a check that reads only the lines it expects — and its clean verdicts on real tilings must be
discarded.** This gate runs before any real tiling is judged.
Note what the fixture must be: a POSITIVE the instrument must FIND, not a known-good tiling it must
pass. A selftest pinned to "the good tiling comes up clean" would satisfy a simulator that always
returns clean.
Arm 2's `guard_dirty == 0` at 500 launches does NOT establish safety — it establishes that this
tiling did not bite in 500 launches, and is recorded that way.
Exit code is not the verdict; an out-of-bounds write does not fault.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; no board touched; no architecture stated — this is a host-side tiling-arithmetic
hazard, and its routing to this book rests on the surrounding document's DAV_2201/DAV_3510 context
rather than on any hardware property. It plausibly applies to any Ascend part and this book claims
nothing about that. This entry does not establish that the out-of-bounds write actually corrupts a
*live* allocation — that depends on the allocator's layout, which no source in scope describes. It
does not establish the launch count at which the symptom appears; that is what §4 step 3 is for and
it will be workload-specific. It does not cover the multi-dimensional case, where each dimension
has its own tail and the interaction is not addressed by upstream.
