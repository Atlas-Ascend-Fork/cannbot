```
ID:        0261-overlapping-mte-destination-addresses-need-a-manual-pipebarrier-because-hardware-does-not-serialise-them
LABEL:     trap
LEVEL:     L4 (synchronisation)
STRATUM:   harvested — two upstream skills state it, both `upstream/skills-dev-main`, therefore ONE
           origin (RULES.md Art. 3). Nothing was compiled and no overlap was observed.
BOARD:     family-claimed(unverified)
           # the regbase sync material scopes itself to "Ascend 950 Vector 核" and arch35 without
           # naming a board token this book recognises; no board was contacted.
SOURCE:    ops/ascendc-regbase-best-practice/references/paradigms/common/sync-and-consistency.md:245
           — "- **MTE2/MTE3 搬运地址重叠时需手动插入**：硬件不保证搬运地址重叠时的串行化，需手动
           `PipeBarrier<PIPE_MTE2>()`（UB 目的地址重叠）或 `PipeBarrier<PIPE_MTE3>()`（GM 目的地址重叠）"
SOURCE:    ops/ascendc-sync-check/references/sync-mechanism.md:149-151 — "### 4.3 地址重叠场景 /
           - 目的 GM 地址重叠：两条 DataCopy 间需 `PipeBarrier<PIPE_MTE3>()`。/ - 目的 UB 地址重叠：
           两条 DataCopy 间需 `PipeBarrier<PIPE_MTE2>()`。"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  two `DataCopy` calls with overlapping destination addresses, no intervening
           `PipeBarrier`, producing the sequentially-correct result across 50 runs at five shapes on
           a 950 board — the hardware would then serialise them and the rule is unnecessary.
```

# 0261 · Overlapping MTE destination addresses need a manual `PipeBarrier` because hardware does not serialise them

## 1 · Claim
Upstream asserts that the hardware does **not** guarantee serialisation between two data movements whose
destination addresses overlap, and that the developer must insert the barrier manually: a
`PipeBarrier<PIPE_MTE2>()` when the overlapping destination is in UB, and a `PipeBarrier<PIPE_MTE3>()`
when it is in GM. Upstream states this as an exception carved out of the same list that says arch35
hardware guarantees ordering between consecutive Vector computations and consecutive VFs. Not established
here: nothing was compiled and no overlapping copy was issued.

This is the **positive** requirement inside the B2 material (0259). Where the `PIPE_V` question is a
four-way disagreement about whether a barrier is needed after a VF, this bullet — in the same constraint
list, two lines below — states unambiguously where one *is* needed, and no upstream source contradicts it.

## 2 · The wrong branch this removes
The wrong branch arrives by generalising the good news. An agent that reads
`sync-and-consistency.md:243` — arch35 guarantees ordering between consecutive Vector computations and
VFs, so no manual `PipeBarrier<PIPE_V>` — concludes that the architecture handles same-pipe ordering and
stops inserting barriers. The very next bullet says that for MTE with overlapping destinations it does
not. Two lines apart, opposite conclusions, and the first is the memorable one because it removes work.

