# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

"""FIX-4 (2026-08-20 black-box repro): O1.7 classify subprocess hardening.

The repro (moe_fused_a8w8 multirank session, 910B4): claude backend hardcoded
permission_mode=acceptEdits; in headless `--print` any non-edit tool call
(Bash ls / Read) has no approval channel and hung to the full 300s timeout
with zero output → classification always failed → kb_recommendations []
→ every later agent brief carried DEFAULT-only KB. Pinned here:
- dispatch gets bypassPermissions + effort=low + 900s default hang fuse
- timeouts are never sha-pinned (write side), and timeout-shaped pins from
  older builds are ignored (read-side self-heal — no manual cleanup)
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parent.parent))
import phase_o17_classify as o17  # noqa: E402


def _load_real_o17():
    """Fresh module instance bypassing the autouse hermetic patch (the ut
    conftest replaces o17._invoke_claude_skill with a fake for every ut
    test; these two tests pin the REAL dispatch contract)."""
    src = Path(o17.__file__)
    spec = importlib.util.spec_from_file_location("o17_fix4_real", src)
    mod = importlib.util.module_from_spec(spec)
    # register BEFORE exec: the module's @dataclass resolves cls.__module__
    # through sys.modules at decoration time
    sys.modules["o17_fix4_real"] = mod
    spec.loader.exec_module(mod)
    return mod


class _FakeEnvelope:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _FakeBackend:
    name = "claude"

    def __init__(self, envelope):
        self._envelope = envelope
        self.calls = []

    def dispatch(self, *args, **kwargs):
        self.calls.append(kwargs)
        return self._envelope


def test_invoke_dispatches_bypass_permissions_and_low_effort(tmp_path, monkeypatch):
    ws = tmp_path / "op_x"
    ws.mkdir()
    (ws / "model.py").write_text("class Model:\n    pass\n")
    real = _load_real_o17()
    fake = _FakeBackend(
        _FakeEnvelope(raw_envelope={}, output_text="ok", is_error=False)
    )
    monkeypatch.setattr(real, "_backend", fake)

    ok, stdout, stderr, timed_out = getattr(real, "_invoke_claude_skill")(
        ws, timeout=123
    )

    assert ok and not timed_out
    kwargs = fake.calls[0]
    assert kwargs["permission_mode"] == "bypassPermissions"
    assert kwargs["effort"] == "medium"
    assert kwargs["timeout"] == 123
    assert kwargs["output_format"] is None and kwargs["stdin_prompt"] is True


def test_timeout_shaped_pin_self_heals_and_reinvokes(tmp_path, monkeypatch):
    """Read-side self-heal: an error pin written by the old acceptEdits-hang

    build (timeout-shaped text) must be ignored so the op re-classifies
    without manual op_classification.error* cleanup.
    """
    ws = tmp_path / "moe_fused_a8w8"
    ws.mkdir()
    (ws / "model.py").write_text("class Model:\n    pass\n")
    cur_sha = getattr(o17, "_compute_source_sha256")(ws)
    (ws / "op_classification.error").write_text(
        "skill subprocess failed: timeout after 300s"
    )
    (ws / "op_classification.error.sha256").write_text(cur_sha)

    calls = {"n": 0}

    def fake_invoke(ws_, timeout=900):
        calls["n"] += 1
        # the real skill writes the classification file itself
        import json as _json

        (ws_ / "op_classification.json").write_text(
            _json.dumps(
                {
                    "op": "moe_fused_a8w8",
                    "op_class_tags": ["moe"],
                    "kb_recommendations": ["patterns/domains/sync_fundamentals.md"],
                    "rationale": "recovered",
                    "source_signatures_observed": [],
                    "source_sha256": cur_sha,
                }
            )
        )
        return (True, "", "", False)

    monkeypatch.setattr(o17, "_invoke_claude_skill", fake_invoke)
    result = o17.classify(ws)  # no force: must NOT short-circuit on the pin

    assert calls["n"] == 1, "timeout-shaped pin must be ignored, skill re-invoked"
    assert result.op_class_tags == ["moe"]
    assert result.error is None


def test_legacy_error_marker_is_ignored_and_skill_retried(tmp_path, monkeypatch):
    """Guard (multirank e2e finding #12): a legacy op_classification.error
    (+ .sha256) marker from older builds no longer short-circuits — the
    skill is re-invoked, so transient failures self-heal instead of pinning
    the workspace into permanently degraded classification.
    """
    ws = tmp_path / "op_y"
    ws.mkdir()
    (ws / "model.py").write_text("class Model:\n    pass\n")
    cur_sha = getattr(o17, "_compute_source_sha256")(ws)
    (ws / "op_classification.error").write_text("skill subprocess failed: exit 2")
    (ws / "op_classification.error.sha256").write_text(cur_sha)

    invoked = []

    def _fail_again(ws_, timeout=900):
        invoked.append(1)
        return (False, "", "skill subprocess failed: exit 2 (again)", False)

    monkeypatch.setattr(o17, "_invoke_claude_skill", _fail_again)
    result = o17.classify(ws)
    assert invoked == [1]  # the legacy marker did NOT short-circuit the retry
    assert "skill subprocess failed" in (result.error or "")
    assert result.op_class_tags == []
