```
ID:        0020-chain-adjacent-vector-steps-in-ub-so-intermediates-never-round-trip-through-gm
LABEL:     knowledge
LEVEL:     L3 (data movement & layout)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/single-core-pipeline/techniques/vec-01-ub-fusion.md:14 — "多个连续 Vector 操作直接在 UB（或向量寄存器）中传递中间结果，消除不必要的 GM↔UB 搬移 … 把 N 步链路从「每步一来一回 GM」压成「入口 load 一次、出口 store 一次」"
           ops/ascendc-perf-optimize/references/single-core-pipeline/techniques/INDEX.md:5 — "卡片代码统一 A5（arch3510）RegBase；非 A5 平台用 `#if defined(__NPU_ARCH__) && (__NPU_ARCH__ == 3510)` 编译期隔离"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a fused build on a named 950 board whose `aiv_time` is not below the staged build's by
           more than run spread, at a shape where the intermediate fits UB — the round trip would
           then not be the cost the card claims, and the card's own 性能数据 section already
           concedes it has never been measured.
```

# 0020 · Chain adjacent vector steps in UB so intermediates never round-trip through GM

## 1 · Claim
Upstream asserts (technique card vec-01, marked 写满 but with 性能数据 待实测) that consecutive
Vector operations should pass intermediates inside UB or the vector registers rather than through
GM, collapsing an N-step chain from "one GM round trip per step" to "load once at the entry,
store once at the exit", and that the MTE2/MTE3 instruction count falls by the number of
eliminated staging steps. Not established here: upstream states the direction and explicitly
records that no measurement exists.

## 2 · The wrong branch this removes
An agent composing an operator from library calls writes each step as a self-contained
load-compute-store, because that is what each API example looks like and because it is easy to
test one step at a time. The result is correct, passes precision regression, and spends most of
its time moving the same bytes back and forth over GM. The profile then reads as memory bound
(0005 routes it to `memory.md`), and the agent starts optimising the copies — merging them,
aligning them, prefetching them — when the correct action is to delete them. The distinguishing
signature is given by the card and is cheap: in the trace, an MTE3 immediately followed by an
MTE2 between two VECTOR segments.

## 3 · Ground / Source
`vec-01:6-10`, the diagnostic conditions:

> - trace 中两个 VECTOR 活跃段之间插入了 **MTE3（写回）+ MTE2（读入）**，说明中间结果经过了
>   GM，未融合。
> - `aiv_mte2_ratio` / `aiv_mte3_ratio` 偏高但计算量本身不大（搬运快于计算，却因往返而空转）。
> - 算子由多个 elementwise/activation 步骤串成，且各步骤之间落 GM 中转。

`vec-01:19-28` gives the before/after: six GM accesses (`DataCopy` in, compute, `DataCopy` to
`gmMid`, `DataCopy` from `gmMid`, compute, `DataCopy` out) against two. `vec-01:34` is the
evidence line, quoted in full because its form matters:

> msprof `aiv_time` 前后对比：融合后 MTE2/MTE3 指令数按被消除的中转次数下降；访存往返是主要
> 开销时收益明显。**待实测**（预期方向：中间落 GM 的步数越多，省掉的往返越多）。

Stop rules, `vec-01:36-40`: the intermediate must fit in UB, halved when DoubleBuffer is on
(0018); if the intermediate is still consumed elsewhere the staging cannot simply be deleted;
fusion changes buffer lifetimes, so EnQue/DeQue synchronisation must not be dropped or a
half-written buffer is read.

Placement in the library: routed to from three of the four diagnosis pages — `vec.md:82`
(相邻可融合 Vector 操作、中间落 GM), `memory.md:25` (UB 内可原地消费、消除搬入搬出往返),
`no-bound.md:30` (同一数据重复搬入) — which makes it the most-referenced card in the set and,
per `INDEX.md:9-10`, still not a measured one. The next step beyond it is instruction-level
fusion (0022) and register-level elimination of the staging buffer itself (0027).

## 4 · Procedure
Later phase, needs a card. Board token from the driver readout.
1. Device selection per 0010: explicit `ASCEND_RT_VISIBLE_DEVICES`, occupancy recorded before
   and after, no assumption of an idle die or of which 950 board is present.
2. Build one operator two ways from a common source tree, differing only in staging: (F) fused,
   intermediates resident in UB; (S) staged, each step writing and re-reading GM. Verify by
   `md5sum` that the two kernel objects differ and that repeated builds of each are identical.
3. Sweep the chain length N over 2, 3, 4 steps, and the tile size over three values, one of which
   makes the intermediate exceed half of UB so the DoubleBuffer red line binds.
4. Capture per 0010: `aiv_time`, `aiv_mte2_ratio`, `aiv_mte3_ratio`, and the MTE2/MTE3
   instruction counts if the trace exposes them; five repetitions, median and spread. Run the
   precision regression on both builds.

## 5 · Checker — acceptance declared before the run
Verdict variable `fusion_gain(N)` = (aiv_time(S) − aiv_time(F)) / aiv_time(S), computed per N.
Acceptance for the card as written: `fusion_gain(N) > spread` for every N, and monotone
non-decreasing in N — the card's stated expectation is that more eliminated round trips means
more gain, so a flat or inverted curve refutes the mechanism even if the sign is right.
Secondary: the eliminated MTE instruction count must equal the number of removed staging steps
times the per-step count; a gain without that reduction means something else changed.

Exit code is not the verdict — both builds run to completion in every arm. The verdict is the
printed curve plus the precision-regression result, and a build that gains time while failing
precision is reported as a failure, not as a gain.

Red input: the over-large tile arm, where the intermediate cannot fit UB. There the fused build
must either fail to allocate or fall back to smaller tiles, and `fusion_gain` must not be
reported as if the comparison were like-for-like — it is reported as `constraint_violated`.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured, by us or by upstream — the card's own evidence line says 待实测. No board, no
shape, no operator family is established. The card's code is declared A5/arch3510 RegBase and
compile-fenced, so nothing here transfers to another architecture, and per RULES.md Art. 1 nothing
transfers to the 910 book. It does not establish the size of the round-trip cost relative to
compute, which is what decides whether the technique matters for a given operator; and it does
not establish that the intermediate can be kept in registers rather than UB — that is 0027's
subject and a different mechanism with a different red line.
