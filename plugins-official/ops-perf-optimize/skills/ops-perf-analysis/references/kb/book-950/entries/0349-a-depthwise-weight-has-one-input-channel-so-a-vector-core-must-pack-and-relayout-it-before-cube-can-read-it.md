```
ID:        0349-a-depthwise-weight-has-one-input-channel-so-a-vector-core-must-pack-and-relayout-it-before-cube-can-read-it
LABEL:     knowledge
LEVEL:     L3 (data movement & layout)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/conv/conv_common_perf_experience.md:75 —
           "**为什么需要 AIV**：DepthwiseConv2D 的 weight 是 `[C, 1, kH, kW]`，每个通道只有 1 个
           输入通道，无法直接满足 Cube 的 K 维对齐要求（K0=16 for fp16）。AIV 负责将多个 group 的
           weight 拼接（enlarge）并重排为 NZ 格式。"
SOURCE:    same file:121 — "Cube 的 L0B 要求 NZ（FractalZ）格式：`[K1, N1, K0, N0]`，其中 K0=16、
           N0=16（fp16）。DepthwiseConv2D 的 weight 原始格式是 NCHW：`[enlarge, cout/groups,
           cin/groups, kh×kw]`。" ; :127 — "GM(NCHW) --MTE2--> UB(nd) --V(DataCopyGather)--> UB(nz)
           --MTE3--> L1(BL1)" ; :66-73 — the `__mix__(1, 2)` AIC/AIV division of labour ;
           :180 — "BL1 PingPong：AIV 交替写入 BL1[0]/BL1[1]，AIC 交替读取，通过 CrossCoreFlag 同步"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a DepthwiseConv2D build on a named 950 board that feeds the Cube directly from an
           un-enlarged `[C, 1, kH, kW]` weight and produces correct results — the K0 alignment
           requirement would then not force the AIV stage, and the whole mixed-core structure would
           be an implementation choice rather than a necessity.
```

# 0349 · A depthwise weight has one input channel, so a vector core must pack and re-lay it before Cube can read it

## 1 · Claim
Upstream asserts a structural necessity rather than an optimisation. The Cube's L0B operand requires
NZ (FractalZ) layout `[K1, N1, K0, N0]` with `K0 = 16` and `N0 = 16` for fp16. A DepthwiseConv2D
weight is `[C, 1, kH, kW]` — one input channel per group — so its K extent per group cannot meet the
`K0 = 16` alignment, and it cannot be fed to Cube as it stands. Upstream asserts the resolution: the
kernel runs as `__mix__(1, 2)`, and the vector cores concatenate several groups' weights (`enlarge`)
and re-lay the result into NZ before the cube core consumes it. Upstream asserts the three-stage
path — `GM(NCHW) --MTE2--> UB(nd) --V(DataCopyGather)--> UB(nz) --MTE3--> L1(BL1)` — with a
multi-dimensional ND `DataCopy` into UB, a `Reg::DataCopyGather` re-layout inside UB against a
gather index built at `kUbSize` spacing, and an NZ-formatted copy out to `BL1`. Upstream asserts the
producer/consumer structure that follows: AIV alternately writes `BL1[0]` and `BL1[1]` while AIC
alternately reads them, synchronised by a cross-core flag. Not established here.

## 2 · The wrong branch this removes
Depthwise convolution reads as a cheaper convolution — fewer multiply-accumulates, one channel per
filter — so the expected implementation is the standard Cube path with a smaller K. It is not
available. The operand does not satisfy the Cube's layout precondition, and no amount of tiling
fixes that, because the deficiency is in the tensor's own shape.

The wrong branch is therefore attempting the direct path and diagnosing its failure as a tiling
error. What the agent will see is a K extent that cannot be aligned, and the natural response —
pad K to 16 — is wasteful in exactly the ratio the enlarge avoids: padding `cin/groups = 1` to 16
does 16× the Cube work for one group's answer, while enlarging packs 16 real groups into the same
fractal. Both make the alignment hold; one computes garbage in fifteen sixteenths of the array.

The second wrong branch is treating the AIV stage as overhead to be removed. It is the reason the
kernel is `__mix__` at all, and removing it removes the operator. Upstream's own guide lists
`weight_nz_transform` as a strategy with the condition `cin/groups < K0` (`conv/guide.md:53`) — a
computable predicate, not a judgement, and it is the cleanest statement in this family of when the
stage is required.

