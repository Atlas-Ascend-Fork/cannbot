#!/usr/bin/env python3
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
"""Read-only paired-effect proof builder and verifier (schema 1).

The proof binds a pre-result plan, full canonical10 receipts and headline CSVs.
It never trusts a reported interval. Historical NumPy experiments retain their
original RNG and quantile implementation; future plans can use stdlib bootstrap.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import random
import re
import statistics
from collections import Counter
from contextvars import ContextVar
from datetime import datetime, timedelta
from functools import wraps
from itertools import permutations
from pathlib import Path

POLICIES = {"legacy_jitter_v1": 1, "confidence_effect_v1": 1}
METHODS = {"python_mt19937_percentile_median_v1", "numpy_pcg64_percentile_median_v1"}
INDEPENDENT_METHOD = "python_mt19937_independent_medians_v1"
HISTORICAL_CI = (
    "paired nonparametric percentile bootstrap median difference, numpy default_rng "
    "seed2026,100000 draws,linear 2.5/97.5 percentiles"
)
SHARED_CANDIDATE_KIND = "shared_candidate_paired_v1"


def policy(value=None, *, default="legacy_jitter_v1"):
    value = value or {"id": default, "version": 1}
    if isinstance(value, str):
        value = {"id": value, "version": 1}
    if (
        not isinstance(value, dict)
        or type(value.get("version")) is not int
        or POLICIES.get(value.get("id")) != value.get("version")
    ):
        raise ValueError(f"unknown performance effect policy: {value}")
    return {"id": value["id"], "version": value["version"]}


_RECEIPT_SNAPSHOT = ContextVar("effect_receipt_snapshot", default=None)


def _receipt_uncached(path):
    path = Path(path).resolve()
    if not path.is_file():
        raise ValueError(f"missing effect dependency: {path}")
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return {"path": str(path), "sha256": h.hexdigest()}


def receipt(path):
    path = str(Path(path).resolve())
    snapshot = _RECEIPT_SNAPSHOT.get()
    if snapshot is None:
        return _receipt_uncached(path)
    if path not in snapshot:
        snapshot[path] = _receipt_uncached(path)
    return dict(snapshot[path])


def _verified_receipts(function):
    """Hash each dependency once, then fully rehash it before accepting a result."""

    @wraps(function)
    def wrapped(*args, **kwargs):
        if _RECEIPT_SNAPSHOT.get() is not None:
            return function(*args, **kwargs)
        snapshot = {}
        token = _RECEIPT_SNAPSHOT.set(snapshot)
        try:
            result = function(*args, **kwargs)
            for path, expected in snapshot.items():
                if _receipt_uncached(path) != expected:
                    raise ValueError(f"effect dependency changed during verification: {path}")
            return result
        finally:
            _RECEIPT_SNAPSHOT.reset(token)

    return wrapped


def check_receipt(value):
    actual = receipt(value["path"])
    if actual["sha256"] != value.get("sha256"):
        raise ValueError(f"effect dependency changed: {value['path']}")
    return actual


def read(path):
    value = json.loads(Path(path).read_text())
    if not isinstance(value, dict):
        raise ValueError("effect evidence JSON must be an object")
    return value


def quantile(values, q):
    position = (len(values) - 1) * q
    lo = int(position)
    hi = min(lo + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (position - lo)


def compute_statistics(differences, method):
    if method.get("id") not in METHODS or method.get("statistic") != "median" or method.get("quantile") != "linear":
        raise ValueError("unknown paired statistical method/version")
    if method.get("confidence") != 0.95 or not isinstance(method.get("seed"), int):
        raise ValueError("paired method requires frozen 95% confidence and integer seed")
    draws = method.get("draws")
    if not isinstance(draws, int) or not 1000 <= draws <= 1000000:
        raise ValueError("bootstrap draws must be frozen in [1000,1000000]")
    if method["id"] == "numpy_pcg64_percentile_median_v1":
        import numpy as np

        # Do not replace this with Python random: the historical algorithm is frozen.
        rng = np.random.default_rng(method["seed"])
        samples = rng.choice(np.asarray(differences), size=(draws, len(differences)), replace=True)
        low, high = map(float, np.quantile(np.median(samples, axis=1), [0.025, 0.975], method="linear"))
    else:
        rng = random.Random(method["seed"])
        medians = sorted(statistics.median(rng.choices(differences, k=len(differences))) for _ in range(draws))
        low, high = quantile(medians, 0.025), quantile(medians, 0.975)
    wins = sum(d < 0 for d in differences)
    losses = sum(d > 0 for d in differences)
    n = wins + losses
    p = min(1.0, 2 * sum(math.comb(n, k) for k in range(min(wins, losses) + 1)) / 2**n) if n else 1.0
    return {
        "method": method,
        "paired_estimate_us": statistics.median(differences),
        "paired_ci_us": [low, high],
        "round_deltas_us": differences,
        "wins": wins,
        "losses": losses,
        "ties": len(differences) - n,
        "exact_sign_two_sided_p": p,
    }


def _norm_header(value):
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _field(row, key):
    for name, value in row.items():
        if _norm_header(name) == _norm_header(key):
            return value.strip()
    raise ValueError(f"raw op summary missing {key}")


def shared_candidate_rounds(plan):
    """Validate all three executions, including the other baseline in each contrast."""
    baselines = plan.get("baseline_variants")
    candidate = plan.get("candidate_variant")
    if baselines != ["original", "current"] or candidate != "candidate":
        raise ValueError("shared candidate requires explicit original/current/candidate roles")
    rounds = plan.get("round_count")
    if type(rounds) is not int or rounds < 6 or rounds % 6:
        raise ValueError("shared candidate rounds must contain complete six-permutation blocks")
    rows = plan.get("cases", [])
    if len(rows) != 3 * rounds or len({r.get("case_id") for r in rows}) != len(rows):
        raise ValueError("shared candidate missing/duplicate execution coverage")
    variants = baselines + [candidate]
    groups = []
    for i in range(rounds):
        group = rows[3 * i:3 * i + 3]
        if {r.get("variant") for r in group} != set(variants) or any(
            type(r.get("round")) is not int
            or r["round"] != i
            or type(r.get("position")) is not int
            or r["position"] != j
            for j, r in enumerate(group)
        ):
            raise ValueError("shared candidate round order/coverage mismatch")
        groups.append(group)
    counts = Counter(tuple(r["variant"] for r in group) for group in groups)
    if counts != Counter({order: rounds // 6 for order in permutations(variants)}):
        raise ValueError("shared candidate requires balanced complete permutations")
    return groups


def _add_dependency(dependencies, path):
    item = receipt(path)
    dependencies[item["path"]] = item
    return Path(item["path"])


def _freeze_dependency(dependencies, item):
    check_receipt(item)
    return _add_dependency(dependencies, item["path"])


def _walk_nested(dependencies, value):
    if isinstance(value, dict):
        if isinstance(value.get("path"), str) and value.get("sha256"):
            if Path(value["path"]).is_dir() and value.get("identity_method") == "source-tree-v1":
                pass  # Full source tree is independently checked below.
            else:
                _freeze_dependency(dependencies, value)
        for child in value.values():
            _walk_nested(dependencies, child)
    elif isinstance(value, list):
        for child in value:
            _walk_nested(dependencies, child)


def _check_collection_status(c):
    if c.get("status") != "complete" or c.get("samples_per_case") != 10 or c.get("warmup_time_included") is not False:
        raise ValueError("invalid canonical10 collection")


def _freeze_collection_files(c, dependencies):
    for key in ("cases_csv", "runner_file", "identity_manifest"):
        if key in c:
            _freeze_dependency(dependencies, {"path": c[key], "sha256": c.get(key + "_sha256")})


def _merge_multi_session(c, sessions, execution, dependencies):
    if len(sessions) <= 1:
        return execution
    executions = [read(_add_dependency(dependencies, entry["execution_manifest"])) for entry in sessions]
    if any(doc.get("samples_per_case") != 10 or doc.get("warmup") != executions[0].get("warmup") for doc in executions):
        raise ValueError("multi-session canonical protocol is asymmetric")
    if any(
        entry.get("case_ids") != [run["case_id"] for run in doc["case_runs"]]
        for entry, doc in zip(sessions, executions)
    ):
        raise ValueError("multi-session case coverage/order mismatch")
    return {
        "samples_per_case": 10,
        "warmup": executions[0]["warmup"],
        "case_runs": [run for doc in executions for run in doc["case_runs"]],
    }


def _expected_label(row, label, plan, shared, shared_groups, rows):
    return {
        "case_id": row["case_id"],
        "round_id": label.get("round_id"),
        "order": (
            [r["variant"] for r in shared_groups[row["round"]]]
            if shared
            else "AB" if rows[2 * row["round"]]["variant"] == plan["baseline_variant"] else "BA"
        ),
        "position": row["position"],
        "variant": row["variant"],
        "input_sha256": plan["snapshot"]["sha256"],
    }


def _check_topology_row(index, row, label, run, round_labels, plan, shared, shared_groups, rows, execution):
    if label.get("round_id") not in round_labels:
        round_labels.append(label.get("round_id"))
    expected = _expected_label(row, label, plan, shared, shared_groups, rows)
    confirmation = {k: v for k, v in expected.items() if k != "case_id"}
    if (
        label != expected
        or round_labels.index(label["round_id"]) != row["round"]
        or run.get("case_id") != row["case_id"]
    ):
        raise ValueError("paired topology labels differ from effect plan order/input")
    if (
        run.get("confirmation") != confirmation
        or execution["case_runs"][index].get("confirmation") != confirmation
    ):
        raise ValueError("paired topology labels differ from effect plan order/input")


def _verify_topology(plan, c, rows, execution, shared, shared_groups, effect_plan, paired, dependencies):
    if paired:
        topology = read(_add_dependency(dependencies, paired["plan"]["path"]))
        _freeze_dependency(dependencies, paired["plan"])
        declaration = paired.get("declaration", {})
        if (
            not effect_plan
            or declaration.get("effect_plan") != effect_plan
            or topology.get("paired_confirmation") != declaration
        ):
            raise ValueError("paired topology must bind the registered effect_plan receipt")
        _freeze_dependency(dependencies, declaration["effect_plan"])
        if declaration.get("round_count") != plan.get("round_count") or declaration.get(
            "statistical_method"
        ) != plan.get("statistical_method"):
            raise ValueError("topology statistical declaration differs from frozen effect plan")
        if shared and any(
            declaration.get(k) != plan.get(k) for k in ("kind", "baseline_variants", "candidate_variant")
        ):
            raise ValueError("shared candidate topology role binding mismatch")
        _check_topology_labels(plan, rows, execution, shared, shared_groups, paired, topology, dependencies)


def _check_topology_labels(plan, rows, execution, shared, shared_groups, paired, topology, dependencies):
    labels = paired.get("case_labels", [])
    runs = topology.get("case_runs", [])
    if len(labels) != len(rows) or len(runs) != len(rows):
        raise ValueError("paired topology/effect plan label coverage mismatch")
    round_labels = []
    for index, (row, label, run) in enumerate(zip(rows, labels, runs)):
        _check_topology_row(index, row, label, run, round_labels, plan, shared, shared_groups, rows, execution)


def _check_order_and_validation(plan, c, order, validation, execution):
    if (
        len(order) != len(set(order))
        or c["case_ids"] != order
        or [run["case_id"] for run in execution["case_runs"]] != order
    ):
        raise ValueError("paired case order/coverage differs from frozen plan")
    if c.get("case_count_expected") != len(order) or c.get("case_count_collected") != len(order):
        raise ValueError("paired collection case count mismatch")
    if (
        execution.get("samples_per_case") != 10
        or validation.get("status") != "pass"
        or validation.get("case_order", order) != order
    ):
        raise ValueError("canonical10 validation/order mismatch")
    warmup_keys = ("mode", "logical_op", "implementation", "tensor_bytes", "tensor_allocation")
    if any(
        c.get("warmup", {}).get(k) != execution.get("warmup", {}).get(k)
        or validation.get("warmup", {}).get(k) != c.get("warmup", {}).get(k)
        for k in warmup_keys
    ):
        raise ValueError("asymmetric warmup protocol")
    if validation.get("warmup_time_included") is not False or validation.get("preparation_time_included") is not False:
        raise ValueError("warmup/preparation included in timing")


def _expected_launches(execution):
    expected = []
    for run in execution["case_runs"]:
        warm, target = run["warmup_kernel_sequence"], run["target_kernel_sequence"]
        if not warm or not target or run["iteration_kernel_sequence"] != warm + target:
            raise ValueError("invalid ordered launch topology")
        for j, kernel in enumerate(run.get("preparation_kernel_sequence", [])):
            expected.append((run["case_id"], -1, j, "preparation", kernel))
        for sample in range(10):
            for j, kernel in enumerate(warm + target):
                expected.append((run["case_id"], sample, j, "warmup" if j < len(warm) else "target", kernel))
    names = {entry[-1] for entry in expected}
    return expected, names


def _read_launch_rows(dependencies, raw_path, names):
    session_rows = []
    with _add_dependency(dependencies, raw_path).open(newline="", encoding="utf-8-sig") as stream:
        for line, row in enumerate(csv.DictReader(stream), 2):
            name = _field(row, "Op Name")
            if name in names:
                session_rows.append(
                    {
                        "source_row": line,
                        "kernel": name,
                        "duration_us": float(_field(row, "Task Duration(us)")),
                        "task_start_us": float(_field(row, "Task Start Time(us)")),
                        "block_num": _field(row, "Block Num"),
                    }
                )
    session_rows.sort(key=lambda row: (row["task_start_us"], row["source_row"]))
    return session_rows


def _map_raw_launches(plan, c, sessions, order, expected, names, dependencies, validation):
    raw = []
    raw_paths = [entry["op_summary"] for entry in sessions] if len(sessions) > 1 else [c["op_summary"]]
    for raw_path in raw_paths:
        raw.extend(_read_launch_rows(dependencies, raw_path, names))
    if len(raw) != len(expected) or [r["kernel"] for r in raw] != [e[-1] for e in expected]:
        raise ValueError("raw ordered launch mapping incomplete or mismatched")
    mapped = []
    samples = {case: [0.0] * 10 for case in order}
    for r, (case, sample, index, role, _) in zip(raw, expected):
        if not math.isfinite(r["duration_us"]) or r["duration_us"] <= 0:
            raise ValueError("invalid raw duration")
        mapped.append({"case_id": case, "sample_index": sample, "sequence_index": index, "role": role, **r})
        if role == "target":
            samples[case][sample] += r["duration_us"]
    if validation.get("mapped_launches") != mapped or any(
        validation.get(k) != len(mapped)
        for k in ("expected_relevant_launches", "parsed_relevant_launches", "mapped_relevant_launches")
    ):
        raise ValueError("validation mapping differs from raw ordered launches")
    if plan.get("expected_relevant_launches") != len(mapped):
        raise ValueError("frozen launch budget mismatch")
    return samples


def _check_performance_csv(c, order, samples, dependencies):
    with _add_dependency(dependencies, c["performance_csv"]).open(newline="") as stream:
        perf = list(csv.DictReader(stream))
    if [r["case_id"] for r in perf] != order:
        raise ValueError("performance sample order mismatch")
    medians = {}
    for row in perf:
        values = samples[row["case_id"]]
        if json.loads(row["sample_total_us"]) != [round(v, 6) for v in values] or int(row["sample_count"]) != 10:
            raise ValueError("performance samples differ from original mapped launches")
        median = statistics.median(values)
        if abs(float(row["total_us"]) - median) > 1e-6 or (max(values) - min(values)) / median > 0.10:
            raise ValueError("canonical10 median/spread gate failed")
        medians[row["case_id"]] = median
    return medians


def _check_device(c, plan, root, dependencies):
    device = read(_add_dependency(dependencies, root / "device.json"))
    if (
        device.get("soc") != plan["soc"]
        or device.get("physical") != plan["physical_device"]
        or c["identity"].get("device_id") != plan["physical_device"]
    ):
        raise ValueError("paired device/SoC identity mismatch")


def _original_precision_contract(plan):
    return plan.get(
        "original_precision_contract",
        {"status": "strict_pass", "rtol": 0, "atol": 0} if plan.get("stats", {}).get("ci") == HISTORICAL_CI else None,
    )


def _precision_keys_ok(precision, order):
    checks = precision.get("sample_checks", [])
    keys = [(r.get("case_id"), r.get("sample_index")) for r in checks]
    covered = set()
    for case in order:
        for i in range(10):
            covered.add((case, i))
    return len(keys) == len(set(keys)) and set(keys) == covered


def _check_precision(plan, c, order, root, dependencies):
    precision = read(_add_dependency(dependencies, root / "precision-results.json"))
    checks = precision.get("sample_checks", [])
    precision_contract = _original_precision_contract(plan)
    if not isinstance(precision_contract, dict) or not all(k in precision_contract for k in ("status", "rtol", "atol")):
        raise ValueError("new effect plan requires original_precision_contract")
    if precision.get("status") != precision_contract["status"] or not _precision_keys_ok(precision, order):
        raise ValueError("full original precision coverage failed")
    if any(
        r.get("status") != "PASS"
        or r.get("rtol") != precision_contract["rtol"]
        or r.get("atol") != precision_contract["atol"]
        for r in checks
    ):
        raise ValueError("original precision weakened or failed")
    if not precision.get("unchanged_input_raw_bytes") or not precision.get("all_retained_outputs_rechecked"):
        raise ValueError("input/output truth evidence missing")
    _check_prime_precision(plan, precision, order, dependencies)
    _walk_nested(dependencies, precision)


def _check_prime_precision(plan, precision, order, dependencies):
    prime_checks = precision.get("prime_checks", [])
    precision_contract = _original_precision_contract(plan)
    if (
        len(prime_checks) != len(order)
        or {r.get("case_id") for r in prime_checks} != set(order)
        or any(
            r.get("status") != "PASS"
            or r.get("rtol") != precision_contract["rtol"]
            or r.get("atol") != precision_contract["atol"]
            for r in prime_checks
        )
    ):
        raise ValueError("declared prime original precision coverage failed")
    for result in precision.get("sample_checks", []) + prime_checks:
        artifact = result.get("artifact")
        if not isinstance(artifact, dict) or not artifact.get("path") or not artifact.get("sha256"):
            raise ValueError("original precision requires retained output artifact receipt")
        _freeze_dependency(dependencies, artifact)


def _check_frequency(plan, order, root, dependencies):
    for case in order:
        for sample in (0, 9):
            f = read(_add_dependency(dependencies, root / "frequency" / f"{case}-{sample}.json"))
            if f.get("case_id") != case or f.get("sample_index") != sample:
                raise ValueError("active performance frequency gate failed")
            if f.get("rated", 0) <= 0 or f.get("activity") != f.get("rated"):
                raise ValueError("active performance frequency gate failed")


def _check_inputs(plan, c, root, dependencies):
    inputs = read(_add_dependency(dependencies, root / "inputs.json"))
    _freeze_dependency(dependencies, plan["snapshot"])
    if inputs.get("snapshot") != plan["snapshot"] or c["identity"].get("snapshot") != plan["snapshot"]:
        raise ValueError("paired immutable input identity mismatch")


def _read_identities(plan, root, dependencies):
    compile_identity = read(_add_dependency(dependencies, root / "compile-identity.json"))
    expected_identity = read(_add_dependency(dependencies, plan["expected_identity"]["path"]))
    _freeze_dependency(dependencies, plan["expected_identity"])
    return compile_identity, expected_identity


def _check_shared_runs(plan, rows, compile_identity, expected_identity, c, dependencies):
    variant_names = set(plan["baseline_variants"] + [plan["candidate_variant"]])
    variant_sources = (
        compile_identity.get("variants", {}),
        expected_identity,
        c["identity"].get("variant_sources", {}),
    )
    if any(set(values) != variant_names for values in variant_sources):
        raise ValueError("shared candidate normal identity coverage mismatch")
    actual_runs = compile_identity.get("case_runs", [])
    if len(actual_runs) != len(rows):
        raise ValueError("shared candidate requires actual per-execution identity receipts")
    for row, actual in zip(rows, actual_runs):
        ref = expected_identity[row["variant"]]
        if (
            actual.get("case_id") != row["case_id"]
            or actual.get("variant") != row["variant"]
            or actual.get("source") != ref["source"]
        ):
            raise ValueError("shared candidate executed source variant mismatch")
        for kind in ("generated", "built", "live"):
            if actual.get(kind, {}).get("sha256") != ref["reference_artifacts"][kind]["sha256"]:
                raise ValueError("shared candidate execution normal/build/live identity mismatch")
        if not isinstance(actual.get("runtime_evidence"), dict):
            raise ValueError("shared candidate missing actual runtime evidence")
        _walk_nested(dependencies, actual)


def _walk_source_tree(source, dependencies):
    digest, file_names = hashlib.sha256(), []
    source_root = Path(source["path"])
    for directory, dirs, names in os.walk(source_root):
        dirs[:] = sorted(
            d for d in dirs if d not in {".git", ".pytest_cache", "__pycache__", "build", "dist", "output", "outputs"}
        )
        for name in sorted(names):
            file = Path(directory) / name
            if file.suffix.lower() not in {
                ".c",
                ".cc",
                ".cpp",
                ".h",
                ".hh",
                ".hpp",
                ".py",
                ".sh",
                ".cmake",
                ".json",
                ".yaml",
                ".yml",
                ".toml",
            } and name not in {"CMakeLists.txt", "Makefile"}:
                continue
            current = receipt(file)
            digest.update(file.relative_to(source_root).as_posix().encode())
            digest.update(b"\0")
            digest.update(current["sha256"].encode())
            digest.update(b"\0")
            file_names.append(current["path"])
    if (
        digest.hexdigest() != source["sha256"]
        or file_names != [f["path"] for f in source["files"]]
        or len(file_names) != source["file_count"]
    ):
        raise ValueError("complete source tree identity changed")


def _check_variant_identity(plan, c, variant, v, expected_identity, dependencies):
    ref = expected_identity.get(variant)
    if not ref or v.get("source") != ref["source"] or c["identity"]["variant_sources"].get(variant) != ref:
        raise ValueError("paired source/normal identity mismatch")
    source = ref["source"]
    if source.get("identity_method") != "source-tree-v1":
        raise ValueError("unknown source identity method")
    _walk_source_tree(source, dependencies)
    _walk_nested(dependencies, ref)
    _walk_nested(dependencies, v)
    for kind in ("generated", "built", "live"):
        if v[kind]["sha256"] != ref["reference_artifacts"][kind]["sha256"]:
            raise ValueError("normal generated/build/runtime identity mismatch")
    if v["built"]["sha256"] != v["live"]["sha256"]:
        raise ValueError("built/runtime payload identity mismatch")


@_verified_receipts
def verify_collection(plan, collection_path, dependencies, effect_plan=None):
    """Rebuild ordered target samples from raw launches, then verify every receipt."""

    c = read(_add_dependency(dependencies, collection_path))
    _check_collection_status(c)
    sessions = c.get("sessions", [])
    if not sessions or (plan.get("kind") != "canonical10_independent" and len(sessions) != 1):
        raise ValueError("paired v1 requires one same-device session")
    _freeze_collection_files(c, dependencies)
    validation = read(_add_dependency(dependencies, c["validation_json"]))
    execution = read(_add_dependency(dependencies, c["execution_manifest"]))
    execution = _merge_multi_session(c, sessions, execution, dependencies)
    rows = plan["cases"]
    order = [row["case_id"] for row in rows]
    shared = plan.get("kind") == SHARED_CANDIDATE_KIND
    shared_groups = shared_candidate_rounds(plan) if shared else None
    paired = c.get("paired_confirmation")
    if shared and not paired:
        raise ValueError("shared candidate requires registered collector topology")
    _verify_topology(plan, c, rows, execution, shared, shared_groups, effect_plan, paired, dependencies)
    _check_order_and_validation(plan, c, order, validation, execution)
    expected, names = _expected_launches(execution)
    samples = _map_raw_launches(plan, c, sessions, order, expected, names, dependencies, validation)
    medians = _check_performance_csv(c, order, samples, dependencies)
    root = Path(c["performance_csv"]).parent / "evidence"
    _check_device(c, plan, root, dependencies)
    _check_precision(plan, c, order, root, dependencies)
    _check_frequency(plan, order, root, dependencies)
    _check_inputs(plan, c, root, dependencies)
    compile_identity, expected_identity = _read_identities(plan, root, dependencies)
    if shared:
        _check_shared_runs(plan, rows, compile_identity, expected_identity, c, dependencies)
    for variant, v in compile_identity["variants"].items():
        _check_variant_identity(plan, c, variant, v, expected_identity, dependencies)
    _walk_nested(dependencies, c["identity"])
    return medians, expected_identity


@_verified_receipts
def verify_proof(proof_path, baseline_path, candidate_path):
    proof = read(proof_path)
    if (
        proof.get("schema_version") != 1
        or proof.get("policy_id") != "confidence_effect_v1"
        or proof.get("policy_version") != 1
    ):
        raise ValueError("unknown paired proof schema/policy")
    for item in proof["dependencies"]:
        check_receipt(item)
    if proof.get("baseline") != receipt(baseline_path) or proof.get("candidate") != receipt(candidate_path):
        raise ValueError("proof belongs to a different comparison/baseline")
    result = build_proof(
        Path(proof["plan"]["path"]),
        Path(proof["registration"]["path"]),
        Path(proof["collection"]["path"]),
        Path(baseline_path),
        Path(candidate_path),
        proof["case_id"],
        proof["baseline_variant"],
        proof["candidate_variant"],
    )
    if proof != result:
        raise ValueError("paired proof differs from recomputed evidence")
    return result


def _parse_iso(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _session_chronology_ok(registration, session, deps):
    attempts = session.get("attempts", [])
    if not attempts:
        raise ValueError("ambiguous registration chronology requires bound capture attempts")
    registered = _parse_iso(registration["issued_at"])
    valid = []
    for attempt in attempts:
        directory = Path(attempt["dir"]).resolve()
        item = receipt(directory / "attempt.json")
        deps[item["path"]] = item
        actual = read(item["path"])
        if actual != attempt or registered >= _parse_iso(actual["started_at"]):
            raise ValueError("registration must strictly precede every actual capture attempt")
        for name in ("execution_manifest", "op_summary"):
            value = actual.get(name)
            if value is not None and not Path(value).resolve().is_relative_to(directory):
                raise ValueError("capture chronology artifact outside actual attempt")
        if actual.get("data_status") == "valid" and actual.get("returncode") == 0:
            valid.append(actual)
    if len(valid) != 1 or any(
        Path(session[name]).resolve() != Path(valid[0][name]).resolve() for name in ("execution_manifest", "op_summary")
    ):
        raise ValueError("capture chronology not bound to selected successful execution")
    for name in ("execution_manifest", "op_summary"):
        item = receipt(valid[0][name])
        if item not in [{"path": f.get("path"), "sha256": f.get("sha256")} for f in valid[0].get("files", [])]:
            raise ValueError("capture chronology selected artifact receipt mismatch")
        deps[item["path"]] = item


def registration_precedes_capture(registration, collection, deps, *, label="plan"):
    """Resolve only a whole-second collection timestamp ambiguity with bound attempts."""
    registered, started = _parse_iso(registration["issued_at"]), _parse_iso(collection["started_at"])
    if registered < started:
        return
    text = collection["started_at"]
    if not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})", text
    ) or registered >= started + timedelta(seconds=1):
        raise ValueError(f"{label} registration must precede collection")
    sessions = collection.get("sessions", [])
    if not sessions:
        raise ValueError("ambiguous registration chronology requires bound capture attempts")
    for session in sessions:
        _session_chronology_ok(registration, session, deps)


def _execution_signature(document):
    return (
        document["source"]["sha256"],
        sorted(
            (
                t["target_soc"],
                sorted(r["sha256"] for r in t["build"]["artifacts"]),
                sorted(r["sha256"] for r in t["runtime"]["loaded_artifacts"]),
            )
            for t in document["targets"]
        ),
    )


def _registered_plan_check(plan_path, registration, deps):
    """Verify the plan receipt was pre-registered, then resolve registration chronology."""
    frozen_plan = receipt(plan_path)
    if frozen_plan not in [
        {"path": r.get("path"), "sha256": r.get("sha256")} for r in registration.get("artifacts", [])
    ]:
        raise ValueError("plan not registered before result")
    return frozen_plan


def _frozen_method(plan, historical, baseline_variant, candidate_variant, case_id):
    if historical:
        method = {
            "id": "numpy_pcg64_percentile_median_v1",
            "confidence": 0.95,
            "statistic": "median",
            "quantile": "linear",
            "seed": 2026,
            "draws": 100000,
        }
        if (
            plan["stats"].get("primary")
            != "median of 10 paired round differences baseline median10 - early median10; positive means early faster"
            or baseline_variant != "baseline"
            or candidate_variant != "early"
        ):
            raise ValueError("historical plan comparison/primary method mismatch")
        return method
    method = plan.get("statistical_method", {})
    shared = plan.get("kind") == SHARED_CANDIDATE_KIND
    baseline_bound = (
        baseline_variant in plan.get("baseline_variants", [])
        if shared
        else plan.get("baseline_variant") == baseline_variant
    )
    if (
        plan.get("effect_case_id") != case_id
        or not baseline_bound
        or plan.get("candidate_variant") != candidate_variant
    ):
        raise ValueError("paired plan case/comparison binding mismatch")
    return method


def _collect_pairs(plan, rows, baseline_variant, candidate_variant):
    pairs = []
    ab = ba = 0
    if plan.get("kind") == SHARED_CANDIDATE_KIND:
        groups = shared_candidate_rounds(plan)
        for group in groups:
            pair = [r for r in group if r["variant"] in (baseline_variant, candidate_variant)]
            ab += pair[0]["variant"] == baseline_variant
            ba += pair[0]["variant"] == candidate_variant
            pairs.append({r["variant"]: r["case_id"] for r in pair})
        return pairs, ab, ba
    if len(rows) != 2 * plan["round_count"]:
        raise ValueError("missing or duplicate paired rounds")
    for i in range(plan["round_count"]):
        pair = rows[2 * i:2 * i + 2]
        if {r.get("variant") for r in pair} != {baseline_variant, candidate_variant} or any(
            r.get("round") != i or r.get("position") != j for j, r in enumerate(pair)
        ):
            raise ValueError("paired round order/coverage mismatch")
        ab += pair[0]["variant"] == baseline_variant
        ba += pair[0]["variant"] == candidate_variant
        pairs.append({r["variant"]: r["case_id"] for r in pair})
    return pairs, ab, ba


def _proof_dependencies(paths):
    deps = {}
    for path in paths:
        item = receipt(path)
        deps[item["path"]] = item
    return deps


def _adapter_proof(plan, args):
    """Delegate adapter-specific plan kinds to their dedicated proof builders."""
    kind = plan.get("kind")
    if kind == "msprof_op10_independent_v1":
        from msprof_op_effect_adapter import build_op_proof

        build = build_op_proof
    elif kind == "canonical10_independent":
        build = build_canonical_proof
    else:
        return None
    return build(*args)


def _check_source_case(case_id, source_identities, variants):
    if any(
        case_id != source_identities[v].get("kernel_sequence", {}).get("case_id")
        for v in variants
    ):
        raise ValueError("logical case/source identity mismatch")


@_verified_receipts
def build_proof(
    plan_path,
    registration_path,
    collection_path,
    baseline_path,
    candidate_path,
    case_id,
    baseline_variant="baseline",
    candidate_variant="candidate",
):
    deps = _proof_dependencies((plan_path, registration_path, collection_path, baseline_path, candidate_path))
    plan = read(plan_path)
    delegated = _adapter_proof(
        plan,
        (plan_path, registration_path, collection_path, baseline_path, candidate_path,
         case_id, baseline_variant, candidate_variant),
    )
    if delegated is not None:
        return delegated
    registration = read(registration_path)
    c = read(collection_path)
    frozen_plan = _registered_plan_check(plan_path, registration, deps)
    registration_precedes_capture(registration, c, deps)
    if plan.get("samples_per_case") != 10 or plan.get("round_count", 0) < 6:
        raise ValueError("paired plan requires canonical10 and at least 6 frozen rounds")
    historical = plan.get("stats", {}).get("ci") == HISTORICAL_CI
    method = _frozen_method(plan, historical, baseline_variant, candidate_variant, case_id)
    rows = plan["cases"]
    pairs, ab, ba = _collect_pairs(plan, rows, baseline_variant, candidate_variant)
    if abs(ab - ba) > 1:
        raise ValueError("paired order must balance AB and BA")
    medians, source_identities = verify_collection(plan, collection_path, deps, effect_plan=frozen_plan)
    base = [medians[p[baseline_variant]] for p in pairs]
    cand = [medians[p[candidate_variant]] for p in pairs]
    _check_headline_medians(baseline_path, candidate_path, case_id, base, cand)
    _check_source_case(case_id, source_identities, (baseline_variant, candidate_variant))
    stats = compute_statistics([b - a for a, b in zip(base, cand)], method)
    return {
        "schema_version": 1,
        "policy_id": "confidence_effect_v1",
        "policy_version": 1,
        "historical_adapter": historical,
        "plan": frozen_plan,
        "registration": receipt(registration_path),
        "collection": receipt(collection_path),
        "baseline": receipt(baseline_path),
        "candidate": receipt(candidate_path),
        "case_id": case_id,
        "baseline_variant": baseline_variant,
        "candidate_variant": candidate_variant,
        "target_soc": plan["soc"],
        "source_identities": {v: source_identities[v] for v in (baseline_variant, candidate_variant)},
        "input_identity": plan["snapshot"],
        "statistics": stats,
        "dependencies": sorted(deps.values(), key=lambda r: r["path"]),
    }


def _check_headline_medians(baseline_path, candidate_path, case_id, base, cand):
    from summarize_performance_effects import load_performance

    for path, values in ((baseline_path, base), (candidate_path, cand)):
        _, headlines = load_performance(Path(path))
        if case_id not in headlines or abs(headlines[case_id] - statistics.median(values)) > 1e-6:
            raise ValueError("headline case/median differs from paired original samples")


def _check_canonical_headlines(baseline_path, candidate_path, case_id, base, cand):
    from summarize_performance_effects import load_performance

    for path, values in ((baseline_path, base), (candidate_path, cand)):
        _, headlines = load_performance(Path(path))
        if case_id not in headlines or abs(headlines[case_id] - statistics.median(values)) > 1e-6:
            raise ValueError("canonical headline differs from original samples")


def independent_statistics(base, cand, method):
    """Shared unchanged statistic for application and explicit msprof-op adapters."""
    rng = random.Random(method["seed"])
    deltas = sorted(
        statistics.median(rng.choices(cand, k=10)) - statistics.median(rng.choices(base, k=10))
        for _ in range(method["draws"])
    )
    return {
        "method": method,
        "estimator": "independent_median_difference",
        "estimate_us": statistics.median(cand) - statistics.median(base),
        "ci_us": [quantile(deltas, 0.025), quantile(deltas, 0.975)],
        "baseline_samples_us": base,
        "candidate_samples_us": cand,
    }


def _canonical_side(plan, registration, side, variant, binding, collection_path, contexts, deps, case_id):
    """Verify one canonical side's collection and return its ordered ten samples."""
    if side == "baseline_collection" or "sha256" in binding["manifest"]:
        check_receipt(binding["manifest"])
    else:
        receipt(binding["manifest"]["path"])  # Declared future output path; SHA captured only after collection.
    if side == "baseline_collection" and receipt(collection_path) != binding["manifest"]:
        raise ValueError("canonical builder collection differs from frozen baseline collection")
    c = read(binding["manifest"]["path"])
    contexts.append(
        {
            "warmup": {
                k: c["warmup"].get(k)
                for k in ("mode", "logical_op", "implementation", "tensor_bytes", "tensor_allocation")
            },
            "cann_version": c.get("identity", {}).get("cann_version"),
            "environment": c.get("identity", {}).get("environment"),
        }
    )
    if side == "candidate_collection":
        registration_precedes_capture(registration, c, deps, label="canonical method")
    # The baseline may be an existing canonical receipt. Neither side can be
    # recollected or cherry-picked; the plan binds its original full order.
    side_plan = {
        **plan,
        "cases": [{"case_id": c} for c in binding["case_order"]],
        "expected_relevant_launches": binding["expected_relevant_launches"],
        "expected_identity": binding["expected_identity"],
    }
    medians, identities = verify_collection(side_plan, Path(binding["manifest"]["path"]), deps)
    if binding["case_id"] not in medians or variant not in identities:
        raise ValueError("canonical source/collection case identity mismatch")
    if identities[variant].get("kernel_sequence", {}).get("case_id") != case_id:
        raise ValueError("canonical logical case identity mismatch")
    _check_canonical_variant(c, binding, identities, variant)
    sources = identities[variant]
    with Path(c["performance_csv"]).open(newline="") as stream:
        row = next(r for r in csv.DictReader(stream) if r["case_id"] == binding["case_id"])
    return json.loads(row["sample_total_us"]), sources


