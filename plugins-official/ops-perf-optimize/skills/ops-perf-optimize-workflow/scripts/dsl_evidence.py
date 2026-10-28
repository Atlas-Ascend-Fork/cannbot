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

"""Capture DSL toolchain facts and validate source/configuration/build/load evidence.

This validates collected evidence; it does not invent a compiler observation or
claim functional/performance success. Version-specific harnesses supply variants.
"""
from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cli_output import emit
from prepare_case_sets import (
    CODE_SUFFIXES,
    IGNORED_CODE_DIRS,
    code_identity,
    case_id,
    identity,
    inventory_csv,
    read_csv,
)
from validate_execution_identity import atomic_json, file_identity, read_json, validate_runtime_evidence
from workflow_backend import validate_backend


def _compile_environment() -> dict:
    selected = {}
    for key, value in sorted(os.environ.items()):
        if key.startswith("CANNBOTDSL_") or key in (
            "ASCEND_HOME_PATH", "ASCEND_OPP_PATH", "ASCEND_AICPU_PATH"
        ):
            selected[key] = value
    return selected


def environment_snapshot() -> dict:
    spec = importlib.util.find_spec("cannbotdsl")
    if spec is None or not spec.origin:
        raise ValueError("cannbotdsl is not installed in the configured Python")
    distribution = importlib.metadata.distribution("cannbot-dsl")
    root = Path(spec.origin).parent
    # Source plus shipped compiler binaries: a version string alone is not identity.
    files = sorted(path for path in root.rglob("*") if path.is_file() and path.suffix in (".py", ".so"))
    return {
        "schema_version": 1,
        "python": str(Path(sys.executable).resolve()),
        "dsl_version": distribution.version,
        "package_root": str(root.resolve()),
        "package_files": [file_identity(path) for path in files],
        "compile_environment": _compile_environment(),
    }


def verify_file(value: dict) -> str:
    if not isinstance(value, dict) or not value.get("path") or not value.get("sha256"):
        raise ValueError("file evidence requires path and sha256")
    actual = file_identity(Path(value["path"]))
    if actual != value:
        raise ValueError(f"evidence changed: {value['path']}")
    return actual["path"]


def _checked_file(value, receipts):
    path = verify_file(value)
    if path in receipts and receipts[path] != value:
        raise ValueError("DSL file evidence changed during validation")
    receipts[path] = dict(value)
    return path


def _validate_context(evidence: dict, manifest: dict, manifest_path: Path, stage: str | None) -> dict:
    config = manifest["configuration"]
    validate_backend(config)
    if config.get("backend") != "cannbot_dsl":
        raise ValueError("DSL evidence requires a cannbot_dsl manifest")
    if evidence.get("schema_version") not in (1, 2) or evidence.get("backend") != "cannbot_dsl":
        raise ValueError("unsupported DSL evidence schema/backend")
    if evidence.get("stage") not in ("baseline", "preparation", "analysis", "implementation", "integration"):
        raise ValueError("invalid DSL evidence stage")
    if stage is not None and evidence["stage"] != stage:
        raise ValueError("DSL evidence belongs to another stage")
    if evidence.get("manifest") != file_identity(manifest_path):
        raise ValueError("DSL evidence belongs to another manifest")
    if evidence.get("dsl") != config["dsl"]:
        raise ValueError("DSL entrypoint or execution mode differs from frozen configuration")
    return config


def _validate_source(evidence: dict, manifest: dict, config: dict) -> dict:
    source = evidence.get("source", {})
    if not source.get("path") or code_identity(Path(source["path"])) != source:
        raise ValueError("DSL source/dependency identity changed")
    if evidence["stage"] == "baseline" and source != manifest["inputs"]["code"]:
        raise ValueError("baseline DSL source differs from frozen source")
    return source


def _owner_source_within_tree(path: Path, owned_source: dict, source: dict) -> bool:
    return (path.is_absolute() and path.is_dir()
            and path.resolve().is_relative_to(Path(source["path"]).resolve())
            and code_identity(path) == owned_source)


