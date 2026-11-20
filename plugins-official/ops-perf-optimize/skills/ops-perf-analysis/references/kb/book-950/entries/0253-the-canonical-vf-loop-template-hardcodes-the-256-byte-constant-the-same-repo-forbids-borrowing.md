```
ID:        0253-the-canonical-vf-loop-template-hardcodes-the-256-byte-constant-the-same-repo-forbids-borrowing
LABEL:     trap
LEVEL:     L8 (toolchain & build)
STRATUM:   verified — §4 run on 950PR 2026-08-25, via §5's declared verdicts: substitution_is_legal PASS
           (GetVecLen() is constexpr; the literal is avoidable), Arm B's borrowed build measured
           writing 64 halves beyond the task window, bare `VL` does not resolve. §6 has the
           readouts. Previously harvested (documentary conflict only).
BOARD:     950PR (measured 2026-08-25; Arm A is pin-level, board-independent)
SOURCE:    ops/ascendc-regbase-best-practice/references/paradigms/common/vf-programming-rules.md:95-107
           — "## 7 VF 循环范式" with "constexpr uint32_t kRepF32 = 256 / sizeof(float);  // = 64" and
           the constraint note "`offset` 用 `static_cast<int32_t>(i) * kRepF32`，避免 `uint16_t` ×
           `int32_t` 隐式转换。"
SOURCE:    ops/ascendc-perf-optimize/references/single-core-pipeline/techniques/vec-03-fused-instr.md:52
           — "lane 数用 `GetVecLen()/sizeof(dtype)`，**不要借** `B32_DATA_NUM_PER_REPEAT(=64)` 或
           `ONE_BLK_SIZE/sizeof(dtype)`——换 dtype/换代会全错。"
INDEX:     substitution_is_legal=PASS (constexpr compile) · borrowed-build overrun 64 halves ·
           bare VL: undeclared identifier. Run 2026-08-25, 9.1.0 pin / Ascend950PR.
OVERTURN:  `GetVecLen()` shown not to be usable in a `constexpr` initialiser on a LATER pinned
           toolkit (on 9.1.0 it is, measured) — the repair would then move from substitution to
           restructuring for that pin.
```

# 0253 · The canonical VF loop template hardcodes the 256-byte constant the same repo forbids borrowing

## 1 · Claim
Upstream asserts, in `ascendc-perf-optimize`, that a VF's lane count must come from
`GetVecLen()/sizeof(dtype)` and never from a borrowed or hardcoded capacity (0252). Upstream's canonical
VF loop template, in `ascendc-regbase-best-practice`, writes
`constexpr uint32_t kRepF32 = 256 / sizeof(float);  // = 64` — the vector-register width as a literal.
The same file states VL = 256 B in its own type table nine sections earlier. Not established here:
nothing was compiled, and whether `GetVecLen()` can appear in a `constexpr` initialiser on this toolkit
is untested.

## 2 · The wrong branch this removes
The template is the artefact that transmits. It sits under the heading `## 7 VF 循环范式` — the loop
paradigm — in the file a Regbase author opens to learn how to write a VF, and it is complete, correct on
fp32 on this architecture, and short enough to copy whole. The rule that forbids it lives in a different
skill, in a technique card's stop-rules block, in a library the 2026-08-24 deep-dive measured as having
essentially no coupling with this one (one shared line ≥40 characters between them). So an agent learning
Regbase from the canonical template never meets the rule, and an agent that meets the rule has already
been taught the wrong habit.

What breaks and when: `kRepF32` is named for fp32 and is correct for fp32. A kernel templated on `T`
that reuses the pattern — `256 / sizeof(T)` — still tracks the dtype and fails only on an architecture
whose VL differs. A kernel that copies the *name and the value* into a `half` path gets 64 where 128 is
needed and processes half its data per pass. Neither faults on this machine.

The sharper reading is that the template is one step short of correct rather than wrong in principle. It
already divides by `sizeof(float)`, so it has the shape of the rule; the only defect is the capacity
being a literal instead of an accessor. That makes it the most imitable kind of defect — the structure
teaches the right lesson and the constant teaches the wrong one, and a reader copying the structure will
copy the constant with it.

There is a real possibility this is forced rather than careless, and it changes the repair. `constexpr`
requires a compile-time constant initialiser. If `GetVecLen()` is `__simd_callee__` — callable only
inside a VF, at run time — then `constexpr uint32_t kRepF32 = GetVecLen()/sizeof(float);` is ill-formed
and the template's author had no substitution available. The fix would then be structural: compute the
lane count as a non-`constexpr` local inside the VF, which costs the `constexpr`-ness the surrounding
code may rely on. §4 Arm A settles this and it is a file read.

## 3 · Ground / Source
`vf-programming-rules.md:95-107`, the template in full with the constraint note that follows it:

> ## 7 VF 循环范式
>
> ```cpp
> constexpr uint32_t kRepF32 = 256 / sizeof(float);  // = 64
> uint16_t repeatTime = static_cast<uint16_t>(
>     (static_cast<uint32_t>(totalElems) + kRepF32 - 1) / kRepF32);
> for (uint16_t i = 0; i < repeatTime; ++i) {
>     int32_t offset = static_cast<int32_t>(i) * kRepF32;
>     // ...
> }
> ```
>
> **约束**：`offset` 用 `static_cast<int32_t>(i) * kRepF32`，避免 `uint16_t` × `int32_t` 隐式转换。

Everything else about this template is careful. The `uint16_t` loop variable satisfies the VF hard
constraint requiring exactly that type (0254). The ceiling division is written correctly. The offset cast
is called out with its reason — an implicit `uint16_t × int32_t` conversion — which is the kind of note
that only gets written after someone was bitten by it. The one literal is the anomaly, not the pattern.

The same file states the capacity it hardcodes, at `:9`:

> | `AscendC::Reg::RegTensor<T>` | 向量寄存器，VL=256B。b16→128 元素，b32→64 元素 |

and at `:43`: "`scalarValue` 是引用传递，内部自动递减 VL_T（float:64，half:128）". So the file knows the
value is dtype-dependent and knows both values; it hardcodes the byte width anyway. And at `:122` the
`__simd_vf__` example uses a bare `VL` identifier —
`int32_t off = static_cast<int32_t>(i) * static_cast<int32_t>(VL);` — a third spelling, with `VL` never
defined anywhere in the file. That is a fourth variant of the same quantity inside one document: `256`
literal, `kRepF32`, the prose `VL=256B`, and an undefined `VL` symbol.

The rule it violates, `vec-03-fused-instr.md:52`, is quoted in the header and carried as 0252. Note the
asymmetry in how the two libraries gate: perf-optimize gates on msprof thresholds, regbase gates on
compile and correctness rules. A hardcoded capacity is invisible to both — it does not slow anything
down on the machine it was written on, and it compiles. That is the same structural reason B2's
four-way disagreement survived (0259 §3).

This is filed as `C-950arch-009` in `harvest/contradictions-950-arch.md`.

For scale: contradiction rows C-006 and C-007 record four UB values and five core counts hardcoded across
one perf-optimize subtree. So neither library is clean, and the discipline exists in exactly one card and
is practised in neither template.

## 4 · Procedure
Runnable later; the decisive arm needs no device and should run first, because it decides which defect
this is.

Arm A — is the substitution even legal. Locate `GetVecLen()` in the installed toolkit and record its
declaration — namespace, return type, and whether it is `constexpr`, `__simd_callee__`, or both:

```bash
grep -RIn "GetVecLen" "$ASCEND_HOME_PATH/include/ascendc/basic_api/interface/reg_compute/"
```

`grep -R`, not `-r` — these trees are symlink farms. Then compile the substitution directly:

```cpp
constexpr uint32_t kRep = AscendC::Reg::GetVecLen() / sizeof(float);   // legal?
```

If this compiles, the template's literal is a plain defect and the repair is a one-line substitution. If
it does not, the repair is structural and this entry's §2 second reading holds.

Arm B — the dtype divergence, on the board. Build one elementwise VF at `half` twice: once with
`kRepF32`-style `256 / sizeof(float)` copied as-written, once with `256 / sizeof(T)`, once with the
accessor form if Arm A permits it. Compare each output against a host reference. The first is expected to
process half the elements; recording whether the remainder is dropped or written out of bounds is the
finding, since the two need different repairs.

Arm C — the `VL` symbol at `:122`. Attempt to compile that example as written. `VL` is undefined in the
file, so either it is expected from an SDK header — in which case Arm A's grep should find it — or the
example does not compile, which is a separate documentation defect worth recording. This costs one
build and closes a loose end that would otherwise propagate.

Arm D — the imitation test, which is the only arm that measures what this entry is actually about. Give
the template and the vec-03 stop rules to a fresh consuming agent, ask it to write a `half` VF, and
record which lane expression it emits. This is a behavioural measurement rather than a hardware one, and
it is the one that says whether the defect transmits. It needs no board.

Device selection for Arms B and C is explicit: the operator names the device index, the probe prints it
back with `compiler/version.info` and the resolved SoC string, occupancy is checked first (shared
machine, ≤4 dies), and no die is substituted for another. All three builds of Arm B run on one named die
in one session.

