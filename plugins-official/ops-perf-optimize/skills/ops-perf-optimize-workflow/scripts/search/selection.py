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

"""Merge a search observation into an existing selection.json.

The merge only writes the `search` block. It requires the normal conformance
gate and effect summary for a measured outcome, and mechanism evidence for a
verified/refuted verdict. It never changes `selected_candidate`, promotes a
candidate, or bypasses precision/identity gates.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

from . import policy as search


OUTCOMES = search.OUTCOMES


def _atomic_json(path, payload):
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(prefix=path.name, dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
        os.replace(temp, path)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise


def _observation(observations_path, scheme_id):
    payload = search.load(observations_path)
    observations = payload.get("observations")
    search.require(
        isinstance(observations, list) and observations, "observations are empty"
    )
    if scheme_id is None:
        scheme_id = payload.get("recommended")
    search.require(isinstance(scheme_id, str) and scheme_id, "no scheme_id selected")
    item = next(
        (item for item in observations if item.get("scheme_id") == scheme_id), None
    )
    search.require(item is not None, f"observation not found: {scheme_id}")
    return payload, item


def build(
    selection_path,
    observations_path,
    scheme_id,
    gate,
    effect,
    evidence,
    mechanism_status,
    mechanism_evidence,
    retry_condition,
    *,
    replace=False,
):
    selection = search.load(selection_path)
    search.require(isinstance(selection, dict), "selection.json must be an object")
    if selection.get("search") is not None and not replace:
        raise ValueError(
            "selection.json already has search; pass --replace to overwrite"
        )
    observations, item = _observation(observations_path, scheme_id)
    outcome = item.get("outcome")
    search.require(outcome in OUTCOMES, f"invalid observation outcome: {outcome}")
    scheme = item.get("scheme_id")
    search.require(isinstance(scheme, str) and scheme, "observation needs scheme_id")
    refs = [search.ref(observations_path)]
    for path in evidence:
        refs.append(search.ref(path))
    result = {
        "scheme_id": scheme,
        "outcome": outcome,
        "evidence": refs,
        "retry_condition": retry_condition
        or item.get("retry_condition")
        or "re-measure with new evidence",
        "mechanism": {"status": mechanism_status},
        "comparison": observations.get("comparison", "unknown"),
        "confirmation_required": bool(observations.get("confirmation_required", False)),
        "exploration_eligible": bool(observations.get("exploration_eligible", False)),
        "exploration_blocker": observations.get("exploration_blocker"),
        "shape_specific": bool(observations.get("shape_specific", False)),
        "ready_for_confirmation": bool(
            observations.get("ready_for_confirmation", False)
        ),
        "holdout": observations.get("holdout"),
        "no_go": observations.get("no_go", []),
    }
    # Older observation producers emit null for an unbucketed item; omit that
    # legacy sentinel while preserving and validating an actual declaration.
    if item.get("case_bucket") is not None:
        result["case_bucket"] = search.checked_case_bucket(
            item, "observation.case_bucket"
        )
    if outcome == "measured":
        search.require(gate, "measured outcome needs --conformance-gate")
        search.require(effect, "measured outcome needs --effect-summary")
        result["conformance_gate"] = search.ref(gate)
        result["effect_summary"] = search.ref(effect)
        for name in ("score_distribution", "pareto_rank"):
            search.require(name in item, f"measured observation needs {name}")
            result[name] = item[name]
        for name in ("confidence_interval", "statistical_evidence"):
            if item.get(name) is not None:
                result[name] = item[name]
        if item.get("race") is not None:
            result["race"] = item["race"]
        if item.get("prune_reason") is not None:
            result["prune_reason"] = item["prune_reason"]
        search.validate_observation(result, {})
    if mechanism_status in ("verified", "refuted"):
        search.require(
            mechanism_evidence, f"{mechanism_status} needs --mechanism-evidence"
        )
        result["mechanism"]["evidence"] = [
            search.ref(path) for path in mechanism_evidence
        ]
    elif mechanism_evidence:
        result["mechanism"]["evidence"] = [
            search.ref(path) for path in mechanism_evidence
        ]
    merged = dict(selection)
    merged["search"] = result
    return merged


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--scheme-id")
    parser.add_argument("--conformance-gate", type=Path)
    parser.add_argument("--effect-summary", type=Path)
    parser.add_argument("--evidence", type=Path, action="append", default=[])
    parser.add_argument(
        "--mechanism-status",
        choices=("verified", "refuted", "unknown"),
        default="unknown",
    )
    parser.add_argument("--mechanism-evidence", type=Path, action="append", default=[])
    parser.add_argument("--retry-condition")
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    try:
        merged = build(
            args.selection.resolve(),
            args.observations.resolve(),
            args.scheme_id,
            args.conformance_gate,
            args.effect_summary,
            args.evidence,
            args.mechanism_status,
            args.mechanism_evidence,
            args.retry_condition,
            replace=args.replace,
        )
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(
            json.dumps({"status": "invalid", "reason": str(error)}, ensure_ascii=False)
        )
        return 2
    _atomic_json(args.out or args.selection, merged)
    print(
        json.dumps(
            {"status": "merged", "out": str((args.out or args.selection).resolve())},
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
