```
ID:        0226-dav-3510-deletes-the-l1-to-gm-and-gm-to-l0-paths-so-kernels-relying-on-them-must-be-rerouted
LABEL:     boundary
LEVEL:     L3 (data movement & layout)
STRATUM:   harvested — one upstream origin, which marks the deletion as a public-or-experience
           value with no ini field (0206 row 5). Nothing was compiled; how the loss manifests is
           unknown.
BOARD:     950PR, 950DT
SOURCE:    ops/npu-arch/references/npu-arch-guide.md:285 — "> 注：DAV_3510 上 L1→GM 和 GM→L0A/L0B 的
           数据通路已被删除，依赖这些路径的 kernel 需要改造为替代路径（如 L1→UB→GM、GM→L1→L0A/L0B）。
           [¹](#unverified)"
SOURCE:    ops/npu-arch/references/npu-hardware-params.md:170 — "| 5 | L1→GM 和 GM→L0A/L0B 通路已删除 |
           Guide §4 关键数据通路改动 | 公开资料 / 经验值 |"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a `DataCopy` from L1 to GM, or from GM directly to L0A/L0B, that compiles and delivers
           correct data on a 950 board — the path would then not be deleted.
```

# 0226 · DAV_3510 deletes the L1→GM and GM→L0A/L0B paths, so kernels relying on them must be rerouted

## 1 · Claim
Upstream asserts that two data paths present on the previous architecture have been **removed** on
DAV_3510: L1 → GM, and GM → L0A/L0B. Upstream asserts that kernels depending on them must be rewritten to
use substitute routes, and names them: `L1→UB→GM` for the first and `GM→L1→L0A/L0B` for the second.
Upstream marks the deletion as a public-or-experience value with no corresponding INI field. Not
established here: nothing was compiled, so whether the loss appears as a build error, a runtime fault, or
a silent fallback is unknown.

This is the deletion travelling with the additions of 0225 — the same architecture change adds three CV
paths and removes two GM paths. The additions are opt-in; this is not.

## 2 · The wrong branch this removes
A removal is the hardest kind of delta to act on, because nothing in the new material mentions the
missing thing. An agent porting a Cube kernel reads about L0C→UB and UB→L1 (0225), finds them irrelevant
to its data flow, and ports the kernel unchanged. Whether that works depends entirely on the failure
mode, and upstream states none.

Three possibilities, and they are not close in cost. A build error naming the path is harmless — the port
fails loudly and gets fixed. A runtime fault is nearly as good. But if the toolchain silently substitutes
the two-hop route, the port succeeds, results are correct, and the kernel now performs an extra buffer
traversal per copy that its author never wrote and cannot see. `GM→L1→L0A` moves the operand twice
instead of once; on a Cube kernel whose operands stream, that is a doubling of MTE traffic on the
critical path, showing up as an MTE-bound profile with no visible cause.

The substitution is not free even when deliberate, and the second-order cost is the one that gets missed:
the substitute routes consume intermediate buffers that were not previously in the data flow.
`L1→UB→GM` occupies UB, which on a Cube-heavy kernel may have been budgeted entirely to Vector work;
`GM→L1→L0A/L0B` occupies L1, which is 512 KB (0212) and is already the residency budget for the operand
tiles themselves. So rerouting can force a re-tiling, and an agent that treats it as a mechanical path
substitution will overflow a buffer it never accounted for.

The third branch is scope. `GM→L0A/L0B` being gone means the operand *must* pass through L1, so L1 is no
longer optional for Cube operands on this architecture. Any tiling strategy that assumed a direct GM
feed for a large operand no longer has one.

## 3 · Ground / Source
`npu-arch-guide.md:275-285`, the deletion in its actual position — as a trailing note to the section
announcing the three additions:

> ### DAV_3510 相比 DAV_2201 的关键数据通路改动
>
> DAV_3510 新增三条通路，使 Cube 与 Vector 可直接交换数据，避免 GM workspace 中转：
>
> 1. **L0C → UBuffer**：Cube 结果直达 Vector，FixPipe 输出到 UB
> 2. **UBuffer ↔ L1**：Vector 与 Cube 双向直连（UB→L1 为新增方向），避免 GM 中转
> 3. **SSBuffer 消息通路**：CV 间细粒度同步信号
>
> **典型受益场景**：FA / FIA 类融合算子可彻底消除 workspace A/B/C 的 GM 读写。
>
> > 注：DAV_3510 上 L1→GM 和 GM→L0A/L0B 的数据通路已被删除，依赖这些路径的 kernel 需要改造为替代路径
> > （如 L1→UB→GM、GM→L1→L0A/L0B）。 [¹](#unverified)

The placement is the finding as much as the content. The section is headed 关键数据通路改动 — key data
path *changes* — and its body is three numbered additions with a benefit statement. The deletion is a
blockquoted note after the benefit, unnumbered, in a smaller structural position than any of the
additions. A reader scanning for what changed gets three bullets and a payoff; the thing that breaks
existing code is the fourth item and is not on the list.

That is why this is filed separately from 0225 rather than as a paragraph inside it: additions and
deletions have opposite consequences for a port, and a single entry covering both would present them
with equal weight, which is exactly the defect in the source.

The MTE engine table two subsections earlier, `:265-273`, is where the deletion should be visible and is
not:

> | 引擎 | 路径 |
> |-----|------|
> | MTE1 | L1 ↔ L0A/B/C, L1 ↔ UB |
> | MTE2 | GM → L1 / UB |
> | MTE3 | UB → GM / L1 |

Read carefully, this table is already consistent with the deletion — MTE2 lists `GM → L1 / UB` and not
GM→L0A/L0B, and MTE3 lists `UB → GM / L1` and not L1→GM. So the engine table describes the post-deletion
state without remarking on it. An agent reading only the table would derive the correct routes and never
know a change occurred; an agent porting from a kernel that used the old paths would not be warned. Both
halves of the source are right and neither transmits the delta.

The provenance, `npu-hardware-params.md:170`, row 5 of the 公开资料/经验值 table: no INI field supplies
it. That is expected — a *deleted* path is exactly the kind of fact a configuration file has no way to
express, since ini fields enumerate capacities and rates rather than absences. So unlike the capacity
figures (0209-0213), there is no ini route to corroboration even in principle, and §4 is the only path.

A search of the installed CANN 9.0.0-beta.2 950 ini set found no field naming any GM↔L0 or L1→GM path,
consistent with the above and establishing nothing.

## 4 · Procedure
Runnable later on `950PR`; `950DT` needs its own run and BOARD is narrowed at promotion. The claim is a
negative — a capability is absent — so the procedure must attempt the capability, and the compile arm is
the cheap decisive one.

Arm A — attempt both deleted paths, compile first. Write two kernels: one performing a `DataCopy` from an
L1-resident tensor directly to GM, one from GM directly into L0A (and separately L0B). Compile each for a
3510 target. Record exactly one of three outcomes per path: the API/`QuePosition` combination does not
exist (a compile error naming the symbol); it exists and the build fails with a diagnostic naming the
path; or it exists and builds clean. The third is the one that matters and is why this arm is not
skippable.

Arm B — the behaviour arm, run only for paths reaching outcome three. Execute and compare against a host
reference. Correct data means the toolchain substituted the two-hop route silently — §2's undetectable
branch — and confirming that is the finding. Wrong data or a fault is a different and louder result.

Arm C — the substitution cost, which is what makes this actionable. For each deleted path, build the
substitute route explicitly (`L1→UB→GM`, `GM→L1→L0A`) and measure bytes moved and Task Duration against a
single-hop copy of the same logical extent on an architecture-appropriate comparison — here, against the
*other* direction that still exists (GM→L1 for the second case). The doubling §2 predicts is a
measurement, not an inference, and this arm makes it one.

Arm D — the buffer-occupancy consequence, which no other arm reaches. Run a Cube kernel at a tiling that
fills L1 with operand tiles (0212), then add the `GM→L1→L0A` substitute route's staging requirement, and
record whether the tiling still fits. §2's claim that rerouting can force a re-tiling is arithmetic over
buffer capacities; this arm shows whether it bites in practice.

Device selection is explicit: the operator names the device index, the harness prints it back with
`compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared machine,
≤4 dies), and no die is substituted for another. Arm C's paired builds run on one named die in one
session or the comparison attributes nothing.

## 5 · Checker — acceptance declared before the run
Verdict variable `path_deleted[p]`, one per path, two of them, never aggregated — the two deletions are
independent claims and one holding must not cover the other.

Per path, `path_deleted` is true iff Arm A reaches outcome one or two — the construct does not exist, or
the build is refused with a diagnostic naming the path. The checker matches diagnostic text, not exit
status: "it did not compile" and "it did not compile for the stated reason" are different results, and
only the second establishes a deletion rather than a typo.

Outcome three with Arm B producing **correct** data is recorded as `deleted-but-substituted`, not as
false. That is a distinct verdict declared now, because it is the branch with no detector and it is the
one the delivered skill must warn about: the path is gone, the toolchain hides it, and the cost is invisible.
Outcome three with wrong data overturns nothing about the deletion but is reported first, since a
silently wrong copy is worse than either.

`substitution_cost` (Arm C) — bytes moved and duration for the substitute route against the single-hop
baseline. Reported with run variance, no pass threshold; the predicted doubling is what is being
measured, not asserted.

The positive fixture, declared before the run: Arm A must include a control that copies along a path
upstream says **does** exist — `GM → L1` — which must compile and deliver correct data in the same
session. If the control also fails, the harness cannot express a `DataCopy` at all and every refusal it
reported is an artefact rather than evidence of deletion. Without this the checker reads only "some
builds failed", which is the known blind species.

Process exit code is not the verdict anywhere: for the two deleted paths a non-zero exit is the expected
outcome.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No kernel was compiled, no copy
was attempted, and no device was contacted. The ini search noted in §3 found nothing; a configuration
file cannot express a deleted path even in principle, so that negative carries no weight and is recorded
only for completeness.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled or run. The entry does not establish that either path is deleted, and — more
importantly for a porting agent — it does not establish **how the loss manifests**: build error, runtime
fault, or silent substitution. That is Arm A/B and it is the single most useful thing here, because the
silent branch has no detector and §2's whole argument turns on it. There is **no second origin** and
none is possible from configuration data: upstream marks the deletion 公开资料/经验值 (0206 row 5), and
an ini enumerates what exists rather than what does not. It does not establish that the substitute routes
upstream names work, or what they cost — Arm C is open and the predicted doubling is arithmetic over hop
counts, not a measurement. It does not establish the buffer-occupancy consequence in §2 (Arm D), which is
likewise arithmetic over 0212's L1 capacity. It says nothing about which upstream kernels actually used
the deleted paths; no survey was performed, so the porting exposure is unquantified. It says nothing
about the three *added* paths, which are 0225 — they are separated deliberately because a port must act
on this entry and may ignore that one. Nothing transfers to the other book (RULES.md Art. 1): that these paths
existed on DAV_2201 is upstream's framing, carried as quotation, and this book claims only the DAV_3510
state.
