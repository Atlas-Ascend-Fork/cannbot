# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Exercise round completion and the user-visible report through the CLI."""

import csv
import json
from pathlib import Path
import subprocess
import sys

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


class Run:
    def __init__(self, root: Path, mode: str = "standard"):
        self.root = root
        self.state = root / "workflow-state.json"
        self.report = root / "性能调优报告.md"
        configuration = {
            "precision_diagnosis_policy": "persistent",
            "target_socs": ["Ascend950"],
            "tuning_mode": mode,
            "functional_mode": "reuse_performance",
        }
        if mode == "generalization":
            configuration["generalization"] = {"competitor": {"source": "file"}}
        manifest = root / "run-manifest.json"
        manifest.write_text(json.dumps({
            "configuration": configuration, "inputs": {}, "collections": {},
        }))
        self.command("start", "--manifest", manifest)

    def command(self, *args, expected=0):
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "workflow_state.py"),
             str(args[0]), "--state", str(self.state), *map(str, args[1:])],
            text=True, capture_output=True, cwd=self.root,
        )
        assert result.returncode == expected, result.stdout + result.stderr
        return json.loads(result.stdout)

    def performance(self, name, values, ids=("a", "b", "c")):
        path = self.root / f"{name}.csv"
        with path.open("w", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["case_id", "total_us"])
            writer.writerows(zip(ids, values))
        return path

    def effects(self, name, baseline, candidate):
        path = self.root / f"{name}.json"
        subprocess.run([
            sys.executable, str(SCRIPTS / "summarize_performance_effects.py"),
            "--baseline", str(baseline), "--candidate", str(candidate),
            "--out-json", str(path), "--out-csv", str(path.with_suffix(".csv")),
        ], check=True, capture_output=True, text=True)
        return path

    def complete(self, stage, summaries, candidate="winner", **options):
        current, cumulative = summaries
        return self.command(
            "mark", "--stage", stage, "--status", "complete",
            "--performance-summary", current,
            "--cumulative-performance-summary", cumulative,
            "--selected-candidate", candidate,
            "--performance-scope", options.get("scope", "tuning_subset"),
            expected=options.get("expected", 0),
        )


def table_row(report: str, first_cell: str) -> list[str]:
    report = report.split("## 当前性能结果\n", 1)[1].split("\n## ", 1)[0]
    prefix = f"| {first_cell} |"
    rows = [line for line in report.splitlines() if line.startswith(prefix)]
    assert len(rows) == 1, rows
    return [cell.strip() for cell in rows[0].split("|")[1:-1]]


def test_inspect_reads_selected_context_without_history_or_state_writes(tmp_path):
    run = Run(tmp_path)
    manifest = tmp_path / "run-manifest.json"
    value = json.loads(manifest.read_text())
    value["collections"]["performance_tuning"] = {
        "path": "/frozen/cases.csv", "sha256": "abc", "count": 1000,
        "selection": {"case_ids": [f"case-{i}" for i in range(1000)]},
    }
    manifest.write_text(json.dumps(value))
    run.command("sync-manifest")
    for stage, message in [("round1.impl", "old"), ("round2.impl", "first"), ("round2.impl", "latest")]:
        run.command("progress", "--stage", stage, "--message", message)
    state_before, report_before = run.state.read_bytes(), run.report.read_bytes()
    result = run.command("inspect", "--stage", "round2.impl", "--recent", 1)
    assert [event["message"] for event in result["recent_events"]] == ["latest"]
    assert result["stages"] == {"round2.impl": None}
    assert result["collections"]["performance_tuning"] == {
        "path": "/frozen/cases.csv", "sha256": "abc", "count": 1000,
    }
    assert run.state.read_bytes() == state_before
    assert run.report.read_bytes() == report_before
    assert run.command("inspect", "--recent", 0)["recent_events"] == []
    manifest.write_text(manifest.read_text() + "\n")
    assert "stale_inputs" in run.command("inspect", expected=2)["error"]


