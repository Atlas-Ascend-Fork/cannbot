# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Behavioral checks for target freezing and full-inventory regression gates."""

from __future__ import annotations

import csv
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "ops-perf-optimize-workflow" / "scripts"))
from build_performance_targets import build, validate_reference  # noqa: E402
from prepare_case_sets import code_identity, identity  # noqa: E402
from validate_execution_identity import file_identity, record  # noqa: E402
from validate_postprocess_performance import validate  # noqa: E402
from workflow_state import check_phase_artifacts  # noqa: E402


EXPECTED_ERROR_RESULT = {
    "results": [
        {
            "case_id": "f_error",
            "status": "PASS",
            "expected_substring": "bad input",
            "error_excerpt": "bad input: value 2",
        }
    ]
}


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return path


def table(path, rows):
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path


def fixture(tmp_path, *, directory=False):
    performance = table(
        tmp_path / "performance-full.csv", [{"case_id": "p1"}, {"case_id": "p2"}]
    )
    functional = table(
        tmp_path / "functional-full.csv", [{"case_id": "f1"}, {"case_id": "f2"}]
    )
    if directory:
        inventory = tmp_path / "functional-dir"
        inventory.mkdir()
        functional.rename(inventory / "cases.csv")
        functional = inventory
    request = dump(tmp_path / "request.json", {})
    manifest = dump(
        tmp_path / "manifest.json",
        {
            "schema_version": 2,
            "request": identity(request),
            "inputs": {},
            "configuration": {
                "target_socs": ["Ascend950"],
                "performance_reference": {"kind": "theoretical", "target_ratio": 0.8},
                "precision_diagnosis_policy": "persistent",
                "tuning_mode": "standard",
                "workflow_layout": "five-stage-v1",
            },
            "collections": {
                "performance_full": identity(performance),
                "functional_full": identity(functional),
            },
        },
    )
    raw = dump(tmp_path / "roofline.json", {"source": "synthetic test evidence"})
    evidence = dump(
        tmp_path / "evidence.json",
        {
            "cases": [
                {
                    "case_id": case,
                    "target_soc": "Ascend950",
                    "kind": "theoretical",
                    "reference_us": value,
                    "method": "test model",
                    "source_artifacts": [str(raw)],
                }
                for case, value in [("p1", 8), ("p2", 16)]
            ]
        },
    )
    return manifest, evidence


def profiles(tmp_path, *, functional=(100, 100), performance=(100, 100)):
    paths = {}
    for kind, prefix, after in [
        ("functional", "f", functional),
        ("performance", "p", performance),
    ]:
        baseline = table(
            tmp_path / f"{kind}-before.csv",
            [{"case_id": f"{prefix}{i}", "total_us": 100} for i in (1, 2)],
        )
        candidate = table(
            tmp_path / f"{kind}-after.csv",
            [{"case_id": f"{prefix}{i}", "total_us": after[i - 1]} for i in (1, 2)],
        )
        paths[kind] = (baseline, candidate)
    return paths


def mixed_expected_error_fixture(tmp_path):
    manifest, _ = fixture(tmp_path)
    functional = table(
        tmp_path / "functional-full.csv",
        [
            {"case_id": "f1", "is_enabled": "True", "expected_error": ""},
            {
                "case_id": "f_error",
                "is_enabled": "False",
                "expected_error": "bad input",
            },
        ],
    )
    data = json.loads(manifest.read_text())
    data["collections"]["functional_full"] = identity(functional)
    dump(manifest, data)
    paths = profiles(tmp_path)
    for path in paths["functional"]:
        table(path, [{"case_id": "f1", "total_us": 100}])
    outcomes = (
        dump(
            tmp_path / "errors-before.json",
            EXPECTED_ERROR_RESULT,
        ),
        dump(
            tmp_path / "errors-after.json",
            EXPECTED_ERROR_RESULT,
        ),
    )
    return manifest, paths, outcomes


