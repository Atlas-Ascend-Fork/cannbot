#!/usr/bin/env python3
# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------
"""
dispatch_round.py — 启动一个独立的子 Claude Code CLI 执行单个 round。

用法:
    python3 dispatch_round.py \
        --manifest triton_ascend_output/{op_name}-{algorithm}-{run_tag}/.task_manifest_{N}.json \
        [--timeout 7200] \
        [--command-template 'claude -p --plugin-dir {plugin_dir} '
                            '--system-prompt-file {sub_reference} --allowed-tools Bash,Read,Write,Edit,Glob,Grep '
                            '"Execute round worker. Manifest: {manifest_path}"']

环境变量:
    TRITON_WORKER_COMMAND_TEMPLATE: 覆盖默认命令模板
    TRITON_WORKER_TIMEOUT_SECONDS:  覆盖默认超时
    TRITON_NPU_DEVICE_ID:           显式指定要使用的 NPU 设备 ID（需空闲）
    TRITON_SKIP_NPU_IDLE_CHECK:     设置为 1/true/yes 时跳过空闲卡检测
    TRITON_NPU_IDLE_MAX_AICORE:     AICore 空闲阈值（默认 1%）
    TRITON_NPU_IDLE_MAX_AIVECTOR:   AIVector 空闲阈值（默认 1%）
    TRITON_NPU_IDLE_MAX_NPU_UTIL:   NPU 利用率空闲阈值（默认 1%）
    TRITON_NPU_IDLE_MAX_HBM:        HBM 使用空闲阈值（默认 10%）

输出 (JSON):
    {
        "status": "success" | "timeout" | "error" | "no_result",
        "round_result": { ... },
        "stdout": "...",
        "stderr": "...",
        "returncode": 0,
        "pid": 12345
    }
"""

import argparse
import json
import logging
import os
import shlex
import shutil
import signal
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from log_parser import StreamJsonReadableParser
import check_npu_idle
import preflight as preflight_mod

logger = logging.getLogger(__name__)


# Sub-directories of .claude/ that the worker needs locally so it can run
# with cwd=work_dir without requiring write access to the plugin root.
CLAUDE_RESOURCE_DIRS = ("skills", "template", "references")


DEFAULT_TIMEOUT_SECONDS = int(os.environ.get("TRITON_WORKER_TIMEOUT_SECONDS", "7200"))

DEFAULT_COMMAND_TEMPLATE = (
    'claude -p '
    '--permission-mode auto '
    '--output-format stream-json '
    '--include-partial-messages '
    '--include-hook-events '
    '--verbose '
    '--system-prompt-file {sub_reference} '
    '"Execute triton-auto-evolve round worker. Read manifest: {manifest_path}" '
    '--allowed-tools Bash Read Write Edit Glob Grep'
)


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc


def resolve_plugin_dir() -> Path:
    """Resolve plugin root relative to this script."""
    script_path = Path(__file__).resolve()
    # skills/triton-agent-loop/scripts/dispatch_round.py -> plugin root
    return script_path.parents[3]


def resolve_kb_root(start_dir: Path) -> Path | None:
    """Return the knowledge-card root of the cloned cannbot-knowledge repo.

    Knowledge content lives ONLY in the cannbot-knowledge checkout (never
    inside a skill directory).  Resolution order mirrors
    ``plugins-official/triton-op-generator``:

    1. ``CANNBOT_KNOWLEDGE_ROOT`` environment variable (must exist),
    2. probing ``.cannbot/dependencies/*/cannbot-knowledge/knowledge`` from
       ``start_dir`` and up to six ancestor directories (the path written by
       ``init.sh`` / the unified installer),
    3. ``None`` — the worker then runs in skeleton mode (warn only).
    """
    env_root = os.environ.get("CANNBOT_KNOWLEDGE_ROOT", "")
    if env_root:
        candidate = Path(env_root)
        if candidate.is_dir():
            return candidate

    search_dir = start_dir.resolve()
    for _ in range(7):  # start_dir itself plus six ancestors
        for candidate in sorted(search_dir.glob(".cannbot/dependencies/*/cannbot-knowledge/knowledge")):
            if candidate.is_dir():
                return candidate
        if search_dir.parent == search_dir:
            break
        search_dir = search_dir.parent

    return None