def test_each_round_refreshes_current_and_cumulative_results_and_keeps_history(tmp_path):
    run = Run(tmp_path)
    original = run.performance("original", [10, 20, 100])
    first = run.performance("first", [8, 21, 101])
    first_effects = run.effects("first-effects", original, first)
    run.complete("round1.complete", (first_effects, first_effects), "candidate-one")
    report = run.report.read_text()
    assert table_row(report, "本轮")[1:6] == ["3", "1", "2", "1", "1"]
    assert len(table_row(report, "本轮")) == 7
    assert table_row(report, "a")[1:4] == ["10.000000", "10.000000", "8.000000"]
    assert table_row(report, "c")[-1] == "jitter_no_effect"

    second = run.performance("second", [7, 19, 101])
    second_effects = run.effects("second-effects", first, second)
    cumulative = run.effects("cumulative", original, second)
    run.complete("round2.complete", (second_effects, cumulative), "candidate-two")
    report = run.report.read_text()
    assert table_row(report, "本轮")[1:6] == ["3", "1", "2", "2", "0"]
    assert table_row(report, "累计")[6] == "1.226279x"
    assert table_row(report, "本轮")[6] == "1.123903x"
    assert table_row(report, "a")[1:4] == ["10.000000", "8.000000", "7.000000"]
    assert table_row(report, "`round1.complete`")[1] == "candidate-one"
    assert table_row(report, "`round2.complete`")[1] == "candidate-two"

    # Retaining the current baseline still refreshes the report and preserves gains.
    no_change = run.effects("retained", second, second)
    run.complete("round3.complete", (no_change, cumulative), "baseline")
    report = run.report.read_text()
    assert table_row(report, "本轮")[1:7] == ["3", "3", "0", "0", "0", "N/A"]
    assert table_row(report, "累计")[6] == "1.226279x"
    assert table_row(report, "a")[1:4] == ["10.000000", "7.000000", "7.000000"]
    state = json.loads(run.state.read_text())
    checkpoint = state["stages"]["round3.complete"]
    assert checkpoint["performance"]["selected_candidate"] == "baseline"
    assert "cases" not in checkpoint["performance"]
    run.command("verify")
    run.command("render")
    assert table_row(run.report.read_text(), "累计") == table_row(report, "累计")
    run.command("progress", "--stage", "final.functional", "--message", "full validation running")
    run.complete("final.performance", (cumulative, cumulative), "candidate-two", scope="full")
    assert table_row(run.report.read_text(), "`final.performance`")[2] == "全集"
    run.command("finish", "--status", "success", "--reason-code", "completed", "--message", "done")
    assert table_row(run.report.read_text(), "累计") == table_row(report, "累计")


@pytest.mark.parametrize("stage", ["round1.complete", "gen.round1.complete", "gen.outer1.exit", "final.performance"])
def test_completion_requires_performance_without_mutating_state_or_report(tmp_path, stage):
    run = Run(tmp_path)
    before = (run.state.read_bytes(), run.report.read_bytes())
    result = run.command("mark", "--stage", stage, "--status", "complete", expected=2)
    assert "--performance-summary" in result["error"]
    assert (run.state.read_bytes(), run.report.read_bytes()) == before


@pytest.mark.parametrize(
    "problem",
    ["wrong-count", "different-candidate", "invalid-json", "missing-source", "missing-null-metric"],
)
def test_invalid_performance_cannot_complete_round(tmp_path, problem):
    run = Run(tmp_path)
    original = run.performance("original", [10, 20, 100])
    winner = run.performance("winner", [8, 21, 101])
    effects = run.effects("effects", original, winner)
    cumulative = effects
    if problem == "wrong-count":
        payload = json.loads(effects.read_text())
        payload["total_case_count"] = 99
        effects.write_text(json.dumps(payload))
    elif problem == "different-candidate":
        other = run.performance("other", [8, 21, 101])
        cumulative = run.effects("other-effects", original, other)
    elif problem == "invalid-json":
        effects.write_text("[]")
    elif problem == "missing-null-metric":
        run.effects("effects", original, original)
        payload = json.loads(effects.read_text())
        payload.pop("effective_geomean_speedup")
        effects.write_text(json.dumps(payload))
    else:
        winner.unlink()
    before = (run.state.read_bytes(), run.report.read_bytes())
    run.complete("round1.complete", (effects, cumulative), expected=2)
    assert (run.state.read_bytes(), run.report.read_bytes()) == before


@pytest.mark.parametrize("damage", ["modify-summary", "delete-source", "invalidate-stage"])
def test_invalidated_evidence_is_not_shown_as_current_performance(tmp_path, damage):
    run = Run(tmp_path)
    original = run.performance("original", [10, 20, 100])
    winner = run.performance("winner", [8, 21, 101])
    effects = run.effects("effects", original, winner)
    run.complete("round1.complete", (effects, effects))
    if damage == "modify-summary":
        effects.write_text("{}")
    elif damage == "delete-source":
        winner.unlink()
    else:
        run.command("mark", "--stage", "round1.complete", "--status", "invalid")
    run.command("render")
    report = run.report.read_text()
    assert "当前性能结果不可用" in report
    assert "| a |" not in report
    if damage != "invalidate-stage":
        run.command("verify", expected=2)
        assert json.loads(run.state.read_text())["stages"]["round1.complete"]["status"] == "invalid"
    run.command("finish", "--status", "blocked", "--reason-code", "external_blocker", "--message", "repair evidence")


