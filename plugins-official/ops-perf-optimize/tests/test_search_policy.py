# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Synthetic search trajectories. These tests make no hardware performance claims."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = (
    Path(__file__).resolve().parents[1] / "skills/ops-perf-optimize-workflow/scripts"
)
sys.path.insert(0, str(SCRIPTS))
import search_policy as search
from prepare_case_sets import load_request, load_manifest
from summarize_performance_effects import summarize
from validate_implementation_conformance import evaluate, verify_gate
from validate_source_isolation import snapshot
from test_prepare_case_sets import create_request, write_cases, run as run_case_sets


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False))
    return path


def round_checkpoint(stage, selection, summary, cumulative, selected):
    return [
        "--stage",
        stage,
        "--status",
        "complete",
        "--artifact",
        selection,
        "--performance-summary",
        summary,
        "--cumulative-performance-summary",
        cumulative,
        "--selected-candidate",
        selected,
    ]


def accept_stage(cli, stage, artifact):
    cli("mark", "--stage", stage, "--status", "complete", "--artifact", artifact)


def state_cli(state):
    from test_schedule_contract import state_command

    def cli(*args):
        result = state_command(state, *map(str, args))
        assert result.returncode == 0, result.stdout + result.stderr

    return cli


class Run:
    def __init__(self, root, mode="standard", backend="ascendc", confidence=False):
        self.root = root
        self.source = root / "baseline"
        self.source.mkdir()
        self.filename = "kernel.py" if backend == "cannbot_dsl" else "kernel.cpp"
        (self.source / self.filename).write_text("value = 0\n")
        self.workload = root / "cases.csv"
        self.workload.write_text("case_id\na\nb\n")
        self.original = self.performance("original", [100, 100])
        self.baseline = self.original
        self.mode = mode
        self.configuration = {
            "precision_diagnosis_policy": "persistent",
            "target_socs": ["Ascend950"],
            "functional_mode": "reuse_performance",
            "tuning_mode": mode,
            "backend": backend,
            "search_policy": search.POLICY,
            "optimization_objective": {"mode": "fixed_rounds", "rounds": 3},
        }
        if confidence:
            self.configuration["performance_effect_policy"] = {
                "id": "confidence_effect_v1",
                "version": 1,
            }
        if mode == "generalization":
            self.configuration["generalization"] = {"competitor": {"source": "file"}}
        if backend == "cannbot_dsl":
            self.configuration["dsl"] = {
                "repo_root": str(root),
                "entrypoint": "op:run",
                "execution_mode": "jit",
                "workload_scope": "network_cases",
            }
        key = (
            "generalization_full" if mode == "generalization" else "performance_tuning"
        )
        self.manifest = write(
            root / "manifest.json",
            {
                "configuration": self.configuration,
                "inputs": {},
                "collections": {key: search.ref(self.workload)},
            },
        )
        self.state = root / "workflow-state.json"
        self.cli("start", "--manifest", self.manifest)
        self.evidence = root / "diagnosis.txt"
        self.evidence.write_text("synthetic fixture, not a hardware measurement")
        accept_stage(self.cli, "phase.preparation", self.evidence)

    def cli(self, command, *args, ok=True):
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "workflow_state.py"),
                command,
                "--state",
                str(self.state),
                *map(str, args),
            ],
            text=True,
            capture_output=True,
        )
        if ok:
            assert result.returncode == 0, result.stdout + result.stderr
        else:
            assert result.returncode != 0, result.stdout
        return json.loads(result.stdout)

    def round(self, number):
        return ("gen." if self.mode == "generalization" else "") + f"round{number}"

    def performance(self, name, values):
        path = self.root / f"{name}.csv"
        path.write_text(
            "case_id,total_us\n"
            + "".join(f"{case},{v}\n" for case, v in zip(("a", "b"), values))
        )
        return path

    def plan(self, number, *, mechanism=None, depends=(), retry=None, register=True):
        scheme = f"s{number}"
        contract = {
            "schema_version": 3,
            "scheme_id": scheme,
            "implementation_mode": "exact",
            "substitution_policy": "forbidden",
            "target_socs": ["Ascend950"],
            "backend": self.configuration["backend"],
            "safety": {"public_contract": "unchanged", "non_target_socs": "unchanged"},
            "expectations": {"vf": False, "casttrait": False},
            "required_features": [
                {"id": "change", "description": "implement the declared decision"}
            ],
            "case_ids": ["a", "b"],
            "search": {
                "kind": "architecture" if not depends else "local",
                "mechanism": mechanism or scheme,
                "parent": search.source_identity(self.source),
                "workload": search.ref(self.workload),
                "baseline_performance": search.ref(self.baseline),
                "depends_on": list(depends),
                "trigger": [search.ref(self.evidence)],
                "mechanism_check": "probe verifies the expected dataflow",
            },
        }
        if retry:
            contract["search"]["retry"] = retry
        path = write(
            self.root / self.round(number) / f"implementation-contract-{scheme}.json",
            contract,
        )
        if register:
            accept_stage(self.cli, f"{self.round(number)}.analysis", path)
        return path

    def isolation_scope(self, directory):
        return write(
            directory / "scope.json",
            {
                "schema_version": 1,
                "target_socs": ["Ascend950"],
                "baseline_files": snapshot(self.source),
                "editable_ranges": {
                    self.filename: [
                        {
                            "start": 1,
                            "end": 1,
                            "kind": "target_private",
                            "reason": "fixture",
                        }
                    ]
                },
                "new_files": {},
            },
        )

    def candidate_gate(self, number, contract):
        directory = self.root / self.round(number)
        scheme = search.load(contract)["scheme_id"]
        candidate = directory / "candidate"
        candidate.mkdir()
        (candidate / self.filename).write_text(f"value = {number}\n")
        (candidate / "proof.txt").write_text("synthetic build/feature evidence")
        scope = self.isolation_scope(directory)
        conformance = write(
            directory / "conformance.json",
            {
                "schema_version": 3,
                "scheme_id": scheme,
                "implementation_status": "complete",
                "route_changed": False,
                "substitution_used": False,
                "features": {
                    "change": {
                        "status": "pass",
                        "source_locations": [f"{self.filename}:1"],
                        "evidence_files": ["proof.txt"],
                    }
                },
            },
        )
        args = argparse.Namespace(
            contract=contract,
            result=conformance,
            manifest=self.manifest,
            isolation_scope=scope,
            baseline=self.source,
            candidate=candidate,
        )
        malformed, gate = evaluate(args)
        assert not malformed and gate["decision"] == "pass"
        gate_path = write(directory / "gate.json", gate)
        accept_stage(self.cli, f"{self.round(number)}.impl.{scheme}", gate_path)
        return candidate, gate_path

    def outcome(
        self, number, contract, *, values=(110, 110), kind="measured", selected=False
    ):
        directory = self.root / self.round(number)
        scheme = search.load(contract)["scheme_id"] if contract else None
        effect_policy = self.configuration.get("performance_effect_policy", {}).get(
            "id", "legacy_jitter_v1"
        )
        result = {
            "scheme_id": scheme,
            "outcome": kind,
            "evidence": [search.ref(self.evidence)],
            "mechanism": {"status": "unknown"},
            "retry_condition": "revisit only with new probe evidence",
        }
        if kind == "measured":
            candidate, gate_path = self.candidate_gate(number, contract)
            candidate_perf = self.performance(f"perf-{number}", values)
            effect = write(
                directory / "effect.json",
                summarize(self.baseline, candidate_perf, policy_id=effect_policy),
            )
            result.update(
                effect_summary=search.ref(effect),
                conformance_gate=search.ref(gate_path),
            )
        selection = write(directory / "selection.json", {"search": result})
        kept_perf = candidate_perf if selected else self.baseline
        current = (
            effect
            if selected
            else write(
                directory / "kept.json",
                summarize(self.baseline, self.baseline, policy_id=effect_policy),
            )
        )
        cumulative = write(
            directory / "cumulative.json",
            summarize(self.original, kept_perf, policy_id=effect_policy),
        )
        args = round_checkpoint(
            f"{self.round(number)}.complete",
            selection,
            current,
            cumulative,
            scheme if selected else "baseline",
        )
        return args, candidate if kind == "measured" else None, kept_perf

    def finish_round(self, number, **kwargs):
        plan = self.plan(number)
        args, candidate, perf = self.outcome(number, plan, **kwargs)
        self.cli("mark", *args)
        if kwargs.get("selected"):
            self.source, self.baseline = candidate, perf
        return args

    def view(self):
        return self.cli("inspect")["search"]


