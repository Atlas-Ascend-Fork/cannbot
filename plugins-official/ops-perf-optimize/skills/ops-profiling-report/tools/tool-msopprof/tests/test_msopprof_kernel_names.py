# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Runtime symbols and CSV names stay distinct, including offline recovery."""
import copy
import json
from pathlib import Path

import pytest

from device_fixture import bind_plan
from msopprof_fixture import backend, fake_tool

SYMBOL = "_Z10exp_kernelIDhEvPhS0_lljffj"


def capture(tmp_path, monkeypatch, *, explicit=False, fail_extraction=False):
    monkeypatch.setenv("ASCEND_RT_VISIBLE_DEVICES", "4")
    tool = fake_tool(tmp_path)
    tool.write_text(tool.read_text() + f'''
print('[INFO]  Start analyze kernel on device: device4, kernel: {SYMBOL}, name is: 0')
print('  Op Name: B')
print('  Task Duration(us): 5.000000')
print('  Block Dim: 8')
print('  Device Id: 4')
print('  Pid:', os.getpid())
print('[INFO]  Start analyze kernel on device: device4, kernel: unrelated, name is: 1')
print('  Op Name: Unrelated')
''')
    plan = backend.prepare({"tool": str(tool), "kernel_filter": "*exp_kernel*"})
    identity = {"runner": ["/unused/app"], "cwd": str(tmp_path)}
    identity.update({"report_op_name": "B"} if explicit else {"kernel_name": SYMBOL})
    plan.update(identities={"baseline": identity}, frequency_policy="record_only", effect_case_id="case")
    bind_plan(plan, physical=4)
    monkeypatch.setattr(backend.device_context, "probe", lambda *a: plan["device_binding"])
    folder = tmp_path / "capture"
    folder.mkdir()
    with monkeypatch.context() as context:
        if fail_extraction:
            def fail(*args):
                raise ValueError("old selector could not resolve the runtime name")
            context.setattr(backend, "runtime_name_binding", fail)
        attempt = backend.collect_attempt(plan, identity,
            {"variant": "baseline", "slot": 0, "sample_index": 0}, folder)
    return plan, identity, attempt


def bound_report(tmp_path, plan, attempt):
    plan_path, attempt_path = tmp_path / "plan.json", tmp_path / "attempt.json"
    plan_path.write_text(json.dumps(plan))
    attempt_path.write_text(json.dumps(attempt))
    return backend.build_bound_report(plan_path, attempt_path, tmp_path / "report")


def test_explicit_report_name_does_not_become_capture_filter(tmp_path, monkeypatch):
    plan, identity, attempt = capture(tmp_path, monkeypatch, explicit=True)
    assert attempt["status"] == "valid", attempt
    assert "--kernel-name=*exp_kernel*" in attempt["command"]
    report = bound_report(tmp_path, plan, attempt)
    assert "kernel_name_binding" not in report
    assert report["identity"] == identity
    assert backend.validate_screening(report)["duration_us"] == 5


def test_legacy_symbol_recovers_from_original_log_without_recollecting(tmp_path, monkeypatch):
    plan, identity, attempt = capture(tmp_path, monkeypatch, fail_extraction=True)
    assert attempt["status"] == "needs_review"
    original_attempt = copy.deepcopy(attempt)
    raw = next((tmp_path / "capture/output").rglob("OpBasicInfo.csv"))
    original = {path: path.read_bytes() for path in (raw, Path(attempt["run_log"]["path"]))}
    before = json.dumps(plan, sort_keys=True)
    monkeypatch.setattr(backend.subprocess, "run", lambda *a, **k: pytest.fail("offline recovery must not launch"))
    monkeypatch.setattr(backend.device_context, "probe", lambda *a: pytest.fail("offline recovery must not probe"))
    recovery = tmp_path / "recovery"
    recovery.mkdir()
    recovered = backend.recover_attempt(plan, identity, attempt, recovery)
    assert recovered["status"] == "valid", recovered
    assert recovered["archive"] == attempt["archive"]
    assert attempt == original_attempt
    assert json.dumps(plan, sort_keys=True) == before
    assert all(path.read_bytes() == content for path, content in original.items())
    report = bound_report(tmp_path, plan, recovered)
    assert report["kernel_name_binding"]["runtime_symbol"] == SYMBOL
    assert report["selected_record"]["op_name"] == "B"
    assert report["identity"]["kernel_name"] == SYMBOL
    assert backend.validate_screening(report)["duration_us"] == 5
    forged = copy.deepcopy(report)
    forged["kernel_name_binding"]["report_op_name"] = "A"
    with pytest.raises(ValueError, match="binding changed"):
        backend.validate_screening(forged)


