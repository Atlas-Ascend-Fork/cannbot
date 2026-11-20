```
ID:        0321-double-buffering-has-an-off-switch-and-a-ub-that-holds-the-whole-case-is-when-to-use-it
LABEL:     knowledge
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/elementwise/double_buffer_design.md:86-96
           — "### 3.2 自适应双缓冲决策 / 当 UB 足够大时可一次性容纳所有数据时，**无需双缓冲**
           （减少同步开销）；否则启用双缓冲隐藏延迟。" · "bool useDb = true; if (maxRow >
           rowPerHeadCore) {  // UB 足够大 / useDb = false; } / SetTilingKey(context, xDtype, useDb);"
SOURCE:    same file:50-56 — the buffer-count ladder (Double 2 / Triple 3 for AIC+AIV / 2×2 Matrix 4
           for matmul M+K / TQueBind 1 for in-place / custom PingPong for multi-level) ;
           :268-279 — "if (算子是 memory-bound && MTE2 active >> VECTOR active): ... elif
           (UB 足够大，可一次容纳所有数据): → 不使用双缓冲（减少同步开销） / else: → 单缓冲即可
           （compute-bound 场景双缓冲无收益）"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured operator on a named 950 board whose whole working set fits UB and which is
           nonetheless faster with double buffering than without — the synchronisation overhead
           would then be smaller than whatever residual overlap remains, and the off switch would be
           the wrong default for that regime.
```

# 0321 · Double buffering has an off switch, and a UB that holds the whole case is when to use it

## 1 · Claim
Upstream asserts that double buffering is a conditional optimisation with two named regimes in which
it should be **off**. When UB is large enough to hold the whole case at once, upstream asserts
double buffering should not be enabled, on the stated ground that there is nothing left to hide and
the synchronisation costs remain. When the operator is compute-bound rather than memory-bound,
upstream asserts single buffering suffices, on the stated ground that double buffering has no
benefit there. Upstream asserts that the decision is made host-side and encoded in the tiling key,
and gives the shape of that decision as a `useDb` flag passed to `SetTilingKey`. Upstream asserts a
buffer-count ladder rather than a binary: 2 for general memory-bound Vector work, 3 for AIC+AIV
mixed cores so that movement, Cube and Vector overlap in three stages, 4 as a 2×2 matrix for matmul
splitting M and K simultaneously, 1 via `TQueBind` for in-place read-modify-write (saving 50 % of
the buffer), and hand-flagged ping-pong for multi-level L1/L0 storage. Not established here.

## 2 · The wrong branch this removes
Double buffering is the most reflexively applied AscendC optimisation, and the reflex is what this
entry interrupts. The cost is real and is stated in the same file: the queue's UB footprint doubles,
`ub_factor` halves, the tile count doubles, and the loop acquires per-tile `SetFlag`/`WaitFlag`
pairs that upstream describes as having `轻微开销` and warns can offset the gain if over-applied.
Apply that to an operator whose data already fits, and every one of those costs is paid for an
overlap that has nothing to overlap with.

The second wrong branch is the compute-bound case, and it is the one that produces the confusing
measurement. On a compute-bound operator, enabling double buffering typically shows *no* change —
which an agent reads as "the change did not take", and then debugs, and then finds the trace
signature is fine, and then concludes something is wrong with the tooling. Nothing is wrong; the
regime was misidentified. `950:0012` supplies the trace check and this entry supplies the reason the
check can come back healthy with no gain attached.

The third is the ladder. Reading double buffering as "2" makes 3 and 4 invisible, and they are the
answers to different questions: 3 exists because a mixed AIC/AIV kernel has *three* producers to
overlap, not two, and 4 exists because matmul streams along two axes at once. An agent that has
learned "double buffering" and meets a CV-fusion kernel will pick 2 and leave the Cube stage
serialised behind the Vector stage.

`TQueBind` at the other end is the one most likely to be missed entirely: for a read-modify-write
whose input and output are the same tensor, one physical buffer serves both queue positions, and
upstream states the saving as 50 %. That is not a variant of double buffering, it is its opposite,
and it lives in the same table.

## 3 · Ground / Source
The adaptive decision, `double_buffer_design.md:86-96`:

