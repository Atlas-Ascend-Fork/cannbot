# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

from __future__ import annotations

import csv
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "skills" / "ops-perf-optimize-workflow" / "scripts" / "prepare_case_sets.py"
STATE_TOOL = ROOT / "skills" / "ops-perf-optimize-workflow" / "scripts" / "workflow_state.py"


def write_cases(path: Path, count: int, *, include_l1: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["case_id", "shape", "dtype", "mode", "level"])
        writer.writeheader()
        for index in range(count):
            writer.writerow(
                {
                    "case_id": f"case-{index:03d}",
                    "shape": f"[{1 if index % 7 == 0 else index + 2}, {16 if index % 2 == 0 else 17}]",
                    "dtype": "float16" if index % 3 else "float32",
                    "mode": "tail" if index % 2 else "aligned",
                    "level": "L1" if include_l1 and index == count - 1 else "L0",
                }
            )


def write_competitor(path: Path, count: int, *, alias_columns: bool = False) -> None:
    id_field = "testcase_name" if alias_columns else "case_id"
    time_field = "gpu_time_us" if alias_columns else "gpu_total_us"
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=[id_field, time_field])
        writer.writeheader()
        for index in range(count):
            writer.writerow({id_field: f"case-{index:03d}", time_field: str(index + 1.5)})


def run(*args: str | Path) -> dict:
    result = subprocess.run(
        [sys.executable, str(TOOL), *(str(arg) for arg in args)],
        check=True,
        text=True,
        capture_output=True,
    )
    return json.loads(result.stdout)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def create_request(
    path: Path,
    code: Path,
    performance: Path | None,
    *,
    functional_mode: str | None = "reuse_performance",
    functional_cases: Path | None = None,
    extra: tuple[str, ...] = (),
) -> dict:
    args: list[str | Path] = [
        "create-request",
        "--request",
        path,
        "--operator-name",
        "test_op",
        "--target-soc",
        "Ascend950",
        "--code-dir",
        code,
        "--python-executable",
        sys.executable,
        "--cann-env-command",
        "inherit",
        *extra,
    ]
    if functional_mode:
        args.extend(("--functional-mode", functional_mode))
    if performance:
        args.extend(("--performance-cases", performance))
    if functional_cases:
        args.extend(("--functional-cases", functional_cases))
    return run(*args)


def test_large_performance_selection_is_deterministic_and_confirmed_explicitly(tmp_path: Path) -> None:
    code = tmp_path / "code"
    code.mkdir()
    (code / "kernel.cpp").write_text("// kernel\n", encoding="utf-8")
    cases = tmp_path / "performance.csv"
    write_cases(cases, 60)
    request = tmp_path / "optimization-request.json"
    result = create_request(request, code, cases)
    assert result["summary"]["optimization_objective"] == {"mode": "fixed_rounds", "rounds": 3}
    assert result["summary"]["target_socs"] == ["Ascend950"]
    assert "precision_diagnosis_policy" not in result["summary"]
    assert result["summary"]["python"]["executable"] == str(Path(sys.executable).resolve())
    assert result["summary"]["cann"]["setup_command"] == "inherit"
    assert "precision_diagnosis_policy" not in load(request)
    assert run("validate-request", "--request", request)["status"] == "valid"

    selections = []
    for name in ("run-a", "run-b"):
        output = tmp_path / name
        result = run(
            "freeze",
            "--output-dir",
            output,
            "--request",
            request,
        )
        assert result["confirmation"] == "pending"
        manifest = load(output / "run-manifest.json")
        assert manifest["collections"]["performance_full"]["count"] == 60
        tuning = manifest["collections"]["performance_tuning"]
        assert tuning["count"] == 50
        assert tuning["selection"]["algorithm"] == "coverage-v1"
        assert tuning["selection"]["confirmation"] == "pending"
        assert manifest["configuration"]["optimization_objective"]["rounds"] == 3
        assert manifest["configuration"]["target_socs"] == ["Ascend950"]
        assert load(output / "optimization-request.json") == load(request)
        selections.append([item["case_id"] for item in tuning["selection"]["selected"]])
    assert selections[0] == selections[1]

    manifest_path = tmp_path / "run-a" / "run-manifest.json"
    run("confirm-performance", "--manifest", manifest_path, "--by", "user")
    assert load(manifest_path)["collections"]["performance_tuning"]["selection"]["confirmation"] == "confirmed"


