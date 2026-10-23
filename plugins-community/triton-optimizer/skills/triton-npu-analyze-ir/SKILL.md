---
name: triton-npu-analyze-ir
description: Use when an agent needs to capture, archive, or inspect Triton Ascend compiler IR for an operator workflow, especially to analyze dumped Triton or Bisheng IR stages, reason about likely performance issues from generated IR artifacts, or collect complete IR from a local or remote execution.
---

# Ascend Operator IR Analyzer

## Overview

Capture complete Triton Ascend compiler IR into a stable archive directory, then inspect the archived stages for likely performance problems. Use the bundled script first instead of re-explaining the capture mechanics in the conversation.

## Default Workflow

1. Run the bundled capture helper with an IR output parent, a generated benchmark harness, the operator file you want to inspect, and the benchmark case id.
   - `--case-id <id>` is required. The helper creates one exact archive below the parent using `YYYYMMDDTHHMMSSZ-<case-id>/`, then prints `IR archive: <path>` and `Capture manifest: <path>/capture-manifest.json`.
   - Before SIMT-only capture, resolve the active runtime Triton Ascend `compiler.py`; do not guess its site-packages path. Inspect the SIMT compile path for this diagnostic:
     ```python
     if opt.debug:
         print(f"[DEBUG] cmd_list: {' '.join(cmd_list)}")
     ```
     Keep the space in `' '.join(cmd_list)` so the capture helper can recover argument boundaries. The helper enables `TRITON_DEBUG=1`.
     - If the `[DEBUG] cmd_list:` diagnostic already exists, do not edit the file or add another print. Log `[helix][simt-mlir] cmd_list diagnostic already present; no edit: <path>`.
     - If the diagnostic is absent, make a recoverable backup, add the exact guarded print to the SIMT compile path, and validate the edited file with `python3 -m py_compile`. Log `[helix][simt-mlir] added cmd_list diagnostic: <path>` only after validation succeeds.
     - If the resolved file is outside the writable workspace, request permission before editing it. If permission is denied or the write fails, log `[helix][simt-mlir] cannot add cmd_list diagnostic: <path>: <reason>` followed by the exact manual snippet above, then stop capture. Do not silently try another compiler file or continue into the expected missing-marker failure.
   - Local:
     ```bash
     python3 ./scripts/capture_ir.py --ir-dir ir --bench-file bench_matmul.py --operator-file matmul.py --case-id <id>
     ```
   - Remote:
     ```bash
     python3 ./scripts/capture_ir.py --ir-dir ir --bench-file bench_matmul.py --operator-file matmul.py --case-id <id> --remote user@host:2222 --remote-workdir /tmp/helix
     ```

2. Inspect the resulting archive. Use the exact `IR archive:` path printed by capture, not the reusable `--ir-dir` parent:
   - Read `capture-manifest.json` to identify the captured kernel or variant you
     want to inspect.
   - Pass the selected inspection directory to `inspect_ir.py`; do not pass the
     reusable capture parent or archive root.
   - Start with `python3 ./scripts/inspect_ir.py list-stages --ir-dir <inspection-dir>`. If that is not enough, inspect the artifacts named by the manifest directly.

