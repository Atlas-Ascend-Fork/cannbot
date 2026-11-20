# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Reject mixing genuine captures across devices, protocols or scalar summaries."""
import copy
import json
from pathlib import Path

import pytest

from msopprof_fixture import backend, captured


@pytest.mark.parametrize("field", ["summary", "op_info", "timing", "selected_record", "identity", "case_id"])
def test_screening_cannot_borrow_another_capture_scalar(tmp_path, monkeypatch, field):
    *_, report = captured(tmp_path / "first", monkeypatch)
    *_, other = captured(tmp_path / "other", monkeypatch, physical=5, kernel="A")
    forged = copy.deepcopy(report)
    forged[field] = "another-case" if field == "case_id" else other[field]
    with pytest.raises(ValueError, match="changed|differ"):
        backend.validate_screening(forged)


def test_different_devices_cannot_share_comparison_key(tmp_path, monkeypatch):
    *_, first = captured(tmp_path / "first", monkeypatch, physical=4)
    *_, second = captured(tmp_path / "second", monkeypatch, physical=5)
    left, right = backend.validate_screening(first), backend.validate_screening(second)
    assert first["protocol"] == second["protocol"]
    assert left["frequency_mhz"] == right["frequency_mhz"]
    assert left["comparison_key"] != right["comparison_key"]
    assert left["comparison_key"]["device_binding"]["physical_device"] == 4
    assert right["comparison_key"]["device_binding"]["physical_device"] == 5


@pytest.mark.parametrize("changed", ["protocol", "command", "returncode", "identity", "case"])
def test_publication_binds_actual_execution_metadata(tmp_path, monkeypatch, changed):
    plan, identity, attempt, _ = captured(tmp_path, monkeypatch)
    forged, other_plan = copy.deepcopy(attempt), copy.deepcopy(plan)
    if changed == "protocol":
        other_plan["protocol"]["warmup"] = 17
    elif changed == "command":
        forged["command"] = [a.replace("--warm-up=3", "--warm-up=17") for a in forged["command"]]
    elif changed == "returncode":
        forged["returncode"] = 1
    elif changed == "case":
        other_plan["effect_case_id"] = "another-case"
    else:
        forged["comparison_identity"]["runner"] = ["/another/app"]
    with pytest.raises(ValueError):
        backend.validate_publication(forged, Path(attempt["archive"]["path"]),
            Path(attempt["summary"]["path"]), "", Path(attempt["import_log"]["path"]).read_text(), other_plan)


@pytest.mark.parametrize("changed", ["binding", "csv", "extra_csv", "missing_archive"])
def test_failed_recovery_never_retains_valid_status(tmp_path, monkeypatch, changed):
    plan, identity, attempt, _ = captured(tmp_path, monkeypatch)
    if changed == "binding":
        plan = copy.deepcopy(plan)
        plan["device_binding"]["physical_device"] = 5
    elif changed == "missing_archive":
        attempt = {k: v for k, v in attempt.items() if k != "archive"}
    elif changed == "csv":
        selected = json.loads(Path(attempt["summary"]["path"]).read_text())
        Path(selected["record"]["source"]["path"]).write_text("changed")
    else:
        (backend.output_path(attempt) / "Memory_extra.csv").write_text("metric,value\nA,9\n")
    monkeypatch.setattr(backend.subprocess, "run", lambda *a, **k: pytest.fail("recovery must remain offline"))
    recovery = tmp_path / "recovery"
    recovery.mkdir()
    result = backend.recover_attempt(plan, identity, attempt, recovery)
    assert result["status"] == "needs_review" and result["error"]
    assert attempt["status"] == "valid"


def test_bound_scalar_uses_frozen_occurrence_and_retains_all_raw_rows(tmp_path, monkeypatch):
    _, _, _, report = captured(tmp_path, monkeypatch, kernel="A", occurrence=1)
    assert len(report["records"]) == 2
    assert report["selected_record"] == report["records"][1]
    assert backend.validate_screening(report)["duration_us"] == 1


def test_existing_bound_report_without_optional_invocation_still_validates(tmp_path, monkeypatch):
    _, _, _, report = captured(tmp_path, monkeypatch)
    report.pop("invocation")
    assert backend.validate_screening(report)["duration_us"] == 5


@pytest.mark.parametrize("field", ["archive", "summary"])
def test_bound_report_checks_manifest_and_summary_receipts(tmp_path, monkeypatch, field):
    _, _, attempt, report = captured(tmp_path, monkeypatch)
    path = Path(attempt[field]["path"])
    path.write_text(path.read_text() + "\n")
    with pytest.raises(ValueError, match="receipt changed"):
        backend.validate_report(report)


def test_wrong_case_does_not_publish_any_report(tmp_path, monkeypatch):
    captured(tmp_path, monkeypatch)
    plan_path = tmp_path / "plan.json"
    plan = json.loads(plan_path.read_text())
    plan["effect_case_id"] = "wrong"
    plan_path.write_text(json.dumps(plan))
    out = tmp_path / "wrong-case"
    with pytest.raises(ValueError, match="case differs"):
        backend.build_bound_report(plan_path, tmp_path / "attempt.json", out)
    assert not out.exists()


@pytest.mark.parametrize("case", [None, "", " ", 123])
def test_formal_capture_rejects_missing_or_invalid_case_before_launch(tmp_path, monkeypatch, case):
    from device_fixture import bare_plan
    plan = bare_plan(backend.PROTOCOL)
    plan.update(frequency_policy="record_only", effect_case_id=case, identities={})
    monkeypatch.setattr(backend.subprocess, "run", lambda *a, **k: pytest.fail("must not launch"))
    with pytest.raises(ValueError, match="effect_case_id"):
        backend.collect_attempt(plan, {}, {}, tmp_path)
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("wrong", ["runner", "variant"])
def test_unfrozen_target_is_rejected_before_any_device_probe(tmp_path, monkeypatch, wrong):
    from device_fixture import bare_plan
    identity = {"kernel_name": "A", "runner": ["/frozen/app"]}
    plan = bare_plan(backend.PROTOCOL)
    plan.update(frequency_policy="record_only", identities={"baseline": identity})
    target = dict(identity, runner=["/unexpected/app"]) if wrong == "runner" else identity
    slot = {"variant": "baseline" if wrong == "runner" else "unexpected"}
    monkeypatch.setattr(backend.subprocess, "run", lambda *a, **k: pytest.fail("must not launch"))
    with pytest.raises(ValueError, match="identity changed|variant not frozen"):
        backend.collect_attempt(plan, target, slot, tmp_path)
    assert not (tmp_path / "output").exists()
