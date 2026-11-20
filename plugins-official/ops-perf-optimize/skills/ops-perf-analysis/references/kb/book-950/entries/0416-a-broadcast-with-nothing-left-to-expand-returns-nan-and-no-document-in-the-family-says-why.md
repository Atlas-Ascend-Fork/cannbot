```
ID:        0416-a-broadcast-with-nothing-left-to-expand-returns-nan-and-no-document-in-the-family-says-why
LABEL:     trap
LEVEL:     L5 (compute & numerics)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured by us
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/broadcast/broadcast_design.md:95 —
           "2. **`brcInTile` 但无可展开维（切分轴广播且 `ubFormer==1`）且 `rank≤5` → ① NDDMA**：此时
           UB Broadcast 会 `dShape==sShape` 空广播出 nan；NDDMA 在 `ubFormer==1` 下搬 inner 连续数据、
           外层靠 offset 广播仍正确。" ; :3 — "选错直接慢甚至 nan，选对才快"
SOURCE:    same family, ub_broadcast_design.md:11 — "**前提：tile 内要有 UB Broadcast 能展开的维
           （`dShape>sShape`）。** 两种会出 nan 的反例（cann-bench Maximum case 18 实测）：" ;
           :63 — "**退化守卫**：`UbBroadcast` 内先检查是否存在 `dShape>sShape` 的维；若无（如尾块
           `rows==1` 或选型漏判），直接 `DataCopy(dst,src,对齐cnt)` 做 dtype 无关的 UB→UB 拷贝
           （不用 `Adds`，避免 int64 等不支持），而非调 `Broadcast`，防空广播出 nan。"
SOURCE:    same family, code/broadcast_common.h:252,255 — "// Broadcast 会变成 src==dst 的空广播并产生
           nan。此时直接拷贝 src→dst（src 已是该 tile 正确数据）。" ·
           "if (!anyExpand) {                              // 无可展开维：直接 UB→UB 拷贝（dtype 无关，避免空广播 nan）"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a `Broadcast<T,R>` call on a named 950 board with `dstShape == srcShape` on every axis whose
           output matches its input elementwise — the degenerate call would then be a no-op rather than
           a NaN source, upstream's two host gates and its kernel guard would all be unnecessary, and
           the family's headline correctness claim would be wrong.
```

# 0416 · A broadcast with nothing left to expand returns NaN, and no document in the family says why

## 1 · Claim
Upstream asserts that choosing the wrong broadcast implementation is not merely slow but can produce
NaN — `选错直接慢甚至 nan，选对才快` — and asserts one specific mechanism for it, in six places across
three files of one directory: calling the UB-side `Broadcast` when the tile contains no axis to expand,
so that `dstShape == srcShape` on every axis, is an "empty broadcast" (`空广播`) that emits NaN.
Upstream asserts two host-side gates that must prevent this — a broadcast axis strictly outside the
tile routes to the DataCopyPad path, and a broadcast axis that *is* the split axis with `ubFormer == 1`
routes to NDDMA — and one kernel-side guard that catches what the gates miss, replacing the
`Broadcast` call with a plain UB-to-UB `DataCopy`. Upstream attributes the finding to one measured
case, `cann-bench Maximum case 18`. Upstream states the proximate condition (`dShape==sShape`) and
nowhere states why that condition yields NaN rather than a copy, a no-op or an error. Not established
here.

## 2 · The wrong branch this removes
This is a correctness claim about a routing decision, which makes it different in kind from every other
gate in the broadcast family. An agent that treats implementation choice as a performance question —
the natural reading, since the other three branch conditions are about bandwidth and alignment — will
happily route a degenerate tile to the UB path when it is convenient, and receive NaN. Worse, it will
receive NaN only on the tiles that degenerate: a tail block with `rows == 1`, or the last `ubFormer`
of a split where the broadcast axis is the split axis. So the failure is shape-dependent and
partial — most of the output is right — which is the profile that survives a smoke test and fails a
tolerance check somewhere downstream, with the tiling document looking blameless.

