```
ID:        0225-dav-3510-adds-l0c-to-ub-and-ub-to-l1-direct-paths-so-cv-fusion-need-not-round-trip-gm
LABEL:     knowledge
LEVEL:     L3 (data movement & layout)
STRATUM:   harvested — one upstream origin, which marks the CV direct paths as a public-or-experience
           value with no ini field (0206 row 4). Nothing was compiled and no copy was issued.
BOARD:     950PR, 950DT
SOURCE:    ops/npu-arch/references/npu-arch-guide.md:275-285 — "### DAV_3510 相比 DAV_2201 的关键数据
           通路改动 / DAV_3510 新增三条通路，使 Cube 与 Vector 可直接交换数据，避免 GM workspace 中转：
           / 1. **L0C → UBuffer**：Cube 结果直达 Vector，FixPipe 输出到 UB / 2. **UBuffer ↔ L1**：
           Vector 与 Cube 双向直连（UB→L1 为新增方向），避免 GM 中转 / 3. **SSBuffer 消息通路**：
           CV 间细粒度同步信号 / **典型受益场景**：FA / FIA 类融合算子可彻底消除 workspace A/B/C 的
           GM 读写。"
SOURCE:    ops/npu-arch/references/npu-hardware-params.md:169 — "| 4 | CV 直通通路：L0C→UB、UB→L1、
           SSBuffer 消息 | Guide §4 关键数据通路改动 / SKILL.md §DAV_3510 关键变化 | 公开资料 / 经验值 |"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a DataCopy from L0C to UB, or from UB to L1, that fails to compile or faults on a 950
           board — the path would then not exist; or a fused operator using the direct path showing
           no reduction in GM traffic against a workspace-mediated version at the same shape.
```

# 0225 · DAV_3510 adds L0C→UB and UB→L1 direct paths, so CV fusion need not round-trip GM

## 1 · Claim
Upstream asserts that DAV_3510 adds three data paths that let the Cube and Vector units exchange data
without staging through Global Memory: **L0C → UBuffer**, so a Cube result reaches Vector directly via
FixPipe output to UB; **UBuffer ↔ L1** bidirectionally, with UB→L1 being the new direction; and an
**SSBuffer message channel** carrying fine-grained CV synchronisation signals. Upstream names the
benefiting workload class — FA / FIA-style fused operators, which can eliminate the GM reads and writes
of workspaces A, B and C entirely. Upstream marks all three paths as public-or-experience values with no
ini field behind them. Not established here: nothing was compiled and no copy was issued.

## 2 · The wrong branch this removes
A fused Cube+Vector operator written without this knowledge stages every Cube result through a GM
workspace: FixPipe writes L0C→GM, then MTE2 reads GM→UB, then Vector computes. That is two full GM
traversals of the intermediate per stage, on a tensor that never needed to leave the core.

The failure is not a defect. The workspace-mediated kernel is correct, it is the shape every earlier
architecture required, and it is what any ported kernel already does. Its cost shows up as MTE2 and MTE3
occupancy — which is indistinguishable in a profile from an operator that genuinely needs that traffic.
An agent looking at an MTE2-bound fused operator will reach for tiling, double buffering or L2 hints,
and none of those removes a traversal the architecture no longer requires.

The scale is the reason this matters more than most path facts. For an FA-shaped operator upstream
claims the elimination is total — workspaces A, B and C, all of them — so the saving is not a percentage
of the intermediate traffic, it is the intermediate traffic. And that traffic is often the majority of
the operator's GM bytes, which means the roofline's memory term (0264, 0270) is computed for a data flow
the hardware does not require.

The inverse branch: an agent that assumes the direct paths make workspaces unnecessary *in general*.
They are per-core paths between per-core buffers. L0C is 256 KB and UB is 248 KB (0209, 0211), so
whatever crosses the direct path must fit in those, and a fusion whose intermediate exceeds them still
needs GM. Upstream states the paths and never states the capacity condition; the condition follows from
the buffer sizes and is arithmetic, not measurement.

