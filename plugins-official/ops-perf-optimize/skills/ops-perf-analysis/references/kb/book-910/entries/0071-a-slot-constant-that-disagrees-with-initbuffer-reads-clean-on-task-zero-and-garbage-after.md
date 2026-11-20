```
ID:        0071-a-slot-constant-that-disagrees-with-initbuffer-reads-clean-on-task-zero-and-garbage-after
LABEL:     trap
LEVEL:     L2 (memory hierarchy & residency)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-api-best-practices/references/api-buffer.md:323 — "const uint32_t slotElems = 128 * 1024 / sizeof(DATA_T);  // ❌ 误写 128KB" with ":329-330 — 任务 task=0 输出正常（偏移=0，即使常量错也不越界）… task=1+ 输出 NaN / inf"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a stage function using a per-slot constant larger than `InitBuffer`'s allocation reads within bounds at every task index on a named DAV_2201 board — i.e. the framework clamps the offset.
```

# 0071 · A slot constant that disagrees with InitBuffer reads clean on task zero and garbage after

## 1 · Claim
Upstream asserts that in mix kernels (`__mix__(N, M)`) or multi-stage operators, where several
compute-stage functions share one pair of L1/L0 buffers by rotating through slots, the per-slot
constants used inside each stage — slot element count, slot byte count, per-slot stride — must
match `InitBuffer`'s actual allocation. Upstream asserts the failure signature when they do not:
task 0 is correct because its offset is zero, and tasks 1 and above read dirty data past the end of
the buffer and produce NaN or inf. Not established here.

## 2 · The wrong branch this removes
The defect is a constant duplicated across functions that drift apart — ordinary, and ordinarily
caught. What makes it a trap here is the **detection signature**, which upstream states outright:
*task 0 always passes*, because a wrong slot size multiplied by index 0 is still 0. Every offset
error is invisible at the first task.

The consequences for validation are specific and severe:
- A single-case test passes. A test that happens to use one task passes.
- Upstream names the resulting pattern as "偶数 task PASS / 奇数 task FAIL" or "首个 task PASS /
  后续 task 全爆炸" — **periodic** failure, which reads like a race condition or a synchronisation
  bug, and sends the investigation to the pipeline rather than to a constant.
- The output is NaN or inf, not a small numerical error, so a tolerance-based comparison does flag
  it — but only on the tasks that run past index 0.

This is the third entry in this book with a first-run-passes signature: 0019 (scalar/DCache
incoherency) and 0029 (negative tail length → out-of-bounds write) are the others. Three independent
mechanisms, one detection signature — which is worth carrying as a signature in its own right. When
a kernel passes on one case and fails periodically across many, the constant-and-offset family is
where to look before the synchronisation is.

Upstream's engineering fix is a placement rule, not a diligence rule: hoist every per-slot constant
into a single header, one `constexpr` definition, every stage referencing it. A rule that lives in
one place cannot drift; a rule that must be remembered in each stage will.

## 3 · Ground / Source
`ops/ascendc-api-best-practices/references/api-buffer.md` §"多 stage 共享 L1 / L0 Buffer 的常量
一致性", lines 297-341.

Scope, line 301: "mix kernel（`__mix__(N, M)`）或多 stage 算子中，同一对 L1 / L0 Buffer 经常被多个
Compute stage 函数共享访问做轮转（例如 GEMM 算子中两个连续 Mmad 计算共享同一对 L1 输入 buffer）。"

The constants that must agree, lines 305-309: 单 slot 元素数 (`slotElems`), 单 slot 字节数
(`slotBytes`), per-slot stride / 槽偏移基数 — "**必须与 InitBuffer 的实际分配字节数一致**".

