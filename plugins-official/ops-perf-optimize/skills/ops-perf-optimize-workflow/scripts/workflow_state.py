#!/usr/bin/env python3
# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Eventized workflow state and live-report renderer for ops-perf-optimize."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import html
import json
import os
import re
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import quote

from cli_output import emit, run_cli
from summarize_performance_effects import summarize, recompute_summary, summary_dependency_paths
from performance_effect_evidence import policy
from validate_execution_identity import dependency_paths, validate_execution_identity


SCHEMA_VERSION = 3
WORKFLOW_VERSION = "unified-workflow-v12-execution-identity"
PHASES = ("baseline", "preparation", "analysis", "implementation", "integration")
TUNING_MODES = ("standard", "generalization")
STAGE_STATUSES = ("in_progress", "complete", "invalid", "skipped")
TERMINAL_STATUSES = ("success", "failed", "blocked", "awaiting_operator")
TERMINAL_REASON_CODES = (
    "completed",
    "external_blocker",
    "input_invalid",
    "workflow_error",
    "known_baseline_failure",
    "candidate_precision_regression",
    "no_material_improvement",
    "ceiling_bound",
    "structural_headroom_unrealized",
)
# Structural-direction ledger (pursue_optimal). A structural direction proposed by analysis is a
# cross-round obligation that must be discharged before a clean success finish under pursue_optimal.
STRUCTURAL_DIRECTION_STATUSES = (
    "not_attempted",          # proposed, not yet implemented — UNRESOLVED
    "blocked_by_scope",       # frozen scope too narrow — UNRESOLVED (re-freeze + re-attempt)
    "blocked_by_precision",   # attempted, evidenced it breaks the precision contract — resolved
    "infeasible_evidenced",   # attempted, source/model evidence proves infeasibility — resolved
    "realized",               # implemented and selected — resolved
)
UNRESOLVED_STRUCTURAL_STATUSES = ("not_attempted", "blocked_by_scope")
PRECISION_CLASSIFICATIONS = (
    "known_baseline_failure",
    "improved_baseline_failure",
    "new_or_worsened_failure",
    "under_diagnosis",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


_SHA_CACHE: dict[tuple[str, int, int], str] = {}


def file_sha(path: Path) -> str:
    """SHA256 with a stat-keyed per-process memo.

    Stage commands re-verify large dependency closures (schedule reports,
    DSL compile evidence, phase artifacts) and hash the same files many
    times in one invocation; the stat signature keeps the cache coherent
    within the command while removing repeated full reads.
    """
    stat = path.stat()
    key = (str(path), stat.st_size, stat.st_mtime_ns)
    cached = _SHA_CACHE.get(key)
    if cached is not None:
        return cached
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    value = digest.hexdigest()
    _SHA_CACHE[key] = value
    return value


def tree_sha(path: Path) -> str:
    digest = hashlib.sha256()
    for item in sorted(candidate for candidate in path.rglob("*") if candidate.is_file()):
        digest.update(item.relative_to(path).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_sha(item).encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


def artifact_identity(raw_path: str | Path) -> dict[str, Any]:
    path = Path(raw_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"artifact does not exist: {path}")
    return {
        "path": str(path),
        "kind": "directory" if path.is_dir() else "file",
        "sha256": tree_sha(path) if path.is_dir() else file_sha(path),
    }


def atomic_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    atomic_text(path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_manifest(path: Path) -> dict[str, Any]:
    payload = read_json(path)
    if "configuration" not in payload or "collections" not in payload or "inputs" not in payload:
        raise ValueError(f"invalid run manifest: {path}")
    from workflow_backend import validate_backend
    validate_backend(payload["configuration"], validate_live=False)
    precision_policy = payload["configuration"].get("precision_diagnosis_policy")
    if precision_policy != "persistent":
        raise ValueError(f"invalid precision diagnosis policy: {precision_policy}")
    policy(payload["configuration"].get("performance_effect_policy"))
    from validate_schedule_contract import policy_enabled
    policy_enabled(payload)
    tuning_mode = payload["configuration"].get("tuning_mode", "standard")
    if tuning_mode not in TUNING_MODES:
        raise ValueError(f"invalid tuning mode: {tuning_mode}")
    target_socs = payload["configuration"].get("target_socs")
    if not isinstance(target_socs, list) or not target_socs:
        raise ValueError("run manifest requires non-empty target_socs")
    if tuning_mode == "generalization":
        if payload["configuration"].get("functional_mode") != "reuse_performance":
            raise ValueError("generalization mode fixes functional mode to reuse_performance")
        generalization = payload["configuration"].get("generalization")
        if not isinstance(generalization, dict):
            raise ValueError("generalization configuration is missing")
        competitor = generalization.get("competitor", {})
        if competitor.get("source") != "file":
            raise ValueError("invalid generalization competitor source")
    return payload


@contextmanager
def state_lock(state_path: Path) -> Iterator[None]:
    lock_path = state_path.with_suffix(state_path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def append_event(state: dict[str, Any], kind: str, **payload: Any) -> None:
    state.setdefault("events", []).append({"at": utc_now(), "kind": kind, **payload})


def stage_first_event_time(state: dict[str, Any], stage: str) -> str | None:
    for event in state.get("events", []):
        if event.get("kind") == "stage" and event.get("stage") == stage and event.get("at"):
            return event["at"]
    return None


def resolve_stage_started_at(state: dict[str, Any], stage: str, record: dict[str, Any]) -> str | None:
    return record.get("started_at") or stage_first_event_time(state, stage)


def manifest_summary(manifest: dict[str, Any]) -> list[str]:
    collections = manifest.get("collections", {})
    tuning_mode = manifest.get("configuration", {}).get("tuning_mode", "standard")
    if tuning_mode == "generalization":
        labels = {
            "generalization_full": "泛化全集",
            "competitor_performance": "竞品性能",
            "baseline_performance": "NPU 基线性能",
            "generalization_tuning": "泛化调优子集",
            "functional_acceptance": "功能验收子集",
            "optimized_involved": "涉及优化用例集",
        }
    else:
        labels = {
            "performance_full": "性能全集",
            "performance_tuning": "性能调优子集",
            "functional_full": "功能全集",
            "functional_acceptance": "功能验收子集",
        }
    rows: list[str] = []
    for key, label in labels.items():
        item = collections.get(key)
        if not item:
            rows.append(f"| {label} | pending | - | - |")
            continue
        selection = item.get("selection", {})
        status = selection.get("confirmation", "frozen")
        rows.append(
            f"| {label} | {item.get('count', '-')} | `{str(item.get('sha256', '-'))[:12]}` | {status} |"
        )
    return rows


def performance_checkpoint(stage: str) -> bool:
    return stage == "final.performance" or stage.startswith("integration.performance.") or bool(
        re.fullmatch(r"(?:gen\.)?round[1-9]\d*\.complete|gen\.outer[1-9]\d*\.exit", stage)
    )


def prepare_performance(args: argparse.Namespace) -> tuple[dict[str, str], list[str]]:
    """Validate existing effect artifacts without collecting performance again."""
    required = (args.performance_summary, args.cumulative_performance_summary, args.selected_candidate)
    if not all(required):
        raise ValueError(
            "performance checkpoint requires --performance-summary, "
            "--cumulative-performance-summary and --selected-candidate"
        )
    references = {
        "round_summary": str(args.performance_summary.resolve()),
        "cumulative_summary": str(args.cumulative_performance_summary.resolve()),
        "selected_candidate": args.selected_candidate,
        "scope": args.performance_scope,
    }
    artifacts: list[str] = []
    summaries = []
    for key in ("round_summary", "cumulative_summary"):
        reference = references.get(key)
        if reference is None:
            raise ValueError(f"missing performance reference: {key}")
        path = Path(reference)
        summary = read_json(path)
        if not isinstance(summary, dict) or any(
            not isinstance(summary.get(field), str) for field in ("baseline_path", "candidate_path")
        ):
            raise ValueError(f"{path}: expected an effect summary with performance source paths")
        baseline = Path(summary["baseline_path"])
        candidate = Path(summary["candidate_path"])
        if not baseline.is_absolute() or not candidate.is_absolute():
            raise ValueError(f"{path}: performance source paths must be absolute")
        expected = recompute_summary(summary)
        if any(field not in summary or summary[field] != value for field, value in expected.items()):
            raise ValueError(f"{path}: effect summary differs from source performance or jitter policy")
        artifacts.extend([str(path), str(baseline), str(candidate)] + summary_dependency_paths(summary))
        summaries.append(summary)
    current, cumulative = summaries
    if current["candidate_path"] != cumulative["candidate_path"]:
        raise ValueError("round and cumulative summaries must reference the same selected performance")
    if [case["case_id"] for case in current["cases"]] != [case["case_id"] for case in cumulative["cases"]]:
        raise ValueError("round and cumulative summaries must cover the same ordered cases")
    return references, artifacts


def recorded_performance(record: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Only display evidence that still matches the completed checkpoint."""
    artifacts = {item["path"]: item for item in record.get("artifacts", [])}
    summaries = []
    for key in ("round_summary", "cumulative_summary"):
        path = record["performance"][key]
        if artifact_identity(path) != artifacts.get(path):
            raise ValueError(f"performance artifact changed or not registered: {path}")
        summary = read_json(Path(path))
        expected = recompute_summary(summary)
        if any(summary.get(k) != v for k, v in expected.items()):
            raise ValueError("recorded effect summary differs from recomputed policy/evidence")
        for source in [summary["baseline_path"], summary["candidate_path"]] + summary_dependency_paths(summary):
            if artifact_identity(source) != artifacts.get(source):
                raise ValueError(f"performance source changed or not registered: {source}")
        summaries.append(summary)
    return summaries[0], summaries[1]


def report_cell(value: Any) -> str:
    return html.escape(str(value)).replace("|", "&#124;").replace("`", "&#96;").replace("\n", "<br>")


def speedup_text(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.6f}x"


def _effective_counts(summary: dict[str, Any]) -> str:
    fields = (
        "effective_case_count",
        "effective_improvement_count",
        "effective_regression_count",
        "jitter_case_count",
    )
    return "/".join(str(summary[field]) for field in fields)


def _completed_checkpoints(state: dict[str, Any]) -> list[tuple[str, dict]]:
    checkpoints = [
        (name, record)
        for name, record in state.get("stages", {}).items()
        if performance_checkpoint(name) or record.get("performance")
    ]
    completion_order = {
        event.get("stage"): index
        for index, event in enumerate(state.get("events", []))
        if event.get("kind") == "stage" and event.get("status") == "complete"
    }
    checkpoints.sort(key=lambda item: (
        item[1].get("completed_at", item[1].get("updated_at", "")),
        completion_order.get(item[0], -1),
    ))
    return [(name, record) for name, record in checkpoints if record.get("completed_at")]


def _recorded_value(record: dict) -> tuple[object, str | None]:
    if record.get("status") != "complete":
        return None, f"保存点状态为 {record.get('status')}"
    if not record.get("performance"):
        return None, "尚未登记性能摘要；需用已有采集补齐"
    try:
        return recorded_performance(record), None
    except (OSError, KeyError, ValueError) as error:
        return None, str(error)


def _performance_availability(completed: list[tuple[str, dict]]) -> tuple[dict, dict]:
    available, errors = {}, {}
    for name, record in completed:
        value, error = _recorded_value(record)
        if error:
            errors[name] = error
        else:
            available[name] = value
    return available, errors


def _summary_metric_row(label: str, summary: dict) -> str:
    return (
        f"| {label} | {summary['total_case_count']} | {summary['jitter_case_count']} | "
        f"{summary['effective_case_count']} | {summary['effective_improvement_count']} | "
        f"{summary['effective_regression_count']} | {speedup_text(summary['effective_geomean_speedup'])} |"
    )


def _policy_evidence_lines(label: str, summary: dict) -> list[str]:
    lines = [
        f"- {label}规则：{summary.get('policy_id', 'legacy_jitter_v1')} "
        f"v{summary.get('policy_version', 1)}；待确认 {summary.get('inconclusive_case_count', 0)}。"
    ]
    for case in summary["cases"]:
        stats = case.get("statistical_evidence")
        if stats:
            estimator = "配对估计" if "paired_estimate_us" in stats else "独立样本估计"
            estimate = stats.get("paired_estimate_us", stats.get("estimate_us"))
            interval = stats.get("paired_ci_us", stats.get("ci_us"))
            lines.append(
                f"- {label} `{report_cell(case['case_id'])}`：依据 {case['classification_basis']}；"
                f"{estimator} {estimate:+.6f}us；95% CI {interval}；"
                f"方法 {stats['method']['id']}。"
            )
    return lines


def _case_table_rows(current: dict, cumulative: dict) -> list[str]:
    rows = []
    for case, total in zip(current["cases"], cumulative["cases"]):
        rows.append(
            f"| {report_cell(case['case_id'])} | {total['baseline_total_us']:.6f} | "
            f"{case['baseline_total_us']:.6f} | {case['candidate_total_us']:.6f} | "
            f"{case['delta_us']:+.6f} | {case['delta_percent']:+.6f} | "
            f"{speedup_text(case['speedup'])} | {case['classification']} | "
            f"{total['delta_us']:+.6f} | {total['delta_percent']:+.6f} | "
            f"{speedup_text(total['speedup'])} | {total['classification']} |"
        )
    return rows


def _latest_performance_lines(latest_name: str, latest: dict, errors: dict, available: dict) -> list[str]:
    lines = [f"- 最近性能保存点：`{report_cell(latest_name)}`（{latest.get('completed_at')}）"]
    if latest_name in errors:
        lines.append(f"- 当前性能结果不可用：{report_cell(errors[latest_name])}。")
        return lines
    current, cumulative = available[latest_name]
    performance = latest.get("performance")
    if not isinstance(performance, dict):
        raise ValueError("latest performance record is missing data")
    scope = "性能全集" if performance["scope"] == "full" else "本轮调优子集"
    lines.extend([
        f"- 当前保留实现：`{report_cell(performance['selected_candidate'])}`",
        f"- 统计范围：{scope}，{current['total_case_count']} 个 case；子集结果不代表未测全集。",
        "- 本轮变化相对轮初基线；累计变化相对原始基线，均只统计同一组已实测 case。",
        "- 有效几何加速比只统计冻结规则判为有效的 case；confidence规则的待确认项不计入有效指标。",
        "",
        "| 比较 | 总 case | 抖动 | 有效 | 有效提升 | 有效回退 | 有效几何加速比 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ])
    for label, summary in (("本轮", current), ("累计", cumulative)):
        lines.append(_summary_metric_row(label, summary))
    for label, summary in (("本轮", current), ("累计", cumulative)):
        lines.extend(_policy_evidence_lines(label, summary))
    lines.extend([
        "", "### 逐 case 当前性能", "",
        "差值 = 当前耗时 − 对应基线耗时，负值表示提升；抖动 case 保留展示但不计入有效指标。",
        "",
        "| case_id | 原始基线(us) | 轮初基线(us) | 当前(us) | 本轮差值(us) | 本轮变化(%) | 本轮加速比 | 本轮分类 | "
        "累计差值(us) | 累计变化(%) | 累计加速比 | 累计分类 |",
        "|---|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|---|",
    ])
    lines.extend(_case_table_rows(current, cumulative))
    lines.extend([
        "",
        f"- 本轮证据：`{report_cell(performance['round_summary'])}`",
        f"- 累计证据：`{report_cell(performance['cumulative_summary'])}`",
    ])
    return lines


def _performance_summary_lines(completed: list[tuple[str, dict]], errors: dict, available: dict) -> list[str]:
    lines = [
        "", "### 各轮性能汇总", "",
        "各行使用该保存点的实测集合，不跨轮拼接 case 或累计乘算加速比。",
        "",
        "| 保存点 | 保留实现 | 范围 | 总 case | 本轮有效/提升/回退/抖动 | 本轮有效几何加速比 | 累计有效/提升/回退/抖动 | 累计有效几何加速比 | 证据 |",
        "|---|---|---|---:|---|---:|---|---:|---|",
    ]
    for name, record in completed:
        if name in errors:
            continue
        current, cumulative = available[name]
        counts = [_effective_counts(summary) for summary in (current, cumulative)]
        performance = record["performance"]
        scope = "全集" if performance["scope"] == "full" else "调优子集"
        lines.append(
            f"| `{report_cell(name)}` | {report_cell(performance['selected_candidate'])} | "
            f"{scope} | {current['total_case_count']} | {counts[0]} | "
            f"{speedup_text(current['effective_geomean_speedup'])} | {counts[1]} | "
            f"{speedup_text(cumulative['effective_geomean_speedup'])} | "
            f"[本轮]({quote(performance['round_summary'])}) / "
            f"[累计]({quote(performance['cumulative_summary'])}) |"
        )
    if errors:
        lines.append("")
        lines.extend(
            f"- `{report_cell(name)}`：性能结果不可用，{report_cell(error)}。"
            for name, error in errors.items()
        )
    return lines


def performance_report(state: dict[str, Any]) -> list[str]:
    lines = ["", "## 当前性能结果", ""]
    completed = _completed_checkpoints(state)
    if not completed:
        return lines + ["- 尚无已完成轮次的性能结果。"]
    available, errors = _performance_availability(completed)
    latest_name, latest = completed[-1]
    lines.extend(_latest_performance_lines(latest_name, latest, errors, available))
    lines.extend(_performance_summary_lines(completed, errors, available))
    return lines


def structural_directions_report(state: dict[str, Any]) -> list[str]:
    directions = state.get("structural_directions", [])
    intent = state.get("optimization_intent", "safe_incremental")
    if not directions and intent != "pursue_optimal":
        return []
    lines = ["", "## 结构方向台账", ""]
    if intent == "pursue_optimal":
        lines.append(
            "> pursue_optimal：结构方向是跨轮义务。`not_attempted`/`blocked_by_scope` 未了结时，"
            "禁止以 success/completed 收尾（blocked_by_scope 须重冻结更宽 scope 后重试）。"
        )
    if not directions:
        lines.append("- 尚未登记结构方向。")
        return lines
    lines.extend(["", "| 方向 | 状态 | 轮次 | 预估收益 | 说明 | 证据 |", "|---|---|---:|---|---|---|"])
    for d in directions:
        lines.append(
            f"| `{report_cell(d.get('id'))}` | `{report_cell(d.get('status'))}` | "
            f"{report_cell(d.get('round'))} | {report_cell(d.get('estimated_gain'))} | "
            f"{report_cell(d.get('description'))} | {report_cell(d.get('evidence'))} |"
        )
    unresolved = [d.get("id") for d in directions if d.get("status") in UNRESOLVED_STRUCTURAL_STATUSES]
    if unresolved:
        lines.append("")
        lines.append(f"- ⚠ 未了结结构方向：{', '.join(f'`{i}`' for i in unresolved)}（阻止 success/completed 收尾）。")
    return lines


def report_next_action(state: dict[str, Any]) -> str:
    """A lifecycle boundary supersedes the previous stage's action."""
    for event in reversed(state.get("events", [])):
        if event.get("kind") == "finish":
            return "任务已结束" if event.get("status") == "success" else "处理终态记录中的未决事项"
        if event.get("next_action"):
            return report_cell(event["next_action"])
        if event.get("kind") == "stage":
            if event.get("status") == "in_progress":
                return f"等待 `{report_cell(event['stage'])}` 产出并复核"
            return "复核保存点，确定后续阶段"
    return report_cell(state.get("precision", {}).get("next_action") or state.get("next_action") or "等待当前阶段产出")


def report_stage_conclusion(state: dict[str, Any]) -> str:
    for event in reversed(state.get("events", [])):
        if event.get("kind") != "stage" or event.get("status") != "complete":
            continue
        stage = event["stage"]
        record = state.get("stages", {}).get(stage, {})
        if record.get("status") != "complete":
            return f"`{report_cell(stage)}` 当前为 `{report_cell(record.get('status'))}`，原结论待复核"
        message = event.get("message") or "已完成，详见保存点证据"
        return f"`{report_cell(stage)}`：{report_cell(message)}"
    return "尚无已验收阶段结论"


def _objective_text(objective: dict) -> str:
    if objective.get("mode") == "fixed_rounds":
        return f"固定 {objective.get('rounds', '-')} 轮"
    if objective.get("mode") == "target":
        comparison = {"ge": ">=", "le": "<=", "eq": "="}.get(objective.get("comparison"), "?")
        text = (
            f"{objective.get('metric', '-')} {comparison} {objective.get('value', '-')} "
            f"{objective.get('unit') or ''}"
        ).strip()
        if objective.get("max_rounds") is not None:
            text += f"（最多 {objective['max_rounds']} 轮）"
        return text
    return "未配置"


def _summary_lines(state: dict, configuration: dict, tuning_mode: str, objective_text: str) -> list[str]:
    terminal = state.get("terminal", {})
    operator = state.get("operator", {})
    environments = configuration.get("environments", {})
    python_environment = environments.get("python", {})
    cann_environment = environments.get("cann", {})
    current = state.get("current_stage") or ("阶段间歇" if state.get("stages") else "未开始")
    return [
        "# 性能调优报告",
        "",
        "> 本报告由 `run-manifest.json` 与 `workflow-state.json` 持续生成；既是执行现场，也是最终交付。",
        "",
        "## 当前结论",
        "",
        f"- 任务状态：`{terminal.get('status', 'running')}`",
        f"- 当前阶段：`{current}`",
        f"- 调优模式：`{tuning_mode}`",
        f"- 优化意图：`{state.get('optimization_intent', configuration.get('optimization_intent', 'safe_incremental'))}`",
        f"- 性能参考锚点：`{state.get('reference_perf') or configuration.get('reference_perf') or '未设置'}`",
        f"- 语言后端：`{configuration.get('backend', 'ascendc')}`",
        f"- DSL 配置：`{json.dumps(configuration.get('dsl'), ensure_ascii=False)}`",
        f"- 已验证目标 SoC：`{', '.join(configuration.get('target_socs', []))}`",
        f"- 优化目标：{objective_text}",
        f"- Python：`{python_environment.get('executable', '-')}` ({python_environment.get('version', '-')})",
        f"- Python 激活命令：`{python_environment.get('activation_command') or '无需'}`",
        f"- CANN 环境：`{cann_environment.get('setup_command', '-')}`",
        f"- 最近验收结论：{report_stage_conclusion(state)}",
        f"- 下一动作：{report_next_action(state)}",
        f"- 安全恢复点：{operator.get('safe_restore_point') or state.get('safe_restore_point') or '输入已冻结'}",
        f"- 最后更新：{state.get('updated_at', '-')}",
    ]


def _generalization_lines(generalization: dict) -> list[str]:
    thresholds = generalization.get("ratio_thresholds", {})
    return [
        f"- 竞品来源：`{generalization.get('competitor', {}).get('source', '-')}`",
        f"- 泛化目标用例数：{generalization.get('target_case_count', '-')}",
        f"- Ratio 门限：geomean ≥ {thresholds.get('geomean', 1.0)}，min ≥ {thresholds.get('minimum', 0.6)}",
        f"- 循环上限：内层 {generalization.get('inner_max_rounds', 3)} 轮，"
        f"外层 {generalization.get('outer_max_iterations', 2)} 次",
    ]


def _five_stage_lines(configuration: dict, state: dict) -> list[str]:
    lines = ["", "## 五阶段交接", "", "| 阶段 | 状态 |", "|---|---|"]
    for phase, label in zip(PHASES, ("基线评估", "前处理", "诊断分析", "实施验证", "后处理")):
        record = state.get("stages", {}).get(f"phase.{phase}", {})
        lines.append(f"| {label} | {record.get('status', 'pending')} |")
    for phase in ("baseline", "integration"):
        record = state.get("stages", {}).get(f"phase.{phase}", {})
        for artifact in record.get("artifacts", []):
            name = Path(artifact["path"]).name
            if name in ("环境检查报告.md", "性能目标.md", "VERIFY_REPORT.md"):
                lines.append(f"- [{name}]({quote(artifact['path'])})（{record.get('status', 'pending')}）")
    return lines


def _mode_lines(configuration: dict, state: dict) -> list[str]:
    lines = []
    if configuration.get("tuning_mode") == "generalization":
        lines.extend(_generalization_lines(configuration.get("generalization", {})))
    reference = configuration.get("performance_reference")
    if reference:
        lines.append(f"- 性能对标：`{report_cell(reference['kind'])}`；目标比率：{reference['target_ratio']}")
    if configuration.get("workflow_layout") == "five-stage-v1":
        lines.extend(_five_stage_lines(configuration, state))
    return lines


def _inventory_lines(manifest: dict, request: dict, configuration: dict) -> list[str]:
    functional_status = (
        manifest.get('collections', {}).get('functional_full', {})
        .get('validation', {}).get('status', 'pending')
    )
    return [
        "",
        "## 输入与冻结集合",
        "",
        "| 集合 | 数量 | SHA-256 | 状态 |",
        "|---|---:|---|---|",
        *manifest_summary(manifest),
        "",
        f"- 优化请求：`{request.get('path', '-')}` (`{str(request.get('sha256', '-'))[:12]}`)",
        f"- 代码目录：`{manifest.get('inputs', {}).get('code', {}).get('path', '-')}`",
        f"- 功能模式：`{configuration.get('functional_mode', '-')}`",
        f"- 功能库存静态检查：`{functional_status}`",
        "",
        "## 阶段",
        "",
        "| 阶段 | 状态 | 开始 | 完成 | 耗时(s) | 证据 |",
        "|---|---|---|---|---:|---:|",
    ]


def _stage_lines(stages: dict) -> list[str]:
    if not stages:
        return ["| - | 未开始 | - | - | - | 0 |"]
    lines = []
    for name, record in stages.items():
        elapsed = record.get('elapsed_seconds')
        lines.append(
            f"| `{name}` | {record.get('status', '-') or '-'} | {report_cell(record.get('started_at') or '-')} | "
            f"{report_cell(record.get('completed_at') or '-')} | "
            f"{report_cell(elapsed if elapsed is not None else '-')} | "
            f"{len(record.get('artifacts', []))} |"
        )
    return lines


def _precision_lines(precision: dict) -> list[str]:
    baseline = precision.get("known_baseline_failures", [])
    regressions = precision.get("new_or_worsened_failures", [])
    lines = ["", "## 精度状态", "", f"- 已证实基线失败：{len(baseline)}"]
    for item in baseline:
        lines.append(f"  - `{item.get('case_id', '-')}`：{item.get('message', '-')} ({item.get('evidence', '-')})")
    lines.append(f"- 候选新增/恶化失败：{len(regressions)}")
    for item in regressions:
        lines.append(f"  - `{item.get('case_id', '-')}`：{item.get('message', '-')} ({item.get('evidence', '-')})")
    lines.append(f"- 当前假设：{precision.get('current_hypothesis') or '无'}")
    excluded = precision.get("excluded_hypotheses", [])
    lines.append(f"- 已排除假设：{'; '.join(excluded) if excluded else '无'}")
    return lines


def _progress_lines(state: dict) -> list[str]:
    lines = ["", "## 最近进展", ""]
    progress_events = [
        event for event in state.get("events", [])
        if event.get("kind") in ("progress", "diagnosis", "decision", "stage")
    ]
    if not progress_events:
        return lines + ["- 输入已冻结，等待首个阶段。"]
    for event in progress_events[-12:]:
        message = event.get("message") or f"{event.get('stage', '-')} → {event.get('status', '-')}"
        lines.append(f"- {event.get('at', '-')} `{event.get('kind')}`：{message}")
    return lines


def _candidate_lines(state: dict, stages: dict) -> list[str]:
    lines = ["", "## 候选与逐轮选择", ""]
    candidate_events = [event for event in state.get("events", []) if event.get("candidate")]
    latest_candidates: dict[str, dict[str, Any]] = {}
    for event in candidate_events:
        latest_candidates[event["candidate"]] = event
    if latest_candidates:
        lines.extend(["| 候选 | 阶段 | 最新结论 | 证据 |", "|---|---|---|---|"])
        for candidate, event in sorted(latest_candidates.items()):
            details = event.get("details") or {}
            conclusion = event.get("message", "-")
            if details:
                conclusion += "；" + "，".join(f"{key}={value}" for key, value in sorted(details.items()))
            lines.append(
                f"| `{candidate}` | `{event.get('stage', '-')}` | {conclusion} | {event.get('evidence', '-')} |"
            )
    else:
        lines.append("- 尚无候选结论。")
    selection_stages = [
        (name, record) for name, record in stages.items()
        if name.endswith(".selection") or name == "final.selection"
    ]
    for name, record in selection_stages:
        context = "；".join(record.get("context", [])) or "见登记 artifact"
        lines.append(f"- `{name}`：{record.get('status', '-')}；{context}")
    return lines


def _operator_lines(operator: dict) -> list[str]:
    lines = ["", "## 人工介入", ""]
    if operator.get("awaiting"):
        lines.append("- 状态：等待人工")
        lines.append(f"- 问题：{operator.get('question', '-')}")
    else:
        lines.append("- 状态：无需人工输入")
    if operator.get("last_decision"):
        lines.append(f"- 最近决策：{operator['last_decision']}")
    return lines


def _terminal_lines(terminal: dict) -> list[str]:
    lines = ["", "## 最终验收", ""]
    if terminal:
        lines.extend([
            f"- 终态：`{terminal.get('status')}`",
            f"- 原因码：`{terminal.get('reason_code', '-')}`",
            f"- 结论：{terminal.get('message', '-')} ",
            f"- 完成时间：{terminal.get('at', '-')} ",
        ])
    else:
        lines.append("- 尚未进入终态；已完成证据见阶段表，候选与逐轮选择见对应 artifact。")
    return lines + [""]


def report_text(state: dict[str, Any]) -> str:
    manifest_path = Path(state["manifest"]["path"])
    manifest = (
        read_manifest(manifest_path)
        if manifest_path.exists()
        else {"inputs": {}, "collections": {}, "configuration": {}}
    )
    configuration = manifest.get("configuration", {})
    terminal = state.get("terminal", {})
    operator = state.get("operator", {})
    precision = state.get("precision", {})
    tuning_mode = configuration.get("tuning_mode", "standard")
    objective_text = _objective_text(configuration.get("optimization_objective", {}))
    request = manifest.get("request", {})
    stages = state.get("stages", {})
    lines = _summary_lines(state, configuration, tuning_mode, objective_text)
    lines.extend(_mode_lines(configuration, state))
    lines.extend(performance_report(state))
    lines.extend(structural_directions_report(state))
    lines.extend(_inventory_lines(manifest, request, configuration))
    lines.extend(_stage_lines(stages))
    lines.extend(_precision_lines(precision))
    lines.extend(_progress_lines(state))
    lines.extend(_candidate_lines(state, stages))
    lines.extend(_operator_lines(operator))
    lines.extend(_terminal_lines(terminal))
    return "\n".join(lines)


def commit(state_path: Path, state: dict[str, Any]) -> None:
    state["updated_at"] = utc_now()
    report = report_text(state)
    atomic_json(state_path, state)
    atomic_text(state_path.parent / "性能调优报告.md", report)


def workflow_version(args: argparse.Namespace) -> str:
    return getattr(args, "workflow_version", None) or WORKFLOW_VERSION


def _resume_payload(state: dict, state_path: Path, manifest_path: Path,
                    manifest_id: dict, version: str) -> tuple[dict, int]:
    manifest_entry = state.get("manifest", {})
    if (
        manifest_entry.get("path") != str(manifest_path)
        or manifest_entry.get("sha256") != manifest_id["sha256"]
    ):
        return {"status": "stale_inputs", "reason": "run_manifest_changed"}, 3
    if state.get("workflow_version") != version:
        return {
            "status": "resume_with_workflow_change",
            "current": state.get("workflow_version"),
            "requested": version,
        }, 5
    invalid = [name for name, record in state.get("stages", {}).items() if record.get("status") == "invalid"]
    status = "resume_with_invalid_checkpoints" if invalid else "resume"
    return {"status": status, "invalid_stages": invalid, "state": str(state_path)}, (4 if invalid else 0)


def _new_state(manifest: dict, manifest_id: dict, version: str) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "workflow_version": version,
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "manifest": manifest_id,
        "backend": manifest["configuration"].get("backend", "ascendc"),
        "dsl": manifest["configuration"].get("dsl"),
        **({"schedule_policy": manifest["configuration"]["schedule_policy"]}
           if "schedule_policy" in manifest["configuration"] else {}),
        **({"performance_effect_policy": policy(manifest["configuration"]["performance_effect_policy"])}
           if "performance_effect_policy" in manifest["configuration"] else {}),
        "tuning_mode": manifest["configuration"].get("tuning_mode", "standard"),
        "optimization_intent": manifest["configuration"].get("optimization_intent", "safe_incremental"),
        "reference_perf": manifest["configuration"].get("reference_perf"),
        "current_stage": None,
        "stages": {},
        "structural_directions": [],
        "events": [],
        "precision": {
            "policy": manifest["configuration"]["precision_diagnosis_policy"],
            "known_baseline_failures": [],
            "new_or_worsened_failures": [],
            "excluded_hypotheses": [],
            "current_hypothesis": None,
            "next_action": None,
        },
        "operator": {"awaiting": False, "safe_restore_point": "inputs_frozen"},
        "safe_restore_point": "inputs_frozen",
    }


def command_start(args: argparse.Namespace) -> int:
    state_path = args.state.resolve()
    manifest_path = args.manifest.resolve()
    manifest = read_manifest(manifest_path)
    manifest_id = artifact_identity(manifest_path)
    version = workflow_version(args)
    with state_lock(state_path):
        if state_path.exists():
            payload, code = _resume_payload(read_json(state_path), state_path, manifest_path,
                                            manifest_id, version)
            emit(json.dumps(payload, ensure_ascii=False))
            return code
        state = _new_state(manifest, manifest_id, version)
        append_event(state, "start", message="输入与配置已冻结")
        commit(state_path, state)
    emit(
        json.dumps(
            {"status": "new", "state": str(state_path), "report": str(state_path.parent / '性能调优报告.md')},
            ensure_ascii=False,
        )
    )
    return 0


def validate_frozen_effect_policy(state, manifest):
    if state.get("schedule_policy") != manifest["configuration"].get("schedule_policy"):
        raise ValueError("schedule policy changed; start a new run")
    if policy(state.get("performance_effect_policy")) != policy(
            manifest["configuration"].get("performance_effect_policy")):
        raise ValueError("performance effect policy changed; start a new run")


def command_sync_manifest(args: argparse.Namespace) -> int:
    state_path = args.state.resolve()
    with state_lock(state_path):
        state = read_json(state_path)
        manifest_path = Path(state["manifest"]["path"])
        manifest = read_manifest(manifest_path)
        validate_frozen_effect_policy(state, manifest)
        state["manifest"] = artifact_identity(manifest_path)
        if (state.get("backend", "ascendc") != manifest["configuration"].get("backend", "ascendc")
                or state.get("dsl") != manifest["configuration"].get("dsl")):
            raise ValueError("backend/DSL configuration changed; start a new run instead of switching language")
        state["tuning_mode"] = manifest["configuration"].get("tuning_mode", "standard")
        state["optimization_intent"] = manifest["configuration"].get(
            "optimization_intent", state.get("optimization_intent", "safe_incremental")
        )
        state["reference_perf"] = manifest["configuration"].get("reference_perf", state.get("reference_perf"))
        state["precision"]["policy"] = manifest["configuration"]["precision_diagnosis_policy"]
        append_event(state, "manifest", message=args.message or "run manifest synchronized")
        commit(state_path, state)
    emit(json.dumps({"status": "manifest_synchronized"}, ensure_ascii=False))
    return 0


def schedule_stage_kind(stage):
    if stage == "phase.integration":
        return "integration"
    if stage == "phase.analysis" or re.fullmatch(r"(?:gen\.)?round[1-9]\d*\.analysis", stage):
        return "model"
    if stage == "phase.implementation" or re.fullmatch(r"(?:gen\.)?round[1-9]\d*\.(?:impl\.[^.]+|complete)", stage):
        return "runtime"
    return None


def _check_model_schedule(value, manifest_path, extra):
    """Verify an analysis schedule report and append its bound artifacts."""
    from validate_implementation_conformance import required_feature_ids, validate_manifest_scope
    from validate_schedule_contract import ref, require, verify_ref, verify_report

    required_feature_ids(value)
    validate_manifest_scope(value, read_manifest(manifest_path))
    schedule = value.get("schedule", {})
    deps = {}
    contract = verify_ref(schedule.get("contract"), deps)
    gate = verify_ref(schedule.get("check"), deps)
    checked = verify_report(gate, manifest_path, "model")
    require(checked["contract"] == ref(contract) and checked["scheme_id"] == value["scheme_id"],
            "analysis schedule scheme mismatch")
    extra.extend([str(contract), str(gate), *checked["dependencies"]])


def _check_implementation_schedule(value, level, manifest_path, selected_candidate, extra, path):
    """Re-run implementation conformance and append its bound artifacts."""
    import subprocess
    import sys
    from validate_schedule_contract import ref, require, verify_report

    identity = value["evidence_identity"]
    require(value.get("decision") == "pass" and value.get("schedule"),
            "implementation requires schedule conformance gate")
    require(identity["manifest"] == ref(manifest_path), "conformance manifest identity mismatch")
    if selected_candidate is not None:
        require(str(selected_candidate) == value.get("scheme_id")
                or Path(identity["candidate"]["path"]).resolve() == Path(selected_candidate).resolve(),
                "selected candidate differs from schedule conformance")
    command = ["timeout", "60s", sys.executable,
               str(Path(__file__).with_name("validate_implementation_conformance.py"))]
    for key in ("contract", "result", "manifest", "isolation_scope", "baseline", "candidate"):
        command.extend(["--" + key.replace("_", "-"), identity[key]["path"]])
    result = subprocess.run(command + ["--verify-existing", str(path)],
                            capture_output=True, text=True, timeout=65)
    require(result.returncode == 0,
            "implementation conformance is stale/invalid: " + result.stdout + result.stderr)
    checked = verify_report(value["schedule"]["runtime"]["path"], manifest_path, "runtime",
                            identity["candidate"]["path"])
    if level == "integration":
        require(checked.get("integration"),
                "integration requires actual integrated source/build/load schedule evidence")
    extra.extend(checked["dependencies"])
    extra.extend(value["schedule"][name]["path"] for name in ("model", "runtime"))
    # Source trees are re-snapshotted by conformance on recovery. Register
    # evidence files individually so unrelated logs do not invalidate it.
    extra.extend(identity[key]["path"] for key in ("contract", "result", "isolation_scope"))
    extra.extend(identity.get("feature_evidence", {}))


def check_schedule_artifacts(level, paths, manifest_path, selected_candidate=None):
    """Recompute saved gates; filenames or a declared pass are insufficient."""
    from validate_schedule_contract import policy_enabled
    if not policy_enabled(read_manifest(manifest_path)):
        return paths
    extra, found = [], 0
    for raw in paths:
        path = Path(raw).resolve()
        if path.suffix != ".json" or not path.is_file():
            continue
        value = read_json(path)
        if not isinstance(value, dict):
            continue
        if level == "model" and value.get("schema_version") == 3 and "implementation_mode" in value:
            _check_model_schedule(value, manifest_path, extra)
            found += 1
        elif level in ("runtime", "integration") and "evidence_identity" in value and "conformance_failures" in value:
            _check_implementation_schedule(value, level, manifest_path, selected_candidate, extra, path)
            found += 1
    if not found:
        raise ValueError(f"schedule policy requires {level} bound contract/conformance artifacts")
    return list(dict.fromkeys(paths + extra))


def check_schedule_handoff(stage, state, manifest_path):
    from validate_schedule_contract import policy_enabled
    if not policy_enabled(read_manifest(manifest_path)):
        return
    match = re.fullmatch(r"((?:gen\.)?round[1-9]\d*)\.impl\.([^.]+)", stage)
    predecessor = match[1] + ".analysis" if match else "phase.analysis"
    record = state.get("stages", {}).get(predecessor, {})
    if record.get("status") != "complete":
        raise ValueError(f"schedule analysis handoff incomplete: {predecessor}")
    paths = [a["path"] for a in record.get("artifacts", [])]
    for artifact in record.get("artifacts", []):
        if artifact_identity(artifact["path"]) != artifact:
            raise ValueError("schedule analysis artifact changed; re-analyze")
    check_schedule_artifacts("model", paths, manifest_path)
    if match:
        values = [read_json(Path(p)) for p in paths if Path(p).suffix == ".json"]
        schemes = {v.get("scheme_id") for v in values if isinstance(v, dict)}
        if match[2] not in schemes:
            raise ValueError("implementation scheme absent from this round's analysis")


def check_runtime_handoff(stage, paths, state):
    """The implemented scheme contract must be the one accepted at analysis."""
    from validate_schedule_contract import require
    match = re.match(r"((?:gen\.)?round[1-9]\d*)\.", stage)
    allowed = [match[1] + ".analysis"] if match else [
        name for name in state.get("stages", {}) if schedule_stage_kind(name) == "model"]
    accepted = {}
    for name in allowed:
        record = state.get("stages", {}).get(name, {})
        if record.get("status") != "complete":
            continue
        for artifact in record.get("artifacts", []):
            accepted[artifact["path"]] = artifact["sha256"]
    for raw in paths:
        path = Path(raw)
        if path.suffix != ".json" or not path.is_file():
            continue
        value = read_json(path)
        if not isinstance(value, dict) or "conformance_failures" not in value:
            continue
        scheme_match = re.fullmatch(r"(?:gen\.)?round[1-9]\d*\.impl\.([^.]+)", stage)
        if scheme_match:
            require(value.get("scheme_id") == scheme_match[1], "conformance scheme differs from implementation stage")
        contract = value.get("evidence_identity", {}).get("contract", {})
        require(accepted.get(contract.get("path")) == contract.get("sha256"),
                "implementation contract was not frozen by this round's analysis")


def _baseline_artifacts(files: dict, manifest_path: Path) -> list[str]:
    from build_performance_targets import build

    preflight = read_json(files["preflight-report.json"])
    if preflight.get("status") not in ("pass", "warn") or preflight.get("fail_count") != 0:
        raise ValueError("baseline phase requires a passing preflight")
    manifest = read_manifest(manifest_path)
    if manifest["configuration"].get("backend", "ascendc") == "cannbot_dsl":
        if preflight.get("backend") != "cannbot_dsl" or not preflight.get("dsl_environment"):
            raise ValueError("DSL baseline requires its own backend/environment preflight")
        from dsl_evidence import verify_file
        _dsl_env_extra = verify_file(preflight["dsl_environment"])
    manifest = read_manifest(manifest_path)
    if preflight.get("request_sha256") != manifest["request"]["sha256"]:
        raise ValueError("preflight request identity mismatch")
    saved = read_json(files["performance-targets.json"])
    evidence = Path(saved["evidence"]["path"])
    if build(manifest_path, evidence) != saved:
        raise ValueError("target evidence or input identity changed")
    extra = [str(evidence)]
    for row in saved["cases"]:
        extra.extend(item["path"] for item in row["source_artifacts"])
    if manifest["configuration"]["performance_reference"]["kind"] != "baseline":
        return extra
    identity_path = files.get("execution-identity.json")
    if identity_path is None:
        raise ValueError("baseline reference requires execution-identity.json")
    execution_identity = validate_execution_identity(manifest_path, identity_path)
    extra.extend(dependency_paths(execution_identity))
    return extra


def _gate_evidence_pair(gate: dict, key: str) -> tuple[Path, Path] | None:
    side = gate["collections"].get("functional", {}).get(key)
    if not side:
        return None
    return (
        Path(side["baseline"]["evidence"]["path"]),
        Path(side["candidate"]["evidence"]["path"]),
    )


def _check_postprocess_gate(gate: dict, manifest_path: Path) -> list[str]:
    from validate_postprocess_performance import validate

    paths_by_kind = {kind: (Path(item["baseline"]["path"]), Path(item["candidate"]["path"]))
                     for kind, item in gate["collections"].items()}
    functional_errors = _gate_evidence_pair(gate, "expected_errors")
    functional_host_checks = _gate_evidence_pair(gate, "host_checks")
    functional_baseline_failures = _gate_evidence_pair(gate, "baseline_failures")
    host_gate = gate["collections"].get("functional", {}).get("host_checks") or {}
    baseline_failure_gate = gate["collections"].get("functional", {}).get("baseline_failures") or {}
    effect_evidence = {k: [Path(p) for p in v] for k, v in gate.get("effect_evidence", {}).items()}
    same_implementation = {k: Path(p) for k, p in gate.get("same_implementation", {}).items()}
    if validate(manifest_path, gate["target_soc"], paths_by_kind,
                functional_errors=functional_errors,
                functional_host_checks=functional_host_checks,
                functional_baseline_failures=functional_baseline_failures,
                effect_evidence=effect_evidence,
                same_implementation=same_implementation) != gate or gate['decision'] != 'pass':
        raise ValueError("postprocess gate is stale or has regressions")
    extra = [str(p) for pair in paths_by_kind.values() for p in pair]
    if functional_errors:
        extra.extend(str(p) for p in functional_errors)
    if functional_host_checks:
        extra.extend(str(p) for p in functional_host_checks)
        extra.extend(item["path"] for side in host_gate.values() for item in side["raw_evidence"])
    if functional_baseline_failures:
        extra.extend(str(p) for p in functional_baseline_failures)
        extra.extend(item["path"] for side in baseline_failure_gate.values() for item in side["raw_evidence"])
    return extra


def _integration_artifacts(files: dict, manifest_path: Path) -> list[str]:
    manifest = read_manifest(manifest_path)
    gates = {}
    extra: list[str] = []
    for path in files.values():
        if path.suffix != ".json":
            continue
        gate = read_json(path)
        if not isinstance(gate, dict):
            continue  # Raw execution records can be JSON arrays, not full gates.
        if gate.get("schema_version") not in (1, 2) or "target_soc" not in gate or "collections" not in gate:
            continue
        if gate["target_soc"] in gates:
            raise ValueError("duplicate postprocess gate for target SoC")
        extra.extend(_check_postprocess_gate(gate, manifest_path))
        gates[gate['target_soc']] = gate
        for item in gate["collections"].values():
            extra.extend(summary_dependency_paths(item["summary"]))
    if set(gates) != set(manifest['configuration']['target_socs']):
        raise ValueError("postprocess requires both full inventories on every target SoC")
    return extra


def check_phase_artifacts(phase: str, paths: list[str], manifest_path: Path,
                          user_paths: list[str] | None = None) -> list[str]:
    """Check new phase outputs; source/route semantics remain separate gates.

    user_paths: artifacts explicitly registered by the operator for this phase,
    before schedule-dependency extras were appended. Phase evidence lookups are
    name-keyed, and schedule closures legitimately carry same-named evidence
    from earlier rounds (e.g. dsl-compile-evidence.json); the operator's
    explicit registration must win over closure extras.
    """
    files = {Path(path).name: Path(path).resolve() for path in (user_paths if user_paths is not None else paths)}
    required = {
        "baseline": ("环境检查报告.md", "性能目标.md", "performance-targets.json", "preflight-report.json"),
        "preparation": ("extraction-manifest.json", "source-compatibility.md", "functional-acceptance.md"),
        "analysis": ("analysis.md",),
        "implementation": ("final-functional-regression.md", "final-performance-comparison.md"),
        "integration": ("VERIFY_REPORT.md",),
    }
    missing = set(required.get(phase, ())) - set(files)
    if missing:
        raise ValueError(f"{phase} phase missing artifacts: {sorted(missing)}")
    extra: list[str] = []
    manifest = read_manifest(manifest_path)
    if phase in ("analysis", "implementation", "integration"):
        level = {"analysis": "model", "implementation": "runtime", "integration": "integration"}[phase]
        extra.extend(check_schedule_artifacts(level, paths, manifest_path))
    if manifest["configuration"].get("backend", "ascendc") == "cannbot_dsl":
        if phase in ("preparation", "implementation", "integration"):
            from dsl_evidence import validate as validate_dsl_evidence
            evidence_path = files.get("dsl-compile-evidence.json")
            if evidence_path is None:
                raise ValueError(f"DSL {phase} requires dsl-compile-evidence.json")
            evidence = read_json(evidence_path)
            expected_collection = ("functional_acceptance" if phase == "preparation"
                                   else "generalization_full"
                                   if manifest["configuration"].get("tuning_mode") == "generalization"
                                   else "performance_full")
            if evidence.get("collection") != expected_collection:
                raise ValueError(f"DSL {phase} requires compiled coverage of {expected_collection}")
            extra.extend(validate_dsl_evidence(evidence, manifest_path, phase))
    if phase == "baseline":
        extra.extend(_baseline_artifacts(files, manifest_path))
    if phase == "integration":
        extra.extend(_integration_artifacts(files, manifest_path))
    return list(dict.fromkeys(paths + extra))


def _phase_artifact_check(args: argparse.Namespace, state: dict, manifest_path: Path,
                          user_artifacts: list[str] | None = None) -> list[str]:
    manifest = read_manifest(manifest_path)
    if manifest["configuration"].get("workflow_layout") != "five-stage-v1" or not args.stage.startswith("phase."):
        return args.artifact or []
    phase = args.stage.removeprefix("phase.")
    if phase not in PHASES:
        raise ValueError("unknown workflow phase")
    if args.status in ("in_progress", "complete"):
        for predecessor in PHASES[:PHASES.index(phase)]:
            if state.get("stages", {}).get(f"phase.{predecessor}", {}).get("status") != "complete":
                raise ValueError(f"phase prerequisite incomplete: {predecessor}")
    if args.status == "complete":
        return check_phase_artifacts(phase, args.artifact or [], manifest_path, user_paths=user_artifacts)
    return args.artifact or []


def _complete_record(record: dict, state: dict, args: argparse.Namespace,
                     timestamp: str, has_performance: bool) -> None:
    started_at = resolve_stage_started_at(state, args.stage, record)
    if started_at:
        record["started_at"] = started_at
        record["elapsed_seconds"] = round((parse_time(timestamp) - parse_time(started_at)).total_seconds(), 3)
    else:
        record.pop("started_at", None)
        record["elapsed_seconds"] = None
    record["completed_at"] = timestamp
    record["artifacts"] = [artifact_identity(path) for path in (args.artifact or [])]
    if has_performance or performance_checkpoint(args.stage):
        performance, paths = prepare_performance(args)
        manifest = read_manifest(Path(state["manifest"]["path"]))
        frozen_policy = policy(manifest["configuration"].get("performance_effect_policy"))
        for key in ("round_summary", "cumulative_summary"):
            saved = read_json(Path(performance[key]))
            saved_policy = policy({"id": saved.get("policy_id", "legacy_jitter_v1"),
                                   "version": saved.get("policy_version", 1)})
            if saved_policy != frozen_policy:
                raise ValueError("performance summary policy differs from frozen manifest")
            if ((args.stage == "final.performance" or args.stage.startswith("integration.performance."))
                    and saved.get("inconclusive_case_count", 0)):
                raise ValueError("final performance has inconclusive cases requiring confirmation")
            if args.stage.startswith("integration.performance.") and saved.get("effective_regression_count", 0):
                raise ValueError("integrated performance has regressions requiring original-code routing")
        record["performance"] = performance
        paths = list(dict.fromkeys([item["path"] for item in record["artifacts"]] + paths))
        record["artifacts"] = [artifact_identity(path) for path in paths]
    else:
        record.pop("performance", None)
    state["safe_restore_point"] = args.stage
    state.setdefault("operator", {})["safe_restore_point"] = args.stage
    current_stage = state.get("current_stage") or ""
    round_prefix = args.stage.removesuffix(".complete") + "."
    stage_matches = current_stage == args.stage
    round_matches = (
        args.stage.endswith(".complete")
        and performance_checkpoint(args.stage)
        and current_stage.startswith(round_prefix)
    )
    if stage_matches or round_matches:
        state["current_stage"] = None


def _skipped_record(record: dict, state: dict, args: argparse.Namespace, timestamp: str) -> None:
    started_at = resolve_stage_started_at(state, args.stage, record)
    if started_at:
        record["started_at"] = started_at
        record["elapsed_seconds"] = round((parse_time(timestamp) - parse_time(started_at)).total_seconds(), 3)
    else:
        record.pop("started_at", None)
        record["elapsed_seconds"] = None
    record["completed_at"] = timestamp
    record["reason"] = args.reason
    record["artifacts"] = [artifact_identity(path) for path in (args.artifact or [])]
    state["safe_restore_point"] = args.stage


def _apply_mark_status(record: dict, state: dict, args: argparse.Namespace,
                       timestamp: str, has_performance: bool) -> None:
    if args.status == "in_progress":
        record.setdefault("started_at", timestamp)
        state["current_stage"] = args.stage
    elif args.status == "complete":
        _complete_record(record, state, args, timestamp, has_performance)
    elif args.status == "skipped":
        _skipped_record(record, state, args, timestamp)
    elif args.status == "invalid":
        record["invalidated_at"] = timestamp
        record["reason"] = args.reason or "artifact_or_workflow_changed"


def command_mark(args: argparse.Namespace) -> int:
    if args.reason and args.status not in ("skipped", "invalid"):
        raise ValueError("--reason is valid only with --status skipped or invalid")
    has_performance = any((args.performance_summary, args.cumulative_performance_summary, args.selected_candidate))
    if has_performance and args.status != "complete":
        raise ValueError("performance summaries are valid only with --status complete")
    state_path = args.state.resolve()
    with state_lock(state_path):
        state = read_json(state_path)
        manifest_path = Path(state["manifest"]["path"])
        manifest = read_manifest(manifest_path)
        validate_frozen_effect_policy(state, manifest)
        from validate_schedule_contract import policy_enabled
        schedule_kind = schedule_stage_kind(args.stage)
        user_artifacts = list(args.artifact or [])
        if schedule_kind and policy_enabled(manifest):
            if args.status == "skipped":
                raise ValueError("schedule handoff/acceptance cannot be skipped")
            if (schedule_kind == "runtime" and args.status in ("in_progress", "complete")
                    and not args.stage.endswith(".complete")):
                check_schedule_handoff(args.stage, state, manifest_path)
            if args.status == "complete":
                selected = args.selected_candidate if schedule_kind == "runtime" else None
                args.artifact = check_schedule_artifacts(schedule_kind, args.artifact or [], manifest_path, selected)
            if schedule_kind == "runtime" and args.status == "complete":
                check_runtime_handoff(args.stage, args.artifact, state)
        args.artifact = _phase_artifact_check(args, state, manifest_path, user_artifacts=user_artifacts)
        previous = state.setdefault("stages", {}).get(args.stage, {})
        timestamp = utc_now()
        record = dict(previous)
        record["status"] = args.status
        record["updated_at"] = timestamp
        _apply_mark_status(record, state, args, timestamp, has_performance)
        if args.context:
            record["context"] = args.context
        state["stages"][args.stage] = record
        append_event(
            state, "stage", stage=args.stage, status=args.status,
            message=args.message, next_action=args.next_action,
        )
        commit(state_path, state)
    emit(json.dumps({"status": "marked", "stage": args.stage, "stage_status": args.status}, ensure_ascii=False))
    return 0


def unique_append(items: list[Any], value: Any, key: str | None = None) -> None:
    if key is None:
        if value not in items:
            items.append(value)
        return
    if not any(item.get(key) == value.get(key) and item.get("message") == value.get("message") for item in items):
        items.append(value)


def _progress_payload(args: argparse.Namespace) -> dict[str, Any]:
    payload: dict[str, Any] = {"message": args.message}
    if args.next_action:
        payload["next_action"] = args.next_action
    for key in ("stage", "evidence", "case_id", "candidate", "classification"):
        value = getattr(args, key, None)
        if value:
            payload[key] = value
    if not args.detail:
        return payload
    details: dict[str, str] = {}
    for item in args.detail:
        if "=" not in item:
            raise ValueError("--detail must use key=value")
        key, value = item.split("=", 1)
        if not key:
            raise ValueError("--detail key cannot be empty")
        details[key] = value
    payload["details"] = details
    return payload


def _apply_hypotheses(args: argparse.Namespace, precision: dict) -> None:
    if args.hypothesis:
        precision["current_hypothesis"] = args.hypothesis
    if not args.excluded_hypothesis:
        return
    excluded = precision.setdefault("excluded_hypotheses", [])
    for hypothesis in args.excluded_hypothesis:
        unique_append(excluded, hypothesis)


def _record_classification(args: argparse.Namespace, precision: dict) -> None:
    if not args.classification:
        return
    if not args.case_id:
        raise ValueError("precision classification requires --case-id")
    item = {
        "case_id": args.case_id,
        "candidate": args.candidate,
        "message": args.message,
        "evidence": args.evidence,
        "at": utc_now(),
    }
    if args.classification == "known_baseline_failure":
        target = "known_baseline_failures"
    elif args.classification == "new_or_worsened_failure":
        target = "new_or_worsened_failures"
    else:
        target = "diagnosis_results"
    unique_append(precision.setdefault(target, []), item, "case_id")


def command_progress(args: argparse.Namespace) -> int:
    state_path = args.state.resolve()
    with state_lock(state_path):
        state = read_json(state_path)
        precision = state.setdefault("precision", {})
        kind = "diagnosis" if args.kind == "diagnosis" else "progress"
        payload = _progress_payload(args)
        _apply_hypotheses(args, precision)
        if args.next_action:
            precision["next_action"] = args.next_action
            state["next_action"] = args.next_action
        _record_classification(args, precision)
        append_event(state, kind, **payload)
        commit(state_path, state)
    emit(json.dumps({"status": "recorded", "kind": kind}, ensure_ascii=False))
    return 0


def command_decision(args: argparse.Namespace) -> int:
    if args.awaiting and not args.question:
        raise ValueError("--awaiting requires --question")
    state_path = args.state.resolve()
    with state_lock(state_path):
        state = read_json(state_path)
        operator = state.setdefault("operator", {})
        if args.awaiting:
            operator.update({"awaiting": True, "question": args.question, "requested_at": utc_now()})
            message = args.question
        else:
            operator.update({"awaiting": False, "last_decision": args.decision, "resolved_at": utc_now()})
            operator.pop("question", None)
            if state.get("terminal", {}).get("status") == "awaiting_operator":
                state.pop("terminal")
            message = args.decision
        if args.safe_restore_point:
            operator["safe_restore_point"] = args.safe_restore_point
            state["safe_restore_point"] = args.safe_restore_point
        append_event(state, "decision", message=message, awaiting=args.awaiting)
        commit(state_path, state)
    emit(json.dumps({"status": "awaiting" if args.awaiting else "resolved"}, ensure_ascii=False))
    return 0


def command_structural_direction(args: argparse.Namespace) -> int:
    """Upsert a structural-direction ledger entry (pursue_optimal cross-round obligation)."""
    state_path = args.state.resolve()
    with state_lock(state_path):
        state = read_json(state_path)
        ledger = state.setdefault("structural_directions", [])
        entry = next((d for d in ledger if d.get("id") == args.id), None)
        if entry is None:
            entry = {"id": args.id, "created_at": utc_now()}
            ledger.append(entry)
        entry["status"] = args.status
        entry["updated_at"] = utc_now()
        if args.description:
            entry["description"] = args.description
        if args.round is not None:
            entry["round"] = args.round
        if args.evidence:
            entry["evidence"] = args.evidence
        if args.estimated_gain:
            entry["estimated_gain"] = args.estimated_gain
        append_event(
            state,
            "structural_direction",
            message=f"{args.id} -> {args.status}",
            direction_id=args.id,
            status=args.status,
        )
        commit(state_path, state)
    emit(json.dumps({"status": "recorded", "direction": args.id, "direction_status": args.status}, ensure_ascii=False))
    return 0


def command_migrate(args: argparse.Namespace) -> int:
    state_path = args.state.resolve()
    audit = artifact_identity(args.audit)
    with state_lock(state_path):
        state = read_json(state_path)
        adopted = False
        if getattr(args, "adopt_schedule_policy", False):
            from validate_schedule_contract import policy_enabled, require
            require("schedule_policy" not in state, "schedule policy adoption requires an absent state field")
            require(audit["kind"] == "file" and Path(audit["path"]).stat().st_size > 0,
                    "schedule policy adoption requires a nonempty audit file")
            manifest_path = Path(state["manifest"]["path"])
            require(artifact_identity(manifest_path) == state["manifest"],
                    "cannot adopt policy after manifest identity changed")
            manifest = read_manifest(manifest_path)
            require(manifest.get("request", {}).get("path") and policy_enabled(manifest),
                    "policy adoption requires a matching frozen request and manifest policy")
            occurred = set(state.get("stages", {}))
            occurred.update(event.get("stage") for event in state.get("events", []) if event.get("stage"))
            if state.get("current_stage"):
                occurred.add(state["current_stage"])
            require(not any(schedule_stage_kind(name) or ".acceptance." in name or ".selection" in name
                            for name in occurred),
                    "cannot adopt schedule policy after analysis/implementation/integration activity")
            state["schedule_policy"] = manifest["configuration"]["schedule_policy"]
            adopted = True
            append_event(state, "schedule_policy_adopted", audit=audit, manifest=state["manifest"],
                         policy=state["schedule_policy"],
                         reason="explicit pre-analysis migration of an already frozen policy")
        for stage in args.invalidate_stage or []:
            record = state.setdefault("stages", {}).setdefault(stage, {})
            record.update({"status": "invalid", "invalidated_at": utc_now(), "reason": "workflow_migration"})
        state["workflow_version"] = args.workflow_version
        append_event(state, "workflow_migration", audit=audit,
                     invalidated=args.invalidate_stage or [], schedule_policy_adopted=adopted)
        commit(state_path, state)
    emit(json.dumps({"status": "workflow_migrated", "invalidated": args.invalidate_stage or []}, ensure_ascii=False))
    return 0


def _verify_artifact(stage: str, artifact: dict, invalid: list[dict[str, str]]) -> str | None:
    try:
        current = artifact_identity(artifact["path"])
    except FileNotFoundError:
        invalid.append({"kind": "artifact", "stage": stage, "path": artifact["path"]})
        return "artifact_missing"
    if current["sha256"] != artifact["sha256"]:
        invalid.append({"kind": "artifact", "stage": stage, "path": artifact["path"]})
        return "artifact_changed"
    return None


def _verify_stage_artifacts(name: str, record: dict, invalid: list[dict[str, str]]) -> None:
    for artifact in record.get("artifacts", []):
        reason = _verify_artifact(name, artifact, invalid)
        if reason:
            record.update({"status": "invalid", "reason": reason, "invalidated_at": utc_now()})


def _verify_stage_evidence(state: dict, name: str, record: dict, invalid: list[dict[str, str]]) -> None:
    try:
        kind = schedule_stage_kind(name)
        if kind:
            paths = [a["path"] for a in record.get("artifacts", [])]
            check_schedule_artifacts(kind, paths, Path(state["manifest"]["path"]))
            if kind == "runtime" and "schedule_policy" in state:
                check_runtime_handoff(name, paths, state)
        if record.get("performance"):
            recorded_performance(record)
        if name == "phase.integration" and (
                "schedule_policy" in state
                or policy(state.get("performance_effect_policy"))["id"] == "confidence_effect_v1"):
            check_phase_artifacts("integration", [a["path"] for a in record.get("artifacts", [])],
                                  Path(state["manifest"]["path"]))
    except (ValueError, KeyError, TypeError, OSError) as error:
        invalid.append({"kind": "effect_evidence", "stage": name, "reason": str(error)})
        record.update({"status": "invalid", "reason": "effect_evidence_changed", "invalidated_at": utc_now()})


def _verify_stage_records(state: dict, invalid: list[dict[str, str]]) -> None:
    for name, record in state.get("stages", {}).items():
        if record.get("status") != "complete":
            continue
        _verify_stage_artifacts(name, record, invalid)
        _verify_stage_evidence(state, name, record, invalid)


def command_verify(args: argparse.Namespace) -> int:
    state_path = args.state.resolve()
    invalid: list[dict[str, str]] = []
    with state_lock(state_path):
        state = read_json(state_path)
        validate_frozen_effect_policy(state, read_manifest(Path(state["manifest"]["path"])))
        current_manifest = artifact_identity(state["manifest"]["path"])
        if current_manifest["sha256"] != state["manifest"]["sha256"]:
            invalid.append({"kind": "manifest", "path": current_manifest["path"]})
        _verify_stage_records(state, invalid)
        if invalid:
            append_event(state, "verification", message="state verification failed", invalid=invalid)
        commit(state_path, state)
    emit(json.dumps({"status": "invalid" if invalid else "valid", "invalid": invalid}, ensure_ascii=False))
    return 2 if invalid else 0


def command_inspect(args: argparse.Namespace) -> int:
    """Read a bounded stage view; no state writes or completion inference."""
    if args.recent < 0:
        raise ValueError("--recent must be non-negative")
    state = read_json(args.state.resolve())
    manifest_id = state["manifest"]
    if file_sha(Path(manifest_id["path"])) != manifest_id["sha256"]:
        raise ValueError("stale_inputs: run_manifest_changed")
    manifest = read_manifest(Path(manifest_id["path"]))
    stages = state.get("stages", {})
    selected = args.stage or ([state["current_stage"]] if state.get("current_stage") else [])
    events = [event for event in state.get("events", []) if event.get("stage") in selected]
    emit(json.dumps({
        "manifest": manifest_id,
        "configuration": manifest["configuration"],
        "inputs": manifest["inputs"],
        "collections": {
            name: {key: value[key] for key in ("path", "sha256", "count") if key in value}
            for name, value in manifest["collections"].items() if isinstance(value, dict)
        },
        "current_stage": state.get("current_stage"),
        "stage_statuses": {name: record.get("status") for name, record in stages.items()},
        "stages": {name: stages.get(name) for name in selected},
        "recent_events": events[-args.recent:] if args.recent else [],
        "operator": state.get("operator"),
        "safe_restore_point": state.get("safe_restore_point"),
        "verification": "manifest_sha_only; use verify for saved artifacts and stage gates for evidence ownership",
    }, ensure_ascii=False))
    return 0


def command_render(args: argparse.Namespace) -> int:
    state_path = args.state.resolve()
    with state_lock(state_path):
        state = read_json(state_path)
        atomic_text(args.output.resolve() if args.output else state_path.parent / "性能调优报告.md", report_text(state))
    emit(json.dumps({"status": "rendered"}, ensure_ascii=False))
    return 0


def _check_structural_directions(state: dict, args: argparse.Namespace) -> None:
    if not (
        state.get("optimization_intent") == "pursue_optimal"
        and args.status == "success"
        and args.reason_code == "completed"
    ):
        return
    unresolved = [
        d for d in state.get("structural_directions", [])
        if d.get("status") in UNRESOLVED_STRUCTURAL_STATUSES
    ]
    if not unresolved:
        return
    ids = ", ".join(f"{d.get('id')}[{d.get('status')}]" for d in unresolved)
    raise ValueError(
        "pursue_optimal: cannot finish success/completed with unrealized structural directions: "
        f"{ids}. Re-freeze a wider scope and re-attempt each blocked_by_scope/not_attempted "
        "direction, or record it as realized / infeasible_evidenced / blocked_by_precision. "
        "If parking for a human decision, finish with "
        "--status awaiting_operator --reason-code structural_headroom_unrealized."
    )


def _check_phase_completion(state: dict, args: argparse.Namespace) -> None:
    if args.status != "success":
        return
    manifest_path = Path(state["manifest"]["path"])
    manifest = read_manifest(manifest_path)
    validate_frozen_effect_policy(state, manifest)
    if manifest["configuration"].get("workflow_layout") != "five-stage-v1":
        return
    if artifact_identity(manifest_path) != state["manifest"]:
        raise ValueError("run manifest changed; verify before finishing")
    for stage, saved in state.get("stages", {}).items():
        kind = schedule_stage_kind(stage)
        if kind and saved.get("status") == "complete":
            check_schedule_artifacts(kind, [a["path"] for a in saved.get("artifacts", [])], manifest_path)
            if kind == "runtime" and "schedule_policy" in state:
                check_runtime_handoff(stage, [a["path"] for a in saved.get("artifacts", [])], state)
    for phase in PHASES:
        record = state.get("stages", {}).get(f"phase.{phase}", {})
        if record.get("status") != "complete":
            raise ValueError(f"required phase is incomplete: {phase}")
        for artifact in record.get("artifacts", []):
            if artifact_identity(artifact["path"]) != artifact:
                raise ValueError(f"phase artifact changed: {artifact['path']}")


def command_finish(args: argparse.Namespace) -> int:
    if args.status in ("failed", "blocked") and args.reason_code in (
        "known_baseline_failure",
        "candidate_precision_regression",
    ):
        raise ValueError(
            "a known baseline failure or one candidate regression cannot terminate the workflow; "
            "record conditional_pass or eliminate that candidate"
        )
    state_path = args.state.resolve()
    with state_lock(state_path):
        state = read_json(state_path)
        _check_structural_directions(state, args)
        _check_phase_completion(state, args)
        state["terminal"] = {
            "status": args.status,
            "reason_code": args.reason_code,
            "message": args.message,
            "at": utc_now(),
        }
        if args.status == "awaiting_operator":
            state.setdefault("operator", {})["awaiting"] = True
        append_event(state, "finish", message=args.message, status=args.status)
        commit(state_path, state)
    emit(json.dumps({"status": args.status, "report": str(state_path.parent / '性能调优报告.md')}, ensure_ascii=False))
    return 0


def _command(subparsers: argparse._SubParsersAction, name: str, help_text: str, func) -> argparse.ArgumentParser:
    command = subparsers.add_parser(name, help=help_text)
    command.add_argument("--state", type=Path, required=True)
    command.set_defaults(func=func)
    return command


def _add_mark_args(mark: argparse.ArgumentParser) -> None:
    mark.add_argument("--stage", required=True)
    mark.add_argument("--status", choices=STAGE_STATUSES, required=True)
    mark.add_argument("--reason")
    mark.add_argument("--message")
    mark.add_argument("--next-action", help="next action at this lifecycle checkpoint")
    mark.add_argument("--artifact", action="append")
    mark.add_argument("--context", action="append")
    mark.add_argument("--performance-summary", type=Path,
                      help="selected implementation vs round baseline effect-summary.json")
    mark.add_argument("--cumulative-performance-summary", type=Path,
                      help="same selected performance vs original baseline effect-summary.json")
    mark.add_argument("--selected-candidate", help="retained implementation identity, including baseline when retained")
    mark.add_argument("--performance-scope", choices=("tuning_subset", "full"), default="tuning_subset")


def _add_progress_args(progress: argparse.ArgumentParser) -> None:
    progress.add_argument("--kind", choices=("progress", "diagnosis"), default="progress")
    progress.add_argument("--message", required=True)
    progress.add_argument("--stage")
    progress.add_argument("--evidence")
    progress.add_argument("--hypothesis")
    progress.add_argument("--excluded-hypothesis", action="append")
    progress.add_argument("--next-action")
    progress.add_argument("--case-id")
    progress.add_argument("--candidate")
    progress.add_argument("--classification", choices=PRECISION_CLASSIFICATIONS)
    progress.add_argument("--detail", action="append", help="structured report field as key=value")


def _add_structural_args(sdir: argparse.ArgumentParser) -> None:
    sdir.add_argument("--id", required=True, help="stable direction id (e.g. whole-op-fusion)")
    sdir.add_argument("--status", choices=STRUCTURAL_DIRECTION_STATUSES, required=True)
    sdir.add_argument("--description")
    sdir.add_argument("--round", type=int)
    sdir.add_argument("--evidence")
    sdir.add_argument("--estimated-gain")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    sub = result.add_subparsers(dest="command", required=True)
    start = _command(sub, "start", "start or resume a run", command_start)
    start.add_argument("--manifest", type=Path, required=True)
    start.add_argument("--workflow-version")
    sync = _command(sub, "sync-manifest", "accept an intentional manifest update", command_sync_manifest)
    sync.add_argument("--message")
    _add_mark_args(_command(sub, "mark", "change a stage lifecycle state", command_mark))
    _add_progress_args(_command(sub, "progress", "record meaningful work or a diagnosis checkpoint", command_progress))
    decision = _command(sub, "decision", "record an operator wait or decision", command_decision)
    group = decision.add_mutually_exclusive_group(required=True)
    group.add_argument("--awaiting", action="store_true")
    group.add_argument("--decision")
    decision.add_argument("--question")
    decision.add_argument("--safe-restore-point")
    _add_structural_args(_command(
        sub, "structural-direction",
        "upsert a structural-direction ledger entry (pursue_optimal cross-round obligation)",
        command_structural_direction,
    ))
    migrate = _command(sub, "migrate-workflow", "record workflow impact audit", command_migrate)
    migrate.add_argument("--audit", type=Path, required=True)
    migrate.add_argument("--workflow-version", required=True)
    migrate.add_argument("--invalidate-stage", action="append")
    migrate.add_argument("--adopt-schedule-policy", action="store_true",
                         help="explicitly adopt an already frozen policy into a pre-analysis legacy state")
    _command(sub, "verify", "verify manifest and completed artifacts", command_verify)
    inspect = _command(sub, "inspect",
                       "read manifest identity and selected stage context without full history", command_inspect)
    inspect.add_argument("--stage", action="append", help="exact stage key; repeat for prerequisite stages")
    inspect.add_argument("--recent", type=int, default=3)
    render = _command(sub, "render", "render the live report from current state", command_render)
    render.add_argument("--output", type=Path)
    finish = _command(sub, "finish", "record terminal status and finalize the live report", command_finish)
    finish.add_argument("--status", choices=TERMINAL_STATUSES, required=True)
    finish.add_argument("--reason-code", choices=TERMINAL_REASON_CODES, required=True)
    finish.add_argument("--message", required=True)
    return result


def main() -> int:
    return run_cli(parser)


if __name__ == "__main__":
    raise SystemExit(main())
