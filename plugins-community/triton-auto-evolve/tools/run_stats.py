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
"""run_stats.py — triton-auto-evolve 运行统计：token 用量 + 流程运行时间。

主 round 子 CLI（dispatch_round.py, stream-json）与 gene-fusion route 子 CLI
（dispatch_parallel.py, json）的 usage 都不会完整落盘，但所有子 CLI 均以 work_dir
为 cwd 运行，其会话 transcript 会写入 ~/.claude/projects/<slug>/*.jsonl。本脚本
扫描属于指定 op 工作区的 transcript，聚合 token 用量，并统计流程运行时间。

用法:
    python3 tools/run_stats.py \
        --op-dir triton_ascend_output/3_FusionAttention-gene-fusion-gf1021 \
        [--start-epoch 1761012345 | --start-epoch-file path] \
        [--claude-projects ~/.claude/projects] \
        [--out <op-dir>/run_stats.json]

输出:
    - 向 stdout 打印一行 JSON 摘要（供 orchestrator 每次进展检查输出）
    - 详细统计写入 <op-dir>/run_stats.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TOKEN_KEYS = (
    "input_tokens",
    "output_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
)


def _norm(text: str) -> str:
    """小写并去除所有非字母数字，规避 slug 化对 '/' '_' '.' 的不同处理。"""
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _entry_epoch(entry: dict[str, Any]) -> float | None:
    ts = entry.get("timestamp")
    if not isinstance(ts, str):
        return None
    try:
        return datetime.strptime(ts.replace("Z", "+0000"), "%Y-%m-%dT%H:%M:%S.%f%z").timestamp()
    except ValueError:
        try:
            return datetime.strptime(ts.replace("Z", "+0000"), "%Y-%m-%dT%H:%M:%S%z").timestamp()
        except ValueError:
            return None


def _add_usage(target: dict[str, int], usage: dict[str, Any]) -> None:
    for key in TOKEN_KEYS:
        value = usage.get(key)
        if isinstance(value, (int, float)):
            target[key] = int(target.get(key, 0) + value)


def _empty_usage() -> dict[str, int]:
    return {key: 0 for key in TOKEN_KEYS}


ROUND_RE = re.compile(re.escape(_norm("opt-round-")) + r"(\d+)")


def _scan_transcript(
    transcript: Path, cwd_slug: str, round_index: int | None, start_epoch: float | None
) -> dict[str, Any] | None:
    """扫描单个 transcript，返回会话统计；无 assistant usage 或不可读时返回 None。"""
    try:
        lines = transcript.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    usage = _empty_usage()
    first_ts: float | None = None
    last_ts: float | None = None
    assistant_msgs = 0
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        epoch = _entry_epoch(entry)
        if epoch is not None:
            if start_epoch is not None and epoch < start_epoch:
                continue  # 本轮 run 之前的旧会话不计入
            first_ts = epoch if first_ts is None else min(first_ts, epoch)
            last_ts = epoch if last_ts is None else max(last_ts, epoch)
        if entry.get("type") != "assistant":
            continue
        message = entry.get("message") or {}
        msg_usage = message.get("usage")
        if isinstance(msg_usage, dict) and any(
            isinstance(msg_usage.get(k), (int, float)) for k in TOKEN_KEYS
        ):
            _add_usage(usage, msg_usage)
            assistant_msgs += 1
    if assistant_msgs == 0:
        return None
    return {
        "transcript": str(transcript),
        "cwd_slug": cwd_slug,
        "round": round_index,
        "assistant_messages": assistant_msgs,
        "usage": usage,
        "total_tokens": sum(usage.values()),
        "first_ts": first_ts,
        "last_ts": last_ts,
        "active_seconds": (
            round(last_ts - first_ts, 1)
            if first_ts is not None and last_ts is not None
            else None
        ),
    }


def scan_transcripts(
    claude_projects: Path, op_dir: Path, start_epoch: float | None
) -> dict[str, Any]:
    """扫描属于 op 工作区的 transcript，按 cwd 分组聚合 token 用量。"""
    op_key = _norm(f"triton_ascend_output/{op_dir.name}")
    sessions: list[dict[str, Any]] = []
    total = _empty_usage()

    if not claude_projects.is_dir():
        return {"sessions": [], "total": total, "projects_root_missing": True}

    for project_dir in sorted(claude_projects.iterdir()):
        if not project_dir.is_dir():
            continue
        slug_key = _norm(project_dir.name)
        if op_key not in slug_key:
            continue
        round_match = ROUND_RE.search(slug_key)
        round_index = int(round_match.group(1)) if round_match else None
        for transcript in sorted(project_dir.glob("*.jsonl")):
            record = _scan_transcript(transcript, project_dir.name, round_index, start_epoch)
            if record is None:
                continue
            for key in TOKEN_KEYS:
                total[key] += record["usage"][key]
            sessions.append(record)

    sessions.sort(key=lambda s: (s["round"] is None, s["round"] or 0, s["cwd_slug"]))
    return {"sessions": sessions, "total": total}


def read_progress(op_dir: Path) -> dict[str, Any]:
    """读取 round_index.json / state 文件中的轮次进度（best-effort）。"""
    progress: dict[str, Any] = {"rounds_completed": 0, "best_speedup": None, "current_round": None}
    index_path = op_dir / "round_index.json"
    if index_path.is_file():
        try:
            entries = json.loads(index_path.read_text(encoding="utf-8"))
            if isinstance(entries, list) and entries:
                speeds = [e.get("best_speedup") for e in entries if isinstance(e.get("best_speedup"), (int, float))]
                progress["rounds_completed"] = len(entries)
                progress["best_speedup"] = max(speeds) if speeds else None
        except (OSError, json.JSONDecodeError):
            pass
    state_files = sorted(Path(op_dir).parent.parent.glob(f".triton-agent/state-*-{op_dir.name}.json"))
    if not state_files:
        state_files = sorted(Path(op_dir).parent.parent.glob(".triton-agent/state-*.json"))
    for state_file in state_files:
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if op_dir.name in str(state.get("work_dir", "")) or not progress:
            progress["current_round"] = state.get("current_round")
            progress["status"] = state.get("status")
            break
    return progress


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate sub-CLI token usage and runtime for a run")
    parser.add_argument("--op-dir", required=True, type=Path, help="op 工作区目录（如 triton_ascend_output/<op>-<algo>-<tag>）")
    parser.add_argument("--start-epoch", type=float, default=None, help="run 起始 unix 时间（秒）")
    parser.add_argument("--start-epoch-file", type=Path, default=None, help="含起始 unix 时间的文件")
    parser.add_argument("--claude-projects", type=Path, default=Path.home() / ".claude" / "projects")
    parser.add_argument("--out", type=Path, default=None, help="详细统计输出路径（默认 <op-dir>/run_stats.json）")
    args = parser.parse_args()

    op_dir = args.op_dir.resolve()
    start_epoch = args.start_epoch
    if start_epoch is None and args.start_epoch_file is not None:
        try:
            start_epoch = float(args.start_epoch_file.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            start_epoch = None

    scanned = scan_transcripts(args.claude_projects, op_dir, start_epoch)
    progress = read_progress(op_dir)
    now = time.time()
    elapsed_seconds = round(now - start_epoch, 1) if start_epoch is not None else None

    total = scanned["total"]
    total["total_tokens"] = sum(total[k] for k in TOKEN_KEYS)
    detail = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "op_dir": str(op_dir),
        "start_epoch": start_epoch,
        "elapsed_seconds": elapsed_seconds,
        "progress": progress,
        "total_usage": total,
        "sessions": scanned["sessions"],
    }
    out_path = args.out or (op_dir / "run_stats.json")
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(detail, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        sys.stdout.buffer.write((json.dumps({"error": f"cannot write {out_path}: {exc}"},
                                    ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
        return 1

    summary = {
        "rounds_completed": progress.get("rounds_completed", 0),
        "current_round": progress.get("current_round"),
        "best_speedup": progress.get("best_speedup"),
        "tokens": total,
        "sub_cli_sessions": len(scanned["sessions"]),
        "elapsed_minutes": round(elapsed_seconds / 60.0, 1) if elapsed_seconds is not None else None,
        "detail": str(out_path),
    }
    sys.stdout.buffer.write((json.dumps(summary, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
