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

__all__ = [
    "WorkflowStateRecoveryResult",
    "baseline_dir",
    "bootstrap_optimize_workflow_state",
    "classify_optimize_workspace",
    "initialize_baseline_integrity",
    "recover_optimize_workflow_state",
]

import importlib.util
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from types import ModuleType
from typing import Any


def _plugin_skills_root() -> Path:
    runtime_file = Path(__file__).resolve()
    for root in (runtime_file.parents[1], runtime_file.parents[2]):
        skills = root / "skills"
        if skills.is_dir():
            return skills
    return runtime_file.parents[1] / "skills"


@lru_cache(maxsize=1)
def _skill_roots_by_name() -> dict[str, Path]:
    root = _plugin_skills_root()
    if not root.is_dir():
        raise FileNotFoundError(f"skills root does not exist: {root}")
    direct_skills = [path for path in root.iterdir() if path.is_dir()]
    discovered: dict[str, Path] = {}
    if any((path / "SKILL.md").exists() for path in direct_skills):
        for skill_dir in direct_skills:
            if (skill_dir / "SKILL.md").exists():
                discovered[skill_dir.name] = skill_dir
        return discovered
    for group_dir in direct_skills:
        for skill_dir in group_dir.iterdir():
            if skill_dir.is_dir() and (skill_dir / "SKILL.md").exists():
                discovered[skill_dir.name] = skill_dir
    return discovered


@lru_cache(maxsize=None)
def _load_skill_script_module(skill_name: str, script_name: str) -> ModuleType:
    skill_root = _skill_roots_by_name().get(skill_name)
    if skill_root is None:
        raise FileNotFoundError(f"skill not found in plugin payload: {skill_name!r}")
    relative = Path(script_name + ".py")
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"Invalid skill script path: {script_name!r}")
    path = skill_root / "scripts" / relative
    if not path.is_file():
        raise FileNotFoundError(f"Skill script does not exist: {path}")
    module_name = f"plugin_skill_{skill_name.replace('-', '_')}_{script_name.replace('/', '_').replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load skill script: {path}")
    module = importlib.util.module_from_spec(spec)
    scripts_root = str(skill_root / "scripts")
    added = scripts_root not in sys.path
    if added:
        sys.path.insert(0, scripts_root)
    previous_module = sys.modules.get(module_name)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        if previous_module is None:
            sys.modules.pop(module_name, None)
        else:
            sys.modules[module_name] = previous_module
        if added:
            sys.path.remove(scripts_root)
    return module


def baseline_dir(workspace: Path) -> Path:
    return workspace / "baseline"


@lru_cache(maxsize=1)
def _optimize_baseline_module() -> ModuleType:
    return _load_skill_script_module("triton-npu-optimize-state", "baseline/check")


def load_baseline_state(workspace: Path) -> Any:
    return _optimize_baseline_module().load_baseline_state(workspace)


def baseline_gate_issues(workspace: Path) -> tuple[str, ...]:
    return _optimize_baseline_module().baseline_gate_issues(workspace)


@dataclass(frozen=True)
class WorkspaceInspection:
    state: str
    detail: str | None
    test_mode: str | None
    bench_mode: str | None


def classify_optimize_workspace(input_path: Path, workdir: Path) -> WorkspaceInspection:
    return _classify_optimize_workspace(input_path, workdir)


def _classify_optimize_workspace(
    input_path: Path,
    workdir: Path,
) -> WorkspaceInspection:
    has_rounds = any(path.is_dir() for path in workdir.glob("opt-round-*"))
    test_harnesses = _existing_test_harnesses(input_path, workdir)
    bench_harness = _existing_bench_harness(input_path, workdir)
    has_baseline_dir = baseline_dir(workdir).exists()

    if not has_rounds:
        if has_baseline_dir:
            baseline_issue = _baseline_issue(workdir)
            if baseline_issue is not None:
                return WorkspaceInspection("partial-session", baseline_issue, None, None)
            return _classify_baseline_only_workspace(input_path, workdir)
        return WorkspaceInspection("no-session", None, None, None)

    baseline_issue = _baseline_issue(workdir)
    if baseline_issue is not None:
        return WorkspaceInspection("partial-session", baseline_issue, None, None)

    return _classify_harness_modes(input_path, workdir, bench_harness, test_harnesses)


