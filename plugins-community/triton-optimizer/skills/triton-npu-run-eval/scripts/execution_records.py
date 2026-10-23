# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Write execution facts for optional optimize workflow consumers."""

from __future__ import annotations

import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
from typing import Iterator, cast


LEDGER_SCHEMA_VERSION = 1
BASELINE_EVIDENCE_SCHEMA_VERSION = 1


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def operator_sha256(path: Path) -> str:
    """Hash one operator artifact, including an AscendC API/source pair."""
    resolved = path.resolve()
    if not _is_ascendc_api(resolved):
        return sha256_file(resolved)
    digest = hashlib.sha256()
    digest.update(b"helix-ascendc-operator-v1\0")
    for source in (resolved, resolved.with_suffix(".asc")):
        if not source.is_file():
            digest.update(source.suffix.encode("ascii") + b"\0missing\0")
            continue
        content = source.read_bytes()
        digest.update(source.suffix.encode("ascii") + b"\0")
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return f"sha256:{digest.hexdigest()}"


def active_state_path(*paths: Path) -> Path | None:
    """Find an optional optimize workflow state without loading its skill."""
    roots = [Path.cwd().resolve(), *(path.resolve().parent for path in paths)]
    for candidate in _walk_state_candidates(roots):
        if candidate.is_file():
            return candidate
    return None


def _walk_state_candidates(roots: list[Path]) -> Iterator[Path]:
    """Yield .helix/state.json candidates from each root upward, deduplicated."""
    seen: set[Path] = set()
    for root in roots:
        for directory in (root, *root.parents):
            if directory in seen:
                continue
            seen.add(directory)
            yield directory / ".helix" / "state.json"


def load_state(path: Path) -> dict[str, object] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return cast(dict[str, object], payload) if isinstance(payload, dict) else None


def record_generated_file(state_path: Path, *, role: str, path: Path) -> dict[str, object]:
    """Record an evaluation-produced baseline artifact for state validation."""
    state = _require_state(state_path)
    integrity = _require_integrity(state)
    resolved = path.resolve()
    if not resolved.is_file():
        raise ValueError(f"generated managed {role} does not exist: {resolved}")
    integrity[role] = str(resolved)
    integrity[role.replace("_file", "_sha256")] = sha256_file(resolved)
    status_key = f"{role[:-5]}_status" if role.endswith("_file") else f"{role}_status"
    integrity[status_key] = "recorded"
    _write_state(state_path, state)
    return integrity


def ensure_reference_result(state_path: Path, path: Path) -> None:
    """Record the first reference artifact and reject conflicting later inputs."""
    integrity = _require_integrity(_require_state(state_path))
    resolved = path.resolve()
    recorded = integrity.get("reference_result_file")
    recorded_hash = integrity.get("reference_result_sha256")
    if recorded is None:
        record_generated_file(state_path, role="reference_result_file", path=resolved)
        return
    if (
        resolved != Path(str(recorded))
        or not isinstance(recorded_hash, str)
        or sha256_file(resolved) != recorded_hash
    ):
        raise ValueError(
            f"managed integrity mismatch for reference_result_file: {resolved}. "
            "Restore the runner-owned original reference result and retry."
        )


def validate_managed_path(
    state_path: Path,
    *,
    role: str,
    supplied: Path,
) -> dict[str, object]:
    """Reject a command input that differs from the active round's pinned file."""
    state = _require_state(state_path)
    integrity = _require_integrity(state)
    expected_path = integrity.get(role)
    expected_hash = integrity.get(role.replace("_file", "_sha256"))
    resolved = supplied.resolve()
    actual_hash = operator_sha256(resolved) if role == "baseline_operator_file" else sha256_file(resolved)
    path_matches = isinstance(expected_path, str) and resolved == Path(expected_path)
    hash_matches = isinstance(expected_hash, str) and actual_hash == expected_hash
    if not (path_matches and hash_matches):
        _mark_stale(state_path, state, integrity)
        recovery = _create_recovery_copy(state_path, integrity, role)
        suffix = f" Recovery copy: {recovery}" if recovery is not None else ""
        raise ValueError(
            f"managed integrity mismatch for {role}: received {resolved}; expected {expected_path}. "
            f"Restore the canonical file and retry.{suffix}"
        )
    return integrity


