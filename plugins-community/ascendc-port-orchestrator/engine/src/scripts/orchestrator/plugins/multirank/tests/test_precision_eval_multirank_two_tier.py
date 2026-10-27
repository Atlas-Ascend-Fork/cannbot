# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

"""Tests for multirank_precision_eval_two_tier.py — multirank canonical judge.

Mirrors test_precision_eval_port_a3_two_tier.py style. multirank has no vendor CANN
competitor → T2 stays N/A_ALL_T1 unless the spec declares a t2_competitor; the
default verdict is T1-only (delegates to precision_eval_two_tier.classify_output
with cann=cpu_truth). PURE (no NPU).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import torch

# engine/src/scripts/ (for precision_eval_two_tier) + orchestrator/ (for the
# multirank extension package) must both be importable.
_SCRIPTS = Path(__file__).resolve().parents[4]  # engine/src/scripts/
_ORCH = _SCRIPTS / "orchestrator"
for _p in (str(_ORCH), str(_SCRIPTS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from plugins.multirank.multirank_precision_eval_two_tier import (  # noqa: E402
    classify_multirank_case,
    summarize_per_rank,
    aggregate_all_ranks,
)


def test_classify_match_passes_t1():
    r = classify_multirank_case(
        torch.tensor([1.0, 2.0, 3.0], dtype=torch.float16),
        torch.tensor([1.0, 2.0, 3.0], dtype=torch.float16),
    )
    assert r["verdict"] == "PASS_T1"
    assert r["tier1_pass"] is True
    # multirank declares no competitor → T2 always N/A, never an auto-pass.
    assert r["tier2_status"] == "N/A_ALL_T1"


def test_classify_mismatch_fails():
    r = classify_multirank_case(
        torch.tensor([5.0, 2.0, 3.0], dtype=torch.float16),
        torch.tensor([1.0, 2.0, 3.0], dtype=torch.float16),
    )
    assert r["verdict"] == "FAIL"
    assert r["tier1_pass"] is False
    assert r["tier2_status"] == "N/A_ALL_T1"


def test_classify_integer_bit_exact():
    r = classify_multirank_case(torch.tensor([1, 2, 3]), torch.tensor([1, 2, 3]))
    assert r["tier1_pass"] is True


def test_classify_none_cpu_truth_eval_err():
    r = classify_multirank_case(torch.tensor([1.0]), None)
    assert r["verdict"] == "EVAL_ERR"
    assert r["tier2_status"] == "N/A_ALL_T1"


def test_summarize_all_pass():
    t = torch.zeros(4, dtype=torch.float16)
    cases = [classify_multirank_case(t, t) for _ in range(3)]
    s = summarize_per_rank(cases)
    assert s["status"] == "PASS"
    assert s["tier1_pass"] == 3 and s["total"] == 3
    assert s["tier2_pass"] == 0  # no competitor → no T2 contribution
    assert s["tier1_pass_inclusive"] == 3  # = tier1_pass (no T2 contribution)
    assert s["tier2_status"] == "N/A_ALL_T1"


def test_summarize_with_fail():
    t = torch.zeros(4, dtype=torch.float16)
    cases = [
        classify_multirank_case(t, t),
        classify_multirank_case(torch.ones(4, dtype=torch.float16), t),
    ]
    s = summarize_per_rank(cases)
    assert s["status"] == "FAIL"
    assert s["tier1_pass"] == 1


def test_aggregate_all_ranks_pass():
    t = torch.zeros(4, dtype=torch.float16)
    rs = [summarize_per_rank([classify_multirank_case(t, t)]) for _ in range(2)]
    a = aggregate_all_ranks(rs)
    assert a["status"] == "PASS"
    assert a["world_size"] == 2
    assert a["tier1_pass"] == 2


def test_aggregate_one_rank_fails_overall_fails():
    """ALL-rank-PASS (strict AND): one rank FAIL → overall FAIL (design §3.2)."""
    t = torch.zeros(4, dtype=torch.float16)
    rs = [
        summarize_per_rank([classify_multirank_case(t, t)]),
        summarize_per_rank(
            [classify_multirank_case(torch.ones(4, dtype=torch.float16), t)]
        ),
    ]
    a = aggregate_all_ranks(rs)
    assert a["status"] == "FAIL"


# ---------------------------------------------------------------------------
# T2 competitor arm (spec-declared composed stock CANN path)
# ---------------------------------------------------------------------------


def _g():
    return torch.tensor([1.0, -2.0, 0.5, 8.0], dtype=torch.bfloat16)


def test_classify_t2_parity_pass():
    """Ours fails T1 but is parity-or-better vs the competitor → PASS_T2."""
    g = _g()
    ours = (g.float() * 1.2).to(torch.bfloat16)  # ~20% err → T1 FAIL
    comp = (g.float() * 1.5).to(torch.bfloat16)  # worse competitor
    r = classify_multirank_case(ours, g, competitor=comp)
    assert r["verdict"] == "PASS_T2"
    assert r["tier1_pass"] is False
    assert r["tier2_status"] == "PASS"
    assert r["comp_mere"] is not None and r["ours_mere"] <= r["comp_mere"]


def test_classify_t2_strictly_worse_fails():
    """Ours fails T1 AND is strictly worse than the competitor → FAIL."""
    g = _g()
    ours = (g.float() * 1.2).to(torch.bfloat16)
    comp = (g.float() * 1.1).to(torch.bfloat16)  # better competitor
    r = classify_multirank_case(ours, g, competitor=comp)
    assert r["verdict"] == "FAIL"
    assert r["tier1_pass"] is False
    assert r["tier2_status"] == "FAIL"


def test_classify_t1_pass_with_competitor_t2_moot():
    g = _g()
    r = classify_multirank_case(
        g.clone(), g, competitor=(g.float() * 2).to(torch.bfloat16)
    )
    assert r["verdict"] == "PASS_T1"
    assert r["tier1_pass"] is True
    assert r["tier2_status"] == "N/A_T1_PASS"


def test_classify_no_competitor_t2_stays_na():
    """Backward compat: no competitor → T2 N/A, verdict ladder unchanged."""
    g = _g()
    ours = (g.float() * 1.2).to(torch.bfloat16)
    r = classify_multirank_case(ours, g)
    assert r["verdict"] == "FAIL"
    assert r["tier2_status"] == "N/A_ALL_T1"


def test_summarize_counts_t2_into_inclusive():
    g = _g()
    t1 = classify_multirank_case(g.clone(), g, competitor=g.clone())
    t2 = classify_multirank_case(
        (g.float() * 1.2).to(torch.bfloat16),
        g,
        competitor=(g.float() * 1.5).to(torch.bfloat16),
    )
    s = summarize_per_rank([t1, t2])
    assert s["status"] == "PASS"
    assert s["tier1_pass"] == 1
    assert s["tier2_pass"] == 1
    assert s["tier1_pass_inclusive"] == 2
    assert s["tier2_status"] == "PASS"


def test_aggregate_pass_within_tolerance_when_t2_contributes():
    g = _g()
    t1 = classify_multirank_case(g.clone(), g, competitor=g.clone())
    t2 = classify_multirank_case(
        (g.float() * 1.2).to(torch.bfloat16),
        g,
        competitor=(g.float() * 1.5).to(torch.bfloat16),
    )
    rs = [summarize_per_rank([t1, t2]) for _ in range(2)]
    a = aggregate_all_ranks(rs)
    assert a["status"] == "PASS_WITHIN_TOLERANCE"
    assert a["tier2_status"] == "PASS"
    assert a["tier1_pass"] == 2
    assert a["tier2_pass"] == 2
    assert a["tier1_pass_inclusive"] == 4
    assert a["total"] == 4


def test_aggregate_pure_t1_stays_plain_pass():
    g = _g()
    rs = [
        summarize_per_rank(
            [classify_multirank_case(g.clone(), g, competitor=g.clone())]
        )
        for _ in range(2)
    ]
    a = aggregate_all_ranks(rs)
    assert a["status"] == "PASS"
    assert a["tier2_status"] == "N/A_ALL_T1"
    assert a["tier1_pass_inclusive"] == a["tier1_pass"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
