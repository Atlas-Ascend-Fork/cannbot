# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

from __future__ import annotations

import errno
import locale
import os
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Optional, TextIO, TypedDict, cast

from env_registry import (
    ASCEND_RT_VISIBLE_DEVICES,
    HELIX_EVAL_TIMEOUT_SECONDS,
    HELIX_PREWARM_TRITON,
    HELIX_PREWARM_WORKERS,
    HELIX_PYTHON,
    HELIX_SCP_TIMEOUT_SECONDS,
    HELIX_SSH_TIMEOUT_SECONDS,
    TRITON_ALL_BLOCKS_PARALLEL,
    TRITON_ALWAYS_COMPILE,
    TRITON_CACHE_DIR,
)
from result_payload import ResultPayload, make_result

_IS_WINDOWS = sys.platform == "win32"
_SSH_MUX_CONTROL_DIR = Path.home() / ".cache" / "helix" / "ssh-mux"
_SSH_MUX_CONTROL_PERSIST_SECONDS = 60
_BLOCKS_PARALLEL_UNSAFE_VALUE = "1"
_BLOCKS_PARALLEL_SAFE_VALUE = "0"
if not _IS_WINDOWS:
    import pty
    import select
else:
    pty = None
    select = None


class RemoteSpec(TypedDict):
    user_host: str
    port: int | None


class StagingInput(TypedDict):
    source: Path
    target: str


_STAGING_EXCLUDED_NAMES = frozenset(
    {
        "state.json",
        "round-state.json",
        "verify-state.json",
        "profile-result.json",
    }
)


def local_python_executable() -> str:
    configured = os.environ.get(HELIX_PYTHON, "").strip()
    if configured:
        return configured
    if getattr(sys, "frozen", False):
        return "python"
    return sys.executable


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from exc
    if value < 0:
        raise ValueError(f"{name} must be non-negative, got {raw!r}")
    return value


def _ssh_timeout() -> int:
    return env_int(HELIX_SSH_TIMEOUT_SECONDS, 120)


def _scp_timeout() -> int:
    return env_int(HELIX_SCP_TIMEOUT_SECONDS, 300)


def eval_timeout_seconds() -> int:
    return env_int(HELIX_EVAL_TIMEOUT_SECONDS, 300)


def emit_verbose(stderr: TextIO, category: str, message: str) -> None:
    print(f"[{category}] {message}", file=stderr)


def _timeout_message(timeout_seconds: float, timeout_env_name: str = HELIX_EVAL_TIMEOUT_SECONDS) -> str:
    return (
        f"Evaluation timed out after {timeout_seconds:g} seconds "
        f"({timeout_env_name}); the current operator execution exceeded the limit.\n"
    )


def _iter_pipe_chunks(stream: Any) -> Iterator[bytes | str]:
    if stream is None:
        return
    read = getattr(stream, "read", None)
    if callable(read):
        yield from _iter_read_chunks(read)
        return
    readline = getattr(stream, "readline", None)
    if callable(readline):
        yield from _iter_readline_chunks(readline)
        return
    try:
        for chunk in stream:
            if isinstance(chunk, (bytes, str)):
                yield chunk
    except ValueError:
        return


def _iter_read_chunks(read: Any) -> Iterator[bytes | str]:
    while True:
        try:
            try:
                chunk = read(4096)
            except TypeError:
                chunk = read()
        except ValueError:
            return
        if not chunk:
            return
        if isinstance(chunk, (bytes, str)):
            yield chunk


def _iter_readline_chunks(readline: Any) -> Iterator[bytes | str]:
    while True:
        try:
            chunk = readline()
        except ValueError:
            return
        if not chunk:
            return
        if isinstance(chunk, (bytes, str)):
            yield chunk


