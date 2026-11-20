```
ID:        0375-the-simt-accessors-are-declared-in-a-header-that-neither-guide-names
LABEL:     trap
LEVEL:     L8 (toolchain & build)
STRATUM:   corroborated — two independent origins: upstream's SIMT programming guide, which names two
           include paths, and the INSTALLED CANN 9.0.0-beta.2 headers on this machine, in which neither
           named header declares the symbols attributed to it. Nothing was compiled.
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-simt-programming-best-practices/references/index-calculation.md:34-38 — "## 头文件
           / ```cpp / #include \"simt_api/common_functions.h\" / ```" — given as the header for
           `GetThreadIdx` / `GetThreadNum` / `GetBlockIdx` / `GetBlockNum`.
SOURCE:    ops/ascendc-simt-programming-best-practices/references/multi-core-sync.md:35-39 — "## 头文件
           / ```cpp / #include \"simt_api/device_sync_functions.h\" / ```" — given as the header for
           `AscendC::SyncAll()`.
SOURCE:    INSTALLED TOOLKIT, independent origin — CANN `Version=9.0.0-beta.2`,
           `innerversion=V100R001C10SPC001B214`, `timestamp=20260328_213255003`, aarch64 —
           `asc/include/simt_api/common_functions.h` declares `asc_vf_call` and `using dim3 =
           cce::dim3` and **no** `GetThreadIdx` / `GetThreadNum` / `GetBlockIdx` / `GetBlockNum`;
           `asc/include/simt_api/device_sync_functions.h:20-24` declares `asc_syncthreads()`,
           `asc_threadfence()`, `asc_threadfence_block()` and **no** `SyncAll`.
SOURCE:    same toolkit — the four accessors are declared in
           `asc/include/interface/simt_api/cpp/kernel_simt_common_intf.h:28-38`, and `SyncAll()` in
           `include/ascendc/basic_api/interface/kernel_operator_block_sync_intf.h:76-84` — two headers
           neither upstream file names.
INDEX:     none — nothing measured; see SOURCE. Re-derivable by file read on this machine:
           grep -rn "GetThreadIdx\|SyncAll" $ASCEND_HOME_PATH/asc/include/simt_api/ | head
           grep -rln "inline int32_t GetThreadIdx\|inline void SyncAll" $ASCEND_HOME_PATH/asc/include/ $ASCEND_HOME_PATH/include/ascendc/
OVERTURN:  a toolkit pin in which `simt_api/common_functions.h` declares the four accessors, or in which
           `simt_api/device_sync_functions.h` declares `SyncAll` — the mismatch would then be version
           skew rather than a documentation error. Equally: a transitive include chain from either named
           header that reaches the real declarations, which would make the documented includes
           sufficient in practice even though they are wrong in attribution.
```

# 0375 · The SIMT accessors are declared in a header that neither guide names

## 1 · Claim
Upstream asserts that `AscendC::Simt::GetThreadIdx`, `GetThreadNum`, `GetBlockIdx` and `GetBlockNum`
require `#include "simt_api/common_functions.h"`. Upstream asserts, in a sibling file, that
`AscendC::SyncAll()` requires `#include "simt_api/device_sync_functions.h"`. Not established here:
nothing was compiled.

Read in the installed CANN 9.0.0-beta.2 headers, an independent origin, by file read:
`simt_api/common_functions.h` declares `asc_vf_call` and a `dim3` alias and declares none of the four
accessors. `simt_api/device_sync_functions.h` declares `asc_syncthreads`, `asc_threadfence` and
`asc_threadfence_block`, and declares no `SyncAll`. The four accessors are declared in
`interface/simt_api/cpp/kernel_simt_common_intf.h`; `SyncAll()` is declared in
`basic_api/interface/kernel_operator_block_sync_intf.h`. Neither of those two headers is named by either
upstream file.

The inference, stated separately: each of the two documented includes names a header that exists, is in
the right subtree, and carries a *sibling* API surface rather than the one attributed to it. Not
established here — no translation unit was compiled, and transitive inclusion could still make the
documented include sufficient.

## 2 · The wrong branch this removes
A wrong include path is normally the most benign kind of documentation error, because the compiler says
so. Two things make this one worse.

