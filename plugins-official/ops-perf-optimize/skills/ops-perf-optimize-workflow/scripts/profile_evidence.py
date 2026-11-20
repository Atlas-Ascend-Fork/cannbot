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

"""Independent profiling receipts and confidence evidence.

Sample semantics and raw evidence are verified by the reporting entry.
Precision is checked once per frozen implementation.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

REPORT_SCRIPTS = Path(__file__).resolve().parents[2] / "ops-profiling-report/scripts"
sys.path.insert(0, str(REPORT_SCRIPTS))
from profile_report import positive
import report_contract

from performance_effect_evidence import (
    INDEPENDENT_METHOD,
    _verified_receipts,
    check_receipt,
    independent_statistics,
    read,
    receipt,
)
from prepare_case_sets import case_ids_from_collection
from validate_execution_identity import validate_document

KIND = report_contract.COMPARISON_KIND
MEDIAN_KIND = "profile_median_v1"


def require(value, message):
    if not value:
        raise ValueError(message)


def timestamp(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(result.tzinfo is not None, "timestamps require a timezone")
    return result


def bind(value, deps):
    require(
        isinstance(value, dict)
        and (
            set(value) == {"path", "sha256"}
            or (set(value) == {"path", "sha256", "kind"} and value["kind"] == "file")
        )
        and Path(value["path"]).is_absolute(),
        "canonical absolute artifact receipt required",
    )
    actual = check_receipt(value)
    deps[actual["path"]] = actual
    return Path(actual["path"])


def document(value, deps):
    return read(bind(value, deps))


def validate_order(order, variants, samples=10):
    require(
        isinstance(order, list) and len(order) == samples * 2,
        "all registered slots required",
    )
    seen = {variant: [] for variant in variants}
    for slot, row in enumerate(order):
        require(
            set(row) == {"slot", "variant", "sample_index"}
            and row["slot"] == slot
            and row["variant"] in seen
            and type(row["sample_index"]) is int,
            "slot order/index differs from registration",
        )
        seen[row["variant"]].append(row["sample_index"])
    require(
        all(sorted(indices) == list(range(samples)) for indices in seen.values()),
        "each variant must cover every registered sample index once",
    )


def execution(identity, soc, deps):
    doc = document(identity["execution_identity"], deps)
    validate_document(
        {"configuration": {"target_socs": [soc]}, "inputs": {"code": doc["source"]}},
        doc,
    )
    # validate_document has already verified these file receipts.
    for target in doc["targets"]:
        build, runtime = target["build"], target["runtime"]
        for item in [
            build["log"],
            *build["artifacts"],
            runtime["evidence"],
            *runtime["source_artifacts"],
            *runtime["loaded_artifacts"],
        ]:
            deps[item["path"]] = item
    generated = identity.get("generated", [])
    for item in generated:
        bind(item, deps)
    runner = identity.get("runner")
    require(
        isinstance(runner, list)
        and runner
        and all(isinstance(x, str) for x in runner)
        and Path(runner[0]).is_absolute(),
        "frozen absolute runner argv required",
    )
    loaded = doc["targets"][0]["runtime"]["loaded_artifacts"]
    launcher = identity.get("launcher")
    if launcher is not None:
        require(
            bind(launcher, deps) == Path(runner[0]).resolve(),
            "launcher path differs from runner",
        )
    else:
        require(
            any(item["path"] == str(Path(runner[0]).resolve()) for item in loaded),
            "launcher receipt required for interpreter or wrapper",
        )
    require(Path(identity.get("cwd", "")).is_absolute(), "frozen runner cwd required")
    return doc


def validate_plan(plan_path, deps=None):
    deps = {} if deps is None else deps
    plan = read(plan_path)
    median = plan.get("kind") == MEDIAN_KIND
    require(
        plan.get("schema_version") == 1
        and (median or report_contract.supports_comparison(plan.get("kind"))),
        "unknown profiling plan",
    )
    count = plan.get("samples_per_variant")
    require(median or not plan.get("reuse"), "sample reuse requires the median policy")
    require(
        type(count) is int and count > 0 and (median or count == 10),
        "independent report protocol differs from registration",
    )
    require(
        type(plan.get("physical_device")) is int
        and plan["physical_device"] >= 0
        and type(plan.get("logical_device")) is int
        and plan["logical_device"] >= 0,
        "physical/logical device identity required",
    )
    frequency = plan.get("frequency_policy", "rated")
    require(
        frequency in ("rated", "record_only") and (median or frequency == "rated"),
        "confidence measurements require rated frequency",
    )
    if frequency == "rated":
        require(
            positive(plan.get("rated_frequency_mhz")),
            "positive rated frequency required",
        )
    manifest = document(plan["manifest"], deps)
    require(
        manifest.get("configuration", {}).get("performance_effect_policy")
        == {"id": "median_v1" if median else "confidence_effect_v1", "version": 1},
        "frozen policy differs from profiling plan",
    )
    require(
        plan["soc"] in manifest["configuration"]["target_socs"],
        "SoC not frozen in manifest",
    )
    if manifest.get("request"):
        request = document(manifest["request"], deps)
        require(
            request.get("performance_effect_policy")
            == manifest["configuration"]["performance_effect_policy"],
            "policy differs from frozen request",
        )
    bind(plan["tool"], deps)
    report_contract.validate_measurement(plan)
    require(
        isinstance(plan.get("environment"), dict)
        and Path(plan["environment"].get("ASCEND_HOME_PATH", "")).is_absolute(),
        "frozen CANN environment required",
    )
    collection = manifest["collections"][plan["collection"]]
    bind({k: collection[k] for k in ["path", "sha256"]}, deps)
    require(
        plan["effect_case_id"] in case_ids_from_collection(collection),
        "case is not frozen",
    )
    # Bind every frozen input file, not just the JSON describing it.
    snapshot = document(plan["snapshot"], deps)
    require(
        snapshot
        and all(isinstance(k, str) and isinstance(v, str) for k, v in snapshot.items()),
        "snapshot must map absolute file paths to SHA256 values",
    )
    for path, digest in snapshot.items():
        bind({"path": path, "sha256": digest}, deps)
    policy = document(plan["precision_policy"], deps)
    require(
        policy.get("basis") == "original_comparator",
        "original precision policy required",
    )
    bind(policy["comparator"], deps)
    variants = [plan.get("baseline_variant"), plan.get("candidate_variant")]
    require(
        all(isinstance(v, str) and v for v in variants)
        and variants[0] != variants[1]
        and set(plan["identities"]) == set(variants),
        "variant identity coverage mismatch",
    )
    docs = {}
    for variant in variants:
        identity = plan["identities"][variant]
        docs[variant] = execution(identity, plan["soc"], deps)
        precision = document(identity["precision"], deps)
        require(
            precision.get("status") in ["pass", "strict_pass"]
            and precision.get("case_id") == plan["effect_case_id"]
            and precision.get("source") == docs[variant]["source"]
            and precision.get("input_snapshot") == plan["snapshot"]
            and precision.get("execution_identity") == identity["execution_identity"]
            and precision.get("policy") == plan["precision_policy"]
            and precision.get("returncode") == 0,
            "precision is not bound to this source/input/runner",
        )
        bind(precision["comparison_log"], deps)
        bind(precision["actual_output"], deps)
    original = manifest["inputs"]["code"]
    baseline = docs[variants[0]]["source"]
    same_git_tree = (
        baseline.get("identity_method")
        == original.get("identity_method")
        == "git-tree-v1"
        and baseline["sha256"] == original["sha256"]
        and baseline.get("git", {}).get("head_commit")
        == original.get("git", {}).get("head_commit")
    )
    if baseline != original and not same_git_tree:
        mapping = document(plan["identities"][variants[0]]["source_archive"], deps)
        require(
            mapping.get("manifest") == plan["manifest"]
            and mapping.get("original_source") == original
            and mapping.get("original_snapshot") == baseline
            and {k: v for k, v in baseline.items() if k != "path"}
            == {k: v for k, v in original.items() if k != "path"},
            "baseline must preserve original frozen source",
        )
    validate_order(plan.get("order"), variants, count)
    method = plan.get("statistical_method", {})
    require(
        median
        or (
            method.get("id") == INDEPENDENT_METHOD
            and method.get("confidence") == 0.95
            and method.get("statistic") == "difference_of_medians"
            and method.get("quantile") == "linear"
            and type(method.get("seed")) is int
            and type(method.get("draws")) is int
            and 1000 <= method["draws"] <= 1000000
        ),
        "frozen independent bootstrap method required",
    )
    require(
        plan.get("retry_policy") == "failed_without_published_report_only",
        "failure-only retry policy required",
    )
    return plan, docs


raw_sample = report_contract.raw_sample


def _headline(path, case_id):
    with Path(path).open(newline="") as stream:
        rows = [r for r in csv.DictReader(stream) if r.get("case_id") == case_id]
    require(len(rows) == 1, "headline requires exactly one matching case")
    return float(rows[0]["total_us"])


@_verified_receipts
def build_profile_proof(
    plan_path,
    registration_path,
    collection_path,
    baseline_path,
    candidate_path,
    case_id,
    baseline_variant,
    candidate_variant,
):
    deps = {}
    plan, docs = validate_plan(plan_path, deps)
    require(
        report_contract.supports_comparison(plan["kind"]),
        "median collection does not produce a confidence proof",
    )
    variants = [baseline_variant, candidate_variant]
    require(
        (case_id, *variants)
        == (
            plan["effect_case_id"],
            plan["baseline_variant"],
            plan["candidate_variant"],
        ),
        "comparison differs from registered plan",
    )
    registration = read(registration_path)
    require(
        receipt(plan_path) in registration.get("artifacts", []),
        "plan not registered before capture",
    )
    cursor = timestamp(registration["issued_at"])
    collection = read(collection_path)
    require(
        collection.get("kind") == plan["kind"]
        and collection.get("schema_version") == 1
        and collection.get("plan") == receipt(plan_path),
        "collection does not bind registered plan",
    )
    rows = collection.get("samples", [])
    require(len(rows) == 20, "all twenty sample slots required")
    samples = {v: [] for v in variants}
    pids, paths = set(), set()
    for expected, row in zip(plan["order"], rows):
        require(
            {k: row.get(k) for k in expected} == expected,
            "collection slot order changed",
        )
        attempts = row.get("attempts", [])
        require(attempts, "sample has no retained attempt")
        success = False
        for position, ref in enumerate(attempts):
            require(ref["path"] not in paths, "attempt reused across slots")
            paths.add(ref["path"])
            attempt = document(ref, deps)
            require(
                attempt.get("schema_version") == 1
                and attempt.get("protocol") == plan["protocol"]
                and {k: attempt.get(k) for k in expected} == expected
                and attempt.get("physical_device") == plan["physical_device"]
                and attempt.get("logical_device") == plan["logical_device"],
                "attempt identity/protocol mismatch",
            )
            start, end = (
                timestamp(attempt["started_at"]),
                timestamp(attempt["ended_at"]),
            )
            require(
                cursor < start <= end,
                "attempt must follow registration and preceding capture",
            )
            cursor = end
            report_contract.check_command(
                attempt["command"], plan["identities"][row["variant"]], plan
            )
            require(
                attempt["command"][0] == plan["tool"]["path"]
                and attempt.get("environment") == plan["environment"],
                "tool or environment changed",
            )
            log = bind(attempt["run_log"], deps).read_text(errors="replace")
            if attempt.get("status") == "failed":
                report_contract.validate_failure(attempt, log, plan)
                require(
                    type(attempt.get("returncode")) is int,
                    "retain actual wrapper exit code, including zero",
                )
                continue
            require(
                position == len(attempts) - 1
                and not success
                and attempt.get("status") == "valid"
                and attempt.get("returncode") == 0,
                "only final first valid attempt allowed",
            )
            archive = bind(attempt["archive"], deps)
            import_log = bind(attempt["import_log"], deps).read_text(errors="replace")
            summary = bind(attempt["summary"], deps)
            if plan.get("protocol", {}).get("device_contract") == "runtime_device_v1":
                bind(attempt["target_process"], deps)
                bind(attempt["device_binding_file"], deps)
                for item in read(archive)["files"]:
                    bind(item, deps)
            report_contract.validate_publication(
                attempt, archive, summary, log, import_log, plan
            )
            # The report belongs to one independent process, even if it contains multiple replays.
            require(
                str(archive) not in paths and str(summary) not in paths,
                "capture evidence reused",
            )
            paths.update([str(archive), str(summary)])
            value, pid = raw_sample(summary, plan["identities"][row["variant"]], plan)
            require(
                pid not in pids, "repeated process/replay is not an independent capture"
            )
            pids.add(pid)
            samples[row["variant"]].append(value)
            success = True
        require(success, "slot has no valid capture")
    for variant, path in zip(variants, [baseline_path, candidate_path]):
        values = samples[variant]
        median = statistics.median(values)
        require(
            len(values) == 10 and (max(values) - min(values)) / median <= 0.10,
            "independent samples fail coverage or spread gate",
        )
        require(
            math.isclose(_headline(path, case_id), median, rel_tol=1e-9, abs_tol=1e-6),
            "headline does not equal all ten verified sample values",
        )
    for path in [
        plan_path,
        registration_path,
        collection_path,
        baseline_path,
        candidate_path,
    ]:
        item = receipt(path)
        deps[item["path"]] = item
    # Include execution files in the proof's final dependency recheck.
    for item in deps.values():
        check_receipt(item)
    return {
        "schema_version": 1,
        "kind": plan["kind"],
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
        "input_identity": plan["snapshot"],
        "source_identities": {
            v: {
                "source": docs[v]["source"],
                "generated": plan["identities"][v].get("generated", []),
                "execution_identity": plan["identities"][v]["execution_identity"],
            }
            for v in variants
        },
        "statistics": independent_statistics(
            samples[baseline_variant],
            samples[candidate_variant],
            plan["statistical_method"],
        ),
        "dependencies": sorted(deps.values(), key=lambda x: x["path"]),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument(
        "--register", type=Path, help="write a new immutable pre-capture registration"
    )
    args = parser.parse_args()
    try:
        validate_plan(args.plan)
        if args.register:
            args.register.parent.mkdir(parents=True, exist_ok=True)
            with args.register.open("x") as stream:
                json.dump(
                    {
                        "issued_at": datetime.now(timezone.utc).isoformat(),
                        "artifacts": [receipt(args.plan)],
                    },
                    stream,
                    indent=2,
                )
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(
            json.dumps({"status": "invalid", "reason": str(error)}, ensure_ascii=False)
        )
        return 2
    print(json.dumps({"status": "valid", "plan": str(args.plan.resolve())}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
