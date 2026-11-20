# DEEP-DIVE 2026-08-24 · ops/ascendc-perf-optimize (Opus reader, one contact)

> Status: an agent-produced survey — ONE contact, not a measurement. Every quote and line number
> must be re-verified against the file before a claim-card or entry is built on it. Paths
> relative to `upstream/skills-dev-main/ops/ascendc-perf-optimize/` unless noted.
> Coverage: SKILL.md, evals, all of single-core-pipeline (incl. all 24 cards), all of
> comm-compute, tiling index + all 12 family index.md + reduction/elewise/broadcast flows + both
> experience.md + sort/topk; remaining tiling bodies and the 9 Python solvers at
> family/template granularity; neighbours via delegated readers; duplication measured
> mechanically (3-line shingles; ≥40-char line-set intersection). Nothing compiled or run.

Size: 91 .md (440 KB) + 9 .py (202 KB) + evals.json. Count correction: **24** technique cards
(14 vec, 7 mem, scalar-01, nobound-01, nobound-02), not 22.

---

## 1 · THE CONTRACT

Frontmatter verbatim (SKILL.md:1-4):

```yaml
---
name: ascendc-perf-optimize
description: Ascend C 算子性能优化策略制定。结合 Tiling 建模与流水分析（仿真图 + profiling 数据），按卡间/核间/核内三层流水制定性能优化策略，并回修 Tiling 参数。触发：算子性能调优、流水分析、Tiling 修正、bound 诊断、MC² 通算融合算子优化、卡间流水配平时。
---
```

Workflow: **4 steps, not 3** (SKILL.md:8; :124-138 常见误解澄清 defends this):
Step 1 Tiling 理论建模 (all) → Step 2 卡间流水 (comm ops only, skippable) → Step 3 核间流水
(multi-core-sync ops only, skippable) → Step 4 单核流水 (all). Every step emits a correction
back to Step 1's tiling (:23, :36).

Inputs (:28): 算子类型、计算流程（kernel 代码/伪代码）、profiling 数据、仿真图（可选）.
Concretely: msprof kernel_details.csv, op_summary.csv, PipeUtilization.csv,
ResourceConflictRatio.csv (single-core-pipeline/metrics.md:14,33,34).
**MC² hard data gate** (:65-68): before pipeline balancing, MUST have (1) TilingData capture
from host prints (baseM/baseN/baseK/usedCoreNum…), (2) isolation test at tileCnt=1 (comment out
comm/compute process separately, measure T_comm and T_compute, compute R) — 缺失任何一项须返回
数据采集阶段补采,不得凭经验给出切分方案.

Outputs: four `- [ ]` checklists (:46-54, :72-80, :95-99, :113-118) — artifact names, no
acceptance criteria (see defect 4.8).

File tree: see §1.5 of the transcript; key shape: references/{comm-compute(6),
inter-core-pipeline(1, dead), single-core-pipeline(6 + techniques/25), tiling(2 + 12 families,
each index + fallback/{tiling-flow,tiling-fields}.md + script; gather lacks tiling-fields;
fa/ is a stub)}.

**The drop-in interface is wider than SKILL.md — 15 inbound relative links from siblings, all
currently resolving.** Must-preserve paths (referrer → path):
- `ascendc-performance-best-practices/reference/mc2/guide.md:33,37-43` →
  `references/comm-compute/{index,bound_diagnosis,pipeline_balancing,expansion_analysis,local_matmul}.md`
  ("对应的分析层框架…详见 /ascendc-perf-optimize skill 的 references/comm-compute/ 目录")
- `bp/reference/gather/guide.md:7,180` → `references/tiling/gather/fallback/tiling-flow.md`
- `bp/reference/scatter/scatter_design.md:32,95,115` → `references/tiling/scatter/fallback/tiling-flow.md`
- `bp/evals/evals.json:36` names `ascendc-perf-optimize` as a loadable skill.

**Eval contract, self-contradictory**: evals.json has 3 evals (ids 1,2,4; id 3 missing), all
`"files": []`, `"expectations": []` (prose-graded), all `"ascend_platforms": ["A2"]` — against
an A5-only card library. Eval id 1's expected_output is the 4-step-collapsed-to-"流水分析"
answer that SKILL.md:125 marks ❌ 错误理解. **The skill's own test rewards the answer the skill
calls wrong.** The replacement must decide: honour the eval or fix it.

---

## 2 · KNOWLEDGE CONTENT MAP

