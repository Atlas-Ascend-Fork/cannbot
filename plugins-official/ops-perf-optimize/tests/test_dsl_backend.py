# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Behavioral checks for frozen DSL routing and compiler provenance gates."""
from __future__ import annotations

import json
import copy
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "ops-perf-optimize-workflow" / "scripts"))
from workflow_backend import validate_backend
from dsl_evidence import validate
from prepare_case_sets import code_identity, identity
from validate_execution_identity import file_identity
from validate_implementation_conformance import validate_candidate_safety, validate_manifest_scope, ContractError
from workflow_state import check_phase_artifacts
from test_prepare_case_sets import create_request, run, write_cases, load


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False))
    return file_identity(path)


def config(root):
    return {"repo_root": str(root), "entrypoint": "flash_attn.flash_attn:flash_attn",
            "execution_mode": "jit", "workload_scope": "network_cases"}


def fixture_evidence(root):
    source = root / "source"
    source.mkdir()
    (source / "op.py").write_text("def run(x):\n    return x\n")
    package = root / "package.py"
    package.write_text("# immutable test toolchain\n")
    env_id = write_json(root / "environment.json", {
        "schema_version": 1, "dsl_version": "test-version", "package_files": [file_identity(package)],
    })
    cases = root / "cases.csv"
    write_cases(cases, 2)
    manifest = {
        "configuration": {"backend": "cannbot_dsl", "dsl": config(root), "target_socs": ["Ascend950PR"],
                          "precision_diagnosis_policy": "persistent"},
        "inputs": {"code": code_identity(source), "dsl_environment": env_id},
        "collections": {"performance_full": identity(cases)},
    }
    manifest_path = root / "manifest.json"
    manifest_id = write_json(manifest_path, manifest)
    config_id = write_json(root / "config.json", {
        "source": code_identity(source), "environment": env_id,
        "target_soc": "Ascend950PR", "target_arch": "dav-3510",
        "entrypoint": config(root)["entrypoint"], "execution_mode": "jit",
        "parameters": {"tile": 128, "depth": 2},
    })
    generated = root / "generated.asc"
    generated.write_text("// generated code test fixture\n")
    binary = root / "program.so"
    binary.write_bytes(b"test fixture only, never used for NPU execution")
    build_log = root / "build.log"
    build_log.write_text("\n".join([
        code_identity(source)["sha256"], config_id["sha256"],
        file_identity(generated)["sha256"], file_identity(binary)["sha256"],
    ]))
    runtime_log = root / "runtime.log"
    runtime_log.write_text(f"loaded {binary} sha256={file_identity(binary)['sha256']}\n")
    runtime_id = write_json(root / "runtime.json", {
        "method": "synthetic provenance validator fixture; no hardware claims",
        "target_soc": "Ascend950PR", "compile_config": config_id,
        "loaded_artifacts": [file_identity(binary)], "source_artifacts": [file_identity(runtime_log)],
    })
    evidence = {
        "schema_version": 1, "backend": "cannbot_dsl", "stage": "implementation",
        "manifest": manifest_id, "dsl": config(root), "source": code_identity(source),
        "environment": env_id, "collection": "performance_full",
        "variants": [{"id": "v1", "target_soc": "Ascend950PR", "case_ids": ["case-000", "case-001"],
                      "compile_config": config_id, "generated_sources": [file_identity(generated)],
                      "build_log": file_identity(build_log), "built_artifacts": [file_identity(binary)],
                      "runtime_evidence": runtime_id}],
    }
    return manifest_path, evidence


def test_legacy_default_and_invalid_language_inputs(tmp_path):
    assert validate_backend({}) == "ascendc"
    with pytest.raises(ValueError, match="backend"):
        validate_backend({"backend": "typo"})
    with pytest.raises(ValueError, match="configuration"):
        validate_backend({"backend": "cannbot_dsl"})
    with pytest.raises(ValueError, match="entrypoint"):
        validate_backend({"backend": "cannbot_dsl", "dsl": {**config(tmp_path), "entrypoint": "python op.py"}})


