# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------
"""Target toolchain resolution and the controlled direct-build process.

This module owns everything the controlled build needs from the machine it runs
on: which Python and CANN ``set_env.sh`` to use, which ``npu-smi`` binary is
approved, the device SoC probe, the pre-CMake runtime preflight, and the
session-isolated build process whose whole process group can be stopped on a
timeout.
"""
from __future__ import annotations

import logging
import os
import shlex
import signal
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Mapping, Sequence

from a5_target_capability import (
    a5_soc_version,
    canonical_target_id,
    parse_npu_smi_mapping_soc,
    parse_npu_smi_soc,
    soc_product_family,
    soc_version_for_target,
)
from a5_target_transport import _Target, _ssh_command, is_local_host
from npubench.npubench_target_base import TargetTransportError, _DirectBuildTimeout


def _run_direct_build_process(
    shell_command: str,
    *,
    cwd: Path,
    env: Mapping[str, str],
    timeout_sec: int,
) -> subprocess.CompletedProcess[str]:
    """Run the build in its own session so timeout can stop every descendant.

    The build genuinely needs a login shell: it must source the CANN
    ``set_env.sh`` and chain the build invocation after it.  The interpreter is
    the approved absolute bash path and every value interpolated into
    ``shell_command`` by the caller is ``shlex.quote``d or ``int()``-cast, so no
    caller-controlled shell metacharacter can reach the shell.
    """
    command = [_bash_binary(), "-lc", shell_command]
    process = subprocess.Popen(
        command,
        cwd=str(cwd),
        env=dict(env),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout_sec)
    except subprocess.TimeoutExpired as exc:
        stdout, stderr = _terminate_direct_build_process_group(process)
        raise _DirectBuildTimeout(
            timeout_sec,
            _process_output_text(stdout if stdout is not None else exc.stdout),
            _process_output_text(stderr if stderr is not None else exc.stderr),
        ) from exc
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def _terminate_direct_build_process_group(process: subprocess.Popen[str]) -> tuple[str, str]:
    """Terminate then forcibly reap the isolated direct-build process group."""
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        return process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        return process.communicate()


def _process_output_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value


def _target_python(env: Mapping[str, Any], target: str | None = None) -> Path:
    """Resolve the build interpreter, target-parametric.

    Precedence: ``{TARGET}_PYTHON`` / ``{TARGET}_HOST_PYTHON``, legacy A5
    spellings, ``{TARGET}_NPU_PYTHON_BIN`` (bin DIRECTORY on the 310b board),
    ``NPU_PYTHON_BIN``, ``sys.executable`` — the last names the CONTROLLER
    interpreter, so a remote deployment must configure an explicit key.
    """
    from briefs.target_env_map import TARGET_ENV_PREFIXES

    prefix = TARGET_ENV_PREFIXES.get(canonical_target_id(target)) if target else None
    explicit_values: list[object] = []
    if prefix:
        explicit_values += [env.get(f"{prefix}_PYTHON"), env.get(f"{prefix}_HOST_PYTHON")]
    explicit_values += [env.get("A5_PYTHON"), env.get("A5_HOST_PYTHON")]
    for explicit in explicit_values:
        if isinstance(explicit, str) and explicit.strip():
            return Path(explicit.strip()).expanduser()
    if prefix:
        prefixed = env.get(f"{prefix}_NPU_PYTHON_BIN")
        if isinstance(prefixed, str) and prefixed.strip():
            # Target-prefixed NPU_PYTHON_BIN names a bin DIRECTORY (board-side
            # path, never local-file-checked).
            return Path(prefixed.strip().rstrip("/")).expanduser() / "python3"
    for directory in (env.get("A5_NPU_PYTHON_BIN"), env.get("NPU_PYTHON_BIN")):
        if isinstance(directory, str) and directory.strip():
            candidate = Path(directory.strip()).expanduser()
            if candidate.is_dir():
                return candidate / "python3"
            return candidate
    return Path(sys.executable)


