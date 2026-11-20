```
ID:        0451-the-four-stages-of-one-kv-block-run-c1-v1-c2-v2-and-a-reorder-is-a-correctness-violation-not-a-schedule
LABEL:     trap
LEVEL:     L4 (synchronisation)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-tiling-design/references/flashattention/overview.md:110-118 —
           "同一 KV 分块内,stage 依赖方向严格为 **C1 → V1 → C2 → V2**。 / 禁止: /
           - 把 stage 重排成 C1 → C2 → V1 → V2(让 AIC / AIV 角色分段) /
           - 在 stage 之间用错跨核同步方向(如 V1 完成只设置 AIC 等待但不设置 V1→C2 通知) /
           三级流水的 loop body 执行顺序(C1 本轮 → V2 上两轮 → V1+C2 上一轮)与本不变量不冲突 ——
           它讲的是不同 KV 分块如何交错,同一分块内的依赖方向仍是 C1→V1→C2→V2。 /
           **违反后果**:Mm2 Fixpipe ADDR_MISALIGN / 跨核数据未就绪 → 输出全零或乱值。"
SOURCE:    same file:106 — "任何 FA 类实现都必须满足以下四个不变量。**违反必崩**(silent zero /
           精度漂移 / 多核死锁)。" ; same shelf, design.md:505 — "**与 I1 的关系**:同一 KV 分块内的
           stage 依赖方向严格 C1→V1→C2→V2(I1 不变量,见 overview §3.1);**不同 KV 分块如何交错**
           (loop body 内 stage 顺序、是否反排、是否让某些 stage 早于其依赖的本轮 stage 执行)由设计
           决定,不在 I1 约束内。"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a FlashAttention kernel on a named 950 board built with the stages emitted as
           C1 → C2 → V1 → V2 within one KV block, whose output matches a CPU reference within the
           declared tolerance across the shape sweep — the ordering would then be a scheduling
           preference rather than a dependency, and the "违反必崩" framing would be wrong. Equally
           in the other direction: an ADDR_MISALIGN or an all-zero output tile from that build is
           the observation this entry predicts.
```

# 0451 · The four stages of one KV block run C1 → V1 → C2 → V2, and a reorder is a correctness violation, not a schedule

## 1 · Claim
Upstream asserts that a FlashAttention-class operator decomposes each KV block into four stages
across two core types — `C1` (Q·K^T on the cube core), `V1` (scale, softmax, cast on the vector core),
`C2` (P·V on the cube core), `V2` (cross-block accumulation on the vector core) — and that within one
KV block the dependency direction is strictly `C1 → V1 → C2 → V2`. Upstream asserts that reordering
those four into `C1 → C2 → V1 → V2`, so that each core type runs as one contiguous segment, is
forbidden, and that the named consequence is an `Mm2 Fixpipe ADDR_MISALIGN` or cross-core data that
is not yet ready, surfacing as an all-zero or garbage output. Upstream asserts separately that
interleaving *different* KV blocks — including a three-stage pipeline whose loop body runs
`C1(this round) → V2(two rounds back) → V1+C2(one round back)` — does not violate this, because the
invariant constrains the dependency direction inside one block and not the arrangement across blocks.
Not established here.

## 2 · The wrong branch this removes
Without this entry a harness agent looking at a `__mix__` kernel sees two core types and one obvious
optimisation: batch the work by core. Run both cube stages, then both vector stages, and you halve
the number of cross-core handshakes per KV block — from three to one — which is exactly the reasoning
that makes `C1 → C2 → V1 → V2` attractive. It is wrong because `C2` consumes `P`, and `P` is what
`V1` produces; the reorder does not merely delay a result, it reads a buffer before its producer has
written it.

The normal checks do not catch it. A cross-core handshake that is present but pointed at the wrong
stage still compiles, still runs, and still terminates — upstream's second forbidden form is exactly
that (`V1 完成只设置 AIC 等待但不设置 V1→C2 通知`). The failure surfaces as an all-zero tile or an
address-alignment fault inside the second Mmad, neither of which names the stage ordering. And a
single-KV-block test can pass by accident, because with one block there is no stale round to read.

