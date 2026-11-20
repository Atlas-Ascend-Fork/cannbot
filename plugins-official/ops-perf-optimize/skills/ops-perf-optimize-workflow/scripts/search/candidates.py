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

"""Expand a declarative candidate space into a validated frontier.

This is deliberately operator-agnostic: the operator-specific part is a JSON
space (axes, values, prior, trigger), not code. The script does not edit source,
run devices, or claim model ranking; it only produces a frontier that the
existing search policy can validate, select, and record.
"""

from __future__ import annotations

import argparse
import itertools
import math
import json
import re
import statistics
from pathlib import Path

from . import policy as search


def _identifier(value):
    return re.sub(r"[^A-Za-z0-9_-]+", "-", str(value)).strip("-")


BINDING_KINDS = ("tiling_field", "source_constant", "contract_feature")
CONSTRAINT_KINDS = ("divide_by", "min", "max", "product_max")


def _validate_binding(axis):
    binding = axis.get("binding")
    if binding is None:
        return None
    search.require(
        isinstance(binding, dict), f"{axis['name']}: binding must be an object"
    )
    kind = binding.get("kind")
    search.require(
        kind in BINDING_KINDS, f"{axis['name']}: unsupported binding kind: {kind}"
    )
    if kind in ("tiling_field", "contract_feature"):
        search.require(
            isinstance(binding.get("field"), str) and binding["field"].strip(),
            f"{axis['name']}: binding needs field",
        )
    else:
        search.require(
            isinstance(binding.get("file"), str) and binding["file"].strip(),
            f"{axis['name']}: source_constant binding needs file",
        )
        search.require(
            isinstance(binding.get("symbol"), str) and binding["symbol"].strip(),
            f"{axis['name']}: source_constant binding needs symbol",
        )
    return dict(binding)


def _validate_constraints(constraints):
    search.require(isinstance(constraints, list), "constraints must be a list")
    for constraint in constraints:
        search.require(isinstance(constraint, dict), "constraint must be an object")
        kind = constraint.get("kind")
        search.require(kind in CONSTRAINT_KINDS, f"unsupported constraint kind: {kind}")
        if kind == "product_max":
            fields = constraint.get("fields")
            search.require(
                isinstance(fields, list)
                and len(fields) >= 2
                and all(isinstance(field, str) and field for field in fields),
                "product_max needs at least two field names",
            )
            search.require(
                isinstance(constraint.get("value"), (int, float))
                and not isinstance(constraint.get("value"), bool),
                "product_max needs a numeric value",
            )
        else:
            search.require(
                isinstance(constraint.get("field"), str) and constraint["field"],
                f"{kind} needs field",
            )
            search.require(
                isinstance(constraint.get("value"), (int, float))
                and not isinstance(constraint.get("value"), bool),
                f"{kind} needs a numeric value",
            )


def _constraint_ok(values, constraints):
    for constraint in constraints:
        kind = constraint["kind"]
        if kind == "product_max":
            product = 1
            for field in constraint["fields"]:
                search.require(
                    field in values, f"constraint references unknown axis: {field}"
                )
                product *= values[field]
            if product > constraint["value"]:
                return False
        elif kind == "divide_by":
            field = constraint["field"]
            search.require(
                field in values, f"constraint references unknown axis: {field}"
            )
            divisor = constraint["value"]
            if divisor <= 0 or values[field] % divisor != 0:
                return False
        elif kind == "min":
            field = constraint["field"]
            search.require(
                field in values, f"constraint references unknown axis: {field}"
            )
            if values[field] < constraint["value"]:
                return False
        elif kind == "max":
            field = constraint["field"]
            search.require(
                field in values, f"constraint references unknown axis: {field}"
            )
            if values[field] > constraint["value"]:
                return False
    return True


def _axis_prior(axis, value, fallback):
    prior = axis.get("prior")
    if prior is None:
        return fallback
    search.require(isinstance(prior, dict), f"{axis['name']}: prior must be an object")
    key = str(value)
    search.require(key in prior, f"{axis['name']}: prior missing value {key}")
    return search.gain_range(prior[key], f"{axis['name']}.prior[{key}]")


def _combine_priors(axes, combination, fallback):
    lows, highs = [], []
    for axis, value in zip(axes, combination):
        low, high = _axis_prior(axis, value, fallback)
        lows.append(low)
        highs.append(high)
    return [statistics.fmean(lows), statistics.fmean(highs)]