def _remote_cann_set_env(target: _Target) -> Path | None:
    """Resolve the board-side CANN set_env.sh over SSH; None when unresolved.

    Candidate order as :func:`_resolve_cann_set_env`, judged ON the target
    machine; None is fail-soft (login environment).
    """
    cann = Path(target.cann_path).expanduser()
    candidates = (
        cann / "set_env.sh",
        Path("/usr/local/Ascend/cann/set_env.sh"),
        Path("/usr/local/Ascend/ascend-toolkit/set_env.sh"),
        Path("/usr/local/Ascend/ascend-toolkit/latest/set_env.sh"),
    )
    quoted_candidates = " ".join(shlex.quote(str(candidate)) for candidate in candidates)
    chain = (
        f"for candidate in {quoted_candidates}; do "
        "if [ -f \"$candidate\" ]; then "
        "printf '%s\\n' \"$candidate\"; exit 0; fi; "
        "done; exit 1"
    )
    try:
        result = _ssh_capture(target, chain, what="remote set_env resolve", timeout=30)
    except TargetTransportError:
        return None
    if result.returncode != 0:
        return None
    lines = [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]
    return Path(lines[-1]) if lines else None


def _resolve_cann_set_env(cann_path: Path) -> Path | None:
    """Resolve the active CANN environment script without trusting stale config."""
    candidates = [
        cann_path / "set_env.sh",
        Path("/usr/local/Ascend/cann/set_env.sh"),
        Path("/usr/local/Ascend/ascend-toolkit/set_env.sh"),
        Path("/usr/local/Ascend/ascend-toolkit/latest/set_env.sh"),
    ]
    for candidate in candidates:
        try:
            if candidate.is_file() and not candidate.is_symlink():
                return candidate.resolve()
        except OSError:
            continue
    return None


def _configured_npu_smi(target: _Target) -> str | None:
    """Return the explicitly configured npu-smi path, if any."""
    if canonical_target_id(target.name) == "310b":
        configured = target.env.get("ASCEND310B_NPU_SMI_BIN") or target.env.get("NPU_SMI_BIN")
    else:
        configured = target.env.get("A5_NPU_SMI_BIN") or target.env.get("NPU_SMI_BIN")
    if isinstance(configured, str) and configured.strip():
        return configured.strip()
    return None


# G2-7: the npu-smi prefix is resolved BY THE BOARD across these candidates
# (the board ships /usr/local/sbin, not /usr/local/bin).
_REMOTE_SMI_CANDIDATES = (
    "/usr/local/bin/npu-smi",
    "/usr/local/sbin/npu-smi",
    "/usr/bin/npu-smi",
)


def _remote_smi_shell(args: str) -> str:
    """Remote npu-smi invocation with board-side binary resolution.

    No candidate exits 127, flowing into the SoC probe's fail-closed BLOCKED
    path — never a silent fallback or a PATH lookup.
    """
    chain = " ".join(shlex.quote(candidate) for candidate in _REMOTE_SMI_CANDIDATES)
    return (
        f"SMI_BIN=$(for c in {chain}; do [ -x \"$c\" ] && {{ printf '%s' \"$c\"; break; }}; done); "
        f"[ -n \"$SMI_BIN\" ] || exit 127; \"$SMI_BIN\" {args}"
    )


