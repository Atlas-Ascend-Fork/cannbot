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

"""Assemble task files, assigning numeric IDs by dependency layer and parallel branch."""

import argparse
import logging
import os
import re
import sys
import tempfile
from pathlib import Path

import yaml

LOGGER = logging.getLogger(__name__)

TASK_FIELDS = {
    "task_type",
    "title",
    "goal",
    "approach",
    "acceptance",
    "out_of_scope",
    "executor",
    "verifier",
    "on_exhaust",
}


VARIABLE_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
VARIABLE_REFERENCE = re.compile(r"\{\{var:([A-Za-z_][A-Za-z0-9_]*)\}\}")


class UniqueLoader(yaml.SafeLoader):
    """Reject duplicate YAML keys instead of silently losing task instructions."""


def unique_mapping(loader, node):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if not isinstance(key, str) or key in result:
            raise ValueError(f"non-string or duplicate YAML key: {key!r}")
        result[key] = loader.construct_object(value_node)
    return result


UniqueLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping
)


def load_yaml(path):
    """Use only SafeLoader constructors, with duplicate-key validation."""
    loader = UniqueLoader(path.read_text(encoding="utf-8"))
    try:
        return loader.get_single_data()
    finally:
        loader.dispose()


def bind_variables(declarations, supplied):
    """Bind task-local string variables; null declarations require a value."""
    if not isinstance(declarations, dict) or not isinstance(supplied, dict):
        raise ValueError("variables must be a mapping")
    if any(
        not isinstance(key, str) or not VARIABLE_NAME.fullmatch(key)
        for key in declarations
    ):
        raise ValueError("variable names must be identifiers")
    unknown = set(supplied) - set(declarations)
    if unknown:
        raise ValueError(f"undeclared variables: {sorted(unknown)}")
    values = {**declarations, **supplied}
    for key, default in declarations.items():
        if default is not None and not isinstance(default, str):
            raise ValueError(f"variable {key}: default must be a string or null")
        value = values.get(key)
        if not isinstance(value, str) or (default is None and not value.strip()):
            raise ValueError(
                f"variable {key}: a string value is required (null declarations require nonempty input)"
            )
    return values


def expand_variables(text, values):
    """Replace only explicit placeholders once, without evaluating supplied text."""
    if "{{var" in VARIABLE_REFERENCE.sub("", text):
        raise ValueError("malformed variable placeholder")

    def replace(match):
        name = match.group(1)
        if name not in values:
            raise ValueError(f"undeclared variable reference: {name}")
        return values[name]

    result = VARIABLE_REFERENCE.sub(replace, text)
    if not result.strip():
        raise ValueError("variable expansion produced an empty prompt item")
    return result


def dependency_overrides(dependencies, count):
    overrides = {}
    for specification in dependencies:
        target, separator, sources = specification.partition(":")
        if not separator:
            raise ValueError(
                "--depends-on requires N:M,K or N: for an independent task"
            )
        index = int(target)
        parents = [int(value) for value in sources.split(",")] if sources else []
        if index not in range(1, count + 1) or any(
            value not in range(1, count + 1) for value in parents
        ):
            raise ValueError(f"dependency positions must be between 1 and {count}")
        if index in overrides or len(set(parents)) != len(parents):
            raise ValueError(f"duplicate dependency specification: {specification}")
        overrides[index] = parents
    return overrides


def read_task(source, supplied):
    task = load_yaml(source)
    if (
        not isinstance(task, dict)
        or set(task) - {"procedure", "variables"} != TASK_FIELDS
    ):
        raise ValueError(
            f"{source}: require 9 task fields and optional procedure/variables; "
            "id, depends_on and max_retries are supplied during assembly"
        )
    values = bind_variables(task.pop("variables", {}), supplied)
    if task["task_type"] != "normal":
        raise ValueError(f"{source}: assembly currently accepts normal tasks")
    for key in ["title", "executor", "verifier"]:
        if not isinstance(task[key], str) or not task[key].strip():
            raise ValueError(f"{source}: {key} must be a nonempty string")
    for key in ["goal", "approach", "acceptance", "out_of_scope"] + (
        ["procedure"] if "procedure" in task else []
    ):
        value = task[key]
        if (
            not isinstance(value, list)
            or not value
            or any(not isinstance(x, str) or not x.strip() for x in value)
        ):
            raise ValueError(
                f"{source}: {key} must be a nonempty list of nonempty strings"
            )
    if task["on_exhaust"] not in ("exit", "continue"):
        raise ValueError(f"{source}: on_exhaust must be exit or continue")
    return task, values


