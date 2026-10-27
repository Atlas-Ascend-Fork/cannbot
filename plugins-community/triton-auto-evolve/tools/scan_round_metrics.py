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
"""扫描 orchestrator loop 的 round 产物，累计 token 用量与运行时间。

用法:
    python3 tools/scan_round_metrics.py \
        --op-dir triton_ascend_output/fusion_attention-gene-fusion-s8192 \
        --start-ts-file /tmp/fa_evolve_start_ts

从每个 opt-round-*/sub_agent.log 的 stream-json 行中提取:
  - type=assistant 事件的 message.usage（逐次 API 调用用量, 求和）
  - type=result 事件的 usage/total_cost_usd/duration_ms（回合汇总, 以 result 为准去重）
输出/更新 <op-dir>/orchestrator_metrics.json, 并打印一行 JSON 摘要。
仅读取 round 产物, 不修改任何 pipeline 状态文件。
"""

import argparse
import datetime
import json
import sys
import time
from pathlib import Path


def _round_key(p: Path) -> tuple:
    try:
        return (0, int(p.name.rsplit("-", 1)[-1]))
    except ValueError:
        return (1, 0)


STDOUT_PREFIX = "[sub-agent stdout] "
STDERR_PREFIX = "[sub-agent stderr] "

TOKEN_KEYS = ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")

# scan_round 输出字典中的 token 键名（cache_read/cache_creation 无 _input 后缀）
OUT_TOKEN_KEYS = ("input_tokens", "output_tokens", "cache_read_tokens", "cache_creation_tokens")


def _strip_prefix(line: str) -> str:
    if line.startswith(STDOUT_PREFIX):
        return line[len(STDOUT_PREFIX):].strip()
    if line.startswith(STDERR_PREFIX):
        return line[len(STDERR_PREFIX):].strip()
    return line.strip()


def _accumulate_stream_usage(ev: dict, summed: dict) -> None:
    """stream_event(message_delta) 的增量 usage 累加进 summed。"""
    inner = ev.get("event") or {}
    if inner.get("type") != "message_delta":
        return
    usage = inner.get("usage") or {}
    for key in summed:
        value = usage.get(key)
        if isinstance(value, (int, float)) and value > 0:
            summed[key] += int(value)


def _apply_result_event(ev: dict, out: dict) -> dict:
    """result 事件：回填费用/回合数/API 时长，返回其 usage 块（以 result 为准防重复计数）。"""
    usage = ev.get("usage") or {}
    cost = ev.get("total_cost_usd")
    if isinstance(cost, (int, float)):
        out["cost_usd"] = round(cost, 4)
    turns = ev.get("num_turns")
    if isinstance(turns, int):
        out["num_turns"] = turns
    dur = ev.get("duration_ms")
    if isinstance(dur, (int, float)):
        out["duration_api_s"] = round(dur / 1000.0, 1)
    return usage


