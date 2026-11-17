---
name: triton-npu-optimize-knowledge
description: Symptom routing contract for Triton Ascend NPU optimize pattern selection. Use when choosing an optimization direction or submitting symptom IDs during an optimize round. Pattern card content lives in the cannbot-knowledge repository; this skill only owns the symptom routing contract.
---

# Optimize Knowledge

## Purpose

This skill is the **routing layer** between measured evidence and the optimize
pattern library. It owns exactly two artifacts:

- `references/symptom-contract.json` — the symptom → candidate-pattern mapping
  and explicit `pattern_paths` used internally by `triton-npu-optimize-state` during deep-analysis submission.
- `references/pattern_index.md` — the generated stage tree for pattern triage
  (structural → kernel → refinement → autotune); each entry's Source names the
  cannbot-knowledge card path. This is also the stage source for automatic
  retrieval, including each entry's priority; external card metadata does not override it.

Pattern card **content** is served read-only from the
[cannbot-knowledge](https://gitcode.com/cann/cannbot-knowledge) repository,
provisioned at install time under
`.cannbot/dependencies/triton-optimizer/cannbot-knowledge/`:

The 63 pattern cards live in `knowledge/ops/triton/optimizations/patterns/`.
The 14-symptom contract and stage/priority tree are synchronized to Helix
commit `08d9a4a06c591193d85262bf80b5d77ef23e542f`. The external cards cite
that same source revision. Update the knowledge checkout before deploying this
catalog; older checkouts lack the dedicated cards. Broader technique articles
remain available in the knowledge repository but are not substitutes for these
pattern cards. Historical symptom submissions are not rewritten; new rounds
must select IDs from the current contract.

`pattern_paths` maps each current Helix pattern ID to its card path relative to
`knowledge/ops/triton/optimizations/`. Use the same ID in the symptom candidates,
stage index, retrieval results, and exclusions. Directory and filename changes
in the knowledge repository are represented by this mapping, not by old ID aliases.
A missing mapped file is an error; a symptom without registered candidates
returns no recommendations.

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
2. For profile- or IR-backed routing, read `references/symptom-contract.json`
   for symptom IDs, evidence hints, non-matches, and candidate patterns.
   Deep-analysis submission performs optional recommendation matching internally.
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