def test_three_evaluations_trigger_replan_and_replay_is_idempotent(tmp_path):
    run = Run(tmp_path)
    for n in range(1, 4):
        args = run.finish_round(n)
        assert run.view()["stagnation"] == n
        run.cli("mark", *args)
        assert run.view()["stagnation"] == n
    assert run.view()["next_action"] == "replan"
    path = run.plan(4, register=False)
    rejected = run.cli(
        "mark",
        "--stage",
        "round4.analysis",
        "--status",
        "complete",
        "--artifact",
        path,
        ok=False,
    )
    assert "architecture review" in rejected["error"]
    for _ in range(2):
        run.cli(
            "search-replan",
            "--reason",
            "plateau",
            "--reopen",
            "s1",
            "--evidence",
            run.evidence,
            "--message",
            "revisit topology",
        )
        assert run.view()["stagnation"] == 0
    assert (
        sum(e["kind"] == "search_replan" for e in search.load(run.state)["events"]) == 1
    )
    run.cli(
        "mark", "--stage", "round4.analysis", "--status", "complete", "--artifact", path
    )
    assert run.cli("verify")["status"] == "valid"


def test_winner_becomes_reference_and_resets_stagnation(tmp_path):
    run = Run(tmp_path)
    run.finish_round(1)
    run.finish_round(2, values=(80, 80), selected=True)
    view = run.view()
    assert view["stagnation"] == 0 and view["anchor"] == search.source_identity(
        run.source
    )
    assert view["accepted_decisions"] == ["s2"]
    path = run.plan(3, depends=("s2",))
    assert search.load(path)["search"]["parent"] == view["anchor"]


