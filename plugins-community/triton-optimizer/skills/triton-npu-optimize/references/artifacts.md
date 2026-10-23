# Optimization Artifact Contract

## Workspace Layout

Assume the operator workspace is the directory that contains the input operator file.

Expected long-lived artifacts:

- `test_<operator-stem>.py` or the mode-specific generated correctness artifact
- `bench_<operator-stem>.py` or the mode-specific generated benchmark artifact
- `baseline/`
- `baseline/state.json`
- `baseline/<operator>_perf.txt`
- `opt-note.md`
- `learned_lessons.md`
- `opt-round-1/`
- `opt-round-2/`
- ...

Ordinary `*_result.pt` files are temporary run-test artifacts and are not part of the long-lived optimize artifact contract. They may be removed after a round is submitted or during optimize cleanup. Their absence in a completed baseline or terminal round is expected and must not, by itself, trigger another correctness run.

## Top-Level Session Note

`opt-note.md` is the top-level ledger for completed round entries and one final `## Overall Summary`.

The initial `Hardware` block is pre-set before the agent starts. Do not create,
edit, move, or remove that block.

Do not write session-start diagnosis or tentative bottleneck narrative in `opt-note.md`.

For round 1, record the starting hypothesis in `opt-round-1/attempts.md`. For later rounds, keep the initial hypothesis in that round's `attempts.md`.

## Baseline Directory

The canonical optimize baseline lives under `baseline/`.

Required baseline artifacts:

- the baseline operator snapshot or source set under `baseline/`
- `baseline/<operator>_perf.txt`
- `baseline/state.json`

<!-- BEGIN GENERATED BASELINE STATE CONTRACT -->
`baseline/state.json` required fields:

```json
{
  "source_operator": "record the path from the directory that contains `baseline/state.json` to the operator file that baseline preparation started from, normally `../<operator>.py`.",
  "baseline_operator": "record the path from the directory that contains `baseline/state.json` to the operator snapshot saved under `baseline/`, normally `<operator>.py` or another baseline-local path.",
  "test_file": "record the path from the directory that contains `baseline/state.json` to the correctness harness used for the baseline, normally `../test_<operator>.py` or `../differential_test_<operator>.py`.",
  "test_mode": "record the resolved correctness mode used for the baseline run.",
  "bench_file": "record the path from the directory that contains `baseline/state.json` to the benchmark harness used for the baseline, normally `../bench_<operator>.py`.",
  "bench_mode": "record the resolved benchmark mode used for the baseline run.",
  "perf_artifact": "record the path from the directory that contains `baseline/state.json` to the canonical baseline perf artifact, normally `<operator>_perf.txt` or `perf.txt`.",
  "correctness_status": "record the final baseline correctness result; use `passed` only after correctness succeeds. Allowed values: `passed`, `failed`, `not_run`.",
  "benchmark_status": "record the final baseline benchmark result; use `passed` only after the benchmark succeeds. Allowed values: `passed`, `failed`, `not_run`."
}
```

Path-bearing fields in `baseline/state.json` must be written relative to the directory that contains `baseline/state.json`.
<!-- END GENERATED BASELINE STATE CONTRACT -->

Treat these state fields as the authoritative artifact references for baseline validation:

- `baseline_operator`
- `perf_artifact`

That means the checker should first verify the paths declared in `baseline/state.json` instead of guessing from default filenames. Legacy directory scanning is only a fallback when `baseline/state.json` is missing or invalid.

## Per-Round Directory

Each completed round directory must contain:

- the optimized operator file for that round
- `attempts.md`
- `summary.md`
- performance result text copied or summarized from the benchmark run
- any profiler or IR evidence collected for that round, kept in stable round-local directories
- any small auxiliary logs needed to understand the round outcome

Recommended layout:

```text
opt-round-N/
  opt_<original-operator>
  attempts.md
  summary.md
  opt_<original-operator>_perf.txt
  perf-analysis.md
  profile/
  ir/
  logs/
```

Keep the layout simple. Do not create unnecessary nested documentation.

Each completed round must also include `round-state.json`.