def _npu_smi_command(target: _Target) -> str:
    configured = _configured_npu_smi(target)
    if not is_local_host(target.host):
        # Remote board: binaries are judged by the board itself — the
        # explicit NPU_SMI_BIN only. Unconfigured remotes resolve on the
        # board via _remote_smi_shell at the probe builders, never an
        # embedded resolver word here.
        if configured is None:
            raise TargetTransportError(
                "remote npu-smi requires an explicit NPU_SMI_BIN; the "
                "unconfigured default resolves on the board via "
                "_remote_smi_shell"
            )
        return configured
    if configured is not None:
        candidate = Path(configured).expanduser()
        if candidate.is_symlink() or not candidate.is_file() or not os.access(candidate, os.X_OK):
            raise TargetTransportError(
                f"configured npu-smi is unavailable or unsafe: {candidate}"
            )
        return str(candidate.resolve())
    for candidate in (Path("/usr/local/bin/npu-smi"), Path("/usr/local/sbin/npu-smi"), Path("/usr/bin/npu-smi")):
        if candidate.is_file() and not candidate.is_symlink() and os.access(candidate, os.X_OK):
            return str(candidate)
    raise TargetTransportError(
        "npu-smi is unavailable at an approved absolute path; refusing PATH lookup"
    )


def _positive_timeout_from_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    value = raw.strip()
    if not value:
        raise TargetTransportError(f"{name} must be a positive integer, got an empty value")
    try:
        timeout = int(value)
    except ValueError as exc:
        raise TargetTransportError(
            f"{name} must be a positive integer, got {raw!r}"
        ) from exc
    if timeout <= 0:
        raise TargetTransportError(f"{name} must be greater than zero, got {raw!r}")
    return timeout


def _bash_binary() -> str:
    """Return an approved absolute bash path (never rely on PATH lookup)."""
    for candidate in (Path("/bin/bash"), Path("/usr/bin/bash")):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    raise TargetTransportError("bash is unavailable at an approved absolute path")


# ---------------------------------------------------------------------------
# 310B arch-token compile path: direct invocation must pass the dav-m300
# token (soc-version spellings do not dispatch) plus ``-xcce`` for
# device-side macro dumps; derivation and identity rules live in
# patches/build_ascendc.py.
# ---------------------------------------------------------------------------
AICORE_ARCH_BY_TARGET: dict[str, str] = {
    "310b": "dav-m300",
}
# Reject control for the arch-token probe: a token the compiler must refuse.
_ARCH_TOKEN_REJECT_CONTROL = "dav-NOSUCH"


def bisheng_compiler_path(cann_path: Path) -> Path:
    """Return the 310B-capable bisheng compiler under a CANN install.

    Path composition only (the spelling lives in one place); callers verify
    existence and executability.
    """
    return cann_path / "tools" / "bisheng_compiler" / "bin" / "bisheng"


def arch_token_macro_probe_argv(
    cann_path: Path, arch_token: str, probe_tu: Path
) -> list[str]:
    """Build the accept-control argv that must dump the arch identity macros.

    bisheng + arch token + ``-xcce -dM -E``; judge identity by the
    ``__DAV_*`` macros, never the numeric ``__CCE_AICORE__`` (values can
    collide across generations; see patches/build_ascendc.py).
    """
    return [
        str(bisheng_compiler_path(cann_path)),
        f"--cce-aicore-arch={arch_token}",
        "-xcce",
        "-dM",
        "-E",
        str(probe_tu),
    ]


def arch_token_reject_probe_argv(
    cann_path: Path, probe_tu: Path
) -> list[str]:
    """Build the reject-control argv: an unknown arch token must FAIL.

    An accept-without-reject pair cannot prove the dispatch actually reads
    the token, so the O0 probe requires both controls.
    """
    return arch_token_macro_probe_argv(
        cann_path, _ARCH_TOKEN_REJECT_CONTROL, probe_tu
    )


# 310B board products (log triage only; SoC identity comes from npu-smi,
# whose Name column reports e.g. 310B1) are catalogued by the npu-arch
# skill, references/npu-hardware-params.md section 0.


