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

"""Validate that an implementation completed the assigned optimization scheme without substitution."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import tempfile
import os
import re
import sys
from pathlib import Path
from typing import Any

from cli_output import atomic_json, emit

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_source_isolation import snapshot, validate_source_isolation  # noqa: E402

SCHEMA_VERSION = 3
VALID_IMPLEMENTATION_MODES = {"exact"}
VALID_RESULT_STATUSES = {"complete", "partial", "blocked"}
VALID_FEATURE_STATUSES = {"pass", "fail", "not_implemented", "blocked"}
FEATURE_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:[_-][a-z0-9]+)*$")
SOURCE_LOCATION_PATTERN = re.compile(r"^(.*):(\d+)$")
SOURCE_SUFFIXES = {".c", ".cc", ".cpp", ".h", ".hh", ".hpp", ".cce", ".asc", ".py"}
IGNORED_DIRS = {".git", ".pytest_cache", "__pycache__", "build", "build_out", "dist", "output", "outputs"}
PUBLIC_CONTRACT_DIRS = {"op_api", "op_proto"}
PUBLIC_CONTRACT_NAME = re.compile(
    r"(?:_def|_proto|_infershape|torch_adpt)\.(?:c|cc|cpp|h|hh|hpp|json|ya?ml)$",
    re.IGNORECASE,
)


class ContractError(ValueError):
    """Raised when the contract or result is malformed."""


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ContractError(f"cannot read {path}: {error}") from error
    if not isinstance(value, dict):
        raise ContractError(f"{path}: root must be an object")
    return value


def _validate_safety(safety: object) -> None:
    if not isinstance(safety, dict):
        raise ContractError("safety must be an object")
    if set(safety) != {"public_contract", "non_target_socs"}:
        raise ContractError("safety must contain exactly public_contract and non_target_socs")
    if safety.get("public_contract") != "unchanged":
        raise ContractError("safety.public_contract must be 'unchanged'")
    if safety.get("non_target_socs") != "unchanged":
        raise ContractError("safety.non_target_socs must be 'unchanged'")


def _validate_expectations(expectations: object) -> None:
    if not isinstance(expectations, dict) or set(expectations) != {"vf", "casttrait"}:
        raise ContractError("expectations must contain exactly the vf and casttrait booleans")
    if not all(isinstance(expectations[name], bool) for name in ("vf", "casttrait")):
        raise ContractError("expectations.vf and expectations.casttrait must be booleans")
    if expectations["casttrait"] and not expectations["vf"]:
        raise ContractError("expectations.casttrait=true requires expectations.vf=true")


def _validate_contract(contract: dict[str, Any]) -> list[str]:
    if contract.get("schema_version") != SCHEMA_VERSION:
        raise ContractError(f"contract schema_version must be {SCHEMA_VERSION}")
    scheme_id = contract.get("scheme_id")
    if not isinstance(scheme_id, str) or not scheme_id.strip():
        raise ContractError("contract scheme_id must be a non-empty string")
    if contract.get("implementation_mode") not in VALID_IMPLEMENTATION_MODES:
        raise ContractError("implementation_mode must be 'exact'")
    if contract.get("substitution_policy") != "forbidden":
        raise ContractError("substitution_policy must be 'forbidden'")
    target_socs = contract.get("target_socs")
    if not isinstance(target_socs, list) or not target_socs:
        raise ContractError("target_socs must be a non-empty unique string array")
    if not all(isinstance(soc, str) and soc.strip() for soc in target_socs):
        raise ContractError("target_socs must be a non-empty unique string array")
    if len(target_socs) != len(set(target_socs)):
        raise ContractError("target_socs must be a non-empty unique string array")
    _validate_safety(contract.get("safety"))
    _validate_expectations(contract.get("expectations"))
    return target_socs


def _feature_ids(features: list) -> list[str]:
    identifiers: list[str] = []
    for index, feature in enumerate(features):
        if not isinstance(feature, dict):
            raise ContractError(f"required_features[{index}] must be an object")
        identifier = feature.get("id")
        description = feature.get("description")
        if not isinstance(identifier, str) or not FEATURE_ID_PATTERN.fullmatch(identifier):
            raise ContractError(f"required_features[{index}].id must be stable snake/kebab case")
        if identifier in identifiers:
            raise ContractError(f"duplicate required feature id: {identifier}")
        if not isinstance(description, str) or not description.strip():
            raise ContractError(f"required feature {identifier} needs a description")
        identifiers.append(identifier)
    return identifiers


def required_feature_ids(contract: dict[str, Any]) -> list[str]:
    _validate_contract(contract)
    features = contract.get("required_features")
    if not isinstance(features, list) or not features:
        raise ContractError("required_features must be a non-empty array")
    return _feature_ids(features)


def validate_manifest_scope(contract: dict[str, Any], manifest: dict[str, Any]) -> None:
    manifest_socs = manifest.get("configuration", {}).get("target_socs")
    if manifest_socs != contract.get("target_socs"):
        raise ContractError("contract target_socs must exactly match RUN_MANIFEST configuration.target_socs")
    backend = manifest.get("configuration", {}).get("backend", "ascendc")
    if contract.get("backend", "ascendc") != backend:
        raise ContractError("contract backend must match the frozen language")
    if backend == "cannbot_dsl" and contract.get("expectations", {}).get("casttrait"):
        raise ContractError("DSL contracts describe cast/pack semantics as required features, not C++ CastTrait")


def resolve_candidate_file(candidate: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    resolved = path.resolve() if path.is_absolute() else (candidate / path).resolve()
    try:
        resolved.relative_to(candidate)
    except ValueError as error:
        raise ContractError(f"evidence escapes candidate root: {raw_path}") from error
    return resolved


def validate_source_location(candidate: Path, location: str) -> str | None:
    match = SOURCE_LOCATION_PATTERN.fullmatch(location)
    if not match:
        return f"invalid source location {location!r}; expected path:line"
    raw_path, raw_line = match.groups()
    try:
        path = resolve_candidate_file(candidate, raw_path)
    except ContractError as error:
        return str(error)
    if not path.is_file():
        return f"source evidence does not exist: {location}"
    line_number = int(raw_line)
    try:
        line_count = sum(1 for _ in path.open(encoding="utf-8", errors="replace"))
    except OSError as error:
        return f"cannot read source evidence {location}: {error}"
    if line_number < 1 or line_number > line_count:
        return f"source evidence line is outside file: {location} (lines={line_count})"
    return None


def _check_evidence_files(identifier: str, feature: dict, candidate: Path, malformed: list[str]) -> None:
    evidence_files = feature.get("evidence_files")
    if not isinstance(evidence_files, list) or not evidence_files:
        malformed.append(f"passing feature {identifier} needs evidence_files")
        return
    if not all(isinstance(item, str) and item for item in evidence_files):
        malformed.append(f"passing feature {identifier} needs evidence_files")
        return
    for raw_path in evidence_files:
        try:
            evidence_path = resolve_candidate_file(candidate, raw_path)
        except ContractError as error:
            malformed.append(str(error))
            continue
        if not evidence_path.is_file():
            malformed.append(f"feature {identifier} evidence file does not exist: {raw_path}")


def _check_source_locations(identifier: str, feature: dict, candidate: Path,
                            malformed: list[str]) -> None:
    source_locations = feature.get("source_locations")
    if not isinstance(source_locations, list) or not source_locations:
        malformed.append(f"passing feature {identifier} needs source_locations")
        return
    if not all(isinstance(item, str) and item for item in source_locations):
        malformed.append(f"passing feature {identifier} needs source_locations")
        return
    for location in source_locations:
        error = validate_source_location(candidate, location)
        if error:
            malformed.append(f"feature {identifier}: {error}")


def _check_feature(identifier: str, features: dict, candidate: Path,
                   malformed: list[str], failures: list[str]) -> None:
    feature = features.get(identifier)
    if not isinstance(feature, dict):
        malformed.append(f"missing result for required feature {identifier}")
        return
    feature_status = feature.get("status")
    if feature_status not in VALID_FEATURE_STATUSES:
        malformed.append(f"feature {identifier} has invalid status {feature_status!r}")
        return
    if feature_status != "pass":
        failures.append(f"required feature {identifier} is {feature_status}")
        return
    _check_evidence_files(identifier, feature, candidate, malformed)
    _check_source_locations(identifier, feature, candidate, malformed)


def _check_result_header(result: dict, contract: dict, malformed: list[str], failures: list[str]) -> None:
    if result.get("schema_version") != SCHEMA_VERSION:
        malformed.append(f"result schema_version must be {SCHEMA_VERSION}")
    if result.get("scheme_id") != contract.get("scheme_id"):
        malformed.append("result scheme_id does not match contract")
    if result.get("implementation_status") not in VALID_RESULT_STATUSES:
        malformed.append(f"implementation_status must be one of {sorted(VALID_RESULT_STATUSES)}")
    if result.get("route_changed") is not False:
        failures.append("route_changed must be false for an exact implementation")
    if result.get("substitution_used") is not False:
        failures.append("substitution_used must be false for an exact implementation")


def validate_result(
    contract: dict[str, Any], result: dict[str, Any], candidate: Path
) -> tuple[list[str], dict[str, Any]]:
    required = required_feature_ids(contract)
    malformed: list[str] = []
    failures: list[str] = []
    _check_result_header(result, contract, malformed, failures)
    features = result.get("features")
    if not isinstance(features, dict):
        malformed.append("features must be an object keyed by required feature id")
        features = {}
    extra = sorted(set(features) - set(required))
    if extra:
        malformed.append(f"result contains undeclared features: {extra}")
    for identifier in required:
        _check_feature(identifier, features, candidate, malformed, failures)
    if result.get("implementation_status") != "complete":
        failures.append(f"implementation_status is {result.get('implementation_status')}, not complete")
    decision = "pass" if not malformed and not failures else "fail"
    report = {
        "schema_version": SCHEMA_VERSION,
        "decision": decision,
        "scheme_id": contract.get("scheme_id"),
        "candidate": str(candidate),
        "expectations": contract.get("expectations"),
        "target_socs": contract.get("target_socs"),
        "safety_contract": contract.get("safety"),
        "required_features": required,
        "malformed_evidence": malformed,
        "conformance_failures": failures,
    }
    return malformed, report


def relative_files(root: Path) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for current, directories, files in os.walk(root):
        directories[:] = sorted(name for name in directories if name not in IGNORED_DIRS)
        current_path = Path(current)
        for name in sorted(files):
            path = current_path / name
            if path.is_file():
                result[path.relative_to(root).as_posix()] = path
    return result


def is_public_contract_path(relative: str) -> bool:
    path = Path(relative)
    lowered_parts = {part.lower() for part in path.parts}
    return bool(lowered_parts & PUBLIC_CONTRACT_DIRS) or bool(PUBLIC_CONTRACT_NAME.search(path.name))


def file_bytes(path: Path | None) -> bytes | None:
    return path.read_bytes() if path and path.is_file() else None


def python_public_signatures(path: Path) -> dict[str, str]:
    """Conservative signature check; body/input/return semantics still need review."""
    result = {}
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
            # Decorated device helpers are not public Python entry points.
            decorators = [ast.unparse(item).split("(", 1)[0].rsplit(".", 1)[-1] for item in node.decorator_list]
            if {"kernel", "jit", "aicpu_kernel"} & set(decorators):
                continue
            result[node.name] = ast.dump(node.args, include_attributes=False) + ":" + (
                ast.dump(node.returns, include_attributes=False) if node.returns else "None"
            )
    return result


def atomic_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _protected_contract_changes(baseline_files: dict[str, Path], candidate_files: dict[str, Path]) -> list[str]:
    protected_changes = []
    for relative in sorted(set(baseline_files) | set(candidate_files)):
        if not is_public_contract_path(relative):
            continue
        if file_bytes(baseline_files.get(relative)) != file_bytes(candidate_files.get(relative)):
            protected_changes.append(relative)
    return protected_changes


def _python_signature_changes(
    baseline_files: dict[str, Path],
    candidate_files: dict[str, Path],
    protected_changes: list[str],
    failures: list[str],
) -> None:
    for relative, path in baseline_files.items():
        if path.suffix != ".py":
            continue
        try:
            original = python_public_signatures(path)
            current = python_public_signatures(candidate_files[relative]) if relative in candidate_files else {}
            changed = [name for name, signature in original.items() if current.get(name) != signature]
            if changed:
                protected_changes.append(relative)
                failures.append(f"public Python signature/default/annotation changed: {relative}: {changed}")
        except SyntaxError as error:
            failures.append(f"cannot parse Python public contract: {relative}: {error}")


def validate_candidate_safety(baseline: Path, candidate: Path, backend: str = "ascendc") -> dict[str, Any]:
    baseline = baseline.resolve()
    candidate = candidate.resolve()
    if not baseline.is_dir():
        raise ContractError(f"baseline is not a directory: {baseline}")
    if not candidate.is_dir():
        raise ContractError(f"candidate is not a directory: {candidate}")
    baseline_files = relative_files(baseline)
    candidate_files = relative_files(candidate)
    protected_changes = _protected_contract_changes(baseline_files, candidate_files)
    failures = []
    if backend == "cannbot_dsl":
        _python_signature_changes(baseline_files, candidate_files, protected_changes, failures)
    if protected_changes:
        failures.append(
            "public interface/constraint/dtype contract changed: " + ", ".join(protected_changes)
        )
    return {
        "decision": "pass" if not failures else "fail",
        "baseline": str(baseline),
        "candidate": str(candidate),
        "protected_contract_patterns": [
            "**/op_api/**",
            "**/op_proto/**",
            "*_def.*",
            "*_proto.*",
            "*_infershape.*",
            "*torch_adpt*",
        ],
        "changed_public_contract_files": protected_changes,
        "failures": failures,
    }


def attach_candidate_safety(report: dict[str, Any], safety: dict[str, Any]) -> None:
    report["candidate_safety"] = safety
    report["conformance_failures"].extend(safety["failures"])
    if safety["decision"] != "pass":
        report["decision"] = "fail"


def evidence_identity(args: argparse.Namespace, result: dict[str, Any]) -> dict[str, Any]:
    """Bind the gate to inputs, source trees and feature evidence, not filenames alone."""
    def sha(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    identity = {
        name: {"path": str(path.resolve()), "sha256": sha(path)}
        for name in ("contract", "result", "manifest", "isolation_scope")
        for path in (getattr(args, name),)
    }
    for name in ("baseline", "candidate"):
        path = getattr(args, name).resolve()
        identity[name] = {
            "path": str(path),
            "sha256": hashlib.sha256(
                json.dumps(snapshot(path), sort_keys=True).encode()
            ).hexdigest(),
        }
    evidence = {}
    for feature in result.get("features", {}).values():
        if not isinstance(feature, dict) or feature.get("status") != "pass":
            continue
        for raw in feature.get("evidence_files", []):
            path = resolve_candidate_file(args.candidate.resolve(), raw)
            evidence[str(path)] = sha(path)
    identity["feature_evidence"] = evidence
    return identity


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--isolation-scope", type=Path, required=True)
    output = parser.add_mutually_exclusive_group(required=True)
    output.add_argument("--out", type=Path)
    output.add_argument("--verify-existing", type=Path, help="verify a saved gate without overwriting evidence")
    return parser.parse_args()


def _verify_saved_gate(
    args: argparse.Namespace, report: dict[str, Any], malformed: list[str], candidate: Path
) -> int:
    saved = load_json(args.verify_existing.resolve())
    if saved != report:
        emit(json.dumps({
            "decision": "fail", "reason": "stale_or_misattributed_gate",
            "gate": str(args.verify_existing.resolve()),
        }, ensure_ascii=False))
        return 1
    emit(json.dumps({
        "decision": report["decision"], "scheme_id": report["scheme_id"],
        "candidate": str(candidate), "gate": str(args.verify_existing.resolve()),
    }, ensure_ascii=False))
    return 2 if malformed else (0 if report["decision"] == "pass" else 1)


def main() -> int:
    args = parse_args()
    candidate = args.candidate.resolve()
    if not candidate.is_dir():
        emit(f"[ERROR] candidate is not a directory: {candidate}", file=sys.stderr)
        return 2
    try:
        contract = load_json(args.contract.resolve())
        result = load_json(args.result.resolve())
        manifest = load_json(args.manifest.resolve())
        validate_manifest_scope(contract, manifest)
        malformed, report = validate_result(contract, result, candidate)
        from validate_schedule_contract import validate_implementation_schedule
        schedule = validate_implementation_schedule(contract, result, args.manifest.resolve(), candidate)
        if schedule is not None:
            report["schedule"] = schedule
        safety = validate_candidate_safety(
            args.baseline.resolve(), candidate,
            manifest.get("configuration", {}).get("backend", "ascendc"),
        )
        attach_candidate_safety(report, safety)
        isolation = validate_source_isolation(
            load_json(args.isolation_scope.resolve()), args.baseline, candidate,
            contract["target_socs"],
        )
        report["source_isolation"] = isolation
        isolation["scope_path"] = str(args.isolation_scope.resolve())
        isolation["scope_sha256"] = hashlib.sha256(args.isolation_scope.read_bytes()).hexdigest()
        report["conformance_failures"].extend(isolation["failures"])
        if isolation["decision"] != "pass":
            report["decision"] = "fail"
        if not malformed:
            report["evidence_identity"] = evidence_identity(args, result)
        if args.verify_existing:
            return _verify_saved_gate(args, report, malformed, candidate)
    except (ValueError, OSError) as error:
        emit(f"[ERROR] {error}", file=sys.stderr)
        return 2
    if args.out:
        atomic_json(args.out.resolve(), report)
    emit(json.dumps(report, ensure_ascii=False, sort_keys=True))
    if malformed:
        return 2
    return 0 if report["decision"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