def _check_canonical_variant(c, binding, identities, variant):
    actual_runs = []
    if len(c.get("sessions", [])) > 1:
        for session in c["sessions"]:
            actual_runs.extend(read(session["execution_manifest"])["case_runs"])
    else:
        actual_runs = read(c["execution_manifest"])["case_runs"]
    actual_run = next(r for r in actual_runs if r["case_id"] == binding["case_id"])
    actual_variant = actual_run.get("variant", actual_run.get("confirmation", {}).get("variant"))
    if actual_variant is None and len(identities) == 1:
        actual_variant = next(iter(identities))
    if actual_variant != variant:
        raise ValueError("canonical case does not identify its actually executed source variant")


@_verified_receipts
def build_canonical_proof(
    plan_path,
    registration_path,
    collection_path,
    baseline_path,
    candidate_path,
    case_id,
    baseline_variant,
    candidate_variant,
):
    """Strong canonical10 screening can use independent median confidence.

    This consumes ten original samples per side once, without pairing unrelated
    launches or requiring repeated rounds for every case. Small screening changes
    still require the paired method to control order/session noise.
    """
    plan, registration = read(plan_path), read(registration_path)
    if (
        plan.get("effect_case_id") != case_id
        or plan.get("baseline_variant") != baseline_variant
        or plan.get("candidate_variant") != candidate_variant
    ):
        raise ValueError("canonical plan case/comparison binding mismatch")
    method = _canonical_method(plan)
    frozen_plan = receipt(plan_path)
    if frozen_plan not in [
        {"path": r.get("path"), "sha256": r.get("sha256")} for r in registration.get("artifacts", [])
    ]:
        raise ValueError("canonical plan not registered before result")
    deps = {}
    for path in (plan_path, registration_path, baseline_path, candidate_path):
        item = receipt(path)
        deps[item["path"]] = item
    samples, sources, contexts = {}, {}, []
    for side, variant in (("baseline_collection", baseline_variant), ("candidate_collection", candidate_variant)):
        samples[side], sources[variant] = _canonical_side(
            plan, registration, side, variant, plan[side], collection_path, contexts, deps, case_id
        )
    if contexts[0] != contexts[1]:
        raise ValueError("independent canonical protocol/environment is asymmetric")
    base, cand = samples["baseline_collection"], samples["candidate_collection"]
    _check_canonical_headlines(baseline_path, candidate_path, case_id, base, cand)
    stats = independent_statistics(base, cand, method)
    return {
        "schema_version": 1,
        "kind": "canonical10_independent",
        "policy_id": "confidence_effect_v1",
        "policy_version": 1,
        "historical_adapter": False,
        "plan": frozen_plan,
        "registration": receipt(registration_path),
        "collection": receipt(collection_path),
        "baseline": receipt(baseline_path),
        "candidate": receipt(candidate_path),
        "case_id": case_id,
        "baseline_variant": baseline_variant,
        "candidate_variant": candidate_variant,
        "target_soc": plan["soc"],
        "source_identities": sources,
        "input_identity": plan["snapshot"],
        "statistics": stats,
        "dependencies": sorted(deps.values(), key=lambda r: r["path"]),
    }


