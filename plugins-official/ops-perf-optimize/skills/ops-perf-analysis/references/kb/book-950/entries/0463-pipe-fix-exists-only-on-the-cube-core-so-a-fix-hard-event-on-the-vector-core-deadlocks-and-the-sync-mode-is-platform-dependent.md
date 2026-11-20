```
ID:        0463-pipe-fix-exists-only-on-the-cube-core-so-a-fix-hard-event-on-the-vector-core-deadlocks-and-the-sync-mode-is-platform-dependent
LABEL:     trap
LEVEL:     L4 (synchronisation)
STRATUM:   corroborated — upstream's skills repo (one origin) plus the installed CANN toolchain at pin
           cann-9.0.0-beta.2 (independent origin: headers in the installed toolkit, STRATA S2), which
           carries the same directional pipe assignment as a template default. Nothing measured,
           nothing compiled. The corroboration covers the pipe assignment only, not the deadlock
           claim, not the mode recommendation and not the queue-wrapper rule.
BOARD:     family-claimed(unverified)
SOURCE:    /usr/local/Ascend/cann-9.0.0-beta.2/asc/include/interface/kernel_operator_common_intf.h:43-48
           — "#if defined(__NPU_ARCH__) && (__NPU_ARCH__ != 1001) && (__NPU_ARCH__ != 2002) /
           template<pipe_t AIV_PIPE = PIPE_MTE3, pipe_t AIC_PIPE = PIPE_FIX> / #else /
           template<pipe_t AIV_PIPE = PIPE_MTE3, pipe_t AIC_PIPE = PIPE_MTE3> / #endif /
           __aicore__ inline void SetNextTaskStart();"
SOURCE:    same toolkit, arm64-linux/ccec_compiler/lib/clang/15.0.5/include/cce_aicore_intrinsics_3510.h:406
           — "PIPE_FIX = 10,     // {L0C} ->{L1,UB,L1UB}"
SOURCE:    ops/ascendc-tiling-design/references/flashattention/design.md:519-536 —
           "跨核同步原语:`CrossCoreSetFlag<mode, PIPE>` / `CrossCoreWaitFlag(id)`。 /
           - **mode**:平台相关(A2/A3 用 mode=2;A5 推荐 mode=4 + AIV1 早返回;详见 `/npu-arch`
           平台 API 版本表) / - **PIPE 类型**:AIC → AIV 用 `PIPE_FIX`(Fixpipe 完成后通知);
           AIV → AIC 用 `PIPE_MTE3`(GM 写完后通知) / - **PIPE_FIX 仅 AIC 有**:AIV 端无 PIPE_FIX,
           `HardEvent::FIX_*` 在 AIV 端无效,会死锁(用 cross-core sync 取代)" ·
           "- [ ] `mode=2 CrossCoreSetFlag` 是 fire-and-forget,不阻塞后续操作 → 不能依赖它做
           back-pressure" · "- [ ] GM 自读自写段经输出 queue 包装写出(`AllocTensor → DataCopy →
           EnQue → DeQue → DataCopy → FreeTensor`)+ 配合 `MTE3_MTE2` fence,**禁止**直接
           `DataCopy(GM 自读自写段, LocalTensor)` 不经 queue 包装(无 MTE3 同步事件 → 多 s2 时上一轮
           内容未落盘 → 周期性 chunk 错位)"
SOURCE:    same file:617 — "- A5 平台 mode=4 同步基座(若目标平台为 A5):
           `asc-devkit/examples/01_simd_cpp_api/05_compatibility_guide/matmul_s4/matmul_s4.asc`"
INDEX:     none — nothing measured; see SOURCE. The second origin is re-derivable by file read
           (no device):
           grep -n 'AIC_PIPE = PIPE_FIX' /usr/local/Ascend/cann-9.0.0-beta.2/asc/include/interface/kernel_operator_common_intf.h
           grep -n 'PIPE_FIX = ' /usr/local/Ascend/cann-9.0.0-beta.2/arm64-linux/ccec_compiler/lib/clang/15.0.5/include/cce_aicore_intrinsics_3510.h
OVERTURN:  a `HardEvent::FIX_*` wait issued on a vector core of a named 950 board that returns rather
           than hanging — `PIPE_FIX` would then exist or be harmlessly ignored on that core, and the
           deadlock claim would be wrong. Equally: a `mode=2` cross-core set flag on a 950 board that
           does block the setter would falsify the fire-and-forget property the back-pressure warning
           rests on, and a `mode=4` build that is not faster than `mode=2` on 950 would leave the
           platform recommendation without a measured basis.
```

