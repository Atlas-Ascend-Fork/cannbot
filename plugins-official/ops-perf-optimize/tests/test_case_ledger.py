# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: CANN-2.0
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# the CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You should not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Per-case convergence ledger: partitioning, gates, verdict identity, envelope."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

SCRIPTS = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "ops-perf-optimize-workflow"
    / "scripts"
)
sys.path.insert(0, str(SCRIPTS))

from test_round_performance_report import Run  # noqa: E402

TARGET_US = 50.0
PREP = SCRIPTS / "prepare_case_sets.py"


def _objective(scope=None):
    payload = {
        "mode": "target",
        "metric": "case_gpu_npu_ratio",
        "comparison": "ge",
        "value": 0.185,
        "unit": "ratio",
    }
    if scope is not None:
        payload["scope"] = scope
    return payload


class LedgerRun(Run):
    """Round-performance run plus a registered frozen per-case target set."""

    def __init__(
        self,
        root: Path,
        *,
        with_targets: bool = True,
        objective: dict | None = None,
    ):
        super().__init__(root, objective=objective)
        self.targets = None
        if not with_targets:
            return
        self.targets = root / "performance-targets.json"
        self.targets.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "target_socs": ["Ascend950"],
                    "cases": [
                        {
                            "case_id": case,
                            "target_soc": "Ascend950",
                            "target_us": TARGET_US,
                        }
                        for case in ("a", "b", "c")
                    ],
                }
            )
        )
        self.command(
            "mark",
            "--stage",
            "phase.baseline",
            "--status",
            "complete",
            "--artifact",
            self.targets,
        )

    def ledger(self) -> dict:
        return json.loads(self.state.read_text())["case_convergence"]

    def verdict(self, case_id: str, reference: str, *, evidence_sha: str | None = None):
        proof = self.root / f"verdict-evidence-{case_id}.txt"
        proof.write_text(f"per-case ceiling evidence for {case_id}\n", encoding="utf-8")
        sha = hashlib.sha256(proof.read_bytes()).hexdigest()
        payload = {
            "schema_version": 1,
            "case_id": case_id,
            "verdict": "NEAR-BANDWIDTH-CEILING",
            "measured_us": TARGET_US + 1.0,
            "ceiling_us": TARGET_US + 1.2,
            "headroom_us": 0.2,
            "mbu": 0.93,
            "mfu": None,
            "mte2_util": None,
            "reference_identity": reference,
            "evidence": [{"path": str(proof), "sha256": evidence_sha or sha}],
        }
        path = self.root / f"case-verdict-{case_id}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path


def _one_round(run, name, values, candidate):
    original = run.performance("original", [100, 100, 100])
    measured = run.performance(name, values)
    effects = run.effects(f"effect-{name}", original, measured)
    run.complete("round1.complete", (effects, effects), candidate)


def _reset_targets(run, targets):
    run.targets.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "target_socs": ["Ascend950"],
                "cases": [
                    {
                        "case_id": case_id,
                        "target_soc": "Ascend950",
                        "target_us": target_us,
                    }
                    for case_id, target_us in targets
                ],
            }
        )
    )
    run.command(
        "mark",
        "--stage",
        "phase.baseline",
        "--status",
        "complete",
        "--artifact",
        run.targets,
    )


def _subset_round(run, stage, name, case_id, value, candidate):
    original = run.performance(f"{name}-original", [100], ids=[case_id])
    measured = run.performance(name, [value], ids=[case_id])
    effects = run.effects(f"effect-{name}", original, measured)
    run.complete(stage, (effects, effects), candidate)


