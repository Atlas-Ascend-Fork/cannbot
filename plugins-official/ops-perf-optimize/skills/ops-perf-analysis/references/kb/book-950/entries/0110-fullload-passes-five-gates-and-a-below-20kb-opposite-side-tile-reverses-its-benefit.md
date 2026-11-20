```
ID:        0110-fullload-passes-five-gates-and-a-below-20kb-opposite-side-tile-reverses-its-benefit
LABEL:     knowledge
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/tiling/matmul/fallback/tiling-flow.md:197-231,247-267 —
           "门禁条件（五条，任一不过即回退 SWAT）" ... "5. 流水健康度: Bytes_opp = baseX × kL1 ×
           sizeof(dtype) ≥ 20 KB └─ < 20 KB 时 MTE2 带宽效率低，全载收益被反噬" ...
           "典型 T=5 时，小侧 MTE2 字节下降 80%，Task 时间降低 5%~15%"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured pair on a named 950 board at an opposite-side tile below 20 KB where
           FullLoad still beats SWAT on the same shape — that kills gate 5 as a gate; a paired
           run at T ≥ 5 showing no task-time reduction kills the 5–15 % figure independently.
```

# 0110 · FullLoad passes five gates, and a below-20 KB opposite-side tile reverses its benefit

## 1 · Claim
Upstream asserts that the FullLoad strategy — one operand held resident in L1 for the whole
computation so the K axis is not re-read for it — is admitted only when five conditions all hold,
and that failing any one falls back to SWAT. The five, as upstream states them: (1) the shape did
not take the StreamK branch; (2) at least one side fits, `min(Bytes_A, Bytes_B) × 2 ≤ L1_SIZE`
where `Bytes_A = baseM × Align(K, c0) × sizeof(dtype)` and `Bytes_B = Align(K, c0) × baseN ×
sizeof(dtype)`; (3) the opposite side's loop count `T` is at least 2, where
`T_A = N / (usedCoreNum × baseN)` and `T_B = M / (usedCoreNum × baseM)`, because `T = 1` yields
zero benefit; (4) the multi-core layout satisfies `mBlockCnt ≤ WINDOW_LEN(=4)`,
`aicNum % mBlockCnt == 0` and `totalBlockCnt > aicNum`; (5) pipeline health —
`Bytes_opp = baseX × kL1 × sizeof(dtype) ≥ 20 KB`, below which MTE2 bandwidth efficiency is poor
and the residency benefit is, in upstream's word, bitten back (`收益被反噬`). Upstream separately
asserts a benefit figure: at a typical `T = 5` the small side's MTE2 bytes fall by 80 % and task
time by 5–15 %. Not established here — the 5–15 % figure carries no board, no shape and no tool.

## 2 · The wrong branch this removes
Gate 2 is the one an agent invents on its own: "does it fit in L1". Gates 3 and 5 are the ones it
does not, and they are the ones that make FullLoad a loss when it is a loss. Gate 3 is an
economics gate — if the opposite side is traversed once, there is no repeated movement to
eliminate, so residency buys nothing while costing L1 that the streaming side could have used.
Gate 5 is a bandwidth gate in the opposite direction: making one side resident shrinks the
streaming side's per-transfer tile, and below roughly 20 KB the transfers are too small for MTE2
to run efficiently, so the movement you did not eliminate becomes slower than it was. An agent
that enables FullLoad on "it fits and it is smaller" therefore has two independent ways to lose
that no correctness check can see. Both losses present as an unremarkable time on a plan that
looks well-reasoned.

Gate 5 is also the sharper teaching in general form: an optimisation that concentrates a resource
on one operand degrades the transfer geometry of the other, and the second effect has its own
threshold. This is the only place in the tiling reference set that states such a reversal
explicitly.

## 3 · Ground / Source
`matmul/fallback/tiling-flow.md:197-223`, the gate block in full:

```
### 4.1 门禁条件（五条，任一不过即回退 SWAT）

1. 策略条件: 未走 StreamK 分支
   └─ StreamK 下 K 已切给多核，"全载"语义失效

2. 小侧矩阵容量（至少一侧通过）:
   Bytes_A = baseM × Align(K, c0) × sizeof(dtype)
   Bytes_B = Align(K, c0) × baseN × sizeof(dtype)
   条件: min(Bytes_A, Bytes_B) × 2 ≤ L1_SIZE

3. 对侧循环次数 T ≥ 2:
   T_A = N / (usedCoreNum × baseN)
   T_B = M / (usedCoreNum × baseM)
   └─ T = 1 → 收益为 0，不开

4. 多核排布 (以 A-Full-Load 为例):
   mBlockCnt ≤ WINDOW_LEN(=4)
   aicNum % mBlockCnt == 0
   totalBlockCnt > aicNum

5. 流水健康度:
   Bytes_opp = baseX × kL1 × sizeof(dtype) ≥ 20 KB
   └─ < 20 KB 时 MTE2 带宽效率低，全载收益被反噬

两侧都通过时，选 min(Bytes_A, Bytes_B) 更小的那侧做全载。
```

The objective and the benefit figure, `:225-231`:

```
ΔBytes = (T - 1) × baseM × K × |dtype|    # A-Full-Load

典型 T=5 时，小侧 MTE2 字节下降 80%，Task 时间降低 5%~15%。
```

