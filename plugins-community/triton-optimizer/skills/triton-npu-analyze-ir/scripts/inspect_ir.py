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


from __future__ import annotations

import argparse
import difflib
import json
import re
from pathlib import Path
from typing import NamedTuple, TypedDict, cast


KEYWORDS: tuple[str, ...] = (
    "alloc",
    "copy",
    "matmul",
    "for",
    "if",
    "vector",
    "load",
    "store",
    "dma",
    "wait",
    "set_flag",
    "barrier",
)


class StageInfo(NamedTuple):
    path: Path
    relative_path: str
    stem: str
    size_bytes: int
    line_count: int


_StageChange = TypedDict(
    "_StageChange",
    {
        "from": StageInfo,
        "to": StageInfo,
        "line_delta": int,
        "size_delta": int,
        "keyword_deltas": dict[str, int],
        "score": int,
    },
)


class _StageSignalSummary(TypedDict):
    stage: str
    path: str
    line_count: int
    size_bytes: int
    vector_ops: int
    transfer_ops: int
    sync_ops: int
    alloc_ops: int
    interesting_score: int


class _SuspiciousTransition(TypedDict):
    from_stage: str
    to_stage: str
    signal_score: int
    vector_delta: int
    transfer_delta: int
    sync_delta: int
    line_delta: int
    size_delta: int


class _IndirectAccessSignal(TypedDict):
    stage: str
    path: str
    indirect_loads: int
    indirect_stores: int
    evidence: list[str]


def resolve_stages_dir(ir_dir: str | Path) -> Path:
    ir_path = Path(ir_dir).expanduser().resolve()
    if not ir_path.exists():
        raise FileNotFoundError(f"IR directory does not exist: {ir_path}")
    if not ir_path.is_dir():
        raise FileNotFoundError(f"IR path is not a directory: {ir_path}")
    stages_dir = ir_path / "bishengir_stages"
    if not stages_dir.is_dir():
        kernel_root = ir_path / "kernels"
        kernel_stage_dirs = sorted(
            path for path in kernel_root.glob("*/bishengir_stages") if path.is_dir()
        )
        if kernel_stage_dirs:
            keys = ", ".join(path.parent.name for path in kernel_stage_dirs)
            raise FileNotFoundError(
                "IR directory contains kernel bundles (directories): "
                f"{ir_path}. Choose one of: {keys} (for example "
                f"{ir_path / 'kernels' / kernel_stage_dirs[0].parent.name})."
            )
        if any((child / "bishengir_stages").is_dir() for child in ir_path.iterdir() if child.is_dir()):
            raise FileNotFoundError(
                "IR directory is a capture parent, not an exact capture archive: "
                f"{ir_path}. Pass the `IR archive:` path printed by capture_ir.py."
            )
        raise FileNotFoundError(f"IR directory is missing bishengir_stages/: {ir_path}")
    return stages_dir


def discover_archive_stages(ir_dir: str | Path) -> list[StageInfo]:
    ir_path = Path(ir_dir).expanduser().resolve()
    stage_infos = discover_stages(resolve_stages_dir(ir_path))
    pass_order_path = ir_path / "pass-order.json"
    if not pass_order_path.is_file():
        return stage_infos

    raw_payload = json.loads(pass_order_path.read_text(encoding="utf-8"))
    if not isinstance(raw_payload, dict):
        raise ValueError(f"Pass-order artifact is not a JSON object: {pass_order_path}")
    payload = cast(dict[str, object], raw_payload)
    raw_passes = payload.get("passes")
    if not isinstance(raw_passes, list):
        raise ValueError(f"Pass-order artifact has no 'passes' list: {pass_order_path}")
    passes = cast(list[object], raw_passes)

    by_relative_path = {
        (Path("bishengir_stages") / info.relative_path).as_posix(): info
        for info in stage_infos
    }
    ordered: list[StageInfo] = []
    included: set[str] = set()
    for raw_entry in passes:
        if not isinstance(raw_entry, dict):
            continue
        entry = cast(dict[str, object], raw_entry)
        if entry.get("match") != "sha256":
            continue
        raw_stage_paths = entry.get("stage_paths")
        if not isinstance(raw_stage_paths, list):
            continue
        stage_paths = cast(list[object], raw_stage_paths)
        for stage_path in stage_paths:
            if not isinstance(stage_path, str) or stage_path in included:
                continue
            info = by_relative_path.get(stage_path)
            if info is not None:
                ordered.append(info)
                included.add(stage_path)
    ordered.extend(info for info in stage_infos if info.relative_path not in included)
    return ordered


