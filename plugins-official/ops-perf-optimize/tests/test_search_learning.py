# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Restore prior learning and diagnostic attribution over existing evidence."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parents[1]
        / "skills/ops-perf-optimize-workflow/scripts"
    ),
)
# ruff: noqa: E402
from search import attribution, prior, proxy
from test_search_evidence import make_index, write
from test_search_policy import Run
from test_search_round import options
import search_round


def record(
    scheme, factors, ratio, *, mechanism="tiling", soc="Ascend950", classification=None
):
    classification = classification or (
        "effective_improvement" if ratio < 1 else "effective_regression"
    )
    return {
        "scheme_id": scheme,
        "factors": factors,
        "mechanism": mechanism,
        "target_socs": [soc],
        "effect_summary": {"path": scheme, "sha256": scheme},
        "cases": [
            {
                "case_id": "a",
                "ratio": ratio,
                "reference_us": 100,
                "candidate_us": ratio * 100,
                "classification": classification,
            }
        ],
    }


def test_original_proxy_learns_numeric_axis_direction_and_prior_fallback():
    history = [
        record(str(i), {"baseM": base}, ratio)
        for i, (base, ratio) in enumerate(
            ((64, 0.7), (64, 0.72), (128, 1.0), (128, 1.05))
        )
    ]
    nodes = [
        {
            "scheme_id": name,
            "mechanism": "tiling",
            "factors": {"baseM": size},
            "cost": 1,
            "risk": 0.1,
        }
        for name, size in (("small", 64), ("large", 128))
    ]
    assert proxy.rank(history, nodes, soc="Ascend950")[0]["scheme_id"] == "small"
    exact = prior.query(history, mechanism="tiling", soc="Ascend950")
    assert exact["n"] == 4 and exact["source"] == "exact"
    assert (
        prior.query(history, mechanism="tiling", soc="other")["source"] == "mechanism"
    )
    assert prior.query(history, mechanism="new", soc="other")["source"] == "global"
    assert proxy.rank([], nodes, soc="Ascend950")[0]["prior"]["source"] == "none"


def test_history_reuses_verified_events_without_duplicate_trials(tmp_path):
    run = Run(tmp_path)
    run.finish_round(1, values=(120, 120), selected=False)
    run.finish_round(2, kind="precision_failed")
    before = run.state.read_bytes()
    history = prior.read_history([run.state, run.state])
    assert run.state.read_bytes() == before
    assert [item["scheme_id"] for item in history] == ["s1"]
    assert [row["ratio"] for row in prior.iter_rows(history, soc="Ascend950")] == [
        1.2,
        1.2,
    ]
    assert not prior.iter_rows(history, soc="Ascend910B")
    effect = tmp_path / "round1/effect.json"
    effect.write_text(effect.read_text() + " ")
    with pytest.raises(ValueError, match="restore accepted search evidence"):
        prior.read_history([run.state])


def test_history_ranking_is_connected_to_candidate_planning(tmp_path):
    root = tmp_path / "previous"
    root.mkdir()
    run = Run(root)
    run.finish_round(1, values=(90, 90), selected=True)
    args = options(tmp_path)
    args.history_state, args.soc, args.top_k = [run.state], "Ascend950", 1
    result = search_round.run(args)
    acquisition = json.loads(open(result["acquisition"]).read())
    assert acquisition["ranking"] and acquisition["history"]
    # A tiny prior budget cannot delete the mandatory open/type coverage.
    assert acquisition["pruned"] == []
    assert "prune_skipped_reason" in acquisition
    assert not list(tmp_path.rglob("*.sqlite"))


@pytest.mark.parametrize(
    "round_name, expected", [("round1", 0), ("round2", 1), ("gen.round3", 2)]
)
def test_combo_progression_uses_existing_round_numbers(tmp_path, round_name, expected):
    args = options(tmp_path)
    space = json.loads(args.space.read_text())
    space["axes"].append({"name": "buffers", "values": [1, 2]})
    write(args.space, space)
    args.combo_stage, args.round = "auto", round_name
    result = search_round.run(args)
    assert result["combo_stage"]["stage"] == expected
    frontier = json.loads(open(result["frontier"]).read())
    assert frontier["base_factors"] == {"m": 64, "n": 64, "buffers": 1}
    assert any(node["explore_tag"] == "open" for node in frontier["nodes"])


def test_supported_components_and_slow_combination_are_distinguished():
    base = {"x": 0, "y": 0}
    components = [
        record("x", {"x": 1, "y": 0}, 0.9),
        record("y", {"x": 0, "y": 1}, 0.92),
    ]
    combo = record("xy", {"x": 1, "y": 1}, 1.2)
    report = attribution.build({"candidates": [combo]}, {"nodes": []}, base, components)
    result = report["candidates"][0]
    assert result["reason"] == "negative_interaction"
    assert {c["scheme_id"] for c in result["supported_components"]} == {"x", "y"}
    assert report["advisory_only"]
    # Different factor levels or reference measurements are not components.
    components[0]["factors"]["x"] = 2
    components[1]["cases"][0]["reference_us"] = 200
    result = attribution.build({"candidates": [combo]}, {"nodes": []}, base, components)
    assert result["candidates"][0]["reason"] == "implementation_imperfect"


def test_slow_implementation_is_not_a_mechanism_refutation():
    item = record("slow", {"x": 1}, 1.2)
    report = attribution.build({"candidates": [item]}, {"nodes": []}, {"x": 0})
    assert report["candidates"][0]["reason"] == "implementation_imperfect"
    assert "mechanism_wrong" not in report["counts"]
    item["cases"][0]["classification"] = "inconclusive"
    assert attribution.build({"candidates": [item]}, {"nodes": []}, {"x": 0})[
        "counts"
    ] == {"noise": 1}


def test_small_real_gain_stays_eligible_when_prediction_is_missed(tmp_path):
    args = options(tmp_path)
    planned = search_round.run(args)
    frontier = json.loads(open(planned["frontier"]).read())
    values = {node["scheme_id"]: [99.9, 99.9] for node in frontier["nodes"]}
    args.evidence_index = make_index(tmp_path / "tuning", values)
    args.attribution, args.dry_run = True, False
    result = search_round.run(args)
    report = json.loads(open(result["attribution"]).read())
    by_scheme = {item["scheme_id"]: item for item in report["candidates"]}
    assert all(
        by_scheme[node["scheme_id"]]["reason"] == "implementation_imperfect"
        for node in frontier["nodes"]
        if node["expected_gain_range"][0] > 0.001
    )
    observation = json.loads(open(result["observation"]).read())
    assert observation["eligible_for_confirmation"] is True
    assert observation["no_go"] == []
