```
ID:        0453-three-slot-semantics-need-three-counters-and-three-constants-and-sharing-one-constant-is-a-silent-race
LABEL:     trap
LEVEL:     L2 (memory hierarchy & residency)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-tiling-design/references/flashattention/design.md:552-568 —
           "**核心原则**:不同语义的 slot 必须用**不同的计数器**取模**不同的常量**,**不能共用**。
           这是数学要求,不是命名约定。" · "跨 task 状态 slot:taskSlot = taskCounter % preloadSlots /
           跨 loop handshake slot:handshakeSlot = loopCounter % handshakeSlots /
           跨 loop 自读自写 slot:selfRefSlot = loopCounter % selfRefSlots" · "**关键**:同一变量
           (loop 计数器)取模**不同常量**会得到不同 slot 序列 —— 这就是为什么 §2.4 Q2 要求各槽数
           独立声明。"
SOURCE:    same file:570-575 — "**误用症状**: / - 用 task 计数器替代 loop 计数器(在 handshake /
           自读自写 slot 上):multi-s2 块在 s2N ≥ 3 时精度漂移 / - 用 loop 计数器替代 task 计数器
           (在 task 状态 slot 上):s2 累积状态错乱(max/sum 跨 task 串扰)/ - 三类 slot 全部用同一
           常量取模:可能掩盖 race,但任一槽数的"实际并行度需求"变化时整体崩塌 /
           **最小复现条件**:`single task + multi s2 块(s2N ≥ 3)`,或 `multi task per core + multi s2 块`。"
           ; same shelf, subfamilies.md:332-340 — the three-constant table and "混用同一常量会导致
           silent 数据污染或 race(O_acc 被覆写 / KV 预取阻断 / Cube↔Vector 握手错位)。"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a FlashAttention build on a named 950 board in which all three slot families are taken
           modulo one constant and one counter, run at `s2N ≥ 3` with multiple tasks per core, whose
           output agrees elementwise with the FP32 reference across the shape sweep including the
           hostile end — the separation would then be unnecessary at every reachable configuration
           and upstream's "mathematical requirement" would be an unexercised precaution. In the other
           direction: a run in which the shared-constant build drifts only above `s2N = 3` is the
           observation this entry predicts, and the drift's onset is the number the entry lacks.
```

# 0453 · Three slot semantics need three counters and three constants, and sharing one constant is a silent race

## 1 · Claim
Upstream asserts that a FlashAttention-class operator carries at least three distinct kinds of
rotating buffer slot, and that each must be indexed by **its own counter modulo its own constant**:
cross-task state slots by a task counter modulo `preloadSlots`; cross-stage handshake slots by a loop
counter modulo `handshakeSlots`; cross-loop self-read/self-write slots by the same loop counter modulo
a possibly different `selfRefSlots`. Upstream asserts this is a mathematical requirement rather than a
naming convention, and gives a distinct symptom for each of three misuses: a task counter used where a
loop counter belongs produces precision drift at `s2N ≥ 3`; a loop counter used where a task counter
belongs produces cross-task contamination of the online-softmax `max`/`sum`; and collapsing all three
onto one constant may hide the race until any one slot family's parallelism requirement changes.
Upstream asserts a minimal reproduction condition: a single task with `s2N ≥ 3` KV blocks, or multiple
tasks per core with multiple KV blocks. Not established here.

## 2 · The wrong branch this removes
Without this entry a competent agent writing the loop body sees several rotating buffers, notices that
they all rotate, and defines one `SLOT_NUM`. This is not carelessness — it is the ordinary
de-duplication instinct, and it is reinforced by the fact that the three constants are often *equal*
in a working implementation. Upstream's own worked instantiation at `design.md:125` has the cross-task
state slot count equal to the handshake slot count (both 2) and the self-read/self-write count at 3,
so two of the three genuinely coincide in the shipped configuration. An agent that unifies them
observes no failure and has, by upstream's account, merely hidden one.

The normal checks do not catch it for a specific reason worth naming. The three quantities are not
tuning parameters that happen to be equal; they answer three different questions — how many tasks hold
live state at once, how deep the cross-core handshake must be to keep the two core types from
serialising, and how many rounds of the self-accumulating GM segment are in flight in a three-stage
pipeline. They coincide only until one of the three answers changes, and the change that moves them
apart is a *pipeline depth* change, which an agent makes for performance and would never expect to
break correctness.

The second wrong branch is subtler and upstream states it directly: two of the three slot families use
the **same counter**. `handshakeSlot` and `selfRefSlot` are both `loopCounter % k` for different `k`.
An agent that has correctly separated "task counter" from "loop counter" may believe it has done the
separation, and still be sharing one constant between the two loop-counter families — where the same
counter modulo different constants produces genuinely different slot sequences. This is the sentence
upstream italicises at `:568`, and it is the one an agent reading fast will read as a restatement of
the counter split rather than as a second, independent requirement.

## 3 · Ground / Source
The principle and the three formulas, `references/flashattention/design.md:550-568`:

```
### §7.4 跨 loop buffer 与跨 task 状态 slot 公式分离原则

**核心原则**:不同语义的 slot 必须用**不同的计数器**取模**不同的常量**,**不能共用**。这是数学要求,不是命名约定。
```

and the table below it, whose columns are exactly "which counter" and "which constant":

```
| **跨 task 状态 slot** | 跨 task 持有 stateful 状态(默认 task 级模式下的 softmax max/sum/exp 等)| **task 计数器**(每完成一个 task 自增 1)| 跨 task 状态槽数(§2.4 Q2)| 跨 s2 在线累积的 softmax 状态段 |
| **跨 loop handshake slot** | 跨 stage 握手 buffer(上一 stage 写 → 下一 stage 读)| **loop 计数器**(每个 loop body 自增 1)| 跨 stage 握手槽数(§2.4 Q2)| 跨核握手段 |
| **跨 loop 自读自写 slot** | 同一段在不同 loop 迭代中被自身读写 | **loop 计数器** | 自读自写槽数(§2.4 Q2,可能 ≠ 握手槽数)| 默认 task 级模式下 V2 跨 s2 块的 O_acc 落地段 |
```

with the skeleton at `:562-566`:

```
跨 task 状态 slot:taskSlot = taskCounter % preloadSlots
跨 loop handshake slot:handshakeSlot = loopCounter % handshakeSlots
跨 loop 自读自写 slot:selfRefSlot = loopCounter % selfRefSlots
```

The symptom table, `:570-575`, is the part that makes this entry testable rather than exhortatory:

```
**误用症状**:
- 用 task 计数器替代 loop 计数器(在 handshake / 自读自写 slot 上):multi-s2 块在 s2N ≥ 3 时精度漂移
- 用 loop 计数器替代 task 计数器(在 task 状态 slot 上):s2 累积状态错乱(max/sum 跨 task 串扰)
- 三类 slot 全部用同一常量取模:可能掩盖 race,但任一槽数的"实际并行度需求"变化时整体崩塌

**最小复现条件**:`single task + multi s2 块(s2N ≥ 3)`,或 `multi task per core + multi s2 块`。
```

A published minimal reproduction condition is rare in this corpus and it is what §4 is built on. Note
what it implies about test design: the first misuse cannot be reproduced with fewer than three KV
blocks, so a suite whose largest case has `s2N = 2` will report the defect absent.

The same rule appears twice more in the same repository. `overview.md:129-138` states it as invariant
I3 — `跨 task 持有的状态 … **必须按任务分槽隔离**,不同任务的状态不能共享同一物理位置` — with the
consequence `被上一任务的尾状态污染 → 输出乱值`, and adds a third forbidden form specific to
task-level PRELOAD: `在任务级 PRELOAD 下,用同一 task slot 公式覆盖跨 stage handshake buffer(混淆
task-level 与 loop-level slot 语义)`. And `subfamilies.md:330-340` states it as a subfamily-level
prohibition over three named constants — cross-core handshake, L1 rotation, V2 self-read/self-write —
where the middle one is subfamily-specific and the outer two are not:

```
| 跨核握手槽 | Cube↔Vector 跨核握手 buffer 的轮转(典型固定值)| `design.md §2.4` |
| L1 rotation 槽 | 任务级 KV / Q 预取深度(子族特定)| 本文件 §2.2 |
| V2 自读自写槽 | V2 阶段在三级流水中同时活跃的 task 数(典型 > 跨核握手槽)| `design.md §2.4` + `§4.4 Q2` |
```

so the family names **four** slot semantics in total, not three: the L1 rotation depth is a fourth,
listed in `design.md:117` alongside the other three and excluded from `§7.4`'s table because it is not
a GM-segment index. An agent that separates exactly the three formulas in `§7.4` and then shares a
constant with the L1 rotation depth has satisfied the stated rule and violated the stated prohibition.
Registered as `C-950fin-003` — not a contradiction of fact, but two enumerations of one set that do
not have the same members, in one repository.

`subfamilies.md:338` also states a relation the `§7.4` table does not: `V2 自读自写槽 … 典型 > 跨核
握手槽`. Upstream's worked instantiation (`design.md:125`) is consistent with it (3 vs 2). It is the
only ordering statement in the family and it has no derivation.

Three files, one repository — one origin (RULES.md Art. 3). This entry is `harvested`.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three consecutive idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample afterwards
and discard the case if the die moved.

One GQA kernel with the three slot formulas behind three compile switches, so that every arm is the
same source with the same tiling. The CPU reference is computed in FP64 and compared at the atol/rtol
declared per `overview.md §4.4` — never at the kernel's own precision (`0396`).

**Arm 0 — the shape ladder, which decides whether any other arm means anything.** The correct build at
`s2N ∈ {1, 2, 3, 4, 8}` × `tasks_per_core ∈ {1, 2, 4}`, all green. This establishes that the harness
reaches the region where upstream says the defects live. An arm-1 pass at `s2N = 2` is not evidence.

