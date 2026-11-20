```
ID:        0029-load-the-loop-invariant-once-and-pack-short-rows-into-one-vector-length
LABEL:     knowledge
LEVEL:     L5 (compute & numerics)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/single-core-pipeline/techniques/vec-06-broadcast-once-vl-merge.md:13-15 — "a 轴常量跨行共享 → 用 `DataCopy<..., DIST_BLK>` 广播到整个 VL，**循环外只 load 一次** … 单行太短填不满一拍 → 把多行 packed 进一个 VL（`mergeNum = VL_FP32 / aFactorAlign`）… 行内归约用**蝶式 `DeInterleave`×log2(R) + `Max`/`Add` 组内规约、再 `Interleave` 广播回本行**"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a paired build on a named 950 board at small A and R ≪ VL in which packing multiple
           rows into one vector length does not reduce `aiv_time` beyond run spread — lane
           utilisation would then not be the constraint the card says it is.
```

# 0029 · Load the loop invariant once and pack short rows into one vector length

## 1 · Claim
Upstream asserts (card vec-06, 性能数据 待实测) three related moves for kernels whose rows are
short relative to a vector beat: broadcast an a-axis constant (mean, rstd, gamma) to a full VL
once outside the loop with `DataCopy<..., LoadDist::DIST_BLK>` and reuse it instead of reloading
per iteration; pack `mergeNum = VL_FP32 / aFactorAlign` rows into a single vector register and
compute them in one instruction under `UpdateMask`; and, when the reduction axis R is much
shorter than a VL, gather VL/R rows into one full register and reduce inside it with a butterfly
of `DeInterleave` × log2(R) plus `Max`/`Add`, broadcasting back with `Interleave`, rather than
issuing narrow-mask `ReduceMax`/`ReduceSum` per row. Not established here.

## 2 · The wrong branch this removes
A kernel whose rows are 8 or 16 elements wide looks efficient: every instruction is a vector
instruction, the VECTOR lane is busy, `aiv_vec_ratio` is high, and the routing tree says VEC
bound. What the ratio cannot show is that each beat lights a handful of lanes out of sixty-four.
An agent reading only ratios will try to reduce the number of vector instructions — fusion,
LUTs — when the available factor is in the width of each one. The second wrong branch is
narrower and comes from the card's own stop rules: an agent that packs rows without also relaxing
the host-side dispatch threshold produces a kernel branch that never receives the small-A shapes
it was written for, and measures no change because no traffic arrives.

## 3 · Ground / Source
`vec-06:6-9` diagnostic: MTE2 saturated with the same a-axis constant reloaded every iteration;
row element count far below one beat's lane count, so register utilisation is low; or a reduction
axis R ≪ VL where `ReduceMax`/`ReduceSum` is issued repeatedly under a narrow mask.

`vec-06:20-27` gives the broadcast helper — `DataCopy<float, MicroAPI::LoadDist::DIST_BLK>(dst,
(__local_mem__ float*)in + offset)` — with the instruction that the entry point calls it once per
constant (mean/rstd/gamma/dbeta/dgamma) and the R loop never reloads, and that the inner loop runs
`loopTimes = CeilDiv(rLength, mergeNum)`.

Stop rules, `vec-06:34-39`, all four load-bearing:
> - packed layout 要求 UB 内数据已按 `aFactorAlign_` 对齐连续摆放，装载阶段需保证该布局。
> - 该策略常需**同时放宽 host tiling 的 dispatch 阈值**，让"小 A"形状真正走到这个 kernel 分支，
>   否则改了 kernel 也接不到流量（属 tiling 联动，见 `../../tiling/`）。
> - 只对"a 轴常量跨行共享"成立；逐行变化的数据不能广播复用。
> - pack 多行 + 蝶式归约需 **R 为 2 的幂**（蝶式级数 = log2(R)）；数据须紧凑连续（`R*R`），
>   buffer/CopyIn/CopyOut 须成套改；尾段用 `act=dim0*R` 收窄 mask，勿越界。

Cases at `:43`: batch-norm-grad small-A add-broadcast VL merge; hc-pre short-row pack plus
butterfly reduction. The symbol `VL_FP32` in `mergeNum` is used as a constant here while 0252
requires the lane count to come from `GetVecLen()/sizeof(T)` — the same tension noted there.

## 4 · Procedure
Later phase, needs a card; device selection per 0010, board token from the driver readout.
1. Build one layer-norm-style operator three ways from a common tree: (B) baseline, per-row
   constant reload and per-row narrow-mask reduce; (I) invariant broadcast once, rows unpacked;
   (P) invariant broadcast plus row packing and butterfly reduction. Record `md5sum` of each.
2. Sweep the row length R over powers of two from 4 to one full VL, and separately over one
   non-power-of-two value, which the card's stop rule excludes — the excluded case is run to
   confirm the exclusion is real rather than assumed.
3. Ensure the host dispatch threshold admits every shape to the intended branch, and verify per
   shape which branch executed; a shape that fell to another branch is reported, not averaged in.
4. Capture `aiv_time`, `aiv_mte2_ratio`, and lane utilisation from the instruction trace; five
   repetitions; median and spread; precision regression on all three builds.

## 5 · Checker — acceptance declared before the run
Verdict variables `gain_I` and `gain_P` against B, per R, and `lanes_lit(build, R)` from the
trace. Acceptance: `gain_I > spread` wherever the constant is genuinely reloaded in B;
`gain_P > gain_I` for R ≤ VL/4; and `lanes_lit(P) ≈ VL` where B lights only R. The lane count is
the mechanism check — a gain without more lanes lit came from elsewhere.

Exit code is not the verdict. Every shape reports which kernel branch ran, and a run in which the
intended branch did not execute is `branch_not_reached`, never a measured zero — that specific
confusion is what the card's dispatch-threshold stop rule warns about.

Red input: the non-power-of-two R. The butterfly path must refuse it or fall back; if it silently
produces a result, the exclusion in the stop rule is not enforced and the output must be checked
element-by-element before any timing is believed.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; 待实测 upstream. `VL_FP32` is not established for any board (0252, 0018). No
shape, board or operator family is established, and the butterfly path is claimed only for R a
power of two with contiguous `R*R` data. It does not establish the host-side threshold change the
technique depends on — that is a tiling-side edit outside this entry, and outside this agent's
scope. It says nothing about dtypes other than fp32, whose VL and therefore whose `mergeNum`
differ.
