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

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, Literal, NamedTuple, cast

from baseline.check import (
    baseline_gate_issues,
    load_baseline_state,
)
from round.contract import (
    ROUND_BENCHMARK_STATUS_VALUES,
    ROUND_CORRECTNESS_STATUS_VALUES,
    ROUND_STATE_REQUIRED_FIELDS,
)
from round.kernel_continuity import analyze_triton_kernel_continuity, is_triton_operator_source
from round.local_optimum import (
    collect_local_optimum_warnings,
    compute_round_geomean_speedup,
    validate_baseline_perf_for_speedup,
)
from shared.json_io import load_json_object, optional_str
from shared.ascendc_operator_files import ascendc_source_path, is_ascendc_api
from shared.models import OptimizeCheckResult, RoundArtifactsInspection, RoundState
from shared.paths import (
    baseline_dir,
    declared_state_file,
    existing_file,
    invalid_dependency_issue,
    missing_path_issue,
    noncanonical_path_issue,
    unexpected_path_name_issue,
)
from shared.results import append_pass_issues_to_summary, build_check_result
from shared.round_naming import expected_round_operator_name, expected_round_perf_name, resolve_workspace_operator_file
from shared.managed_integrity import load_evidence_records, operator_sha256, sha256_file, validate_integrity


_OPTIMIZE_DELETE_PT_FILES_ENV = "HELIX_OPTIMIZE_DELETE_PT_FILES"
_OPTIMIZE_DELETE_TRITON_CACHE_ENV = "HELIX_OPTIMIZE_DELETE_TRITON_CACHE"
_TRITON_CACHE_DIR_NAME = ".helix-triton-cache"
OptimizePtCleanupMode = Literal["never", "round", "run-test"]
_PT_CLEANUP_MODES = frozenset({"never", "round", "run-test"})
_LEGACY_ROUND_CLEANUP_VALUES = frozenset({"1", "true", "yes", "on"})
_LEGACY_NEVER_CLEANUP_VALUES = frozenset({"0", "false", "no", "off"})
_PROFILE_ARTIFACT_PREFIXES = ("PROF_", "OPPROF_")
_ALLOWED_CORRECTNESS_STATUS_VALUES = frozenset(ROUND_CORRECTNESS_STATUS_VALUES)
_ALLOWED_BENCHMARK_STATUS_VALUES = frozenset(ROUND_BENCHMARK_STATUS_VALUES)
_BENCHMARK_REQUIRED_FIELDS = (
    "perf_artifact",
    "comparison_target_path",
    "effective_metric_source",
)


def ordinary_optimize_pt_cleanup_mode() -> OptimizePtCleanupMode:
    raw_value = os.environ.get(_OPTIMIZE_DELETE_PT_FILES_ENV)
    if raw_value is None:
        return "round"
    value = raw_value.strip().lower()
    if value in _PT_CLEANUP_MODES:
        return cast(OptimizePtCleanupMode, value)
    if value in _LEGACY_ROUND_CLEANUP_VALUES:
        return "round"
    if value in _LEGACY_NEVER_CLEANUP_VALUES:
        return "never"
    return "round"


def is_ordinary_pt_result_file(path: Path) -> bool:
    name_lower = path.name.lower()
    return name_lower == "test_result.pt" or name_lower.endswith("_result.pt")


def cleanup_pt_file(pt_file: Path) -> str | None:
    if not pt_file.is_file() or not is_ordinary_pt_result_file(pt_file):
        return None
    try:
        pt_file.unlink()
        return pt_file.name
    except OSError:
        return None


def cleanup_dir_pt_files(directory: Path) -> list[str]:
    cleaned: list[str] = []
    try:
        candidates = sorted(
            directory.rglob("*"),
            key=lambda path: (len(path.relative_to(directory).parts), str(path)),
        )
    except OSError:
        return cleaned
    for pt_file in candidates:
        if not pt_file.is_file() or pt_file.suffix.lower() != ".pt":
            continue
        try:
            pt_file.unlink()
            cleaned.append(str(pt_file.relative_to(directory)))
        except (OSError, ValueError):
            continue
    return cleaned


def should_delete_optimize_triton_cache() -> bool:
    raw_value = os.environ.get(_OPTIMIZE_DELETE_TRITON_CACHE_ENV)
    if raw_value is None:
        return True
    return raw_value.strip().lower() not in _LEGACY_NEVER_CLEANUP_VALUES


def cleanup_workspace_triton_cache(workspace: Path) -> None:
    """Remove the fixed workspace-local Triton cache without following links."""
    if not should_delete_optimize_triton_cache():
        return
    cache_dir = workspace / _TRITON_CACHE_DIR_NAME
    if cache_dir.is_symlink() or not cache_dir.is_dir():
        return
    try:
        shutil.rmtree(cache_dir)
    except OSError:
        pass


def _is_profile_artifact_name(name: str) -> bool:
    return any(name.startswith(prefix) for prefix in _PROFILE_ARTIFACT_PREFIXES)


def _remove_artifact_path(path: Path) -> None:
    if path.is_symlink():
        path.unlink()
        return
    if path.is_dir():
        shutil.rmtree(path)
        return
    path.unlink()


def cleanup_dir_prof_artifacts(
    directory: Path,
    *,
    preserve_paths: tuple[Path, ...] = (),
) -> list[str]:
    cleaned: list[str] = []
    preserved = {path.resolve(strict=False) for path in preserve_paths}
    try:
        candidates = sorted(directory.iterdir())
    except OSError:
        return cleaned
    for artifact in candidates:
        if not _is_profile_artifact_name(artifact.name):
            continue
        if artifact.resolve(strict=False) in preserved:
            continue
        try:
            _remove_artifact_path(artifact)
            cleaned.append(artifact.name)
        except OSError:
            pass
    return cleaned


