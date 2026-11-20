```
ID:        0254-a-vf-body-obeys-seven-hard-constraints-that-are-not-style-preferences
LABEL:     boundary
LEVEL:     L8 (toolchain & build)
STRATUM:   harvested — one upstream origin (ops/ascendc-regbase-best-practice). Upstream calls them
           硬约束 (hard constraints) but names no enforcement mechanism for any of the seven;
           nothing was compiled.
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-regbase-best-practice/references/paradigms/common/vf-programming-rules.md:134-142
           — "## 9 VF 7 条硬约束 / 1. **for 循环必须从 0 开始** / 2. **VF 内最多 4 层 for** /
           3. **循环控制变量必须是 `uint16_t`** / 4. **VF 内禁止数组** / 5. **VF 内禁止访问类的"对象级"
           成员变量**（在 `asc_vf_call` 调用侧提取为临时变量/参数传入）/ 6. **VF 内禁止运行时 `if/else`**
           （用 `if constexpr` 代替）/ 7. **使用 `asc_vf_call` 启动 SIMD VF 函数**"
SOURCE:    same file:144-150 — "## 10 `__simd_vf__` 函数约束 / - C 函数格式，**不能是类成员函数** /
           - **不能引用外部模板**（如 `Reducer::identity` 需作为参数传入）/ - 支持模板参数 /
           - 支持内部 `if constexpr` / - `asc_vf_call` 显式传递所有模板参数"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a VF that compiles and produces correct output while violating any one of the seven —
           a loop starting at 1, a five-deep nest, an `int32_t` induction variable, a local array,
           or a runtime `if/else`. Each is independently falsifiable and one suffices for that row.
```

# 0254 · A VF body obeys seven hard constraints that are not style preferences

