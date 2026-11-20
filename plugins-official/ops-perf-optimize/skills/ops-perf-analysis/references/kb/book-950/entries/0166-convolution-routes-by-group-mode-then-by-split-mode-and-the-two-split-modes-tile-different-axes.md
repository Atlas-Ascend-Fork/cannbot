```
ID:        0166-convolution-routes-by-group-mode-then-by-split-mode-and-the-two-split-modes-tile-different-axes
LABEL:     knowledge
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/tiling/convolution/fallback/fallback-algorithm.md:11-40 —
           "Step 1 — Group 决策： ├─ groups=1 → 普通卷积 ├─ groups>1, opt-group weight 能装入 UB →
           OPT_GROUP └─ groups>1, opt-group 不满足 UB 约束 → ORI_GROUP" · "Step 2 — 切分模式决策：
           ├─ outputOrder = M → M-split └─ outputOrder = HW → HW-split" · "| **Mmode** | M-split |
           mAL1 × nBL1 × kAL1/kBL1 | mL0 × kL0 × nL0 | / | **HWmode** | HW-split | hoAL1 × woAL1 ×
           nBL1 × kAL1/kBL1 | hoL0 × woL0 × kL0 × nL0 |"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured Conv2D on a named 950 board where the split mode upstream's `outputOrder`
           selects is slower than the other on the same shape — `outputOrder` would then not be a
           performance-ordering input, and the two-mode split would be arbitrary.
```

# 0166 · Convolution routes by group mode, then by split mode, and the two split modes tile different axes

## 1 · Claim
Upstream asserts a three-decision routing for Conv2D and DepthwiseConv. Step 0 classifies the
operator, with DepthwiseConv entering the same path as Conv2D under `groups = Ci = Co` and anything
else returning `暂未收录`. Step 1 decides the group mode: `groups = 1` is ordinary convolution;
`groups > 1` with the opt-group weight fitting UB takes OPT_GROUP, merging several groups into an
enlarged group; `groups > 1` failing that UB constraint takes ORI_GROUP, processing group by group.
Step 2 decides the split mode from `outputOrder`: `M` selects M-split, `HW` selects HW-split. Upstream
asserts the two modes tile different axis sets — Mmode splits L1 along `mAL1 × nBL1 × kAL1/kBL1` and
L0 along `mL0 × kL0 × nL0`, while HWmode splits L1 along `hoAL1 × woAL1 × nBL1 × kAL1/kBL1` and L0
along `hoL0 × woL0 × kL0 × nL0`. Upstream asserts a seven-step generation pipeline from operator
classification through multi-core allocation, single-core shape, API tiling configuration, single-core
L1/L0/UB tiling, RunInfo assembly, and TilingKey computation. Not established here.

## 2 · The wrong branch this removes
Convolution has the largest formula body in this domain — a 69 KB script and three markdown documents
— and the natural failure is to start at the formulas. The routing above is what decides *which*
formulas apply, and the two split modes are not variants of one derivation: HWmode tiles the output
spatial dimensions `ho` and `wo` separately where Mmode tiles a single flattened `m`. A plan that
computes `mAL1` and then applies it in an HW-split kernel is describing a tile that does not exist.

The group decision removes a second wrong branch, and it is the one an agent is most likely to get
wrong because it looks like a correctness question and is a capacity question. OPT_GROUP merges
groups to make the weight movement worthwhile; whether it applies is decided by whether the merged
weight fits UB. So the group mode is a UB-budget outcome, not a property of the operator, and the same
convolution can take either mode on different platforms. An agent that treats `groups > 1` as
selecting one fixed path will produce a plan that does not fit or one that under-uses the machine.

Third: DepthwiseConv is not a separate algorithm here. Upstream routes it through the same steps with
`groups = Ci = Co`, so an agent looking for depthwise-specific tiling will not find one and should not
invent one.

## 3 · Ground / Source
The routing, `convolution/fallback/fallback-algorithm.md:11-31`, in full:

```
给定：算子名 + Shape (N, Ci, Hi, Wi, Co, Kh, Kw) + dtype + attributes

Step 0 — 算子分类：
  ├─ Conv2D → 进入 Step 1
  ├─ DepthwiseConv → 进入 Step 1（groups = Ci = Co）
  └─ 其他 → 返回「暂未收录」

Step 1 — Group 决策：
  ├─ groups=1 → 普通卷积
  ├─ groups>1, opt-group weight 能装入 UB → OPT_GROUP
  └─ groups>1, opt-group 不满足 UB 约束 → ORI_GROUP

Step 2 — 切分模式决策：
  ├─ outputOrder = M → M-split
  └─ outputOrder = HW → HW-split

Step 3 — 算法路由：
  ├─ M-split → Mmode（M 优先 tiling）
  └─ HW-split → HWmode（HW 优先 tiling）
```

The two sub-algorithms' tiling dimensions, `:37-40`:

```
| 子算法 | 切分模式 | L1 tiling 维度 | L0 tiling 维度 |
|--------|---------|---------------|---------------|
| **Mmode** | M-split | mAL1 × nBL1 × kAL1/kBL1 | mL0 × kL0 × nL0 |
| **HWmode** | HW-split | hoAL1 × woAL1 × nBL1 × kAL1/kBL1 | hoL0 × woL0 × kL0 × nL0 |
```

The seven-step pipeline, `convolution/fallback/tiling-flow.md:11-55`, in full:

```
给定：Conv2D 算子 + Shape (N, Ci, Hi, Wi, Co, Kh, Kw) + dtype + attributes

Step 0 — 算子分类与 Group 决策：
  ├─ groups=1 → 普通卷积
  ├─ groups>1, opt-group weight 能装入 UB → OPT_GROUP（合并多组为 enlarge 组）
  └─ groups>1, opt-group 不满足 UB 约束 → ORI_GROUP（逐组处理）

Step 1 — 切分模式决策（GetTilingSplitMode）：
  ├─ outputOrder = M → M-split（沿 batch × M × Co × groups 切分）
  └─ outputOrder = HW → HW-split（沿 batch × Ho × Wo × Co × groups 切分）

Step 2 — 多核算力分配（NumBlocksDecision）：
  ├─ M-split: 回溯搜索 {batch, m, n, group} 四维因子组合
  │   └─ 目标：最小化总代价 = loadFmap + loadWeight × BW_coeff + loadOutput + cubeCompute
  └─ HW-split: 回溯搜索 {batch, ho, wo, n, group} 五维因子组合
      └─ 目标：最大化核利用率（总块数尽可能接近 aicoreNum）

Step 3 — 单核 Shape 计算（Conv2dApiTilingSetShape）：
  ├─ M-split: singleCoreM = CeilDiv(Align(Ho×Wo, m0), mDim)
  │           singleCoreCo = Align(CeilDiv(Align(Co, n0), nDim), n0)
  └─ HW-split: singleCoreHo = CeilDiv(Ho, hoDim), singleCoreWo = CeilDiv(Wo, woDim)
  └─ singleCoreBatch = CeilDiv(Batch, batchDim)

Step 4 — API Tiling 引擎配置（Conv2dOpTilingSetShape）：
  ├─ 设置 org/single shape、dtype、format、padding/stride/dilation
  └─ 配置 group 参数（enlarge, singleGroups, singleGroupOpt）

Step 5 — 单核 Tiling 计算（GetConv2dApiTiling → Conv2dTiling::GetTiling）：
  ├─ M-split → Mmode（M 优先 tiling）
  └─ HW-split → HWmode（HW 优先 tiling）
  内部执行：
  ├─ L1 Tiling：确定 kAL1/kBL1/mAL1/nBL1/hoAL1/woAL1 切分 + 双缓冲策略
  ├─ L0 Tiling：L1 → L0 子切分 + L0C 双缓冲检查
  └─ UB Tiling：Weight UB transpose 参数 / DMA fmap copy 参数

Step 6 — RunInfo 输出（GetConv2dOpsTiling）：
  └─ 组装多核 numBlocks + 单核 tiling data → kernel 下发参数

Step 7 — TilingKey 计算（SetTilingKey）：
  ├─ fmpTiling / weightTiling：L1 全载程度
  ├─ l1PingPong / l0PingPong：各级 ping-pong buffer 使能
  ├─ outputOrder / iterOrder / groupType：调度模式标记
  └─ weightUbTrans / fmapCopyMode / innerBatch：数据搬运模式
```

The per-mode L1 strategy hierarchies, `:89-101`:

```
### 3.1 Mmode（M-split）

- L1 tiling：沿 mAL1、nBL1、kAL1/kBL1 三维切分
- 策略层次：FullLoad（fmap 或 weight 全载 L1）→ K-only FullLoad → No FullLoad
- 支持 innerBatch 机制（1×1 卷积时单次 load 处理多 batch）
- L0 tiling：mL0 × kL0 × nL0

### 3.2 HWmode（HW-split）

- L1 tiling：沿 hoAL1、woAL1、kAL1/kBL1、nBL1 四维切分
- 额外支持 DMA kernel split（khL1/kwL1）用于大 kernel 场景
- L0 tiling：hoL0 × woL0 × kL0 × nL0
```

Note what is *not* stated anywhere in this family: how `outputOrder` is decided. Step 1 is named
`GetTilingSplitMode` and its input `outputOrder` is treated as given; no rule, threshold or shape
predicate for choosing M over HW appears in `fallback-algorithm.md`, `tiling-flow.md` or
`tiling-fields.md`. The single most consequential routing decision in the family — it selects which of
two different tiling algorithms runs — is an input with no stated derivation. Registered as
C-950tiling-033 and as the family's largest gap.