def resolve_claude_root(plugin_dir: Path, work_dir: Path) -> Path:
    """Find the resource root used by this project.

    The ``references`` directory is the completeness anchor: it holds the
    plugin's own scheduling specs (``orchestrator-loop.md``, per-algorithm
    ``round.md``) and ships WITH the plugin — it is *not* knowledge content.
    Knowledge cards live solely in the cannbot-knowledge checkout and resolve
    separately via :func:`resolve_kb_root`.

    Candidates:

    1. ``.claude`` under work_dir ancestors — the project install written by
       ``init.sh`` (its ``references`` is a symlink to the plugin's specs);
    2. ``.claude`` under the current working directory;
    3. the plugin root itself — a bare source checkout carries ``skills/`` and
       ``references/`` at its root, so a worker can run straight from the repo
       even when ``plugin_dir/.claude`` was never populated (init.sh only
       writes ``settings.json`` there).
    """
    candidates: list[Path] = []

    # 1) Walk up from work_dir (covers project-directory installs).
    resolved_work = work_dir.resolve()
    for parent in resolved_work.parents:
        candidates.append(parent / ".claude")

    # 2) Current working directory (e.g. when work_dir is a temporary path).
    candidates.append(Path.cwd() / ".claude")

    # 3) Plugin root as final fallback (bare checkout: resources at the root).
    candidates.append(plugin_dir)

    for candidate in candidates:
        if candidate.is_dir() and (candidate / "references").exists():
            return candidate

    raise FileNotFoundError(
        f"Cannot find installed .claude resources. "
        f"Tried candidates: {candidates}. Please run init.sh in the project directory first."
    )


def prepare_isolated_claude(work_dir: Path, plugin_dir: Path) -> Path:
    """Copy installed ``.claude`` resources into ``work_dir/.claude``.

    The worker runs with ``cwd=work_dir``.  Giving it a local copy of the
    ``.claude/`` subtree keeps it isolated: it does not need write access to
    the plugin root and any accidental modifications only affect the copy.

    Knowledge cards are not part of this copy: they live in the shared
    cannbot-knowledge checkout under ``.cannbot/dependencies/`` (resolved via
    :func:`resolve_kb_root`), so nothing accumulates inside the worker's
    resource tree.
    """
    src_claude = resolve_claude_root(plugin_dir, work_dir)
    dst_claude = work_dir / ".claude"
    dst_claude.mkdir(parents=True, exist_ok=True)

    for name in CLAUDE_RESOURCE_DIRS:
        src = src_claude / name
        if not src.exists():
            continue
        dst = dst_claude / name
        if dst.exists():
            shutil.rmtree(dst, ignore_errors=True)
        shutil.copytree(src, dst, symlinks=False)

    # Warn but do not fail: the worker can still run without the knowledge
    # base (skeleton mode, round docs mark phases as kb_unavailable).
    if resolve_kb_root(work_dir) is None:
        logger.warning(
            "cannbot-knowledge checkout not found near %s; "
            "workers run in skeleton mode (kb_unavailable)",
            work_dir,
        )

    settings_src = src_claude / "settings.json"
    if settings_src.is_file():
        shutil.copy2(settings_src, dst_claude / "settings.json")

    return dst_claude


