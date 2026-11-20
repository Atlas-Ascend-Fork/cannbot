# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.

"""Regression cases for issue 1 using local captures and a synthetic profiler."""

import json
from pathlib import Path

import pytest

from test_npu_compute_evidence import evidence, fixture, text, write
import collect_profile as collector
import npu_compute_backend as backend


def load(path):
    return json.loads(Path(path).read_text())


def register(path, plan):
    registration = path.with_name(path.stem + "-registration.json")
    write(
        registration,
        {"artifacts": [write(path, plan)], "issued_at": "2025-01-01T00:00:00+00:00"},
    )
    return registration


@pytest.fixture
def measurement(tmp_path, monkeypatch):
    paths = fixture(tmp_path)
    plan = load(paths[0])
    manifest_path = Path(plan["manifest"]["path"])
    manifest = load(manifest_path)
    manifest["configuration"]["performance_effect_policy"]["id"] = "median_v1"
    plan.update(
        kind=evidence.MEDIAN_KIND,
        samples_per_variant=1,
        manifest=write(manifest_path, manifest),
    )
    plan["order"] = plan["order"][:2]
    register(paths[0], plan)
    monkeypatch.setenv("ASCEND_HOME_PATH", "/example/cann")
    calls = []

    def run(command, cwd, log):
        calls.append(command)
        export = Path(command[command.index("--export") + 1])
        if "--import" in command:
            archive = Path(command[command.index("--import") + 1])
            name = archive.read_text()
            root = export / "result"
            write(
                root / "summary.jsonl",
                {
                    "category": "OpInfoSummary",
                    "Op Name": name,
                    "Block Dim": 32,
                    "Device Id": 0,
                    "Pid": 10000 + len(calls),
                    "Task Duration(us)": 100 if name == "baseline" else 90,
                    "Current Freq": 1650,
                    "Rated Freq": 1650,
                },
            )
            log.write_text("npu-compute: unpacked= " + str(root))
        else:
            export.write_text(Path(cwd).name)
            log.write_text("npu-compute: report= " + str(export))
        return 0

    monkeypatch.setattr(backend, "run", run)
    return paths[0], paths[0].with_name("plan-registration.json"), plan, calls


def test_plain_build_log_and_frozen_interpreter_preserve_artifact_checks(tmp_path):
    paths = fixture(tmp_path)
    plan = load(paths[0])
    entry = plan["identities"]["candidate"]
    execution_path = entry["execution_identity"]["path"]
    execution = load(execution_path)
    build = execution["targets"][0]["build"]
    build["log"] = text(Path(build["log"]["path"]), "Build completed successfully.\n")
    entry["execution_identity"] = write(Path(execution_path), execution)
    precision = load(entry["precision"]["path"])
    precision["execution_identity"] = entry["execution_identity"]
    entry["precision"] = write(Path(entry["precision"]["path"]), precision)
    entry["launcher"] = text(tmp_path / "python", "synthetic interpreter")
    entry["runner"] = [entry["launcher"]["path"], "run.py", "--dry-run"]
    write(paths[0], plan)
    evidence.validate_plan(paths[0])
    Path(entry["launcher"]["path"]).write_text("changed interpreter")
    with pytest.raises(ValueError, match="changed"):
        evidence.validate_plan(paths[0])
    text(Path(entry["launcher"]["path"]), "synthetic interpreter")
    Path(build["artifacts"][0]["path"]).write_text("changed operator")
    with pytest.raises(ValueError, match="artifact identity changed"):
        evidence.validate_plan(paths[0])


def test_import_recovery_uses_same_archive_and_preserves_failed_import(
    measurement, tmp_path, monkeypatch
):
    plan_path, registration, _, calls = measurement
    run = backend.run
    failed = False

    def fail_once(command, cwd, log):
        nonlocal failed
        if "--import" in command and not failed:
            failed = True
            calls.append(command)
            log.write_text("temporary parser failure")
            return 1
        return run(command, cwd, log)

    monkeypatch.setattr(backend, "run", fail_once)
    out = tmp_path / "collection"
    with pytest.raises(ValueError, match="retained needs_review"):
        collector.collect(plan_path, registration, out)
    path = out / "sample-00/attempt-00/attempt.json"
    before = load(path)
    collector.collect(plan_path, registration, out)
    after = load(path)
    assert after["status"] == "valid"
    assert after["archive"] == before["archive"]
    assert load(after["recovery_history"][0]["path"]) == before
    assert Path(before["import_log"]["path"]).read_text() == "temporary parser failure"
    assert sum("--import" not in command for command in calls) == 2
    assert sum("--import" in command for command in calls) == 3
    collector.collect(plan_path, registration, out)
    assert len(calls) == 5


