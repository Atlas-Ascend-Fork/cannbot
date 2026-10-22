#!/usr/bin/env python3
# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Version 2.0 (the "License").
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

from cli_output import emit, run_cli


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
COMPETITOR_SOURCES = ("file",)
PERFORMANCE_REFERENCE_KINDS = ("baseline", "xpu", "theoretical", "unfused")
PRECISION_DIAGNOSIS_POLICY = "persistent"
ID_COLUMNS = ("case_id", "id", "case", "name")
LEVEL_COLUMNS = ("level", "test_level", "case_level")
IGNORED_CODE_DIRS = {".git", ".pytest_cache", "__pycache__", "build", "dist", "output", "outputs"}
CODE_SUFFIXES = {".c", ".cc", ".cpp", ".h", ".hh", ".hpp", ".py", ".sh", ".cmake", ".json", ".yaml", ".yml", ".toml"}


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
    status = "complete" if not issues else "needs_review"
    return {"status": status, **groups, "issues": issues, "duplicate_case_ids": duplicates}


def freeze_csv(source: Path, destination: Path) -> tuple[list[str], list[dict[str, str]]]:
    fields, rows = read_csv(source)
    atomic_csv(destination, fields, rows)
    return fields, rows


def _copy_functional_tree(source: Path, destination_dir: Path) -> None:
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


def _functional_full(source: Path, output_dir: Path, fields: list, rows: list) -> tuple[Path, dict]:
    if source.is_dir():
        destination_dir = output_dir / "functional-full"
        _copy_functional_tree(source, destination_dir)
        frozen_csv = inventory_csv(destination_dir)
        full = {
            **identity(destination_dir),
            "count": len(rows),
            "case_manifest": str(frozen_csv.resolve()),
            "validation": inventory_validation(fields, rows),
        }
        return frozen_csv, full
    frozen_csv = output_dir / "functional-full-cases.csv"
    atomic_csv(frozen_csv, fields, rows)
    full = collection(frozen_csv, rows)
    full["validation"] = inventory_validation(fields, rows)
    return frozen_csv, full


def _functional_acceptance(rows: list, output_dir: Path, fields: list) -> dict:
    l0_pairs = [(index, row) for index, row in enumerate(rows) if level(row) == "L0"]
    if not l0_pairs:
        raise ValueError("Functional inventory contains no L0 cases")
    l0_rows = [row for _, row in l0_pairs]
    selected_local, details = select_rows(l0_rows, ACCEPTANCE_LIMIT)
    selected_rows = [l0_rows[index] for index in selected_local]
    acceptance = output_dir / "functional-acceptance-cases.csv"
    atomic_csv(acceptance, fields, selected_rows)
    selection = {
        "algorithm": SELECTION_ALGORITHM,
        "limit": ACCEPTANCE_LIMIT,
        "source_count": len(rows),
        "l0_count": len(l0_rows),
        "selected": details,
    }
    return collection(acceptance, selected_rows, selection)


def functional_payload(source: Path, output_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    source_csv = inventory_csv(source)
    fields, rows = read_csv(source_csv)
    _, full = _functional_full(source, output_dir, fields, rows)
    return full, _functional_acceptance(rows, output_dir, fields)


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


def validate_reference(value: dict) -> dict:
    if not isinstance(value, dict) or value.get("kind") not in PERFORMANCE_REFERENCE_KINDS:
        raise ValueError(f'performance_reference.kind must be one of {PERFORMANCE_REFERENCE_KINDS}')
    ratio = value.get("target_ratio")
    if isinstance(ratio, bool) or not isinstance(ratio, (int, float)) or not math.isfinite(ratio):
        raise ValueError('target_ratio must be finite and positive (reference_us / target_us)')
    if ratio <= 0:
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
        "python": request["environments"]["python"],
        "cann": request["environments"]["cann"],
        "confirmation": request["confirmation"],
    }


