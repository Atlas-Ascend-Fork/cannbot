```
ID:        0034-unroll-only-loops-whose-trip-count-is-a-compile-time-constant-and-tiny
LABEL:     knowledge
LEVEL:     L5 (compute & numerics)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/single-core-pipeline/techniques/vec-10-small-loop-unroll.md:13 — "把小定长循环完全展开，消除循环控制开销（计数、分支判断），把各迭代的独立指令暴露给调度器，增大指令级并行"
           ops/ascendc-perf-optimize/references/single-core-pipeline/techniques/vec-10-small-loop-unroll.md:35-36 — "仅对**编译期常量、次数很小**的循环做；大循环全展开会爆指令 cache … 展开后注意寄存器数量是否超限（超了反而 spill，得不偿失）"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a paired build on a named 950 board in which fully unrolling a compile-time K=3 loop
           changes `aiv_time` by less than run spread — the loop-control overhead would then be
           negligible and the technique inert for that kernel.
```

# 0034 · Unroll only loops whose trip count is a compile-time constant and tiny

## 1 · Claim
Upstream asserts (card vec-10, 性能数据 待实测) that a very small loop whose trip count is known
at compile time — a convolution kernel width of three, two sequence positions — should be fully
unrolled, removing the counter and branch and exposing the iterations' independent instructions to
the scheduler; and that the technique is bounded on both sides: a large unrolled loop overflows
the instruction cache, and an unroll that pushes the register count past the budget spills and
loses more than it gains. Not established here.

## 2 · The wrong branch this removes
Two branches meet here and the card names both. An agent that has read about unrolling applies it
to whatever loop is hot, including loops whose count varies with shape — which is a correctness
error, not a performance one (0032). An agent that has read the caution against unrolling leaves
a K=3 loop as written, paying counter and branch cost per iteration on a body of two
instructions. The discriminator is stated and cheap: is the count a compile-time constant, and is
it small? Everything else routes elsewhere — variable counts to 0031's constant-step form, large
counts nowhere.

## 3 · Ground / Source
`vec-10:6-9` diagnostic: the inner VF loop has a very small, compile-time-known count; the VECTOR
lane shows bubbles that instruction-level parallelism could fill, and loop control is a
non-trivial share.

`vec-10:18-26`, before and after:
> for (uint32_t k = 0; k < 3; ++k) {          // K=3，编译期已知
>     Mul(acc, in[k], weight[k], m); Add(sum, sum, acc, m);
> }
> Mul(a0, in[0], weight[0], m);  Mul(a1, in[1], weight[1], m);  Mul(a2, in[2], weight[2], m);
> Add(sum, a0, a1, m);           Add(sum, sum, a2, m);

Note what the after-form also does, beyond removing the counter: it breaks the accumulator chain
by using three destinations and merging them, which is 0031's mechanism at a compile-time size —
so a measured gain here has two candidate causes and the procedure below must separate them.

Stop rules, `vec-10:35-37`, quoted in SOURCE plus the third: a runtime trip count is out of scope
and belongs to vec-08's constant-step form. Case at `:41`: fused-causal-conv1d VF kernel unroll,
K=3 and two sequence positions fully expanded.

## 4 · Procedure
Later phase, needs a card; device selection per 0010, board token from the driver readout.
1. Build one K=3 convolution-style VF three ways from a common tree: (R) the rolled loop; (U) the
   fully unrolled form as printed in the card, with three accumulators; (U1) fully unrolled but
   accumulating into a single register in the original order. U1 exists to separate loop-control
   removal from dependency-chain breaking.
2. Sweep K over {2, 3, 4, 8, 16, 64} as compile-time constants, so the instruction-cache boundary
   the card warns about is approached from below.
3. Capture `aiv_time`, `aiv_vec_ratio`; five repetitions, median and spread; record instruction
   count and spill/reload count per build from the disassembly.
4. Compare outputs against a host reference; note that U reorders the accumulation and U1 does not.

## 5 · Checker — acceptance declared before the run
Verdict variables `gain_U(K)`, `gain_U1(K)`, `spills(K)`, `icount(K)`. Acceptance for the card's
stated mechanism — loop-control removal — is `gain_U1(3) > spread`; if only `gain_U(3)` is
positive, the win is the accumulator split and the card's explanation is incomplete. The upper
bound is checked by `gain_U(K)` turning non-positive at some K, with `spills(K)` or `icount(K)`
rising at the same K; a decline with neither rising leaves the cause unattributed and is reported
that way.

Exit code is not the verdict. Bit-exactness is reported per build: U1 must match the rolled build
exactly, U need not.

Red input: K=64 unrolled. It must not beat the rolled form. If it does, the instruction-cache
caution is not operative at these sizes and the entry is corrected in place rather than the result
being set aside.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; 待实测 upstream. Neither bound has a number: "次数很小" and "大循环" are not
quantified anywhere, and no instruction-cache size or register budget for this architecture is
established in this book. It does not establish which of the two mechanisms in the after-form
supplies any gain. No board, shape or dtype is established, and nothing here applies to runtime
trip counts.
