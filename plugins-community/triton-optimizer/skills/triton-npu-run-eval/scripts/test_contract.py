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

import base64
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
import importlib
import importlib.util
import os
import pickle
import sys
from pathlib import Path
from typing import Any, cast

from env_registry import (
    HELIX_ACCURACY_MODE,
    HELIX_DTYPE_CLOSE_ATOL,
    HELIX_DTYPE_CLOSE_RTOL,
)
from torch_npu_warnings import bootstrap_torch_npu, temporary_sys_path_entries


# Shared with run_test_execution.py so dynamically loaded tests can import bundled helpers.
SCRIPT_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class DifferentialTestCase:
    case_id: str
    inputs: tuple[object, ...] | list[object]
    fn: Callable[[], object]


def load_differential_test_cases(
    test_file: Path,
    operator_file: Path,
    case_id: str | None = None,
    *,
    seed_payload: object | None = None,
) -> list[DifferentialTestCase]:
    test_path = test_file.resolve()
    operator_path = operator_file.resolve()
    bootstrap_torch_npu(test_path.parent, operator_path.parent)
    with temporary_sys_path_entries(test_path.parent, operator_path.parent, SCRIPT_DIR):
        test_module = load_module(test_path, f"differential_test_{test_path.stem}")
        if seed_payload is not None:
            archive_case_ids = seed_input_groups_from_payload(test_module, seed_payload)
        else:
            archive_case_ids = _load_input_groups_from_archive(
                test_module, _derive_input_archive(operator_path)
            )
        build_operator_api = require_callable(test_module, "build_operator_api", test_path)
        build_cases = require_callable(test_module, "build_differential_test_cases", test_path)
        operator_module = load_module(operator_path, f"differential_operator_{operator_path.stem}")
        raw_cases = build_cases(build_operator_api(operator_module))
    if archive_case_ids is not None and case_id is not None:
        return _select_archive_seeded_case(raw_cases, archive_case_ids, case_id)
    return normalize_differential_cases(raw_cases, case_id=case_id)


def _move_tree_to_npu(value: Any) -> Any:
    torch = cast(Any, importlib.import_module("torch"))
    if isinstance(value, torch.Tensor):
        return value.npu()
    if isinstance(value, list):
        return [_move_tree_to_npu(item) for item in cast(list[Any], value)]
    if isinstance(value, tuple):
        return tuple(_move_tree_to_npu(item) for item in cast(tuple[Any, ...], value))
    return value


def _move_tree_to_cpu(value: Any) -> Any:
    torch = cast(Any, importlib.import_module("torch"))
    if isinstance(value, torch.Tensor):
        return value.cpu() if value.is_npu else value
    if isinstance(value, list):
        return [_move_tree_to_cpu(item) for item in cast(list[Any], value)]
    if isinstance(value, tuple):
        return tuple(_move_tree_to_cpu(item) for item in cast(tuple[Any, ...], value))
    if isinstance(value, dict):
        return {key: _move_tree_to_cpu(item) for key, item in cast(dict[Any, Any], value).items()}
    return value


def move_payload_tensors_to_cpu(payload: object) -> None:
    """Move every NPU tensor in a differential payload's case records to CPU.

    Case inputs are already CPU snapshots; case results are NPU tensors kept
    for the comparison.  A caller that keeps the payload alive across further
    NPU work (the single-worker differential flow holds the reference payload
    through the candidate phase) calls this to release device memory; the
    comparison paths operate on CPU tensors either way.
    """
    cases = cast(Any, payload).get("cases") if isinstance(payload, Mapping) else None
    if not isinstance(cases, list):
        return
    for record in cast(list[Any], cases):
        _move_record_tensors_to_cpu(record)


def _move_record_tensors_to_cpu(record: object) -> None:
    if not isinstance(record, dict):
        return
    for key in ("inputs", "result"):
        if key in record:
            record[key] = _move_tree_to_cpu(record[key])


# Shared host: several tenants may load archives concurrently, and each one
# reads the same MemAvailable before anyone's load lands. Keep the per-process
# fraction small enough that ~10 simultaneous loads still cannot exhaust the box.
_ARCHIVE_LOAD_MAX_MEM_FRACTION = 0.05
_ARCHIVE_LOAD_FALLBACK_CAP_BYTES = 8 * 1024**3


