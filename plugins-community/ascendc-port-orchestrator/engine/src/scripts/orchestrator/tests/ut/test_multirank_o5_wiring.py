# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

"""multirank O5 wiring (#14) — engine-side final seam.

Pins the four wiring points this task added:

  1. fsm_phase_finalize._o5_post_verify
     - R2 durable-marker HIT  → re-measure never runs (post_verify_for_finalize
       is not even called);
     - R2 MISS                → the O5 runner is the multirank one
       (multirank_runner.run_all_groups(multirank_runner.CampaignContext(workspace=ws, op=op), None), never ssh_runner);
     - VERIFIED arm delegates to fsm_finalize_coverage.handle_o5_verified
       (ctx, lane, o5, truth_source) — including the UNVERIFIED-coverage pause;
     - RUNNER_FAILED splits by truth source: multirank adopts the coverage module's
       infra→await_user_decision / algorithm→await_worker split, non-multirank keeps
       the legacy always-await_worker routing.

  2. phase_o5.post_verify_for_finalize reconcile dispatch
     - truth_source==multirank AND a per-case verdict map →
       multirank_o5_reconcile.reconcile_multirank_coverage (never _reconcile_counts);
     - anything else (non-mc2, or an mc2 runner without the map) → the
       count-level _reconcile_counts exactly as before;
     - the runner's unverified_world_sizes is forwarded onto the report
       ({} when absent).

  3. MeasuredResult / O5Report field formalization — declared defaults match
     getattr(multirank_runner, "_measured")() and the defensive getattr reads.

  4. classify_runner_error — the multirank card-allocation / probe / EJ0003
     host-port tokens classify INFRA; kernel verdicts stay ALGORITHM.

Run: cd engine/src/scripts && PYTHONPATH=. python3 -m pytest \
     orchestrator/tests/ut/test_mc2_o5_wiring.py -v
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parent.parent.parent))  # orchestrator/

import orchestrator  # noqa: E402,F401  (force module identity for fsm_context read-through)
import fsm_finalize_coverage as coverage  # noqa: E402
import fsm_phase_finalize as F  # noqa: E402
from plugins.multirank import multirank_o5_reconcile  # noqa: E402
from plugins.multirank import multirank_runner  # noqa: E402
import phase_o5  # noqa: E402
import state_executor  # noqa: E402
from _o5_post_verify_stubs import wire_recorded_transitions  # noqa: E402
from fsm_context import OrchestratorContext  # noqa: E402
from phase_o5 import classify_runner_error  # noqa: E402


MULTIRANK_TS = "multirank"
CASE = "case0@ws1[randn]"


# ---------------------------------------------------------------------------
# shared fixtures / seeds (mock style of test_fsm_phase_finalize /
# test_debt_o5_infra_0_misclassify_retry)
# ---------------------------------------------------------------------------


class _Snap:
    iter_counts: dict = {}


def _ctx(tmp_path) -> OrchestratorContext:
    ws = tmp_path / "op"
    ws.mkdir()
    return OrchestratorContext(op="op", workspace=ws, lane=0)


def _wire_o5_common(monkeypatch, truth_source: str = MULTIRANK_TS) -> list:
    """Neutralize the reload/emit/rollback seams; returns recorded next states."""
    monkeypatch.setattr(phase_o5, "record_harness_state", lambda ws, rep: True)
    recorded = wire_recorded_transitions(monkeypatch, truth_source)
    monkeypatch.setattr(state_executor, "at_iter_cap", lambda ws, st: False)
    monkeypatch.setattr(state_executor, "iter_cap", lambda st, workspace=None: 9)
    return recorded


@pytest.fixture
def mc2_common(monkeypatch):
    """Neutralize the reload/emit/rollback seams with an multirank truth source.

    Returns the list of recorded transition target states.
    """
    return _wire_o5_common(monkeypatch)


def _seed_mc2_claim(ws: Path, *, tier1: int = 1, total: int = 1) -> None:
    """Minimal multirank verification.json claim: one world-size-1 case, rank0 PASS."""
    vj = {
        "precision": {
            "status": "PASS",
            "pass_a": {"status": "PASS", "tier1_pass": tier1, "total": total},
            "pass_b": {"status": "N/A"},
        },
        "multirank": {
            "world_sizes": [1],
            "cases": [{"name": CASE, "world_size": 1}],
            "rank_verdicts": {"1": [{"rank": 0, "status": "PASS", "cases": [CASE]}]},
        },
    }
    (ws / "verification.json").write_text(json.dumps(vj, indent=2))


def _mc2_measured(**extra):
    """A runner result whose per-case map identity-matches _seed_mc2_claim."""
    return getattr(multirank_runner, "_measured")(
        pass_a={"tier1_pass": 1, "total": 1},
        multirank_case_verdicts={CASE: {"world_size": 1, "ranks": {"0": "PASS"}}},
        **extra,
    )


def _wire_reconcile_recorders(monkeypatch) -> tuple[list, list]:
    """Patch both reconcile paths with plain call counters; (coverage, counts)."""
    coverage_calls: list = []
    counts_calls: list = []
    monkeypatch.setattr(
        multirank_o5_reconcile,
        "reconcile_multirank_coverage",
        lambda *a: coverage_calls.append(1),
    )
    monkeypatch.setattr(
        phase_o5, "_reconcile_counts", lambda *a: counts_calls.append(1)
    )
    return coverage_calls, counts_calls


def _seq_o5(monkeypatch, results):
    """Patch post_verify_for_finalize to return `results` in order (last
    repeats); return the call counter so tests can assert re-measure counts."""
    calls: list = []
    seq = list(results)

    def _fake(ws, op, lane, runner):
        calls.append(1)
        return seq[len(calls) - 1] if len(calls) <= len(seq) else seq[-1]

    monkeypatch.setattr(phase_o5, "post_verify_for_finalize", _fake)
    return calls


# ---------------------------------------------------------------------------
# 1a. R2 durable marker: HIT skips the re-measure
# ---------------------------------------------------------------------------


def test_r2_marker_hit_skips_remeasure(mc2_common, monkeypatch, tmp_path):
    """A current durable marker short-circuits O5: the synthesized VERIFIED

    report flows straight through the VERIFIED arm — the re-measure
    (post_verify_for_finalize) never runs and no runner is built.
    """
    marked = phase_o5.O5Report(
        verdict="VERIFIED",
        truth_source=MULTIRANK_TS,
        summary="O5 VERIFIED (durable marker)",
    )
    monkeypatch.setattr(
        multirank_o5_reconcile, "try_skip_remeasure", lambda ws, op: marked
    )
    monkeypatch.setattr(
        multirank_o5_reconcile, "stamp_verified_marker", lambda ws, o5: None
    )
    calls = _seq_o5(monkeypatch, [phase_o5.O5Report(verdict="MISMATCH")])

    res = getattr(F, "_o5_post_verify")(_ctx(tmp_path), _Snap())

    assert res is None, "marker-skip VERIFIED (full coverage) proceeds"
    assert calls == [], "the re-measure must NOT run on a marker hit"
    assert mc2_common == [], "no rollback on the marker-skip path"


def test_r2_marker_miss_runs_the_remeasure(mc2_common, monkeypatch, tmp_path):
    """Marker miss (None) falls through to the real re-measure exactly once."""
    monkeypatch.setattr(
        multirank_o5_reconcile, "try_skip_remeasure", lambda ws, op: None
    )
    monkeypatch.setattr(
        multirank_o5_reconcile, "stamp_verified_marker", lambda ws, o5: None
    )
    calls = _seq_o5(monkeypatch, [phase_o5.O5Report(verdict="VERIFIED", summary="ok")])

    res = getattr(F, "_o5_post_verify")(_ctx(tmp_path), _Snap())

    assert res is None
    assert len(calls) == 1


# ---------------------------------------------------------------------------
# 1b. R2 miss → the O5 runner is the multirank one (run_all_groups, lanes=None)
# ---------------------------------------------------------------------------


def test_marker_miss_selects_multirank_runner(mc2_common, monkeypatch, tmp_path):
    """On an multirank workspace the re-measure runner is

    multirank_runner.run_all_groups(
        multirank_runner.CampaignContext(workspace=ws, op=op), None) — the per-case auto-allocation
    production path, never ssh_runner. Driven through the REAL
    post_verify_for_finalize (claim + coverage-aware reconcile) so the runner
    contract, not just its selection, is exercised.
    """
    monkeypatch.setattr(
        multirank_o5_reconcile, "try_skip_remeasure", lambda ws, op: None
    )
    monkeypatch.setattr(
        multirank_o5_reconcile, "stamp_verified_marker", lambda ws, o5: None
    )
    ran: list = []

    def fake_run_all_groups(ctx, lanes=None, **kw):
        ran.append((ctx.workspace, ctx.op, lanes))
        return _mc2_measured()

    monkeypatch.setattr(multirank_runner, "run_all_groups", fake_run_all_groups)
    ctx = _ctx(tmp_path)
    _seed_mc2_claim(ctx.workspace)

    res = getattr(F, "_o5_post_verify")(ctx, _Snap())

    assert ran == [(ctx.workspace, "op", None)], (
        "the multirank runner must receive lanes=None (auto-allocation path)"
    )
    assert res is None, "full-coverage VERIFIED proceeds to finalize"


# ---------------------------------------------------------------------------
# 1c. VERIFIED arm delegates to fsm_finalize_coverage.handle_o5_verified
# ---------------------------------------------------------------------------


def test_verified_arm_delegates_with_truth_source(mc2_common, monkeypatch, tmp_path):
    """The VERIFIED arm hands (ctx, lane, o5, truth_source) to

    handle_o5_verified — the delegation replaces the former inline
    log+record (the coverage module performs those itself).
    """
    delegated: list = []

    def fake_handle(ctx, lane, o5, ts):
        delegated.append((ctx, lane, o5, ts))
        return None

    monkeypatch.setattr(coverage, "handle_o5_verified", fake_handle)
    o5 = phase_o5.O5Report(verdict="VERIFIED", summary="ok")
    monkeypatch.setattr(
        multirank_o5_reconcile, "try_skip_remeasure", lambda ws, op: None
    )
    _seq_o5(monkeypatch, [o5])
    ctx = _ctx(tmp_path)

    res = getattr(F, "_o5_post_verify")(ctx, _Snap())

    assert res is None
    assert len(delegated) == 1, "VERIFIED must delegate exactly once"
    assert delegated[0][0] is ctx
    assert delegated[0][2] is o5
    assert delegated[0][3] == MULTIRANK_TS


def test_verified_with_unverified_coverage_pauses(mc2_common, monkeypatch, tmp_path):
    """End-to-end VERIFIED delegation: a non-empty, non-accepted

    unverified_world_sizes set makes handle_o5_verified pause at
    await_user_decision (the R2 marker is stamped first for multirank).
    """
    monkeypatch.setattr(
        multirank_o5_reconcile, "try_skip_remeasure", lambda ws, op: None
    )
    stamped: list = []
    monkeypatch.setattr(
        multirank_o5_reconcile,
        "stamp_verified_marker",
        lambda ws, o5: stamped.append(o5),
    )
    _seq_o5(
        monkeypatch,
        [
            phase_o5.O5Report(
                verdict="VERIFIED",
                summary="O5 VERIFIED (coverage-aware)",
                unverified_world_sizes={"8": {"detail": "needed 8 idle NPU(s)"}},
            )
        ],
    )

    res = getattr(F, "_o5_post_verify")(_ctx(tmp_path), _Snap())

    assert res is not None and res.action == "continue"
    assert mc2_common == ["await_user_decision"], (
        "unverified coverage must pause for the user, not finalize silently"
    )
    assert stamped, "the multirank VERIFIED path stamps the R2 durable marker"


# ---------------------------------------------------------------------------
# 1d. RUNNER_FAILED split by truth source
# ---------------------------------------------------------------------------


def test_mc2_infra_runner_failed_pauses_for_user(mc2_common, monkeypatch, tmp_path):
    """multirank + infra-class RUNNER_FAILED surviving the bounded retry →

    await_user_decision (an external resource problem the worker cannot
    fix), NOT a worker respawn.
    """
    # the infra retry loop backs off 600s by default (transient host windows);
    # this test pins routing, not the window — zero the backoff
    monkeypatch.setenv("CANNBOT_O5_INFRA_RETRY_BACKOFF_SEC", "0")
    calls = _seq_o5(
        monkeypatch,
        [
            phase_o5.O5Report(
                verdict="RUNNER_FAILED",
                rollback_kind="infra",
                summary="multirank_runner.run_all_groups: lane auto-allocation failed",
            )
        ],
    )

    res = getattr(F, "_o5_post_verify")(_ctx(tmp_path), _Snap())

    assert res is not None and res.action == "continue"
    assert mc2_common == ["await_user_decision"]
    assert len(calls) == 1 + getattr(F, "_O5_INFRA_MAX_RETRIES"), (
        "infra failures re-attempt in place up to the bound, then pause"
    )


def test_mc2_algorithm_runner_failed_rolls_to_worker(mc2_common, monkeypatch, tmp_path):
    """multirank + algorithm-class RUNNER_FAILED → await_worker exactly as before

    (the worker CAN fix discoverability failures), no retry consumed.
    """
    calls = _seq_o5(
        monkeypatch,
        [
            phase_o5.O5Report(
                verdict="RUNNER_FAILED",
                rollback_kind="algorithm",
                summary="verifier discoverability gap",
            )
        ],
    )

    res = getattr(F, "_o5_post_verify")(_ctx(tmp_path), _Snap())

    assert res is not None and res.action == "continue"
    assert mc2_common == ["await_worker"]
    assert len(calls) == 1, "algorithm failures are not retried"


def test_non_mc2_infra_runner_failed_keeps_legacy_routing(monkeypatch, tmp_path):
    """Non-multirank modes keep the legacy routing: an infra RUNNER_FAILED

    (retry-exhausted) still rolls to await_worker — the multirank split must not
    change behavior for backward/port_a3 workspaces.
    """
    # infra retry loop backs off 600s by default; this test pins routing
    monkeypatch.setenv("CANNBOT_O5_INFRA_RETRY_BACKOFF_SEC", "0")
    recorded = _wire_o5_common(monkeypatch, truth_source="backward_autograd")
    calls = _seq_o5(
        monkeypatch,
        [
            phase_o5.O5Report(
                verdict="RUNNER_FAILED",
                rollback_kind="infra",
                summary="ssh timeout after 300s",
            )
        ],
    )

    res = getattr(F, "_o5_post_verify")(_ctx(tmp_path), _Snap())

    assert res is not None and res.action == "continue"
    assert recorded == ["await_worker"], (
        "non-multirank infra RUNNER_FAILED keeps the legacy await_worker rollback"
    )
    assert len(calls) == 1 + getattr(F, "_O5_INFRA_MAX_RETRIES")


# ---------------------------------------------------------------------------
# 2. phase_o5 reconcile dispatch + unverified forward
# ---------------------------------------------------------------------------


def test_reconcile_dispatch_mc2_uses_coverage_reconcile(monkeypatch, tmp_path):
    """truth_source==mc2 + a per-case verdict map → reconcile_multirank_coverage

    (the count-level _reconcile_counts is NOT called).
    """
    _seed_mc2_claim(tmp_path)
    monkeypatch.setattr(phase_o5, "expected_truth_source", lambda ws: MULTIRANK_TS)
    coverage_calls: list = []
    counts_calls: list = []

    def fake_reconcile(workspace, rep, measured, v):
        coverage_calls.append((workspace, rep, measured, v))
        rep.summary = "O5 VERIFIED (coverage-aware)"

    monkeypatch.setattr(
        multirank_o5_reconcile, "reconcile_multirank_coverage", fake_reconcile
    )
    monkeypatch.setattr(
        phase_o5, "_reconcile_counts", lambda *a: counts_calls.append(1)
    )
    measured = _mc2_measured()

    rep = phase_o5.post_verify_for_finalize(
        tmp_path, "op", runner=lambda ws, op, lane: measured
    )

    assert counts_calls == []
    assert len(coverage_calls) == 1
    assert coverage_calls[0][0] == tmp_path
    assert coverage_calls[0][2] is measured
    assert coverage_calls[0][3]["multirank"]["cases"][0]["name"] == CASE
    assert rep.verdict == "VERIFIED"


def test_reconcile_dispatch_non_mc2_uses_count_reconcile(monkeypatch, tmp_path):
    """A non-mc2 truth source keeps the count-level _reconcile_counts even

    when the runner happens to carry a per-case map.
    """
    _seed_mc2_claim(tmp_path)
    monkeypatch.setattr(phase_o5, "expected_truth_source", lambda ws: "cpu_pytorch")
    coverage_calls, counts_calls = _wire_reconcile_recorders(monkeypatch)

    phase_o5.post_verify_for_finalize(
        tmp_path, "op", runner=lambda ws, op, lane: _mc2_measured()
    )

    assert counts_calls, "non-mc2 must keep the count-level reconcile"
    assert coverage_calls == []


def test_reconcile_dispatch_mc2_without_case_map_falls_back(monkeypatch, tmp_path):
    """mc2 runner WITHOUT the per-case map (legacy/diagnostic runner shape)

    falls back to the count-level reconcile — the defensive getattr path.
    """
    _seed_mc2_claim(tmp_path)
    monkeypatch.setattr(phase_o5, "expected_truth_source", lambda ws: MULTIRANK_TS)
    coverage_calls, counts_calls = _wire_reconcile_recorders(monkeypatch)

    rep = phase_o5.post_verify_for_finalize(
        tmp_path,
        "op",
        runner=lambda ws, op, lane: phase_o5.MeasuredResult(
            pass_a={"tier1_pass": 1, "total": 1}
        ),
    )

    assert counts_calls, "no per-case map → count-level reconcile"
    assert coverage_calls == []
    assert rep.verdict == "VERIFIED"


def test_unverified_world_sizes_forwarded_to_report(monkeypatch, tmp_path):
    """The runner's unverified_world_sizes is forwarded onto the report so

    the finalize FSM can pause with the full coverage picture.
    """
    _seed_mc2_claim(tmp_path)
    monkeypatch.setattr(phase_o5, "expected_truth_source", lambda ws: MULTIRANK_TS)
    unv = {"8": {"status": "UNVERIFIED", "detail": "needed 8 idle NPU(s)"}}

    rep = phase_o5.post_verify_for_finalize(
        tmp_path,
        "op",
        runner=lambda ws, op, lane: _mc2_measured(unverified_world_sizes=unv),
    )

    assert rep.verdict == "VERIFIED"
    assert rep.unverified_world_sizes == unv


def test_unverified_world_sizes_defaults_to_empty(monkeypatch, tmp_path):
    """A result without the extras (any non-mc2 runner) forwards {} — never

    None — so downstream `if rep.unverified_world_sizes` stays honest.
    """
    _seed_mc2_claim(tmp_path)
    monkeypatch.setattr(phase_o5, "expected_truth_source", lambda ws: "cpu_pytorch")

    rep = phase_o5.post_verify_for_finalize(
        tmp_path,
        "op",
        runner=lambda ws, op, lane: phase_o5.MeasuredResult(
            pass_a={"tier1_pass": 1, "total": 1}
        ),
    )

    assert rep.unverified_world_sizes == {}


# ---------------------------------------------------------------------------
# 3. field formalization (declared defaults stay compatible with the
#    getattr(multirank_runner, "_measured") factory and the defensive getattr reads)
# ---------------------------------------------------------------------------


def test_measured_result_declares_mc2_field_defaults():
    m = phase_o5.MeasuredResult()
    assert m.unverified_world_sizes == {}
    assert m.multirank_case_verdicts is None


def test_measured_result_post_init_normalizes_none():
    m = phase_o5.MeasuredResult(unverified_world_sizes=None)
    assert m.unverified_world_sizes == {}


def test_o5_report_declares_unverified_default():
    r = phase_o5.O5Report(verdict="VERIFIED")
    assert r.unverified_world_sizes == {}


def test_mc2_measured_factory_compatible_with_declared_fields():
    """#12's factory keeps working now that the fields are declared: the

    explicit assignments land on the declared fields, same values.
    """
    m = getattr(multirank_runner, "_measured")(
        pass_a={"tier1_pass": 1, "total": 1},
        unverified_world_sizes={"2": {"detail": "d"}},
        multirank_case_verdicts={CASE: {"world_size": 1, "ranks": {"0": "PASS"}}},
    )
    assert m.unverified_world_sizes == {"2": {"detail": "d"}}
    assert m.multirank_case_verdicts[CASE]["ranks"] == {"0": "PASS"}
    # default path: factory normalizes to the declared defaults
    bare = getattr(multirank_runner, "_measured")(pass_a={"tier1_pass": 1, "total": 1})
    assert bare.unverified_world_sizes == {}
    assert bare.multirank_case_verdicts is None


# ---------------------------------------------------------------------------
# 4. multirank infra tokens in classify_runner_error
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "msg",
    [
        "multirank_runner.run_all_groups: lane auto-allocation failed for every case "
        "(first: case0 (world_size=8): NPU probe failed)",
        "case0 (world_size=2): NPU probe failed (reason on stderr) — refusing to "
        "guess idle cards",
        "multirank_runner.run_all_groups: post-run card check failed after case0 "
        "(world_size=2): post-run NPU probe failed (reason on stderr)",
        "rank1 stderr tail: ... Communication_Error_Bind_IP_Port ... abort HCCL init",
        "rank0 stderr tail: ... Failed to bind the IP port (EJ0003) ...",
    ],
)
def test_mc2_infra_tokens_classify_infra(msg):
    """Card-allocation / probe / EJ0003 host-port tokens are infra — the

    kernel didn't fail, the box's card/port weather did.
    """
    assert classify_runner_error(msg) == "infra"


@pytest.mark.parametrize(
    "msg",
    [
        "case0 rank1: verdict=FAIL (mere 1.2e-1 > tol) — real precision failure",
        "kernel assert failed: index 8 out of range for tensor of size 4",
        "case0: EVAL_ERR while comparing against the golden file",
    ],
)
def test_mc2_kernel_failures_stay_algorithm(msg):
    """Precision/kernel failures must keep consuming the algorithm budget."""
    assert classify_runner_error(msg) == "algorithm"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
