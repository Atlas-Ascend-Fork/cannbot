# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Network msprof: actual l0 schema, invocation selection and bound evidence."""

import copy
import csv
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

import profile_report
import report_contract
import report_common
from device_fixture import bind_plan
from msprof_fixture import FIXTURE, NAMES, fake_tool

backend = report_contract.backend({"provider": "msprof"})
tools = backend.tools


def raw_fixture(root):
    profile = root / "PROF_fixture"
    (profile / "mindstudio_profiler_output").mkdir(parents=True)
    (profile / "host").mkdir()
    (profile / "device_1").mkdir()
    csv_path = profile / "mindstudio_profiler_output/op_summary.csv"
    shutil.copyfile(FIXTURE / "op_summary.csv", csv_path)
    shutil.copyfile(FIXTURE / "info.json", profile / "host/info.json")
    return csv_path


def capture(tmp_path, monkeypatch, physical=4):
    tmp_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("ASCEND_RT_VISIBLE_DEVICES", str(physical))
    tool = fake_tool(tmp_path)
    plan = report_contract.prepare({"tools": ["msprof"], "tool": str(tool)})
    identity = {"runner": ["/unused/app", "baseline"], "cwd": str(tmp_path),
                "kernels": [{"name": NAMES[0], "occurrence": 0}, {"name": NAMES[1]},
                            {"name": NAMES[2]}, {"name": NAMES[0], "occurrence": 1}]}
    plan.update(identities={"baseline": identity}, effect_case_id="case")
    bind_plan(plan, physical=physical)
    monkeypatch.setattr(backend.device_context, "probe", lambda *a: plan["device_binding"])
    directory = tmp_path / "capture"
    directory.mkdir()
    attempt = backend.collect_attempt(plan, identity, {"variant": "baseline", "slot": 0, "sample_index": 0}, directory)
    assert attempt["status"] == "valid", attempt
    plan_path, attempt_path = tmp_path / "plan.json", tmp_path / "attempt.json"
    plan_path.write_text(json.dumps(plan))
    attempt_path.write_text(json.dumps(attempt))
    report = backend.build_bound_report(plan_path, attempt_path, tmp_path / "report")
    return plan, identity, attempt, report


def test_real_l0_csv_sum_preserves_device_time_precision(tmp_path):
    path = raw_fixture(tmp_path / "raw")
    data = tools.inspect_collection(path)
    assert [r["op_name"] for r in data["records"]] == NAMES
    assert {r["pid"] for r in data["records"]} == {1234}
    assert data["records"][0]["start_us"] == "1794904812628183.913"
    selected = tools.select_records(data, {"kernels": [{"name": n} for n in NAMES]})
    assert tools.invocation(selected)["duration_us"] == 13.063
    assert len(selected) == 3
    # No target identity means discovery, not a whole-process invocation total.
    assert "invocation" not in tools.build_report(tmp_path / "raw", "case")


def test_host_pid_must_be_an_integer(tmp_path):
    path = raw_fixture(tmp_path)
    (tmp_path / "PROF_fixture/host/info.json").write_text('{"pid": 1234.9}')
    with pytest.raises(ValueError, match="process ID"):
        tools.inspect_collection(path)


def test_explicit_l2_metric_option_is_supported(tmp_path):
    found = tools.capabilities(str(fake_tool(tmp_path)))
    argv = tools.build_command(found["tool"]["path"], ["/app"], tmp_path / "output",
                               ["--l2=on"], found["options"])
    assert "--l2=on" in argv


@pytest.mark.parametrize("physical", [0, 1, 4, 7])
def test_capture_recovery_and_mother_report(tmp_path, monkeypatch, physical):
    plan, identity, attempt, report = capture(tmp_path, monkeypatch, physical)
    assert backend.raw_sample(attempt["summary"]["path"], identity, plan)[0] == 18.478
    assert report["invocation"]["duration_us"] == 18.478
    assert len(report["invocation"]["records"]) == 4
    assert {r["application_device"] for r in report["measurements"]} == {0}
    assert {r["physical_device"] for r in report["measurements"]} == {physical}
    assert attempt["tool_elapsed_seconds"] > 0
    screened = backend.validate_screening(report)
    assert screened["duration_us"] == 18.478 and screened["frequency_mhz"] is None
    assert any(Path(r["path"]).name == "info.json" for r in screened["dependencies"])
    combined = profile_report.consolidate([tmp_path / "report/profile-report.json"], tmp_path / "combined")
    assert combined["invocations"][0]["duration_us"] == 18.478
    assert not any("warmup" in item or "l2_cache" in item for item in combined["limitations"])
    monkeypatch.setattr(report_common.subprocess, "run", lambda *a, **k: pytest.fail("recovery must stay offline"))
    recovery = tmp_path / "recovery"
    recovery.mkdir()
    recovered = backend.recover_attempt(plan, identity, dict(attempt, status="needs_review"), recovery)
    assert recovered["status"] == "valid" and "tool_elapsed_seconds" not in recovered


