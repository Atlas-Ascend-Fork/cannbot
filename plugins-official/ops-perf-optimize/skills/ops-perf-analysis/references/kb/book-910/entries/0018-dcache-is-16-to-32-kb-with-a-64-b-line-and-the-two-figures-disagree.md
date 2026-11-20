```
ID:        0018-dcache-is-16-to-32-kb-with-a-64-b-line-and-the-two-figures-disagree
LABEL:     boundary
LEVEL:     L2 (memory hierarchy & residency)
STRATUM:   verified — §4 run on 910B2 2026-08-25 via §5's declared verdicts: `dcache_knee` = PASS-for-16K
           (per-access cost flat 0.285–0.296 sys-cycles from 4 KB to 16 KB, 2.82 at 20 KB, 4.5–4.8 from
           24 KB up — the knee lies in (16, 20] KB ⊂ [12, 20] KB and not in [24, 40]); `line_bytes` = 64
           (streaming cost doubles per stride doubling 8 → 16 → 32 → 64 B, flat from 64 B: 0.80 / 1.38 /
           2.47 / 4.67 / 4.88 / 4.64 / 4.77); control green (cold, 32 accesses: stride 8 B 67–78 vs
           stride 256 B 272–285 sys-cycles). §6 has the tables. Previously harvested (one file, two values).
BOARD:     910B2 (measured 2026-08-25); other 910 parts unverified
SOURCE:    ops/ascendc-performance-analysis/references/metrics_reference.md:178 — "| DCache | 16K / 32K | 64B (Cache Line) | 数据段缓存（TilingData 等） |"; ibid:412 — "| DCache | 32KB 限制 | — |"
INDEX:     means=scalar-only kernel (`acc += p[i*stride]`, `__gm__` loads on one AIV, `dav-c220-vec`),
           in-kernel `GetSystemCycle()` delta (≈50 MHz system counter, derived: 18654 ticks ↔ ~380 µs)
           + host wall time; 5 launches per point (min/median), fresh process per cold point
           conditions=CANN 9.1.0, 910B2 die 0, curFreq 800 MHz before AND after (rated 1800 — the
           sweep ran at the DVFS floor; absolute ns scale with it, the knee and the step are ratios)
           readouts: capacity sweep stride 64 B, 65536 accesses: 4/8/12/16 KB 0.285/0.288/0.291/0.296
           sys-cycles per access; 20 KB 2.82; 24/28/32/40/48/64/96/128/256 KB 4.5–4.8 — knee in (16, 20] KB;
           streaming 1 MB stride 8/16/32/64/128/256/512 B 0.80/1.38/2.47/4.67/4.88/4.64/4.77 — step at 64 B
           time=2026-08-25
OVERTURN:  a scalar-read sweep on a named DAV_2201 board locates a working-set knee at a size that is neither 16 KB nor 32 KB, or shows no knee at all.
```

# 0018 · DCache is 16 K to 32 K with a 64 B line, and the two figures disagree

## 1 · Claim
Measured on 910B2 (one AIV, scalar loads): the scalar data cache holds **16 KB** — per-access cost is
flat from a 4 KB working set to 16 KB and jumps ten-fold between 16 KB and 20 KB, saturating from 24 KB
on — and its line is **64 B** — streaming cost per access doubles with each stride doubling from 8 to
64 B and is flat beyond. Upstream's "16K / 32K" therefore names the right size first; its flat "32KB
限制" ninety lines later is wrong for this part. Not established: which architecture the "32K" belongs
to, if any (§7).

Inference, stated separately: a cold miss costs ≈ 4.7 system-counter ticks ≈ 95 ns at the 800 MHz
clock the run sat at (≈ 75 core cycles), a warm hit ≈ 6 ns including the loop — so a TilingData struct
that overflows 16 KB pays roughly 15× per scalar read of the overflow, which is the "scalar time" upstream
warns about without a number.