The third is the cross-core synchronisation. AIV produces `BL1` and AIC consumes it; the ping-pong
across two `BL1` halves is what lets them overlap, and it is guarded by a cross-core flag rather
than by the intra-core event machinery. An implementer who carries the single-core ping-pong
pattern (`0301`'s `MTE1_MTE2` / `MTE2_MTE1` pairs) will synchronise the wrong two agents: those
events order pipes within a core, and nothing in them orders an AIV write against an AIC read.

## 3 · Ground / Source
The necessity, `conv/conv_common_perf_experience.md:75`:

```
**为什么需要 AIV**：DepthwiseConv2D 的 weight 是 `[C, 1, kH, kW]`，每个通道只有 1 个输入通道，
无法直接满足 Cube 的 K 维对齐要求（K0=16 for fp16）。AIV 负责将多个 group 的 weight 拼接（enlarge）
并重排为 NZ 格式。
```

The layout requirement, `:121`:

```
Cube 的 L0B 要求 NZ（FractalZ）格式：`[K1, N1, K0, N0]`，其中 K0=16、N0=16（fp16）。
DepthwiseConv2D 的 weight 原始格式是 NCHW：`[enlarge, cout/groups, cin/groups, kh×kw]`。
```

Note the weight shape at `:121` already carries `enlarge` as its outermost dimension, while `:75`
gives the original as `[C, 1, kH, kW]`. The two are the same tensor before and after the packing,
and reading `:121` alone would suggest the enlarge is part of the input format rather than something
the kernel does. Recorded because an implementer reaching for the layout section first will meet the
post-enlarge shape without the sentence explaining it.

The three-stage path, `:127`:

```
GM(NCHW) --MTE2--> UB(nd) --V(DataCopyGather)--> UB(nz) --MTE3--> L1(BL1)
```

Stage 1, `:135-140`, is a three-level ND copy whose strides encode the packing:

```cpp
MultiCopyParams<DTYPE, 3> copyParams;
// loop0: cin/groups × khkw (连续拷贝)
// loop1: cout/groups (srcStride = srcKSize, dstStride = kUbSize)
// loop2: enlarge (srcStride = cout/groups × srcKSize, dstStride = cout/groups × kUbSize + srcKSize)
DataCopy<DTYPE, 3, kDefaultMultiCopyConfig>(ubNd, filterGm_[0], copyParams);
```

Stage 2, `:143-146`, is the re-layout, and it is a Reg/MicroAPI operation — which is what ties this
family to the arch35 programming model regardless of its directory name (`0346`):

```cpp
// 构建索引：[0, khkw, 2*khkw, ..., (K0-1)*khkw]，后续 repeat 通过 Adds 累加 nStride
Reg::DataCopyGather<DTYPE, DTYPE, IndexT>(gatherReg, srcAddr + srcOffset, indexReg, gatherMaskReg);
Reg::DataCopy<DTYPE>(dstAddr + dstOffset, gatherReg, vstsMaskReg);
```

The gather index `[0, khkw, 2·khkw, …, (K0−1)·khkw]` is `K0 = 16` entries spaced by one group's
`kh × kw`, which is the packing made explicit: sixteen groups' worth of weight, one element from
each, become one K0-deep fractal column. That single line is the clearest statement of what
`enlarge` means and upstream never says it in prose.

Stage 3, `:149-152`:

```cpp
DataCopyParams nzCp;
nzCp.blockCount = kTotal_ / K0_VAL;
nzCp.blockLen = co1Opt * GN0 * K0_VAL * sizeof(DTYPE) / BLOCK_BYTES;
DataCopy(bl1, ubNz, nzCp);
```

`kTotal_ / K0_VAL` blocks — with `kTotal ≈ 144` and `K0 = 16` (`0348` §3), that is 9, matching the
inner loop's stated `kTotal/kL0 次，如 9 次`.

The mixed-core division, `:66-73`:

```
AIV: GM(weight NCHW) → UB(nd) → V(DataCopyGather) → UB(nz) → L1(BL1)
AIC: GM(fmap) → L1(AL1) → L0A → Mmad → L0C → GM(output)
     L1(BL1) → L0B → Mmad
     GM(bias) → L1(BiasL1) → C2(BiasBT) → Mmad
```

and the synchronisation, `:180`:
`BL1 PingPong：AIV 交替写入 BL1[0]/BL1[1]，AIC 交替读取，通过 CrossCoreFlag 同步`, inside an L1
layout `[AL1_ping][AL1_pong][BL1_ping][BL1_pong][BiasL1]` (`:170`).

Nothing here is measured. The family carries no timing for this stage or for any alternative to it,
so the claim is a structural necessity plus an implementation, with no cost attached to either.

## 4 · Procedure
Proposed, runnable later on a named 950 board. Never run in this phase.

Arm 1 — the necessity, which is the entry's title claim and is the arm most worth running. Attempt to
feed the Cube an un-enlarged `[C, 1, kH, kW]` weight directly, at fp16. Upstream's claim predicts it
cannot be expressed — a compile-time rejection, a runtime refusal, or wrong output. Record which. A
compile-time rejection would make the requirement a language-level invariant; a wrong answer would
make it a silent one, which is a materially different hazard.

Arm 2 — the padding alternative, priced. Build the depthwise operator two ways: enlarge-and-relayout
(shipped), and pad `cin/groups` from 1 to 16 with zeros and take the direct Cube path. Both must be
correct. Compare kernel time, Cube busy and MTE2 bytes. §2 predicts padding does ~16× the Cube work;
this arm turns that prediction into a number, and it is the number that justifies the AIV stage
existing.

Arm 3 — the AIV stage's own cost. Time the three sub-stages separately (GM→UB ND copy, UB gather
re-layout, UB→BL1 NZ copy) and report each as a share of kernel time, with and without the BL1
ping-pong overlap. Upstream asserts the overlap without measuring it; the question is whether the
AIV stage is hidden behind Cube work or is on the critical path.