@pytest.mark.parametrize("field", ["identity", "case_id", "protocol", "invocation", "records", "measurements"])
def test_report_cannot_change_bound_selection_or_total(tmp_path, monkeypatch, field):
    _, _, _, report = capture(tmp_path, monkeypatch)
    forged = copy.deepcopy(report)
    if field in ("records", "measurements"):
        forged[field] = forged[field][:1]
    elif field == "invocation":
        forged[field]["duration_us"] = 1
    elif field == "case_id":
        forged[field] = "other"
    else:
        forged[field] = {}
    with pytest.raises(ValueError):
        backend.validate_screening(forged)


@pytest.mark.parametrize("changed", ["device", "pid", "duration", "timestamp", "summary", "binding"])
def test_raw_tampering_rejected_by_recovery(tmp_path, monkeypatch, changed):
    plan, identity, attempt, report = capture(tmp_path, monkeypatch)
    if changed in ("device", "duration", "timestamp"):
        path = Path(report["records"][0]["source"]["path"])
        with path.open() as f:
            reader = csv.DictReader(f)
            fields = reader.fieldnames
            rows = list(reader)
        column = {"device": "Device_id", "duration": "Task Duration(us)", "timestamp": "Task Start Time(us)"}[changed]
        rows[0][column] = "N/A" if changed == "timestamp" else "0"
        with path.open("w", newline="") as f:
            writer = csv.DictWriter(f, fields)
            writer.writeheader()
            writer.writerows(rows)
    elif changed == "pid":
        path = Path(report["records"][0]["process"]["path"])
        path.write_text(json.dumps({"pid": "9876"}))
    elif changed == "summary":
        path = Path(attempt["summary"]["path"])
        summary = json.loads(path.read_text())
        summary["records"] = summary["records"][:1]
        path.write_text(json.dumps(summary))
    else:
        plan["device_binding"]["physical_device"] = 5
        (tmp_path / "plan.json").write_text(json.dumps(plan))
    with pytest.raises(ValueError):
        backend.validate_report(report)
    if changed != "summary":  # recovery reconstructs derived summaries from intact originals
        folder = tmp_path / "recovery"
        folder.mkdir()
        assert backend.recover_attempt(plan, identity, attempt, folder)["status"] == "needs_review"


def test_ambiguous_missing_or_reused_launch_cannot_be_summed(tmp_path, monkeypatch):
    plan, identity, attempt, _ = capture(tmp_path, monkeypatch)
    data = json.loads(Path(attempt["import_log"]["path"]).read_text())
    for kernels in ([{"name": NAMES[0]}], [{"name": "missing"}],
                    [{"name": NAMES[0], "occurrence": 0}] * 2,
                    [{"name": NAMES[0], "occurrence": 9}]):
        with pytest.raises(ValueError):
            tools.select_records(data, {"kernels": kernels})


def test_duplicate_exports_are_not_extra_kernel_launches(tmp_path):
    path = raw_fixture(tmp_path / "raw")
    shutil.copyfile(path, path.with_name("op_summary_second.csv"))
    with pytest.raises(ValueError, match="duplicate device task"):
        tools.inspect_collection(tmp_path / "raw")


def test_brief_runtime_names_and_all_launches(tmp_path):
    root = tmp_path / "raw"
    source = raw_fixture(root)
    lines = source.read_text().splitlines()
    duplicate = lines[1].split(",")
    duplicate[2], duplicate[8] = "9", "1794904812642000.000"
    source.write_text("\n".join([*lines, ",".join(duplicate)]) + "\n")
    timeline = source.with_name("task_time.csv")
    timeline.write_text(
        "Device_id,stream_id,task_id,task_start(us),kernel_name\n"
        "1,61,6,1794904812628183.913,AddKernel\n"
        "1,61,9,1794904812642000.000,AddKernel\n"
        "1,61,7,1794904812640900.103,WrongStart\n"
        "1,62,8,1794904812641613.635,WrongStream\n"
        "2,61,8,1794904812641613.635,WrongDevice\n"
        "1,61,9,1794904812641613.635,WrongTask\n"
    )
    timeline.with_name("task_time_other.csv").write_text(
        timeline.read_text().replace("AddKernel", "WrongExport")
    )

    def cli(*args):
        return json.loads(subprocess.check_output([sys.executable, tools.__file__, *args]))

    full = cli("inspect", root)
    saved = tmp_path / "inspect.json"
    brief = cli("inspect", root, "--brief", "--out", saved)
    assert json.loads(saved.read_text()) == full
    assert "records" not in brief and brief["launches"] == 4
    groups = {group["name"]: group for group in brief["kernels"]}
    assert groups[NAMES[0]]["launches"] == 2
    assert set(groups[NAMES[0]]["runtime_names"]) == {"AddKernel"}
    assert groups[NAMES[0]]["runtime_names"]["AddKernel"]["launches"] == 2
    assert all("runtime_names" not in groups[name] for name in NAMES[1:])
    timeline.unlink()
    assert all("runtime_names" not in group for group in cli("inspect", root, "--brief")["kernels"])

    identity = tmp_path / "identity.json"
    identity.write_text('{"kernels":"all"}')
    args = ["report", root, "--case-id", "case", "--identity", identity]
    report_full = cli(*args, "--out", tmp_path / "full")
    report_brief = cli(*args, "--out", tmp_path / "brief", "--brief")
    stored = json.loads(Path(report_brief["report"]).read_text())
    assert stored["records"] == report_full["records"] == full["records"]
    assert stored["invocation"]["duration_us"] == 18.478
    assert len(stored["invocation"]["records"]) == report_brief["launches"] == 4
    assert report_brief["invocation"] == {"launches": 4, "duration_us": 18.478}


