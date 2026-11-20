```
ID:        0059-a-core-time-spread-above-ten-percent-is-called-load-imbalance
LABEL:     boundary
LEVEL:     L9 (performance)
STRATUM:   harvested — drafted from one upstream origin; nothing measured, and the threshold has no stated architecture or derivation
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-analysis/references/metrics_reference.md:220-222 — "最大值与最小值差距 >10% → 负载不均衡 / 需要调整 Tiling 策略，按基本块总数均分"; ops/ops-profiling/references/optimization_quickref.md:112 — "**判定**: PipeUtilization.csv 各核 `ai*_time(us)` 差异 >10%"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a named DAV_2201 board shows core-time spreads above 10 % that do not respond to tiling redistribution — because the spread has a cause other than uneven work.
```

# 0059 · A core-time spread above ten percent is called load imbalance

## 1 · Claim
Upstream asserts that when the maximum and minimum per-core execution times in
PipeUtilization.csv differ by more than 10 %, the workload is load-imbalanced, and that the remedy
is to adjust the tiling to divide by total basic-block count. Upstream lists three remedies:
distribute the tail across more cores, choose a block dim that divides the data evenly, and
dynamic load balancing. No architecture or derivation is stated for the 10 %. Not established here.

## 2 · The wrong branch this removes
The rule is useful and its failure mode is specific: **a core-time spread has at least two causes
and this rule names only one.** 0030 records the other — multiple cores accessing GM addresses
inside one 512 B window serialise, which shows up as exactly the same observable, a large spread in
per-core `mte2_time`. Upstream's own profiling guide even lists "检查各核 mte2_time 差异大" as the
*diagnostic for same-address access*, in a different document from the one calling it imbalance.

So an agent that measures a 25 % spread has two upstream rules pointing at the same number and
prescribing opposite actions: redistribute the work (which does not move the addresses) or stagger
the addresses (which does not rebalance the work). Nothing upstream tells it which applies, and
following the more prominent rule — imbalance, which appears in the main metrics reference —
leaves an address-collision case untouched after a tiling rewrite.

That ambiguity is why this entry is `boundary` rather than `knowledge`. The threshold is worth
having as a trigger to investigate; it is not a diagnosis.

The discriminator this entry can offer, and it is an inference rather than an upstream claim: true
imbalance should show a spread in *total* per-core time roughly proportional to the work each core
received, while address collision should concentrate the spread in `mte2_time` with compute time
roughly even. That is testable and §4 tests it.

## 3 · Ground / Source
`ops/ascendc-performance-analysis/references/metrics_reference.md` §4.4 核间负载均衡判断, lines
219-222, verbatim in full:
"通过 Profiling 数据中各核的耗时对比：
- 最大值与最小值差距 >10% → 负载不均衡
- 需要调整 Tiling 策略，按基本块总数均分"

`ops/ops-profiling/references/optimization_quickref.md` §5, line 112: "**判定**:
PipeUtilization.csv 各核 `ai*_time(us)` 差异 >10%", with the remedies at lines 130-132:
"| 均匀分配尾块 | 数据总量不能被核数整除时，将尾块分散到更多核 | | 调整 Block Dim | 选择能整除
数据量的核数 | | 动态负载均衡 | 小核先完成的去帮大核（高级） |".

The colliding rule, same skill, `optimization_quickref.md:63`: "| 4 | **避免同地址访问** |
多核读同一地址 | 检查各核 mte2_time 差异大 |" — and the mechanism in
`metrics_reference.md:407` (0030): "| GM 同地址访问 | 512B 范围内多核串行化，性能降 10–20% |
错峰访问或改变切分方向 |".

Note the coincidence worth flagging: the imbalance threshold is 10 % and the same-address penalty
is quoted as 10–20 %. So a pure address-collision case would produce a spread that sits exactly at
or just above the imbalance trigger. The two rules do not merely overlap in principle; they
overlap at the same numeric region.

Neither statement carries an architecture. `metrics_reference.md` has per-chip columns elsewhere
and none here; `optimization_quickref.md` has no provenance line at all (0053 §3). One origin.

The tail-handling remedy connects to 0029: distributing a tail across more cores changes the tail
arithmetic, and a tail length derived by subtraction can go negative when the distribution changes.
Fixing imbalance is a live opportunity to introduce that defect.

## 4 · Procedure
Proposed, runnable later; not run. The procedure's job is to separate the two causes, not to
confirm the threshold.

1. Name the die; record `GetCoreNumAiv()` rather than assuming it; occupancy before and after; no
   substitution.
2. Three arms, same total work, one binary with a runtime selector:
   - Arm B (balanced): work divides evenly across cores, addresses well spread.
   - Arm I (imbalanced): deliberately uneven work per core, addresses well spread.
   - Arm C (colliding): even work per core, all cores' base offsets inside one 512 B window —
     this is 0030's arm C and the two experiments share it.
3. Per arm and per core: `ai*_time(us)`, `aiv_mte2_time(us)`, `aiv_vec_time`. Compute the spread
   (max − min) of each, separately. Five repeats, first discarded.
4. The discriminator test: in arm I the spread should appear in total time AND in compute time; in
   arm C it should appear in `mte2_time` with compute time even. Report both spreads for both arms
   so the discriminator is tested rather than assumed.
5. Then apply upstream's prescribed remedy — tiling redistribution — to both arms I and C, and
   record which responds. Arm C is predicted not to.

## 5 · Checker — acceptance declared before the run
Verdict variables `spread_total(arm)`, `spread_mte2(arm)`, `spread_vec(arm)`, and
`remedy_yield(arm)`.
Gate, run first: `spread_total(B)` must be below 10 % and `spread_total(I)` above it. Arm I is the
constructed positive — a deliberate imbalance the instrument must FIND — and arm B the constructed
negative. If the measurement cannot separate them, no verdict is issued for arm C.
The threshold claim is upheld iff that gate passes, i.e. 10 % separates a deliberately balanced
case from a deliberately imbalanced one.
The discriminator claim (this entry's inference, §2) is upheld iff `spread_vec(I)` is high while
`spread_vec(C)` is low, and `remedy_yield(I)` is high while `remedy_yield(C)` is near zero.
These two verdicts are reported separately and labelled by owner: the first tests upstream's
threshold, the second tests this book's inference. A failure of the second corrects §2 without
touching §1, and a success is not credited to upstream.
Exit code is not the verdict.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; no board touched; **no architecture or derivation is stated by upstream** for the
10 % figure, which is a threshold of the 0053 class. This entry does not establish that 10 % is the
right boundary — §4's gate tests only that it separates two deliberately constructed extremes,
which a much wider range of thresholds would also do. The discriminator in §2 is this book's
inference, not upstream's, and is unestablished. It does not enumerate the causes of core-time
spread beyond the two named; clock throttling, per-core cache state and neighbour tenancy on a
shared machine are all plausible and none is covered. It does not establish the dynamic
load-balancing remedy, which upstream marks 高级 and does not describe.
