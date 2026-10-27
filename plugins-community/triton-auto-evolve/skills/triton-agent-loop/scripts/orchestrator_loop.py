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
"""orchestrator_loop.py — 主 Orchestrator 的 round 调度循环参考实现。

用法:
    python3 orchestrator_loop.py \
        --op-name layer_norm \
        --algorithm <discovered-algorithm> \
        --run-tag default \
        --mode A \
        --task-desc path/to/layer_norm.py \
        [--task-json path/to/layer_norm.json] \
        [--gpu-kernel-ref path/to/gpu_kernel_ref.py] \
        [--gpu-perf-csv path/to/gpu_perf.csv] \
        [--timeout 7200] \
        [--op-category matmul]

    可用算法由 skills/triton-agent-loop/scripts/strategies/ 下的 Strategy 子类动态发现。

说明:
    本脚本仅作为参考实现。主 Claude Code Agent 可以直接调用其中的函数，
    也可以复现其逻辑。它负责：
    1. 初始化 workspace 和 state-{op_name}-{algorithm}-{run_tag}.json
    2. 循环生成 task_manifest.json
    3. 调用 dispatch_round.py 启动子 CLI
    4. 解析 round_result.json
    5. 执行 C1/C2 停止/继续判定
    6. 停止时选择全局最优 round 并输出最终报告

工作区隔离:
    不同算法或同一算法的不同运行使用独立目录：
        triton_ascend_output/{op_name}-{algorithm}-{run_tag}/

设计变更（v2）:
    - C3/D4 判定从 Orchestrator 移除，下沉到各进化策略内部。
    - 不再创建 opt-round-N-switch 目录；方向切换只作为元数据记录。
    - 所有策略通过 RoundDecision 信封返回决策，Orchestrator 只补全缺失项。
    - algorithm 不再配置在 config.json 中；由用户在会话开始时选择，并写入 state。
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config_loader import (
    read_config,
    get_enabled_algorithms,
    get_algorithm_params,
)
from direction_selector import build_direction_history
from strategies import discover_strategies, load_strategy_for_algorithm
from strategies.base import BaselineProposal, RoundDecision

logger = logging.getLogger(__name__)


SCRIPT_DIR = Path(__file__).resolve().parent
CTRL_SKILLS_DIR = SCRIPT_DIR.parent
REPO_OPS_CANDIDATES = [
    SCRIPT_DIR.parents[5] / "ops",
    SCRIPT_DIR.parents[6] / "ops",
]

_ORCH_T0 = time.monotonic()


def _stage(label: str) -> None:
    """A4: 轮内阶段打点，逐行 flush（本机 stdout 块缓冲已踩过坑）。

    定位 summary(N)→manifest(N+1) 轮间过渡异常的观测基础：各阶段耗时一目了然。
    """
    logger.info(
        "[timing] +%8.1fs %s %s",
        time.monotonic() - _ORCH_T0,
        datetime.now(timezone.utc).astimezone().strftime("%H:%M:%S"),
        label,
    )


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def find_ops_root() -> Path | None:
    """Find shared ops/ directory."""
    for candidate in REPO_OPS_CANDIDATES:
        if candidate.is_dir():
            return candidate
    return None


def _algorithm_reference(algorithm: str) -> str:
    """Return the reference document path for an algorithm."""
    return f".claude/references/algorithms/{algorithm}/round.md"


def select_algorithm(
    config: dict[str, Any],
    state: dict[str, Any] | None = None,
) -> str | None:
    """Determine the active optimization algorithm for this task.

    Priority:
      1. ``state["algorithm"]`` if present and still enabled.
      2. If exactly one algorithm is enabled in ``config["algorithms"]``, use it.
      3. Otherwise return ``None`` so the caller can ask the user.

    The main Claude Code agent should use ``AskUserQuestion`` when this function
    returns ``None``.  When running this script directly, pass ``--algorithm``.
    """
    discovered = set(discover_strategies().keys())
    enabled = [a for a in get_enabled_algorithms(config) if a in discovered]
    if not enabled:
        raise ValueError("No algorithms are enabled in config.json")

    if state and isinstance(state.get("algorithm"), str):
        algo = state.get("algorithm")
        if algo in enabled:
            return algo

    if len(enabled) == 1:
        return enabled[0]

    return None


def _discovered_algorithm_names() -> set[str]:
    """Return the set of algorithm names discovered from strategy modules."""
    return set(discover_strategies().keys())


def _find_legacy_workspace(
    cwd: Path, op_name: str
) -> tuple[Path, dict[str, Any]] | None:
    """Detect a legacy workspace: triton_ascend_output/{op_name}/ + state-{op_name}.json."""
    legacy_op_dir = cwd / "triton_ascend_output" / op_name
    legacy_state_path = cwd / ".triton-agent" / f"state-{op_name}.json"
    if not legacy_op_dir.is_dir() or not legacy_state_path.is_file():
        return None
    try:
        return legacy_op_dir, load_json(legacy_state_path)
    except ValueError:
        return None


def _algorithm_from_round_index(round_index_path: Path, discovered: set[str]) -> str | None:
    """round_index.json 首条记录的 algorithm 字段（合法且已启用才返回）。"""
    if not round_index_path.is_file():
        return None
    try:
        data = load_json(round_index_path)
    except ValueError:
        return None
    if not isinstance(data, list) or not data:
        return None
    algo = data[0].get("algorithm")
    if isinstance(algo, str) and algo in discovered:
        return algo
    return None


def _algorithm_from_summaries(legacy_op_dir: Path, discovered: set[str]) -> str | None:
    """opt-round-*/summary.json 中首个合法的 algorithm 字段。"""
    for summary_path in sorted(legacy_op_dir.glob("opt-round-*/summary.json")):
        try:
            algo = load_json(summary_path).get("algorithm")
        except ValueError:
            continue
        if isinstance(algo, str) and algo in discovered:
            return algo
    return None


def _infer_algorithm_from_legacy(
    legacy_state: dict[str, Any],
    legacy_op_dir: Path,
    discovered: set[str],
) -> str | None:
    """Infer the algorithm used by a legacy workspace from multiple sources."""
    state_algo = legacy_state.get("algorithm")
    if isinstance(state_algo, str) and state_algo in discovered:
        return state_algo
    from_index = _algorithm_from_round_index(legacy_op_dir / "round_index.json", discovered)
    if from_index is not None:
        return from_index
    return _algorithm_from_summaries(legacy_op_dir, discovered)


def _discover_algorithm_from_new_state(cwd: Path, op_name: str) -> str | None:
    """Scan new-format state files and read the saved algorithm.

    Returns the algorithm if exactly one matching state file exists; otherwise
    returns None so the caller can ask the user or fall back to other sources.
    """
    state_dir = cwd / ".triton-agent"
    if not state_dir.is_dir():
        return None
    matches = list(state_dir.glob(f"state-{op_name}-*.json"))
    if len(matches) != 1:
        return None
    try:
        return load_json(matches[0]).get("algorithm")
    except ValueError:
        return None


def _list_new_state_algorithms(
    cwd: Path,
    op_name: str,
    run_tag: str | None = None,
) -> dict[str, Path]:
    """Return a mapping of algorithm -> state file path for new-format states.

    If *run_tag* is provided, only state files whose names end with
    ``-{run_tag}.json`` are considered. This isolates workspaces that differ
    only by run tag so that ``--algorithm naive --run-tag run2`` does not
    conflict with an existing ``state-{op_name}-mcts-default.json``.
    """
    state_dir = cwd / ".triton-agent"
    if not state_dir.is_dir():
        return {}
    result: dict[str, Path] = {}
    for path in state_dir.glob(f"state-{op_name}-*.json"):
        if run_tag is not None and not path.name.endswith(f"-{run_tag}.json"):
            continue
        try:
            algo = load_json(path).get("algorithm")
            if isinstance(algo, str) and algo:
                result[algo] = path
        except ValueError:
            continue
    return result


def _build_legacy_report(
    op_name: str,
    legacy_op_dir: Path,
    legacy_state: dict[str, Any],
    inferred: str | None,
) -> dict[str, Any]:
    """Build a structured report about a detected legacy workspace."""
    return {
        "type": "legacy_workspace_detected",
        "op_name": op_name,
        "legacy_dir": str(legacy_op_dir),
        "legacy_state": str(
            legacy_op_dir.parent.parent / ".triton-agent" / f"state-{op_name}.json"
        ),
        "current_round": legacy_state.get("current_round", "unknown"),
        "last_work_dir": legacy_state.get("work_dir", "unknown"),
        "state_algorithm": legacy_state.get("algorithm", "unknown"),
        "inferred_algorithm": inferred,
        "migration_plan": (
            f"Rename {legacy_op_dir.name} to {op_name}-<algorithm>-<run_tag>/, "
            f"create .triton-agent/state-{op_name}-<algorithm>-<run_tag>.json, "
            "preserve all round data."
        ),
        "options": [
            {
                "id": "continue_inferred",
                "label": f"Continue with inferred algorithm '{inferred or 'unknown'}'",
            },
            {"id": "specify_algorithm", "label": "Specify a different algorithm"},
            {"id": "abandon", "label": "Abandon legacy workspace and start fresh"},
        ],
    }


def _migrate_legacy_workspace(
    cwd: Path,
    op_name: str,
    algorithm: str,
    run_tag: str,
    legacy: tuple[Path, dict[str, Any]],
) -> Path:
    """Migrate a legacy workspace to the new naming scheme.

    Returns the new operator directory path.
    """
    legacy_op_dir, legacy_state = legacy
    new_op_dir = cwd / "triton_ascend_output" / f"{op_name}-{algorithm}-{run_tag}"
    new_state_path = cwd / ".triton-agent" / f"state-{new_op_dir.name}.json"
    if new_op_dir.exists():
        raise FileExistsError(f"Migration target already exists: {new_op_dir}")

    legacy_op_dir.rename(new_op_dir)

    current_round = legacy_state.get("current_round", 1)
    work_dir = new_op_dir / f"opt-round-{current_round}"
    legacy_state.update(
        {
            "algorithm": algorithm,
            "run_tag": run_tag,
            "algorithm_reference": _algorithm_reference(algorithm),
            "work_dir": str(work_dir),
        }
    )
    save_json(new_state_path, legacy_state)

    # Ensure a round_index.json exists so the migration is treated as a recovery
    # rather than a fresh initialization.
    round_index_path = new_op_dir / "round_index.json"
    if not round_index_path.is_file():
        save_json(round_index_path, [])

    legacy_state_path = cwd / ".triton-agent" / f"state-{op_name}.json"
    if legacy_state_path.is_file():
        legacy_state_path.write_text(
            json.dumps(
                {
                    "migrated": True,
                    "migrated_to": str(new_state_path),
                    "migrated_at": datetime.now(timezone.utc).isoformat(),
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

    return new_op_dir


def _write_global_baseline(op_dir: Path, op_name: str, task_desc: Path) -> None:
    """Copy the user task file as the immutable global baseline."""
    global_baseline_dir = op_dir / "global_baseline"
    global_baseline_dir.mkdir(parents=True, exist_ok=True)
    global_baseline_code = global_baseline_dir / f"{op_name}_generated.py"
    if task_desc.is_file():
        shutil.copy2(task_desc, global_baseline_code)
    baseline_info = {
        "source_path": str(task_desc),
        "baseline_speedup": 1.0,
        "established_at": datetime.now(timezone.utc).isoformat(),
    }
    save_json(global_baseline_dir / "baseline_info.json", baseline_info)


def _write_experience_file(op_dir: Path, op_name: str, algorithm: str, run_tag: str) -> None:
    """Write the operator-level experience file."""
    experience_path = op_dir / "operator_experience.md"
    experience_path.write_text(
        f"# Operator Experience: {op_name} ({algorithm}/{run_tag})\n\n"
        "## Failures / Avoid\n"
        "<!-- Sub-agent appends here after each round -->\n\n"
        "## Successful Patterns\n"
        "<!-- Sub-agent appends here after each round -->\n\n"
        "## Notes\n",
        encoding="utf-8",
    )


def _write_initial_state(
    cfg: OrchestratorConfig, op_dir: Path, algorithm: str, round_dir: Path, algorithm_ref: str,
) -> None:
    """Write the initial state file."""
    state = {
        "op_name": cfg.op_name,
        "algorithm": algorithm,
        "run_tag": cfg.run_tag,
        "status": "active",
        "current_round": 1,
        "algorithm_reference": algorithm_ref,
        "rounds": {"1": {"status": "active", "round_dir": "opt-round-1"}},
        "phase": "round_active",
        "work_dir": str(round_dir),
        "last_phase": 0,
        "performance_history": [],
        "direction_history": [],
    }
    state_dir = cfg.cwd / ".triton-agent"
    state_dir.mkdir(parents=True, exist_ok=True)
    save_json(state_dir / f"state-{op_dir.name}.json", state)


def _write_initial_summary(
    round_dir: Path, op_name: str, algorithm: str, target_speedup: float,
) -> None:
    """Write the Round 1 summary.json."""
    summary = {
        "round_index": 1,
        "algorithm": algorithm,
        "baseline_dir": "global_baseline",
        "global_baseline_dir": "global_baseline",
        "global_baseline_speedup": 1.0,
        "round_strategy": "exploration",
        "analysis_policy": "pattern_entry",
        "hypothesis": f"Initial LLM-driven exploration for {op_name} optimization",
        "direction": "pattern: custom",
        "evidence_sources": ["model_knowledge"],
        "status": "active",
        "best_speedup": 0.0,
        "success": False,
        "target_speedup": target_speedup,
    }
    save_json(round_dir / "summary.json", summary)


def _write_initial_round_index(
    op_dir: Path, op_name: str, algorithm: str, target_speedup: float,
) -> None:
    """Write the initial round_index.json."""
    round_index = [{
        "round_index": 1,
        "round_dir": "opt-round-1",
        "algorithm": algorithm,
        "direction": "pattern: custom",
        "hypothesis": f"Initial LLM-driven exploration for {op_name} optimization",
        "evidence_sources": ["model_knowledge"],
        "analysis_policy": "pattern_entry",
        "effective_metric_source": "kernel",
        "status": "active",
        "best_speedup": 0.0,
        "round_strategy": "exploration",
        "direction_yield": None,
        "yield_reason": None,
        "absolute_gain_vs_baseline": None,
        "absolute_gain_vs_global_baseline": None,
        "baseline_dir": "global_baseline",
        "global_baseline_dir": "global_baseline",
        "global_baseline_speedup": 1.0,
        "consecutive_low_gain_count": 0,
        "round_type": "active",
        "target_speedup": target_speedup,
    }]
    save_json(op_dir / "round_index.json", round_index)


def init_workspace(
    cfg: OrchestratorConfig, op_dir: Path, config: dict[str, Any], algorithm: str,
) -> Path:
    """Initialize workspace for Round 1."""
    algorithm_ref = _algorithm_reference(algorithm)
    round_dir = op_dir / "opt-round-1"
    round_dir.mkdir(parents=True, exist_ok=True)
    init_cfg = OrchestratorConfig(
        cwd=cfg.cwd, op_name=cfg.op_name, mode=cfg.mode, task_desc=cfg.task_desc,
        task_json=cfg.task_json, gpu_kernel_ref=cfg.gpu_kernel_ref, gpu_perf_csv=cfg.gpu_perf_csv,
        algorithm=algorithm, run_tag=cfg.run_tag,
    )
    _write_global_baseline(op_dir, cfg.op_name, cfg.task_desc)
    _write_experience_file(op_dir, cfg.op_name, algorithm, cfg.run_tag)
    _write_initial_state(init_cfg, op_dir, algorithm, round_dir, algorithm_ref)
    target_speedup = config.get("target_speedup", 5)
    _write_initial_summary(round_dir, cfg.op_name, algorithm, target_speedup)
    _write_initial_round_index(op_dir, cfg.op_name, algorithm, target_speedup)

    return round_dir


@dataclass
class ManifestSpec:
    """Inputs for writing the round worker's task_manifest.json."""

    op_dir: Path
    op_name: str
    round_index: int
    baseline_dir: Path | None
    algorithm: str
    round_strategy: str
    analysis_policy: str
    hypothesis: str
    direction: str
    evidence_sources: list[str]
    mode: str
    task_desc: Path
    task_json: Path | None
    gpu_kernel_ref: Path | None
    gpu_perf_csv: Path | None
    config: dict[str, Any]
    arch: str = "ascend910b1"
    lineage_summary: list[dict[str, Any]] | None = None
    experience_file: str | None = None
    global_baseline_dir: Path | None = None
    global_baseline_speedup: float = 1.0
    decision_metadata: dict[str, Any] | None = None


