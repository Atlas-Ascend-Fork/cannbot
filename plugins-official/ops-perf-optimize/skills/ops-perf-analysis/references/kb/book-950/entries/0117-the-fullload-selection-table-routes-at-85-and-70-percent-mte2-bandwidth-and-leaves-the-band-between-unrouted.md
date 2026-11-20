```
ID:        0117-the-fullload-selection-table-routes-at-85-and-70-percent-mte2-bandwidth-and-leaves-the-band-between-unrouted
LABEL:     trap
LEVEL:     L9 (performance)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/tiling/matmul/fallback/tiling-flow.md:259-267 —
           "| 小侧 ≤ L1/2, T≥2, **真 MTE2 bound** (带宽 ≥ 85%) | **FullLoad** | MTE2 是瓶颈 |
            | 小侧 ≤ L1/2, T≥2, 假 MTE2 bound (带宽 < 70%) | SWAT | 瓶颈不在搬移 |"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured sweep on a named 950 board showing the FullLoad-vs-SWAT crossover falls
           cleanly at one MTE2 bandwidth utilisation between 70 % and 85 % — the band would then
           be a stated tolerance around a real threshold rather than an unrouted gap.
```

# 0117 · The FullLoad selection table routes at 85 % and 70 % MTE2 bandwidth and leaves the band between unrouted

## 1 · Claim
Upstream asserts a five-row selection table for the FullLoad decision whose last two substantive
rows are conditioned on MTE2 bandwidth utilisation: at `≥ 85 %` the operator is a true MTE2-bound
case and FullLoad is chosen; at `< 70 %` it is a false MTE2-bound case and SWAT is chosen.
Upstream states no row for utilisation in `[70 %, 85 %)`. Upstream also gives no capture protocol
for the utilisation figure in this file — which counter, over which window, on which core type —
and no board for the two numbers. Not established here.

## 2 · The wrong branch this removes
The gap is not academic: measured MTE2 utilisation on real matmul cases lands in the seventies and
low eighties often enough that a decision table with a 15-point hole will be consulted inside the
hole regularly. An agent that meets an unrouted input does one of three things, all bad and all
invisible: it rounds to the nearest arm (turning a 15-point gap into a 7.5-point silent
threshold at 77.5 %), it takes the conservative arm (SWAT, forfeiting FullLoad on genuinely
MTE2-bound shapes in the 70–85 band), or it treats the earlier geometric gates as sufficient and
ignores the bandwidth condition entirely. None of these is recorded in the plan, so two agents
handed the same case can produce different strategies and neither can say why.

The second wrong branch is quieter. `带宽 ≥ 85%` is a *diagnosis* input to a *tiling* decision:
it requires a profile of the current kernel before the plan for the next kernel can be chosen. An
agent that reads the table as a static rule tries to evaluate it from the shape alone and
substitutes a guess. Upstream never says the number must come from a profiling run, and never
says which run — the un-optimised baseline or the candidate.

## 3 · Ground / Source
`matmul/fallback/tiling-flow.md:259-267`, §4.5 in full:

```
### 4.5 选型决策

| 场景 | 策略 | 原因 |
|------|------|------|
| 两侧 > L1/2 | SWAT | 物理不可行 |
| 小侧 ≤ L1/2, T=1 | SWAT | 无重复搬移可消除 |
| 小侧 ≤ L1/2, T≥2, **真 MTE2 bound** (带宽 ≥ 85%) | **FullLoad** | MTE2 是瓶颈 |
| 小侧 ≤ L1/2, T≥2, 假 MTE2 bound (带宽 < 70%) | SWAT | 瓶颈不在搬移 |
| 已走 StreamK | **不叠加** | K 已切散 |
```

The five rows partition on `(fit, T, bandwidth, StreamK)`. Rows 1, 2 and 5 are complete
conditions. Rows 3 and 4 together cover bandwidth `≥ 85` and `< 70` and leave `[70, 85)` with no
arm. There is no default row and no "otherwise" clause anywhere in §4.

The thresholds appear nowhere else in the tiling subtree; `85` and `70` are stated once each,
here, with no derivation, no capture method and no board. Under 0104's provenance rule both trace
to literals in a markdown table and are therefore software 经验值 — searchable, not architectural.