The second wrong branch is the over-correction, and upstream states it explicitly so that the first
correction does not destroy the pipeline: an agent that reads I1 as "the four stages must appear in
this textual order in the loop body" will refuse the three-stage pipeline arrangement, in which `V2`
appears *before* `V1` in the source. That arrangement is legal and, per `0465`, necessary. The
invariant is about which round's data a stage reads, not about the order of statements.

## 3 · Ground / Source
The invariant, `references/flashattention/overview.md:108-118`:

```
### §3.1 I1 — 数据流方向不变量

同一 KV 分块内,stage 依赖方向严格为 **C1 → V1 → C2 → V2**。

禁止:
- 把 stage 重排成 C1 → C2 → V1 → V2(让 AIC / AIV 角色分段)
- 在 stage 之间用错跨核同步方向(如 V1 完成只设置 AIC 等待但不设置 V1→C2 通知)

三级流水的 loop body 执行顺序(C1 本轮 → V2 上两轮 → V1+C2 上一轮)与本不变量不冲突 —— 它讲的是不同 KV 分块如何交错,同一分块内的依赖方向仍是 C1→V1→C2→V2。

**违反后果**:Mm2 Fixpipe ADDR_MISALIGN / 跨核数据未就绪 → 输出全零或乱值。
```

The four stages themselves, `:73-78`, are a table whose fifth column is the cross-core synchronisation
semantics of each:

```
| **C1** | AIC | Q·K^T GEMM(Nd2Nz Q/K → L1 → L0 → Mmad → Fixpipe)| → `[Bq, Bk]` 中间矩阵到 GM | 完成后通知 AIV |
| **V1** | AIV | scale + softmax + cast | `[Bq, Bk]` → 归一化后的 P 到 GM | 等 C1 完成 / 完成后通知 AIC |
| **C2** | AIC | P·V GEMM(Nd2Nz P/V → L1 → L0 → Mmad → Fixpipe)| P + V → `[Bq, D]` 中间矩阵到 GM | 等 V1 完成 / 完成后通知 AIC |
| **V2** | AIV | 跨 KV 分块累积(默认 task 级模式下做 online rescale + Add;末块归一化)| `[Bq, D]` → 写回 attentionOut(末块)/ GM 自读自写段(非末块,在线累积)| 等 C2 完成 |
```

Note what the fourth column says about where each stage's product lives: every intermediate matrix
crosses the AIC/AIV boundary **through GM**, not through a shared on-chip buffer. That is why the
ordering is a data dependency and not a pipeline preference — the consumer reads a global-memory
segment whose write is signalled by a cross-core flag, so a mis-ordered flag is a read of stale or
uninitialised memory rather than a stall.

