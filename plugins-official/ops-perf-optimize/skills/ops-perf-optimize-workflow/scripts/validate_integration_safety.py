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

"""Gate register integration on SoC isolation and public-contract immutability."""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

from cli_output import emit

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_implementation_conformance import (  # noqa: E402
    ContractError,
    SOURCE_SUFFIXES,
    file_bytes,
    is_public_contract_path,
    relative_files,
    validate_candidate_safety,
)
from validate_source_isolation import validate_source_isolation  # noqa: E402


SCHEMA_VERSION = 2
ADD_CONFIG_SOC = re.compile(r'\bAddConfig\s*\(\s*"([^"]+)"')
CPP_COMMENT = re.compile(r"//.*?$|/\*.*?\*/", re.MULTILINE | re.DOTALL)
ROUTE_EVIDENCE_DISTANCE = 6


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ContractError(f"cannot read {path}: {error}") from error
    if not isinstance(value, dict):
        raise ContractError(f"{path}: root must be an object")
    return value


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def string_list(value: Any, field: str, *, required: bool = True) -> list[str]:
    if not isinstance(value, list) or (required and not value):
        raise ContractError(f"{field} must be a{' non-empty' if required else ''} array")
    if not all(isinstance(item, str) and item.strip() for item in value):
        raise ContractError(f"{field} must contain non-empty strings")
    result = [item.strip() for item in value]
    if len(result) != len(set(result)):
        raise ContractError(f"{field} must not contain duplicates")
    return result


def parse_location(location: str, *, require_line: bool) -> tuple[str, int | None]:
    raw_path = location
    line_number: int | None = None
    path_part, separator, possible_line = location.rpartition(":")
    if separator and possible_line.isdigit():
        raw_path = path_part
        line_number = int(possible_line)
    elif require_line:
        raise ContractError(f"evidence must use path:line: {location}")
    return raw_path, line_number


def evidence_text(root: Path, location: str, *, require_line: bool) -> str:
    raw_path, line_number = parse_location(location, require_line=require_line)
    path = (root / raw_path).resolve()
    try:
        path.relative_to(root)
    except ValueError as error:
        raise ContractError(f"evidence escapes source root: {location}") from error
    if not path.is_file():
        raise ContractError(f"evidence file does not exist: {location}")
    if line_number is None:
        return path.read_text(encoding="utf-8", errors="replace")
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if line_number < 1 or line_number > len(lines):
        raise ContractError(f"evidence line is outside file: {location} (lines={len(lines)})")
    start = max(0, line_number - 3)
    end = min(len(lines), line_number + 2)
    return "\n".join(lines[start:end])