def discover_stages(stages_dir: str | Path) -> list[StageInfo]:
    root = Path(stages_dir).expanduser().resolve()
    stage_files = sorted(root.rglob("*.mlir"), key=lambda path: _stage_sort_key(root, path))
    if not stage_files:
        raise FileNotFoundError(f"No .mlir stages found under {root}")
    return [_build_stage_info(root, path) for path in stage_files]


def resolve_stage_selector(stages_dir: str | Path, selector: str) -> Path:
    stage_infos = discover_stages(stages_dir)
    normalized = selector.strip().removesuffix(".mlir")
    exact_rel_matches = [
        info.path
        for info in stage_infos
        if info.relative_path.removesuffix(".mlir") == normalized
    ]
    if len(exact_rel_matches) == 1:
        return exact_rel_matches[0]

    exact_stem_matches = [info.path for info in stage_infos if info.stem == normalized]
    if len(exact_stem_matches) == 1:
        return exact_stem_matches[0]

    substring_matches = [
        info.path
        for info in stage_infos
        if normalized in info.stem or normalized in info.relative_path.removesuffix(".mlir")
    ]
    if len(substring_matches) == 1:
        return substring_matches[0]
    if not substring_matches:
        raise FileNotFoundError(f"No stage matches selector: {selector}")
    raise ValueError(
        "Stage selector is ambiguous: "
        f"{selector} -> {', '.join(path.name for path in substring_matches[:5])}"
    )


def list_stages_text(
    ir_dir: str | Path,
    *,
    grep: str | None = None,
    limit: int | None = None,
    sort_by: str = "order",
) -> str:
    stage_infos = discover_archive_stages(ir_dir)
    if grep:
        pattern = re.compile(grep)
        stage_infos = [
            info
            for info in stage_infos
            if pattern.search(info.stem) or pattern.search(info.relative_path)
        ]
    stage_infos = _sort_stage_infos(stage_infos, sort_by=sort_by)
    if limit is not None:
        stage_infos = stage_infos[:limit]
    if not stage_infos:
        return "No stages matched.\n"

    lines = ["Stages:"]
    for info in stage_infos:
        prefix = f"{info.stem:<36} {_format_size(info.size_bytes):>6}"
        if sort_by == "interesting":
            score = _interesting_score(_keyword_counts(info.path.read_text(encoding="utf-8")))
            prefix = f"{prefix}  score={score}"
        lines.append(f"{prefix}  {info.relative_path}")
    return "\n".join(lines) + "\n"


def stage_summary_text(ir_dir: str | Path, selector: str) -> str:
    stages_dir = resolve_stages_dir(ir_dir)
    stage_path = resolve_stage_selector(stages_dir, selector)
    info = _build_stage_info(stages_dir, stage_path)
    text = stage_path.read_text(encoding="utf-8")
    counts = _keyword_counts(text)
    highlights = _stage_highlights(text)

    lines = [
        f"Stage: {info.stem}",
        f"Path: {info.relative_path}",
        f"Size: {_format_size(info.size_bytes)}",
        f"Lines: {info.line_count}",
        "",
        "Keyword counts:",
    ]
    for keyword in KEYWORDS:
        lines.append(f"- {keyword}: {counts[keyword]}")
    lines.extend(
        [
            "",
            "Highlights:",
        ]
    )
    if highlights:
        lines.extend(f"- {line}" for line in highlights)
    else:
        lines.append("- No highlight lines matched the default heuristics.")
    return "\n".join(lines) + "\n"


def diff_stages_text(
    ir_dir: str | Path,
    *,
    from_selector: str,
    to_selector: str,
    context: int = 2,
) -> str:
    stages_dir = resolve_stages_dir(ir_dir)
    from_path = resolve_stage_selector(stages_dir, from_selector)
    to_path = resolve_stage_selector(stages_dir, to_selector)
    from_info = _build_stage_info(stages_dir, from_path)
    to_info = _build_stage_info(stages_dir, to_path)
    from_text = from_path.read_text(encoding="utf-8")
    to_text = to_path.read_text(encoding="utf-8")
    from_counts = _keyword_counts(from_text)
    to_counts = _keyword_counts(to_text)

    diff_lines = list(
        difflib.unified_diff(
            from_text.splitlines(),
            to_text.splitlines(),
            fromfile=from_info.relative_path,
            tofile=to_info.relative_path,
            lineterm="",
            n=context,
        )
    )

    lines = [
        f"From: {from_info.stem}",
        f"To: {to_info.stem}",
        f"Line delta: {to_info.line_count - from_info.line_count:+d}",
        f"Size delta: {to_info.size_bytes - from_info.size_bytes:+d} bytes",
        "",
        "Keyword deltas:",
    ]
    for keyword in KEYWORDS:
        delta = to_counts[keyword] - from_counts[keyword]
        lines.append(f"- {keyword}: {delta:+d} ({from_counts[keyword]} -> {to_counts[keyword]})")
    lines.extend(["", "Unified diff:"])
    if diff_lines:
        lines.extend(diff_lines)
    else:
        lines.append("(no textual differences)")
    return "\n".join(lines) + "\n"


