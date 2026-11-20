```
ID:        0255-updatemask-decrements-its-argument-by-reference-so-a-manual-decrement-doubles-the-step
LABEL:     trap
LEVEL:     L5 (compute & numerics)
STRATUM:   harvested — one upstream origin (ops/ascendc-regbase-best-practice); the signature it
           quotes was not checked against the installed headers. Nothing was compiled.
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-regbase-best-practice/references/paradigms/common/vf-programming-rules.md:36-51
           — "template <typename T> __simd_callee__ inline MaskReg UpdateMask(uint32_t& scalarValue);"
           … "**关键**：`scalarValue` 是引用传递，内部自动递减 VL_T（float:64，half:128）。**调用后
           不可再手动递减**。" with the worked counter-example
           "// remaining 已被自动递减，不可再写 remaining -= 64  // ❌ 会变成每轮减 2×VL"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a 950 board on which `UpdateMask<T>` leaves its argument unchanged — the decrement would
           then be the caller's job and every loop written to this rule under-processes its tail.
```

# 0255 · `UpdateMask` decrements its argument by reference, so a manual decrement doubles the step

## 1 · Claim
Upstream asserts that `AscendC::Reg::UpdateMask<T>` takes its element-count argument by non-const
reference (`uint32_t& scalarValue`) and decrements it internally by `VL_T` — 64 for `float`, 128 for
`half`. Upstream asserts the operative prohibition: after calling it, the caller must not decrement the
same variable again, and doing so subtracts `2 × VL` per iteration. Not established here: nothing was
compiled, and the signature was not checked against the installed toolkit headers.

## 2 · The wrong branch this removes
A function that returns a mask and silently mutates its argument is an unusual interface, and every
instinct an agent has about loop bookkeeping points the wrong way. The natural VF loop is: compute the
mask for this iteration, do the work, advance the remaining count. Three of those four steps are the
agent's job and the fourth has already been done for it.

