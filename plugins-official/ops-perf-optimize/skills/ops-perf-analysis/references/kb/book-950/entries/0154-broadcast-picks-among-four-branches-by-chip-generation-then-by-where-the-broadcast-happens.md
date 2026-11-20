```
ID:        0154-broadcast-picks-among-four-branches-by-chip-generation-then-by-where-the-broadcast-happens
LABEL:     knowledge
LEVEL:     L3 (data movement & layout)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/tiling/broadcast/fallback/tiling-flow.md:9-29,66-75 —
           "├─ DAV_2201 → UB Broadcast 静态接口 (rank=1/2, 32B对齐约束)" · "└─ DAV_3510 → 广播发生在
           哪个阶段? ├─ GM→UB搬入阶段 → 按优先级决策链选择: ① 用户强制 → 遵从 ② NLast场景 且
           尾轴≥dcache/2 → UB BRC动态接口 ③ dtype为INT8/FP16/BF16 且 尾轴32B对齐 → UB BRC动态接口
           ④ 其他 → NDDMA" · "NDDMA 硬件stride=0自动复制"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured broadcast on a named 950 board where NDDMA stride-0 replication is slower than
           a UB-side Broadcast expansion on a case the decision chain routes to NDDMA — the chain's
           default arm would then be wrong for that regime.
```

# 0154 · Broadcast picks among four branches by chip generation, then by where the broadcast happens

## 1 · Claim
Upstream asserts a broadcast branch decision beginning with axis collapse (pad left with 1s, mark
broadcast axes, merge adjacent axes with the same flag, compute strides), then: a single collapsed
dimension selects OneDim (pure elementwise, possibly with scalar inputs); more than one dimension
selects by chip generation. Upstream asserts that DAV_2201 takes the UB Broadcast static interface
with `rank = 1/2` and a 32-byte alignment constraint, while DAV_3510 asks where the broadcast happens:
if at the GM→UB load stage, a four-step priority chain decides — user force wins first, then a
non-last-axis case whose trailing axis is at least `dcache/2` takes the UB BRC dynamic interface,
then INT8/FP16/BF16 with a 32-byte-aligned trailing axis takes the same, and everything else takes
NDDMA; if the broadcast is of an intermediate result inside UB, the UB BRC dynamic interface is used
with rank 1 to 9. Upstream asserts that NDDMA achieves broadcast by hardware stride-0 replication
during the transfer, with a schedule mode selected by remaining axis count — at most 5 axes gives
`WithoutLoop` and one `DataCopy<T,5>`, more than 5 gives `WithLoop` with the innermost 5 axes on
NDDMA and outer axes in a kernel loop — plus a `FuseAxis` optimisation merging adjacent axes with the
same broadcast pattern. Not established here.

## 2 · The wrong branch this removes
The interesting content is that broadcast is not one technique but a choice of *where* the
replication happens: in the DMA engine during the load (NDDMA, stride 0), or in UB afterwards
(Broadcast API expansion). An agent that knows only the second pays UB capacity and vector time to
materialise data the transfer engine could have replicated for free. An agent that knows only the
first applies NDDMA to a case where the trailing axis is small, where per-transfer overhead dominates
and the UB-side expansion would have been cheaper — which is precisely what conditions ② and ③ carve
out.

Condition ② is the one worth reading closely: `尾轴 ≥ dcache/2`. A large trailing axis means each
replicated row is big, so a UB-side expansion amortises well; a small one means many small NDDMA
descriptors. The threshold is expressed in terms of a data-cache size that this family never states —
`dcache` appears here and nowhere else in the family — so the condition is not evaluable from these
documents alone. Condition ③ is a straightforward alignment gate.

The chip-generation split removes a third wrong branch and is the only genuine dual-architecture
branch anywhere in this tiling subtree. A prior survey established that `grep -rn "910"` over
`references/tiling/` returns nothing and that every chip-naming file names the 950 family; this
decision tree is the exception, naming DAV_2201 and DAV_3510 as peers. What that means for this book
is narrow and worth stating: the DAV_2201 arm is a fact about upstream's *950-era document*, not a
910 fact this book may carry — Art. 1 forbids the transfer, and the 910 half is not established here
(0155 §7).

