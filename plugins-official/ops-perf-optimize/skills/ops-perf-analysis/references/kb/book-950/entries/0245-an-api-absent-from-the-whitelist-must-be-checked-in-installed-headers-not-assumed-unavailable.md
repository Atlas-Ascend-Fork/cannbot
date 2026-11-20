```
ID:        0245-an-api-absent-from-the-whitelist-must-be-checked-in-installed-headers-not-assumed-unavailable
LABEL:     procedure
LEVEL:     L8 (toolchain & build)
STRATUM:   harvested — one upstream origin states the rule. The rule was EXERCISED during this
           harvest (0246, 0244) and both times the headers answered, but exercising a procedure on
           two cases is not verification of the procedure; nothing was compiled.
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-regbase-best-practice/references/knowledge/api/regbase_api_whitelist.md:29 —
           "If an API is absent from the lists below, treat it as unavailable until you verify it in
           the installed SDK headers and update the design instead of guessing."
SOURCE:    same file:117 — "If the task needs an API that is not listed here, verify the SDK header
           family first and update the design rather than filling the gap with speculation."
           # same file — ONE origin, quoted twice because the rule is stated at both ends of the
           # document and a reader who opens either end meets it.
INDEX:     none — nothing measured; see SOURCE. The rule's own action is re-derivable by file read:
           grep -RIn "<ApiName>" $ASCEND_HOME_PATH/include/ascendc/basic_api/interface/reg_compute/
OVERTURN:  an API absent from the whitelist, present in the installed 950-era headers, and shown by
           a compile to be unusable inside a VF on a 950 board — the headers would then not be a
           sufficient authority and the rule's second clause would need a third step.
```

# 0245 · An API absent from the whitelist must be checked in installed headers, not assumed unavailable

## 1 · Claim
Upstream asserts a two-clause rule for APIs missing from its Regbase whitelist: treat the API as
unavailable **until** verified in the installed SDK headers, and then update the design — never fill the
gap by guessing. Upstream states the rule twice, once in the document's opening paragraph and once in
its closing guardrails, and names the four header roots against which the verification is to be
performed. Not established here: nothing was compiled, and whether a header presence is *sufficient*
for VF usability is untested.

The rule is what makes the whitelist safe to be incomplete. Read without its second clause it is a
closed-world assumption; read whole it is a default with an escape hatch and a named authority.

## 2 · The wrong branch this removes
Both halves of the rule get dropped, and dropping either is worse than not having the rule.

Drop the second clause and the whitelist becomes a closed world. This is not hypothetical — it is
exactly what happened to B1. `MulDstAdd` appears nowhere in the whitelist; the perf-optimize card
library uses it uniformly, including in a precision red line. An agent applying only "absent →
unavailable" rejects the card as wrong, substitutes the listed `MulAddDst`, compiles cleanly, and
silently changes the arithmetic (0246, 0247). The document containing the rule was the document that
would have prevented the error, and following half of it caused the error.

Drop the first clause and the reverse: an agent that treats absence as neutral picks whatever API name
appears in an example it found, on the reasoning that the whitelist is evidently not exhaustive. That
loses the whitelist's actual content — which surfaces are callable *inside a VF* (0250) — and the
failure mode is a kernel-side API called from a VF body, which is a different class of error from a
wrong-name error.

The subtler branch is what "verify" is taken to mean. An agent that greps the headers, finds the symbol,
and proceeds has done the *named* step and has not established usability: a symbol can be declared and
be kernel-side rather than VF-safe, be behind a different `dav_*` implementation for a different
architecture, or carry `static_assert`s that reject the dtype the design needs. 0246 is the worked case
— both FMA spellings are declared, and the dtype sets differ by six type families, so "present" and
"usable for my dtype" came apart. The rule says verify in the headers; it does not say a grep is
verification, and §4 is written so the difference is not glossed.

## 3 · Ground / Source
`regbase_api_whitelist.md:29`, the closing sentence of the document's opening paragraph:

> This file is the local launch gate for regbase direct-invoke work. It separates ordinary regbase
> kernel-side APIs from VF-function-safe APIs so design and review do not mix `LocalTensor`-style
> assumptions with `AscendC::Reg::*` reg-compute semantics. In open-source kernels, the same VF-safe
> surface often appears through the alias `AscendC::MicroAPI::*`. **If an API is absent from the lists
> below, treat it as unavailable until you verify it in the installed SDK headers and update the design
> instead of guessing.**

