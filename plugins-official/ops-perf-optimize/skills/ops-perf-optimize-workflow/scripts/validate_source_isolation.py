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

"""Check source edits against a pre-implementation, baseline-bound isolation scope.

This is an edit-boundary check, not a C++ control-flow or SoC reachability proof.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path

from cli_output import emit


CODE_SUFFIXES = {
    ".c", ".cc", ".cpp", ".h", ".hh", ".hpp", ".cce", ".asc", ".inc", ".inl", ".tpp",
    ".cmake", ".py", ".sh", ".ini",
}
BUILD_NAMES = {"CMakeLists.txt", "Makefile", "CMakePresets.json", "CMakeUserPresets.json"}
CONFIG_DIRS = {"config", "configs", "cmake"}
IGNORED_DIRS = {
    ".git", ".pytest_cache", "__pycache__", "build", "build_out", "dist",
    "output", "outputs", "docs",
}


def source_files(root: Path) -> dict[str, Path]:
    if not root.is_dir():
        raise ValueError(f"source root is not a directory: {root}")

    def fail_on_walk_error(error: OSError) -> None:
        raise error

    result = {}
    for current, directories, files in os.walk(root, onerror=fail_on_walk_error):
        directories[:] = sorted(set(directories) - IGNORED_DIRS)
        for name in directories:
            if (Path(current) / name).is_symlink():
                raise ValueError(f"source directory symlink is not isolated: {Path(current) / name}")
        for name in sorted(files):
            path = Path(current) / name
            config = (
                path.suffix.lower() in {".json", ".yaml", ".yml"}
                and CONFIG_DIRS.intersection(path.relative_to(root).parts)
            )
            if path.suffix.lower() not in CODE_SUFFIXES and name not in BUILD_NAMES and not config:
                continue
            if not path.is_file() or path.is_symlink() or path.stat().st_nlink != 1:
                raise ValueError(f"source symlink/hardlink is not isolated: {path}")
            result[path.relative_to(root).as_posix()] = path
    return result


def snapshot(root: Path) -> dict[str, str]:
    return {
        relative: hashlib.sha256(path.read_bytes()).hexdigest()
        for relative, path in source_files(root).items()
    }


def _validate_ranges(before: dict, before_files: dict, ranges: dict) -> None:
    for relative, entries in ranges.items():
        if relative not in before or not isinstance(entries, list) or not entries:
            raise ValueError(f"invalid editable_ranges path or entries: {relative}")
        line_count = len(before_files[relative].read_bytes().splitlines(keepends=True))
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError(f"invalid editable range: {relative}: {entry}")
            start, end = entry.get("start"), entry.get("end")
            if type(start) is not int or type(end) is not int:
                raise ValueError(f"invalid editable range: {relative}: {entry}")
            if not 1 <= start <= end <= line_count:
                raise ValueError(f"invalid editable range: {relative}: {entry}")
            if entry.get("kind") not in {"routing", "target_private"}:
                raise ValueError(f"invalid editable range: {relative}: {entry}")
            reason = entry.get("reason")
            if not isinstance(reason, str) or not reason.strip():
                raise ValueError(f"invalid editable range: {relative}: {entry}")


def _validate_additions(before: dict, additions: dict) -> None:
    for relative, entry in additions.items():
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"new file must use a new relative source path: {relative}")
        if path.as_posix() != relative or relative in before:
            raise ValueError(f"new file must use a new relative source path: {relative}")
        if not isinstance(entry, dict) or "copied_from" not in entry:
            raise ValueError(f"new file requires copied_from (path or null): {relative}")
        origin = entry["copied_from"]
        if origin is not None and (not isinstance(origin, str) or origin not in before):
            raise ValueError(f"copy origin absent from baseline: {relative}: {origin}")


def _covered(allowed: list, tag: str, i1: int, i2: int) -> bool:
    if tag == "insert":
        return any(e["start"] - 1 <= i1 <= e["end"] for e in allowed)
    return any(e["start"] <= i1 + 1 and i2 <= e["end"] for e in allowed)


def _collect_failures(before_files: dict, after_files: dict, before: dict,
                      ranges: dict, additions: dict) -> tuple[list[str], list[str]]:
    failures, changes = [], []
    for relative in sorted(set(before_files) | set(after_files)):
        old = before_files[relative].read_bytes() if relative in before_files else None
        new = after_files[relative].read_bytes() if relative in after_files else None
        if old == new:
            continue
        changes.append(relative)
        if old is None:
            if relative not in additions:
                failures.append(f"undeclared new source/build file: {relative}")
            continue
        if new is None:
            failures.append(f"baseline source/build file deleted: {relative}")
            continue
        matcher = difflib.SequenceMatcher(
            a=old.splitlines(keepends=True), b=new.splitlines(keepends=True), autojunk=False,
        )
        for tag, i1, i2, _j1, _j2 in matcher.get_opcodes():
            if tag == "equal":
                continue
            if not _covered(ranges.get(relative, []), tag, i1, i2):
                failures.append(f"edit outside frozen scope: {relative}:{i1 + 1}-{max(i1 + 1, i2)}")
    for relative in additions:
        if relative not in after_files:
            failures.append(f"declared new source/build file missing: {relative}")
    return failures, changes


def validate_source_isolation(
    scope: dict, baseline: Path, candidate: Path, target_socs: list[str],
) -> dict:
    if scope.get("schema_version") != 1:
        raise ValueError("source isolation schema_version must be 1")
    if not target_socs or scope.get("target_socs") != target_socs:
        raise ValueError("source isolation target_socs must exactly match RUN_MANIFEST")
    baseline = baseline.resolve()
    candidate = candidate.resolve()
    if baseline == candidate or baseline in candidate.parents or candidate in baseline.parents:
        raise ValueError("baseline and candidate must be separate source trees")
    before_files, after_files = source_files(baseline), source_files(candidate)
    before = snapshot(baseline)
    if not before or scope.get("baseline_files") != before:
        raise ValueError("source isolation baseline_files must match the complete source snapshot")
    ranges, additions = scope.get("editable_ranges"), scope.get("new_files")
    if not isinstance(ranges, dict) or not isinstance(additions, dict):
        raise ValueError("editable_ranges and new_files must be objects")
    _validate_ranges(before, before_files, ranges)
    _validate_additions(before, additions)
    failures, changes = _collect_failures(before_files, after_files, before, ranges, additions)
    return {
        "schema_version": 1,
        "decision": "fail" if failures else "pass",
        "target_socs": target_socs,
        "scope_content_sha256": hashlib.sha256(
            json.dumps(scope, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest(),
        "changed_files": changes,
        "failures": failures,
        "limitations": "Checks frozen edit boundaries; route semantics require source review and runtime evidence.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["snapshot"])
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    # Store this artifact outside the source tree; otherwise JSON becomes a build input.
    root, out = args.baseline.resolve(), args.out.resolve()
    if root == out or root in out.parents:
        parser.error("snapshot output must be outside the source tree")
    try:
        value = snapshot(root)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    emit(f"snapshotted {len(value)} source/build inputs: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