def _validate_evidence_inputs(
    artifact_kind: str,
    artifact_path: Path | None,
    comparison_target_path: Path | None,
    comparison_operator_path: Path | None,
    custom_baseline: bool,
) -> None:
    if custom_baseline:
        has_comparison_inputs = (
            artifact_path is not None
            or comparison_target_path is not None
            or comparison_operator_path is not None
        )
        if has_comparison_inputs:
            raise ValueError(
                "custom-baseline evidence records only the execution fact; "
                "pass no artifact or comparison inputs"
            )
    elif artifact_path is None and artifact_kind != "correctness":
        raise ValueError("managed evidence artifact is required")
    if artifact_path is not None and not artifact_path.is_file():
        raise ValueError(f"managed evidence artifact does not exist: {artifact_path}")


def _build_evidence_record(
    integrity: dict[str, object],
    *,
    round_name: str,
    command: str,
    mode: str,
    artifact_kind: str,
    remote: bool,
    full_execution: bool,
    custom_baseline: bool,
    operator_path: Path,
) -> dict[str, object]:
    record: dict[str, object] = {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "round": round_name,
        "command": command,
        "artifact_kind": artifact_kind,
        "mode": mode,
        "status": "passed",
        "remote": remote,
        "full_execution": full_execution,
        "integrity_status": integrity.get("status"),
        "operator_file": str(operator_path.resolve()),
        "operator_sha256": operator_sha256(operator_path),
        "recorded_at": _utc_now(),
    }
    if custom_baseline:
        # A custom comparison contributes nothing to the round gate; record only
        # the execution fact, with no canonical snapshot or comparison provenance.
        record["comparison_kind"] = "custom-baseline"
    else:
        record["baseline_operator_file"] = integrity.get("baseline_operator_file")
        record["baseline_operator_sha256"] = integrity.get("baseline_operator_sha256")
        record["baseline_perf_file"] = integrity.get("baseline_perf_file")
        record["baseline_perf_sha256"] = integrity.get("baseline_perf_sha256")
    return record


def append_evidence(
    state_path: Path,
    *,
    round_name: str,
    command: str,
    mode: str,
    artifact_kind: str,
    artifact_path: Path | None,
    operator_path: Path,
    remote: bool,
    full_execution: bool = True,
    comparison_target_path: Path | None = None,
    comparison_operator_path: Path | None = None,
    custom_baseline: bool = False,
) -> dict[str, object]:
    """Append an execution fact; optimize-state validates it before consuming it."""
    state = _require_state(state_path)
    integrity = _require_integrity(state)
    _validate_evidence_inputs(
        artifact_kind,
        artifact_path,
        comparison_target_path,
        comparison_operator_path,
        custom_baseline,
    )
    record = _build_evidence_record(
        integrity,
        round_name=round_name,
        command=command,
        mode=mode,
        artifact_kind=artifact_kind,
        remote=remote,
        full_execution=full_execution,
        custom_baseline=custom_baseline,
        operator_path=operator_path,
    )
    if artifact_path is not None:
        record["artifact_path"] = str(artifact_path.resolve())
        record["artifact_sha256"] = sha256_file(artifact_path)
    _record_comparison_paths(record, comparison_target_path, comparison_operator_path)
    ledger_path = state_path.parent / "evidence" / f"{round_name}.jsonl"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, sort_keys=True) + "\n")
    return record


def append_baseline_evidence(
    *,
    command: str,
    artifact_kind: str,
    status: str,
    return_code: int,
    operator_path: Path,
    remote: bool,
    test_file: Path | None = None,
    bench_file: Path | None = None,
    artifact_path: Path | None = None,
    full_execution: bool = True,
) -> dict[str, object]:
    """Append one baseline evaluation fact without requiring optimize state."""
    if command not in {"run-test-baseline", "run-bench-baseline"}:
        raise ValueError(f"unsupported baseline evidence command: {command}")
    if artifact_kind not in {"correctness", "perf"}:
        raise ValueError(f"unsupported baseline evidence artifact kind: {artifact_kind}")
    if status not in {"passed", "failed"}:
        raise ValueError(f"unsupported baseline evidence status: {status}")
    if not operator_path.is_file():
        raise ValueError(f"baseline evidence operator does not exist: {operator_path}")
    if (test_file is None) == (bench_file is None):
        raise ValueError("baseline evidence requires exactly one harness input")
    harness_key = "test_file" if test_file is not None else "bench_file"
    harness_path = (test_file if test_file is not None else bench_file)
    if harness_path is None:
        raise RuntimeError("baseline evidence harness input invariant violated")
    if not harness_path.is_file():
        raise ValueError(f"baseline evidence {harness_key} does not exist: {harness_path}")
    if status == "passed" and artifact_kind == "perf" and artifact_path is None:
        raise ValueError("passed baseline benchmark evidence requires a perf artifact")
    if artifact_path is not None and not artifact_path.is_file():
        raise ValueError(f"baseline evidence artifact does not exist: {artifact_path}")

    record: dict[str, object] = {
        "schema_version": BASELINE_EVIDENCE_SCHEMA_VERSION,
        "command": command,
        "artifact_kind": artifact_kind,
        "status": status,
        "return_code": return_code,
        "remote": remote,
        "full_execution": full_execution,
        harness_key: str(harness_path.resolve()),
        harness_key.replace("_file", "_sha256"): sha256_file(harness_path),
        "operator_file": str(operator_path.resolve()),
        "operator_sha256": operator_sha256(operator_path),
        "recorded_at": _utc_now(),
    }
    if artifact_path is not None:
        record["artifact_path"] = str(artifact_path.resolve())
        record["artifact_sha256"] = sha256_file(artifact_path)

    ledger_path = harness_path.resolve().parent / ".helix" / "evidence" / "baseline.jsonl"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, sort_keys=True) + "\n")
    return record


