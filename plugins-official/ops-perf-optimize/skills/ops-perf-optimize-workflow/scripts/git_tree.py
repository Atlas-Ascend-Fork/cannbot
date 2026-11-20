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

"""Read-only source-tree views shared by the git-native validators.

A TreeSource is a uniform read-only view over either a directory checkout
(`DirectoryTree`) or a git commit (`GitTree`). Validators consume tree views so
the same semantic gates run on both backends. All git invocations pin
`core.autocrlf=false` and `core.eol=lf` so line coordinates and byte content
match the raw file bytes recorded in the repository.

Directory mode remains the parity oracle for git mode: tests materialize git
revisions through `git archive` and assert both modes agree on gate decisions.
"""

from __future__ import annotations

import difflib
import hashlib
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


GIT_CONFIG_ARGS = (
    "-c", "core.autocrlf=false",
    "-c", "core.eol=lf",
    "-c", "core.quotepath=false",
)
FILE_MODES = {"100644", "100755"}
SYMLINK_MODE = "120000"
GITLINK_MODE = "160000"
HUNK_PATTERN = re.compile(
    r"^@@ -(?P<old_start>\d+)(?:,(?P<old_count>\d+))?"
    r" \+(?P<new_start>\d+)(?:,(?P<new_count>\d+))? @@"
)


class GitError(RuntimeError):
    """Raised when a git invocation fails or returns unusable output."""


def run_git(repo: Path, *args: str) -> str:
    """Run git with pinned normalization config and return decoded stdout."""
    return run_git_bytes(repo, *args).decode("utf-8", "replace")


def run_git_bytes(repo: Path, *args: str) -> bytes:
    command = ("git", *GIT_CONFIG_ARGS, "-C", str(repo), *args)
    result = subprocess.run(command, capture_output=True)
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise GitError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout


def is_git_repo(root: Path) -> bool:
    if not root.is_dir():
        return False
    result = subprocess.run(
        ("git", *GIT_CONFIG_ARGS, "-C", str(root), "rev-parse", "--is-inside-work-tree"),
        capture_output=True,
    )
    return result.returncode == 0 and result.stdout.strip() == b"true"


def git_version_ok(minimum: tuple[int, int] = (2, 20)) -> tuple[bool, str]:
    result = subprocess.run(("git", "--version"), capture_output=True, text=True)
    if result.returncode != 0:
        return False, ""
    match = re.search(r"git version (\d+)\.(\d+)", result.stdout)
    if not match:
        return False, result.stdout.strip()
    version = (int(match.group(1)), int(match.group(2)))
    return version >= minimum, f"{version[0]}.{version[1]}"


def rev_resolve(repo: Path, rev: str) -> str:
    return run_git(repo, "rev-parse", "--verify", f"{rev}^{{commit}}").strip()


def tree_sha(repo: Path, rev: str) -> str:
    return run_git(repo, "rev-parse", "--verify", f"{rev}^{{tree}}").strip()


def git_ls_entries(repo: Path, rev: str) -> dict[str, str]:
    """List tracked entries at a revision: relative path -> git file mode."""
    output = run_git_bytes(repo, "ls-tree", "-r", "--full-name", "-z", rev)
    entries: dict[str, str] = {}
    for record in output.split(b"\0"):
        if not record:
            continue
        meta, _, raw_path = record.partition(b"\t")
        mode = meta.split(b" ")[0].decode("ascii", "replace")
        entries[raw_path.decode("utf-8", "replace")] = mode
    return entries


def git_show_bytes(repo: Path, rev: str, relative: str) -> bytes:
    return run_git_bytes(repo, "show", f"{rev}:{relative}")


def git_diff_name_status(repo: Path, old_rev: str, new_rev: str) -> dict[str, str]:
    """Changed paths between two revisions: path -> status (M/A/D/T/R...)."""
    output = run_git(repo, "diff", "--no-renames", "--name-status", old_rev, new_rev)
    changes: dict[str, str] = {}
    for line in output.splitlines():
        if not line.strip():
            continue
        status, _, path = line.partition("\t")
        if not path:
            continue
        changes[path.strip()] = status.strip()[0]
    return changes


