---
applies_to: soc=all
reason: Pipe sync — intra-core (PIPE_S/V/MTE2/MTE3/Cube, §1-§9) + inter-core AIC↔AIV (SyncAll/CrossCoreSetFlag/CrossCoreWaitFlag, §10) — is a universal foundation for EVERY AscendC kernel, not specific to a5/a3/a2. The --cce-auto-sync flag decides whether the compiler inserts sync for you, affecting every op. The intra-core pipe-sync instructions (SetFlag/WaitFlag/PipeBarrier) target the SIMD programming model — they do NOT apply to SIMT. Arch differences are confined to eventID pool size (A2/A3 = 8 vs legacy = 4, see §5) and the A5 LocalMemBar substitute (P-P95).
---

# Domain: Sync Fundamentals

> The systematic method for "what sync do I insert" — analysis by address-space dataflow, forward + reverse dependency rules, loop patterns, pitfalls, and a checklist; §10 adds the inter-core (AIC↔AIV) layer. This is the home for **generic sync principles**; one-off bug reports (PB-*) are witnesses referenced in §11, NOT the knowledge base.
> Load when: kernel has Local Memory data dependency, `--cce-auto-sync=off`, TBuf-managed buffers, a loop reusing UB, eventID selection, an AIC↔AIV handshake in a MIX kernel, or a precision/data-error signature suspected of missing sync.
> chip_scope: **all** — pipe types are consistent across arch; A2/A3 eventID pool = 8.
> Scope note: §1-§9 cover **intra-core** (one core, pipe-to-pipe; SIMD model — the pipe-sync instructions do NOT apply to SIMT); §10 covers **inter-core** (AIC↔AIV). Cross-rank (card) sync is a separate layer, out of this document's scope.

## 1. Why Sync — Asynchronous Parallel Execution Model

AI Core execution units are **fully asynchronous and parallel**. Each runs on its own "pipe"; the pipe names used throughout this doc:

| Pipe | Unit | Data direction |
|---|---|---|
| `PIPE_S` (Scalar) | Scalar | control — reads & dispatches ALL instructions |
| `PIPE_V` (Vector) | Vector | UB compute (and L0C↔UB) |
| `PIPE_M` (Cube) | Cube | L0A/L0B → L0C matrix compute |
| `PIPE_MTE2` | DMA in | GM/L2 → Local (UB / L1 / L0) load |
| `PIPE_MTE3` | DMA out | Local → GM/L2 store |
| `PIPE_MTE1` | DMA | L1 → L0A/L0B |
| `PIPE_FIX` (Fixpipe) | — | L0C → GM/L1 output |

Vector dataflow: `GM --(MTE2)--> UB --(V)--> UB --(MTE3)--> GM`.
Cube dataflow: `GM --(MTE2)--> L1 --(MTE1)--> L0A/L0B --(M)--> L0C --(FIX)--> GM`.

- **Scalar** dispatches instructions to the other pipes and **continues immediately**, never waiting for the dispatched instruction to finish.
- **V / Cube / MTE2 / MTE3 / ...** execute asynchronously on their own pipes, fully decoupled from Scalar's progress.
- Without explicit sync, Scalar can keep dispatching MTE2→V→MTE3 back-to-back; all three advance simultaneously and **data dependencies are NOT guaranteed**.

If `dstLocal` is V's output and MTE3's input, with no sync in between → MTE3 may move the data before V finishes writing → data corruption.

**Conclusion: data dependencies must be enforced by the developer with explicit sync instructions** (`PipeBarrier` / `SetFlag`+`WaitFlag`); the hardware does not infer dependencies. `TQue` lets the framework do this for you; `TBuf` and bare `DataCopy`/`LocalTensor` do not (see §6).

**Corollary — the S-dispatch vs S-UB-touch boundary** (decides whether an `S↔MTE` flag is needed): Scalar **dispatching** an MTE/V instruction is control flow — it hands the instruction to the target pipe's queue and moves on; the dispatch itself moves no UB data, so it creates NO UB dependency. An `S↔MTE` flag is required ONLY when Scalar **directly touches UB** — `SetValue` writing UB (→ `S_MTE3` before MTE3 reads it) or `GetValue` reading MTE2-loaded UB (→ `MTE2_S`). Do NOT insert `S_MTE2`/`S_MTE3` just because a preceding routine *ran on* the S pipe (e.g. a soft barrier's poll); if S only dispatched the following `DataCopy`, no flag is needed.

The corollary's `S_MTE3` case assumes SetValue is the FIRST write to that UB word in the current pass. If another pipe (typically `V` via `Duplicate`/`Cast` clearing or staging the same word) wrote it earlier in program order, that prior write is asynchronous and may land AFTER SetValue — overwriting the staged scalar. Fence the prior writer to completion before SetValue: `SetFlag<HardEvent::V_S>(eid)` + `WaitFlag<HardEvent::V_S>(eid)` (see §8 cross-pipe producer-producer).

```cpp
// WRONG — S only DISPATCHED the DataCopy; no UB data flows from S, so the flag is spurious:
//   AscendC::SetFlag<AscendC::HardEvent::S_MTE2>(id);
//   AscendC::WaitFlag<AscendC::HardEvent::S_MTE2>(id);
//   AscendC::DataCopy(ub, gm, n);
// RIGHT — dispatch is control flow; the MTE2 queue is self-ordered, no flag needed:
//   AscendC::DataCopy(ub, gm, n);
```

## 2. auto-sync: on vs off (decides whether you insert sync manually)

