# SOURCES — what upstream material exists, and the order it is mined

All paths relative to `upstream/skills-dev-main/ops/` unless noted. Priorities from the
2026-08-24 structural survey (two Opus readers); a harvester re-verifies quotes at claim-card
time — the survey located material, it did not certify it. Repo language is Chinese; claim-cards
quote the original and may add an English gloss.

## The chip truth source — mine FIRST, both books
- `npu-arch/` — NpuArch↔SocVersion map, buffer sizes, core counts, SIMT arch. Declares itself
  the 真源 and states a confidence convention ("ini 文件是发现硬件参数的必要不充分条件";
  bandwidth figures flagged 基于公开资料与经验值). Every hardware constant harvested from ANY
  other skill must be cross-checked against this one; disagreement → `CONTRADICTIONS.md` (five
  rows already seeded, C-001…C-005).

## Priority A — the skill being replaced, and its evidence-bearing neighbours
1. `ascendc-perf-optimize/` — 4-step pipeline + 22 technique cards (7-slot template with a
   `## 性能数据` slot: 1 real measurement, 1 borrowed-and-flagged, 7 protocol-no-numbers, 13
   待实测) + 12 tiling families. The card library is A5/arch3510-first with `__NPU_ARCH__ == 3510`
   compile-time isolation — chip-scope every card at harvest. Known holes: Step 3
   (inter-core-pipeline) is a declared no-op; eval #1 contradicts the SKILL.md's own 误解1.
   **Deep-dive finding that shapes both books: `grep -rn "910"` over `references/tiling/` returns
   nothing (likewise A2/A3/Atlas); 12 of 54 files name a chip and every one names 950-family.
   This skill feeds book-950 almost exclusively — book-910 inherits essentially nothing from it,
   and the 910 replacement's content is DERIVATION (new work), not verification of theirs.**
   Preserve intact: scatter (measured on Ascend950PR with case identity, 12602↔3767us, 1565→89us)
   and reduction/euclidean_norm; also two honesty exemplars (`sort/topk_host_tiling.md:193`
   "这些数值是性能策略，不是架构能力边界"; `scatter/fallback/tiling-flow.md:338` states its own
   gate is wrong). Contradiction rows C-004, C-006…C-009 all live in this skill.
2. `ascendc-performance-best-practices/` — 13 operator-family guides; the BEST evidence culture
   in the repo lives in `reference/scatter/` and `reference/sort/` (negative results with case
   identity). Has a per-family 适用架构 column — harvest it as chip scoping, don't flatten it.
3. `ops-profiling/` — msprof collection + bottleneck-threshold judgement tables. Thresholds are
   claims: each one is a claim-card with its condition set.
4. `ascendc-performance-analysis/` — trace parsing → bound diagnosis; contains the metrics table
   already implicated in C-001/C-002.
5. `ascendc-performance-evaluation/` — 950-only roofline/theoretical estimator + instruction-cost
   JSON. 950 book only. An instruction-cost table is a dense field of per-board claims.

## Priority B — the knowledge the pipeline leans on
6. `ascendc-tiling-design/` — operator taxonomy + tiling methodology, dual-arch tables
   (DAV_3510/DAV_2201 separated — keep the separation). 4 of 9 families are 📋 规划中: record the
   absence as a known hole, don't invent content for it.
7. `ascendc-api-best-practices/` — API semantics, parameter limits, precision/sync/DataCopy
   rules. 910-era vs 950-era must be sorted by mechanism vocabulary (regbase/SIMT → book-950).
8. `ascendc-regbase-best-practice/` — 950 book only; largest unmeasured-marker count (56) — a
   quarry of harvested-stratum entries whose §4 procedures are the real deliverable.
9. `ascendc-simt-*` (3 skills) — 950 book only; C-005 lives here.
10. `ascendc-sync-check/`, `ascendc-mc2-best-practice/` — L4 and comm-fusion material; mc2 is
    large (1 MB) and process-heavy: mine the constraint tables, skip the scaffolding.

## Priority C — context needed for the drop-in contract (not entry material)
- `plugins-official/ops-perf-optimize/` (repo root, not ops/) — the REAL perf path: SessionStart
  hook → primary agent `perf-optimize` → skill-as-contract with 强制加载 / 启动门禁 /
  workflow-state.json / case-set freeze. the delivered skill must fit THIS mechanism.
- `workflow-orchestrator/` + `plugins-official/ops-registry-invoke-demo/workflows/op-optimize.yaml`
  — the DAG the harness may run instead.
- `docs/STANDARDS.md`, `.claude-plugin/marketplace.json`, `evals/` conventions — the packaging
  contract for the delivered skill (frontmatter name + trigger-bearing description; references/ payload;
  evals/evals.json).

## Explicitly NOT mined (this phase)
Migration/scaffolding/process skills (`*-template`, `*-invoke-to-*`, `st-design`, `ut-develop`,
`whitebox-design`, `code-review` workflow files, `docs-gen/search`, infra/model/graph trees):
process instruction, not falsifiable machine knowledge. Exception: constraint tables embedded in
them (e.g. `ascendc-code-review/references/simt-constraints.md`, already implicated in C-005)
may be cited as corroborating-or-contradicting text for claims mined elsewhere. Same repo = one
origin (STRATA S2).

---

## Mining status — wave 1 + 1.5 closed 2026-08-24
- npu-arch: MINED, both books (910: all 5 files after a self-caught coverage sweep; 950: identifier system + DAV_3510 rows + simt-arch-guide).
- ascendc-perf-optimize: MINED (0001-block diagnosis/techniques/comm-compute; 0101-block all 12 tiling families; scripts at structure+constant level, disclosed per entry).
- ascendc-performance-best-practices: PARTIAL. 910/dual side mined into book-910; 950 side mined for matmul/mte2_preload, scatter, sort, bank-conflict, common, ub_resident. Wave 1.75 closed gather/broadcast/conversion/scalar/reduce twins (0401-block); wave 1.9 closed elementwise (vector_efficiency mined; double_buffer was already 950:0319/0321) and the scan shelf top items (0451-block). MINED, with the mc2 implementation-twin deferred-and-carded as the one justified residue.
- ops-profiling, ascendc-performance-analysis: MINED (thresholds harvested with their scoping honestly recorded as unscoped where upstream is silent).
- ascendc-api-best-practices: MINED for 910 (18/18 files, dry-exit met); 950-marked material was absent from the follow-up files.
- ascendc-performance-evaluation: MINED (method + instruction-cost table).
- ascendc-regbase-best-practice: LARGELY MINED (whitelist, paradigms/common, sync, patterns, dev-experience, pitfalls per controller ruling). REMAINING: paradigms/<family> beyond mask_predicate + numerical_stable (~recurrence 1376 lines, Q-950rem-28); pitfalls precision files (Q-950rem-29); regbase_api_sync.md (Q-950rem-30).
- ascendc-simt-* trio: MINED (incl. debug-api.md, macro-api.md).
- ascendc-mc2-best-practice: PARTIAL (constraint tables mined; window-memory-layout narrowed not closed; implementation twin of comm-compute deferred by twin-diff budget — carded).
- ascendc-tiling-design: MINED to plan — DAV_2201 columns in book-910; DAV_3510 taxonomy + broadcast/reduction methodology (wave 1.75); FlashAttention + matmul families (wave 1.9, 0451-block). Justified residue, recorded not silent: the reduction full-load arms (restate budgets 950:0123 carries) and the 📋 规划中 categories, both in card ascendc-tiling-design--003/--004.
- Backlog above = a later harvest pass menu, operator's call; recorded here so absence reads as absence, not as coverage.
