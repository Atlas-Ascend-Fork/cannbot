```
ID:        0456-one-resident-buffer-proportional-to-m-times-d-forces-the-whole-architecture-to-stream-and-branching-on-d-is-forbidden
LABEL:     knowledge
LEVEL:     L2 (memory hierarchy & residency)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-tiling-design/references/flashattention/design.md:63-84 —
           "回答:**UB 上是否存在常驻 ∝ m × D 的 buffer?**" · "- **答案是"有"** → 必须改架构,把
           `[m, D]` 移到 GM workspace,UB 改用固定大小 ping-pong buffer 分 chunk 处理(称为
           **streaming UB 模式**)" · "3. m × D 矩阵在 UB 内按行分 chunk 处理,chunk 大小 =
           `bufferSize / D_align`(运行期参数自适应,非编译期分支)" · "5. **单一代码路径**覆盖全 D 范围" ·
           "- streaming 在小 D 下退化为单 chunk loop,实测开销小(典型 ≤ 5%;decode 长 KV 等少数场景
           可能略高,具体取决于 chunk loop 调度开销)" · "**禁止**:把 Tiling 决策做成
           `if D ≤ X: 朴素模式 else: streaming` 两套代码。"
SOURCE:    same file:462-468 — "**流式 chunk 行数**(streaming UB 模式下,真·通用公式): /
           ```chunkRows = chunkBufferBytes / (D_align × sizeof(compute_T))``` / > 该公式是 streaming
           UB 模式下"chunk 与 D 解耦"的关键数学依据(不是 GQA 特例)" ; :251-259 — the per-buffer
           elimination checklist naming `O_acc`, the P·V intermediate, and the `sum` broadcast
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured FlashAttention pair on a named 950 board — streaming versus a naive resident
           `[m, D]` build — in which the streaming build's overhead at small D exceeds 5% outside the
           variance floor, or in which the naive build fits UB at the largest D the operator claims to
           support. Either observation kills a different half: the first kills the "typically ≤ 5%"
           figure that justifies the single path, the second kills the premise that a resident
           `[m, D]` buffer must overflow at all.
```

# 0456 · One resident buffer proportional to m × D forces the whole architecture to stream, and branching on D is forbidden

## 1 · Claim
Upstream asserts a single yes/no question decides a FlashAttention operator's UB architecture: does any
UB buffer stay resident with a size proportional to `m × D`? Upstream asserts that if the answer is
yes — the named suspects being the `[m, D]` accumulator `O_acc`, the `P·V` intermediate matrix, and a
broadcast-expanded `sum` — the architecture must change: the `[m, D]` matrix moves to GM workspace and
UB uses fixed-size ping-pong buffers processing the matrix in row chunks, which upstream names the
"streaming UB mode". Upstream asserts five properties of that mode, of which the load-bearing ones are
that the UB buffer size is chosen independently of `D`, that the chunk height is a runtime quotient
`chunkRows = chunkBufferBytes / (D_align × sizeof(compute_T))` rather than a compile-time branch, and
that a single code path covers the whole `D` range. Upstream asserts the streaming path degenerates to
a one-chunk loop at small `D` with a measured overhead typically at or below 5%, possibly higher in
decode-with-long-KV cases. Upstream forbids the alternative explicitly: two code bodies selected by
`if D ≤ X`. Not established here.

## 2 · The wrong branch this removes
Without this entry a competent agent sizes UB for the shapes in front of it. The MVP has a small head
dimension, `[m, D]` fits comfortably, `O_acc` lives in UB where the arithmetic is cheapest, and every
test passes. The architecture is then *correct and fast for the shapes tested*, and it has no
generalisation: at `D = 512` the same buffer needs several times the whole UB, and the fix is not a
tiling adjustment but a different memory architecture — `O_acc` in GM, read back and rescaled per
chunk, with the queue plumbing that implies. The cost of discovering this late is a rewrite of §4's
memory division, §7's pipeline and the host tiling that feeds both.

The normal checks do not catch it because UB overflow is not a compile error and, per `0458`, not
always a runtime error either. What an agent sees is a working operator whose supported `D` range is
an accident of the buffers it happened to allocate.

The second wrong branch is the one upstream bothers to forbid in bold, which means it is the one
people take after seeing the first: keep the fast resident path for small `D` and add a streaming path
for large `D`, chosen by a threshold. This is locally rational — it costs nothing at small `D` and it
does support large `D` — and upstream rejects it on maintenance rather than performance grounds:
`维护两套 codebase 的成本远高于 streaming 单路径的小开销`. An agent that weighs only the measured
number (≤5%) will take the branch; the argument for the single path is the two-codebase cost, and it
is an argument, not a measurement.

## 3 · Ground / Source
The decision and the mode it selects, `references/flashattention/design.md:63-84`:

```
### §2.2 UB 模式决策(streaming 与 D 解耦判定标准)

回答:**UB 上是否存在常驻 ∝ m × D 的 buffer?**

如果有(典型如把 `[m, D]` O_acc 常驻 UB、把 P·V 中间矩阵常驻 UB、把 sum 广播展开后常驻 UB 等),大 D 场景下 UB 必然溢出。判定:

- **答案是"有"** → 必须改架构,把 `[m, D]` 移到 GM workspace,UB 改用固定大小 ping-pong buffer 分 chunk 处理(称为 **streaming UB 模式**)
- **答案是"没有"** → 已经走 streaming,继续设计

**streaming 模式的核心原则**:
1. UB 用**固定大小**(与 D 无关)的 ping-pong buffer
2. `O_acc` 改存 GM workspace,跨 chunk 通过输入接收 queue 流转(读回 + rescale + 累加 + 写出)
3. m × D 矩阵在 UB 内按行分 chunk 处理,chunk 大小 = `bufferSize / D_align`(运行期参数自适应,非编译期分支)
4. Cube Mmad 配合 k-axis 分块(见 §2.3),L0 / L1 也与 D 解耦
5. **单一代码路径**覆盖全 D 范围

**决策依据**:
- streaming 在小 D 下退化为单 chunk loop,实测开销小(典型 ≤ 5%;decode 长 KV 等少数场景可能略高,具体取决于 chunk loop 调度开销)
- 不按 D 分支:维护两套 codebase 的成本远高于 streaming 单路径的小开销
- 扩展性:未来更大 D / 新平台 UB 容量变化不需要重做决策

**禁止**:把 Tiling 决策做成 `if D ≤ X: 朴素模式 else: streaming` 两套代码。
```

Two sentences in that block are of different kinds and are joined by layout rather than by argument.
`实测开销小(典型 ≤ 5%…)` is presented as measured — `实测`, measured in practice — and carries no
case, no shape, no `D`, no dtype, no board, no tool and no repetition count. `维护两套 codebase 的
成本远高于 streaming 单路径的小开销` is an engineering judgement. The prohibition rests on both, and
only the second is fully stated. The `≤ 5%` is the only number in the FA family's 1224 lines that is
presented as a measurement; it is recorded as `Q-950fin-04` and as `C-950fin-005` against the
family's own rule at `design.md:208` that buffer formulas may contain no bare numbers.

The chunk formula, `:462-468`:

```
- **流式 chunk 行数**(streaming UB 模式下,真·通用公式):

chunkRows = chunkBufferBytes / (D_align × sizeof(compute_T))

> 该公式是 streaming UB 模式下"chunk 与 D 解耦"的关键数学依据(不是 GQA 特例):chunk 行数由"UB 单 chunk 容量"与"每行字节数"的比值决定,从而让小 D 时 chunk 行数大、loop 少,大 D 时 chunk 行数小、loop 多,**单一代码路径自适应**。
```

The formula is the mechanism, and it is worth stating what it does *not* contain: no `m`. The chunk
height is independent of the number of rows to be processed, so the loop count absorbs `m` as well as
`D`. `D_align` rather than `D` means the quotient is taken against the padded row, so at `D` just
above an alignment boundary the chunk height drops by a whole row's worth of budget — an aliasing
upstream does not discuss and which is where the "decode long KV" exception it hedges about may live.

The per-buffer landing check, `:251-259`, turns the architectural question into an audit list —
`O_acc(主嫌疑):是否已移到 GM workspace?`, then the `P·V` intermediate, the previous round's
`O_acc` cache, and the broadcast-expanded `sum`, with a named alternative for the last:
`sum 广播是否走 BinaryRepeatParams(src1RepStride=1) 在 Div 内自动消费,而非分配中间 buffer?`. That
last item is the only one of the four with a concrete API-level remedy, and it is the one an agent
would not think of, because a broadcast is normally materialised.

The consequence for the levels below UB is stated once and not developed: `Cube Mmad 配合 k-axis
分块(见 §2.3),L0 / L1 也与 D 解耦`. So streaming is not a UB decision with UB consequences — it is
an architecture decision that reaches L0 and L1, whose own decoupling is `0457`'s neighbourhood.

Two files in one repository are one origin (RULES.md Art. 3).

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind on three consecutive idle samples only; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and
discard the case if the die moved. Variance floor first: one build, 30 in-process and 5 fresh-process
runs, IQR over median, reported beside every point.

**Arm 1 — the overhead figure, which is the number the prohibition rests on.** Two builds of one GQA
kernel: (a) `O_acc` resident in UB, (b) streaming per upstream. Sweep `D ∈ {64, 128, 256}` — the range
where both builds fit — at prefill and decode shapes, `Sq ∈ {1, 512}`, `Sk ∈ {512, 8192}`. Report
`(t_streaming − t_resident) / t_resident` per point with its floor. Upstream predicts ≤5% typical and
allows more in decode-with-long-`Sk`; this arm either finds that or moves it, and either way it is the
first scoped version of the figure.

