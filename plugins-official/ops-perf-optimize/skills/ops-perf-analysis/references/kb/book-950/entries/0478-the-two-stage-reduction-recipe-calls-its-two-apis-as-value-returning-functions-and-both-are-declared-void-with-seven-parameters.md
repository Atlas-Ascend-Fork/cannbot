```
ID:        0478-the-two-stage-reduction-recipe-calls-its-two-apis-as-value-returning-functions-and-both-are-declared-void-with-seven-parameters
LABEL:     trap
LEVEL:     L5 (compute & numerics)
STRATUM:   corroborated — upstream's skills repo (one origin) plus the installed CANN toolchain at pin
           cann-9.0.0-beta.2 (independent origin: headers in the installed toolkit, STRATA S2). The
           two origins agree both APIs exist; they disagree on the call shape. Nothing measured,
           nothing compiled.
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/elementwise/vector_efficiency_design.md:97-100
           — "// 高延迟单条指令 / float sum = WholeReduceSum(src, dataSize);  // 延迟高，大数据量时明显"
           ; :135-145 — "// 阶段 1：BlockReduceSum，每 blockSize 个元素产生一个部分和 /
           for (uint32_t i = 0; i < numBlocks; i++) { / blockSums[i] = BlockReduceSum(src + i *
           blockSize, blockSize); / } / PipeBarrier<PIPE_V>(); / / // 阶段 2：WholeReduceSum 汇总部分和 /
           float totalSum = WholeReduceSum(blockSums, numBlocks);" ; :11 —
           "| 归约指令延迟 | WholeReduceSum 单条高延迟 | BlockReduceSum + WholeReduceSum 组合 |
           延迟降低 20-40% |"
SOURCE:    /usr/local/Ascend/cann-9.0.0-beta.2/asc/include/interface/kernel_operator_vec_reduce_intf.h:46-49
           — "template <typename T, bool isSetMask = true> / __aicore__ inline void BlockReduceSum(
           const LocalTensor<T>& dst, const LocalTensor<T>& src, / const int32_t repeatTime,
           const int32_t mask, const int32_t dstRepStride, const int32_t srcBlkStride, /
           const int32_t srcRepStride);" ; :143-153 — the two `WholeReduceSum` declarations under an architecture gate, both
           `void`, both taking dst and src `LocalTensor`s plus five integer parameters
INDEX:     none — nothing measured; see SOURCE. Re-derivable by file read (no device):
           grep -n 'void BlockReduceSum\|void WholeReduceSum' /usr/local/Ascend/cann-9.0.0-beta.2/asc/include/interface/kernel_operator_vec_reduce_intf.h
OVERTURN:  a `float sum = WholeReduceSum(src, n);` that compiles for a DAV_3510 target under some CANN
           pin — a value-returning two-argument overload would then exist in a toolkit this book has
           not looked at. Equally, and independently: a measured `BlockReduceSum + WholeReduceSum`
           pair on a named 950 board that is NOT faster than a single `WholeReduceSum` over the same
           data beyond the variance floor kills the 20-40% latency claim, which stands or falls
           separately from the call shape.
```

# 0478 · The two-stage reduction recipe calls its two APIs as value-returning functions, and both are declared void with seven parameters

## 1 · Claim
Upstream asserts that a single `WholeReduceSum` over a large buffer is a high-latency instruction, and
that replacing it with a two-stage combination — `BlockReduceSum` producing one partial sum per block,
then `WholeReduceSum` over the partial sums — reduces reduction latency by 20-40%. Upstream's
reference code for both the naive and the optimised form calls the two APIs as **value-returning
functions taking a pointer and a length**: `float sum = WholeReduceSum(src, dataSize);` and
`blockSums[i] = BlockReduceSum(src + i * blockSize, blockSize);`. Against that stands a second,
independent origin: the installed CANN toolchain at pin `cann-9.0.0-beta.2` declares both as
`void`-returning templates taking a destination `LocalTensor`, a source `LocalTensor`, and five
integer parameters (repeat count, mask, and three strides). Not established here; the latency claim
and the call shape are separate and are kept separate below.

## 2 · The wrong branch this removes
Without this entry an agent adopting the two-stage reduction copies the reference loop. The loop is the
problem, not only the signature: `for (i = 0; i < numBlocks; i++) blockSums[i] = BlockReduceSum(...)`
issues one instruction per block, in scalar sequence, on the host-visible loop counter. The real API
takes a `repeatTime` parameter and does all the blocks in one call. So the printed code, if it were
translatable literally, would replace one high-latency instruction with `numBlocks` low-latency ones
issued serially — the opposite of the optimisation, and precisely the scalar-loop overhead the same
document's *first* mechanism (counter mode, `0477`) exists to remove. The recipe and the recipe's own
sibling mechanism disagree in the same file.

