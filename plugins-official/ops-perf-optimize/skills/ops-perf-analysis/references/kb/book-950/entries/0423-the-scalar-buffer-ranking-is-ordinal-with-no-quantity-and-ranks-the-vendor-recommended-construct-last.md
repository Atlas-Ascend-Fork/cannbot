```
ID:        0423-the-scalar-buffer-ranking-is-ordinal-with-no-quantity-and-ranks-the-vendor-recommended-construct-last
LABEL:     boundary
LEVEL:     L4 (synchronisation)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/scalar/
           buffer_management_conversion_guide.md:126 — "从性能角度，有三种管理方式，性能从高到低排列。
           每种方式都包含**地址分配**和**同步管理**两个维度。" ; :128,:165,:194 —
           "### 方式 1：静态构造 tensor + 手动管理同步（性能最佳）" ·
           "### 方式 2：TPipe + TBuf 管理地址 + 手动管理同步（性能次之）" ·
           "### 方式 3：TPipe + TQue 管理地址+同步（性能最低，但编码最简单）"
SOURCE:    same file :215 — "- 优点：代码简洁，AscendC 官方推荐用法" ; :221 —
           "| 低频（外循环，如 mAL1Iter、batchIter） | 方式 3（TQue） | scalar 开销可忽略，代码最简洁 |" ;
           :366 — "**方式 2 使用固定 event ID 时的风险**：… TQue 的 `AllocEventID` 会跳过已被占用的位，
           但它不知道手动 `SetFlag` 使用的 event ID——如果手动用的 ID 没有通过 `AllocEventID` 占用位图，
           TQue 可能分配到同一个 ID，导致 flag 错配。"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a matched pair on a named 950 board — one kernel, one compile-time switch selecting manual
           `SetFlag`/`WaitFlag` or `TQue` for the same buffer in the same inner loop — in which the
           `TQue` form is not slower by more than the variance floor. The ranking's third place would
           then not be a performance fact at any loop frequency, and the family's ordering would be a
           coding-style preference stated in performance language.
```

# 0423 · The scalar buffer ranking is ordinal with no quantity, and ranks the vendor-recommended construct last

## 1 · Claim
Upstream asserts three ways to manage an on-chip buffer's address allocation and synchronisation,
explicitly ordered by performance from highest to lowest: statically constructed tensors with manual
`SetFlag`/`WaitFlag` (best), `TPipe` + `TBuf` for addresses with manual flags (second), and `TPipe` +
`TQue` for both (lowest, but simplest to write). Upstream asserts the mechanism for the third place —
per-iteration `TQue` state-machine work, buffer rotation and event-ID allocation and release — and
asserts that this cost accumulates significantly in a high-frequency inner loop and is hidden by
compute time in a low-frequency outer one. Upstream states in the same section that the third way is
`AscendC 官方推荐用法` — the vendor's recommended usage — and its own selection table then recommends
the third way for outer loops and the first or second for inner loops. Upstream attaches **no
quantity** to any of the three: no time, no ratio, no instruction count, no percentage. Not established
here.

## 2 · The wrong branch this removes
An agent reading `性能最佳` / `性能次之` / `性能最低` will read a ranking and apply it globally,
replacing `TQue` with hand-managed flags everywhere. That is the wrong branch for two reasons the file
itself supplies. First, the ranking is conditional and the condition is loop frequency, not correctness
or code size: `:221` recommends the *last-ranked* option for outer loops, where `scalar 开销可忽略`.
Second, and this is the part that bites, the second way has a disclosed failure mode that the third way
does not: mixing manual fixed event IDs with any `TQue` in the same kernel can produce a duplicate
event ID and a mis-paired flag, because `TQue`'s allocator does not know which IDs the manual code took.
So the middle rung of a performance ladder carries a correctness hazard the bottom rung does not, and a
ranking presented as one-dimensional hides that entirely.

The second wrong branch is the opposite: treating `官方推荐用法` as settling the matter and never
considering manual flags. The family's claim is specific and plausible — `TQue`'s `AllocTensor` /
`EnQue` / `DeQue` / `FreeTensor` each expand to state-machine work on the scalar pipeline, and `0422`
records that this family's whole diagnosis is that the scalar pipeline's instruction supply is what
stalls the others. A per-iteration scalar cost inside a Cube-feeding inner loop is exactly the shape
that diagnosis predicts. The honest position is that the ranking names a real mechanism and quantifies
nothing, so **the ordering is a hypothesis with a stated variable (loop frequency) and no measured
crossover** — and the crossover is the only thing an agent actually needs.