def _mem_available_bytes() -> int | None:
    try:
        with open("/proc/meminfo") as fh:
            return _scan_mem_available_bytes(fh)
    except (OSError, ValueError, IndexError):
        return None


def _scan_mem_available_bytes(fh: object) -> int | None:
    for line in fh:
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) * 1024
    return None


def archive_load_size_allowed(archive_path: Path) -> bool:
    """Skip loading when the archive is too large to torch.load safely (RSS
    grows by roughly the file size; the small fraction assumes concurrent
    loads on a shared host all reading the same MemAvailable).
    """
    try:
        size = archive_path.stat().st_size
    except OSError:
        return False
    available = _mem_available_bytes()
    limit = (
        int(available * _ARCHIVE_LOAD_MAX_MEM_FRACTION)
        if available is not None
        else _ARCHIVE_LOAD_FALLBACK_CAP_BYTES
    )
    if size > limit:
        print(
            f"[run-test] input archive too large to load safely "
            f"({size / 1024**3:.1f} GiB > limit {limit / 1024**3:.1f} GiB); "
            "regenerating inputs instead",
            file=sys.stderr,
        )
        return False
    return True


def _input_groups_on_npu(groups: list[Any]) -> bool:
    """Loaded input groups may contain only tensors (already on NPU), lists,
    tuples, and scalars. Any other nesting (e.g. a dict, whose tensors
    _move_tree_to_npu cannot reach and which would stay on CPU) means the
    structure is unsupported — discard and let the build function
    regenerate normally."""
    torch = cast(Any, importlib.import_module("torch"))
    stack: list[Any] = list(groups)
    while stack:
        value = stack.pop()
        if isinstance(value, torch.Tensor):
            if not value.is_npu:
                return False
        elif isinstance(value, (list, tuple)):
            stack.extend(cast(Any, value))
        elif isinstance(value, Mapping):
            return False
    return True


def _derive_input_archive(operator_path: Path) -> Path | None:
    """The run-test contract pairs a candidate triton_<name>.py with the
    reference <name>.py in the same directory (references/run-test.md), and
    the reference archive is always <name>_result.pt beside it
    (_derived_result_path). Optimize rounds follow run-test-optimize:
    candidate opt_<ref>.py lives in a round directory (opt-round-N/) while
    the reference operator and its archive <ref>_result.pt sit in the
    workspace root one level up (references/artifacts.md round layout), so
    both directories are searched. Remote differential runs stage the pair
    flat as candidate_triton_<name>.py / reference_<name>.py (or
    candidate_opt_<ref>.py / reference_<ref>.py for optimize rounds) with
    the archive named reference_<name>_result.pt
    (run_remote_differential_comparison). Derive from whichever convention
    applies; anything off-contract means no archive reuse."""
    stem = operator_path.stem
    if stem.startswith("candidate_opt_"):
        archive_name = f"reference_{stem[len('candidate_opt_'):]}_result.pt"
        search_dirs = (operator_path.parent,)
    elif stem.startswith("candidate_triton_"):
        archive_name = f"reference_{stem[len('candidate_triton_'):]}_result.pt"
        search_dirs = (operator_path.parent,)
    elif stem.startswith("opt_"):
        archive_name = f"{stem[len('opt_'):]}_result.pt"
        search_dirs = (operator_path.parent, operator_path.parent.parent)
    elif stem.startswith("triton_"):
        archive_name = f"{stem[len('triton_'):]}_result.pt"
        search_dirs = (operator_path.parent,)
    else:
        return None
    for base in search_dirs:
        archive = base / archive_name
        if archive.is_file():
            return archive
    return None


def _load_input_groups_from_archive(
    test_module: object, archive_path: Path | None
) -> "list[str] | None":
    """Seed the test module's input-group cache from the reference result
    archive so the candidate worker skips regenerating identical inputs, and
    return the archive's case ids aligned by position with the seeded groups
    (None when the cache was not seeded). torch.save/load and the H2D copy
    are bitwise-exact; any inconsistency or unsupported structure silently
    falls back to normal generation."""
    if archive_path is None:
        return None
    # No cache hooks means there is nothing to seed: bail before the
    # GB-scale archive read, not after it.
    if not hasattr(test_module, "_GROUPS_CACHE") or not hasattr(test_module, "_GROUPS_LOADED"):
        return None
    try:
        if not archive_load_size_allowed(archive_path):
            return None
        torch = cast(Any, importlib.import_module("torch"))
        payload = torch.load(archive_path, map_location="cpu")
    except Exception:
        return None
    return seed_input_groups_from_payload(test_module, payload)