The 80 % follows from the formula — `(T-1)/T = 4/5` at `T = 5` — and is arithmetic, not a
measurement. The `5%~15%` does not follow from anything stated; it is the only number in the
matmul family that describes an outcome rather than a rule, and it has no shape, no dtype, no
core count, no board and no tool attached. A prior survey of this skill reached the same reading
independently of this entry, calling the family "effectively bare, sole number 5%~15% unscoped".

The L1 budget inequality, `:247-257`:

```
A_full_load + B_streaming_pingpong ≤ L1_SIZE

baseM × Align(K, c0) × sizeof(dtype)                           # A 全量驻留
+ (baseN × stepKb × baseK × sizeof(dtype)) × nBufferNum        # B 流式 pingpong
≤ L1_SIZE

如果溢出，自动收缩 B 侧 stepKb。缩到 1 仍溢出 → fallback SWAT。
```

Note the automatic shrink: a FullLoad plan that reports `stepKb = 1` is a plan that was squeezed,
not chosen, and its `nBufferNum` will have fallen to 2 (`:243` — `通常回退到 2`). That is
observable in the emitted tiling data without a device and is worth checking before any timing.

The selection table, `:259-267`, adds two thresholds that belong to bound diagnosis rather than to
geometry:

```
| 小侧 ≤ L1/2, T≥2, **真 MTE2 bound** (带宽 ≥ 85%) | **FullLoad** | MTE2 是瓶颈 |
| 小侧 ≤ L1/2, T≥2, 假 MTE2 bound (带宽 < 70%) | SWAT | 瓶颈不在搬移 |
```

The interval [70 %, 85 %) is routed by no row. That gap is entry 0117 and is registered as
C-950tiling-004; it is the same species as the [70,85) gap a prior survey found in this file's
MTE2 gates, re-verified here at these lines.

`c0` and `L1_SIZE` appear in these formulas and are defined nowhere in the family — see 0111.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s
spacing; bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and
discard the case if the die moved.

Gate 5 sweep, which is the gate this procedure exists to test. Fix a shape whose gates 1–4 all
pass comfortably (A-FullLoad: M=256, K=4096, N=65536, BF16, so `Bytes_A = 256×4096×2 = 2 MB` —
adjust M downward until gate 2 passes against the *queried* L1 capacity, not against 524288).
Then sweep `Bytes_opp = baseN × kL1 × sizeof(dtype)` across
{4 KB, 8 KB, 16 KB, 20 KB, 24 KB, 32 KB, 64 KB} by varying `baseN` and `stepKb`, and at each
point build both a FullLoad kernel and the SWAT baseline for the identical shape. One compiler
pin; md5 each binary; host echo of `isAFullLoad`, `stepKb`, `nBufferNum`, `kL1`. Verify both arms
against an fp64 reference within the declared tolerance. Record `aic_time` and MTE2 bytes moved
under `msprof --aic-metrics=PipeUtilization`, ≥10 iterations, first 5 dropped, per case.

Gate 3 arm, separately: hold everything fixed and vary `N` so that `T_A` takes the values
{1, 2, 3, 5, 8}, and record the FullLoad-over-SWAT ratio at each. This makes both the `T ≥ 2` gate
and the `5%~15%` figure observable on the same axis, and the `T = 1` point is the negative arm —
retained in the report whether or not it bites.

Refuses to assume: that a free die stays free; that a die may be substituted; that L1 is 512 KB
(0109 records that the only stated value is an unattributed FAQ literal — the capacity is queried
at runtime); that `c0` is any particular value (it is swept as {16, 32} and the two results
reported separately — see 0111); that `aicNum` is a script default; that the 20 KB threshold is
sharp — the sweep brackets it rather than testing one point either side.

## 5 · Checker — acceptance declared before the run
Verdict variable `fl_ratio(Bytes_opp)` = median FullLoad `aic_time` / median SWAT `aic_time` at
each swept point, and `T_ratio(T)` on the second arm. Declared before the run: gate 5 is supported
iff `fl_ratio > 1` (FullLoad slower) for every point below 20 KB and `fl_ratio < 1` for every
point at or above 20 KB. It is overturned iff any point below 20 KB has `fl_ratio < 0.95` — the
OVERTURN condition. The `5%~15%` figure is supported iff `T_ratio(5)` lies in [0.85, 0.95]; a
value outside that band is reported as the number it is, in both directions, including the
unflattering direction where FullLoad at `T = 5` is a wash.

The exit code is not the verdict. The blind failure this checker must avoid: the L1 budget
inequality shrinks `stepKb` automatically and falls back to SWAT when it cannot fit, so a
"FullLoad" arm may in fact be a SWAT arm, in which case `fl_ratio ≈ 1` at every point and the
sweep would read as a clean confirmation of nothing. The host echo of `isAFullLoad` is therefore
required to be true at every FullLoad point, MTE2 bytes moved must differ measurably between the
two arms, and the checker goes red if either condition fails at any point instead of reporting
the ratios it can compute.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured. The entry does not establish that 20 KB is the right threshold or that it is
a threshold at all; upstream gives it with no derivation and no measurement. It does not establish
the `5%~15%` task-time figure, which is unscoped in every dimension — no board, no shape, no
dtype, no core count, no tool — and is recorded here as an upstream assertion only. It does not
establish `L1_SIZE` or `c0` for any board (0111). It does not establish that the five gates are
independent or that they are exhaustive. The [70 %, 85 %) MTE2 band is unrouted by upstream's own
table and this entry does not fill it (0117). No board is named in the source file, so BOARD is
`family-claimed(unverified)` and the chip is unstated; §4 names 950PR/950DT because that is where
our run would happen. Nothing here is established for any 910-family board.
