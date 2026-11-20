```
ID:        0250-a-kernel-side-api-and-its-vf-side-namesake-are-not-interchangeable
LABEL:     trap
LEVEL:     L8 (toolchain & build)
STRATUM:   harvested — one upstream origin (ops/ascendc-regbase-best-practice), stated in the
           whitelist and reinforced by that skill's pitfall material. The installed toolkit's two
           header trees are consistent with the split; nothing was compiled.
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-regbase-best-practice/references/knowledge/api/regbase_api_whitelist.md:53-59
           — "- Ordinary regbase kernel-side APIs and VF-function APIs are not interchangeable, even
           when names look similar." … "- If the same capability exists in both a kernel-side and a
           VF-function-safe form, verify the namespace, parameter style, and mask/control contract
           before coding."
SOURCE:    same file:105-107 — "- Do not assume that a kernel-side `LocalTensor` API has the same
           signature, mask contract, or address assumptions as its VF-side counterpart."
SOURCE:    same file:62-84 — the two tables: kernel-side families (`VF Function? = No`,
           `basic_api/interface/`) and VF-safe families (`VF Function? = Yes`,
           `basic_api/interface/reg_compute/`), with `Add`, `Sub`, `Mul`, `Max`, `Min`, `And`, `Or`,
           `Xor`, `Adds`, `Muls`, `Compare`, `Select`, `Move` appearing in BOTH.
INDEX:     none — nothing measured; see SOURCE. The two header roots are re-derivable by file read:
           ls $ASCEND_HOME_PATH/include/ascendc/basic_api/interface/ $ASCEND_HOME_PATH/include/ascendc/basic_api/interface/reg_compute/
OVERTURN:  a kernel-side API listed `VF Function? = No` that compiles inside a `__simd_vf__` and
           produces correct output on a 950 board — the partition would then be advisory rather
           than a boundary.
```

# 0250 · A kernel-side API and its VF-side namesake are not interchangeable

## 1 · Claim
Upstream asserts that the Regbase API surface is partitioned into two families that share names but not
semantics: ordinary kernel-side APIs, rooted at `basic_api/interface/` and marked `VF Function? = No`,
and VF-function-safe APIs rooted at `basic_api/interface/reg_compute/` and marked `Yes`. Upstream asserts
they are **not interchangeable even when the names look identical**, and names the three things that may
differ between a same-named pair: the namespace, the parameter style, and the mask/control contract.
Upstream asserts specifically that a kernel-side `LocalTensor` API must not be assumed to share the
signature, mask contract, or address assumptions of its VF-side counterpart. Not established here:
nothing was compiled, and upstream names no enforcement mechanism.

At least thirteen names appear in both tables — `Add`, `Sub`, `Mul`, `Max`, `Min`, `And`, `Or`, `Xor`,
`Adds`, `Muls`, `Compare`, `Select`, `Move`.

## 2 · The wrong branch this removes
This is the entry that 0244, 0245, 0246 and 0258 all lean on, and it is the one that makes the whitelist
more than a list of legal names.

An agent inside a VF needs an add. It knows `Add` exists — it has seen it in the kernel-side table, in
example code, in a hundred places. It writes `Add(dst, src0, src1, count)`, the kernel-side form with an
element count. The VF-side form is `Reg::Add(dstReg, src0Reg, src1Reg, maskReg)`: different namespace,
`RegTensor` instead of `LocalTensor`, and a **mask** instead of a count. Those are not variations on a
signature; they are different execution models wearing one name.

Three failure modes follow and they are not equally visible.

If the kernel-side symbol is simply unavailable inside a VF, the build fails and the agent learns. Cheap.

If it is available and takes a `LocalTensor`, the agent will reach for one — and `vec-03`'s stop rule
(`:53`) says a `LocalTensor` wrapper *blocks* `RegTensor` register allocation. So the code compiles, runs,
is numerically correct, and has silently defeated the entire point of the Regbase model: computation in
registers rather than through UB. The profile shows a VF that is not much faster than the membase version
it replaced, with no defect anywhere.

