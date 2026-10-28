# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""CPU-only contract fixtures: these are not generated-code/hardware proofs."""
from __future__ import annotations
import copy
import importlib.util
import json
import shutil
import subprocess
import sys
from collections import namedtuple
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "ops-perf-optimize-workflow" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import validate_schedule_contract as schedule
import workflow_state as workflow


def write(path, value):
    path.write_text(json.dumps(value, indent=2))
    return path


ContractFixture = namedtuple("ContractFixture", ["cp", "manifest", "ep", "contract", "evidence", "candidate"])


def _fixture_tasks(evidence):
    tasks = []
    for tid, resource, reads, writes in [
        ("load0", "dma", [], [(0, "all")]),
        ("read0", "compute", [(0, "all")], []),
        ("load1", "dma", [], [(1, "all")]),
        ("read1", "compute", [(1, "all")], []),
    ]:
        tasks.append({"id": tid, "program": "P", "resource": resource,
                      "coordinates": {"query": 0, "tile": int(tid[-1]), "subtile": 0},
                      "branches": ["full"], "source": [evidence], "completion_event": tid + "_done",
                      "reads": [{"buffer": "B", "view": v, "generation": g} for g, v in reads],
                      "writes": [{"buffer": "B", "view": v, "generation": g} for g, v in writes]})
    return tasks


def fixture(tmp_path):
    source = tmp_path / "source.cpp"
    source.write_text("// source review fixture, not hardware evidence\n")
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "kernel.cpp").write_text("// candidate\n")
    evidence = schedule.ref(source)
    cases = tmp_path / "cases.csv"
    cases.write_text("case_id,shape\ncase1,1\n")
    manifest = write(tmp_path / "manifest.json", {
        "configuration": {"schedule_policy": schedule.POLICY, "target_socs": ["Ascend950"],
                          "precision_diagnosis_policy": "persistent"},
        "inputs": {}, "collections": {"performance_tuning": schedule.ref(cases)}})
    tasks = _fixture_tasks(evidence)

    def edge(a, b, kind):
        return {"from": a, "to": b, "kind": kind, "from_phase": "complete", "to_phase": "start", "source": [evidence]}
    c = {"schema_version": 1, "kind": "schedule-contract", "scheme_id": "s1", "candidate_root": str(candidate),
         "scope": {"collection": "performance_tuning", "target_socs": ["Ascend950"], "case_ids": ["case1"],
                   "description": "one expanded wraparound fixture"},
         "identities": {k: evidence for k in ("baseline", "reference", "model", "compiler", "workload")},
         "applicability": {"required": True, "reason": "async buffer reuse", "evidence": [evidence],
                           "features": {"cross_tile": True, "multi_engine": True, "async_reuse": True}},
         "model": {"version": "finite-expanded-v1",
                   "boundaries": ["one finite branch; no hardware semantics certified"]},
         "coverage_review": {"complete": True, "evidence": [evidence], "blocking_issue_review": [evidence]},
         "unknowns": [],
         "tasks": tasks, "resources": [{"id": r, "mode": "exclusive"} for r in ("dma", "compute")],
         "programs": [{"id": "P", "submission_order": [t["id"] for t in tasks]}],
         "edges": [edge("load0", "read0", "data"), edge("read0", "load1", "reuse"), edge("load1", "read1", "data"),
                   edge("load0", "load1", "resource"), edge("read0", "read1", "resource")],
         "buffers": [{"id": "B", "memory": "L1", "bytes": 128, "depth": 1, "alignment": 32,
                      "initial_generations": [], "views": [{"id": "all", "offset": 0, "bytes": 128}],
                      "initialization": "load0", "drain": "read1"}], "capacities": {"L1": 128},
         "branches": [{"id": "full", "predicate": "valid tile", "case_ids": ["case1"]}], "events": []}
    cp = write(tmp_path / "schedule-contract-s1.json", c)
    lowering_keys = ("generated_code", "build", "task_mapping", "event_mapping", "last_reader_review")
    e = {"schema_version": 1, "contract": schedule.ref(cp), "manifest": schedule.ref(manifest),
         "candidate": schedule.source_identity(candidate), "scope": c["scope"], "compiler": evidence,
         "lowering": {"status": "pass", **{k: [evidence] for k in lowering_keys}},
         "runtime": {"status": "pass", "covered_branches": ["full"],
                     "coverage": [{"case_id": "case1", "target_soc": "Ascend950", "branch": "full",
                                   "evidence": [evidence]}],
                     **{k: [evidence] for k in ("load", "execution", "precision", "sequence_stress")}}}
    ep = write(tmp_path / "schedule-evidence-s1.json", e)
    return ContractFixture(cp, manifest, ep, c, e, candidate)


