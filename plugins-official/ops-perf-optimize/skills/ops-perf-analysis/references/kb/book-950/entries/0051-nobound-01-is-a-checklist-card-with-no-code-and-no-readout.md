```
ID:        0051-nobound-01-is-a-checklist-card-with-no-code-and-no-readout
LABEL:     boundary
LEVEL:     L9 (performance)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/single-core-pipeline/techniques/nobound-01-nobound.md:6 — "**占位卡**：手段清单已整理，`before/after` 代码与 msprof 实测数据**待增量补**。诊断特征见 `../no-bound.md`"
           ops/ascendc-perf-optimize/references/single-core-pipeline/techniques/nobound-01-nobound.md:31 — "**待增量补**：需采 msprof `aiv_time` + 各泳道 overlap 度前后对比（重点看 DoubleBuffer 是否生效，见 `../metrics.md` §3）"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a revision in which any of the six measures carries a before/after pair and an
           `aiv_time` readout with case identity; or a measurement showing that UnitFlag
           substitution or Preload sizing changes `aiv_time` in the direction the table's effect
           column asserts, which would convert one row from expectation to evidence.
```

# 0051 · nobound-01 is a checklist card with no code and no readout

## 1 · Claim
Upstream asserts a no-bound technique card listing six measures — enable PingPong/DoubleBuffer;
replace explicit barriers with UnitFlag for MMAD→Fixp; reduce the per-round transfer volume;
Preload the next batch before the current computation finishes and size the Preload window to the
compute duration; issue movement and compute instructions before the previous step has fully
completed; and use Vec fusion to remove repeated transfers — and upstream asserts, in the card's own
header and evidence section, that its before/after code and msprof data are outstanding. Not
established here; there is nothing to establish.

## 2 · The wrong branch this removes
The no-bound branch is the one an agent reaches when nothing looks wrong (0007, 0008), so it is
where an agent is least able to invent a next step and most likely to take whatever the card
offers. This card offers six measures without a worked example, and one of them — enabling
DoubleBuffer — is precisely the state the neighbouring measured card treats as its *precondition*
rather than its remedy (0052 begins from "DB is on and still not overlapping"). An agent that works
down the list in order will enable something already enabled and report it as the optimisation.

The card's own cross-reference, `nobound-01:8`, is the correction and is easy to miss: if the
diagnosis points to stage ordering, go to nobound-02 first, because this card fills bubbles within
a given order while nobound-02 changes the order.

## 3 · Ground / Source
`nobound-01:1-8`, the header, the placeholder note quoted in SOURCE, and the routing note to
nobound-02. `nobound-01:12` gives the diagnostic condition — all units at low utilisation, no single
bottleneck, throughput below expectation, bubbles and waits in the trace, insufficient
movement/compute overlap. `nobound-01:16` states the mechanism in one sentence: no-bound is usually
a scheduling problem — transfers not overlapped with compute, too many synchronisation points,
bubbles unfilled. `nobound-01:20-27` is the six-row measures table, including the PingPong row's
condition 控制每次搬移量使计算时间 ≥ 搬移时间 and the UnitFlag row's MMAD→Fixp 用 UnitFlag 同步替
显式 Barrier. `nobound-01:31` is the evidence line quoted in SOURCE.

Stop rules, `nobound-01:35-37`: PingPong halves the usable UB (entry 0018, and corrected as to
mechanism by 0019); an over-large Preload window can overflow UB and must match the compute
duration; and a bubble caused by a reduction dependency chain is not a no-bound case at all but a
VEC dependency, handled by vec-08 (0031).

`INDEX.md:35` marks the card 占位. `no-bound.md:27` routes 搬算未重叠 / 同步过多 / Preload /
提早发射 / PingPong to it. The measured content of the no-bound branch is entirely in nobound-02
(0052).

## 4 · Procedure
Artifact-level; no device is implicated by the absence claim.
```bash
UP=upstream/skills-dev-main/ops/ascendc-perf-optimize
sha256sum $UP/references/single-core-pipeline/techniques/nobound-01-nobound.md
  # 53a8d7d553fcf508ba9f74a7661a828fd8951c07ddf00fb11fb5652980e1ecfa
grep -c "```" $UP/references/single-core-pipeline/techniques/nobound-01-nobound.md   # expect 0
grep -n "待增量补\|占位" $UP/references/single-core-pipeline/techniques/nobound-01-nobound.md
```
To close the gap rather than record it: the UnitFlag row is the most testable of the six and needs
a Cube-bearing operator — build one kernel with an explicit barrier between MMAD and Fixp and one
with UnitFlag synchronisation, on a named 950 board, device selected per 0010, and compare
`aiv_time` and correctness. That is new work.

## 5 · Checker — acceptance declared before the run
Verdict variable `card_is_placeholder`, as in 0050: zero fenced code blocks, zero numeric readouts,
placeholder marker present. Expected true at the pinned blob.

Exit code is not the verdict; `grep -c` returning zero exits non-zero, which is the confirming
observation here.

Red input: nobound-02 run through the same check, which must return false — otherwise the check is
measuring its own patterns rather than the cards.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing about no-bound performance on any board is established here; the entry records an absence.
The six measures are not evaluated, and the UnitFlag mechanism in particular is asserted nowhere
else in this scope, so this book carries no description of it. No board, shape or operator. The
absence is recorded at one pinned blob.
