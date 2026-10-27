# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------
"""Tests for multirank_runner.py (Layer 4c multi-rank launcher + ALL-rank-PASS
aggregation), verified via mocked subprocess.Popen (the real HCCL path runs
at cold-start on provisioned hardware). Also covers multirank_rank_verdicts
(fold/entry/unverified shaping) and multirank_emit (verification.json + the
target-aligned performance schema).

Scope notes:
  - no trusted perf receipt / perf_report.md plumbing:
    receipt stubs removed, perf-mode tests assert NO perf_report.md is
    written and no receipt keys appear;
  - the emitted performance block follows the multirank_emit schema:
    aggregate fragment at top level + a source-stamped
    independent_re_measure (perf_irm_provenance gate coverage below);
  - MeasuredResult campaign extras (unverified_world_sizes /
    multirank_case_verdicts) are attached by multirank_runner._measured (the phase_o5
    dataclass does not declare them);
  - the finalize rank-verdicts gate (multirank_finalize_check_rank_verdicts) is a
    follow-up port and does not exist here — the emit test asserts the
    emitted mc2 block shape + plugin detection instead of calling the gate.

multirank_verify is a per-rank thin shell that emits a last-line rank-summary JSON
(classified via multirank_precision_eval_two_tier); multirank_runner parses +
aggregate_all_ranks. The verifier executes in place from the harness tree
(getattr(multirank_runner, "_CANONICAL_VERIFY")) — never staged into the workspace; the
canonical gate self-checks that it imports classify_multirank_case. These tests
mock the rank JSON output.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve()
sys.path.insert(
    0, str(_HERE.parents[2])
)  # .../orchestrator (multirank_runner, phase_o5)
sys.path.insert(
    0, str(_HERE.parents[3])
)  # .../src/scripts (multirank_precision_eval_two_tier)
from plugins.multirank import multirank_runner  # noqa: E402
from plugins.multirank.multirank_rank_verdicts import (
    rank_verdict_entry as _rank_verdict_entry,
)  # noqa: E402
from phase_o5 import MeasuredResult  # noqa: E402


@pytest.fixture(autouse=True)
def _local_campaign(monkeypatch):
    """Force the LOCAL Popen path for every test here (hermetic): the live
    .ascendc_env (when present on this box) must not flip a test campaign
    into remote staging. Remote-path behavior has its own tests (they
    restore the original via _ORIG_RESOLVE_REMOTE)."""
    monkeypatch.setattr(multirank_runner, "_resolve_remote", lambda op: None)


_ORIG_RESOLVE_REMOTE = getattr(multirank_runner, "_resolve_remote")


def _rank_json(rank, status="PASS", tier1_pass=2, total=2, perf=None):
    d = {
        "rank": rank,
        "status": status,
        "tier1_pass": tier1_pass,
        "tier1_pass_inclusive": tier1_pass,
        "total": total,
        "tier2_status": "N/A_ALL_T1" if status == "PASS" else "FAIL",
    }
    if perf is not None:
        d["perf"] = perf
    return d


def _fake_popen(seq):
    """seq: list of (exitcode, rank_json_or_None). Returns a Popen replacement
    that writes the rank's last-line JSON to the stdout handle multirank_runner passes
    (mirrors a real multirank_verify.py emitting its rank summary), then returns the
    exit code on wait()."""
    it = iter(seq)

    def _popen(*args, **kw):
        exitcode, rank_json = next(it)
        stdout = kw.get("stdout")

        class _P:
            @staticmethod
            def wait(timeout=None):
                if stdout is not None:
                    stdout.write("opType=MatmulAllreduce DumpHead: AIV-0\n")
                    if rank_json is not None:
                        stdout.write(json.dumps(rank_json) + "\n")
                    stdout.flush()
                return exitcode

            def kill(self):
                pass

        return _P()

    return _popen


def _make_ws(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir(parents=True, exist_ok=True)
    return ws


def _wire_rank_env(monkeypatch, tmp_path, popen=None, rank_timeout=None) -> Path:
    """Wire the fake rank-launch env (Popen source + fixed port, optional fast
    rank timeout) and return a [2]-golden workspace."""
    if popen is not None:
        monkeypatch.setattr(multirank_runner.subprocess, "Popen", popen)
    monkeypatch.setattr(multirank_runner, "_free_port", lambda: 29500)
    if rank_timeout is not None:
        monkeypatch.setattr(multirank_runner, "_MULTIRANK_RANK_TIMEOUT", rank_timeout)
        monkeypatch.delenv("MULTIRANK_RANK_TIMEOUT", raising=False)
    ws = _make_ws(tmp_path)
    _provision_fake_golden(ws, [2])
    return ws


def _wire_probe_recorders(monkeypatch) -> tuple:
    """Record pick_idle/confirm_idle calls (auto-alloc observation);
    returns (picks, confirms)."""
    import npu_probe

    picks: list[int] = []
    confirms: list[list[int]] = []
    monkeypatch.setattr(
        npu_probe,
        "pick_idle",
        lambda env, n: (picks.append(n), (list(range(10, 10 + n)), None))[1],
    )
    monkeypatch.setattr(
        npu_probe,
        "confirm_idle",
        lambda env, lanes: confirms.append(list(lanes)) and None,
    )
    return picks, confirms


def _ws_two_case_specs(tmp_path: Path) -> Path:
    """A [2]-spec workspace provisioned with two ws=2 golden cases."""
    ws = _make_ws(tmp_path)
    _write_spec(ws, [2])
    _provision_fake_golden(ws, [("case0@ws2[randn]", 2), ("case1@ws2[randn]", 2)])
    return ws


def _perf_payload(
    candidate_us: float = 100.0,
    baseline_us: float | None = 200.0,
    ratio: float | None = 2.0,
    with_profile_dirs: bool = True,
) -> dict:
    """A rank-reported perf fragment: top-level aggregate + one case entry."""
    perf: dict = {
        "candidate_us": candidate_us,
        "baseline_us": baseline_us,
        "ratio": ratio,
        "cases": [
            {
                "case_id": "case0@ws2[randn]",
                "candidate_us": candidate_us,
                "baseline_us": baseline_us,
                "ratio": ratio,
            }
        ],
    }
    if with_profile_dirs:
        perf["profile_dirs"] = []
    return perf


def _pass_a_view(overall: dict) -> dict:
    """The flat pass_a view the tests hand-build from an aggregate result."""
    return {
        "status": overall["status"],
        "tier1_pass": overall["tier1_pass"],
        "tier1_pass_inclusive": overall["tier1_pass_inclusive"],
        "total": overall["total"],
        "tier2_status": overall["tier2_status"],
        "method": overall["method"],
    }


def test_device_mask_joins_lanes():
    assert getattr(multirank_runner, "_device_mask")([0]) == "0"
    assert getattr(multirank_runner, "_device_mask")([1, 2, 4, 8]) == "1,2,4,8"


def test_run_empty_lanes_error():
    res = multirank_runner.run(
        multirank_runner.CampaignContext(workspace=Path("/tmp/ws"), op="op"), []
    )
    assert res.runner_error is not None
    assert "empty lanes" in res.runner_error


def test_run_1rank_uses_multiprocess_not_ssh(monkeypatch, tmp_path):
    """world_size==1 uses the multirank_verify.py multi-process path (never ssh_runner)

    — multirank ops don't produce pass_a/b_runner.py that ssh_runner expects.
    """
    ws = _make_ws(tmp_path)
    _provision_fake_golden(ws, [1])
    ssh_called = []
    monkeypatch.setattr(
        multirank_runner.phase_o5_runner,
        "ssh_runner",
        lambda *a, **k: (
            ssh_called.append(1) or MeasuredResult(pass_a={"tier1_pass": 5, "total": 5})
        ),
    )
    monkeypatch.setattr(
        multirank_runner.subprocess, "Popen", _fake_popen([(0, _rank_json(0))])
    )
    res = multirank_runner.run(
        multirank_runner.CampaignContext(workspace=ws, op="op"), [2]
    )
    assert not ssh_called  # ws=1 does NOT delegate to ssh_runner
    assert res.runner_error is None


def test_run_verify_missing(tmp_path, monkeypatch):
    ws = _make_ws(tmp_path)
    _provision_fake_golden(ws, [2])
    monkeypatch.setattr(
        multirank_runner, "_CANONICAL_VERIFY", tmp_path / "no_such_verify.py"
    )
    res = multirank_runner.run(
        multirank_runner.CampaignContext(workspace=ws, op="op"), [0, 1]
    )
    assert res.runner_error and "canonical verifier missing" in res.runner_error


def test_canonical_gate_blocks_non_canonical_verify(tmp_path, monkeypatch):
    """Canonical verifier without classify_multirank_case import -> gate refuses."""
    stub = tmp_path / "multirank_verify.py"
    stub.write_text("# stub verifier\n")
    ws = _make_ws(tmp_path)
    _provision_fake_golden(ws, [2])
    monkeypatch.setattr(multirank_runner, "_CANONICAL_VERIFY", stub)
    res = multirank_runner.run(
        multirank_runner.CampaignContext(workspace=ws, op="op"), [0, 1]
    )
    assert res.runner_error and "canonical gate" in res.runner_error


def test_canonical_verify_points_at_harness_tree():
    """The canonical verifier is the harness-tree reference_provider copy —

    never a staged workspace file (tamper vector removed by construction).
    """
    p = getattr(multirank_runner, "_CANONICAL_VERIFY")
    assert p.name == "multirank_verify.py"
    assert p.parent.name == "reference_provider"
    assert p.is_file()  # exists in this checkout


def test_parse_rank_summary():
    log = "kernel log\nCANN Version\n" + json.dumps(_rank_json(0))
    rs = getattr(multirank_runner, "_parse_rank_summary")(log)
    assert rs["rank"] == 0 and rs["tier1_pass"] == 2
    assert getattr(multirank_runner, "_parse_rank_summary")("no JSON here\n") is None


def test_activate_opp_env_finds_install(tmp_path):
    op_dir = tmp_path / "op"
    (
        op_dir / ".install" / "packages" / "vendors" / "customize" / "op_api" / "lib"
    ).mkdir(parents=True)
    env = getattr(multirank_runner, "_activate_opp_env")({}, op_dir, "op")
    assert "ASCEND_CUSTOM_OPP_PATH" in env
    assert env["ASCEND_CUSTOM_OPP_PATH"].endswith(".install/packages/vendors/customize")
    assert "op_api/lib" in env["LD_LIBRARY_PATH"]
    assert "multirank" in env["PYTHONPATH"]


def test_activate_opp_env_prefers_mandated_nest(tmp_path):
    """multirank NEST layout (mandated): prj-<op>/.install wins over legacy

    single-layer workspace/.install (keep-in-sync with multirank_build._opp_path).
    """
    ws = tmp_path
    for base in (ws / "prj-op", ws):
        (
            base / ".install" / "packages" / "vendors" / "customize" / "op_api" / "lib"
        ).mkdir(parents=True)
    env = getattr(multirank_runner, "_activate_opp_env")({}, ws, "op")
    assert "prj-op" in env["ASCEND_CUSTOM_OPP_PATH"]


def test_run_all_ranks_pass(tmp_path, monkeypatch):
    """world_size=2, both emit PASS rank JSON + exit 0 -> pass_a PASS (aggregated)."""
    ws = _make_ws(tmp_path)
    _provision_fake_golden(ws, [2])
    seq = [(0, _rank_json(0)), (0, _rank_json(1))]
    monkeypatch.setattr(multirank_runner.subprocess, "Popen", _fake_popen(seq))
    monkeypatch.setattr(multirank_runner, "_free_port", lambda: 29500)
    res = multirank_runner.run(
        multirank_runner.CampaignContext(workspace=ws, op="op"), [0, 1]
    )
    assert res.runner_error is None
    assert res.pass_a["status"] == "PASS"
    assert res.pass_a["tier1_pass"] == 4  # 2 ranks x 2 cases
    assert res.pass_a["tier2_pass"] == 0  # carried: schema-gate required field
    assert res.determinism["n_identical_cases"] == 2


def test_emit_carries_forward_worker_pass_a_fields(tmp_path):
    """An O5 rewrite refreshes the measured numbers but must NOT erase

    fields the worker maintains on the existing artifact: pass_a.tier2_pass
    (verification-schema required) and any worker-authored precision keys
    survive; measured counts take the fresh values.
    """
    from multirank_precision_eval_two_tier import aggregate_all_ranks

    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "verification.json").write_text(
        json.dumps(
            {
                "build_evidence": "keep",
                "precision": {
                    "status": "PARTIAL",
                    "evidence_note": "kw-maintained precision note",
                    "pass_a": {
                        "status": "PARTIAL",
                        "tier1_pass": 3,
                        "total": 4,
                        "tier2_pass": 1,
                    },
                },
            }
        )
    )

    rank_summaries = [_rank_json(0), _rank_json(1)]
    overall = aggregate_all_ranks(rank_summaries)
    pass_a = _pass_a_view(overall)
    pass_a["tier2_pass"] = overall["tier2_pass"]
    payload = multirank_runner.VerificationPayload(
        overall=overall,
        pass_a=pass_a,
        rank_summaries=rank_summaries,
    )
    getattr(multirank_runner, "_emit_verification_json")(ws, payload)

    vj = json.loads((ws / "verification.json").read_text())
    assert vj["build_evidence"] == "keep"
    prec = vj["precision"]
    assert prec["evidence_note"] == "kw-maintained precision note"  # carried
    pa = prec["pass_a"]
    assert pa["status"] == "PASS" and pa["tier1_pass"] == 4  # fresh measured
    assert pa["tier2_pass"] == overall["tier2_pass"]  # present, fresh
    assert pa["total"] == 4


def test_det_policy_satisfied_truth_table():
    """determinism.md modulation: n_a / best_effort monitor-only (always

    satisfied); required gates on the observed value.
    """
    assert getattr(multirank_runner, "_det_policy_satisfied")("n_a", False) is True
    assert (
        getattr(multirank_runner, "_det_policy_satisfied")("best_effort", False) is True
    )
    assert (
        getattr(multirank_runner, "_det_policy_satisfied")("required", False) is False
    )
    assert getattr(multirank_runner, "_det_policy_satisfied")("required", True) is True


def test_run_det_policy_from_state_file(tmp_path, monkeypatch):
    """det_policy is read from .opgen_state.json (O1.5 classification), and the

    emitted determinism dict carries the policy-modulated satisfied value.
    """
    ws = _make_ws(tmp_path)
    _provision_fake_golden(ws, [2])
    (ws / ".opgen_state.json").write_text(json.dumps({"det_policy": "best_effort"}))
    seq = [(0, _rank_json(0)), (0, _rank_json(1))]
    monkeypatch.setattr(multirank_runner.subprocess, "Popen", _fake_popen(seq))
    monkeypatch.setattr(multirank_runner, "_free_port", lambda: 29500)
    res = multirank_runner.run(
        multirank_runner.CampaignContext(workspace=ws, op="op"), [0, 1]
    )
    assert res.runner_error is None
    assert res.determinism["policy"] == "best_effort"
    assert res.determinism["observed_deterministic"] is True
    assert res.determinism["policy_satisfied"] is True
    vj = json.loads((ws / "verification.json").read_text())
    assert vj["determinism"]["policy"] == "best_effort"
    assert vj["determinism"]["policy_satisfied"] is True


def _write_spec(ws: Path, world_sizes: list[int]) -> None:
    """Seed a minimal spec.py carrying only the per-case world_sizes — the
    single source _golden_world_sizes reads (not ref_runnable.json)."""
    cases = "[" + ", ".join(f"{{'world_size': {w}}}" for w in world_sizes) + "]"
    (ws / "spec.py").write_text(f"SPEC = {{'cases': {cases}}}\n")


def _provision_fake_golden(ws: Path, cases: list) -> None:
    """Seed a fake golden/ tree (manifest + stub per-case files) so the
    runner's campaign enumeration finds the given cases. Entries are either
    bare world_sizes (one synthetic `case{i}@ws{N}[randn]` each) or
    (name, world_size) pairs. The stub .pt files are never loaded — the
    verifier subprocess is mocked."""
    import multirank_phase_o25

    g = ws / "golden"
    g.mkdir(parents=True, exist_ok=True)
    entries = []
    for i, c in enumerate(cases):
        name, w = (f"case{i}@ws{c}[randn]", c) if isinstance(c, int) else c
        slug = multirank_phase_o25.case_slug(name)
        (g / f"{slug}.pt").write_bytes(b"stub")
        entries.append(
            {
                "idx": i + 1,
                "name": name,
                "case": i,
                "world_size": w,
                "profile": "randn",
                "file": f"{slug}.pt",
            }
        )
    (g / "manifest.json").write_text(
        json.dumps(
            {
                "op": "op",
                "world_sizes": sorted({e["world_size"] for e in entries}),
                "n_cases": len(entries),
                "cases": entries,
            }
        )
    )


def test_run_rejects_undeclared_world_size(tmp_path):
    """len(lanes) must match a declared case world_size — physical lanes select

    which cards execute a declared group; they cannot create a new one.
    """
    ws = _make_ws(tmp_path)
    _write_spec(ws, [2])
    res = multirank_runner.run(
        multirank_runner.CampaignContext(workspace=ws, op="op"), [0, 1, 2]
    )
    assert res.runner_error and "no declared case world_size" in res.runner_error


def test_measured_result_carries_campaign_extras_always(tmp_path):
    """This tree's phase_o5.MeasuredResult does not declare the multirank campaign

    extras; multirank_runner._measured attaches them on EVERY path ({} / None
    defaults) so the multirank plugin contract never hits AttributeError.
    """
    res = multirank_runner.run(
        multirank_runner.CampaignContext(workspace=Path("/tmp/ws"), op="op"), []
    )
    assert isinstance(res, MeasuredResult)
    assert res.unverified_world_sizes == {}
    assert res.multirank_case_verdicts is None


def test_run_all_groups_partial_coverage_is_loud(tmp_path, monkeypatch):
    """Feasible groups RUN (their verdicts are computed), but skipped declared

    groups are reported as UNVERIFIED in runner_error — declared cases never
    silently drop out of the campaign.
    """
    ws = _make_ws(tmp_path)
    _write_spec(ws, [2, 4])
    _provision_fake_golden(ws, [2, 4])
    seq = [(0, _rank_json(0)), (0, _rank_json(1))]  # only the ws=2 group runs
    monkeypatch.setattr(multirank_runner.subprocess, "Popen", _fake_popen(seq))
    monkeypatch.setattr(multirank_runner, "_free_port", lambda: 29500)
    res = multirank_runner.run_all_groups(
        multirank_runner.CampaignContext(workspace=ws, op="op"), [0, 1]
    )
    assert res.runner_error and "PARTIAL" in res.runner_error
    assert "[4]" in res.runner_error or "4" in res.runner_error
    # no verification.json emit on partial coverage (gate must not see a
    # falsely-complete PASS)
    assert not (ws / "verification.json").exists()


def test_run_all_groups_merges_multi_ws(tmp_path, monkeypatch):
    """Full coverage: every declared group's cases launch (lanes[:ws] per

    case), verdicts merge into one verification.json with per-group folded
    rank verdicts (exactly ws entries per group, each carrying its covered
    case names).
    """
    ws = _make_ws(tmp_path)
    _write_spec(ws, [2, 4])
    _provision_fake_golden(ws, [2, 4])
    seq = (
        [(0, _rank_json(0)), (0, _rank_json(1))]  # ws=2 group
        + [(0, _rank_json(r)) for r in range(4)]
    )  # ws=4 group
    monkeypatch.setattr(multirank_runner.subprocess, "Popen", _fake_popen(seq))
    monkeypatch.setattr(multirank_runner, "_free_port", lambda: 29500)
    res = multirank_runner.run_all_groups(
        multirank_runner.CampaignContext(workspace=ws, op="op"), [0, 1, 2, 3]
    )
    assert res.runner_error is None
    assert res.pass_a["status"] == "PASS"
    vj = json.loads((ws / "verification.json").read_text())
    assert vj["multirank"]["world_sizes"] == [2, 4]
    assert len(vj["multirank"]["rank_verdicts"]["2"]) == 2
    assert len(vj["multirank"]["rank_verdicts"]["4"]) == 4
    # coverage evidence: the declared case list + per-entry covered cases
    assert {c["name"] for c in vj["multirank"]["cases"]} == {
        "case0@ws2[randn]",
        "case1@ws4[randn]",
    }
    assert vj["multirank"]["rank_verdicts"]["2"][0]["cases"] == ["case0@ws2[randn]"]
    assert vj["multirank"]["rank_verdicts"]["4"][0]["cases"] == ["case1@ws4[randn]"]


def test_run_one_rank_fails(tmp_path, monkeypatch):
    """One rank's verdict FAIL (but BOTH summaries parsed cleanly) -> MEASURED

    result with aggregate FAIL counts, NOT runner_error.
    Verdict-vs-execution contract (matmul_allreduce P0aba.O5
    reconciliation): a rank with failing cases still prints its classified
    summary (exit 1) — that is a completed measurement, returned so phase_o5
    reconciles counts against the worker's claim (same as ssh_runner's
    FAIL-count path for benchmark/port_a3). runner_error is reserved for
    global could-not-execute refusals (empty lanes / missing verifier).
    """
    seq = [(0, _rank_json(0)), (1, _rank_json(1, status="FAIL", tier1_pass=1))]
    monkeypatch.setattr(multirank_runner.subprocess, "Popen", _fake_popen(seq))
    monkeypatch.setattr(multirank_runner, "_free_port", lambda: 29500)
    ws = _make_ws(tmp_path)
    _provision_fake_golden(ws, [2])
    res = multirank_runner.run(
        multirank_runner.CampaignContext(workspace=ws, op="op"), [0, 1]
    )
    assert res.runner_error is None
    assert res.pass_a["status"] == "FAIL"
    assert res.pass_a["tier1_pass"] == 3  # rank0: 2/2 + rank1: 1/2
    assert res.pass_a["total"] == 4
    assert res.determinism is not None
    # no verification.json emit on measured-FAIL — emit is the ALL-rank-PASS
    # GAP-1 contract; a FAIL measurement must not overwrite the worker's
    # claimed artifact (PARTIAL status + Tier-2 evidence).
    assert not (ws / "verification.json").exists()


def test_run_all_groups_mixed_verdict_returns_measured(tmp_path, monkeypatch):
    """ws=1 group all-PASS + ws=2 group one-rank-FAIL -> merged MEASURED

    result (status=FAIL, counts summed across groups), no runner_error, no
    verification.json emit (GAP-1 emit stays ALL-rank-PASS-only).
    """
    ws = _make_ws(tmp_path)
    _write_spec(ws, [1, 2])
    _provision_fake_golden(ws, [1, 2])
    seq = (
        [(0, _rank_json(0))]  # ws=1 group, rank 0 PASS
        + [(0, _rank_json(0)), (1, _rank_json(1, status="FAIL", tier1_pass=1))]
    )
    monkeypatch.setattr(multirank_runner.subprocess, "Popen", _fake_popen(seq))
    monkeypatch.setattr(multirank_runner, "_free_port", lambda: 29500)
    res = multirank_runner.run_all_groups(
        multirank_runner.CampaignContext(workspace=ws, op="op"), [0, 1]
    )
    assert res.runner_error is None
    assert res.pass_a["status"] == "FAIL"
    assert res.pass_a["tier1_pass"] == 2 + 2 + 1  # ws=1: 2/2, ws=2: 2/2 + 1/2
    assert res.pass_a["total"] == 6
    assert not (ws / "verification.json").exists()


def test_run_unparsable_rank_log(tmp_path, monkeypatch):
    """A rank whose log has no JSON (hard crash) -> synthetic ERROR entry; the

    campaign STAYS a completed measurement (the co-rank keeps its real
    verdict) — never a whole-campaign runner_error.
    """
    ws = _make_ws(tmp_path)
    _provision_fake_golden(ws, [2])
    seq = [(0, _rank_json(0)), (1, None)]  # rank 1 crashed, emitted no JSON
    monkeypatch.setattr(multirank_runner.subprocess, "Popen", _fake_popen(seq))
    monkeypatch.setattr(multirank_runner, "_free_port", lambda: 29500)
    res = multirank_runner.run(
        multirank_runner.CampaignContext(workspace=ws, op="op"), [0, 1]
    )
    assert res.runner_error is None
    assert res.pass_a["status"] == "FAIL"
    assert res.pass_a["tier1_pass"] == 2  # rank0's real verdicts only
    cv = res.multirank_case_verdicts["case0@ws2[randn]"]
    assert cv["ranks"] == {"0": "PASS", "1": "ERROR"}


def test_run_per_rank_timeout(tmp_path, monkeypatch, caplog):
    import logging

    caplog.set_level(logging.INFO)
    """Both ranks exceed the host-side fallback timeout -> SIGKILL + synthetic

    ERROR entries; the campaign is a measured FAIL (the timeout is classified
    in each ERROR's `error` field; device-side rc=2 hang is the other class).
    """
    import subprocess as sp

    class _Hanging:
        @staticmethod
        def wait(timeout=None):
            raise sp.TimeoutExpired(cmd="x", timeout=timeout)

        def kill(self):
            pass

    monkeypatch.setattr(
        multirank_runner.subprocess, "Popen", lambda *a, **kw: _Hanging()
    )
    ws = _wire_rank_env(monkeypatch, tmp_path, rank_timeout=1)
    res = multirank_runner.run(
        multirank_runner.CampaignContext(workspace=ws, op="op"), [0, 1]
    )
    assert res.runner_error is None
    assert res.pass_a["status"] == "FAIL"
    assert res.pass_a["tier1_pass"] == 0 and res.pass_a["total"] == 2
    cv = res.multirank_case_verdicts["case0@ws2[randn]"]
    assert cv["ranks"] == {"0": "ERROR", "1": "ERROR"}
    out = caplog.text
    # host-side fallback still surfaced distinctly in the launch detail
    assert "rank_timed_out=[0, 1]" in out
    assert "timed out after 1s" in out
    assert "SIGKILL" in out


def test_run_device_hang_rc2(tmp_path, monkeypatch, caplog):
    import logging

    caplog.set_level(logging.INFO)
    """rc==2 (multirank_verify _LaunchWatchdog os._exit(2)) → synthetic ERROR with

    the device-hang classification — measured per case, not a campaign abort;
    distinct from the host-side timeout fallback and from precision fail.
    """

    class _DeviceHang:
        @staticmethod
        def wait(timeout=None):
            return 2  # rc=2 = device hang

        def kill(self):
            pass

    monkeypatch.setattr(
        multirank_runner.subprocess, "Popen", lambda *a, **kw: _DeviceHang()
    )
    ws = _wire_rank_env(monkeypatch, tmp_path, rank_timeout=1)
    res = multirank_runner.run(
        multirank_runner.CampaignContext(workspace=ws, op="op"), [0, 1]
    )
    assert res.runner_error is None
    assert res.pass_a["status"] == "FAIL"
    cv = res.multirank_case_verdicts["case0@ws2[randn]"]
    assert set(cv["ranks"].values()) == {"ERROR"}
    out = caplog.text
    assert "rank_device_hang=[0, 1]" in out
    assert "device-side hang" in out


def test_rank_timeout_env_override(monkeypatch):
    """MULTIRANK_RANK_TIMEOUT env overrides the default at call time (honored by BOTH

    the FSM run_phase_gate path and run.py verify). Invalid values fall back.
    """
    monkeypatch.delenv("MULTIRANK_RANK_TIMEOUT", raising=False)
    assert getattr(multirank_runner, "_rank_timeout")() == getattr(
        multirank_runner, "_MULTIRANK_RANK_TIMEOUT"
    )
    monkeypatch.setenv("MULTIRANK_RANK_TIMEOUT", "42")
    assert getattr(multirank_runner, "_rank_timeout")() == 42
    monkeypatch.setenv("MULTIRANK_RANK_TIMEOUT", "garbage")
    assert getattr(multirank_runner, "_rank_timeout")() == getattr(
        multirank_runner, "_MULTIRANK_RANK_TIMEOUT"
    )


# ---------------------------------------------------------------------------
# post_verify_for_finalize × multirank_runner collaboration (routing target)
# ---------------------------------------------------------------------------
def _mc2_ws(tmp_path):
    ws = tmp_path / "mc2_op"
    ws.mkdir()
    (ws / ".opgen_state.json").write_text(
        json.dumps({"opgen_mode": "port_a3_to_a5", "multirank": True})
    )
    (ws / "verification.json").write_text(
        json.dumps(
            {
                "precision": {
                    "status": "PASS",
                    "pass_a": {"status": "PASS", "tier1_pass": 2, "total": 2},
                },
                "mc2": {
                    "world_size": 2,
                    "ranks": [
                        {"rank": 0, "status": "PASS"},
                        {"rank": 1, "status": "PASS"},
                    ],
                },
            }
        )
    )
    return ws


def test_post_verify_multirank_runner_error_blocks_finalize(tmp_path, monkeypatch):
    """A rank FAIL -> multirank_runner runner_error -> post_verify RUNNER_FAILED."""
    from phase_o5 import post_verify_for_finalize

    ws = _mc2_ws(tmp_path)
    monkeypatch.setattr(
        multirank_runner,
        "run",
        lambda ctx, lanes: MeasuredResult(runner_error="rank 1 verify exit 1"),
    )

    def runner(_ws, _op, _ln):
        return multirank_runner.run(
            multirank_runner.CampaignContext(workspace=_ws, op=_op), [0, 1]
        )

    rep = post_verify_for_finalize(ws, "op", runner=runner)
    assert rep.verdict == "RUNNER_FAILED"
    assert "rank 1" in rep.summary


def test_post_multirank_verify_all_pass_verifies(tmp_path, monkeypatch):
    """All ranks PASS -> multirank_runner pass_a PASS -> post_verify VERIFIED."""
    from phase_o5 import post_verify_for_finalize

    ws = _mc2_ws(tmp_path)
    monkeypatch.setattr(
        multirank_runner,
        "run",
        lambda ctx, lanes: MeasuredResult(
            pass_a={"status": "PASS", "tier1_pass": 2, "total": 2},
            determinism={"n_identical_cases": 2, "n_cases_checked": 2},
        ),
    )

    def runner(_ws, _op, _ln):
        return multirank_runner.run(
            multirank_runner.CampaignContext(workspace=_ws, op=_op), [0, 1]
        )

    rep = post_verify_for_finalize(ws, "op", runner=runner)
    assert rep.verdict == "VERIFIED"
    assert not rep.mismatches


def _mc2_ws_partial(tmp_path, tier1_pass=25, total=35):
    """Workspace claiming an honest PARTIAL (25/35) — the matmul_allreduce
    requirement-class shape (10 cancellation-domain cells unpassable under
    the native_output=None strict carve-out, probe-verified)."""
    ws = tmp_path / "mc2_op"
    ws.mkdir()
    (ws / ".opgen_state.json").write_text(
        json.dumps({"opgen_mode": "port_a3_to_a5", "multirank": True})
    )
    (ws / "verification.json").write_text(
        json.dumps(
            {
                "precision": {
                    "status": "PARTIAL",
                    "pass_a": {
                        "status": "PARTIAL",
                        "tier1_pass": tier1_pass,
                        "total": total,
                    },
                },
                "mc2": {
                    "world_sizes": [1, 2],
                    "rank_verdicts": {
                        "1": [{"rank": 0, "status": "PASS"}],
                        "2": [
                            {"rank": 0, "status": "FAIL"},
                            {"rank": 1, "status": "FAIL"},
                        ],
                    },
                },
            }
        )
    )
    return ws


def test_post_multirank_verify_measured_fail_reconciles_partial_claim(
    tmp_path, monkeypatch
):
    """measured-FAIL (25/35, the runner's measured-FAIL path) vs claimed

    PARTIAL 25/35 -> VERIFIED. A measured FAIL status IS a grading; count
    reconciliation compares exact fields for status=PARTIAL.
    """
    from phase_o5 import post_verify_for_finalize

    ws = _mc2_ws_partial(tmp_path)
    monkeypatch.setattr(
        multirank_runner,
        "run_all_groups",
        lambda ctx, lanes: MeasuredResult(
            pass_a={"status": "FAIL", "tier1_pass": 25, "total": 35},
            determinism={"n_identical_cases": 0, "n_cases_checked": 2},
        ),
    )

    def runner(_ws, _op, _ln):
        return multirank_runner.run_all_groups(
            multirank_runner.CampaignContext(workspace=_ws, op=_op), [0, 1]
        )

    rep = post_verify_for_finalize(ws, "op", runner=runner)
    assert rep.verdict == "VERIFIED"
    assert not rep.mismatches


def test_post_multirank_verify_measured_fail_exposes_overclaim(tmp_path, monkeypatch):
    """measured-FAIL (25/35) vs claimed PASS 35/35 -> MISMATCH. The count

    reconciliation remains the anti-fraud anchor: a worker cannot launder a
    requirement-class FAIL into PASS by hand-claiming full counts.
    """
    from phase_o5 import post_verify_for_finalize

    ws = _mc2_ws(tmp_path)  # claims PASS 2/2; measured below is 1/2
    monkeypatch.setattr(
        multirank_runner,
        "run",
        lambda ctx, lanes: MeasuredResult(
            pass_a={"status": "FAIL", "tier1_pass": 1, "total": 2},
            determinism={"n_identical_cases": 0, "n_cases_checked": 2},
        ),
    )

    def runner(_ws, _op, _ln):
        return multirank_runner.run(
            multirank_runner.CampaignContext(workspace=_ws, op=_op), [0, 1]
        )

    rep = post_verify_for_finalize(ws, "op", runner=runner)
    assert rep.verdict == "MISMATCH"
    assert any("tier1_pass" in m for m in rep.mismatches)


def test_emit_verification_json_aggregates_mc2_verdict(tmp_path):
    """_emit_verification_json writes the verification.json finalize gates

    require: precision (status + pass_a + pass_b=N/A) + performance=N/A +
    mc2 rank-verdict block. Read-merge preserves worker-authored keys. GAP-1 fix.
    The finalize rank-verdicts gate module (multirank_finalize_check_rank_verdicts)
    is a follow-up port — this asserts the emitted mc2 block shape + plugin
    detection instead of calling the gate.
    """
    from multirank_precision_eval_two_tier import aggregate_all_ranks
    from plugins import detect_plugin

    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "verification.json").write_text(json.dumps({"build_evidence": "keep"}))
    (ws / ".opgen_state.json").write_text(
        json.dumps({"opgen_mode": "port_a3_to_a5", "multirank": True})
    )

    rank_summaries = [_rank_json(0), _rank_json(1)]
    overall = aggregate_all_ranks(rank_summaries)
    pass_a = _pass_a_view(overall)

    payload = multirank_runner.VerificationPayload(
        overall=overall,
        pass_a=pass_a,
        rank_summaries=rank_summaries,
    )
    getattr(multirank_runner, "_emit_verification_json")(ws, payload)

    vj = json.loads((ws / "verification.json").read_text())
    # worker key preserved by read-merge
    assert vj["build_evidence"] == "keep"
    # precision
    assert vj["precision"]["status"] == "PASS"
    assert vj["precision"]["pass_a"] == pass_a
    assert vj["precision"]["pass_b"]["status"] == "N/A"
    assert vj["precision"]["pass_b"]["reason"].strip()
    # performance (N/A with reason — gate rejects silent None)
    assert vj["performance"]["status"] == "N/A"
    assert vj["performance"]["reason"].strip()
    # mc2 rank-verdict block (schema: world_size groups per declared case ws)
    mr_block = vj["multirank"]
    assert mr_block["world_sizes"] == [2]
    assert (mr_block["world_sizes"][0] & (mr_block["world_sizes"][0] - 1)) == 0
    assert len(mr_block["rank_verdicts"]["2"]) == 2
    assert all(r["status"] == "PASS" for r in mr_block["rank_verdicts"]["2"])
    # truth tier stamped (which golden provider produced the compared truth)
    assert mr_block["truth_tier"] == "npubench"

    # the workspace resolves to port_a3 (multirank flag on) — the gate's scope
    from plugins.port_a3 import get_plugin_instance as _pa3

    plug = detect_plugin(ws)
    assert plug is not None and plug.name == "port_a3_to_a5"
    assert _pa3().is_multirank_workspace(ws) is True


# ---------------------------------------------------------------------------
# perf pathway (--perf mode: multirank_verify emits per-rank perf -> multirank_runner
# aggregates median ratio -> verification.json.performance)
# ---------------------------------------------------------------------------
def test_aggregate_perf_none_when_precision_only():
    """No rank carried perf (precision-only run) -> None."""
    rs = [_rank_json(0), _rank_json(1)]
    assert getattr(multirank_runner, "_aggregate_perf")(rs) is None


def test_aggregate_perf_median_ratio():
    """Two-level aggregation: per-case mean across ranks, then median across

    cases; per-side times stay evidence-only (median).
    """
    rs = [
        _rank_json(
            0,
            perf={
                "candidate_us": 100.0,
                "baseline_us": 200.0,
                "ratio": 2.0,
                "cases": [
                    {
                        "case_id": "case0@ws2[randn]",
                        "candidate_us": 100.0,
                        "baseline_us": 200.0,
                        "ratio": 2.0,
                    }
                ],
            },
        ),
        _rank_json(
            1,
            perf={
                "candidate_us": 110.0,
                "baseline_us": 220.0,
                "ratio": 2.0,
                "cases": [
                    {
                        "case_id": "case0@ws2[randn]",
                        "candidate_us": 110.0,
                        "baseline_us": 220.0,
                        "ratio": 2.0,
                    }
                ],
            },
        ),
    ]
    agg = getattr(multirank_runner, "_aggregate_perf")(rs)
    assert agg is not None and agg["ran"] is True
    assert agg["candidate_us"] == 105.0  # median(100, 110)
    assert agg["baseline_us"] == 210.0  # median(200, 220)
    assert agg["ratio"] == 2.0  # median of per-case means
    st = agg["case_stats"]["case0@ws2[randn]"]
    assert st["candidate_us_mean"] == 105.0  # mean across the case's ranks
    assert st["candidate_us_std"] == 7.071  # sample stdev(100, 110)
    assert st["ratio"] == 2.0


def test_aggregate_perf_no_baseline_ratio_none():
    """perf with candidate but no baseline (perf_baseline absent) -> ratio None."""
    rs = [
        _rank_json(
            0,
            perf={
                "candidate_us": 100.0,
                "baseline_us": None,
                "ratio": None,
                "cases": [
                    {
                        "case_id": "case0@ws1[randn]",
                        "candidate_us": 100.0,
                        "baseline_us": None,
                        "ratio": None,
                    }
                ],
            },
        )
    ]
    agg = getattr(multirank_runner, "_aggregate_perf")(rs)
    assert agg is not None
    assert agg["candidate_us"] == 100.0
    assert agg["ratio"] is None  # no baseline -> no ratio


def test_aggregate_perf_two_level_case_equal_vote(tmp_path):
    """A flipped tiny case (rank ratios 0.2 / 7.4) gets ONE case-level vote

    (mean) and cannot drag the campaign median away from the consistent
    majority; the case-level std records the rank imbalance.
    """

    def _perf(cand, base, case_id):
        return {
            "candidate_us": cand,
            "baseline_us": base,
            "ratio": round(base / cand, 3),
            "cases": [
                {
                    "case_id": case_id,
                    "candidate_us": cand,
                    "baseline_us": base,
                    "ratio": round(base / cand, 3),
                }
            ],
        }

    rs = [
        _rank_json(0, perf=_perf(25.0, 180.0, "case0@ws2[randn]")),  # flip
        _rank_json(1, perf=_perf(115.0, 23.0, "case0@ws2[randn]")),  # mirror
        _rank_json(0, perf=_perf(350.0, 280.0, "case1@ws2[randn]")),
        _rank_json(1, perf=_perf(370.0, 296.0, "case1@ws2[randn]")),
        _rank_json(0, perf=_perf(660.0, 520.0, "case2@ws2[randn]")),
        _rank_json(1, perf=_perf(670.0, 518.0, "case2@ws2[randn]")),
    ]
    agg = getattr(multirank_runner, "_aggregate_perf")(rs)
    st = agg["case_stats"]
    # flipped case: mean of {7.2, 0.2} = 3.7, and the std shows the imbalance
    assert st["case0@ws2[randn]"]["candidate_us_std"] > 0
    # campaign ratio = median of the 3 case ratios {3.7, 0.8, 0.78} ≈ 0.8
    assert 0.7 < agg["ratio"] < 0.9


def test_run_perf_mode_emits_performance_pass(tmp_path, monkeypatch):
    """run(perf=True) with rank perf ratio>1 -> verification.json performance

    PASS + independent_re_measure; precision block NOT written (perf_only).
    """
    perf = {
        "candidate_us": 100.0,
        "baseline_us": 200.0,
        "ratio": 2.0,
        "profile_dirs": [],
        "cases": [
            {
                "case_id": "case0@ws2[randn]",
                "candidate_us": 100.0,
                "baseline_us": 200.0,
                "ratio": 2.0,
            }
        ],
    }
    seq = [(0, _rank_json(0, perf=perf)), (0, _rank_json(1, perf=perf))]
    monkeypatch.setattr(multirank_runner.subprocess, "Popen", _fake_popen(seq))
    monkeypatch.setattr(multirank_runner, "_free_port", lambda: 29500)
    ws = _make_ws(tmp_path)
    _provision_fake_golden(ws, [2])
    res = multirank_runner.run(
        multirank_runner.CampaignContext(workspace=ws, op="op", perf=True), [0, 1]
    )
    assert res.runner_error is None
    assert res.perf is not None and res.perf["ratio"] == 2.0
    assert res.pass_a is None  # perf mode: precision unmeasured
    vj = json.loads((ws / "verification.json").read_text())
    assert vj["performance"]["status"] == "PASS"
    assert vj["performance"]["ratio"] == 2.0
    assert vj["performance"]["independent_re_measure"]["ran"] is True
    # no receipt plumbing — measurement returned as measured
    assert "trusted_receipt" not in vj["performance"]
    assert "execution_report" not in vj["performance"]
    assert "precision" not in vj  # perf_only preserves prior precision
    assert not (ws / "perf_report.md").exists()  # no per-op perf report writer


def test_run_perf_mode_irm_is_orchestrator_sourced(tmp_path, monkeypatch):
    """The emitted independent_re_measure carries an orchestrator `source`

    stamp — the irm gate rejects a ran=true claim without one, and
    fsm_phase_finalize would otherwise relabel the orchestrator measurement
    as worker-authored. Validated against the REAL gate predicate.
    """
    import perf_irm_provenance

    # Enter via finalize_pipeline (the finalize_pipeline <-> finalize_checks
    # import-cycle root): a cold finalize_checks_provenance import would
    # ImportError. Matches test_debt_217_perf_irm_provenance.py's pattern.
    import finalize_pipeline  # noqa: F401
    import finalize_checks_provenance as fcp

    perf = _perf_payload(
        candidate_us=100.0, baseline_us=90.0, ratio=1.1, with_profile_dirs=False
    )
    seq = [(0, _rank_json(0, perf=perf)), (0, _rank_json(1, perf=perf))]
    ws = _wire_rank_env(monkeypatch, tmp_path, popen=_fake_popen(seq))
    assert (
        multirank_runner.run(
            multirank_runner.CampaignContext(workspace=ws, op="op", perf=True), [0, 1]
        ).runner_error
        is None
    )
    vj = json.loads((ws / "verification.json").read_text())
    block = vj["performance"]
    # aggregate fragment at top level (the plugin merge shape), slim stamped irm
    assert block["case_stats"]["case0@ws2[randn]"]["ratio"] == 1.1
    assert block["method"]
    irm = block["independent_re_measure"]
    assert perf_irm_provenance.is_orchestrator_measured(irm) is True
    assert irm["ratio"] == 1.1 and irm["median_ratio"] == 1.1
    # the actual finalize gate accepts the emitted shape (read-only check)
    assert (
        getattr(fcp, "_validate_independent_perf_measure")(irm, "PASS", "PASS") is None
    )


def test_run_perf_mode_no_baseline_is_na(tmp_path, monkeypatch):
    """run(perf=True) candidate-only perf (no baseline) -> performance N/A with

    the perf-mode reason (distinct from precision-mode N/A) + honest na_kind
    + unmeasured irm (ran=false, orchestrator-attempted source).
    """
    perf = _perf_payload(baseline_us=None, ratio=None)
    seq = [(0, _rank_json(0, perf=perf)), (0, _rank_json(1, perf=perf))]
    ws = _wire_rank_env(monkeypatch, tmp_path, popen=_fake_popen(seq))
    res = multirank_runner.run(
        multirank_runner.CampaignContext(workspace=ws, op="op", perf=True), [0, 1]
    )
    assert res.runner_error is None
    assert res.perf is not None and res.perf["ratio"] is None
    vj = json.loads((ws / "verification.json").read_text())
    assert vj["performance"]["status"] == "N/A"
    assert "perf_baseline absent" in vj["performance"]["reason"]
    assert vj["performance"]["na_kind"] == "UNMEASURABLE_BY_DESIGN"
    irm = vj["performance"]["independent_re_measure"]
    assert irm["ran"] is False and irm["status"] == "N/A"
    assert irm["reason"]


def test_run_default_precision_mode_perf_none(tmp_path, monkeypatch):
    """run() default (perf=False) -> res.perf None + performance N/A (precision-

    mode reason). Backward-compat: existing precision runs unchanged.
    """
    seq = [(0, _rank_json(0)), (0, _rank_json(1))]
    monkeypatch.setattr(multirank_runner.subprocess, "Popen", _fake_popen(seq))
    monkeypatch.setattr(multirank_runner, "_free_port", lambda: 29500)
    ws = _make_ws(tmp_path)
    _provision_fake_golden(ws, [2])
    res = multirank_runner.run(
        multirank_runner.CampaignContext(workspace=ws, op="op"), [0, 1]
    )
    assert res.runner_error is None
    assert res.perf is None
    assert res.pass_a is not None  # precision measured
    vj = json.loads((ws / "verification.json").read_text())
    assert vj["performance"]["status"] == "N/A"
    assert "perf_baseline" in vj["performance"]["reason"]


# ---------------------------------------------------------------------------
# lanes=None — per-group auto-allocation (the production path)
# ---------------------------------------------------------------------------


def test_run_all_groups_auto_allocates_per_group_ascending(tmp_path, monkeypatch):
    """lanes=None: each group's idle cards are probed right before ITS launch,

    groups run in ASCENDING world_size order, and every group's cards are
    confirmed process-clean right after.
    """

    ws = _make_ws(tmp_path)
    _write_spec(ws, [4, 2, 1])  # deliberately unsorted; declared order is sorted
    _provision_fake_golden(ws, [1, 2, 4])
    picks, confirms = _wire_probe_recorders(monkeypatch)
    seq = (
        [(0, _rank_json(0))]
        + [(0, _rank_json(r)) for r in range(2)]
        + [(0, _rank_json(r)) for r in range(4)]
    )
    monkeypatch.setattr(multirank_runner.subprocess, "Popen", _fake_popen(seq))
    monkeypatch.setattr(multirank_runner, "_free_port", lambda: 29500)
    res = multirank_runner.run_all_groups(
        multirank_runner.CampaignContext(workspace=ws, op="op", env=object()), None
    )
    assert res.runner_error is None, res.runner_error
    assert picks == [1, 2, 4]  # ascending, per group
    assert confirms == [[10], [10, 11], [10, 11, 12, 13]]


def test_run_all_groups_auto_alloc_failure_mid_campaign(tmp_path, monkeypatch):
    """A group that cannot get enough idle cards is recorded UNVERIFIED and the

    campaign CONTINUES (ws=1 ran, ws=8 skipped with objective probe evidence) —
    no longer an immediate whole-campaign runner_error.
    """
    import npu_probe

    ws = _make_ws(tmp_path)
    _write_spec(ws, [1, 8])
    _provision_fake_golden(ws, [1, 8])
    calls: list[int] = []

    def _pick(env, n):
        calls.append(n)
        if n > 1:
            return None, f"only 1 idle NPU(s) but {n} needed"
        return [3], None

    monkeypatch.setattr(npu_probe, "pick_idle", _pick)
    monkeypatch.setattr(npu_probe, "confirm_idle", lambda env, lanes: None)
    monkeypatch.setattr(
        multirank_runner.subprocess, "Popen", _fake_popen([(0, _rank_json(0))])
    )
    monkeypatch.setattr(multirank_runner, "_free_port", lambda: 29500)
    res = multirank_runner.run_all_groups(
        multirank_runner.CampaignContext(workspace=ws, op="op", env=object()), None
    )
    assert res.runner_error is None, res.runner_error
    assert list(res.unverified_world_sizes) == ["8"]
    rec = res.unverified_world_sizes["8"]
    assert rec["status"] == "UNVERIFIED" and rec["reason"] == "card_shortage"
    assert "only 1 idle" in rec["detail"] and "probe" in rec
    # ws=1 ran: verification.json emitted with the rank_verdict for "1" and the
    # unverified placeholder for "8"
    vj = json.loads((ws / "verification.json").read_text())
    assert vj["multirank"]["world_sizes"] == [1, 8]
    assert len(vj["multirank"]["rank_verdicts"]["1"]) == 1
    assert "8" not in vj["multirank"]["rank_verdicts"]
    assert vj["multirank"]["unverified"]["8"]["status"] == "UNVERIFIED"


def test_run_all_groups_auto_alloc_failure_first_group_still_runner_error(
    tmp_path, monkeypatch
):
    """If NOTHING has run yet (the first group is card-short), the campaign

    cannot proceed at all — that stays a runner_error (the infra retry / pause
    path owns it), never an empty UNVERIFIED coverage.
    """
    import npu_probe

    ws = _make_ws(tmp_path)
    _write_spec(ws, [4, 8])
    _provision_fake_golden(ws, [4, 8])
    monkeypatch.setattr(
        npu_probe,
        "pick_idle",
        lambda env, n: (None, f"only 2 idle NPU(s) but {n} needed"),
    )
    monkeypatch.setattr(multirank_runner, "_free_port", lambda: 29500)
    res = multirank_runner.run_all_groups(
        multirank_runner.CampaignContext(workspace=ws, op="op", env=object()), None
    )
    assert res.runner_error is not None
    assert "world_size=4" in res.runner_error
    assert res.unverified_world_sizes == {}


def test_run_all_groups_unverified_carries_probe_evidence(tmp_path, monkeypatch):
    """The UNVERIFIED placeholder is tamper-evident: reason + detail + probe

    source are recorded so the finalize gate can distinguish an objective
    card-shortage from a worker self-report of 'did not run'.
    """
    import npu_probe

    ws = _make_ws(tmp_path)
    _write_spec(ws, [1, 4, 8])
    _provision_fake_golden(ws, [1, 4, 8])

    def _pick(env, n):
        if n > 1:
            return None, f"only 1 idle NPU(s) but {n} needed"
        return [7], None

    monkeypatch.setattr(npu_probe, "pick_idle", _pick)
    monkeypatch.setattr(npu_probe, "confirm_idle", lambda env, lanes: None)
    monkeypatch.setattr(
        multirank_runner.subprocess, "Popen", _fake_popen([(0, _rank_json(0))])
    )
    monkeypatch.setattr(multirank_runner, "_free_port", lambda: 29500)
    res = multirank_runner.run_all_groups(
        multirank_runner.CampaignContext(workspace=ws, op="op", env=object()), None
    )
    assert sorted(res.unverified_world_sizes, key=int) == ["4", "8"]
    for ws_key in ("4", "8"):
        rec = res.unverified_world_sizes[ws_key]
        assert rec["status"] == "UNVERIFIED"
        assert rec["reason"] == "card_shortage"
        assert rec["detail"] and rec["probe"]


def test_run_all_groups_post_run_confirm_failure(tmp_path, monkeypatch):
    """Leftover processes on a just-used card → probe_leak note on that case's

    entry (the verdicts are already collected and stay measured); the
    campaign completes and the next case's pick_idle re-probes on its own —
    never a whole-campaign runner_error.
    """
    import npu_probe

    ws = _make_ws(tmp_path)
    _write_spec(ws, [2])
    _provision_fake_golden(ws, [2])
    monkeypatch.setattr(npu_probe, "pick_idle", lambda env, n: (list(range(n)), None))
    monkeypatch.setattr(
        npu_probe,
        "confirm_idle",
        lambda env, lanes: "card(s) [1] still show running processes",
    )
    seq = [(0, _rank_json(0)), (0, _rank_json(1))]
    monkeypatch.setattr(multirank_runner.subprocess, "Popen", _fake_popen(seq))
    monkeypatch.setattr(multirank_runner, "_free_port", lambda: 29500)
    res = multirank_runner.run_all_groups(
        multirank_runner.CampaignContext(workspace=ws, op="op", env=object()), None
    )
    assert res.runner_error is None, res.runner_error
    cv = res.multirank_case_verdicts["case0@ws2[randn]"]
    assert cv["ranks"] == {"0": "PASS", "1": "PASS"}  # verdicts kept
    assert "card(s) [1]" in cv["probe_leak"]


def test_run_case_crash_keeps_measured_campaign(tmp_path, monkeypatch):
    """The moe_fused_a8w8 shape: case0/case1 measured PASS, case2's rank

    hard-crashes with no summary. The campaign COMPLETES — every case keeps
    its outcome (case2 folds a synthetic ERROR) — so O5 can reconcile an
    honest PARTIAL claim instead of hitting a structurally un-reconcilable
    runner_error.
    """
    ws = _make_ws(tmp_path)
    _provision_fake_golden(
        ws, [("case0@ws1[randn]", 1), ("case1@ws1[randn]", 1), ("case2@ws1[randn]", 1)]
    )
    seq = [
        (0, _rank_json(0)),  # case0 PASS
        (0, _rank_json(0)),  # case1 PASS
        (1, None),
    ]  # case2 rank0 hard crash, no summary
    monkeypatch.setattr(multirank_runner.subprocess, "Popen", _fake_popen(seq))
    monkeypatch.setattr(multirank_runner, "_free_port", lambda: 29500)
    res = multirank_runner.run(
        multirank_runner.CampaignContext(workspace=ws, op="op"), [0]
    )
    assert res.runner_error is None
    assert res.pass_a["status"] == "FAIL"
    assert res.pass_a["tier1_pass"] == 4 and res.pass_a["total"] == 5
    assert res.multirank_case_verdicts["case0@ws1[randn]"]["ranks"] == {"0": "PASS"}
    assert res.multirank_case_verdicts["case1@ws1[randn]"]["ranks"] == {"0": "PASS"}
    assert res.multirank_case_verdicts["case2@ws1[randn]"]["ranks"] == {"0": "ERROR"}
    # no verification.json emit on measured-FAIL (GAP-1 unchanged)
    assert not (ws / "verification.json").exists()


def test_synthetic_error_summary_is_canonical_judge_schema():
    """The synthetic ERROR entry is consumed by aggregate_all_ranks /

    case_verdicts_of / fold_rank_verdicts without special-casing: the
    aggregate honestly fails, and the O5 identity compare sees ERROR on the
    fail side (a claimed crash reconciles against it).
    """
    from multirank_precision_eval_two_tier import aggregate_all_ranks
    from multirank_rank_verdicts import case_verdicts_of, fold_rank_verdicts

    rs = getattr(multirank_runner, "_synthetic_error_summary")(
        1,
        "case0_ws2_randn",
        "rank exited rc=1 without a parseable summary",
        "workspace/.run/case0_ws2_randn/rank_1.log",
    )
    overall = aggregate_all_ranks([_rank_json(0), rs])
    assert overall["status"] == "FAIL"
    assert overall["tier1_pass"] == 2 and overall["total"] == 3
    ran = [("case0@ws2[randn]", [_rank_json(0), rs], {0: True, 1: False})]
    cv = case_verdicts_of(ran)["case0@ws2[randn]"]
    assert cv["ranks"] == {"0": "PASS", "1": "ERROR"}
    assert fold_rank_verdicts(2, ran)[1]["status"] == "FAIL"


def test_case_verdicts_of_probe_leak_orthogonal():
    """probe_leak is a hygiene note ORTHOGONAL to status: any verdict (here an

    ERROR cell — a crashed rank often leaves residue) may carry it, and the
    verdicts themselves are unchanged; no leak → no key.
    """
    from multirank_rank_verdicts import case_verdicts_of

    rs = getattr(multirank_runner, "_synthetic_error_summary")(
        0, "case0_ws1_randn", "rc=1", "log"
    )
    out = case_verdicts_of(
        [("case0@ws1[randn]", [rs], {0: False})],
        leaks={"case0@ws1[randn]": "card(s) [0] busy"},
    )
    cv = out["case0@ws1[randn]"]
    assert cv["ranks"] == {"0": "ERROR"}
    assert cv["probe_leak"] == "card(s) [0] busy"
    assert "probe_leak" not in case_verdicts_of([("c", [_rank_json(0)], {})])["c"]


def test_run_perf_writes_separate_rank_logs(tmp_path, monkeypatch):
    """A perf re-measure writes .run/<slug>.perf/ — the precision run's rank

    logs (the evidence post-hoc aggregation reads) are never overwritten.
    """
    ws = _make_ws(tmp_path)
    _provision_fake_golden(ws, [2])
    seq = [(0, _rank_json(0)), (0, _rank_json(1))]
    monkeypatch.setattr(multirank_runner.subprocess, "Popen", _fake_popen(seq))
    monkeypatch.setattr(multirank_runner, "_free_port", lambda: 29500)
    assert (
        multirank_runner.run(
            multirank_runner.CampaignContext(workspace=ws, op="op"), [0, 1]
        ).runner_error
        is None
    )
    prec_log = ws / ".run" / "case0_ws2_randn" / "rank_0.log"
    prec_log.write_text(prec_log.read_text() + "PRECISION-EVIDENCE\n")

    perf = _perf_payload()
    seq2 = [(0, _rank_json(0, perf=perf)), (0, _rank_json(1, perf=perf))]
    monkeypatch.setattr(multirank_runner.subprocess, "Popen", _fake_popen(seq2))
    res = multirank_runner.run(
        multirank_runner.CampaignContext(workspace=ws, op="op", perf=True), [0, 1]
    )
    assert res.runner_error is None
    # precision evidence intact; perf logs in their own dir
    assert "PRECISION-EVIDENCE" in prec_log.read_text()
    assert (ws / ".run" / "case0_ws2_randn.perf" / "rank_0.log").is_file()
    assert (ws / ".run" / "case0_ws2_randn.perf" / "rank_1.log").is_file()


def test_rank_verdict_entry_carries_failed_cases_only_for_fail(tmp_path):
    """A FAIL rank's rank_verdicts entry carries failed_cases with the per-case

    precision numbers (case_id + ours/comp MERE/MARE) so a failure stays
    diagnosable after the rank_*.log files are overwritten by a later group.
    PASS_T2 cases (tier1_pass=False but rescued by the parity arm) must NOT be
    listed as failures.
    """
    fail_rank = {
        "rank": 0,
        "status": "FAIL",
        "results": [
            {
                "case_id": "case0@ws1[randn]",
                "verdict": "PASS_T1",
                "tier1_pass": True,
                "ours_mere": 0.0,
                "ours_mare": 0.0,
            },
            {
                "case_id": "case1@ws1[randn]",
                "verdict": "FAIL",
                "tier1_pass": False,
                "tier2_status": "FAIL",
                "ours_mere": 6.07e-05,
                "ours_mare": 123.98,
                "comp_mere": 1.50e-06,
                "comp_mare": 0.104,
            },
            {
                "case_id": "case2@ws1[randn]",
                "verdict": "PASS_T2",
                "tier1_pass": False,
                "tier2_status": "PASS",
                "ours_mere": 1.26e-06,
                "ours_mare": 1.67,
                "comp_mere": 1.29e-06,
                "comp_mare": 1.67,
            },
        ],
    }
    entry = _rank_verdict_entry(fail_rank)
    assert entry["status"] == "FAIL"
    ids = [c["case_id"] for c in entry["failed_cases"]]
    assert ids == ["case1@ws1[randn]"], ids  # only the genuine FAIL, not PASS_T2
    assert entry["failed_cases"][0]["ours_mare"] == 123.98

    # PASS rank carries no failed_cases key at all
    ok = _rank_verdict_entry({"rank": 1, "status": "PASS"})
    assert "failed_cases" not in ok


def test_run_all_groups_filter_ws_runs_only_that_group(tmp_path, monkeypatch):
    """--filter-ws=N: probe once for the N-card set, run ONLY the ws=N group,

    and NEVER touch verification.json (a filtered run is a diagnostic subset,
    not the campaign).
    """
    import npu_probe

    ws = _make_ws(tmp_path)
    _write_spec(ws, [1, 2, 4])
    _provision_fake_golden(ws, [1, 2, 4])
    picks: list[int] = []
    monkeypatch.setattr(
        npu_probe,
        "pick_idle",
        lambda env, n: (picks.append(n), (list(range(10, 10 + n)), None))[1],
    )
    monkeypatch.setattr(npu_probe, "confirm_idle", lambda env, lanes: None)
    seq = [(0, _rank_json(0)), (0, _rank_json(1))]
    monkeypatch.setattr(multirank_runner.subprocess, "Popen", _fake_popen(seq))
    monkeypatch.setattr(multirank_runner, "_free_port", lambda: 29500)
    _ctx = multirank_runner.CampaignContext(workspace=ws, op="op", env=object())
    res = multirank_runner.run_all_groups(_ctx, None, filter_ws=2)
    assert res.runner_error is None, res.runner_error
    assert picks == [2]  # only the ws=2 group
    assert res.pass_a["status"] == "PASS"
    assert not (ws / "verification.json").exists()  # untouched by design


def test_run_all_groups_filter_ws_undeclared_errors(tmp_path, monkeypatch):
    """--filter-ws naming an undeclared world_size → loud runner_error; no group may be invented."""
    import npu_probe

    ws = _make_ws(tmp_path)
    _write_spec(ws, [1, 2, 4])
    _provision_fake_golden(ws, [1, 2, 4])
    called = []
    monkeypatch.setattr(
        npu_probe, "pick_idle", lambda env, n: called.append(n) or ([0], None)
    )
    _ctx = multirank_runner.CampaignContext(workspace=ws, op="op", env=object())
    res = multirank_runner.run_all_groups(_ctx, None, filter_ws=3)
    assert res.runner_error and "--filter-ws=3" in res.runner_error
    assert "declared" in res.runner_error
    assert called == []


# ---------------------------------------------------------------------------
# per-case isolation (one launch per case: own probe / own logs / own golden)
# ---------------------------------------------------------------------------


def test_fold_rank_verdicts_multi_case(tmp_path):
    """The fold collapses per-case rank summaries into exactly ws entries:

    status PASS only if the rank PASSed every case; the entry's `cases` names
    what it covers; a case-level FAIL lands in that rank's failed_cases with
    the case's precision detail (and only that case's).
    """
    case_a = "case0@ws2[randn]"
    case_b = "case1@ws2[randn]"
    fail_b_rank1 = {
        "rank": 1,
        "status": "FAIL",
        "results": [
            {
                "case_id": case_b,
                "verdict": "FAIL",
                "tier1_pass": False,
                "ours_mere": 1.0,
                "ours_mare": 2.0,
                "comp_mere": 0.1,
                "comp_mare": 0.2,
            },
        ],
    }
    ran = [
        (case_a, [_rank_json(0), _rank_json(1)], {0: True, 1: True}),
        (case_b, [_rank_json(0), fail_b_rank1], {0: True, 1: False}),
    ]
    entries = getattr(multirank_runner, "_fold_rank_verdicts")(2, ran)
    assert len(entries) == 2
    e0, e1 = entries
    assert e0["rank"] == 0 and e0["status"] == "PASS"
    assert e0["cases"] == [case_a, case_b]
    assert "failed_cases" not in e0
    assert e1["rank"] == 1 and e1["status"] == "FAIL"
    assert e1["cases"] == [case_a, case_b]
    assert [c["case_id"] for c in e1["failed_cases"]] == [case_b]
    assert e1["failed_cases"][0]["ours_mare"] == 2.0


def test_case_verdicts_of_maps_per_case_ranks():
    """case_verdicts_of: compact per-case verdict map (per-rank verdict cell +

    summed tier counts) for the O5 coverage reconcile.
    """
    from multirank_rank_verdicts import case_verdicts_of

    fail_rank1 = {
        "rank": 1,
        "status": "FAIL",
        "tier1_pass": 1,
        "tier1_pass_inclusive": 1,
        "total": 2,
        "tier2_status": "FAIL",
        "results": [
            {"case_id": "case0@ws2[randn]", "verdict": "FAIL", "ours_mare": 9.9},
        ],
    }
    ran = [
        (
            "case0@ws2[randn]",
            [_rank_json(0, tier1_pass=2, total=2), fail_rank1],
            {0: True, 1: False},
        )
    ]
    out = case_verdicts_of(ran)
    cv = out["case0@ws2[randn]"]
    assert cv["world_size"] == 2
    assert cv["ranks"] == {"0": "PASS", "1": "FAIL"}
    assert cv["tier1_pass"] == 3 and cv["total"] == 4
    assert cv["failed_cases"][0]["case_id"] == "case0@ws2[randn]"


def test_record_group_unverified_shapes(tmp_path):
    """record_group_unverified: ALL missing → the full-group placeholder;

    some ran → per-case unverified_cases entries (probe evidence carried).
    """
    from multirank_rank_verdicts import record_group_unverified, GroupUnverifiedRecord

    cases = [{"name": "case0@ws2[randn]"}, {"name": "case1@ws2[randn]"}]
    unv: dict = {}
    unv_cases: dict = {}
    # all card-short
    record_group_unverified(
        GroupUnverifiedRecord(
            ws=2,
            group_cases=cases,
            ran=[],
            missing=[(cases[1], "only 1 idle NPU(s)")],
            probe_label="probe-label",
        ),
        unv,
        unv_cases,
    )
    assert list(unv) == ["2"] and not unv_cases
    assert unv["2"]["reason"] == "card_shortage"
    assert "case1@ws2[randn]" in unv["2"]["detail"]
    # partial: one case ran, one card-short
    unv, unv_cases = {}, {}
    record_group_unverified(
        GroupUnverifiedRecord(
            ws=2,
            group_cases=cases,
            ran=[("case0", [{}], {})],
            missing=[(cases[1], "only 1 idle NPU(s)")],
            probe_label="probe-label",
        ),
        unv,
        unv_cases,
    )
    assert not unv and list(unv_cases) == ["case1@ws2[randn]"]
    rec = unv_cases["case1@ws2[randn]"]
    assert rec["world_size"] == 2 and rec["probe"] == "probe-label"


def test_run_all_groups_probes_and_logs_per_case(tmp_path, monkeypatch):
    """Per-case isolation in the auto-alloc path: TWO cases at the same ws →

    TWO probes (one before each case's own launch), TWO confirm_idle checks,
    and each case's rank logs under its own .run/<case-slug>/ dir.
    """

    ws = _ws_two_case_specs(tmp_path)
    picks, confirms = _wire_probe_recorders(monkeypatch)
    seq = (
        [(0, _rank_json(0)), (0, _rank_json(1))]  # case0 launch
        + [(0, _rank_json(0)), (0, _rank_json(1))]
    )  # case1 launch
    monkeypatch.setattr(multirank_runner.subprocess, "Popen", _fake_popen(seq))
    monkeypatch.setattr(multirank_runner, "_free_port", lambda: 29500)
    res = multirank_runner.run_all_groups(
        multirank_runner.CampaignContext(workspace=ws, op="op", env=object()), None
    )
    assert res.runner_error is None, res.runner_error
    assert picks == [2, 2]  # one probe per case
    assert confirms == [[10, 11], [10, 11]]  # one confirm per case
    for slug in ("case0_ws2_randn", "case1_ws2_randn"):
        assert (ws / ".run" / slug / "rank_0.log").is_file(), slug
        assert (ws / ".run" / slug / "rank_1.log").is_file(), slug
    vj = json.loads((ws / "verification.json").read_text())
    assert len(vj["multirank"]["rank_verdicts"]["2"]) == 2
    assert vj["multirank"]["rank_verdicts"]["2"][0]["cases"] == [
        "case0@ws2[randn]",
        "case1@ws2[randn]",
    ]


def test_run_all_groups_partial_ws_unverified_cases(tmp_path, monkeypatch):
    """Card shortage mid-group: one case at ws=2 runs, the second case's probe

    fails → the group is PARTIALLY verified. rank_verdicts['2'] folds the case
    that ran; the missing case is loud under mc2.unverified_cases with probe
    evidence; the ws-level O5 projection still reports ws=2.
    """
    import npu_probe

    ws = _ws_two_case_specs(tmp_path)
    picks: list[int] = []

    def _pick(env, n):
        picks.append(n)
        if len(picks) == 1:
            return [3, 4], None
        return None, f"only 1 idle NPU(s) but {n} needed"

    monkeypatch.setattr(npu_probe, "pick_idle", _pick)
    monkeypatch.setattr(npu_probe, "confirm_idle", lambda env, lanes: None)
    seq = [(0, _rank_json(0)), (0, _rank_json(1))]  # case0 launch only
    monkeypatch.setattr(multirank_runner.subprocess, "Popen", _fake_popen(seq))
    monkeypatch.setattr(multirank_runner, "_free_port", lambda: 29500)
    res = multirank_runner.run_all_groups(
        multirank_runner.CampaignContext(workspace=ws, op="op", env=object()), None
    )
    assert res.runner_error is None, res.runner_error
    assert list(res.unverified_world_sizes) == ["2"]
    proj = res.unverified_world_sizes["2"]
    assert proj["status"] == "UNVERIFIED" and proj["reason"] == "card_shortage"
    vj = json.loads((ws / "verification.json").read_text())
    mr_block = vj["multirank"]
    assert len(mr_block["rank_verdicts"]["2"]) == 2
    assert mr_block["rank_verdicts"]["2"][0]["cases"] == ["case0@ws2[randn]"]
    assert "unverified" not in mr_block, "partial group is not a full-group placeholder"
    uv = mr_block["unverified_cases"]["case1@ws2[randn]"]
    assert uv["status"] == "UNVERIFIED" and uv["reason"] == "card_shortage"
    assert "only 1 idle" in uv["detail"] and uv["probe"] and uv["world_size"] == 2


# An honest FAIL roll the perf-only emit must preserve verbatim (module-level
# so the test body stays under the size gate).
_HONEST_FAIL_BLOCK = {
    "world_sizes": [2],
    "rank_verdicts": {
        "2": [
            {
                "rank": 0,
                "status": "FAIL",
                "failed_cases": [
                    {
                        "case_id": "case0@ws2[randn]",
                        "verdict": "FAIL",
                        "ours_mare": 123.98,
                    }
                ],
            },
            {"rank": 1, "status": "PASS"},
        ]
    },
}


def test_perf_emit_preserves_precision_multirank_block(tmp_path, monkeypatch):
    """A perf-only emit updates `performance` but must NOT touch the mc2

    rank-verdict block: perf-mode rank summaries are vacuously PASS and would
    erase an honest FAIL roll (rank + failed_cases) written by the precision
    campaign or the worker's claimed artifact.
    """
    honest_block = _HONEST_FAIL_BLOCK
    perf = _perf_payload(candidate_us=100.0, baseline_us=90.0, ratio=0.9)
    seq = [(0, _rank_json(0, perf=perf)), (0, _rank_json(1, perf=perf))]
    ws = _wire_rank_env(monkeypatch, tmp_path, popen=_fake_popen(seq))
    (ws / "verification.json").write_text(
        json.dumps(
            {
                "precision": {
                    "status": "FAIL",
                    "pass_a": {"status": "FAIL", "tier1_pass": 3, "total": 4},
                },
                "multirank": honest_block,
            }
        )
    )
    res = multirank_runner.run(
        multirank_runner.CampaignContext(workspace=ws, op="op", perf=True), [0, 1]
    )
    assert res.runner_error is None
    vj = json.loads((ws / "verification.json").read_text())
    assert vj["multirank"] == honest_block, (
        "perf emit must not rewrite the multirank block"
    )
    assert vj["multirank"]["rank_verdicts"]["2"][0]["failed_cases"]
    assert vj["performance"]["ratio"] == 0.9  # perf block still updated
    assert vj["precision"]["status"] == "FAIL"  # precision claim untouched


# ---------------------------------------------------------------------------
# Remote (endpoint) campaign path: staging + remote launcher + log pullback
# ---------------------------------------------------------------------------
def _fake_campaign(op="op"):
    """A remote-container campaign context with a complete stage mapping."""
    from plugins.multirank import multirank_endpoint as ep

    endpoint = ep.ExecEndpoint(
        role="candidate",
        arch="a5",
        exec_mode="remote-container",
        host="a5.test",
        user="root",
        container="cjm",
        block_present=True,
        stage_host_dir="/data/ws",
        stage_container_dir="/cw",
    )
    return getattr(multirank_runner, "_RemoteCampaign")(
        endpoint, "/data/ws/multirank_verify", "/cw/multirank_verify", op
    )


class _R:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_resolve_remote_none_for_local_or_missing_env(monkeypatch):
    from plugins.multirank import multirank_endpoint as ep

    monkeypatch.setattr(ep, "load_env_or_none", lambda: None)
    assert getattr(multirank_runner, "_resolve_remote")("op") is None
    from briefs._common import AscendCEnv, TargetConfig

    monkeypatch.setattr(
        ep,
        "load_env_or_none",
        lambda: AscendCEnv(
            target="a5", targets={"a5": TargetConfig(arch="a5", exec_mode="local")}
        ),
    )
    assert getattr(multirank_runner, "_resolve_remote")("op") is None


def test_resolve_remote_builds_campaign(monkeypatch):
    monkeypatch.setattr(multirank_runner, "_resolve_remote", _ORIG_RESOLVE_REMOTE)
    from plugins.multirank import multirank_endpoint as ep
    from briefs._common import AscendCEnv, TargetConfig

    monkeypatch.setattr(
        ep,
        "load_env_or_none",
        lambda: AscendCEnv(
            target="a5",
            targets={
                "a5": TargetConfig(
                    arch="a5",
                    host="h",
                    container="c",
                    exec_mode="remote-container",
                    stage_host_dir="/data/ws",
                    stage_container_dir="/cw",
                )
            },
        ),
    )
    rc = getattr(multirank_runner, "_resolve_remote")("myop")
    assert rc is not None
    assert rc.ws_exec == "/cw/multirank_verify/myop"
    assert rc.stage_host == "/data/ws/multirank_verify"


def test_run_remote_launches_and_pulls(monkeypatch, tmp_path):
    """run() on a remote campaign: the launcher is invoked ON THE ENDPOINT

    with stage-side paths + device ids + the verify extras; the rank logs
    are pulled back and verdict aggregation is IDENTICAL to the local path.
    """
    ws = _make_ws(tmp_path)
    ws_name = ws.name  # _make_ws uses tmp/ws; sync paths key off ws.name
    _provision_fake_golden(ws, [2])
    campaign = _fake_campaign(ws.name)
    from plugins.multirank import multirank_endpoint as ep

    launched = []

    def _remote_exec(endpoint, cmd, timeout=None):
        joined = " ".join(cmd)
        if joined.startswith("mkdir"):
            return _R()
        if "npu-smi" in joined:
            return _R()
        if "multirank_remote_launch.py" in joined:
            launched.append(cmd)
            return _R()
        return _R()

    def _sync_down(endpoint, remote_dir, names, local_dir):
        # Simulate the pull: the "remote" rank logs land under workspace/.run
        slug = None
        for name in names:
            parts = name.split("/")
            if len(parts) >= 3:
                slug = parts[-2]
        for r in range(2):
            log = ws / ".run" / slug / f"rank_{r}.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            log.write_text(json.dumps(_rank_json(r)) + "\n")
            (ws / ".run" / slug / f"rank_{r}.rc").write_text("0\n")
        return {"transferred": list(names), "skipped": []}

    monkeypatch.setattr(ep, "remote_exec", _remote_exec)
    monkeypatch.setattr(ep, "sync_down", _sync_down)
    monkeypatch.setattr(
        ep, "sync_up", lambda e, files, d: {"transferred": [], "skipped": []}
    )

    res = multirank_runner.run(
        multirank_runner.CampaignContext(workspace=ws, op=ws_name, remote=campaign),
        [0, 1],
    )
    assert res.runner_error is None
    # two ranks x 2 tier1 each aggregate to 4 (same semantics as local)
    assert res.pass_a["tier1_pass"] == 4 and res.pass_a["status"] == "PASS"
    # the launcher ran on the endpoint with exec-side paths + device ids
    assert len(launched) == 1
    cmd = launched[0]
    assert cmd[0] == "python3"
    assert cmd[1] == campaign.launch_exec
    assert cmd[2] == campaign.verify_exec
    assert cmd[3] == campaign.ws_exec
    assert cmd[4] == "case0_ws2_randn"
    assert cmd[5] == "2"
    assert cmd[7:9] == ["0", "1"]  # device ids forwarded
    assert "--" in cmd and "--ref" in cmd


def test_remote_launch_failure_measured_not_dropped(monkeypatch, tmp_path):
    """A launcher-level failure (ssh/stage broken) is MEASURED: every rank

    gets a synthetic ERROR entry — the case is never silently dropped.
    """
    ws = _make_ws(tmp_path)
    _provision_fake_golden(ws, [2])
    campaign = _fake_campaign(ws.name)
    from plugins.multirank import multirank_endpoint as ep

    def _boom(endpoint, cmd, timeout=None):
        if "multirank_remote_launch.py" in " ".join(cmd):
            raise RuntimeError("ssh: connect timed out")
        return _R()

    monkeypatch.setattr(ep, "remote_exec", _boom)
    monkeypatch.setattr(
        ep, "sync_up", lambda e, files, d: {"transferred": [], "skipped": []}
    )
    res = multirank_runner.run(
        multirank_runner.CampaignContext(workspace=ws, op=ws.name, remote=campaign),
        [0, 1],
    )
    assert res.runner_error is None  # NOT a campaign-abort
    assert res.pass_a["status"] == "ERROR" or res.pass_a["tier1_pass"] == 0


def test_pick_idle_remote_parses_endpoint_npu_smi(monkeypatch):
    import lane_pool

    campaign = _fake_campaign()
    from plugins.multirank import multirank_endpoint as ep

    monkeypatch.setattr(
        ep, "remote_exec", lambda e, cmd, timeout=None: _R(stdout="unused")
    )
    fake_status = type("S", (), {"util_pct": 0, "has_running_process": False})()
    monkeypatch.setattr(
        lane_pool,
        "parse_npu_smi",
        lambda text, valid_ids=None: {0: fake_status, 1: fake_status},
    )
    lanes, err = getattr(multirank_runner, "_pick_idle_remote")(campaign, 2)
    assert err is None and lanes == [0, 1]
    busy = type("S", (), {"util_pct": 90, "has_running_process": False})()
    monkeypatch.setattr(
        lane_pool,
        "parse_npu_smi",
        lambda text, valid_ids=None: {0: fake_status, 1: busy},
    )
    lanes2, err2 = getattr(multirank_runner, "_pick_idle_remote")(campaign, 2)
    assert lanes2 is None and "idle NPU" in err2


if __name__ == "__main__":
    _sys = sys
    _pytest = pytest
    _sys.exit(_pytest.main([__file__, "-v"]))


def test_activate_opp_env_pythonpath_includes_scripts_root(tmp_path):
    """The judge's import closure reaches precision_eval_two_tier at the

    src/scripts root — without it on PYTHONPATH the LOCAL launch path fails
    with ModuleNotFoundError (the remote staged copy carries the tree and
    worked).
    """
    op_dir = tmp_path / "op"
    (
        op_dir / ".install" / "packages" / "vendors" / "customize" / "op_api" / "lib"
    ).mkdir(parents=True)
    env = getattr(multirank_runner, "_activate_opp_env")({}, op_dir, "op")
    entries = env["PYTHONPATH"].split(":")
    scripts_root = str(Path(multirank_runner.__file__).resolve().parents[3])
    assert scripts_root in entries
    assert str(Path(multirank_runner.__file__).resolve().parent) in entries


def test_run_only_raises_on_staging_failure(monkeypatch, tmp_path):
    """run_only must fail loud on remote staging errors — silently returning

    shows up as 'nothing happened' with the reason lost.
    """
    ws = tmp_path / "op_ws"
    ws.mkdir()
    monkeypatch.setattr(multirank_runner, "_resolve_remote", lambda op: object())
    monkeypatch.setattr(
        multirank_runner,
        "_remote_stage",
        lambda remote, workspace, op: "scp: connection refused",
    )
    with pytest.raises(RuntimeError, match="connection refused"):
        multirank_runner.run_only_mode(ws, "op")


def test_remote_stage_files_carries_judge_import_closure(tmp_path):
    """The staged judge closure must mirror the sys.path inserts the staged

    modules perform — a missing member surfaces on the endpoint as a
    per-rank ModuleNotFoundError, never as a stage error.
    """
    ws = tmp_path / "op_ws"
    ws.mkdir()
    manifest = getattr(multirank_runner, "_remote_stage_files")(ws, "op")
    names = {name for _, name in manifest}
    for required in (
        "precision_eval_two_tier.py",
        "precision_tier1.py",
        "precision_tier2.py",
        "reference_provider/verify.py",
        "orchestrator/precision/cannbench_grader/__init__.py",
        "orchestrator/precision/cannbench_grader/compare.py",
        "orchestrator/precision/cannbench_grader/thresholds.py",
    ):
        assert required in names
    _precision_mods = {
        "precision_eval_two_tier.py",
        "precision_tier1.py",
        "precision_tier2.py",
        "reference_provider/verify.py",
    }
    closure = []
    for p, n in manifest:
        if n in _precision_mods or n.startswith(
            "orchestrator/precision/cannbench_grader/"
        ):
            closure.append(p)
    assert closure and all(p.is_file() for p in closure)


def test_remote_stage_import_smoke_fails_loud(monkeypatch, tmp_path):
    """A judge closure gap must fail the campaign at STAGE time — the smoke

    probes the endpoint-side import so manifest drift never degrades into
    eight rc=1 rank logs to excavate.
    """
    ws = _make_ws(tmp_path)
    (ws / "spec.py").write_text("")  # op surface — else nothing-to-stage fires
    campaign = _fake_campaign(ws.name)
    from plugins.multirank import multirank_endpoint as ep

    def _remote_exec(endpoint, cmd, timeout=None):
        joined = " ".join(cmd)
        if joined.startswith("mkdir"):
            return _R()
        assert "import precision_eval_two_tier" in joined
        assert campaign.stage_exec in joined
        return _R(
            returncode=1,
            stderr="ModuleNotFoundError: No module named 'precision_tier2'",
        )

    monkeypatch.setattr(ep, "remote_exec", _remote_exec)
    monkeypatch.setattr(
        ep, "sync_up", lambda e, files, d: {"transferred": [], "skipped": []}
    )
    res = getattr(multirank_runner, "_remote_stage")(campaign, ws, ws.name)
    assert res is not None and res.runner_error is not None
    assert "import smoke failed" in res.runner_error
    assert "precision_tier2" in res.runner_error
    # happy path: a clean endpoint import keeps staging silent (None)
    monkeypatch.setattr(ep, "remote_exec", lambda endpoint, cmd, timeout=None: _R())
    assert getattr(multirank_runner, "_remote_stage")(campaign, ws, ws.name) is None


def test_remote_launch_shares_full_ordered_device_mask(monkeypatch, tmp_path):
    """All rank processes must get the SAME full ordered mask — CANN

    renumbers the ordered mask to local 0..ws-1, so verify-side
    set_device(rank) binds rank r to dev_ids[r]. A per-rank single-device
    mask renumbers that one card to npu:0 and every rank > 0 dies with
    NPU 10701 (Invalid device ID, expected [0,1)).
    """
    from plugins.multirank import multirank_remote_launch as rl

    ws = tmp_path / "ws"
    ws.mkdir()
    spawns = []

    class _P:
        @staticmethod
        def wait(timeout=None):
            return 0

        def kill(self):
            pass

    def _popen(cmd, env=None, **kw):
        spawns.append((cmd, env))
        return _P()

    monkeypatch.setattr(rl.subprocess, "Popen", _popen)
    monkeypatch.setattr(rl, "_opp_env", lambda ws_dir: {})
    monkeypatch.setattr(
        rl.sys,
        "argv",
        [
            "multirank_remote_launch.py",
            "verify.py",
            str(ws),
            "slug0",
            "3",
            "29500",
            "4",
            "6",
            "8",
            "--",
        ],
    )
    assert rl.main() == 0
    assert len(spawns) == 3
    masks = {env["ASCEND_RT_VISIBLE_DEVICES"] for _, env in spawns}
    assert masks == {"4,6,8"}
    for r, (cmd, _env) in enumerate(spawns):
        assert cmd[cmd.index("--rank") + 1] == str(r)