The same species of gap exists elsewhere in this skill's diagnosis layer, which is outside this
domain's scope but is noted so the pattern is visible: an earlier survey of this skill recorded a
bound-routing tree whose predicates are qualitative (`占比高/利用率高`) with no thresholds and no
precedence at all. The matmul table is the more advanced form of the same defect — it has numbers,
and the numbers do not meet.

Registered as C-950tiling-004. It is not a contradiction between two sources; it is a single
table that does not cover its own input domain, and it is recorded in the contradictions file
because that is where this domain's decision-surface defects live and because entry 0110 cites it.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase. The
question the procedure answers is not "what belongs in the gap" but "where is the crossover", and
the answer names the arm the gap should route to.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s
spacing; bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and
discard the case if the die moved.

Bandwidth-ladder pairing. Construct a family of matmul cases that all pass FullLoad's geometric
gates (0110: fit, `T ≥ 2`, layout, `Bytes_opp ≥ 20 KB`) but span MTE2 utilisation from roughly
60 % to roughly 95 %. Utilisation is varied by changing the arithmetic intensity — sweep N with
M and K fixed, and sweep dtype across BF16/FP8 — rather than by throttling anything, so every
point is a legitimate operator. For each case build both arms with one compiler pin: FullLoad
(smaller side resident) and SWAT. md5 both binaries; host echo of `isAFullLoad`, `stepKb`,
`nBufferNum`; fp64 reference check within the declared tolerance. Under
`msprof --aic-metrics=PipeUtilization`, ≥10 iterations, first 5 dropped, per case, record for the
SWAT arm the MTE2 bandwidth utilisation (this is the table's input, and it must be measured on the
baseline arm, not on the candidate — which of the two upstream means is unstated, so both are
recorded and reported separately) and for both arms `aic_time`.

Refuses to assume: that a free die stays free; that a die may be substituted; that "带宽" means
achieved bytes/s over peak — the exact counter and window are recorded with the readout, and if
the profile offers more than one candidate metric, all are reported rather than one being chosen
silently; that the crossover is a single point independent of dtype (each dtype is its own ladder);
that peak bandwidth is any published figure — upstream's own truth-source skill flags its
bandwidth numbers as `基于公开资料与经验值`, so any utilisation percentage inherits that
uncertainty and the raw bytes/s is recorded alongside it.

## 5 · Checker — acceptance declared before the run
Verdict variable `crossover_bw`, the MTE2 utilisation at which median FullLoad `aic_time` first
falls below median SWAT `aic_time`, computed per dtype ladder. Declared before the run: upstream's
table is vindicated as a tolerance band iff `crossover_bw ∈ [70, 85]` for every ladder — the gap
is then a stated uncertainty around a real threshold, and the OVERTURN condition fires. The table
is shown to be wrong-valued iff `crossover_bw < 70` or `> 85` on any ladder, and the measured
value is reported instead. If FullLoad never wins at any utilisation on a ladder, `crossover_bw =
none` for that ladder, which is a stronger result than either and is reported as such.

The exit code is not the verdict. This checker's blind mode is the one 0110 also guards: a
FullLoad arm whose L1 budget silently shrank `stepKb` to 1 or fell back to SWAT would produce
`aic_time` parity at every utilisation and yield `crossover_bw = none` from an experiment that
never ran FullLoad. The `isAFullLoad` echo must be true at every point and MTE2 bytes moved must
differ measurably between arms; the checker goes red on either failure rather than reporting a
crossover. A second, independent guard: the utilisation ladder must actually span the range — if
the constructed cases all land within 10 points of each other, the ladder is void and no crossover
is reported.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured. The entry does not establish where the crossover is, does not establish that
85 % and 70 % are meaningful at all, and does not propose a value for the gap — filling it by
judgement is exactly what Art. 7 forbids. It does not establish what "带宽" means operationally:
upstream names no counter, no window and no core type, and the §4 procedure treats that ambiguity
as unresolved rather than picking a metric. It does not establish whether the utilisation is to be
measured on the baseline or on the candidate. It says nothing about the same-shaped threshold gaps
elsewhere in this skill's diagnosis layer, which are another domain's to record. No board is named
in the source, so BOARD is `family-claimed(unverified)` and the chip is unstated; §4 names
950PR/950DT because that is where our run would happen. Nothing here is established for any
910-family board.
