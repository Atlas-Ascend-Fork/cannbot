# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

import argparse
import json
from pathlib import Path

import pytest

from test_search_evidence import make_index, write
import search_round


def options(tmp_path):
    source = tmp_path / "baseline"
    source.mkdir()
    (source / "kernel.cpp").write_text("value=0\n")
    trigger = tmp_path / "trigger.txt"
    trigger.write_text("synthetic")
    space = write(
        tmp_path / "space.json",
        {
            "schema_version": 1,
            "axes": [
                {"name": "m", "values": [64, 128]},
                {"name": "n", "values": [64, 128]},
            ],
            "prior": {"gain": [0.05, 0.2], "cost": 1.0, "risk": 0.1},
        },
    )
    return argparse.Namespace(
        frontier=None,
        space=space,
        parent=source,
        trigger=trigger,
        round="round1",
        best_us=100.0,
        n=2,
        p_pass=0.5,
        max_candidates=64,
        method=None,
        evidence_index=None,
        holdout_evidence_index=None,
        contract=None,
        selection=None,
        gate=None,
        effect_summary=None,
        evidence=[],
        mechanism_status="unknown",
        mechanism_evidence=[],
        retry_condition=None,
        replace=False,
        out_dir=tmp_path / "out",
        dry_run=True,
    )


def test_dry_run_needs_no_runner_or_measurement_protocol(tmp_path):
    result = search_round.run(options(tmp_path))
    assert result["status"] == "planned"
    assert Path(result["frontier"]).is_file()


def run_with_summaries(tmp_path, holdout_time):
    args = options(tmp_path)
    planned = search_round.run(args)
    nodes = json.loads(Path(planned["frontier"]).read_text())["nodes"]
    values = {node["scheme_id"]: [90, 90] for node in nodes}
    args.evidence_index = make_index(tmp_path / "tuning", values)
    args.holdout_evidence_index = make_index(
        tmp_path / "holdout",
        {key: [holdout_time] * 2 for key in values},
        cases=("h1", "h2"),
        manifest=tmp_path / "tuning/manifest.json",
    )
    args.dry_run = False
    return search_round.run(args)


def test_round_adapts_existing_summaries_without_executing_runner(
    tmp_path, monkeypatch
):
    def forbidden(*args, **kwargs):
        raise AssertionError("search must not launch a device process")

    monkeypatch.setattr("subprocess.run", forbidden)
    result = run_with_summaries(tmp_path, 90)
    assert result["status"] == "completed"
    assert result["ready_for_confirmation"] is True
    assert result["selection"] is None
    assert Path(result["holdout_measurements"]).is_file()


def test_fast_candidate_with_failed_holdout_stays_unselected(tmp_path):
    result = run_with_summaries(tmp_path, 120)
    assert result["status"] == "completed"
    assert result["ready_for_confirmation"] is False
    assert result["confirmation_blocker"] == "holdout_regression"
    assert result["selection"] is None


def contract_for_frontier(frontier):
    node = frontier["nodes"][0]
    return {
        "scheme_id": node["scheme_id"],
        "search": {
            "parent": frontier["parent"],
            "kind": node["kind"],
            "candidate_factors": node.get("factors", {}),
            "candidate_bindings": node.get("bindings", {}),
        },
    }


def handoff_options(tmp_path):
    args = options(tmp_path)
    planned = search_round.run(args)
    args.frontier = Path(planned["frontier"])
    frontier = json.loads(args.frontier.read_text())
    frontier["nodes"][0]["status"] = "selected"
    write(args.frontier, frontier)
    contract = contract_for_frontier(frontier)
    args.contract = write(tmp_path / "contract.json", contract)
    args.evidence_index = make_index(
        tmp_path / "tuning", {contract["scheme_id"]: [90, 90]}
    )
    args.space = args.parent = args.trigger = args.best_us = None
    args.dry_run = False
    args.out_dir = tmp_path / "implementation"
    return args


def test_handoff_consumes_one_scheme_without_replanning(tmp_path, monkeypatch):
    import search.round as round_impl

    args = handoff_options(tmp_path)
    original = args.frontier.read_bytes()

    def forbidden(*args, **kwargs):
        raise AssertionError(
            "implementation must not generate candidates or run models"
        )

    monkeypatch.setattr(round_impl.search_candidates, "build", forbidden)
    monkeypatch.setattr(round_impl, "run_l1_prefilter", forbidden)
    result = search_round.run(args)
    assert result["status"] == "completed"
    assert result["frontier"] == str(args.frontier.resolve())
    assert args.frontier.read_bytes() == original
    assert not (args.out_dir / "candidate-frontier.json").exists()
    measurements = json.loads(Path(result["measurements"]).read_text())
    assert len(measurements["candidates"]) == 1