def find_changes_text(
    ir_dir: str | Path,
    *,
    limit: int | None = None,
    sort_by: str = "score",
) -> str:
    stage_infos = discover_archive_stages(ir_dir)
    changes = _adjacent_stage_changes(stage_infos)
    changes = _sort_stage_changes(changes, sort_by=sort_by)
    if limit is not None:
        changes = changes[:limit]
    if not changes:
        return "No adjacent stage changes found.\n"

    lines = ["Adjacent stage changes:"]
    for change in changes:
        lines.append(
            f"{change['from'].stem} -> {change['to'].stem}  "
            f"score={change['score']}  lines={change['line_delta']:+d}  size={change['size_delta']:+d}B"
        )
        lines.append(f"  keyword deltas: {_format_keyword_delta_summary(change['keyword_deltas'])}")
    return "\n".join(lines) + "\n"


def performance_signals_text(
    ir_dir: str | Path,
    *,
    limit: int | None = None,
    output_format: str = "text",
) -> str:
    payload = build_performance_signals_payload(ir_dir, limit=limit)
    if output_format == "json":
        return json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if output_format != "text":
        raise ValueError(f"Unsupported output format: {output_format}")

    lines = ["Performance signals:"]
    _append_stage_section(lines, "Vector-heavy stages", payload["vector_heavy_stages"])
    _append_stage_section(lines, "Transfer-heavy stages", payload["transfer_heavy_stages"])
    _append_stage_section(lines, "Sync-heavy stages", payload["sync_heavy_stages"])
    _append_transition_section(lines, payload["suspicious_transitions"])
    _append_indirect_section(lines, payload["indirect_access_signals"])
    return "\n".join(lines) + "\n"


def _append_stage_section(lines: list[str], title: str, stages: object) -> None:
    lines.extend(["", f"{title}:"])
    lines.extend(_render_signal_stage_lines(stages))


def _append_transition_section(lines: list[str], transitions: object) -> None:
    lines.extend(["", "Suspicious transitions:"])
    for change in cast(list[dict[str, object]], transitions or []):
        lines.append(
            f"- {change['from_stage']} -> {change['to_stage']} "
            f"(score={change['signal_score']}, vector_delta={change['vector_delta']:+d}, "
            f"transfer_delta={change['transfer_delta']:+d}, sync_delta={change['sync_delta']:+d})"
        )


def _append_indirect_section(lines: list[str], signals: object) -> None:
    lines.extend(["", "Indirect-access stages:"])
    items = cast(list[dict[str, object]], signals)
    if not items:
        lines.append("- No indirect load/store stages found.")
        return
    for signal in items:
        lines.append(
            f"- {signal['stage']} "
            f"(loads={signal['indirect_loads']}, stores={signal['indirect_stores']})"
        )
        lines.extend(f"  evidence: {entry}" for entry in cast(list[str], signal["evidence"]))


class _PerformanceSignalsPayload(TypedDict):
    stage_summaries: list[_StageSignalSummary]
    vector_heavy_stages: list[_StageSignalSummary]
    transfer_heavy_stages: list[_StageSignalSummary]
    sync_heavy_stages: list[_StageSignalSummary]
    suspicious_transitions: list[_SuspiciousTransition]
    indirect_access_signals: list[_IndirectAccessSignal]


def build_performance_signals_payload(
    ir_dir: str | Path,
    *,
    limit: int | None = None,
) -> _PerformanceSignalsPayload:
    stage_infos = discover_archive_stages(ir_dir)
    stage_summaries = [_stage_signal_summary(info) for info in stage_infos]
    suspicious_transitions = _suspicious_transitions(stage_infos)
    indirect_access_signals = _indirect_access_signals(stage_infos)
    if limit is not None:
        suspicious_transitions = suspicious_transitions[:limit]
        indirect_access_signals = indirect_access_signals[:limit]

    sorted_vector = sorted(
        [summary for summary in stage_summaries if summary["vector_ops"] > 0],
        key=lambda item: (-item["vector_ops"], str(item["stage"])),
    )
    sorted_transfer = sorted(
        [summary for summary in stage_summaries if summary["transfer_ops"] > 0],
        key=lambda item: (-item["transfer_ops"], str(item["stage"])),
    )
    sorted_sync = sorted(
        [summary for summary in stage_summaries if summary["sync_ops"] > 0],
        key=lambda item: (-item["sync_ops"], str(item["stage"])),
    )

    if limit is not None:
        stage_summaries = stage_summaries[:]
        sorted_vector = sorted_vector[:limit]
        sorted_transfer = sorted_transfer[:limit]
        sorted_sync = sorted_sync[:limit]

    return {
        "stage_summaries": stage_summaries,
        "vector_heavy_stages": sorted_vector,
        "transfer_heavy_stages": sorted_transfer,
        "sync_heavy_stages": sorted_sync,
        "suspicious_transitions": suspicious_transitions,
        "indirect_access_signals": indirect_access_signals,
    }


