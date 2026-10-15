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
"""实时解析工作流 YAML 的本地网页服务。

解析工作流 YAML 中的节点与依赖关系，并加载每个节点引用的 task YAML 作为节点提示词，
输出成一张纵向的图。页面通过 SSE 监听文件变化，文件一变就重新解析并刷新，无需手动重启。

用法: python3.12 server.py [--workflow PATH] [--port 8765]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import threading
import time
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import yaml

HERE = Path(__file__).resolve().parent
INDEX_FILE = HERE / "index.html"
DEFAULT_WORKFLOW = HERE.parents[1] / (
    "plugins-official/ops-direct-invoke/skills/"
    "ops-direct-invoke/workflows/cannbot-dsl/op-dev.yaml"
)

SECTION_META = {
    # 字段名: (显示名, harness 可见性)。可见性是硬边界：
    # approach 只下发执行者，procedure 只下发验收者，其余字段双方可见。
    "title": ("标题", "both"),
    "goal": ("目标", "both"),
    "approach": ("执行方法", "executor"),
    "procedure": ("验收方法", "verifier"),
    "acceptance": ("交付件", "both"),
    "out_of_scope": ("禁止操作", "both"),
}
SECTION_ORDER = ["title", "goal", "approach", "procedure", "acceptance", "out_of_scope"]
VISIBILITY_LABELS = {
    "both": "双方可见",
    "executor": "仅执行者可见",
    "verifier": "仅验收者可见",
}
NON_PROMPT_KEYS = {
    "task_type",
    "depends_on",
    "executor",
    "verifier",
    "executor_skills",
    "verifier_skills",
    "max_retries",
    "on_exhaust",
    "rollback_to",
    "variables",
    "yaml",
    "yaml_file",
    "task",
    "file",
    "template",
    "id",
}
REF_KEYS = ("yaml", "yaml_file", "task", "file", "template")
SCAN_SUFFIXES = (".yaml", ".yml")
MAX_SCAN_FILES = 5000


class GraphError(Exception):
    """工作流文件本身无法解析。"""


def load_yaml_file(path: Path):
    """读取并解析 YAML；出错时抛 GraphError，由上层展示到页面上。"""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise GraphError(f"读取失败: {path} ({error})") from error
    except UnicodeDecodeError as error:
        raise GraphError(f"不是 UTF-8 文本: {path} ({error})") from error
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise GraphError(f"YAML 解析失败: {path}\n{error}") from error


def display_path(path: Path, root: Path | None) -> str:
    """尽量显示为相对路径，读起来短一些。"""
    try:
        resolved = path.resolve()
    except OSError:
        return str(path)
    if root is not None:
        try:
            return resolved.relative_to(root).as_posix()
        except ValueError:
            pass
    return resolved.as_posix()


def resolve_candidates(base: Path, ref: str) -> list[Path]:
    """引用路径可能相对工作流目录，也可能相对技能根目录，按顺序尝试。"""
    candidate = Path(ref).expanduser()
    if candidate.is_absolute():
        return [candidate]
    bases = [base]
    for ancestor in base.parents:
        if len(bases) >= 4:
            break
        bases.append(ancestor)
    candidates = []
    for root in bases:
        path = root / candidate
        if path not in candidates:
            candidates.append(path)
    return candidates


def resolve_ref(base: Path, ref: str) -> Path:
    """返回引用路径；存在多个候选时优先返回实际存在的那个。"""
    candidates = resolve_candidates(base, ref)
    for path in candidates:
        if path.is_file():
            return path
    return candidates[0]


def to_items(value) -> list:
    """把提示词字段规范化为字符串列表。"""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, bool):
        return ["true" if value else "false"]
    if isinstance(value, (int, float)):
        return [str(value)]
    if isinstance(value, list):
        items = []
        for entry in value:
            if isinstance(entry, str):
                items.append(entry)
            elif entry is None:
                items.append("")
            else:
                items.append(
                    yaml.safe_dump(
                        entry, allow_unicode=True, default_flow_style=True
                    ).strip()
                )
        return items
    return [yaml.safe_dump(value, allow_unicode=True, default_flow_style=True).strip()]


def extract_prompt(path: Path, root: Path | None) -> dict:
    """节点提示词 = task YAML 中除调度字段外的全部内容。"""
    data = load_yaml_file(path)
    if not isinstance(data, dict):
        raise GraphError(f"提示词文件顶层不是映射: {display_path(path, root)}")
    return prompt_from_data(data, path.stat().st_size)


def prompt_from_data(data: dict, size: int = 0) -> dict:
    """文件引用和组装后内联的 task 使用相同的详情结构。"""
    prompt_keys = [key for key in data if key not in NON_PROMPT_KEYS and key != "title"]
    prompt_keys.sort(
        key=lambda key: (
            SECTION_ORDER.index(key) if key in SECTION_ORDER else len(SECTION_ORDER),
            str(key),
        )
    )
    sections = []
    for key in prompt_keys:
        label, visibility = SECTION_META.get(str(key), (str(key), "both"))
        sections.append(
            {
                "key": str(key),
                "label": label,
                "visibility": visibility,
                "visibility_label": VISIBILITY_LABELS[visibility],
                "items": to_items(data[key]),
            }
        )
    meta = []
    excluded_refs = {"yaml", "yaml_file", "task", "file", "template", "id"}
    for key in data:
        if key not in NON_PROMPT_KEYS or key in excluded_refs:
            continue
        meta.append(
            {
                "key": str(key),
                "value": yaml.safe_dump(
                    data[key], allow_unicode=True, default_flow_style=True
                ).strip(),
            }
        )
    title = data.get("title")
    return {
        "title": title.strip() if isinstance(title, str) else "",
        "sections": sections,
        "meta": meta,
        "size": size,
    }


def file_info(path: Path, declared: str, root: Path | None) -> dict:
    exists = path.is_file()
    stat = path.stat() if exists else None
    return {
        "declared": declared,
        "path": path.resolve().as_posix()
        if exists or path.is_absolute()
        else str(path),
        "rel": display_path(path, root),
        "exists": exists,
        "size": stat.st_size if stat else 0,
        # 字符串形式下发，避免 JS Number 精度丢失；保存时原样回传用于冲突检测
        "mtime_ns": str(stat.st_mtime_ns) if stat else "0",
    }


def subgraph_info(path: Path, declared: str, root: Path | None) -> dict:
    info = file_info(path, declared, root)
    info["child_node_ids"] = []
    info["child_count"] = 0
    info["error"] = None
    if info["exists"]:
        try:
            data = load_yaml_file(path)
            nodes = data.get("nodes") if isinstance(data, dict) else None
            if isinstance(nodes, list):
                ids = [
                    str(item.get("id"))
                    for item in nodes
                    if isinstance(item, dict) and item.get("id")
                ]
                info["child_node_ids"] = ids
                info["child_count"] = len(ids)
        except GraphError as error:
            info["error"] = str(error)
    return info


def graph_preview(workflow_path: Path) -> tuple[Path, dict]:
    """Load optional diagram-only descriptions for subgraphs created at runtime."""
    path = workflow_path.with_name(f"{workflow_path.stem}.graph-preview.yaml")
    if not path.is_file():
        return path, {}
    data = load_yaml_file(path)
    if not isinstance(data, dict) or not isinstance(data.get("subgraphs"), dict):
        raise GraphError(f"图预览文件需要 subgraphs 映射: {path}")
    previews = {}
    for node_id, item in data["subgraphs"].items():
        if not isinstance(item, dict) or not isinstance(item.get("title"), str):
            raise GraphError(f"子图 {node_id} 的预览标题无效: {path}")
        stages = item.get("stages")
        if (
            not isinstance(stages, list)
            or not stages
            or any(
                not isinstance(stage, dict)
                or not isinstance(stage.get("title"), str)
                or not isinstance(stage.get("description"), str)
                for stage in stages
            )
        ):
            raise GraphError(f"子图 {node_id} 的预览阶段无效: {path}")
        previews[str(node_id)] = {
            "title": item["title"],
            "runtime_file": str(item.get("runtime_file") or ""),
            "summary": str(item.get("summary") or ""),
            "note": str(item.get("note") or ""),
            "stages": [
                {"title": stage["title"], "description": stage["description"]}
                for stage in stages
            ],
            "source": path.as_posix(),
            "nodes": item.get("nodes"),
            "workflow_file": str(item.get("workflow_file") or ""),
        }
    return path, previews


def node_content(item, node_id, node_type, base, root, previews):
    ref_key = None
    for key in REF_KEYS:
        if isinstance(item.get(key), str) and item[key]:
            ref_key = key
            break
    declared = item[ref_key] if ref_key else ""
    ref = file_info(resolve_ref(base, declared), declared, root) if declared else None
    subgraph = None
    if node_type == "subgraph":
        target = resolve_ref(base, declared) if declared else base / "<缺少 file 字段>"
        subgraph = subgraph_info(target, declared or "缺少 file 字段", root)
        if not subgraph["exists"] and node_id in previews:
            subgraph["preview"] = previews[node_id]

    prompt, prompt_error = node_prompt(item, node_type, ref, subgraph, root)
    return ref, subgraph, prompt, prompt_error


def node_prompt(item, node_type, ref, subgraph, root):
    if node_type == "subgraph":
        return None, None  # 子图 YAML 是调度图，不作为 task 提示词展示。
    if ref is not None and ref["exists"]:
        try:
            return extract_prompt(Path(ref["path"]), root), None
        except GraphError as error:
            return None, str(error)
    if ref is not None and not (subgraph and subgraph.get("preview")):
        return None, f"提示词文件不存在: {ref['rel']}"
    if any(key in item for key in SECTION_ORDER):
        return prompt_from_data(item), None
    return None, None


def node_extra(item):
    excluded = {
        "id",
        "task_type",
        "depends_on",
        "executor",
        "verifier",
        "max_retries",
        "on_exhaust",
        "rollback_to",
        *REF_KEYS,
    }
    extra = []
    for key, value in item.items():
        if key in excluded:
            continue
        extra.append(
            {
                "key": str(key),
                "value": yaml.safe_dump(
                    value, allow_unicode=True, default_flow_style=True
                ).strip(),
            }
        )
    return extra


def parse_node(item, node_id, index, base, root, previews):
    node_type = str(
        item.get("task_type") or ("subgraph" if item.get("file") else "normal")
    )
    depends_on = item.get("depends_on") or []
    if isinstance(depends_on, str):
        depends_on = [depends_on]
    depends_on = [str(dep) for dep in depends_on if dep]

    ref, subgraph, prompt, prompt_error = node_content(
        item, node_id, node_type, base, root, previews
    )

    node = {
        "id": node_id,
        "index": index,
        "layer": 0,
        "task_type": node_type,
        "depends_on": depends_on,
        "dependents": [],
        "executor": item.get("executor"),
        "verifier": item.get("verifier"),
        "max_retries": item.get("max_retries"),
        "on_exhaust": item.get("on_exhaust"),
        "rollback_to": item.get("rollback_to"),
        "extra": node_extra(item),
        "ref": ref,
        "subgraph": subgraph,
        "prompt": prompt,
        "prompt_error": prompt_error,
        "in_cycle": False,
    }
    return node


def parse_nodes(nodes_raw, base, root, previews, warnings):
    nodes: list[dict] = []
    by_id: dict[str, dict] = {}

    for index, item in enumerate(nodes_raw, start=1):
        if not isinstance(item, dict):
            warnings.append(f"第 {index} 个节点不是映射，已跳过")
            continue
        node_id = item.get("id")
        node_id = str(node_id).strip() if node_id else f"node-{index}"
        if not node_id:
            node_id = f"node-{index}"
        if node_id in by_id:
            warnings.append(f"节点 id 重复: {node_id}（保留第一个）")
            continue
        node = parse_node(item, node_id, index, base, root, previews)
        nodes.append(node)
        by_id[node_id] = node

    return nodes, by_id


def connect_nodes(nodes, by_id, warnings):
    edges: list[dict] = []
    rollbacks: list[dict] = []
    for node in nodes:
        keeps = []
        for dep in node["depends_on"]:
            if dep == node["id"]:
                warnings.append(f"节点 {node['id']} 依赖自身，已忽略")
                continue
            if dep not in by_id:
                warnings.append(f"节点 {node['id']} 依赖了不存在的节点: {dep}")
                continue
            keeps.append(dep)
            edges.append({"from": dep, "to": node["id"]})
        node["depends_on"] = keeps
        target = node["rollback_to"]
        if target:
            if str(target) in by_id:
                rollbacks.append({"from": node["id"], "to": str(target)})
            else:
                warnings.append(
                    f"节点 {node['id']} 的 rollback_to 指向不存在的节点: {target}"
                )
    for node in nodes:
        for dep in node["depends_on"]:
            by_id[dep]["dependents"].append(node["id"])

    return edges, rollbacks


def graph_stats(nodes, edges, layers):
    stats = {
        "nodes": len(nodes),
        "edges": len(edges),
        "layers": len(layers),
        "parallel_nodes": max((len(layer) for layer in layers), default=0),
        "subgraphs": sum(1 for node in nodes if node["task_type"] == "subgraph"),
        "missing_prompts": sum(
            1
            for node in nodes
            if node["prompt"] is None
            and not (
                node["subgraph"]
                and (node["subgraph"].get("preview") or node["subgraph"]["exists"])
            )
        ),
    }
    return stats


def workflow_info(workflow_path, root, data):
    return {
        "file": workflow_path.as_posix(),
        "rel": display_path(workflow_path, root),
        "name": str(data.get("workflow") or workflow_path.stem),
        "use_when": data.get("use_when")
        if isinstance(data.get("use_when"), str)
        else "",
        "max_parallel": data.get("max_parallel"),
        "max_rollbacks": data.get("max_rollbacks"),
        "style": data.get("style"),
        "other": [
            {
                "key": str(key),
                "value": yaml.safe_dump(
                    value, allow_unicode=True, default_flow_style=True
                ).strip(),
            }
            for key, value in data.items()
            if key
            not in (
                "nodes",
                "workflow",
                "use_when",
                "max_parallel",
                "max_rollbacks",
            )
        ],
    }


def build_graph(workflow_path: Path, ancestors: tuple[Path, ...] = ()) -> dict:
    """重新解析工作流 YAML 及其节点提示词，返回前端需要的完整结构。"""
    workflow_path = workflow_path.expanduser()
    workflow_path = workflow_path.resolve() if workflow_path.exists() else workflow_path
    if workflow_path in ancestors or len(ancestors) >= 12:
        raise GraphError(f"子图引用循环或超过 12 层: {workflow_path}")
    root = find_root(workflow_path)
    data = load_yaml_file(workflow_path)
    _, previews = graph_preview(workflow_path)
    graph = graph_from_data(workflow_path, root, data, previews)
    for node in graph["nodes"]:
        node["prompt_editable"] = bool(
            not ancestors
            and node["task_type"] != "subgraph"
            and any(
                isinstance(item, dict)
                and item.get("id") == node["id"]
                and any(item.get(key) for key in PROMPT_REF_KEYS)
                for item in data["nodes"]
            )
        )
        subgraph = node["subgraph"]
        if not subgraph:
            continue
        try:
            child = build_child_graph(subgraph, workflow_path, root, ancestors)
            if child is None:
                continue
            subgraph["graph"] = child
            subgraph["child_node_ids"] = [item["id"] for item in child["nodes"]]
            subgraph["child_count"] = len(child["nodes"])
        except GraphError as error:
            subgraph["error"] = str(error)
            graph["warnings"].append(f"子图 {node['id']}: {error}")
    return graph


def build_child_graph(subgraph, workflow_path, root, ancestors):
    child_ancestors = (*ancestors, workflow_path)
    if subgraph["exists"]:
        child = build_graph(Path(subgraph["path"]), child_ancestors)
        child["view_kind"] = "actual"
        child["view_note"] = "真实子图文件；显示已生成节点及依赖，不表示执行状态。"
        return child
    preview = subgraph.get("preview")
    if not preview:
        return None
    if preview["workflow_file"]:
        target = resolve_ref(workflow_path.parent, preview["workflow_file"])
        child = build_graph(target, child_ancestors)
    elif preview["nodes"]:
        child = graph_from_data(
            workflow_path,
            root,
            {"workflow": preview["title"], "nodes": preview["nodes"]},
            {},
        )
    else:
        return None  # 兼容仅包含阶段说明的旧预览。
    child["view_kind"] = "planned"
    child["workflow"]["name"] = preview["title"]
    child["view_note"] = preview["note"] or "规划结构，实际运行文件尚未生成。"
    for child_node in child["nodes"]:
        child_node["prompt_editable"] = False
    return child


def graph_from_data(workflow_path, root, data, previews):
    """复用同一解析、分层及边构建逻辑处理主图与规划子图。"""
    if not isinstance(data, dict):
        raise GraphError(f"工作流顶层不是映射: {display_path(workflow_path, root)}")
    nodes_raw = data.get("nodes")
    if not isinstance(nodes_raw, list) or not nodes_raw:
        raise GraphError(
            f"工作流未包含 nodes 列表: {display_path(workflow_path, root)}"
        )

    warnings: list[str] = []
    nodes, by_id = parse_nodes(
        nodes_raw, workflow_path.parent, root, previews, warnings
    )
    edges, rollbacks = connect_nodes(nodes, by_id, warnings)
    layers = assign_layers(nodes, by_id, warnings)
    stats = graph_stats(nodes, edges, layers)
    return {
        "ok": True,
        "workflow": workflow_info(workflow_path, root, data),
        "root": root.as_posix() if root else "",
        "parsed_at": datetime.now(timezone.utc).astimezone().strftime("%H:%M:%S"),
        "nodes": nodes,
        "edges": edges,
        "rollbacks": rollbacks,
        "layers": layers,
        "stats": stats,
        "warnings": warnings,
    }


def assign_layers(
    nodes: list[dict], by_id: dict[str, dict], warnings: list[str]
) -> list[list[str]]:
    """按最长路径分层：每个节点必须排在所有依赖之后；有环时把剩余节点放到最后一层。"""
    pending = {node["id"]: set(node["depends_on"]) for node in nodes}
    resolved: dict[str, int] = {}
    ready = [node["id"] for node in nodes if not pending[node["id"]]]
    while ready:
        current = ready.pop(0)
        depth = 0
        for dep in by_id[current]["depends_on"]:
            depth = max(depth, resolved[dep] + 1)
        resolved[current] = depth
        for dependent in by_id[current]["dependents"]:
            pending[dependent].discard(current)
            if (
                not pending[dependent]
                and dependent not in resolved
                and dependent not in ready
            ):
                ready.append(dependent)
    leftover = [node["id"] for node in nodes if node["id"] not in resolved]
    if leftover:
        warnings.append("检测到依赖环，节点已放到最后一层: " + ", ".join(leftover))
        for node_id in leftover:
            resolved[node_id] = max(resolved.values(), default=-1) + 1
            by_id[node_id]["in_cycle"] = True
    depth_max = max(resolved.values(), default=0)
    layers: list[list[str]] = [[] for _ in range(depth_max + 1)]
    for node in nodes:
        node["layer"] = resolved[node["id"]]
        layers[resolved[node["id"]]].append(node["id"])
    for node in nodes:
        if node["in_cycle"]:
            node["layer"] = len(layers) - 1
    return layers


def find_root(workflow_path: Path) -> Path | None:
    """用于把绝对路径显示成仓库内相对路径。"""
    for parent in [workflow_path.parent, *workflow_path.parents]:
        if (parent / ".git").exists():
            return parent
    return workflow_path.parent


def watch_spec(workflow_path: Path) -> tuple[list[Path], list[Path]]:
    """需要监听的文件：工作流自身 + 它引用的 task / 子图；目录用于发现新增文件。"""
    files: list[Path] = []
    dirs: list[Path] = []
    workflow_path = workflow_path.expanduser()
    if workflow_path.exists():
        files.append(workflow_path.resolve())
        dirs.append(workflow_path.resolve().parent)
    preview_path = workflow_path.with_name(f"{workflow_path.stem}.graph-preview.yaml")
    files.append(preview_path)
    try:
        data = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError, UnicodeDecodeError):
        return files, dirs
    if not isinstance(data, dict):
        return files, dirs
    base = workflow_path.parent
    for item in data.get("nodes") or []:
        if not isinstance(item, dict):
            continue
        for key in REF_KEYS:
            ref = item.get(key)
            if not isinstance(ref, str) or not ref:
                continue
            target = resolve_ref(base, ref)
            files.append(Path(target))
            dirs.append(Path(target).parent)
    try:
        graph = build_graph(workflow_path)
    except GraphError:
        return files, dirs

    def collect(current):
        files.append(Path(current["workflow"]["file"]))
        for node in current["nodes"]:
            if node["ref"]:
                target = Path(node["ref"]["path"])
                files.append(target)
                dirs.append(target.parent)
            subgraph = node["subgraph"]
            if subgraph and subgraph.get("preview"):
                files.append(Path(subgraph["preview"]["source"]))
            if subgraph and subgraph.get("graph"):
                collect(subgraph["graph"])

    collect(graph)
    return files, dirs


def normalize(path: Path) -> Path:
    """展开 .. 与符号链接，保证同一文件只有一个监听键。"""
    try:
        return path.resolve()
    except OSError:
        return path


EDITABLE_FIELDS = (
    "title",
    "goal",
    "approach",
    "procedure",
    "acceptance",
    "out_of_scope",
)
REQUIRED_LIST_FIELDS = ("goal", "approach", "acceptance", "out_of_scope")
PROMPT_REF_KEYS = (
    "yaml",
    "yaml_file",
    "task",
)  # file/template 指向子图，运行时生成，不可编辑


def prompt_targets(workflow_path: Path) -> set[str]:
    """当前工作流节点引用的提示词文件集合（规范化绝对路径），编辑只允许落在这些文件上。"""
    data = load_yaml_file(workflow_path)
    targets: set[str] = set()
    if not isinstance(data, dict):
        return targets
    base = workflow_path.parent
    for item in data.get("nodes") or []:
        if not isinstance(item, dict):
            continue
        key = next(
            (
                k
                for k in PROMPT_REF_KEYS
                if isinstance(item.get(k), str) and item.get(k)
            ),
            None,
        )
        if key:
            targets.add(normalize(resolve_ref(base, item[key])).as_posix())
    return targets


def editable_target(workflow_path: Path, payload: dict):
    raw_path = payload.get("path")
    if not isinstance(raw_path, str) or not raw_path:
        return None, ({"ok": False, "error": "缺少 path"}, 400)
    target = normalize(Path(raw_path).expanduser())
    if target.as_posix() not in prompt_targets(workflow_path):
        return None, (
            {
                "ok": False,
                "error": f"不是当前工作流节点引用的提示词文件: {raw_path}",
            },
            403,
        )
    try:
        stat = target.stat()
    except OSError:
        return None, ({"ok": False, "error": f"文件不存在: {raw_path}"}, 400)
    base_mtime = payload.get("base_mtime_ns")
    base_size = payload.get("base_size")
    try:
        stale = (
            str(stat.st_mtime_ns) != str(base_mtime) or int(base_size) != stat.st_size
        )
    except (TypeError, ValueError):
        stale = True
    if stale:
        return None, (
            {
                "ok": False,
                "conflict": True,
                "error": "文件已在别处被修改，请取消编辑后重新打开，获取最新内容",
            },
            409,
        )
    return target, None


def save_prompt(workflow_path: Path, payload: dict) -> tuple[dict, int]:
    """把面板编辑的字段写回 task YAML；字段名与 YAML 键一一对应。返回 (结果, HTTP 状态码)。"""
    target, error = editable_target(workflow_path, payload)
    if error is not None:
        return error
    fields = payload.get("fields")
    if not isinstance(fields, dict) or not fields:
        return {"ok": False, "error": "fields 必须是非空映射"}, 400
    unknown = sorted(set(fields) - set(EDITABLE_FIELDS))
    if unknown:
        return {"ok": False, "error": "不允许编辑的字段: " + ", ".join(unknown)}, 400
    data = load_yaml_file(target)
    if not isinstance(data, dict):
        return {"ok": False, "error": "提示词文件顶层不是映射"}, 400
    for key, value in fields.items():
        if key == "title":
            if not isinstance(value, str) or not value.strip():
                return {"ok": False, "error": "title 必须是非空字符串"}, 400
            data["title"] = value.strip()
            continue
        if not isinstance(value, list) or any(
            not isinstance(item, str) or not item.strip() for item in value
        ):
            return {"ok": False, "error": f"{key} 必须是非空字符串列表"}, 400
        if not value and key in REQUIRED_LIST_FIELDS:
            return {"ok": False, "error": f"{key} 至少要保留一个条目"}, 400
        if not value and key == "procedure":
            data.pop("procedure", None)  # procedure 是可选字段，清空即移除
        else:
            data[key] = list(value)
    text = yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=4096)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(target)
    return {"ok": True}, 200


def watch_signature(workflow_path: Path) -> dict[str, tuple[int, int]]:
    files, dirs = watch_spec(workflow_path)
    signature: dict[str, tuple[int, int]] = {}
    seen_dirs: set[Path] = set()
    for path in files:
        path = normalize(path)
        try:
            stat = path.stat()
        except OSError:
            signature[path.as_posix()] = (-1, -1)
            continue
        signature[path.as_posix()] = (stat.st_mtime_ns, stat.st_size)
    for directory in dirs:
        try:
            key = normalize(directory)
        except OSError:
            continue
        if key in seen_dirs or not key.is_dir():
            continue
        seen_dirs.add(key)
        count = 0
        for child in sorted(key.rglob("*")):
            if count > MAX_SCAN_FILES:
                break
            if not child.is_file() or child.suffix not in SCAN_SUFFIXES:
                continue
            count += 1
            try:
                stat = child.stat()
            except OSError:
                continue
            signature[child.as_posix()] = (stat.st_mtime_ns, stat.st_size)
    return signature


class Watcher(threading.Thread):
    """轮询文件签名，发现变化后唤醒所有 SSE 连接。"""

    def __init__(self, workflow_path: Path, interval: float = 0.8):
        super().__init__(daemon=True, name="watcher")
        self.workflow_path = workflow_path
        self.interval = interval
        self.condition = threading.Condition()
        self.version = 0
        self.signature: dict[str, tuple[int, int]] = {}
        self.changed: list[str] = []
        self.stop_flag = threading.Event()

    def snapshot(self) -> tuple[int, list[str]]:
        with self.condition:
            return self.version, list(self.changed)

    def wait(self, version: int, timeout: float) -> tuple[int, list[str]]:
        with self.condition:
            if self.version == version:
                self.condition.wait(timeout)
            return self.version, list(self.changed)

    def publish_change(self, current) -> None:
        changed = [
            path
            for path in sorted(set(current) | set(self.signature))
            if current.get(path) != self.signature.get(path)
        ]
        self.signature = current
        with self.condition:
            self.version += 1
            self.changed = changed
            self.condition.notify_all()

    def run(self) -> None:
        while not self.stop_flag.is_set():
            try:
                current = watch_signature(self.workflow_path)
            except Exception:  # 轮询期间任何异常都不应中断监听
                current = {}
            if current != self.signature:
                self.publish_change(current)
            self.stop_flag.wait(self.interval)


class Handler(BaseHTTPRequestHandler):
    server_version = "WorkflowGraph/1.0"
    protocol_version = "HTTP/1.0"

    def log_message(self, fmt: str, *args) -> None:
        if self.path.startswith("/api/events"):
            return
        logging.info(
            "[%s] %s %s", time.strftime("%H:%M:%S"), self.address_string(), fmt % args
        )

    def do_get(self) -> None:
        route = urlparse(self.path).path
        try:
            if route in ("/", "/index.html"):
                self.send_file(INDEX_FILE, "text/html; charset=utf-8")
            elif route == "/api/graph":
                self.send_json(self.build_payload())
            elif route == "/api/events":
                self.serve_events()
            elif route == "/api/health":
                self.send_json({"ok": True, "version": self.server.watcher.version})
            else:
                self.send_error(404, "not found")
        except (BrokenPipeError, ConnectionResetError):
            pass

    def build_payload(self) -> dict:
        workflow = self.server.workflow_path
        try:
            return build_graph(workflow)
        except GraphError as error:
            return {
                "ok": False,
                "error": str(error),
                "workflow": {
                    "file": workflow.as_posix(),
                    "rel": workflow.name,
                    "name": workflow.stem,
                },
                "parsed_at": datetime.now(timezone.utc)
                .astimezone()
                .strftime("%H:%M:%S"),
            }

    def serve_events(self) -> None:
        watcher = self.server.watcher
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        version, changed = watcher.snapshot()
        self.push(
            "ready",
            {"version": version, "workflow": self.server.workflow_path.as_posix()},
        )
        while True:
            version, changed = watcher.wait(version, 15.0)
            if self.server.stop_flag.is_set():
                break
            if changed:
                self.push("change", {"version": version, "changed": changed})
            else:
                self.wfile.write(b": ping\n\n")
                self.wfile.flush()

    def push(self, event: str, payload: dict) -> None:
        body = f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n".encode(
            "utf-8"
        )
        self.wfile.write(body)
        self.wfile.flush()

    def do_post(self) -> None:
        route = urlparse(self.path).path
        try:
            if route != "/api/save-prompt":
                self.send_error(404, "not found")
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(max(length, 0)).decode("utf-8")
                payload = json.loads(raw) if raw.strip() else {}
            except ValueError:
                self.send_json({"ok": False, "error": "请求体不是有效 JSON"}, 400)
                return
            if not isinstance(payload, dict):
                self.send_json({"ok": False, "error": "请求体必须是 JSON 对象"}, 400)
                return
            try:
                result, status = save_prompt(self.server.workflow_path, payload)
            except GraphError as error:
                result, status = {"ok": False, "error": str(error)}, 400
            self.send_json(result, status)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=None).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path: Path, content_type: str) -> None:
        try:
            body = path.read_bytes()
        except OSError:
            self.send_error(500, f"missing {path.name}")
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


Handler.do_GET = Handler.do_get
Handler.do_POST = Handler.do_post


def bind_server(
    host: str, port: int, attempts: int = 20
) -> tuple[ThreadingHTTPServer, int]:
    """端口被占用时顺延，避免和机器上其它服务冲突。"""
    last_error: OSError | None = None
    for offset in range(attempts):
        try:
            return ThreadingHTTPServer((host, port + offset), Handler), port + offset
        except OSError as error:
            last_error = error
    raise OSError(f"无法监听 {host}:{port}~{port + attempts - 1}: {last_error}")


def main() -> None:
    parser = argparse.ArgumentParser(description="实时解析工作流 YAML 的网页服务")
    parser.add_argument(
        "--workflow", type=Path, default=DEFAULT_WORKFLOW, help="工作流 YAML 路径"
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open", action="store_true", help="启动后自动打开浏览器")
    args = parser.parse_args()

    workflow_path = args.workflow.expanduser()
    if not workflow_path.is_absolute():
        workflow_path = (Path.cwd() / workflow_path).resolve()
    if not workflow_path.is_file():
        parser.error(f"工作流文件不存在: {workflow_path}")

    watcher = Watcher(workflow_path)
    try:
        server, port = bind_server(args.host, args.port)
    except OSError as error:
        parser.exit(1, f"{error}\n")
    server.daemon_threads = True
    server.watcher = watcher
    server.workflow_path = workflow_path
    server.stop_flag = watcher.stop_flag
    watcher.start()

    url = f"http://{args.host}:{port}/"
    logging.info("工作流: %s", workflow_path)
    logging.info("打开:   %s   (Ctrl+C 退出)", url)
    if args.open:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        logging.info("\n已退出")
    finally:
        watcher.stop_flag.set()
        server.server_close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    main()