def build_command(
    manifest_path: Path,
    work_dir: Path,
    command_template: str | None = None,
) -> str:
    plugin_dir = resolve_plugin_dir()

    # Read the manifest to find the algorithm-specific reference document.
    manifest = load_json(manifest_path)
    reference_path = manifest.get("algorithm_reference") or manifest.get("worker_reference")
    if not reference_path:
        reference_path = ".claude/references/algorithms/naive/round.md"

    # Prefer the isolated copy so the worker's reference files live inside
    # work_dir.  Fall back to the installed .claude root before
    # prepare_isolated_claude has run (e.g. custom command templates).
    sub_reference = work_dir / reference_path
    if not sub_reference.is_file():
        try:
            claude_root = resolve_claude_root(plugin_dir, work_dir)
            # reference_path starts with ".claude/"; claude_root is already the
            # .claude directory, so strip the leading ".claude/" segment.
            relative_reference = Path(reference_path).relative_to(".claude")
            sub_reference = claude_root / relative_reference
        except (FileNotFoundError, ValueError):
            sub_reference = plugin_dir / reference_path

    if not sub_reference.is_file():
        raise FileNotFoundError(
            f"Algorithm reference not found: {reference_path} "
            f"(tried work_dir={work_dir / reference_path}, "
            f"claude_root={claude_root if 'claude_root' in locals() else 'n/a'}, "
            f"plugin_dir={plugin_dir / reference_path})"
        )

    template = command_template or os.environ.get(
        "TRITON_WORKER_COMMAND_TEMPLATE", DEFAULT_COMMAND_TEMPLATE
    )

    # Support shell-style quoting in template by using shell=True
    cmd = template.format(
        manifest_path=str(manifest_path),
        work_dir=str(work_dir),
        plugin_dir=str(plugin_dir),
        reference_dir=str(work_dir / ".claude" / "references"),
        sub_reference=str(sub_reference),
    )
    return cmd


def _terminate_process_tree(proc: subprocess.Popen[str], hard: bool = False) -> None:
    """A4: 整组击杀（start_new_session 的子进程自成一组），失败退回直杀。

    只 terminate/kill 直接子进程（shell 或 claude CLI）时，其存活中的 bash
    子进程会孤儿化并继承 stdout 管道写端，_stream_subprocess 末尾的读线程
    join 因 EOF 永不到来而挂死。
    """
    sig = signal.SIGKILL if hard else signal.SIGTERM
    try:
        os.killpg(os.getpgid(proc.pid), sig)
    except (ProcessLookupError, PermissionError):
        try:
            proc.send_signal(sig)
        except ProcessLookupError:
            pass
    except OSError:
        try:
            proc.send_signal(sig)
        except ProcessLookupError:
            pass


def _stream_reader(stream, prefix: str, chunks: list[str], log_f, parser) -> None:
    """Read one stream line-by-line into chunks and the log/parser."""
    for line in iter(stream.readline, ""):
        chunks.append(line)
        formatted = f"{prefix}{line}"
        log_f.write(formatted)
        log_f.flush()
        if parser is not None:
            parser.feed_line(formatted)


def _wait_for_completion(
    proc: subprocess.Popen[str],
    deadline: float | None,
    completion_signal: Path | None,
    completion_grace: float,
    signal_floor: float,
) -> tuple[int, bool, bool]:
    """Wait for the subprocess exit or completion signal; returns (rc, timed_out, harvested)."""
    grace_started: float | None = None
    while True:
        try:
            rc = proc.wait(timeout=0.5)
            return rc, False, False
        except subprocess.TimeoutExpired:
            pass
        if deadline is not None and time.monotonic() >= deadline:
            _terminate_process_tree(proc, hard=True)
            return proc.wait(), True, False
        if completion_signal is None or completion_grace <= 0:
            continue
        try:
            signal_mtime = completion_signal.stat().st_mtime
        except OSError:
            continue
        if signal_mtime < signal_floor:
            continue
        if grace_started is None:
            grace_started = time.monotonic()
            continue
        if time.monotonic() - grace_started < completion_grace:
            continue
        _terminate_process_tree(proc, hard=False)
        try:
            rc = proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            _terminate_process_tree(proc, hard=True)
            rc = proc.wait()
        return rc, False, True