A third branch, which is about which path: `UBuffer ↔ L1` is stated as bidirectional with UB→L1 as *the
new direction*. So L1→UB already existed and only the reverse is new. An agent reading "UB↔L1 is new"
will not know which half it may rely on when reasoning about an earlier architecture, and this book must
not carry that half anyway (RULES.md Art. 1).

## 3 · Ground / Source
`npu-arch-guide.md:275-285`, the section in full:

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

The note at the end is a *deletion* travelling with the additions, and it is carried as 0226 — the same
change removed two paths, and a kernel that used them must be rewritten. Additions are opt-in; deletions
are not, which is why they are separated.

The MTE engine table, `:265-273`, gives the paths that carry the traffic:

> | 引擎 | 路径 |
> |-----|------|
> | MTE1 | L1 ↔ L0A/B/C, L1 ↔ UB |
> | MTE2 | GM → L1 / UB |
> | MTE3 | UB → GM / L1 |

Read against the three additions: MTE1 already lists `L1 ↔ UB` and MTE3 lists `UB → GM / L1`. So the
UB→L1 direction appears in *two* engine rows, and which engine actually carries it is not stated. That
matters for pipeline modelling — an intermediate crossing UB→L1 occupies MTE1 or MTE3, and those are
different lanes in an overlap-factor calculation (0264). Nothing here resolves it.

The Buffer table, `:251-263`, states the programming consequence of the third path:

> | **SSBuffer** | **DAV_3510 新增**：CV 间消息通路 | 替代 GM workspace 的细粒度同步 |

替代 GM workspace 的细粒度同步 — SSBuffer replaces GM-workspace-mediated fine-grained synchronisation,
which is a different thing from replacing the data movement. Paths 1 and 2 move data; path 3 moves
signals. Conflating them would suggest SSBuffer is a data buffer, and 0227 carries it separately for that
reason.

`SKILL.md:57-64` restates the change at headline level: "| CV 直通通路 | 新增 L0C→UB、UB→L1、SSBuffer
消息 |" alongside "| 同步机制 | BufferID 替代 set/wait 强配对 |" (0228).

The provenance, `npu-hardware-params.md:169`, row 4 of the 公开资料/经验值 table: no INI field supplies
any of this, and upstream says so. A search of the installed CANN 9.0.0-beta.2 950 ini set found no field
naming a CV path — consistent with upstream, establishing nothing. What the ini *does* carry is
`l0_c_to_ub_rate=128` and `ub_to_l1_rate=128` in `[AICoreMemoryRates]`
(`Ascend950PR_9589.ini`) — two rate fields named for exactly the two new paths. That is suggestive and is
deliberately **not** claimed as corroboration: the fields carry no unit (0224), the same block lists
rates for paths on architectures that do not have them, and a rate field's presence is not evidence a
path exists. It is recorded because §4 Arm A should check whether those fields are non-zero on parts
where the path is absent.

## 4 · Procedure
Runnable later on `950PR`; `950DT` needs its own run and BOARD is narrowed at promotion.

Arm A — existence, compile and run. Write a kernel performing a `DataCopy` from an L0C-resident tensor to
a UB destination, and a second from UB to L1, and check both compile for a 3510 target and produce
correct data. Record the diagnostic if either fails. This establishes the path exists; it establishes
nothing about benefit. Alongside, read `l0_c_to_ub_rate` and `ub_to_l1_rate` from the resolved ini and
record them — §3 flags them as suggestive and unclaimed, and this is where they get checked.

Arm B — the engine attribution, which §3 identifies as unresolved and which pipeline modelling needs.
Run Arm A's UB→L1 copy under msprof and record which pipe lane it occupies — MTE1 or MTE3. A path whose
engine is unknown cannot be placed in an overlap-factor calculation.