The consequence is precise and asymmetric. With a double decrement, `remaining` reaches zero after half
the iterations. What happens then depends on how the loop is bounded — and it is bounded by
`repeatTime`, computed independently as `ceil(totalElems / VL)` (0253's template), not by `remaining`.
So the loop keeps running with `remaining` already at or below zero, and `UpdateMask` is being asked for
a mask on a count that has underflowed. `remaining` is `uint32_t`: subtracting past zero wraps to a
value near 2³², so the mask for the back half of the loop is computed from a huge count and will most
plausibly come back **full** — meaning the tail iterations process a full register of elements each,
writing past the intended extent.

That is the shape worth carrying: the visible symptom is not "half the data was processed". It is
correct output for the first half of every tile and out-of-bounds writes at the end — which reads as a
tail-handling bug or a stride error, and sends the author into the loop arithmetic rather than to the
call.

The regbase pitfall material names this diagnosis loop directly: "Assuming small-shape success proves
correctness … small aligned cases hide tail handling, partial-tile masking" (`common_traps.md` §3). A
shape that is exactly one register wide runs one iteration and cannot exhibit the bug at all.

The inverse branch also exists and is cheaper: an agent that knows the decrement is automatic but writes
its own loop counter separately, never passing the same variable twice, gets correct behaviour and has
simply not used the interface as designed. That is fine. The trap is specifically the *combination* of
using the reference form and treating it as a value.

## 3 · Ground / Source
`vf-programming-rules.md:36-51`, the section in full — signature, rule, and counter-example together,
because the counter-example is what makes the rule stick:

> ## 3 UpdateMask
>
> ```cpp
> template <typename T>
> __simd_callee__ inline MaskReg UpdateMask(uint32_t& scalarValue);
> ```
>
> **关键**：`scalarValue` 是引用传递，内部自动递减 VL_T（float:64，half:128）。**调用后不可再手动递减**。
>
> ```cpp
> uint32_t remaining = static_cast<uint32_t>(totalElems);
> for (uint16_t i = 0; i < repeatTime; ++i) {
>     maskReg = AscendC::Reg::UpdateMask<float>(remaining);
>     // remaining 已被自动递减，不可再写 remaining -= 64  // ❌ 会变成每轮减 2×VL
> }
> ```

Three things about this passage carry weight beyond the rule.

The signature is quoted rather than described — `uint32_t& scalarValue` — so the reference is visible in
the source material rather than being something a reader has to infer from behaviour. That is the only
reason this trap is discoverable by reading; a doc that said "UpdateMask updates the count" would not
be.

`VL_T` is given as a dtype-dependent quantity with both values named (float 64, half 128), which is the
same pair the file's type table derives from VL = 256 B at `:9` (0219). So the decrement is *the lane
count*, not a fixed number, and an agent that hardcodes `remaining -= 64` is making two errors at once —
the double decrement and the wrong constant for any dtype other than fp32 (0252).

The prohibition is stated in the imperative and the counter-example is written as a comment *inside* the
loop, at exactly the line where the wrong code would go. That placement is the reason it transmits: a
reader copying the loop copies the warning.

The interface's own consumers are visible in the same file. `:120-127`, the canonical `__simd_vf__`
example, uses it correctly:

```cpp
    uint32_t remaining = totalElems;
    for (uint16_t i = 0; i < repeatTime; ++i) {
        int32_t off = static_cast<int32_t>(i) * static_cast<int32_t>(VL);
        mask = AscendC::Reg::UpdateMask<T>(remaining);
        AscendC::Reg::LoadAlign(aReg, src + off);
        // ... 计算
        AscendC::Reg::StoreAlign(dst + off, aReg, mask);
    }
```

Note that the *offset* is computed from `i`, not from `remaining` — the two counters are independent, and
that separation is what makes the loop survivable. `remaining` drives only the mask; `i` drives the
address. An agent that tried to derive the offset from `remaining` would couple them and the double
decrement would then also corrupt addressing.

`UpdateMask` appears in the whitelist's VF-safe "Mask and copy helpers" family
(`regbase_api_whitelist.md:82`) alongside `MaskReg`, `CreateMask`, `Pack`, `UnPack`, `Move` and
`LocalMemBar`, with the guardrail at `:110`: "Re-check mask creation and update rules before using
`CreateMask`, `UpdateMask`, `Pack`, or `UnPack` inside a VF helper." So the whitelist flags this family
as one to re-read rather than assume — consistent with this entry, and one origin with it.

What upstream does not supply: what `UpdateMask` returns when the count is already 0, what it does on
underflow, and whether the decrement saturates. Those are exactly the states the double-decrement bug
drives it into, and §4 has to probe them directly rather than reason about them.

## 4 · Procedure
Runnable later on `950PR`. The claim is about a side effect, so the procedure observes the argument, not
the mask.

Arm A — the signature, file read only, no device. Locate `UpdateMask` in the installed toolkit and record
its declaration verbatim:

```bash
grep -RIn "UpdateMask" "$ASCEND_HOME_PATH/include/ascendc/basic_api/interface/reg_compute/"
```

`grep -R`, not `-r` — these trees are symlink farms. The one thing to record is whether the parameter is
`uint32_t&`. If it is by value, this entry is overturned by a file read and no board is needed.

Arm B — the side effect, observed directly. Inside a `__simd_vf__`, store `remaining` to UB before and
after a single `UpdateMask<float>` call on a count of 200, and again for `UpdateMask<half>`:

```cpp
__simd_vf__ inline void MaskProbeVf(__ubuf__ uint32_t* out)
{
    AscendC::Reg::MaskReg m;
    uint32_t remaining = 200;
    out[0] = remaining;
    m = AscendC::Reg::UpdateMask<float>(remaining);
    out[1] = remaining;                    // expect 136 = 200 - 64
    uint32_t remainingH = 200;
    out[2] = remainingH;
    m = AscendC::Reg::UpdateMask<half>(remainingH);
    out[3] = remainingH;                   // expect 72 = 200 - 128
}
```

Two dtypes, because a single one cannot distinguish "it decrements by VL_T" from "it decrements by 64".

Arm C — the underflow behaviour, which upstream does not state and which is where the bug actually
lands. Call `UpdateMask<float>` repeatedly on an initial count of 100 and record `remaining` after each
call: 100 → 36 → ? The third call is on a count smaller than VL, and the fourth is at or past zero.
Record whether it saturates at 0 or wraps, and record the mask's effective lane count at each step by
storing a full register through it into a poisoned buffer.

Arm D — the bug reproduced end to end, which is what makes §2's failure-shape claim checkable rather
than asserted. Build one elementwise VF twice at `float` over 200 elements: once correctly, once with
`remaining -= 64` added after the `UpdateMask` call. Compare both against a host reference and record
*where* the second diverges and whether it writes beyond the intended extent (poison the destination
past the expected end and count changed words). §2 predicts correct output early, out-of-bounds writes
late; either half being wrong corrects this entry.

Device selection is explicit for Arms B-D: the operator names the device index, the probe prints it back
with `compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared
machine, ≤4 dies), and no die is substituted for another. All dtypes and both builds of one comparison
run on one named die in one session.

## 5 · Checker — acceptance declared before the run
Verdict variable `decrement_is_vl_t`, from Arm B, requiring both dtypes in one predicate: pass iff
`out[1] == 136` **and** `out[3] == 72`. Both, because the entry's claim is that the step is `VL_T` rather
than a constant, and a fp32-only check passes under either hypothesis. Process exit code is not the
verdict.

Named alternatives, declared now so none can be reinterpreted afterwards. `out[1] == 200` overturns the
entry — the parameter is effectively by value and the caller owns the decrement. `out[1] == 136` with
`out[3] == 136` means the step is a constant 64 rather than `VL_T`, which corrects the entry in place and
matters more than it sounds: it would mean a `half` loop under-decrements and the mask stays full too
long.

`underflow_behaviour` (Arm C) — reported, not gated: the sequence of `remaining` values and the observed
lane count at each step, including past zero. This is the state the bug drives the interface into and
upstream documents none of it; a saturating implementation and a wrapping one produce very different
symptoms and the delivered skill needs to know which.

`bug_writes_out_of_bounds` (Arm D) — pass iff the double-decrement build's poison-word count beyond the
intended extent is non-zero. A count of zero does **not** fail this entry; it corrects §2's failure-shape
claim from out-of-bounds writes to dropped work, which changes what a reviewer looks for and is worth
recording either way.

The positive fixture, declared before the run: Arm B must be shown to go red on a known answer — call
`UpdateMask<float>` on an initial count of 64 exactly, where the result must be 0. If the probe reports
136 or 64 there, it is reading a stale `out[1]` or the store is not ordered after the call, and every
value it produced is void. A second fixture for Arm D: the *correct* build must match the host reference
exactly and show zero poison words. If it does not, the harness's reference or extent is wrong and the
double-decrement result attributes nothing. Without both, the checker reads only "a number changed",
which is the known blind species.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No kernel was compiled, no
`UpdateMask` was called, and no header was searched for its declaration — Arm A is a file read and
remains open. The signature in §3 is upstream's transcription of it, not a reading of the installed
toolkit.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled. The entry does not establish the signature, the decrement, or its magnitude — Arm
A is a file read that would settle the first, and it was not performed. There is **no second origin**:
one upstream file, and unlike 0244 and 0246 the installed headers were not consulted, so nothing
corroborates the reference parameter. It does not establish underflow behaviour, saturation, or what
`UpdateMask` returns on a zero count — upstream states none of it, and those are precisely the states the
trap produces; Arm C is the only thing here that would tell them apart. It does not establish the
failure shape claimed in §2: correct-then-out-of-bounds is reasoning from `uint32_t` wraparound plus a
`repeatTime`-bounded loop, and Arm D is what would confirm or replace it. It says nothing about
`CreateMask`, `Pack` or `UnPack`, the sibling mask helpers the whitelist groups with `UpdateMask` and
flags as needing a re-read; each may or may not share this interface style. It says nothing about
`MERGING` versus `ZEROING` mask semantics, which is a different property of the mask than its lane count.
BOARD is `family-claimed(unverified)` — the file names no board token this book recognises, the material
is arch35-generic regbase, and none was contacted. Finally, the `VL_T` values quoted (64 / 128) depend on
VL being 256 **bytes**, which 0219 has not verified and 0273 records one upstream file labelling in bits;
if that resolves the other way, both numbers here move by 8×.
