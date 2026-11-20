```
ID:        0055-masking-ratio-and-speed-up-are-both-defined-against-the-tilecnt-1-baseline
LABEL:     knowledge
LEVEL:     L9 (performance)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/comm-compute/index.md:16 — "掩盖率 = (融合前耗时 - 融合后耗时) / min(计算耗时, 通信耗时)"
           ops/ascendc-perf-optimize/references/comm-compute/index.md:30 — "加速比 = 融合前耗时 / 融合后耗时"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured MC² case on a named 950 board whose masking ratio computed from these
           definitions exceeds 1.0 — the stated theoretical ceiling would then be wrong, which
           would mean the baseline is not the serial sum the definition assumes.
```

# 0055 · Masking ratio and speed-up are both defined against the tileCnt=1 baseline

## 1 · Claim
Upstream asserts two performance indicators for MC² fused communication-compute operators:
masking ratio = (pre-fusion time − post-fusion time) / min(compute time, communication time), and
speed-up = pre-fusion time / post-fusion time; that the pre-fusion time is the operator's total at
`tileCnt=1`, where communication and computation are serial; that compute time and communication
time are each measured at `tileCnt=1` by commenting out the other process; and that the masking
ratio's theoretical ceiling is 1.0, complete masking. Not established here; nothing was measured.

## 2 · The wrong branch this removes
Without a defined baseline, "the operator got 20% faster" is unanchored: faster than the unfused
implementation, than the previous split, or than the theoretical serial time? The two indicators
answer different questions and an agent that reports only speed-up cannot say whether it is near
the end of the available gain. Masking ratio is the one that closes: it is normalised by the
smaller of the two phases, which is the most that can be hidden, so 0.9 means there is almost
nothing left and 0.4 means half the opportunity is unclaimed. Speed-up alone cannot distinguish
"well-masked small overlap" from "badly-masked large overlap", and those want opposite next moves.

The wrong branch inside the definition is the baseline. `tileCnt=1` is not "the code before the
optimisation" — it is the same fused kernel with one tile, so communication and computation
serialise. An agent that substitutes a hand-written unfused implementation as the baseline gets a
different, larger number and cannot compare it with anything upstream reports.

## 3 · Ground / Source
`comm-compute/index.md:7-35`, the 性能指标 section in full. Masking ratio, `:15-23`:

> 掩盖率 = (融合前耗时 - 融合后耗时) / min(计算耗时, 通信耗时)
> - **融合前耗时**：tileCnt=1 时的算子总耗时（通信与计算串行）
> - **融合后耗时**：优化后（流水配平等）的算子总耗时
> - **计算耗时 / 通信耗时**：在 tileCnt=1 下，注释掉通信或计算过程分别测得
> 掩盖率越高，说明通信被计算掩盖得越充分。理论上限为 1.0（完全掩盖）。

Speed-up, `:29-34`, over the same baseline. The ceiling claim is consistent with the definition
under the serial-baseline assumption: if pre-fusion = T_comp + T_comm and post-fusion ≥
max(T_comp, T_comm), then the numerator ≤ min(T_comp, T_comm), so the ratio ≤ 1. That derivation is
this book's, from upstream's own definitions, and it is an argument rather than a measurement — it
depends on the baseline actually being the serial sum, which is what the OVERTURN condition tests.

`index.md:140-145` makes the calculation mandatory (Step 5 为必选步骤) with the reasoning that the
isolation test has already produced T_comm and T_compute, so the cost is only the arithmetic, and
that 掩盖率直接反映通信被计算掩盖的程度，是 MC² 算子区别于普通算子的核心评价指标. `SKILL.md:79`
repeats it as a required Step 2 output: 加速比与掩盖率（MC² 算子必选）.

## 4 · Procedure
Later phase, needs cards on several ranks. Device selection per 0057's multi-rank protocol; board
token from the driver readout on every rank, and a rank set whose boards are not assumed identical.
1. For one MC² operator, measure at `tileCnt=1`: the full operator (pre-fusion baseline), the
   communication-only build, and the computation-only build, each per the multi-rank protocol of
   0057 and the isolation procedure of 0059.
2. Measure the optimised split (post-fusion) the same way.
3. Compute masking ratio and speed-up from the four numbers, and separately compute
   `T_comp + T_comm` and compare it against the measured pre-fusion time — that comparison is the
   test of the baseline assumption, and it is not part of upstream's procedure.
4. Repeat over at least four problem sizes spanning the R range upstream reports (0058), since the
   ceiling argument is size-independent only if the baseline stays serial at every size.

## 5 · Checker — acceptance declared before the run
Verdict variables `masking`, `speedup`, and `baseline_is_serial` =
`|T_pre − (T_comp + T_comm)| / T_pre`. Acceptance of the definitions as stated: `masking` in
[0, 1] for every case, and `baseline_is_serial` within 10% — if the pre-fusion time is materially
below the sum, the two phases already overlap at `tileCnt=1` and the ceiling of 1.0 does not hold.

Exit code is not the verdict. All four raw times are reported per rank as well as the cross-rank
maximum, so a masking ratio above 1.0 can be traced to which rank produced it rather than being
clipped.

Red input: a deliberately unfused implementation used as the baseline. It must produce a *different*
masking ratio from the `tileCnt=1` baseline; if the two agree, the distinction the definition rests
on is not observable for this operator and the report says so.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured. No board, no operator, no rank count. The 1.0 ceiling is derived from upstream's
own definitions under an assumption about the baseline that no measurement in this book supports.
The definitions say nothing about how to attribute a gain between Local Matmul (0071) and pipeline
balancing (0063), both of which move the same post-fusion number. They also presuppose that
commenting out one process leaves the other's cost unchanged, which is 0059's open question.