def _state_relative_path(state_dir: Path, workspace: Path, relative_path: str | None) -> Path | None:
    if relative_path is None:
        return None
    declared_path = Path(relative_path)
    state_relative = state_dir / declared_path
    if state_relative.exists():
        return state_relative
    workspace_relative = workspace / declared_path
    if workspace_relative.exists():
        return workspace_relative
    return None


def resolve_round_profile_dir(round_dir: Path) -> Path | None:
    workspace = round_dir.parent
    round_state_path = round_dir / "round-state.json"
    if round_state_path.is_file():
        try:
            state = load_round_state(round_dir)
        except ValueError:
            state = None
        if state is not None:
            declared_profile_dir = _state_relative_path(
                round_dir,
                workspace,
                state.profile_dir,
            )
            if declared_profile_dir is not None and declared_profile_dir.is_dir():
                return declared_profile_dir

    conventional_profile_dir = round_dir / "profile"
    if conventional_profile_dir.is_dir():
        return conventional_profile_dir
    return None


def _rmdir_if_empty(candidate: Path, root_dir: Path) -> None:
    try:
        if candidate != root_dir and not any(candidate.iterdir()):
            candidate.rmdir()
    except OSError:
        pass


def _cleanup_csv_only_candidate(candidate: Path, root_dir: Path, cleaned: list[str]) -> None:
    try:
        if candidate.is_symlink():
            _remove_artifact_path(candidate)
            cleaned.append(str(candidate.relative_to(root_dir)))
            return
        if candidate.is_dir():
            cleaned.extend(_cleanup_profile_dir_csv_only(candidate, root_dir=root_dir))
            _rmdir_if_empty(candidate, root_dir)
            return
        if candidate.suffix.lower() == ".csv":
            return
        _remove_artifact_path(candidate)
        cleaned.append(str(candidate.relative_to(root_dir)))
    except OSError:
        pass


def _cleanup_profile_dir_csv_only(current_dir: Path, *, root_dir: Path) -> list[str]:
    cleaned: list[str] = []
    try:
        candidates = sorted(current_dir.iterdir())
    except OSError:
        return cleaned

    for candidate in candidates:
        _cleanup_csv_only_candidate(candidate, root_dir, cleaned)

    return cleaned


def cleanup_profile_dir_csv_only(profile_dir: Path) -> list[str]:
    if not profile_dir.is_dir():
        return []
    return _cleanup_profile_dir_csv_only(profile_dir, root_dir=profile_dir)


def cleanup_round_profile_artifacts(round_dir: Path) -> list[str]:
    cleaned: list[str] = []
    profile_dir = resolve_round_profile_dir(round_dir)
    if profile_dir is not None:
        profile_dir_label = os.path.relpath(profile_dir.resolve(), round_dir.resolve())
        for name in cleanup_profile_dir_csv_only(profile_dir):
            cleaned.append(f"{profile_dir_label}/{name}")

    preserve_paths: tuple[Path, ...] = ()
    if profile_dir is not None:
        try:
            if profile_dir.parent.resolve() == round_dir.resolve():
                preserve_paths = (profile_dir,)
        except OSError:
            preserve_paths = ()

    for name in cleanup_dir_prof_artifacts(round_dir, preserve_paths=preserve_paths):
        cleaned.append(name)
    return cleaned


def cleanup_round_ir_artifacts(round_dir: Path) -> list[str]:
    if not _has_deep_analysis_entry(round_dir):
        return []
    ir_dir = round_dir / "ir"
    if not ir_dir.is_dir() and not ir_dir.is_symlink():
        return []
    try:
        _remove_artifact_path(ir_dir)
        return ["ir"]
    except OSError:
        return []


def _has_deep_analysis_entry(round_dir: Path) -> bool:
    return _deep_analysis_state_and_entry(round_dir) is not None


def _deep_analysis_state_and_entry(round_dir: Path) -> tuple[dict[str, object], dict[str, object]] | None:
    state_path = round_dir.parent / ".helix" / "state.json"
    try:
        state = load_json_object(state_path, display_name=".helix/state.json")
    except (FileNotFoundError, ValueError):
        return None
    rounds = state.get("rounds")
    if not isinstance(rounds, dict):
        return None
    rounds_dict = cast(dict[str, object], rounds)
    for round_entry_object in rounds_dict.values():
        if not isinstance(round_entry_object, dict):
            continue
        round_entry = cast(dict[str, object], round_entry_object)
        if round_entry.get("round_dir") != round_dir.name:
            continue
        if isinstance(round_entry.get("deep_analysis"), dict):
            return state, round_entry
    return None


def cleanup_workspace_profile_artifacts(workspace: Path) -> list[str]:
    cleaned: list[str] = []
    for round_dir in sorted(workspace.glob("opt-round-*")):
        if not round_dir.is_dir():
            continue
        for name in cleanup_round_profile_artifacts(round_dir):
            cleaned.append(f"{round_dir.name}/{name}")
        for name in cleanup_round_ir_artifacts(round_dir):
            cleaned.append(f"{round_dir.name}/{name}")
    for name in cleanup_dir_prof_artifacts(workspace):
        cleaned.append(name)
    return cleaned


