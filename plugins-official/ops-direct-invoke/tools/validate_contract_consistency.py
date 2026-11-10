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
"""Gate: active TDD case inputs must satisfy the Unit's machine-readable domain.

声明域写在 Unit 的 `scope.domain_constraints`，只描述公开输入自身的属性，
不依赖具体算子的语义，只使用 shape、dtype 与标量属性：

    scope:
      domain_constraints:
        - {input: <输入A>, metric: dimension, axis: -1, relation: multiple_of, value: 64}
        - {input: <输入B>, metric: dimension, axis: 1, relation: le, value: 4096}
        - {input: <输入A>, metric: dimension, axis: 0, relation: eq, value: 1}
        - {input: <输入A>, metric: numel, relation: le, value: 1048576}
        - {input: <输入A>, metric: dtype, relation: in, value: [<dtype1>, <dtype2>]}
        - {input: <标量属性>, metric: value, relation: eq, value: <取值>}

    input    : 公开输入名；metric=value 时为标量属性名
    metric   : dimension | numel | dtype | value
    axis     : 仅 metric=dimension 使用，支持负轴
    relation : eq | ne | le | lt | ge | gt | multiple_of | in
    value    : 数值、字符串、布尔或列表
    default  : 可选，仅 metric=value；用例未提供该标量属性时按此值比较

校验对象是 testcase.csv 中 tdd 分组的 active 行，含 execution 的每个 call；
inputs_json 为空、输入不存在或维度越界均按契约错误处理。
expected 以 raises_error 开头的错误路径用例不参与声明域校验。

缺少 `scope.domain_constraints`（或为空）表示声明域无法机器校验，默认判失败；
迁移期可加 `--allow-undeclared` 降级为 UNCHECKED 提示。
"""

import argparse
import csv
import json
import logging
from pathlib import Path

import yaml

METRICS = frozenset({"dimension", "numel", "dtype", "value"})
RELATIONS = frozenset({"eq", "ne", "le", "lt", "ge", "gt", "multiple_of", "in"})
EXAMPLE = (
    "scope.domain_constraints: "
    "[{input: <公开输入名>, metric: dimension, axis: -1, relation: multiple_of, value: 64}]"
)


class ContractError(ValueError):
    """Raised when the Unit contract or a TDD case input cannot be interpreted."""


def load_units(directory):
    units = {}
    for source in sorted(Path(directory).glob("U*.yaml")):
        doc = yaml.safe_load(source.read_text(encoding="utf-8"))
        if not isinstance(doc, dict) or set(doc) != {"unit"}:
            raise ContractError(f"{source}: expected one unit object")
        unit = doc["unit"]
        if not isinstance(unit, dict) or unit.get("unit_id") != source.stem:
            raise ContractError(f"{source}: unit_id must match filename")
        units[source.stem] = unit
    if not units:
        raise ContractError(f"{directory}: no U*.yaml")
    return units


def _require_positive_int(uid, name, value):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ContractError(f"{uid}/{name}: multiple_of needs a positive integer value")


def _require_relation_value(uid, name, relation, value):
    if relation == "multiple_of":
        _require_positive_int(uid, name, value)
    elif relation == "in" and (not isinstance(value, list) or not value):
        raise ContractError(f"{uid}/{name}: in needs a nonempty list value")


def _require_axis(uid, name, metric, axis):
    if metric == "dimension":
        if isinstance(axis, bool) or not isinstance(axis, int):
            raise ContractError(f"{uid}/{name}: dimension requires integer axis")
    elif axis is not None:
        raise ContractError(f"{uid}/{name}: axis is only valid for dimension")


