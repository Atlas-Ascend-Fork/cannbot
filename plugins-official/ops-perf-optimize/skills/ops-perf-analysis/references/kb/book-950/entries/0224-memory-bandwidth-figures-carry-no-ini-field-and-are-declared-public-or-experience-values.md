```
ID:        0224-memory-bandwidth-figures-carry-no-ini-field-and-are-declared-public-or-experience-values
LABEL:     boundary
LEVEL:     L3 (data movement & layout)
STRATUM:   harvested — one upstream origin, which marks the figures as public-or-experience values
           with no ini field (0206 row 13). A search of the installed 950 ini set found no
           bandwidth field, which agrees with upstream and establishes nothing. Nothing was measured.
BOARD:     950PR
           # upstream's bandwidth rows name 950PR PCIE and 950PR Server; no 950DT figure is given.
SOURCE:    ops/npu-arch/references/npu-hardware-params.md:178 — "| 13 | Memory 带宽 Server 1.6 TB/s /
           PCIE 1.4 TB/s | Guide §3 算力与系统规格 | 同上 |" (信息来源 column: 公开资料 / 经验值)
SOURCE:    ops/npu-arch/references/npu-arch-guide.md:91 — "| Memory 带宽 | 1.6 TB/s [¹](#unverified) |
           1.4 TB/s [¹](#unverified) | 1.6 TB/s [¹](#unverified) |"; :431 — "<a id=\"unverified\">¹</a>
           基于公开资料与经验值，暂未在当前安装的 INI 中找到直接对应的可核验字段。"
           # same skill — ONE origin (RULES.md Art. 3).
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a sustained streaming measurement on 950PR whose achieved GM bandwidth exceeds the
           published figure for that SKU — the "peak" would then be understated and every roofline
           built on it is a floor rather than a ceiling.
```

# 0224 · Memory bandwidth figures carry no ini field and are declared public-or-experience values

## 1 · Claim
Upstream asserts memory bandwidth figures of 1.6 TB/s for 950PR Server and 1.4 TB/s for 950PR PCIE, and
marks both as **not derivable from the installed INI** — row 13 of its 公开资料/经验值 table, with the
inline `[¹]` footnote reading "基于公开资料与经验值，暂未在当前安装的 INI 中找到直接对应的可核验字段".
A search of the installed CANN 9.0.0-beta.2 950 ini set for a bandwidth field returned nothing, which
agrees with upstream's statement. Not established here: nothing was measured.

Unlike the Cube figures (0222), which are arithmetic over four named ini fields, and unlike the Vector
figures (0223), whose base is ini-derived and whose ×2 is not, the bandwidth figures have **no derivation
and no field** — they are the weakest-pedigree numbers in the entire hardware table.

## 2 · The wrong branch this removes
Bandwidth is the denominator of every memory roofline, so this figure sets the ceiling for the majority
of Vector operators — which are memory-bound. An agent takes 1.6 TB/s from a table that also contains
core counts and buffer sizes, and cannot tell that this row alone has no checkable source.

The damage direction is the one 0206 §2 predicts for rate rows and it is the expensive one. If the true
sustained bandwidth is lower, a well-written kernel reports a fraction of "peak" and the team optimises
against an unreachable target; nothing distinguishes "the kernel is slow" from "the denominator was a
public figure".

But the sharper wrong branch here is different and is specific to bandwidth: **the published figure is
not the number a roofline should use at all**, for two independent reasons, and both are documented
inside this same material.

First, peak is not sustained. `ascendc-performance-evaluation`'s own on-board sweep (0270) measures HBM
sustained read at 1.51 TB/s and write at 1.50 TB/s on 950PR_9589 — against a published 1.6 — and its note
says explicitly that the variant `gm_bandwidth_bytes_per_s` "is this HBM-sustained value; **it is NOT too
low**", a sentence written to stop someone raising the constant to make a model fit.

Second, and larger: below the L2 residency knee the effective bandwidth is 2-3× the HBM figure — 4.5 TB/s
single-stream read, 2.84 TB/s combined copy (0270). So an operator whose working set fits in L2 is
bounded by a number the memory-bandwidth row does not contain, and using 1.6 TB/s there under-predicts by
up to 3× in the direction that makes a correct kernel look broken.

So this entry's practical content is: the published row is a chip-level HBM peak with no ini backing, it
is not the sustained rate, and it is not the effective rate for most Vector operators. The number to use
is in a different skill and is measured.

Third branch, from the ini itself. The installed 950 ini does carry `[AICoreMemoryRates]` fields —
`ddr_rate`, `l2_rate`, `ub_to_ddr_rate` and others — which look like bandwidth and are not the chip
figure: they are per-core rates in an unstated unit, and upstream's own consumer treats them as
GB/s-per-core and multiplies by the core count to derive a chip figure (see §3). An agent that finds
`ddr_rate=31` and reads it as 31 GB/s of chip bandwidth is off by the core count.

