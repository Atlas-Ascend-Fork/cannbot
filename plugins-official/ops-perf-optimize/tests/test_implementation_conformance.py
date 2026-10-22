# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_implementation_conformance.py"
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("validate_implementation_conformance", SCRIPT)
assert SPEC and SPEC.loader
CONFORMANCE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONFORMANCE)


def contract() -> dict:
    return {
        "schema_version": 3,
        "scheme_id": "strategy1_global_base",
        "implementation_mode": "exact",
        "substitution_policy": "forbidden",
        "target_socs": ["Ascend950"],
        "safety": {
            "public_contract": "unchanged",
            "non_target_socs": "unchanged",
        },
        "expectations": {"vf": True, "casttrait": True},
        "required_features": [
            {"id": "reg_vf_hot_path", "description": "Keep the hot reduction in Reg VF"},
            {"id": "casttrait_fp16_bf16", "description": "Widen and narrow with CastTrait"},
        ],
    }


def make_candidate(tmp_path: Path) -> Path:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "kernel.cpp").write_text("line1\nline2\n", encoding="utf-8")
    (candidate / "compile.json").write_text("{}\n", encoding="utf-8")
    return candidate


def complete_result() -> dict:
    feature = {
        "status": "pass",
        "evidence_files": ["compile.json"],
        "source_locations": ["kernel.cpp:2"],
    }
    return {
        "schema_version": 3,
        "scheme_id": "strategy1_global_base",
        "implementation_status": "complete",
        "route_changed": False,
        "substitution_used": False,
        "features": {
            "reg_vf_hot_path": dict(feature),
            "casttrait_fp16_bf16": dict(feature),
        },
    }


def test_exact_complete_result_passes(tmp_path: Path) -> None:
    candidate = make_candidate(tmp_path)
    malformed, report = CONFORMANCE.validate_result(contract(), complete_result(), candidate)
    assert not malformed
    assert report["decision"] == "pass"
    assert not report["conformance_failures"]


def test_partial_implementation_cannot_be_called_complete(tmp_path: Path) -> None:
    candidate = make_candidate(tmp_path)
    result = complete_result()
    result["implementation_status"] = "partial"
    result["features"]["casttrait_fp16_bf16"]["status"] = "not_implemented"
    malformed, report = CONFORMANCE.validate_result(contract(), result, candidate)
    assert not malformed
    assert report["decision"] == "fail"
    assert "required feature casttrait_fp16_bf16 is not_implemented" in report["conformance_failures"]
    assert "implementation_status is partial, not complete" in report["conformance_failures"]


def test_substitution_is_rejected_even_when_features_claim_pass(tmp_path: Path) -> None:
    candidate = make_candidate(tmp_path)
    result = complete_result()
    result["route_changed"] = True
    result["substitution_used"] = True
    malformed, report = CONFORMANCE.validate_result(contract(), result, candidate)
    assert not malformed
    assert report["decision"] == "fail"
    assert "route_changed must be false for an exact implementation" in report["conformance_failures"]
    assert "substitution_used must be false for an exact implementation" in report["conformance_failures"]


def test_passing_feature_requires_existing_local_evidence(tmp_path: Path) -> None:
    candidate = make_candidate(tmp_path)
    result = complete_result()
    result["features"]["reg_vf_hot_path"]["evidence_files"] = ["missing.json"]
    malformed, report = CONFORMANCE.validate_result(contract(), result, candidate)
    assert malformed
    assert report["decision"] == "fail"


def test_contract_requires_machine_readable_vf_expectations() -> None:
    value = contract()
    del value["expectations"]
    try:
        CONFORMANCE.required_feature_ids(value)
    except CONFORMANCE.ContractError as error:
        assert "expectations" in str(error)
    else:
        raise AssertionError("contract without expectations should be rejected")


def test_casttrait_expectation_requires_vf() -> None:
    value = contract()
    value["expectations"] = {"vf": False, "casttrait": True}
    try:
        CONFORMANCE.required_feature_ids(value)
    except CONFORMANCE.ContractError as error:
        assert "requires expectations.vf=true" in str(error)
    else:
        raise AssertionError("CastTrait without VF should be rejected")


