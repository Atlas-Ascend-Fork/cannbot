#!/usr/bin/env python3
# ----------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------
"""Validate implementation Unit contracts before test generation or scheduling."""

import argparse
import logging
from pathlib import Path

import yaml


def names(value, label):
    if (
        not isinstance(value, list)
        or any(not isinstance(item, str) or not item.strip() for item in value)
        or len(value) != len(set(value))
    ):
        raise ValueError(f"{label} must contain unique nonempty names")
    return value


def reject_duplicate_keys(node, visited=None):
    visited = visited if visited is not None else set()
    if node is None or id(node) in visited:
        return
    visited.add(id(node))
    if isinstance(node, yaml.MappingNode):
        seen = set()
        for key, value in node.value:
            if (
                not isinstance(key, yaml.ScalarNode)
                or key.tag != "tag:yaml.org,2002:str"
            ):
                raise ValueError("non-string YAML key")
            if key.value in seen:
                raise ValueError(f"duplicate YAML key: {key.value!r}")
            seen.add(key.value)
            reject_duplicate_keys(value, visited)
    elif isinstance(node, yaml.SequenceNode):
        for item in node.value:
            reject_duplicate_keys(item, visited)


def load_units(directory):
    native = {}
    for source in sorted(Path(directory).glob("U*.yaml")):
        text = source.read_text(encoding="utf-8")
        reject_duplicate_keys(yaml.compose(text, Loader=yaml.SafeLoader))
        doc = yaml.safe_load(text)
        if not isinstance(doc, dict) or set(doc) != {"unit"}:
            raise ValueError(f"{source}: expected one unit object")
        unit = doc["unit"]
        if not isinstance(unit, dict) or unit.get("unit_id") != source.stem:
            raise ValueError(f"{source}: unit_id must match filename")
        native[source.stem] = unit
    if not native:
        raise ValueError(f"{directory}: no U*.yaml")
    return native


def validate_units(native):
    """Return a deterministic dependency order; planning metadata is never proof of success."""
    graph, obligations = {}, {}
    all_ids = set()
    for uid, unit in native.items():
        if not isinstance(unit, dict) or unit.get("unit_id") != uid:
            raise ValueError(f"{uid}: invalid unit object")
        graph[uid] = names(unit.get("depends_on", []), f"{uid}: depends_on")
        for field in ("requires", "provides"):
            names(unit.get(field, []), f"{uid}: {field}")
        obligations[uid] = validate_obligations(uid, unit, all_ids)

    order, ancestors = dependency_order(graph)
    for uid in order:
        validate_evidence(
            uid, native[uid], graph[uid], ancestors[uid], native, obligations
        )
    return order


def validate_obligations(uid, unit, all_ids):
    scope = unit.get("scope", {})
    if not isinstance(scope, dict):
        raise ValueError(f"{uid}: scope must be a mapping")
    names(scope.get("source_files", []), f"{uid}: source_files")
    items = unit.get("verification_obligations")
    if not isinstance(items, list) or not items:
        raise ValueError(f"{uid}: verification_obligations must be a nonempty list")
    ids, kinds = set(), set()
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"{uid}: obligation must be a mapping")
        ref = item.get("id")
        if not isinstance(ref, str) or not ref.strip() or ref in all_ids:
            raise ValueError(
                f"{uid}: obligation IDs must be nonempty and globally unique"
            )
        kind = item.get("kind")
        if kind == "structural":
            raise ValueError(
                f"{uid}/{ref}: structural obligations are removed; migrate to "
                "design_constraints.review_evidence or feasibility_checks.review_evidence, "
                "retaining design references"
            )
        if not isinstance(kind, str) or kind not in {
            "numerical",
            "semantic",
            "device",
        }:
            raise ValueError(f"{uid}: unsupported obligation kind: {kind}")
        ids.add(ref)
        all_ids.add(ref)
        kinds.add(kind)
    if unit.get("kind") == "minimal_operator" and "numerical" not in kinds:
        raise ValueError(f"{uid}: minimal operator lacks numerical obligation")
    return ids


def dependency_order(graph):
    ancestors, order, visiting = {}, [], set()

    def visit(uid):
        if uid in visiting:
            raise ValueError(f"unit dependency cycle includes {uid}")
        if uid in ancestors:
            return
        visiting.add(uid)
        inherited = set()
        for dep in sorted(graph[uid]):
            if dep not in graph:
                raise ValueError(f"{uid}: unknown unit dependency: {dep}")
            visit(dep)
            inherited.add(dep)
            inherited.update(ancestors[dep])
        visiting.remove(uid)
        ancestors[uid] = inherited
        order.append(uid)

    for uid in sorted(graph):
        visit(uid)

    return order, ancestors


def validate_evidence(uid, unit, dependencies, ancestors, native, obligations):
    available = {cap for dep in ancestors for cap in native[dep].get("provides", [])}
    if not set(unit.get("requires", [])) <= available:
        raise ValueError(f"{uid}: requires capability without dependency provider")
    if "dependency_reasons" in unit:
        reasons = unit["dependency_reasons"]
        if (
            not isinstance(reasons, dict)
            or set(reasons) != set(dependencies)
            or any(
                not isinstance(reason, str) or not reason.strip()
                for reason in reasons.values()
            )
        ):
            raise ValueError(f"{uid}: dependency_reasons must explain each dependency")
    refs = obligations[uid] | {ref for dep in ancestors for ref in obligations[dep]}
    implementation = unit.get("implementation", {})
    if not isinstance(implementation, dict):
        raise ValueError(f"{uid}: implementation must be a mapping")
    checks = (
        (
            "design_constraints",
            unit.get("design_constraints", []),
            ("source", "commitment"),
        ),
        (
            "feasibility_checks",
            implementation.get("feasibility_checks", []),
            ("design_source", "question", "before_step", "on_failure"),
        ),
    )
    for label, items, fields in checks:
        validate_check_items(uid, label, items, fields, refs)
    if unit.get("kind") == "pipeline_framework" and not any(
        item.get("review_evidence") for _, items, _ in checks for item in items
    ):
        raise ValueError(
            f"{uid}: pipeline framework requires structural review_evidence in design_constraints or feasibility_checks"
        )


def validate_check_items(uid, label, items, fields, refs):
    if not isinstance(items, list):
        raise ValueError(f"{uid}: {label} must be a list")
    for item in items:
        if not isinstance(item, dict) or any(
            not isinstance(item.get(key), str) or not item[key].strip()
            for key in fields
        ):
            raise ValueError(f"{uid}: {label} requires actionable contract fields")
        bound = names(item.get("obligation_ids", []), f"{uid}: {label} obligation_ids")
        if not set(bound) <= refs:
            raise ValueError(f"{uid}: invalid {label} obligation references")
        review = item.get("review_evidence", [])
        if not isinstance(review, list) or any(
            not isinstance(entry, dict)
            or any(
                not isinstance(entry.get(key), str) or not entry[key].strip()
                for key in ("artifact", "check", "pass_criteria")
            )
            for entry in review
        ):
            raise ValueError(
                f"{uid}: {label} review evidence needs artifact/check/pass_criteria"
            )
        if not bound and not review:
            raise ValueError(
                f"{uid}: {label} requires executable obligations or review evidence"
            )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--units-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        order = validate_units(load_units(args.units_dir))
    except (ValueError, OSError, yaml.YAMLError) as error:
        parser.exit(1, f"{error}\n")
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.info("validated %d Unit contracts: %s", len(order), ", ".join(order))


if __name__ == "__main__":
    main()