**As-run notes (2026-08-25, before the promoting evaluation of §6).** Arm A ran as a host-side
compile probe on the bound 9.1.0 pin (`constexpr uint32_t lanes = GetVecLen()/sizeof(float)`), with
one instrument correction self-reported at the time: a namespace-scope `static_assert` on
`GetVecLen()` evaluates the HOST pass of an -xasc TU (where the function returns 0) and printed a
false "≠256" before the device-side echo settled the value — see 0252 §4's caution. Arm B shares
0252's Arm E run (borrowed kRep=64 at half, distinct-sentinel instrument). Arm C compiled the bare
`VL` line as written.

## 5 · Checker — acceptance declared before the run
Verdict variable `substitution_is_legal` (Arm A) — pass iff the `constexpr` initialiser using
`GetVecLen()` compiles. This verdict does not decide the entry; it decides **which entry this is**, and
that is why it is separated out. Legal means the template carries an avoidable hardcoded capacity and
this entry stands as a trap. Illegal means the template's author had no substitution and the entry is
corrected in place to a `boundary` — the rule in 0252 would then be unimplementable as literally stated,
which is a finding against the rule rather than against the template.

`dtype_divergence` (Arm B) — pass iff the copied-as-written build at `half` produces output differing
from the host reference. A build that produces *correct* output at `half` despite a 64-lane step means
the mask absorbed the error at a throughput cost only, which relocates the defect from correctness to
performance and is declared now so it cannot be read as vindication.

`vl_symbol_resolves` (Arm C) — pass iff the `:122` example compiles. Failure is recorded as a separate
documentation defect, not as evidence about the lane rule.

`imitation_reproduces_defect` (Arm D) — reported: which of the three lane expressions a fresh agent
emits. No pass condition; this is the transmission measurement and either outcome is informative.

The positive fixture, declared before the run: Arm B must include a fourth build at `float` with the
template copied as-written. It **must** match the host reference exactly. If it does not, the harness's
reference or its element count is wrong and every `dtype_divergence` verdict is void — the template is
correct at fp32 by construction, so a failure there is a harness failure, not a finding. Without this
the checker only reads "the half build was wrong", which is the known blind species: many things make a
`half` build wrong.

Process exit codes are not the verdict anywhere: in Arms A and C a non-zero exit is a possible expected
outcome and is the informative one.

## 6 · Evidence
RUN 2026-08-25 (Arms A and C host-side compiles on the bound pin; Arm B shares 0252 Arm E's device
run; 2026-08-25 direct-launch probes, Ascend950PR, bound pin CANN 9.1.0 build 20260730_231653901, `-xasc --npu-arch=dav-3510`; probe sources and full logs with the verification run).

- **Arm A** — `substitution_is_legal` = PASS: `GetVecLen()` is `constexpr` on this pin
  (`kernel_operator_sys_var_intf.h:76`) and the initialiser compiles. The template's
  `kRepF32 = 256/sizeof(float)` literal is therefore an avoidable hardcoded capacity, and this
  entry STANDS as a trap.
- **Arm B** — `dtype_divergence` came back as the outcome §5 declared must not be read as
  vindication, PLUS a sharper edge: the copied-as-written 64-lane step at `half` produced CORRECT
  output inside the 128-element task window — and silently wrote **64 further halves beyond it**
  (0252 §6 Arm E, distinct-sentinel readout). The defect does not relocate to performance; it
  relocates to the neighbour's memory.
- **Arm C** — `vl_symbol_resolves` = FAIL: the `:122` bare `VL` line does not compile ("use of
  undeclared identifier 'VL'"). Recorded as the separate documentation defect §5 anticipated.

VF loop-form constraint hit while building Arm B's loop: the induction variable must be `uint16_t`
(hard error) — consistent with the template's own `static_cast<int32_t>(i) * kRepF32` caution about
`uint16_t` arithmetic, and now measured as compiler-enforced.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled. The entry does not establish that the template is *wrong* — §2 records a live
reading in which the literal is forced by `GetVecLen()` not being `constexpr`, and Arm A is the file read
that decides between defect and constraint. It does not establish that the hardcoded capacity ever
produces a wrong result: Arm B is open, and §5 declares in advance that a correct `half` build would
relocate this to a performance issue. It does not establish that the defect transmits to a consuming
agent; Arm D is a behavioural arm and is open. There is **no second origin**: both files are one repo,
which is exactly why the disagreement could not be settled inside it. BOARD is
`family-claimed(unverified)` — neither file names a board token this book recognises, and none was
contacted. It says nothing about whether 256 is the right capacity in the first place; that is 0219, and
0273 records that one upstream file labels the same number in bits. It says nothing about the undefined
`VL` symbol's intended source beyond flagging it, and nothing about `B32_DATA_NUM_PER_REPEAT` or
`ONE_BLK_SIZE`, the two constants 0252's rule names and this template does not use. Finally, the four
spellings of one quantity catalogued in §3 are counted within a single file; no survey of the wider repo
was performed, so "four variants" is a floor.
