```
ID:        0116-mx-scale-is-one-byte-per-32-k-elements-and-its-reuse-factor-exists-to-clear-a-32kb-minimum-load
LABEL:     knowledge
LEVEL:     L3 (data movement & layout)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/tiling/matmul/fallback/tiling-variants.md:44-56 —
           "Scale 数据量约为计算数据的 1/32，但小数据 MTE2 搬移效率低，需要特殊处理" ·
           "scale_per_K = CeilDiv(K, MX_GROUP_SIZE(=32))" · "受 `SCALE_FACTOR_MAX=127` 和
           `MTE2_MIN_LOAD_SIZE=32KB` 约束" ; matmul/fallback/tiling-fields.md:65 —
           "候选 `[16, 8, 4, 2]`，按 §3.2 公式从大到小回退"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured mxfp4/mxfp8 case on a named 950 board where a Scale transfer well below
           32 KB achieves the same MTE2 efficiency as one above it — the minimum-load constant
           would then not be the reason the reuse factor exists.
```

# 0116 · MX Scale is one byte per 32 K-elements, and its reuse factor exists to clear a 32 KB minimum load

## 1 · Claim
Upstream asserts the Scale geometry for the MX-quantised matmul variants: one UE8 (1-byte) scale
value per group of 32 K-elements, so `scale_per_K = CeilDiv(K, MX_GROUP_SIZE(=32))`,
`total_scaleA = baseM × scale_per_K × sizeof(UE8)` and
`total_scaleB = baseN × scale_per_K × sizeof(UE8)`. Upstream further asserts the reason this
metadata needs its own tiling treatment: the Scale volume is about 1/32 of the compute data, and
small transfers move inefficiently over MTE2, so a reuse factor (`scaleFactorA` / `scaleFactorB`)
controls how much Scale is fetched per movement, bounded by `SCALE_FACTOR_MAX = 127` and
`MTE2_MIN_LOAD_SIZE = 32KB`. Upstream additionally asserts an enhancement layer in which
`scaleL1BufferNum` takes one of `[16, 8, 4, 2]` by falling back from largest to smallest, with
`scaleKL1` re-assigned to `scaleL1BufferNum × kL1` and `scaleBufferNum` fixed at 2. Not
established here.

## 2 · The wrong branch this removes
The 1/32 ratio invites the conclusion that Scale is negligible and can be left out of the L1
budget. It cannot: the budget inequality at `matmul/fallback/tiling-flow.md:154` charges
`scaleASize + scaleBSize` inside the `× DB_SIZE` term for MX scenarios, and the four-buffer test
at `:177` charges them at depth 2 on top of the operands at depth 4. An agent that omits Scale
overestimates the L1 headroom and produces a plan that overflows or, more often, one whose
`nBufferNum` should have fallen to 2 and did not.

The sharper wrong branch is treating the reuse factor as a tunable with no floor. Its purpose is
not reuse for its own sake: it exists to make each Scale transfer large enough to clear
`MTE2_MIN_LOAD_SIZE = 32KB`. An agent that shrinks it to save L1 converts a small number of
efficient transfers into a large number of inefficient ones, which shows up as MTE2 time on an
operand carrying 3 % of the bytes — a symptom that reliably gets attributed to the wrong operand.
This is the same reversal shape as FullLoad's 20 KB pipeline-health gate (0110): concentrating a
budget on one thing degrades another thing's transfer geometry, and that degradation has its own
threshold.

## 3 · Ground / Source
`matmul/fallback/tiling-variants.md:42-56`, §3.1 in full:

```
### 3.1 Scale 维度建模

Scale 是 MX 量化的元数据：每个 group（32 个 K 元素）配一个 scale 值用于反量化。Scale 数据量约为计算数据的 1/32，但小数据 MTE2 搬移效率低，需要特殊处理。

**Scale 几何**：

scale_per_K = CeilDiv(K, MX_GROUP_SIZE(=32))
total_scaleA = baseM × scale_per_K × sizeof(UE8)
total_scaleB = baseN × scale_per_K × sizeof(UE8)

**Scale 复用因子**（scaleFactorA / scaleFactorB）：控制单次 Scale 搬移量，防止小数据占比过高。受 `SCALE_FACTOR_MAX=127` 和 `MTE2_MIN_LOAD_SIZE=32KB` 约束。

**TilingData 影响**：scaleKL1 覆盖的 K 范围需与 kL1 对齐；全载路径需为 Scale 预留 L1 空间。
```