def _canonical_method(plan):
    method = plan.get("statistical_method", {})
    if method.get("id") != INDEPENDENT_METHOD or method.get("confidence") != 0.95:
        raise ValueError("unknown independent canonical statistical method/version")
    if method.get("statistic") != "difference_of_medians" or method.get("quantile") != "linear":
        raise ValueError("unknown independent canonical statistical method/version")
    if (
        not isinstance(method.get("seed"), int)
        or not isinstance(method.get("draws"), int)
        or not 1000 <= method["draws"] <= 1000000
    ):
        raise ValueError("independent bootstrap requires frozen seed/draws")
    return method


def _collect_source_files(document, dependencies):
    """Register the original source scope as well as build/runtime receipts."""
    from prepare_case_sets import CODE_SUFFIXES, IGNORED_CODE_DIRS

    for directory, dirs, names in os.walk(document["source"]["path"]):
        dirs[:] = sorted(d for d in dirs if d not in IGNORED_CODE_DIRS)
        for name in sorted(names):
            file = Path(directory) / name
            if file.suffix.lower() in CODE_SUFFIXES or name in ("CMakeLists.txt", "Makefile"):
                item = receipt(file)
                dependencies[item["path"]] = item


@_verified_receipts
def verify_noop(path, baseline_path, candidate_path):
    """Same receipt is allowed only with identical source, build and loaded identity."""
    from validate_execution_identity import validate_execution_identity, dependency_paths
    from prepare_case_sets import CODE_SUFFIXES, IGNORED_CODE_DIRS

    receipt(path)
    value = read(path)
    if value.get("schema_version") == 1 and value.get("kind") == "casewise_byte_identical_noop":
        return verify_casewise_noop(value, baseline_path, candidate_path)
    if value.get("schema_version") != 1 or value.get("kind") != "byte_identical_noop":
        raise ValueError("unknown same-implementation evidence")
    if value.get("baseline") != receipt(baseline_path) or value.get("candidate") != receipt(candidate_path):
        raise ValueError("same-implementation proof comparison mismatch")
    base_order, base, cand_order, cand = _noop_timings(baseline_path, candidate_path)
    if base_order != cand_order or base != cand or value.get("case_ids") != base_order:
        raise ValueError("same implementation must reuse identical case timing receipt")
    documents, dependencies = _noop_documents(value)
    left, right = documents
    if _execution_signature(left) != _execution_signature(right):
        raise ValueError("different source/build/runtime implementations cannot use no-op evidence")
    return {
        "case_ids": base_order,
        "target_socs": [t["target_soc"] for t in left["targets"]],
        "dependencies": sorted(dependencies.values(), key=lambda r: r["path"]),
    }


