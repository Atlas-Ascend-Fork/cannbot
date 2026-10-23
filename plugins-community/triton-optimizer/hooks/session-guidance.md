# Helix Plugin Session Guidance

This plugin serves two Triton Ascend NPU workflows in this workspace. Use the
section that matches the task the user requests.

## Convert: PyTorch operator to Triton

Use the `triton-npu-convert` skill as the workflow contract.
Read the matching `references/convert-to-triton.md` example before editing.
Treat the original operator as immutable source material and the differential correctness oracle.
Preserve the original public API and any input-construction functions defined by the source operator (for example, `get_inputs()` or `get_init_inputs()`) in the converted output.
The output Python file must be named `triton_<origin-name>.py` unless an explicit output path is requested.
Validate every backend with `run-test-convert`; do not self-declare correctness or use ad-hoc comparisons.
Accept correctness only when standard output contains `PASS:` for differential mode or `All tests passed!` for standalone mode.
Only the standard `run-test-convert` PASS output proves correctness; never use custom tolerances or direct test-file execution.
Never use `torch.allclose` or `torch.testing.assert_close`, run `python3 differential_test_*.py` directly, create custom `.pt` files, or self-declare PASS.
Target Ascend NPU only; do not add CUDA, CPU, MPS, or generic device fallback dispatch.

### Source-language compute constraint (PyTorch example)

The converted implementation must not continue calling source-language APIs
that perform the original computation. Keep only the public PyTorch-facing
API, zero-cost metadata queries, buffer allocation, input adaptation, and
target-kernel launches. Move computation into the target Triton, TileLang,
or AscendC implementation.

For a PyTorch source operator, `forward()` must not use `torch` compute
functions such as `torch.matmul`, `torch.relu`, or `torch.sum`; functional
calls such as `torch.nn.functional.softmax` or `F.linear`; tensor compute
methods such as `x.sum()` or `x.softmax()`; tensor arithmetic such as
`x + y`, `x @ w`, or `x * y`; or `nn.Module` computation calls such as
`self.linear(x)`. These are forbidden even when a target kernel is present.
It may use `torch.empty*`/`zeros`/`ones` for output buffers, shape/reshape/
transpose metadata operations, `.dtype`/`.device`/`.numel()`, and a target
kernel launch followed by returning its output.

## Optimize orchestration

This workspace is under optimize orchestration when running Triton Ascend NPU
optimize work. Use the `triton-npu-optimize-state` skill to manage optimization
workflow state.

### Round workflow

Use these commands for the corresponding lifecycle steps:

- `submit-baseline`: submit the initial baseline.
- `start-round`: open each optimization round.
- `set-current-round-state`: update the active round's strategy or evidence depth.
- `submit-round`: submit each complete round.

- Use validation, hook, and round-state feedback to decide dynamically whether additional flows such as deep optimization, `claim-edit`, or another state update are needed; do not run these conditional flows unless the feedback calls for them.

### Ground rules

- Read files cautiously. Do not read unrelated files speculatively or just in case.
- Prefer the smallest source that can unblock the next decision.
- Follow the user's instructions strictly.

### Analysis

- Choose the analysis level for each round before editing code.
- Treat the current round's recorded strategy and required evidence depth as authoritative over notes or assumptions.
- Escalate analysis in this order: pattern triage, profiling diagnosis, IR attribution, compiler-source escalation.
- Use profiling diagnosis when pattern triage does not identify a supported bottleneck.
- Use measured evidence to select the bottleneck.
- Do not begin with blind tiling or launch-parameter search.
- For operators that use multiple kernels, inspect the measured kernel sequence and producer-consumer dataflow before selecting an optimization.
- Use legality, synchronization, intermediate-memory traffic, and boundary/tail behavior to decide whether to fuse work or retain separate kernel launches. Then investigate grid, computation, memory access, and tiling in that order; benchmark each change and do not assume fewer launches are faster.

### Target and evidence

- Treat `baseline/` as the canonical optimize baseline.
- Use canonical `run-bench` comparison output as the authoritative source for round performance summaries.
- Continue optimizing the Triton Ascend NPU kernel path instead of replacing it with a pure PyTorch rewrite.
- A round that bypasses the Triton kernel path does not count as a successful optimize round.
