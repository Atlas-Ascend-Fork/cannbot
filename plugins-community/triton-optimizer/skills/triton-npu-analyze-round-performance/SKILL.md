---
name: triton-npu-analyze-round-performance
description: Use when an optimize round needs deep performance diagnosis from round-local profile and optional IR evidence, especially to explain scalar/vector/cube imbalance, frequent data movement, weak pipeline overlap, or other signals that should be traced back to problems in the current operator implementation.
---

# Analyze Optimize Round Performance

Diagnose one `opt-round-N/` at a time and write the result to `opt-round-N/perf-analysis.md`.

This skill is for deep round analysis inside the `triton-npu-optimize` skill, not for supervisor audits and not for whole-session summaries.
This skill is the owner of `opt-round-N/perf-analysis.md` for round-level performance diagnosis inside the `triton-npu-optimize` skill.

In file paths below, `{language}` is the kernel language of the current optimize session.

It supports both:

- `profile-only diagnosis`
- `profile-plus-IR diagnosis`

When IR attribution is needed, use the corresponding `{language}-npu-analyze-ir` skill as the IR evidence companion for capture, navigation, and stage-level inspection. That does not transfer ownership of `opt-round-N/perf-analysis.md`.

Use two complementary analysis paths to find performance problems:

- profiling analysis to identify where time is going and which hardware-facing symptom dominates
- IR analysis to explain why that symptom appears in the current lowering and operator structure, and to discover additional source-level opportunities exposed by the lowering

Use profiler-first layered analysis. Start from profiler evidence and use IR as explanation and attribution rather than as the default entrypoint.

## Pipeline diagnosis boundary

- Profile-only conclusions are valid for hotspots, host overhead, independent
  transfer operators, and trusted engine activity symptoms.
- Tile/K-loop/grid/handshake claims and any software-pipeline or launch-fill
  recommendation require a matched `profile-report --format json` and Triton
  `pipeline-structure --format json` pair from the same revision, candidate,
  case id, resolved shape/dtype, profile operator, and mapped IR kernel.
- Record separate measured runtime, IR structure, conclusion/confidence, and
  evidence-gap sections in `perf-analysis.md`. `Task Wait` and aggregate pipe
  ratios never prove inner overlap. Only mapped MTE/AIC/AIV intervals can say
  `internal_overlap=measured`; otherwise retain `not_observable`.
- If profile Block Num and resolved IR grid disagree, report both, lower
  confidence, and omit launch fill. Batching/fusion are host-graph options,
  not an implicit in-kernel edit.

When compiler source analysis is enabled by the launch prompt or workspace guidance, treat it as a later escalation after profile and IR analysis. Use the corresponding `{language}-npu-analyze-compiler-source` skill only when this skill has narrowed the problem to a concrete performance-related compiler-side question that still needs source-backed explanation before the next operator change is clear.

Read [references/triton-npu-profiling-analysis.md](references/triton-npu-profiling-analysis.md) when the round needs deeper interpretation of `op_summary`, `task_time`, `api_statistic`, or `msprof` JSON signals.
Read [references/triton-npu-optimization-guidance.md](references/triton-npu-optimization-guidance.md) when you need help turning profiling symptoms and IR findings into concrete potential optimization points.
Read [references/triton-npu-architecture-notes.md](references/triton-npu-architecture-notes.md) when the likely optimization point depends on chip differences such as A3 versus A5 buffer sizes, layout behavior, or cube/vector data handoff.
Use the `{language}-npu-optimize-knowledge` skill when structured profile or IR evidence is available and you need language-specific symptom routing before returning to detailed pattern references. Run the `triton-npu-retrieve-patterns` skill's `scripts/retrieve_patterns.py` (`list`, `info <id>`, `patterns <id>`); read the knowledge skill's `references/symptom-contract.json` only when no retrieval skill is available.
When the optimize target is `operator` and the evidence points to Torch NPU or framework-op behavior, also use the staged `torch-npu-optimize-knowledge` skill and start from its `references/pattern_index.md` for operator-level pattern routing.

Read the references in this order:

1. profiling analysis, to understand the dominant profiler signals
2. optimization guidance, to turn those signals plus IR findings into potential optimization points
3. architecture notes, to adjust those optimization points for chip-specific constraints when needed

## Default workflow

1. Resolve the current round directory and round-local operator file.
2. Confirm the round has profile evidence.
   - Prefer round-local evidence such as `opt-round-N/profile/`.
   - If profile evidence is missing, collect it first through the `triton-npu-profile-operator` skill.
3. Strongly consider spawning a subagent before the deep analysis phase.
   - Use this when profile or IR artifacts are large, or when the round already has a long `attempts.md`.
   - If context is still small enough, the current agent may continue directly.
