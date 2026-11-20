# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Behavioral checks for result selection and incomplete performance evidence."""

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/ops-profiling-report/scripts/npu_compute_report.py"
spec = importlib.util.spec_from_file_location("profile_report_under_test", SCRIPT)
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


def summary(path, name="target", duration=12.0):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "category": "OpInfoSummary",
                "Op Name": name,
                "Task Duration(us)": duration,
            }
        )
        + "\n"
    )


def test_exact_kernel_selection_preserves_separate_result_collections(tmp_path):
    first = tmp_path / "collection-p1-0001/summary.jsonl"
    second = tmp_path / "collection-p2-0002/summary.jsonl"
    summary(first)
    summary(second)
    with pytest.raises(ValueError, match="found 2"):
        report.select_summary(tmp_path, "target")
    selected, records = report.select_summary(tmp_path, "target", second)
    assert selected == second
    assert records[-1]["Task Duration(us)"] == 12
    with pytest.raises(ValueError, match="found 0"):
        report.select_summary(tmp_path, "targ")


def test_selected_summary_cannot_escape_collection(tmp_path):
    root = tmp_path / "result"
    root.mkdir()
    outside = tmp_path / "summary.jsonl"
    summary(outside)
    with pytest.raises(ValueError, match="belong"):
        report.select_summary(root, "target", outside)


def test_missing_or_duplicate_summary_categories_are_rejected(tmp_path):
    p = tmp_path / "summary.jsonl"
    p.write_text('{"category":"Memory"}\n')
    with pytest.raises(ValueError):
        report.load_summary(p)
    p.write_text('{"category":"OpInfoSummary"}\n' * 2)
    with pytest.raises(ValueError):
        report.load_summary(p)


def test_missing_frequency_and_duration_do_not_become_zero():
    item = report.timing(
        {"Task Duration(us)": None, "Current Freq": None, "Rated Freq": 1650}
    )
    assert item["duration_us"] is None
    assert item["rated_frequency_valid"] is False
    assert (
        report.timing(
            {"Task Duration(us)": 10, "Current Freq": 1600, "Rated Freq": 1650}
        )["rated_frequency_valid"]
        is False
    )


def test_partial_roofline_does_not_establish_convergence_or_compute_peak():
    item = report.roofline(10, hbm_bytes=1000, peak_bw=1e9, flops=10000)
    assert item["MBU"] == pytest.approx(0.1)
    assert item["MFU"] is None
    assert item["memory_lower_bound_us"] == pytest.approx(1)
    assert item["ceiling_us"] is None
    assert item["headroom_us"] is None
    assert item["roofline_complete"] is False


def test_explicit_complete_roofline_uses_both_cost_terms():
    item = report.roofline(
        10, hbm_bytes=1000, peak_bw=1e9, flops=20000, peak_flops=1e10
    )
    assert item["MFU"] == pytest.approx(0.2)
    assert item["ceiling_us"] == pytest.approx(2)
    assert item["cost_bound"] == "Compute-Bound"


def test_measured_zero_is_distinct_from_unknown_cost():
    item = report.roofline(10, hbm_bytes=0, peak_bw=1e9, flops=20000, peak_flops=1e10)
    assert item["MBU"] == 0
    assert item["memory_lower_bound_us"] == 0
    assert item["roofline_complete"] is True


@pytest.mark.parametrize("bad", [0, -1, float("nan"), float("inf"), True])
def test_invalid_explicit_peaks_are_rejected(bad):
    with pytest.raises(ValueError):
        report.roofline(10, peak_bw=bad)


@pytest.mark.parametrize("producer_extensions", [False, True])
def test_report_skill_runs_outside_plugin_without_workflow_state(
    tmp_path, producer_extensions
):
    # Only the report skill and the unchanged backend are available. Starting a
    # fresh interpreter also rules out workflow modules cached by other tests.
    from test_summary_compat import SKILL as tool_skill, current_producer

    isolated = tmp_path / "standalone-report"
    shutil.copytree(
        SCRIPT.parent.parent,
        isolated,
        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"),
    )
    if producer_extensions:
        collection, raw, records = current_producer(tmp_path)
    else:
        collection = tmp_path / "collection"
        shutil.copytree(tool_skill / "tests/fixtures/real-capture", collection)
        raw = collection / "summary.jsonl"
        records = [
            json.loads(line) for line in raw.read_text().splitlines() if line.strip()
        ]
    before = {str(p): report.receipt(p) for p in collection.rglob("*") if p.is_file()}
    output = tmp_path / "report"
    command = [
        sys.executable,
        "-E",
        "-s",
        "-B",
        str(isolated / "scripts/npu_compute_report.py"),
        "--collection-root",
        str(collection),
        "--case-id",
        "standalone-case",
        "--op-name",
        records[-1]["Op Name"],
        "--tool-skill",
        str(tool_skill),
        "--out",
        str(output),
    ]
    result = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    index = json.loads((output / "profile-report.json").read_text())
    assert index["status"] == "diagnostic_valid"
    assert index["identity"] == {}  # no manifest or optimization state needed
    assert index["performance_eligible"] is False
    assert index["timing"]["duration_us"] == records[-1]["Task Duration(us)"]
    assert len(index["inspections"]) == 4
    assert bool(index["summary_compatibility"]) == producer_extensions
    assert before == {
        str(p): report.receipt(p) for p in collection.rglob("*") if p.is_file()
    }
    roofline = subprocess.run(
        [
            sys.executable,
            "-E",
            "-s",
            "-B",
            str(isolated / "scripts/compute_efficiency.py"),
            "--duration-us",
            "10",
            "--bytes",
            "1000",
            "--peak-bw",
            "1000000000",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert roofline.returncode == 0, roofline.stderr
    metrics = json.loads(roofline.stdout)
    assert metrics["MBU"] == pytest.approx(0.1)
    assert metrics["MFU"] is None and metrics["roofline_complete"] is False
