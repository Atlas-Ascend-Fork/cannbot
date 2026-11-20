```
ID:        0061-flagid-is-four-bits-so-a-core-has-sixteen-and-two-subsystems-reserve-ranges-inside-them
LABEL:     trap
LEVEL:     L4 (synchronisation)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-api-best-practices/references/api-crosscore-sync.md:113 — "| 数量上限 | 模式 0/1/2 每核仅 **16 个 flagId（0-15）**，超出**截断低 4bit** |"; ibid:116 — "| 保留区间 | **SyncAll 硬同步内部占用 flagId [11-14]**；Matmul 高阶 API 占用 flagId [0, 2N-1]（最多 [0,7]）|"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a `flagId` of 16 or above is shown to address a distinct flag on a named DAV_2201 board — i.e. the field is wider than 4 bits and does not truncate.
```

# 0061 · flagId is four bits, so a core has sixteen — and two subsystems reserve ranges inside them

## 1 · Claim
Upstream asserts that under cross-core sync modes 0/1/2 each core has only 16 `flagId` values
(0–15), and that a value above 15 is **truncated to its low 4 bits**. Upstream asserts the
truncation is symmetric, so `Set` and `Wait` given the same out-of-range value still pair — and
that this is the hardware basis on which passing an unbounded index (a tile id) as a `flagId`
works at all. Upstream asserts two reservations inside those sixteen: `SyncAll` hard
synchronisation occupies [11–14], and the Matmul high-level API occupies [0, 2N−1], at most [0,7].
Upstream asserts that the hardware does **not** guarantee execution order between consecutive
`CrossCoreSetFlag` calls from one core. Not established here.

## 2 · The wrong branch this removes
Truncation without error is the trap, and the reservations make it bite.

An agent uses a loop index or a tile id as its `flagId` — which upstream explicitly says works, and
it does, as long as nothing else is using flags. Add a `SyncAll` anywhere in the kernel, or a
Matmul high-level API call, and the agent's flag 27 (truncating to 11) collides with `SyncAll`'s
reserved range. The collision is not detected: both parties set and wait on the same counter, the
counts interleave, and a `Wait` consumes a signal meant for the other subsystem. Upstream's own
words for a mispaired Set/Wait are "未定义行为/异常中断".

Three properties make this hard to find without the entry:
1. Nothing rejects the out-of-range value, so no error names the cause.
2. The colliding party may be *inside a library call* the agent did not write, so its flag usage is
   invisible in the source.
3. The reservation ranges overlap the natural choices: [0,7] is where a human starts counting and
   [11,14] is inside where a truncated index lands.

The ordering clause closes a fourth branch: an agent that issues two `CrossCoreSetFlag` calls and
relies on the first arriving first has no such guarantee.

Note the reading this corrects. `ascendc-performance-analysis/references/metrics_reference.md:448`
says "同一 flagId 计数器最多设置 15 次" — which reads as "a flagId may be set at most 15 times".
This file's line 115 says each flagId **has a counter with range 0–15** and each `Wait` consumes
one. Those are compatible (a 4-bit counter saturating or wrapping at 16 outstanding signals) but
the first phrasing invites an agent to think it may only ever use a flag fifteen times in the
kernel's life, which is a different and much more restrictive belief.

## 3 · Ground / Source
`ops/ascendc-api-best-practices/references/api-crosscore-sync.md` §3 flagId 硬件规则, lines 111-119,
verbatim in full:
```
| 规则 | 说明 |
| 数量上限 | 模式 0/1/2 每核仅 **16 个 flagId（0-15）**，超出**截断低 4bit** |
| 截断复用 | Set/Wait 双方传入超出 15 的值时截断到同一 flag，配对保持——这是直接用无界索引（如 tile id）作 flagId 能工作的硬件基础 |
| 计数器语义 | 每个 flagId 对应一个计数器（0-15），Wait 消耗一次计数；Set/Wait 必须配对，否则未定义行为/异常中断 |
| 保留区间 | **SyncAll 硬同步内部占用 flagId [11-14]**；Matmul 高阶 API 占用 flagId [0, 2N-1]（最多 [0,7]）|
| 混用风险 | 官方不建议同时使用 CrossCoreSetFlag 与 SyncAll 硬同步；组合使用时，自定义 flagId 落入 [11,14]（截断后）存在冲突风险 |
| 发射顺序 | 同一核连续发出的 CrossCoreSetFlag，硬件**不保证执行顺序**——不要依赖 per-flag 的先后次序 |
```
The parameter's declared width, line 45: "| `flagId` | `uint16_t` | flag 标识符（硬件规则见 §3）|" —
so a 16-bit parameter feeding a 4-bit field. That gap is the truncation.
The `SyncAll` note restated at line 82: "SyncAll 硬同步内部占用 flagId [11-14]（见 §3），官方不建议
与 CrossCoreSetFlag 混用".

