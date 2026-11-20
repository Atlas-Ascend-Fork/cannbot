```
ID:        0058-an-l2-hit-rate-below-50-percent-is-the-stated-trigger-for-cache-mode-work-on-a2-a3
LABEL:     knowledge
LEVEL:     L9 (performance)
STRATUM:   harvested — drafted from one upstream origin; nothing measured here
BOARD:     family-claimed(unverified)
SOURCE:    ops/ops-profiling/references/csv_fields_reference.md:218 — "| ai*_total_hit_rate(%) | 读/写 cache 总命中率 | **>80% 良好，<50% 需优化** |"; ops/ops-profiling/references/optimization_quickref.md:62 — "| 3 | **L2 CacheMode** | L2 hit rate <50% | 检查 L2Cache.csv |"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a paired study on a named DAV_2201 board shows L2 cache-mode changes yielding no more at hit rates below 50 % than above 80 %.
```

# 0058 · An L2 hit rate below 50 % is the stated trigger for cache-mode work on A2/A3

## 1 · Claim
Upstream asserts, in a field table scoped to Atlas A2/A3, that an L2 total hit rate above 80 % is
good and below 50 % needs optimisation, with the same 80 % standard applied separately to the read
and write hit rates. Upstream asserts that a hit rate below 50 % is the trigger for L2 cache-mode
work. Not established here.

## 2 · The wrong branch this removes
L2 hit rate is one of the few profiling fields whose meaning is obvious, which makes it one of the
most likely to be acted on without a threshold. An agent seeing 62 % has no way to know whether
that is a problem. With the bands, 62 % sits between "good" and "needs optimisation" — which is
itself useful information: it says the effort belongs elsewhere.

The second branch is the direction of the fix. "Low hit rate" reads as "improve locality", and the
tiling changes that improve locality are expensive and invasive. Upstream's prescribed remedy is
narrower and cheaper: a cache-mode setting. Knowing that the recommended first move is a mode
change rather than a re-tiling saves the wrong investigation.

The third: the same skill elsewhere recommends L2 bypass under provable no-reuse. Bypass and
hit-rate improvement are opposite responses to the same observable, and which is right depends on
whether the data is reused at all — a property of the algorithm, not of the counter. An agent that
reads only the hit rate cannot tell them apart, and this entry's job is to say so.

## 3 · Ground / Source
`ops/ops-profiling/references/csv_fields_reference.md` §7 L2Cache.csv, under the heading
"### Atlas A2/A3" at line 208, with the gate at line 218:
```
| ai*_total_hit_rate(%) | 读/写 cache 总命中率 | **>80% 良好，<50% 需优化** |
```
and lines 216-217: `| ai*_write_hit_rate(%) | 写 cache 命中率 | >80% |`,
`| ai*_read_hit_rate(%) | 读 cache 命中率 | >80% |`.

The action, `ops/ops-profiling/references/optimization_quickref.md` §3 MTE2/MTE3 Bound, line 62:
`| 3 | **L2 CacheMode** | L2 hit rate <50% | 检查 L2Cache.csv |`.

The file map, `ops/ascendc-performance-analysis/references/metrics_reference.md:345`:
`| \`L2Cache.csv\` | L2 Cache 命中率 | \`hit_rate\` |` — note the field is named `hit_rate` there
and `ai*_total_hit_rate(%)` in the field reference. Two spellings for what is presumably one
quantity; 0051 §4 is the procedure that would settle which the tool actually emits, and this is
exactly the silent-zero hazard 0051 §2 describes.

The opposite prescription, from another agent's domain and NOT re-verified here: the deep-dive
survey records `ascendc-perf-optimize/references/single-core-pipeline/techniques/mem-05` as
recommending L2 bypass (`SetL2CacheHint(CACHE_MODE_DISABLE)`) only under provable no-reuse, with a
ban on case-ID or shape whitelists. Flagged as the counter-move named in §2, not asserted.

**Scoping.** This is one of the better-scoped threshold statements in scope: `csv_fields_reference.md`
carries both an architecture (Atlas A2/A3) and a tool version (MindStudio 8.3.0) at line 3, unlike
`optimization_quickref.md`, which carries neither. Where the two disagree in discipline, the
scoped one is the one to cite — and both are the same repo, so one origin.

The L2 capacity these rates are relative to is itself unresolved (0007, C-001), which means a hit
rate can be measured but not predicted.

## 4 · Procedure
Proposed, runnable later; not run.

1. Name the die; record the part; occupancy before and after; no substitution.
2. Build a kernel family whose L2 reuse is tunable: a blocked read over a GM buffer whose block
   size is swept so that the working set spans well inside to well outside plausible L2 capacity
   (8 MB … 256 MB, per 0007 §4 — the two experiments share a sweep and should share a run).
3. Per point: `ai*_total_hit_rate`, `ai*_read_hit_rate`, `ai*_write_hit_rate`, `aiv_mte2_time`,
   and total task duration. Five repeats, first discarded.
4. Then apply the prescribed remedy — an L2 cache-mode change — at each point, and record the
   speed-up as a function of the *baseline* hit rate.
5. Report the achieved hit rate alongside the working set, so the capacity question (0007) gets a
   second, independent readout out of the same run.

## 5 · Checker — acceptance declared before the run
Verdict variable `yield(hit_rate)`: speed-up from the cache-mode change as a function of baseline
hit rate.
PASS (the 50 % trigger upheld) iff mean `yield` below 50 % exceeds mean `yield` above 80 % by more
than three times the pooled repeat-to-repeat spread.
The declared negative, and the likelier one: a `yield` that varies smoothly or not at all with hit
rate, meaning the 50 % figure is not a decision boundary. The entry is then corrected to say so
rather than retained on the strength of the number appearing upstream.
Control that lets this go red: the hit rate must actually vary across the sweep — if it is
constant, the family does not tune reuse and no verdict is issued. That check runs first.
The field-name ambiguity of §3 is a gate, not a footnote: if neither `hit_rate` nor
`ai*_total_hit_rate` is present and populated in the emitted CSV, the run produces no verdict at
all (0051, 0052). A missing field reads as zero, and zero would look like a spectacular
confirmation of "below 50 %".
Exit code is not the verdict.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured here; no board touched. "Atlas A2/A3" is two product lines, not a board, and the
figures are pinned to MindStudio 8.3.0, which this book has no installation bound to. This entry
does not establish that 50 % or 80 % are real boundaries; they are unscoped-by-derivation
thresholds of the 0053 class, better scoped by architecture than most but with no stated basis. It
does not establish which of the two field spellings the tool emits. It does not resolve when a low
hit rate should lead to bypass rather than to improved locality (§2) — that depends on algorithmic
reuse, which no counter reports. It says nothing about L2 capacity, which is itself open (0007).
