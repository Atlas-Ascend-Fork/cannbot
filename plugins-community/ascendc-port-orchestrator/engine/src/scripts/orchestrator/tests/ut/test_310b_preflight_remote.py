# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------
"""310B O0 target-toolchain probe chain.

Every probe must execute ON the machine named by .ascendc_env (SSH for the
board); the chain is fail-closed on ANY gap: 1) bisheng presence + sha256
fingerprint; 2) arch-token ACCEPT asserting the ``__DAV_M300__`` identity
macro; 3) arch-token REJECT control; 4) npu-smi SoC identity.  Also pins
the remote build-preflight variants and the board-side set_env / npu-smi /
python resolution.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parent.parent))
import phase_o5_runner  # noqa: E402,F401  (pre-existing import-cycle order)
import npubench.npubench_target_toolchain as tt  # noqa: E402
from a5_target_transport import _Target  # noqa: E402
from npubench.npubench_target_base import TargetTransportError  # noqa: E402

_BOARD = "310b-board"
_BISHENG_SHA = "ab" * 32
# Module-private probe seams, bound once via getattr (protected-access
# checker convention).
_remote_tu_compile_command = getattr(tt, "_remote_tu_compile_command")
_build_preflight_probe = getattr(tt, "_build_preflight_probe")
_remote_build_preflight_error = getattr(tt, "_remote_build_preflight_error")
_remote_cann_set_env = getattr(tt, "_remote_cann_set_env")
_npu_smi_command = getattr(tt, "_npu_smi_command")
_soc_probe_argv = getattr(tt, "_soc_probe_argv")
_bash_binary = getattr(tt, "_bash_binary")
_mapping_probe_argv = getattr(tt, "_mapping_probe_argv")
_target_python = getattr(tt, "_target_python")



def _board_target(env: dict | None = None) -> _Target:
    merged = {"ASCEND310B_SOC_VERSION": "Ascend310B1"}
    merged.update(env or {})
    return _Target(
        name="ASCEND310B",
        host=_BOARD,
        user="root",
        password="redacted-ut",
        container="local",
        cann_path="/usr/local/Ascend/ascend-toolkit/latest",
        benchmark_root="/root/AscendOpGenAgent",
        host_mode=True,
        visible_device=0,
        ssh_options=(),
        env=merged,
    )


def _a5_target() -> _Target:
    return _Target(
        name="A5",
        host="",
        user="root",
        password="",
        container="npu_dev3",
        cann_path="/usr/local/Ascend/cann",
        benchmark_root="/root/AscendOpGenAgent",
        host_mode=False,
        visible_device=0,
        ssh_options=(),
        env={},
    )


def _cp(argv: list, rc: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(argv, rc, stdout, stderr)


def _canned_capture(responses: dict) -> object:
    """Fake _ssh_capture keyed by the probe's `what` label."""

    def fake(target, remote_command, *, what, timeout):
        assert what in responses, f"unexpected probe step: {what}"
        return responses[what]()

    return fake


def _success_responses() -> dict:
    return {
        "bisheng presence+sha256": lambda: _cp(["x"], 0, f"{_BISHENG_SHA}  /CANN/bisheng\n", ""),
        "arch-token accept compile": lambda: _cp(
            ["x"], 0, "#define __DAV_M300__ 1\n#define __CCE_AICORE__ 300\n", ""
        ),
        "arch-token reject control": lambda: _cp(
            ["x"], 1, "", "error: unsupported cce architecture 'dav-NOSUCH'"
        ),
    }


def _patch_soc(monkeypatch: pytest.MonkeyPatch, observed: str = "Ascend310B1") -> None:
    monkeypatch.setattr(
        tt, "_probe_target_soc",
        lambda target, set_env, **kwargs: observed,
    )


# ---------------------------------------------------------------------------
# 1) The success chain
# ---------------------------------------------------------------------------
def test_probe_success_chain_over_ssh(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tt, "_ssh_capture", _canned_capture(_success_responses()))
    _patch_soc(monkeypatch)
    report = tt.probe_310b_target_toolchain(_board_target())
    assert report["probe"] == "ssh"
    assert report["host"] == _BOARD
    assert report["bisheng"].endswith("/bisheng_compiler/bin/bisheng")
    assert report["bisheng_sha256"] == _BISHENG_SHA
    # Identity is judged by the __DAV_* macro, never the numeric value.
    assert report["arch_token_accept"] == {"token": "dav-m300", "identity_macro": "__DAV_M300__"}
    assert report["arch_token_reject_control"] == {"token": "dav-NOSUCH", "rejected": True}
    assert report["chip_seen"] is True
    assert report["observed_soc"] == "Ascend310B1"
    assert report["configured_soc"] == "Ascend310B1"
    assert report["soc_family"] is not None


