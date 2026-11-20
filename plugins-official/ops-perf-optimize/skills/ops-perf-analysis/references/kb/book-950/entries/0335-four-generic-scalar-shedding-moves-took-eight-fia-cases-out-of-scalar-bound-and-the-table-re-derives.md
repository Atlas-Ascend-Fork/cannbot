```
ID:        0335-four-generic-scalar-shedding-moves-took-eight-fia-cases-out-of-scalar-bound-and-the-table-re-derives
LABEL:     knowledge
LEVEL:     L1 (core & pipe assignment)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/flash_attention/scalar_general_techniques_design.md:9-13
           — "| Scalar 耗时 | 8 组 case 算术平均下降 33.22% | | 端到端耗时 | 8 组 case 算术平均提升
           14.74% | | Bound 状态 | 8 组 case 从 SCALAR_BOUND 跳出 |"
SOURCE:    same file:19-24 — "| 主循环 | 热路径函数体大，I-Cache miss 导致 PC 停滞 | I-Cache 预取 |
           | Init | `TPipe::InitBuffer` 通用框架带来条件判断和队列操作 | 静态创建 `LocalTensor` | |
           Init | `ConstParam` 作为类成员访问，编译器难以寄存器化 | 类成员局部化 | | Kernel 入口 |
           TilingData 字段多，整块拷贝到栈形成头开销 | TilingData 指针直读 |" ; :88-99 — the eight-case
           table quoted in §3 ; :99 — "若某 case Scalar 明显下降但端到端收益很小，说明瓶颈已转移到
           CUBE / MTE2，应停止在 Scalar 方向继续叠加。"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured FIA case on a named 950 board where applying all four techniques leaves Scalar
           time unchanged outside the run spread — the four locations would then not be where the
           scalar cost is, at least for that shape.
```

# 0335 · Four generic scalar-shedding moves took eight FIA cases out of SCALAR_BOUND, and the table re-derives

## 1 · Claim
Upstream asserts four scalar-cost reductions that share a property: none changes tiling fields and
none changes the main data flow, so upstream classifies them as a low-risk prelude applicable to
every scalar sub-class (`0334`). The four target four locations. In the main loop, a large hot-path
function body causes instruction-cache misses and PC stalls, addressed by an explicit I-cache
prefetch inserted after the last MTE wait outside the loop and before the first scalar computation.
In `Init`, `TPipe::InitBuffer`'s general framework costs conditionals and queue operations, addressed
by constructing `LocalTensor` statically from a compile-time position and offset. Also in `Init`,
`ConstParam` accessed as a class member resists register allocation, addressed by making it a local
where its use is confined to one inlined chain. At kernel entry, copying a large TilingData struct to
the stack is header overhead, addressed by keeping a `__gm__` pointer and reading fields on demand.
Upstream asserts a measurement over eight FIA cases: Scalar time down 33.22 % on arithmetic average,
end-to-end down 14.74 %, and all eight leaving `SCALAR_BOUND`. Not established here.

Upstream asserts a stopping rule that travels with the result: if a case's Scalar time falls
markedly while end-to-end barely moves, the bottleneck has moved to CUBE or MTE2 and no further
scalar work should be stacked.

## 2 · The wrong branch this removes
An agent diagnosing `SCALAR_BOUND` goes looking for scalar *arithmetic* — divisions, modulos,
address computations in the inner loop. Three of these four techniques are not about arithmetic at
all. Two are in `Init`, which runs once and looks irrelevant to a hot loop; one is at kernel entry,
before any loop exists; one is about *instruction* fetch rather than data. So the whole set is
invisible to the search an agent would naturally run, and upstream reports it as the intervention
with the largest effect in this family — against `0336`'s −1.51 % for the sub-class-specific work.

The second wrong branch is why the stopping rule matters. Case 8 in upstream's own table shows
44.36 % Scalar reduction for 3.55 % end-to-end. An agent reading the Scalar column would call that a
success and continue; upstream reads it as the signal to stop, because the remaining time is no
longer scalar. Publishing the Scalar column without the end-to-end column would license exactly the
wrong conclusion, and upstream publishes both — which is the reason this entry carries the whole
table rather than the headline.

The third: `静态创建 LocalTensor` replaces the framework's bookkeeping with hand-computed offsets,
and upstream attaches the obligation — `Buffer 偏移必须按 L1 布局精确计算`, and in the applicability
table `必须补充 buffer 不重叠检查`. The technique moves an invariant from the framework into the
author's head, which is a real trade and not a free win.

