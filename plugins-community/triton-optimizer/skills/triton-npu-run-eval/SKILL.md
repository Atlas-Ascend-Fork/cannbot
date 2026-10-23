---
name: triton-npu-run-eval
description: Execute and evaluate generated operator artifacts. Use when you need to run generated test cases, run generated benchmark cases, fast-screen a candidate operator against a baseline, profile benchmark harnesses, summarize profiling data, or compare performance artifacts, including during optimization workflows.
---

# Run-Eval Router

Use the bundled helper script in this skill. Treat
`<triton-npu-run-eval-skill-path>` as the staged path to the
`triton-npu-run-eval` skill for the active backend:

```bash
python3 <triton-npu-run-eval-skill-path>/scripts/cli.py <subcommand> ...
```

Read only the focused guide for the subcommand you are about to run:

- `run-test-baseline` / `run-test-convert` / `run-test-optimize`: [references/run-test.md](references/run-test.md) for correctness-only or workflow-specific validation
- `run-bench` / `run-bench-baseline`: [references/run-bench.md](references/run-bench.md)
- `profile-bench`: [references/profile-bench.md](references/profile-bench.md)
- `profile-report`: [references/profile-report.md](references/profile-report.md)
- `compare-perf`: [references/compare-perf.md](references/compare-perf.md)

When comparing candidates for promotion on the basis of `run-bench` or
`compare-perf` output, also read
[references/benchmark-noise-control.md](references/benchmark-noise-control.md)
— noise floors, interleaved A/B, and when only direct profiler op time is
trustworthy on a shared device.

When a workflow needs both correctness and benchmark results, run the
`run-test-*` command first and run `run-bench` only after it passes; a failed
correctness gate means the benchmark result is not usable.

During normal use:

- call `python3 <triton-npu-run-eval-skill-path>/scripts/cli.py <subcommand> ...` directly
- do not read unrelated command guides
- do not reread Python files under `<triton-npu-run-eval-skill-path>/scripts/` unless you need to debug, patch, or verify helper behavior

When the current session uses Triton, the runner assigns a private
`TRITON_CACHE_DIR` that is reused within the session. Do not access
`~/.triton` or another session's cache directory; clear only the assigned cache
while no evaluation subprocess is running.