def _soc_probe_argv(target: _Target, set_env: Path | None) -> list[str]:
    """Build the npu-smi probe argv, using a shell only to source ``set_env``.

    A shell is genuinely required only when a CANN ``set_env.sh`` has to be
    sourced into the probe environment.  Without one the approved absolute
    ``npu-smi`` binary is executed directly as argv, so no shell is involved at
    all.  In the sourcing case the interpreter is the absolute bash path, the
    two interpolated strings are ``shlex.quote``d and the device index is
    ``int()``-cast, so no caller-controlled shell metacharacter can reach it.

    Exception (G2-7): a REMOTE target without an explicit ``NPU_SMI_BIN`` uses
    the board-side candidate resolution of :func:`_remote_smi_shell` and is
    therefore always a ``bash -lc`` command — the controller must not guess
    the board's install prefix (the 310B board ships ``/usr/local/sbin``).
    """
    device = int(target.visible_device)
    if not is_local_host(target.host) and _configured_npu_smi(target) is None:
        command = _remote_smi_shell(f"info -t board -i {device}")
        if set_env is not None:
            command = f"source {shlex.quote(str(set_env))} >/dev/null 2>&1 && {command}"
        return [_bash_binary(), "-lc", command]
    npu_smi = _npu_smi_command(target)
    if set_env is None:
        return [npu_smi, "info", "-t", "board", "-i", str(device)]
    command = f"{shlex.quote(npu_smi)} info -t board -i {device}"
    command = f"source {shlex.quote(str(set_env))} >/dev/null 2>&1 && {command}"
    return [_bash_binary(), "-lc", command]


def _mapping_probe_argv(target: _Target, set_env: Path | None) -> list[str]:
    """Build the ``npu-smi info -m`` argv under the same safety rules.

    Multi-chip npu-smi generations (26.2.rc1, e.g. the 310P Atlas 300I Duo
    topology: 3 cards x 2 AI chips) reject ``-t board -i <logic device id>``
    because ``-i`` means CARD id there, and even the valid per-card board
    listing carries no per-chip model.  The mapping table is the only surface
    that maps a Chip Logic ID (= ASCEND_RT device index) to its chip name, so
    it is the fallback probe for those generations.  No interpolated device
    value at all; the set_env sourcing case mirrors :func:`_soc_probe_argv`.
    Remote unconfigured npu-smi resolves on the board (G2-7, see
    :func:`_remote_smi_shell`).
    """
    if not is_local_host(target.host) and _configured_npu_smi(target) is None:
        command = _remote_smi_shell("info -m")
        if set_env is not None:
            command = f"source {shlex.quote(str(set_env))} >/dev/null 2>&1 && {command}"
        return [_bash_binary(), "-lc", command]
    npu_smi = _npu_smi_command(target)
    if set_env is None:
        return [npu_smi, "info", "-m"]
    command = f"{shlex.quote(npu_smi)} info -m"
    command = f"source {shlex.quote(str(set_env))} >/dev/null 2>&1 && {command}"
    return [_bash_binary(), "-lc", command]


def _run_soc_probe(
    argv: Sequence[str], target: _Target | None = None
) -> subprocess.CompletedProcess[str]:
    """Run one SoC probe — over SSH when the target host is remote.

    A probe argv describes a command ON THE TARGET MACHINE; for a remote
    host it is dispatched through the shared SSH transport.
    """
    if target is not None and not is_local_host(target.host):
        remote = " ".join(shlex.quote(str(item)) for item in argv)
        argv = _ssh_command(remote, target)
    return subprocess.run(
        list(argv),
        capture_output=True,
        text=True,
        check=False,
        timeout=_positive_timeout_from_env("CANNBOT_DIRECT_SOC_PROBE_TIMEOUT_SEC", 30),
    )