`:80` states the scope boundary in upstream's own words: `C1 → V1 → C2 → V2 是同一 KV 分块内的严格
数据流方向(见 §3.1 不变量 I1)。不同 KV 分块之间如何交错(流水排布、loop body 内 stage 顺序、
几级流水)由设计阶段决定,不在本不变量约束内。` The design shelf repeats the same separation at
`design.md:505`, and the fact that it is stated twice, in two files, is why §2's over-correction is
named here: upstream evidently expected readers to make it. Both statements are in one repository and
are therefore one origin (RULES.md Art. 3).

The severity register, `overview.md:106`: `任何 FA 类实现都必须满足以下四个不变量。**违反必崩**
(silent zero / 精度漂移 / 多核死锁)。` — "violating them must crash", with three named symptoms.
Upstream gives no case, no shape and no measurement for any of them; the symptom list is an assertion
about failure modes, not a readout. That register applies to `0452`, `0453` and `0454` as well, and
is why all four are `trap`-labelled.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three consecutive idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample afterwards
and discard the case if the die moved between samples.

Build a minimal GQA kernel per `design.md §8.1`'s baseline rule — first compile and run the
`asc-devkit` `__mix__` reference example named there, to establish that the kernel type itself works
under this CANN pin, before any FA code is written. Then, from one source with a compile switch:

**Arm 1 — the correct order (control).** `C1 → V1 → C2 → V2`, single KV block, single task, `Sq` and
`D` at the smallest aligned shape. Record elementwise agreement against a CPU reference computed in
FP32 from the same inputs. This arm must be green before any other arm is interpreted; if it is not,
nothing downstream is a finding about ordering.

**Arm 2 — the forbidden order (the poison arm, and this entry's reason).** The same source with the
stages emitted `C1 → C2 → V1 → V2` and the cross-core flags moved to match that emission. Multi-KV
block (`s2N ≥ 3`) and multi-task, because §2 records that a single block can pass by accident. Record:
the runtime error code if the kernel faults; the fraction of output elements that are exactly zero;
and elementwise agreement. Upstream predicts `ADDR_MISALIGN` or an all-zero/garbage tile.

**Arm 3 — the mis-pointed flag.** The correct stage order, but with `V1`'s completion signalling only
the AIC wait and not the `V1 → C2` notification, per upstream's second forbidden form. This separates
"the ordering is wrong" from "the handshake is wrong" — they are different defects with, upstream
implies, the same symptom.

**Arm 4 — the legal interleave, retained because it is expected NOT to bite.** The three-stage
pipeline body `C1(n) → V2(n-2) → V1(n-1) + C2(n-1)`, which places `V2` textually before `V1`. This
arm must be *green*. It is retained precisely because a green result here is what distinguishes I1
from a statement about source order; if this arm fails, either §2's over-correction is not an
over-correction or the harness has a second defect, and the entry is not supported either way.

Refuses to assume: that a free die stays free, or that a die may be substituted for another; that the
control arm's correctness implies the harness can detect incorrectness (arm 2 is the detector's own
test); that an exit code of 0 means the output is right; that one KV block is a test of a cross-block
dependency; that the CPU reference may be computed at the kernel's own precision (`0396`).

## 5 · Checker — acceptance declared before the run
Verdict `order_is_a_dependency`, computed from arms 1–4 together and named before any readout exists.
It is `true` iff arm 1 agrees elementwise with the FP32 reference, arm 2 either faults with a runtime
error or disagrees on more than the tolerance at `s2N ≥ 3`, and arm 4 agrees. It is `false` iff arm 2
agrees within tolerance across the whole sweep — the OVERTURN condition, under which the stage order
is a scheduling preference and this entry is wrong.

The process exit code is **not** the verdict. A FlashAttention kernel that writes zeros exits 0 and is
fast; that is the specific failure upstream names. Three guards:

1. **Every arm reports its zero fraction**, not only its max absolute error. An all-zero output tile
   compared against a reference by relative error can look "close" where the reference is also near
   zero, so the checker fails red if the zero fraction of any arm's output exceeds that of arm 1 by
   more than the padding rows account for.
2. **The input that makes this checker go red**: arm 1 itself. If the control arm does not agree with
   the CPU reference, the checker reports `harness_unsound` and refuses to emit a verdict at all. A
   suite whose only possible outcome is "the forbidden order failed" cannot distinguish a real
   dependency from a build that never worked — and this checker's positive fixture is arm 1 blinded
   (deliberately mis-scaled by `1/scale`), which must be caught.
3. **No arm is reported without its shape, its `s2N`, its task count, the CANN pin, and the compiler
   command**, because arm 2's prediction is explicitly conditioned on `s2N ≥ 3` and a single-block
   run of arm 2 passing is not evidence.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The four-stage table, the
invariant text, and the two statements of its scope boundary are file reads performed at drafting
time. The observation that every inter-stage product crosses the core boundary through GM is a reading
of upstream's own fourth column, not an observation of a build.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured, compiled, or run. The entry does not establish that the forbidden order ever
fails, only that upstream forbids it and names two symptoms for it. It does not establish that
`ADDR_MISALIGN` is the error a violation produces, nor that it is produced by `Mm2`'s Fixpipe rather
than elsewhere. It does not establish the four-stage decomposition as the only possible one — upstream
itself says subfamily extensions may add stages (`design.md:105`), and this entry covers the default
FA/GQA shape only. It says nothing about how many KV blocks may be in flight, which is a design
decision upstream explicitly leaves open. It does not establish the three-stage arrangement in arm 4
as good, only as permitted. No board token appears in the invariant text or the stage table, so BOARD
is `family-claimed(unverified)`; the family names `A5` elsewhere (`design.md:94`, `:525`, `:617`) but
not here, and §4 names 950PR/950DT only as where our run would happen. Nothing here is established for
any 910-family board, and nothing in this entry transfers to the split-KV-reduce parallel strategy,
whose stage semantics differ (`0454`).
