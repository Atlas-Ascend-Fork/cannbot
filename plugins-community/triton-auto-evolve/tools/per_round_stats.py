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
"""per_round_stats.py — 按轮统计 kernel 性能、轮运行时间与 token 消耗。

数据源（均为 gf1021 run 已落盘事实）：
  1. kernel 性能：opt-round-N/round_result.json 的 best_speedup / best_task_duration_us
     （round_index.json 仅作 status 对照）。
  2. 轮运行时间：编排日志 round N: dispatch start → dispatch done（log 相对秒差）。
  3. token：~/.claude/projects/<slug>/*.jsonl transcript 聚合，按会话首末时间戳
     归属到编排日志的轮时间窗（route 子 CLI 会话落在父轮窗内，一并计入该轮）。

用法：
  python3 tools/per_round_stats.py --op-dir triton_ascend_output/<op-dir> \
      --log triton_ascend_output/orchestrator_<op>_<tag>.log \
      --start-epoch-file triton_ascend_output/.run_start_<op>_<tag>.epoch
"""

import argparse
import calendar
import json
import logging
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

logger = logging.getLogger(__name__)

TOKEN_KEYS = ("input_tokens", "output_tokens", "cache_read_input_tokens")

LINE_RE = re.compile(
    r"\[\s*timing\s*\]\s*\+\s*([\d.]+)s\s+(\d{2}:\d{2}:\d{2})\s+round (\d+): (dispatch start|dispatch done)"
)


def parse_log_windows(log_path: Path, first_epoch: float):
    """返回 {round: (start_epoch, end_epoch, wall_seconds)}。

    日志相对秒在编排器重启时归零（新段）。首段锚点 = start_epoch（X=0 即 run start）；
    后续段锚点用上一行的绝对 epoch + wall 时钟差（mod 86400，容忍跨天）链接，
    不依赖解析当天的日期。
    """
    text = log_path.read_text(encoding="utf-8", errors="replace")
    anchor = None
    prev_x = prev_wall_s = prev_epoch = None
    starts, ends = {}, {}
    for m in LINE_RE.finditer(text):
        x = float(m.group(1))
        hh, mm, ss = (int(v) for v in m.group(2).split(":"))
        wall_s = hh * 3600 + mm * 60 + ss
        rnd = int(m.group(3))
        kind = m.group(4)
        if anchor is None:
            anchor = first_epoch
        elif prev_x is not None and x < prev_x - 1:  # 新段（重启归零）
            wall_delta = (wall_s - prev_wall_s + 43200) % 86400 - 43200
            anchor = prev_epoch + wall_delta - x
        prev_x, prev_wall_s = x, wall_s
        prev_epoch = anchor + x
        if kind == "dispatch start":
            starts[rnd] = prev_epoch
        else:
            ends[rnd] = prev_epoch
    windows = {}
    for rnd in sorted(starts):
        if rnd in ends:
            windows[rnd] = (starts[rnd], ends[rnd], ends[rnd] - starts[rnd])
    return windows


def iter_sessions(op_dir_name: str):
    """遍历 transcript slug 含 op-dir 名的会话文件。"""
    root = Path.home() / ".claude" / "projects"
    norm = op_dir_name.lower().replace("_", "-").replace(".", "-")
    for d in root.iterdir():
        if not d.is_dir():
            continue
        slug = d.name.lower().replace("_", "-").replace(".", "-")
        if norm not in slug:
            continue
        for f in d.glob("*.jsonl"):
            yield f


