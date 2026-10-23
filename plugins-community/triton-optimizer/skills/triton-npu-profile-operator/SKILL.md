---
name: triton-npu-profile-operator
description: Get and analyze Ascend NPU operator performance data. Use for profiling Ascend operators, identifying hot operators and timing bottlenecks, summarizing performance evidence, comparing profiling results across runs, or inspecting profiler artifacts such as msprof outputs, CSV summaries, and JSON timelines.
---

# Ascend NPU Operator Profiler

Profile Ascend NPU operators and summarize the resulting timing data.

## Default workflow

### Profiling + summary (profile-bench)

1. Profile benchmark harnesses through the `triton-npu-run-eval` skill's `profile-bench` helper.
   - For the exact wrapper invocation, read that skill's `references/profile-bench.md`.
   - The standard argument shape is:

   ```text
   profile-bench --bench-file bench_matmul.py --operator-file matmul.py --case-id <id>
   ```

2. The helper runs the profiler, copies back the generated local `PROF_*` directory, and prints a summary inline.

3. Review the inline summary in the conversation. Call out:
   - which operator was analyzed
   - whether that operator was explicit or inferred
   - total, average, min, and max time
   - runtime ratio and top hotspots

### Re-reporting without re-profiling (profile-report)

When the profiling data already exists (e.g. from a previous `profile-bench` run), use `profile-report` to generate a new summary without re-running the benchmark:

```text
profile-report --profile-dir PROF_000001_.../ --target-op matmul_kernel
```

For round-analysis workflows that need structured signals, use JSON mode:

```text
profile-report --profile-dir PROF_000001_.../ --target-op matmul_kernel --format json
```

This is useful when you want to:
- Inspect the same `PROF_*` data with different `--target-op` values
- Re-summarize historical profiling data
- Emit structured JSON for downstream workflows without re-profiling

## Working rules

- Prefer the `triton-npu-run-eval` skill's `profile-bench` helper for benchmark profiling, especially when the workflow is remote-aware.
- Profile one selected `--case-id <id>` case; benchmark profiling must not receive `--bench` or `--num-bench`.
- When the outer task is remote-aware, pass the same `--remote` and `--remote-workdir` settings through `profile-bench` so profiling runs on the remote machine while the resulting `PROF_*` directory is copied back locally.
- Keep direct `msprof <command>` only as a local fallback when there is no generated benchmark harness or when the user explicitly wants a manual invocation.
- Treat `op_summary_*.csv` as potentially large. Do not dump it into the conversation or read it naively line-by-line into memory if a streaming pass is enough.
- Prefer the bundled summary script over ad hoc shell parsing so the report stays consistent.
- Prefer the bundled summary script in JSON mode when the downstream task is `triton-npu-analyze-round-performance` or any profiler-first layered analysis workflow.
- If the user names the operator, pass it through `--target-op`.
- If the user does not name the operator, let the script infer the hottest operator from `op_statistic` and state that this is an inference.
- Always show the final Markdown summary in the conversation instead of only mentioning generated files.

## Pipeline-evidence boundary

- `pipeline_signals.ratios` preserves raw values and only supplies
  `normalized_percent_avg` after its stage time divided by the matching AIC/AIV
  engine time validates the unit. A bare low ratio is `unknown`; do not infer a
  fraction from its amplitude or CANN version.
- Treat `task_wait` as an `inter_task_gap`, never proof of kernel-internal MTE
  and compute overlap. `internal_overlap=not_observable` is the expected
  result unless mapped engine intervals are present.
- Profile alone supports hotspots, host overhead, transfer operators, and
  engine-family activity symptoms. It does not prove tile shape, K-loop depth,
  generated handshakes, launch fill, or software-pipeline quality.
- For a pipeline recommendation, associate the same revision, candidate
  directory, `--case-id`, resolved shape/dtype, profile `--target-op`, and IR
  `--kernel`, then run `capture_ir.py` followed by `pipeline-structure`.

## Instruction-level timeline (msprof op InstrTimeline)

When pipe ratios show high vector activity and you need instruction-level
evidence, use `msprof op --aic-metrics=InstrTimeline`. For a pure vector
kernel, pass `--instr-timeline-pipe=vector`. For a kernel that mixes Vector
and Cube work, pass the quoted `--instr-timeline-pipe='vector|cube'`; one
capture contains both pipe groups. The trace is a per-instruction
`trace.json` (timestamps, durations, and PC fields). For Triton traces,
group by `tid` before aggregating event names and use the bundled summary
script; do not apply the AscendC bubble formula to overlapping Triton `dur`
values.

