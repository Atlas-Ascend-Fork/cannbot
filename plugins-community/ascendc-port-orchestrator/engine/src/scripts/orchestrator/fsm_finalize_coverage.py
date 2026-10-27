# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

"""UNVERIFIED escape hatch — multirank card-shortage coverage gap (fsm slice).

Split out of fsm_phase_finalize (which is at the architecture-lint BIG_FILE
bar): the coverage-pause + coverage-accept logic for a declared world_size
group the probe could not allocate cards for.

Wiring note: this module currently has NO core call sites —
`fsm_phase_finalize` keeps its current in-file O5 dispatch and
does NOT import this module yet. The intended wiring is: the O5 VERIFIED
arm delegates to `handle_o5_verified` (R2 marker
stamp for multirank + the coverage pause), and the RUNNER_FAILED arm may adopt
`_handle_o5_runner_failed` for the infra-vs-algorithm split. The standalone
consumers already exist: the multirank extension plugin's
finalize_perf_capture calls `coverage_accept_satisfied`, and
`multirank_o5_reconcile.try_skip_remeasure` calls it too.
"""

from __future__ import annotations

from typing import Optional

import events
import finalize_pipeline
import state_executor
from logging_config import get_logger

from fsm_context import HandlerResult, OrchestratorContext

log = get_logger(__name__)

# Infra-class O5 RUNNER_FAILED retry bound (kept in sync with
# fsm_phase_finalize._O5_INFRA_MAX_RETRIES — the runner-failed handler here
# only sees a verdict AFTER the in-place retry loop there already re-ran the
# real post_verify this many times).
_O5_INFRA_MAX_RETRIES = 2


def coverage_accept_satisfied(workspace, unverified: dict) -> bool:
    """Every currently-unverified world_size is already in the

    `.coverage_accept.json` marker (stamped by a prior ACCEPT-UNVERIFIED
    user_decision.md). Subset check — a NEW unverified ws (not in the
    marker) still pauses.
    """
    if not unverified:
        return True
    marker = workspace / ".coverage_accept.json"
    if not marker.is_file():
        return False
    try:
        import json as _json

        accepted = set(
            _json.loads(marker.read_text()).get("accepted_world_sizes") or []
        )
    except Exception:
        return False
    return set(unverified) <= accepted


def handle_o5_verified(ctx, lane, o5, truth_source) -> Optional[HandlerResult]:
    """VERIFIED arm of the O5 dispatch: record the harness state, stamp the

    R2 durable marker (multirank — a later resume can then skip the re-measure),
    then the UNVERIFIED-coverage pause.
    """
    workspace = ctx.workspace
    log.info(f"O5 post-verify: {o5.summary}")
    import phase_o5

    phase_o5.record_harness_state(workspace, o5)
    if truth_source == "multirank":
        from plugins.multirank import multirank_o5_reconcile

        multirank_o5_reconcile.stamp_verified_marker(workspace, o5)
    return pause_on_unverified_coverage(ctx, lane, o5)


def pause_on_unverified_coverage(ctx, lane, o5) -> Optional[HandlerResult]:
    """Precision is fully verified for the world_sizes that RAN, but the probe

    could not allocate cards for others. Pause with the coverage list so the
    user decides (free cards + re-measure, or ACCEPT-UNVERIFIED to ship the
    degraded campaign) — unless every gap is already accept-stamped. Returns a
    continue-HandlerResult on pause, else None (full coverage / fully accepted
    → finalize proceeds).
    """
    if not getattr(o5, "unverified_world_sizes", None):
        return None
    workspace = ctx.workspace
    if coverage_accept_satisfied(workspace, o5.unverified_world_sizes):
        return None
    _det_parts = []
    for k, v in sorted(o5.unverified_world_sizes.items(), key=lambda kv: int(kv[0])):
        _det_parts.append(f"ws={k}: {v.get('detail', '')}")
    _det = "; ".join(_det_parts)
    _pause = "await_user_decision"
    log.info(
        "O5 VERIFIED but world_size coverage is partial — pausing for "
        f"user decision (unverified: {_det})"
    )
    events.emit(
        workspace,
        "orchestrator.phase_o5_coverage_pause",
        lane=lane,
        data={"unverified": o5.unverified_world_sizes, "pause_target": _pause},
    )
    state_executor.record_transition(
        workspace,
        state_executor.TransitionDecision(
            next_state=_pause,
            matched_transition_index=-1,
            rationale=(
                f"O5 VERIFIED (precision) with UNVERIFIED world_sizes "
                f"(card shortage): {_det}. Paused: free cards and "
                f"re-invoke to re-measure, or ACCEPT-UNVERIFIED to "
                f"ship the degraded campaign."
            ),
            from_state="finalize",
            handoff="",
        ),
    )
    finalize_pipeline.record_rollback(
        workspace,
        rollback_state=_pause,
        reason=f"O5 coverage pause (UNVERIFIED world_sizes): {_det}",
        gate="phase_o5_coverage",
    )
    return HandlerResult.cont()


