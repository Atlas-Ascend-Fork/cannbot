# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Collector integration with a synthetic CLI boundary; never accesses an NPU."""

import json
from pathlib import Path

import pytest

from test_npu_compute_evidence import evidence, fixture, write
import collect_profile as collector
import npu_compute_backend as backend
import npu_compute_report as profile_report


@pytest.mark.parametrize(
    "policy,samples", [("confidence_effect_v1", 10), ("median_v1", 1), ("median_v1", 3)]
)
def test_registered_collector_preserves_captures_on_resume_and_builds_real_proof(
    tmp_path, monkeypatch, policy, samples
):
    paths = fixture(tmp_path)
    if policy == "median_v1":
        plan = json.loads(paths[0].read_text())
        manifest_path = Path(plan["manifest"]["path"])
        manifest = json.loads(manifest_path.read_text())
        manifest["configuration"]["performance_effect_policy"]["id"] = policy
        plan.update(
            kind=evidence.MEDIAN_KIND,
            samples_per_variant=samples,
            frequency_policy="record_only",
            manifest=write(manifest_path, manifest),
        )
        plan.pop("statistical_method")
        plan.pop("rated_frequency_mhz")
        plan["order"] = [r for r in plan["order"] if r["sample_index"] < samples]
        registration = json.loads(paths[1].read_text())
        registration["artifacts"] = [write(paths[0], plan)]
        write(paths[1], registration)
    monkeypatch.setattr(
        backend, "tool_skill", lambda context: tmp_path / "external-skill"
    )
    monkeypatch.setenv("ASCEND_HOME_PATH", "/example/cann")
    calls = []

    def fake_run(command, cwd, log):
        calls.append(command)
        if "--import" in command:
            archive = Path(command[command.index("--import") + 1])
            root = (
                Path(command[command.index("--export") + 1]) / "actual-returned-child"
            )
            name = "baseline" if archive.read_text() == "baseline" else "candidate"
            write(
                root / "summary.jsonl",
                {
                    "category": "OpInfoSummary",
                    "Op Name": name,
                    "Block Dim": 32,
                    "Device Id": 0,
                    "Pid": 10000 + len(calls),
                    "Task Duration(us)": 100 if name == "baseline" else 90,
                    "Current Freq": 1600 if policy == "median_v1" else 1650,
                    "Rated Freq": 1650,
                },
            )
            log.write_text("npu-compute: unpacked= " + str(root))
        else:
            assert command[1:5] == [
                "--section",
                "PipeUtilization",
                "--cache-control",
                "all",
            ]
            archive = Path(command[command.index("--export") + 1])
            archive.write_text(Path(cwd).name)
            log.write_text("npu-compute: report= " + str(archive))
        return 0

    monkeypatch.setattr(backend, "run", fake_run)
    monkeypatch.setattr(
        profile_report,
        "build_report",
        lambda *a, **k: pytest.fail(
            "timing collection must not build full diagnostics"
        ),
    )
    out = tmp_path / "fresh-collection"
    collector.collect(paths[0], paths[1], out, tmp_path / "external-skill")
    assert len(calls) == samples * 4  # each side needs a capture and import per sample
    proof_paths = (
        paths[0],
        paths[1],
        out / "collection.json",
        out / "baseline.csv",
        out / "candidate.csv",
    )
    if policy == "confidence_effect_v1":
        assert (
            evidence.build_profile_proof(*proof_paths, "case", "baseline", "candidate")[
                "statistics"
            ]["ci_us"][1]
            < 0
        )
    else:
        from summarize_performance_effects import summarize

        summary = summarize(proof_paths[3], proof_paths[4], policy_id=policy)
        assert summary["cases"][0]["classification"] == "effective_improvement"
        with pytest.raises(ValueError, match="does not produce a confidence proof"):
            evidence.build_profile_proof(*proof_paths, "case", "baseline", "candidate")
    collector.collect(paths[0], paths[1], out, tmp_path / "external-skill")
    assert len(calls) == samples * 4
    # A fresh registration cannot re-label previously collected samples.
    registration = json.loads(paths[1].read_text())
    registration["issued_at"] = "2025-01-02T00:00:00+00:00"
    write(paths[1], registration)
    with pytest.raises(ValueError, match="another plan or registration"):
        collector.collect(paths[0], paths[1], out, tmp_path / "external-skill")
    assert len(calls) == samples * 4


