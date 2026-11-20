```
ID:        0480-on-dav-3510-wholereducesum-lets-the-destination-dtype-differ-from-the-source-and-drops-the-half-float-assert-the-other-branch-keeps
LABEL:     knowledge
LEVEL:     L5 (compute & numerics)
STRATUM:   corroborated — the installed CANN toolchain at pin cann-9.0.0-beta.2 (headers in the
           installed toolkit, STRATA S2) as the primary origin, plus upstream's skills repo, whose
           elementwise shelf uses the API and states no dtype rule. Nothing measured, nothing
           compiled; no caller exercising the widening was found.
BOARD:     family-claimed(unverified)
SOURCE:    /usr/local/Ascend/cann-9.0.0-beta.2/asc/include/interface/kernel_operator_vec_reduce_intf.h:143-153
           — "#if (__NPU_ARCH__ == 3510) || (__NPU_ARCH__ == 5102) || (__NPU_ARCH__ == 3003) ||
           (__NPU_ARCH__ == 3113) / template <typename T, bool isSetMask = true, typename U = T> /
           __aicore__ inline void WholeReduceSum(const LocalTensor<U>& dst, const LocalTensor<T>& src,
           / … / #else / template <typename T, bool isSetMask = true> / __aicore__ inline void
           WholeReduceSum(const LocalTensor<T>& dst, const LocalTensor<T>& src, / … / #endif"
SOURCE:    same toolkit, asc/impl/basic_api/kernel_operator_vec_reduce_intf_impl.h:362-364 — the
           non-3510 branch's dtype assert: "ASCENDC_ASSERT((SupportType<PrimType, half, float>()),
           { KERNEL_LOG(KERNEL_ERROR, "Failed to check dtype in " / "WholeReduceSum, current api
           support dtype combination is src and dst both: half / float");});" — absent from the
           3510 branch (:492-513) ; :511 — "WholeReduceSumImpl<SrcPrimType, isSetMask, DstPrimType>(
           (__ubuf__ DstPrimType*)dst.GetPhyAddr(), (__ubuf__ SrcPrimType*)src.GetPhyAddr(),"
SOURCE:    ops/ascendc-performance-best-practices/reference/elementwise/vector_efficiency_design.md:145
           — "float totalSum = WholeReduceSum(blockSums, numBlocks);" (upstream's only use; states no
           dtype rule anywhere in the family)
INDEX:     none — nothing measured; see SOURCE. Re-derivable by file read (no device):
           sed -n '143,153p' /usr/local/Ascend/cann-9.0.0-beta.2/asc/include/interface/kernel_operator_vec_reduce_intf.h
           grep -n 'src and dst both: half / float' /usr/local/Ascend/cann-9.0.0-beta.2/asc/impl/basic_api/kernel_operator_vec_reduce_intf_impl.h
OVERTURN:  a `WholeReduceSum<half, true, float>(...)` — narrow source, wide destination — that fails
           to compile or produces wrong values for a DAV_3510 target under this toolkit pin. The
           widening would then be a declaration the backend does not honour, and this entry would be
           recording a dead template parameter rather than a capability.
```

# 0480 · On DAV_3510, WholeReduceSum lets the destination dtype differ from the source, and drops the half/float assert the other branch keeps

## 1 · Claim
The installed CANN toolchain at pin `cann-9.0.0-beta.2` declares `WholeReduceSum` twice, under a
preprocessor gate on `__NPU_ARCH__`. On 3510 and three other architecture values it carries a third
template parameter `typename U = T`, and its destination is `LocalTensor<U>` while its source is
`LocalTensor<T>` — so the destination element type may differ from the source's. On every other
architecture the destination and source are both `LocalTensor<T>`, and the implementation additionally
asserts that `T` is `half` or `float`, with the message "current api support dtype combination is src
and dst both: half / float". **That assert is absent from the 3510 branch.** The 3510 implementation
carries the two primitive types through separately to the backend call
(`WholeReduceSumImpl<SrcPrimType, isSetMask, DstPrimType>`), so the widening is plumbed and not merely
declared at the interface. Upstream asserts, of the same API, only that it is a single high-latency
instruction worth decomposing (`0478`); upstream asserts no dtype rule for it in any file of the
family, and its one written use passes the same element type on both sides. Not established here that
any caller reaches the widened form.

