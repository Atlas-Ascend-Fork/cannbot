```
ID:        0038-a-budgeted-counter-and-updatemask-fold-the-tail-into-the-last-beat
LABEL:     knowledge
LEVEL:     L5 (compute & numerics)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/single-core-pipeline/techniques/vec-13-vf-tail-unified-mask.md:14 — "`UpdateMask<float>(cnt)` 每调用一次消耗一个 VL 宽度并**递减 `cnt`**：满拍返回全 mask，`cnt` 不足一个 VL 时自动返回窄化 mask … **一个循环、一份计算体**覆盖主体 + 尾块"
           ops/ascendc-perf-optimize/references/single-core-pipeline/techniques/vec-13-vf-tail-unified-mask.md:48 — "每个被处理的「行 / 段」进入主循环前**必须重置计数器**（`p1 = part1Num; p2 = part2Num;`），否则第二行起 mask 已被上一行递减耗尽"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a build on a named 950 board in which the unified-mask form is not faster than separate
           tail loops at a shape whose tail share is large, with instruction-cache pressure
           unchanged — the duplicated compute body would then cost nothing worth removing.
```

# 0038 · A budgeted counter and UpdateMask fold the tail into the last beat

## 1 · Claim
Upstream asserts (card vec-13, 性能数据 待实测) that each call to `UpdateMask<T>(cnt)` consumes
one vector-length of the counter and decrements it in place, returning a full mask while the
remainder exceeds a VL and a narrowed mask when it does not; and that budgeting the total length
into per-half counters — adding the tail to whichever counter owns the last beat — lets one main
loop with one copy of the compute body cover both the body and the tail, replacing a main loop
plus one or two separate tail loops that duplicate the body. Not established here.

## 2 · The wrong branch this removes
Separate tail loops are how tails are normally written, and they are correct. Their cost is
threefold and none of it appears as a ratio: the compute body exists in two or three copies
(instruction-cache pressure), the tail boundary arithmetic
(`tailNum`/`tailTwoVL`/`tailOneVL`/`tailLen`) is intricate and is where out-of-range writes come
from, and every edit to the computation must be applied to every copy or the copies diverge
silently. An agent optimising such a kernel will tune the main loop and leave the tail copies
behind, so the very shapes with the largest tail share get the least-optimised code.

The counter-reset rule is the trap inside the repair, and it is why this entry is not simply
"use UpdateMask": because the counter is decremented by reference, a second row entering the loop
with an exhausted counter produces an empty mask and writes nothing — a silent, row-dependent
correctness failure.

## 3 · Ground / Source
`vec-13:6-10` diagnostic: a VF handling a length not divisible by VL with a main loop plus one or
two tail loops; the tail loops duplicating the whole load/compute/store body; boundary quantities
intricate and easy to overrun; worst when one beat spans several VL halves, where the tail must
distinguish "tail > 1 VL" from "tail ≤ 1 VL".

`vec-13:19-39` before/after. The budget, quoted because it is the mechanism:
> uint32_t loopSize   = 2 * VL_FLOAT32_SIZE;             // 一拍两个 VL 半区
> uint16_t dLoopCount = (dLen + loopSize - 1) / loopSize;// 单一循环次数，已含尾块
> uint32_t part1Num   = (dLoopCount - 1) * VL_FLOAT32_SIZE;
> uint32_t part2Num   = part1Num;
> uint32_t tailNum    = dLen - part1Num - part2Num;
> if (tailNum > VL_FLOAT32_SIZE) { part1Num += VL_FLOAT32_SIZE; part2Num += (tailNum - VL_FLOAT32_SIZE); }
> else                          { part1Num += tailNum; }  // 尾 <= 1 VL：全落 part1，part2 末拍 mask 空

Stop rules, `vec-13:46-50`: reset the counters before every row or segment (quoted in SOURCE); the
budget must agree exactly with the offset stepping (`i*loopSize`, `+VL`) or the loop reads out of
range or drops the tail; and the counters must be `uint32_t`, since `UpdateMask` decrements by
reference and a narrow type truncates. Source at `:54`: RoPE arch35 `BatchInterleaveModeVF`,
against the single-row `InterleaveModeVF` as the counter-example.

Note that the code uses a `VL_FLOAT32_SIZE` symbol where 0252 requires `GetVecLen()/sizeof(T)`;
the same inconsistency is recorded there.

## 4 · Procedure
Later phase, needs a card; device selection per 0010, board token from the driver readout.
1. Build one interleave-style VF two ways from a common tree: (T) main loop plus two tail loops;
   (U) single loop with budgeted counters and `UpdateMask`. Record `md5sum` of both.
2. Run over a shape set whose `dLen mod loopSize` covers: 0, one element, just under one VL, just
   over one VL, and just under two VLs — the four boundaries the budget's `if` distinguishes.
3. Run every shape with at least three rows, so the counter-reset rule is exercised; and run build
   U a third way (U') with the reset deliberately omitted.
4. Capture `aiv_time`, instruction count from the disassembly, five repetitions, median and spread;
   compare every output element against a host reference.

## 5 · Checker — acceptance declared before the run
Verdict variables `correct(build, shape)` element-wise, `icount(build)`, and `gain(shape)`.
Acceptance: `correct(U, shape)` for all five boundary shapes and all row counts;
`icount(U) < icount(T)`; `gain` positive where the tail share is large. And the declared
expectation for the negative arm: `correct(U', shape)` must be false for rows beyond the first.

Exit code is not the verdict. The output comparison covers every element including the tail —
comparing only the first VL, or comparing a norm, would pass a kernel that writes nothing to the
tail, which is precisely the failure the reset rule prevents.

Red input: build U', the reset omitted. If it passes, the shape set is single-row somewhere it
should not be, and the run is void rather than confirmatory.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; 待实测 upstream. `UpdateMask`'s decrement-by-reference semantics are asserted by
the card and not verified here. No board, shape, or dtype is established; the budget shown is for
fp32 with two VL halves per beat, and other dtypes change `VL` and therefore the arithmetic. It
does not establish the instruction-cache benefit numerically, only that the body exists once
instead of three times. Nothing transfers to the 910 book.