def _comparison_target_dependency_issue(round_dir: Path) -> str | None:
    state_path = baseline_dir(round_dir.parent) / "state.json"
    if not state_path.is_file():
        # baseline_gate_issues() already reports a missing baseline/state.json; avoid duplicating it here.
        return None
    try:
        load_baseline_state(round_dir.parent)
    except ValueError as exc:
        return invalid_dependency_issue(
            "comparison_target_path",
            "baseline/state.json",
            str(exc),
        )
    return None


def _resolve_comparison_target_value(data: dict[str, Any]) -> object:
    value = data.get("comparison_target_path")
    legacy = data.get("comparison_target")
    if value is None:
        return legacy
    if legacy is not None and str(value) != str(legacy):
        raise ValueError(
            "comparison_target_path and comparison_target disagree: "
            f"{value!r} != {legacy!r}"
        )
    return value


def _missing_fields(
    data: dict[str, Any], fields: tuple[str, ...], comparison_target_path_value: object
) -> list[str]:
    missing = []
    for field_name in fields:
        if field_name in data:
            continue
        if field_name == "comparison_target_path" and comparison_target_path_value is not None:
            continue
        missing.append(field_name)
    return missing


def _benchmark_paths(
    data: dict[str, Any], benchmark_status: str, comparison_target_path_value: object
) -> tuple[str | None, str | None, str | None]:
    if benchmark_status != "passed":
        return (
            optional_str(data.get("perf_artifact")),
            optional_str(comparison_target_path_value),
            optional_str(data.get("effective_metric_source")),
        )
    missing = _missing_fields(data, _BENCHMARK_REQUIRED_FIELDS, comparison_target_path_value)
    if missing:
        raise ValueError(
            "missing required benchmark round-state fields: " + ", ".join(missing)
        )
    return (
        str(data["perf_artifact"]),
        str(comparison_target_path_value),
        str(data["effective_metric_source"]),
    )


def _round_statuses(data: dict[str, Any]) -> tuple[str, str]:
    return (
        _validated_status_value(
            "correctness_status",
            data["correctness_status"],
            allowed_values=_ALLOWED_CORRECTNESS_STATUS_VALUES,
        ),
        _validated_status_value(
            "benchmark_status",
            data["benchmark_status"],
            allowed_values=_ALLOWED_BENCHMARK_STATUS_VALUES,
        ),
    )


def load_round_state(round_dir: Path) -> RoundState:
    round_state_path = round_dir / "round-state.json"
    data = load_json_object(round_state_path, display_name="round-state.json")
    comparison_target_path_value = _resolve_comparison_target_value(data)
    missing_fields = _missing_fields(data, ROUND_STATE_REQUIRED_FIELDS, comparison_target_path_value)
    if missing_fields:
        raise ValueError("missing required round-state fields: " + ", ".join(missing_fields))

    correctness_status, benchmark_status = _round_statuses(data)
    perf_artifact, comparison_target_path, effective_metric_source = _benchmark_paths(
        data, benchmark_status, comparison_target_path_value
    )

    return RoundState(
        round_name=str(data["round"]),
        parent_round=str(data["parent_round"]),
        hypothesis=str(data["hypothesis"]),
        correctness_status=correctness_status,
        benchmark_status=benchmark_status,
        perf_artifact=perf_artifact,
        comparison_target_path=comparison_target_path,
        effective_metric_source=effective_metric_source,
        summary_path=str(data["summary_path"]),
        opt_note_updated=bool(data["opt_note_updated"]),
        analysis_skipped_reason=optional_str(data.get("analysis_skipped_reason")),
        profile_dir=optional_str(data.get("profile_dir")),
        ir_dir=optional_str(data.get("ir_dir")),
        perf_analysis_path=optional_str(data.get("perf_analysis_path")),
    )


def _load_round_state_or_none(round_dir: Path, round_state_path: Path | None) -> RoundState | None:
    if round_state_path is None:
        return None
    try:
        return load_round_state(round_dir)
    except ValueError:
        return None


def _summary_issues(
    state: RoundState | None, declared_summary: str | None, summary_path: Path | None
) -> list[str]:
    if summary_path is None:
        return [
            missing_path_issue(
                "summary_path",
                declared_summary,
                expected_path="summary.md",
            )
        ]
    name_mismatch = declared_summary is not None and Path(declared_summary).name != summary_path.name
    if state is not None and name_mismatch:
        return [
            unexpected_path_name_issue(
                "summary_path",
                declared_summary,
                expected_name="summary.md",
            )
        ]
    return []


def _perf_issues(
    state: RoundState | None,
    declared_perf: str | None,
    perf_path: Path | None,
    expected_perf_name: str,
) -> list[str]:
    if perf_path is None and (state is None or state.benchmark_status == "passed"):
        return [
            missing_path_issue(
                "perf_artifact",
                declared_perf,
                expected_path=expected_perf_name,
            )
        ]
    name_mismatch = (
        declared_perf is not None
        and perf_path is not None
        and Path(declared_perf).name != perf_path.name
    )
    if state is not None and name_mismatch:
        return [
            unexpected_path_name_issue(
                "perf_artifact",
                declared_perf,
                expected_name=expected_perf_name,
            )
        ]
    return []


def _operator_issues(operator_path: Path | None, expected_operator_name: str) -> list[str]:
    if operator_path is None:
        return [f"missing {expected_operator_name}"]
    if is_ascendc_api(operator_path) and not ascendc_source_path(operator_path).is_file():
        return [f"missing AscendC source: {ascendc_source_path(operator_path).name}"]
    return []


class _RoundArtifactPaths(NamedTuple):
    declared_summary: str | None
    declared_perf: str | None
    declared_analysis: str | None
    summary_path: Path | None
    perf_path: Path | None
    perf_analysis_path: Path | None