def pipeline_structure_payload(ir_dir: str | Path, *, kernel: str | None = None) -> dict[str, object]:
    """Extract conservative, source-cited Triton pipeline structure facts."""
    root = Path(ir_dir).expanduser().resolve()
    source_path = _select_pipeline_source(root, kernel)
    source_text = source_path.read_text(encoding="utf-8") if source_path else ""
    source_rel = source_path.relative_to(root).as_posix() if source_path else None
    source_lines = source_text.splitlines()
    matrix_lines = _matching_lines(source_lines, ("tt.dot", "tt.matmul", "linalg.matmul", "mmadl"))
    vector_lines = _matching_lines(source_lines, ("tt.reduce", "vector."))
    transfer_lines = _matching_lines(source_lines, ("tt.load", "tt.store", "copy", "dma"))
    family = _engine_family(matrix_lines, vector_lines, transfer_lines)
    loop_line, loop = _first_loop(source_lines)
    tile = _tile_from_matrix_line(source_lines, matrix_lines[0] if matrix_lines else None)
    manifest = _load_manifest(root)
    dimensions = _manifest_dimensions(manifest)
    k_trip = _k_trip_count(loop, dimensions.get("k"))
    grid = _grid_structure(dimensions, tile)
    target_path, target_line, target_cores = _find_target_cores(root)
    coordination = _pipeline_coordination(root)
    loop_body = _loop_body_signals(source_lines, loop_line)
    evidence_gaps: list[str] = []
    if source_path is None:
        evidence_gaps.append("No unambiguous Triton source stage contains the selected kernel and compute operation.")
    if k_trip["value"] is None:
        evidence_gaps.append("K-loop bound is dynamic and capture metadata does not provide a resolved K value.")
    if target_cores is None:
        evidence_gaps.append("No AI_CORE_COUNT target declaration was found.")
    return {
        "kernel": kernel or _kernel_name(source_text),
        "engine_family": family,
        "source_stage": source_rel,
        "target": {"ai_core_count": target_cores, "source": _source_ref(root, target_path, target_line)},
        "compute_structure": {
            "tile_m": tile[0], "tile_n": tile[1], "tile_k": tile[2],
            "k_trip_count": k_trip, "source": _source_ref(root, source_path, loop_line),
        },
        "launch_grid": grid,
        "loop_body": dict(loop_body, source=_source_ref(root, source_path, loop_line)),
        "pipeline_coordination": coordination,
        "evidence_gaps": evidence_gaps,
    }


def pipeline_structure_text(ir_dir: str | Path, *, kernel: str | None = None, output_format: str = "text") -> str:
    payload = pipeline_structure_payload(ir_dir, kernel=kernel)
    if output_format == "json":
        return json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if output_format != "text":
        raise ValueError(f"Unsupported output format: {output_format}")
    tile = cast(dict[str, object], payload["compute_structure"])
    trip = cast(dict[str, object], tile["k_trip_count"])
    target = cast(dict[str, object], payload["target"])
    coordination = cast(dict[str, object], payload["pipeline_coordination"])
    lines = [
        "Pipeline structure:",
        f"- Kernel: `{payload['kernel'] or 'unknown'}`",
        f"- Engine family: `{payload['engine_family']}`",
        f"- Source stage: `{payload['source_stage'] or 'unknown'}`",
        f"- Tile: `{tile['tile_m']}x{tile['tile_n']}x{tile['tile_k']}`",
        f"- K loop: `{trip['value'] if trip['value'] is not None else trip['formula']}`",
        f"- AI Core count: `{target['ai_core_count']}`",
        f"- Coordination: `{coordination['status']}` (does not prove timed overlap)",
    ]
    gaps = cast(list[str], payload["evidence_gaps"])
    if gaps:
        lines.append("- Evidence gaps: " + "; ".join(gaps))
    return "\n".join(lines) + "\n"