The per-tile L1 form of the same geometry, `matmul/fallback/tiling-flow.md:147-150`:

```
   // MXFP8/MXFP4 场景额外计算 scale 缓冲区:
   scaleElemPerK = Align(CeilDiv(baseK, 32), 16);  // 每行 scale 元素数，对齐到 16
   scaleASize = scaleElemPerK * baseM;             // A 侧 scale 缓冲区 (fp8_e8m0)
   scaleBSize = scaleElemPerK * baseN;             // B 侧 scale 缓冲区 (fp8_e8m0)
```

Re-derived: at `baseK = 256`, `CeilDiv(256, 32) = 8`, aligned to 16 gives `scaleElemPerK = 16` —
so the 16-element alignment doubles the Scale footprint at this `baseK`, and the "1/32 of the
data" figure understates the L1 charge by 2× here. At `baseK = 512` the ceiling is 16 and the
alignment costs nothing. The alignment's cost is therefore `baseK`-dependent and largest at the
smallest legal `baseK` — at `baseK = 32` (`CeilDiv = 1`, aligned to 16) it is 16×. Upstream does
not state this; it is arithmetic on upstream's formula and is recorded as such.

The budget lines that charge Scale, `matmul/fallback/tiling-flow.md:152-154` and `:174-178`:

```
2. buffer约束:
   标准场景: (al1Size + bl1Size + biasSize) * DB_SIZE <= l1Size
   MXFP8/MXFP4: (al1Size + bl1Size + scaleASize + scaleBSize + biasSize) * DB_SIZE <= l1Size
```

```
MXFP8/MXFP4 场景 scale 使用独立 2-buffer pingpong，需计入：
used_4buf = baseN × kl1 × 4 + baseM × kl1 × 4 + scaleASize × 2 + scaleBSize × 2 + biasSize
```

The enhancement-layer fields, `matmul/fallback/tiling-fields.md:62-66` and `:112-117`:

```
| `scaleFactorA` / `scaleFactorB` | Scale 在 L1 中相对 stepKa/b 的复用倍数 | SWAT: 由剩余 L1 反推；A-Full 下 `scaleFactorA=1`；B-Full 下 `scaleFactorB=1` | `_cal_scale_factors()` |
| `scaleKL1` | L1 中 Scale 覆盖的 K 范围 | 基线: `min(scaleFactorA·stepKa·baseK, scaleFactorB·stepKb·baseK)`；启用 Scale Coalescing 后重赋值为 `scaleL1BufferNum × kL1` | `_calc_scale_kl1()` |
| `scaleL1BufferNum` | Scale 相对 A/B kL1 的 K 覆盖倍数（增强层 1 新增） | 候选 `[16, 8, 4, 2]`，按 §3.2 公式从大到小回退 | `scale_coalescing_tiling.md §2.2` |
| `scaleBufferNum` | Scale 侧 L1 pingpong 深度（增强层 1 新增） | 固定 **2** | 增强层常量 |
```

`scale_coalescing_tiling.md` is referenced as the derivation's home and is not present in this
tree — the `[16, 8, 4, 2]` ladder's `§3.2 公式` is therefore unreachable from here. Recorded in
`harvest/standing/950-tiling.md`.

Under 0104's provenance rule, `MX_GROUP_SIZE = 32` is a format property (how MX quantisation is
defined) and not searchable; `SCALE_FACTOR_MAX = 127` and `MTE2_MIN_LOAD_SIZE = 32KB` are named
constants with no chip-config trace given anywhere, so both are software 经验值 under the rule
and both are candidates for the search — which is exactly what makes the 32 KB figure worth
measuring rather than obeying.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s
spacing; bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and
discard the case if the die moved.

