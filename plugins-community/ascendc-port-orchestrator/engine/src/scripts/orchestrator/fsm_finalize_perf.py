# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License).
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

"""Finalize-phase independent perf capture (module split from fsm_phase_finalize).

The pre-eligibility re-measure: capture when the plugin permits it, relabel
worker self-reports when it does not, and route away on an independently
measured below-threshold ratio (FSM G6) or a plugin-reported resource
shortage.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

import events
import finalize_pipeline
import phase_o5
import phase_o5_perf_capture
import perf_irm_provenance
import state_executor
from fsm_context import HandlerResult, OrchestratorContext

log = logging.getLogger(__name__)

_PERF_STATUS_PAUSE_RESOURCE = "PAUSE_RESOURCE"


class _PerfCapturePause(Exception):
    """Internal control-flow — a plugin capture asked for a resource pause.

    Carries the plugin-supplied reason; `_run_perf_capture` translates it
    into the await_user_decision pause HandlerResult. Raised BEFORE any
    performance fragment is merged or written, so verification.json keeps
    its pre-capture content on the pause path.
    """

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _perf_capture_plugin(workspace: Path):
    """Return the active plugin and whether it permits independent capture."""
    plugin = getattr(finalize_pipeline, "_get_active_plugin")(workspace)
    should_capture = plugin is not None and plugin.should_run_phase_o5_perf_capture()
    return plugin, should_capture


def _capture_perf_if_requested(
    ctx: OrchestratorContext,
    plugin,
    should_capture: bool,
    verification_path: Path,
    verification: dict,
) -> bool:
    """Capture, merge, and stamp performance when capture is requested."""
    existing_perf = verification.get("performance", {}) or {}
    override = os.environ.get("AOG_PERF_CAPTURE_OVERRIDE_WORKER", "").strip()
    requested = should_capture and (
        existing_perf.get("ratio") in (None, 0, 0.0)
        or override in ("1", "true", "TRUE", "yes")
    )
    if not requested:
        return False
    perf_result = phase_o5_perf_capture.measure_op_perf(
        ctx.op,
        ctx.workspace,
        plugin=plugin,
    )
    if perf_result.get("status") == _PERF_STATUS_PAUSE_RESOURCE:
        # Resource-shortage sentinel: the plugin's capture could not run for
        # an external reason (e.g. occupied measurement cards). Do NOT merge
        # or write any performance fragment — hand the pause up so finalize
        # halts for the user instead of bouncing a worker that cannot free
        # the resource.
        raise _PerfCapturePause(str(perf_result.get("reason") or ""))
    merged_perf = perf_irm_provenance.merge_perf_preserving_irm(
        existing_perf, perf_result
    )
    merged_perf["independent_re_measure"] = (
        perf_irm_provenance.orchestrator_irm_from_perf_result(
            perf_result,
            worker_ratio=existing_perf.get("ratio"),
        )
    )
    verification["performance"] = merged_perf
    if existing_perf.get("ratio"):
        verification["performance"]["worker_authored_aux"] = existing_perf
    verification_path.write_text(json.dumps(verification, indent=2))
    events.emit(
        ctx.workspace,
        "orchestrator.phase_o5_perf_capture",
        lane=ctx.lane,
        data={
            "status": perf_result.get("status"),
            "ratio": perf_result.get("ratio"),
            "plugin": getattr(plugin, "name", "unknown"),
        },
    )
    log.info(
        f"phase_o5_perf_capture: status={perf_result.get('status')} "
        f"ratio={perf_result.get('ratio')}"
    )
    return True


def _relabel_worker_authored_perf(
    plugin,
    should_capture: bool,
    verification_path: Path,
    verification: dict,
    existing_perf: dict,
) -> None:
    """Make a non-orchestrator performance report explicitly self-reported."""
    existing_irm = existing_perf.get("independent_re_measure")
    if not existing_perf or perf_irm_provenance.is_orchestrator_measured(existing_irm):
        return
    capture_reason = (
        "did not run: worker self-reported a ratio"
        if should_capture
        else f"disabled for plugin {getattr(plugin, 'name', 'unknown')!r}"
    )
    existing_perf["independent_re_measure"] = perf_irm_provenance.worker_authored_irm(
        existing_irm,
        reason=(
            "no orchestrator-side perf re-measure ran for this op "
            f"(phase_o5_perf_capture {capture_reason}). The recorded "
            "performance.ratio is a WORKER SELF-REPORT, not an independent "
            "measure. Force an orchestrator capture with "
            "AOG_PERF_CAPTURE_OVERRIDE_WORKER=1."
        ),
    )
    verification["performance"] = existing_perf
    verification_path.write_text(json.dumps(verification, indent=2))


def _pause_for_resource(ctx: OrchestratorContext, reason: str) -> HandlerResult:
    """Pause finalize on a plugin-reported resource shortage (status ==
    PAUSE_RESOURCE) so the operator can free the resource / accept a degraded
    campaign. Records a finalize→await_user_decision transition; the main
    loop's pause path then halts for the user (user_decision.md). Routes the
    pause at the USER, not at a worker respawn — a worker cannot free the
    occupied external resource, so await_worker would only burn an iteration
    on a problem it cannot solve. Mirrors the DEBT-192 loop-break pause
    pattern (`_record_nonconvergent_loop`)."""
    workspace = ctx.workspace
    pause_state = "await_user_decision"
    log.info(
        f"phase_o5_perf_capture: plugin-reported resource shortage — pausing "
        f"for user (NOT awaiting a worker; a worker cannot free the resource): "
        f"{reason[:200]}"
    )
    events.emit(
        workspace,
        "orchestrator.phase_o5_perf_capture_pause",
        lane=ctx.lane,
        data={"reason": reason[:300], "pause_target": pause_state},
    )
    state_executor.record_transition(
        workspace,
        state_executor.TransitionDecision(
            next_state=pause_state,
            matched_transition_index=-1,
            rationale=(
                f"perf capture hit a resource shortage: {reason[:200]}. "
                f"Paused for human action: free the resource and re-invoke to "
                f"re-measure, or accept the degraded campaign (record the "
                f"decision in user_decision.md)."
            ),
            from_state="finalize",
            handoff="",
            rollback_kind="infra",
        ),
    )
    finalize_pipeline.record_rollback(
        workspace,
        rollback_state=pause_state,
        reason=f"perf capture resource shortage (infra): {reason[:200]}",
        gate="phase_o5_perf_capture",
    )
    return HandlerResult.cont()


def _run_perf_capture(ctx: OrchestratorContext) -> Optional[HandlerResult]:
    """Independent performance re-measure before eligibility, routed.

    Beyond the historical best-effort capture, an INDEPENDENTLY measured
    ratio below the effective threshold routes the op back to
    await_optimizer — the low-perf → optimizer escalation previously lived
    only on the await_worker exit transitions and never fired when the perf
    data only materialized here (moe_fused_a8w8: perf never measured on the
    final kernel, performance: N/A shipped silently).

    Returns a HandlerResult ONLY when routing away (below-threshold
    escalate, or the plugin-reported resource-shortage pause); None on every
    other path — capture failures stay best-effort as before. The escalation
    fires only when the capture actually RAN this iteration (an independent
    measurement confirmed the number); worker self-reported perf keeps its
    await_worker-exit semantics unchanged.
    """
    # NPUKernelBench has a fixed runner-owned W3/R5 profiler contract.  Do
    # not overwrite it with the historical port performance capture, which
    # assumes a different reference callable and methodology. Only an
    # EXPLICIT npubench resolution skips — an unresolvable provider (e.g. a
    # multirank workspace whose plugin owns the capture) must NOT silently
    # skip the measurement.
    try:
        if phase_o5.expected_truth_source(ctx.workspace) == "npubench":
            return None
    except Exception as error:
        log.warning("could not resolve provider before perf capture: %s", error)

    try:
        plugin, should_capture = _perf_capture_plugin(ctx.workspace)
        verification_path = ctx.workspace / "verification.json"
        if not verification_path.exists():
            return None
        verification = json.loads(verification_path.read_text())
        existing_perf = verification.get("performance", {}) or {}
        captured = _capture_perf_if_requested(
            ctx,
            plugin,
            should_capture,
            verification_path,
            verification,
        )
        if not captured:
            _relabel_worker_authored_perf(
                plugin,
                should_capture,
                verification_path,
                verification,
                existing_perf,
            )
            return None
        perf = verification.get("performance", {}) or {}
        ratio = perf.get("ratio")
        if isinstance(ratio, (int, float)) and ratio > 0:
            threshold = _effective_perf_threshold(verification)
            if ratio < threshold:
                return _escalate_perf_below_threshold(ctx, ratio, threshold)
    except _PerfCapturePause as pause:
        return _pause_for_resource(ctx, pause.reason)
    except Exception as error:
        log.warning(
            f"phase_o5_perf_capture failed ({type(error).__name__}: {error}); "
            "worker-authored perf kept as-is"
        )
    return None


def _effective_perf_threshold(verification: dict) -> float:
    """The same threshold the FSM's verification_perf_below_threshold
    primitive resolves (performance.threshold, else the parity default)."""
    perf = (verification or {}).get("performance", {}) or {}
    try:
        return float(perf.get("threshold", 1.0))
    except (TypeError, ValueError):
        return 1.0


def _escalate_perf_below_threshold(
    ctx: OrchestratorContext,
    ratio: float,
    threshold: float,
) -> HandlerResult:
    """Route finalize → await_optimizer on an independently measured
    below-threshold ratio (mirrors the O5-mismatch rollback recording)."""
    rollback_state = "await_optimizer"
    log.info(
        f"phase_o5_perf_capture: independently measured ratio {ratio} < "
        f"threshold {threshold} — escalating to {rollback_state}"
    )
    events.emit(
        ctx.workspace,
        "orchestrator.phase_o5_perf_below_threshold",
        lane=ctx.lane,
        data={"ratio": ratio, "threshold": threshold, "goto": rollback_state},
    )
    state_executor.record_transition(
        ctx.workspace,
        state_executor.TransitionDecision(
            next_state=rollback_state,
            matched_transition_index=-1,
            rationale=(
                f"independently measured perf ratio {ratio} < threshold "
                f"{threshold} at finalize — escalate to {rollback_state} "
                f"(FSM G6: perf must be re-optimized before shipping)"
            ),
            from_state="finalize",
            handoff="",
        ),
    )
    finalize_pipeline.record_rollback(
        ctx.workspace,
        rollback_state=rollback_state,
        reason=(
            f"phase_o5_perf_capture: measured ratio {ratio} below threshold {threshold}"
        ),
        gate="phase_o5_perf_below_threshold",
    )
    return HandlerResult.cont()