def assign_node_ids(nodes):
    by_id = {node["id"]: node for node in nodes}
    depths, visiting = {}, set()

    def depth(tid):
        if tid in visiting:
            raise ValueError(f"dependency cycle at input position {int(tid) + 1}")
        if tid in depths:
            return depths[tid]
        visiting.add(tid)
        depths[tid] = 1 + max(
            (depth(parent) for parent in by_id[tid]["depends_on"]), default=-1
        )
        visiting.remove(tid)
        return depths[tid]

    for tid in by_id:
        depth(tid)
    # Preserve branch order across layers even when task inputs list the other branch first.
    ranks = {}
    for layer in sorted(set(depths.values())):
        peers = [tid for tid in by_id if depths[tid] == layer]
        peers.sort(
            key=lambda tid: (
                tuple(sorted(ranks.get(parent) for parent in by_id[tid]["depends_on"])),
                int(tid),
            )
        )
        for branch, tid in enumerate(peers):
            ranks[tid] = (layer, branch) if len(peers) > 1 else (layer,)
    identifiers = {tid: ".".join(map(str, rank)) for tid, rank in ranks.items()}
    for node in nodes:
        node["id"] = identifiers[node["id"]]
        node["depends_on"] = [identifiers[parent] for parent in node["depends_on"]]


def resolve_report_references(nodes, bindings):
    # Resolve report path IDs before handing the standard YAML to harness.
    by_id = {node["id"]: node for node in nodes}
    ancestors = {}

    def upstream(tid):
        if tid not in ancestors:
            ancestors[tid] = set(by_id[tid]["depends_on"])
            for parent in by_id[tid]["depends_on"]:
                ancestors[tid].update(upstream(parent))
        return ancestors[tid]

    for node, values in zip(nodes, bindings):
        expand_node_prompts(node, values, by_id, upstream)


def expand_node_prompts(node, values, by_id, upstream):
    def resolve_id(match):
        title = match.group(1)
        if title is None:
            return node["id"]
        candidates = {
            tid for tid in upstream(node["id"]) if by_id[tid]["title"] == title
        }
        # A later run of the same producer supersedes its earlier ancestor.
        nearest = candidates - {
            tid for candidate in candidates for tid in upstream(candidate)
        }
        if len(nearest) != 1:
            raise ValueError(
                f"node {node['id']}: report producer {title!r} must resolve to one upstream node"
            )
        return next(iter(nearest))

    for field in ["goal", "approach", "procedure", "acceptance", "out_of_scope"]:
        if field in node:
            node[field] = [
                re.sub(r"\{\{id(?::([^{}]+))?\}\}", resolve_id, item)
                for item in node[field]
            ]
            if any("{{id" in item for item in node[field]):
                raise ValueError(f"node {node['id']}: malformed report ID placeholder")
            node[field] = [expand_variables(item, values) for item in node[field]]


def assemble(files, dependencies, retries, variables=None):
    count = len(files)
    if not count:
        raise ValueError("at least one task is required")
    if len(retries) != count or any(
        type(value) is not int or value < 0 for value in retries
    ):
        raise ValueError("max_retries must be a nonnegative integer for every task")
    supplied = [{} for _ in files] if variables is None else variables
    if len(supplied) != count:
        raise ValueError("variables must be supplied for each task position")
    overrides = dependency_overrides(dependencies, count)
    nodes, bindings = [], []
    for index, source in enumerate(files, 1):
        task, values = read_task(source, supplied[index - 1])
        bindings.append(values)
        parents = overrides.get(index, [index - 1] if index > 1 else [])
        nodes.append(
            {
                "id": str(index - 1),
                **task,
                "max_retries": retries[index - 1],
                "depends_on": [str(value - 1) for value in parents],
            }
        )
    assign_node_ids(nodes)
    resolve_report_references(nodes, bindings)
    return {"workflow": "ops-direct-invoke", "max_parallel": 2, "nodes": nodes}