def _validate_socs(request: dict) -> list[str]:
    target_socs = request.get("target_socs")
    message = "optimization request requires a non-empty, unique target_socs list"
    if not isinstance(target_socs, list) or not target_socs:
        raise ValueError(message)
    if not all(isinstance(soc, str) and soc.strip() for soc in target_socs):
        raise ValueError(message)
    if len(set(target_socs)) != len(target_socs):
        raise ValueError(message)
    return target_socs


def _validate_functional(request: dict, tuning_mode: str) -> dict:
    functional = request["functional"]
    valid_modes = GENERALIZATION_FUNCTIONAL_MODES if tuning_mode == "generalization" else FUNCTIONAL_MODES
    if functional["mode"] not in valid_modes:
        raise ValueError(f"invalid functional mode: {functional['mode']}")
    if functional["mode"] == "existing" and not functional.get("cases"):
        raise ValueError("existing functional mode requires a cases path")
    if functional["mode"] != "existing" and functional.get("cases"):
        raise ValueError("functional cases path is valid only for existing mode")
    return functional


def _validate_generalization(generalization: dict) -> None:
    target_case_count = generalization.get("target_case_count")
    if not isinstance(target_case_count, int) or target_case_count <= 0:
        raise ValueError("generalization target_case_count must be a positive integer")
    if generalization.get("tuning_case_limit") != GENERALIZATION_TUNING_LIMIT:
        raise ValueError(f"generalization tuning_case_limit must be {GENERALIZATION_TUNING_LIMIT}")
    if generalization.get("inner_max_rounds") != 3 or generalization.get("outer_max_iterations") != 2:
        raise ValueError("generalization loop limits must be inner=3 and outer=2")
    if generalization.get("ratio_thresholds") != {"geomean": 1.0, "minimum": 0.6}:
        raise ValueError("generalization ratio thresholds must be geomean=1.0 and minimum=0.6")
    competitor = generalization.get("competitor", {})
    source = competitor.get("source")
    if source not in COMPETITOR_SOURCES:
        raise ValueError(f"invalid competitor source: {source}")
    if competitor.get("gpu_environment") is not None:
        raise ValueError("competitor gpu_environment is not supported")
    performance = competitor.get("performance")
    if performance is not None and not Path(performance).is_file():
        raise ValueError(f"competitor performance is not a file: {performance}")


def _validate_objective(objective: dict) -> None:
    if objective["mode"] == "fixed_rounds":
        if not isinstance(objective.get("rounds"), int) or objective["rounds"] <= 0:
            raise ValueError("fixed_rounds objective requires positive integer rounds")
        return
    if objective["mode"] != "target":
        raise ValueError(f"invalid optimization objective mode: {objective['mode']}")
    if not objective.get("metric") or objective.get("value") is None or not objective.get("unit"):
        raise ValueError("target objective requires metric, value, and unit")
    if objective.get("comparison") not in ("ge", "le", "eq"):
        raise ValueError("target comparison must be ge, le, or eq")
    max_rounds = objective.get("max_rounds")
    if max_rounds is not None and (not isinstance(max_rounds, int) or max_rounds <= 0):
        raise ValueError("target max_rounds must be a positive integer")


def _validate_live_paths(request: dict, functional: dict, performance_cases,
                         tuning_mode: str) -> None:
    code_dir = Path(request["code_dir"])
    performance_cases_path = Path(performance_cases) if performance_cases else None
    if not code_dir.is_dir():
        raise ValueError(f"configured code directory is unavailable: {code_dir}")
    if performance_cases_path is not None and not performance_cases_path.is_file():
        raise ValueError(f"configured performance cases are unavailable: {performance_cases_path}")
    if functional["mode"] == "existing" and not Path(functional["cases"]).exists():
        raise ValueError(f"configured functional cases are unavailable: {functional['cases']}")
    if tuning_mode != "generalization":
        return
    performance = request["generalization"]["competitor"].get("performance")
    if performance is not None and not Path(performance).is_file():
        raise ValueError(f"configured competitor performance is unavailable: {performance}")