def test_target_latency_and_evidence_identity(tmp_path):
    manifest, evidence = fixture(tmp_path)
    result = build(manifest, evidence)
    assert [row["target_us"] for row in result["cases"]] == [10, 20]
    original = result["cases"][0]["source_artifacts"][0]
    Path(original["path"]).write_text("changed model")
    assert build(manifest, evidence)["cases"][0]["source_artifacts"][0] != original


@pytest.mark.parametrize(
    "mutation",
    ["missing", "duplicate", "extra_soc", "nan", "zero", "wrong_kind", "no_source"],
)
def test_invalid_or_incomplete_targets_are_rejected(tmp_path, mutation):
    manifest, evidence = fixture(tmp_path)
    data = json.loads(evidence.read_text())
    if mutation == "missing":
        data["cases"].pop()
    elif mutation == "duplicate":
        data["cases"].append(data["cases"][0])
    elif mutation == "extra_soc":
        data["cases"][0]["target_soc"] = "Ascend910B"
    elif mutation == "nan":
        data["cases"][0]["reference_us"] = float("nan")
    elif mutation == "zero":
        data["cases"][0]["reference_us"] = 0
    elif mutation == "wrong_kind":
        data["cases"][0]["kind"] = "xpu"
    else:
        data["cases"][0]["source_artifacts"] = []
    dump(evidence, data)
    with pytest.raises(ValueError):
        build(manifest, evidence)


@pytest.mark.parametrize(
    "kind,ratio",
    [("theoretical", 1.1), ("unfused", 0.9), ("xpu", 0), ("baseline", float("inf"))],
)
def test_invalid_reference_contract(kind, ratio):
    with pytest.raises(ValueError):
        validate_reference({"kind": kind, "target_ratio": ratio})


@pytest.mark.parametrize(
    "kind,ratio",
    [("theoretical", 0.8), ("unfused", 2), ("xpu", 0.6), ("baseline", 1.2)],
)
def test_all_reference_routes_compute_targets(tmp_path, kind, ratio):
    manifest, evidence = fixture(tmp_path)
    config = json.loads(manifest.read_text())
    config["configuration"]["performance_reference"] = {
        "kind": kind,
        "target_ratio": ratio,
    }
    dump(manifest, config)
    data = json.loads(evidence.read_text())
    for row in data["cases"]:
        row["kind"] = kind
    dump(evidence, data)
    assert build(manifest, evidence)["cases"][0]["target_us"] == 8 / ratio


def test_targets_cover_every_requested_soc(tmp_path):
    manifest, evidence = fixture(tmp_path)
    data = json.loads(manifest.read_text())
    data["configuration"]["target_socs"].append("Ascend910B")
    dump(manifest, data)
    with pytest.raises(ValueError, match="missing target evidence"):
        build(manifest, evidence)


def test_functional_only_regression_cannot_hide_behind_perf_improvements(tmp_path):
    manifest, _ = fixture(tmp_path, directory=True)
    paths = profiles(tmp_path, functional=(104, 50), performance=(50, 50))
    result = validate(manifest, "Ascend950", paths)
    assert result["decision"] == "route_required"
    assert result["collections"]["functional"]["regressed_case_ids"] == ["f1"]
    # Simulate a measured final binary routing f1 to legacy, preserving other gains.
    table(
        paths["functional"][1],
        [{"case_id": "f1", "total_us": 100}, {"case_id": "f2", "total_us": 50}],
    )
    assert validate(manifest, "Ascend950", paths)["decision"] == "pass"


def test_gate_requires_every_case_not_just_tuning_subset(tmp_path):
    manifest, _ = fixture(tmp_path)
    paths = profiles(tmp_path)
    for path in paths["functional"]:
        table(path, [{"case_id": "f1", "total_us": 100}])
    with pytest.raises(ValueError, match="full coverage mismatch"):
        validate(manifest, "Ascend950", paths)


