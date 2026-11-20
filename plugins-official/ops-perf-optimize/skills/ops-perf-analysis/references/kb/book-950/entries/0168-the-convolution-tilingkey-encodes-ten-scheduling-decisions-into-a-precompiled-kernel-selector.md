```
ID:        0168-the-convolution-tilingkey-encodes-ten-scheduling-decisions-into-a-precompiled-kernel-selector
LABEL:     knowledge
LEVEL:     L8 (toolchain & build)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/tiling/convolution/fallback/tiling-flow.md:104-119 —
           "TilingKey 将 tiling 结果编码为固定格式的查找键，用于匹配预编译的 kernel 变体" ·
           "| `fmpTiling` | Fmap L1 全载程度 | 0=FULLLOAD_AL1, 1=ONLY_M_FULLLOAD, 2=OTHER | ...
           | `innerBatch` | Inner batch 模式 | 0=SINGLE, 1=1x1_MULTI, 2=MULTI |"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a convolution on a named 950 board where two tiling plans producing the same TilingKey
           have materially different performance — the key would then not capture the scheduling
           decisions it selects a kernel by, and kernel selection would be under-determined.
```

# 0168 · The convolution TilingKey encodes ten scheduling decisions into a precompiled kernel selector

## 1 · Claim
Upstream asserts that convolution tiling terminates in a TilingKey: the tiling result encoded into a
fixed-format lookup key used to match a precompiled kernel variant. Upstream asserts ten fields and
their value sets: `fmpTiling` (fmap L1 full-load degree — FULLLOAD_AL1 / ONLY_M_FULLLOAD / OTHER),
`weightTiling` (the same three for weight — FULLLOAD_BL1 / ONLY_N_FULLLOAD / OTHER), `l1PingPong` and
`l0PingPong` (four states each: both off, A on B off, A off B on, both on), `outputOrder`
(HW-mode / M-mode), `iterOrder` (M_FIRST / N_FIRST), `groupType` (NORMAL / ORI_GROUP / OPT_GROUP),
`weightUbTrans` (off / on), `fmapCopyMode` (LOAD3D / DMA), and `innerBatch`
(SINGLE / 1x1_MULTI / MULTI). Not established here.

## 2 · The wrong branch this removes
The TilingKey changes what "emit a tiling plan" means for this family. Everywhere else in this domain
the tiling data is consumed as numbers by one kernel; here a subset of the decisions selects *which
kernel binary runs*, from a precompiled set. Two consequences an agent will not infer.

First, a decision that does not appear in the key cannot influence kernel selection, and a decision
that does appear must take one of the enumerated values — there is no continuous knob among these
ten. An agent that reasons "enable double buffering on A only if the budget allows" has to land on
one of `l1PingPong`'s four states; there is no partial state, and the same is true of the two
full-load fields, which quantise L1 residency into three levels rather than reporting a fraction.

Second, the key is a *selector*, so a plan whose key names a variant that was not precompiled has no
kernel to run. Upstream does not say what happens then, and that is the practical trap: the tiling
search space as described by the formulas (0166, 0167) is larger than the key's product of value sets
— `3 × 3 × 4 × 4 × 2 × 2 × 3 × 2 × 2 × 3 = 20736` distinct keys — and whether all of them exist as
binaries is unstated. An agent that optimises freely over the tiling parameters may produce a plan
that is legal by the formulas and unreachable by the dispatcher.

Third, the ten fields are a compact statement of what this family considers to be the scheduling
decisions at all. `fmapCopyMode` (LOAD3D versus DMA) and `weightUbTrans` are not mentioned in the
tiling flow's Step 5 description beyond a passing reference to "UB Tiling: Weight UB transpose
parameters / DMA fmap copy parameters"; the key is where they surface as first-class choices.

## 3 · Ground / Source
`convolution/fallback/tiling-flow.md:104-119`, §4 in full:

```
## 4. TilingKey 编码

TilingKey 将 tiling 结果编码为固定格式的查找键，用于匹配预编译的 kernel 变体：

| 字段 | 含义 | 取值 |
|------|------|------|
| `fmpTiling` | Fmap L1 全载程度 | 0=FULLLOAD_AL1, 1=ONLY_M_FULLLOAD, 2=OTHER |
| `weightTiling` | Weight L1 全载程度 | 0=FULLLOAD_BL1, 1=ONLY_N_FULLLOAD, 2=OTHER |
| `l1PingPong` | L1 双缓冲使能 | 0=ALL_CLOSE, 1=A开B关, 2=A关B开, 3=ALL_OPEN |
| `l0PingPong` | L0 双缓冲使能 | 同上 |
| `outputOrder` | 输出顺序 | 0=HW-mode, 1=M-mode |
| `iterOrder` | L1 迭代顺序 | 0=M_FIRST, 1=N_FIRST |
| `groupType` | 分组类型 | 0=NORMAL, 1=ORI_GROUP, 2=OPT_GROUP |
| `weightUbTrans` | Weight UB transpose | 0=关闭, 1=启用 |
| `fmapCopyMode` | Fmap 搬运模式 | 0=LOAD3D, 1=DMA |
| `innerBatch` | Inner batch 模式 | 0=SINGLE, 1=1x1_MULTI, 2=MULTI |
```

Its place in the pipeline, `:50-54`:

```
Step 7 — TilingKey 计算（SetTilingKey）：
  ├─ fmpTiling / weightTiling：L1 全载程度
  ├─ l1PingPong / l0PingPong：各级 ping-pong buffer 使能
  ├─ outputOrder / iterOrder / groupType：调度模式标记
  └─ weightUbTrans / fmapCopyMode / innerBatch：数据搬运模式
```

Cross-references from the rest of the family, for the fields that are decided elsewhere:
`outputOrder` is Step 1's input, with no stated derivation rule (0166, C-950tiling-033); `groupType`
comes from Step 0's group decision, gated on whether the opt-group weight fits UB; `fmpTiling` and
`weightTiling` reflect the L1 strategy hierarchy `FullLoad → K-only FullLoad → No FullLoad`
(`:92`), which maps onto three levels but whose middle level is named `ONLY_M_FULLLOAD` for fmap and
`ONLY_N_FULLLOAD` for weight — so `K-only FullLoad` in the prose and `ONLY_M/N_FULLLOAD` in the key
are different names and it is not stated whether they are the same state. Registered as
C-950tiling-035.

`innerBatch`'s `1x1_MULTI` value corresponds to the mechanism at `:93` —
`支持 innerBatch 机制（1×1 卷积时单次 load 处理多 batch）` — so the key distinguishes the
1×1-convolution multi-batch case from a general multi-batch case, and the general one (`MULTI`) is not
described anywhere in the family.

`iterOrder` (M_FIRST / N_FIRST) appears only in the key. No section of the family explains when L1
iteration should go M-first or N-first, what the trade-off is, or how the value is decided. It is one
of ten fields selecting a kernel binary and it has no derivation anywhere in this reference set —
the same species of gap as `outputOrder` and, unlike it, not even named as a step input. Recorded in
`harvest/standing/950-tiling.md`.

Re-derived: the key's value sets multiply to `3 × 3 × 4 × 4 × 2 × 2 × 3 × 2 × 2 × 3 = 20736`
combinations. Upstream states neither how many are legal (many combinations are presumably excluded —
`outputOrder = M` with HW-specific settings, for instance) nor how many are precompiled.

The `demo/` directory that `:5` says carries the implementation with per-step source correspondence
(`main.cpp 注释标注了每步对应的原始代码路径`) is absent from this tree, so the key's bit layout — the
`固定格式` the section names — cannot be recovered here either. The fields are enumerated; their
packing is not.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase. Two arms need
no device.

Arm 1 — key coverage, host only, no device. Enumerate the ten fields' value sets, generate all 20736
combinations, and for each ask the host tiling whether it is producible from some legal shape and
whether a kernel variant exists for it. Record three counts: producible, producible-and-dispatchable,
and producible-but-not-dispatchable. The third count is the practical finding — it is the set of plans
the formulas admit and the dispatcher cannot run.