def _soc_probe_result(
    target: _Target,
    argv: Sequence[str],
    *,
    allow_configured_fallback: bool = True,
) -> subprocess.CompletedProcess[str] | None:
    """Run the probe with one retry; optionally trust the configured SOC."""
    try:
        return _run_soc_probe(argv, target)
    except subprocess.TimeoutExpired:
        # Shared-infra contention (2026-08-22, source-migration flow): npu-smi
        # can hang when concurrent campaigns saturate the device manager.
        # Retry once below, then trust the configured SOC policy (authoritative
        # in .ascendc_env) so a healthy build is not blocked by probe latency.
        pass
    except (OSError, subprocess.SubprocessError) as exc:
        raise TargetTransportError(
            f"direct-launch target SoC probe could not start: {type(exc).__name__}: {exc}"
        ) from exc
    try:
        return _run_soc_probe(argv, target)
    except (OSError, subprocess.SubprocessError) as exc:
        if not allow_configured_fallback:
            raise TargetTransportError(
                "direct-launch target SoC probe failed twice; "
                f"an observed SoC is required: {type(exc).__name__}: {exc}"
            ) from exc
        configured = soc_version_for_target(target.env, target.name)
        if configured:
            logging.getLogger(__name__).warning(
                "direct-launch SoC probe timed out twice under contention; "
                "trusting configured SOC %s", configured
            )
            return None
        raise TargetTransportError(
            f"direct-launch target SoC probe could not start: {type(exc).__name__}: {exc}"
        ) from exc


def _chip_name_from_board_output(output: str) -> str:
    """Read ``Chip Name`` from the 25.1.rc1 per-device board listing.

        NPU ID    : 5
        Chip Name : Ascend950DT
    """
    for line in output.splitlines():
        if "Chip Name" not in line:
            continue
        parts = line.split(":")
        if len(parts) >= 2:
            name = parts[-1].strip().split()
            if name:
                return name[0]
    return ""


def _soc_from_mapping_table(target: _Target, set_env: Path | None) -> str:
    """Fallback: read the chip model from the ``info -m`` mapping table.

    Returns "" when the table is unavailable or has no row for the device —
    a closed-gate signal, not an exception: this probe only runs AFTER the
    primary board probe already failed to identify a model, and the caller's
    family checks surface the combined failure with the board rc attached.
    """
    try:
        completed = _soc_probe_result(target, _mapping_probe_argv(target, set_env))
    except TargetTransportError:
        return ""
    if completed is None or completed.returncode != 0:
        return ""
    return parse_npu_smi_mapping_soc(completed.stdout or "", target.visible_device)


def _probe_target_soc(
    target: _Target,
    set_env: Path | None,
    *,
    allow_configured_fallback: bool = True,
) -> str:
    """Bind configured SoC policy to the target device's reported model."""
    # Per-device board query first.  The FULL npu-smi info listing iterates
    # every physical device and hangs as soon as one unrelated card wedges
    # its management path (2026-08-22 A5 campaign: device 4 died Critical
    # and froze the whole listing; lanes 1/2/3 were healthy but every
    # full-listing probe timed out at 30s).  The per-device query stays
    # responsive for healthy devices.  Multi-chip generations where the
    # board query cannot work at all (no per-chip model in the listing;
    # -i means CARD id) fall through to the mapping-table probe below.
    completed = _soc_probe_result(
        target,
        _soc_probe_argv(target, set_env),
        allow_configured_fallback=allow_configured_fallback,
    )
    if completed is None:
        # Target-aware configured-SoC read (a5 → A5_SOC_VERSION,
        # 310p → ASCEND310P_SOC_VERSION via the canonical prefix map).
        return soc_version_for_target(target.env, target.name)
    output = completed.stdout or ""
    observed = ""
    if completed.returncode == 0:
        observed = parse_npu_smi_soc(output, target.visible_device)
        if not observed:
            observed = _chip_name_from_board_output(output)
    if not observed:
        # 26.2.rc1 multi-chip topology (a 6-chip 310P box: 3 cards x 2 chips,
        # Chip Logic IDs 0-5 are the ASCEND_RT devices): the board
        # query rejects the logic device id with a usage error (rc=215) and
        # the valid per-card listing carries no per-chip model.  The mapping
        # table resolves Chip Logic ID → chip name.  It is a full-system
        # query, but it only runs after the board probe already failed fast,
        # so the wedged-card hang scenario above still terminates through
        # the timeout → configured-SoC trust path in _soc_probe_result.
        observed = _soc_from_mapping_table(target, set_env)
    configured_family = soc_product_family(
        soc_version_for_target(target.env, target.name)
    )
    observed_family = soc_product_family(observed)
    if not observed or observed_family is None:
        detail = (completed.stderr or completed.stdout or "").strip().splitlines()
        suffix = detail[-1] if detail else "no diagnostic"
        raise TargetTransportError(
            "direct-launch target SoC probe returned no recognized model for "
            f"device {target.visible_device} "
            f"(board rc={completed.returncode}: {suffix})"
        )
    if configured_family != observed_family:
        raise TargetTransportError(
            "direct-launch target SoC does not match configuration: "
            f"configured={soc_version_for_target(target.env, target.name)!r}, "
            f"observed={observed!r}, "
            f"device={target.visible_device}"
        )
    return observed


