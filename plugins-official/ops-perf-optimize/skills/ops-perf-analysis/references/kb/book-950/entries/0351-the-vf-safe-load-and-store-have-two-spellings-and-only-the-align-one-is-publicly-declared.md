```
ID:        0351-the-vf-safe-load-and-store-have-two-spellings-and-only-the-align-one-is-publicly-declared
LABEL:     knowledge
LEVEL:     L3 (data movement & layout)
STRATUM:   corroborated — two independent origins: the upstream skills repo, which uses both
           spellings in two different files, and the vendor's INSTALLED CANN 9.0.0-beta.2 headers
           on this machine, which define both and forward each pair to one identical
           implementation. A header read is a second origin of authority, not a run: nothing was
           compiled and no register was loaded.
BOARD:     family-claimed(unverified)
           # the implementations live in the toolkit's `dav_c310` tree; neither origin names a
           # board token this book recognises and no board was contacted.
SOURCE:    ops/ascendc-regbase-best-practice/references/paradigms/common/vf-programming-rules.md:15
           — "**API 选型**：新代码统一走 `LoadAlign` / `StoreAlign`（地址要求 32B 对齐）。"
SOURCE:    ops/ascendc-regbase-best-practice/references/knowledge/patterns/regbase_kernel_dataflow_patterns.md:43,45,102,106
           — "`Reg::*` / `MicroAPI::*` VF-safe loads such as `DataCopy<..., LoadDist::...>`" /
           "VF-safe stores such as `DataCopy<..., StoreDist::...>`" and, in the canonical minimal VF
           body, "`DataCopy<float, LoadDist::DIST_NORM>(vin, inAddr + i * VL);`" /
           "`DataCopy<float, StoreDist::DIST_NORM_B32>(outAddr + i * VL, vout, mask);`"
           # both files are `upstream/skills-dev-main` — ONE origin (RULES.md Art. 3).
SOURCE:    INSTALLED TOOLKIT, independent origin — CANN `Version=9.0.0-beta.2`,
           `innerversion=V100R001C10SPC001B214`, `timestamp=20260328_213255003`, 950-era (ships a
           `dav_c310` reg-compute tree and 32 `Ascend950{PR,DT}_*.ini` with `NpuArch=3510`):
             `include/ascendc/basic_api/interface/reg_compute/kernel_reg_compute_datacopy_intf.h:30-171`
               declares `LoadAlign`, `StoreAlign`, `Load`, `Store`, `LoadUnAlignPre`, `LoadUnAlign`,
               `StoreUnAlign`, `StoreUnAlignPost`, `Gather`, `GatherB`, `Scatter` — and **no**
               `DataCopy` function at all (only the `DataCopyMode` enum appears, as a template
               parameter).
             same file `:175` — `#include "../../impl/basic_api/reg_compute/kernel_reg_compute_datacopy_intf_impl.h"`
             `asc/impl/basic_api/reg_compute/kernel_reg_compute_datacopy_intf_impl.h:33-40` —
               `__simd_callee__ inline void DataCopy(U& dstReg, __ubuf__ T* srcAddr)
                { DataCopyImpl<T, dist, U>(dstReg, srcAddr); }` immediately followed by
               `__simd_callee__ inline void LoadAlign(U& dstReg, __ubuf__ T* srcAddr)
                { DataCopyImpl<T, dist, U>(dstReg, srcAddr); }` — the same body, twice, under two
               names. The pattern repeats for every overload in the file (`:44/:49`, `:55/:60`,
               `:67/:72`, `:78/:83`, `:89/:94`, `:101/:106`, `:112/:117`, `:123/:128`, `:135/:140`,
               `:146/:152`, `:160/:165`, `:171/:177`, `:185/:189`).
             same file `:17` — the header announces itself: "kernel_reg_compute_datacopy_intf_impl.h
               is an internal header file and must not be used directly. Functions or variables
               defined in this file maybe removed in the future."