@pytest.mark.parametrize(
    "kind", ["implementation_failed", "precision_failed", "evidence_invalid"]
)
def test_failed_gates_do_not_count_as_performance_stagnation(tmp_path, kind):
    run = Run(tmp_path)
    run.finish_round(1, kind=kind)
    assert run.view()["stagnation"] == 0
    assert run.view()["next_action"] in ("repair_candidate", "repair_evidence")


def test_confirmation_is_separate_from_stagnation():
    assert search.classify({"inconclusive_case_count": 1}) == "inconclusive"
    assert (
        search.classify(
            {"effective_improvement_count": 1, "effective_geomean_speedup": 1.001}
        )
        == "improvement"
    )


def test_unconfirmed_gain_cannot_close_a_round_or_promote(tmp_path):
    run = Run(tmp_path, confidence=True)
    plan = run.plan(1)
    args, _, _ = run.outcome(1, plan, values=(80, 80), selected=True)
    before = run.state.read_bytes()
    error = run.cli("mark", *args, ok=False)
    assert "inconclusive" in error["error"]
    assert run.state.read_bytes() == before
    assert run.view()["stagnation"] == 0


def test_confirmed_small_gain_consumes_raw_evidence(tmp_path):
    from test_confidence_effect_policy import fixture, confirmed

    f = fixture(tmp_path)
    path = write(tmp_path / "effect.json", confirmed(f))
    summary, dependencies = search.checked_summary(
        search.ref(path),
        {
            "configuration": {
                "performance_effect_policy": {
                    "id": "confidence_effect_v1",
                    "version": 1,
                }
            }
        },
    )
    assert search.classify(summary) == "improvement"
    assert abs(summary["cases"][0]["delta_percent"]) < 3
    assert search.ref(f.raw) in dependencies


def test_dsl_uses_the_same_search_and_reference_promotion(tmp_path):
    run = Run(tmp_path, backend="cannbot_dsl")
    run.finish_round(1, values=(90, 90), selected=True)
    assert run.view()["accepted_decisions"] == ["s1"]
    assert run.cli("verify")["status"] == "valid"


def test_stagnation_does_not_extend_the_user_budget(tmp_path):
    run = Run(tmp_path)
    for number in range(1, 4):
        run.finish_round(number)
    assert run.view()["next_action"] == "replan"
    run.cli(
        "finish",
        "--status",
        "success",
        "--reason-code",
        "completed",
        "--message",
        "fixed round budget completed",
    )
    assert run.view()["next_action"] == "complete"
    assert search.load(run.manifest)["configuration"]["optimization_objective"] == {
        "mode": "fixed_rounds",
        "rounds": 3,
    }


