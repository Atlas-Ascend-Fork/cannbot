# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Exercise both values of the evidence gate; fixtures are not content reviews."""
import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/ops-perf-optimize-workflow/scripts"))
import experience_reflux as reflux
import workflow_state as workflow
from test_search_installed import installed_search, python as installed_python


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    return path


@pytest.fixture
def case(tmp_path):
    manifest = save(tmp_path / "run-manifest.json", {
        "schema_version": 2, "configuration": {
            "target_socs": ["Ascend950"], "backend": "ascendc", "tuning_mode": "standard",
            "precision_diagnosis_policy": "persistent", "workflow_layout": "four-stage-v1",
            "performance_effect_policy": {"id": "median_v1", "version": 1},
            "experience_policy": dict(reflux.LEGACY_POLICY)}, "collections": {}, "inputs": {}})
    summary = save(tmp_path / "summary.json", {"effective_geomean_speedup": 1.03, "total_case_count": 2})
    observation = save(
        tmp_path / "observations.json", {"old_pitch": 64, "new_pitch": 32, "compiler_error": "duplicate register"}
    )
    sources = {"summary": reflux.file_ref(summary), "observation": reflux.file_ref(observation)}
    stages, rounds, lessons = {}, [], []
    for n, outcome in ((1, "accepted"), (2, "implementation_failed")):
        selection = {"round": n, "candidate_accepted": outcome == "accepted", "search": {
            "outcome": "measured" if n == 1 else outcome,
            **({"effect_summary": reflux.file_ref(summary)} if n == 1 else {})}}
        path = save(tmp_path / f"implementation/round{n}/selection.json", selection)
        sources[f"selection{n}"] = reflux.file_ref(path)
        stage = f"round{n}.complete"
        stages[stage] = {"status": "complete", "artifacts": [reflux.file_ref(path)]}
        rounds.append({"stage": stage, "selection_source": f"selection{n}", "outcome": outcome,
                       "performance": {"source": "summary", "geomean_speedup": 1.03, "case_count": 2,
                                       "comparison": "candidate against original parent"} if n == 1 else None})
        anchor = {"source": "observation", "pointer": "/old_pitch" if n == 1 else "/compiler_error"}
        lessons.append(
            {
                "id": f"L{n}",
                "title": f"Fixture decision {n}",
                "rounds": [stage],
                "problem": "Excessive padded rows in the recorded path",
                "change": "Reduce pitch from 64 to 32",
                "benefit": "Fewer initialized elements",
                "cost": "Additional tail mask instructions",
                "applies_when": ["The original path is selected and width is at most 32"],
                "does_not_apply": ["Width above 32 needs new address analysis"],
                "invariants": ["Original tap order"],
                "observations": [
                    {
                        "statement": "The checked evidence records the old pitch or compilation failure",
                        "evidence": [anchor],
                    }
                ],
                "reasoning": {
                    "status": "hypothesis",
                    "statement": "Clearing less storage may explain part of the difference",
                    "unproven": "The experiment does not isolate instruction cycle contributions",
                    "evidence": [anchor],
                },
                "decision": "Check path and address bounds before testing the new layout",
                "retry_condition": "Require generated code without the duplicate-register error",
                "falsification": "An out-of-range full-lane access invalidates the proposed layout",
                "reproduction": {
                    "offline_steps": ["Read old_pitch in observations.json and compare against 64"],
                    "expected": "Recorded old pitch is 64",
                    "requires_device": "New timing needs device execution",
                },
            }
        )
    state = {"manifest": reflux.file_ref(manifest), "stages": stages}
    save(tmp_path / "workflow-state.json", state)
    bundle = {"schema_version": 1, "producer": "fixture-author", "manifest": reflux.file_ref(manifest),
              "context": {"platform": "Synthetic Ascend950 fixture", "toolchain": "Fixture compiler version",
                          "measurement": "Two cases, fixed N3 median", "time": "2026-11-18"},
              "sources": sources, "rounds": rounds, "lessons": lessons,
              "synthesis": ["A successful source change does not guarantee successful generated code"],
              "limitations": ["Synthetic fixture; not an operator performance claim"]}
    bp = save(tmp_path / "experience-lessons.json", bundle)
    material = tmp_path / "experience-material.md"
    material.write_text(reflux.render(bundle))
    anchor = {"source": "material", "lines": [1, 3]}
    review = {
        "schema_version": 1,
        "reviewer": "fixture-reader",
        "method": "Synthetic test of review plumbing only",
        "bundle": reflux.file_ref(bp),
        "material": reflux.file_ref(material),
        "critical_errors": [],
        "dimensions": {
            k: {"score": 4, "reason": "Synthetic review response exercises gate validation", "evidence": [anchor]}
            for k in reflux.DIMENSIONS
        },
        "reader_tests": [
            {
                "id": category,
                "category": category,
                "question": "Does the stated precondition permit this layout?",
                "answer": "Check width and original path before applying the layout",
                "score": 2,
                "dangerous": False,
                "lesson_ids": ["L1", "L2"],
                "evidence": [anchor],
            }
            for category in ("apply", "reject", "retry", "uncertainty")
        ],
    }
    rp = save(tmp_path / "experience-review.json", review)
    card = tmp_path / "knowledge-reflux/raw.md"
    card.parent.mkdir()
    card.write_text("---\nproducer: fixture-author\n---\n" + material.read_text())
    export = save(tmp_path / "knowledge-reflux.json", {"card": reflux.file_ref(card),
        "experience_material": reflux.file_ref(material), "experience_review": reflux.file_ref(rp)})
    return SimpleNamespace(root=tmp_path, manifest=manifest, bundle=bundle, bp=bp, material=material,
                           review=review, rp=rp, state=state, card=card, export=export)


