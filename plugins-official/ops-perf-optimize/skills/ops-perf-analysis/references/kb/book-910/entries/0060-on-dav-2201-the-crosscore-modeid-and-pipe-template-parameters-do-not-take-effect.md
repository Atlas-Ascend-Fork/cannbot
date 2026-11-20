```
ID:        0060-on-dav-2201-the-crosscore-modeid-and-pipe-template-parameters-do-not-take-effect
LABEL:     trap
LEVEL:     L4 (synchronisation)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-api-best-practices/references/api-crosscore-sync.md:127 — "| **A3 / 910b（DAV_2201）** | **不生效**——CrossCoreWaitFlag 阻塞全部流水 | 参数无实际作用 |"; ibid:56 — "A3/910b 上该模板参数不生效，实践中存在 Set 0x2 / Wait 默认 0 的配对"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  on a named DAV_2201 board, a `CrossCoreWaitFlag<mode, PIPE_V>` is shown to block only the named pipe while another pipe continues — i.e. the template parameter does take effect.
```

# 0060 · On DAV_2201 the CrossCore modeId and pipe template parameters do not take effect

## 1 · Claim
Upstream asserts that on DAV_2201 (which it writes "A3 / 910b") the `modeId` and `pipe` template
parameters of `CrossCoreSetFlag` / `CrossCoreWaitFlag` **do not take effect**, that
`CrossCoreWaitFlag` blocks every pipeline regardless, and that the parameters have no actual
function. Upstream asserts the same architecture accepts mismatched pairs in practice — a `Set`
with `0x2` against a `Wait` with the default 0 — precisely because the parameter is inert.
Upstream asserts that on DAV_3510 the parameters DO take effect and carry constraints. Not
established here.

## 2 · The wrong branch this removes
Two branches, in opposite directions, and this entry is the reconciliation the book was missing.

