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
"""Transition to Next Round Script

Atomically executes Step 4 (prepare next round) and Phase 0 (directory creation)
of the Agent Loop, ensuring reliable round-to-round transitions.

All rounds are created as normal directories named opt-round-{N+1}. Direction
switch metadata is recorded in round_index.json and opt-note.md, but no special
"-switch" directory is created.

Usage:
    python3 transition_next_round.py \
        --op-dir triton_ascend_output/{op_name} \
        --current-round {N} \
        --next-round-strategy {exploration|structural_change|focused_tuning|stabilization|plateau_review} \
        --next-analysis-policy {pattern_entry|bottleneck_analysis|ir_supported} \
        --next-hypothesis "..." \
        --next-direction "..." \
        --next-evidence-sources '[...]' \
        [--baseline-dir opt-round-K] \
        [--baseline-dirs '["opt-round-K", "opt-round-L"]'] \
        [--switch-marker '{"reason": "...", "previous_direction": "...", "new_direction": "..."}']

Output (JSON):
    {
        "status": "success" | "fail",
        "next_round": <int>,
        "next_round_dir": "opt-round-<N>",
        "baseline_speedup": <float>,
        "issues": [...],
        "warnings": [...]
    }
"""

import argparse
import json
import shutil
import string
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config_loader import read_config, get_algorithm_params, get_enabled_algorithms
from direction_selector import (
    DirectionYieldContext,
    build_direction_history,
)
from strategies import discover_strategies, load_strategy_for_algorithm
from strategies.base import SwitchMarker
from workspace_utils import find_op_name


def _format_state_template(template: str, op_name: str) -> str | None:
    """Safely format a state file template.

    Only the ``{op_name}`` placeholder is allowed. Returns ``None`` for
    malformed templates instead of raising.
    """
    try:
        parsed = list(string.Formatter().parse(template))
    except ValueError:
        return None
    fields = {field_name for _, field_name, _, _ in parsed if field_name is not None}
    if fields - {"op_name"}:
        return None
    try:
        return template.format(op_name=op_name)
    except (KeyError, IndexError):
        return None


def _copy_algorithm_state_files(
    source_dir: Path,
    target_dir: Path,
    op_name: str,
    strategy: Any,
) -> list[str]:
    """Copy algorithm-specific state files from source round to next round.

    State file templates are declared by the Strategy class via
    ``state_file_templates``. Each template may contain the ``{op_name}``
    placeholder.

    Returns a list of copied relative paths.
    """
    copied: list[str] = []
    templates = getattr(strategy, "state_file_templates", [])
    for template in templates:
        rel_path = _format_state_template(template, op_name)
        if rel_path is None:
            continue
        src = source_dir / rel_path
        if not src.is_file():
            continue
        dst = target_dir / rel_path
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied.append(rel_path)
    return copied


