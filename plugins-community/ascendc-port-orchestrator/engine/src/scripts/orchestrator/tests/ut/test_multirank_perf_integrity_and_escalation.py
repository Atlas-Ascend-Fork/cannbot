# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

"""multirank perf integrity gate + finalize perf escalation (FSM G6 for perf data).

moe_fused_a8w8 shipped performance: N/A silently: the spec declared
perf_baseline, but the multirank plugin switched the finalize perf capture
off (should_run_phase_o5_perf_capture -> False silenced the whole capture,
plugin-owned multi-rank hook included), the FSM's below-threshold exit never
fired without data, and no gate owned "declared but never measured".

Covered here:
  - the capture switch is ON (the hook dispatch — measure_op_perf asks the
    plugin's finalize_perf_capture FIRST — keeps the single-card fallback
    unreachable for multirank)
  - multirank_perf_integrity: spec declares perf_baseline → measured ratio XOR
    .perf_waiver; undeclared spec → N/A by design, gate silent
  - _run_perf_capture escalation: an independently measured below-threshold
    ratio records finalize → await_optimizer; a skipped capture or an
    at/above-threshold ratio does not route
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parent.parent))  # orchestrator/
sys.path.insert(0, str(_HERE.parent.parent.parent))  # src/scripts/

import fsm_phase_finalize as fpf  # noqa: E402
import fsm_finalize_perf as fpf_perf  # noqa: E402
from plugins import get_plugin  # noqa: E402


_SPEC_WITH_BASELINE = (
    "def perf_baseline(inputs, device, rank, world_size):\n"
    "    return inputs['x'] * 2\n"
    "SPEC = {'op_name': 'p', 'inputs': {}, 'cases': [{'world_size': 1}],\n"
    "            'perf_baseline': perf_baseline}\n"
)
_SPEC_NO_BASELINE = "SPEC = {'op_name': 'p', 'inputs': {}, 'cases': []}\n"


def _plugin():
    plug = get_plugin("multirank")
    assert plug is not None, "multirank plugin must resolve"
    return plug


def _ws(tmp_path: Path, spec_src: str, tier: str | None = None) -> Path:
    ws = tmp_path / "mc2_op"
    ws.mkdir()
    state = {"op": "mc2_op", "opgen_mode": "port_a3_to_a5", "multirank": True}
    if tier is not None:
        from plugins.multirank import TRUTH_TIER_STATE_KEY

        state[TRUTH_TIER_STATE_KEY] = tier
    (ws / ".opgen_state.json").write_text(json.dumps(state))
    (ws / "spec.py").write_text(spec_src)
    return ws


def _gate(plug, ws, vj):
    gates = dict(plug.extra_finalize_checks())
    return gates["multirank_perf_integrity"](ws, vj)


# ---------------------------------------------------------------------------
# capture switch
# ---------------------------------------------------------------------------


def test_mc2_capture_switch_is_on():
    """G6: the finalize perf capture MUST run for multirank. The switch only

    decides whether measure_op_perf runs — the dispatch asks the plugin's
    finalize_perf_capture hook first, so the multi-rank campaign is what
    actually executes.
    """
    assert _plugin().should_run_phase_o5_perf_capture() is True
    assert callable(getattr(_plugin(), "finalize_perf_capture", None))


# ---------------------------------------------------------------------------
# multirank_perf_integrity gate
# ---------------------------------------------------------------------------
# The perf waiver obligation exists for wired truth tiers — simulated here
# by writing the tier into durable state (the provider wiring is
# irrelevant to the gate itself).


def test_perf_integrity_declared_with_ratio_passes(tmp_path):
    ws = _ws(tmp_path, _SPEC_WITH_BASELINE, tier="npubench")
    vj = {"performance": {"ratio": 2.31}}
    assert _gate(_plugin(), ws, vj) is None


def test_perf_integrity_declared_without_ratio_or_waiver_rejects(tmp_path):
    ws = _ws(tmp_path, _SPEC_WITH_BASELINE, tier="npubench")
    vj = {"performance": {"status": "N/A"}}
    reason = _gate(_plugin(), ws, vj)
    assert reason is not None
    assert "perf_baseline" in reason and ".perf_waiver" in reason


def test_perf_integrity_declared_with_waiver_passes(tmp_path):
    ws = _ws(tmp_path, _SPEC_WITH_BASELINE, tier="npubench")
    (ws / ".perf_waiver").write_text("owner: perf waived (cards busy)\n")
    assert _gate(_plugin(), ws, {"performance": {"status": "N/A"}}) is None


def test_perf_integrity_undeclared_spec_is_silent(tmp_path):
    """No perf_baseline in the spec → perf is N/A by design; the gate must not invent an obligation."""
    ws = _ws(tmp_path, _SPEC_NO_BASELINE)
    assert _gate(_plugin(), ws, {"performance": {"status": "N/A"}}) is None


def test_perf_integrity_missing_spec_is_silent(tmp_path):
    ws = tmp_path / "not_mc2"
    ws.mkdir()
    assert _gate(_plugin(), ws, {"performance": {}}) is None


# ---------------------------------------------------------------------------
# tier-aware finalize perf capture
# ---------------------------------------------------------------------------
# The real multirank_runner is NOT imported here (importing it pulls torch,
# which double-mounts under this file's sys.path setup): a fake module is
# injected into sys.modules so the plugin's lazy `from . import
# multirank_runner` binds the fake without touching the real one.


def _inject_fake_runner(monkeypatch, calls, result):
    def _run_all_groups(*args, **kwargs):
        calls.append((args, kwargs))
        return result

    class _FakeCampaignContext:
        """Attribute-bag stand-in for multirank_runner.CampaignContext."""

        def __init__(self, **kw):
            self.__dict__.update(kw)

    fake = SimpleNamespace(
        run_all_groups=_run_all_groups, CampaignContext=_FakeCampaignContext
    )
    # Patch BOTH sys.modules and the parent-package attribute: `from . import
    # multirank_runner` prefers an already-bound parent attribute over
    # sys.modules, so a modules-only injection is bypassed once any earlier
    # test imported the real runner.
    monkeypatch.setitem(sys.modules, "plugins.multirank.multirank_runner", fake)
    import plugins.multirank as _pkg

    monkeypatch.setattr(_pkg, "multirank_runner", fake, raising=False)
    return fake


def test_finalize_perf_capture_npu_tier_runs_campaign(tmp_path, monkeypatch):
    """An NPU truth tier keeps the multi-rank --perf campaign path (the

    npubench provider wiring is orthogonal to the capture itself).
    """
    ws = _ws(tmp_path, _SPEC_WITH_BASELINE, tier="npubench")
    calls = []
    _inject_fake_runner(
        monkeypatch,
        calls,
        SimpleNamespace(
            runner_error=None, unverified_world_sizes={}, perf={"ratio": 1.5}
        ),
    )
    result = _plugin().finalize_perf_capture(ws, "mc2_op")
    assert len(calls) == 1
    ctx_arg = calls[0][0][0]  # run_all_groups(CampaignContext(...), None)
    assert ctx_arg.perf is True
    assert ctx_arg.workspace == ws and ctx_arg.op == "mc2_op"
    assert result["ratio"] == 1.5


# ---------------------------------------------------------------------------
# finalize perf escalation
# ---------------------------------------------------------------------------


class _Recording:
    def __init__(self):
        self.transitions = []
        self.rollbacks = []


def _fake_capture_env(monkeypatch, tmp_path, *, captured, ratio, threshold=1.0):
    """Wire _run_perf_capture's collaborators: plugin resolution, the
    capture call, and the transition/rollback recorders."""
    ws = tmp_path / "mc2_op"
    ws.mkdir(exist_ok=True)
    vj = {"precision": {"status": "PASS"}}
    if ratio is not None:
        vj["performance"] = {"ratio": ratio, "threshold": threshold}
    else:
        vj["performance"] = {"status": "N/A"}
    (ws / "verification.json").write_text(json.dumps(vj))

    rec = _Recording()

    # Signature mirrors _capture_perf_if_requested(ctx, plugin, should, vp,
    # verification, existing); *args keeps the mock protocol-proof while the
    # body only consumes vp/verification (positions 3/4).
    def _capture(*args):
        if not captured:
            return False
        vp, verification = args[3], args[4]
        verification["performance"] = {"ratio": ratio, "threshold": threshold}
        vp.write_text(json.dumps(verification))
        return True

    monkeypatch.setattr(fpf_perf, "_perf_capture_plugin", lambda ws_: (object(), True))
    monkeypatch.setattr(fpf_perf, "_capture_perf_if_requested", _capture)
    monkeypatch.setattr(
        fpf.state_executor,
        "record_transition",
        lambda ws_, dec: rec.transitions.append(dec),
    )
    monkeypatch.setattr(
        fpf.finalize_pipeline,
        "record_rollback",
        lambda ws_, **kw: rec.rollbacks.append(kw),
    )
    ctx = SimpleNamespace(workspace=ws, lane=0, op="mc2_op")
    return ctx, rec


def test_below_threshold_capture_escalates_to_optimizer(tmp_path, monkeypatch, capsys):
    ctx, rec = _fake_capture_env(monkeypatch, tmp_path, captured=True, ratio=0.42)
    result = getattr(fpf, "_run_perf_capture")(ctx)
    assert result is not None and result.action == "continue"
    assert rec.transitions and rec.transitions[0].next_state == "await_optimizer"
    assert rec.rollbacks and rec.rollbacks[0]["gate"] == "phase_o5_perf_below_threshold"
    capsys.readouterr()
    assert "await_optimizer" in (rec.transitions[0].rationale)


def test_at_threshold_capture_does_not_route(tmp_path, monkeypatch):
    ctx, rec = _fake_capture_env(monkeypatch, tmp_path, captured=True, ratio=1.2)
    assert getattr(fpf, "_run_perf_capture")(ctx) is None
    assert not rec.transitions and not rec.rollbacks


def test_skipped_capture_never_routes(tmp_path, monkeypatch):
    """Worker self-reported perf (capture skipped) keeps its await_worker-exit

    semantics — finalize never escalates on numbers it did not measure.
    """
    ctx, rec = _fake_capture_env(monkeypatch, tmp_path, captured=False, ratio=0.3)
    monkeypatch.setattr(fpf_perf, "_relabel_worker_authored_perf", lambda *a: None)
    assert getattr(fpf, "_run_perf_capture")(ctx) is None
    assert not rec.transitions and not rec.rollbacks


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