def _classify_harness_modes(
    input_path: Path,
    workdir: Path,
    bench_harness: Path,
    test_harnesses: list[Path],
) -> WorkspaceInspection:
    if not test_harnesses:
        return WorkspaceInspection(
            "partial-session",
            f"missing generated test harness for {input_path.name}",
            None,
            None,
        )
    if len(test_harnesses) > 1:
        return WorkspaceInspection("partial-session", "multiple test harnesses exist", None, None)
    if not bench_harness.exists():
        return WorkspaceInspection("partial-session", f"missing {bench_harness.name}", None, None)

    test_mode = _parse_test_mode(test_harnesses[0])
    if test_mode is None:
        return WorkspaceInspection(
            "partial-session",
            f"unreadable test-mode metadata in {test_harnesses[0].name}",
            None,
            None,
        )

    try:
        bench_mode = _resolve_bench_mode_from_baseline(workdir)
    except (FileNotFoundError, ValueError, KeyError) as exc:
        return WorkspaceInspection(
            "partial-session",
            f"unable to resolve bench mode from baseline/state.json: {exc}",
            None,
            None,
        )

    return WorkspaceInspection("resumable-session", None, test_mode, bench_mode)


def _existing_test_harnesses(input_path: Path, workdir: Path) -> list[Path]:
    declared_test = _declared_test_harness(input_path, workdir)
    candidates: list[Path] = []
    if declared_test is not None:
        candidates.append(declared_test)
    candidates.extend(
        [
            input_path.with_name(f"differential_test_{input_path.stem}.py"),
            input_path.with_name(f"test_{input_path.stem}.py"),
        ]
    )
    return _existing_unique_paths(candidates)


def _existing_bench_harness(input_path: Path, workdir: Path) -> Path:
    declared_bench = _declared_bench_harness(input_path, workdir)
    if declared_bench is not None and declared_bench.exists():
        return declared_bench
    return input_path.with_name(f"bench_{input_path.stem}.py")


def _resolve_baseline_state_path(relative_path: str, workdir: Path) -> Path:
    declared = Path(relative_path)
    baseline_dir_path = baseline_dir(workdir)
    if not declared.is_absolute():
        return baseline_dir_path / declared
    return declared


def _declared_test_harness(input_path: Path, workdir: Path) -> Path | None:
    state = _matching_baseline_state(input_path, workdir)
    if state is None:
        return None
    path = _resolve_baseline_state_path(state.test_file, workdir)
    if not path.exists():
        return None
    return path


def _declared_bench_harness(input_path: Path, workdir: Path) -> Path | None:
    state = _matching_baseline_state(input_path, workdir)
    if state is None:
        return None
    path = _resolve_baseline_state_path(state.bench_file, workdir)
    if not path.exists():
        return None
    return path


def _matching_baseline_state(input_path: Path, workdir: Path):
    try:
        state = load_baseline_state(workdir)
    except ValueError:
        return None

    declared_source = _resolve_baseline_state_path(state.source_operator, workdir).resolve()
    if declared_source != input_path.resolve():
        return None
    return state


def _existing_unique_paths(paths: list[Path]) -> list[Path]:
    unique_paths: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        resolved = path.resolve(strict=False)
        if resolved in seen:
            continue
        seen.add(resolved)
        if path.exists():
            unique_paths.append(path)
    return unique_paths


def _parse_test_mode(test_file: Path) -> str | None:
    metadata = _test_api_module().parse_metadata(test_file)
    mode = metadata.get("test-mode")
    if mode not in {"standalone", "differential"}:
        return None
    return str(mode)


def _resolve_bench_mode_from_baseline(workdir: Path) -> str:
    state = load_baseline_state(workdir)
    return state.bench_mode


def _baseline_issue(workdir: Path) -> str | None:
    root = baseline_dir(workdir)
    if not root.exists():
        return "missing established baseline/"

    issues = baseline_gate_issues(workdir)
    if not issues:
        return None
    return issues[0]


def _classify_baseline_only_workspace(input_path: Path, workdir: Path) -> WorkspaceInspection:
    test_harnesses = _existing_test_harnesses(input_path, workdir)
    bench_harness = _existing_bench_harness(input_path, workdir)
    return _classify_harness_modes(input_path, workdir, bench_harness, test_harnesses)


@lru_cache(maxsize=1)
def _test_api_module():
    return _load_skill_script_module("triton-npu-run-eval", "run_test_api")