def seed_input_groups_from_payload(
    test_module: object, payload: object
) -> "list[str] | None":
    """Seed the test module's input-group cache from an in-memory payload.

    Same contract as _load_input_groups_from_archive, but the records come
    from a payload already in this process (the single-worker differential
    flow hands the reference phase's payload to the candidate phase, so
    unfixed-seed harnesses build bitwise-identical inputs without any
    archive on disk).
    """
    if not hasattr(test_module, "_GROUPS_CACHE") or not hasattr(test_module, "_GROUPS_LOADED"):
        return None
    try:
        records = cast(Any, payload).get("cases") if isinstance(payload, Mapping) else None
        if not records:
            return None
        groups: list[object] = []
        case_ids: list[str] = []
        for record in records:
            inputs = cast(Any, record).get("inputs") if isinstance(record, Mapping) else None
            if not isinstance(inputs, (list, tuple)):
                return None
            record_id = cast(Any, record).get("id") if isinstance(record, Mapping) else None
            if not isinstance(record_id, str) or not record_id.strip():
                return None
            groups.append(_move_tree_to_npu(list(cast(Any, inputs))))
            case_ids.append(record_id)
        if not _input_groups_on_npu(groups):
            return None
        setattr(test_module, "_GROUPS_CACHE", groups)
        setattr(test_module, "_GROUPS_LOADED", True)
    except Exception:
        return None
    return case_ids


def _select_archive_seeded_case(
    raw_cases: object,
    archive_case_ids: "list[str]",
    case_id: str,
) -> list[DifferentialTestCase]:
    """Select one case from an archive-seeded build. The harness numbers the
    seeded cases by position, so a filtered reference archive renumbers them
    (its single case-50 becomes case-01); realign the ids to the archive
    records so selection, case records, and the candidate archive all use
    the id the reference produced."""
    records = normalize_differential_case_records(raw_cases)
    if len(records) != len(archive_case_ids):
        raise ValueError(
            f"Archive seeded {len(archive_case_ids)} input group(s) but the test "
            f"harness built {len(records)} case(s); case ids cannot be aligned "
            f"for case-id selection"
        )
    aligned = [
        {**record, "id": archive_id}
        for record, archive_id in zip(records, archive_case_ids)
    ]
    return normalize_differential_cases(aligned, case_id=case_id)


def normalize_differential_cases(
    raw_cases: object,
    *,
    case_id: str | None = None,
) -> list[DifferentialTestCase]:
    selected = select_differential_case_records(
        normalize_differential_case_records(raw_cases), case_id
    )
    cases: list[DifferentialTestCase] = []
    for record in selected:
        cases.append(
            DifferentialTestCase(
                case_id=cast(str, record["id"]),
                inputs=cast(Any, record["inputs"]),
                fn=cast(Callable[[], object], record["fn"]),
            )
        )
    return cases


def normalize_differential_case_records(raw_cases: object) -> list[dict[str, object]]:
    if isinstance(raw_cases, (str, bytes)) or isinstance(raw_cases, Mapping) or not isinstance(raw_cases, Iterable):
        raise ValueError("Differential test hook 'build_differential_test_cases' must return an iterable of cases")
    records: list[dict[str, object]] = []
    seen_case_ids: set[str] = set()
    for raw_case in cast(Iterable[object], raw_cases):
        if not isinstance(raw_case, Mapping):
            raise ValueError("Differential test cases must be mappings")
        case_map = cast(Mapping[str, object], raw_case)
        record_id = case_map.get("id")
        if not isinstance(record_id, str) or not record_id.strip():
            raise ValueError("Differential test case is missing required string field 'id'")
        if record_id in seen_case_ids:
            raise ValueError(f"Duplicate differential test case id: {record_id}")
        raw_inputs = case_map.get("inputs")
        if not isinstance(raw_inputs, (list, tuple)):
            raise ValueError(
                f"Differential test case '{record_id}' is missing required list/tuple field 'inputs'"
            )
        case_fn = case_map.get("fn")
        if not callable(case_fn):
            raise ValueError(f"Differential test case '{record_id}' is missing required callable field 'fn'")
        seen_case_ids.add(record_id)
        inputs: tuple[object, ...] | list[object]
        if isinstance(raw_inputs, tuple):
            inputs = tuple(cast(tuple[object, ...], raw_inputs))
        else:
            inputs = list(cast(list[object], raw_inputs))
        records.append({"id": record_id, "inputs": inputs, "fn": case_fn})
    if not records:
        raise ValueError("Differential test hook 'build_differential_test_cases' returned no cases")
    return records