## 2 · The wrong branch this removes
An agent sizing TilingData — a real decision, since upstream elsewhere advises shrinking it to cut
scalar time — wants to know whether its struct fits the cache. With "16K / 32K" it cannot know:
the two answers differ by 2×, and a struct that fits one and not the other has entirely different
scalar behaviour. The agent's likely move is to take the larger, because the flat statement in the
constraint table says 32 KB and is more quotable. That is a coin flip dressed as a lookup.

The sharper wrong branch is structural and applies to any budget formula: a capacity that appears
in a denominator must be a single number. An agent writing `usable = ubSize - DCACHE` needs one
value; it will pick one, and the picking will not be recorded anywhere in the code.

## 3 · Ground / Source
`ops/ascendc-performance-analysis/references/metrics_reference.md` §3.6 缓存结构, line 178:
```
| DCache | 16K / 32K | 64B (Cache Line) | 数据段缓存（TilingData 等） |
```
§7 硬件约束速查表, line 412: `| DCache | 32KB 限制 | — |` — note the empty remedy column, so the
constraint is stated with no advice attached, which is unusual in that table and suggests the row
was completed from the ICache row above it.

Registered as `harvest/contradictions-910.md` **C-910-003**.

A third, independent-of-size statement about DCache behaviour, same file line 413, carried
separately by 0019: "| Scalar 写 GM | DCache 与 GM 不保证一致性 | 使用 `DataCacheCleanAndInvalid` |".

Related, and NOT evidence for the 910 side: `ops/ascendc-performance-best-practices/reference/
gather/templates/gather_tiling.template` lines 59 and 62 define, in one file,
`constexpr int32_t DCACHE_SIZE = 128 * 1024;` and `constexpr int32_t DCACHE = 32 * 1024;` — two
DCache constants 4× apart in a single translation unit, with only the second used in the budget
expressions at lines 241 and 617. That template's family is marked DAV_3510 in
`ops/ascendc-performance-best-practices/SKILL.md`, so it is 950-side material and is quoted here
only to show that the ambiguity is not confined to one document. It is not filed as a 910
contradiction row.

The 64 B cache line is separately relevant: `ops/ascendc-performance-best-practices/reference/
scalar/coding_principles.md:319` states "D-Cache cacheline 大小为 64 字节。结构体过大时，访问不同
成员可能落在不同 cacheline 上，导致 D-Cache miss 增多。建议结构体 ≤ 64B（1 个 cacheline），最大
不超过 128B。" — same repo (one origin), but from a guide whose 适用架构 column in
`ops/ascendc-performance-best-practices/SKILL.md:35` reads **DAV_2201 / DAV_3510**, which is the
strongest architecture attribution available for the 64 B figure. The size figure has no such
attribution.

## 4 · Procedure
Proposed, runnable later; not run. The line size and the capacity need different experiments and
are kept apart.

1. Name the die; occupancy before and after; no substitution.
2. Capacity arm: a scalar-only kernel that strides through a GM-resident array with
   `GetValue`, working set swept 4 KB … 128 KB in powers of two, stride fixed at 64 B so every
   access is a distinct line. Record `SCALARLDST` time per element. The capacity shows as the knee
   where per-element cost jumps.
3. Line-size arm: fix the working set well inside the smaller candidate (8 KB) and sweep the
   *stride* over 8, 16, 32, 64, 128, 256 B. Per-element cost should be flat up to the line size
   and then flat again at a higher level — the step locates the line.
4. Five repeats each, first discarded, medians and spreads reported.