def build(tmp_path, mutate=None, level="model"):
    cp, manifest, ep, c, e, candidate = fixture(tmp_path)
    if mutate:
        mutate(c)
        write(cp, c)
        e["contract"] = schedule.ref(cp)
        write(ep, e)
    return schedule.build_report(cp, manifest, level, ep if level != "model" else None)


def test_model_lowering_runtime_distinct(tmp_path):
    cp, manifest, ep, _, _, candidate = fixture(tmp_path)
    for level, status in [("model", "ready_for_implementation"), ("lowering", "lowering_verified"),
                          ("runtime", "eligible")]:
        report = schedule.build_report(cp, manifest, level, ep if level != "model" else None)
        assert report["status"] == status
        gate = write(tmp_path / (level + ".json"), report)
        assert schedule.verify_report(gate, manifest, level, candidate) == report
    with pytest.raises(ValueError, match="runtime evidence"):
        schedule.verify_report(tmp_path / "model.json", manifest, "runtime", candidate)


@pytest.mark.parametrize("mutation,expected", [
    (lambda c: c["edges"].pop(1), "reuse before last"),
    (lambda c: c["edges"].pop(0), "data producer"),
    (lambda c: c["capacities"].update(L1=127), "capacity exceeded"),
    (lambda c: c["edges"][0].update(from_phase="submit"), "completion -> start"),
    (lambda c: c["edges"].append({**c["edges"][0], "from": "read1", "to": "load0"}), "cycle"),
    (lambda c: c["programs"][0]["submission_order"].pop(), "every task exactly once"),
    (lambda c: c["buffers"][0]["views"][0].update(bytes=256), "view exceeds"),
])
def test_graph_and_lifecycle_rejections(tmp_path, mutation, expected):
    report = build(tmp_path, mutation)
    assert report["status"] == "MODEL_REJECTED"
    assert any(expected in error for error in report["errors"]), report


def test_submission_is_not_completion(tmp_path):
    report = build(tmp_path, lambda c: c.update(edges=[]))
    assert report["status"] == "MODEL_REJECTED"
    assert "resource FIFO" in report["errors"][0]


def test_alias_last_reader_in_other_program(tmp_path):
    def mutate(c):
        read = copy.deepcopy(c["tasks"][1])
        read.update(id="aiv1read", program="AIV1", resource="vector1")
        c["tasks"].append(read)
        c["resources"].append({"id": "vector1", "mode": "exclusive"})
        c["programs"].append({"id": "AIV1", "submission_order": ["aiv1read"]})
        c["buffers"][0]["views"].append({"id": "alias", "offset": 64, "bytes": 64})
        read["reads"][0]["view"] = "alias"
        c["edges"].append({**c["edges"][0], "to": "aiv1read"})
    report = build(tmp_path, mutate)
    assert report["status"] == "MODEL_REJECTED"
    assert "reuse before last" in report["errors"][0]


def event(c):
    return {"id": "e", "hardware_id": "event0", "generation": 0, "initial_tokens": 0,
            "drain_tokens": 0, "source": c["applicability"]["evidence"],
            "publishes": [{"task": "load0", "pipe": "dma", "tokens": 1}],
            "waits": [{"task": "read0", "pipe": "compute", "tokens": 1}]}


def test_events_balanced(tmp_path):
    assert build(tmp_path, lambda c: c.update(events=[event(c)]))["decision"] == "pass"