Evidence over the 24 cards (measured by extracting each `## 性能数据` section):
**1 measured in-library** (nobound-02) · **1 external + disclaimed** (vec-03) · **7
recipe-no-numbers** (mem-01..07) · **15 待实测/待增量补** (13 vec + scalar-01 + nobound-01).
Library scope: techniques/INDEX.md:5 "卡片代码统一 A5（arch3510）RegBase；非 A5 平台用
`#if defined(__NPU_ARCH__) && (__NPU_ARCH__ == 3510)` 编译期隔离"; INDEX.md:9-10 disclaims its
provenance column ("频次不是性能收益排名").

### 2.1 Diagnosis layer (single-core-pipeline/)
- Bound routing tree scalar/memory/vec/no-bound — index.md:20-27, unscoped, BARE (predicates
  are "占比高/利用率高", no numbers, no precedence).
- MC² pre-check: CrossCoreWaitFlag on MTE2 pollutes ratios → reroute to comm-compute
  (index.md:13-18, memory.md:11), conditioned.
- **Overlap factor** Σ(lanes)/aiv_time, ideal bound Σ/max, attainment — metrics.md:41-59, A5 56
  cores, MEASURED (reader recomputed all five figures, self-consistent: Σ=93.97, 1.634, 0.513,
  3.183 vs stated 3.186, 51.3%).
- aiv_mte3_wait_ratio > 0.4 → consumer follows async compute (metrics.md:33, no-bound.md:12).
- Capture protocol: per-case aiv_time, no representative sampling; msprof is truth, simulator
  qualitative only (metrics.md:17-19).
- Trace reading, DB-effective vs serial signature, preg spill (metrics.md:67-84, A5/arch3510).
- RegBase caveat: MTE2/MTE3 carry only TilingData in VF paths (metrics.md:84, BARE).
- RVECEX/RVECSU/RVECLD/RVECST lane translation (metrics.md:92-99, 950 regbase, BARE).
- VEC severity ladder 50-65/65-80/>80% (vec.md:18-21, unscoped; metrics.md:63 calls them
  经验判定线); Cast >20%, transcendental >30% (vec.md:52-59, unscoped).
- Scalar bound: tile 数巨大 → batchPerTile = elemNum/plane (scalar.md:10,30).
- UB "192 KB / 910B2, 248 KB / 950"; DB halves usable UB (vec.md:102-103 — chips named, BARE).

