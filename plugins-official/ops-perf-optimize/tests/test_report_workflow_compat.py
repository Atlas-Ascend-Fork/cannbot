# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.

"""Report integration with frozen policies and real Git worktree identities."""

import json
import subprocess
from pathlib import Path

import pytest

from test_npu_compute_evidence import evidence, fixture, prove, write
from prepare_case_sets import code_identity
from summarize_performance_effects import summarize
import search_policy


def rebind(paths, plan):
    reference = write(paths[0], plan)
    registration = json.loads(paths[1].read_text())
    registration["artifacts"] = [reference]
    write(paths[1], registration)
    collection = json.loads(paths[2].read_text())
    collection["plan"] = reference
    write(paths[2], collection)


def test_confidence_plan_cannot_disable_frequency_verification(tmp_path):
    paths = fixture(tmp_path)
    plan = json.loads(paths[0].read_text())
    plan["frequency_policy"] = "record_only"
    write(paths[0], plan)
    with pytest.raises(ValueError, match="require rated frequency"):
        evidence.validate_plan(paths[0])


def test_plan_cannot_silently_change_the_frozen_policy(tmp_path):
    paths = fixture(tmp_path)
    plan = json.loads(paths[0].read_text())
    plan["kind"] = evidence.MEDIAN_KIND
    write(paths[0], plan)
    with pytest.raises(ValueError, match="frozen policy differs"):
        evidence.validate_plan(paths[0])


def test_predeclared_independent_order_need_not_be_paired(tmp_path):
    paths = fixture(tmp_path)
    plan = json.loads(paths[0].read_text())
    order = sorted(plan["order"], key=lambda row: (row["variant"], row["sample_index"]))
    plan["order"] = [{**row, "slot": slot} for slot, row in enumerate(order)]
    write(paths[0], plan)
    evidence.validate_plan(paths[0])
    plan["order"][1]["sample_index"] = plan["order"][0]["sample_index"]
    write(paths[0], plan)
    with pytest.raises(ValueError, match="sample index once"):
        evidence.validate_plan(paths[0])


def git_fixture(tmp_path):
    paths = fixture(tmp_path)
    plan = json.loads(paths[0].read_text())
    manifest_path = Path(plan["manifest"]["path"])
    manifest = json.loads(manifest_path.read_text())
    expected = {}
    for variant, entry in plan["identities"].items():
        execution_path = Path(entry["execution_identity"]["path"])
        execution = json.loads(execution_path.read_text())
        source = Path(execution["source"]["path"])
        commands = [
            ["init", "-q"],
            ["config", "user.name", "Test"],
            ["config", "user.email", "test@example.com"],
            ["add", "."],
            ["commit", "-qm", "fixture"],
        ]
        for command in commands:
            subprocess.run(
                ["git", "-C", str(source), *command], check=True, capture_output=True
            )
        if variant == "baseline":
            manifest["inputs"]["code"] = code_identity(source)
            worktree = tmp_path / "baseline-worktree"
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(source),
                    "worktree",
                    "add",
                    "--detach",
                    str(worktree),
                ],
                check=True,
                capture_output=True,
            )
            source = worktree
        identity = code_identity(source)
        execution["source"] = identity
        build = execution["targets"][0]["build"]
        log = Path(build["log"]["path"])
        log.write_text(
            " ".join(
                [identity["sha256"], *[item["sha256"] for item in build["artifacts"]]]
            )
        )
        build["log"] = evidence.receipt(log)
        entry["execution_identity"] = write(execution_path, execution)
        precision_path = Path(entry["precision"]["path"])
        precision = json.loads(precision_path.read_text())
        precision.update(
            source=identity, execution_identity=entry["execution_identity"]
        )
        entry["precision"] = write(precision_path, precision)
        expected[variant] = {
            "commit": identity["git"]["head_commit"],
            "tree": identity["sha256"],
        }
    plan["manifest"] = write(manifest_path, manifest)
    rebind(paths, plan)
    return paths, plan, manifest, expected


def test_worktree_report_proof_matches_gate_commit_and_tree(tmp_path):
    paths, plan, manifest, expected = git_fixture(tmp_path)
    proof = write(tmp_path / "proof.json", prove(paths))
    summary = summarize(
        paths[3],
        paths[4],
        policy_id="confidence_effect_v1",
        evidence_paths=[proof["path"]],
    )
    result = {
        "outcome": "measured",
        "effect_summary": write(tmp_path / "effect.json", summary),
    }
    contract = {
        "case_ids": ["case"],
        "target_socs": ["Ascend950"],
        "search": {"baseline_performance": evidence.receipt(paths[3])},
    }
    assert (
        search_policy.checked_measurement(result, manifest, contract, expected, [])
        == summary
    )
    for field in ("commit", "tree"):
        mismatched = {
            **expected,
            "candidate": {**expected["candidate"], field: "0" * 40},
        }
        with pytest.raises(ValueError, match="another candidate implementation"):
            search_policy.checked_measurement(
                result, manifest, contract, mismatched, []
            )


def test_worktree_screening_validates_without_directory_gate_keys(tmp_path):
    from npu_compute_report import timing

    paths, plan, manifest, expected = git_fixture(tmp_path)
    reports = {}
    for side, slot in [("baseline", 0), ("candidate", 1)]:
        raw = evidence.receipt(tmp_path / f"captures/{slot}/unpacked/summary.jsonl")
        info = json.loads(Path(raw["path"]).read_text())
        reports[side] = write(
            tmp_path / f"{side}/report.json",
            {
                "provider": "npu-compute",
                "case_id": "case",
                "status": "diagnostic_valid",
                "performance_eligible": False,
                "summary": raw,
                "op_info": info,
                "timing": timing(info),
                "inspections": [],
                "identity": {
                    "execution_identity": plan["identities"][side][
                        "execution_identity"
                    ],
                    "input_snapshot": plan["snapshot"],
                },
            },
        )
    paths[3].write_text("case_id,total_us\ncase,100\n")
    paths[4].write_text("case_id,total_us\ncase,90\n")
    summary = summarize(paths[3], paths[4], policy_id="confidence_effect_v1")
    result = {
        "outcome": "screened",
        "provisional": True,
        "screening_evidence": {"case": reports},
    }
    contract = {"case_ids": ["case"], "target_socs": ["Ascend950"]}
    search_policy.checked_screening(result, manifest, contract, expected, summary, [])
    expected["candidate"]["tree"] = "0" * 40
    with pytest.raises(ValueError, match="another source"):
        search_policy.checked_screening(
            result, manifest, contract, expected, summary, []
        )