@pytest.mark.parametrize("mutation,expected", [
    (lambda e: e.update(publishes=[]), "token imbalance"),
    (lambda e: e["waits"][0].update(pipe="dma"), "pipe mismatch"),
    (lambda e: e["publishes"][0].update(task="read1", pipe="compute"), "cycle"),
])
def test_event_rejections(tmp_path, mutation, expected):
    def change(c):
        ev = event(c)
        mutation(ev)
        c["events"] = [ev]
    report = build(tmp_path, change)
    assert report["status"] == "MODEL_REJECTED"
    assert expected in report["errors"][0]


def test_branch_missing_publish(tmp_path):
    def change(c):
        c["branches"].append({"id": "tail", "predicate": "tail", "case_ids": ["case1"]})
        c["tasks"][1]["branches"].append("tail")
        c["events"] = [event(c)]
    assert "token imbalance" in build(tmp_path, change)["errors"][0]


@pytest.mark.parametrize("kind,status", [("safety", "needs_probe"), ("performance", "ready_for_implementation")])
def test_unknowns_are_not_conflated(tmp_path, kind, status):
    report = build(tmp_path, lambda c: c["unknowns"].append(
        {"kind": kind, "question": "unknown fact", "status": "open"}))
    assert report["status"] == status


def test_model_feasible_not_eligible(tmp_path):
    cp, manifest, ep, c, e, _ = fixture(tmp_path)
    c["coverage_review"]["complete"] = False
    write(cp, c)
    assert schedule.build_report(cp, manifest)["status"] == "MODEL_FEASIBLE"
    with pytest.raises(ValueError, match="reviewed model"):
        schedule.build_report(cp, manifest, "runtime", ep)


def test_false_applicability_requires_evidence_and_trigger_facts(tmp_path):
    cp, manifest, _, c, _, _ = fixture(tmp_path)
    c["applicability"]["required"] = False
    write(cp, c)
    with pytest.raises(ValueError, match="contradicts"):
        schedule.build_report(cp, manifest)
    c["applicability"]["features"] = dict.fromkeys(c["applicability"]["features"], False)
    c["applicability"]["evidence"] = []
    write(cp, c)
    with pytest.raises(ValueError, match="evidence references"):
        schedule.build_report(cp, manifest)


@pytest.mark.parametrize("change", ["source", "model", "compiler", "contract", "manifest", "runtime"])
def test_recovery_binds_all_evidence(tmp_path, change):
    cp, manifest, ep, c, e, candidate = fixture(tmp_path)
    gate = write(tmp_path / "gate.json", schedule.build_report(cp, manifest, "runtime", ep))
    before = gate.read_bytes()
    changed = {"source": candidate / "kernel.cpp", "model": Path(c["identities"]["model"]["path"]),
               "compiler": Path(c["identities"]["compiler"]["path"]), "contract": cp,
               "manifest": manifest, "runtime": ep}[change]
    changed.write_text(changed.read_text() + "\n ")
    with pytest.raises(ValueError):
        schedule.verify_report(gate, manifest, "runtime")
    assert gate.read_bytes() == before


def test_runtime_pass_without_files_rejected(tmp_path):
    cp, manifest, ep, _, e, _ = fixture(tmp_path)
    e["runtime"]["precision"] = []
    write(ep, e)
    with pytest.raises(ValueError, match="runtime.precision"):
        schedule.build_report(cp, manifest, "runtime", ep)


def test_wrong_candidate_rejected(tmp_path):
    cp, manifest, ep, _, _, _ = fixture(tmp_path)
    other = tmp_path / "other"
    other.mkdir()
    with pytest.raises(ValueError, match="candidate identity mismatch"):
        schedule.build_report(cp, manifest, "runtime", ep, other)


def implementation_contract(c, cp, gate):
    return {"schema_version": 3, "scheme_id": c["scheme_id"], "implementation_mode": "exact",
            "substitution_policy": "forbidden", "target_socs": ["Ascend950"],
            "safety": {"public_contract": "unchanged", "non_target_socs": "unchanged"},
            "expectations": {"vf": False, "casttrait": False},
            "required_features": [{"id": "schedule", "description": "scheduled buffer reuse"}],
            "schedule": {"contract": schedule.ref(cp), "check": schedule.ref(gate)}}


