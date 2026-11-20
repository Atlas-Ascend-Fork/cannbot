# Contradictions register — domain `950-core` (perf-optimize diagnosis / technique cards / comm-compute)

> **TRIAGED 2026-08-25**: every row below has a phase-2 disposition in
> `harvest/TRIAGE_DOMAIN_ROWS_20260825.md` (resolved / assigned-to-round / noted / blocked).

Per-agent register for the 950-core harvest block (`book-950/entries/0001-0099`), to be merged into
`harvest/CONTRADICTIONS.md` by the controller in wave 2. Row format follows that file.

Scope mined: `ops/ascendc-perf-optimize/` — `SKILL.md`, `references/single-core-pipeline/**` (index,
metrics, vec, scalar, memory, no-bound, all 24 technique cards + INDEX), `references/comm-compute/**`
(6 files), `references/inter-core-pipeline/`, `evals/evals.json`. Not mined here: `references/tiling/**`
(another agent's domain — C-004/C-006/C-007/C-008/C-009 in the main register live there).

Same topic, different advice or numbers, across upstream sources — or between an upstream source and
the vendor's installed CANN toolkit read under the phase-1 read-only exception. Recorded here and in
the affected entries' §3; resolved only by a procedure run on a named board (RULES.md Art. 7). Every quote
below was re-verified against the file during this harvest.

Toolkit pin used where "installed toolkit" appears: `/usr/local/Ascend/cann-9.0.0-beta.2`
(symlinked as `/usr/local/Ascend/cann`). Read-only: no execution, no compilation, no device contact.
`grep -R` used throughout, not `grep -r` — these trees contain symlinked directories.

**ID 008 is deliberately vacant** (drafting gap). Entries cite C-rows by number, so the number is
left unallocated rather than renumbered.

---

## C-950core-001 · The MC² balance condition is stated inverted relative to its own diagram
- `ascendc-perf-optimize/references/comm-compute/pipeline_balancing.md:96-100` (diagram) and `:150`
  (look-up table) — the short block's **compute** covers a long block's **communication**:
  "长块N计算 → 短块计算 … 长块N-1通信 长块N通信 // 约束：compute[long_k] ≥ comm[long_k-1]，短块 comm
  尽量短"; table row "计算后通信 | 计算 Bound | 后（drain 端） | compute[N] ≥ comm[N-1]，尾通信尽量短".
  In per-row terms `β × M_short ≥ α × M_long`, i.e. **M_short ≥ M_long / R**.
- `pipeline_balancing.md:165` (formula section) — the opposite pairing for the same case:
  "α × M_short ≥ β × M_long （计算 Bound，短块通信掩盖长块计算）", i.e. **M_short ≥ R × M_long**,
  which for R > 1 makes the "short" block larger than the long ones.
The derived initial values `:175` and the feasible region `:185` are algebraically consistent with
`:165`, so the algebra self-checks; only the diagram, the short/long naming and the search's
`tail = M % hs` construction disagree. → 950 book, carried by 950:0065; decidable by the sweep in
its §4.

## C-950core-002 · Pruning rule P4: prose says soft penalty, pseudocode hard-excludes — and excludes everything
- `pipeline_balancing.md:287` (rule table) — "P4 | **配平条件**：shortMSize < ρ × longMSize 排除
  （**松约束可降级为惩罚**）| ρ = max(R, 1/R)".
- `pipeline_balancing.md:361-364` (pseudocode) — "if shortMSize > 0 and shortMSize < ρ × hs: continue"
  — a hard skip. With `tail = M % hs` (`:344`) and ρ ≥ 1, `tail < hs ≤ ρ × hs` always, so every
  candidate with a non-zero tail is pruned and only exact divisors of M (uniform splits) survive.
→ 950 book, carried by 950:0066 (with the corrected predicate `shortMSize ≥ hs / ρ` stated there
as a clearly-separated proposal, not a finding).

## C-950core-003 · `MulDstAdd` vs `MulAddDst` — RESOLVED against the installed toolkit: both exist
- `ascendc-perf-optimize/.../techniques/vec-03-fused-instr.md:51` — uses `MulDstAdd(dst, src1, src2,
  mask)` with semantics "dst = dst*src1 + src2", and builds a precision stop rule on that order.
- `ascendc-regbase-best-practice/references/knowledge/api/regbase_api_whitelist.md:76` — lists
  `MulAddDst` among binary register-compute APIs, with the rule that an API absent from the lists is
  to be treated as unavailable until verified in the installed SDK headers.
- INSTALLED TOOLKIT (independent origin, read-only): **both names exist, as different functions** —
  `arm64-linux/asc/impl/basic_api/reg_compute/kernel_reg_compute_vec_fused_intf_impl.h:70`
  `MulDstAdd(...) → FusedMulDstAddImpl` (c310 impl emits `vmadd`; types {half, float, bfloat16_t};
  `static_assert(... "MulDstAdd only support Mode ZEROING")`), and
  `.../reg_compute/kernel_reg_compute_vec_binary_intf_impl.h:111` `MulAddDst(...) → MulAddDstImpl`
  (types incl. uint16/int16/uint32/int32/int64/uint64, 8-byte path via `RegTensor<T,RegTraitNumTwo>`).
  A third, membase-level `MulAddDst(const LocalTensor<T>&, ...)` exists at
  `.../basic_api/kernel_operator_vec_binary_intf_impl.h:442`.
So the whitelist's *absence* was not evidence of unavailability, and "correcting" the spelling would
change which implementation is called. Operand semantics remain unresolved: the two upstream
documents state different orders (`dst = dst*src1+src2` vs `dst = src0*src1+dst`). → 950 book,
carried by 950:0246 (stratum `corroborated`); the semantics half needs the §4 run.

## C-950core-004 · `PipeBarrier<PIPE_V>` after a VF segment — four incompatible statements
- `ascendc-perf-optimize/.../techniques/vec-03-fused-instr.md:54` — "VF 段后该有的
  `PipeBarrier<PIPE_V>()` 要保留——VF 内部不替你做同步".
- `ascendc-regbase-best-practice/references/paradigms/common/sync-and-consistency.md:243` —
  "arch35/Ascend 950 上连续 Vector 计算之间、连续 VF 之间硬件保证顺序，无需手动 PipeBarrier<PIPE_V>()".
- `ascendc-regbase-best-practice/references/paradigms/quantization/references/vf-microapi-patterns.md:347`
  — "`PipeBarrier<PIPE_ALL>()` | `__VEC_SCOPE__` 内不需要（VF 自动调度）".
- `ascendc-sync-check/references/sync-mechanism.md:155` — "auto-sync 开启时编译器在 V 操作间自动插入
  `PipeBarrier<PIPE_V>`，开发者无需手工添加" (auto-sync default-on per `:13`, flag `--cce-auto-sync`).
The last two cannot both be the reason; the first contradicts the second on the same architecture; and
only the fourth mentions the build flag the guarantee depends on. Note the survey located the second
at `references/common/sync-and-consistency.md`; the real path is
`references/paradigms/common/sync-and-consistency.md` (line 243 correct). → 950 book, carried by
950:0259 (verification queue B2).

## C-950core-005 · SKILL.md says the inter-core directory is empty; the directory holds a framework
- `ascendc-perf-optimize/SKILL.md:101` — "当前 `references/inter-core-pipeline/` 内容为空，此步骤返回
  「核间流水优化策略暂未收录，跳过核间流水分析」".
- `ascendc-perf-optimize/references/inter-core-pipeline/index.md:1-41` — a 41-line analysis framework
  (task DAG, sync-point cost modelling, load balance, bubble analysis, tiling correction), whose own
  last line repeats the skip string.
So the two agree on the verdict and disagree on the content; an agent trusting SKILL.md would delete
the only inter-core material in the skill. → 950 book, carried by 950:0002 (CONTRACT defect F2).

## C-950core-006 · Eval #1 rewards the merged-pipeline answer SKILL.md marks as a misreading
- `ascendc-perf-optimize/evals/evals.json:19` — expected_output "回复应描述性能优化的主要流程：Tiling
  建模、流水分析、优化策略制定和 Tiling 回修四个步骤。"
- `ascendc-perf-optimize/SKILL.md:130-132` — 误解2 "将 Step 2/3/4 合并为「流水分析」 ❌ **错误**".
Precise form: the eval's list is **four items with the three pipeline steps merged into one**, so it
instantiates 误解2 at `:130-132`, not literally 误解1's three-step string at `:125` (the deep-dive
cited `:125`). Same file: eval ids are 1, 2, 4 — id 3 absent with no note; all three carry
`"files": []` and `"expectations": []`, so grading is prose-only and could not have caught this.
→ 950 book, carried by 950:0003 and cited by 950:0001 (CONTRACT defect F1).

