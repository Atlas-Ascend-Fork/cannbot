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
"""Stop Decision Validation Script

Agent MUST run this script BEFORE outputting any "stop" or "final report" decision.
The script objectively verifies whether stop conditions (C1/C2) are met and
whether the active strategy recommends stopping, preventing subjective early
termination of the optimization loop.

Usage:
    python3 check_stop_decision.py \
        --op-dir triton_ascend_output/{op_name}-{algorithm}-{run_tag} \
        --current-round {N} \
        [--best-speedup X] \
        [--target-speedup Y] \
        [--max-rounds M] \
        [--algorithm-recommends-stop]

Output (JSON):
    {
        "can_stop": false,
        "reason": "no stop condition met",
        "conditions_met": [],
        "checks": { ... }
    }

Rules:
    - Agent MUST NOT stop when can_stop is false
    - Agent MUST NOT output a final summary report when can_stop is false
    - Agent MUST NOT ask the user for confirmation to continue when can_stop is false
"""

import argparse
import json
import math
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from workspace_utils import read_round_summaries


def _read_rounds_from_summaries(op_dir: Path) -> list[dict[str, Any]]:
    """Read summary.json from each opt-round-* directory.

    Sorts directories by numeric round index and parses directories
    like opt-round-9-switch correctly (kept for backwards compatibility).
    """
    rounds = []
    for data in read_round_summaries(op_dir):
        if data.get("success", False):
            status = "success"
        elif data.get("failure_phase"):
            status = "active"
        else:
            status = "unknown"

        rounds.append({
            "round_index": data.get("round_index", 0),
            "round_dir": data["round_dir"],
            "best_speedup": data["best_speedup"],
            "round_strategy": data.get("round_strategy", ""),
            "direction": data.get("direction", ""),
            "analysis_policy": data.get("analysis_policy", "pattern_entry"),
            "status": status,
            "improvement_made": data.get("optimized", False),
            "phase4_entered": data.get("phase4_entered", False),
        })
    return rounds


def _evaluate_c1(effective_best_speedup: float, target_speedup: float) -> tuple[bool, str]:
    """Evaluate C1 (target reached)."""
    if isinstance(effective_best_speedup, (int, float)) and isinstance(target_speedup, (int, float)):
        if math.isfinite(effective_best_speedup) and target_speedup > 0:
            c1_met = effective_best_speedup >= target_speedup
            return c1_met, (
                f"best_speedup({effective_best_speedup:.4f}) "
                f"{'>=' if c1_met else '<'}"
                f" target_speedup({target_speedup})"
            )
        return False, f"invalid values: best_speedup={effective_best_speedup}, target_speedup={target_speedup}"
    return False, f"non-numeric values: best_speedup={effective_best_speedup}, target_speedup={target_speedup}"


def _read_effective_best_speedup(
    op_dir: Path, cli_best_speedup: float, result: dict[str, Any],
) -> tuple[float, list[dict[str, Any]]]:
    """Read round data and compute the effective best speedup."""
    all_rounds = _read_rounds_from_summaries(op_dir)
    non_idle_entries = [r for r in all_rounds if r.get("best_speedup", 0) > 0 or r.get("phase4_entered", False)]
    actual_best_speedup = max((r.get("best_speedup", 0) for r in non_idle_entries), default=0)
    if cli_best_speedup > 0 and actual_best_speedup > 0 and abs(cli_best_speedup - actual_best_speedup) > 0.001:
        result.setdefault("warnings", []).append(
            f"CLI best_speedup({cli_best_speedup:.4f}) differs from actual max "
            f"from summary.json({actual_best_speedup:.4f}). Using actual value."
        )
    return max(cli_best_speedup, actual_best_speedup), non_idle_entries


@dataclass
class StopChecks:
    """Stop condition evaluation results."""

    c1_met: bool
    c1_detail: str
    c2_met: bool
    c2_detail: str
    strategy_stop_met: bool
    strategy_detail: str


def _assemble_result(result: dict[str, Any], checks: StopChecks) -> None:
    """Assemble the stop decision result."""
    conditions_met: list[str] = []
    if checks.c1_met:
        conditions_met.append("C1")
    if checks.c2_met:
        conditions_met.append("C2")
    if checks.strategy_stop_met:
        conditions_met.append("strategy_stop")

    result["conditions_met"] = conditions_met
    result["checks"] = {
        "C1": {"met": checks.c1_met, "detail": checks.c1_detail},
        "C2": {"met": checks.c2_met, "detail": checks.c2_detail},
        "strategy_stop": {"met": checks.strategy_stop_met, "detail": checks.strategy_detail},
    }

    if checks.c1_met:
        result["can_stop"] = True
        result["reason"] = "C1: target_reached"
    elif checks.c2_met:
        result["can_stop"] = True
        result["reason"] = "C2: max_rounds_reached"
    elif checks.strategy_stop_met:
        result["can_stop"] = True
        result["reason"] = "strategy_recommends_stop"
    else:
        result["reason"] = "no stop condition met (C1/C2 not met)"


