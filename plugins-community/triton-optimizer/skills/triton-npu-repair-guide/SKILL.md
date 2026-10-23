---
name: triton-npu-repair-guide
description: >-
  Heuristic fixes for Ascend Triton compile/JIT/kernel errors and numerical precision mismatches when editing or converting the operator.
  Use when a Triton Ascend NPU operator hits compile, JIT, launch, or kernel-structure errors or precision mismatches.
  Does not replace triton-npu-gen-test, triton-npu-gen-bench, or harness specs.
---

# Triton repair experience (Ascend)

Use this skill when **repairing the operator** after Triton/Ascend **compilation**,
**JIT**, **kernel-side** failures, or **numerical mismatches** vs the torch baseline
— especially during `convert`, `optimize`, or any flow
that exercises the real Triton path.

Patterns and code hints live in [references/repair-experience.md](references/repair-experience.md).
Match the error or symptom, apply a **minimal** change, then re-run validation.

## Relationship to other skills

- Does **not** replace `triton-npu-gen-test`, `triton-npu-gen-bench`, or normative harness specs.
- Complements `triton-npu-run-eval` (re-validate after applying a heuristic).
- When a generation-only workflow such as `triton-npu-gen-test` or `triton-npu-gen-bench` stages this skill, use it as a diagnostic reference for compile, JIT, launch, kernel-side, or numerical symptoms.

## How to apply

1. Open [references/repair-experience.md](references/repair-experience.md) and match error text or symptom to a section.
2. Apply the smallest change; re-run validation through the `triton-npu-run-eval` skill, using `run-test-baseline` or `run-test-optimize` / `run-bench` as appropriate, and prefer `--verbose` on `run-test` while diagnosing failures.
3. If nothing fits, do **not** force a heuristic—fall back to logs, IR skills, or deeper debugging.

## Recording a new fix

If you fixed the operator with a pattern `repair-experience.md` does not
cover, record the symptom, the fix, and how you verified it in the workspace's
`learned_lessons.md` when that flow maintains one.