and `:113-117`, the Guardrails section, which restates it as an instruction rather than a caveat:

> ## Guardrails
> - Check this file before drafting code or generated guidance.
> - Use [[regbase_api_reference]] to confirm the broad regbase call family after the whitelist check.
> - Use [[regbase_api_sync]] when the question is about barriers, flags, or cross-core coordination
>   rather than pure API availability.
> - Prefer `DataCopyPad` when alignment is uncertain; do not assume `DataCopy` can absorb a misaligned
>   GM transfer.
> - **If the task needs an API that is not listed here, verify the SDK header family first and update
>   the design rather than filling the gap with speculation.**

Two placements of one rule, at the two points a reader is most likely to be looking: on arrival, and at
the moment of "what do I do about this gap". That placement is the part worth imitating — a rule stated
only in a preamble does not reach a reader who jumped to a table.

The named authority, `:33-38` (quoted in full in 0244 §3): four `$ASCEND_HOME_PATH`-relative roots —
`include/ascendc/basic_api/interface/` for kernel-side APIs,
`include/ascendc/basic_api/interface/reg_compute/` for `AscendC::Reg::*` VF-safe interfaces,
`include/ascendc/include/adv_api/` for higher-level helpers, and
`asc/impl/basic_api/kernel_macros.h` for the `MicroAPI` alias. Upstream adds an instruction about how to
cite them: "Do not replace them with environment-specific absolute paths in design or review notes" —
i.e. record the logical root, not the machine's path, so the reference survives a different install.

`:40` closes a naming loophole in the same spirit: "Existing knowledge cards may record the same SDK
sources with the shorthand `$INCLUDE_DIR/...`. Treat that as the same logical header root, not as a
second API surface."

The parallel rule for the *reverse* direction, `:55-59` — because the whitelist's content is a
partition, not just a list:

> - When a design enters a VF function, prefer `AscendC::Reg::*` and other `reg_compute/` interfaces as
>   the callable surface.
> - A VF function may call `__simd_callee__` interfaces from `reg_compute/`, but it must not treat
>   another VF helper as a general callable utility.
> - Pointer arguments passed into VF helpers must stay in `__ubuf__` address space.
> - If the same capability exists in both a kernel-side and a VF-function-safe form, verify the
>   namespace, parameter style, and mask/control contract before coding.

The last bullet is the one that turns this from bookkeeping into a procedure: verification is of three
things — namespace, parameter style, and mask/control contract — not of a name.

**This rule was exercised twice during this harvest, and both times it worked.** For `MulDstAdd`
(0246): absent from the whitelist, found declared in
`include/ascendc/basic_api/interface/reg_compute/kernel_reg_compute_vec_fused_intf.h:39-40` as a
`__simd_callee__` template, with a dtype set differing from its sibling's — which resolved B1 and
revealed the whitelist gap rather than a spelling dispute. For the `MicroAPI` alias (0244): upstream
named `kernel_macros.h` and the declaration was found at line 136 exactly as stated. Two cases is not a
verification of the procedure, but it is worth recording that the named authority answered both times,
because a rule pointing at an authority that turns out to be silent is a different and worse rule.

## 4 · Procedure
Runnable later. The rule is a procedure, so what §4 establishes is whether the procedure's *output* is
trustworthy — specifically whether "present in headers" implies "usable in a VF".

Arm A — the grep step, as the rule names it, over the four roots. `grep -R`, never `-r`: these trees are
symlink farms and `-r` does not follow symlinked directories, so a negative obtained with `-r` is not a
negative. Run both and compare hit counts; a difference voids any past negative on that path. Record the
root, file, line and full declaration — not merely "found".

Arm B — the sufficiency test, which is what this entry adds over "run a grep". Take a sample of APIs
declared in `reg_compute/` but **absent from the whitelist** — `MulDstAdd` is one, and Arm A's
enumeration will supply the rest — and for each compile a minimal `__simd_vf__` that calls it. Record:
does it resolve; does it accept the design's dtype; does its mask parameter behave as the whitelist's
listed neighbours do. An API that greps clean and fails any of the three is the case that makes the rule
insufficient as stated.