def _select_pipeline_source(root: Path, kernel: str | None) -> Path | None:
    candidates = sorted((root / "triton_dump").rglob("*.mlir")) if (root / "triton_dump").is_dir() else []
    ranked: list[tuple[int, Path]] = []
    for path in candidates:
        text = path.read_text(encoding="utf-8")
        if kernel and kernel not in text:
            continue
        if not any(marker in text.lower() for marker in ("tt.dot", "tt.matmul", "scf.for", "tt.load")):
            continue
        rank = 0 if path.name.endswith(".ttadapter.mlir") else 1 if path.name.endswith(".ttir.mlir") else 2
        ranked.append((rank, path))
    if not ranked:
        return None
    best_rank = min(rank for rank, _path in ranked)
    best = [path for rank, path in ranked if rank == best_rank]
    return best[0] if len(best) == 1 else None


def _matching_lines(lines: list[str], needles: tuple[str, ...]) -> list[int]:
    return [index + 1 for index, line in enumerate(lines) if any(needle in line.lower() for needle in needles)]


def _first_loop(lines: list[str]) -> tuple[int | None, str | None]:
    for index, line in enumerate(lines):
        if "scf.for" in line:
            return index + 1, line
    return None, None


def _tile_from_matrix_line(lines: list[str], line_number: int | None) -> tuple[int | None, int | None, int | None]:
    if line_number is None:
        return None, None, None
    sizes = re.findall(r"tensor<(\d+)x(\d+)x", lines[line_number - 1])
    if len(sizes) >= 2:
        left, right = sizes[0], sizes[1]
        return int(left[0]), int(right[1]), int(left[1])
    return None, None, None


def _load_manifest(root: Path) -> dict[str, object]:
    path = root / "capture-manifest.json"
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return cast(dict[str, object], raw) if isinstance(raw, dict) else {}


def _manifest_dimensions(manifest: dict[str, object]) -> dict[str, int]:
    result: dict[str, int] = {}
    resolved = manifest.get("resolved_case")
    if not isinstance(resolved, dict):
        return result
    resolved_case = cast(dict[str, object], resolved)

    def visit(value: object) -> None:
        if isinstance(value, dict):
            mapping = cast(dict[object, object], value)
            for key, item in mapping.items():
                lowered = str(key).lower()
                if lowered in ("m", "n", "k") and isinstance(item, int):
                    result[lowered] = item
                visit(item)
        elif isinstance(value, list):
            for item in cast(list[object], value):
                visit(item)
    visit(resolved_case.get("resolved_shape"))
    visit(resolved_case.get("case_data"))
    return result


def _k_trip_count(loop: str | None, resolved_k: int | None) -> dict[str, object]:
    if loop is None:
        return {"formula": "unknown", "value": None, "steady_state": "unknown"}
    step_match = re.search(r"step %c(\d+)", loop)
    bound_match = re.search(r"to %c(\d+)", loop)
    step = int(step_match.group(1)) if step_match else None
    bound = int(bound_match.group(1)) if bound_match else resolved_k
    formula = f"ceil(K / {step})" if step else "unknown"
    value = (bound + step - 1) // step if bound is not None and step else None
    if value is None:
        steady = "unknown"
    elif value < 8:
        steady = "limited_steady_state"
    elif value < 16:
        steady = "moderate_steady_state"
    else:
        steady = "steady_state"
    return {"formula": formula, "value": value, "steady_state": steady}


def _grid_structure(dimensions: dict[str, int], tile: tuple[int | None, int | None, int | None]) -> dict[str, object]:
    m, n, _k = tile
    resolved_dims = dimensions.get("m") and dimensions.get("n")
    if m and n and resolved_dims:
        grid = (dimensions["m"] + m - 1) // m * ((dimensions["n"] + n - 1) // n)
        return {
            "blocks": grid,
            "formula": f"ceil(M / {m}) * ceil(N / {n})",
            "source": "capture-manifest.json resolved_case",
        }
    return {"blocks": None, "formula": f"ceil(M / {m}) * ceil(N / {n})" if m and n else "unknown", "source": None}


def _engine_family(matrix_lines: list[int], vector_lines: list[int], transfer_lines: list[int]) -> str:
    if matrix_lines and vector_lines:
        return "mixed"
    if matrix_lines:
        return "cube"
    if vector_lines:
        return "vector"
    if transfer_lines:
        return "transfer"
    return "unknown"


