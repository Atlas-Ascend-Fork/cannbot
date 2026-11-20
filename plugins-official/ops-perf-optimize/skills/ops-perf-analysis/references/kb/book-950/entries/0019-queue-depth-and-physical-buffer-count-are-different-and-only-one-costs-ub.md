```
ID:        0019-queue-depth-and-physical-buffer-count-are-different-and-only-one-costs-ub
LABEL:     trap
LEVEL:     L2 (memory hierarchy & residency)
STRATUM:   verified — §4 Arm 2 run on 950PR 2026-08-25 via §5: `depth_is_free` = TRUE exactly (largest per-buffer
           InitBuffer at BUFFER_NUM 2: 131072 at depth 2 AND at depth 4; at BUFFER_NUM 3: 87360 at both depths);
           control `buffernum_costs` = TRUE (87360 < 131072; totals 262080 vs 262144). Every probe touched its
           buffers' tails and read them back. Previously harvested.
BOARD:     950PR (measured 2026-08-25); 950DT unverified
SOURCE:    ops/ascendc-perf-optimize/references/single-core-pipeline/techniques/nobound-02-stage-order-rescheduling.md:81 — "**先确认 depth 改大不额外占 UB**：物理 buffer 数由 `InitBuffer(que, BUFFER_NUM, size)` 决定，queue depth 只约束同时挂起的句柄数。若两者绑定，加 depth 会压小 tile 粒度、tile 数变多，每 tile 固定开销（参数打包等）跟着乘，可能得不偿失"
           ops/ascendc-perf-optimize/references/single-core-pipeline/techniques/nobound-01-nobound.md:35 — "PingPong 使能时实际可用 UB 需除以 2，注意容量"
INDEX:     means=four kernels from one source (`TQue<VECIN, depth>` with depth ∈ {2, 4} × `InitBuffer(que, BUF, N)` with
           BUF ∈ {2, 3}), each buffer AllocTensor'ed and its last 32 B written and copied back; fresh process per
           probe, 32-B bisection of N
           conditions=CANN 9.1.0, 950PR, direct launch, plain vector kernel (no VF)
           readouts: largest granted / smallest refused N — d2b2 131072 / 131104; d4b2 131072 / 131104;
           d2b3 87360 / 87392; d4b3 87360 / 87392; buffer UB addresses 0, N[, 2N]
           time=2026-08-25
OVERTURN:  an allocation experiment on a named 950 board in which raising a queue's depth while
           holding `BUFFER_NUM` fixed reduces the largest tile that can be allocated — that
           would mean depth and physical buffer count are bound together on this toolkit, and
           the card's precondition is false rather than merely unchecked.
```

# 0019 · Queue depth and physical buffer count are different, and only one costs UB

## 1 · Claim
Measured on 950PR: a `TQue`'s **depth** costs no UB and its **BUFFER_NUM** costs all of it. With two
buffers per queue the largest per-buffer `InitBuffer` that runs is 131072 B at depth 2 and 131072 B at
depth 4 — identical to the byte; with three buffers it is 87360 B at both depths (3 × 87360 = 262080, the
largest multiple of 32 whose triple fits the 262144-B ceiling 950:0209 measured). Upstream's sentence
that queue depth and physical buffer count are different quantities and only the second consumes UB is
what the part does. Not established: 950DT; depths above 4; `TQueBind`.

## 2 · The wrong branch this removes
The delayed-write-back technique (0052) requires an output queue of depth 2, because the compute
stage enqueues while the previous tile is still awaiting dequeue. An agent that has internalised
the halving rule of 0018 — "double buffering halves usable UB" — will apply it to the depth
change, halve its tile budget, and re-tile. If the two quantities are in fact independent, that
re-tiling is a pure loss: smaller tiles, more of them, more per-tile fixed cost (0017), and the
reordering gain partly eaten by the very adjustment made to accommodate it. The opposite error
is equally available: assume depth is free, raise it, and silently exceed UB.

The general shape is worth stating because it recurs: two knobs with similar names, one of which
has a capacity cost and one of which may not, and a rule of thumb that names neither precisely.

## 3 · Ground / Source
`nobound-02:77-84`, the card's stop rules, of which the third is this entry's subject:

> - **先确认 depth 改大不额外占 UB**：物理 buffer 数由 `InitBuffer(que, BUFFER_NUM, size)`
>   决定，queue depth 只约束同时挂起的句柄数。若两者绑定，加 depth 会压小 tile 粒度、tile 数
>   变多，每 tile 固定开销（参数打包等）跟着乘，可能得不偿失。

