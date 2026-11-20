```
ID:        0407-the-gather-cost-gate-the-analysis-shelf-points-at-is-a-host-header-of-five-constants-and-a-two-regime-traffic-model
LABEL:     knowledge
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/gather/templates/
           gather_elements_v2_route.template:48-51 — "constexpr uint64_t kPostDimLimit = 32;
           / constexpr uint64_t kTransposeLen = 16; / constexpr uint64_t kInternalUbLimitBytes = 120000;
           / constexpr uint64_t kCachelineElementsBytes = 512;" ; :84-91 — the eleven disqualifying
           conditions of `CanUseInternalTranspose` ; :66-77 — the two-regime profitability model
SOURCE:    same file :2-7 — "GatherElementsV2 upstream route gate. / This host-only helper separates
           physical Transpose from the one-kernel / internal Transpose template. The cost gate follows
           the structure of / ops-nn aclnn_gather.cpp::IfUseGatherElementsV2/MemCheck; platform
           capability / is supplied by the caller instead of being hard-coded to one SoC."
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a `PER_ELEMENT` non-last-axis gather on a named 950 board that passes all eleven capability
           conditions and both profitability regimes, built both as the in-kernel transpose and as the
           SIMT fallback, in which the SIMT fallback is faster by more than the variance floor. The
           gate would then admit a case it should reject, and its `direct > inside` predicate would be
           the wrong direction for that regime.
```

# 0407 · The gather cost gate the analysis shelf points at is a host header of five constants and a two-regime traffic model

## 1 · Claim
Upstream asserts, in the analysis shelf, that the gather family's UB feasibility test decides only
whether a UB tiling can be generated, that a capability gate and a workspace cost gate must both pass
before the call, and that the complete gate set lives in a named file in the implementation shelf —
`reference/gather/templates/gather_elements_v2_route.template`. That file exists. Upstream asserts in
it a host-only routing helper returning one of four routes (`LAST_DIM`, `INTERNAL_TRANSPOSE`,
`PHYSICAL_TRANSPOSE`, `SCALAR_SIMT`), reached through eleven disqualifying conditions and, if all
eleven pass, a two-regime profitability model: when the index's non-gather work is smaller than the
core count the test is an element-count inequality, and otherwise it is a byte-traffic comparison
between a direct random read and the workspace round trip, admitting the in-kernel transpose only when
`direct > inside`. Upstream asserts its provenance — the structure of `ops-nn`'s
`aclnn_gather.cpp::IfUseGatherElementsV2/MemCheck` — and asserts that platform capability is a caller
input rather than a hard-coded SoC. Not established here.

## 2 · The wrong branch this removes
`0148` records that this family's routing is documented but not complete: the analysis shelf computes
`needTrans`, says plainly that `needTrans = true` does not mean the internal transpose is globally
optimal, and points at a file in another skill. An agent that stops where the analysis shelf stops has
a plan satisfying the only test it can see and failing two it cannot. This entry is that pointer
followed, and what it finds changes the shape of the gap: the missing gate is not a refinement of
`needTrans` at all. `needTrans` asks *can UB hold the transpose buffers*; the route gate asks *is the
workspace round trip cheaper than reading randomly*, and those two questions have different inputs,
different units, and no term in common. An agent that treats the out-of-skill gate as "the same test
with more terms" will merge them and get a predicate that is neither.

Four of the symbols `0148` and `0149` record as undefined are defined here, and their absence was the
reason those entries could not state the routing:

| symbol, as recorded undefined | value here | file:line |
|---|---|---|
| `postDim > 32` (0149 §7) | `kPostDimLimit = 32`, and the sense is `xPostDim <= 32` **disqualifies** | `:48`, `:87` |
| `gatherDim ≥ 16` (0149 §7) | `kTransposeLen = 16`, applied to **both** `xGatherDim` and `idxGatherDim` | `:49`, `:87` |
| `120000` (0149 §7) | `kInternalUbLimitBytes`, tested as `xGatherDim * xDtypeSize >= 120000` disqualifies | `:50`, `:88` |
| `INT32_MAX` behaviour (0147 §7) | `xElementCount >= std::numeric_limits<int32_t>::max()` disqualifies | `:86` |

