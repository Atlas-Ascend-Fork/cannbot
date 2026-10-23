---
name: triton-npu-optimize-state
description: Manage temporary optimize workflow state in an Ascend NPU optimize workspace, including baseline acceptance, round start, same-round strategy-state updates, and round submission. Use when the optimize workflow needs to accept a baseline, start or update a round, or submit a round.
---

# Optimize State

Use this skill to manage optimize workflow state through one structured CLI entrypoint:

```bash
python3 scripts/cli.py submit-baseline --baseline-dir baseline
python3 scripts/cli.py start-round --round-dir opt-round-1 --round-strategy exploration --analysis-policy pattern_entry --reason "..."
python3 scripts/cli.py claim-edit --target opt-round-1/opt_kernel.py --source pattern --pattern-path .cannbot/dependencies/triton-optimizer/cannbot-knowledge/knowledge/ops/triton/optimizations/patterns/<pattern>.md --reason "..."
python3 scripts/cli.py submit-deep-analysis --round-dir opt-round-1 --profile-manifest opt-round-1/profile/PROF_*/helix-profile-manifest.json --ir-manifest opt-round-1/ir/<archive>/capture-manifest.json --symptom <symptom-id> [--symptom <symptom-id> ...]
python3 scripts/cli.py set-current-round-state --round-strategy focused_tuning --analysis-policy ir_required --reason "..."
python3 scripts/cli.py submit-round --round-dir opt-round-2 --current-round 2 --final-round 4
```

## When To Use

- Use `submit-baseline` when `baseline/` needs to be accepted before any optimize round may begin or continue.
- Use `start-round` immediately before beginning work on a new `opt-round-N/`; it initializes the active round's workflow-owned strategy state.
- If `start-round` returns `deep_analysis_required`, do not edit. First collect profile and IR artifacts for one explicit shared case ID, then use `submit-deep-analysis` to validate both manifests and open the active round.
- When automatic deep optimization follows a measured plateau, the first deep round must start as `plateau_review`. After deep analysis, reassess the complete selected optimization scope and applicable structural patterns before using `set-current-round-state` to record the next direction; the operator remains read-only during the review.
- Use `claim-edit` only when the edit hook denies an operator edit for a missing claim; never call it proactively. Choose `--source pattern` to declare the staged pattern that guided the edit, or `--source self-directed` when no pattern file was used. See `### claim-edit` for the exact forms.
- Use `set-current-round-state` when the active round's strategy or required evidence depth changes mid-round.
- Use `submit-round` after one round is complete and before the workflow may continue or stop.

## Subcommands

### `submit-baseline`

- Validates canonical baseline artifacts and `baseline/state.json`.
- Prints JSON only; read the `guideline` field for the pass/fix instruction.
- Treat returned `issues` as the baseline repair checklist.
- Baseline preparation still belongs to `triton-npu-prepare-optimize-baseline`.

### `start-round`

- Enforces the runner-managed `.helix/state.json` workflow gate before a round begins.
- Requires `--round-strategy`, `--analysis-policy`, and `--reason`.
- Writes the active round's latest strategy state into `.helix/state.json`.
- Appends a structured `State Update` block to `opt-round-N/attempts.md`.
- Prints JSON only; read the `guideline` field and keep the returned `hard_rules` in force for the active round.
- Use this to bridge temporary runner-managed workflow state with the durable `opt-round-N/` you are about to work in.

#### `--round-strategy` Allowed Values

- `exploration`: narrow the next promising optimization direction before making a larger commitment.
- `structural_change`: pursue a larger rewrite in shape, layout, dataflow, or algorithm structure.
- `focused_tuning`: refine a direction that is already validated instead of searching broadly again.
- `stabilization`: repair correctness, compile stability, or fragile performance before further tuning.
- `plateau_review`: reassess the complete selected optimization scope after a local plateau. This is a read-only strategy: inspect the target gap, plausible savings, full kernel/operator structure, and applicable structural patterns before recording the next edit direction.

#### `--analysis-policy` Allowed Values

- `pattern_entry`: begin from code structure and pattern triage; deeper evidence is optional before the main edit.
- `profile_required`: require profiler evidence before the main edit.
- `ir_required`: require IR-backed attribution before the main edit.
- `compiler_source_required`: require compiler-source evidence because profiler and IR evidence have already narrowed the question to a compiler-side issue.

#### `--reason`

- Always pass a short explicit reason that explains why this round is entering the chosen strategy and evidence depth.
- This text is stored in workflow state and mirrored into the round's structured `State Update` block in `attempts.md`.

#### Common `start-round` Examples

- First exploratory round from code structure and pattern triage:
  ```bash
  python3 scripts/cli.py start-round \
    --round-dir opt-round-1 \
    --round-strategy exploration \
    --analysis-policy pattern_entry \
    --reason "Start from pattern triage to narrow the first promising direction."
  ```

- Profiler-backed structural rewrite:
  ```bash
  python3 scripts/cli.py start-round \
    --round-dir opt-round-2 \
    --round-strategy structural_change \
    --analysis-policy profile_required \
    --reason "Profiler evidence points to a bottleneck that likely needs a larger structural rewrite."
  ```

- Validated direction with deeper IR-backed tuning:
  ```bash
  python3 scripts/cli.py start-round \
    --round-dir opt-round-3 \
    --round-strategy focused_tuning \
    --analysis-policy ir_required \
    --reason "The direction is already validated, but IR attribution is still needed before the next tuning edit."
  ```

### `set-current-round-state`

