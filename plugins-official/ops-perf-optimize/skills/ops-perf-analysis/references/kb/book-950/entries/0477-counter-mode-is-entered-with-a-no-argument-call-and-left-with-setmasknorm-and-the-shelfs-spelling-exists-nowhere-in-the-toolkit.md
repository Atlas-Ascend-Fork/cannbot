```
ID:        0477-counter-mode-is-entered-with-a-no-argument-call-and-left-with-setmasknorm-and-the-shelfs-spelling-exists-nowhere-in-the-toolkit
LABEL:     trap
LEVEL:     L5 (compute & numerics)
STRATUM:   corroborated — upstream's skills repo (one origin) plus the installed CANN toolchain at pin
           cann-9.0.0-beta.2 (independent origin: headers in the installed toolkit, STRATA S2). The
           two origins AGREE that a counter mask mode exists and is entered and left by paired calls,
           and DISAGREE on every spelling. Nothing measured, nothing compiled.
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/elementwise/vector_efficiency_design.md:21
           — "- **Counter 模式（入口）**：`SetMaskCount(dataSize)` 后一次 Vector API 调用覆盖全部数据，
           避免手动计算 `repeatTimes` 和 `tailSize`。" ; :106-110 —
           "// Counter 模式：SetMaskCount 后一次 API 调用 / SetMaskCount(dataSize); /
           Add(dst, src1, src2, dataSize);  // 自动处理主块+尾块，无需手动 mask /
           SetMaskMode(NORMAL);  // 完成后恢复 mask 模式" ; :162 —
           "2. **Counter 模式必须恢复 mask**：使用完 Counter 模式后，必须调用 `SetMaskMode(NORMAL)` 恢复，
           避免影响后续 Vector API。"
SOURCE:    /usr/local/Ascend/cann-9.0.0-beta.2/asc/include/interface/kernel_common.h:169-177 —
           "__aicore__ inline void SetMaskCount() / { / SetMaskCountImpl(); / } / /
           __aicore__ inline void SetMaskNorm() / { / SetMaskNormImpl(); / }"
SOURCE:    same toolkit, asc/impl/adv_api/detail/quantization/quant/ascend_quant_pre_impl.h:345,353,382-383
           — "SetMaskCount();" … "SetVectorMask<T, MaskMode::COUNTER>(0, splitSize);" …
           "SetMaskNorm(); / ResetMask();" (the shipped idiom, with a splitSize loop and a remainder
           between the second call and the last two)
INDEX:     none — nothing measured; see SOURCE. Re-derivable by file read (no device):
           grep -n 'SetMaskCount\|SetMaskNorm' /usr/local/Ascend/cann-9.0.0-beta.2/asc/include/interface/kernel_common.h
           grep -RIl 'SetMaskMode' /usr/local/Ascend/cann-9.0.0-beta.2/   # zero files
OVERTURN:  a `SetMaskMode(NORMAL)` or a one-argument `SetMaskCount(n)` that compiles for a DAV_3510
           target under some CANN pin — the spellings would then exist in a toolkit this book has not
           looked at, and the disagreement would be a version skew rather than an error. Equally: a
           counter-mode `Add` covering a `dataSize` larger than the shipped code's `splitSize` bound,
           in one call, would show the "one call covers all the data" claim holds unconditionally.
```

# 0477 · Counter mode is entered with a no-argument call and left with SetMaskNorm, and the shelf's spelling exists nowhere in the toolkit

## 1 · Claim
Upstream asserts that a Vector operator can remove the per-call scalar cost of computing `repeatTimes`
and `tailSize` by switching the mask unit into counter mode, after which a single Vector API call
covers the whole data length and handles the main block and the tail automatically. Upstream asserts
the entry call is `SetMaskCount(dataSize)` — taking the element count as an argument — and that the
mode must afterwards be restored with `SetMaskMode(NORMAL)`, stated twice, once in code and once as a
constraint. Against that stands a second, independent origin. The installed CANN toolchain at pin
`cann-9.0.0-beta.2` declares `SetMaskCount()` with **no parameters** and `SetMaskNorm()` as its
counterpart, and contains **no symbol named `SetMaskMode` anywhere**; its own shipped counter-mode
code is a five-call idiom — `SetMaskCount()` to switch the mode, then
`SetVectorMask<T, MaskMode::COUNTER>(0, count)` to supply the length, then the operation, then
`SetMaskNorm()`, then `ResetMask()`. The two origins agree the mechanism exists and disagree on every
call in it. Not established here which behaviour follows from either.

