```
ID:        0320-doubling-initbuffer-num-without-restructuring-the-loop-into-prefetch-form-buys-nothing
LABEL:     trap
LEVEL:     L1 (core & pipe assignment)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/elementwise/double_buffer_design.md:228-232
           — "1. **仅改 InitBuffer 的 num 不够！必须重构循环为预取模式**。- 错误：仅改
           `InitBuffer(..., num, ...)` 的 `num=1→2`，循环不变 → 无性能提升。- 正确：必须实现预取
           （prefetch）循环。" · "2. **Tiling 联动：InitBuffer 的 num 翻倍时 ub_factor 必须减半**。
           双缓冲使队列内存翻倍，若不调整 ub_factor，总 UB 用量超限会导致编译失败或运行时越界。"
SOURCE:    same file:144-158 — "// 主循环：计算 i，同时预取 i+1，写回 i-1 ... for (uint32_t i = 0;
           i < tileNum - 1; i++) { CopyIn(i + 1); Compute(i); if (i > 0) { CopyOut(i - 1); } }" ;
           :236 — "4. **Tail tile 处理**：tile_size 减半后，tile 数量翻倍，需确保尾 tile 处理逻辑
           正确更新。"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a paired build on a named 950 board in which raising `InitBuffer`'s `num` from 1 to 2
           with the loop left in `CopyIn(i); Compute(i); CopyOut(i)` form measurably shortens the
           kernel outside the run spread — the queue machinery would then be performing the
           reordering itself and the restructure would be unnecessary.
```

# 0320 · Doubling `InitBuffer`'s `num` without restructuring the loop into prefetch form buys nothing

## 1 · Claim
Upstream asserts that enabling double buffering is two changes, not one, and that doing only the
first gives no speed-up: raising `InitBuffer`'s `num` from 1 to 2 allocates the second physical
buffer, but the loop must also be rewritten so that iteration `i` issues the copy-in of `i+1`,
computes `i`, and copies out `i−1`. Upstream asserts two obligations that travel with the change:
the host-side `ub_factor` must be halved in the same edit, because the queue's UB footprint doubles
and an unadjusted budget overruns at compile time or at run time; and the tail-tile logic must be
recomputed, because halving the tile size doubles the tile count. Not established here.

## 2 · The wrong branch this removes
This is the most available wrong branch in the whole double-buffering subject, because the
one-line change looks complete. `InitBuffer(q, 2, size)` compiles, runs, produces correct output,
consumes twice the UB — and, upstream says, runs at the same speed. An agent measuring it finds no
gain and concludes double buffering does not help this operator. It then either reverts (losing a
real optimisation) or, worse, keeps the doubled allocation because "it is enabled" and pays the UB
without the overlap.

The diagnosis is available and is already in this book from the other shelf: `950:0012` gives the
trace signature — MTE2 and VECTOR alternating means the overlap is real; MTE2 all before VECTOR all
after means it is not. So the pair is: `0320` says what to do, `950:0012` says how to see whether it
happened. An agent with only the first will make the change and not verify it; with only the second
it will diagnose the failure and not know the cause.

The second wrong branch is the `ub_factor` one and it fails in the opposite direction — loudly, but
at a distance. Doubling `num` without halving `ub_factor` doubles total UB demand. If it overruns at
compile time the message points at `InitBuffer`; if it overruns at run time it is an out-of-bounds
write into the neighbouring buffer, and the symptom is a wrong number in an unrelated tensor. The
edit is in the kernel and the fix is on the host, which is why it gets missed.

The third is the tail. Halving the tile size doubles `tileNum`; a tail computation that was correct
at the old tile size — `tileNum = ceil(total / tileSize)` and a last-tile length derived by
subtraction — is still *arithmetically* correct but now exercises a different remainder, and any
latent off-by-one in it is newly reachable. Upstream states the obligation and not the failure;
`910`-side experience recorded elsewhere in this project (a tail length derived by subtraction going
negative) is the shape of thing this obligation exists to prevent, and is not carried across
(RULES.md Art. 1).

