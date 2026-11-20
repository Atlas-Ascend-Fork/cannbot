```
ID:        0012-doublebuffer-is-effective-only-when-mte2-and-vector-alternate-in-the-trace
LABEL:     knowledge
LEVEL:     L1 (core & pipe assignment)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/single-core-pipeline/metrics.md:80 — "**DoubleBuffer 是否生效**：MTE2 与 VECTOR 交替出现 = 搬入与计算重叠（健康）；MTE2 全在前、VECTOR 全在后 = 串行（DB 未生效）"
           ops/ascendc-perf-optimize/references/single-core-pipeline/vec.md:69-72 — "| **DB 生效** | MTE2 和 VECTOR 交替出现 | 搬入与计算重叠，流水健康 | | **DB 未生效** | MTE2 全在前，VECTOR 全在后 | 串行执行，需开启或修复 DoubleBuffer |"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a kernel on a named 950 board built with `InitBuffer(..., BUFFER_NUM=2, ...)` whose
           trace shows the alternating signature while paired timing against a single-buffer
           build of the same kernel shows no wall-clock difference beyond run spread — the
           signature would then not be evidence that double buffering is doing anything.
```

# 0012 · DoubleBuffer is effective only when MTE2 and VECTOR alternate in the trace

## 1 · Claim
Upstream asserts a visual predicate for whether double buffering is actually overlapping: in the
five-lane trace, alternation of MTE2 and VECTOR segments means load and compute overlap and the
pipeline is healthy, while MTE2 entirely before VECTOR means serial execution and double
buffering is not in effect — regardless of whether it was enabled in the source. Not established
here; no trace was captured.

## 2 · The wrong branch this removes
An agent verifies double buffering by reading the source: it finds `InitBuffer(que, 2, size)`,
concludes DB is on, and moves to the next hypothesis. Upstream's whole no-bound branch exists
because that inference fails — `nobound-02:15` makes "DB is enabled but load and compute still
do not overlap" the precondition of its entire card, and `:25-27` explains why: the two buffers
only *permit* overlap, and what realises it is the scalar core being free to issue. So "DB is
configured" and "DB is effective" are different propositions, one readable from source, the
other only from a trace. An agent that cannot tell them apart will either spend its budget
re-enabling something already enabled, or skip the reordering fix that was the actual repair.

## 3 · Ground / Source
`metrics.md:79-82`, under 要点观察:

> - **DoubleBuffer 是否生效**：MTE2 与 VECTOR 交替出现 = 搬入与计算重叠（健康）；MTE2 全在前、
>   VECTOR 全在后 = 串行（DB 未生效）。
> - **依赖链空泡**：VECTOR 出现周期性空泡且此时 MTE2/MTE3 也不忙 → 依赖链长 / 寄存器压力
>   （非访存）。
> - **寄存器 spill**：VF 计算段内出现成对的 spill→reload 指令（preg 溢出，int64 等实际占用
>   翻倍时常见），打断计算流。

`vec.md:65-72` carries the same predicate as a two-row table under DoubleBuffer 检查. The
deep-dive notes this block is byte-identical to a block in the neighbouring
`ascendc-performance-analysis` skill; per RULES.md Art. 3 that is the same repo and therefore the
same origin, so this entry stays at one origin.

Consuming statements: `index.md:23` routes 各单元利用率均不高 to the overlap factor rather than
to a DB check; `nobound-01:22` lists 开 PingPong / DoubleBuffer as its first手段 with the
condition 控制每次搬移量使计算时间 ≥ 搬移时间; `nobound-02:15` makes the failed-DB observation
its entry gate and adds DB 没开就先开 DB，本卡不是它的替代品.

A coverage gap worth recording rather than filling: DoubleBuffer is named ninety-odd times
across this skill, is a routing criterion on three diagnosis pages and a precondition of the one
measured card, and has no technique card of its own — `mem-02` covers manual ping-pong
prefetch, which is a different mechanism from `InitBuffer` BUFFER_NUM.

## 4 · Procedure
Later phase, needs a card; the trace arm can also run under the simulator, but the verdict is
the board (0010).
1. Device selection per 0010; board token from the driver; occupancy recorded either side.
2. Build one kernel three ways from the same source, changing only `BUFFER_NUM`: (S1)
   BUFFER_NUM=1; (S2) BUFFER_NUM=2; (S3) BUFFER_NUM=2 with the loop body ordered as in the
   `before` form of 0052, i.e. the case upstream says shows the serial signature despite DB.
3. Capture an instruction-level trace for each (`npusim record`/`report`, per 0010's caveat that
   absolute times from the simulator are not the verdict), and msprof `aiv_time` for each,
   five repetitions.
4. Classify each trace mechanically: partition the kernel span into deciles, and compute
   `alternation = fraction of deciles containing both an MTE2 and a VECTOR segment`.

## 5 · Checker — acceptance declared before the run
Verdict variables: `alternation(S)` per build, and `speedup(S2 vs S1)` from board `aiv_time`.
The predicate is accepted iff `alternation(S2) > 0.6`, `alternation(S1) < 0.2`, and
`speedup(S2 vs S1) > run spread`. The interesting arm is S3: upstream predicts
`alternation(S3) < 0.2` with DB configured — if S3 alternates as much as S2, the visual
predicate does not detect the failure it is advertised to detect.

Exit code is not the verdict; the trace parser exits 0 on an empty trace. `segments_parsed` per
lane is asserted non-zero, and a build whose trace contains no VECTOR segment is reported
`trace_empty`, never classified as non-alternating — that confusion is exactly the checker
species this book forbids: silence read as a negative result.

Red input: S1, which must classify as non-alternating. If the classifier calls S1 alternating,
it cannot distinguish the two states at all and the run is void.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
No trace, no board, no measurement. The predicate is stated for MTE2 against VECTOR on the AIV
side; nothing here covers the AIC lanes or a Cube-bearing operator, where the producing lane is
MTE1/CUBE and the signature is different. It does not establish the decile-based alternation
metric as upstream's meaning — upstream states the predicate in words about a picture, and any
mechanical form of it is our construction, which is why the procedure declares it in advance.
It does not establish that enabling DB is beneficial: 0019 records that DB halves the usable UB,
and whether the overlap pays for the halved tile is a per-case measurement nobody has made here.