def test_analysis_gate_all_rounds_and_missing(tmp_path):
    cp, manifest, ep, c, e, _ = fixture(tmp_path)
    gate = write(tmp_path / "model.json", schedule.build_report(cp, manifest))
    impl = write(tmp_path / "implementation-contract-s1.json", implementation_contract(c, cp, gate))
    for stage in ("phase.analysis", "round1.analysis", "round2.analysis", "gen.round3.analysis"):
        assert workflow.schedule_stage_kind(stage) == "model"
        paths = workflow.check_schedule_artifacts("model", [str(impl)], manifest)
        assert str(cp) in paths and str(gate) in paths
        with pytest.raises(ValueError, match="bound contract"):
            workflow.check_schedule_artifacts("model", [], manifest)
    with pytest.raises(ValueError, match="bound contract"):
        workflow.check_schedule_artifacts("runtime", [str(gate)], manifest)


def test_legacy_policy_and_unknown_or_null_policy(tmp_path):
    manifest = write(tmp_path / "manifest.json", {"configuration": {"target_socs": ["Ascend950"],
        "precision_diagnosis_policy": "persistent"}, "inputs": {}, "collections": {}})
    assert workflow.check_schedule_artifacts("runtime", [], manifest) == []
    assert schedule.validate_implementation_schedule({}, {}, manifest, tmp_path) is None
    for value in (None, {"id": "skip", "version": 1}):
        with pytest.raises(ValueError, match="unsupported"):
            schedule.policy_enabled({"configuration": {"schedule_policy": value}})


def test_noop_reuses_gate_only_with_same_identity(tmp_path):
    cp, manifest, ep, c, e, candidate = fixture(tmp_path)
    c["applicability"].update(required=False,
                              features=dict.fromkeys(c["applicability"]["features"], False),
                              reason="reviewed local no-op")
    write(cp, c)
    e["contract"] = schedule.ref(cp)
    write(ep, e)
    gate = write(tmp_path / "gate.json", schedule.build_report(cp, manifest, "runtime", ep))
    assert schedule.verify_report(gate, manifest, "runtime", candidate)["status"] == "eligible"
    (candidate / "kernel.cpp").write_text("// changed\n")
    with pytest.raises(ValueError, match="source SHA"):
        schedule.verify_report(gate, manifest, "runtime", candidate)


def test_cli_verify_readonly(tmp_path):
    cp, manifest, ep, _, _, _ = fixture(tmp_path)
    gate = tmp_path / "gate.json"
    command = ["timeout", "30s", sys.executable, str(SCRIPTS / "validate_schedule_contract.py"),
               "--contract", str(cp), "--manifest", str(manifest), "--level", "runtime", "--evidence", str(ep)]
    result = subprocess.run(command + ["--out", str(gate)], capture_output=True, text=True, timeout=35)
    assert result.returncode == 0, result.stdout + result.stderr
    before = gate.read_bytes()
    result = subprocess.run(command + ["--verify-existing", str(gate)], capture_output=True, text=True, timeout=35)
    assert result.returncode == 0, result.stdout + result.stderr
    assert gate.read_bytes() == before


def test_reference_absence_is_explicit(tmp_path):
    cp, manifest, _, c, _, _ = fixture(tmp_path)
    c["identities"]["reference"] = None
    write(cp, c)
    with pytest.raises(ValueError, match="explicit reason"):
        schedule.build_report(cp, manifest)
    c["reference_absence_reason"] = "No reference implementation supplied"
    write(cp, c)
    assert schedule.build_report(cp, manifest)["status"] == "ready_for_implementation"


@pytest.mark.parametrize("case_ids", [["invented"], ["case1", "invented"], []])
def test_scope_must_match_frozen_collection(tmp_path, case_ids):
    cp, manifest, _, c, _, _ = fixture(tmp_path)
    c["scope"]["case_ids"] = case_ids
    write(cp, c)
    with pytest.raises(ValueError, match="case_ids"):
        schedule.build_report(cp, manifest)