# 0463 · PIPE_FIX exists only on the cube core, so a FIX hard event on the vector core deadlocks, and the sync mode is platform-dependent

## 1 · Claim
Upstream asserts that cross-core synchronisation in a mixed AIC/AIV FlashAttention kernel uses
`CrossCoreSetFlag<mode, PIPE>` and `CrossCoreWaitFlag(id)`, and that the `PIPE` argument is fixed by
direction: cube-to-vector signals on `PIPE_FIX`, after Fixpipe completes; vector-to-cube signals on
`PIPE_MTE3`, after the GM write completes. Upstream asserts that `PIPE_FIX` exists only on the cube
core, that a `HardEvent::FIX_*` on the vector core is therefore invalid and hangs, and that cross-core
synchronisation must be used in its place. Upstream asserts the `mode` argument is platform-dependent:
`mode=2` on A2/A3, and `mode=4` plus an early return on the second vector core recommended on A5.
Upstream asserts `mode=2`'s set-flag is fire-and-forget and does not block the setter, so it cannot
carry back-pressure. Upstream asserts that a GM self-read/self-write segment must be written through
an output queue with an `MTE3_MTE2` fence, and that writing it with a bare `DataCopy` leaves the
previous round unflushed and produces periodic chunk misalignment when there are several KV blocks.
Not established here.

## 2 · The wrong branch this removes
Without this entry an agent synchronising two core types reaches for the primitive it already knows.
Within one core, `SetFlag`/`WaitFlag` on a `HardEvent` is the standard Ascend C idiom and it is
correct; the natural generalisation is to use a `HardEvent` naming the producing pipe. For the
cube-to-vector direction the producing pipe is Fixpipe, so `HardEvent::FIX_*` is the obvious choice —
and upstream says the vector core has no such pipe, so the wait never retires. A hang is the least
diagnosable failure in this operator: there is no output to compare, no error code, and both core
types are involved.

The second wrong branch is back-pressure. Having a flag primitive in hand, an agent naturally uses it
to throttle: set the flag, and let the setter block until the consumer takes it. Upstream says
`mode=2`'s set does not block, so a producer written that way runs ahead and overwrites the buffer the
consumer has not read — a data race whose symptom is wrong values under load and correct values under
a debugger.

The third wrong branch is the one the checklist item names, and it is the subtlest: writing the GM
self-read/self-write segment with a bare `DataCopy` instead of through the queue. The write happens.
The data is correct. What is missing is the `MTE3` synchronisation event that the queue wrapper
generates, so the *next* round reads the segment before the previous round's write has landed.
Upstream's symptom — `周期性 chunk 错位`, periodic chunk misalignment — is a per-round pattern, and it
appears only with several KV blocks, which is the same multi-block precondition that `0453` and `0458`
require. Three distinct defects in this family share one reproduction shape, and an agent that finds
`s2N ≥ 3` failing has three candidates, not one.

## 3 · Ground / Source
The primitives and their directional pipes, `references/flashattention/design.md:519-527`:

```
### §7.2 跨核同步原语选择

回答:**AIC↔AIV 跨核同步用哪种 mode?PIPE 类型选什么?**

跨核同步原语:`CrossCoreSetFlag<mode, PIPE>` / `CrossCoreWaitFlag(id)`。

- **mode**:平台相关(A2/A3 用 mode=2;A5 推荐 mode=4 + AIV1 早返回;详见 `/npu-arch` 平台 API 版本表)
- **PIPE 类型**:AIC → AIV 用 `PIPE_FIX`(Fixpipe 完成后通知);AIV → AIC 用 `PIPE_MTE3`(GM 写完后通知)
- **PIPE_FIX 仅 AIC 有**:AIV 端无 PIPE_FIX,`HardEvent::FIX_*` 在 AIV 端无效,会死锁(用 cross-core sync 取代)
```

The `mode` line is one of the four places the FA family names a platform, and it is the only one that
attaches a *behavioural difference* to the name. `A2/A3 用 mode=2;A5 推荐 mode=4 + AIV1 早返回` — and
per this book's vocabulary map, A5 is the 950 family, A2/A3 the 910 family. So this single line is the
family's one genuine dual-architecture statement, and the two halves belong to two different books
(RULES.md Art. 1). This entry carries the A5 half and nothing else; the A2/A3 half is not this book's and is
not restated here even as context for comparison.

Note also that the two halves are not parallel in force. `用` for A2/A3 — use. `推荐` for A5 —
recommended. So `mode=4` is a recommendation with a companion condition (`AIV1 早返回`, the second
vector core returning early) and no stated consequence for using `mode=2` on A5 instead. Whether
`mode=2` is wrong there, slower there, or merely not the newest idiom, upstream does not say, and it
defers to `/npu-arch`'s platform API version table for the detail. Recorded as `Q-950fin-12`. The
baseline-verification section reinforces that `mode=4` is A5-specific by naming a separate example to
compile first when the target is A5 (`:617`).

The seven-item cross-core timing checklist, `:529-536`, carries the other three claims. Two are
ordering rules that read as obvious and are the ones people invert (`AIV → AIC 的 CrossCoreSetFlag 在
数据写完之后`; `AIC → AIV 的 CrossCoreWaitFlag 在数据读取之前`). One separates the two families of
primitive (`同核内的 PIPE 同步用 SetFlag/WaitFlag,跨核用 CrossCoreSetFlag/WaitFlag,不混用`). Then:

```
- [ ] `mode=2 CrossCoreSetFlag` 是 fire-and-forget,不阻塞后续操作 → 不能依赖它做 back-pressure
- [ ] GM 自读自写段经输出 queue 包装写出(`AllocTensor → DataCopy → EnQue → DeQue → DataCopy → FreeTensor`)+ 配合 `MTE3_MTE2` fence,**禁止**直接 `DataCopy(GM 自读自写段, LocalTensor)` 不经 queue 包装(无 MTE3 同步事件 → 多 s2 时上一轮内容未落盘 → 周期性 chunk 错位)
- [ ] 跨阶段依赖(MTE2↔MTE1、M↔FIX 等)用对应 `HardEvent`,不用 `PipeBarrier` 替代
```

The queue-wrapper item is the most operational line in the family: it names the six-call sequence
exactly, names the fence, names the forbidden shortcut, gives the mechanism (`无 MTE3 同步事件`) and
gives the symptom. Note that the fire-and-forget property is asserted for `mode=2` only, and the A5
recommendation is `mode=4`; whether `mode=4` blocks is not stated, so the back-pressure warning's
scope on this book's boards is unknown. Recorded as `C-950fin-008` — a property stated for the mode
this book does not use, in the document that tells this book to use another.

The last item points forward to `0464`: hard events for cross-stage dependencies, not `PipeBarrier`.

Upstream's files are one repository and therefore one origin (RULES.md Art. 3); the `/npu-arch` platform
table it defers to is another skill in the same repository, so it does not add an origin either.

**The second origin.** The installed CANN toolchain at pin `cann-9.0.0-beta.2` carries the same
directional pipe assignment, independently, as a template default in a public interface header —
`asc/include/interface/kernel_operator_common_intf.h:43-48`:

```cpp
#if defined(__NPU_ARCH__) && (__NPU_ARCH__ != 1001) && (__NPU_ARCH__ != 2002)
template<pipe_t AIV_PIPE = PIPE_MTE3, pipe_t AIC_PIPE = PIPE_FIX>
#else
template<pipe_t AIV_PIPE = PIPE_MTE3, pipe_t AIC_PIPE = PIPE_MTE3>
#endif
__aicore__ inline void SetNextTaskStart();
```

The API is `SetNextTaskStart` — a super-kernel fusion flag between two operators, per the comment two
lines above it — not the FlashAttention family's `CrossCoreSetFlag`. What corroborates is the
*assignment*: the vector side's notify pipe defaults to `PIPE_MTE3` and the cube side's to `PIPE_FIX`,
exactly as upstream's `AIC → AIV 用 PIPE_FIX` / `AIV → AIC 用 PIPE_MTE3` states, in a different
authority that did not copy this document.

Two further things fall out of the same lines, and neither is in upstream's text. First, the
assignment is **architecture-gated**: on `__NPU_ARCH__` 1001 and 2002 the cube-side default is
`PIPE_MTE3`, not `PIPE_FIX`. So "cube signals on Fixpipe" is not universal even inside this
toolchain — it is the default everywhere *except* two older architecture values. Neither excluded
value is DAV_3510, so the `PIPE_FIX` branch is the one this book's boards take, which is why this entry
carries it. Second, the gate spells the architecture as `__NPU_ARCH__ == <number>`, and the numbers it
excludes (1001, 2002) are not in this book's vocabulary map (`form/CONVENTIONS.md` gives 2201 for
DAV_2201 and 3510 for DAV_3510). Two architecture identifiers used by the shipped toolchain are
unmapped by our own convention table; recorded as `C-950fin-009` alongside the existing
identifier-system entries `0203` and `0421`.

The pipe's own definition, in the 3510-specific compiler intrinsics header
(`arm64-linux/ccec_compiler/lib/clang/15.0.5/include/cce_aicore_intrinsics_3510.h:406`), describes it
by its source and destinations rather than by its core:

```c
  PIPE_FIX = 10,     // {L0C} ->{L1,UB,L1UB}
```

`L0C` is the cube accumulator. A pipe whose source is L0C is a pipe the vector core has no source for,
which is consistent with upstream's restriction — but consistency is not proof, and the header does
not say the vector core lacks the pipe. §7 keeps that distinction.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind on three consecutive idle samples only; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and
discard the case if the die moved. Every arm that can hang carries a hard timeout, and a timeout is
recorded as an outcome, never discarded as infrastructure noise.

**Arm 1 — the missing pipe, isolated.** Two minimal kernels, not FlashAttention: one issuing a
`HardEvent::FIX_*` wait on the cube core (control, must retire), one issuing the same on the vector
core (must hang, per upstream). Report retirement or timeout. This is the cheapest possible test of the
family's most expensive failure mode, and it needs no attention operator at all.

**Arm 2 — the mode, on this book's boards.** One GQA kernel built with `mode=2` and with
`mode=4 + AIV1 early return`, otherwise identical, across prefill and decode shapes. Report
correctness, `aic_time`, `aiv_time` and the cross-core wait time for each. `Q-950fin-12` asks what
`mode=2` costs on 950; this arm answers it, and a `mode=2` build that is correct and not slower would
mean the recommendation is a style preference on this board.

**Arm 3 — back-pressure.** With `mode=2`, a producer deliberately running ahead of its consumer by
`k` rounds for `k ∈ {1, 2, 4}` on a segment with 2 slots. Report the disagreeing-run fraction over ≥20
repetitions. Then repeat with `mode=4` — which is where `C-950fin-008` is resolved: if `mode=4` blocks
the setter, the race does not reproduce and the back-pressure warning does not apply to the mode this
book uses.

**Arm 4 — the queue wrapper.** Two builds of the self-read/self-write path: the six-call queue sequence
with the `MTE3_MTE2` fence, and a bare `DataCopy`. Sweep `s2N ∈ {1, 2, 3, 8}`, report per-round
agreement and the *round index* of the first disagreement. Upstream's symptom is periodic; a periodic
error is confirmed by its period, not by its magnitude, so the per-round index is the datum.