def load_request(path: Path, *, validate_live: bool = True) -> dict[str, Any]:
    request = json.loads(path.read_text(encoding="utf-8"))
    if request.get("schema_version") != REQUEST_SCHEMA_VERSION:
        raise ValueError(f"Unsupported optimization-request schema: {request.get('schema_version')}")
    if request.get("confirmation", {}).get("status") != "confirmed":
        raise ValueError("optimization request must be confirmed before use")
    request.pop("precision_diagnosis_policy", None)
    _validate_socs(request)
    tuning_mode = request.get("tuning_mode", "standard")
    if tuning_mode not in TUNING_MODES:
        raise ValueError(f"invalid tuning mode: {tuning_mode}")
    request["tuning_mode"] = tuning_mode
    functional = _validate_functional(request, tuning_mode)
    performance_cases = request.get("performance_cases")
    generalization = request.get("generalization")
    if tuning_mode == "standard":
        if not performance_cases:
            raise ValueError("standard mode requires performance cases")
        if generalization is not None:
            raise ValueError("generalization configuration is valid only in generalization mode")
    else:
        if not isinstance(generalization, dict):
            raise ValueError("generalization mode requires generalization configuration")
        _validate_generalization(generalization)
    if request.get("performance_reference") is not None:
        validate_reference(request["performance_reference"])
        if tuning_mode == "generalization" and request["performance_reference"]["kind"] != "xpu":
            raise ValueError("generalization requires xpu performance_reference")
    _validate_objective(request["optimization_objective"])
    cann_info = request["environments"]["cann"]
    if not cann_info.get("setup_command"):
        raise ValueError("CANN environment setup command is required")
    if validate_live and cann_info["setup_command"] == "inherit" and cann_info.get(
        "snapshot_at_confirmation"
    ) != cann_snapshot():
        raise ValueError("inherited CANN environment changed; reconfirm optimization request")
    python_info = request["environments"]["python"]
    executable = resolve_executable(python_info["executable"])
    if validate_live and python_version(executable) != python_info["version"]:
        raise ValueError("configured Python version changed; reconfirm optimization request")
    if validate_live:
        _validate_live_paths(request, functional, performance_cases, tuning_mode)
    return request


def _create_inputs(args: argparse.Namespace):
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
    return code_dir, performance_cases, target_socs, reference_perf


def _standard_config(args: argparse.Namespace, performance_cases) -> tuple[str, None]:
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
    if args.competitor_perf is not None:
        raise ValueError("competitor inputs are valid only in generalization mode")
    return args.functional_mode, None


def _generalization_config(args: argparse.Namespace) -> tuple[str, dict]:
    functional_mode = args.functional_mode or "reuse_performance"
    if functional_mode not in GENERALIZATION_FUNCTIONAL_MODES:
        raise ValueError("generalization mode fixes functional mode to reuse_performance")
    if args.functional_cases is not None:
        raise ValueError("generalization mode does not accept --functional-cases")
    if args.target_case_count <= 0:
        raise ValueError("--target-case-count must be positive")
    competitor = {"source": "file", "performance": None}
    if args.competitor_perf is not None:
        competitor_path = args.competitor_perf.resolve()
        if not competitor_path.is_file():
            raise ValueError(f"COMPETITOR_PERF is not a file: {competitor_path}")
        competitor["performance"] = str(competitor_path)
    return functional_mode, {
        "target_case_count": args.target_case_count,
        "tuning_case_limit": GENERALIZATION_TUNING_LIMIT,
        "competitor": competitor,
        "ratio_thresholds": {"geomean": 1.0, "minimum": 0.6},
        "inner_max_rounds": 3,
        "outer_max_iterations": 2,
    }


