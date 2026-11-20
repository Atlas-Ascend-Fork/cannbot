# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Search consumes real effect summaries; it never executes a task runner."""

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = (
    Path(__file__).resolve().parents[1] / "skills/ops-perf-optimize-workflow/scripts"
)
sys.path.insert(0, str(SCRIPTS))
# ruff: noqa: E402
from search import evidence
from performance_effect_evidence import receipt
from summarize_performance_effects import summarize
from device_fixture import bind_plan
from test_msopprof import fake_tool
from test_npu_compute_evidence import fixture as identity_fixture, write as write_receipt


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))
    return path


def make_index(
    folder, values=None, cases=("a", "b"), policy="median_v1", manifest=None
):
    folder.mkdir(parents=True, exist_ok=True)
    if manifest is None:
        manifest = write(
            folder / "manifest.json",
            {
                "configuration": {
                    "performance_effect_policy": {"id": policy, "version": 1}
                }
            },
        )
    case_path = folder / "cases.csv"
    case_path.write_text("case_id\n" + "\n".join(cases) + "\n")
    baseline = folder / "baseline.csv"
    baseline.write_text(
        "case_id,total_us\n" + "".join(f"{case},100\n" for case in cases)
    )
    refs = []
    for scheme, times in (values or {"fast": [90] * len(cases)}).items():
        candidate = folder / f"{scheme}.csv"
        candidate.write_text(
            "case_id,total_us\n"
            + "".join(f"{case},{value}\n" for case, value in zip(cases, times))
        )
        summary = write(
            folder / f"{scheme}-effect.json",
            summarize(baseline, candidate, policy_id=policy),
        )
        refs.append({"scheme_id": scheme, "effect_summary": receipt(summary)})
    return write(
        folder / "index.json",
        {
            "schema_version": 1,
            "manifest": receipt(manifest),
            "cases": receipt(case_path),
            "candidates": refs,
        },
    )


def test_existing_summary_keeps_units_and_does_not_fabricate_repeats(tmp_path):
    index = make_index(tmp_path)
    result = evidence.build(index, {"nodes": [{"scheme_id": "fast"}]})
    case = result["candidates"][0]["cases"][0]
    assert (case["candidate_us"], case["reference_us"], case["ratio"]) == (90, 100, 0.9)
    assert case["classification"] == "effective_improvement"
    assert "ratio_samples" not in case
    assert "confidence_interval" not in case
    assert result["policy_id"] == "median_v1"
    assert result["evidence_role"] == "screening"


@pytest.mark.parametrize(
    "mutation, message",
    [
        ("sha", "dependency changed"),
        ("csv", "stale or altered"),
        ("summary", "stale or altered"),
        ("policy", "policy differs"),
        ("cases", "coverage/order"),
        ("scheme", "unknown/duplicate"),
        ("duplicate", "unknown/duplicate"),
    ],
)
def test_rejects_invalid_evidence_bindings(tmp_path, mutation, message):
    index = make_index(tmp_path)
    data = json.loads(index.read_text())
    summary = tmp_path / "fast-effect.json"
    if mutation == "sha":
        summary.write_text(summary.read_text() + " ")
    elif mutation == "csv":
        path = tmp_path / "fast.csv"
        path.write_text(path.read_text().replace("90", "80"))
    elif mutation == "summary":
        payload = json.loads(summary.read_text())
        payload["cases"][0]["classification"] = "effective_regression"
        write(summary, payload)
        data["candidates"][0]["effect_summary"] = receipt(summary)
    elif mutation == "policy":
        manifest = tmp_path / "manifest.json"
        write(
            manifest,
            {
                "configuration": {
                    "performance_effect_policy": {
                        "id": "confidence_effect_v1",
                        "version": 1,
                    }
                }
            },
        )
        data["manifest"] = receipt(manifest)
    elif mutation == "cases":
        cases = tmp_path / "cases.csv"
        cases.write_text("case_id\nb\na\n")
        data["cases"] = receipt(cases)
    elif mutation == "scheme":
        data["candidates"][0]["scheme_id"] = "unknown"
    else:
        data["candidates"].append(data["candidates"][0])
    write(index, data)
    with pytest.raises(ValueError, match=message):
        evidence.build(index, {"nodes": [{"scheme_id": "fast"}]})


def test_saved_adaptation_detects_transitive_csv_changes(tmp_path):
    index = make_index(tmp_path)
    frontier = {"nodes": [{"scheme_id": "fast"}]}
    saved = write(tmp_path / "measurements.json", evidence.build(index, frontier))
    (tmp_path / "baseline.csv").write_text("case_id,total_us\na,101\nb,101\n")
    with pytest.raises(ValueError, match="stale or altered"):
        evidence.read(saved, frontier)


def test_existing_short_collection_feeds_search_without_new_captures(tmp_path, monkeypatch):
    import collect_profile
    import report_contract

    plan_path, registration, *_ = identity_fixture(tmp_path)
    plan = json.loads(plan_path.read_text())
    manifest_path = Path(plan["manifest"]["path"])
    manifest = json.loads(manifest_path.read_text())
    manifest["configuration"]["performance_effect_policy"]["id"] = "median_v1"
    monkeypatch.setenv("ASCEND_HOME_PATH", "/example/cann")
    monkeypatch.setenv("ASCEND_RT_VISIBLE_DEVICES", "0")
    backend = report_contract.backend({"provider": "msopprof"})
    plan.update(backend.prepare({"tool": str(fake_tool(tmp_path)), "launch_count": 2}))
    plan.update(kind="profile_median_v1", samples_per_variant=1, order=plan["order"][:2],
                manifest=write_receipt(manifest_path, manifest))
    for variant, kernel, blocks in (("baseline", "A", 4), ("candidate", "B", 8)):
        plan["identities"][variant].update(kernel_name=kernel, block_dim=blocks)
    bind_plan(plan)
    monkeypatch.setattr(backend.device_context, "probe", lambda *args: plan["device_binding"])
    registered = json.loads(registration.read_text())
    registered["artifacts"] = [write_receipt(plan_path, plan)]
    write(registration, registered)
    output = tmp_path / "captures"
    collect_profile.collect(plan_path, registration, output)
    attempts = list(output.glob("sample-*/attempt-*/attempt.json"))
    assert len(attempts) == 2
    assert all(json.loads(path.read_text())["status"] == "valid" for path in attempts)

    def forbid_capture(*args, **kwargs):
        pytest.fail("search must consume existing measurements without launching a capture")

    monkeypatch.setattr(backend, "collect_attempt", forbid_capture)
    summary = write(
        tmp_path / "effect.json",
        summarize(
            output / "baseline.csv", output / "candidate.csv", policy_id="median_v1"
        ),
    )
    cases = tmp_path / "search-cases.csv"
    cases.write_text("case_id\n" + plan["effect_case_id"] + "\n")
    index = write(
        tmp_path / "index.json",
        {
            "schema_version": 1,
            "manifest": plan["manifest"],
            "cases": receipt(cases),
            "candidates": [{"scheme_id": "fast", "effect_summary": receipt(summary)}],
        },
    )
    result = evidence.build(index, {"nodes": [{"scheme_id": "fast"}]})
    assert plan["samples_per_variant"] == 1
    assert result["candidates"][0]["cases"][0]["ratio"] == 0.5