### 2.2 The 24 cards (all A5 RegBase MicroAPI; evidence status per above)
vec-01 UB fusion (kill MTE3→MTE2 GM round-trip; red line: intermediate fits UB, halved under DB)
· vec-02 cast fused into load/store (DIST_UNPACK_B16/DIST_PACK_B32; precision thresholds fp16
2⁻¹⁰ / bf16 2⁻⁷ / fp32 2⁻¹³) · vec-03 fused MicroAPI instr (lane count `GetVecLen()/sizeof(T)`;
raw `__ubuf__ T*`; −40% external disclaimed; **uses API name `MulDstAdd`** — see defect 4.10)
· vec-04 vectorize scalar round-trips (Brcb + stride-0 + masked write-back; 64 B alignment)
· vec-05 eliminate UB staging (3 sub-methods; red line: kept round-trip needs
`LocalMemBar<VEC_STORE,VEC_LOAD>` or maxAbsErr=inf) · vec-06 broadcast-once + VL merge
(mergeNum = VL_FP32/aFactorAlign; butterfly reduce; R power of two) · vec-07 hardware tree
reduce (changes float accumulation order — not bit-identical) · vec-08 multi-accumulator unroll
(break RAW chain; "循环次数绝不写死成常量") · vec-09 loop sink into VF · vec-10 unroll
compile-time tiny loops only · vec-11 Exp<expandLevel=0> LUT path (precision-for-speed) ·
vec-12 preg split (arch3510 no native int64: RegTensor<T,RegTraitNumTwo> = 2 physical 32-bit
pregs) · vec-13 unified tail via UpdateMask (reset counters per row) · vec-14 32 B-pad split
segments at copy stage (alignment must match CopyIn dstStride / VF offset / CopyOut srcStride).
mem-01 align+contiguate main path, isolate tail ("950 历史提交中出现 16B、32B、64B、128B 等
不同约束，不能抽成一个全局常量") · mem-02 ping-pong prefetch · mem-03 batched multi-row copy +
merged same-lifetime queues · mem-04 UB reuse, no GM zeroing detour · mem-05 L2 bypass ONLY
under provable no-reuse (SetL2CacheHint(CACHE_MODE_DISABLE); ban on case-ID/shape whitelists) ·
mem-06 one-shot contiguous write-back · mem-07 identity fast path. All七 cite real upstream
commits (ops-nn/ops-transformer/ops-math, arch35).
scalar-01, nobound-01: 占位 checklists. **nobound-02 stage-order rescheduling — the exemplar**:
A5/arch3510 Ascend950PR BlockDim 56, T=10752; 58.99→52.86→39.61 us (−32.9%); back-to-back
−37.6%; L2-dirty p50 −2.5%; aiv_mte3_wait_ratio 0.47→0.06; 重叠因子 1.63→2.58; per-shape sweep
(T=64/512 neutral, T=4096 −24.6%, T=10752 −35.3%); reversal ablation +7.3%; md5-checked builds;
own scope caveats (:83-86).

### 2.3 comm-compute (MC²)
Masking ratio (T_before−T_after)/min(T_compute,T_comm), speed-up (index.md:16,30) · multi-rank
capture ≥10 iters, first 5 warm-up, mean of last 5, **max across ranks** (index.md:65-75) ·
host-side timing forbidden (index.md:42) · AIC/AIV split, Pattern A/B opposite sync directions
(pipeline_balancing.md:32-62) · α/β, R = T_compute/T_comm, five-row bound table ("实测 R 从 0.3
到 9.8", bound_diagnosis.md:3) · MTE2-pollution test ratio_full − ratio_pure > 0.1
(bound_diagnosis.md:76) · long/short placement matrix, feasible region, 16 B alignment,
core-utilization correction (pipeline_balancing.md:158-236) · adaptive search, 4 pruning rules,
Top-N=15 (:280-372; **P4 is broken — defect 4.2**) · expansion analysis (minimize bottleneck
side's inflation) · Local Matmul bound-independent first choice · constraints MC-C1/C2/C3
(index.md:180-182). **MC2_JitterDiagnose.md is an orphan with side effects** (defect 4.18).

### 2.4 tiling/ — 12 families
Two-level routing; buffer convention Vec=UB, Cube=L1+UB split at L1 not UB (index.md:96); YAML
output schemas (:104-158). **parameter-analysis.md:47-50 — the single best reusable rule**:
芯片规格配置 → 硬件约束,不可放松; 硬编码字面量 → 软件经验值,可纳入搜索.

| Family | Chip named? | Evidence |
|---|---|---|
| reduction (5 templates + 2 interleaved fast paths + BlockSplitR) | Ascend950/arch35/dav-3510, CANN 9.0.0 | MEASURED — 20-case table, #18 8.29×; disclosed misfires #13 −28%, #15 10× slower, #17 −9% |
| scatter (6 paths; outputs blocks+threads+workspace) | Ascend950PR | MEASURED — "阈值与吞吐数字均为 Ascend950PR 实测（72.46 分 / 20-20 通过 / Scatter 榜第 1）"; 12602↔3767 µs; 1565→89 µs; 4.81×; ~600 GB/s |
| sort (DAV_3510 TopK multi-template + M-way merge fallback) | DAV_3510 | conditioned, anti-extrapolation fences (topk_host_tiling.md:193; topk.md:280-286) |
| scan (7 algorithms) | NO chip anywhere | measured claims UNSCOPED — 8~50×, 12~31%, bank rule 5.5×, ~9 µs launch |
| conversion (NDDMA family + 4 others; small-channel transpose C≤16) | dav-3510 in index only | index has numbers (3-10× SIMT, 6.25% bandwidth) without platform/case |
| gather (6-8 templates) | no | BARE — SIMD threshold table (int8 218/int16 360/int32 620/int64 2048) underived; cost gate lives OUTSIDE the skill (bp/reference/gather/templates/) |
| matmul (SWAT/FullLoad/StreamK + variants) | arch35 one line | effectively BARE — sole number "5%~15%" unscoped |
| mc2 (equal-M fallback + 3 degradation levels) | no | bare |
| convolution (69 KB formulas + cost model) | no | bare, no calibration source |
| elewise | no | bare |
| broadcast (genuine DAV_2201 vs DAV_3510 branch) | DAV_2201, DAV_3510 | bare |
| fa | — | stub (and tiling/index.md:24 routes GroupNorm here — defect 4.7) |

---

## 3 · OVERLAP / DUPLICATION
Verbatim duplication small and mostly deliberate (分析层/实现层 split with bp, 15 resolving
inbound links). Byte-identical blocks: vec.md:33-42 ↔ performance-analysis/SKILL.md:274-284
(trace block + DB table; also severity ladder and Cast>20%); comm-compute/local_matmul.md:62 ↔
bp/mc2/local_matmul_design.md:117; pipeline_balancing.md:37-38 ↔ bp same:40-41; scatter
thread-candidate code ↔ bp/scatter/fiber_exclusive_design.md:97,100 — with unenforced
dual-maintenance obligation (tiling-flow.md:305 "同源，改动请同步两处").
**Two divergent forks with ascendc-tiling-design**: broadcast maxElemNum derivation
(tiling-design's copy has an extra branch `if shapeLen == 1`), and small-channel transpose
(same 16*C+32 budget under two owners; perf-optimize holds measured counter-evidence
tiling-design readers never see).
**No coupling at all with regbase-bp / api-bp / mc2-bp / sync-check** (one shared ≥40-char line,
a compiler guard; vocabulary disjoint: 重叠因子/aiv_vec_ratio/preg/spill/RVEC = 10/10/37/10/8 in
perf-optimize, 0 in all four; no file in those four references perf-optimize by name). The two
libraries gate differently — perf-optimize by msprof threshold, regbase by compile/correctness
rule — which is exactly how defects 4.10/4.11 survived.
**Unique to perf-optimize** (concept-count table): overlap factor, L2-bypass predicate
discipline, multi-accumulator unroll. Bank-conflict and RegBase-VF authority live in neighbours
(bank conflict: bp 134 mentions vs perf-optimize 3).
**Family contradictions**: 950 UB 248 KB (vec.md:102, analysis ×2, npu-arch, tiling-design) vs
192 KB (perf-optimize's own reduction anchors); reduction taxonomy AR-SmallR/AR-FullLoad/
AR-Recompute/ARA-* vs tiling-design's ColSplit/RowSplit (no AR-SmallR); dichotomy gate numeric
(R≤8/R>8, tiling-flow.md:291-292) vs qualitative in tiling-design; `npusim` ("cannsim 已更名…
两名字同入口", nobound-02:11) vs ops-simulator documenting only `cannsim`.

---

## 4 · QUALITY DEFECTS (merged list)
4.1 **Four incompatible UB values, one chip-scoped**: 262144 (conv_tiling.py:245) · 248*1024
(six scripts) · 192*1024 (scan_tiling.py:103) · 240 KiB-usable-of-248 (topk_host_tiling.md:209,
DAV_3510, the only scoped one). Severe: **192 KB-for-950 under a measurement banner**
(euclidean_norm/experience.md:5 "平台：Ascend 950 / arch35…UB≈192KB。数据全部 msprof 上板实测",
feeding reproducible self-checks rGroupCnt=61 / workspaceBytes=7808 at tiling-flow.md:201; all
five template budgets calibrated at 192 KB). coreNum likewise: 64 (six defaults) / 72
(scan, reduction) / 32 (conv) / 8/24 (examples).
4.2 **MC² search prunes 100% of what it seeks**: pipeline_balancing.md:341-364 — tail < hs by
construction, P4 `if shortMSize < ρ×hs: continue` with ρ≥1 fires on every non-zero tail → only
uniform splits reachable; prose row :287 asks for a soft penalty, pseudocode hard-continues.
Three different answers for M_short (:150, :175, :185).
4.3 **Decision node that decides nothing**: conversion/index.md:95-102 — C≥32 → N_LAST 推荐;
C<32 → N_LAST 推荐(配合维度合并).
4.4 **stepK five values, one self-refuting**: max 8 (tiling-flow.md:159) · 上限 4
(tiling-fields.md:24) · {1,2,4} (:186) · {1,2,4}+StreamK-exception-3 (tiling-flow.md:375,
contradicting its own :36 constants) · mc2/index.md:64 emits step_k: 3.
4.5 **StreamK gate stated twice, computed 8× apart**: "K ≥ 32768 且 B=1 且无 group"
(tiling-flow.md:21, fallback-algorithm.md:35) vs formula :283 → K≥4096 at aicNum=24; worked
example :351 (K=16384→SK) satisfies formula, violates rule. Also :344 heading "→ A-FullLoad" vs
:346 computing 不开; :352 kCnt=6, skSingleCoreK=2732 where CeilDiv(16384,6)=2731.
4.6 **Undefined symbols in load-bearing formulas**: VLC (scan gates/segment sizing, never
defined); VREG in two unit systems in one file (:57 implies 64 elements, :145 implies 256
bytes); RPC_WORKSIZE, MB_SIZE, c0, L1_SIZE (matmul); M merge-ways colliding with M-shape
(sort); MIN_OUT_UB, ubBlockSize, xAlign, minIdxSlice (gather); bufferNum, extraSize,
maxDtypeBits (broadcast/elewise — their ONLY UB formulas); dcache (silently 64 in script);
outLanes, szA0 (reduction); α, β, R (mc2, deferred to comm-compute).
4.7 **Placeholder labels hiding real content**: elewise & broadcast index.md say 占位/暂未收录
while complete tiling-flow/fields/scripts sit in the same directory (the elewise script is the
ONLY correct copy of a formula that diverges three ways family-wide); tiling/index.md:73-77
labels conversion 占位 which is flatly wrong; only fa/ is a true stub — and GroupNorm routes to
it, landing on "暂未收录" while reduction (covering LayerNorm) sits next door.
4.8 **Checklists that cannot fail**: SKILL.md's four output blocks (artifact names, no
criteria); tileSize=4096? (always true); used_core_num ≥ 1 (floored by max(1,…)). Counter-
example in the same skill: euclidean_norm/experience.md:169-170 (items that can fail).
4.9 **Bound routing without numbers**: index.md:20-27 no thresholds/precedence; the worked
example resolves MTE2 .513/VEC .483/SCALAR .480 with a 0.52 cut appearing exactly once
(metrics.md:57). Same shape: matmul MTE2-bandwidth gates ≥85%→FullLoad, <70%→SWAT, [70,85)
unrouted (tiling-flow.md:265-266).
4.10 **`MulDstAdd` vs `MulAddDst`**: vec-03 uses MulDstAdd uniformly incl. a precision red line
built on it; regbase whitelist (regbase_api_whitelist.md:76 + 20+ uses) says MulAddDst and
"absent from the lists → treat as unavailable until verified in installed SDK headers".
4.11 **Four-way PipeBarrier<PIPE_V> contradiction**: vec-03:54 keep it (VF 不替你同步) · regbase
sync-and-consistency.md:243 hardware guarantees order, 无需手动 · regbase
vf-microapi-patterns.md:347 none needed in __VEC_SCOPE__ · sync-check sync-mechanism.md:155,158
compiler auto-inserts (16,531 occurrences counted). The last two cannot both hold.
4.12 **Measurement fused to inference**: metrics.md:57 (lane times measured; 理想上界 Σ/max is a
modelling assumption presented as arithmetic — true data dependency forbids full overlap);
vec.md:21, vec-11:9 same shape.
4.13 **性能数据 sections with no data**: all 7 mem cards (recipe under a heading promising data).
4.14 **Step 3 vacuous and misdescribed**: SKILL.md:101 "内容为空" — directory actually holds a
40-line framework, unreachable behind the skip string.
4.15 **More self-contradictions**: scatter threads "只能取 {1024,512,128,32,8}" then 256 five
lines later (tiling-fields.md:45,50); heading 固定 1024 线程 vs 按 pass 定 (:163 vs :180-188);
scatter ships a gate its own text calls wrong (:338 判据应该是冲突度…当前实现用的是 starved);
scan borrow-R trigger 4096 / 16384 / 4096 across .md and script (4× apart); sort merge
bytes-per-element 64 B (.md) vs ~104-112 B (script); broadcast DAV_2201 constraints stated in
.md, dropped unconditionally by broadcast_tiling.py:373.
4.16 **Broken links, all targets present, off-by-one ../**: euclidean_norm/experience.md:89
(needs 7 has 6), scan/tiling-flow.md:344 and scan/index.md:63 (need 5 have 6); gather
fallback/index.md:10 → nonexistent tiling-fields.md (which gather/index.md:13 instructs
reading); matmul tiling-fields.md:91,100 → batch/group_matmul.md missing;
convolution/tiling-flow.md:5 → demo/ missing; metrics.md:17 cites
workflows/cannbench-a5-baseline-collection.md, nowhere under ops/.
4.17 **Coverage gaps**: bank conflict mentioned 3×, taught 0× — the one substantive measured
rule buried at scan/tiling-flow.md:110 (`if (S*sizeof(C)) % 16 == 0: S |= 1  # 撞 bank,实测慢
5.5 倍`); DoubleBuffer: 92 mentions, routing criterion, nobound-02 precondition — no card
(mem-02 covers manual prefetch, not InitBuffer BUFFER_NUM).
4.18 **Orphan with side effects**: comm-compute/MC2_JitterDiagnose.md — referenced nowhere,
own frontmatter with allowed-tools, instructs writing _jitter_analysis.py into the user's
profiling dir and pip-installing from an external mirror.

---

## 5 · WHAT A REPLACEMENT NEEDS
5.1 **Must cover**: (1) the routing contract — 4 steps, triggers, skip rules, the 7
sibling-visible paths, the MC² data gate; (2) numeric non-overlapping bound predicates with
precedence + the msprof capture protocol; (3) the overlap-factor method (unique here; keep the
worked example; split measured half from the Σ/max assumption); (4) all 24 technique units + 2
missing cards (DoubleBuffer enable/sizing; bank conflict, promoting the 5.5× rule); (5) the MC²
chain with a CORRECTED search (4.2); (6) tiling modelling for 12 families, keeping
parameter-analysis.md's hardware-constraint vs software-literal discipline, promoting content
out from behind wrong 占位 labels, re-homing GroupNorm; (7) something real for Step 3 or an
honest removal; (8) **dual gating per unit** — a metric gate (msprof threshold) AND a
compile/correctness gate; neither upstream library has both, which is why 4.10/4.11 survived.
5.2 **Exemplars**: nobound-02 (platform/shape/BlockDim + md5 + unflattering variants + per-shape
sweep + reversal ablation + own caveats); vec-03:47 borrowed-number handling; euclidean_norm §6
+ reduction §13 negative results ("误命中 RARA 慢 10×"; "mte2_ratio 单指标会误导"); sort's
禁止外推的边界 + "这些数值是性能策略，不是架构能力边界"; npu-arch's ini-field provenance model;
mc2-bp's measurement-regime honesty; **query-don't-hardcode**
(`GetCoreMemSize(CoreMemType::UB)`, topk_host_tiling.md:81).
5.3 **Verification queue**:
BLOCKING — B1 MulDstAdd vs MulAddDst (installed SDK headers, no card needed); B2
PipeBarrier<PIPE_V> after VF on 950 (isolated toggle, bit-compare AND timing, barrier the only
variable); B3 950 UB 192 vs 248 KB (runtime query; gates every reduction budget).
950 QUEUE (decision-gating thresholds): Cast>20%; aiv_vec_ratio>80%/90%; transcendental>30%;
aiv_mte3_wait_ratio>0.4; the 0.52 lane cut; DB halves-UB rule; 32 B alignment penalty (vec-14
premise); Exp<expandLevel=0> trade; int64 preg×2 (vec-12); nobound-02 transfer beyond its one
operator; npusim/cannsim naming; bank 5.5× rule; matmul 85/70 gates + [70,85) gap; MC² R-table
boundaries, TAIL_MIN=128, 80%/50% cuts, Top-N=15; reduction gates (R1×dtypeSize≤16B, rowsSize≥8,
innerRowElems≥512, chunkA0==A0); scatter thread candidates + 256-vs-1024; the four UB and four
coreNum script defaults.
ESTABLISH FROM SCRATCH (no upstream authority, npu-arch does not supply them): 32 B DataCopy
block granularity, 256 B repeat granularity, cache-line 128/256 B, 256 B vector-register width
(hence VL_FP32=64), DCache size, repeatTimes≤255 — first-time establishment per part.
ADOPT AS RULE (don't verify): vec-03:52 lane count from GetVecLen()/sizeof(dtype), never
borrowed constants — the correct side of a family-wide disagreement (regbase's own canonical
template does the forbidden thing, vf-programming-rules.md:98); generalize to every capacity
constant.
5.4 **The 910 conclusion**: a 910-targeted replacement inherits essentially nothing — (1) card
library declared A5-only with compile-time fencing; (2) grep "910"/"A2"/"A3"/"Atlas" over
references/tiling/ returns nothing, and every chip-naming tiling file names the 950 family;
(3) the only 910 number in the skill is vec.md:102's bare "192KB / 910B2". The one genuine
910/950 branch (broadcast DAV_2201 vs DAV_3510) is discarded unconditionally by its own script.
**So: 950 work = verification of theirs; 910 work = derivation of ours.**
