# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Resolve fixed-worker Python dependencies for remote workspaces."""

from __future__ import annotations

import ast
from collections.abc import Iterable
from pathlib import Path


def resolve_remote_python_bundle(entry_scripts: Iterable[Path]) -> list[Path]:
    """Return fixed-worker scripts and their local static-import closure."""
    entries = [entry.resolve() for entry in entry_scripts]
    if not entries:
        return []
    scripts_root = Path(__file__).resolve().parent
    pending = list(entries)
    resolved: set[Path] = set()
    while pending:
        path = pending.pop()
        if path in resolved:
            continue
        if not _is_local_script(path, scripts_root):
            raise ValueError(f"Bundle entry must be a Python script under {scripts_root}: {path}")
        resolved.add(path)
        pending.extend(_local_import_paths(path, scripts_root))
    return sorted(resolved, key=lambda path: path.relative_to(scripts_root).as_posix())


def _is_local_script(path: Path, scripts_root: Path) -> bool:
    try:
        path.relative_to(scripts_root)
    except ValueError:
        return False
    return path.is_file() and path.suffix == ".py"


def _absolute_import_dependencies(node: ast.Import, scripts_root: Path) -> set[Path]:
    dependencies: set[Path] = set()
    for alias in node.names:
        dependency = _resolve_absolute_module(alias.name, scripts_root)
        if dependency is not None:
            dependencies.add(dependency)
    return dependencies


def _local_import_paths(path: Path, scripts_root: Path) -> list[Path]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    dependencies: set[Path] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            dependencies.update(_absolute_import_dependencies(node, scripts_root))
        elif isinstance(node, ast.ImportFrom):
            dependencies.update(_resolve_from_import(node, path, scripts_root))
    return sorted(dependencies, key=lambda dependency: dependency.as_posix())


def _relative_alias_modules(base: Path, node: ast.ImportFrom) -> set[Path]:
    dependencies: set[Path] = set()
    for alias in node.names:
        dependency = _resolve_module_at(base / alias.name)
        if dependency is not None:
            dependencies.add(dependency)
    return dependencies


def _resolve_from_import(node: ast.ImportFrom, path: Path, scripts_root: Path) -> set[Path]:
    base = path.parent
    if node.level:
        for _ in range(node.level - 1):
            base = base.parent
        if node.module is None:
            return _relative_alias_modules(base, node)
        candidate = _resolve_module_at(base / Path(*node.module.split(".")))
        return {candidate} if candidate is not None else set()
    if node.module is None:
        return set()
    candidate = _resolve_absolute_module(node.module, scripts_root)
    return {candidate} if candidate is not None else set()


def _resolve_absolute_module(module_name: str, scripts_root: Path) -> Path | None:
    return _resolve_module_at(scripts_root / Path(*module_name.split(".")))


def _resolve_module_at(base: Path) -> Path | None:
    module_file = base.with_suffix(".py")
    if module_file.is_file():
        return module_file.resolve()
    package_init = base / "__init__.py"
    if package_init.is_file():
        return package_init.resolve()
    return None
