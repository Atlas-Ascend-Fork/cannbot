```
ID:        0406-the-950-backend-accepts-eleven-dtypes-for-reducemax-where-the-shared-public-header-documents-two
LABEL:     knowledge
LEVEL:     L5 (compute & numerics)
STRATUM:   corroborated — upstream's skills repo (one origin) plus the installed CANN toolchain
           (independent origin: headers in the installed toolkit, STRATA S2). Nothing measured,
           nothing compiled.
BOARD:     family-claimed(unverified)
SOURCE:    /usr/local/Ascend/cann-9.0.0-beta.2/aarch64-linux/asc/impl/adv_api/detail/reduce/
           reduce_max/reduce_max_c310_impl.h:127-131 — "static_assert(SupportType<T, int8_t, uint8_t,
           int16_t, uint16_t, half, bfloat16_t, int32_t, uint32_t, float, / int64_t, uint64_t>(),
           / "ReduceMax only support "
           / "int8_t/uint8_t/int16_t/uint16_t/half/bfloat16_t/int32_t/uint32_t/float/int64_t/uint64_t
           data type on current " / "device!");"
SOURCE:    same toolkit, asc/include/adv_api/reduce/reduce.h:101 —
           " * \note support data type: float/half" (the public doc comment on the same API)
SOURCE:    ops/ascendc-tiling-design/references/reduction/ara-rowsplit.md:176 —
           "ReduceMax<float, Pattern::Reduce::RA>(chunkResultLocal, xLocal, tmpLocal, srcShape, true);"
           (upstream's own use is float-only throughout the family)
INDEX:     none — nothing measured; see SOURCE. Re-derivable by file read (no device):
           grep -Rn 'SupportType<T,' /usr/local/Ascend/cann-9.0.0-beta.2/aarch64-linux/asc/impl/adv_api/detail/reduce/*/*c310_impl.h
           grep -n 'note support data type' /usr/local/Ascend/cann-9.0.0-beta.2/aarch64-linux/asc/include/adv_api/reduce/reduce.h
OVERTURN:  a `ReduceMax<bfloat16_t, Pattern::Reduce::AR>` or `ReduceSum<int64_t, Pattern::Reduce::AR>`
           instantiation that fails to compile for a DAV_3510 target under this toolkit pin — the
           per-operation `SupportType` lists would then not be the accepted set, and the widening this
           entry records would be a dead declaration rather than a capability.
```

# 0406 · The 950 backend accepts eleven dtypes for ReduceMax where the shared public header documents two

## 1 · Claim
Upstream asserts, across the whole reduction family, that a Reduce call is made in `float`: every
Reduce instantiation in the design shelf is `ReduceMax<float, …>` or `ReduceMax<float>`, and the
implementation shelf states the policy behind it as a blanket rule — narrow inputs are cast up to FP32
on load and cast back on store, `FP32 直通、FP16/BF16 自动 Cast`. Upstream states no dtype table for
these APIs and names no dtype the hardware refuses.

Against that stands a second, independent origin. The installed CANN toolchain, at pin
`cann-9.0.0-beta.2`, restricts each `Reduce*` advanced API's
element type by a `static_assert` inside a per-architecture implementation header, and the DAV_3510
(`c310`) lists are wider than the doc comments on the shared public header that declares the same
functions. For `ReduceMax` and `ReduceMin` the `c310` list is eleven types — `int8_t`, `uint8_t`,
`int16_t`, `uint16_t`, `half`, `bfloat16_t`, `int32_t`, `uint32_t`, `float`, `int64_t`, `uint64_t` —
against a public doc comment reading `support data type: float/half`. For `ReduceSum` the `c310` list
is five — `int32_t`, `uint32_t`, `float`, `int64_t`, `uint64_t` — against `support data type: float`,
and the implementation dispatches 8-byte types to a separate `…B64…` compute path selected by
`SupportBytes<T, 8>()`. For `ReduceMean` and `ReduceProd` the `c310` list is `float` only, matching
their doc comments. So upstream's float-only habit is consistent with the narrowest reading of the
toolkit and leaves nine of the eleven types the 950 backend declares for `ReduceMax` untouched and
uncommented. Not established here that any of these instantiations compiles or computes correctly —
nothing was compiled, and reading a `static_assert` is not observing a build.

