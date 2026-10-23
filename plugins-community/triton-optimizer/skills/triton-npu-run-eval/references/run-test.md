# Single-phase test commands

Use the `run-test-*` commands for correctness validation. When the workflow also needs a benchmark, run it with `run-bench` only after the test command exits zero — a failed correctness gate means the benchmark result is not usable.

# `run-test-baseline`, `run-test-convert`, and `run-test-optimize`

Use the single-phase `run-test-*` commands when only correctness is required or when validating a workflow-specific stage. Use `run-test-baseline` for baseline or generation validation, `run-test-convert` for convert validation, and `run-test-optimize` for optimize-round validation.


```bash
python3 <triton-npu-run-eval-skill-path>/scripts/cli.py run-test-baseline --test-file test_<operator>.py --operator-file <operator>.py --test-mode standalone
python3 <triton-npu-run-eval-skill-path>/scripts/cli.py run-test-baseline --test-file differential_test_<operator>.py --operator-file <operator>.py --test-mode differential --ref-operator-file <operator>.py

python3 <triton-npu-run-eval-skill-path>/scripts/cli.py run-test-convert --test-file test_<operator>.py --operator-file triton_<operator>.py --test-mode standalone
python3 <triton-npu-run-eval-skill-path>/scripts/cli.py run-test-convert --test-file differential_test_<operator>.py --operator-file triton_<operator>.py --test-mode differential --ref-operator-file <operator>.py

python3 <triton-npu-run-eval-skill-path>/scripts/cli.py run-test-optimize --test-file differential_test_<operator>.py --operator-file opt_<operator>.py --test-mode differential --ref-operator-file <operator>.py
python3 <triton-npu-run-eval-skill-path>/scripts/cli.py run-test-optimize --test-file test_<operator>.py --operator-file opt_<operator>.py --test-mode standalone
```

Rules:

- Always pass both `--test-file` and `--operator-file`.
- If `--test-mode` is omitted, the command reads `# test-mode: ...` from the test file.
- Use `--test-mode standalone` or `--test-mode differential` only when you need to override the embedded metadata.
- Standalone mode never accepts `--case-id` or `--ref-operator-file`.
- Differential mode optionally accepts `--case-id <id>` when you want to rerun only one declared test case during a repair loop.
- If `--case-id <id>` is omitted in differential mode, the command runs every declared test case.
- In `--case-id` mode, the command compares a single in-memory payload and does not write a new `*_result.pt` archive for the candidate or any reference rerun.
- If you combine `--case-id <id>` with `--ref-operator-file <path>`, the command first checks the derived `<ref_operator>_result.pt` for that one case and reruns only the missing reference case in memory when needed.
- In differential mode, always pass `--ref-operator-file <operator>.py` to use the reference operator for comparison.
- With `--remote` in differential mode, `--ref-operator-file` runs both phases plus the comparison in one remote worker process without transferring `.pt` payloads or writing archives.
- Prefer `--verbose` while debugging failures so the command prints per-case progress and richer error context.

- `run-test-baseline` must be used to validate the correctness of a baseline operator.
- A `run-test-baseline --case-id <id>` execution is diagnostic only. Run the
  full baseline harness successfully before `submit-baseline`.
- `run-test-convert` must be used to validate the correctness of a converted operator.
- `run-test-optimize` must be used to validate the correctness of an optimized operator.
- `run-test-baseline` initially preserves archived `.pt` result payloads so active optimize validation may reuse them. Later optimize round or final cleanup may delete those payloads; they are a cache, not durable evidence.
- The comparison policy is controlled by the execution environment; invoke the run-test command normally.
- There is no compare-level option.

### Triton API-path validation

Every `run-test-*` command statically checks the candidate operator before numerical execution.
When the candidate has Triton source signals, it must preserve the required Triton implementation
path. A Torch NPU or TileLang candidate continues through the existing test flow unchanged.

Remote examples:

```bash
python3 <triton-npu-run-eval-skill-path>/scripts/cli.py run-test-baseline --test-file test_<operator>.py --operator-file <operator>.py --remote user@host:2222
python3 <triton-npu-run-eval-skill-path>/scripts/cli.py run-test-baseline --test-file differential_test_<operator>.py --operator-file <operator>.py --test-mode differential --case-id case-0 --verbose
python3 <triton-npu-run-eval-skill-path>/scripts/cli.py run-test-convert --test-file differential_test_<operator>.py --operator-file triton_<operator>.py --ref-operator-file <operator>.py --remote user@host:2222 --remote-workdir /tmp/helix
python3 <triton-npu-run-eval-skill-path>/scripts/cli.py run-test-optimize --test-file differential_test_<operator>.py --operator-file opt_<operator>.py --ref-operator-file <operator>.py --remote user@host:2222 --remote-workdir /tmp/helix
```