def test_probe_local_board_spelling_reports_local(monkeypatch: pytest.MonkeyPatch) -> None:
    # A controller-local 310B spelling would still label its transport
    # honestly.
    monkeypatch.setattr(tt, "_ssh_capture", _canned_capture(_success_responses()))
    _patch_soc(monkeypatch)
    target = _board_target()
    object.__setattr__(target, "host", "localhost")
    report = tt.probe_310b_target_toolchain(target)
    assert report["probe"] == "local"


# ---------------------------------------------------------------------------
# 2) Fail-closed variants — every gap raises, no silent degrade
# ---------------------------------------------------------------------------
def _expect_probe_failure(monkeypatch: pytest.MonkeyPatch, responses: dict, needle: str) -> None:
    monkeypatch.setattr(tt, "_ssh_capture", _canned_capture(responses))
    _patch_soc(monkeypatch)
    with pytest.raises(TargetTransportError) as excinfo:
        tt.probe_310b_target_toolchain(_board_target())
    assert needle in str(excinfo.value)


def test_probe_bisheng_missing_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = _success_responses()

    def bisheng_missing():
        return _cp(["x"], 127, "", "bisheng: not found")

    responses["bisheng presence+sha256"] = bisheng_missing
    _expect_probe_failure(monkeypatch, responses, "bisheng compiler missing")


def test_probe_bisheng_sha_unreadable_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = _success_responses()

    def bisheng_sha_unreadable():
        return _cp(["x"], 0, "not-a-digest\n", "")

    responses["bisheng presence+sha256"] = bisheng_sha_unreadable
    _expect_probe_failure(monkeypatch, responses, "sha256 fingerprint is unreadable")


def test_probe_accept_without_identity_macro_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    # rc=0 with only the numeric macro is NOT an accept.
    responses = _success_responses()

    def accept_without_identity_macro():
        return _cp(["x"], 0, "#define __CCE_AICORE__ 300\n", "")

    responses["arch-token accept compile"] = accept_without_identity_macro
    _expect_probe_failure(monkeypatch, responses, "identity macro __DAV_M300__ missing")


def test_probe_accept_compile_error_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = _success_responses()

    def accept_compile_error():
        return _cp(["x"], 2, "", "error: cannot compile")

    responses["arch-token accept compile"] = accept_compile_error
    _expect_probe_failure(monkeypatch, responses, "arch-token accept compile failed")


def test_probe_reject_control_not_refused_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    # dav-NOSUCH ACCEPTED (rc=0): accept-without-reject proves nothing.
    responses = _success_responses()

    def reject_control_not_refused():
        return _cp(["x"], 0, "#define __DAV_M300__ 1\n", "")

    responses["arch-token reject control"] = reject_control_not_refused
    _expect_probe_failure(monkeypatch, responses, "reject control failed")


def test_probe_reject_control_wrong_message_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    # Refused for an unrelated reason: still not the arch-dispatch rejection.
    responses = _success_responses()

    def reject_control_wrong_message():
        return _cp(["x"], 1, "", "error: no space left on device")

    responses["arch-token reject control"] = reject_control_wrong_message
    _expect_probe_failure(monkeypatch, responses, "reject control failed")


def test_probe_ssh_unreachable_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    def _unreachable(target, remote_command, *, what, timeout):
        raise TargetTransportError(f"310b toolchain probe '{what}' could not start: ssh missing")

    monkeypatch.setattr(tt, "_ssh_capture", _unreachable)
    with pytest.raises(TargetTransportError, match="could not start"):
        tt.probe_310b_target_toolchain(_board_target())


def test_probe_soc_mismatch_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tt, "_ssh_capture", _canned_capture(_success_responses()))

    def _wrong_box(target, set_env, **kwargs):
        raise TargetTransportError(
            "direct-launch target SoC does not match configuration: "
            "configured='Ascend310B1', observed='Ascend310P3'"
        )

    monkeypatch.setattr(tt, "_probe_target_soc", _wrong_box)
    with pytest.raises(TargetTransportError, match="does not match configuration"):
        tt.probe_310b_target_toolchain(_board_target())


