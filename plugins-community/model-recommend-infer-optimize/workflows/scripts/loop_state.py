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
"""持续优化循环的状态辅助工具（幂等恢复 + 对账）

用法：
  python3 loop_state.py next  --log-dir data/M100/optimization_log
  python3 loop_state.py check --log-dir data/M100/optimization_log
  python3 loop_state.py init  --log-dir data/M100/optimization_log --metric qps --op '>=' --value 1500
  python3 loop_state.py migrate --log-dir data/M100/optimization_log   # 旧版 schema 迁移

next   : 打印下一轮轮次号与当前计数；已终止、轮次预算用尽或连续无收益达 3 轮时以退出码 3 结束；
         目标未确认或噪声带未测定时以退出码 4 结束（准入未通过）。
check  : 校验 loop_state 与 perf_ledger 是否对账一致（轮次与收益数字）；
         delta_pct / gain_pct 既支持数字也支持对象（按 latency → qps → tp99 取主指标）。
init   : 生成 loop_state.json 骨架（目标必须由用户确认，脚本只落盘 confirmed_by_user=false）。
migrate: 把旧版（round / rounds_executed / status 字段、history 用 round）迁移到当前 schema。

退出码：0 正常；1 参数/文件错误（含 JSON 损坏）；2 对账不一致（含终止标记与原因矛盾）；3 循环已终止或不应再开新轮；4 循环准入未通过。
"""

import argparse
import json
import logging
import os
import re
import shutil
import sys
import time

LOG = logging.getLogger("loop_state")


def configure_logging():
    """统一日志格式：只输出正文，避免脚本输出被前缀干扰。"""
    if LOG.handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    LOG.addHandler(handler)
    LOG.setLevel(logging.INFO)
    LOG.propagate = False


ROUND_PATTERN = re.compile(r"循环第\s*(\d+)\s*轮")
# 连续无收益轮数上限（与 loop-rules.md §4 的 converged_no_gain 判定一致）
NO_GAIN_LIMIT = 3
# loop_state.json 的 schema 版本；旧文件无该字段（视为 1），用 migrate 升级
SCHEMA_VERSION = 2
# delta_pct / gain_pct 为对象时的主指标取用顺序
GAIN_METRIC_ORDER = (
    "latency",
    "latency_avg_ms",
    "latency_avg",
    "tp99",
    "tp99_ms",
    "qps",
    "throughput",
)
# 旧版 schema 的遗留字段
LEGACY_FIELDS = ("round", "rounds_executed", "status")
# target.mode 合法取值：target=用户给数值目标；regression_guard=以历史最优为回归基准
TARGET_MODES = ("target", "regression_guard")


class StateFileError(Exception):
    """loop_state / perf_ledger 文件不可解析。"""


def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as exc:
        raise StateFileError(
            "%s 不是合法 JSON（第 %d 行第 %d 列：%s）。请修正语法，或用 `loop_state.py migrate` 迁移旧格式。"
            % (path, exc.lineno, exc.colno, exc.msg)
        ) from exc
    except OSError as exc:
        raise StateFileError("%s 读取失败：%s" % (path, exc)) from exc


