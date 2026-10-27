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
"""Gene-fusion strategy.

The gene-fusion algorithm delegates the bulk of its work to the sub-agent:
- Round 1 performs B1 compute-atom decomposition + B2 fusion analysis and
  spawns parallel routes internally.
- Round 2+ evolves the gene pool internally.

This Orchestrator-side strategy is therefore thin: it only needs to propose a
baseline (global baseline for round 1, best historical round afterwards) and
classify the yield of each completed round.
"""

from pathlib import Path
from typing import Any

import direction_selector as ds
from direction_selector import DirectionYieldContext
from ..base import (
    BaselineProposal,
    RoundDecision,
    Strategy,
    StrategyCapabilities,
)


def adapt_route_mix(
    round_index: list[dict[str, Any]],
    params: dict[str, Any],
) -> dict[str, Any]:
    """G4 混合比自适应：按最近轮次 best_speedup 走势调节 elite/exploration 路数（需 ≥3 有效轮）。"""
    max_routes = int(params.get("max_routes", 3))
    elite = int(params.get("elite_count", 1))
    exploration = int(params.get("exploration_count", 1))
    crossover = 1
    mix: dict[str, Any] = {
        "elite_count": elite,
        "crossover_count": crossover,
        "exploration_count": exploration,
        "adjust_reason": None,
    }

    def _scoreable(r: dict[str, Any]) -> bool:
        return r.get("status") != "failed" and float(r.get("best_speedup", 0.0) or 0.0) > 0

    scored = [
        float(r.get("best_speedup", 0.0) or 0.0)
        for r in sorted(round_index, key=lambda r: r.get("round_index", 0))
        if _scoreable(r)
    ]
    if len(scored) < 3:
        return mix
    recent = list(zip(scored[-3:], scored[-2:]))  # 末尾两个相邻差分
    if all(b > a for a, b in recent):  # 连续提升：收敛期集中精英
        if exploration > 0:
            elite += 1
            exploration -= 1
            reason = "consecutive improvement x2: elite+1 exploration-1"
        else:
            return mix
    elif all(b <= a for a, b in recent):  # 连续停滞：加码探索
        if elite > 0:
            exploration += 1
            elite -= 1
            reason = "consecutive stagnation x2: exploration+1 elite-1"
        else:
            return mix
    else:
        return mix  # 走势异向，不调节
    if elite + crossover + exploration > max_routes:
        return mix
    mix.update(elite_count=elite, exploration_count=exploration, adjust_reason=reason)
    return mix


class GeneFusionStrategy(Strategy):
    """Strategy wrapper for the gene-fusion algorithm."""

    name = "gene-fusion"
    capabilities = StrategyCapabilities(
        can_propose_direction=True,
        can_propose_baseline=True,
        can_propose_multiple_baselines=False,
        can_decide_switch_internally=False,
        can_recommend_stop=False,
        needs_persistent_state=False,
        can_select_round=False,
    )
    state_file_templates: list[str] = ["gene_pool.json", "fusion_plan.json"]

    def __init__(self, **params: Any) -> None:
        # Store algorithm parameters (max_routes, crossover_rate, etc.) for
        # potential use by the Orchestrator when building the manifest.
        self.params = params

    def select_next_round(
        self,
        round_index: list[dict[str, Any]],
        op_category: str | None,
        current_policy: str,
        context: dict[str, Any] | None = None,
    ) -> RoundDecision:
        """Choose the next gene-fusion round (round 1 from global baseline, else best historical)."""
        if not round_index:
            return RoundDecision(
                direction="pattern: custom",
                hypothesis=("Gene-fusion Round 1: decompose compute atoms, perform automatic fusion "
                            "analysis, and build the initial gene pool."),
                round_strategy="exploration",
                analysis_policy="pattern_entry",
                evidence_sources=["model_knowledge"],
                baseline=BaselineProposal(mode="none"),
                metadata={"algorithm_params": self.params},
            )

        best = self._best_historical_round(round_index)
        if best is not None:
            mix = adapt_route_mix(round_index, self.params)
            adapted_params = dict(self.params)
            adapted_params["elite_count"] = mix["elite_count"]
            adapted_params["exploration_count"] = mix["exploration_count"]
            if mix["adjust_reason"]:
                adapted_params["route_mix_adjust"] = mix["adjust_reason"]
            return RoundDecision(
                direction="pattern: custom",
                hypothesis="Gene-fusion evolutionary round: evolve the gene pool from the best historical round.",
                round_strategy="exploration",
                analysis_policy="pattern_entry",
                evidence_sources=["direction_history", "model_knowledge"],
                baseline=BaselineProposal(mode="single", round_dirs=[best.get("round_dir", "")]),
                metadata={"algorithm_params": adapted_params, "route_mix": mix},
            )

        return RoundDecision(
            direction="pattern: custom",
            hypothesis="Gene-fusion round: continue exploring from the global baseline.",
            round_strategy="exploration",
            analysis_policy="pattern_entry",
            evidence_sources=["model_knowledge"],
            baseline=BaselineProposal(mode="none"),
            metadata={"algorithm_params": self.params},
        )

    def classify_direction_yield(
        self,
        ctx: DirectionYieldContext,
    ) -> tuple[str, str, float]:
        return ds.classify_direction_yield(ctx)

    def _best_historical_round(
        self, round_index: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        """Return the highest-speedup round that passed verification."""
        def _verified(r: dict[str, Any]) -> bool:
            return r.get("best_speedup", 0.0) > 0 and r.get("direction_yield") != "failed"

        candidates = [r for r in round_index if _verified(r)]
        if not candidates:
            return None
        return max(candidates, key=lambda r: float(r.get("best_speedup", 0.0)))
