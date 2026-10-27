---
applies_to: soc=all
reason: MC² (compute-communication fusion) HCCL window-RDMA communication tooling. HcclResource abstracts the chip-dependent HCCL context layout, so the helpers apply across 910B/910C/950PR(A5). The comm half is GM-based soft sync + window RDMA — architecture-independent in principle; this KB and the reference implementation are verified on the separated-core family only (arch ≥ 220 / V220 upward — 910B/910C/950PR), unified-core architectures not covered yet.
---

# Domain: MC² Communication (compute-communication fusion)
> Reference examples for MC² multi-rank kernel communication: HCCL context lifecycle, cross-rank soft barrier, window RDMA, GM-aligned scalar I/O.
> **Communication paths** — MC² has three paths, one section each below:
> 1. HCCL comm domain + HCCL high-level APIs;
> 2. HCCL comm domain + reuse of its internal cross-card shared-memory resources (**this document's focus**; the scaffold emits it unconditionally);
> 3. shmem comm domain + shmem-allocated shared-memory communication (reserved).
>
> chip_scope: **all**.

---

## Scope — cross-rank sync & data exchange

THIS document covers Path 2: the HCCL resource base (P-P110), the cross-rank
soft barrier (P-P111), and window-RDMA data exchange (P-P112) — all cross-rank
work runs on AIV (kernel form & core routing: next section). Intra-core (pipe) and inter-core (AIC↔AIV) sync both live in
[`sync_fundamentals.md`](sync_fundamentals.md) — **MANDATORY prerequisite
reading** (every MC² kernel compiles with `--cce-auto-sync=off`).

## Kernel Form & Compute Routing

> **Compute-fusion inheritance** — MC² = a single kernel fusing a **compute**
> half with a **communication** half, where communication is realized via
> **memory semantics**: window RDMA turns the collective into `DataCopy`
> (one-sided put/get into the peer's shared GM + CrossRankSync soft barrier
> for visibility), NOT an HCCL collective API. That memory-semantic DataCopy
> IS the MC² core — covered by P-P110-112 in THIS domain. This document does
> NOT cover the compute half; it inherits the general compute-fusion KB — route
> the compute half yourself via `PATTERN_INDEX.md`.
>
> **Architecture independence** — the MC² comm half is GM-based soft sync
> (CrossRankSync flag + one-sided window RDMA): what it needs is
> cross-card-addressable shared GM, NOT a specific core architecture — a
> unified-core chip can run the same scheme in principle. The AIC/AIV content
> in this domain (MIX handshake, comm routing below) reflects the
> separated-core family the reference implementation and this KB are verified
> on: arch 220 (V220) upward (910B/910C/950PR …).
>
> **Kernel form & comm routing** — `KERNEL_TYPE_MIX_AIC_1_2` is a launch
> core-ratio config (cube:vector kernel launch ratio on the fixed 1:2 C:V
> separated-core hardware); it is NOT an MC² requirement. What MC² constrains
> is the comm half's routing: on separated-core chips the cross-rank data
> movement runs on **AIV only**. It works through the **UB** (Unified
> Buffer): the atomicAdd flag-set is S+MTE3, the poll is S+MTE2, the
> window-RDMA `DataCopy` is UB↔GM — none of it uses V. The AIC is designed
> solely to accelerate matrix compute (cube/Mmad) and has **no UB**, so it
> cannot do any UB-mediated GM access. The compute half may span both cores:
> - **MIX**: compute spans AIC (cube) + AIV (vec epilogue); AIV additionally
>   does the cross-rank DataCopy. AIC implies AIV (AIV is mandatory for the
>   comm half) — **no AIC-only MC² exists**.
> - **AIV-only**: compute is pure vec on AIV; AIV does both compute and
>   cross-rank DataCopy; the `if ASCEND_IS_AIC { }` branch is left EMPTY.
>
> N-rank topology (ring/tree/recursive-halving beyond pairwise 2-rank) is a
> tracked gap — not yet in KB.

## Path 1 — HCCL comm domain + HCCL high-level APIs

Not covered by this KB yet (no scaffold/KB wiring). Where to find the API
reference:

- `HcclAllReduce` / `HcclBroadcast` / `HcclSend` / `HcclRecv` — high-level
  collective APIs (HCCL server on AICPU).
- `Hccl::InitV2` — high-level context init: `atlasascendc_api_07_0867.md`.

⚠ Conflicts with Path 2's MTE setting — the two are mutually exclusive (see
the Path 2 precondition).

