# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Synthetic candidate-frontier contracts. These tests make no hardware claims."""

import sys
from itertools import combinations, product
from pathlib import Path

import pytest

SCRIPTS = (
    Path(__file__).resolve().parents[1] / "skills/ops-perf-optimize-workflow/scripts"
)
sys.path.insert(0, str(SCRIPTS))
# ruff: noqa: E402
import search_policy as search

from test_search_policy import Run, write


def node(
    scheme,
    *,
    level="M0",
    kind="architecture",
    optimization_type="tiling",
    explore_tag="exploit",
    depends=(),
    gain=(0.2, 0.4),
    cost=2.0,
    risk=0.2,
    fidelity="L1",
    status="candidate",
    trigger=None,
    lower_bound=None,
    mechanism=None,
):
    value = {
        "scheme_id": scheme,
        "kind": kind,
        "level": level,
        "mechanism": mechanism or f"mechanism-{scheme}",
        "optimization_type": optimization_type,
        "trigger": trigger or [],
        "expected_gain_range": list(gain),
        "cost": cost,
        "risk": risk,
        "fidelity": fidelity,
        "status": status,
        "explore_tag": explore_tag,
        "depends_on": list(depends),
    }
    if lower_bound is not None:
        value["lower_bound_us"] = lower_bound
    return value


def frontier(tmp_path, *, best=100.0, nodes=None, round_name="round1"):
    source = tmp_path / "baseline"
    source.mkdir(exist_ok=True)
    (source / "kernel.cpp").write_text("value = 0\n")
    evidence = tmp_path / "diagnosis.txt"
    evidence.write_text("synthetic fixture, not a hardware measurement")
    ref = search.ref(evidence)
    nodes = nodes or [
        node("s1", status="selected", trigger=[ref], gain=(0.4, 0.6)),
        node("s2", trigger=[ref], optimization_type="bandwidth"),
        node(
            "s3",
            level="open",
            explore_tag="open",
            optimization_type="algorithm",
            trigger=[ref],
        ),
        node(
            "s4",
            kind="local",
            level="M1",
            depends=("s1",),
            trigger=[ref],
            gain=(0.05, 0.1),
        ),
        node(
            "s5",
            kind="local",
            level="M1",
            depends=("s2",),
            optimization_type="bandwidth",
            trigger=[ref],
        ),
        node(
            "s6",
            kind="local",
            level="M1",
            depends=("s1",),
            optimization_type="schedule",
            trigger=[ref],
        ),
    ]
    return {
        "schema_version": 1,
        "round": round_name,
        "parent": search.source_identity(source),
        "best_total_us": best,
        "n": 3,
        "p_pass": 0.5,
        "epsilon": 0.01,
        "explore_every": 3,
        "prefilter": {
            "l0": {"method": "roofline", "best_total_us": best},
            "l1": {
                "tool": "ops-opmodel-toolkit",
                "coverage": len(nodes),
                "budget_skipped": 0,
                "evidence": [ref],
            },
        },
        "nodes": nodes,
    }


def test_valid_frontier_has_a_dag_diversity_and_open_exploration(tmp_path):
    run = Run(tmp_path)
    value = frontier(tmp_path)
    dependencies = search.validate_frontier(value)
    assert dependencies
    assert {item["kind"] for item in value["nodes"]} == {"architecture", "local"}
    assert any(item["explore_tag"] == "open" for item in value["nodes"])
    assert run is not None


def test_frontier_rejects_cycles_and_missing_trigger(tmp_path):
    value = frontier(tmp_path)
    value["nodes"][0]["depends_on"] = ["s4"]
    with pytest.raises(ValueError, match="cycle"):
        search.validate_frontier(value)
    value = frontier(tmp_path)
    value["nodes"][0]["trigger"] = []
    with pytest.raises(ValueError, match="evidence references"):
        search.validate_frontier(value)


