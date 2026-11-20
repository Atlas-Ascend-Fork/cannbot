```
ID:        0244-microapi-is-a-namespace-alias-for-reg-not-a-second-api-family
LABEL:     knowledge
LEVEL:     L8 (toolchain & build)
STRATUM:   corroborated — upstream states the aliasing and names the header that defines it; the
           INSTALLED CANN 9.0.0-beta.2 toolkit is an independent origin for the same claim. Nothing
           was compiled.
BOARD:     family-claimed(unverified)
           # a namespace alias is a source-level fact; no board is named by either origin and none
           # was contacted.
SOURCE:    ops/ascendc-regbase-best-practice/references/knowledge/api/regbase_api_whitelist.md:29-38
           — "In open-source kernels, the same VF-safe surface often appears through the alias
           `AscendC::MicroAPI::*`." … "`$ASCEND_HOME_PATH/asc/impl/basic_api/kernel_macros.h` —
           Defines `namespace MicroAPI = Reg;`, which is why many open-source kernels call the same
           VF-safe surface as `AscendC::MicroAPI::*`."
SOURCE:    INSTALLED TOOLKIT, independent origin — CANN `Version=9.0.0-beta.2`,
           `innerversion=V100R001C10SPC001B214`, 950-era (ships `dav_c310` / `npu_arch_3510` trees
           and 32 `Ascend950{PR,DT}_*.ini` with `NpuArch=3510`) —
           `arm64-linux/asc/impl/basic_api/kernel_macros.h:136`: `namespace MicroAPI = Reg;`
           inside `namespace AscendC`, exactly the file and declaration upstream names.
INDEX:     none — nothing measured; see SOURCE. Re-derivable by file read:
           grep -RIn "namespace MicroAPI" $ASCEND_HOME_PATH/asc/impl/basic_api/ $ASCEND_HOME_PATH/include/ascendc/
OVERTURN:  a toolkit in which `AscendC::MicroAPI::X` and `AscendC::Reg::X` resolve to different
           functions for any X, or in which one resolves and the other does not — the alias would
           then be a partial re-export rather than a namespace alias.
```

# 0244 · `MicroAPI` is a namespace alias for `Reg`, not a second API family

## 1 · Claim
Upstream asserts that `AscendC::MicroAPI::*` and `AscendC::Reg::*` are the same VF-safe API surface
under two spellings, that the aliasing is established by `namespace MicroAPI = Reg;` in
`$ASCEND_HOME_PATH/asc/impl/basic_api/kernel_macros.h`, and that open-source Regbase kernels commonly
use the `MicroAPI` spelling. Upstream instructs the reader to treat the two as one family — "an
aliasing style difference, not a second whitelist" — unless local code adds its own wrapper layer on
top. Not established here: nothing was compiled, and the alias declaration was not located in the
installed headers.

## 2 · The wrong branch this removes
This is the vocabulary entry the rest of the Regbase block leans on, and without it an agent reading
two upstream libraries concludes there are two API surfaces.

The perf-optimize card library speaks `MicroAPI` throughout — its 24 technique cards are declared "A5
（arch3510）RegBase" and its code uses MicroAPI spellings. The regbase-best-practice whitelist speaks
`Reg::*` and is the document that says which calls are legal inside a VF. An agent that treats them as
distinct families has two immediate wrong branches. It may look for `MicroAPI` in the whitelist, find
nothing, and apply the whitelist's absence rule — "absent from the lists → treat as unavailable"
(0245) — rejecting the entire card library as unverified. Or it may conclude the whitelist governs only
`Reg::*` code and that `MicroAPI` code is outside its scope, which removes the one document that scopes
VF-callable surface at all.

Both are the same error as B1's (0246) with a wider blast radius: there the confusion was one API name,
here it is every name in the library.