## 2 · The wrong branch this removes
Without this entry an agent adopting the shelf's recommendation copies its three lines. None of them
matches a declaration in the installed toolkit at this pin: `SetMaskCount` is declared with no
parameters, `SetMaskMode` is declared nowhere at all, and `Add(dst, src1, src2, dataSize)` in counter
mode is not how the length reaches the mask unit. Whether the toolchain rejects them at build time is
§4 arm 1 and is not established here — but if it does, that is the benign case, because a build error
is a fast teacher.

The dangerous branch is the partial fix. An agent that reaches for a plausible replacement, finds
`SetMaskNorm()` and uses it may satisfy the toolchain and still not have set the count: `SetMaskCount()` only switches the *mode*, and the count itself comes from
`SetVectorMask<T, MaskMode::COUNTER>(0, n)`. Omit that and the operation runs under whatever mask
register the previous code left behind. That produces wrong element counts, not a fault. And upstream's
own constraint list warns about exactly the mirror-image error — `Counter 模式后后续 API 结果异常` from
failing to restore — so the shelf has the *shape* of the hazard right and the *calls* wrong.

The second wrong branch is the scope of "one call covers everything". Upstream says
`一次 Vector API 调用覆盖全部数据`. The toolkit's own shipped counter-mode code does not do that: it
computes a `splitSize`, calls `SetVectorMask<T, MaskMode::COUNTER>(0, splitSize)`, loops
`calcCount / splitSize` times, then handles a remainder with a second `SetVectorMask` call. Whatever
bounds `splitSize` there — in that instance a temporary-buffer capacity — the shipped pattern is a
loop with a tail, which is the thing counter mode was said to remove.

## 3 · Ground / Source
The shelf's claim, `reference/elementwise/vector_efficiency_design.md:21`:

```
- **Counter 模式（入口）**：`SetMaskCount(dataSize)` 后一次 Vector API 调用覆盖全部数据，避免手动计算 `repeatTimes` 和 `tailSize`。
```

its reference code, `:106-110`:

```cpp
// Counter 模式：SetMaskCount 后一次 API 调用
SetMaskCount(dataSize);
Add(dst, src1, src2, dataSize);  // 自动处理主块+尾块，无需手动 mask
SetMaskMode(NORMAL);  // 完成后恢复 mask 模式
```

and the constraint that repeats the second spelling, `:162`:

```
2. **Counter 模式必须恢复 mask**：使用完 Counter 模式后，必须调用 `SetMaskMode(NORMAL)` 恢复，避免影响后续 Vector API。
```

The shelf also hedges the mechanism's availability at `:160`: `**Counter 模式依赖硬件支持**：仅部分
Vector API 支持 Counter 模式，使用前需确认 API 文档` — only some Vector APIs support it, check the
documentation first. That hedge is the one instruction in the section that, followed, would have caught
the rest.

**The second origin.** `asc/include/interface/kernel_common.h:169-177` in the installed toolkit:

```cpp
__aicore__ inline void SetMaskCount()
{
    SetMaskCountImpl();
}