def test_expected_error_rows_get_semantic_coverage_without_fabricated_time(tmp_path):
    manifest, paths, outcomes = mixed_expected_error_fixture(tmp_path)
    with pytest.raises(
        ValueError, match="require before/after functional error evidence"
    ):
        validate(manifest, "Ascend950", paths)
    gate = validate(manifest, "Ascend950", paths, functional_errors=outcomes)
    assert gate["decision"] == "pass"
    assert [
        case["case_id"]
        for case in gate["collections"]["functional"]["summary"]["cases"]
    ] == ["f1"]
    assert gate["collections"]["functional"]["expected_errors"]["candidate"][
        "case_ids"
    ] == ["f_error"]
    output = dump(tmp_path / "postprocess-performance-Ascend950.json", gate)
    report = tmp_path / "VERIFY_REPORT.md"
    report.write_text("mixed inventory report")
    assert str(outcomes[0]) in check_phase_artifacts(
        "integration", [str(output), str(report)], manifest
    )


def test_expected_error_gate_rejects_wrong_message_and_fake_timing(tmp_path):
    manifest, paths, outcomes = mixed_expected_error_fixture(tmp_path)
    dump(
        outcomes[1],
        {
            "results": [
                {
                    "case_id": "f_error",
                    "status": "PASS",
                    "expected_substring": "bad input",
                    "error_excerpt": "different error",
                }
            ]
        },
    )
    with pytest.raises(ValueError, match="message mismatch"):
        validate(manifest, "Ascend950", paths, functional_errors=outcomes)
    for path in paths["functional"]:
        table(
            path,
            [
                {"case_id": "f1", "total_us": 100},
                {"case_id": "f_error", "total_us": 1},
            ],
        )
    with pytest.raises(ValueError, match="full coverage mismatch"):
        validate(manifest, "Ascend950", paths, functional_errors=outcomes)


def test_gate_honors_existing_jitter_policy_and_soc_scope(tmp_path):
    manifest, _ = fixture(tmp_path)
    paths = profiles(tmp_path, functional=(103, 100))
    assert validate(manifest, "Ascend950", paths)["decision"] == "pass"
    with pytest.raises(ValueError, match="TARGET_SOCS"):
        validate(manifest, "Ascend910B", paths)


def test_regression_gate_cli_fails_and_records_routes_required(tmp_path):
    manifest, _ = fixture(tmp_path)
    paths = profiles(tmp_path, performance=(150, 50))
    out = tmp_path / "gate.json"
    args = [
        sys.executable,
        str(ROOT / "skills" / "ops-perf-optimize-workflow" / "scripts/validate_postprocess_performance.py"),
        "--manifest",
        str(manifest),
        "--target-soc",
        "Ascend950",
        "--out",
        str(out),
    ]
    for kind, (baseline, candidate) in paths.items():
        args.extend(
            [f"--baseline-{kind}", str(baseline), f"--candidate-{kind}", str(candidate)]
        )
    result = subprocess.run(args, capture_output=True, text=True)
    assert result.returncode == 2
    assert json.loads(out.read_text())["collections"]["performance"][
        "regressed_case_ids"
    ] == ["p1"]


def test_phase_gate_recomputes_csv_instead_of_trusting_pass_label(tmp_path):
    manifest, _ = fixture(tmp_path)
    paths = profiles(tmp_path)
    gate = dump(
        tmp_path / "postprocess-performance-Ascend950.json",
        validate(manifest, "Ascend950", paths),
    )
    report = tmp_path / "VERIFY_REPORT.md"
    report.write_text("synthetic test report")
    assert str(paths["functional"][0]) in check_phase_artifacts(
        "integration", [str(gate), str(report)], manifest
    )
    table(
        paths["functional"][1],
        [{"case_id": "f1", "total_us": 150}, {"case_id": "f2", "total_us": 100}],
    )
    with pytest.raises(ValueError, match="stale or has regressions"):
        check_phase_artifacts("integration", [str(gate), str(report)], manifest)