def test_ledger_partitions_cases_after_each_round_checkpoint(tmp_path):
    run = LedgerRun(tmp_path)
    _one_round(run, "candidate", [40, 100, 100], "cand-1")
    ledger = run.ledger()
    assert ledger["reference_candidate"] == "cand-1"
    assert ledger["cases"]["a"]["status"] == "optimized"
    assert ledger["cases"]["a"]["gap_us"] == -10.0
    assert ledger["cases"]["b"]["status"] == "headroom_open"
    assert ledger["cases"]["b"]["gap_us"] == 50.0
    assert ledger["cases"]["c"]["status"] == "headroom_open"
    report = run.report.read_text()
    assert "逐 case 收敛账本" in report
    assert "未了结 case" in report
    view = run.command("inspect")
    assert view["case_convergence"]["counts"]["optimized"] == 1
    assert [item["case_id"] for item in view["case_convergence"]["unresolved"]] == [
        "b",
        "c",
    ]


def _finish(run, status, reason_code, message, **kwargs):
    return run.command(
        "finish",
        "--status",
        status,
        "--reason-code",
        reason_code,
        "--message",
        message,
        **kwargs,
    )


def test_convergence_finish_requires_a_terminal_ledger(tmp_path):
    run = LedgerRun(tmp_path)
    _one_round(run, "candidate", [40, 100, 100], "cand-1")
    rejected = _finish(
        run,
        "success",
        "no_material_improvement",
        "no direction left",
        expected=2,
    )
    assert "unresolved cases" in rejected["error"]
    assert "b" in rejected["error"] and "c" in rejected["error"]
    # A waiver discharges the human decision; the remaining unresolved case still blocks.
    run.command(
        "case-converge",
        "--case-id",
        "b",
        "--status",
        "waived",
        "--reason",
        "user accepts b as-is",
    )
    still_rejected = _finish(
        run,
        "success",
        "ceiling_bound",
        "bounded",
        expected=2,
    )
    assert "c[headroom_open]" in still_rejected["error"]
    # Honest budget stop is a distinct, allowed reason code with an attached summary.
    budget = _finish(
        run,
        "awaiting_operator",
        "budget_exhausted",
        "authorized rounds consumed; c still has headroom",
    )
    assert budget["status"] == "awaiting_operator"
    state = json.loads(run.state.read_text())
    summary = state["terminal"]["case_convergence"]
    assert summary["unresolved_count"] == 1
    assert summary["unresolved"][0]["case_id"] == "c"
    assert state["terminal"]["reason_code"] == "budget_exhausted"
    report = run.report.read_text()
    assert "未了结 case：c" in report


def test_converged_verdict_identity_binding_and_stale_demotion(tmp_path):
    run = LedgerRun(tmp_path)
    _one_round(run, "candidate", [40, 100, 100], "cand-1")
    original = run.performance("original", [100, 100, 100])
    candidate = run.performance("candidate", [40, 100, 100])
    verdict = run.verdict("b", "cand-1")
    run.command(
        "case-converge", "--case-id", "b", "--status", "converged", "--verdict", verdict
    )
    assert run.ledger()["cases"]["b"]["status"] == "converged"
    # A new reference implementation promotion demotes the claim (identity I3).
    promoted = run.performance("promoted", [40, 100, 45])
    round_effects = run.effects("round2", candidate, promoted)
    cumulative = run.effects("round2-cumulative", original, promoted)
    run.complete("round2.complete", (round_effects, cumulative), "cand-2")
    entry = run.ledger()["cases"]["b"]
    assert entry["status"] == "headroom_open"
    assert (
        entry["stale_verdict"]["demoted_because"] == "reference_implementation_changed"
    )
    # c meanwhile meets its target on the promoted implementation.
    assert run.ledger()["cases"]["c"]["status"] == "optimized"
    report = run.report.read_text()
    assert "verdict 已过期" in report