@pytest.mark.parametrize(
    "problem",
    [
        "missing",
        "wrong_symbol",
        "wrong_pid",
        "wrong_device",
        "wrong_duration",
        "ambiguous",
        "duplicate_field",
        "extra_log",
        "extra_row",
        "missing_block",
    ],
)
def test_runtime_mapping_never_guesses_unproven_or_ambiguous_names(tmp_path, monkeypatch, problem):
    plan, identity, attempt = capture(tmp_path, monkeypatch)
    assert attempt["status"] == "valid", attempt
    log_path = Path(attempt["run_log"]["path"])
    log = log_path.read_text()
    if problem == "missing":
        log = "No runtime/report mapping in this log\n"
    elif problem == "wrong_symbol":
        log = log.replace(SYMBOL, "_Z13another_kernelv")
    elif problem == "wrong_pid":
        log = log.replace("Pid:", "Pid: 999")
    elif problem == "wrong_device":
        log = log.replace("device4", "device5").replace("Device Id: 4", "Device Id: 5")
    elif problem == "wrong_duration":
        log = log.replace("5.000000", "99.000000")
    elif problem == "duplicate_field":
        log = log.replace("  Block Dim: 8", "  Block Dim: 8\n  Block Dim: 8")
    elif problem == "extra_log":
        log += log[log.index("[INFO]  Start analyze"):]
    elif problem in ("extra_row", "missing_block"):
        csv_path = next((tmp_path / "capture/output").rglob("OpBasicInfo.csv"))
        raw = csv_path.read_text()
        if problem == "extra_row":
            csv_path.write_text(raw + raw.splitlines()[-1] + "\n")
        else:
            csv_path.write_text(raw.replace(",8,1650,", ",,1650,"))
            log = log.replace("  Block Dim: 8\n", "")
    else:
        start = log.index("[INFO]  Start analyze")
        log += log[start:].replace(SYMBOL, "_Z13another_kernelv")
    log_path.write_text(log)
    with pytest.raises(ValueError, match="KERNEL_NAME_MAPPING"):
        backend.read_bound_records(tmp_path / "capture/output", identity, plan, backend.receipt(log_path))


def test_stale_log_receipt_rejected_even_if_names_still_match(tmp_path, monkeypatch):
    plan, identity, attempt = capture(tmp_path, monkeypatch)
    path = Path(attempt["run_log"]["path"])
    path.write_text(path.read_text() + "\nchanged\n")
    with pytest.raises(ValueError, match="evidence changed"):
        backend.read_bound_records(tmp_path / "capture/output", identity, plan, attempt["run_log"])


@pytest.mark.parametrize("name", ["", " ", None, "*exp_kernel*"])
def test_report_selector_rejects_empty_names_and_capture_patterns(name):
    with pytest.raises(ValueError, match="exact CSV Op Name"):
        backend.report_op_name({"report_op_name": name})


def test_explicit_wrong_report_name_has_no_implicit_alias(tmp_path, monkeypatch):
    plan, identity, attempt = capture(tmp_path, monkeypatch)
    explicit = {**identity, "report_op_name": "wrong"}
    data = backend.read_bound_records(tmp_path / "capture/output", explicit, plan, attempt["run_log"])
    with pytest.raises(ValueError, match="0 matching launches.*expected CSV Op Name='wrong'"):
        backend.select_record(data, explicit, plan)
