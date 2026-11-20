```
ID:        0065-the-balance-condition-is-written-inverted-relative-to-its-own-diagram
LABEL:     trap
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/comm-compute/pipeline_balancing.md:165-166 — "α × M_short ≥ β × M_long    （计算 Bound，短块通信掩盖长块计算） β × M_short ≥ α × M_long    （通信 Bound，短块计算掩盖长块通信）"
           ops/ascendc-perf-optimize/references/comm-compute/pipeline_balancing.md:96-100 — "长块1计算 → 长块2计算 → ... → 长块N计算 → 短块计算 … (无通信)   长块1通信    ...   长块N-1通信   长块N通信 // 约束：compute[long_k] ≥ comm[long_k-1]，短块 comm 尽量短"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured sweep on a named 950 board, compute-bound (R > 1), in which the best split has
           M_short ≥ R × M_long — i.e. a "short" block larger than the long blocks — which would
           vindicate the formula at `:165` and refute the diagram, the naming and the search's own
           `tail = M % hs` construction.
```

# 0065 · The balance condition is written inverted relative to its own diagram

## 1 · Claim
Upstream asserts a balance condition for non-uniform MC² splitting in two mutually inconsistent
forms. The diagrams and the strategy look-up table pair the short block's **computation** against a
long block's **communication**: for a compute-bound, compute-then-comm operator the constraint is
`compute[N] ≥ comm[N-1]` with the short block's communication as short as possible, which in per-row
terms is `β × M_short ≥ α × M_long`, i.e. `M_short ≥ M_long / R`. The formula section states the
opposite pairing for the same case: `α × M_short ≥ β × M_long`, glossed 短块通信掩盖长块计算, which is
`M_short ≥ R × M_long`. With R > 1 the second form requires the short block to be *larger* than the
long block. Not established here which is intended; both are upstream's text, and Art. 7 forbids
resolving it by preference.

## 2 · The wrong branch this removes
An agent implementing the balance condition will take the formula, because the formula is in the
section called 配平公式 and is written as arithmetic. Three things then go wrong at once. The derived
initial values invert: `M_long = M / (longBlockCnt + R)` and `M_short = R × M / (longBlockCnt + R)`
give a short block R times the long block, so the names in the TilingData stop describing the
blocks. The feasible region (`:185`) becomes `M_short ≥ R × M_long`, which the search's own
enumeration cannot satisfy, since it sets `tail = M % hs` and a remainder is always smaller than its
divisor — that is the mechanism of the P4 defect (0066). And the placement matrix's advice, "make the
short block's communication as short as possible", becomes incoherent, because a block that is R
times larger has R times the communication.

The reason this is a trap rather than a typo worth silently fixing: the arithmetic downstream of the
formula is *self-consistent* with the formula. Substituting `M_short = R × M_long` into
`longBlockCnt × M_long + M_short = M` yields exactly the printed initial values, so a reader checking
the algebra finds no error. Only the diagram, the naming, and the search's remainder construction
disagree — three places a formula-checker does not look.

## 3 · Ground / Source
Version A — diagram and look-up table. `pipeline_balancing.md:92-101`, compute-then-comm, compute
bound:

> **计算 Bound**：计算要掩盖通信，最后一块的通信无法被掩盖，因此**短块放最后（drain 端）**。短块通信
> 耗时要尽可能短，对应的计算短块耗时要掩盖住通信的长块耗时。整体上第 N 块的计算耗时 ≥ 第 N-1 块的
> 通信耗时，才能达到掩盖率最优。
> ```
> 短块在后:
>   长块1计算 → 长块2计算 → ... → 长块N计算 → 短块计算
>      ↕掩盖      ↕掩盖              ↕掩盖       ↕(尾通信无法掩盖)
>   (无通信)   长块1通信    ...   长块N-1通信   长块N通信
> 约束：compute[long_k] ≥ comm[long_k-1]，短块 comm 尽量短
> ```