def _find_target_cores(root: Path) -> tuple[Path | None, int | None, int | None]:
    candidates = sorted(root.rglob("*.mlir"))
    for path in candidates:
        for index, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
            match = re.search(r'"AI_CORE_COUNT",\s*(\d+)', line)
            if match:
                return path, index + 1, int(match.group(1))
    return None, None, None


def _pipeline_coordination(root: Path) -> dict[str, object]:
    for path in discover_archive_stages(root):
        lines = path.path.read_text(encoding="utf-8").splitlines()
        pairs: set[tuple[str, str, str]] = set()
        sets: set[tuple[str, str, str]] = set()
        waits: set[tuple[str, str, str]] = set()
        refs: list[dict[str, object]] = []
        for index, line in enumerate(lines):
            match = re.search(r"hivm\.hir\.(set_flag|wait_flag)\[<([^>]+)>, <([^>]+)>, <([^>]+)>\]", line)
            if not match:
                continue
            item = (match.group(2), match.group(3), match.group(4))
            (sets if match.group(1) == "set_flag" else waits).add(item)
            refs.append({"path": (Path("bishengir_stages") / path.relative_path).as_posix(), "line": index + 1})
        pairs = sets & waits
        matrix_mte = [item for item in pairs if "PIPE_M" in item[0] or "PIPE_M" in item[1]]
        if matrix_mte:
            return {
                "status": "handshake_present",
                "mte_to_matrix_event_pairs": len(matrix_mte),
                "alternating_event_ids": len({item[2] for item in matrix_mte}) > 1,
                "proves_timed_overlap": False,
                "source": refs,
            }
    return {
        "status": "none",
        "mte_to_matrix_event_pairs": 0,
        "alternating_event_ids": False,
        "proves_timed_overlap": False,
        "source": [],
    }


def _loop_body_signals(lines: list[str], loop_line: int | None) -> dict[str, object]:
    if loop_line is None:
        return {
            "input_loads": None,
            "matrix_ops": None,
            "output_transfers_inside_loop": None,
            "boundary_path_present": "unknown",
        }
    body_lines = _loop_body_lines(lines, loop_line)
    if body_lines is None:
        return {
            "input_loads": None,
            "matrix_ops": None,
            "output_transfers_inside_loop": None,
            "boundary_path_present": "unknown",
        }
    body = "\n".join(body_lines)
    lowered = body.lower()
    return {
        "input_loads": lowered.count("tt.load") + lowered.count("memref.copy"),
        "matrix_ops": lowered.count("tt.dot") + lowered.count("linalg.matmul") + lowered.count("mmadl"),
        "output_transfers_inside_loop": lowered.count("tt.store"),
        "boundary_path_present": "tt.if" in lowered or "scf.if" in lowered,
    }


def _loop_body_lines(lines: list[str], loop_line: int) -> list[str] | None:
    """Return exactly one brace-delimited loop body, including nested regions."""
    start = loop_line - 1
    depth = 0
    body: list[str] = []
    for index in range(start, len(lines)):
        line = lines[index]
        depth += line.count("{") - line.count("}")
        body.append(line)
        if index > start and depth == 0:
            return body
    return None


def _source_ref(root: Path, path: Path | None, line: int | None) -> dict[str, object] | None:
    return {"path": path.relative_to(root).as_posix(), "line": line} if path is not None and line is not None else None


def _kernel_name(text: str) -> str | None:
    match = re.search(r"(?:tt\.|func\.)func\s+@([A-Za-z0-9_]+)", text)
    return match.group(1) if match else None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect archived Triton Ascend IR stages.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list-stages")
    list_parser.add_argument("--ir-dir", required=True)
    list_parser.add_argument("--grep")
    list_parser.add_argument("--limit", type=int)
    list_parser.add_argument(
        "--sort-by",
        choices=["order", "size", "lines", "interesting"],
        default="order",
    )

    summary_parser = subparsers.add_parser("stage-summary")
    summary_parser.add_argument("--ir-dir", required=True)
    summary_parser.add_argument("--stage", required=True)

    diff_parser = subparsers.add_parser("diff-stages")
    diff_parser.add_argument("--ir-dir", required=True)
    diff_parser.add_argument("--from", dest="from_selector", required=True)
    diff_parser.add_argument("--to", dest="to_selector", required=True)
    diff_parser.add_argument("--context", type=int, default=2)

    changes_parser = subparsers.add_parser("find-changes")
    changes_parser.add_argument("--ir-dir", required=True)
    changes_parser.add_argument("--limit", type=int)
    changes_parser.add_argument(
        "--sort-by",
        choices=["score", "lines", "size"],
        default="score",
    )

    signals_parser = subparsers.add_parser("performance-signals")
    signals_parser.add_argument("--ir-dir", required=True)
    signals_parser.add_argument("--limit", type=int)
    signals_parser.add_argument(
        "--format",
        dest="output_format",
        choices=("text", "json"),
        default="text",
    )

    pipeline_parser = subparsers.add_parser("pipeline-structure")
    pipeline_parser.add_argument("--ir-dir", required=True)
    pipeline_parser.add_argument("--kernel")
    pipeline_parser.add_argument("--format", dest="output_format", choices=("text", "json"), default="text")

    return parser