def test_verdict_rejected_on_stale_identity_and_tampered_evidence(tmp_path):
    run = LedgerRun(tmp_path)
    _one_round(run, "candidate", [40, 100, 100], "cand-1")
    stale = run.command(
        "case-converge",
        "--case-id",
        "b",
        "--status",
        "converged",
        "--verdict",
        run.verdict("b", "someone-else"),
        expected=2,
    )
    assert "stale" in stale["error"]
    verdict = run.verdict("b", "cand-1", evidence_sha="0" * 64)
    tampered = run.command(
        "case-converge",
        "--case-id",
        "b",
        "--status",
        "converged",
        "--verdict",
        verdict,
        expected=2,
    )
    assert "SHA mismatch" in tampered["error"]
    optimized = run.command(
        "case-converge",
        "--case-id",
        "a",
        "--status",
        "waived",
        "--reason",
        "x",
        expected=2,
    )
    assert "already meets" in optimized["error"]
    assert run.ledger()["cases"]["b"]["status"] == "headroom_open"


def test_waiver_survives_recompute_until_the_target_is_met(tmp_path):
    run = LedgerRun(tmp_path)
    _one_round(run, "candidate", [40, 100, 100], "cand-1")
    original = run.performance("original", [100, 100, 100])
    candidate = run.performance("candidate", [40, 100, 100])
    run.command(
        "case-converge", "--case-id", "b", "--status", "waived", "--reason", "accepted"
    )
    improved = run.performance("improved", [40, 45, 100])
    round_effects = run.effects("round2", candidate, improved)
    cumulative = run.effects("round2-cumulative", original, improved)
    run.complete("round2.complete", (round_effects, cumulative), "cand-2")
    assert run.ledger()["cases"]["b"]["status"] == "optimized"
    assert run.ledger()["cases"]["c"]["status"] == "headroom_open"


def test_missing_targets_block_convergence_but_not_other_finishes(tmp_path):
    run = LedgerRun(tmp_path, with_targets=False)
    original = run.performance("original", [100, 100, 100])
    candidate = run.performance("candidate", [40, 100, 100])
    effects = run.effects("effect", original, candidate)
    run.complete("round1.complete", (effects, effects), "cand-1")
    blocked = run.command(
        "finish",
        "--status",
        "success",
        "--reason-code",
        "no_material_improvement",
        "--message",
        "cannot optimize",
        expected=2,
    )
    assert "targets are unavailable" in blocked["error"]
    unavailable = run.command("remaining-work", expected=2)
    assert "targets are unavailable" in unavailable["error"]
    parked = run.command(
        "finish",
        "--status",
        "awaiting_operator",
        "--reason-code",
        "budget_exhausted",
        "--message",
        "stop here",
    )
    assert parked["status"] == "awaiting_operator"
    state = json.loads(run.state.read_text())
    assert state["terminal"]["case_convergence"]["targets_error"]
    report = run.report.read_text()
    assert "账本不可用" in report


def test_remaining_work_envelope_inherits_facts_and_drops_priors(tmp_path):
    run = LedgerRun(tmp_path)
    _one_round(run, "candidate", [40, 100, 100], "cand-1")
    out = tmp_path / "remaining-work.json"
    payload = run.command("remaining-work", "--out", out)
    assert [item["case_id"] for item in payload["remaining_cases"]] == ["b", "c"]
    assert payload["inherit"]["achieved_cases"] == ["a"]
    assert payload["do_not_inherit"]["failure_observations"] == "excluded"
    assert payload["do_not_inherit"]["stagnation_counters"] == "reset"
    assert json.loads(out.read_text())["summary"]["optimized"] == 1
    # The command is read-only: no terminal record is written.
    assert "terminal" not in json.loads(run.state.read_text())

    state = json.loads(run.state.read_text())
    state["events"].extend(
        [
            {
                "kind": "search_result",
                "result": {
                    "scheme_id": scheme_id,
                    "mechanism": {
                        "status": "verified",
                        "evidence": [f"mechanism-{scheme_id}.json"],
                    },
                    "evidence": [f"outcome-{scheme_id}.json"],
                },
            }
            for scheme_id in ("s1", "s2")
        ]
    )
    run.state.write_text(json.dumps(state))
    payload = run.command("remaining-work")
    assert payload["schema_version"] == 2
    inherited = payload["inherit"]["verified_mechanisms"]
    assert [item["scheme_id"] for item in inherited] == ["s1", "s2"]
    assert [item["evidence"] for item in inherited] == [
        ["mechanism-s1.json"],
        ["mechanism-s2.json"],
    ]
    assert all(item["mechanism"]["status"] == "verified" for item in inherited)
    assert payload["source_state"]["path"] == str(run.state.resolve())
    assert payload["source_manifest"]["path"] == str(
        run.root / "run-manifest.json"
    )
    assert payload["inherit"]["reference_candidate"] == "cand-1"
    assert payload["inherit"]["frozen_inputs"] == {}
    assert "terminal" not in json.loads(run.state.read_text())


