```
ID:        0052-resource-conflict-ratios-exist-only-on-device-and-cannot-be-simulated
LABEL:     boundary
LEVEL:     L7 (verification)
STRATUM:   harvested — drafted from one upstream origin; nothing measured here
BOARD:     family-claimed(unverified)
SOURCE:    ops/ops-profiling/references/csv_fields_reference.md:224 — "UB 上的 bank group、bank conflict 和资源冲突占比。**上板独有数据，仿真无法获取。**"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a simulator run (`msprof op simulator`) is shown to produce populated ResourceConflictRatio.csv fields on any Ascend target.
```

# 0052 · Resource conflict ratios exist only on device and cannot be simulated

## 1 · Claim
Upstream asserts that the bank-group, bank and resource conflict ratios in
ResourceConflictRatio.csv are device-only data and cannot be obtained from simulation. Upstream
gives the gate values for those fields: `aiv_vec_total_cflt_ratio` below 5 % good and above 15 %
severe, with `aiv_vec_bankgroup_cflt_ratio`, `aiv_vec_bank_cflt_ratio` and `aiv_vec_mte_cflt_ratio`
each below 3 % and `aiv_vec_resc_cflt_ratio` below 5 %. Not established here.

## 2 · The wrong branch this removes
This book is written under a no-device phase (RULES.md Art. 6), and the natural workaround for a
procedure that needs a card is to run it in the simulator instead. For every bank-conflict entry in
this book — 0013, 0014, 0015, 0016 — that workaround does not exist. Their §4 procedures name the
conflict counters, the counters are device-only, and a simulator run would produce empty or absent
columns which, per 0051 §2, read as zero and therefore as "no conflict".

That is the exact shape of a false negative that looks like a clean result. An agent that
simulates a bank-conflict experiment and reports "no conflicts found" has produced a
well-formed, plausible, entirely uninformative artefact — and nothing in the output says so.

The second branch is the mirror: an agent that concludes from this that the simulator is useless.
Upstream's own guidance elsewhere is narrower — the simulator is qualitative and msprof is the
truth — and simulation remains usable for instruction-sequence and overlap questions. The boundary
is specific: conflict ratios, not everything.

## 3 · Ground / Source
`ops/ops-profiling/references/csv_fields_reference.md` §8 ResourceConflictRatio.csv, line 224,
verbatim: "UB 上的 bank group、bank conflict 和资源冲突占比。**上板独有数据，仿真无法获取。**"

The gates, lines 228-235:
```
| aiv_vec_total_cflt_ratio | Vector 指令被阻塞的总占比 | **<5% 良好，>15% 严重** |
| aiv_vec_bankgroup_cflt_ratio | 被 bankgroup 冲突阻塞占比（block stride 不合理） | <3% |
| aiv_vec_bank_cflt_ratio | 被 bank 冲突阻塞占比（读写指针地址不合理） | <3% |
| aiv_vec_resc_cflt_ratio | 被计算单元资源冲突阻塞占比 | <5% |
| aiv_vec_mte_cflt_ratio | 被 MTE 冲突阻塞占比 | <3% |
```
The interpretation and fixes, lines 239-256, map each conflict class to a cause and a remedy —
bankgroup to `block_stride` (0015), bank to UB tensor start addresses and padding (0016), resource
to pipeline scheduling, MTE to movement/compute timing. Those mappings are why the counters matter:
they are the only instrument that distinguishes 0015's failure from 0016's, and both present as
inflated Vector time.

The document's scope (Atlas A2/A3, MindStudio 8.3.0) is 0051's.

The simulator's own scope, same repo, one origin:
`ops/ascendc-performance-analysis/references/metrics_reference.md:293-314` documents
`msprof op simulator` with `--soc-version`, `--aic-metrics=TimelineDetail`, `--core-id`,
`PMSampling` — a substantial capability set that does not include the conflict metrics.

**Consequence for this book, stated plainly**: entries 0013, 0014, 0015 and 0016 cannot be
verified without a card, and their §4 procedures say so by naming device-only counters. Any future
phase that proposes to "verify the bank entries in simulation" is proposing something this entry
says is impossible, and that proposal should be refused with this citation.

## 4 · Procedure
Proposed, runnable later; not run.

1. Simulator arm, no card required and permitted now in principle — except that RULES.md Art. 6 excludes
   simulator runs from phase 1, so this too waits: `msprof op simulator --soc-version=<2201 part>
   --aic-metrics=Default` over the deliberate-conflict kernel of 0016 arm U (a constructed
   conflict, known to be present by construction).
2. Enumerate the produced CSVs and check specifically whether ResourceConflictRatio.csv exists,
   and if so whether its conflict columns are populated or constant-zero.
3. Device arm, on a named die (occupancy before and after, no substitution): the same kernel under
   `msprof op`, confirming the conflict columns ARE populated and non-zero.
4. The comparison is the result. Using a kernel with a *constructed* conflict is essential: if the
   simulator reports zero on a kernel that genuinely has no conflict, nothing is learned.

## 5 · Checker — acceptance declared before the run
Verdict variables `sim_conflict_present` (file exists and columns populated) and
`dev_conflict_present`.
Gate, run first: `dev_conflict_present` must be true with a non-zero bankgroup ratio on the
constructed-conflict kernel. If the device arm cannot see a conflict that was built on purpose,
the kernel does not construct one and the simulator comparison is meaningless.
PASS (claim upheld) iff `dev_conflict_present && !sim_conflict_present`.
The three simulator outcomes are recorded separately and never collapsed: file absent / file
present with columns absent / file present with columns constant-zero. The third is the dangerous
one — it is what produces a plausible clean report — and a boolean check would hide it inside the
first two.
Exit code is not the verdict; the simulator exits zero having produced nothing.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured here; no board touched. Version- and product-line-scoped as in 0051; nothing is
established for other MindStudio versions. This entry does not establish what the simulator CAN
produce, only what upstream says it cannot. It does not establish that the five gate values are
right — they are unscoped thresholds of the kind 0053 records, and their provenance is not stated.
It does not establish the relationship between a conflict ratio and a time cost. It says nothing
about whether AIC-side conflict counters exist; every field named is `aiv_`.
