```
ID:        0313-scale-coalescing-lengthens-only-the-scale-pingpong-period-and-the-missing-last-round-release-hangs-the-kernel
LABEL:     trap
LEVEL:     L4 (synchronisation)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/matmul/scale_coalescing_design.md:54 —
           "关键点：**scale 的 pingpong 周期拉长到 `scaleKL1Ratio × kL1Iter` 而非 `kL1Iter`**。只要
           `SCALE_BUFFER_NUM = 2`（ping/pong）就足够覆盖所有稳态轮次。"
SOURCE:    same file:202-208 — "if ((iter0 + 1) % scaleKL1Ratio_ == 0 || iter0 == kL1Iter_ - 1) {
           AscendC::SetFlag<AscendC::HardEvent::MTE1_MTE2>(SCALE_BUFFER_FLAG_0 + scaleL1BufId); ... }"
           · "**漏掉"末轮强制释放"（`iter0 == kL1Iter_ - 1`）会导致 K 不是 `scaleKL1` 整数倍时 AIV
           永远 Wait**。" ; :97 — "**`scaleKL1` 必须是 `kL1` 的整数倍**（`scaleKL1Ratio_ = scaleKL1
           / kL1`）。否则 `iter0 % scaleKL1Ratio_ == 0` 的判定会丢 scale 对齐，精度出错。" ;
           :187-194 — "uint64_t scaleKL1IterOffset = (iter0 % scaleKL1Ratio_) * kL1_; ... **漏加
           这个偏移会直接导致精度错误**（不同 K 段用同一份 scale 反量化）。"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a build on a named 950 board with `K` not a multiple of `scaleKL1` and the `|| iter0 ==
           kL1Iter_ - 1` term removed that completes normally — the missing release would then not
           be what deadlocks, and upstream's stated failure mode would be wrong.
```

# 0313 · Scale coalescing lengthens only the scale ping-pong period, and the missing last-round release hangs the kernel

## 1 · Claim
Upstream asserts that merging K-fragmented scale loads into one large transfer changes exactly one
thing in the synchronisation model: the scale buffers' ping-pong period stretches from `kL1Iter` to
`scaleKL1Ratio × kL1Iter`, while A and B keep their per-`kL1` period, and that two physical scale
buffers still suffice. Upstream asserts three implementation invariants and the failure each one has
when broken. `scaleKL1` must be an integer multiple of `kL1`, or the `iter0 % scaleKL1Ratio_ == 0`
trigger loses alignment and the result is wrong. The L0 fetch must add
`scaleKL1IterOffset = (iter0 % scaleKL1Ratio_) × kL1_`, or every K segment dequantises with the same
scale slice. The scale buffer release must fire on `(iter0 + 1) % scaleKL1Ratio_ == 0` **or**
`iter0 == kL1Iter_ - 1`, and omitting the second disjunct hangs the kernel whenever `K` is not a
multiple of `scaleKL1`. Not established here.

## 2 · The wrong branch this removes
The whole optimisation reads as a buffer-sizing change — enlarge `scaleKL1`, fetch less often — and
an agent implementing it from that description gets three chances to produce a kernel that is worse
than useless.

Two of the three fail *silently*. Dropping `scaleKL1IterOffset` gives a kernel that runs at full
speed, reports the expected MTE2 improvement, and dequantises every K segment with the first
segment's scale. Upstream names the signature: `输出 C 局部明显偏离 golden；尾部 K 段错得更严重` —
error growing with K index, which is a pattern a spot-check of the first tile cannot see. Choosing a
`scaleKL1` that is not a multiple of `kL1` gives the same class of failure by another route.

The third fails *loudly but at the wrong place*. Without the `|| iter0 == kL1Iter_ - 1` disjunct, a
`K` that is not a multiple of `scaleKL1` leaves the last partial scale buffer never released, and
the wait never satisfies. The symptom upstream reports is a hang attributed to AIV; the cause is one
missing term in an AIC-side release condition. An engineer chasing an AIV hang will not look there.

The fourth branch is the entry's structural point. Upstream states that the *only* thing coalescing
changes is the scale period. That is what licenses stacking it with ping-pong (`0301`) and with
Full-Load (`0311`) while forbidding it with StreamK (`0310`) — under StreamK the L1 buffer count is
fixed at 2 and the K segment is already ≥ 2048, so the scale blocks were never small. Reading the
exclusion as arbitrary and forcing the combination spends L1 for nothing.