If the two forms differ in the **mask/control contract** — which is the specific thing upstream names —
the failure is numerical and partial. A count-based API processes exactly `count` elements; a mask-based
one processes the lanes the mask selects, with `MaskMergeMode` deciding what happens to the rest (0255).
An agent that supplies the wrong control for the API it actually called gets the wrong tail, which
survives every small-shape test (`common_traps.md` §3: small aligned cases hide tail handling).

The deeper reason this is a `trap` rather than `knowledge`: the whitelist's two tables are printed one
after another with the same column headings, and the only thing distinguishing them is a `Yes`/`No`
column and a header-root path. Thirteen names appear in both. A reader who scans for a name finds it, and
finding it is not the question — *which table it was in* is.

## 3 · Ground / Source
`regbase_api_whitelist.md:53-59`, the Scope Rules, which state the partition as a rule rather than a
layout:

> ## Scope Rules
>
> - Ordinary regbase kernel-side APIs and VF-function APIs are not interchangeable, even when names look
>   similar.
> - When a design enters a VF function, prefer `AscendC::Reg::*` and other `reg_compute/` interfaces as
>   the callable surface.
> - When reading open-source code, treat `AscendC::MicroAPI::*` as the same VF-safe API family unless the
>   local code adds its own wrapper layer on top.
> - A VF function may call `__simd_callee__` interfaces from `reg_compute/`, but it must not treat another
>   VF helper as a general callable utility.
> - Pointer arguments passed into VF helpers must stay in `__ubuf__` address space.
> - If the same capability exists in both a kernel-side and a VF-function-safe form, verify the namespace,
>   parameter style, and mask/control contract before coding.

and `:105-111`, the VF-Specific Guardrails, which restate it as an instruction at the point of use:

> - Treat `AscendC::Reg::*` as the default API surface once you are inside a VF function.
> - **Do not assume that a kernel-side `LocalTensor` API has the same signature, mask contract, or address
>   assumptions as its VF-side counterpart.**
> - Check the VF-capable header first when the code path uses `RegTensor`, `MaskReg`, `LoadDist`, or
>   `StoreDist`.
> - Re-check mask creation and update rules before using `CreateMask`, `UpdateMask`, `Pack`, or `UnPack`
>   inside a VF helper.
> - If a helper would need to call another VF helper, stop and re-check the design.

The overlap, from the two tables at `:62-84`. Kernel-side (`VF Function? = No`,
`basic_api/interface/`):

> | Binary compute | `Add`, `Sub`, `Mul`, `Div`, `Max`, `Min`, `And`, `Or`, `Xor`, `Axpy`, `FusedMulAdd`, `AddRelu`, `SubRelu` | No | `basic_api/interface/` |
> | Scalar helpers | `Adds`, `Muls`, `Divs`, `Maxs`, `Mins`, `ShiftLefts`, `ShiftRights` | No | `basic_api/interface/` |
> | Compare and select | `Compare`, `Compares`, `Select` | No | `basic_api/interface/` |
> | Conversion and utility | `Cast`, `ReinterpretCast`, `Duplicate`, `Arange`, `CreateVecIndex`, `Interleave`, `DeInterleave`, `Move` | No | `basic_api/interface/` |
> | Sync and event | `PipeBarrier`, `SetFlag`, `WaitFlag`, `CrossCoreSetFlag`, `CrossCoreWaitFlag`, `SyncAll` | No | `basic_api/interface/` |

VF-safe (`Yes`, `basic_api/interface/reg_compute/`):

> | Binary reg compute | `Add`, `Sub`, `Mul`, `Div`†, `Max`, `Min`, `And`, `Or`, `Xor`, `MulAddDst`, `Mull` | Yes | `basic_api/interface/reg_compute/` |
> | Scalar reg compute | `Adds`, `Muls`, `Divs`, `Maxs`, `Mins`, `ShiftLefts`, `ShiftRights` | Yes | `basic_api/interface/reg_compute/` |
> | Compare and select | `Compare`, `Compares`, `Select` | Yes | `basic_api/interface/reg_compute/` |
> | Mask and copy helpers | `MaskReg`, `CreateMask`, `UpdateMask`, `Pack`, `UnPack`, `Move`, `LocalMemBar` | Yes | `basic_api/interface/reg_compute/` |