def test_l0_lower_bound_must_be_pruned_before_selection(tmp_path):
    value = frontier(tmp_path)
    value["nodes"][1]["lower_bound_us"] = 200.0
    with pytest.raises(ValueError, match="prune it"):
        search.validate_frontier(value)
    pruned = search.prune(value)
    assert pruned["pruned"][0]["scheme_id"] == "s2"
    assert pruned["pruned"][0]["prune_reason"] == "lower_bound"
    search.validate_frontier(pruned)


def test_ucb_and_exploration_quota_select_from_the_frontier(tmp_path):
    value = frontier(tmp_path)
    ranked = search.select(value, strategy="beam", width=2)
    assert ranked["selected"] == "s1"
    assert len(ranked["beam"]) == 2
    opened = search.select(value, strategy="ucb", force_explore=True)
    assert opened["selected"] == "s3"
    assert opened["explore_forced"]


def test_race_uses_paired_confidence_and_keeps_ambiguous_candidates(tmp_path):
    winner = search.race([0.9, 0.91, 0.89])
    assert winner["decision"] == "stop_winner"
    loser = search.race([1.1, 1.12, 1.09])
    assert loser["decision"] == "stop_loser"
    ambiguous = search.race([0.9, 1.1, 1.0])
    assert ambiguous["decision"] == "continue"
    assert search.race([0.9])["decision"] == "continue"


def test_backprop_marks_refuted_mechanism_in_frontier(tmp_path):
    value = frontier(tmp_path)
    result = {
        "result": {
            "scheme_id": "s1",
            "outcome": "measured",
            "mechanism": {"status": "refuted"},
            "retry_condition": "only with a new probe",
        },
        "promoted": None,
    }
    observed = search.backprop(value, result)
    selected = next(item for item in observed["nodes"] if item["scheme_id"] == "s1")
    assert selected["status"] == "no_go"
    assert selected["children"] == ["s4", "s6"]


def attached_frontier(run, value):
    contract_path = run.plan(1, register=False)
    contract = search.load(contract_path)
    selected = next(item for item in value["nodes"] if item["scheme_id"] == "s1")
    contract["search"].update(
        {
            "frontier_parent": "s1",
            "fidelity": selected["fidelity"],
            "expected_gain_range": selected["expected_gain_range"],
            "cost": selected["cost"],
        }
    )
    write(contract_path, contract)
    value["parent"] = contract["search"]["parent"]
    path = write(run.root / "round1/candidate-frontier-s1.json", value)
    run.cli(
        "mark",
        "--stage",
        "round1.analysis",
        "--status",
        "complete",
        "--artifact",
        contract_path,
        "--artifact",
        path,
    )
    return contract_path, path


def observation(selection_path):
    selection = search.load(selection_path)
    selection["search"].update(
        {
            "score_distribution": {
                "metric": "candidate_over_best",
                "samples": [0.91, 0.9, 0.92],
            },
            "confidence_interval": {"low": 0.89, "high": 0.93, "confidence": 0.95},
            "pareto_rank": 1,
            "race": {"decision": "stop_winner"},
        }
    )
    write(selection_path, selection)


def test_frontier_round_updates_state_and_observation_evidence(tmp_path):
    run = Run(tmp_path)
    contract_path, _ = attached_frontier(run, frontier(tmp_path))
    plan = search.load(contract_path)
    args, _, _ = run.outcome(1, contract_path, values=(90, 90), selected=True)
    selection = tmp_path / "round1/selection.json"
    observation(selection)
    run.cli("mark", *args)
    view = run.view()
    assert view["frontier"]["selected"] is not None
    assert view["patience"] == search.PATIENCE
    accepted = next(
        item for item in view["frontier"]["nodes"] if item["scheme_id"] == "s1"
    )
    assert accepted["status"] == "accepted"
    assert view["reanchor"]["mode"] == "relative_5pct"
    assert view["reanchor"]["targets"][0]["target_total_us"] == 85.5
    assert run.cli("verify")["status"] == "valid"
    assert plan["scheme_id"] == "s1"


