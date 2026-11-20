```
ID:        0377-the-simt-ub-reservation-accessor-is-spelled-two-ways-nine-lines-apart-and-the-snippet-reserves-the-dcache-ceiling
LABEL:     trap
LEVEL:     L2 (memory hierarchy & residency)
STRATUM:   harvested — one upstream origin (ops/ascendc-simt-programming-best-practices). This is the
           THIRD upstream location of the 256 KB / 128 KB reservation snippet already recorded as
           `C-950arch-007` and carried by `950:0239`; the snippet itself is not re-entered here.
           Nothing was compiled.
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-simt-programming-best-practices/references/data-transfer.md:16-30 — "## 复杂场景：
           使用 UB 中转 / 需要在 SIMT 内部使用 UB 时： / 1. **tiling 侧**：设置 `SetLocalMemory` 分配动态
           UB / 2. **kernel 侧**：使用 `TBuf<QuePosition::VECCALC>` 声明 buffer / 3. **VF 调用**：将
           `__ubuf__` 指针传入 VF / ### Tiling 侧 / ```cpp / constexpr uint64_t DCACHE_SIZE = 128 * 1024;
           / uint64_t ubsize = 256 * 1024; / context->SetLocalMemorySize(ubsize - DCACHE_SIZE); / ```"
SOURCE:    ops/ascendc-simt-programming-best-practices/references/intra-core-shared.md:41-45 — "## 注意事项
           / - 同地址并发写入需使用原子操作（`asc_atomic_add` 等） / - 共享内存大小受 UB 可用空间限制 /
           - buffer 大小需在 tiling 侧预留（通过 `SetLocalMemorySize`）" — the second spelling again,
           in a sibling file, with no mention of `SetLocalMemory`.
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a CANN API in which BOTH `SetLocalMemory` and `SetLocalMemorySize` exist on the tiling
           context with different meanings — the two spellings would then be two calls rather than one
           name written two ways, and the prose step 1 would be describing a different operation from
           its own snippet.
```

# 0377 · The SIMT UB reservation accessor is spelled two ways nine lines apart, and the snippet reserves the DCache ceiling

## 1 · Claim
Upstream asserts a three-step recipe for using UB inside a SIMT kernel: reserve dynamic UB on the tiling
side, declare a `TBuf<QuePosition::VECCALC>` on the kernel side, and pass the resulting `__ubuf__` pointer
into the VF. Upstream asserts the tiling-side step in prose as `SetLocalMemory` and, nine lines later in
its own code block, as `context->SetLocalMemorySize(...)`. Upstream asserts the same reservation
requirement in a sibling file using only the second spelling. Not established here: nothing was compiled,
and no source in scope defines either name.

This entry claims the **spelling mismatch and its consequence**. The snippet's numeric content — a 256 KB
UB total and a 128 KB DCache reservation — is already recorded as `C-950arch-007` and carried by
`950:0239`; this file is its **third** upstream location and is added to that contradiction row rather
than re-entered as a claim.

## 2 · The wrong branch this removes
Two names for one operation, nine lines apart, in the file that teaches the operation.

The prose is what an agent reads to learn the step; the code block is what it copies. So the mismatch is
survivable when the agent copies, and not when it works from the prose — which is exactly the case for a
generating harness that has been told "call `SetLocalMemory` on the tiling context" and has no snippet in
front of it. The failure is an unresolved name at host compile time, which is loud, so the direct cost is
one cycle.

The **indirect** cost is worse and is why this is a trap rather than a typo. An agent that meets
`no member named 'SetLocalMemory'` has three hypotheses: the API changed, the context type is wrong, or
the include is missing. All three are wrong. And the successful repair — find the real name — teaches the
agent that this document's prose is unreliable, which is a correct lesson drawn from one instance and
applied to the whole file, including the parts that are right. The neighbouring statements in the same
document (the `TBuf<QuePosition::VECCALC>` requirement, the `__ubuf__` pointer passing, the choice table
at `:45-51`) are not obviously more reliable than the sentence that just failed.

The **third** branch is the one that produces silently wrong behaviour rather than a compile error, and it
is why the two spellings are not interchangeable in meaning even if only one exists. `SetLocalMemory` and
`SetLocalMemorySize` differ in what their argument plausibly *is*: a memory (a region, perhaps a
base and extent) versus a size. An agent that assumes the former and passes a total rather than a residual
has reserved the wrong quantity, and the arithmetic in the very snippet below it — `ubsize - DCACHE_SIZE`
— shows the argument is a residual after a reservation, not a total. Get that backwards and the kernel
asks for the whole UB, leaving nothing for the DCache the same subtree says is mandatory (0237).