def test_request_policy_cannot_be_downgraded_on_fresh_state(tmp_path):
    cp, manifest, _, c, _, _ = fixture(tmp_path)
    request = write(tmp_path / "request.json", {"schedule_policy": schedule.POLICY})
    value = schedule.load(manifest)
    value["request"] = schedule.ref(request)
    value["configuration"].pop("schedule_policy")
    write(manifest, value)
    with pytest.raises(ValueError, match="differs from frozen request"):
        workflow.read_manifest(manifest)
    result = subprocess.run([shutil.which("timeout"), "30s", sys.executable,
                             str(SCRIPTS / "workflow_state.py"), "start",
                             "--state", str(tmp_path / "state.json"), "--manifest", str(manifest)],
                            capture_output=True, text=True, timeout=35)
    assert result.returncode != 0 and "differs from frozen request" in result.stdout + result.stderr
    assert not (tmp_path / "state.json").exists()


def test_boolean_policy_version_rejected():
    with pytest.raises(ValueError, match="unsupported"):
        schedule.policy_enabled({"configuration": {"schedule_policy": {"id": "schedule_contract_v1", "version": True}}})


def test_resource_fifo_cannot_reverse_program_submission(tmp_path):
    def change(c):
        c["tasks"] = c["tasks"][:2]
        for t in c["tasks"]:
            t.update(reads=[], writes=[], resource="dma")
        c["programs"][0]["submission_order"] = ["load0", "read0"]
        c["edges"] = [{**c["edges"][0], "from": "read0", "to": "load0", "kind": "resource"}]
    report = build(tmp_path, change)
    assert report["status"] == "MODEL_REJECTED"
    assert "FIFO contradicts" in report["errors"][0]


def full_gate(tmp_path, integrated=False):
    """A complete conformance CLI fixture, including original source isolation."""
    from validate_source_isolation import snapshot
    cp, manifest, ep, c, e, candidate = fixture(tmp_path)
    baseline = tmp_path / "baseline"
    shutil.copytree(candidate, baseline)
    (candidate / "compile.json").write_text("{}\n")
    if integrated:
        integration_evidence(tmp_path, cp, manifest, ep, c, e, candidate)
    model = write(tmp_path / "model.json", schedule.build_report(cp, manifest))
    runtime = write(tmp_path / "runtime.json", schedule.build_report(cp, manifest, "runtime", ep))
    impl = write(tmp_path / "implementation-contract-s1.json", implementation_contract(c, cp, model))
    (candidate / "compile.json").write_text("{}\n")
    result = write(tmp_path / "result.json", {
        "schema_version": 3, "scheme_id": "s1", "implementation_status": "complete",
        "route_changed": False, "substitution_used": False,
        "features": {"schedule": {"status": "pass", "source_locations": ["kernel.cpp:1"],
                                  "evidence_files": ["compile.json"]}},
        "schedule": {"check": schedule.ref(runtime)}})
    isolation = write(tmp_path / "isolation.json", {
        "schema_version": 1, "target_socs": ["Ascend950"], "baseline_files": snapshot(baseline),
        "editable_ranges": {}, "new_files": {}})
    gate = tmp_path / "conformance.json"
    command = ["timeout", "30s", sys.executable, str(SCRIPTS / "validate_implementation_conformance.py")]
    for key, path in [("contract", impl), ("result", result), ("manifest", manifest),
                      ("baseline", baseline), ("candidate", candidate), ("isolation-scope", isolation)]:
        command.extend(["--" + key, str(path)])
    run = subprocess.run(command + ["--out", str(gate)], capture_output=True, text=True, timeout=35)
    assert run.returncode == 0, run.stdout + run.stderr
    return manifest, impl, gate, candidate, command


def test_conformance_schedule_gate_and_live_source_recovery(tmp_path):
    manifest, impl, gate, candidate, _ = full_gate(tmp_path)
    paths = workflow.check_schedule_artifacts("runtime", [str(gate)], manifest, "s1")
    assert str(impl) in paths
    with pytest.raises(ValueError, match="selected candidate"):
        workflow.check_schedule_artifacts("runtime", [str(gate)], manifest, "another")
    (candidate / "kernel.cpp").write_text("// changed source\n")
    with pytest.raises(ValueError, match="stale/invalid"):
        workflow.check_schedule_artifacts("runtime", [str(gate)], manifest)


