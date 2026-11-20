# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Profiling captures integrated with workflow reuse and preflight recovery."""
import copy
import json
from pathlib import Path
import sys
import pytest
from msopprof_fixture import backend, captured


def test_candidate_sample_reuse_is_validated_against_its_original_plan(tmp_path, monkeypatch):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/ops-perf-optimize-workflow/scripts"))
    import collect_profile
    previous, identity, attempt, _ = captured(tmp_path, monkeypatch, variant="candidate")
    previous.update(kind="profile_median_v1", soc="Ascend950", snapshot={}, precision_policy={}, samples_per_variant=1)
    previous_path = tmp_path / "previous.json"
    previous_path.write_text(json.dumps(previous))
    collection = {"schema_version": 1, "kind": previous["kind"], "plan": backend.receipt(previous_path),
                  "samples": [{"variant": "candidate", "sample_index": 0,
                               "attempts": [backend.receipt(tmp_path / "attempt.json")]}]}
    collection_path = tmp_path / "collection.json"
    collection_path.write_text(json.dumps(collection))
    current = copy.deepcopy(previous)
    current["identities"] = {"baseline": identity, "candidate": dict(identity, runner=["/new/candidate"])}
    current["reuse"] = {"baseline": {"variant": "candidate", "collection": backend.receipt(collection_path)}}
    monkeypatch.setattr(backend.subprocess, "run", lambda *a, **k: pytest.fail("reuse must not start a process"))
    samples = collect_profile.reused_samples(current)
    assert samples["baseline", 0][1] == 5
    # Reuse again after the original candidate became the next round's baseline.
    round2 = tmp_path / "round2.json"
    round2.write_text(json.dumps(current))
    collection2 = tmp_path / "collection2.json"
    collection2.write_text(json.dumps({"schema_version": 1, "kind": current["kind"],
        "plan": backend.receipt(round2), "samples": [{"variant": "baseline", "sample_index": 0,
        **samples["baseline", 0][0]}]}))
    third = copy.deepcopy(current)
    third["identities"]["candidate"]["runner"] = ["/third/candidate"]
    third["reuse"] = {"baseline": {"variant": "baseline", "collection": backend.receipt(collection2)}}
    assert collect_profile.reused_samples(third)["baseline", 0][1] == 5
    assert json.loads((tmp_path / "attempt.json").read_text())["variant"] == "candidate"


def test_reuse_rejects_wrong_side_with_same_runner_but_different_execution_identity(tmp_path, monkeypatch):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/ops-perf-optimize-workflow/scripts"))
    import collect_profile
    previous, candidate, attempt, _ = captured(tmp_path, monkeypatch, variant="candidate")
    baseline = dict(candidate, cwd=str(tmp_path / "another-source"), execution_identity={"source": "different"})
    previous["identities"]["baseline"] = baseline
    previous.update(kind="profile_median_v1", soc="Ascend950", snapshot={}, precision_policy={}, samples_per_variant=1)
    previous_path = tmp_path / "previous.json"
    previous_path.write_text(json.dumps(previous))
    collection_path = tmp_path / "mislabelled-collection.json"
    collection_path.write_text(json.dumps({"schema_version": 1, "kind": previous["kind"],
        "plan": backend.receipt(previous_path), "samples": [{"variant": "baseline", "sample_index": 0,
        "attempts": [backend.receipt(tmp_path / "attempt.json")]}]}))
    current = copy.deepcopy(previous)
    current["reuse"] = {"baseline": {"variant": "baseline", "collection": backend.receipt(collection_path)}}
    monkeypatch.setattr(backend.subprocess, "run", lambda *a, **k: pytest.fail("reuse must not launch"))
    with pytest.raises(ValueError, match="comparison identity changed"):
        collect_profile.reused_samples(current)


@pytest.mark.parametrize("partial", [False, True])
def test_preflight_failure_removes_only_an_empty_attempt_directory(tmp_path, monkeypatch, partial):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/ops-perf-optimize-workflow/scripts"))
    import collect_profile
    plan_path = tmp_path / "plan.json"
    plan_path.write_text("{}")
    registration = tmp_path / "registration.json"
    registration.write_text(
        json.dumps({"artifacts": [backend.receipt(plan_path)], "issued_at": "2000-01-01T00:00:00Z"})
    )
    plan = {"environment": {}, "tool": backend.receipt(plan_path), "identities": {"baseline": {}},
            "order": [{"variant": "baseline", "slot": 0, "sample_index": 0}]}
    monkeypatch.setattr(collect_profile, "validate_plan", lambda *a: (plan, {}))
    monkeypatch.setattr(collect_profile, "reused_samples", lambda *a: {})

    def fail(plan, identity, slot, directory, context):
        if partial:
            (directory / "run.log").write_text("retain partial evidence")
        raise ValueError("device probe unavailable")
    monkeypatch.setattr(collect_profile.report_contract, "collect_attempt", fail)
    out = tmp_path / "collection"
    with pytest.raises(ValueError, match="probe unavailable"):
        collect_profile.collect(plan_path, registration, out)
    directory = out / "sample-00/attempt-00"
    assert directory.exists() is partial
    if partial:
        assert (directory / "run.log").read_text() == "retain partial evidence"