Scale-transfer-size sweep. Fix an mxfp4 shape with large K (M=N=1024, K=8192) so Scale is a real
but minor operand, and sweep `scaleFactorA` so that the per-movement Scale bytes take the values
{4 KB, 8 KB, 16 KB, 24 KB, 32 KB, 48 KB, 64 KB}, staying under `SCALE_FACTOR_MAX = 127` and
re-validating the L1 inequality at every point against the queried L1 capacity (0141), not against
a literal. Build each point with one compiler pin, md5 the binary, echo `scaleFactorA`,
`scaleKL1`, `nBufferNum` and the evaluated L1 occupancy from the host, and check the output
against an fp64 dequantised reference within the declared tolerance. Record `aic_time` and,
critically, the MTE2 time and bytes attributable to the Scale transfers separately from the
operand transfers, under `msprof --aic-metrics=PipeUtilization`, ≥10 iterations, first 5 dropped,
per case.

Second arm — the 16-element alignment cost. Repeat at `baseK ∈ {32, 64, 128, 256}` and record the
measured L1 occupancy against the value `Align(CeilDiv(baseK,32),16)` predicts, so the 2× and 16×
over-charges derived in §3 are observed rather than computed.

Third arm — the enhancement ladder. Where `scaleL1BufferNum` is available, walk `[16, 8, 4, 2]`
and record which value the fallback lands on and what it costs `nBufferNum`, which
`tiling-fields.md:117` says may drop from 4 to 2 as a consequence.

Refuses to assume: that a free die stays free; that a die may be substituted; that 32 KB is a real
efficiency threshold (it is bracketed, not tested at one point); that a `scaleFactor` that builds
was used (host echo required); that the Scale MTE2 traffic is separable in the profile — if it is
not, that is reported and the arm is void rather than estimated.

## 5 · Checker — acceptance declared before the run
Verdict variable `mte2_scale_eff(size)`, the Scale bytes moved divided by the Scale MTE2 time, at
each swept transfer size. Declared before the run: the 32 KB constant is supported iff
`mte2_scale_eff` rises monotonically up to 32 KB and is flat within 10 % above it. The OVERTURN
fires iff efficiency at 8 KB is within 10 % of efficiency at 64 KB — the minimum-load constant is
then not the reason the reuse factor exists, and the entry is corrected in place. A second verdict
`align_cost(baseK)` compares measured L1 occupancy against the formula's prediction; a mismatch is
a finding about the formula, reported with both numbers.

The exit code is not the verdict. Two guards keep this checker able to fail. First, the Scale
MTE2 traffic must be separable from operand traffic in the profile; if the tool reports only an
aggregate, `mte2_scale_eff` is not computable and the checker returns `void`, not a number —
computing it from the aggregate would be a measurement whose scope does not cover the sentence it
supports. Second, `scaleFactorA` must be echoed per point; a clamped factor would flatten the
efficiency curve and read as a clean overturn of a constant that was never actually varied.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured. The entry does not establish `MTE2_MIN_LOAD_SIZE`, `SCALE_FACTOR_MAX`, or
that Scale transfers below 32 KB are in fact inefficient; upstream gives all three as bare
constants with no derivation and no board. It does not establish that the `[16, 8, 4, 2]` ladder
behaves as described — its derivation lives in a file absent from this tree. The 2× and 16×
alignment over-charges in §3 are this book's arithmetic on upstream's formula, not upstream's
statement and not a measurement. Nothing here covers `group_matmul`'s quantised path, whose Scale
K coverage uses a different expression (`Align(max(scaleFactorA·stepKa, scaleFactorB·stepKb)·baseK,
MX_DIVISOR_SIZE)`, `tiling-fields.md:64`) with `MX_DIVISOR_SIZE` itself undefined (0111). No board
is named in either source file, so BOARD is `family-claimed(unverified)` and the chip is unstated;
§4 names 950PR/950DT because that is where our run would happen. Nothing here is established for
any 910-family board.
