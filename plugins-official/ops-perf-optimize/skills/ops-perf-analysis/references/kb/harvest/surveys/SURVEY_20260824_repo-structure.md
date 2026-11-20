# SURVEY 2026-08-24 · skills-dev repo structure (Opus reader, one contact)

> Status: an agent-produced survey — ONE contact, not a measurement. Every quote below must be
> re-verified against the file before a claim-card is built on it. Paths relative to
> `upstream/skills-dev-main/`.

Root facts: 252 SKILL.md files repo-wide; 87 dirs under `ops/`; repo language Chinese;
`CLAUDE.md` symlinks to `AGENTS.md`.

## 1. Skill anatomy
Declared convention in `docs/STANDARDS.md` §"SKILL.md 结构": frontmatter = `name` + `description`
only; body = `## 工作流程` / `## 脚本工具` / `## 参考资料`; subdirs `references/` (on-demand
knowledge), `scripts/`, `assets/`. **Only the frontmatter is actually standardized** (38/38
sampled have exactly name+description; one adds `permission:`, one `metadata:`). The
`description` does all routing work and always ends with `触发：<conditions>`. Body headings are
not standardized — every skill invents its own sections. Subdir census across `ops/*`:
`references/` 64, `scripts/` 38, `evals/` 26, `templates/` 9, `tests/` 8, `reference/` 5
(singular — spelling deviation in ascendc-golden-generator, ascendc-performance-best-practices,
cann-env-setup, ops-precision-standard, pypto-precision-compare), `assets/` 3. Links are plain
relative markdown, usually in routing tables with load-gating annotations (`⚠️ 必须先读`,
`📋 规划中`). `evals/evals.json` holds prompt→expected_output regression cases with
`config.ascend_platforms` (e.g. `["A2"]`). Sizes 1.9 KB–80 KB; the 80 KB one
(`ascendc-registry-invoke-to-direct-invoke`) contradicts AGENTS.md's 渐进式披露 principle.

## 2. Orchestration
Skill selection is description-matching; no route table, no index (`skills_snapshot.json` is on
TODO, unbuilt). Registration is `.claude-plugin/marketplace.json` (20 plugins). **Neither
`ascendc-perf-optimize` nor `ascendc-performance-best-practices` is registered by any plugin**;
the plugin `ops-direct-invoke-skills` claims "40+" and lists 18. Three coexisting composition
mechanisms:
1. **Hook + primary agent** (the real perf path): `plugins-official/ops-perf-optimize/hooks/hooks.json`
   SessionStart hook injects `<CANNBOT_CONTEXT>` delegating perf work to primary agent
   `perf-optimize` (`plugins-official/ops-perf-optimize/AGENTS.md`, `mode: primary`,
   `skills: [ops-perf-optimize, ops-profiling, ascendc-perf-ttk]`).
2. **Skill-as-contract**: `plugins-official/ops-perf-optimize/skills/ops-perf-optimize/SKILL.md`
   (4.1 KB) — `## 强制加载` (5 mandatory reads), `## 启动门禁` (freeze 3 inputs + 4 case-sets),
   6-stage `## 阶段顺序`, state in `workflow-state.json`.
3. **DAG engine**: `ops/workflow-orchestrator/` (real Python runner, checkpoint resume); the only
   workflow YAMLs are in `plugins-official/ops-registry-invoke-demo/workflows/`
   (`op-optimize.yaml`: create-workspace → perf-analysis → optimize-impl → perf-verify).
Anti-pattern for contrast: `ops/pypto-orchestration-manual/` (orchestrator-only manual with an
audience fence and MEMORY.md handoff).

## 3. Chip targeting
Truth source (self-declared 真源): `ops/npu-arch/references/npu-hardware-params.md` §0.
- ASCEND910B = DAV_2201 = `__NPU_ARCH__` 2201 = Atlas A2 **and A3** = Ascend910B1~B4, 910B2C, 910_93.
- ASCEND950 = DAV_3510 = 3510 = Atlas A5 = Ascend950DT, 950PR. `archXX` = first two DAV digits;
  `__DAV_C310__` ≡ DAV_3510 ≡ arch35, with warning "不可按数值推断".