def _noop_timings(baseline_path, candidate_path):
    from summarize_performance_effects import load_performance

    base_order, base = load_performance(Path(baseline_path))
    cand_order, cand = load_performance(Path(candidate_path))
    return base_order, base, cand_order, cand


def _noop_documents(value):
    from validate_execution_identity import validate_execution_identity, dependency_paths

    documents, dependencies = [], {}
    for side in ("baseline_execution", "candidate_execution"):
        binding = value[side]
        for key in ("manifest", "identity"):
            item = check_receipt(binding[key])
            dependencies[item["path"]] = item
        document = validate_execution_identity(Path(binding["manifest"]["path"]), Path(binding["identity"]["path"]))
        documents.append(document)
        for source in dependency_paths(document):
            item = receipt(source)
            dependencies[item["path"]] = item
        _collect_source_files(document, dependencies)
    return documents, dependencies


@_verified_receipts
def verify_casewise_noop(value, baseline_path, candidate_path):
    """Verify an explicit unchanged subset of one mixed comparison, never timings alone."""
    from validate_execution_identity import validate_execution_identity, dependency_paths
    from prepare_case_sets import CODE_SUFFIXES, IGNORED_CODE_DIRS, code_identity
    from summarize_performance_effects import load_performance

    if value.get("baseline") != receipt(baseline_path) or value.get("candidate") != receipt(candidate_path):
        raise ValueError("casewise no-op comparison mismatch")
    base_order, base = load_performance(Path(baseline_path))
    cand_order, cand = load_performance(Path(candidate_path))
    identifiers = value.get("case_ids")
    if base_order != cand_order or not isinstance(identifiers, list) or not identifiers:
        raise ValueError("casewise no-op case subset/order mismatch")
    if (
        any(not isinstance(case, str) for case in identifiers)
        or len(set(identifiers)) != len(identifiers)
        or identifiers != [case for case in base_order if case in identifiers]
    ):
        raise ValueError("casewise no-op case subset/order mismatch")
    if any(base[case] != cand[case] for case in identifiers):
        raise ValueError("casewise same implementation must reuse identical case timings")
    with Path(baseline_path).open(newline="") as stream:
        baseline_rows = {row["case_id"]: row for row in csv.DictReader(stream)}
    with Path(candidate_path).open(newline="") as stream:
        candidate_rows = {row["case_id"]: row for row in csv.DictReader(stream)}
    if any(baseline_rows[case] != candidate_rows[case] for case in identifiers):
        raise ValueError("casewise no-op must reuse the complete original timing rows")
    cases = value.get("cases")
    if not isinstance(cases, list) or [case.get("case_id") for case in cases] != identifiers:
        raise ValueError("casewise no-op execution coverage mismatch")
    dependencies, target_socs, checked_sources = {}, None, {}

    def checked(item):
        result = check_receipt(item)
        dependencies[result["path"]] = result
        return result

    for case in cases:
        sides = []
        for name in ("baseline", "candidate"):
            side_tuple, soc = _casewise_side(
                case[name], checked, dependencies, checked_sources, target_socs, validate_execution_identity
            )
            target_socs = [soc]
            sides.append(side_tuple)
        if sides[0] != sides[1]:
            raise ValueError("casewise no-op source/generated/build/runtime/arguments/inputs differ")
    for source in checked_sources.values():
        if code_identity(Path(source["path"])) != source:
            raise ValueError("casewise no-op source changed during verification")
    return {
        "case_ids": identifiers,
        "target_socs": target_socs,
        "dependencies": sorted(dependencies.values(), key=lambda item: item["path"]),
    }