def _record_comparison_paths(
    record: dict[str, object],
    comparison_target_path: Path | None,
    comparison_operator_path: Path | None,
) -> None:
    """Resolve, verify, and record the optional comparison provenance paths."""
    if comparison_target_path is not None:
        resolved_comparison_target = comparison_target_path.resolve()
        if not resolved_comparison_target.is_file():
            raise ValueError(
                f"managed evidence comparison target does not exist: {resolved_comparison_target}"
            )
        record["comparison_target_path"] = str(resolved_comparison_target)
        record["comparison_target_sha256"] = sha256_file(resolved_comparison_target)
    if comparison_operator_path is not None:
        resolved_comparison_operator = comparison_operator_path.resolve()
        if not resolved_comparison_operator.is_file():
            raise ValueError(
                f"managed evidence comparison operator does not exist: {resolved_comparison_operator}"
            )
        record["comparison_operator_path"] = str(resolved_comparison_operator)
        record["comparison_operator_sha256"] = operator_sha256(resolved_comparison_operator)


def _is_ascendc_api(path: Path) -> bool:
    if path.suffix != ".py" or not path.is_file():
        return False
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError):
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(alias.name == "ascendc_ops" for alias in node.names):
            return True
        if isinstance(node, ast.ImportFrom) and node.module == "ascendc_ops":
            return True
    return False


def _require_state(state_path: Path) -> dict[str, object]:
    state = load_state(state_path)
    if state is None:
        raise ValueError(f"invalid workflow state: {state_path}")
    return state


def _require_integrity(state: dict[str, object]) -> dict[str, object]:
    baseline = state.get("baseline")
    if not isinstance(baseline, dict):
        raise ValueError("workflow state baseline must be an object")
    integrity = cast(dict[str, object], baseline).get("integrity")
    if not isinstance(integrity, dict):
        raise ValueError("workflow state baseline integrity is missing")
    return cast(dict[str, object], integrity)


def _mark_stale(state_path: Path, state: dict[str, object], integrity: dict[str, object]) -> None:
    if integrity.get("status") == "stale":
        return
    integrity["status"] = "stale"
    _write_state(state_path, state)


def _create_recovery_copy(
    state_path: Path,
    integrity: dict[str, object],
    role: str,
) -> Path | None:
    source_name = {
        "test_file": "test.py",
        "bench_file": "bench.py",
        "baseline_operator_file": "baseline_operator.py",
        "baseline_perf_file": "baseline_perf.txt",
        "reference_result_file": "reference_result.pt",
    }.get(role)
    originals_dir = integrity.get("originals_dir")
    if source_name is None or not isinstance(originals_dir, str):
        return None
    source = Path(originals_dir) / source_name
    if not source.is_file():
        return None
    expected = integrity.get(role)
    display_name = Path(expected).name if isinstance(expected, str) else source_name
    target = state_path.parent.parent / "baseline-recovery" / f"{display_name}.original"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    if role == "baseline_operator_file":
        ascendc_source = Path(originals_dir) / "baseline_operator.asc"
        if ascendc_source.is_file():
            recovery_name = f"{Path(display_name).with_suffix('.asc').name}.original"
            shutil.copy2(ascendc_source, target.with_name(recovery_name))
    return target


def _write_state(path: Path, state: dict[str, object]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
