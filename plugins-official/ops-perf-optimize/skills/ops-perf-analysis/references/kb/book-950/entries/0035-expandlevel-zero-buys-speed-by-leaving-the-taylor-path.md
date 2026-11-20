```
ID:        0035-expandlevel-zero-buys-speed-by-leaving-the-taylor-path
LABEL:     knowledge
LEVEL:     L5 (compute & numerics)
STRATUM:   harvested — upstream text; a read of the installed headers supports part of the
           mechanism and not the description; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/single-core-pipeline/techniques/vec-11-reduce-compute-lut.md:14 — "超越函数内部用 Taylor 级数展开，每个元素数十条 FMA，是计算量主源。查表（LUT）+ 插值用少量指令逼近同一函数值，直接减少向量指令数。CANN 的 `Exp<T, expandLevel, isReuseSrc>` 把 `expandLevel = 0` 设为内部查表+插值模式"
           INSTALLED TOOLKIT (read-only, second origin for the routing fact only): /usr/local/Ascend/cann-9.0.0-beta.2/arm64-linux/asc/impl/adv_api/detail/math/exp/exp_c310_impl.h:117-120 — "if constexpr (taylorExpandLevel == 0) { Exp<T>(dstLocal, srcLocal, calCount); return; }"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a paired run on a named 950 board where `Exp<float, 0, false>` is not faster than
           `Exp<float, 2, false>` beyond run spread, or where its maximum relative error is no
           worse — either would falsify the stated precision-for-speed trade in one direction or
           the other.
```

# 0035 · expandLevel zero buys speed by leaving the Taylor path

## 1 · Claim
Upstream asserts (card vec-11, 性能数据 待实测) that hardware transcendental functions are
implemented by Taylor expansion costing tens of fused multiply-adds per element; that a lookup
table with interpolation approximates the same value in far fewer instructions; and that CANN's
`Exp<T, expandLevel, isReuseSrc>` selects an internal LUT-plus-interpolation mode at
`expandLevel = 0`. Not established here. A read-only inspection of the installed CANN
9.0.0-beta.2 headers confirms the *routing* half — at `taylorExpandLevel == 0` the advanced-API
implementation delegates to the basic `Exp<T>` and returns before the Taylor path — and does not
show what the basic implementation does, so "LUT plus interpolation" is unsupported by that read.

## 2 · The wrong branch this removes
Where a transcendental dominates, the micro-architectural cards have little left to give (0015's
top rung), and an agent without this option concludes the kernel is irreducible. The card's real
content is that a cheaper approximation is reachable through a template parameter rather than by
rewriting the function — and that it is a trade, not a free win.

The wrong branch on the other side is the one the card explicitly forbids: hand-trimming Taylor
terms (12 → 8) inside the implementation. That gets the same speed with an unstated error bound
and no way to reason about it, and it diverges from the vendor's implementation at the next
toolkit update.

## 3 · Ground / Source
`vec-11:6-10` diagnostic: deep VEC bound (`aiv_vec_ratio` > 90%) on an elementwise or activation
operator; transcendental instructions (`vec_exp`/`vec_log`/`vec_tanh`) above 30% of the VECTOR
lane, where DoubleBuffer, fused instructions and bank alignment have already been exhausted; the
computation itself is the bottleneck.

`vec-11:18-25` before/after: `Exp<float, /*expandLevel=*/2, false>` becomes
`Exp<float, /*expandLevel=*/0, false>`, with the note that Log/Tanh follow the same pattern.

Stop rules, `vec-11:32-35`: it is 精度换性能 and must pass the precision regression, especially on
fp32 high-precision paths; hand-trimming Taylor terms is **不推荐**; and the availability of a
lookup mode and its parameter must be confirmed from the devkit or official documentation rather
than recalled from memory.

That last stop rule is the one this entry acts on. Read-only, at the installed pin:
- `impl/adv_api/detail/math/exp/exp_c310_impl.h:102,117-120` — the c310 (arch35 / 950-family)
  implementation takes `uint8_t taylorExpandLevel` and, at level 0, calls `Exp<T>(dstLocal,
  srcLocal, calCount)` and returns, bypassing `ExpAPI::ExpCompute<T, taylorExpandLevel>`;
- `exp_common_impl.h:40` — the template's default is `uint8_t expandLevel = 10`, not 2;
- `impl/simt_api/cpp/dav_c310/kernel_simt_transcendental_impl.h:375-388` — a `TaylorExpand`
  helper whose loop runs `for (int i = expandLevel - 1; i > 0; i--)`, i.e. the parameter is a
  Taylor order in that implementation too.
So the parameter's name and the level-0 branch are confirmed; the words "查表 + 插值" describe the
basic `Exp<T>` implementation and are not visible in these headers. Recorded as C-950core-010,
with the default-value discrepancy (2 in the card's before-form against a template default of 10)
as C-950core-011.

## 4 · Procedure
Later phase, needs a card; device selection per 0010, board token from the driver readout.
1. Build one exp-dominated elementwise kernel at `expandLevel` ∈ {0, 2, 10}, everything else
   identical; record `md5sum` of each object.
2. Capture `aiv_time` and `aiv_vec_ratio`, five repetitions, median and spread; from the
   disassembly, count vector instructions per element for each level.
3. Compute the maximum relative error of each build against a double-precision host reference over
   an input set that includes the argument ranges where an interpolated table is weakest — near
   zero, near the overflow boundary, and at a dense sweep in between.
4. Repeat for `half` as well as `float`, since the c310 implementation's `static_assert` admits
   both and the precision consequences differ.

## 5 · Checker — acceptance declared before the run
Verdict variables `gain(level)`, `instr_per_elem(level)`, `maxRelErr(level, dtype)`. Acceptance of
the trade as stated: `gain(0) > spread`, `instr_per_elem(0)` well below `instr_per_elem(2)`, and
`maxRelErr(0)` strictly worse than `maxRelErr(2)` yet within the dtype threshold from 0021. If
`maxRelErr(0)` is not worse, the level-0 path is not an approximation and the card's description
of it is wrong even though its advice is harmless.

Exit code is not the verdict. The error sweep reports the argument at which the maximum occurred,
not just its magnitude — a maximum that always lands at the same input is a boundary artefact and
must be visible as such.

Red input: the near-overflow argument range. It must be included and reported separately; a
precision check over a benign uniform range would hide exactly the failure mode a table-based
approximation has.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured. The LUT-plus-interpolation description is not established: the installed headers
show only that level 0 leaves the advanced-API Taylor path. No board, shape or dtype is
established. It does not establish the same behaviour for Log, Tanh, Sigmoid, GELU or Softmax —
the card generalises to them and this entry does not. It does not establish that the parameter
means the same thing across CANN versions, and the observed template default (10) differs from
the card's illustrative before-value (2), which is itself unexplained.