## 1 · Claim
Upstream asserts seven 硬约束 on the body of a `__simd_vf__` function: `for` loops must start at 0; at
most four levels of `for` nesting; the loop control variable must be `uint16_t`; arrays are forbidden;
object-level class member variables may not be accessed (they must be extracted at the `asc_vf_call`
site and passed in); runtime `if/else` is forbidden and `if constexpr` must be used instead; and a SIMD
VF is launched via `asc_vf_call`. Upstream asserts five further constraints on the function's form: it
must be a C-style function and cannot be a class member; it cannot reference external templates
(upstream's example: `Reducer::identity` must be passed as a parameter); template parameters are
supported; internal `if constexpr` is supported; and `asc_vf_call` must pass all template parameters
explicitly. Not established here: nothing was compiled, and upstream names no enforcement mechanism for
any of the twelve.

## 2 · The wrong branch this removes
These read as a coding-style list, and that is the trap. An agent generating a VF writes idiomatic
modern C++ — `int` induction variables, a small local array for a stencil window, a runtime branch on a
tiling flag, a member function on the operator class — and every one of those is on the list. If the
constraints are compiler-enforced, the agent gets a diagnostic and learns; the cost is a failed build.
If they are not, the failure mode is unspecified and could be anything from a silently scalarised loop
to a wrong result.

Upstream calls them 硬约束 and names no mechanism, so which of those two worlds we are in is unknown —
and that uncertainty is itself the actionable content. Three of the seven have plausible silent-failure
shapes worth naming, because they determine what a reviewer should look for:

**Constraint 6 (no runtime `if/else`)** is the one with real teeth. A VF executes as a vector operation
over lanes; a runtime branch has no coherent meaning unless it is uniform across the register, and the
mask registers exist precisely to express per-lane selection instead. A tolerated runtime branch would
most plausibly be scalarised — the loop stops vectorising — which is a large, silent performance loss
with correct output. Nothing in a profile says "your branch cost you the vectorisation"; it just shows a
slow VF.

**Constraint 4 (no arrays)** connects to register allocation. `RegTensor` lives in vector registers, and
a local array wants an addressable stack frame. On the SIMT side the analogous pressure is explicit —
per-thread registers are banded and overflow spills to stack (0236). If a VF array is tolerated rather
than rejected, the likely outcome is a spill, again silent.

**Constraint 3 (`uint16_t` induction variable)** is the most easily violated by accident and the one
upstream's own template documents a consequence for: `vf-programming-rules.md:107` warns that `offset`
must be written `static_cast<int32_t>(i) * kRepF32` to avoid an implicit `uint16_t × int32_t`
conversion. So the narrow induction type is load-bearing enough that it creates a second rule about how
to use it — which is a strong hint that it is enforced, and also that an agent widening `i` to `int32_t`
to "fix" the cast warning would be violating constraint 3 to remove a warning that constraint 3 caused.

Constraint 5 and the member-function prohibition (§10's first bullet) are the two most likely to bite a
generated kernel, because operator code in this repo is class-shaped: the natural place to put a VF is a
private method of the operator class, and both rules forbid it.

## 3 · Ground / Source
`vf-programming-rules.md:134-150`, sections 9 and 10 in full — they are one contract split across two
headings and a reader who stops at section 9 misses five of the twelve:

> ## 9 VF 7 条硬约束
>
> 1. **for 循环必须从 0 开始**
> 2. **VF 内最多 4 层 for**
> 3. **循环控制变量必须是 `uint16_t`**
> 4. **VF 内禁止数组**
> 5. **VF 内禁止访问类的"对象级"成员变量**（在 `asc_vf_call` 调用侧提取为临时变量/参数传入）
> 6. **VF 内禁止运行时 `if/else`**（用 `if constexpr` 代替）
> 7. **使用 `asc_vf_call` 启动 SIMD VF 函数**
>
> ## 10 `__simd_vf__` 函数约束
>
> - C 函数格式，**不能是类成员函数**
> - **不能引用外部模板**（如 `Reducer::identity` 需作为参数传入）
> - 支持模板参数（如 `typename T` / `bool isTailR`）
> - 支持内部 `if constexpr`
> - `asc_vf_call` 显式传递所有模板参数

The worked example at `:109-132` shows all of it applied at once, and is the artefact that transmits:

```cpp
template <typename T>
__simd_vf__ inline void XxxVfImpl(
    __ubuf__ T* src, __ubuf__ T* dst,
    uint32_t totalElems, uint16_t repeatTime)
{
    AscendC::Reg::RegTensor<T> aReg;
    AscendC::Reg::MaskReg mask;
    uint32_t remaining = totalElems;
    for (uint16_t i = 0; i < repeatTime; ++i) {
        int32_t off = static_cast<int32_t>(i) * static_cast<int32_t>(VL);
        mask = AscendC::Reg::UpdateMask<T>(remaining);
        AscendC::Reg::LoadAlign(aReg, src + off);
        // ... 计算
        AscendC::Reg::StoreAlign(dst + off, aReg, mask);
    }
}
asc_vf_call<XxxVfImpl<T>>(src, dst, totalElems, repeatTime);
```

Note the shape: a free function template, raw `__ubuf__` pointers rather than `LocalTensor` (which
`vec-03-fused-instr.md:53` separately forbids because the wrapper blocks `RegTensor` allocation), scalar
parameters passed in rather than read from a member, `uint16_t i` starting at 0, one loop level, no
array, no runtime branch. Every constraint is visible in twenty lines, which is why the template matters
more than the list — and why 0253's defect in the *same* file is worth its own entry.

The SIMT side has a parallel but **different** contract, and conflating them is a live hazard.
`ascendc-simt-api-reference/references/overview.md:39` states for `asc_vf_call`: "子任务函数不能是类的
成员函数，推荐使用普通函数或类静态函数，且入口函数必须使用 `__simt_vf__` 修饰宏。传递的参数只支持裸指针
和常见基本数据类型，不支持传递结构体、数组等。" So the member-function prohibition and the
no-structs/no-arrays parameter restriction appear on both sides — but the SIMT rules govern
`__simt_vf__` and the seven above govern `__simd_vf__`, and upstream elsewhere forbids cross-mode calls
between the two callee families entirely. An agent that merges the two lists will apply a SIMD
constraint to a SIMT VF or vice versa.

What upstream does not supply for any of the twelve: a diagnostic, an error message, a compiler flag, or
a statement of what happens on violation. The word 硬 is the only claim about enforcement.

## 4 · Procedure
Runnable later; every arm is compile-only and needs no device, which makes this one of the cheapest
verifiable entries in the block and the one that should run first.

Arm A — one violation per build, twelve builds plus a control. Start from the §3 worked example as the
control, which must compile. Then produce one variant per constraint, each violating exactly one rule
and nothing else:

1. `for (uint16_t i = 1; i < repeatTime + 1; ++i)` — loop starts at 1
2. five nested `for` loops
3. `for (int32_t i = 0; ...)` — wrong induction type
4. `T tmp[8];` declared inside the VF
5. a VF reading `this->scalar_` from an enclosing class
6. `if (runtimeFlag) { ... } else { ... }` on a value passed in as a parameter
7. the VF invoked directly instead of through `asc_vf_call`
8. the VF declared as a non-static class member function
9. the VF referencing `Reducer::identity` instead of taking it as a parameter

For each, record three things and not one: does it compile; if not, does the diagnostic name the
constraint; if it does compile, does it produce correct output. The third column is the entry's real
payload — a constraint that compiles is a constraint whose failure mode is unknown.

Arm B — the silent-degradation arm, for whichever violations compile. For each such variant, disassemble
and compare against the control: count vector instructions, count stack load/stores, and record whether
the loop was vectorised at all. Constraint 6 predicts scalarisation and constraint 4 predicts spill;
this arm is what distinguishes "tolerated" from "tolerated and free". A disassembly is a build artefact,
so this still needs no device.

Arm C — the timing consequence, the only arm needing a board, and only for variants that compiled and
produced correct output. Run control and variant at identical shape, same die, same session, minimum
`aiv_time` over 50 repetitions. A correct-but-slower variant is the worst case for a reviewer and the
most useful thing to be able to quote.

Arm D — the four-level nesting boundary specifically, because it is the one constraint stated as a
number. Build at 1, 2, 3, 4 and 5 levels and locate the exact level at which it breaks. A limit stated as
"at most 4" is falsifiable at 5 and confirmable at 4; anything else is a guess about where the wall is.

Device selection for Arm C is explicit: the operator names the device index, the probe prints it back
with `compiler/version.info` and the resolved SoC string, occupancy is checked first (shared machine,
≤4 dies), and no die is substituted for another. Control and variant run on one named die in one session
or the comparison attributes nothing.

## 5 · Checker — acceptance declared before the run
Verdict variable `constraint_enforced[k]`, one per constraint, twelve of them, **never aggregated**. An
aggregate boolean over twelve independent rules is the exact shape that lets eleven enforced constraints
hide the one that is silently tolerated — and the tolerated one is where the damage is.

Per constraint, three declared outcomes, none reinterpretable afterwards:
`enforced` — the violating build fails **and** its diagnostic names the constraint (or names the
construct: the induction type, the array, the member access). The checker matches diagnostic text, not
exit status, because "it did not compile" and "it did not compile for the stated reason" are different
results and only the second establishes enforcement.
`tolerated-degraded` — it compiles, output is correct, and Arm B or C shows a measurable cost. The
constraint is real advice with no mechanism, and the delivered skill must say so.
`tolerated-silent` — it compiles, output is correct, and no cost is detectable. The constraint is
unsupported by anything observable on this toolkit, which does not make it wrong but does mean it cannot
be relied on as a guard.

A fourth outcome is possible and is the one to watch for: compiles, and output is **wrong**. That is the
worst case for every one of the twelve and is reported first in the summary regardless of which
constraint produced it.

`nest_limit` (Arm D) — the deepest level that compiles. Pass iff exactly 4.

The positive fixture, declared before the run: the control build must compile **and** produce output
bit-matching a host reference. If the control fails, every "the violating build failed" result is an
artefact of the harness rather than evidence of enforcement, and all twelve verdicts are void. A second
fixture: introduce a deliberate, unrelated syntax error into one variant and confirm the harness reports
it as a *different* failure from a constraint violation — if the harness cannot distinguish a typo from
an enforced constraint, its `enforced` verdicts mean nothing. Without both, the checker reads only
"some builds failed", which is the known blind species.

Process exit codes are not the verdict anywhere: for eleven of the twelve builds a non-zero exit is the
expected outcome.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No translation unit was
compiled, no diagnostic was collected, no disassembly was inspected, and no device was contacted.
Upstream's word 硬约束 is an assertion about enforcement, not an observation of it, and no header or
compiler documentation was consulted for any of the twelve.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled. The entry does not establish that any of the twelve is enforced, or what happens
on violation — which is the whole of §4 and is open for all of them. Upstream supplies no diagnostic, no
flag and no failure description, so the silent-degradation shapes named in §2 for constraints 3, 4 and 6
are reasoning about the mechanism, not observations. It does not establish the four-level nesting limit
as a hardware or compiler limit rather than a guideline; Arm D locates the wall and does not explain it.
There is **no second origin**: sections 9 and 10 are one file in one repo, and no installed header was
read for any of it — unlike 0244 and 0246, where the toolkit answered. It does not establish that the
twelve are complete: `vec-03-fused-instr.md:53` adds a thirteenth from a different skill (raw
`__ubuf__ T*` rather than `LocalTensor`, because the wrapper blocks `RegTensor` allocation), so the list
is a floor and no survey of the wider repo was performed. It says nothing about the **SIMT** contract:
`__simt_vf__` has its own, partly overlapping rules (0241's territory) and upstream forbids cross-mode
calls between the two callee families, so nothing here transfers to a SIMT VF even where the wording
matches. BOARD is `family-claimed(unverified)` — the file names no board token this book recognises, the
material is arch35-generic regbase, and none was contacted; constraints that are compiler-enforced would
be board-independent, which is itself untested. Finally, the worked example quoted in §3 is the same
template whose lane constant 0253 records as violating a rule from another skill, so it should be cloned
for its structure and not for its constants.