## 3 · Ground / Source
The two-part change, `double_buffer_design.md:228-236`:

```
1. **仅改 InitBuffer 的 num 不够！必须重构循环为预取模式**。
   - 错误：仅改 `InitBuffer(..., num, ...)` 的 `num=1→2`，循环不变 → 无性能提升。
   - 正确：必须实现预取（prefetch）循环。

2. **Tiling 联动：InitBuffer 的 num 翻倍时 ub_factor 必须减半**。双缓冲使队列内存翻倍，若不调整
   ub_factor，总 UB 用量超限会导致编译失败或运行时越界。
...
4. **Tail tile 处理**：tile_size 减半后，tile 数量翻倍，需确保尾 tile 处理逻辑正确更新。
```

The prescribed loop, `:141-158`:

```cpp
// 预取：加载第一个 tile
CopyIn(0);

// 主循环：计算 i，同时预取 i+1，写回 i-1
// 实现 MTE2 / Vector / MTE3 三级硬件流水线并行
for (uint32_t i = 0; i < tileNum - 1; i++) {
    CopyIn(i + 1);      // MTE2: 预取下一个 tile（与本轮 Vector 并行）
    Compute(i);         // Vector: 计算当前 tile（与上一轮 MTE3 并行）
    if (i > 0) {
        CopyOut(i - 1); // MTE3: 写回前一个结果（与下一轮 MTE2 并行）
    }
}

// 收尾：处理最后两个 tile（循环内未写回的尾部）
Compute(tileNum - 1);
for (uint32_t i = (tileNum > 1) ? tileNum - 2 : 0; i < tileNum; i++) {
    CopyOut(i);
}
```

Read the epilogue carefully — it is where the software-pipelined form pays its debt. The main loop
stops at `tileNum − 1` and never computes the last tile, and it never copies out the last two. The
epilogue does both. An implementer who copies the loop and not the epilogue drops one tile of
output, and the shape of the failure is a wrong final tile rather than a fault.

The naive form it replaces, `:110-126`, makes the serialisation explicit with three comments —
`阶段 1：MTE2 搬入（Vector idle!）`, `阶段 2：Vector 计算（MTE2 idle!）`, `阶段 3：MTE3 搬出
（Vector idle!）`.

The synchronisation model, `:42-46`, names `HardEvent::MTE2_V`, `HardEvent::V_MTE3` and
`PipeBarrier<PIPE_V>`; the explicit-event variant at `:161-186` shows the hand-managed form with
`MTE3_MTE2` guarding buffer reuse and `EVENT_ID6`/`EVENT_ID7` as the ping/pong ids.

The restated checklist, `:283-288`, is the executable form of this entry and four of its six items
can fail.

The distinction between queue *depth* and physical buffer *count* — `TQue` depth constrains
outstanding handles, `InitBuffer`'s `num` allocates buffers, only the latter is the double-buffer
switch — is stated at `:132-135` and is already carried by `950:0019` from the other shelf. Cited,
not re-entered (same repo, one origin, RULES.md Art. 3).

