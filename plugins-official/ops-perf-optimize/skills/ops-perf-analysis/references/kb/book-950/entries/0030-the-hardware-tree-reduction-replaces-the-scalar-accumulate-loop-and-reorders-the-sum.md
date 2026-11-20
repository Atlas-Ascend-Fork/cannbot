```
ID:        0030-the-hardware-tree-reduction-replaces-the-scalar-accumulate-loop-and-reorders-the-sum
LABEL:     knowledge
LEVEL:     L5 (compute & numerics)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/single-core-pipeline/techniques/vec-07-low-latency-reduce.md:14 — "手写 `for` 逐元素归约是单累加器 RAW 串行链，链长 ≈ 元素数，硬件无法并行。硬件树形归约指令（`ReduceSum`/`ReduceMax`/`ReduceMin`）内部按树形两两合并，链长降到 log 级，并吃满 lane"
           ops/ascendc-perf-optimize/references/single-core-pipeline/techniques/vec-07-low-latency-reduce.md:36 — "树形归约**改变浮点累加次序**，与串行结果不 bit 一致——fp32 中间累加缓解，须过 `func_cases` 精度回归"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a paired build on a named 950 board where the hardware tree reduction is not faster
           than a scalar accumulate loop over the same element count beyond run spread; or one
           where the two produce bit-identical results, which would falsify the reordering
           warning and remove the precision obligation it imposes.
```

# 0030 · The hardware tree reduction replaces the scalar accumulate loop and reorders the sum

## 1 · Claim
Upstream asserts (card vec-07, 性能数据 待实测) that a hand-written element-wise accumulation
loop is a single-accumulator RAW chain whose length is the element count, that the hardware
reduction instructions (`ReduceSum`/`ReduceMax`/`ReduceMin`) merge pairwise in a tree so the chain
falls to logarithmic length while filling the lanes, and that the substitution changes the
floating-point accumulation order so results are not bit-identical to the serial version — an
fp32 intermediate mitigates it and the precision regression must still pass. Not established here.

## 2 · The wrong branch this removes
The hand-written loop is not merely slow because it is scalar; it is slow twice over. Each
iteration is a `GetValue`, which is a scalar pull with its V_S/S_V synchronisation (0026), and
the accumulator dependency prevents any of them from overlapping. An agent that vectorises only
the multiply and leaves the accumulation as written keeps the second cost and reports a
disappointing gain.

The opposite wrong branch is the reason this entry is `knowledge` and not a recipe: substituting
a tree reduction silently changes numerical results. A team that treats bit-exactness against a
previous release as its correctness criterion will see a regression and blame the wrong change.
The card states the trade explicitly, which is what makes it usable — the substitution is
admissible only after the precision regression, not before.

## 3 · Ground / Source
`vec-07:6-10` diagnostic: the operator contains a reduction implemented as a hand-written `for`;
the VECTOR lane shows periodic bubbles from waiting on the accumulator write-back; reduction
instructions are a visible share of a high `aiv_vec_ratio`.

`vec-07:18-27`, before and after:
> float acc = 0.0f;
> for (uint32_t i = 0; i < count; ++i) { acc += src.GetValue(i); }  // 逐元素标量累加，V_S/S_V 同步伤流水
> ReduceSum(dstLocal, srcLocal, workLocal, count);   // 树形归约，lane 并行

Stop rules, `vec-07:34-38`: the order change and the resulting bit-inexactness, quoted in SOURCE;
`ReduceSum`/`Brcb` require 64-alignment so buffers must be allocated accordingly; the result lands
in lane 0 and must be broadcast (`Duplicate`/`Brcb`) before element-wise use — the same lane-0
constraint that 0027's form B turns into an optimisation.

Related cards: `vec-06` for R ≪ VL, where the card redirects to the butterfly form rather than
this one (0029); `vec-08` for the case where the chain is across iterations rather than within a
row (0031). The three form a set: within-row and short → butterfly; within-row and long →
hardware reduce; across iterations → multiple accumulators.

## 4 · Procedure
Later phase, needs a card; device selection per 0010, board token read from the driver.
1. Build one reduction operator two ways from a common tree: (L) scalar accumulate loop; (T)
   hardware `ReduceSum`. Record `md5sum` of both objects.
2. Sweep `count` over four values spanning 64× so the log-versus-linear chain claim is testable
   as a scaling statement rather than a single ratio.
3. Capture `aiv_time`, `aiv_vec_ratio`, `aiv_scalar_ratio`; five repetitions; median and spread.
4. Compute, for the same inputs, the double-precision reference sum on the host; record the
   relative error of both builds against it, and record whether L and T agree bit-for-bit.

## 5 · Checker — acceptance declared before the run
Verdict variables `gain(count)`, `bitequal(L,T)`, and `relerr(build)` against the host reference.
Acceptance for the mechanism: `gain` grows with `count` — a constant-factor gain would indicate
the win is the removal of the scalar pulls rather than the shortened chain, which is a different
claim from the one the card makes. Acceptance for the warning: `bitequal(L,T)` is false and
`relerr(T)` is within the dtype threshold from 0021.

Exit code is not the verdict; the comparison is over the returned scalar, and a build that
returns the same value because the reduction never executed is caught by asserting the result
differs from the initial accumulator value on non-trivial input.

Red input: an input whose exact sum is representable, e.g. a small count of powers of two. Both
builds must return it exactly and `bitequal` must be true there — if the checker reports
non-bit-equality on a case where reordering cannot matter, the difference is coming from
something other than the summation order and the whole comparison is void.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; 待实测 upstream. It does not establish the magnitude of the reordering error for
any dtype or distribution — only that it exists. The 64-alignment requirement is asserted with no
unit and unverified. No board, shape or dtype is established, and nothing here covers `ReduceMax`
or `ReduceMin`, whose reordering is exact and whose precision obligation is therefore different —
the card groups all three, and that grouping is upstream's, not this book's.