def _build_request(args, inputs: dict, config: tuple) -> dict:
    code_dir = inputs["code_dir"]
    performance_cases = inputs["performance_cases"]
    target_socs = inputs["target_socs"]
    reference_perf = inputs["reference_perf"]
    functional_mode, generalization = config
    reference = (json.loads(args.performance_reference.read_text(encoding="utf-8"))
                 if args.performance_reference else
                 {"kind": "xpu" if args.tuning_mode == "generalization" else "baseline", "target_ratio": 1.0})
    validate_reference(reference)
    if args.tuning_mode == "generalization" and reference["kind"] != "xpu":
        raise ValueError("generalization retains its xpu ratio contract; use standard for other reference kinds")
    executable = resolve_executable(args.python_executable)
    return {
        "schema_version": REQUEST_SCHEMA_VERSION,
        "created_at": now(),
        "operator": args.operator_name,
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
        "generalization": generalization,
        "environments": {
            "python": {
                "executable": str(executable),
                "version": python_version(executable),
                "activation_command": args.python_activation_command,
            },
            "cann": {
                "setup_command": args.cann_env_command,
                "snapshot_at_confirmation": cann_snapshot(),
            },
        },
        "confirmation": {
            "status": "confirmed",
            "confirmed_at": now(),
            "confirmed_by": args.confirmed_by,
        },
    }


def command_create_request(args: argparse.Namespace) -> int:
    code_dir, performance_cases, target_socs, reference_perf = _create_inputs(args)
    if args.tuning_mode == "standard":
        functional_mode, generalization = _standard_config(args, performance_cases)
    else:
        functional_mode, generalization = _generalization_config(args)
    inputs = {"code_dir": code_dir, "performance_cases": performance_cases,
              "target_socs": target_socs, "reference_perf": reference_perf}
    request = _build_request(args, inputs, (functional_mode, generalization))
    atomic_json(args.request.resolve(), request)
    emit(
        json.dumps(
            {"status": "request_created", "request": str(args.request.resolve()), "summary": request_summary(request)},
            ensure_ascii=False,
        )
    )
    return 0


def command_validate_request(args: argparse.Namespace) -> int:
    request = load_request(args.request.resolve())
    emit(json.dumps({"status": "valid", "summary": request_summary(request)}, ensure_ascii=False))
    return 0


def load_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != RUN_SCHEMA_VERSION:
        raise ValueError(f"Unsupported run-manifest schema: {payload.get('schema_version')}")
    return payload


def _frozen_manifest(request: dict, frozen_request: Path, tuning_mode: str, code_dir: Path,
                     performance_source: Path | None) -> dict[str, Any]:
    return {
        "schema_version": RUN_SCHEMA_VERSION,
        "created_at": now(),
        "updated_at": now(),
        "request": identity(frozen_request),
        "configuration": {
            "operator": request.get("operator"),
            "tuning_mode": tuning_mode,
            "target_socs": request["target_socs"],
            "functional_mode": request["functional"]["mode"],
            "optimization_objective": request["optimization_objective"],
            "optimization_intent": request.get("optimization_intent", "safe_incremental"),
            "reference_perf": request.get("reference_perf"),
            "workflow_layout": "five-stage-v1",
            "performance_reference": request.get("performance_reference") or {
                "kind": "xpu" if tuning_mode == "generalization" else "baseline", "target_ratio": 1.0},
            "environments": request["environments"],
            "precision_diagnosis_policy": PRECISION_DIAGNOSIS_POLICY,
            "generalization": request.get("generalization"),
        },
        "inputs": {
            "code": code_identity(code_dir),
            "performance_cases": identity(performance_source) if performance_source else None,
            "functional_cases": None,
            "competitor_performance": None,
        },
        "collections": {},
    }