def test_outer_zero_with_no_report_is_a_retained_failure_not_success(
    tmp_path, monkeypatch
):
    paths = fixture(tmp_path)
    monkeypatch.setattr(
        backend, "tool_skill", lambda context: tmp_path / "external-skill"
    )
    monkeypatch.setenv("ASCEND_HOME_PATH", "/example/cann")

    def failed(command, cwd, log):
        log.write_text("real outer exit 0; target failed before report creation")
        return 0

    monkeypatch.setattr(backend, "run", failed)
    out = tmp_path / "failed-collection"
    with pytest.raises(ValueError, match="retained failed"):
        collector.collect(paths[0], paths[1], out, tmp_path / "external-skill")
    attempt = json.loads((out / "sample-00/attempt-00/attempt.json").read_text())
    assert attempt["returncode"] == 0 and attempt["status"] == "failed"
    assert not (out / "collection.json").exists()


def test_screened_search_can_select_a_provisional_reference_without_claiming_confidence(
    tmp_path,
):
    import search_policy as search
    from summarize_performance_effects import summarize

    paths = fixture(tmp_path)
    plan = json.loads(paths[0].read_text())
    paths[3].write_text("case_id,total_us\ncase,100\n")
    paths[4].write_text("case_id,total_us\ncase,90\n")
    summary = summarize(
        paths[3], paths[4], policy_id={"id": "confidence_effect_v1", "version": 1}
    )
    identities = {
        v: json.loads(Path(i["execution_identity"]["path"]).read_text())["source"]
        for v, i in plan["identities"].items()
    }
    reports = {}
    for side, slot in [("baseline", 0), ("candidate", 1)]:
        raw = evidence.receipt(tmp_path / f"captures/{slot}/unpacked/summary.jsonl")
        info = json.loads(Path(raw["path"]).read_text())
        from npu_compute_report import timing

        reports[side] = write(
            tmp_path / f"{side}/profile-report.json",
            {
                "provider": "npu-compute",
                "case_id": "case",
                "status": "diagnostic_valid",
                "performance_eligible": False,
                "summary": raw,
                "op_info": info,
                "timing": {**timing(info), "use": "historical report wording"},
                "inspections": [],
                "identity": {
                    "execution_identity": plan["identities"][side][
                        "execution_identity"
                    ],
                    "input_snapshot": plan["snapshot"],
                },
            },
        )
    result = {
        "outcome": "screened",
        "provisional": True,
        "screening_evidence": {"case": reports},
        "scheme_id": "candidate",
        "effect_summary": evidence.receipt(paths[3]),
    }
    contract = {"case_ids": ["case"], "target_socs": ["Ascend950"]}
    manifest = json.loads(Path(plan["manifest"]["path"]).read_text())
    search.checked_screening(result, manifest, contract, identities, summary, [])
    # Selection only changes the working reference; effect stays inconclusive.
    record = {
        "performance": {
            "selected_candidate": "candidate",
            "round_summary": str(paths[3]),
        }
    }
    classification, _ = search.candidate_selection(
        record, result, summary, identities["candidate"], manifest, {"baseline"}
    )
    assert classification == "provisional_improvement"
    assert summary["inconclusive_case_count"] == 1

    # Each case has its own input snapshot; only its two sides must agree.
    snapshot = write(tmp_path / "second-inputs.json", {"input": "second case"})
    second = {}
    for side in ("baseline", "candidate"):
        report = json.loads(Path(reports[side]["path"]).read_text())
        report["case_id"] = "second"
        report["identity"]["input_snapshot"] = snapshot
        second[side] = write(tmp_path / f"{side}/second-report.json", report)
    result["screening_evidence"]["second"] = second
    contract["case_ids"].append("second")
    summary["cases"].append({**summary["cases"][0], "case_id": "second"})
    search.checked_screening(result, manifest, contract, identities, summary, [])
    report = json.loads(Path(second["candidate"]["path"]).read_text())
    report["identity"]["input_snapshot"] = plan["snapshot"]
    second["candidate"] = write(Path(second["candidate"]["path"]), report)
    with pytest.raises(ValueError, match="inputs differ within case"):
        search.checked_screening(result, manifest, contract, identities, summary, [])