def normalize_soc(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def declaration_evidence(
    value: Any, field: str, baseline: Path, backend: str,
    external_receipts: list[dict[str, str]],
) -> list[tuple[str, str, bool]]:
    """Read source-local declarations or explicitly SHA-bound DSL documentation.

    External declarations never authorize source edits or substitute for candidate
    guard/fallback evidence, which must still reside in each changed source file.
    """
    if not isinstance(value, list) or not value:
        raise ContractError(f"{field} must be a non-empty evidence array")
    result = []
    for entry in value:
        if isinstance(entry, str) and entry.strip():
            location = entry.strip()
            result.append((location, evidence_text(baseline, location, require_line=False), False))
            continue
        if backend != "cannbot_dsl" or not isinstance(entry, dict):
            raise ContractError(f"{field}: external declarations require manifest backend cannbot_dsl")
        if entry.get("kind") != "external_dsl_declaration":
            raise ContractError(f"{field}: invalid external declaration kind")
        raw_path, digest = entry.get("path"), entry.get("sha256")
        if not isinstance(raw_path, str) or not Path(raw_path).is_absolute():
            raise ContractError(f"{field}: external declaration path must be absolute")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ContractError(f"{field}: external declaration requires SHA-256")
        path = Path(raw_path).resolve()
        try:
            payload = path.read_bytes()
        except OSError as error:
            raise ContractError(f"{field}: cannot read external declaration {path}: {error}") from error
        if hashlib.sha256(payload).hexdigest() != digest:
            raise ContractError(f"{field}: external declaration SHA-256 mismatch: {path}")
        external_receipts.append({"path": str(path), "sha256": digest})
        # An external filename is not evidence of the declared architecture.
        result.append((str(path), payload.decode("utf-8", errors="replace"), True))
    if len({location for location, _text, _external in result}) != len(result):
        raise ContractError(f"{field} must not contain duplicate evidence")
    return result


def discover_add_config_socs(root: Path) -> dict[str, list[str]]:
    """Discover explicit operator support declarations while ignoring commented examples."""
    discovered: dict[str, list[str]] = {}
    for relative, path in relative_files(root).items():
        if path.suffix.lower() not in SOURCE_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        uncommented = CPP_COMMENT.sub(lambda match: "\n" * match.group(0).count("\n"), text)
        for match in ADD_CONFIG_SOC.finditer(uncommented):
            name = match.group(1).strip()
            key = normalize_soc(name)
            line = uncommented.count("\n", 0, match.start()) + 1
            discovered.setdefault(key, []).append(f"{relative}:{line}")
    return discovered


def changed_candidate_hunks(baseline: Path, candidate: Path, relative: str) -> list[tuple[int, int]]:
    baseline_path = baseline / relative
    candidate_path = candidate / relative
    before = (
        baseline_path.read_text(encoding="utf-8", errors="replace").splitlines()
        if baseline_path.is_file()
        else []
    )
    after = (
        candidate_path.read_text(encoding="utf-8", errors="replace").splitlines()
        if candidate_path.is_file()
        else []
    )
    hunks: list[tuple[int, int]] = []
    for tag, _i1, _i2, j1, j2 in difflib.SequenceMatcher(a=before, b=after).get_opcodes():
        if tag == "equal":
            continue
        start = max(1, j1 + 1)
        end = max(start, j2)
        hunks.append((start, end))
    return hunks


def location_matches_file(location: str, relative: str) -> tuple[bool, int]:
    raw_path, line = parse_location(location, require_line=True)
    normalized = Path(raw_path).as_posix().removeprefix("./")
    return normalized == Path(relative).as_posix(), int(line)


def changed_source_files(baseline: Path, candidate: Path) -> list[str]:
    baseline_files = relative_files(baseline)
    candidate_files = relative_files(candidate)
    changed = []
    for relative in sorted(set(baseline_files) | set(candidate_files)):
        if Path(relative).suffix.lower() not in SOURCE_SUFFIXES:
            continue
        if file_bytes(baseline_files.get(relative)) == file_bytes(candidate_files.get(relative)):
            continue
        changed.append(relative)
    return changed


def _supported_socs(scope: dict, baseline: Path, backend: str = "ascendc",
                    external_receipts: list[dict[str, str]] | None = None) -> tuple[list[str], list[str], list[str]]:
    entries = scope.get("supported_socs")
    if not isinstance(entries, list) or not entries:
        raise ContractError("supported_socs must be a non-empty evidence array")
    supported_socs: list[str] = []
    supported_keys: list[str] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str) or not entry["name"].strip():
            raise ContractError(f"supported_socs[{index}] requires a non-empty name")
        name = entry["name"].strip()
        key = normalize_soc(name)
        if key in supported_keys:
            raise ContractError(f"duplicate supported SoC: {name}")
        evidence = declaration_evidence(entry.get("evidence"), f"supported_socs[{index}].evidence",
                                        baseline, backend, external_receipts if external_receipts is not None else [])
        for location, text, external in evidence:
            if key not in normalize_soc(text if external else f"{location}\n{text}"):
                raise ContractError(f"supported SoC evidence does not name {name}: {location}")
        supported_socs.append(name)
        supported_keys.append(key)
    discovered = discover_add_config_socs(baseline)
    if discovered and set(supported_keys) != set(discovered):
        missing = sorted(set(discovered) - set(supported_keys))
        extra = sorted(set(supported_keys) - set(discovered))
        raise ContractError(
            "supported_socs must exactly match uncommented AddConfig declarations; "
            f"missing={missing}, extra={extra}, discovered={discovered}"
        )
    return supported_socs, supported_keys, discovered