## 2 · The wrong branch this removes
Without this entry an agent carries a reduction's accumulation precision as a separate step. The
natural pattern for reducing an FP16 buffer accurately is cast-then-reduce: `Cast` the source to FP32
in UB, then `WholeReduceSum<float>`. That costs a full pass over the data and a second UB buffer the
size of the source — which, in a UB-bound elementwise operator, is exactly the budget an optimisation
is trying to recover. On this architecture the API's own destination type may be wider than its source
type, so the cast may be unnecessary.

It may also be a trap in the other direction, and this entry is careful about which. **No caller in the
installed tree supplies the third template argument.** Every instantiation found is `WholeReduceSum<T>`
or `WholeReduceSum<T, bool>` — the toolkit's own layernorm, groupnorm, softmax and reduce-sum
implementations all use `float` for both. So the widening is declared, plumbed through to the backend
call, and unexercised by anything shipped. An agent that adopts it is the first user, and §7 says so.

The second wrong branch is generalising the dropped assert. The non-3510 branch restricts `T` to
`half` and `float`; the 3510 branch has no such check. That does **not** mean 3510 accepts every dtype
— it means the interface layer stops checking, and what the backend accepts is not visible from the
header. This is **not** the shape `0405`/`0406` record: there a per-architecture implementation header
carried its own, *longer* `static_assert` list, so the wider accepted set was readable. Here no such
list exists (§3), so nothing is readable at all. The lesson from those entries still transfers, and is
the stronger half of it: the absence of a check is not the presence of a capability.

## 3 · Ground / Source
The gate and the two declarations, `asc/include/interface/kernel_operator_vec_reduce_intf.h:143-153`:

```cpp
#if (__NPU_ARCH__ == 3510) || (__NPU_ARCH__ == 5102) || (__NPU_ARCH__ == 3003) || (__NPU_ARCH__ == 3113)
template <typename T, bool isSetMask = true, typename U = T>
__aicore__ inline void WholeReduceSum(const LocalTensor<U>& dst, const LocalTensor<T>& src,
    const uint64_t mask[], const int32_t repeatTime, const int32_t dstRepStride, const int32_t srcBlkStride,
    const int32_t srcRepStride);
#else
template <typename T, bool isSetMask = true>
__aicore__ inline void WholeReduceSum(const LocalTensor<T>& dst, const LocalTensor<T>& src,
    const uint64_t mask[], const int32_t repeatTime, const int32_t dstRepStride, const int32_t srcBlkStride,
    const int32_t srcRepStride);
#endif
```

The same gate appears again at `:188-197` for the count-mask overload, so both mask modes are widened
on 3510 and neither is elsewhere.

The assert that is present in one branch and not the other,
`asc/impl/basic_api/kernel_operator_vec_reduce_intf_impl.h:362-364` (the `#else`, non-3510 branch):

```cpp
    using PrimType = PrimT<T>;
    ASCENDC_ASSERT((SupportType<PrimType, half, float>()), { KERNEL_LOG(KERNEL_ERROR, "Failed to check dtype in "
        "WholeReduceSum, current api support dtype combination is src and dst both: half / float");});
```

**The absence in the 3510 branch was checked by search, not by reading one region.** Every
`SupportType` occurrence in that file was located and mapped against the preprocessor regions. Both
`WholeReduceSum` 3510 branches — the bit-mask form at `:331-352` and the count-mask form at
`:492-513` — contain none; both `#else` forms do (`:363`, `:524`). And every `SupportType` in the file
is `<…, half, float>`: there is **no** wider per-architecture dtype list anywhere in it, so this is not
the shape `0406` records, where the architecture-specific header carried its own, longer
`static_assert` list. Here the check is simply not made.

The contrast that makes this specific rather than a blanket property of the 3510 path: `WholeReduceMax`
and `WholeReduceMin` **keep** their `half`/`float` assert *inside* the 3510 branch (`:398-401`,
`:448-451`, `:548-551`). So on this architecture the dtype check is dropped for `Sum` and retained for
`Max`/`Min` — which is consistent with `Sum` being the operation whose accumulator may reasonably be
wider than its input, and is the reason this entry is about `WholeReduceSum` and not about the reduce
family. What it has instead is the two-type
plumbing, `:511`:

```cpp
    WholeReduceSumImpl<SrcPrimType, isSetMask, DstPrimType>((__ubuf__ DstPrimType*)dst.GetPhyAddr(), (__ubuf__ SrcPrimType*)src.GetPhyAddr(),
        mask, repeatTime, dstRepStride, srcBlkStride, srcRepStride);
```

with `using DstPrimType = PrimT<U>; using SrcPrimType = PrimT<T>;` above it — two distinct primitive
types reaching the backend. The non-3510 branch passes one type twice
(`WholeReduceSumImpl<PrimType, isSetMask>`). So the difference is not cosmetic: the two branches call
different backend templates.

The same widening appears on `RepeatReduceSum` under the identical gate (`:272-292`), so it is a
family-level change on this architecture rather than one API's quirk.

**Three things this does not settle, and they are the entry's substance.**

*Reachability.* A search of the installed `asc/` tree for any `WholeReduceSum` instantiation with three
template arguments returns nothing. Every caller found — `reduce_sum_v220_impl.h:176`,
`layernorm_common_basic_impl.h:88`, `groupnorm_common_impl.h:261`,
`softmax_common_impl.h:330` and others — uses one or two arguments with `float` throughout. The
capability is declared, plumbed, and not shown reachable.

*Which pairs.* With the assert gone, the header constrains nothing, and this book cannot enumerate
accepted `(T, U)` pairs by reading. `0406` establishes, for a different API family, that the
architecture-specific implementation headers carry the real dtype lists in `static_assert`s. **A search
for `SupportType` across `asc/impl/basic_api/` found no such per-architecture list for this basic API**
— every occurrence in the reduce implementation file is the same `half`/`float` pair, and the
`dav_c310/` reg-compute headers' `SupportType` uses are a different API surface. So the accepted set is
unknown rather than unrestricted, and §4 arm 1 enumerates by compiling rather than by grepping.

*The architecture spelling.* The gate is `__NPU_ARCH__ == 3510`, alongside 5102, 3003 and 3113. This
book's vocabulary map (`form/CONVENTIONS.md`) maps `__NPU_ARCH__` 2201 to DAV_2201 and 3510 to
DAV_3510, and knows none of the other three values. The same unmapped-identifier observation is made
from a different header at `0463`, and this book's identifier entries are `0203` and `0421`. Recorded
as `C-950fin-009` (shared with `0463`) — two headers in the shipped toolchain gate on architecture
numbers our own convention table does not list.

**Origins.** The primary origin here is the installed toolchain, not the skills repo — which is
unusual for this book and is why the STRATUM line names it first. Upstream's contribution is that its
elementwise shelf calls the API (`vector_efficiency_design.md:145`) and states no dtype rule for it in
any of the family's files, so the two origins do not conflict; they are a capability and a silence.
That is enough for `corroborated` on the API's *existence and use*, and not enough for anything about
the widening, which only one origin mentions.

## 4 · Procedure
Arms 1 and 2 need a compiler and no device; arms 3 and 4 need a named 950 board (950PR or 950DT). None
is run in this phase.

**Arm 1 — the accepted pairs (compile-only).** For a DAV_3510 target under the stated pin, instantiate
`WholeReduceSum<T, true, U>` for `T, U ∈ {half, float, bfloat16_t, int16_t, int32_t}` — 25
combinations — and record which compile, with the verbatim diagnostic for those that do not. This
converts "the assert is absent" into an enumerated accepted set, and is the same method `0406` used for
the advanced reduce APIs.

**Arm 2 — the other branch, as a control (compile-only).** The same 25 combinations for a DAV_2201
target. The prediction is that only `(half, half)` and `(float, float)` compile, per the assert. This
control matters: without it, a wide accepted set on 3510 could be a property of the compiler rather
than of the architecture branch. **Note the boundary: this arm's result is evidence about the
non-3510 branch's behaviour and is NOT carried into this book as a 910 fact (RULES.md Art. 1) — it is a
control for a 950 claim and its result stays in §6 as such.**

**Arm 3 — the widening's numerics (device).** For each accepted `(T, U)` pair with `U` wider than `T`,
reduce a buffer whose exact sum overflows or loses precision in `T` and compare against an FP64
reference. Report whether accumulation happens at `U`'s precision or at `T`'s and is then converted —
those are different capabilities and the header cannot distinguish them.