## Path 2 — HCCL comm domain + reuse of its internal cross-card shared-memory resources

**Precondition**: before the aclnn call, the host MUST disable AI CPU dispatch
and set MTE mode — `NnopbaseSetHcclServerType(executor, NNOPBASE_HCCL_SERVER_TYPE_MTE)` —
otherwise the windows are occupied by AICPU and kernel reads/writes misbehave.
Path-1 high-level APIs CONFLICT with this MTE setting (mutually exclusive).

> **Provenance & where the code lives**: the CrossRankSync primitives and the HcclResource helper (P-P110) are owner-authorized reference implementations (design §3.1). **The code lives in `multirank/templates/`** (shipped as `.h.txt` reference assets; copy into the op project under the `.h` name below); this document is the interface **usage guide** (procedure + semantics + constraints). Two assets, both for Path 2:
> - `hccl_res_helper.h.txt` (HcclResource) — copy into the op project as `op_host/hccl_res_helper.h`, then `#include` verbatim into its **own** header; kernel calls the interface only, never touches `hcclContext_` or the layout structs.
> - `cross_rank_sync_example.h.txt` (CrossRankSync*) — **COPY-PASTE SOURCE, not `#include`d**; procedure: P-P111 below.
>
> Author your own fusion logic around them; never rename or rewrite the sync functions (see P-P111 for what is load-bearing).

### P-P110: MC² HcclResource — HCCL context lifecycle + rank/window topology

**Severity**: High | **Source**: reference op HCCL-resource util header (HcclResource, owner-authorized, design §3.1).

**Three HCCL window resources** (allocated by the framework at init; the op only reads/writes them, never allocates/frees):

| Resource | Default size | Purpose |
|---|---|---|
| `windowsIn` | 200 MB (controlled by `HCCL_BUFFSIZE`; default if unset) | symmetric memory slab 1 |
| `windowsOut` | 200 MB (controlled by `HCCL_BUFFSIZE`; default if unset) | symmetric memory slab 2 (In/Out naming carries no direction, see P-P112) |
| `windowsExp` | 1 MB | sync flag region — **A2 single-node & A3 only** (no zeroing guarantee; see the flag-memory rule in P-P111) |

**No-exp layouts — A5 and A2 multi-node**: there is **no `windowsExp` region** (`GetWindowsExpSize()` returns 0, `GetWindowsExp()` traps). On A2 multi-node, `IsA2MultiNode()` returns true — the topology is 2× 910B chassis interconnected via a switch (dual-node 16-card). For cross-rank flag sync you must **carve your own status region out of a window slab** (`windowsIn` / `windowsOut`, e.g. reserve the first 1 MB as the per-card flag area) and plan it explicitly:

- **Disjoint from data**: the carved flag region and the RDMA data traffic sharing that slab MUST NOT overlap — size both and offset the data `DataCopy`s past the reserved segment.
- **Treat the flag region as random values** (never rely on external zeroing) — the per-variant consequences and the full dirty-flag rule live in P-P111.

The single entry point for MC² rank-private state. `AscendC::GetHcclContext<HCCL_GROUP_ID_0>()` returns a `__gm__` pointer whose layout depends on chip — `HcclResource::Init` binds it and abstracts the differences, exposing rank id / size / workspace / per-peer window addresses through the interface below. All other MC² helpers depend on it.

**Code**: `src/scripts/orchestrator/plugins/multirank/op_template_gen/multirank_assets/templates/hccl_res_helper.h.txt` (copy as `op_host/hccl_res_helper.h`) — hardened with `ascendc_assert` rankId/addr guards. Kernel code calls the **interface only**:

| Interface method | Returns |
|---|---|
| `Init(mc2InitTiling, mc2Context = AscendC::GetHcclContext<HCCL_GROUP_ID_0>())` | parses `devType` from the MC² init tiling (`mc2InitTiling` MUST be non-null); binds the HCCL context (`mc2Context` — when to pass it explicitly, see below) |
| `GetRankId()` / `GetRankSize()` | this rank's id / world size |
| `GetWindowsInAddr(rankId)` / `GetWindowsOutAddr(rankId)` | symmetric window-slab addr for rankId (direction-agnostic, see P-P112) |
| `GetWindowsSize()` | per-slab size of the symmetric window memory (uniform meaning across chips) |
| `GetWindowsExp(rankId)` / `GetWindowsExpSize()` | sync-flag region addr / size — **A2 single-node & A3 only**; on A5 and A2 multi-node the size is 0 and the addr getter traps (see no-exp layouts above) |
| `GetWorkspaceAddr()` / `GetWorkspaceSize()` | workspace GM addr / size |
| `IsA2MultiNode()` | A2 multi-node flag (always false on A5) |