`nobound-02:61` states the requirement that provokes it — 输出队列 depth 取 2（`Compute` EnQue
时上一拍还挂着未 DeQue）— and `nobound-02:91` makes the correction to its sibling card explicit:

> 另外 nobound-01 的红线"PingPong 使能时可用 UB 需除以 2"针对的是物理 buffer 数；本卡红线
> 补充了 **queue depth 与物理 buffer 数是两回事**，depth 加大不一定占 UB，取决于
> `InitBuffer` 的 `BUFFER_NUM`。

So the skill contains its own correction, made in one card, to a rule stated flatly in another
(`nobound-01:35`) and in the vec diagnosis page (`vec.md:103`, entry 0018). The correction is
carried in the corrected card only; nothing propagates it back. Recorded as C-950core-009.

## 4 · Procedure
Two arms; the first is read-only inspection of the installed toolkit and needs no device.
```bash
# Arm 1 — does the queue implementation couple depth to buffer count?  (-R, not -r: symlinks)
T=/usr/local/Ascend/cann-9.0.0-beta.2
grep -Rn "InitBuffer" $T/arm64-linux/asc/include | head
grep -Rn "class TQue\|TQueBind\|bufferNum\|depth" $T/arm64-linux/asc/include/basic_api | head -20
```
Arm 2 (later phase, needs a card; board token from the driver readout, device selection per 0010,
occupancy recorded either side): in a minimal kernel, bisect the largest `size` for which
`InitBuffer(que, 2, size)` initialises, at queue depth 2 and again at queue depth 4, changing
nothing else. Then repeat with `BUFFER_NUM` 2 and 3 at fixed depth, to confirm the bisection is
sensitive to the knob that is supposed to cost UB.

**As run (2026-08-25, job tque950 on the 950 machine):** Arm 1 (header read) was superseded by the
behavioural arm; Arm 2 as written with the four combinations built as four kernels in one source
(`depth` is a template parameter), each probe a fresh process that allocates the queue, `AllocTensor`s
every buffer, writes eight words at each buffer's tail, copies the last buffer's tail to GM (on its own
64-B line, per this project's scalar/vector store rule) and reads it back; a probe counts as granted only
if the words read back. Bisection at 32-B steps between 1024 and 270336 per buffer.

## 5 · Checker — acceptance declared before the run
Verdict variable `depth_is_free`, declared now:
`depth_is_free = (max_size(depth=4) == max_size(depth=2))` exactly, not within a tolerance — a
capacity boundary is discrete and a difference of one allocation granule is a difference.
Control variable `buffernum_costs` = `max_size(BUFFER_NUM=3) < max_size(BUFFER_NUM=2)`, which
must be true; if it is not, the bisection is not measuring UB pressure at all and neither result
is usable.

Exit code is not the verdict — an over-large `InitBuffer` may abort the kernel, which is the
datum. The checker records the largest success and the smallest failure for each configuration
and prints all four pairs.

Red input: the `BUFFER_NUM` arm. It is included precisely so the instrument must demonstrate it
can see a UB cost before its report of "no cost" is believed. A checker that only varied depth
could report `depth_is_free` on an instrument that was blind to everything.

## 6 · Evidence
RUN 2026-08-25, 950PR (idle before and after). Largest granted / smallest refused per-buffer N (32-B steps;
refusal = 507035 at the tail touch):

| depth | BUFFER_NUM | largest granted N | smallest refused N | total granted | buffer addresses |
|---|---|---|---|---|---|
| 2 | 2 | 131072 | 131104 | 262144 | 0, 131072 |
| 4 | 2 | 131072 | 131104 | 262144 | 0, 131072 |
| 2 | 3 | 87360 | 87392 | 262080 | 0, 87360, 174720 |
| 4 | 3 | 87360 | 87392 | 262080 | 0, 87360, 174720 |

`depth_is_free` = (131072 == 131072) = TRUE, and again at BUFFER_NUM 3 (87360 == 87360). Control
`buffernum_costs` = (87360 < 131072) = TRUE. `GetRuntimeUBSize()` echoed 253952 in every probe (the
API tier); the granted totals reach the 262144 enforcement ceiling of 950:0209.

## 7 · Scope limits — what this entry does NOT establish
950PR only, direct launch, a plain vector kernel (a VF-bearing kernel's ceiling is the grant + 8 KB,
950:0238 — depth was not re-tested there); depths 2 and 4 only; `TQue<VECIN>` only (`TQueBind` and
`VECOUT` not probed); whether depth costs anything OTHER than UB (event IDs, scheduling slots — 910:0043
/ 910:0067's territory) is not measured here. Nothing transfers to the 910 book (RULES.md Art. 1).
