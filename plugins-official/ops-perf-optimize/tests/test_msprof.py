# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Network msprof through the workflow's median collector and reuse path."""
import copy
import csv
import json
from pathlib import Path
import pytest
import report_contract
import report_common
from device_fixture import bind_plan
from msprof_fixture import NAMES, fake_tool

backend = report_contract.backend({"provider": "msprof"})


def test_generic_median_collector_multikernel_to_single_and_reuse(tmp_path, monkeypatch):
    from test_npu_compute_evidence import fixture, write
    import collect_profile
    paths = fixture(tmp_path)
    plan = json.loads(paths[0].read_text())
    executable = fake_tool(tmp_path)
    plan.update(report_contract.prepare({"tools": ["msprof"], "tool": str(executable)}))
    plan.update(kind="profile_median_v1", samples_per_variant=1)
    manifest_path = Path(plan["manifest"]["path"])
    manifest = json.loads(manifest_path.read_text())
    manifest["configuration"]["performance_effect_policy"] = {"id": "median_v1", "version": 1}
    plan["manifest"] = write(manifest_path, manifest)
    plan["order"] = [
        {"slot": i, "variant": name, "sample_index": 0} for i, name in enumerate(("baseline", "candidate"))
    ]
    monkeypatch.setenv("ASCEND_HOME_PATH", "/example/cann")
    bind_plan(plan)
    monkeypatch.setattr(backend.device_context, "probe", lambda *a: plan["device_binding"])
    for variant, identity in plan["identities"].items():
        identity["runner"].append(variant)
        identity["kernels"] = ([{"name": NAMES[0], "occurrence": 0}, {"name": NAMES[1]},
                                {"name": NAMES[2]}, {"name": NAMES[0], "occurrence": 1}]
                               if variant == "baseline" else [{"name": NAMES[0]}])
    registered = write(paths[0], plan)
    registration = json.loads(paths[1].read_text())
    registration["artifacts"] = [registered]
    write(paths[1], registration)
    out = tmp_path / "collected"
    collect_profile.collect(paths[0], paths[1], out)
    for variant, expected in [("baseline", 18.478), ("candidate", 5.415)]:
        with (out / f"{variant}.csv").open() as f:
            rows = list(csv.DictReader(f))
        assert float(rows[0]["total_us"]) == expected
    before = (out / "collection.json").read_bytes()
    monkeypatch.setattr(report_contract, "collect_attempt", lambda *a, **k: pytest.fail("reuse must not collect"))
    collect_profile.collect(paths[0], paths[1], out)
    assert (out / "collection.json").read_bytes() == before
    reused = copy.deepcopy(plan)
    reused["reuse"] = {
        "baseline": {"collection": report_common.receipt(out / "collection.json"), "variant": "baseline"}
    }
    assert collect_profile.reused_samples(reused)["baseline", 0][1] == 18.478
