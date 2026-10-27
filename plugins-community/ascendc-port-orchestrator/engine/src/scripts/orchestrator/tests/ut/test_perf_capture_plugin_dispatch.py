# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

"""Plugin dispatch wiring for the engine perf capture (`finalize_perf_capture`).

Pins the three-arm dispatch contract added at the engine perf-capture call
point (`phase_o5_perf_capture.measure_op_perf` + `fsm_phase_finalize`):

1. A plugin that OVERRIDES `BasePlugin.finalize_perf_capture` and returns a
   dict short-circuits the measurement — the returned dict IS the perf
   result and the default symmetric single-process path never runs.
2. A plugin returning None (the BasePlugin default; port_a3 / backward do
   not override) keeps the engine default path exactly as before.
3. The resource-shortage sentinel (status == "PAUSE_RESOURCE" + reason)
   never writes a performance fragment — it pauses the finalize FSM at
   await_user_decision for the user instead of failing the run or bouncing
   a worker that cannot free the occupied resource.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[2]))  # …/orchestrator
sys.path.insert(0, str(_HERE.parents[2] / "plugins"))  # plugins package

import events  # noqa: E402
import fsm_phase_finalize as fpf  # noqa: E402
import phase_o5_perf_capture  # noqa: E402
import state_executor  # noqa: E402
import finalize_pipeline  # noqa: E402
from fsm_context import HandlerResult, OrchestratorContext  # noqa: E402
from plugins.base import BasePlugin  # noqa: E402


PLUGIN_CAPTURED = {
    "method": "plugin-owned joint-metric measurement",
    "status": "PASS",
    "ratio": 1.8,
}


class _CapturePlugin(BasePlugin):
    """Fake paradigm plugin whose perf capture the symmetric engine path
    cannot express — it takes over the measurement via the hook."""

    name = "joint_metric"

    def __init__(self, result):
        self._result = result
        self.calls: list[tuple[Path, str]] = []

    def finalize_perf_capture(self, workspace: Path, op: str):
        self.calls.append((workspace, op))
        return self._result


@pytest.fixture
def default_path_spies(monkeypatch):
    """Record (and stub out) every entry into the default symmetric path."""
    calls: list[str] = []
    monkeypatch.setattr(
        phase_o5_perf_capture,
        "_candidate_filename_for",
        lambda *a, **k: (calls.append("candidate"), "model_new_ascendc.py")[1],
    )
    monkeypatch.setattr(
        phase_o5_perf_capture,
        "_measure_local",
        lambda **k: (calls.append("measure"), ([10.0] * 5, [5.0] * 5))[1],
    )
    return calls


def _ws(tmp_path: Path) -> Path:
    ws = tmp_path / "op"
    ws.mkdir()
    (ws / "model.py").write_text("# reference\n")
    (ws / "model_new_ascendc.py").write_text("# candidate\n")
    return ws


# ---------------------------------------------------------------------------
# 1. Plugin returns a dict → short-circuit, default path untouched
# ---------------------------------------------------------------------------


def test_plugin_dict_short_circuits_measure_op_perf(tmp_path, default_path_spies):
    """The hook's dict is returned verbatim and the symmetric engine path

    (candidate resolution + local subprocess measure) never runs.
    """
    ws = _ws(tmp_path)
    plugin = _CapturePlugin(dict(PLUGIN_CAPTURED))

    result = phase_o5_perf_capture.measure_op_perf("op", ws, plugin=plugin)

    assert result["status"] == "PASS"
    assert result["ratio"] == 1.8
    assert result["method"] == PLUGIN_CAPTURED["method"]
    assert plugin.calls == [(ws, "op")]
    assert default_path_spies == [], (
        "default symmetric path ran despite plugin override"
    )


def test_base_plugin_default_returns_none(tmp_path):
    """BasePlugin's neutral default is None (not overridden → engine default)."""
    assert BasePlugin().finalize_perf_capture(tmp_path, "op") is None