def _resolve_round_artifact_paths(
    round_dir: Path, workspace: Path, state: RoundState | None
) -> _RoundArtifactPaths:
    declared_summary = state.summary_path if state is not None else None
    declared_perf = state.perf_artifact if state is not None else None
    declared_analysis = state.perf_analysis_path if state is not None else None

    if state is None:
        summary_path = None
        perf_path = None
        perf_analysis_path = None
    else:
        summary_path = declared_state_file(round_dir, workspace, declared_summary)
        perf_path = declared_state_file(round_dir, workspace, declared_perf)
        perf_analysis_path = declared_state_file(round_dir, workspace, declared_analysis)

    if summary_path is None:
        summary_path = existing_file(round_dir / "summary.md")
    if perf_path is None:
        perf_path = resolve_round_perf_file(round_dir)
    return _RoundArtifactPaths(
        declared_summary=declared_summary,
        declared_perf=declared_perf,
        declared_analysis=declared_analysis,
        summary_path=summary_path,
        perf_path=perf_path,
        perf_analysis_path=perf_analysis_path,
    )


def inspect_round_artifacts(round_dir: Path) -> RoundArtifactsInspection:
    workspace = round_dir.parent
    attempts_path = existing_file(round_dir / "attempts.md")
    round_state_path = existing_file(round_dir / "round-state.json")
    state = _load_round_state_or_none(round_dir, round_state_path)

    paths = _resolve_round_artifact_paths(round_dir, workspace, state)
    summary_path = paths.summary_path
    perf_path = paths.perf_path
    perf_analysis_path = paths.perf_analysis_path

    expected_operator_name_value, expected_perf_name_value = _expected_round_artifact_names(workspace)
    try:
        operator_path = resolve_round_operator_file(round_dir)
    except ValueError as exc:
        operator_path = None
        issues = [str(exc)]
    else:
        issues = []

    if attempts_path is None:
        issues.append("missing attempts.md")
    issues.extend(_summary_issues(state, paths.declared_summary, summary_path))
    if round_state_path is None:
        issues.append("missing round-state.json")
    issues.extend(_perf_issues(state, paths.declared_perf, perf_path, expected_perf_name_value))
    if paths.declared_analysis is not None and perf_analysis_path is None:
        issues.append(
            missing_path_issue(
                "perf_analysis_path",
                paths.declared_analysis,
                expected_path="perf-analysis.md",
            )
        )
    issues.extend(_operator_issues(operator_path, expected_operator_name_value))

    return RoundArtifactsInspection(
        round_dir=round_dir,
        operator_path=operator_path,
        attempts_path=attempts_path,
        summary_path=summary_path,
        perf_path=perf_path,
        perf_analysis_path=perf_analysis_path,
        round_state_path=round_state_path,
        issues=tuple(issues),
    )


def is_completed_round_directory(round_dir: Path) -> bool:
    if not round_dir.is_dir():
        return False
    name = round_dir.name
    if not name.startswith("opt-round-"):
        return False
    suffix = name[len("opt-round-"):]
    if not suffix.isdigit():
        return False

    inspection, round_state, _state_error = _inspect_round_minimum_artifact_package(round_dir)
    if inspection.issues or round_state is None:
        return False

    return (
        round_state.correctness_status == "passed"
        and round_state.benchmark_status == "passed"
    )


def is_terminal_round_directory(round_dir: Path) -> bool:
    if not round_dir.is_dir():
        return False
    name = round_dir.name
    if not name.startswith("opt-round-"):
        return False
    suffix = name[len("opt-round-"):]
    if not suffix.isdigit():
        return False

    inspection, round_state, _state_error = _inspect_round_minimum_artifact_package(round_dir)
    return not inspection.issues and round_state is not None


def iter_terminal_round_directories(workspace: Path) -> tuple[Path, ...]:
    return tuple(
        path
        for path in sorted(workspace.glob("opt-round-*"))
        if is_terminal_round_directory(path)
    )


def count_terminal_round_directories(workspace: Path) -> int:
    return len(iter_terminal_round_directories(workspace))


def iter_completed_round_directories(workspace: Path) -> tuple[Path, ...]:
    return tuple(
        path
        for path in sorted(workspace.glob("opt-round-*"))
        if is_completed_round_directory(path)
    )


def count_completed_round_directories(workspace: Path) -> int:
    return len(iter_completed_round_directories(workspace))


def best_completed_round_geomean_speedup(workspace: Path) -> float | None:
    baseline = load_baseline_state(workspace)
    baseline_perf_path = declared_state_file(
        baseline_dir(workspace),
        workspace,
        baseline.perf_artifact,
    )
    if baseline_perf_path is None:
        raise ValueError(
            "baseline perf artifact is missing: "
            f"{baseline.perf_artifact}"
        )
    validate_baseline_perf_for_speedup(baseline_perf_path)

    best_speedup: float | None = None
    for round_dir in iter_completed_round_directories(workspace):
        try:
            geomean_speedup = compute_round_geomean_speedup(
                round_dir,
                baseline_perf_path=baseline_perf_path,
            )
        except (KeyError, OSError, TypeError, ValueError):
            # A completed round can be an intentionally abandoned branch or can
            # contain a benchmark error record. It remains terminal history, but
            # it cannot contribute to historical best-speedup ranking.
            continue
        if geomean_speedup is None:
            continue
        if best_speedup is None or geomean_speedup > best_speedup:
            best_speedup = geomean_speedup
    return best_speedup