`Compare`, `Compares`, `Select` appear as a **whole family** in both tables, under the same family name,
with only the `Yes`/`No` and the root differing. `Adds`/`Muls`/`Divs`/`Maxs`/`Mins`/`ShiftLefts`/
`ShiftRights` likewise. That is the strongest form of the trap: not a coincidental name collision but two
parallel families designed to mirror each other.

Note also what is *only* kernel-side and matters: `PipeBarrier`, `SetFlag`, `WaitFlag`, `SyncAll` are all
`No`. So the synchronisation primitives of 0259, 0261 and 0262 are not callable from inside a VF — the
VF-internal ordering primitive is `LocalMemBar` (0258), which appears only in the VF-safe table. An agent
that tries to place a `PipeBarrier` inside a VF body has confused the two scopes, and this partition is
what says so.

The `Div` dagger (0249) sits on the VF-side row only. So a same-named pair can differ in **precision
contract** too — one more axis than upstream's three.

Reinforcement from the same skill's pitfall material,
`references/knowledge/pitfalls/api_misuse.md:32-46` ("Mixing regbase and membase mental models") and
`references/knowledge/pitfalls/regbase_vs_membase_confusions.md:47`:

> | "A familiar API name means the usage contract is the same." | Similar names can hide different branch
>   expectations and data movement assumptions. | Re-check the regbase whitelist and usage notes before
>   implementation. |

Same repo throughout — **one origin** (RULES.md Art. 3).

**Installed toolkit, consistent with the split** (phase-1 read-only exception, no compilation): the two
header roots exist as separate trees —
`include/ascendc/basic_api/interface/` and `include/ascendc/basic_api/interface/reg_compute/` — and 0246
quotes `kernel_reg_compute_vec_binary_intf.h` from the second declaring `Reg::MulAddDst` as
`__simd_callee__` taking `(U& dstReg, U& srcReg0, U& srcReg1, MaskReg& mask)`. That is the VF-side
signature shape: register references and a mask, no count. The corresponding kernel-side header
(`kernel_operator_vec_binary_intf.h`) exists in the first root. Two trees, two shapes — consistent with
upstream, and **not** corroboration of the interchangeability claim, which is about behaviour rather than
about directory structure.

## 4 · Procedure
Runnable later on `950PR`; the decisive arms are compile-only and need no device.

Arm A — the partition, tested in the direction that matters. For each of the thirteen dual-listed names,
compile a `__simd_vf__` that calls the **kernel-side** form (its namespace, its `LocalTensor` parameter
style, its count argument). Upstream's partition predicts these fail. Record per name: does it compile,
and if not does the diagnostic name the address space, the type, or the scope. A name that compiles is
the finding.

Arm B — the signature divergence, a file read needing no device. For each dual-listed name, extract both
declarations from the two header roots and diff them on upstream's three axes plus the fourth this entry
found: namespace, parameter style, mask/control contract, precision contract. The output is a table of
what actually differs per name — which is the artefact a consuming agent needs and which no upstream
document supplies.

Arm C — the `LocalTensor` register-allocation claim, which is the silent branch in §2. Build one VF two
ways: parameters as raw `__ubuf__ T*` (per the whitelist and vec-03), and as `LocalTensor`. Compare
`aiv_time` at identical shape on the same die in the same session, and disassemble both to count
`RegTensor`-backed operations versus UB round trips. vec-03 claims the wrapper blocks register
allocation; the disassembly is what makes that attributable rather than a timing anecdote.