**Forward:** an agent writes `CrossCoreWaitFlag<0x2, PIPE_S>(id)` on a 910 part expecting a
*scoped* wait — one pipe stalls, the others carry on — and designs an overlap around it. Every pipe
stalls. The code is correct, the synchronisation works, and the overlap the design depended on
does not exist. This is the same shape as 0042 (TBuf's `PipeBarrier<PIPE_ALL>` stopping everything),
from a different API, and it explains *why* fine-grained cross-core overlap is hard to obtain on
this family.

**Backward, and worse:** a pattern that works on A3 works *because* the parameter is inert.
Upstream says so outright — "在 A3 上能运行的 `CrossCoreWaitFlag<0x2, PIPE_S>(id)` 写法依赖'A3 参数
不生效'的硬件行为" — and on DAV_3510 modes 0/1/2 do not support `PIPE_S` at all. So the 910-working
code is *illegal* on 950 and its legality on 910 is an accident. A port that compiles is not a port
that is correct.

The third thing this entry buys: it **reconciles C-910-009**. `radix_sort.md` says "A2 无硬件
barrier" and `metrics_reference.md` documents a three-mode `CrossCore*` API for Atlas A2/A3. Both
are true under this entry: the flags exist, and the wait blocks all pipes — so there is no
*fine-grained* cross-core barrier on A2, which is what an author seeking MTE2/Vector overlap would
call "no hardware barrier". That reading is an inference drawn here, not an upstream statement, and
it is marked as such in §7.

## 3 · Ground / Source
`ops/ascendc-api-best-practices/references/api-crosscore-sync.md` §4 平台生效性差异, lines 124-129,
verbatim in full:
```
| 平台 | modeId/pipe 模板参数 | pipe 约束 |
| **A3 / 910b（DAV_2201）** | **不生效**——CrossCoreWaitFlag 阻塞全部流水 | 参数无实际作用 |
| **950（DAV_3510）** | 生效 | 模式 0/1/2 **不支持 `PIPE_S`/`PIPE_ALL`**；`PIPE_S` 仅模式 4 支持 |
```
line 131: "**移植要点**：在 A3 上能运行的 `CrossCoreWaitFlag<0x2, PIPE_S>(id)` 写法依赖\"A3 参数
不生效\"的硬件行为；迁到 950 时模式 0/1/2 下 `PIPE_S` 违反官方约束，需改为合法 pipe。"
line 56, in the `CrossCoreWaitFlag` parameter table: "| `modeId` | `uint8_t` | 建议与 SetFlag 的
modeId 一致（A3/910b 上该模板参数不生效，实践中存在 Set 0x2 / Wait 默认 0 的配对） |"

The mode semantics, lines 98-103 — all three of which the table marks as available on 950/A3/A2:
```
| `0` | AI Core 核间同步（AIC 调用时同步所有 AIC；AIV 调用时同步所有 AIV） | 950/A3/A2 |
| `1` | AI Core 内部两个 AIV 之间的同步 | 950/A3/A2 |
| `2`（`0x2`） | 同核 AIC 与所有 AIV 之间的同步 | 950/A3/A2 |
| `4`（`INTRA_MODE`） | AscendC Matmul 高阶 API 内部使用 | 仅 950，且要求 `KERNEL_TYPE_MIX_AIC_1_2` |
```
So the modes are *documented as available* on A2/A3 and the parameter selecting them is
*documented as inert* on A2/A3, in one file eighty lines apart. That is not a contradiction — an
inert selector with a fixed effective behaviour is coherent — but it is the kind of pair a reader
will not reconcile unless both lines are in front of them, which is why both are quoted here.

"910b" is a fourth spelling again (cf. 0014 §3's "220x"); the parenthetical "（DAV_2201）" settles
the intent in this file.

Same repo as `metrics_reference.md` §8.2 and `radix_sort.md` §5: one origin (STRATA S2), three
files. See `harvest/contradictions-910.md` C-910-009.

## 4 · Procedure
Proposed, runnable later; not run.

1. Name the die; occupancy before and after; no substitution. Record `GetCoreNumAic/Aiv()`.
2. Three arms, one binary, template parameters varied by build (md5-confirmed to differ only there):
   - Arm S: `CrossCoreWaitFlag<0, PIPE_S>` — the pipe the parameter names.
   - Arm V: `CrossCoreWaitFlag<0, PIPE_V>` — a different pipe.
   - Arm M: `CrossCoreWaitFlag<0x2, PIPE_S>` against a `Set` with the default mode, i.e. the
     mismatched pairing upstream says works on this family.
3. Each arm places independent work on a pipe the parameter does NOT name, positioned so that it
   could proceed during the wait if the wait were scoped. Collect the Chrome trace
   (`--aic-metrics=TimelineDetail`) and the per-pipe times.
4. The observable is whether the independent work overlaps the wait. Arm S and arm V must be
   compared against each other, not against a no-wait baseline: if the parameter is inert, S and V
   are indistinguishable, and that indistinguishability IS the result.
5. Arm M's observable is simply whether it completes rather than hanging.
6. Five repeats, first discarded, arms interleaved.

## 5 · Checker — acceptance declared before the run
Verdict variables `overlap(S)`, `overlap(V)` (independent-work time hidden behind the wait, as a
fraction) and `completes(M)`.
Gate, run first: a no-wait control must show `overlap` near 1 for the same work placement. If the
independent work does not overlap even with no wait present, the harness cannot detect scoping and
no verdict is issued.
PASS (claim upheld) iff `overlap(S) ≈ overlap(V) ≈ 0` — every pipe blocked, parameter inert — AND
`completes(M)` is true.
OVERTURN iff `overlap(V) > overlap(S) + 0.3`, i.e. naming a different pipe changes what stalls.
The mismatched-pair arm is a second, independent test of inertness: if arm M **hangs**, the
parameter is not inert after all, and that outcome overturns §1 even if arms S and V agreed — a
checker that ran only S and V would miss it. Declared now so arm M cannot be dropped as redundant.
Exit code is not the verdict, except that a hang is recorded via a wall-clock timeout as its own
outcome rather than as a failure.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; no board touched; the source names an architecture and two product lines, not a
board. This entry does not establish that the three modes behave identically on DAV_2201 — upstream
says the *selector* is inert, which implies one effective behaviour, but does not say which mode's
semantics that behaviour is. It does not establish the C-910-009 reconciliation offered in §2: that
"blocks all pipes" is what `radix_sort.md` meant by "无硬件 barrier" is this book's inference, not
upstream's, and §4 does not test it. It does not establish the DAV_3510 side, quoted only as the
contrast that makes the porting hazard concrete. The 910-legal/950-illegal `PIPE_S` asymmetry is
upstream's assertion and untested here.