The third branch runs the other way and is why upstream's qualifier matters. Treating the two as
interchangeable is right for the vendor surface and wrong the moment a local project defines its own
`MicroAPI` wrapper — which upstream explicitly allows for ("unless the local code adds its own wrapper
layer on top"). An agent that has internalised "MicroAPI ≡ Reg" will read a project's wrapper as the
vendor API and mis-attribute its behaviour. The alias is a fact about the vendor headers, not a
guarantee about every occurrence of the token.

## 3 · Ground / Source
`regbase_api_whitelist.md:27-38`, the file's opening and its Header Reference Roots section — quoted
together because the alias claim and the header that backs it are stated in different paragraphs:

> This file is the local launch gate for regbase direct-invoke work. It separates ordinary regbase
> kernel-side APIs from VF-function-safe APIs so design and review do not mix `LocalTensor`-style
> assumptions with `AscendC::Reg::*` reg-compute semantics. **In open-source kernels, the same VF-safe
> surface often appears through the alias `AscendC::MicroAPI::*`.** If an API is absent from the lists
> below, treat it as unavailable until you verify it in the installed SDK headers and update the design
> instead of guessing.
>
> ## Header Reference Roots
> Use these SDK roots as the primary verification source. Do not replace them with
> environment-specific absolute paths in design or review notes.
>
> - `$ASCEND_HOME_PATH/include/ascendc/basic_api/interface/`
>   Ordinary kernel-side AscendC interfaces such as `DataCopy`, vector `LocalTensor` compute,
>   barriers, and event sync.
> - `$ASCEND_HOME_PATH/include/ascendc/basic_api/interface/reg_compute/`
>   `AscendC::Reg::*` interfaces and support types that are valid call targets inside VF functions.
> - `$ASCEND_HOME_PATH/include/ascendc/include/adv_api/`
>   Task-specific higher-level regbase helpers such as norm, pad, transpose, select, and quantization
>   families.
> - `$ASCEND_HOME_PATH/asc/impl/basic_api/kernel_macros.h`
>   Defines `namespace MicroAPI = Reg;`, which is why many open-source kernels call the same VF-safe
>   surface as `AscendC::MicroAPI::*`.

The fourth root is the one that carries this entry: upstream names a specific header and quotes the
specific declaration. That is an unusually checkable claim for this material, and it is the reason this
entry can reach `corroborated` while its neighbours cannot.

The reading rules, `:53-59` (Scope Rules) and `:105-111` (VF-Specific Guardrails):

> - When reading open-source code, treat `AscendC::MicroAPI::*` as the same VF-safe API family unless
>   the local code adds its own wrapper layer on top.
> - Treat `AscendC::Reg::*` as the default API surface once you are inside a VF function. When source
>   code uses `AscendC::MicroAPI::*`, read it as the same VF-safe family.

and `:40`, a small piece of housekeeping worth keeping because it names a third spelling:

> Existing knowledge cards may record the same SDK sources with the shorthand `$INCLUDE_DIR/...`.
> Treat that as the same logical header root, not as a second API surface.

So the file is explicitly in the business of collapsing spellings onto one surface, and names three of
them (`Reg::*`, `MicroAPI::*`, `$INCLUDE_DIR` paths).

**Second origin — the installed toolkit**, read under the phase-1 read-only exception; no compilation,
no execution. The toolkit is CANN `Version=9.0.0-beta.2`, `innerversion=V100R001C10SPC001B214`, and is
950-era on three independent indications (0246 §3): 32 `Ascend950{PR,DT}_*.ini` files with
`NpuArch=3510`, an `asc/impl/basic_api/reg_compute/dav_c310/` tree, and an
`asc/impl/c_api/instr_impl/npu_arch_3510/` tree.

The declaration, located during this harvest at
`arm64-linux/asc/impl/basic_api/kernel_macros.h:128-137`, verbatim with its context:

```cpp
#define ASCEND_IS_AICORE constexpr(true)
#else
#define ASCEND_IS_AICORE constexpr(false)
#endif

namespace AscendC {
namespace Reg {
} // namespace Reg
namespace MicroAPI = Reg;
} // namespace AscendC
#endif // ASCENDC_KERNEL_MACROS_H
```

Upstream named the file and quoted the declaration; both are exactly as stated. Two details the
upstream quote does not carry and which matter for §4. First, the alias is declared **beside an empty
`namespace Reg { }` block** — the block exists only to make the name available so the alias is
well-formed at this point in the translation unit. So `kernel_macros.h` establishes the alias without
declaring any of the API; the members arrive later, from
`include/ascendc/basic_api/interface/reg_compute/`. That is the correct construction and it means the
alias covers whatever is subsequently added to `Reg` — which is what makes it a namespace alias rather
than a re-export, and is the strongest available argument for Arm C's expected result.

Second, the search was run once with `grep -R` and once with `grep -r` over
`asc/impl/basic_api/`, returning one file each. So no symlinked directory hid a second declaration on
this path, and the negative half of the result is trustworthy — which is not automatic in these trees.

What the second origin therefore covers: the header root's existence, the `Reg::*` surface's existence
(0246 quotes two of its interface headers verbatim), and the alias declaration itself. What it does not
cover is resolution — a declaration read is not a compile, and Arm B is what shows the two spellings
name the same function rather than merely making the same names visible.

## 4 · Procedure
Runnable later; both decisive arms need no device and should run first.

Arm A — locate the declaration, file read only. **Already performed** during this harvest (§3); it is
kept here because it is the re-derivation step a consumer must be able to repeat on its own toolkit:

```bash
grep -RIn "namespace MicroAPI" "$ASCEND_HOME_PATH/asc/impl/basic_api/" \
                               "$ASCEND_HOME_PATH/include/ascendc/"
```

`grep -R`, not `-r` — these trees are symlink farms and `-r` does not follow symlinked directories; run
both and compare hit counts, since a silently short file list produces a confident negative. Record the
file, the line, and the exact declaration. Upstream predicts `kernel_macros.h`; a different file is a
finding, and absence is a bigger one.

Arm B — resolution equivalence, compile only. Two translation units, identical but for the namespace,
each calling the same VF-safe function inside a `__simd_vf__`:

```cpp
AscendC::Reg::MulAddDst(dR, aR, bR, m);        // TU1
AscendC::MicroAPI::MulAddDst(dR, aR, bR, m);   // TU2
```

Both must compile for a 3510 target. Then the stronger form: in a *third* TU, take the address of both
and require them equal at compile time —

```cpp
static_assert(&AscendC::Reg::MulAddDst<float, AscendC::Reg::MaskMergeMode::ZEROING, RegT>
           == &AscendC::MicroAPI::MulAddDst<float, AscendC::MicroAPI::MaskMergeMode::ZEROING, RegT>,
              "MicroAPI is not an alias of Reg");
```

A namespace alias makes that trivially true; a partial re-export or a wrapper layer makes it false or
ill-formed. This is what distinguishes an alias from two surfaces that happen to agree on names, and it
is the arm that tests the actual claim.

Arm C — the extent of the alias. Enumerate the symbols declared in
`include/ascendc/basic_api/interface/reg_compute/` and, for each, compile a use under both spellings.
A namespace alias covers the whole namespace by construction, so any symbol reachable under one
spelling and not the other falsifies "alias" in favour of "partial re-export". This is mechanical and
needs no device.

Arm D — the wrapper caveat, which is upstream's own qualifier and the one thing here that is not a
vendor fact. Take one open-source Regbase kernel from
`references/reference-ops/open_source_operator_table.md` and check whether its `MicroAPI` calls resolve
to the vendor namespace or to a project-local wrapper. The method is a build with `-E` and a grep for
the resolved declaration, not a reading of the call site — the call site is exactly what cannot
distinguish the two.

No device is needed for any arm. If a board is used later to confirm runtime equivalence, device
selection is explicit: the operator names the device index, the probe prints it back with
`compiler/version.info`, occupancy is checked first (shared machine, ≤4 dies), and no die is
substituted for another.

## 5 · Checker — acceptance declared before the run
Verdict variable `is_namespace_alias`, and it is deliberately **not** satisfiable by Arm B's first half.
Two TUs both compiling shows the names exist in both namespaces; it does not show they name the same
function, which is the claim.

Pass requires all three: Arm A locating a `namespace MicroAPI = Reg;` declaration (file and line
recorded — **satisfied**, `kernel_macros.h:136`); Arm B's `static_assert` compiling; and Arm C finding
no symbol reachable under one spelling and not the other. Arms B and C remain open, so the verdict is
currently `NOT ESTABLISHED`, not a pass.

Failure modes are named now so none can be reinterpreted afterwards. Arm B's `static_assert` failing
while both TUs compile means `MicroAPI` is a wrapper or a re-export, not an alias — a materially
different fact, and the entry is corrected in place. Arm C finding an asymmetric symbol means the same.
Arm A having succeeded on this toolkit says nothing about another: a consumer whose grep returns nothing
must drop this entry to one origin rather than assume the declaration is present.

The positive fixture, declared before the run: run Arm C's comparison with one symbol name deliberately
misspelled in the `MicroAPI` arm. It must be reported as reachable under `Reg` and not under
`MicroAPI`. If the comparison reports it symmetric, the enumeration is not actually compiling each
symbol under both spellings and every symmetric result it produced is void. Without this the checker
only reads "nothing came up asymmetric", which is the known blind species — a comparison that never
fires is indistinguishable from a comparison that always agrees.

A second guard, on Arm A specifically: the search must be run once with `grep -R` and once with
`grep -r` and the two hit counts recorded. If they differ, the tree contains symlinked directories on
the search path and any past negative result obtained with `-r` is void. Process exit codes are not the
verdict anywhere — in Arm B's failure mode a non-zero exit is the informative outcome.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

On the toolkit contact: **a header grep is a file read, not a run.** What it established is that
`arm64-linux/asc/impl/basic_api/kernel_macros.h:136` contains `namespace MicroAPI = Reg;` inside
`namespace AscendC`, beside an empty `namespace Reg { }` block, on this toolkit
(`Version=9.0.0-beta.2`, `innerversion=V100R001C10SPC001B214`), and that `grep -R` and `grep -r` agree
on one hit so no symlinked directory hid a second declaration. It does not establish that the two
spellings resolve to the same function: no translation unit was compiled, no symbol was resolved, no
`static_assert` was evaluated, and no device was contacted. Arms B, C and D are open.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled. The entry does not establish that the two spellings resolve to identical
functions; two namespaces can carry the same names without being aliases, which is exactly what Arm B's
`static_assert` exists to separate and what makes a "both compiled" result insufficient. A declaration
read at `kernel_macros.h:136` is strong evidence of intent and is not resolution — the header could be
excluded from a given build, shadowed by a project-local `MicroAPI`, or superseded later in the
include order, and none of those is visible to a grep. It does not establish the alias's extent: an alias covers a whole
namespace, a re-export need not, and Arm C is open. It does not establish anything about
project-local `MicroAPI` wrappers, which upstream explicitly allows for and which would make an
otherwise-correct reading wrong at one call site; Arm D is the only thing here that addresses them.
BOARD is `family-claimed(unverified)` because a namespace alias is a source-level fact that names no
board, and none was contacted — the alias would hold or fail identically on 950PR and 950DT and this
entry claims neither. The toolkit reading is pinned to `9.0.0-beta.2`, host directory `arm64-linux` and
`include/ascendc`, one machine; a different CANN version may define the alias elsewhere or not at all,
and upstream's own instruction is to cite the `$ASCEND_HOME_PATH`-relative roots rather than absolute
paths for exactly that reason. Finally, this entry says nothing about *which* APIs are VF-safe — that is
the whitelist's content (0245, 0250) — only that the two namespaces name one surface.