def test_frontier_observation_without_statistics_is_rejected(tmp_path):
    run = Run(tmp_path)
    contract_path, _ = attached_frontier(run, frontier(tmp_path))
    args, _, _ = run.outcome(1, contract_path, values=(90, 90), selected=True)
    error = run.cli("mark", *args, ok=False)
    assert "score_distribution" in error["error"]


def test_contract_metadata_must_match_the_selected_frontier_node(tmp_path):
    run = Run(tmp_path)
    value = frontier(tmp_path)
    contract_path = run.plan(1, register=False)
    contract = search.load(contract_path)
    contract["search"].update(
        {
            "frontier_parent": "s2",
            "fidelity": "L2",
            "expected_gain_range": [0.1, 0.2],
            "cost": 2.0,
        }
    )
    write(contract_path, contract)
    path = write(run.root / "round1/candidate-frontier-s1.json", value)
    error = run.cli(
        "mark",
        "--stage",
        "round1.analysis",
        "--status",
        "complete",
        "--artifact",
        contract_path,
        "--artifact",
        path,
        ok=False,
    )
    assert "frontier_parent" in error["error"] or "fidelity" in error["error"]


def test_search_frontier_cli_prunes_and_ranks_without_writing_state(tmp_path):
    run = Run(tmp_path)
    contract_path, frontier_path = attached_frontier(run, frontier(tmp_path))
    before = run.state.read_bytes()
    output = tmp_path / "ranking.json"
    payload = run.cli(
        "search-frontier",
        "--frontier",
        frontier_path,
        "--contract",
        contract_path,
        "--strategy",
        "beam",
        "--out",
        output,
    )
    assert payload["status"] == "valid"
    assert payload["selection"]["selected"] == "s1"
    assert payload["pruned"] == []
    assert output.exists()
    assert run.state.read_bytes() == before


def test_pareto_ranks_mark_the_non_dominated_front(tmp_path):
    value = frontier(tmp_path)
    value["nodes"][1]["expected_gain_range"] = [0.05, 0.1]
    value["nodes"][1]["cost"] = 1.0
    value["nodes"][1]["risk"] = 0.1
    ranked = search.pareto_ranks(value)
    ranks = {candidate["scheme_id"]: candidate["pareto_rank"] for candidate in ranked["nodes"]}
    assert ranks["s2"] == 1
    assert ranked["pareto_size"] >= 1


def test_successive_halving_eliminates_and_keeps_a_rung(tmp_path):
    value = frontier(tmp_path)
    reduced = search.successive_halving(value, keep_ratio=0.5, min_keep=1)
    assert len(reduced["promoted"]) == 3
    assert len(reduced["eliminated"]) == 3
    for candidate in reduced["nodes"]:
        if candidate["scheme_id"] in reduced["eliminated"]:
            assert candidate["status"] == "pruned"
            assert candidate["prune_reason"] == "successive_halving"


def test_mcts_doe_and_tpe_strategies_are_available(tmp_path):
    value = frontier(tmp_path)
    mcts = search.select(value, strategy="mcts")
    assert mcts["selected"] in {candidate["scheme_id"] for candidate in value["nodes"]}
    assert mcts["mcts_iterations"] == 64
    for candidate in value["nodes"]:
        candidate["factors"] = {"tile": 128 if candidate["scheme_id"] in ("s1", "s4") else 64}
    doe = search.select(value, strategy="doe")
    assert doe["doe"] is True
    observations = [
        {"scheme_id": "s1", "score": 0.9, "classification": "improvement"},
        {"scheme_id": "s2", "score": 0.8, "classification": "improvement"},
        {"scheme_id": "s4", "score": 1.1, "classification": "no_improvement"},
        {"scheme_id": "s5", "score": 1.2, "classification": "no_improvement"},
    ]
    tpe = search.select(value, observations=observations, strategy="tpe")
    assert tpe["tpe"] is True
    assert tpe["selected"] in {candidate["scheme_id"] for candidate in value["nodes"]}