def terminate_process_tree(process: subprocess.Popen[Any]) -> None:
    if process.poll() is not None:
        return
    if _IS_WINDOWS:
        taskkill = shutil.which("taskkill")
        if taskkill is None:
            raise RuntimeError(
                "taskkill executable not found on PATH; cannot terminate the process tree"
            )
        try:
            completed = subprocess.run(
                [taskkill, "/PID", str(process.pid), "/T", "/F"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if completed.returncode != 0:
                process.terminate()
        except OSError:
            process.terminate()
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        process.terminate()
    try:
        process.wait(timeout=1)
        return
    except (AttributeError, TypeError, subprocess.TimeoutExpired):
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        kill = getattr(process, "kill", None)
        if callable(kill):
            kill()


def _process_group_popen_kwargs() -> dict[str, Any]:
    if _IS_WINDOWS:
        return {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)}
    return {"start_new_session": True}


@dataclass(frozen=True)
class _StreamTimeouts:
    """Grouped timeout settings for the process-wait helpers."""

    stall_timeout_seconds: int
    timeout_seconds: float | None = None
    timeout_env_name: str = HELIX_EVAL_TIMEOUT_SECONDS


class _BufferedOutputCollector:
    """Thread-drained stdout/stderr accumulation with last-output tracking."""

    def __init__(self) -> None:
        self.stdout_lines: list[str] = []
        self.stderr_lines: list[str] = []
        self.started_at = time.monotonic()
        self._last_output = self.started_at
        self._lock = threading.Lock()

    def drain(self, stream: Any, chunks: list[str]) -> None:
        for chunk in _iter_pipe_chunks(stream):
            text = _coerce_output_text(chunk)
            with self._lock:
                chunks.append(text)
                self._last_output = time.monotonic()

    def idle_seconds(self) -> float:
        with self._lock:
            return time.monotonic() - self._last_output

    def stdout_text(self) -> str:
        return "".join(self.stdout_lines)

    def stderr_text(self) -> str:
        return "".join(self.stderr_lines)


def run_buffered_process(
    command: list[str],
    workdir: str,
    stall_timeout_seconds: int,
    extra_env: dict[str, str] | None = None,
    *,
    timeout_seconds: float | None = None,
    timeout_env_name: str = HELIX_EVAL_TIMEOUT_SECONDS,
) -> ResultPayload:
    process = subprocess.Popen(
        command,
        cwd=workdir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=False,
        env=_merged_env(extra_env),
        **_process_group_popen_kwargs(),
    )
    stdout_pipe = process.stdout
    stderr_pipe = process.stderr
    collector = _BufferedOutputCollector()
    readers = (
        threading.Thread(target=collector.drain, args=(stdout_pipe, collector.stdout_lines), daemon=True),
        threading.Thread(target=collector.drain, args=(stderr_pipe, collector.stderr_lines), daemon=True),
    )
    for reader in readers:
        reader.start()
    timeouts = _StreamTimeouts(
        stall_timeout_seconds=stall_timeout_seconds,
        timeout_seconds=timeout_seconds,
        timeout_env_name=timeout_env_name,
    )
    try:
        stalled_result = _await_buffered_process(process, collector, readers, timeouts)
        if stalled_result is not None:
            return stalled_result
        _join_readers(readers)
        return make_result(
            return_code=_resolved_returncode(process.returncode),
            stdout=collector.stdout_text(),
            stderr=collector.stderr_text(),
        )
    finally:
        _close_pipe(stdout_pipe)
        _close_pipe(stderr_pipe)


def _await_buffered_process(
    process: subprocess.Popen[Any],
    collector: _BufferedOutputCollector,
    readers: Sequence[threading.Thread],
    timeouts: _StreamTimeouts,
) -> ResultPayload | None:
    """Poll the process; return a timed-out/stalled result, or None on exit."""
    while True:
        if process.poll() is not None:
            return None
        timeout_seconds = timeouts.timeout_seconds
        if timeout_seconds is not None and timeout_seconds > 0:
            if time.monotonic() - collector.started_at > timeout_seconds:
                terminate_process_tree(process)
                _join_readers(readers)
                return make_result(
                    return_code=1,
                    stdout=collector.stdout_text(),
                    stderr=collector.stderr_text()
                    + _timeout_message(timeout_seconds, timeouts.timeout_env_name),
                    stalled=True,
                )
        if timeouts.stall_timeout_seconds > 0:
            if collector.idle_seconds() > timeouts.stall_timeout_seconds:
                terminate_process_tree(process)
                _join_readers(readers)
                return make_result(
                    return_code=1,
                    stdout=collector.stdout_text(),
                    stderr=collector.stderr_text(),
                    stalled=True,
                )
        time.sleep(0.05)


def _join_readers(readers: Sequence[threading.Thread]) -> None:
    for reader in readers:
        reader.join(timeout=1)


def _close_pipe(pipe: Any) -> None:
    if pipe is None:
        return
    close = getattr(pipe, "close", None)
    if callable(close):
        close()


def run_streaming_process(
    command: list[str],
    workdir: str,
    stall_timeout_seconds: int,
    stdout: Optional[TextIO] = None,
    extra_env: dict[str, str] | None = None,
    *,
    timeout_seconds: float | None = None,
    timeout_env_name: str = HELIX_EVAL_TIMEOUT_SECONDS,
) -> ResultPayload:
    if _IS_WINDOWS:
        return _run_streaming_windows(
            command,
            workdir,
            stall_timeout_seconds,
            stdout,
            extra_env,
            timeout_seconds=timeout_seconds,
            timeout_env_name=timeout_env_name,
        )
    return _run_streaming_pty(
        command,
        workdir,
        stall_timeout_seconds,
        stdout,
        extra_env,
        timeout_seconds=timeout_seconds,
        timeout_env_name=timeout_env_name,
    )


class _StreamWatch:
    """Shared mutable state between the streaming reader and the watchdog loop."""

    def __init__(self) -> None:
        self.start = time.monotonic()
        self.last_output = self.start
        self.stalled = False
        self.timed_out = False
        self.lock = threading.Lock()


def _watch_streaming_process(
    process: subprocess.Popen[Any],
    reader_thread: threading.Thread,
    watch: _StreamWatch,
    stall_timeout_seconds: int,
    timeout_seconds: float | None,
) -> None:
    while True:
        reader_thread.join(timeout=0.1)
        if not reader_thread.is_alive() and process.poll() is not None:
            return
        with watch.lock:
            elapsed = time.monotonic() - watch.last_output
        if (
            timeout_seconds is not None
            and timeout_seconds > 0
            and time.monotonic() - watch.start > timeout_seconds
        ):
            terminate_process_tree(process)
            watch.stalled = True
            watch.timed_out = True
            return
        if stall_timeout_seconds > 0 and elapsed > stall_timeout_seconds:
            terminate_process_tree(process)
            watch.stalled = True
            return


def _run_streaming_windows(
    command: list[str],
    workdir: str,
    stall_timeout_seconds: int,
    stdout: Optional[TextIO] = None,
    extra_env: dict[str, str] | None = None,
    *,
    timeout_seconds: float | None = None,
    timeout_env_name: str = HELIX_EVAL_TIMEOUT_SECONDS,
) -> ResultPayload:
    process = subprocess.Popen(
        command,
        cwd=workdir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=False,
        env=_merged_env(extra_env),
        **_process_group_popen_kwargs(),
    )
    output_chunks: list[str] = []
    watch = _StreamWatch()

    def reader() -> None:
        if process.stdout is None:
            raise RuntimeError("streaming process stdout pipe is missing")
        while True:
            chunk = process.stdout.read(4096)
            if not chunk:
                break
            text = _coerce_output_text(chunk)
            with watch.lock:
                output_chunks.append(text)
                print(text, file=stdout or sys.stdout, end="", flush=True)
                watch.last_output = time.monotonic()

    reader_thread = threading.Thread(target=reader, daemon=True)
    reader_thread.start()
    _watch_streaming_process(process, reader_thread, watch, stall_timeout_seconds, timeout_seconds)
    reader_thread.join()
    rc = process.wait() if not watch.stalled else 1
    return make_result(
        return_code=rc,
        stdout="".join(output_chunks),
        stderr=(
            _timeout_message(timeout_seconds, timeout_env_name)
            if watch.timed_out and timeout_seconds is not None
            else ""
        ),
        stalled=watch.stalled,
    )


def _run_streaming_pty(
    command: list[str],
    workdir: str,
    stall_timeout_seconds: int,
    stdout: Optional[TextIO] = None,
    extra_env: dict[str, str] | None = None,
    *,
    timeout_seconds: float | None = None,
    timeout_env_name: str = HELIX_EVAL_TIMEOUT_SECONDS,
) -> ResultPayload:
    pty_module = pty
    select_module = select
    if pty_module is None or select_module is None:
        raise RuntimeError("PTY streaming is unavailable on this platform")
    master_fd, slave_fd = cast(Any, pty_module).openpty()
    output_chunks: list[str] = []
    process = subprocess.Popen(
        command,
        cwd=workdir,
        stdin=subprocess.DEVNULL,
        stdout=slave_fd,
        stderr=slave_fd,
        text=False,
        close_fds=True,
        env=_merged_env(extra_env),
        **_process_group_popen_kwargs(),
    )
    os.close(slave_fd)
    timeouts = _StreamTimeouts(
        stall_timeout_seconds=stall_timeout_seconds,
        timeout_seconds=timeout_seconds,
        timeout_env_name=timeout_env_name,
    )
    try:
        return _stream_pty_output(process, master_fd, output_chunks, stdout, timeouts)
    finally:
        os.close(master_fd)


def _stream_pty_output(
    process: subprocess.Popen[Any],
    master_fd: int,
    output_chunks: list[str],
    stdout: Optional[TextIO],
    timeouts: _StreamTimeouts,
) -> ResultPayload:
    """Pump the PTY master fd until the child exits or a timeout fires."""
    select_module = cast(Any, select)
    started_at = time.monotonic()
    last_output_at = started_at
    while True:
        ready, _, _ = select_module.select([master_fd], [], [], 0.1)
        if ready:
            chunk = _read_pty_chunk(master_fd, process)
            if chunk is None:
                break
            if chunk:
                text = _coerce_output_text(chunk)
                output_chunks.append(text)
                print(text, file=stdout or sys.stdout, end="")
                last_output_at = time.monotonic()
            elif process.poll() is not None:
                break
            continue
        if process.poll() is not None:
            break
        stalled_result = _pty_timeout_result(
            process, output_chunks, timeouts, started_at, last_output_at
        )
        if stalled_result is not None:
            return stalled_result
    return make_result(return_code=process.wait(), stdout="".join(output_chunks), stderr="")


def _read_pty_chunk(master_fd: int, process: subprocess.Popen[Any]) -> bytes | None:
    """Read one PTY chunk; None means the slave closed (the child exited)."""
    try:
        return os.read(master_fd, 4096)
    except OSError as error:
        if error.errno != errno.EIO:
            raise
        # PTY slave closed — normal child exit signal.
        # poll() may not reflect termination yet due to a race,
        # so wait briefly before treating this as clean shutdown.
        if process.poll() is None:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        return None


def _pty_timeout_result(
    process: subprocess.Popen[Any],
    output_chunks: list[str],
    timeouts: _StreamTimeouts,
    started_at: float,
    last_output_at: float,
) -> ResultPayload | None:
    """A stalled/timed-out result when a deadline passed, else None."""
    now = time.monotonic()
    timeout_seconds = timeouts.timeout_seconds
    if timeout_seconds is not None and timeout_seconds > 0 and now - started_at > timeout_seconds:
        terminate_process_tree(process)
        return make_result(
            return_code=1,
            stdout="".join(output_chunks),
            stderr=_timeout_message(timeout_seconds, timeouts.timeout_env_name),
            stalled=True,
        )
    if timeouts.stall_timeout_seconds > 0 and now - last_output_at > timeouts.stall_timeout_seconds:
        terminate_process_tree(process)
        return make_result(
            return_code=1,
            stdout="".join(output_chunks),
            stderr="",
            stalled=True,
        )
    return None


def parse_remote_spec(raw: str) -> RemoteSpec:
    candidate = raw.strip()
    if not candidate:
        raise ValueError("Remote target must not be empty.")
    if ":" not in candidate:
        return {"user_host": candidate, "port": None}

    user_host, possible_port = candidate.rsplit(":", 1)
    if not possible_port.isdigit():
        raise ValueError(f"Remote target port must be numeric: {raw}")
    return {"user_host": user_host, "port": int(possible_port)}


def create_remote_workspace(
    remote: str,
    remote_workdir: str | None,
    verbose: bool = False,
    stderr: TextIO | None = None,
) -> tuple[RemoteSpec, str]:
    spec = parse_remote_spec(remote)
    # Sweep while we are here: session dirs are only removed by the finally
    # cleanup, so a SIGKILLed process (cancel / wall-clock timeout / crash)
    # leaks them. No session can outlive the eval wall clock (hours), so any
    # helix-* dir older than 24h is a corpse — sweeping on every new session
    # keeps bare CLI runs (no external watchdog) self-healing.
    sweep = "find %s -maxdepth 1 -name 'helix-*' -mmin +1440 -exec rm -rf {} + 2>/dev/null;"
    if remote_workdir:
        root = shlex.quote(remote_workdir)
        pattern = shlex.quote(str(PurePosixPath(remote_workdir) / "helix-XXXXXX"))
        remote_command = f"mkdir -p {root} && {sweep % root} mktemp -d {pattern}"
    else:
        remote_command = sweep % '${TMPDIR:-/tmp}' + " mktemp -d"
    command = _ssh_command(spec, remote_command)
    _maybe_emit_remote_command(command, verbose, stderr)
    result = run_buffered_process(command, ".", stall_timeout_seconds=_ssh_timeout())
    if not result_succeeded(result):
        raise RuntimeError(result["stderr"] or result["stdout"] or "Failed to create remote workspace.")
    workspace = result["stdout"].strip().splitlines()[-1].strip()
    if not workspace:
        raise RuntimeError("Remote workspace command did not return a path.")
    return spec, workspace


def cleanup_remote_workspace(
    spec: RemoteSpec,
    remote_workspace: str,
    verbose: bool = False,
    stderr: TextIO | None = None,
) -> None:
    command = _ssh_command(spec, f"rm -rf {shlex.quote(remote_workspace)}")
    _maybe_emit_remote_command(command, verbose, stderr)
    run_buffered_process(command, ".", stall_timeout_seconds=_ssh_timeout())


def delete_remote_files(
    spec: RemoteSpec,
    remote_workspace: str,
    names: Sequence[str],
    *,
    verbose: bool = False,
    stderr: TextIO | None = None,
) -> None:
    """Best-effort delete of consumed files in the remote session. Failure is
    ignored: session teardown (cleanup_remote_workspace) removes the whole
    directory on the normal path anyway.
    """
    if not names:
        return
    command = _ssh_command(
        spec,
        "rm -f "
        + " ".join(shlex.quote(f"{remote_workspace}/{name}") for name in names),
    )
    _maybe_emit_remote_command(command, verbose, stderr)
    run_buffered_process(command, ".", stall_timeout_seconds=_ssh_timeout())


def copy_file_to_remote(
    spec: RemoteSpec,
    local_path: Path,
    remote_path: str,
    verbose: bool = False,
    stderr: TextIO | None = None,
) -> None:
    local_workdir, local_arg = _scp_local_operand(local_path)
    command = _scp_to_remote_command(spec, local_arg, remote_path)
    _maybe_emit_remote_command(command, verbose, stderr)
    result = run_buffered_process(command, local_workdir, stall_timeout_seconds=_scp_timeout())
    if not result_succeeded(result):
        raise RuntimeError(result["stderr"] or result["stdout"] or f"Failed to copy {local_path} to remote.")


def _stage_one(source: Path, target: Path) -> None:
    try:
        # A hard link avoids re-reading and re-writing large staged files
        # when source and staging directory share a filesystem.
        os.link(source, target)
    except OSError:
        try:
            shutil.copy2(source, target)
        except OSError as exc:
            raise RuntimeError(f"Failed to stage {source} for remote copy: {exc}") from exc


def copy_staging_files_to_remote(
    spec: RemoteSpec,
    records: Sequence[StagingInput],
    remote_directory: str,
    verbose: bool = False,
    stderr: TextIO | None = None,
) -> None:
    """Copy flat staging records through one SCP connection, honoring aliases."""
    if not records:
        return
    names = [str(record["target"]) for record in records]
    if len(set(names)) != len(names):
        raise ValueError("Remote batch copy requires unique target filenames.")
    if any(Path(name).name != name for name in names):
        raise ValueError("Remote batch copy requires flat target filenames.")
    with tempfile.TemporaryDirectory(prefix="helix-remote-stage-") as tmp:
        stage_dir = Path(tmp)
        for record in records:
            source = Path(str(record["source"]))
            target = stage_dir / str(record["target"])
            _stage_one(source, target)
        command = ["scp", *_ssh_mux_options()]
        if spec["port"] is not None:
            command.extend(["-P", str(spec["port"])])
        command.extend(names)
        command.append(f"{spec['user_host']}:{remote_directory}/")
        _maybe_emit_remote_command(command, verbose, stderr)
        result = run_buffered_process(command, str(stage_dir), stall_timeout_seconds=_scp_timeout())
    if not result_succeeded(result):
        raise RuntimeError(result["stderr"] or result["stdout"] or "Failed to copy staging files to remote.")


def collect_staging_input_files(
    source_dirs: Sequence[Path],
    explicit_files: Sequence[tuple[Path, str | None]] = (),
    *,
    extra_files: Sequence[tuple[Path, str | None]] = (),
    excluded_paths: Sequence[Path] = (),
    excluded_names: Sequence[str] = (),
    suffixes: Sequence[str] = (".json", ".py"),
) -> list[StagingInput]:
    """Collect flat isolated-workspace inputs and reject basename collisions."""
    excluded = {path.resolve() for path in excluded_paths}
    records: list[StagingInput] = []
    sources_by_target: dict[str, Path] = {}
    all_explicit = (*explicit_files, *extra_files)
    explicit_sources = {path.resolve() for path, _target in all_explicit}
    excluded_target_names = set(excluded_names)

    for source, _target in all_explicit:
        resolved = source.resolve()
        if not resolved.is_file():
            raise FileNotFoundError(resolved)

    def add(source: Path, target: str | None) -> None:
        resolved = source.resolve()
        if target is None and resolved in excluded:
            return
        target_name = target or source.name
        previous = sources_by_target.get(target_name)
        if previous is not None:
            if previous != resolved:
                kind = "JSON" if target_name.lower().endswith(".json") else "Python"
                raise ValueError(
                    f"Staging would collide on {kind} basename '{target_name}': "
                    f"{previous} vs {resolved}"
                )
            return
        sources_by_target[target_name] = resolved
        records.append({"source": resolved, "target": target_name})

    for source, target in all_explicit:
        add(source, target)
    normalized_suffixes = {suffix.lower() for suffix in suffixes}
    for source_dir in source_dirs:
        if not source_dir.is_dir():
            continue
        for source in sorted(source_dir.resolve().iterdir(), key=lambda path: path.name):
            if _is_staging_source_skipped(
                source,
                explicit_sources=explicit_sources,
                excluded=excluded,
                excluded_target_names=excluded_target_names,
                normalized_suffixes=normalized_suffixes,
            ):
                continue
            add(source, None)
    return records


def _is_staging_source_skipped(
    source: Path,
    *,
    explicit_sources: set[Path],
    excluded: set[Path],
    excluded_target_names: set[str],
    normalized_suffixes: set[str],
) -> bool:
    if not source.is_file() or source.name.lower() in _STAGING_EXCLUDED_NAMES:
        return True
    if source.suffix.lower() not in normalized_suffixes:
        return True
    resolved = source.resolve()
    if resolved in explicit_sources or resolved in excluded:
        return True
    return source.name in excluded_target_names


def collect_json_input_files(source_dirs: Sequence[Path]) -> list[Path]:
    """Collect non-state JSON inputs and reject remote basename collisions."""
    return [
        Path(str(record["source"])).resolve()
        for record in collect_staging_input_files(source_dirs, suffixes=(".json",))
    ]


def copy_file_from_remote(
    spec: RemoteSpec,
    remote_path: str,
    local_path: Path,
    verbose: bool = False,
    stderr: TextIO | None = None,
) -> None:
    local_workdir, local_arg = _scp_local_operand(local_path)
    command = _scp_from_remote_command(spec, remote_path, local_arg)
    _maybe_emit_remote_command(command, verbose, stderr)
    result = run_buffered_process(command, local_workdir, stall_timeout_seconds=_scp_timeout())
    if not result_succeeded(result):
        raise RuntimeError(result["stderr"] or result["stdout"] or f"Failed to copy {remote_path} from remote.")


def copy_directory_from_remote(
    spec: RemoteSpec,
    remote_path: str,
    local_path: Path,
    verbose: bool = False,
    stderr: TextIO | None = None,
) -> None:
    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_workdir, local_arg = _scp_local_operand(local_path)
    command = _scp_from_remote_command(spec, remote_path, local_arg, recursive=True)
    _maybe_emit_remote_command(command, verbose, stderr)
    result = run_buffered_process(command, local_workdir, stall_timeout_seconds=_scp_timeout())
    if not result_succeeded(result):
        raise RuntimeError(
            result["stderr"] or result["stdout"] or f"Failed to copy directory {remote_path} from remote."
        )


def ssh_session_command(
    spec: RemoteSpec,
    remote_workspace: str,
    remote_command: "str | Sequence[str]",
    extra_env: "dict[str, str] | None" = None,
) -> "list[str]":
    env_prefix = _shell_env_prefix(_remote_execution_extra_env(remote_workspace, extra_env))
    command_text = _normalize_remote_command(remote_command)
    return _ssh_command(
        spec,
        f"cd {shlex.quote(remote_workspace)} && {env_prefix + ' ' if env_prefix else ''}{command_text}",
    )


def run_remote_command_streaming(
    spec: RemoteSpec,
    remote_workspace: str,
    remote_command: str | Sequence[str],
    *,
    stdout: TextIO | None = None,
    verbose: bool = False,
    stderr: TextIO | None = None,
    extra_env: dict[str, str] | None = None,
    stall_timeout_seconds: int | None = None,
    timeout_env_name: str = HELIX_EVAL_TIMEOUT_SECONDS,
) -> ResultPayload:
    command = ssh_session_command(spec, remote_workspace, remote_command, extra_env)
    _maybe_emit_remote_command(command, verbose, stderr)
    timeout = stall_timeout_seconds if stall_timeout_seconds is not None else eval_timeout_seconds()
    if not verbose:
        return run_buffered_process(
            command,
            ".",
            stall_timeout_seconds=0,
            timeout_seconds=timeout,
            timeout_env_name=timeout_env_name,
        )
    return run_streaming_process(
        command,
        ".",
        stall_timeout_seconds=0,
        stdout=stdout,
        timeout_seconds=timeout,
        timeout_env_name=timeout_env_name,
    )


def run_remote_command_buffered(
    spec: RemoteSpec,
    remote_workspace: str,
    remote_command: str | Sequence[str],
    *,
    verbose: bool = False,
    stderr: TextIO | None = None,
    extra_env: dict[str, str] | None = None,
    stall_timeout_seconds: int | None = None,
    timeout_env_name: str = HELIX_EVAL_TIMEOUT_SECONDS,
) -> ResultPayload:
    command = ssh_session_command(spec, remote_workspace, remote_command, extra_env)
    _maybe_emit_remote_command(command, verbose, stderr)
    timeout = stall_timeout_seconds if stall_timeout_seconds is not None else eval_timeout_seconds()
    return run_buffered_process(
        command,
        ".",
        stall_timeout_seconds=0,
        timeout_seconds=timeout,
        timeout_env_name=timeout_env_name,
    )


def _ssh_mux_options() -> list[str]:
    if _IS_WINDOWS:
        return []
    _SSH_MUX_CONTROL_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    return [
        "-o",
        "ControlMaster=auto",
        "-o",
        f"ControlPath={_SSH_MUX_CONTROL_DIR}/%C",
        "-o",
        f"ControlPersist={_SSH_MUX_CONTROL_PERSIST_SECONDS}",
    ]


def _ssh_command(spec: RemoteSpec, remote_command: str) -> list[str]:
    command = ["ssh", *_ssh_mux_options()]
    if spec["port"] is not None:
        command.extend(["-p", str(spec["port"])])
    command.extend([spec["user_host"], f"bash -lc {shlex.quote(remote_command)}"])
    return command


def _scp_to_remote_command(spec: RemoteSpec, local_path_arg: str, remote_path: str) -> list[str]:
    command = ["scp", *_ssh_mux_options()]
    if spec["port"] is not None:
        command.extend(["-P", str(spec["port"])])
    command.extend([local_path_arg, f"{spec['user_host']}:{remote_path}"])
    return command


def _scp_from_remote_command(
    spec: RemoteSpec,
    remote_path: str,
    local_path_arg: str,
    recursive: bool = False,
) -> list[str]:
    command = ["scp", *_ssh_mux_options()]
    if recursive:
        command.append("-r")
    if spec["port"] is not None:
        command.extend(["-P", str(spec["port"])])
    command.extend([f"{spec['user_host']}:{remote_path}", local_path_arg])
    return command


def _maybe_emit_remote_command(command: list[str], verbose: bool, stderr: TextIO | None) -> None:
    if not verbose or stderr is None:
        return
    emit_verbose(stderr, "remote", f"command: {shlex.join(command)}")


def result_succeeded(result: ResultPayload) -> bool:
    return result["return_code"] == 0 and not result["stalled"]


def _normalize_remote_command(remote_command: str | Sequence[str]) -> str:
    if isinstance(remote_command, str):
        return remote_command
    return shlex.join(str(part) for part in remote_command)


def _resolved_returncode(returncode: int | None) -> int:
    return returncode if returncode is not None else 1


def _normalized_execution_extra_env(extra_env: dict[str, str] | None) -> dict[str, str]:
    normalized = {} if extra_env is None else dict(extra_env)
    blocks_parallel = normalized.get(TRITON_ALL_BLOCKS_PARALLEL)
    if blocks_parallel == _BLOCKS_PARALLEL_UNSAFE_VALUE:
        normalized[TRITON_ALL_BLOCKS_PARALLEL] = _BLOCKS_PARALLEL_SAFE_VALUE
    elif (
        blocks_parallel is None
        and os.environ.get(TRITON_ALL_BLOCKS_PARALLEL) == _BLOCKS_PARALLEL_SAFE_VALUE
    ):
        normalized[TRITON_ALL_BLOCKS_PARALLEL] = _BLOCKS_PARALLEL_SAFE_VALUE
    return normalized


def _remote_execution_extra_env(
    remote_workspace: str,
    extra_env: dict[str, str] | None,
) -> dict[str, str]:
    normalized = _normalized_execution_extra_env(extra_env)
    if normalized.get(TRITON_CACHE_DIR) is not None or os.environ.get(TRITON_CACHE_DIR) is not None:
        normalized[TRITON_CACHE_DIR] = str(
            PurePosixPath(remote_workspace) / ".helix-triton-cache"
        )
    for name in (
        TRITON_ALWAYS_COMPILE,
        ASCEND_RT_VISIBLE_DEVICES,
        HELIX_PREWARM_TRITON,
        HELIX_PREWARM_WORKERS,
        HELIX_EVAL_TIMEOUT_SECONDS,
    ):
        if name not in normalized:
            value = os.environ.get(name)
            if value is not None:
                normalized[name] = value
    return normalized


def _merged_env(extra_env: dict[str, str] | None) -> dict[str, str] | None:
    normalized = _normalized_execution_extra_env(extra_env)
    if extra_env is None and not normalized:
        return None
    merged = dict(os.environ)
    merged.update(normalized)
    return merged


def _shell_env_prefix(extra_env: dict[str, str] | None) -> str:
    normalized = _normalized_execution_extra_env(extra_env)
    if not normalized:
        return ""
    return " ".join(f"{key}={shlex.quote(value)}" for key, value in sorted(normalized.items()))


def _coerce_output_text(data: bytes | str) -> str:
    # Keep this decoder local to the skill helper instead of importing a shared
    # helix utility: skill-side scripts must stay self-contained.
    if isinstance(data, str):
        return data
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        preferred = locale.getpreferredencoding(False) or "utf-8"
        return data.decode(preferred, errors="replace")


def _scp_local_operand(local_path: Path) -> tuple[str, str]:
    return str(local_path.parent), local_path.name