def _build_preflight_probe(target: _Target) -> str:
    """Python-source probe for the candidate build runtime, per destination.

    Every destination demands torch/torch_npu and the Python development
    headers; 310b additionally demands AscendCL headers for its ACLRT shim.
    """
    inc = (
        "inc=sysconfig.get_path('include'); "
        "assert inc and __import__('os').path.isfile("
        "__import__('os').path.join(inc,'Python.h')), "
        "'Python development headers are missing'"
    )
    probe = (
        "import importlib.util,sysconfig; "
        "mods=('torch','torch_npu'); "
        "missing=[m for m in mods if importlib.util.find_spec(m) is None]; "
        "assert not missing, 'missing Python modules: '+','.join(missing); "
    )
    if canonical_target_id(target.name) == "310b":
        cann = Path(target.cann_path).expanduser()
        header_paths = (
            cann / "include" / "acl" / "acl_rt.h",
            cann / "include" / "acl" / "acl.h",
            cann / "include" / "aclrt.h",
        )
        headers = ", ".join(repr(str(path)) for path in header_paths)
        probe += (
            f"assert any(__import__('os').path.isfile(p) for p in ({headers})), "
            "'AscendCL runtime headers (acl_rt.h/acl.h) are missing under the "
            "configured CANN path — the raw-ACLRT pybind shim cannot build'; "
        )
    return probe + inc


def _remote_build_preflight_error(python: str, target: _Target) -> str | None:
    """Run the build preflight ON the remote board over SSH."""
    remote_command = f"{shlex.quote(python)} -c {shlex.quote(_build_preflight_probe(target))}"
    try:
        result = _ssh_capture(
            target, remote_command,
            what="remote build preflight",
            timeout=_positive_timeout_from_env("CANNBOT_DIRECT_PREFLIGHT_TIMEOUT_SEC", 60),
        )
    except TargetTransportError as exc:
        return f"direct candidate target Python preflight could not start: {exc}"
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()
        suffix = detail[-1] if detail else "no diagnostic"
        label = (
            "AscendCL runtime headers, torch, torch_npu and Python.h"
            if canonical_target_id(target.name) == "310b"
            else "torch, torch_npu and Python.h"
        )
        return (
            f"direct candidate target Python preflight failed for {python} on "
            f"{target.host}: {suffix}; install/use a target environment "
            f"containing {label}"
        )
    return None


