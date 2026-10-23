# `run-bench`

Run a generated benchmark with:

```bash
python3 <triton-npu-run-eval-skill-path>/scripts/cli.py run-bench-baseline --bench-file bench_<operator>.py --operator-file baseline/<operator>.py --output baseline/<operator>_perf.txt
python3 <triton-npu-run-eval-skill-path>/scripts/cli.py run-bench --bench-file bench_<operator>.py --operator-file <operator>.py
python3 <triton-npu-run-eval-skill-path>/scripts/cli.py run-bench --bench-file bench_<operator>.py --operator-file opt_<operator>.py
python3 <triton-npu-run-eval-skill-path>/scripts/cli.py run-bench --bench-file bench_<operator>.py --operator-file opt_<operator>.py --baseline-operator-file <operator>.py
python3 <triton-npu-run-eval-skill-path>/scripts/cli.py run-bench --bench-file bench_<operator>.py --operator-file opt_<operator>.py --baseline-operator-file <operator>.py --metric-source all --skip-latency-errors
python3 <triton-npu-run-eval-skill-path>/scripts/cli.py run-bench --bench-file bench_a.py --operator-file a.py --output ./artifacts/a_perf.txt
```

Rules:

- Always pass both `--bench-file` and `--operator-file`.
- Use `run-bench-baseline` for the final baseline benchmark. Give it `--output`
  for the perf path that `baseline/state.json` will declare.
- If `--bench-mode` is omitted, defaults to `torch-npu-profiler`.
- Use `--bench-mode torch-npu-profiler` or `--bench-mode perf-counter` only when you need to override the default. `--bench-mode msprof` is still accepted as a deprecated alias: it runs the `torch-npu-profiler` path and prints a deprecation notice.
- Use `--output <path>` when you need the perf artifact at a specific location.
- Use `--baseline-operator-file <path>` when you want `run-bench` to reuse or generate the baseline perf artifact automatically and then compare it against the candidate perf artifact. During an active optimize round, this may be a temporary comparison operator created for exploration; only the canonical baseline comparison satisfies the round's final benchmark gate.
- Use `--skip-latency-errors` when you want automatic baseline comparison to continue past recoverable latency-error entries.
- Use `--metric-source auto|kernel|total-op|all` when you want automatic baseline comparison to use a specific comparison basis.
- On success without `--baseline-operator-file`, `run-bench` prints `Perf file: <path>` and a short hint to use `compare-perf` instead of reading perf files directly.
- On success with `--baseline-operator-file`, `run-bench` prints `Baseline perf file: <path>`, `Perf file: <path>`, and the automatic comparison output.
- On failure, `run-bench` prints the captured benchmark output so the error remains diagnosable.

Baseline compare notes:

- The baseline perf artifact path is derived from `--baseline-operator-file` using the normal `<operator-stem>_perf.txt` naming rule beside that file.
- If that baseline perf artifact already exists, `run-bench` reuses it and does not rerun the baseline benchmark.
- If that baseline perf artifact does not exist, `run-bench` benchmarks the baseline operator first to create it, then benchmarks the candidate operator from `--operator-file`, then compares the two perf files automatically.

Fast probe (optimize-round screening):

- Use `--fast-probe` only inside an active optimize round for a cheap directional screen; outside a managed round the flag is rejected.
- `--fast-probe` caps warmup/repeats at 1/3 and only supports the default `torch-npu-profiler` mode.
- It never generates or replaces the canonical baseline perf artifact; the baseline perf file must already exist (run a full `run-bench` first).
- The candidate perf artifact defaults to `<operator-stem>_probe.txt` beside the operator file instead of the canonical `<operator-stem>_perf.txt`.
- The comparison output ends with a disclaimer that capped warmup/repeats make it a screening signal, not a reliable conclusion; the run is recorded in evidence and round timing as non-authoritative and never counts as the round's benchmark evidence.

Mode notes:

- In both modes, the benchmark file is import-only. `run-bench` imports the module, calls `build_operator_api(operator_module)`, reads the declared cases from `build_bench_cases()`, and constructs each executable case via `build_bench_case_fn(operator_api, case)`.
- In `torch-npu-profiler` mode, the runner profiles each declared case with `torch_npu.profiler` and writes `latency-<case-id>` perf entries.
- In `perf-counter` mode, the runner measures per-iteration wall-clock time with `time.perf_counter()` instead of using NPU profiling. Results include `kernel_avg_time_us` (per-iteration average) but `ops` is empty. `total_op_avg_time_us` equals `kernel_avg_time_us`. Results are only comparable within the same mode; `compare-perf` rejects cross-mode comparisons.

Examples:

```bash
python3 <triton-npu-run-eval-skill-path>/scripts/cli.py run-bench --bench-file bench_<operator>.py --operator-file <operator>.py --bench-mode torch-npu-profiler
python3 <triton-npu-run-eval-skill-path>/scripts/cli.py run-bench --bench-file bench_<operator>.py --operator-file opt_<operator>.py --baseline-operator-file <operator>.py
python3 <triton-npu-run-eval-skill-path>/scripts/cli.py run-bench --bench-file bench_<operator>.py --operator-file opt_<operator>.py --baseline-operator-file <operator>.py --metric-source kernel
```

Remote examples:

```bash
python3 <triton-npu-run-eval-skill-path>/scripts/cli.py run-bench --bench-file bench_<operator>.py --operator-file <operator>.py --remote user@host:2222
python3 <triton-npu-run-eval-skill-path>/scripts/cli.py run-bench --bench-file bench_<operator>.py --operator-file opt_<operator>.py --bench-mode perf-counter --remote user@host:2222 --remote-workdir /tmp/helix
```