## 3 · Ground / Source
The decision tree, `broadcast/fallback/tiling-flow.md:9-29`, in full:

```
给定: N个输入shape + 1个输出shape + dtype + ubSize + coreNum

Step 0 — 合轴 (DimensionCollapse):
  补维(左补1) → 标记广播轴flag → 合并相邻同flag轴 → 计算strides

Step 1 — 分支判定:
  ├─ 合轴后仅1维 → OneDim (纯Elementwise,可能有标量输入)
  │
  └─ 合轴后>1维 → 选择广播方式:
      ├─ DAV_2201 → UB Broadcast 静态接口 (rank=1/2, 32B对齐约束)
      │
      └─ DAV_3510 → 广播发生在哪个阶段?
          ├─ GM→UB搬入阶段 → 按优先级决策链选择:
          │   ① 用户强制 → 遵从
          │   ② NLast场景 且 尾轴≥dcache/2 → UB BRC动态接口
          │   ③ dtype为INT8/FP16/BF16 且 尾轴32B对齐 → UB BRC动态接口
          │   ④ 其他 → NDDMA
          │
          └─ UB内部广播 (中间结果需广播) → UB BRC动态接口 (rank 1~9)
```

The NDDMA branch, `:66-75`:

```
## 4. NDDMA Broadcast 分支 (DAV_3510专属)

**条件**: GM→UB搬入阶段，NDDMA硬件stride=0自动复制。

**流程**:
1. UB切分、多核切分与UB Broadcast相同
2. 判定schMode: 剩余轴≤5 → WithoutLoop; >5 → WithLoop
3. WithoutLoop: 一次DataCopy<T,5>完成
4. WithLoop: 最内5轴给NDDMA，外层Kernel for-loop遍历
5. FuseAxis优化: 合并广播模式相同的相邻轴
```

The UB Broadcast branch's own sub-decision, `:49-62`:

```
**流程**:
1. 从最内轴向外累乘，找到放不下的轴作为 `ubSplitAxis`
2. UB切分: `ubFormer = maxElemNum / curProduct`
3. 多核切分: 展平ubSplitAxis及其外层轴，均分给多核
4. 搬运指令优化: DataCopyPad dummy填充 → Copy → GatherMask (省tmpBuffer)

**广播方式子决策** (axis=-1):
- Broadcast静态接口约束(srcShape对齐)满足 → Broadcast API
- 否则 M>2 → DataCopyPad填充+Copy+GatherMask
- M≤2 → 逐行Duplicate
```

The scalar handling, `:104-110`:

```
| 场景 | 方案 |
|------|------|
| OneDim + 有对应TensorScalar接口 | Adds/Muls/Subs 直接对标量 |
| OneDim + 无TensorScalar接口 | Duplicate展开 + TensorTensor接口 |
| 多维 | strid=0 → NDDMA硬件复制或UB Broadcast |
```

The `sch_mode` field and the two alignment regimes, `broadcast/fallback/tiling-fields.md:42,56-62`:

```
| `sch_mode` | NDDMA调度模式 | 1=WithoutLoop (≤5轴), 2=WithLoop (>5轴) |
```
```
| 场景 | 对齐粒度 | 说明 |
|------|---------|------|
| OneDim | 128B (CACHE_LINE) | `(ubSize/bufferNum / 128) * 128 / dtype_bytes` |
| 多维 | 256B (REPEAT) | `maxElemNum对齐到 256*8/minDtypeBits` |
| NDDMA blockLen | 32B | DataCopy blockLen对齐 |
```

Three different alignment quanta in one family — 128 B for the one-dimensional branch, 256 B for the
multi-dimensional branches, 32 B for NDDMA transfer lengths — each named with a reason
(`CACHE_LINE`, `REPEAT`, `DataCopy blockLen`). This is the only place in the domain where the three
are stated side by side with their justifications, and none is given a board.

`dcache` in condition ② is used and never defined in this family. The gather family gives a
`DCache(128KB)` figure inline in one condition (0148 §3); whether it is the same quantity is not
stated anywhere, and this entry does not assume it is. Recorded in
`harvest/standing/950-tiling.md`.

