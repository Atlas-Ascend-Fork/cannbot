```
ID:        0465-v2-runs-before-v1-in-the-loop-body-so-the-softmax-state-is-read-before-the-same-body-overwrites-it
LABEL:     knowledge
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-tiling-design/references/flashattention/design.md:507-517 —
           "**编排约束**: / - 在 loop body 内任何重排都不能让某个 stage 读到本轮尚未产生的状态
           (读旧轮的状态需要 slot 公式正确,见 §7.4) / - 反排某些 stage(让节拍编号大的先执行)可避免
           覆盖问题——典型场景:V2 需要读上一轮的 softmax state,若与 V1 在同一 loop body 中按节拍顺序
           执行,V1 会先覆写 state;故 V2 应**先于** V1 执行" · "> 一种已落地的实例化(三级流水排布,
           具体代码见参考实现):loop body 内 stage 顺序 `C1(本轮) → V2(上两轮) → V1(上一轮) +
           C2(上一轮)`,V2 提前执行确保 softmax state 不被 V1 覆盖。"
SOURCE:    same file:541-548 — "**禁止**:数字下标(`info0` / `info1` / `info2` 这种)——下标与节拍号
           容易错位,改动时易写错。 / **强制**:按"该 slot 在 loop body 内**哪个节拍执行 / 处理哪一轮
           的任务**"**语义化**命名。命名格式开放,但必须能从名字直接读出该 slot 对应的 stage 与轮次。"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a three-stage-pipeline FlashAttention build on a named 950 board with `V1` emitted before
           `V2` in the loop body, whose output agrees elementwise with the FP64 reference across a
           multi-KV-block sweep — the overwrite would then not occur, either because the state is
           slot-rotated deeply enough or because the two stages do not share the buffer this entry
           assumes, and the reordering would be unnecessary. Equally: a `V1`-first build that agrees
           only when the state slot count is raised would show the reordering and the slot depth are
           two solutions to one problem, which upstream never says.
```

# 0465 · V2 runs before V1 in the loop body, so the softmax state is read before the same body overwrites it

## 1 · Claim
Upstream asserts that once several KV blocks are interleaved in one loop body, the order in which the
stages are *emitted* is a design decision separate from the dependency direction inside a block, and
that it is constrained by one rule: no stage may read state that the current round has not yet
produced, and reading an older round's state requires the slot formula to be right. Upstream asserts a
specific consequence: `V2` reads the previous round's softmax state, and `V1` writes it, so emitting
them in beat order puts the write before the read and `V1` clobbers what `V2` needs — therefore `V2`
must be emitted **before** `V1`. Upstream asserts one realised instantiation, a three-stage pipeline
whose loop body runs `C1(this round) → V2(two rounds back) → V1(one round back) + C2(one round back)`,
with `V2` moved early for exactly that reason. Upstream separately forbids numeric cache-slot suffixes
and requires slot names from which the stage and the round can be read directly. Not established here.

## 2 · The wrong branch this removes
Without this entry an agent writes the loop body in the order the stages are numbered. `C1`, `V1`,
`C2`, `V2` is the dependency order, it is the order the whole family is documented in (`0451`), and
writing it any other way looks like a violation of the invariant that names that order. So the wrong
branch here is produced by *correctly* learning the previous rule and applying it one level up — which
is why `0451` spends a paragraph forbidding the same over-correction from the other side.

The mechanism is a write-after-read hazard created by pipelining, not by the algorithm: within one KV
block `V1` produces state that `V2` later consumes, so there is no conflict; across rounds, the `V1`
of round *n−1* and the `V2` of round *n−2* are in the same loop body, and `V1` writes the buffer that
`V2` is about to read. The fix is either to rotate the buffer deeply enough that the two rounds use
different slots, or to emit the reader first. Upstream chooses the second and does not say the first
exists as an alternative — although its own slot-count discipline (`0453`) is exactly that mechanism.
Recorded as `Q-950fin-15`.

The normal checks do not catch it in a single-round test, because with one KV block there is no
previous round to clobber. It appears with multiple blocks, in the softmax statistics, as drift rather
than as garbage — the same signature as three other defects in this family (`0453`, `0458`, `0463`),
which is why this book carries them separately with their distinguishing observations rather than as
one "multi-block failure" entry.

