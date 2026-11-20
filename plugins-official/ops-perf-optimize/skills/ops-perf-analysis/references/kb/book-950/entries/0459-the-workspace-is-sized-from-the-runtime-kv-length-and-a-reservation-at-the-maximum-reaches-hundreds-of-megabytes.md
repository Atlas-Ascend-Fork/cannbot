```
ID:        0459-the-workspace-is-sized-from-the-runtime-kv-length-and-a-reservation-at-the-maximum-reaches-hundreds-of-megabytes
LABEL:     knowledge
LEVEL:     L0 (launch & host)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-tiling-design/references/flashattention/design.md:371-379 —
           "#### Q3:按运行时 Sk 分配原则 / 回答:**workspace 是按 `Sk_max` 静态预留,还是按运行时
           `Sk` 动态分配?** / **正确答案永远是动态**:Host 暴露 `GetXxxWorkspaceSize(...)` API,
           按运行时 Sk 计算返回 size;caller 按返回 size 分配 workspace。 / **禁止**:按 Sk_max 静态
           预留——例如 `跨核握手段 size = B × Hq × Bq × Sk_max × sizeof(elem)`,Sk_max 较大(如 32K)
           时单块可达数百 MB,实际运行时浪费严重且限制用户上限。"
SOURCE:    same file:348-356 — the workspace segment roster (跨核握手段 / 跨 loop 自读自写段 /
           任务级状态段 / 子族扩展段 / 并行策略扩展段) ; :383 — "- [ ] **清单 9(长 Sk workspace
           槽轮转)**:所有 workspace 段按运行时 Sk 分配;§2.4 列出的所有槽语义类别(跨 stage 握手 /
           跨 loop 自读自写 / 跨 task 状态 / L1 rotation)数量与公式分清楚"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a FlashAttention operator on a named 950 board whose handshake segment, sized from the
           runtime `Sk`, measurably costs more per launch than a `Sk_max`-sized reservation reused
           across launches — the dynamic rule would then trade allocation time for memory rather than
           being strictly better, and "正确答案永远是动态" would be scoped rather than absolute.
           Equally: a `Sk_max = 32K` reservation whose measured single-segment size is far below the
           hundreds of megabytes upstream states would falsify the figure the prohibition rests on.
```

# 0459 · The workspace is sized from the runtime KV length, and a reservation at the maximum reaches hundreds of megabytes

## 1 · Claim
Upstream asserts that a FlashAttention-class operator's GM workspace segments must be sized from the
runtime `Sk`, not statically reserved at `Sk_max`, and states the answer as unconditional — `正确答案
永远是动态`. Upstream asserts the mechanism: the host exposes a `GetXxxWorkspaceSize(...)` API that
computes a size from the runtime `Sk` and returns it, and the caller allocates exactly that. Upstream
asserts the cost of the forbidden form with one worked expression and one figure: a cross-core
handshake segment sized `B × Hq × Bq × Sk_max × sizeof(elem)` reaches hundreds of megabytes for a
single block when `Sk_max` is large, taking 32K as the example, wasting memory at runtime and capping
what a user may ask for. Not established here.

## 2 · The wrong branch this removes
Without this entry an agent sizes the workspace the way kernel workspaces are usually sized: from the
tiling's declared maxima, once, at compile or at host-init. This is the ordinary discipline everywhere
else — a fixed-size workspace is simpler, has no per-launch allocation, and cannot fail to be big
enough. For FlashAttention it is wrong for a reason specific to the family: `Sk` is not a shape the
operator *has*, it is a shape that grows during a decode session, so `Sk_max` is not a property of the
workload but a limit the implementation imposes on the user. The static reservation therefore does two
things at once, and the second is invisible in a benchmark: it wastes memory, and it caps the context
length the operator supports.

The normal checks do not catch it because the static form is *correct*. Every test passes. Memory
usage is high, which reads as "attention is memory-hungry", which is true for unrelated reasons. And
the cap only appears when a user asks for a longer context than the constant allows, at which point
the failure is an allocation error attributed to the caller.