## 3 · Ground / Source
The four locations, `scalar_general_techniques_design.md:17-24`:

```
FIA 通用 Scalar 开销主要来自 4 个位置：

| 阶段 | 问题场景 | 优化手段 |
| 主循环 | 热路径函数体大，I-Cache miss 导致 PC 停滞 | I-Cache 预取 |
| Init | `TPipe::InitBuffer` 通用框架带来条件判断和队列操作 | 静态创建 `LocalTensor` |
| Init | `ConstParam` 作为类成员访问，编译器难以寄存器化 | 类成员局部化 |
| Kernel 入口 | TilingData 字段多，整块拷贝到栈形成头开销 | TilingData 指针直读 |
```

Their constraints, `:28-33`, each one a real limit rather than a caveat:

```
| I-Cache 预取 | 在循环外最后一次 MTE 等待之后、第一次 Scalar 计算之前插入预取 | 预取范围只覆盖
  热循环主体，避免预取本身增压 |
| 静态 `LocalTensor` | 用 `LocalTensor<T>(TPosition, offset, size)` 替代动态 `InitBuffer` |
  Buffer 偏移必须按 L1 布局精确计算 |
| `ConstParam` 局部化 | 将只在 `Init()` 或单个内联链路使用的 `ConstParam` 从成员改为局部变量 |
  跨非内联函数共享的参数不能局部化 |
| TilingData 直读 | 保存 `__gm__ FATilingData*` 指针，避免整块 tiling struct 栈拷贝 | 热路径反复
  使用字段仍需缓存到局部变量或少量成员 |
```

The last constraint is a genuine tension with the technique itself: reading fields through a GM
pointer removes the stack copy and adds a GM read per access, so hot fields must still be cached —
which is the same ALU-versus-load trade `0334` and `0336` record, appearing here in miniature.

The measured table, `:88-97`:

```
| case | 总耗时优化前 | 总耗时优化后 | Scalar 优化比例 | 端到端提升 |
| 1 | 24408 | 19890 | 32.92% | 18.51% |
| 2 | 32400 | 27432 | 24.67% | 15.33% |
| 3 | 25182 | 20250 | 28.44% | 19.59% |
| 4 | 24210 | 20268 | 21.92% | 16.28% |
| 5 | 26208 | 22212 | 32.52% | 15.25% |
| 6 | 24354 | 21240 | 30.43% | 12.79% |
| 7 | 32166 | 26820 | 50.53% | 16.62% |
| 8 | 52704 | 50832 | 44.36% | 3.55% |
```

Re-derived, every figure. End-to-end column against the two cycle columns: case 1,
`(24408 − 19890)/24408 = 18.51 %` ✓; case 8, `(52704 − 50832)/52704 = 3.553 %` ✓; the other six
check likewise. Headline averages: the Scalar column sums to `265.79`, `/8 = 33.224 %`, stated as
33.22 % ✓; the end-to-end column sums to `117.92`, `/8 = 14.74 %` ✓ exactly.

That the table's own averages re-derive from its own rows is worth stating plainly, because in this
shelf it is not the norm — `0310`, `0312` and `950:0114` all record cells that contradict their own
sources. Here the arithmetic is sound throughout, which raises confidence in the transcription and
in nothing else: the cycles themselves are still upstream's, on an unnamed part, with no repeat
count, no variance and no tool named.

The stopping rule, `:99`:

```
若某 case Scalar 明显下降但端到端收益很小，说明瓶颈已转移到 CUBE / MTE2，应停止在 Scalar 方向
继续叠加。
```

Case 8 is that rule's own instance, sitting in the table above it.

One wording note: the guide's summary line calls the end-to-end result `端到端耗时平均提升 14.74%`
— "提升" (increase) applied to 耗时 (time) — while the table shows time falling. The direction is
unambiguous from the numbers; the summary sentence is loose. Recorded, not adjudicated.

Measured/inferred split at sentence level: **measured** — the eight before/after cycle pairs and the
bound-state change. **not measured** — that each of the four techniques contributes; the table is
for all four applied together, and no per-technique attribution exists anywhere in the file. That is
the same confound `0302` records: a multi-change comparison carries no attribution to any one change.

## 4 · Procedure
Proposed, runnable later on a named 950 board. Never run in this phase.

Arm 1 — reproduce the aggregate. Baseline and all-four-applied builds over eight FIA cases, recording
total cycles, Scalar cycles, and the bound classification from the same profiling step that produced
upstream's percentages (`950:0001`). Compare against the table.