def select_differential_case_records(
    case_records: list[dict[str, object]], case_id: str | None
) -> list[dict[str, object]]:
    if case_id is None:
        return case_records
    for case_record in case_records:
        if case_record["id"] == case_id:
            return [case_record]
    available = ", ".join(cast(str, record["id"]) for record in case_records)
    raise ValueError(f"Unknown differential test case id '{case_id}'. Available case ids: {available}")


def load_module(module_path: Path, module_name: str) -> Any:
    spec = importlib.util.spec_from_file_location(f"{module_name}_{module_path.stem}", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


def require_callable(
    module: object,
    name: str,
    source_path: Path,
    *,
    kind: str = "Differential test module",
) -> Callable[..., Any]:
    candidate = getattr(module, name, None)
    if not callable(candidate):
        raise ValueError(f"{kind} missing required hook '{name}': {source_path}")
    return cast(Callable[..., Any], candidate)


def compute_flag_from_metadata(metadata: Mapping[str, str]) -> bool:
    return parse_compute_kind(metadata.get("compute-kind"))


def parse_compute_kind(raw_value: object) -> bool:
    if raw_value is None:
        return True
    if not isinstance(raw_value, str):
        raise ValueError("Test metadata 'compute-kind' must be 'compute' or 'non-compute'")
    normalized = raw_value.strip().lower()
    if normalized == "compute":
        return True
    if normalized == "non-compute":
        return False
    raise ValueError("Test metadata 'compute-kind' must be 'compute' or 'non-compute'")


def run_test_accuracy_env(accuracy_mode: str | None = None) -> dict[str, str]:
    extra_env: dict[str, str] = {}
    if accuracy_mode is not None:
        extra_env[HELIX_ACCURACY_MODE] = accuracy_mode
    for name in (HELIX_ACCURACY_MODE, HELIX_DTYPE_CLOSE_ATOL, HELIX_DTYPE_CLOSE_RTOL):
        if name not in extra_env and (value := os.environ.get(name)) is not None:
            extra_env[name] = value
    return extra_env


def normalize_payload_for_serialization(payload: object) -> object:
    try:
        torch_module = importlib.import_module("torch")
    except ImportError:
        torch_module = None

    def normalize(value: object) -> object:
        tensor_type = None if torch_module is None else getattr(torch_module, "Tensor", None)
        if isinstance(tensor_type, type) and isinstance(value, tensor_type):
            tensor_like = cast(Any, value)
            detached = cast(object, tensor_like.detach()) if hasattr(tensor_like, "detach") else value
            to_cpu = getattr(cast(Any, detached), "cpu", None)
            return to_cpu() if callable(to_cpu) else detached
        if isinstance(value, Mapping):
            return {key: normalize(item) for key, item in cast(Mapping[object, object], value).items()}
        if isinstance(value, tuple):
            tuple_value = cast(tuple[object, ...], value)
            items = tuple(normalize(item) for item in tuple_value)
            if hasattr(tuple_value, "_fields"):
                named_tuple_type = cast(Any, type(tuple_value))
                return cast(object, named_tuple_type(*items))
            return items
        if isinstance(value, list):
            return [normalize(item) for item in cast(list[object], value)]
        return value

    return normalize(payload)


def serialize_payload_object(payload: object) -> str:
    normalized = normalize_payload_for_serialization(payload)
    return base64.b64encode(pickle.dumps(normalized)).decode("ascii")


def deserialize_payload_object(serialized_payload: str) -> object:
    return pickle.loads(base64.b64decode(serialized_payload.encode("ascii")))