The normal checks do not catch it early because the mismatch surfaces at build time — after the
design is written. An agent that plans a kernel around "two-stage reduction, one call per block" has committed a
memory layout (`blockSums` as a scalar array), a synchronisation point (`PipeBarrier<PIPE_V>()` between
the stages), and a loop structure, and only then meets the API's actual shape. The
`PipeBarrier` in particular is a real obligation in the correct form too, so the wrong design contains
a right-looking piece.

The second wrong branch is the one this entry deliberately does **not** close: taking "the code does
not match the headers" as a refutation of the 20-40% figure. It is not. The two-stage decomposition is
a real technique with a real mechanism, and this book carries a related instance from another family
(`0030`: the hardware tree reduction replaces the scalar accumulate loop). What the mismatch shows is
that the printed code cannot be the code that produced any measurement — so the figure has no
demonstrated provenance, which is a different and weaker statement than "the figure is wrong".

## 3 · Ground / Source
The naive form, `reference/elementwise/vector_efficiency_design.md:97` heading
(`**归约反例 — 单一 WholeReduceSum：**`) and `:99-100` body:

```cpp
// 高延迟单条指令
float sum = WholeReduceSum(src, dataSize);  // 延迟高，大数据量时明显
```

the optimised form, `:135-145`:

```cpp
// 两阶段归约：先 BlockReduceSum 分块，再 WholeReduceSum 汇总
// 阶段 1：BlockReduceSum，每 blockSize 个元素产生一个部分和
for (uint32_t i = 0; i < numBlocks; i++) {
    blockSums[i] = BlockReduceSum(src + i * blockSize, blockSize);
}
PipeBarrier<PIPE_V>();

// 阶段 2：WholeReduceSum 汇总部分和
float totalSum = WholeReduceSum(blockSums, numBlocks);
```

and the claim it carries, `:11`:

```
| 归约指令延迟 | WholeReduceSum 单条高延迟 | BlockReduceSum + WholeReduceSum 组合 | 延迟降低 20-40% |
```

**The second origin.** `asc/include/interface/kernel_operator_vec_reduce_intf.h:46-49`:

```cpp
template <typename T, bool isSetMask = true>
__aicore__ inline void BlockReduceSum(const LocalTensor<T>& dst, const LocalTensor<T>& src,
    const int32_t repeatTime, const int32_t mask, const int32_t dstRepStride, const int32_t srcBlkStride,
    const int32_t srcRepStride);
```

Seven parameters, `void` return, `LocalTensor` operands, and a `repeatTime` that makes the caller's
loop unnecessary. `WholeReduceSum` is declared four times in the same header (bit-mask and count-mask
overloads, each under an architecture gate — see `0480`), all `void`, all with dst and src
`LocalTensor`s plus five integers. No overload of either API takes a raw pointer and a length, and none
returns a value.

Three consequences follow from the declaration and are not in the shelf's text.

`dst` is a `LocalTensor`, not a scalar. Both APIs write **into UB**, one partial sum per repeat, so
`blockSums` is a tensor and `totalSum` is a tensor element — which means the "single high-latency
instruction" and the "combination" both leave their result on-chip, and reading it into a scalar is a
further step the shelf's code hides behind an assignment.

`repeatTime` is capped. The implementation asserts `ASCENDC_CHECK_VALUE_RANGE(repeatTime, 0, 255, ...)`
(`asc/impl/basic_api/kernel_operator_vec_reduce_intf_impl.h:342`, `:503`), so one call covers at most
255 repeats and a larger reduction needs a loop anyway — just a loop over 255-repeat calls rather than
over single blocks. The shelf's `blockSize ∈ {64, 128}` guidance (`:60`) and this cap together bound
what one call can reduce, and neither document states the product.

The `PipeBarrier<PIPE_V>()` between the stages is the one line of the recipe that survives contact with
the real API: stage 2 reads what stage 1 wrote to UB, both on the vector pipe, and the family's own
sibling shelf forbids using `PipeBarrier` where a hard event exists (`0464`) — for a same-pipe
dependency `PIPE_V` is the right instrument.

Registered as `C-950fin-022`. This is the second call-shape mismatch in one 203-line document, the
first being `0477`'s; both were found by comparing the same file against the same installed toolkit.

## 4 · Procedure
Two arms need only a compiler; two need a named 950 board (950PR or 950DT). None is run in this phase.

**Arm 1 — the call shape (compile-only).** Under the stated toolkit pin, for a DAV_3510 target,
attempt to compile the shelf's two statements verbatim, and the header-shaped equivalents. Record which
compile and the verbatim diagnostics for those that do not. As in `0460`, the diagnostic text is the
datum: a message about "no matching function" settles `C-950fin-022`; a message about something else
means the mismatch is not what §3 reads it as.