def _isolation_style(scope: dict, baseline: Path, backend: str = "ascendc",
                     external_receipts: list[dict[str, str]] | None = None) -> tuple[list[str], list[str]]:
    isolation = scope.get("project_isolation_style")
    if not isinstance(isolation, dict):
        raise ContractError("project_isolation_style is required when supported SoCs remain unverified")
    kind = isolation.get("kind")
    if not isinstance(kind, str) or not kind.strip():
        raise ContractError("project_isolation_style.kind must be non-empty")
    markers = string_list(isolation.get("target_path_markers"), "target_path_markers")
    tokens = string_list(isolation.get("target_route_tokens"), "target_route_tokens")
    style_evidence = declaration_evidence(isolation.get("evidence"), "project_isolation_style.evidence",
                                          baseline, backend, external_receipts if external_receipts is not None else [])
    style_text = "\n".join(text for _location, text, _external in style_evidence)
    if not any(token.lower() in style_text.lower() for token in tokens):
        raise ContractError("project isolation style evidence contains none of target_route_tokens")
    return markers, tokens


def _shared_changes(source_changes: list[str], markers: list[str]) -> list[str]:
    shared: list[str] = []
    for relative in source_changes:
        lowered = relative.lower()
        if (Path(relative).suffix != ".py"
                and not ({"op_host", "op_kernel"} & {part.lower() for part in Path(relative).parts})):
            continue
        if is_public_contract_path(relative):
            continue
        if any(marker.lower() in lowered for marker in markers):
            continue
        shared.append(relative)
    return shared


def _route_failure(relative: str, route: dict, baseline: Path, candidate: Path,
                   tokens: list[str]) -> str | None:
    target_guard = string_list(route.get("target_guard"), f"{relative}.target_guard")
    fallback = string_list(route.get("non_target_fallback"), f"{relative}.non_target_fallback")
    guard_lines: list[int] = []
    for location in target_guard:
        same_file, line = location_matches_file(location, relative)
        if not same_file:
            raise ContractError(f"target guard evidence must point into changed file {relative}: {location}")
        text = evidence_text(candidate, location, require_line=True)
        if not any(token.lower() in text.lower() for token in tokens):
            raise ContractError(f"target guard evidence contains no route token for {relative}: {location}")
        guard_lines.append(line)
    for location in fallback:
        same_file, _line = location_matches_file(location, relative)
        if not same_file:
            raise ContractError(f"fallback evidence must point into changed file {relative}: {location}")
        evidence_text(candidate, location, require_line=True)
    uncovered = []
    for start, end in changed_candidate_hunks(baseline, candidate, relative):
        if any(
            all(abs(changed - guard) <= ROUTE_EVIDENCE_DISTANCE for changed in range(start, end + 1))
            for guard in guard_lines
        ):
            continue
        uncovered.append(f"{start}-{end}")
    if uncovered:
        return (
            f"changed hunks are not local to target route evidence in {relative}: "
            f"{uncovered} (max_distance={ROUTE_EVIDENCE_DISTANCE})"
        )
    return None


def _validate_routes(scope: dict, paths: tuple[Path, Path], shared: list[str],
                     tokens: list[str]) -> list[str]:
    routes = scope.get("shared_file_routes")
    if not isinstance(routes, dict):
        raise ContractError("shared_file_routes must be an object keyed by changed shared source path")
    failures = []
    for relative in shared:
        route = routes.get(relative)
        if not isinstance(route, dict):
            failures.append(f"changed shared source lacks SoC-isolation evidence: {relative}")
            continue
        failure = _route_failure(relative, route, paths[0], paths[1], tokens)
        if failure:
            failures.append(failure)
    return failures


