# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License).
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

"""Unit tests for the npubench collector's CLI dispatch (main).

The collector runs as a subprocess on the NPU endpoint; these tests pin the
arg-parsing and dispatch contract only — torch/torch_npu are faked via
sys.modules, the spec loader and the collection paths are monkeypatched, so
no NPU is touched.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import multirank_npu_bench_collect as mc  # noqa: E402


@pytest.fixture
def fake_torch(monkeypatch):
    """Inject a fake torch/torch_npu pair; torch.load returns the case payload."""
    payload = {"idx": 1, "name": "case1", "world_size": 2, "mode": "task"}
    fake = SimpleNamespace(load=lambda p, weights_only=False: payload)
    monkeypatch.setitem(sys.modules, "torch", fake)
    monkeypatch.setitem(sys.modules, "torch_npu", SimpleNamespace())
    return payload


def _argv(monkeypatch, *args):
    monkeypatch.setattr(sys, "argv", ["multirank_npu_bench_collect.py", *args])


def test_usage_error_without_three_positional_args(monkeypatch, caplog):
    _argv(monkeypatch, "spec.py", "in.pt")
    assert mc.main() == 2
    assert "usage:" in caplog.text


def test_rank_flag_routes_to_rank_process(monkeypatch, fake_torch, tmp_path):
    _argv(
        monkeypatch,
        str(tmp_path / "spec.py"),
        str(tmp_path / "in.pt"),
        str(tmp_path / "out.pt"),
        "--rank",
        "3",
        "--wrapper",
        str(tmp_path / "w.py"),
    )
    recorded = {}

    def _fake_run_rank(spec):
        recorded["spec"] = spec
        return 9

    monkeypatch.setattr(mc, "_run_rank_task_process", _fake_run_rank)
    assert mc.main() == 9
    spec = recorded["spec"]
    assert spec.rank == 3
    assert spec.wrapper_path == str(tmp_path / "w.py")
    assert spec.spec_path == tmp_path / "spec.py"


def test_non_task_spec_form_refused(monkeypatch, fake_torch, tmp_path):
    _argv(
        monkeypatch,
        str(tmp_path / "spec.py"),
        str(tmp_path / "in.pt"),
        str(tmp_path / "out.pt"),
    )
    monkeypatch.setattr(
        mc,
        "_load_spec",
        lambda p: SimpleNamespace(SPEC={"input_mode": "derived"}),
    )
    assert mc.main() == 4


def test_needs_ep_comm_routes_to_multiproc(monkeypatch, fake_torch, tmp_path):
    _argv(
        monkeypatch,
        str(tmp_path / "spec.py"),
        str(tmp_path / "in.pt"),
        str(tmp_path / "out.pt"),
        "--wrapper",
        str(tmp_path / "w.py"),
    )
    monkeypatch.setattr(
        mc,
        "_load_spec",
        lambda p: SimpleNamespace(
            SPEC={"input_mode": "task_generated", "needs_ep_comm": True}
        ),
    )
    recorded = {}

    def _fake_multiproc(torch, me, spec_path, payload, out_path):
        recorded["args"] = (me, spec_path, payload, out_path)
        return 7

    monkeypatch.setattr(mc, "_collect_task_multiproc", _fake_multiproc)
    assert mc.main() == 7
    _me, _spec, payload, _out = recorded["args"]
    assert payload["wrapper_path"] == str(tmp_path / "w.py")
    assert payload["_in_path"] == str(tmp_path / "in.pt")


def test_sequential_form_routes_to_sequential(monkeypatch, fake_torch, tmp_path):
    _argv(
        monkeypatch,
        str(tmp_path / "spec.py"),
        str(tmp_path / "in.pt"),
        str(tmp_path / "out.pt"),
    )
    mod = SimpleNamespace(SPEC={"input_mode": "task_generated"})
    monkeypatch.setattr(mc, "_load_spec", lambda p: mod)
    recorded = {}

    def _fake_seq(torch, m, payload, out_path):
        recorded["call"] = (m, payload, out_path)
        return 0

    monkeypatch.setattr(mc, "_collect_task_sequential", _fake_seq)
    assert mc.main() == 0
    assert recorded["call"][0] is mod


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
