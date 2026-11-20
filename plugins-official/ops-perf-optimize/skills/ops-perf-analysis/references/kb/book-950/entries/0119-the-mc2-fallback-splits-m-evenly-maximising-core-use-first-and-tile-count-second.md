```
ID:        0119-the-mc2-fallback-splits-m-evenly-maximising-core-use-first-and-tile-count-second
LABEL:     procedure
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/tiling/mc2/fallback/tiling-flow.md:82-95,130-170
           and mc2/fallback/script/mc2_tiling.py:39-42 — "排序: 主键 util 降序, 次键 tileCnt 降序
           （即 longMSize 升序）" ; the three degradation levels 放宽对齐到 16 / 允许短块 /
           放宽利用率阈值至 80% ; "UTIL_THRESHOLD_RELAXED = 0.80" · "SHORT_BLOCK_MIN = 16"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured MC² case on a named 950 board where a candidate with lower core utilisation
           but more tiles beats the lexicographic winner — the primary/secondary key order would
           then be wrong, and with it every plan the fallback produces.
```

# 0119 · The MC² fallback splits M evenly, maximising core use first and tile count second

## 1 · Claim
Upstream asserts a four-step equal-split algorithm as the MC² default: compute
`nBlockCnt = ceil(N / baseN)`; derive the full-machine floor
`minMBlockCnt = max(1, ceil(N_core / nBlockCnt))` and `minLongMSize = minMBlockCnt × baseM`;
enumerate candidates `{ k × baseM | k ∈ [minMBlockCnt, M/baseM], (k × baseM) divides M }`; and
sort them lexicographically by utilisation descending, then `tileCnt` descending — equivalently
`longMSize` ascending — taking the first. Upstream states the reasoning for both keys: the primary
key protects the compute-resource floor, and the secondary key maximises the number of
communication/computation overlap windows. Upstream further asserts three ordered degradations when
no perfect even split exists: relax the alignment from `baseM` to 16, then admit exactly one short
block at the drain end with `shortMSize ≥ 16`, then relax the utilisation target to 80 %. Not
established here.

## 2 · The wrong branch this removes
The obvious alternative — cut M into as many tiles as the core count allows, because more tiles
means more overlap — is wrong in a way that only shows up on shapes with a small N. Upstream's own
second worked example is the counter-case: at N=256 with `baseN=128`, `nBlockCnt = 2`, so a single
M block gives only 2 of 8 cores work; the machine is only full at `minMBlockCnt = 4`, i.e.
`longMSize = 512`, which caps `tileCnt` at 4. An agent maximising tiles picks `longMSize = 128`
and runs a 25 %-occupied machine with 16 overlap windows. The primary key exists precisely to stop
that, and no correctness check sees the difference.

The degradation ladder removes a different wrong branch: giving up. `M` prime, or with no factor
that is both a `baseM` multiple and a divisor, is common, and an agent without the ladder either
fails or invents a short block immediately — skipping the 16-alignment step that upstream ranks
above short blocks, because a partial final M block costs some Mac utilisation while a short tile
costs a whole under-occupied pipeline stage at the drain end.

## 3 · Ground / Source
The objective and its ordering, `mc2/fallback/tiling-flow.md:82-95`:

```
Step 4 — 按目标排序选最优:
  对每个候选 longMSize:
    mBlockCnt  = longMSize / baseM
    totalBlk   = mBlockCnt × nBlockCnt
    util       = min(totalBlk, N_core) / N_core
    tileCnt    = M / longMSize

  排序: 主键 util 降序, 次键 tileCnt 降序（即 longMSize 升序）
  选择: 排序后第一个候选即为最优

**为什么这样选**：
- 主键选利用率最高：满核时计算资源不浪费，是性能的基础保障
- 次键选 tileCnt 最多：更多切分 → 通信与计算的 overlap 窗口更多 → 流水掩盖更充分
```

The two worked examples, `:99-128`, re-derived here rather than trusted. Example 1: M=4096,
N=4096, `baseM=baseN=128`, `N_core=8`. `nBlockCnt = ceil(4096/128) = 32`;
`minMBlockCnt = ceil(8/32) = 1` (the ceiling of 0.25 is 1); `minLongMSize = 128`. Candidates 128,
256, 512 … all give `util = 100 %` because `totalBlk ≥ 32 > 8`, so the secondary key decides and
`longMSize = 128`, `tileCnt = 32` wins. Correct as stated. Example 2: M=2048, N=256,
`baseM=baseN=128`, `N_core=8`. `nBlockCnt = ceil(256/128) = 2`; `minMBlockCnt = ceil(8/2) = 4`;
`minLongMSize = 512`. Candidates 512 (`totalBlk = 4×2 = 8`, `util = 100 %`, `tileCnt = 4`), 1024,
2048 — the smallest wins. Correct as stated. Both examples check out; this is the one family in
this domain whose worked arithmetic survives re-derivation intact.

The degradation ladder, `:130-170`, in the order upstream gives it:

```
#### 降级 A：放宽对齐到 16
候选集 = { d | d 整除 M, d ≥ minLongMSize, d % 16 == 0 }
注意: longMSize 非 baseM 倍数时，最后一个 M 方向 block 为部分块（partial block），
      Mac 利用率略有损失，但整体仍优于短块方案

#### 降级 B：允许短块
longMSize   = minLongMSize（或更大，按 tileCnt 目标选）
longBlockCnt = floor(M / longMSize)
shortMSize   = M - longBlockCnt × longMSize
shortBlockCnt = 1（若 shortMSize > 0）
shortBlockPos = 1（默认放后，drain 端）
约束: shortMSize ≥ 16（否则减小 longMSize 或 tileCnt）

#### 降级 C：放宽利用率阈值
若 minLongMSize > M（M 太小无法满核）:
放宽利用率阈值至 80%（或更低）:
  minMBlockCnt = max(1, ceil(0.8 × N_core / nBlockCnt))
  minLongMSize = minMBlockCnt × baseM
若 M < baseM: 单块切分（tileCnt=1），无流水掩盖，仅保证功能正确
```