**`mc2Context` — when you must pass it explicitly**: the default second argument (`AscendC::GetHcclContext<HCCL_GROUP_ID_0>()`) is valid only when the context has already been wired into the kernel for you. Two invocation modes:

- **Registry invoke (engineered-op framework)**: the op is registered with compute-communication fusion capability (`this->MC2().HcclGroup("group");` in the host-side registration) — the framework implicitly inserts the `SetHcclContext` call at compile time, so `GetHcclContext` returns the group's context and the default argument works as-is.
- **Direct invoke**: the kernel is launched directly (no framework registration) and the MC² tiling structure is created via `HcclAllocComResourceByTiling` — the host obtains the `mc2Context` pointer from that call and must pass it into the kernel explicitly as `Init`'s second argument (nothing sets the context on your behalf).

Do NOT read `hcclContext_` or the `hccl_res_detail::*` layout structs from kernel logic — the layout is chip-dependent and the class abstracts it.

---

### P-P111: MC² CrossRankSync — cross-rank soft barrier + GM-aligned scalar I/O

**Severity**: High | **Source**: owner-authorized reference implementation (design §3.1).

A software barrier for custom MC² topologies. Every participating rank `atomicAdd(1)` into a GM flag slot, then polls until the observed value advances by `rankSize`. `CrossRankSync*` are member functions that acquire the UB scratch + flag GM INSIDE the body, so only scalars are passed. The inter-core `SyncAll` handshake (AIC↔AIV in MIX_AIC_1_2) is summarized at the end of this entry; full rules: `sync_fundamentals.md` §10.

#### Copy & fill-in procedure

1. Do NOT `#include` this file — copy the `#define` block (incl.
   `GET_SYNC_GM_IN_RANK`) + the chosen `CrossRankSync*` function BYTE-FOR-WORD
   into the kernel class private section as a **member function** (the
   `/*SYNC_BUF_*/` placeholder leaves an incomplete statement that won't
   compile if `#include`d). Why member: under the kernel's **-O3 release
   build**, passing the LocalTensor at the call site faulted on A2/910B4,
   while the same `Get<T>()` called INSIDE a member function is correct. A
   renamed/rewritten "soft barrier" of your own is NOT equivalent — the
   participating-core / atomicAdd / poll / release ordering is load-bearing
   (the allreduce_swiglu ws=4 failure was a self-rolled barrier: it passed
   ws=1 — which skips the comm path — and faulted at ws≥2).
2. Replace the ONLY code placeholder `/*SYNC_BUF_*/` — an expression yielding
   the flag-scratch `AscendC::LocalTensor<uint32_t>` (e.g. a TBuf member's
   `syncBuf_.Get<uint32_t>()`; NOT TBuf-bound — any source works). If
   TBuf-backed, `InitBuffer` it to ≥ 32 B (the UB minimum allocation+access
   granularity; the scratch only ever holds ONE `uint32` flag — 512 B is
   wasteful cargo-cult).
3. Adjust the EXAMPLE body of `GET_SYNC_GM_IN_RANK(rankId)` to your planned
   flag region, keeping the signature (`rankId` in → that rank's sync-flag GM
   base out; exp / In / Out slab all valid — see the flag-region note below).
   An unadjusted EXAMPLE body (e.g. the exp lookup on a no-exp layout) or a
   bogus address makes every rank hit a bogus address and the barrier never
   fires.
4. Optionally adjust the `[ADJUSTABLE]` participating-core predicate — the
   defaults (`block-0/subblock-0` for RandomMem; `subAivId==0 && aicoreId<rankSize`
   write phase / `aicoreId==rankId` poll phase for Deterministic) are correct
   for the standard MC² layout; change ONLY the predicate. Most ops need no
   change.

Steps 2-4 are the ONLY fill-in points; do NOT rename / reflow / change the
algorithm (atomicAdd / DataCopyPad / poll / release ordering is load-bearing).

