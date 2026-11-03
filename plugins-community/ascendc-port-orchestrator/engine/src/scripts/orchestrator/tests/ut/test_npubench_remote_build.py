# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------
"""Controlled remote candidate build identity checks."""
from __future__ import annotations

import hashlib
import subprocess
import sys
import tarfile
from pathlib import Path

import _reorg_paths  # noqa: F401
import pytest

from npubench import npubench_target as target

# Bind module-private seams once via getattr for the protected-access checker.
_Target = getattr(target, "_Target")
_ControlledBuild = getattr(target, "_ControlledBuild")
_candidate_source_digest = getattr(target, "_candidate_source_digest")
_authored_cmake_sha256 = getattr(target, "_authored_cmake_sha256")
_run_remote_direct_build = getattr(target, "_run_remote_direct_build")


def _run_remote_build(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    build_command: str,
    *,
    staged_mutation: str | None = None,
    python: str = sys.executable,
) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    workspace = tmp_path / "controller-workspace"
    kernel = workspace / "kernel"
    kernel.mkdir(parents=True)
    (workspace / "model_new_ascendc.py").write_text("MODEL = 'original'\n")
    (kernel / "CMakeLists.txt").write_text("project(original)\n")
    script = tmp_path / "build.py"
    script.write_text("# controlled build placeholder\n")
    board = tmp_path / "board"
    endpoint = _Target(
        name="310b",
        host="board.invalid",
        user="tester",
        password="",
        container="local",
        cann_path="/unused",
        benchmark_root=str(board),
        host_mode=True,
        visible_device=0,
        ssh_options=(),
        env={"ASCEND310B_PYTHON": python},
    )
    build = _ControlledBuild(
        workspace=workspace,
        contract={},
        source_kind=None,
        attempt="0" * 32,
        state={},
        target=endpoint,
        candidate_digest=_candidate_source_digest(workspace),
        authored_cmake_sha256=_authored_cmake_sha256(workspace),
    )
    token = hashlib.sha256(str(tmp_path).encode()).hexdigest()[:32]
    remote_root = board / "cannbot_build" / token
    remote_result = Path(f"/tmp/cannbot_build_result_{token}.tar")
    scratch: list[Path] = []

    def upload(stage: Path, actual_root: str, remote_stage: str, _endpoint) -> None:
        scratch.extend((stage, Path(remote_stage)))
        Path(actual_root).mkdir(parents=True)
        with tarfile.open(stage) as archive:
            archive.extractall(actual_root)
        if staged_mutation is not None:
            (Path(actual_root) / staged_mutation).write_text("staged mutation\n")

    def run_remote(_endpoint, command: str, **_kwargs):
        return subprocess.run(
            ["/bin/bash", "-c", command], capture_output=True, text=True, check=False
        )

    monkeypatch.setattr(target.uuid, "uuid4", lambda: type("Token", (), {"hex": token})())
    monkeypatch.setattr(target, "_upload_and_extract_remote_stage", upload)
    monkeypatch.setattr(target, "_run_remote_build_step", run_remote)
    monkeypatch.setattr(target, "_fetch_remote_build_result", lambda *_args: None)
    monkeypatch.setattr(target, "_cleanup_remote_build_side_effects", lambda *_args: None)
    try:
        completed = _run_remote_direct_build(build, build_command, script, 30)
    finally:
        remote_result.unlink(missing_ok=True)
        for path in scratch:
            path.unlink(missing_ok=True)
    return completed, workspace, remote_root


@pytest.mark.parametrize(
    "authored_path", ["workspace/model_new_ascendc.py", "workspace/kernel/CMakeLists.txt"]
)
def test_remote_build_rejects_candidate_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, authored_path: str
) -> None:
    completed, workspace, _ = _run_remote_build(
        tmp_path,
        monkeypatch,
        f"printf changed > {authored_path}; mkdir -p workspace/kernel/build",
    )

    assert completed.returncode != 0
    assert "remote authored candidate or CMake changed" in completed.stderr
    assert not (workspace / "kernel" / "build").exists()


def test_remote_build_rejects_staged_input_that_differs_from_bound_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    completed, _, remote_root = _run_remote_build(
        tmp_path,
        monkeypatch,
        "mkdir -p workspace/kernel/build",
        staged_mutation="workspace/model_new_ascendc.py",
    )

    assert completed.returncode != 0
    assert "does not match the controlled candidate before build" in completed.stderr
    assert not (remote_root / "workspace" / "kernel" / "build").exists()


def test_remote_build_digest_failure_is_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    completed, _, remote_root = _run_remote_build(
        tmp_path,
        monkeypatch,
        "mkdir -p workspace/kernel/build",
        python=str(tmp_path / "missing-python"),
    )

    assert completed.returncode != 0
    assert not (remote_root / "workspace" / "kernel" / "build").exists()


def test_remote_build_imports_artifacts_when_candidate_is_stable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    completed, workspace, _ = _run_remote_build(
        tmp_path,
        monkeypatch,
        "mkdir -p workspace/kernel/build; printf artifact > workspace/kernel/build/result.txt",
    )

    assert completed.returncode == 0, completed.stderr
    assert (workspace / "kernel" / "build" / "result.txt").read_text() == "artifact"
