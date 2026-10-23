---
name: triton-npu-retrieve-patterns
description: Deterministic offline retrieval of candidate optimization patterns for submitted symptom IDs, mapped through the language knowledge skill's symptom contract. Use when routing observed Ascend NPU performance symptoms to candidate optimization patterns. Advisory only.
---

# Retrieve Patterns (Symptom)

## Purpose

Map submitted symptom IDs to candidate optimization pattern cards using the
language knowledge skill's symptom contract. Deterministic and offline.

## Usage

Run from the operator workspace root:

    python3 <skill-dir>/scripts/retrieve_patterns.py <subcommand> ...

Subcommands:

- `list`: every symptom ID with its one-line summary, plus the reserved
  `unknown` note.
- `info <id>`: one full symptom entry (summary, evidence hint, non-matches,
  candidate patterns).
- `patterns <id>`: the candidate pattern cards for one symptom (card path,
  summary, use-when conditions).
- `retrieve`: map submitted symptom IDs to pattern recommendations.

The `retrieve` options:

- `--symptom <id>` (required, repeatable): symptom IDs submitted for the round.
  The reserved `unknown` must be passed alone and returns no recommendations.

Examples (single and multiple symptoms):

    python3 <skill-dir>/scripts/retrieve_patterns.py retrieve --symptom tile-footprint-too-large
    python3 <skill-dir>/scripts/retrieve_patterns.py retrieve --symptom tile-footprint-too-large --symptom exact-tile-boundary-mask