A fifth, `kCachelineElementsBytes = 512`, is new — it caps the per-core workspace row count at
`512 / xDtypeSize` rows, which for FP32 is 128. That is the same 512 the analysis shelf calls
`CACHELINE` in its own `needTrans` block (`tiling-flow.md:105`, carried at `0148`), used here for a
different purpose in a different formula. One number, two roles, no cross-reference. Registered as
`C-950td-010`.

The second wrong branch this removes is trusting the gate to be complete now that it is found. It is
not. `physicalTransposeProfitable` is a **caller-supplied boolean** with the comment
`profiling/model gate; availability alone is insufficient` (`:44`), and the file computes nothing for
it. So the helper closes the internal-transpose gate and delegates the physical-transpose gate to
whoever calls it. The hole the analysis shelf pointed out of has one wall built and one still open, and
an agent that reads `SelectGatherElementsV2Route` as a complete router will hand it two `false`s it
never derived and receive `SCALAR_SIMT` — which, per `0408`, is the wrong answer on the family's own
headline case.

Third, the direction of the profitability test is worth stating explicitly because it is easy to
invert. `direct > inside` admits the transpose: the transpose is chosen when the **direct** path moves
more bytes. `direct` counts the whole of `x` (`xElementCount * xDtypeSize`), because a random
per-element read of a non-last axis touches every cache line of the source; `inside` counts only the
index-shaped output plus the workspace rounds. So the transpose wins when `x` is much larger than the
output, and loses when the output is comparable to `x` — which is exactly the case `0408` records
upstream measuring and rejecting.

## 3 · Ground / Source
The analysis shelf's pointer, `ops/ascendc-perf-optimize/references/tiling/gather/fallback/tiling-flow.md:142`
(quoted at `0148`, re-verified at drafting time):

```
> 以上只判断内部模板能否生成 UB tiling。调用前还必须通过 API 上游能力与 workspace 成本门控；`needTrans=true` 不表示内部 Transpose 全局最优。完整门控参考最佳实践库的 `reference/gather/templates/gather_elements_v2_route.template`。
```

The file it names, `ascendc-performance-best-practices/reference/gather/templates/gather_elements_v2_route.template`.
Its self-description and provenance, `:1-8`:

```cpp
/**
 * GatherElementsV2 upstream route gate.
 *
 * This host-only helper separates physical Transpose from the one-kernel
 * internal Transpose template. The cost gate follows the structure of
 * ops-nn aclnn_gather.cpp::IfUseGatherElementsV2/MemCheck; platform capability
 * is supplied by the caller instead of being hard-coded to one SoC.
 */
```

Two things in that header are worth more than they look. `platform capability is supplied by the
caller instead of being hard-coded to one SoC` is upstream deliberately removing exactly the defect
this project's contract names F4 (hardcoded capacity constants) — the SoC-dependent facts became
`internalTransposeSocSupported` and `physicalTransposeAvailable`, inputs rather than literals. And
`follows the structure of ops-nn aclnn_gather.cpp` names a real upstream source file, which makes this
a transcription of shipped production routing rather than a document written for the skill.

The four routes and the parameter block, `:18-45`:

```cpp
enum class GatherElementsV2Route {
    LAST_DIM,
    INTERNAL_TRANSPOSE,
    PHYSICAL_TRANSPOSE,
    SCALAR_SIMT,
};

struct GatherElementsV2RouteParams {
    uint64_t xPreDim = 1;
    uint64_t xGatherDim = 1;
    uint64_t xPostDim = 1;
    uint64_t idxPreDim = 1;
    uint64_t idxGatherDim = 1;
    uint64_t idxPostDim = 1;
    uint64_t xElementCount = 1;
    uint64_t indexElementCount = 1;
    uint64_t coreNum = 1;
    uint32_t xDtypeSize = 0;
    uint32_t indexDtypeSize = 0;
    bool isLastDim = false;
    bool perElementSemantics = true;
    bool nonGatherShapesEqual = true;
    bool mergeAxesCompatible = true;
    bool internalTransposeDtypeSupported = false; // current kernel: fp16/bf16/fp32/int32
    bool internalTransposeSocSupported = false;
    bool physicalTransposeAvailable = false;
    bool physicalTransposeProfitable = false; // profiling/model gate; availability alone is insufficient
};
```

