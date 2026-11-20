```
ID:        0228-bufferid-replaces-the-set-wait-pairing-requirement-across-seven-independent-instruction-queues
LABEL:     knowledge
LEVEL:     L4 (synchronisation)
STRATUM:   harvested — one upstream origin, which marks BufferID as a public-or-experience value
           with no ini field (0206 row 6). Nothing was compiled, and the regbase sync material that
           a 950 kernel actually follows still teaches paired SetFlag/WaitFlag.
BOARD:     950PR, 950DT
SOURCE:    ops/npu-arch/references/npu-arch-guide.md:287-291 — "### 指令序列与 BufferID 同步 /
           DAV_3510 上各执行单元拥有独立指令队列：Cube / FixPipe / MTE1 / MTE2 / MTE3 / SIMD VF /
           SIMT VF。/ **BufferID 同步机制**：消除原 set/wait 强制配对需求，简化多流水算子的同步代码。"
SOURCE:    ops/npu-arch/references/npu-hardware-params.md:171 — "| 6 | BufferID 取代 set/wait 同步 |
           Guide §4 指令序列与 BufferID 同步 / SKILL.md §DAV_3510 关键变化 | 公开资料 / 经验值 |"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a 950 kernel that omits a SetFlag/WaitFlag pair across two dependent pipes and produces
           bit-stable correct output across 50 runs at five shapes — the pairing requirement would
           then genuinely be gone; or a documented BufferID API absent from the installed headers,
           which would mean the mechanism is not programmer-visible at all.
```

# 0228 · BufferID replaces the set/wait pairing requirement across seven independent instruction queues

## 1 · Claim
Upstream asserts that on DAV_3510 each execution unit owns an independent instruction queue, and names
seven: Cube, FixPipe, MTE1, MTE2, MTE3, SIMD VF, SIMT VF. Upstream asserts a **BufferID synchronisation
mechanism** that eliminates the previous mandatory pairing of set and wait operations, simplifying
synchronisation code in multi-pipe operators. Upstream marks BufferID as a public-or-experience value
with no corresponding INI field. Not established here: nothing was compiled, and no BufferID API was
located in the installed toolkit.

There is a tension inside this material that this entry exists to hold open rather than resolve. Upstream
says the pairing requirement is eliminated; the regbase synchronisation guidance that a 950 kernel author
actually follows says **SetFlag/WaitFlag 必须成对出现** — must appear in pairs (0262 §3).

## 2 · The wrong branch this removes
An agent reading "BufferID eliminates set/wait pairing" stops writing pairs. If the pairing is still
required in the API surface it is actually using, the result is a missing cross-pipe dependency: MTE2
writes UB and Vector reads it before the write lands. That fails non-deterministically, at some shapes,
on some runs — the failure class the regbase pitfall material names as masquerading as precision drift
(0258 §2, 0262 §2).

The reverse branch is milder and is the safe default: keep writing pairs and forgo whatever
simplification BufferID offers. Nothing breaks; the code is more verbose than it needed to be.

The reason the first branch is live rather than hypothetical is that the two statements sit in different
skills with different audiences and neither references the other. `npu-arch` is the architecture-facts
skill and states the elimination as a headline change. `ascendc-regbase-best-practice` is the skill an
implementer opens, and its synchronisation document teaches paired `SetFlag`/`WaitFlag` with a four-event
table, an eventID pool model, and worked loop code (0262). An agent that reads the architecture skill and
writes code from the implementation skill will see the contradiction; an agent that reads only the first
will not.

Three readings reconcile them and this entry cannot choose between them. BufferID may be a *hardware*
mechanism that the AscendC API layer still exposes through paired primitives — in which case the pairing
requirement is a software contract over a hardware feature that no longer needs it, and dropping the
pairs is wrong. It may be a separate API surface available alongside SetFlag/WaitFlag, in which case both
documents are right about their own surface. Or the regbase guidance may be carried forward from an
earlier architecture and be stale. §4 is written to distinguish them, and the honest posture until then
is: **keep the pairs**, because that is the branch with a known failure mode rather than an unknown one.

The seven-queue fact has its own consumer independent of the synchronisation question. An overlap-factor
or roofline model (0264) needs to know how many independent lanes can progress concurrently; seven
queues, including *separate* SIMD VF and SIMT VF queues, is a different machine from one where Vector is
a single lane. That SIMD and SIMT VF are separately queued is the detail most likely to be missed and is
directly relevant to mixed-mode kernels.