def test_complete_evidence_closure_passes(case):
    result = reflux.validate(case.bp, case.manifest, material_path=case.material, review_path=case.rp)
    assert result["status"] == "pass"
    assert result["round_count"] == result["lesson_count"] == 2
    assert any(x["path"].endswith("observations.json") for x in result["dependencies"])


def test_structure_only_is_not_semantic_pass(case):
    assert reflux.validate(case.bp, case.manifest)["status"] == "structure_pass"


@pytest.mark.parametrize(
    "mutation,reason",
    [
        (lambda b: b["rounds"].pop(), "round coverage"),
        (lambda b: b["lessons"].pop(), "no lessons"),
        (lambda b: b["rounds"][0].update(outcome="rejected"), "contradicts selection"),
        (lambda b: b["rounds"][0].update(selection_source="selection2"), "selection identity"),
        (lambda b: b["rounds"][0]["performance"].update(geomean_speedup=1.3), "ratio does not match"),
        (lambda b: b["rounds"][0]["performance"].update(case_count=1), "scope count"),
        (lambda b: b["rounds"][1].update(performance=b["rounds"][0]["performance"]), "unmeasured round"),
        (lambda b: b["lessons"][0].update(decision="TODO"), "substantive"),
        (lambda b: b["lessons"][0]["observations"][0].update(evidence=[]), "lacks evidence"),
        (
            lambda b: b["lessons"][0]["observations"][0]["evidence"][0].update(pointer="/absent"),
            "unresolved JSON pointer",
        ),
        (
            lambda b: b["lessons"][0]["observations"][0].update(
                evidence=[{"source": "observation", "lines": [1, 9999]}]
            ),
            "out of bounds",
        ),
        (lambda b: b["lessons"][0]["reasoning"].update(status="definitely_true"), "epistemic status"),
        (lambda b: b["lessons"][1].update(id="L1"), "duplicate lesson"),
        (lambda b: b["sources"]["observation"].update(sha256="0" * 64), "SHA mismatch"),
    ],
)
def test_bad_extraction_rejected(case, mutation, reason):
    mutation(case.bundle)
    save(case.bp, case.bundle)
    with pytest.raises(ValueError, match=reason):
        reflux.validate(case.bp, case.manifest)


def test_changed_original_bytes_rejected(case):
    (case.root / "observations.json").write_text('{"old_pitch": 128}')
    with pytest.raises(ValueError, match="SHA mismatch"):
        reflux.validate(case.bp, case.manifest)


def test_retained_baseline_summary_cannot_replace_candidate(case):
    p = save(case.root / "retained.json", {"effective_geomean_speedup": 1., "total_case_count": 2})
    case.bundle["sources"]["retained"] = reflux.file_ref(p)
    case.bundle["rounds"][0]["performance"].update(source="retained", geomean_speedup=1.)
    save(case.bp, case.bundle)
    with pytest.raises(ValueError, match="actual candidate summary"):
        reflux.validate(case.bp, case.manifest)


@pytest.mark.parametrize("mutation,reason", [
    (lambda r: r.update(reviewer="fixture-author"), "author cannot"),
    (lambda r: r["dimensions"]["conditions"].update(score=2), "below 3/4"),
    (lambda r: [v.update(score=3) for v in r["dimensions"].values()], "below 85"),
    (lambda r: r.update(critical_errors=["invented speedup"]), "critical experience errors"),
    (lambda r: r["reader_tests"][0].update(dangerous=True), "dangerous reader"),
    (lambda r: r["reader_tests"][0].update(score=0), "below 87.5"),
    (lambda r: r["reader_tests"][0].update(category="reject"), "decision diversity"),
    (lambda r: [v.update(lesson_ids=["L1"]) for v in r["reader_tests"]], "cover all lessons"),
    (lambda r: r["dimensions"]["conditions"].update(evidence=[]), "lacks evidence"),
])
def test_bad_reviews_cannot_self_declare_pass(case, mutation, reason):
    mutation(case.review)
    case.review["status"] = "pass"
    save(case.rp, case.review)
    with pytest.raises(ValueError, match=reason):
        reflux.validate(case.bp, case.manifest, material_path=case.material, review_path=case.rp)


