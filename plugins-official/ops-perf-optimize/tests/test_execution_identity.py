# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "ops-perf-optimize-workflow" / "scripts"))
from prepare_case_sets import code_identity, identity  # noqa: E402

SCRIPT = ROOT / "skills" / "ops-perf-optimize-workflow" / "scripts" / "validate_execution_identity.py"
SPEC = importlib.util.spec_from_file_location("validate_execution_identity", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def write_json(path: Path, value: dict) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    source = tmp_path / "source"
    source.mkdir()
    (source / "kernel.cpp").write_text("void kernel() {}\n", encoding="utf-8")
    request = write_json(tmp_path / "request.json", {})
    manifest = write_json(
        tmp_path / "run-manifest.json",
        {
            "schema_version": 2,
            "request": identity(request),
            "inputs": {"code": code_identity(source)},
            "configuration": {
                "target_socs": ["Ascend910_93"],
                "performance_reference": {"kind": "baseline", "target_ratio": 1.0},
            },
        },
    )
    built = tmp_path / "build" / "libop.so"
    loaded = tmp_path / "runtime" / "libop.so"
    built.parent.mkdir()
    loaded.parent.mkdir()
    built.write_bytes(b"same implementation")
    loaded.write_bytes(built.read_bytes())
    return manifest, source, built, loaded


def record(tmp_path: Path) -> tuple[Path, Path, Path]:
    manifest, _, built, loaded = fixture(tmp_path)
    build_log = tmp_path / "build.log"
    build_log.write_text("build succeeded\n", encoding="utf-8")
    loader_log = tmp_path / "loader.log"
    loader_log.write_text(f"loaded {loaded.resolve()}\n", encoding="utf-8")
    runtime = write_json(
        tmp_path / "runtime-evidence.json",
        {
            "method": "loader trace",
            "target_soc": "Ascend910_93",
            "source_artifacts": [MODULE.file_identity(loader_log)],
            "loaded_artifacts": [MODULE.file_identity(loaded)],
        },
    )
    output = tmp_path / "execution-identity.json"
    args = SimpleNamespace(
        manifest=manifest,
        target_soc="Ascend910_93",
        build_command="build operator",
        build_log=build_log,
        built_artifact=[built],
        runtime_evidence=runtime,
        out=output,
    )
    assert MODULE.record(args)["status"] == "complete"
    return manifest, output, loaded


def test_records_complete_source_build_load_chain(tmp_path: Path) -> None:
    manifest, output, _ = record(tmp_path)
    document = MODULE.validate_execution_identity(manifest, output)
    dependencies = MODULE.dependency_paths(document)
    assert document["targets"][0]["target_soc"] == "Ascend910_93"
    assert str((tmp_path / "build.log").resolve()) in dependencies
    assert str((tmp_path / "runtime-evidence.json").resolve()) in dependencies


def runtime_args(tmp_path, manifest, built, loaded, loader_line):
    build_log = tmp_path / "build.log"
    build_log.write_text("build succeeded\n", encoding="utf-8")
    loader_log = tmp_path / "loader.log"
    loader_log.write_text(loader_line, encoding="utf-8")
    runtime = write_json(
        tmp_path / "runtime-evidence.json",
        {
            "method": "loader trace",
            "source_artifacts": [MODULE.file_identity(loader_log)],
            "loaded_artifacts": [MODULE.file_identity(loaded)],
        },
    )
    return SimpleNamespace(
        manifest=manifest,
        target_soc="Ascend910_93",
        build_command="build operator",
        build_log=build_log,
        built_artifact=[built],
        runtime_evidence=runtime,
        out=tmp_path / "execution-identity.json",
    )


def test_rejects_loaded_artifact_from_another_build(tmp_path: Path) -> None:
    manifest, _, built, loaded = fixture(tmp_path)
    loaded.write_bytes(b"different implementation")
    args = runtime_args(tmp_path, manifest, built, loaded, f"loaded {loaded.resolve()}\n")
    with pytest.raises(ValueError, match="do not match the recorded build"):
        MODULE.record(args)


def test_rejects_runtime_claim_without_raw_evidence(tmp_path: Path) -> None:
    manifest, _, built, loaded = fixture(tmp_path)
    args = runtime_args(tmp_path, manifest, built, loaded, "no target artifact recorded\n")
    with pytest.raises(ValueError, match="does not identify loaded artifact"):
        MODULE.record(args)


def test_rejects_source_change_after_freeze(tmp_path: Path) -> None:
    manifest, output, _ = record(tmp_path)
    (tmp_path / "source" / "kernel.cpp").write_text("void changed() {}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="frozen source identity changed"):
        MODULE.validate_execution_identity(manifest, output)


def _git_repo_with_baseline(tmp_path: Path) -> tuple[Path, Path, Path]:
    """A git repo + a run root whose baseline.json anchors the committed state."""

    source = tmp_path / "source"
    source.mkdir()
    (source / "kernel.cpp").write_text("void kernel() {}\n", encoding="utf-8")

    def git(*args):
        result = subprocess.run(("git", "-C", str(source), *args), capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        return result.stdout
    git("init", "-q", "-b", "master")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    git("add", "-A")
    git("commit", "-qm", "init")
    commit = git("rev-parse", "HEAD").strip()
    tree = git("rev-parse", "HEAD^{tree}").strip()
    run_root = tmp_path / "run"
    (run_root / "baseline").mkdir(parents=True)
    write_json(
        run_root / "baseline" / "baseline.json",
        {"option": "b", "baseline_commit": commit, "baseline_tree_sha": tree, "dirty_files": []},
    )
    # The run root needs a manifest for _run_root discovery; reuse the parent one.
    return source, run_root, commit


def _worktree_record_args(source: Path, run_root: Path) -> SimpleNamespace:
    worktree = run_root / "worktree"
    subprocess.run(("git", "-C", str(source), "worktree", "add", "--detach", str(worktree), "HEAD"),
                   check=True, capture_output=True)
    request = write_json(source.parent / "request.json", {})
    manifest = write_json(
        run_root / "run-manifest.json",
        {
            "schema_version": 2,
            "request": identity(request),
            "inputs": {"code": code_identity(source)},
            "configuration": {
                "target_socs": ["Ascend910_93"],
                "performance_reference": {"kind": "baseline", "target_ratio": 1.0},
            },
        },
    )
    built = run_root / "libop.so"
    built.write_bytes(b"impl")
    build_log = run_root / "build.log"
    build_log.write_text("build\n", encoding="utf-8")
    loader_log = run_root / "loader.log"
    loaded = run_root / "loaded.so"
    loaded.write_bytes(b"impl")
    loader_log.write_text(f"loaded {loaded.resolve()}\n", encoding="utf-8")
    runtime = write_json(
        run_root / "runtime-evidence.json",
        {
            "method": "loader trace",
            "target_soc": "Ascend910_93",
            "source_artifacts": [MODULE.file_identity(loader_log)],
            "loaded_artifacts": [MODULE.file_identity(loaded)],
        },
    )
    output = run_root / "baseline" / "execution-identity.json"
    return SimpleNamespace(
        manifest=manifest, target_soc="Ascend910_93", build_command="build",
        build_log=build_log, built_artifact=[built], runtime_evidence=runtime, out=output,
    )


def test_git_baseline_anchor_survives_user_worktree_drift(tmp_path: Path) -> None:
    """The recorded commit anchors source identity across edits in the user worktree."""
    source, run_root, _ = _git_repo_with_baseline(tmp_path)
    # Worktree equals the baseline tree: simulate via a checkout dir of HEAD.
    args = _worktree_record_args(source, run_root)
    # User worktree drifts (dirty edit) BEFORE recording.
    (source / "kernel.cpp").write_text("void user_edit() {}\n", encoding="utf-8")
    assert MODULE.record(args)["status"] == "complete"
    document = json.loads(args.out.read_text(encoding="utf-8"))
    assert document["source_anchor"]["kind"] == "git-baseline"
    # Further drift after recording must not invalidate the anchored chain.
    (source / "kernel.cpp").write_text("void more_drift() {}\n", encoding="utf-8")
    MODULE.validate_execution_identity(args.manifest, args.out)


def test_git_baseline_anchor_blocks_build_on_drifted_worktree(tmp_path: Path) -> None:
    """The worktree used for the build must match the frozen baseline commit."""
    source, run_root, _ = _git_repo_with_baseline(tmp_path)
    args = _worktree_record_args(source, run_root)
    # Advance the worktree with a real content change.
    worktree = run_root / "worktree"
    (worktree / "kernel.cpp").write_text("void advanced() {}\n", encoding="utf-8")
    subprocess.run(("git", "-C", str(worktree), "add", "-A"), check=True, capture_output=True)
    subprocess.run(("git", "-C", str(worktree), "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "advance"), check=True, capture_output=True)
    with pytest.raises(ValueError, match="worktree tree differs from the frozen baseline"):
        MODULE.record(args)


def test_git_baseline_anchor_blocks_uncommitted_worktree_edits(tmp_path: Path) -> None:
    """An unchanged HEAD cannot vouch for uncommitted changes to the compiled source."""
    source, run_root, _ = _git_repo_with_baseline(tmp_path)
    args = _worktree_record_args(source, run_root)
    # Same HEAD, edited working tree: the anchor check must refuse.
    worktree = run_root / "worktree"
    (worktree / "kernel.cpp").write_text("void silently_edited() {}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="uncommitted changes"):
        MODULE.record(args)
    # Cleaning the edit restores the anchor.
    subprocess.run(("git", "-C", str(worktree), "checkout", "--", "."), check=True, capture_output=True)
    assert MODULE.record(args)["status"] == "complete"


def test_baseline_anchor_discovers_finalize_alias(tmp_path: Path) -> None:
    """The real session produced baseline-finalize.json; discovery accepts it."""
    source, run_root, _ = _git_repo_with_baseline(tmp_path)
    (run_root / "baseline" / "baseline.json").rename(
        run_root / "baseline" / "baseline-finalize.json"
    )
    args = _worktree_record_args(source, run_root)
    assert MODULE.record(args)["status"] == "complete"
    document = json.loads(args.out.read_text(encoding="utf-8"))
    assert document["source_anchor"]["kind"] == "git-baseline"
