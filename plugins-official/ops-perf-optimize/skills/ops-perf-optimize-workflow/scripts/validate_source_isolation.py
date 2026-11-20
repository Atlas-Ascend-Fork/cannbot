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

from cli_output import atomic_json, emit
from git_tree import (
    GitTree,
    git_diff_name_status,
    old_side_opcodes,
    source_filtered,
    tree_sha,
    tree_snapshot,
)


CODE_SUFFIXES = {
    ".c",
    ".cc",
    ".cpp",
    ".h",
    ".hh",
    ".hpp",
    ".cce",
    ".asc",
    ".inc",
    ".inl",
    ".tpp",
    ".cmake",
    ".py",
    ".sh",
    ".ini",
}
BUILD_NAMES = {
    "CMakeLists.txt",
    "Makefile",
    "CMakePresets.json",
    "CMakeUserPresets.json",
}
CONFIG_DIRS = {"config", "configs", "cmake"}
IGNORED_DIRS = {
    ".git",
    ".pytest_cache",
    "__pycache__",
    "build",
    "build_out",
    "dist",
    "output",
    "outputs",
    "docs",
    "golden_cache",
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
                raise ValueError(
                    f"source directory symlink is not isolated: {Path(current) / name}"
                )
        for name in sorted(files):
            path = Path(current) / name
            config = path.suffix.lower() in {
                ".json",
                ".yaml",
                ".yml",
            } and CONFIG_DIRS.intersection(path.relative_to(root).parts)
            if (
                path.suffix.lower() not in CODE_SUFFIXES
                and name not in BUILD_NAMES
                and not config
            ):
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


def _validate_ranges(before: dict, line_counts: dict[str, int], ranges: dict) -> None:
    for relative, entries in ranges.items():
        if relative not in before or not isinstance(entries, list) or not entries:
            raise ValueError(f"invalid editable_ranges path or entries: {relative}")
        line_count = line_counts[relative]
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
            raise ValueError(
                f"new file must use a new relative source path: {relative}"
            )
        if path.as_posix() != relative or relative in before:
            raise ValueError(
                f"new file must use a new relative source path: {relative}"
            )
        if not isinstance(entry, dict) or "copied_from" not in entry:
            raise ValueError(
                f"new file requires copied_from (path or null): {relative}"
            )
        origin = entry["copied_from"]
        if origin is not None and (not isinstance(origin, str) or origin not in before):
            raise ValueError(f"copy origin absent from baseline: {relative}: {origin}")


def _covered(allowed: list, tag: str, i1: int, i2: int) -> bool:
    if tag == "insert":
        return any(e["start"] - 1 <= i1 <= e["end"] for e in allowed)
    # SequenceMatcher can join edits in separately authorized adjacent ranges.
    # Check their exact union; an unauthorized gap must still reject the edit.
    cursor = i1 + 1
    for entry in sorted(allowed, key=lambda e: e["start"]):
        if entry["end"] < cursor:
            continue
        if entry["start"] > cursor:
            return False
        cursor = entry["end"] + 1
        if cursor > i2:
            return True
    return False


def _collect_failures(
    before_files: dict, after_files: dict, before: dict, ranges: dict, additions: dict
) -> tuple[list[str], list[str]]:
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
            a=old.splitlines(keepends=True),
            b=new.splitlines(keepends=True),
            autojunk=False,
        )
        for tag, i1, i2, _j1, _j2 in matcher.get_opcodes():
            if tag == "equal":
                continue
            if not _covered(ranges.get(relative, []), tag, i1, i2):
                failures.append(
                    f"edit outside frozen scope: {relative}:{i1 + 1}-{max(i1 + 1, i2)}"
                )
    for relative in additions:
        if relative not in after_files:
            failures.append(f"declared new source/build file missing: {relative}")
    return failures, changes