## 3 · Ground / Source
The ranking, `reference/scalar/buffer_management_conversion_guide.md:126`:

```
从性能角度，有三种管理方式，性能从高到低排列。每种方式都包含**地址分配**和**同步管理**两个维度。
```

and its three headings, `:128`, `:165`, `:194`:

```
### 方式 1：静态构造 tensor + 手动管理同步（性能最佳）
```
```
### 方式 2：TPipe + TBuf 管理地址 + 手动管理同步（性能次之）
```
```
### 方式 3：TPipe + TQue 管理地址+同步（性能最低，但编码最简单）
```

The stated mechanism for each. Way 1, `:159-163`:

```
- 无 TPipe 对象初始化耗时
- 无 TQue 的 AllocTensor/EnQue/DeQue/FreeTensor 引入的 scalar 开销
- 开发者完全控制 flag 时序
- PingPong 通过偏移量和 event ID 交替实现
- 缺点：编码复杂度高，需手动计算地址布局和 event ID
```

Way 2, `:189-192`, differs from way 1 in exactly one respect — a one-off `TPipe` construction cost —
and keeps the same synchronisation (`同步逻辑与方式 1 完全一致，无 TQue 的 scalar 开销`). Way 3,
`:212-215`:

```
- 对比方式 2：每次迭代额外有 TQue 状态机操作（buffer 轮转、event ID 分配/释放）
- 在高频内循环（如 kIt 循环）中，scalar 开销累积显著
- 在低频外循环中，开销被计算时间掩盖，影响可忽略
- 优点：代码简洁，AscendC 官方推荐用法
```

Four bullets: two costs, one condition under which the cost vanishes, and the vendor's recommendation.
The last two do not sit comfortably under a heading reading `性能最低`.

The selection table that makes the ranking conditional, `:219-223`:

```
| 低频（外循环，如 mAL1Iter、batchIter） | 方式 3（TQue） | scalar 开销可忽略，代码最简洁 |
| 高频（内循环，如 kIt、nL0It） | 方式 1 或 2 | 避免 TQue scalar 开销阻塞 Cube 流水线 |
| 需要与其他 TQue 共享 TPipe 地址空间 | 方式 2 | TPipe 统一地址分配，手动 flag 保持性能 |
```

`避免 TQue scalar 开销阻塞 Cube 流水线` names the consequence precisely and is the sentence that ties
this file to the family's root-cause claim (`0422`): the cost is not the buffer work itself but the
scalar pipeline failing to keep the Cube pipeline fed. Neither `高频` nor `低频` is given a number, so
the table's own discriminating variable is unquantified.

The hazard the ranking hides, `:366`:

```
**方式 2 使用固定 event ID 时的风险**：方式 2 有 TPipe，如果同时混用了 TQue，TQue 内部会通过 `AllocEventID` 动态分配同一 `HardEvent` 类型的 event ID。TQue 的 `AllocEventID` 会跳过已被占用的位，但它不知道手动 `SetFlag` 使用的 event ID——如果手动用的 ID 没有通过 `AllocEventID` 占用位图，TQue 可能分配到同一个 ID，导致 flag 错配。
```

with the fix at `:368` — use `TPipe`'s dynamic allocation for the manual buffers too, or reserve the
manual IDs through `AllocEventID` at init so the bitmap knows about them. The ID pool is stated as
`QUE_MAX_EVENT`, `通常为 8` (`:400`), and IDs are independent across `HardEvent` types but mutually
exclusive within one (`:364`). This book records the same pooling hazard from a different source at
`0262` — event IDs pooled per `HardEvent` type with eight slots, and `FetchEventID` able to return the
same ID twice — so the two sources describe one mechanism, and neither corroborates the other (RULES.md
Art. 3, one repo). What this file adds is the *interaction*: the hazard arises specifically when the
second-ranked way is mixed with the third.

One rule in the file is unconditional and sits outside the ranking entirely, `:451`:

```
在 `__mix__` 混合核模式下，AIC 和 AIV 各自独立运行，共享 L1 上的某些 buffer（典型场景：AIV 将 weight 变换后写入 BL1，AIC 从 BL1 读取做 Mmad）。这种跨核的生产者-消费者同步**必须使用 `CrossCoreSetFlag` / `CrossCoreWaitFlag`**，无论 buffer 地址用静态构造还是 TBuf 管理，也无论同步用 TQue 还是手动 flag——跨核同步是独立于上述所有模式的基础机制。
```

That is the file's clearest sentence and the one an agent most needs: the three ways are a choice about
*intra*-core synchronisation, and cross-core synchronisation is a separate mechanism none of them
replaces. `0359` carries the adjacent distinction from another source (explicit event flags belong to
overlap designs, cross-core flags to cross-core dependencies).

Registered as `C-950td-029`: a performance ranking whose bottom rung is the vendor's recommended usage
and whose own selection table recommends that rung for one of the three listed regimes, with no
quantity attached to any rung.

Two internal inconsistencies in the supporting tables, recorded because they bear on whether the file's
event reasoning can be relied on. `:36` assigns `L0C→UB` to the `FIX` pipeline and `:37` assigns the
same transfer to `MTE3`, in adjacent rows of one table. And the forward/reverse event table lists
`MTE2_V → V_MTE2` at `:98` and `V_MTE2 → MTE2_V` at `:101`, each presented as the other's forward, with
no statement of which direction is canonical. Registered as `C-950td-030`.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase. The ranking's
variable is loop frequency, so the procedure sweeps loop frequency and finds the crossover the family
does not state.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and discard the case
if the die moved. Variance floor first: one build, 30 in-process runs, 5 fresh-process runs.

**Arm 1 — one kernel, three buffer strategies, a compile-time switch.** Write one Cube-feeding kernel
whose inner-loop buffer management is selected by a template parameter: `WAY1` (static `LocalTensor`
construction at computed offsets, fixed event IDs), `WAY2` (`TPipe` + `TBuf`, same manual flags), `WAY3`
(`TPipe` + `TQue<..., 2>`). Everything else — tiling, arithmetic, data — identical, from one source
file, one compiler pin, three distinct md5s echoed. Sweep the inner-loop trip count over
`{1, 2, 4, 8, 16, 64, 256, 1024}` at fixed total work, so that iteration count rises as per-iteration
work falls. Record `aiv_time`, the scalar pipeline share and the scalar Load/Store share (the metric
`0422` records this family as nominating), ≥10 iterations, first 5 dropped. Elementwise comparison
against a CPU reference on all three.

**Arm 2 — the crossover.** From arm 1, report the trip count at which `WAY3` first becomes slower than
`WAY1` by more than the floor. That number is the family's missing quantity and is the deliverable of
this entry.

**Arm 3 — the `TPipe` construction cost, way 1 versus way 2.** Upstream says these differ only by a
one-off `TPipe` initialisation (`:189`). Measure it directly: time a kernel that does nothing but
construct `TPipe` and `InitBuffer` the same buffers, against one that constructs nothing. If the
difference is below the floor, ways 1 and 2 are indistinguishable and the three-way ranking is really a
two-way one — which would simplify the advice considerably.

**Arm 4 — the event-ID hazard, which is a correctness arm and must not be scored on time.** Build a
kernel mixing way 2 with a `TQue` on the **same** `HardEvent` type, with the manual IDs *not* reserved
through `AllocEventID`, and run it 200 times in fresh processes comparing elementwise against a CPU
reference. Then build the same with the manual IDs reserved per `:368` and repeat. Upstream predicts a
flag mis-pairing in the first and none in the second; `0262` records that a same-ID collision is
possible in this pooling scheme, so the failure may be intermittent and a single run proves nothing.

**Arm 5 — the cross-core rule.** Build the `__mix__` producer-consumer case (AIV writes `BL1`, AIC
reads it for `Mmad`) with `CrossCoreSetFlag`/`CrossCoreWaitFlag` and, as a poison arm, with intra-core
flags only. Upstream says the second cannot work at all; confirm it fails, and record *how* — silently
wrong or hung — because those have very different debugging costs.

