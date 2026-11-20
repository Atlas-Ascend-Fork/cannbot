```
ID:        0304-the-instruction-queue-depth-is-a-hardware-constant-and-mte2-preload-routes-around-it-rather-than-raising-it
LABEL:     knowledge
LEVEL:     L1 (core & pipe assignment)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
           # measured by upstream at BF16 M=1024 K=4096 N=2048, but the file names no board and the
           # matmul family's only architecture attribution is one cell of the shelf SKILL.md (0347).
SOURCE:    ops/ascendc-performance-best-practices/reference/matmul/mte2_preload_design.md:17 —
           "当 PING 与 PONG 之间插入的指令数超过芯片预设指令队列深度（硬件参数，不可软件调大），
           即使 PING 的数据依赖已解除，PONG 仍会被指令队列阻塞。"
SOURCE:    same file:7 — "典型收益：Task 时间 **−3%–10%**（对应 `matmul` BF16 `M=1024, K=4096,
           N=2048` 实测 `66.0μs → 63.3μs`，约 **−4%**；MTE2 段 `37.6μs → 32.7μs`，约 **−13%**）。"
           ; :263-267 (the seven-column per-segment table, quoted in full in §3)
           ; :302 — "| **指令队列深度软件调大** | ❌ 不存在（硬件约束） | 指令队列深度是芯片固定值，
           软件只能绕开，不能调大 |"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured paired build on a named 950 board at the stated BF16 shape where MTE2 Preload
           moves the MTE2 segment by less than the baseline arm's own repeat-to-repeat spread — the
           mechanism would then not be issue blocking, or not be relieved by this transform. A
           second, independent kill: any documented or measured way to raise the instruction queue
           depth from software, which would make the whole technique a workaround for a
           misconfiguration.
```

# 0304 · The instruction queue depth is a hardware constant, and MTE2 Preload routes around it rather than raising it

## 1 · Claim
Upstream asserts a blocking mechanism and a transform that avoids it. The mechanism: under L1
ping-pong, `MTE2_PONG` cannot issue until every instruction issued after `MTE2_PING` has issued, so
when the instruction count inserted between them exceeds the chip's preset instruction queue depth,
`PONG` stalls on the *queue* even though its data dependency is already clear. Upstream asserts that
this depth is a hardware parameter that software cannot raise (`硬件参数，不可软件调大`), and states
the same again in its stacking table as `❌ 不存在（硬件约束）`. The transform: issue `PING` and
`PONG` back to back in the first round, so `PONG`'s issue point moves to within a few instructions of
`PING`'s, and every later round stays one tile out of phase.

Upstream asserts a measurement for the transform at BF16 `M=1024, K=4096, N=2048` with
`baseM=baseN=256, baseK=64, kL1=256, kL1TileNum=16, PINGPONG_NUM=2`: task time 66.000 → 63.288 µs
(−4.1 %) and the MTE2 segment 37.595 → 32.722 µs (−13.0 %), with a stated range of −3 % to −10 %
across shapes. Not established here — these are upstream's readouts, not ours.

This entry supersedes the harvest card
`harvest/claims/ascendc-performance-best-practices--001-...`, which routed this measurement away
from book-910 on the strength of the family's `DAV_3510` marking and left the 950-side decision to
another agent. That decision is taken here: the card's routing stands, and the claim enters this
book. The card is left in place as the record of the routing (RULES.md Art. 9).

## 2 · The wrong branch this removes
Three, in descending order of cost.

First and worst: an agent that sees `MTE2_PONG` starting far later than `MTE2_PING` ends, and
concludes MTE2 is bandwidth-bound. The correct reading is the opposite — nothing is saturated;
`PONG` has its data and cannot get an issue slot. Upstream names the discriminating signature:
all pipes at ≤ 60–70 % busy with a deterministic gap between PING and PONG in the trace, which it
calls "准无 bound". An agent on the bandwidth branch will shrink `baseK`, enlarge tiles, or reach
for A/B-Full-Load — and upstream states directly that the true-bound case (MTE2 busy > 85 % *and*
bandwidth utilisation ≥ 85 %) is where Preload has little to give, so the two branches want
opposite work.

Second: reducing `kL1` to shorten the PING→PONG instruction distance. It works on the blocking and
loses overall — fewer K per buffer means more outer iterations and more start/stop, which upstream
states as `净收益为负`.

Third, and the one an agent is most likely to reach for: looking for a way to raise the queue
depth. There is none. Upstream states it twice, in two different sections, in the imperative. An
agent that spends time searching a configuration surface for it is searching a space that does not
contain the answer — and the entry's value is partly in saying so before the search starts.