@dataclass
class CompletionCfg:
    """Gene-fusion completion-signal harvest configuration."""

    signal: Path | None = None
    grace: float = 0.0
    floor: float = 0.0


@dataclass
class StreamCtx:
    """Everything needed to stream a sub CLI run to disk and harvest it."""

    proc: subprocess.Popen[str]
    work_dir: Path
    cmd: str
    timeout: int | None
    completion: CompletionCfg


def _stream_subprocess(ctx: StreamCtx) -> tuple[int, str, str, bool, bool]:
    """Stream sub CLI stdout/stderr to disk while the round is running."""
    proc, work_dir = ctx.proc, ctx.work_dir
    cmd, timeout = ctx.cmd, ctx.timeout
    completion = ctx.completion
    log_path = work_dir / "sub_agent.log"
    readable_log_path = work_dir / "sub_agent_readable.log"
    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []
    timed_out = False
    harvested = False

    with open(log_path, "w", encoding="utf-8") as log_f, \
         open(readable_log_path, "w", encoding="utf-8") as readable_f:
        log_f.write(f"# Command: {cmd}\n")
        log_f.write(f"# CWD: {work_dir}\n")
        log_f.write(f"# Timeout: {timeout}s\n")
        log_f.write("-" * 80 + "\n")
        log_f.flush()

        parser = StreamJsonReadableParser(readable_f)
        t_out = threading.Thread(
            target=_stream_reader,
            args=(proc.stdout, "[sub-agent stdout] ", stdout_chunks, log_f, parser),
            daemon=True,
        )
        t_err = threading.Thread(
            target=_stream_reader,
            args=(proc.stderr, "[sub-agent stderr] ", stderr_chunks, log_f, parser),
            daemon=True,
        )
        t_out.start()
        t_err.start()

        deadline = time.monotonic() + timeout if timeout else None
        rc, timed_out, harvested = _wait_for_completion(
            proc, deadline, completion.signal, completion.grace, completion.floor
        )

        t_out.join()
        t_err.join()
        parser.flush()

        log_f.write("\n" + "-" * 80 + "\n")
        log_f.write(f"# Exit code: {rc}  timed_out={timed_out}  harvested={harvested}\n")
        log_f.flush()

    return rc, "".join(stdout_chunks), "".join(stderr_chunks), timed_out, harvested


@contextmanager
def _child_process_scope(proc: subprocess.Popen[str]):
    """Forward SIGINT/SIGTERM to the child and ensure it is reaped.

    This reduces the chance that a sub-agent keeps running as an orphan after
    the main orchestrator is stopped.
    """
    old_sigint = signal.signal(signal.SIGINT, signal.SIG_IGN)
    old_sigterm = signal.signal(signal.SIGTERM, signal.SIG_IGN)

    def _forward(signum: int, frame: Any) -> None:
        try:
            if proc.poll() is None:
                proc.send_signal(signum)
        except ProcessLookupError:
            pass

    def _cleanup() -> None:
        if proc.poll() is not None:
            return
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
                proc.wait(timeout=5)
            except Exception as exc:
                logger.warning("failed to kill process tree: %s", exc)

    try:
        signal.signal(signal.SIGINT, _forward)
        signal.signal(signal.SIGTERM, _forward)
        yield
    finally:
        _cleanup()
        signal.signal(signal.SIGINT, old_sigint)
        signal.signal(signal.SIGTERM, old_sigterm)


def wait_for_round_result(work_dir: Path, timeout: float, interval: float = 2.0) -> Path | None:
    """Poll for round_result.json until it appears or timeout."""
    result_path = work_dir / "round_result.json"
    elapsed = 0.0
    while elapsed < timeout:
        if result_path.is_file():
            return result_path
        time.sleep(interval)
        elapsed += interval
    return None


