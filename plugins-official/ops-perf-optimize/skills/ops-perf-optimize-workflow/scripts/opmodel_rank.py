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

"""Map OpModel schedule rankings onto candidate-frontier scheme ids.

OpModel's dag_run ranks schedules (Cycles + tiling parameters), not the
search engine's scheme_ids. This adapter reads a per-operator binding file
(frontier axis value -> OpModel parameter value) and produces a conservative
scheme ranking: mapped schemes are sorted by their best matching Cycles;
unmapped schemes are always retained and reported, never invented.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROW = re.compile(r"^\s*(\d+)\s+(\d+)\s+\S+\s+(.+?)\s*$")
PARAM = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)=([^\s\[]+)")


def _norm(value):
    text = str(value)
    try:
        return str(int(text))
    except ValueError:
        return text


def parse_schedules(text):
    rows = []
    for line in text.splitlines():
        match = ROW.match(line)
        if not match:
            continue
        tiling = {name: _norm(value) for name, value in PARAM.findall(match.group(3))}
        if not tiling:
            continue
        rows.append({"rank": int(match.group(1)), "cycles": int(match.group(2)), "tiling": tiling})
    if not rows:
        raise ValueError("no schedule rows parsed from OpModel output")
    return rows


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _axis_value(axis, value, binding):
    mapped = binding.get("values")
    if mapped is not None:
        key = _norm(value)
        if key not in {_norm(k) for k in mapped}:
            return None
        return _norm(mapped[next(k for k in mapped if _norm(k) == key)])
    return _norm(value)


def scheme_params(factors, binding):
    axes = binding.get("axes") or {}
    params = {_norm(k): _norm(v) for k, v in (binding.get("fixed") or {}).items()}
    for axis, rule in axes.items():
        if axis not in factors:
            return None
        param = rule.get("param") if isinstance(rule, dict) else rule
        if not param:
            return None
        value = _axis_value(axis, factors[axis], rule if isinstance(rule, dict) else {})
        if value is None:
            return None
        params[_norm(param)] = value
    return params


def rank(frontier, schedules, binding):
    mapped, unmapped = [], []
    for node in frontier.get("nodes", []):
        if node.get("explore_tag") == "open":
            continue
        scheme_id = node.get("scheme_id")
        params = scheme_params(node.get("factors") or {}, binding)
        if params is None:
            unmapped.append({"scheme_id": scheme_id, "reason": "axis missing or value unmapped"})
            continue
        matches = [
            row for row in schedules
            if all(row["tiling"].get(key) == value for key, value in params.items())
        ]
        if not matches:
            unmapped.append({"scheme_id": scheme_id, "reason": "no schedule matches binding"})
            continue
        best = min(matches, key=lambda row: (row["cycles"], row["rank"]))
        mapped.append({
            "scheme_id": scheme_id,
            "cycles": best["cycles"],
            "schedule_rank": best["rank"],
            "params": params,
        })
    mapped.sort(key=lambda item: (item["cycles"], item["scheme_id"]))
    ranking = [item["scheme_id"] for item in mapped] + [item["scheme_id"] for item in unmapped]
    return {
        "schema_version": 1,
        "ranking": ranking,
        "mapped": mapped,
        "unmapped": unmapped,
        "schedules": len(schedules),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frontier", type=Path, required=True)
    parser.add_argument("--binding", type=Path, required=True)
    parser.add_argument("--stdout", type=Path, help="captured OpModel stdout")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        text = args.stdout.read_text(encoding="utf-8") if args.stdout else sys.stdin.read()
        result = rank(load_json(args.frontier), parse_schedules(text), load_json(args.binding))
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"status": "ranked", "out": str(args.out.resolve()),
                          "mapped": len(result["mapped"]), "unmapped": len(result["unmapped"])}, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({"status": "invalid", "reason": str(error)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
