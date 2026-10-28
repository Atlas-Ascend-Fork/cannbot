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
"""Verify pre-registered independent msprof-op samples without inventing application rows.

Diagnostic single captures remain useful but never constitute this final proof.
This module does not execute a profiler or reserve an accelerator.
"""

from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
import re
import statistics
from datetime import datetime, timezone
from pathlib import Path

from cli_output import emit

KIND = "msprof_op10_independent_v1"


def require(value, message):
    if not value:
        raise ValueError(message)


def timestamp(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(result.tzinfo is not None, "attempt/registration timestamps require timezone")
    return result


def bind(value, deps):
    from performance_effect_evidence import check_receipt

    require(
        isinstance(value, dict) and isinstance(value.get("path"), str) and Path(value["path"]).is_absolute(),
        "absolute evidence reference required",
    )
    actual = check_receipt(value)
    require(value == actual, "noncanonical evidence reference")
    deps[actual["path"]] = actual
    return Path(actual["path"])


def read_ref(value, deps):
    from performance_effect_evidence import read

    return read(bind(value, deps))


def check_execution(value, source, soc, generated, deps):
    from validate_execution_identity import validate_document, dependency_paths
    from performance_effect_evidence import receipt, read

    document = read_ref(value, deps)
    require(document.get("source") == source, "executed source identity differs from frozen variant")
    validate_document({"configuration": {"target_socs": [soc]}, "inputs": {"code": source}}, document)
    for path in dependency_paths(document):
        item = receipt(path)
        deps[item["path"]] = item
    target = document["targets"][0]
    build = target["build"]
    build_text = Path(build["log"]["path"]).read_text(errors="replace")
    required = [source["sha256"]] + [item["sha256"] for item in generated + build["artifacts"]]
    require(
        all(digest in build_text for digest in required), "build receipt does not bind source/generated/built identity"
    )
    runtime = read(target["runtime"]["evidence"]["path"])
    return document, target, runtime


def _frozen_policy(plan, deps):
    from performance_effect_evidence import read, policy
    from prepare_case_sets import case_ids_from_collection

    manifest = read_ref(plan.get("manifest"), deps)
    require(
        policy(manifest.get("configuration", {}).get("performance_effect_policy"))["id"] == "confidence_effect_v1",
        "op adapter requires frozen confidence_effect_v1",
    )
    if manifest.get("request"):
        request = manifest["request"]
        from performance_effect_evidence import check_receipt, read, receipt

        check_receipt(request)
        frozen_request = read(request["path"])
        require(
            frozen_request.get("performance_effect_policy")
            == manifest["configuration"].get("performance_effect_policy"),
            "effect policy differs from frozen request",
        )
        deps[request["path"]] = receipt(request["path"])
    soc = plan.get("soc")
    require(soc in manifest["configuration"]["target_socs"], "plan SoC not frozen")
    collection = manifest.get("collections", {}).get(plan.get("collection"))
    require(isinstance(collection, dict), "plan requires frozen collection")
    bind({"path": collection.get("path"), "sha256": collection.get("sha256")}, deps)
    require(
        plan.get("effect_case_id") in case_ids_from_collection(collection), "effect case absent from frozen collection"
    )
    return manifest, soc


def _validate_protocol_devices(plan):
    protocol = plan.get("protocol", {})
    require(
        protocol
        == {
            "profiler": "msprof op",
            "aic_metrics": "PipeTimeline",
            "launch_count": 1,
            "warmup": 5,
            "metric": "Task Duration(us)",
            "target_calls": 2,
            "synchronizations": 2,
            "warmup_time_included": False,
        },
        "single-launch protocol differs from frozen task",
    )
    require(
        type(plan.get("physical_device")) is int
        and plan["physical_device"] >= 0
        and type(plan.get("logical_device")) is int
        and plan["logical_device"] >= 0,
        "physical/logical device required",
    )
    frequency = plan.get("rated_frequency_mhz")
    require(
        type(frequency) in (int, float) and math.isfinite(frequency) and frequency > 0,
        "plan requires frozen positive rated_frequency_mhz",
    )
    require(
        plan.get("samples_per_variant") == 10 and type(plan["samples_per_variant"]) is int,
        "op confirmation requires exactly ten samples per variant",
    )


def _validate_method(plan):
    from performance_effect_evidence import INDEPENDENT_METHOD

    method = plan.get("statistical_method", {})
    require(
        method.get("id") == INDEPENDENT_METHOD
        and method.get("confidence") == 0.95
        and method.get("statistic") == "difference_of_medians"
        and method.get("quantile") == "linear"
        and type(method.get("seed")) is int
        and type(method.get("draws")) is int
        and 1000 <= method["draws"] <= 1000000,
        "independent bootstrap method must be frozen",
    )


def _validate_output_contract(plan, deps):
    snapshot = bind(plan.get("snapshot"), deps)
    output = plan.get("output_contract", {})
    require(
        output.get("dtype") == "bfloat16"
        and isinstance(output.get("shape"), list)
        and output["shape"]
        and all(type(n) is int and n > 0 for n in output["shape"]),
        "exact BF16 raw-output shape required",
    )
    reference = bind(output.get("reference"), deps)
    require(reference.stat().st_size == math.prod(output["shape"]) * 2, "reference BF16 byte extent mismatch")
    require(
        plan.get("precision") == {"status": "strict_pass", "rtol": 0, "atol": 0, "comparison": "raw_bf16_bytes_equal"},
        "original exact precision may not be weakened",
    )
    return snapshot


def _validate_identity(plan, variant, identity, manifest, soc, deps):
    require(
        isinstance(identity.get("kernel_name"), str) and identity["kernel_name"],
        "exact profiler kernel name required",
    )
    require(
        type(identity.get("block_dim")) is int
        and identity["block_dim"] > 0
        and type(identity.get("mix_block_dim")) is int
        and identity["mix_block_dim"] > 0,
        "kernel block geometry required",
    )
    generated = identity.get("generated")
    require(isinstance(generated, list) and generated, "generated-code identity required")
    for item in generated:
        bind(item, deps)
    expected = read_ref(identity.get("execution_identity"), deps)
    if variant == plan["baseline_variant"]:
        original = manifest.get("inputs", {}).get("code")
        if identity.get("source_archive"):
            mapping = read_ref(identity["source_archive"], deps)
            archived = expected.get("source")
            require(
                mapping.get("schema_version") == 1
                and mapping.get("manifest") == plan["manifest"]
                and mapping.get("original_source") == original
                and mapping.get("original_snapshot") == archived,
                "baseline archive mapping must bind frozen manifest/original/snapshot",
            )
            require(
                isinstance(archived, dict)
                and isinstance(original, dict)
                and archived.get("path") != original.get("path")
                and {k: v for k, v in archived.items() if k != "path"}
                == {k: v for k, v in original.items() if k != "path"},
                "baseline archive must preserve original frozen source bytes and relative paths",
            )
        else:
            require(
                expected.get("source") == original,
                "confirmation baseline must be the original frozen source identity",
            )
    check_execution(identity["execution_identity"], expected.get("source"), soc, generated, deps)


def _validate_variant_identities(plan, manifest, soc, deps):
    variants = [plan.get("baseline_variant"), plan.get("candidate_variant")]
    require(
        all(isinstance(v, str) and v for v in variants) and variants[0] != variants[1],
        "distinct baseline/candidate variants required",
    )
    identities = plan.get("identities", {})
    require(set(identities) == set(variants), "variant identity coverage mismatch")
    for variant, identity in identities.items():
        _validate_identity(plan, variant, identity, manifest, soc, deps)
    return variants


def _validate_order(plan, variants):
    order = plan.get("order")
    require(isinstance(order, list) and len(order) == 20, "pre-registered order requires twenty slots")
    seen, ab = {v: [] for v in variants}, 0
    for pair_index in range(10):
        pair = order[2 * pair_index:2 * pair_index + 2]
        require(
            {item.get("variant") for item in pair} == set(variants),
            "each frozen pair must contain baseline and candidate",
        )
        ab += pair[0]["variant"] == variants[0]
        for position, item in enumerate(pair):
            require(
                set(item) == {"slot", "variant", "sample_index"}
                and item["slot"] == 2 * pair_index + position
                and item["sample_index"] == pair_index,
                "slot/sample index differs from frozen pair order",
            )
            seen[item["variant"]].append(item["sample_index"])
    require(ab == 5, "frozen AB/BA order must be balanced five/five")


def validate_plan(plan_path, deps=None):
    from performance_effect_evidence import read, receipt

    deps = {} if deps is None else deps
    plan_path = Path(plan_path).resolve()
    plan = read(plan_path)
    deps[str(plan_path)] = receipt(plan_path)
    require(plan.get("schema_version") == 1 and plan.get("kind") == KIND, "unknown msprof op plan schema/kind")
    manifest, soc = _frozen_policy(plan, deps)
    _validate_protocol_devices(plan)
    _validate_method(plan)
    _validate_output_contract(plan, deps)
    variants = _validate_variant_identities(plan, manifest, soc, deps)
    _validate_order(plan, variants)
    require(
        plan.get("retry_policy") == "record_failed_attempts_then_first_success_no_valid_sample_replacement",
        "explicit failure-only retry policy required",
    )
    return plan


def raw_sample(path, expected, plan):
    from performance_effect_evidence import _field

    with path.open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    require(len(rows) == 1, "OpBasicInfo must contain exactly one complete target row")
    row = rows[0]
    require(
        _field(row, "Op Name") == expected["kernel_name"] and _field(row, "Op Type") == "mix",
        "raw target kernel identity mismatch",
    )
    duration = float(_field(row, "Task Duration(us)"))
    require(math.isfinite(duration) and duration > 0, "raw duration must be finite and positive")
    require(int(_field(row, "Device Id")) == plan["physical_device"], "raw physical device mismatch")
    require(
        int(_field(row, "Block Dim")) == expected["block_dim"]
        and int(_field(row, "Mix Block Dim")) == expected["mix_block_dim"],
        "raw block geometry mismatch",
    )
    current, rated = float(_field(row, "Current Freq")), float(_field(row, "Rated Freq"))
    require(
        math.isfinite(current) and math.isfinite(rated) and current == rated == plan["rated_frequency_mhz"],
        "sample frequency differs from frozen rated frequency",
    )
    require(int(_field(row, "Pid")) > 0, "raw process identity missing")
    return duration, int(_field(row, "Pid"))


def _verify_failed_attempt(attempt, log, expected, plan, deps, is_last):
    require(attempt.get("status") == "failed" and not is_last, "failed attempts must precede the first valid sample")
    failed_captures = list(attempt.get("raw_captures", []))
    require(
        isinstance(attempt.get("raw_captures", []), list),
        "failed raw_captures must be a list of original file references",
    )
    if attempt.get("op_basic_info") and attempt["op_basic_info"] not in failed_captures:
        failed_captures.append(attempt["op_basic_info"])
    for capture in failed_captures:
        failed_raw = bind(capture, deps)
        try:
            raw_sample(failed_raw, expected, plan)
        except (ValueError, KeyError, TypeError):
            pass  # A real timeout may leave missing/zero/incomplete data.
        else:
            require(
                "All task success" not in log,
                "failed attempt contains complete successful timing; cannot discard it",
            )


def _check_raw_capture(attempt, log, expected, plan, deps, raw_paths, profiled_pids):
    """Bind one unambiguous raw capture and confirm it matches the run log."""
    if "raw_captures" in attempt:
        require(
            attempt["raw_captures"] == [attempt.get("op_basic_info")],
            "successful attempt requires one unambiguous raw capture",
        )
    raw_path = bind(attempt.get("op_basic_info"), deps)
    require(str(raw_path) not in raw_paths, "raw capture reused across samples")
    raw_paths.add(str(raw_path))
    value, raw_pid = raw_sample(raw_path, expected, plan)
    require(raw_pid not in profiled_pids, "profiled process reused across independent samples")
    profiled_pids.add(raw_pid)
    require(
        "Warm Up enabled. times:5" in log and "All task success" in log,
        "actual profiler log lacks warmup5/success evidence",
    )
    observed = [float(v) for v in re.findall(r"Task Duration\(us\):\s*([0-9.eE+-]+)", log)]
    require(
        len(observed) == 1 and abs(observed[0] - value) <= 1e-6,
        "run.log duration differs from original OpBasicInfo",
    )
    logged_pids = re.findall(r"\bPid:\s*(\d+)", log)
    require(logged_pids == [str(raw_pid)], "profiler log PID differs from raw timed process")
    return value, raw_pid


def _check_loaded_runtime(attempt, expected, expected_doc, plan, deps, raw_pid):
    """Confirm the loaded execution, device and protocol match the registered variant."""
    _doc, target, runtime = check_execution(
        attempt.get("execution_identity"),
        expected_doc["source"],
        plan["soc"],
        expected["generated"],
        deps,
    )
    require(
        type(runtime.get("pid")) is int and runtime["pid"] == raw_pid,
        "loaded/output runtime PID differs from profiled process",
    )
    normal = expected_doc["targets"][0]
    require(
        {a["sha256"] for a in target["build"]["artifacts"]} == {a["sha256"] for a in normal["build"]["artifacts"]},
        "sample build differs from pre-registered variant",
    )
    require(
        runtime.get("physical_device") == plan["physical_device"]
        and runtime.get("logical_device") == plan["logical_device"]
        and runtime.get("target_soc") == plan["soc"],
        "actual runtime device/SoC identity mismatch",
    )
    require(
        runtime.get("input_snapshot") == plan["snapshot"]
        and runtime.get("target_calls") == 2
        and runtime.get("synchronizations") == 2,
        "runtime inputs or original two-call protocol changed",
    )
    return target


def _check_precision(attempt, plan, case_id, deps, target):
    """Confirm the precision receipt is bound to this execution and its actual output."""
    truth = read_ref(attempt.get("precision"), deps)
    require(
        truth.get("contract") == plan["precision"]
        and truth.get("case_id") == case_id
        and truth.get("input_snapshot") == plan["snapshot"]
        and truth.get("execution_identity") == attempt["execution_identity"],
        "precision not bound to this actual execution",
    )
    output = truth.get("actual_output")
    output_path = bind(output, deps)
    require(output in target["runtime"]["source_artifacts"], "precision output not retained by this runtime")
    require(
        truth.get("dtype") == plan["output_contract"]["dtype"]
        and truth.get("shape") == plan["output_contract"]["shape"],
        "precision output extent mismatch",
    )
    require(
        output_path.read_bytes() == Path(plan["output_contract"]["reference"]["path"]).read_bytes(),
        "actual BF16 output differs from original reference",
    )


def _verify_successful_sample(
    attempt, log, expected, expected_doc, plan, case_id, deps, raw_paths, profiled_pids, is_last
):
    require(attempt.get("status") == "valid" and is_last, "first successful capture cannot be discarded/replaced")
    value, raw_pid = _check_raw_capture(attempt, log, expected, plan, deps, raw_paths, profiled_pids)
    target = _check_loaded_runtime(attempt, expected, expected_doc, plan, deps, raw_pid)
    _check_precision(attempt, plan, case_id, deps, target)
    sources = target["runtime"]["source_artifacts"]
    require(
        attempt["op_basic_info"] in sources and attempt["run_log"] in sources,
        "raw timing files not bound to actual loaded execution",
    )
    return value


def _check_sample_gate(samples):
    for variant in samples:
        values = samples[variant]
        require(
            len(values) == 10 and (max(values) - min(values)) / statistics.median(values) <= 0.10,
            "op median10 sample count/spread gate failed",
        )


def _check_headlines(samples, case_id, baseline_path, candidate_path, baseline_variant, candidate_variant):
    from summarize_performance_effects import load_performance

    for path, variant in ((baseline_path, baseline_variant), (candidate_path, candidate_variant)):
        order, values = load_performance(Path(path))
        require(
            order == [case_id] and abs(values[case_id] - statistics.median(samples[variant])) <= 1e-6,
            "headline differs from actual op median10",
        )


def _validate_op_collection(plan_path, registration_path, collection_path, plan,
                            case_id, baseline_variant, candidate_variant):
    """Bind the frozen op plan to its registration and complete collection."""
    from performance_effect_evidence import read, receipt

    require(
        (plan["effect_case_id"], plan["baseline_variant"], plan["candidate_variant"])
        == (case_id, baseline_variant, candidate_variant),
        "op plan comparison binding mismatch",
    )
    registration = read(registration_path)
    require(receipt(plan_path) in registration.get("artifacts", []), "op plan not registered before capture")
    issued = timestamp(registration["issued_at"])
    collection = read(collection_path)
    require(
        collection.get("schema_version") == 1
        and collection.get("kind") == KIND
        and collection.get("plan") == receipt(plan_path),
        "op collection must bind registered plan",
    )
    rows = collection.get("samples")
    require(isinstance(rows, list) and len(rows) == 20, "op collection requires all twenty samples")
    return rows, issued


def _check_op_command(command):
    """Require the retained command to be the registered msprof-op capture."""
    require(
        isinstance(command, list)
        and len(command) >= 4
        and all(isinstance(x, str) for x in command)
        and Path(command[0]).name == "msprof"
        and command[1] == "op"
        and [v for v in command if v.startswith("--aic-metrics")] == ["--aic-metrics=PipeTimeline"]
        and [v for v in command if v.startswith("--launch-count")] == ["--launch-count=1"],
        "attempt must retain actual msprof op command",
    )


def _check_attempt_receipt(attempt_ref, expected_slot, plan, deps, attempt_paths, chronology):
    """Bind one attempt receipt and advance the chronological cursor."""
    from performance_effect_evidence import read

    attempt_path = bind(attempt_ref, deps)
    require(str(attempt_path) not in attempt_paths, "attempt receipt reused across samples")
    attempt_paths.add(str(attempt_path))
    attempt = read(attempt_path)
    require(
        attempt.get("schema_version") == 1 and all(attempt.get(k) == v for k, v in expected_slot.items()),
        "attempt slot identity mismatch",
    )
    start, end = timestamp(attempt["started_at"]), timestamp(attempt["ended_at"])
    require(
        chronology["issued"] < start and chronology["last_end"] <= start < end,
        "registration/actual attempt chronology invalid",
    )
    chronology["last_end"] = end
    require(
        attempt.get("protocol") == plan["protocol"]
        and attempt.get("physical_device") == plan["physical_device"]
        and attempt.get("logical_device") == plan["logical_device"],
        "attempt protocol/device changed",
    )
    return attempt


def _verify_sample(context, expected_slot, row):
    """Verify one registered sample slot and return its variant and successful duration."""
    require(
        all(row.get(k) == v for k, v in expected_slot.items()), "actual sample order differs from registered order"
    )
    variant = expected_slot["variant"]
    expected = context["plan"]["identities"][variant]
    attempts = row.get("attempts")
    require(isinstance(attempts, list) and attempts, "sample requires actual attempt receipts")
    successful = 0
    value = None
    for index, attempt_ref in enumerate(attempts):
        attempt = _check_attempt_receipt(
            attempt_ref, expected_slot, context["plan"], context["deps"],
            context["attempt_paths"], context["chronology"],
        )
        _check_op_command(attempt.get("command"))
        log_path = bind(attempt.get("run_log"), context["deps"])
        log = log_path.read_text(errors="replace")
        require(type(attempt.get("returncode")) is int, "attempt requires actual returncode")
        if attempt["returncode"] != 0:
            _verify_failed_attempt(
                attempt, log, expected, context["plan"], context["deps"], index == len(attempts) - 1
            )
            continue
        value = _verify_successful_sample(
            attempt, log, expected, context["expected_docs"][variant], context["plan"],
            context["case_id"], context["deps"], context["raw_paths"], context["profiled_pids"],
            index == len(attempts) - 1,
        )
        successful += 1
    require(successful == 1, "sample lacks one complete successful capture")
    return variant, value


def _op_proof_report(plan, paths, case_id, variants, expected_docs, samples, stats, deps):
    """Assemble the frozen msprof-op proof document from verified receipts."""
    from performance_effect_evidence import receipt

    plan_path, registration_path, collection_path, baseline_path, candidate_path = paths
    baseline_variant, candidate_variant = variants
    return {
        "schema_version": 1,
        "kind": KIND,
        "policy_id": "confidence_effect_v1",
        "policy_version": 1,
        "historical_adapter": False,
        "plan": receipt(plan_path),
        "registration": receipt(registration_path),
        "collection": receipt(collection_path),
        "baseline": receipt(baseline_path),
        "candidate": receipt(candidate_path),
        "case_id": case_id,
        "baseline_variant": baseline_variant,
        "candidate_variant": candidate_variant,
        "target_soc": plan["soc"],
        "source_identities": {
            v: {
                "source": expected_docs[v]["source"],
                "generated": plan["identities"][v]["generated"],
                "execution_identity": plan["identities"][v]["execution_identity"],
            }
            for v in samples
        },
        "input_identity": plan["snapshot"],
        "statistics": stats,
        "dependencies": sorted(deps.values(), key=lambda item: item["path"]),
    }


def build_op_proof(
    plan_path,
    registration_path,
    collection_path,
    baseline_path,
    candidate_path,
    case_id,
    baseline_variant,
    candidate_variant,
):
    from performance_effect_evidence import read, receipt, independent_statistics

    deps = {}
    plan = validate_plan(plan_path, deps)
    rows, issued = _validate_op_collection(
        plan_path, registration_path, collection_path, plan, case_id, baseline_variant, candidate_variant
    )
    expected_docs = {v: read(plan["identities"][v]["execution_identity"]["path"]) for v in plan["identities"]}
    samples = {v: [] for v in plan["identities"]}
    context = {
        "plan": plan, "deps": deps, "case_id": case_id, "expected_docs": expected_docs,
        "raw_paths": set(), "profiled_pids": set(), "attempt_paths": set(),
        "chronology": {"issued": issued, "last_end": issued},
    }
    for expected_slot, row in zip(plan["order"], rows):
        variant, value = _verify_sample(context, expected_slot, row)
        samples[variant].append(value)
    _check_sample_gate(samples)
    _check_headlines(samples, case_id, baseline_path, candidate_path, baseline_variant, candidate_variant)
    stats = independent_statistics(samples[baseline_variant], samples[candidate_variant],
                                   plan["statistical_method"])
    for path in (plan_path, registration_path, collection_path, baseline_path, candidate_path):
        item = receipt(path)
        deps[item["path"]] = item
    return _op_proof_report(
        plan, (plan_path, registration_path, collection_path, baseline_path, candidate_path),
        case_id, (baseline_variant, candidate_variant), expected_docs, samples, stats, deps,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument(
        "--register", type=Path, help="create a new pre-capture registration receipt; refuses overwrite"
    )
    args = parser.parse_args()
    try:
        from performance_effect_evidence import receipt

        validate_plan(args.plan)
        if args.register:
            with args.register.open("x") as stream:
                json.dump(
                    {"issued_at": datetime.now(timezone.utc).isoformat(), "artifacts": [receipt(args.plan)]},
                    stream,
                    indent=2,
                )
                stream.write("\n")
        emit(
            json.dumps({"status": "registered" if args.register else "plan_valid", "plan": receipt(args.plan)})
        )
        return 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        emit(json.dumps({"status": "error", "error": str(error)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
