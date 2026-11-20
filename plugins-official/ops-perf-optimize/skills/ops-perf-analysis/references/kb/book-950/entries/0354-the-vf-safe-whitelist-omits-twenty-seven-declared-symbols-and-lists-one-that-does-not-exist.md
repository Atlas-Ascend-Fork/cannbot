```
ID:        0354-the-vf-safe-whitelist-omits-twenty-seven-declared-symbols-and-lists-one-that-does-not-exist
LABEL:     trap
LEVEL:     L8 (toolchain & build)
STRATUM:   corroborated — two independent origins: upstream's Regbase API whitelist, and the
           INSTALLED CANN 9.0.0-beta.2 interface headers on this machine, enumerated by file read.
           Nothing was compiled; no call was resolved by a toolchain.
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-regbase-best-practice/references/knowledge/api/regbase_api_whitelist.md:26 —
           "If an API is absent from the lists below, treat it as unavailable until you verify it in
           the installed SDK headers and update the design instead of guessing."
SOURCE:    same file:75-82 — the eight VF-Function-Safe rows, whose function names are `Abs`, `Relu`,
           `Exp`, `Sqrt`, `Ln`, `Log`, `Log2`, `Log10`, `Neg`, `Not`, `Add`, `Sub`, `Mul`, `Div`,
           `Max`, `Min`, `And`, `Or`, `Xor`, `MulAddDst`, `Mull`, `Adds`, `Muls`, `Divs`, `Maxs`,
           `Mins`, `ShiftLefts`, `ShiftRights`, `Compare`, `Compares`, `Select`, `Reduce`,
           `ReduceDataBlock`, `PairReduceElem`, `LoadAlign`, `StoreAlign`, `LoadUnAlignPre`,
           `LoadUnAlign`, `StoreUnAlign`, `StoreUnAlignPost`, `Load`, `Store`, `Gather`, `Scatter`,
           `CreateMask`, `UpdateMask`, `Pack`, `UnPack`, `Move`, `LocalMemBar` — plus a traits row of
           eleven type and enum names.
SOURCE:    INSTALLED TOOLKIT, independent origin — CANN `Version=9.0.0-beta.2`,
           `innerversion=V100R001C10SPC001B214`, `timestamp=20260328_213255003`, aarch64 —
           `include/ascendc/basic_api/interface/reg_compute/*.h` declare **76 distinct
           `__simd_callee__` function names** inside `namespace AscendC { namespace Reg {`.
           Twenty-seven of them appear in no whitelist row: `AbsSub`, `AddC`, `Arange`, `Axpy`,
           `Cast`, `ClearSpr`, `CreateAddrReg`, `DeInterleave`, `Duplicate`, `ExpSub`, `GatherB`,
           `Histograms`, `Interleave`, `LeakyRelu`, `MaskDeInterleave`, `MaskGenWithRegTensor`,
           `MaskInterleave`, `MoveMask`, `MulDstAdd`, `MulsCast`, `Prelu`, `ShiftLeft`, `ShiftRight`,
           `Squeeze`, `SubC`, `Truncate`, `Unsqueeze`.
SOURCE:    same toolkit — `Divs`, listed in the whitelist's Scalar-reg-compute row, appears **nowhere**
           under `include/ascendc/basic_api/interface/reg_compute/` (0 hits) and only in the
           kernel-side `include/ascendc/basic_api/interface/kernel_operator_vec_binary_scalar_intf.h`.
           Its six row-mates `Adds`, `Muls`, `Maxs`, `Mins`, `ShiftLefts`, `ShiftRights` are each
           declared once in `kernel_reg_compute_vec_binary_scalar_intf.h`.
INDEX:     none — nothing measured; see SOURCE. Both counts are re-derivable by file read:
           grep -hoP '__simd_callee__ inline \w+ \K\w+(?=\()' $ASCEND_HOME_PATH/include/ascendc/basic_api/interface/reg_compute/*.h | sort -u
           grep -Rc "Divs" $ASCEND_HOME_PATH/include/ascendc/basic_api/interface/reg_compute/
OVERTURN:  a `Reg::Divs` declaration in any reg-compute header of any toolkit pin — the listed-but-
           absent half of this claim would then be a pin artefact rather than a table error. For the
           other half: a whitelist revision listing the twenty-seven, or evidence that some of them
           are deliberately excluded as unsupported rather than merely omitted.
```

# 0354 · The VF-safe whitelist omits twenty-seven declared symbols and lists one that does not exist

## 1 · Claim
Upstream asserts a gate: an API absent from the whitelist's tables is to be treated as unavailable
until verified in the installed SDK headers. Upstream's VF-function-safe tables list fifty function
names and eleven traits. Not established here: nothing was compiled.

Read in the installed CANN 9.0.0-beta.2 interface headers, an independent origin: the public
`reg_compute/` directory declares seventy-six distinct `__simd_callee__` function names in
`namespace AscendC::Reg`. Twenty-seven of those appear in no whitelist row. In the other direction,
one name the whitelist lists as VF-safe — `Divs` — is declared in no reg-compute header at all; it
exists only in the kernel-side scalar-binary header, while its six row-mates are each declared in the
reg-compute one.

The inference, stated separately: the whitelist is a sample of the VF-safe surface rather than an
enumeration of it, and its absence rule is therefore load-bearing for roughly a third of that surface.
The `Divs` row is a defect of the opposite kind, which the absence rule structurally cannot catch.

## 2 · The wrong branch this removes
The two halves fail in opposite directions and only one of them has a documented recovery.

**Omission.** Twenty-seven names is not a rounding error; it includes families a real kernel needs.
`Cast` is absent from the VF-safe tables — and casting is the central operation of every fp16/bf16
route the same subtree recommends (0357). `Duplicate` and `Arange` are how a VF gets a constant or an
index vector. `Interleave`/`DeInterleave` and `Pack`/`UnPack` are the layout half of the b16 story
(0257). `Axpy`, `AddC`, `SubC`, `AbsSub`, `ExpSub`, `MulsCast`, `Truncate`, `Prelu`, `LeakyRelu` are
fused forms that exist precisely so a chain does not have to be written as three instructions. An
agent obeying the gate literally will decompose `Cast` into something else, or route out of the VF, or
report that the operation is unavailable — three wrong answers with the same cause. The absence rule
is the recovery, and 0245 records that it works; this entry supplies the missing magnitude, which is
that the rule is needed about once in every three lookups, not occasionally.

**Commission.** `Divs` is the harder half, because the prescribed procedure runs backwards over it.
The gate says: absent from the tables → check the headers. It says nothing about present in the tables,
because presence is supposed to be the safe state. So an agent that wants `Reg::Divs(dst, src, scalar)`
inside a VF finds it listed, VF-safe, `Yes`, in the right header root — and skips the header check,
because the rule told it to check only on absence. The failure is a compile error at a call the agent
has already validated by the book, and the agent's first hypothesis will be a wrong include, a wrong
namespace, or a toolkit pin problem, because the one thing it has evidence *for* is that the API is
supported.

Worse, there is a plausible-looking wrong repair sitting next to it: `AscendC::Divs` (kernel-side)
does exist. An agent that drops the `Reg::` qualification to make the error go away has moved a
kernel-side `LocalTensor` API into a VF body, which is exactly the confusion 0250 exists to prevent,
and it will have done so while following the whitelist.

Note what a *checker* over this repo would and would not catch. A tool that verifies "every API used in
generated code appears in the whitelist" goes green on `Reg::Divs` and red on `Reg::Cast`. It is
precisely inverted relative to reality. A checker whose fixture is "the whitelist accepts what we
write" cannot discover that the whitelist is wrong in both directions — the same blind species this
book keeps recording, here applied to the gate rather than to the code.

## 3 · Ground / Source
The gate is quoted in SOURCE; the two guardrails that partly anticipate the problem are
`regbase_api_whitelist.md:104` and `:112`:

> - If a helper would need to call another VF helper, stop and re-check the design. The safe callable
>   surface inside VF functions is the `__simd_callee__` family from `reg_compute/`.

> - If the task needs an API that is not listed here, verify the SDK header family first and update the
>   design rather than filling the gap with speculation.

`:104` is the interesting one: it names the real criterion — `__simd_callee__` in `reg_compute/` — which
is exactly the predicate used to produce the seventy-six-name enumeration in SOURCE. So the document
knows what the true surface is defined by, states it as a guardrail, and then ships tables that cover
two-thirds of it. The repair is placement: the tables and the predicate are two representations of one
set, maintained separately, and one drifted. Fixing the twenty-seven names by hand would leave the
generator that produced the drift intact and the defect returns with the next SDK release.

The enumeration method matters, so it is stated rather than summarised. The predicate is
`__simd_callee__ inline <ret> <Name>(` at the start of a declaration in
`include/ascendc/basic_api/interface/reg_compute/*.h`. On this machine
`$ASCEND_HOME_PATH/include/ascendc` resolves to `aarch64-linux/asc/include`, and `arm64-linux` is a
symlink to `aarch64-linux`, so the whitelist's declared root and the enumerated path are the same files.
The predicate has two known blind spots, both recorded here because they bound the count: it misses any
declaration whose return type or attribute order differs, and it misses names introduced only in impl
headers — `Reg::DataCopy` is exactly such a name (0351) and is therefore **not** in the seventy-six.
So twenty-seven is a lower bound on the omission, not a measurement of it.

The whitelist's traits row accounts for eleven of the twelve tokens that appear in the tables and not in
the function enumeration — `LoadDist`, `StoreDist`, `CastTrait`, `CMPMODE`, `RoundMode`,
`MaskMergeMode`, `PostLiteral`, `DataCopyMode`, `ReduceType`, `PairReduce`, `MaskReg` — and those are
types, correctly listed and correctly not functions. The twelfth is `Divs`, which the whitelist places
in a *function* row alongside six names that all resolve. That asymmetry is what makes it a defect
rather than a category difference.

`MulDstAdd` appears in the twenty-seven, and is already carried by 0246: it is declared in
`kernel_reg_compute_vec_fused_intf.h` and absent from the whitelist. That entry resolved B1 by finding
it; this entry supplies the context that it was one of twenty-seven, i.e. that finding it was not luck.
`GatherB` sits next to `Gather` in the same header and is likewise unlisted — a second instance in the
same row as a listed name, which is the shape hardest for a reader to notice.

## 4 · Procedure
Two of the three arms are file reads and need no device. The compile arm is what turns a name list into
an availability claim.

Arm A — the enumeration, re-derived independently of the shortcut in INDEX. Parse each
`reg_compute/*.h` with a real C++ parser (or `clang -Xclang -ast-dump` on a TU that includes
`kernel_reg_compute_intf.h` with `__NPU_ARCH__=3510`) and list every function template in
`AscendC::Reg`. Compare against the grep-derived seventy-six. A larger AST-derived count means the grep
predicate missed declaration forms, and the omission count rises; the delta is itself the readout, and
it is the honest way to bound §3's stated blind spots rather than merely disclosing them.

Arm B — availability, per name, which is the claim the whitelist actually makes. For each of the
twenty-seven omitted names and for `Divs`, compile a minimal VF for a 3510 target that calls it with
plausible arguments, and record: resolves / does not resolve / resolves but rejected inside
`__VEC_SCOPE__`. The third outcome is the one the whitelist's `VF Function?` column is about, and no
file read can reach it — a `__simd_callee__` attribute is a declaration, not a guarantee that the
compiler accepts the call in a VF context. Predicted: twenty-seven resolve, `Divs` does not.

Arm C — the `Divs` diagnostic, recorded verbatim. §2 predicts the agent's first hypothesis will be a
wrong include. The exact message is the deliverable, because it is what a debugging agent will search
for, and because "no member named 'Divs' in namespace 'AscendC::Reg'" is indistinguishable from a
typo unless someone has written down that the name is in the whitelist and not in the SDK.

Arm D — pins, no device. Repeat the two INDEX greps against every other CANN tree on this machine
(`cann-8.5.0`, `ascend-toolkit`, `cann`) and report per pin whether `Reg::Divs` exists. A pin where it
does exist converts this from a table error into version skew and is the OVERTURN condition; looking
for it is cheap and must not be skipped because the current pin already gave the more interesting
answer.

Device selection, for Arms B and C: no die is needed to compile, but if the build is run on the shared
machine the operator names the device index, the harness prints it back with `compiler/version.info`
and the resolved SoC string, and occupancy is checked (≤4 dies).

## 5 · Checker — acceptance declared before the run
`omitted_count` (Arms A, B) — the number of `Reg::` VF-safe symbols that resolve and appear in no
whitelist row. Reported, not gated; there is no correct value to declare, and the point is the
magnitude. It is separated from the enumeration count on purpose: a name that is declared and does not
resolve is a different fact from a name that is declared and unlisted, and merging them would let a
large enumeration stand in for a large availability gap.

`divs_resolves` (Arms B, C, D) — false iff `Reg::Divs` fails to resolve on this pin. Pass condition is
**false**, i.e. the checker is written to confirm an absence. That inverts the usual reading, so it is
stated plainly: a `true` here overturns half this entry, and that is the point of writing it down
before the run.

`listed_and_absent_count` — the full reverse diff: every whitelist function-row name that fails Arm B.
Predicted 1. A larger number means the tables drifted in both directions, which changes the delivered skill's
posture from "the tables under-report" to "the tables are unreliable in both directions and the header
is the only source".

The positive fixture, declared before the run: Arm B must include three controls — `Reg::Exp` (listed
and declared, must resolve), `Reg::MulDstAdd` (unlisted and declared, must resolve, per 0246), and
`Reg::NoSuchApiXyz` (neither, must fail). If the first two do not resolve, the build harness is broken
and every "does not resolve" result is an artefact; if the third resolves, the compile is not actually
type-checking the call and every "resolves" result is an artefact. Both directions are needed: a
fixture that only checks "the good name works" is the known blind species, and a fixture that only
checks "the bad name fails" cannot distinguish a working harness from one that rejects everything.

Process exit codes are not the verdict: in Arm B a compile failure is the expected and informative
outcome for one of the twenty-eight names.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No translation unit was
compiled, no call resolved, no die contacted. The seventy-six-name enumeration, the twenty-seven-name
difference and the `Divs` absence are file reads over the installed CANN 9.0.0-beta.2 headers performed
under the phase-1 sanctioned read-only exception; they establish what the headers contain and nothing
about what a compiler accepts.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled. The entry does not establish that the twenty-seven omitted names are *usable* —
`__simd_callee__` on a declaration is not the same as the compiler accepting the call inside
`__VEC_SCOPE__`, and Arm B is what would close that. It does not establish that `Reg::Divs` is
unusable, only that it is undeclared in the reg-compute interface headers of this one pin; Arm D is what
would distinguish a table error from version skew, and it has not run.

The count of twenty-seven is a **lower bound, by construction**. The grep predicate matches one
declaration form; any symbol declared with a different attribute order, a different return-type spelling,
or only in an impl header is missed. `Reg::DataCopy` is a known missed instance (0351). An AST-derived
count (Arm A) is the only honest number and does not exist yet.

It does not establish *why* any name is omitted. "Omitted" and "deliberately excluded as unsupported"
are different states with the same appearance in a table, and no upstream text distinguishes them for
any of the twenty-seven. Treating omission as a defect is this entry's reading and is not upstream's
statement.

It says nothing about the kernel-side tables, which were not enumerated against
`basic_api/interface/`; the same drift may exist there and has not been looked for. It says nothing
about the `adv_api` families in the third table. It says nothing about parameter signatures,
mask contracts, or precision contracts of any name — only about presence, which is the one axis the
whitelist claims to cover and the least of the four `Q-950arch-29` asks for.

BOARD is `family-claimed(unverified)`: a header enumeration names no board, and no board was contacted.
