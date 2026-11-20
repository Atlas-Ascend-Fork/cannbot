# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Installed CLI simulations with synthetic build and performance evidence.

Unlike isolated adapter tests, each generated frontier is frozen, consumed by
implementation, and completed through the real workflow state machine.
"""

import json
import subprocess
import sys

import pytest

import test_search_policy as fixtures
import test_search_installed as installations

installed_search = installations.installed_search


class Simulation:
    def __init__(self, installed, root, monkeypatch, **kwargs):
        self.installed = installed
        monkeypatch.setattr(fixtures, "SCRIPTS", installed["scripts"])
        self.run = fixtures.Run(root, **kwargs)
        self.trace = []
        self.last_checkpoint = None

    def cli(self, script, *args, ok=True):
        result = subprocess.run(
            [sys.executable, str(self.installed["scripts"] / script), *map(str, args)],
            cwd=self.installed["cwd"],
            env=self.installed["env"],
            text=True,
            capture_output=True,
            timeout=30,
        )
        self.trace.append(
            {"script": script, "args": list(map(str, args)), "stdout": result.stdout}
        )
        fixtures.write(self.run.root / "simulation-transcript.json", self.trace)
        assert (result.returncode == 0) == ok, result.stdout + result.stderr
        return json.loads(result.stdout)

    def plan(self, number, *, depends=(), retry=None, combo_stage="auto", axes=None):
        run = self.run
        folder = run.root / run.round(number)
        axes = fixtures.write(
            folder / "axes.json",
            {
                "schema_version": 1,
                "kind": "local" if depends else "architecture",
                "level": "M1" if depends else "M0",
                "mechanism": "tile-search",
                "depends_on": list(depends),
                "axes": axes
                if axes is not None
                else [
                    {"name": "tile", "values": [64, 128, 256]},
                    {"name": "buffers", "values": [1, 2]},
                ],
                "prior": {"gain": [0.05, 0.2], "cost": 1.0, "risk": 0.1},
            },
        )
        knowledge = fixtures.write(
            folder / "knowledge.json",
            {
                "target_socs": ["Ascend950"],
                "evidence": [fixtures.search.ref(run.evidence)],
            },
        )
        space = folder / "candidate-space.json"
        self.cli(
            "search_kb_space.py",
            "--space",
            axes,
            "--knowledge",
            knowledge,
            "--manifest",
            run.manifest,
            "--out",
            space,
        )
        planned = self.cli(
            "search_round.py",
            "--state",
            run.state,
            "--space",
            space,
            "--parent",
            run.source,
            "--trigger",
            run.evidence,
            "--round",
            run.round(number),
            "--best-us",
            100,
            "--history-state",
            run.state,
            "--soc",
            "Ascend950",
            "--combo-stage",
            combo_stage,
            "--out-dir",
            folder / "plan",
            "--dry-run",
        )
        frontier = fixtures.search.load(planned["frontier"])
        # Re-evaluate the same factors in both rounds. The accepted first
        # implementation is a different parent for the second decision.
        node = frontier["nodes"][0]
        scheme = node["scheme_id"]
        original = run.plan(number, depends=depends, retry=retry, register=False)
        contract = fixtures.search.load(original)
        contract["scheme_id"] = scheme
        contract["search"].update(
            kind=node["kind"],
            mechanism=node["mechanism"],
            frontier_parent=scheme,
            fidelity=node["fidelity"],
            expected_gain_range=node["expected_gain_range"],
            cost=node["cost"],
            candidate_factors=node.get("factors", {}),
            candidate_bindings=node.get("bindings", {}),
        )
        contract_path = fixtures.write(
            folder / f"implementation-contract-{scheme}.json", contract
        )
        frontier_path = fixtures.write(
            folder / f"candidate-frontier-{scheme}.json", frontier
        )
        run.cli(
            "mark",
            "--stage",
            run.round(number) + ".analysis",
            "--status",
            "complete",
            "--artifact",
            contract_path,
            "--artifact",
            frontier_path,
        )
        return contract_path, frontier_path

    def complete(self, number, plan, values=(90, 90), selected=True):
        run = self.run
        contract_path, frontier_path = plan
        contract = fixtures.search.load(contract_path)
        folder = contract_path.parent
        args, candidate, kept = run.outcome(
            number, contract_path, values=values, selected=selected
        )
        effect = folder / "effect.json"
        index = fixtures.write(
            folder / "evidence-index.json",
            {
                "schema_version": 1,
                "manifest": fixtures.search.ref(run.manifest),
                "cases": fixtures.search.ref(run.workload),
                "candidates": [
                    {
                        "scheme_id": contract["scheme_id"],
                        "effect_summary": fixtures.search.ref(effect),
                    }
                ],
            },
        )
        original = frontier_path.read_bytes()
        observed = self.cli(
            "search_round.py",
            "--state",
            run.state,
            "--frontier",
            frontier_path,
            "--contract",
            contract_path,
            "--evidence-index",
            index,
            "--attribution",
            "--out-dir",
            folder / "observed",
        )
        assert frontier_path.read_bytes() == original
        attribution = fixtures.search.load(observed["attribution"])
        assert attribution["advisory_only"]
        assert attribution["candidates"][0]["effect_summary"] == fixtures.search.ref(
            effect
        )
        self.cli(
            "search_selection.py",
            "--selection",
            folder / "selection.json",
            "--observations",
            observed["observation"],
            "--scheme-id",
            contract["scheme_id"],
            "--conformance-gate",
            folder / "gate.json",
            "--effect-summary",
            effect,
            "--evidence",
            run.evidence,
            "--retry-condition",
            "new evidence or parent",
            "--replace",
        )
        run.cli("mark", *args)
        self.last_checkpoint = args
        before = [
            e
            for e in fixtures.search.load(run.state)["events"]
            if e["kind"].startswith("search_")
        ]
        run.cli("mark", *args)
        after = [
            e
            for e in fixtures.search.load(run.state)["events"]
            if e["kind"].startswith("search_")
        ]
        assert before == after
        assert run.cli("verify")["status"] == "valid"
        if selected:
            run.source, run.baseline = candidate, kept
        return contract["scheme_id"]


def test_installed_proposal_sources_reach_frontier_and_original_checkpoint(
    installed_search, tmp_path, monkeypatch
):
    simulation = Simulation(installed_search, tmp_path, monkeypatch)
    run = simulation.run
    sources = {
        name: fixtures.search.ref(
            fixtures.write(tmp_path / f"{name}.json", {"synthetic_source": name})
        )
        for name in (
            "knowledge-query",
            "ascendc-performance-best-practices",
            "ascendc-perf-optimize",
            "ops-opmodel-toolkit",
        )
    }
    kb, template, method, model = sources.values()
    routes = {
        "reuse_kb": [kb],
        "pipeline": [template, kb, kb, fixtures.search.ref(run.evidence)],
        "balanced_cores": [method],
        "resident_dag": [model],
        "mapped_dag": [model],
    }
    plan = simulation.plan(
        1,
        axes=[
            {
                "name": "route",
                "values": list(routes),
                "binding": {"kind": "contract_feature", "field": "dataflow_route"},
                "trigger": routes,
            }
        ],
    )
    frontier = fixtures.search.load(plan[1])
    candidates = [node for node in frontier["nodes"] if node["factors"]]
    assert {node["factors"]["route"] for node in candidates} == set(routes)
    for node in frontier["nodes"]:
        expected = routes.get(node["factors"].get("route"), [])
        assert [ref for ref in sources.values() if ref in node["trigger"]] == [
            ref for ref in sources.values() if ref in expected
        ]
        assert all(node["trigger"].count(ref) == 1 for ref in node["trigger"])
    assert frontier["prefilter"]["l1"]["status"] == "unsupported"
    assert not (plan[1].parent / "plan/prefilter.json").exists()
    simulation.complete(1, plan)

    # Even an unselected source is frozen by the existing analysis checkpoint.
    model_path = tmp_path / "ops-opmodel-toolkit.json"
    original = model_path.read_bytes()
    model_path.write_bytes(original + b" ")
    assert run.cli("verify", ok=False)["status"] == "invalid"
    model_path.write_bytes(original)
    run.cli(
        "mark",
        "--stage",
        "round1.analysis",
        "--status",
        "complete",
        "--artifact",
        plan[0],
        "--artifact",
        plan[1],
    )
    assert run.cli("verify")["status"] == "valid"


@pytest.mark.parametrize("mode", ["standard", "generalization"])
@pytest.mark.parametrize("backend", ["ascendc", "cannbot_dsl"])
def test_two_installed_rounds_and_reopened_dependency(
    installed_search, tmp_path, monkeypatch, mode, backend
):
    simulation = Simulation(
        installed_search, tmp_path, monkeypatch, mode=mode, backend=backend
    )
    run = simulation.run
    first = simulation.complete(1, simulation.plan(1))
    second_plan = simulation.plan(2, depends=(first,))
    second = simulation.complete(2, second_plan, values=(80, 80))
    assert first != second
    assert run.view()["accepted_decisions"] == sorted([first, second])
    assert run.view()["stagnation"] == 0

    # Restoration must revalidate the original evidence, not count a new trial.
    summary = second_plan[0].parent / "effect.json"
    original = summary.read_bytes()
    summary.write_bytes(original + b" ")
    assert run.cli("verify", ok=False)["status"] != "valid"
    summary.write_bytes(original)
    run.cli("mark", *simulation.last_checkpoint)
    assert run.cli("verify")["status"] == "valid"

    run.cli(
        "search-replan",
        "--reason",
        "architecture_limit",
        "--reopen",
        first,
        "--evidence",
        run.evidence,
        "--message",
        "synthetic architecture review",
    )
    assert run.view()["reopened_decisions"] == sorted([first, second])
    result = simulation.cli(
        "search_candidates.py",
        "--state",
        run.state,
        "--space",
        second_plan[0].parent / "candidate-space.json",
        "--parent",
        run.source,
        "--trigger",
        run.evidence,
        "--round",
        run.round(3),
        "--best-us",
        80,
        "--out",
        tmp_path / "reopened-frontier.json",
        ok=False,
    )
    assert "unknown frontier dependencies" in result["reason"]
    result = run.cli("search-frontier", "--frontier", second_plan[1], ok=False)
    assert "unknown frontier dependencies" in result["error"]


def test_installed_precision_failure_can_retry_with_new_evidence(
    installed_search, tmp_path, monkeypatch
):
    simulation = Simulation(installed_search, tmp_path, monkeypatch)
    run = simulation.run
    contract, _ = simulation.plan(1)
    scheme = fixtures.search.load(contract)["scheme_id"]
    args, _, _ = run.outcome(1, contract, kind="precision_failed")
    run.cli("mark", *args)
    assert run.view()["next_action"] == "repair_candidate"
    assert run.view()["stagnation"] == 0
    assert not (contract.parent / "effect.json").exists()
    probe = tmp_path / "repair-evidence.txt"
    probe.write_text("synthetic evidence of repaired precision defect")
    retry = {
        "decision_id": scheme,
        "reason": "precision defect repaired",
        "evidence": [fixtures.search.ref(probe)],
    }
    simulation.complete(2, simulation.plan(2, retry=retry))
    assert run.view()["stagnation"] == 0


def test_installed_slow_implementation_can_be_refined_and_promoted(
    installed_search, tmp_path, monkeypatch
):
    simulation = Simulation(installed_search, tmp_path, monkeypatch)
    run = simulation.run
    first_plan = simulation.plan(1, combo_stage="-1")
    first = simulation.complete(1, first_plan, values=(120, 120), selected=False)
    report = fixtures.search.load(first_plan[0].parent / "observed/attribution.json")
    assert report["counts"] == {"implementation_imperfect": 1}
    assert run.view()["accepted_decisions"] == []
    probe = tmp_path / "cost-probe.txt"
    probe.write_text("synthetic probe identifies avoidable implementation overhead")
    retry = {
        "decision_id": first,
        "reason": "remove measured overhead",
        "evidence": [fixtures.search.ref(probe)],
    }
    second_plan = simulation.plan(2, retry=retry, combo_stage="-1")
    old = fixtures.search.load(first_plan[0])["search"]
    new = fixtures.search.load(second_plan[0])["search"]
    assert old["candidate_factors"] == new["candidate_factors"]
    assert old["mechanism"] == new["mechanism"]
    acquisition = fixtures.search.load(second_plan[0].parent / "plan/acquisition.json")
    assert acquisition["history"] and acquisition["ranking"]
    second = simulation.complete(2, second_plan, values=(80, 80), selected=True)
    assert run.view()["accepted_decisions"] == [second]
    assert run.view()["stagnation"] == 0


@pytest.mark.parametrize("outcome", ["measured", "precision_failed"])
def test_installed_coverage_uses_completed_measurements_and_existing_ledger(
    installed_search, tmp_path, monkeypatch, outcome
):
    simulation = Simulation(installed_search, tmp_path, monkeypatch)
    run = simulation.run
    plan = simulation.plan(1, combo_stage="-1")
    contract, frontier = plan
    report = tmp_path / "coverage.json"

    def audit():
        before = run.state.read_bytes()
        result = run.cli(
            "search-frontier",
            "--frontier",
            frontier,
            "--contract",
            contract,
            "--out",
            report,
        )["axis_coverage"]
        assert run.state.read_bytes() == before
        return result

    generated = audit()
    assert generated["axes"]["tile"] == {"tested": [], "untested": [64, 128, 256]}
    if outcome == "measured":
        scheme = simulation.complete(1, plan, values=(120, 120), selected=False)
    else:
        scheme = fixtures.search.load(contract)["scheme_id"]
        args, _, _ = run.outcome(1, contract, kind=outcome)
        run.cli("mark", *args)
    coverage = audit()
    assert coverage["axes"]["tile"]["tested"] == ([64] if outcome == "measured" else [])
    assert coverage["is_exhaustion_proof"] is False
    assert bool(coverage["evidence"]) == (outcome == "measured")
    rejected = run.cli(
        "search-frontier",
        "--frontier",
        frontier,
        "--contract",
        contract,
        "--no-go",
        ok=False,
    )
    assert "unmeasured" in rejected["error"]
    # Analysis hands the still-open direction to the existing main-agent ledger.
    run.cli(
        "structural-direction",
        "--id",
        "tile-search-256",
        "--status",
        "not_attempted",
        "--description",
        "unmeasured tile=256",
        "--evidence",
        report,
    )
    entry = fixtures.search.load(run.state)["structural_directions"][0]
    assert entry["id"] == "tile-search-256" and entry["evidence"] == str(report)
    run.cli(
        "search-replan",
        "--reason",
        "architecture_limit",
        "--reopen",
        scheme,
        "--evidence",
        run.evidence,
        "--message",
        "synthetic review reopens this decision",
    )
    assert audit()["axes"]["tile"]["tested"] == []
    space = contract.parent / "candidate-space.json"
    space.write_text(space.read_text() + " ")
    rejected = run.cli(
        "search-frontier", "--frontier", frontier, "--contract", contract, ok=False
    )
    assert "changed" in rejected["error"] or "restore accepted" in rejected["error"]


def test_installed_no_go_requires_measurements_or_frozen_exclusions(
    installed_search, tmp_path, monkeypatch
):
    simulation = Simulation(installed_search, tmp_path, monkeypatch)
    run = simulation.run
    contract, frontier = plan = simulation.plan(1, combo_stage="-1")
    audit_args = ["search-frontier", "--frontier", frontier, "--contract", contract]

    def read_only(*args, ok=False):
        before = run.state.read_bytes()
        result = subprocess.run(
            [
                sys.executable,
                str(installed_search["scripts"] / "workflow_state.py"),
                *map(str, args),
                "--state",
                str(run.state),
            ],
            cwd=installed_search["cwd"],
            env=installed_search["env"],
            text=True,
            capture_output=True,
            timeout=30,
        )
        assert result.returncode == (0 if ok else 2), result.stdout + result.stderr
        assert run.state.read_bytes() == before
        return json.loads(result.stdout)

    # Generation is not measurement, and omitting the direction ledger cannot bypass finish.
    assert "unmeasured" in read_only(*audit_args, "--no-go")["error"]
    for reason in ("no_material_improvement", "ceiling_bound"):
        assert (
            "unmeasured"
            in read_only(
                "finish",
                "--status",
                "success",
                "--reason-code",
                reason,
                "--message",
                "no-go",
            )["error"]
        )

    simulation.complete(1, plan, values=(120, 120), selected=False)
    coverage = read_only(*audit_args, ok=True)["axis_coverage"]
    assert coverage["axes"]["tile"]["tested"] == [64]
    directions = coverage["untested_directions"]
    proof = tmp_path / "exclusion.md"
    first = [
        "structural-direction",
        "--id",
        directions[0]["id"],
        "--status",
        "infeasible_evidenced",
    ]
    read_only(*first)  # A bare exclusion status is insufficient.
    proof.touch()
    read_only(*first, "--evidence", proof)  # Nor is an empty proof file.
    proof.write_text("Synthetic exclusion rationale for the declared axis values.\n")
    for direction in directions:
        run.cli(
            "structural-direction",
            "--id",
            direction["id"],
            "--status",
            "infeasible_evidenced",
            "--evidence",
            proof,
        )
    assert read_only(*audit_args, "--no-go", ok=True)["status"] == "valid"

    original = proof.read_bytes()
    proof.write_bytes(original + b"changed")
    invalid = run.cli("verify", ok=False)
    assert any(item["kind"] == "search_exclusion" for item in invalid["invalid"])
    assert "SHA" in read_only(*audit_args, "--no-go")["error"]
    assert (
        "SHA"
        in read_only(
            "finish",
            "--status",
            "blocked",
            "--reason-code",
            "ceiling_bound",
            "--message",
            "no-go",
        )["error"]
    )
    proof.unlink()
    assert run.cli("verify", ok=False)["status"] == "invalid"
    read_only(*audit_args, "--no-go")
    proof.write_bytes(original)
    assert run.cli("verify")["status"] == "valid"
    result = run.cli(
        "finish",
        "--status",
        "success",
        "--reason-code",
        "ceiling_bound",
        "--message",
        "scoped axis audit passed; not a combination exhaustion proof",
    )
    assert result["status"] == "success"


def test_installed_no_go_audits_earlier_spaces_but_allows_budget_exit(
    installed_search, tmp_path, monkeypatch
):
    simulation = Simulation(installed_search, tmp_path, monkeypatch)
    run = simulation.run
    plans, coverages = [], []
    for number in (1, 2):
        contract, frontier = plan = simulation.plan(number, combo_stage="-1")
        simulation.complete(number, plan, values=(100 - number * 10,) * 2)
        plans.append(plan)
        coverages.append(
            run.cli(
                "search-frontier",
                "--frontier",
                frontier,
                "--contract",
                contract,
            )["axis_coverage"]
        )
    old_ids = {item["id"] for item in coverages[0]["untested_directions"]}
    new_ids = {item["id"] for item in coverages[1]["untested_directions"]}
    assert old_ids.isdisjoint(new_ids)  # A changed parent cannot reuse old exclusions.
    proof = tmp_path / "second-parent-exclusion.md"
    proof.write_text("Synthetic rationale applicable only to the second parent.\n")
    for direction in coverages[1]["untested_directions"]:
        run.cli(
            "structural-direction",
            "--id",
            direction["id"],
            "--status",
            "blocked_by_precision",
            "--evidence",
            proof,
        )
    run.cli(
        "search-frontier",
        "--frontier",
        plans[1][1],
        "--contract",
        plans[1][0],
        "--no-go",
    )
    before = run.state.read_bytes()
    rejected = run.cli(
        "finish",
        "--status",
        "success",
        "--reason-code",
        "no_material_improvement",
        "--message",
        "no-go",
        ok=False,
    )
    assert "unmeasured" in rejected["error"]
    assert run.state.read_bytes() == before
    # Exhausting a fixed budget is allowed without claiming the space is exhausted.
    run.cli(
        "finish",
        "--status",
        "awaiting_operator",
        "--reason-code",
        "structural_headroom_unrealized",
        "--message",
        "budget used",
    )
    run.cli(
        "finish",
        "--status",
        "success",
        "--reason-code",
        "completed",
        "--message",
        "fixed rounds completed; untested directions remain",
    )


def test_no_go_without_candidate_space_cannot_silently_pass(tmp_path):
    run = fixtures.Run(tmp_path)
    run.plan(1)
    rejected = run.cli(
        "finish",
        "--status",
        "blocked",
        "--reason-code",
        "ceiling_bound",
        "--message",
        "no-go",
        ok=False,
    )
    assert "candidate space" in rejected["error"]


def test_no_go_legacy_frontier_without_space_receipt_is_unavailable(tmp_path):
    from test_search_frontier import attached_frontier, frontier

    run = fixtures.Run(tmp_path)
    contract, path = attached_frontier(run, frontier(tmp_path))
    before = run.state.read_bytes()
    rejected = run.cli(
        "search-frontier",
        "--frontier",
        path,
        "--contract",
        contract,
        "--no-go",
        ok=False,
    )
    assert "candidate-space coverage" in rejected["error"]
    assert run.state.read_bytes() == before


@pytest.mark.parametrize("invalid_axes", [[], [{"name": "radix", "values": []}]])
def test_installed_no_go_rejects_empty_space_even_with_no_pending_items(
    installed_search, tmp_path, monkeypatch, invalid_axes
):
    run = Simulation(installed_search, tmp_path, monkeypatch).run
    space = fixtures.write(
        tmp_path / "space.json",
        {
            "schema_version": 1,
            "mechanism": "fft",
            "axes": invalid_axes,
        },
    )
    frontier = fixtures.write(
        tmp_path / "candidate-frontier-audit.json",
        {
            "schema_version": 1,
            "round": run.round(1),
            "nodes": [],
            "parent": fixtures.search.source_identity(run.source),
            "candidate_space": fixtures.search.ref(space),
            "workload": fixtures.search.ref(run.workload),
        },
    )
    before = run.state.read_bytes()
    rejected = run.cli(
        "search-frontier",
        "--frontier",
        frontier,
        "--no-go",
        ok=False,
    )
    expected = "values are required" if invalid_axes else "candidate space needs axes"
    assert expected in rejected["error"]
    run.cli(
        "mark",
        "--stage",
        run.round(1) + ".analysis",
        "--status",
        "complete",
        "--artifact",
        frontier,
        ok=False,
    )
    assert run.state.read_bytes() == before


def test_installed_no_go_audits_all_pruned_nodes_without_relaxing_selection(
    installed_search, tmp_path, monkeypatch
):
    simulation = Simulation(installed_search, tmp_path, monkeypatch)
    run = simulation.run
    contract, path = simulation.plan(1, combo_stage="-1")
    frontier = fixtures.search.load(path)
    for node in frontier["nodes"]:
        node.update(status="pruned", prune_reason="manual")
    path = fixtures.write(tmp_path / "all-pruned.json", frontier)
    before = run.state.read_bytes()
    report = run.cli(
        "search-frontier",
        "--frontier",
        path,
        "--contract",
        contract,
        "--no-go",
        ok=False,
    )
    assert report["status"] == "blocked" and "unmeasured" in report["error"]
    assert run.state.read_bytes() == before
    for item in report["axis_coverage"]["untested_directions"]:
        run.cli(
            "structural-direction",
            "--id",
            item["id"],
            "--status",
            "infeasible_evidenced",
            "--evidence",
            run.evidence,
        )
    before = run.state.read_bytes()
    assert (
        run.cli(
            "search-frontier", "--frontier", path, "--contract", contract, "--no-go"
        )["status"]
        == "valid"
    )
    assert (
        "after pruning"
        in run.cli(
            "search-frontier", "--frontier", path, "--contract", contract, ok=False
        )["error"]
    )
    assert run.state.read_bytes() == before


@pytest.mark.parametrize("mode", ["standard", "generalization"])
def test_installed_analysis_only_no_go_uses_existing_checkpoint(
    installed_search, tmp_path, monkeypatch, mode
):
    run = Simulation(installed_search, tmp_path, monkeypatch, mode=mode).run
    space = fixtures.write(
        tmp_path / "space.json",
        {
            "schema_version": 1,
            "mechanism": "fft",
            "axes": [{"name": "radix", "values": [4, 8]}],
        },
    )
    path = fixtures.write(
        tmp_path / "candidate-frontier-audit.json",
        {
            "schema_version": 1,
            "round": run.round(1),
            "nodes": [],
            "parent": fixtures.search.source_identity(run.source),
            "candidate_space": fixtures.search.ref(space),
            "workload": fixtures.search.ref(run.workload),
        },
    )
    output = tmp_path / "audit.json"
    before = run.state.read_bytes()
    outside = tmp_path / "outside.csv"
    outside.write_text("case_id\nnot-in-frozen-inventory\n")
    invalid = fixtures.write(
        tmp_path / "candidate-frontier-invalid.json",
        {
            **fixtures.search.load(path),
            "workload": fixtures.search.ref(outside),
        },
    )
    assert (
        "escapes frozen inventory"
        in run.cli(
            "mark",
            "--stage",
            run.round(1) + ".analysis",
            "--status",
            "complete",
            "--artifact",
            invalid,
            ok=False,
        )["error"]
    )
    report = run.cli(
        "search-frontier", "--frontier", path, "--no-go", "--out", output, ok=False
    )
    assert report == fixtures.search.load(output)
    assert report["axis_coverage"]["axes"]["radix"] == {
        "tested": [],
        "untested": [4, 8],
    }
    assert run.state.read_bytes() == before
    assert (
        "registered candidate space"
        in run.cli(
            "finish",
            "--status",
            "success",
            "--reason-code",
            "ceiling_bound",
            "--message",
            "unregistered audit",
            ok=False,
        )["error"]
    )
    checkpoint = [
        "mark",
        "--stage",
        run.round(1) + ".analysis",
        "--status",
        "complete",
        "--artifact",
        path,
    ]
    run.cli(*checkpoint)
    state = fixtures.search.load(run.state)
    assert not any(e["kind"] == "search_plan" for e in state["events"])
    assert run.view()["frontier"]["selected"] is None
    assert (
        "unmeasured"
        in run.cli(
            "finish",
            "--status",
            "success",
            "--reason-code",
            "ceiling_bound",
            "--message",
            "no-go",
            ok=False,
        )["error"]
    )
    for item in report["axis_coverage"]["untested_directions"]:
        run.cli(
            "structural-direction",
            "--id",
            item["id"],
            "--status",
            "infeasible_evidenced",
            "--evidence",
            run.evidence,
        )
    assert (
        run.cli("search-frontier", "--frontier", path, "--no-go")["status"] == "valid"
    )
    run.cli("mark", "--stage", run.round(1) + ".analysis", "--status", "invalid")
    assert (
        "search acceptance invalidated"
        in run.cli(
            "finish",
            "--status",
            "success",
            "--reason-code",
            "ceiling_bound",
            "--message",
            "invalidated audit",
            ok=False,
        )["error"]
    )
    run.cli(*checkpoint)
    args, _, _ = run.outcome(1, None, kind="no_candidate")
    run.cli("mark", *args)
    run.cli(
        *checkpoint
    )  # Re-registering the same audit after round completion is idempotent.
    state = fixtures.search.load(run.state)
    assert sum(e["kind"] == "search_frontier" for e in state["events"]) == 1
    assert run.view()["stagnation"] == 0
    assert run.cli("verify")["status"] == "valid"
    run.cli(
        "finish",
        "--status",
        "success",
        "--reason-code",
        "ceiling_bound",
        "--message",
        "analysis-only audit passed",
    )
    # Registration retains the input receipt, not just a copied coverage verdict.
    space.write_text(space.read_text() + " ")
    assert run.cli("verify", ok=False)["status"] == "invalid"
    run.cli(
        "finish",
        "--status",
        "success",
        "--reason-code",
        "ceiling_bound",
        "--message",
        "stale audit",
        ok=False,
    )
