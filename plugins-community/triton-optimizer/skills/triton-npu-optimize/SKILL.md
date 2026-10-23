---
name: triton-npu-optimize
description: Iteratively optimize an Ascend NPU operator through correctness and performance gates. Use for multi-round optimization with a canonical baseline, tracked evidence, and profiler-backed diagnosis.
---

# Optimize

## Goal

Optimize one Ascend NPU operator through validated rounds anchored to a
canonical `baseline/`. Use this skill when the operator itself should improve,
rather than only generating or running tests and benchmarks.

Optimize target modes:

- `kernel`: optimize the measured kernel path. Prefer the kernel-oriented
  comparison emitted by canonical `run-bench` and record any total-op fallback
  in `effective_metric_source`.
- `operator`: optimize end-to-end operator latency. Wrapper logic, data
  movement, scheduling, pre-processing, post-processing, and kernel code are
  valid surfaces. Show both comparison views and use total-op as the canonical
  conclusion.

## Outputs

- `baseline/`
- `opt-round-N/`
- completed round entries and one final `## Overall Summary` in `opt-note.md`
- round-local `profile/`, `ir/`, `perf-analysis.md`, or
  `compiler-analysis.md` when deeper investigation is needed

## Core Loop

1. Establish or reuse `baseline/`.
2. Open `opt-round-N/` with `triton-npu-optimize-state start-round` and begin
   `attempts.md`.
3. Choose the shallowest analysis level that justifies the next move.
4. Make one coherent code-changing optimization attempt.
5. Optionally use `run-bench --fast-probe` for a non-canonical directional screen.
6. Validate correctness, benchmark, compare, and record the outcome.
7. Stop editing the round after its first canonical `run-bench` comparison
   conclusion. Put a new idea in a new round.

## Stage 0: Baseline Setup

- Reuse `baseline/` only when it remains canonical for the workspace.
- Otherwise use `triton-npu-prepare-optimize-baseline` before creating
  `opt-round-1/`.
- Read [artifacts.md](references/artifacts.md) before selecting baseline or
  round paths and [opt-note-format.md](references/opt-note-format.md) before
  updating `opt-note.md`.
- Use sibling skills for baseline preparation, evaluation, profiling, optional
  analysis, and round gating. Do not bypass their contracts with helper-script
  paths.

## Stage 1: Round Entry

- Create each `opt-round-N/` from a validated parent and record the parent.
- Before the first edit, use `triton-npu-optimize-state start-round` to set the
  round strategy, analysis policy, and reason.
- Start `attempts.md` immediately. Its structured `State Update` blocks are
  script-written history; do not duplicate that state in `summary.md`.
- Record the hypothesis, primary analysis level, supporting evidence, selected
  pattern direction when used, and why the evidence supports the round.
- If the intent or required evidence depth changes, use
  `triton-npu-optimize-state set-current-round-state` before continuing.

## Stage 2: Layered Analysis

The base escalation order is `pattern triage -> profiling diagnosis`.

### Pattern Triage

- Inspect current code structure and benchmark behavior before choosing a direction.
- Use the staged `{language}-npu-optimize-knowledge` skill as the generic optimize knowledge library. Its `references/symptom-contract.json` is the routing contract and `references/pattern_index.md` is the stage-ordered triage index; pattern card content is served from the provisioned cannbot-knowledge clone (`knowledge/ops/{language}/optimizations/patterns/` and `.../operator_optimization/`).
- When the optimize target is `operator`, also use the staged `torch-npu-optimize-knowledge` skill for Torch NPU and whole-operator pattern routing such as framework-op fallback, wrapper-level changes, or broader operator restructuring.
- Read the staged `{language}-npu-optimize-knowledge` skill's `references/pattern_index.md` before detailed pattern references and follow its stage order. High/Normal applies within a stage and never overrides that order; each index entry's Source names the cannbot-knowledge card.
- Read only the one or two most relevant detailed pattern cards from the cannbot-knowledge library after symptom routing has narrowed the candidate set.
- Do not leave the chosen pattern implicit in free-form prose; write it down explicitly in `attempts.md`, and carry the final named pattern direction into `summary.md` when it guided the round.
- For pattern-driven candidate selection, follow the generated stage tree: structural changes first, then kernel-local algorithm/dataflow/storage changes, then refinement, and autotune last.
- Skip patterns whose triggers do not match, but do not let a later-stage High pattern bypass an applicable earlier-stage candidate. Not every stage needs to produce a change.
- Avoid consecutive causally equivalent low-information variants. Before retrying a prior no-benefit direction, identify in `attempts.md`: the prior negative result, the causally relevant changed condition, why that change may invalidate or narrow the prior conclusion, and the expected discriminator.
- Possibly relevant changed conditions include shape regime, dtype, tile/precision coupling, mask/boundary regime, fusion/materialization boundary, grid ownership, compiler lowering, hardware target, effective metric source, and bottleneck attribution. This list is not automatic permission to retry; explain why the named condition is causally relevant.
- Renaming or rephrasing the direction, changing source spelling, making unrelated parameter changes, or performing deeper analysis by itself does not establish a new condition.
- If no causally relevant changed condition can be named, pivot instead of retrying. Normally pivot after at most three no-benefit attempts in one direction even when informative retries were justified; this is guidance, not mechanical enforcement.