def test_existing_plugins_do_not_override_the_hook():
    """backward must not override finalize_perf_capture — its finalize perf

    behavior stays byte-for-byte the pre-wiring default. port_a3_to_a5 DOES
    override it as a CONDITIONAL delegation (multirank workspaces → the
    extension's multi-NPU campaign; single-card → super()/engine default),
    pinned by plugins/port_a3/tests/test_port_a3_plugin.py.
    """
    from plugins.backward import BackwardPlugin

    assert "finalize_perf_capture" not in vars(BackwardPlugin), (
        "BackwardPlugin now overrides finalize_perf_capture — "
        "the no-override behavior guarantee regressed"
    )


# ---------------------------------------------------------------------------
# 2. Plugin returns None → default path runs unchanged
# ---------------------------------------------------------------------------


def test_plugin_none_runs_default_path(tmp_path, default_path_spies):
    """Hook returns None → engine default: candidate resolved + symmetric

    samples measured + ratio/status built exactly as before the wiring.
    """
    ws = _ws(tmp_path)
    plugin = _CapturePlugin(None)

    result = phase_o5_perf_capture.measure_op_perf("op", ws, plugin=plugin)

    assert default_path_spies == ["candidate", "measure"]
    assert result["status"] == "PASS"  # median 10.0 / median 5.0
    assert result["ratio"] == 2.0
    assert result["phase_o5_perf_capture_version"] == phase_o5_perf_capture.VERSION


# ---------------------------------------------------------------------------
# 3. PAUSE_RESOURCE → FSM pauses at await_user_decision (no perf written)
# ---------------------------------------------------------------------------


class _PauseObservers:
    def __init__(self):
        self.transitions: list = []
        self.rollbacks: list[dict] = []
        self.events: list[tuple] = []


@pytest.fixture
def pause_observers(monkeypatch):
    """Capture the pause side-effect seams (transition / rollback / event)."""
    obs = _PauseObservers()
    monkeypatch.setattr(
        state_executor,
        "record_transition",
        lambda ws, dec: obs.transitions.append(dec),
    )
    monkeypatch.setattr(
        finalize_pipeline,
        "record_rollback",
        lambda ws, **kw: (obs.rollbacks.append(kw), {})[1],
    )
    monkeypatch.setattr(
        events,
        "emit",
        lambda ws, name, **kw: obs.events.append((name, kw)),
    )
    return obs


def _verification(ws: Path, perf: dict) -> None:
    (ws / "verification.json").write_text(
        json.dumps(
            {
                "precision": {"status": "PASS"},
                "performance": perf,
            },
            indent=2,
        )
    )


def _ctx(ws: Path) -> OrchestratorContext:
    return OrchestratorContext(op="op", workspace=ws, lane=0)


def _activate_plugin(monkeypatch, plugin):
    monkeypatch.setattr(
        finalize_pipeline,
        "_get_active_plugin",
        lambda _ws: plugin,
    )
    monkeypatch.delenv("AOG_PERF_CAPTURE_OVERRIDE_WORKER", raising=False)


def test_pause_resource_pauses_fsm_and_keeps_performance(
    monkeypatch,
    tmp_path,
    pause_observers,
    default_path_spies,
):
    """PAUSE_RESOURCE: no performance fragment is written; the FSM records a

    finalize→await_user_decision pause (infra-class) with the plugin reason —
    never a failure return and never a worker respawn.
    """
    ws = tmp_path / "op"
    ws.mkdir()
    worker_perf = {"status": "PASS", "ratio": None, "method": "worker timing"}
    _verification(ws, worker_perf)  # ratio None → capture is requested
    plugin = _CapturePlugin(
        {
            "status": "PAUSE_RESOURCE",
            "reason": "all measurement cards are occupied by another campaign",
        }
    )
    _activate_plugin(monkeypatch, plugin)

    result = getattr(fpf, "_run_perf_capture")(_ctx(ws))

    assert isinstance(result, HandlerResult)
    assert result.action == "continue"
    # Default symmetric path never ran; the pause came from the plugin hook.
    assert default_path_spies == []
    assert plugin.calls == [(ws, "op")]
    # No performance fragment written — verification.json is untouched.
    vj = json.loads((ws / "verification.json").read_text())
    assert vj["performance"] == worker_perf
    assert "PAUSE_RESOURCE" not in json.dumps(vj)
    # FSM pause: finalize → await_user_decision, tagged infra (free re-entry).
    assert [d.next_state for d in pause_observers.transitions] == [
        "await_user_decision"
    ]
    assert pause_observers.transitions[0].from_state == "finalize"
    assert pause_observers.transitions[0].rollback_kind == "infra"
    assert "occupied" in pause_observers.transitions[0].rationale
    assert pause_observers.rollbacks[0]["rollback_state"] == "await_user_decision"
    assert pause_observers.rollbacks[0]["gate"] == "phase_o5_perf_capture"
    pause_events = [
        e
        for e in pause_observers.events
        if e[0] == "orchestrator.phase_o5_perf_capture_pause"
    ]
    assert len(pause_events) == 1
    assert "occupied" in pause_events[0][1]["data"]["reason"]
    assert pause_events[0][1]["data"]["pause_target"] == "await_user_decision"


