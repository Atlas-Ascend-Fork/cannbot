```
ID:        0007-l2-on-910b1-b2-is-stated-as-192-mb-by-the-truth-source-and-32-mb-by-the-metrics-table
LABEL:     boundary
LEVEL:     L2 (memory hierarchy & residency)
STRATUM:   overturned — 2026-08-24, exactly as §5 intended: the behavioural knee landed inside
           192 MB ± 25 % and outside 32 MB ± 25 % on the measured 910B2, so the claim "the
           question is open" is dead. The surviving number lives in 0077 (verified). Killing
           observation in §6.
BOARD:     910B2
SOURCE:    ops/npu-arch/references/npu-hardware-params.md:132 — "| DAV_2201 | Ascend910B2 | 24 | 48 | 1.8 GHz | 192 MB | 64 GB |"; ops/ascendc-performance-analysis/references/metrics_reference.md:122 — "| **L2 Cache** | 32 MB | 32 MB | 128 MB | 16 MB | GM 缓存（全芯片共享） |"
INDEX:     killing run — 910B2 NPU 0 (bus 0000:C1:00.0), CANN 9.1.0 ts 20260730_231653901,
           driver 25.5.1, 2026-08-24. Re-derive: multi-pass streaming-read kernel (4 passes,
           64 KB chunks, 1 AIV core), buffer swept 8→256 MB, ≥2 repeats/size; warm-pass hit
           counts from the profiler's aiv_r0/r1_read_cache_hit columns under
           --aic-metrics=L2Cache. Full table in 0077 §6.
OVERTURN:  a runtime or INI readout of L2 capacity on a named Ascend910B2 part returns a third value, or returns one of the two and thereby kills the other. Either outcome overturns this entry, whose claim is that the question is open.
```

# 0007 · L2 on 910B1/B2 is stated as 192 MB by the truth source and 32 MB by the metrics table

## 1 · Claim
Upstream asserts, in its self-declared truth source, that Ascend910B2 has 192 MB of L2. Upstream
also asserts, in its performance-analysis metrics table, that 910B1/B2 have 32 MB of L2. These are
6× apart, neither cites the other, and nothing in this book resolves them. The claim of this entry
is the disagreement itself, not either number. Not established here.

## 2 · The wrong branch this removes
An agent gating an L2-residency decision — "does the working set fit in L2, so can I skip a
re-load or disable a cache hint" — picks whichever number it met first and proceeds. At 192 MB a
64 MB working set is comfortably resident; at 32 MB it is not, and the two answers recommend
opposite tilings. The normal checks do not catch this because *both* numbers are in the same
upstream repo, both in tables that look authoritative, and an agent that cross-checks one source
against another will happily find the number it already has (in whichever file it opened) and
score that as corroboration. Recording the conflict is the only thing that makes the agent stop.
Note that RULES.md Art. 7 forbids resolving this by picking the more plausible author, and the truth
source's self-declaration is exactly such a plausibility argument — it is not evidence.

## 3 · Ground / Source
Statement A — `ops/npu-arch/references/npu-hardware-params.md`, §"子型号变化参数" SKU table,
line 132:
```
| DAV_2201 | Ascend910B2 | 24 | 48 | 1.8 GHz | 192 MB | 64 GB |
```
restated at `ops/npu-arch/SKILL.md:52` — "| L2 | 192 MB | 112 MB | 128 MB |" for Ascend910B2 /
Ascend950PR PCIE / Ascend950PR Server. Same repo, same skill: one origin.

Statement B — `ops/ascendc-performance-analysis/references/metrics_reference.md` §3.1 存储层次,
line 122, in a table whose columns (line 115) are 910B1/B2 | 910B3 | 950 | 310P3:
```
| **L2 Cache** | 32 MB | 32 MB | 128 MB | 16 MB | GM 缓存（全芯片共享） |
```

A candidate provenance for the discrepancy, offered as a lead for §4 and explicitly NOT as a
resolution: 32 MB is exactly the `l2_size` that npu-arch's own §2.1 attributes to **DAV_1001**
(`ops/npu-arch/references/npu-hardware-params.md:56` — "| L2 | `l2_size` | 32 MB (33554432) |"),
the previous-generation Ascend910. It is possible that the metrics table carried a
previous-generation figure into a 910B column. It is equally possible that npu-arch's 192 MB is a
figure from one SKU's INI, which its own §"子型号变化参数" warns may describe an engineering
sample rather than a production part (see 0012). Two plausible stories, no evidence — which is why
this stays open.

