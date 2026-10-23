---
name: triton-npu-convert
description: Convert one PyTorch operator to a Triton, TileLang, or AscendC Ascend NPU implementation through a spec-first workflow, preserve its public API and input helpers, and validate it with run-test-convert. Use when the user asks to convert a PyTorch operator into an Ascend NPU kernel implementation.
---

# Ascend NPU Convert

Use this skill for a new converted operator artifact. Select the target with
the command's `--lang` value: `triton`, `tilelang`, or `ascendc`.

## Inputs and outputs

- Read one original PyTorch operator file as immutable source material and correctness oracle.
- Preserve its public function/module API, signatures, construction behavior,
  and any input-construction functions defined by the source operator (for
  example, `get_inputs()` or `get_init_inputs()`).
- Write `{language}_<origin-name>.py` (for example, `triton_<origin-name>.py`)
  or the requested explicit `.py` path.
- For AscendC, also write a same-stem `.asc`; the two files are one artifact.

## Workflow

1. Read the original operator and identify its public entrypoint and helpers.
2. Write `spec.json` in the operator workspace as the conversion contract
   derived from the original operator, following
   `references/spec-contract.json`: the preserved public API, the kernel
   decomposition plan, the semantics, and the resolved test plan — the
   existing suitable test to reuse, or the test to generate when none exists.
   Keep it stable for the rest of the run.
3. Read the matching example in `references/convert-to-<language>.md`.
4. Implement the requested target kernel path from `spec.json`. Do not modify, or overwrite the original input operator file.
5. For AscendC, produce the `.asc` source and its compatible `.py` wrapper,
   preserving the original PyTorch API contract.
6. Execute the resolved test plan recorded in `spec.json`. If a suitable test already exists in the operator workspace, reuse it. This includes existing standalone and differential test cases. Do not create a new test when an existing suitable test can be reused unless the user explicitly asks to regenerate it. Otherwise use `triton-npu-gen-test` to create the standalone or differential test file. Run `triton-npu-run-eval`'s `run-test-convert` for the requested standalone or differential test mode and test file. In differential mode, pass the original operator as `--ref-operator-file <original>`.
7. Finish only after the command reports its standard pass output, or report a
   concrete environment blocker.

## Contract files

- `references/spec-contract.json`: authoritative field contract for
  `spec.json`.

## Validation enforcement rules

Correctness validation is a mandatory completion gate. Always use the staged
`triton-npu-run-eval` skill's `run-test-convert` command for both standalone
and differential conversion validation. Do not replace it with ad-hoc Python
comparisons or a direct test-file invocation.

The literal output determines success:

- Differential mode passes only when the command prints `PASS: all N case(s) matched the NPU accuracy contract.` or a matching per-case `PASS case '...' matched ...` message.
- Standalone mode passes only when the command prints `All tests passed!` (or its matching standard success output).
- `FAIL:`, an exception, missing output, or any other output is not a pass.

If validation does not print the required success output, repair the converted
artifact or test and rerun the same `run-test-convert` command.

The following practices are forbidden:

- Do not use `torch.allclose`, `torch.testing.assert_close`, `torch.equal`, or any custom-tolerance numerical comparison to declare conversion correctness.
- Do not run `python3 differential_test_*.py` or another generated test file directly; invoke it through `run-test-convert`.
- Do not create or compare custom `.pt` result files, or self-declare `PASS` from a private comparison script.

## fp32 Cube math mode

For fp32 Cube ops, tensor dtype is not the compute dtype. Check whether the
NPU oracle actually uses IEEE fp32 or HF32, then match that math mode.
Convolution and matmul/bmm can differ; do not assume one family's mode for
the other, and do not "fix" precision by computing more accurately than the
oracle.

## Universal source-language constraint

The converted implementation must not continue using source-language APIs that
perform the original computation. Public wrappers, input/output adaptation,
zero-cost metadata queries, buffer allocation, and target-kernel launches may
remain. The computation itself belongs in the selected target implementation.

All converted computation must target Ascend NPU. Do not add CUDA, CPU, MPS,
or generic multi-backend fallback branches such as `torch.cuda.is_available()`
dispatch unless the original public API genuinely requires shared import-only
structure. A device fallback is not a valid conversion.

For the complete PyTorch-specific form of this rule, read the convert memory
file prepared by the CLI before agent launch.

## Backend references

- [Convert to Triton](references/convert-to-triton.md)

Do not create optimize rounds, baseline artifacts, ad-hoc comparison scripts,
custom result files, or pure source-language fallbacks in this workflow.
