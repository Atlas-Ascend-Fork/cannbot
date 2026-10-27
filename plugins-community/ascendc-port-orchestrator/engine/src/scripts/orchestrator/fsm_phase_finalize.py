# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------
"""fsm_phase_finalize.py — the `finalize` FSM state handler (DEBT-201 split).

Extracted VERBATIM from run_single_op's `if snap.current_state == "finalize":`
branch (orchestrator.py) as part of the god-function decomposition via
dependency inversion. The slice is entered once per loop iteration when the FSM
is at the `finalize` state; it runs:

  Phase O5 independent post-verify (precision re-measure) + rollback routing
  → phase_o5_perf_capture (independent perf re-measure)
  → pre-finalize audit-artifact production + GE op_host assembler + schema_norm
  → batch precheck + P0ff eligibility gate + DEBT-192 loop-break
  → finalize_pipeline.finalize_op (archive promotion)
  → P0aax KB-manager merge gate → finalize→done routing.

DEPENDENCY CONTRACT (why the monkeypatch surface still bites):
- Orchestrator-MODULE-LEVEL deps (_ensure_audit_artifacts) are reached via
  `ctx.<name>` (read-through property resolving the live orchestrator module),
  so `monkeypatch.setattr(orchestrator, X)` bites. Per-run inputs
  (op/workspace/lane/extra_lanes/runtime_kwargs) come off `ctx`.
- SIBLING modules (phase_o5, phase_o5_runner, phase_o5_perf_capture,
  finalize_pipeline, schema_norm, kb_invoke, events, state_executor,
  fsm_finalize_coverage, multirank_runner)
  are imported directly here — the SAME module objects the tests patch, so
  `monkeypatch.setattr(<sibling>, ...)` bites the direct reference with no
  indirection.

The block BODY is byte-identical to the original; the only mechanical edits are:
`op`→`ctx.op`, `workspace`→`ctx.workspace`, `lane`→`ctx.lane`,
`extra_lanes`→`ctx.extra_lanes`, `runtime_kwargs`→`ctx.runtime_kwargs`,
`_ensure_audit_artifacts`→`ctx._ensure_audit_artifacts`, and each `continue` /
`return N` → `return HandlerResult.cont()` / `.ret(N)`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import events
import finalize_pipeline
import kb_invoke
import state_executor
import phase_o5_perf_capture  # noqa: F401 — re-exported for test patch sites
from logging_config import get_logger

from fsm_context import HandlerResult, OrchestratorContext

# The O5 verification flow lives in fsm_finalize_o5_flow (module-size
# discipline); re-exported so existing import/patch sites keep working.
from fsm_finalize_o5_flow import (  # noqa: F401
    _DEVICE_ERROR_CODE_RE,
    _DEVICE_ERROR_MARKERS,
    _DEVICE_RECLASSIFY_PREFIX,
    _HOST_COPY_FAULT_ESCALATION_FILE,
    _HOST_COPY_FAULT_MARKERS,
    _HOST_COPY_FAULT_MAX_TRANSIENT,
    _HOST_COPY_FAULT_MAX_TRANSIENT_ENV,
    _HOST_TRANSIENT_RECLASSIFY_PREFIX,
    _NEAR_MISS_BLOCKED_FINGERPRINT_CLASSES,
    _O5_CANDIDATE_GUARD_INTERVAL_ENV,
    _O5_CANDIDATE_GUARD_INTERVAL_SECONDS,
    _O5_CANDIDATE_GUARD_MAX_RETRIES,
    _O5_CANDIDATE_GUARD_MAX_RETRIES_ENV,
    _O5_INFRA_MAX_RETRIES,
    _O5_INFRA_RETRY_BACKOFF_ENV,
    _O5_INFRA_RETRY_BACKOFF_SECONDS,
    _PRECISION_REPORT_REL,
    _REPAIR_RECORD_FILENAME,
    _REPAIR_RESET_WINDOW_SECONDS,
    _WORKER_FIXABLE_CANDIDATE_REJECTION_MARKERS,
    _assemble_finalize_ge_ophost,
    _await_o5_candidate_stable,
    _bump_host_copy_fault_escalation,
    _candidate_case_failure_signature,
    _candidate_case_signature,
    _candidate_failing_case_indices,
    _candidate_precision_cases,
    _candidate_precision_signal_observable,
    _candidate_stability_guard_failure,
    _candidate_tier1_pass_count,
    _candidate_tree_changed,
    _candidate_tree_from_report,
    _clear_harness_build_artifacts,
    _delivery_cpp_roots,
    _dispatch_o5_non_blocking,
    _dispatch_o5_runner_failed,
    _format_batch_precheck_failures,
    _handle_npubench_candidate_failure,
    _handle_o5_mismatch,
    _handle_o5_runner_failed,
    _host_copy_fault_max_transient,
    _is_delivery_cpp_source,
    _is_direct_npubench_candidate_failure,
    _is_generated_or_backup_dir,
    _is_repairable_npubench_candidate_failure,
    _is_worker_fixable_candidate_rejection,
    _load_ascendc_static_checker,
    _log_perf_na_recommendation,
    _mark_host_copy_fault_deterministic,
    _maybe_zero_progress_park,
    _mismatch_at_worker_cap,
    _mismatch_is_device_error,
    _mismatch_is_host_transient,
    _multirank_o5_runner,
    _near_miss_inadmissible_cases,
    _nonconvergent_loop_result,
    _normalize_finalize_workspace,
    _npubench_candidate_failure_at_worker_cap,
    _o5_candidate_guard_interval_seconds,
    _o5_candidate_guard_max_retries,
    _o5_candidate_stability_probe,
    _o5_candidate_tree_key,
    _o5_failure_signature_input,
    _o5_infra_retry_backoff_seconds,
    _o5_post_verify,
    _o5_runner_for_workspace,
    _prepare_finalize_audit,
    _record_finalize_rollback,
    _record_nonconvergent_loop,
    _record_o5_provisional,
    _repair_reset_age_seconds,
    _repeat_fingerprint_classes,
    _resolve_o5_report,
    _retry_device_error_mismatch,
    _retry_host_transient_mismatch,
    _retry_infra_o5_verification,
    _rollback_npubench_candidate_failure,
    _rollback_o5_mismatch,
    _rollback_o5_runner_failure,
    _rollback_rationale,
    _route_await_user_decision_park,
    _run_batch_finalize_precheck,
    _run_delivery_static_check,
    _run_finalize_prep,
    _run_o5_verification,
    _runner_failure_at_worker_cap,
    _same_signature_park_route,
    _skip_remeasure_if_marked,
    _sleep,
    _stop_direct_npubench_candidate_failure,
    _worker_cap_stats,
    near_miss_case_admitted,
)

# Independent perf capture lives in fsm_finalize_perf (module-size
# discipline); re-exported so existing import/patch sites keep working.
from fsm_finalize_perf import (  # noqa: F401
    _PERF_STATUS_PAUSE_RESOURCE,
    _PerfCapturePause,
    _perf_capture_plugin,
    _capture_perf_if_requested,
    _relabel_worker_authored_perf,
    _pause_for_resource,
    _run_perf_capture,
    _effective_perf_threshold,
    _escalate_perf_below_threshold,
)

log = get_logger(__name__)


# DEBT-O5-INFRA-0-MISCLASSIFY (2026-07-20): an infra-class O5 RUNNER_FAILED
# (e.g. a stale/missing NPU_PYTHON_BIN → exit-127 `<bin>/python3: No such file
# or directory`) means the RUNNER broke, not the kernel — the artifact is
# intact. Rolling back to await_worker + respawning the base worker is
# pointless (nothing to re-emit) and burns a real author iteration, so instead
# we RE-ATTEMPT the O5 re-measure in place, BOUNDED by this cap so a genuinely
# stuck infra issue still falls through to the await_worker rollback (fail
# loud, never silent). The bound is an in-call loop count — it CANNOT loop
# forever within a finalize iteration; cross-iteration progress stays guarded
# by the existing await_worker iter_cap loop-guard. The O5 gate is NOT
# skipped: each re-attempt runs the full, real post_verify_for_finalize.

# Host-level transient windows (2026-08-22 A5 campaign: 507035 copy faults +
# wedged npu-smi + msprof stalls that come and go every ~15-30 min) make an
# immediate O5 re-attempt land in the SAME bad window.  Back off between
# infra retries so the second attempt has a real chance to catch a clean
# window.  Env-overridable; tests patch _sleep.


# --- Host copy-fault escalation guard (2026-08-27, 42_CoTAttention) -----------
# torch_npu launches ops ASYNCHRONOUSLY: a candidate device-kernel hard fault
# (e.g. aivec error 340 "VEC to access UB is not aligned" wedging the device,
# surfaced as 507035/507015 device error type 3) only reports at the NEXT host
# op — frequently an H2D/D2H copy — so the measured precision `reason` carries
# the copy-fault markers below even when the candidate's own kernel caused it.
# On 2026-08-27 the 42_CoTAttention candidate reproduced such a fault
# DETERMINISTICALLY on a healthy device (per-launch aclrtSynchronizeStream
# bisect: cot_softmax_f32), while the transient classification looped 10+
# identical O5 failures and explicitly told the worker "INFRA, do not edit the
# candidate" — the exact opposite of the needed repair.
# Guard: persist a per-candidate-binding counter; once the same binding trips
# the copy-fault classification more than the cap, stop re-attempting as infra
# and let the MISMATCH roll back to await_worker with a deterministic-fault
# debugging note.


# Plugin-owned perf capture (BasePlugin.finalize_perf_capture) may report that
# the measurement could not run for an external resource reason the worker
# cannot fix (status == "PAUSE_RESOURCE" + reason in the returned dict). That
# is not a perf verdict and must never reach verification.json — it asks the
# finalize FSM to pause at await_user_decision instead.


def handle_finalize(ctx: OrchestratorContext, snap) -> HandlerResult:
    """Run the `finalize` state slice for one loop iteration.

    Thin orchestrator over the finalize sub-phases (each <200 lines per the
    architecture-lint god-function bar). Returns a HandlerResult telling the
    driver loop to `continue` (re-snapshot) or `return <exit_code>`.
    Any sub-phase may short-circuit by returning a HandlerResult; a None means
    "proceed to the next sub-phase".
    """
    # Phase O5 independent post-verify + rollback routing.
    _r = _o5_post_verify(ctx, snap)
    if _r is not None:
        return _r
    # Independent perf re-measure (best-effort; short-circuits ONLY when the
    # plugin-owned capture reports a resource shortage → pause for the user).
    _r = _run_perf_capture(ctx)
    if _r is not None:
        return _r
    # Pre-finalize artifact production (audit + GE op_host + schema_norm) and
    # batch precheck; returns the aggregated multi-failure reason (or None).
    precheck_all_reasons = _run_finalize_prep(ctx)
    # P0ff eligibility gate + DEBT-192 loop-break rollback routing.
    _r = _check_eligibility_and_rollback(ctx, snap, precheck_all_reasons)
    if _r is not None:
        return _r
    # Archive promotion + P0aax KB-merge gate + finalize→done routing.
    return _promote_and_route(ctx)


# ---------------------------------------------------------------------------
# Near-miss fingerprint admission (DSH ruling §4.c layer 3, 2026-08-28)
# ---------------------------------------------------------------------------
# npubench_runner's precision report carries a per-case `repeat_fingerprint`
# (class ∈ deterministic-fail / bimodal / stable-pass / reference-unstable).
# A case whose verdict flips across repeats (bimodal) or whose reference is
# itself unstable on device (reference-unstable) must NEVER be accepted via
# the near-miss rule — the evidence needed to judge "ULP-level near miss" is
# not trustworthy for those cases.  Legacy reports without the field keep the
# existing behavior (admission undecided here, no blocking).


# Device-class errors split OUT of the host-transient text classification
# (DSH ruling P0-1 §4.b, 2026-08-28): 5070xx device errors / aivec errcodes
# are not transient host windows.  They do not self-heal (2026-08-27 3FA:
# 507015 wedged device 3 for 95 minutes while the engine slept 4x600s), so
# the retry backoff is 0 and the same-signature parking threshold is 2
# (state_executor.DEVICE_SIGNATURE_PARK_THRESHOLD) instead of 3.

# Summary prefix used when a device-class MISMATCH is rolled into the infra
# retry loop; lets the settled report be classified back as device-class even
# after the measured payload is out of scope.


# ---------------------------------------------------------------------------
# P0-2 repair-reset race guard (2026-08-28, PR875 equiv review)
# ---------------------------------------------------------------------------
# Before an O5 evaluation, the candidate must be stable: entry file present as
# a regular non-symlink file, tree digest not changing under our feet, and no
# candidate-repair reset archived within the last 60s.  A violation used to
# surface as a bogus infra ERROR evaluation (the 14:52 "model_new_ascendc.py
# must be a regular non-symlink file" round); now it suspends with bounded
# retries and only then fails loud as an infra runner failure.


# ---------------------------------------------------------------------------
# P0-1 same-signature failure parking (DSH ruling §4.b, 2026-08-28)
# ---------------------------------------------------------------------------


# Host-level H2D copy faults (2026-08-22 A5 campaign): the measured
# precision report fails inside torch_npu's copy path, not in the candidate
# kernel.  A MISMATCH verdict carrying one of these markers must re-attempt
# in place as infra — the worker cannot repair the host (2026-08-23 CoT).
# WARNING (2026-08-27, 42_CoTAttention): these markers are NOT proof of a
# host fault.  torch_npu launches asynchronously, so a candidate device-kernel
# hard fault (507035/507015, e.g. aivec error 340) surfaces at the NEXT host
# op — often an H2D copy — making the reason byte-identical to a genuine
# transient host window.  The escalation guard in `_resolve_o5_report` bounds
# how many times the same candidate binding may hide behind this
# classification before it is treated as a deterministic candidate fault.


_DIGEST_SCHEME_DRIFT_MARKER = "candidate digest scheme drift"
_SNAPSHOT_MISSING_MARKER = "immutable candidate snapshot is missing"


def _eligibility_is_harness_refreezable(eligibility: dict) -> bool:
    """Digest-scheme drift / missing frozen snapshot are harness-state issues.

    Both mean the O5 evidence was produced under a different harness state
    (older exclusion list, or the snapshot was cleared by an operator
    recovery).  The worker cannot repair either — the harness can, by
    re-freezing the snapshot with the current code and re-running O5 (audit
    H1, Option B).
    """
    reason = str(eligibility.get("reason") or "")
    return _DIGEST_SCHEME_DRIFT_MARKER in reason or _SNAPSHOT_MISSING_MARKER in reason


def _self_heal_digest_scheme_drift(
    ctx: OrchestratorContext,
    snap,
) -> bool:
    """Clear stale evaluation artifacts and re-run O5 in place, once.

    Removes only the derived snapshot/exec trees (kernel/build stays for
    receipt reuse); the re-run freezes a fresh snapshot under the current
    digest scheme and rebinds the evidence reports.
    """
    from pathlib import Path as _Path

    workspace = _Path(ctx.workspace)
    cleared = []
    for rel in (".npubench_candidate", ".npubench_exec"):
        target = workspace / rel
        if target.is_symlink() or target.is_file():
            try:
                target.unlink()
                cleared.append(rel)
            except OSError:
                pass
        elif target.is_dir():
            import shutil as _shutil

            try:
                _shutil.rmtree(target)
                cleared.append(rel)
            except OSError:
                pass
    if cleared:
        log.info(
            "digest-scheme self-heal: cleared %s; re-running O5 with current "
            "exclusion list (bounded, no worker respawn)",
            ", ".join(cleared),
        )
    runner = _o5_runner_for_workspace(ctx.workspace, extra_lanes=ctx.extra_lanes)
    o5 = _run_o5_verification(ctx, runner)
    return o5.verdict in ("VERIFIED", "PROVISIONAL")


def _check_eligibility_and_rollback(
    ctx: OrchestratorContext,
    snap,
    precheck_all_reasons: Optional[str],
) -> Optional[HandlerResult]:
    """Gate finalization and route ineligible work to its existing rollback."""
    eligibility = finalize_pipeline.check_finalize_eligibility(ctx.workspace)
    if eligibility["eligible"]:
        return None
    if _eligibility_is_harness_refreezable(
        eligibility
    ) and _self_heal_digest_scheme_drift(ctx, snap):
        # The re-run froze a fresh snapshot + evidence under the current
        # scheme.  Re-run artifact prep and the authoritative gate once more;
        # on failure fall through to the normal rollback path.
        precheck_all_reasons = _run_finalize_prep(ctx)
        eligibility = finalize_pipeline.check_finalize_eligibility(ctx.workspace)
        if eligibility["eligible"]:
            return None
    gate_tag = eligibility.get("gate") or "finalize_eligibility"
    finalize_pipeline.record_rollback(
        ctx.workspace,
        rollback_state=eligibility["rollback_state"],
        reason=eligibility["reason"],
        gate=gate_tag,
    )
    loop_result = _nonconvergent_loop_result(
        ctx.workspace,
        ctx.lane,
        eligibility,
        gate_tag,
    )
    if loop_result is not None:
        return loop_result
    return _record_finalize_rollback(
        ctx.workspace,
        ctx.lane,
        eligibility,
        precheck_all_reasons,
    )


def _static_failure_reason(static_report: dict) -> str:
    """Summarize failing scoped static-check reports without changing the gate."""
    summaries = [
        f"{Path(item.get('root', '')).name}: {item.get('report', {}).get('summary', 'failed')}"
        for item in static_report.get("reports", [])
        if not item.get("report", {}).get("passed")
    ]
    return static_report.get("error") or "; ".join(summaries) or "unknown failure"


# 2026-08-30 (PR13 WP-A / A.4.2): finalize hard-fails must land on an FSM
# transition, never on a bare HandlerResult.ret(7) — a bare exit leaves no
# transition, so resume re-ran the same failing promotion with no recovery
# path.  Delivery-contract violations the worker can repair (unrecognized
# delivery files) route to await_worker with the filenames and repair
# guidance; harness-side gates (static safety) and KB-merge failures route to
# await_user_decision.
_DELIVERY_WORKER_FIXABLE_MARKERS = (
    "unrecognized file",
    "unrecognized hidden artifact",
)


def _finalize_hard_fail_transition(
    workspace: Path, *, target: str, rationale: str
) -> HandlerResult:
    """Record a finalize -> target FSM transition for a hard-fail, then continue.

    Returning ``HandlerResult.cont()`` after recording the transition mirrors
    the same-signature park route: the main loop re-reads the state and
    dispatches await_worker / parks at await_user_decision instead of the
    process dying on a bare exit code.
    """
    log.error(rationale)
    state_executor.record_transition(
        workspace,
        state_executor.TransitionDecision(
            next_state=target,
            matched_transition_index=-1,
            rationale=rationale,
            from_state="finalize",
            handoff="",
        ),
    )
    return HandlerResult.cont()


def _check_delivery_static_safety(workspace: Path, lane) -> Optional[HandlerResult]:
    """Run the scoped static safety gate before promotion and knowledge merge."""
    static_report = _run_delivery_static_check(workspace)
    if not static_report.get("passed"):
        reason = _static_failure_reason(static_report)
        log.error(
            "finalize static safety GATE failed; blocking promotion and KB merge: %s",
            reason,
        )
        events.emit(
            workspace,
            "orchestrator.finalize_static_check_failed",
            lane=lane,
            data={"reason": reason[:500]},
        )
        return _finalize_hard_fail_transition(
            workspace,
            target="await_user_decision",
            rationale=(
                "finalize static safety GATE failed; promotion and KB merge "
                f"blocked. Reason: {reason[:500]} — this is a harness-side "
                "safety net the worker cannot repair; routing to "
                "await_user_decision (write user_decision.md to adjudicate) "
                "instead of a bare exit 7."
            ),
        )
    if static_report.get("skipped"):
        log.info("finalize static safety GATE: skipped (%s)", static_report["skipped"])
    else:
        log.info(
            "finalize static safety GATE: PASS (%d delivery root(s))",
            len(static_report.get("reports", [])),
        )
    return None


def _log_finalize_promotion(finalize_report) -> None:
    """Log the existing archive-promotion outcome."""
    if finalize_report.skipped:
        log.info(f"finalize: skipped ({finalize_report.skip_reason})")
        return
    log.info(
        f"finalize: promoted {len(finalize_report.files_promoted)} files + "
        f"{len(finalize_report.dirs_promoted)} dirs → {finalize_report.archive_dir}"
    )
    for error in finalize_report.errors:
        log.info(f"finalize WARN: {error}")


def _finalize_kb_merge_error_route(
    workspace: Path, lane, error: Exception
) -> HandlerResult:
    """Park a raised KB-merge failure at await_user_decision."""
    log.info(
        f"finalize KB merge ERROR: {error}; blocking transition to done — "
        "staying at finalize"
    )
    events.emit(
        workspace,
        "orchestrator.finalize_kb_merge_error",
        lane=lane,
        data={"error": str(error)[:500]},
    )
    return _finalize_hard_fail_transition(
        workspace,
        target="await_user_decision",
        rationale=(
            f"finalize KB merge raised {type(error).__name__}: "
            f"{str(error)[:500]} — KB-manager processing is harness-side; "
            "routing to await_user_decision (inspect .kb_merge_log.jsonl, "
            "then write user_decision.md) instead of a bare exit 7."
        ),
    )


def _finalize_kb_merge_failed_route(
    workspace: Path, lane, result: dict
) -> HandlerResult:
    """Park an unsuccessful KB-merge result at await_user_decision."""
    log.info(
        "finalize KB merge FAILED (exit_code=%s); blocking transition to done "
        "— staying at finalize. Inspect .kb_merge_log.jsonl + retry orchestrator.",
        result.get("log_entry", {}).get("exit_code"),
    )
    events.emit(
        workspace, "orchestrator.finalize_kb_merge_failed", lane=lane, data=result
    )
    return _finalize_hard_fail_transition(
        workspace,
        target="await_user_decision",
        rationale=(
            "finalize KB merge FAILED (exit_code=%s); blocking transition "
            "to done. KB-manager processing is harness-side; routing to "
            "await_user_decision (inspect .kb_merge_log.jsonl, then write "
            "user_decision.md) instead of a bare exit 7."
            % result.get("log_entry", {}).get("exit_code")
        ),
    )


def _merge_finalize_knowledge(workspace: Path, lane) -> Optional[HandlerResult]:
    """Require successful KB-manager processing for a substantive update."""
    knowledge_update = workspace / "knowledge_update.md"
    if not knowledge_update.exists() or knowledge_update.stat().st_size < 100:
        return None
    if getattr(kb_invoke, "_prepare_existing_marker")(workspace):
        log.info(
            "finalize: knowledge_update.md already merged (.kb_merged marker present)"
        )
        return None
    log.info(
        "finalize KB merge GATE: invoking aog-knowledge-maintain "
        "(knowledge_update.md = %s bytes)...",
        knowledge_update.stat().st_size,
    )
    try:
        result = kb_invoke.merge_one(workspace)
    except Exception as error:
        return _finalize_kb_merge_error_route(workspace, lane, error)
    if not result.get("success"):
        return _finalize_kb_merge_failed_route(workspace, lane, result)
    log.info("finalize KB merge OK — proceeding to done")
    events.emit(
        workspace,
        "orchestrator.finalize_kb_merge_ok",
        lane=lane,
        data={"workspace": str(workspace)},
    )
    return None


def _unrecognized_delivery_files(worker_fixable: list[str]) -> list[str]:
    """Pull the offending delivery paths out of worker-fixable promote errors."""
    _pm_len = len("promote ")
    return [
        text.split(":", 1)[0][_pm_len:]
        if text.startswith("promote ") and ":" in text
        else text[:200]
        for text in worker_fixable
    ]


def _finalize_worker_fixable_route(
    workspace: Path, worker_fixable: list[str]
) -> HandlerResult:
    """Hand unrecognized delivery files back to the worker for repair.

    Every blocking error is an unrecognized delivery file — the worker can
    repair it (delete the file or move it out of the delivery territory), so
    route back to await_worker with the filenames and the repair guidance
    instead of a bare exit 7.
    """
    files = _unrecognized_delivery_files(worker_fixable)
    return _finalize_hard_fail_transition(
        workspace,
        target="await_worker",
        rationale=(
            "finalize promotion blocked on %d unrecognized delivery "
            "file(s): %s. Repair guidance for the next worker round: "
            "delete each listed file from the workspace, or move it "
            "outside the delivery territory (kernel/, op_host/) when "
            "it is still needed at runtime, then hand off as usual — "
            "the delivery contract only ships recognized source files."
            % (len(worker_fixable), ", ".join(files))
        ),
    )


def _finalize_promotion_blocked_route(
    workspace: Path, texts: list[str]
) -> HandlerResult:
    """Park promotion errors the worker cannot repair at await_user_decision."""
    return _finalize_hard_fail_transition(
        workspace,
        target="await_user_decision",
        rationale=(
            "finalize promotion reported %d blocking error(s) the worker "
            "cannot be expected to repair alone: %s — routing to "
            "await_user_decision (write user_decision.md to adjudicate) "
            "instead of a bare exit 7."
            % (
                len(texts),
                "; ".join(text[:300] for text in texts[:3]),
            )
        ),
    )


def _finalize_promotion_error_route(
    workspace: Path,
    lane,
    finalize_report,
    blocking_errors: list,
) -> HandlerResult:
    """Report blocking promotion errors and pick the matching repair route."""
    log.error(
        "finalize promotion reported %d error(s); refusing transition to done",
        len(finalize_report.errors),
    )
    events.emit(
        workspace,
        "orchestrator.finalize_promotion_failed",
        lane=lane,
        data={"errors": [str(error)[:500] for error in finalize_report.errors]},
    )
    texts = [str(error) for error in blocking_errors]
    worker_fixable = [
        text
        for text in texts
        if any(marker in text for marker in _DELIVERY_WORKER_FIXABLE_MARKERS)
    ]
    if len(worker_fixable) == len(texts):
        return _finalize_worker_fixable_route(workspace, worker_fixable)
    return _finalize_promotion_blocked_route(workspace, texts)


def _advance_finalize_state_to_done(
    workspace: Path,
    runtime_kwargs: dict,
) -> Optional[HandlerResult]:
    """Drive the state machine to done; return a result only when it errors."""
    try:
        decision = state_executor.next_state(
            workspace,
            "→ orchestrator: pipeline_done",
            dry_run=False,
            runtime_kwargs=runtime_kwargs,
        )
        log.info(
            f"route: {decision.from_state} → {decision.next_state} "
            f"({decision.rationale})"
        )
    except state_executor.StateMachineError as error:
        log.info(f"finalize→done routing error: {error}")
        return HandlerResult.ret(5)
    return None


def _route_finalize_to_done(
    workspace: Path,
    lane,
    runtime_kwargs: dict,
    finalize_report,
) -> HandlerResult:
    """Advance the FSM after successful promotion and knowledge processing."""
    # DEBT-100 git-add auto-stage is explicitly non-blocking (its WARN stays
    # in the report for audit) — a gitignore'd output/ tree makes git return
    # rc=1 and that must not block the done transition (2026-08-23 BAM: the
    # promotion itself archived 22 files successfully, then this single
    # non-blocking entry refused the transition).
    blocking_errors = [
        error
        for error in finalize_report.errors
        if "git-add auto-stage (non-blocking" not in str(error)
    ]
    if blocking_errors:
        return _finalize_promotion_error_route(
            workspace,
            lane,
            finalize_report,
            blocking_errors,
        )
    routing_result = _advance_finalize_state_to_done(workspace, runtime_kwargs)
    if routing_result is not None:
        return routing_result
    events.emit(
        workspace,
        "orchestrator.finalize_pipeline",
        lane=lane,
        data={
            "skipped": finalize_report.skipped,
            "files_promoted": len(finalize_report.files_promoted),
            "dirs_promoted": len(finalize_report.dirs_promoted),
            "errors": len(finalize_report.errors),
        },
    )
    return HandlerResult.cont()


def _promote_and_route(ctx: OrchestratorContext) -> HandlerResult:
    """Promote eligible output, process knowledge, then move the FSM to done."""
    static_result = _check_delivery_static_safety(ctx.workspace, ctx.lane)
    if static_result is not None:
        return static_result
    # Destination-aware archive namespace: pass the RUN's resolved
    # archive_project (briefs target-aware map — a3_to_a5_port stays for a5,
    # a3_to_310p_port for 310p) so finalize routes
    # the op into the destination's own output project instead of the plugin's
    # static a5-destination default. Never read the global env file here: the
    # run context is the authority (a stale global TARGET must not re-route a
    # finalize). Resolution failure falls back to the plugin default.
    try:
        _env = ctx.resolve_env()
    except Exception:
        _env = None
    _archive_project = getattr(_env, "archive_project", None) if _env else None
    finalize_report = finalize_pipeline.finalize_op(
        ctx.op, ctx.workspace, archive_project=_archive_project
    )
    _log_finalize_promotion(finalize_report)
    if finalize_report.errors:
        return _route_finalize_to_done(
            ctx.workspace,
            ctx.lane,
            ctx.runtime_kwargs,
            finalize_report,
        )
    merge_result = _merge_finalize_knowledge(ctx.workspace, ctx.lane)
    if merge_result is not None:
        return merge_result
    return _route_finalize_to_done(
        ctx.workspace,
        ctx.lane,
        ctx.runtime_kwargs,
        finalize_report,
    )
