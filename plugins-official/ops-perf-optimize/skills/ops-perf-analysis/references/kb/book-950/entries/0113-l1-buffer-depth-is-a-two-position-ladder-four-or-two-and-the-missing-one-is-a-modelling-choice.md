```
ID:        0113-l1-buffer-depth-is-a-two-position-ladder-four-or-two-and-the-missing-one-is-a-modelling-choice
LABEL:     knowledge
LEVEL:     L2 (memory hierarchy & residency)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/tiling/matmul/fallback/tiling-flow.md:165-179 and
           matmul/fallback/tiling-fields.md:163-173 — "used_4buf = baseN × kl1 × 4 + baseM × kl1 × 4
           + biasSize; nBufferNum = (used_4buf < l1Size) ? 4 : 2" and "参考引擎把 L1 缓冲深度**离散成
           两档**（4 / 2）写入 nBufferNum，未实现"单槽不乒乓"档位 ... 应解释为"流式重叠 + L1 离散
           档位"的设计差异，而非"工具产不出 1""
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured matmul on a named 950 board where a hand-written L1 single-buffer kernel
           (no ping-pong) beats the nBufferNum=2 plan on the same shape — that would make the
           missing rung a real loss rather than a deliberate omission.
```

# 0113 · L1 buffer depth is a two-position ladder, 4 or 2, and the missing 1 is a modelling choice

## 1 · Claim
Upstream asserts that `nBufferNum`, the L1 ping-pong depth for the streaming operands, takes only
two values, 4 or 2, and that the choice is a single capacity test: estimate the four-buffer layout
as `used_4buf = baseN × kl1 × 4 + baseM × kl1 × 4 + biasSize` and take 4 if that is below `l1Size`,
otherwise 2. For the MX variants the scale buffers enter the same estimate as an independent
2-deep ping-pong: `used_4buf = baseN × kl1 × 4 + baseM × kl1 × 4 + scaleASize × 2 + scaleBSize × 2
+ biasSize`. Upstream further asserts that the absence of `nBufferNum = 1` is a deliberate
modelling decision, not a generator limitation — SWAT is a K-streaming path in which a single L1
slot forces load-then-compute-then-load with no MTE2/Cube overlap, so the reference engine
discretises L1 depth into two rungs and does not implement a no-ping-pong rung. Not established
here.

## 2 · The wrong branch this removes
Two, in opposite directions. First, an agent that reads "double buffering" as a switch tries to
turn it off to reclaim L1 for a larger `baseK`, gets `nBufferNum = 1` rejected or ignored, and
concludes the tool is broken. Upstream's own framing is the correction and is worth carrying
verbatim: the difference should be explained as `"流式重叠 + L1 离散档位"的设计差异，而非"工具产不
出 1"` — a modelling assumption mismatch, not a missing feature. Second, and more costly, an agent
comparing a generated plan against a hand-written kernel that does use a single L1 slot will find
the two disagree on L1 occupancy by 2× and try to reconcile the numbers; they are not reconcilable
because they are different models, and the report should say so rather than average them.

The capacity test itself removes a third: `used_4buf` is compared against `l1Size` with a strict
`<`, and both operands' four-buffer footprints are charged even though only the streaming side is
actually four-deep in the FullLoad branch. An agent that re-derives the test more carefully will
get 4 where upstream gets 2, and will have silently changed the plan's L1 pressure.

## 3 · Ground / Source
`matmul/fallback/tiling-flow.md:165-179`, §3.6 in full:

```
### 3.6 L1 缓冲数

nBufferNum 控制 L1 中 pingpong 缓冲数量。4 缓冲比 2 缓冲能更好地隐藏 MTE2 搬移延迟。

used_4buf = baseN × kl1 × 4 + baseM × kl1 × 4 + biasSize
nBufferNum = (used_4buf < l1Size) ? 4 : 2

MXFP8/MXFP4 场景 scale 使用独立 2-buffer pingpong，需计入：

used_4buf = baseN × kl1 × 4 + baseM × kl1 × 4 + scaleASize × 2 + scaleBSize × 2 + biasSize
nBufferNum = (used_4buf < l1Size) ? 4 : 2
```

`matmul/fallback/tiling-fields.md:163-173`, §11.1, the rationale in full:

```
### 11.1 为什么 `nBufferNum` 仅取 4 / 2，无 1

**SWAT 是 K 维流式路径**：反复把 A、B 与 Scale 从 GM 经 MTE 搬入 L1，再由 Cube 从 L1 经 L0 做乘加。L1 上**只有一套**槽位（单缓冲）时只能"搬完 → 算 → 再搬"，**MTE2 与 Cube 难以重叠**，吞吐受限于串行。要做流水重叠，L1 上需**至少两套**轮换缓冲——这就是**乒乓（双缓冲）**。

`TilingSwat._calculate_default_n_buffer_num()` 的选择逻辑：

- 估算**四缓冲**布局的 A/B/Scale 总占用（`step_k = min(stepKa, stepKb)`、`kl1 = step_k × baseK`）
- 占用 ≤ `l1_size` → `nBufferNum = 4`（深乒乓）
- 占用 > `l1_size` → 回退 `nBufferNum = 2`（双乒乓，仍重叠）

**为何不暴露 `nBufferNum = 1`**：参考引擎把 L1 缓冲深度**离散成两档**（4 / 2）写入 `nBufferNum`，未实现"单槽不乒乓"档位——这与 SWAT 流式 + 重叠的默认目标一致。用户若把"不开乒乓"理解为 L1 单缓冲（`nBufferNum=1`），与参考的 `nBufferNum=2` **建模假设不同**，应解释为"流式重叠 + L1 离散档位"的设计差异，而非"工具产不出 1"。
```

The two statements of the comparison differ: `tiling-flow.md:171` writes `used_4buf < l1Size`
(strict), `tiling-fields.md:170-171` writes `占用 ≤ l1_size → 4` (non-strict). At exact equality
the two texts give different answers. Minor, and recorded rather than adjudicated —
C-950tiling-006.

Related field constraints elsewhere in the family: under StreamK `l1BufferNum` is forced to 2
(`tiling-flow.md:306`, `tiling-fields.md:41`) so this test does not run at all; under FullLoad it
`通常回退到 2` (`tiling-flow.md:243`); `group_matmul` does not carry the field at all and lets the
kernel's compile-time `L1_BUFFER_NUM` decide (`tiling-fields.md:104`). So the two-rung ladder
governs exactly the SWAT and FullLoad paths of the non-group variants, and an agent reporting a
tuned `nBufferNum` on a StreamK or group plan has reported a field that does not exist there.

`l1Size` has no value anywhere in the family — see 0111.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s
spacing; bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and
discard the case if the die moved.

Three-rung comparison, which requires stepping outside the generator for the missing rung. Fix one
SWAT shape whose `used_4buf` sits comfortably below the queried L1 capacity (so the generator
would choose 4) and one whose `used_4buf` sits just above it (so it would choose 2). For each,
build three kernels from the same source with one compiler pin: `nBufferNum = 4`, `= 2`, and a
hand-written single-slot L1 variant that performs the same computation with no L1 ping-pong. The
third arm is the point of the experiment — it is the rung upstream declines to model, and without
it "4 or 2" is untested rather than confirmed. md5 all three binaries. Check every arm against an
fp64 reference within the declared tolerance. Record `aic_time`, MTE2 bytes and MTE2/Cube overlap
under `msprof --aic-metrics=PipeUtilization`, ≥10 iterations, first 5 dropped, per case.

Second arm, for the boundary: sweep `baseK` so `used_4buf` crosses the queried `l1Size` exactly,
and record which rung the generator selects at, just below, and just above equality — this
settles the strict-vs-non-strict discrepancy behaviourally.

Refuses to assume: that a free die stays free; that a die may be substituted; that `l1Size` is any
literal (it is queried); that the single-slot arm is legal — if it cannot be built, that is the
result and is reported as such; that a rung ordering at BF16 holds for the MX variants, whose
scale buffers enter the estimate differently.

## 5 · Checker — acceptance declared before the run
Verdict variable `rung_order`, the ordering of median `aic_time` across the three arms per shape.
Declared before the run: the claim survives iff `t(4) ≤ t(2) < t(1)` on the shape where four
buffers fit, and `t(2) < t(1)` on the shape where they do not. The OVERTURN fires iff `t(1)` beats
`t(2)` by more than 5 % on either shape. A second variable `boundary_rung` records the generator's
choice at exact equality and settles C-950tiling-006 without a timing argument.

The exit code is not the verdict. Two guards make this checker able to go red. First, the overlap
metric: if the `nBufferNum = 2` arm shows the same MTE2/Cube overlap as the single-slot arm, the
ping-pong did not happen and the comparison is void — the checker fails rather than reporting the
times. Second, the host echo of `nBufferNum` must match the request in the two generated arms;
a plan that fell back from 4 to 2 silently would otherwise make `t(4) = t(2)` read as
"four buffers buy nothing".

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured. The entry does not establish that four buffers are faster than two on any
shape, that two are faster than one, or that a single-slot L1 kernel can even be built on this
architecture — that is what §4's third arm exists to find out. It does not establish `l1Size` or
`biasSize` for any board (0111), and it does not establish whether the strict or non-strict
comparison is the implemented one. It says nothing about L1 depth under StreamK (forced 2),
group_matmul (field absent) or the enhancement layers, whose `scaleL1BufferNum` runs a separate
`[16, 8, 4, 2]` fallback ladder (`tiling-fields.md:65`, `:114`) that this entry does not cover.
No board is named in the source files, so BOARD is `family-claimed(unverified)` and the chip is
unstated; §4 names 950PR/950DT because that is where our run would happen. Nothing here is
established for any 910-family board.
