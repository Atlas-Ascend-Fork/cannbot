# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SCRIPT = ROOT / "scripts" / "preflight_dependencies.py"
SKILL = ROOT / "skills" / "ops-perf-optimize-workflow" / "SKILL.md"
CONTRACT = (
    ROOT
    / "skills"
    / "ops-perf-optimize-workflow"
    / "references"
    / "workflow-contract.md"
)

SPEC = importlib.util.spec_from_file_location("preflight_dependencies", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_plugin_scripts_all_present() -> None:
    for name in MODULE.PLUGIN_SCRIPTS:
        assert (ROOT / "scripts" / name).is_file(), name


def test_check_plugin_scripts_detects_missing_script() -> None:
    report = MODULE.Report()
    with mock.patch.object(MODULE, "PLUGIN_SCRIPTS", ("definitely_missing.py",)):
        MODULE.check_plugin_scripts(report)
    assert report.checks[0]["status"] == "fail"


def test_check_python_env_fails_fast_on_missing_executable() -> None:
    report = MODULE.Report()
    MODULE.check_python_env(report, "/nonexistent/python3", "true")
    assert report.status == "fail"
    assert any("executable not found" in check["detail"] for check in report.checks)


def test_check_cann_flags_incomplete_install_as_warn_when_libs_exist() -> None:
    import tempfile

    report = MODULE.Report()
    with tempfile.TemporaryDirectory() as temporary:
        home = Path(temporary) / "cann-9.1.0"
        lib64 = home / "x86_64-linux" / "lib64"
        (home / "compiler").mkdir(parents=True)
        lib64.mkdir(parents=True)
        (home / "compiler" / "version.info").write_text(
            "Version=9.1.0\ntimestamp=20260610\n", encoding="utf-8"
        )
        (lib64 / "libopapi_oam.so").write_bytes(b"\x7fELF-fake")

        def fake_run_shell(command, timeout=120):
            if "ASCEND_HOME_PATH" in command:
                return 0, str(home)
            if "command -v" in command:
                return 0, f"/fake/bin/{command.rsplit(' ', 1)[-1]}"
            if command.startswith("nm -D "):
                return 1, ""  # no warmup symbols anywhere
            return 1, ""

        with mock.patch.object(MODULE, "run_shell", side_effect=fake_run_shell):
            MODULE.check_cann(report, "source /x/setenv.bash")

    statuses = {check["name"]: check["status"] for check in report.checks}
    assert statuses["warmup-symbols"] == "warn"
    assert "incomplete install" in next(
        check["detail"] for check in report.checks if check["name"] == "warmup-symbols"
    )
    assert report.status == "warn"


def test_check_device_busy_is_warn_not_fail() -> None:
    report = MODULE.Report()
    with (
        mock.patch.object(MODULE.glob, "glob", return_value=["/dev/davinci0"]),
        mock.patch.object(
            MODULE,
            "run_shell",
            return_value=(1, "aclError 507033 device occupied"),
        ),
    ):
        MODULE.check_device(report, sys.executable, "true", 0)
    statuses = {check["name"]: check["status"] for check in report.checks}
    assert statuses["device-init"] == "warn"
    assert report.status == "warn"


def test_report_status_and_exit_semantics() -> None:
    report = MODULE.Report()
    report.add("a", "g", "ok", "fine")
    assert report.status == "pass"
    report.add("b", "g", "warn", "meh")
    assert report.status == "warn"
    report.add("c", "g", "fail", "broken")
    assert report.status == "fail"
    summary = report.summary()
    assert summary["fail_count"] == 1 and summary["warn_count"] == 1


def test_baseline_owns_preflight_and_orchestrator_enforces_gate() -> None:
    baseline = (
        ROOT / "skills/ops-perf-baseline-evaluate/references/input-freezing.md"
    ).read_text()
    assert (
        "input-freezing.md"
        in (ROOT / "skills/ops-perf-baseline-evaluate/SKILL.md").read_text()
    )
    assert "环境有 fail 时禁止 freeze" in CONTRACT.read_text()
    assert (
        0
        < baseline.index("create-request")
        < baseline.index("preflight_dependencies.py")
        < baseline.index("freeze --request")
    )


def test_operator_subdirectory_keeps_scope_and_discovers_repository_build(
    tmp_path,
) -> None:
    (tmp_path / ".git").write_text("gitdir: /a/worktree\n")
    (tmp_path / "build.sh").write_text("#!/bin/sh\n")
    operator = tmp_path / "ops" / "example"
    operator.mkdir(parents=True)
    report = MODULE.Report()
    with mock.patch.object(MODULE, "run_shell", return_value=(0, "/bin/tool")):
        MODULE.check_build(report, operator)
    assert report.status == "warn"
    entry = next(check for check in report.checks if check["name"] == "build-entry")
    assert str(tmp_path / "build.sh") in entry["detail"]
    assert next(check for check in report.checks if check["name"] == "code-dir")[
        "detail"
    ] == str(operator)


def test_standalone_cmake_project_does_not_require_build_sh(tmp_path) -> None:
    (tmp_path / "CMakeLists.txt").write_text("project(example)\n")
    report = MODULE.Report()
    with mock.patch.object(MODULE, "run_shell", return_value=(0, "/bin/tool")):
        MODULE.check_build(report, tmp_path)
    assert report.status == "warn"


def test_build_discovery_does_not_escape_nearest_repository(tmp_path) -> None:
    (tmp_path / "build.sh").write_text("#!/bin/sh\n")
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    operator = repo / "op"
    operator.mkdir()
    report = MODULE.Report()
    with mock.patch.object(MODULE, "run_shell", return_value=(0, "/bin/tool")):
        MODULE.check_build(report, operator)
    assert report.status == "fail"