def _casewise_side(side, checked, dependencies, checked_sources, target_socs, validate_execution_identity):
    from validate_execution_identity import dependency_paths

    binding = side["execution"]
    checked(binding["manifest"])
    checked(binding["identity"])
    document = validate_execution_identity(Path(binding["manifest"]["path"]), Path(binding["identity"]["path"]))
    checked_sources[document["source"]["path"]] = document["source"]
    if len(document["targets"]) != 1:
        raise ValueError("casewise no-op requires one actual SoC per execution pair")
    target = document["targets"][0]
    soc = target["target_soc"]
    if target_socs is not None and target_socs != [soc]:
        raise ValueError("casewise no-op target coverage differs between cases")
    for dependency in dependency_paths(document):
        checked(receipt(dependency))
    _casewise_source_files(document, checked)
    generated = _casewise_build_evidence(side, document, target, checked)
    observed = _casewise_runtime_evidence(side, document, target, checked, dependencies)
    inputs = _casewise_input_evidence(side, soc, checked, dependencies)
    call_specs = {json.dumps({"args": row["args"], "kwargs": row["kwargs"]}, sort_keys=True) for row in observed}
    return (
        (
            _execution_signature(document),
            sorted(item["sha256"] for item in generated),
            side["provider_source"]["sha256"],
            call_specs,
            inputs,
        ),
        soc,
    )


