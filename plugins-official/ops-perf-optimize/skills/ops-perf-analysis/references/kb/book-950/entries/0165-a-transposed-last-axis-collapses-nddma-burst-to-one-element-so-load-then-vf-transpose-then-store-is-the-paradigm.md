```
ID:        0165-a-transposed-last-axis-collapses-nddma-burst-to-one-element-so-load-then-vf-transpose-then-store-is-the-paradigm
LABEL:     knowledge
LEVEL:     L3 (data movement & layout)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/tiling/conversion/index.md:63-86,131 —
           "末轴参与转置时, NDDMA 的末轴 burst 极短(1个元素), stride 搬运效率低。改用"连续搬入 →
           UB 内 VF 重排 → 连续搬出"" · "范式: MTE2 连续搬入 → Vector/SIMD VF 片上转置 → MTE3 连续搬出
           优势: MTE2/MTE3 两端都走连续大 burst, 带宽打满 非连续访问代价转移到 UB 内 VF 计算(延迟低)" ·
           "GATHER(vgather 按 index 重排)和 VCONV(16×16 块转置)是这一范式的具体实现"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured transpose on a named 950 board with the last axis participating where the NDDMA
           strided path matches or beats the load-transpose-store paradigm — the one-element burst
           would then not be the dominant cost, and the paradigm's premise would be wrong.
```

# 0165 · A transposed last axis collapses NDDMA burst to one element, so load-then-VF-transpose-then-store is the paradigm

## 1 · Claim
Upstream asserts that when the last axis participates in the transpose
(`perm[permSize-1] != permSize-1`), the NDDMA path's innermost burst degenerates to a single element,
making strided movement inefficient, and that the preferred structure is a three-stage paradigm:
contiguous MTE2 load, on-chip Vector/SIMD VF rearrangement inside UB, contiguous MTE3 store. Upstream
asserts the reason — both DMA ends then run long contiguous bursts and saturate bandwidth, while the
non-contiguous access cost moves into UB-internal VF computation, which is latency-cheap. Upstream
asserts three concrete implementations of the paradigm: GATHER using `vgather` to rearrange by index
(requiring dav-3510, the last axis participating, and `TRANSPOSE_ENABLE_GATHER`), VCONV performing
on-chip 16×16 block transposes (VCONV_5HD for 2-D last-axis exchange at 16-bit with `R > 5`,
VCONV_021 for `perm = [0,2,1]` at 8/16/32-bit), and a custom VF rearrangement built from
Broadcast/Select/DataCopy. Upstream asserts the fallback order: if no acceleration strategy qualifies,
a reduced dimension count above `NDDMA_MAX_DIM_NUM(5)` goes to BIG_DIM, otherwise to
CUT_ONCE / CUT_TWICE / NDDMA_BASE, with the note that the strided path's short trailing burst limits
efficiency but there is no better option. Not established here.

## 2 · The wrong branch this removes
The wrong branch is optimising the DMA. Facing a transpose whose profile shows the memory pipe busy
and the bursts short, an agent tunes the transfer: larger tiles, more buffers, different stride
patterns. None of it helps, because the burst length is set by the permutation — if the last axis
moves, consecutive output elements come from addresses `stride` apart in the input, and no tiling
choice makes that contiguous. Upstream's paradigm does not shorten the movement; it relocates the
irregularity from the DMA engine into the vector unit, where a rearrangement is a compute operation
rather than a transfer.

The second wrong branch is treating GATHER and VCONV as unrelated strategies in a list. They are the
same paradigm with different rearrangement primitives, and reading them that way tells an agent what
to do when neither qualifies: build the rearrangement out of whatever vector primitives exist
(`自定义 VF: UB 内 Broadcast/Select/DataCopy 重排`) rather than falling straight to NDDMA. Upstream
puts the custom option *before* the NDDMA fallback in its stated preference order, which an agent
reading the strategy table alone would never infer — the table lists NDDMA as a strategy and the
custom VF as nothing at all.

The third: the acceleration strategies' gates are narrow and each is narrow for a different reason.
VCONV_5HD needs 2-D last-axis exchange, 16-bit elements and `R > 5`; VCONV_021 needs exactly
`perm = [0,2,1]`; GATHER needs an architecture, a permutation property and a build flag. An agent that
treats "the last axis is transposed" as sufficient to take an acceleration path will fail all three
gates and land on NDDMA without noticing it skipped the custom-VF option.

## 3 · Ground / Source
The paradigm, `conversion/index.md:63-86`, in full:

```
  ├─ perm[permSize-1] != permSize-1 (末轴参与转置)
  │   │
  │   Step 2a: 搬入 + UB 内 SIMD VF 转置 + 搬出 ★ 末轴转置的首选范式
  │   │  末轴参与转置时, NDDMA 的末轴 burst 极短(1个元素),
  │   │  stride 搬运效率低。改用"连续搬入 → UB 内 VF 重排 → 连续搬出":
  │   │
  │   │  ┌──────────────────────────────────────────────────────┐
  │   │  │ 范式: MTE2 连续搬入 → Vector/SIMD VF 片上转置 → MTE3 连续搬出 │
  │   │  │                                                      │
  │   │  │ 优势: MTE2/MTE3 两端都走连续大 burst, 带宽打满     │
  │   │  │       非连续访问代价转移到 UB 内 VF 计算(延迟低)    │
  │   │  │                                                      │
  │   │  │ 实现:                                                │
  │   │  │  - GATHER: vgather 按 index 重排(需 dav-3510)        │
  │   │  │  - VCONV: 片上 16×16 块转置                          │
  │   │  │  - 自定义 VF: UB 内 Broadcast/Select/DataCopy 重排   │
  │   │  └──────────────────────────────────────────────────────┘
  │   │
  │   ├─ 满足 GATHER/VCONV 条件 → 对应加速策略
  │   │
  │   └─ 不满足加速策略条件:
  │       ├─ 规约后 dim > NDDMA_MAX_DIM_NUM(5) → BIG_DIM
  │       └─ 否则 → CUT_ONCE / CUT_TWICE / NDDMA_BASE
  │           (NDDMA stride 搬运, 末轴短 burst 效率有限, 但无更好选择)
```

The acceleration gates, `:56-59`:

```
Step 1: 加速策略优先
  ├─ VCONV_5HD: 2D 末轴交换 + 16bit + R>5 → VCONV
  ├─ VCONV_021: perm=[0,2,1] + 8/16/32bit → VCONV_021
  └─ GATHER: 末轴参与转置 + dav-3510 + TRANSPOSE_ENABLE_GATHER → GATHER
```

The principle that states the preference order, `:131`:

```
5. **末轴参与转置时优先"搬入 + VF 转置 + 搬出"范式**:当末轴参与转置(`perm[permSize-1] != permSize-1`)时,NDDMA 的末轴 burst 退化到 1 个元素,stride 搬运效率极低。应优先采用"连续搬入 → UB 内 SIMD VF 片上转置 → 连续搬出"的三段式范式,使 MTE2/MTE3 两端都走连续大 burst。GATHER(vgather 按 index 重排)和 VCONV(16×16 块转置)是这一范式的具体实现。不满足加速策略条件时,可考虑自定义 UB 内 VF 重排(Broadcast/Select/DataCopy 组合),最后才回退到 NDDMA stride 搬运。
```

The small-channel case the fallback directory covers, `conversion/fallback/index.md:11`:

```
本目录的 [tiling-flow.md](tiling-flow.md) 与 [tiling-fields.md](tiling-fields.md) 覆盖 **Small-Channel Transpose**（C ≤ 16，建模为 [C, N] → [N, C]）的 Tiling 推导与字段语义。
```

`[C, N] → [N, C]` with `C ≤ 16` is a last-axis-participating transpose, so the small-channel path is
an instance of this paradigm with a specific shape assumption, and it is the only one whose TilingData
derivation exists in this tree.

Three constants and one flag appear without values or definitions beyond what is quoted:
`NDDMA_MAX_DIM_NUM(5)` is given inline; `R > 5` in the VCONV_5HD gate is not explained (what `R`
denotes is not stated in this file); `TRANSPOSE_ENABLE_GATHER` is a build flag whose default is
unstated; and the 16×16 VCONV block size is given without a dtype scope, though a 16×16 block of
16-bit elements is 512 bytes, matching the `CACHELINE = 512` constant the gather family uses (0148 §3)
— a coincidence recorded as a reading, not a fact.

The efficiency claim is asymmetric in evidence. The untransposed-last-axis branch (0164) carries four
measured penalties (3–10×, 2–5×, 6.25 %, ~4 µs); this branch carries none. `burst 极短(1个元素)` and
`延迟低` are structural assertions, `带宽打满` is a goal, and no number is attached to any of them.
So the family's better-evidenced half is the one where the answer was already N_LAST, and its
paradigm claim — the more interesting one — is unmeasured.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and discard the
case if the die moved. Variance floor first: one build, 30 in-process runs and 5 fresh-process runs.