def _dispatch_command(args: argparse.Namespace) -> str:
    if args.command == "list-stages":
        return list_stages_text(args.ir_dir, grep=args.grep, limit=args.limit, sort_by=args.sort_by)
    if args.command == "stage-summary":
        return stage_summary_text(args.ir_dir, args.stage)
    if args.command == "find-changes":
        return find_changes_text(args.ir_dir, limit=args.limit, sort_by=args.sort_by)
    if args.command == "performance-signals":
        return performance_signals_text(args.ir_dir, limit=args.limit, output_format=args.output_format)
    if args.command == "pipeline-structure":
        return pipeline_structure_text(args.ir_dir, kernel=args.kernel, output_format=args.output_format)
    return diff_stages_text(
        args.ir_dir,
        from_selector=args.from_selector,
        to_selector=args.to_selector,
        context=args.context,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        print(_dispatch_command(args), end="")
        return 0
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(str(exc))
        return 1


def _build_stage_info(stages_dir: Path, path: Path) -> StageInfo:
    relative_path = path.relative_to(stages_dir).as_posix()
    text = path.read_text(encoding="utf-8")
    return StageInfo(
        path=path,
        relative_path=relative_path,
        stem=path.stem,
        size_bytes=path.stat().st_size,
        line_count=len(text.splitlines()),
    )


def _stage_sort_key(stages_dir: Path, path: Path) -> tuple[int, str, str]:
    stem = path.stem
    match = re.match(r"(\d+)_", stem)
    order = int(match.group(1)) if match else 10**9
    relative = path.relative_to(stages_dir).as_posix()
    return (order, stem, relative)


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes}B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f}K"
    return f"{size_bytes / (1024 * 1024):.1f}M"


def _keyword_counts(text: str) -> dict[str, int]:
    lowered = text.lower()
    return {keyword: lowered.count(keyword.lower()) for keyword in KEYWORDS}


def _interesting_score(counts: dict[str, int]) -> int:
    weights = {
        "alloc": 3,
        "copy": 4,
        "matmul": 5,
        "for": 1,
        "if": 1,
        "vector": 3,
        "load": 2,
        "store": 2,
        "dma": 4,
        "wait": 6,
        "set_flag": 6,
        "barrier": 6,
    }
    return sum(counts.get(keyword, 0) * weights.get(keyword, 0) for keyword in KEYWORDS)


def _sort_stage_infos(stage_infos: list[StageInfo], *, sort_by: str) -> list[StageInfo]:
    if sort_by == "order":
        return list(stage_infos)
    if sort_by == "size":
        return sorted(stage_infos, key=lambda info: (-info.size_bytes, info.relative_path))
    if sort_by == "lines":
        return sorted(stage_infos, key=lambda info: (-info.line_count, info.relative_path))
    return sorted(
        stage_infos,
        key=lambda info: (
            -_interesting_score(_keyword_counts(info.path.read_text(encoding="utf-8"))),
            info.relative_path,
        ),
    )


def _adjacent_stage_changes(stage_infos: list[StageInfo]) -> list[_StageChange]:
    changes: list[_StageChange] = []
    for index in range(len(stage_infos) - 1):
        previous = stage_infos[index]
        current = stage_infos[index + 1]
        previous_counts = _keyword_counts(previous.path.read_text(encoding="utf-8"))
        current_counts = _keyword_counts(current.path.read_text(encoding="utf-8"))
        keyword_deltas = {
            keyword: current_counts[keyword] - previous_counts[keyword]
            for keyword in KEYWORDS
        }
        score = (
            abs(current.line_count - previous.line_count)
            + abs(current.size_bytes - previous.size_bytes) // 64
            + sum(abs(delta) for delta in keyword_deltas.values())
        )
        changes.append(
            {
                "from": previous,
                "to": current,
                "line_delta": current.line_count - previous.line_count,
                "size_delta": current.size_bytes - previous.size_bytes,
                "keyword_deltas": keyword_deltas,
                "score": score,
            }
        )
    return changes