def _casewise_source_files(document, checked):
    from prepare_case_sets import CODE_SUFFIXES, IGNORED_CODE_DIRS

    for directory, dirs, names in os.walk(document["source"]["path"]):
        dirs[:] = sorted(d for d in dirs if d not in IGNORED_CODE_DIRS)
        for filename in sorted(names):
            source_file = Path(directory) / filename
            if source_file.suffix.lower() in CODE_SUFFIXES or filename in ("CMakeLists.txt", "Makefile"):
                checked(receipt(source_file))


def _casewise_build_evidence(side, document, target, checked):
    checked(side["compile_config"])
    config = read(side["compile_config"]["path"])
    if config.get("source") != document["source"] or config.get("target_soc") != target["target_soc"]:
        raise ValueError("casewise no-op compile configuration source/SoC mismatch")
    generated = side.get("normal_generated")
    if not isinstance(generated, list) or not generated:
        raise ValueError("casewise no-op requires normal generated code")
    for item in generated:
        checked(item)
    log = Path(target["build"]["log"]["path"]).read_text(errors="replace")
    hashes = [
        document["source"]["sha256"],
        side["compile_config"]["sha256"],
        *[item["sha256"] for item in generated + target["build"]["artifacts"]],
    ]
    if any(digest not in log for digest in hashes):
        raise ValueError("casewise no-op build log does not bind normal source/config/code/image")
    return generated