**Arm 2 — where the resident build stops.** Extend the sweep to `D ∈ {512, 1024}` with build (a) only,
querying UB at runtime (`PlatformAscendC::GetCoreMemSize`) and echoing the computed total occupancy
before launch. Record the largest `D` at which (a) fits, and what happens at the first `D` where it
does not: a host-side refusal, a silent overrun (`0458`), or a fault. Upstream's premise is `大 D 场景
下 UB 必然溢出`; this arm gives that "必然" a number on this board.

**Arm 3 — the chunk formula.** For build (b), echo `chunkRows` and `chunkBufferBytes` from the device
at every point of arm 1's sweep, and confirm `chunkRows == chunkBufferBytes / (D_align × sizeof(T))`
exactly. Sweep `D` across an alignment boundary (`D ∈ {120, 128, 136}`) and record the chunk height and
the loop count on both sides, to expose the `D_align` aliasing §3 names. Retained even though the
formula is arithmetic: what is being tested is that the shipped kernel uses it, not that it is true.

**Arm 4 — the broadcast remedy, retained because it may not bite.** Build (b) with the `sum` broadcast
materialised into an intermediate buffer versus consumed inside `Div` via
`BinaryRepeatParams(src1RepStride=1)`. If the two measure the same, the remedy is a UB-budget
technique with no time cost, which is what upstream implies but never says; if the in-`Div` form is
slower, the elimination checklist trades time for capacity and §7 records that.

Refuses to assume: that a free die stays free, or that a die may be substituted; that `ub_size` is a
literal (queried and echoed — the corpus carries four incompatible script defaults for it, C-006);
that the two builds differ only in residency (each echoes its full buffer list and total occupancy);
that a build which fits is a build that is correct (every point carries an elementwise comparison
against an FP64 reference at the declared atol); that a single `D` value characterises the sweep.

## 5 · Checker — acceptance declared before the run
Verdict `overhead(D, shape) = (t_streaming − t_resident) / t_resident`, declared before the run, with
its floor. Acceptance for upstream's figure as written: `median overhead ≤ 0.05` over the prefill
points of arm 1. The OVERTURN's first half fires iff `overhead > 0.05 + floor` at a majority of those
points — the "typically ≤ 5%" would then not hold on this board, and the single-path argument would
rest on the maintenance premise alone, which is not measurable.

Verdict `resident_ceiling` from arm 2: the largest `D` at which build (a) both fits and agrees. The
OVERTURN's second half fires iff `resident_ceiling` reaches the largest `D` the operator claims to
support — the premise that a resident `[m, D]` must overflow would then be false here.

Verdict `chunk_formula_holds` from arm 3: boolean, exact integer equality at every point, plus the
recorded chunk heights on both sides of the alignment boundary.

The exit code is not the verdict: build (a) at an oversized `D` may exit 0 having quietly overwritten a
neighbouring buffer, which is the failure `0458` documents. Guards: (1) every point carries its
elementwise agreement, its echoed total UB occupancy and the queried `ub_size`; a point missing any is
untestable, never agreement; (2) **the input that makes this checker go red**: arm 1 at the smallest
`D` with `Sq = 1` and one KV block, where streaming degenerates to a single chunk and the two builds
execute the same work — if `|overhead|` there exceeds the floor, the builds differ in something other
than residency and every overhead number in the sweep is an artifact; (3) arm 2's "fits" is decided by
the echoed occupancy sum against the queried capacity, never by the absence of a crash.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The decision question, the
five streaming principles, the two-part decision basis, the prohibition, the chunk formula and the
four-item elimination checklist are file reads performed at drafting time. The observations that the
chunk formula contains no `m`, that `D_align` rather than `D` creates an aliasing at alignment
boundaries, and that the `≤ 5%` figure carries no scope, are readings of upstream's own lines, not
observations of a build.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The entry does not establish the 5% overhead — upstream calls it
`实测` and supplies no case, shape, dtype, board, tool or repetition count, and this entry inherits
none of that. It does not establish that a resident `[m, D]` buffer overflows UB at any particular
`D`, since UB capacity on this family is itself contested in the corpus (C-003, C-004, C-006). It does
not establish that the single-code-path decision is right — half of upstream's stated basis is a
maintenance-cost judgement that no procedure can test. It does not establish the L0/L1 decoupling that
`:76` claims follows from streaming; that is `design.md §2.3`'s material and is not carried here. It
does not cover the split-KV-reduce strategy, whose `O_acc` is a per-core partial in a different
workspace segment (`0454`). It does not establish `chunkBufferBytes` itself, which upstream never
defines beyond "the UB single-chunk capacity". No board token appears in either passage, so BOARD is
`family-claimed(unverified)`; §4 names 950PR/950DT only as where our run would happen. Nothing here is
established for any 910-family board.
