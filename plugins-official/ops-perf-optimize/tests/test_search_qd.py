# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

import sys
from pathlib import Path
SCRIPTS = Path(__file__).resolve().parents[1] / "skills/ops-perf-optimize-workflow/scripts"
sys.path.insert(0, str(SCRIPTS))
import search.policy as search_policy


def node(sid, fam, bucket, bottleneck, gain=0.1, cost=1, risk=0.1):
    return {
        "scheme_id": sid,
        "kind": "local",
        "level": "M1",
        "mechanism": fam,
        "mechanism_family": fam,
        "shape_bucket": bucket,
        "bottleneck_type": bottleneck,
        "explore_tag": "exploit",
        "expected_gain_range": [0, gain],
        "cost": cost,
        "risk": risk,
        "status": "candidate",
        "depends_on": [],
    }


def frontier():
    return {
        "nodes": [
            node("a1", "m1", "b1", "mem", 0.3),
            node("a2", "m1", "b1", "mem", 0.2),
            node("b1", "m2", "b1", "vec", 0.1),
            node("b2", "m2", "b1", "vec", 0.05),
        ]
    }


def test_qd_descriptor_and_elite_grid():
    f = frontier()
    ranked, meta = search_policy.qd_rank(f, [])
    assert len(meta["cells"]) == 2
    assert meta["unexplored"] == 2
    assert {search_policy._qd_descriptor(n) for n in f["nodes"]} == {("m1", "b1", "mem"), ("m2", "b1", "vec")}


def test_qd_prefers_unmeasured_cell():
    f = frontier()
    obs = [{"scheme_id": "a1", "outcome": "measured"}]
    ranked, meta = search_policy.qd_rank(f, obs)
    assert ranked[0]["scheme_id"] in {"b1", "b2"}


def test_qd_selection_keeps_ucb_order_within_cell():
    f = frontier()
    out = search_policy.select(f, [{"scheme_id": "b1", "outcome": "measured"}], strategy="qd")
    assert out["selected"] in {"a1", "a2"}
    assert out["qd"]["unexplored"] == 1
