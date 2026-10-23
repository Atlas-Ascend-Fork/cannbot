# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Runner-owned optimize evaluation integrity and evidence ledger helpers."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any, Optional, cast

from shared.ascendc_operator_files import ascendc_source_path, is_ascendc_api, is_ascendc_operator


INTEGRITY_SCHEMA_VERSION = 1
LEDGER_SCHEMA_VERSION = 1


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def operator_sha256(path: Path) -> str:
    """Hash one operator artifact, treating an AscendC API/source pair as one value."""
    if not is_ascendc_api(path):
        return sha256_file(path)
    digest = hashlib.sha256()
    digest.update(b"helix-ascendc-operator-v1\0")
    ascendc_source = ascendc_source_path(path)
    for source in (path, ascendc_source):
        if not source.is_file():
            digest.update(source.suffix.encode("ascii") + b"\0missing\0")
            continue
        content = source.read_bytes()
        digest.update(source.suffix.encode("ascii") + b"\0")
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return f"sha256:{digest.hexdigest()}"


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"missing managed integrity state: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid managed integrity state: {path}: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"managed integrity state must be an object: {path}")
    return cast(dict[str, Any], payload)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _resolve_declared_path(baseline_state_path: Path, value: object) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError("baseline state contains an empty path field")
    path = Path(value).expanduser()
    if path.is_absolute():
        return path.resolve()
    baseline_relative = baseline_state_path.parent / path
    if baseline_relative.is_file():
        return baseline_relative.resolve()
    workspace_relative = baseline_state_path.parent.parent / path
    if workspace_relative.is_file():
        return workspace_relative.resolve()
    return baseline_relative.resolve()


def _baseline_inputs(baseline_state_path: Path) -> dict[str, Path]:
    payload = _load_json(baseline_state_path)
    inputs = {
        "test_file": _resolve_declared_path(baseline_state_path, payload.get("test_file")),
        "bench_file": _resolve_declared_path(baseline_state_path, payload.get("bench_file")),
        "baseline_operator_file": _resolve_declared_path(
            baseline_state_path, payload.get("baseline_operator")
        ),
        "baseline_perf_file": _resolve_declared_path(
            baseline_state_path, payload.get("perf_artifact")
        ),
    }
    operator = inputs["baseline_operator_file"]
    if is_ascendc_operator(operator):
        inputs["baseline_ascendc_source_file"] = ascendc_source_path(operator)
    return inputs


def _require_regular_files(paths: dict[str, Path], *, allow_missing: set[str] | None = None) -> None:
    allowed = allow_missing or set()
    for role, path in paths.items():
        if role not in allowed and not path.is_file():
            raise ValueError(f"canonical {role} does not exist: {path}")


def _originals_dir(state_path: Path) -> Path:
    return state_path.parent / "eval" / "originals"