def test_existing_inventory_freezes_full_set_and_selects_only_l0(tmp_path: Path) -> None:
    code = tmp_path / "code"
    code.mkdir()
    (code / "kernel.cpp").write_text("// kernel\n", encoding="utf-8")
    performance = tmp_path / "performance.csv"
    functional = tmp_path / "functional.csv"
    write_cases(performance, 5)
    write_cases(functional, 46, include_l1=True)
    output = tmp_path / "run"
    request = tmp_path / "existing-request.json"
    create_request(
        request,
        code,
        performance,
        functional_mode="existing",
        functional_cases=functional,
    )

    run(
        "freeze",
        "--output-dir",
        output,
        "--request",
        request,
    )
    manifest = load(output / "run-manifest.json")
    assert manifest["configuration"]["precision_diagnosis_policy"] == "persistent"
    assert manifest["collections"]["functional_full"]["count"] == 46
    acceptance = manifest["collections"]["functional_acceptance"]
    assert acceptance["count"] == 40
    assert acceptance["selection"]["l0_count"] == 45
    with (output / "baseline" / "functional-acceptance-cases.csv").open(encoding="utf-8") as stream:
        assert {row["level"] for row in csv.DictReader(stream)} == {"L0"}


def test_generate_mode_attaches_inventory_without_a_second_manifest(tmp_path: Path) -> None:
    code = tmp_path / "code"
    code.mkdir()
    (code / "kernel.cpp").write_text("// kernel\n", encoding="utf-8")
    performance = tmp_path / "performance.csv"
    generated = tmp_path / "generated.csv"
    write_cases(performance, 3)
    write_cases(generated, 4, include_l1=True)
    output = tmp_path / "run"
    request = tmp_path / "generate-request.json"
    create_request(request, code, performance, functional_mode="generate")

    run(
        "freeze",
        "--output-dir",
        output,
        "--request",
        request,
    )
    manifest_path = output / "run-manifest.json"
    assert load(manifest_path)["functional_preparation"]["status"] == "pending"
    run("attach-functional", "--manifest", manifest_path, "--functional-cases", generated)
    manifest = load(manifest_path)
    assert manifest["functional_preparation"]["status"] == "complete"
    assert manifest["collections"]["functional_full"]["count"] == 4
    assert manifest["collections"]["functional_acceptance"]["count"] == 3
    assert not (output / "functional-preparation.json").exists()
    assert not (output / "functional-acceptance-selection.json").exists()


def test_target_objective_and_environment_are_reusable(tmp_path: Path) -> None:
    code = tmp_path / "code"
    code.mkdir()
    (code / "kernel.cpp").write_text("// kernel\n", encoding="utf-8")
    performance = tmp_path / "performance.csv"
    write_cases(performance, 2)
    request = tmp_path / "target-request.json"

    create_request(
        request,
        code,
        performance,
        extra=(
            "--optimization-mode",
            "target",
            "--target-metric",
            "effective_geomean_speedup",
            "--target-comparison",
            "ge",
            "--target-value",
            "1.2",
            "--target-unit",
            "ratio",
            "--max-rounds",
            "5",
            "--python-activation-command",
            "source /opt/venv/bin/activate",
        ),
    )
    payload = load(request)
    assert payload["optimization_objective"] == {
        "mode": "target",
        "metric": "effective_geomean_speedup",
        "comparison": "ge",
        "value": 1.2,
        "unit": "ratio",
        "max_rounds": 5,
    }
    assert payload["environments"]["python"]["activation_command"] == "source /opt/venv/bin/activate"
    assert payload["confirmation"]["status"] == "confirmed"

    for name in ("first", "second"):
        output = tmp_path / name
        run("freeze", "--output-dir", output, "--request", request)
        manifest = load(output / "run-manifest.json")
        assert manifest["configuration"]["optimization_objective"]["value"] == 1.2
        assert manifest["configuration"]["environments"]["cann"]["setup_command"] == "inherit"


def test_unconfirmed_request_is_rejected(tmp_path: Path) -> None:
    code = tmp_path / "code"
    code.mkdir()
    performance = tmp_path / "performance.csv"
    write_cases(performance, 1)
    request = tmp_path / "request.json"
    create_request(request, code, performance)
    payload = load(request)
    payload["confirmation"]["status"] = "pending"
    request.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(TOOL), "freeze", "--output-dir", str(tmp_path / "run"), "--request", str(request)],
        check=False,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 2
    assert "must be confirmed" in result.stdout