#### Choosing an entry point

| Function (member; scalar params) | When | GM initial value |
|---|---|---|
| `CrossRankSyncInRandomMemValue(rankSize, rankId, flagId)` | **default, balanced** — every rank keeps its OWN slot: arrive broadcasts atomicAdd to ALL ranks' slots, poll watches the own slot for a `rankSize` delta over its initial value — no shared hot slot; tolerates any initial value (reads its baseline first) | any value, no need to zero |
| `CrossRankSyncInDeterministicMemValue(rankSize, rankId, flagId, flagValue, expectedVal)` | perf tuning — each participating core writes (generally) the PEER ranks' slots (`GET_SYNC_GM_IN_RANK(aicoreId)`), owning rank polls its own slot (`GET_SYNC_GM_IN_RANK(rankId)`); can improve poll-bandwidth balance | must be deterministic (usually zeroed) |
| `CrossRankSyncInDeterministicMemValueWithClear(rankSize, rankId, flagId, flagValue)` | production + flag reuse (owning rank clears the flag after sync, slot reusable) | **must be 0** (auto-clears) |

The flag GM comes from the injected `GET_SYNC_GM_IN_RANK(rankId)` macro — `rankId` in → that rank's sync-flag region GM base out (the `#define` block ships an EXAMPLE body; adjusting it is procedure step 3); region placement: see the note below.

> **Flag-region planning (backs `GET_SYNC_GM_IN_RANK`)**: no interface hands you the flag memory — the macro's backing region is planned freely by the op: ANY shared slab works (`windowsExp`, `windowsIn`, or `windowsOut`, wherever fits the memory plan). On **A5 and A2 multi-node there is no `windowsExp`**: carve the region out of a window slab (e.g. the first 1 MB), keep it disjoint from the RDMA data traffic in that slab, and **never assume the flag memory is zeroed — treat it as random unless the host explicitly clears it before dispatch** (see the dirty-flag constraint below).

**Scalar params**:

| Param | Description |
|---|---|
| `rankSize` | number of participating ranks |
| `rankId` | current rank id (ALL variants: RandomMem reads baselines from / polls its own slot; Deterministic/WithClear also use it as the polling core id) |
| `flagId` | flag index; actual offset = flag base + `flagId * SOFT_SYNC_ALIGN_BYTE (512B)` |
| `flagValue` | value each participating core atomically adds (Deterministic/WithClear) |
| `expectedVal` | target total = `initial + rankSize * flagValue` (WithClear checks `flagValue * rankSize` internally, hence requires initial 0) |

> Why the 512B flag spacing and the atomicAdd-write + DataCopyPad-poll shape:
> the multi-core 512B-window serialization, the DCache-line (64B) overlap
> overwrite trap, and the MTE-first scalar-visibility rule are catalogued in
> `memory_constraints.md` — consult it before hand-rolling any scalar flag /
> GM publication outside this template.