def test_conformance_rejects_model_check_in_place_of_runtime(tmp_path):
    manifest, impl, gate, _, command = full_gate(tmp_path)
    result = schedule.load(tmp_path / "result.json")
    result["schedule"]["check"] = schedule.ref(tmp_path / "model.json")
    write(tmp_path / "result.json", result)
    before = gate.read_bytes()
    run = subprocess.run(command + ["--verify-existing", str(gate)], capture_output=True, text=True, timeout=35)
    assert run.returncode != 0 and "runtime evidence" in run.stderr
    assert gate.read_bytes() == before


def state_command(state, *args):
    return subprocess.run([shutil.which("timeout"), "30s", sys.executable,
                           str(SCRIPTS / "workflow_state.py"), *args, "--state", str(state)],
                          capture_output=True, text=True, timeout=35)


def test_real_round2_handoff_complete_and_verify(tmp_path):
    manifest, impl, gate, candidate, _ = full_gate(tmp_path)
    state = tmp_path / "workflow-state.json"
    run = state_command(state, "start", "--manifest", str(manifest))
    assert run.returncode == 0, run.stderr
    for stage in ("round1.analysis", "round2.analysis", "gen.round3.analysis"):
        run = state_command(state, "mark", "--stage", stage, "--status", "complete")
        assert run.returncode != 0 and "bound contract" in run.stdout + run.stderr
    run = state_command(state, "mark", "--stage", "round2.impl.s1", "--status", "complete", "--artifact", str(gate))
    assert run.returncode != 0 and "handoff incomplete" in run.stdout + run.stderr
    run = state_command(state, "mark", "--stage", "round2.analysis", "--status", "complete", "--artifact", str(impl))
    assert run.returncode == 0, run.stderr
    run = state_command(state, "mark", "--stage", "round2.impl.s1", "--status", "complete", "--artifact", str(gate))
    assert run.returncode == 0, run.stderr
    run = state_command(state, "verify")
    assert run.returncode == 0, run.stderr
    (candidate / "kernel.cpp").write_text("// modified after checkpoint\n")
    run = state_command(state, "verify")
    assert run.returncode == 2, run.stderr
    saved = schedule.load(state)
    assert saved["stages"]["round2.impl.s1"]["status"] == "invalid"


def test_round2_cannot_use_round1_analysis_or_unfrozen_contract(tmp_path):
    manifest, impl, gate, _, _ = full_gate(tmp_path)
    state = {"stages": {"round1.analysis": {"status": "complete", "artifacts": [workflow.artifact_identity(impl)]}}}
    with pytest.raises(ValueError, match="handoff incomplete"):
        workflow.check_schedule_handoff("round2.impl.s1", state, manifest)
    with pytest.raises(ValueError, match="not frozen"):
        workflow.check_runtime_handoff("round2.impl.s1", [str(gate)], state)
    state["stages"]["round2.analysis"] = copy.deepcopy(state["stages"]["round1.analysis"])
    assert workflow.check_runtime_handoff("round2.impl.s1", [str(gate)], state) is None
    state["stages"]["round2.analysis"]["artifacts"][0]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="not frozen"):
        workflow.check_runtime_handoff("round2.impl.s1", [str(gate)], state)


def _separate_resources(c):
    c.update(buffers=[], edges=[], resources=[])
    for task in c["tasks"]:
        task.update(resource=task["id"], reads=[], writes=[])
        c["resources"].append({"id": task["id"], "mode": "exclusive"})


def test_later_event_generation_cannot_create_initial_tokens(tmp_path):
    def change(c):
        _separate_resources(c)
        first = event(c)
        first["publishes"][0]["pipe"] = "load0"
        first["waits"][0]["pipe"] = "read0"
        later = copy.deepcopy(first)
        later.update(id="next", generation=1, initial_tokens=1, publishes=[],
                     waits=[{"task": "read1", "pipe": "read1", "tokens": 1}])
        c["events"] = [first, later]
    report = build(tmp_path, change)
    assert report["status"] == "MODEL_REJECTED"
    assert "initial tokens" in report["errors"][0]