**The named headers are not wrong-looking.** They exist, they are in `simt_api/`, and their names describe
exactly the thing being looked for — "common functions" for common accessors, "device sync functions" for
a device-wide sync. An agent that hits `no member named 'GetThreadIdx' in namespace 'AscendC::Simt'` while
having included the header the guide names will not suspect the guide. It will suspect a typo, a
namespace, a toolkit pin, or the arch gate (0352, 0373) — four hypotheses, all plausible, all wrong. The
correct hypothesis is that the document attributes symbols to the wrong file, and nothing points there.

**The sibling surfaces are the trap's second half.** Both named headers carry a *different, plausible* API
for the same job:

- `common_functions.h` gives `asc_vf_call(dim3, args...)` where the guide wanted `Simt::VF_CALL(Dim3,
  args...)`. Same operation, lower-case spelling, namespace scope instead of `AscendC::Simt`.
- `device_sync_functions.h` gives `asc_syncthreads()` where the guide wanted `AscendC::SyncAll()`. **These
  are not the same operation.** `asc_syncthreads` is a CUDA-shaped intra-block barrier — it synchronises
  the threads of one block. `SyncAll()` is a block-level, all-core barrier
  (`kernel_operator_block_sync_intf.h`, alongside a `GlobalTensor`/`LocalTensor` workspace overload). An
  agent that includes the documented header, finds `asc_syncthreads` in it, and uses it because it is
  there has replaced a cross-core barrier with an intra-core one.

That substitution is the sharpest consequence in this entry. `multi-core-sync.md`'s whole subject is
exchanging data *between cores* through workspace; the guarantee it asks for is that every core has
finished writing before any core reads. `asc_syncthreads` does not provide it. The kernel compiles, runs,
and is correct whenever the timing happens to work — which is most of the time, at small core counts, on
an idle machine. It fails intermittently at scale, and the failure presents as data corruption in
workspace, which is the shape `common_traps.md:145-159` records as masquerading as precision drift.

**A third branch, for the `SyncAll` half.** `SyncAll()` is not in `simt_api/` at all — it is in
`basic_api/interface/`, the ordinary kernel-side surface. So the correct usage crosses from the SIMT
headers into the general AscendC headers, and the guide's include list does not say so. An agent building
a SIMT kernel from the SIMT guide alone has no reason to include a `basic_api` header, and
`kernel_simt_intf.h` (the SIMT aggregate) includes `kernel_operator_data_copy_intf.h`,
`kernel_operator_vec_binary_scalar_intf.h`, `kernel_tensor.h`, `kernel_tpipe.h`, `kernel_utils.h` and
`kernel_common.h` — but not the block-sync header. Whether `SyncAll` is reachable at all from a
SIMT-only include set is an open question and is Arm B.

## 3 · Ground / Source
Upstream's two include statements are quoted in SOURCE, each given under a `## 头文件` heading at the end
of its file, in the form a reader copies.

`simt_api/common_functions.h`, in the installed toolkit, with licence and guards elided (its complete
declarative content):

> ```cpp
> #include "simt_api/device_types.h"
> #include "utils/debug/asc_printf.h"
> #include "utils/debug/asc_assert.h"
> #include "utils/debug/asc_time.h"
> #ifndef SPLIT_CORE_VEC
> #if (defined(__DAV_VEC__) && (__NPU_ARCH__ == 2201 || __NPU_ARCH__ == 3510))
> #define SPLIT_CORE_VEC
> #endif
> #endif
> #if (__NPU_ARCH__ == 3510) || (__NPU_ARCH__ == 5102)
> #ifndef __NPU_COMPILER_INTERNAL_PURE_SIMT__
> using dim3 = cce::dim3;
> template <auto funcPtr, typename... Args>
> __aicore__ inline void asc_vf_call(dim3 threadNums, Args &&...args)
> { … }
> #endif
> #endif
> ```

One function, one type alias, three debug includes, one macro definition. No index accessor, and no
transitive include of `kernel_simt_common_intf.h`.

`simt_api/device_sync_functions.h:18-26`:

> ```cpp
> #include "simt_api/device_types.h"
>
> __SIMT_DEVICE_FUNCTIONS_DECL__ inline void asc_syncthreads();
>
> __SIMT_DEVICE_FUNCTIONS_DECL__ inline void asc_threadfence();
>
> __SIMT_DEVICE_FUNCTIONS_DECL__ inline void asc_threadfence_block();
>
> #include "impl/simt_api/device_sync_functions_impl.h"
> ```

