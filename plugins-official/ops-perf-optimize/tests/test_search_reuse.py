# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Regressions for shared policy and frozen proof statistics."""

import random
import statistics
import sys
from pathlib import Path

import pytest

SCRIPTS = (
    Path(__file__).resolve().parents[1] / "skills/ops-perf-optimize-workflow/scripts"
)
sys.path.insert(0, str(SCRIPTS))
# ruff: noqa: E402
import search_policy
from search import policy
from performance_effect_evidence import compute_statistics, quantile
from test_search_frontier import frontier


def test_both_policy_imports_share_git_and_csv_contracts(tmp_path):
    assert search_policy is policy
    parent = {"commit": "a" * 40, "tree": "b" * 40}
    f = frontier(tmp_path)
    f["parent"] = parent
    search_policy.validate_parent({"parent": parent}, None)
    policy.validate_frontier(f)
    cases = tmp_path / "cases.csv"
    cases.write_text("shape,dtype\n128,float32\n")
    assert policy.case_ids(cases) == ["row-2"]
    with pytest.raises(ValueError, match="invalid git parent"):
        policy.validate_parent({"parent": {"commit": "bad", "tree": "b" * 40}}, None)


def test_invalidated_results_do_not_change_search_history():
    event = {
        "kind": "search_result",
        "invalidated": True,
        "result": {"scheme_id": "s1", "outcome": "measured"},
        "classification": "no_improvement",
        "context": "c",
    }
    replay = policy.replay({"events": [event]})
    assert replay["stagnation"] == 0
    assert replay["results"] == {}


def test_existing_bootstrap_preserves_frozen_proof_algorithm():
    values = [-1.1, -2.3, 0.7, -0.5, 1.2, -0.9]
    method = {
        "id": "python_mt19937_percentile_median_v1",
        "statistic": "median",
        "quantile": "linear",
        "confidence": 0.95,
        "draws": 1000,
        "seed": 7,
    }
    rng = random.Random(7)
    medians = sorted(
        statistics.median(rng.choices(values, k=len(values))) for _ in range(1000)
    )
    result = compute_statistics(values, method)
    assert result["paired_ci_us"] == [
        quantile(medians, 0.025),
        quantile(medians, 0.975),
    ]


def test_f1_observation_gate_requires_measured():
    assert search_policy.needs_observation_gate({"outcome": "measured"}, True)
    assert not search_policy.needs_observation_gate(
        {"outcome": "screened", "provisional": True}, True
    )
    assert not search_policy.needs_observation_gate({"outcome": "measured"}, False)


def test_f2_observation_payload_has_explicit_mechanism_keys():
    event = {
        "classification": "measured",
        "result": {
            "mechanism": {"id": "m", "status": "verified"},
            "retry_condition": "none",
        },
    }
    decisions = {"s1": (None, {"search": {"mechanism": "axis-x"}})}
    row = search_policy.observation_payload("s1", event, decisions)
    assert row["scheme_id"] == "s1"
    assert row["mechanism_id"] == "axis-x"
    assert row["mechanism_status"] == "verified"
    assert row["classification"] == "measured"
    assert row["mechanism"]["id"] == "m"