def test_utility_scopes_failure_memory_by_case_bucket():
    from search import policy as search_policy

    node_small = {
        "scheme_id": "n-small",
        "mechanism": "double-buffer",
        "case_bucket": "small-shape",
        "expected_gain_range": [0.1, 0.3],
        "cost": 1.0,
        "risk": 0.1,
    }
    node_large = {
        **node_small,
        "scheme_id": "n-large",
        "case_bucket": "large-shape",
    }
    refuted_on_large = {
        "mechanism": "double-buffer",
        "case_bucket": "large-shape",
        "mechanism_status": "refuted",
    }
    small = search_policy.utility(node_small, [refuted_on_large])
    large = search_policy.utility(node_large, [refuted_on_large])
    # A large-shape failure must not poison the same mechanism for small shapes.
    assert small["attempts"] == 0 and small["prior"] == 0.5
    assert large["attempts"] == 1 and large["prior"] == 0.0
    # Unbucketed observations keep the legacy whole-set semantics.
    unscoped = {
        "mechanism": "double-buffer",
        "mechanism_status": "refuted",
    }
    small_unscoped = search_policy.utility(node_small, [unscoped])
    assert small_unscoped["attempts"] == 1 and small_unscoped["prior"] == 0.0


def test_per_case_objective_finish_requires_all_cases_met(tmp_path):
    # Issue #205: an aggregate metric passing (4/11-style) must not be ACHIEVED
    # while the per-case bottom line fails for most cases.
    run = LedgerRun(tmp_path, objective=_objective("per_case"))
    _one_round(run, "cand", [40, 100, 100], "cand-1")
    rejected = run.command(
        "finish",
        "--status",
        "success",
        "--reason-code",
        "completed",
        "--message",
        "geomean target reached",
        expected=2,
    )
    assert "per_case objective not met" in rejected["error"]
    assert "2 of 3" in rejected["error"]
    assert "b[headroom_open]" in rejected["error"]
    report = run.report.read_text()
    assert "逐 case 口径" in report
    # A waiver plus a real improvement discharges every case; finish then passes.
    run.command(
        "case-converge", "--case-id", "b", "--status", "waived", "--reason", "accepted"
    )
    improved = run.performance("improved", [40, 100, 45])
    round_effects = run.effects(
        "round2", run.performance("cand", [40, 100, 100]), improved
    )
    cumulative = run.effects(
        "round2-cumulative", run.performance("original", [100, 100, 100]), improved
    )
    run.complete("round2.complete", (round_effects, cumulative), "cand-2")
    assert run.ledger()["cases"]["c"]["status"] == "optimized"
    done = run.command(
        "finish",
        "--status",
        "success",
        "--reason-code",
        "completed",
        "--message",
        "per-case bottom line met on every case",
    )
    assert done["status"] == "success"