Three primitives, all at namespace scope, none of them `SyncAll`. `__SIMT_DEVICE_FUNCTIONS_DECL__` expands
to `__simt_callee__` or `__aicore__` depending on `__NPU_COMPILER_INTERNAL_PURE_SIMT__`
(`device_types.h:24-27`).

Where the symbols actually are: `interface/simt_api/cpp/kernel_simt_common_intf.h:28-38` for the four
accessors (quoted at 0374 §3), and `basic_api/interface/kernel_operator_block_sync_intf.h:76-84` for
`SyncAll` — which declares both a workspace-taking overload
(`SyncAll(const GlobalTensor<int32_t>&, const LocalTensor<int32_t>&, ...)`) and a no-argument one, the
latter twice under different conditions.

**The naming pattern is worth stating, because it explains the error rather than merely recording it.**
The toolkit carries two parallel SIMT surfaces: a lower-case, CUDA-shaped one at namespace scope
(`asc_vf_call`, `asc_syncthreads`, `asc_threadfence`, `asc_atomic_add`, `threadIdx.x`) living under
`simt_api/`, and a CamelCase one inside `AscendC::Simt` (`VF_CALL`, `GetThreadIdx`, `AtomicAdd`,
`WarpShflSync`) living under `interface/simt_api/cpp/`. Upstream's guide documents the CamelCase surface
and cites the lower-case surface's headers. The vendor's own SIMT documentation uses the lower-case
surface: `debug-api.md:138` comments "// asc\_vf\_call调用时dim3参数：dim3(8, 2, 8)" and `:111,141-143`
use `__launch_bounds__` and `threadIdx.x/.y/.z`. So the two spellings are both real, both documented
somewhere, and mixed within one skill's reference files.

Two further symbols in the second surface that no upstream document in scope mentions, recorded because
they bear on the `asc_syncthreads` substitution: `asc_threadfence` and `asc_threadfence_block` are
*fences*, not barriers, and `kernel_simt_warp_level_intf.h:49,51` declares CamelCase `ThreadBarrier()`
and `ThreadFence()` alongside fourteen warp-level primitives (`WarpAllSync`, `WarpAnySync`,
`WarpBallotSync`, `WarpActiveMask`, `WarpShflSync`, `WarpShflUpSync`, `WarpShflDownSync`,
`WarpShflXorSync`, `WarpReduceAddSync`, `WarpReduceMaxSync`, `WarpReduceMinSync`, `Uni`, plus the two
above). None of the fourteen appears in any upstream file in this harvest's scope. That is a whole
cooperative-primitive family the SIMT guide does not know about, and it means an agent solving an
intra-block synchronisation problem from the guide alone has neither the right barrier nor the family it
belongs to.

## 4 · Procedure
Every arm is a compile; no device is needed.

Arm A — the documented includes, compiled. Two translation units: one including only
`simt_api/common_functions.h` and calling `AscendC::Simt::GetThreadIdx()`; one including only
`simt_api/device_sync_functions.h` and calling `AscendC::SyncAll()`. Record whether each resolves. If
either does, transitive inclusion rescues the documentation and the OVERTURN's second clause applies.

Arm B — reachability from the SIMT aggregate. A translation unit including `kernel_operator.h` and
`simt_api/cpp/kernel_simt_intf.h` — the realistic SIMT prologue — calling both `GetThreadIdx()` and
`SyncAll()`. Record which resolve. §2 predicts the accessors do and `SyncAll` may not; if `SyncAll` is
unreachable from a SIMT-only include set, `multi-core-sync.md`'s entire recipe is uncompilable as written
and that is a much stronger finding than a wrong path.

Arm C — the correct includes, established. Bisect the minimal include set for each symbol and record it.
This is the deliverable an agent needs, and it is what the delivered skill should carry in place of upstream's two
lines.

Arm D — the substitution hazard, which is the dangerous half. Build one multi-core workspace-exchange
kernel three ways: with `SyncAll()`, with `asc_syncthreads()`, and with no barrier. Run each 500 times at
two core counts against a host reference. §2 predicts `asc_syncthreads` is correct at low core counts and
fails intermittently at higher ones, i.e. that it sits between the other two rather than matching either.
The failure-rate table is the finding, because it is what makes "these are not the same operation"
actionable rather than a naming observation.

