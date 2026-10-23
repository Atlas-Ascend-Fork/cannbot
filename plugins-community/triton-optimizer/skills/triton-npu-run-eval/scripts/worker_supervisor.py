# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Parent-side supervisor for the unified evaluation worker."""

from __future__ import annotations

import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, TextIO

from env_registry import HELIX_EVAL_TIMEOUT_SECONDS
from result_payload import ResultPayload, make_result
from run_runtime import (
    RemoteSpec,
    _merged_env,  # pyright: ignore[reportPrivateUsage]  # shared within the skill scripts
    _maybe_emit_remote_command,  # pyright: ignore[reportPrivateUsage]  # shared within the skill scripts
    _process_group_popen_kwargs,  # pyright: ignore[reportPrivateUsage]  # shared within the skill scripts
    _resolved_returncode,  # pyright: ignore[reportPrivateUsage]  # shared within the skill scripts
    _timeout_message,  # pyright: ignore[reportPrivateUsage]  # shared within the skill scripts
    eval_timeout_seconds,
    local_python_executable,
    ssh_session_command,
    terminate_process_tree,
)
import worker_protocol as protocol

_pending_termination_signal: "Optional[int]" = None


def pending_termination_signal() -> "Optional[int]":
    """Return the signal whose parent-side handling interrupted a supervised run.

    The CLI consumes this after its command handler finishes, so the
    partial-result synthesis runs first and the process still exits 128+N.
    """
    return _pending_termination_signal


@dataclass
class SupervisedRun:
    records: "list[dict[str, object]]"
    progress: "list[dict[str, object]]"
    final: "Optional[dict[str, object]]"
    planned_case_ids: "list[str]"
    timed_out: bool
    result: ResultPayload
    # Wall-clock start of the worker process. Callers that fall back to an
    # artifact the worker may have written (the bench perf file) compare its
    # mtime against this, so a leftover artifact from an earlier run can never
    # be mistaken for this run's output. The default disables that check for
    # hand-built runs.
    started_at: float = 0.0


def print_prewarm_warning(event: Mapping[str, object]) -> None:
    """Print one progress event's message when it is a prewarm warning.

    Passed as ``run_supervised_worker``'s ``on_progress`` by callers that do
    not forward the raw worker stream, so prewarm degradations surface live
    in every mode, local and remote. Info-level and non-prewarm events stay
    quiet here: runs with ``forward_stdout`` see them in the forwarded raw
    envelopes instead, so nothing prints twice.
    """
    if event.get("event") != "prewarm" or event.get("level") != "warning":
        return
    message = event.get("message")
    if isinstance(message, str):
        print(message)


def local_worker_command(worker_path: Path, action: str, args: "Sequence[str]") -> "list[str]":
    return [local_python_executable(), str(worker_path), action, *args]