**Call skeleton** — `SyncAll` MUST wrap the cross-rank soft sync in three steps (otherwise the rep core's sync state cannot spread to all cores on this card):

```cpp
AscendC::SyncAll<true>();                  // 1. all cores on this card finish current stage
CrossRankSyncInDeterministicMemValue(...); // 2. rep core does the cross-rank soft sync
AscendC::SyncAll<true>();                  // 3. spread sync state to all cores on this card
```

`SyncAll<true>` (AIV-only) or `SyncAll<false>` (AIC+AIV) depending on whether AIC participates in this sync.

**Why the wrap works (HBM visibility — do not second-guess it)**: `SyncAll` contains `PipeBarrier<PIPE_ALL>` (drains every pipe intra-core) and guarantees all data-moving cores on the card have written out; `CrossRankSync*` then notifies the other ranks. The `SyncAll → CrossRankSync* → SyncAll` chain DOES make prior data visible in HBM. When results are wrong, the first check is "did I copy these functions verbatim-as-members and call them in the 3-step skeleton?" — not an L2-cache theory.

**Deterministic semantics** (rankSize = N): phase 1 all-core `SyncAll`; phase 2 cores with `subAivId==0 && aicoreId<N` each atomically add `flagValue` to `syncAddr(k)` (rank k's sync address); phase 3 the core with `aicoreId==rankId` polls its own address until `expectedVal`; phase 4 all-core `SyncAll` spreads. Final `syncAddr(rankId) = initial + N * flagValue` (N ranks each write once), so **`expectedVal = initial + rankSize * flagValue`**.

**Key constraints** (violation = deadlock / data corruption):

- **flagId rotation — never reuse the same flag back-to-back (a MANDATORY kernel-development rule, NOT a host concern)**:
  - **"Back-to-back" defined precisely**: the host dispatches this device kernel **multiple times in a row with NO cross-rank sync inserted between launches** (no `dist.barrier()`, no HCCL collective, no inter-rank stream sync between consecutive kernel launches). This is the DEFAULT situation, not an edge case — verify runs N cases back-to-back under one HCCL context, training runs N steps, inference runs N batches. The kernel MUST NOT assume the host will insert a sync on its behalf; defending against back-to-back re-dispatch is the kernel's own responsibility.
  - **Even a single-sync, single-flag kernel is NOT exempt**: *"my kernel has only ONE `CrossRankSync` on ONE fixed flagId, so no two syncs are adjacent"* is **WRONG** — the adjacency is across launches, not within one: launch N's only sync and launch N+1's only sync form a back-to-back pair, and a single fixed flagId means they always land on the SAME GM slot (the flag memory is random at entry — see the dirty-flag rule below). With small per-launch data the kernel completes fast and is re-dispatched often, so this pair occurs readily — see the failure mode below for how it breaks the sync state machine.
  - **Failure mode (intermittent, nearly impossible to diagnose)**: cards run at different speeds and the fast/slow-card skew can be severe; a fast card finishes launch N's sync, re-enters launch N+1, and atomicAdds the flag again WHILE a slow card is still polling launch N. The slow card then reads a flag value polluted by launch N+1 → inconsistent cross-rank sync state → **intermittent, timing-sensitive deadlock** that rarely reproduces and is extremely hard to root-cause. (Mechanically: the GM flag mutation is not perceived by all ranks simultaneously, so reusing one flagId lets an early rank re-touch it while a late rank still polls stale state.)
  - **Rule — make every pair of temporally-adjacent cross-rank syncs use a DIFFERENT flag slot**: the goal is that no two consecutive syncs — including across the launch N → launch N+1 boundary — ever share a flag, so a fast card re-entering launch N+1 cannot disturb launch N's flag state machine.
  - **Clearing the flag is NOT a fix (do not conflate the two)**: `CrossRankSyncInRandomMemValue` never requires zeroing in the first place — its poll waits for an increment of `rankSize` from any initial value; `WithClear` only enables deterministic reuse of the SAME flagId WITHIN a kernel, and does nothing to stop a fast card re-touching that slot mid-poll of the previous launch. The deduction *"use WithClear so I can keep one fixed flagId across dispatches"* is **WRONG** — with one fixed flagId the back-to-back deadlock remains regardless of clearing.
  - **Two ways to achieve the rule (pick the simplest)**:
    1. **≥2 kernel-internal sync points with distinct static flagIds (SIMPLEST — no host change)**: even if the op logically needs only ONE cross-rank sync, insert a second redundant one (at the start or end of `Process()`) on a different `flagId`. Two flags alternating in a fixed order make every temporally-adjacent sync pair — including the launch N last-sync ↔ launch N+1 first-sync boundary — land on different slots. Preferred because it needs no host-side round tracking.
    2. **Rotate one sync's flagId by dispatch round**: `flagId = launchRound % flagNum` (`flagNum ≥ 2`); the kernel does not know its own dispatch index, so the host must pass `launchRound`. ⚠️ In an msopgen project template (the engineered-op workflow in the AscendC docs) the tiling struct is CACHED — `InferTiling` is NOT invoked on every dispatch — so `launchRound` cannot simply ride in a tiling field (it would go stale on cached dispatches). You must instead pass it as a dedicated kernel entry-point argument (a separate param, bypassing the tiling cache) and write it through the aclnn wrapper on every launch. This extra plumbing is exactly why scheme 1 (≥2 kernel-internal syncs) is preferred.
  - **Reviewer gate**: a kernel whose flag-based cross-rank soft barrier uses a FIXED `flagId` and that can be dispatched more than once (**ASSUME multi-dispatch unless provably single-shot**) is a **BLOCK** (intermittent-deadlock risk) — regardless of (a) how many times the barrier is called inside one `Process()`, and (b) whether the flag memory is HCCL `windowsExp`, a slab-carved region (A5 / A2 multi-node), or host-managed GM. The back-to-back rule applies to ANY flag-based cross-rank soft barrier, not only HCCL-context ones.
- **expectedVal maintenance**: Deterministic uses atomic-add to mutate the flag, so the caller must know the accumulated final value; the initial value is not trustworthy (treat it as random — no framework zeroing between rounds), so the op must establish and maintain the initial value itself. Two schemes: ① **even/odd round flip** of `flagValue` (e.g. 1 / -1), which needs an extra initial-0 GM slot recording the current round (per-rank per-core independent address to avoid contention); ② **clear scheme** — after round N completes, all ranks have left the critical section, so each rank clearing its own flag N has no write contention; use `WithClear` (provided the flagId-rotation rule above holds).
- **dirty flag memory — never assume zero**: treat the flag memory as RANDOM at kernel entry — do NOT rely on any external framework zeroing guarantee (in production, multiple dispatched ops may share this memory); only an explicit host-side clear before dispatch counts. `RandomMem` tolerates any initial value by design; `Deterministic` / `WithClear` need a known initial value — read it first or zero it in a setup phase; never derive `expectedVal` from an assumed-0 base.
- **symmetric invocation & cross-rank param consistency**: every rank must call the CrossRankSync* series at the SAME sync points, the SAME number of times — the barrier math assumes each rank contributes exactly ONE atomicAdd per sync: one rank skipping a call leaves the poll one delta short (timeout); an extra call lets a later poll pass early. `flagId` / `flagValue` / `expectedVal` / `rankSize` must also be identical on every rank, else poll semantics diverge.
- **timeout guard**: the poll MUST use `GetSystemCycle()` with a timeout (reference impl 30s @ 50MHz); on timeout printf diagnostics + `Trap()` — never let the core spin forever.
- **poll backoff (internal)**: the reference implementation already inserts a short delay between polls; do NOT strip it when editing the predicate. Tight polling would fire a GM read to the bus on every iteration; while the flag is not ready these reads are all invalid yet keep hogging the bus, starving other traffic in multi-card high-concurrency.
- **participating core count**: the write phase needs `rankSize` cores matching `subAivId==0 && aicoreId<rankSize`; under 1:2 sub-blocking only `subAivId==0` qualifies, so increase `blockDim` accordingly.
- **No `using namespace AscendC`** — explicit `AscendC::` qualification only.

**Common mistakes** (symptom → root constraint; full rules in Key constraints above):

| Symptom | Root constraint (see above) |
|---|---|
| data corruption / deadlock around the barrier | missing `SyncAll` — the 3-step wrap (call skeleton) |
| some ranks poll-timeout / deadlock | symmetric invocation & cross-rank param consistency |
| intermittent deadlock (fast/slow-card skew), nearly impossible to diagnose | flagId rotation — fixed flagId on a multi-dispatch op (clearing does NOT fix) |
| poll hangs forever / exits early | expectedVal maintenance |
| never reaches expectedVal | participating core count |
| multi-card high-concurrency perf collapse | poll backoff stripped from the reference impl |
| kernel reads/writes misbehave | Path 2 precondition (AICPU not disabled) |

#### Finer-grained sync — token-level arrival flags

The CrossRankSync* entry points are a COARSE whole-card barrier — one sync per
stage. An op is NOT bound to that granularity: a 1-to-1 sync over ANY GM
address needs NO atomicAdd — the producer WRITES a known value to an arrival
flag after the token's data; the receiver polls that address until the value
appears, then reads the slot (token-granularity send/receive — a pipelined
producer/consumer across ranks instead of a full-card barrier per exchange).
The flag address here is NOT tied to `GET_SYNC_GM_IN_RANK` — that macro only
feeds the example's pre-planned sync region; a token-level flag may live
anywhere the op's memory plan decides (e.g. adjacent to the token's data
slot). GM alignment granularity for flag/data placement: see
`memory_constraints.md`.

Arrival flags require a DETERMINISTIC initial value (0) — GM is dirty at entry
(the dirty-flag rule), so zero the flag addresses first. A written flag keeps
its value across dispatches (no atomicAdd accumulation to track) —
distinguish rounds by writing a per-round value (e.g. the round index), or
have the receiver restore 0 after consuming so the slot is reusable.

#### Inter-core sync (AIC ↔ AIV)

Every MIX kernel handshakes AIC↔AIV via `AscendC::SyncAll<false>` (count barrier; call counts MUST match across all cores — the #1 deadlock cause) or the finer-grained `CrossCoreSetFlag<2>`/`CrossCoreWaitFlag`. The full rules — `SyncAll` semantics, count matching, branch structure, deadlock examples, review checklist — live in `sync_fundamentals.md` §10. MC²-specific: AIC never joins cross-rank communication — the inter-core and cross-rank layers do not nest (during cross-rank communication, AIC blocks idle at their own `SyncAll<false>` wait).

---

### P-P112: MC² Window RDMA — one-sided put/get communication pattern

**Severity**: Medium | **Source**: reference op HCCL-resource util header (window topology, owner-authorized, design §3.1).

The window addresses from P-P110 (`GetWindowsInAddr` / `GetWindowsOutAddr`) are RDMA-registered GM regions pre-allocated per rank-pair by the HCCS framework. No standalone code — this entry is the *usage pattern* for one-sided communication, building on P-P110's methods.

#### Call skeleton (end-to-end put → signal → wait → get)

Symmetric put/get, mode B (sender writes peer slab, receiver reads own slab). The `SyncAll` wrapping follows the P-P111 3-step skeleton — do not re-derive it:

```cpp
// peerWin/ownWin = the window slab. Mode B: sender writes the peer's slab, receiver reads own.
// Ordering: WRITE precedes the sender's SIGNAL; the receiver's WAIT precedes READ. A SyncAll
// BEFORE the WRITE or AFTER the READ is not required by this pattern — add one only if a
// surrounding stage needs it.

// === sender: WRITE → (SyncAll → SIGNAL → SyncAll) ===
/* WRITE your tile into the peer's window slab (DataCopy) */
AscendC::SyncAll<true>();                                              // all cores finished writing
CrossRankSyncInRandomMemValue(rankSize, rankId, flagId);   // cross-rank SIGNAL: data ready
AscendC::SyncAll<true>();                                              // spread sync state to all cores on card

// === receiver: (SyncAll → WAIT → SyncAll) → READ ===
AscendC::SyncAll<true>();                                              // all cores ready to wait
CrossRankSyncInRandomMemValue(rankSize, rankId, flagId);   // cross-rank WAIT for peer's write
AscendC::SyncAll<true>();                                              // spread sync state to all cores on card
/* READ your own window slab (DataCopy) */
```

#### Send/recv modes & pitfall

```cpp
// windowsIn / windowsOut are two INDEPENDENT symmetric slabs — "In"/"Out" carry NO
// send/recv direction. Use either slab; the only rule is sender and receiver point at
// the SAME slab. Examples below use windowsIn throughout.
//
// Two send/recv modes (equivalent; prefer mode B) — the difference is self rank vs peer
// rank, NOT In vs Out:
//   mode A: sender writes GetWindowsInAddr(selfRank), receiver reads GetWindowsInAddr(peerRank)
//   mode B: sender writes GetWindowsInAddr(peerRank), receiver reads GetWindowsInAddr(selfRank)

// sender: WRITE into the slab, THEN signal peers
//   WRITE your tile into GetWindowsInAddr(/* selfRank(mode A) | peerRank(mode B) */)
//   ... 3-step SyncAll wrap (see skeleton above) ...
//   CrossRankSyncInRandomMemValue(...)   ← SIGNAL peers: data ready

// receiver: WAIT, THEN READ from the slab
//   CrossRankSyncInRandomMemValue(...)   ← WAIT for peer's write
//   ... 3-step SyncAll wrap ...
//   READ your tile from GetWindowsInAddr(/* peerRank(mode A) | selfRank(mode B) */)

// ❌ Pitfall (permanent hang): sender GetWindowsOutAddr + receiver GetWindowsInAddr — the write
//    and read land on two different slabs, the receiver never sees the data, DataCopy blocks
//    forever. Root cause is asymmetric send/recv, NOT "using windowsOut".
```

All window addresses return as `GM_ADDR` (raw `__gm__ void*`) — wrap into an `AscendC::GlobalTensor<T>` before `DataCopy` / `SetAtomicAdd` / `GetPhyAddr`.

---

**Dependencies**: P-P110 (HcclResource) → P-P112 (window addr methods + usage); P-P112 is a usage pattern, not a header.

---

## Path 3 — shmem comm domain + shmem-allocated shared-memory communication

Reserved — not covered yet.
