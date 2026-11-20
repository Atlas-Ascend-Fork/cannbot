```
ID:        0071-local-matmul-is-the-first-choice-and-does-not-wait-for-a-bound-verdict
LABEL:     knowledge
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/comm-compute/local_matmul.md:9 — "通算融合算子按 M 维度切分后，每个 tile 的数据需要跨卡通信再做 matmul。但本 rank 自身的数据无需通信——这部分 Local 数据可以提前（或延后）独立计算，与首次通信重叠执行，从而隐藏通信延迟"
           ops/ascendc-perf-optimize/references/comm-compute/index.md:3 — "Local Matmul 是首选优化策略（不依赖 Bound 判定），流水配平在此基础上进一步优化长短块排布。两者结合使用，推荐优先分析和实现 Local Matmul"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured MC² case on a named 950 board where extracting the local rank's data into an
           independent matmul overlapped with the first communication does not reduce T_total beyond
           run spread — the first communication would then not be exposed, and the "first choice"
           ranking would be wrong for that operator.
```

# 0071 · Local Matmul is the first choice and does not wait for a bound verdict

## 1 · Claim
Upstream asserts that after an MC² operator is split along M, each tile's data must be communicated
before it can be multiplied — except the local rank's own share, which needs no communication and can
therefore be computed independently, before or after the communicated blocks, overlapping the first
communication and hiding its latency. Upstream asserts this is the first-choice optimisation, that it
does not depend on the bound verdict, that pipeline balancing then refines the long/short arrangement
on top of it, and that the local matmul uses its own tiling data sized for the full M. Not established
here; nothing was measured.

## 2 · The wrong branch this removes
The fill stage of any MC² pipeline is structurally unmaskable: the first communication has no
preceding computation to hide behind (0063, 0064). An agent working only with the balancing apparatus
will accept that as a fixed cost and spend its effort on the short-block placement, which optimises
the *drain* end and the steady state. The local data is work that is available immediately, needs no
transfer, and is therefore exactly the material to put in the hole — and it is invisible to the
balancing model, because that model has only α, β and block sizes, no notion of a phase that needs no
communication at all.

The other wrong branch is sequencing. Because Local Matmul does not depend on R, it is available
before the isolation test has been run, so it is the one strategy that can be worked on while the
data gate (0061) is still being satisfied. An agent that waits for R to do anything at all delays
the change with the widest applicability.

## 3 · Ground / Source
`local_matmul.md:7-21`, the principle quoted in SOURCE, with the timeline:

> 无 Local Matmul 优化:
>   AIC: [等待通信块0] → DoMatmul(块0) → DoMatmul(块1) → ...
>   AIV: 通信块0 → 通信块1 → ...   ↑ AIC 空闲等待
> 有 Local Matmul 优化（通信后计算，前置）:
>   AIC: LocalMatmul(全量M) → WaitFlag(0) → DoMatmul(块0) → ...
>   AIV: 通信块0 → 通信块1 → ...   ↑ Local matmul 与首次通信重叠，隐藏通信延迟

Modes, `local_matmul.md:25-44`. For Pattern A (communication then computation) the local matmul is
placed *first*: either 融合 — the self rank computed inside the communication-block loop, suited to
small communication volume and a small local share — or 前置独立, `LocalMatmulProcess` running before
and overlapping the first communication, suited to a communication-bound operator. For Pattern B
(computation then communication) it is placed *last*: 融合 for a small communication volume, or
后置独立 where the communication blocks compute only remote ranks.

Selection table, `:47-54`: comm-then-compute → 前置独立 (local compute overlaps the first
communication, hiding its latency), or 融合 when the communication volume is small; compute-then-comm
→ 后置独立 (communication blocks compute only remote ranks, so the local part does not conflict), or
融合 for a small volume.

Constraints, `:58-66`: the continuity constraint (entry 0072), and 独立 tiling data — Local matmul
uses its own tiling data with the full M as the compute scale, independent of the long-block and
short-block tiling data. Output schema, `:70-77`: `mode` ∈ {fused, preemptive_independent,
posterior_independent}, `local_tiling_data`, `constraint`.

The routing statement is in the index, `comm-compute/index.md:3` (quoted in SOURCE) and `:119-121`,
which places Local Matmul as Step 1 — before Bound 判定 at Step 2 — and marks it 首选，不依赖 Bound
判定. `index.md:136` puts matmul compute-efficiency optimisation last (仅计算 Bound，优先级最低，正交
可叠加). So the chain's stated priority order is: Local Matmul, then bound diagnosis, then balancing,
then matmul efficiency.

## 4 · Procedure
Later phase, needs one card per rank; capture per 0057, R per 0059, TilingData per 0062.
1. Device selection per 0057; board token per rank from the driver readout; occupancy either side.
2. Take one Pattern A operator (comm then compute). Build three variants from a common tree: (N) no
   local extraction — every block communicated, including the local share; (F) fused — local share
   computed inside the block loop; (P) preemptive independent — `LocalMatmulProcess` before the block
   loop with its own full-M tiling data. Record `md5sum` of each.
3. Sweep the rank count over at least two values, since the local share is 1/rankNum of the data and
   the technique's headroom shrinks as ranks grow.
4. Measure all three per the ten-iteration protocol; from the trace, record the AIC idle interval
   before the first block's computation, which is the quantity the technique is supposed to remove.
5. Repeat with a Pattern B operator and the posterior-independent variant.

## 5 · Checker — acceptance declared before the run
Verdict variables `dT(variant)` against N, and `fill_idle(variant)` from the trace. Acceptance:
`dT(P) < 0` beyond spread, and `fill_idle(P)` materially below `fill_idle(N)` — the second is the
mechanism check, because a total-time gain with an unchanged fill gap came from elsewhere (the local
block's own tiling, for instance, which differs from the communicated blocks').

Second verdict `mode_choice_agrees`: whether the mode the selection table prescribes for this
operator's order and communication volume is in fact the faster of F and P.

Exit code is not the verdict. All three variants' per-rank tables and both trace quantities are
published, including rank counts where the local share is too small to matter — retained because they
did not bite.

Red input: a rank count high enough that the local share is a small fraction of M. There the gain must
shrink; if it does not, the benefit is not coming from the local data's size and the attribution is
wrong.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured. No board, operator, rank count or communication volume. "First choice" is a
priority claim over balancing with no measurement behind it on either side. The selection table's
condition 通信量小 has no threshold. It does not establish that the local share can always be
extracted — an operator whose local rows are interleaved with remote ones may not admit an
independent local matmul at all — nor what the independent local tiling costs in extra host tiling
work. The continuity constraint that governs the Pattern A compute-bound case is 0072 and is equally
unverified.