@dataclass(frozen=True)
class Hunk:
    """One `git diff` hunk; counts of zero mean an empty range at that side."""

    old_start: int
    old_count: int
    new_start: int
    new_count: int


def git_diff_hunks(repo: Path, old_rev: str, new_rev: str, relative: str) -> list[Hunk] | None:
    """Hunks for one path; None signals a binary diff without line numbers."""
    output = run_git(repo, "diff", "-U0", "--no-renames", old_rev, new_rev, "--", relative)
    hunks: list[Hunk] = []
    for line in output.splitlines():
        match = HUNK_PATTERN.match(line)
        if match:
            hunks.append(Hunk(
                old_start=int(match.group("old_start")),
                old_count=int(match.group("old_count") or "1"),
                new_start=int(match.group("new_start")),
                new_count=int(match.group("new_count") or "1"),
            ))
    if hunks:
        return hunks
    if "Binary files " in output:
        return None
    return []


def hunks_to_old_opcodes(hunks: list[Hunk]) -> list[tuple[str, int, int]]:
    """Convert git hunks to difflib-style opcodes over the old-side line index.

    Insertions are (tag='insert', i1, i1); replacements and deletions use the
    0-based half-open old-side range, exactly like SequenceMatcher opcodes.
    """
    opcodes: list[tuple[str, int, int]] = []
    for hunk in hunks:
        if hunk.old_count == 0:
            opcodes.append(("insert", hunk.old_start, hunk.old_start))
        else:
            tag = "delete" if hunk.new_count == 0 else "replace"
            opcodes.append((tag, hunk.old_start - 1, hunk.old_start - 1 + hunk.old_count))
    return opcodes


def hunks_to_candidate_ranges(hunks: list[Hunk]) -> list[tuple[int, int]]:
    """Convert git hunks to 1-based inclusive candidate-side changed ranges."""
    ranges: list[tuple[int, int]] = []
    for hunk in hunks:
        if hunk.new_count == 0:
            # Git reports the line before the deletion point when the count is 0.
            start = hunk.new_start + 1
            ranges.append((start, start))
        else:
            ranges.append((hunk.new_start, hunk.new_start + hunk.new_count - 1))
    return ranges


def difflib_opcodes(old_bytes: bytes | None, new_bytes: bytes | None) -> list[tuple[str, int, int]]:
    if old_bytes is None or new_bytes is None:
        return []
    matcher = difflib.SequenceMatcher(
        a=old_bytes.splitlines(keepends=True), b=new_bytes.splitlines(keepends=True), autojunk=False,
    )
    return [
        (tag, i1, i2)
        for tag, i1, i2, _j1, _j2 in matcher.get_opcodes()
        if tag != "equal"
    ]


def difflib_candidate_ranges(old_bytes: bytes | None, new_bytes: bytes | None) -> list[tuple[int, int]]:
    if old_bytes is None or new_bytes is None:
        return []
    # Mirrors the legacy integration-safety hunk computation exactly.
    matcher = difflib.SequenceMatcher(
        a=old_bytes.splitlines(), b=new_bytes.splitlines(),
    )
    ranges: list[tuple[int, int]] = []
    for tag, _i1, _i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        start = max(1, j1 + 1)
        end = max(start, j2)
        ranges.append((start, end))
    return ranges