def test_handle_finalize_short_circuits_on_pause(
    monkeypatch,
    tmp_path,
    pause_observers,
    default_path_spies,
):
    """The pause must short-circuit handle_finalize BEFORE finalize prep /

    eligibility / promotion — those would gate a half-measured archive.
    """
    ws = tmp_path / "op"
    ws.mkdir()
    _verification(ws, {"status": "PASS", "ratio": None})
    plugin = _CapturePlugin(
        {
            "status": "PAUSE_RESOURCE",
            "reason": "measurement cards busy",
        }
    )
    _activate_plugin(monkeypatch, plugin)
    monkeypatch.setattr(fpf, "_o5_post_verify", lambda *_: None)
    after_pause: list[str] = []
    monkeypatch.setattr(
        fpf,
        "_run_finalize_prep",
        lambda *_: (after_pause.append("prep"), None)[1],
    )

    class _Snap:
        iter_counts: dict = {}

    result = fpf.handle_finalize(_ctx(ws), _Snap())

    assert result.action == "continue"
    assert after_pause == [], "finalize prep ran after a resource pause"
    assert [d.next_state for d in pause_observers.transitions] == [
        "await_user_decision"
    ]
    assert default_path_spies == []


def test_plugin_dict_is_used_as_perf_result_at_finalize(
    monkeypatch,
    tmp_path,
    pause_observers,
    default_path_spies,
):
    """A non-sentinel plugin dict flows through the finalize merge exactly

    like an engine-measured result: written into verification.performance
    with the orchestrator independent_re_measure stamp.
    """
    import perf_irm_provenance

    ws = tmp_path / "op"
    ws.mkdir()
    _verification(ws, {"status": "PASS", "ratio": None})
    plugin = _CapturePlugin(dict(PLUGIN_CAPTURED))
    _activate_plugin(monkeypatch, plugin)

    result = getattr(fpf, "_run_perf_capture")(_ctx(ws))

    assert result is None  # normal best-effort path — no pause
    assert default_path_spies == []
    vj = json.loads((ws / "verification.json").read_text())
    assert vj["performance"]["ratio"] == 1.8
    assert vj["performance"]["method"] == PLUGIN_CAPTURED["method"]
    irm = vj["performance"]["independent_re_measure"]
    assert perf_irm_provenance.is_orchestrator_measured(irm)
    capture_events = [
        e
        for e in pause_observers.events
        if e[0] == "orchestrator.phase_o5_perf_capture"
    ]
    assert len(capture_events) == 1
    assert capture_events[0][1]["data"]["status"] == "PASS"


def test_pause_only_when_capture_actually_ran(
    monkeypatch,
    tmp_path,
    pause_observers,
    default_path_spies,
):
    """A worker-authored ratio suppresses the capture → the plugin hook is

    never invoked and the worker's self-report is only relabelled (existing
    default behavior preserved on the no-capture arm).
    """
    ws = tmp_path / "op"
    ws.mkdir()
    worker_perf = {
        "status": "PASS",
        "ratio": 2.7,
        "independent_re_measure": {"ran": True, "ratio": 2.7},
    }
    _verification(ws, worker_perf)
    plugin = _CapturePlugin(
        {
            "status": "PAUSE_RESOURCE",
            "reason": "should never be consulted",
        }
    )
    _activate_plugin(monkeypatch, plugin)

    result = getattr(fpf, "_run_perf_capture")(_ctx(ws))

    assert result is None
    assert plugin.calls == []
    vj = json.loads((ws / "verification.json").read_text())
    assert vj["performance"]["ratio"] == 2.7
    assert pause_observers.transitions == []