def test_no_candidate_needs_analysis_and_requests_replanning(tmp_path):
    run = Run(tmp_path)
    args, _, _ = run.outcome(1, None, kind="no_candidate")
    error = run.cli("mark", *args, ok=False)
    assert "analysis is incomplete" in error["error"]
    run.cli(
        "mark",
        "--stage",
        "round1.analysis",
        "--status",
        "complete",
        "--artifact",
        run.evidence,
    )
    run.cli("mark", *args)
    assert run.view()["next_action"] == "replan"
    assert run.view()["stagnation"] == 0


def test_net_gain_cannot_bypass_existing_per_case_retreat_limit(tmp_path):
    run = Run(tmp_path)
    plan = run.plan(1)
    args, _, _ = run.outcome(1, plan, values=(200, 10), selected=True)
    error = run.cli("mark", *args, ok=False)
    assert "retreat limit" in error["error"]


@pytest.mark.parametrize(
    "stage", ["round1.analysis", "round1.impl.s1", "round1.complete"]
)
def test_invalidated_acceptance_blocks_search_until_restored(tmp_path, stage):
    run = Run(tmp_path)
    args = run.finish_round(1)
    run.cli(
        "mark", "--stage", stage, "--status", "invalid", "--reason", "review_required"
    )
    assert run.view()["next_action"] == "repair_evidence"
    next_plan = run.plan(2, register=False)
    run.cli(
        "mark",
        "--stage",
        "round2.analysis",
        "--status",
        "complete",
        "--artifact",
        next_plan,
        ok=False,
    )
    if stage == "round1.complete":
        run.cli("mark", *args)
    else:
        artifact = (
            tmp_path / "round1/implementation-contract-s1.json"
            if stage.endswith("analysis")
            else tmp_path / "round1/gate.json"
        )
        run.cli(
            "mark", "--stage", stage, "--status", "complete", "--artifact", artifact
        )
    run.cli(
        "mark",
        "--stage",
        "round2.analysis",
        "--status",
        "complete",
        "--artifact",
        next_plan,
    )
    assert run.cli("verify")["status"] == "valid"


def test_only_one_immutable_scheme_per_round_and_no_speculative_next_round(tmp_path):
    run = Run(tmp_path)
    first = run.plan(1)
    second = run.plan(2, register=False)
    for stage, paths in [
        ("round1.analysis", [first, second]),
        ("round1.analysis", [second]),
        ("round2.analysis", [second]),
    ]:
        before = run.state.read_bytes()
        args = ["--stage", stage, "--status", "complete"]
        for path in paths:
            args += ["--artifact", path]
        run.cli("mark", *args, ok=False)
        assert run.state.read_bytes() == before


def test_failed_mechanism_needs_new_retry_evidence(tmp_path):
    run = Run(tmp_path)
    run.finish_round(1)
    path = run.plan(2, mechanism="s1", register=False)
    rejected = run.cli(
        "mark",
        "--stage",
        "round2.analysis",
        "--status",
        "complete",
        "--artifact",
        path,
        ok=False,
    )
    assert "retry needs" in rejected["error"]
    probe = tmp_path / "new-probe.txt"
    probe.write_text("changed tiling removes the previously measured transfer")
    path = run.plan(
        2,
        mechanism="s1",
        retry={
            "decision_id": "s1",
            "reason": "changed conditions",
            "evidence": [search.ref(probe)],
        },
    )
    assert run.view()["next_action"] == "implement"
    args, _, _ = run.outcome(2, path)
    run.cli("mark", *args)
    new_probe = tmp_path / "third-probe.txt"
    new_probe.write_text("new evidence identifies a different overhead")
    run.plan(
        3,
        mechanism="s1",
        retry={
            "decision_id": "s2",
            "reason": "new diagnosis",
            "evidence": [search.ref(new_probe)],
        },
    )


def test_invalid_measurement_can_be_retried_with_repaired_evidence(tmp_path):
    run = Run(tmp_path)
    run.finish_round(1, kind="evidence_invalid")
    probe = tmp_path / "repair.txt"
    probe.write_text("measurement protocol repaired and verified")
    run.plan(
        2,
        mechanism="s1",
        retry={
            "decision_id": "s1",
            "reason": "fixed protocol",
            "evidence": [search.ref(probe)],
        },
    )
    assert run.view()["next_action"] == "implement"
    assert run.view()["stagnation"] == 0


def test_replanning_waits_for_the_active_round_result(tmp_path):
    run = Run(tmp_path)
    run.plan(1)
    error = run.cli(
        "search-replan",
        "--reason",
        "gate_impasse",
        "--reopen",
        "s1",
        "--evidence",
        run.evidence,
        "--message",
        "reconsider architecture",
        ok=False,
    )
    assert "complete the active round" in error["error"]