## 3 · Ground / Source
`npu-arch-guide.md:287-291`, the section in full — it is four lines and carries both claims:

> ### 指令序列与 BufferID 同步
>
> DAV_3510 上各执行单元拥有独立指令队列：Cube / FixPipe / MTE1 / MTE2 / MTE3 / SIMD VF / SIMT VF。
>
> **BufferID 同步机制**：消除原 set/wait 强制配对需求，简化多流水算子的同步代码。

消除…强制配对需求 — eliminates the *mandatory pairing requirement*. Note the precise wording: it does not
say set/wait is removed, it says the requirement that they be paired is. That is a narrower claim than
"BufferID replaces set/wait", which is how `npu-hardware-params.md:171` compresses it (取代) and how
`SKILL.md:62` compresses it further ("| 同步机制 | BufferID 替代 set/wait 强配对 |"). Three statements of
one change at three levels of compression, and the least compressed is the most careful.

The counter-statement, `ascendc-regbase-best-practice/references/paradigms/common/sync-and-consistency.md:66-84`
— the document a 950 implementer follows:

> **接口**：
> ```cpp
> template <HardEvent event> __aicore__ inline void SetFlag(int32_t eventID);
> template <HardEvent event> __aicore__ inline void WaitFlag(int32_t eventID);
> ```
> - `eventID`：事件 ID。通过 `GetTPipePtr()->FetchEventID(HardEvent::XXX)` 获取，不可硬编码
> - **SetFlag/WaitFlag 必须成对出现**

That file is explicitly scoped to Ascend950 ("> Ascend 950 Vector 核同步机制", `:3`) and states
`QUE_MAX_EVENT = 8` for arch 3510 at `:90` (0262). So it is not stale by its own account — it is 950
guidance asserting a pairing requirement that the architecture skill says was eliminated.

Both files are `upstream/skills-dev-main`, so this is **one origin** disagreeing with itself (RULES.md Art. 3),
which is the same shape as B2 (0259) and is why it is recorded rather than adjudicated (Art. 7). Note the
difference from B2 though: there, four passages disagree about whether a barrier is *needed*; here, an
architecture claim and an API contract may simply be about different layers. That is a more likely
reconciliation and it is still a reconciliation nobody has written down.

The provenance, `npu-hardware-params.md:171`, row 6 of the 公开资料/经验值 table — no INI field supplies
it, which is expected for an instruction-queue property.

**Independent search, installed toolkit** (phase-1 read-only exception): the four upstream-named header
roots (0245 §3) were not searched for a BufferID API during this harvest. That search is a file read, it
would settle whether the mechanism is programmer-visible at all, and it is the cheapest open item on this
entry — §4 Arm A. Recorded as not-done rather than as absent.

The seven queues also bear on `sync-and-consistency.md:38-44`, which lists **four** in-core pipes for a
Vector core — PIPE_S, PIPE_V, PIPE_MTE2, PIPE_MTE3 — and says "Vector 核内部有 4 个异步并行执行的单元".
Seven queues architecture-wide and four pipes visible to a Vector kernel are compatible (Cube, FixPipe
and MTE1 are not Vector-core pipes), but the two counts appear in two skills without the reconciliation,
and an agent building a lane model needs to know which count applies to its kernel.

## 4 · Procedure
Runnable later on `950PR`; `950DT` needs its own run and BOARD is narrowed at promotion. The two claims —
queue independence and pairing elimination — need different arms.

Arm A — is BufferID programmer-visible, file read only, no device. Search the installed toolkit for a
BufferID API:

```bash
grep -RIn -i "bufferid\|buffer_id\|BUFFER_ID" "$ASCEND_HOME_PATH/include/ascendc/"
```

`grep -R`, not `-r` — symlink farms. Nothing returned means the mechanism is not exposed and the
"simplification" is unavailable to a kernel author regardless of what the hardware does — which would
resolve §2's tension decisively in favour of keeping the pairs. Something returned tells you which
surface it belongs to.