Arm 4 — the cross-core synchronisation, as a deliberate defect. Remove the `CrossCoreFlag` guarding
`BL1` and run repeatedly. See §5.

Arm 5 — the gather index, checked structurally before any timing. Echo the constructed index from
the kernel and compare against `[0, khkw, …, (K0−1)·khkw]` exactly. An off-by-one here produces a
weight fractal that is subtly wrong, and the resulting convolution is wrong everywhere by a small
amount — the hardest error class to attribute.

Variance floor first for Arms 2–3: one build, 30 in-process runs, 5 fresh-process runs, IQR over
median, with `0327`'s same-path sibling check. Device selection: `npu-smi info -l`;
`npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing; bind only on three idle samples;
re-sample after; discard the case if the die moved. Refuses to assume: that a free die stays free;
that a die may be substituted; that `K0 = 16` for the dtype under test — it is echoed, since upstream
states it only for fp16 and `950:0214`'s neighbourhood records that low-precision cube dtypes widen
the MAC array; that AIV and AIC ran concurrently (Arm 3 reads the trace, because a `__mix__` kernel
whose two halves serialise looks identical in total time to one where the AIV stage is genuinely
hidden).

## 5 · Checker — acceptance declared before the run
Verdict `direct_path` ∈ {compile-reject, runtime-reject, wrong-output, correct} from Arm 1. Declared
before the run: upstream is **supported** by any of the first three; `correct` fires the OVERTURN and
the whole AIV stage becomes an optimisation rather than a necessity.

Verdict `pad_ratio` = padded-path kernel time / enlarged-path kernel time, with the floor, reported
alongside the Cube-busy ratio. §2's argument predicts both near 16 on the Cube side; a `pad_ratio`
near 1 would mean the Cube work is not the constraint and the enlarge is buying something else.

Verdict `aiv_share` = the three sub-stages' combined share of kernel time from Arm 3, and
`aiv_hidden` = true iff that share falls when the BL1 ping-pong is enabled.

Verdict `index_exact` = true iff Arm 5's echoed index matches the specification element for element.

The exit code is not the verdict. Three guards.

First, every build is compared elementwise against a CPU reference over the whole output, at more
than one `(C, kH, kW)` — a layout error that happens to be harmless at a square 3×3 kernel need not
be at 3×5.

Second — the input that makes this checker go red — Arm 4's `CrossCoreFlag` removal is the planted
positive: it **must** produce a wrong result, at least intermittently, across repeated runs. If it
never does, then AIV and AIC are not actually overlapping in this build (the producer always
finishes first by accident of timing), `aiv_hidden` is measuring nothing, and every conclusion about
the ping-pong is void. That fixture is mandatory because a race that does not manifest is
indistinguishable from correct synchronisation in a single run, and this arm is the only thing that
distinguishes them.

Third, `index_exact` is checked *before* any timing arm is interpreted. A correct-looking timing on a
wrongly packed weight is worse than useless, and the index is the one thing in the whole path that
can be verified exactly rather than statistically.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. `K0 = 16`, `N0 = 16`,
`kTotal ≈ 144` and `kTotal_/K0_VAL = 9` are upstream's stated or re-derived values; no weight was
transformed, no gather index was built, no Cube was fed, and no cross-core flag was removed.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. **Upstream supplies no timing** for the AIV transform stage, for
the mixed-core overlap, or for any alternative, so the entry carries a structure and a necessity
argument with no magnitude — the 16× padding ratio in §2 is arithmetic from `K0 = 16`, not a
measurement, and §4 Arm 2 is what would test it. The necessity itself is upstream's assertion: no
build was attempted on the direct path, so `无法直接满足` is unverified, and whether it fails loudly
or silently is unknown. `K0 = N0 = 16` is stated for fp16 only and is not established for any other
dtype. `cinAligned`, `kUbSize`, `srcKSize`, `co1Opt`, `GN0`, `K0_VAL`, `BLOCK_BYTES` and `nStride`
appear in the code excerpts and are defined nowhere in the family (recorded in
`harvest/standing/950-bp.md`). The weight shape is given two ways in one document — `[C, 1, kH, kW]`
at `:75` and `[enlarge, cout/groups, cin/groups, kh×kw]` at `:121` — without the relation being
stated. The enlarge factor's selection rule is nowhere given. `Reg::DataCopyGather` is used without
being located in any header here. BOARD is `family-claimed(unverified)`: the Convolution family is
marked DAV_3510 in the shelf index and no file in it names a chip (`0347`). Nothing transfers to the
other book (RULES.md Art. 1) — the `Reg::` surface this transform uses is arch-gated (`950:0352`).