The diagram's last column pairs 短块计算 with 长块N通信. The look-up table at `:150` states the same:
计算后通信 | 计算 Bound | 后（drain 端） | compute[N] ≥ comm[N-1]，尾通信尽量短.

Version B — the formula section. `pipeline_balancing.md:160-166`:

> ### 配平条件
> 使短块与相邻长块完全掩盖——短块的被掩盖操作耗时 ≥ 相邻长块的瓶颈操作耗时：
> ```
> α × M_short ≥ β × M_long    （计算 Bound，短块通信掩盖长块计算）
> β × M_short ≥ α × M_long    （通信 Bound，短块计算掩盖长块通信）
> ```

and its consequences, `:171-176` (initial values) and `:182-194` (feasible region:
`配平条件: α × M_short ≥ β × M_long → M_short ≥ R × M_long`, with `M_long ≤ M / (longBlockCnt + R)`).

The prose sentence at `:82` — 短块的被掩盖操作耗时 ≥ 相邻长块的瓶颈操作耗时 — is the general statement
both versions claim to instantiate, and it does not by itself decide which operation belongs to which
block: for a compute-bound operator the bottleneck operation is computation and the masked operation
is communication, which reads as version B; but the pipeline diagram has the short block's
*computation* overlapping the last long block's *communication*, which is version A. So the
ambiguity is in the prose and the two instantiations differ.

Recorded as C-950core-001. Note what is *not* an inconsistency, because a survey claim suggested it
was: `:175` and `:185` are algebraically consistent with each other and with `:165` — the divergence
is between `:165`/`:175`/`:185` on one side and `:100`/`:150` (and the diagram) on the other.

## 4 · Procedure
Later phase, needs one card per rank. This is a decidable question and the procedure is designed to
decide it by measurement, not by reading (Art. 7).
1. Device selection per 0057; board token per rank from the driver readout; occupancy either side.
2. Take one compute-then-comm operator at a problem size with R ≈ 3 (measured per 0059, not assumed).
3. Fix `longBlockCnt = 3` and enumerate splits by `M_short / M_long` over a range spanning both
   candidate conditions: from `1/(2R)` through `1/R` (version A's boundary) and `1` up to `R`
   (version B's boundary) — at least ten points, 16-byte aligned per 0067, each with its own
   long-block and short-block tiling data (0062).
4. Measure every split per the ten-iteration multi-rank protocol; compute the masking ratio of each
   (0055).
5. Repeat at R ≈ 0.3 for the communication-bound branch, where the two versions swap.

## 5 · Checker — acceptance declared before the run
Verdict variable `argmax_ratio` = the `M_short / M_long` ratio of the split with the lowest measured
T_total, with its neighbours' times and the run spread. Declared readings, fixed before the run:
- `argmax_ratio` at or just above `1/R` → version A holds; the formula section at `:165`/`:175`/`:185`
  is wrong and the search's P4 must be corrected as proposed in 0066;
- `argmax_ratio` at or above `R` → version B holds; the diagram, the look-up table and the
  short/long naming are wrong, and the search's remainder construction cannot express the optimum at
  all;
- `argmax_ratio` in neither region → both conditions are wrong for this operator and the balance
  condition is not the binding constraint; the entry is corrected in place with the measured optimum.

Exit code is not the verdict. The whole sweep is published with spreads, including the region where
the two candidate boundaries fall inside one spread of each other, in which case the verdict is
`indistinguishable` and no version is credited.

Red input: the uniform split (`M_short / M_long = 1`, tail zero), included as a reference point. It
must not be the fastest; if it is, the entire non-uniform apparatus buys nothing on this operator and
the sweep says so before any version wins.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; no board, operator, R value or rank count. It does not say which version is
correct — deliberately, since Art. 7 assigns that to the procedure above and this book has not run
it. The reading that version A is the intended one is *supported* by three independent features of
upstream's own text (the diagram, the naming, and `tail = M % hs`) and is still not established by
measurement. Nothing here covers splits with more than one short block, or operators whose two
phases do not both scale linearly in M — the per-row α and β model (0059) is assumed throughout and
is itself unverified.
