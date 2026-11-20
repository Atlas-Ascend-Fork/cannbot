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

"""Check an extracted experience archive without reading original local paths.

Checks text identities, cited JSON/line anchors, effect CSV arithmetic and
profile_median_v1 samples. Does not run archived commands or kernels, or review
causality. Archives declare excluded binary/runtime dependencies explicitly.
"""
import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import statistics

from rough_bundle import require, safe_name


def verify(root):
    root = root.resolve()
    index = json.loads((root / "archive-index.json").read_text())
    require(index["schema_version"] == 1, "unknown archive schema")
    files = index["files"]

    def local(name):
        safe_name(name)
        p = root / name
        require(p.resolve().is_relative_to(root), "reference escapes archive")
        require(name in files and p.is_file(), "missing archived source")
        return p

    for name, digest in files.items():
        require(hashlib.sha256(local(name).read_bytes()).hexdigest() == digest,
                "archive SHA mismatch")

    def historical(path):
        # These strings are lookup keys only. Never Path(path).open().
        for old, new in index["path_roots"].items():
            if path.startswith(old + "/"):
                return local(new + "/" + path[len(old) + 1:])
        raise ValueError("historical reference has no archived mapping")

    def ref(value):
        p = historical(value["path"])
        require(hashlib.sha256(p.read_bytes()).hexdigest() == value["sha256"],
                "reference SHA mismatch")
        return p

    def load(p):
        return json.loads(p.read_text())

    def pointer(obj, pointer):
        require(not pointer or pointer.startswith("/"), "invalid JSON pointer")
        for part in pointer.split("/")[1:]:
            key = part.replace("~1", "/").replace("~0", "~")
            obj = obj[int(key)] if isinstance(obj, list) else obj[key]
        return obj

    bundle = load(local(index["lessons"]))
    sources = {key: ref(value) for key, value in bundle["sources"].items()}
    anchor_count = 0
    for lesson in bundle["lessons"]:
        for statement in [*lesson["observations"], lesson["reasoning"]]:
            for anchor in statement["evidence"]:
                p = sources[anchor["source"]]
                if "pointer" in anchor:
                    pointer(load(p), anchor["pointer"])
                else:
                    first, last = anchor["lines"]
                    require(1 <= first <= last <= len(p.read_text().splitlines()), "line anchor outside source")
                anchor_count += 1

    def durations(path):
        rows = list(csv.DictReader(path.read_text().splitlines()))
        result = {row["case_id"]: float(row["total_us"]) for row in rows}
        require(len(result) == len(rows), "duplicate case ID")
        require(all(math.isfinite(v) and v > 0 for v in result.values()), "invalid duration")
        return result

    effects = {}
    for key in index["effects"]:
        effect = load(sources[key])
        before = durations(historical(effect["baseline_path"]))
        after = durations(historical(effect["candidate_path"]))
        require(before.keys() == after.keys(), "effect case sets differ")
        ratios = {k: before[k] / after[k] for k in before}
        ratio = math.exp(statistics.mean(math.log(x) for x in ratios.values()))
        require(len(ratios) == effect["total_case_count"], "effect case count mismatch")
        require(math.isclose(ratio, effect["effective_geomean_speedup"], rel_tol=1e-12), "effect ratio mismatch")
        for row in effect["cases"]:
            require(math.isclose(row["speedup"], ratios[row["case_id"]], rel_tol=1e-12), "case ratio mismatch")
        effects[key] = {"cases": len(ratios), "geomean_speedup": ratio}

    valid = failed = kernels = 0
    final_effect = load(sources[index["sampling_effect"]])
    expected = {"baseline": durations(historical(final_effect["baseline_path"])),
                "candidate": durations(historical(final_effect["candidate_path"]))}
    seen_cases = set()
    for spec in index["collections"]:
        case_id = spec["case_id"]
        require(case_id not in seen_cases, "duplicate sampling case")
        seen_cases.add(case_id)
        collection = load(local(spec["name"]))
        values = {"baseline": [], "candidate": []}
        seen_samples = set()
        for sample in collection["samples"]:
            variant = sample["variant"]
            samples = values.get(variant)
            require(samples is not None, "unknown sampling variant")
            key = (variant, sample["sample_index"])
            require(key not in seen_samples, "duplicate sample")
            seen_samples.add(key)
            accepted = []
            for attempt_ref in sample["attempts"]:
                attempt = load(ref(attempt_ref))
                if attempt["status"] == "valid":
                    accepted.append(attempt)
                else:
                    require(attempt["status"] == "failed", "unknown attempt status")
                    failed += 1
            require(len(accepted) == 1, "sample needs exactly one valid recorded attempt")
            summary = load(ref(accepted[0]["summary"]))
            require(summary["records"], "empty sample records")
            total = 0.0
            for record in summary["records"]:
                rows = list(csv.DictReader(io.StringIO(ref(record["source"]).read_text())))
                require(2 <= record["line"] <= len(rows) + 1, "record line outside CSV")
                value = float(rows[record["line"] - 2]["Task Duration(us)"])
                require(math.isfinite(value) and value > 0 and
                        math.isclose(value, record["duration_us"], rel_tol=1e-12), "kernel duration mismatch")
                total += value
                kernels += 1
            samples.append(total)
            valid += 1
        for variant, samples in values.items():
            require(len(samples) == index["samples_per_variant"], "sample count mismatch")
            expected_median = expected[variant].get(case_id)
            require(expected_median is not None, "sampling case missing from effect CSV")
            require(math.isclose(statistics.median(samples), expected_median, rel_tol=1e-12),
                    "sample median differs from effect CSV")
    require(seen_cases == expected["baseline"].keys(), "missing sampling cases")
    return {"status": "pass", "files": len(files), "direct_sources": len(sources),
            "anchors": anchor_count, "effects": effects, "valid_samples": valid,
            "failed_attempts": failed, "kernel_records": kernels,
            "excluded_binary_files": len(index["excluded_binary_files"]),
            "scope": "archived text integrity and offline arithmetic; no NPU, binary replay or causal review"}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("root", type=Path)
    args = p.parse_args()
    try:
        print(json.dumps(verify(args.root), ensure_ascii=False, indent=2))
    except (ValueError, OSError, KeyError, TypeError, IndexError):
        raise SystemExit("archive verification failed; check files, hashes, references and sample arithmetic") from None