def test_workflow_cannot_skip_baseline_or_finish_early(tmp_path):
    manifest, _ = fixture(tmp_path)
    state = tmp_path / "state.json"
    cli = [sys.executable, str(ROOT / "skills" / "ops-perf-optimize-workflow" / "scripts/workflow_state.py")]
    subprocess.run(
        cli + ["start", "--state", str(state), "--manifest", str(manifest)],
        check=True,
        capture_output=True,
    )
    attempt = subprocess.run(
        cli
        + [
            "mark",
            "--state",
            str(state),
            "--stage",
            "phase.preparation",
            "--status",
            "in_progress",
        ],
        capture_output=True,
        text=True,
    )
    assert attempt.returncode != 0 and "prerequisite" in attempt.stdout
    attempt = subprocess.run(
        cli
        + [
            "finish",
            "--state",
            str(state),
            "--status",
            "success",
            "--reason-code",
            "completed",
            "--message",
            "synthetic test completion",
        ],
        capture_output=True,
        text=True,
    )
    assert attempt.returncode != 0 and "incomplete" in attempt.stdout


def test_five_roles_dispatch_to_generic_subagent_without_named_experts():
    manifest = json.loads((ROOT / ".claude-plugin/plugin.json").read_text())
    assert manifest.get("agents", []) == ["./AGENTS.md"]
    assert not (ROOT / "agents").exists()
    contract = (
        ROOT / "skills/ops-perf-optimize-workflow/references/workflow-contract.md"
    ).read_text()
    assert "通用 subagent" in contract
    for skill in (
        "ops-perf-baseline-evaluate",
        "ops-perf-preparation",
        "ops-perf-analysis",
        "ops-perf-implementation",
        "ops-perf-postprocess",
    ):
        assert (ROOT / "skills" / skill / "SKILL.md").is_file(), skill
    assert "ops/ops-theoretical-performance-estimation" in (
        ROOT / "plugin-sources.json"
    ).read_text()


def phase_files(tmp_path, preflight, targets, gate):
    def note(name):
        path = tmp_path / name
        path.write_text("{}" if name.endswith(".json") else "# synthetic test artifact")
        return path

    return {
        "baseline": [preflight, targets, note("环境检查报告.md"), note("性能目标.md")],
        "preparation": [
            note("extraction-manifest.json"),
            note("source-compatibility.md"),
            note("functional-acceptance.md"),
        ],
        "analysis": [note("analysis.md")],
        "implementation": [
            note("final-functional-regression.md"),
            note("final-performance-comparison.md"),
        ],
        "integration": [gate, note("VERIFY_REPORT.md")],
    }