__aicore__ inline void SetMaskNorm()
{
    SetMaskNormImpl();
}
```

Neither takes an argument, and the restore is `SetMaskNorm`, not `SetMaskMode`. A search for
`SetMaskMode` across the entire installed toolkit — every file, not only headers — returns **zero
files**. So the restore call the shelf names twice is not a differently-spelled variant of something;
it is absent.

Where the count actually comes from, `asc/impl/adv_api/detail/quantization/quant/ascend_quant_pre_impl.h`,
which is the toolkit's own counter-mode user. `:345-363`, verbatim:

```cpp
    SetMaskCount();
    LocalTensor<half> tmpBuffer = sharedTmpBuffer.ReinterpretCast<half>();
    if constexpr(config.workLocalSize != 0 && config.calcCount != 0) {
        constexpr uint32_t splitSize = config.workLocalSize / sizeof(half) / ONE_BLK_SIZE * ONE_BLK_SIZE;
        ASCENDC_ASSERT((splitSize != 0), {
            KERNEL_LOG(KERNEL_ERROR, "splitSize should not be 0!");
        });
        constexpr uint32_t loopCount = config.calcCount / splitSize;
        SetVectorMask<T, MaskMode::COUNTER>(0, splitSize);
        for (uint32_t i = 0; i < loopCount; ++i) {
            AscendQuantIntrinsicsImpl(dstTensor[splitSize * i], srcTensor[splitSize * i],
                tmpBuffer, static_cast<half>(scale), static_cast<half>(offset));
        }
        if constexpr(config.calcCount % splitSize > 0) {
            SetVectorMask<T, MaskMode::COUNTER>(0, config.calcCount % splitSize);
            AscendQuantIntrinsicsImpl(dstTensor[splitSize * loopCount], srcTensor[splitSize * loopCount],
                tmpBuffer, static_cast<half>(scale), static_cast<half>(offset));
        }
    }
```

and the exit, `:382-383`:

```cpp
    SetMaskNorm();
    ResetMask();