class TreeSource:
    """Read-only view over a source tree: directory checkout or git commit."""

    def __init__(self, kind: str, label: str) -> None:
        self.kind = kind
        self._label = label

    # -- entry inventory ---------------------------------------------------

    def entries(self, ignored_dirs: set[str]) -> dict[str, str]:
        """All files below the root, minus ignored directory names.

        Returns relative POSIX path -> entry kind ('file', 'symlink',
        'gitlink'); directories are never listed.
        """
        raise NotImplementedError

    # -- content access ----------------------------------------------------

    def read_bytes(self, relative: str) -> bytes | None:
        raise NotImplementedError

    def read_text(self, relative: str) -> str | None:
        content = self.read_bytes(relative)
        return None if content is None else content.decode("utf-8", "replace")

    def exists(self, relative: str) -> bool:
        return self.read_bytes(relative) is not None

    def line_count(self, relative: str) -> int | None:
        content = self.read_bytes(relative)
        return None if content is None else len(content.splitlines())

    # -- identity ----------------------------------------------------------

    def label(self) -> str:
        return self._label

    def identity(self) -> dict[str, str]:
        raise NotImplementedError


class DirectoryTree(TreeSource):
    """A plain directory checkout (the legacy validator input)."""

    def __init__(self, root: Path) -> None:
        super().__init__("directory", str(root.resolve()))
        self.root = root.resolve()

    def entries(self, ignored_dirs: set[str]) -> dict[str, str]:
        if not self.root.is_dir():
            raise GitError(f"source root is not a directory: {self.root}")

        def fail_on_walk_error(error: OSError) -> None:
            raise error

        result: dict[str, str] = {}
        for current, directories, files in os.walk(self.root, onerror=fail_on_walk_error):
            directories[:] = sorted(set(directories) - ignored_dirs)
            for name in sorted(files):
                path = Path(current) / name
                kind = "symlink" if path.is_symlink() else "file"
                result[path.relative_to(self.root).as_posix()] = kind
        return result

    def read_bytes(self, relative: str) -> bytes | None:
        path = self.root / relative
        if not path.is_file():
            return None
        return path.read_bytes()

    def identity(self) -> dict[str, str]:
        digest = hashlib.sha256()
        for relative in sorted(self.entries({"__unused__"})):
            content = self.read_bytes(relative)
            digest.update(relative.encode("utf-8"))
            digest.update(b"\0")
            digest.update(hashlib.sha256(content or b"").digest())
        return {"kind": "directory", "label": self.label(), "sha256": digest.hexdigest()}


class GitTree(TreeSource):
    """One commit of a git repository, read through git plumbing."""

    def __init__(self, repo: Path, rev: str) -> None:
        self.repo = repo.resolve()
        self.rev_expression = rev
        self.commit = rev_resolve(self.repo, rev)
        self._entries_cache: dict[str, str] | None = None
        self._blob_cache: dict[str, str] | None = None
        super().__init__("git", f"git:{self.repo}@{self.commit}")

    def entries(self, ignored_dirs: set[str]) -> dict[str, str]:
        if self._entries_cache is None:
            self._entries_cache = git_ls_entries(self.repo, self.commit)
        tracked = self._entries_cache
        result: dict[str, str] = {}
        for relative, mode in tracked.items():
            parts = Path(relative).parts
            if ignored_dirs.intersection(parts):
                continue
            if mode in FILE_MODES:
                kind = "file"
            elif mode == SYMLINK_MODE:
                kind = "symlink"
            elif mode == GITLINK_MODE:
                kind = "gitlink"
            else:
                kind = "file"
            result[relative] = kind
        return result

    def blob_shas(self) -> dict[str, str]:
        """Return cached blob IDs for tracked paths without reading file contents."""
        if self._blob_cache is None:
            output = run_git(self.repo, "ls-tree", "-r", "--full-name", self.commit)
            cache: dict[str, str] = {}
            for line in output.splitlines():
                meta, _, path = line.partition("\t")
                parts = meta.split()
                if len(parts) >= 3 and path:
                    cache[path] = parts[2]
            self._blob_cache = cache
        return self._blob_cache

    def read_bytes(self, relative: str) -> bytes | None:
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts:
            raise GitError(f"path escapes repository root: {relative}")
        if self._entries_cache is None:
            self._entries_cache = git_ls_entries(self.repo, self.commit)
        mode = self._entries_cache.get(relative)
        if mode is None or mode not in FILE_MODES:
            return None
        return git_show_bytes(self.repo, self.commit, relative)

    def identity(self) -> dict[str, str]:
        return {
            "kind": "git",
            "label": self.label(),
            "commit": self.commit,
            "tree": tree_sha(self.repo, self.commit),
        }


