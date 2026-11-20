```
ID:        0036-an-int64-regtensor-occupies-two-physical-registers-so-source-counts-hide-spills
LABEL:     knowledge
LEVEL:     L5 (compute & numerics)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/single-core-pipeline/techniques/vec-12-preg-split.md:9 — "常见于 int64：arch3510 无原生 int64 计算单元，int64 用 `RegTensor<T, RegTraitNumTwo>` 表达（一个逻辑 int64 = 2 个物理 32-bit 子寄存器 `reg[0]/reg[1]`），**实际 preg 占用 ×2**，源码寄存器数看不出已超"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a trace on a named 950 board showing spill/reload pairs in a VF whose live 64-bit
           logical registers, counted at ×2, are well within the physical budget — the ×2 model
           would then not explain the spills and the split would be aimed at the wrong quantity.
```

# 0036 · An int64 RegTensor occupies two physical registers, so source counts hide spills

## 1 · Claim
Upstream asserts (card vec-12, 性能数据 待实测) that arch3510 has no native int64 compute unit, so
an int64 value is expressed as `RegTensor<T, RegTraitNumTwo>` — one logical int64 held in two
physical 32-bit sub-registers — and therefore consumes twice the physical register budget that
the source suggests; that unexplained spill/reload pairs inside a VF segment are the symptom; and
that the repair is to split the VF into two variants along a runtime condition so that each path
holds fewer live logical registers. Not established here.

## 2 · The wrong branch this removes
Register pressure is normally diagnosed by counting declarations. With a doubled representation
that count is wrong by a factor of two for exactly the type most likely to be near the limit, so a
developer sees eight registers where the hardware sees sixteen, concludes there is headroom, and
looks elsewhere for the periodic bubbles. The bubbles then get attributed to a dependency chain
and treated with more accumulators (0031), which adds registers and makes the spilling worse.
The two diagnoses are opposite treatments of similar-looking traces, and this entry is the
discriminator: check the trace for spill/reload pairs, and count 64-bit logicals twice.

## 3 · Ground / Source
`vec-12:6-9` diagnostic: abnormal preg spill/reload pairs in the VF segment even though the source
register count looks within budget; common with int64 for the reason quoted in SOURCE.

`vec-12:18-27` after-form: branch at the VF entry on a runtime condition —
`if (dimR < VL) { VF_small(...); return; } VF_full(...);` — with the comment 小 R：不需要跨块两两
比较，砍掉 value1/level1 两个 int64 逻辑寄存器 = 省 4 个 preg. The before-form runs the full path
unconditionally, so small-R cases hold the large-R registers for nothing. A secondary move at
`:27`: use `DeInterleave` to merge int64 high and low halves instead of `Mul(twoMask)` plus
`ReduceSum(twoMask)`, reducing intermediates and masks.

Stop rules, `vec-12:34-37`: acceptance is that the spill/reload pairs disappear from the trace —
counting source registers is explicitly not acceptance; the two split paths must be functionally
equivalent, and a split along a dimension that does not actually reduce live registers leaves both
paths spilling; the split adds a branch and code, so if the cost exceeds the gain, change the
dimension or reduce pressure another way.

The representation half of the claim has independent support from the installed toolkit, recorded
here and used in 0037 rather than promoted into this entry's §1: at
`.../reg_compute/dav_c310/kernel_reg_compute_vec_binary_impl.h:1857-1863`, an 8-byte element type
takes a branch constructing `RegTensor<ActualT, RegTraitNumTwo>`. That corroborates the two-register
representation. It does not corroborate the ×2 preg *cost*, which is a claim about allocation.

## 4 · Procedure
Later phase, needs a card; device selection per 0010, board token from the driver readout.
1. Build one argmax-style VF that holds N live int64 logical registers, parameterised so N can be
   set at compile time; sweep N upward until spill/reload pairs appear in the trace, and record
   the N at which they do. Repeat the sweep with int32 logicals in place of int64.
2. Record `md5sum` per build; capture the instruction trace and count spill/reload pairs per VF
   segment; capture `aiv_time`, five repetitions, median and spread.
3. Build the split form (VF_small / VF_full) at an N above the spill threshold and re-capture both
   the spill count and `aiv_time` for the small-R and large-R inputs separately.

## 5 · Checker — acceptance declared before the run
Verdict variables `N_spill(dtype)` — the first N at which spill/reload appears — and
`spills(split, input)`. Acceptance of the ×2 model: `N_spill(int64) ≈ N_spill(int32) / 2`, within
one register. Acceptance of the repair: `spills(split, small-R) == 0` with `aiv_time` improved
beyond spread, while the large-R path is unchanged. `aiv_time` alone is not acceptance — the
card's own stop rule says the trace must show the spills gone, and this checker enforces that.

Exit code is not the verdict. The spill counter asserts it can find spill/reload markers at all
by running first on a deliberately over-subscribed build; if that build reports zero spills, the
counter is blind and no other reading is admissible.

Red input: the over-subscribed build just described. It must report a non-zero spill count.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; 待实测 upstream. The physical register budget of this architecture is not
established anywhere in this book, so "×2 of what" has no denominator yet. The absence of a
native int64 compute unit is asserted, not verified. It does not establish that splitting is the
best repair — shortening live ranges or reusing registers are alternatives the card names without
comparing. No board, shape or dtype coverage is established beyond int64, and nothing transfers to
the 910 book.