## 3 · Ground / Source
`npu-arch-guide.md:82-93`, the 算力与系统规格 table — the bandwidth row and the memory capacity row sit
adjacent, and only one of them has a field:

> | 规格项 | Ascend910B2 (DAV_2201) | Ascend950PR PCIE (DAV_3510) | Ascend950PR Server (DAV_3510) |
> |--------|:---:|:---:|:---:|
> | Memory 容量 (GB) | 64 | 112 | 128 |
> | Memory 带宽 | 1.6 TB/s [¹](#unverified) | 1.4 TB/s [¹](#unverified) | 1.6 TB/s [¹](#unverified) |

Memory capacity **is** an ini field (`memory_size` — 120259084288 for 957b, 137438953472 for 9589 in the
installed set, matching the tabulated 112 GB and 128 GB). Memory bandwidth, in the row directly below,
is not. Two adjacent rows in one table with different pedigrees, distinguished only by a superscript.

The footnote, `:429-431`:

> ### 标注
> - <a id="unverified">¹</a> 基于公开资料与经验值，暂未在当前安装的 INI 中找到直接对应的可核验字段。
>   详见 `npu-hardware-params.md` §4。

暂未…找到直接对应的可核验字段 — no directly verifiable corresponding field has been found in the
currently installed INI. That is an unusually precise disclosure: it does not say the figure is wrong, it
says the check could not be performed, and it names where the check was attempted.

Row 13 of the table it points at, `npu-hardware-params.md:178`:

> | 13 | Memory 带宽 Server 1.6 TB/s / PCIE 1.4 TB/s | Guide §3 算力与系统规格 | 同上 |

with 同上 inheriting 公开资料 / 经验值 from the rows above.

**Independent search, installed toolkit** (phase-1 read-only exception): the 32 `NpuArch=3510` ini files
carry no field whose name or value corresponds to a chip-level memory bandwidth. What they do carry, in
`Ascend950PR_9589.ini`:

```
[AICoreMemoryRates]
ddr_rate=31
ddr_read_rate=31
ddr_write_rate=31
l2_rate=100
l2_read_rate=100
l2_write_rate=100
l1_to_l0_a_rate=256
l1_to_l0_b_rate=256
l1_to_ub_rate=128
l0_c_to_ub_rate=128
ub_to_l2_rate=128
ub_to_ddr_rate=128
ub_to_l1_rate=128
```

No unit is declared for any of them. This is consistent with upstream's statement — none of these is
"directly corresponding" to a chip figure — and it is a **negative**, which establishes nothing on its
own.

How another upstream skill treats these same fields, from
`ascendc-performance-evaluation/references/hardware/ascend950pr.json`:

```json
"l2_bandwidth_source": "derived from VectorCoreMemoryRates.l2_rate * vector_core_cnt; rate unit treated as GB/s",
"gm_bandwidth_source": "npu-arch public/experience value",
"derived_from_ini": {
  "vector_core_ddr_bandwidth_bytes_per_s": 1024000000000,
  "aicore_ddr_bandwidth_bytes_per_s": 992000000000
}
```

Two things to read off that. The unit is a **treatment**, not a reading — "rate unit treated as GB/s" —
so the derivation rests on an assumption about an undeclared unit. And that skill takes the chip GM
bandwidth from npu-arch's public value rather than deriving it, while deriving the L2 figure from the ini
— an explicit acknowledgement that the ini does not supply the chip number. Same repo as npu-arch, so one
origin; it is quoted because it is the only place the derivation is attempted and its caveats stated.

Note the arithmetic those derived fields imply: 16 GB/s × 64 vector cores = 1024 GB/s and
31 GB/s × 32 AI cores = 992 GB/s — both **below** the published 1.6 TB/s, and below the 1.5 TB/s
sustained figure 0270 measures. So the ini-derived route and the published figure do not agree, and
neither matches the measurement. Three numbers, three methods; this entry claims none of them.

## 4 · Procedure
Runnable later on `950PR`; **no 950DT bandwidth figure is published**, so BOARD stays 950PR.

Arm A — sustained streaming, far above L2. Build a pure `DataCopyPad` GM↔UB kernel at full core width
with a working set several times the L2 capacity for the SKU under test (0218), so residency cannot
contribute. Separate read-only, write-only and copy modes. Minimum over 50 repetitions. Report achieved
bytes/second per mode. This is upstream's own `tests/onboard/kernels/membw` protocol (0270) and the two
entries share one run deliberately — what this entry adds is the comparison against the *published* row
rather than against the calibrated constants.

Arm B — the L2-resident regime, which is where the published figure is most wrong. Repeat Arm A with a
working set well under the knee. Report the ratio to Arm A. §2 predicts 2-3×; a roofline using the
published 1.6 TB/s here is wrong by that factor.

Arm C — the ini-derivation arm, which tests the unit assumption. Compute
`ddr_rate × ai_core_cnt` and `vector_core ddr_rate × vector_core_cnt` from the resolved ini under the
GB/s treatment, and compare both against Arm A's measurement. If neither matches, the unit treatment is
wrong or the fields mean something else, and the "derived_from_ini" route is unusable — which is worth
establishing, because it is the only route that could ever give this figure an ini pedigree.

Arm D — the SKU spread. Repeat Arm A on a 957b (published 1.4 TB/s) and a 9589 (published 1.6 TB/s) and
check whether the measured ratio matches the published ratio. Two SKUs, because a single measurement
cannot distinguish "the figure is right" from "the figure happens to be near what this part does".

Device selection is explicit: the operator names the device index **and the SKU**, the harness prints
both back with `compiler/version.info` and the resolved SoC string, occupancy is checked before the run
(shared machine, ≤4 dies), and no die is substituted for another. Bandwidth is a shared resource — L2 and
HBM are contended across cores — so a co-tenant would depress every reading; the sole-tenancy of the die
is confirmed and recorded before Arm A, not assumed.

## 5 · Checker — acceptance declared before the run
Verdict variable `published_is_ceiling`, declared FALSE-on-any-hit: false as soon as any Arm A mode on
any SKU exceeds that SKU's published figure outside run variance. This is the only pass/fail and it is
deliberately one-sided — a peak figure may be loose and still be a ceiling, but a peak that is exceeded is
not a peak.

`sustained_fraction[sku, mode]` — achieved divided by published, reported with run variance. **No
acceptance band is declared**, deliberately: upstream publishes a figure with no method and no
conditions, so there is no stated quantity for a band to be around, and inventing one would let a
convenient result read as validation of a number that has no derivation. What is reported instead is the
gap, with the mode and the SKU attached.

`l2_regime_ratio` (Arm B) — Arm B divided by Arm A. Reported. A ratio near 1.0 would mean the L2 effect
0270 measures is absent, which would contradict that entry rather than this one.

`ini_derivation_matches` (Arm C) — pass iff either derived figure lands within 10 % of Arm A's
corresponding measurement. Failure is the expected outcome given §3's arithmetic and is a finding about
the derivation route, not about the hardware.

The positive fixture, declared before the run: Arm A must be shown to go red on a known input — run it
with the working set reduced below the L2 knee while still labelled "far above L2". The measured figure
must then **exceed** the published one and `published_is_ceiling` must go false. If it does not, the
sweep is not sensitive to residency and every Arm A figure is suspect, because the whole design of Arm A
depends on having escaped L2. Without this the checker reads only "the number came out below 1.6", which
is the known blind species: a bandwidth test that is accidentally launch-bound or L2-resident produces a
comfortable pass for the wrong reason.

Process exit code is not the verdict for any arm.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No kernel was built and no bytes
were moved. The `[AICoreMemoryRates]` fields quoted in §3 are a file read under the sanctioned phase-1
read-only exception, and the arithmetic performed on them (16 × 64, 31 × 32) is arithmetic over an
**assumed** unit, reproduced here from another upstream skill's stated treatment rather than derived. The
search that found no bandwidth field is a negative and establishes nothing.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured. The entry does not establish that 1.6 TB/s or 1.4 TB/s is right or wrong — it
establishes that upstream declares them unverifiable from the installed configuration, that the installed
ini carries no corresponding field, and that three different routes to a bandwidth number (published,
ini-derived, measured by another upstream skill) give three different answers. There is **no second
origin**: the figures are one upstream skill's public-or-experience values, and the ini supplies nothing.
It does not establish the sustained-versus-peak gap or the L2 regime; those are 0270's measurements,
which are upstream's own readouts and enter this book as upstream text (RULES.md Art. 3), and Arms A and B are
open here. It does not establish the unit of the `[AICoreMemoryRates]` fields — the GB/s reading is
another skill's declared *treatment* of an undeclared unit, and Arm C is what would test it. BOARD is
`950PR`: **no 950DT bandwidth figure is published anywhere in this scope**, so there is nothing to carry
or test for it, and the 950DT parts in the installed ini set have memory capacities up to 154618822656
(144 GB) with no corresponding rate. It says nothing about L2 bandwidth, about the ramp-up behaviour
below ~0.8 MB, or about the host-side launch floor below 8 MB — all three are documented in 0270 and all
three bound where any bandwidth figure applies at all. Nothing transfers to the other book (RULES.md Art. 1):
the 910B2 column's 1.6 TB/s is upstream's text and carries the same `[¹]` marker.