@dataclass
class StopDecisionSpec:
    """Inputs for the C1/C2 stop-condition evaluation."""

    op_dir: Path | str
    current_round: int = 0
    best_speedup: float = 0.0
    target_speedup: float = 1.0
    max_rounds: int = 5
    algorithm_recommends_stop: bool = False


def check_stop_decision(spec: StopDecisionSpec) -> dict[str, Any]:
    """Objectively evaluate C1/C2 stop conditions from summary.json (not round_index.json)."""
    op_dir = spec.op_dir
    current_round = spec.current_round
    best_speedup = spec.best_speedup
    target_speedup = spec.target_speedup
    max_rounds = spec.max_rounds
    algorithm_recommends_stop = spec.algorithm_recommends_stop
    if isinstance(op_dir, str):
        op_dir = Path(op_dir)
    result: dict[str, Any] = {
        "can_stop": False,
        "reason": "",
        "conditions_met": [],
        "checks": {},
    }

    # ── Read round data from summary.json (authoritative source) ──
    effective_best_speedup, non_idle_entries = _read_effective_best_speedup(op_dir, best_speedup, result)

    c1_met, c1_detail = _evaluate_c1(effective_best_speedup, target_speedup)
    non_idle_count = len(non_idle_entries)
    c2_met = non_idle_count >= max_rounds
    c2_detail = f"non-idle rounds({non_idle_count}) {'>=' if c2_met else '<'} max_rounds({max_rounds})"
    strategy_stop_met = algorithm_recommends_stop
    strategy_detail = f"algorithm_recommends_stop={algorithm_recommends_stop}"

    # ── Assemble result ──
    _assemble_result(result, StopChecks(
        c1_met=c1_met, c1_detail=c1_detail, c2_met=c2_met, c2_detail=c2_detail,
        strategy_stop_met=strategy_stop_met, strategy_detail=strategy_detail,
    ))

    # ── Write transition lock on stop decision (releases Phase 7 gate) ──
    if result["can_stop"]:
        lock = {
            "action": "stop",
            "transition_at": datetime.now(timezone.utc).isoformat(),
            "reason": result["reason"],
            "from_round": current_round,
            "state_after": {
                "current_round": current_round,
                "last_phase": 7,
                "status": "completed" if current_round > 0 else "active",
            },
            "conditions_met": result["conditions_met"],
        }
        lock_path = op_dir / ".transition_lock.json"
        try:
            lock_path.write_text(
                json.dumps(lock, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8"
            )
        except OSError as exc:
            result.setdefault("warnings", []).append(f"failed to write stop lock: {exc}")

    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate stop decision for Agent Loop (must run before any stop output)"
    )
    parser.add_argument("--op-dir", required=True, help="Operator directory path")
    parser.add_argument("--current-round", type=int, default=0, help="Current round number")
    parser.add_argument("--best-speedup", type=float, default=0.0, help="Best speedup achieved")
    parser.add_argument("--target-speedup", type=float, default=1.0, help="Target speedup")
    parser.add_argument("--max-rounds", type=int, default=5, help="Maximum rounds (config.json max_rounds)")
    parser.add_argument("--algorithm-recommends-stop", action="store_true",
                        help="The active strategy recommends stopping")
    args = parser.parse_args()

    op_dir = Path(args.op_dir).expanduser().resolve()
    if not op_dir.is_dir():
        sys.stdout.write(json.dumps({
            "can_stop": False,
            "reason": f"operator directory not found: {op_dir}",
            "conditions_met": [],
            "checks": {},
        }) + "\n")
        return 1

    result = check_stop_decision(StopDecisionSpec(
        op_dir=op_dir,
        current_round=args.current_round,
        best_speedup=args.best_speedup,
        target_speedup=args.target_speedup,
        max_rounds=args.max_rounds,
        algorithm_recommends_stop=args.algorithm_recommends_stop,
    ))
    sys.stdout.write(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    return 0 if result["can_stop"] else 1


if __name__ == "__main__":
    sys.exit(main())