## 3 · Ground / Source
The synchronisation change, `scale_coalescing_design.md:44-54`:

```
在 pingpong 事件模型（`pingpong_design.md` §2.3）基础上新增一对 "scale 独立 pingpong" 事件，与
A/B 的 L1 pingpong **事件 ID 分离**：

| `MTE1_MTE2(SCALE_BUFFER_FLAG_0)` | scaleA/B 在 L1 双缓冲 ping 释放 | 当前 L0 已消费完前一份
  merged scale，准许 MTE2 覆写 ping |
| `MTE1_MTE2(SCALE_BUFFER_FLAG_1)` | scaleA/B 在 L1 双缓冲 pong 释放 | 同上，pong |
| `MTE2_MTE1`（仍复用 A/B 轨） | A/B 搬入就绪 → L1→L0 | 合并后不变 |

关键点：**scale 的 pingpong 周期拉长到 `scaleKL1Ratio × kL1Iter` 而非 `kL1Iter`**。只要
`SCALE_BUFFER_NUM = 2`（ping/pong）就足够覆盖所有稳态轮次。
```

The integer-multiple requirement, `:97`:

```
3. **`scaleKL1` 必须是 `kL1` 的整数倍**（`scaleKL1Ratio_ = scaleKL1 / kL1`）。否则
   `iter0 % scaleKL1Ratio_ == 0` 的判定会丢 scale 对齐，精度出错。
```

The L0 fetch offset, `:186-194`:

```cpp
uint64_t scaleKL1IterOffset = (iter0 % scaleKL1Ratio_) * kL1_;

AscendC::Te::Copy(
    CopyL12L0MxScaleA, tensorScaleAL0, tensorBlockScaleAL1,
    AscendC::Te::MakeCoord(0, scaleKL1IterOffset + kL0Offset));   // 关键偏移
```

`B 侧同理（坐标维度反过来）。**漏加这个偏移会直接导致精度错误**（不同 K 段用同一份 scale 反量化）。`

The release condition, `:200-208`:

```cpp
AscendC::SetFlag<AscendC::HardEvent::MTE1_MTE2>(l1BufId);   // A/B 的每轮释放（不变）
if ((iter0 + 1) % scaleKL1Ratio_ == 0 || iter0 == kL1Iter_ - 1) {
    AscendC::SetFlag<AscendC::HardEvent::MTE1_MTE2>(SCALE_BUFFER_FLAG_0 + scaleL1BufId);
    scaleLoopCnt_++;
}
```

`**漏掉"末轮强制释放"（`iter0 == kL1Iter_ - 1`）会导致 K 不是 `scaleKL1` 整数倍时 AIV 永远 Wait**。`

The tail clipping that makes the last merged fetch legal, `:169-171`:
`if (scaleKL1Offset + curScaleKL1 > k_) { curScaleKL1 = k_ - scaleKL1Offset; }`.

The fallback ladder when L1 will not hold the merged buffers, `:95` and `:224`:
`回退 SCALE_L1_BUFFER_NUM（通常 16 → 8 → 4 → 2）直到成立`, and if 2 still does not fit,
`说明 A/B pingpong 本身已经吃满 L1，此时本优化不可用`. A declared exit, not a forced fit.

One cross-reference in the file is stale: `:234` names `modeling_reference.md §2.2` as the
A-Full-Load document. No file of that name exists anywhere in this shelf; the A-Full-Load document
is `fullload_design.md`. Recorded in `harvest/standing/950-bp.md`; it is a link defect, not a claim
defect, and no slot is spent on it.

Nothing in this section is measured. The synchronisation claim is source plus prose; the two failure
modes are upstream's disclosures, which are strong evidence about what happened once and are not
measurements of what happens.

## 4 · Procedure
Proposed, runnable later on a named 950 board. Never run in this phase. The claims here are
correctness claims, so the procedure is built around deliberate breakage rather than timing.

Arm 1 — the period. Build the coalesced kernel at `SCALE_L1_BUFFER_NUM = 16` and echo, per outer
iteration, whether a scale MTE2 was issued and which scale buffer id was released. The claim is
exact and checkable: a scale fetch on `iter0 ≡ 0 (mod 16)`, a release on
`iter0 ≡ 15 (mod 16)` or on the final iteration, and the two buffer ids alternating. No timing is
needed for this arm.