def _run_worker_preflight(timeout: float = 30.0, attempts: int = 2) -> dict[str, Any]:
    """A3: 派发前 ~30s 预检模型可用性。

    与 worker 命令模板同形态（裸 ``claude --print``，模型由 claude settings
    解析，不带 --model），因此预检通过即代表 worker CLI 能正常出字。
    瞬时故障（网关抖动）重试 ``attempts`` 次，全部失败才判不可派发，
    避免一次网络抖动误杀整轮。
    """
    data: dict[str, Any] | None = None
    error: str | None = None
    elapsed = 0.0
    used = 0
    for attempt in range(max(attempts, 1)):
        used = attempt + 1
        data, error, elapsed = preflight_mod.run_claude(
            "Reply with exactly one word: ok", None, timeout
        )
        if error is None:
            break
        if attempt + 1 < max(attempts, 1):
            time.sleep(5)
    model_ok = False
    if error is None and data is not None:
        text = str(data.get("result") or "").strip()
        if data.get("is_error"):
            error = f"model returned error: {text[:200]}"
        elif not text:
            error = f"empty response (subtype={data.get('subtype', '?')})"
        else:
            model_ok = True
    return {
        "model_ok": model_ok,
        "model": "inherit-from-claude-settings",
        "latency_s": round(elapsed, 2),
        "attempts_used": used,
        "error": error,
    }


def _round_dir_key(path: Path) -> tuple[int, int]:
    """round_N 目录的数值排序键（round_2 < round_10）。"""
    try:
        return (0, int(path.name.rsplit("_", 1)[-1]))
    except ValueError:
        return (1, 0)


def _iter_summary(iter_dir: Path) -> dict[str, Any] | None:
    """A5: 从 route 的 ``output/round_N/`` 提取一次完成迭代的结论摘要。

    ``perf_result.json`` 存在视为该迭代完成（benchmark 跑完是迭代的最后一步）；
    字段全部 best-effort 提取，缺啥省啥，不让对账失败阻塞续跑。
    """
    perf_path = iter_dir / "perf_result.json"
    if not perf_path.is_file():
        return None  # 无 perf = 迭代未完成（正是断点场景），跳过
    perf = load_json(perf_path)
    if not perf:
        return None
    fw = (perf.get("framework") or {}).get("avg_latency_ms")
    impl = (perf.get("implementation") or {}).get("avg_latency_ms")
    speedup = None
    try:
        if fw and impl:
            speedup = round(float(fw) / float(impl), 4)
    except (TypeError, ValueError, ZeroDivisionError):
        speedup = None
    verify_path = iter_dir / "verify" / "verify_result.json"
    verify = load_json(verify_path) if verify_path.is_file() else {}
    total = perf.get("total_cases")
    passed = verify.get("passed_cases", perf.get("passed_cases"))
    precision_pass = None
    try:
        if total is not None and passed is not None:
            precision_pass = int(passed) == int(total)
    except (TypeError, ValueError):
        precision_pass = None
    try:
        iteration = int(iter_dir.name.rsplit("_", 1)[-1])
    except ValueError:
        return None
    return {
        "iteration": iteration,
        "speedup": speedup,
        "precision_pass": precision_pass,
        "framework_avg_ms": fw,
        "implementation_avg_ms": impl,
        "perf_cases": f"{passed}/{total}" if passed is not None else None,
        "artifacts_dir": f"output/round_{iteration}",
    }


def _build_resume_context(work_dir: Path) -> dict[str, Any] | None:
    """A5: 扫描各 route 已完成迭代（重派断点续跑用），无完成迭代返回 None。

    完成判定：``route-*/output/round_N/perf_result.json`` 存在。
    整条 route 已写出 ``round_result.json`` 时标记 ``finished``，续跑方直接
    收割不再迭代。
    """
    routes: dict[str, Any] = {}
    for route_dir in sorted(work_dir.glob("route-*")):
        out_dir = route_dir / "output"
        if not out_dir.is_dir():
            continue
        summaries = [
            s for s in (_iter_summary(d) for d in sorted(out_dir.glob("round_*"), key=_round_dir_key))
            if s is not None
        ]
        finished = (route_dir / "round_result.json").is_file()
        if not summaries and not finished:
            continue
        entry: dict[str, Any] = {"finished": finished}
        if summaries:
            entry["completed"] = summaries
            entry["next_iteration"] = max(s["iteration"] for s in summaries) + 1
        routes[route_dir.name] = entry
    if not routes:
        return None
    return {
        "purpose": "resume_after_redispatch: completed iterations below must NOT be redone",
        "routes": routes,
    }