def validate_source_isolation(
    scope: dict,
    baseline: Path,
    candidate: Path,
    target_socs: list[str],
) -> dict:
    if scope.get("schema_version") != 1:
        raise ValueError("source isolation schema_version must be 1")
    if not target_socs or scope.get("target_socs") != target_socs:
        raise ValueError("source isolation target_socs must exactly match RUN_MANIFEST")
    baseline = baseline.resolve()
    candidate = candidate.resolve()
    if (
        baseline == candidate
        or baseline in candidate.parents
        or candidate in baseline.parents
    ):
        raise ValueError("baseline and candidate must be separate source trees")
    before_files, after_files = source_files(baseline), source_files(candidate)
    before = snapshot(baseline)
    if not before or scope.get("baseline_files") != before:
        raise ValueError(
            "source isolation baseline_files must match the complete source snapshot"
        )
    ranges, additions = scope.get("editable_ranges"), scope.get("new_files")
    if not isinstance(ranges, dict) or not isinstance(additions, dict):
        raise ValueError("editable_ranges and new_files must be objects")
    line_counts = {
        relative: len(path.read_bytes().splitlines(keepends=True))
        for relative, path in before_files.items()
    }
    _validate_ranges(before, line_counts, ranges)
    _validate_additions(before, additions)
    failures, changes = _collect_failures(
        before_files, after_files, before, ranges, additions
    )
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


def snapshot_from_git(repo: Path, rev: str) -> dict[str, str]:
    """Git-mode snapshot with the same shape as the directory snapshot."""
    return tree_snapshot(
        GitTree(repo, rev),
        CODE_SUFFIXES,
        BUILD_NAMES,
        CONFIG_DIRS,
        IGNORED_DIRS,
    )


