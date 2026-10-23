---
name: triton-npu-optimize-knowledge
description: Symptom routing contract for Triton Ascend NPU optimize pattern selection. Use when choosing an optimization direction or submitting symptom IDs during an optimize round. Pattern card content lives in the cannbot-knowledge repository; this skill only owns the symptom routing contract.
---

# Optimize Knowledge

## Purpose

This skill is the **routing layer** between measured evidence and the optimize
pattern library. It owns exactly two artifacts:

- `references/symptom-contract.json` — the symptom → candidate-pattern mapping
  used by `triton-npu-retrieve-patterns` and validated by `submit-deep-analysis`.
- `references/pattern_index.md` — the generated stage tree for pattern triage
  (structural → kernel → refinement → autotune); each entry's Source names the
  cannbot-knowledge card path.

Pattern card **content** is served read-only from the
[cannbot-knowledge](https://gitcode.com/cann/cannbot-knowledge) repository,
provisioned at install time under
`.cannbot/dependencies/triton-optimizer/cannbot-knowledge/`:

- `knowledge/ops/triton/optimizations/patterns/` — trigger-condition pattern cards
- `knowledge/ops/triton/optimizations/operator_optimization/` — optimization-point cards

## Scope

- This skill is reference-only and owns no pattern card content.
- This skill does not define optimize workflow behavior.
- This skill does not own `opt-round-N/perf-analysis.md`, `attempts.md`, `summary.md`, or `opt-note.md`.
- `triton-npu-optimize` owns optimize workflow and validation rules.
- `triton-npu-analyze-round-performance` owns round-level performance diagnosis.

## Reading Order

1. For code-structure triage, read `references/pattern_index.md` and follow its
   stage order from structural through kernel and refinement to autotune; each
   entry's Source points at the cannbot-knowledge card with the full content.
2. For profile- or IR-backed routing, run the `triton-npu-retrieve-patterns` skill's
   `scripts/retrieve_patterns.py list` to see every symptom ID with its one-line
   summary, `info <id>` for one entry's evidence hint, non-matches, and candidate
   patterns, and `patterns <id>` to preview the candidate cards.
   `references/symptom-contract.json` stays the underlying single source of truth;
   do not read it whole.
3. Before calling `submit-deep-analysis`, choose one to five symptom IDs this way.
   Submit them with repeated `--symptom <id>` arguments. Use `unknown` alone when
   none applies; do not invent an ID or combine `unknown` with another symptom.
4. Read only the one or two most relevant cards from the cannbot-knowledge
   patterns library after routing narrows the candidate set.

## Reasoning Rules

- Treat the symptom contract and pattern cards as routing aids, not a hard rule engine.
- Return to the caller skill for diagnosis, optimization choice, and recordkeeping.
- Keep specialized packs such as `triton-npu-cann-ext-api-patterns` separate unless the caller explicitly needs them.
- Symptom IDs are evidence labels, not conclusions. Submit an ID only when its distinguishing code, profile, IR, or shape evidence is present.
- Pattern recommendations are optional and controlled by `HELIX_OPTIMIZE_RECOMMEND_PATTERNS`; when returned, inspect the supplied `summary` and every `use_when` condition before choosing a direction.