The second wrong branch is the over-correction that the segment roster makes easy: sizing only the
handshake segment dynamically because that is the one upstream's example names. The family has five
segment classes (`:348-356`), of which at least three scale with `Sk` or with the number of KV blocks,
and the checklist at `:383` says `所有 workspace 段按运行时 Sk 分配` — all of them.

## 3 · Ground / Source
The rule, `references/flashattention/design.md:371-379`:

```
#### Q3:按运行时 Sk 分配原则

回答:**workspace 是按 `Sk_max` 静态预留,还是按运行时 `Sk` 动态分配?**

**正确答案永远是动态**:Host 暴露 `GetXxxWorkspaceSize(...)` API,按运行时 Sk 计算返回 size;caller 按返回 size 分配 workspace。

**禁止**:按 Sk_max 静态预留——例如 `跨核握手段 size = B × Hq × Bq × Sk_max × sizeof(elem)`,Sk_max 较大(如 32K)时单块可达数百 MB,实际运行时浪费严重且限制用户上限。
```

The expression is worth reading arithmetically, because it is the only place in the FA family where a
memory figure can be checked against its own formula. `B × Hq × Bq × Sk_max × sizeof(elem)` at
`Sk_max = 32768` and `sizeof(elem) = 2` gives 64 KiB per unit of `B × Hq × Bq`; "hundreds of MB"
therefore implies `B × Hq × Bq` in the low thousands — e.g. `B = 4`, `Hq = 32`, `Bq = 16` gives 2048
units and 128 MiB. So the figure is consistent with the formula at ordinary inference shapes, and it is
a *derived* number rather than a measured one. Upstream does not say which shape it used. Recorded as
`Q-950fin-08`; §4 re-derives it rather than inheriting it.

One thing the formula does **not** contain is a slot count. The segment rotates (`0453`), so its true
size is the per-round size times the slot count, and the checklist at `:383` couples the two questions
in one line: `所有 workspace 段按运行时 Sk 分配;§2.4 列出的所有槽语义类别 … 数量与公式分清楚`. An
agent that sizes dynamically and forgets the rotation factor allocates a fraction of what it needs,
which is the failure mode on the other side of this rule and which upstream never names.

The segments the rule applies to, `:348-356`, are five classes: the cross-core handshake segments
carrying the `[Bq, Bk]` score matrix, the `[Bq, Bk]` `P` matrix and the `[Bq, D]` `P·V` intermediate;
the cross-loop self-read/self-write segment holding `O_acc` when streaming (`0456`); the task-level
state segment holding softmax `max`/`sum`/`exp`; subfamily extension segments (MLA's int32
intermediate); and parallel-strategy extension segments (split-KV reduce's three partial segments,
`0454`). Their `Sk` dependence differs: the handshake segments scale with `Bk` and the slot count, not
with `Sk` directly; the split-KV partial segments scale with the number of slices, which is a function
of `Sk`. Upstream's one worked expression has `Sk_max` appearing directly, which is the case for a
segment holding one row per KV position — so the example is *a* segment shape and the rule is stated
over all five.

Two locations in one repository are one origin (RULES.md Art. 3).

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind on three consecutive idle samples only; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample afterwards and
discard the case if the die moved.

**Arm 1 — the figure, re-derived rather than inherited.** Build the operator with both sizing policies
behind a switch. For `Sk_max = 32768` and `Sk ∈ {512, 2048, 8192, 32768}` at fixed
`(B, Hq, Bq, sizeof(elem))`, echo from the host, per segment: the byte count each policy computes, the
slot count, and the total. Report the static total at the declared shape and compare it against
upstream's "hundreds of MB". This is arithmetic on echoed values, not a memory measurement, and §5
names it as such.

**Arm 2 — the cap, which is the half a benchmark cannot see.** With the static policy, increase `Sk`
past `Sk_max` and record the failure: where it is raised (host or device), what it says, and whether
it names `Sk_max`. With the dynamic policy, run the same `Sk` and record success or the true limit.
The claim "限制用户上限" is tested by finding the limit, not by observing that memory is large.

**Arm 3 — the cost of being dynamic, which upstream never states.** Measure end-to-end launch time for
the dynamic policy versus the static policy re-used across launches, over 200 consecutive launches at
fixed `Sk`, with the allocation inside the timed region and then outside it. Upstream's rule is
unconditional; this arm is where an allocation cost, if any, would appear. A dynamic policy that costs
measurably more per launch would scope the rule rather than break it, and §5 declares that outcome
before the run.