## 2 · The wrong branch this removes
A dtype table is the first thing an agent trusts and the last thing anyone re-derives. Faced with an
`int32` ReduceMax over a large axis, an agent that read the public header's `float/half` note writes
the standard workaround: cast to FP32, reduce, cast back — three passes over the data where the
toolkit offers one, and for `int32` values above 2^24 a cast round trip that is not even correct. The
header sentence that produced that plan is nine words long and sits directly above the function it
misdescribes.

The wrong branch is available in the other direction too, and it is the more dangerous one. `int64_t`
and `uint64_t` are in the `ReduceSum` list, and the implementation routes them to
`ReduceSumARB64ReuseSourceCompute` / `ReduceSumRAB64ReuseSourceCompute` — a distinct 64-bit code path.
This book already records that upstream deliberately avoids a vendor 64-bit path in another family
because it carried verified defects (`0145`: `int64` TopK routes around the vendor `b64` path, and
`fp16` TopK computes in FP32, `因为两者都携带已验证的缺陷`). So "the type is in the list" is not "the
type is a good idea": the list says the compiler will accept it, and one of upstream's own families
has already found a b64 path it would not use. An agent that reads this entry as permission to reduce
in `int64` has read it wrong; what the entry licenses is *asking the question*, and §4 is how it is
asked.

The third wrong branch is assuming the two sources are simply out of date with each other and picking
the newer-looking one. They are not the same kind of statement. The doc comment is on the
architecture-generic declaration and must describe the intersection of every backend the toolkit
ships, or nothing at all; the `static_assert` is in one backend and describes exactly that backend.
Both can be literally true at once — `float` is the common denominator — and reading the doc comment
as a *capability ceiling* rather than as a portable subset is the actual error. That reading has a
name in this book: a check that reads only the lines it expects. Here it is a reader that reads only
the header it was pointed at.

The operational content: **on this toolkit the portable dtype set for a `Reduce*` call is the doc
comment's, and the set the 950 backend will compile is the `_c310_impl.h` `SupportType` list — so a
dtype decision for a 950 kernel is made from the implementation header, and a dtype decision for
portable code is made from the doc comment.**

## 3 · Ground / Source
The full per-operation picture, read from the installed toolkit at drafting time. Left column: the doc
comment on the shared declaration, `asc/include/adv_api/reduce/reduce.h`. Right column: the
`SupportType` list in `asc/impl/adv_api/detail/reduce/<op>/<op>_c310_impl.h`.

```
op          reduce.h doc          line   c310 SupportType<T, …>                                          line
ReduceMean  float                 :50    float                                                           :42
ReduceMax   float/half            :101   int8_t uint8_t int16_t uint16_t half bfloat16_t
                                         int32_t uint32_t float int64_t uint64_t                          :127-131
ReduceMin   float/half            :152   int8_t uint8_t int16_t uint16_t half bfloat16_t
                                         int32_t uint32_t float int64_t uint64_t                          :127-131
ReduceSum   float                 :204   int32_t uint32_t float int64_t uint64_t                          :116-117
ReduceProd  float                 :255   float                                                            :134
ReduceAny   float/uint8_t         :306   uint8_t float                                                    :63-64
ReduceAll   float/uint8_t         :357   uint8_t float                                                    :63-64
```

Two of the seven match, three are wider on the backend, and two (`ReduceAny`, `ReduceAll`) agree as
sets while differing in order. `ReduceAny`'s two overloads disagree with *each other* in the same file
— `:306` says `float/uint8_t` and `:331` says `float` — which is a third state and belongs to neither
column. Registered as `C-950td-008`.

The widest case, `reduce_max_c310_impl.h:127-133`, verbatim:

```cpp
    static_assert(SupportType<T, int8_t, uint8_t, int16_t, uint16_t, half, bfloat16_t, int32_t, uint32_t, float,
        int64_t, uint64_t>(),
        "ReduceMax only support "
        "int8_t/uint8_t/int16_t/uint16_t/half/bfloat16_t/int32_t/uint32_t/float/int64_t/uint64_t data type on current "
        "device!");
    static_assert(std::is_same_v<pattern, Pattern::Reduce::AR> || std::is_same_v<pattern, Pattern::Reduce::RA>,
        "ReduceMax only support AR and RA pattern on current device!");
```

against `reduce.h:99-101`:

```
 * \brief This function calculates the max value of all elements in the input tensor based on the reduction pattern.
 *
 * \note support data type: float/half
```

`ReduceMin`'s file carries the identical eleven-type list at the identical line numbers (`:127-131`),
with every diagnostic string correctly saying `ReduceMin` — the two files are a cleanly copied pair,
and this drafter re-verified that specifically after first mis-transcribing one of the two messages
(the error and its correction are reported in `harvest/standing/950-td.md`, self-report SR-950td-01).
So there is no naming artifact here to warn about, and the two operations' diagnostics are safe to
attribute from (`0345`).

`ReduceSum`'s divergence and its 64-bit dispatch, `reduce_sum_c310_impl.h:114-131`:

```cpp
    static_assert(std::is_same_v<pattern, Pattern::Reduce::AR> || std::is_same_v<pattern, Pattern::Reduce::RA>,
        "ReduceSum only support AR and RA pattern on current device!");
    static_assert(SupportType<T, int32_t, uint32_t, float, int64_t, uint64_t>(),
        "ReduceSum only support int32_t/uint32_t/float/int64_t/uint64_t data type on current device!");
    __ubuf__ T *dstAddr = (__ubuf__ T *)dst.GetPhyAddr();
    __ubuf__ T *srcAddr = (__ubuf__ T *)src.GetPhyAddr();
    LocalTensor<T> tmpBuf = sharedTmpBuffer.ReinterpretCast<T>();
    __ubuf__ T *tmpAddr = (__ubuf__ T *)tmpBuf.GetPhyAddr();
    if constexpr (std::is_same_v<pattern, Pattern::Reduce::AR>) {
        if constexpr (SupportBytes<T, 8>()) {
            ReduceSumARB64ReuseSourceCompute<T, isReuseSource>(dstAddr, srcAddr, tmpAddr, srcShape);
        } else {
            ReduceSumARReuseSourceCompute<T, isReuseSource>(dstAddr, srcAddr, tmpAddr, srcShape);
        }
    } else {
        if constexpr (SupportBytes<T, 8>()) {
            ReduceSumRAB64ReuseSourceCompute<T, isReuseSource>(dstAddr, srcAddr, tmpAddr, srcShape);
        } else {
            ReduceSumRAReuseSourceCompute<T, isReuseSource>(dstAddr, srcAddr, tmpAddr, srcShape);
```

Note the two omissions from `ReduceSum`'s list that its `ReduceMax` sibling has: `half` and
`bfloat16_t`. So on this backend a *max* over bf16 is a native call and a *sum* over bf16 is not —
which is exactly the asymmetry a numerics engineer would expect (an order-independent max needs no
accumulator width; a sum does) and exactly the asymmetry a dtype table flattens.

What upstream's skills repo does with all of this: nothing. Every Reduce call in the design shelf's
reduction family is `float`-instantiated — `ara-rowsplit.md:176`
(`ReduceMax<float, Pattern::Reduce::RA>(chunkResultLocal, xLocal, tmpLocal, srcShape, true);`),
`patterns.md:131` (the same call), `ar-colsplit.md:111`
(`ReduceMax<float>(chunkResultLocal, xLocal, tmpLocal, chunkSize, false);`) — and the implementation
shelf states the policy explicitly, `ascendc-performance-best-practices/reference/reduce/guide.md:76`:

```
| `CastToFp32From<T>` / `CastFromFp32To<T>` | 载入即升 FP32、输出即降回原精度，FP32 直通、FP16/BF16 自动 Cast |
```