**Arm 1 — task counter substituted for loop counter**, on the handshake and self-read/self-write
slots, across the same ladder. Upstream predicts agreement at `s2N ≤ 2` and drift from `s2N = 3`.
Record max absolute error per `s2N`, not a pass/fail: the *onset* is the finding, because upstream
states the threshold and this arm is where the threshold is confirmed or moved.

**Arm 2 — loop counter substituted for task counter** on the state slot, at `tasks_per_core ≥ 2`.
Upstream predicts cross-task contamination of `max`/`sum`. Dump the per-task softmax `max` and `sum`
from the state segment alongside the output, so that the arm distinguishes "the output is wrong" from
"the output is wrong *because the state crossed tasks*" — the second is the claim, the first is not.

**Arm 3 — all three modulo one constant.** Run at the whole ladder with all three constants set to
each of 2, 3 and 4 in turn. Upstream predicts this may pass. A pass is therefore not a refutation of
the entry, and the checker says so before the run: what this arm tests is the *second* half of
upstream's claim, that the shared build collapses when one slot family's requirement changes. So arm 3
is repeated with the pipeline depth raised one level, where the self-read/self-write requirement moves
to 4 while the handshake requirement does not.

**Arm 4 — the fourth constant, which the `§7.4` table omits.** The correct build with the L1 rotation
depth sharing the handshake constant. Retained because it may not bite: if it is green everywhere on
the ladder, `C-950fin-003` is a documentation gap and not a defect, and §7 records that.

Refuses to assume: that a free die stays free, or that a die may be substituted; that a green run at
`s2N = 2` says anything about `s2N ≥ 3` (arm 0 exists to forbid that inference); that a race
reproduces on every run — every arm is repeated ≥20 times and the *fraction* of runs that disagree is
reported, since a slot race is a scheduling-dependent defect and a single green run is not a green
result; that the compiler leaves the three constants distinct if they are numerically equal (each arm
echoes the three values it actually compiled with).

## 5 · Checker — acceptance declared before the run
Verdict `drift_onset(arm) = min { s2N : fraction of runs disagreeing beyond atol > 0 }`, declared
before the run, with `+∞` when no `s2N` on the ladder disagrees. Acceptance for the entry as written:
`drift_onset(arm 1) == 3` and `drift_onset(arm 0) == +∞`. An onset at 4 or higher is a finding that
moves upstream's stated threshold; an onset at 2 is a finding that upstream's minimal reproduction is
not minimal. Both are reported as such rather than as a pass.

Verdict `state_crosses_tasks` from arm 2 ∈ {`yes`, `no`, `output_wrong_but_state_clean`}, the third
value existing so that the arm cannot be scored as supporting the claim merely by failing.

Verdict `shared_collapses_on_depth_change` from arm 3 ∈ {`true`, `false`}, evaluated only on the
depth-raised repetition. Declared now: arm 3 passing at fixed depth is **not** an OVERTURN. The
OVERTURN fires iff arm 3 passes at fixed depth **and** at the raised depth, across the full ladder,
with all three constants shared.

The exit code is not the verdict: every arm here produces plausible-looking output, and two of the
three misuses are documented to produce *drift* rather than garbage — a comparison that only checks
for NaNs or zeros would pass all of them. Guards: (1) each arm reports the disagreeing-run fraction
over ≥20 repetitions, and an arm reported from a single run is discarded as untestable, never as
agreement; (2) **the input that makes this checker go red**: arm 1 at `s2N = 8`, the far end of the
ladder, where upstream's mechanism predicts the largest drift — if arm 1 is clean at `s2N = 8` while
arm 0 is clean everywhere, the two builds are not actually different and every onset in the table is
an artifact, so the checker requires each arm to echo the compiled constants and the counter symbol
it indexed with, and fails red if any two arms echo identical configurations; (3) no point is reported
without its atol, its repetition count, its CANN pin and its echoed constants.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The principle, the three
formulas, the symptom table, the minimal reproduction condition, the subfamily-level prohibition and
the worked instantiation are file reads performed at drafting time. The observation that the family
enumerates four slot semantics in one place and three in another, and the observation that two of the
three formulas share a counter, are readings of upstream's own lines, not observations of a build.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The entry does not establish that any misuse fails, nor that
`s2N = 3` is where the first one starts — upstream states it and this entry records the statement. It
does not establish the *values* of `preloadSlots`, `handshakeSlots` or `selfRefSlots`: upstream gives
one worked instantiation (`design.md:125`) as an example and explicitly refuses to fix the numbers,
so nothing here says how many slots any of them needs. It does not establish that
`selfRefSlots > handshakeSlots`, which upstream states as typical with no derivation. It does not
resolve `C-950fin-003` — whether the L1 rotation depth is a fourth member of the same rule or a
separate one — and §4 arm 4 is the procedure that would. It says nothing about the split-KV-reduce
parallel strategy, whose task structure is declared incompatible with the default RunInfo
(`design.md:145`) and whose slot semantics are not enumerated anywhere in the family. No board token
appears in any of the three passages, so BOARD is `family-claimed(unverified)`; §4 names 950PR/950DT
only as where our run would happen. Nothing here is established for any 910-family board.
