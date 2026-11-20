```
ID:        0319-the-only-doublebuffer-design-in-the-shelf-sits-in-a-950-family-and-carries-no-950-number
LABEL:     boundary
LEVEL:     L2 (memory hierarchy & residency)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
           # the Elementwise family is marked DAV_3510 in the shelf SKILL.md; every capacity figure
           # inside the document names a 910-family part instead. No 950 number exists in the file.
SOURCE:    ops/ascendc-performance-best-practices/SKILL.md:37 — "| Elementwise 逐元素类 | Sin, Cos,
           Abs, Exp | DAV_3510 | ✅ [双缓冲设计](reference/elementwise/double_buffer_design.md) ·
           [向量化效率优化](reference/elementwise/vector_efficiency_design.md) |"
SOURCE:    ops/ascendc-performance-best-practices/reference/elementwise/double_buffer_design.md:79-83
           — "Required UB = tile_size × sizeof(dtype) × buffer_num × num_tensors / Available UB =
           192KB (Ascend 910B3) / Example: FP16, 2 tensors (in+out), double buffer / = 12288 × 2 ×
           2 × 2 = 98304 bytes = 96KB [PASS]" ; :246-249 — "7. **同一 TPosition 上 QUE Buffer 数量
           受限**（参考官方文档）。- Atlas A2 训练系列产品（如 910B1）：同一 TPosition 上 QUE Buffer
           不超过 **8** 块。- Atlas 训练/推理系列产品：同一 TPosition 上 QUE Buffer 不超过 **4** 块。"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  the discovery, anywhere in the upstream repository, of a DoubleBuffer capacity or
           queue-count figure scoped to DAV_3510 — the gap this entry records would then be a
           reading failure rather than a documentation gap, and the entry is deleted.
```

# 0319 · The only DoubleBuffer design in the shelf sits in a 950 family and carries no 950 number

## 1 · Claim
Upstream asserts, in its operator-family index, that the Elementwise family targets `DAV_3510` and
routes its double-buffering knowledge to one document. That document states its UB budget
inequality — `Required UB = tile_size × sizeof(dtype) × buffer_num × num_tensors` — and then
evaluates it against `Available UB = 192KB (Ascend 910B3)`. It states a per-`TPosition` queue-buffer
limit and gives two values, one for "Atlas A2 训练系列产品（如 910B1）" (≤ 8) and one for
"Atlas 训练/推理系列产品" (≤ 4). It states no DAV_3510 UB capacity, no DAV_3510 queue limit, and no
DAV_3510 measurement of any kind. Not established here — and specifically, nothing in the document's
capacity arithmetic is carried into this book, because every constant in it names a part of the
other family (RULES.md Art. 1).

What *is* carried is the mechanism, which the document states without architecture: double buffering
is enabled by `InitBuffer`'s `num` parameter, it doubles the queue's UB footprint, the host-side
`ub_factor` must be halved in the same change, and the tile count doubles so tail handling must be
recomputed. Those are structural claims about the AscendC programming model and they name no chip.

## 2 · The wrong branch this removes
An agent asked to enable double buffering on a 950 elementwise operator opens the family's own
design document, finds a worked UB budget, and uses it. The budget says 192 KB. The 950 figure is
248 KB (`950:0209`), so the agent leaves 22 % of the buffer unused for the life of the kernel —
silently, with no symptom in a profile, exactly the failure `950:0209` §2 describes for a
conservative UB constant. The document is not lying; it is a 910 worked example that the index cell
routed a 950 reader to.

The queue-count limit is worse in kind, because there the agent has no value at all. `≤ 8` is
attributed to A2 training parts, `≤ 4` to "Atlas 训练/推理系列产品", and DAV_3510 is neither of
those in upstream's own vocabulary map (which gives ASCEND950 = Atlas A5). An agent that picks 8
because it is the larger, or 4 because it is the safer, has invented a hardware limit. The document
even walks through the arithmetic — `VECIN` and `VECOUT` both map to `TPosition::VECCALC`, so
`inQueue(2) + outQueue(2)` occupies 4 blocks — and concludes `虽未达到 910B1 的上限，但扩展时需注意`,
comparing a 950-family design against a 910B1 ceiling.