@lru_cache(maxsize=1)
def _state_machine_module():
    return _load_skill_script_module("triton-npu-optimize-state", "state_manage/state_machine")


@dataclass(frozen=True)
class WorkflowStateRecoveryResult:
    guidance: str | None


def bootstrap_optimize_workflow_state(
    state_path: Path,
    *,
    baseline_reused: bool,
    remote: str | None = None,
    remote_workdir: str | None = None,
) -> None:
    _state_machine_module().bootstrap_state(
        state_path,
        baseline_reused=baseline_reused,
        remote=remote,
        remote_workdir=remote_workdir,
    )


def initialize_baseline_integrity(state_path: Path) -> None:
    _load_skill_script_module(
        "triton-npu-optimize-state", "optimize_state_api"
    ).initialize_baseline_integrity(state_path)


def recover_optimize_workflow_state(
    workdir: Path,
    *,
    state_path: Path,
) -> WorkflowStateRecoveryResult:
    """Recover workflow state without touching durable artifacts.

    Multiple Claude sessions may run concurrently in one workspace, so this
    never deletes ``baseline/``, ``opt-round-*``, or transient ``.helix/``
    data; it only creates or replaces ``.helix/state.json`` itself, and only
    when that file is missing or corrupt.
    """
    if state_path.exists():
        try:
            _state_machine_module().load_state(state_path)
            return WorkflowStateRecoveryResult(None)
        except ValueError:
            pass  # corrupt state carries nothing recoverable; replace below

    source_operator, resolution_issue = _resolve_source_operator_hint(workdir)
    if resolution_issue is not None:
        return _recover_partial_session(
            state_path, resolution_issue, state_existed=state_path.exists()
        )
    if source_operator is None:
        if any(path.is_dir() for path in workdir.glob("opt-round-*")):
            return _recover_partial_session(
                state_path,
                "missing established baseline/ while opt-round-* directories exist",
                state_existed=state_path.exists(),
            )
        bootstrap_optimize_workflow_state(state_path, baseline_reused=False)
        return WorkflowStateRecoveryResult(None)

    inspection = classify_optimize_workspace(source_operator, workdir)
    if inspection.state == "resumable-session":
        bootstrap_optimize_workflow_state(state_path, baseline_reused=True)
        initialize_baseline_integrity(state_path)
        return WorkflowStateRecoveryResult(
            "Existing optimize baseline and round artifacts were accepted for resume; "
            "workflow state was rebuilt. Continue with the next round; "
            "do not call `submit-baseline` unless intentionally preparing a new baseline."
        )
    if inspection.state == "partial-session":
        return _recover_partial_session(
            state_path,
            f"cannot resume optimize workflow from partial session: {inspection.detail}",
            state_existed=state_path.exists(),
        )
    bootstrap_optimize_workflow_state(state_path, baseline_reused=False)
    return WorkflowStateRecoveryResult(None)


def _recover_partial_session(
    state_path: Path, problem: str, *, state_existed: bool
) -> WorkflowStateRecoveryResult:
    if state_existed:
        # A corrupt state file would block `submit-baseline` from bootstrapping
        # its own state, so replace it; durable artifacts stay untouched.
        bootstrap_optimize_workflow_state(state_path, baseline_reused=False)
    return WorkflowStateRecoveryResult(
        _repair_guidance(problem),
    )


def _resolve_source_operator_hint(workdir: Path) -> tuple[Path | None, str | None]:
    if not baseline_dir(workdir).exists():
        return None, None
    try:
        baseline_state = load_baseline_state(workdir)
    except (FileNotFoundError, ValueError) as exc:
        return None, f"cannot determine source operator from baseline/state.json: {exc}"

    baseline_dir_path = baseline_dir(workdir)
    declared = Path(baseline_state.source_operator)
    if declared.is_absolute():
        return declared, None
    return (baseline_dir_path / declared).resolve(), None


def _repair_guidance(problem: str) -> str:
    return (
        f"{problem} "
        "Re-run `run-test-baseline` and `run-bench-baseline`, then use "
        "`triton-npu-optimize-state` `submit-baseline` to rebuild accepted baseline state, "
        "then use `start-round` to reopen the intended `opt-round-N/` before "
        "continuing round edits, same-round state updates, or round submission."
    )