Nothing in this section is measured. The file's header table claims `MTE2/VECTOR 重叠度 0% →
~80-90%` and `吞吐量提升 20-50%` with no shape, dtype, board or tool; those are not carried.

## 4 · Procedure
Proposed, runnable later on a named 950 board. Never run in this phase.

Four builds of one memory-bound elementwise operator, one variable between adjacent pairs:

- **B0** `num = 1`, serial loop. Baseline.
- **B1** `num = 2`, loop unchanged. *This is the claim under test.*
- **B2** `num = 2`, prefetch loop, `ub_factor` halved.
- **B3** `num = 2`, prefetch loop, `ub_factor` **not** halved. Expected to fail to build or to
  overrun; retained as the correctness fixture (§5).

Record for each: kernel time, MTE2 and VECTOR segment times, total UB requested, and the trace
signature `950:0012` names (do MTE2 and VECTOR alternate). Variance floor first — one build, 30
in-process runs, 5 fresh-process runs, IQR over median, reported beside every comparison.

Arm 1 — the null. `B1 − B0` is predicted to be inside the floor while `B2 − B0` is outside it. Both
comparisons are reported; reporting only the second would make the entry unfalsifiable.

Arm 2 — the mechanism, not just the outcome. Extract the trace signature for B1 and B2. Upstream's
claim is not merely "B1 is not faster" but "B1 does not overlap", and those are different
statements: B1 could overlap and be limited elsewhere. If B1's trace *does* alternate while its
time does not move, the entry is corrected in place — the loop structure would not be what prevents
overlap.

Arm 3 — the tail obligation. Run B2 at a total element count deliberately not divisible by the
halved tile size, and compare the final tile against the reference specifically. This is the arm
that exercises the doubled tile count.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three idle samples; re-sample after; discard if the die moved. Refuses to assume: that
a free die stays free; that a die may be substituted; that `ub_factor` reached the kernel — total UB
requested is echoed from the kernel, not read from the host struct; that the compiler left the loop
as written (B1 and B2 are disassembled and diffed, because a null result between two builds the
compiler reordered identically is unattributable).

## 5 · Checker — acceptance declared before the run
Verdict `naive_db_gain` = (B0 median − B1 median) / B0 median, with the floor. Declared before the
run: the entry is **supported** iff `naive_db_gain` is **inside** the floor. This is a checker whose
green is a null result, and saying so now is what makes the null readable afterwards. The OVERTURN
fires iff `naive_db_gain` is positive and outside the floor.

Verdict `prefetch_gain` = (B0 median − B2 median) / B0 median. Declared: this **must** be positive
and outside the floor, and it is the fixture that makes the first verdict meaningful — see below.

Verdict `overlap_b1` / `overlap_b2` = the trace signature from Arm 2 for each build.
Verdict `tail_correct` = true iff Arm 3's final tile matches the reference.

The exit code is not the verdict. Three guards.

First, every build is compared elementwise against a CPU reference over the whole output — B2's
epilogue is exactly the piece an implementer drops, and a dropped final tile is a *faster* kernel.

Second — the input that makes this checker go red. `prefetch_gain` is the planted positive: if
`naive_db_gain` is inside the floor **and** `prefetch_gain` is also inside the floor, then the
operator is not memory-bound, the whole experiment is measuring nothing, and the green on the first
verdict is void rather than confirming. A checker that could only ever report "no difference" is the
known blind species; requiring B2 to move is what excludes it here. B3 is the second fixture: it
**must** fail to build or fail precision. If B3 passes cleanly, the `ub_factor` linkage is not
reaching the allocation and obligation 2 was never under test.

Third, no verdict is reported without the floor, and the trace signature is reported alongside the
timing for both B1 and B2 — a timing null with an unexamined trace cannot distinguish "did not
overlap" from "overlapped and was limited elsewhere".

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. Upstream gives no measured
before/after for any of the four builds; its header table's `0% → ~80-90%` overlap and `20-50%`
throughput figures carry no case and are not carried here.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The entry does not establish that the prefetch restructure *is*
faster — only that upstream asserts the `num` change alone is not, and §4 measures both halves. It
carries no magnitude: every benefit figure in the source file is unscoped. It does not establish
that the queue machinery cannot perform the reordering itself on some toolkit version; that is the
OVERTURN and it is untested. The `ub_factor` obligation is stated by upstream as a host-side rule
and is not verified against any tiling implementation here. The epilogue's correctness (`0320` §3)
is read from upstream's code excerpt and has not been compiled. The document that states all of this
carries no 950 constant anywhere (`0319`), so the *mechanism* is taken as model-level and that
assumption is untested. BOARD is `family-claimed(unverified)`. Nothing transfers to the other book
(RULES.md Art. 1).
