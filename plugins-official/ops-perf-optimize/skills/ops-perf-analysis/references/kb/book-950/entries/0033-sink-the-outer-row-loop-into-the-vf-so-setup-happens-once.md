```
ID:        0033-sink-the-outer-row-loop-into-the-vf-so-setup-happens-once
LABEL:     knowledge
LEVEL:     L5 (compute & numerics)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/single-core-pipeline/techniques/vec-09-loop-sink-into-vf.md:13 — "把外层 `for` 折进 VF，用 `dimA` 形参在 VF 内承接（`for (a < dimA)`），mask / 常量寄存器等固定 setup 移到内层循环外**只做一次**，消除 N 次进出 VF 与 N 次重复 setup"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a paired build on a named 950 board with many short rows in which sinking the outer
           loop leaves `aiv_time` unchanged beyond spread while the repeated setup micro-ops
           disappear from the trace — the VF entry and setup cost would then not be on the
           critical path.
```

# 0033 · Sink the outer row loop into the VF so setup happens once

## 1 · Claim
Upstream asserts (card vec-09, 性能数据 待实测) that calling a VF once per row from a scalar
`for` loop outside it repeats the VF entry and its fixed setup — mask creation, `vbr`/`vdup`,
constant-register initialisation — once per row; and that folding the loop into the VF, passing
the row count as a `dimA` parameter and hoisting the setup above the inner loop, removes N VF
entries and N setups. Not established here.

## 2 · The wrong branch this removes
Per-row VF calls are the natural decomposition: one row is one unit of work, the VF signature
stays simple, and the call site reads well. The cost is a head cost that no ratio names — it
appears in the trace as repeated identical setup micro-instructions and as a SCALAR lane busy
between VF segments, which the scalar diagnosis page (0017) would attribute to per-tile fixed
cost. An agent that does not know this technique will try to reduce the scalar work rather than
to change how often the VF is entered.

## 3 · Ground / Source
`vec-09:6-9` diagnostic: the caller loops outside the VF and invokes it per row with `dimA=1`; the
trace shows the VF segment starting and stopping repeatedly with identical setup micro-ops
recurring — the card names this 头开销大, a high Setup share.

`vec-09:17-27`, before and after:
> for (a = 0; a < processNum; a++) VF(dst[a], src[a * R], /*dimA=*/1, R);
> VF(dst, src, /*dimA=*/processNum, R);
> //   <一次性 setup：mask / 常量寄存器 / DuplicateConst>
> //   for (uint32_t a = 0; a < dimA; ++a) { <逐行计算，复用上面的 setup> }

Stop rules, `vec-09:34-37`: the technique holds only when the setup is genuinely reusable across
rows and rows are independent; it does not apply when setup must vary with `a`, or when the
batched `dimA` blows the register budget or lengthens the VF body past instruction-cache or
register limits; and a beat with fewer than 32 active lanes is not worth starting a VF for at all.

Cases at `:41`: argmax-with-value (outer loop sunk plus an int64 preg split — the two changes
interact, and the split is 0036), and fused-causal-conv1d (outer j loop sunk). Note the
interaction: sinking increases the live-register pressure inside one VF, which is precisely the
condition 0036 repairs, so the two cards are frequently applied to the same kernel in opposite
directions.

## 4 · Procedure
Later phase, needs a card; device selection per 0010, board token from the driver readout.
1. Build one row-wise operator two ways from a common tree: (O) VF called per row with `dimA=1`;
   (S) one call with `dimA=processNum` and hoisted setup. Record `md5sum` of both objects.
2. Sweep row count over four values spanning 64× at fixed short row length, then sweep row length
   at fixed row count — the claim is about per-entry cost, so it must scale with entries, not
   with elements.
3. Capture `aiv_time`, `aiv_scalar_ratio`; five repetitions, median and spread; from the trace,
   count VF segment starts and count occurrences of the setup micro-op sequence.
4. Record peak live-register usage or spill/reload counts for build S, since the stop rule
   predicts they rise.

## 5 · Checker — acceptance declared before the run
Verdict variables `gain(rows)`, `vf_entries(build)`, `setup_ops(build)`, `spills(build)`.
Acceptance: `vf_entries(S) == 1` per kernel invocation against `rows` for O; `setup_ops(S)` at
most one per invocation; `gain` increasing with row count and roughly flat in row length. A gain
that scales with row *length* instead would mean something other than entry cost changed.

Exit code is not the verdict; the trace counter asserts it matched at least one VF-entry marker
in build O before reporting any count for S.

Red input: the long-row, few-rows configuration, where the card predicts little or no gain. If
the gain is large there too, the attribution to entry and setup cost fails and is reported as
such rather than folded into an average.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; 待实测 upstream. It does not establish the size of a VF entry cost, nor the
32-lane threshold below which a VF is not worth starting — that number is asserted in vec-03 and
repeated here without derivation. It does not establish where the register-pressure boundary lies
for a sunk loop. No board, shape, or dtype is established.
