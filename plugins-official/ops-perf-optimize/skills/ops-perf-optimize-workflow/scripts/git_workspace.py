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

"""Mechanical git workspace operations for the git-native optimization workflow.

Every subcommand only performs the mechanical operation it names; semantic
judgement (scopes, gates, routing) stays in the validators and the orchestrating
agents. All git invocations pin core.autocrlf=false so content and line
coordinates always match raw repository bytes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

from cli_output import atomic_json, emit
from git_tree import (
    GIT_CONFIG_ARGS,
    GitError,
    is_git_repo,
    git_version_ok,
    rev_resolve,
    run_git,
    run_git_bytes,
    tree_sha,
)

CODE_SUFFIXES = {".c", ".cc", ".cpp", ".h", ".hh", ".hpp", ".cce", ".asc", ".py",
                 ".sh", ".cmake", ".ini", ".tpp", ".inl", ".inc"}


class WorkspaceError(ValueError):
    """Raised for invalid workspace requests or unusable git state."""


def repo_or_error(root: Path) -> Path:
    root = root.resolve()
    if not is_git_repo(root):
        raise WorkspaceError(f"not a git repository: {root}")
    return root


def git(repo: Path, *args: str) -> str:
    try:
        return run_git(repo, *args)
    except GitError as error:
        raise WorkspaceError(str(error)) from error


def git_bytes(repo: Path, *args: str) -> bytes:
    try:
        return run_git_bytes(repo, *args)
    except GitError as error:
        raise WorkspaceError(str(error)) from error


def write_json(out: Path, value: dict) -> None:
    atomic_json(Path(out).resolve(), value)
    emit(json.dumps(value, ensure_ascii=False, sort_keys=True))


def status_entries(repo: Path) -> list[dict[str, str]]:
    """Parse `git status --porcelain` into {xy, path, orig_path?} records."""
    entries = []
    for line in git(repo, "status", "--porcelain").splitlines():
        if not line.strip():
            continue
        xy, _, rest = line[:2], line[2:3], line[3:]
        if " -> " in rest:
            orig, _, path = rest.partition(" -> ")
        else:
            orig, path = "", rest
        entries.append({"xy": xy.strip(), "path": path.strip(), "orig_path": orig.strip()})
    return entries


def dirty_files(repo: Path) -> list[str]:
    return sorted({entry["path"] for entry in status_entries(repo)})


def untracked_files(repo: Path) -> list[str]:
    return sorted(
        line for line in git(repo, "ls-files", "--others", "--exclude-standard").splitlines()
        if line.strip()
    )


def ignored_source_files(repo: Path) -> list[str]:
    """Source-suffixed files present on disk but excluded from git tracking."""
    others = set(
        line for line in git(repo, "ls-files", "--others", "--ignored", "--exclude-standard").splitlines()
        if line.strip()
    )
    return sorted(path for path in others if Path(path).suffix.lower() in CODE_SUFFIXES)


# -----------------------------------------------------------------------------------------------------------
# probe


def cmd_probe(args: argparse.Namespace) -> int:
    code_dir = Path(args.code_dir).resolve()
    version_ok, version = git_version_ok()
    if not is_git_repo(code_dir):
        write_json(args.out, {
            "code_dir": str(code_dir),
            "is_git_repo": False,
            "git_version_ok": version_ok,
            "git_version": version,
            "dirty_files": [],
            "untracked_files": [],
            "ignored_source_files": [],
            "build_entry_hints": [],
        })
        return 0
    hints = sorted(
        name for name in ("build.sh", "CMakeLists.txt", "Makefile", "README.md", "README")
        if (code_dir / name).exists()
    )
    write_json(args.out, {
        "code_dir": str(code_dir),
        "is_git_repo": True,
        "git_version_ok": version_ok,
        "git_version": version,
        "head_commit": rev_resolve(code_dir, "HEAD"),
        "dirty_files": dirty_files(code_dir),
        "untracked_files": untracked_files(code_dir),
        "ignored_source_files": ignored_source_files(code_dir),
        "build_entry_hints": hints,
    })
    return 0


# -----------------------------------------------------------------------------------------------------------
# Initialize the repository after the caller confirms GIT_INIT.


def cmd_init(args: argparse.Namespace) -> int:
    code_dir = Path(args.code_dir).resolve()
    if (code_dir / ".git").exists():
        raise WorkspaceError(f"already a git repository: {code_dir}")
    if not code_dir.is_dir():
        raise WorkspaceError(f"code dir not found: {code_dir}")
    # GIT_INIT consent is recorded in the request; this command only performs
    # the mechanical, reversible in-place init (adds .git, never touches files).
    git(code_dir, "init", "-b", "master")
    # Repo-local identity only; global git config is never touched.
    git(code_dir, "config", "user.name", "ops-perf-optimize")
    git(code_dir, "config", "user.email", "ops-perf-optimize@workflow")
    git(code_dir, "add", "-A")
    git(code_dir, "commit", "-m", "perf-opt: initial baseline (in-place git init)")
    head = rev_resolve(code_dir, "HEAD")
    write_json(args.out, {
        "inited_in_place": True,
        "baseline_commit": head,
        "baseline_tree_sha": tree_sha(code_dir, head),
        "ignored_source_files": ignored_source_files(code_dir),
        "local_identity_configured": True,
        "user_files_touched": False,
    })
    return 0


# -----------------------------------------------------------------------------------------------------------
# prepare-baseline


def _save_patch(repo: Path, out_dir: Path) -> Path:
    patch = out_dir / "dirty-state.patch"
    patch.parent.mkdir(parents=True, exist_ok=True)
    patch.write_bytes(git_bytes(repo, "diff", "--binary", "HEAD"))
    return patch


def _copy_untracked(repo: Path, out_dir: Path) -> Path:
    backup = out_dir / "dirty-untracked"
    for relative in untracked_files(repo):
        source = repo / relative
        target = backup / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return backup


def cmd_prepare_baseline(args: argparse.Namespace) -> int:
    repo = repo_or_error(Path(args.repo))
    run_dir = Path(args.run_dir).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    dirty = dirty_files(repo)
    head = rev_resolve(repo, "HEAD")
    # Snapshot commits need an identity; configure a repo-local one when absent.
    if not git(repo, "config", "--get", "user.email").strip():
        git(repo, "config", "user.name", "ops-perf-optimize")
        git(repo, "config", "user.email", "ops-perf-optimize@workflow")

    if args.option == "b":
        closure: list[str] = []
        if args.closure_files:
            closure_path = Path(args.closure_files).resolve()
            try:
                loaded = json.loads(closure_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise WorkspaceError(f"cannot read closure files: {error}") from error
            if not isinstance(loaded, list) or not all(isinstance(item, str) for item in loaded):
                raise WorkspaceError("closure files must be a JSON array of paths")
            closure = loaded
        warning = sorted(set(dirty) & set(closure))
        write_json(args.out, {
            "option": "b", "baseline_commit": head, "baseline_tree_sha": tree_sha(repo, head),
            "dirty_files": dirty, "closure_warning": warning,
            "user_worktree_untouched": True,
        })
        return 0

    if args.option == "d":
        patch = _save_patch(repo, run_dir)
        backup = _copy_untracked(repo, run_dir)
        # Discard only after the audit patch and the untracked backup are both
        # complete on disk; a destroyed backup would break the recovery promise.
        if not patch.is_file():
            raise WorkspaceError(f"audit patch was not written: {patch}")
        if backup.is_dir() and not any(backup.iterdir()):
            raise WorkspaceError(f"untracked backup is empty: {backup}")
        untracked = untracked_files(repo)
        if dirty:
            git(repo, "restore", ".")
        if untracked:
            # The run directory may legitimately live inside the repository;
            # exclude it from the clean so the just-written backups survive.
            clean_args = ["clean", "-fd"]
            try:
                clean_args += ["-e", str(run_dir.relative_to(repo))]
            except ValueError:
                pass  # run directory outside the repository: nothing to exclude
            git(repo, *clean_args)
            if not patch.is_file():
                raise WorkspaceError(
                    f"audit patch was destroyed by the discard: {patch}; "
                    "the backup location must stay outside the clean scope"
                )
        write_json(args.out, {
            "option": "d", "baseline_commit": head, "baseline_tree_sha": tree_sha(repo, head),
            "discarded_tracked": sorted(set(dirty) - set(untracked)),
            "discarded_untracked": untracked,
            "audit_patch": str(patch),
            "untracked_backup_dir": str(backup),
            "user_worktree_untouched": False,
        })
        return 0

    raise WorkspaceError(f"unknown baseline option: {args.option}")


# -----------------------------------------------------------------------------------------------------------
# worktree add/remove


def cmd_worktree_add(args: argparse.Namespace) -> int:
    repo = repo_or_error(Path(args.repo))
    path = Path(args.path).resolve()
    from_rev = rev_resolve(repo, args.from_rev)
    branch = args.branch
    existing = git(repo, "worktree", "list", "--porcelain")
    registered = {line.split(" ", 1)[1].strip() for line in existing.splitlines()
                  if line.startswith("worktree ")}
    if str(path) in registered:
        current_branch = git(path, "rev-parse", "--abbrev-ref", "HEAD").strip()
        head = rev_resolve(path, "HEAD")
        if current_branch != branch or head != from_rev:
            raise WorkspaceError(
                f"worktree already exists with different identity: {path} ({current_branch}@{head[:12]})"
            )
    else:
        git(repo, "worktree", "add", "-b", branch, str(path), from_rev)
    _ensure_artifact_excludes(path)
    head = rev_resolve(path, "HEAD")
    verified = tree_sha(path, "HEAD")
    expected = tree_sha(repo, from_rev)
    if verified != expected:
        raise WorkspaceError(f"worktree tree hash mismatch: {verified} != {expected}")
    write_json(args.out, {
        "path": str(path), "branch": branch, "created_from": from_rev,
        "head_commit": head, "verified_tree_sha": verified,
    })
    return 0


# Build products must never ride `git add -A` into attempt commits. Git reads
# excludes for every worktree from the COMMON info/exclude, which would also
# hide products in the user's own worktree; instead the run worktree gets a
# private `core.excludesFile` (per-worktree config) that points at a file beside
# the worktree in the run directory. Tracked files are unaffected (exclude is
# untracked-only), the user's git status stays visible, and a scheme that
# genuinely declares such a file in scope can still `git add -f` it.
ARTIFACT_EXCLUDE_MARKER = "# ops-perf-optimize: build artifact excludes"
ARTIFACT_EXCLUDE_PATTERNS = (
    ARTIFACT_EXCLUDE_MARKER,
    "*.o",
    "*.so",
    "*.so.*",
    "*.a",
    "*.pyc",
    "__pycache__/",
    "kernel_meta/",
    "golden_cache/",
    ".cache/",
    "build/",
    "build_out/",
    "dist/",
)


def _ensure_artifact_excludes(worktree: Path) -> Path:
    repo = Path(git(worktree, "rev-parse", "--path-format=absolute", "--git-common-dir").strip()).parent
    probe = subprocess.run(
        ("git", *GIT_CONFIG_ARGS, "-C", str(repo), "config", "--get", "extensions.worktreeConfig"),
        capture_output=True,
    )
    if probe.returncode != 0 or probe.stdout.strip() != b"true":
        git(repo, "config", "extensions.worktreeConfig", "true")
    exclude = worktree.parent / "worktree.exclude"
    current = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
    if ARTIFACT_EXCLUDE_MARKER not in current:
        with exclude.open("a", encoding="utf-8") as stream:
            if current and not current.endswith("\n"):
                stream.write("\n")
            stream.write("\n".join(ARTIFACT_EXCLUDE_PATTERNS) + "\n")
    git(worktree, "config", "--worktree", "core.excludesFile", str(exclude))
    return exclude


def cmd_worktree_remove(args: argparse.Namespace) -> int:
    path = Path(args.path).resolve()
    if not is_git_repo(path):
        raise WorkspaceError(f"not a git worktree: {path}")
    common_dir = Path(git(path, "rev-parse", "--path-format=absolute", "--git-common-dir").strip())
    repo = common_dir.parent
    dirty = dirty_files(path)
    if dirty and not args.force:
        raise WorkspaceError(f"worktree has uncommitted changes (use --force after saving them): {dirty}")
    remove_args = ["worktree", "remove"]
    if args.force:
        remove_args.append("--force")
    remove_args.append(str(path))
    git(repo, *remove_args)
    write_json(args.out, {"removed": str(path), "had_uncommitted_changes": bool(dirty)})
    return 0


# -----------------------------------------------------------------------------------------------------------
# discard-unexpected


def cmd_discard_unexpected(args: argparse.Namespace) -> int:
    worktree = Path(args.worktree).resolve()
    if not is_git_repo(worktree):
        raise WorkspaceError(f"not a git worktree: {worktree}")
    allow_path = Path(args.allow_list).resolve()
    try:
        allow = json.loads(allow_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise WorkspaceError(f"cannot read allow list: {error}") from error
    if not isinstance(allow, list) or not all(isinstance(item, str) for item in allow):
        raise WorkspaceError("allow list must be a JSON array of relative paths")
    allowed = set(allow)

    out_dir = Path(args.patch_out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    entries = status_entries(worktree)
    tracked_paths: set[str] = set()
    untracked_paths: set[str] = set()
    for entry in entries:
        if entry["xy"] == "??":
            if entry["path"] not in allowed:
                untracked_paths.add(entry["path"])
            continue
        if entry["xy"] == "!!":
            continue
        for path in filter(None, (entry["orig_path"], entry["path"])):
            if path not in allowed:
                tracked_paths.add(path)
    unexpected_tracked = sorted(tracked_paths)
    unexpected_untracked = sorted(untracked_paths)

    def in_head(relative: str) -> bool:
        probe = subprocess.run(
            ("git", "-C", str(worktree), "cat-file", "-e", f"HEAD:{relative}"),
            capture_output=True,
        )
        return probe.returncode == 0

    patch = out_dir / "unexpected.patch"
    backup = out_dir / "unexpected-untracked"
    if unexpected_tracked:
        patch.write_bytes(git_bytes(worktree, "diff", "--binary", "HEAD", "--", *unexpected_tracked))
        head_paths = [path for path in unexpected_tracked if in_head(path)]
        new_paths = [path for path in unexpected_tracked if not in_head(path)]
        if head_paths:
            git(worktree, "restore", "--staged", "--worktree", "--", *head_paths)
        for relative in new_paths:
            git(worktree, "restore", "--staged", "--", relative)
            (worktree / relative).unlink(missing_ok=True)
    for relative in unexpected_untracked:
        source = worktree / relative
        target = backup / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        source.unlink()
    write_json(args.out, {
        "discarded_tracked": unexpected_tracked,
        "discarded_untracked": unexpected_untracked,
        "audit_patch": str(patch) if unexpected_tracked else None,
        "untracked_backup_dir": str(backup) if unexpected_untracked else None,
        "allow_list": sorted(allowed),
    })
    return 0


# -----------------------------------------------------------------------------------------------------------
# merge-check


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cmd_runtime_evidence(args: argparse.Namespace) -> int:
    """Generate a runtime evidence JSON for validate_execution_identity."""
    repo = repo_or_error(Path(args.repo)) if args.repo else None
    out_dir = Path(args.patch_out).resolve() if args.patch_out else None
    loaded = []
    for raw in (args.loaded_artifact or []):
        path = Path(raw).resolve()
        if not path.is_file():
            raise WorkspaceError(f"loaded artifact does not exist: {path}")
        loaded.append({"path": str(path), "sha256": _sha256_file(path)})
    if not loaded:
        raise WorkspaceError("runtime-evidence requires at least one --loaded-artifact")
    # source artifact: a listing file that names every loaded artifact
    listing = (out_dir or Path(args.out).resolve().parent) / "load-evidence.txt"
    listing.parent.mkdir(parents=True, exist_ok=True)
    listing.write_text(
        "\n".join(f"{item['path']} sha256={item['sha256']}" for item in loaded) + "\n"
    )
    evidence = {
        "method": args.method or "TTK kernel --binary=release via ASCEND_CUSTOM_OPP_PATH; BINARY_MATCH",
        "target_soc": args.target_soc,
        "source_artifacts": [{"path": str(listing), "sha256": _sha256_file(listing)}],
        "loaded_artifacts": loaded,
    }
    if args.commit and repo:
        evidence["commit"] = rev_resolve(repo, args.commit)
    write_json(args.out, evidence)
    return 0


def cmd_merge_check(args: argparse.Namespace) -> int:
    repo = repo_or_error(Path(args.repo))
    candidate = rev_resolve(repo, args.candidate_rev)
    target_head = rev_resolve(repo, args.target_branch)
    merged = rev_resolve(repo, args.merged_rev) if args.merged_rev else target_head
    if args.merged_rev and merged != target_head:
        raise WorkspaceError(
            f"--merged-rev {merged[:12]} does not match the current target branch "
            f"head {target_head[:12]}; merge first, then produce the equivalence evidence"
        )
    if args.baseline_rev:
        baseline = rev_resolve(repo, args.baseline_rev)
    else:
        base_output = git(repo, "merge-base", merged, candidate).strip()
        baseline = base_output or None

    ff = merged == candidate
    if ff and not args.baseline_rev:
        raise WorkspaceError(
            "fast-forward evidence requires --baseline-rev (the pre-merge target head or "
            "the workspace baseline commit); without it the blob-identity check compares "
            "the candidate against itself and proves nothing"
        )
    candidate_tree = tree_sha(repo, candidate)
    merged_tree = tree_sha(repo, merged)
    tree_equal = ff and merged_tree == candidate_tree

    blob_identity = {"files_checked": 0, "mismatches": []}
    if baseline and ff:
        changed = git(repo, "diff", "--no-renames", "--name-only", baseline, candidate)
        for relative in (line.strip() for line in changed.splitlines() if line.strip()):
            blob_identity["files_checked"] += 1
            merged_blob = git(repo, "rev-parse", f"{merged}:{relative}").strip()
            candidate_blob = git(repo, "rev-parse", f"{candidate}:{relative}").strip()
            if merged_blob != candidate_blob:
                blob_identity["mismatches"].append(relative)

    rebuild = None
    if args.rebuild_artifact and args.accepted_artifact:
        rebuild = {
            "rebuild_sha256": _sha256_file(Path(args.rebuild_artifact).resolve()),
            "accepted_sha256": _sha256_file(Path(args.accepted_artifact).resolve()),
        }
        rebuild["matches_accepted"] = (
            rebuild["rebuild_sha256"] == rebuild["accepted_sha256"]
        )
    elif bool(args.rebuild_artifact) != bool(args.accepted_artifact):
        raise WorkspaceError("merge-check needs both --rebuild-artifact and --accepted-artifact")

    smoke = None
    if args.smoke_report:
        smoke_path = Path(args.smoke_report).resolve()
        if not smoke_path.is_file():
            raise WorkspaceError(f"smoke report does not exist: {smoke_path}")
        smoke = {"path": str(smoke_path), "sha256": _sha256_file(smoke_path)}
        try:
            payload = json.loads(smoke_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            smoke.update({"pass": False, "status": None,
                          "reason": f"smoke report is not a JSON object: {error}"})
        else:
            if not isinstance(payload, dict):
                smoke.update({"pass": False, "status": None,
                              "reason": "smoke report is not a JSON object"})
            else:
                status = str(payload.get("result", payload.get("status", ""))).strip().upper()
                smoke["pass"] = status == "PASS"
                smoke["status"] = status or None
                if not smoke["pass"]:
                    smoke["reason"] = f"smoke report status is {status or 'missing'}; PASS required"

    reuse: list = []
    if args.reuse_json:
        reuse_path = Path(args.reuse_json).resolve()
        try:
            loaded = json.loads(reuse_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise WorkspaceError(f"cannot read reuse list: {error}") from error
        if not isinstance(loaded, list):
            raise WorkspaceError("reuse list must be a JSON array")
        reuse = loaded
    if not ff:
        reuse = []

    decision = "fast_forward" if ff else "merge"
    eligible = ff and tree_equal and not blob_identity["mismatches"]
    missing_evidence = []
    if ff and smoke is None:
        missing_evidence.append("smoke-report (regression verification)")
    if ff and rebuild is None:
        missing_evidence.append("rebuild-artifact/accepted-artifact (build reproducibility)")
    if rebuild is not None:
        eligible = eligible and rebuild["matches_accepted"]
    if smoke is not None:
        eligible = eligible and smoke["pass"]
    # Fast-forward reuse is evidence-carrying only: without the regression and
    # rebuild receipts the fast path would re-measure nothing and prove nothing.
    if missing_evidence:
        eligible = False

    write_json(args.out, {
        "schema_version": 1,
        "decision": decision,
        "evidence_reuse_eligible": eligible,
        "ff_check": {"target_head": target_head, "candidate": candidate, "merged": merged},
        "tree_identity": {
            "merged_tree": merged_tree, "candidate_tree": candidate_tree, "equal": tree_equal,
        },
        "blob_identity": blob_identity,
        "missing_evidence": missing_evidence,
        "baseline_for_diff": baseline,
        "rebuild": rebuild,
        "smoke": smoke,
        "evidence_reuse": reuse,
    })
    return 0


# -----------------------------------------------------------------------------------------------------------
# CLI


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    sub = result.add_subparsers(dest="command", required=True)

    probe = sub.add_parser("probe", help="probe a code directory for git workspace readiness")
    probe.add_argument("--code-dir", required=True)
    probe.add_argument("--out", required=True)
    probe.set_defaults(func=cmd_probe)

    init = sub.add_parser("init", help="consented in-place git init: first commit as baseline (reversible, .git only)")
    init.add_argument("--code-dir", required=True)
    init.add_argument("--out", required=True)
    prepare = sub.add_parser("prepare-baseline", help="materialize the baseline commit per dirty-state policy")
    prepare.add_argument("--repo", required=True)
    prepare.add_argument("--option", choices=["b", "d"], default="b",
                         help="b: HEAD baseline (dirty changes stay in the user worktree, default); "
                              "d: save an audit patch then discard")
    prepare.add_argument("--run-dir", required=True)
    prepare.add_argument("--closure-files", help="JSON array of operator closure paths (option b warning)")
    prepare.add_argument("--out", required=True)
    init.set_defaults(func=cmd_init)
    prepare.set_defaults(func=cmd_prepare_baseline)

    add = sub.add_parser("worktree-add", help="create (or re-verify) the single run worktree")
    add.add_argument("--repo", required=True)
    add.add_argument("--branch", required=True)
    add.add_argument("--from", dest="from_rev", required=True)
    add.add_argument("--path", required=True)
    add.add_argument("--out", required=True)
    add.set_defaults(func=cmd_worktree_add)

    remove = sub.add_parser("worktree-remove", help="remove the run worktree (refuses dirty without --force)")
    remove.add_argument("--path", required=True)
    remove.add_argument("--force", action="store_true")
    remove.add_argument("--out", required=True)
    remove.set_defaults(func=cmd_worktree_remove)

    discard = sub.add_parser("discard-unexpected",
                             help="save and discard worktree changes outside the frozen allow list")
    discard.add_argument("--worktree", required=True)
    discard.add_argument("--allow-list", required=True, help="JSON array of allowed relative paths")
    discard.add_argument("--patch-out", required=True)
    discard.add_argument("--out", required=True)
    discard.set_defaults(func=cmd_discard_unexpected)

    runtime = sub.add_parser(
        "runtime-evidence",
        help="generate runtime evidence JSON for validate_execution_identity",
    )
    runtime.add_argument("--repo", help="git repository (optional, for commit pinning)")
    runtime.add_argument("--commit", help="commit to pin in the evidence")
    runtime.add_argument("--target-soc", required=True)
    runtime.add_argument("--loaded-artifact", action="append", required=True,
                         help="actually loaded artifact file (repeatable)")
    runtime.add_argument("--method", help="evidence method description")
    runtime.add_argument("--patch-out", help="directory for the load listing file")
    runtime.add_argument("--out", required=True)
    runtime.set_defaults(func=cmd_runtime_evidence)

    merge = sub.add_parser("merge-check", help="produce merge-equivalence evidence")
    merge.add_argument("--repo", required=True)
    merge.add_argument("--candidate-rev", required=True)
    merge.add_argument("--target-branch", required=True)
    merge.add_argument("--merged-rev", help="target branch head after merge (default: current target head)")
    merge.add_argument("--baseline-rev", required=False,
                       help="pre-merge target head or workspace baseline commit; required for "
                            "fast-forward evidence (default: merge-base, which degenerates "
                            "to the candidate itself after a fast-forward merge)")
    merge.add_argument("--rebuild-artifact", help="rebuilt artifact in the original project context")
    merge.add_argument("--accepted-artifact", help="accepted artifact from final verification")
    merge.add_argument("--smoke-report", help="regression smoke report path (JSON object with result/status = PASS)")
    merge.add_argument("--reuse-json", help="JSON array of evidence-reuse entries (fast-forward path only)")
    merge.add_argument("--out", required=True)
    merge.set_defaults(func=cmd_merge_check)

    return result


def main() -> int:
    args = parser().parse_args()
    try:
        return args.func(args)
    except (WorkspaceError, GitError, ValueError, OSError, KeyError) as error:
        emit(json.dumps({"status": "error", "error": str(error)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