def _parse_rule(uid, item):
    if not isinstance(item, dict):
        raise ContractError(f"{uid}: domain constraint must be a mapping")
    name = item.get("input")
    if not isinstance(name, str) or not name.strip():
        raise ContractError(f"{uid}: domain constraint needs nonempty input")
    metric = item.get("metric")
    if metric not in METRICS:
        raise ContractError(f"{uid}/{name}: unsupported metric {metric!r}")
    relation = item.get("relation")
    if relation not in RELATIONS:
        raise ContractError(f"{uid}/{name}: unsupported relation {relation!r}")
    if "value" not in item:
        raise ContractError(f"{uid}/{name}: domain constraint lacks value")
    axis = item.get("axis")
    _require_relation_value(uid, name, relation, item["value"])
    _require_axis(uid, name, metric, axis)
    if "default" in item and metric != "value":
        raise ContractError(f"{uid}/{name}: default is only valid for metric=value")
    rule = {
        "input": name,
        "metric": metric,
        "axis": axis,
        "relation": relation,
        "value": item["value"],
    }
    if "default" in item:
        rule["default"] = item["default"]
    return rule


def domain_rules(uid, unit):
    scope = unit.get("scope") or {}
    if not isinstance(scope, dict):
        raise ContractError(f"{uid}: scope must be a mapping")
    items = scope.get("domain_constraints")
    if items is None or items == []:
        return None
    if not isinstance(items, list):
        raise ContractError(f"{uid}: scope.domain_constraints must be a list")
    return [_parse_rule(uid, item) for item in items]


def load_cases(test_dir):
    path = Path(test_dir) / "testcase.csv"
    if not path.is_file():
        raise ContractError(f"missing {path}")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [
            row
            for row in csv.DictReader(handle)
            if row.get("sheet") == "tdd" and row.get("status") == "active"
        ]


def input_sets(row):
    """Return (label, inputs) for the base call and every execution call."""
    raw = (row.get("inputs_json") or "").strip()
    if not raw:
        raise ContractError("active TDD 行缺少 inputs_json")
    try:
        base = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ContractError(f"inputs_json 无法解析: {error}") from error
    if not isinstance(base, dict):
        raise ContractError("inputs_json 必须是对象")

    sets = [("inputs", base)]
    raw = (row.get("assertions_json") or "").strip()
    if not raw:
        return sets
    try:
        assertions = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ContractError(f"assertions_json 无法解析: {error}") from error
    if not isinstance(assertions, list):
        return sets
    for entry in assertions:
        if not isinstance(entry, dict) or entry.get("kind") != "execution":
            continue
        for index, call in enumerate(entry.get("calls") or []):
            if isinstance(call, dict) and isinstance(call.get("inputs"), dict):
                # runner 按 call 自身的 inputs 独立执行，不与 baseline 合并。
                sets.append((f"calls[{index}]", call["inputs"]))
    return sets


def actual_value(inputs, rule):
    name = rule["input"]
    value = inputs.get(name)
    if value is None:
        if "default" in rule:
            return rule["default"]
        raise ContractError(f"输入 {name} 缺失")
    if rule["metric"] == "value":
        return value
    tensor = value
    if not isinstance(tensor, dict) or not isinstance(tensor.get("shape"), list):
        raise ContractError(f"输入 {name} 不是带 shape 的张量")
    shape = tensor["shape"]
    if any(isinstance(dim, bool) or not isinstance(dim, int) for dim in shape):
        raise ContractError(f"输入 {name} 的 shape 非整数列表: {shape}")
    if rule["metric"] == "numel":
        total = 1
        for dim in shape:
            total *= dim
        return total
    if rule["metric"] == "dtype":
        return tensor.get("dtype")
    axis = rule["axis"]
    if not -len(shape) <= axis < len(shape):
        raise ContractError(f"输入 {name} 的 axis={axis} 越界，shape={shape}")
    return shape[axis]


def label(rule):
    if rule["metric"] == "dimension":
        return f"{rule['input']}.shape[{rule['axis']}]"
    if rule["metric"] == "value":
        return rule["input"]
    return f"{rule['input']}.{rule['metric']}"