def test_precision_diagnosis_policy_is_not_a_request_input() -> None:
    result = subprocess.run(
        [sys.executable, str(TOOL), "create-request", "--help"],
        check=True,
        text=True,
        capture_output=True,
    )
    assert "precision-diagnosis-policy" not in result.stdout


def test_changed_inherited_cann_environment_is_rejected(tmp_path: Path) -> None:
    code = tmp_path / "code"
    code.mkdir()
    performance = tmp_path / "performance.csv"
    write_cases(performance, 1)
    request = tmp_path / "request.json"
    create_request(request, code, performance)
    payload = load(request)
    snapshot = payload["environments"]["cann"]["snapshot_at_confirmation"]
    snapshot["ASCEND_HOME_PATH"] = f"{snapshot['ASCEND_HOME_PATH'] or ''}/changed"
    request.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(TOOL), "validate-request", "--request", str(request)],
        check=False,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 2
    assert "inherited CANN environment changed" in result.stdout


def start_state(output: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            str(STATE_TOOL),
            "start",
            "--state",
            str(output / "workflow-state.json"),
            "--manifest",
            str(output / "run-manifest.json"),
        ],
        check=True,
        text=True,
        capture_output=True,
    )


def test_generalization_provided_inventory_and_file_competitor_are_frozen(tmp_path: Path) -> None:
    code = tmp_path / "code"
    code.mkdir()
    (code / "kernel.cpp").write_text("// kernel\n", encoding="utf-8")
    cases = tmp_path / "generalization.csv"
    competitor = tmp_path / "competitor.csv"
    write_cases(cases, 45, include_l1=True)
    write_competitor(competitor, 45)
    request = tmp_path / "generalization-request.json"

    result = create_request(
        request,
        code,
        cases,
        functional_mode=None,
        extra=(
            "--tuning-mode",
            "generalization",
            "--competitor-perf",
            str(competitor),
        ),
    )
    assert result["summary"]["tuning_mode"] == "generalization"

    output = tmp_path / "run"
    run("freeze", "--output-dir", output, "--request", request)
    manifest = load(output / "run-manifest.json")
    assert manifest["configuration"]["tuning_mode"] == "generalization"
    assert manifest["configuration"]["functional_mode"] == "reuse_performance"
    assert manifest["collections"]["generalization_full"]["count"] == 45
    assert manifest["collections"]["functional_full"]["shared_with"] == "generalization_full"
    assert manifest["collections"]["functional_acceptance"]["count"] == 40
    assert manifest["collections"]["competitor_performance"]["count"] == 45
    assert manifest["collections"]["competitor_performance"]["validation"] == {
        "status": "complete",
        "matched_count": 45,
    }
    assert manifest["generalization_preparation"]["competitor"]["status"] == "complete"
    start_state(output)
    report = (output / "性能调优报告.md").read_text(encoding="utf-8")
    assert "调优模式：`generalization`" in report
    assert "竞品来源：`file`" in report
    assert "泛化全集 | 45" in report


def test_generalization_generated_cases_and_external_competitor_are_attached(tmp_path: Path) -> None:
    code = tmp_path / "code"
    code.mkdir()
    (code / "kernel.cpp").write_text("// kernel\n", encoding="utf-8")
    request = tmp_path / "generalization-request.json"
    early_competitor = tmp_path / "early-competitor.csv"
    write_competitor(early_competitor, 4)
    create_request(
        request,
        code,
        None,
        functional_mode=None,
        extra=(
            "--tuning-mode",
            "generalization",
            "--competitor-source",
            "file",
            "--competitor-perf",
            str(early_competitor),
        ),
    )
    output = tmp_path / "run"
    run("freeze", "--output-dir", output, "--request", request)
    manifest_path = output / "run-manifest.json"
    pending = load(manifest_path)
    assert pending["generalization_preparation"] == {
        "cases": {"status": "pending"},
        "competitor": {"status": "pending_cases"},
    }
    assert pending["configuration"]["generalization"]["target_case_count"] == 1000
    assert pending["configuration"]["functional_mode"] == "reuse_performance"

    generated = tmp_path / "generated.csv"
    write_cases(generated, 4)
    run("attach-generalization", "--manifest", manifest_path, "--cases", generated)
    manifest = load(manifest_path)
    assert manifest["collections"]["generalization_full"]["count"] == 4
    assert manifest["collections"]["competitor_performance"]["validation"]["status"] == "complete"
    assert manifest["generalization_preparation"]["cases"]["status"] == "complete"
    assert manifest["generalization_preparation"]["competitor"]["status"] == "complete"
    with (output / "baseline" / "competitor-performance.csv").open(encoding="utf-8") as stream:
        assert csv.DictReader(stream).fieldnames == ["case_id", "gpu_total_us"]