def _copy_originals(paths: dict[str, Path], target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    for role, source in paths.items():
        target = target_dir / {
            "test_file": "test.py",
            "bench_file": "bench.py",
            "baseline_operator_file": "baseline_operator.py",
            "baseline_perf_file": "baseline_perf.txt",
            "baseline_ascendc_source_file": "baseline_operator.asc",
        }[role]
        shutil.copy2(source, target)
        if sha256_file(target) != sha256_file(source):
            raise ValueError(f"managed original copy verification failed: {target}")


def initialize_baseline_integrity(
    workflow_state_path: Path,
    *,
    reference_result: Optional[Path] = None,
) -> dict[str, Any]:
    """Record canonical baseline inputs and create runner-owned recovery copies."""
    state = _load_json(workflow_state_path)
    baseline_state_path = workflow_state_path.parent.parent / "baseline" / "state.json"
    paths = _baseline_inputs(baseline_state_path)
    _require_regular_files(paths, allow_missing={"baseline_perf_file"})
    originals_dir = _originals_dir(workflow_state_path)
    _copy_originals({key: value for key, value in paths.items() if value.is_file()}, originals_dir)
    integrity: dict[str, Any] = {
        "schema_version": INTEGRITY_SCHEMA_VERSION,
        "status": "passed",
        "test_file": str(paths["test_file"]),
        "test_sha256": sha256_file(paths["test_file"]),
        "bench_file": str(paths["bench_file"]),
        "bench_sha256": sha256_file(paths["bench_file"]),
        "baseline_operator_file": str(paths["baseline_operator_file"]),
        "baseline_operator_sha256": operator_sha256(paths["baseline_operator_file"]),
        "baseline_perf_file": str(paths["baseline_perf_file"]),
        "baseline_perf_sha256": (
            sha256_file(paths["baseline_perf_file"])
            if paths["baseline_perf_file"].is_file()
            else None
        ),
        "baseline_perf_status": "recorded" if paths["baseline_perf_file"].is_file() else "missing",
        "originals_dir": str(originals_dir.resolve()),
        "recorded_at": utc_now(),
    }
    if reference_result is not None and reference_result.is_file():
        resolved_reference = reference_result.resolve()
        integrity["reference_result_file"] = str(resolved_reference)
        integrity["reference_result_sha256"] = sha256_file(resolved_reference)
        integrity["reference_result_status"] = "recorded"
        shutil.copy2(resolved_reference, originals_dir / "reference_result.pt")
    else:
        integrity["reference_result_status"] = "not-retained"

    baseline_obj = state.get("baseline")
    if not isinstance(baseline_obj, dict):
        raise ValueError("workflow state baseline must be an object")
    baseline = cast(dict[str, Any], baseline_obj)
    baseline["integrity"] = integrity
    _write_json(workflow_state_path, state)
    return integrity


def load_integrity(workflow_state_path: Path) -> dict[str, Any]:
    state = _load_json(workflow_state_path)
    baseline_obj = state.get("baseline")
    if not isinstance(baseline_obj, dict):
        raise ValueError("workflow state baseline must be an object")
    baseline = cast(dict[str, Any], baseline_obj)
    integrity = baseline.get("integrity")
    if not isinstance(integrity, dict):
        raise ValueError("workflow state baseline integrity is missing")
    return cast(dict[str, Any], integrity)


def validate_integrity(workflow_state_path: Path) -> dict[str, Any]:
    integrity = load_integrity(workflow_state_path)
    _validate_core_integrity_files(workflow_state_path, integrity)
    _validate_baseline_perf_integrity(workflow_state_path, integrity)
    _validate_reference_result_integrity(workflow_state_path, integrity)
    if integrity.get("status") != "passed":
        integrity["status"] = "passed"
        state = _load_json(workflow_state_path)
        baseline = state.get("baseline")
        if isinstance(baseline, dict):
            baseline["integrity"] = integrity
            _write_json(workflow_state_path, state)
    return integrity


def _validate_core_integrity_files(workflow_state_path: Path, integrity: dict[str, Any]) -> None:
    for role in ("test_file", "bench_file", "baseline_operator_file"):
        raw_path = integrity.get(role)
        raw_hash = integrity.get(role.replace("_file", "_sha256"))
        if not isinstance(raw_path, str) or not Path(raw_path).is_absolute():
            raise ValueError(f"managed integrity {role} must be an absolute path")
        path = Path(raw_path)
        if not path.is_file():
            _raise_integrity_failure(workflow_state_path, integrity, role, f"missing: {path}")
        actual_hash = operator_sha256(path) if role == "baseline_operator_file" else sha256_file(path)
        if not isinstance(raw_hash, str) or actual_hash != raw_hash:
            _raise_integrity_failure(workflow_state_path, integrity, role, f"hash mismatch: {path}")


def _validate_baseline_perf_integrity(workflow_state_path: Path, integrity: dict[str, Any]) -> None:
    baseline_perf_raw = integrity.get("baseline_perf_file")
    if not isinstance(baseline_perf_raw, str) or not Path(baseline_perf_raw).is_absolute():
        raise ValueError("managed integrity baseline_perf_file must be an absolute path")
    baseline_perf_path = Path(baseline_perf_raw)
    baseline_perf_hash = integrity.get("baseline_perf_sha256")
    if baseline_perf_hash is None:
        return
    if not baseline_perf_path.is_file() or sha256_file(baseline_perf_path) != baseline_perf_hash:
        _raise_integrity_failure(
            workflow_state_path,
            integrity,
            "baseline_perf_file",
            f"hash mismatch: {baseline_perf_path}",
        )


def _validate_reference_result_integrity(workflow_state_path: Path, integrity: dict[str, Any]) -> None:
    reference_path = integrity.get("reference_result_file")
    reference_hash = integrity.get("reference_result_sha256")
    if reference_path is None:
        return
    if not isinstance(reference_path, str) or not Path(reference_path).is_absolute():
        raise ValueError("managed integrity reference_result_file must be absolute")
    if not Path(reference_path).is_file():
        _raise_integrity_failure(
            workflow_state_path,
            integrity,
            "reference_result_file",
            f"missing: {reference_path}",
        )
    if not isinstance(reference_hash, str) or sha256_file(Path(reference_path)) != reference_hash:
        _raise_integrity_failure(
            workflow_state_path,
            integrity,
            "reference_result_file",
            f"hash mismatch: {reference_path}",
        )


def _build_evidence_record(
    *,
    integrity: dict[str, Any],
    round_name: str,
    command: str,
    mode: str,
    artifact_kind: str,
    artifact_path: Path | None,
    operator_path: Path,
    remote: bool,
    status: str,
    record_id: str | None = None,
    metadata: dict[str, object] | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "round": round_name,
        "command": command,
        "artifact_kind": artifact_kind,
        "mode": mode,
        "status": status,
        "remote": remote,
        "integrity_status": integrity.get("status"),
        "operator_file": str(operator_path.resolve()),
        "operator_sha256": operator_sha256(operator_path),
        "baseline_operator_file": integrity["baseline_operator_file"],
        "baseline_operator_sha256": integrity["baseline_operator_sha256"],
        "baseline_perf_file": integrity["baseline_perf_file"],
        "baseline_perf_sha256": integrity["baseline_perf_sha256"],
        "recorded_at": utc_now(),
    }
    if artifact_path is not None:
        record["artifact_path"] = str(artifact_path.resolve())
        record["artifact_sha256"] = sha256_file(artifact_path)
    if record_id is not None:
        record["record_id"] = record_id
    if metadata is not None:
        record["metadata"] = metadata
    return record


def _evidence_ledger_path(workflow_state_path: Path, *, round_name: str) -> Path:
    return workflow_state_path.parent / "evidence" / f"{round_name}.jsonl"


def _normalize_evidence_metadata(metadata: object) -> dict[str, object]:
    if not isinstance(metadata, dict):
        raise ValueError("managed evidence batch metadata must be an object")
    normalized: dict[str, object] = {}
    for key, value in cast(dict[object, object], metadata).items():
        if not isinstance(key, str) or (
            not isinstance(value, (str, int, float, bool)) and value is not None
        ):
            raise ValueError("managed evidence batch metadata must use string keys and scalar values")
        normalized[key] = value
    return normalized


def _evidence_item_fields_valid(item: dict[str, object]) -> bool:
    text_fields_valid = all(
        isinstance(item.get(key), str) and bool(item.get(key))
        for key in ("artifact_kind", "command", "mode")
    )
    return text_fields_valid and isinstance(item.get("remote"), bool)


def _prepare_evidence_record(
    integrity: dict[str, Any],
    round_name: str,
    item: dict[str, object],
) -> dict[str, Any]:
    if not _evidence_item_fields_valid(item):
        raise ValueError("managed evidence batch record has invalid fields")
    artifact_kind = item.get("artifact_kind")
    artifact_path = item.get("artifact_path")
    operator_path = item.get("operator_path")
    command = item.get("command")
    mode = item.get("mode")
    remote = item.get("remote")
    metadata = item.get("metadata", {})
    if not isinstance(artifact_path, Path) or not artifact_path.is_file():
        raise ValueError("managed evidence batch artifact does not exist")
    if not isinstance(operator_path, Path) or not operator_path.is_file():
        raise ValueError("managed evidence batch operator does not exist")
    normalized_metadata = _normalize_evidence_metadata(metadata)
    artifact_hash = sha256_file(artifact_path)
    record_id = hashlib.sha256(
        f"{round_name}\0{artifact_kind}\0{artifact_hash}\0{remote}".encode("utf-8")
    ).hexdigest()
    return _build_evidence_record(
        integrity=integrity,
        round_name=round_name,
        command=command,
        mode=mode,
        artifact_kind=artifact_kind,
        artifact_path=artifact_path,
        operator_path=operator_path,
        remote=remote,
        status="passed",
        record_id=record_id,
        metadata=normalized_metadata,
    )


def _append_new_evidence_records(
    workflow_state_path: Path,
    round_name: str,
    prepared: list[dict[str, Any]],
) -> None:
    ledger_path = _evidence_ledger_path(workflow_state_path, round_name=round_name)
    existing = load_evidence_records(workflow_state_path, round_name)
    existing_ids = {record.get("record_id") for record in existing}
    additions = [record for record in prepared if record["record_id"] not in existing_ids]
    if not additions:
        return
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = ledger_path.with_name(f".{ledger_path.name}.tmp")
    all_records = [*existing, *additions]
    temporary.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in all_records),
        encoding="utf-8",
    )
    temporary.replace(ledger_path)