def test_aggregate_and_legacy_objectives_allow_completed_with_disclosure(tmp_path):
    for name, objective in (
        ("aggregate", _objective("aggregate")),
        ("legacy", _objective()),
    ):
        root = tmp_path / name
        root.mkdir(parents=True, exist_ok=True)
        run = LedgerRun(root, objective=objective)
        _one_round(run, "cand", [40, 100, 100], "cand-1")
        done = run.command(
            "finish",
            "--status",
            "success",
            "--reason-code",
            "completed",
            "--message",
            "aggregate objective met",
        )
        assert done["status"] == "success"
        state = json.loads(run.state.read_text())
        # Aggregate/legacy scopes stay allowed but the unresolved cases are
        # still machine-attached to the terminal record for transparency.
        assert state["terminal"]["case_convergence"]["unresolved_count"] == 2


def test_cross_candidate_case_results_cannot_be_stitched_into_success(tmp_path):
    run = LedgerRun(tmp_path, objective=_objective("per_case"))
    _reset_targets(run, (("a", 50.0), ("b", 50.0)))
    _subset_round(run, "round1.complete", "first-a", "a", 40, "cand-1")
    _subset_round(run, "round2.complete", "second-b", "b", 45, "cand-2")

    ledger = run.ledger()
    assert ledger["reference_candidate"] == "cand-2"
    assert ledger["cases"]["a"]["status"] == "pending"
    assert ledger["cases"]["b"]["status"] == "optimized"
    rejected = run.command(
        "finish",
        "--status",
        "success",
        "--reason-code",
        "completed",
        "--message",
        "different candidates must not form a synthetic full pass",
        expected=2,
    )
    assert "a[pending]" in rejected["error"]

    # Partial checkpoints remain composable while the reference identity stays
    # unchanged: round3 supplies the missing case on cand-2 itself.
    _subset_round(run, "round3.complete", "second-a", "a", 40, "cand-2")
    assert run.ledger()["cases"]["a"]["status"] == "optimized"
    done = run.command(
        "finish",
        "--status",
        "success",
        "--reason-code",
        "completed",
        "--message",
        "all cases measured on the current reference",
    )
    assert done["status"] == "success"


def test_targets_are_baseline_owned_nonempty_finite_and_frozen(tmp_path):
    run = LedgerRun(tmp_path, objective=_objective("per_case"))
    override = tmp_path / "override" / "performance-targets.json"
    override.parent.mkdir()
    override.write_text(json.dumps({"cases": []}))
    run.command(
        "mark",
        "--stage",
        "round1.analysis",
        "--status",
        "complete",
        "--artifact",
        override,
    )
    rejected = run.command(
        "finish",
        "--status",
        "success",
        "--reason-code",
        "completed",
        "--message",
        "a later artifact cannot replace the baseline targets",
        expected=2,
    )
    assert "3 of 3" in rejected["error"]

    for rows, message in (
        ((), "non-empty cases list"),
        ((("a", float("nan")),), "finite and positive"),
        ((("a", float("inf")),), "finite and positive"),
    ):
        _reset_targets(run, rows)
        rejected = run.command(
            "finish",
            "--status",
            "success",
            "--reason-code",
            "completed",
            "--message",
            "invalid targets must fail closed",
            expected=2,
        )
        assert message in rejected["error"]


def test_target_coverage_is_checked_against_frozen_collection(tmp_path):
    run = LedgerRun(tmp_path, objective=_objective("per_case"))
    collection = tmp_path / "frozen-performance.csv"
    collection.write_text("case_id,total_us\na,100\n", encoding="utf-8")
    manifest_path = tmp_path / "run-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["collections"]["performance_full"] = {
        "path": str(collection),
        "sha256": hashlib.sha256(collection.read_bytes()).hexdigest(),
    }
    manifest_path.write_text(json.dumps(manifest))
    run.command("sync-manifest")
    rejected = run.command(
        "finish",
        "--status",
        "success",
        "--reason-code",
        "completed",
        "--message",
        "target coverage must match the frozen collection",
        expected=2,
    )
    assert "coverage differs" in rejected["error"]
    assert "extra=" in rejected["error"]