The **numeric content is not this entry's claim and must not be inherited from it.** `950:0239` records
that the recommended tiling snippet reserves 128 KB for DCache where the rule states a 32 KB minimum, and
`C-950arch-007` records the arithmetic. What this file adds is that the same snippet, with the same two
literals, appears in a *third* upstream location — a SIMT programming guide that is not
`npu-arch/references/simt-arch-guide.md` and not `ascendc-simt-tiling-design/references/guide.md`. Three
copies of one snippet in three skills is the signature of a copied constant rather than a derived one, and
it is the reason the repair is a generator rather than three edits: fix the instances and the defect
returns with the next skill.

Note also what this third copy **omits** that the other two carry: the surrounding rule. In
`simt-arch-guide.md` the snippet sits nine lines after "需为 DCache 预留 ≥32KB" and the 216 KB arithmetic;
here it appears with no rule at all, no mention of a 32 KB minimum, and no explanation of either literal.
So the copy that reaches a SIMT kernel author through the programming guide is the one with the least
context, and it is the one presented as the recipe.

## 3 · Ground / Source
`data-transfer.md:16-30`, the recipe and its snippet:

> ## 复杂场景：使用 UB 中转
>
> 需要在 SIMT 内部使用 UB 时：
>
> 1. **tiling 侧**：设置 `SetLocalMemory` 分配动态 UB
> 2. **kernel 侧**：使用 `TBuf<QuePosition::VECCALC>` 声明 buffer
> 3. **VF 调用**：将 `__ubuf__` 指针传入 VF
>
> ### Tiling 侧
>
> ```cpp
> constexpr uint64_t DCACHE_SIZE = 128 * 1024;
> uint64_t ubsize = 256 * 1024;
> context->SetLocalMemorySize(ubsize - DCACHE_SIZE);
> ```

Step 1 says `SetLocalMemory`. The block says `SetLocalMemorySize`. Nothing between them acknowledges a
difference.

The sibling file, `intra-core-shared.md:41-45`, uses only the second spelling:

> ## 注意事项
>
> - 同地址并发写入需使用原子操作（`asc_atomic_add` 等）
> - 共享内存大小受 UB 可用空间限制
> - buffer 大小需在 tiling 侧预留（通过 `SetLocalMemorySize`）

Two files, three mentions, two spellings — and the minority spelling is the one in the numbered recipe.

Neither name is defined anywhere in this harvest's scope: no upstream file gives a signature, and the
tiling-context API is not in the installed toolkit trees read during this harvest (`gert::TilingContext`'s
declaration was not located). So this entry cannot say which spelling is real, and does not.

The choice table at `:45-51` is the file's other content and is carried by 0378:

> | 场景 | 方案 | 原因 |
> |------|------|------|
> | 逐元素操作，无依赖 | 直接 GM | 避免不必要的 UB 搬运 |
> | 需要核内线程间共享数据 | UB 中转 | 共享数据需在核内共享内存 |
> | 多次访问同一数据 | UB 中转 | UB 访问延迟低于 GM |

The third row states a latency ordering — UB lower than GM — with no figure and no measurement, and is
recorded here as an unquantified claim rather than carried as one.

For the two literals in the snippet: `C-950arch-007` and `950:0239` already carry them, along with
`npu-arch-guide.md:305`'s statement that 128 KB is the DCache *maximum* and `950:0209`'s finding that all
32 installed DAV_3510 inis report `ub_size=253952` (248 KB), not 262144. This entry adds the third
location and claims none of the numbers.

All quoted material is `upstream/skills-dev-main` — one origin (RULES.md Art. 3).

## 4 · Procedure
Host-side; no device is needed for the decisive arms.

Arm A — which name exists. Compile a host tiling translation unit calling `context->SetLocalMemory(...)`
and another calling `context->SetLocalMemorySize(...)`, against the installed CANN headers. Record which
resolve and, for each that does, its full signature and parameter semantics. One of three outcomes:
only the second exists (the prose is wrong), only the first exists (the snippet is wrong), or both exist
(the OVERTURN — two different calls, and the recipe's step 1 describes a different operation from its own
snippet).

Arm B — the argument's meaning. For whichever name resolves, determine from the header whether the
argument is a residual (bytes available to the kernel after reservations) or a total. §2 predicts residual,
from the snippet's own subtraction. If it is a total, the snippet reserves 128 KB by subtracting it from a
number that is itself wrong (0209: no installed 950 ini reports 256 KB), and the recipe is wrong twice
over.

Arm C — the observable consequence, which needs a board. Build one SIMT kernel with a `TBuf` allocation
larger than the reservation permits and record what happens: a tiling-time rejection, a build failure, a
launch failure, or silent corruption. `Q-950arch-07` asks the related question — whether the DCache
compile check covers a runtime-computed residual — and this arm is its allocation-side twin. Silent
corruption is the outcome with no detector and is the one worth naming in advance.