Refuses to assume: that a free die stays free, or that a die may be substituted; that a hang is a bug
in the harness (arm 1 exists to make a hang a *result*); that `mode` values are interchangeable across
architectures — the A2/A3 half of upstream's line belongs to the other book and is not tested here,
and no 910 result would be evidence for these boards or the reverse (RULES.md Art. 1); that a race
reproduces on one run (arms 3 and 4 report fractions over ≥20 repetitions); that correct output means
correct synchronisation (arm 3's whole point is that it can be correct under a debugger).

## 5 · Checker — acceptance declared before the run
Verdict `fix_event_retires(core)` from arm 1, boolean per core type, declared before the run.
Acceptance: `true` on cube, `false` (timeout) on vector. The OVERTURN's first half fires iff the vector
core's wait retires.

Verdict `mode_delta = median(t, mode=2) − median(t, mode=4)` from arm 2, with the variance floor, plus
`mode2_correct` boolean. A `mode2_correct == true` with `|mode_delta| < floor` is recorded as
"recommendation not measurable at these shapes", which is a finding, not a pass.

Verdict `race_fraction(mode, k)` from arm 3. The OVERTURN's second half fires iff
`race_fraction(2, k) == 0` for all `k` — the fire-and-forget property would then not produce the race
it is warned about.

Verdict `first_bad_round(s2N)` from arm 4 and its period. Acceptance for the queue-wrapper claim: the
bare build disagrees from some round onward with a detectable period, while the wrapped build agrees at
every round.

The exit code is not the verdict: arm 1's expected outcome is a timeout, which most harnesses score as
infrastructure failure, and arm 3's defect is intermittent by construction. Guards: (1) a timeout is
classified as `deadlock` only when the paired control arm retires on the same build and the same die,
otherwise it is `untestable` — this prevents a hung machine from being read as a confirmed claim; (2)
**the input that makes this checker go red**: arm 1's cube-core control, which must retire — if it
times out, the harness cannot observe retirement at all and the vector-core timeout carries no
information; (3) no arm is reported without its repetition count, its timeout value, its mode, its
`s2N`, the CANN pin and the compiler command.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The primitives, the directional
pipe assignment, the `PIPE_FIX` restriction with its deadlock consequence, the platform-dependent mode
line, the fire-and-forget property, the six-call queue sequence with its fence and symptom, and the A5
baseline example are file reads performed at drafting time. The observations that `用` and `推荐` are
different modalities, and that the fire-and-forget property is asserted only for the mode this book
does not use, are readings of upstream's own lines, not observations of a build.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured, compiled or run. The entry does not establish that `PIPE_FIX` is absent from the
vector core. The second origin corroborates the *directional pipe assignment* and shows that `PIPE_FIX`
is defined as an L0C-sourced move; it does not state that the vector core lacks the pipe, and an
absence is not shown by a definition that happens to name a cube-side source. The deadlock claim
therefore rests on upstream alone, and §4 arm 1 is what would settle it. It does not establish that
`mode=4`
is better than `mode=2` on any 950 board: upstream writes `推荐`, gives no measurement, and defers to a
platform table not quoted here (`Q-950fin-12`). It does not establish what `AIV1 早返回` requires or
costs. It does not establish that `mode=2` is fire-and-forget on these boards, nor whether `mode=4` is
(`C-950fin-008`). It does not establish the queue wrapper's necessity, only that upstream forbids the
shortcut and names a mechanism and a symptom. **It carries only the A5 half of upstream's
platform-dependent mode line; the A2/A3 half is book-910 material and nothing here is established for
any 910-family board (RULES.md Art. 1).** `A5` names a family rather than a board, so BOARD is
`family-claimed(unverified)`; §4 names 950PR/950DT only as where our run would happen. It says nothing
about synchronisation under the split-KV-reduce strategy, whose combine stage introduces a cross-core
dependency the default strategy does not have (`0454`).
