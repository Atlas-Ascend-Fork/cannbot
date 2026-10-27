# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------
"""verification.json emission for the multirank runner (extracted from multirank_runner
to keep it under the architecture-lint BIG_FILE bar, and so the O5
coverage-aware reconcile can write the same artifact shape).

Performance schema:

  verification.json.performance = {
    ...aggregate_perf fragment at the TOP level (ran / ratio / median_ratio /
    case_stats / candidate_us / baseline_us / rows / method /
    unverified_cases) — the same fragment MultiRankPlugin.finalize_perf_capture
    returns and fsm_phase_finalize._capture_perf_if_requested merges via
    perf_irm_provenance.merge_perf_preserving_irm,
    "status": PASS | PASS_WITHIN_TOLERANCE | BELOW_THRESHOLD | N/A,
    "independent_re_measure": {
      measured   -> {ran: true, ratio, median_ratio, rows, method, source}
      unmeasured -> {ran: false, status: "N/A", reason, na_kind?, source}
    },
  }

The `source` stamp MUST start with an orchestrator prefix ("phase_o5 …" —
perf_irm_provenance.ORCHESTRATOR_SOURCE_PREFIXES): multirank_runner IS the
orchestrator-side launcher, so (a) the irm gate
(finalize_checks_provenance._validate_independent_perf_source) accepts the
ran=true claim, and (b) fsm_phase_finalize._relabel_worker_authored_perf
does not relabel this orchestrator measurement as worker-authored. No
trusted-receipt fields (trusted_receipt / execution_report) are written
here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .multirank_rank_verdicts import rank_verdict_entry as _rank_verdict_entry

# Orchestrator-side measurement stamps (prefix-matched by
# perf_irm_provenance.is_orchestrator_source — both start with "phase_o5").
_IRM_SOURCE_MEASURED = (
    "phase_o5 multirank_runner: orchestrator launched the harness-tree "
    "multirank_verify.py multi-NPU per-case A/B campaign in its own launcher — "
    "independent of the worker's verification.json self-report"
)
_IRM_SOURCE_ATTEMPTED = (
    "phase_o5 multirank_runner: orchestrator ran the multi-NPU perf campaign but "
    "no ratio was produced (perf_baseline absent or measurement failed)"
)

# Parity band — mirrors phase_o5_perf_capture._build_result and the plugin's
# ko_escalation_threshold default: PASS at/above parity (1.0),
# PASS_WITHIN_TOLERANCE down to the escalation threshold, BELOW_THRESHOLD
# under it.
_PERF_TOLERANCE_THRESHOLD = 0.9

# Honest N/A vocabulary (plugins/base.py finalize_perf_capture contract):
# the campaign RAN but the spec declares no usable baseline — unmeasurable
# by design, distinct from MEASUREMENT_FAILED (the plugin's runner_error
# branch owns that one).
_NA_UNMEASURABLE = "UNMEASURABLE_BY_DESIGN"


@dataclass
class VerificationPayload:
    """verification.json content fields.

    Construct with one keyword per line — VerificationPayload(overall=...,
    pass_a=..., ...); the three required fields have no default so a
    missing one fails at construction, not at emit time.
    """

    overall: dict
    pass_a: dict
    rank_summaries: list
    determinism: "dict | None" = None
    multirank_block: "dict | None" = None
    perf: "dict | None" = None
    perf_only: bool = False


def emit_verification_json(
    workspace: Path,
    payload: VerificationPayload,
) -> None:
    """Write verification.json aggregating the multi-rank multirank verdict.

    finalize gates (the plugin's multirank_rank_verdicts consistency gate,
    _check_universal_entrypoints, _check_post_worker_audit) require this file
    at workspace root. Data is fully derived from aggregate_all_ranks + the
    assembled pass_a; the two N/A literals (pass_b, performance) carry
    explicit reasons because the gates reject silent None as reward-hacking.
    Read-merge-write preserves any worker-authored keys (e.g. build_evidence).

    The determinism dict (computed by the caller) MUST be persisted — the
    FSM transition condition `verification_det_policy_satisfied` reads
    vj["determinism"].policy_satisfied and fail-closes on a missing field,
    so omitting it spuriously reroutes await_worker → await_det_analyzer on
    every multirank op.

    perf_only=True (a --perf campaign) updates ONLY the performance block:
    precision / multirank / determinism are never rewritten — perf-mode rank
    summaries are vacuously PASS (they measure speed, not correctness), so
    stamping them over the precision artifacts would erase an honest FAIL
    roll (rank + failed_cases) written by the precision campaign or by the
    worker's claimed artifact.
    """
    vp = workspace / "verification.json"
    try:
        vj = json.loads(vp.read_text()) if vp.is_file() else {}
    except Exception:
        vj = {}
    if not payload.perf_only:
        # Read-merge at BOTH levels (carried-forward): the fresh measurement
        # keys overwrite (a re-run refreshes the measured numbers), but keys
        # the worker maintains on the existing artifact (e.g. pass_a.tier2_pass
        # or precision evidence notes) survive the rewrite. A wholesale block
        # replacement erased them on every O5 re-measure.
        old_prec = vj.get("precision") if isinstance(vj.get("precision"), dict) else {}
        old_pass_a = (
            old_prec.get("pass_a") if isinstance(old_prec.get("pass_a"), dict) else {}
        )
        new_prec = {
            "status": payload.overall["status"],
            "pass_a": {**old_pass_a, **payload.pass_a},
            "pass_b": {
                "status": "N/A",
                "reason": (
                    "multirank: pass_b subsumed by multi-rank multirank_verify "
                    "(ALL-rank-PASS is the dispatch test)"
                ),
            },
        }
        vj["precision"] = {**old_prec, **new_prec}
    vj["performance"] = _performance_block(payload.perf, payload.perf_only)
    if not payload.perf_only:
        # The multirank rank-verdict block is a PRECISION artifact (see docstring).
        # truth_tier stamps WHICH golden provider produced the compared truth
        # (npubench / a3_live) so finalize + reports can
        # distinguish "precision+perf both trustworthy" from "precision-only".
        from . import read_truth_tier

        _tier = read_truth_tier(workspace)
        if payload.multirank_block is not None:
            vj["multirank"] = {**payload.multirank_block, "truth_tier": _tier}
        else:
            vj["multirank"] = {
                "world_sizes": [payload.overall["world_size"]],
                "rank_verdicts": {
                    str(payload.overall["world_size"]): [
                        _rank_verdict_entry(rs) for rs in payload.rank_summaries
                    ]
                },
                "truth_tier": _tier,
            }
    if payload.determinism is not None and not payload.perf_only:
        vj["determinism"] = payload.determinism
    vp.write_text(json.dumps(vj, indent=2))


def _performance_block(perf: dict | None, perf_only: bool) -> dict:
    """Build the target-schema performance fragment (see module docstring)."""
    if perf is not None and perf.get("ratio") is not None:
        ratio = perf["ratio"]
        if ratio >= 1.0:
            perf_status = "PASS"
        elif ratio >= _PERF_TOLERANCE_THRESHOLD:
            perf_status = "PASS_WITHIN_TOLERANCE"
        else:
            perf_status = "BELOW_THRESHOLD"
        # Top level holds the measured fragment from aggregate_perf output —
        # the same fields the plugin's finalize_perf_capture returns or merges here.
        block = dict(perf)
        block["status"] = perf_status
        block["independent_re_measure"] = {
            "ran": True,
            "ratio": ratio,
            "median_ratio": perf.get("median_ratio", ratio),
            "rows": perf.get("rows"),
            "method": perf.get("method"),
            "source": _IRM_SOURCE_MEASURED,
        }
        return block
    if perf_only:
        reason = (
            "multirank: perf mode ran but no ratio (perf_baseline "
            "absent or measurement failed)"
        )
        na_kind = _NA_UNMEASURABLE
    else:
        reason = (
            "multirank: perf via multirank_runner multi-NPU path; "
            "perf_baseline in the spec drives the ratio (omit -> N/A)"
        )
        na_kind = None
    block: dict = {"status": "N/A", "reason": reason}
    if na_kind is not None:
        block["na_kind"] = na_kind
    block["independent_re_measure"] = {
        "ran": False,
        "status": "N/A",
        "reason": reason,
        "source": _IRM_SOURCE_ATTEMPTED,
    }
    return block
