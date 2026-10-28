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

"""Freeze performance/functional case sets into one run manifest.

The selector is intentionally deterministic. Existing inventories never need an
agent or a run-specific helper script.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from workflow_backend import BACKENDS, DSL_EXECUTION_MODES, validate_backend

from cli_output import emit


RUN_SCHEMA_VERSION = 2
REQUEST_SCHEMA_VERSION = 2
SELECTION_ALGORITHM = "coverage-v1"
PERFORMANCE_LIMIT = 50
ACCEPTANCE_LIMIT = 40
GENERALIZATION_TUNING_LIMIT = 30
DEFAULT_GENERALIZATION_CASE_COUNT = 1000
TUNING_MODES = ("standard", "generalization")
FUNCTIONAL_MODES = ("reuse_performance", "existing", "generate")
GENERALIZATION_FUNCTIONAL_MODES = ("reuse_performance",)
COMPETITOR_SOURCES = ("file", "xpu-perf-benchmark")
PERFORMANCE_REFERENCE_KINDS = ("baseline", "xpu", "theoretical", "unfused", "same_npu_reference")
PRECISION_DIAGNOSIS_POLICY = "persistent"
ID_COLUMNS = ("case_id", "id", "case", "name")
LEVEL_COLUMNS = ("level", "test_level", "case_level")
IGNORED_CODE_DIRS = {".git", ".pytest_cache", "__pycache__", "build", "dist", "output", "outputs"}
CODE_SUFFIXES = {".c", ".cc", ".cpp", ".h", ".hh", ".hpp", ".py", ".sh", ".cmake", ".json", ".yaml", ".yml", ".toml"}


def _is_valid_schedule_policy(value: dict[str, Any]) -> bool:
    return (
        set(value) == {"id", "version"}
        and value.get("id") == "schedule_contract_v1"
        and type(value.get("version")) is int
        and value["version"] == 1
    )


def validate_schedule_policy(value: Any) -> dict[str, Any] | None:
    """Missing policy denotes a historical request; do not silently migrate it."""
    if value is None:
        return None
    if not isinstance(value, dict) or not _is_valid_schedule_policy(value):
        raise ValueError("unsupported schedule_policy: expected schedule_contract_v1 version 1")
    return dict(value)


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_tree(path: Path) -> str:
    digest = hashlib.sha256()
    for item in sorted(candidate for candidate in path.rglob("*") if candidate.is_file()):
        digest.update(item.relative_to(path).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256_file(item).encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


def identity(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    return {
        "path": str(resolved),
        "kind": "directory" if resolved.is_dir() else "file",
        "sha256": sha256_tree(resolved) if resolved.is_dir() else sha256_file(resolved),
    }


def code_identity(path: Path) -> dict[str, Any]:
    """Hash source/build-contract files without walking generated binaries."""
    resolved = path.resolve()
    digest = hashlib.sha256()
    count = 0
    for root, directories, files in os.walk(resolved):
        directories[:] = sorted(name for name in directories if name not in IGNORED_CODE_DIRS)
        root_path = Path(root)
        for name in sorted(files):
            item = root_path / name
            if item.suffix.lower() not in CODE_SUFFIXES and name not in ("CMakeLists.txt", "Makefile"):
                continue
            digest.update(item.relative_to(resolved).as_posix().encode("utf-8"))
            digest.update(b"\0")
            digest.update(sha256_file(item).encode("ascii"))
            digest.update(b"\0")
            count += 1
    return {
        "path": str(resolved),
        "kind": "directory",
        "sha256": digest.hexdigest(),
        "identity_method": "source-tree-v1",
        "file_count": count,
    }


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def atomic_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames:
            raise ValueError(f"CSV has no header: {path}")
        fieldnames = [str(name) for name in reader.fieldnames]
        rows = [{name: (row.get(name) or "").strip() for name in fieldnames} for row in reader]
    if not rows:
        raise ValueError(f"CSV has no cases: {path}")
    return fieldnames, rows


def inventory_csv(path: Path) -> Path:
    if path.is_file():
        return path
    for name in ("cases.csv", "manifest.csv", "functional-cases.csv"):
        candidate = path / name
        if candidate.is_file():
            return candidate
    raise ValueError(
        f"Directory inventory must contain cases.csv, manifest.csv, or functional-cases.csv: {path}"
    )


def case_id(row: dict[str, str], source_index: int) -> str:
    for key in ID_COLUMNS:
        if row.get(key):
            return row[key]
    return f"row-{source_index + 2}"


def level(row: dict[str, str]) -> str:
    for key in LEVEL_COLUMNS:
        if row.get(key):
            return row[key].upper().replace("LEVEL", "L")
    return "L0"


def shape_numbers(row: dict[str, str]) -> list[int]:
    text = " ".join(value for key, value in row.items() if "shape" in key.lower())
    return [int(value) for value in re.findall(r"(?<![\w.])-?\d+", text)]


def coverage_tags(row: dict[str, str]) -> set[str]:
    tags: set[str] = set()
    lowered = {key.lower(): value.strip().lower() for key, value in row.items() if value.strip()}
    for key, value in lowered.items():
        if any(token in key for token in ("dtype", "format", "layout", "mode", "route", "axis", "attr")):
            tags.add(f"{key}={value}")

    dims = shape_numbers(row)
    if dims:
        tags.add(f"rank={len(dims)}")
        elements = 1
        for dim in dims:
            elements *= max(dim, 0)
        scale = "small" if elements <= 2_000_000 else "medium" if elements <= 50_000_000 else "large"
        tags.add(f"scale={scale}")
        if any(dim <= 0 for dim in dims):
            tags.add("boundary=non_positive")
        if 1 in dims:
            tags.add("boundary=unit_dim")
        for alignment in (8, 16, 32):
            tags.add(
                f"align{alignment}="
                + ("aligned" if all(dim > 0 and dim % alignment == 0 for dim in dims) else "tail")
            )
    else:
        tags.add("shape=unspecified")
    tags.add(f"level={level(row)}")
    return tags


def select_rows(rows: list[dict[str, str]], limit: int) -> tuple[list[int], list[dict[str, Any]]]:
    if len(rows) <= limit:
        indices = list(range(len(rows)))
    else:
        tag_sets = [coverage_tags(row) for row in rows]
        frequency: dict[str, int] = {}
        for tags in tag_sets:
            for tag in tags:
                frequency[tag] = frequency.get(tag, 0) + 1

        uncovered = set(frequency)
        remaining = set(range(len(rows)))
        indices = []
        while remaining and len(indices) < limit:
            def score(index: int) -> tuple[float, int, str]:
                novel = tag_sets[index] & uncovered
                weighted = sum(1.0 / frequency[tag] for tag in novel)
                return (weighted, len(novel), case_id(rows[index], index))

            chosen = max(remaining, key=score)
            indices.append(chosen)
            uncovered -= tag_sets[chosen]
            remaining.remove(chosen)
        indices.sort()

    details = [
        {
            "case_id": case_id(rows[index], index),
            "source_row": index + 2,
            "coverage_tags": sorted(coverage_tags(rows[index])),
        }
        for index in indices
    ]
    return indices, details


def collection(path: Path, rows: list[dict[str, str]], selection: dict[str, Any] | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"path": str(path.resolve()), "count": len(rows), "sha256": sha256_file(path)}
    if selection is not None:
        result["selection"] = selection
    return result


def inventory_validation(fields: list[str], rows: list[dict[str, str]]) -> dict[str, Any]:
    lowered = {field.lower(): field for field in fields}
    ids = [case_id(row, index) for index, row in enumerate(rows)]
    duplicates = sorted(value for value, count in Counter(ids).items() if count > 1)
    groups = {
        "interface_fields": sorted(
            field for key, field in lowered.items() if "shape" in key or "dtype" in key or "attr" in key
        ),
        "golden_fields": sorted(
            field
            for key, field in lowered.items()
            if any(token in key for token in ("golden", "expected", "reference", "oracle"))
        ),
        "threshold_fields": sorted(
            field
            for key, field in lowered.items()
            if any(token in key for token in ("atol", "rtol", "tolerance", "threshold", "comparator"))
        ),
        "level_fields": sorted(field for key, field in lowered.items() if key in LEVEL_COLUMNS),
    }
    issues: list[str] = []
    if duplicates:
        issues.append("duplicate_case_ids")
    for key in ("interface_fields", "golden_fields", "threshold_fields"):
        if not groups.get(key):
            issues.append(f"missing_{key}")
    return {
        "status": "complete" if not issues else "needs_review",
        **groups,
        "issues": issues,
        "duplicate_case_ids": duplicates,
    }


def freeze_csv(source: Path, destination: Path) -> tuple[list[str], list[dict[str, str]]]:
    fields, rows = read_csv(source)
    atomic_csv(destination, fields, rows)
    return fields, rows


def baseline_stage_dir(output_dir: Path) -> Path:
    path = output_dir / "baseline"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _freeze_functional_directory(source: Path, destination_dir: Path) -> None:
    if source.resolve() == destination_dir.resolve():
        return
    if destination_dir.exists():
        if sha256_tree(source) != sha256_tree(destination_dir):
            raise ValueError(f"refusing to overwrite a different frozen inventory: {destination_dir}")
        return
    temporary = Path(tempfile.mkdtemp(prefix=".functional-full.", dir=destination_dir.parent))
    try:
        shutil.copytree(source, temporary, dirs_exist_ok=True)
        os.replace(temporary, destination_dir)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def _frozen_functional_directory(
    source: Path, output_dir: Path, fields: list[str], rows: list[dict[str, str]]
) -> dict[str, Any]:
    destination_dir = output_dir / "functional-full"
    _freeze_functional_directory(source, destination_dir)
    frozen_csv = inventory_csv(destination_dir)
    return {
        **identity(destination_dir),
        "count": len(rows),
        "case_manifest": str(frozen_csv.resolve()),
        "validation": inventory_validation(fields, rows),
    }


def _frozen_functional_file(
    output_dir: Path, fields: list[str], rows: list[dict[str, str]]
) -> dict[str, Any]:
    frozen_csv = output_dir / "functional-full-cases.csv"
    atomic_csv(frozen_csv, fields, rows)
    full = collection(frozen_csv, rows)
    full["validation"] = inventory_validation(fields, rows)
    return full


def _functional_acceptance(
    fields: list[str], rows: list[dict[str, str]], output_dir: Path
) -> dict[str, Any]:
    l0_pairs = [(index, row) for index, row in enumerate(rows) if level(row) == "L0"]
    if not l0_pairs:
        raise ValueError("Functional inventory contains no L0 cases")
    l0_rows = [row for _, row in l0_pairs]
    selected_local, details = select_rows(l0_rows, ACCEPTANCE_LIMIT)
    selected_rows = [l0_rows[index] for index in selected_local]
    acceptance = output_dir / "functional-acceptance-cases.csv"
    atomic_csv(acceptance, fields, selected_rows)
    acceptance_selection = {
        "algorithm": SELECTION_ALGORITHM,
        "limit": ACCEPTANCE_LIMIT,
        "source_count": len(rows),
        "l0_count": len(l0_rows),
        "selected": details,
    }
    return collection(acceptance, selected_rows, acceptance_selection)


def functional_payload(source: Path, output_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    source_csv = inventory_csv(source)
    fields, rows = read_csv(source_csv)
    if source.is_dir():
        full = _frozen_functional_directory(source, output_dir, fields, rows)
    else:
        full = _frozen_functional_file(output_dir, fields, rows)
    return full, _functional_acceptance(fields, rows, output_dir)


def generalization_payload(source: Path, output_dir: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    source_csv = inventory_csv(source)
    fields, rows = read_csv(source_csv)
    destination = output_dir / "generalization-full-cases.csv"
    atomic_csv(destination, fields, rows)
    full = collection(destination, rows)
    full["validation"] = inventory_validation(fields, rows)

    l0_rows = [row for row in rows if level(row) == "L0"]
    if not l0_rows:
        raise ValueError("Generalization inventory contains no L0 cases")
    selected, details = select_rows(l0_rows, ACCEPTANCE_LIMIT)
    acceptance_rows = [l0_rows[index] for index in selected]
    acceptance_path = output_dir / "functional-acceptance-cases.csv"
    atomic_csv(acceptance_path, fields, acceptance_rows)
    acceptance_selection = {
        "algorithm": SELECTION_ALGORITHM,
        "limit": ACCEPTANCE_LIMIT,
        "source_count": len(rows),
        "l0_count": len(l0_rows),
        "selected": details,
    }
    acceptance = collection(acceptance_path, acceptance_rows, acceptance_selection)
    functional_full = {**full, "shared_with": "generalization_full"}
    return full, functional_full, acceptance


def normalized_competitor_rows(source: Path) -> list[dict[str, str]]:
    _, rows = read_csv(source)
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, row in enumerate(rows):
        identifier = next((row.get(key) for key in ("case_id", "testcase_name") if row.get(key)), None)
        total = next((row.get(key) for key in ("gpu_total_us", "gpu_time_us") if row.get(key)), None)
        if not identifier or not total:
            raise ValueError(
                f"Competitor row {index + 2} requires case_id/testcase_name and gpu_total_us/gpu_time_us"
            )
        if identifier in seen:
            raise ValueError(f"Duplicate competitor case ID: {identifier}")
        try:
            numeric = float(total)
        except ValueError as error:
            raise ValueError(f"Invalid competitor time for {identifier}: {total}") from error
        if numeric <= 0:
            raise ValueError(f"Competitor time must be positive for {identifier}: {total}")
        seen.add(identifier)
        normalized.append({"case_id": identifier, "gpu_total_us": format(numeric, ".12g")})
    return normalized


def case_ids_from_collection(item: dict[str, Any]) -> set[str]:
    _, rows = read_csv(inventory_csv(Path(item["path"])))
    ids = [case_id(row, index) for index, row in enumerate(rows)]
    if len(ids) != len(set(ids)):
        raise ValueError("frozen collection contains duplicate case IDs")
    return set(ids)


def competitor_payload(
    source: Path,
    output_dir: Path,
    expected_case_ids: set[str] | None,
) -> dict[str, Any]:
    rows = normalized_competitor_rows(source)
    actual = {row["case_id"] for row in rows}
    if expected_case_ids is None:
        validation: dict[str, Any] = {"status": "pending_case_inventory"}
    else:
        missing = sorted(expected_case_ids - actual)
        extra = sorted(actual - expected_case_ids)
        if missing or extra:
            raise ValueError(
                "Competitor performance must exactly cover the generalization inventory: "
                f"missing={missing[:10]}, extra={extra[:10]}"
            )
        validation = {"status": "complete", "matched_count": len(actual)}
    destination = output_dir / "competitor-performance.csv"
    atomic_csv(destination, ["case_id", "gpu_total_us"], rows)
    payload = collection(destination, rows)
    payload["validation"] = validation
    return payload


def resolve_executable(value: str) -> Path:
    candidate = shutil.which(value)
    path = Path(candidate if candidate else value).expanduser().resolve()
    if not path.is_file() or not os.access(path, os.X_OK):
        raise ValueError(f"Python executable is not executable: {path}")
    return path


def python_version(executable: Path) -> str:
    result = subprocess.run(
        [str(executable), "--version"],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        raise ValueError(f"Cannot query Python version from {executable}: {result.stderr.strip()}")
    return (result.stdout or result.stderr).strip()


def cann_snapshot() -> dict[str, str | None]:
    return {
        "ASCEND_HOME_PATH": os.environ.get("ASCEND_HOME_PATH"),
        "ASCEND_OPP_PATH": os.environ.get("ASCEND_OPP_PATH"),
        "ASCEND_AICPU_PATH": os.environ.get("ASCEND_AICPU_PATH"),
    }


def _is_valid_target_ratio(ratio: Any) -> bool:
    return (
        not isinstance(ratio, bool)
        and isinstance(ratio, (int, float))
        and math.isfinite(ratio)
        and ratio > 0
    )


def validate_reference(value: dict) -> dict:
    if not isinstance(value, dict) or value.get("kind") not in PERFORMANCE_REFERENCE_KINDS:
        raise ValueError(f'performance_reference.kind must be one of {PERFORMANCE_REFERENCE_KINDS}')
    ratio = value.get("target_ratio")
    if not _is_valid_target_ratio(ratio):
        raise ValueError('target_ratio must be finite and positive (reference_us / target_us)')
    if value["kind"] == 'theoretical' and ratio > 1:
        raise ValueError('theoretical target_ratio is efficiency and cannot exceed 1')
    if value["kind"] == 'unfused' and ratio < 1:
        raise ValueError('unfused target_ratio must be >= 1')
    return value


def optimization_objective(args: argparse.Namespace) -> dict[str, Any]:
    if args.optimization_mode == "fixed_rounds":
        if args.rounds <= 0:
            raise ValueError("--rounds must be positive")
        if any(
            value is not None
            for value in (args.target_metric, args.target_value, args.target_unit, args.max_rounds)
        ):
            raise ValueError("target fields are valid only with --optimization-mode target")
        return {"mode": "fixed_rounds", "rounds": args.rounds}

    if not args.target_metric or args.target_value is None or not args.target_unit:
        raise ValueError("target mode requires --target-metric, --target-value, and --target-unit")
    if args.max_rounds is not None and args.max_rounds <= 0:
        raise ValueError("--max-rounds must be positive")
    return {
        "mode": "target",
        "metric": args.target_metric,
        "comparison": args.target_comparison,
        "value": args.target_value,
        "unit": args.target_unit,
        "max_rounds": args.max_rounds,
    }


def request_summary(request: dict[str, Any]) -> dict[str, Any]:
    return {
        "backend": request.get("backend", "ascendc"),
        "dsl": request.get("dsl"),
        "operator": request.get("operator"),
        "tuning_mode": request.get("tuning_mode", "standard"),
        "target_socs": request.get("target_socs"),
        "code_dir": request["code_dir"],
        "performance_cases": request["performance_cases"],
        "functional": request["functional"],
        "generalization": request.get("generalization"),
        "optimization_objective": request["optimization_objective"],
        "optimization_intent": request.get("optimization_intent", "safe_incremental"),
        "reference_perf": request.get("reference_perf"),
        "performance_reference": request.get("performance_reference"),
        "performance_effect_policy": request.get("performance_effect_policy"),
        "schedule_policy": request.get("schedule_policy"),
        "python": request["environments"]["python"],
        "cann": request["environments"]["cann"],
        "confirmation": request["confirmation"],
    }


def _validate_request_policies(request: dict[str, Any]) -> None:
    from performance_effect_evidence import policy
    if "performance_effect_policy" in request:
        request["performance_effect_policy"] = policy(request["performance_effect_policy"])
    if "schedule_policy" in request:
        if request["schedule_policy"] is None:
            raise ValueError("explicit null schedule_policy is invalid; historical requests omit it")
        validate_schedule_policy(request["schedule_policy"])


def _has_unique_target_socs(target_socs: Any) -> bool:
    if not isinstance(target_socs, list) or not target_socs:
        return False
    if not all(isinstance(soc, str) and soc.strip() for soc in target_socs):
        return False
    return len(set(target_socs)) == len(target_socs)


def _validate_tuning_mode(request: dict[str, Any]) -> str:
    tuning_mode = request.get("tuning_mode", "standard")
    if tuning_mode not in TUNING_MODES:
        raise ValueError(f"invalid tuning mode: {tuning_mode}")
    request["tuning_mode"] = tuning_mode
    return tuning_mode


def _validate_functional_mode(request: dict[str, Any], tuning_mode: str) -> dict[str, Any]:
    functional = request["functional"]
    valid_modes = GENERALIZATION_FUNCTIONAL_MODES if tuning_mode == "generalization" else FUNCTIONAL_MODES
    if functional["mode"] not in valid_modes:
        raise ValueError(f"invalid functional mode: {functional['mode']}")
    if functional["mode"] == "existing" and not functional.get("cases"):
        raise ValueError("existing functional mode requires a cases path")
    if functional["mode"] != "existing" and functional.get("cases"):
        raise ValueError("functional cases path is valid only for existing mode")
    return functional


def _validate_competitor(competitor: dict[str, Any]) -> None:
    source = competitor.get("source")
    if source not in COMPETITOR_SOURCES:
        raise ValueError(f"invalid competitor source: {source}")
    if source == "file":
        if not competitor.get("performance"):
            raise ValueError("file competitor source requires a performance path")
        if competitor.get("gpu_environment") is not None:
            raise ValueError("GPU environment is valid only for xpu-perf-benchmark source")
        return
    if competitor.get("performance") is not None:
        raise ValueError("competitor performance path is valid only for file source")
    gpu = competitor.get("gpu_environment")
    required_gpu_fields = ("ssh_environment", "work_dir", "conda_environment", "implementation_mode")
    if not isinstance(gpu, dict) or any(not gpu.get(key) for key in required_gpu_fields):
        raise ValueError(
            "xpu-perf-benchmark source requires GPU SSH environment, work directory, "
            "conda environment, and implementation mode"
        )
    if gpu["implementation_mode"] not in ("torch.compile", "triton"):
        raise ValueError("GPU implementation mode must be torch.compile or triton")


def _validate_generalization(request: dict[str, Any]) -> None:
    generalization = request.get("generalization")
    if not isinstance(generalization, dict):
        raise ValueError("generalization mode requires generalization configuration")
    target_case_count = generalization.get("target_case_count")
    if not isinstance(target_case_count, int) or target_case_count <= 0:
        raise ValueError("generalization target_case_count must be a positive integer")
    if generalization.get("tuning_case_limit") != GENERALIZATION_TUNING_LIMIT:
        raise ValueError(f"generalization tuning_case_limit must be {GENERALIZATION_TUNING_LIMIT}")
    if generalization.get("inner_max_rounds") != 3 or generalization.get("outer_max_iterations") != 2:
        raise ValueError("generalization loop limits must be inner=3 and outer=2")
    if generalization.get("ratio_thresholds") != {"geomean": 1.0, "minimum": 0.6}:
        raise ValueError("generalization ratio thresholds must be geomean=1.0 and minimum=0.6")
    _validate_competitor(generalization.get("competitor", {}))


def _validate_performance_cases(request: dict[str, Any], tuning_mode: str) -> None:
    performance_cases = request.get("performance_cases")
    if tuning_mode == "standard":
        if not performance_cases:
            raise ValueError("standard mode requires performance cases")
        if request.get("generalization") is not None:
            raise ValueError("generalization configuration is valid only in generalization mode")
    else:
        _validate_generalization(request)


def _validate_performance_reference(request: dict[str, Any], tuning_mode: str) -> None:
    if request.get("performance_reference") is not None:
        validate_reference(request["performance_reference"])
        if tuning_mode == "generalization" and request["performance_reference"]["kind"] != "xpu":
            raise ValueError("generalization requires xpu performance_reference")


def _validate_objective(request: dict[str, Any]) -> None:
    objective = request["optimization_objective"]
    if objective["mode"] == "fixed_rounds":
        if not isinstance(objective.get("rounds"), int) or objective["rounds"] <= 0:
            raise ValueError("fixed_rounds objective requires positive integer rounds")
    elif objective["mode"] == "target":
        if not objective.get("metric") or objective.get("value") is None or not objective.get("unit"):
            raise ValueError("target objective requires metric, value, and unit")
        if objective.get("comparison") not in ("ge", "le", "eq"):
            raise ValueError("target comparison must be ge, le, or eq")
        if objective.get("max_rounds") is not None and (
            not isinstance(objective["max_rounds"], int) or objective["max_rounds"] <= 0
        ):
            raise ValueError("target max_rounds must be a positive integer")
    else:
        raise ValueError(f"invalid optimization objective mode: {objective['mode']}")


def _validate_cann_environment(request: dict[str, Any], validate_live: bool) -> None:
    cann_info = request["environments"]["cann"]
    if not cann_info.get("setup_command"):
        raise ValueError("CANN environment setup command is required")
    if (
        validate_live
        and cann_info["setup_command"] == "inherit"
        and cann_info.get("snapshot_at_confirmation") != cann_snapshot()
    ):
        raise ValueError("inherited CANN environment changed; reconfirm optimization request")


def _validate_python_environment(request: dict[str, Any], validate_live: bool) -> None:
    python_info = request["environments"]["python"]
    executable = resolve_executable(python_info["executable"])
    if validate_live and python_version(executable) != python_info["version"]:
        raise ValueError("configured Python version changed; reconfirm optimization request")


def _validate_live_paths(
    request: dict[str, Any], tuning_mode: str, functional: dict[str, Any], performance_cases: Any
) -> None:
    code_dir = Path(request["code_dir"])
    performance_cases_path = Path(performance_cases) if performance_cases else None
    if not code_dir.is_dir():
        raise ValueError(f"configured code directory is unavailable: {code_dir}")
    if performance_cases_path is not None and not performance_cases_path.is_file():
        raise ValueError(f"configured performance cases are unavailable: {performance_cases_path}")
    if functional["mode"] == "existing" and not Path(functional["cases"]).exists():
        raise ValueError(f"configured functional cases are unavailable: {functional['cases']}")
    if tuning_mode == "generalization":
        competitor = request["generalization"]["competitor"]
        if competitor["source"] == "file" and not Path(competitor["performance"]).is_file():
            raise ValueError(f"configured competitor performance is unavailable: {competitor['performance']}")


def load_request(path: Path, *, validate_live: bool = True) -> dict[str, Any]:
    request = json.loads(path.read_text(encoding="utf-8"))
    if request.get("schema_version") != REQUEST_SCHEMA_VERSION:
        raise ValueError(f"Unsupported optimization-request schema: {request.get('schema_version')}")
    if request.get("confirmation", {}).get("status") != "confirmed":
        raise ValueError("optimization request must be confirmed before use")
    _validate_request_policies(request)
    request.pop("precision_diagnosis_policy", None)
    validate_backend(request, validate_live=validate_live)
    if not _has_unique_target_socs(request.get("target_socs")):
        raise ValueError("optimization request requires a non-empty, unique target_socs list")
    tuning_mode = _validate_tuning_mode(request)
    functional = _validate_functional_mode(request, tuning_mode)
    performance_cases = request.get("performance_cases")
    _validate_performance_cases(request, tuning_mode)
    _validate_performance_reference(request, tuning_mode)
    _validate_objective(request)
    _validate_cann_environment(request, validate_live)
    _validate_python_environment(request, validate_live)
    if validate_live:
        _validate_live_paths(request, tuning_mode, functional, performance_cases)
    return request


def _validate_create_inputs(
    args: argparse.Namespace,
) -> tuple[Path, Path | None, Path | None, list[str]]:
    code_dir = args.code_dir.resolve()
    performance_cases = args.performance_cases.resolve() if args.performance_cases else None
    target_socs = list(dict.fromkeys(soc.strip() for soc in args.target_soc))
    if not target_socs or any(not soc for soc in target_socs):
        raise ValueError("--target-soc must contain at least one non-empty SoC name")
    if not code_dir.is_dir():
        raise ValueError(f"CODE_DIR is not a directory: {code_dir}")
    if performance_cases is not None and not performance_cases.is_file():
        raise ValueError(f"PERFORMANCE_CASES is not a file: {performance_cases}")
    reference_perf = args.reference_perf.resolve() if args.reference_perf else None
    if reference_perf is not None and not reference_perf.is_file():
        raise ValueError(f"REFERENCE_PERF is not a file: {reference_perf}")
    return code_dir, performance_cases, reference_perf, target_socs


def _validate_standard_create_args(args: argparse.Namespace, performance_cases: Path | None) -> str:
    if performance_cases is None:
        raise ValueError("standard mode requires --performance-cases")
    if args.functional_mode is None:
        raise ValueError("standard mode requires --functional-mode")
    if args.functional_mode not in FUNCTIONAL_MODES:
        raise ValueError(f"invalid standard functional mode: {args.functional_mode}")
    if args.functional_mode == "existing" and args.functional_cases is None:
        raise ValueError("existing mode requires --functional-cases")
    if args.functional_mode != "existing" and args.functional_cases is not None:
        raise ValueError("--functional-cases is valid only for existing mode")
    if args.competitor_source or args.competitor_perf or any(
        (args.gpu_ssh_environment, args.gpu_work_dir, args.gpu_conda_environment, args.gpu_implementation_mode)
    ):
        raise ValueError("competitor inputs are valid only in generalization mode")
    return args.functional_mode


def _resolve_create_competitor(args: argparse.Namespace) -> dict[str, Any]:
    source = args.competitor_source or ("file" if args.competitor_perf else "xpu-perf-benchmark")
    if source == "file":
        if args.competitor_perf is None:
            raise ValueError("--competitor-perf is required when --competitor-source=file")
        competitor_path = args.competitor_perf.resolve()
        if not competitor_path.is_file():
            raise ValueError(f"COMPETITOR_PERF is not a file: {competitor_path}")
        if any(
            (args.gpu_ssh_environment, args.gpu_work_dir, args.gpu_conda_environment, args.gpu_implementation_mode)
        ):
            raise ValueError("GPU environment inputs are valid only for xpu-perf-benchmark source")
        return {"source": "file", "performance": str(competitor_path), "gpu_environment": None}
    gpu_values = {
        "ssh_environment": args.gpu_ssh_environment,
        "work_dir": args.gpu_work_dir,
        "conda_environment": args.gpu_conda_environment,
        "implementation_mode": args.gpu_implementation_mode,
    }
    if any(not value for value in gpu_values.values()):
        raise ValueError(
            "xpu-perf-benchmark source requires --gpu-ssh-environment, --gpu-work-dir, "
            "--gpu-conda-environment, and --gpu-implementation-mode"
        )
    return {"source": "xpu-perf-benchmark", "performance": None, "gpu_environment": gpu_values}


def _validate_generalization_create_args(args: argparse.Namespace) -> tuple[str, dict[str, Any]]:
    functional_mode = args.functional_mode or "reuse_performance"
    if functional_mode not in GENERALIZATION_FUNCTIONAL_MODES:
        raise ValueError("generalization mode fixes functional mode to reuse_performance")
    if args.functional_cases is not None:
        raise ValueError("generalization mode does not accept --functional-cases")
    if args.target_case_count <= 0:
        raise ValueError("--target-case-count must be positive")
    generalization = {
        "target_case_count": args.target_case_count,
        "tuning_case_limit": GENERALIZATION_TUNING_LIMIT,
        "competitor": _resolve_create_competitor(args),
        "ratio_thresholds": {"geomean": 1.0, "minimum": 0.6},
        "inner_max_rounds": 3,
        "outer_max_iterations": 2,
    }
    return functional_mode, generalization


def _load_create_reference(args: argparse.Namespace) -> dict[str, Any]:
    if args.performance_reference:
        return json.loads(args.performance_reference.read_text(encoding="utf-8"))
    return {"kind": "xpu" if args.tuning_mode == "generalization" else "baseline", "target_ratio": 1.0}


def _dsl_configuration(args: argparse.Namespace) -> dict[str, Any] | None:
    if args.backend != "cannbot_dsl":
        return None
    return {
        "repo_root": str(args.dsl_repo_root.resolve()) if args.dsl_repo_root else None,
        "entrypoint": args.dsl_entrypoint,
        "execution_mode": args.dsl_execution_mode or "jit",
        "workload_scope": "network_cases",
    }


def _environment_configuration(args: argparse.Namespace, executable: Path) -> dict[str, Any]:
    return {
        "python": {
            "executable": str(executable),
            "version": python_version(executable),
            "activation_command": args.python_activation_command,
        },
        "cann": {
            "setup_command": args.cann_env_command,
            "snapshot_at_confirmation": cann_snapshot(),
        },
    }


def _build_create_request(
    args: argparse.Namespace,
    code_dir: Path,
    performance_cases: Path | None,
    reference_perf: Path | None,
    target_socs: list[str],
    functional_mode: str,
    generalization: dict[str, Any] | None,
    reference: dict[str, Any],
    executable: Path,
) -> dict[str, Any]:
    return {
        "schema_version": REQUEST_SCHEMA_VERSION,
        "created_at": now(),
        "operator": args.operator_name,
        "backend": args.backend,
        "dsl": _dsl_configuration(args),
        "tuning_mode": args.tuning_mode,
        "target_socs": target_socs,
        "code_dir": str(code_dir),
        "performance_cases": str(performance_cases) if performance_cases else None,
        "functional": {
            "mode": functional_mode,
            "cases": str(args.functional_cases.resolve()) if args.functional_cases else None,
        },
        "optimization_objective": optimization_objective(args),
        "optimization_intent": args.optimization_intent,
        "reference_perf": str(reference_perf) if reference_perf else None,
        "performance_reference": reference,
        "performance_effect_policy": {
            "id": getattr(args, "performance_effect_policy", "confidence_effect_v1"), "version": 1,
        },
        "schedule_policy": {"id": "schedule_contract_v1", "version": 1},
        "generalization": generalization,
        "environments": _environment_configuration(args, executable),
        "confirmation": {
            "status": "confirmed",
            "confirmed_at": now(),
            "confirmed_by": args.confirmed_by,
        },
    }


def command_create_request(args: argparse.Namespace) -> int:
    code_dir, performance_cases, reference_perf, target_socs = _validate_create_inputs(args)
    if args.tuning_mode == "standard":
        functional_mode = _validate_standard_create_args(args, performance_cases)
        generalization = None
    else:
        functional_mode, generalization = _validate_generalization_create_args(args)
    reference = _load_create_reference(args)
    validate_reference(reference)
    if args.tuning_mode == "generalization" and reference["kind"] != "xpu":
        raise ValueError("generalization retains its xpu ratio contract; use standard for other reference kinds")
    executable = resolve_executable(args.python_executable)
    request = _build_create_request(
        args, code_dir, performance_cases, reference_perf, target_socs,
        functional_mode, generalization, reference, executable,
    )
    if args.backend == "ascendc" and any((args.dsl_repo_root, args.dsl_entrypoint, args.dsl_execution_mode)):
        raise ValueError("--dsl-* options require --backend cannbot_dsl")
    validate_backend(request)
    atomic_json(args.request.resolve(), request)
    emit(json.dumps(
        {"status": "request_created", "request": str(args.request.resolve()), "summary": request_summary(request)},
        ensure_ascii=False,
    ))
    return 0


def command_validate_request(args: argparse.Namespace) -> int:
    request = load_request(args.request.resolve())
    emit(json.dumps({"status": "valid", "summary": request_summary(request)}, ensure_ascii=False))
    return 0


def load_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != RUN_SCHEMA_VERSION:
        raise ValueError(f"Unsupported run-manifest schema: {payload.get('schema_version')}")
    validate_backend(payload.get("configuration", {}), validate_live=False)
    from performance_effect_evidence import policy
    policy(payload.get("configuration", {}).get("performance_effect_policy"))
    configuration = payload.get("configuration", {})
    if "schedule_policy" in configuration:
        if configuration["schedule_policy"] is None:
            raise ValueError("explicit null schedule_policy is invalid")
        validate_schedule_policy(configuration["schedule_policy"])
    return payload


def command_freeze(args: argparse.Namespace) -> int:
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    request_source = args.request.resolve()
    request = load_request(request_source)
    tuning_mode = request.get("tuning_mode", "standard")
    code_dir = Path(request["code_dir"])
    performance_source = Path(request["performance_cases"]) if request.get("performance_cases") else None
    functional_mode = request["functional"]["mode"]
    functional_cases = Path(request["functional"]["cases"]) if request["functional"].get("cases") else None

    frozen_request = output_dir / "optimization-request.json"
    atomic_json(frozen_request, request)

    manifest = _freeze_manifest(
        request, tuning_mode, functional_mode, code_dir, performance_source, frozen_request
    )
    _freeze_dsl_environment(args, request, request_source, output_dir, manifest)
    if tuning_mode == "standard":
        confirmation = _freeze_standard(
            args, request, performance_source, functional_mode, functional_cases, manifest, output_dir
        )
    else:
        _freeze_generalization(request, performance_source, functional_cases, manifest, output_dir)
        confirmation = "not_applicable"

    path = output_dir / "run-manifest.json"
    atomic_json(path, manifest)
    emit(json.dumps({"status": "frozen", "manifest": str(path), "confirmation": confirmation}, ensure_ascii=False))
    return 0


def _freeze_dsl_environment(
    args: argparse.Namespace,
    request: dict[str, Any],
    request_source: Path,
    output_dir: Path,
    manifest: dict[str, Any],
) -> None:
    if request.get("backend") != "cannbot_dsl":
        return
    environment_path = (args.dsl_environment or request_source.parent / "dsl-environment.json").resolve()
    environment = json.loads(environment_path.read_text(encoding="utf-8"))
    if (environment.get("schema_version") != 1
            or not environment.get("dsl_version")
            or not environment.get("package_files")):
        raise ValueError("DSL freeze requires the preflight package/environment snapshot")
    for item in environment["package_files"]:
        if {"path": str(Path(item["path"]).resolve()), "sha256": sha256_file(Path(item["path"]))} != item:
            raise ValueError("DSL package changed since preflight")
    frozen_environment = output_dir / "dsl-environment.json"
    if frozen_environment != environment_path:
        shutil.copyfile(environment_path, frozen_environment)
    manifest["inputs"]["dsl_environment"] = {
        "path": str(frozen_environment), "sha256": sha256_file(frozen_environment)
    }


def _freeze_manifest(
    request: dict[str, Any],
    tuning_mode: str,
    functional_mode: str,
    code_dir: Path,
    performance_source: Path | None,
    frozen_request: Path,
) -> dict[str, Any]:
    performance_reference = request.get("performance_reference") or {
        "kind": "xpu" if tuning_mode == "generalization" else "baseline", "target_ratio": 1.0}
    configuration = {
        "operator": request.get("operator"),
        "backend": request.get("backend", "ascendc"),
        "dsl": request.get("dsl"),
        "tuning_mode": tuning_mode,
        "target_socs": request["target_socs"],
        "functional_mode": functional_mode,
        "optimization_objective": request["optimization_objective"],
        "optimization_intent": request.get("optimization_intent", "safe_incremental"),
        "reference_perf": request.get("reference_perf"),
        "workflow_layout": "five-stage-v1",
        "performance_reference": performance_reference,
        "environments": request["environments"],
        "precision_diagnosis_policy": PRECISION_DIAGNOSIS_POLICY,
        "generalization": request.get("generalization"),
    }
    if "performance_effect_policy" in request:
        configuration["performance_effect_policy"] = request["performance_effect_policy"]
    if "schedule_policy" in request:
        configuration["schedule_policy"] = request["schedule_policy"]
    return {
        "schema_version": RUN_SCHEMA_VERSION,
        "created_at": now(),
        "updated_at": now(),
        "request": identity(frozen_request),
        "configuration": configuration,
        "inputs": {
            "code": code_identity(code_dir),
            "performance_cases": identity(performance_source) if performance_source else None,
            "functional_cases": None,
            "competitor_performance": None,
        },
        "collections": {},
    }


def _performance_selection(
    args: argparse.Namespace,
    perf_rows: list[dict[str, str]],
    fields: list[str],
    output_dir: Path,
) -> tuple[Path, list[dict[str, str]], dict[str, Any], str]:
    perf_indices, perf_details = select_rows(perf_rows, PERFORMANCE_LIMIT)
    perf_tuning_rows = [perf_rows[index] for index in perf_indices]
    perf_tuning = baseline_stage_dir(output_dir) / "performance-tuning-cases.csv"
    atomic_csv(perf_tuning, fields, perf_tuning_rows)
    needs_confirmation = len(perf_rows) > PERFORMANCE_LIMIT
    confirmation = "confirmed" if not needs_confirmation or args.confirm_performance else "pending"
    perf_selection = {
        "algorithm": SELECTION_ALGORITHM,
        "limit": PERFORMANCE_LIMIT,
        "source_count": len(perf_rows),
        "selected": perf_details,
        "confirmation": confirmation,
    }
    return perf_tuning, perf_tuning_rows, perf_selection, confirmation


def _freeze_standard(
    args: argparse.Namespace,
    request: dict[str, Any],
    performance_source: Path | None,
    functional_mode: str,
    functional_cases: Path | None,
    manifest: dict[str, Any],
    output_dir: Path,
) -> str:
    if performance_source is None:
        raise ValueError("standard mode requires performance cases")
    if request.get("backend") == "cannbot_dsl":
        _, network_rows = read_csv(performance_source)
        if any(row.get("expected_error") or row.get("execution_kind", "device") not in ("", "device")
               for row in network_rows):
            raise ValueError(
                "DSL performance inventory must contain device cases; "
                "keep host/error checks in functional inventory"
            )
    perf_full = baseline_stage_dir(output_dir) / "performance-full-cases.csv"
    fields, perf_rows = freeze_csv(performance_source, perf_full)
    perf_tuning, perf_tuning_rows, perf_selection, confirmation = _performance_selection(
        args, perf_rows, fields, output_dir
    )
    manifest["collections"].update(
        {
            "performance_full": collection(perf_full, perf_rows),
            "performance_tuning": collection(perf_tuning, perf_tuning_rows, perf_selection),
        }
    )
    manifest["functional_preparation"] = {
        "status": "pending" if functional_mode == "generate" else "complete"
    }
    if functional_mode == "reuse_performance":
        full, acceptance = functional_payload(perf_full, baseline_stage_dir(output_dir))
        manifest["collections"].update({"functional_full": full, "functional_acceptance": acceptance})
    elif functional_mode == "existing":
        if functional_cases is None:
            raise ValueError("existing functional mode requires a cases path")
        full, acceptance = functional_payload(functional_cases, baseline_stage_dir(output_dir))
        manifest["collections"].update({"functional_full": full, "functional_acceptance": acceptance})
        manifest["inputs"]["functional_cases"] = {
            "path": str(functional_cases.resolve()),
            "kind": "directory" if functional_cases.is_dir() else "file",
            "sha256": full["sha256"],
            "identity_method": "frozen-copy",
        }
    return confirmation


def _freeze_file_competitor(manifest: dict[str, Any], output_dir: Path) -> None:
    competitor_source = Path(manifest["configuration"]["generalization"]["competitor"]["performance"])
    expected = (
        case_ids_from_collection(manifest["collections"]["generalization_full"])
        if "generalization_full" in manifest["collections"]
        else None
    )
    competitor_collection = competitor_payload(competitor_source, baseline_stage_dir(output_dir), expected)
    manifest["collections"]["competitor_performance"] = competitor_collection
    manifest["inputs"]["competitor_performance"] = identity(competitor_source)
    competitor_status = (
        "complete"
        if competitor_collection["validation"]["status"] == "complete"
        else "pending_cases"
    )
    manifest["generalization_preparation"]["competitor"] = {"status": competitor_status}


def _freeze_generalization(
    request: dict[str, Any],
    performance_source: Path | None,
    functional_cases: Path | None,
    manifest: dict[str, Any],
    output_dir: Path,
) -> None:
    if request.get("generalization") is None:
        raise ValueError("generalization mode requires generalization configuration")
    if performance_source and functional_cases:
        performance_sha = sha256_file(performance_source)
        functional_sha = sha256_file(inventory_csv(functional_cases))
        if performance_sha != functional_sha:
            raise ValueError(
                "generalization mode uses one performance/functional inventory; "
                "provided performance and functional cases differ"
            )
    case_source = performance_source or functional_cases
    if case_source is not None:
        generalization_full, functional_full, acceptance = generalization_payload(
            case_source, baseline_stage_dir(output_dir)
        )
        manifest["collections"].update(
            {
                "generalization_full": generalization_full,
                "functional_full": functional_full,
                "functional_acceptance": acceptance,
            }
        )
        source_identity = identity(case_source)
        source_identity["identity_method"] = "performance-functional-combined"
        if manifest["inputs"]["performance_cases"] is None:
            manifest["inputs"]["performance_cases"] = source_identity
        manifest["inputs"]["functional_cases"] = source_identity
        preparation_status = "complete"
    else:
        preparation_status = "pending"
    manifest["functional_preparation"] = {"status": preparation_status}
    manifest["generalization_preparation"] = {
        "cases": {"status": preparation_status},
        "competitor": {"status": "pending"},
    }
    if request["generalization"]["competitor"]["source"] == "file":
        _freeze_file_competitor(manifest, output_dir)


def command_confirm(args: argparse.Namespace) -> int:
    manifest = load_manifest(args.manifest)
    if manifest["configuration"].get("tuning_mode", "standard") != "standard":
        raise ValueError("confirm-performance is valid only in standard mode")
    selection = manifest["collections"]["performance_tuning"]["selection"]
    selection["confirmation"] = "confirmed"
    selection["confirmed_at"] = now()
    selection["confirmed_by"] = args.by
    if args.note:
        selection["note"] = args.note
    manifest["updated_at"] = now()
    atomic_json(args.manifest, manifest)
    emit(json.dumps({"status": "confirmed", "manifest": str(args.manifest)}, ensure_ascii=False))
    return 0


def command_attach(args: argparse.Namespace) -> int:
    manifest = load_manifest(args.manifest)
    if manifest["configuration"].get("tuning_mode", "standard") != "standard":
        raise ValueError("use attach-generalization for generalization mode")
    if manifest["configuration"]["functional_mode"] != "generate":
        raise ValueError("attach-functional is valid only for generate mode")
    output_dir = args.manifest.resolve().parent
    full, acceptance = functional_payload(args.functional_cases.resolve(), baseline_stage_dir(output_dir))
    manifest["inputs"]["functional_cases"] = {
        "path": str(args.functional_cases.resolve()),
        "kind": "directory" if args.functional_cases.is_dir() else "file",
        "sha256": full["sha256"],
        "identity_method": "frozen-copy",
    }
    manifest["collections"].update({"functional_full": full, "functional_acceptance": acceptance})
    manifest["functional_preparation"] = {"status": "complete", "completed_at": now()}
    manifest["updated_at"] = now()
    atomic_json(args.manifest, manifest)
    emit(json.dumps({"status": "functional_attached", "manifest": str(args.manifest)}, ensure_ascii=False))
    return 0


def command_attach_generalization(args: argparse.Namespace) -> int:
    manifest = load_manifest(args.manifest)
    if manifest["configuration"].get("tuning_mode", "standard") != "generalization":
        raise ValueError("attach-generalization is valid only in generalization mode")
    if manifest["collections"].get("generalization_full"):
        raise ValueError("generalization inventory is already frozen; create a new run to replace it")
    output_dir = args.manifest.resolve().parent
    source = args.cases.resolve()
    generalization_full, functional_full, acceptance = generalization_payload(source, baseline_stage_dir(output_dir))
    manifest["collections"].update(
        {
            "generalization_full": generalization_full,
            "functional_full": functional_full,
            "functional_acceptance": acceptance,
        }
    )
    source_identity = identity(source)
    source_identity["identity_method"] = "generated-or-provided-combined-inventory"
    manifest["inputs"]["performance_cases"] = source_identity
    manifest["inputs"]["functional_cases"] = source_identity
    manifest["functional_preparation"] = {"status": "complete", "completed_at": now()}
    manifest.setdefault("generalization_preparation", {})["cases"] = {
        "status": "complete",
        "completed_at": now(),
    }

    competitor = manifest["collections"].get("competitor_performance")
    if competitor:
        expected = case_ids_from_collection(generalization_full)
        validated = competitor_payload(Path(competitor["path"]), baseline_stage_dir(output_dir), expected)
        manifest["collections"]["competitor_performance"] = validated
        manifest["generalization_preparation"]["competitor"] = {
            "status": "complete",
            "completed_at": now(),
        }
    manifest["updated_at"] = now()
    atomic_json(args.manifest, manifest)
    emit(json.dumps({"status": "generalization_attached", "manifest": str(args.manifest)}, ensure_ascii=False))
    return 0


def command_attach_competitor(args: argparse.Namespace) -> int:
    manifest = load_manifest(args.manifest)
    if manifest["configuration"].get("tuning_mode", "standard") != "generalization":
        raise ValueError("attach-competitor is valid only in generalization mode")
    configured = manifest["configuration"]["generalization"]["competitor"]
    if configured["source"] != "xpu-perf-benchmark":
        raise ValueError("attach-competitor is valid only for xpu-perf-benchmark source")
    if manifest["collections"].get("competitor_performance"):
        raise ValueError("competitor performance is already frozen; create a new run to replace it")
    generalization_full = manifest["collections"].get("generalization_full")
    if not generalization_full:
        raise ValueError("attach generalization cases before competitor performance")
    output_dir = args.manifest.resolve().parent
    expected = case_ids_from_collection(generalization_full)
    competitor = competitor_payload(args.competitor_perf.resolve(), baseline_stage_dir(output_dir), expected)
    manifest["collections"]["competitor_performance"] = competitor
    manifest["inputs"]["competitor_performance"] = identity(args.competitor_perf.resolve())
    manifest.setdefault("generalization_preparation", {})["competitor"] = {
        "status": "complete",
        "completed_at": now(),
    }
    manifest["updated_at"] = now()
    atomic_json(args.manifest, manifest)
    emit(json.dumps({"status": "competitor_attached", "manifest": str(args.manifest)}, ensure_ascii=False))
    return 0


def _add_create_parser(subparsers: Any) -> None:
    create = subparsers.add_parser("create-request", help="write a reusable, user-confirmed optimization request")
    create.add_argument("--request", type=Path, required=True)
    create.add_argument("--operator-name")
    create.add_argument("--code-dir", type=Path, required=True)
    create.add_argument("--backend", choices=BACKENDS, default="ascendc")
    create.add_argument("--dsl-repo-root", type=Path, help="DSL reference/sample repository; not an import fallback")
    create.add_argument("--dsl-entrypoint", help="Original public Python module:callable")
    create.add_argument("--dsl-execution-mode", choices=DSL_EXECUTION_MODES)
    create.add_argument("--tuning-mode", choices=TUNING_MODES, default="standard")
    create.add_argument(
        "--target-soc",
        action="append",
        required=True,
        help="verified optimization SoC; repeat only when every listed generation will be validated",
    )
    create.add_argument("--performance-cases", type=Path)
    create.add_argument(
        "--performance-effect-policy",
        choices=("legacy_jitter_v1", "confidence_effect_v1"),
        default="confidence_effect_v1",
    )
    create.add_argument(
        "--performance-reference",
        type=Path,
        help="JSON reference kind, target_ratio and source configuration",
    )
    create.add_argument("--functional-mode", choices=FUNCTIONAL_MODES)
    create.add_argument("--functional-cases", type=Path)
    create.add_argument("--target-case-count", type=int, default=DEFAULT_GENERALIZATION_CASE_COUNT)
    _add_create_objective_arguments(create)
    create.set_defaults(func=command_create_request)


def _add_create_objective_arguments(create: argparse.ArgumentParser) -> None:
    create.add_argument("--competitor-source", choices=COMPETITOR_SOURCES)
    create.add_argument("--competitor-perf", type=Path)
    create.add_argument("--gpu-ssh-environment")
    create.add_argument("--gpu-work-dir")
    create.add_argument("--gpu-conda-environment")
    create.add_argument("--gpu-implementation-mode", choices=("torch.compile", "triton"))
    create.add_argument("--optimization-mode", choices=("fixed_rounds", "target"), default="fixed_rounds")
    create.add_argument("--rounds", type=int, default=3)
    create.add_argument("--target-metric")
    create.add_argument("--target-comparison", choices=("ge", "le", "eq"), default="ge")
    create.add_argument("--target-value", type=float)
    create.add_argument("--target-unit")
    create.add_argument("--max-rounds", type=int)
    create.add_argument("--python-executable", default=sys.executable)
    create.add_argument("--python-activation-command")
    create.add_argument("--cann-env-command", required=True)
    create.add_argument("--confirmed-by", default="user")
    create.add_argument(
        "--optimization-intent",
        choices=("safe_incremental", "pursue_optimal"),
        default="safe_incremental",
        help="safe_incremental: isolated increments in the current kernel structure. "
        "pursue_optimal: structural rewrites (fusion / layout / precision scheme) are in scope and "
        "unrealized structural directions block a clean success finish.",
    )
    create.add_argument(
        "--reference-perf",
        type=Path,
        help="optional performance anchor: a case_id,ref_total_us CSV (same-operator/competitor/ceiling "
        "reference implementation). Analysis anchors 'measured vs reference' gap.",
    )


def _add_freeze_parser(subparsers: Any) -> None:
    freeze = subparsers.add_parser("freeze", help="freeze inputs and deterministic case subsets")
    freeze.add_argument("--output-dir", type=Path, required=True)
    freeze.add_argument("--request", type=Path, required=True)
    freeze.add_argument(
        "--dsl-environment", type=Path, help="preflight DSL environment snapshot (default: beside request)"
    )
    freeze.add_argument("--confirm-performance", action="store_true")
    freeze.set_defaults(func=command_freeze)


def _add_attach_parsers(subparsers: Any) -> None:
    attach = subparsers.add_parser("attach-functional", help="attach generated functional inventory")
    attach.add_argument("--manifest", type=Path, required=True)
    attach.add_argument("--functional-cases", type=Path, required=True)
    attach.set_defaults(func=command_attach)

    attach_generalization = subparsers.add_parser(
        "attach-generalization", help="attach a generated performance/functional generalization inventory"
    )
    attach_generalization.add_argument("--manifest", type=Path, required=True)
    attach_generalization.add_argument("--cases", type=Path, required=True)
    attach_generalization.set_defaults(func=command_attach_generalization)

    attach_competitor = subparsers.add_parser(
        "attach-competitor", help="attach xpu-perf-benchmark output to a generalization run"
    )
    attach_competitor.add_argument("--manifest", type=Path, required=True)
    attach_competitor.add_argument("--competitor-perf", type=Path, required=True)
    attach_competitor.set_defaults(func=command_attach_competitor)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    subparsers = result.add_subparsers(dest="command", required=True)
    _add_create_parser(subparsers)

    validate_request = subparsers.add_parser(
        "validate-request", help="validate a reusable request against current paths"
    )
    validate_request.add_argument("--request", type=Path, required=True)
    validate_request.set_defaults(func=command_validate_request)

    _add_freeze_parser(subparsers)

    confirm = subparsers.add_parser("confirm-performance", help="record user confirmation of >50 performance subset")
    confirm.add_argument("--manifest", type=Path, required=True)
    confirm.add_argument("--by", default="user")
    confirm.add_argument("--note")
    confirm.set_defaults(func=command_confirm)

    _add_attach_parsers(subparsers)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        return args.func(args)
    except (FileNotFoundError, KeyError, ValueError) as error:
        emit(json.dumps({"status": "error", "error": str(error)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