Two link targets are absent from this tree: `fallback-algorithm.md:38` and `tiling-flow.md:5` both
point at a `demo/` directory (`算法实现见 [demo/](demo/) 目录，main.cpp 注释标注了每步对应的原始代码
路径`), and `convolution/fallback/` contains only `fallback-algorithm.md`, `tiling-flow.md`,
`tiling-fields.md` and `script/`. So the implementation the flow document defers to for step-by-step
correspondence is unreachable. Recorded in `harvest/standing/950-tiling.md`.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and discard the
case if the die moved. Variance floor first: one build, 30 in-process runs and 5 fresh-process runs.

Arm 1 — the missing `outputOrder` rule, which is the family's central gap. Take eight Conv2D shapes
spanning the plausible discriminators: large `Ho×Wo` with small `Co`, small `Ho×Wo` with large `Co`,
`1×1` kernels, large kernels, and both with and without `groups`. For each build both M-split and
HW-split plans, one compiler pin, md5 each, host echo of `outputOrder`, the group mode, the L1 and L0
tile fields and the TilingKey. Compare output against an fp64 reference within the operator's declared
tolerance. Record `aic_time`, MTE2 bytes and core utilisation under
`msprof --aic-metrics=PipeUtilization`, ≥10 iterations, first 5 dropped. The deliverable is a
shape-to-winner table — the rule upstream does not state.

Arm 2 — the group-mode boundary. Fix a grouped convolution and sweep `groups` and `Co` so the
opt-group weight footprint crosses the queried UB capacity (0141). At each point record which mode the
host selects and build both where legal. This makes the OPT_GROUP/ORI_GROUP gate a measured boundary
rather than a stated one, and it is the arm that would reveal whether the gate uses the real UB
capacity or a literal — this family's script defaults `ub_size` to `262144`, a value no other script
in the subtree uses (C-006, cited not duplicated).

Arm 3 — DepthwiseConv through the shared path. Build one DepthwiseConv both through the Conv2D path
with `groups = Ci = Co` and, if any depthwise-specific kernel exists, through that, and compare. If
the shared path is competitive, upstream's routing is vindicated; if not, the family is missing a
depthwise algorithm and says so nowhere.

Refuses to assume: that a free die stays free; that a die may be substituted; that `aicoreNum` or
`ub_size` are the script's literals (both queried); that `outputOrder` is derivable from shape — arm 1
is what tests whether a rule exists to be found; that a selected mode was the mode that ran (host echo
required).

## 5 · Checker — acceptance declared before the run
Verdict variable `mode_winner(shape)` from arm 1, and `outputorder_predictable`: true iff a single
shape predicate separates the M-winning shapes from the HW-winning ones across all eight. Declared
before the run: the two-mode split is justified iff each mode wins on at least two shapes by more than
the variance floor. The OVERTURN fires iff one mode wins on all eight — the other mode is then
redundant for this shape set. `outputorder_predictable` is reported as a finding either way, since a
false value means the missing rule is not merely undocumented but shape-independent.

Verdict `group_gate_capacity` from arm 2: the UB footprint at which OPT_GROUP stops being selected,
compared against both the queried capacity and the script's 262144 literal. Verdict `dw_competitive`
from arm 3.

The exit code is not the verdict: a convolution with a wrong padding or dilation mapping produces
plausible values and exits 0. The numeric comparison against an fp64 reference runs on every arm and
the checker fails red if it did not. Second guard: mode identity via the host echo of `outputOrder`
and the TilingKey — a forced mode the host overrode would make `mode_winner` reflect one plan run
twice, and the checker reports `void` for that shape rather than a winner.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. This family carries no
measured number anywhere: no throughput, no speed-up, no case identity, no tool.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured. **Every constant in this family is unscoped**: the script's
`C0_SIZE = 32`, `M0 = 16`, `N0 = 16`, `B16_K0 = 16`, `B8_K0 = 32`, `MIN_BURST_SIZE = 128`,
`BAND_WIDTH_COEFF = 4`, `VGATHER_REGISTER_SIZE = 256`, `MAX_16_BIT_NUM = 65535`,
`LOAD3D_M_START_POS_LIMIT = 32767`, `POSTK_LIMIT = 65535`,
`DATACOPYPARAMS_BURSTLEN_MAX = 65535`, `aicore_num = 32` and `ub_size = 262144` are all bare literals
with no chip, no derivation and no measurement, and none of the three markdown documents names a board
or an architecture anywhere. The entry does not establish how `outputOrder` is decided
(C-950tiling-033) — that rule is absent from the family. It does not establish the OPT_GROUP UB
constraint, does not establish that DepthwiseConv is adequately served by the shared path, and does
not establish the L1 strategy hierarchies or the `innerBatch` and DMA-kernel-split mechanisms beyond
recording that they exist. The `demo/` directory the flow document defers to is not in this tree. BOARD
is `family-claimed(unverified)` because the family names no chip at all; §4 names 950PR/950DT because
that is where our run would happen. Nothing here is established for any 910-family board.
