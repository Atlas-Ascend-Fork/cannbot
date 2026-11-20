# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Tests for the mechanical git workspace operations used by the run workflow."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "ops-perf-optimize-workflow"
    / "scripts"
    / "git_workspace.py"
)
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("git_workspace", SCRIPT)
assert SPEC and SPEC.loader
WORKSPACE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(WORKSPACE)


def write(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ("git", "-C", str(repo), *args), capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def commit_all(repo: Path, message: str) -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-m", message)
    return git(repo, "rev-parse", "HEAD").strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.name", "tester")
    git(root, "config", "user.email", "tester@example.com")
    write(root, "op_kernel/kernel.cpp", "int main() { return 0; }\n")
    write(root, "op_host/tiling.cpp", "void Tiling() {}\n")
    write(root, ".gitignore", "build/\nignored_src.cpp\n")
    commit_all(root, "baseline")
    return root


def run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True, timeout=60,
    )


def load(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_probe_reports_non_git_directory(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    out = tmp_path / "probe.json"
    result = run_cli("probe", "--code-dir", str(plain), "--out", str(out))
    assert result.returncode == 0, result.stderr
    report = load(out)
    assert report["is_git_repo"] is False


def test_probe_reports_dirty_untracked_and_ignored_sources(repo: Path, tmp_path: Path) -> None:
    write(repo, "op_kernel/kernel.cpp", "int main() { return 1; }\n")  # dirty tracked
    write(repo, "op_kernel/new_file.cpp", "void New() {}\n")           # untracked
    write(repo, "ignored_src.cpp", "void Ignored() {}\n")              # ignored source file
    out = tmp_path / "probe.json"
    result = run_cli("probe", "--code-dir", str(repo), "--out", str(out))
    assert result.returncode == 0, result.stderr
    report = load(out)
    assert report["is_git_repo"] is True
    assert "op_kernel/kernel.cpp" in report["dirty_files"]
    assert "op_kernel/new_file.cpp" in report["untracked_files"]
    assert "ignored_src.cpp" in report["ignored_source_files"]


def test_prepare_baseline_defaults_to_head_and_keeps_user_dirty_state(
    repo: Path, tmp_path: Path
) -> None:
    """Baseline anchors to the committed state; dirty changes stay in the user worktree."""
    dirty_content = "int main() { return 42; }\n"
    write(repo, "op_kernel/kernel.cpp", dirty_content)
    write(repo, "op_kernel/untracked.cpp", "void Extra() {}\n")
    head_before = git(repo, "rev-parse", "HEAD").strip()
    status_before = git(repo, "status", "--porcelain")
    out = tmp_path / "baseline.json"
    result = run_cli(
        "prepare-baseline", "--repo", str(repo),
        "--run-dir", str(tmp_path / "run"), "--out", str(out),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = load(out)
    # No --option: defaults to (b) HEAD baseline.
    assert report["option"] == "b"
    assert report["baseline_commit"] == head_before
    assert report["baseline_tree_sha"] == git(repo, "rev-parse", "HEAD^{tree}").strip()
    assert report["user_worktree_untouched"] is True
    assert git(repo, "rev-parse", "HEAD").strip() == head_before
    assert git(repo, "status", "--porcelain") == status_before
    assert (repo / "op_kernel/kernel.cpp").read_text() == dirty_content
    # The baseline tree never contains the dirty/untracked content.
    blob = subprocess.run(
        ("git", "-C", str(repo), "show", f"{head_before}:op_kernel/kernel.cpp"),
        capture_output=True, text=True,
    )
    assert blob.stdout != dirty_content


def test_init_creates_reversible_baseline_and_reports_ignored_sources(
    repo: Path, tmp_path: Path
) -> None:
    """Consented init preserves source files, freezes the first commit and reports ignored sources."""
    plain = tmp_path / "plain-code"
    (plain / "op_kernel").mkdir(parents=True)
    (plain / "op_kernel/kernel.cpp").write_text("void kernel() {}\n", encoding="utf-8")
    (plain / ".gitignore").write_text("generated/\n", encoding="utf-8")
    (plain / "generated").mkdir()
    (plain / "generated/gen.cpp").write_text("// ignored\n", encoding="utf-8")
    out = tmp_path / "init.json"
    result = run_cli(
        "init", "--code-dir", str(plain), "--out", str(out),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = load(out)
    assert report["inited_in_place"] is True
    assert report["user_files_touched"] is False
    head = subprocess.run(("git", "-C", str(plain), "rev-parse", "HEAD"),
                          capture_output=True, text=True).stdout.strip()
    assert report["baseline_commit"] == head
    # Source files are tracked; ignored source-suffix files are reported.
    tracked = subprocess.run(("git", "-C", str(plain), "ls-files"),
                             capture_output=True, text=True).stdout.split()
    assert "op_kernel/kernel.cpp" in tracked
    assert "generated/gen.cpp" not in tracked
    assert "generated/gen.cpp" in report["ignored_source_files"]
    # Running init again on an initialized dir is refused.
    again = run_cli("init", "--code-dir", str(plain), "--out", str(tmp_path / "init2.json"))
    assert again.returncode == 2


def test_prepare_baseline_option_b_warns_on_closure_intersection(repo: Path, tmp_path: Path) -> None:
    write(repo, "op_kernel/kernel.cpp", "int main() { return 7; }\n")
    write(repo, "notes.txt", "unrelated dirty file\n")
    closure = tmp_path / "closure.json"
    closure.write_text(json.dumps(["op_kernel/kernel.cpp", "op_host/tiling.cpp"]), encoding="utf-8")
    out = tmp_path / "baseline.json"
    result = run_cli(
        "prepare-baseline", "--repo", str(repo), "--option", "b",
        "--run-dir", str(tmp_path / "run"), "--closure-files", str(closure), "--out", str(out),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = load(out)
    assert report["baseline_commit"] == git(repo, "rev-parse", "HEAD").strip()
    assert report["closure_warning"] == ["op_kernel/kernel.cpp"]
    # Dirty state still present in the user worktree.
    assert (repo / "op_kernel/kernel.cpp").read_text() == "int main() { return 7; }\n"


def test_prepare_baseline_option_d_discards_with_audit_patch(repo: Path, tmp_path: Path) -> None:
    write(repo, "op_kernel/kernel.cpp", "int main() { return 9; }\n")
    write(repo, "op_kernel/untracked.cpp", "void Extra() {}\n")
    run_dir = tmp_path / "run"
    out = tmp_path / "baseline.json"
    result = run_cli(
        "prepare-baseline", "--repo", str(repo), "--option", "d",
        "--run-dir", str(run_dir), "--out", str(out),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = load(out)
    assert report["baseline_commit"] == git(repo, "rev-parse", "HEAD").strip()
    assert git(repo, "status", "--porcelain") == ""
    assert (repo / "op_kernel/kernel.cpp").read_text() == "int main() { return 0; }\n"
    assert Path(report["audit_patch"]).is_file()
    assert Path(report["untracked_backup_dir"], "op_kernel/untracked.cpp").is_file()
    assert not (repo / "op_kernel/untracked.cpp").exists()


def test_worktree_add_and_remove_roundtrip(repo: Path, tmp_path: Path) -> None:
    head = git(repo, "rev-parse", "HEAD").strip()
    worktree = tmp_path / "worktree"
    out = tmp_path / "worktree.json"
    result = run_cli(
        "worktree-add", "--repo", str(repo), "--branch", "perf-opt/test/work",
        "--from", head, "--path", str(worktree), "--out", str(out),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = load(out)
    assert report["head_commit"] == head
    assert report["verified_tree_sha"] == git(repo, "rev-parse", "HEAD^{tree}").strip()
    # Idempotent re-run on the same identity passes.
    result = run_cli(
        "worktree-add", "--repo", str(repo), "--branch", "perf-opt/test/work",
        "--from", head, "--path", str(worktree), "--out", str(out),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    # Dirty worktree refuses removal without --force.
    write(worktree, "op_kernel/kernel.cpp", "int main() { return 3; }\n")
    result = run_cli("worktree-remove", "--path", str(worktree), "--out", str(out))
    assert result.returncode == 2
    assert "uncommitted changes" in result.stdout
    result = run_cli("worktree-remove", "--path", str(worktree), "--force", "--out", str(out))
    assert result.returncode == 0, result.stdout + result.stderr
    assert not worktree.exists()


def test_discard_unexpected_keeps_allow_list_only(repo: Path, tmp_path: Path) -> None:
    head = git(repo, "rev-parse", "HEAD").strip()
    worktree = tmp_path / "worktree"
    run_cli("worktree-add", "--repo", str(repo), "--branch", "perf-opt/test/work",
            "--from", head, "--path", str(worktree), "--out", str(tmp_path / "wt.json"))
    write(worktree, "op_kernel/kernel.cpp", "int main() { return 5; }\n")     # allowed
    write(worktree, "op_host/tiling.cpp", "void Tiling() { changed; }\n")     # unexpected
    write(worktree, "op_kernel/rogue.cpp", "void Rogue() {}\n")               # unexpected untracked
    allow = tmp_path / "allow.json"
    allow.write_text(json.dumps(["op_kernel/kernel.cpp"]), encoding="utf-8")
    out = tmp_path / "discard.json"
    result = run_cli(
        "discard-unexpected", "--worktree", str(worktree),
        "--allow-list", str(allow), "--patch-out", str(tmp_path / "audit"), "--out", str(out),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = load(out)
    assert report["discarded_tracked"] == ["op_host/tiling.cpp"]
    assert report["discarded_untracked"] == ["op_kernel/rogue.cpp"]
    assert (worktree / "op_kernel/kernel.cpp").read_text() == "int main() { return 5; }\n"
    assert (worktree / "op_host/tiling.cpp").read_text() == "void Tiling() {}\n"
    assert not (worktree / "op_kernel/rogue.cpp").exists()
    assert Path(report["audit_patch"]).is_file()
    assert Path(report["untracked_backup_dir"], "op_kernel/rogue.cpp").is_file()
    assert git(worktree, "status", "--porcelain").splitlines() == [" M op_kernel/kernel.cpp"]


def default_branch(repo: Path) -> str:
    return git(repo, "symbolic-ref", "--short", "HEAD").strip()


def test_merge_check_fast_forward_evidence(repo: Path, tmp_path: Path) -> None:
    base = git(repo, "rev-parse", "HEAD").strip()
    write(repo, "op_kernel/kernel.cpp", "int main() { return 1; }\n")
    candidate = commit_all(repo, "optimized")
    smoke = tmp_path / "smoke.json"
    smoke.write_text(json.dumps({"result": "PASS"}), encoding="utf-8")
    accepted = tmp_path / "accepted.so"
    accepted.write_bytes(b"same")
    rebuilt = tmp_path / "rebuilt.so"
    rebuilt.write_bytes(b"same")
    out = tmp_path / "merge.json"
    result = run_cli(
        "merge-check", "--repo", str(repo), "--candidate-rev", candidate,
        "--target-branch", default_branch(repo), "--baseline-rev", base,
        "--smoke-report", str(smoke),
        "--rebuild-artifact", str(rebuilt), "--accepted-artifact", str(accepted),
        "--out", str(out),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = load(out)
    assert report["decision"] == "fast_forward"
    assert report["tree_identity"]["equal"] is True
    assert report["blob_identity"]["files_checked"] == 1
    assert report["blob_identity"]["mismatches"] == []
    assert report["missing_evidence"] == []
    assert report["evidence_reuse_eligible"] is True


def test_merge_check_ff_without_evidence_is_not_reusable(repo: Path, tmp_path: Path) -> None:
    """Reusing fast-forward evidence requires both regression and rebuild receipts."""
    base = git(repo, "rev-parse", "HEAD").strip()
    write(repo, "op_kernel/kernel.cpp", "int main() { return 1; }\n")
    candidate = commit_all(repo, "optimized")
    out = tmp_path / "merge.json"
    result = run_cli(
        "merge-check", "--repo", str(repo), "--candidate-rev", candidate,
        "--target-branch", default_branch(repo), "--baseline-rev", base, "--out", str(out),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = load(out)
    assert report["decision"] == "fast_forward"
    assert report["evidence_reuse_eligible"] is False
    assert set(report["missing_evidence"]) == {
        "smoke-report (regression verification)",
        "rebuild-artifact/accepted-artifact (build reproducibility)",
    }


def test_merge_check_rejects_forged_merged_rev(repo: Path, tmp_path: Path) -> None:
    """Regression: --merged-rev must match the actual target branch head."""
    base = git(repo, "rev-parse", "HEAD").strip()
    write(repo, "op_kernel/kernel.cpp", "int main() { return 1; }\n")
    candidate = commit_all(repo, "optimized")
    out = tmp_path / "merge.json"
    result = run_cli(
        "merge-check", "--repo", str(repo), "--candidate-rev", candidate,
        "--target-branch", default_branch(repo), "--baseline-rev", base,
        "--merged-rev", base, "--out", str(out),
    )
    assert result.returncode == 2
    assert "does not match the current target branch head" in result.stdout


def test_merge_check_non_ff_forces_full_reverification(repo: Path, tmp_path: Path) -> None:
    branch = default_branch(repo)
    write(repo, "op_host/tiling.cpp", "void Tiling() { concurrent; }\n")
    commit_all(repo, "concurrent user change")
    user_head = git(repo, "rev-parse", "HEAD").strip()
    git(repo, "checkout", "-q", "-b", "perf-opt/work", user_head)
    write(repo, "op_kernel/kernel.cpp", "int main() { return 1; }\n")
    candidate = commit_all(repo, "optimized")
    git(repo, "checkout", "-q", branch)
    git(repo, "merge", "--no-ff", "-m", "merge optimized", candidate)
    out = tmp_path / "merge.json"
    result = run_cli(
        "merge-check", "--repo", str(repo), "--candidate-rev", candidate,
        "--target-branch", branch, "--out", str(out),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = load(out)
    assert report["decision"] == "merge"
    assert report["evidence_reuse_eligible"] is False
    assert report["evidence_reuse"] == []


def test_merge_check_fast_forward_requires_explicit_baseline(repo: Path, tmp_path: Path) -> None:
    write(repo, "op_kernel/kernel.cpp", "int main() { return 1; }\n")
    candidate = commit_all(repo, "optimized")
    out = tmp_path / "merge.json"
    result = run_cli(
        "merge-check", "--repo", str(repo), "--candidate-rev", candidate,
        "--target-branch", default_branch(repo), "--out", str(out),
    )
    # Without --baseline-rev the blob check would compare the candidate against
    # itself (merge-base degenerates after a fast-forward merge): refuse.
    assert result.returncode == 2
    assert "requires --baseline-rev" in result.stdout


def test_merge_check_smoke_failure_disqualifies_reuse(repo: Path, tmp_path: Path) -> None:
    base = git(repo, "rev-parse", "HEAD").strip()
    write(repo, "op_kernel/kernel.cpp", "int main() { return 1; }\n")
    candidate = commit_all(repo, "optimized")
    failing = tmp_path / "smoke-fail.json"
    failing.write_text(json.dumps({"status": "fail", "failed": 40}), encoding="utf-8")
    out = tmp_path / "merge.json"
    result = run_cli(
        "merge-check", "--repo", str(repo), "--candidate-rev", candidate,
        "--target-branch", default_branch(repo), "--baseline-rev", base,
        "--smoke-report", str(failing), "--out", str(out),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = load(out)
    assert report["decision"] == "fast_forward"
    assert report["smoke"]["pass"] is False
    assert report["evidence_reuse_eligible"] is False


def test_merge_check_smoke_must_be_a_json_pass_object(repo: Path, tmp_path: Path) -> None:
    base = git(repo, "rev-parse", "HEAD").strip()
    write(repo, "op_kernel/kernel.cpp", "int main() { return 1; }\n")
    candidate = commit_all(repo, "optimized")
    plain = tmp_path / "smoke.txt"
    plain.write_text("all cases passed (prose)", encoding="utf-8")
    out = tmp_path / "merge.json"
    result = run_cli(
        "merge-check", "--repo", str(repo), "--candidate-rev", candidate,
        "--target-branch", default_branch(repo), "--baseline-rev", base,
        "--smoke-report", str(plain), "--out", str(out),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = load(out)
    assert report["smoke"]["pass"] is False
    assert "not a JSON object" in report["smoke"]["reason"]
    assert report["evidence_reuse_eligible"] is False


def test_merge_check_rebuild_artifact_mismatch_disqualifies_reuse(repo: Path, tmp_path: Path) -> None:
    base = git(repo, "rev-parse", "HEAD").strip()
    write(repo, "op_kernel/kernel.cpp", "int main() { return 1; }\n")
    candidate = commit_all(repo, "optimized")
    accepted = tmp_path / "accepted.so"
    accepted.write_bytes(b"accepted-bytes")
    rebuilt = tmp_path / "rebuilt.so"
    rebuilt.write_bytes(b"different-bytes")
    out = tmp_path / "merge.json"
    result = run_cli(
        "merge-check", "--repo", str(repo), "--candidate-rev", candidate,
        "--target-branch", default_branch(repo), "--baseline-rev", base,
        "--rebuild-artifact", str(rebuilt), "--accepted-artifact", str(accepted),
        "--out", str(out),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = load(out)
    assert report["decision"] == "fast_forward"
    assert report["rebuild"]["matches_accepted"] is False
    assert report["evidence_reuse_eligible"] is False


def test_worktree_add_excludes_build_artifacts_from_status(repo: Path, tmp_path: Path) -> None:
    """Build products must stay out of attempt commits and the delivered diff."""
    base = git(repo, "rev-parse", "HEAD").strip()
    out = tmp_path / "wt.json"
    result = run_cli(
        "worktree-add", "--repo", str(repo), "--branch", "perf-opt/ex/work",
        "--from", base, "--path", str(tmp_path / "wt"), "--out", str(out),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    wt = tmp_path / "wt"
    # Fresh artifacts appear after the build step.
    (wt / "libop.so").write_bytes(b"build product")
    (wt / "kernel_meta").mkdir()
    (wt / "kernel_meta/meta.json").write_text("{}", encoding="utf-8")
    status = git(wt, "status", "--porcelain")
    assert "libop.so" not in status and "kernel_meta" not in status
    # `git add -A` keeps them out of the index and of any attempt commit.
    git(wt, "add", "-A")
    staged = git(wt, "diff", "--cached", "--name-only")
    assert "libop.so" not in staged and "kernel_meta/meta.json" not in staged
    # The user's own worktree / main repository excludes are untouched.
    main_exclude = Path(git(repo, "rev-parse", "--path-format=absolute", "--git-dir").strip()) / "info" / "exclude"
    assert not main_exclude.exists() or "ops-perf-optimize" not in main_exclude.read_text(encoding="utf-8")