def test_handoff_requires_the_current_contract(tmp_path):
    args = handoff_options(tmp_path)
    args.contract = None
    with pytest.raises(ValueError, match="--frontier requires --contract"):
        search_round.run(args)


def test_handoff_rejects_mismatched_contract(tmp_path):
    args = handoff_options(tmp_path)
    contract = json.loads(args.contract.read_text())
    contract["search"]["parent"] = {}
    write(args.contract, contract)
    with pytest.raises(ValueError, match="frontier parent differs from contract"):
        search_round.run(args)


@pytest.mark.parametrize("field", ["evidence_index", "holdout_evidence_index"])
def test_handoff_rejects_results_for_another_scheme(tmp_path, field):
    args = handoff_options(tmp_path)
    frontier = json.loads(args.frontier.read_text())
    other = frontier["nodes"][1]["scheme_id"]
    index = make_index(tmp_path / "other", {other: [90, 90]})
    setattr(args, field, index)
    with pytest.raises(ValueError, match="current contract scheme"):
        search_round.run(args)


def prefilter_options(tmp_path, monkeypatch):
    import search_prefilter

    args = options(tmp_path)
    space = json.loads(args.space.read_text())
    space["axes"].append({"name": "buffers", "values": [1, 2]})
    write(args.space, space)
    initial = search_round.run(args)
    frontier = json.loads(Path(initial["frontier"]).read_text())
    args.prefilter_backend = "dag_run"
    args.prefilter_top_k = 4
    args.prefilter_ranking = write(
        tmp_path / "ranking.json",
        {
            "ranking": [node["scheme_id"] for node in frontier["nodes"]],
        },
    )
    monkeypatch.setattr(
        search_prefilter,
        "run_prefilter",
        lambda *a, **kw: {
            "status": "applied",
            "tool": "synthetic-model",
            "backend": "dag_run",
            "coverage": len(frontier["nodes"]),
            "evidence": [],
        },
    )
    return args, frontier


def test_l1_ranking_without_calibration_report_does_not_prune(tmp_path, monkeypatch):
    args, original = prefilter_options(tmp_path, monkeypatch)
    result = search_round.run(args)
    frontier = json.loads(Path(result["frontier"]).read_text())
    assert frontier["nodes"] == original["nodes"]
    assert frontier["prefilter"]["l1"]["budget_skipped"] == 0
    assert (
        "validation report required"
        in frontier["prefilter"]["l1"]["prune_skipped_reason"]
    )


def test_l1_report_is_pinned_and_unmapped_candidates_survive(tmp_path, monkeypatch):
    from search import policy

    args, original = prefilter_options(tmp_path, monkeypatch)
    args.prefilter_validation = tmp_path / "calibration.md"
    args.prefilter_validation.write_text(
        "Synthetic analysis-reviewed calibration report; no device claim."
    )
    regular = [
        node["scheme_id"] for node in original["nodes"] if node["explore_tag"] != "open"
    ]
    write(
        args.prefilter_ranking,
        {"ranking": regular[:-1], "unmapped": [{"scheme_id": regular[-2]}]},
    )
    result = search_round.run(args)
    frontier = json.loads(Path(result["frontier"]).read_text())
    kept = {node["scheme_id"] for node in frontier["nodes"]}
    assert set(regular[-2:]) <= kept
    assert any(node["explore_tag"] == "open" for node in frontier["nodes"])
    assert frontier["prefilter"]["l1"]["budget_skipped"] > 0
    dependencies = policy.validate_frontier(frontier)
    assert policy.ref(args.prefilter_validation) in dependencies
    assert policy.ref(args.prefilter_ranking) in dependencies
    validation = frontier["prefilter"]["l1"].pop("ranking_validation")
    with pytest.raises(ValueError, match="L1 pruning needs"):
        policy.validate_frontier(frontier)
    frontier["prefilter"]["l1"]["ranking_validation"] = validation
    args.prefilter_validation.write_text("changed review")
    with pytest.raises(ValueError, match="stale evidence SHA"):
        policy.validate_frontier(frontier)