Refuses to assume: that a free die stays free; that a die may be substituted; that the three ways were
built from one source (three md5s from one file, echoed); that a fast run is correct (elementwise
comparison on every arm); that the event hazard is deterministic (arm 4's run count is declared in
advance and reported with the result); that this family's unlabelled capacity constants apply to this
board (none is used — `0422` §7 records why).

## 5 · Checker — acceptance declared before the run
Verdict `way_order(trip)` = the ordering of the three by median `aiv_time` at that trip count, with the
floor. Declared before the run: the ranking is **supported** iff `WAY1 ≤ WAY2 < WAY3` outside the floor
at the highest trip count, **and** the three are indistinguishable within the floor at the lowest — the
ordering holds where upstream says it holds and vanishes where upstream says it vanishes. The OVERTURN
fires iff `WAY3` is not slower than `WAY1` beyond the floor at **any** trip count: the ranking would
then not be a performance fact and would be a style preference in performance language.

Verdict `crossover_trip` from arm 2, an integer or `none`.

Verdict `tpipe_cost` from arm 3, in µs with its floor; `below_floor` collapses ways 1 and 2.

Verdict `id_collision(reserved)` from arm 4 = failures out of 200 fresh-process runs, for each of the
two builds. Reported as counts, never as "passes" — a 200-run null bounds the rate and does not
eliminate it.

Verdict `crosscore_poison` from arm 5 ∈ {`hangs`, `wrong_silently`, `passes`}. `passes` would overturn
`:451`'s `必须`.

The exit code is not the verdict. Arms 1–3 always complete; arm 4's failure mode is intermittent wrong
data with a zero exit; arm 5's poison arm may hang, which is a *result* and must be caught by timeout
rather than read as an infrastructure failure. Three guards. First, every arm compares elementwise
against a CPU reference and an arm whose comparison did not execute is `untestable` — arm 4 in
particular has no meaning without it, since flag mis-pairing produces plausible numbers. Second,
**the input that makes this checker go red**: arm 1 includes a trip count of 1, where a per-iteration
cost cannot accumulate and all three ways **must** agree within the floor. If they differ at trip
count 1, the three builds differ in something other than buffer management — a different tiling, a
different unroll — and every ordering in the sweep is attributing a build difference to a construct
choice, which is the failure species this book records as carrying no attribution at all. Third, every
point reports its floor, its md5, its echoed way, and its scalar-pipe share; the ranking's stated
mechanism is scalar overhead, and a timing that moves without the scalar share moving has not
demonstrated that mechanism even if it confirms the ordering.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement, and upstream supplies none: the
ranking is stated with the words `性能最佳` / `性能次之` / `性能最低` / `累积显著` / `可忽略` and no
number of any kind. The family's four files contain no timing and no ratio at all (`0422` §6). The
`QUE_MAX_EVENT ≈ 8` and `G_CV_SYNC_STRIDE ≈ 16` figures quoted in §3 are upstream's, both hedged with
`通常`, neither carrying an architecture; they are recorded, not carried.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The entry does not establish the ordering, the mechanism, or that any
way is faster than any other — it records an ordinal claim with no quantity, its stated condition
(loop frequency, itself unquantified), and the fact that its bottom rung is the vendor's recommended
usage. It does not establish the crossover trip count, which is the number an agent actually needs and
which upstream never gives. It does not establish that `TQue`'s per-iteration work reaches the scalar
pipeline, only that upstream says so; `0422` records that the family's whole scalar diagnosis is itself
unmeasured. It does not establish the event-ID hazard or `QUE_MAX_EVENT = 8`; `0262` carries the
pooling mechanism from another file of the same repository, which under RULES.md Art. 3 is one origin and
does not corroborate. It does not resolve the two table inconsistencies (`C-950td-030`) and does not
rely on either table's event directions. It does not establish that `CrossCoreSetFlag`/`CrossCoreWaitFlag`
are mandatory, only that upstream states it unconditionally. It carries no capacity constant from this
family — the file's capacity table is headed `容量(典型)`, names no architecture, and its UB row
disagrees with `0209` — and it establishes nothing about `__mix__`, `BL1`, or AIC/AIV core assignment
beyond quoting the scenario. The family carries no architecture marking anywhere in 1 192 lines, so
BOARD is `family-claimed(unverified)` on the weakest grounds and §4 names 950PR/950DT only as where our
run would happen. Nothing here is established for any 910-family board.