The second wrong branch is the naming one, and it is small but load-bearing here: with stages emitted
out of beat order, a slot named `info0`/`info1`/`info2` no longer corresponds to anything a reader can
recover. Upstream forbids numeric suffixes for exactly this reason — `下标与节拍号容易错位` — so the
naming rule is not style, it is what makes the reordering auditable.

## 3 · Ground / Source
The constraint and the worked case, `references/flashattention/design.md:507-517`:

```
**编排约束**:
- 在 loop body 内任何重排都不能让某个 stage 读到本轮尚未产生的状态(读旧轮的状态需要 slot 公式正确,见 §7.4)
- 反排某些 stage(让节拍编号大的先执行)可避免覆盖问题——典型场景:V2 需要读上一轮的 softmax state,若与 V1 在同一 loop body 中按节拍顺序执行,V1 会先覆写 state;故 V2 应**先于** V1 执行

**同步事件 ID 取值规则**:
- 不与平台保留 ID 冲突
- 各 ID 语义独立声明,**禁止**复用同一 ID 表达不同语义
```

and the instantiation at `:517`:

```
> 一种已落地的实例化(三级流水排布,具体代码见参考实现):loop body 内 stage 顺序 `C1(本轮) → V2(上两轮) → V1(上一轮) + C2(上一轮)`,V2 提前执行确保 softmax state 不被 V1 覆盖。
```

Two things are worth separating. The **round labels** are what makes the arrangement legal: `C1` works
on this round, `V2` on two rounds back, `V1` and `C2` on one round back. So the textual order
`C1 → V2 → V1` is not the dependency order reversed; it is four different rounds' work, and every
stage still consumes only what an earlier round produced. An agent that reproduces the *order* without
the *round offsets* has built something that reads uninitialised state, which is the first constraint's
prohibition rather than its remedy.

The **`+`** in `V1(上一轮) + C2(上一轮)` is unexplained. Two stages on two different core types, same
round, joined by a plus rather than an arrow — presumably concurrent, but upstream never says, and
`0451`'s invariant requires `V1` before `C2` within a block. The two are consistent if the plus means
"issued in the same beat with the cross-core handshake enforcing the order", which is what the family's
synchronisation section (`0463`) would provide. Upstream does not state it. Recorded as `C-950fin-011`
— not a contradiction of fact, but a notation the family uses once and never defines, in the one place
its stage order looks like it violates its own invariant.

The synchronisation ID rules in the same block are a third obligation and a small one, but the second
of them (`禁止复用同一 ID 表达不同语义`) is the same prohibition as `0453`'s constant-sharing rule
applied to event IDs rather than to slot counts — a fifth surface for one discipline in this family.

The naming rule, `:541-548`:

```
**禁止**:数字下标(`info0` / `info1` / `info2` 这种)——下标与节拍号容易错位,改动时易写错。

**强制**:按"该 slot 在 loop body 内**哪个节拍执行 / 处理哪一轮的任务**"**语义化**命名。命名格式开放,但必须能从名字直接读出该 slot 对应的 stage 与轮次。
```

`命名格式开放` — the format is left open, and only the recoverability property is required. That is
worth noting as a form choice: the rule constrains what the name must let a reader recover, not what
it must look like, which is the same shape as this book's own filename convention (`form/CONVENTIONS.md`).

One file, one origin (RULES.md Art. 3).

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind on three consecutive idle samples only; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and
discard the case if the die moved. All comparisons against an FP64 reference at the declared atol.

