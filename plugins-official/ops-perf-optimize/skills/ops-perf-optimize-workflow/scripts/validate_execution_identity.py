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

"""Record and validate the implementation executed for baseline measurement."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from cli_output import atomic_json, emit
from prepare_case_sets import code_identity, load_manifest


SCHEMA_VERSION = 1


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def file_identity(path: Path) -> dict[str, str]:
    resolved = path.resolve()
    if not resolved.is_file():
        raise ValueError(f"artifact is not a file: {resolved}")
    return {"path": str(resolved), "sha256": sha256_file(resolved)}


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read JSON {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def validate_source(manifest: dict[str, Any]) -> dict[str, Any]:
    frozen = manifest.get("inputs", {}).get("code")
    if not isinstance(frozen, dict) or not frozen.get("path") or not frozen.get("sha256"):
        raise ValueError("run manifest has no frozen code identity")
    current = code_identity(Path(frozen["path"]))
    if current["sha256"] != frozen["sha256"]:
        raise ValueError("frozen source identity changed")
    return frozen


def file_contains_any(path: Path, values: list[str]) -> bool:
    needles = [value.encode("utf-8") for value in values if value]
    overlap = max((len(needle) for needle in needles), default=1) - 1
    tail = b""
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            data = tail + block
            if any(needle in data for needle in needles):
                return True
            tail = data[-overlap:] if overlap else b""
    return False


def validate_runtime_evidence(
    path: Path,
) -> tuple[dict[str, Any], list[dict[str, str]], list[dict[str, str]]]:
    evidence = read_json(path)
    if not str(evidence.get("method", "")).strip():
        raise ValueError("runtime evidence requires a non-empty method")
    raw_sources = evidence.get("source_artifacts")
    if not isinstance(raw_sources, list) or not raw_sources:
        raise ValueError("runtime evidence requires source_artifacts")
    sources: list[dict[str, str]] = []
    for item in raw_sources:
        if not isinstance(item, dict) or not item.get("path") or not item.get("sha256"):
            raise ValueError("runtime source_artifacts require path and sha256")
        actual = file_identity(Path(item["path"]))
        if actual["sha256"] != item["sha256"]:
            raise ValueError(f"runtime source artifact identity changed: {actual['path']}")
        sources.append(actual)
    raw_artifacts = evidence.get("loaded_artifacts")
    if not isinstance(raw_artifacts, list) or not raw_artifacts:
        raise ValueError("runtime evidence requires loaded_artifacts")
    loaded: list[dict[str, str]] = []
    for item in raw_artifacts:
        if not isinstance(item, dict) or not item.get("path") or not item.get("sha256"):
            raise ValueError("runtime loaded_artifacts require path and sha256")
        actual = file_identity(Path(item["path"]))
        if actual["sha256"] != item["sha256"]:
            raise ValueError(f"loaded artifact identity changed: {actual['path']}")
        if not any(
            file_contains_any(
                Path(source["path"]),
                [str(item["path"]), actual["path"], actual["sha256"]],
            )
            for source in sources
        ):
            raise ValueError(f"runtime evidence does not identify loaded artifact: {actual['path']}")
        loaded.append(actual)
    return evidence, loaded, sources


def validate_document(manifest: dict[str, Any], document: dict[str, Any]) -> dict[str, Any]:
    if document.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"unsupported execution identity schema: {document.get('schema_version')}")
    source = validate_source(manifest)
    if document.get("source") != source:
        raise ValueError("execution identity source does not match the run manifest")

    targets = document.get("targets")
    if not isinstance(targets, list):
        raise ValueError("execution identity targets must be a list")
    expected_socs = set(manifest.get("configuration", {}).get("target_socs", []))
    actual_socs = {item.get("target_soc") for item in targets if isinstance(item, dict)}
    if actual_socs != expected_socs or len(targets) != len(expected_socs):
        raise ValueError(
            f"execution identity target coverage mismatch: expected={sorted(expected_socs)}, "
            f"actual={sorted(str(item) for item in actual_socs)}"
        )

    for target in targets:
        target_soc = target["target_soc"]
        build = target.get("build", {})
        runtime = target.get("runtime", {})
        if not str(build.get("command", "")).strip():
            raise ValueError(f"{target_soc}: build command is missing")
        build_log = build.get("log", {})
        if file_identity(Path(build_log.get("path", ""))) != build_log:
            raise ValueError(f"{target_soc}: build log identity changed")
        built = build.get("artifacts")
        if not isinstance(built, list) or not built:
            raise ValueError(f"{target_soc}: build artifacts are missing")
        verified_built = [file_identity(Path(item.get("path", ""))) for item in built]
        if verified_built != built:
            raise ValueError(f"{target_soc}: build artifact identity changed")

        evidence_identity = runtime.get("evidence", {})
        evidence_path = Path(evidence_identity.get("path", ""))
        if file_identity(evidence_path) != evidence_identity:
            raise ValueError(f"{target_soc}: runtime evidence identity changed")
        evidence, loaded, sources = validate_runtime_evidence(evidence_path)
        if evidence.get("target_soc") not in (None, target_soc):
            raise ValueError(f"{target_soc}: runtime evidence target SoC mismatch")
        if loaded != runtime.get("loaded_artifacts"):
            raise ValueError(f"{target_soc}: runtime loaded artifact identity changed")
        if sources != runtime.get("source_artifacts"):
            raise ValueError(f"{target_soc}: runtime source artifact identity changed")
        built_hashes = {item["sha256"] for item in built}
        missing = [item["path"] for item in loaded if item["sha256"] not in built_hashes]
        if missing:
            raise ValueError(
                f"{target_soc}: loaded artifacts do not match the recorded build: {missing}"
            )
    return document


def validate_execution_identity(manifest_path: Path, identity_path: Path) -> dict[str, Any]:
    manifest = load_manifest(manifest_path.resolve())
    document = read_json(identity_path.resolve())
    return validate_document(manifest, document)


def dependency_paths(document: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    for target in document["targets"]:
        paths.append(target["build"]["log"]["path"])
        paths.extend(item["path"] for item in target["build"]["artifacts"])
        paths.append(target["runtime"]["evidence"]["path"])
        paths.extend(item["path"] for item in target["runtime"]["source_artifacts"])
        paths.extend(item["path"] for item in target["runtime"]["loaded_artifacts"])
    return list(dict.fromkeys(paths))


def record(args: argparse.Namespace) -> dict[str, Any]:
    manifest_path = args.manifest.resolve()
    manifest = load_manifest(manifest_path)
    source = validate_source(manifest)
    expected_socs = set(manifest["configuration"]["target_socs"])
    if args.target_soc not in expected_socs:
        raise ValueError(f"target SoC is not frozen in the run manifest: {args.target_soc}")
    if not str(args.build_command).strip():
        raise ValueError("build command is missing")

    built = [file_identity(path) for path in args.built_artifact]
    evidence, loaded, sources = validate_runtime_evidence(args.runtime_evidence)
    if evidence.get("target_soc") not in (None, args.target_soc):
        raise ValueError("runtime evidence target SoC mismatch")
    built_hashes = {item["sha256"] for item in built}
    missing = [item["path"] for item in loaded if item["sha256"] not in built_hashes]
    if missing:
        raise ValueError(f"loaded artifacts do not match the recorded build: {missing}")

    target = {
        "target_soc": args.target_soc,
        "build": {
            "command": args.build_command,
            "log": file_identity(args.build_log),
            "artifacts": built,
        },
        "runtime": {
            "evidence": file_identity(args.runtime_evidence),
            "source_artifacts": sources,
            "loaded_artifacts": loaded,
        },
    }
    document = (
        read_json(args.out)
        if args.out.is_file()
        else {"schema_version": SCHEMA_VERSION, "source": source, "targets": []}
    )
    if document.get("schema_version") != SCHEMA_VERSION or document.get("source") != source:
        raise ValueError("existing execution identity belongs to another source or schema")
    targets = [item for item in document.get("targets", []) if item.get("target_soc") != args.target_soc]
    targets.append(target)
    document["targets"] = sorted(targets, key=lambda item: item["target_soc"])
    complete = {item["target_soc"] for item in targets} == expected_socs
    if complete:
        validate_document(manifest, document)
    atomic_json(args.out, document)
    return {"status": "complete" if complete else "pending", "identity": str(args.out.resolve())}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    record_parser = subparsers.add_parser("record", help="record one target SoC build/load identity")
    record_parser.add_argument("--manifest", type=Path, required=True)
    record_parser.add_argument("--target-soc", required=True)
    record_parser.add_argument("--build-command", required=True)
    record_parser.add_argument("--build-log", type=Path, required=True)
    record_parser.add_argument("--built-artifact", type=Path, action="append", required=True)
    record_parser.add_argument("--runtime-evidence", type=Path, required=True)
    record_parser.add_argument("--out", type=Path, required=True)

    validate_parser = subparsers.add_parser("validate", help="validate complete target coverage and provenance")
    validate_parser.add_argument("--manifest", type=Path, required=True)
    validate_parser.add_argument("--identity", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command == "record":
            result = record(args)
        else:
            document = validate_execution_identity(args.manifest, args.identity)
            result = {
                "status": "valid",
                "identity": str(args.identity.resolve()),
                "dependencies": dependency_paths(document),
            }
    except (OSError, ValueError, KeyError, TypeError) as error:
        emit(json.dumps({"status": "invalid", "reason": str(error)}, ensure_ascii=False))
        return 2
    emit(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