def test_contract_requires_target_soc_and_safety_invariants() -> None:
    value = contract()
    del value["target_socs"]
    try:
        CONFORMANCE.required_feature_ids(value)
    except CONFORMANCE.ContractError as error:
        assert "target_socs" in str(error)
    else:
        raise AssertionError("contract without target_socs should be rejected")

    value = contract()
    value["safety"]["public_contract"] = "reviewed"
    try:
        CONFORMANCE.required_feature_ids(value)
    except CONFORMANCE.ContractError as error:
        assert "public_contract" in str(error)
    else:
        raise AssertionError("contract must freeze the public contract")

    value = contract()
    value["safety"]["unexpected"] = "value"
    try:
        CONFORMANCE.required_feature_ids(value)
    except CONFORMANCE.ContractError as error:
        assert "exactly public_contract and non_target_socs" in str(error)
    else:
        raise AssertionError("contract safety schema must reject stale or unknown policy fields")


def test_contract_target_soc_must_match_run_manifest() -> None:
    manifest = {"configuration": {"target_socs": ["Ascend910B"]}}
    try:
        CONFORMANCE.validate_manifest_scope(contract(), manifest)
    except CONFORMANCE.ContractError as error:
        assert "RUN_MANIFEST" in str(error)
    else:
        raise AssertionError("implementation contract cannot broaden or switch target SoCs")