def _apply_decision_metadata(
    manifest: dict[str, Any],
    algorithm: str,
    decision_metadata: dict[str, Any] | None,
) -> None:
    """Forward algorithm-specific metadata and gene-fusion route_mix into the manifest."""
    if decision_metadata:
        for key in ("mcts_parent_id", "mcts_selection_path", "mcts_pending_expansion"):
            if key in decision_metadata:
                manifest[key] = decision_metadata[key]
    if algorithm == "gene-fusion" and isinstance(decision_metadata, dict):
        route_mix = decision_metadata.get("route_mix")
        if isinstance(route_mix, dict) and "elite_count" in route_mix:
            manifest["route_mix"] = route_mix
            adapted = dict(manifest["algorithm_params"] or {})
            adapted["elite_count"] = route_mix["elite_count"]
            adapted["exploration_count"] = route_mix["exploration_count"]
            if route_mix.get("adjust_reason"):
                adapted["route_mix_adjust"] = route_mix["adjust_reason"]
            manifest["algorithm_params"] = adapted


def build_manifest(spec: ManifestSpec) -> Path:
    """Write task_manifest.json for the round worker."""
    work_dir = spec.op_dir / f"opt-round-{spec.round_index}"
    work_dir.mkdir(parents=True, exist_ok=True)

    algorithm_reference = _algorithm_reference(spec.algorithm)
    algorithm_params = get_algorithm_params(spec.config, spec.algorithm)

    parent_round_journal: str | None = None
    if spec.baseline_dir is not None:
        journal_path = Path(spec.baseline_dir) / "round_journal.md"
        if journal_path.is_file():
            parent_round_journal = str(journal_path)

    manifest: dict[str, Any] = {
        "op_name": spec.op_name,
        "round_index": spec.round_index,
        "work_dir": str(work_dir),
        "baseline_dir": str(spec.baseline_dir) if spec.baseline_dir else None,
        "algorithm": spec.algorithm,
        "algorithm_reference": algorithm_reference,
        "algorithm_params": algorithm_params,
        "round_strategy": spec.round_strategy,
        "analysis_policy": spec.analysis_policy,
        "hypothesis": spec.hypothesis,
        "direction": spec.direction,
        "evidence_sources": spec.evidence_sources,
        "mode": spec.mode,
        "arch": spec.arch,
        "input_files": {
            "task_desc": str(spec.task_desc),
            "task_json": str(spec.task_json) if spec.task_json else None,
            "gpu_kernel_ref": str(spec.gpu_kernel_ref) if spec.gpu_kernel_ref else None,
            "gpu_perf_csv": str(spec.gpu_perf_csv) if spec.gpu_perf_csv else None,
        },
        "config": spec.config,
        "is_recovery": False,
        "worker_reference": algorithm_reference,
        "lineage_summary": spec.lineage_summary or [],
        "experience_file": spec.experience_file,
        "global_baseline_dir": str(spec.global_baseline_dir) if spec.global_baseline_dir else None,
        "global_baseline_speedup": spec.global_baseline_speedup,
        "parent_round_journal": parent_round_journal,
    }

    _apply_decision_metadata(manifest, spec.algorithm, spec.decision_metadata)

    manifest_path = spec.op_dir / f".task_manifest_{spec.round_index}.json"
    save_json(manifest_path, manifest)
    return manifest_path


def dispatch_round(manifest_path: Path, timeout: int = 7200) -> dict[str, Any]:
    """Call dispatch_round.py to spawn sub CLI."""
    cmd = [
        sys.executable,
        str(SCRIPT_DIR / "dispatch_round.py"),
        "--manifest", str(manifest_path),
        "--timeout", str(timeout),
    ]
    try:
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True)
        return json.loads(output)
    except subprocess.CalledProcessError as exc:
        try:
            return json.loads(exc.output)
        except json.JSONDecodeError:
            return {
                "status": "error",
                "stderr": exc.output,
                "returncode": exc.returncode,
            }
    except json.JSONDecodeError as exc:
        return {"status": "error", "stderr": f"invalid JSON from dispatch_round.py: {exc}"}


def _run_helper(cmd: list[str], timeout: int = 600) -> tuple[int, str]:
    """Run a helper script; return (returncode, combined output)."""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except (subprocess.TimeoutExpired, OSError) as exc:
        return 1, str(exc)