def test_reopening_foundation_retires_dependent_decisions_without_losing_incumbent(
    tmp_path,
):
    run = Run(tmp_path)
    run.finish_round(1, values=(90, 90), selected=True)
    path = run.plan(2, depends=("s1",))
    args, candidate, perf = run.outcome(2, path, values=(80, 80), selected=True)
    run.cli("mark", *args)
    anchor = run.view()["anchor"]
    run.source, run.baseline = candidate, perf
    run.cli(
        "search-replan",
        "--reason",
        "architecture_limit",
        "--reopen",
        "s1",
        "--evidence",
        run.evidence,
        "--message",
        "replace exposed boundary scheduling",
    )
    assert run.view()["anchor"] == anchor
    assert run.view()["reopened_decisions"] == ["s1", "s2"]
    path = run.plan(3, depends=("s2",), register=False)
    run.cli(
        "mark",
        "--stage",
        "round3.analysis",
        "--status",
        "complete",
        "--artifact",
        path,
        ok=False,
    )


@pytest.mark.parametrize(
    "damage", ["probe", "contract", "source", "summary", "feature_evidence"]
)
def test_changed_evidence_prevents_recovery_and_promotion(tmp_path, damage):
    run = Run(tmp_path)
    run.finish_round(1)
    paths = {
        "probe": run.evidence,
        "contract": tmp_path / "round1/implementation-contract-s1.json",
        "source": tmp_path / "round1/candidate/kernel.cpp",
        "summary": tmp_path / "round1/effect.json",
        "feature_evidence": tmp_path / "round1/candidate/proof.txt",
    }
    damaged = paths.get(damage)
    assert damaged is not None
    damaged.write_text(damaged.read_text() + " ")
    assert run.view()["next_action"] == "repair_evidence"
    assert run.cli("verify", ok=False)["status"] == "invalid"


def test_gate_cannot_be_reused_after_candidate_changes(tmp_path):
    run = Run(tmp_path)
    plan = run.plan(1)
    _, candidate, _ = run.outcome(1, plan)
    gate = tmp_path / "round1/gate.json"
    assert verify_gate(gate)["decision"] == "pass"
    (candidate / "kernel.cpp").write_text("another source\n")
    with pytest.raises(ValueError, match="stale"):
        verify_gate(gate)


def test_generalization_scope_change_does_not_accumulate_unrelated_stagnation(tmp_path):
    run = Run(tmp_path, mode="generalization")
    run.finish_round(1)
    extra = tmp_path / "selected-cases.csv"
    extra.write_text("case_id,note\na,new workload identity\nb,new workload identity\n")
    run.workload = extra
    run.finish_round(2)
    assert run.view()["stagnation"] == 1


@pytest.mark.parametrize("depends", [["unknown"], ["s1"], ["a", "a"]])
def test_invalid_dependencies_are_rejected(tmp_path, depends):
    run = Run(tmp_path)
    path = run.plan(1, depends=depends, register=False)
    run.cli(
        "mark",
        "--stage",
        "round1.analysis",
        "--status",
        "complete",
        "--artifact",
        path,
        ok=False,
    )


def test_request_policy_is_frozen_and_absent_inputs_stay_absent(tmp_path):
    code = tmp_path / "code"
    code.mkdir()
    (code / "kernel.cpp").write_text("original\n")
    cases = tmp_path / "cases.csv"
    write_cases(cases, 2)
    request = tmp_path / "request.json"
    create_request(request, code, cases)
    assert load_request(request)["search_policy"] == search.POLICY
    run_case_sets("freeze", "--request", request, "--output-dir", tmp_path / "run")
    assert (
        load_manifest(tmp_path / "run/run-manifest.json")["configuration"][
            "search_policy"
        ]
        == search.POLICY
    )
    value = search.load(request)
    del value["search_policy"]
    write(request, value)
    assert "search_policy" not in load_request(request)
    run_case_sets(
        "freeze", "--request", request, "--output-dir", tmp_path / "without-policy"
    )
    assert (
        "search_policy"
        not in load_manifest(tmp_path / "without-policy/run-manifest.json")[
            "configuration"
        ]
    )


