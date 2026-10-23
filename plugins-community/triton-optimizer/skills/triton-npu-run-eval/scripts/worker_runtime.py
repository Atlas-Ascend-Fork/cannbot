# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Composition object shared by the unified worker's action functions.

The worker's interface to its parent is its CLI plus the stdout line
protocol — not a Python class. The genuinely shared behavior (emission,
child registry, SIGTERM cleanup) composes into this runtime; the per-command
difference is the case loop, which stays in the execution modules.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
from typing import Any, Mapping, Optional, TextIO

import worker_protocol as protocol
from run_runtime import terminate_process_tree

# One lock for every protocol line this process prints: the deferred-parse
# pipeline emits from its parser thread while the main thread keeps profiling,
# and an interleaved write would corrupt both lines past recovery.
_EMIT_LOCK = threading.Lock()


class _WorkerTerminated(BaseException):
    """Raised from the SIGTERM handler to unwind after children are killed.

    Uncaught by design: the worker exits with code 1 and a traceback, never
    emitting a ``final`` protocol line (an abrupt exit is the failure signal).
    """


class WorkerRuntime:
    def __init__(self, phase: str = "", stream: Optional[TextIO] = None) -> None:
        self._phase = phase
        self._stream = stream if stream is not None else sys.stdout
        self._protocol_fd = self._open_protocol_channel()
        self._children: "list[subprocess.Popen[Any]]" = []

    def emit_case(self, record: Mapping[str, object]) -> None:
        self._write_protocol(protocol.encode_case(self._phase, record) + "\n")

    def emit_progress(self, event: str, **detail: object) -> None:
        self._write_protocol(protocol.encode_progress(self._phase, event, detail) + "\n")

    def emit_passthrough(self, text: str) -> None:
        """Print *text* as plain worker output with protocol defusing.

        Worker stdout is the protocol channel: the supervisor decodes every
        line and the first decodable ``final`` envelope wins.  Text produced
        by compared code (native reference replay, libraries) must never
        impersonate an envelope, so any line that would decode as a protocol
        message is prefixed to defuse it.
        """
        for line in text.splitlines(keepends=True):
            if protocol.decode_message(line) is not None:
                line = f"| {line}"
            self._write_protocol(line)

    def emit_final(self, payload: Mapping[str, object]) -> None:
        self._write_protocol(protocol.encode_final(self._phase, payload) + "\n")

    def register_child(self, child: "subprocess.Popen[Any]") -> None:
        self._children.append(child)

    def unregister_child(self, child: "subprocess.Popen[Any]") -> None:
        if child in self._children:
            self._children.remove(child)

    def kill_registered_children(self) -> None:
        for child in list(self._children):
            if getattr(child, "poll", lambda: None)() is None:
                terminate_process_tree(child)

    def arm_sigterm_exit(self) -> None:
        """SIGTERM: kill registered children, exit 1, never emit ``final``."""
        signal.signal(signal.SIGTERM, self._handle_sigterm)

    def _handle_sigterm(self, signum: int, frame: object) -> None:
        self.kill_registered_children()
        # Deliberate raise inside a signal handler: SIGTERM must end the worker
        # immediately after the children are gone, without emitting a final
        # protocol line (an abrupt exit is the failure signal).
        raise _WorkerTerminated()

    def _open_protocol_channel(self) -> Optional[int]:
        """A private fd on the protocol stream, or ``None`` when it has none.

        Taken once, here, before any profiled case runs: the profiler window
        points fds 1 and 2 at /dev/null (see ``_write_protocol``), so a
        duplicate taken inside that window would capture /dev/null instead of
        the supervisor's pipe.

        ``None`` for a stream without an fd — the unit tests' ``StringIO`` —
        and the stream object is then the whole output path.
        """
        try:
            return os.dup(self._stream.fileno())
        except (AttributeError, OSError, ValueError):
            return None

    def _write_protocol(self, text: str) -> None:
        """Write protocol text to a channel the profiler's redirection cannot move.

        ``run_bench_execution._suppress_output_streams`` points fds 1 and 2 at
        /dev/null for the whole window of every profiled case.  ``dup2`` is
        process-wide, not thread-local, so it also swallowed whatever the
        deferred pipeline's parser thread emitted from inside that window — and
        that thread is where the ``case`` records of every batch after the first
        come from.  Writing to a duplicate of the *original* fd 1 keeps the
        channel pointed at the supervisor's pipe regardless of what the profiler
        does to fd 1, so no record depends on which thread emits it or on when
        a batch happens to finish parsing.
        """
        with _EMIT_LOCK:
            if self._protocol_fd is None:
                print(text, end="", file=self._stream, flush=True)
                return
            payload = text.encode("utf-8")
            while payload:
                payload = payload[os.write(self._protocol_fd, payload):]


class NullWorkerRuntime(WorkerRuntime):
    """Default emit target so execution loops keep their old signatures usable."""

    def emit_case(self, record: Mapping[str, object]) -> None:
        return

    def emit_progress(self, event: str, **detail: object) -> None:
        return

    def emit_passthrough(self, text: str) -> None:
        return

    def emit_final(self, payload: Mapping[str, object]) -> None:
        return

    def kill_registered_children(self) -> None:
        return

    def arm_sigterm_exit(self) -> None:
        return

    def _open_protocol_channel(self) -> Optional[int]:
        # Every emit is a no-op, so this runtime must not spend a descriptor.
        return None
