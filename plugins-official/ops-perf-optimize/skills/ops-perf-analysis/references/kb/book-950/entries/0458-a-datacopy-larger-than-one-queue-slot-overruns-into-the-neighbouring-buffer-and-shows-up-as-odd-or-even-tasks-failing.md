```
ID:        0458-a-datacopy-larger-than-one-queue-slot-overruns-into-the-neighbouring-buffer-and-shows-up-as-odd-or-even-tasks-failing
LABEL:     trap
LEVEL:     L2 (memory hierarchy & residency)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-tiling-design/references/flashattention/design.md:231-239 —
           "#### Q2:单次 DataCopy 量是否 ≤ 单槽容量? / 回答:**所有 `DataCopy(UB, GM, ...)` /
           `DataCopy(GM, UB, ...)` 调用,单次搬运的字节数是否都不超过对应 TQue 的单槽容量?** /
           若不满足,**必须实施 chunk loop 切分**,公式:`mSplit = 单槽字节容量 / (cols × sizeof(elem))`。
           V1 / V2 必须**对称**做 chunk loop,不能只切一边。 / **踩坑警告**:`mEff × cols × sizeof(elem)
           > 单槽容量` 时单次 DataCopy 会溢出 UB,破坏邻接 buffer。单 task / 单 s2 小用例可能蒙混过关
           (恰好落邻接 buffer 没人覆写),multi-task / multi-s2 时被并发 task 覆写 → 表现为"奇/偶 task
           FAIL"或周期性 chunk 错位。"
SOURCE:    same file:264 — "- [ ] **清单 1(streaming UB 容量)**:所有 TQue 单槽容量 × depth 列清;
           所有 kernel 内 DataCopy 量 ≤ 单槽;超容位置已实施 chunk loop;V1 / V2 chunk loop 对称
           (切分公式 / softmax stat slot 偏移 / SoftMaxShapeInfo.srcM / causal mask 行映射四方面对称)"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a deliberately oversized single `DataCopy` into a UB queue slot on a named 950 board that
           faults, or that is clamped, or that is refused at compile time — the overrun would then be
           caught by the toolchain rather than silently corrupting a neighbour, and the whole
           "odd/even task FAIL" mechanism would have no subject. Equally: an oversized copy that
           corrupts a neighbouring buffer while a single-task single-KV-block case still passes is
           exactly the observation this entry predicts, and the smallest case at which it starts to
           fail is the number the entry lacks.
```

# 0458 · A DataCopy larger than one queue slot overruns into the neighbouring buffer, and shows up as odd or even tasks failing

## 1 · Claim
Upstream asserts an obligation on every `DataCopy` between GM and UB in a FlashAttention-class kernel:
the bytes moved in one call must not exceed the single-slot capacity of the `TQue` involved. Upstream
asserts that when it does — when `mEff × cols × sizeof(elem)` exceeds the slot — the copy overruns UB
and damages the adjacent buffer, with no fault. Upstream asserts a specific and unusual symptom
profile for the resulting defect: a single-task, single-KV-block case may pass by luck, because the
region it spills into happens not to be rewritten by anyone; with multiple tasks or multiple KV blocks
a concurrent task overwrites it, and the failure presents as "odd/even task FAIL" or as a periodic
chunk misalignment. Upstream asserts the remedy is a chunk loop with
`mSplit = 单槽字节容量 / (cols × sizeof(elem))`, and that the `V1` and `V2` stages must chunk
**symmetrically** in four named respects: the split formula, the softmax statistics slot offset,
`SoftMaxShapeInfo.srcM`, and the causal mask's row mapping. Not established here.

## 2 · The wrong branch this removes
Without this entry an agent sizes a `TQue` by its total footprint. `InitBuffer(queue, depth, bytes)`
reads as "give this queue `depth × bytes`", and a copy of `mEff × cols × sizeof(elem)` bytes into a
queue holding more than that looks safe — the queue *does* have room. It does not have room in one
slot, and a slot is the unit a single `DataCopy` writes into. The arithmetic error is off by a factor
of `depth`, which is typically 2, so the copy that overruns is the one that is merely twice too big —
comfortably inside the queue and outside the slot.

The normal checks fail here in a way this book has an entry species for. The obvious check is "does the
test pass", and upstream says the small test passes *for the wrong reason*: the spilled bytes land in
a region nobody happens to read. The obvious second check is "does UB total occupancy fit", which is a
different question (`design.md §4.1 Q3`) and which this defect satisfies. So both checks a careful
agent would run are green while the kernel is corrupting memory.