def _generate_bottleneck_card(
    source_round_dir: Path,
    next_round_dir: Path,
    result: dict[str, Any],
) -> None:
    """B1-脚本（gene-fusion 专用）：蒸馏刚完成轮次最优 route 的瓶颈卡片到下一轮目录。

    卡片是增强产物：蒸馏/写入的任何失败只记 warning，不阻塞 transition。
    """
    try:
        from bottleneck_card import build_card

        card = build_card(source_round_dir)
        out_path = next_round_dir / "bottleneck_card.json"
        out_path.write_text(
            json.dumps(card, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        result["warnings"].append(
            "bottleneck_card distilled from "
            f"{source_round_dir.name} (best_route={card.get('best_route')}, "
            f"bottlenecks={len(card.get('proven_bottlenecks') or [])})"
        )
    except Exception as exc:  # noqa: BLE001
        result["warnings"].append(f"bottleneck_card generation skipped: {exc}")


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc


def _find_state_dir(op_dir: Path) -> Path | None:
    """查找 .triton-agent/ 目录（从 op_dir 向上搜索）。"""
    for p in [op_dir] + list(op_dir.parents):
        candidate = p / ".triton-agent"
        if candidate.is_dir():
            return candidate
    return None


def _state_path_for_op_dir(op_dir: Path, state_dir_loc: Path | None, op_name: str | None = None) -> Path | None:
    """Return the state file path for the given operator workspace.

    New-format workspaces use ``state-{op_dir.name}.json`` so that different
    algorithms/runs are isolated.  If that file does not exist but a legacy
    ``state-{op_name}.json`` exists, fall back to the legacy path for backward
    compatibility.
    """
    if state_dir_loc is None:
        return None
    new_path = state_dir_loc / f"state-{op_dir.name}.json"
    if new_path.is_file():
        return new_path
    if op_name:
        legacy_path = state_dir_loc / f"state-{op_name}.json"
        if legacy_path.is_file():
            return legacy_path
    return new_path


def _load_round_index(op_dir: Path) -> list[dict[str, Any]]:
    round_index_path = op_dir / "round_index.json"
    if not round_index_path.is_file():
        return []
    try:
        data = load_json(round_index_path)
        if isinstance(data, list):
            return data
    except ValueError:
        pass
    return []


def _entry_for_round_index(round_index: list[dict[str, Any]], round_index_num: int) -> dict[str, Any] | None:
    for entry in round_index:
        if entry.get("round_index") == round_index_num:
            return entry
    return None


def _check_round_artifacts(current_dir: Path, issues: list[str]) -> None:
    """Check Phase 3/4 verification, code change, and attempts authenticity."""
    phase3_verify_paths = sorted(current_dir.glob("output/iter_*/verify/verify_result.json"))
    phase3_ok = False
    if phase3_verify_paths:
        try:
            vdata = load_json(phase3_verify_paths[-1])
            total = vdata.get("total_cases", 0)
            passed = vdata.get("passed_cases", 0)
            if isinstance(total, (int, float)) and isinstance(passed, (int, float)):
                phase3_ok = int(total) > 0 and int(passed) == int(total)
        except ValueError:
            pass
    if not phase3_ok:
        issues.append("Phase 3 verification not found on disk (output/iter_*/verify/verify_result.json)")

    opt_iter_dirs = sorted(current_dir.glob("output/opt_iter_*"))
    phase4_ok = len(opt_iter_dirs) > 0
    has_real_change = False
    generated_code = current_dir / "output" / "generated_code.py"
    if phase4_ok and generated_code.is_file():
        for od in opt_iter_dirs:
            opt_code = od / "optimized_code.py"
            if opt_code.is_file() and opt_code.read_bytes() != generated_code.read_bytes():
                has_real_change = True
                break
        if not has_real_change:
            issues.append(
                "None of the opt_iter_*/optimized_code.py files differ from "
                "output/generated_code.py. All optimization iterations produced "
                "byte-identical code — no actual optimization was performed."
            )

    attempts_path = current_dir / "output" / "attempts.md"
    if phase4_ok and not attempts_path.is_file():
        issues.append("phase4_entered but output/attempts.md not found")
    elif attempts_path.is_file():
        lines = attempts_path.read_text().splitlines()
        tried_count = sum(1 for line in lines if line.strip().startswith("- [") and ("已尝试" in line or "已命中" in line))
        if tried_count < 1 and phase4_ok:
            issues.append(
                "output/attempts.md has no '已尝试' or '已命中' records. "
                "At least 1 optimization point must be actually attempted."
            )


def _validate_current_round(current_dir: Path) -> tuple[list[str], dict[str, Any]]:
    """Validate current round and return (issues, current_summary)."""
    issues: list[str] = []
    current_summary: dict[str, Any] = {}

    if not current_dir.is_dir():
        issues.append(f"current round directory not found: {current_dir}")
        return issues, current_summary

    current_summary_path = current_dir / "summary.json"
    if current_summary_path.is_file():
        try:
            current_summary = load_json(current_summary_path)
        except ValueError:
            pass

    _check_round_artifacts(current_dir, issues)

    return issues, current_summary


@dataclass
class DirectionMetaInput:
    """Inputs for computing direction metadata of a completed round."""

    op_dir: Path
    source_round_dir: str
    current_summary: dict[str, Any]
    baseline_entry: dict[str, Any] | None
    strategy: Any
    switch_marker: SwitchMarker | None
    global_baseline_speedup: float


def _compute_direction_metadata(spec: DirectionMetaInput) -> dict[str, Any]:
    """Compute direction_yield, yield_reason, and absolute_gain."""
    current_summary = spec.current_summary
    best_speedup = current_summary.get("best_speedup", 0.0)
    if not isinstance(best_speedup, (int, float)):
        best_speedup = 0.0
    bs = spec.baseline_entry.get("best_speedup", 0.0) if spec.baseline_entry else None
    baseline_speedup = bs if isinstance(bs, (int, float)) else 0.0
    target_speedup = current_summary.get("target_speedup", 5.0)
    if not isinstance(target_speedup, (int, float)):
        target_speedup = 5.0
    perf_data = current_summary.get("perf_data") or {}
    total = perf_data.get("total_cases", 0)
    passed = perf_data.get("passed_cases", 0)
    verify_passed = (
        isinstance(total, (int, float)) and isinstance(passed, (int, float))
        and int(total) > 0 and int(passed) == int(total)
    )
    improvement_made = bool(current_summary.get("optimized", False))
    current_round_dir = spec.op_dir / spec.source_round_dir
    plateau_detected = spec.switch_marker is not None and spec.switch_marker.reason == "plateau_stagnation"

    yield_label, yield_reason, absolute_gain = spec.strategy.classify_direction_yield(
        DirectionYieldContext(
            best_speedup=best_speedup,
            baseline_speedup=baseline_speedup,
            target_speedup=target_speedup,
            verify_passed=verify_passed,
            improvement_made=improvement_made,
            plateau_detected=plateau_detected,
            timeout=current_summary.get("status") == "timeout",
            idle=current_summary.get("round_type") == "idle",
            context={"op_dir": str(spec.op_dir), "round_dir": str(current_round_dir)},
            global_baseline_speedup=spec.global_baseline_speedup,
        )
    )

    return {
        "direction_yield": yield_label,
        "yield_reason": yield_reason,
        "absolute_gain_vs_baseline": round(absolute_gain, 6),
        "absolute_gain_vs_global_baseline": round(
            best_speedup - spec.global_baseline_speedup if spec.global_baseline_speedup > 0 else 0.0, 6
        ),
    }


def _select_baseline_path(
    op_dir: Path,
    op_name: str,
    baseline_dir_name: str | None,
    baseline_dir_names: list[str],
) -> tuple[Path | None, dict[str, Any] | None, float]:
    """Select the baseline code path and matching round_index entry."""
    round_index = _load_round_index(op_dir)

    # Prefer explicit single baseline.
    if baseline_dir_name:
        candidate = op_dir / baseline_dir_name / f"{op_name}_generated.py"
        if candidate.is_file():
            entry = _entry_for_baseline(round_index, baseline_dir_name)
            speedup = float(entry.get("best_speedup", 0.0)) if entry else 0.0
            return candidate, entry, speedup
        return None, None, 0.0

    # If multiple baselines are given, pick the first valid one.
    for name in baseline_dir_names:
        if not name:
            continue
        candidate = op_dir / name / f"{op_name}_generated.py"
        if candidate.is_file():
            entry = _entry_for_baseline(round_index, name)
            speedup = float(entry.get("best_speedup", 0.0)) if entry else 0.0
            return candidate, entry, speedup

    return None, None, 0.0


def _entry_for_baseline(round_index: list[dict[str, Any]], round_dir: str) -> dict[str, Any] | None:
    for entry in round_index:
        if entry.get("round_dir") == round_dir:
            return entry
    return None


@dataclass
class TransitionRequest:
    """Inputs for executing a round transition."""

    op_dir: Path | str
    current_round: int
    next_round_strategy: str
    next_analysis_policy: str
    next_hypothesis: str
    next_direction: str
    next_evidence_sources: list[str]
    current_success_criteria: str = ""
    current_key_learnings: str = ""
    baseline_dir: str | None = None
    baseline_dirs: list[str] | None = None
    combination_rule: str | None = None
    switch_marker: SwitchMarker | None = None
    strategy_name: str = "naive"
    strategy_params: dict[str, Any] | None = None
    global_baseline_dir: str | None = None
    global_baseline_speedup: float = 1.0
    algorithm: str = "naive"
    algorithm_metadata: dict[str, Any] | None = None


def _baseline_speedup_from_info(baseline_info_path: Path) -> float | None:
    """baseline_info.json 中的正数 baseline_speedup（缺失/损坏/非法返回 None）。"""
    if not baseline_info_path.is_file():
        return None
    try:
        baseline_info = load_json(baseline_info_path)
    except ValueError:
        return None
    gbs = baseline_info.get("baseline_speedup", 0.0)
    if isinstance(gbs, (int, float)) and gbs > 0:
        return float(gbs)
    return None


def _resolve_global_baseline(
    op_dir: Path, global_baseline_dir: str | None, global_baseline_speedup: float,
) -> tuple[float, str | None]:
    """Resolve the global baseline speedup from baseline_info.json if not provided."""
    if global_baseline_dir:
        gbs = _baseline_speedup_from_info(op_dir / global_baseline_dir / "baseline_info.json")
        if gbs is not None:
            return gbs, global_baseline_dir
        return global_baseline_speedup, global_baseline_dir
    gbs = _baseline_speedup_from_info(op_dir / "global_baseline" / "baseline_info.json")
    if gbs is not None:
        return gbs, "global_baseline"
    return global_baseline_speedup, global_baseline_dir


@dataclass
class BaselineSelectionSpec:
    """Inputs for selecting and copying the baseline into the next round."""

    op_dir: Path
    next_round_dir: Path
    op_name: str | None
    baseline_dir: str | None
    baseline_dirs: list[str] | None
    strategy: Any
    algorithm: str
    result: dict[str, Any]


def _select_and_copy_baseline(
    spec: BaselineSelectionSpec,
) -> tuple[Path | None, dict[str, Any] | None, float]:
    """Select the baseline round and copy its generated code into the next round."""
    baseline_path: Path | None = None
    baseline_speedup = 0.0
    baseline_entry: dict[str, Any] | None = None

    if spec.baseline_dir or spec.baseline_dirs:
        baseline_path, baseline_entry, baseline_speedup = _select_baseline_path(
            spec.op_dir, spec.op_name or "", spec.baseline_dir, spec.baseline_dirs or []
        )
        if baseline_path is None:
            spec.result["warnings"].append(
                "specified baseline not found; next round starts without baseline code"
            )
        else:
            spec.result["warnings"].append(
                f"baseline copied from {baseline_entry.get('round_dir') if baseline_entry else 'unknown'} "
                f"(speedup={baseline_speedup:.4f})"
            )
    else:
        spec.result["warnings"].append("no baseline specified, next round starts without baseline code")

    _copy_baseline_code(spec, baseline_path, baseline_entry)
    # 基础设施补位(R8/R9/R10 实测缺陷): transition 未随轮携带 golden 任务文件与
    # 冻结锚, 迫使 worker 每轮手工 cp 任务文件 + freeze_baseline.py 落锚。
    # golden 取自 baseline 轮(其 sha 已被锚固化); 锚随轮复制并改写 torch_path。
    _carry_golden_task(spec, baseline_entry)

    return baseline_path, baseline_entry, baseline_speedup


def _copy_baseline_code(
    spec: BaselineSelectionSpec,
    baseline_path: Path | None,
    baseline_entry: dict[str, Any] | None,
) -> None:
    """Copy the baseline round's generated code (and algorithm state) into the next round."""
    if baseline_path and baseline_path.is_file() and spec.op_name:
        target_path = spec.next_round_dir / f"{spec.op_name}_generated.py"
        shutil.copy2(baseline_path, target_path)
        if baseline_entry and baseline_entry.get("round_dir"):
            source_round_dir_path = spec.op_dir / baseline_entry["round_dir"]
            copied_state = _copy_algorithm_state_files(
                source_round_dir_path, spec.next_round_dir, spec.op_name, spec.strategy
            )
            if copied_state:
                spec.result["warnings"].append(
                    f"copied algorithm state files for {spec.algorithm}: {copied_state}"
                )
    elif spec.op_name:
        target_path = spec.next_round_dir / f"{spec.op_name}_generated.py"
        if not target_path.is_file():
            target_path.write_text("# placeholder\n", encoding="utf-8")


def _carry_baseline_anchor(spec: BaselineSelectionSpec, golden_src: Path, golden_dst: Path) -> None:
    """随轮复制冻结锚并改写 torch_path（失败仅告警，不阻断 transition）。"""
    anchor_src = golden_src.parent / "output" / ".baseline_anchor.json"
    if not anchor_src.is_file():
        return
    try:
        anchor = json.loads(anchor_src.read_text(encoding="utf-8"))
        anchor["torch_path"] = str(golden_dst)
        anchor_dst_dir = spec.next_round_dir / "output"
        anchor_dst_dir.mkdir(parents=True, exist_ok=True)
        (anchor_dst_dir / ".baseline_anchor.json").write_text(
            json.dumps(anchor, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        spec.result["warnings"].append(
            "baseline anchor copied with torch_path rewritten to next round"
        )
    except (OSError, json.JSONDecodeError) as exc:
        spec.result["warnings"].append(
            f"baseline anchor copy failed (non-fatal): {exc}"
        )


def _carry_golden_task(spec: BaselineSelectionSpec, baseline_entry: dict[str, Any] | None) -> None:
    """随轮携带 golden 任务文件与冻结锚到下一轮。"""
    if not spec.op_name:
        return
    golden_dst = spec.next_round_dir / f"{spec.op_name}.py"
    golden_src: Path | None = None
    if baseline_entry and baseline_entry.get("round_dir"):
        candidate = spec.op_dir / baseline_entry["round_dir"] / f"{spec.op_name}.py"
        if candidate.is_file():
            golden_src = candidate
    if golden_src is None:
        spec.result["warnings"].append(
            f"golden task file {spec.op_name}.py not found in baseline round; "
            "next round may fail _baseline_integrity gate until manually restored"
        )
        return
    shutil.copy2(golden_src, golden_dst)
    _carry_baseline_anchor(spec, golden_src, golden_dst)


@dataclass
class NextSummarySpec:
    """Inputs for writing the next round's summary.json."""

    next_round_dir: Path
    next_round_index: int
    algorithm: str
    baseline_entry: dict[str, Any] | None
    global_baseline_dir: str | None
    global_baseline_speedup: float
    next_round_strategy: str
    next_analysis_policy: str
    next_hypothesis: str
    next_direction: str
    next_evidence_sources: list[str]
    current_summary: dict[str, Any]
    algorithm_metadata: dict[str, Any] | None


def _write_next_summary(spec: NextSummarySpec) -> None:
    """Write the next round's summary.json."""
    next_summary = {
        "round_index": spec.next_round_index,
        "algorithm": spec.algorithm,
        "baseline_dir": spec.baseline_entry.get("round_dir") if spec.baseline_entry else None,
        "global_baseline_dir": spec.global_baseline_dir,
        "global_baseline_speedup": spec.global_baseline_speedup,
        "round_strategy": spec.next_round_strategy,
        "analysis_policy": spec.next_analysis_policy,
        "hypothesis": spec.next_hypothesis,
        "direction": spec.next_direction,
        "evidence_sources": spec.next_evidence_sources,
        "status": "active",
        "best_speedup": 0.0,
        "success": False,
        "gen_iterations": 0,
        "opt_iterations": 0,
        "optimized": False,
        "target_reached": False,
        "target_speedup": spec.current_summary.get("target_speedup", 5.0),
        "direction_yield": None,
        "yield_reason": None,
        "absolute_gain_vs_baseline": None,
        "absolute_gain_vs_global_baseline": None,
    }

    if spec.algorithm_metadata:
        for key in ("mcts_parent_id", "mcts_selection_path", "mcts_pending_expansion"):
            if key in spec.algorithm_metadata:
                next_summary[key] = spec.algorithm_metadata[key]

    (spec.next_round_dir / "summary.json").write_text(
        json.dumps(next_summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


@dataclass
class StateUpdateSpec:
    """Inputs for updating the state file to point at the next round."""

    op_dir: Path
    current_round: int
    next_round_index: int
    next_round_dir_name: str
    next_round_dir: Path
    algorithm: str
    existing_rounds: list[dict[str, Any]]
    result: dict[str, Any]


def _update_state_file(spec: StateUpdateSpec) -> None:
    """Update the state file to point at the next round."""
    state_dir_loc = _find_state_dir(spec.op_dir)
    if state_dir_loc is None:
        spec.result["warnings"].append(".triton-agent/ not found, state file will not be updated")
    op_name = find_op_name(spec.op_dir) or (spec.op_dir.name if spec.op_dir.name else None)
    state_path = _state_path_for_op_dir(spec.op_dir, state_dir_loc, op_name)
    if state_path and state_path.is_file():
        try:
            state = load_json(state_path)
            if str(spec.current_round) in state.get("rounds", {}):
                state["rounds"][str(spec.current_round)]["status"] = "completed"
            rounds = state.setdefault("rounds", {})
            rounds[str(spec.next_round_index)] = {
                "status": "active",
                "round_dir": spec.next_round_dir_name,
            }
            state["current_round"] = spec.next_round_index
            state["algorithm"] = spec.algorithm
            state["algorithm_reference"] = f".claude/references/algorithms/{spec.algorithm}/round.md"
            state["status"] = "active"
            state["phase"] = "round_active"
            state["work_dir"] = str(spec.next_round_dir)
            state["last_phase"] = 0
            state["direction_history"] = build_direction_history(spec.existing_rounds)
            state_path.write_text(
                json.dumps(state, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except ValueError as exc:
            spec.result["warnings"].append(f"state file update failed: {exc}")


@dataclass
class OptNoteSpec:
    """Inputs for appending the completed round's entry to opt-note.md."""

    op_dir: Path
    current_round: int
    current_summary: dict[str, Any]
    current_success_criteria: str
    current_key_learnings: str
    direction_metadata: dict[str, Any]
    switch_marker: SwitchMarker | None


def _append_opt_note(spec: OptNoteSpec) -> None:
    """Append the completed round's entry to opt-note.md."""
    cs = spec.current_summary
    opt_entry = (
        f"\n## Round {spec.current_round}\n\n"
        f"- round_strategy: {cs.get('round_strategy', 'N/A')}\n"
        f"- hypothesis: {cs.get('hypothesis', 'N/A')}\n"
        f"- direction: {cs.get('direction', 'N/A')}\n"
        f"- success_criteria: {spec.current_success_criteria}\n"
        f"- evidence_sources: {json.dumps(cs.get('evidence_sources', []), ensure_ascii=False)}\n"
        f"- result: {'success' if cs.get('success', False) else 'failed'}\n"
        f"- best_speedup: {cs.get('best_speedup', 0)}\n"
        f"- direction_yield: {spec.direction_metadata.get('direction_yield')}\n"
        f"- yield_reason: {spec.direction_metadata.get('yield_reason')}\n"
        f"- absolute_gain_vs_baseline: {spec.direction_metadata.get('absolute_gain_vs_baseline')}\n"
        f"- absolute_gain_vs_global_baseline: {spec.direction_metadata.get('absolute_gain_vs_global_baseline')}\n"
    )
    if spec.switch_marker is not None:
        opt_entry += (
            f"- switch_reason: {spec.switch_marker.reason}\n"
            f"- previous_direction: {spec.switch_marker.previous_direction}\n"
            f"- new_direction: {spec.switch_marker.new_direction}\n"
        )
    opt_entry += f"- key_learnings: {spec.current_key_learnings}\n"

    with open(spec.op_dir / "opt-note.md", "a", encoding="utf-8") as f:
        f.write(opt_entry)


@dataclass
class RoundIndexUpdateSpec:
    """Inputs for finalizing the current entry and appending the next entry."""

    op_dir: Path
    existing_rounds: list[dict[str, Any]]
    current_round: int
    source_round_dir: str
    current_summary: dict[str, Any]
    direction_metadata: dict[str, Any]
    global_baseline_dir: str | None
    global_baseline_speedup: float
    next_round_index: int
    next_round_dir_name: str
    algorithm: str
    next_direction: str
    next_hypothesis: str
    next_evidence_sources: list[str]
    next_analysis_policy: str
    next_round_strategy: str
    baseline_entry: dict[str, Any] | None
    switch_marker: SwitchMarker | None


def _finalize_current_entry(spec: RoundIndexUpdateSpec) -> None:
    """Finalize the current round entry and merge direction metadata."""
    current_entry = _entry_for_round_index(spec.existing_rounds, spec.current_round)
    if current_entry is None:
        current_entry = {
            "round_index": spec.current_round,
            "round_dir": spec.source_round_dir,
            "direction": spec.current_summary.get("direction", ""),
            "hypothesis": spec.current_summary.get("hypothesis", ""),
            "evidence_sources": spec.current_summary.get("evidence_sources", []),
            "analysis_policy": spec.current_summary.get("analysis_policy", "pattern_entry"),
            "effective_metric_source": spec.current_summary.get("effective_metric_source", "kernel"),
            "status": "success" if spec.current_summary.get("success", False) else "failed",
            "best_speedup": spec.current_summary.get("best_speedup", 0.0),
            "round_strategy": spec.current_summary.get("round_strategy", "exploration"),
            "consecutive_low_gain_count": spec.current_summary.get("consecutive_low_gain_count", 0),
            "round_type": spec.current_summary.get("round_type", "active"),
            "target_speedup": spec.current_summary.get("target_speedup", 5.0),
            "global_baseline_dir": spec.current_summary.get("global_baseline_dir") or spec.global_baseline_dir,
            "global_baseline_speedup": (
                spec.current_summary.get("global_baseline_speedup") or spec.global_baseline_speedup
            ),
        }
        spec.existing_rounds.append(current_entry)

    current_entry.update(spec.direction_metadata)
    current_entry["status"] = "success" if spec.current_summary.get("success", False) else "failed"
    if "baseline_dir" not in current_entry:
        current_entry["baseline_dir"] = spec.current_summary.get("baseline_dir")
    if "global_baseline_dir" not in current_entry or not current_entry["global_baseline_dir"]:
        current_entry["global_baseline_dir"] = spec.global_baseline_dir
    if "global_baseline_speedup" not in current_entry or not current_entry["global_baseline_speedup"]:
        current_entry["global_baseline_speedup"] = spec.global_baseline_speedup
    current_entry.pop("parent_round_dir", None)
    current_entry.pop("best_baseline_for_this_direction", None)


def _update_round_index(spec: RoundIndexUpdateSpec) -> None:
    """Finalize the current round entry and append the next round entry."""
    _finalize_current_entry(spec)

    next_entry: dict[str, Any] = {
        "round_index": spec.next_round_index,
        "round_dir": spec.next_round_dir_name,
        "algorithm": spec.algorithm,
        "direction": spec.next_direction,
        "hypothesis": spec.next_hypothesis,
        "evidence_sources": spec.next_evidence_sources,
        "analysis_policy": spec.next_analysis_policy,
        "effective_metric_source": "kernel",
        "status": "active",
        "best_speedup": 0.0,
        "round_strategy": spec.next_round_strategy,
        "consecutive_low_gain_count": 0,
        "round_type": "active",
        "target_speedup": spec.current_summary.get("target_speedup", 5.0),
        "direction_yield": None,
        "yield_reason": None,
        "absolute_gain_vs_baseline": None,
        "absolute_gain_vs_global_baseline": None,
        "baseline_dir": spec.baseline_entry.get("round_dir") if spec.baseline_entry else None,
        "global_baseline_dir": spec.global_baseline_dir,
        "global_baseline_speedup": spec.global_baseline_speedup,
    }
    if spec.switch_marker is not None:
        next_entry["switch_reason"] = spec.switch_marker.reason
        next_entry["previous_direction"] = spec.switch_marker.previous_direction
        next_entry["new_direction"] = spec.switch_marker.new_direction

    spec.existing_rounds.append(next_entry)

    (spec.op_dir / "round_index.json").write_text(
        json.dumps(spec.existing_rounds, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _write_transition_lock(
    op_dir: Path,
    current_round: int,
    next_round_index: int,
    next_round_dir_name: str,
    result: dict[str, Any],
) -> None:
    """Write the transition lock."""
    lock = {
        "action": "continue",
        "transition_at": datetime.now(timezone.utc).isoformat(),
        "from_round": current_round,
        "to_round": next_round_index,
        "to_round_dir": next_round_dir_name,
        "state_after": {
            "current_round": next_round_index,
            "last_phase": 0,
            "status": "active",
            "phase": "round_active",
        },
    }
    lock_path = op_dir / ".transition_lock.json"
    try:
        lock_path.write_text(
            json.dumps(lock, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        result["warnings"].append(f"failed to write transition lock: {exc}")


@dataclass
class PreludeState:
    """State resolved by the transition prelude."""

    op_dir: Path
    current_summary: dict[str, Any]
    existing_rounds: list[dict[str, Any]]
    next_round_index: int
    source_round_dir: str
    next_round_dir_name: str
    next_round_dir: Path


def _validate_gene_fusion_summary(round_dir: Path) -> list[str]:
    """gene-fusion 父轮门禁：查 round_result.json 结构完整性（替代 iter_* 检查）。

    路线级质检结论由 validate_round_result.py §7.0 在收集时逐 route 把关；此处
    只确认父轮确已产出可消费的汇总（gene_fusion 块 + 正的 route_count），不校验
    路线成败，也不依赖子 agent 间不固定的明细字段名（route_outcomes/verdicts/
    route_results/route_mix 混用，gf1021 实测）。
    """
    rr_path = round_dir / "round_result.json"
    if not rr_path.is_file():
        return [f"missing {rr_path.name}"]
    try:
        data = json.loads(rr_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"unreadable round_result.json: {exc}"]
    gene_fusion = data.get("gene_fusion")
    if not isinstance(gene_fusion, dict):
        return ["round_result.json missing gene_fusion block"]
    route_count = gene_fusion.get("route_count")
    if not isinstance(route_count, int) or isinstance(route_count, bool) or route_count <= 0:
        return ["gene_fusion.route_count missing or non-positive"]
    return []


def _prepare_transition(req: TransitionRequest, result: dict[str, Any]) -> PreludeState | dict[str, Any]:
    """Run the prelude: validate current round, compute next round, load round_index."""
    op_dir = req.op_dir
    if isinstance(op_dir, str):
        op_dir = Path(op_dir)

    global_baseline_speedup, global_baseline_dir = _resolve_global_baseline(
        op_dir, req.global_baseline_dir, req.global_baseline_speedup
    )
    result["global_baseline_speedup"] = global_baseline_speedup
    result["global_baseline_dir"] = global_baseline_dir

    issues, current_summary = _validate_current_round(op_dir / f"opt-round-{req.current_round}")
    if issues and req.algorithm == "gene-fusion":
        # gene-fusion 父 round 不执行 Phase 3/4：迭代与验证发生在 route 子 CLI
        # 内部（route-*/），由 validate_round_result.py 的 §7.0 质检把关。父轮
        # output/ 恒无 iter_* 产物，单 agent 形态的防伪门禁在此不适用——改查
        # 等价证据 round_result.json 的结构完整性（gene_fusion.route_count>0，
        # 13/13 轮稳定不变量）。全 route 判废的坏轮也必须放行（继续/停止归
        # C1/C2 策略层，gf1021 R1/R7/R11 实测）；结构缺失才是真 issue。
        summary_issues = _validate_gene_fusion_summary(op_dir / f"opt-round-{req.current_round}")
        if summary_issues:
            result["issues"] = [f"gene-fusion summary: {i}" for i in summary_issues]
            return result
        result["warnings"].extend(f"gene-fusion parent round: {issue}" for issue in issues)
        issues = []
    if issues:
        result["issues"] = issues
        return result

    existing_rounds = _load_round_index(op_dir)
    max_existing = max((r.get("round_index", 0) for r in existing_rounds), default=0)
    next_round_index = max(req.current_round, max_existing) + 1
    source_round_dir = f"opt-round-{req.current_round}"
    next_round_dir_name = f"opt-round-{next_round_index}"
    result["next_round_dir"] = next_round_dir_name
    next_round_dir = op_dir / next_round_dir_name
    next_round_dir.mkdir(parents=True, exist_ok=True)

    return PreludeState(
        op_dir=op_dir,
        current_summary=current_summary,
        existing_rounds=existing_rounds,
        next_round_index=next_round_index,
        source_round_dir=source_round_dir,
        next_round_dir_name=next_round_dir_name,
        next_round_dir=next_round_dir,
    )


def transition_to_next_round(req: TransitionRequest) -> dict[str, Any]:
    """Atomically execute the round transition."""
    current_round = req.current_round
    algorithm = req.algorithm
    baseline_dir = req.baseline_dir
    baseline_dirs = req.baseline_dirs
    strategy_params = req.strategy_params
    switch_marker = req.switch_marker
    result: dict[str, Any] = {
        "status": "fail", "next_round": current_round + 1, "next_round_dir": f"opt-round-{current_round + 1}",
        "baseline_speedup": 0.0, "global_baseline_speedup": req.global_baseline_speedup,
        "global_baseline_dir": req.global_baseline_dir, "issues": [], "warnings": [],
    }

    prelude = _prepare_transition(req, result)
    if isinstance(prelude, dict):
        return prelude
    op_dir = prelude.op_dir
    current_summary = prelude.current_summary
    source_round_dir = prelude.source_round_dir
    next_round_dir = prelude.next_round_dir
    next_round_index = prelude.next_round_index

    # B1 瓶颈卡片 + strategy 加载 + baseline 选择。
    if algorithm == "gene-fusion":
        _generate_bottleneck_card(op_dir / source_round_dir, next_round_dir, result)
    strategy = load_strategy_for_algorithm(read_config(op_dir.parent.parent), algorithm, params=strategy_params)
    op_name = find_op_name(op_dir)
    baseline_path, baseline_entry, baseline_speedup = _select_and_copy_baseline(
        BaselineSelectionSpec(op_dir=op_dir, next_round_dir=next_round_dir, op_name=op_name,
                              baseline_dir=baseline_dir, baseline_dirs=baseline_dirs,
                              strategy=strategy, algorithm=algorithm, result=result)
    )
    result["baseline_speedup"] = baseline_speedup
    direction_metadata = _compute_direction_metadata(DirectionMetaInput(
        op_dir=op_dir, source_round_dir=source_round_dir, current_summary=current_summary,
        baseline_entry=baseline_entry, strategy=strategy, switch_marker=switch_marker,
        global_baseline_speedup=result["global_baseline_speedup"],
    ))
    _write_transition_artifacts(req, prelude, baseline_entry, direction_metadata, result)
    result.update({"status": "success", "next_round": next_round_index, "issues": result["issues"]})
    return result


def _write_transition_artifacts(
    req: TransitionRequest,
    prelude: PreludeState,
    baseline_entry: dict[str, Any] | None,
    direction_metadata: dict[str, Any],
    result: dict[str, Any],
) -> None:
    """Write next-round summary/state/round-index + opt note + transition lock."""
    op_dir, current_round = prelude.op_dir, req.current_round
    next_round_index, next_round_dir_name = prelude.next_round_index, prelude.next_round_dir_name
    next_round_dir, algorithm = prelude.next_round_dir, req.algorithm
    existing_rounds, current_summary = prelude.existing_rounds, prelude.current_summary
    source_round_dir, global_baseline_dir = prelude.source_round_dir, result["global_baseline_dir"]
    global_baseline_speedup, switch_marker = result["global_baseline_speedup"], req.switch_marker

    _write_next_summary(NextSummarySpec(
        next_round_dir=next_round_dir, next_round_index=next_round_index, algorithm=algorithm,
        baseline_entry=baseline_entry, global_baseline_dir=global_baseline_dir,
        global_baseline_speedup=global_baseline_speedup,
        next_round_strategy=req.next_round_strategy, next_analysis_policy=req.next_analysis_policy,
        next_hypothesis=req.next_hypothesis,
        next_direction=req.next_direction, next_evidence_sources=req.next_evidence_sources,
        current_summary=current_summary, algorithm_metadata=req.algorithm_metadata,
    ))
    _update_state_file(StateUpdateSpec(
        op_dir=op_dir, current_round=current_round, next_round_index=next_round_index,
        next_round_dir_name=next_round_dir_name, next_round_dir=next_round_dir,
        algorithm=algorithm, existing_rounds=existing_rounds, result=result,
    ))
    _update_round_index(RoundIndexUpdateSpec(
        op_dir=op_dir, existing_rounds=existing_rounds, current_round=current_round,
        source_round_dir=source_round_dir, current_summary=current_summary,
        direction_metadata=direction_metadata,
        global_baseline_dir=global_baseline_dir, global_baseline_speedup=global_baseline_speedup,
        next_round_index=next_round_index, next_round_dir_name=next_round_dir_name,
        algorithm=algorithm,
        next_direction=req.next_direction, next_hypothesis=req.next_hypothesis,
        next_evidence_sources=req.next_evidence_sources,
        next_analysis_policy=req.next_analysis_policy, next_round_strategy=req.next_round_strategy,
        baseline_entry=baseline_entry, switch_marker=switch_marker,
    ))
    _append_opt_note(OptNoteSpec(
        op_dir=op_dir, current_round=current_round, current_summary=current_summary,
        current_success_criteria=req.current_success_criteria, current_key_learnings=req.current_key_learnings,
        direction_metadata=direction_metadata, switch_marker=switch_marker,
    ))
    _write_transition_lock(op_dir, current_round, next_round_index, next_round_dir_name, result)


def _algorithm_from_state_file(op_dir: Path, enabled: list[str]) -> str | None:
    """state 文件中已保存且仍启用的 algorithm（缺失/损坏/不在启用列表返回 None）。"""
    state_dir = _find_state_dir(op_dir)
    if state_dir is None:
        return None
    state_path = state_dir / f"state-{op_dir.name}.json"
    if not state_path.is_file():
        return None
    try:
        saved_algo = load_json(state_path).get("algorithm")
    except ValueError:
        return None
    if isinstance(saved_algo, str) and saved_algo in enabled:
        return saved_algo
    return None


def _resolve_algorithm(
    cli_algorithm: str | None,
    strategy_name: str,
    op_dir: Path,
) -> str:
    """Resolve the algorithm when --algorithm is not provided.

    Priority:
      1. Explicit CLI --algorithm.
      2. The single enabled algorithm in config.json.
      3. The algorithm saved in the current workspace state file, if enabled.
      4. The explicit --strategy-name (when not auto).
    """
    if cli_algorithm is not None:
        return cli_algorithm

    config = read_config(op_dir.parent.parent)
    discovered = set(discover_strategies().keys())
    enabled = [a for a in get_enabled_algorithms(config) if a in discovered]

    if len(enabled) == 1:
        return enabled[0]

    saved_algo = _algorithm_from_state_file(op_dir, enabled)
    if saved_algo is not None:
        return saved_algo

    if strategy_name != "auto" and strategy_name in discovered:
        return strategy_name

    if not enabled:
        raise ValueError(
            "No algorithms are enabled in config.json; pass --algorithm explicitly."
        )
    raise ValueError(
        f"Multiple algorithms are enabled in config.json: {enabled}. "
        "Pass --algorithm explicitly."
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Transition to the next optimization round")
    parser.add_argument("--op-dir", required=True, help="Operator directory path")
    parser.add_argument("--current-round", type=int, required=True, help="Current round number")
    parser.add_argument("--next-round-strategy", required=True,
                        choices=[
                            "exploration", "structural_change", "focused_tuning",
                            "stabilization", "plateau_review",
                        ],
                        help="Next round strategy")
    parser.add_argument("--next-analysis-policy", required=True,
                        choices=["pattern_entry", "bottleneck_analysis", "ir_supported"],
                        help="Next round analysis policy")
    parser.add_argument("--next-hypothesis", required=True, help="Next round hypothesis")
    parser.add_argument("--next-direction", required=True, help="Next round direction")
    parser.add_argument("--next-evidence-sources", required=True, help="JSON list of evidence sources")
    parser.add_argument("--current-success-criteria", default="", help="Current round success criteria")
    parser.add_argument("--current-key-learnings", default="", help="Current round key learnings")
    parser.add_argument("--baseline-dir", default=None,
                        help="Single baseline round directory to copy code from")
    parser.add_argument("--baseline-dirs", default=None,
                        help="JSON list of baseline round directories (multiple baseline mode)")
    parser.add_argument("--combination-rule", default=None,
                        help="How to combine multiple baselines (e.g. crossover)")
    parser.add_argument("--global-baseline-dir", default=None,
                        help="Global baseline directory for speedup reference")
    parser.add_argument("--global-baseline-speedup", type=float, default=1.0,
                        help="Global baseline speedup (default 1.0)")
    parser.add_argument("--switch-marker", default=None,
                        help='JSON object with reason/previous_direction/new_direction for audit')
    parser.add_argument("--strategy-name", default="auto",
                        help="Direction/baseline selection strategy name. "
                             "Use 'auto' to load the strategy configured in config.json "
                             "(defaults to naive if no config is found).")
    parser.add_argument("--strategy-params", default="{}",
                        help="JSON object of strategy-specific parameters. "
                             "Ignored when --strategy-name=auto.")
    parser.add_argument("--algorithm", default=None,
                        help="Optimization algorithm for the next round. "
                             "Required unless --strategy-name=auto and config.json enables "
                             "exactly one algorithm.")
    parser.add_argument("--algorithm-metadata", default="{}",
                        help="JSON object with algorithm-specific metadata to persist in next summary.json")
    return parser.parse_args()


def _emit_fail(current_round: int, message: str) -> int:
    """Print the standard fail JSON and return exit code 1."""
    sys.stdout.write(json.dumps({
        "status": "fail",
        "next_round": current_round + 1,
        "next_round_dir": f"opt-round-{current_round + 1}",
        "baseline_speedup": 0.0,
        "issues": [message],
        "warnings": [],
    }) + "\n")
    return 1


def _safe_json_loads(raw: str) -> Any:
    """Parse JSON, returning None on malformed/absent input."""
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


@dataclass
class TransitionDerived:
    """Derived transition inputs resolved from CLI args."""

    op_dir: Path
    algorithm: str
    strategy_name: str
    strategy_params: dict[str, Any]
    evidence_sources: list[str]
    baseline_dirs: list[str]
    switch_marker: SwitchMarker | None
    algorithm_metadata: dict[str, Any]


def _build_transition_request(args: argparse.Namespace, d: TransitionDerived) -> TransitionRequest:
    """Build the TransitionRequest from parsed CLI args."""
    return TransitionRequest(
        op_dir=d.op_dir,
        current_round=args.current_round,
        next_round_strategy=args.next_round_strategy,
        next_analysis_policy=args.next_analysis_policy,
        next_hypothesis=args.next_hypothesis,
        next_direction=args.next_direction,
        next_evidence_sources=d.evidence_sources,
        current_success_criteria=args.current_success_criteria,
        current_key_learnings=args.current_key_learnings,
        baseline_dir=args.baseline_dir,
        baseline_dirs=d.baseline_dirs,
        combination_rule=args.combination_rule,
        switch_marker=d.switch_marker,
        strategy_name=d.strategy_name,
        strategy_params=d.strategy_params,
        global_baseline_dir=args.global_baseline_dir,
        global_baseline_speedup=args.global_baseline_speedup,
        algorithm=d.algorithm,
        algorithm_metadata=d.algorithm_metadata,
    )


def main() -> int:
    args = _parse_args()

    op_dir = Path(args.op_dir).expanduser().resolve()
    if not op_dir.is_dir():
        return _emit_fail(args.current_round, f"operator directory not found: {op_dir}")

    try:
        algorithm = _resolve_algorithm(args.algorithm, args.strategy_name, op_dir)
    except ValueError as exc:
        return _emit_fail(args.current_round, str(exc))

    # Strategy parameters: explicit --strategy-params takes precedence; when
    # --strategy-name=auto and empty, fall back to config.json.
    strategy_params = _safe_json_loads(args.strategy_params)
    if not isinstance(strategy_params, dict):
        strategy_params = {}

    if args.strategy_name == "auto":
        strategy_name = algorithm
        if not strategy_params:
            config = read_config(op_dir.parent.parent)
            strategy_params = get_algorithm_params(config, algorithm)
    else:
        strategy_name = args.strategy_name

    evidence_sources = _safe_json_loads(args.next_evidence_sources)
    if not isinstance(evidence_sources, list):
        evidence_sources = [args.next_evidence_sources]

    baseline_dirs: list[str] = []
    if args.baseline_dirs:
        parsed = _safe_json_loads(args.baseline_dirs)
        if isinstance(parsed, list):
            baseline_dirs = [str(x) for x in parsed]

    switch_marker: SwitchMarker | None = None
    if args.switch_marker:
        data = _safe_json_loads(args.switch_marker)
        if isinstance(data, dict):
            switch_marker = SwitchMarker(
                reason=data.get("reason", ""),
                previous_direction=data.get("previous_direction"),
                new_direction=data.get("new_direction"),
            )

    algorithm_metadata = _safe_json_loads(args.algorithm_metadata)
    if not isinstance(algorithm_metadata, dict):
        algorithm_metadata = {}

    result = transition_to_next_round(_build_transition_request(args, TransitionDerived(
        op_dir=op_dir, algorithm=algorithm, strategy_name=strategy_name, strategy_params=strategy_params,
        evidence_sources=evidence_sources, baseline_dirs=baseline_dirs, switch_marker=switch_marker,
        algorithm_metadata=algorithm_metadata,
    )))

    sys.stdout.write(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    return 0 if result["status"] == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
