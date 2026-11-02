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
"""Build and validate the real Unit implementation loop subgraph."""

import argparse
import csv
import importlib.util
import logging
import re
import shlex
import sys
from dataclasses import dataclass, field as dataclass_field
from pathlib import Path

import yaml
from validate_unit_contracts import load_units, validate_units

REQUIRED_FIELDS = ("title", "goal", "approach", "acceptance", "out_of_scope")
CONTENT_FIELDS = (
    "title",
    "goal",
    "approach",
    "procedure",
    "acceptance",
    "out_of_scope",
)
ARCHITECT = "ops-direct-invoke-architect"
DEVELOPER = "ops-direct-invoke-developer"
VERIFIER = "ops-direct-invoke-verifier"
DSL_ROLES = frozenset((ARCHITECT, DEVELOPER, VERIFIER))


def fail(message):
    raise ValueError(message)


def read(path):
    if not path.is_file():
        fail(f"missing {path}")
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        fail(f"{path} must be mapping")
    return value


def validate_role_names(nodes):
    for node in nodes:
        for field in ("executor", "verifier"):
            if node.get(field) not in DSL_ROLES:
                fail(f"node {node.get('id')}: unknown {field} role {node.get(field)!r}")


def load_inputs(work, code=None):
    spec_doc = read(work / "design" / "doc" / "spec.yaml")
    op = (spec_doc.get("op") or {}).get("name")
    if not isinstance(op, str) or not op:
        fail("spec.op.name is required")
    test = (code or work) / "operators" / op / "test"
    design = work / "design" / "doc" / "DESIGN.md"
    if not design.is_file():
        fail("missing DESIGN.md")
    unit_dir = work / "design" / "units"
    try:
        native = load_units(unit_dir)
        unit_order = validate_units(native)
    except (ValueError, OSError, yaml.YAMLError) as error:
        fail(str(error))
    csv_path = test / "testcase.csv"
    if not csv_path.is_file():
        fail(f"missing {csv_path}")
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        cases = [row for row in csv.DictReader(handle) if row["sheet"] == "tdd"]
    case_ids = [row["case_id"] for row in cases]
    if not cases or len(case_ids) != len(set(case_ids)):
        fail("TDD case IDs missing or duplicated")
    return op, unit_dir, native, unit_order, cases


def verified_case_ids(native_id, original, cases):
    uid = native_id.lower()
    rows = [
        row for row in cases if row["unit_id"] == uid and row.get("status") == "active"
    ]
    obligations = {
        item["id"] for item in original.get("verification_obligations") or []
    }
    if not rows or not obligations:
        fail(f"{native_id}: missing TDD cases or obligations")
    covered, expected_ids = set(), []
    for row in rows:
        if not row["case_id"].startswith(f"TD-{uid}-"):
            fail(f"{native_id}: invalid TDD case ID")
        ref_list = [
            ref.strip() for ref in row["obligation_ids"].split(",") if ref.strip()
        ]
        refs = set(ref_list)
        if not refs or len(ref_list) != len(refs) or not refs <= obligations:
            fail(f"{native_id}: invalid obligation reference")
        covered.update(refs)
        expected_ids.append(row["case_id"])
    if covered != obligations:
        fail(f"{native_id}: uncovered verification obligation")
    return expected_ids


def bind_unit_cases(work, unit_dir, native, unit_order, cases):
    units, native_by_id, case_map = [], {}, {}
    for native_id in unit_order:
        original = native[native_id]
        source = unit_dir / f"{native_id}.yaml"
        uid = native_id.lower()
        expected_ids = verified_case_ids(native_id, original, cases)
        units.append(
            {
                "id": uid,
                "depends_on": [dep.lower() for dep in original.get("depends_on") or []],
            }
        )
        native_by_id[uid] = {
            "native_id": native_id,
            "path": source.relative_to(work).as_posix(),
            "source_files": [
                (work / path).resolve().relative_to(work.resolve()).as_posix()
                for path in original.get("scope", {}).get("source_files") or []
            ],
        }
        case_map[uid] = expected_ids
    active_case_ids = {row["case_id"] for row in cases if row.get("status") == "active"}
    if active_case_ids != {case for group in case_map.values() for case in group}:
        fail("TDD CSV contains cases outside native Units")
    return units, native_by_id, case_map