def primary_gain(value):
    """把 delta_pct / gain_pct 归一为单个数字。

    number 直接返回；对象按 GAIN_METRIC_ORDER 取第一个数值（缺失时回退到任意数值字段）；
    字符串数字尝试转换；其余返回 None（对账时跳过并告警）。
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        for key in GAIN_METRIC_ORDER:
            candidate = value.get(key)
            if isinstance(candidate, (int, float)) and not isinstance(candidate, bool):
                return float(candidate)
        for candidate in value.values():
            if isinstance(candidate, (int, float)) and not isinstance(candidate, bool):
                return float(candidate)
        return None
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def legacy_fields(state):
    """返回 state 中出现的旧版字段名。"""
    return [name for name in LEGACY_FIELDS if name in state]


def check_schema(state, state_path):
    """schema 版本检查：缺失或低于当前版本时提示迁移（不阻断）。"""
    version = state.get("schema_version")
    if version == SCHEMA_VERSION:
        return
    legacy = legacy_fields(state)
    if version is None and not legacy:
        # 当前 schema 早期落盘的文件也没有 schema_version，但字段布局一致
        LOG.info(
            "WARN: %s 缺少 schema_version（按 v%d 处理）—— 可用 migrate 补写。"
            % (state_path, SCHEMA_VERSION)
        )
        return
    LOG.info(
        "WARN: %s 的 schema_version=%s（当前 %d）%s —— 请运行 `loop_state.py migrate --log-dir <dir>`。"
        % (
            state_path,
            version,
            SCHEMA_VERSION,
            ("，检测到旧字段 %s" % legacy) if legacy else "",
        )
    )


def log_dir_paths(log_dir):
    return (
        os.path.join(log_dir, "loop_state.json"),
        os.path.join(log_dir, "perf_ledger.json"),
    )


def check_findings_coverage(log_dir, rounds):
    """W8：profiling 专项结论是否并入下一步动作表（只告警，不阻断）。

    findings: <data>/profiling-deep-analysis/iter{k}/findings.json（log_dir 的兄弟目录）
    actions : <data>/regression-baseline-mgmt/next_actions.json
    """
    base = os.path.dirname(os.path.normpath(log_dir)) or "."
    actions_path = os.path.join(base, "regression-baseline-mgmt", "next_actions.json")
    findings_dir = os.path.join(base, "profiling-deep-analysis")
    if not os.path.isdir(findings_dir):
        return
    action_ids = set()
    if os.path.exists(actions_path):
        try:
            actions = load(actions_path)
        except StateFileError as exc:
            LOG.warning("WARN: %s" % exc)
            actions = None
        action_ids = {
            str(item.get("id"))
            for item in _walk_dicts(actions)
            if isinstance(item.get("id"), (str, int))
        }
        if not action_ids:
            LOG.info(
                "WARN: next_actions.json 中的条目都没有 id —— 无法校验 findings 覆盖；"
                "旧工作区可用 loop_state.py migrate 后补 id，或本次忽略该告警。"
            )
            return
    for k in sorted({r for r in rounds if isinstance(r, int)}):
        path = os.path.join(findings_dir, "iter%d" % k, "findings.json")
        if not os.path.exists(path):
            continue
        try:
            data = load(path)
        except StateFileError as exc:
            LOG.warning("WARN: %s" % exc)
            continue
        ids = {
            str(item.get("id"))
            for item in _walk_dicts(data)
            if isinstance(item.get("id"), (str, int))
        }
        if not ids:
            continue
        if not os.path.exists(actions_path):
            LOG.info(
                "WARN: 第 %d 轮有 profiling findings（%s），但缺少 next_actions.json —— 专项结论未进入动作表。"
                % (k, os.path.basename(os.path.dirname(path)))
            )
        elif not (ids & action_ids):
            LOG.info(
                "WARN: 第 %d 轮 findings 的 id %s 均未出现在 next_actions.json —— 专项结论未并入动作表。"
                % (k, sorted(ids))
            )


def _walk_dicts(node):
    """遍历 JSON 结构中的所有 dict（用于提取任意层级的 id）。"""
    if isinstance(node, dict):
        yield node
        for value in node.values():
            for item in _walk_dicts(value):
                yield item
    elif isinstance(node, list):
        for value in node:
            for item in _walk_dicts(value):
                yield item


def cmd_next(args):
    state_path, _ = log_dir_paths(args.log_dir)
    if not os.path.exists(state_path):
        LOG.error("loop_state.json 不存在：%s" % state_path)
        return 1
    state = load(state_path)
    if state.get("terminated"):
        LOG.info(
            "循环已终止：reason=%s，共 %d 轮"
            % (state.get("termination_reason"), state.get("iteration", 0))
        )
        return 3
    iteration = state.get("iteration", 0)
    max_iterations = state.get("max_iterations", 10)
    no_gain = state.get("no_gain_streak", 0)
    if iteration >= max_iterations:
        LOG.info(
            "轮次预算已用尽（iteration=%d ≥ max_iterations=%d）：应收口，终止原因记 budget_exhausted。"
            % (iteration, max_iterations)
        )
        return 3
    if no_gain >= NO_GAIN_LIMIT:
        LOG.info(
            "连续 %d 轮无收益（≥%d）：应终止，终止原因记 converged_no_gain。"
            % (no_gain, NO_GAIN_LIMIT)
        )
        return 3
    LOG.info(
        "下一轮=第 %d 轮 | 已完成=%s | 连续无收益=%s | 上限=%s | 目标(%s)=%s %s %s"
        % (
            state.get("iteration", 0) + 1,
            state.get("iteration", 0),
            state.get("no_gain_streak", 0),
            state.get("max_iterations", 10),
            (state.get("target") or {}).get("mode") or "target",
            (state.get("target") or {}).get("metric"),
            (state.get("target") or {}).get("op"),
            (state.get("target") or {}).get("value"),
        )
    )
    target = state.get("target") or {}
    blockers = []
    mode = target.get("mode") or "target"
    if mode not in TARGET_MODES:
        blockers.append(
            "target.mode=%r 非法（只能是 %s）" % (mode, " / ".join(TARGET_MODES))
        )
    if not target.get("confirmed_by_user"):
        blockers.append("target.confirmed_by_user 不是 true：性能目标尚未由用户确认")
    if not state.get("noise_band_pct"):
        blockers.append("noise_band_pct 未测定：首轮须先测噪声带")
    if blockers:
        for b in blockers:
            LOG.info("FAIL 准入未通过：%s" % b)
        LOG.info("结论：不得进入循环，先补齐上述前置条件。")
        return 4
    return 0


def _check_files_present(state_path, ledger_path):
    """两个状态文件都必须存在，缺失逐条报出。"""
    problems = []
    if not os.path.exists(state_path):
        problems.append("loop_state.json 缺失")
    if not os.path.exists(ledger_path):
        problems.append("perf_ledger.json 缺失")
    for name in problems:
        LOG.error("FAIL: %s" % name)
    return 1 if problems else 0


def _ledger_entries(ledger):
    """取出 ledger 的动作列表；既支持 {"entries": [...]} 也支持裸数组。"""
    if isinstance(ledger, list):
        entries = ledger
    elif isinstance(ledger, dict):
        entries = ledger.get("entries") or []
    else:
        LOG.error("FAIL: perf_ledger.json 既不是对象也不是数组，无法对账。")
        return None
    if not isinstance(entries, list):
        LOG.error("FAIL: perf_ledger.entries 不是数组，无法对账。")
        return None
    return entries


def _round_of(entry):
    """动作条目里标注的轮次号；没有标注返回 None。"""
    if not isinstance(entry, dict):
        return None
    note = str(entry.get("note", "")) + " " + str(entry.get("step", ""))
    match = ROUND_PATTERN.search(note)
    return int(match.group(1)) if match else None


def _check_round_alignment(state, int_rounds, ledger_rounds):
    """轮次一致性：重复轮次、history 与 iteration 回填、ledger 领先等。"""
    iteration = state.get("iteration", 0) or 0
    history_max = max(int_rounds, default=0)
    # iteration 是权威计数，history 可能因中断缺失，故取两者较大者
    max_state = max(iteration, history_max)
    max_ledger = max(ledger_rounds, default=0)

    duplicated = sorted({r for r in int_rounds if int_rounds.count(r) > 1})
    if duplicated:
        LOG.error(
            "FAIL: loop_state.history 存在重复轮次 %s —— 每轮只应有一条记录。"
            % duplicated
        )
        return 2
    if history_max > iteration:
        LOG.error(
            "FAIL: history 已记录到第 %d 轮，但 iteration=%s —— 以 history 为准回填 iteration。"
            % (history_max, iteration)
        )
        return 2
    if max_ledger > max_state:
        LOG.error(
            "FAIL: perf_ledger 已记录到第 %d 轮，但 loop_state.iteration 仅 %d —— 以 ledger 为准回填 "
            "loop_state 并在 note 注明修复。" % (max_ledger, state.get("iteration", 0))
        )
        return 2
    if max_state > max_ledger:
        LOG.warning(
            "WARN: loop_state 已到第 %d 轮，ledger 只到第 %d 轮 —— "
            "检查是否有分析轮（无动作）未记账。" % (max_state, max_ledger)
        )
    gaps = [r for r in range(1, max_state + 1) if r not in int_rounds]
    if gaps and max_state > 0:
        LOG.warning(
            "WARN: history 缺少轮次 %s —— 中断恢复时补记或在 note 说明该轮未执行。"
            % gaps
        )
        if max_ledger >= max_state:
            LOG.info(
                "      （ledger 已覆盖至第 %d 轮，history 缺失可能只是未回填）"
                % max_ledger
            )
    return 0


def _gains_by_round(entries):
    """把 ledger 每轮的 delta_pct 归一为数字，返回 (按轮分组的收益, 无法归一的轮次)。"""
    gain_by_round = {}
    unparsed = []
    for entry in entries:
        round_no = _round_of(entry)
        if round_no is None:
            continue
        raw = entry.get("delta_pct")
        if raw is None:
            continue
        gain = primary_gain(raw)
        if gain is None:
            unparsed.append((round_no, type(raw).__name__))
            continue
        gain_by_round.setdefault(round_no, []).append(gain)
    return gain_by_round, unparsed


def _check_gain_alignment(history, gain_by_round):
    """收益数字对齐：同轮 gain_pct 与 ledger 的 delta_pct 允许 0.05 的抖动。"""
    mismatched = []
    for item in history:
        round_no = item.get("iter")
        gain = primary_gain(item.get("gain_pct"))
        if round_no in gain_by_round and gain is not None:
            if any(abs(gain - other) > 0.05 for other in gain_by_round[round_no]):
                mismatched.append((round_no, gain, gain_by_round[round_no]))
    for round_no, gain, others in mismatched:
        LOG.error(
            "FAIL: 第 %s 轮收益不一致 loop_state=%s vs ledger=%s"
            % (round_no, gain, others)
        )
    return 2 if mismatched else 0


def _check_sweep_fallback(state):
    """sweep 不可用而改手工扫描时，来源必须可追溯。"""
    fallback = state.get("sweep_fallback")
    if fallback is None:
        return
    if (
        not isinstance(fallback, dict)
        or not isinstance(fallback.get("reason"), str)
        or not fallback.get("reason", "").strip()
    ):
        LOG.warning(
            "WARN: sweep_fallback 应为 {reason, rounds} 且 reason 非空 —— "
            "手工扫描的来源无法追溯。"
        )


def _check_termination_marker(state):
    """终止标记与终止原因必须同时成立。"""
    terminated = state.get("terminated")
    reason = state.get("termination_reason")
    if terminated and not reason:
        LOG.error(
            "FAIL: terminated=true 但 termination_reason 为空 —— 终止必须写清 reason。"
        )
        return 2
    if not terminated and reason:
        LOG.error(
            "FAIL: terminated=false 但 termination_reason=%s —— 终止标记与原因不一致。"
            % reason
        )
        return 2
    LOG.info(
        "OK: 状态对账通过（终止=%s reason=%s）"
        % (terminated, reason if terminated else "—")
    )
    return 0


def cmd_check(args):
    state_path, ledger_path = log_dir_paths(args.log_dir)
    if _check_files_present(state_path, ledger_path):
        return 1

    state = load(state_path)
    ledger = load(ledger_path)
    check_schema(state, state_path)
    history = state.get("history") or []
    state_rounds = [item.get("iter") for item in history]
    LOG.info(
        "loop_state 轮次：%s（iteration=%s）" % (state_rounds, state.get("iteration"))
    )

    entries = _ledger_entries(ledger)
    if entries is None:
        return 2
    ledger_rounds = [
        r for r in (_round_of(entry) for entry in entries) if r is not None
    ]
    LOG.info(
        "perf_ledger 出现过的轮次：%s（条数=%d）"
        % (sorted(set(ledger_rounds)), len(entries))
    )

    int_rounds = [r for r in state_rounds if isinstance(r, int)]
    code = _check_round_alignment(state, int_rounds, ledger_rounds)
    if code:
        return code

    gain_by_round, unparsed = _gains_by_round(entries)
    if unparsed:
        LOG.warning(
            "WARN: 以下轮次的 delta_pct 无法归一为数字，已跳过收益对齐：%s"
            % ", ".join("第 %d 轮(%s)" % item for item in unparsed)
        )
    code = _check_gain_alignment(history, gain_by_round)
    if code:
        return code

    check_findings_coverage(args.log_dir, int_rounds)
    _check_sweep_fallback(state)
    return _check_termination_marker(state)


def cmd_init(args):
    state_path, _ = log_dir_paths(args.log_dir)
    os.makedirs(args.log_dir, exist_ok=True)
    if os.path.exists(state_path) and not args.force:
        LOG.error("loop_state.json 已存在（加 --force 覆盖）：%s" % state_path)
        return 1
    state = {
        "schema_version": SCHEMA_VERSION,
        "target": {
            "metric": args.metric,
            "op": args.op,
            "value": args.value,
            "mode": "target",
            "confirmed_by_user": False,
        },
        "noise_band_pct": args.noise_band or 0,
        "iteration": 0,
        "no_gain_streak": 0,
        "max_iterations": args.max_iterations,
        "history": [],
        "terminated": False,
        "termination_reason": None,
    }
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
        f.write("\n")
    LOG.info(
        "已生成 %s（target.confirmed_by_user 需在与用户确认后改为 true）" % state_path
    )
    return 0


def _migrate_legacy_field(state, name, value, changes):
    """把单个旧字段的值搬到当前 schema 的对应字段，并记录变更说明。"""
    if name == "round":
        state["iteration"] = (
            int(value) if isinstance(value, (int, float)) else state.get("iteration", 0)
        )
        changes.append("round -> iteration=%s" % state["iteration"])
    elif name == "rounds_executed":
        if not state.get("iteration"):
            state["iteration"] = int(value) if isinstance(value, (int, float)) else 0
        changes.append("rounds_executed -> iteration=%s" % state.get("iteration"))
    elif name == "status":
        terminated = str(value).lower() in {"terminated", "finished", "done", "closed"}
        state["terminated"] = terminated
        if terminated and not state.get("termination_reason"):
            state["termination_reason"] = "migrated_from_status"
        changes.append("status=%s -> terminated=%s" % (value, terminated))


def _migrate_history(state, changes):
    """history 里的 round 字段改名为 iter（只改第一条，其余保持不变）。"""
    history = state.get("history")
    if not isinstance(history, list):
        return
    for item in history:
        if isinstance(item, dict) and "round" in item and "iter" not in item:
            item["iter"] = item.pop("round")
            changes.append("history.round -> history.iter")
            break


def cmd_migrate(args):
    """把旧版 loop_state.json 迁移到当前 schema（原地改写，先备份）。"""
    state_path, _ = log_dir_paths(args.log_dir)
    if not os.path.exists(state_path):
        LOG.error("loop_state.json 不存在：%s" % state_path)
        return 1
    state = load(state_path)
    if state.get("schema_version") == SCHEMA_VERSION and not legacy_fields(state):
        LOG.info("已是当前 schema（v%d），无需迁移：%s" % (SCHEMA_VERSION, state_path))
        return 0

    changes = []
    for name in legacy_fields(state):
        _migrate_legacy_field(state, name, state.pop(name), changes)
    _migrate_history(state, changes)
    state.setdefault("target", {})
    state.setdefault("iteration", 0)
    state.setdefault("history", [])
    state.setdefault("terminated", False)
    state.setdefault("termination_reason", None)
    state["schema_version"] = SCHEMA_VERSION

    backup = "%s.bak.%s" % (state_path, time.strftime("%Y%m%d_%H%M%S"))
    shutil.copy2(state_path, backup)
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
        f.write("\n")
    LOG.info(
        "已迁移 %s -> schema v%d（备份 %s）"
        % (state_path, SCHEMA_VERSION, os.path.basename(backup))
    )
    for change in changes:
        LOG.info("  - %s" % change)
    return 0


def main():
    configure_logging()
    parser = argparse.ArgumentParser(
        description="model-recommend-infer-optimize 循环状态辅助"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_next = sub.add_parser("next", help="打印下一轮")
    p_next.add_argument("--log-dir", required=True)
    p_next.set_defaults(func=cmd_next)

    p_check = sub.add_parser("check", help="loop_state 与 perf_ledger 对账")
    p_check.add_argument("--log-dir", required=True)
    p_check.set_defaults(func=cmd_check)

    p_init = sub.add_parser("init", help="生成 loop_state 骨架")
    p_init.add_argument("--log-dir", required=True)
    p_init.add_argument(
        "--metric",
        default="latency_avg_ms",
        choices=["latency_avg_ms", "tp99_ms", "qps", "throughput"],
    )
    p_init.add_argument("--op", default="<=", choices=["<=", ">="])
    p_init.add_argument("--value", type=float, required=True)
    p_init.add_argument("--noise-band", type=float, default=0)
    p_init.add_argument("--max-iterations", type=int, default=10)
    p_init.add_argument("--force", action="store_true")
    p_init.set_defaults(func=cmd_init)

    p_migrate = sub.add_parser("migrate", help="旧版 loop_state 迁移到当前 schema")
    p_migrate.add_argument("--log-dir", required=True)
    p_migrate.set_defaults(func=cmd_migrate)

    args = parser.parse_args()
    try:
        return args.func(args)
    except StateFileError as exc:
        LOG.error("%s" % exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