Key interpretation rule: near-zero issue gaps with a saturated vector pipe
mean the kernel is instruction-issue bound; do not chase bubbles, reduce the
instruction count instead.

## Bench mode contract

- Use:
  ```text
  profile-bench --bench-file bench_<operator>.py --operator-file <operator>.py --case-id <id>
  ```
- Runtime command shape inside the helper:
  ```bash
  python3 run_bench_execution.py profile-one --bench-file bench_<operator>.py --operator-file <operator>.py --case-id <id>
  ```
- Do not pass `--bench` or `--num-bench`.
- The helper profiles one selected `--case-id <id>` case with `torch_npu.profiler`. The retired `msprof` bench mode is a deprecated alias for this same torch-npu-profiler path.

## Validation checks

- Accept any of these input shapes for CSV summarization: a `PROF_*` directory, a `mindstudio_profiler_output/` directory, or a parent directory that contains one of them.
- Before summarizing CSV output, confirm `mindstudio_profiler_output/` exists and contains at least one `op_statistic_*.csv`.
- When `op_summary_*.csv` exists, use it as a cross-check for the target operator but keep the main summary anchored on `op_statistic`.

## Failure handling

- If no profile directory can be resolved, re-run the profiling command and check the working directory.
- If `mindstudio_profiler_output/` or `op_statistic_*.csv` is missing, stop and report that the profiler output is incomplete.
- If the requested operator is not present in `op_statistic`, list the available operators and ask the user to confirm the target.
- If `op_summary` uses unrecognized columns, fall back to `op_statistic` and mention that the `op_summary` aggregation was unavailable.

## Bundled resources

- `scripts/reporter.py`
  Unified profile reporter used by the `profile-report` subcommand. Loads profiles from either mode, runs classification (operator type, bound analysis), and renders Markdown or JSON output.

- `scripts/models.py`
  Typed data model for parsed profile data (`OperatorStats`, `KernelInvocation`, `PipelineStage`, `ParsedProfile`). Shared by `reporter.py` and all parsers.

- `scripts/parser_base.py`
  Shared parsing utilities: mode auto-detection, `op_statistic` CSV parser, `api_statistic` CSV parser. Used by both mode-specific parsers.

- `scripts/msprof_parser.py`
  Parses `PROF_*/mindstudio_profiler_output/` artifacts: `op_statistic`, `op_summary`, `task_time`, `api_statistic`, `msprof` JSON.

- `scripts/torch_npu_profiler_parser.py`
  Parses `ASCEND_PROFILER_OUTPUT/` artifacts: `op_statistic`, `kernel_details`, `operator_details`, `step_trace_time`, `api_statistic`, `trace_view`.

- `scripts/instr_timeline_summary.py`
  Summarizes an msprof InstrTimeline `trace.json`: per-stream counts and wall
  spans, per-`tid`/event-class duration shares, issue-interval percentiles for
  `VF`/`VF_SIMT`/`MMAD`, and distinct PC counts. It deliberately does not
  compute bubble or idle-gap estimates because Triton event durations overlap.

- `references/profiler-csv-spec.md`
  Read this when you need the expected CSV layout or column names for `op_statistic` and `op_summary`.

- `references/msprof-op-instr-timeline-triton.md`
  Read this when the operator under test is a Triton kernel: msprof injection and interpreter compatibility, kernel-name suffix filtering, per-pipe event vocabulary, and the analysis views that replace PC-to-source mapping.

## Examples

Profile a benchmark and summarize the hottest operator:

```text
profile-bench --bench-file bench_matmul.py --operator-file matmul.py --case-id fp16_1024
```

Profile a benchmark and summarize a known operator:

```text
profile-bench --bench-file bench_matmul.py --operator-file matmul.py --case-id fp16_1024 --target-op MatMul
```

Profile one benchmark case on a remote machine and keep the remote workspace:

```text
profile-bench --bench-file bench_matmul.py --operator-file opt_matmul.py --case-id fp16_2048 --remote user@host:2222 --remote-workdir /tmp/helix --keep-remote-workdir
```

Fallback manual profiling when you intentionally bypass the helper:

```bash
msprof python3 run_bench_execution.py exec-one --bench-file bench_matmul.py --operator-file matmul.py --case-id fp16_1024
```

Then re-summarize the copied-back profile through the `triton-npu-run-eval` skill's `profile-report` helper, for example `profile-report --profile-dir PROF_000001_.../ --target-op MatMul`.