@dataclass
class NodeOptions:
    extra: dict = dataclass_field(default_factory=dict)
    notes: tuple | list = ()
    acceptance: tuple | list = ()


def make_node(task_path, op, node_id, deps, options: NodeOptions):
    task = read(task_path)
    task = {
        field: [
            item.replace("<op>", op) if isinstance(item, str) else item
            for item in value
        ]
        if isinstance(value, list)
        else value.replace("<op>", op)
        if isinstance(value, str)
        else value
        for field, value in task.items()
    }
    missing = [field for field in REQUIRED_FIELDS if field not in task]
    if missing:
        fail(f"task {task_path.name} missing fields: {', '.join(missing)}")
    node = {
        "id": node_id,
        "task_type": "normal",
        **{field: task[field] for field in CONTENT_FIELDS if field in task},
        "depends_on": deps,
        "executor": options.extra.get("executor", DEVELOPER),
        "verifier": VERIFIER,
        "max_retries": options.extra.get("max_retries", 1),
        "on_exhaust": options.extra.get("on_exhaust", "exit"),
    }
    node["approach"] = list(node["approach"]) + list(options.notes)
    node["acceptance"] = list(node["acceptance"]) + list(options.acceptance)
    if options.extra.get("rollback_to"):
        node["rollback_to"] = options.extra["rollback_to"]
    return node


def unit_dependencies(work, units, index, native_by_id):
    unit = units[index]
    uid = unit["id"]
    entry = native_by_id[uid]
    source_files = {
        str((work / path).resolve()) for path in entry.get("source_files") or []
    }
    deps = {f"implement-{dep}" for dep in unit.get("depends_on") or []}
    for earlier in units[:index]:
        other_files = {
            str((work / path).resolve())
            for path in native_by_id[earlier["id"]].get("source_files") or []
        }
        if not source_files or not other_files or source_files & other_files:
            deps.add(f"implement-{earlier['id']}")
    order = {f"implement-{item['id']}": i for i, item in enumerate(units)}
    return sorted(deps, key=order.__getitem__)


def implementation_fix_node(skill, op, leaves):
    return make_node(
        skill / "tasks/cannbot-dsl/实现修复.yaml",
        op,
        "implementation-fix",
        leaves,
        NodeOptions(
            extra={"max_retries": 2},
            notes=[
                "首次进入实现修复前，按此顺序 integrate 已验收 Unit 的完整 SHA："
                + ", ".join(leaves)
                + "。等待全部 Unit；使用 references/code-versions.md 的汇合协议。"
                "重试先读取版本记录，已汇合的祖先不重复应用，不丢弃已有修复。"
            ],
        ),
    )


def final_stage_nodes(skill, op, units):
    nodes = []
    leaves = [f"implement-{unit['id']}" for unit in units]
    nodes.append(implementation_fix_node(skill, op, leaves))
    nodes.append(
        make_node(
            skill / "tasks/cannbot-dsl/单元集成复验.yaml",
            op,
            "unit-integration",
            ["implementation-fix"],
            NodeOptions(
                extra={
                    "max_retries": 0,
                    "on_exhaust": "rollback",
                    "rollback_to": "implementation-fix",
                }
            ),
        )
    )
    nodes.append(
        make_node(
            skill / "tasks/cannbot-dsl/实现检视.yaml",
            op,
            "implementation-review",
            ["unit-integration"],
            NodeOptions(
                extra={
                    "executor": VERIFIER,
                    "max_retries": 0,
                    "on_exhaust": "rollback",
                    "rollback_to": "implementation-fix",
                }
            ),
        )
    )
    return nodes


def unit_tdd_grep(uid, case_map):
    expression = f"^TD-{re.escape(uid)}-"
    selected = set()
    for cases in case_map.values():
        for case in cases:
            if re.search(expression, case):
                selected.add(case)
    if selected != set(case_map[uid]):
        fail(f"{uid}: TDD batch selection differs from bound cases")
    return expression