The other statement of the counter limit, same repo (one origin):
`ops/ascendc-performance-analysis/references/metrics_reference.md:448` — "- 同一 flagId 计数器最多
设置 15 次", under the heading "### 8.2 核间同步（Atlas A2/A3）" at line 438.

Note this section's mode scoping: the sixteen-flag limit is stated for "模式 0/1/2", and 0060 records
that on DAV_2201 the mode selector is inert — so on this family the limit applies to whatever the
one effective behaviour is. The interaction is not addressed by upstream.

Related: `harvest/claims/ascendc-performance-analysis--001-...md` holds the intra-core `TEventID`
reservations (6 and 7 system-reserved), which are a different resource with the same shape of
hazard and were not entry-ready.

## 4 · Procedure
Proposed, runnable later; not run.

1. Name the die; occupancy before and after; no substitution.
2. Truncation arm: `Set(id)` / `Wait(id & 0xF)` for `id` in {3, 19, 35, 51} — all truncating to 3.
   If truncation holds, every pair completes. Then the asymmetric probe: `Set(19)` / `Wait(4)`,
   which must NOT pair. A procedure that only shows matching pairs completing cannot distinguish
   truncation from a 16-bit field, since matching values pair under both.
3. Collision arm, the substance: a kernel using `flagId = 27` (→ 11) alongside a `SyncAll`, against
   a control using `flagId = 9` (outside both reserved ranges) with the same `SyncAll`. Verify every
   output element and report mismatch counts across launch counts 1, 10, 200 — per 0019 and 0029,
   this class of defect accumulates across launches and a single run may be clean.
4. Ordering arm: two consecutive `CrossCoreSetFlag` calls on distinct flags, with the consumer
   waiting on the second then the first, repeated 1000 times; count how often the order assumption
   fails.
5. Wall-clock timeout on every arm, since the failure mode is a hang as readily as a wrong answer.

## 5 · Checker — acceptance declared before the run
`truncates`: PASS iff every matching-after-truncation pair completes AND the asymmetric pair
(`Set(19)`/`Wait(4)`) times out. Both clauses required, for the reason in §4 step 2.
`collision_mismatches(launches)`: the claim is upheld iff the `flagId = 27` arm shows mismatches or
a hang at some launch count while the `flagId = 9` control shows none at every launch count.
A clean result in both arms does NOT establish safety — it establishes that this workload did not
collide in this many launches, and is recorded as "did not bite, retained". Declared now so a clean
sweep cannot later be narrated as an overturn of the reservation claim.
`order_violations`: reported as a count with no declared threshold; the claim is that no guarantee
exists, and any non-zero count confirms it while zero does not refute it.
Positive fixture for arm 3: run the `flagId = 9` control with a deliberately unpaired `Set` and
confirm the verification loop reports the resulting corruption or hang. A loop that reports clean on
a deliberately broken pairing cannot certify the collision arm.
Exit code is not the verdict; a hang produces no exit code at all, which is why the timeout is
declared as an outcome.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; no board touched; the source names an architecture, not a board. This entry does
not establish the value of N in the Matmul reservation [0, 2N−1] for any given call — upstream
bounds it at [0,7] and does not say what sets it. It does not establish whether the counter
saturates or wraps at 16 outstanding signals, which decides whether an over-set flag loses signals
silently or blocks. It does not resolve how the sixteen-flag limit interacts with the inert mode
selector of 0060. It does not cover intra-core `TEventID` reservations, which are a separate
resource (see the claim-card). The reservation ranges are upstream's assertion about library
internals and could change with any CANN release; no toolkit version is pinned because upstream
pins none.