def run_create_request(tmp_path: Path, extra: tuple[str, ...]) -> subprocess.CompletedProcess:
    code = tmp_path / "code"
    code.mkdir()
    cases = tmp_path / "cases.csv"
    write_cases(cases, 1)
    return subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "create-request",
            "--request",
            str(tmp_path / "request.json"),
            "--code-dir",
            str(code),
            "--performance-cases",
            str(cases),
            *extra,
        ],
        check=False,
        text=True,
        capture_output=True,
    )


def test_generalization_rejects_non_reuse_functional_mode(tmp_path: Path) -> None:
    result = run_create_request(
        tmp_path,
        (
            "--target-soc",
            "Ascend950",
            "--tuning-mode",
            "generalization",
            "--functional-mode",
            "generate",
            "--competitor-perf",
            str(tmp_path / "cases.csv"),
            "--cann-env-command",
            "inherit",
        ),
    )
    assert result.returncode == 2
    assert "fixes functional mode to reuse_performance" in result.stdout


def test_target_soc_is_required_and_frozen_as_verified_scope(tmp_path: Path) -> None:
    result = run_create_request(
        tmp_path,
        (
            "--functional-mode",
            "reuse_performance",
            "--cann-env-command",
            "inherit",
        ),
    )
    assert result.returncode == 2
    assert "--target-soc" in result.stderr
    code = tmp_path / "code"
    cases = tmp_path / "cases.csv"

    request = tmp_path / "multi-soc-request.json"
    create_request(
        request,
        code,
        cases,
        extra=("--target-soc", "Ascend910B", "--target-soc", "Ascend950"),
    )
    # create_request already supplies Ascend950; duplicates are removed without
    # changing the user-confirmed order.
    assert load(request)["target_socs"] == ["Ascend950", "Ascend910B"]
    output = tmp_path / "run"
    run("freeze", "--output-dir", output, "--request", request)
    assert load(output / "run-manifest.json")["configuration"]["target_socs"] == [
        "Ascend950",
        "Ascend910B",
    ]


def test_reference_configuration_is_copied_into_request_and_frozen_manifest(tmp_path: Path) -> None:
    code = tmp_path / "code"
    code.mkdir()
    (code / "kernel.cpp").write_text("// original\n")
    cases = tmp_path / "cases.csv"
    write_cases(cases, 2)
    reference = tmp_path / "reference.json"
    reference.write_text(json.dumps({"kind": "unfused", "target_ratio": 2.0}))
    request = tmp_path / "request.json"
    create_request(request, code, cases, extra=("--performance-reference", str(reference)))
    # External config edits do not silently change the confirmed request.
    reference.write_text(json.dumps({"kind": "unfused", "target_ratio": 3.0}))
    output = tmp_path / "run"
    run("freeze", "--request", request, "--output-dir", output)
    assert load(output / "run-manifest.json")["configuration"]["performance_reference"] == {
        "kind": "unfused", "target_ratio": 2.0,
    }


def test_new_effect_policy_default_override_and_legacy_missing_field(tmp_path: Path) -> None:
    code = tmp_path / "code"
    code.mkdir()
    (code / "kernel.cpp").write_text("// synthetic kernel\n")
    cases = tmp_path / "cases.csv"
    write_cases(cases, 2)
    request = tmp_path / "request.json"
    create_request(request, code, cases)
    assert load(request)["performance_effect_policy"] == {"id": "confidence_effect_v1", "version": 1}
    run("freeze", "--request", request, "--output-dir", tmp_path / "new")
    frozen_manifest = load(tmp_path / "new/run-manifest.json")
    assert frozen_manifest["configuration"]["performance_effect_policy"]["id"] == "confidence_effect_v1"
    create_request(request, code, cases, extra=("--performance-effect-policy", "legacy_jitter_v1"))
    assert load(request)["performance_effect_policy"]["id"] == "legacy_jitter_v1"
    legacy = load(request)
    legacy.pop("performance_effect_policy")
    request.write_text(json.dumps(legacy))
    run("freeze", "--request", request, "--output-dir", tmp_path / "legacy")
    assert "performance_effect_policy" not in load(tmp_path / "legacy/run-manifest.json")["configuration"]