**As run (2026-08-25, the 910 machine, die 0, job d910b after a link fix — `-lstdc++` is needed on
the `--cce-aicore-lang` line when the host side uses the C++ library):** steps 2–4 as written with two
instantiations. Timing is the in-kernel `GetSystemCycle()` delta around the load loop (a fixed-rate
system counter, ≈ 50 MHz by comparison with host wall time), reported per access, beside host wall
time; `SCALARLDST` was not collected (msprof not used — the counter gives the per-element cost the
step asks for). The capacity arm keeps the access count constant (≈ 65536) by varying passes with the
working set, so the first pass's misses are a constant fraction. The line arm was run two ways: (A) a
1 MB streaming set, one pass, where every access misses once the stride reaches the line — the
cleanest step; (B) the 8 KB cold set the text names, one pass, fresh process per point, three
processes per stride. The control is (B)'s two ends at equal element count. Frequency: `curFreq`
800 MHz before and after (rated 1800 MHz) — the scalar-only kernel did not lift DVFS; every verdict
here is a ratio within one clock state.

## 5 · Checker — acceptance declared before the run
Two verdicts, never combined.
`dcache_knee`: PASS-for-32K iff the knee lies in [24 KB, 40 KB]; PASS-for-16K iff in [12 KB,
20 KB]; anything else, including no knee, is recorded as such and overturns both readings.
Because the entry's claim is that upstream disagrees with itself, EITHER clean outcome resolves
C-910-003 and restratifies this entry — the entry is written expecting to die, which is the point.
`line_bytes`: the stride at which the per-element cost step occurs. PASS iff 64.
The controls that let these go red: at stride 8 B with a working set of 8 KB, per-element cost
must be measurably LOWER than at stride 256 B with the same element count — if it is not, the
scalar path is not cache-sensitive on this part and both arms are VOID rather than negative.
Exit code is not the verdict.

## 6 · Evidence
RUN 2026-08-25, 910B2 (die 0 of eight, all idle before and after; curFreq 800 MHz PRE and POST).
Every launch's checksum matched the host (bad=0 everywhere). Units: `cyc` = `GetSystemCycle()` ticks.

**Capacity arm — stride 64 B, ≈ 65536 accesses per launch, 5 launches (median shown):**

| working set B | elems | passes | accesses | cyc med | cyc / access | host µs med | host ns / access |
|---|---|---|---|---|---|---|---|
| 4096 | 64 | 1024 | 65536 | 18654 | 0.285 | 402.4 | 6.139 |
| 8192 | 128 | 512 | 65536 | 18860 | 0.288 | 406.0 | 6.196 |
| 12288 | 192 | 341 | 65472 | 19054 | 0.291 | 408.0 | 6.231 |
| 16384 | 256 | 256 | 65536 | 19391 | 0.296 | 415.9 | 6.346 |
| 20480 | 320 | 204 | 65280 | 183815 | 2.816 | 3711.7 | 56.858 |
| 24576 | 384 | 170 | 65280 | 296066 | 4.535 | 5964.0 | 91.360 |
| 28672 | 448 | 146 | 65408 | 308064 | 4.710 | 6273.9 | 95.919 |
| 32768 | 512 | 128 | 65536 | 305674 | 4.664 | 6185.1 | 94.378 |
| 40960 | 640 | 102 | 65280 | 312071 | 4.780 | 6419.4 | 98.337 |
| 49152 | 768 | 85 | 65280 | 298721 | 4.576 | 6023.4 | 92.271 |
| 65536 | 1024 | 64 | 65536 | 303047 | 4.624 | 6221.2 | 94.928 |
| 98304 | 1536 | 42 | 64512 | 290633 | 4.505 | 5848.8 | 90.663 |
| 131072 | 2048 | 32 | 65536 | 293597 | 4.480 | 5955.3 | 90.871 |
| 262144 | 4096 | 16 | 65536 | 307833 | 4.697 | 6192.5 | 94.490 |

`dcache_knee`: flat to 16 KB (0.285–0.296), 20 KB already 2.82 (≈ 10×), saturated from 24 KB (4.5–4.8).
The knee lies in (16, 20] KB → **PASS-for-16K**; the [24, 40] KB window holds no knee.

**Line arm A — streaming 1 MB, one pass, 5 launches:**