**Arm 2 — the latency claim, which stands separately (device).** Three builds reducing the same buffer
of `N ∈ {2^10 … 2^20}` FP32 elements: (a) a single `WholeReduceSum` sequence, (b) `BlockReduceSum` at
`blockSize ∈ {64, 128}` followed by `WholeReduceSum`, (c) the same as (b) with the intermediate
`PipeBarrier<PIPE_V>()` removed, as a correctness probe. Report `aiv_time`, the vector-pipe utilisation,
and elementwise agreement against an FP64 reference. This is where `延迟降低 20-40%` acquires a case,
a shape, a dtype, a board and a tool for the first time.

**Arm 3 — the repeat cap (device).** Sweep the reduction length past `255 × blockSize` and record where
one call stops sufficing and what the implementation does at `repeatTime = 256` — assert, silent
truncation, or wraparound. The 255 bound is in the shipped implementation and in no shelf document.

**Arm 4 — the scalar-loop form, retained because it may not bite (device).** Build the shelf's
structure as closely as the API permits — one `BlockReduceSum` call per block with `repeatTime = 1`,
in a loop — and compare against (b). §2 predicts it is slower than both (a) and (b). If it is not, the
loop form is not the pathology this entry claims and §7 records that.

Refuses to assume: that a free die stays free, or that a die may be substituted; that a compile failure
means what its message says; that the two stages' result is a scalar (each arm reports where the result
lives and how it is read out); that `repeatTime` may exceed 255 (arm 3 tests it rather than trusting
the assert); that latency and wall time are the same quantity — both are reported, and the shelf's word
is `延迟`; that this toolkit pin is the pin the shelf was written against.

## 5 · Checker — acceptance declared before the run
Verdict `shelf_code_compiles` from arm 1, boolean per statement, with diagnostics. Acceptance for
`C-950fin-022` as read: neither shelf statement compiles and both header-shaped forms do. The
OVERTURN's first half fires iff a value-returning two-argument form compiles.

Verdict `latency_ratio(N, blockSize) = t(b) / t(a)`, declared before the run with its variance floor.
Acceptance for the shelf's figure: `latency_ratio ∈ [0.60, 0.80]` somewhere in the sweep — that is
what "20-40% reduction" means, and it is written down now so that a 5% improvement cannot later be
reported as supporting it. `latency_ratio ≥ 1 − floor` everywhere is the OVERTURN's second half.

Verdict `repeat_cap_behaviour` from arm 3 ∈ {`assert`, `truncate`, `wrap`, `works`}.

Verdict `loop_form_ratio = t(arm 4) / t(b)`.

**The two verdicts are independent and are reported as such.** A failed arm 1 does not license any
statement about arm 2, and a successful arm 2 does not repair the printed code.

The exit code is not the verdict: build (c), with the barrier removed, is expected to produce wrong
sums while exiting 0. Guards: (1) every build compares its reduction result against an FP64 reference
computed from the same inputs, and a build reported without that comparison is `untestable` — a
latency table over three builds, one of which is silently wrong, is worse than no table; (2) **the
input that makes this checker go red**: `N` equal to exactly one block, where (a) and (b) reduce the
same data with the same instruction count and must measure the same within the floor — if they differ
there, the two builds differ in more than the decomposition and every ratio in the sweep is an
artifact; (3) no point is reported without `N`, `blockSize`, dtype, the toolkit pin, the compiler
command, the floor and the metric name.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement, and no compiler was invoked.
Both origins were read at drafting time: the shelf's two code blocks and its headline row, and the
toolkit's `BlockReduceSum` and `WholeReduceSum` declarations with the `repeatTime` range assert. The
observations that the shelf's loop issues one instruction per block where the API takes a repeat count,
that both APIs write into UB rather than returning a scalar, and that `repeatTime` is capped at 255 in
the shipped implementation, are readings of the two origins, not observations of a build. **The shelf's
two statements are recorded here as matching no declaration in this installation at this pin; whether
they compile is arm 1, and it has not been run.**

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured, compiled or run. The entry does not establish that the shelf's code fails to
compile — that is a build result and none was produced; it establishes that the call shapes match no
declaration in the installed toolkit at pin `cann-9.0.0-beta.2`. It does not establish that the
20-40% latency reduction is wrong: that figure stands or falls on arm 2, and nothing about the printed
code's shape bears on whether the two-stage decomposition is faster. What the mismatch does establish
is that the printed code cannot be the code any such measurement came from, so the figure has no
demonstrated provenance — which is weaker than a refutation and is `0479`'s subject. It does not
establish the 255 repeat cap as a hardware limit rather than a software assert. It does not establish
`blockSize ∈ {64, 128}` as correct or as required. It does not cover `BlockReduceMax`, `PairReduceSum`,
`ReduceSum` (the advanced API, `0405`/`0406`'s subject) or the reg-compute reduce family, all of which
have different shapes. It does not speak to the dtype-widening overload the 950 branch of the same
header carries (`0480`). No board token appears in the shelf's passage; the `BlockReduceSum`
declaration is not architecture-gated, so BOARD is `family-claimed(unverified)`; §4 names 950PR/950DT
and a DAV_3510 target only as where our run would happen. Nothing here is established for any
910-family board.