def _validate_owners(evidence: dict, source: dict) -> dict:
    if evidence["stage"] == "baseline":
        raise ValueError("baseline DSL evidence cannot replace the frozen source with grouped owners")
    groups = evidence.get("source_owners")
    if not isinstance(groups, list) or not groups:
        raise ValueError("grouped DSL evidence requires source owners")
    owners = {}
    for owner in groups:
        name, owned_source = owner.get("id"), owner.get("source", {})
        if not isinstance(name, str) or not name or name in owners:
            raise ValueError("missing or duplicate DSL source owner")
        path = Path(owned_source.get("path", ""))
        if not _owner_source_within_tree(path, owned_source, source):
            raise ValueError("DSL source owner is changed or outside the public dispatch tree")
        owners[name] = owned_source
    return owners


def _validate_environment(evidence: dict, manifest: dict, receipts: dict, deps: list) -> None:
    environment_path = _checked_file(evidence["environment"], receipts)
    deps.append(environment_path)
    frozen_environment = manifest["inputs"].get("dsl_environment")
    if not frozen_environment or evidence["environment"] != frozen_environment:
        raise ValueError("DSL compilation environment differs from the frozen preflight environment")
    environment = read_json(Path(environment_path))
    package_files = environment.get("package_files")
    if environment.get("schema_version") != 1 or not environment.get("dsl_version") or not package_files:
        raise ValueError("missing DSL package identity")
    deps.extend(_checked_file(item, receipts) for item in package_files)


def _register_variant(variant: dict, config: dict, identifiers: set, coverage: set) -> tuple:
    key = (variant.get("target_soc"), variant.get("id"))
    if not key[1] or key in identifiers:
        raise ValueError("missing or duplicate DSL variant id/SoC")
    identifiers.add(key)
    if key[0] not in config["target_socs"]:
        raise ValueError("DSL variant target SoC is not frozen")
    cases = variant.get("case_ids")
    if not isinstance(cases, list) or not cases or any(not isinstance(case, str) or not case for case in cases):
        raise ValueError("DSL variants require explicit case mapping")
    coverage.update((case, key[0]) for case in cases)
    return key


def _variant_owner(variant: dict, source: dict, owners: dict, grouped: bool) -> dict:
    if not grouped:
        return source
    owner_id = variant.get("source_owner_id")
    if owner_id not in owners:
        raise ValueError("DSL variant requires a registered source owner")
    if variant.get("component") not in ("attention", "AICPU_metadata"):
        raise ValueError("DSL grouped variant requires its actual component")
    return owners[owner_id]


def _validate_compile_config(variant: dict, key: tuple, variant_source: dict, evidence: dict,
                             config: dict, receipts: dict, deps: list) -> None:
    config_path = _checked_file(variant["compile_config"], receipts)
    deps.append(config_path)
    compile_config = read_json(Path(config_path))
    if (compile_config.get("source") != variant_source
            or compile_config.get("environment") != evidence["environment"]):
        raise ValueError("compile configuration is not bound to source/environment")
    if compile_config.get("target_soc") != key[0] or not compile_config.get("target_arch"):
        raise ValueError("compile configuration target mismatch")
    if compile_config.get("entrypoint") != config["dsl"]["entrypoint"]:
        raise ValueError("compile configuration entrypoint mismatch")
    if compile_config.get("execution_mode") != config["dsl"]["execution_mode"]:
        raise ValueError("compile configuration execution mode mismatch")
    if not isinstance(compile_config.get("parameters"), dict):
        raise ValueError("compile configuration requires parameter/spec/tiling facts")


def _validate_build_outputs(variant: dict, variant_source: dict, config: dict,
                            receipts: dict, deps: list) -> list:
    generated = variant.get("generated_sources", [])
    if config["dsl"]["execution_mode"] == "jit" and not generated:
        raise ValueError("JIT evidence requires generated code")
    deps.extend(_checked_file(item, receipts) for item in generated)
    build_log = _checked_file(variant["build_log"], receipts)
    deps.append(build_log)
    built = variant.get("built_artifacts", [])
    if not built:
        raise ValueError("DSL variant has no built artifacts")
    deps.extend(_checked_file(item, receipts) for item in built)
    # The collected build receipt must identify both its inputs and outputs.
    log = Path(build_log).read_text(encoding="utf-8", errors="replace")
    required_hashes = [variant_source["sha256"], variant["compile_config"]["sha256"]]
    required_hashes.extend(item["sha256"] for item in generated + built)
    if any(value not in log for value in required_hashes):
        raise ValueError("DSL build log does not bind source/configuration/code/binary")
    return built