**Arm 1 — the reorder, at fixed slot depth.** One three-stage-pipeline GQA build with the loop-body
emission order switchable between `C1 → V2 → V1 + C2` (upstream's) and `C1 → V1 + C2 → V2`, round
offsets identical in both. Sweep `s2N ∈ {1, 2, 3, 8}`, ≥20 repetitions, report the disagreeing-run
fraction and the max absolute error per `s2N`. Prediction: `s2N = 1` agrees for both; the `V1`-first
build drifts from `s2N ≥ 2`.

**Arm 2 — the alternative upstream does not name.** The `V1`-first build with the cross-task state slot
count raised by one. If it becomes correct, the reordering and the slot depth are two remedies for one
hazard (`Q-950fin-15`), and a design that has done one need not do the other — which changes what
`0453`'s slot-count discipline is for. If it stays wrong, the reorder is required independently.

**Arm 3 — the round offsets, which are the part that is easy to copy wrong.** Upstream's emission
order with the `V2` offset set to one round back instead of two. This is the "reproduce the order
without the offsets" error §3 names. Report whether it faults, drifts, or agrees; agreement would mean
the two-round offset is not required at this pipeline depth, which is a finding about the
instantiation rather than about the rule.

**Arm 4 — the `+` notation, retained because it may not bite.** Instrument the build to record the
issue order of `V1` and `C2` within one beat and confirm that `V1`'s GM write completes before `C2`'s
read, per `0451`'s invariant. If the two are genuinely concurrent with no ordering, `C-950fin-011` is a
real gap and the invariant is enforced by the handshake rather than by the emission; if `V1` always
precedes, the plus is a typographic choice.

Refuses to assume: that a free die stays free, or that a die may be substituted; that one run is a
result (every cell is repeated ≥20 times, since a write-after-read hazard is schedule-dependent); that
the two builds differ only in emission order (each echoes its stage order and round offsets); that
`s2N = 1` passing means anything; that the slot depth is what the design intended (arm 2 changes it
deliberately and echoes it).

## 5 · Checker — acceptance declared before the run
Verdict `drift_onset(order)` — the smallest `s2N` at which the disagreeing-run fraction exceeds zero —
declared before the run. Acceptance for the entry: `drift_onset(V2_first) == +∞` and
`drift_onset(V1_first) ≤ 2`. The OVERTURN fires iff `drift_onset(V1_first) == +∞` across the sweep
including `s2N = 8`.

Verdict `slot_depth_is_alternative` from arm 2 ∈ {`yes`, `no`}, which is `Q-950fin-15`'s answer and is
recorded whichever way it falls.

Verdict `offset_required` from arm 3 ∈ {`yes`, `no`, `faults`}.

Verdict `v1_precedes_c2` from arm 4, boolean, with the recorded issue order.

The exit code is not the verdict: the `V1`-first build is expected to produce drift, not a fault, and
drift passes any check with a loose tolerance — which is what an attention operator's tolerance is.
Guards: (1) the checker computes raw error and applies the tolerance itself, failing red on any cell
reported as a bare pass/fail without its raw error; (2) **the input that makes this checker go red**:
`s2N = 1`, where the loop body has no previous round and both orders must agree exactly — if they
disagree there, the two builds differ in more than emission order and every onset is an artifact; (3)
no cell is reported without its `s2N`, repetition count, echoed stage order, echoed round offsets,
echoed slot counts, atol and CANN pin.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The orchestration constraint,
the `V2`-before-`V1` rule with its stated mechanism, the three-stage instantiation with its round
offsets, the synchronisation ID rules and the slot-naming rule are file reads performed at drafting
time. The observations that the round offsets rather than the textual order make the arrangement legal,
that the `+` notation is used once and never defined, and that raising the slot depth is an unnamed
alternative remedy, are readings of upstream's own lines, not observations of a build.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The entry does not establish that `V1` clobbers the state — upstream
asserts the hazard and gives no readout. It does not establish that the reordering is necessary rather
than one of two remedies (`Q-950fin-15`). It does not establish the three-stage arrangement or its
round offsets as required or as optimal; upstream calls it `一种已落地的实例化`, one realised
instantiation, and explicitly leaves the pipeline depth to the designer (`0453`). It does not resolve
what the `+` means (`C-950fin-011`). It does not cover the synchronisation ID rules beyond quoting
them, nor the platform-reserved ID range, which upstream references and never enumerates. It says
nothing about the split-KV-reduce strategy, which has no stateful cross-round softmax accumulation and
therefore no such hazard (`0454`). No board token appears in the quoted passages, so BOARD is
`family-claimed(unverified)`; §4 names 950PR/950DT only as where our run would happen. Nothing here is
established for any 910-family board.