Arm C — the partition test, the reverse direction. Take a sample of APIs the whitelist lists as
kernel-side (`VF Function? = No`) — `DataCopy`, `PipeBarrier`, `ReduceSum` — and attempt to call each
from inside a `__simd_vf__`. Upstream's partition predicts these fail. If any succeeds, the whitelist's
`VF Function?` column is advisory rather than binding, which changes what a generated kernel may rely on.

Arm D — the coverage measurement, a file read needing no device, and the one that prices the whitelist.
Enumerate every symbol declared in `include/ascendc/basic_api/interface/reg_compute/` and diff against
the whitelist's VF-safe tables. The size of that difference is how often the escape hatch will be
needed; a large difference means the rule is the primary path rather than an exception, which is worth
knowing before generating guidance from the tables alone.

No device is needed for Arms A and D. For Arms B and C, device selection is explicit: the operator names
the device index, the probe prints it back with `compiler/version.info` and the resolved SoC string,
occupancy is checked first (shared machine, ≤4 dies), and no die is substituted for another.

## 5 · Checker — acceptance declared before the run
Verdict variable `header_presence_is_sufficient`, from Arm B — declared FALSE-on-any-hit: it is false as
soon as one API that greps clean fails to resolve, fails on the design's dtype, or differs in mask
contract from its listed neighbours. Process exit code is not the verdict; in Arm C a failed compile is
the expected outcome.

A false verdict does **not** fail this entry. It sharpens the rule: the honest form would then be
"verify in the headers *and* compile a call", and the delivered skill would carry that third step. Declaring that
now is the point — a procedure entry whose checker can only confirm the procedure is a procedure entry
that will never improve.

`vf_partition_is_binding` (Arm C) — pass iff every whitelist-kernel-side API fails to compile inside a
VF. Any success is reported with the API named, and demotes the `VF Function?` column from a constraint
to a recommendation.

`whitelist_coverage` (Arm D) — the count and list of `reg_compute/` symbols with no whitelist row. No
pass threshold: a non-empty list is the whitelist's honest boundary, not a defect, and it is the number
that says how load-bearing this rule is.

The positive fixture, declared before the run: Arm A must be shown to go red on a name known to be
absent from both the whitelist and the headers — grep for a deliberately misspelled
`MulDstAddd`. It must return nothing from all four roots. If it returns a hit, the search is matching
substrings or the wrong tree, and every "found" result it produced is void. A second fixture for Arm B:
include one API that *is* whitelisted and *is* VF-safe (`Reg::Add`); it must compile. If it fails, the
harness cannot compile a valid VF at all and every failure it reported is an artefact.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

Two greps were performed during this harvest under the sanctioned phase-1 read-only exception, and both
are file reads rather than runs: the FMA search that located `MulAddDst` and `MulDstAdd` in two
`reg_compute/` interface headers (0246 §3), and the alias search that located
`kernel_macros.h:136` (0244 §3). Both found what the rule predicted they would. Neither compiled
anything, so neither establishes that a header-present API is callable from a VF — which is Arm B and is
this entry's actual open question.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled. The entry does not establish that header presence implies VF usability — Arm B is
open, and 0246 already shows that "present" and "usable for a given dtype" come apart by six type
families on the one API pair examined. It does not establish that the whitelist's `VF Function?` column
is enforced by anything (Arm C), nor how much of the `reg_compute/` surface the whitelist omits (Arm D);
the second is a file read and is the cheapest open item here. It does not establish that the four header
roots are the *right* authority — upstream names them and this harvest found them responsive twice,
which is two cases, not a property. BOARD is `family-claimed(unverified)`: a whitelist rule and a header
declaration are source-level facts naming no board, and none was contacted; Arms B and C would establish
their results only for the board they ran on. The two greps are pinned to toolkit `9.0.0-beta.2`, host
directory `arm64-linux`/`include/ascendc`, one machine — upstream's own instruction to cite logical
roots rather than absolute paths exists because a different install may differ. Finally, this entry says
nothing about what the whitelist's tables *contain*; it covers only what to do when they do not contain
what you need.