def test_create_and_freeze_dsl_request_preserve_original_inventory(tmp_path):
    code = tmp_path / "code"
    code.mkdir()
    (code / "op.py").write_text("def run(x): return x\n")
    cases = tmp_path / "network.csv"
    write_cases(cases, 3)
    request = tmp_path / "request.json"
    create_request(request, code, cases, extra=(
        "--backend", "cannbot_dsl", "--dsl-repo-root", str(tmp_path),
        "--dsl-entrypoint", "op:run", "--dsl-execution-mode", "jit",
    ))
    package = tmp_path / "package.py"
    package.write_text("# test package identity")
    write_json(tmp_path / "dsl-environment.json", {
        "schema_version": 1, "dsl_version": "test", "package_files": [file_identity(package)],
    })
    run("freeze", "--request", request, "--output-dir", tmp_path / "run")
    manifest = load(tmp_path / "run/run-manifest.json")
    assert manifest["configuration"]["backend"] == "cannbot_dsl"
    assert manifest["configuration"]["dsl"]["entrypoint"] == "op:run"
    assert manifest["configuration"]["tuning_mode"] == "standard"
    assert manifest["collections"]["performance_full"]["count"] == 3
    assert manifest["inputs"]["dsl_environment"] == file_identity(tmp_path / "run/dsl-environment.json")


def test_evidence_validates_and_tracks_all_dependencies(tmp_path):
    manifest, evidence = fixture_evidence(tmp_path)
    paths = validate(evidence, manifest, "implementation")
    assert str(tmp_path / "program.so") in paths
    assert str(tmp_path / "package.py") in paths
    assert str(tmp_path / "generated.asc") in paths


def grouped_fixture(root):
    manifest, evidence = fixture_evidence(root)
    base_variant = evidence["variants"][0]
    owners, variants, results = [], [], []
    for index, owner_id in enumerate(("pristine", "optimized")):
        owner_path = root / "source" / owner_id
        owner_path.mkdir()
        provider = owner_path / "op.py"
        provider.write_text(f"def run(x):\n    return x + {index}\n")
        owned_source = code_identity(owner_path)
        owners.append({"id": owner_id, "source": owned_source})
        variant = copy.deepcopy(base_variant)
        variant.update(id=f"v{index}", source_owner_id=owner_id, component="attention",
                       case_ids=[f"case-00{index}"])
        compile_config = load(root / "config.json")
        compile_config["source"] = owned_source
        variant["compile_config"] = write_json(root / f"config-{index}.json", compile_config)
        log = root / f"build-{index}.log"
        artifacts = variant["generated_sources"] + variant["built_artifacts"]
        log.write_text("\n".join([owned_source["sha256"], variant["compile_config"]["sha256"],
                                  *[item["sha256"] for item in artifacts]]))
        variant["build_log"] = file_identity(log)
        observation = {"case_id": variant["case_ids"][0], "target_soc": "Ascend950PR",
                       "source_owner_id": owner_id, "provider_source": file_identity(provider),
                       "execution_kind": "device", "component": "attention",
                       "observer_method": "ProviderCallable.__call__"}
        raw_id = write_json(root / f"calls-{index}.json", {
            "invocations": [observation], "loaded_artifacts": variant["built_artifacts"],
        })
        runtime = load(root / "runtime.json")
        runtime.update(compile_config=variant["compile_config"], source_artifacts=[raw_id])
        variant["runtime_evidence"] = write_json(root / f"runtime-{index}.json", runtime)
        results.append({**observation, "variant_id": variant["id"], "raw_evidence": raw_id,
                        "compile_config": variant["compile_config"], "runtime_evidence": variant["runtime_evidence"]})
        variants.append(variant)
    evidence.update(schema_version=2, source=code_identity(root / "source"),
                    source_owners=owners, variants=variants)
    mapping = {"schema_version": 1, "source": evidence["source"],
               "collection": evidence["collection"], "results": results}
    evidence["execution_owner_evidence"] = write_json(root / "execution-owners.json", mapping)
    return manifest, evidence


def test_grouped_actual_owners_validate_without_forging_legacy_source(tmp_path):
    manifest, evidence = grouped_fixture(tmp_path)
    deps = validate(evidence, manifest, "implementation")
    assert str(tmp_path / "source/pristine/op.py") in deps
    assert str(tmp_path / "source/optimized/op.py") in deps
    assert str(tmp_path / "source/op.py") in deps
    assert str(tmp_path / "execution-owners.json") in deps
    assert evidence["source"] != evidence["source_owners"][0]["source"]


def test_grouped_rechecks_verified_files_before_return_without_timestamp_cache(tmp_path, monkeypatch):
    import dsl_evidence
    manifest, evidence = grouped_fixture(tmp_path)
    original_read = dsl_evidence.read_json

    def mutate_after_package_check(path):
        document = original_read(path)
        if Path(path).name == "execution-owners.json":
            package = tmp_path / "package.py"
            payload = package.read_bytes()
            package.write_bytes(b"!" + payload[1:])
        return document

    monkeypatch.setattr(dsl_evidence, "read_json", mutate_after_package_check)
    with pytest.raises(ValueError, match="grouped file changed"):
        validate(evidence, manifest)