def _bind_runtime_evidence(variant: dict, key: tuple, built: list, variant_source: dict, grouped: bool,
                           receipts: dict, deps: list, execution_variants: dict) -> None:
    runtime_path = _checked_file(variant["runtime_evidence"], receipts)
    deps.append(runtime_path)
    runtime, loaded, raw = validate_runtime_evidence(Path(runtime_path))
    if runtime.get("target_soc") != key[0]:
        raise ValueError("DSL runtime target SoC mismatch")
    if runtime.get("compile_config") != variant["compile_config"]:
        raise ValueError("DSL runtime configuration mismatch")
    if any(item["sha256"] not in {binary["sha256"] for binary in built} for item in loaded):
        raise ValueError("loaded DSL binary was not built from this variant")
    deps.extend(item["path"] for item in loaded + raw)
    if grouped:
        for item in loaded + raw:
            if item["path"] in receipts and receipts[item["path"]] != item:
                raise ValueError("DSL runtime file changed during validation")
            receipts[item["path"]] = dict(item)
        execution_variants[key] = (variant, variant_source, raw)


def _validate_variants(variants: list, evidence: dict, config: dict, source: dict, owners: dict,
                       grouped: bool, receipts: dict, deps: list) -> tuple:
    identifiers = set()
    coverage = set()
    execution_variants = {}
    for variant in variants:
        key = _register_variant(variant, config, identifiers, coverage)
        variant_source = _variant_owner(variant, source, owners, grouped)
        _validate_compile_config(variant, key, variant_source, evidence, config, receipts, deps)
        built = _validate_build_outputs(variant, variant_source, config, receipts, deps)
        _bind_runtime_evidence(variant, key, built, variant_source, grouped, receipts, deps,
                               execution_variants)
    return coverage, execution_variants


def _frozen_collection(evidence: dict, manifest: dict) -> tuple:
    collection = evidence.get("collection")
    if collection not in manifest["collections"]:
        raise ValueError("DSL evidence requires a frozen case collection")
    inventory = manifest["collections"][collection]
    inventory_path = Path(inventory["path"])
    if identity(inventory_path)["sha256"] != inventory["sha256"]:
        raise ValueError("DSL case inventory changed")
    _, rows = read_csv(inventory_csv(inventory_path))
    return collection, inventory_path, rows


def _frozen_kinds(rows: list) -> tuple:
    kinds, assertions = {}, {}
    for index, row in enumerate(rows):
        identifier = case_id(row, index)
        if identifier in kinds:
            raise ValueError("frozen collection contains duplicate case IDs")
        kind = row.get("execution_kind") or ("expected_error" if row.get("expected_error") else "device")
        if kind not in ("device", "host_only", "expected_error"):
            raise ValueError(f"invalid frozen DSL execution kind: {identifier}")
        if kind == "expected_error" and not row.get("expected_error"):
            raise ValueError("expected_error case requires its frozen error substring")
        if kind == "host_only" and not (row.get("host_assertion") or row.get("pytest_nodeid")):
            raise ValueError("host_only case requires a frozen assertion or pytest nodeid")
        kinds[identifier] = kind
        assertions[identifier] = row
    return kinds, assertions


def _check_coverage(kinds: dict, config: dict) -> tuple:
    expected = set()
    for case, kind in kinds.items():
        if kind == "device":
            expected.update((case, soc) for soc in config["target_socs"])
    non_device = set()
    for case, kind in kinds.items():
        if kind != "device":
            non_device.update((case, soc) for soc in config["target_socs"])
    return expected, non_device


def _execution_binding_mismatch(result: dict, variant: dict) -> bool:
    return (result.get("source_owner_id") != variant["source_owner_id"]
            or result.get("component") != variant["component"]
            or result.get("compile_config") != variant["compile_config"]
            or result.get("runtime_evidence") != variant["runtime_evidence"]
            or result.get("execution_kind") != "device")


