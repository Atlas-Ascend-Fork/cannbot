#!/usr/bin/env python3
# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

"""multirank_precision_eval_two_tier.py — NATIVE two-tier verdict for multirank (multirank).

multirank (compute-communication fusion) canonical precision judge — the analog of
precision_eval_port_a3_two_tier.py. Delegates the per-case T1 math to the SAME
canonical judge `precision_eval_two_tier.classify_output`, so the tier semantics
are identical to benchmark / port_a3 mode (single source of truth for the math).

Key difference from port_a3 / benchmark: the multirank truth is the per-case
golden/ tree collected by the truth-tier collector (npubench task reference /
a3_live source-side capture) — there is no vendor aclnn
fusion op to be "at least as good as". T2 is therefore COMPETITOR-DECLARED:
when the spec declares an optional `t2_competitor` callable (a composed stock
CANN path — design §4.1 "the user MAY supply composed stock CANN ops as the
T2 baseline"), the verifier runs it per case and this module computes the
REAL T2 arm:
  - T1 = ours matches cpu_truth within per-dtype thresholds (vendored compare.py).
  - T2 = parity-or-better vs the declared competitor (ours_MERE ≤ comp_MERE AND
    ours_MARE ≤ comp_MARE — the canonical judge's route="commercial" fallback,
    identical semantics to benchmark mode's vs-CANN arm).
When the spec declares NO competitor, T2 stays N/A_ALL_T1 for every case and
never masquerades as a real T2 pass (mirrors the port_a3 A3-UNAVAILABLE path —
classify_output called with cann=cpu_truth).

This module is PURE (no NPU / no torch_npu): it takes already-captured tensors and
classifies them. Reusable by both the worker's multirank_verify.py (per-rank self-verify)
and the orchestrator's multirank_runner (author≠measurer cross-check) — the canonical
judge lives in orchestrator code, workers import it (separation per
HARNESS_DESIGN_PHILOSOPHY §4e mechanism-gate / §4j hermetic).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import torch

# Reuse the canonical per-case judge — single source of truth for tier math.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from precision_eval_two_tier import classify_output  # noqa: E402


# ---------------------------------------------------------------------------
# Per-case native two-tier classifier (T2 real iff a competitor tensor is given)
# ---------------------------------------------------------------------------
def _classify_with_tolerance(ours, cpu_truth, tolerance) -> dict[str, Any]:
    """Spec-declared tolerance (e.g. int8-quantized references whose legitimate
    spread the per-dtype canonical thresholds cannot express): plain
    |ours-ref| <= atol + rtol*|ref| on the common dtype, T1 semantics; T2
    stays N/A (no competitor math here)."""
    atol = float(tolerance.get("atol", 0.0))
    rtol = float(tolerance.get("rtol", 0.0))
    try:
        ref_dtype = cpu_truth.dtype
        ours_cmp = (
            ours.detach().cpu().to(ref_dtype)
            if ours.dtype != ref_dtype
            else ours.detach().cpu()
        )
        ok = bool(
            torch.isclose(
                ours_cmp, cpu_truth.detach().cpu(), atol=atol, rtol=rtol
            ).all()
        )
        return {
            "verdict": "PASS_T1" if ok else "FAIL",
            "tier1_pass": ok,
            "tier2_status": "N/A_ALL_T1",
            "tier2_reason": "spec-declared tolerance path (T1-only)",
            "tolerance": {"atol": atol, "rtol": rtol},
        }
    except (RuntimeError, AttributeError, ValueError) as e:
        return {
            "verdict": "EVAL_ERR",
            "error": f"tolerance compare failed: {e!r}",
            "tier2_status": "N/A_ALL_T1",
        }


def _cast_to_ref(t, ref_dtype: "torch.dtype"):
    """Detach + cpu + cast onto the reference dtype (identity when equal)."""
    return t.detach().cpu().to(ref_dtype) if t.dtype != ref_dtype else t.detach().cpu()


def _classify_t1_only(ours_cmp, cpu_cmp, cand_dtype) -> dict[str, Any]:
    """cann=cpu_truth: T1 math identical to the canonical judge; the T2
    fallback (ours<=cann where cann==cpu_truth) is trivially equal so we
    discard it and mark T2 N/A — never let it masquerade as a real T2 pass."""
    m = classify_output(ours_cmp, cpu_cmp, cpu_cmp, cand_orig_dtype=cand_dtype)
    t1_pass = m.get("verdict") in ("PASS_T1", "PASS_T1_SMALLVAL")
    verdict = (
        "PASS_T1"
        if t1_pass
        else ("EVAL_ERR" if m.get("verdict") == "EVAL_ERR" else "FAIL")
    )
    out = {
        "verdict": verdict,
        "tier1_pass": t1_pass,
        "tier2_status": "N/A_ALL_T1",
        "tier2_reason": (
            "multirank spec declares no t2_competitor — T2 not computable; "
            "verdict is T1-only (ours vs cpu_truth)."
        ),
        "dtype": m.get("dtype"),
        "ours_mere": m.get("ours_mere"),
        "ours_mare": m.get("ours_mare"),
        "threshold": m.get("threshold"),
    }
    if "error" in m:
        out["error"] = m["error"]
    return out


def _classify_with_competitor(
    ours_cmp, comp_cmp, cpu_cmp, cand_dtype
) -> dict[str, Any]:
    """Real competitor arm — the same commercial-route parity fallback the
    benchmark mode uses against its CANN competitor."""
    m = classify_output(
        ours_cmp, comp_cmp, cpu_cmp, cand_orig_dtype=cand_dtype, route="commercial"
    )
    v = m.get("verdict")
    t1_pass = v in ("PASS_T1", "PASS_T1_SMALLVAL")
    if t1_pass:
        tier2_status = "N/A_T1_PASS"  # T1 already passed; T2 moot
    elif v == "PASS_T2":
        tier2_status = "PASS"  # ours ≤ competitor (parity-or-better)
    elif v == "EVAL_ERR":
        tier2_status = "EVAL_ERR"
    else:
        tier2_status = "FAIL"  # strictly worse than the competitor
    out = {
        "verdict": v
        if v in ("PASS_T1", "PASS_T1_SMALLVAL", "PASS_T2")
        else ("EVAL_ERR" if v == "EVAL_ERR" else "FAIL"),
        "tier1_pass": t1_pass,
        "tier2_status": tier2_status,
        "dtype": m.get("dtype"),
        "ours_mere": m.get("ours_mere"),
        "ours_mare": m.get("ours_mare"),
        "comp_mere": m.get("cann_mere"),
        "comp_mare": m.get("cann_mare"),
        "beats_competitor": m.get("beats_cann"),
        "threshold": m.get("threshold"),
    }
    if "error" in m:
        out["error"] = m["error"]
    return out


def classify_multirank_case(
    ours: torch.Tensor,
    cpu_truth: torch.Tensor,
    *,
    cand_orig_dtype: "torch.dtype | None" = None,
    competitor: "torch.Tensor | None" = None,
    tolerance: "dict | None" = None,
) -> dict[str, Any]:
    """Native two-tier verdict for ONE multirank (ours, cpu_truth [, competitor]) triple.

    competitor=None → T1-only (ours vs cpu_truth); T2 is N/A_ALL_T1 and never
    masquerades as a real T2 pass.
    competitor given (the spec's `t2_competitor` output — a composed stock CANN
    path run on NPU in the same HCCL group) → the real T2 arm via the canonical
    judge's route="commercial" fallback: PASS_T2 = ours fails T1 but
    ours_MERE ≤ comp_MERE AND ours_MARE ≤ comp_MARE (parity-or-better).

    Delegates T1 math to classify_output so the per-dtype thresholds /
    small-value rule / fp16-aware coarser-dtype are IDENTICAL to the canonical
    judge (same as port_a3 A3-UNAVAILABLE path when competitor is None).

    Returns a dict with:
      verdict       PASS_T1 | PASS_T2 | FAIL | EVAL_ERR
      tier1_pass    bool  (ours matches cpu_truth at T1 thresholds)
      tier2_status  PASS | FAIL | N/A_T1_PASS | N/A_ALL_T1 | EVAL_ERR
      ... plus the underlying classify_output T1 (+T2) metrics.
    """
    if cpu_truth is None:
        return {
            "verdict": "EVAL_ERR",
            "error": "cpu_truth is None",
            "tier2_status": "N/A_ALL_T1",
        }
    if tolerance is not None:
        return _classify_with_tolerance(ours, cpu_truth, tolerance)

    # Align dtypes for comparable error MATH (mirror classify_port_a3_case cast).
    ref_dtype = cpu_truth.dtype
    cand_dtype = (
        cand_orig_dtype
        if cand_orig_dtype is not None
        else getattr(ours, "dtype", ref_dtype)
    )
    try:
        ours_cmp = _cast_to_ref(ours, ref_dtype)
    except (RuntimeError, AttributeError) as e:
        return {
            "verdict": "EVAL_ERR",
            "error": f"ours cast failed: {e!r}",
            "tier2_status": "N/A_ALL_T1",
        }
    cpu_cmp = cpu_truth.detach().cpu()
    if competitor is None:
        return _classify_t1_only(ours_cmp, cpu_cmp, cand_dtype)
    try:
        comp_cmp = _cast_to_ref(competitor, ref_dtype)
    except (RuntimeError, AttributeError) as e:
        return {
            "verdict": "EVAL_ERR",
            "error": f"competitor cast failed: {e!r}",
            "tier2_status": "EVAL_ERR",
        }
    return _classify_with_competitor(ours_cmp, comp_cmp, cpu_cmp, cand_dtype)


# ---------------------------------------------------------------------------
# Per-rank summary (one rank's worth of cases)
# ---------------------------------------------------------------------------
def summarize_per_rank(per_case: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate per-case verdicts for ONE rank → two-tier rank summary.

    Mirrors precision_eval_port_a3_two_tier.summarize schema (verification.json
    contract compatibility): tier2_pass counts cases that FAILED T1 but PASSED
    T2 (parity-or-better vs the declared competitor); tier1_pass_inclusive =
    tier1_pass + tier2_pass (the P0cc inclusive count). With no competitor every
    case is N/A_ALL_T1 → tier2_pass = 0 and inclusive = tier1_pass (unchanged).
    """
    n_total = len(per_case)
    n_t1 = sum(1 for c in per_case if c.get("tier1_pass") is True)
    n_t2 = sum(1 for c in per_case if c.get("tier2_status") == "PASS")
    n_fail = sum(1 for c in per_case if c.get("verdict") == "FAIL")
    n_err = sum(1 for c in per_case if c.get("verdict") == "EVAL_ERR")

    if n_total == 0:
        rank_tier2_status = "N/A_NO_CASES"
    elif n_fail > 0 or n_err > 0:
        rank_tier2_status = "FAIL"
    elif n_t2 > 0:
        rank_tier2_status = "PASS"
    else:
        rank_tier2_status = "N/A_ALL_T1"

    status = "PASS" if (n_fail == 0 and n_err == 0 and n_total > 0) else "FAIL"
    method = (
        "multirank_precision_eval_two_tier (T1 vs cpu_truth + T2 parity vs "
        "spec t2_competitor)"
        if any(
            c.get("tier2_status") in ("PASS", "FAIL", "N/A_T1_PASS") for c in per_case
        )
        else "multirank_precision_eval_two_tier (native T1 vs cpu_truth; T2 N/A — no competitor)"
    )

    return {
        "tier1_pass": n_t1,
        "tier2_pass": n_t2,
        "tier1_pass_inclusive": n_t1 + n_t2,
        "total": n_total,
        "tier2_status": rank_tier2_status,
        "n_fail": n_fail,
        "n_err": n_err,
        "status": status,
        "method": method,
        "results": per_case,
    }


