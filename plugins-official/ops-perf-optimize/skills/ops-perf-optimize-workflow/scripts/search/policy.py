# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Evidence-driven, single-candidate search over the existing workflow events.

Contracts own decisions, selection artifacts own observations, and workflow_state
owns all writes. This module neither runs experiments nor changes stopping goals.
"""

from __future__ import annotations

import copy
import csv
import hashlib
import json
import math
import re
import statistics
from pathlib import Path

from performance_effect_evidence import policy as effect_policy
from summarize_performance_effects import recompute_summary, summary_dependency_paths
from validate_schedule_contract import (
    ref,
    source_identity,
    verify_ref as verify_file_ref,
)


POLICY = {"id": "architecture_search_v1", "version": 1}
PATIENCE = 3
AXIS_DIRECTION_PREFIX = "search-axis:"
EXCLUDED_DIRECTION_STATUSES = ("infeasible_evidenced", "blocked_by_precision")
ROUND = r"(?:gen\.)?round[1-9]\d*"
OUTCOMES = (
    "screened",
    "measured",
    "implementation_failed",
    "precision_failed",
    "evidence_invalid",
    "no_candidate",
)
REPLAN_REASONS = ("plateau", "graph_exhausted", "gate_impasse", "architecture_limit")
FIDELITIES = ("L0", "L1", "L2", "L3")
LEVELS = ("M0", "M1", "open")
EXPLORE_TAGS = ("exploit", "explore", "open")
OPTIMIZATION_TYPES = ("bandwidth", "tiling", "algorithm", "schedule", "other")
NODE_STATUSES = (
    "candidate",
    "selected",
    "accepted",
    "rejected",
    "pruned",
    "failed",
    "no_go",
)
PRUNE_REASONS = (
    "no_trigger",
    "lower_bound",
    "below_noise_floor",
    "successive_halving",
    "manual",
)
STRATEGIES = (
    "ucb",
    "beam",
    "successive_halving",
    "mcts",
    "doe",
    "tpe",
    "pareto",
    "qd",
)
DEFAULT_STRATEGY = "ucb"
DEFAULT_N = 3
DEFAULT_P_PASS = 0.5
DEFAULT_EPSILON = 0.01
DEFAULT_EXPLORE_EVERY = 3
DEFAULT_UCB_C = 0.5
STRATEGY_HANDLERS = {}


STRATEGY_STATUS = {
    "ucb": "stable",
    "beam": "stable",
    "successive_halving": "experimental",
    "mcts": "experimental",
    "doe": "experimental",
    "tpe": "experimental",
    "pareto": "experimental",
    "qd": "stable",
}


def register_strategy(name, handler):
    require(name in STRATEGIES, f"strategy is not declared in STRATEGIES: {name}")
    require(callable(handler), "strategy handler must be callable")
    STRATEGY_HANDLERS[name] = handler


DEFAULT_WEIGHTS = {
    "gain": 1.0,
    "prior": 0.5,
    "novelty": 0.5,
    "ucb": 1.0,
    "cost": 0.3,
    "risk": 0.3,
}


def require(condition, message):
    if not condition:
        raise ValueError(f"search: {message}")


def load(path):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"expected JSON object: {path}")
    return value


def verify_ref(value, dependencies):
    verify_file_ref(value, {})
    if value not in dependencies:
        dependencies.append(value)


def validate_policy(value):
    require(
        isinstance(value, dict)
        and value == POLICY
        and type(value.get("version")) is int,
        "unsupported search_policy",
    )
    return dict(value)


def enabled(manifest):
    config = manifest.get("configuration", {})
    request = manifest.get("request", {})
    if request.get("path"):
        verify_ref({k: request[k] for k in ("path", "sha256")}, [])
        frozen = load(request["path"])
        require(
            ("search_policy" in frozen) == ("search_policy" in config)
            and frozen.get("search_policy") == config.get("search_policy"),
            "policy differs from frozen request",
        )
    if "search_policy" not in config:
        return False
    validate_policy(config["search_policy"])
    return True


def checked_refs(values, label):
    require(isinstance(values, list) and values, f"{label} needs evidence references")
    dependencies = []
    for value in values:
        verify_ref(value, dependencies)
    return dependencies


def checked_case_bucket(record, label, *, legacy_null=False):
    if "case_bucket" not in record:
        return None
    value = record["case_bucket"]
    if legacy_null and value is None:
        return None
    require(
        isinstance(value, str) and value.strip(),
        f"{label} must be a nonempty string",
    )
    return value


def _finite_number(value, label, *, positive=False, nonnegative=False):
    require(
        isinstance(value, (int, float)) and not isinstance(value, bool),
        f"{label} must be a number",
    )
    require(math.isfinite(value), f"{label} must be finite")
    if positive:
        require(value > 0, f"{label} must be > 0")
    if nonnegative:
        require(value >= 0, f"{label} must be >= 0")
    return float(value)


def gain_range(value, label="expected_gain_range"):
    if isinstance(value, dict):
        low, high = value.get("low"), value.get("high")
    elif isinstance(value, (list, tuple)) and len(value) == 2:
        low, high = value
    else:
        raise ValueError(f"search: {label} must be [low, high] or {{low, high}}")
    low = _finite_number(low, f"{label}.low", nonnegative=True)
    high = _finite_number(high, f"{label}.high", nonnegative=True)
    require(low <= high <= 1.0, f"{label} must satisfy 0 <= low <= high <= 1")
    return [low, high]


def _weights(value):
    if value is None:
        return dict(DEFAULT_WEIGHTS)
    require(isinstance(value, dict), "frontier weights must be an object")
    unknown = set(value) - set(DEFAULT_WEIGHTS)
    require(not unknown, f"unknown utility weights: {sorted(unknown)}")
    result = {**DEFAULT_WEIGHTS, **value}
    for name, weight in result.items():
        _finite_number(weight, f"weights.{name}", nonnegative=True)
    return {name: float(weight) for name, weight in result.items()}


def _node_dependencies(node, node_ids, accepted):
    depends = node.get("depends_on", [])
    require(
        isinstance(depends, list)
        and all(isinstance(x, str) and x for x in depends)
        and len(depends) == len(set(depends))
        and node["scheme_id"] not in depends,
        "frontier dependencies must be unique node IDs without self-dependency",
    )
    unknown = set(depends) - set(node_ids) - set(accepted)
    require(not unknown, f"unknown frontier dependencies: {sorted(unknown)}")
    return depends


def _ensure_acyclic(nodes):
    graph = {node["scheme_id"]: set(node.get("depends_on", [])) for node in nodes}
    visiting, done = set(), set()

    def visit(node_id):
        if node_id in done:
            return
        require(node_id not in visiting, "frontier decision graph contains a cycle")
        visiting.add(node_id)
        for parent in graph.get(node_id, ()):
            if parent in graph:
                visit(parent)
        visiting.remove(node_id)
        done.add(node_id)

    for node_id in graph:
        visit(node_id)


def checked_space(reference, dependencies):
    from .candidates import load_space

    verify_ref(reference, dependencies)
    return load_space(reference["path"], dependencies=dependencies)[0]


def validate_frontier(frontier, contract=None, manifest=None, accepted=()):
    """Validate a candidate frontier and its binding to the frozen contract."""
    require(isinstance(frontier, dict), "frontier must be an object")
    require(
        frontier.get("schema_version") == 1
        and type(frontier.get("schema_version")) is int,
        "unsupported frontier schema_version",
    )
    round_name = frontier.get("round")
    require(
        isinstance(round_name, str) and re.fullmatch(ROUND, round_name),
        "frontier needs a round name",
    )
    parent = frontier.get("parent")
    validate_parent({"parent": parent}, None)
    best = _finite_number(frontier.get("best_total_us"), "best_total_us", positive=True)
    n = frontier.get("n", DEFAULT_N)
    require(
        type(n) is int and 1 <= n <= 16,
        "frontier n must be an integer between 1 and 16",
    )
    p_pass = _finite_number(
        frontier.get("p_pass", DEFAULT_P_PASS), "p_pass", positive=True
    )
    require(p_pass <= 1.0, "p_pass must be <= 1")
    epsilon = _finite_number(
        frontier.get("epsilon", DEFAULT_EPSILON), "epsilon", nonnegative=True
    )
    explore_every = frontier.get("explore_every", DEFAULT_EXPLORE_EVERY)
    require(
        type(explore_every) is int and explore_every >= 1,
        "explore_every must be a positive integer",
    )
    _weights(frontier.get("weights"))
    strategy = frontier.get("strategy", DEFAULT_STRATEGY)
    require(strategy in STRATEGIES, f"unknown frontier strategy: {strategy}")
    options = frontier.get("strategy_options", {})
    require(isinstance(options, dict), "strategy_options must be an object")
    if "beam_width" in options:
        require(
            type(options["beam_width"]) is int and options["beam_width"] >= 1,
            "strategy_options.beam_width must be positive",
        )
    if "mcts_iterations" in options:
        require(
            type(options["mcts_iterations"]) is int and options["mcts_iterations"] >= 1,
            "strategy_options.mcts_iterations must be positive",
        )
    if "keep_ratio" in options:
        ratio = _finite_number(
            options["keep_ratio"], "strategy_options.keep_ratio", positive=True
        )
        require(ratio <= 1.0, "strategy_options.keep_ratio must be <= 1")
    nodes = frontier.get("nodes")
    require(isinstance(nodes, list) and nodes, "frontier needs candidate nodes")
    dependencies = []
    minimum = math.ceil(n / p_pass)
    if "candidate_space" in frontier:
        checked_space(frontier["candidate_space"], dependencies)
    require(
        len(nodes) >= minimum,
        f"frontier needs at least {minimum} generated candidates",
    )
    prefilter = frontier.get("prefilter")
    require(isinstance(prefilter, dict), "frontier needs a prefilter record")
    l0 = prefilter.get("l0")
    require(isinstance(l0, dict), "prefilter.l0 is required")
    if l0.get("status", "applied") == "applied":
        require(
            isinstance(l0.get("method"), str) and l0["method"].strip(),
            "prefilter.l0 needs a method",
        )
        require(
            _finite_number(
                l0.get("best_total_us"), "prefilter.l0.best_total_us", positive=True
            )
            == best,
            "prefilter.l0 best_total_us differs from frontier best_total_us",
        )
    else:
        require(
            isinstance(l0.get("reason"), str) and l0["reason"].strip(),
            "unsupported prefilter.l0 needs a reason",
        )
    l1 = prefilter.get("l1")
    require(isinstance(l1, dict), "prefilter.l1 is required")
    if l1.get("status", "applied") == "applied":
        require(
            isinstance(l1.get("tool"), str) and l1["tool"].strip(),
            "prefilter.l1 needs a tool",
        )
        require(
            type(l1.get("coverage")) is int and l1["coverage"] >= 0,
            "prefilter.l1.coverage must be a non-negative integer",
        )
        require(
            type(l1.get("budget_skipped")) is int and l1["budget_skipped"] >= 0,
            "prefilter.l1.budget_skipped must be a non-negative integer",
        )
        dependencies.extend(checked_refs(l1.get("evidence"), "prefilter.l1.evidence"))
        if l1["budget_skipped"]:
            require(
                l1.get("ranking_validation"),
                "L1 pruning needs device ranking validation evidence",
            )
            verify_ref(l1["ranking_validation"], dependencies)
    else:
        require(
            isinstance(l1.get("reason"), str) and l1["reason"].strip(),
            "unsupported prefilter.l1 needs a reason",
        )
    l2 = prefilter.get("l2")
    if l2 is not None:
        require(isinstance(l2, dict), "prefilter.l2 must be an object")
        if l2.get("status", "applied") == "applied":
            dependencies.extend(
                checked_refs(l2.get("evidence"), "prefilter.l2.evidence")
            )
        else:
            require(
                isinstance(l2.get("reason"), str) and l2["reason"].strip(),
                "unsupported prefilter.l2 needs a reason",
            )
    ids = [node.get("scheme_id") for node in nodes if isinstance(node, dict)]
    require(
        len(ids) == len(nodes)
        and all(isinstance(x, str) and re.fullmatch(r"[A-Za-z0-9_-]+", x) for x in ids)
        and len(ids) == len(set(ids)),
        "frontier nodes need unique scheme_id values",
    )
    for node in nodes:
        require(isinstance(node, dict), "frontier node must be an object")
        scheme = node["scheme_id"]
        checked_case_bucket(node, f"{scheme}.case_bucket")
        kind = node.get("kind")
        level = node.get("level")
        require(kind in ("architecture", "local"), f"{scheme}: invalid kind")
        require(level in LEVELS, f"{scheme}: invalid level")
        if kind == "architecture":
            require(
                level in ("M0", "open"), f"{scheme}: architecture must be M0 or open"
            )
        else:
            require(level == "M1", f"{scheme}: local decisions must be M1")
        require(
            isinstance(node.get("mechanism"), str) and node["mechanism"].strip(),
            f"{scheme}: missing mechanism",
        )
        require(
            node.get("optimization_type") in OPTIMIZATION_TYPES,
            f"{scheme}: invalid optimization_type",
        )
        require(node.get("fidelity") in FIDELITIES, f"{scheme}: invalid fidelity")
        require(node.get("status") in NODE_STATUSES, f"{scheme}: invalid status")
        require(
            node.get("explore_tag") in EXPLORE_TAGS,
            f"{scheme}: invalid explore_tag",
        )
        if node.get("trigger") or node["status"] != "pruned":
            dependencies.extend(checked_refs(node.get("trigger"), f"{scheme}.trigger"))
        for evidence in node.get("evidence", []):
            verify_ref(evidence, dependencies)
        gain_range(node.get("expected_gain_range"), f"{scheme}.expected_gain_range")
        _finite_number(node.get("cost"), f"{scheme}.cost", nonnegative=True)
        risk = _finite_number(node.get("risk"), f"{scheme}.risk", nonnegative=True)
        require(risk <= 1.0, f"{scheme}.risk must be <= 1")
        _node_dependencies(node, ids, accepted)
        if "lower_bound_us" in node:
            _finite_number(
                node["lower_bound_us"], f"{scheme}.lower_bound_us", positive=True
            )
        if "score" in node and node["score"] is not None:
            _finite_number(node["score"], f"{scheme}.score")
        if "pareto_rank" in node and node["pareto_rank"] is not None:
            require(
                type(node["pareto_rank"]) is int and node["pareto_rank"] >= 1,
                f"{scheme}: pareto_rank must be a positive integer",
            )
        if node.get("prune_reason") is not None:
            require(
                isinstance(node["prune_reason"], str) and node["prune_reason"].strip(),
                f"{scheme}: prune_reason must be nonempty",
            )
        if node.get("factors") is not None:
            require(
                isinstance(node["factors"], dict)
                and all(
                    isinstance(name, str) and isinstance(value, (str, int, float, bool))
                    for name, value in node["factors"].items()
                ),
                f"{scheme}: factors must map names to scalar levels",
            )
    _ensure_acyclic(nodes)
    require(
        any(node.get("explore_tag") == "open" for node in nodes),
        "frontier needs at least one open exploration node",
    )
    require(
        len({node["optimization_type"] for node in nodes}) >= 2,
        "frontier needs at least two optimization types",
    )
    if len(nodes) >= 3:
        require(
            len({node["level"] for node in nodes}) >= 2,
            "frontier needs at least two decision levels",
        )
    remaining = _selectable_nodes(nodes)
    require(
        len(remaining) >= n,
        f"frontier needs at least {n} candidates after pruning",
    )
    for node in remaining:
        lower = node.get("lower_bound_us")
        if lower is not None and lower >= best * (1.0 + epsilon):
            raise ValueError(
                f"search: {node['scheme_id']} has an optimistic lower bound that "
                "cannot beat the current best; prune it before selection"
            )
        if gain_range(node.get("expected_gain_range"))[1] <= epsilon:
            raise ValueError(
                f"search: {node['scheme_id']} has no expected gain above epsilon; "
                "prune it as below_noise_floor"
            )
    if contract is not None:
        search = contract.get("search", {})
        checked_case_bucket(search, "search.case_bucket")
        require(parent == search.get("parent"), "frontier parent differs from contract")
        scheme = contract.get("scheme_id")
        selected = next((node for node in nodes if node["scheme_id"] == scheme), None)
        require(selected is not None, "selected scheme is not in the frontier")
        require(
            selected["status"] not in ("pruned", "rejected", "failed", "no_go")
            and not selected.get("prune_reason"),
            "selected scheme was pruned",
        )
        if "case_bucket" in search or "case_bucket" in selected:
            require(
                search.get("case_bucket") == selected.get("case_bucket"),
                "search.case_bucket differs from the selected frontier node",
            )
        require(
            search.get("kind", selected["kind"]) == selected["kind"],
            "selected frontier kind differs from contract",
        )
        if "frontier_parent" in search:
            require(
                search["frontier_parent"] == scheme,
                "search.frontier_parent must name the selected frontier node",
            )
        if "fidelity" in search:
            require(
                search["fidelity"] == selected["fidelity"],
                "search.fidelity differs from the selected frontier node",
            )
        if "expected_gain_range" in search:
            require(
                gain_range(search["expected_gain_range"])
                == gain_range(selected["expected_gain_range"]),
                "search.expected_gain_range differs from the selected node",
            )
        if "cost" in search:
            require(
                float(search["cost"]) == float(selected["cost"]),
                "search.cost differs from the selected frontier node",
            )
        for field, node_field in (
            ("candidate_factors", "factors"),
            ("candidate_bindings", "bindings"),
        ):
            if selected.get(node_field) or field in search:
                require(
                    search.get(field, {}) == selected.get(node_field, {}),
                    f"search.{field} differs from the selected frontier node",
                )
    return dependencies


def prune(frontier, best_total_us=None, epsilon=None):
    """Apply the L0 exclusion rules and return a copied frontier."""
    result = copy.deepcopy(frontier)
    best = (
        _finite_number(best_total_us, "best_total_us", positive=True)
        if best_total_us is not None
        else _finite_number(
            frontier.get("best_total_us"), "best_total_us", positive=True
        )
    )
    eps = (
        _finite_number(epsilon, "epsilon", nonnegative=True)
        if epsilon is not None
        else _finite_number(
            frontier.get("epsilon", DEFAULT_EPSILON), "epsilon", nonnegative=True
        )
    )
    pruned = []
    for node in result.get("nodes", []):
        if node.get("status") in ("pruned", "rejected", "failed", "no_go"):
            continue
        reason = None
        if not node.get("trigger"):
            reason = "no_trigger"
        else:
            lower = node.get("lower_bound_us")
            if lower is not None and float(lower) >= best * (1.0 + eps):
                reason = "lower_bound"
            elif gain_range(node.get("expected_gain_range"))[1] <= eps:
                reason = "below_noise_floor"
        if reason:
            node["status"] = "pruned"
            node["prune_reason"] = reason
        if node.get("status") == "pruned":
            pruned.append(
                {
                    "scheme_id": node["scheme_id"],
                    "prune_reason": node.get("prune_reason", "manual"),
                    "fidelity": node.get("fidelity"),
                }
            )
    result["pruned"] = pruned
    return result


def _observations(observations):
    return [
        observation
        for observation in (observations or ())
        if isinstance(observation, dict)
    ]


def _observation_matches_node(observation, node):
    """Mechanism equality plus case-bucket scoping.

    A bucketed observation (trial run only on a shape regime / case cluster)
    counts exclusively against nodes declaring the same ``case_bucket``;
    an unbucketed observation was run on the whole tuning set and keeps the
    legacy all-case semantics. A bucket-local failure therefore cannot
    globally poison the same mechanism for other shape regimes.
    """
    mechanism = observation.get("mechanism_id") or observation.get("mechanism")
    if mechanism != node.get("mechanism"):
        return False
    bucket = observation.get("case_bucket")
    return bucket is None or bucket == node.get("case_bucket")


def utility(node, observations=(), *, total_nodes=None, max_cost=None, weights=None):
    """UCB-style utility; callers decide how to use the ranking."""
    weights = _weights(weights)
    observations = _observations(observations)
    related = [
        observation
        for observation in observations
        if _observation_matches_node(observation, node)
    ]
    attempts = len(related)
    statuses = {observation.get("mechanism_status") for observation in related}
    prior = 0.0 if "refuted" in statuses else 1.0 if "verified" in statuses else 0.5
    low, high = gain_range(node.get("expected_gain_range"))
    gain = (low + high) / 2.0
    novelty = 1.0 / (1.0 + attempts)
    total = total_nodes if total_nodes is not None else max(1, len(observations) + 1)
    ucb = DEFAULT_UCB_C * math.sqrt(math.log(max(2, total + 1)) / (attempts + 1))
    cost = float(node.get("cost", 0.0))
    cost_norm = min(1.0, cost / max_cost) if max_cost and max_cost > 0 else 0.0
    risk = min(1.0, max(0.0, float(node.get("risk", 0.0))))
    value = (
        weights["gain"] * gain
        + weights["prior"] * prior
        + weights["novelty"] * novelty
        + weights["ucb"] * ucb
        - weights["cost"] * cost_norm
        - weights["risk"] * risk
    )
    return {
        "scheme_id": node["scheme_id"],
        "utility": round(value, 6),
        "gain": gain,
        "prior": prior,
        "novelty": novelty,
        "ucb": ucb,
        "cost": cost_norm,
        "risk": risk,
        "attempts": attempts,
    }


def _selectable_nodes(nodes):
    return [
        node for node in nodes
        if node.get("status") not in ("pruned", "rejected", "failed", "no_go") and not node.get("prune_reason")
    ]


def rank(frontier, observations=(), *, weights=None):
    nodes = _selectable_nodes(frontier.get("nodes", []))
    require(nodes, "frontier has no selectable candidates")
    max_cost = max(float(node.get("cost", 0.0)) for node in nodes) or 1.0
    ranked = [
        {
            **utility(
                node,
                observations,
                total_nodes=len(nodes),
                max_cost=max_cost,
                weights=weights,
            ),
            "node": node,
        }
        for node in nodes
    ]
    ranked.sort(key=lambda item: item["utility"], reverse=True)
    return ranked


def _dominates(left, right):
    left_gain = gain_range(left["node"]["expected_gain_range"])[1]
    right_gain = gain_range(right["node"]["expected_gain_range"])[1]
    left_cost = float(left["node"].get("cost", 0.0))
    right_cost = float(right["node"].get("cost", 0.0))
    left_risk = float(left["node"].get("risk", 0.0))
    right_risk = float(right["node"].get("risk", 0.0))
    better = (
        left_gain >= right_gain and left_cost <= right_cost and left_risk <= right_risk
    )
    strict = left_gain > right_gain or left_cost < right_cost or left_risk < right_risk
    return better and strict


def pareto_fronts(items, dominates):
    """Shared nondominated sorting for predicted gains and observed scores."""
    remaining = list(items)
    while remaining:
        front = [
            item
            for item in remaining
            if not any(
                dominates(other, item) for other in remaining if other is not item
            )
        ]
        require(front, "invalid cyclic Pareto dominance")
        yield front
        remaining = [item for item in remaining if item not in front]


def pareto_ranks(frontier, observations=(), *, weights=None):
    """Assign non-dominated ranks over gain / cost / risk."""
    result = copy.deepcopy(frontier)
    ranked = rank(result, observations, weights=weights)
    size = 0
    for size, front in enumerate(pareto_fronts(ranked, _dominates), 1):
        for item in front:
            item["node"]["pareto_rank"] = size
    result["pareto_size"] = size
    return result


def successive_halving(
    frontier,
    observations=(),
    *,
    keep_ratio=0.5,
    min_keep=1,
    weights=None,
):
    """Keep the top fraction for the next rung; state is a copied snapshot."""
    require(0 < keep_ratio <= 1, "successive halving keep_ratio must be in (0, 1]")
    require(type(min_keep) is int and min_keep >= 1, "min_keep must be positive")
    result = copy.deepcopy(frontier)
    ranked = rank(result, observations, weights=weights)
    keep = max(min_keep, math.ceil(len(ranked) * keep_ratio))
    keep = min(keep, len(ranked))
    promoted = [item["scheme_id"] for item in ranked[:keep]]
    eliminated = [item["scheme_id"] for item in ranked[keep:]]
    for item in ranked[keep:]:
        node = next(
            node for node in result["nodes"] if node["scheme_id"] == item["scheme_id"]
        )
        node["status"] = "pruned"
        node["prune_reason"] = "successive_halving"
    result["promoted"] = promoted
    result["eliminated"] = eliminated
    result["rung_keep"] = keep
    return result


def mcts_rank(
    frontier,
    observations=(),
    *,
    iterations=64,
    exploration=1.414,
    weights=None,
):
    """A bounded UCT rollout over the decision DAG.

    There is no device rollout here: the value of a leaf is its utility proxy.
    The result is a ranking, not evidence of measured performance.
    """
    require(
        type(iterations) is int and iterations >= 1, "mcts iterations must be positive"
    )
    require(exploration >= 0, "mcts exploration must be nonnegative")
    ranked = rank(frontier, observations, weights=weights)
    by_id = {item["scheme_id"]: item for item in ranked}
    node_ids = set(by_id)
    children = {sid: [] for sid in node_ids}
    roots = []
    for item in ranked:
        parents = [
            parent
            for parent in item["node"].get("depends_on", [])
            if parent in node_ids
        ]
        if parents:
            for parent in parents:
                children[parent].append(item["scheme_id"])
        else:
            roots.append(item["scheme_id"])
    if not roots:
        roots = sorted(node_ids)
    visits = {sid: 0 for sid in node_ids}
    values = {sid: 0.0 for sid in node_ids}
    utilities = {item["scheme_id"]: item["utility"] for item in ranked}

    def uct(sid, parent_visits):
        if visits[sid] == 0:
            return float("inf")
        return values[sid] / visits[sid] + exploration * math.sqrt(
            math.log(max(1, parent_visits)) / visits[sid]
        )

    for _ in range(iterations):
        root = min(roots, key=lambda sid: (visits[sid], -utilities[sid]))
        path = [root]
        current = root
        while children.get(current):
            parent_visits = visits[current]
            candidates = children[current]
            current = max(
                candidates,
                key=lambda sid: (uct(sid, parent_visits), utilities[sid]),
            )
            path.append(current)
            if visits[current] == 0:
                break
        reward = utilities[path[-1]]
        for sid in path:
            visits[sid] += 1
            values[sid] += reward
    result = []
    for item in ranked:
        sid = item["scheme_id"]
        result.append(
            {
                **item,
                "mcts_visits": visits[sid],
                "mcts_value": round(values[sid] / visits[sid], 6)
                if visits[sid]
                else 0.0,
            }
        )
    result.sort(
        key=lambda item: (
            item["mcts_value"],
            item["mcts_visits"],
            item["utility"],
        ),
        reverse=True,
    )
    return result


def doe_rank(frontier, observations=(), *, weights=None):
    """Rank by additive main effects when nodes declare factors; else UCB."""
    ranked = rank(frontier, observations, weights=weights)
    factors = {item["scheme_id"]: item["node"].get("factors", {}) for item in ranked}
    if not any(factors.values()):
        return ranked
    global_mean = statistics.fmean(item["utility"] for item in ranked)
    effects = {}
    for item in ranked:
        for name, level in factors[item["scheme_id"]].items():
            effects.setdefault((name, str(level)), []).append(item["utility"])
    effect_values = {
        key: statistics.fmean(values) - global_mean for key, values in effects.items()
    }
    result = []
    for item in ranked:
        effect = sum(
            effect_values.get((name, str(level)), 0.0)
            for name, level in factors[item["scheme_id"]].items()
        )
        result.append(
            {
                **item,
                "doe_effect": round(effect, 6),
                "doe_score": round(item["utility"] + effect, 6),
            }
        )
    result.sort(key=lambda item: (item["doe_score"], item["utility"]), reverse=True)
    return result


def _gaussian_density(value, points, bandwidth):
    return statistics.fmean(
        math.exp(-0.5 * ((value - point) / bandwidth) ** 2) for point in points
    )


def tpe_rank(frontier, observations=(), *, weights=None):
    """A lightweight TPE-like density ratio over gain, cost and risk."""
    ranked = rank(frontier, observations, weights=weights)
    nodes = {item["scheme_id"]: item["node"] for item in ranked}
    observed = []
    for observation in _observations(observations):
        sid = observation.get("scheme_id") or observation.get("decision_id")
        node = nodes.get(sid)
        if node is None:
            continue
        score = observation.get("score")
        if not isinstance(score, (int, float)) or isinstance(score, bool):
            score = 1.0 if observation.get("classification") == "improvement" else 0.0
        observed.append((node, float(score)))
    if len(observed) < 4:
        return ranked
    scores = sorted(score for _, score in observed)
    split = scores[len(scores) // 2]
    good = [node for node, score in observed if score > split]
    bad = [node for node, score in observed if score <= split]
    if len(good) < 2 or len(bad) < 2:
        return ranked

    def features(node):
        return (
            (
                gain_range(node["expected_gain_range"])[0]
                + gain_range(node["expected_gain_range"])[1]
            )
            / 2.0,
            float(node.get("cost", 0.0)),
            float(node.get("risk", 0.0)),
        )

    good_features = [features(node) for node in good]
    bad_features = [features(node) for node in bad]
    result = []
    for item in ranked:
        values = features(item["node"])
        ratio = []
        for index, value in enumerate(values):
            good_values = [feature[index] for feature in good_features]
            bad_values = [feature[index] for feature in bad_features]
            bandwidth = max(
                1e-3,
                (
                    statistics.pstdev(good_values + bad_values)
                    if len(good_values + bad_values) > 1
                    else 0.1
                ),
            )
            ratio.append(
                math.log(
                    (_gaussian_density(value, good_values, bandwidth) + 1e-9)
                    / (_gaussian_density(value, bad_values, bandwidth) + 1e-9)
                )
            )
        tpe = statistics.fmean(ratio)
        result.append({**item, "tpe_score": round(tpe, 6)})
    result.sort(key=lambda item: (item["tpe_score"], item["utility"]), reverse=True)
    return result


def _ranking_item(item, extra=None):
    value = {
        "scheme_id": item["scheme_id"],
        "utility": item["utility"],
        "explore_tag": item["node"].get("explore_tag"),
    }
    if extra:
        value.update(extra)
    return value


def _qd_descriptor(node):
    family = node.get("mechanism_family") or node.get("mechanism") or "unknown"
    return (
        str(family),
        str(node.get("shape_bucket", "all")),
        str(node.get("bottleneck_type", "unknown")),
    )


def qd_rank(frontier, observations=(), *, weights=None):
    """QD behavior grid: keep one elite per cell, prioritize unmeasured cells."""
    ranked = rank(frontier, observations, weights=weights)
    nodes = {node["scheme_id"]: node for node in frontier.get("nodes", [])}
    measured = {
        item.get("scheme_id")
        for item in observations
        if item.get("outcome") == "measured"
    }
    cells = {}
    for item in ranked:
        node = nodes.get(item["scheme_id"], {})
        key = _qd_descriptor(node)
        if key not in cells:
            cells[key] = {"elite": item, "measured": False}
        if item["scheme_id"] in measured:
            cells[key]["measured"] = True
    elites = [entry["elite"] for entry in cells.values()]
    unexplored = [entry["elite"] for entry in cells.values() if not entry["measured"]]
    seen, ordered = set(), []
    for item in unexplored + elites + ranked:
        if item["scheme_id"] not in seen:
            seen.add(item["scheme_id"])
            ordered.append(item)
    return ordered, {
        "cells": [list(key) for key in cells],
        "unexplored": len(unexplored),
    }


def select(
    frontier,
    observations=(),
    *,
    strategy=None,
    width=None,
    force_explore=False,
    weights=None,
):
    strategy = strategy or frontier.get("strategy", DEFAULT_STRATEGY)
    require(strategy in STRATEGIES, f"unknown select strategy: {strategy}")
    if strategy in STRATEGY_HANDLERS:
        return STRATEGY_HANDLERS[strategy](
            frontier,
            observations,
            force_explore=force_explore,
            weights=weights,
        )
    options = frontier.get("strategy_options", {})
    width = width or options.get("beam_width", 2)
    require(type(width) is int and width >= 1, "beam width must be positive")
    if strategy == "successive_halving":
        working = successive_halving(
            frontier,
            observations,
            keep_ratio=float(options.get("keep_ratio", 0.5)),
            min_keep=int(options.get("min_keep", 1)),
            weights=weights,
        )
        ranked = rank(working, observations, weights=weights)
        promoted = set(working.get("promoted", []))
        ranked = [item for item in ranked if item["scheme_id"] in promoted] + [
            item for item in ranked if item["scheme_id"] not in promoted
        ]
    elif strategy == "mcts":
        ranked = mcts_rank(
            frontier,
            observations,
            iterations=int(options.get("mcts_iterations", 64)),
            exploration=float(options.get("mcts_exploration", 1.414)),
            weights=weights,
        )
    elif strategy == "doe":
        ranked = doe_rank(frontier, observations, weights=weights)
    elif strategy == "tpe":
        ranked = tpe_rank(frontier, observations, weights=weights)
    elif strategy == "pareto":
        working = pareto_ranks(frontier, observations, weights=weights)
        ranked = rank(working, observations, weights=weights)
        ranks = {
            node["scheme_id"]: node.get("pareto_rank")
            for node in working.get("nodes", [])
        }
        ranked.sort(
            key=lambda item: (
                ranks.get(item["scheme_id"], 10**9),
                -item["utility"],
            )
        )
    elif strategy == "qd":
        ranked, qd_meta = qd_rank(frontier, observations, weights=weights)
    else:
        ranked = rank(frontier, observations, weights=weights)
    if force_explore:
        open_ranked = [
            item for item in ranked if item["node"].get("explore_tag") == "open"
        ]
        if open_ranked:
            ranked = open_ranked + [item for item in ranked if item not in open_ranked]
    chosen = ranked[0]
    beam = ranked[:width] if strategy == "beam" else []
    extra = {}
    if strategy == "successive_halving":
        extra["promoted"] = working.get("promoted", [])
        extra["eliminated"] = working.get("eliminated", [])
    if strategy == "mcts":
        extra["mcts_iterations"] = options.get("mcts_iterations", 64)
    if strategy == "doe":
        extra["doe"] = True
    if strategy == "tpe":
        extra["tpe"] = True
    if strategy == "pareto":
        extra["pareto"] = True
    if strategy == "qd":
        extra["qd"] = qd_meta
    return {
        "strategy": strategy,
        "selected": chosen["scheme_id"],
        "utility": chosen["utility"],
        "explore_forced": force_explore and chosen["node"].get("explore_tag") == "open",
        "ranking": [
            _ranking_item(
                item,
                {
                    key: item[key]
                    for key in (
                        "mcts_value",
                        "mcts_visits",
                        "doe_effect",
                        "doe_score",
                        "tpe_score",
                    )
                    if key in item
                },
            )
            for item in ranked
        ],
        "beam": [item["scheme_id"] for item in beam],
        **extra,
    }


def race(samples, *, min_samples=3, confidence=0.95, patience=2):
    """Decide whether paired candidate/best ratios justify more device time."""
    z_values = {0.9: 1.645, 0.95: 1.96, 0.99: 2.576}
    require(confidence in z_values, "race confidence must be 0.90, 0.95 or 0.99")
    require(type(min_samples) is int and min_samples >= 2, "invalid min_samples")
    require(type(patience) is int and patience >= 1, "invalid race patience")
    ratios = []
    for sample in samples or ():
        value = sample.get("ratio") if isinstance(sample, dict) else sample
        ratios.append(_finite_number(value, "race ratio", positive=True))
    if len(ratios) < min_samples:
        return {
            "decision": "continue",
            "reason": "insufficient_samples",
            "n": len(ratios),
        }
    mean = statistics.fmean(ratios)
    spread = statistics.stdev(ratios) if len(ratios) > 1 else 0.0
    margin = z_values[confidence] * spread / math.sqrt(len(ratios))
    low, high = mean - margin, mean + margin
    if high < 1.0:
        decision = "stop_winner"
    elif low > 1.0:
        decision = "stop_loser"
    else:
        decision = "continue"
    trend = ratios[-patience:]
    if decision == "continue" and len(trend) == patience:
        if all(value < 1.0 for value in trend):
            decision = "stop_winner"
        elif all(value > 1.0 for value in trend):
            decision = "stop_loser"
    return {
        "decision": decision,
        "reason": "confidence_interval"
        if decision != "continue"
        else "interval_crosses_one",
        "n": len(ratios),
        "mean": round(mean, 6),
        "low": round(low, 6),
        "high": round(high, 6),
        "confidence": confidence,
    }


def backprop(frontier, observation):
    """Apply one observation event to a frontier copy and mark node status."""
    result = copy.deepcopy(frontier)
    observation = observation or {}
    result_data = observation.get("result", observation)
    scheme = result_data.get("scheme_id")
    node = next(
        (item for item in result.get("nodes", []) if item.get("scheme_id") == scheme),
        None,
    )
    if node is None:
        return result
    outcome = result_data.get("outcome")
    mechanism = result_data.get("mechanism", {})
    if mechanism.get("status") == "refuted":
        node["status"] = "no_go"
    elif outcome == "measured":
        node["status"] = "accepted" if observation.get("promoted") else "rejected"
    elif outcome in ("implementation_failed", "precision_failed", "evidence_invalid"):
        node["status"] = "failed"
    if result_data.get("score") is not None:
        node["score"] = result_data["score"]
    if result_data.get("pareto_rank") is not None:
        node["pareto_rank"] = result_data["pareto_rank"]
    if result_data.get("prune_reason") is not None:
        node["prune_reason"] = result_data["prune_reason"]
    if result_data.get("retry_condition"):
        node["retry_condition"] = result_data["retry_condition"]
    evidence = result_data.get("evidence", [])
    node["evidence"] = list(node.get("evidence", []))
    for item in evidence:
        if item not in node["evidence"]:
            node["evidence"].append(item)
    node["children"] = [
        item["scheme_id"]
        for item in result.get("nodes", [])
        if scheme in item.get("depends_on", [])
    ]
    return result


def observed_frontier(frontier, observations=()):
    result = copy.deepcopy(frontier)
    for observation in observations or ():
        result = backprop(result, observation)
    return result


def validate_observation(result, frontier):
    """Require the statistical evidence promised by the frontier contract."""
    require(
        result.get("outcome") == "measured", "observation extension needs measurement"
    )
    distribution = result.get("score_distribution")
    if isinstance(distribution, dict):
        samples = distribution.get("samples")
    else:
        samples = distribution
    require(
        isinstance(samples, list) and samples,
        "measured frontier outcome needs score_distribution.samples",
    )
    for sample in samples:
        _finite_number(sample, "score_distribution sample", positive=True)
    case_medians = (
        isinstance(distribution, dict)
        and distribution.get("unit") == "case_median_ratio"
    )
    if case_medians:
        identifiers = distribution.get("case_ids", [])
        require(
            len(identifiers) == len(samples)
            and len(set(identifiers)) == len(identifiers),
            "case median ratios need unique case IDs",
        )
        source = distribution.get("effect_summary")
        require(
            source == result.get("effect_summary"),
            "observation summary differs from evaluated effect summary",
        )
        verify_file_ref(source, {})
        summary = load(source["path"])
        require(
            recompute_summary(summary) == summary,
            "case median summary is stale or altered",
        )
        require(
            identifiers == [c["case_id"] for c in summary["cases"]]
            and samples
            == [
                c["candidate_total_us"] / c["baseline_total_us"]
                for c in summary["cases"]
            ],
            "case median ratios differ from effect summary",
        )
    # A case's median is not a repeat. Do not invent a CI across case medians.
    if not case_medians or result.get("confidence_interval") is not None:
        interval = result.get("confidence_interval")
        require(
            isinstance(interval, dict)
            and isinstance(interval.get("low"), (int, float))
            and isinstance(interval.get("high"), (int, float))
            and not isinstance(interval.get("low"), bool)
            and not isinstance(interval.get("high"), bool)
            and interval["low"] <= interval["high"],
            "measured frontier outcome needs confidence_interval low <= high",
        )
        confidence = interval.get("confidence", 0.95)
        require(
            isinstance(confidence, (int, float))
            and not isinstance(confidence, bool)
            and 0 < confidence < 1,
            "invalid confidence_interval.confidence",
        )
    require(
        type(result.get("pareto_rank")) is int and result["pareto_rank"] >= 1,
        "measured frontier outcome needs a positive pareto_rank",
    )
    if result.get("race") is not None:
        require(
            isinstance(result["race"], dict)
            and result["race"].get("decision")
            in ("continue", "stop_winner", "stop_loser"),
            "invalid race decision",
        )
    if result.get("prune_reason") is not None:
        require(
            isinstance(result["prune_reason"], str) and result["prune_reason"].strip(),
            "prune_reason must be nonempty",
        )


def reanchor_targets(summary, source, *, ratio=0.95):
    """Build the next internal search target after a promotion.

    The frozen user target is untouched; this is the search-internal re-anchor
    (a relative 5% step or the next roofline target when the caller supplies one).
    """
    require(0 < ratio < 1, "reanchor ratio must be in (0, 1)")
    cases = summary.get("cases")
    require(isinstance(cases, list) and cases, "reanchor needs measured cases")
    targets = []
    for case in cases:
        value = _finite_number(
            case.get("candidate_total_us"), "reanchor candidate_total_us", positive=True
        )
        targets.append(
            {
                "case_id": case["case_id"],
                "target_total_us": round(value * ratio, 6),
            }
        )
    return {
        "mode": "relative_5pct",
        "ratio": ratio,
        "source": source,
        "targets": targets,
    }


def case_ids(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    ids = []
    for index, row in enumerate(rows):
        # 与 prepare_case_sets.case_id 的 ID 解析对齐：无 ID 列时回退到
        # 位置编号 row-{index+2}（表头占第 1 行的 Excel 行号口径）。
        value = next(
            (row[k] for k in ("case_id", "id", "case", "name") if row.get(k)),
            None,
        )
        ids.append(value if value else f"row-{index + 2}")
    require(
        ids and all(ids) and len(ids) == len(set(ids)), "workload needs unique case IDs"
    )
    return ids


def validate_workload(contract, manifest, ids, dependencies):
    config = manifest["configuration"]
    key = (
        "generalization_full"
        if config.get("tuning_mode") == "generalization"
        else "performance_tuning"
    )
    inventory = manifest.get("collections", {}).get(key, {})
    frozen = {k: inventory[k] for k in ("path", "sha256") if k in inventory}
    verify_ref(frozen, dependencies)
    frozen_ids = case_ids(frozen["path"])
    require(set(ids) <= set(frozen_ids), "workload escapes frozen inventory")
    if key == "performance_tuning":
        require(ids == frozen_ids, "standard workload differs from frozen tuning set")
    require(
        contract.get("target_socs") == config.get("target_socs"),
        "target SoCs differ",
    )
    require(
        contract.get("backend", "ascendc") == config.get("backend", "ascendc"),
        "backend differs",
    )


def validate_parent(search, baseline):
    parent = search.get("parent")
    # Git-native form (AscendC worktree flow): the parent implementation is the
    # frozen baseline revision; conformance enforces commit/tree equality there.
    if is_git_identity(parent):
        require(
            all(
                re.fullmatch(r"[0-9a-f]{40}", parent[name])
                for name in ("commit", "tree")
            ),
            "invalid git parent identity",
        )
        require(
            baseline is None,
            "git parent identity cannot be checked against a directory baseline",
        )
        return
    require(
        isinstance(parent, dict) and set(parent) == {"path", "sha256"},
        "missing parent source identity",
    )
    require(
        source_identity(Path(parent["path"])) == parent,
        "parent source identity changed",
    )
    if baseline is not None:
        require(
            source_identity(Path(baseline)) == parent,
            "implementation baseline differs from decision parent",
        )


def validate_contract(contract, manifest=None, baseline=None):
    """Validate metadata without inventing a second implementation contract."""
    required = manifest is not None and enabled(manifest)
    if "search" not in contract:
        require(not required, "implementation contract requires search metadata")
        return []
    search = contract["search"]
    require(isinstance(search, dict), "contract.search must be an object")
    checked_case_bucket(search, "search.case_bucket")
    require(search.get("kind") in ("architecture", "local"), "invalid decision kind")
    for name in ("mechanism", "mechanism_check"):
        require(
            isinstance(search.get(name), str) and search[name].strip(),
            f"missing {name}",
        )
    scheme = contract.get("scheme_id")
    require(
        isinstance(scheme, str) and re.fullmatch(r"[A-Za-z0-9_-]+", scheme),
        "invalid scheme_id",
    )
    parents = search.get("depends_on")
    require(
        isinstance(parents, list)
        and all(isinstance(x, str) and x for x in parents)
        and len(parents) == len(set(parents))
        and scheme not in parents,
        "dependencies must be unique decision IDs without self-dependency",
    )
    if "fidelity" in search:
        require(search["fidelity"] in FIDELITIES, "invalid search.fidelity")
    if "expected_gain_range" in search:
        gain_range(search["expected_gain_range"], "search.expected_gain_range")
    if "cost" in search:
        _finite_number(search["cost"], "search.cost", nonnegative=True)
    if "frontier_parent" in search:
        require(
            isinstance(search["frontier_parent"], str)
            and search["frontier_parent"].strip(),
            "search.frontier_parent must be a frontier node ID",
        )
    if "candidate_factors" in search:
        require(
            isinstance(search["candidate_factors"], dict)
            and all(
                isinstance(name, str)
                and name
                and isinstance(value, (str, int, float, bool))
                for name, value in search["candidate_factors"].items()
            ),
            "search.candidate_factors must map names to scalar values",
        )
    if "candidate_bindings" in search:
        require(
            isinstance(search["candidate_bindings"], dict),
            "search.candidate_bindings must be an object",
        )
    validate_parent(search, baseline)
    dependencies = checked_refs(search.get("trigger"), "trigger")
    if "candidate_evidence" in search:
        dependencies.extend(
            checked_refs(search["candidate_evidence"], "candidate_evidence")
        )
    for name in ("workload", "baseline_performance"):
        verify_ref(search.get(name), dependencies)
    ids = case_ids(search["workload"]["path"])
    require(
        contract.get("case_ids") == ids, "contract cases must match ordered workload"
    )
    require(
        case_ids(search["baseline_performance"]["path"]) == ids,
        "baseline performance coverage differs",
    )
    if manifest is not None:
        validate_workload(contract, manifest, ids, dependencies)
    retry = search.get("retry")
    if retry is not None:
        require(
            isinstance(retry, dict)
            and retry.get("decision_id")
            and retry.get("reason"),
            "invalid retry",
        )
        dependencies.extend(checked_refs(retry.get("evidence"), "retry"))
    return dependencies


def contracts(paths):
    found = []
    for raw_path in paths:
        path = Path(raw_path)
        if path.suffix == ".json" and path.name.startswith("implementation-contract-"):
            found.append((path, load(path)))
    return found


def frontiers(paths):
    found = []
    for raw_path in paths:
        path = Path(raw_path)
        if path.suffix == ".json" and path.name.startswith("candidate-frontier-"):
            found.append((path, load(path)))
    return found


def context(contract):
    search = contract["search"]
    value = {
        "parent": search["parent"],
        "workload": search["workload"]["sha256"],
        "socs": contract["target_socs"],
        "backend": contract.get("backend", "ascendc"),
    }
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def reopened_decisions(decisions, reopen):
    affected = set(reopen)
    while True:
        children = {
            sid
            for sid, (_, contract) in decisions.items()
            if affected.intersection(contract["search"]["depends_on"])
        }
        if children <= affected:
            return affected
        affected |= children


def replay(state):
    """Rebuild counters and applicability; repeated checkpoints cannot add trials."""
    decisions, results, retired, accepted = {}, {}, set(), set()
    frontiers_by_round, frontier = {}, None
    anchor, anchor_decision, streak, scope = None, None, 0, None
    reanchor = None
    action = "analyze"
    for event in state.get("events", []):
        if event.get("invalidated"):
            continue  # Legacy invalidated events remain audit-only.
        kind = event.get("kind")
        if kind == "search_plan":
            contract = load(event["contract"]["path"])
            decisions[contract["scheme_id"]] = (event, contract)
            anchor = anchor or contract["search"]["parent"]
            action = "implement"
        elif kind == "search_frontier":
            frontier = load(event["frontier"]["path"])
            frontiers_by_round[event["round"]] = frontier
        elif kind == "search_result":
            result = event["result"]
            scheme = result.get("scheme_id")
            if scheme:
                results[scheme] = event
            if event.get("context") != scope:
                streak, scope = 0, event.get("context")
            if event["classification"] == "no_improvement":
                streak += 1
            if event.get("promoted"):
                anchor, anchor_decision = event["promoted"], scheme
                accepted.add(scheme)
                streak = 0
                if event.get("reanchor"):
                    reanchor = event["reanchor"]
            action = {
                "inconclusive": "confirm",
                "evidence_invalid": "repair_evidence",
                "implementation_failed": "repair_candidate",
                "precision_failed": "repair_candidate",
                "no_candidate": "replan",
            }.get(event["classification"], "analyze")
            if streak >= PATIENCE:
                action = "replan"
        elif kind == "search_replan":
            retired |= reopened_decisions(decisions, event["reopen"])
            streak, scope, action = 0, None, "analyze"
    return {
        "decisions": decisions,
        "results": results,
        "frontiers": frontiers_by_round,
        "frontier": (
            observed_frontier(frontier, list(results.values())) if frontier else None
        ),
        "retired": retired,
        "accepted": accepted,
        "anchor": anchor,
        "anchor_decision": anchor_decision,
        "reanchor": reanchor,
        "stagnation": streak,
        "context": scope,
        "next_action": action,
    }


def append_once(state, event, key):
    for old in state.get("events", []):
        if old.get("kind") == event["kind"] and old.get(key) == event[key]:
            require(
                old == event,
                "checkpoint already recorded with different search evidence",
            )
            return False
    state.setdefault("events", []).append(event)
    return True


def validate_retry(current, contract):
    search = contract["search"]
    for prior_id, prior in reversed(list(current["results"].items())):
        previous = current["decisions"][prior_id][1]["search"]
        if (
            prior.get("context") == context(contract)
            and previous["mechanism"] == search["mechanism"]
            and prior["classification"]
            in (
                "no_improvement",
                "implementation_failed",
                "precision_failed",
                "evidence_invalid",
            )
        ):
            retry = search.get("retry", {})
            require(
                retry.get("decision_id") == prior_id,
                "retry needs the failed decision and changed conditions",
            )
            known = {r["sha256"] for r in prior["artifacts"]}
            require(
                any(r["sha256"] not in known for r in retry.get("evidence", [])),
                "retry needs new evidence",
            )
            break


def require_analysis_ready(state, current):
    require(
        not verify(state),
        "restore accepted search stages before freezing another decision",
    )
    require(
        state.get("stages", {}).get("phase.baseline", {}).get("status") == "complete",
        "baseline acceptance is incomplete",
    )
    finished = {
        e["round"] for e in state.get("events", []) if e.get("kind") == "search_result"
    }
    require(
        all(e["round"] in finished for e, _ in current["decisions"].values()),
        "complete the current round before freezing another decision",
    )
    require(
        current["next_action"] != "replan",
        "architecture review required before another decision",
    )


def register_analysis(state, stage, paths, manifest):
    found = contracts(paths)
    require(len(found) <= 1, "each round may freeze only one implementation contract")
    if not enabled(manifest):
        return []
    found_frontiers = frontiers(paths)
    require(len(found_frontiers) <= 1, "each round may register one candidate frontier")
    if not found:
        if not found_frontiers:
            return []
        frontier_path, frontier = found_frontiers[0]
        require(
            frontier.get("nodes") == [], "analysis without a contract needs nodes: []"
        )
        require(
            frontier.get("round") == stage.removesuffix(".analysis"),
            "frontier round differs from the analysis round",
        )
        _, scope, dependencies = coverage_inputs(state, frontier)
        require(scope is not None, "analysis-only frontier needs a workload receipt")
        current = replay(state)
        dependencies.append(ref(frontier_path))
        event = {
            "kind": "search_frontier",
            "round": frontier["round"],
            "frontier": ref(frontier_path),
            "selected": None,
            "pruned": [],
            "artifacts": dependencies,
            "sources": [frontier["parent"]],
        }
        if frontier["round"] in current["frontiers"]:
            append_once(state, event, "round")
            return dependencies
        require_analysis_ready(state, current)
        if current["anchor"]:
            require(
                frontier["parent"] == current["anchor"],
                "audit parent is not the retained implementation",
            )
        append_once(state, event, "round")
        return dependencies
    path, contract = found[0]
    dependencies = validate_contract(contract, manifest)
    current = replay(state)
    scheme = contract["scheme_id"]
    round_name = stage.removesuffix(".analysis")
    integration = manifest.get("configuration", {}).get("search_integration", "off")
    if integration == "medium" and not found_frontiers:
        raise ValueError(
            "search: medium integration requires candidate-frontier-<scheme_id>.json"
        )
    if found_frontiers:
        frontier_path, frontier = found_frontiers[0]
        require(
            frontier.get("round") == round_name,
            "frontier round differs from the analysis round",
        )
        for name in ("frontier_parent", "fidelity", "expected_gain_range", "cost"):
            require(
                name in contract["search"],
                f"search.{name} is required when a candidate frontier is attached",
            )
        dependencies.extend(
            validate_frontier(
                frontier,
                contract,
                manifest,
                accepted=current["accepted"] - current["retired"],
            )
        )
        dependencies.append(ref(frontier_path))
    else:
        require(
            not any(
                name in contract["search"]
                for name in (
                    "frontier_parent",
                    "fidelity",
                    "expected_gain_range",
                    "cost",
                )
            ),
            "frontier metadata requires candidate-frontier-<scheme_id>.json",
        )
    old = current["decisions"].get(scheme)
    if old:
        require(
            old[0]["contract"] == ref(path) and old[0]["round"] == round_name,
            "decision IDs are immutable and round-specific",
        )
        return dependencies
    require_analysis_ready(state, current)
    search = contract["search"]
    if current["anchor"]:
        require(
            search["parent"] == current["anchor"],
            "decision parent is not the retained implementation",
        )
    require(
        set(search["depends_on"]) <= current["accepted"] - current["retired"],
        "dependencies must be accepted, applicable decisions",
    )
    validate_retry(current, contract)
    for event, _ in current["decisions"].values():
        require(
            event["round"] != round_name,
            "round already has a decision; replan in the next round",
        )
    event = {
        "kind": "search_plan",
        "round": round_name,
        "contract": ref(path),
        "artifacts": [ref(path), *dependencies],
        "sources": [search["parent"]],
    }
    if found_frontiers:
        event["frontier"] = ref(found_frontiers[0][0])
    append_once(state, event, "round")
    if found_frontiers:
        frontier_path, frontier = found_frontiers[0]
        selected = next(
            node
            for node in frontier["nodes"]
            if node["scheme_id"] == contract["scheme_id"]
        )
        frontier_event = {
            "kind": "search_frontier",
            "round": round_name,
            "frontier": ref(frontier_path),
            "selected": selected["scheme_id"],
            "pruned": [
                {
                    "scheme_id": node["scheme_id"],
                    "prune_reason": node.get("prune_reason"),
                }
                for node in frontier["nodes"]
                if node.get("status") == "pruned"
            ],
            "artifacts": [ref(frontier_path)],
            "sources": [],
        }
        append_once(state, frontier_event, "round")
    return dependencies


def check_handoff(state, stage):
    match = re.fullmatch(rf"({ROUND})\.impl\.([^.]+)", stage)
    if not match or "search_policy" not in state:
        return
    current = replay(state)
    entry = current["decisions"].get(match[2])
    require(
        entry and entry[0]["round"] == match[1], "scheme was not frozen for this round"
    )
    analysis = state.get("stages", {}).get(f"{match[1]}.analysis", {})
    require(
        analysis.get("status") == "complete"
        and any(
            a["path"] == entry[0]["contract"]["path"]
            and a["sha256"] == entry[0]["contract"]["sha256"]
            for a in analysis.get("artifacts", [])
        ),
        "analysis handoff is missing or invalid",
    )
    require(
        match[2] not in current["retired"],
        "decision was reopened; re-analyze its dependencies",
    )
    require(
        entry[1]["search"]["parent"] == current["anchor"], "retained parent changed"
    )
    require(
        set(entry[1]["search"]["depends_on"])
        <= current["accepted"] - current["retired"],
        "decision depends on a reopened mechanism",
    )


def checked_summary(reference, manifest):
    dependencies = []
    verify_ref(reference, dependencies)
    summary = load(reference["path"])
    frozen = effect_policy(manifest["configuration"].get("performance_effect_policy"))
    actual = effect_policy(
        {
            "id": summary.get("policy_id", "legacy_jitter_v1"),
            "version": summary.get("policy_version", 1),
        }
    )
    require(actual == frozen, "effect policy differs from manifest")
    computed = recompute_summary(summary)
    require(
        all(summary.get(k) == v for k, v in computed.items()),
        "effect summary differs from evidence",
    )
    paths = [
        summary["baseline_path"],
        summary["candidate_path"],
        *summary_dependency_paths(summary),
    ]
    dependencies.extend(ref(p) for p in paths)
    return summary, dependencies


def classify(summary):
    if summary.get("inconclusive_case_count", 0):
        return "inconclusive"
    if (
        summary.get("effective_improvement_count", 0)
        and (summary.get("effective_geomean_speedup") or 0) > 1
    ):
        return "improvement"
    return "no_improvement"


def round_plan(state, current, round_name):
    analysis = state.get("stages", {}).get(f"{round_name}.analysis", {})
    require(analysis.get("status") == "complete", "round analysis is incomplete")
    plan = next(
        (
            entry
            for entry in current["decisions"].values()
            if entry[0]["round"] == round_name
        ),
        None,
    )
    if plan:
        recorded = any(
            e.get("kind") == "search_result" and e["round"] == round_name
            for e in state.get("events", [])
        )
        require(
            recorded or plan[1]["scheme_id"] not in current["retired"],
            "decision was reopened; re-analyze before evaluation",
        )
    return plan


def round_selection(record, plan):
    selections = [
        a for a in record["artifacts"] if Path(a["path"]).name == "selection.json"
    ]
    require(len(selections) == 1, "round requires one selection.json")
    selection = selections[0]
    result = load(selection["path"]).get("search")
    require(
        isinstance(result, dict) and result.get("outcome") in OUTCOMES,
        "selection.search needs an outcome",
    )
    expected = plan[1]["scheme_id"] if plan else None
    require(
        result.get("scheme_id") == expected,
        "selection decision differs from round contract",
    )
    require(
        (result["outcome"] == "no_candidate") == (plan is None),
        "no_candidate requires an analysis without a contract",
    )
    checked_case_bucket(
        result, "selection.search.case_bucket", legacy_null=True
    )
    if plan:
        contract_search = plan[1]["search"]
        checked_case_bucket(contract_search, "search.case_bucket")
        if "case_bucket" in result or "case_bucket" in contract_search:
            require(
                result.get("case_bucket") == contract_search.get("case_bucket"),
                "selection.search.case_bucket differs from contract.search",
            )
    artifacts = [
        ref(selection["path"]),
        *checked_refs(result.get("evidence"), "outcome"),
    ]
    mechanism = result.get("mechanism", {})
    require(
        mechanism.get("status") in ("verified", "refuted", "unknown"),
        "invalid mechanism verdict",
    )
    if mechanism["status"] != "unknown":
        artifacts.extend(checked_refs(mechanism.get("evidence"), "mechanism"))
    require(
        isinstance(result.get("retry_condition"), str)
        and result["retry_condition"].strip(),
        "outcome needs a retry condition or an evidence-backed not_applicable reason",
    )
    return result, artifacts


def accepted_implementation(state, plan, gate_ref, artifacts):
    event, contract = plan
    stage = f"{event['round']}.impl.{contract['scheme_id']}"
    implementation = state.get("stages", {}).get(stage, {})
    require(
        implementation.get("status") == "complete",
        "implementation acceptance is incomplete",
    )
    require(
        any(
            a["path"] == gate_ref["path"] and a["sha256"] == gate_ref["sha256"]
            for a in implementation.get("artifacts", [])
        ),
        "gate absent from accepted implementation",
    )
    artifacts.extend(
        {k: a[k] for k in ("path", "sha256")}
        for a in implementation["artifacts"]
        if a.get("kind") == "file"
    )


def candidate_gate(state, plan, result, artifacts):
    from validate_implementation_conformance import verify_gate

    gate_ref = result.get("conformance_gate")
    verify_ref(gate_ref, artifacts)
    gate = verify_gate(Path(gate_ref["path"]))
    identity = gate["evidence_identity"]
    require(
        identity["contract"] == plan[0]["contract"], "gate belongs to another decision"
    )
    require(identity["baseline"] == plan[1]["search"]["parent"], "gate parent differs")
    artifacts.extend(
        identity[name] for name in ("contract", "result", "manifest", "isolation_scope")
    )
    artifacts.extend(
        {"path": p, "sha256": sha} for p, sha in identity["feature_evidence"].items()
    )
    schedule = gate.get("schedule")
    if schedule:
        artifacts.extend(schedule[name] for name in ("model", "runtime"))
        artifacts.extend(
            {"path": p, "sha256": sha}
            for p, sha in schedule["report"]["dependencies"].items()
        )
    accepted_implementation(state, plan, gate_ref, artifacts)
    return identity


def checked_measurement(result, manifest, contract, identity, artifacts):
    summary, dependencies = checked_summary(result.get("effect_summary"), manifest)
    artifacts.extend(dependencies)
    require(
        ref(summary["baseline_path"]) == contract["search"]["baseline_performance"],
        "comparison uses a different baseline",
    )
    require(
        [c["case_id"] for c in summary["cases"]] == contract["case_ids"],
        "effect coverage differs",
    )
    for case in summary["cases"]:
        if not case.get("proof_path"):
            continue
        proof = load(case["proof_path"])
        require(
            proof["target_soc"] in contract["target_socs"],
            "performance proof targets another SoC",
        )
        for side in ("baseline", "candidate"):
            measured_source = proof["source_identities"][proof[f"{side}_variant"]][
                "source"
            ]
            checked_source_identity(
                measured_source,
                identity[side],
                f"performance proof belongs to another {side} implementation",
            )
    if result.get("outcome") == "screened":
        checked_screening(result, manifest, contract, identity, summary, artifacts)
    else:
        require(
            classify(summary) != "inconclusive",
            "comparison is inconclusive; confirm before completing this round",
        )
    return summary


def candidate_selection(record, result, summary, candidate, manifest, baseline_names):
    selected = record["performance"]["selected_candidate"]
    classification = classify(summary)
    screened = result.get("outcome") == "screened"
    # Git-mode candidate identity: {commit, tree}; directory mode: {path, sha256}.
    candidate_names = {result["scheme_id"]}
    if isinstance(candidate, dict):
        candidate_names.add(candidate.get("path", candidate.get("commit")))
    if selected not in candidate_names:
        require(
            selected in baseline_names,
            "selection is neither the candidate nor the retained baseline",
        )
        # Ratio/retreat/complexity selection remains owned by the stage's existing policy.
        return ("screening_retained" if screened else "no_improvement"), None
    if screened:
        ratios = [c["speedup"] for c in summary["cases"]]
        require(
            sum(math.log(r) for r in ratios) > 0,
            "provisional selection needs observed net improvement",
        )
        classification = "provisional_improvement"
    else:
        require(
            classification == "improvement", "promotion needs measured net improvement"
        )
    require(
        ref(record["performance"]["round_summary"]) == result["effect_summary"],
        "promoted performance differs from evaluated candidate",
    )
    return classification, candidate


def retained_summary(record, manifest, plan, artifacts):
    kept, dependencies = checked_summary(
        ref(record["performance"]["round_summary"]), manifest
    )
    artifacts.extend(dependencies)
    if plan:
        require(
            ref(kept["baseline_path"]) == plan[1]["search"]["baseline_performance"],
            "retained comparison uses another baseline",
        )
    require(
        all(c["baseline_total_us"] == c["candidate_total_us"] for c in kept["cases"]),
        "retained baseline must use its own performance evidence",
    )


def complete_round(state, stage, record, manifest):
    """Consume the one decision's outcome, including a rejected candidate's evidence."""
    if not enabled(manifest):
        return []
    current = replay(state)
    round_name = stage.removesuffix(".complete")
    require(
        not verify(state), "restore accepted search stages before completing the round"
    )
    plan = round_plan(state, current, round_name)
    result, artifacts = round_selection(record, plan)
    if needs_observation_gate(result, round_name in current["frontiers"]):
        validate_observation(result, current["frontiers"][round_name])
    classification, promoted = result["outcome"], None
    reanchor = None
    sources = [plan[1]["search"]["parent"]] if plan else []
    baseline_names = {"baseline", current["anchor_decision"]}
    if current["anchor"]:
        anchor = current["anchor"]
        if is_git_identity(anchor):
            # Git-mode anchor: identified by commit hash, not a directory path.
            baseline_names.add(anchor["commit"])
        else:
            baseline_names.add(anchor["path"])
    if needs_measurement(result):
        identity = candidate_gate(state, plan, result, artifacts)
        summary = checked_measurement(result, manifest, plan[1], identity, artifacts)
        sources.append(identity["candidate"])
        classification, promoted = candidate_selection(
            record, result, summary, identity["candidate"], manifest, baseline_names
        )
        if promoted is not None:
            reanchor = reanchor_targets(summary, result["effect_summary"])
    else:
        require(
            record["performance"]["selected_candidate"] in baseline_names,
            "unevaluated candidate cannot be promoted",
        )
    if promoted is None:
        retained_summary(record, manifest, plan, artifacts)
    event = {
        "kind": "search_result",
        "round": round_name,
        "result": result,
        "classification": classification,
        "context": context(plan[1]) if plan else None,
        "promoted": promoted,
        "reanchor": reanchor,
        "artifacts": artifacts,
        "sources": sources,
    }
    if reanchor is None:
        event.pop("reanchor", None)
    append_once(state, event, "round")
    return artifacts


def replan(state, reason, reopen, evidence, message):
    require(
        reason in REPLAN_REASONS and message.strip(),
        "replan needs a reason and diagnosis",
    )
    current = replay(state)
    require(set(reopen) <= set(current["decisions"]), "unknown reopened decision")
    finished = {
        e["round"] for e in state.get("events", []) if e.get("kind") == "search_result"
    }
    require(
        all(e["round"] in finished for e, _ in current["decisions"].values()),
        "complete the active round before architecture review",
    )
    artifacts = checked_refs([ref(p) for p in evidence], "replan")
    event = {
        "kind": "search_replan",
        "reason": reason,
        "reopen": sorted(set(reopen)),
        "message": message,
        "artifacts": artifacts,
        "sources": [],
        "after_round": next(
            (
                e["round"]
                for e in reversed(state.get("events", []))
                if e.get("kind") == "search_result"
            ),
            None,
        ),
    }
    if event in state.get("events", []):
        return
    if reason == "plateau":
        require(
            current["stagnation"] >= PATIENCE,
            "plateau needs three comparable unsuccessful evaluations",
        )
    state.setdefault("events", []).append(event)


def event_owners(event):
    if event["kind"] in ("search_plan", "search_frontier"):
        return [f"{event['round']}.analysis"]
    if event["kind"] != "search_result":
        return []
    owners = [f"{event['round']}.complete"]
    if needs_measurement(event["result"]):
        owners.append(f"{event['round']}.impl.{event['result']['scheme_id']}")
    return owners


def verify(state, *, check_stages=True):
    errors = []
    for event in state.get("events", []):
        if not event.get("kind", "").startswith("search_"):
            continue
        if event.get("invalidated"):
            continue  # Legacy invalidated events remain audit-only.
        owners = event_owners(event) if check_stages else []
        errors.extend(
            {
                "kind": "search_stage",
                "stage": stage,
                "reason": f"search acceptance invalidated: {stage}",
            }
            for stage in owners
            if state.get("stages", {}).get(stage, {}).get("status") != "complete"
        )
        try:
            for artifact in event.get("artifacts", []):
                verify_ref(artifact, [])
            for source in event.get("sources", []):
                if is_git_identity(source):
                    # Git-mode parent: identity is the commit+tree pair; validated
                    # by conformance's _validate_search_parent_git, not directory hashing.
                    continue
                require(
                    source_identity(Path(source["path"])) == source,
                    "search source changed",
                )
        except (OSError, ValueError, KeyError, TypeError) as error:
            errors.append(
                {
                    "kind": "search_evidence",
                    "round": event.get("round"),
                    "reason": str(error),
                }
            )
    for entry in state.get("structural_directions", []):
        if (
            entry["id"].startswith(AXIS_DIRECTION_PREFIX)
            and entry.get("status") in EXCLUDED_DIRECTION_STATUSES
        ):
            try:
                verify_exclusion(entry)
            except (OSError, ValueError, KeyError, TypeError) as error:
                errors.append(
                    {
                        "kind": "search_exclusion",
                        "direction_id": entry["id"],
                        "reason": str(error),
                    }
                )
    return errors


def accepted_from_state(path):
    """Read applicable dependencies from the existing verified workflow state."""
    if path is None:
        return set()
    state = load(path)
    require("search_policy" in state, "search policy is not enabled in state")
    verify_ref({key: state["manifest"][key] for key in ("path", "sha256")}, [])
    errors = verify(state)
    require(not errors, f"restore accepted search evidence before planning: {errors}")
    current = replay(state)
    return current["accepted"] - current["retired"]


def coverage_inputs(state, frontier, contract=None):
    """Validate an audit scope without requiring selectable implementation nodes."""
    require(frontier.get("schema_version") == 1, "unsupported frontier schema_version")
    require(
        isinstance(frontier.get("round"), str)
        and re.fullmatch(ROUND, frontier["round"]),
        "frontier needs a round name",
    )
    dependencies = []
    space = checked_space(frontier.get("candidate_space"), dependencies)
    validate_parent({"parent": frontier.get("parent")}, None)
    verify_ref(
        {key: state["manifest"][key] for key in ("path", "sha256")}, dependencies
    )
    manifest = load(state["manifest"]["path"])
    if contract is None:
        contract = next(
            (
                c
                for event, c in replay(state)["decisions"].values()
                if event["round"] == frontier["round"]
            ),
            None,
        )
    if contract is None and frontier.get("workload"):
        config = manifest["configuration"]
        contract = {
            "target_socs": config["target_socs"],
            "backend": config.get("backend", "ascendc"),
            "search": {
                "parent": frontier["parent"],
                "workload": frontier["workload"],
                "mechanism": space.get("mechanism"),
            },
        }
    if contract is not None:
        scope = contract["search"]
        require(
            frontier["parent"] == scope["parent"],
            "frontier parent differs from contract",
        )
        require(
            isinstance(scope.get("mechanism"), str) and scope["mechanism"].strip(),
            "coverage needs an explicit mechanism",
        )
        verify_ref(scope["workload"], dependencies)
        validate_workload(
            contract, manifest, case_ids(scope["workload"]["path"]), dependencies
        )
    return space, contract, dependencies


def axis_coverage(state, frontier, contract=None):
    """Audit declared axis values against accepted measurements, not generation.

    This is an input to the existing direction ledger, not a no-go verdict:
    testing each value does not prove that every combination was explored.
    """
    source = frontier.get("candidate_space")
    if source is None:
        return {
            "status": "unavailable",
            "reason": "frontier has no candidate_space receipt",
        }
    errors = verify(state)
    require(
        not errors, f"restore accepted search evidence before coverage audit: {errors}"
    )
    space, contract, _ = coverage_inputs(state, frontier, contract)
    if contract is None:
        return {
            "status": "unavailable",
            "reason": "coverage needs the current contract or an analysis workload receipt",
        }
    current = replay(state)

    # Ignore round-specific knowledge receipts and cost estimates; keep the
    # actual axis definitions, bindings and feasibility constraints comparable.
    def definition(value):
        return {key: value.get(key) for key in ("axes", "bindings", "constraints")}

    measured, evidence = [], []
    for scheme, result in current["results"].items():
        if scheme in current["retired"] or result["result"]["outcome"] != "measured":
            continue
        plan, previous = current["decisions"][scheme]
        if (
            context(previous) != context(contract)
            or previous["search"]["mechanism"] != contract["search"]["mechanism"]
        ):
            continue
        old_frontier = current["frontiers"].get(plan["round"], {})
        old_source = old_frontier.get("candidate_space")
        if not old_source:
            continue
        verify_ref(old_source, [])
        if definition(load(old_source["path"])) != definition(space):
            continue
        node = next(n for n in old_frontier["nodes"] if n["scheme_id"] == scheme)
        measured.append(node.get("factors", {}))
        evidence.append(
            {
                "contract": plan["contract"],
                "effect_summary": result["result"]["effect_summary"],
            }
        )
    axes, untested_directions = {}, []
    scope = [context(contract), contract["search"]["mechanism"], definition(space)]
    for axis in space["axes"]:
        name, values = axis["name"], axis["values"]
        tested = [
            value
            for value in values
            if any(name in row and row[name] == value for row in measured)
        ]
        axes[name] = {
            "tested": tested,
            "untested": [value for value in values if value not in tested],
        }
        for value in axes[name]["untested"]:
            identity = json.dumps([scope, name, value], sort_keys=True).encode()
            untested_directions.append(
                {
                    "id": AXIS_DIRECTION_PREFIX + hashlib.sha256(identity).hexdigest(),
                    "axis": name,
                    "value": value,
                }
            )
    return {
        "status": "audited",
        "candidate_space": source,
        "axes": axes,
        "untested_directions": untested_directions,
        "evidence": evidence,
        "is_exhaustion_proof": False,
    }


def verify_exclusion(entry):
    proof = entry.get("evidence_ref")
    require(
        proof and proof.get("path") == entry.get("evidence"),
        f"no-go exclusion needs frozen evidence: {entry['id']}",
    )
    verify_ref(proof, [])


def require_no_go(state, coverage):
    """Require measured values or explicit, scoped exclusions in the existing ledger."""
    require(coverage.get("status") == "audited", "no-go needs candidate-space coverage")
    ledger = {entry["id"]: entry for entry in state.get("structural_directions", [])}
    for direction in coverage["untested_directions"]:
        entry = ledger.get(direction["id"], {})
        label = f"{direction['axis']}={direction['value']} ({direction['id']})"
        require(
            entry.get("status") in EXCLUDED_DIRECTION_STATUSES,
            f"no-go blocked: unmeasured direction needs evidenced exclusion: {label}",
        )
        verify_exclusion(entry)


def require_search_no_go(state):
    """Audit all registered search spaces before a terminal no-go claim."""
    verify_ref({key: state["manifest"][key] for key in ("path", "sha256")}, [])
    errors = verify(state)
    require(not errors, f"restore accepted search evidence before no-go: {errors}")
    current = replay(state)
    for event, _ in current["decisions"].values():
        require(
            event["round"] in current["frontiers"],
            f"no-go needs a candidate space for {event['round']}",
        )
    require(current["frontiers"], "no-go needs a registered candidate space")
    for frontier in current["frontiers"].values():
        require_no_go(state, axis_coverage(state, frontier))


def view(state):
    if "search_policy" not in state:
        return None
    errors = verify(state)
    if errors:
        return {"next_action": "repair_evidence", "errors": errors}
    current = replay(state)
    action = (
        "complete"
        if state.get("terminal", {}).get("status") == "success"
        else current["next_action"]
    )
    frontier_state = None
    if current["frontier"]:
        observed = current["frontier"]
        pending = [
            node
            for node in observed.get("nodes", [])
            if node.get("status") in ("candidate", "selected")
            and not node.get("prune_reason")
        ]
        explore_every = observed.get("explore_every", DEFAULT_EXPLORE_EVERY)
        explore_due = (
            bool(current["results"])
            and (len(current["results"]) % explore_every == 0)
            and any(node.get("explore_tag") == "open" for node in pending)
        )
        observations = [
            observation_payload(sid, event, current["decisions"])
            for sid, event in current["results"].items()
        ]
        choice = (
            select(
                observed,
                observations,
                strategy=observed.get("strategy", DEFAULT_STRATEGY),
                force_explore=explore_due,
            )
            if pending
            else None
        )
        utility_by_id = {
            item["scheme_id"]: item["utility"]
            for item in (choice["ranking"] if choice else [])
        }
        if action in ("analyze", "explore", "exploit", "race") and pending:
            last = list(current["results"].values())[-1] if current["results"] else None
            if last and last["result"].get("race", {}).get("decision") == "continue":
                action = "race"
            elif explore_due:
                action = "explore"
            else:
                action = "exploit"
        frontier_state = {
            "round": observed.get("round"),
            "n": observed.get("n", DEFAULT_N),
            "best_total_us": observed.get("best_total_us"),
            "selected": choice["selected"] if choice else None,
            "explore_due": explore_due,
            "beam": choice["beam"] if choice else [],
            "pruned": [
                {
                    "scheme_id": node["scheme_id"],
                    "prune_reason": node.get("prune_reason"),
                }
                for node in observed.get("nodes", [])
                if node.get("status") == "pruned"
            ],
            "nodes": [
                {
                    "scheme_id": node["scheme_id"],
                    "kind": node.get("kind"),
                    "level": node.get("level"),
                    "mechanism": node.get("mechanism"),
                    "fidelity": node.get("fidelity"),
                    "status": node.get("status"),
                    "explore_tag": node.get("explore_tag"),
                    "pareto_rank": node.get("pareto_rank"),
                    "utility": utility_by_id.get(node["scheme_id"]),
                }
                for node in observed.get("nodes", [])
            ],
        }
    return {
        "next_action": action,
        "stagnation": current["stagnation"],
        "patience": PATIENCE,
        "anchor": current["anchor"],
        "reanchor": current.get("reanchor"),
        "frontier": frontier_state,
        "anchor_status": (
            "provisional"
            if current["results"]
            .get(current["anchor_decision"], {})
            .get("classification")
            == "provisional_improvement"
            else "confirmed_or_original"
        ),
        "accepted_decisions": sorted(current["accepted"]),
        "provisional_decisions": sorted(
            sid
            for sid, event in current["results"].items()
            if event.get("classification") == "provisional_improvement"
        ),
        "reopened_decisions": sorted(current["retired"]),
        "observations": [
            observation_payload(sid, e, current["decisions"])
            for sid, e in current["results"].items()
        ],
    }


def checked_screening(result, manifest, contract, identity, summary, artifacts):
    """Allow an explicit diagnostic reference without manufacturing confidence evidence."""
    from validate_execution_identity import dependency_paths, validate_document
    import sys

    scripts = Path(__file__).resolve().parents[3] / "ops-profiling-report/scripts"
    sys.path.insert(0, str(scripts))
    from report_contract import validate_screening

    require(
        effect_policy(manifest["configuration"].get("performance_effect_policy"))["id"]
        == "confidence_effect_v1",
        "screening requires the confidence policy",
    )
    require(
        result.get("provisional") is True,
        "screened selection must explicitly be provisional",
    )
    reports = result.get("screening_evidence", {})
    require(
        set(reports) == set(contract["case_ids"]), "screening report coverage differs"
    )
    frequencies, protocols = set(), set()
    for case in summary["cases"]:
        inputs = set()
        for side in ("baseline", "candidate"):
            report_ref = reports[case["case_id"]][side]
            verify_ref(report_ref, artifacts)
            report = load(report_ref["path"])
            require(report.get("case_id") == case["case_id"], "screening case mismatch")
            measurement = validate_screening(report)
            for item in measurement["dependencies"]:
                verify_ref(item, artifacts)
            require(
                measurement["duration_us"] == case[f"{side}_total_us"],
                "screening headline differs from verified measurement",
            )
            frequencies.add(measurement["frequency_mhz"])
            protocols.add(json.dumps(measurement["comparison_key"], sort_keys=True))
            execution_ref = report["identity"]["execution_identity"]
            verify_ref(execution_ref, artifacts)
            execution = load(execution_ref["path"])
            checked_source_identity(
                execution["source"],
                identity[side],
                "screening report belongs to another source",
            )
            validate_document(
                {
                    "inputs": {"code": execution["source"]},
                    "configuration": {"target_socs": contract["target_socs"]},
                },
                execution,
            )
            artifacts.extend(ref(p) for p in dependency_paths(execution))
            frozen = report["identity"]["input_snapshot"]
            verify_ref(frozen, artifacts)
            inputs.add((frozen["path"], frozen["sha256"]))
        require(len(inputs) == 1, "screening inputs differ within case")
    require(
        len(frequencies) == 1 and len(protocols) == 1,
        "screening frequency/protocol differ",
    )


def identity_path(identity):
    """Get a comparable path/key from either identity form; None for git mode."""
    if isinstance(identity, dict) and set(identity) == {"commit", "tree"}:
        return identity.get("commit")
    if isinstance(identity, dict) and "path" in identity:
        return identity["path"]
    return None


def identity_label(identity):
    """Render a search identity for display, handling both git and directory forms."""
    if isinstance(identity, dict) and set(identity) == {"commit", "tree"}:
        return identity["commit"][:12]
    if isinstance(identity, dict) and "path" in identity:
        return identity["path"]
    return str(identity)


def is_git_identity(identity):
    """True if the identity is in git form {commit, tree}."""
    return isinstance(identity, dict) and set(identity) == {"commit", "tree"}


def checked_source_identity(source, expected, message):
    """Match report source receipts to the conformance gate's identity format."""
    if is_git_identity(expected):
        commit = source.get("commit") or (source.get("git") or {}).get("head_commit")
        tree = source.get("tree")
        if source.get("identity_method") == "git-tree-v1":
            tree = source.get("sha256")
        require(commit == expected["commit"] and tree == expected["tree"], message)
    else:
        require(
            Path(source["path"]).resolve() == Path(expected["path"]).resolve(), message
        )


