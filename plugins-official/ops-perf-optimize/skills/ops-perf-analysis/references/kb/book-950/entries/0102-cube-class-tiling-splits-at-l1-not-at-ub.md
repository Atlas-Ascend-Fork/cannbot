```
ID:        0102-cube-class-tiling-splits-at-l1-not-at-ub
LABEL:     knowledge
LEVEL:     L2 (memory hierarchy & residency)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/tiling/index.md:89-96 —
           "**关键区分**：Cube/融合类算子的切分粒度在 **L1**（不是 UB），L1 split 决定了单次搬运的
           数据量；L0/UB 是 L1 的进一步子切分"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured matmul or convolution case on a named 950 board where holding the L1
           footprint constant and varying only the UB allocation changes kernel wall time by more
           than run variance — that would make UB a first-class split level for Cube operators,
           which this claim denies.
```

# 0102 · Cube-class tiling splits at L1, not at UB

## 1 · Claim
Upstream asserts a four-row buffer convention that decides which capacity a tiling budget is
written against: Vec-class operators (elementwise, broadcast, conversion, part of reduction) move
GM → UB and compute in UB with no L1 participation; Cube-class operators (matmul, convolution)
move GM → L1 → L0 → Cube with L1 as the global reuse buffer and UB used only as a weight/fmap DMA
staging area; fusion-class operators (FA) use L1 + UB; MC² operators use L1 + UB + a GM-side
communication buffer. Upstream further asserts that for Cube and fusion classes the split
granularity is L1 and not UB, with L0 and UB being sub-splits of the L1 tile. Not established
here.

## 2 · The wrong branch this removes
A harness agent that has internalised "on-chip budget means UB" — which is correct for every Vec
family in this reference set and for most published AscendC advice — writes a matmul budget
inequality against UB capacity. The result is a plan that satisfies a constraint the hardware does
not enforce at that level while leaving the L1 inequality unchecked, so `baseM/baseN/baseK` are
chosen by the wrong resource. This does not fail loudly: the kernel compiles, and the L1 overflow
surfaces as an automatic `stepKb` shrink or a silent fallback to SWAT (see 0110), i.e. as a
performance loss attributed to the algorithm rather than to the budget. The normal checks do not
catch it because there is no check — the tiling schema does not carry which buffer a formula was
written against.

## 3 · Ground / Source
`ops/ascendc-perf-optimize/references/tiling/index.md:89-96`, the table in full:

```
| 算子类型 | 主要 Buffer | 说明 |
|---------|------------|------|
| **Vec 类**（Elementwise, Broadcast, Conversion, Reduction 部分） | **UB** | 数据从 GM → UB，计算在 UB 上完成，无 L1 参与 |
| **Cube 类**（MatMul, Convolution） | **L1 + UB** | 数据 GM → L1 → L0 → Cube，L1 做全局复用缓冲，UB 做 weight/fmap DMA 暂存 |
| **融合类**（FA 等） | **L1 + UB** | 多层流水，L1 承载大块数据驻留，UB 承载计算窗口 |
| **MC² 通算融合类** | **L1 + UB + GM（通信）** | 复用 matmul 的 L1/L0 层级，通信数据经 GM 侧 buffer 收发 |

> **关键区分**：Cube/融合类算子的切分粒度在 **L1**（不是 UB），L1 split 决定了单次搬运的数据量；L0/UB 是 L1 的进一步子切分。
```

The convention is honoured by the family files: matmul's budget inequality
(`matmul/fallback/tiling-flow.md:249-257`, see 0110) is written against `L1_SIZE`, and every
Vec-family budget in this subtree is written against a UB literal. It is *not* honoured by the
YAML schema at `index.md:104-137`, which emits `l1_split` / `l0_split` / `ub_split` as three
peer blocks with no marker of which one is the decision level — the discipline lives only in the
prose sentence quoted above. That placement gap is exactly the species this book records: a rule
stated in a paragraph is not a rule the consuming artifact carries (RULES.md Art. 8).

No board, arch, or `__NPU_ARCH__` guard appears anywhere in `index.md`. `L1_SIZE` itself is never
given a value in this file or in matmul's — it is one of the undefined symbols catalogued in
0111.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT, recorded as whichever ran); never
run in this phase.

Device selection: `npu-smi info -l` to enumerate, then `npu-smi info -t usages -i <id> -c <chip>`
three times at 20 s spacing; bind only if HBM-used and AICore-utilisation are at their idle floor
in all three samples; export `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after the run and discard
the case if the die moved during it.

Two-arm sweep on one matmul shape (BF16, M=1024, K=4096, N=2048 — a shape upstream's neighbour
skill already uses, so a future comparison is possible). Arm A: hold the L1 footprint constant at
one `(baseM, baseN, baseK, stepKa, stepKb)` tuple and vary only the UB staging allocation across
the whole legal range the platform reports for `CoreMemType::UB`, in the alignment step the
platform reports. Arm B: hold the UB staging allocation constant and vary `baseK` so the L1
footprint sweeps the same fraction of `L1_SIZE`. Both capacities are read at runtime via
`GetCoreMemSize(CoreMemType::UB)` and its L1 counterpart, never from a literal — see 0141. Build
every point with one compiler pin, record the pin, and md5 the binaries so two points that should
differ are shown to differ. Collect per-case `aiv_time` and `aic_time` under `msprof` with
`--aic-metrics=PipeUtilization`, ≥10 iterations, first 5 discarded.

Refuses to assume: that a free die stays free; that a die may be substituted; that the L1
capacity is the value any script default asserts (C-006 records four incompatible UB defaults in
this same subtree — the L1 literal has no better pedigree); that 950PR and 950DT share a capacity.

## 5 · Checker — acceptance declared before the run
Verdict variables `ub_span` and `l1_span`, each the (max − min) of median wall time across its
arm, normalised by the arm's own minimum. Declared before the run: the claim survives iff
`ub_span < 0.05` and `l1_span > 0.15`. It is overturned iff `ub_span > 0.15` — that is UB acting
as a first-class split level. The band between is a null result and is reported as one, not
rounded toward the claim.

The exit code is not the verdict. `msprof` returns 0 for runs that produced no metrics rows, and
a build that silently fell back to a different tiling still exits 0 — so the checker additionally
requires that the recorded `baseK`/`stepK` echoed by the host print match the tuple requested,
and fails red if any point's request and echo differ. That guard is the reason this checker can
find its own blind spot: without it, an arm in which every point silently collapsed to the same
tiling would read as `ub_span ≈ 0` and be scored as confirmation.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured; no board was touched. The entry does not establish the capacity of L1 or UB
on any board, does not establish that the Vec/Cube/fusion/MC² partition is exhaustive, and says
nothing about where FA-class operators actually split — upstream's FA directory is a stub (0169),
so its row of this table has no content behind it. The claim is about which buffer a budget is
written against; it is not a claim that UB pressure is irrelevant to Cube operators, only that
upstream does not treat it as the split level. No chip is named in the source; BOARD is
`family-claimed(unverified)` for that reason, while §4 names 950PR/950DT because that is where a
future run of ours would happen. Nothing here is established for any 910-family board.