def test_frontier_strategy_is_declared_and_validated(tmp_path):
    value = frontier(tmp_path)
    value["strategy"] = "mcts"
    value["strategy_options"] = {"mcts_iterations": 12}
    search.validate_frontier(value)
    assert search.select(value)["strategy"] == "mcts"
    value["strategy"] = "unknown"
    with pytest.raises(ValueError, match="strategy"):
        search.validate_frontier(value)


def test_reanchor_uses_measured_cases(tmp_path):
    value = search.reanchor_targets(
        {
            "cases": [
                {"case_id": "a", "candidate_total_us": 100.0},
                {"case_id": "b", "candidate_total_us": 200.0},
            ]
        },
        {"path": "/abs/effect.json", "sha256": "0" * 64},
    )
    assert value["mode"] == "relative_5pct"
    assert [item["target_total_us"] for item in value["targets"]] == [95.0, 190.0]


def test_opmodel_prefilter_records_applied_and_unsupported(tmp_path):
    import search_prefilter

    value = frontier(tmp_path)
    out_dir = tmp_path / "opmodel"
    command = (
        f'{sys.executable} -c "import pathlib; '
        f"pathlib.Path(r'{{out}}').joinpath('model-result.json').write_text('ok')\""
    )
    record = search_prefilter.run_prefilter(
        value,
        backend="dag_run",
        model=None,
        out_dir=out_dir,
        command=command,
    )
    assert record["status"] == "applied"
    assert record["coverage"] == len(value["nodes"])
    assert any(
        item["path"].endswith("model-result.json") for item in record["evidence"]
    )
    failed = search_prefilter.run_prefilter(
        value,
        backend="dag_run",
        model=None,
        out_dir=tmp_path / "failed",
        command=f'{sys.executable} -c "raise SystemExit(3)"',
    )
    assert failed["status"] == "unsupported"
    assert "exited with 3" in failed["reason"]


def test_zero_gain_candidate_is_pruned_before_selection(tmp_path):
    value = frontier(tmp_path)
    value["nodes"][1]["expected_gain_range"] = [0.0, 0.0]
    with pytest.raises(ValueError, match="below_noise_floor"):
        search.validate_frontier(value)
    pruned = search.prune(value)
    assert any(
        item["scheme_id"] == "s2" and item["prune_reason"] == "below_noise_floor"
        for item in pruned["pruned"]
    )
    search.validate_frontier(pruned)


def test_declarative_candidate_space_expands_to_a_valid_frontier(tmp_path):
    import search_candidates

    source = tmp_path / "baseline"
    source.mkdir()
    (source / "kernel.cpp").write_text("value = 0\n")
    trigger = tmp_path / "diagnosis.txt"
    trigger.write_text("synthetic fixture")
    space = write(
        tmp_path / "space.json",
        {
            "schema_version": 1,
            "axes": [
                {"name": "baseM", "values": [64, 128]},
                {"name": "baseN", "values": [64, 128]},
            ],
            "prior": {"gain": [0.05, 0.2], "cost": 1.0, "risk": 0.1},
        },
    )
    candidate_frontier = search_candidates.build(
        space, source, trigger, "round1", 100.0, 2, 0.5, 64
    )
    search.validate_frontier(candidate_frontier)
    assert len(candidate_frontier["nodes"]) == 5
    assert any(candidate["explore_tag"] == "open" for candidate in candidate_frontier["nodes"])
    assert all("factors" in candidate for candidate in candidate_frontier["nodes"])
    chosen = search.select(candidate_frontier)
    assert chosen["selected"] in {candidate["scheme_id"] for candidate in candidate_frontier["nodes"]}