def parse_iso(ts: str):
    # transcript 时间戳为 UTC（ISO 8601），必须按 UTC 换算 epoch，
    # 与日志锚点（本地 wall 时间 → mktime）对齐到同一 epoch 基准。
    try:
        return calendar.timegm(time.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S"))
    except (ValueError, TypeError):
        return None


def _zero_tokens() -> dict:
    """空 token 计数器（键集合见 TOKEN_KEYS）。"""
    return dict.fromkeys(TOKEN_KEYS, 0)


def _accumulate_record(rec: dict, tok: dict, first: float, last: float):
    """处理单条 transcript 记录：累加 usage 并扩展时间跨度。

    返回 (first, last, counted)；counted 表示该记录是带 usage 的 assistant 消息。
    """
    ts = rec.get("timestamp")
    if ts:
        t = parse_iso(ts)
        if t:
            first = t if first is None else min(first, t)
            last = t if last is None else max(last, t)
    if rec.get("type") != "assistant":
        return first, last, False
    usage = (rec.get("message") or {}).get("usage")
    if not usage:
        return first, last, False
    for key in TOKEN_KEYS:
        tok[key] += int(usage.get(key) or 0)
    return first, last, True


def _session_records(fh):
    """逐行解析 transcript 的 JSON 记录（空行/坏行跳过）。"""
    for line in fh:
        if line.strip():
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                pass


def _iter_session_records(path: Path):
    """逐条产出 transcript 的 JSON 记录（不可读记 debug 日志）。"""
    if not path.is_file():
        return
    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            yield from _session_records(fh)
    except OSError as exc:
        logger.debug("session transcript unreadable (%s): %s", path, exc)


def session_tokens_and_span(path: Path):
    """单个会话的 token 合计与首末消息 epoch。"""
    tok = _zero_tokens()
    n_msg = 0
    first = last = None
    for rec in _iter_session_records(path):
        first, last, counted = _accumulate_record(rec, tok, first, last)
        if counted:
            n_msg += 1
    return tok, first, last, n_msg


def _match_window(mid: float, windows: dict):
    """会话归属轮次：中点落在某轮窗内（±60s 容差）取该轮；否则取最近窗。"""
    for rnd, (s, e, _) in windows.items():
        if s - 60 <= mid <= e + 60:
            return rnd
    return min(windows, key=lambda r: min(abs(mid - windows[r][0]), abs(mid - windows[r][1])))


def _assign_sessions(windows: dict, op_dir_name: str):
    """把 transcript 会话按首末时间中点归属到轮时间窗，聚合 token 与会话数。"""
    per_round_tok = defaultdict(_zero_tokens)
    per_round_sessions = defaultdict(int)
    unassigned = _zero_tokens()
    unassigned_n = 0
    for f in iter_sessions(op_dir_name):
        tok, first, last, _ = session_tokens_and_span(f)
        if not tok["input_tokens"] and not tok["output_tokens"]:
            continue
        mid = (first + last) / 2 if first and last else (first or 0)
        rnd = _match_window(mid, windows)
        for key in TOKEN_KEYS:
            per_round_tok[rnd][key] += tok[key]
        per_round_sessions[rnd] += 1
    return per_round_tok, per_round_sessions, unassigned, unassigned_n


def _round_status(idx_path: Path, rnd: int):
    """round_index.json 中第 rnd 轮的 status（缺失/损坏返回 None）。"""
    if not idx_path.is_file():
        return None
    try:
        entries = json.loads(idx_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    if isinstance(entries, list) and 0 < rnd <= len(entries):
        return entries[rnd - 1].get("status")
    return None


def _round_metrics(op_dir: Path, rnd: int):
    """opt-round-N 的 kernel 性能数据（round_result.json，best-effort）。"""
    speedup = dur_us = None
    rr = op_dir / f"opt-round-{rnd}" / "round_result.json"
    if rr.is_file():
        try:
            data = json.loads(rr.read_text())
            speedup = data.get("best_speedup")
            dur_us = data.get("best_task_duration_us")
        except (json.JSONDecodeError, OSError):
            pass
    return speedup, dur_us


def _collect_rows(op_dir: Path, windows: dict, assignment):
    """逐轮汇总输出行：kernel 性能 + 轮耗时 + token + 子 CLI 会话数。"""
    per_round_tok, per_round_sessions, _, _ = assignment
    rows = []
    for rnd, (_, _, wall) in sorted(windows.items()):
        speedup, dur_us = _round_metrics(op_dir, rnd)
        tok = per_round_tok[rnd]
        rows.append({
            "round": rnd,
            "kernel_best_task_duration_us": dur_us,
            "kernel_best_speedup": speedup,
            "round_status": _round_status(op_dir / "round_index.json", rnd),
            "round_wall_seconds": round(wall, 1),
            "tokens": {**tok, "total": sum(tok.values())},
            "sub_cli_sessions": per_round_sessions[rnd],
        })
    return rows


def _table_line(row: dict) -> str:
    """单行 markdown 统计行。"""
    t = row["tokens"]
    return (f"| {row['round']} | {row['kernel_best_task_duration_us']} | {row['kernel_best_speedup']} "
            f"| {row['round_wall_seconds'] / 60:.1f} | {row['round_status']} "
            f"| {t['input_tokens']}/{t['output_tokens']}/{t['cache_read_input_tokens']}/{t['total']} "
            f"| {row['sub_cli_sessions']} |")


def _emit_report(rows: list, op_dir: Path, start_epoch: float, assignment):
    """写 per_round_stats.json 并向 stdout 输出统计表。"""
    _, _, unassigned, unassigned_n = assignment
    detail = op_dir / "per_round_stats.json"
    detail.write_text(json.dumps({
        "run_start_epoch": start_epoch,
        "rounds": rows,
        "unassigned_tokens": unassigned,
        "unassigned_sessions": unassigned_n,
    }, ensure_ascii=False, indent=2))

    lines = [
        "| 轮 | kernel 最优延迟(us) | speedup | 轮耗时(min) | 轮状态 | tokens(in/out/cache/total) | 子CLI会话 |",
        "|---|---|---|---|---|---|---|",
    ]
    lines.extend(_table_line(row) for row in rows)
    tok_in = sum(r["tokens"]["input_tokens"] for r in rows)
    tok_out = sum(r["tokens"]["output_tokens"] for r in rows)
    tok_cache = sum(r["tokens"]["cache_read_input_tokens"] for r in rows)
    wall_min = sum(r["round_wall_seconds"] for r in rows) / 60
    sessions = sum(r["sub_cli_sessions"] for r in rows)
    lines.append(f"TOTAL: input={tok_in} output={tok_out} cache_read={tok_cache} "
                 f"total={tok_in + tok_out + tok_cache} round_wall={wall_min:.1f}min sessions={sessions}")
    lines.append(f"detail: {detail}")
    sys.stdout.buffer.write(("\n".join(lines) + "\n").encode("utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--op-dir", required=True)
    ap.add_argument("--log", required=True)
    ap.add_argument("--start-epoch-file", default=None)
    args = ap.parse_args()

    op_dir = Path(args.op_dir).resolve()
    if args.start_epoch_file:
        start_epoch = int(Path(args.start_epoch_file).read_text().strip())
    else:
        start_epoch = int(time.time())
    windows = parse_log_windows(Path(args.log), start_epoch)
    assignment = _assign_sessions(windows, op_dir.name)
    rows = _collect_rows(op_dir, windows, assignment)
    _emit_report(rows, op_dir, start_epoch, assignment)


if __name__ == "__main__":
    main()
