```
ID:        0066-pruning-rule-p4-as-written-removes-every-non-uniform-split
LABEL:     trap
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/comm-compute/pipeline_balancing.md:341-364 — "for hs = hs_min to hs_max step 16: hc = M / hs … tail = M % hs … // --- 剪枝 P4: 配平条件 --- shortMSize = tail; if shortMSize > 0 and shortMSize < ρ × hs: continue"
           ops/ascendc-perf-optimize/references/comm-compute/pipeline_balancing.md:287 — "| P4 | **配平条件**：shortMSize < ρ × longMSize 排除（松约束可降级为惩罚） | 短块无法掩盖相邻长块的瓶颈操作 | ρ = max(R, 1/R) |"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  an execution of the published pseudocode on any real (M, R, baseM, baseN, N_core) tuple
           that emits at least one candidate with a non-zero tail — the vacuity claim below would
           then be false, and the defect is in this entry's reading rather than in the algorithm.
```

# 0066 · Pruning rule P4, as written, removes every non-uniform split

## 1 · Claim
Upstream asserts a unified search over the long-block size `hs`, with four pruning rules, whose
purpose is to enumerate the balance-feasible region systematically and return the best fifteen
candidates for measurement. As published, the search sets `tail = M % hs` and prunes with
`if shortMSize > 0 and shortMSize < ρ × hs: continue`, where `ρ = max(R, 1/R) ≥ 1`. A remainder is
strictly smaller than its divisor, so `tail < hs ≤ ρ × hs` holds for every enumerated `hs`;
therefore every candidate with a non-zero tail is pruned, and only exact divisors of M — uniform
splits — can reach the candidate list. The apparatus whose stated purpose is to find non-uniform
splits cannot emit one. Not established here by execution: this is a reading of the published
pseudocode, and the OVERTURN condition above is how it can be refuted.

## 2 · The wrong branch this removes
Two branches, and the second is the dangerous one. An agent that implements the pseudocode faithfully
gets uniform splits only, and — because the pipeline is long — will attribute the absence of
non-uniform candidates to the *data* rather than to the rule: "the core-utilisation constraint or the
balance condition excluded them", which is exactly the sentence `pipeline_balancing.md:444` offers as
the explanation for such an outcome (搜索过程中可能发现核利用率约束或配平条件排除了预期方案). So the
defect arrives pre-rationalised.

The other branch is an agent that notices the emptiness and deletes P4. That restores non-uniform
candidates and removes the only check that the short block can actually mask its neighbour, leaving
the search to rank on the theoretical time model alone (0069), which does not model inflation
(0070) — so the top candidates will be the most finely split ones.

## 3 · Ground / Source
The rule table, `:282-287`, states P4 as a *soft* constraint: 配平条件：shortMSize < ρ × longMSize
排除（松约束可降级为惩罚）— the parenthesis explicitly contemplates degrading it to a penalty rather
than an exclusion. The pseudocode implements a hard `continue`, quoted in SOURCE. That mismatch
between the prose row and the code is the first recorded observation (C-950core-002).

The enumeration, `:339-368`, in full:

> for hs = hs_min to hs_max step 16:
>     hc   = M / hs                    // 长块数量
>     tail = M % hs                    // 尾块大小 (= shortMSize)
>     // --- 剪枝 P1: 尾块下限 ---
>     if tail > 0 and tail < 128: continue
>     // --- 剪枝 P3: tileCnt 范围 ---
>     tc = hc + (tail > 0 ? 1 : 0)
>     if tc < tcFloor or tc > tcCap: continue
>     // --- 剪枝 P2: 核利用率（主轮 = 长块）---
>     mBlockCnt = ceil(hs / baseM); totalBlk = mBlockCnt × nBlockCnt
>     utilization = min(totalBlk, N_core) / N_core
>     if utilization < utilThresh: continue
>     // --- 剪枝 P4: 配平条件 ---
>     shortMSize = tail
>     if shortMSize > 0 and shortMSize < ρ × hs: continue

with `ρ = max(R, 1/R)` at `:297` and the claim at `:316` that P1-P4 plus the range derivation reduce
the space to 10-50 candidates rather than M/16.