def test_inactive_event_generation_does_not_hide_reuse(tmp_path):
    def change(c):
        _separate_resources(c)
        first = event(c)
        first["publishes"][0]["pipe"] = "load0"
        first["waits"][0]["pipe"] = "read0"
        last = copy.deepcopy(first)
        last.update(id="last", generation=2, publishes=[{"task": "load1", "pipe": "load1", "tokens": 1}],
                    waits=[{"task": "read1", "pipe": "read1", "tokens": 1}])
        c["branches"].append({"id": "tail", "predicate": "tail", "case_ids": ["case1"]})
        for tid in ("tailpub", "tailwait"):
            t = copy.deepcopy(c["tasks"][0])
            t.update(id=tid, resource=tid, branches=["tail"])
            c["tasks"].append(t)
            c["resources"].append({"id": tid, "mode": "exclusive"})
            c["programs"][0]["submission_order"].append(tid)
        middle = copy.deepcopy(first)
        middle.update(id="middle", generation=1, publishes=[{"task": "tailpub", "pipe": "tailpub", "tokens": 1}],
                      waits=[{"task": "tailwait", "pipe": "tailwait", "tokens": 1}])
        c["events"] = [first, middle, last]
    report = build(tmp_path, change)
    assert report["status"] == "MODEL_REJECTED"
    assert "reused before consumption" in report["errors"][0]


def test_stage_scheme_must_match_conformance(tmp_path):
    _, impl, gate, _, _ = full_gate(tmp_path)
    state = {"stages": {"round1.analysis": {"status": "complete", "artifacts": [workflow.artifact_identity(impl)]}}}
    with pytest.raises(ValueError, match="scheme differs"):
        workflow.check_runtime_handoff("round1.impl.other", [str(gate)], state)


@pytest.mark.parametrize("change", ["missing", "soc", "branch", "files"])
def test_runtime_case_soc_branch_evidence_coverage(tmp_path, change):
    cp, manifest, ep, _, e, _ = fixture(tmp_path)
    if change == "missing":
        e["runtime"]["coverage"] = []
    elif change == "soc":
        e["runtime"]["coverage"][0]["target_soc"] = "OtherSoC"
    elif change == "branch":
        e["runtime"]["coverage"][0]["branch"] = "omitted_tail"
    else:
        e["runtime"]["coverage"][0]["evidence"] = []
    write(ep, e)
    with pytest.raises(ValueError, match="coverage|evidence"):
        schedule.build_report(cp, manifest, "runtime", ep)


def integration_evidence(tmp_path, cp, manifest, ep, c, e, candidate):
    """Synthetic CPU receipts exercise joins; no actual hardware is claimed."""
    from prepare_case_sets import code_identity
    from validate_postprocess_performance import validate as postprocess
    value = schedule.load(manifest)
    value["schema_version"] = 2
    value["collections"]["performance_full"] = value["collections"]["performance_tuning"]
    value["collections"]["functional_full"] = value["collections"]["performance_tuning"]
    write(manifest, value)
    c["scope"]["collection"] = "performance_full"
    write(cp, c)
    e.update(contract=schedule.ref(cp), manifest=schedule.ref(manifest), scope=c["scope"])
    base = tmp_path / "baseline-perf.csv"
    current = tmp_path / "integrated-perf.csv"
    base.write_text("case_id,total_us\ncase1,100\n")
    current.write_text("case_id,total_us\ncase1,90\n")
    gate = write(tmp_path / "postprocess.json", postprocess(manifest, "Ascend950", {
        "functional": (base, current), "performance": (base, current)}))
    binary = tmp_path / "fixture.so"
    binary.write_bytes(b"synthetic binary fixture")
    buildlog = tmp_path / "build.log"
    buildlog.write_text("fixture build receipt\n")
    loader = tmp_path / "loader.log"
    loader.write_text(f"loaded {binary}\n")
    raw = [schedule.ref(loader), schedule.ref(current)]
    runtime = write(tmp_path / "integrated-runtime.json",
                    {"method": "synthetic loader trace", "target_soc": "Ascend950",
                     "source_artifacts": raw, "loaded_artifacts": [schedule.ref(binary)]})
    execution = write(tmp_path / "integrated-execution-identity.json", {"schema_version": 1,
        "source": code_identity(candidate), "targets": [{"target_soc": "Ascend950",
            "build": {"command": "fixture-build", "log": schedule.ref(buildlog), "artifacts": [schedule.ref(binary)]},
            "runtime": {"evidence": schedule.ref(runtime), "loaded_artifacts": [schedule.ref(binary)],
                        "source_artifacts": raw}}]})
    e["integration"] = {"execution_identity": schedule.ref(execution), "postprocess_gates": [schedule.ref(gate)]}
    write(ep, e)
    return gate