def append_evidence_batch(
    workflow_state_path: Path,
    *,
    round_name: str,
    records: list[dict[str, object]],
) -> list[dict[str, Any]]:
    integrity = validate_integrity(workflow_state_path)
    prepared = [
        _prepare_evidence_record(integrity, round_name, item)
        for item in records
    ]
    _append_new_evidence_records(workflow_state_path, round_name, prepared)
    return prepared


def load_evidence_records(workflow_state_path: Path, round_name: str) -> list[dict[str, Any]]:
    ledger_path = workflow_state_path.parent / "evidence" / f"{round_name}.jsonl"
    if not ledger_path.is_file():
        return []
    records: list[dict[str, Any]] = []
    for line in ledger_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            records.append(cast(dict[str, Any], payload))
    return records


def active_state_path(*paths: Path) -> Path | None:
    """Find the nearest workflow state used by managed command entry points."""
    roots = [Path.cwd().resolve(), *(path.resolve().parent for path in paths)]
    seen: set[Path] = set()
    for root in roots:
        current = root
        while current not in seen:
            seen.add(current)
            candidate = current / ".helix" / "state.json"
            if candidate.is_file():
                return candidate
            if current.parent == current:
                break
            current = current.parent
    return None


def _raise_integrity_failure(
    workflow_state_path: Path,
    integrity: dict[str, Any],
    role: str,
    detail: str,
) -> None:
    _mark_stale(workflow_state_path, integrity)
    recovery = _create_recovery_copy(workflow_state_path, integrity, role)
    suffix = f" Recovery copy: {recovery}" if recovery is not None else ""
    raise ValueError(f"managed integrity {role} {detail}.{suffix}")