def _validated_status_value(
    field_name: str,
    raw_value: object,
    *,
    allowed_values: frozenset[str],
) -> str:
    value = str(raw_value)
    if value not in allowed_values:
        allowed_text = ", ".join(sorted(allowed_values))
        raise ValueError(f"round-state {field_name} must be one of: {allowed_text}")
    return value


def _min_speedup_pending_prefix(
    *,
    best_speedup: float | None,
    min_speedup: float | None,
) -> str:
    if min_speedup is None:
        return "round check passed. "
    if best_speedup is None:
        return (
            "round check passed. Minimum speedup target cannot yet be evaluated "
            "because no completed round has comparable performance data. "
        )
    return (
        "round check passed. "
        f"Minimum speedup target not yet satisfied: best completed-round geomean speedup "
        f"is {best_speedup:.2f}x (target {min_speedup:.2f}x). "
    )


def _ledger_operator_matches(record: dict[str, Any], operator_path: Path | None) -> bool:
    if operator_path is None:
        return False
    recorded_path = record.get("operator_file")
    recorded_hash = record.get("operator_sha256")
    matches = (
        isinstance(recorded_path, str)
        and Path(recorded_path).resolve() == operator_path.resolve()
        and isinstance(recorded_hash, str)
        and operator_sha256(operator_path) == recorded_hash
    )
    return matches


def _has_baseline_integrity(workflow_state_path: Path) -> bool:
    """Gate on the private baseline integrity payload; legacy sessions lack it."""
    workflow_payload = load_json_object(
        workflow_state_path,
        display_name=".helix/state.json",
    )
    baseline_private = workflow_payload.get("baseline")
    if not isinstance(baseline_private, dict):
        # Legacy workflow states predate managed evidence.
        return False
    baseline_integrity = cast(dict[str, Any], baseline_private).get("integrity")
    return isinstance(baseline_integrity, dict)


def _managed_round_records(
    records: list[dict[str, Any]], round_name: str
) -> list[dict[str, Any]]:
    # Screening runs recorded with full_execution=False (run-bench
    # --fast-probe) never satisfy the required evidence; legacy records
    # without the field count as full executions.
    managed = []
    for item in records:
        if item.get("status") != "passed":
            continue
        if item.get("integrity_status") != "passed":
            continue
        if item.get("round") != round_name:
            continue
        if item.get("full_execution", True) is not True:
            continue
        managed.append(item)
    return managed


def _comparison_target_is_canonical(
    item: dict[str, Any],
    canonical_baseline_perf_path: Path,
    canonical_baseline_perf_hash: object,
) -> bool:
    # A record explicitly marked as a custom comparison is never canonical.
    if item.get("comparison_kind") is not None:
        return False
    # Records written before comparison-target provenance was added
    # implicitly used the canonical baseline and remain compatible.
    raw_path = item.get("comparison_target_path")
    raw_hash = item.get("comparison_target_sha256")
    if raw_path is None and raw_hash is None:
        return True
    if not isinstance(raw_path, str) or not isinstance(raw_hash, str):
        # Partially-populated provenance is rejected, never silently
        # defaulted to the canonical values.
        return False
    if Path(raw_path).resolve() != canonical_baseline_perf_path:
        return False
    if canonical_baseline_perf_hash is None:
        # Integrity recorded no baseline hash (perf absent at baseline
        # submit); path identity is the only checkable canonical binding.
        return True
    return raw_hash == canonical_baseline_perf_hash


def _perf_evidence_matches(
    managed_records: list[dict[str, Any]],
    *,
    expected_perf_path: Path,
    integrity: dict[str, Any],
    operator_path: Path | None,
) -> list[dict[str, Any]]:
    canonical_baseline_perf_path = Path(str(integrity["baseline_perf_file"])).resolve()
    canonical_baseline_perf_hash = integrity.get("baseline_perf_sha256")
    matches = []
    for item in managed_records:
        if item.get("artifact_kind") != "perf":
            continue
        artifact_path = item.get("artifact_path")
        if str(artifact_path if artifact_path is not None else "") != str(expected_perf_path):
            continue
        artifact_file = Path(str(artifact_path))
        if not artifact_file.is_file():
            continue
        if not isinstance(item.get("artifact_sha256"), str):
            continue
        if sha256_file(artifact_file) != item["artifact_sha256"]:
            continue
        if item.get("baseline_perf_sha256") != integrity.get("baseline_perf_sha256"):
            continue
        if not _comparison_target_is_canonical(item, canonical_baseline_perf_path, canonical_baseline_perf_hash):
            continue
        if not _ledger_operator_matches(item, operator_path):
            continue
        matches.append(item)
    return matches


def _correctness_evidence_matches(
    managed_records: list[dict[str, Any]], operator_path: Path | None
) -> list[dict[str, Any]]:
    matches = []
    for item in managed_records:
        if item.get("artifact_kind") != "correctness":
            continue
        if not _ledger_operator_matches(item, operator_path):
            continue
        matches.append(item)
    return matches