def scan_round(work_dir: Path, not_before: float | None = None) -> dict:
    """Scan one round's sub_agent.log for token usage.

    本 CLI 版本中 assistant 事件的 usage 恒为 0, 逐次 API 调用用量在
    stream_event(type=message_delta).event.usage 中; round 结束时的
    result 事件带累计 usage + total_cost_usd, 存在时以 result 为准防重复计数。
    not_before: 兜底扫描 session.jsonl 时时间戳下界(秒), 用于剔除文件里
    混入的更早活动(R8 实测 session.jsonl 混有全天事件)。
    """
    log = work_dir / "sub_agent.log"
    out = {
        "round_dir": work_dir.name,
        "has_result_event": False,
        "input_tokens": 0, "output_tokens": 0,
        "cache_read_tokens": 0, "cache_creation_tokens": 0,
        "cost_usd": 0.0, "num_turns": 0, "duration_api_s": 0.0,
        "log_bytes": log.stat().st_size if log.is_file() else 0,
    }
    if not log.is_file():
        return out

    summed = dict.fromkeys(TOKEN_KEYS, 0)
    result_usage = None
    with log.open("r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = _strip_prefix(raw)
            if not line.startswith("{"):
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            ev_type = ev.get("type")
            if ev_type == "stream_event":
                _accumulate_stream_usage(ev, summed)
            elif ev_type == "result":
                out["has_result_event"] = True
                result_usage = _apply_result_event(ev, out)

    src = result_usage if result_usage else summed
    out["input_tokens"] = int(src.get("input_tokens") or 0)
    out["output_tokens"] = int(src.get("output_tokens") or 0)
    out["cache_read_tokens"] = int(src.get("cache_read_input_tokens") or 0)
    out["cache_creation_tokens"] = int(src.get("cache_creation_input_tokens") or 0)
    if result_usage is None:
        out["cost_usd"] = 0.0  # 无 result 事件时无法计费, 不用估价冒充
        _fallback_from_session(work_dir, out, not_before)
    return out


def _session_event_summary(raw: str) -> tuple:
    """单条 session.jsonl 记录 → (是否 assistant 事件, 时间戳 epoch)；解析失败返回 (False, None)。"""
    try:
        ev = json.loads(raw)
    except json.JSONDecodeError:
        return False, None
    is_assistant = ev.get("type") == "assistant"
    ts = ev.get("timestamp")
    if not isinstance(ts, str):
        return is_assistant, None
    try:
        epoch = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return is_assistant, None
    return is_assistant, epoch


def _fallback_from_session(work_dir: Path, out: dict, not_before: float | None) -> None:
    """sub_agent.log 缺 result 事件时(R8/R9 实测发生), 从 session.jsonl 恢复
    轮次与墙钟口径。cost 无法计费仍保持 0; num_turns 口径与 CLI 不同
    (assistant 事件数 ≈ 2×CLI num_turns), 故单列为 assistant_events 不冒充。"""
    session = work_dir / "session.jsonl"
    if not session.is_file():
        return
    turns = 0
    stamps = []
    with session.open("r", encoding="utf-8", errors="replace") as sf:
        for raw in sf:
            if '"assistant"' not in raw and '"timestamp"' not in raw:
                continue
            is_assistant, epoch = _session_event_summary(raw)
            if is_assistant:
                turns += 1
            if epoch is not None and (not_before is None or epoch > not_before):
                stamps.append(epoch)
    if turns:
        out["assistant_events"] = turns
        out["metrics_source"] = "session_fallback"
    if stamps:
        stamps.sort()
        out["wall_seconds"] = round(stamps[-1] - stamps[0], 1)


def _load_json(path: Path):
    """读取 JSON 文件；缺失/不可读/损坏返回 None。"""
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _scan_all_rounds(op_dir: Path) -> tuple:
    """按轮扫描 sub_agent.log；route-* 子 CLI 日志一并计入（gene-fusion 内部并行派发）。"""
    rounds = []
    prev_log_mtime = None
    for d in sorted(op_dir.glob("opt-round-*"), key=_round_key):
        # 前一轮 sub_agent.log 的 mtime ≈ 上轮 CLI 退出时刻(只会偏晚不会偏早),
        # 作为本轮 session 兜底扫描的时间下界(留 60s 容差), 防止 session.jsonl
        # 混入的更早活动(R8 实测混有全天事件)拉爆墙钟
        not_before = (prev_log_mtime - 60) if prev_log_mtime else None
        rounds.append(scan_round(d, not_before=not_before))
        log = d / "sub_agent.log"
        if log.is_file():
            prev_log_mtime = log.stat().st_mtime
    routes = []
    for d in sorted(op_dir.glob("opt-round-*/route-*")):
        if (d / "sub_agent.log").is_file():
            routes.append(scan_round(d))
    return rounds, routes


def _summarize_usage(records: list) -> tuple:
    """累计 round/route 记录的四项 token 与费用。"""
    totals = dict.fromkeys(OUT_TOKEN_KEYS, 0)
    cost = 0.0
    for r in records:
        for key in totals:
            totals[key] += r[key]
        cost += r["cost_usd"]
    return totals, cost


def _best_speedup_from(src: dict) -> float | None:
    """记录中的数值型 best_speedup（缺失/非数值返回 None）。"""
    speedup = src.get("best_speedup")
    return speedup if isinstance(speedup, (int, float)) else None


def _collect_round_status(op_dir: Path) -> tuple:
    """已完成 round 的 speedup（round_result.json 为准, summary.json 兜底）。"""
    round_status = []
    best = None
    for d in sorted(op_dir.glob("opt-round-*"), key=_round_key):
        entry = {"round_dir": d.name, "finished": False, "status": None, "best_speedup": None}
        src = _load_json(d / "round_result.json")
        if src is None:
            src = _load_json(d / "summary.json")
        if src:
            entry["finished"] = (d / "round_result.json").is_file()
            entry["status"] = src.get("status")
            speedup = _best_speedup_from(src)
            if speedup is not None:
                entry["best_speedup"] = speedup
                best = max(best, speedup) if best is not None else speedup
        round_status.append(entry)
    return round_status, best


def _load_current_round(op_dir: Path):
    """从 state-*.json 读当前轮次（best-effort，读不到返回 None）。"""
    state_candidates = sorted(op_dir.glob("state-*.json")) + sorted(
        (op_dir.parent.parent / ".triton-agent").glob("state-*.json"))
    state_file = next(iter(state_candidates), None)
    if not state_file or not state_file.is_file():
        return None
    state = _load_json(state_file)
    if not isinstance(state, dict):
        return None
    return state.get("current_round")


def _update_metrics_file(op_dir: Path, metrics_update: dict) -> None:
    """合并更新 <op-dir>/orchestrator_metrics.json。"""
    metrics_path = op_dir / "orchestrator_metrics.json"
    metrics = _load_json(metrics_path)
    if not isinstance(metrics, dict):
        metrics = {}
    # 旧字段由 orchestrator_loop 初始写入后从未更新(R10 实测 rounds_completed=0), 以扫描结果为准
    metrics.pop("elapsed_seconds_at_last_check", None)
    metrics.update(metrics_update)
    metrics_path.write_text(json.dumps(metrics, indent=2, ensure_ascii=False) + "\n",
                            encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--op-dir", required=True)
    ap.add_argument("--start-ts-file", required=True)
    args = ap.parse_args()

    op_dir = Path(args.op_dir)
    start = float(Path(args.start_ts_file).read_text().strip())
    now = time.time()
    elapsed = round(now - start, 1)

    rounds, routes = _scan_all_rounds(op_dir)
    totals, cost = _summarize_usage(rounds + routes)
    round_status, best = _collect_round_status(op_dir)
    current_round = _load_current_round(op_dir)
    rounds_completed = sum(1 for e in round_status if e["finished"])
    _update_metrics_file(op_dir, {
        "elapsed_seconds": elapsed,
        "last_check_epoch": now,
        "rounds_completed": rounds_completed,
        "rounds_scanned": [r["round_dir"] for r in rounds],
        "route_logs_scanned": [r["round_dir"] for r in routes],
        "current_round": current_round,
        "best_speedup": best,
        "cumulative_tokens": totals,
        "cumulative_cost_usd": round(cost, 4),
        "per_round": rounds,
    })

    active = (round_status[-1] if round_status and not round_status[-1]["finished"] else None)
    summary = {
        "current_round": current_round,
        "rounds_completed": rounds_completed,
        "finished_rounds": [r["round_dir"] for r in round_status if r["finished"]],
        "active_round": active["round_dir"] if active else None,
        "active_status": active["status"] if active else ("running" if current_round else "idle"),
        "best_speedup": best,
        "tokens_total": totals["input_tokens"] + totals["output_tokens"]
                        + totals["cache_read_tokens"] + totals["cache_creation_tokens"],
        "tokens_in": totals["input_tokens"],
        "tokens_out": totals["output_tokens"],
        "cache_read": totals["cache_read_tokens"],
        "cost_usd": round(cost, 4) if cost else None,
        "elapsed_min": round(elapsed / 60.0, 1),
        "loop_finished": False,
    }
    sys.stdout.buffer.write((json.dumps(summary, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