<!-- BEGIN GENERATED ROUND STATE CONTRACT -->
`round-state.json` required fields:

```json
{
  "round": "record the completed round directory name, for example `opt-round-1`.",
  "parent_round": "record the baseline or prior round that directly seeded this round, for example `opt-round-2`.",
  "hypothesis": "record the concrete optimization idea that this round tested.",
  "correctness_status": "record the final correctness result for this round; use `passed` only after the round operator passes the chosen correctness check. Allowed values: `passed`, `failed`, `not_run`.",
  "benchmark_status": "record the final benchmark result for this round; use `passed` only after the round benchmark succeeds and the round perf artifact is written. Allowed values: `passed`, `failed`, `not_run`.",
  "summary_path": "record the path from the directory that contains `round-state.json` to the final round summary markdown, normally `summary.md`.",
  "opt_note_updated": "set this to `true` only after the top-level `opt-note.md` entry for this round has been updated."
}
```

`round-state.json` optional fields when present:

```json
{
  "perf_artifact": "record the path from the directory that contains `round-state.json` to the canonical round perf artifact, normally `opt_<operator>_perf.txt`. Required when `benchmark_status` is `passed`; optional when `benchmark_status` is `failed` or `not_run`.",
  "comparison_target_path": "record the path from the directory that contains `round-state.json` to the canonical baseline perf artifact used for comparison, normally `../baseline/<operator>_perf.txt` or `../baseline/perf.txt`. Required when `benchmark_status` is `passed`; optional when `benchmark_status` is `failed` or `not_run`.",
  "effective_metric_source": "record the resolved basis from the canonical `run-bench` comparison that decided the round outcome: `kernel`, `total-op`, or `mixed`. Required when `benchmark_status` is `passed`; optional when `benchmark_status` is `failed` or `not_run`.",
  "analysis_skipped_reason": "when deeper analysis was intentionally skipped, record the evidence-backed reason here.",
  "profile_dir": "when profiler artifacts are part of the round record, record the path from the directory that contains `round-state.json` to that round-local profiler directory, normally `profile`.",
  "ir_dir": "when IR artifacts are part of the round record, record the path from the directory that contains `round-state.json` to that round-local IR directory, normally `ir`.",
  "perf_analysis_path": "when a standalone performance-analysis note exists, record the path from the directory that contains `round-state.json` to that markdown file, normally `perf-analysis.md`."
}
```

Path-bearing fields in `round-state.json` must be written relative to the directory that contains `round-state.json`.
<!-- END GENERATED ROUND STATE CONTRACT -->

Treat these round-state fields as the authoritative artifact references for round validation:

- `summary_path`
- `perf_artifact`
- `perf_analysis_path` when present
- `profile_dir` when present
- `ir_dir` when present

That means the checker should first verify the paths declared in `round-state.json` instead of guessing from default filenames. Legacy directory scanning is only a fallback when `round-state.json` is missing or invalid.

Use these subdirectories consistently:

- `profile/`
  Keep profiler artifacts for the round here, for example a copied-back `PROF_*` directory or a stable local wrapper directory that contains the profiler output.
- `ir/`
  Keep language-specific intermediate-representation or generated-source
  evidence for the round here when the corresponding analysis skill is staged.
- `logs/`
  Use this only for small auxiliary logs that do not justify a dedicated contract of their own.

## Summary Requirements

`opt-round-N/summary.md` should include:

- parent round or parent candidate
- optimization hypothesis
- final selected pattern direction when a named pattern guided the round
- `Primary analysis level`
- `Supporting evidence`
- final analysis level
- why that hypothesis looked plausible
- what evidence motivated the round
- which evidence actually decided the round outcome
- whether the round pivoted away from an earlier pattern choice
- code changes that mattered
- correctness validation result
- benchmark comparison
- whether this round becomes the current best candidate
- open questions

For a negative or inconclusive round, summarize the narrow observation and tested scope, attribution status, disposition, and unresolved questions without duplicating the full negative-evidence record.

The optimization points section is required. This is the part future engineers are most likely to reuse.

## Attempt Log Requirements

`opt-round-N/attempts.md` should be updated throughout the round, not only at the end.