The second wrong branch is the asymmetric fix. Having found the overrun in `V1`, an agent chunks `V1`
and leaves `V2` whole — `V2`'s copies may genuinely be smaller, so nothing forces the change. Upstream
says both must chunk, and names four things that must agree, of which only the first is the obvious
one. `SoftMaxShapeInfo.srcM` and the causal mask row mapping are per-chunk quantities: if `V1`
processes rows in chunks and `V2` processes them whole, the softmax statistics slot each stage reads
is indexed differently, and the mask rows `V1` masked are not the rows `V2` normalises.

## 3 · Ground / Source
The obligation, the formula and the symptom, `references/flashattention/design.md:231-239`:

```
#### Q2:单次 DataCopy 量是否 ≤ 单槽容量?

回答:**所有 `DataCopy(UB, GM, ...)` / `DataCopy(GM, UB, ...)` 调用,单次搬运的字节数是否都不超过对应 TQue 的单槽容量?**

若不满足,**必须实施 chunk loop 切分**,公式:`mSplit = 单槽字节容量 / (cols × sizeof(elem))`。V1 / V2 必须**对称**做 chunk loop,不能只切一边。

**踩坑警告**:`mEff × cols × sizeof(elem) > 单槽容量` 时单次 DataCopy 会溢出 UB,破坏邻接 buffer。单 task / 单 s2 小用例可能蒙混过关(恰好落邻接 buffer 没人覆写),multi-task / multi-s2 时被并发 task 覆写 → 表现为"奇/偶 task FAIL"或周期性 chunk 错位。
```

Three properties of this passage make it worth an entry rather than a checklist line.

First, the symptom is *diagnostic*, which is rare. "Odd tasks fail and even tasks pass" is not a
generic wrongness; it is the fingerprint of a buffer being written by whichever task ran into it, and
in a double-buffered pipeline the interfering task alternates. An agent that has this entry can read
that symptom backwards to the cause; without it, "odd tasks fail" reads as a synchronisation defect,
which is where `0453`'s slot-formula errors also point, and the two have different repairs.

Second, upstream states that the small case *passes*, and gives the reason — `恰好落邻接 buffer 没人
覆写`. That is an explicit warning against inferring safety from a green MVP, and it is the same
species this book records at `0395` (a passing small aligned shape establishes nothing about the tail)
from an unrelated family. Two independent-in-authorship instances of one epistemic failure inside one
corpus is itself worth recording, and it is why §4's ladder starts below the region where the defect
is expected to appear.

Third, the remedy formula shares the shape of the streaming chunk formula at `:465`
(`chunkRows = chunkBufferBytes / (D_align × sizeof(compute_T))`, carried at `0456`) but is not the
same expression: `mSplit` divides by `cols × sizeof(elem)` where `chunkRows` divides by
`D_align × sizeof(compute_T)`. These agree when `cols == D_align` and the compute type is the element
type, and diverge otherwise — for instance where the copy is of the `[Bq, Bk]` score matrix rather
than the `[Bq, D]` output. Upstream never says whether one chunk loop serves both or whether an
operator has two. Recorded as `Q-950fin-06`.

The four-way symmetry requirement, `:264`:

```
- [ ] **清单 1(streaming UB 容量)**:所有 TQue 单槽容量 × depth 列清;所有 kernel 内 DataCopy 量 ≤ 单槽;超容位置已实施 chunk loop;V1 / V2 chunk loop 对称(切分公式 / softmax stat slot 偏移 / SoftMaxShapeInfo.srcM / causal mask 行映射四方面对称)
```

`SoftMaxShapeInfo.srcM` appears here and again at `:384` and `subfamilies.md:129`, where it carries a
second obligation from a different cause: `SoftMaxShapeInfo.srcM = mEff`(不是 mPad), the effective
row count and not the aligned one, so padding rows do not enter the reduction. Under chunking, `srcM`
becomes a per-chunk effective count, and the two obligations compose: the last chunk of a padded block
has an effective count that is neither `mEff` nor the chunk height. Upstream states both requirements
and never states their composition. Recorded as `Q-950fin-07`.

Two locations in one repository are one origin (RULES.md Art. 3).

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind on three consecutive idle samples only; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and
discard the case if the die moved.

**Arm 1 — the overrun, isolated.** Not a FlashAttention kernel: one kernel that allocates two adjacent
UB buffers through `TPipe`, fills the second with a known sentinel pattern, and issues a single
`DataCopy` into the first of `k × slot_bytes` for `k ∈ {0.5, 1.0, 1.5, 2.0, 3.0}`. After each, copy
both buffers out and report (a) whether the kernel faulted, (b) the sentinel's survival in the second
buffer, byte-exactly. This is the claim's mechanism with nothing else in the frame. `k = 1.0` is the
boundary and must be clean; `k = 0.5` is the control.