def test_grouped_metadata_uses_real_launch_observation_not_fake_provider_call(tmp_path):
    manifest, evidence = grouped_fixture(tmp_path)
    mapping = load(tmp_path / "execution-owners.json")
    metadata = copy.deepcopy(evidence["variants"][0])
    metadata.update(id="metadata-real", component="AICPU_metadata")
    first_result = mapping["results"][0]
    observed = {}
    for field in ("case_id", "target_soc", "source_owner_id", "provider_source", "execution_kind"):
        observed[field] = first_result[field]
    observed.update(component="AICPU_metadata", observer_method="CompiledAicpuKernel.launch")
    raw = write_json(tmp_path / "metadata-calls.json", {
        "invocations": [observed], "loaded_artifacts": metadata["built_artifacts"],
    })
    runtime = load(tmp_path / "runtime-0.json")
    runtime["source_artifacts"] = [raw]
    metadata["runtime_evidence"] = write_json(tmp_path / "metadata-runtime.json", runtime)
    evidence["variants"].append(metadata)
    mapping["results"].append({**observed, "variant_id": metadata["id"], "raw_evidence": raw,
                               "compile_config": metadata["compile_config"],
                               "runtime_evidence": metadata["runtime_evidence"]})
    evidence["execution_owner_evidence"] = write_json(tmp_path / "execution-owners.json", mapping)
    assert str(tmp_path / "metadata-calls.json") in validate(evidence, manifest)
    mapping["results"][-1]["observer_method"] = "ProviderCallable.__call__"
    evidence["execution_owner_evidence"] = write_json(tmp_path / "execution-owners.json", mapping)
    with pytest.raises(ValueError, match="actual component invocation"):
        validate(evidence, manifest)


@pytest.mark.parametrize("mutation,match", [
    ("changed_owner", "source"), ("outside_owner", "outside"),
    ("duplicate_owner", "duplicate"), ("unknown_owner", "registered"),
    ("wrong_config", "bound"), ("missing_case", "coverage"),
    ("wrong_owner", "binding"), ("load_only", "invocation"),
    ("raw_not_runtime", "runtime"), ("wrong_provider", "outside"),
    ("metadata_hides_attention", "attention coverage"), ("baseline", "baseline"),
])
def test_grouped_owner_forgeries_and_incomplete_invocations_rejected(tmp_path, mutation, match):
    manifest, evidence = grouped_fixture(tmp_path)
    mapping = load(tmp_path / "execution-owners.json")
    if mutation == "changed_owner":
        (tmp_path / "source/pristine/op.py").write_text("changed same owner\n")
    elif mutation == "outside_owner":
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "op.py").write_text("def run(x): return x\n")
        evidence["source_owners"][0]["source"] = code_identity(outside)
    elif mutation == "duplicate_owner":
        evidence["source_owners"].append(evidence["source_owners"][0])
    elif mutation == "unknown_owner":
        evidence["variants"][0]["source_owner_id"] = "invented"
    elif mutation == "wrong_config":
        value = load(tmp_path / "config-0.json")
        value["source"] = evidence["source"]
        evidence["variants"][0]["compile_config"] = write_json(tmp_path / "config-0.json", value)
    elif mutation == "missing_case":
        mapping["results"].pop()
    elif mutation == "wrong_owner":
        mapping["results"][0]["source_owner_id"] = "optimized"
    elif mutation == "load_only":
        raw = tmp_path / "calls-0.json"
        raw_id = write_json(raw, {"invocations": [], "loaded_artifacts": evidence["variants"][0]["built_artifacts"]})
        runtime = load(tmp_path / "runtime-0.json")
        runtime["source_artifacts"] = [raw_id]
        runtime_id = write_json(tmp_path / "runtime-0.json", runtime)
        evidence["variants"][0]["runtime_evidence"] = runtime_id
        mapping["results"][0].update(raw_evidence=raw_id, runtime_evidence=runtime_id)
    elif mutation == "raw_not_runtime":
        mapping["results"][0]["raw_evidence"] = file_identity(tmp_path / "calls-1.json")
    elif mutation == "wrong_provider":
        mapping["results"][0]["provider_source"] = file_identity(tmp_path / "source/optimized/op.py")
    elif mutation == "metadata_hides_attention":
        evidence["variants"][0]["component"] = "AICPU_metadata"
    elif mutation == "baseline":
        evidence["stage"] = "baseline"
    evidence["execution_owner_evidence"] = write_json(tmp_path / "execution-owners.json", mapping)
    with pytest.raises(ValueError, match=match):
        validate(evidence, manifest)


