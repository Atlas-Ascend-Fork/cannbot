---
name: triton-npu-op-coding-guide
description: Per-category Triton-Ascend operator-writing guidance — writing essentials, common mistakes with fixes, and recommended skeleton patterns. Use when implementing or converting a Triton Ascend NPU operator and category-specific coding guidance is needed. Reference-only; does not define workflow.
---

# Op Coding Guide

## Purpose

This skill is the per-category writing guide for Triton-Ascend operators. It
states what must be right in a first implementation: structure, dtype and
precision rules, mask and addressing discipline, grid legality, and the
category-specific patterns and mistakes.

## Scope

- This skill is reference-only. It does not define workflow behavior or own
  any artifact.
- It states pre-measurement rules: what is correct and legal before any
  profiling. Performance tuning that requires bottleneck identification
  (tile search, scheduling experiments, precision ablations) belongs to the
  optimize phase, not here.
- `triton-npu-repair-guide` owns failure signatures. After a compile, JIT, or
  runtime failure, route through the repair guide; this guide's cards link to
  its entries but never restate them.

## Reading Order

1. Always read [fundamentals](references/categories/fundamentals.md). Its
   rules apply to every kernel and are not repeated in category cards.
2. Route to one category card through
   [category-index.md](references/category-index.md) — by operator category,
   or by the requested PyTorch API in its routing table.
3. Read the primary category card for the operator. If the operator genuinely
   spans two categories, read at most one secondary card.
4. Composition precedence: cross-cutting rules in `fundamentals` always
   apply; the primary card owns category-specific structure; a secondary card
   contributes only its scope and pitfalls.

## Reasoning Rules

- Treat cards as writing guidance, not a rule engine. Match the operator's
  actual semantics and shape regime before adopting a pattern.
- Skeleton code is a structural starting point; fill in the operator's real
  strides, masks, and dtypes.
- Do not read cards end-to-end when the index already narrows to one card.
