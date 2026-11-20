# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Test device namespaces, frozen environments and PID continuity at launch."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from device_fixture import binding, bare_plan, bind_plan, process_receipt
import device_context as devices
import report_contract

backend = report_contract.backend({"provider": "msopprof"})


@pytest.mark.parametrize("visible,application,physical", [
    ("0", 0, 0), ("4", 0, 4), ("5", 0, 5),
    ("4,5", 0, 4), ("4,5", 1, 5), ("5,4", 0, 5),
    ("1,2", 0, 6),  # container runtime ID 1 maps to host physical ID 6
])
def test_runtime_mapping_is_not_inferred_from_visible_numbers(visible, application, physical):
    device = binding(application=application, physical=physical, visible=visible)
    assert devices.validate(device)["physical_device"] == physical
    plan = bare_plan(backend.PROTOCOL)
    bind_plan(plan, application=application, physical=physical, visible=visible)
    assert backend.report_device_id(plan) == physical
    row = {"op_name": "A", "device_id": physical}
    assert backend.select_record({"records": [row]}, {"kernel_name": "A"}, plan) == row
    with pytest.raises(ValueError, match="DEVICE_ID_MISMATCH"):
        backend.select_record({"records": [dict(row, device_id=physical + 1)]}, {"kernel_name": "A"}, plan)


@pytest.mark.parametrize("visible", ["", "4,4", "-1", "4,", "x", "4 5"])
def test_invalid_visibility_is_rejected(visible):
    with pytest.raises(ValueError):
        devices.visible_list(visible)


def test_unset_is_distinct_from_empty_and_does_not_default_to_zero():
    assert devices.visible_list(None) is None
    with pytest.raises(ValueError):
        devices.visible_list("")


@pytest.mark.parametrize("bad", [None, True, -1, "0", 8])
def test_invalid_application_device(bad):
    value = binding()
    value["application_device"] = bad
    with pytest.raises(ValueError):
        devices.validate(value)


def test_mapping_order_and_plan_alias_mismatch_rejected():
    plan = bare_plan(backend.PROTOCOL)
    bind_plan(plan, visible="5,4", physical=5)
    plan["device_binding"]["runtime_device"] = 4
    with pytest.raises(ValueError, match="ordered visible list"):
        backend.report_device_id(plan)
    bind_plan(plan, physical=4, visible="4")
    plan["physical_device"] = 0
    with pytest.raises(ValueError, match="aliases"):
        backend.report_device_id(plan)


def test_environment_is_frozen_without_changing_global_environment():
    before = dict(os.environ)
    plan = bare_plan(backend.PROTOCOL)
    inherited = dict(before)
    assert devices.launch_environment(plan, inherited) == before
    visible = "ASCEND_RT_VISIBLE_DEVICES"
    inherited[visible] = "1" if before.get(visible) == "0" else "0"
    with pytest.raises(ValueError, match="environment changed"):
        devices.launch_environment(plan, inherited)
    assert dict(os.environ) == before


def test_different_tasks_keep_separate_environments():
    first, second = bare_plan(backend.PROTOCOL), bare_plan(backend.PROTOCOL)
    env1, env2 = dict(os.environ, ASCEND_RT_VISIBLE_DEVICES="4"), dict(os.environ, ASCEND_RT_VISIBLE_DEVICES="5")
    bind_plan(first, physical=4, environment=env1)
    bind_plan(second, physical=5, environment=env2)
    assert devices.launch_environment(first, env1)["ASCEND_RT_VISIBLE_DEVICES"] == "4"
    assert devices.launch_environment(second, env2)["ASCEND_RT_VISIBLE_DEVICES"] == "5"
    with pytest.raises(ValueError):
        devices.launch_environment(first, env2)


def test_missing_binding_or_wrong_namespace_is_rejected():
    plan = bare_plan(backend.PROTOCOL)
    del plan["device_binding"]
    with pytest.raises(ValueError, match="binding"):
        backend.report_device_id(plan)
    plan = bare_plan(backend.PROTOCOL)
    plan["protocol"]["device_id_namespace"] = "logical"
    with pytest.raises(ValueError, match="namespace"):
        backend.report_device_id(plan)