4. Extract profile signals first.
   - Prefer the `triton-npu-run-eval` skill's `profile-report` helper in JSON mode. The standard argument shape is:
     ```text
     profile-report --profile-dir <profile-dir> --format json
     ```
   - Use this as the default structured entrypoint for profiling evidence.
5. Interpret profiling evidence through the profiling reference instead of ad hoc guesses.
   - Follow [references/triton-npu-profiling-analysis.md](references/triton-npu-profiling-analysis.md) for layered signal interpretation.
6. Use the staged `{language}-npu-optimize-knowledge` skill's symptom contract to narrow the current hypothesis.
   - Use its summary, evidence hint, common non-matches, and candidate patterns as routing aids, not as a replacement for the underlying profile or IR evidence.
   - When the optimize target is `operator` and the bottleneck looks Torch NPU or framework-op specific, also use the staged `torch-npu-optimize-knowledge` skill's `references/pattern_index.md` and the one or two best-matching cards under its `references/patterns/` directory.
7. Decide whether profiler evidence is already sufficient on its own.
   - If the layered profiler signals already explain the likely operator problem well enough, continue to diagnosis.
   - If the profiler signals are suspicious but still not explanatory enough, capture or reuse IR under `opt-round-N/ir/`.
8. Extract IR performance signals as the second analysis path for explanation and attribution.
   - Prefer the `triton-npu-analyze-ir` skill's `inspect_ir.py` helper in `performance-signals` mode:
     ```text
     inspect_ir.py performance-signals --ir-dir <allocated-ir-archive> --format json
     ```
   - Use `list-stages`, `stage-summary`, `find-changes`, or direct file inspection when the heuristic summary points to a specific stage or lowering symptom.
9. Compare with parent or baseline evidence when it already exists and is useful.
   - Do not block the round analysis if comparable evidence is missing.
   - Record missing comparison inputs as an evidence gap rather than guessing.
10. Write `opt-round-N/perf-analysis.md`.
   - Include `Attempted Change Attribution`, competing explanations or confounders, attribution confidence/status, and evidence gaps. Deep analysis is not required for every regression; when it is skipped, record `unresolved` attribution in `attempts.md` rather than guessing.
   - Either `profile-only diagnosis` or `profile-plus-IR diagnosis` is acceptable, as long as the document makes the evidence path clear.

## Output contract

Write the analysis as a standalone document with these sections:

1. `# Round Performance Analysis`
2. `## Executive Summary`
3. `## Profile Signals`
4. `## IR Signals`
5. `## Attempted Change Attribution`
6. `## Competing Explanations And Confounders`
7. `## Attribution Confidence And Status`
8. `## Diagnosis`
9. `## Operator Implementation Issues`
10. `## Optimization Suggestions`
11. `## Evidence Gaps`

Inside `## Profile Signals`, prefer these subsections when the evidence exists:

- `### Hotspots`
- `### Pipeline Ratios`
- `### Timeline And Wait`
- `### Host API Overhead`

Inside `## Diagnosis`, prefer these subsections:

- `### Operator Type Fit`
- `### Compute vs Memory Bound`
- `### Pipeline Bottlenecks`
- `### Memory Hierarchy Bottlenecks`
- `### Concurrency And Scheduling Bottlenecks`

## Required reasoning rules

- Treat profile evidence as the default required input.
- Treat IR as optional but strongly preferred when profiler evidence alone does not explain the likely implementation problem.
- Use IR as explanation and attribution for profiler symptoms, not as the default entrypoint.
- Use profiling analysis and IR analysis together when one source alone cannot explain the performance problem confidently.
- Keep artifact ownership here even when IR evidence is used; the corresponding `{language}-npu-analyze-ir` skill is the IR evidence companion, not the owner of `perf-analysis.md`.
- Distinguish facts from inference.
- Cite the specific profile path, IR path, stage name, or operator name that supports each nontrivial conclusion.
- Do not stop at profiler or IR symptoms. The final diagnosis must point to likely problems in the current operator implementation.
- Keep optimization suggestions tied to those diagnosed implementation problems.
- In `## Optimization Suggestions`, distinguish explanations of the attempted direction from newly discovered candidate hypotheses when IR exposes them.
- Make newly discovered hypotheses evidence-backed and route them to a normal future round through `start-round` and the usual correctness and benchmark gates. Do not edit the operator during deep analysis or bypass round entry.
- Do not automatically write the analysis back into `attempts.md` or `summary.md`. `perf-analysis.md` is the formal output of this skill.

Use the profiling and optimization references for detailed signal interpretation and for mapping those signals to likely optimization points. Keep `SKILL.md` focused on workflow, evidence order, and output quality.