def _rb_note(rollback_kind: str) -> str:
    """NODE-5 re-entry budget note for a rollback kind."""
    if rollback_kind == "infra":
        return "infra re-entry FREE (does not consume iter)"
    return "algorithm re-entry counts"


def _runner_failed_infra_pause(workspace, lane, o5) -> HandlerResult:
    """Infra-class failure that survived the bounded retry: the worker cannot
    fix it (it is not a kernel problem). Pause for human action instead of
    spawning a pointless worker."""
    log.info(
        "P0aba.O5 gate: infra-class RUNNER_FAILED after retry bound — "
        "routing await_user_decision (NOT await_worker: a worker cannot "
        "fix an external resource failure; spawning one wastes a budget)"
    )
    events.emit(
        workspace,
        "orchestrator.phase_o5_runner_failed",
        lane=lane,
        data={
            "summary": o5.summary,
            "rollback_kind": "infra",
            "pause_target": "await_user_decision",
        },
    )
    _pause_state = "await_user_decision"
    state_executor.record_transition(
        workspace,
        state_executor.TransitionDecision(
            next_state=_pause_state,
            matched_transition_index=-1,
            rationale=(
                f"P0aba.O5 RUNNER_FAILED (infra, retries exhausted): "
                f"{o5.summary[:200]}. External resource failure (lane "
                f"allocation / ssh / env) — the worker cannot fix it. "
                f"Paused for human action: resolve the resource (e.g. "
                f"wait for cards to free up), then re-invoke the "
                f"orchestrator to resume from finalize."
            ),
            from_state="finalize",
            handoff="",
        ),
    )
    finalize_pipeline.record_rollback(
        workspace,
        rollback_state=_pause_state,
        reason=f"P0aba.O5 RUNNER_FAILED (infra): {o5.summary[:200]}",
        gate="phase_o5_runner_failed",
    )
    return HandlerResult.cont()  # main loop sees await_user_decision -> pause


def _runner_failed_at_cap_exit(workspace, lane, snap, o5) -> HandlerResult:
    """P0bb-loop-guard (2026-05-23): same exhaustion check as MISMATCH branch —
    if worker is iter_cap-exhausted, routing back loops forever. Exit cleanly
    with diagnostic."""
    counter_name = "worker"
    count = snap.iter_counts.get(counter_name, 0)
    cap = state_executor.iter_cap("await_worker", workspace=workspace)
    log.critical(
        f"O5 RUNNER_FAILED while await_worker "
        f"already at iter_cap ({count}/{cap}). Cannot progress — "
        f"routing back would infinite-loop. Fix the runner "
        f"discoverability (run_pass_b.py / pass_a_runner.py name) "
        f"manually OR mark precision.pass_b N/A explicitly, then resume."
    )
    events.emit(
        workspace,
        "orchestrator.fsm_loop_guard_o5_runner_failed",
        lane=lane,
        data={
            "worker_count": count,
            "worker_cap": cap,
            "summary": o5.summary[:200],
        },
    )
    return HandlerResult.ret(2)