Arm D — the mask/control contract, which is the numerically dangerous axis. For one dual-listed name
(`Select` is the clearest), run the kernel-side count-based form and the VF-side mask-based form on
inputs whose tail is not a whole register, and compare outputs element by element. §2 predicts the tails
differ; showing exactly how is what turns a warning into a rule.

Device selection is explicit for Arms C and D: the operator names the device index, the probe prints it
back with `compiler/version.info` and the resolved SoC string, occupancy is checked first (shared machine,
≤4 dies), and no die is substituted for another. Arms A and B need no device and run first.

## 5 · Checker — acceptance declared before the run
Verdict variable `partition_holds[name]`, one per dual-listed name, thirteen of them, **never
aggregated**. Thirteen names behind one boolean is the shape that lets twelve correctly-rejected names
hide the one that silently compiles — and that one is where a generated kernel will land.

Per name, pass iff the kernel-side form fails inside a VF **and** the diagnostic names the reason. The
checker matches diagnostic text, not exit status: "it did not compile" and "it did not compile for the
stated reason" are different results, and only the second establishes a partition rather than an
unrelated error. A name that compiles is recorded as `interchangeable-on-this-toolkit` — not as a failure
of this entry, but as a hole in the partition that the delivered skill must disclose, since upstream states the
rule and the toolchain would not be enforcing it.

`signature_axes[name]` (Arm B) — which of the four axes differ, per name. No pass condition; it is the
missing table. A name whose two declarations are **identical** on all four axes would be the interesting
case: it would mean the partition is about *where* the symbol lives rather than what it does.

`localtensor_blocks_regalloc` (Arm C) — pass iff the `LocalTensor` build shows measurably more UB traffic
in disassembly **and** is slower. Both clauses: a timing difference alone attributes nothing, and the
claim is specifically about register allocation.

`tail_differs` (Arm D) — pass iff the two forms produce different tails on a non-whole-register shape. A
null result here would mean the mask and count contracts coincide at the tested shape, which is
compatible with them differing elsewhere and is reported as `not provoked`, never as equivalence.

The positive fixture, declared before the run: Arm A must include a control calling the **VF-side** form
of the same name, which must compile and produce correct output in the same session. If the control fails,
the harness cannot build a valid VF at all and every rejection it reported is an artefact rather than
evidence of a partition. Without this the checker reads only "the calls failed", which is the known blind
species — a harness that cannot compile anything rejects everything.

Process exit codes are not the verdict anywhere: in Arm A a non-zero exit is the expected outcome for
thirteen of thirteen builds.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No translation unit was compiled,
no signature was diffed, and no device was contacted. The two header roots noted in §3 were observed to
exist and one VF-side declaration was quoted (0246); a directory listing and a declaration are consistent
with a partition and do not establish that the kernel-side form is *rejected* inside a VF, which is the
claim.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled. The entry does not establish that the partition is enforced for any of the thirteen
dual-listed names — Arm A is open, and `interchangeable-on-this-toolkit` is a live outcome for every one
of them. It does not establish what differs between any same-named pair: upstream names three axes
(namespace, parameter style, mask/control contract), this entry found a fourth (`Div`'s precision
contract, 0249), and Arm B — a file read — is what would produce the actual per-name table. There is **no
second origin**: the rule is one skill, and the installed headers' two-tree structure is consistent with
it rather than corroborating it. It does not establish vec-03's `LocalTensor`-blocks-register-allocation
claim, which comes from a different skill and is the silent branch in §2 (Arm C). It does not enumerate
the dual-listed set exhaustively: thirteen names were counted from the whitelist's tables, and the
whitelist is itself incomplete (0245, 0246 — `MulDstAdd` is absent from it entirely), so the true overlap
may be larger. BOARD is `family-claimed(unverified)`: the whitelist names no board, the material is
arch35-generic regbase, and none was contacted; a compile result would be toolkit-scoped rather than
board-scoped anyway. It says nothing about the **SIMT** side, where `__simt_vf__` and `__simd_vf__` callee
families are separately partitioned and upstream forbids calling across them (0241 §3) — a third
partition, orthogonal to this one.
