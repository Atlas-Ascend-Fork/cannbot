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

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "ops-perf-optimize-workflow"
    / "scripts"
    / "validate_integration_safety.py"
)
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("validate_integration_safety", SCRIPT)
assert SPEC and SPEC.loader
SAFETY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SAFETY)


def write(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def roots(tmp_path: Path) -> tuple[Path, Path]:
    baseline = tmp_path / "baseline"
    candidate = tmp_path / "candidate"
    for root in (baseline, candidate):
        write(root, "op_host/config/ascend910b/op.json", "{}\n")
        write(root, "op_host/config/ascend950/op.json", "{}\n")
        write(
            root,
            "op_host/peer_tiling.cpp",
            "if (soc == ASCEND950) { return Arch35Tiling(); }\nreturn LegacyTiling();\n",
        )
        write(
            root,
            "op_kernel/legacy_kernel.hpp",
            "// legacy kernel remains reachable for non-target SoCs\n",
        )
    write(
        baseline,
        "op_host/test_tiling.cpp",
        "if (soc == ASCEND910B) { return LegacyTiling(); }\nreturn LegacyTiling();\n",
    )
    write(
        candidate,
        "op_host/test_tiling.cpp",
        "if (soc == ASCEND950) { return Arch35Tiling(); }\nreturn LegacyTiling();\n",
    )
    return baseline, candidate


def scope(*, routes: bool) -> dict:
    value = {
        "schema_version": 2,
        "target_socs": ["Ascend950"],
        "verified_socs": ["Ascend950"],
        "supported_socs": [
            {"name": "Ascend910B", "evidence": ["op_host/config/ascend910b/op.json"]},
            {"name": "Ascend950", "evidence": ["op_host/config/ascend950/op.json"]},
        ],
        "project_isolation_style": {
            "kind": "soc-version-route+arch-directory",
            "target_path_markers": ["arch35", "ascend950"],
            "target_route_tokens": ["ASCEND950", "arch35"],
            "evidence": ["op_host/peer_tiling.cpp:1"],
        },
        "shared_file_routes": {},
    }
    if routes:
        value["shared_file_routes"] = {
            "op_host/test_tiling.cpp": {
                "target_guard": ["op_host/test_tiling.cpp:1"],
                "non_target_fallback": ["op_host/test_tiling.cpp:2"],
            }
        }
    return value


def test_unverified_soc_requires_route_and_fallback_for_changed_shared_code(tmp_path: Path) -> None:
    baseline, candidate = roots(tmp_path)
    candidate_safety = SAFETY.validate_candidate_safety(baseline, candidate)
    report = SAFETY.validate_scope(scope(routes=False), baseline, candidate, candidate_safety)
    assert report["decision"] == "fail"
    assert report["unverified_socs"] == ["Ascend910B"]
    assert report["changed_shared_generation_files"] == ["op_host/test_tiling.cpp"]
    assert "lacks SoC-isolation evidence" in report["failures"][0]


def test_target_guard_plus_non_target_fallback_passes_generation_isolation(tmp_path: Path) -> None:
    baseline, candidate = roots(tmp_path)
    candidate_safety = SAFETY.validate_candidate_safety(baseline, candidate)
    report = SAFETY.validate_scope(scope(routes=True), baseline, candidate, candidate_safety)
    assert report["decision"] == "pass"
    assert report["isolation_required"] is True
    assert not report["candidate_safety"]["changed_public_contract_files"]


def test_cli_rejects_shared_helper_edit_outside_host_and_kernel(tmp_path: Path) -> None:
    from validate_source_isolation import snapshot

    baseline, candidate = roots(tmp_path)
    write(baseline, "common/helper.h", "constexpr int block = 128;\n")
    write(candidate, "common/helper.h", "constexpr int block = 256;\n")
    isolation_scope = {
        "schema_version": 1, "target_socs": ["Ascend950"],
        "baseline_files": snapshot(baseline),
        "editable_ranges": {"op_host/test_tiling.cpp": [{
            "start": 1, "end": 1, "kind": "routing", "reason": "Target dispatch only",
        }]},
        "new_files": {},
    }
    command = [sys.executable, str(SCRIPT), "--baseline", str(baseline), "--candidate", str(candidate)]
    for name, value in {
        "scope": scope(routes=True), "isolation-scope": isolation_scope,
        "manifest": {"configuration": {"target_socs": ["Ascend950"]}},
    }.items():
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        command.extend([f"--{name}", str(path)])
    out = tmp_path / "gate.json"
    command.extend(["--out", str(out)])
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 1, result.stderr
    gate = json.loads(out.read_text())
    assert gate["decision"] == "fail"
    assert any("common/helper.h" in error for error in gate["source_isolation"]["failures"])
    write(candidate, "common/helper.h", "constexpr int block = 128;\n")
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(out.read_text())["source_isolation"]["decision"] == "pass"


def test_scope_target_soc_must_match_run_manifest(tmp_path: Path) -> None:
    baseline, candidate = roots(tmp_path)
    candidate_safety = SAFETY.validate_candidate_safety(baseline, candidate)
    try:
        SAFETY.validate_scope(
            scope(routes=True),
            baseline,
            candidate,
            candidate_safety,
            ["Ascend910B"],
        )
    except SAFETY.ContractError as error:
        assert "RUN_MANIFEST" in str(error)
    else:
        raise AssertionError("integration scope cannot switch the frozen target SoC")


def test_supported_soc_list_cannot_omit_uncommented_add_config(tmp_path: Path) -> None:
    baseline, candidate = roots(tmp_path)
    for root in (baseline, candidate):
        write(
            root,
            "op_host/test_def.cpp",
            'this->AICore().AddConfig("ascend910b");\n'
            'this->AICore().AddConfig("ascend950");\n'
            '// this->AICore().AddConfig("commented_soc");\n',
        )
    value = scope(routes=True)
    value["supported_socs"] = [value["supported_socs"][1]]
    candidate_safety = SAFETY.validate_candidate_safety(baseline, candidate)
    try:
        SAFETY.validate_scope(value, baseline, candidate, candidate_safety)
    except SAFETY.ContractError as error:
        assert "exactly match uncommented AddConfig" in str(error)
        assert "ascend910b" in str(error)
        assert "commented_soc" not in str(error)
    else:
        raise AssertionError("supported_socs cannot hide a declared non-target generation")


def test_supported_soc_evidence_must_name_the_soc(tmp_path: Path) -> None:
    baseline, candidate = roots(tmp_path)
    value = scope(routes=True)
    value["supported_socs"][0]["evidence"] = ["op_kernel/legacy_kernel.hpp"]
    candidate_safety = SAFETY.validate_candidate_safety(baseline, candidate)
    try:
        SAFETY.validate_scope(value, baseline, candidate, candidate_safety)
    except SAFETY.ContractError as error:
        assert "does not name Ascend910B" in str(error)
    else:
        raise AssertionError("unrelated files cannot prove SoC support")


def test_route_evidence_must_be_local_to_each_changed_file(tmp_path: Path) -> None:
    baseline, candidate = roots(tmp_path)
    value = scope(routes=True)
    value["shared_file_routes"]["op_host/test_tiling.cpp"]["target_guard"] = [
        "op_host/peer_tiling.cpp:1"
    ]
    candidate_safety = SAFETY.validate_candidate_safety(baseline, candidate)
    try:
        SAFETY.validate_scope(value, baseline, candidate, candidate_safety)
    except SAFETY.ContractError as error:
        assert "must point into changed file" in str(error)
    else:
        raise AssertionError("unrelated target guards cannot justify a changed shared file")


def test_integration_gate_rejects_interface_drift(tmp_path: Path) -> None:
    baseline, candidate = roots(tmp_path)
    for root, dtype in ((baseline, "DT_FLOAT16"), (candidate, "DT_FLOAT16, DT_INT32")):
        write(root, "op_host/op_api/aclnn_test.cpp", f"supported = {{{dtype}}};\n")
    value = scope(routes=True)

    candidate_safety = SAFETY.validate_candidate_safety(baseline, candidate)
    report = SAFETY.validate_scope(value, baseline, candidate, candidate_safety)
    assert report["decision"] == "fail"
    assert report["candidate_safety"]["changed_public_contract_files"] == [
        "op_host/op_api/aclnn_test.cpp"
    ]