def _check_managed_evidence_issues(
    round_dir: Path,
    round_state: RoundState,
    operator_path: Path | None,
) -> tuple[str, ...]:
    """Validate runner-written evidence without trusting round-state metadata."""
    # Step 1: locate the private workflow state; legacy sessions have no ledger.
    workflow_state_path = round_dir.parent / ".helix" / "state.json"
    if not workflow_state_path.is_file():
        return ()
    try:
        if not _has_baseline_integrity(workflow_state_path):
            return ()
        # Step 2: revalidate canonical inputs before consuming any evidence.
        integrity = validate_integrity(workflow_state_path)
        # Step 3: load only records belonging to this workflow and round.
        records = load_evidence_records(workflow_state_path, round_dir.name)
        managed_records = _managed_round_records(records, round_dir.name)
        # Step 4: require a benchmark record for the exact round artifact/operator.
        expected_perf_path = (round_dir / str(round_state.perf_artifact)).resolve()
        perf_matches = _perf_evidence_matches(
            managed_records,
            expected_perf_path=expected_perf_path,
            integrity=integrity,
            operator_path=operator_path,
        )
        # Step 5: require correctness evidence for the exact candidate hash.
        correctness_matches = _correctness_evidence_matches(managed_records, operator_path)
        # Step 6: report missing or invalid evidence to the round checker.
        issues: list[str] = []
        if not perf_matches:
            issues.append("missing managed benchmark evidence")
        if not correctness_matches:
            issues.append("missing managed correctness evidence")
        return tuple(issues)
    except (ValueError, OSError) as exc:
        return (f"managed evidence ledger validation failed: {exc}",)


def _round_artifact_gate(
    round_dir: Path,
) -> tuple[OptimizeCheckResult | None, RoundArtifactsInspection, RoundState]:
    artifact_inspection, round_state, state_error = _inspect_round_minimum_artifact_package(round_dir)
    if artifact_inspection.issues:
        return (
            build_check_result(kind="round", status="fail", issues=artifact_inspection.issues),
            artifact_inspection,
            round_state,
        )
    if state_error is not None:
        return (
            build_check_result(kind="round", status="fail", issues=(state_error,)),
            artifact_inspection,
            round_state,
        )
    if round_state is None:
        raise RuntimeError("round state is unavailable despite a passing artifact inspection")
    return None, artifact_inspection, round_state


def _round_status_gate(round_state: RoundState) -> OptimizeCheckResult | None:
    if round_state.correctness_status != "passed":
        return build_check_result(
            kind="round",
            status="fail",
            issues=(f"correctness_status={round_state.correctness_status}",),
        )
    if round_state.benchmark_status != "passed":
        return build_check_result(
            kind="round",
            status="fail",
            issues=(f"benchmark_status={round_state.benchmark_status}",),
        )
    missing_passed_fields = (
        round_state.perf_artifact is None
        or round_state.comparison_target_path is None
        or round_state.effective_metric_source is None
    )
    if missing_passed_fields:
        raise RuntimeError(
            "passed round state requires perf_artifact, comparison_target_path and effective_metric_source"
        )
    return None


def _baseline_gate_result(round_dir: Path) -> OptimizeCheckResult | None:
    baseline_issues = baseline_gate_issues(round_dir.parent)
    if not baseline_issues:
        return None
    issues = list(baseline_issues)
    comparison_dependency_issue = _comparison_target_dependency_issue(round_dir)
    if comparison_dependency_issue is not None:
        issues.append(comparison_dependency_issue)
    return build_check_result(
        kind="round",
        status="fail",
        issues=tuple(issues),
    )


def _canonical_comparison_issue(
    round_dir: Path,
    round_state: RoundState,
    baseline: object,
    baseline_perf_path: Path | None,
) -> str | None:
    comparison_target_path = declared_state_file(
        round_dir,
        round_dir.parent,
        round_state.comparison_target_path,
    )
    expected_comparison_target = None
    if baseline_perf_path is not None:
        expected_comparison_target = os.path.relpath(
            baseline_perf_path.resolve(),
            round_dir.resolve(),
        )
    if comparison_target_path is None:
        return missing_path_issue(
            "comparison_target_path",
            round_state.comparison_target_path,
            expected_path=expected_comparison_target,
        )
    if baseline_perf_path is not None and comparison_target_path.resolve() != baseline_perf_path.resolve():
        return noncanonical_path_issue(
            "comparison_target_path",
            round_state.comparison_target_path,
            expected_path=expected_comparison_target or baseline.perf_artifact,
        )
    return None


def _resolve_comparison_target(
    round_dir: Path, round_state: RoundState
) -> tuple[list[str], Path | None]:
    try:
        baseline = load_baseline_state(round_dir.parent)
        baseline_perf_path = declared_state_file(
            baseline_dir(round_dir.parent),
            round_dir.parent,
            baseline.perf_artifact,
        )
        issue = _canonical_comparison_issue(round_dir, round_state, baseline, baseline_perf_path)
        return ([issue] if issue is not None else []), baseline_perf_path
    except ValueError as exc:
        return [
            invalid_dependency_issue(
                "comparison_target_path",
                "baseline/state.json",
                str(exc),
            )
        ], None


def _comparison_target_issues(
    round_dir: Path, round_state: RoundState
) -> tuple[list[str], Path | None]:
    semantic_issues, baseline_perf_path = _resolve_comparison_target(round_dir, round_state)
    if round_state.effective_metric_source not in {"kernel", "total-op", "mixed"}:
        semantic_issues.append(
            f"effective_metric_source={round_state.effective_metric_source}"
        )
    return semantic_issues, baseline_perf_path


