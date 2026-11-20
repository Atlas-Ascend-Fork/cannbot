```
ID:        0108-the-streamk-entry-gate-is-stated-as-k-ge-32768-and-computed-as-k-ge-4096
LABEL:     trap
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/tiling/matmul/fallback/tiling-flow.md:21,283 and
           matmul/fallback/fallback-algorithm.md:35 — prose gate "K ≥ 32768 且 B=1 且无 group"
           vs the sub-mode table "`Align(K, 256) ≥ max(8192, aicNum×256) / sizeof(FP16)`",
           which at aicNum=24 evaluates to K ≥ 4096
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured sweep on a named 950 board showing StreamK is a loss on every shape with
           4096 ≤ K < 32768 — that would make the prose gate right and the formula a bug; the
           reverse readout kills the prose gate instead. Either outcome overturns this entry as
           written, because it records the disagreement rather than a value.
```

# 0108 · The StreamK entry gate is stated as K ≥ 32768 and computed as K ≥ 4096

## 1 · Claim
Upstream asserts, in two files, that StreamK applies when `K ≥ 32768 且 B=1 且无 group`. Upstream
also asserts, in a sub-mode table 262 lines below the first of those statements, that pure SK is
entered when `Align(K, 256) ≥ max(8192, aicNum×256) / sizeof(FP16)` together with
`mCnt×nCnt ≤ aicNum/2`. At `aicNum = 24` — the core count used by this file's own worked example
— the second condition evaluates to `K ≥ 4096`, a factor of eight below the first. Upstream's own
worked example (M=512, N=512, K=16384) is routed to SK, which satisfies the formula and violates
the prose gate. Not established here: no board was touched, and this entry records the
disagreement, not a resolution.

## 2 · The wrong branch this removes
Both readings are load-bearing and they route differently over three orders of magnitude of shape
space. A harness agent that reads the summary table — the natural place to look, since it is the
first thing in the file and is repeated in the family's routing document — refuses StreamK for
every shape below K=32768, including the file's own example. An agent that reads the sub-mode
table enables StreamK from K=4096 upward. Neither agent has any reason to doubt itself: both cite
the same file. The normal checks cannot catch this because a StreamK plan and a SWAT plan are
both schema-valid, both produce correct results, and the difference shows up only as a
performance number nobody attributes to the gate.

The second-order trap is worse. `aicNum` appears inside the formula, so the computed threshold is
not a constant: at `aicNum = 32` the formula gives `max(8192, 8192)/2 = 4096`; at `aicNum = 64`
it gives `max(8192, 16384)/2 = 8192`; at `aicNum = 72` it gives `9216`. The prose gate is a fixed
number; the formula gate scales with core count above `aicNum = 32`. An agent that reconciles the
two by picking one has silently also picked whether the gate depends on the machine.

## 3 · Ground / Source
Statement A, `matmul/fallback/tiling-flow.md:21` (the strategy table):

```
| **StreamK** | K 轴切分给多核，每核负责一段 K，workspace 归约 | K ≥ 32768 且 B=1 且无 group |
```

Statement A again, `matmul/fallback/fallback-algorithm.md:35`:

```
| **StreamK** | K ≥ 32768 且 B=1 且无 group | K 轴切分给多核并行 |
```

These two are the same repo and the same claim restated — one origin, not corroboration.

Statement B, `matmul/fallback/tiling-flow.md:281-284` (the sub-mode gate table), in full:

```
| 子模式 | 判定条件 |
|--------|---------|
| **SK** | `Align(K, 256) ≥ max(8192, aicNum×256) / sizeof(FP16)` 且 `mCnt×nCnt ≤ aicNum/2` |
| **DP+SK** | `M%256==0 ∧ N%256==0 ∧ K ≥ max(8192, aicNum×128) / sizeof(FP16)` ∧ `mCnt×nCnt ≥ aicNum` ∧ `(mCnt×nCnt) % aicNum ∈ (0, aicNum/2]` |
```

Arithmetic, re-derived here rather than quoted: at `aicNum = 24`, `aicNum×256 = 6144`, so
`max(8192, 6144) = 8192`; `sizeof(FP16) = 2`; `8192 / 2 = 4096`. The SK condition is therefore
`Align(K, 256) ≥ 4096`. The DP+SK row uses `aicNum×128` and gives the same 4096 at this core
count.

The worked example, `matmul/fallback/tiling-flow.md:351-357`:

```
**M=512, N=512, K=16384 (FP16, aicNum=24) → SK**:
mCnt=2, nCnt=2, totalMNCnt=4 ≤ 12 → SK
kCnt = 24/4 = 6, skSingleCoreK = 2732
baseK=64, stepKa=min(4,4)=4, kL1=256
Workspace: 24 × 256² × 4 ≈ 6.3 MB
```