@pytest.mark.parametrize(
    "value",
    [
        None,
        {},
        {"id": "unknown", "version": 1},
        {"id": "architecture_search_v1", "version": True},
        {"id": "architecture_search_v1", "version": 2},
    ],
)
def test_invalid_policy_rejected(value):
    with pytest.raises(ValueError, match="search_policy"):
        search.validate_policy(value)


def test_manifest_cannot_silently_drop_frozen_policy(tmp_path):
    request = write(tmp_path / "request.json", {"search_policy": search.POLICY})
    with pytest.raises(ValueError, match="frozen request"):
        search.enabled({"configuration": {}, "request": search.ref(request)})


def scheduled_search_gate(tmp_path, selected):
    from test_schedule_contract import full_gate
    from validate_schedule_contract import build_report

    manifest, contract, gate, _, command = full_gate(tmp_path)
    baseline_source = tmp_path / "baseline"
    evidence = tmp_path / "source.cpp"
    configuration = search.load(manifest)
    configuration["configuration"]["search_policy"] = search.POLICY
    write(manifest, configuration)
    baseline = tmp_path / "baseline.csv"
    baseline.write_text("case_id,total_us\ncase1,100\n")
    candidate_perf = tmp_path / "candidate.csv"
    candidate_perf.write_text(f"case_id,total_us\ncase1,{90 if selected else 110}\n")
    schedule_contract = tmp_path / "schedule-contract-s1.json"
    schedule_evidence = tmp_path / "schedule-evidence-s1.json"
    payload = search.load(schedule_evidence)
    payload["manifest"] = search.ref(manifest)
    write(schedule_evidence, payload)
    model = write(tmp_path / "model.json", build_report(schedule_contract, manifest))
    runtime = write(
        tmp_path / "runtime.json",
        build_report(schedule_contract, manifest, "runtime", schedule_evidence),
    )
    payload = search.load(contract)
    payload["case_ids"] = ["case1"]
    payload["schedule"]["check"] = search.ref(model)
    payload["search"] = {
        "kind": "architecture",
        "mechanism": "buffer-reuse",
        "depends_on": [],
        "parent": search.source_identity(baseline_source),
        "workload": search.ref(tmp_path / "cases.csv"),
        "baseline_performance": search.ref(baseline),
        "trigger": [search.ref(evidence)],
        "mechanism_check": "schedule evidence verifies the last reader",
    }
    write(contract, payload)
    payload = search.load(tmp_path / "result.json")
    payload["schedule"]["check"] = search.ref(runtime)
    write(tmp_path / "result.json", payload)
    result = subprocess.run(
        command + ["--out", str(gate)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return manifest, contract, gate, baseline, candidate_perf


@pytest.mark.parametrize(
    "outcome,selected",
    [
        ("measured", True),
        ("measured", False),
        ("implementation_failed", False),
        ("precision_failed", False),
        ("evidence_invalid", False),
        ("no_candidate", False),
    ],
)
def test_search_consumes_schedule_acceptance_without_certifying_failed_trials(
    tmp_path, outcome, selected
):
    manifest, contract, gate, baseline, candidate_perf = scheduled_search_gate(
        tmp_path, selected
    )
    evidence = tmp_path / "source.cpp"
    state = tmp_path / "workflow-state.json"

    cli = state_cli(state)
    cli("start", "--manifest", manifest)
    accept_stage(cli, "phase.preparation", evidence)
    accept_stage(
        cli, "round1.analysis", evidence if outcome == "no_candidate" else contract
    )
    observation = {
        "scheme_id": None if outcome == "no_candidate" else "s1",
        "outcome": outcome,
        "evidence": [search.ref(evidence)],
        "mechanism": {"status": "unknown"},
        "retry_condition": "require new diagnostic evidence",
    }
    effect = write(tmp_path / "effect.json", summarize(baseline, candidate_perf))
    if outcome == "measured":
        accept_stage(cli, "round1.impl.s1", gate)
        observation.update(
            effect_summary=search.ref(effect), conformance_gate=search.ref(gate)
        )
    selection = write(tmp_path / "selection.json", {"search": observation})
    kept = (
        effect
        if selected
        else write(tmp_path / "kept.json", summarize(baseline, baseline))
    )
    cli(
        "mark",
        *round_checkpoint(
            "round1.complete", selection, kept, kept, "s1" if selected else "baseline"
        ),
    )
    cli("verify")
    view = search.view(search.load(state))
    assert view["accepted_decisions"] == (["s1"] if selected else [])
    assert view["stagnation"] == int(outcome == "measured" and not selected)
