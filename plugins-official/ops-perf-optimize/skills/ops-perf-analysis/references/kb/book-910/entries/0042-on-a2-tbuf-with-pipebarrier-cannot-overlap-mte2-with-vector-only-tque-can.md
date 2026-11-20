```
ID:        0042-on-a2-tbuf-with-pipebarrier-cannot-overlap-mte2-with-vector-only-tque-can
LABEL:     trap
LEVEL:     L4 (synchronisation)
STRATUM:   harvested — drafted from one upstream origin, a document declaring itself A2-verified; nothing measured here
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/sort/radix_sort.md:98 — "**TBuf 模型**：`PipeBarrier<PIPE_ALL>` 全停，无法实现 MTE2/Vector overlap"; ibid:121 — "TBuf 手动 double buffer（两个 TBuf + PipeBarrier 切换）在 A2 上**不工作**"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a hand-rolled two-TBuf double buffer with PipeBarrier switching is shown to overlap MTE2 with Vector on a named Atlas A2 board — i.e. a trace shows the two pipes concurrently busy.
```

# 0042 · On A2, TBuf with PipeBarrier cannot overlap MTE2 with Vector — only TQue can

## 1 · Claim
Upstream asserts that on Atlas A2 the TBuf programming model cannot achieve MTE2/Vector overlap
because `PipeBarrier<PIPE_ALL>` stops everything, and that a hand-rolled double buffer built from
two TBufs switched by PipeBarrier does not work. Upstream asserts that the TQue model —
`AllocTensor` / `EnQue` / `DeQue` / `FreeTensor` — synchronises automatically and does achieve real
pipeline parallelism. Not established here.

## 2 · The wrong branch this removes
Hand-rolling a double buffer from two TBufs is a natural and apparently more controllable design:
the agent owns the buffers, sees the barriers, and avoids a queue abstraction whose synchronisation
is implicit. It also reads as the lower-overhead option. On A2, per upstream, it simply does not
overlap — `PipeBarrier<PIPE_ALL>` is a full stop, not a per-pipe fence, so the two halves of the
intended ping-pong serialise.

What makes this a trap rather than a preference is that the code is *correct*. Both buffers are
used, both barriers are placed, the results are right, and the only symptom is that MTE2 and Vector
time add instead of overlapping. An agent measuring `aiv_mte2_time + aiv_vec_time ≈ aiv_time`
would have to already suspect the mechanism to read that sum as a diagnosis.

The correction has a second half that is easy to get wrong and that upstream states separately
(0043): TQue's depth parameter is not the double-buffer control. `TQue<VECIN, 1>` with
`InitBuffer(que, 2, size)` is the working form — depth 1, num 2 — and an agent that reads "double
buffer" and sets the depth to 2 gets neither the overlap nor an error.

## 3 · Ground / Source
`ops/ascendc-performance-best-practices/reference/sort/radix_sort.md` §2.1, the ARCH constraint at
lines 97-99, verbatim:
"**ARCH 关键限制（A2）**：
- **TBuf 模型**：`PipeBarrier<PIPE_ALL>` 全停，无法实现 MTE2/Vector overlap
- **TQue 模型**：`AllocTensor/EnQue/DeQue/FreeTensor` 自动同步，支持真正的流水线并行"

The working form, lines 102-103:
```cpp
TQue<QuePosition::VECIN, 1> dataQue_;  // depth=1 (standard)
pipe.InitBuffer(dataQue_, 2, tileBytes);  // num=2 enables Double Buffer
```
The negative result, line 121: "- TBuf 手动 double buffer（两个 TBuf + PipeBarrier 切换）在 A2 上
**不工作**". Repeated as an anti-pattern at line 349: "| TBuf + PipeBarrier 手动 double buffer |
`PipeBarrier<PIPE_ALL>` 全停，无法 MTE2/Vector overlap | 用 `TQue<VECIN, 1>` +
`InitBuffer(que, 2, size)` |". And in the A2 hardware table at line 308:
`| TBuf + PipeBarrier | 不支持 MTE2/Vec overlap | 必须用 TQue |`.

Four statements of one fact in one document, including one in a table of *negative results* — this
is the evidence culture the deep-dive identifies as the best in the repo, and the reason this
document carries more weight per line than the reference tables do.

The partial workaround upstream keeps anyway, §2.2 lines 123-137: a single-buffer overlap where the
DMA for the next chunk is issued after a `PipeBarrier<PIPE_V>` (not `PIPE_ALL`) frees the data
buffer, while a later stage reads a different buffer. "**收益**：比 TQue 小（仅掩盖 SumMask 阶段的
DMA），但不需要额外 buffer。" Note this uses `PipeBarrier<PIPE_V>` — a per-pipe barrier — which
suggests the "全停" property is specific to `PIPE_ALL`, not to PipeBarrier generally. Upstream does
not draw that distinction and this entry does not assert it.

The general mechanism from another skill, same repo:
`ops/ascendc-performance-analysis/references/metrics_reference.md:106` — "不同指令序列间可以并行
执行（这是 DoubleBuffer 等优化的基础）".

## 4 · Procedure
Proposed, runnable later; not run. This is a paired-arm timing experiment whose verdict is a trace
shape, not only a number.

1. Name the die; occupancy before and after; no substitution.
2. Three arms, same algorithm, same tile size, same total data, md5-confirmed to differ only in the
   buffering construct:
   - Arm T (TBuf): two TBufs switched by `PipeBarrier<PIPE_ALL>`.
   - Arm Q (TQue): `TQue<VECIN, 1>` with `InitBuffer(que, 2, size)`.
   - Arm S (single, control): one buffer, no double buffering at all.
3. Per arm: `aiv_time`, `aiv_mte2_time`, `aiv_vec_time`, and the Chrome trace
   (`--aic-metrics=TimelineDetail`) so overlap is observable directly and not only inferred from
   sums.
4. Five repeats, first discarded, arms interleaved.

## 5 · Checker — acceptance declared before the run
Verdict variable `overlap(arm) = (mte2_time + vec_time − aiv_time) / min(mte2_time, vec_time)` —
zero when the pipes serialise, approaching one when they fully overlap.
Gate, run first: `overlap(S)` must be near zero and `overlap(Q)` must be materially above it. Arm S
is the constructed negative and arm Q the constructed positive; if the metric cannot separate them,
it is not measuring overlap and no verdict is issued for arm T.
PASS (claim upheld) iff `overlap(T) ≈ overlap(S)` and `overlap(Q) > overlap(S) + 0.3`.
OVERTURN iff `overlap(T) ≈ overlap(Q)`.
The 0.3 threshold and the arm-S/arm-Q gate are declared here, before the run. The trace from §4
step 3 is the independent confirmation: the arithmetic and the picture must agree, and a
disagreement voids the run rather than being resolved in favour of whichever is convenient.
Exit code is not the verdict.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured here; no board touched by this book. "A2" is a product line, not a board (see 0041
§7). This entry does not establish that `PipeBarrier<PIPE_V>` shares the full-stop property — §3
notes upstream's own code uses it in an overlap pattern, which suggests it does not, and neither
this entry nor §4 tests it. It does not establish why TBuf cannot overlap, only that upstream
reports it does not. It does not establish anything about A3 or later architectures; the source
refuses that extension (0047). It says nothing about MTE3/Vector overlap, or about triple buffering.