| stride B | elems | cyc med | cyc / access | host µs med | host ns / access |
|---|---|---|---|---|---|
| 8 | 131072 | 105342 | 0.804 | 2146.2 | 16.374 |
| 16 | 65536 | 90273 | 1.377 | 1839.2 | 28.064 |
| 32 | 32768 | 80989 | 2.472 | 1651.3 | 50.395 |
| 64 | 16384 | 76426 | 4.665 | 1565.1 | 95.526 |
| 128 | 8192 | 39969 | 4.879 | 828.5 | 101.139 |
| 256 | 4096 | 18999 | 4.638 | 402.5 | 98.263 |
| 512 | 2048 | 9767 | 4.769 | 229.5 | 112.062 |

`line_bytes` = **64**: cost per access ×1.7, ×1.8, ×1.9 for 8 → 16 → 32 → 64 B, then 4.64–4.88 flat.

**Line arm B — 8 KB set, cold, one pass, fresh process, three per stride:**

| stride B | elems | cyc | cyc / access |
|---|---|---|---|
| 8 | 1024 | 940 | 0.918 |
| 8 | 1024 | 941 | 0.919 |
| 8 | 1024 | 935 | 0.913 |
| 16 | 512 | 792 | 1.547 |
| 16 | 512 | 788 | 1.539 |
| 16 | 512 | 797 | 1.557 |
| 32 | 256 | 728 | 2.844 |
| 32 | 256 | 716 | 2.797 |
| 32 | 256 | 741 | 2.895 |
| 64 | 128 | 714 | 5.578 |
| 64 | 128 | 708 | 5.531 |
| 64 | 128 | 710 | 5.547 |
| 128 | 64 | 402 | 6.281 |
| 128 | 64 | 400 | 6.250 |
| 128 | 64 | 399 | 6.234 |
| 256 | 32 | 279 | 8.719 |
| 256 | 32 | 264 | 8.250 |
| 256 | 32 | 258 | 8.062 |

**Control (declared: stride 8 B must be measurably cheaper per element than stride 256 B at equal
element count, cold):**

| working set B | stride B | elems | cyc | cyc / access |
|---|---|---|---|---|
| 256 | 8 | 32 | 78 | 2.438 |
| 8192 | 256 | 32 | 285 | 8.906 |
| 256 | 8 | 32 | 72 | 2.250 |
| 8192 | 256 | 32 | 272 | 8.500 |
| 256 | 8 | 32 | 67 | 2.094 |
| 8192 | 256 | 32 | 280 | 8.750 |

Stride 8 B costs 2.1–2.4 per access, stride 256 B 8.5–8.9 — 3.6–4.2× — the scalar path is
cache-sensitive and both arms are live.

**Warm reference (4 KB, 1024 passes):**

| working set B | stride B | passes | cyc med | cyc / access | host µs med | host ns / access |
|---|---|---|---|---|---|---|
| 4096 | 64 | 1024 | 18647 | 0.285 | 394.1 | 6.014 |

Sources and log in the the verification run's log area.

## 7 · Scope limits — what this entry does NOT establish
One part (910B2), one die, one AIV, scalar `__gm__` loads from one kernel; the AIC's scalar cache, and
whether AIC and AIV caches are separate, were not probed. The 16 KB is a working-set knee of a
strided scalar read stream — associativity, replacement policy and whether TilingData shares the cache
with other scalar data are not established; a knee is where misses begin under THIS access pattern.
The 64 B line is inferred from the cost step under streaming; a 128-B sector with 64-B fills would give
the same step. The whole sweep ran at curFreq 800 MHz (DVFS floor) — absolute nanoseconds and the
tick-to-cycle conversion are for that state; the `GetSystemCycle()` rate (~50 MHz) is derived from host
wall time, not documented here. Upstream's "32K" is not shown wrong for any other architecture, only
absent on this part. Nothing transfers to the 950 book (RULES.md Art. 1).