def test_integration_requires_actual_integrated_evidence(tmp_path):
    manifest, _, gate, _, _ = full_gate(tmp_path)
    with pytest.raises(ValueError, match="actual integrated"):
        workflow.check_schedule_artifacts("integration", [str(gate)], manifest)


def test_integration_full_gate_and_recovery(tmp_path):
    manifest, _, gate, candidate, _ = full_gate(tmp_path, integrated=True)
    postprocess = tmp_path / "postprocess.json"
    verify = tmp_path / "VERIFY_REPORT.md"
    verify.write_text("Synthetic integration fixture\n")
    paths = workflow.check_phase_artifacts("integration", [str(gate), str(postprocess), str(verify)], manifest)
    assert str(tmp_path / "integrated-execution-identity.json") in paths
    (candidate / "kernel.cpp").write_text("// integration source changed\n")
    with pytest.raises(ValueError, match="stale/invalid"):
        workflow.check_phase_artifacts("integration", [str(gate), str(postprocess), str(verify)], manifest)


def test_integration_wrong_root_rejected(tmp_path):
    from prepare_case_sets import code_identity
    cp, manifest, ep, c, e, candidate = fixture(tmp_path)
    integration_evidence(tmp_path, cp, manifest, ep, c, e, candidate)
    other = tmp_path / "wrong-root"
    shutil.copytree(candidate, other)
    execution = tmp_path / "integrated-execution-identity.json"
    doc = schedule.load(execution)
    doc["source"] = code_identity(other)
    write(execution, doc)
    e["integration"]["execution_identity"] = schedule.ref(execution)
    write(ep, e)
    with pytest.raises(ValueError, match="differs from schedule candidate root"):
        schedule.build_report(cp, manifest, "runtime", ep)


@pytest.mark.parametrize("case", ["allow", "after_analysis", "existing", "changed_manifest"])
def test_explicit_preanalysis_policy_adoption(tmp_path, case):
    _, manifest, _, _, _, _ = fixture(tmp_path)
    request = write(tmp_path / "request.json", {"schedule_policy": schedule.POLICY})
    value = schedule.load(manifest)
    value["request"] = schedule.ref(request)
    write(manifest, value)
    state = tmp_path / "state.json"
    assert state_command(state, "start", "--manifest", str(manifest)).returncode == 0
    saved = schedule.load(state)
    if case != "existing":
        saved.pop("schedule_policy")
    if case == "after_analysis":
        saved["events"].append({"kind": "stage", "stage": "round2.analysis", "status": "invalid"})
    write(state, saved)
    if case == "changed_manifest":
        manifest.write_text(manifest.read_text() + "\n")
    audit = tmp_path / "audit.md"
    audit.write_text("Old state writer omitted the already frozen schedule policy before analysis.\n")
    run = state_command(state, "migrate-workflow", "--audit", str(audit), "--workflow-version",
                        workflow.WORKFLOW_VERSION, "--adopt-schedule-policy")
    if case == "allow":
        assert run.returncode == 0, run.stdout + run.stderr
        migrated = schedule.load(state)
        assert migrated["schedule_policy"] == schedule.POLICY
        assert any(e["kind"] == "schedule_policy_adopted" for e in migrated["events"])
    else:
        assert run.returncode != 0, run.stdout + run.stderr
        assert schedule.load(state) == saved