def test_candidate_source_refs_survive_constraint_pruning(tmp_path):
    import search_candidates

    initial = frontier(tmp_path)
    trigger = initial["nodes"][0]["trigger"][0]
    refs = {
        str(value): [
            search.ref(write(tmp_path / f"source-{value}.json", {"value": value}))
        ]
        for value in (64, 128, 256)
    }
    space = write(
        tmp_path / "space.json",
        {
            "schema_version": 1,
            "axes": [{"name": "tile", "values": [64, 128, 256], "trigger": refs}],
            "constraints": [{"kind": "max", "field": "tile", "value": 128}],
        },
    )
    generated = search_candidates.build(
        space, initial["parent"], trigger["path"], "round1", 100.0, 1, 0.5, 64
    )
    assert [candidate["factors"] for candidate in generated["nodes"]] == [
        {"tile": 64},
        {"tile": 128},
        {},
    ]
    for candidate in generated["nodes"]:
        expected = refs.get(str(candidate["factors"].get("tile")), [])
        assert candidate["trigger"] == [trigger, *expected]
    assert refs["256"][0] in search.validate_frontier(generated)
    Path(refs["256"][0]["path"]).write_text("changed")
    with pytest.raises(ValueError, match="SHA"):
        search.validate_frontier(generated)


@pytest.mark.parametrize(
    ("trigger", "error"),
    [
        ([], "trigger must be an object"),
        ({"missing": []}, "trigger keys must match axis values"),
        ({"64": []}, "trigger needs evidence references"),
        ({"64": {}}, "trigger needs evidence references"),
        ({"64": [{"path": "/missing/source.json", "sha256": "0" * 64}]}, "missing"),
    ],
)
def test_candidate_space_rejects_invalid_source_refs(tmp_path, trigger, error):
    import search_candidates

    space = write(
        tmp_path / "space.json",
        {
            "schema_version": 1,
            "axes": [{"name": "tile", "values": [64], "trigger": trigger}],
        },
    )
    with pytest.raises(ValueError, match=error):
        search_candidates.load_space(space)


def test_candidate_space_bindings_constraints_and_pairwise(tmp_path):
    import search_candidates

    source = tmp_path / "baseline"
    source.mkdir()
    (source / "kernel.cpp").write_text("value = 0\n")
    trigger = tmp_path / "diagnosis.txt"
    trigger.write_text("synthetic fixture")
    space = write(
        tmp_path / "space.json",
        {
            "schema_version": 1,
            "generation": {"method": "pairwise"},
            "axes": [
                {
                    "name": "m",
                    "values": [64, 128, 256],
                    "binding": {"kind": "tiling_field", "field": "baseM"},
                },
                {
                    "name": "n",
                    "values": [64, 128, 256],
                    "binding": {"kind": "tiling_field", "field": "baseN"},
                },
                {
                    "name": "k",
                    "values": [64, 128, 256],
                    "binding": {"kind": "contract_feature", "field": "baseK"},
                },
            ],
            "constraints": [
                {"kind": "divide_by", "field": "m", "value": 64},
                {"kind": "product_max", "fields": ["m", "n"], "value": 65536},
            ],
            "prior": {"gain": [0.05, 0.2], "cost": 1.0, "risk": 0.1},
        },
    )
    candidate_frontier = search_candidates.build(
        space, source, trigger, "round1", 100.0, 3, 0.5, 64
    )
    search.validate_frontier(candidate_frontier)
    tiling = [n for n in candidate_frontier["nodes"] if n["explore_tag"] != "open"]
    assert tiling
    assert all(candidate["bindings"]["m"]["field"] == "baseM" for candidate in tiling)
    assert all(candidate["factors"]["m"] * candidate["factors"]["n"] <= 65536 for candidate in tiling)
    pairs = set()
    for candidate in tiling:
        values = [candidate["factors"][axis] for axis in ("m", "n", "k")]
        for i in range(3):
            for j in range(i + 1, 3):
                pairs.add((i, values[i], j, values[j]))
    axis_pairs = combinations(range(3), 2)
    value_pairs = product((64, 128, 256), repeat=2)
    expected = {(i, a, j, b) for (i, j), (a, b) in product(axis_pairs, value_pairs)}
    assert pairs == expected
    assert len(tiling) < 27