def _sort_stage_changes(changes: list[_StageChange], *, sort_by: str) -> list[_StageChange]:
    if sort_by == "lines":
        return sorted(changes, key=lambda item: (-abs(item["line_delta"]), str(item["to"])))
    if sort_by == "size":
        return sorted(changes, key=lambda item: (-abs(item["size_delta"]), str(item["to"])))
    return sorted(changes, key=lambda item: (-item["score"], str(item["to"])))


def _format_keyword_delta_summary(keyword_deltas: dict[str, int], limit: int = 5) -> str:
    interesting = [(key, delta) for key, delta in keyword_deltas.items() if delta != 0]
    if not interesting:
        return "no keyword count changes"
    interesting.sort(key=lambda item: (-abs(item[1]), item[0]))
    return ", ".join(f"{key}={delta:+d}" for key, delta in interesting[:limit])


def _stage_highlights(text: str, limit: int = 8) -> list[str]:
    highlights: list[str] = []
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        lowered = stripped.lower()
        if any(keyword in lowered for keyword in KEYWORDS):
            highlights.append(stripped)
        if len(highlights) >= limit:
            break
    return highlights


def _stage_signal_summary(info: StageInfo) -> _StageSignalSummary:
    counts = _keyword_counts(info.path.read_text(encoding="utf-8"))
    transfer_ops = counts["copy"] + counts["dma"] + counts["load"] + counts["store"]
    sync_ops = counts["wait"] + counts["set_flag"] + counts["barrier"]
    return {
        "stage": info.stem,
        "path": info.relative_path,
        "line_count": info.line_count,
        "size_bytes": info.size_bytes,
        "vector_ops": counts["vector"],
        "transfer_ops": transfer_ops,
        "sync_ops": sync_ops,
        "alloc_ops": counts["alloc"],
        "interesting_score": _interesting_score(counts),
    }


def _suspicious_transitions(stage_infos: list[StageInfo]) -> list[_SuspiciousTransition]:
    suspicious: list[_SuspiciousTransition] = []
    for change in _adjacent_stage_changes(stage_infos):
        keyword_deltas = change["keyword_deltas"]
        vector_delta = keyword_deltas["vector"]
        transfer_delta = (
            keyword_deltas["copy"]
            + keyword_deltas["dma"]
            + keyword_deltas["load"]
            + keyword_deltas["store"]
        )
        sync_delta = (
            keyword_deltas["wait"]
            + keyword_deltas["set_flag"]
            + keyword_deltas["barrier"]
        )
        signal_score = abs(vector_delta) + abs(transfer_delta) + abs(sync_delta)
        if signal_score == 0:
            continue
        previous = change["from"]
        current = change["to"]
        suspicious.append(
            {
                "from_stage": previous.stem,
                "to_stage": current.stem,
                "signal_score": signal_score,
                "vector_delta": vector_delta,
                "transfer_delta": transfer_delta,
                "sync_delta": sync_delta,
                "line_delta": change["line_delta"],
                "size_delta": change["size_delta"],
            }
        )
    return sorted(suspicious, key=lambda item: (-item["signal_score"], str(item["to_stage"])))


_INDIRECT_LOAD_RE = re.compile(r"\btriton_indirect_load\b", flags=re.IGNORECASE)
_INDIRECT_STORE_RE = re.compile(r"\btriton_indirect_store\b", flags=re.IGNORECASE)


def _indirect_access_signals(stage_infos: list[StageInfo]) -> list[_IndirectAccessSignal]:
    signals: list[_IndirectAccessSignal] = []
    for info in stage_infos:
        text = info.path.read_text(encoding="utf-8")
        evidence: list[str] = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            if _INDIRECT_LOAD_RE.search(line) or _INDIRECT_STORE_RE.search(line):
                evidence.append(f"{info.relative_path}:{line_number}: {line.strip()}")
        if not evidence:
            continue
        signals.append(
            {
                "stage": info.stem,
                "path": info.relative_path,
                "indirect_loads": len(_INDIRECT_LOAD_RE.findall(text)),
                "indirect_stores": len(_INDIRECT_STORE_RE.findall(text)),
                "evidence": evidence,
            }
        )
    return sorted(signals, key=lambda item: (str(item["stage"])))


def _render_signal_stage_lines(entries: list[_StageSignalSummary]) -> list[str]:
    if not entries:
        return ["- No stages matched the default heuristics."]
    lines: list[str] = []
    for entry in entries:
        lines.append(
            f"- {entry['stage']} "
            f"(vector={entry['vector_ops']}, transfer={entry['transfer_ops']}, "
            f"sync={entry['sync_ops']}, lines={entry['line_count']})"
        )
    return lines


if __name__ == "__main__":
    raise SystemExit(main())