def _direct_build_preflight(python: Path, target: _Target) -> str | None:
    """Fail before CMake with an actionable target-runtime diagnostic.

    Runs ON the machine that will build (locally for a controller target,
    over SSH for a remote host).
    """
    if not is_local_host(target.host):
        return _remote_build_preflight_error(str(python), target)
    if not python.is_file() or not os.access(python, os.X_OK):
        return f"direct candidate target Python is unavailable or not executable: {python}"
    cann_path = Path(target.cann_path).expanduser()
    if not cann_path.is_dir():
        return f"direct candidate target CANN path does not exist: {cann_path}"
    probe = _build_preflight_probe(target)
    try:
        result = subprocess.run(
            [str(python), "-c", probe],
            text=True,
            capture_output=True,
            check=False,
            timeout=_positive_timeout_from_env("CANNBOT_DIRECT_PREFLIGHT_TIMEOUT_SEC", 60),
        )
    except (TargetTransportError, OSError, subprocess.SubprocessError) as exc:
        return f"direct candidate target Python preflight could not start: {type(exc).__name__}: {exc}"
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()
        suffix = detail[-1] if detail else "no diagnostic"
        return (
            f"direct candidate target Python preflight failed for {python}: {suffix}; "
            "install/use a target environment containing torch, torch_npu and Python.h"
        )
    return None


