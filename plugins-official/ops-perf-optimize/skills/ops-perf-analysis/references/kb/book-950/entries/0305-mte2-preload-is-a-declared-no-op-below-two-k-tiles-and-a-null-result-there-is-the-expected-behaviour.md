```
ID:        0305-mte2-preload-is-a-declared-no-op-below-two-k-tiles-and-a-null-result-there-is-the-expected-behaviour
LABEL:     boundary
LEVEL:     L9 (performance)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/matmul/mte2_preload_design.md:243 —
           "`kL1TileNum == 1` 时段 2 的条件 `iter0 + 1 < kL1TileNum` 永远不成立，首轮段 2 不触发 →
           退化为"每 tile 只搬一次"，MTE2 Preload 不生效。这是**预期行为**：小 K 下 PING 与 PONG
           之间插入的指令数少，指令队列阻塞本来就不显著。"
SOURCE:    same file:245 — "收益验证应选 `K ≥ 2 × kL1` 且 `kL1TileNum ≥ 2` 的 shape" ;
           :284 — "| pingpong 已开；`kL1TileNum < 2` | 不开 MTE2 Preload | 段 2 不触发，等价于退回
           pingpong 基线 |"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a paired build on a named 950 board at `kL1TileNum == 1` where the MTE2 Preload variant
           is measurably faster or slower than the ping-pong baseline outside the run spread — the
           transform would then not be inert there, and the "declared no-op" reading would be wrong.
```

# 0305 · MTE2 Preload is a declared no-op below two K tiles, and a null result there is the expected behaviour

## 1 · Claim
Upstream asserts that MTE2 Preload (`0304`) is structurally inert when `kL1TileNum == 1`: the
segment-2 prefetch is guarded by `iter0 + 1 < kL1TileNum`, which can never hold, so the kernel
degenerates to one MTE2 per tile — exactly the ping-pong baseline. Upstream asserts this is
`预期行为`, not a defect, with a stated reason: at small K the instruction count inserted between
PING and PONG is small, so queue blocking is not significant to begin with. Upstream asserts the
consequence for anyone measuring the technique — validate on a shape with `K ≥ 2 × kL1` and
`kL1TileNum ≥ 2` — and repeats the gate in its selection table as `kL1TileNum < 2 → 不开`. Not
established here.

## 2 · The wrong branch this removes
An agent measures MTE2 Preload on a convenient small case (upstream's own example: `K = 256`,
`kL1 = 512`), sees no difference, and files a null result: "the technique does not work". The null
result is correct and the conclusion is wrong. The transform was never active in that build — a
source-level guard removed it — so the run measured the baseline against itself.

This is the most common way a real technique gets retired: not by being disproven, but by being
tested outside its declared domain and then reported as tested. The specific defence upstream
supplies is a *precondition that is checkable before the run*, not after: `kL1TileNum = K / kL1`,
computable at tiling time from three numbers.

The symmetric branch also exists. An agent that does not know the guard, sees no gain, and starts
debugging the flag pairing will find nothing wrong, because nothing is wrong. Upstream states the
entry gate precisely so that "no effect" is distinguishable from "not applicable" *without* opening
a profile.

## 3 · Ground / Source
`mte2_preload_design.md:239-245`, the whole item:

```
### 问题 5：仅测试小 K 场景（`kL1TileNum == 1`）看不到收益

**现象**：小 K 场景（如 `K = 256, kL1 = 512`，`kL1TileNum = 1`）跑出来和 pingpong 基线性能一样。

**原因**：`kL1TileNum == 1` 时段 2 的条件 `iter0 + 1 < kL1TileNum` 永远不成立，首轮段 2 不触发 →
退化为"每 tile 只搬一次"，MTE2 Preload 不生效。这是**预期行为**：小 K 下 PING 与 PONG 之间插入的
指令数少，指令队列阻塞本来就不显著。

**解决方案**：收益验证应选 `K ≥ 2 × kL1` 且 `kL1TileNum ≥ 2` 的 shape（如教程例 `M=1024,
K=4096, N=2048`，`kL1 = 256`，`kL1TileNum = 16`），才能观察到 MTE2 段 cycle 节省。
```

The same gate as a routing row, `:284`, and as a checklist item, `:309`
(`- [ ] kL1TileNum ≥ 2（K / kL1 ≥ 2），否则段 2 不触发`). Three statements of one rule in one file
— one origin (RULES.md Art. 3), quoted three times because a reader who opens any of the three meets it.