The third and most general branch: reading a family's 適用架構 cell as a guarantee that everything
under it is scoped to that architecture. The cell routes; it does not scope. This shelf's own bank
document does it the other way — no family marking, correct per-architecture rows (`0314`) — so an
agent cannot infer scope from placement in either direction, and must check the sentence.

The correct posture on 950 is therefore: take the mechanism, refuse the constants, and query the
capacity at runtime (`950:0207`, `950:0141`). The document itself supports that reading — its own
adaptive-decision snippet turns double buffering *off* when UB is large enough (`0321`), which is a
decision that cannot be made against a hard-coded 192 KB.

## 3 · Ground / Source
The routing cell, `SKILL.md:37`:

```
| Elementwise 逐元素类 | Sin, Cos, Abs, Exp | DAV_3510 | ✅ [双缓冲设计](reference/elementwise/double_buffer_design.md) · [向量化效率优化](reference/elementwise/vector_efficiency_design.md) |
```

The budget, `double_buffer_design.md:77-84`:

```
**UB 内存预算校验：**
Required UB = tile_size × sizeof(dtype) × buffer_num × num_tensors
Available UB = 192KB (Ascend 910B3)

Example: FP16, 2 tensors (in+out), double buffer
  = 12288 × 2 × 2 × 2 = 98304 bytes = 96KB [PASS]
```

Re-derived: `12288 × 2 × 2 × 2 = 98304` ✓, `98304 / 1024 = 96 KB` ✓, and `96 ≤ 192` ✓. The
arithmetic is right; the constant is another architecture's.

The queue limit, `:246-249`:

```
7. **同一 TPosition 上 QUE Buffer 数量受限**（参考官方文档）。
- Atlas A2 训练系列产品（如 910B1）：同一 TPosition 上 QUE Buffer 不超过 **8** 块。
- Atlas 训练/推理系列产品：同一 TPosition 上 QUE Buffer 不超过 **4** 块。
- `QuePosition::VECIN` 与 `QuePosition::VECOUT` 底层均映射到 `TPosition::VECCALC`（UB），因此
  `inQueue(2) + outQueue(2)` 合计占用 **4** 块。虽未达到 910B1 的上限，但扩展时需注意。若需更多
  buffer，应按官方建议**合并到一块 buffer 通过偏移使用**，而非继续增加独立队列。
```

A `grep -n "950\|3510\|arch35\|A5"` over both Elementwise files returns nothing. The whole family —
two documents, 490 lines — contains no 950 token, while the index cell that routes to it says
`DAV_3510`. Recorded as `C-950bp-010`.

The mechanism claims that *do* carry, `:132-139` and `:228-236`:

```
// 注意：TQue 模板参数 depth 为队列深度（连续 EnQue 次数），与 double buffer 无关。
//       非原地操作场景下 depth 推荐为 1（编译器有特殊优化）。
//       double buffer 仅通过 InitBuffer 的 num 参数控制（num=2 开启）。
...
1. **仅改 InitBuffer 的 num 不够！必须重构循环为预取模式**。
2. **Tiling 联动：InitBuffer 的 num 翻倍时 ub_factor 必须减半**。双缓冲使队列内存翻倍，若不调整
   ub_factor，总 UB 用量超限会导致编译失败或运行时越界。
4. **Tail tile 处理**：tile_size 减半后，tile 数量翻倍，需确保尾 tile 处理逻辑正确更新。
```

The depth-versus-`num` distinction is already carried by `950:0019` from the other shelf and is
cited here rather than re-entered. The loop-restructure requirement is `0320`; the off switch is
`0321`. The `ub_factor` halving and the tail-count doubling are carried in `0320` §1, since they are
consequences of the same change.

The buffer-strategy ladder, `:50-56`, is architecture-free and is the one piece of routing content
in the file: Double (2) for general memory-bound work; Triple (3) for AIC/AIV mixed cores where
movement, Cube and Vector must overlap; a 2×2 matrix (4) for matmul splitting M and K; `TQueBind`
(1 physical buffer shared between `VECIN` and `VECOUT`) for read-modify-write in place, saving 50 %;
custom hand-flagged ping-pong for multi-level L1/L0 storage as in FlashAttention.

## 4 · Procedure
Proposed, runnable later on a named 950 board. Never run in this phase. This entry's claim is that a
number is missing, so §4 is what would supply it rather than what would confirm the absence.

