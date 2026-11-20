# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Offline contracts for msopprof CLI, multi-kernel extraction and native acquisition."""

import csv
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

import profile_report
import report_contract
import report_common
from device_fixture import bind_plan
from msopprof_fixture import backend, fake_tool

TOOL = Path(__file__).resolve().parents[1]
tools = backend.tools
FIELDS = [
    "Op Name",
    "Op Type",
    "Task Duration(us)",
    "Device Id",
    "Pid",
    "Block Dim",
    "Current Freq",
    "Rated Freq",
]


def basic(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(FIELDS)
        writer.writerows(rows)
    return path


def test_multikernel_multilaunch_and_unknown_values(tmp_path):
    basic(
        tmp_path / "OPPROF_1/A/0/OpBasicInfo.csv",
        [
            ["A", "mix", "12.5", 0, 123, 4, 1650, 1650],
            ["A", "mix", "13", 0, 123, 4, 1650, 1650],
        ],
    )
    basic(
        tmp_path / "OPPROF_1/B/0/OpBasicInfo_1.csv",
        [["B", "vector", "NA", 0, 123, 8, "NA", "NA"]],
    )
    data = tools.inspect_collection(tmp_path)
    assert [(r["op_name"], r["duration_us"]) for r in data["records"]] == [
        ("A", 12.5),
        ("A", 13),
        ("B", None),
    ]
    assert data["records"][2]["raw"]["Task Duration(us)"] == "NA"
    assert data["aggregation"].startswith("none")
    chosen = tools.inspect_collection(tmp_path, ["B"], 0)
    assert len(chosen["records"]) == 1 and chosen["records"][0]["duration_us"] is None
    assert tools.inspect_collection(tmp_path, ["missing"])["status"] == "incomplete"


def test_malformed_csv_rejected(tmp_path):
    path = tmp_path / "OpBasicInfo.csv"
    path.write_text("Op Name,Task Duration(us)\nA,2,extra\n")
    with pytest.raises(ValueError, match="column count"):
        tools.inspect_collection(tmp_path)


@pytest.mark.parametrize("preset", ["default", "detailed", "full"])
def test_set_and_multikernel_argv_are_caller_selected(tmp_path, preset):
    argv = tools.build_command(
        ["msprof", "op"],
        ["python3", "app.py", "a b"],
        tmp_path,
        preset=preset,
        launch_count=9,
        kernel_name="A|B",
        warmup=2,
    )
    assert argv[:2] == ["msprof", "op"]
    assert "--set=" + preset in argv and "--launch-count=9" in argv
    assert "--kernel-name=A|B" in argv and "--warm-up=2" in argv
    assert argv[-3:] == ["python3", "app.py", "a b"]


def test_old_tool_set_does_not_silently_expand(tmp_path):
    with pytest.raises(ValueError, match="no automatic --set expansion"):
        tools.build_command(
            ["msopprof"],
            ["app"],
            tmp_path,
            preset="full",
            supported=[
                "--output",
                "--warm-up",
                "--replay-mode",
                "--launch-count",
                "--aic-metrics",
            ],
        )
    with pytest.raises(ValueError, match="mutually exclusive"):
        tools.build_command(
            ["msopprof"], ["app"], tmp_path, preset="default", metrics="BasicInfo"
        )


def test_command_only_never_probes_or_runs_target(tmp_path):
    script = (
        TOOL / "scripts/msopprof_tools.py"
    )
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            str(script),
            "command",
            "--tool",
            "/missing/msopprof",
            "--output",
            str(tmp_path),
            "--set",
            "full",
            "--launch-count",
            "4",
            "--",
            "/missing/app",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["argv"][-1] == "/missing/app"


def test_report_preserves_all_kernels_and_raw_files(tmp_path):
    root = tmp_path / "capture"
    path = basic(
        root / "OpBasicInfo.csv",
        [
            ["A", "mix", 12, 0, 10, 4, 1650, 1650],
            ["B", "vector", 7, 0, 10, 8, 1650, 1650],
        ],
    )
    before = path.read_bytes()
    result = tools.build_report(root, "case", None, tmp_path / "report")
    assert [r["op_name"] for r in result["records"]] == ["A", "B"]
    assert result["performance_eligible"] is False and "timing" not in result
    assert path.read_bytes() == before
    assert (tmp_path / "report/性能分析报告.md").exists()


def _bound_capture_plan(binding, identity, monkeypatch, physical=0):
    plan = {
        **binding,
        "identities": {"baseline": identity, "candidate": identity},
        "physical_device": 0,
        "logical_device": 0,
        "rated_frequency_mhz": 1650,
        "frequency_policy": "rated",
        "environment": {},
    }
    bind_plan(plan, physical=physical)
    frozen_device = plan["device_binding"]
    monkeypatch.setattr(backend.device_context, "probe", lambda *args: frozen_device)
    return plan


@pytest.mark.parametrize("physical", [0, 4, 5])
def test_native_capture_extract_recovery_and_tamper_detection(tmp_path, monkeypatch, physical):
    monkeypatch.setenv("ASCEND_RT_VISIBLE_DEVICES", str(physical))
    executable = fake_tool(tmp_path)
    binding = backend.prepare(
        {"tool": str(executable), "launch_count": 2, "kernel_filter": "A|B"}
    )
    identity = {
        "runner": ["/unused/app", "a b"],
        "cwd": str(tmp_path),
        "kernel_name": "B",
        "block_dim": 8,
    }
    plan = _bound_capture_plan(binding, identity, monkeypatch, physical=physical)
    report_contract.validate_measurement(plan)
    folder = tmp_path / "attempt"
    folder.mkdir()
    timestamps = [
        "2026-11-16T10:00:00+00:00",
        "2026-11-16T10:00:01+00:00",
        "2026-11-16T10:00:03+00:00",
    ]
    monkeypatch.setattr(report_common, "now", iter(timestamps).__next__)
    attempt = backend.collect_attempt(plan, identity, {"slot": 0}, folder)
    assert attempt["status"] == "valid", attempt
    time_fields = ("started_at", "capture_ended_at", "ended_at")
    assert [attempt[key] for key in time_fields] == timestamps
    assert (
        "--warm-up=3" in attempt["command"]
        and "--replay-mode=kernel" in attempt["command"]
    )
    value, pid = backend.raw_sample(attempt["summary"]["path"], identity, plan)
    assert value == 5 and pid > 0
    extracted = json.loads(Path(attempt["import_log"]["path"]).read_text())
    assert [r["op_name"] for r in extracted["records"]] == ["B"]
    assert len(tools.inspect_collection(folder / "output")["records"]) == 2
    recovered = tmp_path / "recover"
    recovered.mkdir()
    again = backend.recover_attempt(plan, identity, attempt, recovered)
    assert again["status"] == "valid" and again["command"] == attempt["command"]
    assert {key: again.get(key) for key in time_fields} == {
        key: attempt.get(key) for key in time_fields
    }
    assert "capture_ended_at" in again
    plan_path, attempt_path = tmp_path / "plan.json", tmp_path / "attempt.json"
    plan_path.write_text(json.dumps(plan))
    attempt_path.write_text(json.dumps(attempt))
    report = backend.build_bound_report(plan_path, attempt_path, tmp_path / "bound-report")
    backend.validate_report(report)
    assert report["measurements"][0]["application_device"] == 0
    assert report["measurements"][0]["physical_device"] == physical
    screened = backend.validate_screening(report)
    assert attempt["target_process"] in screened["dependencies"]
    assert attempt["device_binding_file"] in screened["dependencies"]
    combined = profile_report.consolidate([tmp_path / "bound-report/profile-report.json"], tmp_path / "combined")
    assert combined["status"] == "valid"
    assert combined["measurements"][0]["device"] == physical
    source = Path(extracted["records"][0]["source"]["path"])
    source.write_text(source.read_text().replace(f",10,{physical},", f",999,{physical},"))
    with pytest.raises(ValueError, match="changed"):
        backend.validate_publication(
            attempt,
            Path(attempt["archive"]["path"]),
            Path(attempt["summary"]["path"]),
            "",
            Path(attempt["import_log"]["path"]).read_text(),
            plan,
        )


def test_unbound_report_is_diagnostic_only(tmp_path):
    basic(tmp_path / "capture/OpBasicInfo.csv", [["A", "mix", 12, 4, 123, 4, 1650, 1650]])
    report = tools.build_report(tmp_path / "capture", "case", ["A"], tmp_path / "report")
    backend.validate_report(report)
    with pytest.raises(ValueError, match="unbound diagnostic"):
        backend.validate_screening(report)


def test_selected_prepare_preserves_metric_preset(tmp_path):
    executable = fake_tool(tmp_path)
    binding = report_contract.prepare(
        {"tools": ["msopprof"], "tool": str(executable), "set": "detailed", "launch_count": 6}
    )
    assert (
        binding["provider"] == "msopprof" and binding["protocol"]["set"] == "detailed"
    )
    assert "aic_metrics" not in binding["protocol"]


def test_unselected_damaged_csv_warns_but_selected_data_remains_usable(tmp_path):
    selected = basic(
        tmp_path / "A/OpBasicInfo.csv", [["A", "mix", 12, 0, 10, 4, 1650, 1650]]
    )
    bad = tmp_path / "B/OpBasicInfo.csv"
    bad.parent.mkdir()
    bad.write_text("bad,bad\n1,2,3\n")
    data = tools.inspect_collection(tmp_path, basic_info=selected)
    assert [r["op_name"] for r in data["records"]] == ["A"]
    assert len(data["warnings"]) == 1 and data["status"] == "parsed"
    with pytest.raises(ValueError):
        tools.inspect_collection(tmp_path, basic_info=bad)
    with pytest.raises(ValueError, match="duplicate CSV header"):
        tools.inspect_collection(tmp_path, ["A"])


def test_optional_metric_rows_and_na_are_not_coerced(tmp_path):
    metric = tmp_path / "Memory.csv"
    metric.write_text("block_id,bw(GB/s)\n0,NA\n1,0\n")
    assert "rows" not in tools.inspect_collection(metric)["csv_files"][0]
    rows = tools.inspect_collection(metric, include_data=True)["csv_files"][0]["rows"]
    assert rows == [
        {"block_id": "0", "bw(GB/s)": "NA"},
        {"block_id": "1", "bw(GB/s)": "0"},
    ]


def test_report_cli_accepts_private_tool_binding_and_multikernel_selection(tmp_path):
    root = tmp_path / "capture"
    selected = basic(
        root / "OpBasicInfo.csv",
        [
            ["A", "mix", 12, 0, 10, 4, 1650, 1650],
            ["B", "vector", 7, 0, 10, 8, 1650, 1650],
        ],
    )
    out = tmp_path / "report"
    run = subprocess.run(
        [
            sys.executable,
            "-B",
            str(
                TOOL / "scripts/msopprof_tools.py"
            ),
            "report",
            str(root),
            "--case-id",
            "multi",
            "--op-name",
            "A",
            "--op-name",
            "B",
            "--basic-info",
            str(selected),
            "--device",
            "0",
            "--out",
            str(out),
        ],
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, run.stdout + run.stderr
    data = json.loads((out / "profile-report.json").read_text())
    assert data["provider"] == "msopprof" and len(data["records"]) == 2


def test_frozen_occurrence_cannot_be_replaced_with_a_faster_launch(tmp_path, monkeypatch):
    executable = fake_tool(tmp_path)
    executable.write_text(
        executable.read_text().replace("['B','vector',5,", "['A','mix',1,")
    )
    binding = backend.prepare({"tool": str(executable), "launch_count": 2})
    identity = {
        "runner": ["/unused/app"],
        "cwd": str(tmp_path),
        "kernel_name": "A",
        "occurrence": 0,
    }
    plan = _bound_capture_plan(binding, identity, monkeypatch)
    folder = tmp_path / "attempt"
    folder.mkdir()
    attempt = backend.collect_attempt(plan, identity, {"slot": 0}, folder)
    assert attempt["status"] == "valid", attempt
    selection = Path(attempt["summary"]["path"])
    document = json.loads(selection.read_text())
    extracted = json.loads(Path(attempt["import_log"]["path"]).read_text())
    assert [row["duration_us"] for row in extracted["records"]] == [10, 1]
    document["record"] = extracted["records"][1]
    selection.write_text(json.dumps(document))
    attempt["summary"] = tools.receipt(selection)
    with pytest.raises(ValueError, match="selection changed"):
        backend.raw_sample(selection, identity, plan)
    with pytest.raises(ValueError, match="selection changed"):
        backend.validate_publication(
            attempt,
            Path(attempt["archive"]["path"]),
            selection,
            "",
            Path(attempt["import_log"]["path"]).read_text(),
            plan,
        )


def test_native_selected_target_survives_an_unselected_corrupt_basicinfo(tmp_path, monkeypatch):
    executable = fake_tool(tmp_path)
    executable.write_text(
        executable.read_text()
        + "\nbad=root/'other';bad.mkdir();"
        "(bad/'OpBasicInfo.csv').write_text('Op Name,Task Duration(us)\\nother,2,3\\n')\n"
    )
    binding = backend.prepare({"tool": str(executable), "launch_count": 2})
    identity = {"runner": ["/unused/app"], "cwd": str(tmp_path), "kernel_name": "A"}
    plan = _bound_capture_plan(binding, identity, monkeypatch)
    folder = tmp_path / "attempt"
    folder.mkdir()
    attempt = backend.collect_attempt(plan, identity, {"slot": 0}, folder)
    assert attempt["status"] == "valid", attempt
    extracted = json.loads(Path(attempt["import_log"]["path"]).read_text())
    assert len(extracted["warnings"]) == 1


def test_caller_can_supply_additional_tool_options(tmp_path):
    argv = tools.build_command(
        ["msopprof"],
        ["app"],
        tmp_path,
        replay_mode="range",
        extra_options=["--mstx=true", "--mstx-include=range1"],
    )
    assert "--mstx=true" in argv and "--mstx-include=range1" in argv
    with pytest.raises(ValueError, match="duplicate"):
        tools.build_command(
            ["msopprof"], ["app"], tmp_path, extra_options=["--warm-up=5"]
        )


@pytest.mark.parametrize("frontend", ["msopprof", "msprof"])
def test_msopprof_preparation_only_probes_selected_frontend(
    tmp_path, monkeypatch, frontend
):
    executable = tmp_path / frontend
    executable.write_text("synthetic executable")
    commands = []

    def which(name):
        return str(executable) if name == frontend else None

    def run(command, **kwargs):
        commands.append(command)
        if command[-1] == "--version":
            raise subprocess.TimeoutExpired(command, 3)
        return SimpleNamespace(
            returncode=0,
            stdout="--output --warm-up --replay-mode --launch-count --aic-metrics",
            stderr="",
        )

    monkeypatch.setattr(backend.tools.shutil, "which", which)
    monkeypatch.setattr(backend.tools.subprocess, "run", run)
    for key in ("ASCEND_HOME_PATH", "ASCEND_HOME"):
        monkeypatch.delenv(key, raising=False)
    binding = report_contract.prepare({"tools": ["msopprof"]})
    prefix = [str(executable)] + (["op"] if frontend == "msprof" else [])
    assert binding["provider"] == "msopprof"
    assert binding["report_context"]["command_prefix"] == prefix
    assert commands == [[*prefix, "--help"], [*prefix, "--version"]]


def test_broken_msopprof_is_reported(tmp_path, monkeypatch):
    executable = tmp_path / "msopprof"
    executable.write_text("fixture")
    monkeypatch.setattr(
        backend.tools.shutil, "which", lambda name: str(executable)
    )
    monkeypatch.setattr(
        backend.tools.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=1, stdout="", stderr="broken CLI"),
    )
    with pytest.raises(ValueError, match="help failed"):
        report_contract.prepare({"tools": ["msopprof"]})


def test_missing_msopprof_is_reported(monkeypatch):
    monkeypatch.setattr(backend.tools.shutil, "which", lambda name: None)
    for key in ("ASCEND_HOME_PATH", "ASCEND_HOME"):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(ValueError, match="unavailable"):
        report_contract.prepare({"tools": ["msopprof"]})


def test_brief_and_explicit_line_selection(tmp_path):
    root = tmp_path / "raw"
    source = basic(root / "A/OpBasicInfo.csv", [
        ["A", "mix", 12, 0, 123, 4, 1650, 1650],
        ["A", "mix", 13, 0, 123, 4, 1650, 1650],
    ])

    def run(*args):
        return subprocess.run([sys.executable, tools.__file__, *args], capture_output=True, text=True)

    full = json.loads(run("inspect", root).stdout)
    saved = tmp_path / "inspect.json"
    brief = json.loads(run("inspect", root, "--brief", "--out", saved).stdout)
    assert json.loads(saved.read_text()) == full
    assert "records" not in brief and brief["kernels"][0]["launches"] == 2
    args = ["report", root, "--case-id", "case"]
    full_report = json.loads(run(*args, "--out", tmp_path / "full").stdout)
    assert full_report["records"] == full["records"]
    selected = run(*args, "--basic-info", source, "--line", "3", "--out", tmp_path / "selected", "--brief")
    assert selected.returncode == 0, selected.stdout
    brief_report = json.loads(selected.stdout)
    stored = json.loads(Path(brief_report["report"]).read_text())
    assert stored["records"] == [full["records"][1]]
    assert stored["measurements"][0]["duration_us"] == 13
    assert brief_report["launches"] == 1
    assert run(*args, "--line", "3", "--out", tmp_path / "invalid").returncode == 2


def test_isolated_sampling_requires_one_launch_before_occurrence(tmp_path):
    source = basic(tmp_path / "OpBasicInfo.csv", [["A", "mix", 12, 0, 123, 4, 1650, 1650]])
    plan = {"protocol": dict(backend.PROTOCOL)}
    bind_plan(plan, physical=0)
    data = tools.inspect_collection(source)
    identity = {"kernels": "all"}
    assert backend.select_record(data, identity, plan)["op_name"] == "A"
    data["records"] *= 2
    with pytest.raises(ValueError, match="exactly one"):
        backend.select_record(data, {**identity, "occurrence": 0}, plan)
