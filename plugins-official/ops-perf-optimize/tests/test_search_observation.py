# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Ranking uses existing summaries and preserves their policy decisions."""

import pytest

from test_search_evidence import make_index, write
from search import evidence, observe
import search_selection


def setup(tmp_path, values=None, holdout_values=None, policy="median_v1"):
    values = values or {"fast": [90, 90], "slow": [110, 120]}
    index = make_index(tmp_path / "tuning", values, policy=policy)
    frontier = {
        "nodes": [{"scheme_id": scheme, "cost": 1, "risk": 0.1} for scheme in values]
    }
    frontier_path = write(tmp_path / "frontier.json", frontier)
    measurements = write(
        tmp_path / "measurements.json", evidence.build(index, frontier)
    )
    holdout = None
    if holdout_values:
        h_index = make_index(
            tmp_path / "holdout",
            holdout_values,
            cases=("h1", "h2"),
            policy=policy,
            manifest=tmp_path / "tuning/manifest.json",
        )
        holdout = write(tmp_path / "holdout.json", evidence.build(h_index, frontier))
    return measurements, frontier_path, holdout


def test_ranks_summary_medians_without_creating_confidence_intervals(tmp_path):
    paths = setup(tmp_path)
    result = observe.build(*paths)
    assert result["recommended"] == "fast"
    assert result["confirmation_required"] is True
    assert result["confirmation_blocker"] == "holdout_measurements_required"
    fast = result["observations"][0]
    assert fast["score_distribution"]["unit"] == "case_median_ratio"
    assert fast["pareto_rank"] == 1
    assert "confidence_interval" not in fast
    assert "race" not in fast


def test_reused_median_evidence_needs_no_paired_recollection(tmp_path):
    paths = setup(tmp_path, holdout_values={"fast": [90, 100]})
    result = observe.build(*paths)
    assert result["ready_for_confirmation"] is True
    assert (
        result["confirmation_required"] is True
    )  # Formal workflow still owns acceptance.
    assert result["confirmation_blocker"] is None
    observation = write(tmp_path / "observation.json", result)
    selection = write(
        tmp_path / "selection.json", {"performance": {"selected_candidate": "baseline"}}
    )
    gate = write(tmp_path / "gate.json", {"decision": "pass"})
    merged = search_selection.build(
        selection,
        observation,
        None,
        gate,
        tmp_path / "tuning/fast-effect.json",
        [],
        "unknown",
        [],
        "",
    )
    assert merged["performance"]["selected_candidate"] == "baseline"
    assert "confidence_interval" not in merged["search"]


def test_holdout_uses_frozen_median_policy_instead_of_extra_retreat_threshold(tmp_path):
    # This mixed holdout is an improvement under median_v1. The old 0.98
    # per-case gate rejected it; the adapter must preserve the frozen policy.
    paths = setup(tmp_path, holdout_values={"fast": [80, 105]})
    result = observe.build(*paths)
    assert result["holdout"]["requires_routing"] is False
    assert result["ready_for_confirmation"] is True


def test_observation_cannot_be_attached_to_another_candidates_effect(tmp_path):
    observation = write(tmp_path / "observation.json", observe.build(*setup(tmp_path)))
    selection = write(tmp_path / "selection.json", {"selected_candidate": "baseline"})
    gate = write(tmp_path / "gate.json", {"decision": "pass"})
    with pytest.raises(ValueError, match="observation summary differs"):
        search_selection.build(
            selection, observation, "fast", gate, tmp_path / "tuning/slow-effect.json",
            [], "unknown", [], "",
        )


def test_holdout_regression_stays_unselected(tmp_path):
    result = observe.build(*setup(tmp_path, holdout_values={"fast": [120, 120]}))
    assert result["ready_for_confirmation"] is False
    assert result["confirmation_blocker"] == "holdout_regression"
    assert (
        result["no_go"] == []
    )  # Failure scope/retry evidence belongs to the existing workflow.


def test_confidence_policy_requires_its_existing_proof(tmp_path):
    result = observe.build(
        *setup(
            tmp_path, holdout_values={"fast": [90, 90]}, policy="confidence_effect_v1"
        )
    )
    assert result["ready_for_confirmation"] is False
    assert result["confirmation_blocker"] == "evidence_pending"
    assert result["holdout"]["cases"][0]["classification"] == "inconclusive"


def test_tuning_cases_cannot_be_used_as_holdout(tmp_path):
    measurements, frontier, _ = setup(tmp_path)
    with pytest.raises(ValueError, match="overlap"):
        observe.build(measurements, frontier, measurements)


def test_control_diagnostic_does_not_change_scores_or_verdicts(tmp_path):
    paths = setup(tmp_path, values={"fast": [90, 90], "control": [105, 105]})
    result = observe.build(*paths, neutral_control="control")
    fast = result["observations"][0]
    assert fast["score_distribution"]["samples"] == [0.9, 0.9]
    assert fast["differential"][0]["adjusted_ratio"] == pytest.approx(0.9 / 1.05)
    assert "adjusted_ci" not in fast["differential"][0]