### Shape-Aware Performance Review

- When the runner-owned `performance-review.md` exists, read it before choosing the next optimization direction.
- Keep geomean speedup as the primary overall objective, while inspecting every case, the worst cases, and regressions, especially large or high-impact shapes.
- Do not add shape branches for noise or small differences. Consider localization only when the divergence is stable and supported by causal profile, IR, or shape evidence.
- Benchmark a localized candidate as the complete composed operator: specialized path, generic fallback, and dispatch overhead.
- Prefer a simpler uniform implementation when overall performance is comparable.

- Start at the shallowest sufficient level and record every escalation and its
  reason. Do not infer the current level from artifact presence.
- Use the staged `{language}-npu-optimize-knowledge` skill for generic pattern
  and symptom references: its `references/symptom-contract.json` is the routing
  contract, `references/pattern_index.md` is the stage-ordered triage index, and
  pattern cards live in the provisioned cannbot-knowledge clone.
- Pattern guidance is optional, but record a selected named pattern in
  `attempts.md` and `summary.md` when it guided the round.
- Treat regressions, no-benefit, and inconclusive results as narrow observations
  about the tested implementation and conditions. Record Observation,
  Attribution, Scope, Confounders, and Disposition. A retry requires a
  materially changed causal condition and expected discriminator.

### Profiling Diagnosis

- Use `triton-npu-profile-operator` and
  `triton-npu-analyze-round-performance` when benchmark behavior needs deeper
  diagnosis.
- If the `triton-npu-retrieve-patterns` skill is available, it may be used
  for pattern routing; read that skill's SKILL.md for usage.
- Keep profiler evidence under `opt-round-N/profile/` and write
  `opt-round-N/perf-analysis.md` when that analysis flow is used.
- Use the current language knowledge skill's pattern and symptom contract when
  available after structured profiler evidence instead of rereading the entire
  knowledge library.

### Optional IR Attribution

Enter this layer only when `{language}-npu-analyze-ir` is staged and
profiler-backed evidence still needs explanation. Keep artifacts under
`opt-round-N/ir/`. Use its findings only to form a subsequent normal round;
never edit during deep analysis or bypass round entry.

### Optional Compiler-Source Escalation

Enter this layer only when `{language}-npu-analyze-compiler-source` is staged,
compiler-source analysis is enabled, and profiler plus IR evidence have
narrowed a concrete compiler-side question. Treat the compiler source as
read-only and write `opt-round-N/compiler-analysis.md`.

## Stage 3: Validate And Record

- Run correctness before trusting performance. Treat ordinary `*_result.pt`
  files as temporary run-test artifacts; their absence from a completed round
  does not itself require another correctness run.
- Use `run-bench --fast-probe` only as a non-canonical screen. You may also
  pass a temporary `--baseline-operator-file` for exploratory comparisons;
  they never replace the canonical baseline and never satisfy the round gate.
  Run canonical `run-bench` before claiming a round outcome; managed
  `run-bench` emits the comparison.
- Keep `opt_<original-operator>` and
  `opt_<original-operator>_perf.txt` in each round. The perf artifact must be
  produced by `triton-npu-run-eval run-bench`.
- Use the comparison emitted by canonical `run-bench` as the authority for
  claimed deltas and speedups. Record one `effective_metric_source`: `kernel`,
  `total-op`, or `mixed`.
- If a round is slower, inconclusive, or not worth promoting, close it as a
  non-promoted branch. If canonical validation cannot complete, record honest
  status and submit the terminal branch instead of leaving it unresolved.
- Use `triton-npu-optimize-state submit-round`, then follow its JSON
  `guideline` stop-or-continue signal.

## Records And Lessons

- `attempts.md`: chronological hypotheses, evidence, changes, validation, and
  pivots.
- `summary.md`: concise conclusion, optimization points, final analysis level,
  deciding evidence, and unresolved questions.
- `opt-note.md`: top-level ledger and final summary.
- `learned_lessons.md`: only reusable, evidence-backed rules that transfer to
  related Ascend NPU operators. Keep round narrative and local failures in
  round artifacts.

## Hard Rules

- Optimize the operator, not generated test or benchmark harnesses.
- Do not claim success without correctness and benchmark evidence.
- Do not hand-calculate speedups from raw perf files.
- Do not finish a round by restoring the parent snapshot alone.
- Do not write forward-looking multi-round plans. Choose the next direction
  from fresh evidence after the current round.