class _WorkerOutputCollector:
    """Accumulate a supervised worker's decoded protocol output.

    The reader threads own the appends; the main thread only reads after
    joining them (except the lock-guarded idle clock used by the wait loop).
    """

    def __init__(self, process: "subprocess.Popen[Any]") -> None:
        self._process = process
        self.records: "list[dict[str, object]]" = []
        self.progress: "list[dict[str, object]]" = []
        self.final: "Optional[dict[str, object]]" = None
        self.planned: "list[str]" = []
        self.stdout_chunks: "list[str]" = []
        self.stderr_chunks: "list[str]" = []
        self._last_output = time.monotonic()
        self._lock = threading.Lock()

    def idle_seconds(self) -> float:
        with self._lock:
            return time.monotonic() - self._last_output

    def read_stdout(
        self,
        forward_stdout: "Optional[TextIO]",
        on_progress: "Optional[Callable[[Mapping[str, object]], None]]",
    ) -> None:
        stream = self._process.stdout
        if stream is None:
            raise RuntimeError("supervised worker stdout pipe is missing")
        for line in stream:
            with self._lock:
                self._last_output = time.monotonic()
            if forward_stdout is not None:
                print(line, end="", file=forward_stdout, flush=True)
            message = protocol.decode_message(line)
            if message is None:
                # Passthrough output (library banners, CANN noise); protocol
                # envelopes surface through records/progress/final instead of
                # the captured stdout text that failure rendering prints.
                with self._lock:
                    self.stdout_chunks.append(line)
                continue
            self._handle_message(message, on_progress)

    def read_stderr(self) -> None:
        stream = self._process.stderr
        if stream is None:
            raise RuntimeError("supervised worker stderr pipe is missing")
        for line in stream:
            with self._lock:
                self.stderr_chunks.append(line)
                self._last_output = time.monotonic()

    def _handle_message(
        self,
        message: "dict[str, Any]",
        on_progress: "Optional[Callable[[Mapping[str, object]], None]]",
    ) -> None:
        if message["kind"] == protocol.KIND_CASE:
            with self._lock:
                self.records.append(message["data"])
            return
        if message["kind"] == protocol.KIND_PROGRESS:
            with self._lock:
                self.progress.append(message["data"])
                self._record_plan(message["data"])
            if on_progress is not None:
                on_progress(message["data"])
            return
        if message["kind"] == protocol.KIND_FINAL and self.final is None:
            self.final = message["data"]

    def _record_plan(self, data: Mapping[str, object]) -> None:
        if data.get("event") == "plan" and isinstance(data.get("case_ids"), list):
            self.planned[:] = [str(item) for item in data["case_ids"]]


def run_supervised_worker(
    command: "list[str]",
    cwd: str,
    *,
    timeout_seconds: "Optional[int]" = None,
    forward_stdout: "Optional[TextIO]" = None,
    extra_env: "Optional[dict[str, str]]" = None,
    timeout_env_name: str = HELIX_EVAL_TIMEOUT_SECONDS,
    on_progress: "Optional[Callable[[Mapping[str, object]], None]]" = None,
) -> SupervisedRun:
    effective_timeout = eval_timeout_seconds() if timeout_seconds is None else timeout_seconds
    # Before the spawn: every artifact the worker writes is stamped later than
    # this, and every artifact an earlier run left behind is stamped earlier.
    started_at = time.time()
    process = subprocess.Popen(
        command,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=_merged_env(extra_env),
        **_process_group_popen_kwargs(),
    )
    collector, readers = _start_output_readers(process, forward_stdout, on_progress)
    timed_out, interrupted = _await_worker_exit(process, collector, effective_timeout)
    for reader in readers:
        reader.join(timeout=2)
    return _supervised_run_result(
        process,
        collector,
        timed_out=timed_out,
        interrupted=interrupted,
        started_at=started_at,
        effective_timeout=effective_timeout,
        timeout_env_name=timeout_env_name,
    )


def _start_output_readers(
    process: "subprocess.Popen[str]",
    forward_stdout: "Optional[TextIO]",
    on_progress: "Optional[Callable[[Mapping[str, object]], None]]",
) -> "tuple[_WorkerOutputCollector, list[threading.Thread]]":
    collector = _WorkerOutputCollector(process)
    readers = [
        threading.Thread(
            target=collector.read_stdout, args=(forward_stdout, on_progress), daemon=True
        ),
        threading.Thread(target=collector.read_stderr, daemon=True),
    ]
    for reader in readers:
        reader.start()
    return collector, readers


def _supervised_run_result(
    process: "subprocess.Popen[str]",
    collector: "_WorkerOutputCollector",
    *,
    timed_out: bool,
    interrupted: bool,
    started_at: float,
    effective_timeout: int,
    timeout_env_name: str,
) -> SupervisedRun:
    return_code = _resolved_returncode(process.returncode)
    stdout_text = "".join(collector.stdout_chunks)
    stderr_text = "".join(collector.stderr_chunks)
    if collector.final is None:
        return_code = 1
        stderr_text += _missing_final_note(
            timed_out, interrupted, effective_timeout, timeout_env_name, stderr_text
        )
    return SupervisedRun(
        records=collector.records,
        progress=collector.progress,
        final=collector.final,
        planned_case_ids=list(collector.planned),
        timed_out=timed_out,
        started_at=started_at,
        result=make_result(
            return_code=return_code,
            stdout=stdout_text,
            stderr=stderr_text,
            stalled=timed_out,
        ),
    )