def _pairwise_select(combinations, axes):
    if len(axes) < 2:
        return list(combinations)
    target = set()
    for combination in combinations:
        for i in range(len(axes)):
            for j in range(i + 1, len(axes)):
                target.add((i, str(combination[i]), j, str(combination[j])))
    uncovered = set(target)
    selected = []
    remaining = list(combinations)
    while uncovered:
        best = None
        best_cover = set()
        for combination in remaining:
            cover = set()
            for i in range(len(axes)):
                for j in range(i + 1, len(axes)):
                    key = (i, str(combination[i]), j, str(combination[j]))
                    if key in uncovered:
                        cover.add(key)
            if len(cover) > len(best_cover):
                best, best_cover = combination, cover
        search.require(
            best is not None, "pairwise generation could not cover the space"
        )
        selected.append(best)
        uncovered -= best_cover
        remaining.remove(best)
    return selected


def load_space(path, dependencies=None):
    dependencies = [] if dependencies is None else dependencies
    space = search.load(path)
    search.require(
        space.get("schema_version") == 1, "candidate space schema_version must be 1"
    )
    axes = space.get("axes")
    search.require(isinstance(axes, list) and axes, "candidate space needs axes")
    names = []
    for axis in axes:
        search.require(isinstance(axis, dict), "each axis must be an object")
        name = axis.get("name")
        search.require(isinstance(name, str) and name, "axis needs name")
        search.require(name not in names, f"duplicate axis: {name}")
        names.append(name)
        values = axis.get("values")
        search.require(
            isinstance(values, list) and values, f"{name}: values are required"
        )
        search.require(
            len({str(v) for v in values}) == len(values), f"{name}: duplicate values"
        )
        _validate_binding(axis)
        triggers = axis.get("trigger", {})
        search.require(isinstance(triggers, dict), f"{name}: trigger must be an object")
        search.require(
            set(triggers) <= {str(v) for v in values},
            f"{name}: trigger keys must match axis values",
        )
        for value, references in triggers.items():
            search.require(
                isinstance(references, list) and references,
                f"{name}={value}: trigger needs evidence references",
            )
            for reference in references:
                search.verify_ref(reference, dependencies)
    _validate_constraints(space.get("constraints", []))
    prior = space.get("prior", {})
    search.require(isinstance(prior, dict), "prior must be an object")
    gain = prior.get("gain", [0.02, 0.15])
    low, high = search.gain_range(gain, "prior.gain")
    cost = float(prior.get("cost", 1.0))
    risk = float(prior.get("risk", 0.15))
    search.require(cost >= 0 and 0 <= risk <= 1, "invalid prior cost/risk")
    return space, axes, (low, high), cost, risk


def expand(space, axes, gain, cost, risk, max_candidates, method=None):
    axis_values = [axis["values"] for axis in axes]
    search.require(
        math.prod(len(values) for values in axis_values) <= 100000,
        "candidate space has too many raw combinations; reduce axes or values",
    )
    names = [axis["name"] for axis in axes]
    constraints = space.get("constraints", [])
    combinations = [
        values for values in itertools.product(*axis_values) if _constraint_ok(dict(zip(names, values)), constraints)
    ]
    method = method or space.get("generation", {}).get("method", "cartesian")
    if method == "cartesian":
        selected = combinations
    elif method == "pairwise":
        selected = _pairwise_select(combinations, axes)
    else:
        raise ValueError(f"search: unsupported generation method: {method}")
    search.require(
        len(selected) <= max_candidates,
        f"candidate space expands to {len(selected)} nodes; raise --max-candidates or reduce axes",
    )
    trigger = space.get("trigger")
    search.require(
        isinstance(trigger, list) and trigger, "candidate space needs trigger evidence"
    )
    bindings = {
        axis["name"]: axis["binding"]
        for axis in axes
        if axis.get("binding") is not None
    }
    nodes = []
    seen = set()
    for combination in selected:
        label = "-".join(
            f"{axis['name']}={value}" for axis, value in zip(axes, combination)
        )
        scheme = f"t-{_identifier(label)}"
        search.require(scheme not in seen, f"duplicate scheme id: {scheme}")
        seen.add(scheme)
        node_trigger = list(trigger)
        for axis, value in zip(axes, combination):
            for reference in axis.get("trigger", {}).get(str(value), []):
                if reference not in node_trigger:
                    node_trigger.append(reference)
        nodes.append(
            {
                "scheme_id": scheme,
                "kind": space.get("kind", "local"),
                "level": space.get("level", "M1"),
                "mechanism": space.get("mechanism", "tiling-parameter"),
                "optimization_type": space.get("optimization_type", "tiling"),
                "trigger": node_trigger,
                "expected_gain_range": _combine_priors(axes, combination, gain),
                "cost": cost,
                "risk": risk,
                "fidelity": space.get("fidelity", "L1"),
                "status": "candidate",
                "explore_tag": "exploit",
                "depends_on": space.get("depends_on", []),
                "factors": {
                    axis["name"]: value for axis, value in zip(axes, combination)
                },
                "bindings": bindings,
            }
        )
    if space.get("open_exploration", True):
        nodes.append(
            {
                "scheme_id": "open-exploration",
                "kind": "architecture",
                "level": "open",
                "mechanism": "open_exploration",
                "optimization_type": "algorithm",
                "trigger": trigger,
                "expected_gain_range": [0.0, gain[1]],
                "cost": cost,
                "risk": min(1.0, risk + 0.15),
                "fidelity": space.get("fidelity", "L1"),
                "status": "candidate",
                "explore_tag": "open",
                "depends_on": [],
                "factors": {},
            }
        )
    return nodes