Note that `x` and `index` carry **separate** `PreDim`/`GatherDim`/`PostDim` triples and separate
element counts. That is not redundancy: `torch.gather` permits `index.shape[i] <= x.shape[i]` on every
non-gather axis, so the two shapes genuinely differ, and `0413` records what happens when a host
collapses them.

The eleven capability conditions, `:81-92`, in full:

```cpp
inline bool CanUseInternalTranspose(const GatherElementsV2RouteParams& p)
{
    using namespace gather_elements_v2_route_detail;
    if (!p.perElementSemantics || p.isLastDim || !p.internalTransposeSocSupported ||
        !p.internalTransposeDtypeSupported || !p.nonGatherShapesEqual || !p.mergeAxesCompatible ||
        p.xDtypeSize == 0 || p.indexDtypeSize == 0 || p.xElementCount >= std::numeric_limits<int32_t>::max() ||
        p.xPostDim <= kPostDimLimit || p.xGatherDim < kTransposeLen || p.idxGatherDim < kTransposeLen ||
        p.xGatherDim * uint64_t(p.xDtypeSize) >= kInternalUbLimitBytes) {
        return false;
    }
    return InternalTransposeProfitable(p);
}
```

(Thirteen clauses by count; eleven are capability tests and two — `xDtypeSize == 0`,
`indexDtypeSize == 0` — are input-validity guards.)

The constants, `:47-51`:

```cpp
namespace gather_elements_v2_route_detail {
constexpr uint64_t kPostDimLimit = 32;
constexpr uint64_t kTransposeLen = 16;
constexpr uint64_t kInternalUbLimitBytes = 120000;
constexpr uint64_t kCachelineElementsBytes = 512;
```

None carries a derivation. `120000` is conspicuously not a power of two and not a round UB fraction —
against a 248 KB UB (`0209`) it is 47 %, against 192 KB it is 61 %, and neither is a recognisable
budget — so it reads as calibration rather than capacity. Under `0104` all four are software literals a
search may cross, and that disposition is worth stating because the accompanying prose forbids
crossing them (`0412`).

The profitability model, `:58-78`:

```cpp
inline bool InternalTransposeProfitable(const GatherElementsV2RouteParams& p)
{
    const uint64_t coreNum = std::max<uint64_t>(1, p.coreNum);
    const uint64_t coresPerGroup = std::max<uint64_t>(1, coreNum / std::max<uint64_t>(1, p.idxPreDim));
    const uint64_t workspaceLen = std::min<uint64_t>(
        kCachelineElementsBytes / p.xDtypeSize, CeilDiv(p.idxPostDim, coresPerGroup));

    using Wide = unsigned __int128;
    if (Wide(p.idxPreDim) * p.idxPostDim <= coreNum) {
        return Wide(p.xElementCount) >
               Wide(p.idxPreDim) * p.idxPostDim * (p.idxGatherDim + p.xGatherDim);
    }

    const Wide directTraffic = Wide(p.xElementCount) * p.xDtypeSize +
                               Wide(p.indexElementCount) * p.indexDtypeSize;
    const Wide internalTraffic = Wide(p.indexElementCount) * p.xDtypeSize +
                                 Wide(coreNum) * workspaceLen *
                                     (Wide(p.idxGatherDim) * p.indexDtypeSize +
                                      Wide(p.xGatherDim) * p.xDtypeSize);
    return directTraffic > internalTraffic;
}
```

The two regimes are not two approximations of one thing. The first branch fires when
`idxPreDim × idxPostDim <= coreNum` — the parallelism-starved case, where the workspace round trip's
cost is dominated by how few cores can be fed — and it compares **element counts** with no dtype size
anywhere. The second compares **bytes**. So the predicate changes units at the branch, and a case
sitting near `idxPreDim × idxPostDim == coreNum` can flip sense for reasons that have nothing to do
with its data volume. Registered as `C-950td-011`; the same-file prose restates both regimes at
`gather_elements_v2_transpose.md:46-60`, which is where the worked numbers live (`0408`).