The failure it produces is a data race between two DMA engines writing the same bytes. Two `DataCopy`
calls whose destinations overlap can land in either order, or interleave, so the overlapping region ends
up holding a mixture. Nothing faults — both copies are legal, both addresses are mapped — and the result
is non-deterministic across runs, shapes and occupancies. That is the failure class the regbase pitfall
material names as masquerading as precision drift (`common_traps.md` §8: "identical input produces
different mismatches … synchronization or branch-selection problems"). An author will look for a numerical
bug.

The overlap is often not visible at the call site, which is the second half of the trap. Two copies with
different base pointers, different offsets and different lengths overlap or not depending on arithmetic
the author has to do deliberately. A tail copy that writes back into the region a main-loop copy already
covered, a scatter with duplicate targets, a padded write that extends into the next tile's territory —
all are overlaps that look like two unrelated copies in the source.

The pipe selection is the third trap and it is easy to get backwards. The barrier goes on the pipe that
**writes** the overlapping destination: UB destinations are written by MTE2 (GM→UB), so
`PipeBarrier<PIPE_MTE2>`; GM destinations are written by MTE3 (UB→GM), so `PipeBarrier<PIPE_MTE3>`. An
agent reasoning "the second copy reads from UB, so barrier the reader" picks the wrong pipe, and a
`PipeBarrier` on the wrong pipe compiles, costs a drain, and does not order the thing that needed
ordering — the worst combination: a cost with no protection, and a barrier visible in the source that
makes a reviewer believe the case is handled.

## 3 · Ground / Source
`sync-and-consistency.md:241-256`, the constraint block with its worked example — quoted whole because
the adjacency to the "no barrier needed" bullet is the finding:

> **约束**：
> - arch35/Ascend 950 上连续 Vector 计算之间、连续 VF 之间硬件保证顺序，无需手动 PipeBarrier<PIPE_V>()
> - `PipeBarrier<PIPE_ALL>()` 会等待所有流水线完成，对性能影响大，能用单流水 PipeBarrier 解决时不要用 PIPE_ALL
> - **MTE2/MTE3 搬运地址重叠时需手动插入**：硬件不保证搬运地址重叠时的串行化，需手动
>   `PipeBarrier<PIPE_MTE2>()`（UB 目的地址重叠）或 `PipeBarrier<PIPE_MTE3>()`（GM 目的地址重叠）
>
> **示例**：
>
> ```cpp
> // MTE3 搬运目的地址重叠，需手动插入
> DataCopy(dstGm[0], srcLocal, count);
> PipeBarrier<PIPE_MTE3>();              // 保证前一个 DataCopy 完成
> DataCopy(dstGm[overlap], srcLocal2, count);  // 目的地址与前一个重叠
> ```

硬件不保证…串行化 — the hardware does not guarantee serialisation. That is a statement about the machine,
not a coding convention, which is what makes it a boundary rather than advice. The worked example is four
lines and shows the GM case; the UB case is stated and not shown.

The second skill states the same rule independently of the arch35 discussion,
`ascendc-sync-check/references/sync-mechanism.md:145-151`:

> `PipeBarrier<PIPE_MTE2>` 只同步 MTE2 内部，**不能**解决 MTE2→V 跨流水依赖；后者需 SetFlag/WaitFlag 或
> TQue 自动同步。同理 `PipeBarrier<PIPE_V>` 不能解决 V→S。
>
> ### 4.3 地址重叠场景
>
> - 目的 GM 地址重叠：两条 DataCopy 间需 `PipeBarrier<PIPE_MTE3>()`。
> - 目的 UB 地址重叠：两条 DataCopy 间需 `PipeBarrier<PIPE_MTE2>()`。

The sentence above the section is the reason the pipe choice matters and is worth carrying: a
`PipeBarrier` orders **within one pipe only**. It cannot express a cross-pipe dependency — that needs
`SetFlag`/`WaitFlag` (0262) or a `TQue`. So the three synchronisation mechanisms are not alternatives:
`PipeBarrier` for same-pipe, `SetFlag`/`WaitFlag` for cross-pipe, `LocalMemBar` for inside a VF (0258).
Three scopes, three primitives, and using one where another belongs is silent.

That same-pipe-only property is what makes §2's wrong-pipe branch harmful rather than merely useless: a
`PipeBarrier<PIPE_MTE3>` placed where MTE2 overlap needed ordering orders MTE3 against itself, which is
a real constraint the compiler will honour and which has nothing to do with the race.

Both files are `upstream/skills-dev-main` — **one origin** (RULES.md Art. 3). They agree exactly, including the
pipe assignment, which is worth noting because the two skills disagree sharply about `PIPE_V` (0259).
Where B2 has four passages and three positions, this rule has two passages and one position.

The whitelist places `PipeBarrier` in the **kernel-side** family (`VF Function? = No`,
`regbase_api_whitelist.md:72`), so it is not callable from inside a VF (0250) — the overlap this entry
covers is between `DataCopy` calls in the kernel shell, not inside VF bodies.

Upstream supplies no cost figure for the barrier and no statement of what the race produces — torn data,
last-writer-wins, or something else.

## 4 · Procedure
Runnable later on `950PR`. The claim is that a race exists without the barrier, so the procedure must
provoke it rather than confirm its absence.

Base kernel: two `DataCopy` calls whose destination ranges overlap by a controllable amount, with
distinguishable source data (all-ones and all-twos, so the overlapping region's content identifies which
copy landed last, and a mixture identifies interleaving). Two builds differing **only** in the presence of
the barrier, controlled by one preprocessor symbol; build md5s recorded and confirmed to differ, or the
run is void.

Arm A — the GM case (`PIPE_MTE3`). Run both builds 50 times at each of five overlap sizes and five total
sizes chosen to vary MTE occupancy, and classify the overlapping region per run: all-ones, all-twos, or
mixed. The barriered build must be all-twos every time; the unbarriered build showing anything else, even
once, establishes the race.

Arm B — the UB case (`PIPE_MTE2`), which upstream states and never demonstrates. Same protocol with two
GM→UB copies overlapping in UB. This arm covers the half of the rule that has no worked example anywhere
in the source.

Arm C — the wrong-pipe arm, which prices §2's third branch. Build the GM-overlap case with
`PipeBarrier<PIPE_MTE2>()` — the wrong pipe — and run the same protocol. Expected: it races exactly like
the unbarriered build while costing a drain. Confirming that a visible barrier provides no protection is
the finding a reviewer most needs, because the source *looks* correct.

Arm D — the cost. On the barriered builds, collect `aiv_time` against the unbarriered ones at each shape,
minimum over 50 repetitions. This prices the rule, which upstream does not, and it bounds how much a
conservative "barrier every copy" policy would cost.

Device selection is explicit: the operator names the device index, the harness prints it back with
`compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared machine,
≤4 dies), and no die is substituted for another. Both builds of one comparison run on one named die in one
session — a race whose two arms ran on different dies attributes nothing.

## 5 · Checker — acceptance declared before the run
Verdict variable `race_observed[pipe]`, one for GM/MTE3 and one for UB/MTE2, never merged — upstream
states two rules and the UB one has no worked example, so it is the likelier of the two to be wrong.

Per pipe, `race_observed` is true iff **any** of the 250 unbarriered runs produces a result other than the
sequentially-correct one. One run out of 250 sets it true; a race is not a majority phenomenon.

Pass is declared now as `race_observed` true for both pipes, with the barriered build correct in all 250.
A clean unbarriered result does **not** establish that the barrier is unnecessary: it is reported as
`race not provoked`, because a data race is precisely the thing a passing run cannot refute, and declaring
that now prevents a null result being read as permission to drop the barrier.

`wrong_pipe_protects` (Arm C) — pass iff the wrong-pipe build races like the unbarriered one. If the
wrong-pipe build is *clean*, then either pipe's barrier suffices and the pipe-selection rule is
unnecessary — a real finding, and a surprising one, so it is named in advance.

`barrier_cost` (Arm D) — Δ`aiv_time` with run variance. Reported, no threshold; a Δ below variance is
reported as "below variance", never as zero.

The positive fixture, declared before the run: a variant with the overlap set to **zero** — two copies to
disjoint destinations. Its unbarriered build must be correct in all 250 runs. If it races, the harness's
copies are interfering through something other than destination overlap and every `race_observed` verdict
is void. A second fixture: the barriered build with the overlap at maximum must be correct in all 250; if
it is not, the barrier does not order even when correctly placed, and the entire rule is void rather than
confirmed. Without both, the checker reads only "the unbarriered build was sometimes wrong", which is the
known blind species — many things make a DMA-heavy kernel intermittently wrong.

Process exit code is not the verdict for any arm.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No kernel was compiled, no
overlapping copy was issued, and no device was contacted. Upstream supplies no cost figure and no
description of what the race produces, so there is not even an upstream observation to record as upstream
text.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled or run. The entry does not establish that the race occurs, what it produces (torn
data, last-writer-wins, or interleaving), or that the barrier prevents it — Arms A-C are all open, and
§5 declares in advance that a clean unbarriered run cannot refute a race. There is **no second origin**:
both quoted files are one repo, and no installed header was read for `PipeBarrier`'s declaration or the
`pipe_t` enumeration. It does not establish the **UB half** of the rule with any worked example — upstream
demonstrates only the GM case, and Arm B exists because the two halves have unequal support. It does not
establish that the pipe selection matters (Arm C); §2's argument that a wrong-pipe barrier is worse than
none is reasoning from `PipeBarrier`'s same-pipe-only property, not an observation. It does not price the
rule, so the cost of a conservative barrier-everything policy is unknown. It says nothing about
**cross-pipe** dependencies, which `PipeBarrier` cannot express at all and which need `SetFlag`/`WaitFlag`
or a `TQue` (0262), nor about ordering inside a VF, which is `LocalMemBar` (0258) — three primitives, three
scopes, and this entry covers only same-pipe MTE ordering. It says nothing about the `PIPE_V` question,
which is the open four-way disagreement of 0259 and sits two bullets above this rule in the same source.
BOARD is `family-claimed(unverified)`: the sync material scopes itself to "Ascend 950 Vector 核" and
arch35 without naming a board token this book recognises, and none was contacted.