## C-950core-007 · Evals declare platform A2 over a card library declared A5-only
- `ascendc-perf-optimize/evals/evals.json:13-15,32-34,51-53` — `"ascend_platforms": ["A2"]`, all three
  evals.
- `ascendc-perf-optimize/references/single-core-pipeline/techniques/INDEX.md:5` — "卡片代码统一 A5
  （arch3510）RegBase；非 A5 平台用 `#if defined(__NPU_ARCH__) && (__NPU_ARCH__ == 3510)` 编译期隔离".
Per upstream's own vocabulary map A2 = DAV_2201 = 910B family, A5 = DAV_3510 = 950 family — disjoint.
The only 910-family number anywhere in this scope is one parenthesis, `vec.md:102`. → 950 book,
carried by 950:0004 (CONTRACT defect F3).

## C-950core-008 · (vacant — see header)

## C-950core-009 · "PingPong halves usable UB" vs "queue depth and buffer count are different things"
- `ascendc-perf-optimize/.../techniques/nobound-01-nobound.md:35` — "PingPong 使能时实际可用 UB 需除以
  2，注意容量"; same rule at `vec.md:103` and as a red line at `vec-01:38`.
- `ascendc-perf-optimize/.../techniques/nobound-02-stage-order-rescheduling.md:81,91` — "物理 buffer 数
  由 `InitBuffer(que, BUFFER_NUM, size)` 决定，queue depth 只约束同时挂起的句柄数 … 本卡红线补充了
  **queue depth 与物理 buffer 数是两回事**，depth 加大不一定占 UB".