**Arm 2 — the symptom ladder, which is the entry's reason.** A GQA kernel with one `DataCopy`
deliberately oversized by a factor of two, run across `tasks_per_core ∈ {1, 2, 4}` × `s2N ∈ {1, 2, 4}`.
Report, per cell, the fraction of runs that disagree with the FP64 reference **and which tasks
disagree, by index parity**. Upstream predicts the `(1, 1)` cell passes and that failures at higher
cells sort by parity. The parity structure is the finding; a bare failure rate would not distinguish
this defect from any other.

**Arm 3 — the asymmetric chunk loop.** The correct build with `V1` chunked and `V2` whole, at
`mEff > chunk height` with causal masking on. Report per-row agreement, not aggregate. Upstream's four
symmetry axes predict specific damage: rows beyond the first chunk should carry the wrong softmax
statistics and the wrong mask. Retained even though it is expected to bite, because *which* rows
disagree separates the four axes from each other.

**Arm 4 — the two formulas, retained because it may not bite.** Echo `mSplit` and `chunkRows` from a
build that carries both, at a shape where `cols ≠ D_align` (a `[Bq, Bk]` score-matrix copy with
`Bk ≠ D`). If one chunk loop serves both copies, `Q-950fin-06` is answered as "one loop, and it is
sized by the tighter of the two"; if the build carries two loops with two heights, that is the answer
instead. Either resolves an open question that no run is otherwise needed for.

Refuses to assume: that a free die stays free, or that a die may be substituted; that a slot's byte
capacity is what the host computed (each arm echoes `slot_bytes` and `depth` as the kernel sees them);
that a green `(1, 1)` cell means anything (arm 2's whole design assumes it does not); that a fault is
the expected outcome — arm 1 exists precisely because upstream says there is none; that runs are
deterministic (every cell is repeated ≥20 times and the disagreeing fraction is reported, since
upstream's mechanism is a concurrent overwrite).

## 5 · Checker — acceptance declared before the run
Verdict `sentinel_survives(k)` from arm 1, boolean per `k`, declared before the run. Acceptance for the
mechanism: `sentinel_survives(0.5) == sentinel_survives(1.0) == true` and `sentinel_survives(k) == false`
for `k > 1`. The OVERTURN fires iff arm 1 faults or is refused at compile time for `k > 1` — the
overrun would then be caught by the toolchain and could not be silent.

Verdict `parity_structured(cell)` from arm 2 ∈ {`all_pass`, `parity_split`, `all_fail`, `unstructured`}.
Acceptance for upstream's symptom: `all_pass` at `(1, 1)` and `parity_split` in at least one cell with
`tasks_per_core ≥ 2`. `unstructured` at every cell would mean the defect is real but the fingerprint
upstream gives is not, which is a correction to the entry rather than a refutation of the overrun.

Verdict `asymmetry_damage_rows` from arm 3: the set of disagreeing row indices, reported, not
summarised.

The exit code is not the verdict: every arm here exits 0, and that is the entry's whole point — the
overrun is defined by the absence of a fault. Guards: (1) arm 1's sentinel is compared byte-exactly and
the checker fails red if the sentinel buffer was never read back, because a comparison that silently
skipped is indistinguishable from a comparison that passed — this is the blind-checker species this
book records at the classifier-silence entries; (2) **the input that makes this checker go red**:
arm 1 at `k = 0.5`, where the sentinel must survive — if it does not, the two buffers are not adjacent
in the layout the harness assumes, and every `k > 1` result is an artifact of the wrong neighbour; (3)
no cell of arm 2 is reported without its repetition count, its per-parity breakdown, its echoed
`slot_bytes` and `depth`, its CANN pin and its atol.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The obligation, the split
formula, the overrun warning with its stated small-case pass, the parity symptom and the four-axis
symmetry requirement are file reads performed at drafting time. The observation that `mSplit` and
`chunkRows` are different expressions that coincide only when `cols == D_align`, and the observation
that chunking composes with the `srcM = mEff` rule in a way upstream never states, are readings of
upstream's own lines, not observations of a build.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The entry does not establish that an oversized `DataCopy` is silent
on this hardware — upstream asserts it and no toolchain behaviour was checked. It does not establish
the parity symptom, which is upstream's description of a defect someone met, not a readout. It does not
establish the smallest case at which the defect becomes visible; upstream says the single-task
single-block case may pass, `可能` — may, not will — so even the negative half is hedged. It does not
establish that the four symmetry axes are the complete set. It does not resolve whether one chunk loop
or two serve an operator with copies of different widths (`Q-950fin-06`), nor how `SoftMaxShapeInfo.srcM`
is set for a partly-padded last chunk (`Q-950fin-07`). It says nothing about `DataCopyPad`, which
upstream uses elsewhere in the same operator (`0461`) and which has different alignment obligations.
No board token appears in either passage, so BOARD is `family-claimed(unverified)`; §4 names
950PR/950DT only as where our run would happen. Nothing here is established for any 910-family board.