**Arm 4 — the alternative it would replace (device).** Cast-then-reduce (`Cast` to FP32, then
`WholeReduceSum<float>`) versus the widened form, at lengths `2^10 … 2^20`, reporting `aiv_time`, UB
occupancy and accuracy. This is the arm that says whether the capability is worth using, and it is
retained even if arm 3 shows the accumulation is not at `U`'s precision — a widened *store* with no
widened accumulate still saves the destination buffer, which is a smaller but real benefit.

Refuses to assume: that a free die stays free, or that a die may be substituted; that a declaration
that compiles is a capability that works (arm 3 exists because it may not be); that the absence of an
assert means acceptance (arm 1 enumerates rather than infers); that accumulation precision follows the
destination type; that a 2201 result says anything about a 950 board or the reverse (RULES.md Art. 1);
that the shelf's call shape is usable (`0478` — arms 3 and 4 build the header's shape).

## 5 · Checker — acceptance declared before the run
Verdict `accepted_pairs(arch)` from arms 1 and 2, a set of `(T, U)` per architecture target, declared
before the run. Acceptance for this entry: `accepted_pairs(3510)` strictly contains
`accepted_pairs(non-3510)`, and contains at least one pair with `T ≠ U`. The OVERTURN fires iff
`accepted_pairs(3510)` contains no pair with `T ≠ U` — the third template parameter would then be a
dead declaration.

Verdict `accumulation_precision(T, U)` from arm 3 ∈ {`at_U`, `at_T_then_cast`, `wrong`}, decided by
whether a sum that is exactly representable in `U` but not in `T` comes out exact.

Verdict `widening_beats_cast` from arm 4, boolean per length, with the variance floor and the UB
occupancy difference.

The exit code is not the verdict: a reduction that silently accumulates at the narrow precision exits 0
and is close to right, which is the whole hazard. Guards: (1) arm 3's test vector is constructed so
that narrow accumulation gives a *specifically wrong* value — a long run of values whose partial sums
cross `T`'s representable spacing — and the checker fails red if the observed error is neither zero nor
that predicted value, because "some other error" means the vector did not exercise what it was built
for; (2) **the input that makes this checker go red**: `(float, float)`, which must be accepted on both
architecture targets and must reduce exactly — if it fails on either, the harness is not building a
working reduction and every cell of arm 1 is an artifact; (3) no cell is reported without its target
architecture, the toolkit pin, the compiler command, and — for arms 3 and 4 — the board token, the
length, the floor and the atol.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement, and no compiler was invoked.
The two gated declarations, the assert present in one branch and absent from the other, the two-type
plumbing into the backend call, the identical gate on `RepeatReduceSum`, and upstream's single
dtype-silent use of the API are file reads performed at drafting time. **The reachability result — that
no instantiation in the installed `asc/` tree supplies the third template argument — is a search
result over that tree at this pin, not a proof that none exists anywhere.** The observation that the
two branches call different backend templates is a reading of the two implementations, not an
observation of a build.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured, compiled or run. The entry does not establish that any `T ≠ U` instantiation
compiles: the widening is **declared and plumbed, not shown reachable**, and §4 arm 1 is what would
enumerate it. It does not establish which dtype pairs the 3510 backend accepts — the interface-level
assert is absent and no per-architecture `static_assert` list was found for this basic API, so the
accepted set is unknown rather than unrestricted. It does not establish that accumulation happens at
the destination's precision; a widened destination could be a widened *store* of a narrowly-accumulated
result, and those are different capabilities (arm 3). It does not establish that the widening is
faster, cheaper or more accurate than cast-then-reduce (arm 4). It says nothing about
`WholeReduceMax`/`Min`, which are not widened under the same gate, nor about the advanced-API `Reduce`
family (`0405`, `0406`), which is a different surface with its own dtype lists. The gate covers four
architecture values, of which only 3510 is in this book's vocabulary map; nothing here is established
for 5102, 3003 or 3113, and the unmapped identifiers are recorded at `C-950fin-009`. **Nothing here is
established for any 910-family board: the non-3510 branch is described only as a control for a 950
claim, and no 910 fact is carried into this book from it (RULES.md Art. 1).** The header is architecture-
gated rather than board-scoped, so BOARD is `family-claimed(unverified)`; §4 names 950PR/950DT only as
where our device arms would run.