def test_exec_launcher_records_the_measured_pid_and_preserves_visibility(tmp_path, monkeypatch):
    monkeypatch.setenv("ASCEND_RT_VISIBLE_DEVICES", "4")
    plan = bare_plan(backend.PROTOCOL)
    bind_plan(plan, physical=4)
    output = tmp_path / "output"
    output.mkdir()
    devices.write_binding(plan, output)
    runner = [sys.executable, "-c", "import os; print(os.getpid(), os.environ['ASCEND_RT_VISIBLE_DEVICES'])"]
    result = subprocess.run(devices.wrapped_runner(plan, runner, output), text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    pid, visible = result.stdout.strip().split()
    item = backend.receipt(tmp_path / "target-process.json")
    process = devices.target_process(item, plan, output, runner)
    assert process["pid"] == int(pid) and visible == "4"
    with pytest.raises(ValueError, match="capture"):
        devices.target_process(item, plan, tmp_path / "another-output", runner)
    (tmp_path / "target-process.json").write_text("{}")
    with pytest.raises(ValueError, match="changed"):
        devices.target_process(item, plan, output, runner)


def test_read_boundary_rejects_wrong_card_without_rewriting_csv(tmp_path):
    plan = bare_plan(backend.PROTOCOL)
    bind_plan(plan, visible="4", physical=4)
    csv = tmp_path / "OpBasicInfo.csv"
    raw = "Op Name,Device Id,Task Duration(us),Pid\nA,4,12,1234\n"
    csv.write_text(raw)
    assert backend.read_bound_records(tmp_path, {"kernel_name": "A"}, plan)["records"][0]["device_id"] == 4
    assert csv.read_text() == raw
    csv.write_text(raw + "A,0,1,5678\n")
    with pytest.raises(ValueError, match="DEVICE_ID_MISMATCH"):
        backend.read_bound_records(tmp_path, {"kernel_name": "A"}, plan)


def test_raw_sample_rejects_wrong_pid_and_accepts_offline_environment(tmp_path, monkeypatch):
    plan = bare_plan(backend.PROTOCOL)
    plan["frequency_policy"] = "record_only"
    identity = {"kernel_name": "A", "runner": ["/fake/runner"]}
    output = tmp_path / "output"
    output.mkdir()
    source = output / "OpBasicInfo.csv"
    source.write_text("Op Name,Device Id,Task Duration(us),Pid\nA,0,12,1234\n")
    data = backend.read_bound_records(output, identity, plan)
    extraction = tmp_path / "extracted.json"
    extraction.write_text(json.dumps(data))
    process = process_receipt(tmp_path, plan, identity["runner"])
    selected = tmp_path / "selected.json"
    document = {"record": data["records"][0], "extraction": backend.receipt(extraction),
                "target_process": process, "capture_output": str(tmp_path / "output"),
                "effect_case_id": plan["effect_case_id"]}

    selected.write_text(json.dumps(document))
    monkeypatch.setenv("ASCEND_RT_VISIBLE_DEVICES", "7")
    monkeypatch.setattr(devices, "probe", lambda *a: pytest.fail("offline replay must not query hardware"))
    assert backend.raw_sample(selected, identity, plan) == (12, 1234)
    document["target_process"] = process_receipt(tmp_path, plan, identity["runner"], pid=9999)
    selected.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="TARGET_PID_MISMATCH"):
        backend.raw_sample(selected, identity, plan)


def test_live_mapping_change_prevents_profiler_start(tmp_path, monkeypatch):
    plan = bare_plan(backend.PROTOCOL)
    plan.update(frequency_policy="record_only", identities={"baseline": {"kernel_name": "A", "runner": ["/fake/app"]}})
    changed = copy.deepcopy(plan["device_binding"])
    changed["physical_device"] = 5
    monkeypatch.setattr(devices, "probe", lambda *a: changed)
    monkeypatch.setattr(backend.subprocess, "run", lambda *a, **k: pytest.fail("must not launch"))
    with pytest.raises(ValueError, match="mapping changed"):
        backend.collect_attempt(plan, plan["identities"]["baseline"], {}, tmp_path)
    assert not (tmp_path / "output").exists()


def test_application_replay_is_rejected_before_device_probe(tmp_path, monkeypatch):
    from msopprof_fixture import fake_tool
    tool = fake_tool(tmp_path)
    monkeypatch.setattr(devices, "probe", lambda *a: pytest.fail("unsupported mode must not probe"))
    with pytest.raises(ValueError, match="application replay"):
        backend.prepare({"tool": str(tool), "application_device": 0, "replay_mode": "application"})
    plan = bare_plan(backend.PROTOCOL)
    plan.update(frequency_policy="record_only", identities={})
    plan["protocol"]["replay_mode"] = "application"
    with pytest.raises(ValueError, match="application replay"):
        backend.validate_measurement(plan)
    plan["protocol"]["replay_mode"] = "range"
    backend.validate_measurement(plan)