One card corrects the other's mechanism without the correction propagating back to the two places
that state the flat rule. → 950 book, carried by 950:0019 (and the capacity half by 950:0018).

## C-950core-010 · `Exp<..., expandLevel=0>` described as LUT+interpolation; the installed header shows delegation
- `ascendc-perf-optimize/.../techniques/vec-11-reduce-compute-lut.md:14` — "CANN 的
  `Exp<T, expandLevel, isReuseSrc>` 把 `expandLevel = 0` 设为内部查表+插值模式".
- INSTALLED TOOLKIT (read-only): `arm64-linux/asc/impl/adv_api/detail/math/exp/exp_c310_impl.h:117-120`
  — "if constexpr (taylorExpandLevel == 0) { Exp<T>(dstLocal, srcLocal, calCount); return; }", i.e.
  level 0 leaves the advanced-API Taylor path and delegates to the basic `Exp<T>`. No lookup-table or
  interpolation branch appears in `exp_c310_impl.h` or `exp_common_impl.h`; the parameter is named
  `taylorExpandLevel` in the implementation and is used as a Taylor order elsewhere
  (`impl/simt_api/cpp/dav_c310/kernel_simt_transcendental_impl.h:375-388`).
The routing fact is corroborated; the description of what level 0 *does* is not. → 950 book, carried
by 950:0035.

## C-950core-011 · Exp default expand level: card shows 2, installed template defaults to 10
- `vec-11-reduce-compute-lut.md:20` — before-form "Exp<float, /*expandLevel=*/2, /*isReuseSrc=*/false>".
- INSTALLED TOOLKIT (read-only): `.../math/exp/exp_common_impl.h:40` —
  "template <typename T, bool isReuseSource = false, uint8_t expandLevel = 10>".
Minor, and recorded because the card's before/after pair implies a default the toolkit does not have.
→ 950 book, carried by 950:0035 §7.

## C-950core-012 · MC² bound routing stated numerically in one file and qualitatively in another
- `ascendc-perf-optimize/references/comm-compute/bound_diagnosis.md:11-17` — five numeric R bands
  (≈1 = 0.9~1.1, 1.1 < R ≤ 2, R > 2, R < 1, R < 0.5) with per-band strategies.
- `ascendc-perf-optimize/references/comm-compute/index.md:126-128` — the same decision as
  "计算耗时 >> 通信耗时 → 计算 Bound … 通信耗时 >> 计算耗时 → 通信 Bound … 通信 ≈ 计算 → 相近",
  with no value for `>>` and no cross-reference to the numeric table.
Same species as the single-core bound tree (950:0005). → 950 book, carried by 950:0058.

## C-950core-013 · The five R bands overlap, with no precedence
- `bound_diagnosis.md:11-17` — R = 0.95 satisfies both "R ≈ 1 (0.9~1.1) 完美平衡 → 等分切分即最优" and
  "R < 1 通信 bound → 用计算掩盖通信，增大 tileCnt"; R = 0.4 satisfies both "R < 1" and
  "R < 0.5 强通信 bound → 从短块出发搜索，最大化 tileCnt". The table states no ordering, so an
  if-chain implementation's answer depends on the order the rows happen to be written in.