Why P4 is vacuous is arithmetic, and it is worth writing out because the whole entry rests on it:
`tail = M mod hs` implies `0 ≤ tail < hs`; `ρ ≥ 1` implies `ρ × hs ≥ hs > tail`; so
`shortMSize < ρ × hs` is true whenever `shortMSize > 0`, and the `continue` fires. Only `tail == 0`
survives — a uniform split, for which the balance condition is not evaluated at all.

The root of the inversion is entry 0065: `M_short ≥ ρ × M_long` is version B of the balance
condition, and version A — the one the diagrams, the look-up table and this very `tail = M % hs`
construction all agree with — is `M_short ≥ M_long / ρ`. P4 implements the version that its own
enumeration cannot satisfy.

**Proposal, clearly separated from the above and not established.** If version A is the intended
condition, the corrected predicate is
```
if shortMSize > 0 and shortMSize < hs / ρ:  continue      # PROPOSAL — not upstream's text
```
which is satisfiable, since `tail ∈ [hs/ρ, hs)` is a non-empty interval for `ρ > 1`, and which is
symmetric across the two bound directions: for compute bound (ρ = R) it requires
`β × M_short ≥ α × M_long`, and for communication bound (ρ = 1/R) it requires
`α × M_short ≥ β × M_long`, in both cases "the short block's masked operation covers the long block's
bottleneck operation" with the short block genuinely shorter. This is a proposal about the pipeline,
decided only by the §4 procedure and by 0065's sweep — not a correction this book has verified, and
not a claim that upstream's intent was version A.

## 4 · Procedure
Two arms. Arm 1 needs no device and settles the vacuity claim; arm 2 needs cards and settles which
predicate is right.
```bash
# Arm 1 — execute the published pseudocode as written, over a grid of real inputs.
# Transcribe :330-368 verbatim into a script (no fixes), then sweep:
#   M      ∈ {1024, 2048, 4096, 8192}
#   R      ∈ {0.3, 0.5, 0.95, 1.0, 1.5, 3.0, 9.8}      # the measured range of 0058
#   baseM  ∈ {128, 256}, baseN ∈ {128, 256}, N_core ∈ {20, 24, 32}
# Record, per tuple: candidates emitted, and how many have a non-zero tail.
```
Arm 2 (later phase, needs one card per rank; capture per 0057, R per 0059, TilingData per 0062): for
one operator at R ≈ 3 and one at R ≈ 0.3, generate candidate sets three ways — P4 as published, P4
removed, and P4 replaced by the proposal above — measure the top fifteen of each, and record which
set contains the measured optimum.

## 5 · Checker — acceptance declared before the run
Arm 1 verdict variable `nonuniform_emitted` = the total number of emitted candidates with a non-zero
tail, over the whole grid. The vacuity claim of §1 predicts exactly 0. A single non-zero tail
anywhere refutes it, and the tuple that produced it is reported.

Arm 2 verdict variables `best_in_set(variant)` — whether the measured optimum is inside that
variant's top fifteen — and `T_best(variant)`. Acceptance of the proposal: the proposal's set
contains the measured optimum and `T_best(proposal) ≤ T_best(published)` beyond spread. If P4-removed
also contains it and is no worse, the proposal buys nothing except search cost, and that is reported
too.

Exit code is not the verdict in either arm. Arm 1 publishes the emitted candidate count per tuple
including the tuples that emit nothing at all (P2 or P3 may empty the set independently of P4) —
those must be distinguished from P4-emptied sets by counting prunes per rule, otherwise the vacuity
claim is credited for exclusions it did not cause.

Red input, arm 1: the same script with P4 deleted. It must emit non-zero-tail candidates on the same
grid. If it does not, the emptiness has another cause and the whole reading is wrong.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
The vacuity claim is a reading of published pseudocode, not an execution of it; arm 1 has not been
run. No board, operator, or measurement is implicated in the defect itself. The proposed predicate is
a proposal: it presumes version A of 0065's contradiction, which is unresolved, and it is not
established to be optimal or even feasible on hardware — a split satisfying it may still lose to a
uniform one because of the inflation the theoretical model omits (0070). Nothing here evaluates P1,
P2 or P3, whose thresholds (128, 80%/50%, tcFloor/tcCap) are separately unverified (0067, 0068,
0069). And nothing here establishes what upstream intended; the prose row's "may be degraded to a
penalty" suggests the authors did not consider the rule binding, which is a reading, not a finding.