@pytest.mark.parametrize("mutation,match", [
    ("coverage", "coverage"), ("stage", "stage"), ("source", "source"),
    ("build", "bind"), ("loaded", "not built"), ("package", "changed"),
    ("config", "execution mode"), ("generated", "generated code"),
])
def test_stale_or_misattributed_dsl_evidence_is_rejected(tmp_path, mutation, match):
    manifest, evidence = fixture_evidence(tmp_path)
    variant = evidence["variants"][0]
    if mutation == "coverage":
        variant["case_ids"].pop()
    elif mutation == "stage":
        evidence["stage"] = "preparation"
    elif mutation == "source":
        (tmp_path / "source/op.py").write_text("def run(x): return x + 1\n")
    elif mutation == "build":
        (tmp_path / "build.log").write_text("build succeeded, without input provenance")
        variant["build_log"] = file_identity(tmp_path / "build.log")
    elif mutation == "loaded":
        other = tmp_path / "other.so"
        other.write_bytes(b"unrelated loaded artifact")
        raw = tmp_path / "runtime.log"
        raw.write_text(f"loaded {other} sha256={file_identity(other)['sha256']}")
        runtime = load(tmp_path / "runtime.json")
        runtime.update(loaded_artifacts=[file_identity(other)], source_artifacts=[file_identity(raw)])
        variant["runtime_evidence"] = write_json(tmp_path / "runtime.json", runtime)
    elif mutation == "package":
        (tmp_path / "package.py").write_text("# changed toolchain")
    elif mutation == "config":
        value = load(tmp_path / "config.json")
        value["execution_mode"] = "aot"
        variant["compile_config"] = write_json(tmp_path / "config.json", value)
    elif mutation == "generated":
        variant["generated_sources"] = []
    with pytest.raises(ValueError, match=match):
        validate(evidence, manifest, "implementation")


def test_phase_gate_requires_compilation_proof(tmp_path):
    manifest, _ = fixture_evidence(tmp_path)
    names = ["extraction-manifest.json", "source-compatibility.md", "functional-acceptance.md"]
    for name in names:
        (tmp_path / name).write_text("{}")
    with pytest.raises(ValueError, match="dsl-compile-evidence"):
        check_phase_artifacts("preparation", [str(tmp_path / name) for name in names], manifest)


def test_python_signature_is_protected_but_kernel_body_can_change(tmp_path):
    old, new = tmp_path / "baseline", tmp_path / "candidate"
    old.mkdir()
    new.mkdir()
    (old / "op.py").write_text("def run(x, *, scale=1.0):\n    return x * scale\n")
    (new / "op.py").write_text("def run(x, *, scale=1.0):\n    return scale * x\n")
    assert validate_candidate_safety(old, new, "cannbot_dsl")["decision"] == "pass"
    (new / "op.py").write_text("def run(x, *, scale=2.0):\n    return scale * x\n")
    assert validate_candidate_safety(old, new, "cannbot_dsl")["decision"] == "fail"


def test_contract_cannot_cross_language_or_require_cpp_casttrait():
    manifest = {"configuration": {"backend": "cannbot_dsl", "target_socs": ["Ascend950PR"]}}
    with pytest.raises(ContractError, match="backend"):
        validate_manifest_scope({"target_socs": ["Ascend950PR"]}, manifest)
    with pytest.raises(ContractError, match="CastTrait"):
        validate_manifest_scope({"backend": "cannbot_dsl", "target_socs": ["Ascend950PR"],
                                 "expectations": {"vf": True, "casttrait": True}}, manifest)


def test_host_checks_preserve_functional_coverage_without_fake_compilation(tmp_path):
    manifest_path, evidence = fixture_evidence(tmp_path)
    cases = tmp_path / "cases.csv"
    cases.write_text("case_id,execution_kind,pytest_nodeid,expected_error\n"
                     "case-000,host_only,test_interface_guard,\n"
                     "case-001,expected_error,,invalid shape\n")
    manifest = load(manifest_path)
    manifest["collections"]["performance_full"] = identity(cases)
    evidence["manifest"] = write_json(manifest_path, manifest)
    evidence["variants"] = []
    raw = tmp_path / "functional.log"
    raw.write_text("test_interface_guard PASS; invalid shape rejected\n")
    results = [
        {"case_id": "case-000", "target_soc": "Ascend950PR", "execution_kind": "host_only",
         "status": "PASS", "assertion": "test_interface_guard", "raw_evidence": file_identity(raw)},
        {"case_id": "case-001", "target_soc": "Ascend950PR", "execution_kind": "expected_error",
         "status": "PASS", "expected_substring": "invalid shape", "error_excerpt": "ValueError: invalid shape",
         "raw_evidence": file_identity(raw)},
    ]
    evidence["non_device_evidence"] = write_json(tmp_path / "non-device.json", {"results": results})
    assert str(raw) in validate(evidence, manifest_path, "implementation")
    results[1]["error_excerpt"] = "different error"
    evidence["non_device_evidence"] = write_json(tmp_path / "non-device.json", {"results": results})
    with pytest.raises(ValueError, match="semantics"):
        validate(evidence, manifest_path, "implementation")