Arm 2 — the attribution the table lacks, and the reason this entry has a §4 at all. Five builds:
baseline, then each technique added alone. Report each technique's own Scalar and end-to-end delta.
A 33 % aggregate over four simultaneous changes tells a consuming agent nothing about which to apply
when only one is available, and upstream's own framing ("four techniques") invites treating them as
a set.

Arm 3 — the I-cache claim specifically, since it is the only one with a hardware story. Record
`icache_miss` before and after the prefetch alone, alongside the PC-stall signature upstream names
(`PC 曲线出现主循环水平段`). A prefetch that lowers Scalar time without lowering I-cache misses is
working for some other reason.

Arm 4 — the stopping rule, tested rather than assumed. On case 8's shape, continue applying scalar
work (S1–S5, `0334`) past the point upstream says to stop, and record whether end-to-end improves.
Upstream predicts it does not. This arm can only bite in upstream's favour or against it, and either
outcome is worth having.

Arm 5 — the static-`LocalTensor` obligation. Build one variant with a deliberately overlapping
hand-computed offset and confirm the failure is detectable. See §5.

Variance floor first: one build, 30 in-process runs, 5 fresh-process runs, IQR over median — case 8's
3.55 % is the smallest effect in the table and sets the sensitivity requirement. `0327`'s same-path
sibling check applied to every table. Device selection: `npu-smi info -l`;
`npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing; bind only on three idle samples;
re-sample after; discard the case if the die moved. Refuses to assume: that a free die stays free;
that a die may be substituted; that the eight cases are known — they are not identified in the source
by shape, dtype or head configuration, so Arm 1 reproduces the *method* and cannot reproduce the
*cases*, and that limitation is reported rather than papered over.

## 5 · Checker — acceptance declared before the run
Verdict `scalar_mean` and `e2e_mean` = the arithmetic means over Arm 1's eight cases, against
33.22 % and 14.74 %. No pass condition on matching upstream's exact figures — the cases differ — but
a sign disagreement (Scalar not falling) fires the OVERTURN.

Verdict `per_technique[t]` for each of the four, from Arm 2, with the floor. Declared before the
run: a technique whose own delta is inside the floor is reported as `unattributed`, and the set's
aggregate is then explicitly noted as carried by the remainder. This is the verdict the source
cannot supply and it is the entry's main deliverable.

Verdict `icache_delta` from Arm 3.
Verdict `stopping_rule_holds` = true iff Arm 4's further scalar work leaves end-to-end inside the
floor on case 8's shape.

The exit code is not the verdict. Three guards. First, every build is compared elementwise against a
reference: `静态创建 LocalTensor` replaces framework-managed offsets with hand arithmetic, and an
overlapping buffer produces wrong output with no allocation error. Second — the input that makes
this checker go red — Arm 5's deliberately overlapping offset is the planted positive: the
correctness comparison **must** fail on it. If it passes, the comparison is not covering the buffers
the technique touches, and every green in the run is void for this class of defect. That fixture is
mandatory precisely because the technique's whole cost is an invariant moved out of the framework.
Third, no `per_technique` figure is reported without its floor, and the aggregate is never presented
without the per-technique breakdown once Arm 2 exists — publishing the 33 % alone is the confound
this procedure was built to remove.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The eight cycle pairs, the
33.22 % and the 14.74 % are upstream's readouts on an unnamed part; this book has built nothing and
profiled nothing. The re-derivation in §3 checks upstream's arithmetic against itself on paper and
is not a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The eight cases are identified by index only — no shape, no dtype,
no head configuration, no sequence length — so the result is not reproducible as stated and cannot be
transferred to a named case. The measurement carries no board, no tool, no repeat count, no variance
and no CANN pin; a 3.55 % end-to-end figure without a stated spread cannot be evaluated. **No
per-technique attribution exists**: all four were applied together, so nothing here establishes that
any single one contributes, and an agent able to apply only one has no basis for choosing. The
I-cache prefetch's mechanism (PC stalls from a large hot-path body) is asserted with no counter
reading. `ConstParam`, `FATilingData` and the `LocalTensor(TPosition, offset, size)` constructor are
named without definitions. The techniques are validated on FIA only; the guide extends them to other
FA variants as `参照通用方法论迁移`, which is a plan, not evidence. The summary line's `耗时平均提升`
wording contradicts its own table's direction and is recorded, not adjudicated. BOARD is
`family-claimed(unverified)`. Nothing transfers to the other book (RULES.md Art. 1).
