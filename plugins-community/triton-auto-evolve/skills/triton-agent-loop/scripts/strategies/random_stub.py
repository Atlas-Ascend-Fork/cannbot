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
"""Random stub strategy: proves the pluggability framework.

This strategy is intentionally simple and non-deterministic. It always returns
a model-driven direction (pattern: custom) so that the sub-agent can autonomously
choose the concrete optimization direction. It is NOT suitable for production
optimization.
"""

import random
from pathlib import Path
from typing import Any

import direction_selector as ds
from direction_selector import DirectionSelection, DirectionYieldContext
from .base import (
    BaselineProposal,
    RoundDecision,
    Strategy,
    StrategyCapabilities,
)


class RandomStubStrategy(Strategy):
    """Random direction/baseline selection stub for framework testing."""

    name = "random_stub"
    capabilities = StrategyCapabilities(
        can_propose_direction=True,
        can_propose_baseline=False,
        can_decide_switch_internally=False,
        can_recommend_stop=False,
    )

    # select_next_direction 迁移期默认方向（目录缺失场景归 autotune）
    legacy_default_direction = "pattern: autotune"

    def __init__(self, seed: int | None = None) -> None:
        self.rng = random.Random(seed)

    def select_next_round(
        self,
        round_index: list[dict[str, Any]],
        op_category: str | None,
        current_policy: str,
        context: dict[str, Any] | None = None,
    ) -> RoundDecision:
        """Return a model-driven direction placeholder."""
        return RoundDecision(
            direction="pattern: custom",
            hypothesis="LLM-driven autonomous direction selection (catalog absent)",
            round_strategy="exploration",
            analysis_policy=current_policy,
            evidence_sources=["model_knowledge"],
            baseline=BaselineProposal(mode="none"),
            metadata={"stub": True, "llm_driven": True},
        )

    def score_baseline_for_direction(
        self,
        candidate: dict[str, Any],
        target_direction: str,
        target_strategy: str = "exploration",
        context: dict[str, Any] | None = None,
    ) -> float:
        # Same hard gates as the naive strategy to keep semantics safe.
        if candidate.get("status") != "success":
            return 0.0
        if candidate.get("round_type") == "idle":
            return 0.0
        perf_data = candidate.get("perf_data") or {}
        total = perf_data.get("total_cases", 0)
        passed = perf_data.get("passed_cases", 0)
        if not (isinstance(total, (int, float)) and isinstance(passed, (int, float))):
            return 0.0
        if int(total) <= 0 or int(passed) != int(total):
            return 0.0
        return self.rng.random()

    def classify_direction_yield(
        self,
        ctx: DirectionYieldContext,
    ) -> tuple[str, str, float]:
        # Yield classification is not the focus of this stub; delegate to naive.
        return ds.classify_direction_yield(ctx)
