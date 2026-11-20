# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Integration phase gate: fast-forward merge equivalence replaces full re-measurement.

The concurrent-change (non-FF) path keeps requiring per-SoC postprocess gates;
only an eligible fast_forward merge-equivalence artifact unlocks evidence reuse.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "ops-perf-optimize-workflow" / "scripts"))
from workflow_state import check_phase_artifacts  # noqa: E402


def manifest(tmp_path: Path) -> Path:
    path = tmp_path / "run-manifest.json"
    path.write_text(json.dumps({
        "schema_version": 2,
        "configuration": {
            "target_socs": ["Ascend950"],
            "backend": "ascendc",
            "tuning_mode": "standard",
            "precision_diagnosis_policy": "persistent",
            "performance_effect_policy": {"id": "legacy_jitter_v1", "version": 1},
        },
        "collections": {},
        "inputs": {"code": None},
    }), encoding="utf-8")
    return path


def equivalence(tmp_path: Path, decision: str = "fast_forward", eligible: bool = True) -> Path:
    smoke = tmp_path / "smoke-report.json"
    smoke.write_text(json.dumps({"cases": 40, "result": "PASS"}), encoding="utf-8")
    path = tmp_path / "merge-equivalence.json"
    path.write_text(json.dumps({
        "schema_version": 1,
        "decision": decision,
        "evidence_reuse_eligible": eligible,
        "ff_check": {"target_head": "a" * 40, "candidate": "a" * 40, "merged": "a" * 40},
        "tree_identity": {"merged_tree": "t" * 40, "candidate_tree": "t" * 40,
                          "equal": decision == "fast_forward"},
        "blob_identity": {"files_checked": 3, "mismatches": []},
        "baseline_for_diff": "b" * 40,
        "rebuild": {"rebuild_sha256": hashlib.sha256(b"x").hexdigest(),
                     "accepted_sha256": hashlib.sha256(b"x").hexdigest(),
                     "matches_accepted": True},
        "smoke": {"path": str(smoke), "sha256": hashlib.sha256(smoke.read_bytes()).hexdigest()},
        "evidence_reuse": [] if not eligible else [
            {"kind": "performance-full", "soc": "Ascend950",
             "source": "final.performance", "identity": "a" * 40},
        ],
    }), encoding="utf-8")
    return path


def report(tmp_path: Path) -> Path:
    path = tmp_path / "VERIFY_REPORT.md"
    path.write_text("# synthetic verify report\n", encoding="utf-8")
    return path


def test_ff_equivalence_replaces_full_remeasurement(tmp_path: Path) -> None:
    manifest_path = manifest(tmp_path)
    paths = [str(equivalence(tmp_path)), str(report(tmp_path))]
    extra = check_phase_artifacts("integration", paths, manifest_path)
    assert any("smoke-report.json" in item for item in extra)


def test_concurrent_change_path_still_requires_per_soc_gates(tmp_path: Path) -> None:
    manifest_path = manifest(tmp_path)
    paths = [str(equivalence(tmp_path, decision="merge", eligible=False)), str(report(tmp_path))]
    with pytest.raises(ValueError, match="both full inventories"):
        check_phase_artifacts("integration", paths, manifest_path)


def test_ineligible_equivalence_requires_per_soc_gates(tmp_path: Path) -> None:
    manifest_path = manifest(tmp_path)
    paths = [str(equivalence(tmp_path, eligible=False)), str(report(tmp_path))]
    with pytest.raises(ValueError, match="both full inventories"):
        check_phase_artifacts("integration", paths, manifest_path)


def test_no_equivalence_and_no_gates_fails(tmp_path: Path) -> None:
    manifest_path = manifest(tmp_path)
    with pytest.raises(ValueError, match="both full inventories"):
        check_phase_artifacts("integration", [str(report(tmp_path))], manifest_path)
