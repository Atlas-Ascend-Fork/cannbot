# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------
"""310B remote-target routing.

A 310B destination keeps the generic HOST/CONTAINER semantics — SSH
transport for remote endpoints, host-direct for CONTAINER=local on a remote
host, docker exec for a real container.

Pins: 1) the host-locality predicates and their deployment table; 2) target
resolution for the remote form; 3) the O5 runners take SSH for remote
targets and keep the localhost-local path; 4) resync extracts host-direct
for CONTAINER=local, docker for containers.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parent.parent))
import phase_o5  # noqa: E402,F401  (MeasuredResult + import-cycle order)
import phase_o5_runner  # noqa: E402
import phase_o5_verify  # noqa: E402
from a5_target_transport import (  # noqa: E402
    A5TargetTransportError,
    _resolve_target,
    host_direct_mode,
    is_local_host,
)
from phase_o5 import MeasuredResult  # noqa: E402

_BOARD = "310b-board"
# Module-private seams, bound once via getattr (convention above).
_publish_resync_tar = getattr(phase_o5_runner, "_publish_resync_tar")
_build_remote_verifier_command = getattr(phase_o5_verify, "_build_remote_verifier_command")
_build_remote_canonical_command = getattr(phase_o5_verify, "_build_remote_canonical_command")


_310B_REMOTE_ENV = (
    "TARGET=310b\n"
    f"ASCEND310B_HOST={_BOARD}\n"
    "ASCEND310B_USER=root\n"
    "ASCEND310B_PASSWORD=redacted-ut\n"
    "ASCEND310B_CONTAINER=local\n"
    "ASCEND310B_CANN_PATH=/usr/local/Ascend/ascend-toolkit/latest\n"
    "ASCEND310B_SOC_VERSION=Ascend310B1\n"
    "BENCHMARK_ROOT=/root/AscendOpGenAgent\n"
)


@pytest.fixture(autouse=True)
def _no_env_file_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep .ascendc_env resolution deterministic (workspace-relative only)."""
    monkeypatch.delenv("ASCENDC_ENV_PATH", raising=False)
    monkeypatch.delenv("ASCENDC_ENV_FILE", raising=False)


def _seed(ws: Path, env_text: str, scripts: tuple[str, ...] = ()) -> Path:
    ws.mkdir(parents=True, exist_ok=True)
    for name in scripts:
        (ws / name).write_text(f"# {name} stub\n")
    (ws.parent / ".ascendc_env").write_text(env_text)
    return ws


# ---------------------------------------------------------------------------
# 1) Pure predicates — the deployment table
# ---------------------------------------------------------------------------
def test_is_local_host_spellings() -> None:
    for host in ("", "localhost", "127.0.0.1", "::1", "[::1]", "LOCALHOST", " LocalHost "):
        assert is_local_host(host) is True, host


def test_is_local_host_remote_board_is_not_local() -> None:
    assert is_local_host(_BOARD) is False
    assert is_local_host("board-host") is False
    assert is_local_host(None) is False
    assert is_local_host(123) is False


def test_host_direct_mode_deployment_table() -> None:
    # Remote bare-metal (the 310B board form): host-direct, no docker exec.
    assert host_direct_mode({}, _BOARD, "local") is True
    # Legacy controller-as-target: CONTAINER=local on a controller-named host.
    assert host_direct_mode({}, "", "local") is False
    assert host_direct_mode({}, "localhost", "local") is False
    # Remote host with a REAL container keeps the docker-exec transport.
    assert host_direct_mode({}, _BOARD, "npu_dev3") is False
    # A5_HOST_MODE remains an explicit opt-in for any deployment.
    assert host_direct_mode({"A5_HOST_MODE": "1"}, "", "npu_dev3") is True
    assert host_direct_mode({"A5_HOST_MODE": "YES"}, "localhost", "local") is True
    assert host_direct_mode({"A5_HOST_MODE": "0"}, _BOARD, "local") is True  # bare-metal derivation


# ---------------------------------------------------------------------------
# 2) _resolve_target — remote-form resolution
# ---------------------------------------------------------------------------
def test_resolve_target_310b_remote_baremetal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ws = _seed(tmp_path / "op", _310B_REMOTE_ENV)
    # Remote targets use O5's health-aware device routing; pin it away from SSH.
    monkeypatch.setattr(
        phase_o5_runner, "resolve_healthy_device", lambda lane, host, user: (lane, "pinned-in-ut")
    )
    target = _resolve_target(ws, 2)
    assert target.name == "ASCEND310B"
    assert target.host == _BOARD
    assert target.container == "local"
    assert target.host_mode is True
    assert target.visible_device == 2


def test_resolve_target_a5_local_container_stays_controller_local(tmp_path: Path) -> None:
    # Legacy a5: CONTAINER=local with no host IS the controller as target —
    # no gate, no host-direct mode, lane used as the visible device directly.
    ws = _seed(tmp_path / "op", "TARGET=a5\nA5_CONTAINER=local\nCANN_PATH=/test/cann\n")
    target = _resolve_target(ws, 1)
    assert target.container == "local"
    assert target.host_mode is False
    assert target.visible_device == 1