The compiler can auto-insert some sync based on LocalTensor dependency analysis (default on, `--cce-auto-sync=on`):

- **on**: the compiler auto-inserts SetFlag/WaitFlag for "obvious" cross-pipe dependencies and serializes adjacent same-pipe ops. But it only covers the forward, in-iteration case; complex address overlap / indirect indexing / reverse (cross-iteration) dependencies still need manual sync.
- **off** (MC² enforces it; some projects set it explicitly): the compiler **inserts nothing** — every sync must be manual, **including V→V same-pipe** (under on the compiler serializes adjacent V; **under off that serialization is GONE** — adjacent V ops that read+write the same UB tensor need an explicit `PipeBarrier<PIPE_V>()`, see OL-195).

To check whether your project is off: inspect the bisheng compile options in `op_kernel/CMakeLists.txt`. MC² mode is always off. **The rest of this doc assumes you must insert sync yourself** (the safe mental model regardless of the flag).

## 3. Intra-Core Sync Decision Tree

```
Local Memory data dependency exists?
├── Within the same pipe (e.g. two V APIs read/write the same UB tensor)
│   └── PipeBarrier<PIPE_V>()        [between MIDDLE ops; NOT after the last — §8]
├── Cross-pipe, within one iteration (e.g. MTE2 load then V compute)
│   └── SetFlag<HardEvent::MTE2_V>(eid) + WaitFlag<HardEvent::MTE2_V>(eid)   [forward, §5]
├── Cross-iteration on the SAME address space (a loop reusing a TBuf)
│   └── reverse sync — see §7 (forward alone is NOT enough)
├── Scalar must wait for all pipes (perf timing)
│   └── PipeBarrier<PIPE_ALL>()      [use sparingly, §4]
└── No dependency (disjoint address spaces)
    └── No sync needed
```

## 4. Single-Pipe Sync: PipeBarrier

Stalls the named pipe so its later instructions wait for earlier ones to finish.

| PipeBarrier | Effect |
|---|---|
| `PipeBarrier<PIPE_V>()` | Order within V pipe (V→V required under auto-sync=off) |
| `PipeBarrier<PIPE_MTE2>()` / `<PIPE_MTE3>()` | Order within DMA pipes (on address overlap) |
| `PipeBarrier<PIPE_ALL>()` | Stalls all pipes — **only for perf timing / wait-for-all; do not overuse** (perf cost) |

- **`PipeBarrier<PIPE_S>()` is forbidden** — the S pipe is inherently synchronous; calling it deadlocks (OL-35). To make Scalar wait on a pipe, use `WaitFlag` with the corresponding `HardEvent::X_S`.
- **`PipeBarrier<PIPE_ALL>()` is functionally the STRONGEST sync** — it stalls every pipe, so it CAN substitute for any single-pipe (`PIPE_V`) or cross-pipe (`SetFlag/WaitFlag`) sync; the only cost is performance (it serializes all pipes and kills overlap). Prefer the precise `PipeBarrier<PIPE_X>()` / `SetFlag/WaitFlag` for overlap, NOT because PIPE_ALL is functionally insufficient. (PB-21 in PLATFORM_BUGS claims a V220 TBuf+PIPE_ALL 507015 crash; it is hypothesis-unconfirmed, A5-unverified, and contradicts the functional model above — **this domain does NOT adopt PB-21**: PIPE_ALL is treated as functionally sufficient, just perf-costly.)

**Function-end / stage-boundary drain** — when the intent is "every pipe must finish before this function returns / this stage hands off", use ONE `AscendC::PipeBarrier<PIPE_ALL>()`, NOT a stack of `SetFlag`/`WaitFlag` pairs assembled to mimic a drain. And do NOT re-drain right before/after a barrier that already drains every pipe (e.g. `AscendC::SyncAll` issues `PipeBarrier<PIPE_ALL>` internally — see §10).

```cpp
// WRONG — assembling Set/Wait pairs to "drain", right before a barrier that already drains everything:
//   WriteTile();
//   AscendC::SetFlag<AscendC::HardEvent::V_MTE3>(id1);
//   AscendC::WaitFlag<AscendC::HardEvent::V_MTE3>(id1);
//   AscendC::SetFlag<AscendC::HardEvent::MTE3_S>(id2);
//   AscendC::WaitFlag<AscendC::HardEvent::MTE3_S>(id2);
//   AscendC::SyncAll<true>();
// RIGHT — the barrier already drains every pipe:
//   WriteTile();
//   AscendC::SyncAll<true>();
// (With NO following barrier, a genuine function-end drain is one call: AscendC::PipeBarrier<PIPE_ALL>();)
```

## 5. Cross-Pipe Sync: SetFlag / WaitFlag + HardEvent

Scalar dispatches both Set and Wait, but **the pipe that actually blocks is the target pipe**; Scalar itself does not wait (unless the target is S). `SetFlag<SRC_DST>` tells the SRC pipe "notify DST when you're done"; `WaitFlag<SRC_DST>` makes DST block until that notification.

### 5.1 HardEvent Cheatsheet (naming = `src_pipe_dst_pipe`, dst waits for src)

**Vector dataflow (GM→UB→GM):**