def validate_source_isolation_git(
    scope: dict,
    repo: Path,
    baseline_rev: str,
    candidate_rev: str,
    target_socs: list[str],
) -> dict:
    """Git-native variant of validate_source_isolation over scope schema v2.

    The frozen identity is the baseline commit instead of a baseline_files
    snapshot; editable_ranges and new_files keep the schema v1 semantics.
    """
    if scope.get("schema_version") != 2:
        raise ValueError("source isolation git schema_version must be 2")
    if not target_socs or scope.get("target_socs") != target_socs:
        raise ValueError("source isolation target_socs must exactly match RUN_MANIFEST")
    repo = repo.resolve()
    baseline = GitTree(repo, baseline_rev)
    candidate = GitTree(repo, candidate_rev)
    if scope.get("baseline_commit") != baseline.commit:
        raise ValueError(
            "source isolation baseline_commit must match the resolved baseline revision"
        )
    declared_tree = scope.get("baseline_tree_sha")
    if declared_tree is not None and declared_tree != tree_sha(repo, baseline.commit):
        raise ValueError(
            "source isolation baseline_tree_sha does not match the baseline commit"
        )

    before = source_filtered(
        baseline.entries(IGNORED_DIRS), CODE_SUFFIXES, BUILD_NAMES, CONFIG_DIRS
    )
    after = source_filtered(
        candidate.entries(IGNORED_DIRS), CODE_SUFFIXES, BUILD_NAMES, CONFIG_DIRS
    )
    for relative, kind in {**before, **after}.items():
        if kind == "gitlink":
            continue
        if kind != "file":
            raise ValueError(f"source symlink/hardlink is not isolated: {relative}")
    ranges, additions = scope.get("editable_ranges"), scope.get("new_files")
    if not isinstance(ranges, dict) or not isinstance(additions, dict):
        raise ValueError("editable_ranges and new_files must be objects")
    line_counts = {}
    for relative in before:
        if relative in ranges:
            content = baseline.read_bytes(relative)
            if content is not None:
                line_counts[relative] = len(content.splitlines())
        else:
            line_counts[relative] = 10**9  # sentinel: no range checks needed
    _validate_ranges(before, line_counts, ranges)
    _validate_additions(before, additions)

    changed = git_diff_name_status(repo, baseline.commit, candidate.commit)
    failures: list[str] = []
    changes: list[str] = []
    # Performance: compare blob SHAs from git ls-tree to skip unchanged files
    # without reading their content (avoids N×git show subprocess calls).
    baseline_blobs = baseline.blob_shas()
    candidate_blobs = candidate.blob_shas()
    for relative in sorted(set(before) | set(after)):
        if before.get(relative) == "gitlink" or after.get(relative) == "gitlink":
            if relative in changed:
                failures.append(
                    f"submodule change requires manual adjudication: {relative}"
                )
                changes.append(relative)
            continue
        if baseline_blobs.get(relative) == candidate_blobs.get(relative):
            continue  # identical blob SHA = identical content, skip
        changes.append(relative)
        old = baseline.read_bytes(relative)
        new = candidate.read_bytes(relative)
        if old == new:
            continue
        if old is None:
            if relative not in additions:
                failures.append(f"undeclared new source/build file: {relative}")
            continue
        if new is None:
            failures.append(f"baseline source/build file deleted: {relative}")
            continue
        for tag, i1, i2 in old_side_opcodes(baseline, candidate, relative):
            if not _covered(ranges.get(relative, []), tag, i1, i2):
                failures.append(
                    f"edit outside frozen scope: {relative}:{i1 + 1}-{max(i1 + 1, i2)}"
                )
    for relative in additions:
        if relative not in after:
            failures.append(f"declared new source/build file missing: {relative}")

    return {
        "schema_version": 2,
        "decision": "fail" if failures else "pass",
        "target_socs": target_socs,
        "baseline_commit": baseline.commit,
        "candidate_commit": candidate.commit,
        "baseline_tree": tree_sha(repo, baseline.commit),
        "candidate_tree": tree_sha(repo, candidate.commit),
        "scope_content_sha256": hashlib.sha256(
            json.dumps(scope, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest(),
        "changed_files": changes,
        "failures": failures,
        "limitations": "Checks frozen edit boundaries; route semantics require source review and runtime evidence.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=["snapshot", "snapshot-git", "validate-git"],
        help="snapshot: directory snapshot; snapshot-git: git revision snapshot; "
        "validate-git: gate a candidate revision against a frozen v2 scope",
    )
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--git-repo", type=Path)
    parser.add_argument("--rev")
    parser.add_argument("--baseline-rev")
    parser.add_argument("--candidate-rev")
    parser.add_argument("--scope", type=Path)
    parser.add_argument("--target-soc", action="append", default=None)
    args = parser.parse_args()
    # Store this artifact outside the source tree; otherwise JSON becomes a build input.
    if args.action == "snapshot":
        root, out = args.baseline, args.out
        if root is None or out is None:
            parser.error("snapshot requires --baseline and --out")
        root, out = root.resolve(), out.resolve()
        if root == out or root in out.parents:
            parser.error("snapshot output must be outside the source tree")
        try:
            value = snapshot(root)
        except (OSError, ValueError) as error:
            parser.error(str(error))
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        emit(f"snapshotted {len(value)} source/build inputs: {out}")
        return 0
    if args.action == "snapshot-git":
        repo, out = args.git_repo, args.out
        if repo is None or args.rev is None or out is None:
            parser.error("snapshot-git requires --git-repo, --rev and --out")
        if (
            Path(repo).resolve() in out.resolve().parents
            or Path(repo).resolve() == out.resolve()
        ):
            parser.error("snapshot output must be outside the repository")
        try:
            value = snapshot_from_git(Path(repo), args.rev)
        except (OSError, ValueError, RuntimeError) as error:
            parser.error(str(error))
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        emit(f"snapshotted {len(value)} source/build inputs: {out}")
        return 0
    # validate-git
    if (
        args.git_repo is None
        or not args.baseline_rev
        or not args.candidate_rev
        or args.scope is None
    ):
        parser.error(
            "validate-git requires --git-repo, --baseline-rev, --candidate-rev and --scope"
        )
    if not args.target_soc:
        parser.error("validate-git requires at least one --target-soc")
    if args.out is None:
        parser.error("validate-git requires --out")
    try:
        scope = json.loads(args.scope.read_text(encoding="utf-8"))
        report = validate_source_isolation_git(
            scope,
            Path(args.git_repo),
            args.baseline_rev,
            args.candidate_rev,
            args.target_soc,
        )
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as error:
        emit(json.dumps({"status": "error", "error": str(error)}, ensure_ascii=False))
        return 2
    atomic_json(args.out.resolve(), report)
    emit(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["decision"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