Arm E — the two surfaces, enumerated. List every symbol in `simt_api/*.h` (lower-case surface) and every
symbol in `interface/simt_api/cpp/*.h` (CamelCase surface) and produce the correspondence table: which
lower-case symbol pairs with which CamelCase one, and which have no partner. Upstream documents one
surface and cites the other's headers; the table is what would let a reader translate between them, and
no document in scope contains it.

Device selection, for Arm D only: the operator names the device index, the harness prints it back with
`compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared machine,
≤4 dies), and all three builds run on one named die in one session. A missing barrier can deadlock at the
workspace read; a watchdog timeout and die release are declared before the run.

## 5 · Checker — acceptance declared before the run
`documented_include_suffices` (Arm A) — two booleans, one per symbol group, never merged. Predicted
**false** for both. A true for either is the OVERTURN's second clause and would mean the documentation is
imprecise rather than wrong — a materially different verdict.

`syncall_reachable_from_simt_prologue` (Arm B) — true iff `SyncAll()` resolves from the realistic SIMT
include set. Reported, not gated: both answers matter and upstream states neither.

`minimal_include_set` (Arm C) — the bisected header list per symbol. Reported. This is the arm whose
output goes into the delivered skill verbatim.

`syncthreads_failure_rate` (Arm D) — failing runs out of 500, per barrier variant, per core count.
Reported as a table, never averaged across core counts: the entire prediction is that the rate *moves*
with core count, and a mean would erase it.

`surface_correspondence` (Arm E) — the two symbol lists and the pairing, with unpaired symbols on each
side listed explicitly.

The positive fixture, declared before the run: Arm D's **no-barrier** build must fail at least once at the
higher core count. If it does not, the workload has no cross-core race in it, and both the `SyncAll` and
`asc_syncthreads` results are statements about the probe rather than about barriers — a synchronisation
experiment whose unsynchronised arm passes has measured nothing. And Arm A must include a control
translation unit including the *correct* header (`kernel_simt_common_intf.h`) that **must** resolve
`GetThreadIdx`; if it does not, the compile environment is wrong and every "does not resolve" result is an
artefact of a missing include path rather than of the documentation. Without both, the checker reads only
"symbols were missing and some runs passed", which is the known blind species.

Process exit codes are not the verdict: Arms A and B expect compile failures as the informative outcome,
and Arm D expects wrong values from processes that exit zero.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No translation unit was compiled,
no symbol resolved, no barrier exercised, no die contacted. The header contents quoted in §3 are file
reads over the installed CANN 9.0.0-beta.2 tree performed under the phase-1 sanctioned read-only
exception; they establish what the headers declare and nothing about what an include chain delivers.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled. The entry does not establish that the documented includes fail — transitive
inclusion is a live possibility and is Arm A's whole point — nor that `SyncAll` is unreachable from a SIMT
include set, nor that substituting `asc_syncthreads` produces wrong results. Arms A through E are all
open.

It does not establish that the mismatch is a documentation error rather than version skew. One toolkit pin
was read; a pin in which `common_functions.h` declares the accessors would reframe it, and that check was
not performed against the other installed trees.

**It does not establish that `asc_syncthreads` and `SyncAll` differ in effect.** §2 argues they must, from
the CUDA-shaped naming and from `SyncAll` living in the block-sync header with a cross-core workspace
overload. That is reasoning from names and neighbours, not from semantics: neither function's
implementation was read, and no source in scope documents `asc_syncthreads` at all. Arm D is what would
establish it, and until then the substitution hazard is a predicted hazard.

It does not establish the correspondence between the two surfaces. The lower-case and CamelCase families
were observed to coexist and partially overlap; which pairs are equivalent, which are merely similar, and
which exist on one side only is Arm E and is unrun. `VF_CALL`/`asc_vf_call` is the one pair whose bodies
were compared (0373 §3) and even there the two differ in whether they define `SPLIT_CORE_VEC` themselves.

It says nothing about the fourteen warp-level primitives beyond recording that they exist and that no
upstream document in scope mentions them. Their semantics, their availability, and whether they are usable
from a `__simt_vf__` body are entirely unestablished.

BOARD is `family-claimed(unverified)`: an include path is not board-dependent, upstream's files name no
board token this book recognises, and no board was contacted.