| Event | Semantics |
|---|---|
| `MTE2_V` | MTE2 load done → V starts |
| `V_MTE3` | V done → MTE3 store starts |
| `V_MTE2` | V done → MTE2 (reverse sync in loops) |
| `S_MTE3` | Scalar SetValue done → MTE3 |
| `MTE2_S` | MTE2 load done → Scalar reads (shape/header metadata) |
| `S_V` / `V_S` | Scalar↔Vector UB handoff. `V_S`: V writes UB → S touches it — **GetValue** (S is consumer, reads V's scalar e.g. ReduceMax→GetValue) or **SetValue** (S re-writes a word V wrote, producer-producer — §8). `S_V`: S SetValue → V reads. |
| `MTE2_MTE3` | MTE2 load done → MTE3 store starts (pure-copy GM→UB→GM, no V) |
| `MTE3_MTE2` | reverse sync in a pure-copy loop |

**Cube dataflow (GM→L1→L0A/L0B→Cube→L0C→GM):**

| Event | Semantics |
|---|---|
| `MTE2_MTE1` | MTE2 into L1 done → MTE1 into L0A/L0B |
| `MTE1_M` | MTE1 done → Cube compute |
| `M_FIX` | Cube done → Fixpipe (L0C→GM/L1) |

### 5.2 eventID Rules (violation = hang / undefined behavior)

The eventID used by intra-core SetFlag/WaitFlag is a **binary flag** (0/1), NOT a counter:

1. **Never hard-code an eventID value** — obtain it via `FetchEventID` / `AllocEventID`, otherwise it clashes with framework-internal events and hangs.
2. **Set / Wait must pair 1:1** — two consecutive Set on the same eventID with no Wait = undefined behavior.
3. **Pool size**: each HardEvent type has its own eventID pool; A2/A3 = 8 (ID 0-7), legacy = 4.

| Scenario | API | Note |
|---|---|---|
| Non-loop, Set then immediate Wait | `FetchEventID` | Equivalent to Alloc+immediate Release; does not hold a bitmap bit; first choice for simple cases |
| Loop reuse OR cross-function lifetime | `AllocEventID` + `ReleaseEventID` | Locks the bitmap bit so no other API grabs the same ID; must be paired (§7.4) |

## 6. TQue vs TBuf — Implicit Sync

| Model | Sync | Note |
|---|---|---|
| `TQue<VECIN/VECOUT, N>` | **auto-inserted by the framework** | EnQue/DeQue/AllocTensor/FreeTensor internally insert the matching SetFlag/WaitFlag; N≥2 also enables pipe overlap. **Prefer this.** |
| `TBuf<VECCALC>` | **inserts NO sync** | Bare UB allocation; every cross-pipe dependency MUST be handled manually. Functionally `PipeBarrier<PIPE_ALL>()` serializes all pipes and would cover any dependency — but it kills overlap; prefer explicit `SetFlag/WaitFlag` (§5, §7) for precision + parallelism. |

**TQue VECIN** (MTE2 produces / V consumes) internal sync:

| Op | Internal call |
|---|---|
| `EnQue` | `SetFlag<MTE2_V>` |
| `DeQue` | `WaitFlag<MTE2_V>` |
| `FreeTensor` | `SetFlag<V_MTE2>` |
| `AllocTensor` | `WaitFlag<V_MTE2>` (first round INVALID, no Wait) |

VECOUT (V produces / MTE3 consumes) analogous: `EnQue`=`SetFlag<V_MTE3>`, `DeQue`=`WaitFlag<V_MTE3>`, `FreeTensor`=`SetFlag<MTE3_V>`, `AllocTensor`=`WaitFlag<MTE3_V>`.

**TBuf + TQue mixed**: every buffer accessed by V must be EITHER TQue-managed OR have explicit SetFlag/WaitFlag, else data corruption (OL-94 rule).

---

## 7. Loop Sync — forward & reverse dependencies (the systematic method)

When a TBuf/LocalTensor is reused across loop iterations, an async op from one iteration (e.g. CopyOut/MTE3) may still be in flight when the next iteration overwrites the same buffer → data race / stale read. The fix is a **systematic per-address-space analysis**, not guessing from one bug.

### 7.1 Forward vs reverse sync (address-space granularity)

For the SAME address space (one TBuf/LocalTensor) used in a loop:

- **Forward sync** — *within one iteration*: the producer pipe writes it, then the consumer pipe reads it (e.g. MTE2 writes xBuf → V reads xBuf, same iter). Easy to notice.
- **Reverse sync** — *across iterations*: the previous iteration's consumer must finish reading before the next iteration's producer writes (e.g. V reads xBuf in iter N → MTE2 writes xBuf in iter N+1). **This is the easy-to-miss one** — "the prev consumer hasn't released the space before the next iteration writes it".

Forward alone is NOT enough in a loop; every reused address space needs BOTH.

### 7.2 Analysis method — trace dataflow at address-space granularity

For each loop-reused TBuf/LocalTensor, list which pipe writes it (via which API) and which pipe reads it, then find the cross-iteration conflict:

```
Buffer: xBuf (TBuf, half)
  producer: DataCopyPad CopyIn   → MTE2 writes
  consumer: Muls/Maxs/Cast       → V reads
  cross-iter conflict: iter N V reads xBuf, iter N+1 MTE2 writes xBuf
  sync needed: V→MTE2 reverse  (WaitFlag<V_MTE2> at loop top)

Buffer: outBuf (TBuf, int8_t)
  producer: Cast                  → V writes
  consumer: DataCopyPad CopyOut  → MTE3 reads
  cross-iter conflict: iter N MTE3 reads outBuf, iter N+1 V writes outBuf
  sync needed: MTE3→V reverse  (WaitFlag<MTE3_V> before V writes)
```

**General rule**: in ANY loop, for EVERY address space touched, enumerate every pipe that reads/writes it and add both forward (within-iter) and reverse (cross-iter) sync for each read-after-write pair. Do not stop at one buffer or one pipe — a common bug is protecting outBuf but forgetting xBuf (§8).

### 7.3 Reverse Set/Wait placement rule

Reverse sync Set/Wait must be split across the loop boundary to form a `Set(t=N) → Wait(t=N+1)` handoff chain:

- **SetFlag** — before the loop (prime the first iteration, which has no prior async op) + at the end of the loop body (after the producer/consumer finishes releasing the space)
- **WaitFlag** — at the top of the loop body (before the op that re-touches the space) + after the loop (consume the last Set so Set/Wait stays paired)

### 7.4 eventID for loops

Reuse one eventID across iterations via `AllocEventID` outside the loop + `ReleaseEventID` after — this locks the bitmap bit so no other API grabs the same ID. `FetchEventID` does NOT lock the bit, so it is for one-shot Set-then-immediate-Wait only, not loop reuse. (OL-94 shows an alternative `FetchEventID`-outside-loop pattern that also works because Set/Wait pair 1:1 each iter; `AllocEventID` is the conservative recommendation.)

### 7.5 Patterns

**Pattern 1 — tile loop (CopyIn → Compute → CopyOut)** — one xBuf (MTE2 write / V read) + one outBuf (V write / MTE3 read), both reused per iter. Reverse: `V_MTE2` (xBuf) + `MTE3_V` (outBuf). Reference layout:

```cpp
// Alloc eventIDs outside loop (reverse V_MTE2, MTE3_V + forward MTE2_V, V_MTE3)
auto evtMte2V = GetTPipePtr()->AllocEventID<HardEvent::MTE2_V>();
auto evtVMte3 = GetTPipePtr()->AllocEventID<HardEvent::V_MTE3>();
auto evtMte3V = GetTPipePtr()->AllocEventID<HardEvent::MTE3_V>();
auto evtVMte2 = GetTPipePtr()->AllocEventID<HardEvent::V_MTE2>();

SetFlag<HardEvent::V_MTE2>(evtVMte2);   // prime: first CopyIn has no prior V
SetFlag<HardEvent::MTE3_V>(evtMte3V);   // prime: first V has no prior MTE3

for (uint32_t t = 0; t < numTiles; ++t) {
    WaitFlag<HardEvent::V_MTE2>(evtVMte2);          // reverse: MTE2 waits prev V done reading xBuf
    DataCopyPad(xLocal, xGm_[off], ...);            // CopyIn: MTE2 writes xBuf
    SetFlag<HardEvent::MTE2_V>(evtMte2V); WaitFlag<HardEvent::MTE2_V>(evtMte2V);  // forward: V waits MTE2
    Muls(xLocal, xLocal, scale, n); PipeBarrier<PIPE_V>();   // V reads xBuf (mid V ops fenced)
    WaitFlag<HardEvent::MTE3_V>(evtMte3V);          // reverse: V waits prev MTE3 done reading outBuf — BEFORE the write below
    Cast(outLocal, xLocal, ..., n);                 // V writes outBuf (last V op — no trailing PipeBarrier<PIPE_V>)
    SetFlag<HardEvent::V_MTE2>(evtVMte2);           // V done reading xBuf
    SetFlag<HardEvent::V_MTE3>(evtVMte3); WaitFlag<HardEvent::V_MTE3>(evtVMte3);  // forward: MTE3 waits V
    DataCopyPad(outGm_[off], outLocal, ...);        // CopyOut: MTE3 reads outBuf
    SetFlag<HardEvent::MTE3_V>(evtMte3V);           // MTE3 done reading outBuf
}
WaitFlag<HardEvent::V_MTE2>(evtVMte2);              // post-loop: consume last reverse Sets
WaitFlag<HardEvent::MTE3_V>(evtMte3V);
PipeBarrier<PIPE_MTE3>();
ReleaseEventID<...>(...);  // release all four
```

Key points: ① **Defer `Wait<MTE3_V>` until just before the V op that actually writes outBuf** (Cast) — the read-only Muls can overlap the prev iter's MTE3; ② the **last V op needs no `PipeBarrier<PIPE_V>`** — the following `V_MTE3` SetFlag already waits for all of V; ③ Set/Wait pair strictly (pre-loop Set + post-loop Wait).

**Pattern 2 — GM streaming loop (CopyIn → CopyOut, no compute)** — one rowBuf, MTE2 write / MTE3 read. Because no V op touches the buffer, the forward handoff is `MTE2_MTE3` directly and the reverse is `MTE3_MTE2` — the V pipe is NOT involved. A common error is routing the copy through V (`MTE2_V` then `V_MTE3`) just because "MTE2→V→MTE3" is the familiar compute-pipeline shape; with no V compute that drags an idle V pipe in as a relay and adds two needless sync points.

```cpp
// WRONG — V is idle, yet dragged in as a relay between MTE2 and MTE3:
//   AscendC::DataCopy(ub, gmIn, n);                       // MTE2 writes ub
//   AscendC::SetFlag<AscendC::HardEvent::MTE2_V>(e1);
//   AscendC::WaitFlag<AscendC::HardEvent::MTE2_V>(e1);
//   AscendC::SetFlag<AscendC::HardEvent::V_MTE3>(e2);
//   AscendC::WaitFlag<AscendC::HardEvent::V_MTE3>(e2);
//   AscendC::DataCopy(gmOut, ub, n);                      // MTE3 reads ub
// RIGHT — pure copy: forward MTE2_MTE3 + reverse MTE3_MTE2, no V:
//   auto eFwd = GetTPipePtr()->AllocEventID<AscendC::HardEvent::MTE2_MTE3>();
//   auto eRev = GetTPipePtr()->AllocEventID<AscendC::HardEvent::MTE3_MTE2>();
//   AscendC::SetFlag<AscendC::HardEvent::MTE3_MTE2>(eRev);            // prime: first MTE2 has no prior MTE3
//   for (...) {
//       AscendC::WaitFlag<AscendC::HardEvent::MTE3_MTE2>(eRev);       // reverse: prev MTE3 done reading ub
//       AscendC::DataCopy(ub, gmIn, n);                               // MTE2 writes ub
//       AscendC::SetFlag<AscendC::HardEvent::MTE2_MTE3>(eFwd);
//       AscendC::WaitFlag<AscendC::HardEvent::MTE2_MTE3>(eFwd);       // forward: MTE3 waits MTE2
//       AscendC::DataCopy(gmOut, ub, n);                              // MTE3 reads ub → writes GM
//       AscendC::SetFlag<AscendC::HardEvent::MTE3_MTE2>(eRev);        // reverse prime for next iter
//   }
//   AscendC::WaitFlag<AscendC::HardEvent::MTE3_MTE2>(eRev);           // post-loop: consume last reverse Set
//   GetTPipePtr()->ReleaseEventID<AscendC::HardEvent::MTE2_MTE3>(eFwd);  // release both bitmap bits (paired with Alloc)
//   GetTPipePtr()->ReleaseEventID<AscendC::HardEvent::MTE3_MTE2>(eRev);
```

**Pattern 3 — double buffer** — two fully independent resource sets (separate UB regions + separate eventIDs per pipeline) rotating; the two pipelines share NOTHING, so they run truly async. Each pipeline still needs its own forward + reverse Set/Wait chain on its own address space.

**Pattern 4 — nested loop (outer tile + inner accumulate)** — a scratch buffer reused by an INNER loop, where the inner loop sits inside an outer tile loop. The inner-loop buffer needs its OWN forward + reverse Set/Wait chain on an INDEPENDENT eventID — it cannot share the outer loop's reverse chain, because the outer reverse Set fires once per OUTER iter (after the inner loop fully drains) and does nothing for the inner across-iteration reuse.

Why the inner loop is its own sync domain: the inner loop reuses the scratch buffer across INNER iterations (N → N+1), a read-after-write the outer loop's reverse never sees. A single inner iteration masks the race — it surfaces when the inner loop runs ≥2 iterations.

```cpp
// WRONG — inner loop has only forward, no reverse:
for (/* outer tile */) {                                     // outer
    for (uint32_t p = 0; p < peerCount; ++p) {               // inner — reuses scratchBuf
        AscendC::DataCopy(scratchBuf, /* src */);            // MTE2 write scratchBuf
        AscendC::SetFlag<AscendC::HardEvent::MTE2_V>(eFwd);
        AscendC::WaitFlag<AscendC::HardEvent::MTE2_V>(eFwd); // forward only — NO reverse
        AscendC::Add(accBuf, accBuf, scratchBuf /* , count */); // in-place accBuf += scratchBuf: accBuf read+write (V→V RAW), scratchBuf read
        AscendC::PipeBarrier<PIPE_V>();                // fence V→V RAW on accBuf before next inner iter's Add reads it
    }
}

// RIGHT — inner loop gets its own V_MTE2 reverse on an independent eventID:
auto eRev = GetTPipePtr()->AllocEventID<AscendC::HardEvent::V_MTE2>();
AscendC::SetFlag<AscendC::HardEvent::V_MTE2>(eRev);          // prime: 1st inner iter has no prior V read
for (/* outer tile */) {
    for (uint32_t p = 0; p < peerCount; ++p) {
        AscendC::WaitFlag<AscendC::HardEvent::V_MTE2>(eRev); // reverse: prev inner iter done reading scratchBuf
        AscendC::DataCopy(scratchBuf, /* src */);
        AscendC::SetFlag<AscendC::HardEvent::MTE2_V>(eFwd);
        AscendC::WaitFlag<AscendC::HardEvent::MTE2_V>(eFwd); // forward
        AscendC::Add(accBuf, accBuf, scratchBuf /* , count */); // in-place accBuf += scratchBuf → V→V RAW on accBuf
        AscendC::SetFlag<AscendC::HardEvent::V_MTE2>(eRev);  // reverse prime for next inner iter
        AscendC::PipeBarrier<PIPE_V>();             // fence V→V RAW on accBuf (in-place Add) before next inner iter reads it
    }
}
AscendC::WaitFlag<AscendC::HardEvent::V_MTE2>(eRev);         // post-inner-loop: consume last Set
GetTPipePtr()->ReleaseEventID<AscendC::HardEvent::V_MTE2>(eRev);
```

Generalize §7.2 to nested loops: apply the per-address-space forward+reverse analysis at EACH loop level — a buffer reused by an inner loop needs reverse sync in the inner-loop dimension, with its own eventID, regardless of whether the outer loop also has reverse sync for its own buffers.

---

## 8. Pitfalls (from the §7 analysis — not one-off bug reports)

- **Address-space reuse: drain the prior consumer before re-writing** (general — applies to EVERY address space and ANY pipe pair; NOT specific to UB/MTE2/V). When ANY address space (`TBuf` UB / L1 / L0A/L0B / L0C / `__gm__` GM) is written again after being read by some prior pipe, the later write MUST stall until every prior pipe reading it has finished. The hazard is "producer overwrites an address a consumer still reads" — it exists for ANY (producer, consumer) pipe pair, loop or no loop.
  - The trigger is **same-address reuse**, not the pipe type — UB reused, L1 reused, GM scratch reused all fire the same rule.
  - AscendC auto-sync inserts only the OBVIOUS forward in-iteration dependency; it NEVER covers "consumer drained → next producer may write" across a reuse. That is on the developer for EVERY reused address.
  - A same-pipe barrier (`PipeBarrier<PIPE_X>`) fences X↔X only; it does NOT fence the consumer's pipe against the re-writing pipe when they differ. Use the matching cross-pipe `SetFlag/WaitFlag<HardEvent::CONSUMER_PRODUCER>`.
  - Signature: often masked under a single execution path (re-write lands late / consumer happens to have drained); surfaces under multi-rank / multi-core / heavy load — "passes single-config, silently wrong multi-config".
  - Fix: before every write that re-targets a previously-read address, insert a reverse `SetFlag/WaitFlag<HardEvent::CONSUMER_PRODUCER>` (`PipeBarrier<PIPE_ALL>()` as a perf-costly fallback); Set after the prior consumer drains, Wait before the re-write.

  Concrete pipes below are illustrative — the hazard is address-reuse, NOT this specific pair; any producer/consumer pair behaves the same:

  ```cpp
  // buf = a reused address space. producer writes it, consumer reads it, producer writes it AGAIN.
  AscendC::DataCopy(buf, gmIn0, n);            // producer writes buf
  AscendC::SetFlag<AscendC::HardEvent::MTE2_V>(e);
  AscendC::WaitFlag<AscendC::HardEvent::MTE2_V>(e);
  AscendC::Cast(out, buf, n);                  // consumer reads buf
  // ... same buf targeted again ...
  AscendC::DataCopy(buf, gmIn1, n);            // WRONG: re-write before the consumer drained buf
  //   ↑ torn data under multi-core/multi-rank: the consumer may still be reading buf from above.

  // RIGHT — fence the prior consumer before the re-write:
  AscendC::SetFlag<AscendC::HardEvent::V_MTE2>(e2);   // consumer done reading buf
  AscendC::WaitFlag<AscendC::HardEvent::V_MTE2>(e2);  // producer waits before re-writing buf
  AscendC::DataCopy(buf, gmIn1, n);
  ```
- **Cross-pipe producer-producer race (write→write on the same address)** — when two DIFFERENT pipes write the same UB word (or any reused address space) in program order, the hardware does NOT guarantee the later-in-program-order write lands last. Common shape: `V Duplicate/clear (32 B)` → `PipeBarrier<PIPE_V>` → `S SetValue(word[0])` → `SetFlag/WaitFlag<S_MTE3>` → `MTE3 DataCopyPad`. `PipeBarrier<PIPE_V>` fences V↔V only; S dispatches and continues immediately (§1), so SetValue can execute and land BEFORE V's asynchronous `Duplicate` finishes — V's late write then zeros the scalar S just staged, and MTE3 ships a 0. This is the write→write counterpart of the read→write drainage rule above (hazard: "second writer lands before the first writer is done", not "producer overwrites a reader"). Easy to miss — the `Duplicate + SetValue + S_MTE3 + DataCopyPad` shape recurs in many reference quant/cast staging kernels and "passes" under light load, surfacing under multi-core/multi-rank (the "passes single-config, silently wrong multi-config" signature). Fix: fence the prior writer to completion before the second writer touches the word — `SetFlag<HardEvent::V_S>(eid)` after the V op + `WaitFlag<HardEvent::V_S>(eid)` before SetValue (`FetchEventID` for the one-shot pair; `PipeBarrier<PIPE_ALL>()` is a perf-costly fallback); better still, restructure so a single V op both clears and stages the scalar (no S SetValue, no race). Reviewer gate: a `V write → S SetValue` on the same UB word with no `V_S` between them is a stale-write hazard — flag it; whether the hardware happens to serialize same-word V/S writes is NOT architecturally guaranteed, so rely on the explicit flag.

- **Missing V→V barrier**: several V ops read/write the same LocalTensor back-to-back with no sync → each may read the prior op's unfinished result. Fix: `PipeBarrier<PIPE_V>()` BETWEEN the middle V ops; the LAST V op needs none (the following `V_MTE3` SetFlag waits for all of V). **Over-syncing** — a barrier after every V op including the last — wastes cycles; place barriers only where a real same-tensor RAW exists.
- **Reverse WaitFlag in the wrong place**: `Wait<MTE3_V>` placed AFTER CopyOut — but V already wrote outBuf by then; the wait must go BEFORE the V op that writes outBuf (Cast), so the prev iter's MTE3 finishes reading first.
- **Missing one buffer's reverse sync**: added outBuf's `MTE3_V` but forgot xBuf's `V_MTE2` → iter N+1 MTE2 CopyIn overwrites xBuf while iter N V still reads it. §7.2's per-buffer analysis catches this — every address space gets its own forward + reverse pair.
- **Missing post-loop WaitFlag (Set/Wait unpaired)**: the last iteration's reverse SetFlag is never consumed → undefined. Add a post-loop WaitFlag for every reverse event.
- **Nested-loop inner buffer missing its own reverse**: outer tile loop has reverse sync for its buffers (xBuf/outBuf), but an inner loop reusing a separate scratch buffer gets only forward → inner across-iteration RAW race. Apply §7.2 per-buffer analysis at EACH loop level; inner-loop buffer needs its own reverse on an independent eventID. See Pattern 4.

## 9. Checklist

Run through in order once the code is written:

- **Unify eventID management** — project-level `AllocEventID`/`ReleaseEventID` (coexists safely with third-party libs that use `FetchEventID`); never mix TPipe-managed and hard-coded eventIDs WITHIN the same op stage.
- **Pick the right eventID API** — loop reuse or cross-function lifetime → `AllocEventID` + `ReleaseEventID`; one-shot Set-then-immediate-Wait → `FetchEventID` (allowed ONLY there).
- **MUST do address-space dependency analysis, insert full forward + reverse sync** — for every TBuf/LocalTensor used in a loop, annotate which API (which pipe) writes and which reads; complete forward (Producer→Consumer `SetFlag`/`WaitFlag`) AND reverse (iter N consumer done → iter N+1 producer may write) for EACH address space independently (§7.2).
- **Avoid redundant sync** — pipe ops on disjoint address spaces need no sync between them.
- **Place reverse sync correctly** — the reverse WaitFlag goes before the first write to that address space in the current iteration (§8 pitfall).
- **Set/Wait must pair** — including the pre-loop prime Set and the post-loop consume Wait.
- **Reverse-fence COVERAGE at each re-write boundary, not just Set/Wait pairing** — for every reused address space (UB/L1/L0/GM; loop or no loop), enumerate its WRITE and READ points over one full pass; at EACH adjacent `prior-read → re-write` boundary — **including boundaries INSIDE the same pass/iteration (e.g. an own-stage V read followed by a loop's first-entry re-write of the same buffer), NOT only cross-iteration boundaries** — confirm the `WaitFlag` gating the re-write is released by a `SetFlag` that fires **after that specific prior read drains**. A globally 1:1 Set/Wait pair is NOT enough if the Wait resolves against a **prime Set** (fired once before the path; covers only "no prior read on first entry") or an **earlier pass's Set** — neither covers a prior read within the SAME pass before this re-write. Trace each reverse chain's prime placement explicitly: a prime Set before an outer loop does NOT cover same-pass reads inside that loop, AND a loop's own reverse chain does NOT cover a prior read that happened BEFORE the loop's first iteration (its prime covers only first-entry). Pairing is necessary; per-boundary (incl. intra-pass) coverage is sufficient.
- **Cross-pipe write→write on the same address** — if two different pipes write the same UB word / address space in one pass (common shape: `V Duplicate/clear` then `S SetValue` on word[0]), confirm a `V_S` (or matching `<X_S>`) flag fences the first writer to completion before the second writes; `PipeBarrier<PIPE_V>` alone does NOT cover S (§1 corollary, §8).
- **Sync between consecutive V ops correctly** — `PipeBarrier<PIPE_V>()` between middle V ops on the same tensor, none after the last.
- **No PIPE_ALL abuse** — only when you truly must stall all pipes (perf timing / debug / end-of-stage flush); otherwise use the precise `PipeBarrier<PIPE_X>()`.
- **Never `PipeBarrier<PIPE_S>()`** — the S pipe is inherently synchronous; this deadlocks.

## 10. Inter-Core Sync (AIC ↔ AIV) — `SyncAll` count-based barrier

§1-§9 are the intra-core layer (one core, pipe-to-pipe). This section is the **inter-core** layer: the handshake BETWEEN the AIC (cube) and AIV (vector) cores inside one MIX kernel.

A `KERNEL_TYPE_MIX_AIC_1_2` kernel runs cube (AIC) + vector/comm (AIV) cores in one binary; the AIC↔AIV handshake DEFAULTS to `AscendC::SyncAll<false>` (count barrier). `CrossCoreSetFlag<mode, pipe>(flagId)` + `CrossCoreWaitFlag(flagId)` is a VALID finer-grained alternative — it is a STANDARD AscendC API (asc-devkit `CrossCoreSetFlag(ISASI).md`), NOT FA-only: **mode 2 = AIC↔AIV sync within an AI Core**, applicable to MIX_AIC_1_2 (flagId ∈ [0,10] on A2/A3; ⚠️ Matmul high-level API uses `CrossCoreSetFlag`/`CrossCoreWaitFlag` flagIds internally — avoid collision; same flagId max 15 sets). `fa_class/cross_core_sync.md` §4 covers the FA-scenario usage, NOT a limitation on the API itself. Pick per handoff: `SyncAll` (coarse) when all cores barrier; `CrossCoreSetFlag<2>`/`CrossCoreWaitFlag` (fine) when a producer-consumer pair overlaps others.

**`SyncAll` internally issues `PipeBarrier<PIPE_ALL>`** (confirmed in the AscendC source), which drains every pipe on the core (MTE2/MTE3/V/S) before releasing the count barrier. Consequence: you do NOT need to insert any `SetFlag`/`WaitFlag`/`PipeBarrier` for MTE or V completion around a `SyncAll` call — all data touched before the `SyncAll` is already written back to HBM by the time it returns, and anything after it starts on a clean pipe state.

- `SyncAll<true>` = AIV-only barrier (AIC does NOT participate — safe when only some AIV blocks reach it).
- `SyncAll<false>` = AIC + AIV all-block barrier (the AIC↔AIV handshake).
- No `flagId`: pairs match by **ordered count** (AIC's Nth `SyncAll<false>` ↔ AIV's Nth `SyncAll<false>`).

Branch via parallel `if ASCEND_IS_AIV { }` / `if ASCEND_IS_AIC { }` (NOT if/else — the compiler prunes per core type):

```cpp
KERNEL_TASK_TYPE_DEFAULT(KERNEL_TYPE_MIX_AIC_1_2);
if ASCEND_IS_AIV {
    /* AIV produce (AIV-side pre-compute) */
    AscendC::SyncAll<false>();   // #1 notify AIC: AIV produce done
    AscendC::SyncAll<false>();   // #2 wait AIC: cube done
    /* AIV consume (AIV-side post-compute) -> SyncAll<true>() */
}
if ASCEND_IS_AIC {
    AscendC::SyncAll<false>();   // #1 wait AIV: produce done
    CubeCompute(cubeParams);     // cube (e.g. matmul)
    AscendC::SyncAll<false>();   // #2 notify AIV: cube done
}
```

**⚠️ #1 deadlock cause — `SyncAll` call counts must match across all cores**: `SyncAll<false>()` is an all-AIC+AIV barrier, `SyncAll<true>()` is an all-AIV barrier — **every participating core must call them at the same positions and the same number of times**; any core one short or one over → permanent deadlock. Static core-split via `ASCEND_IS_AIC`/`ASCEND_IS_AIV` is the easiest trap (AIC and AIV take entirely different branches; AIV adds a sync but you forget the empty matching sync on the AIC side):

```cpp
// ❌ AIV calls SyncAll<false> twice, AIC only once → permanent deadlock
if ASCEND_IS_AIC {
    RunCubeCompute();
    AscendC::SyncAll<false>();          // AIC #1
}
if ASCEND_IS_AIV {
    RunAivComputeA();
    AscendC::SyncAll<false>();          // AIV #1 ✓
    RunAivComputeB();
    AscendC::SyncAll<false>();          // AIV #2 ✗ no matching 2nd on AIC → deadlock
}
// ✅ AIC adds an empty SyncAll to match the count (must call even with no data op)
if ASCEND_IS_AIC {
    RunCubeCompute();
    AscendC::SyncAll<false>();          // AIC #1
    AscendC::SyncAll<false>();          // AIC #2 (match AIV; call even if empty)
}
if ASCEND_IS_AIV {
    RunAivComputeA();
    AscendC::SyncAll<false>();          // AIV #1
    RunAivComputeB();
    AscendC::SyncAll<false>();          // AIV #2
}
```

**Review checklist**: count the `SyncAll<false>()` calls in the AIC branch and the AIV branch — they must be identical (annotate with `// SyncAll #1 of N`); `SyncAll` must NOT sit inside a conditional `if`/`for` branch (unless that condition evaluates the same on all cores); `blockDim` must be ≤ the actual AI-core count, otherwise multi-round scheduling inserts anomalous syncs and hangs. Use `GetCoreNumAic()` for the cap, NOT `GetCoreNumAiv()` — on sub-blocked A2/A3 (1 cube : 2 vector) the latter returns 2× the AI-core count and silently over-subscribes into the same multi-round hang (observed on an MC² fusion op, A2/Ascend910B4).

**Decoupled from cross-rank**: during cross-rank communication (AIV block 0), AIC blocks idle at their own `SyncAll<false>` wait — AIC never joins cross-rank communication. The two layers do not nest.

> **Choosing the inter-core mechanism**: `SyncAll` (count-based, used here) vs `CrossCoreSetFlag<0x2,PIPE>(flagId)`/`CrossCoreWaitFlag` (flag-based, fine-grained — both standard AscendC APIs, mode 2 = AIC↔AIV; FA-class kernels in fa_class §4 are one usage, NOT an API limitation) — pick per the op. See OL-190 (cross-core group barrier symmetric participation), OL-213 (`SyncAll`→`PipeBarrier` multi-core hang #1 cause), PB-34 (manual `CrossCoreSetFlag`/`CrossCoreWaitFlag` V220 deadlock), PB-35 (`event_t` 0..3 vs cross-core flag-id conflict).

## 11. cross-ref (witnesses & adjacent layers — NOT the knowledge base)

| Topic | Entry |
|---|---|
| TQue vs PipeBarrier perf | OL-4 (TQue 1.6-2.3× faster than PIPE_ALL) |
| PIPE_S does not support PipeBarrier; S-pipe event types | OL-35 |
| PB-21 (V220 TBuf+PIPE_ALL 507015 crash) — **NOT adopted in this domain**: hypothesis-unconfirmed, A5-unverified, contradicts the functional model (PIPE_ALL stalls all pipes) | PB-21 |
| Loop reverse-sync **witnesses** (the §7/§8 method applied to real ops) | PB-47 (cross-iteration V→MTE2), PB-49 (cross-row) — these are WITNESSES of the §8 "missing reverse sync" pitfall, not the source of the method |
| TQue loop eventID reuse, TBuf+TQue mixed | OL-94 |
| event-id reuse rules | P-P26 / P-P75 |
| A5 LocalMemBar (A5 substitute for PipeBarrier) | P-P95 |
| V→V auto-sync=off serialization gone | OL-195 |
| **Inter-core** AIC↔AIV (SyncAll / CrossCoreSetFlag / CrossCoreWaitFlag) — method in §10 above | OL-190, OL-213, PB-34, PB-35, `fa_class/cross_core_sync.md` |
| **Data visibility** after the sync fires (DCache/GM coherence, DCCI, alignment granularity) — NOT this page's scope | `memory_constraints.md` (domain page), OL-307 |