Arm 2 — the offset, broken on purpose. Build twice, once with `scaleKL1IterOffset` present and once
with it deleted, and compare both against an FP64 CPU reference for the whole of C, reporting max
relative error **per K segment index**. Upstream predicts the broken build's error grows with the
segment index. This arm is what gives the checker a positive fixture (§5).

Arm 3 — the hang, broken on purpose, with a timeout. Choose `K` not a multiple of `scaleKL1`
(e.g. `scaleKL1 = 8192`, `K = 12288`), build with and without the `|| iter0 == kL1Iter_ - 1`
disjunct, and launch both under a wall-clock timeout. Upstream predicts the second never returns.
A hang arm needs a declared timeout and a declared recovery (`ASCEND_RT_VISIBLE_DEVICES` released,
die re-sampled, case marked `hang` not `fail`), and both are declared here.

Arm 4 — the non-multiple `scaleKL1`. Set `scaleKL1 = 3 × kL1 / 2` so the ratio is not integral, and
record what the host tiling does: reject, round, or accept. Upstream asserts the accept path is
wrong; whether the shipped tiling can even reach it is unknown from reading.

Variance floor is not needed for Arms 1–4 — none of them is a timing comparison. If timing is added
later it takes the floor discipline of `0312`.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three idle samples; re-sample after; discard if the die moved. Arm 3 additionally
re-samples occupancy after the timeout and refuses to start the next arm until the die reads idle,
because a hung kernel that was killed is not the same as a die that is free. Refuses to assume: that
a free die stays free; that a die may be substituted; that a timeout means a hang (a timeout that
also occurs in the *correct* build is a machine problem, and the correct build is always launched
first as the control).

## 5 · Checker — acceptance declared before the run
Verdict `period_exact` = true iff Arm 1's echoed fetch and release iterations match
`iter0 ≡ 0 (mod scaleKL1Ratio_)` and `iter0 ≡ scaleKL1Ratio_ − 1 (mod scaleKL1Ratio_) or
iter0 == kL1Iter_ − 1` with no exceptions. Exact — one stray fetch falsifies it.

Verdict `offset_growth` = true iff Arm 2's broken build shows max relative error monotonically
non-decreasing in K-segment index while the intact build stays at reference tolerance across all
segments.

Verdict `hang_confirmed` = true iff Arm 3's build without the disjunct exceeds the timeout while the
build with it completes, on the same shape, in the same session.

The exit code is not the verdict for any arm — Arm 3's whole point is a process that never exits.

Three guards. First, the intact build is always run first and must pass; a broken-build failure
means nothing if the control also fails. Second — this is where the checker is made able to go red —
Arms 2 and 3 are *themselves* the positive fixtures: the checker must **find** the planted offset
defect and the planted hang. If Arm 2's broken build passes the precision comparison, the comparison
is not covering the tail K segments and every green from it is void; if Arm 3's broken build
completes, either the shape does not actually have a non-multiple `K` (echoed and verified) or the
release condition is not what the source says. A checker that could only confirm the intact build is
clean would be the known blind species, and this arm structure is what excludes it. Third, Arm 2's
error is reported per K-segment, never as a single maximum: a single max would be identical in shape
to a first-segment error and would lose the one signature upstream gives.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The two failure modes are
upstream's disclosures about its own implementation; no kernel was built, no hang was observed, and
no error was computed.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The entry does not establish that two scale buffers suffice at any
`scaleKL1Ratio` — upstream asserts it and gives no bound; a ratio large enough that the merged fetch
does not complete before its reuse would break it, and nothing here rules that out. It does not
establish the benefit of coalescing (that is `0312`) and carries no number. The three failure modes
are upstream's disclosures, which record what happened once on an unnamed part, not what happens.
The fallback ladder `16 → 8 → 4 → 2` is a policy with no measured basis. `MXFP_DIVISOR_SIZE_LOCAL`
and `MXFP_MULTI_BASE_SIZE_LOCAL` appear in every buffer-size expression in the file and are never
defined (recorded in `harvest/standing/950-bp.md`); the worked ladder in `0312` §3 only makes sense
if the first is 32, which is an inference, not a statement. The stale `modeling_reference.md`
cross-reference at `:234` is recorded and not repaired — `upstream/` is read-only. BOARD is
`family-claimed(unverified)`: no file in this family names a chip (`0347`). Nothing transfers to the
other book (RULES.md Art. 1).
