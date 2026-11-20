# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Exercise complete independent-capture proofs using synthetic, local receipts."""

import importlib
import json
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/ops-perf-optimize-workflow/scripts"
sys.path.insert(0, str(SCRIPTS))
evidence = importlib.import_module("profile_evidence")
from prepare_case_sets import code_identity, identity as file_identity
import npu_compute_backend as backend


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))
    return evidence.receipt(path)


def text(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value)
    return evidence.receipt(path)


def fixture(tmp_path, *, external_comparator=False):
    original = tmp_path / "original"
    original.mkdir()
    (original / "operator.cpp").write_text("int operator_body() { return 1; }")
    comparator_root = tmp_path / "test-framework" if external_comparator else original
    comparator = text(
        comparator_root / "compare.py", "# synthetic original comparator for proof tests\n"
    )
    candidate = tmp_path / "optimized"
    candidate.mkdir()
    (candidate / "operator.cpp").write_text("int operator_body() { return 2; }")
    snapshot = write(
        tmp_path / "snapshot.json",
        {str(tmp_path / "input.bin"): text(tmp_path / "input.bin", "input")["sha256"]},
    )
    policy = write(
        tmp_path / "precision-policy.json",
        {"basis": "original_comparator", "comparator": comparator},
    )
    identities = {}
    for variant, source in [("baseline", original), ("candidate", candidate)]:
        folder = tmp_path / variant
        binary = text(folder / "runner", "synthetic test executable " + variant)
        source_id = code_identity(source)
        build_log = text(
            folder / "build.log", source_id["sha256"] + " " + binary["sha256"]
        )
        probe = text(folder / "probe.log", binary["path"])
        runtime = write(
            folder / "runtime.json",
            {
                "method": "synthetic process map",
                "source_artifacts": [probe],
                "loaded_artifacts": [binary],
            },
        )
        identity = write(
            folder / "execution.json",
            {
                "schema_version": 1,
                "source": source_id,
                "targets": [
                    {
                        "target_soc": "Ascend950",
                        "build": {
                            "command": "synthetic build",
                            "log": build_log,
                            "artifacts": [binary],
                        },
                        "runtime": {
                            "evidence": runtime,
                            "source_artifacts": [probe],
                            "loaded_artifacts": [binary],
                        },
                    }
                ],
            },
        )
        precision = write(
            folder / "precision.json",
            {
                "status": "strict_pass",
                "case_id": "case",
                "source": source_id,
                "input_snapshot": snapshot,
                "execution_identity": identity,
                "policy": policy,
                "returncode": 0,
                "comparison_log": text(folder / "compare.log", "PASS"),
                "actual_output": text(folder / "output.bin", "output"),
            },
        )
        identities[variant] = {
            "execution_identity": identity,
            "precision": precision,
            "kernel_name": variant,
            "block_dim": 32,
            "generated": [],
            "runner": [binary["path"], "--dry-run"],
            "cwd": str(folder),
        }
    inventory = text(tmp_path / "cases.csv", "case_id\ncase\n")
    manifest = write(
        tmp_path / "manifest.json",
        {
            "configuration": {
                "target_socs": ["Ascend950"],
                "performance_effect_policy": {
                    "id": "confidence_effect_v1",
                    "version": 1,
                },
            },
            "inputs": {"code": code_identity(original)},
            "collections": {"performance": inventory},
        },
    )
    order = []
    for pair in range(10):
        variants = (
            ["baseline", "candidate"] if pair % 2 == 0 else ["candidate", "baseline"]
        )
        order += [
            {"slot": pair * 2 + i, "variant": v, "sample_index": pair}
            for i, v in enumerate(variants)
        ]
    tool = text(tmp_path / "npu-compute", "synthetic tool fixture")
    plan = {
        "schema_version": 1,
        "kind": evidence.KIND,
        "manifest": manifest,
        "collection": "performance",
        "effect_case_id": "case",
        "soc": "Ascend950",
        "physical_device": 0,
        "logical_device": 0,
        "rated_frequency_mhz": 1650,
        "protocol": backend.PROTOCOL,
        "samples_per_variant": 10,
        "snapshot": snapshot,
        "precision_policy": policy,
        "baseline_variant": "baseline",
        "candidate_variant": "candidate",
        "identities": identities,
        "order": order,
        "tool": tool,
        "environment": {"ASCEND_HOME_PATH": "/example/cann"},
        "retry_policy": "failed_without_published_report_only",
        "statistical_method": {
            "id": evidence.INDEPENDENT_METHOD,
            "confidence": 0.95,
            "statistic": "difference_of_medians",
            "quantile": "linear",
            "seed": 2026,
            "draws": 1000,
        },
    }
    plan_path = tmp_path / "plan.json"
    plan_ref = write(plan_path, plan)
    issued = datetime(2025, 1, 1, tzinfo=timezone.utc)
    registration = tmp_path / "registration.json"
    write(registration, {"artifacts": [plan_ref], "issued_at": issued.isoformat()})
    rows = []
    values = {"baseline": [], "candidate": []}
    for row in order:
        slot, variant = row["slot"], row["variant"]
        folder = tmp_path / "captures" / str(slot)
        archive = text(folder / "capture.npu-rep", "synthetic archive " + str(slot))
        log = text(folder / "run.log", "npu-compute: report= " + archive["path"])
        unpacked = folder / "unpacked"
        imported = text(
            folder / "import.log", "npu-compute: unpacked= " + str(unpacked)
        )
        value = (100 if variant == "baseline" else 90) + row["sample_index"] / 100
        values[variant].append(value)
        summary = text(
            unpacked / "summary.jsonl",
            json.dumps(
                {
                    "category": "OpInfoSummary",
                    "Op Name": variant,
                    "Block Dim": 32,
                    "Device Id": 0,
                    "Pid": 1000 + slot,
                    "Task Duration(us)": value,
                    "Current Freq": 1650,
                    "Rated Freq": 1650,
                }
            )
            + "\n",
        )
        attempt = {
            "schema_version": 1,
            **row,
            "protocol": backend.PROTOCOL,
            "physical_device": 0,
            "logical_device": 0,
            "status": "valid",
            "returncode": 0,
            "started_at": (issued + timedelta(seconds=1 + slot * 2)).isoformat(),
            "ended_at": (issued + timedelta(seconds=2 + slot * 2)).isoformat(),
            "environment": plan["environment"],
            "command": [
                tool["path"],
                "--section",
                "PipeUtilization",
                "--cache-control",
                "all",
                "--export",
                archive["path"],
                "--",
                *identities[variant]["runner"],
            ],
            "run_log": log,
            "archive": archive,
            "import_returncode": 0,
            "import_log": imported,
            "summary": summary,
        }
        attempt_ref = write(folder / "attempt.json", attempt)
        rows.append({**row, "attempts": [attempt_ref]})
    collection = tmp_path / "collection.json"
    write(
        collection,
        {"schema_version": 1, "kind": evidence.KIND, "plan": plan_ref, "samples": rows},
    )
    baseline = tmp_path / "baseline.csv"
    candidate_csv = tmp_path / "candidate.csv"
    for variant, path in [("baseline", baseline), ("candidate", candidate_csv)]:
        text(
            path,
            "case_id,total_us\ncase," + str(statistics.median(values[variant])) + "\n",
        )
    return plan_path, registration, collection, baseline, candidate_csv