restated at `:231` (`载入即升 FP32 保证数值稳定，输出即降回`). That is a deliberate numerical choice —
this book carries the reason at `0397` (the safe accumulation length is per-format and fp16 runs out
three decades before fp32) — and for a *sum* it is well founded. For `ReduceMax` and `ReduceMin` the
numerical argument does not apply, the backend offers eleven native types including both 16-bit floats
and every integer width, and upstream still casts. Whether the native narrow path is faster than
cast-reduce-cast is unmeasured by anyone; recorded in `harvest/standing/950-td.md` as `Q-950td-02`.

The other backend the toolkit ships restricts `ReduceSum` to `float` alone
(`reduce_sum_v220_impl.h:287`), so the doc comment's `float` is the portable intersection rather than
an error. **No fact about that other architecture enters this book** (RULES.md Art. 1); the file is cited
only to establish that the doc comment has a consistent reading, which is what keeps §2's third wrong
branch from being the right one.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase. As with
`0405`, the first half needs **no device** — it is a compile study — and only the numerics and timing
arms need a die.

**Arm 1 — device-free. Does the wider list compile?** For each `(op, T)` pair in the `c310` column,
compile a translation unit instantiating `op<T, Pattern::Reduce::AR>` and `op<T,
Pattern::Reduce::RA>` for a 950 SoC version. Also compile the pairs the doc comment lists but the
backend does not (`ReduceSum<half>`, `ReduceSum<bfloat16_t>`), which must **fail**. One compiler pin,
recorded by `--version` and by `readlink -f` on the toolkit path. Record exit status and the first
unclipped diagnostic per instantiation. Confirm by `-E` include provenance that `_c310_impl.h` is the
selected implementation (`0405` arm 2's requirement, inherited).

**Arm 2 — on-card. Correctness across the widened set.** For each `(op, T)` that compiled, run
`[A1, R] = [1024, 4096]` AR and `[R, A0] = [4096, 256]` RA against a CPU reference computed in the
same type (for integers, exactly; for `half`/`bfloat16_t`, in float64 then compared against the
type's own rounding envelope). Inputs include, per type: the full-range extremes, a run that
overflows the accumulator if one is not widened, and — for the signed integer types — a case whose
true sum is negative. The overflow case is the one that separates "the call exists" from "the call is
usable", and upstream's cast-to-FP32 policy exists partly to avoid it.

**Arm 3 — on-card. Is the native narrow path worth using?** For `ReduceMax` at `half` and
`bfloat16_t`, compare (a) the native instantiation against (b) upstream's policy —
`CastToFp32From<T>` on load, `ReduceMax<float>`, `CastFromFp32To<T>` on store — built from the
implementation shelf's own base template. Same shapes, same inputs, one compiler pin, distinct md5s,
host echo of which path ran. Record `aiv_time`, MTE2 bytes and UB high-water mark. This is `Q-950td-02`.

**Arm 4 — on-card, the b64 caution. Retained because it is expected to be the unflattering one.**
`ReduceSum<int64_t, AR>`, which dispatches to `ReduceSumARB64ReuseSourceCompute`. Correctness against
an exact CPU reference, including values above 2^32 and a case summing to exactly 2^63−1. `0145`
records that another family found a vendor b64 path defective enough to route around; this arm exists
so that this book records what *it* found, whether that is agreement or not.

Device selection for arms 2–4: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at
20 s spacing; bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and
discard the case if the die moved. Variance floor first: one build, 30 in-process runs, 5
fresh-process runs.

Refuses to assume: that the toolkit at run time is the one read at drafting time (pin re-derived and
compared); that a compile failure is the *expected* failure (the diagnostic text is required, and
`reduce_max_c310_impl.h:133` printing `ReduceMin` is why); that a type that compiles computes
correctly (arm 2); that a native call is faster than the cast policy (arm 3 is the question, not the
answer); that a free die stays free; that a die may be substituted.

## 5 · Checker — acceptance declared before the run
Verdict `compiles(op, T)` ∈ {`yes`, `no_dtype`, `no_other`}, where `no_dtype` requires the diagnostic
to contain that operation's own `only support … data type on current device!` text. Declared before
the run: this entry is **supported** iff `compiles(op, T) == yes` for every `(op, T)` in the `c310`
column, **and** `compiles(ReduceSum, half) == no_dtype`. The OVERTURN fires iff any `(op, T)` in the
`c310` column reports `no_dtype` — the `SupportType` list would then not be the accepted set.

Verdict `correct(op, T)` from arm 2: true iff the elementwise comparison passes on all three input
classes, with the overflow case reported separately as `overflowed` rather than folded into a
failure — an integer sum that wraps is the type doing what the type does, not the API being wrong, and
conflating the two would make this entry recommend a cast that may be unnecessary.

Verdict `narrow_speedup(T)` = median `aiv_time`(cast policy) / median `aiv_time`(native), with the
floor, for `T ∈ {half, bfloat16_t}` from arm 3. Reported, not a pass condition. `> 1 + floor` means
upstream is leaving time on the table; `< 1 − floor` means upstream's cast policy is faster and the
widened dtype list is a portability convenience rather than a performance one. Both are findings; the
prediction is recorded now as *no prediction*, because neither shelf states one.

Verdict `b64_exact` from arm 4: true iff every `int64_t` case matches the exact reference.

The exit code is not the verdict, in both directions. In arm 1 a non-zero exit is the *expected*
result for the two planted failures, so "did it build" is not a gate. In arms 2–4 a reduction returns
a number regardless. Three guards. First, **the input that makes this checker go red**: arm 1's
planted failures — `ReduceSum<half>` and `ReduceSum<bfloat16_t>` — must fail with `no_dtype`. If they
compile, the harness is not applying the `c310` assertions at all (wrong include path, wrong SoC flag)
and every `yes` it reported is uninformative. A compile matrix whose only outcome is "everything I
tried worked" has not been shown able to reject anything. Second, every arm-2 comparison is against a
reference in the operand's own semantics, and a `(op, T)` whose comparison did not execute is reported
untestable, never as `correct`. Third, every result carries the toolkit pin, the compiler version, the
`-E` include provenance and (for arms 2–4) the md5 and echoed path; a result missing any of these is
untestable.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The seven-row table in §3 is a
pair of file reads of the installed toolkit performed at drafting time, re-derivable by the two `grep`
commands in INDEX; reading a `SupportType` list is not observing a compilation and certainly not
observing a computation. No kernel was built, no reduction was run, and no dtype was exercised.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The entry does not establish that any widened dtype compiles, runs,
or computes correctly on any board — it establishes what two files in one installed toolkit say, and
that they say different things. It does not establish that the doc comments are wrong: §3 gives the
reading under which they are right (a portable intersection), and that reading is itself unverified
because this book reads only the 950 backend in detail (RULES.md Art. 1 fences the other one out). It does
not establish that the eleven-type `ReduceMax` list is usable in practice — `0145` records a sibling
family routing around a vendor 64-bit path for verified defects, so breadth of declaration is
explicitly not being read as fitness. It does not establish that upstream's cast-to-FP32 policy is
wrong or wasteful; for `ReduceSum` the policy has a numerical justification this book carries at
`0397`, and for `ReduceMax` the question is open and recorded as `Q-950td-02`, not answered. It does
not establish the `SupportBytes<T, 8>()` dispatch behaves differently from the non-b64 path in any
respect other than being a different function. It does not cover `ReduceXorSum`, `Sum` or `Mean` (the
non-`Reduce`-prefixed siblings in the same directory), whose `c310` files carry their own, different
lists — `sum_c310_impl.h:82` and `mean_c310_impl.h:118` both say `half, float` — which is a fourth
vocabulary this entry notes and does not analyse. It does not establish the pattern restriction, which
is `0405`. BOARD is `family-claimed(unverified)`: the toolkit headers name an implementation family
(`c310`) and no board token. Nothing here is established for any 910-family board.