def template_positions(nodes):
    positions = {}
    for index, node in enumerate(nodes, 1):
        if not isinstance(node, dict) or set(node) - {"variables"} != {
            "id",
            "yaml",
            "depends_on",
            "max_retries",
        }:
            raise ValueError(
                "template nodes require id, yaml, depends_on and max_retries; optional variables"
            )
        identifier = node["id"]
        if not isinstance(identifier, str) or not re.fullmatch(
            r"\d+(?:\.\d+)?", identifier
        ):
            raise ValueError("template id must be a numeric string")
        if identifier in positions:
            raise ValueError(f"duplicate template id: {identifier}")
        positions[identifier] = index
        if not isinstance(node["yaml"], str) or not node["yaml"].strip():
            raise ValueError("task yaml must be a nonempty path")
    return positions


def template_use_when(template):
    """Read discovery metadata; it is not part of the harness workflow schema."""
    value = template.get("use_when") if isinstance(template, dict) else None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("use_when must be a nonempty string")
    return value


COMPLETE_WORKFLOW_FIELDS = {
    "workflow",
    "max_parallel",
    "max_rollbacks",
    "system_prompt",
    "nodes",
}

REFERENCE_NODE_KEYS = {"id", "yaml", "depends_on", "max_retries", "variables"}

CONTENT_TASK_FIELDS = (
    "title",
    "goal",
    "approach",
    "procedure",
    "acceptance",
    "out_of_scope",
)

NODE_KEY_ORDER = (
    "id",
    "task_type",
    "title",
    "goal",
    "approach",
    "procedure",
    "acceptance",
    "out_of_scope",
    "depends_on",
    "executor",
    "verifier",
    "max_retries",
    "on_exhaust",
    "rollback_to",
)


def is_reference_template(definition):
    """A reference template's nodes are pure yaml pointers; anything else is a complete workflow."""
    nodes = definition.get("nodes") if isinstance(definition, dict) else None
    return (
        isinstance(nodes, list)
        and bool(nodes)
        and all(
            isinstance(node, dict)
            and "yaml" in node
            and set(node) <= REFERENCE_NODE_KEYS
            for node in nodes
        )
    )


def read_content_task(source):
    """Load a content task: prompt fields only, scheduling stays in the workflow graph."""
    task = load_yaml(source)
    if not isinstance(task, dict) or set(task) - {"procedure"} != set(
        CONTENT_TASK_FIELDS
    ) - {"procedure"}:
        raise ValueError(
            f"{source}: content task requires title, goal, approach, acceptance, "
            "out_of_scope and optional procedure; scheduling fields stay in the workflow"
        )
    if not isinstance(task["title"], str) or not task["title"].strip():
        raise ValueError(f"{source}: title must be a nonempty string")
    for key in ["goal", "approach", "acceptance", "out_of_scope"] + (
        ["procedure"] if "procedure" in task else []
    ):
        value = task[key]
        if not isinstance(value, list) or any(
            not isinstance(item, str) or not item.strip() for item in value
        ):
            raise ValueError(f"{source}: {key} must be a list of nonempty strings")
    return task


def merge_content_task(node, base):
    """Merge a content task referenced by a complete-workflow node; the graph stays authoritative."""
    source = (base / node["yaml"]).resolve(strict=True)
    task = read_content_task(source)
    overlap = set(node) & set(task) - {"yaml"}
    if overlap:
        raise ValueError(
            f"node {node['id']}: both the workflow and {source.name} define "
            + ", ".join(sorted(overlap))
        )
    merged = {key: task[key] for key in CONTENT_TASK_FIELDS if key in task}
    merged.update({key: value for key, value in node.items() if key != "yaml"})
    unknown = set(merged) - set(NODE_KEY_ORDER)
    if unknown:
        raise ValueError(
            f"node {node['id']}: unknown fields after merge: "
            + ", ".join(sorted(unknown))
        )
    empty = [key for key in CONTENT_TASK_FIELDS if key in merged and not merged[key]]
    if empty:
        LOGGER.warning(
            "node %s: empty content fields pending authoring: %s",
            node["id"],
            ", ".join(empty),
        )
    return {key: merged[key] for key in NODE_KEY_ORDER if key in merged}