# ---------------------------------------------------------------------------
# O0 target-toolchain probe chain for a 310b destination: every probe executes
# ON the machine named by .ascendc_env (SSH for a remote host) — the transport
# is part of the evidence ("probe": "ssh" is a first-class report field).
# ---------------------------------------------------------------------------
def _ssh_capture(
    target: _Target, remote_command: str, *, what: str, timeout: int
) -> subprocess.CompletedProcess[str]:
    """Run one probe command ON the target machine; transport is fail-closed."""
    if is_local_host(target.host):
        argv: list[str] = [_bash_binary(), "-lc", remote_command]
    else:
        argv = _ssh_command(remote_command, target)
    try:
        return subprocess.run(
            argv, capture_output=True, text=True, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired as exc:
        raise TargetTransportError(
            f"310b toolchain probe '{what}' timed out after {timeout}s"
        ) from exc
    except (OSError, subprocess.SubprocessError) as exc:
        raise TargetTransportError(
            f"310b toolchain probe '{what}' could not start: "
            f"{type(exc).__name__}: {exc}"
        ) from exc


def _remote_tu_compile_command(compile_argv: Sequence[str], probe_tu: str) -> str:
    """Wrap a probe compile argv: create the TU, compile, always clean up."""
    q = shlex.quote
    compile_command = " ".join(q(str(item)) for item in compile_argv)
    return (
        f"printf '%s\\n' 'int cannbot_o0_probe;' > {q(probe_tu)} && "
        f"{compile_command}; rc=$?; rm -f {q(probe_tu)}; exit $rc"
    )


def _probe_bisheng_fingerprint(target: _Target, bisheng: Path, timeout: int) -> str:
    """Step 1: compiler presence + sha256 fingerprint (O0 registration baseline)."""
    fingerprint = _ssh_capture(
        target,
        f"test -x {shlex.quote(str(bisheng))} && sha256sum {shlex.quote(str(bisheng))}",
        what="bisheng presence+sha256",
        timeout=timeout,
    )
    if fingerprint.returncode != 0:
        raise TargetTransportError(
            "310b O0 probe: bisheng compiler missing or not executable on "
            f"target {target.host} at {bisheng} "
            f"(rc={fingerprint.returncode}; "
            f"stderr_tail={_process_output_text(fingerprint.stderr)[-200:]!r})"
        )
    sha_fields = (fingerprint.stdout or "").split()
    bisheng_sha256 = sha_fields[0] if sha_fields else ""
    if len(bisheng_sha256) != 64 or any(
        character not in "0123456789abcdef" for character in bisheng_sha256
    ):
        raise TargetTransportError(
            "310b O0 probe: bisheng sha256 fingerprint is unreadable "
            f"(stdout_tail={(fingerprint.stdout or '')[-120:]!r})"
        )
    return bisheng_sha256


def _identity_macro_for(arch_token: str) -> str:
    """Map an arch token to its identity macro (dav-m300 -> ``__DAV_M300__``)."""
    return "__DAV_" + arch_token.removeprefix("dav-").upper() + "__"


def _probe_arch_token_accept(
    target: _Target, cann: Path, arch_token: str,
    probe_tu: str, timeout: int,
) -> None:
    """Step 2: arch-token accept compile — identity macro asserted, never numeric."""
    identity_macro = _identity_macro_for(arch_token)
    accept = _ssh_capture(
        target,
        _remote_tu_compile_command(
            arch_token_macro_probe_argv(cann, arch_token, Path(probe_tu)), probe_tu
        ),
        what="arch-token accept compile",
        timeout=timeout,
    )
    macros = accept.stdout or ""
    if accept.returncode == 0 and identity_macro in macros:
        return
    reason = (
        f"identity macro {identity_macro} missing from the macro dump"
        if accept.returncode == 0
        else f"rc={accept.returncode}"
    )
    raise TargetTransportError(
        f"310b O0 probe: arch-token accept compile failed on {target.host} "
        f"(token={arch_token}: {reason}; "
        f"stderr_tail={_process_output_text(accept.stderr)[-200:]!r})"
    )


def _probe_arch_token_reject(target: _Target, cann: Path, probe_tu: str, timeout: int) -> None:
    """Step 3: reject control — an unknown token MUST be refused."""
    reject = _ssh_capture(
        target,
        _remote_tu_compile_command(
            arch_token_reject_probe_argv(cann, Path(probe_tu)), probe_tu
        ),
        what="arch-token reject control",
        timeout=timeout,
    )
    reject_output = (reject.stdout or "") + (reject.stderr or "")
    if reject.returncode == 0 or "unsupported cce architecture" not in reject_output.lower():
        raise TargetTransportError(
            "310b O0 probe: arch-token reject control failed — the compiler "
            f"did not refuse {_ARCH_TOKEN_REJECT_CONTROL} "
            f"(rc={reject.returncode}); an accept-without-reject pair proves "
            "nothing about the arch-token dispatch"
        )


def probe_310b_target_toolchain(target: _Target) -> dict[str, Any]:
    """O0 probe chain for a 310b destination; raises fail-closed on ANY gap.

    Board-side: 1) bisheng presence + sha256; 2) arch-token ACCEPT asserting
    the identity macro; 3) arch-token REJECT control; 4) npu-smi SoC identity
    (configured family must equal the observed).  Returns the report dict for
    the ``orchestrator.phase_o0_310b_probe`` event — any failure raises
    TargetTransportError, no silent degrade.
    """
    arch_token = AICORE_ARCH_BY_TARGET["310b"]
    identity_macro = _identity_macro_for(arch_token)
    timeout = _positive_timeout_from_env("CANNBOT_310B_PROBE_TIMEOUT_SEC", 60)
    cann = Path(target.cann_path).expanduser()
    bisheng = bisheng_compiler_path(cann)
    probe_tu = f"/tmp/cannbot_310b_o0_{uuid.uuid4().hex[:12]}.cc"

    bisheng_sha256 = _probe_bisheng_fingerprint(target, bisheng, timeout)
    _probe_arch_token_accept(target, cann, arch_token, probe_tu, timeout)
    _probe_arch_token_reject(target, cann, probe_tu, timeout)
    observed_soc = _probe_target_soc(target, None, allow_configured_fallback=False)
    return {
        "probe": "local" if is_local_host(target.host) else "ssh",
        "host": target.host,
        "chip_seen": bool(observed_soc),
        "observed_soc": observed_soc,
        "configured_soc": soc_version_for_target(target.env, target.name),
        "soc_family": soc_product_family(observed_soc),
        "bisheng": str(bisheng),
        "bisheng_sha256": bisheng_sha256,
        "arch_token_accept": {"token": arch_token, "identity_macro": identity_macro},
        "arch_token_reject_control": {
            "token": _ARCH_TOKEN_REJECT_CONTROL,
            "rejected": True,
        },
    }