def _round_operator_gate(
    round_dir: Path,
    artifact_inspection: RoundArtifactsInspection,
    test_file: Path | None,
    enforce_triton_api_check: bool,
) -> OptimizeCheckResult | None:
    operator_path = artifact_inspection.operator_path
    if operator_path is None:
        expected_operator_name_value, _expected_perf_name_value = _expected_round_artifact_names(round_dir.parent)
        return build_check_result(
            kind="round",
            status="fail",
            issues=(f"missing {expected_operator_name_value}",),
        )

    # AscendC keeps its host launch path in the paired `.asc` source rather
    # than in the Python wrapper.  The Triton/TileLang source heuristic is
    # therefore not applicable to an AscendC API artifact.
    if not is_ascendc_api(operator_path):
        continuity = analyze_triton_kernel_continuity(operator_path)
        if not continuity.ok:
            return build_check_result(
                kind="round",
                status="fail",
                issues=((continuity.reason or "round operator failed Triton continuity check"),),
            )

    if not enforce_triton_api_check:
        return None
    effective_test_file = test_file
    if effective_test_file is None and is_triton_operator_source(operator_path):
        effective_test_file = _baseline_test_file(round_dir)
        if effective_test_file is None:
            return build_check_result(
                kind="round",
                status="fail",
                issues=(
                    "Triton API check failed: no usable --test-file and baseline/state.json "
                    "test_file could not be resolved",
                ),
            )
    triton_api_issues = _triton_api_check_issues(operator_path, effective_test_file)
    if triton_api_issues:
        return build_check_result(
            kind="round",
            status="fail",
            issues=triton_api_issues,
        )
    return None


def _satisfied_target_result(
    issues: tuple[str, ...], best_speedup: float, target_speedup: float
) -> OptimizeCheckResult:
    return build_check_result(
        kind="round",
        status="pass",
        issues=issues,
        summary=append_pass_issues_to_summary(
            "round check passed. "
            f"Minimum speedup target satisfied: best completed-round geomean speedup "
            f"is {best_speedup:.2f}x (target {target_speedup:.2f}x). "
            "Stop the optimize session immediately instead of opening another round.",
            issues,
        ),
        next_option=None,
    )


def _batch_pass_result(
    result: OptimizeCheckResult,
    *,
    current_round: int,
    final_round: int,
    best_speedup: float | None,
    target_speedup: float | None,
) -> OptimizeCheckResult:
    if best_speedup is not None and target_speedup is not None and best_speedup >= target_speedup:
        return _satisfied_target_result(result.issues, best_speedup, target_speedup)
    pending_prefix = _min_speedup_pending_prefix(
        best_speedup=best_speedup,
        min_speedup=target_speedup,
    )
    if current_round < final_round:
        next_round_name = f"opt-round-{current_round + 1}"
        return build_check_result(
            kind="round",
            status="pass",
            issues=result.issues,
            summary=append_pass_issues_to_summary(
                pending_prefix
                + f"Round {current_round}/{final_round} in the current worker batch is complete. "
                f"Next round: {next_round_name}. "
                f"Use the staged `triton-npu-optimize-state` skill's `start-round` subcommand "
                f"to open {next_round_name} before beginning the next round.",
                result.issues,
            ),
            next_option=next_round_name,
        )
    return build_check_result(
        kind="round",
        status="pass",
        issues=result.issues,
        summary=append_pass_issues_to_summary(
            pending_prefix
            + "This round satisfied the current worker batch target.",
            result.issues,
        ),
        next_option=None,
    )


class _RoundPassContext(NamedTuple):
    baseline_perf_path: Path | None
    optimize_target: Literal["kernel", "operator"] | None
    current_round: int | None
    final_round: int | None
    min_speedup: float | None


def _round_pass_result(
    round_dir: Path,
    round_state: RoundState,
    context: _RoundPassContext,
) -> OptimizeCheckResult:
    optimize_target = context.optimize_target
    current_round = context.current_round
    final_round = context.final_round
    min_speedup = context.min_speedup
    baseline_perf_path = context.baseline_perf_path
    runtime_warnings: list[str] = []
    if optimize_target == "kernel" and round_state.effective_metric_source in {"total-op", "mixed"}:
        runtime_warnings.append(
            "kernel optimize target fell back to "
            f"effective_metric_source={round_state.effective_metric_source}; "
            "the round may still participate in best-round selection, but review the comparison basis."
        )

    cleanup_round_profile_artifacts(round_dir)
    cleanup_round_ir_artifacts(round_dir)
    cleanup_dir_prof_artifacts(round_dir.parent)
    local_optimum_warnings: tuple[str, ...] = ()
    if baseline_perf_path is not None:
        local_optimum_warnings = collect_local_optimum_warnings(
            round_dir,
            baseline_perf_path=baseline_perf_path,
        )
    result = build_check_result(
        kind="round",
        status="pass",
        issues=(*tuple(runtime_warnings), *local_optimum_warnings),
    )

    best_speedup = None
    if min_speedup is not None:
        best_speedup = best_completed_round_geomean_speedup(round_dir.parent)
    target_speedup = min_speedup

    if current_round is not None and final_round is not None:
        return _batch_pass_result(
            result,
            current_round=current_round,
            final_round=final_round,
            best_speedup=best_speedup,
            target_speedup=target_speedup,
        )
    if target_speedup is not None and best_speedup is not None and best_speedup >= target_speedup:
        return _satisfied_target_result(result.issues, best_speedup, target_speedup)
    return result