def _build_routes_spec(
    pool: dict[str, Any],
    params_cfg: dict[str, Any],
    rng: random.Random,
    elite_gene_ids: list[str],
    mix: dict[str, Any],
) -> list[tuple[str, str, list[str], str]]:
    """Build the (route_id, route_type, gene_ids, hypothesis) route spec list."""
    routes_spec: list[tuple[str, str, list[str], str]] = []
    n_elite = int(mix.get("elite_count", 1) or 0)
    n_cross = int(mix.get("crossover_count", 1) or 0)
    n_expl = int(mix.get("exploration_count", 1) or 0)
    idx = 0
    for i in range(n_elite):
        idx += 1
        genes = elite_gene_ids if i == 0 else gene_ops.mutate(
            pool, elite_gene_ids, 0.05, rng).get("genes", elite_gene_ids)
        routes_spec.append((f"route-{idx}", "elite", genes,
                            f"elite fidelity: {genes}"))
    pick_i = 0
    for _ in range(n_cross):
        idx += 1
        other = gene_ops.select_combo(pool, rng)
        crossed = gene_ops.crossover(pool, elite_gene_ids, other,
                                     float(params_cfg.get("crossover_rate", 0.7)), rng)
        mutated = gene_ops.mutate(pool, crossed.get("child", elite_gene_ids),
                                  float(params_cfg.get("mutation_rate", 0.15)), rng)
        genes = mutated.get("genes", elite_gene_ids)
        pick_i += 1
        routes_spec.append((f"route-{idx}", "crossover", genes,
                            f"crossover elite x pick{pick_i}: {genes}"))
    for _ in range(n_expl):
        idx += 1
        picked = gene_ops.select_combo(pool, rng, include_candidates=True)
        mutated = gene_ops.mutate(pool, picked, float(params_cfg.get("mutation_rate", 0.15)), rng)
        genes = mutated.get("genes", picked)
        routes_spec.append((f"route-{idx}", "exploration", genes,
                            f"exploration (candidates preferred): {genes}"))
    return routes_spec


def _collect_and_validate(
    work_dir: Path,
    routes_spec: list[tuple[str, str, list[str], str]],
    parallel: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, str]], bool]:
    """Collect and semantically validate each route; reject invalid ones wholesale."""
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, str]] = []
    any_timeout = False
    for route_id, route_type, gene_ids, _hyp in routes_spec:
        res = parallel.get(route_id) or {}
        route_dir = work_dir / route_id
        rr_path = route_dir / "round_result.json"
        if res.get("status") == "timeout" or not rr_path.is_file():
            any_timeout = True
            rejected.append({"route_id": route_id, "reason": "timeout or no round_result"})
            continue
        if res.get("status") != "success":
            rejected.append({"route_id": route_id, "reason": f"dispatch status={res.get('status')}"})
            continue
        vrc, vout = _run_helper(
            [sys.executable, str(SCRIPT_DIR / "validate_round_result.py"),
             "--round-result", str(rr_path), "--work-dir", str(route_dir)])
        try:
            verdict = json.loads(vout)
        except json.JSONDecodeError:
            verdict = {"accepted": False, "rejected": ["verdict_unparseable"]}
        if vrc != 0 or not verdict.get("accepted"):
            rejected.append({"route_id": route_id,
                             "reason": f"validate rejected: {verdict.get('rejected')}"})
            continue
        rr = load_json(rr_path)
        accepted.append({
            "route_id": route_id, "route_type": route_type, "gene_ids": gene_ids,
            "speedup": rr.get("best_speedup", 0.0),
            "best_task_duration_us": rr.get("best_task_duration_us"),
            "status": "success",
            "verdict_suspicious": verdict.get("suspicious", []),
            "round_result": rr,
        })
    return accepted, rejected, any_timeout