The second wrong branch is trusting the kernel guard and skipping the host gates. Upstream is explicit
that the guard is a backstop and not the design: `这是兜底，正确选型应优先在 host 侧避免`. There is a
concrete reason beyond tidiness. The guard's substitute is `DataCopy(dst, src, 对齐cnt)` — a
**dtype-independent** UB-to-UB copy, chosen over `Adds` precisely so that types like `int64` are not
excluded (`ub_broadcast_design.md:63`). That is a correctness fix, not a performance one: the degenerate
tile still occupied a UB source buffer and a Vector issue slot it did not need, and the host gate would
have sent it to NDDMA, which handles the same tile correctly *and* without the Vector unit
(`broadcast_design.md:95`: `NDDMA 在 ubFormer==1 下搬 inner 连续数据、外层靠 offset 广播仍正确`). An
agent that relies on the guard ships correct output through the wrong pipe.

## 3 · Ground / Source
The headline, `reference/broadcast/broadcast_design.md:3`:

```
> 广播算子的性能关键在于**按场景选对实现**（前置 OneDim 快路径 + tile 内 NDDMA / DataCopyPad / UB 三类）——选错直接慢甚至 nan，选对才快。本文即该选型的最佳实践。
```

**A prior wave's claim-card quotes this sentence as `选错直接慢甚至出错（nan）` and states it appears
twice in the family's opening.** Re-verification at drafting time: `grep -rn 出错` over all eleven files
of this family returns nothing, and the sentence appears once, at `:3`, in the form above. The card's
reading of the sentence is right and its transcription is not. Reported in
`harvest/standing/950-td.md` as `SR-950td-03`; the card itself is not edited (write partition).

The two host gates, `:93-95`:

```
`brcMode` 逐输入写进 TilingData / tilingKey，kernel 据此分发。完整实现见 [`code/broadcast_add_tiling.cpp`](code/broadcast_add_tiling.cpp)。两道关键门控（cann-bench Maximum case 18 实测）：
1. **`!brcInTile`（广播轴严格在外层）→ 一律 ②**：UB/NDDMA 只在 tile 内展开，外层轴只能靠 offset 寻址。
2. **`brcInTile` 但无可展开维（切分轴广播且 `ubFormer==1`）且 `rank≤5` → ① NDDMA**：此时 UB Broadcast 会 `dShape==sShape` 空广播出 nan；NDDMA 在 `ubFormer==1` 下搬 inner 连续数据、外层靠 offset 广播仍正确。（`rank>5` 时 without-loop NDDMA 装不下 → 仍走 ③，由 kernel `UbBroadcast` 退化守卫拷贝兜底。）kernel `UbBroadcast` 的退化守卫（无可展开维则拷贝）对两种情形都做双保险。
```

Read against the template's own version, `ub_broadcast_design.md:11-13`, the two documents do not say
the same thing:

```
**前提：tile 内要有 UB Broadcast 能展开的维（`dShape>sShape`）。** 两种会出 nan 的反例（cann-bench Maximum case 18 实测）：
1. 广播轴**严格在外层**（`brcInTile=false`）：UB 展不了外层轴 → 必须走 ②（offset 寻址）。
2. 广播轴是切分轴**但 `ubFormer==1`**：tile 内仅 1 行，`dShape==sShape` 空广播 → 必须走 ① NDDMA。
```

`ub_broadcast_design.md:11` heads **both** items as `两种会出 nan 的反例` — two counter-examples that
produce NaN. But only item 2 carries a NaN mechanism in either file: item 1's stated failure is that
the outer axis *cannot be expanded* and must be addressed by offset, and `broadcast_design.md:94` gives
item 1's justification with no mention of NaN at all. So one document attributes NaN to two conditions
and the other attributes it to one. Registered as `C-950td-020`. The distinction matters operationally:
if item 1 also NaNs, a `!brcInTile` case wrongly routed to UB is a correctness failure; if it does not,
it is only a wasted Vector pass.

The kernel guard, `ub_broadcast_design.md:37` (in the code sketch) and `:63` (in prose):

```
// ★退化守卫：所有 dShape==sShape（无可展开维，如尾块 rows==1）→ 直接 UB→UB 拷贝，否则空广播出 nan
```
```
- **退化守卫**：`UbBroadcast` 内先检查是否存在 `dShape>sShape` 的维；若无（如尾块 `rows==1` 或选型漏判），直接 `DataCopy(dst,src,对齐cnt)` 做 dtype 无关的 UB→UB 拷贝（不用 `Adds`，避免 int64 等不支持），而非调 `Broadcast`，防空广播出 nan。这是兜底，正确选型应优先在 host 侧避免（见上"前提"）。
```

and as shipped, `code/broadcast_common.h:252-255`:

```cpp
    // Broadcast 会变成 src==dst 的空广播并产生 nan。此时直接拷贝 src→dst（src 已是该 tile 正确数据）。
    if (!anyExpand) {                              // 无可展开维：直接 UB→UB 拷贝（dtype 无关，避免空广播 nan）
```

Ten occurrences of `nan` across the family, all consistent on the proximate condition. What none of
them supplies is the mechanism. Nothing anywhere says whether the NaN comes from uninitialised UB being
read as the expansion source, from `Broadcast`'s behaviour when `GetBroadcastTilingInfo` computes a
zero expansion factor, from a division inside the tiling computation, or from the destination retaining
prior contents. `broadcast_common.h:252`'s `src==dst 的空广播` restates the condition in different
words. The distinction is not academic: if the NaN is uninitialised UB, then the same mis-selection on
a freshly-zeroed buffer would silently produce **zeros** rather than NaN — a wrong answer with no
diagnostic at all, which is strictly worse than the documented failure. Recorded in
`harvest/standing/950-td.md` as `Q-950td-06`.

The evidence base is one case, named twice: `cann-bench Maximum case 18 实测`. It carries a case
identity and nothing else — no board, no shape, no dtype, no tool, no repetition count, no captured
values, no NaN-versus-correct diff. `实测` (measured on hardware) is doing all the work, and this
family contains no other measurement of any kind: no µs, no percentage, no speed-up ratio anywhere in
its eleven files.

One structural note that makes the hazard easier to reason about. `dShape == sShape` on every axis
means the "broadcast" is the identity, and this book already carries the general form of the right
response: `0049` records that degenerate semantics should route to a pure copy template. Upstream's
kernel guard is exactly that rule applied inside a kernel rather than at routing time, and the
`不用 Adds，避免 int64 等不支持` clause is why it uses `DataCopy` — an arithmetic identity would have
been the obvious substitute and would have narrowed the dtype set.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase. The claim is
that a specific call produces NaN, so the procedure must *make* the call — with the guard removed —
and must distinguish NaN from the more dangerous zero case §3 raises.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and discard the case
if the die moved.

**Arm 1 — the degenerate call, guard removed.** Build the family's `UbBroadcast` from
`code/broadcast_common.h` with the `if (!anyExpand)` guard compiled out, and call it with
`dstShape == srcShape` on every axis, FP32, `rows == 1`. Capture the full destination buffer and
classify every element: NaN, equal to the source, zero, or other. This is the entry's central
observation and it is a classification, not a pass/fail.

**Arm 2 — the mechanism, which is what §3 says nobody states.** Repeat arm 1 three times with the
destination UB region prepared differently before the call: (a) untouched, (b) explicitly zeroed by
`Duplicate`, (c) filled with a distinctive sentinel (`-7.5`). If the output is NaN in all three, the
NaN is generated by the operation. If the output tracks the pre-fill — zeros in (b), sentinels in
(c) — then the "NaN" is uninitialised UB read back, upstream's claim is true only by accident of what
happened to be in memory, and the real hazard is silent wrong data. That is the outcome §3 argues is
worse than the documented one, and this arm is the only thing that separates them.

**Arm 3 — is item 1 also a NaN case?** Build the `!brcInTile` configuration (broadcast axis strictly
outside the tile) and route it to the UB path anyway, guard removed. `broadcast_design.md:94` predicts
only that the outer axis cannot be expanded; `ub_broadcast_design.md:11` groups it under NaN. Classify
the output as in arm 1. This settles `C-950td-020`.

**Arm 4 — the guard, and the host gate it backs up.** With the guard restored, run arms 1 and 3 and
confirm the output equals the source elementwise. Then run the same shapes through the NDDMA path the
host gate would have chosen, and record both correctness and `aiv_time` — upstream claims NDDMA is
correct there, and §2's argument that the guard ships correct output through the wrong pipe is only
worth carrying if NDDMA is in fact cheaper. ≥10 iterations, first 5 dropped, variance floor from 30
in-process and 5 fresh-process runs.

**Arm 5 — the dtype clause.** Upstream chose `DataCopy` over `Adds` to keep `int64` working
(`ub_broadcast_design.md:63`). Run the guard path at `int64` and at FP16 and confirm both copy
correctly; then attempt an `Adds`-based guard at `int64` and record whether it compiles. Retained
because it is expected to confirm upstream's reasoning rather than overturn it — the arm that does not
bite is kept because it did not.