Arm 1 — the paradigm against the strided path, which is the claim. Take three last-axis-participating
transposes spanning the acceleration gates: one satisfying VCONV_021 (`perm = [0,2,1]`, fp16), one
satisfying GATHER (dav-3510 available, flag on), and one satisfying neither (a 4-D `perm` scattering
the last axis, fp32). For each build every legal plan: the qualifying acceleration strategy where one
exists, a custom VF rearrangement, and the NDDMA strided path (CUT_ONCE or BIG_DIM as the reduced
dimension count dictates). One compiler pin; md5 each; host echo of the selected strategy and its
parameters. Compare output elementwise against a permutation-aware CPU reference on every arm. Record
`aiv_time`, achieved GB/s on MTE2 and MTE3 separately, and the measured innermost burst length under
`msprof --aic-metrics=PipeUtilization`, ≥10 iterations, first 5 dropped.

The burst measurement is the arm that tests the *mechanism* rather than the outcome: upstream's
premise is that the NDDMA burst degenerates to one element, and that is directly observable. If the
profile cannot expose burst length, the mechanism claim is reported as untested and only the timing
comparison stands.

Arm 2 — the custom-VF position in the order. On the case satisfying neither acceleration gate, compare
the custom VF rearrangement against NDDMA directly. Upstream places custom VF ahead of NDDMA in
preference; this arm is what makes that a measurement rather than an ordering.

Arm 3 — the acceleration gates' boundaries. For VCONV_5HD, sweep `R` across 5 and vary the element
width off 16-bit; for VCONV_021, perturb `perm` away from `[0,2,1]`. Record whether each violation
causes a build refusal (a capability gate) or merely a fallback (a policy gate). The two are different
and upstream does not distinguish them.

Refuses to assume: that a free die stays free; that a die may be substituted; that
`TRANSPOSE_ENABLE_GATHER` is set (its state is recorded with every result); that `R` in the VCONV_5HD
gate means what a reader guesses — arm 3 varies it and records the observed boundary rather than
asserting a definition; that the profile exposes burst length; that a selected strategy was the one
that ran (host echo required).

## 5 · Checker — acceptance declared before the run
Verdict variable `paradigm_gain(case)` = NDDMA median `aiv_time` / best-paradigm median. Declared
before the run: the paradigm is supported iff `paradigm_gain > 1 + variance_floor` on all three cases.
The OVERTURN fires iff `paradigm_gain ≤ 1 + variance_floor` on any case where NDDMA is legal — the
one-element-burst premise would then not be the dominant cost there.

Verdict `burst_observed` = the measured innermost burst length of the NDDMA arm, in elements;
upstream's premise predicts 1. Verdict `customvf_beats_nddma` from arm 2. Verdict
`gate_kind(strategy) ∈ {capability, policy}` from arm 3.

The exit code is not the verdict: a transpose producing a wrongly-permuted output exits 0, and a
permuted output has the same element multiset as a correct one — so an order-insensitive comparison or
a checksum would score every wrong permutation as correct. The comparison is therefore
permutation-aware and elementwise, and the checker fails red if the reference used was not
permutation-aware. Second guard: strategy identity via host echo at every point, since a custom-VF arm
the build system replaced with NDDMA would make `customvf_beats_nddma` false from one plan run twice.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. Unlike the untransposed-last-axis
branch, upstream attaches no measurement to this paradigm at all — the burst-length premise, the
bandwidth-saturation goal and the latency claim are all structural assertions.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured. The entry does not establish that the NDDMA burst degenerates to one element,
that the paradigm saturates bandwidth, or that UB-internal VF rearrangement is latency-cheap — all
three are upstream assertions with no numbers, in contrast to the sibling branch which carries four
measured penalties (0164). It does not establish the acceleration gates (`R > 5`, `perm = [0,2,1]`,
`NDDMA_MAX_DIM_NUM = 5`, `TRANSPOSE_ENABLE_GATHER`), does not define `R`, and does not establish the
16×16 VCONV block size or its dtype scope. It does not establish that custom VF rearrangement is
implementable for an arbitrary `perm`. It covers only the strategy choice; the TilingData derivation
exists in this tree for the `C ≤ 16` small-channel case alone (0163). `dav-3510` names an architecture,
not a board, so BOARD is `family-claimed(unverified)` and no board is named anywhere in this family;
§4 names 950PR/950DT because that is where our run would happen. Nothing here is established for any
910-family board.
