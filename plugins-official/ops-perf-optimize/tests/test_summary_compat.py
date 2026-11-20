# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Retain new producer records while the unchanged inspector checks known fields."""

import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/ops-profiling-report/scripts"))
from npu_compute_report import build_report, receipt

SKILL = ROOT.parents[1] / "vendor/cannbot-skills/tools/tool-npu-compute"


def current_producer(tmp_path):
    root = tmp_path / "collection"
    shutil.copytree(SKILL / "tests/fixtures/real-capture", root)
    path = root / "summary.jsonl"
    records = [
        json.loads(line) for line in path.read_text().splitlines() if line.strip()
    ]
    records[-1].update(
        aic_flops_theoretical=432.54,
        aiv_flops_theoretical=27.03,
        aic_flops="NA",
        aiv_flops=23.132423,
    )
    records[0]["aic_mte1_active_bw(GB/s)"] = "NA"
    records.insert(
        -1, {"category": "PerformanceHints", "hints": ["observed diagnostic hint"]}
    )
    path.write_text("".join(json.dumps(row) + "\n" for row in records))
    return root, path, records


def test_current_extensions_use_readonly_derived_view_and_preserve_raw(tmp_path):
    root, path, records = current_producer(tmp_path)
    before = receipt(path)
    result = build_report(
        root, "case", records[-1]["Op Name"], SKILL, tmp_path / "report"
    )
    assert (
        result["status"] == "diagnostic_valid"
        and result["performance_eligible"] is False
    )
    compat = result["summary_compatibility"]
    assert compat["original_summary"] == before == receipt(path)
    assert compat["opaque_op_metadata"]["aic_flops"] == "NA"
    assert compat["advisory_performance_hints"][0]["hints"] == [
        "observed diagnostic hint"
    ]
    assert records[-1] == result["op_info"]
    assert compat["unavailable_normalizations"]
    projected = [
        json.loads(x)
        for x in Path(compat["derived_view"]["path"]).read_text().splitlines()
    ]
    assert all(r["category"] != "PerformanceHints" for r in projected)
    assert projected[0]["aic_mte1_active_bw(GB/s)"] is None


@pytest.mark.parametrize(
    "problem", ["unknown_category", "unknown_field", "invalid_known_type"]
)
def test_compatibility_does_not_hide_unreviewed_schema_or_invalid_metrics(
    tmp_path, problem
):
    root, path, records = current_producer(tmp_path)
    if problem == "unknown_category":
        records.insert(0, {"category": "UnknownTimingExtension", "duration": 123})
    elif problem == "unknown_field":
        records[-1]["Unexpected Timing Offset(us)"] = 1
    else:
        records[-1]["Current Freq"] = True
    path.write_text("".join(json.dumps(row) + "\n" for row in records))
    before = receipt(path)
    with pytest.raises(ValueError):
        build_report(root, "case", records[-1]["Op Name"], SKILL, tmp_path / "report")
    assert receipt(path) == before
    assert not (tmp_path / "report/profile-report.json").exists()