Refuses to assume: that a free die stays free; that a die may be substituted; that NaN is generated
rather than read (arm 2 exists for exactly that); that the guard is present in whatever build is under
test (its presence or absence is echoed per run); that `ubFormer` reached the kernel as the host
computed it (echoed); that a run without NaN is a correct run (elementwise comparison against a CPU
reference on every arm).

## 5 · Checker — acceptance declared before the run
Verdict `degenerate_output(prefill)` ∈ {`nan`, `equals_source`, `equals_prefill`, `zeros`, `other`},
one per arm-2 pre-fill condition.

Declared before the run: this entry is **supported** iff `degenerate_output` is `nan` for all three
pre-fills — the NaN is produced by the operation, as upstream states. The OVERTURN fires iff
`degenerate_output == equals_source` for any pre-fill: the degenerate call would then be a no-op and
all three of upstream's protections would be unnecessary. A third outcome is possible and is **not**
covered by either: `equals_prefill` or `zeros`, which would mean the destination is being read back
rather than written, and upstream's NaN claim is an artifact of one machine's memory state. That result
neither supports nor overturns this entry — it *replaces* it, and the entry is rewritten in place
around a worse hazard than the one it documents.

Verdict `item1_nans` from arm 3, boolean, settling `C-950td-020`.

Verdict `guard_correct` from arm 4: true iff the guarded path matches the source elementwise at both
configurations. Verdict `nddma_cheaper` = median `aiv_time`(guarded UB path) / median
`aiv_time`(NDDMA path), with the floor.

Verdict `int64_copy_ok` and `int64_adds_compiles` from arm 5.

The exit code is not the verdict, and here that is the whole point: a kernel that writes NaN into every
output element returns success. Three guards. First, every arm classifies the **full** destination
buffer element by element rather than sampling — a partial NaN is the documented failure profile
(`尾块 rows==1`), so an instrument that checks the first element or a reduction of the output can miss
it entirely. Second, **the input that makes this checker go red**: every arm is paired with a
non-degenerate control — the same kernel, same build, with `dShape > sShape` on one axis — which
**must** produce a correct broadcast with no NaN. If the control NaNs, the build is broken and every
degenerate observation is uninformative; a NaN study whose only outcome is "we found NaN" cannot
distinguish the documented hazard from a mis-built kernel. Third, no arm is reported without its echoed
guard state, its echoed `ubFormer` and `anyExpand`, and its pre-fill condition — arm 2's three cases
are indistinguishable without the last of these, and it is the arm that decides what the entry says.

## 6 · Evidence
NOT YET RUN by us — no readout of ours exists. Nothing in this file is our measurement. Upstream's one
measurement is `cann-bench Maximum case 18 实测`, cited twice, carrying a case identity and no board,
shape, dtype, tool, repetition count or captured value; the family contains no other measured figure of
any kind. What was performed here at drafting time is a `grep` of all eleven files for `nan` (ten
occurrences, listed in §3), a `grep` for `出错` (zero occurrences, which is `SR-950td-03`), and a
reading of the two documents' differing attributions.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured by us. The entry does not establish that an empty broadcast produces NaN on any
board — it establishes that upstream states it six times, gates against it twice on the host, guards
against it once in the kernel, and attributes it to one named case. It does not establish the
mechanism, and §3 records that no document in the family supplies one; `Q-950td-06` records the
consequence, which is that the failure might be uninitialised memory rather than a generated NaN, in
which case the hazard is silent wrong data and this entry is understated. It does not resolve whether
the `!brcInTile` case also NaNs (`C-950td-020`). It does not establish `ubFormer`, `brcInTile`,
`anyExpand` or `rank≤5` as anything other than upstream's own predicates, and does not establish that
the two host gates are sufficient. It does not establish that NDDMA is correct at `ubFormer == 1`
beyond upstream's assertion. It says nothing about the other three branch conditions admitting the UB
path (`0415` covers one), nor about the family's four-branch selection as a whole (`0154`). The
`cann-bench Maximum case 18` figure is upstream's and is not carried as ours. The family scopes itself
to `DAV_3510（A5 / Ascend950，C310）` at `broadcast_design.md:6`, which names an architecture and
includes `C310`, a token appearing in no upstream mapping table (`0203`); BOARD is therefore
`family-claimed(unverified)` and no board is named. Nothing here is established for any 910-family
board.