```

So the shipped idiom has **five** distinct calls where the shelf has three — mode in, count set,
operation, mode out, mask reset — the count is supplied by a call the shelf never mentions, the exit
has a `ResetMask()` the shelf never mentions, and the loop-plus-remainder structure the shelf says
counter mode removes is present verbatim in the toolkit's own use of it. Registered as
`C-950fin-021`.

**What is corroborated and what is not.** Both origins agree that a counter mask mode exists, that it
is entered and left by paired calls, and that its purpose is to stop the caller computing repeat counts
per call — that is a genuine second origin for the *mechanism*, which is why this entry is
`corroborated`. Neither origin measures anything: the shelf's `Scalar 开销降低 30-50%` is unscoped
(`0479`) and the header proves only that the symbols exist. The disagreement about spellings is
recorded, not adjudicated — the header is the shipped toolchain at a stated pin, which is strong
evidence about *this* installation and does not establish what the shelf's authors compiled against.

## 4 · Procedure
Two arms need only a compiler; two need a named 950 board (950PR or 950DT). None is run in this phase.

**Arm 1 — the symbols (compile-only).** Under the stated toolkit pin, for a DAV_3510 target, attempt
to compile each of: `SetMaskCount(1024);`, `SetMaskMode(NORMAL);`, `SetMaskCount(); SetMaskNorm();`.
Record which compile and the verbatim diagnostics for those that do not. This is the arm that decides
whether `C-950fin-021` is an error or a version skew, and the diagnostic text is the datum, not the
pass/fail (`0460`).

**Arm 2 — the count's source (device).** Fill `dst` with a sentinel. Run
`SetMaskCount(); Add(dst, src1, src2, ...);` **without** an intervening `SetVectorMask`, at a
`dataSize` the previous code's mask does not cover, and report how many elements of `dst` were written.
Then repeat with `SetVectorMask<T, MaskMode::COUNTER>(0, dataSize)` inserted. The prediction from §2 is
that the first writes a count set by whatever ran before it. A checker that only compared the covered
prefix would see agreement in both cases; this one counts written elements.

**Arm 3 — "one call covers all the data" (device).** Sweep `dataSize` from one repeat up to and beyond
any bound counter mode imposes, with a single `SetVectorMask<T, MaskMode::COUNTER>(0, dataSize)` and
one `Add`, and report the largest `dataSize` fully covered by one call. If there is no bound, the
shelf's headline holds and the toolkit's `splitSize` loop is a temporary-buffer constraint of that one
API rather than a counter-mode limit. If there is a bound, the headline is wrong and the bound is the
number nobody has written down.

**Arm 4 — the restore, retained because it is expected to bite (device).** Run a counter-mode block
followed by a normal-mode Vector call, with and without `SetMaskNorm()` between them, and compare both
against a reference. Upstream's `:162` predicts the un-restored form corrupts the following call. This
is the one claim in the section whose *substance* both origins support, and confirming it separates
"the shelf named the wrong function" from "the shelf described the wrong hazard".

Refuses to assume: that a free die stays free, or that a die may be substituted; that a compile failure
means what its message says (arm 1 records the message); that a correct prefix means a correct count
(arm 2 counts written elements against a sentinel); that this toolkit pin is the pin the shelf was
written against — the pin is stated in every result and a different pin would be a different
experiment; that `Add` supports counter mode at all, which upstream's own `:160` says must be checked
per API first.

## 5 · Checker — acceptance declared before the run
Verdict `symbol_exists(spelling)` from arm 1, boolean per spelling, with diagnostics. Acceptance for
this entry as written: `SetMaskCount()` and `SetMaskNorm()` exist; `SetMaskCount(n)` and
`SetMaskMode(NORMAL)` do not. The OVERTURN fires iff either of the latter two compiles.

Verdict `written_elements(with_setvectormask)` from arm 2, an integer per configuration. Acceptance
for §2's mechanism: without `SetVectorMask` the count differs from `dataSize`; with it, equals.

Verdict `max_single_call_count` from arm 3, an integer or `unbounded`.

Verdict `restore_required` from arm 4, boolean.

The exit code is not the verdict: a counter-mode call that covers the wrong number of elements exits 0
and produces a correct-looking prefix. Guards: (1) arm 2 pre-fills the whole destination with a
sentinel and reports the count of *changed* elements, and a run that compared only the first `dataSize`
elements is reported `untestable` — a checker that reads only the range it expects is the known blind
species and would score a short write as a pass; (2) **the input that makes this checker go red**: the
fully-correct five-call idiom at a `dataSize` of exactly one repeat, where every mode and every mask
setting must produce the same answer — if the configurations differ there, the harness is not isolating
the mask state and every count in arm 2 is an artifact; (3) no result is reported without the toolkit
pin, the target architecture, the compiler command, the API under test and the preceding mask state.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement, and no compiler was invoked.
Both origins were read at drafting time: the shelf's three passages, the toolkit's two declarations,
the toolkit's own five-call usage, and the zero-file result for `SetMaskMode` across the whole installed
tree. The observation that the shipped idiom has five calls where the shelf has three, and that the
toolkit's own counter-mode user contains the loop-and-remainder structure the shelf says counter mode
removes, are readings of the two origins, not observations of a build. **`SetMaskCount(dataSize)` and
`SetMaskMode(NORMAL)` are recorded here as matching no symbol in this installation at this pin. Whether
they compile is not established — that is arm 1, and it has not been run.**

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured, compiled or run. The entry does not establish that the shelf's code fails to
compile; it establishes that its two call spellings match no declaration in the installed toolkit at
pin `cann-9.0.0-beta.2`, which is a file-read result and not a build result. It does not establish that
the toolkit's spellings are the only ones — an older or newer CANN could differ, and the shelf's
authors may have compiled against one. It does not establish that `Add` supports counter mode, nor
which Vector APIs do; upstream says only some do and names none. It does not establish any scalar-cost
saving: the `30-50%` figure is unscoped and is `0479`'s subject, and nothing in the header speaks to
performance at all. It does not establish `splitSize`'s bound, which in the toolkit's quantisation code
is a temporary-buffer capacity of that API and not a property of counter mode. It says nothing about
`MaskMode::NORMAL`, `SetVectorMask`'s bit-mode overloads, or the interaction with `MASK_PLACEHOLDER`.
The corroboration is of the mechanism only, and the two origins disagree on every call
(`C-950fin-021`). No board token appears in the shelf's passage; the header's counter-mode declarations
are not architecture-gated, so BOARD is `family-claimed(unverified)`; §4 names 950PR/950DT and a
DAV_3510 target only as where our run would happen. Nothing here is established for any 910-family
board.
