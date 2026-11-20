# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Parity tests: git-mode source isolation must agree with the directory oracle.

Each case builds a real git repository, materializes both revisions through
`git archive`, then asserts the directory-mode gate (legacy oracle) and the
git-mode gate (schema v2 scope) produce the same decision and the same
per-file failure categories. Registered divergences are limited to hunk
boundary message shapes inside one file, never the decision.
"""

from __future__ import annotations

import importlib.util
import io
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "ops-perf-optimize-workflow"
    / "scripts"
    / "validate_source_isolation.py"
)
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("source_isolation", SCRIPT)
assert SPEC and SPEC.loader
ISOLATION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ISOLATION)

from git_tree import tree_sha  # noqa: E402

TARGETS = ["Ascend950"]
GIT_CONFIG = ("-c", "core.autocrlf=false", "-c", "core.eol=lf", "-c", "user.name=tester",
              "-c", "user.email=tester@example.com")


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ("git", *GIT_CONFIG, "-C", str(repo), *args), capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def write(repo: Path, relative: str, content: bytes | str) -> None:
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))


def commit_all(repo: Path, message: str) -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "--allow-empty", "-m", message)
    return git(repo, "rev-parse", "HEAD").strip()


def materialize(repo: Path, rev: str, target: Path) -> Path:
    """Export one revision as a plain directory tree for the legacy oracle."""
    archive = target.parent / f"{target.name}.tar"
    subprocess.run(
        ("git", *GIT_CONFIG, "-C", str(repo), "archive", "--format=tar", "-o", str(archive), rev),
        check=True, capture_output=True,
    )
    target.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive) as bundle:
        bundle.extractall(target)
    archive.unlink()
    return target


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    write(root, "op_kernel/shared.h", "template<class T> void Legacy(T x) { Compute(x); }\n")
    write(root, "common/params.h", "constexpr int kTile = 128;\n")
    write(root, "op_kernel/entry.cpp", "void Run() {\n  Legacy(x);\n}\n")
    write(root, "op_kernel/uninvolved.h", "void OtherShape() { Legacy(y); }\n")
    write(root, "op_host/config/ascend910b/op.json", '{"source": "shared.h"}\n')
    write(root, "CMakeLists.txt", "add_subdirectory(op_kernel)\n")
    write(root, "README.md", "notes only, not a source input\n")
    write(root, "op_kernel/crlf.cpp", b"void A() {\r\n  Legacy(x);\r\n}\r\n")
    write(root, "op_kernel/blob.cpp", bytes(range(256)))
    commit_all(root, "baseline")
    return root


def failure_categories(report: dict) -> set[tuple[str, str]]:
    categories = set()
    for message in report["failures"]:
        if message.startswith("edit outside frozen scope: "):
            relative = message.split(":", 2)[1].strip()
            categories.add((relative, "edit"))
        elif message.startswith("undeclared new source/build file: "):
            categories.add((message.split(": ", 1)[1], "new"))
        elif message.startswith("baseline source/build file deleted: "):
            categories.add((message.split(": ", 1)[1], "deleted"))
        elif message.startswith("declared new source/build file missing: "):
            categories.add((message.split(": ", 1)[1], "missing"))
        else:
            categories.add((message, "other"))
    return categories


def parity(repo: Path, ranges: dict, additions: dict) -> tuple[dict, dict]:
    """Run the directory oracle and the git gate on the same pair of revisions."""
    baseline_rev = git(repo, "rev-list", "--max-parents=0", "HEAD").strip()
    candidate_rev = git(repo, "rev-parse", "HEAD").strip()
    baseline_dir = materialize(repo, baseline_rev, repo.parent / "oracle-baseline")
    candidate_dir = materialize(repo, candidate_rev, repo.parent / "oracle-candidate")
    v1_scope = {
        "schema_version": 1,
        "target_socs": TARGETS,
        "baseline_files": ISOLATION.snapshot(baseline_dir),
        "editable_ranges": ranges,
        "new_files": additions,
    }
    v2_scope = {
        "schema_version": 2,
        "target_socs": TARGETS,
        "baseline_commit": baseline_rev,
        "baseline_tree_sha": tree_sha(repo, baseline_rev),
        "editable_ranges": ranges,
        "new_files": additions,
    }
    directory = ISOLATION.validate_source_isolation(v1_scope, baseline_dir, candidate_dir, TARGETS)
    git_report = ISOLATION.validate_source_isolation_git(
        v2_scope, repo, baseline_rev, candidate_rev, TARGETS,
    )
    assert git_report["decision"] == directory["decision"]
    assert failure_categories(git_report) == failure_categories(directory)
    assert git_report["changed_files"] == directory["changed_files"]
    return git_report, directory


ENTRY_RANGE = {"op_kernel/entry.cpp": [{
    "start": 2, "end": 2, "kind": "routing", "reason": "target dispatch only",
}]}


def test_in_scope_edit_passes_in_both_modes(repo: Path) -> None:
    write(repo, "op_kernel/entry.cpp", "void Run() {\n  Legacy(x); /* routed */\n}\n")
    commit_all(repo, "in-scope edit")
    git_report, _ = parity(repo, ENTRY_RANGE, {})
    assert git_report["decision"] == "pass"


def test_out_of_scope_edit_fails_in_both_modes(repo: Path) -> None:
    write(repo, "op_kernel/shared.h", "template<class T> void Legacy(T x) { Optimized(x); }\n")
    commit_all(repo, "out-of-scope edit")
    git_report, _ = parity(repo, ENTRY_RANGE, {})
    assert git_report["decision"] == "fail"
    assert ("op_kernel/shared.h", "edit") in failure_categories(git_report)


def test_shared_helper_without_range_is_protected_in_both_modes(repo: Path) -> None:
    write(repo, "common/params.h", "constexpr int kTile = 256;\n")
    commit_all(repo, "helper edit")
    git_report, _ = parity(repo, ENTRY_RANGE, {})
    assert ("common/params.h", "edit") in failure_categories(git_report)


@pytest.mark.parametrize("insert_at,expected", [(1, "pass"), (2, "pass"), (3, "fail")])
def test_insertion_boundaries_agree_with_oracle(repo: Path, insert_at: int, expected: str) -> None:
    lines = ["void Run() {", "  Legacy(x);", "}"]
    lines.insert(insert_at, "  DispatchTarget();")
    write(repo, "op_kernel/entry.cpp", "\n".join(lines) + "\n")
    commit_all(repo, f"insert at position {insert_at}")
    git_report, _ = parity(repo, ENTRY_RANGE, {})
    assert git_report["decision"] == expected


def test_insertion_before_range_fails_like_oracle(repo: Path) -> None:
    write(repo, "op_kernel/entry.cpp", "void Run() {\n  Pre();\n  Legacy(x);\n}\n")
    commit_all(repo, "insert before range")
    git_report, _ = parity(repo, ENTRY_RANGE, {})
    # Insertion after old line 1 sits inside [start-1, end] == [1, 2]; the
    # legacy oracle accepts it, so git mode must accept it too.
    assert git_report["decision"] == "pass"


def test_undeclared_new_file_fails_in_both_modes(repo: Path) -> None:
    write(repo, "op_kernel/optimized.h", "void Optimized();\n")
    commit_all(repo, "undeclared new file")
    git_report, _ = parity(repo, ENTRY_RANGE, {})
    assert ("op_kernel/optimized.h", "new") in failure_categories(git_report)


def test_declared_new_file_passes_in_both_modes(repo: Path) -> None:
    write(repo, "op_kernel/arch35/optimized.h", "void Optimized();\n")
    commit_all(repo, "declared new file")
    git_report, _ = parity(repo, ENTRY_RANGE, {
        "op_kernel/arch35/optimized.h": {"copied_from": "op_kernel/shared.h"},
    })
    assert git_report["decision"] == "pass"


def test_declared_new_file_missing_fails_in_both_modes(repo: Path) -> None:
    commit_all(repo, "no actual change")
    git_report, _ = parity(repo, ENTRY_RANGE, {
        "op_kernel/arch35/optimized.h": {"copied_from": "op_kernel/shared.h"},
    })
    assert ("op_kernel/arch35/optimized.h", "missing") in failure_categories(git_report)


def test_baseline_deletion_fails_in_both_modes(repo: Path) -> None:
    (repo / "op_kernel/uninvolved.h").unlink()
    commit_all(repo, "delete baseline file")
    git_report, _ = parity(repo, ENTRY_RANGE, {})
    assert ("op_kernel/uninvolved.h", "deleted") in failure_categories(git_report)


def test_non_source_changes_are_ignored_in_both_modes(repo: Path) -> None:
    write(repo, "README.md", "notes changed, still not a source input\n")
    commit_all(repo, "doc change")
    git_report, _ = parity(repo, ENTRY_RANGE, {})
    assert git_report["decision"] == "pass"
    assert git_report["changed_files"] == []


def test_renamed_file_is_delete_plus_undeclared_new(repo: Path) -> None:
    (repo / "op_kernel/uninvolved.h").unlink()
    write(repo, "op_kernel/renamed.h", "void OtherShape() { Legacy(y); }\n")
    commit_all(repo, "rename without --find-renames")
    git_report, _ = parity(repo, ENTRY_RANGE, {})
    categories = failure_categories(git_report)
    assert ("op_kernel/renamed.h", "new") in categories
    assert ("op_kernel/uninvolved.h", "deleted") in categories


def test_crlf_file_edits_follow_line_coordinates(repo: Path) -> None:
    write(repo, "op_kernel/crlf.cpp", b"void A() {\r\n  Legacy(x); /* ok */\r\n}\r\n")
    commit_all(repo, "edit crlf line 2")
    ranges = dict(ENTRY_RANGE)
    ranges["op_kernel/crlf.cpp"] = [{
        "start": 2, "end": 2, "kind": "routing", "reason": "crlf line edit",
    }]
    git_report, _ = parity(repo, ranges, {})
    assert git_report["decision"] == "pass"


@pytest.mark.parametrize("cover_all", [True, False])
def test_binary_change_parity_with_oracle(repo: Path, cover_all: bool) -> None:
    write(repo, "op_kernel/blob.cpp", bytes(range(255)) + b"\x01")
    commit_all(repo, "binary edit")
    baseline_content = bytes(range(256))
    total_lines = len(baseline_content.splitlines())
    ranges = dict(ENTRY_RANGE)
    ranges["op_kernel/blob.cpp"] = [{
        "start": 1,
        "end": total_lines if cover_all else total_lines - 1,
        "kind": "target_private",
        "reason": "whole binary",
    }]
    git_report, _ = parity(repo, ranges, {})
    # Binary content has no git line hunks; difflib over raw bytes decides.
    assert git_report["decision"] == ("pass" if cover_all else "fail")


def test_multi_line_replacement_beyond_range_fails(repo: Path) -> None:
    # Replaces old lines 2-3 ("  Legacy(x);" and "}") with two new lines.
    write(repo, "op_kernel/entry.cpp", "void Run() {\n  A();\n  B();\n")
    commit_all(repo, "multi-line replace")
    git_report, _ = parity(repo, ENTRY_RANGE, {})
    assert ("op_kernel/entry.cpp", "edit") in failure_categories(git_report)


def test_git_scope_requires_matching_baseline_commit(repo: Path) -> None:
    commit_all(repo, "candidate")
    baseline_rev = git(repo, "rev-list", "--max-parents=0", "HEAD").strip()
    candidate_rev = git(repo, "rev-parse", "HEAD").strip()
    scope = {
        "schema_version": 2, "target_socs": TARGETS,
        "baseline_commit": "0" * 40, "editable_ranges": {}, "new_files": {},
    }
    with pytest.raises(ValueError, match="baseline_commit"):
        ISOLATION.validate_source_isolation_git(scope, repo, baseline_rev, candidate_rev, TARGETS)


def test_git_scope_rejects_stale_tree_sha(repo: Path) -> None:
    commit_all(repo, "candidate")
    baseline_rev = git(repo, "rev-list", "--max-parents=0", "HEAD").strip()
    candidate_rev = git(repo, "rev-parse", "HEAD").strip()
    scope = {
        "schema_version": 2, "target_socs": TARGETS,
        "baseline_commit": baseline_rev, "baseline_tree_sha": "1" * 40,
        "editable_ranges": {}, "new_files": {},
    }
    with pytest.raises(ValueError, match="baseline_tree_sha"):
        ISOLATION.validate_source_isolation_git(scope, repo, baseline_rev, candidate_rev, TARGETS)


def test_git_scope_rejects_v1_schema(repo: Path) -> None:
    commit_all(repo, "candidate")
    baseline_rev = git(repo, "rev-list", "--max-parents=0", "HEAD").strip()
    candidate_rev = git(repo, "rev-parse", "HEAD").strip()
    with pytest.raises(ValueError, match="schema_version"):
        ISOLATION.validate_source_isolation_git(
            {"schema_version": 1, "target_socs": TARGETS, "baseline_files": {}},
            repo, baseline_rev, candidate_rev, TARGETS,
        )


def test_snapshot_from_git_matches_directory_snapshot(repo: Path) -> None:
    baseline_rev = git(repo, "rev-list", "--max-parents=0", "HEAD").strip()
    materialized = materialize(repo, baseline_rev, repo.parent / "snapshot-dir")
    assert ISOLATION.snapshot_from_git(repo, baseline_rev) == ISOLATION.snapshot(materialized)


def test_validate_git_cli_reports_decision(repo: Path, tmp_path: Path) -> None:
    write(repo, "op_kernel/shared.h", "template<class T> void Legacy(T x) { Optimized(x); }\n")
    commit_all(repo, "out-of-scope edit")
    baseline_rev = git(repo, "rev-list", "--max-parents=0", "HEAD").strip()
    candidate_rev = git(repo, "rev-parse", "HEAD").strip()
    scope_path = tmp_path / "scope.json"
    scope_path.write_text(
        '{"schema_version": 2, "target_socs": ["Ascend950"], '
        f'"baseline_commit": "{baseline_rev}", "editable_ranges": {{}}, "new_files": {{}}}}',
        encoding="utf-8",
    )
    out = tmp_path / "gate.json"
    result = subprocess.run(
        (sys.executable, str(SCRIPT), "validate-git", "--git-repo", str(repo),
         "--baseline-rev", baseline_rev, "--candidate-rev", candidate_rev,
         "--scope", str(scope_path), "--target-soc", "Ascend950", "--out", str(out)),
        capture_output=True, text=True,
    )
    assert result.returncode == 1, result.stderr
    import json
    report = json.loads(out.read_text())
    assert report["decision"] == "fail"
    assert any("edit outside frozen scope" in message for message in report["failures"])