def prove(paths):
    return evidence.build_profile_proof(*paths, "case", "baseline", "candidate")


def edit_sample(paths, index, **changes):
    collection = json.loads(paths[2].read_text())
    row = collection["samples"][index]
    attempt_path = Path(row["attempts"][0]["path"])
    attempt = json.loads(attempt_path.read_text())
    summary_path = Path(attempt["summary"]["path"])
    info = json.loads(summary_path.read_text())
    info.update(changes)
    attempt["summary"] = text(summary_path, json.dumps(info) + "\n")
    row["attempts"][0] = write(attempt_path, attempt)
    write(paths[2], collection)


def test_complete_capture_proof_uses_twenty_distinct_processes_and_original_medians(
    tmp_path,
):
    result = prove(fixture(tmp_path))
    assert result["kind"] == evidence.KIND
    assert result["statistics"]["ci_us"][1] < 0
    assert len(result["statistics"]["baseline_samples_us"]) == 10
    assert len(result["statistics"]["candidate_samples_us"]) == 10


def test_capture_proof_accepts_external_original_comparator(tmp_path):
    prove(fixture(tmp_path, external_comparator=True))


def test_complete_proof_consumes_official_file_receipt_in_frozen_manifest(tmp_path):
    paths = fixture(tmp_path)
    plan = json.loads(paths[0].read_text())
    manifest_path = Path(plan["manifest"]["path"])
    manifest = json.loads(manifest_path.read_text())
    request_path = tmp_path / "optimization-request.json"
    write(
        request_path,
        {
            "performance_effect_policy": manifest["configuration"][
                "performance_effect_policy"
            ]
        },
    )
    # prepare_case_sets.freeze uses file_identity(), including kind:file metadata.
    manifest["request"] = file_identity(request_path)
    assert manifest["request"]["kind"] == "file"
    plan["manifest"] = write(manifest_path, manifest)
    plan_receipt = write(paths[0], plan)
    registration = json.loads(paths[1].read_text())
    registration["artifacts"] = [plan_receipt]
    write(paths[1], registration)
    collection = json.loads(paths[2].read_text())
    collection["plan"] = plan_receipt
    write(paths[2], collection)
    result = prove(paths)
    assert result["statistics"]["ci_us"][1] < 0