Arm D — the third-copy question, which is a repository read. Search the whole upstream tree for the
literal pair `128 * 1024` and `256 * 1024` in a `SetLocalMemorySize` context and report every location.
Three are known (`npu-arch/references/simt-arch-guide.md:138-142`,
`ascendc-simt-tiling-design/references/guide.md:63-73`, and this file). A fourth would strengthen the
generator argument; finding exactly three, with only two carrying the surrounding rule, is the finding as
it stands.

Arm E — the latency claim at `:51`, if a board is available. Time a SIMT kernel reading the same data *n*
times from GM directly and via a UB staging buffer, sweeping *n* from 1 to 16, on one die in one session.
Upstream asserts "UB 访问延迟低于 GM" with no figure; the crossover *n* is the number the choice table
implies and does not give.

Device selection, for Arms C and E: the operator names the device index, the harness prints it back with
`compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared machine,
≤4 dies), and both builds of one comparison run on one named die in one session.

## 5 · Checker — acceptance declared before the run
`resolving_spellings` (Arm A) — the set of names that resolve. Pass iff exactly one does. Both resolving is
the OVERTURN; neither resolving means the tiling context in this pin has a third name and the recipe is
stale in a way §2 does not describe.

`argument_is_residual` (Arm B) — true iff the argument is the size available after reservations. Reported,
not gated: upstream shows a subtraction and states nothing, so there is no documented answer to pass
against.

`over_allocation_outcome` (Arm C) — four-valued: tiling rejection, build failure, launch failure, silent
corruption. Reported. The fourth value is the one with no detector and is why the arm is not a boolean.

`snippet_copy_locations` (Arm D) — the list of files carrying the literal pair, each annotated with whether
the surrounding 32 KB minimum rule is present. Two integers reported separately: total copies, and copies
without the rule. The second is the one that matters, because a snippet copied away from its rule is the
mechanism.

`ub_vs_gm_crossover` (Arm E) — the smallest *n* at which the UB-staged variant is faster, per shape.
Reported, never averaged across shapes.

The positive fixture, declared before the run: Arm A must include a control call to a tiling-context method
that certainly exists (`context->SetWorkspaceSize(...)`, used in this same upstream snippet at
`multi-core-sync.md:19`) and it **must** resolve. If it does not, the include set or the context type is
wrong and every "does not resolve" result is an artefact rather than a finding. And Arm D's search must be
shown to find the two already-known locations; a search that returns only this file is a broken search, not
a smaller problem. Without both, the checker reads only "a name did not resolve and one file matched",
which is the known blind species.

Process exit codes are not the verdict for Arm A: both compiles are expected to fail in one direction or
the other, and the diagnostic text is the readout.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No translation unit was compiled,
no tiling context method resolved, no buffer allocated, no die contacted. The quoted passages are
re-verified file reads of the upstream tree performed during this harvest.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled. The entry does not establish which spelling is correct — neither name is defined
anywhere in this harvest's scope, and the tiling-context API was not located in the installed toolkit
trees read here. It does not establish what the argument means, what an over-allocation does, or whether
UB access is faster than GM. Arms A through E are all open.

**It claims none of the snippet's numbers.** The 256 KB total and the 128 KB DCache reservation are
`C-950arch-007`'s content, carried by `950:0239`, and are not re-entered here — this file is recorded as a
third location of that contradiction, not as new evidence for it. A consumer wanting the numeric claim
must read 0239; 0209 records that no installed 950 ini reports 256 KB, and `Q-950arch-04` records that the
usable-versus-physical boundary has never been measured.

It does not establish that the third copy has a common generator with the other two. Three files carrying
one snippet is consistent with copying, with a shared source, and with independent authorship from a
common example; §2 argues for a generator-level repair on the strength of the pattern, and Arm D would
only count locations, not trace provenance.

It does not establish the latency ordering at `:51`. "UB 访问延迟低于 GM" is stated with no figure, no
shape, and no measurement, and this entry records it as an unquantified upstream claim rather than
adopting it — Arm E is what would give it a crossover, which is the form a tiling routine could use.

It says nothing about `TBuf<QuePosition::VECCALC>` beyond quoting it, nor about whether a SIMT VF may
receive more than one `__ubuf__` pointer, nor about the alignment of the pointer obtained from
`GetPhyAddr()` — which 0257's 32-byte requirement would bear on and which no source in scope connects.

BOARD is `family-claimed(unverified)`: host-side tiling API spelling is not board-dependent, the files name
no board token this book recognises, and no board was contacted.