Separately: the R-value configuration table at `pipeline_balancing.md:434-440` uses *different* bands
(≈1, 1.3~2.0, >2) leaving R ∈ (1.1, 1.3) unassigned and covering no communication-bound band at all,
although `bound_diagnosis.md:3` reports "实测 R 从 0.3 到 9.8". → 950 book, carried by 950:0058 and
950:0073.

## C-950core-014 · Core-utilisation interval formula uses an undefined symbol and a circular bound
- `pipeline_balancing.md:230` — "M_long_min = (feasible_mBlk - 1) × baseM + 16" — `feasible_mBlk` is
  defined nowhere in the file or the directory.
- `pipeline_balancing.md:232` — "M_long_max = floor((M - 16) / longBlockCnt / 16) × 16" — depends on
  `longBlockCnt`, which the search derives from the long-block size the bound is supposed to bound
  (`hc = M / hs`, `:343`).
Same species as the undefined-symbol defects in the tiling subtree. → 950 book, carried by 950:0067.

## C-950core-015 · Core-utilisation threshold called hard in one place and soft in another
- `pipeline_balancing.md:285` — "P2 | **核利用率硬约束** … | 计算 bound ≥ 80%，通信 bound ≥ 50%".
- `pipeline_balancing.md:301` — "utilThreshold = (R >= 1) ? 0.80 : 0.50 // 计算 bound 硬约束 80%，
  通信 bound **软约束** 50%".
Both are implemented as hard `continue`s in the enumeration (`:358`). → 950 book, carried by 950:0068.

## C-950core-016 · Candidate selection metric: `Task Duration` everywhere, `aiv_time` in the implementation note
- `comm-compute/index.md:42,67` — all MC² performance data **must** come from msprof
  `op_summary_*.csv` `Task Duration(us)`; host-side timing forbidden.
- `pipeline_balancing.md:428` — "实施阶段对 Top-N 候选分别设置 longMSize 参数运行 msprof，按实测
  **aiv_time** 选最优".
`aiv_time` (from `kernel_details.csv`, the single-core convention) and `Task Duration` (from
`op_summary_*.csv`) are different columns measuring different spans. → 950 book, carried by 950:0069.

## C-950core-017 · `MC2_JitterDiagnose.md` is an orphan reference file with tool frontmatter and side effects
- `ascendc-perf-optimize/references/comm-compute/MC2_JitterDiagnose.md:1-5` — frontmatter with
  `description`, `allowed-tools: Read, Write, Edit, Bash, Glob, Grep`, `argument-hint`.
- `:51` — "将分析脚本写入 profiling 目录下的 `_jitter_analysis.py`，然后执行"; `:101-103` —
  "pip install --user -i https://pypi.tuna.tsinghua.edu.cn/simple pandas matplotlib openpyxl".
- No file in the skill references it; `comm-compute/index.md:184-193`'s routing table lists five
  documents, not this one. Its analytical content (time/space jitter axes, data-driven 3× warm-up
  detection, CV bands 2%/5%) exists nowhere else in the skill, while the MC² capture protocol
  (`index.md:63-75`) reports a point estimate and never a spread.
Not a numeric contradiction but a packaging one, and CONTRACT defect F6. → 950 book, carried by
950:0074.

---

## Also recorded in entries, not raised to a C-row (single-source scope statements, no second version)
- `metrics.md:17` cites `workflows/cannbench-a5-baseline-collection.md` for the collection
  convention; no such file exists anywhere under `ops/` (dangling reference — 950:0010 §3, and
  `harvest/claims/perf-optimize-core--002-*`).
- `metrics.md:63` calls every ratio threshold an 经验判定线 while `vec.md:17-21` tabulates three of
  them as severity grades and `vec.md:58-59,87` adds three more cut points on the same metric
  (20%, 30%, 90%) — a tension in voice rather than in value (950:0009, 950:0015, 950:0016).
- `vec-13:26` and `vec-06:14` use symbolic vector-length constants (`VL_FLOAT32_SIZE`, `VL_FP32`)
  where `vec-03:52` forbids borrowed lane constants and requires `GetVecLen()/sizeof(T)` — the rule
  is stated once and violated twice inside the same card library (950:0252 §3).
- `pipeline_balancing.md:224` computes `utilization = min(totalBlocks, N_core) / N_core`, which
  saturates at 1.0 and therefore cannot distinguish one wave from three (950:0068 §3).

> 2026-08-24 repair-wave dispositions (audit acceptance-criterion 3): C-950core-003 is CARRIED by
> entries 950:0246/0247/0248 (which resolve it against the installed toolkit); the row is retained
> for its narrative. C-950core-008 remains deliberately vacant as documented above.