def _provider_observation_ok(row, side, soc):
    return (
        row.get("observer_method") == "ProviderCallable.__call__"
        and row.get("component") == "attention"
        and row.get("execution_kind") == "device"
        and row.get("provider_source") == side["provider_source"]
        and row.get("target_soc") == soc
        and row.get("source_owner_id") == side.get("source_owner_id")
    )


def _casewise_runtime_evidence(side, document, target, checked, dependencies):
    checked(side["actual_runtime"])
    if side["actual_runtime"] != target["runtime"]["evidence"]:
        raise ValueError("casewise no-op actual runtime identity mismatch")
    runtime = read(side["actual_runtime"]["path"])
    if runtime.get("compile_config") != side["compile_config"]:
        raise ValueError("casewise no-op runtime compile configuration mismatch")
    checked(side["raw_execution"])
    if side["raw_execution"] not in runtime.get("source_artifacts", []):
        raise ValueError("casewise no-op invocation is not bound to runtime")
    raw = read(side["raw_execution"]["path"])
    checked(side["provider_source"])
    provider_path = Path(side["provider_source"]["path"]).resolve()
    if not provider_path.is_relative_to(Path(document["source"]["path"]).resolve()):
        raise ValueError("casewise no-op Provider source is outside actual owner")
    if raw.get("source") != document["source"]:
        raise ValueError("casewise no-op observed source differs from actual owner")
    observed = _provider_invocations(side, raw, provider_path)
    for row in observed:
        if "observer_method" in row:
            if not _provider_observation_ok(row, side, target["target_soc"]):
                raise ValueError("casewise no-op actual Provider owner/method binding mismatch")
        elif (
            "ProviderCallable" not in str(raw.get("method", ""))
            or str(provider_path) not in raw.get("python_imports", {}).values()
        ):
            raise ValueError("casewise historical invocation lacks observed Provider import provenance")
    return observed


