# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Synthetic OpModel -> scheme mapping tests (no model execution)."""

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "skills/ops-perf-optimize-workflow/scripts"
sys.path.insert(0, str(SCRIPTS))
import opmodel_rank

STDOUT = """  #     Cycles      MII  tiling/slots
  1       4276      n/a  Mb=128 Nb=256 Kb=128 [a_l1=2]
  2       3000      n/a  Mb=256 Nb=256 Kb=256 [a_l1=2]
  3       2500      n/a  Mb=512 Nb=256 Kb=256 [a_l1=2]
wall-clock: 1.0s
"""

BINDING = {
    "axes": {
        "tile": {"param": "Mb"},
        "split_k": {"param": "Kb", "values": {"1": 128, "2": 256}},
    },
    "fixed": {"Nb": 256},
}


def frontier(nodes):
    return {"schema_version": 1, "nodes": nodes}


def node(sid, factors, tag=None):
    return {"scheme_id": sid, "factors": factors, "explore_tag": tag or "exploit"}


def test_rank_maps_and_retains_unmapped():
    schedules = opmodel_rank.parse_schedules(STDOUT)
    result = opmodel_rank.rank(frontier([
        node("s1", {"tile": 128, "split_k": 1}),
        node("s2", {"tile": 256, "split_k": 2}),
        node("s3", {"tile": 512, "split_k": 2}),
        node("s4", {"tile": 1024, "split_k": 2}),
        node("s5", {"tile": 256}),
        node("open", {}, tag="open"),
    ]), schedules, BINDING)
    assert result["ranking"] == ["s3", "s2", "s1", "s4", "s5"]
    assert [item["scheme_id"] for item in result["unmapped"]] == ["s4", "s5"]
    assert result["mapped"][0]["cycles"] == 2500
    assert "open" not in result["ranking"]


def test_no_matching_schedule_is_unmapped():
    schedules = opmodel_rank.parse_schedules(STDOUT)
    result = opmodel_rank.rank(
        frontier([node("x", {"tile": 128, "split_k": 2})]), schedules, BINDING
    )
    assert result["ranking"] == ["x"]
    assert result["unmapped"][0]["reason"] == "no schedule matches binding"


def test_parser_rejects_empty_output():
    with pytest.raises(ValueError, match="no schedule rows"):
        opmodel_rank.parse_schedules("wall-clock: 1.0s\n")


def test_binding_value_missing_is_unmapped():
    schedules = opmodel_rank.parse_schedules(STDOUT)
    result = opmodel_rank.rank(
        frontier([node("x", {"tile": 128, "split_k": 9})]), schedules, BINDING
    )
    assert result["unmapped"][0]["reason"] == "axis missing or value unmapped"
