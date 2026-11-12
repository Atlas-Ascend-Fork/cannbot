#!/usr/bin/env python3
# ----------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------
"""Read-only coverage/version check; does not decide design conformance."""

import argparse
import hashlib
import json
import logging
from pathlib import Path
import sys

import yaml

LOGGER = logging.getLogger(__name__)
ERROR_LOGGER = logging.getLogger(__name__ + ".errors")


class UniqueLoader(yaml.SafeLoader):
    pass


def unique_mapping(loader, node):
    result = {}
    for key, value in node.value:
        key = loader.construct_object(key)
        if not isinstance(key, str) or key in result:
            raise ValueError("mapping keys must be unique strings")
        result[key] = loader.construct_object(value)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def read_yaml(path):
    loader = UniqueLoader(path.read_text(encoding="utf-8"))
    try:
        return loader.get_single_data()
    finally:
        loader.dispose()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be nonempty text")
    return value


def file_in(work, name):
    path = Path(text(name, "path"))
    path = path if path.is_absolute() else work / path
    resolved = path.resolve()
    if not resolved.is_relative_to(work) or not resolved.is_file():
        raise ValueError(f"missing file or outside work directory: {path}")
    return resolved


def unit_contract(path):
    document = read_yaml(path)
    if not isinstance(document, dict) or set(document) != {"unit"}:
        raise ValueError(f"invalid Unit: {path}")
    unit = document["unit"]
    if not isinstance(unit, dict) or unit.get("unit_id") != path.stem:
        raise ValueError(f"Unit identity differs: {path}")
    return unit


def unit_sources(work, unit, identity):
    scope = unit.get("scope", {})
    declared = scope.get("source_files") if isinstance(scope, dict) else None
    if not isinstance(declared, list):
        raise ValueError(f"{identity}: explicit scope.source_files required")
    sources = {}
    for name in declared:
        source = file_in(work, name)
        sources[str(source.relative_to(work))] = digest(source)
    return sources


def required_checks(unit, identity):
    implementation = unit.get("implementation", {})
    if not isinstance(implementation, dict):
        raise ValueError("implementation must be a mapping")
    required = []
    for section, items in (
        ("design_constraints", unit.get("design_constraints", [])),
        ("feasibility_checks", implementation.get("feasibility_checks", [])),
    ):
        if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
            raise ValueError(f"{identity}: invalid {section}")
        required.extend(f"{identity}/{section}/{i}" for i in range(len(items)))
    return required


def design_assets(work):
    # Bind the new design selection and this run's archived model provenance too.
    # Shared/external model workspaces are not traversed.
    assets = {}
    selection = work / "design/selection.yaml"
    if not selection.exists():
        return assets
    path = file_in(work, str(selection))
    assets[str(path.relative_to(work))] = digest(path)
    model = work / "design/model"
    if not model.exists():
        return assets
    for artifact in sorted(model.rglob("*")):
        if any(part in {".git", "__pycache__", ".pytest_cache"} for part in artifact.relative_to(model).parts):
            continue
        if artifact.is_file():
            path = file_in(work, str(artifact))
            assets[str(path.relative_to(work))] = digest(path)
    return assets


def snapshot(work):
    design = file_in(work, "design/doc/DESIGN.md")
    unit_files = sorted((work / "design/units").glob("U*.yaml"))
    if not unit_files:
        raise ValueError("no Unit contracts")
    units, sources, required = {}, {}, []
    for path in unit_files:
        path = file_in(work, str(path))
        unit = unit_contract(path)
        units[path.stem] = digest(path)
        sources.update(unit_sources(work, unit, path.stem))
        required.extend(required_checks(unit, path.stem))
    if not sources:
        raise ValueError("no declared implementation source files")
    assets = design_assets(work)
    return {"version": 1, "design_sha256": digest(design), "units": units,
            "sources": sources, "required_checks": required, "design_assets": assets}


def check(work, record):
    current = snapshot(work)
    if not isinstance(record, dict):
        raise ValueError("evidence record must be a mapping")
    if record.get("snapshot") != current:
        raise ValueError("snapshot differs from current design, Units or declared source files")
    checks = record.get("checks")
    if not isinstance(checks, list):
        raise ValueError("checks must be a list")
    seen = set()
    for item in checks:
        if not isinstance(item, dict):
            raise ValueError("check entry must be a mapping")
        identity = text(item.get("id"), "check.id")
        if identity in seen or identity not in current["required_checks"]:
            raise ValueError(f"duplicate or unknown check: {identity}")
        seen.add(identity)
        text(item.get("finding"), f"{identity}.finding")
        evidence = item.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            raise ValueError(f"{identity}: evidence files required")
        for ref in evidence:
            if not isinstance(ref, dict):
                raise ValueError("evidence reference must be a mapping")
            artifact = file_in(work, ref.get("path"))
            if artifact == record_path(work):
                raise ValueError("the evidence index cannot be its own evidence")
            if ref.get("sha256") != digest(artifact):
                raise ValueError(f"evidence missing or stale: {artifact}")
    missing = set(current["required_checks"]) - seen
    if missing:
        raise ValueError("missing checks: " + ", ".join(sorted(missing)))
    return current


def record_path(work):
    return work / "implementation/design-evidence.yaml"


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    ERROR_LOGGER.addHandler(logging.StreamHandler(sys.stderr))
    ERROR_LOGGER.propagate = False
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--snapshot", action="store_true", help="print current identities and required checks only")
    args = parser.parse_args()
    work = args.work_dir.resolve()
    try:
        if args.snapshot:
            LOGGER.info("%s", json.dumps(snapshot(work), ensure_ascii=False, indent=2))
        else:
            check(work, read_yaml(record_path(work)))
            LOGGER.info("design-evidence: records complete and current; semantic review still required")
    except (OSError, ValueError, TypeError, yaml.YAMLError) as error:
        ERROR_LOGGER.error("design-evidence: %s", error)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