def validate_scope(
    scope: dict[str, Any],
    baseline: Path,
    candidate: Path,
    candidate_safety: dict[str, Any],
    expected_target_socs: list[str] | None = None,
    backend: str = "ascendc",
) -> dict[str, Any]:
    if scope.get("schema_version") != SCHEMA_VERSION:
        raise ContractError(f"integration scope schema_version must be {SCHEMA_VERSION}")
    target_socs = string_list(scope.get("target_socs"), "target_socs")
    if expected_target_socs is not None and target_socs != expected_target_socs:
        raise ContractError("scope target_socs must exactly match RUN_MANIFEST configuration.target_socs")
    verified_socs = string_list(scope.get("verified_socs"), "verified_socs")
    if set(target_socs) != set(verified_socs):
        raise ContractError("verified_socs must exactly match the user-confirmed target_socs")
    external_receipts: list[dict[str, str]] = []
    supported_socs, supported_keys, discovered = _supported_socs(scope, baseline, backend, external_receipts)
    target_keys = {normalize_soc(soc) for soc in target_socs}
    verified_keys = {normalize_soc(soc) for soc in verified_socs}
    missing_targets = sorted(target_keys - set(supported_keys))
    if missing_targets:
        raise ContractError(f"target SoCs are absent from supported_socs: {missing_targets}")
    unverified = [soc for soc, key in zip(supported_socs, supported_keys) if key not in verified_keys]
    source_changes = changed_source_files(baseline, candidate)
    failures = list(candidate_safety["failures"])
    shared: list[str] = []
    if unverified:
        markers, tokens = _isolation_style(scope, baseline, backend, external_receipts)
        shared = _shared_changes(source_changes, markers)
        failures.extend(_validate_routes(scope, (baseline, candidate), shared, tokens))
    report = {
        "schema_version": SCHEMA_VERSION,
        "decision": "pass" if not failures else "fail",
        "baseline": str(baseline),
        "candidate": str(candidate),
        "target_socs": target_socs,
        "verified_socs": verified_socs,
        "supported_socs": supported_socs,
        "auto_discovered_add_config_socs": discovered,
        "unverified_socs": unverified,
        "isolation_required": bool(unverified),
        "changed_source_files": source_changes,
        "changed_shared_generation_files": shared,
        "candidate_safety": candidate_safety,
        "failures": failures,
    }
    unique_receipts = {item["path"]: item for item in external_receipts}
    for receipt in unique_receipts.values():
        if hashlib.sha256(Path(receipt["path"]).read_bytes()).hexdigest() != receipt["sha256"]:
            raise ContractError(f"external declaration changed during validation: {receipt['path']}")
    if unique_receipts:
        report["external_declaration_receipts"] = list(unique_receipts.values())
    return report


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--baseline", type=Path, required=True)
    result.add_argument("--candidate", type=Path, required=True)
    result.add_argument("--manifest", type=Path, required=True)
    result.add_argument("--scope", type=Path, required=True)
    result.add_argument("--isolation-scope", type=Path, required=True)
    result.add_argument("--out", type=Path, required=True)
    return result


def main() -> int:
    args = parser().parse_args()
    baseline = args.baseline.resolve()
    candidate = args.candidate.resolve()
    try:
        manifest = load_json(args.manifest.resolve())
        candidate_safety = validate_candidate_safety(
            baseline, candidate, manifest.get("configuration", {}).get("backend", "ascendc")
        )
        expected_target_socs = string_list(
            manifest.get("configuration", {}).get("target_socs"),
            "RUN_MANIFEST configuration.target_socs",
        )
        report = validate_scope(
            load_json(args.scope.resolve()),
            baseline,
            candidate,
            candidate_safety,
            expected_target_socs,
            manifest.get("configuration", {}).get("backend", "ascendc"),
        )
        isolation = validate_source_isolation(
            load_json(args.isolation_scope.resolve()), baseline, candidate, expected_target_socs,
        )
        report["source_isolation"] = isolation
        isolation["scope_path"] = str(args.isolation_scope.resolve())
        isolation["scope_sha256"] = hashlib.sha256(args.isolation_scope.read_bytes()).hexdigest()
        report["failures"].extend(isolation["failures"])
        if isolation["decision"] != "pass":
            report["decision"] = "fail"
    except (ValueError, OSError) as error:
        emit(f"[ERROR] {error}", file=sys.stderr)
        return 2
    atomic_json(args.out.resolve(), report)
    emit(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["decision"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