def _observation_recorded(observations, result: dict, observed_fields: tuple) -> bool:
    return (isinstance(observations, list)
            and any(isinstance(item, dict) and all(item.get(field) == result.get(field)
                                                   for field in observed_fields)
                    for item in observations))


def _validate_execution_result(result: dict, execution_variants: dict, required_calls: set, seen: set,
                               case_owners: dict, receipts: dict, deps: list) -> None:
    key = (result.get("case_id"), result.get("target_soc"), result.get("variant_id"))
    if key not in required_calls or key in seen:
        raise ValueError("DSL execution owner case/variant coverage mismatch")
    seen.add(key)
    entry = execution_variants.get((key[1], key[2]))
    if entry is None:
        raise KeyError((key[1], key[2]))
    variant, owned_source, raw = entry
    if _execution_binding_mismatch(result, variant):
        raise ValueError("DSL execution owner binding mismatch")
    component_key = (key[0], key[1], variant["component"])
    if component_key in case_owners and case_owners[component_key] != variant["source_owner_id"]:
        raise ValueError("DSL case component maps to conflicting source owners")
    case_owners[component_key] = variant["source_owner_id"]
    provider = result.get("provider_source")
    provider_path = Path(_checked_file(provider, receipts))
    if not provider_path.is_relative_to(Path(owned_source["path"]).resolve()):
        raise ValueError("actual DSL Provider source is outside its owner")
    deps.append(str(provider_path))
    raw_receipt = result.get("raw_evidence")
    raw_path = _checked_file(raw_receipt, receipts)
    if raw_receipt not in raw:
        raise ValueError("DSL Provider invocation is not bound to actual runtime evidence")
    deps.append(raw_path)
    observations = read_json(Path(raw_path)).get("invocations")
    method = ("ProviderCallable.__call__" if variant["component"] == "attention"
              else "CompiledAicpuKernel.launch")
    if result.get("observer_method") != method:
        raise ValueError("DSL execution owner requires an actual component invocation")
    observed_fields = ("case_id", "target_soc", "source_owner_id", "provider_source",
                       "execution_kind", "component", "observer_method")
    if not _observation_recorded(observations, result, observed_fields):
        raise ValueError("DSL actual Provider invocation observation is missing")


def _validate_execution_owner(evidence: dict, source: dict, collection, execution_variants: dict,
                              owners: dict, expected: set, receipts: dict, deps: list) -> None:
    attention_coverage = set()
    for (soc, _), (variant, _, _) in execution_variants.items():
        if variant["component"] == "attention":
            attention_coverage.update((case, soc) for case in variant["case_ids"])
    if attention_coverage != expected:
        raise ValueError("DSL actual attention coverage differs from frozen inventory")
    execution_path = _checked_file(evidence.get("execution_owner_evidence"), receipts)
    deps.append(execution_path)
    execution = read_json(Path(execution_path))
    if (execution.get("schema_version") != 1 or execution.get("source") != source
            or execution.get("collection") != collection):
        raise ValueError("DSL execution owner evidence context mismatch")
    results = execution.get("results")
    if not isinstance(results, list):
        raise ValueError("DSL execution owner evidence requires results")
    seen = set()
    case_owners = {}
    required_calls = set()
    for (soc, identifier), (variant, _, _) in execution_variants.items():
        required_calls.update((case, soc, identifier) for case in variant["case_ids"])
    for result in results:
        _validate_execution_result(result, execution_variants, required_calls, seen, case_owners,
                                   receipts, deps)
    if seen != required_calls:
        raise ValueError("DSL execution owner case/variant coverage mismatch")
    if {variant["source_owner_id"] for variant, _, _ in execution_variants.values()} != set(owners):
        raise ValueError("DSL source owner has no actual compiled execution")