Note also that npu-arch's per-arch §2.3 table for DAV_2201 has **no L2 row at all**: L2 is
explicitly in the by-SKU varying set (line 124: "同一 NpuArch 内，核数、频率、L2、Memory 等参数
可能随子型号不同而变化"). So statement B's structure — one L2 value shared by 910B1 and 910B2 —
is itself a claim upstream's truth source declines to make.

Registered as `harvest/CONTRADICTIONS.md` **C-001**, cited here, not re-filed.
Cross-linked to STANDING_QUESTIONS ("What is L2 capacity on a named Ascend910B2 part?").

## 4 · Procedure
Proposed, runnable later; not run. This is the procedure C-001 names as its resolution.

1. Name the die explicitly and record which physical part it is (`npu-smi info -t board -i <n>`),
   because the whole point is that the answer may be per-SKU. Occupancy before and after; refuse
   to substitute a die — substituting here would be substituting the very variable under test.
2. INI arm (read-only, permitted in the no-card phase):
   `grep -Rn "l2_size" "$ASCEND_HOME_PATH"/*/data/platform_config/` and record EVERY matching
   file with its SoC name, not just the one that matches the installed part. If several 910B INIs
   disagree with each other, that is the answer to a different and more interesting question.
3. Runtime arm: `GetCoreMemSize(platform_ascendc::CoreMemType::L2, l2Size)`. **An accessor does
   exist** — `ops/npu-arch/references/npu-hardware-params.md` does not name one but
   `ops/npu-arch/references/npu-arch-guide.md:208` does, and an earlier draft of this book wrongly
   recorded its absence (see 0011 §7's correction note). Print it on one line with
   `GetCurNpuArch()` and the board string, and treat a returned value as authoritative over both
   documents.
4. Behavioural arm, the only one that measures the machine rather than a file: a streaming read
   kernel over a GM buffer swept across 8 MB … 256 MB, reading `hit_rate` from `L2Cache.csv` per
   size, three repeats, on the named die. The capacity shows as the knee where hit rate collapses.

## 5 · Checker — acceptance declared before the run
Verdict variable `l2_knee_bytes` from the behavioural arm, and `l2_ini_bytes` from the INI arm,
reported separately and never averaged.
This entry's claim (the question is open) is upheld only while the arms disagree or are missing.
It is OVERTURNED — correctly, and that is the intent — as soon as `l2_knee_bytes` lands within
±25 % of one of {32 MB, 192 MB} and outside the other, at which point the entry is restratified
and the surviving number becomes a new entry with its own BOARD naming the part actually used.
The declared threshold is stated now, before any readout: ±25 %, chosen because the two candidates
are 6× apart, so no plausible measurement noise can make both pass.
This checker can go red in a third way, which is why it is not a two-way test: a knee at neither
value (say 96 MB) fails BOTH candidates and is recorded as such rather than snapped to the nearer
one. Exit code is not the verdict.

## 6 · Evidence
**KILLING OBSERVATION (2026-08-24, 910B2 NPU 0, CANN 9.1.0 — identity in INDEX).** All four §4
arms ran; the checker verdicts, against §5 as declared:

- Behavioural arm (`l2_knee_bytes`): warm-pass hit rate is 100.00 % at every size 8–160 MB
  (hit counts equal 3×size/128 B exactly, +5 constant), then 68.8–69.8 % at 192 MB,
  20.5–21.4 % at 224 MB, 0.00 % at 256 MB (5 absolute hits). The collapse localises the
  capacity in (160 MB, 256 MB) — inside 192 MB ± 25 % (144–240), decisively outside
  32 MB ± 25 % (24–40), where the hit rate is still a flat 100 %. §5's overturn condition is
  met; the third-way red case (a knee at neither value) did not occur. The instrument shows
  both extremes in-band (100 % at 8 MB, 0 % at 256 MB) — it can go red and green on knowns.
- INI arm (`l2_ini_bytes`, reported separately, never averaged): Ascend910B1/B2/B2C/B3.ini all
  carry l2_size=201326592 (192 MB); Ascend910B4.ini 100663296 (96 MB), Ascend910B4-1.ini
  176160768 (168 MB) — L2 is per-SKU inside the family, as §3 anticipated. And the 32 MB of
  statement B is FOUND INSTALLED: Ascend910B.ini (NpuArch=1001, the previous generation)
  carries l2_size=33554432 — §3's provenance lead is confirmed: the metrics table carried a
  previous-generation figure into a 910B column.
- Runtime arm: GetCoreMemSize(L2) = 201326592, printed with GetCurNpuArch() = 2201, one process.
- Deviations, recorded per plan: hit rate came from the profiler's op-summary
  aiv_r0/r1_read_cache_hit count columns (this msprof version's equivalent of the L2Cache.csv
  §4 named); 3 of 27 profiled runs produced no op-summary (msprof flakiness: 8 MB rep2,
  16 MB rep1, 64 MB rep2) — every size retains ≥2 repeats and the verdict region (128–256 MB)
  retains 3/3. Reads were 4 passes on one AIV core; curFreq 800 MHz pre and post (hit-rate
  metric, frequency-insensitive; the accompanying effective-bandwidth column in 0077 §6 is
  auxiliary, not a verdict).

The surviving number and its full readout table: **0077**, STRATUM verified(910B2).

## 7 · Scope limits — what this overturn does NOT establish
The killing run covers ONE die of ONE part (910B2, NPU 0, bus 0000:C1:00.0) under ONE pin. The
knee method's own limits transfer to 0077 and are restated there: capacity visible to one AIV core
under streaming reads, localised only to (160 MB, 256 MB) by these sweep points, not measured to
the megabyte; whether the whole 192 MB is visible to one core versus the chip is not separated by
this method. Nothing here covers 910B4 (whose own inis say 96/168 MB — different numbers, unrun),
910B2C, 910B3, or Ascend910_93. The 1001-ini provenance of the 32 MB explains where the figure
plausibly came from; it does not establish HOW the error entered the metrics table.