def assemble_complete_workflow(definition, base):
    """Freeze a complete workflow as harness input; only selection metadata is removed."""
    unknown = set(definition) - COMPLETE_WORKFLOW_FIELDS - {"use_when"}
    if unknown:
        raise ValueError("unknown top-level keys: " + ", ".join(sorted(unknown)))
    template_use_when(definition)
    definition = {key: value for key, value in definition.items() if key != "use_when"}
    if (
        not isinstance(definition.get("workflow"), str)
        or not definition["workflow"].strip()
    ):
        raise ValueError("workflow must be a nonempty string")
    if (
        type(definition.get("max_parallel")) is not int
        or definition["max_parallel"] < 1
    ):
        raise ValueError("max_parallel must be a positive integer")
    if "max_rollbacks" in definition and (
        type(definition["max_rollbacks"]) is not int or definition["max_rollbacks"] < 0
    ):
        raise ValueError("max_rollbacks must be a non-negative integer")
    if not isinstance(definition.get("nodes"), list) or not definition["nodes"]:
        raise ValueError("complete workflow nodes must be a nonempty list")
    definition["nodes"] = [
        merge_content_task(node, base)
        if isinstance(node, dict) and "yaml" in node
        else node
        for node in definition["nodes"]
    ]
    if definition["workflow"] == "op-dev":
        validate_dsl_roles(definition["nodes"])
    return definition


DSL_ROLES = frozenset(
    {
        "ops-direct-invoke-architect",
        "ops-direct-invoke-developer",
        "ops-direct-invoke-verifier",
    }
)


def validate_dsl_roles(nodes):
    """Fail closed if a CANNBot-DSL node references an uninstalled Agent."""
    for node in nodes:
        if node.get("task_type") == "subgraph":
            continue
        for field in ("executor", "verifier"):
            if node.get(field) not in DSL_ROLES:
                raise ValueError(
                    f"node {node.get('id')}: unknown {field} role {node.get(field)!r}"
                )


def assemble_reference_template(template, path):
    """Expand a graph of positional task references."""
    if not isinstance(template, dict) or set(template) - {"use_when"} != {
        "workflow",
        "max_parallel",
        "nodes",
    }:
        raise ValueError("template requires workflow, max_parallel and nodes")
    if "use_when" in template:
        template_use_when(template)
    if not isinstance(template["workflow"], str) or not template["workflow"].strip():
        raise ValueError("workflow must be a nonempty string")
    if type(template["max_parallel"]) is not int or template["max_parallel"] < 1:
        raise ValueError("max_parallel must be a positive integer")
    nodes = template["nodes"]
    if not isinstance(nodes, list) or not nodes:
        raise ValueError("template nodes must be a nonempty list")
    positions = template_positions(nodes)
    dependencies = []
    for index, node in enumerate(nodes, 1):
        parents = node["depends_on"]
        if not isinstance(parents, list) or any(
            not isinstance(parent, str) or parent not in positions for parent in parents
        ):
            raise ValueError("depends_on must reference template node IDs")
        dependencies.append(
            f"{index}:" + ",".join(str(positions.get(parent)) for parent in parents)
        )
    definition = assemble(
        [path.parent / node["yaml"] for node in nodes],
        dependencies,
        [node["max_retries"] for node in nodes],
        [node.get("variables", {}) for node in nodes],
    )
    if [node["id"] for node in definition["nodes"]] != list(positions):
        raise ValueError("template IDs must match dependency layers and branch order")
    definition.update(
        workflow=template["workflow"], max_parallel=template["max_parallel"]
    )
    if definition["workflow"] == "op-dev":
        validate_dsl_roles(definition["nodes"])
    return definition