Arm C — the benefit, paired. Implement one fused Cube+Vector operator two ways at identical shape, same
die, same session: once with the intermediate staged through a GM workspace, once through the direct
L0C→UB path. Record GM bytes read and written (from msprof) and Task Duration for both. The GM-byte
delta is the attributable measurement; the duration is what a team will quote. Both are reported, and the
byte count is the verdict — a duration difference alone could come from anywhere.

Arm D — the capacity condition §2 names and upstream omits. Sweep the intermediate size across the L0C
and UB capacities (0209, 0211) and locate where the direct path stops being usable and a workspace
becomes necessary. That threshold is what a fusion decision actually turns on and no source in this scope
states it.

Device selection is explicit: the operator names the device index, the harness prints it back with
`compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared machine,
≤4 dies), and no die is substituted for another. Arm C's two builds run on one named die in one session
or the comparison attributes nothing.

## 5 · Checker — acceptance declared before the run
Three verdict variables, never aggregated — existence, attribution and benefit are three claims and one
passing must not carry another.

`path_exists[l0c_to_ub]` and `path_exists[ub_to_l1]` (Arm A) — pass iff the copy compiles, runs, and the
destination matches a host reference bit-for-bit. Correctness is required, not just completion: a copy
that runs and delivers wrong data is a worse outcome than one that fails to build, and a checker testing
only for a successful launch would not distinguish them.

`gm_bytes_saved` (Arm C) — the difference in GM bytes between the workspace and direct builds. Pass iff
strictly positive **and** approximately equal to twice the intermediate size (one write plus one read
eliminated). The second clause is what makes this attributable: a positive delta of the wrong magnitude
means something else changed between the builds, and the entry's claim is specifically that a round trip
is removed.

`duration_delta` (Arm C) — reported with run variance, **no pass threshold**. A saving in GM bytes need
not produce a saving in time if the operator was not memory-bound at that shape, and declaring no
threshold now prevents a null timing result being read as a failure of the path.

`capacity_threshold` (Arm D) — the intermediate size at which the direct path stops being usable.
Reported; it is the number a fusion decision needs and no source supplies it.

The positive fixture, declared before the run: Arm C must include a third build in which the *same*
direct-path kernel is run with the intermediate deliberately oversized past Arm D's threshold, forcing a
workspace. Its GM byte count must match the workspace build's. If it does not, the byte counter is not
measuring what the model thinks it is, and every `gm_bytes_saved` figure is void. Without this the
checker reads only "one build moved fewer bytes", which is the known blind species — a build that moved
fewer bytes because it did less work looks identical.

Process exit code is not the verdict for any arm.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No kernel was compiled, no copy
was issued, and no GM byte was counted. The `l0_c_to_ub_rate` and `ub_to_l1_rate` fields noted in §3 are
a file read under the sanctioned phase-1 read-only exception, carry no declared unit, and are explicitly
not claimed as corroboration — a rate field's presence is not evidence that a path exists.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled or run. The entry does not establish that either path exists, which engine carries
it, or that any GM traffic is saved — Arms A-C are all open. There is **no second origin**: upstream
marks the CV paths as public-or-experience values with no ini field (0206 row 4), and the two suggestively
named rate fields are deliberately not treated as one. It does not establish the FA/FIA benefit upstream
names: 彻底消除 workspace A/B/C is upstream's claim about a workload class, and this entry supplies no
operator and no measurement for it. It does not state the **capacity condition** under which the paths
are usable — that follows from L0C being 256 KB and UB 248 KB and is arithmetic, not measurement, and
Arm D is what would locate it. It says nothing about SSBuffer beyond distinguishing it as a *signal*
path rather than a data path; that is 0227. It says nothing about the paths this same change **deleted**
— L1→GM and GM→L0A/L0B — which is 0226 and is the half that breaks existing kernels rather than
enabling new ones. It says nothing about synchronisation between the two units across a direct path;
BufferID (0228) and the SSBuffer messages are the mechanisms and neither is established here. Nothing
transfers to the other book (RULES.md Art. 1) — the entire section is framed by upstream as a delta from
DAV_2201, and this book claims only the DAV_3510 state.