def _freeze_standard(manifest: dict, output_dir: Path, args: argparse.Namespace,
                     request: dict) -> str:
    performance_source = Path(request["performance_cases"]) if request.get("performance_cases") else None
    functional_mode = request["functional"]["mode"]
    functional_cases = Path(request["functional"]["cases"]) if request["functional"].get("cases") else None
    if performance_source is None:
        raise ValueError("standard tuning mode requires performance cases")
    perf_full = output_dir / "performance-full-cases.csv"
    fields, perf_rows = freeze_csv(performance_source, perf_full)
    perf_indices, perf_details = select_rows(perf_rows, PERFORMANCE_LIMIT)
    perf_tuning_rows = [perf_rows[index] for index in perf_indices]
    perf_tuning = output_dir / "performance-tuning-cases.csv"
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
    manifest["collections"].update({
        "performance_full": collection(perf_full, perf_rows),
        "performance_tuning": collection(perf_tuning, perf_tuning_rows, perf_selection),
    })
    manifest["functional_preparation"] = {
        "status": "pending" if functional_mode == "generate" else "complete"
    }
    if functional_mode == "reuse_performance":
        full, acceptance = functional_payload(perf_full, output_dir)
        manifest["collections"].update({"functional_full": full, "functional_acceptance": acceptance})
    elif functional_mode == "existing":
        if functional_cases is None:
            raise ValueError("existing functional mode requires functional cases")
        full, acceptance = functional_payload(functional_cases, output_dir)
        manifest["collections"].update({"functional_full": full, "functional_acceptance": acceptance})
        manifest["inputs"]["functional_cases"] = {
            "path": str(functional_cases.resolve()),
            "kind": "directory" if functional_cases.is_dir() else "file",
            "sha256": full["sha256"],
            "identity_method": "frozen-copy",
        }
    return confirmation


def _freeze_generalization(manifest: dict, output_dir: Path, request: dict,
                           performance_source: Path | None, functional_cases: Path | None) -> str:
    if request["generalization"] is None:
        raise ValueError("generalization mode requires a generalization request")
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
        generalization_full, functional_full, acceptance = generalization_payload(case_source, output_dir)
        manifest["collections"].update({
            "generalization_full": generalization_full,
            "functional_full": functional_full,
            "functional_acceptance": acceptance,
        })
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
    competitor = request["generalization"]["competitor"]
    if competitor.get("performance") is None:
        return "not_applicable"
    competitor_source = Path(competitor["performance"])
    expected = (
        case_ids_from_collection(manifest["collections"]["generalization_full"])
        if "generalization_full" in manifest["collections"]
        else None
    )
    competitor_collection = competitor_payload(competitor_source, output_dir, expected)
    manifest["collections"]["competitor_performance"] = competitor_collection
    manifest["inputs"]["competitor_performance"] = identity(competitor_source)
    status = "complete" if competitor_collection["validation"]["status"] == "complete" else "pending_cases"
    manifest["generalization_preparation"]["competitor"] = {"status": status}
    return "not_applicable"


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
    manifest = _frozen_manifest(request, frozen_request, tuning_mode, code_dir, performance_source)
    if tuning_mode == "standard":
        confirmation = _freeze_standard(manifest, output_dir, args, request)
    else:
        confirmation = _freeze_generalization(manifest, output_dir, request,
                                              performance_source, functional_cases)
    path = output_dir / "run-manifest.json"
    atomic_json(path, manifest)
    emit(json.dumps({"status": "frozen", "manifest": str(path), "confirmation": confirmation}, ensure_ascii=False))
    return 0


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
    full, acceptance = functional_payload(args.functional_cases.resolve(), output_dir)
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
    generalization_full, functional_full, acceptance = generalization_payload(source, output_dir)
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
        validated = competitor_payload(Path(competitor["path"]), output_dir, expected)
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
    if configured.get("source") != "file":
        raise ValueError("attach-competitor requires a file competitor source")
    if configured.get("performance") is not None:
        raise ValueError("competitor performance is already configured; create a new run to replace it")
    if manifest["collections"].get("competitor_performance"):
        raise ValueError("competitor performance is already frozen; create a new run to replace it")
    generalization_full = manifest["collections"].get("generalization_full")
    if not generalization_full:
        raise ValueError("attach generalization cases before competitor performance")
    output_dir = args.manifest.resolve().parent
    expected = case_ids_from_collection(generalization_full)
    competitor = competitor_payload(args.competitor_perf.resolve(), output_dir, expected)
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