Arithmetic of the two examples: the inert case `K = 256, kL1 = 512` gives
`kL1TileNum = ⌈256/512⌉ = 1` ✓. The active case `K = 4096, kL1 = 256` gives `4096/256 = 16` ✓,
consistent with `0304`'s measured configuration.

Note what upstream states as *reason* versus what it states as *mechanism*. The mechanism — the
guard `iter0 + 1 < kL1TileNum` can never hold at `kL1TileNum == 1` — is a fact about the source and
can be checked by reading. The reason — that queue blocking is insignificant at small K anyway — is
an assertion about the machine and is not measured anywhere in the file. Those are different claims
and §4 separates them: if the second is false, the technique has a real gap at small K that the
guard is silently hiding.

## 4 · Procedure
Proposed, runnable later on a named 950 board. Never run in this phase. Two arms, matching the two
claims §3 separates.

Arm 1 — the inertness, which is cheap and is the entry's main content. Build the ping-pong baseline
and the MTE2 Preload variant at `K = 256, kL1 = 512` (`kL1TileNum = 1`), everything else identical
to `0304`'s configuration. Time both with a variance floor established first (one build, 30
in-process runs, 5 fresh-process runs, IQR over median). Additionally disassemble both and diff:
inertness is a *source-level* prediction, so the two binaries should differ only by dead branch
code, and confirming that is stronger evidence than the timing.

Arm 2 — the stated reason, which nobody has measured. Sweep `kL1TileNum` from 1 to 16 by varying K
at fixed `kL1`, and for the *baseline* build alone record the PING→PONG gap in `trace_core*.json` at
each point. Upstream's reason predicts the gap is absent or negligible at `kL1TileNum = 1` and grows
with it. If instead the gap is already present at `kL1TileNum = 1`, then blocking exists at small K,
the guard is suppressing a real opportunity, and the entry is corrected in place — the technique
would need a small-K variant rather than a gate.

Arm 3 — the boundary itself. `kL1TileNum = 2` is the first active point. Time baseline and preload
there. This is where the declared gate says the benefit turns on, and a gate whose first active
point shows nothing is a gate set in the wrong place.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after, discard the case
if the die moved. Refuses to assume: that a free die stays free; that a die may be substituted; that
`kL1TileNum` is what the host tiling says it is — it is echoed from the kernel; that the compiler
left the dead branch dead, which Arm 1's disassembly diff is what checks.

## 5 · Checker — acceptance declared before the run
Verdict `inert_delta` = (baseline median − preload median) / baseline median at `kL1TileNum == 1`,
with the floor attached. Declared before the run: pass is `|inert_delta|` **inside** the floor —
this is the rare checker whose green is a null result, and saying so now is what makes the null
result readable rather than deniable afterwards. The OVERTURN fires iff `|inert_delta|` is outside
the floor in either direction.

Verdict `dead_branch` = true iff the disassembly diff shows the segment-2 body present but
unreachable in the preload build. `dead_branch == false` with `inert_delta` inside the floor means
the compiler removed the branch and the timing agreement proves less than it appears to; the arm is
reported as `void`, not as a pass.

Verdict `gap_at_1` from Arm 2: present or absent at `kL1TileNum == 1`, against the same trace
threshold used at `kL1TileNum == 16`.

The exit code is not the verdict. Two guards. First, both builds are compared elementwise against a
CPU reference — an inert transform that is nonetheless wrong is still wrong, and `0304`'s disclosed
defects (flag pairing, out-of-range prefetch) do not become impossible at small K. Second — the
input that makes this checker go red — Arm 1 is repeated at `kL1TileNum = 16`, where the same
comparison **must** show a difference outside the floor. If the checker reports "inside the floor"
at both 1 and 16, it is not sensitive enough to distinguish the two regimes, its green at
`kL1TileNum = 1` means nothing, and the whole run is void. A checker whose only outcome is "no
difference" is the known blind species, and this is the fixture that catches it here.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The two shape examples
(`K=256, kL1=512` and `K=4096, kL1=256`) are upstream's; no build was made and no trace was read.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The entry does not establish that the guard makes the transform
inert on any part — that is a reading of upstream's source excerpt plus upstream's own statement,
and Arm 1's disassembly is what would confirm it. It does not establish upstream's *reason* (that
queue blocking is negligible at small K), which is asserted and nowhere measured; if that reason is
false the gate is hiding an opportunity rather than describing a limit, and Arm 2 is the only thing
here that would tell. It does not establish that `kL1TileNum = 2` is the right place for the gate.
No board, tool, repeat count or CANN pin accompanies any upstream statement here. BOARD is
`family-claimed(unverified)`: no file in this family names a chip (`0347`). Nothing transfers to the
other book (RULES.md Art. 1).