```
### 3.2 自适应双缓冲决策

当 UB 足够大时可一次性容纳所有数据时，**无需双缓冲**（减少同步开销）；否则启用双缓冲隐藏延迟。

// Host 侧自适应决策
bool useDb = true;
if (maxRow > rowPerHeadCore) {  // UB 足够大
    useDb = false;                // 不使用双缓冲
}
SetTilingKey(context, xDtype, useDb);
```

The condition as written is `maxRow > rowPerHeadCore`, glossed `UB 足够大`. Neither symbol is
defined in the file. The reading consistent with the gloss is that `maxRow` is the row count UB can
hold and `rowPerHeadCore` the row count this core must process, so the test is "capacity exceeds
demand" — but that is an inference from a comment, and the two names are recorded as undefined in
`harvest/standing/950-bp.md`. An implementer cannot lift this snippet without resolving them.

The routing tree, `:267-279`:

```
if (算子是 memory-bound && MTE2 active >> VECTOR active):
    if (纯 Vector 算子):
        → 启用 Double Buffer（InitBuffer num=2）
        → tile_size 减半，保持 UB 预算
    elif (Cube+Vector 融合):
        → 启用 Triple Buffer（InitBuffer num=3）
        → 搬运/Cube/Vector 三级流水
    elif (UB 足够大，可一次容纳所有数据):
        → 不使用双缓冲（减少同步开销）
else:
    → 单缓冲即可（compute-bound 场景双缓冲无收益）
```

Note the tree's structure is defective as written: the `UB 足够大` arm sits inside the
`memory-bound && MTE2 active >> VECTOR active` branch, *after* two arms that will already have
matched almost every operator reaching it (a kernel is either pure-Vector or CV-fused). So the off
switch is written in a position it can rarely be reached from. The prose at `:88` and the
constraints list at `:244` (`6. **自适应策略**：UB 足够大时（可一次容纳所有数据），不使用双缓冲，
减少同步开销`) both state it unconditionally, so the *rule* is clear and the *tree* mis-encodes it.
Recorded in `harvest/standing/950-bp.md`; it is the same species `950:0005` records for the sibling
shelf's bound-routing tree (arms with no precedence) and `950:0164` records for its conversion
family (a decision node whose arms agree).

The ladder, `:50-56`:

```
| 策略 | Buffer 数量 | 适用场景 | 流水阶段 |
| Double Buffer | 2 | 通用 memory-bound | 搬入/计算/搬出三级重叠 |
| Triple Buffer | 3 | AIC/AIV 混合核（Cube+Vector） | 搬运/Cube/Vector 三级同时 |
| 2×2 Matrix Buffer | 4 | Matmul 切 M+K 双维度 | M/K 双维度同时流水 |
| TQueBind | 1（VECIN/VECOUT 共享） | 读-改-写 in-place | 节省 50% buffer |
| Custom PingPong | 2+（手写 flag） | FlashAttention 多级存储 | L1/L0 多级 PingPong |
```

The triple-buffer implementation sketch at `:190-213` is a three-way rotating policy class with
three independent flags (`flag1_`, `flag1_vec1_`, `flag1_bmm2_`) — one per consumer — which is what
makes it a three-stage pipeline rather than a deeper queue.

The synchronisation cost the off switch trades against, `:234`:
`**同步指令开销**：HardEvent `SetFlag/WaitFlag` 有轻微开销，仅在必要路径使用。过度同步会抵消流水
收益。` `轻微` is the only quantification anywhere in the file.

Nothing in this section is measured. The `50%` saving for `TQueBind` is arithmetic (one buffer
instead of two); every other figure in the file is an unscoped range.

## 4 · Procedure
Proposed, runnable later on a named 950 board. Never run in this phase.