def needs_measurement(result):
    # Ordinary screened attempts retain the baseline without a promotion gate.
    return result["outcome"] == "measured" or (
        result["outcome"] == "screened" and result.get("provisional") is True
    )


def observation_payload(sid, event, decisions):
    """One observation row with both legacy and explicit mechanism keys."""
    result = event["result"]
    mechanism = result["mechanism"]
    contract = decisions[sid][1]["search"] if sid in decisions else {}
    result_bucket = checked_case_bucket(
        result, "result.case_bucket", legacy_null=True
    )
    contract_bucket = checked_case_bucket(contract, "search.case_bucket")
    if "case_bucket" in result:
        require(
            result_bucket == contract_bucket,
            "observation case_bucket differs from the frozen contract",
        )
    return {
        "decision_id": sid,
        "scheme_id": sid,
        "mechanism_id": (
            decisions[sid][1]["search"]["mechanism"] if sid in decisions else None
        ),
        "classification": event["classification"],
        "mechanism": mechanism,
        "mechanism_status": mechanism.get("status"),
        "retry_condition": result["retry_condition"],
        # Consistent declarations are propagated; legacy unbucketed rows keep
        # the whole-tuning-set semantics.
        "case_bucket": (
            result_bucket if result_bucket is not None else contract_bucket
        ),
    }


def needs_observation_gate(result, frontier_present):
    """Only a measured result can extend a frontier observation.

    Screened/provisional results retain the baseline but cannot satisfy
    validate_observation's measured contract.
    """
    return bool(frontier_present and result.get("outcome") == "measured")