def test_review_is_bound_to_exact_bundle_bytes(case):
    case.bundle["lessons"][0]["decision"] += " Additional changed advice."
    save(case.bp, case.bundle)
    case.material.write_text(reflux.render(case.bundle))
    with pytest.raises(ValueError, match="different bundle"):
        reflux.validate(case.bp, case.manifest, material_path=case.material, review_path=case.rp)


def test_path_inventory_cannot_replace_reviewed_prose(case):
    case.material.write_text("# Report\n" + "\n".join(case.bundle["sources"]))
    with pytest.raises(ValueError, match="material differs"):
        reflux.validate(case.bp, case.manifest, material_path=case.material, review_path=case.rp)


def test_no_attempt_does_not_invent_lessons(case):
    case.state["stages"] = {}
    save(case.root / "workflow-state.json", case.state)
    case.bundle.update(
        rounds=[], lessons=[], no_attempt_reason="No eligible candidate was implemented; source evidence retained"
    )
    save(case.bp, case.bundle)
    assert reflux.validate(case.bp, case.manifest)["round_count"] == 0
    assert case.bundle["no_attempt_reason"] in reflux.render(case.bundle)


@pytest.mark.parametrize("pointer", ["/-1", "/01", "/+1", "/1~2", "/1~"])
def test_invalid_pointer_cannot_anchor_a_different_fact(pointer):
    with pytest.raises(ValueError, match="JSON pointer"):
        reflux.pointer(["first", "second"], pointer)


def test_rfc_pointer_handles_escaped_keys():
    assert reflux.pointer({"a/b": {"~": ["first"]}}, "/a~1b/~0/0") == "first"


def test_new_policy_missing_material_blocks_integration(case):
    with pytest.raises(ValueError, match="integration requires experience"):
        reflux.integration_artifacts({}, case.manifest)


def test_old_manifest_remains_compatible(case):
    manifest = reflux.load(case.manifest)
    del manifest["configuration"]["experience_policy"]
    save(case.manifest, manifest)
    assert reflux.integration_artifacts({}, case.manifest) == []


def test_actual_raw_card_is_bound_to_reviewed_material(case):
    result = reflux.validate(case.bp, case.manifest, material_path=case.material,
                             review_path=case.rp, reflux_path=case.export)
    assert result["status"] == "pass" and result["export_verified"]
    assert reflux.file_ref(case.card) in result["dependencies"]


@pytest.mark.parametrize("change", ["path_inventory", "truncated", "stale_material", "stale_review"])
def test_bad_raw_export_cannot_pass_using_a_good_intermediate_review(case, change):
    record = reflux.load(case.export)
    if change in ("path_inventory", "truncated"):
        case.card.write_text(
            "\n".join(case.bundle["sources"]) if change == "path_inventory" else case.material.read_text()[:200]
        )
        record["card"] = reflux.file_ref(case.card)
    else:
        record["experience_material" if change == "stale_material" else "experience_review"]["sha256"] = "0" * 64
    save(case.export, record)
    with pytest.raises(ValueError, match="reflux"):
        reflux.validate(
            case.bp, case.manifest, material_path=case.material, review_path=case.rp, reflux_path=case.export
        )


def test_phase_completion_and_finish_require_review(case, monkeypatch):
    report = case.root / "VERIFY_REPORT.md"
    report.write_text("# Fixture integration result\n")
    monkeypatch.setattr(workflow, "_integration_artifacts", lambda *args: [])
    with pytest.raises(ValueError, match="integration requires experience"):
        workflow.check_phase_artifacts("integration", [str(report)], case.manifest)
    paths = [report, case.bp, case.material, case.rp, case.export]
    assert str(case.rp) in workflow.check_phase_artifacts("integration", list(map(str, paths)), case.manifest)
    state = {"manifest": workflow.artifact_identity(case.manifest),
             "performance_effect_policy": {"id": "median_v1", "version": 1},
             "experience_policy": dict(reflux.LEGACY_POLICY),
             "stages": {f"phase.{p}": {"status": "complete", "artifacts": []} for p in workflow.PHASES}}
    with pytest.raises(ValueError, match="integration requires experience"):
        workflow._check_phase_completion(state, SimpleNamespace(status="success"))