def _provider_invocations(side, raw, provider_path):
    actual_case = side.get("actual_case_id")
    if not isinstance(actual_case, str) or not actual_case:
        raise ValueError("casewise no-op requires actual case mapping")
    observed = [row for row in raw.get("invocations", []) if row.get("case_id") == actual_case]
    if not observed or any(not row.get("args") or not isinstance(row.get("kwargs"), dict) for row in observed):
        raise ValueError("casewise no-op lacks actual Provider invocation")
    return observed


def _owner_row_matches(row, side, soc, actual_case):
    return (
        row.get("case_id") == actual_case
        and row.get("target_soc") == soc
        and row.get("compile_config") == side["compile_config"]
        and row.get("runtime_evidence") == side["actual_runtime"]
        and row.get("provider_source") == side["provider_source"]
        and row.get("raw_evidence") == side["raw_execution"]
        and row.get("source_owner_id") == side.get("source_owner_id")
    )


def _input_digests_ok(inputs):
    if not isinstance(inputs, dict) or not inputs or not any(inputs.values()):
        return False
    for digest in inputs.values():
        if digest is not None and not (isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest)):
            return False
    return True


def _casewise_input_evidence(side, soc, checked, dependencies):
    if side.get("owner_execution_evidence"):
        checked(side["owner_execution_evidence"])
        owner_rows = read(side["owner_execution_evidence"]["path"]).get("results", [])
        actual_case = side.get("actual_case_id")
        if not any(_owner_row_matches(row, side, soc, actual_case) for row in owner_rows):
            raise ValueError("casewise no-op source owner execution receipt mismatch")
    checked(side["input_evidence"])
    inputs = read(side["input_evidence"]["path"])
    selector = side.get("input_selector")
    if not isinstance(selector, list) or not selector:
        raise ValueError("casewise no-op requires input selector")
    for field in selector:
        inputs = inputs[field]
    if not _input_digests_ok(inputs):
        raise ValueError("casewise no-op requires nonempty raw tensor input digests")
    return inputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("plan", "registration", "collection", "baseline", "candidate", "out"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--baseline-variant", default="baseline")
    parser.add_argument("--candidate-variant", default="candidate")
    args = parser.parse_args()
    value = build_proof(
        args.plan,
        args.registration,
        args.collection,
        args.baseline,
        args.candidate,
        args.case_id,
        args.baseline_variant,
        args.candidate_variant,
    )
    from summarize_performance_effects import atomic_write_text

    atomic_write_text(args.out, json.dumps(value, indent=2) + "\n")


if __name__ == "__main__":
    main()