def test_probe_soc_timeout_never_uses_configured_soc(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tt, "_ssh_capture", _canned_capture(_success_responses()))
    calls = 0

    def _timeout(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise subprocess.TimeoutExpired("npu-smi", 0.01)

    monkeypatch.setattr(tt, "_run_soc_probe", _timeout)
    with pytest.raises(TargetTransportError, match="observed SoC is required"):
        tt.probe_310b_target_toolchain(_board_target())
    assert calls == 2


# ---------------------------------------------------------------------------
# 3) Probe-command composition
# ---------------------------------------------------------------------------
def test_remote_tu_compile_command_creates_compiles_and_cleans_up() -> None:
    command = _remote_tu_compile_command(["bisheng", "--cce-aicore-arch=dav-m300"], "/tmp/tu.cc")
    assert "printf '%s\\n' 'int cannbot_o0_probe;' > /tmp/tu.cc" in command
    assert "bisheng --cce-aicore-arch=dav-m300" in command
    assert "rc=$?" in command
    assert "rm -f /tmp/tu.cc" in command
    assert command.rstrip().endswith("exit $rc")


def test_arch_token_probe_argv_uses_xcce_for_device_macros() -> None:
    argv = tt.arch_token_macro_probe_argv(Path("/CANN"), "dav-m300", Path("/tmp/tu.cc"))
    assert argv == [
        "/CANN/tools/bisheng_compiler/bin/bisheng",
        "--cce-aicore-arch=dav-m300",
        "-xcce",
        "-dM",
        "-E",
        "/tmp/tu.cc",
    ]


# ---------------------------------------------------------------------------
# 4) Remote build-preflight variants
# ---------------------------------------------------------------------------
def test_build_preflight_probe_310b_demands_ascendcl_and_torch() -> None:
    probe = _build_preflight_probe(_board_target())
    assert "acl_rt.h" in probe
    assert "acl.h" in probe
    assert "Python.h" in probe
    assert "torch" in probe and "torch_npu" in probe


def test_build_preflight_probe_a5_still_demands_torch() -> None:
    probe = _build_preflight_probe(_a5_target())
    assert "torch" in probe and "torch_npu" in probe
    assert "Python.h" in probe


def test_remote_build_preflight_error_310b_label(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        tt, "_ssh_capture", lambda *a, **k: _cp(["x"], 1, "", "AssertionError: headers missing")
    )
    error = _remote_build_preflight_error("/opt/py/bin/python3", _board_target())
    assert error is not None
    assert _BOARD in error
    assert "AscendCL runtime headers" in error
    assert "torch, torch_npu and Python.h" in error


def test_remote_build_preflight_error_a5_label(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        tt, "_ssh_capture", lambda *a, **k: _cp(["x"], 1, "", "ModuleNotFoundError: No module named 'torch'")
    )
    error = _remote_build_preflight_error("/opt/py/bin/python3", _a5_target())
    assert error is not None
    assert "torch, torch_npu and Python.h" in error


def test_remote_build_preflight_passes_on_zero_rc(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tt, "_ssh_capture", lambda *a, **k: _cp(["x"], 0, "", ""))
    assert _remote_build_preflight_error("/opt/py/bin/python3", _board_target()) is None


# ---------------------------------------------------------------------------
# 5) Board-side set_env / npu-smi / python resolution (wrong-machine rule)
# ---------------------------------------------------------------------------
def test_remote_cann_set_env_resolves_board_side(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    def fake(target, remote_command, *, what, timeout):
        captured["command"] = remote_command
        return _cp(["x"], 0, "/usr/local/Ascend/ascend-toolkit/latest/set_env.sh\n", "")

    monkeypatch.setattr(tt, "_ssh_capture", fake)
    resolved = _remote_cann_set_env(_board_target())
    assert resolved == Path("/usr/local/Ascend/ascend-toolkit/latest/set_env.sh")
    # Candidate order is judged ON the board; the shell exits on first hit.
    for candidate in (
        "/usr/local/Ascend/ascend-toolkit/latest/set_env.sh",
        "/usr/local/Ascend/ascend-toolkit/set_env.sh",
        "/usr/local/Ascend/cann/set_env.sh",
    ):
        assert candidate in captured["command"]


def test_remote_cann_set_env_returns_only_first_existing_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = _board_target()
    object.__setattr__(target, "cann_path", str(tmp_path))
    (tmp_path / "set_env.sh").write_text("")

    def fake(target, remote_command, *, what, timeout):
        return subprocess.run(
            ["/bin/bash", "-c", remote_command],
            capture_output=True,
            text=True,
            check=False,
        )

    monkeypatch.setattr(tt, "_ssh_capture", fake)
    assert _remote_cann_set_env(target) == tmp_path / "set_env.sh"


def test_remote_cann_set_env_fail_soft_on_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tt, "_ssh_capture", lambda *a, **k: _cp(["x"], 1, "", "no such file"))
    assert _remote_cann_set_env(_board_target()) is None


def test_remote_cann_set_env_fail_soft_on_transport_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(*a, **k):
        raise TargetTransportError("unreachable")

    monkeypatch.setattr(tt, "_ssh_capture", _raise)
    assert _remote_cann_set_env(_board_target()) is None


def test_npu_smi_command_remote_never_local_file_checks() -> None:
    # Remote binaries are judged by the board itself, never controller-side
    # file-checked; unconfigured remote fails loud here — board-side
    # candidate resolution lives in _remote_smi_shell (G2-7).
    with pytest.raises(TargetTransportError):
        _npu_smi_command(_board_target())
    configured = _board_target(env={"NPU_SMI_BIN": "/opt/board/npu-smi"})
    assert _npu_smi_command(configured) == "/opt/board/npu-smi"


def test_npu_smi_command_310b_prefers_its_explicit_binary() -> None:
    configured = _board_target(
        env={"ASCEND310B_NPU_SMI_BIN": "/opt/board/npu-smi"}
    )
    assert _npu_smi_command(configured) == "/opt/board/npu-smi"
    configured = _board_target(
        env={
            "ASCEND310B_NPU_SMI_BIN": "/opt/board/npu-smi",
            "A5_NPU_SMI_BIN": "/opt/a5/npu-smi",
        }
    )
    assert _npu_smi_command(configured) == "/opt/board/npu-smi"


def test_soc_probe_argv_remote_unconfigured_resolves_on_board() -> None:
    # G2-7: remote + no NPU_SMI_BIN -> board-side candidate loop (no
    # candidate exits 127 into the fail-closed path).
    argv = _soc_probe_argv(_board_target(), None)
    assert argv[:2] == [_bash_binary(), "-lc"]
    command = argv[2]
    assert "/usr/local/bin/npu-smi" in command
    assert "/usr/local/sbin/npu-smi" in command
    assert "exit 127" in command
    assert "info -t board -i 0" in command
    set_env = Path("/usr/local/Ascend/cann-8.5.1/set_env.sh")
    argv = _soc_probe_argv(_board_target(), set_env)
    assert argv[2].startswith("source /usr/local/Ascend/cann-8.5.1/set_env.sh")
    assert "exit 127" in argv[2]


def test_soc_probe_argv_remote_configured_keeps_absolute_spelling() -> None:
    # An explicit NPU_SMI_BIN wins over the resolver loop on remote boards.
    target = _board_target(env={"NPU_SMI_BIN": "/opt/board/npu-smi"})
    assert _soc_probe_argv(target, None)[:1] == ["/opt/board/npu-smi"]
    set_env = Path("/set_env.sh")
    argv = _soc_probe_argv(target, set_env)
    assert "/opt/board/npu-smi info -t board -i 0" in argv[2]
    assert "$(" not in argv[2]


def test_mapping_probe_argv_remote_unconfigured_resolves_on_board() -> None:
    argv = _mapping_probe_argv(_board_target(), None)
    command = argv[2]
    assert "/usr/local/sbin/npu-smi" in command
    assert "exit 127" in command
    assert "info -m" in command


def test_target_python_prefixed_keys_never_local_file_checked() -> None:
    # {TARGET}_NPU_PYTHON_BIN names a bin DIRECTORY: dir + /python3, no
    # controller-side is_dir probe.
    env = {"ASCEND310B_NPU_PYTHON_BIN": "/root/miniconda3/envs/bisheng-wr/bin"}
    assert str(_target_python(env, "ASCEND310B")) == (
        "/root/miniconda3/envs/bisheng-wr/bin/python3"
    )


def test_target_python_explicit_host_python_wins() -> None:
    env = {
        "ASCEND310B_HOST_PYTHON": "/opt/board/python3",
        "ASCEND310B_NPU_PYTHON_BIN": "/root/miniconda3/envs/bisheng-wr/bin",
    }
    assert str(_target_python(env, "ASCEND310B")) == "/opt/board/python3"


def test_target_python_legacy_keys_still_honoured() -> None:
    env = {"A5_PYTHON": "/opt/a5/python3"}
    assert str(_target_python(env, "A5")) == "/opt/a5/python3"
    assert str(_target_python({}, "A5")) == sys.executable