`c220` nearly undocumented (one hit: `ascendc-docs-search/references/compatibility.md:45`);
"910C" appears twice, never defined. regbase/SIMT are 950-era programming models, not chips.
Grouping (grep hit-counts): **950-only**: ascendc-regbase-best-practice (regbase 694),
ascendc-performance-evaluation, ascendc-simt-* ×3, ascendc-atvoss-* ×2, ascendc-blaze-* ×2,
ops-simulator. **910B-only**: ascendc-direct-invoke-to-registry-invoke, ops-precision-standard,
tilelang-perf-optimization, triton-latency-optimizer. **Dual, separated in tables**: npu-arch,
ascendc-tiling-design (DAV_3510 24 / DAV_2201 22), ascendc-performance-analysis,
ascendc-performance-best-practices (per-family 适用架构 column), ascendc-registry-invoke-template.
**Agnostic**: compile-debug, golden-generator, task-focus, sync-check, plog-analysis,
whitebox-design, aiss-tiling-solver. Where dual, knowledge is mixed by default and separated
only in tables; perf-optimize's card index declares A5-first with `__NPU_ARCH__ == 3510` fencing.

## 4. Inventory (top-10 richest in harvestable optimization knowledge)
★ ascendc-performance-best-practices (13 family guides; best evidence in reference/scatter/ and
reference/sort/ — negative results with case identity) · ★ ascendc-regbase-best-practice (950;
56 unmeasured markers) · ★ ascendc-perf-optimize (see the deep-dive file) ·
★ ascendc-performance-evaluation (950 roofline + instruction-cost JSON) · ★ ops-profiling
(msprof + bottleneck-threshold tables) · ★ ascendc-performance-analysis (trace→bound diagnosis;
contains the metrics table in C-001/C-002) · ★ npu-arch (truth source) · ★ ascendc-tiling-design
(dual-arch; 4 of 9 families 📋 规划中) · ★ ascendc-api-best-practices · ★ ascendc-mc2-best-practice
(mine constraint tables, skip scaffolding). Full 38-row table with sizes lives in the original
survey transcript; the rows above are the mining set.

## 5. Evidence culture (range, verbatim)
Best: `ascendc-perf-optimize/references/single-core-pipeline/techniques/nobound-02-stage-order-rescheduling.md`
(A5, Ascend950PR, BlockDim 56, T=10752, md5-checked rebuilds, 58.99→39.61 us −32.9%).
Honest borrowed number: `vec-03` "外部同类改造实测约 -40%（作为预期方向，非本库实测…）".
Named-but-unmeasured: `vec-01` "待实测". Measured with shape:
`ascendc-performance-best-practices/reference/matmul/mte2_preload_design.md:7` (BF16 M=1024
K=4096 N=2048, 66.0→63.3 μs). Bare assertion:
`.../common/datacopy_optimization_design.md:17` "带宽提升最高 30%（Ascend 910B 实测）" — no
shape, no tool; neighbours carry no chip at all. Only `npu-arch` states a confidence convention
("ini 文件是发现硬件参数的必要不充分条件"; bandwidth 基于公开资料与经验值).

## 6. Gaps
perf-optimize Step 3 declared no-op; eval #1 rewards the answer SKILL.md calls 错误理解;
unmeasured markers per skill: regbase-bp 56, perf-optimize 50, direct→registry 30, code-review
25, tiling-design 13, mc2-bp 13. Registration drift (plugins with trees but no marketplace
entry). Broken submodule `third_party/anthropics-skills` → dangling `skill-creator` symlinks
while STANDARDS.md mandates skill-creator. `docs/TODO.md` lists unbuilt: skills_snapshot.json,
per-skill status field, route_prompt(), audit/coverage/quality scripts, bilingual support.
`docs/STANDARDS.md:213` points to `ops/agents/` which does not exist.

## What the harness expects of a skill (packaging contract for the delivered skill)
(a) `name` + trigger-bearing `description` as the only frontmatter contract; (b) SKILL.md that
routes rather than contains; (c) `references/<family>/...` payload; (d) `evals/evals.json` as
acceptance gate; (e) for the perf path specifically, the 强制加载 / 启动门禁 /
workflow-state.json / case-set-freeze discipline in `plugins-official/ops-perf-optimize/`.