**Arm 4 — the rotation factor, retained because it may not bite.** With the dynamic policy, set the
slot counts to their design values and to one, and confirm the computed segment size scales with the
slot count. If it does not, the implementation's dynamic sizing ignores rotation, which is the
under-allocation failure §3 names and which arm 1's arithmetic would not reveal.

Refuses to assume: that a free die stays free, or that a die may be substituted; that the host's
computed workspace size is the size actually allocated (the caller's allocation is echoed too); that
"hundreds of MB" is a measurement (arm 1 re-derives it from the formula and the echoed shape); that
running out of workspace produces a diagnosable error (arm 2 records whatever it produces); that
allocation is free (arm 3 exists because it may not be).

## 5 · Checker — acceptance declared before the run
Verdict `static_total_bytes(shape)` and `dynamic_total_bytes(shape, Sk)`, both echoed sums over the
five segment classes, declared before the run. Acceptance for upstream's figure: at some ordinary
inference shape with `Sk_max = 32768`, `static_total_bytes ≥ 100 MiB`. Reported as arithmetic over
echoed host values — **not** as a measurement of device memory, which this procedure does not make.

Verdict `waste_ratio(Sk) = static_total_bytes / dynamic_total_bytes(Sk)`, which is the quantity the
rule is actually about, and which upstream never states.

Verdict `cap_is_real` from arm 2 ∈ {`fails_at_Sk_max`, `fails_earlier`, `no_cap`}. `no_cap` would mean
the static policy does not limit the user in this implementation, and the second half of upstream's
justification would not apply.

Verdict `dynamic_launch_overhead` from arm 3, with its variance floor. The OVERTURN's first half fires
iff this exceeds the floor and is a material fraction of launch time — declared now as ≥5% of median
end-to-end launch time, stated before the readout exists.

The exit code is not the verdict: both policies produce correct output, and the static one is *more*
robust in the region it covers. Guards: (1) every byte figure is echoed from the host and re-derived by
the checker from the shape and the formula independently, and the checker fails red if the two
disagree — an implementation whose `GetXxxWorkspaceSize` does not match its own documented formula is
a finding, and a checker that only read the echo could not see it; (2) **the input that makes this
checker go red**: `Sk == Sk_max`, where the two policies must compute the *same* size — if
`waste_ratio(Sk_max) ≠ 1`, the two policies differ in more than their `Sk` source and every ratio in
the sweep is an artifact; (3) no figure is reported without its shape, its `sizeof(elem)`, its slot
counts, and the CANN pin.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The rule, the host API shape,
the worked expression, the "hundreds of MB" figure, the five-class segment roster and the checklist
line are file reads performed at drafting time. The arithmetic in §3 — that the formula gives 64 KiB
per `B × Hq × Bq` unit at `Sk_max = 32K` and FP16, so hundreds of megabytes implies a few thousand
units — is a calculation over upstream's own expression, not a measurement of any allocation, and it
is shown so that §4 can re-derive rather than inherit it. The observation that the expression omits
the rotation slot count is a reading of upstream's own line.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured, compiled or allocated. The entry does not establish the hundreds-of-megabytes
figure — upstream states it with no shape attached and §3's reconstruction shows only that some
ordinary shape would produce it, not that it was the shape upstream used. It does not establish that
dynamic sizing is free; upstream's rule is unconditional and its cost is unstated, which is what §4
arm 3 exists for. It does not establish which of the five segment classes actually scale with `Sk` —
upstream states the rule over all of them and works only one. It does not establish that the static
form caps the user, only that upstream says so. It does not cover the workspace *contents* or their
slot rotation, which are `0453`'s material, nor the split-KV-reduce partial segments beyond naming
them. It says nothing about whether the caller's allocator can satisfy a per-launch request of the
sizes involved. No board token appears in the quoted passages, so BOARD is
`family-claimed(unverified)`; §4 names 950PR/950DT only as where our run would happen. Nothing here is
established for any 910-family board.