@pytest.mark.parametrize(
    "metadata",
    [
        {"kind": "directory"},
        {"kind": None},
        {"kind": "file", "unreviewed": True},
    ],
)
def test_receipt_compatibility_rejects_nonfile_and_unknown_metadata(tmp_path, metadata):
    item = text(tmp_path / "artifact.json", "{}")
    with pytest.raises(ValueError, match="canonical absolute artifact receipt"):
        evidence.bind({**item, **metadata}, {})


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"Current Freq": None}, "frequency"),
        ({"Current Freq": 1600}, "frequency"),
        ({"Device Id": 1}, "device"),
        ({"Op Name": "unrelated"}, "target identity"),
        ({"Task Duration(us)": None}, "Duration"),
    ],
)
def test_raw_identity_and_unavailable_values_cannot_be_hidden_by_rehashing(
    tmp_path, changes, message
):
    paths = fixture(tmp_path)
    edit_sample(paths, 1, **changes)
    with pytest.raises(ValueError, match=message):
        prove(paths)


def test_replaying_or_copying_a_capture_does_not_create_an_independent_sample(tmp_path):
    paths = fixture(tmp_path)
    edit_sample(paths, 1, Pid=1000)
    with pytest.raises(ValueError, match="independent"):
        prove(paths)


def test_headline_cannot_cherry_pick_a_faster_sample(tmp_path):
    paths = fixture(tmp_path)
    text(paths[4], "case_id,total_us\ncase,89\n")
    with pytest.raises(ValueError, match="headline"):
        prove(paths)


def test_missing_capture_is_pending_not_an_improvement(tmp_path):
    paths = fixture(tmp_path)
    data = json.loads(paths[2].read_text())
    data["samples"].pop()
    write(paths[2], data)
    with pytest.raises(ValueError, match="twenty"):
        prove(paths)


def test_archive_tampering_invalidates_proof(tmp_path):
    paths = fixture(tmp_path)
    (tmp_path / "captures/0/capture.npu-rep").write_text("changed")
    with pytest.raises(ValueError, match="changed"):
        prove(paths)


def add_failed_attempt(paths, published=False, present=False):
    collection = json.loads(paths[2].read_text())
    row = collection["samples"][0]
    success = json.loads(Path(row["attempts"][0]["path"]).read_text())
    failed = {
        k: v
        for k, v in success.items()
        if k not in ["archive", "summary", "import_log", "import_returncode"]
    }
    failed.update(
        status="failed",
        started_at="2025-01-01T00:00:00.100000+00:00",
        ended_at="2025-01-01T00:00:00.500000+00:00",
        returncode=0,
    )
    archive = paths[0].parent / "failure/report.npu-rep"
    failed["command"] = list(failed["command"])
    failed["command"][failed["command"].index("--export") + 1] = str(archive)
    failed["run_log"] = text(
        archive.parent / "run.log",
        "npu-compute: report= " + str(archive)
        if published
        else "child failed before launch",
    )
    if present:
        text(archive, "an existing report must be parsed, not discarded")
    row["attempts"].insert(0, write(archive.parent / "attempt.json", failed))
    write(paths[2], collection)


def test_wrapper_zero_without_archive_can_be_retained_then_retried(tmp_path):
    paths = fixture(tmp_path)
    add_failed_attempt(paths)
    assert prove(paths)["statistics"]["ci_us"][1] < 0


@pytest.mark.parametrize("published,present", [(True, False), (False, True)])
def test_published_or_existing_archive_cannot_be_discarded_for_resampling(
    tmp_path, published, present
):
    paths = fixture(tmp_path)
    add_failed_attempt(paths, published, present)
    with pytest.raises(ValueError, match="discarded|archive"):
        prove(paths)


def test_source_change_invalidates_reused_precision(tmp_path):
    paths = fixture(tmp_path)
    (tmp_path / "optimized/operator.cpp").write_text("new unverified operator body")
    with pytest.raises(ValueError, match="source|changed"):
        prove(paths)


def test_workflow_router_and_saved_proof_recompute_use_npu_backend(tmp_path):
    from performance_effect_evidence import build_proof, verify_proof

    paths = fixture(tmp_path)
    result = build_proof(*paths, "case")
    proof_path = tmp_path / "proof.json"
    write(proof_path, result)
    assert verify_proof(proof_path, paths[3], paths[4]) == result