def check_round(
    round_dir: Path,
    *,
    current_round: int | None = None,
    final_round: int | None = None,
    optimize_target: Literal["kernel", "operator"] | None = None,
    min_speedup: float | None = None,
    test_file: Path | None = None,
    enforce_triton_api_check: bool = False,
) -> OptimizeCheckResult:
    gate_result, artifact_inspection, round_state = _round_artifact_gate(round_dir)
    if gate_result is not None:
        return gate_result

    status_failure = _round_status_gate(round_state)
    if status_failure is not None:
        return status_failure

    baseline_failure = _baseline_gate_result(round_dir)
    if baseline_failure is not None:
        return baseline_failure

    semantic_issues, baseline_perf_path = _comparison_target_issues(round_dir, round_state)
    semantic_issues.extend(
        _check_managed_evidence_issues(round_dir, round_state, artifact_inspection.operator_path)
    )

    if semantic_issues:
        return build_check_result(
            kind="round",
            status="fail",
            issues=tuple(semantic_issues),
        )

    operator_failure = _round_operator_gate(
        round_dir,
        artifact_inspection,
        test_file,
        enforce_triton_api_check,
    )
    if operator_failure is not None:
        return operator_failure

    return _round_pass_result(
        round_dir,
        round_state,
        _RoundPassContext(
            baseline_perf_path=baseline_perf_path,
            optimize_target=optimize_target,
            current_round=current_round,
            final_round=final_round,
            min_speedup=min_speedup,
        ),
    )


def _triton_api_check_issues(operator_path: Path, test_file: Path | None) -> tuple[str, ...]:
    if not is_triton_operator_source(operator_path):
        return ()
    if test_file is None:
        return ("Triton API check failed: --test-file is required for a Triton round submission",)
    if not test_file.is_file():
        return (f"Triton API check failed: test file does not exist: {test_file}",)

    cli_path = _run_eval_cli_path()
    if not cli_path.is_file():
        return (f"Triton API check failed: missing staged run-eval checker command: {cli_path}",)
    try:
        completed = subprocess.run(
            [
                sys.executable,
                str(cli_path),
                "check-triton-api",
                "--operator-file",
                str(operator_path),
                "--test-file",
                str(test_file),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        return (f"Triton API check failed: unable to run checker: {exc}",)
    try:
        payload_raw: object = json.loads(completed.stdout)
    except json.JSONDecodeError:
        detail = completed.stderr.strip() or completed.stdout.strip() or "no checker output"
        return (f"Triton API check failed: checker returned invalid output: {detail}",)
    if not isinstance(payload_raw, dict):
        return ("Triton API check failed: checker returned a non-object JSON payload",)
    payload = cast(dict[str, object], payload_raw)
    issues = payload.get("issues")
    status = payload.get("status")
    if completed.returncode == 0 and status in {"pass", "not_applicable"}:
        return ()
    if isinstance(issues, list) and issues:
        typed_issues = cast(list[object], issues)
        return tuple(f"Triton API check failed: {issue}" for issue in typed_issues)
    return ("Triton API check failed without a reported issue",)


def _baseline_test_file(round_dir: Path) -> Path | None:
    workspace = round_dir.parent
    try:
        baseline = load_baseline_state(workspace)
    except ValueError:
        return None
    return declared_state_file(
        baseline_dir(workspace),
        workspace,
        baseline.test_file,
    )


def _run_eval_cli_path() -> Path:
    optimize_state_skill_dir = Path(__file__).resolve().parents[2]
    return optimize_state_skill_dir.parent / "triton-npu-run-eval" / "scripts" / "cli.py"


def resolve_round_perf_file(round_dir: Path) -> Path | None:
    workspace = round_dir.parent
    try:
        perf_name = expected_round_perf_name(workspace)
    except ValueError:
        perf_name = None
    if perf_name is not None:
        perf_path = round_dir / perf_name
        if perf_path.is_file():
            return perf_path

    perf_txt = round_dir / "perf.txt"
    if perf_txt.is_file():
        return perf_txt

    perf_files = sorted(path for path in round_dir.glob("*_perf.txt") if path.is_file())
    if len(perf_files) == 1:
        return perf_files[0]
    return None


def resolve_round_operator_file(round_dir: Path) -> Path | None:
    workspace = round_dir.parent
    candidates = [
        path
        for path in sorted(round_dir.iterdir())
        if path.suffix == ".py" and path.is_file()
    ]
    opt_candidates = [path for path in candidates if path.name.startswith("opt_")]
    if len(opt_candidates) > 1:
        names = ", ".join(path.name for path in opt_candidates)
        raise ValueError(
            f"multiple round operator candidates found in {round_dir}: {names}. "
            "Keep exactly one opt_*.py candidate in the round root."
        )

    try:
        operator_name = expected_round_operator_name(workspace)
    except ValueError:
        operator_name = None
    if operator_name is not None:
        operator_path = round_dir / operator_name
        if operator_path.is_file():
            return operator_path

    try:
        legacy_operator_name = resolve_workspace_operator_file(workspace).name
    except ValueError:
        legacy_operator_name = None
    if legacy_operator_name is not None:
        legacy_operator_path = round_dir / legacy_operator_name
        if legacy_operator_path.is_file():
            return legacy_operator_path

    if len(opt_candidates) == 1:
        return opt_candidates[0]
    if len(candidates) == 1:
        return candidates[0]
    if candidates:
        return candidates[0]
    return None


def _inspect_round_minimum_artifact_package(
    round_dir: Path,
) -> tuple[RoundArtifactsInspection, RoundState | None, str | None]:
    artifact_inspection = inspect_round_artifacts(round_dir)
    if artifact_inspection.issues:
        return artifact_inspection, None, None
    try:
        return artifact_inspection, load_round_state(round_dir), None
    except ValueError as exc:
        return artifact_inspection, None, str(exc)


def _expected_round_artifact_names(workspace: Path) -> tuple[str, str]:
    try:
        return expected_round_operator_name(workspace), expected_round_perf_name(workspace)
    except ValueError:
        return "opt_<operator>.py", "opt_<operator>_perf.txt"