The UB and multi-core formulas the branches share, `:79-102`, are quoted in 0151 §3 (the `maxElemNum`
form) and are dimensionally sound here, unlike the elewise markdown copy.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase. The DAV_2201
arm cannot be exercised on a 950 board at all, and this procedure does not pretend otherwise — it
tests the DAV_3510 chain only, and the 910-side arm is a standing question for the other book.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and discard the
case if the die moved. Variance floor first: one build, 30 in-process runs and 5 fresh-process runs.

Arm 1 — the ②/④ boundary, which is the chain's substance. Take a non-last-axis broadcast `Add`
(output `[64, 1024, T]`, second input `[64, 1, T]`) and sweep the trailing axis `T` so that
`T × dtypeSize` crosses the plausible `dcache/2` values — sweep across {8 KB, 16 KB, 32 KB, 64 KB,
128 KB} of trailing-axis bytes, which brackets a `dcache` anywhere from 16 KB to 256 KB. At each
point build both the NDDMA branch and the UB BRC dynamic branch, one compiler pin, md5 each, host
echo of `branch`, `sch_mode`, `ub_split_axis`, `ub_former`, `max_elem_num` and `core_num`. Compare
output elementwise against a CPU reference. Record `aiv_time`, MTE2 bytes and descriptor count under
`msprof --aic-metrics=PipeUtilization`, ≥10 iterations, first 5 dropped, per case. The crossover
locates `dcache/2` behaviourally, which is the only way to get it from these documents.

Arm 2 — the `sch_mode` boundary. Construct collapsed shapes with exactly 5 and exactly 6 remaining
axes, build both `WithoutLoop` and `WithLoop` where legal, and record which the host selects and
which is faster. The 5-axis limit reads as a `DataCopy<T,5>` interface bound rather than a policy
number; forcing 6 axes into `WithoutLoop` should fail to build, and that distinction is recorded.

Arm 3 — condition ③. At INT8, FP16 and BF16, sweep the trailing axis across a 32-byte alignment
boundary and record which branch the host selects and the cost of each.

Refuses to assume: that a free die stays free; that a die may be substituted; that `dcache` is
128 KB or any other value — arm 1 locates it behaviourally and reports a range, not a number
borrowed from another family; that `ubSize` or `coreNum` are the script's literals (queried, 0141);
that a forced branch was used (host echo required); that the DAV_2201 arm can be tested here.

## 5 · Checker — acceptance declared before the run
Verdict variable `nddma_cross`, the trailing-axis byte size at which NDDMA's median `aiv_time` first
exceeds the UB BRC branch's by more than the variance floor. Declared before the run: condition ② is
supported iff `nddma_cross` exists and the host's own branch selection flips within one sweep step of
it. The OVERTURN fires iff NDDMA is slower than UB BRC at every swept size on a case the chain routes
to NDDMA — the default arm would then be wrong for this regime. `dcache_implied = 2 × nddma_cross` is
reported as a derived range with its bracketing, not as a value. Verdict
`schmode_kind ∈ {interface-limit, policy}` from arm 2: `interface-limit` if 6 axes cannot be built
into `WithoutLoop`.

The exit code is not the verdict: a broadcast with a wrong stride produces wrong output and exits 0,
and stride-0 replication is exactly where a stride error hides. The elementwise comparison runs on
every arm and the checker fails red if it did not. Second guard: branch identity via the host echo of
`branch` and `sch_mode` — a forced branch the host overrode would collapse the two arms and make
`nddma_cross` unfindable, which would read as a null rather than as a void experiment. The checker
reports `void` in that case.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured. The entry does not establish the priority chain's correctness, does not
establish `dcache` (used in condition ② and defined nowhere in this family), and does not establish
the 5-axis `sch_mode` boundary. It does not establish the three alignment quanta (128 B, 256 B,
32 B), none of which carries a board. It does not establish that NDDMA stride-0 replication is free,
only that upstream describes it as hardware replication. The `DAV_2201` arm of the decision tree is
recorded here as a property of upstream's document and is **not** established for any 910-family
board — Art. 1 forbids carrying it into the 910 book, and that book must establish its own broadcast
branch independently. `DAV_3510` names an architecture covering both 950PR and 950DT, so BOARD is
`family-claimed(unverified)`; §4 names 950PR/950DT because that is where our run would happen.
