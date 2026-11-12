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
"""Read-only performance protocol and sample checks; never acquire a device."""

import argparse
import hashlib
import json
import logging
import math
from pathlib import Path
import sys

import yaml

COMMON_FIELDS = ("device", "cache_dir", "compile", "timing_boundary")
FLAT_FIELDS = {"samples", "warmup", "repeat_order", "rounds", "tool", "statistic"}
RETIRED_FIELDS = {"exclusivity_policy"}
LOGGER = logging.getLogger(__name__)


def mapping(value, label):
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a mapping")
    return value


def text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonempty string")
    return value


def integer(value, minimum, label):
    if type(value) is not int or value < minimum:
        raise ValueError(f"{label} must be an integer >= {minimum}")
    return value


def load(path):
    return mapping(yaml.safe_load(path.read_text(encoding="utf-8")), str(path))


def protocol_id(snapshot):
    encoded = json.dumps(snapshot, sort_keys=True, ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def contract_cases(contract):
    mapping(contract, "contract")
    integer(contract.get("version"), 1, "version")
    text(contract.get("target"), "target")
    rules = contract.get("adopt_rule")
    if not isinstance(rules, list) or not rules:
        raise ValueError("adopt_rule must be a nonempty list")
    for rule in rules:
        text(rule, "adopt_rule entry")
    cases = contract.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("cases must be a nonempty list of confirmed cases")
    case_ids = [text(mapping(case, "case").get("id"), "case.id") for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("duplicate case IDs")
    budget = mapping(contract.get("budget"), "budget")
    for key in ("max_candidates", "max_rounds"):
        integer(budget.get(key), 1, f"budget.{key}")
    text(budget.get("stop"), "budget.stop")
    return cases, case_ids


def sampling_profile(protocol, purpose, warnings):
    legacy = purpose not in protocol
    if legacy:
        if purpose == "comparison":
            raise ValueError(
                "protocol.comparison is missing; flat legacy sampling is diagnostic-only. "
                "Confirm a comparison profile before claiming stable improvement."
            )
        if "diagnostics" in protocol or "comparison" in protocol:
            raise ValueError("protocol.diagnostics is missing")
        if protocol.get("rounds", 1) != 1:
            raise ValueError("legacy rounds are ambiguous; confirm an explicit diagnostics profile")
        profile = {key: protocol.get(key) for key in ("samples", "warmup", "repeat_order", "tool")}
        if profile["warmup"] == "none":
            profile["warmup"] = 0
        profile["max_invalid_retries"] = 0
        warnings.append("Legacy flat protocol is accepted for diagnostics only; no comparison evidence is inferred.")
    else:
        if FLAT_FIELDS & protocol.keys():
            raise ValueError("do not mix phase-specific profiles with legacy flat sampling fields")
        profile = dict(mapping(protocol.get(purpose), f"protocol.{purpose}"))
    validate_profile(profile, purpose)
    return profile


def validate_profile(profile, purpose):
    integer(profile.get("samples"), 2 if purpose == "comparison" else 1, f"{purpose}.samples")
    integer(profile.get("warmup"), 0, f"{purpose}.warmup")
    integer(profile.get("max_invalid_retries"), 0, f"{purpose}.max_invalid_retries")
    text(profile.get("tool"), f"{purpose}.tool")
    text(profile.get("repeat_order"), f"{purpose}.repeat_order")
    if purpose == "comparison":
        order, statistic = profile["repeat_order"], profile.get("statistic")
        allowed = {
            "independent": {"median", "mean"},
            "interleaved": {"paired_median_ratio", "paired_mean_ratio"},
        }
        if order not in allowed or statistic not in allowed[order]:
            raise ValueError("comparison order/statistic mismatch; minimum/best-sample selection is not supported")


def resolve_protocol(contract, purpose):
    if purpose not in ("diagnostics", "comparison"):
        raise ValueError("purpose must be diagnostics or comparison")
    if contract is None:
        if purpose != "diagnostics":
            raise ValueError("comparison requires a confirmed performance contract")
        return {
            "status": "pass", "purpose": purpose, "diagnostic_only": True,
            "protocol_id": None, "snapshot": None,
            "warnings": ["No performance contract: one diagnostic call per case, no warmup; no gain claim."],
        }
    cases, case_ids = contract_cases(contract)
    protocol = mapping(contract.get("protocol"), "protocol")
    for key in COMMON_FIELDS:
        text(protocol.get(key), f"protocol.{key}")
    warnings = []
    if RETIRED_FIELDS & protocol.keys():
        warnings.append("exclusivity_policy is retired and ignored: no exclusivity or quiet-window gate.")
    profile = sampling_profile(protocol, purpose, warnings)
    common = {key: value for key, value in protocol.items()
              if key not in FLAT_FIELDS | RETIRED_FIELDS | {"diagnostics", "comparison"}}
    snapshot = {"purpose": purpose, "common": common, "sampling": profile, "cases": cases}
    return {
        "status": "pass", "purpose": purpose, "diagnostic_only": purpose == "diagnostics",
        "case_ids": case_ids, "protocol_id": protocol_id(snapshot), "snapshot": snapshot,
        "warnings": warnings,
    }


def check_sample(sample, profile, case_id, pairs):
    text(sample.get("raw_path"), "sample.raw_path")
    # Sharing is an observation, never a reason to reject a sample.
    if sample.get("concurrency") not in ("observed", "not_observed", "unknown"):
        raise ValueError("sample.concurrency must record observed/not_observed/unknown")
    if sample.get("status") == "invalid":
        if sample.get("failure_kind") not in ("tool_error", "missing_data", "unmatched_task"):
            raise ValueError(
                "only evidence failures may invalidate samples; slow/shared samples cannot be discarded"
            )
        text(sample.get("reason"), "invalid sample.reason")
        return False
    if sample.get("status") != "valid":
        raise ValueError("sample.status must be valid or invalid")
    value = sample.get("duration_us")
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise ValueError("valid sample.duration_us must be finite and positive")
    if profile["repeat_order"] == "interleaved":
        pair = text(sample.get("pair_id"), "valid sample.pair_id")
        if pair in pairs:
            raise ValueError(f"{case_id}: duplicate pair_id")
        pairs.add(pair)
    return True


def check_case_samples(case, profile, case_id):
    samples = case.get("samples")
    if not isinstance(samples, list):
        raise ValueError(f"{case_id}: samples must be a list")
    valid, invalid, seen, pairs = [], [], set(), set()
    for sample in samples:
        mapping(sample, f"{case_id} sample")
        sample_id = text(sample.get("id"), "sample.id")
        if sample_id in seen:
            raise ValueError(f"{case_id}: duplicate sample ID")
        seen.add(sample_id)
        target = valid if check_sample(sample, profile, case_id, pairs) else invalid
        target.append(sample)
    if len(valid) != profile["samples"]:
        raise ValueError(f"{case_id}: valid sample count differs from protocol.samples")
    if len(invalid) > profile["max_invalid_retries"]:
        raise ValueError(f"{case_id}: invalid retry budget exceeded")
    return {"valid": valid, "pairs": pairs}


def check_measurement(measurement, resolved):
    """Check completeness, not the truth of logs or statistical significance."""
    mapping(measurement, "measurement")
    if resolved["snapshot"] is None:
        raise ValueError("measurement validation requires an explicit contract")
    if measurement.get("protocol") != resolved["snapshot"]:
        raise ValueError("measurement protocol differs from the confirmed profile")
    if measurement.get("protocol_id") != resolved["protocol_id"]:
        raise ValueError("measurement protocol_id does not match its protocol")
    for key in ("commit", "entry", "case_version", "collection_id"):
        text(measurement.get(key), f"measurement.{key}")
    records = measurement.get("cases")
    if not isinstance(records, list):
        raise ValueError("measurement.cases must be a list")
    indexed = {}
    profile = resolved["snapshot"]["sampling"]
    for case in records:
        mapping(case, "measurement case")
        case_id = text(case.get("id"), "measurement case.id")
        if case_id in indexed:
            raise ValueError("duplicate measurement case ID")
        indexed[case_id] = check_case_samples(case, profile, case_id)
    if set(indexed) != set(resolved["case_ids"]):
        raise ValueError("measurement case set differs from the contract")
    return indexed


def check_reference(measurement, reference, resolved):
    candidate = check_measurement(measurement, resolved)
    baseline = check_measurement(reference, resolved)
    if measurement["case_version"] != reference["case_version"]:
        raise ValueError("candidate and baseline case versions do not match")
    if resolved["snapshot"]["sampling"]["repeat_order"] == "interleaved":
        if measurement["collection_id"] != reference["collection_id"]:
            raise ValueError("interleaved candidate and baseline must come from the same collection_id")
        for case_id in candidate:
            if candidate[case_id]["pairs"] != baseline[case_id]["pairs"]:
                raise ValueError(f"{case_id}: candidate and baseline pair IDs do not match")


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--purpose", choices=("diagnostics", "comparison"), required=True)
    parser.add_argument("--measurement", type=Path)
    parser.add_argument("--reference", type=Path)
    args = parser.parse_args()
    try:
        resolved = resolve_protocol(load(args.contract) if args.contract else None, args.purpose)
        if args.reference and not args.measurement:
            raise ValueError("--reference requires --measurement")
        if args.measurement:
            measurement = load(args.measurement)
            check_measurement(measurement, resolved)
            if args.reference:
                check_reference(measurement, load(args.reference), resolved)
            resolved["measurement_check"] = "pass"
            resolved["gain_verdict"] = "not_evaluated"
        LOGGER.info("%s", json.dumps(resolved, ensure_ascii=False, indent=2, allow_nan=False))
    except (OSError, ValueError, TypeError, yaml.YAMLError) as exc:
        LOGGER.info("%s", json.dumps({"status": "fail", "error": str(exc)}, ensure_ascii=False))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
