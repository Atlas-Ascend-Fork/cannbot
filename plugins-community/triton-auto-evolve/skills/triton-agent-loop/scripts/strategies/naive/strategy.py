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
"""Naive strategy: LLM-driven direction adjustment with internal plateau/low-yield handling.

This strategy is responsible for:
- Letting the sub-agent/LLM propose the concrete optimization direction (always
  surfaced as ``pattern: custom``).
- Detecting when recent rounds are stagnating or yielding low/failed results and
  requesting an adjustment (deeper analysis, different baseline, or a fresh
  optimization idea) instead of stopping the loop.
- Scoring historical baselines for a chosen direction.
- Classifying direction yield after each round.

Stopping is intentionally left to the Orchestrator's C1/C2 checks only; this
strategy no longer recommends stopping.
"""

from pathlib import Path
from typing import Any

import check_local_optimum
import direction_selector as ds
from direction_selector import DirectionSelection, DirectionYieldContext
from ..base import (
    BaselineProposal,
    RoundDecision,
    Strategy,
    StrategyCapabilities,
    SwitchMarker,
)


def _detect_plateau(op_dir: Path | None) -> bool:
    """Detect a speedup plateau (C3) from disk speedups."""
    if op_dir is None:
        return False
    try:
        local_opt = check_local_optimum.check_local_optimum(op_dir, window=3, max_gain=0.02)
        return local_opt.get("in_local_optimum", False)
    except Exception:
        return False


class NaiveStrategy(Strategy):
    """Default strategy: LLM-driven direction selection + low-yield adjustment."""

    name = "naive"
    capabilities = StrategyCapabilities(
        can_propose_direction=True,
        can_propose_baseline=False,
        can_propose_multiple_baselines=False,
        can_decide_switch_internally=True,
        can_recommend_stop=False,
        needs_persistent_state=False,
        can_select_round=False,
    )
    state_file_templates: list[str] = []

    def __init__(self, **kwargs: Any) -> None:
        # Naive has no tunable parameters; accept and ignore any extras.
        pass

    def select_next_round(
        self,
        round_index: list[dict[str, Any]],
        op_category: str | None,
        current_policy: str,
        context: dict[str, Any] | None = None,
    ) -> RoundDecision:
        """Choose the next round: plateau/low-yield triggers adjustment, else normal exploration."""
        op_dir = Path(context["op_dir"]) if context and context.get("op_dir") else None
        current_direction = self._current_direction(round_index)

        # C3 plateau detection + LLM-driven low-yield adjustment.
        plateau_detected = _detect_plateau(op_dir)
        low_yield_adjustment = self._recent_custom_low_yield(round_index, window=3)

        if plateau_detected or low_yield_adjustment:
            switch_reason = "plateau_stagnation" if plateau_detected else "low_yield_adjustment"
            sel = ds.select_next_direction(
                round_index,
                op_category=op_category,
                current_policy=current_policy,
                context_changed=True,
            )
            return RoundDecision(
                direction=sel.direction,
                hypothesis=(f"Recent rounds show "
                            f"{'a speedup plateau' if plateau_detected else 'consistent low/failed yields'}. "
                            "Adjust the optimization approach: re-analyze the bottleneck, try a different "
                            "implementation idea, or escalate the analysis depth."),
                round_strategy=sel.strategy,
                analysis_policy=sel.analysis_policy,
                evidence_sources=sel.evidence_sources,
                baseline=BaselineProposal(mode="none"),
                switch_marker=SwitchMarker(reason=switch_reason, previous_direction=current_direction,
                                           new_direction=sel.direction),
                metadata=sel.metadata,
            )

        # Normal path: let the sub-agent/LLM continue with the current policy.
        sel = ds.select_next_direction(
            round_index,
            op_category=op_category,
            current_policy=current_policy,
            context_changed=False,
        )
        return RoundDecision(
            direction=sel.direction,
            hypothesis=sel.hypothesis,
            round_strategy=sel.strategy,
            analysis_policy=sel.analysis_policy,
            evidence_sources=sel.evidence_sources,
            baseline=BaselineProposal(mode="none"),
            metadata=sel.metadata,
        )

    def classify_direction_yield(
        self,
        ctx: DirectionYieldContext,
    ) -> tuple[str, str, float]:
        return ds.classify_direction_yield(ctx)

    def _current_direction(self, round_index: list[dict[str, Any]]) -> str | None:
        if not round_index:
            return None
        direction = round_index[-1].get("direction", "")
        return direction if direction else None

    def _recent_custom_low_yield(
        self,
        round_index: list[dict[str, Any]],
        window: int = 3,
    ) -> bool:
        """Return True if the last ``window`` non-idle rounds are low-yield or failed.

        Directions are now always surfaced as ``pattern: custom`` by the
        LLM-driven selector, so the check only looks at the recent yield trend.
        When the same open-ended direction keeps producing poor results, the
        strategy asks for an adjustment rather than giving up.
        """
        recent = [r for r in round_index if r.get("round_type") != "idle"][-window:]
        if len(recent) < window:
            return False
        for entry in recent:
            yield_label = entry.get("direction_yield", "")
            if yield_label not in ("low", "failed"):
                return False
        return True