Arm 1 — the off switch, tested where it is claimed to apply. One elementwise operator, sized so the
whole case fits UB with room for a single buffer, built with `useDb ∈ {true, false}`. Record kernel
time, total UB requested, and the per-tile `SetFlag`/`WaitFlag` count (from disassembly, since
upstream's only cost statement is about instruction overhead). Upstream predicts `useDb = false`
wins. This is the arm the OVERTURN is written against.

Arm 2 — the boundary. Grow the case size until it no longer fits, in steps, and record the crossing
point at which `useDb = true` overtakes. That crossing is the number `maxRow > rowPerHeadCore` is
trying to express, and locating it is worth more than confirming the rule.

Arm 3 — the compute-bound regime. Same two builds on a transcendental-heavy operator at the same
shape (so the data movement is identical and only the arithmetic intensity changes). Upstream
predicts no difference. A difference here would mean double buffering helps for a reason other than
hiding memory latency.

Arm 4 — the ladder, at least one rung beyond 2. A CV-fused operator built with `num = 2` and
`num = 3`, recording Cube and Vector segment overlap from the trace. This is the only arm that can
show the ladder is a ladder rather than a list.

Variance floor first: one build, 30 in-process runs, 5 fresh-process runs, IQR over median, beside
every comparison. Device selection: `npu-smi info -l`;
`npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing; bind only on three idle samples;
re-sample after; discard if the die moved. Refuses to assume: that a free die stays free; that a die
may be substituted; that UB capacity is a literal — it is queried and echoed, and Arm 2's crossing
point is meaningless without it (`950:0207`, `950:0209`); that `useDb` reached the kernel — the
tiling key and the kernel's buffer count are both echoed, because a host flag that does not change
the kernel is the null result this arm would otherwise mis-read.

## 5 · Checker — acceptance declared before the run
Verdict `off_wins` = (db-on median − db-off median) / db-on median at Arm 1's fitting size, with the
floor. Declared before the run: the entry is **supported** iff `off_wins` is positive and outside
the floor. The OVERTURN fires iff `off_wins` is negative and outside the floor — double buffering
would then help on a case that fits, and the stated ground (`减少同步开销`) would be wrong.
`off_wins` inside the floor supports the weaker reading only: the off switch costs nothing, which is
not what upstream claims, and the entry is corrected in place to say so.

Verdict `crossover_bytes` = Arm 2's crossing point, in bytes, reported with the queried UB capacity
beside it. No pass condition; it is the deliverable.

Verdict `compute_null` = true iff Arm 3's difference is inside the floor.
Verdict `triple_overlap` = true iff Arm 4's `num = 3` build shows Cube and Vector segments
overlapping where `num = 2` does not.

The exit code is not the verdict. Three guards. First, all builds are compared elementwise against a
CPU reference — `TQueBind`-style sharing and reduced buffer counts are exactly where a
read-before-write hazard appears, and a hazard produces a faster wrong answer. Second — the input
that makes this checker go red — Arm 1 is repeated at a case size that clearly does **not** fit UB,
where `off_wins` **must** go negative and outside the floor. If db-off wins at both sizes, the
experiment is not sensitive to the regime it claims to be discriminating, and every verdict is void.
That planted positive is required because the entry's headline verdict is a preference for the
*absence* of an optimisation, and such a verdict is trivially obtainable from a badly-scaled
experiment. Third, no verdict without the floor, the echoed UB capacity, and the echoed buffer count
from the kernel.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. Upstream gives no timing for
either arm of the adaptive decision, no crossing point, and no figure for the synchronisation
overhead beyond the word `轻微`.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The entry establishes that an off switch is *stated*, not that it
is right: upstream supplies no measurement on either side of it, and its own decision tree places
the off arm where control flow rarely reaches (`§3`), so even the rule's operational status inside
the source is uncertain. `maxRow` and `rowPerHeadCore` are undefined in the file, so the condition
cannot be lifted as written. The synchronisation cost the trade rests on is quantified only as
`轻微`. The buffer-count ladder is a table of five strategies with no measurement behind any of
them and no statement of what makes 3 better than 2 on a mixed core beyond the stage count. The
`TQueBind` 50 % saving is arithmetic, not a measurement, and its correctness precondition (true
in-place semantics) is stated only as `读-改-写 in-place`. The whole file carries no 950 constant
(`0319`), so its capacity-dependent advice cannot be evaluated in this book without the runtime
query `950:0209` §4 owes. BOARD is `family-claimed(unverified)`. Nothing transfers to the other book
(RULES.md Art. 1).