Record at least:

- the initial round hypothesis
- candidate patterns considered at the start of the round when pattern triage is used
- the selected pattern and why it looked plausible when a pattern-backed direction is chosen
- for a seriously considered high-value structural candidate that is not implemented, the concrete legality or measured-cost evidence supporting its `reject` or `defer` disposition
- `Primary analysis level`
- `Supporting evidence`
- the current analysis level
- why the hypothesis may help
- what evidence supports the round direction
- why the round stayed at that level or why it escalated deeper
- why profiling or IR capture was skipped, when those tools were not used
- any reused deeper evidence path when the round starts below pattern triage
- pattern pivots, including when deeper profile or IR evidence weakens or overturns the earlier pattern choice
- each meaningful code change or optimization attempt
- correctness failures and how they were repaired
- benchmark outcomes, including regressions or inconclusive results
- for negative or inconclusive outcomes, separate `Observation`, `Attribution` (`established`, `plausible`, or `unresolved`), concise tested `Scope`, `Confounders and disconfirming evidence`, and `Disposition` (`block`, `permit`, or `motivate`); preserve the retry quartet when retrying
- decisions to continue, pivot, or abandon the current round idea

Keep entries chronological so another engineer can reconstruct how the round evolved.

## Bench Evidence

- Preserve the normalized benchmark result from `run-bench`.
- For a valid round, the round-local perf artifact must be the generated `opt_<original-operator>_perf.txt`.
- That `opt_<original-operator>_perf.txt` file must be produced by the `triton-npu-run-eval` skill's `run-bench` flow for the round operator, not handwritten, post-processed, or substituted from another workflow.
- Keep enough evidence to reconstruct the performance claim without rerunning the entire round immediately.
- Keep `opt_<original-operator>_perf.txt` even when profiler or IR evidence also exists; richer evidence does not replace the round's basic benchmark summary.

## Deep Analysis Evidence

- When a round needs deeper diagnosis, prefer writing a standalone `perf-analysis.md` in the round directory.
- Treat `perf-analysis.md` as optional in the first iteration of this workflow, not a required artifact for every round.
- When `round-state.json` declares `perf_analysis_path`, that path becomes the authoritative location for the analysis file.
- Treat the content and structure of `perf-analysis.md` as owned by `triton-npu-analyze-round-performance`, not by the optimize workflow contract.

## Profile And Optional Analysis Evidence

- When profiling is needed for a round decision, keep the resulting profiler artifacts under `opt-round-N/profile/`.
- When the language-specific analysis skill is staged, keep its IR or generated-source evidence under `opt-round-N/ir/`.
- Prefer preserving profiler and optional analysis evidence inside the round that motivated it instead of scattering those artifacts at the workspace top level.
- If the same evidence informs multiple later rounds, mention the reused path explicitly in `attempts.md` or `summary.md` rather than copying large directories repeatedly.

## Original Operator

- Treat the original input file as round 0.
- Never edit the original file in place during optimization rounds.
- Use copied operator files inside round directories for experimental edits.

## Learned Lessons Log

`learned_lessons.md` is a top-level strict reusable optimization-knowledge log for the whole optimization session.

Only add an entry when it is evidence-backed, portable to related Ascend NPU operators, and written as a reusable rule, diagnostic mapping, or optimization heuristic. Each entry should state where the lesson applies or what limits it. One negative round cannot directly create a universal prohibition: a negative lesson needs portable scope, evidence-backed attribution, applicability limits, and important alternative explanations that survived testing. Prefer risk or diagnostic guidance over universal rejection.

Use it for durable notes that should survive beyond one round, such as:

- profile-to-optimization mappings
- IR-to-code-change mappings
- compiler error repairs that reveal recurring Ascend NPU constraints
- code patterns that suggest an optimization opportunity
- validated heuristics that are not yet documented in the pattern library

Round-local command failures, failed guesses, file names, shape-specific details, temporary troubleshooting notes, and narrative summaries of what happened in one round belong in `attempts.md`, `summary.md`, or `opt-note.md`, not in `learned_lessons.md`.