INDEX:     none — nothing measured; see SOURCE. Both facts are re-derivable by file read on this
           machine:
           grep -n "inline void DataCopy\|inline void LoadAlign" $ASCEND_HOME_PATH/asc/impl/basic_api/reg_compute/kernel_reg_compute_datacopy_intf_impl.h
           grep -c "DataCopy(" $ASCEND_HOME_PATH/include/ascendc/basic_api/interface/reg_compute/kernel_reg_compute_datacopy_intf.h
OVERTURN:  a toolkit in which `Reg::DataCopy` and `Reg::LoadAlign` with the same template arguments
           produce different observable results — different bytes loaded, a different lane count, a
           different fault — or in which one resolves and the other does not. Either would make
           them two APIs rather than two names, and would make upstream's two documents describe
           two different operations rather than one.
```

# 0351 · The VF-safe load and store have two spellings, and only the `Align` one is publicly declared

## 1 · Claim
Upstream asserts two different names for the same job. One file says new Regbase code should use
`LoadAlign` and `StoreAlign` uniformly for UB↔register traffic; another file in the same skill uses
`DataCopy<T, LoadDist::…>` and `DataCopy<T, StoreDist::…>` in its canonical minimal VF body and calls
those "VF-safe loads" and "VF-safe stores". Not established here whether either compiles.

The installed CANN 9.0.0-beta.2 toolkit on this machine — an origin independent of that repo — is
read as follows, and the reading is a file read, not a run. The public interface header
`reg_compute/kernel_reg_compute_datacopy_intf.h` declares `LoadAlign` and `StoreAlign` and contains
no declaration of a function named `DataCopy`. The internal implementation header it includes at its
last line defines **both** names, in adjacent pairs, each pair forwarding to the identical
`DataCopyImpl<...>` instantiation with identical template arguments. That implementation header
prints a message declaring itself internal and subject to removal.

The inference, stated separately from the readings above: in this toolkit the two upstream spellings
name one operation, and the spelling upstream's dataflow document uses is the one the vendor marks
internal. Not established here: nothing was compiled, and no other toolkit pin was inspected.

## 2 · The wrong branch this removes
Without this entry an agent reading the two upstream files has three bad options and no way to choose.

It can conclude the files disagree about the API and pick the more authoritative-looking one. The
whitelist appears to settle it — `DataCopy` sits in the *kernel-side* table with `VF Function? = No`
— so the natural conclusion is that the dataflow pattern file is simply wrong and its canonical VF
body would not compile. That conclusion is wrong: `Reg::DataCopy` exists and is `__simd_callee__`.
An agent that "fixes" working code on the strength of the whitelist has broken nothing and wasted a
cycle, but an agent that concludes the pattern file is untrustworthy discards the only complete VF
body in the subtree.

It can conclude they are two different operations and go looking for the difference — an alignment
contract, a mask contract, a distribution default. There is none to find. The bodies are identical
token-for-token except the function name. Time spent looking for a semantic difference is time spent
on a distinction the headers do not make.

Or it can adopt `DataCopy` because the pattern file's example is the one that reads like real code.
That is the branch this entry actually exists to redirect. The name works today and is defined in a
header whose own first lines say its contents "maybe removed in the future". Generated kernels
written to that spelling carry a dependency on a symbol the vendor has not published in an interface
header, and the failure, when it comes, is a compile break across every generated kernel at once
rather than one operator.

The second-order trap is what the whitelist's `VF Function? = No` row now means. It is not a claim
that no VF-safe `DataCopy` exists; it is a row about the *kernel-side* `DataCopy` that takes
`LocalTensor`, in a table that never mentions the VF-side one. So the whitelist is not wrong on its
own terms and is still misleading when read as an availability oracle — which is precisely how its
own preamble says to read it ("If an API is absent from the lists below, treat it as unavailable").
0245 records the escape hatch; this entry records a case where the hatch has to be used against a row
that is *present* rather than absent, which is the harder case to notice.

## 3 · Ground / Source
`vf-programming-rules.md:13-15` opens the Load/Store section with the choice:

> ## 2 Load / Store
>
> **API 选型**：新代码统一走 `LoadAlign` / `StoreAlign`（地址要求 32B 对齐）。

新代码统一走 — "new code uniformly goes through". That is a directive about which spelling to write,
and its existence implies the author knew another spelling was in circulation. It does not say what
the other one is.

`regbase_kernel_dataflow_patterns.md:41-45` lists the VF body's callable surface:

> 3. **VF body**
>    - `__VEC_SCOPE__`
>    - `RegTensor`
>    - `MaskReg`
>    - `Reg::*` / `MicroAPI::*` VF-safe loads such as `DataCopy<..., LoadDist::...>`
>    - arithmetic / compare / cast / select
>    - `Reg::*` / `MicroAPI::*` VF-safe stores such as `DataCopy<..., StoreDist::...>`

and `:94-108` gives the canonical minimal VF body in full:

> ```cpp
> __VEC_SCOPE__
> {
>     RegTensor<float> vin, vtmp, vout;
>     MaskReg mask;
>
>     for (uint16_t i = 0; i < vfLoopNum; i++) {
>         mask = UpdateMask<float>(size);
>         DataCopy<float, LoadDist::DIST_NORM>(vin, inAddr + i * VL);
>         Exp(vtmp, vin, mask);
>         Adds(vtmp, vtmp, 1.0f, mask);
>         Div(vout, vin, vtmp, mask);
>         DataCopy<float, StoreDist::DIST_NORM_B32>(outAddr + i * VL, vout, mask);
>     }
> }
> ```

The phrase "such as" at `:43` invites a second reading: that `DataCopy<..., LoadDist::...>` is
placeholder shorthand for the load/store family rather than a literal name. **That reading is not the
one the evidence supports.** The code block at `:102` and `:106` is not a schematic — it is a
compilable-looking body with concrete template arguments (`float`, `DIST_NORM`, `DIST_NORM_B32`), and
`Reg::DataCopy` turns out to exist with exactly that signature. The placeholder reading is recorded
here and parked in §7 rather than dismissed, because it changes LABEL: under it this entry is a
`boundary` about documentation shorthand instead of a `knowledge` entry about two real spellings.

The whitelist's two relevant rows, `regbase_api_whitelist.md:64` and `:80`:

> | Data movement | `DataCopy`, `DataCopyPad`, `DataCopyGather`, `DataCopyUnAlignPre`, `DataCopyUnAlign`, `DataCopyUnAlignPost`, `Copy` | No | `basic_api/interface/` |

> | Reg load and store | `LoadAlign`, `StoreAlign`, `LoadUnAlignPre`, `LoadUnAlign`, `StoreUnAlign`, `StoreUnAlignPost`, `Load`, `Store`, `Gather`, `Scatter` | Yes | `basic_api/interface/reg_compute/` |

Read together: the VF-safe row is the `*Align` spelling, and the only `DataCopy` in the document is
the kernel-side one. Nothing in the file says a VF-safe `DataCopy` exists.

The installed toolkit says it does. `$ASCEND_HOME_PATH/include/ascendc` resolves to
`aarch64-linux/asc/include` on this machine (`arm64-linux` is a symlink to `aarch64-linux`), so the
whitelist's own declared header root and the path read here are the same files. In
`reg_compute/kernel_reg_compute_datacopy_intf.h`, inside `namespace AscendC { namespace Reg {`, the
declarations run `LoadAlign` ×6, `StoreAlign` ×5, the `DataCopyMode` strided forms ×4 (again spelled
`LoadAlign`/`StoreAlign`), the UnAlign family, `Load`, `Store`, `Gather`, `GatherB`, `Scatter`, and
the `MaskReg` load/store forms. `DataCopy` appears in that file only as the enum name `DataCopyMode`.

The impl header included at its final line is where the second spelling lives, and the pairing is
mechanical:

> ```cpp
> template <typename T = DefaultType, LoadDist dist = LoadDist::DIST_NORM, typename U>
> __simd_callee__ inline void DataCopy(U& dstReg, __ubuf__ T* srcAddr)
> {
>     DataCopyImpl<T, dist, U>(dstReg, srcAddr);
> }
> template <typename T, LoadDist dist, typename U>
> __simd_callee__ inline void LoadAlign(U& dstReg, __ubuf__ T* srcAddr)
> {
>     DataCopyImpl<T, dist, U>(dstReg, srcAddr);
> }
> ```

Note the one real asymmetry, and it is not semantic: the `DataCopy` overloads carry default template
arguments (`T = DefaultType`, `dist = LoadDist::DIST_NORM`) and the `LoadAlign` twins do not, because
the interface header already supplied the defaults for `LoadAlign`. So a caller writing
`Reg::DataCopy(reg, ptr)` with no template arguments and a caller writing `Reg::LoadAlign(reg, ptr)`
with no template arguments both get `DIST_NORM`, by two different routes.

That the vendor's own advanced-API code uses the internal spelling is worth recording as scope, not
as endorsement: `asc/impl/adv_api/detail/quantization/quant/ascend_quant_per_group_l300_impl.h` calls
`Reg::DataCopy<srcT, Reg::LoadDist::DIST_UNPACK_B16>(...)` and
`Reg::DataCopy<srcT, Reg::LoadDist::DIST_NORM>(...)` at some twenty sites. Implementation files are
not an interface contract, and this entry does not treat them as one.

Related and deliberately not re-entered: 0250 establishes that a kernel-side API and its VF-side
namesake are not interchangeable, over the thirteen names the whitelist dual-lists. `DataCopy` is a
fourteenth instance of that species and is *not* in 0250's list, because the whitelist never lists it
as VF-safe. 0257 establishes the `LoadAlign`/`StoreAlign` alignment and distribution contracts, all
of which apply unchanged to the `DataCopy` spelling since it is the same instantiation. 0244
establishes `MicroAPI` as an alias of `Reg`, so `MicroAPI::DataCopy` is a third spelling of the same
call.

## 4 · Procedure
Runnable later on `950PR`. Two independent questions — do both names resolve, and do they do the same
thing — and they need separate arms because a shared-body reading of the headers is not a compile.

Arm A — resolution. Compile one translation unit for a 3510 target that calls
`AscendC::Reg::LoadAlign<float>(vin, ubPtr)` and one that calls
`AscendC::Reg::DataCopy<float>(vin, ubPtr)`, including only `kernel_operator.h` and whatever the
project's normal kernel prologue is — **not** the internal impl header directly. Record for each:
does it compile, and does the build emit the internal-header message quoted in SOURCE. A compile
failure for `DataCopy` here would mean the reachability observed by file read does not survive the
project's real include set, which is the interesting negative.

Arm B — identity. Build one kernel twice from one source, differing only in the spelling, at
identical inputs on the same die in the same session, and compare outputs bit-for-bit **and**
compare the two disassemblies. Bit-identical outputs alone establish nothing here (two different
loads could agree on this input); the disassembly is the arm that decides, because identical
instruction sequences are what "same instantiation" predicts. This is the arm that would catch the
case where the two names diverge in some overload the header pairing does not cover.

Arm C — the distribution and alignment contracts, carried over. Repeat 0257's Arm C (a `half` buffer
loaded with and without `DIST_UNPACK_B16`) under **both** spellings. If 0257's findings do not
reproduce identically under `DataCopy`, the shared-body reading is wrong and this entry is corrected.

Arm D — the deprecation question, which is the one that matters for the delivered skill and needs no device.
Repeat the two greps in INDEX against every other CANN pin available on the machine
(`/usr/local/Ascend/cann-8.5.0`, `/usr/local/Ascend/ascend-toolkit`, `/usr/local/Ascend/cann`) and
record, per pin, whether `Reg::DataCopy` is declared in the interface header, defined only in the
impl header, or absent. A pin in which it is absent turns "internal" into "removed" and settles what
the delivered skill must emit.

Device selection is explicit: the operator names the device index, the harness prints it back with
`compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared
machine, ≤4 dies), and no die is substituted between arms.

## 5 · Checker — acceptance declared before the run
Three verdict variables, not aggregated.

`both_names_resolve` (Arm A) — true iff both translation units compile. Pass condition is **true**.
A `DataCopy` failure does not overturn the entry; it narrows it to "declared in the impl header and
not reachable through the normal include set", which is a sharper claim than the one written and is
logged as a correction in place.

`spellings_are_one_call` (Arm B) — pass iff outputs are bit-identical **and** the two disassemblies
are identical after symbol renaming. Both clauses are required: outputs alone are the known blind
species here, because the null result ("no difference") is exactly what a weak comparison produces
for free. This is the same failure mode recorded against a performance claim certified with
bit-identical outputs in the parent book — an instrument that cannot distinguish "same" from "not
probed" is not measuring.

`datacopy_is_public` (Arm D) — reported per pin, three-valued: `interface`, `impl-only`, `absent`.
Not gated, because there is no pass state to declare: the deliverable is the table. `absent` in any
newer pin is the observation that decides the delivered skill's recommendation.

The positive fixture, declared before the run: Arm B must include a **third** build that calls
`Reg::LoadAlign` with `DIST_UNPACK_B16` where the other two use `DIST_NORM`. Its output must differ
from both. If all three agree, the comparison harness is not sensitive to a load-behaviour change at
all and `spellings_are_one_call` is void regardless of what it reported — a checker that reads only
"the two builds agreed" cannot tell agreement from blindness. A second fixture for Arm A: a
deliberately misspelled `Reg::LoadAlgin` must fail to compile, or the build is not actually
type-checking the call.

Process exit codes are not the verdict for Arm A: the compile is expected to succeed in both arms and
the informative outcome is the diagnostic text, not the status.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No translation unit was
compiled, no kernel was built, no die was contacted, and no output was compared. The header contents
quoted in SOURCE are file reads performed under the phase-1 sanctioned read-only exception on the
installed CANN 9.0.0-beta.2 tree; they establish what the headers say and nothing about what a
compiler does with them.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled. The entry does not establish that either name resolves in a real build, that
the two produce the same instructions, or that the shared `DataCopyImpl` body means the compiler
selects the same overload — template default arguments differ between the two families and overload
resolution is not a text comparison. It does not establish anything about **other toolkit pins**:
one pin was read, and the deprecation reading ("internal, maybe removed") is the header's own text
about itself, not an observed removal. Arm D is what would give that claim any temporal scope.

The **placeholder reading** of `regbase_kernel_dataflow_patterns.md:43` is not excluded: "VF-safe
loads such as `DataCopy<..., LoadDist::...>`" could be shorthand for the family rather than a literal
name, in which case the file is not using a second spelling at all and this entry's §2 loses its
first branch. The concrete code block at `:102`/`:106` is why the literal reading was preferred; a
compile of that block is what would settle it, and it has not happened.

It does not establish that `DataCopy` is *deprecated* in any formal sense — the internal-header
message is a statement about a file, and every symbol defined in that file carries it equally,
including `LoadAlign`. What distinguishes the two is that `LoadAlign` is **also** declared in a
public interface header and `DataCopy` is not; that asymmetry is the finding, and "internal" is the
header's word for the file, not the vendor's word for the API.

It says nothing about the kernel-side `DataCopy` / `DataCopyPad` family that the whitelist's row
actually governs, nor about `Copy`, `DataCopyGather`, or the `DataCopyUnAlign*` kernel-side trio,
none of which were read. It says nothing about whether `Reg::DataCopy` appears in the vendor's
published documentation, which was not consulted and is not on this machine.

BOARD is `family-claimed(unverified)`: the implementation tree is `dav_c310` and the toolkit ships
950 inis, but a header is not a board and no board was contacted.
