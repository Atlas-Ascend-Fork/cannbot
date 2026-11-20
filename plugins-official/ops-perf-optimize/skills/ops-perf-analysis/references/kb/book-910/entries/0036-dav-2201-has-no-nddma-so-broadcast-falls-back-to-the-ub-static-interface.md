```
ID:        0036-dav-2201-has-no-nddma-so-broadcast-falls-back-to-the-ub-static-interface
LABEL:     boundary
LEVEL:     L3 (data movement & layout)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-tiling-design/references/broadcast/nddma-broadcast.md:5 — "**DAV_2201 不支持 NDDMA**，请使用 [UB Broadcast 静态接口](ub-broadcast.md)"; ibid:196 — "| **芯片** | 仅 DAV_3510（Ascend 950），DAV_2201 不支持 |"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  an NDDMA-based broadcast compiles and runs on a named DAV_2201 board.
```

# 0036 · DAV_2201 has no NDDMA, so broadcast falls back to the UB static interface

## 1 · Claim
Upstream asserts that DAV_2201 does not support NDDMA, that NDDMA broadcast is a DAV_3510-only
path, and that DAV_2201 must use the UB Broadcast static interface instead. Upstream lists NDDMA
among the DAV_3510 additions relative to DAV_2201, alongside SIMT, SIMD-Regbase and CCU. Not
established here.

## 2 · The wrong branch this removes
This is a capability boundary and its value to a 910-targeted agent is mostly negative: it stops
work from being wasted. Most of the broadcast optimisation material in the upstream repo is written
for the NDDMA path, because that is where the newer and more interesting engineering is. An agent
mining that material for a 910 target will read a decision tree, a tiling flow and a set of
templates that cannot execute on its part at all, and will only discover this when the build fails —
or, worse, will produce a design document recommending a path that does not exist.

The second branch is one this entry can only warn about, not fix: upstream's own broadcast tiling
script is reported to drop the DAV_2201 constraints unconditionally
(`harvest/surveys/DEEPDIVE_20260824_perf-optimize.md` §4.15, on
`ascendc-perf-optimize/references/tiling/broadcast/fallback/script/broadcast_tiling.py:373`). That
file is in another agent's domain and the observation is not re-verified here — it is flagged so a
910 consumer treats any broadcast tiling output from that subtree as unscoped.

## 3 · Ground / Source
`ops/ascendc-tiling-design/references/broadcast/nddma-broadcast.md:5`, the file's opening banner:
"> **DAV_2201 不支持 NDDMA**，请使用 [UB Broadcast 静态接口](ub-broadcast.md)。"
Line 196, in its constraint table: "| **芯片** | 仅 DAV_3510（Ascend 950），DAV_2201 不支持 |".
The comparison table at line 181 sets the two paths side by side: "| 维度 | UB Broadcast
(DAV_2201) | NDDMA Broadcast (DAV_3510) |".

The routing decision, `ops/ascendc-tiling-design/references/broadcast/patterns.md:62`:
"├─ DAV_2201 → UB Broadcast（优先静态接口，不满足对齐约束时用搬运指令方案） → [ub-broadcast.md]"
— note the fallback-within-the-fallback: when the static interface's alignment constraints are not
met, DAV_2201 drops further, to a plain data-movement scheme.

The dynamic interface is likewise unavailable:
`ops/ascendc-tiling-design/references/broadcast/dynamic-ub-broadcast.md:13` — "| 芯片 |
DAV_2201/DAV_3510 通用 | 仅 DAV_3510 |", with line 5 directing DAV_2201 to the static rank-1/2
interface.

Corroborating the capability's generation, from the truth source:
`ops/npu-arch/SKILL.md:64` lists under DAV_3510 的关键变化 — "| 编程模型 | 新增 SIMT、SIMD-Regbase、
NDDMA、CCU 通算融合 |". Same repo, one origin, but a different skill and a different framing
(architecture change list versus API availability), which makes the two mutually reinforcing on a
question of fact rather than of degree.

Also relevant to a 910 reader: `ops/ascendc-performance-best-practices/reference/broadcast/
broadcast_design.md:30` gates one of its broadcast modes on "尾轴≥dcache/2（~4096B）" using
`GetNddmaDcacheSize()`. That gate is unavailable on a part without NDDMA, so that document's
decision tree does not apply to DAV_2201 either — a second broadcast source that a 910 agent should
not mine.

## 4 · Procedure
Proposed, runnable later; not run. A capability absence is established by failing to use it, which
makes the procedure short and the interpretation delicate.

1. Compile arm, no device: build an NDDMA broadcast against `__NPU_ARCH__` 2201 and record the
   result. A compile-time rejection establishes the claim at the level upstream states it.
2. Symbol arm, read-only, no device: `grep -Rn "Nddma\|NDDMA\|GetNddmaDcacheSize" \
   "$ASCEND_HOME_PATH"/*/include` and record whether the symbols exist at all and whether they are
   behind an arch guard. This is the arm that distinguishes "absent from the SDK" from "present but
   guarded" from "present and silently wrong on 2201", and those three are not the same finding.
3. Device arm, only if steps 1 and 2 both suggest availability: run it on a named die (occupancy
   before and after, no substitution) and compare against the UB static path bitwise.
4. Positive control: the same build targeting a DAV_3510 part must succeed. Without it, a failure
   at step 1 is equally consistent with a broken build setup, and the whole procedure concludes
   nothing. If no DAV_3510 part is available, say so — the result is then weaker and must be
   recorded as weaker.

## 5 · Checker — acceptance declared before the run
`compiles_2201`: the claim is upheld iff false, AND `compiles_3510` is true.
That conjunction is the entire point of §5. `compiles_2201 == false` alone is worth nothing: a
missing include path, a wrong toolkit, a typo in the arch flag all produce it. Only the contrast
with a working 3510 build turns a failure into evidence. Where the 3510 control cannot be run, the
verdict is INCONCLUSIVE and is recorded as INCONCLUSIVE, not as PASS.
`symbols_present`: recorded in all cases, with three outcomes (absent / arch-guarded / unguarded),
never collapsed to a boolean. An unguarded symbol that compiles for 2201 and misbehaves at runtime
is the most dangerous of the three and would be invisible to a boolean check.
Exit code IS the observation in arm 1, which is the exception to this book's usual rule and is
stated here rather than assumed.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; no board touched; per-architecture, so no individual board. This entry does not
establish what the UB static interface can do — that is 0037. It does not establish that every
NDDMA-dependent optimisation elsewhere in upstream is inapplicable to 910, only that the broadcast
ones named here are; the general claim would need a survey this entry did not perform. The
broadcast_tiling.py observation in §2 is quoted from a survey and was NOT re-verified for this
book — it is flagged, not asserted. It says nothing about whether an equivalent capability exists
on DAV_2201 under another name.