`unsigned __int128` throughout the second regime is a deliberate overflow guard, and it is the right
one: `xElementCount * xDtypeSize` for the family's own case4 is 268 MB, and the `coreNum * workspaceLen
* (…)` term multiplies four quantities. A 64-bit intermediate would survive these cases and not obviously
larger ones.

The delegated hole, `:94-106`:

```cpp
inline GatherElementsV2Route SelectGatherElementsV2Route(const GatherElementsV2RouteParams& p)
{
    if (p.isLastDim) {
        return GatherElementsV2Route::LAST_DIM;
    }
    if (CanUseInternalTranspose(p)) {
        return GatherElementsV2Route::INTERNAL_TRANSPOSE;
    }
    if (p.physicalTransposeAvailable && p.physicalTransposeProfitable) {
        return GatherElementsV2Route::PHYSICAL_TRANSPOSE;
    }
    return GatherElementsV2Route::SCALAR_SIMT;
}
```

`isLastDim` short-circuits before any cost test at all — which the family's own LastDim document then
contradicts, instructing that resident cost be compared against direct random cost before choosing
LastDim and that `不能只判断 dim==last` (`gather_elements_v2_last_dim.md:57-65`,
`guide.md:235`). The router's first line does exactly what the template's document forbids.
Registered as `C-950td-012` and carried at `0411`.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase. The gate is
host-side C++, so its *behaviour* is testable with no device at all; only the question of whether its
verdict is right needs one.

**Arm 1 — device-free. The gate's own truth table.** Compile the header and drive
`SelectGatherElementsV2Route` over a parameter sweep covering, for each of the four routes, at least
one case reaching it and one case just missing it: `xPostDim ∈ {31, 32, 33}` around `kPostDimLimit`;
`xGatherDim`, `idxGatherDim ∈ {15, 16, 17}` around `kTransposeLen`; `xGatherDim * xDtypeSize` at
`119996`, `120000`, `120004`; `xElementCount` at `INT32_MAX − 1`, `INT32_MAX`; and both sides of
`idxPreDim × idxPostDim == coreNum`. Record the returned route and which clause fired (by bisecting
the parameter). This establishes what the gate *does*, which is a prerequisite for asking whether what
it does is right — and it is the arm that would expose an inverted comparison or an off-by-one at a
boundary.

**Arm 2 — device-free. Re-derive upstream's worked rejection.** Instantiate the parameters of
upstream's case4 (`gather_elements_v2_transpose.md:79`: `x = [8192, 8192]` int32,
`index = output = [4096, 8192]`, `dim = 0`, `coreNum = 48`) and confirm the helper returns
**not** `INTERNAL_TRANSPOSE`. Upstream states the arithmetic (`:88-89`); recomputing it from the code
rather than pasting it is the check that the document and the header agree. This is the arm upstream's
own verification list demands (`:115`: `case4 必须命中 PHYSICAL_TRANSPOSE，不能命中 INTERNAL_TRANSPOSE`).

**Arm 3 — on-card. Is the admitted region actually the fast region?** Construct four `PER_ELEMENT`
non-last-axis gathers: two the gate admits (one in each profitability regime) and two it rejects (one
just past `direct > inside`, one just under `kPostDimLimit`). At each, build the in-kernel transpose
template and the SIMT template from the implementation shelf's two `.template` files, one compiler
pin, distinct md5s, host echo of the chosen route and every parameter the gate read. Elementwise
comparison against a CPU reference on both. Record `aiv_time` under
`msprof --aic-metrics=PipeUtilization`, ≥10 iterations, first 5 dropped. Variance floor first: 30
in-process runs, 5 fresh-process runs.

**Arm 4 — the delegated hole.** For the same four cases, also build the physical
transpose ×3 + last-axis gather sequence and time it, so `physicalTransposeProfitable` — the boolean
the helper does not compute — has a measured value on at least four points. Upstream's case4 says this
arm wins where both others lose, so it is not optional.

Device selection for arms 3–4: `npu-smi info -l`;
`npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing; bind only on three idle samples;
`ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and discard the case if the die moved.

Refuses to assume: that a free die stays free; that a die may be substituted; that `coreNum` is 48 (it
is a *parameter* of this helper, and `0217` records installed 950 SKUs spanning a wide range — the run
queries it and echoes it); that a route returned is a route taken (the kernel echoes which template it
is); that the gate's constants are hardware-derived (they are literals, per `0104`); that
`physicalTransposeProfitable` can be left `false` (arm 4 supplies it, and leaving it false silently
routes everything to `SCALAR_SIMT`).

## 5 · Checker — acceptance declared before the run
Verdict `route(case)` from arms 1–2: the enum value returned, plus the clause that decided it.
Declared before the run: the gate is **transcribed correctly** iff every boundary in arm 1 flips the
route at exactly the constant's value (`xPostDim = 32` rejects, `33` admits; `xGatherDim = 15` rejects,
`16` admits; `xGatherDim*xDtypeSize = 120000` rejects, `119996` admits) **and** arm 2 returns a
non-`INTERNAL_TRANSPOSE` route for case4.

Verdict `gate_correct(case)` from arms 3–4: true iff, for every case, the route the gate returns has
the lowest median `aiv_time` of the three built alternatives, outside the variance floor. Declared
before the run: this entry is **supported** iff `gate_correct` holds on all four cases. The OVERTURN
fires iff `gate_correct` is false on an **admitted** case — the gate would then admit a case it should
reject. A `gate_correct` failure on a *rejected* case is a different and weaker finding (the gate is
conservative), recorded as such and not as an overturn.

The exit code is not the verdict. Arm 1's whole purpose is to make the helper return values, so
"it compiled and ran" says nothing. Three guards. First, **the input that makes this checker go red**:
arm 1 includes a parameter set with `perElementSemantics = false`, which **must** return
`SCALAR_SIMT` (or `LAST_DIM` if `isLastDim`), never `INTERNAL_TRANSPOSE`. If a `PER_SLICE` case is
ever admitted to the internal transpose, the harness is not calling the real predicate and every route
in the sweep is void — the sweep would otherwise be able to "confirm" any constant, because a
degenerate always-false or always-true implementation reproduces boundary flips by accident only if
someone checks a case that must go the other way. Second, every arm-3/4 timing is accompanied by an
elementwise correctness result; a gather with wrong indices exits 0 and is fast. Third, no case is
reported without the full parameter block the gate read, echoed from the run — the gate has eighteen
inputs and a study that does not record all of them cannot attribute a route to a clause.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The constants, the eleven
conditions and the two-regime model are file reads of upstream's own header performed at drafting
time. The observation that `120000` is 47 % of 248 KB and 61 % of 192 KB is arithmetic done here on
paper against capacities this book records as themselves unmeasured (`0209`) and disputed (`0131`); it
is offered as a reason the number reads as calibration, not as evidence about any board.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The entry does not establish that the gate is correct, that any of
its five constants is right, or that `direct > inside` is the right direction — §4 is what asks, and §5
declares what would show it wrong. It does not close the family's routing: `physicalTransposeProfitable`
is a caller input the file does not compute, so the physical-transpose arm's cost gate remains outside
this domain, and this entry records that as a delegated hole rather than filling it. It does not
supply the SIMD threshold table (218/360/620/2048) whose derivation `0148` records as missing — this
header does not contain it, and the two gates answer different questions, so `0148`'s primary hole is
narrowed, not closed. It does not establish `coreNum = 48`, `kCachelineElementsBytes = 512` as a real
cache line (`0148` records the analysis shelf using 512 as `CACHELINE` in a different formula, and
`C-950td-010` records the collision), or `120000` as a UB fraction. It does not establish that the
`ops-nn` provenance is accurate — `aclnn_gather.cpp` is not in this tree and was not read. It does not
resolve `isLastDim` short-circuiting before the cost test (`C-950td-012`, carried at `0411`). No board
token appears anywhere in the gather family on either shelf, so BOARD is `family-claimed(unverified)`;
§4 names 950PR/950DT only as where arms 3–4 would run. Nothing here is established for any 910-family
board.