def test_mother_report_alignment_validates_names_counts_and_scope(tmp_path, monkeypatch):
    _, _, _, network = capture(tmp_path / "network", monkeypatch)
    detail_tools = report_contract.backend({"provider": "msopprof"}).tools
    detail = tmp_path / "OpBasicInfo.csv"
    detail.write_text(
        "Op Name,Task Duration(us),Device Id,Pid,Block Dim\n"
        "AddKernel,8.1,4,4321,24\nAddKernel,9.2,4,4321,24\n"
    )
    detail_tools.build_report(detail, "case", None, tmp_path / "detail")
    reports = [
        tmp_path / "network/report/profile-report.json",
        tmp_path / "detail/profile-report.json",
    ]
    matched = {"case_id": "case", "names": {"msprof": NAMES[0], "msopprof": "AddKernel"},
               "basis": "Runner and device task name evidence"}
    unknown = {"case_id": "case", "names": {"msprof": NAMES[1], "msopprof": None},
               "basis": "Detail capture did not include this launch"}
    out = tmp_path / "combined"
    result = profile_report.consolidate(reports, out, {"kernel_alignment": [matched, unknown]})
    left, right = result["kernel_alignment"]
    assert left["names"] == matched["names"]
    assert {name: source["launches"] for name, source in left["sources"].items()} == {
        "msprof": 2, "msopprof": 2,
    }
    assert right["names"]["msopprof"] is None and set(right["sources"]) == {"msprof"}
    assert len(result["measurements"]) == 6
    assert [(row["provider"], row["duration_us"]) for row in result["invocations"]] == [
        ("msprof", network["invocation"]["duration_us"]),
    ]
    rendered = (out / "性能分析报告.md").read_text()
    assert f"{NAMES[0]} ×2" in rendered and "AddKernel ×2" in rendered

    for invalid, reason in (
        ([{**matched, "basis": ""}], "basis"),
        ([matched, matched], "one-to-one"),
        ([{**matched, "case_id": "other"}], "missing or ambiguous"),
        ([{**matched, "names": {"msprof": NAMES[0], "msopprof": "Unseen"}}], "missing or ambiguous"),
    ):
        with pytest.raises(ValueError, match=reason):
            profile_report.consolidate(reports, tmp_path / "invalid", {"kernel_alignment": invalid})


def test_report_aligns_only_receipted_unambiguous_runtime_names(tmp_path):
    network = tmp_path / "network"
    source = raw_fixture(network)
    scope = {"kernels": "all"}
    earlier = tools.build_report(network, "chain", scope)
    with source.open() as stream:
        launches = list(csv.DictReader(stream))
    timeline = tools.task_table(source)
    with timeline.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["Device_id", "stream_id", "task_id", "task_start(us)", "kernel_name"])
        for row, symbol in zip(launches, ["unique", "shared", "shared"], strict=True):
            writer.writerow([row["Device_id"], row["Stream ID"], row["Task ID"], row["Task Start Time(us)"], symbol])
    # An optional export added after the original report cannot establish an alias.
    assert all("runtime_names" not in r for r in backend.overview(earlier)["kernels"])
    current = tools.build_report(network, "chain", scope)
    tools.write_report(current, tmp_path / "network-report")
    raw = tmp_path / "OpBasicInfo.csv"
    raw.write_text("Op Name,Task Duration(us),Device Id,Pid\nunique,2,1,77\nshared,5,1,77\n")
    detail = report_contract.backend({"provider": "msopprof"}).tools.build_report(
        raw, "chain", None, tmp_path / "detail-report")
    assessment = {"kernel_alignment": {"case_id": "chain", "runtime": "msprof",
                  "detail": "msopprof", "basis": "same isolated runner and input"}}
    combined = profile_report.consolidate([current["report"], detail["report"]], tmp_path / "combined", assessment)
    aligned = combined["kernel_alignment"]
    assert [r["names"]["msopprof"] for r in aligned] == ["unique", None, None]
    assert aligned[0]["via"] == {"path": str(timeline), "line": 2}
    assert str(timeline) in (tmp_path / "combined/性能分析报告.md").read_text()
    with timeline.open("a") as stream:
        stream.write("\n")
    with pytest.raises(ValueError, match="changed"):
        backend.overview(current)