# ---------------------------------------------------------------------------
# All-rank aggregation: ALL-rank-PASS means overall PASS — design §3.2
# ---------------------------------------------------------------------------
def aggregate_all_ranks(rank_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate per-rank summaries → op-level multirank verdict.

    multirank design §3.2: verdict is PASS ONLY if EVERY rank PASSes (ALL-rank-PASS,
    strict AND aggregation). A single rank's FAIL fails the op.

    Status vocabulary: "PASS" when every rank passed purely on T1;
    "PASS_WITHIN_TOLERANCE" when every rank passed but ≥1 case needed the T2
    parity arm (the P0cc inclusive vocabulary — O5 count reconciliation then
    compares tier1_pass_inclusive, and the archive honestly records the T2
    contribution); "FAIL" otherwise.
    """
    overall_pass = all(rs.get("status") == "PASS" for rs in rank_summaries)
    total_t1 = sum(rs.get("tier1_pass", 0) for rs in rank_summaries)
    total_t2 = sum(rs.get("tier2_pass", 0) for rs in rank_summaries)
    total_cases = sum(rs.get("total", 0) for rs in rank_summaries)
    if not overall_pass:
        status = "FAIL"
        tier2_status = "FAIL"
    elif total_t2 > 0:
        status = "PASS_WITHIN_TOLERANCE"
        tier2_status = "PASS"
    else:
        status = "PASS"
        tier2_status = "N/A_ALL_T1"
    return {
        "status": status,
        "world_size": len(rank_summaries),
        "tier1_pass": total_t1,
        "tier2_pass": total_t2,
        "total": total_cases,
        "tier1_pass_inclusive": total_t1 + total_t2,
        "tier2_status": tier2_status,
        "ranks": rank_summaries,
        "method": "multirank_precision_eval_two_tier aggregate_all_ranks (ALL-rank-PASS)",
    }