def _validate_non_device(non_device: set, kinds: dict, assertions: dict, evidence: dict,
                         receipts: dict, deps: list) -> None:
    if not non_device:
        return
    path = _checked_file(evidence.get("non_device_evidence"), receipts)
    deps.append(path)
    results = read_json(Path(path)).get("results")
    if not isinstance(results, list):
        raise ValueError("non-device evidence requires per-case results")
    seen = set()
    for result in results:
        key = (result.get("case_id"), result.get("target_soc"))
        if key not in non_device or key in seen:
            raise ValueError("non-device case coverage mismatch")
        seen.add(key)
        if result.get("status") != "PASS" or result.get("execution_kind") != kinds[key[0]]:
            raise ValueError("non-device case did not pass its frozen execution kind")
        frozen = assertions[key[0]]
        if kinds[key[0]] == "expected_error":
            if (result.get("expected_substring") != frozen["expected_error"]
                    or frozen["expected_error"] not in str(result.get("error_excerpt", ""))):
                raise ValueError("expected error semantics changed")
        elif result.get("assertion") != (frozen.get("host_assertion") or frozen.get("pytest_nodeid")):
            raise ValueError("host-only assertion differs from frozen test")
        deps.append(_checked_file(result.get("raw_evidence"), receipts))
    if seen != non_device:
        raise ValueError("non-device case coverage mismatch")


def _verify_grouped_state(source: dict, owners: dict, receipts: dict, deps: list) -> None:
    for checked_source in [source, *owners.values()]:
        if code_identity(Path(checked_source["path"])) != checked_source:
            raise ValueError("DSL grouped source changed during validation")
    for root, directories, files in os.walk(source["path"]):
        directories[:] = sorted(name for name in directories if name not in IGNORED_CODE_DIRS)
        deps.extend(str(Path(root) / name) for name in sorted(files)
                    if Path(name).suffix.lower() in CODE_SUFFIXES or name in ("CMakeLists.txt", "Makefile"))
    for path, receipt in receipts.items():
        if file_identity(Path(path)) != receipt:
            raise ValueError("DSL grouped file changed during validation")


def validate(evidence: dict, manifest_path: Path, stage: str | None = None) -> list[str]:
    receipts = {}
    deps = []
    manifest = read_json(manifest_path)
    config = _validate_context(evidence, manifest, manifest_path, stage)
    source = _validate_source(evidence, manifest, config)
    grouped = evidence["schema_version"] == 2
    owners = _validate_owners(evidence, source) if grouped else {}
    _validate_environment(evidence, manifest, receipts, deps)
    variants = evidence.get("variants")
    if not isinstance(variants, list):
        raise ValueError("DSL evidence requires a compiled variants list")
    coverage, execution_variants = _validate_variants(variants, evidence, config, source, owners,
                                                      grouped, receipts, deps)
    collection, inventory_path, rows = _frozen_collection(evidence, manifest)
    kinds, assertions = _frozen_kinds(rows)
    expected, non_device = _check_coverage(kinds, config)
    if coverage != expected:
        raise ValueError("DSL compiled case coverage differs from frozen inventory")
    if grouped:
        _validate_execution_owner(evidence, source, collection, execution_variants, owners, expected,
                                  receipts, deps)
    _validate_non_device(non_device, kinds, assertions, evidence, receipts, deps)
    deps.append(str(inventory_path))
    if grouped:
        _verify_grouped_state(source, owners, receipts, deps)
    return list(dict.fromkeys(deps))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    env = commands.add_parser("environment", help="run with the confirmed Python and CANN environment")
    env.add_argument("--out", type=Path, required=True)
    check = commands.add_parser("validate")
    check.add_argument("--manifest", type=Path, required=True)
    check.add_argument("--evidence", type=Path, required=True)
    check.add_argument("--stage")
    args = parser.parse_args()
    try:
        if args.command == "environment":
            atomic_json(args.out, environment_snapshot())
            result = {"status": "captured", "environment": str(args.out.resolve())}
        else:
            deps = validate(read_json(args.evidence), args.manifest.resolve(), args.stage)
            result = {"status": "valid", "dependencies": deps}
    except (ValueError, OSError, KeyError, TypeError, importlib.metadata.PackageNotFoundError) as error:
        emit(json.dumps({"status": "invalid", "reason": str(error)}, ensure_ascii=False))
        return 2
    emit(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
