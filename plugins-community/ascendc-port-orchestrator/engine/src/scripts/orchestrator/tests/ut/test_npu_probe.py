# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

"""Tests for npu_probe.py — the replaceable NPU-info fetch layer.

Covers: custom-command JSON contract (happy / malformed / missing-required /
rc≠0 / timeout), env precedence is the caller's (env.npu_info_cmd), the
default npu-smi path (multi-chip max-aggregate via lane_pool), idle_ids
semantics, and the minimal .ascendc_env reader inlined into this repo
(load_npu_info_cmd / ProbeEnv.from_env_file — target-first key resolution).
All subprocess calls are stubbed — hermetic.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parent.parent))

import npu_probe  # noqa: E402
from npu_probe import NpuDevice, ProbeResult  # noqa: E402
from _npu_smi_fixtures import NPU_SMI_910B4_SINGLE_CELL, NPU_SMI_910C_MULTICHIP  # noqa: E402


class _Env:
    def __init__(self, cmd=""):
        self.npu_info_cmd = cmd


def _completed(stdout="", rc=0, stderr=""):
    return subprocess.CompletedProcess(
        args=[], returncode=rc, stdout=stdout, stderr=stderr
    )


_GOOD_JSON = json.dumps(
    {
        "driver_version": "25.5.2",
        "soc": "Ascend910B4",
        "devices": [
            {
                "id": 0,
                "util_pct": 0,
                "processes": 0,
                "hbm_used_mb": 30246,
                "hbm_total_mb": 32768,
            },
            {"id": 1, "util_pct": 92, "processes": 1},
            {"id": 2, "util_pct": 3, "processes": 0},
        ],
    }
)


def test_custom_cmd_happy_path(monkeypatch):
    monkeypatch.setattr(
        npu_probe.subprocess, "run", lambda *a, **k: _completed(stdout=_GOOD_JSON)
    )
    r = npu_probe.fetch_devices(_Env("/opt/probe.sh --json"))
    assert r is not None
    assert r.source == "custom:/opt/probe.sh --json"
    assert r.driver_version == "25.5.2"
    assert r.soc == "Ascend910B4"
    assert set(r.devices) == {0, 1, 2}
    assert r.devices[0].hbm_used_mb == 30246
    assert npu_probe.idle_ids(r) == [0, 2]  # id1 busy (util 92 + a process)


def test_custom_cmd_malformed_json_returns_none(monkeypatch, capsys):
    monkeypatch.setattr(
        npu_probe.subprocess, "run", lambda *a, **k: _completed(stdout="not json")
    )
    assert npu_probe.fetch_devices(_Env("/opt/probe.sh")) is None
    assert "not valid JSON" in capsys.readouterr().err


def test_custom_cmd_missing_required_field_returns_none(monkeypatch, capsys):
    bad = json.dumps({"devices": [{"id": 0, "util_pct": 0}]})  # no processes
    monkeypatch.setattr(
        npu_probe.subprocess, "run", lambda *a, **k: _completed(stdout=bad)
    )
    assert npu_probe.fetch_devices(_Env("/opt/probe.sh")) is None
    assert "missing required field" in capsys.readouterr().err


def test_custom_cmd_nonzero_rc_returns_none_and_never_falls_back(monkeypatch):
    """A configured-but-failing custom command must NOT fall back to npu-smi

    (the custom command exists precisely where npu-smi is untrustworthy).
    The stub would happily satisfy a fallback npu-smi call, so only the
    explicit call-log assertion proves the fallback never happened.
    """
    calls: list[list[str]] = []

    def _fake_run(args, **k):
        calls.append(list(args))
        if args and args[0] == "/opt/probe.sh":
            return _completed(rc=3, stderr="boom")
        return _completed(stdout=_GOOD_JSON)  # tempting npu-smi fallback

    monkeypatch.setattr(npu_probe.subprocess, "run", _fake_run)
    assert npu_probe.fetch_devices(_Env("/opt/probe.sh")) is None
    assert calls == [["/opt/probe.sh"]]  # exactly one subprocess — no fallback


def test_custom_cmd_timeout_returns_none(monkeypatch):
    def _timeout(*a, **k):
        raise subprocess.TimeoutExpired(cmd="x", timeout=1)

    monkeypatch.setattr(npu_probe.subprocess, "run", _timeout)
    assert npu_probe.fetch_devices(_Env("/opt/probe.sh")) is None


def test_default_npu_smi_path_multichip_max_aggregate(monkeypatch):
    """910C shape: two chip rows per NPU. NPU 1 has chip0 at 88% and chip1

    idle — the NPU must report the BUSIEST chip (88), never the last row.
    """
    monkeypatch.setattr(
        npu_probe.subprocess,
        "run",
        lambda *a, **k: _completed(stdout=NPU_SMI_910C_MULTICHIP),
    )
    r = npu_probe.fetch_devices(_Env())
    assert r is not None and r.source == "npu-smi"
    assert r.devices[0].util_pct == 0
    assert r.devices[1].util_pct == 88  # max across chips, not last-row wins
    assert npu_probe.idle_ids(r) == [0]  # NPU 1 busy via its busiest chip


def test_default_npu_smi_failure_returns_none(monkeypatch):
    monkeypatch.setattr(
        npu_probe.subprocess,
        "run",
        lambda *a, **k: _completed(rc=1, stderr="no driver"),
    )
    assert npu_probe.fetch_devices(_Env()) is None


def test_default_npu_smi_binary_absent_returns_none(monkeypatch):
    """npu-smi not on PATH (OSError/FileNotFoundError — e.g. a CI runner

    without the Ascend stack): probe returns None loudly, never raises —
    the caller's fail-open/fail-loud policy decides what happens next.
    """

    def _missing(*a, **k):
        raise FileNotFoundError("[Errno 2] No such file or directory: 'npu-smi'")

    monkeypatch.setattr(npu_probe.subprocess, "run", _missing)
    assert npu_probe.fetch_devices(_Env()) is None


def test_idle_ids_threshold_and_processes():
    r = ProbeResult(
        devices={
            0: NpuDevice(id=0, util_pct=5, processes=0),  # at threshold → idle
            1: NpuDevice(id=1, util_pct=6, processes=0),  # over → busy
            2: NpuDevice(id=2, util_pct=0, processes=2),  # has procs → busy
        },
        source="test",
    )
    assert npu_probe.idle_ids(r) == [0]


def test_default_npu_smi_path_910b4_single_cell_layout(monkeypatch):
    """910B4: id+Name share one cell (no '|' between), one chip per NPU.

    Cards beyond the A5 (0,1,2) universe must be visible (valid_ids=None),
    busy-by-util and busy-by-process both excluded.
    """
    monkeypatch.setattr(
        npu_probe.subprocess,
        "run",
        lambda *a, **k: _completed(stdout=NPU_SMI_910B4_SINGLE_CELL),
    )
    r = npu_probe.fetch_devices(_Env())
    assert r is not None
    assert set(r.devices) == {0, 3, 5}
    assert r.devices[5].util_pct == 96
    assert npu_probe.idle_ids(r) == [0, 3]  # 5 busy (util 96 + process row)


# ---------------------------------------------------------------------------
# Minimal .ascendc_env reader inlined into npu_probe (this repo's
# briefs._common.AscendCEnv has no npu_info_cmd field).
# ---------------------------------------------------------------------------
def test_load_npu_info_cmd_target_specific_wins(tmp_path):
    f = tmp_path / ".ascendc_env"
    f.write_text(
        "TARGET=a3\nNPU_INFO_CMD=/gen/probe.sh\nA3_NPU_INFO_CMD=/a3/probe.sh --json\n"
    )
    assert npu_probe.load_npu_info_cmd(f) == "/a3/probe.sh --json"
    # Compound target base: a3-ds resolves the A3_* block, not A3_DS_*
    f.write_text("TARGET=a3-ds\nA3_NPU_INFO_CMD=/a3/probe.sh\n")
    assert npu_probe.load_npu_info_cmd(f) == "/a3/probe.sh"


def test_load_npu_info_cmd_generic_a5_fallback_and_absent(tmp_path):
    f = tmp_path / ".ascendc_env"
    f.write_text("TARGET=a3\nNPU_INFO_CMD=/gen/probe.sh\n")
    assert npu_probe.load_npu_info_cmd(f) == "/gen/probe.sh"  # generic
    f.write_text("TARGET=a3\nA5_NPU_INFO_CMD=/a5/probe.sh\n")
    assert npu_probe.load_npu_info_cmd(f) == "/a5/probe.sh"  # A5 fallback
    f.write_text("TARGET=a3\n# comment\n\nUNRELATED=1\n")
    assert npu_probe.load_npu_info_cmd(f) == ""  # nothing set
    assert npu_probe.load_npu_info_cmd(tmp_path / "absent") == ""  # no file


def test_load_npu_info_cmd_conflict_warns_target_wins(tmp_path, capsys):
    """DEBT-227 discipline: generic key shadowing the target-specific one is

    never silent — loud stderr warning, target-specific value returned.
    """
    f = tmp_path / ".ascendc_env"
    f.write_text(
        "TARGET=a3\n"
        'NPU_INFO_CMD="/gen/probe.sh"\n'  # quoted value must be unquoted
        "A3_NPU_INFO_CMD=/a3/probe.sh\n"
    )
    assert npu_probe.load_npu_info_cmd(f) == "/a3/probe.sh"
    err = capsys.readouterr().err
    assert "DIFFER" in err
    assert "A3_NPU_INFO_CMD" in err and "NPU_INFO_CMD" in err


def test_probe_env_from_env_file(tmp_path):
    f = tmp_path / ".ascendc_env"
    f.write_text("TARGET=a5\nNPU_INFO_CMD=/opt/probe.sh --json\n")
    env = npu_probe.ProbeEnv.from_env_file(f)
    assert env.npu_info_cmd == "/opt/probe.sh --json"
    # An empty carrier behaves like None → default npu-smi path
    assert npu_probe.ProbeEnv().npu_info_cmd == ""


def test_probe_result_from_smi_text_shared_parser():
    """The shared smi-text parser feeds BOTH the local default path and the
    remote endpoint probe — same parse, same idle verdict (no per-call-site
    re-derivation of the idle criteria).
    """
    r = npu_probe.probe_result_from_smi_text(NPU_SMI_910C_MULTICHIP)
    assert r is not None and r.source == "npu-smi"
    assert r.devices[0].util_pct == 0
    assert r.devices[1].util_pct == 88  # max across chips, not last-row wins
    assert npu_probe.idle_ids(r) == [0]
    # zero devices parses to None (caller decides the error wording)
    assert npu_probe.probe_result_from_smi_text("") is None


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