- Updates the current active round's workflow-owned strategy state without selecting a round by path.
- Locates the nearest ancestor optimize workspace from the current working directory, so it can be run from the workspace root or from inside `opt-round-N/` subdirectories.
- Requires `--reason` plus at least one of `--round-strategy` or `--analysis-policy`.
- Rejects no-op updates and same-round `analysis_policy` rollbacks.
- A round in `plateau_review` may remain there while evidence depth increases, but it may leave only for `structural_change` or `focused_tuning`. The reason must state the evidence-backed direction; operator edits remain blocked until this transition is recorded.
- Appends a structured `State Update` block to the active round's `attempts.md`.
- Prints JSON only; read the `guideline` field and apply any returned `warnings`.

Use the same enum values listed above for `--round-strategy` and `--analysis-policy`.

### `claim-edit`

Call `claim-edit` only when the edit hook denies an operator edit for a
missing claim; never call it proactively. After a denial, run one of these
two forms, then retry the edit:

```bash
python3 scripts/cli.py claim-edit --target opt-round-1/opt_kernel.py \
  --source pattern \
  --pattern-path .cannbot/dependencies/triton-optimizer/cannbot-knowledge/knowledge/ops/triton/optimizations/patterns/<pattern>.md \
  --pattern-path .cannbot/dependencies/triton-optimizer/cannbot-knowledge/knowledge/ops/triton/optimizations/patterns/<pattern2>.md \
  --reason "..."
python3 scripts/cli.py claim-edit --target opt-round-1/opt_kernel.py \
  --source self-directed \
  --reason "..."
```

- `--source pattern` requires at least one `--pattern-path` naming a concrete
  cannbot-knowledge pattern card (`*/cannbot-knowledge/knowledge/ops/<language>/optimizations/patterns/<name>.md`
  or `.../operator_optimization/<name>.md`); repeat
  `--pattern-path` to declare every pattern that guided the edit. `--source
  self-directed` takes no pattern arguments. `--reason`
  is always required.
- The hook blocks operator edits that have no active claim. Run `claim-edit`
  only in response to that denial, then retry the edit.

### `submit-deep-analysis`

- Use this only after `start-round` returns `deep_analysis_required`; it is the sole transition from `deep_analysis` to an editable active round.
- Requires `--round-dir`, `--profile-manifest`, and `--ir-manifest`. It does not accept a case ID or a phase override.
- Requires at least one `--symptom` from the knowledge skill's symptom vocabulary, with at most five IDs (list them with `python3 <retrieval-skill>/scripts/retrieve_patterns.py list` and inspect one with `info <id>`, using the `triton-npu-retrieve-patterns` skill). Use `--symptom unknown` alone when the evidence does not match the current list. When the knowledge skill ships no symptom contract, `--symptom unknown` is the only accepted value and pattern recommendations stay empty.
- The profile manifest must be inside `opt-round-N/profile/`; the IR manifest must be inside one allocated archive below `opt-round-N/ir/`.
- Both manifests must use the same explicit case ID, the unchanged round-candidate SHA-256, and the canonical benchmark SHA-256. The command rejects a mismatch without advancing state.
- Run the normal profile command with `--case-id <id>`. Run `capture_ir.py --ir-dir opt-round-N/ir --case-id <id> ...`, then pass the printed archive child's `capture-manifest.json` path here.
- On success, the command opens `round_active`. A normal deep round may then follow its recorded strategy. A `plateau_review` round must first complete the full-scope review and use `set-current-round-state` to record `structural_change` or evidence-backed `focused_tuning`; the edit hook keeps the operator read-only until then.
- The accepted symptom list is stored in the round's deep-analysis state. If `HELIX_OPTIMIZE_RECOMMEND_PATTERNS` is enabled with a true value (`1`, `true`, `yes`, or `on`), the result also includes up to three matching patterns with their summary and full `use_when` conditions. Returned patterns are recorded in workflow state and are not recommended again during resume of the same optimize workspace. The default is disabled.

#### Common `set-current-round-state` Examples

- Raise only the required evidence depth after profiling becomes necessary:
  ```bash
  python3 scripts/cli.py set-current-round-state \
    --analysis-policy profile_required \
    --reason "Pattern triage is no longer sufficient; profiler evidence is now required before the next code change."
  ```

- Pivot the round into a larger structural rewrite:
  ```bash
  python3 scripts/cli.py set-current-round-state \
    --round-strategy structural_change \
    --reason "The current evidence points to a larger dataflow or layout rewrite instead of another narrow tuning pass."
  ```

- Switch into stabilization when the direction still looks good but the implementation is fragile:
  ```bash
  python3 scripts/cli.py set-current-round-state \
    --round-strategy stabilization \
    --analysis-policy ir_required \
    --reason "The direction still looks promising, but correctness and performance are unstable and need repair before further tuning."
  ```

### `submit-round`

- Validates one completed `opt-round-N/` directory against the baseline contract and round-state contract.
- Prints JSON only; read the `guideline` field for the pass/fix instruction, and read `next_option` when it is present.
- In optimize worker-batch flows, always pass both `--current-round` and `--final-round` so submission is evaluated relative to the current invocation's owned round range.
- When the session has a speedup target, the optimize runner injects `HELIX_OPTIMIZE_MIN_SPEEDUP` automatically and `submit-round` uses that value as the authority.
- Do not use a bare `submit-round --round-dir opt-round-N` call as the primary optimize worker pattern; that shorter form is reserved for manual checks outside the standard optimize worker-batch flow.

## State Ownership

- Treat the structured `State Update` blocks in `opt-round-N/attempts.md` as the script-written history mirror for those state changes.
- If a `State Update` block cannot be mirrored into `attempts.md`, the workflow state still remains authoritative and the command may return a warning about the missing mirror write.
- Do not create a second manual state-history ledger in `summary.md`.