def test_host_direct_commands_use_health_resolved_visible_device(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        phase_o5_verify, "_resolve_visible_device", lambda env, workspace, lane: 1
    )
    target = SimpleNamespace(
        name="ASCEND310B",
        host=_BOARD,
        container="local",
        cann_path="/usr/local/Ascend/ascend-toolkit/latest",
    )
    verifier, host_mode = _build_remote_verifier_command(
        Path("/tmp/ut_op"), {}, target, "/root/AscendOpGenAgent", "run_pass_b.py", 0
    )
    canonical, canonical_host_mode = _build_remote_canonical_command(
        Path("/tmp/ut_op"), {}, target, "/root/AscendOpGenAgent",
        "demo", "precision_eval_two_tier.py", "", 0,
    )
    assert host_mode is True and canonical_host_mode is True
    for command in (verifier, canonical):
        assert "export ASCEND_RT_VISIBLE_DEVICES=1" in command
        assert "export ASCEND_RT_VISIBLE_DEVICES=0" not in command


# ---------------------------------------------------------------------------
# 3) O5 runners — remote bare-metal takes SSH; localhost keeps local
# ---------------------------------------------------------------------------
def _forbid_local_path(*args: object, **kwargs: object) -> None:
    raise AssertionError("remote bare-metal must not run the controller-local verifier path")


def test_ssh_runner_remote_baremetal_takes_ssh_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = _seed(tmp_path / "op", _310B_REMOTE_ENV, scripts=("run_pass_b.py",))
    monkeypatch.setattr(phase_o5_runner, "_run_verifier_local", _forbid_local_path)
    monkeypatch.setattr(
        phase_o5_runner, "_resync_workspace_to_container", lambda ws_, env_, lane=0: None
    )
    sentinel = MeasuredResult(pass_a={"tier1_pass": 1, "total": 1, "status": "PASS"})
    monkeypatch.setattr(phase_o5_runner, "_measure_ssh_verifiers", lambda *a, **k: sentinel)
    result = phase_o5_runner.ssh_runner(ws, "op", lane=0)
    assert result is sentinel


def test_ssh_runner_localhost_local_container_keeps_local_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Controller-named host + local container: verifier stays local.
    ws = _seed(
        tmp_path / "op",
        "TARGET=a5\nA5_CONTAINER=local\nCANN_PATH=/test/cann\n",
        scripts=("run_pass_b.py",),
    )
    sentinel = MeasuredResult(pass_a={"tier1_pass": 1, "total": 1, "status": "PASS"})
    monkeypatch.setattr(phase_o5_runner, "_run_verifier_local", lambda *a, **k: sentinel)
    monkeypatch.setattr(
        phase_o5_runner, "_measure_ssh_verifiers", _forbid_local_path
    )
    result = phase_o5_runner.ssh_runner(ws, "op", lane=0)
    assert result is sentinel


# ---------------------------------------------------------------------------
# 4) O5 resync — host-direct extraction for bare-metal, docker for container
# ---------------------------------------------------------------------------
def _capture_remote_commands(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    commands: list[list[str]] = []

    def _fake_run(argv, **_kwargs):
        commands.append(list(argv))
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(phase_o5_runner.subprocess, "run", _fake_run)
    return commands


def _publish(monkeypatch: pytest.MonkeyPatch, env: dict, host: str, container: str) -> str:
    ws = Path("/tmp/ut_op")
    commands = _capture_remote_commands(monkeypatch)
    error = _publish_resync_tar(
        "/tmp/ut_resync.tar",
        ws,
        env,
        "ASCEND310B" if env.get("TARGET") == "310b" else "A5",
        host,
        "root",
        "",
        container,
        "/root/AscendOpGenAgent",
        push_files=[],
        force_update_scripts=set(),
        forced_json=set(),
        instrument_files=[],
        instrument_dirs=[],
    )
    assert error is None
    assert commands, "expected one scp + one ssh command"
    # First command uploads via scp; the second ssh command extracts remotely.
    assert commands[0][0] == "scp"
    assert commands[1][0] == "ssh"
    return commands[1][-1]


def test_resync_publish_baremetal_extracts_host_direct(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    remote = _publish(
        monkeypatch,
        {"TARGET": "310b", "ASCEND310B_CONTAINER": "local"},
        _BOARD,
        "local",
    )
    assert "tar --skip-old-files" in remote
    assert "docker" not in remote  # host-direct: no docker cp / docker exec hop


def test_resync_publish_container_target_keeps_docker_transport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    remote = _publish(monkeypatch, {"TARGET": "a5"}, _BOARD, "npu_dev3")
    assert "docker cp" in remote
    assert "docker exec npu_dev3" in remote
    assert "tar --skip-old-files" in remote
