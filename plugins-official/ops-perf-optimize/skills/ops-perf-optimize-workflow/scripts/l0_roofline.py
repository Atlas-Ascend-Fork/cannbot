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

"""L0 Roofline prefilter adapter (evidence mode by default).

Calls the installed or vendored calibrated Ascend950 vector roofline engine for every
candidate that maps to a case id and records theoretical lower bounds in the
``prefilter.l0`` slot. Candidates without a case mapping stay in ``unmapped``
and are never pruned. This adapter never prunes: it only records bounds.

Scope: pure RegBase vector kernels only (the engine rejects Cube/matmul).
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from pathlib import Path

from validate_schedule_contract import ref

SCRIPT_DIR = Path(__file__).resolve().parent


def default_skill_dir():
    env = os.environ.get("OPS_THEORETICAL_SKILL")
    if env:
        return Path(env)
    installed = SCRIPT_DIR.parent.parent / "ops-theoretical-performance-estimation"
    if (installed / "scripts/perf.py").is_file():
        return installed
    anchor = SCRIPT_DIR
    for base in (Path.cwd(), *Path.cwd().parents, *anchor.parents):
        candidate = (
            base / "vendor/cannbot-skills/ops/ops-theoretical-performance-estimation"
        )
        if (candidate / "scripts/perf.py").is_file():
            return candidate
    return None


def _evidence(paths):
    seen, out = set(), []
    for path in paths:
        if path is None:
            continue
        path = Path(path)
        if not path.is_file():
            continue
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        out.append(ref(path))
    return out


def run_engine(skill_dir, op, cases):
    """Return ({case_id: result}, hardware_variant) from the vendored engine."""
    scripts = Path(skill_dir) / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    perf = importlib.import_module("perf")
    bridge = importlib.import_module("_engine_bridge")
    spec, rows = bridge.evaluate_spec(perf.build_case_for(op), Path(cases))
    results = {}
    for row in rows:
        result = dict(row["result"])
        result["_template"] = row["case_dict"].get("_template")
        results[row["case"]["case_id"]] = result
    return results, spec.get("hardware_variant")


def case_id_for(node):
    factors = node.get("factors") or {}
    bindings = node.get("bindings") or {}
    return factors.get("case_id") or bindings.get("case_id")


def build_fragment(frontier, results, evidence, op, hardware_variant=None):
    candidates, unmapped = [], []
    for node in frontier.get("nodes", []):
        if node.get("explore_tag") == "open":
            continue
        scheme = node.get("scheme_id")
        case_id = case_id_for(node)
        if not case_id:
            unmapped.append({"scheme_id": scheme, "reason": "no case_id mapping"})
            continue
        result = results.get(case_id)
        if result is None:
            unmapped.append(
                {
                    "scheme_id": scheme,
                    "reason": f"case_id {case_id} not in engine report",
                }
            )
            continue
        bound = result.get("theoretical_time_us")
        if not isinstance(bound, (int, float)) or bound <= 0:
            unmapped.append(
                {"scheme_id": scheme, "reason": "engine returned no positive bound"}
            )
            continue
        candidates.append(
            {
                "scheme_id": scheme,
                "case_id": case_id,
                "template": result.get("_template"),
                "bound": result.get("bound"),
                "bound_us": float(bound),
                "mte2_us": result.get("mte2_time_us"),
                "vector_us": result.get("vector_time_us"),
                "mte3_us": result.get("mte3_time_us"),
            }
        )
    best = frontier.get("best_total_us")
    bounds = [item["bound_us"] for item in candidates]
    return {
        "status": "applied" if candidates else "unsupported",
        "reason": None if candidates else "no candidate mapped to a roofline case",
        "method": "a5-vector-roofline-calibrated",
        "mode": "evidence",
        "operator": op,
        "hardware_variant": hardware_variant,
        "best_total_us": best,
        "bound_floor_us": min(bounds) if bounds else None,
        "coverage": len(candidates),
        "unmapped": unmapped,
        "candidates": candidates,
        "pruned": [],
        "budget_skipped": 0,
        "evidence": evidence,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--op", required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--frontier", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--skill-dir", type=Path)
    parser.add_argument(
        "--engine-report",
        type=Path,
        help="precomputed {case_id: result} JSON (tests/offline)",
    )
    args = parser.parse_args(argv)
    try:
        frontier = json.loads(args.frontier.read_text(encoding="utf-8"))
        skill_dir = args.skill_dir or default_skill_dir()
        if args.engine_report:
            payload = json.loads(args.engine_report.read_text(encoding="utf-8"))
            results = payload.get("results", payload)
            variant = payload.get("hardware_variant")
            evidence = _evidence([args.engine_report, args.cases, args.frontier])
        else:
            if skill_dir is None:
                raise FileNotFoundError(
                    "roofline skill not found; pass --skill-dir or set OPS_THEORETICAL_SKILL"
                )
            results, variant = run_engine(skill_dir, args.op, args.cases)
            flow = Path(skill_dir) / "references/examples" / f"{args.op}_flow.json"
            hardware = Path(skill_dir) / "references/hardware/ascend950pr.json"
            evidence = _evidence(
                [
                    Path(skill_dir) / "scripts/perf.py",
                    Path(skill_dir) / "scripts/flow_runtime.py",
                    Path(skill_dir) / "scripts/evaluate_a5_vector_roofline.py",
                    hardware,
                    flow,
                    args.cases,
                    args.frontier,
                ]
            )
        fragment = build_fragment(frontier, results, evidence, args.op, variant)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(fragment, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(
            json.dumps(
                {
                    "status": fragment["status"],
                    "out": str(args.out.resolve()),
                    "coverage": fragment["coverage"],
                    "unmapped": len(fragment["unmapped"]),
                    "pruned": 0,
                    "mode": "evidence",
                },
                ensure_ascii=False,
            )
        )
        return 0
    except (OSError, ValueError, KeyError, TypeError, ImportError) as error:
        print(
            json.dumps({"status": "invalid", "reason": str(error)}, ensure_ascii=False)
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