def _mark_stale(workflow_state_path: Path, integrity: dict[str, Any]) -> None:
    if integrity.get("status") == "stale":
        return
    integrity["status"] = "stale"
    state = _load_json(workflow_state_path)
    baseline = state.get("baseline")
    if isinstance(baseline, dict):
        baseline["integrity"] = integrity
        _write_json(workflow_state_path, state)


def _create_recovery_copy(
    workflow_state_path: Path,
    integrity: dict[str, Any],
    role: str,
) -> Path | None:
    originals_dir = Path(str(integrity.get("originals_dir", "")))
    source_name = {
        "test_file": "test.py",
        "bench_file": "bench.py",
        "baseline_operator_file": "baseline_operator.py",
        "baseline_perf_file": "baseline_perf.txt",
        "reference_result_file": "reference_result.pt",
    }.get(role)
    if not source_name:
        return None
    source = originals_dir / source_name
    if not source.is_file():
        return None
    expected = integrity.get(role)
    display_name = Path(str(expected)).name if isinstance(expected, str) else source_name
    target = workflow_state_path.parent.parent / "baseline-recovery" / f"{display_name}.original"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    if role == "baseline_operator_file":
        source_ascendc = originals_dir / "baseline_operator.asc"
        if source_ascendc.is_file():
            ascendc_recovery_name = f"{Path(display_name).with_suffix('.asc').name}.original"
            shutil.copy2(source_ascendc, target.with_name(ascendc_recovery_name))
    return target