Arm B — the pairing requirement, tested directly and carefully. Build one kernel with a genuine cross-pipe
RAW dependency (MTE2 writes UB, Vector reads it) in three variants: paired SetFlag/WaitFlag; SetFlag with
no matching WaitFlag; neither. Run each 50 times at five shapes chosen to vary pipeline occupancy
(n ∈ {64, 512, 4096, 10752, 65536}) and compare output bit-for-bit against a host reference. Upstream's
elimination claim predicts the unpaired variants are safe; the regbase contract predicts they are not.
**A declared watchdog timeout is mandatory** — a missing wait can deadlock, and an un-timed arm holds a
die on a shared machine.

Arm C — queue independence, which is the other half and is separately useful. Build a kernel issuing
independent work to several units at once — MTE2 streaming, Cube computing, Vector computing on unrelated
data — and compare total time against the sum of the units run in isolation. Concurrency shows as total
time approaching the maximum rather than the sum. Sweep which units participate, so the result is a set
of concurrent lanes rather than one number.

Arm D — the SIMD VF / SIMT VF separation, the detail §2 flags as most likely missed. Build a mixed kernel
issuing SIMD VF and SIMT VF work with no data dependency and check whether they overlap. Upstream's
seven-queue list says they are separately queued; if they serialise, the list overstates the machine for
the case where it matters most.

Device selection is explicit: the operator names the device index, the harness prints it back with
`compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared machine,
≤4 dies), and no die is substituted for another. All variants of one comparison run on one named die in
one session, with the watchdog timeout declared before the run and the die released on timeout.

## 5 · Checker — acceptance declared before the run
Three verdict variables, never aggregated.

`bufferid_is_exposed` (Arm A) — pass iff a BufferID-shaped API is found, with its header path and
declaration recorded. A negative is not a failure of the entry; it is the finding that the mechanism is
not addressable from a kernel, and it makes the pairing question moot in the safe direction.

`pairing_still_required` (Arm B) — true iff **any** of the 250 runs of either unpaired variant produces
output differing from the reference, or hits the watchdog. One hit sets it true. A clean 250 does **not**
establish that unpaired code is safe: it is reported as `violation not provoked`, because a missing
synchronisation is precisely the defect a passing run cannot refute, and declaring that now prevents a
null result being read as permission to drop the pairs.

`concurrent_lanes` (Arm C, Arm D) — the set of unit pairs whose combined time approaches the max rather
than the sum. Reported, no pass threshold; upstream states a queue count and no concurrency figure.

The positive fixture, declared before the run: Arm B's **paired** variant must produce correct output in
all 250 runs. If it does not, the harness's dependency is not what it thinks it is and every unpaired
result attributes nothing. A second fixture for Arm C: run one unit against *itself* (two dependent MTE2
streams) — the combined time must approach the sum, not the max. If it approaches the max, the timing is
not resolving serialisation and every `concurrent_lanes` entry is void. Without both, the checker reads
only "nothing went wrong", which is the known blind species.

Process exit code is not the verdict anywhere: a watchdog kill in Arm B is the informative outcome.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No kernel was compiled, no
synchronisation was omitted, and no device was contacted. **The installed headers were not searched for a
BufferID API** — that is Arm A, it is a file read, and it is the cheapest open item on this entry;
recorded here as not-done rather than as a negative result.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled or run. The entry does not establish that BufferID exists, is exposed, or eliminates
anything — Arm A is open and is the precondition for the rest. It does not establish that the pairing
requirement is gone, and it deliberately does not adjudicate between the two upstream statements: they are
one origin disagreeing with itself, Art. 7 forbids resolving that by author plausibility, and §2 records
three possible reconciliations without choosing. The safe posture stated in §2 — keep the pairs — is
reasoning about which branch has a known failure mode, not a finding. It does not establish the seven-queue
count or any concurrency between the queues (Arms C, D), nor reconcile it with the four Vector-core pipes
the regbase material names. There is **no second origin**: upstream marks BufferID 公开资料/经验值 (0206
row 6), no ini field expresses instruction queues, and the installed headers were not consulted. It says
nothing about `SetFlag`/`WaitFlag` semantics, the four Vector HardEvent types, or the eventID pool model —
those are 0262, which documents the mechanism this entry says may have been superseded, and the two must
be read together. It says nothing about `PipeBarrier`, which is same-pipe ordering and is B2's subject
(0259). Nothing transfers to the other book (RULES.md Art. 1): that set/wait pairing was mandatory on the
earlier architecture is upstream's framing and is carried as quotation.
