```
ID:        0379-concurrent-same-address-writes-need-an-atomic-and-the-toolkit-ships-two-atomic-spellings
LABEL:     trap
LEVEL:     L4 (synchronisation)
STRATUM:   corroborated — two independent origins: upstream's SIMT programming guide, which states the
           requirement and names one atomic, and the INSTALLED CANN 9.0.0-beta.2 headers on this
           machine, which declare two parallel atomic families under different spellings and scopes.
           Nothing was compiled and no concurrent write was performed.
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-simt-programming-best-practices/references/intra-core-shared.md:41-45 — "## 注意事项
           / - 同地址并发写入需使用原子操作（`asc_atomic_add` 等） / - 共享内存大小受 UB 可用空间限制 /
           - buffer 大小需在 tiling 侧预留（通过 `SetLocalMemorySize`）"
SOURCE:    same file:31-38 — the VF body it applies to: "```cpp / __simt_vf__ __aicore__
           LAUNCH_BOUND(512) inline void OpSimt( / ..., __ubuf__ uint32_t* sharedData) { / // 读取共享数据
           / uint32_t val = sharedData[0]; / // 写入共享数据（注意：同地址并发写需用原子操作） /
           sharedData[Simt::GetThreadIdx()] = val * 2; / } / ```"
SOURCE:    INSTALLED TOOLKIT, independent origin — CANN `Version=9.0.0-beta.2`,
           `innerversion=V100R001C10SPC001B214`, `timestamp=20260328_213255003`, aarch64 —
           `asc/include/interface/simt_api/cpp/kernel_simt_atomic_intf.h:13-81` declares, inside
           `namespace AscendC { namespace Simt {`, ELEVEN generic atomic templates each with a
           `__ubuf__` and a `__gm__` overload: `AtomicAdd`, `AtomicSub`, `AtomicExch`, `AtomicMax`,
           `AtomicMin`, `AtomicInc`, `AtomicDec`, `AtomicCas`, `AtomicAnd`, `AtomicOr`, `AtomicXor` —
           all returning `T`, i.e. the previous value.
SOURCE:    same toolkit — `asc/include/interface/simt_api/asc_bf16.h:301-320` declares a SECOND family
           at namespace scope under the lower-case spelling upstream uses, per dtype rather than
           generic: `asc_atomic_add(__ubuf__ bfloat16_t*, bfloat16_t)`,
           `asc_atomic_add(__ubuf__ bfloat16x2_t*, bfloat16x2_t)`, and `__gm__` counterparts, plus
           `asc_atomic_sub`, `asc_atomic_exch`, `asc_atomic_max` — several of them declared for the
           packed `bfloat16x2_t` type ONLY.
INDEX:     none — nothing measured; see SOURCE. Re-derivable by file read on this machine:
           grep -n "Atomic" $ASCEND_HOME_PATH/asc/include/interface/simt_api/cpp/kernel_simt_atomic_intf.h
           grep -n "asc_atomic" $ASCEND_HOME_PATH/asc/include/interface/simt_api/asc_bf16.h
OVERTURN:  a concurrent same-address write from SIMT threads that is observed to be atomic without an
           atomic call — the requirement would then be advice; or a `Simt::AtomicAdd` and an
           `asc_atomic_add` that produce different results on the same address and type, which would
           make the two families two different guarantees rather than two spellings.
```

# 0379 · Concurrent same-address writes need an atomic, and the toolkit ships two atomic spellings

## 1 · Claim
Upstream asserts that concurrent writes to the same address from SIMT threads require an atomic operation,
and names one example — `asc_atomic_add` — followed by 等 ("and so on"). Upstream places the warning as an
inline comment in the VF body it applies to and repeats it in that file's notes. Not established here:
nothing was compiled and no concurrent write was performed.

Read in the installed CANN 9.0.0-beta.2 headers, an independent origin: **two** atomic families exist.
`AscendC::Simt::Atomic*` is a set of eleven generic templates — `Add`, `Sub`, `Exch`, `Max`, `Min`, `Inc`,
`Dec`, `Cas`, `And`, `Or`, `Xor` — each declared for both `__ubuf__` and `__gm__` addresses and each
returning the previous value. `asc_atomic_*` is a second, lower-case family at namespace scope, declared
per dtype rather than generically, in the float-format headers; in `asc_bf16.h` several of its members are
declared for the packed `bfloat16x2_t` type only.

The inference, stated separately: upstream's single named example belongs to the narrower, dtype-specific
family, and the generic family it does not mention is larger, differently scoped and differently typed.
Not established here — no call was compiled and no implementation was read.

## 2 · The wrong branch this removes
The requirement itself is the easy part. What upstream gives an agent is one function name and 等, and 等
is doing a great deal of work.

**The wrong family.** An agent that needs a maximum, a compare-and-swap, or a bitwise-or looks for
`asc_atomic_max`, `asc_atomic_cas`, `asc_atomic_or` by analogy with the one example. In this toolkit
`asc_atomic_max` exists for bf16; `asc_atomic_cas` and `asc_atomic_or` do not appear in the lower-case
family at all. The generic `AscendC::Simt::AtomicCas` and `AtomicOr` do exist — under a different spelling,
in a different namespace, in a header no upstream document names (0375). So the agent's search fails, and
what it concludes is "SIMT has no atomic compare-and-swap", which is false and which forecloses the entire
lock-free branch of its design.

**The dtype trap.** `asc_atomic_add` in `asc_bf16.h` is declared for `bfloat16_t` and for `bfloat16x2_t` —
a *packed pair*. Several of its siblings (`asc_atomic_sub`, `asc_atomic_exch`) are declared for the packed
type **only**. An agent writing an accumulation over `uint32_t` shared data — which is exactly the type in
upstream's own example, `__ubuf__ uint32_t* sharedData` — will not find its overload in the bf16 header
and must reach the generic family or a different dtype header. The one example upstream names does not
cover the one type upstream's example code uses.

**The return value.** Every `Simt::Atomic*` template returns `T`. An atomic that returns the previous value
is a *fetch-and-op*, which is what makes a lock-free algorithm possible — you can tell whether you won.
Nothing in upstream mentions a return value, so an agent following the guide writes
`AtomicAdd(p, v);` as a statement, discards the information, and then has no way to implement the
reservation pattern (claim a slot, learn your index) that irregular SIMT workloads need. The capability is
present in the header and absent from the documentation.

**The scope that is not stated at all.** The requirement is written in a file about *intra-core* sharing,
so it reads as a rule about UB. Every `Simt::Atomic*` template has a `__gm__` overload as well, and 0378's
model has SIMT threads writing GM directly. So the same hazard exists for GM writes across *cores* and
upstream states the requirement only for the UB case. Whether an atomic's guarantee spans cores or only
threads within one core is not stated anywhere in scope, and those are different guarantees — 0376 records
that cross-core ordering between launches is explicitly not guaranteed, which makes the question live
rather than pedantic.

**What upstream's own example does.** `sharedData[Simt::GetThreadIdx()] = val * 2;` writes to a
*thread-indexed* address — so no two threads collide, and the example is safe by construction. The
warning beside it is about a case the example does not exercise. That is a reasonable way to write a
caution and it leaves an agent with no worked instance of the thing being cautioned about, which is why
§4 Arm A has to build one.

## 3 · Ground / Source
The requirement, `intra-core-shared.md:41-45`, quoted in SOURCE, and the body it annotates, `:31-38`:

> ```cpp
> __simt_vf__ __aicore__ LAUNCH_BOUND(512) inline void OpSimt(
>     ..., __ubuf__ uint32_t* sharedData) {
>     // 读取共享数据
>     uint32_t val = sharedData[0];
>     // 写入共享数据（注意：同地址并发写需用原子操作）
>     sharedData[Simt::GetThreadIdx()] = val * 2;
> }
> ```

Note also `uint32_t val = sharedData[0];` — every thread reads element 0. A concurrent *read* of one
address needs no atomic, but it does need the value to be there, and nothing in the file orders that read
against whatever wrote element 0. That is an ordering question, not an atomicity one, and the file's
warning does not cover it; 0376's remedy is about cores rather than threads, and the intra-block primitive
that would cover it (`asc_syncthreads`, 0375) appears in no upstream document in scope.

The generic family, `kernel_simt_atomic_intf.h:13-81`, in the shape it is declared:

> ```cpp
> namespace AscendC {
> namespace Simt {
> template <typename T>
> __aicore__ inline T AtomicAdd(__ubuf__ T *address, T val);
> template <typename T>
> __aicore__ inline T AtomicAdd(__gm__ T *address, T val);
> …
> template <typename T>
> __aicore__ inline T AtomicCas(__ubuf__ T *address, T compare, T val);
> template <typename T>
> __aicore__ inline T AtomicCas(__gm__ T *address, T compare, T val);
> …
> }  // namespace Simt
> }  // namespace AscendC
> ```

Twenty-two declarations, eleven operations, two address spaces each, every one returning `T`. `AtomicCas`
takes an extra `compare` parameter, as expected.

The lower-case family, `asc_bf16.h:301-320`:

> ```cpp
> __SIMT_DEVICE_FUNCTIONS_DECL__ inline bfloat16_t asc_atomic_add(__ubuf__ bfloat16_t *address, bfloat16_t val);
> __SIMT_DEVICE_FUNCTIONS_DECL__ inline bfloat16x2_t asc_atomic_add(__ubuf__ bfloat16x2_t *address, bfloat16x2_t val);
> __SIMT_DEVICE_FUNCTIONS_DECL__ inline bfloat16_t asc_atomic_add(__gm__ bfloat16_t *address, bfloat16_t val);
> __SIMT_DEVICE_FUNCTIONS_DECL__ inline bfloat16x2_t asc_atomic_add(__gm__ bfloat16x2_t *address, bfloat16x2_t val);
> __SIMT_DEVICE_FUNCTIONS_DECL__ inline bfloat16x2_t asc_atomic_sub(__ubuf__ bfloat16x2_t *address, bfloat16x2_t val);
> __SIMT_DEVICE_FUNCTIONS_DECL__ inline bfloat16x2_t asc_atomic_sub(__gm__ bfloat16x2_t *address, bfloat16x2_t val);
> __SIMT_DEVICE_FUNCTIONS_DECL__ inline bfloat16x2_t asc_atomic_exch(__ubuf__ bfloat16x2_t *address, bfloat16x2_t val);
> __SIMT_DEVICE_FUNCTIONS_DECL__ inline bfloat16x2_t asc_atomic_exch(__gm__ bfloat16x2_t *address, bfloat16x2_t val);
> __SIMT_DEVICE_FUNCTIONS_DECL__ inline bfloat16_t asc_atomic_max(__ubuf__ bfloat16_t *address, bfloat16_t val);
> __SIMT_DEVICE_FUNCTIONS_DECL__ inline bfloat16x2_t asc_atomic_max(__ubuf__ bfloat16x2_t *address, bfloat16x2_t val);
> ```

Note `asc_atomic_add` has both scalar and packed overloads while `asc_atomic_sub` and `asc_atomic_exch`
have packed only — an asymmetry within one header, for one dtype family. Whether the same asymmetry holds
in `asc_fp16.h` and the float headers was not enumerated and is Arm B.

This is the same two-surface pattern 0375 records for the launch and index primitives: a lower-case,
CUDA-shaped family at namespace scope under `simt_api/`, and a CamelCase family inside `AscendC::Simt`
under `interface/simt_api/cpp/`. Upstream's SIMT guide documents the CamelCase surface everywhere
*except* here, where it names the lower-case one. So a single reference file mixes the two surfaces, and
the mixing is invisible because both names are plausible.

`__SIMT_DEVICE_FUNCTIONS_DECL__` expands to `__simt_callee__` or `__aicore__` depending on
`__NPU_COMPILER_INTERNAL_PURE_SIMT__` (`device_types.h:24-27`), so the two families also differ in
declaration attribute — the generic one is `__aicore__` unconditionally.

All upstream material quoted is `upstream/skills-dev-main` — one origin (RULES.md Art. 3).

## 4 · Procedure
Runnable later on `950PR`. The requirement is a concurrency claim, so the probe must produce the collision
upstream's own example avoids.

Arm A — the requirement, provoked. Build a SIMT kernel in which all threads of a block increment **one**
shared `uint32_t` in UB, built three ways: plain `+=`, `Simt::AtomicAdd`, and `asc_atomic_add` where a
matching overload exists. Run 500 times at four thread counts. Expected final value is the thread count;
record the distribution of observed values. The plain build's deficit is the lost-update count, and it is
the measurement — a boolean "wrong" would not distinguish one lost update from four hundred.

Arm B — the two families, enumerated and compared. Enumerate every `Simt::Atomic*` and every
`asc_atomic_*` declaration across all `simt_api/` headers, with dtypes and address spaces, and produce the
correspondence table. Then, for each operation present in both, compile a call in each spelling at a
common dtype and compare results on the same address. If any pair differs, they are two guarantees, not
two spellings — the OVERTURN's second clause.

Arm C — the return value. Build the reservation pattern: every thread calls `AtomicAdd(counter, 1)` and
uses the returned previous value as its slot index, then writes its identity into that slot. Correct
behaviour is a permutation of the thread identities with no slot written twice and none unwritten. This is
the arm that establishes fetch-and-op semantics, which upstream never mentions and which decides whether
lock-free SIMT algorithms are available at all.

Arm D — scope. Repeat Arm A with the shared counter in **GM** rather than UB, and with the threads spread
across cores rather than within one. Upstream states the requirement only for the intra-core UB case;
whether the atomic's guarantee spans cores is unestablished, and 0376's finding that cross-core ordering
between launches is not guaranteed makes it a live question. Both outcomes matter: a cross-core-safe
atomic is a synchronisation primitive; a core-local one is a trap for anyone applying 0378's direct-GM
idiom.

Arm E — the packed types. Where only a `bfloat16x2_t` overload exists (`asc_atomic_sub`,
`asc_atomic_exch`), determine whether atomicity covers the *pair* or each half independently. A packed
atomic that is atomic per-element and not per-pair is usable for accumulation and unusable for
compare-and-swap-style logic, and nothing states which it is.

Device selection is explicit: the operator names the device index, the harness prints it back with
`compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared machine,
≤4 dies), and all builds of one comparison run on one named die in one session. Arm D uses multiple cores
on one die; no die is substituted between arms.

## 5 · Checker — acceptance declared before the run
`lost_update_count` (Arm A) — expected minus observed final value, per build, per thread count, reported as
a distribution over the 500 runs and never as a mean. A mean of 0.4 lost updates and a distribution with
two runs losing a hundred are different failures; the mean hides the one that matters.

`atomic_build_exact` (Arm A) — true iff the atomic builds hit the expected value in all 500 runs at every
thread count. Pass condition **true**. Reported separately from the plain build's deficit: one is the
repair's verdict and the other is the hazard's magnitude.

`family_correspondence` (Arm B) — the two enumerations plus the pairing, with unpaired operations listed on
each side. Plus `families_agree`, true iff every paired call produces identical results.

`fetch_and_op` (Arm C) — true iff the slot assignment is a permutation with no duplicate and no gap. Pass
condition **true**; a false result means the return value is not the previous value and the header's `T`
return means something else.

`crosscore_atomic_safe` (Arm D) — true iff the GM cross-core variant loses no updates. Reported, not gated:
upstream states nothing, and both answers change what 0378's direct-GM idiom is allowed to do.

`packed_atomicity` (Arm E) — three-valued: atomic over the pair, atomic per element, or neither.

The positive fixture, declared before the run: **Arm A's plain `+=` build must lose at least one update**
at the highest thread count. If it does not, the collision never happened — the compiler may have
serialised, or the threads may not overlap — and the atomic builds' clean results are statements about the
probe, not about atomicity. A concurrency experiment whose unsynchronised arm passes has measured nothing.
A second fixture for Arm C: a single-thread launch must produce slot 0 and nothing else; if it does not,
the slot bookkeeping is wrong and the permutation check is void. Without both, the checker reads only "the
counter looked right", which is the known blind species.

Process exit codes are not the verdict for any arm: every failure here exits zero.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No kernel was built, no atomic
called, no counter incremented, no slot claimed, no die contacted. The header declarations quoted in §3
are file reads over the installed CANN 9.0.0-beta.2 tree performed under the phase-1 sanctioned read-only
exception; they establish what is declared and nothing about what the operations guarantee.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled or run. The entry does not establish that a non-atomic concurrent write loses updates,
that either atomic family prevents it, that the return value is the previous value, or that atomicity spans
cores — Arms A through E are all open.

**It establishes nothing about either family's guarantee.** Only declarations were read. An atomic's
memory-ordering semantics, its scope (thread, block, core, device), and its behaviour on the packed types
are not in a declaration, and no source in scope documents any of them for either family.

It does not establish the full extent of either family. The generic family was enumerated from one header;
the lower-case family was read only in `asc_bf16.h`, so its members in `asc_fp16.h`, the float headers and
elsewhere are uncounted, and the asymmetry noted in §3 (scalar-and-packed for `add`, packed-only for `sub`
and `exch`) is a bf16 observation that may not generalise.

It does not establish which family an agent should use. Upstream names one and the toolkit ships two; this
entry records both and recommends neither, because nothing observed distinguishes them and Arm B is what
would.

It says nothing about the *ordering* question §3 raises — every thread reading `sharedData[0]` needs that
element to have been written, which is a barrier question and not an atomicity one, and no upstream
document in scope names an intra-block barrier at all.

It says nothing about atomic performance. An atomic that is correct and serialises 512 threads on one
address is a correctness fix and a throughput cliff, and no arm here measures it.

BOARD is `family-claimed(unverified)`: the headers name architecture gates rather than boards, upstream's
file names no board token this book recognises, and no board was contacted.