def build(
    space_path,
    parent,
    trigger_path,
    round_name,
    best_us,
    n,
    p_pass,
    max_candidates,
    method=None,
    *,
    accepted=(),
):
    space, axes, gain, cost, risk = load_space(space_path)
    if isinstance(parent, dict):
        parent_identity = parent
    else:
        parent_path = Path(parent)
        value = search.load(parent_path) if parent_path.suffix == ".json" else None
        parent_identity = (
            value
            if search.is_git_identity(value)
            else search.source_identity(parent_path)
        )
    search.validate_parent({"parent": parent_identity}, None)
    trigger = search.ref(trigger_path)
    space = dict(space)
    triggers = list(space.get("trigger", []))
    if triggers:
        search.checked_refs(triggers, "candidate knowledge")
    if trigger not in triggers:
        triggers.append(trigger)
    space["trigger"] = triggers
    expanded = expand(space, axes, gain, cost, risk, max_candidates, method)
    # A decision ID belongs to one round, even when another round evaluates
    # the same factors against a new parent or with new diagnostic evidence.
    for node in expanded:
        node["scheme_id"] = f"{_identifier(round_name)}-{node['scheme_id']}"
    frontier = {
        "schema_version": 1,
        "candidate_space": search.ref(space_path),
        "round": round_name,
        "parent": parent_identity,
        "best_total_us": best_us,
        "n": n,
        "p_pass": p_pass,
        "epsilon": space.get("epsilon", search.DEFAULT_EPSILON),
        "explore_every": space.get("explore_every", search.DEFAULT_EXPLORE_EVERY),
        "strategy": space.get("strategy", search.DEFAULT_STRATEGY),
        "strategy_options": space.get("strategy_options", {}),
        "weights": space.get("weights", search.DEFAULT_WEIGHTS),
        "prefilter": {
            "l0": {"method": "declarative candidate space", "best_total_us": best_us},
            "l1": {
                "status": "unsupported",
                "reason": "candidate expansion only; run search_prefilter.py for model coverage",
            },
        },
        "nodes": expanded,
    }
    search.validate_frontier(frontier, accepted=accepted)
    return frontier


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--space", type=Path, required=True)
    parser.add_argument("--state", type=Path, help="workflow state for accepted dependencies")
    parser.add_argument("--parent", type=Path, required=True)
    parser.add_argument("--trigger", type=Path, required=True)
    parser.add_argument("--round", default="round1")
    parser.add_argument("--best-us", type=float, required=True)
    parser.add_argument("--n", type=int, default=search.DEFAULT_N)
    parser.add_argument("--p-pass", type=float, default=search.DEFAULT_P_PASS)
    parser.add_argument("--max-candidates", type=int, default=64)
    parser.add_argument("--method", choices=("cartesian", "pairwise"))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        frontier = build(
            args.space.resolve(),
            args.parent,
            args.trigger,
            args.round,
            args.best_us,
            args.n,
            args.p_pass,
            args.max_candidates,
            args.method,
            accepted=search.accepted_from_state(args.state),
        )
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(
            json.dumps({"status": "invalid", "reason": str(error)}, ensure_ascii=False)
        )
        return 2
    args.out.write_text(
        json.dumps(frontier, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": "expanded",
                "out": str(args.out.resolve()),
                "nodes": len(frontier["nodes"]),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
