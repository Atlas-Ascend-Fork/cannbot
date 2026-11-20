```
ID:        0064-aic-computes-and-aiv-communicates-and-the-sync-direction-reverses-with-the-order
LABEL:     knowledge
LEVEL:     L4 (synchronisation)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/comm-compute/pipeline_balancing.md:28-30 — "MC² 通算融合算子采用 AIC（计算核）+ AIV（向量核）分离架构，AIC 负责 matmul 计算，AIV 负责跨卡通信（AllToAll via UDMA / shmem）。两者通过 CrossCore 事件同步实现通信与计算的流水掩盖。通信与计算的执行顺序不同，同步方向完全相反"
           ops/ascendc-perf-optimize/references/comm-compute/pipeline_balancing.md:60-62 — "**AIV** | 后通信：从远端卡 Win 区 GET 计算结果 | `WaitComputeComplete` 等待 AIC 计算完成，再 `BarrierAll` 对齐所有 rank 后执行 AllToAll"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a trace on a named 950 board of a Pattern B operator in which the AIV waits on
           `CrossCoreWaitFlag` rather than on `WaitComputeComplete`, or in which AIC waits for AIV —
           the direction would then not follow the execution order as claimed.
```

# 0064 · AIC computes and AIV communicates, and the sync direction reverses with the order

## 1 · Claim
Upstream asserts that MC² fused operators use a split AIC/AIV architecture — AIC performs the matmul,
AIV performs cross-card communication (AllToAll over UDMA or shared memory) — synchronised by
CrossCore events; and that the synchronisation direction is exactly opposite in the two execution
orders. In Pattern A (communication then computation, e.g. alltoall + matmul) AIV communicates first
and signals with `CrossCoreSetFlag` while AIC waits with `CrossCoreWaitFlag`: direction AIV → AIC. In
Pattern B (computation then communication, e.g. matmul + alltoall) AIC computes first and signals
with `NotifyComputeComplete` while AIV waits with `WaitComputeComplete` and then issues `BarrierAll`
across ranks before the AllToAll: direction AIC → AIV. Upstream asserts that in each pattern the
first block is a fill with one side idle and the last is a drain with the other side idle. Not
established here.

## 2 · The wrong branch this removes
Everything else in the MC² chain is arithmetic over two phase costs; this entry is where the two
phases become two physical cores with a directed dependency. Three consequences an agent gets wrong
without it. The waiting side is the side whose profile is polluted — `CrossCoreWaitFlag` on AIC's
MTE2 pipeline is Pattern A's artefact (0060), and in Pattern B the waiting is on the AIV side, so
the pollution test's ratio may not be the same one. The fill and drain ends are occupied by
*different* cores in the two patterns, which is why the placement matrix (0063) has different rows
for them. And Pattern B carries an extra cost the diagrams make visible: a `BarrierAll` across all
ranks before each AllToAll, so its communication phase includes a global synchronisation that
Pattern A's does not.

## 3 · Ground / Source
`pipeline_balancing.md:26-62`, the AIC/AIV 分离架构 section. The architecture statement is quoted in
SOURCE. Pattern A, `:32-47`:

> AIV: PutToAllRanks(块0) → SetFlag(0) → PutToAllRanks(块1) → SetFlag(1) → ...
> AIC:                         WaitFlag(0) → DoMatmul(块0) → WaitFlag(1) → DoMatmul(块1) → ...

with the role table — AIV 先通信：将本卡数据 Put 到远端卡 Win 区 / `CrossCoreSetFlag` 通知 AIC 数据已
就绪; AIC 后计算：从 Win 区读取远端数据做 matmul / `CrossCoreWaitFlag` 等待 AIV 数据就绪 — and `:46`:
首块为 fill（AIV 通信，AIC 空闲等待），尾块为 drain（AIC 计算，AIV 已完成）.

Pattern B, `:48-62`:

> AIC: DoMatmul(块0) → NotifyComputeComplete(0) → DoMatmul(块1) → NotifyComputeComplete(1) → ...
> AIV:                  WaitComputeComplete(0) → BarrierAll → AlltoAll(块0) → WaitComputeComplete(1) → ...

with the role table quoted in SOURCE and `:62`: 首块为 fill（AIC 计算，AIV 空闲等待），尾块为 drain
（AIV 通信，AIC 已完成）。Pattern B 的 AIV 在每次 AllToAll 前需 `BarrierAll` 确保所有 rank 的 AIV
对齐.

`comm-compute/index.md:97-105` states the same architecture and both patterns in prose and routes here
for detail. The fusion-mode table at `index.md:85-91` maps five typical operator families onto the two
orders: AllGather+Matmul 通信→计算; ReduceScatter+Matmul and AllReduce+Matmul 计算→通信;
AllToAllv+GroupedMatmul 通信→计算; AllReduce/ReduceScatter with Quant+Matmul 计算→通信. `index.md:93`
excludes pure communication operators from the whole strategy.

## 4 · Procedure
Later phase, needs one card per rank; capture per 0057.
1. Device selection per 0057: one rank per device from an explicit list, board token per rank from the
   driver readout, occupancy recorded before and after.
2. Take one Pattern A operator (alltoall + matmul) and one Pattern B operator (matmul + alltoall).
3. Capture an instruction-level trace per rank, with AIC and AIV lanes distinguished, at `tileCnt=4`
   so fill, steady and drain are all present.
4. From each trace, extract: which core is idle during the first block and during the last; the
   synchronisation primitive each core waits on; and, for Pattern B, the position and duration of
   `BarrierAll` relative to each AllToAll.

## 5 · Checker — acceptance declared before the run
Verdict variables `fill_idle_core`, `drain_idle_core`, `wait_primitive(core)` and, for Pattern B,
`barrier_count` per AllToAll. Acceptance: Pattern A shows AIC idle in fill and AIV idle in drain with
AIC waiting on `CrossCoreWaitFlag`; Pattern B shows the reverse with AIV waiting on
`WaitComputeComplete` and exactly one `BarrierAll` per AllToAll.

Exit code is not the verdict. Both cores' lanes are published for every block index; a trace in which
neither core is idle during the first block is reported `no_fill_observed` rather than assigned to a
pattern — that would be the interesting case, since it would mean something already covers the fill.

Red input: Pattern A's expectations applied to the Pattern B trace. They must fail. If both patterns
satisfy both expectation sets, the trace is not resolving the two cores and no direction claim
follows.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; no board, no operator, no rank count. It does not establish the cost of any
synchronisation primitive, nor of Pattern B's `BarrierAll`, which is named but never quantified
anywhere in this skill. It says nothing about operators that both receive and send around one
computation, which fit neither pattern. The primitive names are upstream's and are not verified
against installed headers in this entry. Nothing here establishes that AIV is the only communication
path, or that UDMA and shared memory behave alike.