def build_nodes(work, skill, op, units, native_by_id, case_map):
    nodes = []

    # Unknown write sets are conservatively serialized; known disjoint sets can run in parallel.
    for index, unit in enumerate(units):
        uid = unit["id"]
        entry = native_by_id[uid]
        grep = shlex.quote(unit_tdd_grep(uid, case_map))
        deps = unit_dependencies(work, units, index, native_by_id)
        nodes.append(
            make_node(
                skill / "tasks/cannbot-dsl/单元实现.yaml",
                op,
                f"implement-{uid}",
                deps,
                NodeOptions(
                    notes=[
                        f"Git 节点 ID 固定为 implement-{uid}。按 references/code-versions.md 的 Unit 协议，"
                        "从 test-generator 已验收 SHA 创建独立 worktree；CODE_DIR 取脚本返回值，"
                        "WORK_DIR 保持不变。执行与验收均使用同一 worktree。",
                        "按顺序汇合并绑定依赖节点的已验收 SHA："
                        + (", ".join(deps) or "无")
                        + "；begin 的 --dependency 复用相同版本。",
                        "本 Unit 的 --allow 精确使用 source_files："
                        + ", ".join(entry["source_files"])
                        + "；为空时停止并补齐授权路径，不以未知写集扩大权限。",
                        f"原生 Unit: {entry['path']}；TDD cases: {', '.join(case_map[uid])}；{op}_golden.py 与 design/doc/DESIGN.md 均为冻结输入。",
                        (
                            '当前 Unit TDD 批跑命令：PYTHONPATH="$CODE_DIR" '
                            f"CANNBOTDSL_OP_MODULE={shlex.quote(f'operators.{op}.{op}')} "
                            f'python "$CODE_DIR"/{shlex.quote(f"operators/{op}/test/test_{op}.py")} '
                            f"--sheet tdd --grep {grep} --device npu --require-accelerator；"
                            "公开入口不是 run 时沿用 CANNBOTDSL_OP_ENTRY。"
                        ),
                        f"将 Red→Green 证据、实现版本、执行命令、退出码与逐例结果写入 $WORK_DIR/implementation/{op}/implement-{uid}-执行记录.md。",
                    ],
                    acceptance=[
                        f'test -s "$WORK_DIR/implementation/{op}/implement-{uid}-执行记录.md"'
                    ],
                ),
            )
        )
        nodes[-1]["procedure"] = list(nodes[-1].get("procedure", [])) + [
            f"Git 节点 ID 为 implement-{uid}；通过 code_versions.py status --node implement-{uid} "
            "取得该 Unit 的 CODE_DIR，审查同一 worktree 的 SHA 与依赖版本，按版本协议登记验收。"
        ]
    nodes.extend(final_stage_nodes(skill, op, units))
    validate_role_names(nodes)
    return nodes


def validate_and_write(work, script, nodes):
    sys.path.insert(0, str(script.parent))
    spec = importlib.util.spec_from_file_location("workflow_get_task", script)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    error = module.validate_node_set(nodes, allow_subgraph=False)
    if error:
        fail(f"generated subgraph invalid: {error}")
    flow_dir = work / ".workflow"
    flow_dir.mkdir(parents=True, exist_ok=True)
    graph_path = flow_dir / "implementation-tasks.yaml"
    graph_path.write_text(
        yaml.safe_dump({"nodes": nodes}, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    _, error = module.load_subgraph(str(graph_path))
    if error:
        fail(f"written subgraph invalid: {error}")
    logging.info("validated %d nodes in %s", len(nodes), graph_path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--code-dir",
        help="code checkout containing operators/; omitted only for legacy callers",
    )
    parser.add_argument(
        "--harness-script",
        required=True,
        help="path to workflow-orchestrator/scripts/get_task.py",
    )
    args = parser.parse_args()
    work = Path(args.output_dir).resolve()
    skill = Path(__file__).resolve().parents[1]
    try:
        op, unit_dir, native, unit_order, cases = load_inputs(
            work, Path(args.code_dir).resolve() if args.code_dir else None
        )
        units, native_by_id, case_map = bind_unit_cases(
            work, unit_dir, native, unit_order, cases
        )
        nodes = build_nodes(work, skill, op, units, native_by_id, case_map)
        validate_and_write(work, Path(args.harness_script).resolve(), nodes)
    except (ValueError, OSError, yaml.YAMLError) as error:
        parser.exit(1, f"{error}\n")


logging.basicConfig(level=logging.INFO, format="%(message)s")


if __name__ == "__main__":
    main()