def _merge_proposals(
    pool: dict[str, Any],
    accepted: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """H1 下沉：合并 accepted route 的 proposed_genes（去重 + 范围校验，不做推理）。"""
    allowed_categories = {"tiling", "memory", "compute", "pipeline", "vectorization", "structural"}
    existing_ids = {g.get("gene_id") for g in pool.get("genes", [])}
    next_gene_num = 1 + max(
        (int(str(g.get("gene_id", "")).lstrip("G") or 0) for g in pool.get("genes", [])),
        default=0,
    )
    merged_proposals: list[dict[str, Any]] = []
    for acc in accepted:
        for prop in (acc.get("round_result", {}).get("knowledge") or {}).get("proposed_genes") or []:
            gid = prop.get("gene_id")
            if not gid or gid in existing_ids:
                continue
            if prop.get("category") not in allowed_categories:
                continue
            new_gene = {
                "gene_id": f"G{next_gene_num:03d}",
                "ku_id": f"P{next_gene_num:03d}",
                "category": prop["category"],
                "description": prop.get("description", ""),
                "source": "route_proposal",
                "source_priority": 3,
                "code_target": prop.get("code_target", "kernel body"),
                "params": prop.get("params") or {},
                "conflicts_with": [],
                "status": "candidate",
                "fitness": None,
                "evidence": {"bottleneck_tag": prop.get("bottleneck_tag"),
                             "hypothesis": prop.get("hypothesis"),
                             "proposed_by": acc["route_id"]},
            }
            pool["genes"].append(new_gene)
            existing_ids.add(new_gene["gene_id"])
            merged_proposals.append({"gene_id": new_gene["gene_id"], "from": acc["route_id"]})
            next_gene_num += 1
    return merged_proposals


@dataclass
class ParentRRSpec:
    """Inputs for assembling the parent-level round_result.json."""

    work_dir: Path
    current_round: int
    config: dict[str, Any]
    round_index: list[dict[str, Any]]
    decision: Any
    baseline_dir: Path
    mix: dict[str, Any]
    accepted: list[dict[str, Any]]
    rejected: list[dict[str, str]]
    any_timeout: bool
    merged_proposals: list[dict[str, Any]]


def _build_parent_round_result(spec: ParentRRSpec) -> dict[str, Any]:
    """Assemble the parent-level round_result.json (same shape as parent session)."""
    prev_best_speedup = max(
        (float(r.get("best_speedup") or 0.0) for r in spec.round_index
         if r.get("status") == "success" and r.get("round_index") < spec.current_round),
        default=0.0,
    )
    best_acc = max(spec.accepted, key=lambda r: r["speedup"]) if spec.accepted else None
    best_speedup = float(best_acc["speedup"]) if best_acc else 0.0
    parent_rr = {
        "round_index": spec.current_round,
        "status": "success" if spec.accepted else ("timeout" if spec.any_timeout else "failed"),
        "algorithm": "gene-fusion",
        "best_speedup": best_speedup,
        "best_task_duration_us": best_acc.get("best_task_duration_us") if best_acc else None,
        "target_reached": bool(
            best_speedup >= float(spec.config.get("target_speedup", 5) or 5)),
        "improvement_made": bool(best_speedup > prev_best_speedup > 0 or
                                 (best_speedup > 0 and prev_best_speedup == 0)),
        "effective_metric_source": "kernel",
        "direction": spec.decision.direction or "",
        "hypothesis": spec.decision.hypothesis or "",
        "round_strategy": spec.decision.round_strategy or "exploration",
        "baseline_dir": str(spec.baseline_dir),
        "design_summary": (
            f"Round {spec.current_round} direct dispatch (H1, no parent session): "
            f"route_mix={spec.mix.get('adjust_reason') or 'default 1/1/1'}; "
            f"{len(spec.accepted)} accepted, {len(spec.rejected)} rejected"
            + (f"; rejected: {[(r['route_id'], r['reason']) for r in spec.rejected]}"
               if spec.rejected else "")
            + (f"; proposed genes merged: {[p['gene_id'] for p in spec.merged_proposals]}"
               if spec.merged_proposals else "")),
        "iter_count": len(spec.accepted),
        "opt_iter_count": 0,
        "gene_fusion": {
            "direct_dispatch": True,
            "route_mix": spec.mix,
            "accepted_routes": [a["route_id"] for a in spec.accepted],
            "rejected_routes": spec.rejected,
            "proposed_genes_merged": spec.merged_proposals,
        },
    }
    return parent_rr


@dataclass
class GfContext:
    """Resolved gene-fusion direct-dispatch context."""

    pool: dict[str, Any]
    fusion_plan: dict[str, Any]
    decision: Any
    mix: dict[str, Any]
    rng: random.Random
    params_cfg: dict[str, Any]
    prev_best: str | None
    elite_gene_ids: list[str]


@dataclass
class GfResolveSpec:
    """Inputs for resolving the gene-fusion direct-dispatch context."""

    op_dir: Path
    current_round: int
    baseline_dir: Path | None
    config: dict[str, Any]
    strategy: Any
    round_index: list[dict[str, Any]]
    op_category: str | None


def _resolve_gf_context(spec: GfResolveSpec) -> GfContext | dict[str, Any]:
    """Resolve the gene-fusion direct-dispatch context, or return a fallback dict."""
    op_dir = spec.op_dir
    current_round = spec.current_round
    baseline_dir = spec.baseline_dir
    config = spec.config
    strategy = spec.strategy
    round_index = spec.round_index
    op_category = spec.op_category
    if baseline_dir is None or not (baseline_dir / "gene_pool.json").is_file():
        return {"status": "fallback", "reason": "baseline gene_pool.json missing"}
    try:
        pool = json.loads((baseline_dir / "gene_pool.json").read_text(encoding="utf-8"))
        fusion_plan = json.loads((baseline_dir / "fusion_plan.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "fallback", "reason": f"baseline gene_pool/fusion_plan unreadable: {exc}"}

    try:
        decision = strategy.select_next_round(
            round_index, op_category=op_category, current_policy="pattern_entry",
            context={"op_dir": str(op_dir), "current_round": current_round},
        )
    except Exception as exc:
        return {"status": "fallback", "reason": f"strategy decision failed: {exc}"}
    mix = (decision.metadata or {}).get("route_mix") or {
        "elite_count": 1, "crossover_count": 1, "exploration_count": 1, "adjust_reason": None,
    }

    rng = random.Random(os.environ.get("TRITON_GF_DIRECT_SEED") or None)
    params_cfg = config.get("algorithms", {}).get("gene-fusion", {}).get("params", {})
    prev_best = pool.get("best_route")
    elite_gene_ids: list[str] = []
    for res in pool.get("route_results", []):
        if res.get("route_id") == prev_best:
            elite_gene_ids = list(res.get("gene_ids") or [])
            break
    if not elite_gene_ids:
        return {"status": "fallback", "reason": "gene_pool missing best_route gene_ids"}

    return GfContext(
        pool=pool, fusion_plan=fusion_plan, decision=decision, mix=mix,
        rng=rng, params_cfg=params_cfg, prev_best=prev_best, elite_gene_ids=elite_gene_ids,
    )


@dataclass
class RenderSpec:
    """Inputs for rendering the per-route task manifests."""

    work_dir: Path
    baseline_dir: Path
    pool: dict[str, Any]
    routes_spec: list[tuple[str, str, list[str], str]]
    op_name: str
    current_round: int
    fusion_plan: dict[str, Any]
    mode: str
    arch: str
    task_desc: Path | None
    task_json: Path | None
    gpu_kernel_ref: Path | None
    gpu_perf_csv: Path | None
    prev_best: str | None


def _render_route_manifests(spec: RenderSpec) -> list[Path]:
    """Render the .task_manifest.json for each route in routes_spec."""
    manifest_paths: list[Path] = []
    for route_id, route_type, gene_ids, hypothesis in spec.routes_spec:
        route_work_dir = spec.work_dir / route_id
        route_work_dir.mkdir(parents=True, exist_ok=True)
        fields = gene_ops.build_manifest_fields(
            spec.pool, route_id, route_type, str(route_work_dir), str(spec.baseline_dir),
            gene_ids, spec.op_name, spec.current_round, hypothesis=hypothesis,
        )
        fields.update({
            "round_index": spec.current_round,
            "round_strategy": "exploration",
            "analysis_policy": "pattern_entry",
            "fusion_plan": spec.fusion_plan,
            "mode": spec.mode,
            "arch": spec.arch,
            "input_files": {
                "task_desc": str(spec.task_desc) if spec.task_desc else None,
                "task_json": str(spec.task_json) if spec.task_json else None,
                "gpu_kernel_ref": str(spec.gpu_kernel_ref) if spec.gpu_kernel_ref else None,
                "gpu_perf_csv": str(spec.gpu_perf_csv) if spec.gpu_perf_csv else None,
            },
            "genetic_metadata": {**(fields.get("genetic_metadata") or {}),
                                 "route_type": route_type, "parent_routes": [spec.prev_best or ""]},
        })
        mpath = route_work_dir / ".task_manifest.json"
        save_json(mpath, fields)
        manifest_paths.append(mpath)
    return manifest_paths


def _dispatch_routes_parallel(
    work_dir: Path,
    params_cfg: dict[str, Any],
    current_round: int,
    manifest_paths: list[Path],
) -> dict[str, Any]:
    """Run dispatch_parallel over the route manifests; returns parallel result or a fallback."""
    dispatch_script = Path(os.environ.get(
        "TRITON_DISPATCH_PARALLEL", str(SCRIPT_DIR / "dispatch_parallel.py")))
    route_timeout = int(params_cfg.get("route_timeout", 3600))
    _stage(f"round {current_round}: direct dispatch_parallel {len(manifest_paths)} routes")
    rc, output = _run_helper(
        [sys.executable, str(dispatch_script),
         "--manifests", *[str(p) for p in manifest_paths],
         "--timeout", str(route_timeout)],
        timeout=route_timeout * len(manifest_paths) + 600,
    )
    parallel_path = work_dir / "parallel_result.json"
    if not parallel_path.is_file():
        return {"status": "timeout" if rc != 0 else "failed",
                "reason": f"direct dispatch produced no parallel_result.json: {output[-400:]}"}
    return load_json(parallel_path)


def _record_gene_pool(
    pool: dict[str, Any],
    accepted: list[dict[str, Any]],
    current_round: int,
    work_dir: Path,
) -> None:
    """G6 记账：适应度更新 + tested combos（update_fitness 原地改池，返回值仅 log）。"""
    gene_ops.update_fitness(pool, accepted, round_index=current_round)
    pool["route_results"] = [
        {k: v for k, v in acc.items() if k != "round_result"} for acc in accepted
    ]
    if accepted:
        best_acc = max(accepted, key=lambda r: r["speedup"])
        pool["best_route"] = best_acc["route_id"]
        pool["best_speedup"] = best_acc["speedup"]
        pool["best_task_duration_us"] = best_acc.get("best_task_duration_us")
    pool["generation"] = current_round - 1
    pool["round_index"] = current_round
    save_json(work_dir / "gene_pool.json", pool)


def _render_gf_artifacts(work_dir: Path, current_round: int, params_cfg: dict[str, Any]) -> None:
    """Render report.md and narrative artifacts (best-effort)."""
    _run_helper([sys.executable, str(SCRIPT_DIR / "render_report.py"),
                 "--round-result", str(work_dir / "round_result.json"),
                 "--out", str(work_dir / "report.md")], timeout=120)
    jp = [str(work_dir / "round_result.json"), str(work_dir / "gene_pool.json")]
    prose_model = str(params_cfg.get("prose_model") or "claude-haiku-4-5-20251001")
    _run_helper([sys.executable, str(SCRIPT_DIR / "prose_render.py"),
                 "--kind", "knowledge_evolution", "--json", *jp,
                 "--out", str(work_dir / "knowledge_evolution.md"),
                 "--prose-model", prose_model], timeout=240)
    _run_helper([sys.executable, str(SCRIPT_DIR / "prose_render.py"),
                 "--kind", "round_journal", "--round-index", str(current_round),
                 "--json", *jp,
                 "--out", str(work_dir / "round_journal.md"),
                 "--prose-model", prose_model], timeout=240)


@dataclass
class GfDirectSpec:
    """Inputs for the gene-fusion direct-dispatch path (H1)."""

    op_dir: Path
    op_name: str
    current_round: int
    baseline_dir: Path | None
    config: dict[str, Any]
    strategy: Any
    round_index: list[dict[str, Any]]
    op_category: str | None
    task_desc: Path | None
    task_json: Path | None
    gpu_kernel_ref: Path | None
    gpu_perf_csv: Path | None
    arch: str
    mode: str


def dispatch_gene_fusion_direct(spec: GfDirectSpec) -> dict[str, Any]:
    """H1 Round 2+ 直派：跳过父 sub agent，编排器直接完成 G0-G6；前置不满足返回 fallback。"""
    import gene_ops  # 同目录，延迟导入避免非 gene-fusion 路径的开销

    op_dir, op_name = spec.op_dir, spec.op_name
    current_round, baseline_dir = spec.current_round, spec.baseline_dir
    config, strategy = spec.config, spec.strategy
    round_index, op_category = spec.round_index, spec.op_category
    task_desc, task_json = spec.task_desc, spec.task_json
    gpu_kernel_ref, gpu_perf_csv = spec.gpu_kernel_ref, spec.gpu_perf_csv
    arch, mode = spec.arch, spec.mode
    work_dir = op_dir / f"opt-round-{current_round}"
    gf = _resolve_gf_context(GfResolveSpec(
        op_dir=op_dir, current_round=current_round, baseline_dir=baseline_dir, config=config,
        strategy=strategy, round_index=round_index, op_category=op_category,
    ))
    if isinstance(gf, dict):
        return gf
    pool, fusion_plan = gf.pool, gf.fusion_plan
    decision, mix = gf.decision, gf.mix
    rng, params_cfg = gf.rng, gf.params_cfg
    prev_best, elite_gene_ids = gf.prev_best, gf.elite_gene_ids

    routes_spec = _build_routes_spec(pool, params_cfg, rng, elite_gene_ids, mix)

    # 渲染 route manifest（build_manifest_fields 结构化字段 + 轮级公共字段）
    manifest_paths = _render_route_manifests(RenderSpec(
        work_dir=work_dir, baseline_dir=baseline_dir, pool=pool, routes_spec=routes_spec,
        op_name=op_name, current_round=current_round, fusion_plan=fusion_plan, mode=mode,
        arch=arch, task_desc=task_desc, task_json=task_json, gpu_kernel_ref=gpu_kernel_ref,
        gpu_perf_csv=gpu_perf_csv, prev_best=prev_best,
    ))

    # 并行派发（TRITON_DISPATCH_PARALLEL 可覆盖为 ops wrapper 以获得钉卡）
    parallel = _dispatch_routes_parallel(work_dir, params_cfg, current_round, manifest_paths)
    if parallel.get("status") in ("timeout", "failed"):
        return parallel

    # 收集 + 语义质检（H1a）：拒收 route 整条剔除
    accepted, rejected, any_timeout = _collect_and_validate(work_dir, routes_spec, parallel)

    # G6 记账：适应度更新 + tested combos（update_fitness 原地改池，返回值仅 log）
    _record_gene_pool(pool, accepted, current_round, work_dir)

    # H1 下沉：proposed_genes 合并（去重 + 范围校验，不做推理）
    merged_proposals = _merge_proposals(pool, accepted)
    save_json(work_dir / "gene_pool.json", pool)

    # 组装父级 round_result.json（与父会话路径格式一致，供 update_round_index 消费）
    parent_rr = _build_parent_round_result(ParentRRSpec(
        work_dir=work_dir, current_round=current_round, config=config, round_index=round_index,
        decision=decision, baseline_dir=baseline_dir, mix=mix, accepted=accepted,
        rejected=rejected, any_timeout=any_timeout, merged_proposals=merged_proposals,
    ))
    save_json(work_dir / "round_result.json", parent_rr)

    # 产物渲染：report.md 走 python 模板（④s）；叙述类走 H2 小模型（best-effort）
    _render_gf_artifacts(work_dir, current_round, params_cfg)

    return {"status": parent_rr["status"], "round_result": parent_rr, "direct_dispatch": True}


def update_round_index(
    op_dir: Path,
    round_result: dict[str, Any],
    active_algorithm: str | None = None,
) -> None:
    """Update round_index.json with completed round info.

    Uses ``active_algorithm`` as the fallback when the sub-agent result does not
    report an algorithm. This prevents a hard-coded "naive" default from causing
    algorithm drift when the active run uses mcts/gene-fusion.
    """
    round_index_path = op_dir / "round_index.json"
    round_index = load_json(round_index_path) if round_index_path.is_file() else []
    if not isinstance(round_index, list):
        round_index = []

    idx = round_result.get("round_index", 0)
    entry = next((r for r in round_index if r.get("round_index") == idx), None)
    if entry is None:
        entry = {
            "round_index": idx,
            "round_dir": f"opt-round-{idx}",
        }
        round_index.append(entry)

    entry.update({
        "algorithm": round_result.get("algorithm") or active_algorithm or "naive",
        "direction": round_result.get("direction", ""),
        "hypothesis": round_result.get("hypothesis", ""),
        "effective_metric_source": round_result.get("effective_metric_source", "kernel"),
        "status": round_result.get("status", "failed"),
        "best_speedup": round_result.get("best_speedup", 0.0),
        "round_strategy": round_result.get("round_strategy", "exploration"),
    })

    # Optional fields enriched by the sub-agent; preserve existing values if absent.
    optional_fields = [
        "evidence_sources",
        "analysis_policy",
        "direction_yield",
        "yield_reason",
        "absolute_gain_vs_baseline",
        "baseline_dir",
        "design_summary",
        "iter_count",
        "opt_iter_count",
        "key_fixes",
        "bottlenecks_observed",
        "parent_round_journal",
    ]
    for key in optional_fields:
        if key in round_result:
            entry[key] = round_result[key]

    save_json(round_index_path, round_index)


@dataclass
class StopCheckArgs:
    """CLI args for the check_stop_decision.py subprocess."""

    op_dir: Path
    current_round: int
    best_speedup: float
    target_speedup: float
    max_rounds: int
    algorithm_recommends_stop: bool = False


def check_stop_decision(args: StopCheckArgs) -> dict[str, Any]:
    """Run check_stop_decision.py."""
    cmd = [
        sys.executable,
        str(SCRIPT_DIR / "check_stop_decision.py"),
        "--op-dir", str(args.op_dir),
        "--current-round", str(args.current_round),
        "--best-speedup", str(args.best_speedup),
        "--target-speedup", str(args.target_speedup),
        "--max-rounds", str(args.max_rounds),
    ]
    if args.algorithm_recommends_stop:
        cmd.append("--algorithm-recommends-stop")
    try:
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True)
        return json.loads(output)
    except (subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        return {"can_stop": False, "reason": str(exc)}


def count_non_idle_rounds(round_index: list[dict[str, Any]]) -> int:
    return sum(1 for r in round_index if r.get("status") != "skipped_idle")


def build_lineage_summary(
    round_index: list[dict[str, Any]],
    target_round_dir: str,
) -> list[dict[str, Any]]:
    """Build a root-to-leaf lineage summary for the target round."""
    by_dir = {entry.get("round_dir"): entry for entry in round_index if entry.get("round_dir")}
    lineage: list[dict[str, Any]] = []
    visited: set[str] = set()
    current_dir = target_round_dir

    while current_dir and current_dir not in visited:
        visited.add(current_dir)
        entry = by_dir.get(current_dir)
        if entry is None:
            break
        lineage_entry: dict[str, Any] = {
            "round_index": entry.get("round_index"),
            "round_dir": current_dir,
            "direction": entry.get("direction"),
            "best_speedup": entry.get("best_speedup"),
            "direction_yield": entry.get("direction_yield"),
            "hypothesis": entry.get("hypothesis"),
            "parent_round_dir": entry.get("baseline_dir"),
        }
        # Enrich the summary with design/iteration metadata when available.
        for key in (
            "design_summary",
            "iter_count",
            "opt_iter_count",
            "key_fixes",
            "bottlenecks_observed",
            "outcome",
        ):
            if key in entry:
                lineage_entry[key] = entry[key]
        lineage.append(lineage_entry)
        current_dir = entry.get("baseline_dir") or ""

    lineage.reverse()
    return lineage


def resolve_baseline(
    op_dir: Path,
    decision: RoundDecision,
    round_index: list[dict[str, Any]],
    op_name: str,
) -> Path | None:
    """Resolve the baseline directory from a RoundDecision.

    Returns the path to the baseline generated code, or None if the next round
    should start without a baseline. If the strategy-selected parent round has
    no code (e.g., a virtual MCTS node), fall back to the global baseline.
    """
    baseline = decision.baseline
    if baseline.mode == "none":
        selected_dir = ""
    elif baseline.mode == "single":
        selected_dir = baseline.round_dirs[0] if baseline.round_dirs else ""
    else:
        selected_dir = ""
        for round_dir_name in baseline.round_dirs:
            if not round_dir_name:
                continue
            candidate = op_dir / round_dir_name / f"{op_name}_generated.py"
            if candidate.is_file():
                return candidate

    if selected_dir:
        candidate = op_dir / selected_dir / f"{op_name}_generated.py"
        if candidate.is_file():
            return candidate

    # Fallback to the immutable global baseline (user-provided reference code).
    global_baseline_candidate = op_dir / "global_baseline" / f"{op_name}_generated.py"
    if global_baseline_candidate.is_file():
        return global_baseline_candidate
    return None


@dataclass
class TransitionCmdSpec:
    """Inputs for building the transition_next_round.py command line."""

    op_dir: Path
    current_round: int
    decision: RoundDecision
    algorithm: str
    algorithm_params: dict[str, Any]
    algorithm_metadata: dict[str, Any]
    global_baseline_dir: str | None
    global_baseline_speedup: float


def _build_transition_cmd(spec: TransitionCmdSpec) -> list[str]:
    """Build the transition_next_round.py command line."""
    op_dir = spec.op_dir
    current_round = spec.current_round
    decision = spec.decision
    algorithm = spec.algorithm
    algorithm_params = spec.algorithm_params
    algorithm_metadata = spec.algorithm_metadata
    global_baseline_dir = spec.global_baseline_dir
    global_baseline_speedup = spec.global_baseline_speedup
    cmd = [
        sys.executable,
        str(SCRIPT_DIR / "transition_next_round.py"),
        "--op-dir", str(op_dir),
        "--current-round", str(current_round),
        "--next-round-strategy", decision.round_strategy or "exploration",
        "--next-analysis-policy", decision.analysis_policy or "pattern_entry",
        "--next-hypothesis", decision.hypothesis or "",
        "--next-direction", decision.direction or "",
        "--next-evidence-sources", json.dumps(decision.evidence_sources, ensure_ascii=False),
        "--strategy-name", algorithm,
        "--strategy-params", json.dumps(algorithm_params, ensure_ascii=False),
        "--algorithm", algorithm,
        "--algorithm-metadata", json.dumps(algorithm_metadata, ensure_ascii=False),
        "--current-success-criteria", "speedup_vs_baseline >= target",
        "--current-key-learnings", "",
        "--global-baseline-dir", global_baseline_dir or "global_baseline",
        "--global-baseline-speedup", str(global_baseline_speedup),
    ]
    baseline = decision.baseline
    if baseline.mode == "single" and baseline.round_dirs:
        cmd.extend(["--baseline-dir", baseline.round_dirs[0]])
    elif baseline.mode == "multiple":
        cmd.extend(["--baseline-dirs", json.dumps(baseline.round_dirs, ensure_ascii=False)])
        if baseline.combination_rule:
            cmd.extend(["--combination-rule", baseline.combination_rule])
    return cmd


@dataclass
class PrepareNextRoundSpec:
    """Inputs for preparing the next round directory via transition_next_round.py."""

    op_dir: Path
    current_round: int
    decision: RoundDecision
    algorithm: str
    config: dict[str, Any]
    global_baseline_dir: str | None
    global_baseline_speedup: float


def prepare_next_round(spec: PrepareNextRoundSpec) -> dict[str, Any]:
    """Prepare the next round directory using transition_next_round.py."""
    op_dir = spec.op_dir
    current_round = spec.current_round
    decision = spec.decision
    algorithm = spec.algorithm
    config = spec.config
    global_baseline_dir = spec.global_baseline_dir
    global_baseline_speedup = spec.global_baseline_speedup
    switch_marker = decision.switch_marker
    algorithm_metadata = dict(decision.metadata or {})
    algorithm_params = get_algorithm_params(config, algorithm)

    cmd = _build_transition_cmd(TransitionCmdSpec(
        op_dir=op_dir, current_round=current_round, decision=decision, algorithm=algorithm,
        algorithm_params=algorithm_params, algorithm_metadata=algorithm_metadata,
        global_baseline_dir=global_baseline_dir, global_baseline_speedup=global_baseline_speedup,
    ))

    if switch_marker is not None:
        cmd.extend([
            "--switch-marker",
            json.dumps({
                "reason": switch_marker.reason,
                "previous_direction": switch_marker.previous_direction,
                "new_direction": switch_marker.new_direction,
            }, ensure_ascii=False),
        ])

    output = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True)
    return json.loads(output)


def _build_experience_section(
    op_name: str,
    best_round_entry: dict[str, Any] | None,
    operator_experience_path: Path,
) -> str:
    """Build the operator experience section for the template."""
    heading = f"## Experience: {op_name}"
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    best_round = best_round_entry.get("round_index") if best_round_entry else None
    best_speedup = best_round_entry.get("best_speedup") if best_round_entry else None
    target_reached = best_round_entry.get("target_reached") if best_round_entry else None
    final_code = (
        best_round_entry.get("artifacts", {}).get("generated_code")
        if best_round_entry
        else None
    )
    lines = [
        heading,
        "",
        f"- **Updated**: {timestamp}",
        f"- **Best round**: {best_round}",
        f"- **Best speedup**: {best_speedup}",
        f"- **Target reached**: {target_reached}",
    ]
    if final_code:
        lines.append(f"- **Final code**: `{final_code}`")
    if operator_experience_path.is_file():
        exp_text = operator_experience_path.read_text(encoding="utf-8").strip()
        if exp_text:
            lines.extend(["", "### Operator experience", "", exp_text])
    return "\n".join(lines) + "\n\n"


def _update_global_template(
    cwd: Path,
    op_name: str,
    category: str | None,
    best_round_entry: dict[str, Any] | None,
    operator_experience_path: Path,
) -> Path | None:
    """Append or replace the operator-specific experience in the project template.

    The project template lives at ``.claude/template/{category}.md`` and is
    copied per project by ``init.sh``. Updates only affect the current project
    unless manually synced across projects.
    """
    category = category or "general"
    template_dir = cwd / ".claude" / "template"
    template_dir.mkdir(parents=True, exist_ok=True)
    template_path = template_dir / f"{category}.md"

    heading = f"## Experience: {op_name}"
    section = _build_experience_section(op_name, best_round_entry, operator_experience_path)

    if template_path.is_file():
        content = template_path.read_text(encoding="utf-8")
    else:
        content = f"# {category.capitalize()} operator optimization experience\n\n"

    # Replace an existing section for the same operator, or append if not present.
    idx = content.find(f"\n{heading}")
    if idx == -1:
        idx = content.find(heading)
    if idx != -1:
        next_heading = content.find("\n## ", idx + 1)
        if next_heading == -1:
            content = content[:idx] + section
        else:
            content = content[:idx] + section + content[next_heading + 1:]
    else:
        content = content.rstrip() + "\n\n" + section

    template_path.write_text(content, encoding="utf-8")
    return template_path


@dataclass
class OrchestratorConfig:
    """Immutable orchestrator run configuration (CLI + strategy inputs)."""

    cwd: Path
    op_name: str
    mode: str
    task_desc: Path
    task_json: Path | None
    gpu_kernel_ref: Path | None
    gpu_perf_csv: Path | None
    timeout: int = 7200
    op_category: str | None = None
    arch: str = "ascend910b1"
    algorithm: str | None = None
    run_tag: str = "default"
    migrate_legacy: str | None = None
    detect_legacy: bool = False


def _handle_detect_legacy(cfg: OrchestratorConfig, discovered: set[str]) -> dict[str, Any] | None:
    """Handle --detect-legacy early exit; returns None if not requested."""
    if not cfg.detect_legacy:
        return None
    legacy = _find_legacy_workspace(cfg.cwd, cfg.op_name)
    if legacy is None:
        sys.stdout.write(json.dumps({"type": "none"}, indent=2, ensure_ascii=False) + "\n")
        return {"_exit_code": 0}
    legacy_op_dir, legacy_state = legacy
    inferred = _infer_algorithm_from_legacy(legacy_state, legacy_op_dir, discovered)
    report = _build_legacy_report(cfg.op_name, legacy_op_dir, legacy_state, inferred)
    sys.stdout.write(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    return {"_exit_code": 0}


def _resolve_from_existing_state(
    cfg: OrchestratorConfig,
    discovered: set[str],
    existing_state_algorithms: dict[str, Path],
    algorithm: str | None,
) -> str | None:
    """Resolve the algorithm from existing state files, or validate the CLI choice."""
    if algorithm is None:
        if len(existing_state_algorithms) == 1:
            new_state_algorithm = next(iter(existing_state_algorithms.keys()))
            if new_state_algorithm not in discovered:
                raise ValueError(
                    f"Saved algorithm '{new_state_algorithm}' has no strategy. "
                    f"Available: {sorted(discovered)}"
                )
            return new_state_algorithm
        if len(existing_state_algorithms) > 1:
            algos = sorted(existing_state_algorithms.keys())
            raise ValueError(
                f"Multiple existing workspaces found for '{cfg.op_name}': {algos}. "
                f"Please specify --algorithm or --migrate-legacy."
            )
        return None
    for existing_algo, existing_path in existing_state_algorithms.items():
        if existing_algo != algorithm:
            raise ValueError(
                f"Existing workspace uses algorithm '{existing_algo}' "
                f"({existing_path.name}). Conflicts with --algorithm {algorithm}."
            )
    return algorithm


def _resolve_legacy_workspace(
    cfg: OrchestratorConfig,
    discovered: set[str],
    existing_state_algorithms: dict[str, Path],
    algorithm: str | None,
) -> tuple[str | None, tuple | None] | dict[str, Any]:
    """Infer the algorithm from a legacy workspace; returns (algorithm, legacy) or exit dict."""
    if existing_state_algorithms:
        return algorithm, None
    legacy = _find_legacy_workspace(cfg.cwd, cfg.op_name)
    if legacy is None:
        return algorithm, None
    legacy_op_dir, legacy_state = legacy
    inferred = _infer_algorithm_from_legacy(legacy_state, legacy_op_dir, discovered)
    if not cfg.migrate_legacy:
        report = _build_legacy_report(cfg.op_name, legacy_op_dir, legacy_state, inferred)
        sys.stderr.write(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
        return {"_exit_code": 3}
    algorithm = cfg.migrate_legacy
    if inferred and algorithm != inferred:
        logger.warning(
            "WARN: requested migration algorithm '%s' differs from "
            "inferred '%s'. Using requested algorithm.",
            algorithm, inferred,
        )
    return algorithm, legacy


def _resolve_algorithm(
    cfg: OrchestratorConfig,
    config: dict[str, Any],
    discovered: set[str],
) -> tuple[str | None, tuple | None] | dict[str, Any]:
    """Resolve the active algorithm from CLI/state/legacy/config; returns
    ``(algorithm, legacy)`` or an ``_exit_code`` dict for early exits.
    """
    algorithm = cfg.algorithm

    early = _handle_detect_legacy(cfg, discovered)
    if early is not None:
        return early

    if algorithm is not None and algorithm not in discovered:
        raise ValueError(
            f"Algorithm '{algorithm}' not discovered. Available: {sorted(discovered)}"
        )

    existing_state_algorithms = _list_new_state_algorithms(
        cfg.cwd, cfg.op_name, cfg.run_tag
    )
    algorithm = _resolve_from_existing_state(cfg, discovered, existing_state_algorithms, algorithm)

    resolved = _resolve_legacy_workspace(cfg, discovered, existing_state_algorithms, algorithm)
    if isinstance(resolved, dict):
        return resolved
    algorithm, legacy = resolved

    if algorithm is None:
        algorithm = select_algorithm(config, None)

    if algorithm is None:
        raise ValueError(
            "No active algorithm selected. In the main Claude Code agent use "
            "AskUserQuestion; when running this script directly pass --algorithm."
        )

    return algorithm, legacy


def _init_workspace_and_strategy(
    cfg: OrchestratorConfig,
    config: dict[str, Any],
    active_algorithm: str,
    legacy: tuple | None,
) -> tuple[Path, Path, Any, int]:
    """Build the workspace path, migrate legacy if needed, initialize state, and
    load the strategy; returns ``(op_dir, state_path, strategy, current_timeout)``.
    """
    op_dir = cfg.cwd / "triton_ascend_output" / f"{cfg.op_name}-{active_algorithm}-{cfg.run_tag}"
    state_path = cfg.cwd / ".triton-agent" / f"state-{op_dir.name}.json"

    if legacy is not None and not op_dir.exists():
        op_dir = _migrate_legacy_workspace(
            cfg.cwd, cfg.op_name, active_algorithm, cfg.run_tag, legacy
        )
        state_path = cfg.cwd / ".triton-agent" / f"state-{op_dir.name}.json"

    state: dict[str, Any] = {}
    if state_path.is_file():
        try:
            state = load_json(state_path)
        except ValueError:
            state = {}

    if not state_path.is_file() or not (op_dir / "round_index.json").is_file():
        init_workspace(cfg, op_dir, config, active_algorithm)
        state = load_json(state_path)

    state["algorithm"] = active_algorithm
    save_json(state_path, state)

    strategy = load_strategy_for_algorithm(config, active_algorithm)
    round_index_for_init: list[dict[str, Any]] = []
    if (op_dir / "round_index.json").is_file():
        try:
            round_index_for_init = load_json(op_dir / "round_index.json")
        except ValueError:
            pass
    if hasattr(strategy, "init_for_operator"):
        strategy.init_for_operator(op_dir, config, round_index_for_init)

    return op_dir, state_path, strategy, cfg.timeout


@dataclass
class StopReportSpec:
    """Inputs for building the final 'stopped' report."""

    op_dir: Path
    op_name: str
    op_category: str | None
    cwd: Path
    round_index: list[dict[str, Any]]
    target_speedup: float
    non_idle_count: int
    reason: str


def _build_stop_report(spec: StopReportSpec) -> dict[str, Any]:
    """Build the final 'stopped' report and copy the best code to ``{op}_final.py``."""
    best_entry = max(
        (r for r in spec.round_index if r.get("status") == "success"),
        key=lambda r: r.get("best_speedup", 0.0),
        default=None,
    )
    final_report = {
        "status": "stopped",
        "reason": spec.reason,
        "best_round": best_entry.get("round_index") if best_entry else None,
        "best_speedup": best_entry.get("best_speedup", 0.0) if best_entry else 0.0,
        "target_speedup": spec.target_speedup,
        "total_rounds": spec.non_idle_count,
    }
    if best_entry:
        src = spec.op_dir / best_entry["round_dir"] / f"{spec.op_name}_generated.py"
        dst = spec.op_dir / f"{spec.op_name}_final.py"
        shutil.copy2(src, dst)
        final_report["final_code"] = str(dst)
    _update_global_template(
        spec.cwd, spec.op_name, spec.op_category, best_entry,
        spec.op_dir / "operator_experience.md",
    )
    return final_report


@dataclass
class _RoundLoad:
    """Per-round context loaded at the top of the orchestrator loop."""

    state: dict[str, Any]
    current_round: int
    work_dir: Path
    summary: dict[str, Any]
    round_index: list[dict[str, Any]]
    baseline_dir: Path | None
    global_baseline_dir: Path
    global_baseline_speedup: float
    experience_file: Path
    lineage_summary: str
    decision_metadata: dict[str, Any]


def _read_round_index_and_baseline(
    op_dir: Path, current_round: int, summary: dict[str, Any],
) -> tuple[list[dict[str, Any]], Path | None]:
    """Read round_index.json and resolve the baseline directory."""
    baseline_dir_name = None
    round_index_path = op_dir / "round_index.json"
    round_index: list[dict[str, Any]] = []
    if round_index_path.is_file():
        try:
            round_index = load_json(round_index_path)
            entry = next(
                (r for r in round_index if r.get("round_index") == current_round), None
            )
            if entry:
                baseline_dir_name = entry.get("baseline_dir")
        except (ValueError, TypeError):
            pass
    if not baseline_dir_name:
        baseline_dir_name = summary.get("baseline_dir")
    baseline_dir = op_dir / baseline_dir_name if baseline_dir_name else None
    return round_index, baseline_dir


def _read_global_baseline_speedup(op_dir: Path) -> float:
    """Read the global baseline speedup from baseline_info.json."""
    baseline_info_path = op_dir / "global_baseline" / "baseline_info.json"
    if not baseline_info_path.is_file():
        return 1.0
    try:
        baseline_info = load_json(baseline_info_path)
        gbs = baseline_info.get("baseline_speedup", 1.0)
        if isinstance(gbs, (int, float)) and gbs > 0:
            return float(gbs)
    except (ValueError, TypeError):
        pass
    return 1.0


def _load_round_context(
    state_path: Path,
    op_dir: Path,
    active_algorithm: str,
) -> _RoundLoad:
    """Load per-round state, summary, baseline, and decision metadata."""
    state = load_json(state_path)
    current_round = state.get("current_round")
    work_dir = Path(state.get("work_dir"))
    summary = load_json(work_dir / "summary.json")
    _stage(f"round {current_round}: begin")

    round_index, baseline_dir = _read_round_index_and_baseline(op_dir, current_round, summary)
    global_baseline_dir = op_dir / "global_baseline"
    global_baseline_speedup = _read_global_baseline_speedup(op_dir)

    experience_file = op_dir / "operator_experience.md"
    lineage_summary = build_lineage_summary(round_index, f"opt-round-{current_round}")

    summary_algorithm = summary.get("algorithm")
    if summary_algorithm and summary_algorithm != active_algorithm:
        logger.warning(
            "WARN: summary.json algorithm (%s) differs from "
            "active algorithm (%s); using active algorithm.",
            summary_algorithm, active_algorithm,
        )
    decision_metadata: dict[str, Any] = {}
    for key in ("mcts_parent_id", "mcts_selection_path", "mcts_pending_expansion"):
        if key in summary:
            decision_metadata[key] = summary[key]

    return _RoundLoad(
        state=state,
        current_round=current_round,
        work_dir=work_dir,
        summary=summary,
        round_index=round_index,
        baseline_dir=baseline_dir,
        global_baseline_dir=global_baseline_dir,
        global_baseline_speedup=global_baseline_speedup,
        experience_file=experience_file,
        lineage_summary=lineage_summary,
        decision_metadata=decision_metadata,
    )


@dataclass
class DispatchRequest:
    """Inputs for dispatching a single round (H1 direct or manifest-based)."""

    op_dir: Path
    cfg: OrchestratorConfig
    config: dict[str, Any]
    strategy: Any
    active_algorithm: str
    ctx: _RoundLoad
    round_index_path: Path
    current_timeout: int


def _dispatch_manifest(req: DispatchRequest) -> dict[str, Any]:
    """Build the manifest and dispatch the round via dispatch_round.py."""
    cfg = req.cfg
    ctx = req.ctx
    current_round = ctx.current_round
    summary = ctx.summary
    manifest_path = build_manifest(ManifestSpec(
        op_dir=req.op_dir,
        op_name=cfg.op_name,
        round_index=current_round,
        baseline_dir=ctx.baseline_dir,
        algorithm=req.active_algorithm,
        round_strategy=summary.get("round_strategy", "exploration"),
        analysis_policy=summary.get("analysis_policy", "pattern_entry"),
        hypothesis=summary.get("hypothesis", ""),
        direction=summary.get("direction", ""),
        evidence_sources=summary.get("evidence_sources", []),
        mode=cfg.mode,
        task_desc=cfg.task_desc,
        task_json=cfg.task_json,
        gpu_kernel_ref=cfg.gpu_kernel_ref,
        gpu_perf_csv=cfg.gpu_perf_csv,
        config=req.config,
        arch=cfg.arch,
        lineage_summary=ctx.lineage_summary,
        experience_file=str(ctx.experience_file) if ctx.experience_file.is_file() else None,
        global_baseline_dir=ctx.global_baseline_dir,
        global_baseline_speedup=ctx.global_baseline_speedup,
        decision_metadata=ctx.decision_metadata,
    ))
    _stage(f"round {current_round}: dispatch start (timeout={req.current_timeout}s)")
    dispatch_result = dispatch_round(manifest_path, req.current_timeout)
    sub_pid = dispatch_result.get("pid")
    if sub_pid:
        logger.info("[orchestrator] Round %s sub-agent PID: %s", current_round, sub_pid)
        logger.info("[orchestrator] To kill manually: kill %s", sub_pid)
    _stage(f"round {current_round}: dispatch done status={dispatch_result['status']}")
    return dispatch_result


def _dispatch_worker(req: DispatchRequest) -> dict[str, Any]:
    """H1 direct dispatch (gene-fusion) or normal manifest-based dispatch."""
    cfg = req.cfg
    ctx = req.ctx
    current_round = ctx.current_round
    dispatch_result: dict[str, Any] | None = None
    if (
        req.active_algorithm == "gene-fusion"
        and current_round >= 2
        and os.environ.get("TRITON_GF_DIRECT_DISPATCH", "0") == "1"
    ):
        _stage(f"round {current_round}: H1 direct dispatch attempt")
        dispatch_result = dispatch_gene_fusion_direct(GfDirectSpec(
            op_dir=req.op_dir, op_name=cfg.op_name, current_round=current_round,
            baseline_dir=ctx.baseline_dir, config=req.config, strategy=req.strategy,
            round_index=(load_json(req.round_index_path) if req.round_index_path.is_file() else []),
            op_category=cfg.op_category, task_desc=cfg.task_desc, task_json=cfg.task_json,
            gpu_kernel_ref=cfg.gpu_kernel_ref, gpu_perf_csv=cfg.gpu_perf_csv,
            arch=cfg.arch, mode=cfg.mode,
        ))
        if dispatch_result.get("status") == "fallback":
            logger.info(
                "[orchestrator] H1 direct dispatch fallback: %s",
                dispatch_result.get("reason"),
            )
            dispatch_result = None

    if dispatch_result is None:
        dispatch_result = _dispatch_manifest(req)

    return dispatch_result


def _handle_timeout(spec: _LoopSpec, ctx: _RoundLoad, current_timeout: int) -> int:
    """Record a round timeout and double the worker timeout for the next round."""
    current_round = ctx.current_round
    new_timeout = min(current_timeout * 2, spec.max_worker_timeout)
    logger.info(
        "[orchestrator] Round %s timed out after %ss; "
        "increasing timeout to %ss for next round",
        current_round, current_timeout, new_timeout,
    )
    state = load_json(spec.state_path)
    state.setdefault("performance_history", []).append({
        "round": current_round,
        "speedup_vs_torch": 0.0,
        "target_reached": False,
        "timeout": True,
    })
    save_json(spec.state_path, state)
    if hasattr(spec.strategy, "record_round_result"):
        try:
            spec.strategy.record_round_result(
                {"round_index": current_round, "status": "timeout", "best_speedup": 0.0},
                ctx.work_dir,
                context={"op_dir": str(spec.op_dir), "current_round": current_round},
            )
        except Exception as exc:
            logger.warning("[orchestrator] Strategy record_round_result warning: %s", exc)
    return new_timeout


@dataclass
class SuccessCtx:
    """Inputs for handling a successfully dispatched round."""

    req: DispatchRequest
    round_result: dict[str, Any]
    state_path: Path
    target_speedup: float
    max_rounds: int
    cwd: Path
    op_name: str


@dataclass
class StopCheckSpec:
    """Inputs for the C1/C2 + strategy stop gate."""

    op_dir: Path
    op_name: str
    op_category: str | None
    cwd: Path
    round_index: list[dict[str, Any]]
    target_speedup: float
    non_idle_count: int
    best_speedup: float
    max_rounds: int
    current_round: int
    decision: Any
    c1: bool
    c2: bool


def _check_stop(sc: SuccessCtx, dc: DecisionCtx) -> dict[str, Any] | None:
    """Run the C1/C2 + strategy stop gate; returns a stop report or None."""
    spec = StopCheckSpec(
        op_dir=sc.req.op_dir, op_name=sc.op_name, op_category=sc.req.cfg.op_category,
        cwd=sc.cwd, round_index=dc.round_index, target_speedup=sc.target_speedup,
        non_idle_count=dc.non_idle_count, best_speedup=dc.best_speedup, max_rounds=sc.max_rounds,
        current_round=sc.req.ctx.current_round, decision=dc.decision, c1=dc.c1, c2=dc.c2,
    )
    if spec.decision.algorithm_recommends_stop:
        stop_check = check_stop_decision(StopCheckArgs(
            spec.op_dir, spec.current_round, spec.best_speedup, spec.target_speedup, spec.max_rounds,
            algorithm_recommends_stop=True,
        ))
        if stop_check.get("can_stop", False) or spec.c1 or spec.c2:
            return _build_stop_report(StopReportSpec(
                op_dir=spec.op_dir,
                op_name=spec.op_name,
                op_category=spec.op_category,
                cwd=spec.cwd,
                round_index=spec.round_index,
                target_speedup=spec.target_speedup,
                non_idle_count=spec.non_idle_count,
                reason=spec.decision.stop_reason or ("C1" if spec.c1 else "C2"),
            ))

    if spec.c1 or spec.c2:
        stop_check = check_stop_decision(StopCheckArgs(
            spec.op_dir, spec.current_round, spec.best_speedup, spec.target_speedup, spec.max_rounds
        ))
        if stop_check.get("can_stop", False):
            return _build_stop_report(StopReportSpec(
                op_dir=spec.op_dir,
                op_name=spec.op_name,
                op_category=spec.op_category,
                cwd=spec.cwd,
                round_index=spec.round_index,
                target_speedup=spec.target_speedup,
                non_idle_count=spec.non_idle_count,
                reason="C1" if spec.c1 else "C2",
            ))
    return None


def _fill_direction(
    strategy: Any,
    round_index: list[dict[str, Any]],
    op_category: str | None,
    current_policy: str,
    decision: RoundDecision,
) -> None:
    """Fill in the direction fields the strategy left empty."""
    if decision.direction is not None:
        return
    if strategy.capabilities.can_select_round:
        return
    if strategy.capabilities.can_propose_direction:
        import direction_selector as ds
        sel = ds.select_next_direction(
            round_index,
            op_category=op_category,
            current_policy=current_policy,
        )
        decision.direction = sel.direction
        decision.hypothesis = sel.hypothesis or decision.hypothesis
        decision.round_strategy = sel.strategy or decision.round_strategy
        decision.analysis_policy = sel.analysis_policy or decision.analysis_policy
        decision.evidence_sources = sel.evidence_sources or decision.evidence_sources
        if not decision.metadata:
            decision.metadata = sel.metadata
    else:
        decision.direction = "pattern: custom"


def _needs_effective_baseline(
    decision: RoundDecision, proposed_dir: str, concrete_file: Path | None,
) -> bool:
    """Return True when the resolved baseline should fall back to the effective dir."""
    return (
        decision.baseline.mode == "none"
        or not proposed_dir
        or concrete_file is None
        or not concrete_file.is_file()
    )


def _resolve_baseline(
    strategy: Any,
    round_index: list[dict[str, Any]],
    op_dir: Path,
    op_name: str,
    decision: RoundDecision,
) -> Path | None:
    """Select a baseline via strategy scoring, then resolve the concrete file."""
    if decision.baseline.mode == "none" and decision.direction:
        best_score = -1.0
        best_entry: dict[str, Any] | None = None
        for entry in round_index:
            if entry.get("status") != "success":
                continue
            score = strategy.score_baseline_for_direction(
                entry,
                target_direction=decision.direction,
                target_strategy=decision.round_strategy or "exploration",
                context={"op_dir": str(op_dir)},
            )
            if score > best_score:
                best_score = score
                best_entry = entry
        if best_entry:
            decision.baseline = BaselineProposal(
                mode="single", round_dirs=[best_entry["round_dir"]]
            )

    baseline_file = resolve_baseline(op_dir, decision, round_index, op_name)
    if baseline_file is None:
        return None
    baseline_dir = baseline_file.parent
    proposed_dir = decision.baseline.round_dirs[0] if decision.baseline.round_dirs else ""
    concrete_file = (
        op_dir / proposed_dir / f"{op_name}_generated.py"
        if proposed_dir
        else None
    )
    if _needs_effective_baseline(decision, proposed_dir, concrete_file):
        effective_dir = baseline_dir.relative_to(op_dir).as_posix()
        decision.baseline = BaselineProposal(mode="single", round_dirs=[effective_dir])
    return baseline_dir


@dataclass
class RecordSpec:
    """Inputs for recording a completed round."""

    op_dir: Path
    round_result: dict[str, Any]
    active_algorithm: str
    strategy: Any
    work_dir: Path
    current_round: int


def _record_round_result(spec: RecordSpec) -> None:
    """Update round_index and record the completed round in the strategy."""
    update_round_index(spec.op_dir, spec.round_result, spec.active_algorithm)
    _stage(f"round {spec.current_round}: round_index updated")
    if hasattr(spec.strategy, "record_round_result"):
        try:
            round_index = load_json(spec.op_dir / "round_index.json")
            current_entry = next(
                (r for r in round_index if r.get("round_index") == spec.current_round), None
            )
            if current_entry:
                spec.strategy.record_round_result(
                    current_entry,
                    spec.work_dir,
                    context={"op_dir": str(spec.op_dir), "current_round": spec.current_round},
                )
        except Exception as exc:
            logger.warning("[orchestrator] Strategy record_round_result warning: %s", exc)


def _finalize_round(
    sc: SuccessCtx,
    round_index: list[dict[str, Any]],
    decision: RoundDecision,
    best_speedup: float,
    baseline_dir: Path | None,
) -> None:
    """Update state and prepare the next round directory."""
    cfg = sc.req.cfg
    ctx = sc.req.ctx
    op_dir = sc.req.op_dir
    active_algorithm = sc.req.active_algorithm
    current_round = ctx.current_round
    state = load_json(sc.state_path)
    state.setdefault("performance_history", []).append({
        "round": current_round,
        "speedup_vs_torch": best_speedup,
        "target_reached": best_speedup >= sc.target_speedup,
    })
    state["direction_history"] = build_direction_history(round_index)
    state["algorithm"] = active_algorithm
    save_json(sc.state_path, state)
    _stage(f"round {current_round}: baseline resolved -> {baseline_dir}")

    _stage(f"round {current_round}: prepare_next_round start")
    prepare_next_round(PrepareNextRoundSpec(
        op_dir=op_dir, current_round=current_round, decision=decision, algorithm=active_algorithm,
        config=sc.req.config, global_baseline_dir="global_baseline",
        global_baseline_speedup=ctx.global_baseline_speedup,
    ))
    _stage(f"round {current_round}: transition done (next manifest ready)")


@dataclass
class DecisionCtx:
    """Stop conditions and the strategy's next-round decision."""

    decision: RoundDecision
    best_speedup: float
    round_index: list[dict[str, Any]]
    non_idle_count: int
    c1: bool
    c2: bool


def _get_decision(
    sc: SuccessCtx, op_dir: Path, strategy: Any, summary: dict[str, Any],
) -> DecisionCtx | dict[str, Any]:
    """Compute stop conditions and ask the strategy for the next decision."""
    cfg = sc.req.cfg
    current_round = sc.req.ctx.current_round
    best_speedup = sc.round_result.get("best_speedup", 0.0)
    round_index = load_json(op_dir / "round_index.json")
    non_idle_count = count_non_idle_rounds(round_index)
    c1 = best_speedup >= sc.target_speedup
    c2 = non_idle_count >= sc.max_rounds
    current_policy = summary.get("analysis_policy", "pattern_entry")
    try:
        decision = strategy.select_next_round(
            round_index,
            op_category=cfg.op_category,
            current_policy=current_policy,
            context={"op_dir": str(op_dir), "current_round": current_round},
        )
    except Exception as exc:
        return {
            "status": "failed",
            "reason": f"strategy.select_next_round failed: {exc}",
            "round": current_round,
        }
    return DecisionCtx(
        decision=decision,
        best_speedup=best_speedup,
        round_index=round_index,
        non_idle_count=non_idle_count,
        c1=c1,
        c2=c2,
    )


def _process_success_round(sc: SuccessCtx) -> dict[str, Any] | None:
    """Handle a successful round: record, check stop, resolve baseline, prepare next.

    Returns a final report dict to stop, or ``None`` to continue the loop.
    """
    req = sc.req
    cfg = req.cfg
    ctx = req.ctx
    op_dir = req.op_dir
    strategy = req.strategy
    active_algorithm = req.active_algorithm
    current_round = ctx.current_round
    summary = ctx.summary

    _record_round_result(RecordSpec(
        op_dir=op_dir,
        round_result=sc.round_result,
        active_algorithm=active_algorithm,
        strategy=strategy,
        work_dir=ctx.work_dir,
        current_round=current_round,
    ))

    dc = _get_decision(sc, op_dir, strategy, summary)
    if isinstance(dc, dict):
        return dc
    decision = dc.decision
    best_speedup = dc.best_speedup
    round_index = dc.round_index
    non_idle_count = dc.non_idle_count
    c1 = dc.c1
    c2 = dc.c2

    _stage(f"round {current_round}: strategy decision done -> {decision.round_strategy}/{decision.direction or ''}")
    stop_report = _check_stop(sc, dc)
    if stop_report is not None:
        return stop_report

    _fill_direction(strategy, round_index, cfg.op_category, summary.get("analysis_policy", "pattern_entry"), decision)
    baseline_dir = _resolve_baseline(strategy, round_index, op_dir, sc.op_name, decision)
    _finalize_round(sc, round_index, decision, best_speedup, baseline_dir)
    return None


@dataclass
class _LoopSpec:
    """Immutable inputs for the orchestrator main loop."""

    cfg: OrchestratorConfig
    config: dict[str, Any]
    strategy: Any
    active_algorithm: str
    op_dir: Path
    state_path: Path
    current_timeout: int
    max_worker_timeout: int
    target_speedup: float
    max_rounds: int


def _run_loop(spec: _LoopSpec) -> dict[str, Any]:
    """Run the orchestration loop until a stop/fail report is produced."""
    cfg = spec.cfg
    while True:
        ctx = _load_round_context(spec.state_path, spec.op_dir, spec.active_algorithm)
        current_round = ctx.current_round
        work_dir = ctx.work_dir
        round_index_path = spec.op_dir / "round_index.json"

        dispatch_req = DispatchRequest(
            op_dir=spec.op_dir,
            cfg=cfg,
            config=spec.config,
            strategy=spec.strategy,
            active_algorithm=spec.active_algorithm,
            ctx=ctx,
            round_index_path=round_index_path,
            current_timeout=spec.current_timeout,
        )
        dispatch_result = _dispatch_worker(dispatch_req)

        if dispatch_result["status"] == "timeout":
            spec.current_timeout = _handle_timeout(spec, ctx, spec.current_timeout)
        elif dispatch_result["status"] != "success":
            return {
                "status": "failed",
                "reason": f"dispatch_round failed: {dispatch_result.get('stderr', '')}",
                "round": current_round,
            }
        else:
            result = _process_success_round(SuccessCtx(
                req=dispatch_req,
                round_result=dispatch_result["round_result"],
                state_path=spec.state_path,
                target_speedup=spec.target_speedup,
                max_rounds=spec.max_rounds,
                cwd=cfg.cwd,
                op_name=cfg.op_name,
            ))
            if result is not None:
                return result


def run_orchestrator(cfg: OrchestratorConfig) -> dict[str, Any]:
    """Main orchestration loop."""
    config = read_config(cfg.cwd)
    target_speedup = config.get("target_speedup", 5)
    max_rounds = config.get("max_rounds", 10)
    max_worker_timeout = config.get("max_worker_timeout", 28800)

    discovered = _discovered_algorithm_names()
    resolved = _resolve_algorithm(cfg, config, discovered)
    if isinstance(resolved, dict):
        return resolved
    active_algorithm, legacy = resolved
    op_dir, state_path, strategy, current_timeout = _init_workspace_and_strategy(
        cfg, config, active_algorithm, legacy
    )

    spec = _LoopSpec(
        cfg=cfg,
        config=config,
        strategy=strategy,
        active_algorithm=active_algorithm,
        op_dir=op_dir,
        state_path=state_path,
        current_timeout=current_timeout,
        max_worker_timeout=max_worker_timeout,
        target_speedup=target_speedup,
        max_rounds=max_rounds,
    )
    return _run_loop(spec)


def _parse_args() -> argparse.Namespace:
    """Parse orchestrator CLI arguments."""
    parser = argparse.ArgumentParser(description="Triton Auto Evolve Orchestrator Loop")
    parser.add_argument("--op-name", required=True, help="Operator name")
    parser.add_argument("--algorithm", default=None,
                        help="Optimization algorithm (required when multiple algorithms are enabled). "
                             "Must match a discovered strategy name.")
    parser.add_argument("--run-tag", default="default",
                        help="Run tag to isolate multiple runs of the same operator/algorithm (default: default)")
    parser.add_argument("--mode", default="A", choices=["A", "B"], help="Input mode")
    parser.add_argument("--task-desc", required=True, help="Path to task description .py file")
    parser.add_argument("--task-json", default=None, help="Path to task JSON file (multi-case mode)")
    parser.add_argument("--gpu-kernel-ref", default=None, help="Path to GPU kernel reference file")
    parser.add_argument("--gpu-perf-csv", default=None, help="Path to GPU performance CSV")
    parser.add_argument("--timeout", type=int, default=7200, help="Initial sub CLI timeout in seconds")
    parser.add_argument(
        "--op-category", default=None,
        help="Operator category (elementwise, matmul, normalization, ...)",
    )
    parser.add_argument("--arch", default="ascend910b1", help="Target Ascend architecture (e.g. ascend910b3)")
    parser.add_argument(
        "--migrate-legacy",
        default=None,
        metavar="ALGORITHM",
        help=(
            "Migrate a legacy workspace (triton_ascend_output/{op_name}/) to the new "
            "naming and continue with ALGORITHM"
        ),
    )
    parser.add_argument(
        "--detect-legacy",
        action="store_true",
        help="Detect legacy workspace, print JSON report, and exit without modifying anything",
    )
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = _parse_args()

    cwd = Path.cwd()
    cfg = OrchestratorConfig(
        cwd=cwd,
        op_name=args.op_name,
        mode=args.mode,
        task_desc=Path(args.task_desc).expanduser().resolve(),
        task_json=Path(args.task_json).expanduser().resolve() if args.task_json else None,
        gpu_kernel_ref=Path(args.gpu_kernel_ref).expanduser().resolve() if args.gpu_kernel_ref else None,
        gpu_perf_csv=Path(args.gpu_perf_csv).expanduser().resolve() if args.gpu_perf_csv else None,
        timeout=args.timeout,
        op_category=args.op_category,
        arch=args.arch,
        algorithm=args.algorithm,
        run_tag=args.run_tag,
        migrate_legacy=args.migrate_legacy,
        detect_legacy=args.detect_legacy,
    )
    result = run_orchestrator(cfg)
    exit_code = result.pop("_exit_code", None)
    if exit_code is not None:
        return exit_code
    sys.stdout.write(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    return 0 if result.get("status") == "stopped" else 1


if __name__ == "__main__":
    sys.exit(main())