def test_generalization_subset_and_full_results_do_not_mix_case_sets(tmp_path):
    run = Run(tmp_path, "generalization")
    original = run.performance("original-subset", [10], ids=["a|special"])
    winner = run.performance("winner-subset", [8], ids=["a|special"])
    effects = run.effects("subset-effects", original, winner)
    run.complete("gen.round1.complete", (effects, effects))
    report = run.report.read_text()
    assert table_row(report, "a&#124;special")[3] == "8.000000"
    assert table_row(report, "本轮")[1] == "1"

    full_original = run.performance("original-full", [10, 20, 100])
    full_winner = run.performance("winner-full", [8, 21, 101])
    full_effects = run.effects("full-effects", full_original, full_winner)
    run.complete("gen.outer1.exit", (full_effects, full_effects), scope="full")
    report = run.report.read_text()
    assert table_row(report, "本轮")[1] == "3"
    assert table_row(report, "`gen.round1.complete`")[2:4] == ["调优子集", "1"]
    assert table_row(report, "`gen.outer1.exit`")[2:4] == ["全集", "3"]
    assert "| a&#124;special |" not in report


def test_legacy_completed_round_is_explicitly_missing_and_can_be_backfilled(tmp_path):
    run = Run(tmp_path)
    state = json.loads(run.state.read_text())
    state["stages"]["round1.complete"] = {"status": "complete", "completed_at": state["updated_at"]}
    run.state.write_text(json.dumps(state))
    run.command("render")
    assert "尚未登记性能摘要" in run.report.read_text()
    original = run.performance("original", [10, 20, 100])
    effects = run.effects("retained", original, original)
    run.complete("round1.complete", (effects, effects), "baseline")
    assert table_row(run.report.read_text(), "本轮")[6] == "N/A"


def conclusion(report):
    return report.split("## 当前结论\n", 1)[1].split("\n## ", 1)[0]


def test_dispatch_and_acceptance_refresh_conclusion_without_publishing_intermediate_results(tmp_path):
    run = Run(tmp_path)
    original = run.performance("original", [10, 20, 100])
    first = run.performance("first", [8, 21, 101])
    effects = run.effects("effects", original, first)
    run.command("mark", "--stage", "round1.impl", "--status", "in_progress")
    run.command("progress", "--stage", "round1.impl", "--message", "diagnosing",
                "--next-action", "inspect candidate scratch memory")
    assert "inspect candidate scratch memory" in conclusion(run.report.read_text())
    run.command("mark", "--stage", "round1.complete", "--status", "complete",
                "--performance-summary", effects, "--cumulative-performance-summary", effects,
                "--selected-candidate", "first", "--message", "保留已验收实现",
                "--next-action", "分析剩余性能差距")
    report = run.report.read_text()
    assert "保留已验收实现" in conclusion(report)
    assert "分析剩余性能差距" in conclusion(report)
    assert "inspect candidate scratch memory" not in conclusion(report)
    assert "当前阶段：`阶段间歇`" in conclusion(report)
    current = table_row(report, "a")

    run.command("mark", "--stage", "round2.analysis", "--status", "in_progress")
    report = run.report.read_text()
    assert "当前阶段：`round2.analysis`" in conclusion(report)
    assert "等待 `round2.analysis` 产出并复核" in conclusion(report)
    assert "分析剩余性能差距" not in conclusion(report)
    assert "保留已验收实现" in conclusion(report)
    run.command("progress", "--stage", "round2.analysis", "--message", "unverified candidate is faster")
    assert "unverified candidate" not in conclusion(run.report.read_text())
    assert table_row(run.report.read_text(), "a") == current
    run.command("render")
    assert table_row(run.report.read_text(), "a") == current


def test_equal_completion_times_use_event_order_after_reload(tmp_path):
    run = Run(tmp_path)
    original = run.performance("original", [10, 20, 100])
    first = run.performance("first", [8, 21, 101])
    effects = run.effects("effects", original, first)
    for stage in ("round9.complete", "round10.complete", "final.performance"):
        run.complete(stage, (effects, effects), candidate=stage)
    state = json.loads(run.state.read_text())
    for record in state["stages"].values():
        record["completed_at"] = "2026-01-01T00:00:00Z"
    run.state.write_text(json.dumps(state, sort_keys=True))
    run.command("render")
    report = run.report.read_text()
    assert "最近性能保存点：`final.performance`" in report
    assert "当前保留实现：`final.performance`" in report
    run.command("mark", "--stage", "round11.analysis", "--status", "in_progress")
    assert "最近性能保存点：`final.performance`" in run.report.read_text()


def test_invalidated_checkpoint_does_not_keep_success_conclusion(tmp_path):
    run = Run(tmp_path)
    original = run.performance("original", [10, 20, 100])
    effects = run.effects("effects", original, original)
    run.complete("round1.complete", (effects, effects))
    run.command("mark", "--stage", "round1.complete", "--status", "invalid")
    assert "原结论待复核" in conclusion(run.report.read_text())