def _sub(subparsers, name: str, help_text: str, func) -> argparse.ArgumentParser:
    command = subparsers.add_parser(name, help=help_text)
    command.set_defaults(func=func)
    return command


def _add_create_args(create: argparse.ArgumentParser) -> None:
    create.add_argument("--request", type=Path, required=True)
    create.add_argument("--operator-name")
    create.add_argument("--code-dir", type=Path, required=True)
    create.add_argument("--tuning-mode", choices=TUNING_MODES, default="standard")
    create.add_argument("--target-soc", action="append", required=True,
                        help="verified optimization SoC; repeat only when every listed generation will be validated")
    create.add_argument("--performance-cases", type=Path)
    create.add_argument("--performance-reference", type=Path,
                        help="JSON reference kind, target_ratio and source configuration")
    create.add_argument("--functional-mode", choices=FUNCTIONAL_MODES)
    create.add_argument("--functional-cases", type=Path)
    create.add_argument("--target-case-count", type=int, default=DEFAULT_GENERALIZATION_CASE_COUNT)
    create.add_argument("--competitor-perf", type=Path)
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
    create.add_argument("--optimization-intent", choices=("safe_incremental", "pursue_optimal"),
                        default="safe_incremental",
                        help="safe_incremental: isolated increments in the current kernel structure. "
                        "pursue_optimal: structural rewrites (fusion / layout / precision scheme) are in scope and "
                        "unrealized structural directions block a clean success finish.")
    create.add_argument("--reference-perf", type=Path,
                        help="optional performance anchor: a case_id,ref_total_us CSV "
                        "(same-operator/competitor/ceiling reference implementation). "
                        "Analysis anchors 'measured vs reference' gap.")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    sub = result.add_subparsers(dest="command", required=True)
    _add_create_args(_sub(sub, "create-request",
                          "write a reusable, user-confirmed optimization request", command_create_request))
    validate_request = _sub(sub, "validate-request",
                            "validate a reusable request against current paths", command_validate_request)
    validate_request.add_argument("--request", type=Path, required=True)
    freeze = _sub(sub, "freeze", "freeze inputs and deterministic case subsets", command_freeze)
    freeze.add_argument("--output-dir", type=Path, required=True)
    freeze.add_argument("--request", type=Path, required=True)
    freeze.add_argument("--confirm-performance", action="store_true")
    confirm = _sub(sub, "confirm-performance",
                   "record user confirmation of >50 performance subset", command_confirm)
    confirm.add_argument("--manifest", type=Path, required=True)
    confirm.add_argument("--by", default="user")
    confirm.add_argument("--note")
    attach = _sub(sub, "attach-functional", "attach generated functional inventory", command_attach)
    attach.add_argument("--manifest", type=Path, required=True)
    attach.add_argument("--functional-cases", type=Path, required=True)
    generalization = _sub(sub, "attach-generalization",
                          "attach a generated performance/functional generalization inventory",
                          command_attach_generalization)
    generalization.add_argument("--manifest", type=Path, required=True)
    generalization.add_argument("--cases", type=Path, required=True)
    competitor = _sub(sub, "attach-competitor",
                      "attach externally collected competitor performance to a generalization run",
                      command_attach_competitor)
    competitor.add_argument("--manifest", type=Path, required=True)
    competitor.add_argument("--competitor-perf", type=Path, required=True)
    return result


def main() -> int:
    return run_cli(parser)


if __name__ == "__main__":
    raise SystemExit(main())