@pytest.mark.parametrize("bad_target", [False, True])
def test_old_report_failure_recovers_only_verified_timing(
    measurement, tmp_path, bad_target
):
    plan_path, registration, _, calls = measurement
    out = tmp_path / "collection"
    collector.collect(plan_path, registration, out)
    path = out / "sample-00/attempt-00/attempt.json"
    attempt = load(path)
    attempt.update(status="needs_review", error="optional report parser failed")
    if bad_target:
        raw = load(attempt["summary"]["path"])
        raw["Op Name"] = "unrelated"
        attempt["summary"] = write(Path(attempt["summary"]["path"]), raw)
    write(path, attempt)
    if bad_target:
        with pytest.raises(ValueError, match="needs review"):
            collector.collect(plan_path, registration, out)
        assert load(path)["status"] == "needs_review"
    else:
        collector.collect(plan_path, registration, out)
        assert load(path)["status"] == "valid"
    assert len(calls) == 4


def next_plan(plan, old, destination):
    plan = json.loads(json.dumps(plan))
    plan["identities"]["candidate"]["runner"].append("--new-candidate")
    plan["reuse"] = {
        "baseline": {
            "collection": evidence.receipt(old / "collection.json"),
            "variant": "baseline",
        }
    }
    return plan, register(destination, plan)


def test_new_candidate_reuses_baseline_and_keeps_original_receipts(
    measurement, tmp_path
):
    plan_path, registration, plan, calls = measurement
    old, new = tmp_path / "first", tmp_path / "second"
    collector.collect(plan_path, registration, old)
    old_row = load(old / "collection.json")["samples"][0]
    destination = tmp_path / "next.json"
    _, registered = next_plan(plan, old, destination)
    collector.collect(destination, registered, new)
    rows = load(new / "collection.json")["samples"]
    assert rows[0]["attempts"] == old_row["attempts"]
    assert rows[0]["reused_from"]["collection"] == evidence.receipt(
        old / "collection.json"
    )
    assert len(calls) == 6  # two original captures, then only the new candidate
    collector.collect(destination, registered, new)
    assert len(calls) == 6


@pytest.mark.parametrize(
    "change",
    ["runner", "device", "frequency", "environment", "archive", "sample_coverage"],
)
def test_reuse_rejects_changed_conditions_or_evidence_before_capture(
    measurement, tmp_path, change
):
    plan_path, registration, plan, calls = measurement
    old = tmp_path / "first"
    collector.collect(plan_path, registration, old)
    destination = tmp_path / "next.json"
    plan, _ = next_plan(plan, old, destination)
    if change == "runner":
        plan["identities"]["baseline"]["runner"].append("--changed")
    elif change == "device":
        plan["physical_device"] = 1
    elif change == "frequency":
        plan["frequency_policy"] = "record_only"
    elif change == "environment":
        plan["environment"]["ASCEND_HOME_PATH"] = "/different/cann"
    elif change == "archive":
        (old / "sample-00/attempt-00/capture.npu-rep").write_text("tampered")
    else:
        collection = load(old / "collection.json")
        collection["samples"] = collection["samples"][1:]
        plan["reuse"]["baseline"]["collection"] = write(
            old / "collection.json", collection
        )
    registered = register(destination, plan)
    with pytest.raises(ValueError, match="differ|changed|complete"):
        collector.collect(destination, registered, tmp_path / "second")
    assert len(calls) == 4


def test_confidence_plan_rejects_cross_plan_sample_reuse(tmp_path):
    paths = fixture(tmp_path)
    plan = load(paths[0])
    plan["reuse"] = {
        "baseline": {"collection": evidence.receipt(paths[2]), "variant": "baseline"}
    }
    write(paths[0], plan)
    with pytest.raises(ValueError, match="reuse requires the median"):
        evidence.validate_plan(paths[0])


def test_proof_rechecks_execution_artifacts_after_sample_validation(
    tmp_path, monkeypatch
):
    paths = fixture(tmp_path)
    sample = evidence.raw_sample
    changed = False

    def change_binary_after_validation(*args):
        nonlocal changed
        result = sample(*args)
        if not changed:
            (tmp_path / "candidate/runner").write_text(
                "changed during proof verification"
            )
            changed = True
        return result

    monkeypatch.setattr(evidence, "raw_sample", change_binary_after_validation)
    with pytest.raises(ValueError, match="changed"):
        evidence.build_profile_proof(*paths, "case", "baseline", "candidate")