Arm 2 — the naming question, host only. Construct one case in the `K-only FullLoad` L1 state and read
the emitted `fmpTiling` and `weightTiling`. If they come out as `ONLY_M_FULLLOAD` / `ONLY_N_FULLLOAD`,
C-950tiling-035 resolves as a naming difference; if they come out as `OTHER`, the prose hierarchy has
three levels and the key has a different three.

Arm 3 — key sufficiency, on a named board. Device selection: `npu-smi info -l`;
`npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing; bind only on three idle samples;
`ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and discard the case if the die moved. Variance
floor first: one build, 30 in-process runs and 5 fresh-process runs.

Find pairs of tiling plans that produce the *same* TilingKey but differ in the numeric fields (tile
sizes, factor combinations) — the key encodes ten categorical decisions, not the tile extents, so such
pairs should exist. Build and run both members of four such pairs, one compiler pin, md5 each, host
echo of the full tiling data and the key. Compare outputs against an fp64 reference within the
operator's declared tolerance. Record `aic_time` under `msprof --aic-metrics=PipeUtilization`, ≥10
iterations, first 5 dropped. If same-key pairs differ materially in time, the key selects the binary
but the numbers still decide the performance — which is expected and worth quantifying, since it tells
a consumer how much of the plan the key does *not* capture.

Arm 4 — `iterOrder`, the field with no derivation. On four shapes, build with `iterOrder = M_FIRST`
and `= N_FIRST` and record both times. The deliverable is the missing rule.

Refuses to assume: that a free die stays free; that a die may be substituted; that all 20736
combinations are legal or precompiled — arm 1 counts them; that the key's field order or bit widths
are recoverable from this tree (they are not, and arms 1 and 2 work from the enumerated values rather
than from a packed integer); that a plan that builds was dispatched to the variant its key names.

## 5 · Checker — acceptance declared before the run
Verdict variables `key_producible`, `key_dispatchable` and `key_orphaned` from arm 1, as three counts
out of 20736. Declared before the run: the key is a complete selector iff `key_orphaned = 0`; a
non-zero count is reported as the number of legal-but-unrunnable plans and is a finding in itself.

Verdict `fullload_naming ∈ {same, different}` from arm 2, resolving C-950tiling-035. Verdict
`same_key_spread` from arm 3: the maximum relative `aic_time` difference within a same-key pair,
reported with the variance floor — this quantifies what the key does not capture. The OVERTURN fires
iff `same_key_spread` exceeds 20 %, since the key would then be selecting kernels by decisions that do
not determine performance. Verdict `iterorder_rule` from arm 4: whether a single shape predicate
separates the M_FIRST-winning shapes from the N_FIRST-winning ones.

The exit code is not the verdict: a convolution dispatched to the wrong kernel variant may still
produce correct output, more slowly. Two guards. First, the numeric comparison against an fp64
reference runs on every point, and the checker fails red if it did not. Second, and specific to this
entry: the emitted key must be read back from the host and matched against the intended one at every
point; a dispatcher that fell back to a default variant would make `same_key_spread` and
`iterorder_rule` measure something other than what they claim, and the checker reports `void` for any
point whose key echo does not match.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. Arms 1 and 2 need no device
and have not been run either.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured. **Every constant in the convolution family is unscoped** — no board, no
architecture, no measurement appears anywhere in its three markdown documents or its script, and the
script's fourteen numeric constants (0166 §7, 0167 §7) are bare literals. The entry does not establish
the key's bit layout, which the `固定格式` phrase implies and which the absent `demo/` directory was to
carry. It does not establish how many combinations are legal or precompiled, and does not establish
what happens to a plan whose key has no variant. It does not establish a derivation for `iterOrder`,
which appears only in this table, or for `outputOrder`, which is Step 1's undefined input
(C-950tiling-033). It does not resolve whether `K-only FullLoad` and `ONLY_M/N_FULLLOAD` name the same
state (C-950tiling-035), and does not describe the `innerBatch = MULTI` mode, which the family
mentions only as a key value. BOARD is `family-claimed(unverified)` because no chip is named anywhere
in this family; §4 arm 3 names 950PR/950DT because that is where our run would happen. Nothing here is
established for any 910-family board.
