# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Synthetic + vendored-engine tests for the L0 Roofline adapter."""

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "skills/ops-perf-optimize-workflow/scripts"
sys.path.insert(0, str(SCRIPTS))
import l0_roofline
import search_policy as search

from test_search_frontier import frontier as frontier_fixture


def _frontier(nodes):
    return {"schema_version": 1, "best_total_us": 100.0, "nodes": nodes}


def test_build_fragment_bounds_and_unmapped_are_conservative():
    frag = l0_roofline.build_fragment(
        _frontier([
            {"scheme_id": "s1", "explore_tag": "exploit", "factors": {"case_id": "a"}},
            {"scheme_id": "s2", "explore_tag": "exploit", "bindings": {"case_id": "b"}},
            {"scheme_id": "s3", "explore_tag": "exploit", "factors": {}},
            {"scheme_id": "open", "explore_tag": "open", "factors": {"case_id": "a"}},
        ]),
        {"a": {"theoretical_time_us": 3.0, "bound": "mte2_bound", "_template": "resident"},
         "b": {"theoretical_time_us": 5.0, "bound": "vector_bound", "_template": "split"}},
        [{"path": "/tmp/flow.json", "sha256": "0" * 64}],
        "rms_norm",
        "ascend950pr_9589",
    )
    assert frag["status"] == "applied"
    assert frag["mode"] == "evidence"
    assert frag["coverage"] == 2
    assert frag["bound_floor_us"] == 3.0
    assert frag["pruned"] == [] and frag["budget_skipped"] == 0
    assert [c["scheme_id"] for c in frag["candidates"]] == ["s1", "s2"]
    assert frag["unmapped"] == [{"scheme_id": "s3", "reason": "no case_id mapping"}]


def test_cli_engine_report_keeps_pruning_disabled(tmp_path):
    frontier = tmp_path / "frontier.json"
    frontier.write_text(json.dumps(_frontier([
        {"scheme_id": "s1", "explore_tag": "exploit", "factors": {"case_id": "a"}},
        {"scheme_id": "s2", "explore_tag": "exploit", "factors": {}},
    ])))
    cases = tmp_path / "cases.json"
    cases.write_text("{}")
    report = tmp_path / "report.json"
    report.write_text(json.dumps({"results": {"a": {"theoretical_time_us": 2.5}}}))
    out = tmp_path / "l0.json"
    rc = l0_roofline.main([
        "--op", "rms_norm", "--cases", str(cases), "--frontier", str(frontier),
        "--out", str(out), "--engine-report", str(report),
    ])
    assert rc == 0
    frag = json.loads(out.read_text())
    assert frag["coverage"] == 1 and frag["pruned"] == [] and frag["budget_skipped"] == 0
    assert frag["unmapped"][0]["scheme_id"] == "s2"


def test_fragment_satisfies_frontier_schema(tmp_path):
    value = frontier_fixture(tmp_path)
    frag = l0_roofline.build_fragment(value, {"a": {"theoretical_time_us": 1.0}}, [], "rms_norm")
    value["prefilter"]["l0"] = frag
    assert search.validate_frontier(value)


def test_vendored_engine_runs_rms_norm(tmp_path):
    skill = l0_roofline.default_skill_dir()
    if skill is None:
        pytest.skip("vendored cannbot-skills submodule not initialized")
    cases = skill / "references/examples/rms_norm_cases.json"
    results, variant = l0_roofline.run_engine(skill, "rms_norm", cases)
    assert "rms_norm_s_512x4096" in results
    assert results["rms_norm_s_512x4096"]["theoretical_time_us"] > 0
    assert variant == "ascend950pr_9589"