def test_complete_phase_lifecycle_freezes_source_evidence(tmp_path):
    manifest, evidence = fixture(tmp_path)
    state = tmp_path / "state.json"
    cli = [sys.executable, str(ROOT / "skills" / "ops-perf-optimize-workflow" / "scripts/workflow_state.py")]

    def run(*args):
        result = subprocess.run(cli + list(args), capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr
        return json.loads(result.stdout)

    run("start", "--state", str(state), "--manifest", str(manifest))
    request_sha = json.loads(manifest.read_text())["request"]["sha256"]
    preflight = dump(
        tmp_path / "preflight-report.json",
        {"status": "warn", "fail_count": 0, "request_sha256": request_sha},
    )
    targets = dump(tmp_path / "performance-targets.json", build(manifest, evidence))
    paths = profiles(tmp_path)
    gate = dump(
        tmp_path / "postprocess-performance-Ascend950.json",
        validate(manifest, "Ascend950", paths),
    )

    for phase, artifacts in phase_files(tmp_path, preflight, targets, gate).items():
        args = ["mark", "--state", str(state), "--stage", f"phase.{phase}"]
        run(*args, "--status", "in_progress")
        for artifact in artifacts:
            args.extend(["--artifact", str(artifact)])
        run(*args, "--status", "complete")
    finish = [
        "finish",
        "--state",
        str(state),
        "--status",
        "success",
        "--reason-code",
        "completed",
        "--message",
        "test only",
    ]
    assert run(*finish)["status"] == "success"
    (tmp_path / "roofline.json").write_text("mutated evidence")
    attempt = subprocess.run(cli + finish, capture_output=True, text=True)
    assert attempt.returncode != 0 and "artifact changed" in attempt.stdout


def record_baseline_identity(tmp_path, manifest):
    built = tmp_path / "build" / "libop.so"
    loaded = tmp_path / "runtime" / "libop.so"
    built.parent.mkdir()
    loaded.parent.mkdir()
    built.write_bytes(b"operator")
    loaded.write_bytes(built.read_bytes())
    build_log = tmp_path / "build.log"
    build_log.write_text("ok\n")
    loader_log = tmp_path / "loader.log"
    loader_log.write_text(f"loaded {loaded.resolve()}\n")
    runtime = dump(
        tmp_path / "runtime-evidence.json",
        {
            "method": "loader trace",
            "target_soc": "Ascend950",
            "source_artifacts": [file_identity(loader_log)],
            "loaded_artifacts": [file_identity(loaded)],
        },
    )
    execution_identity = tmp_path / "execution-identity.json"
    result = record(
        SimpleNamespace(
            manifest=manifest,
            target_soc="Ascend950",
            build_command="build operator",
            build_log=build_log,
            built_artifact=[built],
            runtime_evidence=runtime,
            out=execution_identity,
        )
    )
    assert result["status"] == "complete"
    return execution_identity, build_log, loader_log, runtime


def test_baseline_reference_requires_valid_execution_identity(tmp_path):
    manifest, evidence = fixture(tmp_path)
    source = tmp_path / "source"
    source.mkdir()
    (source / "kernel.cpp").write_text("void kernel() {}\n")
    manifest_data = json.loads(manifest.read_text())
    manifest_data["inputs"]["code"] = code_identity(source)
    manifest_data["configuration"]["performance_reference"] = {
        "kind": "baseline",
        "target_ratio": 1.0,
    }
    manifest.write_text(json.dumps(manifest_data))
    evidence_data = json.loads(evidence.read_text())
    for case in evidence_data["cases"]:
        case["kind"] = "baseline"
    evidence.write_text(json.dumps(evidence_data))

    preflight = dump(
        tmp_path / "preflight-report.json",
        {
            "status": "pass",
            "fail_count": 0,
            "request_sha256": manifest_data["request"]["sha256"],
        },
    )
    targets = dump(tmp_path / "performance-targets.json", build(manifest, evidence))
    artifacts = [
        str(preflight),
        str(targets),
        str(dump(tmp_path / "环境检查报告.md", {})),
        str(dump(tmp_path / "性能目标.md", {})),
    ]
    with pytest.raises(ValueError, match="execution-identity.json"):
        check_phase_artifacts("baseline", artifacts, manifest)

    execution_identity, build_log, loader_log, runtime = record_baseline_identity(tmp_path, manifest)
    frozen = check_phase_artifacts(
        "baseline", artifacts + [str(execution_identity)], manifest
    )
    assert str(build_log.resolve()) in frozen
    assert str(loader_log.resolve()) in frozen
    assert str(runtime.resolve()) in frozen


def test_target_cli_writes_reviewable_markdown_and_machine_evidence(tmp_path):
    manifest, evidence = fixture(tmp_path)
    out, md = tmp_path / "performance-targets.json", tmp_path / "性能目标.md"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "skills" / "ops-perf-optimize-workflow" / "scripts/build_performance_targets.py"),
            "--manifest",
            str(manifest),
            "--evidence",
            str(evidence),
            "--out",
            str(out),
            "--out-md",
            str(md),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert [row["target_us"] for row in json.loads(out.read_text())["cases"]] == [
        10,
        20,
    ]
    assert "p1" in md.read_text() and "p2" in md.read_text()