def as_tree(value: "TreeSource | Path") -> TreeSource:
    """Wrap a plain directory Path into a DirectoryTree view."""
    if isinstance(value, TreeSource):
        return value
    return DirectoryTree(Path(value))


def source_filtered(entries: dict[str, str], suffixes: set[str], build_names: set[str],
                    config_dirs: set[str]) -> dict[str, str]:
    """Apply the source-isolation suffix rules to a raw entry inventory."""
    result: dict[str, str] = {}
    for relative, kind in entries.items():
        path = Path(relative)
        config = (
            path.suffix.lower() in {".json", ".yaml", ".yml"}
            and config_dirs.intersection(path.parts)
        )
        if path.suffix.lower() not in suffixes and path.name not in build_names and not config:
            continue
        result[relative] = kind
    return result


def tree_snapshot(tree: TreeSource, suffixes: set[str], build_names: set[str],
                  config_dirs: set[str], ignored_dirs: set[str]) -> dict[str, str]:
    """Snapshot of source/build inputs: relative path -> sha256 of content."""
    entries = source_filtered(tree.entries(ignored_dirs), suffixes, build_names, config_dirs)
    snapshot: dict[str, str] = {}
    for relative, kind in entries.items():
        if kind != "file":
            raise GitError(f"source symlink/hardlink is not isolated: {relative}")
        snapshot[relative] = hashlib.sha256(tree.read_bytes(relative) or b"").hexdigest()
    return snapshot


def changed_files(baseline: TreeSource, candidate: TreeSource,
                  ignored_dirs: set[str]) -> list[str]:
    """Paths whose content differs between two trees of the same kind."""
    before = baseline.entries(ignored_dirs)
    after = candidate.entries(ignored_dirs)
    changed: list[str] = []
    for relative in sorted(set(before) | set(after)):
        if baseline.read_bytes(relative) != candidate.read_bytes(relative):
            changed.append(relative)
        elif before.get(relative) != after.get(relative):
            # Entry-kind changes (file <-> symlink/gitlink) are changes too.
            changed.append(relative)
    return changed


def old_side_opcodes(baseline: TreeSource, candidate: TreeSource,
                     relative: str) -> list[tuple[str, int, int]]:
    """Difflib-style old-side opcodes for one path.

    Binary diffs carry no line numbers in git output; both tree kinds then
    fall back to difflib over raw bytes so gate decisions stay identical.
    """
    old_bytes = baseline.read_bytes(relative)
    new_bytes = candidate.read_bytes(relative)
    if isinstance(baseline, GitTree) and isinstance(candidate, GitTree):
        hunks = git_diff_hunks(baseline.repo, baseline.commit, candidate.commit, relative)
        if hunks is None:
            return difflib_opcodes(old_bytes, new_bytes)
        return hunks_to_old_opcodes(hunks)
    return difflib_opcodes(old_bytes, new_bytes)


def candidate_ranges(baseline: TreeSource, candidate: TreeSource, relative: str) -> list[tuple[int, int]]:
    """1-based inclusive candidate-side changed ranges for one path."""
    old_bytes = baseline.read_bytes(relative)
    new_bytes = candidate.read_bytes(relative)
    if isinstance(baseline, GitTree) and isinstance(candidate, GitTree):
        hunks = git_diff_hunks(baseline.repo, baseline.commit, candidate.commit, relative)
        if hunks is None:
            return difflib_candidate_ranges(old_bytes, new_bytes)
        return hunks_to_candidate_ranges(hunks)
    return difflib_candidate_ranges(old_bytes, new_bytes)