def satisfied(actual, rule):
    relation, expected = rule["relation"], rule["value"]
    if relation == "multiple_of":
        if isinstance(expected, bool) or not isinstance(expected, int) or expected <= 0:
            raise ContractError(f"{label(rule)}: multiple_of 需要正整数")
        return (
            isinstance(actual, int)
            and not isinstance(actual, bool)
            and actual % expected == 0
        )
    if relation == "in":
        if not isinstance(expected, list) or not expected:
            raise ContractError(f"{label(rule)}: in 需要非空列表")
        return actual in expected
    if relation == "eq":
        return actual == expected
    if relation == "ne":
        return actual != expected
    if actual is None or isinstance(actual, bool):
        return False
    try:
        left, right = float(actual), float(expected)
    except (TypeError, ValueError):
        return False
    return {
        "le": left <= right,
        "lt": left < right,
        "ge": left >= right,
        "gt": left > right,
    }[relation]


def _check_rules(uid, rules, case_id, set_label, inputs, violations):
    for rule in rules:
        try:
            actual = actual_value(inputs, rule)
            ok = satisfied(actual, rule)
        except ContractError as error:
            violations.append(f"{uid} {case_id} {set_label}: {error}")
            continue
        if not ok:
            violations.append(
                f"{uid} {case_id} {set_label}: {label(rule)}={actual!r} "
                f"不满足 {rule['relation']} {rule['value']!r}"
            )


def _check_case(uid, rules, row, violations):
    case_id = (row.get("case_id") or "").strip()
    # 错误路径用例本就位于支持域之外，不参与声明域校验。
    if (row.get("expected") or "").strip().startswith("raises_error"):
        return 0
    try:
        sets = input_sets(row)
    except ContractError as error:
        violations.append(f"{uid} {case_id}: {error}")
        return 0
    for set_label, inputs in sets:
        _check_rules(uid, rules, case_id, set_label, inputs, violations)
    return len(sets)


def check_unit(uid, rules, rows, violations):
    return sum(_check_case(uid, rules, row, violations) for row in rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--units-dir", required=True, type=Path)
    parser.add_argument("--test-dir", required=True, type=Path)
    parser.add_argument(
        "--allow-undeclared",
        action="store_true",
        help="把缺少 scope.domain_constraints 的 Unit 记为 UNCHECKED 而不判失败",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        units = load_units(args.units_dir)
        cases = load_cases(args.test_dir)
        by_unit = {}
        for row in cases:
            uid = (row.get("unit_id") or "").strip().upper()
            if not uid:
                raise ContractError(f"{row.get('case_id')}: active TDD 行缺少 unit_id")
            by_unit.setdefault(uid, []).append(row)
        unknown = sorted(set(by_unit) - set(units))
        if unknown:
            raise ContractError(f"TDD 用例引用了不存在的 Unit: {', '.join(unknown)}")
        declared = {uid: domain_rules(uid, units[uid]) for uid in by_unit}
    except (ContractError, OSError, yaml.YAMLError) as error:
        parser.exit(1, f"{error}\n")

    undeclared = sorted(uid for uid, rules in declared.items() if not rules)
    if undeclared and not args.allow_undeclared:
        parser.exit(
            1,
            "以下 Unit 有 active TDD 用例但缺少可机器校验的声明域: "
            f"{', '.join(undeclared)}\n请补充 {EXAMPLE}\n"
            "（确需迁移期跳过时使用 --allow-undeclared）\n",
        )
    for uid in undeclared:
        logging.info("UNCHECKED %s: 未声明 scope.domain_constraints", uid)

    violations = []
    checked = 0
    for uid in sorted(uid for uid, rules in declared.items() if rules):
        checked += check_unit(uid, declared[uid], by_unit[uid], violations)

    for violation in violations:
        logging.info("VIOLATION %s", violation)
    logging.info(
        "checked %d input set(s) from %d active TDD case(s) across %d Unit(s); %d violation(s)",
        checked,
        len(cases),
        len(set(by_unit) - set(undeclared)),
        len(violations),
    )
    if violations:
        parser.exit(1, "contract consistency check failed\n")


if __name__ == "__main__":
    main()