def _select_npu_device(env: dict[str, str], work_dir: Path, result: dict[str, Any]) -> dict[str, Any] | None:
    """Select an idle NPU device and set env vars; returns an error dict on failure."""
    npu_idle_check_enabled = not check_npu_idle.should_skip_idle_check()
    if npu_idle_check_enabled and shutil.which("npu-smi") is None:
        result["npu_idle_check"] = "skipped: npu-smi not found on this host"
        npu_idle_check_enabled = False
    if not npu_idle_check_enabled:
        return None
    try:
        device_info = check_npu_idle.select_idle_device(
            preferred_id=check_npu_idle.preferred_device_id()
        )
    except check_npu_idle.NpuIdleCheckError as exc:
        return {
            "status": "error",
            "stderr": (
                f"NPU idle check failed: {exc}\n"
                f"details: {json.dumps(exc.details, indent=2, ensure_ascii=False)}"
            ),
        }
    device_id = device_info["device_id"]
    env["ASCEND_VISIBLE_DEVICES"] = str(device_id)
    env["NPU_CALCULATE_DEVICE"] = str(device_id)
    env["ASCEND_RT_VISIBLE_DEVICES"] = str(device_id)
    try:
        (work_dir / "npu_device.json").write_text(
            json.dumps(device_info, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except OSError:
        pass
    return None


def _stream_and_check(ctx: StreamCtx, result: dict[str, Any]) -> bool:
    """Stream the subprocess and check timeout; returns True if the round timed out."""
    with _child_process_scope(ctx.proc):
        returncode, stdout, stderr, timed_out, harvested = _stream_subprocess(ctx)
    result["stdout"] = stdout
    result["stderr"] = stderr
    result["returncode"] = returncode
    if harvested:
        result["completed_via_signal"] = True
    if timed_out:
        result["status"] = "timeout"
    return timed_out


def _launch_subprocess(
    cmd: str, work_dir: Path, env: dict[str, str], result: dict[str, Any],
) -> subprocess.Popen | None:
    """Launch the sub CLI; returns None and sets result.stderr on failure."""
    try:
        return subprocess.Popen(
            shlex.split(cmd),
            shell=False,
            cwd=work_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            start_new_session=True,
        )
    except OSError as exc:
        result["stderr"] = f"failed to start sub CLI: {exc}"
        return None


def _collect_round_result(work_dir: Path, result: dict[str, Any]) -> None:
    """Wait for round_result.json and load it into result."""
    result_path = wait_for_round_result(work_dir, timeout=30.0)
    if result_path is None:
        candidates = list(work_dir.glob("round_result.json"))
        if candidates:
            result_path = candidates[0]
    if result_path is None or not result_path.is_file():
        result["status"] = "no_result"
        return
    try:
        round_result = load_json(result_path)
        result["round_result"] = round_result
        result["status"] = "success"
    except ValueError as exc:
        result["status"] = "error"
        result["stderr"] += f"\nfailed to parse round_result.json: {exc}"


def _resolve_completion_signal(
    manifest: dict[str, Any], work_dir: Path,
) -> CompletionCfg:
    """Resolve the gene-fusion completion signal and grace period."""
    completion_signal = None
    completion_grace = 0.0
    signal_floor = time.time()
    if manifest.get("algorithm") == "gene-fusion":
        completion_signal = work_dir / "round_result.json"
        try:
            completion_grace = float(os.environ.get("TRITON_ROUND_COMPLETION_GRACE", "60"))
        except ValueError:
            completion_grace = 60.0
    return CompletionCfg(signal=completion_signal, grace=completion_grace, floor=signal_floor)


def _prepare_gene_fusion(
    manifest: dict[str, Any], manifest_path: Path, work_dir: Path, result: dict[str, Any],
) -> dict[str, Any] | None:
    """Run gene-fusion preflight and resume-context injection; returns error dict on preflight failure."""
    if manifest.get("algorithm") == "gene-fusion" and os.environ.get("TRITON_SKIP_PREFLIGHT") != "1":
        preflight = _run_worker_preflight()
        result["preflight"] = preflight
        if not preflight.get("model_ok"):
            return {
                "stderr": "preflight failed, dispatch aborted: "
                + json.dumps(preflight, ensure_ascii=False),
            }
    if manifest.get("algorithm") == "gene-fusion":
        resume_context = _build_resume_context(work_dir)
        if resume_context:
            manifest["resume_context"] = resume_context
            try:
                manifest_path.write_text(
                    json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
                )
            except OSError:
                pass
    return None


def dispatch_round(
    manifest_path: Path,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    command_template: str | None = None,
) -> dict[str, Any]:
    """Spawn a sub CLI to execute the round and return the parsed result.

    Before launching, installed ``.claude`` resources (skills, template,
    references, settings.json) are copied into ``work_dir/.claude``.  The sub
    CLI then runs with ``cwd=work_dir`` so the worker resolves all
    ``.claude/...`` paths locally and does not need write access to the plugin
    root.
    """
    manifest = load_json(manifest_path)
    plugin_dir = resolve_plugin_dir()
    work_dir = Path(manifest.get("work_dir", manifest_path.parent)).expanduser().resolve()
    work_dir.mkdir(parents=True, exist_ok=True)

    result: dict[str, Any] = {
        "status": "error",
        "round_result": None,
        "stdout": "",
        "stderr": "",
        "returncode": None,
        "pid": None,
    }

    # ── A3/A5: gene-fusion 派发前预检 + 断点续跑上下文注入 ──
    gf_error = _prepare_gene_fusion(manifest, manifest_path, work_dir, result)
    if gf_error is not None:
        result.update(gf_error)
        return result

    prepare_isolated_claude(work_dir, plugin_dir)

    cmd = build_command(manifest_path, work_dir, command_template)

    env = os.environ.copy()
    env["TRITON_OPTIMIZER_MODE"] = "worker"

    # ── Idle NPU selection (must run before launching the worker) ──
    npu_error = _select_npu_device(env, work_dir, result)
    if npu_error is not None:
        result.update(npu_error)
        return result

    # ── A4: gene-fusion 完成信号收割（round_result.json 落盘即视为完成） ──
    completion = _resolve_completion_signal(manifest, work_dir)

    proc = _launch_subprocess(cmd, work_dir, env, result)
    if proc is None:
        return result

    result["pid"] = proc.pid

    timed_out = _stream_and_check(
        StreamCtx(proc=proc, work_dir=work_dir, cmd=cmd, timeout=timeout, completion=completion), result,
    )
    if timed_out:
        return result

    # Wait a bit for round_result.json flush, then load it.
    _collect_round_result(work_dir, result)
    return result


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(description="Dispatch a per-round worker sub CLI")
    parser.add_argument("--manifest", required=True, help="Path to task_manifest.json")
    parser.add_argument(
        "--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS,
        help="Sub CLI timeout in seconds (default: 7200)",
    )
    parser.add_argument("--command-template", default=None, help="Shell command template for launching sub CLI")
    args = parser.parse_args()

    manifest_path = Path(args.manifest).expanduser().resolve()
    if not manifest_path.is_file():
        sys.stdout.write(json.dumps({
            "status": "error",
            "stderr": f"manifest not found: {manifest_path}",
        }) + "\n")
        return 1

    result = dispatch_round(manifest_path, args.timeout, args.command_template)
    sys.stdout.write(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    return 0 if result["status"] == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