The script's constants, `mc2/fallback/script/mc2_tiling.py:39-42`:

```python
ALIGN_GRANULARITY = 16
UTIL_THRESHOLD_FULL = 1.0
UTIL_THRESHOLD_RELAXED = 0.80
SHORT_BLOCK_MIN = 16
```

The script's control flow does not match the prose ladder. `equal_split_tiling()` at `:226-254`
runs: main path (`baseM` align, util 1.0) → 16-align (util 1.0, `degrade_level=1`) →
`fallback_short_block(..., UTIL_THRESHOLD_FULL)` and **accepts it only if
`result.utilization >= UTIL_THRESHOLD_RELAXED`** (`:239-240`) → otherwise uniform at relaxed util
(`degrade_level=3`) → 16-align at relaxed util → short block at relaxed util. So the short-block
level carries an 80 % acceptance test that the markdown's 降级 B never mentions, and a short-block
solution below 80 % utilisation is rejected in favour of a relaxed-utilisation uniform solution —
the prose ladder's B-before-C order is conditional in the code and unconditional in the text.
Registered as C-950tiling-008.

Under 0104's provenance rule all four script constants trace to literals with no chip-config
pedigree: `16`, `1.0`, `0.80` and `16` are software 经验值 and are searchable. In particular the
80 % threshold is the boundary between two different plan families and is stated once, with no
derivation.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase. MC² needs
multiple ranks: at most 4 dies, per the shared-machine budget.

Device selection: `npu-smi info -l`; for every candidate chip `npu-smi info -t usages -i <id> -c
<chip>` three times at 20 s spacing; bind only chips idle in all three; record the chip ids;
re-sample all after the run and discard the case if any moved. Never exceed 4 dies. The rank count
is recorded with the result.

Arm 1 — the key order, which is the falsifiable core. Choose a shape where the two keys genuinely
conflict: N small enough that `nBlockCnt < N_core` (N=256, `baseN=128`), M with several admissible
factors (M=6144, `baseM=128`), so candidates exist at `util = 100 %, tileCnt = 12` and at
`util = 50 %, tileCnt = 24`. Build and run both plans plus the two nearest neighbours on each side,
same compiler pin, md5 per binary, host print of the full comm-split parameters and all three
matmul tilings, fp64 reference check within the declared tolerance. Capture per rank, ≥10
iterations, first 5 warm-up, mean of the last 5, maximum across ranks as the case value; no
host-side timing.

Arm 2 — the ladder. Construct three M values that each force a different degradation: M with a
16-aligned divisor but no `baseM`-multiple divisor (level A), M prime (level B), and
`M < minLongMSize` (level C). For each, record which level the script selects, which level the
prose ladder would select, and — where they differ (the 80 % acceptance test at `:239`) — build
and time both, so C-950tiling-008 is resolved by measurement rather than by preferring the code or
the text.

Refuses to assume: that a die free before the run stayed free; that a die may be substituted; that
`N_core` is any script default (it comes from the host TilingData print per 0120, and C-007 records
five incompatible core counts in this subtree); that a key ordering established at one N holds at
another — each N is its own case; that the mean-of-last-5 hides no drift, which is checked on the
retained per-iteration series.

## 5 · Checker — acceptance declared before the run
Verdict variable `lex_wins`: true iff the lexicographic winner's case time is the lowest among the
four built candidates in arm 1. Declared acceptance: the key order is supported iff `lex_wins` is
true. The OVERTURN fires iff a candidate with strictly lower utilisation has a case time lower by
more than 2 % — the secondary key would then outrank the primary on this shape, and every plan the
fallback produces inherits the inversion. Arm 2's verdict `ladder_matches` is a per-M comparison of
script level against prose level, with the disagreement case timed both ways and the faster one
recorded as the finding.

The exit code is not the verdict. Two guards. First, per-rank completeness: a short per-iteration
series from any launched rank fails the check rather than being maxed over, because a stalled rank
produces a flattering maximum. Second, plan identity: the host print of `longMSize`, `tileCnt`,
`shortBlockCnt` and `degradeLevel` must match the requested candidate for every point; a candidate
the tiling engine silently replaced would otherwise be timed under the wrong label and could make
`lex_wins` true by accident. The checker goes red on any mismatch.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured; no rank was launched. The entry does not establish that utilisation should
outrank tile count, that 80 % is the right relaxed threshold, or that `shortMSize ≥ 16` is a real
floor rather than a chosen one. It does not resolve the script-versus-prose ladder disagreement —
that is C-950tiling-008 and Art. 7 forbids resolving it by preferring an author. It does not
establish that the equal-split fallback is worse than the long/short balancing path it defers to;
upstream says balancing is theoretically optimal but needs isolation-test α/β/R values, and none of
that is measured here. `utilization` as defined can never exceed 1 and `minMBlockCnt` can never be
0, so both are floored quantities and the objective ranks fewer candidates apart than its form
suggests. No board is named anywhere in the MC² directory, so BOARD is
`family-claimed(unverified)` and the chip is unstated; §4 names 950PR/950DT because that is where
our run would happen. Nothing here is established for any 910-family board.
