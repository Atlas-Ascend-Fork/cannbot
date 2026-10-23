# Triton Optimizer Plugin

`triton-optimizer` packages the Claude optimize workflow and Triton convert workflow for Triton Agent in CANNBot.

It provides two workflow entry skills:

- `triton-npu-optimize`: optimize an existing Triton Ascend NPU operator through validated rounds anchored to a canonical baseline.
- `triton-npu-convert`: convert a PyTorch operator into a PyTorch-facing Triton Ascend NPU implementation through a spec-first workflow and validate it with `run-test-convert`.

Supporting skills (state management, baseline preparation, test/benchmark generation, run-eval, profiling, IR and compiler-source analysis, pattern knowledge, repair guidance) are bundled alongside the entry skills in the plugin `skills/` directory and invoked by the entry skills as needed.

Workflow hooks provide SessionStart runtime-state bootstrap (`.helix/`) and PreToolUse guardrails.