def test_empty_ledger_cannot_pass_verification_gates():
    import case_ledger

    for gate in (
        case_ledger.gate_convergence_finish,
        case_ledger.gate_per_case_objective,
    ):
        try:
            gate({"cases": {}})
        except ValueError as error:
            assert "ledger is empty" in str(error)
        else:
            raise AssertionError(f"{gate.__name__} accepted an empty ledger")


def test_verdict_rejects_nonfinite_or_nonpositive_numbers(tmp_path):
    run = LedgerRun(tmp_path)
    _one_round(run, "candidate", [40, 100, 100], "cand-1")
    verdict = run.verdict("b", "cand-1")
    payload = json.loads(verdict.read_text())
    payload["measured_us"] = float("nan")
    payload["ceiling_us"] = -1
    verdict.write_text(json.dumps(payload))
    rejected = run.command(
        "case-converge",
        "--case-id",
        "b",
        "--status",
        "converged",
        "--verdict",
        verdict,
        expected=2,
    )
    assert "finite positive numeric measured_us" in rejected["error"]
    assert "finite positive numeric ceiling_us" in rejected["error"]


def test_verify_recomputes_ledger_after_performance_invalidation(tmp_path):
    run = LedgerRun(tmp_path)
    _one_round(run, "candidate", [40, 100, 100], "cand-1")
    assert run.ledger()["cases"]["a"]["status"] == "optimized"
    (tmp_path / "candidate.csv").write_text("case_id,total_us\na,1\n")
    run.command("verify", expected=2)
    assert {
        case_id: entry["status"] for case_id, entry in run.ledger()["cases"].items()
    } == {"a": "pending", "b": "pending", "c": "pending"}
    view = run.command("inspect")
    assert view["case_convergence"]["counts"]["pending"] == 3
    assert view["case_convergence"]["counts"]["optimized"] == 0


def _create_request(tmp_path, *extra):
    code = tmp_path / "code"
    code.mkdir(parents=True, exist_ok=True)
    (code / "kernel.cpp").write_text("// k\n", encoding="utf-8")
    cases = tmp_path / "perf.csv"
    cases.write_text("case_id,total_us\n1,100\n", encoding="utf-8")
    request = tmp_path / "req.json"
    result = subprocess.run(
        [
            sys.executable,
            str(PREP),
            "create-request",
            "--request",
            request,
            "--operator-name",
            "dilation2d",
            "--code-dir",
            code,
            "--target-soc",
            "Ascend950",
            "--performance-cases",
            cases,
            "--functional-mode",
            "reuse_performance",
            "--python-executable",
            sys.executable,
            "--cann-env-command",
            "inherit",
            "--optimization-mode",
            "target",
            "--target-metric",
            "case_gpu_npu_ratio",
            "--target-value",
            "0.185",
            "--target-unit",
            "ratio",
            *extra,
        ],
        text=True,
        capture_output=True,
    )
    return request, result


def test_create_request_defaults_to_per_case_scope_and_validates(tmp_path):
    request, result = _create_request(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    objective = json.loads(request.read_text())["optimization_objective"]
    assert objective["scope"] == "per_case"

    explicit, result = _create_request(tmp_path / "x", "--objective-scope", "aggregate")
    assert result.returncode == 0, result.stdout + result.stderr
    assert (
        json.loads(explicit.read_text())["optimization_objective"]["scope"]
        == "aggregate"
    )

    mixed, result = _create_request(
        tmp_path / "y", "--optimization-mode", "fixed_rounds"
    )
    assert result.returncode != 0
    assert (
        "target fields are valid only with --optimization-mode target" in result.stdout
    )
    fixed, result = _create_request(
        tmp_path / "z",
        "--optimization-mode",
        "fixed_rounds",
        "--objective-scope",
        "aggregate",
    )
    assert result.returncode != 0
    assert (
        "target fields are valid only with --optimization-mode target" in result.stdout
    )