def test_candidate_safety_rejects_public_api_dtype_or_constraint_changes(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline"
    candidate = tmp_path / "candidate"
    relative = Path("op_host/op_api/aclnn_test_op.cpp")
    for root, dtype in ((baseline, "DT_FLOAT16"), (candidate, "DT_FLOAT16, DT_INT32")):
        path = root / relative
        path.parent.mkdir(parents=True)
        path.write_text(f"static auto supported = {{{dtype}}};\n", encoding="utf-8")

    safety = CONFORMANCE.validate_candidate_safety(baseline, candidate)
    assert safety["decision"] == "fail"
    assert safety["changed_public_contract_files"] == [relative.as_posix()]
    assert "public interface/constraint/dtype contract changed" in safety["failures"][0]


def test_candidate_safety_ignores_baseline_build_out_staging_artifacts(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline"
    candidate = tmp_path / "candidate"
    for root in (baseline, candidate):
        (root / "op_host").mkdir(parents=True)
        (root / "op_host/op.cpp").write_text("int op();\n", encoding="utf-8")
    for relative in (
        "build_out/_CPack_Packages/Linux/External/custom_opp.run/packages/vendors/v0/op_api/include/aclnn_test_op.h",
        "build_out/_CPack_Packages/Linux/External/custom_opp.run/packages/vendors/v0/op_proto/inc/op_proto.h",
        "build_out/autogen/op_proto.cc",
        "build_out/autogen/op_proto.h",
    ):
        path = baseline / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("generated build artifact\n", encoding="utf-8")

    safety = CONFORMANCE.validate_candidate_safety(baseline, candidate)
    assert safety["decision"] == "pass", safety["failures"]
    assert safety["changed_public_contract_files"] == []


def test_cli_enforces_frozen_isolation_even_when_scheme_claims_complete(tmp_path: Path) -> None:
    from validate_source_isolation import snapshot

    candidate = make_candidate(tmp_path)
    baseline = tmp_path / "baseline"
    shutil.copytree(candidate, baseline)
    (candidate / "kernel.cpp").write_text("changed shared implementation\nline2\n", encoding="utf-8")
    inputs = {
        "contract": contract(),
        "result": complete_result(),
        "manifest": {"configuration": {"target_socs": ["Ascend950"]}},
        "isolation-scope": {
            "schema_version": 1, "target_socs": ["Ascend950"],
            "baseline_files": snapshot(baseline), "editable_ranges": {}, "new_files": {},
        },
    }
    command = [sys.executable, str(SCRIPT), "--baseline", str(baseline), "--candidate", str(candidate)]
    for name, value in inputs.items():
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        command.extend([f"--{name}", str(path)])
    out = tmp_path / "gate.json"
    command.extend(["--out", str(out)])
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 1, result.stderr
    gate = json.loads(out.read_text())
    assert gate["decision"] == "fail"
    assert gate["candidate_safety"]["decision"] == "pass"
    assert gate["source_isolation"]["decision"] == "fail"
    assert any("outside frozen scope" in error for error in gate["conformance_failures"])
    shutil.copy2(baseline / "kernel.cpp", candidate / "kernel.cpp")
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(out.read_text())["source_isolation"]["decision"] == "pass"


def saved_gate(tmp_path):
    from validate_source_isolation import snapshot

    candidate = make_candidate(tmp_path)
    baseline = tmp_path / "baseline"
    shutil.copytree(candidate, baseline)
    (candidate / "kernel.cpp").write_text("optimized\nline2\n")
    inputs = {
        "contract": contract(), "result": complete_result(),
        "manifest": {"configuration": {"target_socs": ["Ascend950"]}},
        "isolation-scope": {
            "schema_version": 1, "target_socs": ["Ascend950"],
            "baseline_files": snapshot(baseline), "new_files": {},
            "editable_ranges": {"kernel.cpp": [
                {"start": 1, "end": 2, "kind": "target_private", "reason": "test change"},
            ]},
        },
    }
    command = [sys.executable, str(SCRIPT), "--baseline", str(baseline), "--candidate", str(candidate)]
    for name, value in inputs.items():
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(value))
        command.extend([f"--{name}", str(path)])
    gate = tmp_path / "gate.json"
    result = subprocess.run(command + ["--out", str(gate)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return command, gate


def test_verify_existing_is_read_only_and_ignores_unrelated_logs(tmp_path):
    command, gate = saved_gate(tmp_path)
    before = gate.read_bytes()
    (tmp_path / "candidate" / "debug.log").write_text("unrelated log\n")
    result = subprocess.run(command + ["--verify-existing", str(gate)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert gate.read_bytes() == before


@pytest.mark.parametrize("changed", [
    "candidate/kernel.cpp", "candidate/compile.json", "contract.json",
    "result.json", "manifest.json", "isolation-scope.json", "baseline/kernel.cpp",
])
def test_verify_existing_rejects_changed_identity_without_overwriting_gate(tmp_path, changed):
    command, gate = saved_gate(tmp_path)
    path = tmp_path / changed
    if path.suffix == ".cpp":
        path.write_text("new source\nline2\n")
    else:
        value = json.loads(path.read_text())
        value["revision"] = "changed"
        path.write_text(json.dumps(value))
    before = gate.read_bytes()
    result = subprocess.run(command + ["--verify-existing", str(gate)], capture_output=True, text=True)
    assert result.returncode != 0
    assert gate.read_bytes() == before


def test_copied_gate_does_not_validate_for_identical_source_in_another_candidate(tmp_path):
    command, gate = saved_gate(tmp_path)
    copy = tmp_path / "another-candidate"
    shutil.copytree(tmp_path / "candidate", copy)
    command[command.index("--candidate") + 1] = str(copy)
    result = subprocess.run(command + ["--verify-existing", str(gate)], capture_output=True, text=True)
    assert result.returncode == 1
    assert json.loads(result.stdout)["reason"] == "stale_or_misattributed_gate"


def test_legacy_gate_requires_revalidation_of_existing_evidence(tmp_path):
    command, gate = saved_gate(tmp_path)
    value = json.loads(gate.read_text())
    del value["evidence_identity"]
    gate.write_text(json.dumps(value))
    result = subprocess.run(command + ["--verify-existing", str(gate)], capture_output=True, text=True)
    assert result.returncode == 1
    result = subprocess.run(command + ["--out", str(gate)], capture_output=True, text=True)
    assert result.returncode == 0
