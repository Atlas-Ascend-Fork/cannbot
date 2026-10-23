# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Long-lived CANN analyse server for the deferred parse pipeline.

The deferred pipeline parses one rolling batch at a time, and a throwaway
interpreter per batch pays torch_npu's import plus process teardown every
time (5.5s of an 8.7s batch on the measured Ascend950PR host). This service
imports torch_npu once for a whole bench run and serves the batches instead:
docs/notes/implemented/2026-09-14-analyse-service-process.md.

Design constraints:

- **Single-threaded.** ``analyse()`` forks a process pool, and a pool forked
  from a multi-threaded parent inherits locked internals and deadlocks
  (docs/notes/implemented/2026-08-28-run-bench-deferred-parse-design.md).
  This process never starts a thread.
- **No torch_npu import at module level.** ``run_bench_execution`` imports
  this module so remote staging picks it up (the AST import closure in
  ``remote_python_bundle``), and the worker importing torch_npu would pay the
  very cost this service exists to amortize. The dependency is resolved at run
  time through ``importlib``, which also keeps the file type-checkable on hosts
  without torch_npu installed.
- **stdout/stderr belong to the running job's log**, never to the protocol.

Protocol, one JSON object per line:

- stdin: ``{"target": str, "workers": int, "deadline_s": float, "log": str}``
  per job, ``{"stop": true}`` to shut down.
- stdout: ``{"ready": true}`` once after the import, then
  ``{"rc": int, "seconds": float}`` per job.
"""

from __future__ import annotations

import importlib
import json
import os
import signal
import sys
import time
import traceback
from contextlib import contextmanager
from typing import Callable, Iterator, Optional, cast


def _emit(protocol_fd: int, payload: "dict[str, object]") -> None:
    os.write(protocol_fd, (json.dumps(payload) + "\n").encode("utf-8"))


def _request_str(request: "dict[str, object]", key: str) -> str:
    value = request.get(key)
    return value if isinstance(value, str) else str(value)


def _request_int(request: "dict[str, object]", key: str, default: int) -> int:
    value = request.get(key)
    return value if isinstance(value, int) else default


def _request_float(request: "dict[str, object]", key: str) -> float:
    value = request.get(key)
    return float(value) if isinstance(value, (int, float)) else 0.0


def _request_log(request: "dict[str, object]") -> Optional[str]:
    value = request.get("log")
    return value if isinstance(value, str) else None


def _load_analyse() -> "Callable[..., None]":
    """Resolve CANN's analyse() at run time; torch_npu is not importable here."""
    module = importlib.import_module("torch_npu.profiler.profiler")
    return cast("Callable[..., None]", getattr(module, "analyse"))


@contextmanager
def _redirect_job_output(log_path: Optional[str]) -> Iterator[None]:
    """Point this job's stdout/stderr (and its forked pool's) at its log."""
    if not log_path:
        yield
        return
    sys.stdout.flush()
    sys.stderr.flush()
    saved_stdout, saved_stderr = os.dup(1), os.dup(2)
    handle = -1
    try:
        handle = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        os.dup2(handle, 1)
        os.dup2(handle, 2)
    except OSError:
        # A long-lived process must not accumulate duplicated descriptors when
        # the redirect fails.
        if handle >= 0:
            os.close(handle)
        os.close(saved_stdout)
        os.close(saved_stderr)
        raise
    try:
        yield
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
        os.dup2(saved_stdout, 1)
        os.dup2(saved_stderr, 2)
        os.close(saved_stdout)
        os.close(saved_stderr)
        os.close(handle)


def _arm_job_deadline(seconds: float) -> None:
    """Bound one job even when the parent is gone: kill our process group."""
    if seconds <= 0:
        return

    def _kill_job(_signum: int, _frame: object) -> None:
        # killpg 失败（如进程组已不存在）时让 OSError 直接终止进程。
        os.killpg(0, signal.SIGKILL)

    signal.signal(signal.SIGALRM, _kill_job)
    signal.alarm(int(seconds))


def _serve_job(request: "dict[str, object]") -> int:
    analyse = _load_analyse()
    with _redirect_job_output(_request_log(request)):
        _arm_job_deadline(_request_float(request, "deadline_s"))
        try:
            analyse(
                _request_str(request, "target"),
                max_process_number=_request_int(request, "workers", 1),
                export_type="text",
            )
        except Exception:
            # The traceback lands in this job's log, which is what the parent
            # reads for its failure diagnostic; one bad job must not end the
            # service.
            traceback.print_exc()
            return 1
        finally:
            signal.alarm(0)
    return 0


def main() -> int:
    protocol_fd = os.dup(1)
    _load_analyse()  # import once: the cost this service exists to amortize

    _emit(protocol_fd, {"ready": True})
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        request = cast("dict[str, object]", json.loads(line))
        if request.get("stop"):
            return 0
        started = time.monotonic()
        try:
            return_code = _serve_job(request)
        except Exception:
            traceback.print_exc()
            return_code = 1
        _emit(protocol_fd, {"rc": return_code, "seconds": time.monotonic() - started})
    return 0


if __name__ == "__main__":
    sys.exit(main())