def test_host_only_regression_gate_checks_assertions_not_npu_times(tmp_path):
    from validate_postprocess_performance import validate as regression
    functional = tmp_path / "functional.csv"
    functional.write_text("case_id,execution_kind,pytest_nodeid\nguard,host_only,test_guard\n")
    performance = tmp_path / "performance.csv"
    performance.write_text("case_id\nnetwork\n")
    manifest = tmp_path / "manifest.json"
    write_json(manifest, {
        "schema_version": 2, "configuration": {"target_socs": ["Ascend950PR"]},
        "collections": {"functional_full": identity(functional), "performance_full": identity(performance)},
    })
    empty, timed = tmp_path / "empty.csv", tmp_path / "timed.csv"
    empty.write_text("case_id,total_us\n")
    timed.write_text("case_id,total_us\nnetwork,10\n")
    raw = tmp_path / "raw.log"
    raw.write_text("test_guard PASS\n")
    host = tmp_path / "host.json"
    write_json(host, {"results": [{"case_id": "guard", "status": "PASS", "assertion": "test_guard",
                                  "raw_evidence": file_identity(raw)}]})
    paths = {"functional": (empty, empty), "performance": (timed, timed)}
    with pytest.raises(ValueError, match="host-only"):
        regression(manifest, "Ascend950PR", paths)
    gate = regression(manifest, "Ascend950PR", paths, functional_host_checks=(host, host))
    assert gate["decision"] == "pass"
    assert gate["collections"]["functional"]["summary"]["timing_not_applicable"] is True


def test_phase_evidence_lookup_prefers_operator_registration_over_closure_extras(tmp_path, monkeypatch):
    """Schedule closures may carry same-named evidence from earlier rounds.

    The operator's explicit registration must win the name-keyed phase lookup.
    """
    import dsl_evidence
    monkeypatch.setattr(dsl_evidence, "validate", lambda evidence, manifest_path, stage=None: [])
    manifest = tmp_path / "run-manifest.json"
    manifest.write_text(json.dumps({
        "schema_version": 2,
        "configuration": {"workflow_layout": "five-stage-v1", "backend": "cannbot_dsl",
                          "target_socs": ["Ascend950"],
                          "dsl": {"repo_root": str(tmp_path), "entrypoint": "m:f",
                                  "execution_mode": "jit", "workload_scope": "network_cases"},
                          "precision_diagnosis_policy": "persistent"},
        "inputs": {}, "collections": {}, "request": {},
    }))
    stale = tmp_path / "round1" / "dsl-compile-evidence.json"
    stale.parent.mkdir(parents=True)
    stale.write_text(json.dumps({"collection": "functional_acceptance", "stage": "implementation", "variants": []}))
    fresh = tmp_path / "implementation" / "final" / "dsl-compile-evidence.json"
    fresh.parent.mkdir(parents=True)
    fresh.write_text(json.dumps({"collection": "performance_full", "stage": "implementation", "variants": []}))
    reports = [tmp_path / "final-functional-regression.md", tmp_path / "final-performance-comparison.md"]
    for item in reports:
        item.write_text("final acceptance report")
    # Closure-only list (stale last) reproduces the defect: the lookup must not
    # silently accept the earlier-round evidence.
    with pytest.raises(ValueError, match="compiled coverage of performance_full"):
        check_phase_artifacts("implementation", [str(p) for p in reports] + [str(fresh), str(stale)], manifest)
    # Operator registration wins over closure extras of the same basename.
    artifacts = check_phase_artifacts(
        "implementation", [str(p) for p in reports] + [str(fresh), str(stale)], manifest,
        user_paths=[str(p) for p in reports] + [str(fresh)])
    assert json.loads(fresh.read_text())["collection"] == "performance_full"
    assert str(fresh) in artifacts and str(stale) in artifacts