def assemble_static_child(node, path, children, ancestors):
    """Compile a declared child; source paths and runtime destinations are independent."""
    if node.get("task_type") != "subgraph":
        raise ValueError("template is only supported on subgraph nodes")
    source, destination = node["template"], node.get("file")
    if not isinstance(source, str) or not source.strip():
        raise ValueError("subgraph template must be a nonempty path")
    if not isinstance(destination, str) or not destination.strip():
        raise ValueError("static subgraph file must be a nonempty relative path")
    target = Path(destination)
    if target.is_absolute() or not target.parts or ".." in target.parts:
        raise ValueError("static subgraph file must stay within the work directory")
    child = assemble_template(path.parent / source, children, ancestors)
    payload = {"nodes": child["nodes"]}
    if target in children and children[target] != payload:
        raise ValueError(f"conflicting static subgraph destination: {target}")
    children[target] = payload
    return {key: value for key, value in node.items() if key != "template"}


def assemble_template(path, children=None, ancestors=()):
    """Compile a template; collect static child outputs separately from harness data."""
    path = path.resolve(strict=True)
    if path in ancestors:
        raise ValueError(f"recursive subgraph template: {path}")
    if children is None:
        children = {}
    template = load_yaml(path)
    if isinstance(template, dict) and isinstance(template.get("nodes"), list):
        template["nodes"] = [
            assemble_static_child(node, path, children, (*ancestors, path))
            if isinstance(node, dict) and "template" in node
            else node
            for node in template["nodes"]
        ]
    if is_reference_template(template):
        definition = assemble_reference_template(template, path)
    else:
        definition = assemble_complete_workflow(template, path.parent)
    if definition["workflow"] == "op-dev":
        for child in children.values():
            validate_dsl_roles(child["nodes"])
    return definition


def publish_workflow(definition, output, reuse=False):
    """Publish a fully written YAML exclusively; reuse only an identical frozen child."""
    rendered = yaml.safe_dump(
        definition, allow_unicode=True, sort_keys=False, width=110
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=output.parent, prefix=".workflow-", delete=False
    ) as stream:
        temporary = Path(stream.name)
    try:
        temporary.write_text(rendered, encoding="utf-8")
        try:
            os.link(temporary, output)
        except FileExistsError:
            if not reuse or output.read_text(encoding="utf-8") != rendered:
                raise FileExistsError(
                    f"workflow already exists or differs: {output}"
                ) from None
    finally:
        temporary.unlink(missing_ok=True)


def write_workflow(definition, output, children=None):
    """Freeze main and child inputs; interrupted assembly may reuse an identical child."""
    if output.exists():
        raise FileExistsError(f"workflow already exists: {output}")
    targets = {output.parent / name: child for name, child in (children or {}).items()}
    if output in targets:
        raise ValueError("static subgraph file conflicts with the main workflow")
    if any(
        not target.resolve().is_relative_to(output.parent.resolve())
        for target in targets
    ):
        raise ValueError("static subgraph file must stay within the work directory")
    for target, child in targets.items():
        publish_workflow(child, target, reuse=True)
    publish_workflow(definition, output)


def write_template(source, output):
    """Compile all templates before publishing any workflow inputs."""
    children = {}
    definition = assemble_template(source, children)
    write_workflow(definition, output, children)
    return definition


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "tasks", nargs="*", type=Path, help="task YAML paths; positions start at 1"
    )
    parser.add_argument(
        "--template", type=Path, help="reference workflow template path"
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        help="required with task paths; retry budget for each task",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="new workflow.yaml path; never overwritten",
    )
    parser.add_argument(
        "--depends-on",
        action="append",
        default=[],
        metavar="N:M,K",
        help="override dependencies of input N with M,K; N: means none; repeat for multiple tasks",
    )
    args = parser.parse_args()
    try:
        output = args.output.absolute()
        if args.template is not None:
            if args.tasks or args.depends_on or args.max_retries is not None:
                raise ValueError(
                    "--template cannot be combined with task paths, --depends-on or --max-retries"
                )
            definition = write_template(args.template, output)
        else:
            if args.max_retries is None:
                raise ValueError("--max-retries is required with task paths")
            definition = assemble(
                args.tasks, args.depends_on, [args.max_retries] * len(args.tasks)
            )
            write_workflow(definition, output)
    except (OSError, ValueError, yaml.YAMLError) as error:
        parser.error(str(error))
    LOGGER.info("%s (%s tasks)", output, len(definition["nodes"]))


if __name__ == "__main__":
    main()