The cost side is disclosed and must travel with the recommendation: scalar time roughly doubles
(2.558 → 5.924 µs, upstream's own table), MTE1 rises, and the net is still negative because the MTE2
saving is larger. A recommendation that quotes −13 % on MTE2 without the +3.4 µs scalar is quoting
half a table.

## 3 · Ground / Source
The mechanism, `mte2_preload_design.md:17`:

```
双缓冲语义下，`MTE2_PING`（本轮搬 L1[0]）发完之后，**下一轮** `MTE2_PONG`（本轮搬 L1[1]）必须等
**所有发射在 PING 之后的指令**都发完才能拿到发射机会。当 PING 与 PONG 之间插入的指令数超过芯片
预设指令队列深度（硬件参数，不可软件调大），即使 PING 的数据依赖已解除，PONG 仍会被指令队列阻塞。
```

The diagnostic signature, `:27-29`:

```
- 现象：`trace_core*.json` 中 `MTE2_PONG` 事件起点 ≫ 理论起点（≈ `MTE2_PING` 事件终点）；
  PING ↔ PONG 之间存在**确定性 gap**
- 不是 MTE2 带宽 bound，不是 CUBE bound，常呈 **"pingpong 已启用但各流水 busy 仍 ≤ 60%–70%"** 的
  "准无 bound"形态
- **KL1 已无法继续缩减**：继续缩减 `kL1` 会减少 PING/PONG 之间插入的指令数（化解阻塞），但单次
  覆盖 K 减少 → 外层循环次数上升 → 循环起停开销上升 / CUBE busy 下降，**净收益为负**
```

The measured table in full, `:261-267`, which is the reason this entry carries a shape:

```
以 `M=1024, K=4096, N=2048`、BF16、`baseM=baseN=256, baseK=128/sizeof(BF16)=64,
kL1=512/sizeof(BF16)=256, kL1TileNum=16, PINGPONG_NUM=2` 为例：

| 版本 | kernel (μs) | mac (μs) | scalar (μs) | mte1 (μs) | **mte2 (μs)** | fixpipe (μs) | icache_miss (%) |
| pingpong 基线（n_buffer） | 66.000 | 40.810 | 2.558 | 10.659 | **37.595** | 1.980 | 1.200 |
| **MTE2 Preload** | **63.288** | 41.880 | 5.924 | 14.299 | **32.722** | 2.543 | 0.500 |
| Δ | **−2.712（−4.1%）** | +1.070 | +3.366 | +3.640 | **−4.873（−13.0%）** | +0.563 | −0.700 |
```

Re-derived: `66.000 − 63.288 = 2.712` ✓, `2.712 / 66.000 = 4.11 %` ✓;
`37.595 − 32.722 = 4.873` ✓, `4.873 / 37.595 = 12.96 %` ✓;
`5.924 − 2.558 = 3.366` ✓; `14.299 − 10.659 = 3.640` ✓; `41.880 − 40.810 = 1.070` ✓;
`2.543 − 1.980 = 0.563` ✓. Shape parameters: `128 / sizeof(BF16) = 64` ✓,
`512 / sizeof(BF16) = 256` ✓, `4096 / 256 = 16 = kL1TileNum` ✓. The sum of the non-kernel deltas is
`+1.070 + 3.366 + 3.640 − 4.873 + 0.563 = +3.766`, which is **not** `−2.712` — the segments are
overlapping pipe occupancies, not an additive decomposition of wall time, and any reader who tries
to reconcile them will fail. Recorded because a consuming agent will try.

The prose corroboration of the scalar cost, `:194`: `scalar busy 可能从 **~3μs 升到 ~6μs**（见实测
对照表）—— 这是已知取舍`. Consistent with the table (2.558 → 5.924).

The impossibility statement, `:302`:

```
| **指令队列深度软件调大** | ❌ 不存在（硬件约束） | 指令队列深度是芯片固定值，软件只能绕开，不能调大 |
```

What the source does **not** give: the depth's value. It is never stated as a number anywhere in
the family, and no ini field in the installed CANN 9.0.0-beta.2 `platform_config` set names an
instruction queue depth. Owed as a measurement in `harvest/standing/950-bp.md`.

Measurement / inference split at sentence level: **measured** — the seven columns of the table, on
one unnamed part. **not measured** — that the cause is queue depth rather than any other
serialisation; that is upstream's mechanism story, and the table is equally consistent with several
others. §4 arm 2 is what would separate them.

## 4 · Procedure
Proposed, runnable later on a named 950 board (`950PR` or `950DT`, separately). Never run in this
phase.

Variance floor first, and it dominates the design: the headline effect is −4 %, so a floor above
about 2 % makes the whole comparison unreportable. One build, 30 in-process runs and 5
fresh-process runs, IQR over median, reported beside every figure below. Established for the
*baseline* arm before the arms are compared — a −4 % claim against an unstated spread cannot be
evaluated.

Arm 1 — reproduce the table. Two builds differing only in the three-segment loop restructure, at
exactly the stated shape and tiling. Collect all seven columns with
`msprof --aic-metrics=PipeUtilization`, plus `icache_miss`. Compare each against upstream's cell.

Arm 2 — the mechanism, which is the half no A/B can establish. Vary the instruction count between
PING and PONG *without* changing the data volume: insert `N` independent no-op-equivalent scalar
instructions into the baseline's inter-issue region for `N = 0, 8, 16, 32, 64, 128`, and record
where the PING→PONG gap in `trace_core*.json` first appears and how it grows. A queue-depth
mechanism predicts a **knee**: no gap below some `N*`, then a gap growing with `N`. A bandwidth or
dependency mechanism predicts no knee. `N*` is then the first number anyone has for this depth, and
it is the entry's real prize.

Arm 3 — the shape-dependence claim. Repeat Arm 1 at `kL1TileNum ∈ {1, 2, 4, 8, 16, 32}` by varying
K, and confirm the declared no-op at `kL1TileNum = 1` (`0305`) and the stated −3 % … −10 % envelope.

Arm 4 — the negative arm, retained whatever it shows. Run at a true-MTE2-bound point (MTE2 busy
> 85 %, bandwidth ≥ 85 %) where upstream predicts near-zero gain. An arm that does not bite is
recorded as an arm that did not bite.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and discard the
case if the die moved. Refuses to assume: that a free die stays free; that a die may be substituted
into a die-scoped claim; that the two builds differ only where intended (both are disassembled and
diffed, because "we changed the loop" is not "the machine changed"); that upstream's part is this
part; that a single run is a measurement.

## 5 · Checker — acceptance declared before the run
Verdict `mte2_delta` = (baseline MTE2 median − preload MTE2 median) / baseline MTE2 median, with the
floor. Declared before the run: the transform is **supported** iff `mte2_delta` is positive and
outside the floor. The OVERTURN fires iff `|mte2_delta|` is inside the floor.

Verdict `task_delta` on kernel time, reported with `mte2_delta` and never instead of it — the whole
point of upstream's table is that the two differ by a factor of three.

Verdict `scalar_cost` = preload scalar − baseline scalar, reported unconditionally. There is no pass
condition on it; it exists so that no downstream recommendation can quote the MTE2 win without it.

Verdict `queue_knee` = `N*` from Arm 2, or `none` if the gap grows smoothly from `N = 0`.
`queue_knee == none` does not overturn the *transform* but does overturn the stated *mechanism*, and
the entry is corrected in place to say the technique works for a reason nobody has established.

The exit code is not the verdict. Three guards.

First: both builds are compared elementwise against one CPU reference at every shape. Upstream lists
four distinct ways this transform produces wrong output silently — a missed `WaitFlag` in segment 1,
a `curL1BufId` that does not switch, an out-of-range prefetch past the K boundary, and a misplaced
`WaitFlag<MTE2_MTE1>` — and a timing-only checker scores a fast wrong kernel as the best result.

Second — the input that makes this checker go red. Arm 1 is repeated with the preload build's
segment-2 condition `iter0 + 1 < kL1TileNum` deliberately removed. This is upstream's disclosed
out-of-bounds defect; the checker **must** report either a fault or a precision failure. If it
reports neither, the correctness arm is not reading what it claims to read and every green is void.
The fixture is a planted positive the checker has to find, not a clean line it hopes for.

Third: no delta is reported without its floor, and no arm is reported without the die-occupancy
samples that preceded and followed it.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. Every number in §3 —
66.000, 63.288, 40.810, 41.880, 2.558, 5.924, 10.659, 14.299, 37.595, 32.722, 1.980, 2.543, 1.200,
0.500 — is upstream's readout on an unnamed part; this book has reproduced none of them. The
instruction queue depth has no value here, in upstream, or in any installed ini file.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. Upstream's figures carry a dtype, a shape and a full tiling
configuration — unusually complete for this shelf — but no board, no core count, no tool, no repeat
count, no variance and no CANN pin, so their precision is not their reliability, and a −4.1 % effect
without a stated spread cannot be evaluated at all. The entry does not establish the queue-depth
mechanism: the table is consistent with any serialisation between PING and PONG, and §4 Arm 2 is the
only thing here that would discriminate. It does not establish the depth's value, which no upstream
document and no installed ini gives. It does not establish the −3 % … −10 % envelope, which is
asserted for unnamed other shapes. The seven segment columns do not add to the kernel delta and must
not be treated as a decomposition. BOARD is `family-claimed(unverified)` because no file in the
matmul family names a chip (`0347`); if the shelf SKILL.md's `DAV_3510` cell for this family is
wrong, this measurement is booked in the wrong book, and the harvest card that first raised that
routing question is retained rather than deleted. Nothing here is established for 950DT if a run
happens on 950PR or the reverse, and nothing transfers to the other book (RULES.md Art. 1).