The worked defect, lines 314-323, verbatim:
```cpp
buf.InitBuffer(matAL1_, 64 * 1024 * PRELOAD_NUM);   // 每 slot 64KB
// ComputeStage1 中（正确）：
const uint32_t slotElems = 64 * 1024 / sizeof(DATA_T);   // 与 InitBuffer 一致
// ComputeStage2 中（错误！）：
const uint32_t slotElems = 128 * 1024 / sizeof(DATA_T);  // ❌ 误写 128KB
auto b = matAL1_.Get<DATA_T>()[loopSlot * slotElems];    // task=0 偏移=0 蒙混，task=1+ 读越界脏数据
```

The signature, lines 328-330, verbatim in full — the most valuable part of the passage:
"- 任务 task=0 输出正常（偏移=0，即使常量错也不越界，读到的还是合法分配区）
- 任务 task=1+ 输出 NaN / inf（偏移到 buffer 末尾外的脏数据）
- \"偶数 task PASS / 奇数 task FAIL\" 或 \"首个 task PASS / 后续 task 全爆炸\" 型周期性错误"

The engineering constraint, lines 334-341: "把所有 per-slot 常量提到单一头文件或单一 constexpr
定义，所有 stage 引用同一定义" with a `constants.h` sketch.

Note the buffers involved are L1 and L0, whose capacities on DAV_2201 are 512 KB and 64/64/128 KB
(0004, 0005) — so a 64 KB slot with `PRELOAD_NUM` slots is a substantial fraction of L1 and the
over-read lands in real allocated memory rather than in unmapped space, which is why it produces
dirty data rather than a fault.

Same repo, one origin. No second source in scope describes this failure mode.

## 4 · Procedure
Proposed, runnable later; not run. The first arm is host-side, needs no card, and is the one worth
building — this defect is catchable before it reaches a device, like 0029's.

1. Static arm, no device: over a multi-stage kernel's source, extract every per-slot constant
   expression and every `InitBuffer` allocation for the same buffer, and check that
   `slot_bytes × slot_count == allocated_bytes` and that all stages agree on `slot_bytes`. Report
   any stage whose constant differs from the allocation's.
2. Device arm, on a named die (occupancy before and after, no substitution): run the kernel over
   task indices 0, 1, 2, 3, 7 and verify each output against a host reference. **Never validate on
   task 0 alone** — that is the whole point.
3. Report per-task correctness as a vector, not an aggregate. The predicted pattern is
   correct-at-0, wrong-at-1+, and a pattern is what confirms the mechanism where a count would not.
4. Poison the region past each slot's end with a recognisable value before the run, so that an
   over-read is identifiable as an over-read rather than as arbitrary corruption.

## 5 · Checker — acceptance declared before the run
`constant_mismatches` from arm 1; `correct(task)` from arm 2.
PASS (the tiling/constant set is safe) iff `constant_mismatches == 0` AND `correct(task)` is true
for every task index tested.
The positive fixture, required and run FIRST: feed arm 1 a source with a deliberately doubled
`slotElems` in one stage and confirm it reports the mismatch. **A static check that reports clean on
a source known to contain the defect is the blind species this book tracks, and its clean verdicts
on real sources must then be discarded.** The fixture is a positive the instrument must FIND — not a
known-good source it must pass, which a check that always returns clean would also satisfy.
For arm 2, a clean `correct(0)` with no higher task tested yields NO verdict — recorded as NOT
ATTEMPTED. Declared now, because "we ran it and it passed" on task 0 is precisely the false
assurance this entry exists to prevent.
Exit code is not the verdict; an over-read into allocated memory does not fault.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; no board touched; no architecture stated by the source — this is a host- and
kernel-source arithmetic hazard whose routing rests on the surrounding document's A2/A3 context
(`api-buffer.md:277`) rather than on a hardware property, and it plausibly applies to any Ascend
part. This entry does not establish that the over-read always produces NaN or inf; that depends on
what the dirty data happens to be, and a benign value would make the defect invisible even at
task 1. It does not establish the mix-kernel `__mix__(N, M)` semantics, which upstream references
without defining. It does not cover UB-side slot rotation, only L1/L0. The static check in §4 is
proposed, not written.