K = 16384 < 32768, so this example violates statement A and satisfies statement B. It is
upstream's only worked StreamK case.

Note also that the formula's units do not close: `Align(K, 256)` is an element count on the left
and `max(8192, aicNum×256) / sizeof(FP16)` is a byte quantity divided by a byte width on the
right, i.e. also an element count — the division by `sizeof(FP16)` makes the right side smaller
for wider dtypes, so the threshold *falls* as element width grows. Whether that is intended is
not stated anywhere in the file; it is recorded here as an open reading, not as a defect ruled on.

This row extends `harvest/CONTRADICTIONS.md` C-009 (which recorded the same pair from the
2026-08-24 survey at the same line numbers, re-verified here) and is registered locally as
C-950tiling-002 with the aicNum-dependence and dtype-dependence added.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase. Art. 7:
a contradiction is resolved by a procedure on a named board, never by picking the more plausible
author, so this procedure is designed to answer "which gate", not "which sentence is nicer".

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s
spacing; bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and
discard the case if the die moved.

K sweep across the disputed interval. Fix M=N=512, FP16, B=1, no group — the regime both gates
agree is otherwise eligible. Sweep K over
{2048, 3072, 4096, 6144, 8192, 12288, 16384, 24576, 32768, 49152}, which brackets both thresholds
and includes the file's own example point. At each K build two kernels with one compiler pin:
SWAT (forced) and StreamK (forced, with the seven StreamK constants asserted per `:312`). md5
both binaries. Verify both against an fp64 reference within the operator's declared tolerance
before reading any time — StreamK reduces partial sums through workspace and therefore changes
float accumulation order, so bit-identity is not expected and the tolerance must be declared in
advance. Record `aic_time`, MTE2 bytes and workspace bytes under
`msprof --aic-metrics=PipeUtilization`, ≥10 iterations, first 5 dropped, per case.

Second arm, to settle the `aicNum` dependence: repeat the sweep with `aicNum` restricted to 24,
32 and the full core count the platform reports, so the formula's core-count term is exercised
rather than assumed. `aicNum` is read from the platform at runtime, never from a script literal.

Refuses to assume: that a free die stays free; that a die may be substituted; that the crossover
is a single K (it is located per `aicNum`, and each is reported separately); that the workspace
allocation succeeds at every K — a StreamK point that cannot allocate `aicNum × 256² × 4` bytes
plus the undefined `RPC_WORKSIZE × MB_SIZE` term (0111) is recorded as a failure at that K, not
dropped.

## 5 · Checker — acceptance declared before the run
Verdict variable `K_cross`, the smallest swept K at which median StreamK `aic_time` is below
median SWAT `aic_time` by more than 5 %, computed per `aicNum` arm. Declared before the run:
statement A (prose, 32768) is supported iff `K_cross ≥ 24576`; statement B (formula, 4096) is
supported iff `K_cross ≤ 6144`; anything between supports neither and is reported as
"both gates wrong, crossover at K_cross". If StreamK never wins at any swept K, that is recorded
as `K_cross = none` and it kills the strategy's usefulness in this regime, not merely the gate.

The exit code is not the verdict. The specific way this checker could be blind: forcing StreamK
on a shape whose gate does not pass may cause the generator to fall back to SWAT silently, in
which case both arms are the same kernel, the timings match, and `K_cross` would be reported as
"never" from an experiment that never ran StreamK at all. The guard is mandatory and structural —
the StreamK arm must show a non-zero `tailInfo.kCnt` and a non-zero workspace allocation in the
host echo at every K, and the checker goes red at any K where it does not, rather than recording
a comparison. The md5 comparison between the two binaries is a second, independent guard on the
same failure.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured. The entry does not say which gate is right — it establishes only that
upstream states two, that they differ by 8× at `aicNum = 24`, and that upstream's own worked
example obeys the formula and violates the prose. It does not establish that `aicNum = 24` is a
real core count for any board (C-007 records five incompatible `coreNum` values in this subtree),
and the formula's threshold moves with `aicNum`, so any resolution is per core count. It does not
establish that the dtype term behaves sensibly for non-FP16 inputs — the formula divides by
`sizeof(FP16)` as a literal, and what happens at BF16, FP8 or FP4 is unstated. No board is named
in either source file, so BOARD is `family-claimed(unverified)` and the chip is unstated; §4
names 950PR/950DT because that is where our run would happen. Nothing here is established for any
910-family board.