def test_candidate_space_rejects_unknown_binding(tmp_path):
    import search_candidates

    source = tmp_path / "baseline"
    source.mkdir()
    (source / "kernel.cpp").write_text("value = 0\n")
    trigger = tmp_path / "diagnosis.txt"
    trigger.write_text("synthetic fixture")
    space = write(
        tmp_path / "space.json",
        {
            "schema_version": 1,
            "axes": [{"name": "m", "values": [1], "binding": {"kind": "magic"}}],
            "prior": {"gain": [0.05, 0.2], "cost": 1.0, "risk": 0.1},
        },
    )
    with pytest.raises(ValueError, match="binding kind"):
        search_candidates.build(space, source, trigger, "round1", 100.0, 1, 0.5, 64)


def test_axis_priors_break_uniform_ties(tmp_path):
    import search_candidates

    source = tmp_path / "baseline"
    source.mkdir()
    (source / "kernel.cpp").write_text("value = 0\n")
    trigger = tmp_path / "diagnosis.txt"
    trigger.write_text("synthetic fixture")
    space = write(
        tmp_path / "space.json",
        {
            "schema_version": 1,
            "axes": [
                {
                    "name": "m",
                    "values": [64, 128],
                    "prior": {"64": [0.02, 0.08], "128": [0.08, 0.2]},
                },
                {
                    "name": "n",
                    "values": [64, 128],
                    "prior": {"64": [0.02, 0.08], "128": [0.08, 0.2]},
                },
            ],
            "prior": {"gain": [0.02, 0.08], "cost": 1.0, "risk": 0.1},
        },
    )
    candidate_frontier = search_candidates.build(
        space, source, trigger, "round1", 100.0, 2, 0.5, 64
    )
    chosen = search.select(candidate_frontier)
    assert chosen["selected"] == "round1-t-m-128-n-128"
    gains = {
        candidate["scheme_id"]: candidate["expected_gain_range"] for candidate in candidate_frontier["nodes"]
    }
    assert gains["round1-t-m-128-n-128"] == [0.08, 0.2]


@pytest.mark.parametrize(
    "field,node_field",
    [("candidate_factors", "factors"), ("candidate_bindings", "bindings")],
)
def test_frontier_validator_owns_candidate_declaration_checks(
    tmp_path, field, node_field
):
    value = frontier(tmp_path)
    value["nodes"][0][node_field] = (
        {"baseM": 128}
        if field == "candidate_factors"
        else {"baseM": {"kind": "tiling_field", "field": "baseM"}}
    )
    contract = {"scheme_id": "s1", "search": {"parent": value["parent"]}}
    with pytest.raises(ValueError, match=field):
        search.validate_frontier(value, contract)
    contract["search"][field] = value["nodes"][0][node_field]
    search.validate_frontier(value, contract)
    contract["search"][field] = {"baseM": "wrong"}
    with pytest.raises(ValueError, match=field):
        search.validate_frontier(value, contract)


def test_existing_stage_mark_registers_frontier_and_rejects_stale_artifacts(tmp_path):
    run = Run(tmp_path)
    _, path = attached_frontier(run, frontier(tmp_path))
    assert run.cli("verify")["status"] == "valid"
    state = search.load(run.state)
    events = [e for e in state["events"] if e.get("kind") == "search_frontier"]
    assert len(events) == 1
    assert search.ref(path) in events[0]["artifacts"]
    path.write_text(path.read_text() + " ")
    result = run.cli("verify", ok=False)
    assert result["status"] != "valid"