def test_replay_preserves_registered_material_over_same_named_export(case, monkeypatch):
    monkeypatch.setattr(workflow, "_integration_artifacts", lambda *args: [])
    report = case.root / "VERIFY_REPORT.md"
    report.write_text("# Fixture report\n")
    renamed = case.card.with_name("experience-material.md")
    case.card.rename(renamed)
    export = reflux.load(case.export)
    export["card"] = reflux.file_ref(renamed)
    save(case.export, export)
    explicit = list(map(str, (report, case.bp, case.material, case.rp, case.export)))
    closure = workflow.check_phase_artifacts("integration", explicit, case.manifest)
    assert str(renamed) in closure
    # Replay sees the appended raw card, whose metadata differs from the source.
    workflow.check_phase_artifacts("integration", closure, case.manifest)
    state = {"manifest": workflow.artifact_identity(case.manifest),
             "performance_effect_policy": {"id": "median_v1", "version": 1},
             "experience_policy": dict(reflux.LEGACY_POLICY),
             "stages": {f"phase.{p}": {"status": "complete", "artifacts": []} for p in workflow.PHASES}}
    state["stages"]["phase.integration"]["artifacts"] = [workflow.artifact_identity(p) for p in closure]
    workflow._check_phase_completion(state, SimpleNamespace(status="success"))


def test_verify_rechecks_semantic_gate_even_if_sha_index_was_rewritten(case, monkeypatch):
    monkeypatch.setattr(workflow, "_integration_artifacts", lambda *args: [])
    case.review["critical_errors"] = ["A critical reader error remains"]
    save(case.rp, case.review)
    report = case.root / "VERIFY_REPORT.md"
    report.write_text("# Fixture report\n")
    record = {"status": "complete", "artifacts": [workflow.artifact_identity(p)
              for p in (report, case.bp, case.material, case.rp, case.export)]}
    invalid = []
    workflow._verify_stage_evidence({"manifest": workflow.artifact_identity(case.manifest)},
                                   "phase.integration", record, invalid)
    assert invalid and record["status"] == "invalid"


@pytest.mark.parametrize(
    "value",
    [
        None,
        {},
        {"id": "wrong", "version": 1},
        {"id": "evidence_lessons_v1", "version": True},
        {"id": "evidence_lessons_v1", "version": 2},
    ],
)
def test_invalid_policy_rejected(value):
    with pytest.raises(ValueError, match="experience_policy"):
        reflux.validate_policy(value)


def test_policy_cannot_be_silently_removed_after_state_initialization(case):
    manifest = reflux.load(case.manifest)
    state = workflow._new_state(manifest, workflow.artifact_identity(case.manifest), workflow.WORKFLOW_VERSION)
    assert state["experience_policy"] == reflux.LEGACY_POLICY
    manifest["configuration"].pop("experience_policy")
    with pytest.raises(ValueError, match="experience policy changed"):
        workflow.validate_frozen_effect_policy(state, manifest)


def test_request_creation_freezes_policy_and_legacy_omission_is_preserved(tmp_path):
    from test_schedule_policy import request_fixture
    from test_prepare_case_sets import run
    from prepare_case_sets import load_request, load_manifest
    request = request_fixture(tmp_path)
    assert load_request(request)["experience_policy"] == reflux.POLICY
    run("freeze", "--request", request, "--output-dir", tmp_path / "new-run")
    assert load_manifest(tmp_path / "new-run/run-manifest.json")["configuration"]["experience_policy"] == reflux.POLICY
    body = reflux.load(request)
    body.pop("experience_policy")
    save(request, body)
    run("freeze", "--request", request, "--output-dir", tmp_path / "old-run")
    assert "experience_policy" not in load_manifest(tmp_path / "old-run/run-manifest.json")["configuration"]


def test_cli_cannot_overwrite_evidence(case, monkeypatch):
    source = case.root / "observations.json"
    before = source.read_bytes()
    monkeypatch.setattr(sys, "argv", ["experience_reflux", "render", "--bundle", str(case.bp),
                                    "--manifest", str(case.manifest), "--out", str(source)])
    assert reflux.main() == 2
    assert source.read_bytes() == before


def test_installed_gate_runs_without_source_checkout_imports(case, installed_search):
    output = installed_python(installed_search,
        "import experience_reflux as e; import workflow_state; "
        "print(e.validate(sys.argv[2], sys.argv[3], material_path=sys.argv[4], "
        "review_path=sys.argv[5])['status'])", case.bp, case.manifest, case.material, case.rp)
    assert output.strip() == "pass"
    assert (installed_search["skills"] / "ops-perf-postprocess/references/experience-reflux.md").is_file()