def _await_worker_exit(
    process: "subprocess.Popen[Any]",
    collector: _WorkerOutputCollector,
    effective_timeout: int,
) -> "tuple[bool, bool]":
    """Wait for the worker; return (timed_out, interrupted)."""
    timed_out = False
    interrupted = False
    interrupting = False

    def _handle_parent_sigterm(signum: int, _frame: object) -> None:
        # Convert a parent-side SIGTERM into the same interrupt path as
        # Ctrl+C: kill the worker tree, keep partial records. Re-entrant
        # arrivals during cleanup are ignored.
        nonlocal interrupting
        if interrupting:
            return
        interrupting = True
        global _pending_termination_signal
        _pending_termination_signal = signum
        raise KeyboardInterrupt

    sigterm_handler_installed = False
    previous_sigterm_handler = signal.getsignal(signal.SIGTERM)
    try:
        signal.signal(signal.SIGTERM, _handle_parent_sigterm)
        sigterm_handler_installed = True
    except ValueError:
        # Signal registration is main-thread-only; supervisors on worker
        # threads (batch orchestration) rely on their orchestrator instead.
        pass

    try:
        while True:
            if process.poll() is not None:
                break
            if effective_timeout > 0 and collector.idle_seconds() > effective_timeout:
                timed_out = True
                terminate_process_tree(process)
                break
            time.sleep(0.05)
    except KeyboardInterrupt:
        interrupted = True
        terminate_process_tree(process)
    finally:
        if sigterm_handler_installed:
            signal.signal(signal.SIGTERM, previous_sigterm_handler)
    return timed_out, interrupted


def _missing_final_note(
    timed_out: bool,
    interrupted: bool,
    effective_timeout: float,
    timeout_env_name: str,
    stderr_text: str,
) -> str:
    """Render the stderr suffix for a worker that emitted no final line."""
    note = "Worker exited without emitting a final line."
    if timed_out:
        note = _timeout_message(effective_timeout, timeout_env_name)
    if interrupted:
        note = "Parent interrupted; worker was terminated."
    separator = "\n" if stderr_text and not stderr_text.endswith("\n") else ""
    return separator + note + "\n"


def run_remote_worker(
    spec: RemoteSpec,
    remote_workspace: str,
    remote_command: "Sequence[str]",
    *,
    extra_env: "Optional[Mapping[str, str]]" = None,
    verbose: bool = False,
    stderr: "Optional[TextIO]" = None,
    on_progress: "Optional[Callable[[Mapping[str, object]], None]]" = None,
) -> SupervisedRun:
    """Run the staged worker over an ssh session under the local supervisor.

    The supervisor spawns the ssh client locally; the remote worker's stdout
    streams back through ssh and resets the no-output timer, and terminating
    the ssh client tears down the remote session.  Without an explicit
    ``on_progress``, non-verbose runs default to ``print_prewarm_warning``
    so prewarm degradations surface live on remote runs too; verbose runs
    already forward the raw stream.
    """
    command = ssh_session_command(
        spec,
        remote_workspace,
        remote_command,
        extra_env=dict(extra_env) if extra_env is not None else None,
    )
    _maybe_emit_remote_command(command, verbose, stderr)
    if on_progress is None and not verbose:
        on_progress = print_prewarm_warning
    return run_supervised_worker(
        command,
        ".",
        timeout_seconds=eval_timeout_seconds(),
        forward_stdout=sys.stdout if verbose else None,
        on_progress=on_progress,
    )
