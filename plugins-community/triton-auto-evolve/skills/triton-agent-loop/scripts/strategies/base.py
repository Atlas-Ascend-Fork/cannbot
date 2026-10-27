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
"""Abstract base class for optimization direction/baseline strategies.

A strategy encapsulates three decision points of the optimization loop:
1. Which direction to try next (select_next_direction / select_next_round).
2. Which historical round to use as baseline (score_baseline_for_direction).
3. How to label the outcome of a direction attempt (classify_direction_yield).

New algorithms are added by subclassing Strategy and placing the module in
this package. The loader discovers them automatically.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import direction_selector as ds
from direction_selector import DirectionSelection, DirectionYieldContext


@dataclass
class StrategyCapabilities:
    """Declare what decisions a strategy is able to produce."""

    can_propose_direction: bool = True
    can_propose_baseline: bool = False
    can_propose_multiple_baselines: bool = False
    can_decide_switch_internally: bool = False
    can_recommend_stop: bool = False
    needs_persistent_state: bool = False
    can_select_round: bool = False


@dataclass
class BaselineProposal:
    """Describe which historical round(s) should seed the next round."""

    mode: Literal["none", "single", "multiple"] = "none"
    round_dirs: list[str] = field(default_factory=list)
    combination_rule: str | None = None
    global_baseline_dir: str | None = None


@dataclass
class SwitchMarker:
    """Audit metadata for a direction switch."""

    reason: str
    previous_direction: str | None = None
    new_direction: str | None = None


@dataclass
class RoundDecision:
    """Decision envelope produced by a strategy for the next optimization round.

    Strategies fill only the fields they are capable of determining. The
    Orchestrator completes any missing fields before creating the next round.
    """

    direction: str | None = None
    hypothesis: str | None = None
    round_strategy: str | None = None
    analysis_policy: str | None = None
    evidence_sources: list[str] = field(default_factory=list)
    baseline: BaselineProposal = field(default_factory=BaselineProposal)
    switch_marker: SwitchMarker | None = None
    algorithm_recommends_stop: bool = False
    stop_reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    parent_round_dir: str | None = None
    selected_round_dir: str | None = None


def decision_to_direction_selection(
    decision: RoundDecision,
    current_policy: str,
    default_direction: str,
    metadata: dict[str, Any] | None = None,
) -> DirectionSelection:
    """Convert a RoundDecision into the legacy DirectionSelection interface.

    Shared by strategies that keep the deprecated select_next_direction()
    entry point during migration. Pass ``metadata`` to override the decision's
    own metadata (e.g. to inject baseline hints).
    """
    return DirectionSelection(
        strategy=decision.round_strategy or "exploration",
        analysis_policy=decision.analysis_policy or current_policy,
        direction=decision.direction or default_direction,
        hypothesis=decision.hypothesis or "",
        evidence_sources=decision.evidence_sources,
        metadata=metadata if metadata is not None else decision.metadata,
    )


class Strategy(ABC):
    """Abstract base class for optimization direction/baseline strategies."""

    # Human-readable identifier. Must be unique across all discovered strategies.
    name: str = ""

    # Capability declaration. Orchestrator uses this to decide which fields of
    # RoundDecision it must fill in.
    capabilities: StrategyCapabilities = StrategyCapabilities()

    # Default direction used by the legacy select_next_direction() conversion.
    legacy_default_direction: str = "pattern: custom"

    # Algorithm-specific state files that must be inherited across rounds.
    # Each entry is a template string relative to the round directory and may
    # contain the {op_name} placeholder. Example: ["gene_pool.json"].
    state_file_templates: list[str] = []

    @abstractmethod
    def select_next_round(
        self,
        round_index: list[dict[str, Any]],
        op_category: str | None,
        current_policy: str,
        context: dict[str, Any] | None = None,
    ) -> RoundDecision:
        """Choose the next optimization round.

        Args:
            round_index: Historical round metadata from round_index.json.
            op_category: Optional operator category (e.g., "matmul", "softmax").
            current_policy: Current analysis_policy (pattern_entry, etc.).
            context: Optional caller context. May include ``op_dir``,
                ``current_round``, or other runtime information strategies can
                use for state management.

        Returns:
            A RoundDecision envelope. Missing fields will be completed by the
            Orchestrator.
        """

    def select_next_direction(
        self,
        round_index: list[dict[str, Any]],
        op_category: str | None,
        current_policy: str,
        context: dict[str, Any] | None = None,
    ) -> DirectionSelection:
        """Legacy interface preserved during migration.

        New code should call select_next_round() instead. The default
        implementation delegates to select_next_round() and converts the
        RoundDecision envelope; strategies only override this when they must
        enrich the conversion (e.g. baseline hints in metadata).
        """
        decision = self.select_next_round(round_index, op_category, current_policy, context)
        return decision_to_direction_selection(
            decision, current_policy, self.legacy_default_direction
        )

    def score_baseline_for_direction(
        self,
        candidate: dict[str, Any],
        target_direction: str,
        target_strategy: str = "exploration",
        context: dict[str, Any] | None = None,
    ) -> float:
        """Score a historical round as a baseline candidate.

        Returns a value in [0.0, 1.0]. 0.0 means the candidate is ineligible.

        The default delegates to the shared direction_selector scorer. Strategies
        that maintain their own baseline preference (e.g. MCTS) override this.
        """
        return ds.score_baseline_for_direction(
            candidate,
            target_direction,
            target_strategy=target_strategy,
        )

    @abstractmethod
    def classify_direction_yield(
        self,
        ctx: DirectionYieldContext,
    ) -> tuple[str, str, float]:
        """Classify the outcome of a direction attempt.

        Returns:
            (direction_yield, yield_reason, absolute_gain)
        """

    def init_for_operator(
        self,
        op_dir: Path,
        config: dict[str, Any],
        round_index: list[dict[str, Any]],
    ) -> None:
        """Optional lifecycle hook called once per operator workspace.

        Strategies that need per-operator initialization (e.g., creating an
        MCTS tree or loading persistent state) can override this method.
        The default implementation does nothing.
        """
        return None

    def record_round_result(
        self,
        round_index_entry: dict[str, Any],
        round_dir: Path,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Optional lifecycle hook called after a round has finished.

        Strategies that maintain persistent state across rounds (e.g. MCTS
        trees, genetic populations) can use this to record the outcome of the
        just-completed round. The default implementation does nothing.

        Args:
            round_index_entry: The entry from round_index.json for the completed
                round. Contains fields such as direction, best_speedup, status,
                baseline_dir, etc.
            round_dir: Path to the completed round directory (e.g. opt-round-1).
            context: Optional caller context, may include op_dir and config.
        """
        return None

    def resolve_to_single_baseline(
        self,
        baseline: BaselineProposal,
        round_index: list[dict[str, Any]],
        target_direction: str,
        context: dict[str, Any] | None = None,
    ) -> BaselineProposal:
        """Optional hook for strategies that can return multiple baselines.

        If the worker does not support multiple baselines, the Orchestrator
        calls this method to reduce the proposal to a single round_dir.
        The default implementation picks the first entry.
        """
        if baseline.mode == "multiple" and baseline.round_dirs:
            return BaselineProposal(mode="single", round_dirs=[baseline.round_dirs[0]])
        return BaselineProposal(mode="none")