def _runner_failed_rollback(workspace, o5) -> HandlerResult:
    """O5 RUNNER_FAILED rollback: re-iterate emission via the worker.

    NODE-5 (2026-05-28): rollback_kind propagates from O5Report.
    `phase_o5_runner` auto-classifies the runner_error against
    `_INFRA_ERROR_PATTERNS` (substring catalog: SCP / oversized
    / JSON parse fail / env issue / etc.). When kind=="infra",
    the recorded jsonl entry carries rollback_kind="infra" and
    `iter_counts_from_log` skips it from iter_below_cap
    accounting — re-entry is free because the kernel didn't
    change. When kind=="algorithm" (default for unclassified
    errors per conservative bias), the re-entry consumes
    budget normally."""
    _rollback_state = "await_worker"
    log.info(f"O5 RUNNER_FAILED rollback target: {_rollback_state}")
    _rb_kind = o5.rollback_kind  # may be None (mismatch path);
    state_executor.record_transition(
        workspace,
        state_executor.TransitionDecision(
            next_state=_rollback_state,
            matched_transition_index=-1,
            rationale=(
                f"P0aba.O5 RUNNER_FAILED: {o5.summary[:200]}. "
                f"Rollback to {_rollback_state}. Worker must "
                "produce a canonical pass_b verifier filename at "
                "workspace root, OR set verification.json precision."
                "pass_b to {status: 'N/A', reason: '<...>'} explicitly."
                + (
                    f" [NODE-5: rollback_kind={_rb_kind!r} — {_rb_note(_rb_kind)}]"
                    if _rb_kind
                    else ""
                )
            ),
            from_state="finalize",
            handoff="",
            rollback_kind=_rb_kind,
        ),
    )
    # P0aay-ext (2026-05-13): record rollback for O5 runner
    # failures too — same completeness fix as MISMATCH path.
    finalize_pipeline.record_rollback(
        workspace,
        rollback_state=_rollback_state,
        reason=f"P0aba.O5 RUNNER_FAILED: {o5.summary[:200]}",
        gate="phase_o5_runner_failed",
    )
    return HandlerResult.cont()  # main loop picks up at the rollback target


def _handle_o5_runner_failed(ctx: OrchestratorContext, snap, o5) -> HandlerResult:
    """P0aba.O5 RUNNER_FAILED handling: loop-guard exit-2 if the worker is
    iter_cap-exhausted, else rollback to await_worker (NODE-5 rollback_kind
    propagated) + `continue`.

    DEBT-O5-INFRA-0-MISCLASSIFY (2026-07-20): by the time control reaches here,
    the INFRA-RETRY loop in `_o5_post_verify` has ALREADY re-attempted an
    infra-class RUNNER_FAILED (stale NPU_PYTHON_BIN &c.) `_O5_INFRA_MAX_RETRIES`
    times in place.

    Infra-class split: an infra failure that survived the retry
    bound is an EXTERNAL resource problem (lane auto-allocation / ssh / scp /
    env) the worker CANNOT fix — rolling back to await_worker would spawn a
    worker with nothing to do (it edits kernels, not hardware occupancy). Such
    failures route to await_user_decision (pause) so the operator can resolve
    the resource (e.g. wait for cards to free up) and re-invoke. Algorithm-class
    RUNNER_FAILED (verifier discoverability / run_pass_b filename / pass_b N/A —
    things the worker CAN fix) reaches here directly (no retry) and still rolls
    back to await_worker exactly as before.

    Note: fsm_phase_finalize keeps its own (simpler)
    `_handle_o5_runner_failed` until the O5 wiring adopts this split; this
    function is drop-in so that adoption is a call-site change only."""
    workspace = ctx.workspace
    lane = ctx.lane

    # P0aba.O5 (2026-05-07, codex finding #3): legacy fail-open
    # path silently allowed finalize when O5 runner errored
    # (ssh / env / verifier script missing). That trusts kw's
    # self-claim with no orchestrator-side independent proof —
    # the same bug shape this session is fixing across the gate.
    # Block by routing to await_worker with a precise reason so
    # the next worker spawn can fix the runner-discoverable gap
    # (e.g., write run_pass_b.py to the canonical filename, or
    # mark verification.json pass_b N/A with explicit reason).
    log.info(f"O5 post-verify: RUNNER_FAILED — {o5.summary}")

    # Infra-class failure that survived the bounded retry: the worker cannot
    # fix it (it is not a kernel problem). Pause for human action instead of
    # spawning a pointless worker.
    if getattr(o5, "rollback_kind", None) == "infra":
        return _runner_failed_infra_pause(workspace, lane, o5)

    log.info("P0aba.O5 gate: routing await_worker for runner reconciliation")
    events.emit(
        workspace,
        "orchestrator.phase_o5_runner_failed",
        lane=lane,
        data={"summary": o5.summary},
    )
    if state_executor.at_iter_cap(workspace, "await_worker"):
        return _runner_failed_at_cap_exit(workspace, lane, snap, o5)
    return _runner_failed_rollback(workspace, o5)