Arm 1 — the UB capacity the budget should use. `GetCoreMemSize(CoreMemType::UB, ubSize)` on the
target part, plus the allocation boundary by bisection at 32 B granularity (`950:0209` §4 Arm B,
which this entry does not duplicate but does depend on). The output is the value that replaces
`192KB (Ascend 910B3)` in any 950 restatement of this document.

Arm 2 — the queue-buffer ceiling on DAV_3510, which no document gives. Build a kernel that declares
`k` queues on `TPosition::VECCALC` with `InitBuffer(..., 1, size)` each, for `k = 1 … 16`, and record
the largest `k` that compiles and launches. Repeat with `InitBuffer(..., 2, size)` to see whether the
limit counts *queues* or *blocks* — upstream's arithmetic (`inQueue(2) + outQueue(2)` = 4 blocks)
says blocks, and that is checkable.

Arm 3 — whether the limit is a hardware ceiling or an allocator policy. At the largest legal `k`,
reduce each buffer to the 32 B minimum and try `k + 1`. If the refusal moves with the sizes, the
limit is capacity; if it does not, it is a count.

Device selection: operator names the index; probe echoes it with `compiler/version.info`; occupancy
sampled three times at 20 s spacing before binding and re-sampled after; no die substituted. Refuses
to assume: that a free die stays free; that a die may be substituted; that a compile failure and a
launch failure are the same thing (both are recorded separately, since a count limit may be enforced
at either); that the part is un-partitioned — a vNPU slice reports a smaller UB (`950:0207`) and
would move Arm 1 without moving Arm 2.

## 5 · Checker — acceptance declared before the run
Verdict `ub_950` = Arm 1's allocation boundary. There is no pass condition; the value is the
deliverable. It is reported alongside the resolved SoC string, because a capacity read against the
wrong resolved ini is a mismatch with no hardware behind it (`950:0204`).

Verdict `que_max_blocks` = the largest total block count Arm 2 admits on `TPosition::VECCALC`.
Declared before the run: the three named outcomes are `4` (the 950 part shares the "Atlas
训练/推理" ceiling), `8` (it shares the A2 training ceiling), or any other value (both upstream
figures are 910-specific and the 950 number is new). No outcome is a "confirmation" of the
document, because the document states no 950 value — which is the entry's whole point.

Verdict `limit_kind` ∈ {capacity, count} from Arm 3.

The exit code is not the verdict. Two guards. First — the input that makes this checker go red —
Arm 2 is run once with a buffer size deliberately large enough that even `k = 2` cannot fit. The
refusal **must** occur, and it must be distinguishable in the record from a count refusal. If a
capacity refusal and a count refusal are indistinguishable in the log, `que_max_blocks` is
unattributable and the arm is void; that is a planted positive the instrument has to find before any
of its greens mean anything. Second, no capacity figure is reported without the partition state of
the part, since the whole quantity is partition-dependent.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The 192 KB, the 8 and the 4
are upstream's figures for 910-family parts and are recorded here as *what the document says*, not
as facts about any part in this book's scope; no 950 capacity was queried and no queue was declared.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. This entry establishes a documentation gap, not a hardware fact:
it does not supply a 950 UB capacity (that is `950:0209`, itself unmeasured), does not supply a 950
queue-buffer ceiling, and does not establish that one exists. It does not establish that the 910
figures are wrong — they are correctly attributed in the source and are simply not this book's.
Nothing in the document's capacity arithmetic is carried across (RULES.md Art. 1); the 192 KB, the `≤ 8`
and the `≤ 4` appear here only as quoted text. The mechanism claims that are carried — `num` versus
depth, the `ub_factor` halving, the tail-count doubling, the buffer-strategy ladder — are stated by
upstream without any architecture and are therefore *assumed* to be model-level rather than
part-level; that assumption is not verified and is the entry's weakest joint. The
`ResourceConflictRatio`-style benefit figures in the file's own header table (`重叠度 0% → ~80-90%`,
`吞吐量提升 20-50%`) carry no case, no shape and no board, and are not carried by this entry or by
`0320`/`0321`. BOARD is `family-claimed(unverified)`. Nothing transfers to the other book.