3. Inspect the IR directory with the bundled helper.
   - `list-stages`
     ```bash
     python3 ./scripts/inspect_ir.py list-stages --ir-dir <ir-dir> [--grep <pattern>] [--limit <N>] [--sort-by order|size|lines|interesting]
     ```
     Use this to enumerate stages, filter by pass name, or rank candidates before opening files. For a first pass over a large IR directory, start with:
     ```bash
     python3 ./scripts/inspect_ir.py list-stages --ir-dir <allocated-archive> --sort-by interesting --limit 20
     ```
   - `stage-summary`
     ```bash
     python3 ./scripts/inspect_ir.py stage-summary --ir-dir <ir-dir> --stage <stage-selector>
     ```
     Use this to get a compact summary for one stage, for example:
     ```bash
     python3 ./scripts/inspect_ir.py stage-summary --ir-dir <allocated-archive> --stage hivm-plan-memory
     ```
   - `diff-stages`
     ```bash
     python3 ./scripts/inspect_ir.py diff-stages --ir-dir <ir-dir> --from <stage-selector> --to <stage-selector> [--context <N>]
     ```
     Use this to compare two known stages and inspect keyword deltas plus unified diff output, for example:
     ```bash
     python3 ./scripts/inspect_ir.py diff-stages --ir-dir <allocated-archive> --from hivm-plan-memory --to hfusion-auto-vectorize-v2
     ```
   - `find-changes`
     ```bash
     python3 ./scripts/inspect_ir.py find-changes --ir-dir <ir-dir> [--limit <N>] [--sort-by score|lines|size]
     ```
     Use this to scan adjacent stage pairs and surface the biggest transitions first. A good default is:
     ```bash
     python3 ./scripts/inspect_ir.py find-changes --ir-dir <allocated-archive> --limit 20
     ```
   - `performance-signals`
     ```bash
     python3 ./scripts/inspect_ir.py performance-signals --ir-dir <ir-dir> [--limit <N>] [--format text|json]
     ```
      Its `Indirect-access stages` section lists which stages lower any access
      through `triton_indirect_load`/`triton_indirect_store`, with source line
      citations. This is navigation evidence only: it does not decide why the
      access became indirect. When an affine-looking index appears to degrade
      to an indirect load/store, trace the index provenance with `rg` and read
      `references/affine-access-degraded-to-indirect.md` for the evidence
      chain, confidence rules, and the genuine-gather non-match. Route a
      confirmed case to `mask-only-affine-addressing`.
   - `pipeline-structure`
     ```bash
     python3 ./scripts/inspect_ir.py pipeline-structure --ir-dir <allocated-archive> --kernel <mapped-kernel> --format json
     ```
     Use this for tile shape, loop depth, load/compute/store placement, launch
     grid, and Hivm handshake facts. Each fact is source-cited. A handshake is
     structural coordination, not timed overlap; keyword-only
     `performance-signals` remains navigation evidence.
     Use this when the first question is performance-oriented rather than purely navigational. It summarizes vector-heavy, transfer-heavy, and sync-heavy stages, plus suspicious stage transitions. For downstream round-analysis workflows, prefer:
     ```bash
     python3 ./scripts/inspect_ir.py performance-signals --ir-dir <allocated-archive> --format json
     ```
   - `stage-selector` may be a numeric-prefix stage id, a full stage name, or a unique substring. If the selector is ambiguous, the script fails explicitly instead of guessing.

4. Analyze likely performance issues directly from the archived IR.
   - Use `list-stages --sort-by interesting` to find passes worth reading first.
   - Use `find-changes` to identify which adjacent pass transition changed the IR the most.
   - Use `stage-summary` to see whether a stage adds buffers, vector ops, loads/stores, or sync-like operations.
   - Use `diff-stages` to identify which pass introduced a suspicious structural change.
   - Once the search space is small enough, inspect the raw `.mlir` files directly with terminal tools such as `rg`, `sed`, or `diff` to trace specific ops, symbols, attributes, or layout details.

5. If the user also needs hotspot evidence or operator timing attribution, use the `triton-npu-profile-operator` skill as a companion skill.
   - Use this pairing when IR suggests a likely bottleneck but you still need runtime evidence to confirm where time is spent.
   - Use this pairing when profiling already identified a hot operator and you want the IR archive to explain why that hotspot exists.

## Working Rules

- Prefer `python3 ./scripts/capture_ir.py --ir-dir ... --bench-file ... --operator-file ...` over ad hoc shell sequences so IR layout and replay flags stay consistent.
- Prefer `python3 ./scripts/inspect_ir.py ...` over manually opening large numbers of `.mlir` files when the first task is navigation, summary, or comparison.
- Prefer `performance-signals` before manual stage browsing when the immediate question is whether IR hints at vectorization loss, transfer-heavy lowering, or weak overlap.
- Treat `inspect_ir.py` as the first-pass navigator, not a replacement for direct text inspection. After it identifies the relevant stages, feel free to use `rg`, `sed`, `diff`, or similar terminal tools on the archived `.mlir` files.
- For remote capture, the helper stages the benchmark harness and operator file into the remote workspace before running the benchmark command there.
- Import-only benchmark harnesses are supported for IR capture; the benchmark file does not need its own executable CLI path.
- Keep each allocated IR archive immutable once captured unless the user explicitly asks to replace it. A same-second retry for the same case replaces only that archive child; it does not remove sibling archives or the output parent.
- Present analysis in terms of concrete artifacts and passes, not only intuition. Call out the relevant archive paths and stage names you inspected.
- Do not invent a fixed Ascend IR tuning methodology yet. Analyze the archived IR directly and be explicit when a conclusion is a hypothesis rather than a proven bottleneck.
- In optimize deep-analysis context, inspect both the attempted hypothesis and unrelated additional source-level opportunities. Report evidence-backed hypotheses to round performance analysis; do not edit the operator or bypass the normal optimize lifecycle.
- `capture-manifest.json` records the selected case's harness-exposed resolved
  shape/dtype and launch metadata. Do not add manual dimensions to the normal
  inspection command. Historical or incomplete manifests must yield a formula
  and an evidence gap, not a guessed shape.
